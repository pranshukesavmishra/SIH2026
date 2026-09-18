# ZeroDrift — Project State

**The portable memory.** Any new session, on any account, in any model:
clone this repo and read this file first. It is the authority on what is
done, what is open, and which number is the real one.

Last updated: 2026-09-18 (deck v3 rebuilt + packaging spec landed)

---
## 1. Identity

| | |
|---|---|
| Team | **ZeroDrift** — Jabalpur Engineering College |
| Problem Statement | **SIH26169**, set by **ISRO** (Dept. of Space) |
| Title | AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile FSOC Terminals |
| Theme / Category | Smart Automation / **Software** |
| Repo | `github.com/pranshukesavmishra/SIH-2026` |
| Live replay console | `zerodrift-fsoc-pat.netlify.app` |
| Status | 2nd Runner-Up, institute internal round (11 Sept 2026) |

**Team (6, locked — changing members disqualifies the nomination):**
Aryan Singh (leader, CSE 3rd yr) · Pranshu Mishra (Mechatronics 3rd) ·
Aashna Verma (IPE 2nd) · Palak Uikey (ECE 2nd) · Vivek Rajput (IT 3rd) ·
Shivanand Sahu (IT 3rd).

---
## 2. Canonical numbers — check here before writing any number anywhere

Deck, report, pitch and chat must all agree with this table. A number
not on this list, or not traceable to its source, does not go in front
of a judge.

| Value | What it actually means | Source of truth |
|---|---|---|
| **1.27 s** | Median acquisition time | `runs/mc-leo/summary.json` → `acquisition_time_s.p50` |
| **2.77 s** | p95 acquisition | same → `.p95` |
| **4.0 s** | Worst-case acquisition | same → `.max` |
| **100%** | Acquisition probability, all runs | same → `acquisition_probability` |
| **97.5%** | Lock retention, **campaign median** | same → `lock_retention_pct.p50` |
| **94.5%** | Lock retention p5 | same → `.p5` |
| **91.6%** | Lock retention, **campaign worst** | same → `.min` |
| **98.3%** | Lock retention, **featured demo run only** | `docs/media/telemetry_run.json` |
| **768 µrad** | Median of p95 pointing error | same → `pointing_error_p95_urad.p50` |
| **198 µrad** | Median pointing error, demo run | replay console / demo run |
| **0 / 64** | Runs with any decoy lock | same → `runs_with_any_decoy_lock` |
| **99.3%** | Link closure **with modelled fine stage** | `docs/technical_report.md` L281–283 |
| **14.7%** | Link closure, **coarse stage alone** | `docs/technical_report.md` L281 |
| **3.1 dB** | Mean link margin | `docs/technical_report.md` L283 |
| **AUC 0.957 vs 0.900** | NN verifier vs classical, short window | `docs/defence_brief.md` |
| **83 / 83** | Automated tests passing | CI |
| **8–21 ms** | Tracker time per 33 ms frame, 2 cores | engine benchmark |
| **₹0.22** | Electricity, full 64-run campaign | `docs/economic_feasibility.md` |
| **207×** | Throughput vs hardware bench | `docs/economic_feasibility.md` |

> ⚠️ **The known trap:** 98.3% (demo-run lock retention) and 99.3%
> (link closure) get confused. They are different metrics. Fixed in the
> v3 deck (18 Sept): slide 5 now carries 99.3% with bars to scale.

---
## 3. Where things live

```
docs/
  technical_report.md      10–15pp deliverable — the numbers' origin
  economic_feasibility.md  cost arithmetic, all assumptions stated
  defence_brief.md         deep Q&A prep for judges
  pitch_script.md          3-min pitch + role split
  PROJECT_STATE.md         ← you are here
  rig_build_guide.md       Mk1 physical rig (built, tilt servo dead)
  rig_mk2_build_guide.md   Mk2 spec — steppers + encoders, ₹4.5k, not built
  zero_cost_demo.md        ₹0 webcam fallback demo
  user_manual.md           deliverable
  submission/              the deck PDF
  media/                   telemetry, panels, assets
src/fsoc_pat/              the engine (detector, tracker, control, ai, gui)
tools/rig/                 firmware + tracker + accuracy logger
runs/mc-leo/summary.json   the 64-run campaign — source of most numbers
packaging/                 build scripts + fsoc-pat.spec (spec-based build, cv2-Qt conflict fixed)
```

