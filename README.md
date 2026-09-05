# FSOC-PAT — virtual camera tracking testbed

Smart India Hackathon 2026 · Problem statement **SIH26169** (ISRO)
*AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile Free Space
Optical Communication (FSOC) Terminals*

Free space optical links carry gigabit rates on a beam so narrow that a small
angular error breaks the link entirely. Before a fine steering mirror can take
over, a **coarse alignment** stage has to find the remote terminal's beacon and
hold it inside the camera's field of view. Developing those algorithms on real
hardware needs expensive cameras, pan-tilt mechanisms and optics — so this
project builds the whole thing in software instead.

Everything here is self-contained. No dataset, no network, no instrument: a run
is fully described by a YAML scenario and a seed, and the same pair always
produces the same frames.

## What is here

The complete coarse alignment system, end to end:

| Layer | Contents |
|---|---|
| Simulation | Scene (sky/cloud/stars/clutter/glint), six trajectory kinds + SGP4/TLE, turbulence with Greenwood dynamics, aliased platform vibration, rate/latency-limited gimbal, full detector noise chain |
| Tracker | Top-hat → matched filter → CFAR → sub-pixel detection (Cramér–Rao-limited), IMM estimation, four-stream target identification (persistence, consistency, direction prior, Goertzel modulation gate), spiral acquisition, five-state lock machine |
| AI | 497-parameter spatio-temporal patch network, from-scratch NumPy with finite-difference-verified gradients; beats the Goertzel on short windows (AUC 0.957 vs 0.900), honestly framed |
| Control | Two-path Smith predictor: proportional on the model comparison, integral on the measured optical error; 4.2 µrad steady lag at 0.75°/s against 40 ms of command latency |
| Evaluation | Performance reports (every PS-mandated quantity + honest extras), Monte Carlo campaign, link-budget closure with a modelled fine stage, demo video export |
| Delivery | PySide6 GUI, PyInstaller standalone build, headless CLI, 69 tests |
| Hardware | ESP32 beacon + pan-tilt firmware, serial/USB drivers behind the simulation's own interfaces, measured calibration, live tracking loop (`hardware/WIRING.md`) |

Headline numbers (all disturbances on, scored against ground truth the
tracker never sees): acquisition ≈ 1 s, lock retention 95–99 %, zero decoy
locks across every scenario, and on a real SGP4-propagated ISS pass the
tracked error stream closes a modelled optical link **99.3 %** of the time
with the fine stage versus **14.7 %** without — the two-stage architecture
justifying itself numerically.

Docs: `docs/technical_report.md` · `docs/user_manual.md` · `docs/defence_brief.md`

```sh
python -m fsoc_pat.gui.app                              # operator GUI
python -m fsoc_pat.runner scenarios/iss_pass.yaml       # headless + report
python -m fsoc_pat.campaign scenarios/leo_pass_nominal.yaml -n 64
python -m fsoc_pat.video scenarios/iss_pass.yaml --out demo.mp4
packaging/build.sh   |   packaging\build.bat           # standalone app
```

## Quick start

```sh
python -m venv .venv
.venv/Scripts/activate            # Windows;  source .venv/bin/activate on Linux
pip install -e ".[dev]"
pytest
```

## What the simulator models

The point of a testbed is that it is *hard in the ways the real problem is hard*.
Four things here are usually left out of a toy simulator, and each one breaks a
naive tracker:

- **Gimbal rate and acceleration limits, plus command latency.** The mount cannot
  follow a step command, and pointing commands take effect tens of milliseconds
  after they are issued. High-gain loops that look fine without this oscillate
  with it.
- **Atmospheric turbulence.** Correlated tip/tilt jitter whose correlation time
  comes from the Greenwood frequency, so raising the frequency makes the jitter
  *harder to follow*, not merely larger. Partly common-mode across the field, so
  the star background is a usable reference — but only partly.
- **Platform vibration.** Sharp resonances integrated as driven damped
  oscillators, deliberately aliased by the frame rate, exactly as real hardware
  aliases them.
- **Confusers.** Clutter, stars and sun glint are rendered through the *same*
  point spread function as the beacon, so a detector cannot cheat by learning a
  rendering difference. Decoy targets are labelled in ground truth but look
  identical in the image.

Ground truth records both the geometric direction of each target and its
*apparent* position after turbulence, so tracking error can be scored against
either without ambiguity. `true_pointing` and `reported_pointing` are kept
separate throughout — scoring against the encoders would flatter the tracker.

## Scenarios

| File | What it exercises |
|---|---|
| `static_easy.yaml` | Acquisition sanity check. No turbulence, no vibration, bright target. |
| `leo_pass_nominal.yaml` | 550 km pass culminating at 55°. Beacon is faint at acquisition (SNR ≈ 6) and bright at culmination (SNR ≈ 39), while the gimbal slews fastest exactly when the target is brightest. |
| `turbulence_hard.yaml` | 400 µrad tip/tilt at 60 Hz with heavy scintillation. Tests whether the filter rejects jitter instead of chasing it. |
| `decoy_field.yaml` | Three decoys crossing the field on independent paths, plus dense clutter and frequent glint. Locking onto the wrong source scores zero. |
| `uav_relay.yaml` | Air-to-ground link to a manoeuvring UAV: slower than a satellite, but with sharp direction changes the filter must not lag. |

## Layout

```
src/fsoc_pat/
  config.py       scenario definition, YAML load/save, deterministic seeding
  geometry.py     angle <-> pixel projection for a pan-tilt camera
  optics.py       point spread function splatting, shared by every source
  scene.py        sky, cloud, terrain, stars, clutter, sun glint
  beacon.py       targets and their trajectories, including LEO pass geometry
  camera.py       rate/acceleration-limited gimbal, detector and noise model
  disturbance.py  atmospheric turbulence and platform vibration
  simulator.py    the loop, and the ground truth it emits
scenarios/        five baseline scenarios
tests/            40 tests covering geometry, config, trajectories, gimbal, loop
analysis/         how this problem statement was chosen (see analysis/README.md)
```

## Performance

Roughly **50 fps** at 640×480 on one core — faster than the 30 fps frame rate it
simulates, so a Monte Carlo campaign of a thousand runs is practical.

## Team ZeroDrift

Smart India Hackathon 2026 · Jabalpur Engineering College · PS **SIH26169** (ISRO, Software, Smart Automation)

| Role | Name |
|---|---|
| Team Leader | Aryan Singh |
| Member | Pranshu Mishra |
| Member | Aashna Verma |
| Member | Vivek Rajput |
| Member | Palak Uikey |
| Member | Shivanand Sahu |
| Faculty Mentor | Dr. Jitendra Singh Thakur — Associate Professor & HOD, CSE |
