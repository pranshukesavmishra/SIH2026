# ZeroDrift — 4:30 Finals Script (software + physical rig, 6 speakers)

Adapted from `stage_script.md` (the 5:00 selection-round script) — same voice,
same honesty rules, compressed by 30s, with the physical rig added as new
content rather than bolted on.

**Setup before you are called:**
- Shivanand: laptop open, `leo_pass_nominal` loaded, real-time ON, ground-truth
  OFF, PAUSED and ready.
- Pranshu: the physical rig on the table, **already powered on**, pan/tilt
  centred, laser off. Do NOT cold-boot it live — every second spent waiting
  for a servo to wake up is a second you don't have.
- Aryan: has the beacon phone (strobe app running, screen dim/locked so it
  doesn't wake mid-pitch) in a pocket, ready to hold up on cue.
- **Backup: a 10-second screen-recorded clip of the rig locking on, cued up
  and ready to play in one tap.** Given how much tonight's session was about
  ambient light breaking the live camera lock, do not bet 45 seconds of a
  4:30 final on a conference hall's ceiling lights. If the live lock doesn't
  land in ~6 seconds, Pranshu says the line marked **[IF SLOW]** below and
  the backup clip plays instead. No apology, no pause.
- Stand in speaking order, left to right. Speak slowly — slow feels
  professional, and every segment below is timed assuming it.

---
## 0:00 – 0:25 · ARYAN (lead) — the hook
> Good morning judges. Team ZeroDrift, ISRO problem 26169. Two terminals,
> kilometres apart, must point exactly into each other's eyes — while both
> shake, and one moves at 27,000 kilometres an hour. That's laser
> communication: enormous bandwidth, but if the pointing fails for an
> instant, the link is gone. ISRO asked for that pointing brain, proven in
> software. We built it — and we brought it to life in hardware too.

**[DO: Aryan nods to Shivanand → Shivanand presses START]**

## 0:25 – 1:00 · VIVEK — what is on the screen
> This is not an animation — it's a physics simulation of the real sky:
> stars, clouds, atmospheric shaking, and one blinking beacon riding a real
> ISS orbit from real orbital data. Our tracker sees only these noisy camera
> pixels. Watch — searching… found it… **LOCKED**. About one second, from
> completely cold.

## 1:00 – 1:35 · AASHNA — how it thinks
> How does it know that's the beacon, not a star? Identity isn't
> brightness — it's the blink. Four times a second, like a handshake. A star
> can be brighter, but it can't blink right, so it scores zero. Our own
> 497-parameter neural network double-checks every lock. Across 64 random
> tests: zero wrong-target locks.

## 1:35 – 2:10 · SHIVANAND — the live torture test
> Now I make its life difficult.
> **[DO: drag turbulence to maximum]**
> Heavy atmospheric shaking — the beacon is dancing. The tracker bends, but
> doesn't break.
> **[DO: switch ground truth ON]**
> The green marker is where the beacon truly was, the whole time it couldn't
> see. It was right. We only reveal the answer after tracking, never during.

## 2:10 – 2:55 · PRANSHU — the physical rig
> Software convinces engineers. This convinces everyone.
> **[DO: Aryan holds up the strobing phone, 1–2 metres from the rig]**
> Same exact principle — find the identity blink, ignore everything
> brighter — now running on a two-hundred-rupee servo and a laser, live.
> **[DO: watch for LOCKED + laser on the phone. If it takes more than ~6s:]**
>
> **[IF SLOW]** "— and here it is locking in our lab, same rig, same code."
> **[DO: tap play on the backup clip, keep talking over it]**
>
> One honest note: this hobby servo has about a degree of mechanical play —
> seventeen thousand microradians. Our algorithm, in software, measures
> **198** microradians — nearly a hundred times finer than this servo can
> physically move. That gap is exactly *why* real optical terminals use two
> stages: coarse alignment, then a fine steering mirror. This rig proves the
> coarse stage. On purpose.

## 2:55 – 3:35 · PALAK — the proof
> Every number here is measured, not promised. Acquisition: 1.27 seconds.
> Lock held 98.3 percent of the pass. Beacon in-frame 100 percent of the
> time. 73 automated tests, all passing. Every figure regenerates from one
> command — any judge can re-run it and get our exact answer. We don't ask
> for trust. We show proof — and it's all on GitHub and a live website you
> can open on your own phone right now.

## 3:35 – 4:30 · ARYAN — the close
> Why does this matter? Without coarse alignment, this optical link closes
> 14.7 percent of the time. With ZeroDrift — 99.3 percent. That's the
> difference between a demo and a usable link.
>
> The same brain that ran that simulation just pointed a real laser on this
> table, a minute ago, in front of you. It scales beyond satellites — UAVs,
> ships, ground vehicles, anything that moves and has to find its partner
> fast, without carrying optics it can't afford. ISRO asked for this proven
> in software, without costly hardware. We answered that — and then we
> proved the same principle again, in metal and glass, because we wanted
> you to see it, not just read it.
>
> We didn't bring a promise. We brought a working system, twice — in
> software, and in your hands. Thank you — we welcome your questions.

---
## Q&A — who answers what (one step forward, answer, step back)
| Topic | Anchor | One-liner to build on |
|---|---|---|
| Beacon, blink, physics, orbits | **Vivek** | "4 Hz because a 30 fps camera can see it cleanly without aliasing." |
| AI, wrong-target, detection | **Aashna** | "Gate is classical and strict; AI adds confidence — 0.957 vs 0.900 classical, benchmarked, not assumed." |
| Delay, control, mount | **Shivanand** | "Commands act 40 ms late, so a Smith predictor aims where the target *will* be." |
| The physical rig, its precision | **Pranshu** | "Coarse stage only, by design — the servo's own mechanical limit is ~17,000 µrad; the algorithm measures 198. A fine mirror closes that gap in a real terminal." |
| Code, tests, app, website | **Pranshu** | "All open source; the site replays a logged run of this same engine." |
| Numbers, reproducibility | **Palak** | "Every figure comes from a logged run in the repo — I can show the file." |
| Already-existing tech (NASA/ESA/Starlink/Astrogate) | **Aryan** | "Those are the eye and the arm — flight optics. We built the brain that decides where to point, testable in software before that hardware exists." |
| Why software-only in the deck, hardware roadmap | **Aryan** | "The PS asks for validation without optical hardware — the rig is a bonus proof of the same principle, not the deliverable." |

**µrad question (someone will ask):** ANYONE: "One microradian tilts the
beam about a millimetre per kilometre. Our median error, 198 µrad, keeps the
beacon deep inside the field for a fine-steering stage to take over."

## Golden rules
1. Never say "should work / basically / obviously." Say **"measured / watch / here is the proof."**
2. Rig doesn't lock fast enough → Pranshu says the **[IF SLOW]** line, backup clip plays, keep talking. No apology.
3. Software misbehaves → Shivanand: "let me show the recorded run of this same engine" → opens the Netlify link.
4. Unknown question → Aryan: "Honest answer — we haven't measured that yet; here's what we do know…" Honesty scores. Bluffing eliminates.
5. Rehearse with a phone timer **at least 3 times, including the rig handoff** — that handoff is the one part that's never been rehearsed under time pressure before tonight.
6. Smile at LOCKED, on the screen and on the table. Those are your product's two best moments.
