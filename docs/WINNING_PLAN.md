# ZeroDrift — Plan to win SIH26169

*Written 18 Sept 2026, against an audit of what is actually in this repo
today — not against what we assume is here. Effort estimates are in
person-days for a team of six.*

---
## 0. The two competitions, and why they need different work

We are not in one contest. We are in two, sequentially, and they are
judged on completely different things.

| | **Round 1 — Idea submission** | **Round 2 — Grand Finale** |
|---|---|---|
| When | Now → **30 Sept 2026** (hard) | ~Dec 2026, offline, if shortlisted |
| Field | Up to **500 ideas** on this PS | **4–5 teams** per PS |
| Judged on | The 6-page PDF, alone | Working software + 5 deliverables + live defence |
| What wins | Clarity, credibility, backing | Depth, robustness under attack, honesty |

Round 1 is a **document** problem. Round 2 is an **engineering** problem.
Everything below is ordered so that Round 1 work finishes first, because
missing 30 Sept means Round 2 never happens.

---
## 1. Where we actually stand

The engine is far more complete than a typical shortlisted entry.
Against the PS's own required capabilities:

| PS requires the software to… | Status |
|---|---|
| Generate a configurable virtual environment | ✅ `simulator.py`, `scene.py`, YAML configs |
| Generate one or more moving targets | ✅ multi-beacon (`cfg.beacons`), decoys flagged |
| Implement a movable virtual camera | ✅ `camera.py` — slew limits, latency, FOV |
| Detect the target beacon automatically | ✅ `detection.py` — top-hat + CFAR |
| Track the beacon continuously using CV | ✅ `tracking.py`, `estimation.py` — Kalman/IMM |
| Control and reposition the virtual camera | ✅ `control.py` — Smith predictor, state machine |
| Introduce turbulence, vibration, motion, noise | ✅ `disturbance.py`, live-adjustable in GUI |
| Display performance and statistics in real time | ✅ PySide6 + pyqtgraph console |

And against the five mandatory deliverables:

| Deliverable | Status | Gap |
|---|---|---|
| **Software Application** (standalone executable) | ❌ **BROKEN** | `packaging/fsoc-pat.spec` referenced by both build scripts **does not exist** |
| **Source Code** (documented, modular) | ✅ | 36 modules, 12 test files, 73 tests |
| **Technical Report** (10–15 pages) | ⚠️ | ~2,491 words ≈ 6–8 pages. Likely **short of the floor** |
| **User Manual** (install, operate, configure, GUI) | ⚠️ | ~957 words. Thin against what the PS enumerates |
| **Performance Log** (auto-generated) | ✅ | `PerformanceReport` mirrors the PS list field-for-field |

**Read that honestly:** we are one missing file and two short documents
away from full compliance. That is a very strong position — and it means
our effort should go into *depth*, not catching up.

---
## 2. TIER 0 — Disqualification risk. Nothing else starts until these land.

| # | Task | Effort | Why it is Tier 0 |
|---|---|---|---|
| 0.1 | Write `packaging/fsoc-pat.spec`, verify `build.sh` and `build.bat` both produce a running binary on Windows **and** Linux | 0.5 d | A **mandatory deliverable** is currently unbuildable |
| 0.2 | Technical report → 12–14 pages: add architecture diagrams, test methodology, per-module description, failure analysis, future work | 2 d | PS states 10–15 pages. Under-length invites a compliance mark-down |
| 0.3 | User manual → cover installation (all OS), first run, **every** config parameter, full GUI walkthrough, troubleshooting | 1.5 d | PS enumerates four sections; we thinly cover two |
| 0.4 | **Compliance matrix** — one row per sentence of the PS, mapped to the artefact and line that satisfies it | 0.5 d | Turns "we think we comply" into a document a judge can audit |
| 0.5 | Deck fixes (98.3→99.3, page number, bar scale, econ panel, one-line problem, Team ID) | 0.5 d | See `docs/PROJECT_STATE.md` §4 |
| 0.6 | **Submit on the portal** — FCFS, 500 ideas per PS, then it freezes | — | Miss this and everything above is wasted |

> **0.6 is the single highest-risk item in this document.** It is not
> engineering work and it is not in our control once the counter fills.
> Do it the day the SPOC finishes nomination.

---
## 3. TIER 1 — What actually wins the finale

At the finale, all 4–5 remaining teams will have "a tracker that works."
Differentiation comes from surviving what the judges invent on the spot,
and from measuring ourselves more honestly than anyone else.

### 1.1 "Break It" mode — hand the judge the controls *(3 d)*
`gui/controls.py` already exposes turbulence RMS, Greenwood frequency and
vibration, bound live to the running config. Extend it into a deliberate
adversarial panel:

- Beacon brightness ×0.1–3.0, live
- Inject decoys on demand (1, 3, 10) and sun-glint at a chosen bearing
- Frame-dropout rate slider; sensor-noise multiplier
- Target manoeuvre injector — sudden slew the filter was never told about
- **One "CHAOS" preset** that turns everything to worst-case at once
- A persistent HUD: still-locked / error / time-since-acquire

*Why it wins:* every other team demos a happy path they control. We say
"turn the knobs yourself." It also maps directly onto the PS clause
"generate and introduce disturbances… display statistics in real time."

### 1.2 Auto-generated performance report *(2 d)*
`PerformanceReport` already holds everything. Render it, one click, into a
timestamped **PDF/HTML** with plots — error-vs-time, state occupancy,
detection duty, acquisition histogram — not just JSON.

*Why it wins:* the PS asks for a "Performance Log." Handing over a
formatted report instead of a data file reads as product, not homework.

