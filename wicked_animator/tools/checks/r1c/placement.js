// Magic lands on the furniture (plan R1-C check 8 + the leftover bug "Magic lifts couples to headboard height").
// For Magic on the double bed, the single bed, the sofa and the floor it measures, in the real app:
//   - the lowest SKIN point (every vertex of the skinned bodies, CPU-skinned) against the surface top, on the keyed
//     pose (frame 0) and over the whole playing loop (motions + physics);
//   - the plan's rule: lowest bone - 0.06 m against the surface;
//   - every bone below 1.1 m inside the furniture's x/z bounds (beds);
//   - the bodies' long axis against the bed's length (Z);
//   - "all keys move together": a 3-key animation fitted on the bed moves every key's hips by the same amount.
//   node tools/checks/r1c/placement.js --port 8843 [--before]
const path = require('path'), fs = require('fs');
const L = require('./lib.js');

const PORT = L.argPort();
const BEFORE = process.argv.includes('--before');

async function measureAll(page, cases) {
  return page.evaluate(async cases => {
    const THREE = await import('three');
    const app = window.app;
    const magic = await import('/js/magic.js');
    const bones = await import('/js/bones.js');
    const v3 = new THREE.Vector3();
    const skinMin = (stride = 3) => {
      let min = Infinity;
      for (const [, v] of app.simViews) {
        if (!v.group.visible) continue;
        v.group.updateMatrixWorld(true);
        for (const mesh of v.meshes) {
          if (!mesh.visible) continue;
          const n = mesh.geometry.attributes.position.count;
          for (let i = 0; i < n; i += stride) { mesh.getVertexPosition(i, v3); v3.applyMatrix4(mesh.matrixWorld); if (v3.y < min) min = v3.y; }
        }
      }
      return min;
    };
    const bonePts = () => {
      const out = [];
      for (const [, v] of app.simViews) {
        v.group.updateMatrixWorld(true);
        for (const n of bones.POSABLE) if (v.bone(n)) out.push(v.worldPos(n));
      }
      return out;
    };
    const res = [];
    for (const [place, recipe] of cases) {
      const t0 = performance.now();
      const ok = await magic.makeMagic(app, { recipe, place, intensity: 0.5, seconds: 3 });
      app.setPlaying(false); app.showcase(false);
      if (app.vp.stopCamera) app.vp.stopCamera();
      const info = place === 'floor' ? null : await fetch('/api/furniture_mesh?id=' + place).then(r => (r.ok ? r.json() : null));
      // upright poses at a seat stand on the floor in front of it (app.lastMagic.where === 'front')
      const where = (app.lastMagic && app.lastMagic.where) || (place === 'floor' ? 'floor' : 'on');
      const top = info && where === 'on' ? info.surface_height : 0;
      // keyed pose at frame 0 (what Magic placed)
      for (const e of app.pipeline.entries()) app.pipeline.base(e, 0);
      const skin0 = skinMin(2);
      const pts = bonePts();
      const boneLow = Math.min(...pts.map(p => p.y)) - 0.06;
      let outside = 0, outsideMax = 0;
      if (info && /bed/.test(place)) {
        const b = info.bounds;
        for (const p of pts) if (p.y < 1.1) {
          const dx = Math.max(b.min[0] - p.x, p.x - b.max[0], 0), dz = Math.max(b.min[2] - p.z, p.z - b.max[2], 0);
          const d = Math.max(dx, dz);
          if (d > 0) { outside++; outsideMax = Math.max(outsideMax, d); }
        }
      }
      // principal axis of the bone points in x/z
      const cx = pts.reduce((a, p) => a + p.x, 0) / pts.length, cz = pts.reduce((a, p) => a + p.z, 0) / pts.length;
      let sxx = 0, szz = 0, sxz = 0;
      for (const p of pts) { sxx += (p.x - cx) ** 2; szz += (p.z - cz) ** 2; sxz += (p.x - cx) * (p.z - cz); }
      const ang = 0.5 * Math.atan2(2 * sxz, sxx - szz);            // angle of the main axis from +X
      const axisFromZ = Math.abs(90 - Math.abs(ang * 180 / Math.PI));   // 0 = along Z
      const spread = Math.sqrt(Math.max(sxx, szz) / pts.length);
      // over the playing loop: every 3rd frame, motions and physics on
      let loopMin = Infinity, loopMax = -Infinity;
      const Lf = app.store.project.length;
      app.pipeline.simulateIfNeeded(true);
      for (let f = 0; f < Lf; f += 3) {
        app.pipeline.apply(f, { physics: true, overrides: false });
        const m = skinMin(4);
        loopMin = Math.min(loopMin, m); loopMax = Math.max(loopMax, m);
      }
      app.pipeline.apply(0, { physics: true });
      res.push({ place, recipe, ok, where, top, skin0: +skin0.toFixed(4), boneLow: +boneLow.toFixed(4), loopMin: +loopMin.toFixed(4), loopMax: +loopMax.toFixed(4),
        outside, outsideMax: +outsideMax.toFixed(3), axisFromZ: +axisFromZ.toFixed(1), spread: +spread.toFixed(3), ms: Math.round(performance.now() - t0) });
    }
    return res;
  }, cases);
}

