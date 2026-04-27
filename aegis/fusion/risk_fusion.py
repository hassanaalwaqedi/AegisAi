"""
AegisAI - Risk Fusion Engine (Cloud-Side)

Combines outputs from multiple AI models (CLIP, SAM, MiDaS, SlowFast)
into unified threat assessments. Runs on AWS GPU instances.

This is a scaffold — model integration will be added when
the cloud layer is deployed to AWS EC2.

Phase 6: Edge/Cloud Hybrid Intelligence
"""

import logging
import time
from typing import Dict, List, Optional

from aegis.fusion.threat_types import ThreatAssessment

logger = logging.getLogger(__name__)


class RiskFusionEngine:
    """
    Multi-model risk fusion for cloud-side analysis.
    
    Takes edge-provided detection metadata and runs heavy
    models to produce refined threat assessments.
    
    Models (to be integrated on AWS deployment):
    - CLIP: Vision-language context verification
    - MobileSAM: Precise segmentation for holding detection
    - MiDaS: Monocular depth for 3D distances
    - SlowFast: Action recognition (walk/run/aim/attack)
    
    Example:
        >>> engine = RiskFusionEngine()
        >>> assessments = engine.analyze(
        ...     frame=frame_array,
        ...     tracks=track_summaries,
        ...     edge_triggers=["weapon_person_overlap"]
        ... )
    """
    
    def __init__(self):
        """Initialize the fusion engine. Models are lazy-loaded."""
        self._clip_model = None
        self._sam_model = None
        self._depth_model = None
        self._action_model = None
        self._initialized = False
        
        logger.info("RiskFusionEngine initialized (models will lazy-load)")
    
    def analyze(
        self,
        frame,
        tracks: List[dict],
        edge_triggers: List[str],
        edge_risk_score: float = 0.0,
    ) -> List[ThreatAssessment]:
        """
        Run multi-model analysis on a suspicious frame.
        
        This is the core fusion logic. Currently returns enhanced
        assessments based on edge data. Full model integration
        will be added for AWS deployment.
        
        Args:
            frame: Decoded frame (numpy array)
            tracks: Track summaries from edge
            edge_triggers: What triggered escalation
            edge_risk_score: Edge-computed risk score
            
        Returns:
            List of ThreatAssessment for each relevant entity
        """
        start = time.time()
        assessments = []
        
        # Separate persons and weapons
        persons = [t for t in tracks if t.get("is_person", False)]
        weapons = [t for t in tracks if t.get("is_weapon", False)]
        
        # Build threat assessments
        for person in persons:
            assessment = ThreatAssessment(
                track_id=person.get("track_id"),
                person_class="person",
                risk_score=edge_risk_score,
            )
            
            models_used = ["edge_filter"]
            explanation_parts = []
            
            # ── CLIP Context Check (stub) ──
            clip_score = self._run_clip_check(frame, person, weapons)
            if clip_score is not None:
                assessment.model_scores["clip"] = clip_score
                models_used.append("clip")
                if clip_score > 0.5:
                    explanation_parts.append(
                        f"CLIP confirms weapon context ({clip_score:.0%})"
                    )
            
            # ── SAM Segmentation Check (stub) ──
            sam_holding = self._run_sam_check(frame, person, weapons)
            if sam_holding is not None:
                assessment.holding_confidence = sam_holding
                assessment.model_scores["sam"] = sam_holding
                models_used.append("sam")
                if sam_holding > 0.5:
                    explanation_parts.append(
                        f"SAM holding confidence: {sam_holding:.0%}"
                    )
            
            # ── MiDaS Depth Check (stub) ──
            depth_info = self._run_depth_check(frame, person, weapons)
            if depth_info:
                assessment.weapon_distance_m = depth_info.get("distance")
                assessment.position_3d = depth_info.get("position_3d")
                assessment.model_scores["midas"] = 1.0
                models_used.append("midas")
                if depth_info.get("distance"):
                    explanation_parts.append(
                        f"Weapon distance: {depth_info['distance']:.1f}m"
                    )
            
            # ── SlowFast Action Check (stub) ──
            action = self._run_action_check(frame, person)
            if action:
                assessment.action = action
                assessment.model_scores["slowfast"] = 1.0
                models_used.append("slowfast")
                explanation_parts.append(f"Action: {action}")
            
            # ── Determine final weapon type ──
            if weapons:
                nearest_weapon = weapons[0]  # Simple: take first weapon
                assessment.weapon_type = nearest_weapon.get("class_name", "weapon")
            
            # ── Compute fused risk score ──
            fused_score = self._compute_fused_score(
                edge_risk_score, assessment, edge_triggers
            )
            assessment.risk_score = fused_score
            assessment.risk_level = self._score_to_level(fused_score)
            
            # ── Build explanation ──
            if weapons:
                explanation_parts.insert(0, f"Weapon ({assessment.weapon_type}) detected near person")
            
            assessment.explanation = " | ".join(explanation_parts) if explanation_parts else "Normal activity"
            assessment.contributing_models = models_used
            
            assessments.append(assessment)
        
        elapsed = (time.time() - start) * 1000
        logger.debug(f"Fusion analysis complete: {len(assessments)} assessments in {elapsed:.0f}ms")
        
        return assessments
    
    def _run_clip_check(self, frame, person, weapons) -> Optional[float]:
        """
        Run CLIP vision-language check.
        
        Stub: Returns None until CLIP model is loaded on AWS.
        When implemented, will evaluate prompts like:
        "person holding a gun", "person with a knife"
        """
        if self._clip_model is None:
            return None
        # TODO: Implement CLIP inference
        return None
    
    def _run_sam_check(self, frame, person, weapons) -> Optional[float]:
        """
        Run MobileSAM segmentation to check mask overlap.
        
        Stub: Returns None until SAM model is loaded on AWS.
        When implemented, will compute overlap between person
        and weapon masks to determine "holding" confidence.
        """
        if self._sam_model is None:
            return None
        # TODO: Implement SAM inference
        return None
    
    def _run_depth_check(self, frame, person, weapons) -> Optional[dict]:
        """
        Run MiDaS depth estimation.
        
        Stub: Returns None until MiDaS model is loaded on AWS.
        When implemented, will estimate 3D distance between
        person and weapon, and distance to restricted zones.
        """
        if self._depth_model is None:
            return None
        # TODO: Implement MiDaS inference
        return None
    
    def _run_action_check(self, frame, person) -> Optional[str]:
        """
        Run SlowFast action recognition.
        
        Stub: Returns None until SlowFast model is loaded on AWS.
        When implemented, will classify actions:
        walking, running, aiming, attacking, standing.
        """
        if self._action_model is None:
            return None
        # TODO: Implement SlowFast inference
        return None
    
    def _compute_fused_score(
        self,
        edge_score: float,
        assessment: ThreatAssessment,
        triggers: List[str],
    ) -> float:
        """
        Compute final fused risk score from all model outputs.
        
        When cloud models are not loaded (stubs), this simply
        returns the edge score. As models come online, each
        contributes weighted evidence.
        """
        score = edge_score
        
        # Boost from CLIP context
        clip = assessment.model_scores.get("clip", 0.0)
        if clip > 0.5:
            score = min(score + 0.15, 1.0)
        
        # Boost from SAM holding detection
        if assessment.holding_confidence > 0.6:
            score = min(score + 0.2, 1.0)
        
        # Boost from dangerous actions
        dangerous_actions = {"aiming", "attacking"}
        if assessment.action in dangerous_actions:
            score = min(score + 0.15, 1.0)
        
        # Boost for close weapon proximity
        if assessment.weapon_distance_m is not None and assessment.weapon_distance_m < 1.5:
            score = min(score + 0.1, 1.0)
        
        return min(score, 1.0)
    
    @staticmethod
    def _score_to_level(score: float) -> str:
        """Map score to risk level."""
        if score >= 0.75:
            return "CRITICAL"
        elif score >= 0.50:
            return "HIGH"
        elif score >= 0.25:
            return "MEDIUM"
        return "LOW"
    
    def __repr__(self) -> str:
        models = []
        if self._clip_model:
            models.append("CLIP")
        if self._sam_model:
            models.append("SAM")
        if self._depth_model:
            models.append("MiDaS")
        if self._action_model:
            models.append("SlowFast")
        return f"RiskFusionEngine(models={models or ['edge_only']})"
