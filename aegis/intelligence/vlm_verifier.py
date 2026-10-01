"""Asynchronous, evidence-gated Gemini visual verification sidecar.

This module never changes CV scores, alert policy, or camera execution.  It
receives a small immutable evidence package after an incident has been
persisted, then records a separate semantic assessment for operator review.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional

import cv2
import numpy as np
from pydantic import BaseModel, Field, field_validator

from aegis.ai.gemini_client import GeminiClient, GeminiConfig, GeminiError
from aegis.settings import VLMSettings, get_settings

logger = logging.getLogger(__name__)


class VLMVerdict(str, Enum):
    NORMAL = "NORMAL"
    UNCERTAIN = "UNCERTAIN"
    POSSIBLE_CONFRONTATION = "POSSIBLE_CONFRONTATION"
    LIKELY_ASSAULT = "LIKELY_ASSAULT"
    PERSON_FALL = "PERSON_FALL"
    WEAPON_RELATED = "WEAPON_RELATED"
    OTHER_RISK = "OTHER_RISK"


class VerificationStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class VLMAuthorizationError(RuntimeError):
    """Raised when a request no longer passes the backend privacy gate."""


class CombinedVerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNCERTAIN = "UNCERTAIN"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"


class VLMSubject(BaseModel):
    track_id: str = Field(min_length=1, max_length=160)
    role: str = Field(min_length=1, max_length=80)


class VLMObservation(BaseModel):
    timestamp: float = Field(ge=0.0)
    description: str = Field(min_length=1, max_length=800)


class IncidentVerification(BaseModel):
    """Strict provider response.  Gemini cannot introduce new verdict labels."""

    verdict: VLMVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    severity: str = Field(pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    summary: str = Field(min_length=1, max_length=2000)
    subjects: List[VLMSubject] = Field(default_factory=list, max_length=20)
    observations: List[VLMObservation] = Field(default_factory=list, max_length=20)
    supporting_evidence: List[str] = Field(default_factory=list, max_length=20)
    contradicting_evidence: List[str] = Field(default_factory=list, max_length=20)
    uncertainties: List[str] = Field(default_factory=list, max_length=20)
    recommended_action: str = Field(pattern="^(REVIEW|MONITOR|NO_ACTION|ESCALATE)$")
    model: str = Field(default="")
    analysis_version: str = Field(default="vlm-incident-v1")

    @field_validator("supporting_evidence", "contradicting_evidence", "uncertainties")
    @classmethod
    def _bounded_text(cls, values: List[str]) -> List[str]:
        return [str(value).strip()[:800] for value in values if str(value).strip()]


@dataclass(frozen=True)
class EvidenceFrame:
    """Locally encoded keyframe. Binary data is never written to logs or DB."""

    timestamp: datetime
    jpeg: bytes
    risk_score: float
    frame_id: Optional[int] = None
    track_ids: tuple[str, ...] = ()
    signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class IncidentEvidencePackage:
    incident_id: Optional[str]
    camera_id: str
    event_id: str
    start_time: datetime
    end_time: datetime
    risk_score: float
    risk_level: str
    tracks: tuple[str, ...]
    cv_detections: tuple[Dict[str, Any], ...]
    behavior_signals: tuple[str, ...]
    risk_explanation: str
    keyframes: tuple[EvidenceFrame, ...]
    video_clip: Optional[str] = None
    event_type: str = "risk_alert"
    is_candidate: bool = False
    event_frame_id: Optional[int] = None


class EvidenceFrameBuffer:
    """Bounded per-camera JPEG ring buffer for VLM evidence only."""

    def __init__(self, *, max_frames: int, jpeg_quality: int) -> None:
        self._max_frames = max_frames
        self._quality = jpeg_quality
        self._frames: Dict[str, Deque[EvidenceFrame]] = defaultdict(lambda: deque(maxlen=self._max_frames))
        self._condition = threading.Condition()

    def capture(
        self,
        camera_id: str,
        frame: np.ndarray,
        *,
        risk_score: float,
        track_ids: Iterable[str] = (),
        signals: Iterable[str] = (),
        frame_id: Optional[int] = None,
        captured_at: Optional[datetime] = None,
    ) -> None:
        """Compress one sampled local frame; failure cannot affect ingestion."""
        if frame is None or not getattr(frame, "size", 0):
            return
        try:
            image = frame
            height, width = image.shape[:2]
            longest = max(height, width)
            if longest > 960:
                scale = 960 / longest
                image = cv2.resize(image, (round(width * scale), round(height * scale)))
            ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), self._quality])
            if not ok:
                return
            evidence = EvidenceFrame(
                timestamp=captured_at or datetime.now(timezone.utc),
                jpeg=encoded.tobytes(),
                risk_score=max(0.0, min(1.0, float(risk_score))),
                frame_id=int(frame_id) if frame_id is not None else None,
                track_ids=tuple(str(item) for item in track_ids if item is not None),
                signals=tuple(str(item) for item in signals if item),
            )
            with self._condition:
                self._frames[str(camera_id)].append(evidence)
                self._condition.notify_all()
        except Exception as exc:
            logger.debug("VLM evidence capture skipped camera_id=%s: %s", camera_id, type(exc).__name__)

    def wait_for_post_frames(
        self,
        camera_id: str,
        *,
        event_frame_id: int,
        minimum_after: int = 2,
        timeout_seconds: float = 5.0,
    ) -> bool:
        """Wait off the camera thread until post-event frames are buffered."""
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        with self._condition:
            while True:
                frames = self._frames.get(str(camera_id), ())
                if sum(frame.frame_id is not None and frame.frame_id > event_frame_id for frame in frames) >= minimum_after:
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)

    def select(
        self,
        camera_id: str,
        *,
        max_keyframes: int,
        event_frame_id: Optional[int] = None,
    ) -> List[EvidenceFrame]:
        with self._condition:
            frames = list(self._frames.get(str(camera_id), ()))
        if not frames:
            return []
        numbered = [frame for frame in frames if frame.frame_id is not None]
        if event_frame_id is not None and numbered:
            before = [frame for frame in numbered if frame.frame_id < event_frame_id]
            pivot = next((frame for frame in numbered if frame.frame_id == event_frame_id), None)
            after = [frame for frame in numbered if frame.frame_id > event_frame_id]
            if pivot is None:
                pivot = min(numbered, key=lambda frame: abs(frame.frame_id - event_frame_id))
                before = [frame for frame in numbered if frame.frame_id < pivot.frame_id]
                after = [frame for frame in numbered if frame.frame_id > pivot.frame_id]

            count = min(max(1, max_keyframes), len(numbered))
            before_count = min(len(before), max(1, (count - 1) // 2)) if count >= 3 else 0
            after_count = min(len(after), max(1, count - before_count - 1)) if count >= 3 else 0

            def spread(items: List[EvidenceFrame], wanted: int) -> List[EvidenceFrame]:
                if wanted <= 0 or not items:
                    return []
                if len(items) <= wanted:
                    return items
                indexes = {round(index * (len(items) - 1) / max(1, wanted - 1)) for index in range(wanted)}
                return [items[index] for index in sorted(indexes)]

            selected = [*spread(before, before_count), pivot, *spread(after, after_count)]
            selected.sort(key=lambda frame: (frame.frame_id if frame.frame_id is not None else -1, frame.timestamp))
            return selected[:max_keyframes]
        # Preserve temporal context (before/after) and retain the strongest
        # score.  The max is intentionally tiny to control data egress.
        count = min(max(1, max_keyframes), len(frames))
        indexes = {round(index * (len(frames) - 1) / max(1, count - 1)) for index in range(count)}
        peak = max(range(len(frames)), key=lambda index: frames[index].risk_score)
        indexes.add(peak)
        selected = [frames[index] for index in sorted(indexes)]
        if len(selected) > max_keyframes:
            # Keep earliest, strongest, and latest first.
            ordered = {0, peak, len(frames) - 1}
            ordered.update(indexes)
            selected = [frames[index] for index in sorted(ordered)[:max_keyframes]]
        return selected[:max_keyframes]

    def clear_camera(self, camera_id: str) -> None:
        with self._condition:
            self._frames.pop(str(camera_id), None)
            self._condition.notify_all()


def combined_state(
    *,
    cv_risk_level: str,
    verdict: VLMVerdict,
    cv_event_type: str = "risk_alert",
) -> CombinedVerificationState:
    if verdict == VLMVerdict.NORMAL:
        return CombinedVerificationState.CONTRADICTED
    if verdict == VLMVerdict.UNCERTAIN:
        return CombinedVerificationState.UNCERTAIN
    level = str(cv_risk_level).upper()
    if level in {"HIGH", "CRITICAL"}:
        return CombinedVerificationState.SUPPORTED
    event_type = str(cv_event_type or "").upper()
    if "ASSAULT" in event_type or "CONFRONTATION" in event_type:
        return CombinedVerificationState.SUPPORTED if verdict in {
            VLMVerdict.POSSIBLE_CONFRONTATION,
            VLMVerdict.LIKELY_ASSAULT,
        } else CombinedVerificationState.UNCERTAIN
    if "FALL" in event_type:
        return CombinedVerificationState.SUPPORTED if verdict == VLMVerdict.PERSON_FALL else CombinedVerificationState.UNCERTAIN
    if "WEAPON" in event_type:
        return CombinedVerificationState.SUPPORTED if verdict == VLMVerdict.WEAPON_RELATED else CombinedVerificationState.UNCERTAIN
    # A different risk category is not evidence that the CV candidate is
    # either true or false. Keep it reviewable without promoting it.
    return CombinedVerificationState.UNCERTAIN


class VLMVerificationService:
    """Bounded worker pool; its failure path is isolated from camera CV."""

    ANALYSIS_VERSION = "vlm-incident-v1"

    def __init__(
        self,
        settings: Optional[VLMSettings] = None,
        *,
        client_factory: Optional[Callable[[], GeminiClient]] = None,
    ) -> None:
        self.settings = settings or get_settings().vlm
        self._client_factory = client_factory or self._default_client
        self._executor = ThreadPoolExecutor(max_workers=self.settings.max_concurrent_requests, thread_name_prefix="vlm-verify")
        self._slots = threading.BoundedSemaphore(self.settings.max_concurrent_requests)
        self._metrics: Dict[str, float] = defaultdict(float)
        self._metrics_lock = threading.Lock()

    def _default_client(self) -> GeminiClient:
        gemini = get_settings().gemini
        return GeminiClient(GeminiConfig(
            api_key=gemini.api_key,
            model=self.settings.model or gemini.model,
            max_tokens=gemini.max_tokens,
            temperature=0.0,
            timeout=self.settings.timeout_seconds,
            max_retries=1,
        ))

    def should_verify(self, package: IncidentEvidencePackage) -> tuple[bool, str]:
        eligible, reason = self._should_verify_metadata(package)
        if not eligible:
            return False, reason
        if len(package.keyframes) < 4:
            return False, "insufficient_keyframes"
        return True, "eligible"

    def _should_verify_metadata(self, package: IncidentEvidencePackage) -> tuple[bool, str]:
        if not self.settings.enabled:
            return False, "vlm_disabled"
        if not self.settings.allows_camera(package.camera_id):
            return False, "camera_not_allowlisted"
        if not package.event_id or not package.camera_id:
            return False, "missing_event_identity"
        if package.is_candidate:
            if not self.settings.verify_candidates:
                return False, "candidate_verification_disabled"
            if package.incident_id:
                return False, "candidate_already_promoted"
            minimum_score = self.settings.candidate_min_risk_score
            minimum_severity = self.settings.candidate_min_severity
        else:
            if not self.settings.verify_incidents:
                return False, "incident_verification_disabled"
            if not package.incident_id:
                return False, "incident_id_required"
            minimum_score = self.settings.min_risk_score
            minimum_severity = self.settings.min_severity
        levels = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        if package.risk_score < minimum_score:
            return False, "risk_below_threshold"
        if levels.get(package.risk_level.upper(), -1) < levels[minimum_severity]:
            return False, "severity_below_threshold"
        return True, "eligible"

    def schedule(self, package: IncidentEvidencePackage) -> str:
        """Persist the decision and return immediately; never wait for Gemini."""
        verification_id = f"vlm-{uuid.uuid4().hex}"
        if package.is_candidate:
            self._metric("vlm_candidates_total")
        blocked_reason = self._authorization_reason(package)
        if blocked_reason:
            self._record_blocked_schedule(verification_id, package, blocked_reason)
            return verification_id
        eligible, reason = self.should_verify(package)
        if not eligible:
            self._store_status(
                verification_id,
                package,
                VerificationStatus.SKIPPED,
                error=reason,
                combined_state=(
                    CombinedVerificationState.INSUFFICIENT_EVIDENCE
                    if reason == "insufficient_keyframes" else None
                ),
            )
            self._metric("vlm_verifications_skipped")
            return verification_id
        if not self._slots.acquire(blocking=False):
            self._store_status(
                verification_id,
                package,
                VerificationStatus.SKIPPED,
                error="concurrency_limit",
                combined_state=CombinedVerificationState.UNCERTAIN,
            )
            self._metric("vlm_verifications_skipped")
            return verification_id
        self._store_status(verification_id, package, VerificationStatus.PENDING)
        self._executor.submit(self._run, verification_id, package)
        return verification_id

    def schedule_deferred(
        self,
        package: IncidentEvidencePackage,
        package_factory: Callable[[], IncidentEvidencePackage],
        *,
        delay_seconds: float,
    ) -> str:
        """Wait for the configured post-event window before selecting evidence."""
        verification_id = f"vlm-{uuid.uuid4().hex}"
        if package.is_candidate:
            self._metric("vlm_candidates_total")
        blocked_reason = self._authorization_reason(package)
        if blocked_reason:
            self._record_blocked_schedule(verification_id, package, blocked_reason)
            return verification_id
        eligible, reason = self._should_verify_metadata(package)
        if not eligible:
            self._store_status(
                verification_id,
                package,
                VerificationStatus.SKIPPED,
                error=reason,
                combined_state=(
                    CombinedVerificationState.INSUFFICIENT_EVIDENCE
                    if reason == "insufficient_keyframes" else None
                ),
            )
            self._metric("vlm_verifications_skipped")
            return verification_id
        if not self._slots.acquire(blocking=False):
            self._store_status(
                verification_id,
                package,
                VerificationStatus.SKIPPED,
                error="concurrency_limit",
                combined_state=CombinedVerificationState.UNCERTAIN,
            )
            self._metric("vlm_verifications_skipped")
            return verification_id
        self._store_status(verification_id, package, VerificationStatus.PENDING)
        self._executor.submit(self._run_deferred, verification_id, package, package_factory, max(0.0, delay_seconds))
        return verification_id

    def verify_now(self, package: IncidentEvidencePackage) -> IncidentVerification:
        """Synchronous seam for authorised tools/tests; camera code never uses it."""
        return self._request_verdict(package)

    def _authorization_reason(self, package: IncidentEvidencePackage) -> Optional[str]:
        if not self.settings.enabled:
            return "vlm_disabled"
        if not package.camera_id or not self.settings.allows_camera(package.camera_id):
            return "camera_not_allowlisted"
        return None

    @staticmethod
    def _authorization_audit(package: IncidentEvidencePackage, *, allowed: bool, reason: Optional[str] = None) -> Dict[str, Any]:
        return {
            "camera_id": package.camera_id,
            "event_id": package.event_id,
            "authorization_decision": "ALLOW" if allowed else "DENY",
            "provider": "gemini",
            "request_allowed": bool(allowed),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        }

    def _log_authorization(self, package: IncidentEvidencePackage, *, allowed: bool, reason: Optional[str] = None) -> Dict[str, Any]:
        audit = self._authorization_audit(package, allowed=allowed, reason=reason)
        logger.info(
            "vlm_authorization_audit camera_id=%s event_id=%s authorization_decision=%s provider=%s request_allowed=%s timestamp=%s reason=%s",
            audit["camera_id"], audit["event_id"], audit["authorization_decision"],
            audit["provider"], audit["request_allowed"], audit["timestamp"], reason or "none",
        )
        return audit

    def _record_blocked_schedule(
        self,
        verification_id: str,
        package: IncidentEvidencePackage,
        reason: str,
    ) -> None:
        if reason != "vlm_disabled":
            self._metric("vlm_requests_blocked_unauthorized_total")
        audit = self._log_authorization(package, allowed=False, reason=reason)
        self._store_status(
            verification_id,
            package,
            VerificationStatus.SKIPPED,
            error=reason,
            authorization_audit=audit,
        )
        self._metric("vlm_verifications_skipped")

    def _reject_before_provider(self, package: IncidentEvidencePackage, reason: str) -> VLMAuthorizationError:
        if reason != "vlm_disabled":
            self._metric("vlm_requests_blocked_unauthorized_total")
        self._log_authorization(package, allowed=False, reason=reason)
        return VLMAuthorizationError(reason)

    def _run(self, verification_id: str, package: IncidentEvidencePackage) -> None:
        started = time.monotonic()
        try:
            self._process_package(verification_id, package, started)
        except VLMAuthorizationError as exc:
            self._update_status(
                verification_id,
                VerificationStatus.SKIPPED,
                combined_state=CombinedVerificationState.UNCERTAIN,
                error=str(exc),
                evidence_metadata=self._evidence_metadata(package),
            )
            self._metric("vlm_verifications_skipped")
        except Exception as exc:
            self._record_failure(verification_id, package, started, exc)
        finally:
            self._slots.release()

    def _run_deferred(
        self,
        verification_id: str,
        package: IncidentEvidencePackage,
        package_factory: Callable[[], IncidentEvidencePackage],
        delay_seconds: float,
    ) -> None:
        started = time.monotonic()
        try:
            if delay_seconds:
                time.sleep(delay_seconds)
            reason = self._authorization_reason(package)
            if reason:
                self._update_status(
                    verification_id,
                    VerificationStatus.SKIPPED,
                    combined_state=CombinedVerificationState.UNCERTAIN,
                    error=reason,
                    evidence_metadata={"authorization": self._authorization_audit(package, allowed=False, reason=reason)},
                )
                if reason != "vlm_disabled":
                    self._metric("vlm_requests_blocked_unauthorized_total")
                self._log_authorization(package, allowed=False, reason=reason)
                self._metric("vlm_verifications_skipped")
                return
            package = package_factory()
            reason = self._authorization_reason(package)
            if reason:
                self._update_status(
                    verification_id,
                    VerificationStatus.SKIPPED,
                    combined_state=CombinedVerificationState.UNCERTAIN,
                    error=reason,
                    evidence_metadata={"authorization": self._authorization_audit(package, allowed=False, reason=reason)},
                )
                if reason != "vlm_disabled":
                    self._metric("vlm_requests_blocked_unauthorized_total")
                self._log_authorization(package, allowed=False, reason=reason)
                self._metric("vlm_verifications_skipped")
                return
            has_pre_event_frames = (
                package.event_frame_id is None
                or any(
                    frame.frame_id is not None and frame.frame_id < package.event_frame_id
                    for frame in package.keyframes
                )
            )
            has_post_event_frames = (
                package.event_frame_id is None
                or any(
                    frame.frame_id is not None and frame.frame_id > package.event_frame_id
                    for frame in package.keyframes
                )
            )
            has_temporal_context = has_pre_event_frames and has_post_event_frames
            if len(package.keyframes) < 4 or (package.is_candidate and not has_temporal_context):
                self._update_status(
                    verification_id,
                    VerificationStatus.SKIPPED,
                    combined_state=CombinedVerificationState.INSUFFICIENT_EVIDENCE,
                    error=(
                        "insufficient_pre_or_post_event_keyframes"
                        if not has_temporal_context else "insufficient_keyframes"
                    ),
                    evidence_metadata=self._evidence_metadata(package),
                )
                self._metric("vlm_verifications_skipped")
                if package.is_candidate:
                    self._metric("vlm_candidates_uncertain")
                return
            self._process_package(verification_id, package, started)
        except VLMAuthorizationError as exc:
            self._update_status(
                verification_id,
                VerificationStatus.SKIPPED,
                combined_state=CombinedVerificationState.UNCERTAIN,
                error=str(exc),
                evidence_metadata=self._evidence_metadata(package),
            )
            self._metric("vlm_verifications_skipped")
        except Exception as exc:
            self._record_failure(verification_id, package, started, exc)
        finally:
            self._slots.release()

    def _process_package(self, verification_id: str, package: IncidentEvidencePackage, started: float) -> None:
        reason = self._authorization_reason(package)
        if reason:
            raise self._reject_before_provider(package, reason)
        self._update_status(
            verification_id,
            VerificationStatus.PROCESSING,
            evidence_metadata=self._evidence_metadata(package),
        )
        verdict = self._request_verdict(package)
        latency_ms = (time.monotonic() - started) * 1000
        state = combined_state(
            cv_risk_level=package.risk_level,
            verdict=verdict.verdict,
            cv_event_type=package.event_type,
        )
        incident_id = package.incident_id
        self._update_status(
            verification_id,
            VerificationStatus.COMPLETED,
            verdict=verdict,
            combined_state=state,
            latency_ms=latency_ms,
            evidence_metadata=self._evidence_metadata(package),
            incident_id=incident_id,
        )
        self._metric("vlm_requests_total")
        self._metric("vlm_verifications_completed")
        if package.is_candidate:
            if state == CombinedVerificationState.SUPPORTED:
                self._metric("vlm_candidates_supported")
            elif state == CombinedVerificationState.CONTRADICTED:
                self._metric("vlm_candidates_contradicted")
                self._metric("vlm_false_positive_reduction_candidates")
            elif state in {CombinedVerificationState.UNCERTAIN, CombinedVerificationState.INSUFFICIENT_EVIDENCE}:
                self._metric("vlm_candidates_uncertain")
        self._metric("vlm_latency_ms", latency_ms)
        logger.info("vlm_verification completed incident_id=%s event_id=%s camera_id=%s model=%s latency_ms=%.1f", incident_id, package.event_id, package.camera_id, verdict.model, latency_ms)

    def _record_failure(self, verification_id: str, package: IncidentEvidencePackage, started: float, exc: Exception) -> None:
        latency_ms = (time.monotonic() - started) * 1000
        self._update_status(
            verification_id,
            VerificationStatus.FAILED,
            combined_state=CombinedVerificationState.FAILED,
            error=type(exc).__name__,
            latency_ms=latency_ms,
            evidence_metadata=self._evidence_metadata(package),
        )
        self._metric("vlm_requests_total")
        self._metric("vlm_requests_failed")
        if package.is_candidate:
            self._metric("vlm_candidate_failures")
        logger.warning("vlm_verification failed incident_id=%s event_id=%s camera_id=%s error=%s", package.incident_id, package.event_id, package.camera_id, type(exc).__name__)

    @staticmethod
    def _evidence_metadata(package: IncidentEvidencePackage) -> Dict[str, Any]:
        return {
            "keyframe_count": len(package.keyframes),
            "keyframe_timestamps": [frame.timestamp.isoformat() for frame in package.keyframes],
            "keyframe_frame_ids": [frame.frame_id for frame in package.keyframes],
            "event_frame_id": package.event_frame_id,
            "clip_path": package.video_clip,
        }

    def _request_verdict(self, package: IncidentEvidencePackage) -> IncidentVerification:
        reason = self._authorization_reason(package)
        if reason:
            raise self._reject_before_provider(package, reason)
        audit = self._log_authorization(package, allowed=True)
        self._metric("vlm_requests_authorized_total")
        client = self._client_factory()
        prompt = self._prompt(package)
        self._metric("vlm_requests_sent_total")
        payload = client.verify_incident(
            prompt,
            [frame.jpeg for frame in package.keyframes],
            response_schema=self._gemini_response_schema(),
        )
        verdict = IncidentVerification.model_validate(payload)
        if package.keyframes:
            offsets = self._frame_offsets(package)
            for observation in verdict.observations:
                if min(abs(observation.timestamp - offset) for offset in offsets) > 0.75:
                    raise GeminiError("Observation timestamp is not grounded in a supplied keyframe.")
        return verdict.model_copy(update={"model": client.config.model, "analysis_version": self.ANALYSIS_VERSION})

    @staticmethod
    def _gemini_response_schema() -> Dict[str, Any]:
        """Use Gemini's documented JSON Schema subset; Pydantic validates strictly afterward."""
        subject = {
            "type": "object",
            "properties": {"track_id": {"type": "string"}, "role": {"type": "string"}},
            "required": ["track_id", "role"],
            "additionalProperties": False,
        }
        observation = {
            "type": "object",
            "properties": {"timestamp": {"type": "number", "minimum": 0}, "description": {"type": "string"}},
            "required": ["timestamp", "description"],
            "additionalProperties": False,
        }
        text_list = {"type": "array", "items": {"type": "string"}, "maxItems": 20}
        return {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": [item.value for item in VLMVerdict]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "severity": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
                "summary": {"type": "string"},
                "subjects": {"type": "array", "items": subject, "maxItems": 20},
                "observations": {"type": "array", "items": observation, "maxItems": 20},
                "supporting_evidence": text_list,
                "contradicting_evidence": text_list,
                "uncertainties": text_list,
                "recommended_action": {"type": "string", "enum": ["REVIEW", "MONITOR", "NO_ACTION", "ESCALATE"]},
            },
            "required": [
                "verdict", "confidence", "severity", "summary", "subjects", "observations",
                "supporting_evidence", "contradicting_evidence", "uncertainties",
                "recommended_action",
            ],
            "additionalProperties": False,
        }

    @staticmethod
    def _frame_offsets(package: IncidentEvidencePackage) -> List[float]:
        if not package.keyframes:
            return []
        origin = package.keyframes[0].timestamp
        offsets = []
        for frame in package.keyframes:
            timestamp = frame.timestamp
            if origin.tzinfo is None and timestamp.tzinfo is not None:
                origin = origin.replace(tzinfo=timezone.utc)
            elif timestamp.tzinfo is None and origin.tzinfo is not None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            offsets.append(max(0.0, (timestamp - origin).total_seconds()))
        return offsets

    @staticmethod
    def _prompt(package: IncidentEvidencePackage) -> str:
        frame_timestamps = [
            f"frame {index}: {offset:.2f}s"
            for index, offset in enumerate(VLMVerificationService._frame_offsets(package), start=1)
        ]
        return (
            "Verify this candidate security incident from the ordered keyframes. "
            "Return only the supplied JSON schema. Base statements exclusively on visible evidence. "
            "Do not identify people or infer intent. Observation timestamps must use one of the supplied seconds relative to the first keyframe. "
            "If evidence is insufficient or ambiguous, return UNCERTAIN and explain why.\n"
            f"Record type: {'candidate event' if package.is_candidate else 'incident'}; event: {package.event_id}; "
            f"incident: {package.incident_id or 'not promoted'}; source event type: {package.event_type}; "
            f"camera: {package.camera_id}; risk level: {package.risk_level}; "
            f"risk score: {package.risk_score:.2f}; tracks: {list(package.tracks)}; "
            f"CV signals: {list(package.behavior_signals)}; CV explanation: {package.risk_explanation[:1000]}; "
            f"available keyframe timestamps: {', '.join(frame_timestamps)}"
        )

    @staticmethod
    def _repository():
        from aegis.database.repositories import IncidentVerificationRepository
        return IncidentVerificationRepository

    def _store_status(
        self,
        verification_id: str,
        package: IncidentEvidencePackage,
        status: VerificationStatus,
        *,
        error: Optional[str] = None,
        combined_state: Optional[CombinedVerificationState] = None,
        authorization_audit: Optional[Dict[str, Any]] = None,
    ) -> None:
        from aegis.database.connection import get_db_session
        with get_db_session() as session:
            self._repository()(session).create_or_get(
                verification_id=verification_id,
                incident_id=package.incident_id,
                event_id=package.event_id,
                camera_id=package.camera_id,
                status=status.value,
                provider="gemini",
                model=self.settings.model or get_settings().gemini.model,
                combined_state=combined_state.value if combined_state else None,
                error=error,
                evidence_metadata={
                    "keyframe_count": len(package.keyframes),
                    "clip_path": package.video_clip,
                    "authorization": authorization_audit or self._authorization_audit(
                        package,
                        allowed=self._authorization_reason(package) is None,
                        reason=self._authorization_reason(package),
                    ),
                },
            )

    def _update_status(self, verification_id: str, status: VerificationStatus, *, verdict: Optional[IncidentVerification] = None, combined_state: Optional[CombinedVerificationState] = None, latency_ms: Optional[float] = None, error: Optional[str] = None, evidence_metadata: Optional[Dict[str, Any]] = None, incident_id: Optional[str] = None) -> None:
        from aegis.database.connection import get_db_session
        with get_db_session() as session:
            self._repository()(session).update(
                verification_id,
                status=status.value,
                verdict=verdict.model_dump(mode="json") if verdict else None,
                combined_state=combined_state.value if combined_state else None,
                latency_ms=latency_ms,
                error=error,
                evidence_metadata=evidence_metadata,
                incident_id=incident_id,
            )

    def _metric(self, name: str, value: float = 1.0) -> None:
        with self._metrics_lock:
            self._metrics[name] += value

    def metrics(self) -> Dict[str, float]:
        with self._metrics_lock:
            return dict(self._metrics)


