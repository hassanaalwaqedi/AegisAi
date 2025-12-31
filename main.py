#!/usr/bin/env python3
# === WARNING SUPPRESSION (MUST BE FIRST) ===
import warnings
import os
warnings.filterwarnings('ignore')
warnings.filterwarnings('ignore', category=RuntimeWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)
os.environ['PYTHONWARNINGS'] = 'ignore'
# === END WARNING SUPPRESSION ===

"""
AegisAI - Smart City Risk Intelligence System
Main Entry Point

Phase 1: Perception Layer - Object detection and tracking
Phase 2: Analysis Layer - Behavioral intelligence (--enable-analysis)

This module orchestrates the full pipeline:
1. Video input handling (files or camera streams)
2. Object detection (YOLOv8)
3. Multi-object tracking (DeepSORT)
4. Behavioral analysis (Phase 2, optional)
5. Visualization and output

Usage:
    # Process a video file
    python main.py --input video.mp4 --output result.mp4

    # Use camera stream
    python main.py --input 0 --output result.mp4

    # Enable Phase 2 Analysis
    python main.py --input video.mp4 --output result.mp4 --enable-analysis

    # With custom model
    python main.py --input video.mp4 --output result.mp4 --model yolov8m.pt

    # Disable display window
    python main.py --input video.mp4 --output result.mp4 --no-display

Copyright 2024 AegisAI Project
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional, Dict, List
from collections import defaultdict

import cv2

from config import (
    AegisConfig,
    DetectionConfig,
    TrackingConfig,
    VideoConfig,
    VisualizationConfig,
    AnalysisConfig,
    RiskConfig,
    AlertConfig,
    APIConfig,
    SemanticConfig,
    DeviceType
)
from aegis.detection import YOLODetector
from aegis.tracking import DeepSORTTracker
from aegis.video import VideoSource, VideoWriter
from aegis.visualization import Renderer

# Phase 2 imports (conditional for backward compatibility)
try:
    from aegis.analysis import (
        TrackHistoryManager,
        MotionAnalyzer,
        MotionAnalyzerConfig,
        BehaviorAnalyzer,
        BehaviorAnalyzerConfig,
        CrowdAnalyzer,
        CrowdAnalyzerConfig,
        FrameAnalysis,
        TrackAnalysis,
        MotionState,
        BehaviorFlags
    )
    ANALYSIS_AVAILABLE = True
except ImportError:
    ANALYSIS_AVAILABLE = False

# Phase 3 imports (conditional for backward compatibility)
try:
    from aegis.risk import (
        RiskEngine,
        RiskEngineConfig,
        RiskWeights,
        RiskThresholds,
        TemporalConfig,
        ZoneManager,
        RiskLevel,
        FrameRiskSummary
    )
    RISK_AVAILABLE = True
except ImportError:
    RISK_AVAILABLE = False

# Phase 4 imports (conditional for backward compatibility)
try:
    from aegis.alerts import AlertManager, AlertManagerConfig, AlertLevel
    from aegis.api import APIServer, APIConfig as APIServerConfig, get_state
    RESPONSE_AVAILABLE = True
except ImportError:
    RESPONSE_AVAILABLE = False

# Phase 5 imports (conditional for backward compatibility)
try:
    from aegis.semantic import (
        DinoEngine,
        PromptManager,
        SemanticTrigger,
        SemanticFusion,
        SemanticExecutor,
        UnifiedObjectIntelligence
    )
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("AegisAI")


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.
    
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="AegisAI - Smart City Risk Intelligence System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input video.mp4 --output result.mp4
  %(prog)s --input 0 --output camera_output.mp4
  %(prog)s --input video.mp4 --output result.mp4 --enable-analysis
  %(prog)s --input video.mp4 --output result.mp4 --confidence 0.6
        """
    )
    
    # Input/Output arguments
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input video file path or camera index (e.g., 0 for webcam)"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output video file path"
    )
    
    # Model arguments
    parser.add_argument(
        "--model", "-m",
        default="yolov8n.pt",
        help="YOLOv8 model path or name (default: yolov8n.pt)"
    )
    parser.add_argument(
        "--confidence", "-c",
        type=float,
        default=0.5,
        help="Detection confidence threshold (default: 0.5)"
    )
    
    # Device arguments
    parser.add_argument(
        "--device", "-d",
        choices=["auto", "cpu", "cuda", "mps"],
        default="auto",
        help="Compute device (default: auto)"
    )
    
    # Display arguments
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Disable live preview window"
    )
    parser.add_argument(
        "--show-fps",
        action="store_true",
        default=True,
        help="Show FPS overlay on output (default: True)"
    )
    
    # Tracking arguments
    parser.add_argument(
        "--max-age",
        type=int,
        default=30,
        help="Maximum frames to keep lost tracks (default: 30)"
    )
    
    # Performance optimization arguments
    parser.add_argument(
        "--frame-skip",
        type=int,
        default=1,
        help="Process every Nth frame (1=all, 2=skip half, etc.) (default: 1)"
    )
    parser.add_argument(
        "--no-fp16",
        action="store_true",
        help="Disable FP16 half-precision inference"
    )

    
    # Phase 2: Analysis arguments
    parser.add_argument(
        "--enable-analysis",
        action="store_true",
        help="Enable Phase 2 behavioral analysis"
    )
    parser.add_argument(
        "--loitering-threshold",
        type=float,
        default=5.0,
        help="Seconds stationary to detect loitering (default: 5.0)"
    )
    
    # Phase 3: Risk arguments
    parser.add_argument(
        "--enable-risk",
        action="store_true",
        help="Enable Phase 3 risk scoring (requires --enable-analysis)"
    )
    parser.add_argument(
        "--demo-zones",
        action="store_true",
        help="Add demo risk zones for testing"
    )
    
    # Phase 4: Response arguments
    parser.add_argument(
        "--enable-alerts",
        action="store_true",
        help="Enable Phase 4 alert generation"
    )
    parser.add_argument(
        "--enable-api",
        action="store_true",
        help="Enable Phase 4 REST API server"
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=8080,
        help="API server port (default: 8080)"
    )
    
    # Phase 5: Semantic arguments
    parser.add_argument(
        "--enable-semantic",
        action="store_true",
        help="Enable Phase 5 semantic layer (Grounding DINO)"
    )
    parser.add_argument(
        "--semantic-prompt",
        type=str,
        default=None,
        help="Initial semantic query (e.g., 'person with bag near entrance')"
    )
    parser.add_argument(
        "--semantic-risk-threshold",
        type=float,
        default=0.6,
        help="Risk score threshold for auto-triggering semantic analysis (default: 0.6)"
    )
    
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> AegisConfig:
    """
    Build configuration from command-line arguments.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        AegisConfig instance
    """
    # Detection configuration with optimizations
    detection_config = DetectionConfig(
        model_path=args.model,
        confidence_threshold=args.confidence,
        frame_skip=getattr(args, 'frame_skip', 1),
        half_precision=not getattr(args, 'no_fp16', False)
    )

    
    # Tracking configuration
    tracking_config = TrackingConfig(
        max_age=args.max_age
    )
    
    # Video configuration
    video_config = VideoConfig(
        display_window=not args.no_display
    )
    
    # Analysis configuration (Phase 2)
    analysis_config = AnalysisConfig(
        enabled=args.enable_analysis or args.enable_risk,  # Risk requires analysis
        loitering_time_threshold=args.loitering_threshold
    )
    
    # Risk configuration (Phase 3)
    risk_config = RiskConfig(
        enabled=args.enable_risk or args.enable_alerts  # Alerts require risk
    )
    
    # Alert configuration (Phase 4)
    alert_config = AlertConfig(
        enabled=args.enable_alerts
    )
    
    # API configuration (Phase 4)
    api_config = APIConfig(
        enabled=args.enable_api,
        port=args.api_port
    )
    
    # Semantic configuration (Phase 5)
    semantic_config = SemanticConfig(
        enabled=getattr(args, 'enable_semantic', False),
        risk_threshold_trigger=getattr(args, 'semantic_risk_threshold', 0.6)
    )
    
    # Device selection
    device_map = {
        "auto": DeviceType.AUTO,
        "cpu": DeviceType.CPU,
        "cuda": DeviceType.CUDA,
        "mps": DeviceType.MPS
    }
    device = device_map.get(args.device, DeviceType.AUTO)
    
    return AegisConfig(
        detection=detection_config,
        tracking=tracking_config,
        video=video_config,
        analysis=analysis_config,
        risk=risk_config,
        alerts=alert_config,
        api=api_config,
        semantic=semantic_config,
        device=device
    )


