"""
Turning a stream of detections into one confident answer: which of these
sources is the beacon?

Detection alone is not enough. Every frame contains stars, ground clutter and
occasionally a sun glint, all rendered through the same point spread function
and all indistinguishable from the beacon in a single frame. Three independent
pieces of evidence separate them, and the tracker requires agreement:

  * **Persistence.** A real target is seen frame after frame and its position
    is predictable. Noise spikes are not, and clutter drifts with the camera
    rather than with the target.

  * **Motion consistency.** Once a track exists, its filter predicts where the
    source should appear. Sources that keep landing inside that prediction are
    behaving like a tracked object; sources that do not are gated out.

  * **A priori direction.** The terminal is not searching blind: ephemeris, or
    the last known position of the other end, says roughly where the remote
    terminal should be. This is what "designated target" means -- a candidate
    near the expected direction is far more likely to be the beacon than one
    at the edge of the field. Without this term a bright star inside the field
    of uncertainty is indistinguishable from the beacon on persistence alone,
    and the tracker will happily lock onto it and follow it forever.

  * **Modulation.** This is the decisive one, and it is how real free-space
    optical terminals tell a beacon from a reflection: the beacon is *pulsed*
    at a known rate, so its brightness carries a signature no star and no
    glint has. A Goertzel filter at the expected frequency scores each track's
    flux history. A sun glint can be brighter, sharper and more persistent
    than the beacon and still fail this test.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import geometry as geo
from .detection import Detection
from .estimation import IMMEstimator

# Chi-square 99% point for two degrees of freedom: the association gate.
GATE_CHI2 = 9.21


def goertzel_power(samples: Sequence[float], normalised_frequency: float) -> float:
    """
    Power at one frequency bin, without computing a whole DFT.

    The Goertzel algorithm is the right tool here: a single bin, updated over a
    short sliding history, at a frequency known in advance. It costs one
    multiply-accumulate per sample instead of a full transform per frame.
    """
    n = len(samples)
    if n < 8:
        return 0.0
    x = np.asarray(samples, dtype=np.float64)
    x = x - x.mean()
    if not np.any(x):
        return 0.0
    # Algebraically the Goertzel recurrence, evaluated as a single complex dot
    # product so it runs in NumPy rather than a Python loop: this is called for
    # every track on every frame, and the loop form cost more than the matched
    # filter did.
    phase = np.exp(-2j * np.pi * normalised_frequency * np.arange(n))
    power = abs(complex(np.dot(x, phase))) ** 2
    total = float(np.dot(x, x))
    return float(np.clip(power / max(total * n / 2.0, 1e-12), 0.0, 1.0))


@dataclass
class Track:
    """One hypothesis about a persistent source in the sky."""
    track_id: int
    imm: IMMEstimator
    hits: int = 1
    misses: int = 0
    age: int = 1
    confirmed: bool = False
    last_detection: Optional[Detection] = None
    flux_history: deque = field(default_factory=lambda: deque(maxlen=90))
    innovation_history: deque = field(default_factory=lambda: deque(maxlen=30))
    modulation_score: float = 0.0
    prior_score: float = 0.0

    @property
    def hit_ratio(self) -> float:
        return self.hits / max(self.age, 1)

    @property
    def angles(self) -> Tuple[float, float]:
        return self.imm.angles

    @property
    def consistency(self) -> float:
        """1.0 when measurements land where the filter predicted, 0 when not."""
        if not self.innovation_history:
            return 0.0
        mean_nis = float(np.mean(self.innovation_history))
        return float(np.clip(1.0 - mean_nis / (2.0 * GATE_CHI2), 0.0, 1.0))

    def score(self, require_modulation: bool) -> float:
        """
        How likely this track is to be the beacon.

        Weighted so no single piece of evidence can carry a track on its own:
        a persistent bright glint still loses to a fainter source that sits
        where the beacon is expected and modulates correctly.
        """
        base = 0.35 * min(self.hit_ratio, 1.0) + 0.20 * self.consistency
        base += 0.08 * float(np.clip(self.age / 30.0, 0.0, 1.0))
        base += 0.30 * self.prior_score
        if require_modulation:
            base += 0.55 * self.modulation_score
        elif self.last_detection is not None:
            base += 0.15 * float(np.clip(self.last_detection.snr / 30.0, 0.0, 1.0))
        return float(base)


class MultiTargetTracker:
    """
    Maintains tracks across frames and nominates one of them as the beacon.

    Association is greedy global-nearest-neighbour on Mahalanobis distance.
    With a handful of candidates inside the gate that is optimal in practice
    and costs nothing; the assignment problem only needs a full solver when
    many targets compete for many detections, which is not this scene.
    """

    def __init__(self, focal_px: float, width: int, height: int,
                 frame_rate_hz: float = 30.0, encoder_noise_urad: float = 25.0,
                 beacon_blink_hz: float = 0.0, confirm_hits: int = 3,
                 max_misses: int = 12, max_tracks: int = 24,
                 pointing_jitter_urad: float = 0.0,
                 initial_rate_sigma_deg_s: float = 3.0,
                 modulation_threshold: float = 0.22):
        self.focal_px = float(focal_px)
        self.width, self.height = int(width), int(height)
        self.frame_rate = float(frame_rate_hz)
        self.encoder_sigma = encoder_noise_urad * 1e-6
        # The measurement noise floor is set by the *disturbances*, not by how
        # well the detector centroids. Two effects displace a measurement and
        # neither is observable frame to frame: platform vibration moves the
        # optical axis away from what the encoders report, and turbulent
        # tip/tilt moves the apparent source. Together they are of order
        # 150 urad here, more than twenty times the centroiding error of a
        # bright target. Omitting them makes every association gate roughly six
        # times too tight, so no track survives to a second frame and the
        # tracker silently spawns and discards a track per detection per frame.
        self.jitter_sigma = pointing_jitter_urad * 1e-6
        self.initial_rate_sigma_deg_s = float(initial_rate_sigma_deg_s)
        self.beacon_blink_hz = float(beacon_blink_hz)
        self.confirm_hits = int(confirm_hits)
        self.max_misses = int(max_misses)
        self.max_tracks = int(max_tracks)
        self.modulation_threshold = float(modulation_threshold)
        # Whether the beacon's pulsing is visible at this frame rate at all.
        # Above the Nyquist limit it aliases away, the single most useful
        # discriminator is unavailable, and the system falls back to
        # persistence and the a priori direction. An acquisition beacon should
        # be specified to modulate below this limit for exactly this reason.
        self.modulation_observable = 0.01 < (self.beacon_blink_hz / self.frame_rate) < 0.49
        self.modulation_aliased = self.beacon_blink_hz > 0.0 and not self.modulation_observable

        self.tracks: List[Track] = []
        self._next_id = 1
        self._expected: Optional[Tuple[float, float]] = None
        self._expected_sigma: float = np.radians(2.0)

    def set_expectation(self, az: float, el: float, sigma_rad: float) -> None:
        """
        Tell the tracker where the remote terminal is expected to be.

        Before lock this comes from ephemeris and is as wide as the field of
        uncertainty. After lock the caller narrows it and slides it along with
        the track, so the prior keeps rejecting newly appearing clutter without
        fighting the target it has already found.
        """
        self._expected = (float(az), float(el))
        self._expected_sigma = max(float(sigma_rad), 1e-6)

    def _score_prior(self) -> None:
        if self._expected is None:
            for track in self.tracks:
                track.prior_score = 0.0
            return
        for track in self.tracks:
            az, el = track.angles
            d = float(geo.angular_separation(az, el, self._expected[0], self._expected[1]))
            track.prior_score = float(np.exp(-0.5 * (d / self._expected_sigma) ** 2))

    # ---- measurement model ---------------------------------------------
    def measurement_sigma(self, detection: Detection) -> float:
        """
        Angular one-sigma for a detection, from its own SNR.

        Centroiding a known PSF is Cramer-Rao limited, so the error falls as
        1/SNR. The constant is measured from this simulator's own detector
        benchmark (error x SNR ~ 0.8 px), which is why the filter's gate sizes
        itself correctly without hand tuning.
        """
        sigma_px = float(np.clip(0.8 / max(detection.snr, 1e-3), 0.01, 3.0))
        centroid = geo.px_to_urad(sigma_px, self.focal_px) * 1e-6
        return float(np.sqrt(centroid ** 2 + self.encoder_sigma ** 2
                             + self.jitter_sigma ** 2))

    def to_angles(self, detection: Detection, cam_az: float, cam_el: float):
        az, el = geo.unproject(detection.u, detection.v, cam_az, cam_el,
                               self.focal_px, self.width, self.height)
        return np.array([float(az), float(el)])

    # ---- main update ----------------------------------------------------
    def update(self, detections: List[Detection], cam_az: float, cam_el: float,
               dt: float) -> None:
        for track in self.tracks:
            track.imm.predict(dt)
            track.age += 1

        measurements = [self.to_angles(d, cam_az, cam_el) for d in detections]
        sigmas = [self.measurement_sigma(d) for d in detections]

        pairs = []
        for ti, track in enumerate(self.tracks):
            for di, (z, sigma) in enumerate(zip(measurements, sigmas)):
                R = np.eye(2) * sigma ** 2
                distance = track.imm.gate_distance(z, R)
                if distance <= GATE_CHI2:
                    pairs.append((distance, ti, di))
        pairs.sort()

        used_tracks, used_dets = set(), set()
        for distance, ti, di in pairs:
            if ti in used_tracks or di in used_dets:
                continue
            used_tracks.add(ti)
            used_dets.add(di)
            track = self.tracks[ti]
            R = np.eye(2) * sigmas[di] ** 2
            track.imm.update(measurements[di], R)
            track.hits += 1
            track.misses = 0
            track.last_detection = detections[di]
            track.flux_history.append(detections[di].flux)
            track.innovation_history.append(distance)
            if track.hits >= self.confirm_hits:
                track.confirmed = True

        for ti, track in enumerate(self.tracks):
            if ti not in used_tracks:
                track.misses += 1
                # Record a zero so a blinking beacon's off-frames still shape
                # its modulation signature instead of leaving a gap.
                track.flux_history.append(0.0)

        for di, detection in enumerate(detections):
            if di in used_dets or len(self.tracks) >= self.max_tracks:
                continue
            imm = IMMEstimator()
            imm.initialise(measurements[di][0], measurements[di][1], sigmas[di],
                           self.initial_rate_sigma_deg_s)
            track = Track(track_id=self._next_id, imm=imm, last_detection=detection)
            track.flux_history.append(detection.flux)
            self._next_id += 1
            self.tracks.append(track)

        self.tracks = [t for t in self.tracks if t.misses <= self.max_misses]
        self._score_modulation()
        self._score_prior()

    def _score_modulation(self) -> None:
        if self.beacon_blink_hz <= 0.0:
            return
        normalised = self.beacon_blink_hz / self.frame_rate
        if not (0.01 < normalised < 0.49):
            # Outside the frame rate's Nyquist band the modulation is not
            # observable at all; claiming a score here would be fiction.
            for track in self.tracks:
                track.modulation_score = 0.0
            return
        for track in self.tracks:
            track.modulation_score = goertzel_power(list(track.flux_history), normalised)

    # ---- outputs ---------------------------------------------------------
    def primary(self) -> Optional[Track]:
        """
        The best beacon candidate, or None if nothing is confirmed yet.

        When the beacon's modulation *is* observable, tracks that carry it are
        considered to the exclusion of those that do not. This is a hard gate
        rather than another weighted term because the evidence is categorical:
        a star has no modulation at all, so under heavy turbulence -- where the
        beacon is faint, scintillating and easily out-scored on brightness and
        persistence -- a weighted sum quietly hands the lock to a star that is
        merely easier to see. Nothing outranks "this one is pulsing".

        The gate opens only once some track actually clears the threshold, so
        acquisition still works during the first frames when no track has
        enough flux history to be scored.
        """
        confirmed = [t for t in self.tracks if t.confirmed]
        if not confirmed:
            return None
        require = self.modulation_observable
        if require:
            modulating = [t for t in confirmed if t.modulation_score >= self.modulation_threshold]
            if modulating:
                return max(modulating, key=lambda t: t.score(True))
        return max(confirmed, key=lambda t: t.score(require))

    def reset(self) -> None:
        self.tracks.clear()
