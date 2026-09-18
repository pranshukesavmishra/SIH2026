# Economic feasibility — the arithmetic

*Every figure below is either measured from a shipped artefact in this
repo, quoted from the problem statement itself, or an indicative market
range that is explicitly labelled as such. Nothing here is asserted
without a stated basis — if a judge asks "where does that number come
from", the answer is on this page.*

---
## 1. The baseline we are replacing

The problem statement (SIH26169, ISRO) states the cost barrier itself:

> "Developing and testing such algorithms on real hardware requires
> expensive cameras, pan-tilt mechanisms, and optical components &
> equipment. A software based virtual camera tracking provides an
> inexpensive and accessible platform for algorithm development and
> learning."

So the economic case is not ours to invent — the problem setter already
states it. What follows quantifies it.

### Indicative cost of a hardware PAT test bench

Scientific/industrial-grade instrumentation, market ranges. These are
**indicative tiers, not vendor quotes** — exact pricing varies with
specification, vendor and import duty.

| Component | Why it is needed | Indicative cost |
|---|---|---|
| Global-shutter machine-vision camera + lens | Frame capture without rolling-shutter skew | ₹1.5–4 L |
| Motorised pan/tilt gimbal with encoders | The coarse stage under test | ₹3–12 L |
| Fast steering mirror (fine stage) | The stage our coarse output feeds | ₹5–20 L |
| Beacon laser source + collimation optics | The target being tracked | ₹1–3 L |
| Vibration-isolated optical table | Otherwise the bench's own noise dominates | ₹2–5 L |
| Turbulence emulation (phase plate / hot-air cell) | Reproducing atmospheric conditions | ₹1–5 L |
| Control electronics, DAQ, synchronisation | Closing the loop in real time | ₹1–2 L |
| **Total** | | **≈ ₹15–50 lakh** |

This excludes lab space, alignment labour, calibration, and maintenance.

---
## 2. What ZeroDrift costs to run — measured, not estimated

**Capital cost: ₹0.** The engine runs on a normal laptop, CPU-only, no
GPU, no cloud, no purchased dataset. Every team member already owns the
hardware it needs.

**Electricity per validation campaign**, derived from the real campaign
log in `runs/mc-leo/summary.json`:

```
wall_time_s          = 2,229 s          (measured, 64-run campaign)
                     = 0.619 hours
laptop draw          = 45 W             (assumption: sustained 2-core load,
                                         typical range 30–65 W)
energy               = 45 W × 0.619 h   = 27.9 Wh = 0.0279 kWh
tariff               = ₹8 / kWh         (assumption: Indian domestic slab,
                                         deliberately taken at the high end)

cost of a complete 64-run Monte Carlo campaign
                     = 0.0279 × 8       = ₹0.22
```

**A full 64-run randomised validation campaign costs about 22 paise of
electricity.** Per individual run: 2,229 / 64 = 34.8 s, ≈ ₹0.0035.

---
## 3. Throughput — the cost that is not money

The campaign sweeps 64 randomised conditions (turbulence 0.5–2×, beacon
brightness 0.4–2.5×, vibration 0.5–2×, plus randomised initial pointing
error and seed).

On hardware, each of those conditions requires physical reconfiguration,
re-alignment and re-calibration. At an **optimistic** two hours per
condition:

```
hardware   : 64 conditions × 2 h   = 128 h ≈ 16 working days (lab time only)
ZeroDrift  : 64 conditions          = 0.62 h = 37 minutes
speed-up   : 128 / 0.62             ≈ 207×
```

Same 64-condition sweep: **37 minutes versus roughly 16 working days**,
before any lab scheduling is counted.

---
## 4. Scaling — where the number becomes national

The decisive economic argument is not one bench, it is *N* benches.

| | Hardware benches | ZeroDrift |
|---|---|---|
| 1 researcher | ₹15–50 L | ₹0 |
| 1 lab (say 5 parallel setups) | ₹75 L – ₹2.5 Cr | ₹0 |
| 100 students / researchers working independently | **≈ ₹15 crore** (at the ₹15 L low end) | **₹0** |
| Recurring cost | Calibration, maintenance, consumables, lab energy | Electricity only (₹0.22 per campaign) |

Equipping a hundred people to develop and benchmark FSOC pointing
algorithms costs roughly ₹15 crore in hardware, or nothing in software.
That is the difference between a capability that lives in two or three
national labs and one that any engineering college in the country can
teach.

---
## 5. Honest limits of this argument

State these before a judge finds them:

- **Simulation does not replace final hardware qualification.** A flight
  terminal must still be tested on real optics. ZeroDrift removes the
  cost from the *algorithm development and benchmarking* loop — which is
  precisely the scope the problem statement asks for — not from
  end-of-line qualification.
- **The hardware ranges are indicative tiers, not quotations.** The
  method is what matters: even at the lowest end of every row, the
  capital gap is four to five orders of magnitude against ₹0.
- **The 2 h/condition hardware figure is an assumption**, chosen
  optimistically in hardware's favour. Real reconfiguration of a
  turbulence cell and re-alignment of a beam path typically takes longer.

---
## 6. The four numbers for the deck

| Claim | Value | Basis |
|---|---|---|
| Capital cost to start | **₹0** vs ₹15–50 lakh | This page, §1–2 |
| Full 64-run validation campaign | **₹0.22** of electricity | Measured `wall_time_s`, §2 |
| Same 64-condition sweep | **37 min vs ~16 working days** (≈207×) | §3 |
| Equipping 100 researchers | **₹0** vs ≈ ₹15 crore | §4 |
