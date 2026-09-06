# ZeroDrift — ONLINE Jury Round Script (6 Sept, 11:08–11:15 AM)

**Format:** Google Meet · 5 min PPT + 2 min Q&A · **max 3 members** ·
cameras ON · admitted 2 min early from lobby.

## Who joins (recommended 3)
1. **Aryan** — presents slides 1, 2, 5, 6 + leads Q&A.
2. **Shivanand** — shares screen, drives the deck AND the live console; presents slides 3–4.
3. **Aashna** — AI/detection Q&A anchor (the PS title says "AI-Based" — that question WILL come).

Vivek, Pranshu, Palak: on WhatsApp standby during the slot to feed
answers if needed — but the 3 on-call should not visibly read.

## Tonight's checklist (do not skip)
- [ ] `ZeroDrift_SIH26169.pdf` open on **BOTH** laptops (Aryan's + Shivanand's) — the rule they gave.
- [ ] Desktop app installed & tested on Shivanand's laptop; `leo_pass_nominal` loads.
- [ ] zerodrift-fsoc-pat.netlify.app opened and tested on both laptops + one phone.
- [ ] Practise the screen-share handover once: Shivanand drops → Aryan shares within 10 seconds, keeps talking.
- [ ] Quiet room, phone hotspot as internet backup, join lobby by 10:55.

---
## The 5 minutes (target 4:30 — online transitions eat time)

**0:00 · ARYAN (slide 1 → 2):**
> Good morning judges, Team ZeroDrift, ISRO problem 26169. Imagine two
> torches, kilometres apart, that must point exactly into each other's
> eyes — while shaking, and while one moves at 27,000 km/h. That is
> laser communication, and pointing is the part that fails. ISRO asked
> for this pointing brain proven in software. We built it — completely —
> and every number on this slide is measured, not projected: lock in
> 1.27 seconds, held 98.3 percent, zero wrong locks in 64 random runs.
> The screenshot is our live console — the link on our last slide opens
> it on your phone. Shivanand, take us inside.

**1:20 · SHIVANAND (slide 3, the pipeline poster):**
> This is the whole machine on one page. Left to right: we simulate a
> physics-true sky with a beacon on a real ISS orbit… a virtual camera
> turns it into 30 noisy frames a second… perception finds about six
> bright candidates per frame… and the decision stage picks the ONE real
> beacon — because the beacon blinks at an agreed 4 hertz, and a star or
> sun-glint can be brighter but can never blink right. Our own small
> neural network double-checks every lock. The control module predicts
> 40 milliseconds ahead and sends 30 pointing commands per second back —
> a closed loop, using 20 of every 33 milliseconds on a normal laptop.

**2:30 · SHIVANAND (slide 4):**
> Is it robust? We ran 64 randomised campaigns — dim beacons, heavy
> turbulence, moving decoys. One hundred percent acquisition, zero wrong
> locks; the worst case still acquired in 4 seconds and held 91.6
> percent. And everything regenerates from one command — any judge can
> re-run our numbers.

**3:10 · ARYAN (slide 5 → 6):**
> Why it matters: without coarse alignment this optical link is usable
> 14.7 percent of the time. With ZeroDrift — 99.3. That is the
> difference between a demo and a link. And everything is public: open
> source, 73 tests passing, a one-click app, and the live console at
> zerodrift-fsoc-pat.netlify.app — please do open it. We didn't bring a
> promise, judges — we brought the working system. Thank you.

**~4:30 — stop. Silence is fine. Wait for questions.**

*(If time remains and judges look curious, Shivanand may say: "I can
show it live in 30 seconds" and switch the share to the app — turbulence
up, recover, truth toggle. Only if invited or clearly ahead of time.)*

---
## 2-minute Q&A (online = 2–3 questions max)
| Question smells like… | Answered by | Open with |
|---|---|---|
| AI / neural network / dataset / why not just brightest pixel | **Aashna** | "The gate is classical and strict — the AI verifier adds confidence: 497 parameters we trained on our own simulator, AUC 0.957 vs 0.900 classical. No downloaded dataset." |
| Physics / beacon / orbit / delay / gimbal | **Shivanand** | "The beacon is the terminal's identity light; 4 Hz sits safely under the camera's Nyquist limit…" |
| Hardware? / roadmap / cost / why software-only / anything else | **Aryan** | "The problem statement asks for validation without optical hardware — that is exactly what a virtual test-range is for." |
| What is a µrad? (anyone) | whoever is asked | "About 1 millimetre of drift per kilometre of distance. Our median is 198 µrad — deep inside the field." |

**Rules for the call:** mics muted unless speaking · answer in ≤20
seconds · never talk over a judge · if nobody knows: Aryan says "honest
answer — not measured yet; what we do know is…" · end every answer with
a number if you have one.

**If screen share dies:** Aryan shares from laptop 2 instantly, Shivanand
keeps narrating. No apologies, no dead air — the 1-minute extension
exists but plan to never need it.
