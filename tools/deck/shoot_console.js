const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const p = await b.newPage({ viewport: { width: 1520, height: 980 }, deviceScaleFactor: 2 });
  await p.goto('http://localhost:8123/console.html', { waitUntil: 'networkidle' });
  await p.waitForTimeout(3000);
  await p.selectOption('#scen', 'media/telemetry_run.json');
  await p.waitForTimeout(2500);

  // PAUSE FIRST so playback cannot advance past the frame we choose
  if (await p.evaluate(() => document.getElementById('play').classList.contains('on'))) await p.click('#play');
  await p.waitForTimeout(500);
  await p.evaluate(() => { ['debrief','help','loading-screen'].forEach(id => { const e=document.getElementById(id); if(e){e.hidden=true;e.style.display='none';} }); });

  const pick = await p.evaluate(() => {
    const f = D.frames; let best = null;
    f.forEach((x, i) => {
      if (x.state !== 'TRACK' || !x.locked || !x.in_fov) return;
      if (i < f.length * 0.45 || i > f.length * 0.82) return;
      if (x.err_urad > 210) return;
      const d = Math.abs(x.err_urad - 198);
      if (!best || d < best.d) best = { i, d, e: x.err_urad, ai: x.ai, mod: x.mod, t: x.t };
    });
    const el = document.getElementById('seek');
    el.value = best.i;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    return best;
  });
  console.log('picked', JSON.stringify(pick));
  await p.waitForTimeout(800);
  const shown = await p.evaluate(() => ({ state: document.getElementById('bigSt').textContent.trim(), err: document.getElementById('bigErr').textContent.trim() }));
  console.log('rendered', JSON.stringify(shown));
  await p.screenshot({ path: '/tmp/deckwork/console_new.png', clip: { x: 8, y: 125, width: 1504, height: 495 } });
  await b.close();
})();
