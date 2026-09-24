// R2-1 screenshots at 1366x768 and 1920x1080 (spec_editing 16 check 24 and the plan's "look at your screenshots"):
// the key selection with its bracket and the selection card, the Curves view, the timing editor, the loop menu, the
// undo history, the pose library (search, chips, part badges) and a play range.
//   node tools/checks/r2-1/shots.js --port 8851
'use strict';
const path = require('path');
const H = require('../lib/harness.js');
const L = require('./lib');

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function scene(page) {
  await page.evaluate(async () => {
    document.getElementById('home').classList.add('hidden');
    const A = await import('/js/animation.js');
    const T = (q, ax, d) => { const h = d * Math.PI / 360, s = Math.sin(h), n = Math.hypot(...ax); const r = [ax[0] / n * s, ax[1] / n * s, ax[2] / n * s, Math.cos(h)];
      return [q[3] * r[0] + q[0] * r[3] + q[1] * r[2] - q[2] * r[1], q[3] * r[1] - q[0] * r[2] + q[1] * r[3] + q[2] * r[0], q[3] * r[2] + q[0] * r[1] - q[1] * r[0] + q[2] * r[3], q[3] * r[3] - q[0] * r[0] - q[1] * r[1] - q[2] * r[2]]; };
    app.newScene(false, false, 'couple');
    const pr = (app.posePresets || []).find(x => x.group === 'couple' && /cowgirl/i.test(x.label)) || (app.posePresets || []).find(x => x.group === 'couple');
    app.setFrame(0);
    if (pr) app.applyPosePreset(pr, { quiet: true });
    await new Promise(r => setTimeout(r, 400));
    const [F, M] = app.store.project.sims;
    const key = (s, f, d, ease = 'auto') => { const p = JSON.parse(JSON.stringify(s.keys[0].pose)); p.rot.b__Spine1__ = T(p.rot.b__Spine1__, [0, 0, 1], d); p.rot.b__L_UpperArm__ = T(p.rot.b__L_UpperArm__, [1, 0, 0], d * 1.5); p.rot.b__Head__ = T(p.rot.b__Head__, [0, 1, 0], d * 0.6); s.keys = s.keys.filter(k => k.frame !== f); s.keys.push({ frame: f, ease, pose: p }); A.sortKeys(s.keys); };
    key(F, 15, 12, 'easeOut'); key(F, 30, -10); key(F, 45, 18, 'custom'); key(F, 60, -6); key(F, 75, 8);
    F.keys.find(k => k.frame === 45).curve = [0.25, 1.35, 0.5, 1];
    F.keys.find(k => k.frame === 30).type = 'breakdown';
    key(M, 20, -8); key(M, 40, 10, 'smooth'); key(M, 65, -12);
    app.refreshAll(); app.timeline.fit();
    app.selectSim(F.id);
  });
}

(async () => {
  const port = L.argPort();
  for (const [w, h] of [[1366, 768], [1920, 1080]]) {
    const { browser, page, logs } = await H.open(port, { w, h, memory: true });
    const shot = async name => { await sleep(350); await H.shot(page, path.join(L.OUT, `shot_${name}_${w}.png`)); };
    try {
      await scene(page);
      // a selection across both sims: the bracket, the ruler's diamonds, the selection card
      await page.evaluate(() => {
        const [F, M] = app.store.project.sims;
        app.showStep('motion');
        app.timeline.sel = new Set([`k|${F.id}|15`, `k|${F.id}|30`, `k|${F.id}|45`, `k|${M.id}|20`, `k|${M.id}|40`]);
        app.setFrame(33);
        app.selectionChanged();
        app.timeline.draw();
      });
      await shot('selection');
      // play only a part, the loop menu at the ruler's badge
      await page.evaluate(() => { app.setPlayRange([15, 45], { quiet: true }); app.timeline.draw(); });
      await shot('play_range');
      const b = await page.evaluate(() => { const g = app.timeline._geo.loopBadge, r = app.timeline.canvas.getBoundingClientRect(); return g ? { x: r.left + g.x, y: r.top + g.y } : null; });
      if (b) { await page.mouse.click(b.x, b.y); await shot('loop_menu'); await page.keyboard.press('Escape'); await page.mouse.click(5, 5); }
      await page.evaluate(() => { app.setPlayRange(null, { quiet: true }); document.querySelector('.ctx-menu')?.remove(); });
      // the Curves view of the middle back, then the timing editor of the custom key
      await page.evaluate(() => { const F = app.store.project.sims[0]; app.store.selected = { sim: F.id, bone: 'b__Spine1__' }; app.emitSelection(); app.setTimelineView('curves', { quiet: true }); app.setFrame(30); });
      await sleep(500);
      await page.evaluate(() => app.curves.frameAll());
      await shot('curves');
      await page.evaluate(() => { const F = app.store.project.sims[0]; const r = document.getElementById('curve-canvas').getBoundingClientRect(); app.timingEditor(F.id, 45, r.left + app.timeline.xAt(45) + 20, r.top - 120); });
      await shot('timing_editor');
      await page.keyboard.press('Escape');
      await page.evaluate(() => app.setTimelineView('keys', { quiet: true }));
      // the undo history
      const u = await page.evaluate(() => { const F = app.store.project.sims[0]; app.setFrame(50); app.keyPose(F.id); app.insertInBetween([F.id]); const r = document.getElementById('btn-undo').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
      await page.mouse.click(u.x, u.y, { button: 'right' });
      await shot('undo_history');
      await page.mouse.click(5, 5);
      // the pose library: My poses with a part pose and a folder, the search box
      await page.evaluate(async () => {
        const F = app.store.project.sims[0], now = Date.now();
        const pose = JSON.parse(JSON.stringify(F.keys[0].pose));
        const KO = await import('/js/keyops.js');
        const mine = [
          { id: 'mp_t1', label: 'Hands on hips', group: 'solo', part: 'hands', folder: 'Hands', fav: true, sims: [{ gender: 'FEMALE', pose: KO.maskPose(pose, new Set(KO.BODY_PARTS.hands)) }], created: now, updated: now },
          { id: 'mp_t2', label: 'Arched back', group: 'solo', folder: 'Favourites', sims: [{ gender: 'FEMALE', pose }], created: now, updated: now },
        ];
        app._setMyPoses(mine);
        app.thumbs.queue(app.posePresets.filter(x => x.mine), () => app.renderStep());
        app._poseMode = 'mine';
        app.showStep('pose');
      });
      await sleep(1500);
      await page.evaluate(() => app.renderStep());
      await shot('my_poses');
      const errs = logs.filter(l => l.type === 'pageerror');
      console.log(w, 'page errors:', errs.map(e => e.text));
    } finally { await browser.close(); }
  }
})().catch(e => { console.error(e); process.exit(1); });
