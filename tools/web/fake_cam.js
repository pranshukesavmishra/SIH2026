/* Synthetic camera for tools/web/test_live_motion.mjs.
 *
 * A canvas-backed MediaStream carrying what the real demo actually meets:
 * a 4 Hz blinking torch moved BY HAND -- jerky, with reversals, stop-and-go
 * and varying speed -- plus a steady bright lamp that must never win, over a
 * textured wall. Exposes window.__truth() so the harness can score the ring
 * against the real position instead of against its own opinion.
 *
 * Handheld rather than constant-velocity on purpose: smooth sweeps are the
 * one motion a constant-velocity predictor handles perfectly, so a test built
 * on them passes while the real page flies off the beacon. This path is the
 * failure the tester reported.
 */
(() => {
  const W = 320, H = 240;
  const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
  const cx = cv.getContext('2d', { willReadFrequently: true });

  const bg = document.createElement('canvas'); bg.width = W; bg.height = H;
  const bx = bg.getContext('2d');
  const img = bx.createImageData(W, H);
  let seed = 12345;
  const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  for (let i = 0; i < W * H; i++) {
    const v = 38 + 14 * ((i % W) / W) + (rnd() - 0.5) * 14;
    img.data[i*4] = img.data[i*4+1] = img.data[i*4+2] = v; img.data[i*4+3] = 255;
  }
  bx.putImageData(img, 0, 0);

  // Waypoints: [t, x, y]. Between them, smoothstep -- hands accelerate and
  // decelerate, they do not teleport to a constant speed.
  const WP = [
    [0.0,  90, 130], [3.5,  90, 130],   // settle: acquire on a still target
    [4.3, 200, 105],                    // quick flick right  (~9 px/frame)
    [4.9, 200, 105],                    // hold
    [5.6, 120, 170],                    // flick back-left (reversal)
    [6.2, 120, 170],
    [7.4, 245, 165],                    // long fast sweep right
    [8.0, 245, 165],
    [8.6, 150,  80],                    // diagonal up-left
    [9.2, 150,  80],
    [10.2, 60, 190],                    // big diagonal down-left
    [11.0, 60, 190],
    [11.7, 230, 120],                   // fast right again
    [13.5, 230, 120],                   // final settle
  ];
  const smooth = u => u * u * (3 - 2 * u);
  function path(t) {
    if (t <= WP[0][0]) return [WP[0][1], WP[0][2]];
    for (let i = 0; i < WP.length - 1; i++) {
      const [t0, x0, y0] = WP[i], [t1, x1, y1] = WP[i + 1];
      if (t >= t0 && t <= t1) {
        const u = t1 > t0 ? smooth((t - t0) / (t1 - t0)) : 1;
        return [x0 + (x1 - x0) * u, y0 + (y1 - y0) * u];
      }
    }
    const L = WP[WP.length - 1];
    return [L[1], L[2]];
  }

  let t0 = null;
  window.__truth = () => {
    if (t0 === null) return null;
    const t = (performance.now() - t0) / 1000;
    return { t, p: path(t), on: (t * 4.0) % 1.0 < 0.5, end: WP[WP.length - 1][0] };
  };

  function spot(u, v, r) {
    const g = cx.createRadialGradient(u, v, 0, u, v, r);
    g.addColorStop(0, 'rgba(255,255,255,1)');
    g.addColorStop(0.45, 'rgba(255,255,255,0.95)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    cx.fillStyle = g; cx.beginPath(); cx.arc(u, v, r, 0, 7); cx.fill();
  }
  function draw() {
    cx.drawImage(bg, 0, 0);
    const s = window.__truth();
    if (s) { if (s.on) spot(s.p[0], s.p[1], 7); spot(275, 205, 7); }
    setTimeout(draw, 25);
  }
  navigator.mediaDevices.getUserMedia = async () => {
    if (t0 === null) { t0 = performance.now(); draw(); }
    return cv.captureStream(30);
  };
})();
