/*
 * Headless tests for docs/beacon_id.js — the browser demo's algorithm.
 *
 *     node tools/web/test_beacon_id.js
 *
 * These mirror tests/test_rig_detect.py case for case. The browser build is
 * a port, and a port is exactly the kind of thing that looks right and
 * behaves differently; it is also the artifact most likely to be put in
 * front of a judge, so it does not get to be the untested one.
 */
"use strict";
const assert = require("assert");
const path = require("path");
const B = require(path.join(__dirname, "..", "..", "docs", "beacon_id.js"));

const W = 160, H = 120, FPS = 30;

// Deterministic noise so a failure is reproducible.
let seed = 7;
function rnd() {
  seed = (seed * 1103515245 + 12345) & 0x7fffffff;
  return seed / 0x7fffffff;
}
function gauss(mu, sd) {
  const u = Math.max(rnd(), 1e-9), v = rnd();
  return mu + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function frame(noise = 8) {
  const lum = new Uint8ClampedArray(W * H);
  for (let i = 0; i < lum.length; i++) lum[i] = Math.max(0, Math.min(255, gauss(noise, 4)));
  return lum;
}
function addBlob(lum, u, v, radius = 10, peak = 255) {
  const out = Uint8ClampedArray.from(lum);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const d2 = (x - u) ** 2 + (y - v) ** 2;
    out[y * W + x] = Math.min(255, out[y * W + x] + peak * Math.exp(-d2 / (2 * radius ** 2)));
  }
  return out;
}

function run(frames, blinkHz = 4.0) {
  const ident = new B.Identifier();
  const lock = new B.Lock();
  const states = [];
  let best = null;
  frames.forEach((lum, i) => {
    const blobs = B.findBlobs(lum, W, H);
    best = ident.update(blobs, lum, W, H, i / FPS, blinkHz);
    states.push(lock.update(best));
  });
  return { ident, lock, states, best };
}

const tests = {
  "finds the saturated blob": () => {
    const blobs = B.findBlobs(addBlob(frame(), 80, 60, 12), W, H);
    assert.ok(blobs.length > 0, "flashlight must be detected");
    assert.ok(Math.abs(blobs[0].u - 80) < 6 && Math.abs(blobs[0].v - 60) < 6);
  },

  "dark frames stay silent": () => {
    for (let i = 0; i < 10; i++)
      assert.strictEqual(B.findBlobs(frame(), W, H).length, 0);
  },

  "noisy dark frame stays silent": () => {
    const lum = new Uint8ClampedArray(W * H);
    for (let i = 0; i < lum.length; i++) lum[i] = Math.max(0, Math.min(255, gauss(35, 18)));
    assert.strictEqual(B.findBlobs(lum, W, H).length, 0);
  },

  "blinking beacon locks": () => {
    const frames = [];
    for (let i = 0; i < 120; i++) {
      const f = frame();
      frames.push(Math.sin(2 * Math.PI * 4 * i / FPS) > 0 ? addBlob(f, 100, 50) : f);
    }
    const { lock, best } = run(frames);
    assert.strictEqual(lock.state, "LOCKED");
    assert.ok(best.score > 0.3, `score ${best.score}`);
    assert.ok(Math.abs(best.domHz - 4) < 1.0, `domHz ${best.domHz}`);
    assert.ok(Math.abs(best.u - 100) < 15 && Math.abs(best.v - 50) < 15);
  },

  "steady lamp is rejected however bright": () => {
    const frames = [];
    for (let i = 0; i < 120; i++) frames.push(addBlob(frame(), 100, 50, 12));
    const { lock, states } = run(frames);
    assert.strictEqual(lock.state, "SEARCHING");
    assert.ok(!states.includes("LOCKED"), "a steady source must never lock");
  },

  "wrong blink rate is rejected": () => {
    const frames = [];
    for (let i = 0; i < 150; i++) {
      const f = frame();
      frames.push(Math.sin(2 * Math.PI * 1 * i / FPS) > 0 ? addBlob(f, 100, 50) : f);
    }
    const { states } = run(frames, 4.0);
    assert.ok(!states.includes("LOCKED"), "1 Hz must not satisfy a 4 Hz matcher");
  },

  "empty scene never locks": () => {
    const frames = [];
    for (let i = 0; i < 120; i++) frames.push(frame());
    const { lock, states } = run(frames);
    assert.strictEqual(lock.state, "SEARCHING");
    assert.ok(states.every(s => s === "SEARCHING"));
  },

  "beacon wins against a steady distractor": () => {
    const frames = [];
    for (let i = 0; i < 120; i++) {
      let f = addBlob(frame(), 30, 30, 12);
      if (Math.sin(2 * Math.PI * 4 * i / FPS) > 0) f = addBlob(f, 120, 85);
      frames.push(f);
    }
    const { lock, best } = run(frames);
    assert.strictEqual(lock.state, "LOCKED");
    assert.ok(Math.abs(best.u - 120) < 20 && Math.abs(best.v - 85) < 20,
      `locked at ${best.u},${best.v} — should be the blinking one`);
  },

  "lock survives a brief dropout": () => {
    const lock = new B.Lock({ confirmFrames: 3, dropFrames: 10 });
    const T = { id: 1, score: 0.9 };
    for (let i = 0; i < 3; i++) lock.update(T);
    assert.strictEqual(lock.state, "LOCKED");
    for (let i = 0; i < 8; i++) lock.update(null);
    assert.strictEqual(lock.state, "LOCKED", "blink-off must not drop the lock");
    for (let i = 0; i < 5; i++) lock.update(null);
    assert.strictEqual(lock.state, "SEARCHING");
  },

  "one good frame does not lock": () => {
    const lock = new B.Lock({ confirmFrames: 5 });
    assert.strictEqual(lock.update({ id: 1, score: 0.9 }), "CONFIRMING");
  },
};

let pass = 0, fail = 0;
for (const [name, fn] of Object.entries(tests)) {
  try { fn(); console.log(`  ok   ${name}`); pass++; }
  catch (e) { console.log(`  FAIL ${name}\n       ${e.message}`); fail++; }
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
