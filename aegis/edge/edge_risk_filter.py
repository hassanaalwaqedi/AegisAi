"""
AegisAI - Edge Risk Filter

Lightweight, rule-based risk assessment that runs on every frame at the edge.
Determines whether a frame is suspicious enough to escalate to the cloud
for deep multi-model analysis.

This module is designed for CPU-only execution with minimal latency.

Features:
- Weapon detection scoring (weapon present, weapon+person coexist, bbox overlap)
- Behavioral anomaly scoring (loitering, erratic, running)
- Per-track cooldown to prevent event flooding
- Frame compression for cloud transmission
- Event-based triggering (only suspicious frames leave the edge)

Phase 6: Edge/Cloud Hybrid Intelligence
"""

import logging
import time
import numpy as np
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from config import EdgeConfig, AegisConfig
from aegis.edge.event_types import EdgeAssessment, TrackSummary, SuspiciousEvent

logger = logging.getLogger(__name__)


def bbox_iou(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> float:
    """
    Compute Intersection over Union between two bounding boxes.
    
    Args:
        box_a: (x1, y1, x2, y2) first bounding box
        box_b: (x1, y1, x2, y2) second bounding box
    
    Returns:
        IoU value between 0.0 and 1.0
    """
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    if intersection == 0:
        return 0.0
    
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - intersection
    
    if union == 0:
        return 0.0
    
    return intersection / union


def bbox_contains(outer: Tuple[int, int, int, int], inner: Tuple[int, int, int, int]) -> bool:
    """Check if inner bbox center is inside outer bbox."""
    cx = (inner[0] + inner[2]) / 2
    cy = (inner[1] + inner[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


class EdgeRiskFilter:
    """
    Lightweight edge-side risk filter for hybrid architecture.
    
    Runs fast rule-based assessment on YOLO+tracker outputs.
    Only escalates suspicious events to the cloud for deep analysis.
    
    Rules:
    1. Weapon detected anywhere → +0.5 risk
    2. Weapon + Person in same frame → +0.3 risk
    3. Weapon bbox overlaps Person bbox → +0.2 risk
    4. Behavioral anomaly (loitering, erratic, running) → +0.15 risk
    5. Risk >= escalation_threshold → escalate to cloud
    
    Example:
        >>> filter = EdgeRiskFilter(config)
        >>> assessment = filter.assess(tracks, frame_id=42)
        >>> if assessment.should_escalate:
        ...     event = filter.create_event(frame, assessment, camera_id="cam1")
        ...     cloud_client.send_event(event)
    """
    
    def __init__(self, config: Optional[AegisConfig] = None, edge_config: Optional[EdgeConfig] = None):
        """
        Initialize the edge risk filter.
        
        Args:
            config: Full AegisConfig instance (preferred)
            edge_config: EdgeConfig instance (alternative)
        """
        if config is not None:
            self._config = config.edge
        else:
            self._config = edge_config or EdgeConfig()
        
        # Per-track cooldown: track_id → last escalation timestamp
        self._cooldowns: Dict[int, float] = {}
        
        # Statistics
        self._total_frames = 0
        self._total_escalations = 0
        self._total_weapons_detected = 0
        
        logger.info(
            f"EdgeRiskFilter initialized | "
            f"threshold={self._config.escalation_threshold}, "
            f"cooldown={self._config.event_cooldown_seconds}s"
        )
    
    @property
    def config(self) -> EdgeConfig:
        """Get edge configuration."""
        return self._config
    
    @property
    def escalation_rate(self) -> float:
        """Percentage of frames escalated to cloud."""
        if self._total_frames == 0:
            return 0.0
        return self._total_escalations / self._total_frames
    
    def assess(self, tracks: list, frame_id: int = 0) -> EdgeAssessment:
        """
        Assess risk for a set of tracked objects in a single frame.
        
        This is the core edge intelligence — fast, rule-based, CPU-only.
        
        Args:
            tracks: List of Track/Detection objects from YOLO+tracker
            frame_id: Current frame number
            
        Returns:
            EdgeAssessment with risk score, triggers, and escalation decision
        """
        self._total_frames += 1
        
        score = 0.0
        triggers = []
        track_summaries = []
        
        # Classify tracks
        persons = []
        weapons = []
        animals = []
        
        for track in tracks:
            # Extract attributes (works with both Detection and Track objects)
            bbox = getattr(track, 'bbox', (0, 0, 0, 0))
            class_name = getattr(track, 'class_name', 'unknown')
            class_id = getattr(track, 'class_id', -1)
            confidence = getattr(track, 'confidence', 0.0)
            track_id = getattr(track, 'track_id', None)
            is_weapon = getattr(track, 'is_weapon', False)
            is_person = getattr(track, 'is_person', False) or class_id == 0
            is_animal = getattr(track, 'is_animal', False)
            category = getattr(track, 'object_category', 'generic')
            
            summary = TrackSummary(
                track_id=track_id,
                class_name=class_name,
                class_id=class_id,
                confidence=confidence,
                bbox=tuple(bbox) if not isinstance(bbox, tuple) else bbox,
                object_category=category,
                is_weapon=is_weapon,
                is_person=is_person,
                is_animal=is_animal,
            )
            track_summaries.append(summary)
            
            if is_person:
                persons.append(summary)
            if is_weapon:
                weapons.append(summary)
            if is_animal:
                animals.append(summary)
        
        # ── Rule 1: Weapon detected ──
        if weapons:
            score += self._config.weapon_detected_score
            weapon_names = [w.class_name for w in weapons]
            triggers.append(f"weapon_detected:{','.join(weapon_names)}")
            self._total_weapons_detected += 1
        
        # ── Rule 2: Weapon + Person coexist ──
        if weapons and persons:
            score += self._config.weapon_person_coexist_score
            triggers.append("weapon_person_coexist")
            
            # ── Rule 3: Weapon bbox overlaps Person bbox ──
            for weapon in weapons:
                for person in persons:
                    iou = bbox_iou(weapon.bbox, person.bbox)
                    if iou > 0.05:
                        score += self._config.weapon_person_overlap_score
                        triggers.append(
                            f"weapon_person_overlap:iou={iou:.2f}:"
                            f"w_id={weapon.track_id}:p_id={person.track_id}"
                        )
                        break  # One overlap per weapon is enough
                    
                    # Check if weapon center is inside person bbox
                    if bbox_contains(person.bbox, weapon.bbox):
                        score += self._config.weapon_person_overlap_score
                        triggers.append(
                            f"weapon_inside_person:"
                            f"w_id={weapon.track_id}:p_id={person.track_id}"
                        )
                        break
        
        # ── Rule 4: Behavioral anomalies ──
        for track in tracks:
            behavior = getattr(track, 'behavior', None)
            if behavior and hasattr(behavior, 'has_anomaly') and behavior.has_anomaly:
                score += self._config.behavioral_anomaly_score
                triggers.append(f"behavioral_anomaly:track_id={getattr(track, 'track_id', '?')}")
                break  # Count anomaly once per frame
        
        # ── Rule 5: Animal false-positive warning ──
        if animals and persons:
            # If animals detected alongside persons, note it
            # but don't increase risk (this is informational)
            triggers.append(f"animals_present:{len(animals)}")
        
        # Clamp score
        score = min(score, 1.0)
        
        # Determine escalation
        should_escalate = (
            score >= self._config.escalation_threshold
            and self._check_cooldown(tracks, frame_id)
        )
        
        if should_escalate:
            self._total_escalations += 1
            self._update_cooldowns(tracks)
            logger.info(
                f"ESCALATE frame {frame_id} | "
                f"score={score:.2f} | triggers={triggers}"
            )
        
        return EdgeAssessment(
            risk_score=score,
            triggers=triggers,
            should_escalate=should_escalate,
            track_summaries=track_summaries,
            frame_id=frame_id,
            timestamp=time.time(),
        )
    
    def create_event(
        self,
        frame: np.ndarray,
        assessment: EdgeAssessment,
        camera_id: str = "default"
    ) -> SuspiciousEvent:
        """
        Create a SuspiciousEvent from a frame and its assessment.
        Compresses the frame to JPEG for efficient cloud transmission.
        
        Args:
            frame: Raw video frame (BGR numpy array)
            assessment: EdgeAssessment from assess()
            camera_id: Camera identifier
            
        Returns:
            SuspiciousEvent ready for cloud transmission
        """
        # Compress frame to JPEG
        quality = self._config.frame_compression_quality
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        _, jpeg_buffer = cv2.imencode('.jpg', frame, encode_params)
        frame_jpeg = jpeg_buffer.tobytes()
        
        h, w = frame.shape[:2]
        
        event = SuspiciousEvent(
            camera_id=camera_id,
            frame_jpeg=frame_jpeg,
            tracks=assessment.track_summaries,
            edge_risk_score=assessment.risk_score,
            triggers=assessment.triggers,
            frame_id=assessment.frame_id,
            frame_width=w,
            frame_height=h,
        )
        
        logger.debug(
            f"Created event {event.event_id} | "
            f"frame_size={len(frame_jpeg)} bytes | "
            f"tracks={len(assessment.track_summaries)}"
        )
        
        return event
    
    def _check_cooldown(self, tracks: list, frame_id: int) -> bool:
        """
        Check if any track in this frame is past its escalation cooldown.
        
        Returns True if at least one involved track can be escalated.
        """
        now = time.time()
        cooldown = self._config.event_cooldown_seconds
        
        for track in tracks:
            track_id = getattr(track, 'track_id', None)
            if track_id is None:
                return True  # Untracked detections always pass cooldown
            
            last_time = self._cooldowns.get(track_id, 0.0)
            if now - last_time >= cooldown:
                return True
        
        return False
    
    def _update_cooldowns(self, tracks: list) -> None:
        """Update cooldown timestamps for all tracks in the frame."""
        now = time.time()
        for track in tracks:
            track_id = getattr(track, 'track_id', None)
            if track_id is not None:
                self._cooldowns[track_id] = now
    
    def cleanup_cooldowns(self, max_age: float = 300.0) -> int:
        """
        Remove expired cooldown entries.
        
        Args:
            max_age: Remove entries older than this (seconds)
            
        Returns:
            Number of entries removed
        """
        now = time.time()
        expired = [
            tid for tid, ts in self._cooldowns.items()
            if now - ts > max_age
        ]
        for tid in expired:
            del self._cooldowns[tid]
        return len(expired)
    
    def get_stats(self) -> dict:
        """Get filter statistics."""
        return {
            "total_frames": self._total_frames,
            "total_escalations": self._total_escalations,
            "escalation_rate": round(self.escalation_rate, 4),
            "weapons_detected": self._total_weapons_detected,
            "active_cooldowns": len(self._cooldowns),
        }
    
    def reset(self) -> None:
        """Reset all state."""
        self._cooldowns.clear()
        self._total_frames = 0
        self._total_escalations = 0
        self._total_weapons_detected = 0
        logger.info("EdgeRiskFilter reset")
    
    def __repr__(self) -> str:
        return (
            f"EdgeRiskFilter(threshold={self._config.escalation_threshold}, "
            f"frames={self._total_frames}, escalations={self._total_escalations})"
        )
