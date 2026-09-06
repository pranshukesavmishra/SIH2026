# ZeroDrift — What Is This Project? (the 3-minute read for anyone)

## The problem, like a story
Internet through light. Instead of radio, two stations fire an invisible
laser at each other — crazy fast, un-jammable, no spectrum licence. One
catch: a laser beam is a thin thread of light. Both stations must point
**exactly** at each other — with hair-thin accuracy — while wind shakes
one and the other flies overhead at 27,000 km/h. If pointing slips, the
link dies. Pointing is the hardest part, and ISRO (problem SIH26169)
asked teams to build this "pointing brain" **in software**, without
lakhs of rupees of optical hardware.

## What is the "beacon"?
Every laser terminal carries a small helper light — the **beacon** —
that blinks at an agreed speed (ours: 4 blinks per second). It is a
lighthouse saying "I am here, I am the right one." Stars and sun-glints
can be brighter, but they can never blink correctly — that blink is the
password.

## What did we build?
Two things, both finished and working:
1. **A virtual test-range** — a physics-true artificial sky: stars,
   clouds, atmospheric shaking, fake decoy lights, and a beacon moving on
   a *real* ISS orbit. Like a flight simulator, but for laser pointing.
2. **The pointing brain** — software that looks at that noisy camera
   picture, finds the beacon, checks its blink password, has a small
   self-trained AI double-check the lock, predicts where the beacon will
   be 40 milliseconds ahead, and steers a virtual camera to keep it
   centred — 30 times every second.

The brain never sees the answer. The simulator secretly knows where the
beacon truly is and grades the brain afterwards — like an examiner with
an answer key the student never touches. That is why our numbers are
honest.

## What can it do? (measured, not promised)
- Finds and locks the beacon in **1.27 seconds** from cold.
- Holds lock **98.3%** of an ISS pass; beacon in view **100%** of the time.
- Fooled by a wrong light **0 times in 64 random test runs**.
- Uses ~**20 of every 33 milliseconds** on a normal laptop — no GPU, no cloud.
- Bottom line: link usable **99.3%** of the time with our brain, vs **14.7%** without.

## Where can I see it?
- **Website** (any phone): zerodrift-fsoc-pat.netlify.app — replays a
  recorded run of the real engine, every number genuine.
- **Desktop app** — the live engine; judges can turn up turbulence and
  watch it fight and recover.
- **Code** — github.com/pranshukesavmishra/SIH-2026, open source,
  73/73 tests passing.

## Little dictionary
- **FSOC** — Free-Space Optical Communication: internet by laser through air/space.
- **µrad (micro-radian)** — a tiny tilt: ~1 mm sideways per km of distance.
- **Coarse alignment** — our job: get the beacon into view and hold it
  steady so the fast fine-steering mirror can do the last tiny bit.
- **COAST** — when the beacon blinks off, the brain keeps pointing from
  prediction. Not a failure — the plan.

**Team ZeroDrift** — Aryan Singh (lead), Pranshu Mishra, Aashna Verma,
Vivek Rajput, Palak Uikey, Shivanand Sahu · Mentor: Dr Jitendra Singh
Thakur · Jabalpur Engineering College.
