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

from collections import deque
from typing import Dict, Optional

import numpy as np

from .tinynet import TemporalPatchNet, normalise_stack


class TrackVerifier:
    def __init__(self, weights_path: str):
        self.net = TemporalPatchNet.load(weights_path)
        self._patches: Dict[int, deque] = {}
        self.scores: Dict[int, float] = {}

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
        buf = self._patches.get(track_id)
        if buf is None or len(buf) < self.net.K:
            return None
        stack = normalise_stack(np.stack(buf))
        value = float(self.net.predict(stack[None])[0])
        self.scores[track_id] = value
        return value

    def forget(self, live_ids) -> None:
        for tid in list(self._patches):
            if tid not in live_ids:
                del self._patches[tid]
                self.scores.pop(tid, None)
