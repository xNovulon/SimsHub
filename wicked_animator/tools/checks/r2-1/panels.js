// R2-1 gate fix: no step-panel button label is cut off (Pose / Face / Sounds steps and every other step) and the Next
// buttons have short labels. Checks every .btn in the step panel (its text fits: scrollWidth <= clientWidth) at 1366x768
// and 1920x1080, and takes pictures of the Pose (My poses), Face and Sounds panels with their buttons in view.
//   node tools/checks/r2-1/panels.js --port 8851
'use strict';
const path = require('path');
const H = require('../lib/harness.js');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const rows = [];
  for (const [w, hgt] of [[1366, 768], [1920, 1080]]) {
    const { browser, page, logs } = await H.open(port, { w, h: hgt, memory: true });
    try {
      await page.evaluate(async () => {
        document.getElementById('home').classList.add('hidden');
        app.newScene(false, false, 'couple');
        const pr = app.posePresets.find(x => x.group === 'couple');
        app.applyPosePreset(pr, { quiet: true });
        const F = app.store.project.sims[0], now = Date.now();
        app._setMyPoses([{ id: 'mp_p1', label: 'Test pose', group: 'solo', sims: [{ gender: 'FEMALE', pose: F.keys[0].pose }], created: now, updated: now }]);
        app.copyPose(F.id);
      });
      const cut = [];
      for (const step of ['scene', 'pose', 'motion', 'body', 'face', 'sounds', 'details', 'share']) {
        const r = await page.evaluate(async step => {
          if (step === 'pose') app._poseMode = 'mine';
          app.showStep(step);
          await new Promise(res => setTimeout(res, 350));
          const out = [];
          // the label (its text and icon, not the decorative glow layers of Magic / primary buttons) inside the button's
          // padding box
          for (const b of document.querySelectorAll('#panel-body .btn, #panel-foot .btn')) {
            if (!b.offsetParent) continue;
            const rg = document.createRange(); rg.selectNodeContents(b);
            const t = rg.getBoundingClientRect(), r = b.getBoundingClientRect();
            if (t.left < r.left - 0.5 || t.right > r.right + 0.5 || t.top < r.top - 0.5 || t.bottom > r.bottom + 0.5) out.push({ text: b.textContent.trim(), text_x: [Math.round(t.left), Math.round(t.right)], btn_x: [Math.round(r.left), Math.round(r.right)], text_y: [Math.round(t.top), Math.round(t.bottom)], btn_y: [Math.round(r.top), Math.round(r.bottom)] });
          }
          const next = [...document.querySelectorAll('#panel-foot .btn.primary')].map(b => b.textContent.trim());
          return { out, next };
        }, step);
        for (const x of r.out) cut.push({ step, ...x });
        if (step === 'face') rows.push([`${w}: the Face step's Next button reads "Next: Sounds"`, r.next.includes('Next: Sounds'), r.next]);
        if (['pose', 'face', 'sounds'].includes(step)) {
          // the panel scrolled so its buttons show
          const want = { pose: 'Add poses from a file', face: 'Make every expression editable', sounds: 'Add random voice' }[step];
          await page.evaluate(want => {
            const b = [...document.querySelectorAll('#panel-body .btn')].find(x => x.textContent.includes(want)) || document.querySelector('#panel-body .btn-grid');
            const body = document.getElementById('panel-body');
            if (b) body.scrollTop += b.getBoundingClientRect().top - body.getBoundingClientRect().top - body.clientHeight / 3;
          }, want);
          await H.sleep(250);
          await H.shot(page, path.join(L.OUT, `panel_${step}_${w}.png`));
        }
      }
      rows.push([`${w}: no step-panel button is cut off (8 steps)`, cut.length === 0, cut.slice(0, 8)]);
      const errs = logs.filter(l => l.type === 'pageerror');
      rows.push([`${w}: no page errors`, !errs.length, errs.map(e => e.text).slice(0, 3)]);
    } finally { await browser.close(); }
  }
  process.exit(L.table(rows, 'R2-1 step panels: labels fit') ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
