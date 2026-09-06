"""
Optical targets and how they move.

A beacon is an unresolved point source with a direction, a slant range and a
brightness. Range matters because it drives brightness by inverse square, so a
satellite pass naturally brightens towards culmination — which is exactly the
regime where the gimbal is also slewing fastest. Those two effects fighting
each other is the interesting part of the tracking problem.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

from .config import BeaconConfig

EARTH_RADIUS_KM = 6371.0


def slant_range_km(elevation_rad: float, altitude_km: float) -> float:
    """
    Range to a circular-orbit target at a given elevation, from the ground.

    Standard geometry: the observer, the Earth centre and the target form a
    triangle, so range falls from ~2600 km at the horizon to the orbit
    altitude at the zenith for a typical LEO.
    """
    r_orbit = EARTH_RADIUS_KM + altitude_km
    sin_el = np.sin(elevation_rad)
    return float(np.sqrt(r_orbit ** 2 - (EARTH_RADIUS_KM * np.cos(elevation_rad)) ** 2)
                 - EARTH_RADIUS_KM * sin_el)


class Beacon:
    """One target. ``state(t)`` is the only thing the simulator needs."""

    def __init__(self, cfg: BeaconConfig, rng: np.random.Generator):
        self.cfg = cfg
        self.rng = rng
        self._walk_state = None
        self._walk_time = 0.0
        kind = cfg.trajectory.kind
        if kind not in _GENERATORS:
            raise ValueError(f"unknown trajectory kind {kind!r}; "
                             f"expected one of {sorted(_GENERATORS)}")
        self._generator = _GENERATORS[kind]

    def state(self, t: float) -> Tuple[float, float, float]:
        """Return ``(az_rad, el_rad, range_km)`` at simulation time ``t``."""
        return self._generator(self, t)

    def intensity(self, t: float, exposure_s: float, range_km: float) -> float:
        """
        Detected signal rate in electrons/second, including inverse-square
        range scaling and any blink modulation averaged over the exposure.
        """
        amp = self.cfg.amplitude_e_s * (self.cfg.ref_range_km / max(range_km, 1e-6)) ** 2
        return amp * self._blink_factor(t, exposure_s)

    def _blink_factor(self, t: float, exposure_s: float) -> float:
        """
        Fraction of the exposure during which a modulated beacon is emitting.

        Below the Nyquist rate of the exposure the camera resolves individual
        pulses and the beacon visibly flickers; above it the pulses average and
        the beacon simply looks dimmer by its duty cycle. Both regimes appear
        in real FSOC links, and the tracker has to survive the first one.
        """
        hz, duty = self.cfg.blink_hz, self.cfg.blink_duty
        if hz <= 0.0:
            return 1.0
        if hz * exposure_s >= 0.5:
            return duty                                  # unresolved, averages out
        phase = (t * hz) % 1.0
        return 1.0 if phase < duty else 0.0


# --------------------------------------------------------------------------
# Trajectory generators. Each takes (beacon, t) and returns (az, el, range_km).
# All angles in params are degrees; all times in seconds.
# --------------------------------------------------------------------------

def _static(b: Beacon, t: float):
    p = b.cfg.trajectory.params
    return (np.radians(p.get("az_deg", 0.0)),
            np.radians(p.get("el_deg", 20.0)),
            p.get("range_km", b.cfg.ref_range_km))


def _linear(b: Beacon, t: float):
    p = b.cfg.trajectory.params
    az = np.radians(p.get("az_deg", 0.0) + p.get("az_rate_deg_s", 1.0) * t)
    el = np.radians(p.get("el_deg", 20.0) + p.get("el_rate_deg_s", 0.0) * t)
    return az, el, p.get("range_km", b.cfg.ref_range_km)


def _circular(b: Beacon, t: float):
    p = b.cfg.trajectory.params
    period = max(p.get("period_s", 30.0), 1e-6)
    radius = np.radians(p.get("radius_deg", 2.0))
    theta = 2.0 * np.pi * t / period
    az = np.radians(p.get("center_az_deg", 0.0)) + radius * np.cos(theta)
    el = np.radians(p.get("center_el_deg", 20.0)) + radius * np.sin(theta)
    return az, el, p.get("range_km", b.cfg.ref_range_km)


def _waypoint(b: Beacon, t: float):
    """Piecewise-linear path through ``[[t, az_deg, el_deg, range_km?], ...]``."""
    p = b.cfg.trajectory.params
    pts = p.get("points") or [[0.0, 0.0, 20.0], [60.0, 10.0, 30.0]]
    arr = np.array([[row[0], row[1], row[2],
                     row[3] if len(row) > 3 else b.cfg.ref_range_km] for row in pts],
                   dtype=np.float64)
    ts = arr[:, 0]
    az = np.interp(t, ts, arr[:, 1])
    el = np.interp(t, ts, arr[:, 2])
    rng = np.interp(t, ts, arr[:, 3])
    return np.radians(az), np.radians(el), float(rng)


def _random_walk(b: Beacon, t: float):
    """
    Ornstein-Uhlenbeck wander about a fixed point.

    Advanced by the caller's time step rather than evaluated closed-form, so
    it is only correct when stepped monotonically — which the simulator does.
    """
    p = b.cfg.trajectory.params
    sigma = np.radians(p.get("sigma_deg", 0.5))
    tau = max(p.get("tau_s", 3.0), 1e-3)
    centre = np.array([np.radians(p.get("center_az_deg", 0.0)),
                       np.radians(p.get("center_el_deg", 20.0))])
    if b._walk_state is None:
        b._walk_state = centre.copy()
        b._walk_time = t
    dt = max(t - b._walk_time, 0.0)
    b._walk_time = t
    alpha = np.exp(-dt / tau)
    noise = b.rng.normal(size=2) * sigma * np.sqrt(max(1.0 - alpha ** 2, 0.0))
    b._walk_state = centre + alpha * (b._walk_state - centre) + noise
    return float(b._walk_state[0]), float(b._walk_state[1]), p.get("range_km", b.cfg.ref_range_km)


def _leo_pass(b: Beacon, t: float):
    """
    A low-Earth-orbit pass: a great-circle arc from horizon to horizon.

    Constructed from the culmination point rather than from two horizon
    crossings, because peak elevation is the parameter that actually
    determines how hard the pass is to track — a high pass sweeps azimuth
    through nearly 180 degrees in seconds.
    """
    from .geometry import unit_vector, angles_from_vector

    p = b.cfg.trajectory.params
    t_rise = p.get("t_rise_s", 0.0)
    t_set = p.get("t_set_s", 240.0)
    peak_el = np.radians(p.get("peak_el_deg", 55.0))
    peak_az = np.radians(p.get("peak_az_deg", 90.0))
    altitude = p.get("altitude_km", 550.0)

    span = max(t_set - t_rise, 1e-6)
    s = np.clip((t - t_rise) / span, 0.0, 1.0)
    theta = (-np.pi / 2.0) + np.pi * s                 # horizon to horizon

    culmination = unit_vector(peak_az, peak_el)
    up = np.array([0.0, 1.0, 0.0])
    along = np.cross(up, culmination)                  # horizontal, perpendicular
    along /= max(np.linalg.norm(along), 1e-12)

    v = culmination * np.cos(theta) + along * np.sin(theta)
    az, el = angles_from_vector(v)
    return float(az), float(max(el, 0.0)), slant_range_km(max(float(el), 0.0), altitude)


def _tle(b: Beacon, t: float):
    """
    A real satellite pass, propagated from its actual two-line elements.

    Uses the SGP4 propagator -- the same model the TLEs are fitted against,
    so using anything else with TLE inputs gives kilometres of error by
    construction. Parameters:

        line1, line2   the TLE
        lat_deg, lon_deg, alt_m   observer location
        epoch_offset_s   simulation t=0 relative to the TLE epoch

    The point is honest kinematics: a scenario driven by a real ISS or
    Starlink TLE exercises the tracker against genuine LEO angular-rate
    profiles rather than an invented arc. (Site coordinates use a spherical
    Earth for the topocentric conversion; the resulting arcminute-level
    differences do not matter for generating angular-rate profiles, and the
    limitation is stated here rather than hidden.)
    """
    try:
        from sgp4.api import Satrec, jday
    except ImportError as exc:                            # pragma: no cover
        raise RuntimeError("trajectory kind 'tle' needs the sgp4 package "
                           "(pip install sgp4)") from exc

    p = b.cfg.trajectory.params
    if b._walk_state is None:                 # reuse the scratch slot as a cache
        b._walk_state = Satrec.twoline2rv(p["line1"], p["line2"])
    sat = b._walk_state

    import datetime as _dt
    epoch = _dt.datetime(2000, 1, 1) + _dt.timedelta(
        days=sat.epochdays - 1.0) + _dt.timedelta(days=365.25 * (sat.epochyr - 2000) * 0)
    # Days since epoch year start handled by sgp4 internally via jd fields:
    jd = sat.jdsatepoch + sat.jdsatepochF + (p.get("epoch_offset_s", 0.0) + t) / 86400.0
    err, r_teme, _ = sat.sgp4(jd, 0.0)
    if err != 0:
        return 0.0, -0.1, 2000.0              # below horizon on propagator error

    r = np.asarray(r_teme)                    # km, TEME frame
    # Greenwich sidereal angle for TEME -> ECEF (sufficient at this fidelity).
    d_ut1 = jd - 2451545.0
    gmst = (280.46061837 + 360.98564736629 * d_ut1) % 360.0
    theta = np.radians(gmst)
    rot = np.array([[np.cos(theta), np.sin(theta), 0.0],
                    [-np.sin(theta), np.cos(theta), 0.0],
                    [0.0, 0.0, 1.0]])
    r_ecef = rot @ r

    lat = np.radians(p.get("lat_deg", 13.0))          # default: near Bengaluru
    lon = np.radians(p.get("lon_deg", 77.6))
    alt_km = p.get("alt_m", 900.0) / 1000.0
    site = (EARTH_RADIUS_KM + alt_km) * np.array(
        [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])

    rho = r_ecef - site
    east = np.array([-np.sin(lon), np.cos(lon), 0.0])
    north = np.array([-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)])
    up = site / np.linalg.norm(site)
    e, n, u = rho @ east, rho @ north, rho @ up

    az = float(np.arctan2(e, n))              # from north, toward east
    el = float(np.arcsin(np.clip(u / np.linalg.norm(rho), -1.0, 1.0)))
    # Map to this package's convention (az from +Z axis): identical structure,
    # the scene has no compass so only consistency matters.
    return az, el, float(np.linalg.norm(rho))


_GENERATORS = {
    "static": _static,
    "tle": _tle,
    "linear": _linear,
    "circular": _circular,
    "waypoint": _waypoint,
    "random_walk": _random_walk,
    "leo_pass": _leo_pass,
}
