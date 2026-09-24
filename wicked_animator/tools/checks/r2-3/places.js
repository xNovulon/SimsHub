// R2-3 spec_bodies 3.9: seat and lying spots, "Sit here" / "Lie here", and Magic on every recipe x place.
//   - the server's spots: sofa 3 seats at y 0.485 facing +Z with feet at y 0.112; double bed 4 edge seats facing
//     +-X at y 0.61, in-bed seats 9/10/12/13, 3 lying spots at z ~ -0.29 facing +Z; the resource index is not rebuilt
//   - the Place tool shows a marker per spot, and the spots card lists them
//   - "Sit here" on sofa seat 1: the pelvis at (-0.75, 0.595 +- 0.01, 0.08); the feet within 1 cm of the foot spots
//     on every frame (the sim has a motion); the knees point forward
//   - "Lie here" on the double bed: the pelvis over the spot, the lowest skin on the mattress, nothing below it
//   - Magic cowgirl on the double bed: the lowest skin within 1 cm of 0.562 (measured on the skinned meshes, which is
//     what the placement uses; the capsule estimate of spec 3.9 is recorded next to it), every bone with y < 1.1 over
//     the bed, the long axis within 10 deg of Z
//   - every Magic recipe x {floor, double bed, sofa, loveseat, armchair, counter, table}: no bone below
//     surface - 0.03 where the grid has a height (inside its top: down to 30 cm under it, not on the floor under a
//     table top), on the keyed pose and over the playing loop
//   node tools/checks/r2-3/places.js --port 8853 [--quick]
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const QUICK = process.argv.includes('--quick');
const INDEX = path.join(L.ROOT, 'cache', 'furniture', '_index_v1.pkl');