_verifier: Optional[VLMVerificationService] = None
_verifier_lock = threading.Lock()


def get_vlm_verifier() -> VLMVerificationService:
    global _verifier
    with _verifier_lock:
        if _verifier is None:
            _verifier = VLMVerificationService()
        return _verifier


def build_persisted_incident_package(incident_id: str) -> IncidentEvidencePackage:
    """Build an authorised on-demand package from existing durable snapshots."""
    from pathlib import Path
    from aegis.database.connection import get_db_session
    from aegis.database.repositories import EventRepository, IncidentRepository

    with get_db_session() as session:
        incident = IncidentRepository(session).get_by_incident_id(incident_id)
        if incident is None:
            raise ValueError("incident_not_found")
        events = EventRepository(session).get_by_incident_id(incident_id)
        base_package = IncidentEvidencePackage(
            incident_id=incident.incident_id,
            camera_id=str(incident.camera_id or ""),
            event_id=str(events[-1].event_id) if events else incident.incident_id,
            start_time=incident.start_time,
            end_time=incident.last_seen_time,
            risk_score=float(incident.max_risk_score or 0.0),
            risk_level=str(incident.current_risk_level or "LOW"),
            tracks=tuple(filter(None, [incident.primary_track_id, *(incident.related_track_ids or [])])),
            cv_detections=tuple(),
            behavior_signals=tuple(str(item) for item in (incident.contributing_factors or [])),
            risk_explanation=str(incident.summary_reason or ""),
            keyframes=tuple(),
        )
        service = get_vlm_verifier()
        reason = service._authorization_reason(base_package)
        unauthorized_event = next(
            (
                event for event in events
                if not service.settings.allows_camera(str(event.camera_id or ""))
            ),
            None,
        )
        if unauthorized_event is not None:
            denied_package = IncidentEvidencePackage(
                **{**base_package.__dict__, "camera_id": str(unauthorized_event.camera_id or ""), "event_id": str(unauthorized_event.event_id)}
            )
            reason = "camera_not_allowlisted"
            try:
                raise service._reject_before_provider(denied_package, reason)
            except VLMAuthorizationError as exc:
                raise ValueError(str(exc)) from exc
        if reason:
            try:
                raise service._reject_before_provider(base_package, reason)
            except VLMAuthorizationError as exc:
                raise ValueError(str(exc)) from exc

        # Authorization is complete before any snapshot file is opened/read.
        frames: List[EvidenceFrame] = []
        for event in events:
            path = Path(event.snapshot_path) if event.snapshot_status == "saved" and event.snapshot_path else None
            if path is None or not path.is_file():
                continue
            try:
                frames.append(EvidenceFrame(
                    timestamp=event.timestamp or incident.last_seen_time,
                    jpeg=path.read_bytes(),
                    risk_score=float(event.risk_score or 0.0),
                    track_ids=tuple(filter(None, [event.track_key])),
                    signals=tuple(str(item) for item in (event.factors or [])),
                ))
            except OSError:
                continue
        selected = sorted(frames, key=lambda frame: frame.risk_score, reverse=True)[:8]
        selected.sort(key=lambda frame: frame.timestamp)
        return IncidentEvidencePackage(**{**base_package.__dict__, "keyframes": tuple(selected)})
