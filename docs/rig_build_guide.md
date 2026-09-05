# ZeroDrift Mini-Rig — Build Guide (under ₹700)

> **NOT in the pitch deck, on purpose.** The problem statement asks for
> validation *without* optical hardware, and our pitch is software-only.
> This rig is an optional table-side principle demo: a webcam finds a
> blinking phone flashlight and two tiny motors physically steer a laser
> onto it — the same closed loop our simulator runs, made touchable.
> If you build nothing, the ₹0 webcam demo (`docs/zero_cost_demo.md`)
> already works.

---
## 1. What you are building

**Phone flashlight blinking at 4 Hz** (the beacon) → **laptop webcam**
sees it → our Python script identifies it *by its blink* (steady lights
rejected) → sends angles to an **Arduino Nano** → two **SG90 servos**
turn a **laser pointer** until its dot sits on/near the phone.
Camera → detect → identify → steer → repeat, 15–30 times a second.
That is coarse alignment, physically.

## 2. Shopping list (checked against Indian sellers, Aug 2026)

| # | Item | Qty | Typical price | Where |
|---|------|-----|--------------|-------|
| 1 | SG90 9g micro servo | 2 | ₹60–90 each | robu.in, robocraze.com, zbotic.in, local electronics market |
| 2 | Pan-tilt bracket kit for SG90 (2-axis) | 1 | ₹80–170 | robocraze.com "Servo Pan Tilt Setup", robu.in |
| 3 | Arduino Nano clone (CH340, soldered pins) | 1 | ₹210–260 | robu.in, hubtronics.in, dnatechindia.com (₹219), Amazon.in |
| 4 | KY-008 / 650 nm 5 V laser module (5 mW) | 1 | ₹40–90 | robu.in "Laser Module 650nm 5V" |
| 5 | Female-female jumper wires (20 pc) | 1 | ₹60–90 | any of the above |
| 6 | Mini-USB cable (Nano uses mini-USB!) | 1 | ₹40–80 | often lying at home — check first |
| — | Webcam | — | **₹0** — laptop's built-in works | — |
| — | Beacon | — | **₹0** — any phone + free "strobe light" app at ~4 Hz | — |
| | **TOTAL** | | **≈ ₹550–700** | one robu.in / robocraze order ships it all |

Tools: small Phillips screwdriver, tape/blu-tack, scissors. **No soldering.**
Buying tips: order servos+bracket from ONE seller so the screws match;
"CH340" in the Nano listing matters (that's the USB chip the driver needs).

## 3. Assembly — 30 minutes

1. **Bracket:** assemble the pan-tilt kit per its diagram: one servo sits
   flat (pan), the second mounts sideways on top (tilt). Don't fully
   tighten the servo-horn screws yet.
2. **Laser:** tape / blu-tack the KY-008 onto the top (tilt) platform,
   lens pointing forward.
3. **Wiring** (jumper wires, no soldering — servo plugs are 3-pin):
   ```
   Pan  servo:  orange→D9    red→5V    brown→GND
   Tilt servo:  orange→D10   red→5V    brown→GND
   Laser KY-008:  S→D7       middle→5V  −→GND
   ```
   All three share the Nano's 5V and GND pins (use the bracket's wires or
   split with jumpers). Two SG90s on USB power is fine for this light load.
4. **Base:** tape the bracket to a heavy book so it can't tip.

## 4. Flash the Arduino — 10 minutes

1. Install Arduino IDE (arduino.cc). Windows: if the board isn't detected,
   install the **CH340 driver** (search "CH340 driver windows").
2. Open `tools/rig/rig_firmware.ino` from our repo.
3. Tools → Board: **Arduino Nano** · Processor: **ATmega328P (Old Bootloader)**
   (clone boards usually need Old Bootloader) · Port: the COM/tty that appeared.
4. Upload (→ arrow). Both servos snap to centre — that's success.

## 5. Run it — 5 minutes

```
pip install opencv-python numpy pyserial
python tools/rig/rig_track.py --port COM5        # Windows (see IDE for port)
python tools/rig/rig_track.py --port /dev/ttyUSB0  # Linux/Mac
```
1. Put the rig next to the laptop, both facing the room.
2. Second teammate stands 3–5 m away, phone strobing at ~4 Hz, facing the webcam.
3. Window shows **LOCKED** + green ring → laser turns on and walks onto the target.
4. **If the dot runs AWAY from the phone**: your servo orientation is
   mirrored — open `rig_track.py` and flip the sign of one gain
   (change `- args.gain*ex` to `+`, or the tilt line). One-character fix.
5. Keys: arrows = trim · c = centre · l = laser toggle · q = quit.

## 6. Calibration for the demo table
- Start with `--gain 0.02`. Wobbly/oscillating → lower it (0.01). Too slow → raise (0.04).
- Camera and laser should sit close together (parallax stays small).
- Demo in normal indoor light; a very bright window behind the target can
  out-shine the phone — face away from windows.

## 7. What to SAY while it runs
> "Brightness is not identity — modulation is. The steady tube-light is
> brighter than the phone, but it doesn't blink at the agreed 4 Hz, so it
> scores zero and is rejected — same hard gate our simulator uses, where
> the tracker locked a wrong target 0 times in 64 randomised runs. And
> the loop you're watching — see, identify, steer — is the same loop our
> virtual terminal runs at 30 fps against a satellite."

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| Nano not detected | Install CH340 driver; try another cable (data cable, not charge-only) |
| Upload error | Processor → ATmega328P (Old Bootloader) |
| Servos jitter constantly | Lower `--gain`; check GND shared between Nano and servos |
| Never says LOCKED | Phone strobe closer to 4 Hz; move closer; dim room lights |
| Locks onto tube-light | It won't stay locked — score decays; if it does, raise threshold 0.35→0.5 in script |
| Laser dot far from phone | Normal small offset (parallax); mount laser closer to webcam |

## 9. Video & reading references (real links, verified via search)
- YouTube — [OpenCV object tracking · Arduino laser pan/tilt](https://www.youtube.com/watch?v=1X-xxgN4n8M)
- YouTube — [Face tracking with OpenCV, Python, Arduino & pan-tilt servos](https://www.youtube.com/watch?v=X3D3L67CFC4)
  (their loop is identical to ours — they centre a face, we centre a blinking beacon)
- Written — [PyImageSearch pan/tilt tracking tutorial](https://pyimagesearch.com/2019/04/01/pan-tilt-face-tracking-with-a-raspberry-pi-and-opencv/)
- Written — [Top Tech Boy: pan/tilt servo object tracking in OpenCV](https://toptechboy.com/using-a-pan-tilt-camera-servo-to-track-an-object-of-interest-in-opencv/)
- Code reference — [aju22/Object-Tracking-OpenCV_Arduino on GitHub](https://github.com/aju22/Object-Tracking-OpenCV_Arduino)

## 10. Safety
5 mW red laser: never at eyes or faces; aim across a table at a paper
target zone; firmware soft-limits (pan 20–160°, tilt 40–140°) keep it from
sweeping the room — don't remove them.
