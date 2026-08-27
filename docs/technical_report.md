# FSOC-PAT: A Virtual Camera Tracking Testbed for Coarse Alignment of Mobile FSOC Terminals

**Smart India Hackathon 2026 — Problem Statement SIH26169 (ISRO)**
*Technical Report*

---

## 1. Problem understanding

Free Space Optical Communication carries gigabit-class data rates on a laser
beam narrow enough that pointing error *is* power loss: a Gaussian beam of
divergence θ delivers exp(−2r²/θ²) of its peak intensity at angular offset r.
Between mobile platforms — a satellite and a ground station, a UAV relay —
neither end knows the other's direction precisely, so a Pointing, Acquisition
and Tracking (PAT) chain establishes the link in two stages. A **fine stage**
(a fast steering mirror behind a quadrant detector) holds micro-radian
accuracy, but only within a throw of a few milliradians and only once it has
a signal. Everything before that is the **coarse stage**: sweep the Field of
Uncertainty, find the remote terminal's beacon among everything else that
glints, decide which source it is, and hold it inside the tracking camera's
field of view against turbulence, platform vibration and the mount's own
limitations, until the fine stage can take over.

The problem statement asks for this coarse stage in software: a virtual scene,
a virtual pan-tilt camera, disturbances, and a tracker that closes the loop —
because real cameras, mounts and optics are expensive, and algorithms
developed against an honest simulation transfer.

Our reading of "honest" drives every design decision in this report: the
simulation must be hard in the ways the real problem is hard, the tracker must
never touch information a real system would not have, and every performance
number must be scored against ground truth the tracker cannot see.

## 2. System architecture

Two closed loops share one geometry library:

```
 SIMULATION (the world)                 TRACKER (the system under test)
 ┌──────────────────────────┐          ┌──────────────────────────────┐
 │ scene: sky, cloud, stars │  frame   │ detection: top-hat → matched │
 │ beacon: trajectories,    │ ───────▶ │  filter → CFAR → sub-pixel   │
 │  radiometry, modulation  │          │ tracking: association, IMM,  │
 │ disturbance: turbulence, │          │  modulation ID, AI verifier  │
 │  vibration               │          │ search: spiral over the FOU  │
 │ camera: gimbal limits,   │ ◀─────── │ control: two-path Smith      │
 │  latency, detector noise │ command  │  predictor, PI + feedforward │
 └──────────────────────────┘          └──────────────────────────────┘
        │                                        │
        ▼ ground truth                           ▼ telemetry
       ───────────────  metrics engine  ───────────────
        acquisition time, lock retention, pointing error
        percentiles, decoy statistics, link availability
```

The same tracker objects also run against a physical rig (§8): a USB camera
and two servos behind the same interfaces, so "the identical code drives real
optics" is enforced by construction rather than claimed.

## 3. The simulated world

**Scene.** Split by spatial frequency. Low: a sky gradient that brightens
toward the horizon, fractal cloud, terrain, and a forward-scattering solar
halo, held as a panorama and resampled per frame. High: ~900 stars and
point-source ground clutter with power-law brightness, plus occasional
specular sun glint. Everything unresolved is splatted through the *same*
photometrically-normalised PSF as the beacon — deliberately, so no detector
can cheat by learning a rendering difference.

**Targets.** Six trajectory generators: static, linear, circular, waypoint,
Ornstein–Uhlenbeck wander, an analytic great-circle LEO pass with correct
slant-range geometry — and real two-line elements propagated with SGP4, so
the shipped ISS scenario carries genuine LEO angular-rate profiles (0.8°/s at
its 70° culmination). Brightness follows inverse-square range and the
acquisition beacon is pulsed (4 Hz, 50% duty), because modulation is how real
FSO terminals make the beacon identifiable at all.

**Disturbances.** Turbulent tip/tilt as a Gauss–Markov process with its
corner at the Greenwood frequency (raising the frequency makes jitter *harder
to follow*, not merely larger), partially common-mode across the field with
an anisoplanatic residual; log-normal scintillation; platform vibration as
white-noise-driven damped resonances (18/47/120 Hz) sub-stepped for stability
and deliberately aliased by the 30 fps camera, exactly as real hardware
aliases them; frame drops.

**Camera.** A rate- and acceleration-limited gimbal with a trapezoidal slew
profile, 40 ms command latency, and encoder noise — `true_pointing` and
`reported_pointing` are kept separate throughout, and all scoring uses the
true one. The detector integrates electrons: shot noise (Poisson, with a
variance-exact Gaussian approximation above 25 e⁻), read noise, dark current,
hot pixels, full-well saturation and 12-bit quantisation.

Every run is reproducible: one YAML scenario plus one seed produces
bit-identical frames, with independent random streams per subsystem so
editing one does not reshuffle another.

## 4. Detection

The beacon is an unresolved point: no shape, no texture, only PSF-shaped
brightness. The chain is the standard one from infrared search-and-track and
space surveillance, each stage for a specific reason:

1. **Morphological top-hat** removes everything larger than the PSF — sky
   gradient, cloud, halo — because a global threshold is useless against a
   background that varies by orders of magnitude across the frame.
