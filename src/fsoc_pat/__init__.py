"""
FSOC-PAT — virtual camera tracking testbed for coarse alignment of mobile
Free Space Optical Communication terminals.

Smart India Hackathon 2026, problem statement SIH26169 (ISRO).

The package is deliberately split so that every stage of the pointing,
acquisition and tracking (PAT) chain can be exercised, replaced or measured
in isolation:

    config       scenario definition, load/save, deterministic seeding
    geometry     angle <-> pixel projection for a pan-tilt camera
    scene        the fixed world the camera looks at (sky, stars, cloud, clutter)
    beacon       moving optical targets, their trajectories and radiometry
    camera       the virtual pan-tilt camera and its rate/acceleration limits
    disturbance  atmospheric turbulence, platform vibration, sensor noise
    simulator    steps everything forward and emits frames plus ground truth

Nothing in this package needs a network, a dataset or a physical device: a
scenario is fully described by its YAML file and its seed, so any run can be
reproduced exactly.
"""

__version__ = "0.1.0"
