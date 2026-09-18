"""
Angle/pixel geometry for a pan-tilt camera.

Conventions used everywhere in this package:

    Azimuth   az   radians, right-handed about the vertical axis, 0 = +Z
    Elevation el   radians, positive up, 0 = horizon, limited to +/- pi/2

    World unit vector for a direction (az, el):
        x = cos(el) * sin(az)      right
        y = sin(el)                up
        z = cos(el) * cos(az)      forward at (0, 0)

    Image coordinates are pixels with the origin at the top-left corner and
    the principal point at the image centre. +u is right, +v is down.

Working in unit vectors rather than raw angle differences matters: near the
zenith a naive `target_az - camera_az` overstates the true angular error by
1/cos(el), which would make the tracking controller unstable exactly where
a satellite pass is fastest.
"""
from __future__ import annotations

import numpy as np

TWO_PI = 2.0 * np.pi


def wrap_pi(angle):
    """Wrap an angle, or array of angles, into (-pi, pi]."""
    return (np.asarray(angle) + np.pi) % TWO_PI - np.pi


def clamp_elevation(el):
    """Clamp elevation into [-pi/2, pi/2]; a gimbal cannot tip past the zenith."""
    return np.clip(el, -np.pi / 2.0, np.pi / 2.0)


def focal_px(fov_deg: float, width_px: int) -> float:
    """Focal length in pixels for a given horizontal field of view."""
    return (width_px / 2.0) / np.tan(np.radians(fov_deg) / 2.0)


def fov_deg_from_focal(focal_pixels: float, width_px: int) -> float:
    """Inverse of :func:`focal_px`, used when a real lens is specified in mm."""
    return float(np.degrees(2.0 * np.arctan((width_px / 2.0) / focal_pixels)))


def unit_vector(az, el):
    """Direction (az, el) -> unit vector(s) in world frame, shape (..., 3)."""
    az = np.asarray(az, dtype=np.float64)
    el = np.asarray(el, dtype=np.float64)
    cos_el = np.cos(el)
    return np.stack([cos_el * np.sin(az), np.sin(el), cos_el * np.cos(az)], axis=-1)


def angles_from_vector(v):
    """Unit vector(s) -> (az, el). Inverse of :func:`unit_vector`."""
    v = np.asarray(v, dtype=np.float64)
    x, y, z = v[..., 0], v[..., 1], v[..., 2]
    az = np.arctan2(x, z)
    el = np.arcsin(np.clip(y / np.maximum(np.linalg.norm(v, axis=-1), 1e-12), -1.0, 1.0))
    return az, el


def camera_rotation(cam_az: float, cam_el: float) -> np.ndarray:
    """
    World -> camera rotation matrix for a camera pointed at (cam_az, cam_el).

    Applying this to a world unit vector gives the same vector expressed in the
    camera frame, where +Z is the boresight.
    """
    ca, sa = np.cos(cam_az), np.sin(cam_az)
    ce, se = np.cos(cam_el), np.sin(cam_el)
    # Undo the azimuth pan, then undo the elevation tilt.
    r_yaw = np.array([[ca, 0.0, -sa],
                      [0.0, 1.0, 0.0],
                      [sa, 0.0, ca]])
    r_pitch = np.array([[1.0, 0.0, 0.0],
                        [0.0, ce, -se],
                        [0.0, se, ce]])
    return r_pitch @ r_yaw


def project(target_az, target_el, cam_az, cam_el, focal_pixels, width, height):
    """
    Project world direction(s) into image coordinates.

    Returns ``(u, v, visible)`` where ``visible`` is False for anything behind
    the camera or outside the sensor. Scalars in, scalars out.
    """
    v_world = unit_vector(target_az, target_el)
    v_cam = v_world @ camera_rotation(cam_az, cam_el).T

    z = v_cam[..., 2]
    in_front = z > 1e-9
    safe_z = np.where(in_front, z, 1.0)

    u = focal_pixels * v_cam[..., 0] / safe_z + width / 2.0
    v = -focal_pixels * v_cam[..., 1] / safe_z + height / 2.0

    visible = in_front & (u >= 0) & (u < width) & (v >= 0) & (v < height)
    if np.isscalar(target_az) or np.ndim(target_az) == 0:
        return float(u), float(v), bool(visible)
    return u, v, visible


def unproject(u, v, cam_az, cam_el, focal_pixels, width, height):
    """
    Image coordinates -> world direction (az, el).

    This is what turns a detection in pixels into an absolute pointing command,
    so it is the inverse the tracking controller depends on.
    """
    x = (np.asarray(u, dtype=np.float64) - width / 2.0) / focal_pixels
    y = -(np.asarray(v, dtype=np.float64) - height / 2.0) / focal_pixels
    v_cam = np.stack([x, y, np.ones_like(x)], axis=-1)
    v_cam /= np.linalg.norm(v_cam, axis=-1, keepdims=True)
    v_world = v_cam @ camera_rotation(cam_az, cam_el)
    return angles_from_vector(v_world)


def angular_separation(az1, el1, az2, el2):
    """
    Great-circle angle between two directions, in radians.

    This is the only honest way to report tracking error: it stays correct at
    any elevation, unlike the difference of azimuth angles.
    """
    v1 = unit_vector(az1, el1)
    v2 = unit_vector(az2, el2)
    dot = np.clip(np.sum(v1 * v2, axis=-1), -1.0, 1.0)
    return np.arccos(dot)


def px_to_urad(pixels, focal_pixels):
    """Convert a pixel distance near the boresight to microradians."""
    return np.arctan(np.asarray(pixels, dtype=np.float64) / focal_pixels) * 1e6


def urad_to_px(urad, focal_pixels):
    """Convert microradians near the boresight to a pixel distance."""
    return np.tan(np.asarray(urad, dtype=np.float64) * 1e-6) * focal_pixels
