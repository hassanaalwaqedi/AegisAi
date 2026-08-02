"""
AegisAI - Pipeline Overlay Rendering

Extracted from main.py — draws analysis and risk overlays onto video frames.
These are the CLI-mode overlays used by the standalone perception pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import cv2

if TYPE_CHECKING:
    from aegis.analysis import FrameAnalysis
    from aegis.risk import FrameRiskSummary


def draw_analysis_overlay(frame, analysis: "FrameAnalysis"):
    """
    Draw analysis-specific annotations on frame.

    Highlights anomalous tracks with red borders and behavior labels.

    Args:
        frame: Video frame to annotate (modified in place)
        analysis: Frame analysis results

    Returns:
        Annotated frame
    """
    for ta in analysis.track_analyses:
        if ta.behavior.has_anomaly:
            x1, y1, x2, y2 = ta.current_bbox

            # Draw red warning border
            cv2.rectangle(
                frame,
                (x1 - 3, y1 - 3),
                (x2 + 3, y2 + 3),
                (0, 0, 255),  # Red
                2,
            )

            # Add behavior label
            behaviors = ta.behavior.active_behaviors
            if behaviors:
                primary = next(
                    (b for b in behaviors if b.name != "NORMAL"),
                    behaviors[0],
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
                    cv2.LINE_AA,
                )

    return frame


def draw_risk_overlay(frame, risk_summary: "FrameRiskSummary"):
    """
    Draw risk-specific annotations on frame.

    Shows critical risk warnings at the bottom of the frame.

    Args:
        frame: Video frame to annotate (modified in place)
        risk_summary: Frame risk summary

    Returns:
        Annotated frame
    """
    for risk in risk_summary.track_risks:
        if risk.is_concerning:
            # Add risk label at frame level if critical
            if risk.level.value == "CRITICAL":
                summary_text = (
                    risk.explanation.summary
                    if risk.explanation
                    else "Critical risk detected"
                )
                label = f"CRITICAL: {summary_text[:50]}"
                cv2.putText(
                    frame,
                    label,
                    (10, frame.shape[0] - 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )
                break  # Only show one critical message

    return frame
