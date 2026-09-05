# FSOC-PAT hardware rig — wiring and bring-up

Total parts cost ≈ ₹6,000–7,500. The rig does not reproduce the simulation's
precision (an MG996R resolves ~0.3°); it proves the *identical software*
drives real optics through real disturbances — which is the point the problem
statement itself makes about hardware cost.

## Beacon unit (fixed, across the room)
```
ESP32 #1 GPIO 4 ──[220 Ω]──▶ LED anode
LED cathode ───────────────▶ GND
USB power from any phone charger.
```
Flash `firmware/beacon_esp32/`. Over serial: `F 4.0` sets 4 Hz, `D 50` duty.

## Tracker unit (on the tripod)
```
ESP32 #2 GPIO 18 ──▶ pan  MG996R signal (orange)
ESP32 #2 GPIO 19 ──▶ tilt MG996R signal (orange)
5 V 3 A adapter + ──▶ both servo reds ── 1000 µF cap to GND near the servos
adapter −, servo browns, ESP32 GND ──▶ common ground (essential)
USB camera on the tilt platform, cable strain-relieved.
```
Flash `firmware/gimbal_esp32/` (needs the ESP32Servo library).
**Never power servos from the ESP32's 5 V pin** — the brownout resets look
like firmware bugs and are not.

## Bring-up order
1. Beacon on, room lights low, LED visibly blinking.
2. `python -m fsoc_pat.hil.calibrate --port COM5 --camera 0`
   — measures plate scale, servo scale and true command latency;
   writes `hardware/calibration.yaml`.
3. `python -m fsoc_pat.hil.live --port COM5 --camera 0`
   — the full acquisition + tracking loop, printing the same performance
   report as the simulator.

## Demo disturbances
- Bolt the vibration motor to the camera platform; switch it on mid-track.
- Hair dryer across the optical path = real turbulence.
- ND filter / sunglasses lens over the lens = low-SNR regime.
- A second LED on continuous (no blink) = a live decoy the tracker must ignore.
