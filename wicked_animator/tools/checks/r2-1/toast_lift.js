// R2-1: at 1366x768 the "pose set" toast never covers the clipping card (R2-3): toasts rise above it while it is open.
//   node tools/checks/r2-1/toast_lift.js --port 8851
'use strict';
const path = require('path');
const H = require('../lib/harness.js');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const rows = [];
  const { browser, page, logs } = await H.open(port, { w: 1366, h: 768, memory: true });
  try {
    await page.evaluate(async () => {
      document.getElementById('home').classList.add('hidden');
      app.newScene(false, false, 'couple');
      app.showStep('pose');
      const pr = app.posePresets.find(x => x.group === 'couple' && /cowgirl/i.test(x.label)) || app.posePresets.find(x => x.group === 'couple');
      app.applyPosePreset(pr, { quiet: true });
      await app.checkClipping({ step: 2 });
    });
    await H.sleep(500);
    const r = await page.evaluate(async () => {
      const pr = app.posePresets.find(x => x.group === 'couple');
      app.applyPosePreset(pr);                     // its "pose set" toast
      await new Promise(res => setTimeout(res, 450));   // (the toast and the card have finished popping in)
      const card = document.getElementById('clip-card'), t = document.querySelector('#toasts .toast');
      const a = card && card.getBoundingClientRect(), b = t && t.getBoundingClientRect();
      const overlap = a && b ? Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)) * Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) : -1;
      return { card: !!card, toast: !!t, overlap, lift: getComputedStyle(document.documentElement).getPropertyValue('--toast-lift'), cardTop: a && Math.round(a.top), toastBottom: b && Math.round(b.bottom), toastTop: b && Math.round(b.top) };
    });
    await H.sleep(250);
    await H.shot(page, path.join(L.OUT, 'shot_toast_over_clip_card_1366.png'));
    rows.push(['the clipping card is open and a toast shows', r.card && r.toast, r]);
    rows.push(['the toast sits above the card (no overlap)', r.overlap === 0 && r.toastBottom <= r.cardTop, r]);
    const back = await page.evaluate(async () => { document.querySelector('#clip-card .icon-btn')?.click(); await new Promise(res => setTimeout(res, 50)); return getComputedStyle(document.documentElement).getPropertyValue('--toast-lift').trim(); });
    rows.push(['closing the card puts toasts back down', back === '0px', back]);
    const errs = logs.filter(l => l.type === 'pageerror');
    rows.push(['no page errors', !errs.length, errs.map(e => e.text).slice(0, 3)]);
  } finally { await browser.close(); }
  process.exit(L.table(rows, 'R2-1 toasts above the clipping card') ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
