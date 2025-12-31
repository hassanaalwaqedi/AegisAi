"""
AegisAI - API Routes: Data Export

CSV and JSON export endpoints for events and alerts.

Phase 4: Response & Productization Layer
"""

import csv
import io
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from aegis.api.state import get_state

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/events/csv")
async def export_events_csv(
    limit: int = Query(default=1000, le=10000),
    hours: Optional[int] = Query(default=24, description="Export events from last N hours")
):
    """
    Export risk events as CSV.
    
    Returns:
        CSV file download with event data
    """
    state = get_state()
    events = state.get_events(limit=limit)
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "timestamp",
        "event_id",
        "track_id",
        "risk_level",
        "risk_score",
        "message",
        "factors"
    ])
    
    # Data rows
    for event in events:
        writer.writerow([
            event.get("timestamp", ""),
            event.get("event_id", ""),
            event.get("track_id", ""),
            event.get("risk_level", ""),
            event.get("risk_score", ""),
            event.get("message", ""),
            "|".join(event.get("factors", []))
        ])
    
    output.seek(0)
    
    filename = f"aegis_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/alerts/csv")
async def export_alerts_csv(
    limit: int = Query(default=1000, le=10000),
    acknowledged: Optional[bool] = Query(default=None)
):
    """
    Export alerts as CSV.
    
    Returns:
        CSV file download with alert data
    """
    state = get_state()
    alerts = state.get_alerts(limit=limit)
    
    # Filter by acknowledged status if specified
    if acknowledged is not None:
        alerts = [a for a in alerts if a.get("acknowledged") == acknowledged]
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "timestamp",
        "alert_id",
        "track_id",
        "level",
        "risk_score",
        "message",
        "zone",
        "acknowledged"
    ])
    
    # Data rows
    for alert in alerts:
        writer.writerow([
            alert.get("timestamp", ""),
            alert.get("alert_id", ""),
            alert.get("track_id", ""),
            alert.get("level", ""),
            alert.get("risk_score", ""),
            alert.get("message", ""),
            alert.get("zone", ""),
            alert.get("acknowledged", False)
        ])
    
    output.seek(0)
    
    filename = f"aegis_alerts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/tracks/csv")
async def export_tracks_csv():
    """
    Export current tracks snapshot as CSV.
    
    Returns:
        CSV file download with track data
    """
    state = get_state()
    tracks = state.get_tracks()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "track_id",
        "class_name",
        "confidence",
        "risk_score",
        "risk_level",
        "bbox_x1",
        "bbox_y1",
        "bbox_x2",
        "bbox_y2",
        "behaviors"
    ])
    
    # Data rows
    for track in tracks:
        bbox = track.get("bbox", [0, 0, 0, 0])
        writer.writerow([
            track.get("track_id", ""),
            track.get("class_name", ""),
            track.get("confidence", ""),
            track.get("risk_score", ""),
            track.get("risk_level", ""),
            bbox[0] if len(bbox) > 0 else "",
            bbox[1] if len(bbox) > 1 else "",
            bbox[2] if len(bbox) > 2 else "",
            bbox[3] if len(bbox) > 3 else "",
            "|".join(track.get("behaviors", []))
        ])
    
    output.seek(0)
    
    filename = f"aegis_tracks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/summary")
async def export_summary():
    """
    Get export summary statistics.
    
    Returns:
        Counts of exportable items
    """
    state = get_state()
    
    events = state.get_events(limit=10000)
    alerts = state.get_alerts(limit=10000)
    tracks = state.get_tracks()
    
    return {
        "exportable": {
            "events": len(events),
            "alerts": len(alerts),
            "tracks": len(tracks)
        },
        "formats": ["csv"],
        "endpoints": {
            "events_csv": "/export/events/csv",
            "alerts_csv": "/export/alerts/csv",
            "tracks_csv": "/export/tracks/csv"
        }
    }
