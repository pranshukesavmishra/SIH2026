"""
Beacon detection for the desk rig's optical regime.

Why this exists alongside :mod:`fsoc_pat.detection`:

The mission detector is built for an *unresolved* target -- a beacon at
kilometres range lands inside one pixel, carries no shape, and is found by
top-hat -> matched filter -> CFAR. That chain's first stage removes
everything *larger* than the PSF kernel, which is exactly right when the
signal is a point and the clutter is sky gradient and cloud.

The desk rig inverts that regime. A phone flashlight 1-2 m from a webcam is
a saturated blob 40-80 px across -- far larger than the PSF kernel -- so the
top-hat classifies it as background and erases it, while 1-3 px sensor grain
survives and passes CFAR (in a near-black frame the local noise sigma is
tiny, so grain scores SNR 10+). Observed live on the rig: a blazing
flashlight in frame produced zero detections on it and 24 detections on
empty noise.

So the rig gets a detector matched to its own regime -- find the bright
extended blob, then identify it by its blink -- while identification,
lock hysteresis and control stay the shared idea they always were. The
transfer claim the project makes is about the *identification* principle
(a beacon is known by its modulation, not its brightness), and that is
precisely what is preserved here.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class Blob:
    """One bright region in one frame."""
    u: float          # centroid column
    v: float          # centroid row
    area: int         # pixels above threshold
    peak: float       # brightest pixel value, 0-255


def to_gray8(image: np.ndarray) -> np.ndarray:
    """Accept the 12-bit-scaled frames UsbCamera emits, or plain 8-bit."""
    if image.dtype == np.uint16:
        return (image >> 4).astype(np.uint8)
    if image.dtype != np.uint8:
        return np.clip(image, 0, 255).astype(np.uint8)
    return image


class RigBeaconDetector:
    """
    Bright-blob detector.

    The beacon here saturates the sensor, so it is found by absolute
    brightness rather than by local contrast. Two thresholds work together:

      * ``abs_floor`` -- nothing dimmer than this is ever a candidate. This
        is what keeps an empty dark room silent instead of detecting grain:
        with no light source in frame the brightest pixel is well under the
        floor, so there are no candidates at all and the rig holds still.
      * ``rel_fraction`` of the frame maximum -- once something bright IS
        present, this cuts the blob out of its own bloom cleanly.

    ``min_area`` then discards single-pixel noise; a real flashlight core is
    tens to thousands of pixels.
    """

    def __init__(self, abs_floor: int = 110, rel_fraction: float = 0.55,
                 min_area: int = 6, max_area_fraction: float = 0.25,
                 max_blobs: int = 8):
        self.abs_floor = int(abs_floor)
        self.rel_fraction = float(rel_fraction)
        self.min_area = int(min_area)
        self.max_area_fraction = float(max_area_fraction)
        self.max_blobs = int(max_blobs)

    def detect(self, image: np.ndarray) -> List[Blob]:
        gray = to_gray8(image)
        peak = int(gray.max())
        if peak < self.abs_floor:
            return []                      # nothing bright enough to be a beacon

        thresh = max(self.abs_floor, int(self.rel_fraction * peak))
        _, mask = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
        # Close single-pixel gaps so a blinking source mid-transition still
        # reads as one blob rather than a scatter of fragments.
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

        n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
        max_area = self.max_area_fraction * gray.size
        blobs: List[Blob] = []
        for i in range(1, n):                     # 0 is the background label
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area < self.min_area or area > max_area:
                continue
            cu, cv_ = centroids[i]
            blobs.append(Blob(u=float(cu), v=float(cv_), area=area,
                              peak=float(gray[labels == i].max())))
        blobs.sort(key=lambda b: b.area, reverse=True)
        return blobs[:self.max_blobs]


@dataclass
class BlinkTrack:
    """A candidate location, watched over time for the beacon's modulation."""
    track_id: int
    u: float
    v: float
    samples: Deque[float] = field(default_factory=lambda: deque(maxlen=96))
    times: Deque[float] = field(default_factory=lambda: deque(maxlen=96))
    last_seen: float = 0.0
    score: float = 0.0
    dominant_hz: float = 0.0
    modulation: float = 0.0     # RMS of the AC component, 8-bit units


def _dft_power_fraction(x: np.ndarray, t: np.ndarray, f: float) -> float:
    """Fraction of the signal's AC power sitting at frequency ``f``."""
    total = float(np.dot(x, x))
    if total <= 1e-9:
        return 0.0
    w = np.exp(-2j * np.pi * f * (t - t[0]))
    comp = np.abs(np.dot(x, w)) ** 2
    return float(min(1.0, 2.0 * comp / (total * len(x))))