---
## 4. Open threads

**Submission (hard deadline 30 Sept 2026)**
- [ ] Rename consent letter to `ZeroDrift_Consentletter.docx`, upload to the Google Form
- [ ] Idea submission on the SIH portal — **first-come-first-served, 500 ideas per PS**, do not wait for the deadline
- [ ] Team ID still blank on deck slide 1

**Deck fixes — ALL DONE in v3 (18 Sept, `docs/submission/ZeroDrift_SIH26169.pptx/pdf`,
rebuilt from the official template + the team's 10-Sept graphics; source +
assets: `docs/submission/deck_src/` — `python build_deck_v3.py` regenerates it)**
- [x] Slide 5: 98.3% → 99.3% (matches the technical report), bars drawn to scale
- [x] Slide 2: 98.3% chip relabelled "lock held · featured demo run"; 1.27 s chip
      relabelled "median acquisition · 64 runs" (also fixes the "Acquistion" typo)
- [x] Slide 2: page number correct (2)
- [x] Economic feasibility panel on slide 5 (capital-cost card + ₹0.22 / 207× / ₹15 cr)
- [x] Slides 1 & 2 lead with the problem in one line
- [ ] Team ID still blank on slide 1 — fill when SIH portal issues it

**Software**
- [x] `packaging/fsoc-pat.spec` committed (root cause: `.gitignore`'s `*.spec` was
      hiding it — negated now). Both build scripts and CI use the spec; it bundles
      `scenarios/` + `models/`, strips cv2's bundled Qt (which otherwise shadows
      PySide6's platform plugins and kills the GUI on launch). Verified on Linux:
      headless report runs, GUI event loop starts offscreen.
