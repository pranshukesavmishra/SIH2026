# ZeroDrift Mini-Rig Mk2 — Build Guide

> Still **not in the pitch deck**, on purpose — same reasoning as Mk1
> (`docs/rig_build_guide.md`, `docs/zero_cost_demo.md`): the PS is
> Software category, validated without hardware. Mk2 exists for one
> reason Mk1 couldn't deliver: **a real, measured accuracy number from
> physical hardware**, plus a physical demonstration of the actual
> coarse→fine architecture your numbers are built on. Build this only if
> you're aiming for the Grand Finale demo table (December 2026) — there's
> no deadline pressure driving this, so build it properly.

---
## 0. What Mk1 couldn't do, and why Mk2 fixes it

| Mk1 limitation | Root cause | Mk2 fix |
|---|---|---|
| No real accuracy number, only "it looks locked" | No ground truth measurement | Ground-truth logger (§4) |
| Open-loop pointing, ~1° resolution, gears stripped under stall | SG90 hobby servos | NEMA17 steppers + drivers (§1) |
| Only shows "a motor points at the light" | Single-stage gimbal | Second, finer stage on top (§2) |
| Can't show disturbance rejection live | No repeatable disturbance source | Vibration injector (§5) |
| Wide FOV → low angular resolution per pixel | Laptop webcam, uncontrolled exposure | Dedicated USB cam, manual exposure (§3) |

---
## 1. Coarse stage — steppers, not servos

**Why**: a stepper commanded to move N steps moves *exactly* N steps
(barring skipped steps under overload) — that's real, repeatable,
known position. A servo is open-loop PWM with no idea where it actually
ended up. This is the single change that turns "should be accurate" into
"is accurate, and here's the log."

| # | Item | Qty | ~Price | Notes |
|---|---|---|---|---|
| 1 | NEMA17 stepper motor | 2 | ₹250–350 ea | Standard 1.8°/step (200 steps/rev) |
| 2 | A4988 or TMC2209 driver | 2 | ₹80–150 ea | TMC2209 is quieter, worth the extra ₹50–70 if available |
| 3 | Pan-tilt bracket sized for NEMA17 | 1 | ₹250–450 | 3D-printed or laser-cut; search "NEMA17 pan tilt bracket" |
| 4 | 9–12V 1–2A power supply (for VMOT, separate from logic) | 1 | ₹200–350 | Steppers draw more current than Nano's USB 5V can safely supply |

**Wiring**: drivers take STEP/DIR from the Nano (2 pins each = 4 total),
logic 5V from the Nano, **motor power (VMOT) from the separate 9–12V
supply — not from the Nano** — with grounds tied common between the two
supplies. Tie each driver's EN pin LOW (always enabled) unless you want
software-controlled motor release.

**Firmware**: use the `AccelStepper` library (Arduino Library Manager)
instead of `Servo.h` for these two axes — it handles acceleration/
deceleration profiles so the coarse stage doesn't lose steps on fast
moves. See `tools/rig/rig_firmware_v2.ino` (drafted below) for the
starting point — **written but not yet bench-tested; verify step/dir
pin assignments and direction signs against your actual driver
wiring before trusting it.**

### Closed-loop upgrade — AS5600 magnetic encoders (do this if "accurate" needs to mean something)

A stepper alone is still open-loop in the sense that matters: if it ever
skips a step (stall, snag, power sag) it doesn't know it happened, and
neither do you. An **AS5600 magnetic rotary encoder** (₹150–250 each,
I2C, contactless, 12-bit → 0.088°/step resolution) on each motor shaft
gives the firmware a real, measured angle to compare against the
commanded one — this is the actual difference between "should be
accurate" and "is accurate, and the firmware knows when it isn't."

**One wrinkle**: every AS5600 shares the same fixed I2C address (0x36),
so two of them can't sit on the same bus directly. Add a **TCA9548A I2C
multiplexer breakout** (~₹100–150) — it puts each encoder on its own
channel, selected in software before each read. This is a standard,
well-documented fix, not a workaround.

| # | Item | Qty | ~Price |
|---|---|---|---|
| 4a | AS5600 magnetic encoder breakout | 2 | ₹150–250 ea |
| 4b | TCA9548A I2C multiplexer breakout | 1 | ₹100–150 |

**Be honest about what this actually buys you**: low single-digit
milliradians of *measured, repeatable* pointing with careful calibration
— a real, defensible number. It does **not** get a hobby rig anywhere
near the simulator's microradian-level figures — those are validated
against a physics model and instrumentation no hackathon budget
replicates, and the technical report already says so. The rig's job is
to demonstrate the same closed-loop *principle* honestly, not to match
the simulator digit-for-digit. Say this proactively if asked — it reads
as rigor, not a weakness, and it's the same stance `docs/defence_brief.md`
already takes on the simulator's own limitations.

