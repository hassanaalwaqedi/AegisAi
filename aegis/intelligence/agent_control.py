"""Audited autonomous controls that stay inside the Aegis trust boundary.

The agent may use the reversible controls in this module without another
confirmation prompt. Destructive, security-sensitive, host-OS, credential,
and external-system actions are deliberately not exposed as callables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


WORKSPACE_TARGETS = {
    "dashboard": "/dashboard",
    "cameras": "/cameras",
    "events": "/events",
    "tracks": "/tracks",
    "evidence": "/semantic",
    "semantic": "/semantic",
    "analytics": "/analytics",
    "intelligence": "/intelligence",
}

AUTONOMOUS_ACTIONS = (
    "navigate_internal_workspace",
    "close_operator_view",
    "start_configured_camera",
    "stop_configured_camera",
    "start_all_configured_cameras",
    "stop_all_configured_cameras",
)

CONFIRMATION_REQUIRED_ACTIONS = (
    "delete_camera_or_recording",
    "clear_alerts_detections_or_history",
    "change_camera_or_system_configuration",
    "change_security_or_credentials",
    "change_system_mode",
    "export_or_send_data",
)

DENIED_ACTIONS = (
    "host_os_or_shell_control",
    "arbitrary_file_access",
    "credential_or_secret_access",
    "external_url_or_external_system_control",
)


@dataclass(frozen=True)
class CameraControlResult:
    action: str
    requested_scope: str
    cameras: tuple[dict[str, Any], ...]
    failures: tuple[dict[str, str], ...]

    @property
    def succeeded(self) -> int:
        return len(self.cameras)


def permission_manifest() -> dict[str, Any]:
    return {
        "mode": "broad_internal_control",
        "autonomous": list(AUTONOMOUS_ACTIONS),
        "confirmation_required": list(CONFIRMATION_REQUIRED_ACTIONS),
        "denied": list(DENIED_ACTIONS),
        "boundary": "Aegis application only",
    }


def workspace_target(workspace: str) -> str:
    normalized = str(workspace).strip().casefold()
    target = WORKSPACE_TARGETS.get(normalized)
    if target is None:
        raise ValueError("The requested workspace is outside the Aegis allowlist.")
    return target


def control_camera_runtime(
    *,
    action: str,
    camera_id: str | None = None,
    scope: str = "one",
    actor_id: str = "aegis-agent",
) -> CameraControlResult:
    """Start or stop configured cameras without exposing configuration access."""
    normalized_action = str(action).strip().casefold()
    normalized_scope = str(scope).strip().casefold()
    if normalized_action not in {"start", "stop"}:
        raise ValueError("Camera runtime action must be start or stop.")
    if normalized_scope not in {"one", "all"}:
        raise ValueError("Camera runtime scope must be one or all.")

    from aegis.api.routes.cameras import get_camera_manager
    from aegis.audit import record_audit

    manager = get_camera_manager()
    configured = {
        str(item.get("camera_id")): item
        for item in manager.list_cameras()
        if isinstance(item, dict) and item.get("camera_id")
    }
    if normalized_scope == "one":
        requested_id = str(camera_id or "").strip()
        if not requested_id or requested_id not in configured:
            raise LookupError("The requested configured camera was not found.")
        target_ids = [requested_id]
    else:
        target_ids = [
            item_id
            for item_id, item in configured.items()
            if normalized_action == "stop" or item.get("enabled", True) is not False
        ]

    changed: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    operation = manager.start_camera if normalized_action == "start" else manager.stop_camera
    for target_id in target_ids:
        try:
            payload = operation(target_id)
            changed.append(payload if isinstance(payload, dict) else {"camera_id": target_id, "status": normalized_action})
        except Exception as exc:
            failures.append({"camera_id": target_id, "error": type(exc).__name__})
            continue
        try:
            record_audit(
                "agent.camera_started" if normalized_action == "start" else "agent.camera_stopped",
                actor_id=str(actor_id)[:160] or "aegis-agent",
                resource_type="camera",
                resource_id=target_id,
                details={"scope": normalized_scope, "permission": "autonomous_internal"},
            )
        except Exception as exc:
            failures.append({"camera_id": target_id, "error": f"audit:{type(exc).__name__}"})

    return CameraControlResult(
        action=normalized_action,
        requested_scope=normalized_scope,
        cameras=tuple(changed),
        failures=tuple(failures),
    )
