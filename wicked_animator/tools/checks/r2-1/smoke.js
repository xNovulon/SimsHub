// R2-1 quick smoke: the app starts, no page errors, the new parts exist; a screenshot at 1366x768 (and 1920x1080).
//   node tools/checks/r2-1/smoke.js --port 8851
'use strict';
const path = require('path');
const H = require('../lib/harness.js');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const rows = [];
  for (const [w, hgt] of [[1366, 768], [1920, 1080]]) {
    const { browser, page, logs } = await H.open(port, { w, h: hgt });
    try {
      const r = await page.evaluate(async () => {
        const app = window.app;
        return { curves: !!app.curves, refs: !!app.refs, seg: !!document.getElementById('tl-view-seg'), autoCurve: app.store.project.autoCurve,
          events: Array.isArray(app.store.project.events), cmds: app._editCommands().length };
      });
      rows.push([`${w} app parts`, r.curves && r.refs && r.seg && r.autoCurve === 'clamped' && r.events, r]);
      await page.evaluate(() => { app.hideHomeForTest = true; document.getElementById('home').classList.add('hidden'); app.showStep('pose'); });
      await H.sleep(800);
      await H.shot(page, path.join(L.OUT, `smoke_pose_${w}.png`));
      await page.evaluate(() => { app.setTimelineView('curves'); });
      await H.sleep(900);
      await H.shot(page, path.join(L.OUT, `smoke_curves_${w}.png`));
      const errs = logs.filter(l => l.type === 'pageerror' || (l.type === 'error' && !/favicon/.test(l.text)));
      rows.push([`${w} no page errors`, !errs.length, errs.map(e => e.text).slice(0, 5)]);
    } finally { await browser.close(); }
  }
  process.exit(L.table(rows, 'R2-1 smoke') ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
