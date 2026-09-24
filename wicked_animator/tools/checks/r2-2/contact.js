// R2-2 checks: hold on to the partner, hands and natural limits, turn together, pins over time, follow-through /
// look-at / tremble loop continuity, performance (build_plan.md R2-2; spec_bodies 4.10, 5.6; spec_editing 16 checks
// 8, 16, 17). Nothing is written by the app (the harness answers every writing route); the export check builds its
// package offline in %TEMP%.
//   node tools/checks/r2-2/contact.js --port 8852 [--only A,B,C] [--no-shots]
// Output: a PASS/FAIL table, cache/checks/r2-2/contact_results.json, screenshots in cache/checks/r2-2/.
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execFileSync } = require('child_process');
const H = require('../lib/harness.js');
const L = require('./lib.js');

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const PORT = +arg('--port', 8852);
const ONLY = arg('--only', null) ? new Set(arg('--only').split(',')) : null;
const SHOTS = !argv.includes('--no-shots');
const OUT = path.join(H.ROOT, 'cache', 'checks', 'r2-2');
fs.mkdirSync(OUT, { recursive: true });
const want = g => !ONLY || ONLY.has(g);

const rows = [];
const C = (name, ok, detail) => { rows.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  ${detail === undefined ? '' : (typeof detail === 'string' ? detail : JSON.stringify(detail)).slice(0, 260)}`); };
const results = {};

// ---------------------------------------------------------------- in-page helpers
async function installHelpers(page) {
  return page.evaluate(async () => {
    const THREE = await import('three');
    const mods = {};
    for (const [k, f] of Object.entries({ B: 'bones', PM: 'posemath', Hd: 'holds', HA: 'hands', SK: 'skin', MG: 'magic', MO: 'motion', AN: 'animation', PL: 'pipeline' })) mods[k] = await import(`/js/${f}.js`);
    const sleep = ms => new Promise(res => setTimeout(res, ms));
    for (let i = 0; i < 150 && !(app.posePresets && app.posePresets.length); i++) await sleep(100);
    const home = document.getElementById('home');
    if (home) home.classList.add('hidden');
    const R = { THREE, ...mods, sleep };
    R.magic = async (recipe, place = 'double_bed', opts = {}) => {
      app.store.dirty = false;
      const ok = await mods.MG.makeMagic(app, { recipe, place, intensity: 0.55, seconds: 3, ...opts });
      app.setPlaying(false); app.showcase(false);
      clearTimeout(app._magicShow);
      return ok;
    };
    R.byFrame = f => app.store.project.sims.find(s => s.frame === f);
    R.view = s => app.simViews.get(s.id);
    R.skinOf = h => { const ov = app.simViews.get(h.sim), ab = ov.bone(h.bone); ab.updateWorldMatrix(true, false); return new THREE.Vector3().fromArray(h.off).applyMatrix4(ab.matrixWorld); };
    R.palmGap = (s, limb) => mods.Hd.limbPoint(R.view(s), limb).distanceTo(R.skinOf(s.pins[limb]));
    R.deg = r => r * 180 / Math.PI;
    R.qang = (a, b) => { const d = Math.abs(a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w) / ((a.length() * b.length()) || 1); return 2 * Math.acos(Math.min(1, d)) * 180 / Math.PI; };
    R.anyNaN = () => { for (const [, v] of app.simViews) for (const b of v.bones) { const q = b.quaternion, p = b.position; if (![q.x, q.y, q.z, q.w, p.x, p.y, p.z].every(Number.isFinite)) return b.name; } return null; };
    R.snapQ = v => v.bones.map(b => b.quaternion.clone());
    R.snapP = v => v.bones.map(b => b.position.clone());
    R.errors = [];
    const ce = console.error.bind(console);
    console.error = (...a) => { R.errors.push(a.map(x => String((x && x.message) || x)).join(' ')); ce(...a); };
    window.R = R;
    return { features: !!app.__contact, look: !!mods.MO.MOTIONS.look, tremble: !!mods.MO.MOTIONS.tremble };
  });
}

(async () => {
  const t0 = Date.now();
  const { browser, page, logs, writes, stubbed } = await L.open(PORT, { w: 1366, h: 768 });
  let page2 = null;
  try {
    const env = await installHelpers(page);
    results.env = { ...env, stubbed };
    C('0 contact feature installed (features/contact.js)', env.features, env);

    // ============================================================== A. holds (spec_bodies 4.10)
    if (want('A')) {
      // A1 - Magic cowgirl with default holds: palm centre 1.2 +- 0.8 cm from its skin point on every frame, no NaN,
      // reach < 1 cm
      const a1 = await page.evaluate(async () => {
        await R.magic('cowgirl', 'double_bed');
        const p = app.store.project, him = R.byFrame('ym');
        const holds = Object.entries(him.pins).filter(([, h]) => R.B.isHold(h));
        let lo = 9, hi = 0, nan = null, reach = 0;
        for (let f = 0; f < p.length; f++) {
          app.pipeline.apply(f, { physics: true, overrides: false });
          nan = nan || R.anyNaN();
          for (const [limb] of holds) {
            const d = R.palmGap(him, limb);
            lo = Math.min(lo, d); hi = Math.max(hi, d);
            reach = Math.max(reach, (app.pipeline.reach.get(him.id) || {})[limb] || 0);
          }
        }
        return { holds: holds.map(([l, h]) => `${l}: ${h.label} (${h.bone})`), loCm: +(lo * 100).toFixed(2), hiCm: +(hi * 100).toFixed(2), nan, reachCm: +(reach * 100).toFixed(3), toast: document.querySelector('.toast span')?.textContent || '' };
      });
      results.A1 = a1;
      C('A1 Magic cowgirl: his hands hold her (2 default holds)', a1.holds.length === 2, a1.holds);
      C('A1 held palm 1.2 +- 0.8 cm from its skin point on every frame', a1.holds.length && a1.loCm >= 0.4 && a1.hiCm <= 2.0, `min ${a1.loCm} cm, max ${a1.hiCm} cm over 90 frames`);
      C('A1 no NaN, reach < 1 cm', !a1.nan && a1.reachCm < 1, `NaN: ${a1.nan || 'none'}, worst reach ${a1.reachCm} cm`);
      C('A1 Magic says the hands hold on', /Hands hold on to the partner/.test(a1.toast), a1.toast);

      // the other recipes with default holds (information + the same quality bar)
      const aR = await page.evaluate(async () => {
        const out = {};
        for (const [rid, place] of [['doggy', 'double_bed'], ['anal', 'double_bed'], ['pronebone', 'double_bed'], ['spooning', 'double_bed'], ['carry', 'floor'], ['kiss', 'floor'], ['missionary', 'double_bed']]) {
          await R.magic(rid, place);
          const p = app.store.project;
          const holder = p.sims.find(s => Object.values(s.pins).some(R.B.isHold));
          let hi = 0, lo = 9, n = 0;
          if (holder) {
            for (let f = 0; f < p.length; f += 3) {
              app.pipeline.apply(f, { physics: true, overrides: false });
              for (const [limb, h] of Object.entries(holder.pins)) if (R.B.isHold(h)) { const d = R.palmGap(holder, limb); hi = Math.max(hi, d); lo = Math.min(lo, d); }
            }
            n = Object.values(holder.pins).filter(R.B.isHold).length;
          }
          out[rid] = { holds: n, loCm: n ? +(lo * 100).toFixed(2) : null, hiCm: n ? +(hi * 100).toFixed(2) : null };
        }
        return out;
      });
      results.Arecipes = aR;
      const held = Object.entries(aR).filter(([, x]) => x.holds);
      C('A1b default holds on doggy, anal, prone bone, spooning, carry, kiss (missionary: her hands are too far - skipped by the reach rule)',
        ['doggy', 'anal', 'pronebone', 'spooning', 'carry', 'kiss'].every(r => aR[r].holds >= 1) && held.every(([, x]) => x.loCm >= 0.4 && x.hiCm <= 2.0), aR);

      // A2 - drop the right hand 3 cm from her waist -> a hold on her ('waist' or 'lower back'); 20 cm away -> let go;
      // undo brings it back
      const a2 = await page.evaluate(async () => {
        const THREE = R.THREE;
        await R.magic('doggy', 'double_bed');
        const him = R.byFrame('ym'), her = R.byFrame('yf'), hv = R.view(him), fv = R.view(her);
        delete him.pins['R hand']; delete him.pins['L hand'];
        app.setFrame(0);
        app.setTool('ik');
        app.pipeline.apply(0, { physics: false });
        // her waist, the side nearer his right hand
        const palm0 = R.Hd.limbPoint(hv, 'R hand');
        const slots = R.B.GRAB.waist.filter(n => fv.bone(n)).sort((a, b) => fv.worldPos(a).distanceTo(palm0) - fv.worldPos(b).distanceTo(palm0));
        const hit = R.SK.nearestSkin(fv, fv.worldPos(slots[0]), 0.1);
        const want = hit.point.clone().addScaledVector(hit.normal, 0.03);
        const it = app.interact, gz = app.vp.gizmo;
        const drag = (limb, to) => {
          const x = it.handleList.find(h => h.simId === him.id && h.limb === limb);
          it.selectHandle(x);
          const off = R.Hd.limbPoint(hv, limb).sub(hv.worldPos('b__R_Hand__'));
          gz.dispatchEvent({ type: 'mouseDown' });
          gz.dispatchEvent({ type: 'dragging-changed', value: true });
          it.proxy.position.copy(to.clone().sub(off));
          gz.dispatchEvent({ type: 'objectChange' });
          gz.dispatchEvent({ type: 'mouseUp' });
          gz.dispatchEvent({ type: 'dragging-changed', value: false });
        };
        drag('R hand', want);
        const gapAfterDrop = R.Hd.limbPoint(hv, 'R hand').distanceTo(hit.point);
        const h1 = him.pins['R hand'] ? JSON.parse(JSON.stringify(him.pins['R hand'])) : null;
        app.pipeline.apply(0, { physics: false });
        const settled = h1 ? R.palmGap(him, 'R hand') : null;
        // 20 cm out from the skin, away from her on screen too (a drop that still looks on her skin holds on)
        const cam = app.vp.camera.position, view = R.Hd.limbPoint(hv, 'R hand').sub(cam).normalize();
        const outward = hit.normal.clone().addScaledVector(view, -hit.normal.dot(view));
        if (outward.lengthSq() < 1e-4) outward.set(1, 0, 0).cross(view);
        const away = R.Hd.limbPoint(hv, 'R hand').addScaledVector(outward.normalize(), 0.2);
        drag('R hand', away);
        const gone = !him.pins['R hand'];
        app.undo();
        const back = app.store.project.sims.find(s => s.id === him.id).pins['R hand'];
        return { slot: slots[0], dropCm: +(gapAfterDrop * 100).toFixed(2), hold: h1 && { sim: h1.sim === her.id, label: h1.label, bone: h1.bone }, settledCm: settled && +(settled * 100).toFixed(2),
          gone, undoBack: !!(back && back.sim === her.id), undoLabel: back && back.label };
      });
      results.A2 = a2;
      C('A2 drop the right hand 3 cm from her waist -> it holds her waist / lower back', a2.hold && a2.hold.sim && ['waist', 'lower back'].includes(a2.hold.label), a2);
      C('A2 ...the palm then sits 1.2 cm off her skin', a2.settledCm !== null && Math.abs(a2.settledCm - 1.2) <= 0.8, `${a2.settledCm} cm`);
      C('A2 dragged 20 cm away -> it lets go; undo brings the hold back', a2.gone && a2.undoBack, { gone: a2.gone, undoBack: a2.undoBack, label: a2.undoLabel });

      // A2c - her hand dropped where it looks on his shoulder on screen, but 13.5 cm in front of it in depth: it holds
      // (the skin under the palm / the pointer, within 4 cm across the view and 20 cm in depth); 35 cm in front: not
      const a2c = await page.evaluate(async () => {
        const THREE = R.THREE;
        const run = async depth => {
          await R.magic('kiss', 'floor');
          const him = R.byFrame('ym'), her = R.byFrame('yf'), hv = R.view(her), mv = R.view(him);
          delete her.pins['R hand']; delete her.pins['L hand'];
          app.setFrame(0); app.setTool('ik');
          app.pipeline.apply(0, { physics: false });
          const palm0 = R.Hd.limbPoint(hv, 'R hand');
          const slot = R.B.GRAB.shoulder.filter(n => mv.bone(n)).sort((a, b) => mv.worldPos(a).distanceTo(palm0) - mv.worldPos(b).distanceTo(palm0))[0];
          const sk = R.SK.nearestSkin(mv, mv.worldPos(slot), 0.1);
          // look at that skin point from the outside of his shoulder
          const eye = sk.point.clone().addScaledVector(sk.normal, 1.2).add(new THREE.Vector3(0, 0.15, 0));
          app.vp.controls.lookFrom(eye, sk.point);
          app.vp.camera.updateMatrixWorld(true);
          const toCam = eye.clone().sub(sk.point).normalize();
          const want = sk.point.clone().addScaledVector(toCam, depth);
          const it = app.interact, gz = app.vp.gizmo;
          const x = it.handleList.find(h => h.simId === her.id && h.limb === 'R hand');
          it.selectHandle(x);
          const off = R.Hd.limbPoint(hv, 'R hand').sub(hv.worldPos('b__R_Hand__'));
          gz.dispatchEvent({ type: 'mouseDown' });
          gz.dispatchEvent({ type: 'dragging-changed', value: true });
          it.proxy.position.copy(want.clone().sub(off));
          gz.dispatchEvent({ type: 'objectChange' });
          const q = sk.point.clone().project(app.vp.camera), rc = app.vp.canvas.getBoundingClientRect();
          it.lastPointer = { clientX: rc.left + (q.x + 1) / 2 * rc.width, clientY: rc.top + (1 - q.y) / 2 * rc.height };
          const palm = R.Hd.limbPoint(hv, 'R hand'), gap3d = R.SK.nearestSkin(mv, palm, 1) ;
          gz.dispatchEvent({ type: 'mouseUp' });
          gz.dispatchEvent({ type: 'dragging-changed', value: false });
          const h = her.pins['R hand'];
          return { skinGapCm: +(gap3d.dist * 100).toFixed(1), held: R.B.isHold(h) && h.sim === him.id, label: h && h.label, settledCm: R.B.isHold(h) ? +(R.palmGap(her, 'R hand') * 100).toFixed(2) : null };
        };
        return { near: await run(0.135), far: await run(0.35) };
      });
      results.A2c = a2c;
      C('A2c a drop that looks on his shoulder on screen (13.5 cm in front of it) holds his shoulder', a2c.near.held && /shoulder|chest|back|neck/.test(a2c.near.label || '') && a2c.near.skinGapCm > 4 && Math.abs(a2c.near.settledCm - 1.2) <= 0.8, a2c.near);
      C('A2c ...35 cm in front of it does not', !a2c.far.held, a2c.far);

      // A2d - the gate's case, with the real mouse: Magic cowgirl, the camera where the gizmo's X arrow points (almost)
      // straight at it, her hand dot pressed at its centre and dragged once onto his shoulder: it holds on the FIRST
      // release (the dot wins over the arrow drawn on top of it; arrows seen end-on are hidden)
      const a2d = [];
      for (const clickFirst of [true, false]) {
        const setup = await page.evaluate(async clickFirst => {
          const THREE = R.THREE;
          await R.magic('cowgirl', 'double_bed');
          await R.sleep(1300);
          app.setPlaying(false); app.showcase(false); clearTimeout(app._magicShow);
          if (app.vp.stopCamera) app.vp.stopCamera();
          app.setFrame(0);
          const him = R.byFrame('ym'), her = R.byFrame('yf'), hv = R.view(him), fv = R.view(her);
          app.selectSim(her.id);
          app.setTool('ik');
          app.pipeline.apply(0, { physics: false, overrides: false });
          // her hand nearest to his shoulder, let go of anything it had
          const slots = R.B.GRAB.shoulder.filter(n => hv.bone(n));
          const pick = ['L hand', 'R hand'].map(l => { const pm = R.Hd.limbPoint(fv, l); const sl = slots.sort((a, b) => hv.worldPos(a).distanceTo(pm) - hv.worldPos(b).distanceTo(pm))[0]; return { l, sl, d: hv.worldPos(sl).distanceTo(pm) }; }).sort((a, b) => a.d - b.d)[0];
          const limb = pick.limb = pick.l;
          delete her.pins[limb];
          app.pipeline.apply(0, { physics: false, overrides: false });
          app.interact.refreshHandles();
          const sk = R.SK.nearestSkin(hv, hv.worldPos(pick.sl), 0.12);
          const target = sk.point.clone().addScaledVector(sk.normal, 0.015);
          const palm = R.Hd.limbPoint(fv, limb), mid = palm.clone().add(target).multiplyScalar(0.5);
          // the camera on the world X axis through the middle (4 degrees above it), on the side it can see both from
          const side = Math.sign((palm.x + target.x) / 2 - (hv.worldPos('b__Spine1__').x + fv.worldPos('b__Spine1__').x) / 2) || 1;
          const eye = mid.clone().add(new THREE.Vector3(side * 1.4, 0.1, 0));
          app.vp.controls.lookFrom(eye, mid);
          app.vp.camera.updateMatrixWorld(true);
          await R.sleep(200);
          const rc = app.vp.canvas.getBoundingClientRect();
          const toS = v => { const q = v.clone().project(app.vp.camera); return [Math.round(rc.left + (q.x + 1) / 2 * rc.width), Math.round(rc.top + (1 - q.y) / 2 * rc.height)]; };
          const hd = app.interact.handleList.find(x => x.simId === her.id && x.limb === limb);
          if (clickFirst) app.interact.selectHandle(hd);
          const eyeDir = eye.clone().sub(mid).normalize();
          return { limb, dot: toS(hd.mesh.position), target: toS(target), xFacingDeg: +(Math.acos(Math.abs(eyeDir.x)) * 180 / Math.PI).toFixed(1), slot: pick.sl };
        }, clickFirst);
        // the gizmo draws its X arrow over the dot: hidden now (seen end-on)
        const arrows = await page.evaluate(() => { const g = app.vp.gizmo, giz = g._gizmo; g.updateMatrixWorld(true);
          const vis = n => giz.picker.translate.children.filter(c => c.name === n).map(c => c.visible);
          return { attached: g.object === app.interact.proxy, X: vis('X'), Y: vis('Y'), XYZ: vis('XYZ') }; });
        const [x0, y0] = setup.dot, [x1, y1] = setup.target;
        await page.mouse.move(x0, y0); await H.sleep(60);
        await page.mouse.down(); await H.sleep(40);
        for (let k = 1; k <= 20; k++) { await page.mouse.move(x0 + (x1 - x0) * k / 20, y0 + (y1 - y0) * k / 20); await H.sleep(12); }
        await page.mouse.up(); await H.sleep(300);
        const after = await page.evaluate(limb => {
          const her = R.byFrame('yf'), him = R.byFrame('ym'), h = her.pins[limb];
          app.setFrame(0);
          // (and while it plays: his look-at turns the head her hand is on - the palm stays on it)
          let playWorst = 0;
          if (R.B.isHold(h)) { const ed = app.pipeline.editing; app.pipeline.editing = null;
            for (let f = 0; f < app.store.project.length; f += 3) { app.pipeline.apply(f, { physics: true, overrides: false }); playWorst = Math.max(playWorst, R.palmGap(her, limb)); }
            app.pipeline.editing = ed; app.applyPoses(false); }
          const reach = (app.pipeline.reach.get(her.id) || {})[limb] || 0;
          const chip = [...document.querySelectorAll('#inspector .hold-chip')].map(x => x.className + '|' + x.textContent.trim()).find(t => t.includes(limb === 'L hand' ? 'Left hand' : 'Right hand'));
          return { held: R.B.isHold(h) && h.sim === him.id, label: h && h.label, gap: R.B.isHold(h) ? +(R.palmGap(her, limb) * 100).toFixed(2) : null, reachCm: +(reach * 100).toFixed(2), chip, anchor: h && h.bone, playWorstCm: +(playWorst * 100).toFixed(2) };
        }, setup.limb);
        a2d.push({ clickFirst, ...setup, arrows, ...after });
      }
      results.A2d = a2d;
      for (const r of a2d) {
        C(`A2d gate case${r.clickFirst ? ' (dot clicked first)' : ' (press and drag at once)'}: X arrow ${r.xFacingDeg} deg from the view, hidden; one drag onto his shoulder holds on the first release`,
          r.xFacingDeg < 15 && (!r.clickFirst || (r.arrows.attached && r.arrows.X.every(v => !v))) && r.held && Math.abs(r.gap - 1.2) <= 0.8 && r.playWorstCm <= 2,
          { dot: r.dot, target: r.target, arrows: r.arrows, held: r.held, label: r.label, anchor: r.anchor, gapCm: r.gap, playWorstCm: r.playWorstCm, reachCm: r.reachCm });
      }

      // A3 - export and read the package: the arm follows her hips (palm moves > 5 cm, stays < 2 cm from the skin)
      const a3 = await page.evaluate(async () => {
        await R.magic('cowgirl', 'double_bed');
        const him = R.byFrame('ym'), her = R.byFrame('yf');
        const baked = app.bake();
        const hi = baked.actors.findIndex((a, i) => app.store.project.sims[i].id === him.id), pi = baked.actors.findIndex((a, i) => app.store.project.sims[i].id === her.id);
        const limb = Object.keys(him.pins).find(l => R.B.isHold(him.pins[l]) && l.includes('hand'));
        const h = him.pins[limb];
        return { baked, holder: hi, partner: pi, limb, bone: h.bone, off: h.off };
      });
      const job = path.join(os.tmpdir(), 'wa_r22_export_job.json');
      fs.writeFileSync(job, JSON.stringify(a3));
      let ex = null;
      try { ex = JSON.parse(execFileSync('python', [path.join(__dirname, 'export_holds.py'), job], { encoding: 'utf8', timeout: 300000 }).trim().split('\n').pop()); } catch (e) { ex = { error: String(e.message || e).slice(0, 400) }; }
      results.A3 = ex;
      C('A3 export: the held hand follows her hips in the package (palm travels > 5 cm)', ex && ex.palmTravelCm > 5, ex);
      C('A3 ...and stays < 2 cm from her skin point on every frame', ex && ex.palmSkinMaxCm < 2, ex && `min ${ex.palmSkinMinCm}, max ${ex.palmSkinMaxCm} cm over ${ex.frames} frames; package ${ex.bytes} bytes in %TEMP%`);

      // A4 - a hold with from / to fades in and out over `fade` frames with no jump over 3 degrees per frame
      const a4 = await page.evaluate(async () => {
        await R.magic('cowgirl', 'double_bed');
        const him = R.byFrame('ym'), hv = R.view(him);
        const limb = Object.keys(him.pins).find(l => R.B.isHold(him.pins[l]));
        app.setFrame(0);
        R.Hd.setPin(app, him.id, limb, { from: 20, to: 45 });            // "Hold only from here to the next key" (its fade: as smooth as needed)
        const fade = him.pins[limb].fade;
        const chain = R.B.LIMBS[limb];
        let worst = 0, at = -1, prev = null;
        const inside = [], outside = [];
        const p = app.store.project;
        for (let f = 0; f <= p.length; f++) {
          app.pipeline.apply(f % p.length, { physics: false, overrides: false });
          const q = chain.map(n => R.PM.spaceQuat(hv, hv.bone(n)));
          if (prev) { const d = Math.max(...q.map((x, i) => R.qang(x, prev[i]))); if (d > worst) { worst = d; at = f; } }
          prev = q;
          if (f >= 20 && f <= 45) inside.push(R.palmGap(him, limb));
        }
        // the same frames without the hold: how big a step is the motion itself
        const saved = him.pins[limb]; delete him.pins[limb];
        let base = 0; prev = null;
        for (let f = 0; f <= p.length; f++) {
          app.pipeline.apply(f % p.length, { physics: false, overrides: false });
          const q = chain.map(n => R.PM.spaceQuat(hv, hv.bone(n)));
          if (prev) base = Math.max(base, Math.max(...q.map((x, i) => R.qang(x, prev[i]))));
          prev = q;
        }
        him.pins[limb] = saved;
        return { limb, fade, worstDeg: +worst.toFixed(2), atFrame: at, motionAloneDeg: +base.toFixed(2), insideMaxCm: +(Math.max(...inside) * 100).toFixed(2) };
      });
      results.A4 = a4;
      C('A4 a hold for frames 20-45 eases in and out: never more than 3 degrees in a frame', a4.worstDeg <= 3, a4);
      C('A4 ...and holds on inside its range', a4.insideMaxCm <= 2, `${a4.insideMaxCm} cm`);

      // A5 - a mirrored held pose keeps its hold on the partner
      const a5 = await page.evaluate(async () => {
        await R.magic('cowgirl', 'double_bed');
        const out = {};
        const him = R.byFrame('ym');
        // (a) the holder's pose mirrored at a key: the holds stay, the palms stay on her
        app.setFrame(0);
        app.mirrorPose(him.id);
        app.pipeline.overrides.clear();
        app.applyPoses(false);
        let hi = 0;
        const limbs = Object.keys(him.pins).filter(l => R.B.isHold(him.pins[l]));
        for (let f = 0; f < app.store.project.length; f += 5) { app.pipeline.apply(f, { physics: true, overrides: false }); for (const l of limbs) hi = Math.max(hi, R.palmGap(him, l)); }
        out.pose = { holds: limbs, maxCm: +(hi * 100).toFixed(2) };
        // (b) the whole animation mirrored (R2-1's keyops.mirrorProject) and the holds found again (interact.rebindHold)
        let KO = null;
        try { KO = await import('/js/keyops.js'); } catch { KO = null; }
        if (KO && KO.mirrorProject) {
          await R.magic('cowgirl', 'double_bed');
          const p = app.store.project, before = Object.fromEntries(p.sims.map(s => [s.id, Object.keys(s.pins).filter(l => R.B.isHold(s.pins[l]))]));
          const { holdsToRebind } = KO.mirrorProject(p, app.assets.rig);
          app.refreshAll();
          for (const x of holdsToRebind) app.interact.rebindHold(x.simId, x.limb);
          const him2 = R.byFrame('ym');
          const limbs2 = Object.keys(him2.pins).filter(l => R.B.isHold(him2.pins[l]));
          let hi2 = 0, lo2 = 9;
          for (let f = 0; f < p.length; f += 3) { app.pipeline.apply(f, { physics: true, overrides: false }); for (const l of limbs2) { const d = R.palmGap(him2, l); hi2 = Math.max(hi2, d); lo2 = Math.min(lo2, d); } }
          out.project = { before: before[him2.id], after: limbs2, rebind: holdsToRebind.length, maxCm: +(hi2 * 100).toFixed(2), minCm: +(lo2 * 100).toFixed(2) };
        } else out.project = { skipped: 'keyops.mirrorProject not there (R2-1)' };
        return out;
      });
      results.A5 = a5;
      C('A5 a mirrored held pose keeps its holds on the partner', a5.pose.holds.length === 2 && a5.pose.maxCm <= 2, a5.pose);
      C('A5 the whole animation mirrored: the holds swap sides and still hold her (rebindHold)', a5.project.skipped ? true : (a5.project.after.length === a5.project.before.length && a5.project.after.length > 0
        && a5.project.after.every(l => a5.project.before.includes(l[0] === 'L' ? 'R' + l.slice(1) : 'L' + l.slice(1))) && a5.project.maxCm <= 2), a5.project);

      // A6 - dangling holds are cleaned: removing the partner drops the hold; a project saved with a dangling one loads clean
      const a6 = await page.evaluate(async () => {
        await R.magic('cowgirl', 'double_bed');
        const him = R.byFrame('ym'), her = R.byFrame('yf');
        const had = Object.values(him.pins).filter(R.B.isHold).length;
        app.removeSim(her.id);
        const left = Object.values(app.store.project.sims[0].pins).filter(R.B.isHold).length;
        const p = JSON.parse(JSON.stringify(app.store.project));
        p.sims[0].pins['L hand'] = { sim: 'nobody', bone: 'b__Pelvis__', off: [0, 0, 0], rot: [0, 0, 0, 1] };
        app.store.load(p); app._projectLoaded && app._projectLoaded();
        const afterLoad = Object.values(app.store.project.sims[0].pins).filter(R.B.isHold).length;
        return { had, left, afterLoad };
      });
      results.A6 = a6;
      C('A6 a hold on a removed sim is dropped; a dangling hold in a loaded file is dropped', a6.had === 2 && a6.left === 0 && a6.afterLoad === 0, a6);

      // A7 - the inspector: hold chips, the ▾ menu with "Hold her…" parts; the view's handle colours and hover text
      const a7 = await page.evaluate(async () => {
        await R.magic('cowgirl', 'double_bed');
        const him = R.byFrame('ym');
        app.selectSim(him.id);
        app.setFrame(10);
        const chips = [...document.querySelectorAll('#inspector .hold-chip')].map(x => x.textContent.trim());
        const held = [...document.querySelectorAll('#inspector .pin.held')].length;
        const more = [...document.querySelectorAll('#inspector .pin-cell')].find(c => c.textContent.includes('Left foot'));
        more.querySelector('.pin-more').click();
        await R.sleep(50);
        const menu = [...document.querySelectorAll('.ctx-menu button, .ctx-menu .ctx-label')].map(x => x.textContent.trim());
        document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
        app.setTool('ik');
        const it = app.interact;
        const hh = it.handleList.find(x => x.simId === him.id && x.kind === 'limb' && R.B.isHold(him.pins[x.limb]));
        const her = R.byFrame('yf');
        const col = hh && '#' + hh.mesh.material.color.getHexString();
        const hint = hh && it.handleHint(hh);
        // her hand on his forearm: the chip says "his"
        const mv = R.view(him), fv = R.view(her);
        const hit = R.SK.nearestSkin(mv, mv.worldPos('b__L_Forearm__').lerp(mv.worldPos('b__L_Hand__'), 0.5), 0.2);
        R.Hd.makeHold(app, her.id, 'R hand', { sim: him, v: mv }, hit, { checkpoint: false, quiet: true, shape: false });
        app.selectSim(her.id);
        const hisChip = [...document.querySelectorAll('#inspector .hold-chip')].map(x => x.textContent.trim()).find(t => /Right hand/.test(t));
        void fv;
        return { chips, held, menu, handleColour: col, herColour: her.color, hint, hisChip };
      });
      results.A7 = a7;
      C('A7 the Pins & holds card shows each hold as a chip in her colour ("Right hand · holding her hip")', a7.chips.length === 2 && a7.chips.every(c => /holding (her|Female 1's) hip/.test(c)) && a7.held === 2, a7.chips);
      C('A7 a hold on him reads "holding his …" (not "him")', a7.hisChip && /holding his /.test(a7.hisChip) && !/holding him /.test(a7.hisChip), a7.hisChip);
      C('A7 the ▾ menu offers parts in reach, pins for part of the loop, hold nearest', a7.menu.some(m => /^Hold (her|Female)/.test(m)) && a7.menu.some(m => /Pin only from here to the next key/.test(m)) && a7.menu.includes('Hold the nearest partner'), a7.menu);
      C('A7 a held hand dot shows her colour; its hover text says what it holds', a7.handleColour === a7.herColour.toLowerCase() && /holding Female 1's .* \(drag it away to let go\)/.test(a7.hint || ''), { col: a7.handleColour, her: a7.herColour, hint: a7.hint });

      // A8 - while her hips are dragged in the Drag tool, his held hands follow at once (no re-apply during a drag)
      const a8 = await page.evaluate(async () => {
        await R.magic('cowgirl', 'double_bed');
        const him = R.byFrame('ym'), her = R.byFrame('yf'), it = app.interact, gz = app.vp.gizmo;
        app.setFrame(0); app.setTool('ik');
        const limbs = Object.keys(him.pins).filter(l => R.B.isHold(him.pins[l]));
        const x = it.handleList.find(h => h.simId === her.id && h.kind === 'hips');
        it.selectHandle(x);
        gz.dispatchEvent({ type: 'mouseDown' });
        gz.dispatchEvent({ type: 'dragging-changed', value: true });
        it.proxy.position.x += 0.06; it.proxy.position.y += 0.04;
        gz.dispatchEvent({ type: 'objectChange' });
        const during = Math.max(...limbs.map(l => R.palmGap(him, l)));
        gz.dispatchEvent({ type: 'mouseUp' });
        gz.dispatchEvent({ type: 'dragging-changed', value: false });
        return { limbs, duringCm: +(during * 100).toFixed(2) };
      });
      results.A8 = a8;
      C('A8 dragging her hips: his held hands follow at once (palm still 1.2 cm off her skin)', a8.limbs.length === 2 && Math.abs(a8.duringCm - 1.2) <= 0.8, a8);

      // A9 - Magic's other defaults: look at the partner, trembling legs at a hard finish, the Finish (moments), voices
      const a9 = await page.evaluate(async () => {
        await R.magic('cowgirl', 'double_bed', { intensity: 0.9, finish: 'face' });
        const p = app.store.project, him = R.byFrame('ym'), her = R.byFrame('yf');
        const layers = s => s.layers.map(l => l.type + (l.type === 'look' ? '@' + l.weight : ''));
        const voices = s => (s.sounds || []).filter(x => x.kind === 'voice').length;
        let moments = null;
        try { moments = await import('/js/moments.js'); } catch { moments = null; }
        return { her: layers(her), him: layers(him), category: p.category, act: p.act, loops: p.loops,
          events: (p.events || []).map(e => e.type + (e.cum ? ':' + e.cum : '')), herVoices: voices(her), himVoices: voices(him), moments: !!(moments && moments.finishPreset) };
      });
      results.A9 = a9;
      C('A9 Magic: both look at each other (60%), her legs tremble at a hard finish', a9.her.includes('look@0.6') && a9.him.includes('look@0.6') && a9.her.includes('tremble'), a9);
      C('A9 Magic Finish "Face": a one-time Climax of the act with the cum moment', a9.moments ? (a9.category === 'CLIMAX' && a9.act === 'VAGINAL' && a9.loops === 1 && a9.events.includes('CUM:FACE')) : a9.category === 'CLIMAX', a9);
      C('A9 Magic cowgirl gives voices to both (her moans, his woohoo)', a9.herVoices > 0 && a9.himVoices > 0, { her: a9.herVoices, him: a9.himVoices });

      // A10 - Magic "Lap ride" on an armchair: he sits on the seat (feet on its foot spots), she sits on his lap; nothing
      // goes into the chair; a lying-length couple is not laid on a loveseat; nothing moves after Magic is done (the
      // ready pose's own lift has landed before Magic places the couple)
      const a10 = await page.evaluate(async () => {
        const pl = await import('/js/placing.js');
        const out = {};
        await R.magic('sitting', 'chair_living');
        const info = await app._furnitureInfo('chair_living'), g = pl.gridOf(info), seat = info.slots.find(x => x.kind === 'seat');
        const him = R.byFrame('ym'), her = R.byFrame('yf'), hv = R.view(him), fv = R.view(her);
        const p = app.store.project;
        let into = 0;
        for (let f = 0; f < p.length; f += 3) {
          app.pipeline.apply(f, { physics: true, overrides: false });
          for (const v of [hv, fv]) for (const n of R.B.POSABLE) { const b = v.bone(n); if (!b) continue; const q = v.worldPos(n), h = pl.gridHeight(g, q.x, q.z); if (h !== null && q.y < h - 0.03 && q.y > h - 0.3) into = Math.max(into, h - q.y); }
        }
        app.pipeline.apply(0, { physics: false, overrides: false });
        const hips = v => v.worldPos('b__L_Thigh__').add(v.worldPos('b__R_Thigh__')).multiplyScalar(0.5);
        const feet = ['L', 'R'].map(sd => R.PM.spacePos(hv, hv.bone(`b__${sd}_Foot__`)).distanceTo(new R.THREE.Vector3(...seat.feet[sd])));
        out.lap = { where: app.lastMagic.where, hisHipsOverSeat: +(hips(hv).y - pl.gridHeight(g, seat.pos[0], seat.pos[2] + 0.1)).toFixed(3), herOverHis: +(hips(fv).y - hips(hv).y).toFixed(3),
          feetCm: feet.map(d => +(d * 100).toFixed(2)), intoChairCm: +(into * 100).toFixed(2), herHands: ['L hand', 'R hand'].filter(l => her.pins[l]), hisHolds: Object.keys(him.pins).filter(l => R.B.isHold(him.pins[l])) };
        await R.magic('anal', 'loveseat');
        out.loveseatAnal = app.lastMagic.where;
        await R.magic('cowgirl', 'double_bed');
        const before = R.view(R.byFrame('yf')).worldPos('b__Pelvis__');
        await R.sleep(700);
        app.pipeline.apply(0, { physics: false, overrides: false });
        out.lateMoveCm = +(R.view(R.byFrame('yf')).worldPos('b__Pelvis__').distanceTo(before) * 100).toFixed(3);
        return out;
      });
      results.A10 = a10;
      C('A10 Magic Lap ride on the armchair: he sits on the seat (hips 10 cm over it, feet on its foot spots), she on his lap',
        a10.lap.where === 'lap' && Math.abs(a10.lap.hisHipsOverSeat - 0.10) < 0.01 && a10.lap.herOverHis > 0.12 && a10.lap.feetCm.every(d => d < 1) && a10.lap.hisHolds.length === 2 && a10.lap.herHands.length === 2, a10.lap);
      C('A10 ...nothing goes more than 3 cm into the chair over the loop', a10.lap.intoChairCm <= 3, `${a10.lap.intoChairCm} cm`);
      C('A10 a couple longer than the loveseat is not laid on it (anal: in front of it)', a10.loveseatAnal === 'front', a10.loveseatAnal);
      C("A10 nothing moves after Magic is done (the ready pose's lift landed first)", a10.lateMoveCm < 0.05, `${a10.lateMoveCm} cm`);
    }

    // ============================================================== B. hands (spec_bodies 5.6)
    if (want('B')) {
      const b1 = await page.evaluate(async () => {
        await R.magic('kiss', 'floor');
        const s = R.byFrame('yf'), v = R.view(s);
        app.pipeline.apply(0, { physics: false });
        const out = {};
        for (const id of R.HA.SHAPE_ORDER) {
          for (const side of ['L', 'R']) R.HA.applyHandShape(v, side, id, 1);
          v.group.updateMatrixWorld(true);
          let worst = 9, pair = null;
          for (const side of ['L', 'R']) {
            // fingertip ends: the tip joint + its bone length along x (the tip bone has no child: use the middle joint's length)
            const tip = f => {
              const b2 = v.bone(`b__${side}_${f}2__`), b1 = v.bone(`b__${side}_${f}1__`);
              const len = v.restByName[`b__${side}_${f}2__`].pos.length();
              return new R.THREE.Vector3(len * (side === 'L' ? 1 : -1) * 0.9, 0, 0).applyMatrix4(b2.matrixWorld);
            };
            const F = ['Thumb', 'Index', 'Mid', 'Ring', 'Pinky'].map(tip);
            for (let i = 1; i < 4; i++) { const d = F[i].distanceTo(F[i + 1]); if (d < worst) { worst = d; pair = `${side} ${i}-${i + 1}`; } }
          }
          out[id] = { minTipMm: +(worst * 1000).toFixed(1), pair };
        }
        return out;
      });
      results.B1 = b1;
      const bad = Object.entries(b1).filter(([, x]) => x.minTipMm <= 8);
      C('B1 each of the 10 shapes on both hands: neighbouring fingertips > 8 mm apart', !bad.length, bad.length ? bad : Object.fromEntries(Object.entries(b1).map(([k, x]) => [k, x.minTipMm])));

      // B2 - a finger ring dragged past its range stops at the Appendix C limit; with limits off it passes
      const b2 = await page.evaluate(async () => {
        const s = R.byFrame('yf'), v = R.view(s), it = app.interact, gz = app.vp.gizmo;
        s.pins = {};                              // free arms (a held arm is re-solved onto the partner)
        app.setTool('rotate');
        const turn = (name, deg, limits) => {
          app.naturalLimits = limits;
          app.store.selected = { sim: s.id, bone: name };
          it.selectBone(s.id, name);
          gz.dispatchEvent({ type: 'mouseDown' });
          gz.dispatchEvent({ type: 'dragging-changed', value: true });
          const b = v.bone(name);
          b.quaternion.copy(v.restByName[name].quat).multiply(new R.THREE.Quaternion().setFromAxisAngle(new R.THREE.Vector3(0, 0, 1), deg * Math.PI / 180));
          gz.dispatchEvent({ type: 'objectChange' });
          const rv = R.PM.quatToRv(v.restByName[name].quat.clone().invert().multiply(b.quaternion));
          gz.dispatchEvent({ type: 'mouseUp' });
          gz.dispatchEvent({ type: 'dragging-changed', value: false });
          return +rv[2].toFixed(2);
        };
        const out = {
          index1On: turn('b__L_Index1__', 140, true), index1Off: turn('b__L_Index1__', 140, false),
          index1BackOn: turn('b__R_Index1__', -40, true),
          forearmOn: turn('b__L_Forearm__', 175, true),
          knuckleX: (() => { app.naturalLimits = true; it.selectBone(s.id, 'b__L_Mid0__'); return { x: gz.showX, y: gz.showY, z: gz.showZ }; })(),
          knuckleXoff: (() => { app.naturalLimits = false; it.selectBone(s.id, 'b__L_Mid0__'); return { x: gz.showX, y: gz.showY, z: gz.showZ }; })(),
          hud: document.getElementById('hud')?.textContent || '',
        };
        app.naturalLimits = true;
        return out;
      });
      results.B2 = b2;
      C('B2 a finger ring dragged to 140 degrees stops at 100 (Appendix C); with limits off it passes', Math.abs(b2.index1On - 100) < 0.05 && Math.abs(b2.index1Off - 140) < 0.05, b2);
      C('B2 backwards stops at -3 (right hand mirrored), an elbow at 155', Math.abs(b2.index1BackOn + 3) < 0.05 && Math.abs(b2.forearmOn - 155) < 0.05, b2);
      C('B2 knuckles: spread and curl rings only while limits are on', !b2.knuckleX.x && b2.knuckleX.y && b2.knuckleX.z && b2.knuckleXoff.x, { on: b2.knuckleX, off: b2.knuckleXoff });

      const b3 = await page.evaluate(async () => {
        const v = R.view(R.byFrame('yf'));
        const out = {};
        for (const side of ['L', 'R']) {
          R.HA.applyHandShape(v, side, 'flat', 1);
          R.HA.setCurl(v, side, 0.6); R.HA.setSpread(v, side, 0.4); R.HA.setThumb(v, side, 0.3);
          out[side] = R.HA.readHand(v, side);
        }
        return out;
      });
      results.B3 = b3;
      C('B3 readHand after setCurl(0.6) gives 0.6 +- 0.02 (both hands; spread 0.4 and thumb 0.3 too)', ['L', 'R'].every(s => Math.abs(b3[s].curl - 0.6) <= 0.02 && Math.abs(b3[s].spread - 0.4) <= 0.02 && Math.abs(b3[s].thumb - 0.3) <= 0.02), b3);

      const b4 = await page.evaluate(() => {
        const v = R.view(R.byFrame('yf'));
        const ids = R.HA.MINED;
        let worst = 999, pair = null;
        for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
          const a = R.HA.shapeQuats(v, 'L', ids[i]), b = R.HA.shapeQuats(v, 'L', ids[j]);
          const most = Math.max(...Object.keys(a).map(n => R.qang(a[n], b[n])));
          if (most < worst) { worst = most; pair = `${ids[i]} / ${ids[j]}`; }
        }
        return { worstDeg: +worst.toFixed(1), pair };
      });
      results.B4 = b4;
      C('B4 the mined shapes are at least 14 degrees apart at their most different joint', b4.worstDeg >= 14, b4);

      // B5 - the inspector's hand-shape row: 10 buttons, a click shapes the hand and keys it; sliders
      const b5 = await page.evaluate(async () => {
        await R.magic('kiss', 'floor');
        const s = R.byFrame('yf');
        app.setTool('rotate');
        app.store.selected = { sim: s.id, bone: 'b__R_Index1__' };
        app.interact.selectBone(s.id, 'b__R_Index1__');
        app.emitSelection();
        const btns = [...document.querySelectorAll('#inspector .hand-shape')];
        const fist = btns.find(b => b.dataset.shape === 'fist');
        fist && fist.click();
        await R.sleep(30);
        const key = s.keys.find(k => k.frame === Math.round(app.store.frame));
        const v = R.view(s);
        const cur = R.HA.currentShape(v, 'R');
        const on = document.querySelector('#inspector .hand-shape.on')?.dataset.shape;
        const sliders = [...document.querySelectorAll('#inspector .hand-sliders .slider label')].map(x => x.textContent);
        return { buttons: btns.length, keyedFist: !!(key && key.pose.rot.b__R_Index1__), cur, on, sliders, limitsSwitch: !!document.querySelector('#inspector .limit-row') };
      });
      results.B5 = b5;
      C('B5 a finger shows 10 hand shapes; Fist shapes the hand, keys it and lights up', b5.buttons === 10 && b5.keyedFist && b5.cur === 'fist' && b5.on === 'fist', b5);
      C('B5 Curl / Spread / Thumb sliders and the Natural limits switch are there', b5.sliders.join() === 'Curl,Spread,Thumb' && b5.limitsSwitch, b5.sliders);
    }

    // ============================================================== C. spec_editing 16: checks 8, 16, 17
    if (want('C')) {
      // 8 - Whole back 40 degree turn -> 10, 12, 12, 6 degrees on Spine0/1/2/Neck
      const c8 = await page.evaluate(async () => {
        await R.magic('standing', 'floor');
        const s = R.byFrame('yf'), v = R.view(s), it = app.interact, gz = app.vp.gizmo;
        app.setTool('rotate');
        app.setTurnGroup('back');
        const names = ['b__Spine0__', 'b__Spine1__', 'b__Spine2__', 'b__Neck__'];
        app.store.selected = { sim: s.id, bone: 'b__Spine1__' };
        it.selectBone(s.id, 'b__Spine1__');
        app.beginEdit(s.id);
        const before = names.map(n => v.bone(n).quaternion.clone());
        gz.dispatchEvent({ type: 'mouseDown' });
        gz.dispatchEvent({ type: 'dragging-changed', value: true });
        // the gizmo turns Spine1 by 40 degrees about its own local z (a bend)
        v.bone('b__Spine1__').quaternion.multiply(new R.THREE.Quaternion().setFromAxisAngle(new R.THREE.Vector3(0, 0, 1), 40 * Math.PI / 180));
        gz.dispatchEvent({ type: 'objectChange' });
        gz.dispatchEvent({ type: 'mouseUp' });
        gz.dispatchEvent({ type: 'dragging-changed', value: false });
        const turns = names.map((n, i) => +R.qang(before[i], v.bone(n).quaternion).toFixed(3));
        const keyed = s.keys.find(k => k.frame === Math.round(app.store.frame));
        const keyedTurns = names.map((n, i) => +R.qang(before[i], new R.THREE.Quaternion().fromArray(keyed.pose.rot[n])).toFixed(3));
        app.setTurnGroup('none');
        return { turns, keyedTurns };
      });
      results.C8 = c8;
      C('C8 Whole back: a 40 degree turn -> 10 / 12 / 12 / 6 degrees on Spine0/1/2/Neck (+-0.1), and keyed so', [10, 12, 12, 6].every((w, i) => Math.abs(c8.turns[i] - w) <= 0.1 && Math.abs(c8.keyedTurns[i] - w) <= 0.1), c8);

      // 16 - ranged pin 20-45, fade 3: the chain equals the unpinned pose at <= 16 and >= 49; the hand within 1 mm of
      // the pin at 20-45
      const c16 = await page.evaluate(async () => {
        await R.magic('doggy', 'double_bed');
        const her = R.byFrame('yf'), v = R.view(her), p = app.store.project;
        her.pins = {};
        const chain = R.B.LIMBS['R hand'];
        const free = [];
        for (let f = 0; f < p.length; f++) { app.pipeline.apply(f, { physics: false, overrides: false }); free.push(chain.map(n => v.bone(n).quaternion.clone())); }
        app.setFrame(20);
        app.pipeline.apply(20, { physics: false, overrides: false });
        const at = R.PM.spacePos(v, v.bone('b__R_Hand__')).toArray();
        her.pins['R hand'] = { at, from: 20, to: 45, fade: 3 };
        let outWorst = 0, inWorst = 0;
        for (let f = 0; f < p.length; f++) {
          app.pipeline.apply(f, { physics: false, overrides: false });
          if (f <= 16 || f >= 49) outWorst = Math.max(outWorst, ...chain.map((n, i) => R.qang(free[f][i], v.bone(n).quaternion)));
          if (f >= 20 && f <= 45) inWorst = Math.max(inWorst, R.PM.spacePos(v, v.bone('b__R_Hand__')).distanceTo(new R.THREE.Vector3().fromArray(at)));
        }
        return { outsideDeg: +outWorst.toFixed(6), insideMm: +(inWorst * 1000).toFixed(3) };
      });
      results.C16 = c16;
      C('C16 pin 20-45 (fade 3): unpinned at <= 16 and >= 49, the hand within 1 mm of the pin at 20-45', c16.outsideDeg < 1e-3 && c16.insideMm <= 1, c16);

      // 17 - "Let go, keep the look" on a pinned hand under a thrust: within 1 cm of the old pin on every frame after
      const c17 = await page.evaluate(async () => {
        await R.magic('doggy', 'double_bed');
        const him = R.byFrame('ym'), v = R.view(him), p = app.store.project;
        him.pins = { ...Object.fromEntries(Object.entries(him.pins).filter(([, x]) => !R.B.isHold(x))) };
        app.pipeline.apply(0, { physics: false, overrides: false });
        const at = R.PM.spacePos(v, v.bone('b__L_Hand__')).clone().add(new R.THREE.Vector3(0, 0.05, 0));
        him.pins['L hand'] = at.toArray();
        const keysBefore = him.keys.length;
        app.bakePin(him.id, 'L hand');
        const him2 = app.store.sim(him.id);
        let worst = 0, at2 = -1;
        for (let f = 0; f < p.length; f++) {
          app.pipeline.apply(f, { physics: false, overrides: false });
          const d = R.PM.spacePos(v, v.bone('b__L_Hand__')).distanceTo(at);
          if (d > worst) { worst = d; at2 = f; }
        }
        return { pinGone: !him2.pins['L hand'], keysBefore, keysAfter: him2.keys.length, breakdowns: him2.keys.filter(k => k.type === 'breakdown').length, worstCm: +(worst * 100).toFixed(3), atFrame: at2, thrust: him2.layers.some(l => l.type === 'thrust') };
      });
      results.C17 = c17;
      C('C17 "Let go, keep the look" under a thrust: the hand stays within 1 cm of the old pin on every frame', c17.pinGone && c17.thrust && c17.worstCm <= 1, c17);

      // 17b - the same for a hold (her hips ride): the hand keeps following her after letting go
      const c17b = await page.evaluate(async () => {
        await R.magic('cowgirl', 'double_bed');
        const him = R.byFrame('ym'), p = app.store.project;
        const limb = Object.keys(him.pins).find(l => R.B.isHold(him.pins[l]));
        const hold = JSON.parse(JSON.stringify(him.pins[limb]));
        app.bakePin(him.id, limb);
        const h2 = app.store.sim(him.id);
        let worst = 0;
        for (let f = 0; f < p.length; f++) {
          app.pipeline.apply(f, { physics: false, overrides: false });
          const d = R.Hd.limbPoint(R.view(h2), limb).distanceTo(R.skinOf(hold));
          worst = Math.max(worst, d);
        }
        return { limb, gone: !R.B.isHold(h2.pins[limb]), worstCm: +(worst * 100).toFixed(2) };
      });
      results.C17b = c17b;
      C('C17b "Let go, keep the look" on a hold: the palm keeps following her (< 2.5 cm from the skin point)', c17b.gone && c17b.worstCm <= 2.5, c17b);
    }

    // ============================================================== D. loop continuity (lag + look + tremble)
    if (want('D')) {
      const d = await page.evaluate(async () => {
        await R.magic('cowgirl', 'double_bed', { intensity: 0.9 });
        const p = app.store.project;
        p.length = 90;
        for (const s of p.sims) {
          s.lag = { arms: 4, head: 3 };
          if (R.MO.MOTIONS.look && !s.layers.some(l => l.type === 'look')) { const l = R.MO.newLayer('look'); l.weight = 0.6; s.layers.push(l); }
          if (R.MO.MOTIONS.tremble && !s.layers.some(l => l.type === 'tremble')) { const l = R.MO.newLayer('tremble'); s.layers.push(l); }
        }
        app.pipeline.simulateIfNeeded(true);
        const layers = p.sims.map(s => s.layers.map(l => l.type));
        const views = p.sims.map(s => R.view(s));
        const snap = () => views.map(v => v.bones.map(b => b.quaternion.clone()));
        const diff = (a, b) => { let m = 0; a.forEach((qs, i) => qs.forEach((q, k) => { m = Math.max(m, R.qang(q, b[i][k])); })); return m; };
        app.pipeline.apply(0, { physics: true, overrides: false }); const s0 = snap();
        app.pipeline.apply(90, { physics: true, overrides: false }); const s90 = snap();
        let biggest = 0, prev = null;
        for (let f = 0; f < 90; f++) { app.pipeline.apply(f, { physics: false, overrides: false }); const s = snap(); if (prev) biggest = Math.max(biggest, diff(prev, s)); prev = s; }
        app.pipeline.apply(0, { physics: false, overrides: false }); const seam = diff(prev, snap());
        // the look turns the head toward the partner's face; the eyes get lookUp/lookSide
        return { layers, wrapDeg: +diff(s0, s90).toFixed(4), seamDeg: +seam.toFixed(3), biggestDeg: +biggest.toFixed(3), look: !!R.MO.MOTIONS.look, tremble: !!R.MO.MOTIONS.tremble,
          face: app.pipeline.lastFace.get(p.sims[0].id) };
      });
      results.D = d;
      C(`D a lagged${d.look ? ', looking' : ''}${d.tremble ? ' and trembling' : ''} 90-frame loop: apply(0) = apply(90) within 0.1 degrees`, d.wrapDeg <= 0.1, d);
      C('D the step from frame 89 to 0 is no bigger than the biggest step inside the loop', d.seamDeg <= d.biggestDeg + 1e-6, { seam: d.seamDeg, biggest: d.biggestDeg });
      C('D look-at and tremble motions are there (R2-3) and run in pass B', d.look && d.tremble, { look: d.look, tremble: d.tremble, layers: d.layers });

      // lag: the arms reach each pose 4 frames late, the rest on time
      const dl = await page.evaluate(async () => {
        await R.magic('standing', 'floor');
        const s = R.byFrame('yf'), p = app.store.project;
        s.layers = [];
        const v = R.view(s);
        // two keys that differ: frame 0 and 45
        const k0 = s.keys[0];
        const k1 = JSON.parse(JSON.stringify({ ...k0, frame: 45 }));
        const q = new R.THREE.Quaternion().fromArray(k1.pose.rot.b__L_UpperArm__).multiply(new R.THREE.Quaternion().setFromAxisAngle(new R.THREE.Vector3(0, 0, 1), 0.8));
        k1.pose.rot.b__L_UpperArm__ = q.toArray();
        k1.pose.rot.b__Spine1__ = new R.THREE.Quaternion().fromArray(k1.pose.rot.b__Spine1__).multiply(new R.THREE.Quaternion().setFromAxisAngle(new R.THREE.Vector3(0, 0, 1), 0.3)).toArray();
        s.keys = [k0, k1];
        const at = (f, lag) => { s.lag = lag; app.pipeline.apply(f, { physics: false, overrides: false }); return { arm: v.bone('b__L_UpperArm__').quaternion.clone(), spine: v.bone('b__Spine1__').quaternion.clone() }; };
        const late = at(30, { arms: 4, head: 0 }), onTime26 = at(26, null), onTime30 = at(30, null);
        s.lag = null;
        return { armIsFrame26: +R.qang(late.arm, onTime26.arm).toFixed(4), spineOnTime: +R.qang(late.spine, onTime30.spine).toFixed(4), armMoved: +R.qang(onTime26.arm, onTime30.arm).toFixed(2) };
      });
      results.Dlag = dl;
      C('D Follow-through: arms 4 frames late take frame 26\'s arm at frame 30, the back stays on time', dl.armIsFrame26 < 1e-3 && dl.spineOnTime < 1e-3 && dl.armMoved > 0.5, dl);
    }

    // ============================================================== E. performance
    if (want('E')) {
      const e = await page.evaluate(async () => {
        const time = (n = 300) => {
          const p = app.store.project;
          for (let k = 0; k < 60; k++) app.pipeline.apply(k % p.length, { physics: true, overrides: false });
          const t = [];
          for (let k = 0; k < n; k++) { const t0 = performance.now(); app.pipeline.apply(k % p.length, { physics: true, overrides: false }); t.push(performance.now() - t0); }
          t.sort((a, b) => a - b);
          return { median: +t[n >> 1].toFixed(3), p90: +t[Math.floor(n * 0.9)].toFixed(3) };
        };
        await R.magic('cowgirl', 'double_bed');
        const p = app.store.project;
        const him = R.byFrame('ym'), her = R.byFrame('yf');
        // no holds
        const saved = JSON.parse(JSON.stringify(p.sims.map(s => s.pins)));
        for (const s of p.sims) for (const l of Object.keys(s.pins)) if (R.B.isHold(s.pins[l])) delete s.pins[l];
        const layersSaved = p.sims.map(s => s.layers);
        const plain = time();
        // 4 holds: his two hands on her hips, her two hands on his chest / shoulders
        p.sims.forEach((s, i) => { s.pins = saved[i]; });
        app.pipeline.apply(0, { physics: false, overrides: false });
        for (const limb of ['L hand', 'R hand']) if (!R.B.isHold(her.pins[limb])) {
          const hv = R.view(her), mv = R.view(him);
          const hit = R.SK.nearestSkin(mv, R.Hd.limbPoint(hv, limb), 0.6);
          if (hit) R.Hd.makeHold(app, her.id, limb, { sim: him, v: mv }, hit, { checkpoint: false, quiet: true, shape: false });
        }
        const n = p.sims.reduce((a, s) => a + Object.values(s.pins).filter(R.B.isHold).length, 0);
        const held = time();
        return { plain, held, holds: n, layers: layersSaved.map(l => l.map(x => x.type)) };
      });
      results.E = e;
      C('E pipeline.apply, 2 sims (Magic cowgirl, no holds): median <= 1.0 ms', e.plain.median <= 1.0, e.plain);
      C('E pipeline.apply, 2 sims with 4 holds: median <= 1.5 ms', e.holds === 4 && e.held.median <= 1.5, { ...e.held, holds: e.holds });
    }

    // ============================================================== F. contracts other slices use
    if (want('F')) {
      const f = await page.evaluate(async () => {
        const out = {};
        out.bodyParts = !R.B.BODY_PARTS.upper.some(n => /Jaw|Tounge/.test(n)) && R.B.BODY_PARTS.face.length === 0 && R.B.BODY_PARTS.hands.length === 32;
        out.turnGroups = R.B.TURN_GROUPS.back.w.reduce((a, b) => a + b, 0) === 1 && Math.abs(R.B.TURN_GROUPS.neckHead.w.reduce((a, b) => a + b, 0) - 1) < 1e-9;
        out.pinAt = JSON.stringify([R.B.pinAt([1, 2, 3]), R.B.pinAt({ at: [4, 5, 6] }), R.B.pinAt({ sim: 's', bone: 'b' })]) === '[[1,2,3],[4,5,6],null]';
        const w = f => +R.B.pinWeight({ at: [0, 0, 0], from: 20, to: 45, fade: 3 }, f, 90, true).toFixed(3);
        out.pinWeight = [16, 17, 18, 19, 20, 45, 46, 47, 48].map(w);
        out.pinWeightWrap = [80, 5, 10, 60].map(f => +R.B.pinWeight({ at: [0, 0, 0], from: 80, to: 5, fade: 3 }, f, 90, true).toFixed(3));
        const q = new R.THREE.Quaternion().setFromEuler(new R.THREE.Euler(0.3, -0.2, 0.5, 'XYZ')), rest = new R.THREE.Quaternion().setFromEuler(new R.THREE.Euler(0.1, 0.2, -0.3));
        out.restEuler = R.qang(R.PM.fromRestEuler(rest, R.PM.restEuler(q, rest)), q) < 1e-6;
        out.segSegDist = Math.abs(R.PM.segSegDist(new R.THREE.Vector3(0, 0, 0), new R.THREE.Vector3(1, 0, 0), new R.THREE.Vector3(0.5, 1, -1), new R.THREE.Vector3(0.5, 1, 1)) - 1) < 1e-9;
        out.pickers = Array.isArray(app.interact.pickers) && typeof app.interact.attachGizmo === 'function';
        // a picker gets the click before the bodies do; attachGizmo moves any object and reports it
        let picked = 0;
        const fn = (e, kind) => { if (kind === 'click') { picked++; return true; } return false; };
        app.interact.pickers.push(fn);
        const r = app.vp.canvas.getBoundingClientRect();
        app.interact._click({ clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, button: 0, altKey: false });
        app.interact.pickers.splice(app.interact.pickers.indexOf(fn), 1);
        out.pickerFirst = picked === 1;
        const obj = new R.THREE.Object3D(); app.vp.scene.add(obj);
        let changed = 0, ended = 0;
        const detach = app.interact.attachGizmo(obj, { onChange: () => changed++, onEnd: () => ended++, modes: ['translate', 'rotate'] });
        const gz = app.vp.gizmo;
        gz.dispatchEvent({ type: 'mouseDown' }); obj.position.x += 0.1; gz.dispatchEvent({ type: 'objectChange' }); gz.dispatchEvent({ type: 'mouseUp' });
        const toggled = app.interact.toggleGizmoMode() && gz.mode === 'rotate';
        detach(); app.vp.scene.remove(obj);
        out.attachGizmo = changed === 1 && ended === 1 && toggled && !app.interact.active;
        out.mixins = ['makeHold', 'holdNamed', 'holdNearest', 'letGo', 'bakePin', 'setPinRange', 'setHandShape', 'setHandSlider', 'setNaturalLimits', 'setTurnGroup', 'rebindHold'].filter(m => typeof app[m] !== 'function');
        out.palette = (() => { const cmds = app.hooks.commands.flatMap(fn => { try { return fn(app) || []; } catch { return []; } }); return ['natural-limits', 'hand-fist', 'turn-back'].filter(id => !cmds.some(c => c.id === id)); })();
        // the pipeline passes the face style to talkAt: creator projects talk for a voice line's real length, classic
        // ones keep the old rule (1.1 s here)
        await R.magic('kiss', 'floor');
        const p = app.store.project, s = p.sims[0];
        s.sounds = [{ frame: 0, name: 'vo_r22_test_moan', kind: 'voice', sec: 2.5 }];
        const openAt = (style, f) => { p.faceStyle = style; app.pipeline.apply(f, { physics: false, overrides: false }); const fc = app.pipeline.lastFace.get(s.id); return +(((fc && fc.open) || 0)).toFixed(3); };
        out.talk = { creator60: openAt('creator', 60), classic60: openAt('classic', 60), creator10: openAt('creator', 10), classic10: openAt('classic', 10) };
        p.faceStyle = 'creator';
        // a click on a sim's hair selects that sim (hair parts are pickable): a small hair cap skinned to the head
        {
          const THREE = R.THREE, s0 = p.sims[0], other = p.sims[1], v0 = R.view(s0), hi = v0.index('b__Head__');
          const bind = v0.skeleton.boneInverses[hi].clone().invert();
          const pts = [], faces = [];
          // (a box round the whole head, like hair over the skull)
          const corner = (x, y, z) => { pts.push(...new THREE.Vector3(0.1 + x, 0.02 + y, z).applyMatrix4(bind).toArray()); };
          for (const x of [-0.14, 0.14]) for (const y of [-0.14, 0.14]) for (const z of [-0.14, 0.14]) corner(x, y, z);
          for (const f of [[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]]) faces.push(...f);
          v0.addPart({ name: 'test hair', meshes: [{ positions: pts, normals: [], uvs: [], faces, bones: Array(8).fill(0).flatMap(() => [hi, 0, 0, 0]), weights: Array(8).fill(0).flatMap(() => [1, 0, 0, 0]) }] }, null, { role: 'hair' });
          app.setTool('rotate');
          app.selectSim(other.id);
          app.pipeline.apply(0, { physics: false, overrides: false });
          v0.group.updateMatrixWorld(true);
          const head = v0.bone('b__Head__'), c = new THREE.Vector3(0.1, 0.02, 0).applyMatrix4(head.matrixWorld);
          // from the side of the head (in a kiss the partner's head is in front of it)
          const side = new THREE.Vector3(0, 0, 1).applyQuaternion(head.getWorldQuaternion(new THREE.Quaternion())).setY(0).normalize();
          app.vp.controls.lookFrom(c.clone().addScaledVector(side, 1.1).add(new THREE.Vector3(0, 0.3, 0)), c);
          app.vp.camera.updateMatrixWorld(true);
          const q = c.clone().project(app.vp.camera), rc = app.vp.canvas.getBoundingClientRect();
          const ev = { clientX: rc.left + (q.x + 1) / 2 * rc.width, clientY: rc.top + (1 - q.y) / 2 * rc.height, button: 0, altKey: false };
          const hit = app.vp.pick(ev, app.interact._meshes());
          app.interact._click(ev);
          out.hairClick = { hitRole: hit && hit.object.userData.role, hitSoft: hit && !!hit.object.userData.soft, selected: app.store.selected.sim === s0.id, bone: app.store.selected.bone, parts: (v0.parts || []).length };
          v0.removeParts('hair');
          app.selectSim(other.id);
        }
        out.pageErrors = R.errors.slice(0, 5);
        return out;
      });
      results.F = f;
      C('F BODY_PARTS without jaw / tongue, face part empty (plan 2.1); TURN_GROUPS shares add up to 1', f.bodyParts && f.turnGroups, f);
      C('F pinAt / pinWeight (range 20-45 fade 3: 0 at 16-17, rises 18-19, 1 inside; wraps 80-5)', f.pinAt && JSON.stringify(f.pinWeight) === JSON.stringify([0, 0, 0.259, 0.741, 1, 1, 0.741, 0.259, 0]) && JSON.stringify(f.pinWeightWrap) === JSON.stringify([1, 1, 0, 0]), { w: f.pinWeight, wrap: f.pinWeightWrap });
      C('F posemath: restEuler / fromRestEuler round trip, segSegDist exported', f.restEuler && f.segSegDist, f);
      C('F interact.pickers get clicks first; attachGizmo moves any object (T toggles modes)', f.pickers && f.pickerFirst && f.attachGizmo, f);
      C('F app methods and palette commands are there', !f.mixins.length && !f.palette.length, { missingMethods: f.mixins, missingCommands: f.palette });
      C("F a click on a sim's hair lands on the hair (not its see-through edges) and selects that sim's head", f.hairClick && f.hairClick.hitRole === 'hair' && !f.hairClick.hitSoft && f.hairClick.selected && f.hairClick.bone === 'b__Head__', f.hairClick);
      C('F talking: a 2.5 s voice line keeps the mouth moving at 2 s in a creator project, the classic rule (1.1 s) stays', f.talk.creator60 > 0 && f.talk.classic60 === 0 && f.talk.creator10 > 0 && f.talk.classic10 > 0, f.talk);
    }

    // ============================================================== G. screenshots
    if (SHOTS && want('G')) {
      const shots = [];
      const shotAt = async (pg, name) => { const f = await H.shot(pg, path.join(OUT, name)); shots.push(path.relative(H.ROOT, f)); };
      for (const [w, h] of [[1366, 768], [1920, 1080]]) {
        let pg = page;
        if (w !== 1366) {
          const o = await L.open(PORT, { w, h });
          page2 = o.browser; pg = o.page;
          await installHelpers(pg);
        }
        await pg.evaluate(async () => {
          await R.magic('cowgirl', 'double_bed');
          await R.sleep(1500);                                    // the camera swoop of a new Magic scene ends
          const him = R.byFrame('ym');
          app.selectSim(him.id);
          app.setTool('ik');
          app.setFrame(12);
          const v = R.view(him), c = v.worldPos('b__Spine1__');
          app.vp.frame(c, 0.95, app.vp.viewDir ? app.vp.viewDir() : undefined);
          await R.sleep(400);
        });
        await shotAt(pg, `holds_cowgirl_${w}.png`);
        // three frames of the loop, closer on the hands
        for (const f of [0, 30, 60]) {
          await pg.evaluate(async f => { app.setFrame(f); await R.sleep(250); }, f);
          await shotAt(pg, `holds_frame${f}_${w}.png`);
        }
        // the ▾ menu
        await pg.evaluate(async () => {
          const cell = [...document.querySelectorAll('#inspector .pin-cell')].find(c => c.textContent.includes('Right hand'));
          cell && cell.querySelector('.pin-more').click();
          await R.sleep(200);
        });
        await shotAt(pg, `pin_menu_${w}.png`);
        await pg.evaluate(() => document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })));
        // the hand shape card on a finger
        await pg.evaluate(async () => {
          const her = R.byFrame('yf');
          app.setTool('rotate');
          app.store.selected = { sim: her.id, bone: 'b__R_Index1__' };
          app.interact.selectBone(her.id, 'b__R_Index1__');
          app.emitSelection();
          app.setHandShape(her.id, 'R', 'grip');
          const v = R.view(her);
          app.vp.frame(v.worldPos('b__R_Hand__'), 0.28);
          await R.sleep(400);
        });
        await shotAt(pg, `hand_shapes_card_${w}.png`);
        if (pg !== page) { await pg.evaluate(() => app.store.setDirty(false)).catch(() => {}); await page2.close(); page2 = null; }
      }
      // close-ups of every shape (fov 20)
      await page.evaluate(async () => { await R.magic('kiss', 'floor'); await R.sleep(1500); });
      for (const id of ['relaxed', 'soft', 'grip', 'fist', 'flat', 'point', 'two', 'spread', 'pinch', 'stroke']) {
        await page.evaluate(async id => {
          const s = R.byFrame('yf'), v = R.view(s);
          app.setHandShape(s.id, 'R', id, { both: true });
          app.store.selected = { sim: s.id, bone: null };
          app.interact.setTool('rotate'); app.vp.gizmo.detach();
          const cam = app.vp.camera, fov = cam.fov;
          cam.fov = 20; cam.updateProjectionMatrix();
          const hand = v.worldPos('b__R_Hand__'), palmN = new R.THREE.Vector3(0, 1, 0).applyQuaternion(v.bone('b__R_Hand__').getWorldQuaternion(new R.THREE.Quaternion()));
          const at = v.worldPos('b__R_Mid1__');
          app.vp.controls.lookFrom ? app.vp.controls.lookFrom(at.clone().addScaledVector(palmN, -0.55).add(new R.THREE.Vector3(0, 0.12, 0)), at) : 0;
          await R.sleep(300);
          window.__fov = fov;
        }, id);
        await shotAt(page, `hand_${id}.png`);
      }
      await page.evaluate(() => { app.vp.camera.fov = window.__fov || 45; app.vp.camera.updateProjectionMatrix(); });
      results.shots = shots;
      C('G screenshots written', shots.every(s => fs.existsSync(path.join(H.ROOT, s))), shots.join(', '));
    }

    const errs = logs.filter(l => l.type === 'pageerror' || (l.type === 'error' && !/Failed to load resource/.test(l.text)));
    C('no page errors', !errs.length, errs.slice(0, 5));
  } catch (e) {
    C('check script ran to the end', false, String(e && e.stack || e).slice(0, 800));
  } finally {
    // nothing unsaved when the page closes, so it sends no crash-recovery copy to the test server on its way out
    await page.evaluate(() => { try { app.store.setDirty(false); } catch { /* the app never started */ } }).catch(() => {});
    if (page2) await page2.close().catch(() => {});
    await browser.close();
  }
  results.seconds = Math.round((Date.now() - t0) / 1000);
  fs.writeFileSync(path.join(OUT, 'contact_results.json'), JSON.stringify({ rows, results }, null, 1));
  const ok = H.report(rows, `R2-2 contact checks (port ${PORT}, ${results.seconds} s)`);
  fs.writeFileSync(path.join(OUT, 'contact_table.txt'), rows.map(r => `${r.ok ? 'PASS' : 'FAIL'}  ${r.name}  ${typeof r.detail === 'string' ? r.detail : JSON.stringify(r.detail || '')}`.slice(0, 400)).join('\n'));
  process.exit(ok ? 0 : 1);
})();
