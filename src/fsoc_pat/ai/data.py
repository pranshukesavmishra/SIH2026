"""
Harvesting labelled patch stacks from the simulator.

The simulator is the labelling oracle: it knows exactly where the beacon, each
decoy, every star and every clutter source is in every frame, so training data
costs nothing but compute and inherits no annotation noise. Stacks are cut
around *true* source positions, plus matched random background positions, with
the source's sub-pixel motion followed frame to frame -- exactly what the real
verifier sees when it follows a track.

The generator varies scenario seed, beacon brightness, blink phase and
turbulence per sample, so the network cannot memorise one sky.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np

from ..config import SimConfig
from ..simulator import Simulator
from .tinynet import normalise_stack


def _cut(image: np.ndarray, u: float, v: float, patch: int) -> np.ndarray:
    half = patch // 2
    r, c = int(round(v)), int(round(u))
    h, w = image.shape
    if not (half <= r < h - half and half <= c < w - half):
        return None
    return image[r - half:r + half + 1, c - half:c + half + 1].astype(np.float64)


def harvest(n_runs: int = 24, frames: int = 8, patch: int = 11,
            base_seed: int = 1000, verbose: bool = False
            ) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns (stacks, labels): label 1 = the true beacon, 0 = anything else
    (stars, clutter, decoys, empty sky).
    """
    stacks: List[np.ndarray] = []
    labels: List[int] = []
    rng = np.random.default_rng(base_seed)

    for run in range(n_runs):
        cfg = SimConfig()
        cfg.seed = base_seed + run
        cfg.duration_s = (frames + 4) / cfg.camera.frame_rate_hz
        cfg.noise.frame_drop_probability = 0.0
        beacon = cfg.beacons[0]
        beacon.trajectory.kind = "linear"
        beacon.trajectory.params = dict(
            az_deg=0.3, el_deg=20.2,
            az_rate_deg_s=float(rng.uniform(-0.4, 0.4)),
            el_rate_deg_s=float(rng.uniform(-0.2, 0.2)), range_km=800.0)
        beacon.amplitude_e_s = float(rng.uniform(1.5e6, 1.2e7))
        beacon.blink_hz = 4.0
        beacon.blink_duty = 0.5
        # A hard negative that moves AND blinks -- at the wrong frequency.
        # Without it the network could pass by learning "anything that pulses",
        # which is not identification, just novelty detection.
        from ..config import BeaconConfig, TrajectoryConfig
        wrong_hz = float(rng.choice([1.5, 2.5, 6.5, 9.0]))
        cfg.beacons.append(BeaconConfig(
            name="imposter", is_decoy=True,
            amplitude_e_s=float(rng.uniform(1.5e6, 1.2e7)),
            blink_hz=wrong_hz, blink_duty=0.5,
            trajectory=TrajectoryConfig("linear", dict(
                az_deg=0.3 + float(rng.uniform(-1.5, 1.5)),
                el_deg=20.2 + float(rng.uniform(-1.0, 1.0)),
                az_rate_deg_s=float(rng.uniform(-0.4, 0.4)),
                el_rate_deg_s=float(rng.uniform(-0.2, 0.2)), range_km=800.0))))
        cfg.initial_pointing_deg = [0.3, 20.2]
        cfg.turbulence.tilt_rms_urad = float(rng.uniform(40.0, 250.0))
        cfg.scene.clutter_count = 60

        sim = Simulator(cfg)
        # Random phase offset: without it every training stack starts at t=0
        # and the network memorises ONE blink phase -- then fails on the seven
        # others it meets in service, where a window starts anywhere in the
        # cycle. (Found live as a train/serve gap, not by inspection.)
        skip = int(rng.integers(0, frames))
        for _ in range(skip):
            sim.step()
        run_frames = [sim.step() for _ in range(frames + 2)]

        def jitter():
            # Serving cuts patches at the tracker's smoothed estimate, which
            # wanders a pixel or two around the apparent source under
            # turbulence. Training must include that wander or centred-only
            # training makes off-centre beacons score as background.
            return rng.normal(0.0, 1.2, 2)

        # Beacon stack: follow its true sub-pixel position, jittered.
        stack = []
        ok = True
        for fr in run_frames[:frames]:
            t = fr.primary
            du, dv = jitter()
            cut = _cut(fr.image, t.u + du, t.v + dv, patch) if t.in_frame else None
            if cut is None:
                ok = False
                break
            stack.append(cut)
        if ok:
            stacks.append(normalise_stack(np.stack(stack)))
            labels.append(1)

        # Imposter stack: the wrong-frequency blinker, followed like the beacon.
        stack, ok = [], True
        for fr in run_frames[:frames]:
            imposter = next(t for t in fr.targets if t.is_decoy)
            cut = _cut(fr.image, imposter.u, imposter.v, patch) if imposter.in_frame else None
            if cut is None:
                ok = False
                break
            stack.append(cut)
        if ok:
            stacks.append(normalise_stack(np.stack(stack)))
            labels.append(0)

        # Negative stacks: stars/clutter (via scene internals is cheating --
        # use bright *detections* that are not the beacon), plus random sky.
        from ..detection import PointDetector
        det = PointDetector(psf_sigma=sim.camera.psf_sigma(cfg.turbulence.seeing_blur_px))
        first = run_frames[0]
        candidates = [d for d in det.detect(first.image)
                      if np.hypot(d.u - first.primary.u, d.v - first.primary.v) > 8.0]
        rng.shuffle(candidates)
        for d in candidates[:3]:
            stack, ok = [], True
            for fr in run_frames[:frames]:
                du, dv = jitter()
                cut = _cut(fr.image, d.u + du, d.v + dv, patch)
                if cut is None:
                    ok = False
                    break
                stack.append(cut)
            if ok:
                stacks.append(normalise_stack(np.stack(stack)))
                labels.append(0)
        for _ in range(2):                                   # empty sky
            u = rng.uniform(patch, cfg.camera.width - patch)
            v = rng.uniform(patch, cfg.camera.height - patch)
            stack = [_cut(fr.image, u, v, patch) for fr in run_frames[:frames]]
            if all(s is not None for s in stack):
                stacks.append(normalise_stack(np.stack(stack)))
                labels.append(0)

        if verbose and run % 8 == 0:
            print(f"  run {run}: {len(labels)} samples so far")

    return np.stack(stacks), np.array(labels, dtype=float)
