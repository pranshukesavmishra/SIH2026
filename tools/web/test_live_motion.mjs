/* End-to-end check of docs/live.html against a synthetic handheld beacon.
 *
 *   cd docs && python3 -m http.server 8099 &
 *   node ../tools/web/test_live_motion.mjs
 *
 * Drives the REAL page in headless Chromium with fake_cam.js and scores the
 * ring against ground truth. The metric that matters, and the one an earlier
 * version of this harness was missing: WHILE THE BEACON IS LIT, how far is
 * the ring from the actual light? A test that only asks "did it stay LOCKED"
 * passes happily while the ring sails across the room.
 */
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { readFileSync } from 'fs';

const HERE = new URL('.', import.meta.url).pathname;
const OUT = process.argv[2] || '/tmp';
const URL_ = process.env.LIVE_URL || 'http://127.0.0.1:8099/live.html';

const b = await chromium.launch({
  executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium' });
const pg = await b.newPage({ viewport: { width: 1100, height: 850 } });
pg.on('pageerror', e => console.log('PAGEERROR', String(e).slice(0, 200)));
await pg.addInitScript(readFileSync(`${HERE}/fake_cam.js`, 'utf8'));
await pg.goto(URL_);
await pg.click('#startBtn');

const S = [];
const t0 = Date.now();
while (Date.now() - t0 < 14200) {
  S.push(await pg.evaluate(() => {
    const tr = window.__truth();
    return { ds: displayState(), st: state,
             p: pos ? [pos.x, pos.y] : null, m: margin,
             v: [vel.x, vel.y], cf: coastFrames,
             t: tr ? tr.t : null, tp: tr ? tr.p : null, on: tr ? tr.on : false };
  }));
  await new Promise(r => setTimeout(r, 55));
}
await pg.screenshot({ path: `${OUT}/live_motion_end.png` });
await b.close();

const fail = [], ok = m => console.log('  ok:', m);
const err = s => (s.p && s.tp) ? Math.hypot(s.p[0] - s.tp[0], s.p[1] - s.tp[1]) : Infinity;
const pct = (a, b) => `${((a / Math.max(b, 1)) * 100) | 0}%`;

// --- 1. acquires the blinking beacon while it is still ---
const pre = S.filter(s => s.t > 2.0 && s.t < 3.4 && s.st === 'LOCKED');
if (!pre.length) fail.push('never acquired the still beacon');
else {
  const e = Math.min(...pre.map(err));
  e < 25 ? ok(`acquired still beacon, err ${e.toFixed(0)}px`)
         : fail.push(`still-beacon lock is ${e.toFixed(0)}px off`);
}

// --- 2. THE headline: while LIT and LOCKED, the ring is ON the light ---
const lit = S.filter(s => s.t > 3.5 && s.st === 'LOCKED' && s.on && s.p);
const good = lit.filter(s => err(s) < 45);
const med = lit.length ? lit.map(err).sort((a, b) => a - b)[lit.length >> 1] : Infinity;
if (!lit.length) fail.push('no lit LOCKED samples during motion at all');
else if (good.length / lit.length < 0.85)
  fail.push(`ring on the light only ${pct(good.length, lit.length)} of lit frames `
          + `(median err ${med.toFixed(0)}px, worst ${Math.max(...lit.map(err)).toFixed(0)}px)`);
else ok(`ring on the light for ${pct(good.length, lit.length)} of lit frames, median err ${med.toFixed(0)}px`);

// --- 3. never runs away: no sample may be absurdly far while claiming lock ---
const runaway = S.filter(s => s.st === 'LOCKED' && s.p && err(s) > 110);
runaway.length ? fail.push(`ring ran away (>110px) on ${runaway.length} samples, `
                         + `worst ${Math.max(...runaway.map(err)).toFixed(0)}px at t=${runaway[0].t.toFixed(1)}s`)
               : ok('never ran away from the beacon');

// --- 4. lock survives the whole handheld sequence ---
const lost = S.find(s => s.t > 3.6 && s.t < 13.4 && s.st === 'SEARCHING');
lost ? fail.push(`lock lost at t=${lost.t.toFixed(1)}s`) : ok('lock held through every flick and reversal');

// --- 5. the steady lamp never wins ---
const lamp = S.find(s => s.st === 'LOCKED' && s.p && Math.hypot(s.p[0] - 275, s.p[1] - 205) < 30);
lamp ? fail.push(`locked the STEADY lamp at t=${lamp.t.toFixed(1)}s`) : ok('steady lamp never captured the lock');

// --- 6. settles back onto the beacon at the end ---
const fin = S.filter(s => s.t > 13.0 && s.st === 'LOCKED');
const finE = fin.length ? Math.min(...fin.map(err)) : Infinity;
finE < 25 ? ok(`settled on the beacon at rest, err ${finE.toFixed(0)}px`)
          : fail.push(`did not settle at rest (best ${finE === Infinity ? 'no lock' : finE.toFixed(0) + 'px'})`);

// --- 7. readouts stay sane ---
const mx = Math.max(...S.map(s => s.m));
mx <= 60 ? ok(`margin bounded (max ${mx.toFixed(1)}x)`) : fail.push(`margin absurd: ${mx}`);

console.log(fail.length ? '\nFAILURES:\n  - ' + fail.join('\n  - ') : '\nALL CHECKS PASSED');
process.exit(fail.length ? 1 : 0);