## 2. Fine stage — the part that tells the real story

A second, smaller gimbal sits on top of the coarse one, carrying only
the laser, and only starts correcting once the coarse stage reports
lock. This is a direct physical analogue of your whole pitch's
justification (coarse gets the beacon in the FOV; a fine stage holds it
precisely — the 14.7%→99.3% number).

| # | Item | Qty | ~Price |
|---|---|---|---|
| 5 | MG90S metal-gear micro servo | 2 | ₹150–200 ea |
| 6 | Small secondary bracket (mount fine servos + laser on the coarse platform) | 1 | ₹100–150 |

Mechanically gear or lever this down if you can (even a longer lever arm
from the servo horn reduces angular resolution per degree of servo
rotation) — the point isn't servo precision, it's that a *second, slower,
finer* correction loop exists at all.

**Control logic** (in `rig_track.py`): once the coarse stage's blink-lock
holds steady for N frames, switch to sending small corrections to the
fine-stage servos instead of re-commanding the coarse steppers — mirrors
your simulator's state machine (search → acquire → track) but now with
two physical actuators instead of one.

## 3. Camera — controlled, not automatic

Swap the laptop's built-in webcam for a dedicated UVC USB camera you can
pin exposure/gain on via OpenCV (`cv2.CAP_PROP_EXPOSURE`,
`cv2.CAP_PROP_AUTO_EXPOSURE`, `cv2.CAP_PROP_GAIN`) — any basic UVC webcam
works, ~₹500–900. If budget-constrained, reuse the existing webcam and
skip this line item — it's a smaller win than §1/§4.

## 4. Ground-truth accuracy logger — the credibility piece

A fixed printed grid/crosshair target at a **measured** distance from the
rig. A second camera (a spare phone via any "IP webcam" app is ₹0)
watches the laser dot on the target and a simple OpenCV blob/centroid
detector logs its position against the target's known center every
frame. Convert pixel deviation → real angle:

```
error_rad ≈ deviation_mm / distance_mm      (small-angle approximation)
```

This gives you a genuine, defensible number — "held within X mrad of
target over N trials" — instead of a qualitative "it worked." Starting
script: `tools/rig/accuracy_logger.py` (drafted below) — run it as a
second process alongside `rig_track.py`, pointed at the target board.

## 5. Disturbance injector — show, don't just claim, robustness

| # | Item | Qty | ~Price |
|---|---|---|---|
| 7 | Small offset-weight vibration motor (phone-style) | 1 | ₹20–40 |
| 8 | NPN transistor (2N2222) + flyback diode (1N4148) | 1 each | ₹10–20 |

Drive it from a spare Nano digital pin through the transistor (never
straight from a digital pin — it'll draw more than the pin can source).
Mount it on the base. Toggle with a new serial command (`V1`/`V0`) so you
can switch it on mid-demo and show the tracker holding or re-acquiring
lock through induced shake — a direct physical echo of the "aliased
platform vibration" disturbance your simulator already models.

## 6. Rigid base

Swap the taped-book base for a stiff plywood or acrylic plate, coarse
stepper bolted down (not taped). Base flex corrupts your ground-truth
measurement more than it affects the visual demo, so this matters more
for Mk2 than it did for Mk1.

---
## Budget summary

| Subsystem | Cost |
|---|---|
| Coarse stage (steppers, drivers, bracket, PSU) | ₹1,000–1,550 |
| Closed-loop encoders (AS5600 ×2 + TCA9548A mux) | ₹400–650 |
| Fine stage (servos, bracket) | ₹400–550 |
| Camera (optional upgrade) | ₹0–900 |
| Ground-truth target (printed, ~₹0) + logger (reuse a phone) | ₹0–100 |
| Disturbance injector | ₹30–60 |
| Rigid base | ₹150–300 |
| **Total** | **≈ ₹1,980–4,110** |

## Phased build order (don't do it all at once)

1. **Ground-truth target + logger first** (§4) — cheapest, and it lets you
   measure the *current* Mk1 rig's real accuracy before changing anything,
   giving you a before/after number worth putting in front of judges.
2. **Coarse stepper swap + AS5600 encoders** (§1) — the actual accuracy
   fix; do these together since the encoders are what let you confirm
   the stepper swap actually worked.
3. **Rigid base** (§6) — do this alongside §2, since a wobbly base
   undermines everything above it.
4. **Fine stage** (§2) — once coarse is solid and measured.
5. **Disturbance injector** (§5) — last, it's additive polish, not a
   dependency for anything else.
6. **Camera upgrade** (§3) — optional, smallest marginal gain of the set.

## Safety
Same as Mk1: 5 mW laser never at eyes/faces, soft-limit pan/tilt ranges
in firmware. Steppers can draw enough current to warm up under stall —
don't leave the rig powered and blocked/jammed unattended.
