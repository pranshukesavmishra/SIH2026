"""
Scenario definition, serialisation and seeding.

A scenario is the complete description of one simulation run. Two runs with
the same YAML file and the same seed produce bit-identical frames, which is
what makes the Monte Carlo campaign and the regression tests meaningful.

Every sub-config is a plain dataclass so that the GUI can bind widgets to
fields without a schema layer.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, get_type_hints

import yaml


@dataclass
class CameraConfig:
    """Detector and optics. Defaults model a modest machine-vision camera."""
    width: int = 640
    height: int = 480
    fov_deg: float = 6.0                 # horizontal field of view
    frame_rate_hz: float = 30.0
    exposure_ms: float = 10.0
    bit_depth: int = 12
    full_well_e: float = 20000.0
    read_noise_e: float = 6.0
    dark_current_e_per_s: float = 50.0
    psf_sigma_px: float = 1.3            # diffraction + defocus, as a Gaussian
    hot_pixel_fraction: float = 2e-4


@dataclass
class GimbalConfig:
    """Pan-tilt mount limits. These are what make naive controllers oscillate."""
    max_rate_deg_s: float = 20.0
    max_accel_deg_s2: float = 60.0
    command_latency_ms: float = 40.0
    encoder_noise_urad: float = 25.0
    az_limits_deg: Optional[List[float]] = None      # None = unlimited pan
    el_limits_deg: List[float] = field(default_factory=lambda: [-5.0, 89.0])


@dataclass
class TrajectoryConfig:
    """
    How a target moves. ``kind`` selects the generator in beacon.py.

    Supported kinds: static, linear, circular, waypoint, random_walk, leo_pass.
    ``params`` carries whatever that generator needs, in degrees and seconds.
    """
    kind: str = "leo_pass"
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BeaconConfig:
    """
    An optical target.

    ``amplitude_e_s`` is the peak detected signal rate at ``ref_range_km``;
    the simulator scales it by inverse square as the range changes, so a LEO
    pass naturally brightens towards closest approach.

    ``is_decoy`` marks a target the tracker is *not* supposed to lock onto.
    Decoys are how the discrimination logic gets tested rather than assumed.
    """
    name: str = "beacon"
    trajectory: TrajectoryConfig = field(default_factory=TrajectoryConfig)
    amplitude_e_s: float = 4.0e6
    ref_range_km: float = 800.0
    blink_hz: float = 0.0                # 0 = continuous wave
    blink_duty: float = 0.5
    is_decoy: bool = False


@dataclass
class TurbulenceConfig:
    """
    Atmospheric turbulence, as seen by a tracking camera.

    Modelled as two effects rather than a full phase screen: a temporally
    correlated tip/tilt jitter of the apparent target position, and log-normal
    scintillation of its intensity. The correlation time comes from the
    Greenwood frequency, so raising ``greenwood_hz`` makes the jitter harder
    for the controller to follow rather than merely larger.
    """
    enabled: bool = True
    tilt_rms_urad: float = 120.0
    greenwood_hz: float = 25.0
    scintillation_index: float = 0.25
    seeing_blur_px: float = 0.8


@dataclass
class VibrationConfig:
    """Platform vibration as damped resonances plus a broadband floor."""
    enabled: bool = True
    modes: List[List[float]] = field(
        # [frequency_hz, amplitude_urad, damping_ratio]
        default_factory=lambda: [[18.0, 90.0, 0.06], [47.0, 40.0, 0.08], [120.0, 15.0, 0.1]]
    )
    broadband_rms_urad: float = 20.0


@dataclass
class SceneConfig:
    """The fixed world: sky, cloud, horizon, stars and confusing bright things."""
    panorama_width: int = 1024           # low-frequency background only
    sky_brightness_e_s: float = 2.0e5
    cloud_amount: float = 0.35
    cloud_contrast: float = 0.6
    horizon_el_deg: float = 0.0
    terrain_brightness_e_s: float = 6.0e4
    star_count: int = 900
    star_max_e_s: float = 8.0e6
    clutter_count: int = 40              # point sources that mimic a beacon
    clutter_max_e_s: float = 2.0e7
    sun_az_deg: float = 120.0
    sun_el_deg: float = 35.0
    glint_probability: float = 0.004     # per frame
    glint_amplitude_e_s: float = 4.0e7


@dataclass
class NoiseConfig:
    """Non-ideal frame delivery."""
    enabled: bool = True
    frame_drop_probability: float = 0.01


@dataclass
class SimConfig:
    """A complete scenario."""
    name: str = "default"
    description: str = ""
    seed: int = 20261169
    duration_s: float = 60.0
    initial_pointing_deg: List[float] = field(default_factory=lambda: [0.0, 10.0])
    camera: CameraConfig = field(default_factory=CameraConfig)
    gimbal: GimbalConfig = field(default_factory=GimbalConfig)
    scene: SceneConfig = field(default_factory=SceneConfig)
    beacons: List[BeaconConfig] = field(default_factory=lambda: [BeaconConfig()])
    turbulence: TurbulenceConfig = field(default_factory=TurbulenceConfig)
    vibration: VibrationConfig = field(default_factory=VibrationConfig)
    noise: NoiseConfig = field(default_factory=NoiseConfig)

    # ---- serialisation -------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(self.to_dict(), fh, sort_keys=False, default_flow_style=False)

    @classmethod
    def load(cls, path: str) -> "SimConfig":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(yaml.safe_load(fh) or {})

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimConfig":
        data = dict(data or {})
        beacons = [_build(BeaconConfig, b) for b in data.pop("beacons", [])] or [BeaconConfig()]
        cfg = _build(cls, data)
        cfg.beacons = beacons
        return cfg


def _build(cls, data):
    """
    Recursively construct a nested dataclass from a plain dict.

    Field types are resolved with ``get_type_hints`` rather than read off
    ``field.type``: this module uses postponed annotation evaluation, so
    ``field.type`` is the *string* ``"CameraConfig"`` and a nested config
    would silently stay a dict, surfacing much later as an AttributeError
    deep inside the simulator.
    """
    if data is None:
        return cls()
    try:
        types = get_type_hints(cls)
    except Exception:                                   # pragma: no cover
        types = {f.name: f.type for f in dataclasses.fields(cls)}

    kwargs = {}
    for key, value in data.items():
        if key not in types:
            continue                                    # tolerate extra keys
        target = types[key]
        if dataclasses.is_dataclass(target) and isinstance(value, dict):
            kwargs[key] = _build(target, value)
        else:
            kwargs[key] = value
    return cls(**kwargs)
