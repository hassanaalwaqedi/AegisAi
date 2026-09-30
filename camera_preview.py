"""Open the default local camera in a native OpenCV preview window.

Press Q or Escape to close the preview.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

import cv2

from aegis.detection import YOLODetector, YOLOEThreatDetector
from config import DetectionConfig


WEAPON_CLASSES = {"knife", "scissors", "baseball bat"}
FIREARM_CLASSES = {"handgun", "pistol", "revolver", "rifle", "shotgun"}


def assess_risk(detections: Iterable, motion_score: float, frame_shape: tuple[int, ...]) -> tuple[str, int, list[str]]:
    """Return an explainable *operator-review* score, not a violence verdict."""
    items = list(detections)
    people = [item for item in items if item.is_person]
    weapons = [item for item in items if item.class_name.lower() in WEAPON_CLASSES]
    firearms = [item for item in items if item.class_name.lower() in FIREARM_CLASSES]
    reasons: list[str] = []
    score = 0

    if people:
        score += 5
        reasons.append(f"{len(people)} person(s) detected")
    if len(people) >= 4:
        score += 15
        reasons.append("crowd density")
    if weapons:
        score += min(70, 55 + 10 * len(weapons))
        reasons.append("weapon-like object detected")
    if firearms:
        # YOLOE is open-vocabulary: treat gun outputs as review candidates,
        # never as confirmation of a firearm or violent intent.
        score += min(55, 40 + 5 * len(firearms))
        reasons.append("firearm candidate — operator verification required")
    if weapons and people:
        score += 15
        reasons.append("person and weapon-like object in same frame")
    if firearms and people:
        score += 15
        reasons.append("person near firearm candidate")
    if motion_score >= 12:
        score += 10
        reasons.append("rapid scene motion")

    height, width = frame_shape[:2]
    frame_diagonal = (width * width + height * height) ** 0.5
    close_people = False
    for first_index, first in enumerate(people):
        fx1, fy1, fx2, fy2 = first.bbox
        first_center = ((fx1 + fx2) / 2, (fy1 + fy2) / 2)
        for second in people[first_index + 1 :]:
            sx1, sy1, sx2, sy2 = second.bbox
            second_center = ((sx1 + sx2) / 2, (sy1 + sy2) / 2)
            distance = ((first_center[0] - second_center[0]) ** 2 + (first_center[1] - second_center[1]) ** 2) ** 0.5
            if distance / frame_diagonal < 0.18:
                close_people = True
                break
    if close_people and motion_score >= 12:
        score += 25
        reasons.append("close people with rapid motion — review")

    score = min(score, 100)
    if weapons and people and motion_score >= 12:
        return "CRITICAL", max(score, 90), reasons
    if score >= 70:
        return "HIGH", score, reasons
    if score >= 30:
        return "MEDIUM", score, reasons
    return "LOW", score, reasons or ["no current risk signals"]


def draw_risk_panel(frame, level: str, score: int, reasons: list[str], motion_score: float) -> None:
    colors = {"LOW": (0, 190, 0), "MEDIUM": (0, 190, 255), "HIGH": (0, 100, 255), "CRITICAL": (0, 0, 255)}
    color = colors[level]
    panel_width = min(frame.shape[1] - 24, 500)
    panel_height = 145
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (10 + panel_width, 10 + panel_height), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)
    cv2.rectangle(frame, (10, 10), (10 + panel_width, 10 + panel_height), color, 2)
    cv2.putText(frame, f"RISK: {level}  {score}/100", (22, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.78, color, 2, cv2.LINE_AA)
    cv2.putText(frame, f"Motion signal: {motion_score:.1f}", (22, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (235, 235, 235), 1, cv2.LINE_AA)
    for index, reason in enumerate(reasons[:2]):
        cv2.putText(frame, reason, (22, 94 + index * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (235, 235, 235), 1, cv2.LINE_AA)
    cv2.putText(frame, "Heuristic only — not a violence determination", (22, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (190, 190, 190), 1, cv2.LINE_AA)


def main() -> int:
    camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not camera.isOpened():
        camera.release()
        camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        print("Could not open camera index 0.", file=sys.stderr)
        return 1

    local_model = Path(__file__).with_name("yolo11n.pt")
    threat_model = Path(__file__).with_name("models") / "yoloe-26n-seg.pt"
    threat_embeddings = Path(__file__).with_name("models") / "yoloe-26n-seg.threat-prompts.npz"
    detector_config = DetectionConfig(
        model_path=str(local_model),
        threat_model_path=str(threat_model),
        threat_prompt_embeddings_path=str(threat_embeddings),
        threat_detector_enabled=True,
        threat_frame_skip=3,
    )
    detector = YOLODetector(detection_config=detector_config)
    threat_detector = YOLOEThreatDetector(detection_config=detector_config)
    previous_gray = None
    frame_number = 0
    threat_detections = []
    print("Safety detection preview is open. Press Q or Escape to close it.")
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("Could not read a camera frame.", file=sys.stderr)
                return 1

            frame_number += 1
            object_detections = detector.detect(frame, confidence_threshold=0.35)
            if frame_number % detector_config.threat_frame_skip == 1:
                threat_detections = threat_detector.detect(frame, confidence_threshold=0.25)
            detections = [*object_detections, *threat_detections]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            motion_score = 0.0 if previous_gray is None else float(cv2.absdiff(gray, previous_gray).mean())
            previous_gray = gray
            for detection in detections:
                x1, y1, x2, y2 = detection.bbox
                is_firearm_candidate = detection.class_name.lower() in FIREARM_CLASSES
                color = (220, 0, 220) if is_firearm_candidate else (0, 220, 0) if detection.is_person else (0, 180, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label_prefix = "candidate " if is_firearm_candidate else ""
                label = f"{label_prefix}{detection.class_name} {detection.confidence:.0%}"
                cv2.putText(
                    frame,
                    label,
                    (x1, max(24, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    color,
                    2,
                    cv2.LINE_AA,
                )

            risk_level, risk_score, reasons = assess_risk(detections, motion_score, frame.shape)
            draw_risk_panel(frame, risk_level, risk_score, reasons, motion_score)
            cv2.putText(frame, f"Detections: {len(detections)}", (12, frame.shape[0] - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow("AegisAI Safety Camera Preview", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                return 0
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    raise SystemExit(main())
