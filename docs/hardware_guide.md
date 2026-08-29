# FSOC-PAT hardware-in-the-loop rig — buying & building guide

> **STATUS: NOT PART OF THE PLAN.** The team is software-only by decision
> and the problem statement asks for validation without optical hardware.
> This file is kept for reference only — see docs/BUILD_GUIDE.md §9.

SIH 2026 · PS SIH26169 (ISRO) · companion to the software in this repository.

The rig proves one sentence to the judges: **the identical code that drives the
virtual gimbal drives real optics through real disturbances.** The problem
statement's own premise is that real PAT hardware is prohibitively expensive —
so a ₹6–7k rig that runs the same tracker is the strongest possible closing
argument. It does not reproduce the simulation's microradian precision
(hobby servos resolve ~0.3°); say that plainly in the report, never hide it.

---

## 1. Shopping list

**Budget path (~₹3,000):** items 2–8 only, with a borrowed 1080p webcam and a
phone charger for USB power. A working rig, complete demo.
**Full rig (~₹6,000–7,500):** everything below — the manual-exposure camera is
the single upgrade that matters most, because auto-exposure hunts on every
beacon blink.

Order everything at once — shipping is the long pole, parts are commodity.

### Where to buy, in order of preference
1. **robu.in** — usually cheapest for robotics parts, fast shipping.
2. **amazon.in** — camera, tripod, adapters; easy returns.
3. **flyrobo.in / quartzcomponents.com / sharvielectronics.com** — price-check alternates.

Links marked ✓ are verified product pages; the rest are live search links that
land on current listings (sort by price low→high).