(async () => {
  const port = L.argPort();
  const rows = [];
  const idxBefore = fs.existsSync(INDEX) ? fs.statSync(INDEX).mtimeMs : null;
  // ---- the server's spots
  const get = id => fetch(`http://127.0.0.1:${port}/api/furniture_mesh?v=2&id=${id}`).then(r => r.json());
  const sofa = await get('sofa'), bed = await get('double_bed');
  const seats = (sofa.slots || []).filter(s => s.kind === 'seat');
  rows.push(['sofa: 3 seats at y 0.485 facing +Z, feet at y 0.112', seats.length === 3 && seats.every(s => Math.abs(s.pos[1] - 0.485) < 0.002 && s.dir[2] > 0.99 && s.feet && Math.abs(s.feet.L[1] - 0.112) < 0.002),
    seats.map(s => `${s.n}:(${s.pos.join(',')})`).join(' ')]);
  const edge = (bed.slots || []).filter(s => s.kind === 'edge'), inb = (bed.slots || []).filter(s => s.kind === 'in'), lie = (bed.slots || []).filter(s => s.kind === 'lie');
  rows.push(['double bed: 4 edge seats facing +-X at y 0.61', edge.length === 4 && edge.every(s => Math.abs(Math.abs(s.dir[0]) - 1) < 0.01 && Math.abs(s.pos[1] - 0.61) < 0.002), edge.map(s => s.n).join(',')]);
  rows.push(['double bed: in-bed seats 9, 10, 12, 13', inb.map(s => s.n).sort((a, b) => a - b).join(',') === '9,10,12,13', inb.map(s => s.n).join(',')]);
  rows.push(['double bed: 3 lying spots at z ~ -0.29 facing +Z', lie.length === 3 && lie.every(s => Math.abs(s.pos[2] + 0.29) < 0.02 && s.dir[2] > 0.99), lie.map(s => `(${s.pos.join(',')})`).join(' ')]);

  const { browser, page, logs } = await L.appPage(port, { w: 1366, h: 768 });
  try {
    await page.waitForFunction('app.posePresets && app.posePresets.length > 0 && window.wickedScene', { timeout: 180000 });
    // ---- Place tool markers, the spots card, Sit here
    const sit = await page.evaluate(async () => {
      const THREE = await import('three');
      const home = await import('/js/home.js'); home.hideHome(app);
      app.newScene(false, false);
      app.setFurniture('sofa');
      const info = await app._furnitureInfo('sofa');
      const s = app.store.project.sims[0];
      app.selectSim(s.id);
      app.setTool('move');
      await new Promise(r => setTimeout(r, 700));
      const markers = window.wickedScene.slots.group ? window.wickedScene.slots.group.children.length : 0;
      const card = document.querySelector('.spots-card');
      const cardButtons = card ? card.querySelectorAll('button').length : 0;
      // a motion, so the feet are checked on a moving body
      app.addLayer(s.id, 'breathe');
      const seat = info.slots.find(x => x.kind === 'seat' && x.n === 0);
      app.sitHere(s.id, seat);
      await new Promise(r => setTimeout(r, 300));
      const v = app.simViews.get(s.id);
      const p = app.store.project;
      let worst = 0;
      for (let k = 0; k < p.length; k += 3) {
        app.pipeline.apply(k, { physics: true, overrides: false });
        v.group.updateMatrixWorld(true);
        for (const [side, b] of [['L', 'b__L_Foot__'], ['R', 'b__R_Foot__']]) worst = Math.max(worst, v.worldPos(b).distanceTo(new THREE.Vector3(...seat.feet[side])));
      }
      app.pipeline.base({ sim: s, v }, 0);
      v.group.updateMatrixWorld(true);
      const pel = v.worldPos('b__Pelvis__');
      // the knees in front of the hips (sitting, not folded back into the seat)
      const knees = ['L', 'R'].map(sd => v.worldPos(`b__${sd}_Calf__`).z - v.worldPos(`b__${sd}_Thigh__`).z);
      app.applyPoses();
      return { markers, cardButtons, pel: pel.toArray(), worst, knees, undo: app.store.undo.length };
    });
    await L.shot(page, 'places_sit_sofa.png');
    rows.push(['Place tool: a marker per sofa seat', sit.markers === 3, `${sit.markers} markers`]);
    rows.push(['Place tool: the spots card lists them', sit.cardButtons === 3, `${sit.cardButtons} buttons`]);
    rows.push(['Sit here, sofa seat 1: pelvis at (-0.75, 0.595 +- 0.01, 0.08)', Math.abs(sit.pel[0] + 0.75) < 0.01 && Math.abs(sit.pel[1] - 0.595) <= 0.01 && Math.abs(sit.pel[2] - 0.08) < 0.01, sit.pel.map(x => x.toFixed(3)).join(', ')]);
    rows.push(['Sit here: feet within 1 cm of the foot spots on every frame', sit.worst <= 0.01, `worst ${(sit.worst * 100).toFixed(2)} cm`]);
    rows.push(['Sit here: knees forward (not folded into the seat)', sit.knees.every(d => d > 0.15), sit.knees.map(x => x.toFixed(2)).join(', ')]);

    // ---- Lie here (a standing sim on the double bed)
    const lieR = await page.evaluate(async () => {
      const pl = await import('/js/placing.js');
      const bones = await import('/js/bones.js');
      app.newScene(false, false);
      app.setFurniture('double_bed');
      const info = await app._furnitureInfo('double_bed');
      const s = app.store.project.sims[0];
      app.selectSim(s.id);
      const spot = info.slots.find(x => x.kind === 'lie' && Math.abs(x.pos[0]) < 0.01) || info.slots.find(x => x.kind === 'lie');
      await app.lieHere(s.id, spot);
      const v = app.simViews.get(s.id);
      app.pipeline.base({ sim: s, v }, 0);
      v.group.updateMatrixWorld(true);
      const pel = v.worldPos('b__Pelvis__');
      const low = pl.lowestSkin(app, [s], 0);
      const g = pl.gridOf(info);
      let below = 0, worst = 0;
      for (const n of bones.POSABLE) {
        if (!v.bone(n)) continue;
        const q = v.worldPos(n), hh = pl.gridHeight(g, q.x, q.z);
        if (hh !== null && q.y < hh - 0.03 && q.y > hh - 0.3) { below++; worst = Math.max(worst, hh - q.y); }
      }
      const head = v.worldPos('b__Head__');
      app.frameSims({ fromFront: true });
      return { pel: pel.toArray(), spot: spot.pos, low, top: info.surface_height, below, worst, headZ: head.z };
    });
    await new Promise(r => setTimeout(r, 900));
    await L.shot(page, 'places_lie_bed.png');
    rows.push(['Lie here: pelvis over the lying spot (x/z within 2 cm)', Math.hypot(lieR.pel[0] - lieR.spot[0], lieR.pel[2] - lieR.spot[2]) < 0.02, `pelvis (${lieR.pel.map(x => x.toFixed(3)).join(', ')}) spot (${lieR.spot.join(', ')})`]);
    rows.push(['Lie here: lowest skin on the mattress (+-1 cm)', Math.abs(lieR.low - lieR.top) <= 0.01, `skin ${lieR.low.toFixed(3)} vs ${lieR.top}`]);
    rows.push(['Lie here: no bone below the surface - 3 cm', lieR.below === 0, `${lieR.below} (worst ${(lieR.worst * 100).toFixed(1)} cm)`]);
    rows.push(['Lie here: along the bed, the head at the headboard end', lieR.headZ < lieR.pel[2] - 0.3, `head z ${lieR.headZ.toFixed(2)} vs pelvis z ${lieR.pel[2].toFixed(2)}`]);

    // ---- Magic on the double bed (the 3.9 numbers), then every recipe x place
    const recipes = await page.evaluate(async () => (await import('/js/magic.js')).RECIPES.map(r => r.id));
    const places = ['double_bed', 'floor', 'sofa', 'loveseat', 'chair_living', 'counter', 'table_dining'];
    const cases = [];
    for (const place of places) for (const recipe of (QUICK ? ['cowgirl', 'missionary', 'bj'] : recipes)) cases.push([place, recipe]);
    const results = [];
    for (const [place, recipe] of cases) {
      const r = await page.evaluate(async (place, recipe) => {
        const THREE = await import('three');
        const magic = await import('/js/magic.js'), pl = await import('/js/placing.js'), bones = await import('/js/bones.js'), cc = await import('/js/clipcheck.js');
        app.store.setDirty(false);
        const ok = await magic.makeMagic(app, { recipe, place, intensity: 0.6, seconds: 3 });
        app.setPlaying(false); app.showcase(false); if (app.vp.stopCamera) app.vp.stopCamera();
        if (!ok) return { ok: false };
        const info = place === 'floor' ? null : await app._furnitureInfo(place);
        const g = info ? pl.gridOf(info) : null;
        const where = (app.lastMagic && app.lastMagic.where) || 'on';
        const p = app.store.project;
        const sims = p.sims;
        let below = 0, worst = 0, where0 = '';
        const test = (label) => {
          for (const [id, v] of app.simViews) {
            v.group.updateMatrixWorld(true);
            for (const n of bones.POSABLE) {
              if (!v.bone(n)) continue;
              const q = v.worldPos(n);
              const hh = g ? pl.gridHeight(g, q.x, q.z) : 0;
              // inside the furniture's top (not on the floor under a table top or a seat's overhang)
              if (hh !== null && q.y < hh - 0.03 && q.y > hh - 0.3) { below++; if (hh - q.y > worst) { worst = hh - q.y; where0 = `${label} ${n} ${(hh - q.y).toFixed(3)}`; } }
            }
          }
        };
        for (const [, v] of app.simViews) void v;
        for (const e of app.pipeline.entries()) app.pipeline.base(e, 0);
        test('keyed');
        for (let k = 0; k < p.length; k += 3) { app.pipeline.apply(k, { physics: true, overrides: false }); test('frame ' + k); }
        const out = { ok: true, where, below, worst, where0 };
        if (place === 'double_bed' && recipe === 'cowgirl') {
          for (const e of app.pipeline.entries()) app.pipeline.base(e, 0);
          let capLow = Infinity;
          const DOWN = new THREE.Vector3(0, -1, 0);
          for (const [, v] of app.simViews) for (const c of cc.capsulesOf(v)) {
            const n = { c, ...cc.capsuleNow(v, c) };
            for (const t of [0, 0.5, 1]) { const y = n.a.clone().lerp(n.b, t).y - cc.reach(n, DOWN, t, true); if (y < capLow) { capLow = y; out.capPart = c.name; } }
          }
          out.capLow = capLow;
          out.skinLow = pl.lowestSkin(app, sims, 0);
          let outside = 0;
          const pts = [];
          for (const [, v] of app.simViews) { v.group.updateMatrixWorld(true); for (const n of bones.POSABLE) if (v.bone(n)) { const q = v.worldPos(n); pts.push(q); if (q.y < 1.1 && pl.gridHeight(g, q.x, q.z) === null) outside++; } }
          out.outside = outside;
          const ax = pl.longAxis(pts, []);
          out.axisFromZ = Math.acos(Math.min(1, Math.abs(ax.dir.z))) * 180 / Math.PI;
        }
        return out;
      }, place, recipe);
      results.push({ place, recipe, ...r });
      if (place === 'double_bed' && recipe === 'cowgirl' && r.ok) {
        rows.push(['Magic cowgirl, double bed: lowest capsule skin within 1 cm of 0.562', Math.abs(r.capLow - 0.562) <= 0.01, `${r.capLow.toFixed(3)} (${r.capPart}; the skin itself: ${r.skinLow.toFixed(3)})`]);
        rows.push(['Magic cowgirl, double bed: lowest mesh skin within 1 cm of 0.562', Math.abs(r.skinLow - 0.562) <= 0.01, `${r.skinLow.toFixed(3)}`]);
        rows.push(['Magic cowgirl, double bed: every bone below 1.1 m over the bed', r.outside === 0, `${r.outside} outside`]);
        rows.push(['Magic cowgirl, double bed: long axis within 10 deg of Z', r.axisFromZ <= 10, `${r.axisFromZ.toFixed(1)} deg`]);
      }
    }
    const made = results.filter(r => r.ok), bad = made.filter(r => r.below > 0);
    for (const place of places) {
      const mine = made.filter(r => r.place === place), badHere = mine.filter(r => r.below > 0);
      rows.push([`Magic on ${place}: no bone below the surface - 3 cm (${mine.length} recipes, keyed + loop)`, !badHere.length,
        badHere.length ? badHere.map(r => `${r.recipe}: ${r.below} (${r.where0})`).join('; ') : `ok (${mine.map(r => r.where).filter((x, i, a) => a.indexOf(x) === i).join('/')})`]);
    }
    fs.writeFileSync(path.join(L.OUT, 'places.json'), JSON.stringify({ sit, lie: lieR, results }, null, 1));
    void bad;
    const idxAfter = fs.existsSync(INDEX) ? fs.statSync(INDEX).mtimeMs : null;
    rows.push(['the furniture resource index is not rebuilt', idxBefore === idxAfter, `${idxBefore} -> ${idxAfter}`]);
    const errs = logs.filter(l => l.type === 'pageerror' || (l.type === 'error' && !/Failed to load resource/.test(l.text)));
    rows.push(['no page errors', !errs.length, errs.slice(0, 3).map(e => e.text).join(' | ')]);
    process.exitCode = L.table(rows, 'R2-3: spots, sit, lie, Magic on furniture (spec_bodies 3.9)') ? 0 : 1;
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
