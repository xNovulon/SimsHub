// R2-3 spec_bodies 6.5: Look at, Tremble and Follow-through (lag) loop without a jump, look-at points at the target,
// and the tremble's shake has the promised rhythm.
//   - look + tremble + lag on a looping 90-frame project: apply(0) and apply(90) give the same pose within 0.1 deg for
//     every bone, and the step from apply(89) to apply(0) is no bigger than the largest step inside the loop
//   - look toward a target inside 70 deg: the head's forward is within 5 deg of the eyes-to-target direction, and the
//     eye values stay within +-1
//   - the tremble's shake crosses zero n1 x 2 times per loop (+-2), n1 = round(loop seconds x 6.5 Hz)
//   - the Motion step shows the Look at / Tremble cards and the Follow-through sliders (which write sim.lag)
//   node tools/checks/r2-3/motions.js --port 8853
'use strict';
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const rows = [];
  const { browser, page, logs } = await L.appPage(port, { w: 1366, h: 768 });
  try {
    await page.waitForFunction('app.posePresets && app.posePresets.length > 0 && window.wickedScene', { timeout: 180000 });
    // ---- the loop joins
    const loop = await page.evaluate(async () => {
      const magic = await import('/js/magic.js'), home = await import('/js/home.js');
      home.hideHome(app);
      await magic.makeMagic(app, { recipe: 'cowgirl', place: 'double_bed', intensity: 0.6, seconds: 3 });
      app.setPlaying(false); app.showcase(false); if (app.vp.stopCamera) app.vp.stopCamera();
      const p = app.store.project;
      const [her, him] = p.sims;
      // look (both), tremble on her legs, lag on both
      for (const s of p.sims) if (!(s.layers || []).some(l => l.type === 'look')) app.addLayer(s.id, 'look');
      app.addLayer(her.id, 'tremble');
      const tr = her.layers.find(l => l.type === 'tremble');
      tr.params.amount = 3; tr.params.parts = 'body';
      her.lag = { arms: 3, head: 2 }; him.lag = { arms: 2, head: 4 };
      app.pipeline.simulateIfNeeded(true);
      const grab = frame => {
        app.pipeline.apply(frame, { physics: false, overrides: false });
        const out = [];
        for (const e of app.pipeline.entries()) for (const b of e.v.bones) out.push(b.quaternion.clone());
        return out;
      };
      // the rig's and the ready poses' quaternions are not all exactly unit length: compare them normalised
      const ang = (a, b) => 2 * Math.acos(Math.min(1, Math.abs(a.dot(b)) / ((a.length() * b.length()) || 1))) * 180 / Math.PI;
      const maxDiff = (A, B) => { let m = 0; for (let i = 0; i < A.length; i++) m = Math.max(m, ang(A[i], B[i])); return m; };
      const f0 = grab(0), f90 = grab(p.length), f89 = grab(p.length - 1);
      let inside = 0, prev = grab(0);
      for (let k = 1; k < p.length; k++) { const cur = grab(k); inside = Math.max(inside, maxDiff(prev, cur)); prev = cur; }
      app.applyPoses(false);
      return { wrap: maxDiff(f0, f90), seam: maxDiff(f89, f0), inside, length: p.length, layers: p.sims.map(s => s.layers.map(l => l.type).join('+')) };
    });
    rows.push([`look + tremble + lag: apply(0) = apply(${loop.length}) within 0.1 deg`, loop.wrap <= 0.1, `${loop.wrap.toFixed(4)} deg (layers ${loop.layers.join(' / ')})`]);
    rows.push(['the step over the loop point is no bigger than the largest step inside', loop.seam <= loop.inside + 1e-6, `seam ${loop.seam.toFixed(2)} deg, inside max ${loop.inside.toFixed(2)} deg`]);

    // ---- look at: the head points at the target, the eyes stay in range
    const look = await page.evaluate(async () => {
      const THREE = await import('three'), mo = await import('/js/motion.js'), pm = await import('/js/posemath.js');
      app.newScene(false, false);
      const [a, b] = app.store.project.sims;
      // the partner a little to the side and lower: about 30 degrees away from where the head looks
      app.transformSim(b.id, { offset: new THREE.Vector3(0, -0.25, 0.4) });
      app.addLayer(a.id, 'look');
      const layer = a.layers.find(l => l.type === 'look');
      const all = app.pipeline.entries(), e = all.find(x => x.sim.id === a.id);
      const res = [];
      for (const target of ['face', 'chest', 'groin']) {
        layer.params.target = target;
        for (const x of all) app.pipeline.base(x, 0);
        const v = e.v;
        const before = new THREE.Vector3(0, 1, 0).applyQuaternion(pm.spaceQuat(v, v.bone('b__Head__')));
        const ctx = { frame: 0, length: app.store.project.length, fps: 30, loop: true, others: all.filter(x => x !== e) };
        const tgt = mo.lookTarget(v, { ...layer.params }, ctx);
        const eyes0 = pm.spacePos(v, v.bone('b__L_Eye__')).add(pm.spacePos(v, v.bone('b__R_Eye__'))).multiplyScalar(0.5);
        const startAngle = before.angleTo(tgt.clone().sub(eyes0)) * 180 / Math.PI;
        const eyesOut = mo.applyLayer(v, layer, ctx);
        const fwd = new THREE.Vector3(0, 1, 0).applyQuaternion(pm.spaceQuat(v, v.bone('b__Head__')));
        const eyes = pm.spacePos(v, v.bone('b__L_Eye__')).add(pm.spacePos(v, v.bone('b__R_Eye__'))).multiplyScalar(0.5);
        const err = fwd.angleTo(tgt.clone().sub(eyes)) * 180 / Math.PI;
        res.push({ target, startAngle, err, eyes: eyesOut });
      }
      app.applyPoses();
      return res;
    });
    for (const r of look) {
      rows.push([`look at the partner's ${r.target} (${r.startAngle.toFixed(0)} deg away): head forward within 5 deg`, r.startAngle <= 70 ? r.err < 5 : true, `${r.err.toFixed(2)} deg`]);
      rows.push([`look at the partner's ${r.target}: eye values within +-1`, !!r.eyes && Math.abs(r.eyes.lookUp) <= 1 && Math.abs(r.eyes.lookSide) <= 1, JSON.stringify(r.eyes && { up: +r.eyes.lookUp.toFixed(3), side: +r.eyes.lookSide.toFixed(3) })]);
    }

    // ---- tremble rhythm (in the bake: what the game gets)
    const tr = await page.evaluate(async () => {
      const THREE = await import('three'), mo = await import('/js/motion.js');
      app.newScene(false, false);
      const s = app.store.project.sims[0];
      const bakeCalf = () => app.pipeline.bake().tracks[0].b__L_Thigh__.r.map(q => new THREE.Quaternion().fromArray(q));
      const off = bakeCalf();
      app.addLayer(s.id, 'tremble');
      const layer = s.layers.find(l => l.type === 'tremble');
      const on = bakeCalf();
      const p = app.store.project;
      const n1 = mo.trembleCycles(p.length, p.fps || 30, layer.params.speed)[0];
      // the shake about the tremble's axis (local z plus 0.35 x): its sign from the delta's z component
      const d = on.map((q, k) => off[k].clone().invert().multiply(q)).map(q => (q.w < 0 ? -1 : 1) * q.z);
      const mean = d.reduce((a, x) => a + x, 0) / d.length;
      let crossings = 0;
      for (let k = 0; k < d.length; k++) if ((d[k] - mean > 0) !== (d[(k + 1) % d.length] - mean > 0)) crossings++;
      const peak = Math.max(...d.map(x => Math.abs(2 * Math.asin(Math.min(1, Math.abs(x))) * 180 / Math.PI)));
      return { n1, crossings, peak, frames: p.length };
    });
    rows.push([`tremble: ${tr.n1 * 2} zero crossings per loop (+-2)`, Math.abs(tr.crossings - tr.n1 * 2) <= 2, `${tr.crossings} crossings over ${tr.frames} frames, peak ${tr.peak.toFixed(2)} deg`]);

    // ---- the Motion step
    const ui = await page.evaluate(async () => {
      const s = app.store.sim() || app.store.project.sims[0];
      app.selectSim(s.id);
      if (!s.layers.some(l => l.type === 'look')) app.addLayer(s.id, 'look');
      app._openLayer = s.layers.find(l => l.type === 'look').id;
      app.showStep('motion');
      const t0 = performance.now(); app.renderStep(); const ms = performance.now() - t0;
      const root = document.getElementById('panel-body');
      const txt = root.textContent;
      const sliders = [...root.querySelectorAll('.section')].find(x => /Follow-through/.test(x.textContent));
      const range = sliders && sliders.querySelector('input[type=range]');
      if (range) { range.value = 4; range.dispatchEvent(new Event('input')); range.dispatchEvent(new Event('change')); }
      return { ms, look: /Look at/.test(txt) && /Eyes follow/.test(txt), tremble: /Tremble/.test(txt), follow: !!sliders, lag: s.lag || null };
    });
    await L.shot(page, 'motions_step.png');
    rows.push(['Motion step: the Look at card (target, who, eyes)', ui.look]);
    rows.push(['Motion step: Tremble in the catalogue', ui.tremble]);
    rows.push(['Motion step: Follow-through sliders write sim.lag', ui.follow && ui.lag && ui.lag.arms === 4, JSON.stringify(ui.lag)]);
    rows.push(['Motion step renders under 50 ms', ui.ms < 50, `${ui.ms.toFixed(1)} ms`]);
    const errs = logs.filter(l => l.type === 'pageerror' || (l.type === 'error' && !/Failed to load resource/.test(l.text)));
    rows.push(['no page errors', !errs.length, errs.slice(0, 3).map(e => e.text).join(' | ')]);
    process.exitCode = L.table(rows, 'R2-3: look at, tremble, follow-through (spec_bodies 6.5)') ? 0 : 1;
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