class BlinkIdentifier:
    """
    Turns bright blobs into an identified beacon by their temporal signature.

    Brightness is sampled at every live track's location on *every* frame,
    including frames where no blob was detected there -- the blink-off half
    of the cycle is half of the beacon's signature, and sampling only the
    frames where it is lit would show a source that never turns off, which
    is exactly what a steady lamp looks like.

    Two conditions must both hold before a track is called the beacon:

      * **modulation depth** -- the brightness must actually swing. A steady
        lamp, a window, a laptop screen: all bright, none modulated. This is
        the test that rejects "distraction" sources however bright they are.
      * **frequency match** -- most of that swing must sit at the beacon's
        blink rate, not spread across random flicker.
    """

    def __init__(self, blink_hz: float = 4.0, gate_px: float = 70.0,
                 patch_radius: int = 8, min_samples: int = 30,
                 min_modulation: float = 10.0, score_threshold: float = 0.30,
                 drop_after_s: float = 2.0):
        self.blink_hz = float(blink_hz)
        self.gate_px = float(gate_px)
        self.patch_radius = int(patch_radius)
        self.min_samples = int(min_samples)
        self.min_modulation = float(min_modulation)
        self.score_threshold = float(score_threshold)
        self.drop_after_s = float(drop_after_s)
        self.tracks: List[BlinkTrack] = []
        self._next_id = 1

    def _sample(self, gray: np.ndarray, u: float, v: float) -> float:
        r = self.patch_radius
        h, w = gray.shape[:2]
        y0, y1 = max(0, int(v) - r), min(h, int(v) + r + 1)
        x0, x1 = max(0, int(u) - r), min(w, int(u) + r + 1)
        patch = gray[y0:y1, x0:x1]
        return float(patch.max()) if patch.size else 0.0

    def update(self, blobs: List[Blob], image: np.ndarray,
               now: Optional[float] = None) -> List[BlinkTrack]:
        now = time.perf_counter() if now is None else now
        gray = to_gray8(image)

        unmatched = list(blobs)
        for track in self.tracks:
            best, best_d = None, self.gate_px
            for blob in unmatched:
                d = float(np.hypot(blob.u - track.u, blob.v - track.v))
                if d < best_d:
                    best, best_d = blob, d
            if best is not None:
                unmatched.remove(best)
                # Ease the track toward the blob rather than snapping: the
                # centroid of a blinking blob jitters as it fades in and out.
                track.u += 0.5 * (best.u - track.u)
                track.v += 0.5 * (best.v - track.v)
                track.last_seen = now

        for blob in unmatched:
            self.tracks.append(BlinkTrack(track_id=self._next_id, u=blob.u,
                                          v=blob.v, last_seen=now))
            self._next_id += 1

        for track in self.tracks:
            track.samples.append(self._sample(gray, track.u, track.v))
            track.times.append(now)
            self._score(track)

        self.tracks = [t for t in self.tracks
                       if now - t.last_seen <= self.drop_after_s]
        return self.tracks

    def _score(self, track: BlinkTrack) -> None:
        if len(track.samples) < self.min_samples:
            track.score = 0.0
            track.modulation = 0.0
            return
        x = np.asarray(track.samples, dtype=float)
        t = np.asarray(track.times, dtype=float)
        x = x - x.mean()
        track.modulation = float(np.sqrt(np.mean(x * x)))
        if track.modulation < self.min_modulation:
            # Bright but steady -- a lamp, a screen, a window. Not the beacon,
            # no matter how strong the signal is.
            track.score = 0.0
            track.dominant_hz = 0.0
            return
        track.score = _dft_power_fraction(x, t, self.blink_hz)

        span = float(t[-1] - t[0])
        if span > 0:
            fps = (len(t) - 1) / span
            top = min(15.0, 0.45 * fps)
            if top > 1.0:
                freqs = np.linspace(1.0, top, 60)
                powers = [_dft_power_fraction(x, t, f) for f in freqs]
                track.dominant_hz = float(freqs[int(np.argmax(powers))])

    def best(self) -> Optional[BlinkTrack]:
        confirmed = [t for t in self.tracks if t.score >= self.score_threshold]
        return max(confirmed, key=lambda t: t.score) if confirmed else None


class LockController:
    """
    SEARCHING -> CONFIRMING k/n -> LOCKED, with hysteresis both ways.

    Confirmation exists so one lucky frame cannot declare a lock, and the
    separate, longer drop count exists so the beacon's own blink-off frames
    -- or a hand briefly crossing it -- cannot drop one.
    """

    SEARCHING = "SEARCHING"
    CONFIRMING = "CONFIRMING"
    LOCKED = "LOCKED"

    def __init__(self, confirm_frames: int = 5, drop_frames: int = 20):
        self.confirm_frames = int(confirm_frames)
        self.drop_frames = int(drop_frames)
        self.state = self.SEARCHING
        self.hits = 0
        self.misses = 0
        self.track_id: Optional[int] = None

    def update(self, candidate: Optional[BlinkTrack]) -> str:
        if candidate is not None:
            if self.track_id is not None and candidate.track_id != self.track_id \
                    and self.state == self.LOCKED:
                # Hold the locked track; do not swap on a marginally better one.
                self.misses += 1
                if self.misses > self.drop_frames:
                    self._reset()
                return self.state
            self.track_id = candidate.track_id
            self.misses = 0
            self.hits += 1
            self.state = (self.LOCKED if self.hits >= self.confirm_frames
                          else self.CONFIRMING)
        else:
            self.misses += 1
            if self.state == self.LOCKED:
                if self.misses > self.drop_frames:
                    self._reset()
            else:
                self.hits = 0
                if self.misses > self.confirm_frames:
                    self._reset()
        return self.state

    def _reset(self) -> None:
        self.state = self.SEARCHING
        self.hits = 0
        self.misses = 0
        self.track_id = None

    @property
    def progress(self) -> Tuple[int, int]:
        return min(self.hits, self.confirm_frames), self.confirm_frames