### 1.3 Scenario library expansion *(3 d)*
Six scenarios today (`iss_pass`, `leo_pass_nominal`, `decoy_field`,
`turbulence_hard`, `uav_relay`, `static_easy`). Add the ones that prove
generality:

- **GEO station-keeping** — near-stationary, long dwell
- **Ship-to-shore maritime** — platform roll/pitch as the dominant disturbance
- **Daytime with sun in FOV** — the hardest realistic rejection case
- **Zenith / keyhole pass** — az-rate singularity, where naive mounts fail
- **Two-beacon handover** — one sets, another rises; must not cross-lock

*Why it wins:* the PS names "satellites, UAVs." Showing maritime and GEO
says the architecture generalises rather than being tuned to one case.

### 1.4 AI depth — remove our own stated limitation *(4 d)*
Today: a 497-parameter NumPy verifier, gradient-checked, AUC 0.957 vs
0.900 classical on short windows. Its documented weakness is that it only
knows the 4 Hz training distribution.

- **Adaptive blink-frequency estimation** — infer the beacon's rate from
  the data rather than assuming 4 Hz, then verify at the inferred rate
- **Calibrated uncertainty** on the verifier output, so the state machine
  can refuse a marginal lock rather than guessing
- Extend the head-to-head benchmark table: classical vs NN across window
  length, SNR and frequency — publish where each *loses*

*Why it wins:* "Where is the AI?" is the question ISRO judges always ask.
The answer that lands is a benchmark table showing exactly what the
network earns *and where the classical method beats it*.

### 1.5 Multi-target simultaneous tracking *(3 d)*
Multi-beacon generation exists; make the tracker hold **two independent
confirmed tracks** at once with correct association, and demonstrate a
clean handover. Directly serves the PS's "one or more moving targets."

---
## 4. TIER 2 — The unfair advantage: prove it leaves the simulator

`src/fsoc_pat/hil/` (`rig.py`, `calibrate.py`, `live.py`) is already
scaffolded for hardware-in-the-loop.

**The demo that no software-category team can match:** the *same* tracker
binary, unchanged, driving the physical Mk2 rig — webcam in, real servos
out, real laser on a real target — running beside the simulation on the
same screen.

- Build the Mk2 rig (spec and costed at ₹4,480–4,550 in `docs/rig_mk2_build_guide.md`) — **5 d, in parallel, not on the software critical path**
- Prove interface parity: detector/tracker/controller cannot tell webcam+servos from the virtual world
- Report measured physical accuracy honestly (low single-digit mrad — *not* the simulator's µrad)

*Why it wins:* it answers "will this transfer to hardware?" with a
demonstration instead of a promise — while staying inside the software
category, because the deliverable is still the software.

**Also Tier 2:** the optional 3–5 minute demo video (1.5 d). Optional in
the PS, but every judge watches it.

---
## 5. TIER 3 — Finale execution

The finale evaluates in **multiple layers** — rotating juries, several
checkpoints. Plan for repetition, not one big reveal.

- **Progressive demo:** each checkpoint shows something the last did not
  (checkpoint 1 nominal lock → 2 chaos mode → 3 HIL rig → 4 full report)
- **One-page leave-behind** per jury: problem, four numbers, the link
- **Failure drills:** rehearse camera-not-found, exe crash, no internet,
  projector at 1024×768. Each needs a 10-second recovery
- **Q&A ownership:** one member owns each of physics / detection /
  control / results / demo, per `docs/pitch_script.md`
- **Two laptops, both fully set up.** Never one.

---
## 6. Equipment list

Software category — none of this is required to comply. It is for the
finale demo.

| Item | Purpose | Cost |
|---|---|---|
| Mk2 rig (full BOM in `rig_mk2_build_guide.md`) | The HIL demonstration | ₹4,480–4,550 |
| Second laptop, fully configured | Backup — non-negotiable | owned |
| USB webcam (manual exposure) | HIL camera | being sourced |
| Phone + tripod | Beacon + referee camera | owned |
| HDMI / USB-C adapter set | Projector roulette | ₹300–600 |
| Extension board | Venue sockets are scarce; needs desk approval | ₹300–500 |
| Power bank | Long judging queues | owned |
| Printed one-pagers (×10) | Leave-behind per jury | ₹100 |

---
## 7. Sequencing

```
NOW ──► 30 SEPT          TIER 0 only. Deck, documents, executable, SUBMIT.
                         Nothing in Tier 1 starts until 0.6 is done.

OCT ──► shortlist        TIER 1.1, 1.2, 1.4  (Break It mode, auto-report,
                         AI depth) — the three with the best
                         impact-to-effort ratio.
                         Mk2 rig build runs in parallel, off the
                         critical path.

NOV                      TIER 1.3, 1.5 (scenarios, multi-target),
                         TIER 2 (HIL parity, demo video).
                         Freeze features 2 weeks before the finale.

DEC ──► finale           TIER 3 only. Rehearsal, drills, no new code.
```

**Total Tier 1 + 2 ≈ 21 person-days of software.** Across six people
over October–November that is comfortable — *provided* Tier 0 is closed
in September and we hold the feature freeze.

---
## 8. The one thing that decides this

Every finalist will claim their tracker works. What we can claim, and
prove on the spot, is a narrower and much stronger thing:

> **We measure ourselves against ground truth the tracker cannot see,
> we publish where our method loses, and you can try to break it
> yourself right now.**

That posture is already the house style in `docs/defence_brief.md`. Every
item in Tier 1 exists to make it demonstrable rather than assertable.
Protect it — one inflated number (see the 98.3 / 99.3 incident in
`PROJECT_STATE.md`) costs more credibility than any feature buys.
