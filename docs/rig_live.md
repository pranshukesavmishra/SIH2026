# ZD-1 RIG LIVE — running the real engine on the real camera

One command, one browser tab. This is the same `CoarseAlignmentTracker`
that produced every replayed number, fed by a camera instead of the
simulator — nothing in the tracking path knows the difference.

## Quick start (any laptop, no hardware)

    pip install -e .            # once
    python -m fsoc_pat.hil.serve --video path/to/clip.mp4 --blink-hz 4

Open **http://localhost:8765/rig.html**.

## With a camera (the demo)

    python -m fsoc_pat.hil.serve                 # auto-detects the camera

- Point the camera at the beacon unit. Dim the room; manual exposure
  helps (`--exposure -6` on most UVC cams).
- `--blink-hz 0` puts the identification in **adaptive mode**: no assumed
  frequency at all — the "measured blink" tile shows what the tracker
  itself measures. Change the beacon (`F6.0` on its serial port) and
  watch the readout follow. That is the whole pitch in one gesture.
- `--fov-deg` matters for µrad numbers: measure it (or run
  `python -m fsoc_pat.hil.calibrate`) rather than guessing.

## With the Mk2 rig attached

    python -m fsoc_pat.hil.serve --port-serial auto

The engine steers the mount only in TRACK/COAST and gates the laser
behind lock; coarse moves are step- and rate-limited in software
(`hil/mk2.py`) independent of what the tracking asks for. `--dry-run`
attaches the Mk2 driver but captures the would-be serial traffic instead
of sending it.

## What the dashboard will not show you

The real world has no ground truth. Pointing-error-vs-beacon, in-FOV %
and wrong-target counts exist only in simulation, where the true beacon
position is known. Live, the dashboard shows measured quantities only —
that is a feature, and judges should hear it said out loud.
