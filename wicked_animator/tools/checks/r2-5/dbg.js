// R2-5 debugging helper: runs a snippet file in the app page
const H = require('../lib/harness.js');
const fs = require('fs');
(async () => {
  const { browser, page, logs } = await H.open(+process.argv[2] || 8872, { w: 1366, h: 768 });
  await page.evaluate(async () => { document.getElementById('home').classList.add('hidden'); for (let i = 0; i < 100 && !(app.posePresets && app.posePresets.length); i++) await new Promise(r => setTimeout(r, 100)); });
  const src = fs.readFileSync(process.argv[3], 'utf8');
  const r = await page.evaluate(new Function('return (async () => {' + src + '})()'));
  console.log(JSON.stringify(r, null, 1));
  for (const l of logs) if (l.type === 'pageerror') console.log('pageerror', l.text);
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
