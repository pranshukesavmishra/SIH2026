# Defence Brief — what to say when the judges ask

*For the team. Each entry: the question, the two-sentence answer, and the
deeper story if they pull the thread. Judges score understanding, not code.*

## The one-paragraph pitch

FSOC links die from pointing error, and before a fine mirror can hold
micro-radians, a coarse stage must find and keep the beacon in a camera's
field of view. We built the whole coarse stage against a physics-honest
virtual world — turbulence with the right time constants, aliased platform
vibration, a mount with real latency and slew limits, a detector with real
noise — and we score it only against ground truth it cannot see. It acquires
in about a second, holds ~98% lock through pulsing and dropouts, never takes
a decoy in any test we ran, and on a real ISS pass our tracked error stream
closes a modelled optical link 99.3% of the time once the fine stage is
included — versus 14.7% without it, which is the two-stage architecture
justifying itself numerically.

## "Why is your closed-loop bandwidth only 3 Hz? Make it faster."

Because everything faster than 15 Hz is invisible to a 30 fps camera — the
turbulence and the vibration resonances alias. A controller that chases
aliased jitter amplifies it through the mount's inertia. The coarse stage's
job is the slow problem; the kilohertz problem belongs to the fine steering
mirror behind it. *(Thread: Greenwood frequency 25 Hz, resonances 18/47/120
Hz; our link-budget module models the FSM honestly — range saturation and
bandwidth leakage — and the 14.7% → 99.3% availability jump is the proof.)*

## "How do you know you're tracking the beacon and not a star?"

Four independent evidence streams must agree: persistence, motion consistency
against the filter's prediction, an a-priori direction prior (that is what
"designated" means), and — decisively — modulation: the beacon pulses at a
known rate, and a Goertzel filter at that exact frequency scores every
track's brightness history. A star scores zero. It is a hard gate, not a
weighted vote, because under heavy turbulence a weighted vote quietly picks
whichever star is easiest to see. *(Thread: flux history records zeros
through misses — the off-frames are half the signature.)*

## "Where exactly is the AI? Is it real or decoration?"

A 497-parameter spatio-temporal network we wrote from scratch in NumPy —
every gradient checked against finite differences — that reads eight
track-aligned patches and answers "is this the beacon". It beats the
classical Goertzel on short windows (AUC 0.957 vs 0.900) because eight
samples cannot resolve a frequency bin but a learned temporal signature still
separates. We will also tell you what the classical method does better:
given three seconds it is near-perfect and generalises to any frequency from
first principles. The network's honest contribution is identification speed.
*(Thread: hard negatives blink at wrong frequencies, so it cannot pass by
detecting "anything that pulses"; two train/serve skews we found and fixed
are documented in the code.)*

## "Your pointing error is hundreds of µrad. Isn't that bad?"

That residual is the aliased turbulence — below our Nyquist limit nothing at
30 fps can remove it, and the fine stage exists precisely to absorb it (it
has 3 mrad of throw; we deliver hundreds of µrad; the link closes at 99.3%).
The number that is ours to own is the coarse contract — beacon inside the
field of view — and that holds at 100% while locked. Also note which error we
quote: mount-vs-beacon, the honest one, five times larger than the flattering
filter-vs-beacon number we could have quoted instead.

## "What was your hardest bug?"

The controller lagged the target by exactly rate × latency, and the clue was
that disabling the integrator *removed* the lag — the integrator was
creating it. Our Smith predictor subtracted the mount's in-flight motion from
the measured error, which is correct for steps but misreads target-following
motion as correction-in-transit; the integrator wound against a bias that
could never reach zero. The fix is structural: compare predicted target
against predicted mount on the same horizon, proportional on that model
comparison, integral on the measured optical error only. 444 µrad → 4.2 µrad
on the ramp testbed. *(Also worth telling: association gates six times too
tight because measurement noise omitted the disturbances — 486 discarded
tracks in 400 frames, silently.)*

## "How do we know this isn't tuned to one lucky run?"

Same YAML + same seed = bit-identical frames, and the Monte Carlo campaign
randomises seed, beacon brightness (0.4–2.5×), turbulence (0.5–2×), vibration
(0.5–2×) and initial pointing error, then reports distributions — with every
run's draws logged so any outlier reproduces exactly. Separately, six unit
layers assert the physics itself: culmination symmetry, inverse-square,
Cramér–Rao scaling of the centroid, CFAR false-alarm rates against theory.

## "Why should ISRO believe this transfers to hardware?"

The hardware layer presents the same interfaces as the simulation — the
detector, tracker and controller objects cannot tell a webcam and two servos
from the virtual world; that is enforced by construction. Calibration is
measured, not assumed: plate scale and command latency come from commanding
the real servo and watching the real spot move. The rig costs ₹7k and does
not reproduce the simulation's precision — MG996R servos resolve ~0.3° — and
we say so; what it proves is that the identical code survives real optics,
real vibration (a motor bolted to the mount), and real turbulence (a hair
dryer in the path).

## Honest limitations, volunteer before asked

Turbulence is tip/tilt + scintillation, not a full phase screen — right
temporal statistics, no speckle. The az/el mount has the keyhole problem near
zenith; real terminals do too. The network knows only its training
distribution (4 Hz beacon); the classical path covers the rest. SGP4
topocentric conversion uses a spherical Earth — arcminutes, irrelevant for
angular-rate realism, stated in the docstring.

## Numbers to memorise

Acquisition ~1 s (2.3 s on the real ISS pass) · lock retention 95–99% ·
decoy locks: zero, every scenario · detector at the Cramér–Rao limit,
1.6 µrad at high SNR · control lag 4.2 µrad at 0.75°/s (was 444 before the
Smith restructure) · link availability 14.7% coarse-only → 99.3% with the
fine stage, 3.1 dB mean margin · 25–37 fps on two cores · 69 tests · 497
network parameters, gradient-checked.
