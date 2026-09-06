"""
The fixed world the camera looks at.

Split by spatial frequency, because that is what the rendering cost depends on:

  * Low frequency — sky gradient, cloud, terrain below the horizon. Held as a
    small equirectangular panorama and resampled per frame. Smooth, so a
    1024x512 map is plenty even at a 6 degree field of view.

  * High frequency — stars, ground clutter, sun glint. Unresolved point
    sources, projected and splatted individually through the same PSF as the
    beacon. Rendering them the same way is the point: clutter that looked
    different from a beacon would let a detector cheat.

Both are fixed in the world frame, so they sweep across the detector as the
gimbal slews. That apparent motion is a large part of what a tracker has to
reject.
"""
from __future__ import annotations

import cv2
import numpy as np

from . import geometry as geo
from .config import SceneConfig
from .optics import splat_gaussian


class Scene:
    def __init__(self, cfg: SceneConfig, camera_cfg, rng: np.random.Generator):
        self.cfg = cfg
        self.camera_cfg = camera_cfg
        self.rng = rng

        self.pano_w = int(cfg.panorama_width)
        self.pano_h = max(2, self.pano_w // 2)
        self._panorama = self._build_panorama()

        self._stars = self._sample_point_field(cfg.star_count, cfg.star_max_e_s,
                                               el_min=-5.0, el_max=89.0, power=2.5)
        self._clutter = self._sample_point_field(cfg.clutter_count, cfg.clutter_max_e_s,
                                                 el_min=-2.0, el_max=25.0, power=1.4)
        self._ray_cache = None
        self._glint = None

    # ---- construction --------------------------------------------------
    def _build_panorama(self) -> np.ndarray:
        """Sky gradient, fractal cloud and terrain, in electrons/second."""
        h, w = self.pano_h, self.pano_w
        el = np.linspace(np.pi / 2.0, -np.pi / 2.0, h)[:, None]

        # Sky brightens towards the horizon, as scattering path length grows.
        sky = self.cfg.sky_brightness_e_s * (0.35 + 0.65 * np.cos(el) ** 2)
        sky = np.repeat(sky, w, axis=1)

        if self.cfg.cloud_amount > 0.0:
            cloud = self._fractal_noise(h, w, octaves=5)
            cloud = np.clip((cloud - (1.0 - self.cfg.cloud_amount)) /
                            max(self.cfg.cloud_amount, 1e-6), 0.0, 1.0)
            sky *= 1.0 + self.cfg.cloud_contrast * cloud

        horizon = np.radians(self.cfg.horizon_el_deg)
        below = (el < horizon).astype(np.float64)
        terrain = self.cfg.terrain_brightness_e_s * (0.6 + 0.4 * self._fractal_noise(h, w, octaves=4))
        pano = sky * (1.0 - below) + terrain * below

        # Forward-scattered glow around the sun.
        sun_x = int((np.radians(self.cfg.sun_az_deg) + np.pi) / (2 * np.pi) * w) % w
        sun_y = int((np.pi / 2 - np.radians(self.cfg.sun_el_deg)) / np.pi * h)
        yy, xx = np.mgrid[0:h, 0:w]
        dx = np.minimum(np.abs(xx - sun_x), w - np.abs(xx - sun_x)) / w * 2 * np.pi
        dy = (yy - sun_y) / h * np.pi
        halo = np.exp(-((dx ** 2 + dy ** 2) / (2 * np.radians(18.0) ** 2)))
        pano *= 1.0 + 2.5 * halo
        return pano.astype(np.float32)

    def _fractal_noise(self, h: int, w: int, octaves: int = 4) -> np.ndarray:
        """Sum of upsampled random fields; cheap, seeded, and smooth enough."""
        out = np.zeros((h, w), dtype=np.float32)
        amplitude, total = 1.0, 0.0
        for octave in range(octaves):
            size = max(2, 2 ** (octave + 2))
            layer = self.rng.random((size, max(2, size * 2))).astype(np.float32)
            layer = cv2.resize(layer, (w, h), interpolation=cv2.INTER_CUBIC)
            out += amplitude * layer
            total += amplitude
            amplitude *= 0.55
        out /= max(total, 1e-9)
        return np.clip(out, 0.0, 1.0)

    def _sample_point_field(self, count, max_rate, el_min, el_max, power):
        """
        Random point sources with a power-law brightness distribution, so a few
        are bright and most are near the noise floor — as in a real star field.
        """
        count = int(count)
        if count <= 0:
            return np.zeros((0, 3))
        az = self.rng.uniform(-np.pi, np.pi, count)
        el = np.radians(self.rng.uniform(el_min, el_max, count))
        brightness = max_rate * self.rng.random(count) ** power
        return np.stack([az, el, brightness], axis=1)

    # ---- rendering -----------------------------------------------------
    def _camera_rays(self):
        """Unit ray direction per pixel, in the camera frame. Computed once."""
        if self._ray_cache is not None:
            return self._ray_cache
        cam = self.camera_cfg
        f = geo.focal_px(cam.fov_deg, cam.width)
        u = np.arange(cam.width, dtype=np.float64) + 0.5 - cam.width / 2.0
        v = np.arange(cam.height, dtype=np.float64) + 0.5 - cam.height / 2.0
        uu, vv = np.meshgrid(u, v)
        rays = np.stack([uu / f, -vv / f, np.ones_like(uu)], axis=-1).astype(np.float32)
        rays /= np.linalg.norm(rays, axis=-1, keepdims=True)
        self._ray_cache = rays
        return rays

    def render_background(self, cam_az: float, cam_el: float) -> np.ndarray:
        """Diffuse background in electrons/second, for the current pointing."""
        rays = self._camera_rays()
        world = rays @ geo.camera_rotation(cam_az, cam_el).astype(np.float32)  # R^T applied
        az = np.arctan2(world[..., 0], world[..., 2])
        el = np.arcsin(np.clip(world[..., 1], -1.0, 1.0))

        map_x = ((az + np.pi) / (2.0 * np.pi) * self.pano_w).astype(np.float32)
        map_y = ((np.pi / 2.0 - el) / np.pi * self.pano_h).astype(np.float32)
        return cv2.remap(self._panorama, map_x, map_y,
                         interpolation=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_WRAP)

    def draw_point_sources(self, image, cam_az, cam_el, sigma_px, tilt=(0.0, 0.0)):
        """
        Splat every visible star and clutter source into ``image`` in place.

        ``tilt`` is the common-mode turbulence offset; applying it here as well
        as to the beacon is what makes the star field a usable reference for a
        team that wants to estimate and subtract it.
        """
        cam = self.camera_cfg
        f = geo.focal_px(cam.fov_deg, cam.width)
        for field in (self._stars, self._clutter):
            if len(field) == 0:
                continue
            u, v, visible = geo.project(field[:, 0] + tilt[0], field[:, 1] + tilt[1],
                                        cam_az, cam_el, f, cam.width, cam.height)
            idx = np.flatnonzero(visible)
            for i in idx:
                splat_gaussian(image, float(u[i]), float(v[i]), float(field[i, 2]), sigma_px)

    def maybe_glint(self, image, sigma_px, rng):
        """
        Occasional specular flash — a reflection off a distant surface.

        Bright, unpredictable, and shaped exactly like the beacon, so it is the
        single most effective way to provoke a false lock.
        """
        if rng.random() >= self.cfg.glint_probability:
            return None
        cam = self.camera_cfg
        u = rng.uniform(0, cam.width)
        v = rng.uniform(0, cam.height)
        amp = self.cfg.glint_amplitude_e_s * rng.uniform(0.6, 1.6)
        splat_gaussian(image, u, v, amp, sigma_px)
        return (u, v, amp)
