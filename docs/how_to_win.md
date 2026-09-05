# How to Win SIH 2026 — the playbook for team FSOC-PAT

*Written for problem statement SIH26169 (ISRO). Everything here is either
measured from the last five editions of SIH or built into your repository.*

## 1. Understand what game you are actually playing

SIH has **one winner per problem statement**, not one national winner. Your
competition is never "all of India" — it is the ~5–8 teams that reach the
Grand Finale on *your* PS. The funnel: college internal hackathon → your SPOC
nominates up to 30 teams → idea submission on the portal (capped at 500 per
PS) → a handful of teams per PS at the finale. Roughly:

    P(shortlist) ≈ 6 ÷ (ideas submitted on your PS)

You already made the strategic move: SIH26169 repels the crowd (FSOC, PAT,
coarse alignment — vocabulary that filters out most teams at paragraph one)
while being fully buildable in software. Now the goal is to be *obviously*
the best of the few who dared.

## 2. What five editions of winners have in common

1. **Completeness beats ambition.** Judges consistently reward a stable,
   working system that fully answers the brief over a grander vision with
   holes. You have this: every mandatory bullet of the PS is implemented and
   tested (69→72 automated tests).
2. **Deep-domain entries win with real engineering.** The 2023 MoD winner
   built a magnetic-anomaly-detecting VTOL, not an app. Your equivalents: a
   Cramér–Rao-limited detector, a two-path Smith predictor, SGP4 orbits.
3. **Sponsors adopt what they can use.** ISRO accepted four SIH 2024
   solutions for in-house development. Frame everything as "a testbed ISRO
   can hand to interns and researchers" — that is literally what the PS asks
   for and what your scenario-YAML + report pipeline delivers.
4. **Answer the stated problem.** Do not drift into "we also do X with
   blockchain". Every demo minute maps to a PS bullet.
5. **Winners are unglamorous and precise.** The 2025 software winner was a
   standards-mapping API. Precision reads as competence.

## 3. The idea-submission round (before 20 Sep — verify with your SPOC)

- Submit **measured results, not promises**: acquisition 1.27 s median across
  64 randomised runs, 100% acquisition probability, zero wrong locks, link
  availability 14.7%→99.3%. Almost nobody submits numbers at this stage.
- One architecture diagram (the two-loop figure in the technical report),
  one screenshot of the GUI, one table of results. Reviewers scan hundreds
  of submissions; yours must be legible in 90 seconds.
- State the honest-metrics rule explicitly ("all errors scored against
  ground truth the tracker cannot see") — it is a differentiator on its own.

## 4. The 36-hour finale — how to run it

- **Hour 0–2:** get the packaged app running on the venue machine and do a
  full demo rehearsal immediately. Never touch the environment again.
- **Keep 2–3 planned extensions in your pocket** and implement them *live*
  during the hackathon (ideas: star-field common-mode tilt estimation; an
  extra scenario the judges suggest; a parameter the jury asks about turned
  into a GUI slider). Judges score visible progress between rounds — teams
  that arrive "finished" and idle score worse than teams that visibly build.
- **Every round, lead with the live system**, not slides: GUI up, ISS pass
  running, then one slide of numbers. Offer the judges the controls — "turn
  the turbulence up yourself" is worth ten minutes of talking.
- **The power round decides close calls.** Rehearse a 3-minute and an
  8-minute version of the demo. Assign one person to drive, one to narrate;
  never both roles in one person.
- If the HIL rig is working, end every session with it: simulator on one
  screen, the real servo rig tracking the real blinking LED beside it, and
  say the sentence: "same code, real optics."

## 5. Judges' questions — the seven that will come

Memorise `docs/defence_brief.md`. The seven: why only 3 Hz bandwidth · how do
you know it's the beacon and not a star · is the AI real · why hundreds of
µrad · hardest bug · how do we know it isn't one lucky run · why does this
transfer to hardware. Each has a two-sentence answer and a deeper thread in
the brief. Volunteer the limitations before they are found — it converts a
weakness into credibility.

## 6. Numbers to say from memory

1.27 s median acquisition (100% of 64 randomised runs) · 95–99% lock ·
zero wrong locks ever · 1.6 µrad detector at high SNR (Cramér–Rao limit) ·
4.2 µrad control lag at 0.75°/s · 14.7% → 99.3% link availability ·
25–37 fps real-time · 72 tests · 497-parameter gradient-checked network.

## 7. Team roles for the finale (6 people)

| Role | Owns |
|---|---|
| Demo driver | The GUI, the scenarios, the rehearsed failure recoveries |
| Narrator/pitch | The story, the numbers, the power round |
| Systems engineer | Q&A on control/estimation (defence brief §control) |
| CV/AI engineer | Q&A on detection/network (defence brief §AI) |
| Hardware lead | The rig, the calibration story, live disturbances |
| Docs/scribe | Judge feedback log between rounds; updates the checklist slide |

Between rounds, the scribe's log becomes the "what we changed since you last
saw us" opener — judges love being listened to.

## 8. What NOT to do

- Do not add features the PS never asked for at the cost of demo stability.
- Do not show ground truth overlays in judged demos (it looks like cheating
  even when it isn't — you have the toggle for a reason).
- Do not claim precision the servos don't have; say "0.3° servos, and here's
  why that still proves transfer" (defence brief has the wording).
- Do not let the laptop sleep, auto-update, or run on battery. Bring a mouse.
