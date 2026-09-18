"""Bounded scene references shared by text projections and a live voice session."""
from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from aegis.ai.schemas import OperatorCommandRequest
from aegis.intelligence.operator import execute_operator_command


class OperatorSceneContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    panel: Literal["camera", "events", "evidence", "tracks", "system", "analytics", "answer", "error"] = "answer"
    query: str = Field(default="", max_length=500)
    selected_id: str | None = Field(default=None, max_length=128)
    ordered_ids: list[str] = Field(default_factory=list, max_length=50)


def execute_scene_command(message: str, context: OperatorSceneContext):
    """Resolve UI references, then fetch evidence from the real command executor."""
    selected = context.selected_id
    ordinal = re.search(r"\b(first|second|third|fourth|fifth|\d+(?:st|nd|rd|th)?)\s+(?:one|result|event|item)\b", message, re.I)
    if ordinal:
        words = ["first", "second", "third", "fourth", "fifth"]
        token = ordinal.group(1).lower()
        index = words.index(token) if token in words else int(re.match(r"\d+", token).group()) - 1
        selected = context.ordered_ids[index] if 0 <= index < len(context.ordered_ids) else None
        # Fetch the selected record again; the browser supplies only identifiers.
        if context.panel in {"events", "evidence"}:
            message = "Show related evidence"
        elif context.panel == "camera":
            message = f"Open camera {selected or 'unavailable'}"
        elif context.panel == "tracks":
            message = f"Show track {selected or 'unavailable'}"
    request = OperatorCommandRequest(
        message=message,
        previous_query=context.query or None,
        previous_evidence_id=selected if context.panel in {"events", "evidence"} else None,
        selected_camera_id=selected if context.panel == "camera" else None,
        selected_track_id=selected if context.panel == "tracks" else None,
    )
    return execute_operator_command(request)