def get_video_source(input_arg: str) -> tuple:
    """
    Parse input argument to determine video source.
    
    Args:
        input_arg: Input argument string
        
    Returns:
        Tuple of (source, is_camera)
    """
    # Check if input is a camera index
    try:
        camera_index = int(input_arg)
        return camera_index, True
    except ValueError:
        return input_arg, False


def create_analysis_components(config: AegisConfig):
    """
    Create Phase 2 analysis components.
    
    Args:
        config: System configuration
        
    Returns:
        Tuple of (history_manager, motion_analyzer, behavior_analyzer, crowd_analyzer)
    """
    if not ANALYSIS_AVAILABLE:
        raise RuntimeError("Analysis module not available")
    
    # Create configurations from AegisConfig
    motion_config = MotionAnalyzerConfig(
        stationary_threshold=config.analysis.stationary_speed_threshold,
        min_history_for_analysis=config.analysis.min_history_for_analysis,
        running_threshold=config.analysis.running_speed_threshold
    )
    
    behavior_config = BehaviorAnalyzerConfig(
        loitering_time_threshold=config.analysis.loitering_time_threshold,
        speed_change_threshold=config.analysis.speed_change_threshold,
        direction_reversal_threshold=config.analysis.direction_reversal_threshold,
        erratic_variance_threshold=config.analysis.erratic_variance_threshold,
        running_speed_threshold=config.analysis.running_speed_threshold,
        min_history_for_behavior=config.analysis.min_history_for_analysis,
        assumed_fps=config.analysis.assumed_fps
    )
    
    crowd_config = CrowdAnalyzerConfig(
        grid_cell_size=config.analysis.grid_cell_size,
        crowd_density_threshold=config.analysis.crowd_density_threshold
    )
    
    # Create components
    history_manager = TrackHistoryManager(
        window_size=config.analysis.history_window_size,
        stale_threshold=90
    )
    
    motion_analyzer = MotionAnalyzer(config=motion_config)
    behavior_analyzer = BehaviorAnalyzer(
        config=behavior_config,
        motion_analyzer=motion_analyzer
    )
    crowd_analyzer = CrowdAnalyzer(config=crowd_config)
    
    return history_manager, motion_analyzer, behavior_analyzer, crowd_analyzer