// every key moves together (a 3-key animation, keys at 0/30/60, fitted onto the double bed)
async function keysTogether(page) {
  return page.evaluate(async () => {
    const THREE = await import('three');
    const app = window.app;
    let placing;
    try { placing = await import('/js/placing.js'); } catch { return { skipped: 'no placing.js yet' }; }
    const magic = await import('/js/magic.js');
    await magic.makeMagic(app, { recipe: 'missionary', place: 'floor', intensity: 0.5, seconds: 3 });
    app.setPlaying(false); app.showcase(false);
    const p = app.store.project;
    // three keys: the Magic pose at 0, then the same pose turned/moved a little at 30 and 60 (on the floor)
    for (const s of p.sims) {
      const k0 = s.keys.find(k => k.frame === 0);
      for (const [f, dx] of [[30, 0.1], [60, -0.12]]) {
        const k = JSON.parse(JSON.stringify(k0)); k.frame = f;
        s.keys.push(k);
      }
      s.keys.sort((a, b) => a.frame - b.frame);
    }
    app.refreshAll();
    const hips = () => p.sims.map(s => s.keys.map(k => (k.pose.pos && k.pose.pos.b__Pelvis__ ? [...k.pose.pos.b__Pelvis__] : null)));
    const before = hips();
    p.furniture = 'double_bed'; p.locations = ['DOUBLE_BED']; app.buildFurniture();
    const info = await placing.furnitureInfo(app, 'double_bed');
    await placing.fitOnSurface(app, p.sims, info, { frame: 0 });
    app.refreshAll();
    const after = hips();
    const moved = [];
    before.forEach((keys, i) => keys.forEach((b, j) => { const a = after[i][j]; moved.push(b && a ? Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]) : null); }));
    // the same world move for every key of a sim (the hips' local offsets change identically when there is no turn;
    // with a turn their distances from the pivot differ, so compare the world pelvis at each key instead)
    const worldPelvis = [];
    for (const s of p.sims) {
      const v = app.simViews.get(s.id);
      const per = [];
      for (const k of s.keys) { app.pipeline.base({ sim: s, v }, k.frame); v.group.updateMatrixWorld(true); per.push(v.worldPos('b__Pelvis__').toArray()); }
      worldPelvis.push(per);
    }
    return { keys: p.sims.map(s => s.keys.map(k => k.frame)), moved, worldPelvis };
  });
}

