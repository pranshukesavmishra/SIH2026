"""
Shared rendering primitive: splatting point sources onto the focal plane.

Beacons, stars, clutter and sun glint are all unresolved point sources, so
they all reach the detector as the same thing — the point spread function,
scaled by brightness. Rendering them through one function keeps them
photometrically consistent, which matters: if clutter were drawn differently
from the beacon, a detector could cheat by learning the difference.
"""
from __future__ import annotations

import numpy as np


def splat_gaussian(image: np.ndarray, u: float, v: float, amplitude: float,
                   sigma: float, extent_sigmas: float = 4.0) -> None:
    """
    Add one Gaussian PSF to ``image`` in place, at sub-pixel position (u, v).

    Only a local window is touched, so rendering a thousand stars costs
    milliseconds rather than a full-frame operation each.
    """
    if amplitude <= 0.0 or sigma <= 0.0:
        return
    height, width = image.shape
    radius = int(np.ceil(extent_sigmas * sigma))

    u0, u1 = int(np.floor(u)) - radius, int(np.floor(u)) + radius + 1
    v0, v1 = int(np.floor(v)) - radius, int(np.floor(v)) + radius + 1
    u0c, u1c = max(u0, 0), min(u1, width)
    v0c, v1c = max(v0, 0), min(v1, height)
    if u0c >= u1c or v0c >= v1c:
        return

    xs = np.arange(u0c, u1c, dtype=np.float32) + np.float32(0.5 - u)
    ys = np.arange(v0c, v1c, dtype=np.float32) + np.float32(0.5 - v)
    gx = np.exp(-0.5 * (xs / sigma) ** 2)
    gy = np.exp(-0.5 * (ys / sigma) ** 2)
    # Normalised so `amplitude` is total signal, not peak: brightness then
    # stays meaningful when the PSF widens under seeing.
    kernel = np.outer(gy, gx) / np.float32(2.0 * np.pi * sigma * sigma)
    image[v0c:v1c, u0c:u1c] += amplitude * kernel


def splat_many(image: np.ndarray, us, vs, amplitudes, sigma: float) -> None:
    """Vectorised convenience wrapper for a field of point sources."""
    for u, v, a in zip(np.atleast_1d(us), np.atleast_1d(vs), np.atleast_1d(amplitudes)):
        splat_gaussian(image, float(u), float(v), float(a), sigma)
