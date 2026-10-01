from aegis.intelligence.agent_control import control_camera_runtime, permission_manifest, workspace_target


class FakeCameraManager:
    def __init__(self):
        self.actions = []

    def list_cameras(self):
        return [
            {"camera_id": "north", "name": "North", "enabled": True},
            {"camera_id": "disabled", "name": "Disabled", "enabled": False},
        ]

    def start_camera(self, camera_id):
        self.actions.append(("start", camera_id))
        return {"camera_id": camera_id, "runtime": {"status": "online"}}

    def stop_camera(self, camera_id):
        self.actions.append(("stop", camera_id))
        return {"camera_id": camera_id, "runtime": {"status": "stopped"}}


def test_permission_manifest_keeps_destructive_and_host_actions_outside_autonomy():
    manifest = permission_manifest()
    assert "start_configured_camera" in manifest["autonomous"]
    assert "delete_camera_or_recording" in manifest["confirmation_required"]
    assert "host_os_or_shell_control" in manifest["denied"]
    assert workspace_target("analytics") == "/analytics"


def test_camera_control_executes_only_configured_runtime_actions(monkeypatch):
    manager = FakeCameraManager()
    audits = []
    monkeypatch.setattr("aegis.api.routes.cameras.get_camera_manager", lambda: manager)
    monkeypatch.setattr("aegis.audit.record_audit", lambda *args, **kwargs: audits.append((args, kwargs)))

    one = control_camera_runtime(action="stop", scope="one", camera_id="north", actor_id="operator")
    all_enabled = control_camera_runtime(action="start", scope="all", actor_id="operator")

    assert one.succeeded == 1
    assert all_enabled.succeeded == 1
    assert manager.actions == [("stop", "north"), ("start", "north")]
    assert len(audits) == 2


def test_camera_control_rejects_unknown_camera(monkeypatch):
    monkeypatch.setattr("aegis.api.routes.cameras.get_camera_manager", FakeCameraManager)

    try:
        control_camera_runtime(action="stop", scope="one", camera_id="unknown")
    except LookupError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("Unknown cameras must not be controlled")