2. **Matched filter** (correlation with the PSF; for a Gaussian, a blur) —
   the optimal linear detector for a known shape in noise.
3. **CFAR threshold** from an annulus around each pixel (guard band excluded
   so a bright target cannot inflate its own threshold), holding the false
   alarm rate constant from dark sky to bright cloud. The annulus statistics
   are computed on an area-averaged decimated grid — safe because area
   averaging preserves both E[x] and E[x²], so the recovered variance is the
   true full-resolution variance; measured Pd and centroid error are
   unchanged to three decimals while the cost halves.
4. **Sub-pixel centroid** by a log-parabola fit on the background-subtracted
   response — algebraically exact for a Gaussian peak — with a plain-parabola
   fallback where wings reach zero.

Measured performance (turbulence, stars and clutter present): Pd = 0.88 at
SNR 5.3, Pd = 1.00 from SNR 10, centroid error 0.10 px (17 µrad) at SNR 10
falling to 0.010 px (1.6 µrad) at SNR 79. Error × SNR is constant across the
range — the Cramér–Rao signature, so the estimator sits at its theoretical
limit rather than merely working. A one-filter-footprint border margin is
excluded: measured on an empty field, the border ring supplied 18 of 19
false alarms while covering 14% of the pixels.

## 5. Identification and tracking

Detection is not identification: every frame also contains stars, clutter and
glint, all PSF-shaped. Four independent evidence streams separate them.

**Persistence and motion consistency.** Greedy nearest-neighbour association
under a χ² gate feeds per-track Interacting Multiple Model filters — a smooth
and a manoeuvring constant-acceleration model differing only in process
noise, mixed by likelihood. The IMM's mode probability doubles as a live
"how hard is the target manoeuvring" readout. The measurement noise model
includes the *disturbance* terms (vibration displaces the optical axis from
what encoders report; turbulence displaces the apparent source): omitting
them made every gate six times too tight, and the tracker silently spawned
and discarded 486 one-hit tracks over 400 frames. With them: one track.

**A priori direction.** The terminal knows roughly where the remote end
should be (ephemeris); a Gaussian prior over that direction — wide during
search, narrowed and slid along with the lock — is what "designated target"
means operationally.

**Modulation.** The decisive stream. A single-bin DFT (Goertzel) at the known
beacon frequency scores each track's flux history — recorded through misses,
because the off-frames are half the signature. A star scores 0.00, the pulsed
beacon 0.81. Applied as a hard gate rather than a weighted term: under heavy
turbulence a weighted sum quietly hands the lock to whichever steady star is
easiest to see.

**Learned verifier (the AI component, §6).**

A five-state machine (SEARCH → ACQUIRE → TRACK ⇄ COAST → REACQUIRE) sequences
acquisition: an Archimedean spiral over the Field of Uncertainty (arc-length
stepped, short-axis spacing, azimuth steps divided by cos(el) so the pattern
does not collapse near the zenith), coasting on the filter's prediction
through blink-off frames and dropouts, a local re-spiral on loss, and a full
restart only when that fails. Lock hysteresis prevents oscillating between
the beacon and a marginally-scored decoy.

## 6. AI methods

A single frame *cannot* distinguish the beacon from a star here — the
simulator renders every point source through the same PSF precisely so that
no single-frame cue exists. What separates them lives in time. The learned
component is therefore a **spatio-temporal network over K=8 track-aligned
patches**: one shared 3×3 spatial convolution (PSF shape), a temporal
convolution across frames (modulation, motion), a dense head. 497 parameters,
implemented from scratch in NumPy — inference ships inside the standalone
executable without a framework, and every gradient is verified against finite
differences in the test suite (worst relative error 1.5 × 10⁻⁷).

Training data is harvested from the simulator, which is a labelling oracle.
Hard negatives include imposters that move *and* blink at wrong frequencies,
so the network cannot pass by detecting "anything that pulses". Held-out
performance: **AUC 0.957 vs 0.900** for the Goertzel bin power on identical
8-frame inputs. The honest framing, which we prefer to an inflated one: given
3 s of history the classical Goertzel is near-perfect and generalises to any
configured frequency from first principles; the network's edge is *speed* —
it separates beacon from imposter on a 0.27 s window where eight samples
cannot resolve the frequency bin. It joins the evidence fusion at a
deliberately lower weight than the classical gate.

Two train/serve skews were found live and are documented in the code: patches
must be cut at the track's *predicted* position every frame (only-detection
patches show a source that never blinks off — which training labels "star"),
and training must randomise blink phase and jitter patch centres, or the
network memorises one phase and centred-only PSFs.

## 7. Control

The loop is deliberately slow. Turbulence (Greenwood 25 Hz) and the vibration
resonances sit at or above the 15 Hz Nyquist limit of a 30 fps camera: that
jitter is aliased, unobservable, and chasing it amplifies it. The closed-loop
bandwidth is ~3 Hz — enough to follow real target motion, slow enough to
average the rest — and removing the fast residual is precisely the fine
stage's job (§9).

