# Hardware Purchase Guide — FSOC-PAT demonstration rig

Two tiers. Buy Tier 1 now (shipping is the long pole); add Tier 2 if budget
allows. Sources: Robu.in, Amazon.in, ThinkRobotics, local electronics market.

## Tier 1 — Core rig (~₹3,000–3,500): everything needed for a working demo

| # | Item | Spec that matters | Qty | ~₹ |
|---|---|---|---|---|
| 1 | MG996R servos | METAL gear (SG90 plastic gears have backlash that ruins pointing) | 2 | 700 |
| 2 | Aluminium pan-tilt bracket | Fits MG996R; 1/4" tripod mount hole | 1 | 600 |
| 3 | ESP32 DevKit V1 | Any 30/38-pin clone; one drives servos, one drives the beacon | 2 | 900 |
| 4 | 5 mm high-brightness LEDs (white + red) | Bare, no diffuser — must stay a point source at 5–10 m | 10 | 100 |
| 5 | 5 V 3 A adapter + DC barrel jack | Servos NEVER powered from the ESP32 5V pin | 1 | 350 |
| 6 | 1000 µF 16 V capacitor, 220 Ω resistors, 2N2222 | Cap absorbs servo current spikes that reset the ESP32 | — | 100 |
| 7 | Breadboard + jumper set (M-M, M-F) | | 1 | 300 |
| 8 | Basic USB webcam (1080p) | Works for the demo; see Tier 2 for the better option | 1 | (500–1,000 used / borrow) |

With a borrowed webcam and phone-charger USB power, Tier 1 lands ≈ ₹3,000.

## Tier 2 — Upgrades (~₹3,500–4,500 more): what makes the demo convincing

| # | Item | Why | ~₹ |
|---|---|---|---|
| 9 | ELP USB camera, manual exposure, 12 mm lens (ELP-USBFHD01M family) | Auto-exposure hunts on every beacon blink and ruins point-target detection; the 12 mm lens gives the narrow FOV the simulation models | 3,500 |
| 10 | Camera tripod (1/4" screw) | Stable base for the pan-tilt head | 800 |
| 11 | Vibration motor (or DC motor + offset weight) | Bolt to the mount; switch on live: real platform vibration, tracker holds | 100 |
| 12 | ND filter or dark sunglasses lens | Forces the low-SNR regime where the detector earns its keep | 200 |
| 13 | Mini tripod / clamp for the beacon | | 400 |

Free demo props: a hair dryer across the optical path is genuine atmospheric
turbulence; a second LED on continuous power is a live decoy the tracker must
ignore (and will — that is the modulation gate working).

## Wiring, flashing, bring-up

Everything is in the repository: `hardware/WIRING.md` (diagrams and the
bring-up order), `hardware/firmware/beacon_esp32/` and
`hardware/firmware/gimbal_esp32/` (flash with Arduino IDE + the ESP32Servo
library), then:

```
python -m fsoc_pat.hil.calibrate --port COM5 --camera 0   # measures the rig
python -m fsoc_pat.hil.live      --port COM5 --camera 0   # tracks for real
```

## The honest sentence about precision (memorise)

"MG996R servos resolve about 0.3°, so the rig does not reproduce the
simulation's micro-radian precision — it proves the identical software
survives real optics, real vibration and real turbulence, which is exactly
the transfer question the problem statement raises. A ₹2,000 upgrade to
belt-reduced steppers reaches ~0.02° if we want precision later."
