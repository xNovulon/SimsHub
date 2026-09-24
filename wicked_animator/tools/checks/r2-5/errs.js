// prints the page's errors after load (R2-5 debugging helper)
const H = require('../lib/harness.js');
(async () => {
  const { browser, page, logs } = await H.open(+process.argv[2] || 8855, { w: 1366, h: 768, beforeLoad: async p => {
    p.on('response', r => { if (r.status() >= 400) console.log('HTTP', r.status(), r.url()); });
  } });
  const s = await page.evaluate(async () => { await new Promise(r => setTimeout(r, 3000)); return { type: typeof window.app, ctor: window.app && window.app.constructor && window.app.constructor.name, presets: window.app && app.posePresets && app.posePresets.length, faces: !!(window.app && app.__faces2) }; });
  console.log(JSON.stringify(s));
  for (const l of logs) if (/error|warn/i.test(l.type)) console.log(l.type, l.text.slice(0, 400));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
