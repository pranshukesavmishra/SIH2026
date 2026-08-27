"""
Finding an unresolved beacon in a single frame.

The beacon is a *point* target: at these ranges it is smaller than one pixel,
so it carries no texture, no shape and no structure. Everything a detector can
use is that it is (a) brighter than its immediate surroundings and (b) shaped
exactly like the point spread function. The standard chain for this, used in
infrared search-and-track and in space surveillance, is followed here:

    top-hat  ->  matched filter  ->  CFAR threshold  ->  sub-pixel centroid

Each stage exists for a specific reason:

  * **Top-hat** removes anything larger than the PSF. The sky gradient, cloud
    and the sun's halo vary by orders of magnitude across the frame, so a
    global threshold is useless; morphological opening with a kernel wider
    than the PSF estimates that background and leaves point sources behind.

  * **Matched filter** — correlation with the PSF itself — is the optimal
    linear detector for a known-shape signal in additive noise. For a
    Gaussian PSF the correlation is just a Gaussian blur, which is why this
    costs almost nothing.

  * **CFAR** (constant false alarm rate) sets the threshold from the noise
    measured in an annulus around each pixel, so the false alarm rate stays
    fixed whether the beacon is against dark sky or bright cloud. A fixed
    threshold would drown in cloud and go blind against dark sky.

  * **Sub-pixel centroid** by quadratic interpolation of the log response.
    Pixel-accurate detection is not good enough: one pixel at this focal
    length is ~160 microradians, which is already larger than the pointing
    budget of the coarse stage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np


@dataclass
class Detection:
    """One candidate point source in one frame."""
    u: float              # sub-pixel column
    v: float              # sub-pixel row
    snr: float            # peak response over local noise sigma
    flux: float           # background-subtracted signal in the aperture
    sharpness: float      # 1.0 for a perfect PSF match, lower for extended blobs

    @property
    def position(self):
        return (self.u, self.v)


class PointDetector:
    """
    Single-frame detector for PSF-shaped point sources.

    ``cfar_k`` is the threshold in units of local noise sigma. For Gaussian
    noise the per-pixel false alarm probability is the Gaussian tail at k, so
    k = 5 gives roughly 3e-7 per pixel — about one false alarm per ten frames
    at 640x480, which the tracker's gating then rejects. Lower it to acquire
    fainter targets at the cost of more clutter to sort through.
    """

    def __init__(self, psf_sigma: float = 1.5, cfar_k: float = 5.0,
                 guard_px: Optional[int] = None, window_px: Optional[int] = None,
                 min_separation_px: Optional[int] = None, max_detections: int = 24,
                 stats_downscale: int = 4, border_margin_px: Optional[int] = None):
        self.psf_sigma = float(psf_sigma)
        self.cfar_k = float(cfar_k)
        # The guard band must exclude the target's own PSF wings from the noise
        # estimate, or a bright beacon inflates its own threshold and hides.
        self.guard = int(guard_px if guard_px is not None else max(3, round(4 * psf_sigma)))
        self.window = int(window_px if window_px is not None else self.guard * 3 + 2)
        self.min_sep = int(min_separation_px if min_separation_px is not None
                           else max(3, round(3 * psf_sigma)))
        self.max_detections = int(max_detections)
        self.stats_downscale = max(1, int(stats_downscale))
        # Within one filter footprint of the frame edge the top-hat and the
        # CFAR annulus both run on reflected data, which is not a real
        # neighbourhood: the statistics there are wrong and produce almost all
        # of the detector's false alarms. Measured on an empty field, the
        # border ring supplied 18 of 19 exceedances at k=5 while covering 14%
        # of the pixels. A source this close to the edge is about to leave the
        # field anyway, so excluding the ring costs nothing real.
        self.border_margin = int(border_margin_px if border_margin_px is not None
                                 else self.window)

        # 2.5 sigma is enough to erase a point source while leaving the
        # background intact, and the opening cost grows with kernel area.
        radius = max(1, int(round(2.5 * psf_sigma)))
        # A rectangular structuring element is separable, so OpenCV runs it as
        # two 1-D passes; an elliptical one of the same radius is not, and cost
        # three times as much for a background estimate that is indistinguishable.
        self._open_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (2 * radius + 1, 2 * radius + 1))

    # ---- stages --------------------------------------------------------
    def suppress_background(self, image: np.ndarray) -> np.ndarray:
        """White top-hat: whatever is smaller than the PSF kernel survives."""
        img = image.astype(np.float32, copy=False)
        opened = cv2.morphologyEx(img, cv2.MORPH_OPEN, self._open_kernel)
        return img - opened

    def matched_filter(self, residual: np.ndarray) -> np.ndarray:
        """Correlate with the PSF. For a symmetric Gaussian this is a blur."""
        ksize = int(2 * round(3 * self.psf_sigma) + 1)
        return cv2.GaussianBlur(residual, (ksize, ksize), self.psf_sigma,
                                borderType=cv2.BORDER_REPLICATE)

    def cfar_statistics(self, response: np.ndarray):
        """
        Local mean and standard deviation from an annulus around each pixel.

        Both are computed on a decimated grid and interpolated back up. This is
        not an approximation of convenience: the background statistics are
        smooth *by construction* — they come from the sky gradient, cloud and
        the sun's halo, none of which has structure at the pixel scale — while
        anything sharp enough to matter has already been removed by the top-hat.

        Decimation is safe here specifically because area-averaging preserves
        both the local mean and the local mean-of-squares exactly, so the
        variance recovered as ``E[x^2] - E[x]^2`` is the true full-resolution
        pixel variance, not the variance of a smoothed image. Doing this at
        full resolution cost 6 ms per frame, half the detector's budget.

        Set ``stats_downscale=1`` to compute it exactly, for validation.
        """
        scale = self.stats_downscale
        sq = cv2.multiply(response, response)

        if scale > 1:
            h, w_full = response.shape
            small_size = (max(w_full // scale, 8), max(h // scale, 8))
            grid = cv2.resize(response, small_size, interpolation=cv2.INTER_AREA)
            grid_sq = cv2.resize(sq, small_size, interpolation=cv2.INTER_AREA)
        else:
            grid, grid_sq = response, sq

        # Annulus = outer box minus the guard region at its centre. The guard
        # must exclude the target's own PSF wings, or a bright beacon inflates
        # the threshold that is supposed to find it.
        w = max(3, int(round(self.window / scale)))
        w += (w + 1) % 2
        g = max(1, int(round(self.guard / scale)))
        g += (g + 1) % 2

        sum_w = cv2.boxFilter(grid, -1, (w, w), normalize=False, borderType=cv2.BORDER_REFLECT)
        sum_g = cv2.boxFilter(grid, -1, (g, g), normalize=False, borderType=cv2.BORDER_REFLECT)
        sqsum_w = cv2.boxFilter(grid_sq, -1, (w, w), normalize=False, borderType=cv2.BORDER_REFLECT)
        sqsum_g = cv2.boxFilter(grid_sq, -1, (g, g), normalize=False, borderType=cv2.BORDER_REFLECT)

        n = float(w * w - g * g)
        mean = (sum_w - sum_g) / n
        var = np.maximum((sqsum_w - sqsum_g) / n - mean * mean, 1e-12)
        sigma = np.sqrt(var)

        if scale > 1:
            size = (response.shape[1], response.shape[0])
            mean = cv2.resize(mean, size, interpolation=cv2.INTER_LINEAR)
            sigma = cv2.resize(sigma, size, interpolation=cv2.INTER_LINEAR)
        return mean, sigma

    # ---- main entry point ----------------------------------------------
    def detect(self, image: np.ndarray) -> List[Detection]:
        residual = self.suppress_background(image)
        response = self.matched_filter(residual)
        mean, sigma = self.cfar_statistics(response)

        # Interpolation and sharpness both need the background removed: the
        # log-parabola below is exact for a Gaussian sitting on zero, not for
        # one sitting on an arbitrary pedestal.
        clean = response - mean
        excess = clean / sigma
        candidates = excess > self.cfar_k
        if not candidates.any():
            return []

        # Keep only strict local maxima, then enforce a separation radius so a
        # single bright source does not produce a cluster of detections.
        # A separable pair of 1-D dilations is equivalent to one square
        # dilation and markedly cheaper at this kernel size.
        k = 2 * self.min_sep + 1
        peaks = cv2.dilate(clean, np.ones((1, k), np.uint8))
        peaks = cv2.dilate(peaks, np.ones((k, 1), np.uint8))
        candidates &= (clean >= peaks)

        m = self.border_margin
        if m > 0:
            candidates[:m, :] = False
            candidates[-m:, :] = False
            candidates[:, :m] = False
            candidates[:, -m:] = False

        rows, cols = np.nonzero(candidates)
        if len(rows) == 0:
            return []
        strengths = excess[rows, cols]
        order = np.argsort(-strengths)[:self.max_detections]

        out: List[Detection] = []
        for idx in order:
            r, c = int(rows[idx]), int(cols[idx])
            du, dv = self._subpixel_offset(clean, r, c)
            out.append(Detection(
                u=c + 0.5 + du, v=r + 0.5 + dv,
                snr=float(strengths[idx]),
                flux=float(self._aperture_flux(residual, r, c)),
                sharpness=float(self._sharpness(clean, r, c)),
            ))
        return out

    # ---- helpers -------------------------------------------------------
    @staticmethod
    def _subpixel_offset(clean: np.ndarray, r: int, c: int):
        """
        Quadratic peak interpolation, separably in x and y.

        ``clean`` must be background-subtracted. Fitting a parabola to the
        *logarithm* of three samples is algebraically exact for a Gaussian
        peak, which is what a matched-filtered PSF is, and recovers the
        centroid to a few hundredths of a pixel. Where the wings fall to or
        below zero the log is undefined, so it falls back to the ordinary
        three-point parabola, which is less accurate but always defined.
        """
        h, w = clean.shape
        if not (1 <= r < h - 1 and 1 <= c < w - 1):
            return 0.0, 0.0

        def offset(a, b, c_):
            if a > 0.0 and b > 0.0 and c_ > 0.0:
                la, lb, lc = np.log(a), np.log(b), np.log(c_)
                denom = la - 2.0 * lb + lc
                if denom < -1e-12:                       # concave: a real peak
                    return float(np.clip(0.5 * (la - lc) / denom, -0.5, 0.5))
            denom = a - 2.0 * b + c_
            if denom < -1e-12:
                return float(np.clip(0.5 * (a - c_) / denom, -0.5, 0.5))
            return 0.0

        du = offset(clean[r, c - 1], clean[r, c], clean[r, c + 1])
        dv = offset(clean[r - 1, c], clean[r, c], clean[r + 1, c])
        return du, dv

    def _aperture_flux(self, residual: np.ndarray, r: int, c: int) -> float:
        """Background-subtracted signal inside a PSF-sized aperture."""
        rad = max(1, int(round(2.0 * self.psf_sigma)))
        h, w = residual.shape
        patch = residual[max(r - rad, 0):min(r + rad + 1, h),
                         max(c - rad, 0):min(c + rad + 1, w)]
        return float(patch.sum())

    def _sharpness(self, clean: np.ndarray, r: int, c: int) -> float:
        """
        How PSF-like the source is: peak against a one-sigma ring around it.

        A genuine point source falls off as the PSF does. An extended blob --
        a cloud edge caught by the top-hat, or two merged sources -- does not,
        and scores lower. The tracker uses this to prefer real beacons over
        structured background.
        """
        rad = max(1, int(round(self.psf_sigma)))
        h, w = clean.shape
        r0, r1 = max(r - rad, 0), min(r + rad + 1, h)
        c0, c1 = max(c - rad, 0), min(c + rad + 1, w)
        patch = clean[r0:r1, c0:c1]
        peak = clean[r, c]
        if peak <= 0 or patch.size <= 1:
            return 0.0
        ring = (patch.sum() - peak) / (patch.size - 1)
        expected = float(np.exp(-0.5))            # a Gaussian at one sigma
        return float(np.clip((ring / peak) / expected, 0.0, 2.0))
