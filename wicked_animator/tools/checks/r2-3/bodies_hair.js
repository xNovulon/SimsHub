// R2-3 spec_bodies 8.6 and 9.5: other bodies (WickedWhims' penis sliders, Tray sims) and hair.
//   - /api/body_variant length=1: Penis_Mid01 rests 25.5 +- 1 mm further along the shaft than length=0; length=-1:
//     30 +- 1 mm shorter; the penis tip on the posed body at frame 0 moves by about the same; which tilt aims up
//   - trying 3 Tray sims and 4 sizes while it plays ("change body every loop"), then stopping: JSON.stringify(project)
//     is byte-identical, and the bake (what Send to game writes) equals the one taken before
//   - a trial Tray body shows that sim's own hair; the Body step renders under 50 ms with the new sections
//   - hair: 5 Tray sims (3 CC hairs, 2 EA hairs) each show hair on the head; with Head bob playing, the hair's centre
//     stays within 2 cm of where it sits on the head through the loop; a hair that isn't installed shows nothing and
//     no error; the first load of a CC hair < 1.5 s and from the cache < 100 ms; new sims get the default hair
//   node tools/checks/r2-3/bodies_hair.js --port 8853
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

// Tray sims of this PC (adults): CC hair x3, EA hair x2, one whose hair is not installed, one for the cold hair load
const TRAY = {
  cc: [['0x003516eecbb510e6', 0], ['0x00841570bfc5017f', 0], ['0x008414ba05c70038', 0]],
  ea: [['0x003d1736d3ca0019', 0], ['0x003014ffac34005b', 0]],
  missing: ['0x00841570b71b00c1', 0],
  cold: ['0x00841570be660169', 1],
};