def run_perception_pipeline(
    config: AegisConfig,
    input_source: str,
    output_path: str,
    show_fps: bool = True,
    semantic_prompt: Optional[str] = None
) -> dict:
    """
    Execute the main perception and analysis pipeline.
    
    Args:
        config: System configuration
        input_source: Video file path or camera index
        output_path: Output video file path
        show_fps: Whether to show FPS overlay
        
    Returns:
        Dictionary with processing statistics
    """
    # Initialize components
    logger.info("Initializing perception pipeline...")
    
    source_input, is_camera = get_video_source(input_source)
    enable_analysis = config.analysis.enabled and ANALYSIS_AVAILABLE
    
    # Create Phase 1 components
    detector = YOLODetector(config=config)
    tracker = DeepSORTTracker(config=config)
    renderer = Renderer(config=config)
    
    # Create Phase 2 components if enabled
    if enable_analysis:
        logger.info("Phase 2 Analysis enabled")
        history_manager, motion_analyzer, behavior_analyzer, crowd_analyzer = \
            create_analysis_components(config)
    else:
        history_manager = None
        motion_analyzer = None
        behavior_analyzer = None
        crowd_analyzer = None
    
    # Create Phase 3 components if enabled
    enable_risk = config.risk.enabled and RISK_AVAILABLE and enable_analysis
    risk_engine = None
    
    if enable_risk:
        logger.info("Phase 3 Risk scoring enabled")
        # Create risk engine with configured weights
        risk_weights = RiskWeights(
            loitering=config.risk.weight_loitering,
            speed_anomaly=config.risk.weight_speed_anomaly,
            direction_change=config.risk.weight_direction_change,
            crowd_density=config.risk.weight_crowd_density,
            zone_context=config.risk.weight_zone,
            erratic_motion=config.risk.weight_erratic
        )
        risk_thresholds = RiskThresholds(
            medium=config.risk.low_threshold,
            high=config.risk.medium_threshold,
            critical=config.risk.high_threshold
        )
        temporal_config = TemporalConfig(
            escalation_rate=config.risk.escalation_rate,
            decay_rate=config.risk.decay_rate
        )
        risk_config_engine = RiskEngineConfig(
            weights=risk_weights,
            thresholds=risk_thresholds,
            temporal=temporal_config,
            use_zones=config.risk.use_zones,
            use_temporal=config.risk.use_temporal
        )
        risk_engine = RiskEngine(config=risk_config_engine)
    
    # Create Phase 4 components if enabled
    enable_alerts = config.alerts.enabled and RESPONSE_AVAILABLE and enable_risk
    enable_api = config.api.enabled and RESPONSE_AVAILABLE
    alert_manager = None
    api_server = None
    
    if enable_alerts:
        logger.info("Phase 4 Alert generation enabled")
        alert_manager_config = AlertManagerConfig(
            enabled=True,
            min_level=AlertLevel[config.alerts.min_level],
            cooldown_seconds=config.alerts.cooldown_seconds,
            log_to_file=config.alerts.log_to_file,
            log_path=config.alerts.log_path
        )
        alert_manager = AlertManager(config=alert_manager_config)
    
    if enable_api:
        logger.info("Phase 4 API server enabled")
        api_server_config = APIServerConfig(
            enabled=True,
            host=config.api.host,
            port=config.api.port,
            serve_dashboard=config.api.serve_dashboard
        )
        api_server = APIServer(config=api_server_config)
        api_server.start()
        api_server.state.start()
    
    # Create Phase 5 components if enabled
    enable_semantic = config.semantic.enabled and SEMANTIC_AVAILABLE and enable_risk
    dino_engine = None
    prompt_manager = None
    semantic_trigger = None
    semantic_executor = None
    semantic_fusion = None
    active_semantic_query = None  # Track current user query
    
    if enable_semantic:
        logger.info("Phase 5 Semantic layer enabled")
        dino_engine = DinoEngine(config.semantic)
        prompt_manager = PromptManager(cache_ttl=config.semantic.cache_ttl_seconds)
        semantic_trigger = SemanticTrigger(config.semantic)
        semantic_executor = SemanticExecutor(dino_engine, max_workers=config.semantic.max_concurrent_requests)
        semantic_fusion = SemanticFusion()
        
        # Set initial prompt if provided via CLI
        if semantic_prompt:
            active_semantic_query = semantic_prompt
            prompt_manager.add_prompt(active_semantic_query, priority=100)
            logger.info(f"Initial semantic query: '{active_semantic_query}'")
    
    # Track history for motion trails (basic feature from Phase 1)
    track_history = defaultdict(list)
    
    # Processing statistics
    stats = {
        "frames_processed": 0,
        "total_detections": 0,
        "total_tracks": 0,
        "total_anomalies": 0,
        "concerning_tracks": 0,
        "max_risk_score": 0.0,
        "total_alerts": 0,
        "semantic_triggers": 0,
        "semantic_matches": 0,
        "processing_time": 0.0,
        "average_fps": 0.0,
        "analysis_enabled": enable_analysis,
        "risk_enabled": config.risk.enabled and RISK_AVAILABLE,
        "alerts_enabled": enable_alerts,
        "api_enabled": enable_api,
        "semantic_enabled": enable_semantic
    }
    
    # FPS calculation
    fps_window = []
    fps_window_size = 30
    
    logger.info(f"Opening video source: {source_input}")
    
    with VideoSource(source_input, config=config) as source:
        # Initialize output writer
        writer = VideoWriter(
            output_path,
            fps=source.fps,
            resolution=source.resolution,
            config=config
        )
        writer.open()
        
        # Warmup detector
        detector.warmup(image_size=(source.height, source.width))
        
        logger.info("Starting perception processing...")
        start_time = time.time()
        frame_id = 0
        
        try:
            # Get frame skip setting (default: process every frame)
            frame_skip = getattr(config.detection, 'frame_skip', 1)
            last_detections = []
            last_tracks = []
            
            for frame in source:
                frame_start = time.time()
                timestamp = frame_id / source.fps if source.fps > 0 else 0.0
                
                # ═══════════════════════════════════════════════════════════
                # PHASE 1: PERCEPTION (with frame skipping optimization)
                # ═══════════════════════════════════════════════════════════
                
                # Only run detection on every Nth frame for performance
                if frame_id % frame_skip == 0:
                    # Step 1: Detection
                    detections = detector.detect(frame)
                    last_detections = detections
                    stats["total_detections"] += len(detections)
                    
                    # Step 2: Tracking
                    tracks = tracker.update(detections, frame)
                    last_tracks = tracks
                else:
                    # Reuse previous detections for skipped frames
                    detections = last_detections
                    tracks = last_tracks
                
                stats["total_tracks"] = max(
                    stats["total_tracks"],
                    tracker.get_total_tracks_created()
                )

                
                # ═══════════════════════════════════════════════════════════
                # PHASE 2: ANALYSIS (if enabled)
                # ═══════════════════════════════════════════════════════════
                
                frame_analysis = None
                
                if enable_analysis and history_manager:
                    # Update track history
                    history_manager.update(tracks, frame_id, timestamp)
                    
                    # Compute motion metrics
                    motion_states = motion_analyzer.analyze_all(history_manager)
                    
                    # Detect behaviors
                    behaviors = behavior_analyzer.analyze_all(
                        history_manager, motion_states
                    )
                    
                    # Compute crowd metrics
                    crowd_metrics = crowd_analyzer.analyze(tracks, frame.shape)
                    
                    # Build track analyses
                    track_analyses = []
                    anomaly_tracks = []
                    
                    for track in tracks:
                        tid = track.track_id
                        history = history_manager.get_history(tid)
                        
                        if history:
                            motion = motion_states.get(tid, MotionState())
                            behavior = behaviors.get(tid, BehaviorFlags())
                            
                            ta = TrackAnalysis(
                                track_id=tid,
                                class_id=track.class_id,
                                class_name=track.class_name,
                                motion=motion,
                                behavior=behavior,
                                history_length=history.history_length,
                                time_tracked=history.duration,
                                current_position=(
                                    (track.bbox[0] + track.bbox[2]) / 2,
                                    (track.bbox[1] + track.bbox[3]) / 2
                                ),
                                current_bbox=track.bbox
                            )
                            track_analyses.append(ta)
                            
                            if behavior.has_anomaly:
                                anomaly_tracks.append(tid)
                    
                    # Create frame analysis
                    frame_analysis = FrameAnalysis(
                        frame_id=frame_id,
                        timestamp=timestamp,
                        track_analyses=track_analyses,
                        crowd_metrics=crowd_metrics,
                        anomaly_count=len(anomaly_tracks),
                        anomaly_tracks=anomaly_tracks
                    )
                    
                    stats["total_anomalies"] += len(anomaly_tracks)
                
                # ═══════════════════════════════════════════════════════════
                # PHASE 3: RISK SCORING (if enabled)
                # ═══════════════════════════════════════════════════════════
                
                frame_risk = None
                
                if enable_risk and risk_engine and frame_analysis:
                    frame_risk = risk_engine.compute_frame_risks(
                        track_analyses=frame_analysis.track_analyses,
                        crowd_metrics=frame_analysis.crowd_metrics,
                        frame_id=frame_id,
                        timestamp=timestamp
                    )
                    
                    stats["concerning_tracks"] += frame_risk.concerning_tracks
                    stats["max_risk_score"] = max(
                        stats["max_risk_score"],
                        frame_risk.max_risk_score
                    )
                
                # ═══════════════════════════════════════════════════════════
                # PHASE 4: ALERTS & API (if enabled)
                # ═══════════════════════════════════════════════════════════
                
                if enable_alerts and alert_manager and frame_risk:
                    for risk in frame_risk.track_risks:
                        if risk.is_concerning:
                            alert = alert_manager.process_risk(
                                track_id=risk.track_id,
                                risk_level=risk.level.value,
                                risk_score=risk.score,
                                message=risk.explanation.summary,
                                zone=risk.explanation.factors[0].description if risk.explanation.factors else "",
                                factors=[f.display_name for f in risk.explanation.factors]
                            )
                            if alert:
                                stats["total_alerts"] += 1
                                # Add to API event queue if enabled
                                if enable_api and api_server:
                                    api_server.state.add_event(alert.to_dict())
                
                if enable_api and api_server and frame_risk:
                    # Update API state
                    api_server.state.update_status(
                        frames=stats["frames_processed"],
                        fps=avg_fps if 'avg_fps' in dir() else 0,
                        active_tracks=len(tracks),
                        detections=stats["total_detections"],
                        anomalies=stats["total_anomalies"],
                        max_risk_level=frame_risk.max_risk_level.value if frame_risk else "LOW",
                        max_risk_score=frame_risk.max_risk_score if frame_risk else 0.0
                    )
                    
                    # Update tracks in API state
                    for risk in frame_risk.track_risks:
                        api_server.state.update_track(
                            track_id=risk.track_id,
                            class_name=risk.explanation.summary.split()[0] if risk.explanation.summary else "Unknown",
                            risk_level=risk.level.value,
                            risk_score=risk.score,
                            behaviors=[f.display_name for f in risk.explanation.factors[:3]]
                        )
                    
                    # Update statistics
                    risk_dist = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
                    for risk in frame_risk.track_risks:
                        risk_dist[risk.level.value] += 1
                    
                    if frame_analysis:
                        api_server.state.update_statistics(
                            person_count=frame_analysis.crowd_metrics.person_count,
                            vehicle_count=frame_analysis.crowd_metrics.vehicle_count,
                            crowd_detected=frame_analysis.crowd_metrics.crowd_detected,
                            max_density=frame_analysis.crowd_metrics.max_density,
                            risk_distribution=risk_dist
                        )
                
                # ═══════════════════════════════════════════════════════════
                # PHASE 5: SEMANTIC ANALYSIS (if enabled)
                # ═══════════════════════════════════════════════════════════
                
                unified_intel = None
                
                if enable_semantic and semantic_trigger and frame_analysis and frame_risk:
                    # Check for trigger events
                    trigger_events = semantic_trigger.check_triggers(
                        tracks=frame_analysis.track_analyses,
                        risk_scores=frame_risk,
                        user_query=active_semantic_query,
                        frame=frame
                    )
                    
                    # Submit triggered tracks for async DINO inference
                    for event in trigger_events:
                        # Check cache first
                        image_hash = prompt_manager.compute_image_hash(event.cropped_frame)
                        cached = prompt_manager.get_cached_result(event.prompt, image_hash)
                        
                        if cached is not None:
                            # Use cached result
                            semantic_executor._results[event.track_id] = cached
                        else:
                            # Submit for async inference
                            semantic_executor.submit(
                                track_id=event.track_id,
                                image=event.cropped_frame,
                                prompt=event.prompt
                            )
                        
                        stats["semantic_triggers"] += 1
                    
                    # Collect completed semantic results (non-blocking)
                    semantic_results = semantic_executor.get_results()
                    
                    # Cache new results
                    for track_id, detections in semantic_results.items():
                        if detections:
                            stats["semantic_matches"] += len(detections)
                    
                    # Fuse all perception layers
                    unified_intel = semantic_fusion.fuse(
                        tracks=tracks,
                        track_analyses=frame_analysis.track_analyses,
                        semantic_results=semantic_results,
                        risk_summary=frame_risk,
                        timestamp=timestamp
                    )
                    
                    # Log high-value semantic matches
                    for obj in unified_intel:
                        if obj.has_semantic_match() and obj.semantic_confidence > 0.5:
                            logger.info(
                                f"[SEMANTIC] Track {obj.track_id}: "
                                f"'{obj.semantic_label}' ({obj.semantic_confidence:.2f}) "
                                f"-> Risk: {obj.risk_score:.2f}"
                            )
                
                # ═══════════════════════════════════════════════════════════
                # VISUALIZATION
                # ═══════════════════════════════════════════════════════════
                
                # Update track history for trails (Phase 1 feature)
                for track in tracks:
                    center_x = (track.bbox[0] + track.bbox[2]) // 2
                    center_y = (track.bbox[1] + track.bbox[3]) // 2
                    track_history[track.track_id].append((center_x, center_y))
                    
                    # Limit trail length
                    if len(track_history[track.track_id]) > 50:
                        track_history[track.track_id] = \
                            track_history[track.track_id][-50:]
                
                # Draw tracks
                annotated_frame = renderer.draw_tracks(frame, tracks)
                
                # Add risk overlay if available
                if frame_risk and frame_risk.has_concerns:
                    annotated_frame = draw_risk_overlay(
                        annotated_frame, frame_risk
                    )
                # Add analysis annotations if available (fallback if no risk)
                elif frame_analysis and frame_analysis.anomaly_count > 0:
                    annotated_frame = draw_analysis_overlay(
                        annotated_frame, frame_analysis
                    )
                
                # Calculate FPS
                frame_time = time.time() - frame_start
                current_fps = 1.0 / frame_time if frame_time > 0 else 0
                fps_window.append(current_fps)
                if len(fps_window) > fps_window_size:
                    fps_window.pop(0)
                avg_fps = sum(fps_window) / len(fps_window)
                
                # Add info overlay
                if show_fps:
                    info = {
                        "FPS": f"{avg_fps:.1f}",
                        "Tracks": len(tracks),
                        "Detections": len(detections)
                    }
                    if not is_camera:
                        progress = source.current_frame / source.frame_count * 100
                        info["Progress"] = f"{progress:.1f}%"
                    
                    if enable_analysis and frame_analysis:
                        info["Anomalies"] = frame_analysis.anomaly_count
                        if frame_analysis.crowd_metrics.crowd_detected:
                            info["Crowd"] = "DETECTED"
                    
                    if enable_risk and frame_risk:
                        if frame_risk.max_risk_score > 0.1:
                            info["Risk"] = f"{frame_risk.max_risk_level.value}"
                        if frame_risk.concerning_tracks > 0:
                            info["Concerns"] = frame_risk.concerning_tracks
                    
                    annotated_frame = renderer.draw_info_overlay(
                        annotated_frame, info
                    )
                
                # Write output
                writer.write(annotated_frame)
                
                # Display (if enabled)
                if config.video.display_window:
                    cv2.imshow(config.video.window_name, annotated_frame)
                    
                    # Check for quit key
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q') or key == 27:  # 'q' or ESC
                        logger.info("User requested quit")
                        break
                
                stats["frames_processed"] += 1
                frame_id += 1
                
                # Progress logging (every 100 frames)
                if stats["frames_processed"] % 100 == 0:
                    log_msg = (
                        f"Processed {stats['frames_processed']} frames, "
                        f"FPS: {avg_fps:.1f}, "
                        f"Active tracks: {len(tracks)}"
                    )
                    if enable_analysis:
                        log_msg += f", Anomalies: {stats['total_anomalies']}"
                    if enable_risk:
                        log_msg += f", Concerns: {stats['concerning_tracks']}"
                    logger.info(log_msg)
        
        except KeyboardInterrupt:
            logger.info("Processing interrupted by user")
        
        finally:
            # Cleanup
            writer.release()
            cv2.destroyAllWindows()
        
        # Calculate final statistics
        stats["processing_time"] = time.time() - start_time
        stats["average_fps"] = (
            stats["frames_processed"] / stats["processing_time"]
            if stats["processing_time"] > 0 else 0
        )
    
    return stats


