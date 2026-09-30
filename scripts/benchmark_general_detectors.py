"""Controlled local benchmark for Aegis general-detection checkpoints.

This is an explicit operator tool, not part of application startup. It uses
only local checkpoint paths and never provisions/downloads model weights.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import cv2
import psutil
import torch
from ultralytics import YOLO


DEFAULT_CLASSES = [0, 2, 3, 5, 7, 14, 15, 16, 34, 43, 76]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def read_frames(source: Path, limit: int) -> list:
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to read benchmark source: {source}")
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    stride = max(1, total // limit) if total else 1
    frames = []
    index = 0
    while len(frames) < limit:
        ok, frame = capture.read()
        if not ok:
            break
        if index % stride == 0:
            frames.append(frame)
        index += 1
    capture.release()
    if not frames:
        raise RuntimeError(f"No frames decoded from benchmark source: {source}")
    return frames


def benchmark(model_path: Path, frames: list, *, nms_free: bool) -> dict:
    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    model = YOLO(str(model_path))
    kwargs = {
        "conf": 0.5,
        "iou": 0.45,
        "classes": DEFAULT_CLASSES,
        "imgsz": 640,
        "verbose": False,
    }
    if nms_free:
        kwargs["nms"] = False
    # First inference is recorded separately and excluded from warm latency.
    started = time.perf_counter()
    first = model.predict(frames[0], **kwargs)[0]
    first_ms = (time.perf_counter() - started) * 1000
    model.predict(frames[0], **kwargs)
    timings, people, detections = [], [], []
    for frame in frames:
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        started = time.perf_counter()
        result = model.predict(frame, **kwargs)[0]
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        timings.append((time.perf_counter() - started) * 1000)
        class_ids = result.boxes.cls.tolist() if result.boxes is not None else []
        people.append(sum(int(item) == 0 for item in class_ids))
        detections.append(len(class_ids))
    mean = sum(timings) / len(timings)
    changes = [abs(right - left) for left, right in zip(people, people[1:])]
    return {
        "model": model_path.name,
        "checkpoint": str(model_path.resolve()),
        "task": model.task,
        "class_count": len(model.names),
        "device": str(model.device),
        "input_size": 640,
        "nms_free": nms_free,
        "first_inference_ms": round(first_ms, 2),
        "warm_avg_ms": round(mean, 2),
        "p50_ms": round(percentile(timings, 0.50), 2),
        "p95_ms": round(percentile(timings, 0.95), 2),
        "fps": round(1000 / mean, 2),
        "frames": len(frames),
        "person_detections": sum(people),
        "frames_with_person": sum(count > 0 for count in people),
        "average_people_per_frame": round(sum(people) / len(people), 2),
        "person_count_change_mae": round(sum(changes) / len(changes), 3) if changes else 0,
        "average_detections_per_frame": round(sum(detections) / len(detections), 2),
        "rss_mb": round(psutil.Process().memory_info().rss / 1024**2, 1),
        "vram_mb": round(torch.cuda.max_memory_allocated() / 1024**2, 1) if torch.cuda.is_available() else 0,
        "first_frame_shape": list(first.orig_shape),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--models", type=Path, nargs="+", required=True)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--nms-free", action="store_true")
    args = parser.parse_args()
    frames = read_frames(args.source, args.frames)
    report = {
        "source": str(args.source.resolve()),
        "frame_count": len(frames),
        "nms_free": args.nms_free,
        "results": [benchmark(path, frames, nms_free=args.nms_free) for path in args.models],
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