| # | Item | Qty | ~₹ | Link |
|---|------|-----|-----|------|
| 1 | **USB camera, manual exposure** — ELP-USBFHD01M (2 MP, UVC) with **12 mm lens**, or any UVC cam whose datasheet says manual exposure/gain. Auto-exposure hunts on every beacon blink and ruins detection | 1 | 2,500–3,800 | [amazon.in search "ELP USB camera manual exposure"](https://www.amazon.in/s?k=ELP+USB+camera+module+manual+exposure) · fallback: [12mm M12 lens board cam](https://www.amazon.in/s?k=USB+camera+module+12mm+lens+UVC) |
| 2 | **MG996R metal-gear servo** (TowerPro or Towardpro clone) | 2 | 230 × 2 | ✓ [robu.in MG996R ₹230](https://robu.in/product/towardpro-mg996r-digital-high-torque-servo-motor/) |
| 3 | **Pan-tilt bracket kit for MG996R**, aluminium | 1 | 180–600 | ✓ [flyrobo pan-tilt kit](https://www.flyrobo.in/servo-pan-and-tilt-bracket-mount-kit-for-mg995-mg996r) · [robu.in search](https://robu.in/?s=pan+tilt+bracket+MG995) |
| 4 | **ESP32 DevKit V1** (30-pin) | 1 | 350–450 | [robu.in search "ESP32 DevKit"](https://robu.in/?s=ESP32+DevKit+V1) |
| 5 | **5 mm high-brightness LEDs**, white + red, clear lens (no diffuser) | 10 | 60–100 | [robu.in search "5mm LED high brightness"](https://robu.in/?s=5mm+LED+high+bright+white) |
| 6 | **5 V 3 A adapter + DC barrel jack breakout** | 1 | 300–400 | [robu.in search "5V 3A adapter"](https://robu.in/?s=5v+3a+power+adapter) |
| 7 | **1000 µF 16 V electrolytic cap, 220 Ω resistors ×10, 2N2222 ×3** | — | 100 | [robu.in search "1000uF capacitor"](https://robu.in/?s=1000uf+capacitor) |
| 8 | **Breadboard + jumpers (M-M, M-F)** | 1 set | 250–350 | [robu.in search "breadboard jumper kit"](https://robu.in/?s=breadboard+jumper+wire+kit) |
| 9 | **Tripod with 1/4″ screw** (any phone/camera tripod that takes the bracket) | 1 | 600–900 | [amazon.in search "tripod 1/4 inch screw"](https://www.amazon.in/s?k=camera+tripod+quarter+inch+screw) |
| 10 | **Mini tripod / clamp stand for the beacon** | 1 | 250–450 | [amazon.in search "mini tripod flexible"](https://www.amazon.in/s?k=mini+flexible+tripod) |
| 11 | **Vibration motor** (coin type, or small DC motor + a bolt as offset mass) | 2 | 60–120 | [robu.in search "vibration motor"](https://robu.in/?s=vibration+motor) |
| 12 | **ND filter** — or a dark sunglasses lens, or 2 layers of fully-exposed camera film | 1 | 0–250 | [amazon.in search "ND filter 52mm"](https://www.amazon.in/s?k=nd+filter) |

Also verified while price-checking: [pan-tilt kit at ₹176 (IndiaMART, Ahmedabad)](https://www.indiamart.com/proddetail/servo-pan-and-tilt-bracket-mount-kit-for-mg995-mg996r-fr-04-430-2852653713633.html) and [MG996R ₹230 (IndiaMART, Pune)](https://www.indiamart.com/proddetail/mg996r-towerpro-digital-high-torque-servo-motor-25064468388.html) — IndiaMART is fine for bulk/local pickup but robu/amazon are safer for single pieces.

**Camera buying rule:** before paying, confirm the listing or datasheet says
**"UVC"** and **"manual exposure"** (or the sensor is OV2710/AR0330 — both
support it). If in doubt, buy from a listing that shows the ELP model number.

**Do not buy:** SG90 servos (plastic gears, backlash), any camera described
only as a "webcam" with no sensor named, "laser pointer" beacons (a laser
speckles and is an eye hazard in a demo hall — the LED is the right beacon).

---

**Free demo props:** a hair dryer across the optical path is genuine
atmospheric turbulence; a second LED on *continuous* power is a live decoy the
tracker must ignore — and will, which is the modulation gate working in front
of the judges.

## 2. Wiring

```
5V 3A ADAPTER ──┬───────────────► servo PAN  red
                ├───────────────► servo TILT red
                ├── 1000 µF cap across +5V / GND, close to the servos
                └── GND ────┬───► servo PAN  brown
                            ├───► servo TILT brown
                            └───► ESP32 GND          ◄── COMMON GROUND, mandatory
ESP32 GPIO 13 ──────────────────► servo PAN  orange (signal)
ESP32 GPIO 12 ──────────────────► servo TILT orange (signal)
ESP32 GPIO 4  ── 220 Ω ──► 2N2222 base; collector ► LED– ; LED+ ── 220 Ω ── +5V
ESP32 USB ──────────────────────► PC (serial, 115200 baud)
USB camera ─────────────────────► PC (second USB port)
```

Rules that prevent the classic failures:
- **Never power servos from the ESP32's 5 V pin** — the brownout resets the
  board mid-demo. Servos get their own adapter; only grounds are shared.
- The 1000 µF capacitor sits physically next to the servo power rails.
- The beacon LED runs through the transistor so the ESP32 pin (12 mA limit)
  never sources LED current directly.
- The **beacon ESP32 can be a second board, or the same one** — same firmware;
  for the demo it is cleaner to put the LED on its own ESP32 at the far end of
  the room with just a power bank.

## 3. Assembly

1. Bolt the pan servo into the bracket base, tilt servo into the arm; mount
   the bracket on the tripod (1/4″ screw).
2. Zip-tie or hot-glue the camera to the tilt arm, lens axis parallel to the
   arm. Rigidity matters more than elegance — any flex is uncommanded motion.
3. Route servo wires with a strain-relief loop so panning never tugs a pin.
4. Vibration motor: bolt it to the tripod head with a cable tie. Its switch
   (or a spare GPIO) is your live "platform vibration ON" demo moment.
5. Beacon: LED + transistor + ESP32 on the mini tripod across the room
   (5–10 m). At that range a bare 5 mm LED is still an unresolved point —
   exactly like the simulation's PSF.

## 4. Software bring-up (in order)

Everything below already exists or is scheduled in the repo — nothing to
write yourself:

1. `firmware/beacon_blink/` — flash the beacon ESP32. The LEDC peripheral
   generates the exact blink frequency (default 6 Hz, 50% duty). The tracker
   *identifies* the beacon by this frequency, so it must match the scenario.
2. `firmware/pantilt/` — flash the mount ESP32. Serial protocol:
   `P<microseconds>\nT<microseconds>\n`, 50 Hz servo pulses via LEDC.
3. `python -m fsoc_pat.hil.calibrate` — automatic calibration: sweeps the
   servos, watches the beacon move in the image, and measures pixels-per-count,
   axis alignment and the real command latency. Writes `hil_calibration.yaml`.
4. `python -m fsoc_pat.hil.run` — the same CoarseAlignmentTracker, camera
   backend swapped from simulator to OpenCV capture, gimbal backend swapped
   from virtual to serial. Same GUI, same performance report.

## 5. Demo runbook (finale)

1. Start in **simulation**: LEO pass scenario, show acquisition, lock, the
   performance report generating itself.
2. Switch backend to **hardware**: same GUI now tracking the real LED across
   the room. Walk the beacon tripod around — the mount follows.
3. **Disturbance, live:** switch on the vibration motor → lock holds, error
   trace grows and recovers. Hair dryer across the line of sight → real
   turbulence. ND filter over the lens → low-SNR regime, watch coast/reacquire.
4. Kill the beacon power for two seconds → REACQUIRE spiral finds it again.
5. End on the split-screen metrics: simulation numbers beside hardware numbers.

## 6. The honest caveat (put this in the report)

MG996R resolution is ~0.3° ≈ 5,000 µrad; the simulation achieves ~100–500 µrad.
The rig therefore demonstrates **transfer** (same code, real optics, real
disturbances), not precision. The upgrade path if ever needed: NEMA17 steppers,
1/16 microstepping, 5:1 belt → ~390 µrad for roughly ₹2,000 more.
