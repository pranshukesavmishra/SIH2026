const { chromium } = require('playwright');
(async () => {
  const name = process.argv[2];
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const p = await b.newPage({ viewport: { width: 2320, height: 1040 }, deviceScaleFactor: 2 });
  await p.goto('file:///tmp/deckwork/art/' + name + '.html', { waitUntil: 'networkidle' });
  await p.waitForTimeout(700);
  const over = await p.evaluate(() => ({ h: document.body.scrollHeight, w: document.body.scrollWidth }));
  console.log(name, 'content', JSON.stringify(over));
  await p.screenshot({ path: '/tmp/deckwork/art/' + name + '.png', clip: { x:0, y:0, width:2320, height:1040 } });
  await b.close();
})();