(async () => {
  const port = L.argPort();
  const base = `http://127.0.0.1:${port}`;
  const rows = [];
  // ---- cold and cached hair load (before the page asks for it)
  const hairOf = async (tray, index) => (await (await fetch(`${base}/api/body_variant?tray=${tray}&index=${index}`)).json()).hair;
  const cold = await hairOf(...TRAY.cold);
  if (cold && cold.casp) {
    const inst = cold.casp.replace(/^0x/, '').padStart(16, '0');
    const dir = path.join(L.ROOT, 'cache', 'hair');
    for (const f of fs.existsSync(dir) ? fs.readdirSync(dir) : []) if (f.startsWith(`${inst}_v`) || f.startsWith(`hair_${inst}_v`)) fs.unlinkSync(path.join(dir, f));
    const t0 = Date.now(); const a = await (await fetch(`${base}/api/hair?casp=${cold.casp}`)).json(); const first = Date.now() - t0;
    const t1 = Date.now(); await (await fetch(`${base}/api/hair?casp=${cold.casp}`)).json(); const again = Date.now() - t1;
    // the same hair on its sim's own body shape (what the app asks for a Tray sim): the shaping is extra
    const t2 = Date.now(); const sh = await (await fetch(`${base}/api/hair?tray=${TRAY.cold[0]}&index=${TRAY.cold[1]}`)).json(); const shaped = Date.now() - t2;
    rows.push([`a CC hair's first load under 1.5 s (${(a.name || '').slice(0, 40)})`, first < 1500, `${first} ms (${a.origin}, ${a.meshes.map(m => m.positions.length / 3).join('+')} vertices)`]);
    rows.push(['the same hair again (cache) under 100 ms', again < 100, `${again} ms`]);
    rows.push(['... fitted to its sim\'s body shape: first time under 1.5 s', shaped < 1500 && sh.meshes && sh.meshes.length > 0, `${shaped} ms (${sh.meshes ? sh.meshes.length : 0} mesh)`]);
  } else rows.push(['a CC hair to time', false, 'none found']);

  // ---- the genital sliders on the rest pose
  const variant = async q => (await (await fetch(`${base}/api/body_variant?frame=ym&${q}`)).json()).body;
  const [b0, bp, bm, tu, td] = await Promise.all(['', 'length=1', 'length=-1', 'tilt=1', 'tilt=-1'].map(variant));
  const { browser, page, logs } = await L.appPage(port, { w: 1366, h: 768 });
  try {
    await page.waitForFunction('app.posePresets && app.posePresets.length > 0 && window.wickedScene', { timeout: 180000 });
    const rest = await page.evaluate(async (bodies) => {
      const THREE = await import('three'), { Sim } = await import('/js/sim.js');
      const at = body => { const v = new Sim(app.assets.rig, body); v.group.updateMatrixWorld(true); const o = {}; for (const n of ['b__Penis_Base', 'b__Penis_Mid01', 'b__Penis_Tip']) o[n] = v.worldPos(n); v.dispose(); return o; };
      const [z, p, m, u, d] = bodies.map(at);
      const shaft = z.b__Penis_Mid01.clone().sub(z.b__Penis_Base).normalize();
      const along = x => x.b__Penis_Mid01.clone().sub(z.b__Penis_Mid01).dot(shaft) * 1000;
      return { plus: along(p), minus: along(m), tiltUp: u.b__Penis_Tip.y - d.b__Penis_Tip.y, deltas: [Object.keys(bodies[1].rest_delta || {}).length, Object.keys(bodies[2].rest_delta || {}).length] };
    }, [b0, bp, bm, tu, td]);
    rows.push(['length +1: Penis_Mid01 rests 25.5 +- 1 mm further along the shaft', Math.abs(rest.plus - 25.5) <= 1, `${rest.plus.toFixed(1)} mm (${rest.deltas[0]} bones moved)`]);
    rows.push(['length -1: 30 +- 1 mm shorter', Math.abs(rest.minus + 30) <= 1, `${rest.minus.toFixed(1)} mm`]);
    rows.push(['tilt: which SMOD aims up (recorded)', true, rest.tiltUp > 0 ? `+1 aims up (tip ${(rest.tiltUp * 1000).toFixed(0)} mm higher than -1)` : `-1 aims up (tip ${(-rest.tiltUp * 1000).toFixed(0)} mm higher than +1)`]);

    // ---- trying bodies on a posed animation
    const trial = await page.evaluate(async () => {
      const THREE = await import('three');
      const magic = await import('/js/magic.js'), home = await import('/js/home.js'), B = await import('/js/bodies.js');
      home.hideHome(app);
      await magic.makeMagic(app, { recipe: 'cowgirl', place: 'double_bed', intensity: 0.6, seconds: 3 });
      app.setPlaying(false); app.showcase(false); if (app.vp.stopCamera) app.vp.stopCamera();
      await new Promise(r => setTimeout(r, 800));
      const p = app.store.project;
      const him = p.sims.find(s => s.frame === 'ym'), her = p.sims.find(s => s.frame === 'yf');
      const before = JSON.stringify(p);
      const bakeBefore = JSON.stringify(app.bake());
      const tipAt = () => { app.pipeline.apply(0, { physics: false, overrides: false }); const v = app.simViews.get(him.id); v.group.updateMatrixWorld(true); return v.worldPos('b__Penis_Tip'); };
      const own = tipAt();
      await app.tryBody(him.id, { kind: 'size', preset: 'small' });
      const small = tipAt();
      const trialKey = app.trial.get(him.id) && app.trial.get(him.id).bodyKey;
      const moved = small.distanceTo(own) * 1000;
      // the Body step with the sections, while trying
      app.selectSim(him.id);
      app.showStep('body');
      const t0 = performance.now(); app.renderStep(); const renderMs = performance.now() - t0;
      const banner = document.getElementById('vp-trial');
      const bannerText = banner && !banner.classList.contains('hidden') ? banner.textContent : '';
      // a Tray body on her, with its own hair
      const tray = (await B.traySims()).filter(t => t.frame === 'yf');
      await app.tryBody(her.id, { kind: 'tray', tray: tray[0].tray, index: tray[0].index, name: tray[0].name });
      await new Promise(r => setTimeout(r, 1500));
      const vHer = app.simViews.get(her.id);
      const trayHair = { key: vHer.hairKey, parts: (vHer.parts || []).length, name: vHer.hairName };
      // cycle: 3 Tray sims and 4 sizes while playing
      const seen = new Set();
      for (const t of tray.slice(1, 3)) { await app.tryBody(her.id, { kind: 'tray', tray: t.tray, index: t.index, name: t.name }); seen.add(app.trial.get(her.id).bodyKey); }
      for (const k of ['small', 'average', 'large', 'xl']) { await app.tryBody(him.id, { kind: 'size', preset: k }); seen.add((app.trial.get(him.id) || {}).bodyKey || 'own'); }
      app.speed = 4;
      app.cycleBodies(true, him.id);
      app.setPlaying(true);
      const keysSeen = new Set();
      const t1 = performance.now();
      while (performance.now() - t1 < 4500) { await new Promise(r => setTimeout(r, 100)); keysSeen.add((app.trial.get(him.id) || {}).bodyKey || 'own'); }
      app.setPlaying(false);
      app.speed = 1;
      app.cycleBodies(false, him.id);
      app.endTrial();
      await new Promise(r => setTimeout(r, 300));
      const after = JSON.stringify(p);
      const bakeAfter = JSON.stringify(app.bake());
      return { same: before === after, bakeSame: bakeBefore === bakeAfter, moved, trialKey, renderMs, bannerText, trayHair, seen: [...seen], cycled: [...keysSeen], dirty: app.store.dirty,
        firstDiff: before === after ? -1 : [...before].findIndex((c, i) => c !== after[i]) };
    });
    // the tip moves about as much as Mid01 does at rest for the same values (small = length -1, girth -0.6, balls -0.5)
    const small = (await (await fetch(`${base}/api/body_variant?frame=ym&length=-1&girth=-0.6&balls=-0.5`)).json()).body;
    const restSmall = await page.evaluate(async (b0, bs) => {
      const { Sim } = await import('/js/sim.js');
      const tip = body => { const v = new Sim(app.assets.rig, body); v.group.updateMatrixWorld(true); const x = v.worldPos('b__Penis_Tip'); v.dispose(); return x; };
      return tip(bs).distanceTo(tip(b0)) * 1000;
    }, b0, small);
    rows.push(['"Small" on the posed body: the tip moves about as much as at rest (+-5 mm)', Math.abs(trial.moved - restSmall) <= 5, `posed ${trial.moved.toFixed(1)} mm, rest ${restSmall.toFixed(1)} mm (${trial.trialKey})`]);
    rows.push(['the trial pill says what is shown', /Trying/.test(trial.bannerText), trial.bannerText]);
    rows.push(['a trial Tray body wears that sim\'s own hair', trial.trayHair.parts > 0 && /^c:/.test(trial.trayHair.key || ''), JSON.stringify(trial.trayHair)]);
    rows.push(['"Change body every loop" changes the body at the loop point while playing', trial.cycled.length >= 3, `${trial.cycled.length} bodies seen: ${trial.cycled.join(', ')}`]);
    rows.push(['after trying 3 Tray sims and 4 sizes: the project is byte-identical', trial.same, trial.same ? `${trial.seen.length} bodies tried` : `first difference at ${trial.firstDiff}`]);
    rows.push(['... and the bake (Send to game) is identical', trial.bakeSame]);
    rows.push(['Body step with hair and other bodies renders under 50 ms', trial.renderMs < 50, `${trial.renderMs.toFixed(1)} ms`]);
    await L.shot(page, 'bodies_after_trial.png');

    // ---- hair on 5 Tray sims, head bob playing
    const hair = await page.evaluate(async (TRAY) => {
      const THREE = await import('three');
      app.newScene(false, false, 'solo');
      await new Promise(r => setTimeout(r, 600));
      const add = async ([tray, index], name) => { await app.addTraySim(tray, index, name); return app.store.project.sims[app.store.project.sims.length - 1]; };
      const list = [];
      for (const t of TRAY.cc) list.push({ kind: 'CC', sim: await add(t, 'cc') });
      for (const t of TRAY.ea) list.push({ kind: 'EA', sim: await add(t, 'ea') });
      const miss = await add(TRAY.missing, 'missing');
      // the solo scene's own sim leaves; the rest stand in a row
      app.removeSim(app.store.project.sims[0].id);
      await new Promise(r => setTimeout(r, 3500));                     // bodies and hair arrive
      // where the hair's top sits against the crown, along the head's up axis, on the drawn vertices (hair_fit.js does
      // this for every Tray sim)
      const fit = v => {
        const head = v.bone('b__Head__'), hi = v.skeleton.bones.indexOf(head), body = v.meshes[0];
        body.updateMatrixWorld(true);
        const M = new THREE.Matrix4().multiplyMatrices(body.matrixWorld, head.matrixWorld).multiply(v.skeleton.boneInverses[hi]);
        const up = new THREE.Vector3(0, 1, 0).transformDirection(M), tmp = new THREE.Vector3();
        let crown = -Infinity, top = -Infinity;
        for (const m of v.meshes) {
          const si = m.geometry.attributes.skinIndex, sw = m.geometry.attributes.skinWeight;
          for (let i = 0; i < m.geometry.attributes.position.count; i++) {
            let w = 0;
            for (let k = 0; k < 4; k++) if (si.getComponent(i, k) === hi) w += sw.getComponent(i, k);
            if (w >= 0.5) { m.getVertexPosition(i, tmp); m.localToWorld(tmp); crown = Math.max(crown, tmp.dot(up)); }
          }
        }
        for (const m of (v.parts || []).filter(q => !q.userData.soft)) {
          for (let i = 0; i < m.geometry.attributes.position.count; i++) { m.getVertexPosition(i, tmp); m.localToWorld(tmp); top = Math.max(top, tmp.dot(up)); }
        }
        return top - crown;
      };
      app.applyPoses();
      const fits = new Map(list.map(x => [x.sim.id, fit(app.simViews.get(x.sim.id))]));
      for (const x of list) app.addLayer(x.sim.id, 'headbob');
      const p = app.store.project;
      const out = [];
      for (const x of list) {
        const v = app.simViews.get(x.sim.id);
        const hairMesh = (v.parts || []).find(m => !m.userData.soft);
        if (!hairMesh) { out.push({ kind: x.kind, name: x.sim.label, parts: 0 }); continue; }
        const n = hairMesh.geometry.attributes.position.count, tmp = new THREE.Vector3();
        const centres = [];
        for (let k = 0; k < p.length; k += 5) {
          app.pipeline.apply(k, { physics: false, overrides: false });
          v.group.updateMatrixWorld(true);
          const c = new THREE.Vector3(); let m = 0;
          for (let i = 0; i < n; i += 7) { hairMesh.getVertexPosition(i, tmp); c.add(tmp); m++; }
          c.multiplyScalar(1 / m);
          const head = v.bone('b__Head__');
          centres.push(head.worldToLocal(v.space.localToWorld(c)));
        }
        const mean = centres.reduce((a, c) => a.add(c), new THREE.Vector3()).multiplyScalar(1 / centres.length);
        const drift = Math.max(...centres.map(c => c.distanceTo(mean)));
        // does it sit on the head? its top 2 cm below to 8 cm above the crown
        out.push({ kind: x.kind, name: v.hairName, parts: v.parts.filter(m => m.userData.role === 'hair').length, drift, fit: fits.get(x.sim.id), ms: v.hairMs });
      }
      const vm = app.simViews.get(miss.id);
      app.applyPoses();
      return { out, missing: { parts: (vm.parts || []).filter(m => m.userData.role === 'hair').length, hairKey: vm.hairKey } };   // (a Tray sim arrives dressed: count its hair only)
    }, TRAY);
    for (const h of hair.out) {
      rows.push([`${h.kind} hair on a Tray sim: its top sits on the crown (-2 to +8 cm)`, h.parts > 0 && h.fit >= -0.02 && h.fit <= 0.08, `${(h.name || '').slice(0, 44)} · ${h.parts} meshes · top ${h.fit !== undefined ? (h.fit * 100).toFixed(1) : '-'} cm from the crown`]);
      rows.push([`${h.kind} hair: stays on the head through Head bob (< 2 cm)`, h.drift !== undefined && h.drift < 0.02, h.drift !== undefined ? `${(h.drift * 1000).toFixed(1)} mm` : 'no hair']);
    }
    rows.push(['a Tray sim whose hair is not installed: no hair, no error', hair.missing.parts === 0, JSON.stringify(hair.missing)]);
    // close-ups
    const sims = await page.evaluate(() => app.store.project.sims.map(s => s.id));
    for (let i = 0; i < Math.min(5, sims.length); i++) {
      await page.evaluate(async id => {
        const THREE = await import('three');
        const v = app.simViews.get(id);
        app.setPlaying(false); app.setFrame(0);
        v.group.updateMatrixWorld(true);
        app.vp.frame(v.worldPos('b__Head__').add(new THREE.Vector3(0, 0.08, 0)), 0.22, new THREE.Vector3(0.5, 0.15, 1));
        await new Promise(r => setTimeout(r, 1300));
      }, sims[i]);
      await L.shot(page, `hair_tray_${i + 1}.png`);
    }
    // the app's own sims: the default hair, and a pick in the Body step
    const own = await page.evaluate(async () => {
      app.newScene(false, false);
      await new Promise(r => setTimeout(r, 2500));
      const res = app.store.project.sims.map(s => ({ frame: s.frame, hair: s.hair && s.hair.name, parts: (app.simViews.get(s.id).parts || []).length }));
      const s = app.store.project.sims[0];
      app.selectSim(s.id);
      app.showStep('body');
      await new Promise(r => setTimeout(r, 400));
      const chip = [...document.querySelectorAll('.hair-row .chipbtn')].find(b => /Long waves/.test(b.textContent));
      if (chip) chip.click();
      await new Promise(r => setTimeout(r, 1500));
      const dots = document.querySelectorAll('.hair-dots button').length;
      return { res, picked: s.hair, parts: (app.simViews.get(s.id).parts || []).length, dots, undo: app.store.undo.length };
    });
    rows.push(['new sims get the default hair of their body', own.res.every(r => r.hair && r.parts > 0), JSON.stringify(own.res)]);
    rows.push(['Body step: picking "Long waves" puts it on (with colour dots)', own.picked && /LongWavy/.test(own.picked.name) && own.parts > 0 && own.dots >= 6, `${JSON.stringify(own.picked)} · ${own.dots} colours`]);
    await L.shot(page, 'hair_body_step_1366.png');
    const errs = logs.filter(l => l.type === 'pageerror' || (l.type === 'error' && !/Failed to load resource/.test(l.text)));
    rows.push(['no page errors', !errs.length, errs.slice(0, 3).map(e => e.text).join(' | ')]);
    fs.writeFileSync(path.join(L.OUT, 'bodies_hair.json'), JSON.stringify({ rest, trial, hair }, null, 1));
    process.exitCode = L.table(rows, 'R2-3: other bodies and hair (spec_bodies 8.6, 9.5)') ? 0 : 1;
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