def draw_analysis_overlay(
    frame,
    analysis: 'FrameAnalysis'
):
    """
    Draw analysis-specific annotations on frame.
    
    Args:
        frame: Video frame to annotate
        analysis: Frame analysis results
        
    Returns:
        Annotated frame
    """
    # Highlight anomalous tracks
    for ta in analysis.track_analyses:
        if ta.behavior.has_anomaly:
            x1, y1, x2, y2 = ta.current_bbox
            
            # Draw red warning border
            cv2.rectangle(
                frame,
                (x1 - 3, y1 - 3),
                (x2 + 3, y2 + 3),
                (0, 0, 255),  # Red
                2
            )
            
            # Add behavior label
            behaviors = ta.behavior.active_behaviors
            if behaviors:
                # Get primary behavior (excluding NORMAL)
                primary = next(
                    (b for b in behaviors if b.name != "NORMAL"),
                    behaviors[0]
                )
                label = primary.name.replace("_", " ")
                
                cv2.putText(
                    frame,
                    label,
                    (x1, y2 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA
                )
    
    return frame


def draw_risk_overlay(
    frame,
    risk_summary: 'FrameRiskSummary'
):
    """
    Draw risk-specific annotations on frame.
    
    Args:
        frame: Video frame to annotate
        risk_summary: Frame risk summary
        
    Returns:
        Annotated frame
    """
    for risk in risk_summary.track_risks:
        if risk.is_concerning:
            # Get risk color based on level
            color = risk.level.color_bgr
            
            # Add risk label at frame level if critical
            if risk.level.value == "CRITICAL":
                summary_text = risk.explanation.summary if risk.explanation else "Critical risk detected"
                label = f"CRITICAL: {summary_text[:50]}"
                cv2.putText(
                    frame,
                    label,
                    (10, frame.shape[0] - 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA
                )
                break  # Only show one critical message
    
    return frame


def print_summary(stats: dict, output_path: str) -> None:
    """
    Print processing summary to console.
    
    Args:
        stats: Processing statistics dictionary
        output_path: Path to output video
    """
    print("\n" + "=" * 60)
    print("AegisAI - Processing Complete")
    print("=" * 60)
    print(f"  Frames Processed:    {stats['frames_processed']}")
    print(f"  Total Detections:    {stats['total_detections']}")
    print(f"  Unique Tracks:       {stats['total_tracks']}")
    
    if stats.get("analysis_enabled"):
        print(f"  Total Anomalies:     {stats['total_anomalies']}")
    
    if stats.get("risk_enabled"):
        print(f"  Concerning Tracks:   {stats['concerning_tracks']}")
        print(f"  Max Risk Score:      {stats['max_risk_score']:.2f}")
    
    if stats.get("alerts_enabled"):
        print(f"  Total Alerts:        {stats['total_alerts']}")
    
    print(f"  Processing Time:     {stats['processing_time']:.2f} seconds")
    print(f"  Average FPS:         {stats['average_fps']:.2f}")
    print(f"  Output File:         {output_path}")
    
    # Phase status
    phases = []
    if stats.get("analysis_enabled"):
        phases.append("Phase 2: Analysis")
    if stats.get("risk_enabled"):
        phases.append("Phase 3: Risk")
    if stats.get("alerts_enabled"):
        phases.append("Phase 4: Alerts")
    if stats.get("api_enabled"):
        phases.append("Phase 4: API")
    
    if phases:
        print(f"  Active Phases:       {', '.join(phases)}")
    
    print("=" * 60 + "\n")


def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    print("\n")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║                                                          ║")
    print("║    █████╗ ███████╗ ██████╗ ██╗███████╗     █████╗ ██╗   ║")
    print("║   ██╔══██╗██╔════╝██╔════╝ ██║██╔════╝    ██╔══██╗██║   ║")
    print("║   ███████║█████╗  ██║  ███╗██║███████╗    ███████║██║   ║")
    print("║   ██╔══██║██╔══╝  ██║   ██║██║╚════██║    ██╔══██║██║   ║")
    print("║   ██║  ██║███████╗╚██████╔╝██║███████║    ██║  ██║██║   ║")
    print("║   ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝╚══════╝    ╚═╝  ╚═╝╚═╝   ║")
    print("║                                                          ║")
    print("║         Smart City Risk Intelligence System              ║")
    print("║        Phase 1: Perception | Phase 2: Analysis           ║")
    print("║                                                          ║")
    print("╚══════════════════════════════════════════════════════════╝\n")
    
    try:
        # Parse arguments
        args = parse_args()
        
        # Validate input
        source_input, is_camera = get_video_source(args.input)
        if not is_camera and not Path(source_input).exists():
            logger.error(f"Input file not found: {args.input}")
            return 1
        
        # Check analysis availability
        if args.enable_analysis and not ANALYSIS_AVAILABLE:
            logger.warning(
                "Analysis module not available. "
                "Running without Phase 2 analysis."
            )
        
        # Build configuration
        config = build_config(args)
        
        # Log configuration
        logger.info(f"Input: {args.input}")
        logger.info(f"Output: {args.output}")
        logger.info(f"Model: {args.model}")
        logger.info(f"Confidence: {args.confidence}")
        logger.info(f"Device: {args.device}")
        logger.info(f"Analysis: {'ENABLED' if config.analysis.enabled else 'DISABLED'}")
        
        # Run pipeline
        stats = run_perception_pipeline(
            config=config,
            input_source=args.input,
            output_path=args.output,
            show_fps=args.show_fps,
            semantic_prompt=getattr(args, 'semantic_prompt', None)
        )
        
        # Print summary
        print_summary(stats, args.output)
        
        return 0
    
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
        return 0
    
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