- [x] Accuracy work landed on branch `accuracy-work` (PR #3, 18 Sept): adaptive
      blink-frequency estimation (measured ±0.1 Hz, blind mode when no frequency
      is agreed, pairs with the beacon unit's `F<hz>` command), "measured blink"
      row in the ZD-1 console, temperature-calibrated verifier with a
      validation-derived abstain band (vote stays raw-scale — see the commit
      for the measured regression that forced that), and a 24-condition
      classical-vs-NN benchmark in `docs/benchmark_identification.md`
      including the 21 cells the classical method wins. 102/102 tests; the
      64-run campaign guard re-ran on the final code: **0/64 decoy locks
      confirmed**. Canonical decimals above refreshed from that rerun; the
      p50 1.27 s, max 4.0 s, min 91.6 % and 0/64 are unchanged.

**Mk2 live software — DONE (18 Sept, `mk2-live-software` branch)**
- [x] The REAL engine on real camera frames: `hil/engine.py` runs
      `CoarseAlignmentTracker` (CFAR, blink gate + adaptive frequency, IMM,
      Smith predictor, AI verifier) on live/video/array frames — the
      "identical code drives real optics" claim is now true by construction.
- [x] `hil/mk2.py`: v2-protocol driver (P/T steps, p/t servo degrees, L, V)
      with software safety envelope + dry-run mode. `hil/serve.py`: one
      process = engine + SSE telemetry + MJPEG + dashboard; `docs/rig.html`
      is the live ZD-1 console (truth-referenced tiles deliberately absent —
      no ground truth exists off-simulation). `tools/rig/beacon_firmware.ino`
      implements the F/B/M beacon protocol. Run guide: `docs/rig_live.md`.
- [x] Verified end-to-end with a synthetic beacon video: TRACK lock on the
      blinking source (brighter steady lamp refused), measured blink 3.0 Hz,
      8–10 ms/frame. 7 new tests; suite green.
- [ ] On real hardware still to do: measure FOV + plate scale
      (`hil.calibrate`), verify stepper direction signs, then
      `python -m fsoc_pat.hil.serve --port-serial auto`.

**Browser live demo (live.html) — motion-hardened (18 Sept, `live-tracker-v2`)**
- [x] Fast-moving beacon stays locked: velocity learned from measured position
      deltas (true target velocity, dark phases included), feed-forward
      prediction scaled by the real inter-frame gap, speed/blind-time-grown
      search disc + ROI + tether, ROI-wide recapture once blind past a normal
      dark phase, lag-corrected + overshoot-capped map re-tether. All bounded
      by the modulation map's 3x drop budget, so identity still rules.
- [x] Honest COASTING state (amber, dashed ring) whenever the lock is carried
      by prediction — no more green LOCKED with blink 0.00 on a stale ring.
- [x] MARGIN vs NOISE floored (max ~50x; the six-digit readout is gone).
- [x] RIG CAMERA VIEW button: probes localhost:8765, opens the full-engine
      rig console (hil/serve.py) when running, explains how to start it when not.
- [x] Verified end-to-end in headless Chromium with a synthetic camera
      (`tools/web/test_live_motion.mjs` + `fake_cam.js`): 5/6 runs fully clean,
      worst case = temporary lag with honest COASTING and recovery; zero lock
      losses, zero decoy captures across all runs.

**Live demo tracking rewrite — v3 (18 Sept, `live-tracker-v2`)**
- [x] v2's velocity feed-forward was a runaway: it integrated velocity into
      BOTH `pos` and `anchor` every frame, then re-projected the anchor by half
      a window again in `analyse()`, under a cap proportional to the drift it
      was meant to limit. Positive feedback — the ring flew off the beacon and
      hovered over blank wall (brightness 10) still claiming a lock. Reported
      from the field, reproduced, fixed at the design level.
- [x] New rule: **prediction steers the search, measurement moves the ring.**
      `pos` never advances without something the camera measured, except a
      bounded coast through a known blink-off (stops at 6 frames, tether-
      clamped, never written back to the anchor).
- [x] Search sized to real positional uncertainty (speed x blind time); lead
      capped in pixels so a decelerating hand can't fling it past a stopped
      beacon; velocity survives the dark phase but is clamped and reversal-
      adaptive; recapture picks the NEAREST lit thing, not the brightest
      (a torch and a lamp both saturate — brightness is a coin flip the lamp
      kept winning).
- [x] Map-silence budget is now conditional on the silence being EXPLAINED by
      recent motion (its window needs ~1.3 s of stillness to rebuild), with
      absolute ceilings. `ZeroDriftDrop()` in the console reports why any lock
      was abandoned.
- [x] Readouts hold the last real measurement between confirmations instead of
      flickering "blink 0.00" on a healthy lock.
- [x] Verified: **10/10 headless runs pass** against a synthetic HANDHELD path
      (6 fast flicks, reversals, stop-and-go, plus a steady decoy lamp).
      Median ring-to-beacon error 3–6 px while lit; zero lock losses; **zero
      decoy captures**. `tools/web/test_live_motion.mjs`.
- Guard rails found the hard way, do not "optimise" away: the 70 px search
  ceiling (90 px swallowed the lamp), the wide-search-must-not-be-anchored
  finding (the anchor is what goes stale in motion), and the tight-primary-disc
  experiment (starved the follower, 0/8).

**Rig (no deadline — Grand Finale, Dec 2026 if selected)**
- [ ] Mk1 tilt servo dead (stripped gears); replacement also not moving — free-spin test never reported back
- [ ] Mk2: priced at ₹4,480–4,550; ABS enclosure size still unconfirmed
- [ ] Camera+laser combined head — diagram not yet drawn

**Outreach**
- [ ] DRDO chairman brief — message drafted, send status unknown

---
## 5. Git topology — how not to clobber anything

```
origin/main ──────●  (team's PowerPoint + site work)
                   \
                    ●──●──●──●──●──●──●──●──●  claude/session-01f6…h9tr19
                                             (9 commits: docs, deck rebuilds,
                                              rig specs, economic feasibility)
```

- The session branch **contains everything on main** — no divergence, a
  clean fast-forward. Merging is safe whenever you want it.
- Nothing is lost if a session dies: everything is pushed.

### Working from a second account / a different model, safely

1. **Clone, don't guess.** `git clone` the repo and read this file.
2. **Branch first.** `git checkout -b <something-descriptive>` off `main`
   or off the session branch. Never commit straight onto someone else's
   branch.
3. **Never force-push** a branch you did not create. Never
   `git push --force` to `main`.
4. **Merge through a PR**, so both sides can see the diff before it lands.
5. **Update this file** when you finish something, and commit it. This
   file is the handoff — if it is stale, the next session starts blind.

Two sessions on two accounts can work at the same time without conflict
as long as each stays on its own branch and touches different files.
Same file, two branches → resolve at merge, never by force-push.
