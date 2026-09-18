"""
Acquisition: covering the Field of Uncertainty until the beacon appears.

Before tracking can start, the terminal only knows the other end's direction to
within some uncertainty — ephemeris error, mount misalignment, GPS and time
error all add up to a cone perhaps a degree or two wide, while the camera sees
a few degrees. The standard answer in free-space optical links is an
**Archimedean spiral** outward from the best estimate: it is the pattern that
covers a disc with the shortest path, and it searches the most likely direction
first, so the expected acquisition time is far better than its worst case.

Two details decide whether a scan works in practice:

  * **Step spacing.** Consecutive spiral turns must overlap, or the beacon can
    sit in a gap and never be seen. The spacing is set from the *short* axis of
    the field of view, since the camera is not square.

  * **Dwell.** The mount must settle and the detector must integrate before the
    scan moves on. Vibration during a step is the dominant cause of missed
    detections in published acquisition studies, so dwell is expressed in
    frames rather than seconds and defaults to more than one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

import numpy as np


@dataclass
class SearchPlan:
    """A precomputed spiral, and the numbers that justify it."""
    points: List[Tuple[float, float]]        # (az, el) offsets from centre, radians
    step_rad: float
    fou_radius_rad: float
    dwell_frames: int

    @property
    def n_steps(self) -> int:
        return len(self.points)

    def expected_frames(self, frame_rate_hz: float) -> Tuple[float, float]:
        """(mean, worst-case) frames to acquisition, ignoring slew time."""
        worst = self.n_steps * self.dwell_frames
        # A spiral searches inward-out, so the mean is well under half the
        # worst case: most of the probability mass sits in the early turns.
        return worst / 3.0, float(worst)


class SpiralSearch:
    """
    Archimedean spiral over the field of uncertainty.

    ``r(theta) = step * theta / (2 pi)`` advances one step per turn; sampling
    it at equal *arc length* rather than equal angle keeps the dwell points
    evenly spread, which a naive equal-angle spiral does not — it bunches them
    near the centre and leaves gaps at the rim.
    """

    def __init__(self, fou_radius_deg: float = 1.5, fov_deg: float = 6.0,
                 aspect: float = 0.75, overlap: float = 0.75, dwell_frames: int = 2):
        self.fou_radius = np.radians(fou_radius_deg)
        # Use the short axis: covering with the wide axis leaves vertical gaps.
        self.step = np.radians(fov_deg) * aspect * overlap
        self.dwell_frames = max(1, int(dwell_frames))
        self.plan = self._build_plan()

        self._index = 0
        self._frames_on_point = 0
        self.completed_cycles = 0

    def _build_plan(self) -> SearchPlan:
        points: List[Tuple[float, float]] = [(0.0, 0.0)]
        if self.fou_radius <= self.step / 2.0:
            # The uncertainty already fits inside one frame: no scan needed.
            return SearchPlan(points, self.step, self.fou_radius, self.dwell_frames)

        a = self.step / (2.0 * np.pi)
        theta, max_theta = 0.0, 2.0 * np.pi * (self.fou_radius / self.step + 1.0)
        while theta < max_theta:
            # Advance by an arc length of one step: d(theta) = step / r locally.
            radius = a * theta
            theta += self.step / max(radius, self.step / (2.0 * np.pi))
            radius = a * theta
            if radius > self.fou_radius:
                break
            points.append((radius * np.cos(theta), radius * np.sin(theta)))
        return SearchPlan(points, self.step, self.fou_radius, self.dwell_frames)

    # ---- stepping ------------------------------------------------------
    def reset(self) -> None:
        self._index = 0
        self._frames_on_point = 0
        self.completed_cycles = 0

    def current_offset(self) -> Tuple[float, float]:
        return self.plan.points[self._index % self.plan.n_steps]

    def advance(self) -> None:
        """Call once per frame; moves to the next dwell point when due."""
        self._frames_on_point += 1
        if self._frames_on_point >= self.dwell_frames:
            self._frames_on_point = 0
            self._index += 1
            if self._index >= self.plan.n_steps:
                self._index = 0
                self.completed_cycles += 1

    def command(self, centre_az: float, centre_el: float) -> Tuple[float, float]:
        """
        Absolute pointing for the current dwell point.

        The azimuth offset is divided by cos(elevation) because a fixed
        azimuth step covers less sky the higher you point; without it the
        spiral collapses horizontally near the zenith and leaves the outer
        field of uncertainty unsearched.
        """
        d_az, d_el = self.current_offset()
        el = float(np.clip(centre_el + d_el, -np.pi / 2 + 1e-6, np.pi / 2 - 1e-6))
        return centre_az + d_az / max(np.cos(el), 0.05), el
