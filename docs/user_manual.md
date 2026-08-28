# FSOC-PAT User Manual

The virtual camera tracking system for coarse alignment of FSOC terminals —
installation, operation, and parameter reference.

## 1. Installation

### From the packaged application (recommended for evaluation)
Unzip `fsoc-pat.zip` anywhere and run `fsoc-pat.exe` (Windows) or `fsoc-pat`
(Linux). Nothing else to install; scenarios and the trained AI model are
bundled.

### From source
Requires Python 3.10+.
```
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on Linux
pip install -e ".[gui,dev]"
pytest                            # 69 tests, ~2 minutes
python -m fsoc_pat.gui.app        # launch the GUI
```

### Building the standalone application yourself
`packaging\build.bat` (Windows) or `packaging/build.sh` (Linux) from the
repository root; the result appears in `dist/fsoc-pat/`.

## 2. Running the application

### GUI
```
fsoc-pat [scenario.yaml]          # default: scenarios/leo_pass_nominal.yaml
```
| Region | Contents |
|---|---|
| Left | Live camera view. Corner brackets frame the sensor's active area; the gap cross at centre is the boresight. Cyan diamonds = current detections. The locked track wears a double-arc reticle in the state colour — solid while tracking, dashed while coasting on prediction — with an arrowed half-second velocity vector; a ring pulses outward once at the moment of lock. During SEARCH the acquisition spiral and its current dwell point are drawn. Lower right, a 4× magnifier stays centred on the track, because at a 6° FOV the beacon is a handful of pixels. Top left, the state chip and the live numbers. |
| Middle | Live plots on a shared time axis: pointing error (log scale, filled, with the FOV half-width as the labelled failure line), manoeuvre probability (amber, filled) with normalised SNR behind it, and the lock state as solid coloured spans — the width of an orange COAST span *is* the length of a beacon blink. |
| Right | Controls (below). |
| Bottom | Status bar: time, state, pointing error, processing per frame (1 s rolling mean). |

**Controls.** *open/save scenario* — load or store any configuration as YAML.
*start/stop, pause.* *real-time pacing* — off runs the simulation as fast as
the machine allows. *show ground truth* — overlays the true beacon (green)
and decoys (red); intended for development, leave OFF for honest
demonstrations. *export performance report* — writes the JSON + text report
after a completed run. The disturbances and beacon groups edit the live
configuration: turbulence on/off and strength, Greenwood frequency,
vibration on/off, frame-drop probability, beacon brightness and blink rate.

The lock-state colours, everywhere in the application: blue SEARCH, yellow
ACQUIRE, green TRACK, orange COAST (holding lock through a signal gap), red
REACQUIRE.

### Headless
```
fsoc-pat --headless scenarios/iss_pass.yaml --duration 60 --out runs/
```
Prints the performance report and writes `<scenario>.report.{json,txt}`.

### Monte Carlo campaign
```
python -m fsoc_pat.campaign scenarios/leo_pass_nominal.yaml -n 64 --out runs/mc
```

### Demo video
```
python -m fsoc_pat.video scenarios/iss_pass.yaml --duration 45 --out demo.mp4
```

## 3. Scenario files

A scenario is one YAML file; two runs with the same file and seed are
bit-identical. The shipped library:

| File | Exercises |
|---|---|
| `static_easy.yaml` | Acquisition sanity: bright static beacon, no disturbances. |
| `leo_pass_nominal.yaml` | 550 km pass, 55° culmination; SNR 6 at acquisition, 39 at culmination, fastest slew when brightest. |
| `turbulence_hard.yaml` | 400 µrad tilt at 60 Hz, heavy scintillation. |
| `decoy_field.yaml` | Three moving decoys crossing the field + dense clutter + glint; wrong lock scores zero. |
| `uav_relay.yaml` | Manoeuvring UAV at 4 km, sharp waypoint turns. |
| `iss_pass.yaml` | A real ISS pass over Bengaluru propagated with SGP4; rates to 0.8°/s. |

Key sections (all editable in any text editor, or through the GUI panel):

```yaml
seed: 20261169                  # reproducibility
duration_s: 240.0
initial_pointing_deg: [12.2, 19.2]   # where the mount starts
acquisition_fou_deg: 2.0        # field-of-uncertainty radius the spiral covers
camera:   {fov_deg: 6.0, frame_rate_hz: 30, exposure_ms: 10, ...}
gimbal:   {max_rate_deg_s: 20, command_latency_ms: 40, ...}
scene:    {star_count: 900, clutter_count: 40, glint_probability: 0.004, ...}
beacons:  # first non-decoy = the designated target
  - name: beacon
    blink_hz: 4.0               # keep below half the frame rate
    amplitude_e_s: 4.0e6
    trajectory: {kind: leo_pass, params: {...}}   # or tle with line1/line2
turbulence: {tilt_rms_urad: 120, greenwood_hz: 25, ...}
vibration:  {modes: [[18, 90, 0.06], ...], ...}
```

Practical notes: the beacon must blink *below* the camera's Nyquist rate
(≤ 14 Hz at 30 fps) or its modulation aliases away and cannot identify it;
`acquisition_fou_deg` should cover the real initial pointing error or the
spiral may never see the beacon.

## 4. The performance report

Every quantity the problem statement names, plus the honest extras:

```
Simulation duration / frames / simulated fps / processing throughput
Acquisition time        time to the first TRACK state
Lock retention          % of frames holding a confirmed track (COAST included)
Pointing error          true optical axis vs true beacon — mean/max/p50/p95/p99
Estimate error          filter vs true beacon (always smaller; reported second)
Beacon inside FOV       the coarse stage's contract with the fine stage
Wrong-target time       frames locked on a decoy — never blended into means
Reacquisitions          count and mean recovery time; flags never-recovered
State occupancy / detections per frame / processing percentiles
```

## 5. Hardware rig (optional)

See `hardware/WIRING.md` for the ₹6–7k parts list, wiring diagrams, ESP32
firmware flashing, then:
```
python -m fsoc_pat.hil.calibrate --port COM5 --camera 0    # measures the rig
python -m fsoc_pat.hil.live --port COM5 --camera 0         # tracks for real
```

## 6. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Never leaves SEARCH | Beacon outside the FOU: raise `acquisition_fou_deg`, or check `initial_pointing_deg` against the trajectory's start. |
| Locks a star / decoy | Beacon `blink_hz` is 0 or above Nyquist — the modulation gate is inactive; set 2–10 Hz. |
| ~50% detection duty while tracking fine | Normal: a 50%-duty beacon is dark half the time; COAST bridges it. |
| Slow / below real-time | Untick *real-time pacing* to check headroom; close the ground-truth overlay; reduce `star_count`. |
| GUI blank on Linux | `QT_QPA_PLATFORM=xcb` (or `offscreen` for headless machines). |
| Live rig ignores exposure | Camera lacks manual-exposure UVC support — use the recommended ELP module, or dim the room. |
