# ZeroDrift — 5-Minute Selection Script (6 speakers)

**Setup before you are called:** Shivanand opens the app, loads
`leo_pass_nominal`, real-time ON, ground-truth OFF, ready but PAUSED.
Phone with the Netlify link open as backup. Everyone stands in speaking
order, left to right. Speak slowly — slow feels professional.

---
## 0:00 – 0:40 · ARYAN (lead) — the hook
> Good morning judges. We are Team ZeroDrift, and we solved ISRO problem
> 26169. Imagine two torches, kilometres apart, that must point exactly
> into each other's eyes — while both are shaking and one is moving at
> 27,000 km/h. That is laser communication. The data speed is amazing,
> but if the pointing fails, everything fails. ISRO asked for this
> pointing brain to be built and proven in software. We built it.
> Completely. And you will watch it work, live, right now.

**[DO: Aryan nods to Shivanand → Shivanand presses START]**

## 0:40 – 1:25 · VIVEK — what is on the screen
> What you see is not an animation. It is a physical simulation of the
> real sky — stars, clouds, atmospheric shaking, and one blinking light
> called the beacon, riding a real ISS orbit computed from real orbital
> data. Our tracker sees only these noisy camera pixels — nothing else.
> Watch the left panel… it is searching… found it… and LOCKED. That took
> about one second, from completely cold.

## 1:25 – 2:10 · AASHNA — how it thinks
> How does it know that dot is the beacon, and not a star? Simple idea:
> identity is not brightness — identity is the blink. The beacon blinks
> four times per second, like a secret handshake. A star can be brighter,
> but it can never blink right, so it scores zero and is rejected. Then
> our own small neural network — 497 parameters, trained by us, not
> downloaded — double-checks every lock. In 64 random test runs, it
> locked a wrong light exactly zero times.

## 2:10 – 2:50 · SHIVANAND — the live torture test (speaks while driving)
> Let me make its life difficult.
> **[DO: drag turbulence to maximum]**
> That is heavy atmospheric shaking — see the beacon dancing. The tracker
> bends… but does not break.
> **[DO: wait 3 seconds, point at the error graph]**
> And here is the honest part. This whole time it never saw the answer.
> **[DO: switch ground truth ON]**
> The green marker is where the beacon truly was. Our tracker was right —
> and we only reveal the answer key after tracking, never during.

## 2:50 – 3:30 · PRANSHU — the engineering
> This is finished engineering, not a concept. Five thousand lines of
> open-source Python. It processes nine megapixels every second and uses
> only twenty of every thirty-three milliseconds — on a normal laptop, no
> GPU, no cloud. Everything is public: our GitHub repository, a one-click
> desktop app, and a live web console — zerodrift-fsoc-pat.netlify.app —
> where you can replay this exact run on your own phone, right now.

## 3:30 – 4:05 · PALAK — the proof
> And we measured everything the problem statement asks. Acquisition in
> 1.27 seconds. Lock held 98.3 percent of the pass. The beacon stayed
> inside the camera's view 100 percent of the time. 73 automated tests,
> all passing. And every number regenerates from one command — any judge
> can re-run our results and get the same answer. We do not ask for
> trust. We show proof.

## 4:05 – 5:00 · ARYAN — the close
> Why does this matter? Without coarse alignment, this optical link works
> only 14.7 percent of the time. With ZeroDrift — 99.3 percent. That is
> the difference between a demo and a usable link. Today it aligns a
> simulated ISRO terminal; the same brain works for UAVs, ships and
> ground stations. Judges — the problem asked for algorithms proven in
> software without costly optics. We are the team that did not bring a
> promise. We brought the working system. Thank you — we welcome your
> questions.

---
## Q&A — who answers what (one step forward, answer, step back)
| Topic | Anchor | One-liner to build on |
|---|---|---|
| Beacon, blink, physics, orbits | **Vivek** | "The beacon is the terminal's identity light; 4 Hz because the camera's 30 fps can see it cleanly." |
| AI, wrong-target, detection | **Aashna** | "Gate is classical and strict; AI adds confidence — benchmarked 0.957 vs 0.900 classical." |
| Delay, control, mount | **Shivanand** | "Commands act 40 ms late, so a Smith predictor aims where the target WILL be." |
| Code, tests, app, website | **Pranshu** | "All open source; the site replays a logged run of this same engine." |
| Numbers, reproducibility | **Palak** | "Every figure comes from a logged run in the repo — I can show the file." |
| Why software-only, roadmap, anything unclear | **Aryan** | "The PS asks for validation without optical hardware — that is the point of a virtual test-range." |

**µrad question (someone will ask):** ANYONE: "One micro-radian tilts the
beam about 1 millimetre per kilometre. Our median error, 198 µrad, keeps
the beacon deep inside the field for the fine-steering stage."

## Golden rules
1. Never say "should work / basically / obviously." Say **"measured / watch / here is the proof."**
2. If the app misbehaves: Shivanand says "let me show the recorded run of this same engine" → opens the Netlify link. No apologies, keep talking.
3. If asked something nobody knows: Aryan: "Honest answer — we haven't measured that yet; here is what we do know…" Honesty scores. Bluffing eliminates.
4. Rehearse 3 times with a phone timer. Target 4:45 — questions eat the rest.
5. Smile at LOCKED. It's your product's best moment.
