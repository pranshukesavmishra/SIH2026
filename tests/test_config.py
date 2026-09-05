"""Scenario files must survive a save/load cycle with their types intact."""
from fsoc_pat.config import CameraConfig, SimConfig, TrajectoryConfig


def test_round_trip_preserves_values(tmp_path):
    cfg = SimConfig()
    path = tmp_path / "s.yaml"
    cfg.save(str(path))
    assert SimConfig.load(str(path)).to_dict() == cfg.to_dict()


def test_nested_sections_are_rebuilt_as_dataclasses(tmp_path):
    """Regression: postponed annotations once left these as plain dicts."""
    path = tmp_path / "s.yaml"
    SimConfig().save(str(path))
    cfg = SimConfig.load(str(path))
    assert isinstance(cfg.camera, CameraConfig)
    assert isinstance(cfg.beacons[0].trajectory, TrajectoryConfig)
    assert cfg.gimbal.max_rate_deg_s == 20.0


def test_unknown_keys_are_ignored():
    cfg = SimConfig.from_dict({"name": "x", "not_a_field": 1, "camera": {"width": 320}})
    assert cfg.name == "x" and cfg.camera.width == 320


def test_shipped_scenarios_all_load():
    import glob
    files = sorted(glob.glob("scenarios/*.yaml"))
    assert files, "no scenarios found"
    for path in files:
        cfg = SimConfig.load(path)
        assert cfg.beacons and cfg.duration_s > 0