Commands take effect 40 ms after issue. The controller is a **two-path Smith
predictor**: an internal replica of the mount, driven by the same commands,
answers "where will the mount be when this command lands"; the target's
filter answers "where will the target be". The *proportional* path acts on
the difference of those two predictions (fast, dead-time-immune); the
*integral* path acts on the measured optical error (slow, but the only signal
that reflects where the mount truly is, hence the only path that can remove a
constant offset the model cannot see). The optical error itself comes from
the image, not the encoders — immune to encoder bias, which is why a tracking
sensor exists.

Getting this structure right mattered more than any gain: a step-input Smith
form (subtracting in-flight motion from the measured error) misreads
target-following motion as correction-in-transit and settles exactly one dead
time behind the target. On a sterile ramp testbed the restructure took the
steady-state lag from 444 µrad to **4.2 µrad** at 0.75°/s (25.6 µrad at
3°/s); a 0.3° step settles in 0.27 s; a 100 ms latency still holds 13 µrad.

## 8. Test methodology

Four layers, each catching what the previous cannot:

1. **Unit tests (69)** — projection exactness (boresight, round-trip,
   pixel-radius vs true separation, high-elevation behaviour), config
   round-trips, trajectory physics (culmination symmetry, slant range,
   inverse-square, blink Nyquist), gimbal limits actually binding, detector
   saturation, IMM/association behaviour, link-budget monotonicity, and the
   network's finite-difference gradient check.
2. **Statistical validation** — detector Pd/accuracy vs SNR against
   Cramér–Rao scaling; CFAR false-alarm rate against the Gaussian prediction
   (which is how the border-artefact bug was found); decimated-CFAR
   equivalence against exact.
3. **Closed-loop scenario suite** — six shipped scenarios from
   `static_easy` to `decoy_field` (three decoys crossing the field, dense
   clutter, frequent glint — wrong-lock scores zero) and the SGP4 ISS pass.
4. **Monte Carlo campaign** — randomised seed, beacon brightness (0.4–2.5×),
   turbulence (0.5–2×), vibration (0.5–2×) and initial pointing error across
   the Field of Uncertainty; distributions below, every run reproducible
   from its logged draws.

The honest-metrics rule is enforced in the scoring itself: the headline
error is **pointing error** — true optical axis vs true beacon, the angle
that decides whether a link closes — not the flattering estimate-vs-truth
error (which differs by 5× here); lock retention counts COAST-through-blink
as locked but a decoy lock as a separate, never-laundered statistic;
acquisition time is time-to-TRACK, not time-to-first-detection.

## 9. Performance analysis

Closed loop, 60 s per scenario, all disturbances on:

| Scenario | Acquisition | Lock retention | Pointing error (mean) | Decoy locks |
|---|---|---|---|---|
| static_easy | 0.77 s | 98.6% | 53 µrad | 0 |
| leo_pass_nominal | 1.10 s | 98.8% | ~500 µrad† | 0 |
| decoy_field | 1.03 s | 99.0% | ~500 µrad† | 0 |
| turbulence_hard | 1.50 s | 95.3% | 292 µrad | 0 |
| uav_relay | 4.07 s | 96.2% | 1.3 mrad | 0 |
| iss_pass (SGP4) | 2.27 s | 97.8% | p95 773 µrad | 0 |

† dominated by residual turbulent jitter, which is below the coarse stage's
Nyquist limit and belongs to the fine stage; the coarse contract (beacon in
FOV) holds at 100%.

**Monte Carlo (leo_pass family, 64 randomised runs):** see
`runs/mc-leo/summary.json` — acquisition probability, acquisition-time
percentiles, lock-retention envelope, pointing-error envelope, wrong-lock
count. *(Numbers inserted from the campaign output in the submitted PDF.)*

**Link closure (the number the exercise exists for).** On the tracked ISS
pass, with a 250 µrad communications beam and a 15 cm aperture: the coarse
stage alone closes the link **14.7%** of the time; coarse + a modelled fine
steering stage (3 mrad throw, 300 Hz, range-saturation and bandwidth-leakage
honest) closes it **99.3%** at 3.1 dB mean margin, zero outages. That pair of
numbers *is* the two-stage PAT architecture's justification, measured rather
than asserted.

Throughput: 25–37 fps against the 30 fps simulated camera on two cores,
~8 ms/frame processing in the packaged binary.

## 10. Future improvements

Ordered by what we would actually do next: (i) estimate the common-mode
turbulent tilt from the star field and feed it forward — the scene already
renders stars through the same tilt for exactly this experiment; (ii) replace
the greedy association with a proper assignment solver for dense decoy
fields; (iii) adaptive CFAR k scheduling against measured clutter density;
(iv) close the loop on the physical rig with a camera-derived (rather than
encoder-derived) pointing feed at higher frame rates; (v) extend the network
to variable beacon frequencies via frequency-conditioned inputs.

---

*All code, tests, scenarios and this report: repository `SIH2026`, branch
`claude/sih-problem-selection-w3p3o4`. Every number in this report is
regenerable: `pytest` for the unit layer, `python -m fsoc_pat.runner` per
scenario, `python -m fsoc_pat.campaign` for the distributions,
`python -m fsoc_pat.ai.train` for the AI benchmark.*
