# ZeroDrift — Project Memory (handoff for any Claude / teammate)

> Paste this file (or point the session at it) to continue work in a fresh
> Claude session with zero context loss. Updated: 2026-08-29.

## Memory graph

```mermaid
graph TD
  PS[SIH26169 · ISRO<br>AI virtual-camera tracking for<br>FSOC coarse alignment<br>Theme: Smart Automation · Software] --> ENGINE
  PS --> DECK
  subgraph Product
    ENGINE[Python engine src/fsoc_pat/<br>5,500+ lines · 73/73 tests<br>sim → perception → IMM → Smith → control] --> GUI[PySide6 console<br>fsoc_pat.gui.app]
    ENGINE --> EXE[PyInstaller one-click app<br>packaging/build.sh|.bat]
    ENGINE --> REC[Recordings tools/export_telemetry.py<br>docs/media/telemetry_run.json ISS 45s<br>telemetry_turbulence.json · telemetry_decoys.json]
    REC --> SITE[Web replay docs/demo.html<br>hosted: zerodrift-fsoc-pat.netlify.app<br>REPLAYS recordings, simulates nothing]
    REC --> CHART[Slide-2 chart make_chart2.py]
  end
  subgraph Submission
    DECK[Official 6-slide deck<br>docs/submission/ZeroDrift_SIH26169.pdf+pptx<br>strict template · validate.py all-pass] --> S2[S2 chips+chart = ISS run<br>1.27s · 98.3% · 198 µrad · 0/64]
    DECK --> S3[S3 winning-deck layout<br>tech-stack tiles + flow diagram]
    DECK --> S6[S6 links: repo · live demo ·<br>7 scholar refs · compare table]
  end
  subgraph Team
    ROSTER[team_private/roster.md GITIGNORED<br>never push - personal data] 
    TEAMDECK[docs/team/ZeroDrift_Team_Explainer<br>beacon explainer + judge Q&A + roles]
    GUIDE[docs/zero_cost_demo.md +<br>tools/webcam_beacon_demo.py ₹0 demo]
  end
  DECK -.consistency rule.-> REC
```

## Identity
- Team **ZeroDrift**, Jabalpur Engineering College. Lead: Aryan Singh. 6 members, 2 female. Mentor: Dr Jitendra Singh Thakur (HOD CSE). Contact details live ONLY in `team_private/roster.md` (gitignored — never push).
- Problem: **SIH26169** (ISRO) — AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile FSOC Terminals. Category Software, Theme Smart Automation. Team ID: assigned by portal after SPOC nomination (deck shows "—").

## Repos & pushing
- origin `pranshukesavmishra/SIH2026`, branch `claude/sih-problem-selection-w3p3o4` (draft PR #1 tracks it).
- mirror `pranshukesavmishra/SIH-2026` — push same branch to `main`: `git push mirror claude/sih-problem-selection-w3p3o4:main`. Always push BOTH.
- Commit footer: Co-Authored-By Claude + Claude-Session link (see git log). No model IDs in pushed artifacts.

## The one law of this project
**Every number in any user-facing artifact must trace to a shipped measurement.** Canonical sources:
| Claim | Source |
|---|---|
| 1.27 s acq · 98.3% lock · 198 µrad p50 · 100% in-FOV | `docs/media/telemetry_run.json` (ISS 45 s, seed 20261169 — the run the site replays & slide-2 chart plots) |
| 0/64 wrong locks · worst 4.0 s / 91.6% | `runs/mc-leo/summary.json` |
| ≈20 ms of 33 ms budget | `runs/iss_pass.report.json` p50 |
| 99.3% vs 14.7% availability | `src/fsoc_pat/linkbudget.py` |
| AUC 0.957 vs 0.900 | `docs/technical_report.md` |
| 73 tests | `pytest` |
An audit workflow enforced this (2026-08-29): fixed 14 ms→20 ms, IMM 0.3 s→reworded, chips 1.1/98.8→1.27/98.3, faster-than-real-time→8–21 ms of budget, worst-case relabel, chart margin, caption run-neutral.

## Deck build system (scratchpad — recreate if container lost)
`/tmp/.../scratchpad/ppt/`: `template.pptx` (official, MD5 90028af7…), `build_deck.py` (single source; rebuilds deck from template each run), `make_chart2.py` (chart from telemetry_run.json), `make_logo2.py`, `make_sidelabel.py`, `validate.py`. Flow: edit build_deck.py → run → validate.py → soffice → pdftoppm → eyeball renders. Outputs copied to `docs/submission/`. If scratchpad is gone: these five scripts must be re-created or recovered from session history; deck pptx in docs/submission still opens fine in PowerPoint for manual edits.

## Hosted demo
- `docs/demo.html` = honest replay dashboard (3 scenario recordings, play/scrub, every chart from JSON). Deploy to Netlify: drag-drop the whole `docs/` folder at app.netlify.com (site name zerodrift-fsoc-pat) so `demo.html` + `media/*.json` ship together; or connect the repo, publish dir `docs`, homepage = index.html, dashboard at `/demo.html`.
- The older Antigravity-built page invented numbers (couldn't acquire in hard-turbulence because its JS was fake). Real engine: hard turbulence acq 1.27 s, 94.3% lock (`telemetry_turbulence.json`).

## Positioning answers (asked & settled)
- **Software or website?** It IS software (Python engine + GUI + one-click EXE). The website is only a replay viewer for reach. Stage demo = desktop app; judges' phones = website.
- **Hardware:** none, by decision; deck mentions none; PS wants zero-optical-hardware validation. ₹0 physical option: `docs/zero_cost_demo.md` + `tools/webcam_beacon_demo.py` (blinking phone flashlight vs webcam — identity-by-modulation principle).
- Progress Stage on forms: 5. Deck naming: `ZeroDrift_SIH26169.pdf` ≤10 MB.

## Open items
- User must verify Netlify site matches recordings after redeploy (sandbox cannot reach netlify.app / github.io / reddit / youtube — egress blocked).
- Team rehearsal: `docs/team/ZeroDrift_Team_Explainer.pdf`, `docs/pitch_script.md`, `docs/defence_brief.md`.
- Watch PS 26169 pick-count on portal ~10–14 Sept; national idea deadline ~20 Sept 2026.
