"""The from-scratch network must be *provably* correct, not plausibly so."""
import numpy as np
import pytest

from fsoc_pat.ai.tinynet import TemporalPatchNet, normalise_stack


def test_gradients_match_finite_differences():
    """Every parameter tensor, checked numerically. This is the correctness
    statement a framework user never gets to make."""
    rng = np.random.default_rng(0)
    net = TemporalPatchNet(frames=6, patch=9, c_spatial=4, c_temporal=6, seed=1)
    x = rng.normal(size=(5, 6, 9, 9))
    y = (rng.random(5) > 0.5).astype(float)

    def loss():
        logits = net.forward(x)
        p = 1 / (1 + np.exp(-logits))
        return float(-np.mean(y * np.log(p + 1e-9) + (1 - y) * np.log(1 - p + 1e-9)))

    logits = net.forward(x, keep=True)
    p = 1 / (1 + np.exp(-logits))
    grads = net._backward((p - y) / len(y))

    worst = 0.0
    for key in net.params:
        flat = net.params[key].ravel()
        for i in rng.choice(flat.size, size=min(5, flat.size), replace=False):
            old = flat[i]
            h = 1e-6
            flat[i] = old + h; lp = loss()
            flat[i] = old - h; lm = loss()
            flat[i] = old
            fd = (lp - lm) / (2 * h)
            an = grads[key].ravel()[i]
            worst = max(worst, abs(fd - an) / max(abs(fd) + abs(an), 1e-12))
    assert worst < 1e-5, f"worst relative gradient error {worst:.2e}"


def test_training_separates_a_learnable_signal():
    """Blinking vs steady synthetic sources: loss must fall and separate."""
    rng = np.random.default_rng(3)
    n, K, P = 60, 8, 11

    def stack(blinking):
        s = rng.normal(0, 1, (K, P, P))
        pattern = (np.arange(K) % 2 == 0) if blinking else np.ones(K, bool)
        for k in range(K):
            if pattern[k]:
                s[k, P // 2 - 1:P // 2 + 2, P // 2 - 1:P // 2 + 2] += 8.0
        return normalise_stack(s)

    x = np.stack([stack(i < n // 2) for i in range(n)])
    y = np.array([1.0] * (n // 2) + [0.0] * (n // 2))
    net = TemporalPatchNet(frames=K, patch=P, seed=2)
    history = net.train(x, y, epochs=150)
    assert history[-1] < 0.1 * history[0]
    p = net.predict(x)
    assert p[:n // 2].mean() > 0.85 and p[n // 2:].mean() < 0.15


def test_save_load_round_trip(tmp_path):
    rng = np.random.default_rng(1)
    net = TemporalPatchNet(frames=6, patch=9, seed=5)
    x = rng.normal(size=(3, 6, 9, 9))
    before = net.predict(x)
    path = str(tmp_path / "w.npz")
    net.save(path)
    after = TemporalPatchNet.load(path).predict(x)
    assert np.allclose(before, after)


def test_normalise_is_brightness_invariant():
    """Brightness must not be learnable: a decoy can outshine the beacon."""
    rng = np.random.default_rng(2)
    stack = rng.normal(10, 2, (8, 11, 11))
    a = normalise_stack(stack)
    b = normalise_stack(stack * 37.0 + 120.0)
    assert np.allclose(a, b, atol=1e-9)


def test_verifier_loads_calibration_and_abstains(tmp_path):
    """With calibration.json beside the weights, marginal scores become
    abstentions (None) instead of guesses; confident scores still vote."""
    import json
    from fsoc_pat.ai.verifier import TrackVerifier

    rng = np.random.default_rng(4)
    net = TemporalPatchNet(frames=4, patch=9, seed=6)
    net.save(str(tmp_path / "w.npz"))
    (tmp_path / "calibration.json").write_text(json.dumps(
        {"temperature": 2.0, "abstain_lo": 0.0, "abstain_hi": 1.0}))

    v = TrackVerifier(str(tmp_path / "w.npz"))
    assert v.temperature == 2.0
    img = rng.normal(100, 5, (60, 80))
    for _ in range(4):
        v.observe(7, img, 40.0, 30.0)
    # the all-inclusive abstain band above forces None whatever the logit
    assert v.score(7) is None
    # ...but the raw calibrated value was still recorded for telemetry
    assert 0.0 <= v.scores[7] <= 1.0

    # no sidecar -> legacy behaviour, a real number comes back
    bare = tmp_path / "bare"
    bare.mkdir()
    net.save(str(bare / "w2.npz"))
    v2 = TrackVerifier(str(bare / "w2.npz"))
    for _ in range(4):
        v2.observe(7, img, 40.0, 30.0)
    assert isinstance(v2.score(7), float)


def test_temperature_scaling_preserves_ranking():
    from fsoc_pat.ai.calibrate import fit_temperature

    rng = np.random.default_rng(9)
    logits = rng.normal(0, 3, 400)
    labels = (logits + rng.normal(0, 2, 400) > 0).astype(float)
    T = fit_temperature(logits, labels)
    assert 0.25 <= T <= 12.0
    p = 1 / (1 + np.exp(-logits / T))
    assert np.all(np.argsort(p) == np.argsort(logits))   # monotone
