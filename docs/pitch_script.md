# ZeroDrift — internal round pitch script

Three minutes, mapped slide-by-slide to the submitted deck. Written to be spoken,
not read: practise until it sounds like talking. The presenter owns the words;
everyone else owns one question area each (bottom of this file).

## The 30-second version (use when time is cut short)

> Laser communication can carry a thousand times more data than radio, but the
> beam is so narrow that a tiny pointing error kills the link. ISRO asked for the
> "eyes and neck" of such a terminal — find the beacon, lock on, never let go —
> built entirely in software. We didn't propose it. **We built it.** It locks on
> in about a second, holds through turbulence and fake lights, and was never
> fooled once in sixty-four randomised trials. Everything is open, measured, and
> reproducible on this laptop.

## The 3-minute pitch

**[Slide 1 — 15 s]**
> Good morning. We are Team ZeroDrift, and we picked ISRO's problem statement
> 26169 — coarse alignment for free-space optical communication. In one line:
> we built the eyes and neck of a laser communication terminal.

**[Slide 2 — 45 s]**
> Imagine two towers talking by torch light instead of radio — that's how
> satellite internet will work, because light carries far more data. The catch:
> the beam is as narrow as a laser pen. Shake slightly, and the call drops.
> So before anything can be transmitted, a camera on a motorised mount must FIND
> the other terminal's blinking beacon and keep FACING it — through shimmering
> air, vibration, and a sky full of stars that look exactly like the beacon.
> ISRO asked for this entire stage in software, because testing on real optics
> costs lakhs. This screenshot is not a mock-up — it is our system, live,
> holding lock. And these three numbers are measured, not projected: locked in
> 1.1 seconds, held 98.8 % of the time, and across 64 randomised trials it never
> once chased the wrong light.

**[Slide 3 — 45 s]**
> How it works, in one breath: a physics-honest virtual world generates the sky —
> real turbulence statistics, real vibration, real satellite orbits. Every frame
> flows through this pipeline: detect every bright dot, identify the beacon by
> its secret blink rhythm — stars don't blink, so they score zero — estimate its
> motion with a Kalman filter, and steer the camera slightly AHEAD of the target,
> like a goalkeeper diving where the ball WILL be. The state machine below is the
> system's autopilot: search in a spiral, acquire, track, coast through blinks,
> and re-acquire on its own. We verified it recovers even when started five
> degrees off-target among decoys.

**[Slide 4 — 30 s]**
> Is it feasible? It's finished. Seventy-three automated tests pass. A 64-run
> Monte-Carlo campaign under randomised turbulence, brightness and vibration:
> one hundred percent acquisition, zero wrong locks. The worst single run —
> a half-brightness beacon under double turbulence — still locked in under
> three seconds. Every number regenerates from one command.

**[Slide 5 — 30 s]**
> Why it matters: sovereign FSOC development for India without importing optical
> test benches; any student or lab can develop pointing algorithms on a normal
> laptop; and the one number that justifies the whole architecture — with our
> coarse stage feeding a fine mirror, the optical link stays closed 99.3 % of a
> tracked ISS pass, versus 14.7 % without it.

**[Slide 6 — 15 s]**
> Everything — source, tests, reports, demo video — is public on GitHub and
> reproducible today. We're Team ZeroDrift. Zero drift is the mission. Thank you.

## Likely faculty questions (internal round level)

**"Did you really build all this?"**
Yes — and we can prove it in thirty seconds: clone the repository, run one
command, watch it acquire live. 5,500 lines of documented Python, 73 tests, CI.

**"Where is the AI?"** *(the PS says AI-assisted)*
Two places. A neural network we wrote from scratch — no framework — that
verifies a tracked object really is the beacon; it beats the classical method on
short observation windows (AUC 0.957 vs 0.900). Plus classical AI: Kalman/IMM
estimation and CFAR detection, benchmarked head-to-head so we know what each
earns.

**"Why no hardware?"**
The problem statement is Software category, and its stated purpose is developing
these algorithms WITHOUT expensive optics. Our contribution is exactly that: the
entire validation loop needs nothing but a laptop.

**"What's novel here?"**
The identification gate. Everyone can detect bright dots; the hard part is never
chasing the wrong one. We identify the beacon by its blink signature as a hard
gate — a sun glint can be brighter and steadier than the beacon and still fail.
Zero wrong locks in every test we ran.

**"What are the limitations?"** *(answer honestly — it scores points)*
Three we state ourselves: pointing error under heavy turbulence sits at the
physical floor the disturbance itself sets; sharp unannounced manoeuvres cost
about a second of recovery, which no causal predictor can avoid; and the
simulator, however honest, is still a model — the fine-steering stage behind
us is modelled, not implemented.

**"What next if selected?"**
Harden the finale demo, extend the Monte-Carlo envelope, and prepare live
disturbance toggles so judges can try to break it themselves.

## Role split for Q&A

| Area | Owner |
|---|---|
| Physics & simulator (turbulence, orbits, noise) | member 1 |
| Detection & identification (CFAR, blink gate, AI verifier) | member 2 |
| Tracking & control (Kalman/IMM, Smith predictor, state machine) | member 3 |
| Results & reproducibility (tests, Monte-Carlo, reports) | member 4 |
| Demo driving (runs the GUI live) | member 5 |
| Pitch & impact story | team lead |

Assign names in the first team meeting; each owner reads their section of
`docs/defence_brief.md` — it has the deeper answers for ISRO-level judges.
