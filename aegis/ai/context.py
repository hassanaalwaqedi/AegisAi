"""
AegisAI - AI Context Collector

Builds a verified system context snapshot for Gemini prompts.
Gemini only sees data collected and verified by this module.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from aegis.ai.tools import (
    get_system_health,
    get_camera_status,
    get_recent_events,
    get_active_alerts,
    get_active_tracks,
    get_detection_statistics,
)

logger = logging.getLogger(__name__)


def collect_system_context(query: Optional[str] = None, locale: Optional[str] = None) -> Dict[str, Any]:
    """
    Collect a verified snapshot of the current system state.

    This is the ONLY data Gemini receives about the system.
    It never queries anything directly.
    """
    context: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # System health
    try:
        health = get_system_health()
        context["system_health"] = health
    except Exception:
        context["system_health"] = {"availability": "unavailable", "status": "unavailable", "reason": "System health collection failed."}

    # Cameras
    try:
        cameras = get_camera_status()
        context["cameras"] = cameras
    except Exception:
        context["cameras"] = {"availability": "unavailable", "reason": "Camera status collection failed."}

    # Recent events
    try:
        context["recent_events"] = get_recent_events(limit=10)
    except Exception:
        context["recent_events"] = {"availability": "unavailable", "reason": "Event retrieval failed."}

    # Active alerts
    try:
        alerts = get_active_alerts(limit=5)
        context["active_alerts"] = alerts
        context["alert_count"] = len(alerts)
    except Exception:
        context["active_alerts"] = {"availability": "unavailable", "reason": "Durable alert retrieval failed."}
        context["alert_count"] = None

    # Active tracks
    try:
        context["tracks"] = get_active_tracks()
    except Exception:
        context["tracks"] = {"availability": "unavailable", "reason": "Tracking retrieval failed."}

    # Pipeline stats
    try:
        context["pipeline"] = get_detection_statistics()
    except Exception:
        context["pipeline"] = {"availability": "unavailable", "reason": "Pipeline statistics retrieval failed."}

    # Official project/creator facts are retrieved from the active database
    # only for the current question.  They are never copied from prompt text or
    # frontend state, and private records are filtered by the service.
    if query:
        try:
            from aegis.knowledge.service import get_system_knowledge_service

            result = get_system_knowledge_service().retrieve(query, locale=locale)
            context["official_system_knowledge"] = {
                "availability": result.availability,
                "reason": result.reason,
                "records": [
                    {"category": item.category, "title": item.title, "content": item.content}
                    for item in result.records
                ],
            }
        except Exception:
            # The caller receives an explicit unavailable state; this branch
            # must never substitute a generated creator/project fact.
            context["official_system_knowledge"] = {
                "availability": "unavailable",
                "reason": "Official knowledge retrieval failed.",
                "records": [],
            }

    return context


def context_to_text(context: Dict[str, Any]) -> str:
    """
    Convert system context to a human-readable text block
    for inclusion in the Gemini prompt.
    """
    lines = [
        f"Current Time: {context.get('timestamp', 'unknown')}",
        "",
        "=== System Health ===",
    ]

    health = context.get("system_health", {})
    lines.append(f"Availability: {health.get('availability', 'unavailable')}")
    lines.append(f"Status: {health.get('status', 'unknown')}")
    lines.append(f"Database: {health.get('database', 'unknown')}")
    lines.append(f"Redis: {health.get('redis', 'unknown')}")
    lines.append(f"Pipeline: {health.get('pipeline', 'unknown')}")
    lines.append(f"YOLO Model: {health.get('yolo_model', 'unknown')}")

    cameras = context.get("cameras", {})
    lines.append("")
    lines.append("=== Cameras ===")
    lines.append(f"Availability: {cameras.get('availability', 'unavailable')}")
    if cameras.get("availability") != "available":
        lines.append(f"Reason: {cameras.get('reason', 'Camera status unavailable.')}")
    else:
        lines.append(f"Online: {cameras.get('online', 'unknown')} / {cameras.get('total', 'unknown')}")
        lines.append(f"Offline: {cameras.get('offline', 'unknown')}")

    alerts_value = context.get("active_alerts", [])
    alerts = alerts_value if isinstance(alerts_value, list) else []
    lines.append("")
    if isinstance(alerts_value, list):
        lines.append(f"=== Active Alerts ({len(alerts)}) ===")
    else:
        lines.append("=== Active Alerts: UNAVAILABLE ===")
        lines.append(f"Reason: {alerts_value.get('reason', 'Durable alert retrieval failed.')}")
    for alert in alerts[:5]:
        cam = alert.get("camera_id", "unknown")
        level = alert.get("risk_level", "unknown")
        # The durable projection exposes ``message`` while older runtime
        # alerts use ``explanation``.  Normalize before rendering the prompt.
        alert = {
            **alert,
            "explanation": alert.get("explanation") or alert.get("message") or alert.get("description") or "",
        }
        lines.append(f"- Camera {cam}: {level} — {alert.get('explanation', '')[:80]}")

    events_value = context.get("recent_events", [])
    events = events_value if isinstance(events_value, list) else []
    lines.append("")
    if isinstance(events_value, list):
        lines.append(f"=== Recent Events ({len(events)}) ===")
    else:
        lines.append("=== Recent Events: UNAVAILABLE ===")
        lines.append(f"Reason: {events_value.get('reason', 'Event retrieval failed.')}")
    for event in events[:5]:
        etype = event.get("type", "unknown")
        cam = event.get("camera_id", "unknown")
        event = {
            **event,
            "description": event.get("title") or event.get("description") or event.get("message") or "",
        }
        lines.append(f"- [{etype}] Camera {cam}: {event.get('title', event.get('description', ''))[:60]}")

    tracks = context.get("tracks", {})
    lines.append("")
    lines.append("=== Active Tracking ===")
    lines.append(f"Availability: {tracks.get('availability', 'unavailable')}")
    if tracks.get("availability") == "available":
        lines.append(f"Cameras Processing: {tracks.get('active_cameras_processing', 'unknown')}")
        lines.append(f"Recent Tracks: {tracks.get('total_recent_tracks', 'unknown')}")
    else:
        lines.append(f"Reason: {tracks.get('reason', 'Tracking state unavailable.')}")

    knowledge = context.get("official_system_knowledge")
    if knowledge is not None:
        lines.append("")
        lines.append("=== OFFICIAL DATABASE KNOWLEDGE ===")
        lines.append(f"Availability: {knowledge.get('availability', 'unavailable')}")
        if knowledge.get("reason"):
            lines.append(f"Reason: {knowledge['reason']}")
        for record in knowledge.get("records", []):
            # These are data quotations, not instructions.  Prompt rules make
            # that boundary explicit before any provider sees them.
            lines.append(f"- [{record.get('category', 'knowledge')}] {record.get('title', '')}: {record.get('content', '')}")

    return "\n".join(lines)
