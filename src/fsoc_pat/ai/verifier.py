"""
The trained network in the loop: an extra, learned opinion on each track.

The verifier follows each candidate track, keeps the last K patches cut at the
track's own detected positions, and scores the stack. The score feeds the
tracker's evidence combination alongside persistence, consistency, the a
priori direction and the Goertzel modulation power -- it does not replace
them. The classical chain works from first principles at any configured blink
frequency; the network knows only what its training distribution taught it.
That difference is the honest headline of the AI comparison in the technical
report, not a footnote.
"""
from __future__ import annotations

import json
import pathlib
from collections import deque
from typing import Dict, Optional

import numpy as np

from .tinynet import TemporalPatchNet, normalise_stack


class TrackVerifier:
    def __init__(self, weights_path: str):
        self.net = TemporalPatchNet.load(weights_path)
        self._patches: Dict[int, deque] = {}
        self.scores: Dict[int, float] = {}
        # Calibration, when the sidecar exists (see ai/calibrate.py):
        # temperature-scaled probabilities plus the abstain band inside which
        # the verifier declines to vote at all. Absent sidecar = legacy
        # behaviour, bit for bit.
        self.temperature = 1.0
        self.abstain_lo: Optional[float] = None
        self.abstain_hi: Optional[float] = None
        sidecar = pathlib.Path(weights_path).with_name("calibration.json")
        if sidecar.exists():
            cal = json.loads(sidecar.read_text())
            self.temperature = float(cal.get("temperature", 1.0))
            self.abstain_lo = cal.get("abstain_lo")
            self.abstain_hi = cal.get("abstain_hi")

    def observe(self, track_id: int, image: np.ndarray,
                u: float, v: float) -> None:
        half = self.net.P // 2
        r, c = int(round(v)), int(round(u))
        h, w = image.shape
        if not (half <= r < h - half and half <= c < w - half):
            return
        buf = self._patches.setdefault(track_id, deque(maxlen=self.net.K))
        buf.append(image[r - half:r + half + 1, c - half:c + half + 1]
                   .astype(np.float64))

    def score(self, track_id: int) -> Optional[float]:
        """Calibrated probability that this track is the beacon -- or None.

        None means either "not enough patches yet" or, with calibration
        loaded, "the evidence is marginal and the verifier abstains": a
        probability inside the abstain band carries no information the
        validation set could confirm, so contributing it to the track score
        would be guessing. The classical evidence decides those cases alone.
        """
        buf = self._patches.get(track_id)
        if buf is None or len(buf) < self.net.K:
            return None
        stack = normalise_stack(np.stack(buf))
        logit = float(self.net.forward(stack[None])[0])
        raw = float(1.0 / (1.0 + np.exp(-logit)))
        self.scores[track_id] = raw
        if self.abstain_lo is not None:
            # The abstain decision runs on the CALIBRATED probability -- that
            # is what the validation set licensed. The vote that leaves this
            # method stays on the raw scale: the tracker's evidence weights
            # were tuned against it, and with T = 1.16 the two nearly
            # coincide -- rescaling the vote buys no accuracy while
            # perturbing a validated ensemble (measured: it moved the
            # featured ISS run's acquisition from 1.27 s to 3.77 s through
            # nothing but early track-election noise).
            calibrated = float(1.0 / (1.0 + np.exp(-logit / self.temperature)))
            if self.abstain_lo <= calibrated <= self.abstain_hi:
                return None
        return raw

    def forget(self, live_ids) -> None:
        for tid in list(self._patches):
            if tid not in live_ids:
                del self._patches[tid]
                self.scores.pop(tid, None)
