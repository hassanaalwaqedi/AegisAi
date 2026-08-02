from aegis.api.routes.cameras import _build_camera_heatmap, _normalise_camera_zones


def test_camera_heatmap_uses_actual_detection_centres():
    cells = _build_camera_heatmap(
        [
            {"bbox": [40, 40, 120, 160]},
            {"bbox": [45, 45, 125, 165]},
            {"bbox": [500, 300, 580, 420]},
        ],
        frame_width=640,
        frame_height=480,
    )

    assert sum(cell.count for cell in cells) == 3
    assert max(cell.intensity for cell in cells) == 1.0
    assert len(cells) == 2


def test_camera_zones_only_return_valid_saved_metadata():
    zones = _normalise_camera_zones(
        [
            {"id": "restricted-entry", "name": "Restricted entry", "type": "RESTRICTED", "bounds": [10, 20, 200, 300]},
            {"name": "Invalid", "bounds": [10, 20, 10, 30]},
        ]
    )

    assert len(zones) == 1
    assert zones[0].zone_id == "restricted-entry"
    assert zones[0].bounds == [10.0, 20.0, 200.0, 300.0]
