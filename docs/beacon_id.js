/*
 * ZeroDrift — beacon identification, browser edition.
 *
 * A direct port of src/fsoc_pat/hil/rig_detect.py, kept in its own file so
 * the algorithm can be tested headlessly (tools/web/test_beacon_id.js)
 * rather than only by pointing a torch at a laptop and hoping.
 *
 * The principle, in one line: a beacon is known by its modulation, not its
 * brightness. Bright-but-steady is rejected; correctly-blinking is locked.
 */
(function (root) {
  "use strict";

  const DEFAULTS = {
    absFloor: 110,      // nothing dimmer is ever a candidate
    relFraction: 0.55,  // cut the blob out of its own bloom
    minArea: 5,
    maxAreaFraction: 0.25,
    maxBlobs: 8,
    patch: 6,
    gate: 34,
    maxLen: 96,
    minSamples: 26,
    minModulation: 10,  // RMS of the AC component, 8-bit units
    scoreThreshold: 0.30,
    dropAfter: 2.0,
    confirmFrames: 5,
    dropFrames: 20,
  };

  /* ---- detection: bright extended blobs ---- */
  function findBlobs(lum, w, h, opts) {
    const o = Object.assign({}, DEFAULTS, opts);
    let peak = 0;
    for (let i = 0; i < lum.length; i++) if (lum[i] > peak) peak = lum[i];
    if (peak < o.absFloor) return [];

    const thresh = Math.max(o.absFloor, o.relFraction * peak);
    const seen = new Uint8Array(lum.length);
    const blobs = [], stack = [];
    const maxArea = o.maxAreaFraction * lum.length;

    for (let p = 0; p < lum.length; p++) {
      if (seen[p] || lum[p] < thresh) continue;
      let area = 0, su = 0, sv = 0, bpeak = 0;
      stack.push(p); seen[p] = 1;
      while (stack.length) {
        const q = stack.pop();
        const x = q % w, y = (q - x) / w;
        area++; su += x; sv += y;
        if (lum[q] > bpeak) bpeak = lum[q];
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx, ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
          const n = ny * w + nx;
          if (!seen[n] && lum[n] >= thresh) { seen[n] = 1; stack.push(n); }
        }
      }
      if (area >= o.minArea && area <= maxArea)
        blobs.push({ u: su / area, v: sv / area, area: area, peak: bpeak });
    }
    blobs.sort(function (a, b) { return b.area - a.area; });
    return blobs.slice(0, o.maxBlobs);
  }

  /* ---- identification: modulation depth + frequency match ---- */
  function powerFraction(x, t, f) {
    let total = 0;
    for (let i = 0; i < x.length; i++) total += x[i] * x[i];
    if (total <= 1e-9) return 0;
    let re = 0, im = 0;
    for (let i = 0; i < x.length; i++) {
      const a = -2 * Math.PI * f * (t[i] - t[0]);
      re += x[i] * Math.cos(a); im += x[i] * Math.sin(a);
    }
    return Math.min(1, 2 * (re * re + im * im) / (total * x.length));
  }

  function sampleAt(lum, w, h, u, v, patch) {
    let m = 0;
    const x0 = Math.max(0, (u | 0) - patch), x1 = Math.min(w - 1, (u | 0) + patch);
    const y0 = Math.max(0, (v | 0) - patch), y1 = Math.min(h - 1, (v | 0) + patch);
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
      const s = lum[y * w + x]; if (s > m) m = s;
    }
    return m;
  }

  function Identifier(opts) {
    this.o = Object.assign({}, DEFAULTS, opts);
    this.tracks = [];
    this._nextId = 1;
  }

  Identifier.prototype._score = function (tr, blinkHz) {
    const o = this.o, n = tr.s.length;
    if (n < o.minSamples) { tr.score = 0; tr.mod = 0; return; }
    let mean = 0;
    for (let i = 0; i < n; i++) mean += tr.s[i];
    mean /= n;
    const x = new Float64Array(n);
    let ss = 0;
    for (let i = 0; i < n; i++) { x[i] = tr.s[i] - mean; ss += x[i] * x[i]; }
    tr.mod = Math.sqrt(ss / n);
    // Bright but unmodulated — a lamp, a screen, a window. Never the beacon.
    if (tr.mod < o.minModulation) { tr.score = 0; tr.domHz = 0; return; }
    tr.score = powerFraction(x, tr.t, blinkHz);

    const span = tr.t[n - 1] - tr.t[0];
    if (span > 0) {
      const rate = (n - 1) / span, top = Math.min(15, 0.45 * rate);
      if (top > 1) {
        let bestF = 0, bestP = -1;
        for (let f = 1; f <= top; f += 0.25) {
          const p = powerFraction(x, tr.t, f);
          if (p > bestP) { bestP = p; bestF = f; }
        }
        tr.domHz = bestF;
      }
    }
  };

  /* Brightness is sampled at every live track on EVERY frame, including the
     frames where the beacon is dark: the off-half of the cycle carries half
     the signature, and sampling only lit frames would make a blinking source
     look exactly like a steady one. */
  Identifier.prototype.update = function (blobs, lum, w, h, now, blinkHz) {
    const o = this.o;
    const free = blobs.slice();
    for (const tr of this.tracks) {
      let best = null, bd = o.gate;
      for (const b of free) {
        const d = Math.hypot(b.u - tr.u, b.v - tr.v);
        if (d < bd) { bd = d; best = b; }
      }
      if (best) {
        free.splice(free.indexOf(best), 1);
        tr.u += 0.5 * (best.u - tr.u);
        tr.v += 0.5 * (best.v - tr.v);
        tr.seen = now;
      }
    }
    for (const b of free)
      this.tracks.push({ id: this._nextId++, u: b.u, v: b.v, s: [], t: [],
                         seen: now, score: 0, mod: 0, domHz: 0 });

    for (const tr of this.tracks) {
      tr.s.push(sampleAt(lum, w, h, tr.u, tr.v, o.patch));
      tr.t.push(now);
      if (tr.s.length > o.maxLen) { tr.s.shift(); tr.t.shift(); }
      this._score(tr, blinkHz);
    }
    this.tracks = this.tracks.filter(function (tr) {
      return now - tr.seen <= o.dropAfter;
    });

    let best = null;
    for (const tr of this.tracks)
      if (tr.score >= o.scoreThreshold && (!best || tr.score > best.score)) best = tr;
    return best;
  };

  /* ---- SEARCHING -> CONFIRMING k/n -> LOCKED, hysteresis both ways ---- */
  function Lock(opts) {
    const o = Object.assign({}, DEFAULTS, opts);
    this.confirmFrames = o.confirmFrames;
    this.dropFrames = o.dropFrames;
    this.reset();
  }
  Lock.prototype.reset = function () {
    this.state = 'SEARCHING'; this.hits = 0; this.misses = 0; this.trackId = null;
  };
  Lock.prototype.update = function (best) {
    if (best) {
      if (this.state === 'LOCKED' && this.trackId !== null && best.id !== this.trackId) {
        if (++this.misses > this.dropFrames) this.reset();
        return this.state;
      }
      this.trackId = best.id; this.misses = 0; this.hits++;
      this.state = this.hits >= this.confirmFrames ? 'LOCKED' : 'CONFIRMING';
    } else {
      this.misses++;
      if (this.state === 'LOCKED') {
        if (this.misses > this.dropFrames) this.reset();
      } else {
        this.hits = 0;
        if (this.misses > this.confirmFrames) this.reset();
      }
    }
    return this.state;
  };
  Object.defineProperty(Lock.prototype, 'progress', {
    get: function () { return [Math.min(this.hits, this.confirmFrames), this.confirmFrames]; }
  });

  const API = { DEFAULTS, findBlobs, powerFraction, sampleAt, Identifier, Lock };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.ZeroDriftBeacon = API;
})(typeof window !== 'undefined' ? window : globalThis);