(async () => {
  const server = await L.startServer(PORT);
  const T = L.table();
  const out = {};
  try {
    const { browser, page, logs } = await L.open(PORT, { w: 1366, h: 768, beforeLoad: pg => pg.evaluateOnNewDocument(() => { try { localStorage.setItem('fsa.tourDone', 'true'); } catch { } }) });
    await page.waitForFunction(() => window.app && window.app.posePresets && window.app.posePresets.length, { timeout: 60000 });
    await page.evaluate(() => { document.getElementById('home').classList.add('hidden'); });
    const cases = [];
    for (const place of ['double_bed', 'single_bed', 'sofa', 'floor']) for (const recipe of ['cowgirl', 'missionary', 'doggy', 'bj']) cases.push([place, recipe]);
    const res = await measureAll(page, cases);
    out.cases = res;
    for (const r of res) {
      const tag = `${r.recipe} ${r.where === 'front' ? 'in front of' : 'on'} ${r.place}`;
      if (!r.ok) { T.check(`${tag}: Magic made it`, false); continue; }
      T.check(`${tag}: lowest skin on the surface (keyed pose)`, Math.abs(r.skin0 - r.top) <= 0.02, `skin ${r.skin0} vs top ${r.top} (${((r.skin0 - r.top) * 100).toFixed(1)} cm)`);
      T.check(`${tag}: never sinks > 3 cm while playing`, r.loopMin >= r.top - 0.03, `loop lowest skin ${r.loopMin}..${r.loopMax} vs top ${r.top}`);
      if (r.place === 'double_bed' && r.recipe === 'cowgirl') {
        T.check(`${tag}: lowest bone - 0.06 within 2 cm of 0.562`, Math.abs(r.boneLow - 0.562) <= 0.02, `${r.boneLow}`);
        T.check(`${tag}: every bone below 1.1 m inside the bed`, r.outside === 0, `${r.outside} outside (max ${r.outsideMax} m)`);
        T.check(`${tag}: long axis within 10 deg of Z`, r.axisFromZ <= 10, `${r.axisFromZ} deg`);
      }
      if (r.place === 'floor' && r.recipe === 'cowgirl') T.check(`${tag}: lowest bone - 0.06 within 2 cm of 0`, Math.abs(r.boneLow) <= 0.02, `${r.boneLow}`);
    }
    if (!BEFORE) {
      // every other recipe on both beds ("Surprise me" picks a bed 2 times in 3): resting, never through it
      const more = ['double_bed', 'single_bed'].flatMap(pl => ['standing', 'spooning', 'pronebone', 'sitting', 'anal', 'handjob', 'cunni', 'titjob', 'kiss', 'carry'].map(r => [pl, r]));
      const res2 = await measureAll(page, more);
      out.more = res2;
      for (const r of res2) {
        const tag = `${r.recipe} ${r.where === 'front' ? 'at the foot of' : 'on'} ${r.place}`;
        if (!r.ok) { T.check(`${tag}: Magic made it`, true, 'no ready pose for it here (skipped)'); continue; }
        T.check(`${tag}: lowest skin on the surface (keyed pose)`, Math.abs(r.skin0 - r.top) <= 0.02, `skin ${r.skin0} vs top ${r.top} (${((r.skin0 - r.top) * 100).toFixed(1)} cm)`);
      }
      // pictures: cowgirl on each place, framed from the front
      for (const place of ['double_bed', 'single_bed', 'sofa', 'floor']) {
        await page.evaluate(async place => {
          const magic = await import('/js/magic.js');
          await magic.makeMagic(window.app, { recipe: 'cowgirl', place, intensity: 0.5, seconds: 3 });
          window.app.setPlaying(false); window.app.showcase(false); clearTimeout(window.app._magicShow);
          window.app.setFrame(0); window.app.frameSims({ fromFront: true });
        }, place);
        await L.sleep(900);
        await L.shot(page, path.join(L.OUT, `magic_cowgirl_${place}.png`));
      }
      const k = await keysTogether(page);
      out.keys = k;
      if (k.skipped) T.check('every key moved', false, k.skipped);
      else {
        const moved = k.moved.filter(x => x !== null);
        T.check('every key moved (3 keys per sim)', moved.length >= 6 && moved.every(x => x > 0.05), moved.map(x => x.toFixed(3)).join(' '));
        // the same pose at 0/30/60 must end in the same place after the move
        const spread = k.worldPelvis.map(per => Math.max(...per.map(a => Math.hypot(a[0] - per[0][0], a[1] - per[0][1], a[2] - per[0][2]))));
        T.check('all keys moved together (same place for the same pose)', spread.every(x => x < 0.002), spread.map(x => x.toFixed(4)).join(' '));
      }
    }
    out.errors = logs.filter(x => /pageerror|\[error\]/.test(x)).slice(0, 20);
    T.check('no page errors', !out.errors.length, out.errors.join(' | ').slice(0, 300));
    await browser.close();
  } finally { L.stopServer(server); }
  fs.mkdirSync(L.OUT, { recursive: true });
  fs.writeFileSync(path.join(L.OUT, BEFORE ? 'placement_before.json' : 'placement.json'), JSON.stringify(out, null, 1));
  const ok = T.print(BEFORE ? 'Magic placement (BEFORE the fix)' : 'Magic placement');
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
