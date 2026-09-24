// R2-1 checks: spec_editing section 16, checks 1-7, 9-15, 18-22 and 24 (8, 16 and 17 are R2-2's; 23 is tools/e2e.js).
// Runs the full app through the shared harness (memory mode: saving and opening stay in the test; every writing
// route is answered in the browser). Reference files (check 20) go to the test server's own folder, so the server
// must run with ANIMATOR_SAVES / WICKED_PROJECTS_DIR in %TEMP% (lib.startServer does that).
//   node tools/checks/r2-1/editing.js --port 8851 [--only 1,2,20] [--no-shots] [--start]
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const cp = require('child_process');
const H = require('../lib/harness.js');
const L = require('./lib');

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const PORT = L.argPort();
const ONLY = arg('--only', null) ? new Set(arg('--only').split(',')) : null;
const SHOTS = !argv.includes('--no-shots');
const want = n => !ONLY || ONLY.has(String(n));
const rows = [];
const C = (name, ok, detail) => { rows.push([name, !!ok, detail]); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  ${detail === undefined ? '' : (typeof detail === 'string' ? detail : JSON.stringify(detail)).slice(0, 300)}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const results = {};

async function pe(page, fn, ...args) {
  let r;
  try { r = await page.evaluate(fn, ...args); } catch (e) { C(`page code ran (${fn.name || 'anonymous'})`, false, String(e.message || e).slice(0, 400)); return null; }
  if (r && Array.isArray(r.checks)) for (const [n, ok, d] of r.checks) C(n, ok, d);
  return r ? r.data : null;
}

// in-page helpers: window.__T
async function helpers(page) {
  await page.evaluate(async () => {
    const T = window.__T = {};
    T.KO = await import('/js/keyops.js');
    T.A = await import('/js/animation.js');
    T.THREE = await import('three');
    T.toasts = [];
    new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) if (n.textContent) T.toasts.push(n.textContent); }).observe(document.getElementById('toasts'), { childList: true, subtree: true });
    T.newToasts = n => T.toasts.slice(n);
    T.q = a => new T.THREE.Quaternion().fromArray(a);
    T.qang = (a, b) => { const d = Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]) / ((Math.hypot(...a) * Math.hypot(...b)) || 1); return 2 * Math.acos(Math.min(1, d)); };
    // largest difference between two poses: {deg, mm} over every bone either mentions (rest when missing)
    T.poseDiff = (a, b, skip = new Set()) => {
      let deg = 0, mm = 0;
      const ra = a.rot || {}, rb = b.rot || {};
      for (const n of new Set([...Object.keys(ra), ...Object.keys(rb)])) {
        if (skip.has(n)) continue;
        const r = T.A.restOf(n);
        const qa = ra[n] || (r && r.r), qb = rb[n] || (r && r.r);
        if (qa && qb) deg = Math.max(deg, T.qang(qa, qb) * 180 / Math.PI);
      }
      const pa = a.pos || {}, pb = b.pos || {};
      for (const n of new Set([...Object.keys(pa), ...Object.keys(pb)])) {
        if (skip.has(n)) continue;
        const r = T.A.restOf(n);
        const va = pa[n] || (r && r.t), vb = pb[n] || (r && r.t);
        if (va && vb) mm = Math.max(mm, Math.hypot(va[0] - vb[0], va[1] - vb[1], va[2] - vb[2]) * 1000);
      }
      return { deg, mm };
    };
    T.turn = (q, axis, deg) => T.q(q).multiply(new T.THREE.Quaternion().setFromAxisAngle(new T.THREE.Vector3(...axis).normalize(), deg * Math.PI / 180)).toArray();
    // a new couple animation, both sims with only their first key
    T.fresh = (template = 'couple') => {
      app.newScene(false, false, template);
      app.store.setDirty(false);
      app.setPlaying(false);
      app.timeline.clearSel();
      app.setPlayRange(null, { quiet: true });
      const sims = app.store.project.sims;
      return { F: sims[0], M: sims[1] };
    };
    // a key at `frame` for a sim: its first pose, with the spine and an arm turned by `deg`
    T.keyAt = (sim, frame, deg = 0, ease = 'auto') => {
      const base = JSON.parse(JSON.stringify(sim.keys.find(k => !k.faceOnly).pose));
      base.rot.b__Spine1__ = T.turn(base.rot.b__Spine1__, [0, 0, 1], deg);
      base.rot.b__L_UpperArm__ = T.turn(base.rot.b__L_UpperArm__, [1, 0, 0], deg * 1.5);
      sim.keys = sim.keys.filter(k => k.frame !== frame);
      sim.keys.push({ frame, ease, pose: base });
      T.A.sortKeys(sim.keys);
    };
    T.frames = sim => sim.keys.map(k => k.frame).join(',');
    T.geo = (frame, row, at = 15) => {
      const tl = app.timeline, r = tl.canvas.getBoundingClientRect();
      tl._layout();
      return { x: r.left + tl.xAt(frame), y: r.top + tl._y(row, at), top: r.top + tl.laneTop(row), lane: tl.lane, left: r.left, rtop: r.top };
    };
  });
}

async function drag(page, from, to, { steps = 10, mods = [] } = {}) {
  for (const m of mods) await page.keyboard.down(m);
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  for (let k = 1; k <= steps; k++) await page.mouse.move(from.x + (to.x - from.x) * k / steps, from.y + (to.y - from.y) * k / steps);
  await page.mouse.up();
  for (const m of mods) await page.keyboard.up(m);
  await sleep(120);
}
async function key(page, combo) {
  const parts = combo.split('+');
  for (const m of parts.slice(0, -1)) await page.keyboard.down(m);
  await page.keyboard.press(parts[parts.length - 1]);
  for (const m of parts.slice(0, -1).reverse()) await page.keyboard.up(m);
  await sleep(120);
}

(async () => {
  const OUT = L.OUT;
  const { browser, page, logs } = await H.open(PORT, { w: 1366, h: 768, memory: true });
  try {
    await helpers(page);
    await page.evaluate(() => { document.getElementById('home').classList.add('hidden'); app.showStep('motion'); });
    await sleep(300);

    // ============================================================ 1. select 3 keys on two sims, stretch x2, undo, redo
    if (want(1)) {
      await page.evaluate(() => {
        const { F, M } = __T.fresh();
        for (const s of [F, M]) { __T.keyAt(s, 5, 10); __T.keyAt(s, 10, 20); __T.keyAt(s, 15, 30); }
        app.refreshAll(); app.timeline.fit(); app.setFrame(0);
      });
      const a = await page.evaluate(() => ({ s: __T.geo(3, 0, 7), e: __T.geo(17, 1, 44) }));
      await drag(page, a.s, a.e, { mods: ['Control'] });
      const sel = await page.evaluate(() => ({ n: app.timeline.sel.size, ids: [...app.timeline.sel] }));
      C('1 Ctrl+drag a box selects the 3 keys of each sim (6)', sel.n === 6, sel);
      if (SHOTS) await H.shot(page, path.join(OUT, 'shot_box_selection_1366.png'));
      await page.evaluate(() => app.setFrame(0));
      const g = await page.evaluate(() => ({ k: __T.geo(10, 0), t: __T.geo(20, 0) }));
      await drag(page, g.k, { x: g.t.x, y: g.k.y }, { mods: ['Alt'] });
      const st = await page.evaluate(() => app.store.project.sims.map(__T.frames));
      C('1 Alt+drag stretches them x2 from the playhead (frame 0)', st.every(x => x === '0,10,20,30'), st);
      if (SHOTS) { await page.evaluate(() => app.setFrame(40)); await sleep(120); await H.shot(page, path.join(OUT, 'shot_stretch_bracket_1366.png')); }
      await key(page, 'Control+z');
      const un = await page.evaluate(() => app.store.project.sims.map(__T.frames));
      await key(page, 'Control+y');
      const re = await page.evaluate(() => app.store.project.sims.map(__T.frames));
      C('1 Ctrl+Z: frames exactly as before; Ctrl+Y: exactly doubled', un.every(x => x === '0,5,10,15') && re.every(x => x === '0,10,20,30'), { undo: un, redo: re });
    }

    // ============================================================ 2 + 3. drag over a key and back; drop onto a key
    if (want(2) || want(3)) {
      await page.evaluate(() => {
        const { F } = __T.fresh();
        __T.keyAt(F, 10, 20); __T.keyAt(F, 20, 40);
        app.refreshAll(); app.timeline.fit(); app.setFrame(0); app.timeline.clearSel();
        window.__k20 = JSON.stringify(F.keys.find(k => k.frame === 20).pose);
        window.__k10 = JSON.stringify(F.keys.find(k => k.frame === 10).pose);
      });
      const g = await page.evaluate(() => ({ k10: __T.geo(10, 0), k20: __T.geo(20, 0), k12: __T.geo(12, 0) }));
      if (want(2)) {
        await page.mouse.move(g.k10.x, g.k10.y); await page.mouse.down();
        for (let k = 1; k <= 10; k++) await page.mouse.move(g.k10.x + (g.k20.x - g.k10.x) * k / 10, g.k10.y);
        for (let k = 1; k <= 8; k++) await page.mouse.move(g.k20.x + (g.k12.x - g.k20.x) * k / 8, g.k10.y);
        await page.mouse.up(); await sleep(150);
        const r = await page.evaluate(() => { const F = app.store.project.sims[0]; return { frames: __T.frames(F), k20: JSON.stringify(F.keys.find(k => k.frame === 20)?.pose) === window.__k20 }; });
        C('2 dragging a key over another key and back deletes nothing', r.frames === '0,12,20' && r.k20, r);
        await key(page, 'Control+z');
      }
      if (want(3)) {
        const n0 = await page.evaluate(() => __T.toasts.length);
        await drag(page, g.k10, g.k20);
        await sleep(100);
        const r = await page.evaluate(n0 => { const F = app.store.project.sims[0]; const k = F.keys.find(x => x.frame === 20); return { frames: __T.frames(F), moved: k && JSON.stringify(k.pose) === window.__k10, toasts: __T.newToasts(n0) }; }, n0);
        C('3 a key dropped onto another replaces it, and the toast says so', r.frames === '0,20' && r.moved && r.toasts.some(t => /replaced/.test(t)), r);
        await key(page, 'Control+z');
        const u = await page.evaluate(() => { const F = app.store.project.sims[0]; return { frames: __T.frames(F), k20: JSON.stringify(F.keys.find(k => k.frame === 20)?.pose) === window.__k20 }; });
        C('3 ... undo brings the replaced key back', u.frames === '0,10,20' && u.k20, u);
      }
    }

    // ============================================================ 4. reverse twice
    if (want(4)) {
      await pe(page, () => {
        const { F, M } = __T.fresh();
        __T.keyAt(F, 10, 15, 'easeIn'); __T.keyAt(F, 25, -20, 'custom'); __T.keyAt(F, 40, 35, 'linear'); __T.keyAt(M, 18, 25, 'easeOut');
        F.keys.find(k => k.frame === 25).curve = [0.2, 0.1, 0.3, 1];
        F.keys[0].ease = 'smooth';
        app.refreshAll();
        const before = JSON.stringify(app.store.project.sims.map(s => s.keys));
        app.timeline.selectAll();
        app.reverseSelectedKeys();
        const once = app.store.project.sims.map(__T.frames);
        const c1 = app.store.project.sims[0].keys.find(k => k.ease === 'custom');
        app.timeline.selectAll();
        app.reverseSelectedKeys();
        const after = JSON.stringify(app.store.project.sims.map(s => s.keys));
        return { checks: [['4 reverse twice: keys, eases and custom curves identical to the start', before === after, { once, customOnce: c1 && c1.curve }],
          ['4 ... and once really plays it backwards (frames mirrored in the selection)', once[0] === '0,15,30,40', once]] };
      });
    }

    // ============================================================ 5. copy 4 keys, another animation, paste
    if (want(5)) {
      await pe(page, () => {
        const { F } = __T.fresh();
        __T.keyAt(F, 10, 20); __T.keyAt(F, 20, -15); __T.keyAt(F, 30, 30);
        app.refreshAll();
        app.selectSim(F.id);
        app.timeline.selectAll([F.id]);
        app.copySelectedKeys();
        const clip = app.keyClip, uidA = app.store.project.uid;
        // another animation: its sims stand somewhere else and face another way
        const { F: F2 } = __T.fresh();
        app.selectSim(F2.id);
        app.turnSim(F2.id, 50);
        app.transformSim(F2.id, { offset: new __T.THREE.Vector3(0.7, 0, -0.4) });
        app.refreshAll();
        const at = 20, p = app.store.project, rig = app.assets.rig;
        app.setFrame(at);
        const before = __T.A.evaluate(F2.keys, at, p.length, p.loop, p.autoCurve);
        const p0 = __T.KO.hipsOf(before, rig), y0 = __T.KO.facingOf(before, rig);
        const rep = app.pasteKeys();
        const pasted = F2.keys.filter(k => k.frame >= at).map(k => k.frame);
        const first = F2.keys.find(k => k.frame === at);
        const p1 = __T.KO.hipsOf(first.pose, rig), y1 = __T.KO.facingOf(first.pose, rig);
        return { checks: [
          ['5 copy 4 keys, paste into another animation: 4 keys at the playhead', p.uid !== uidA && clip.count === 4 && rep.pasted === 4 && pasted.join() === '20,30,40,50', { pasted, count: clip.count }],
          ['5 ... the pelvis at the first pasted key is within 1 mm of where the sim stood', p0.distanceTo(p1) * 1000 < 1, { mm: +(p0.distanceTo(p1) * 1000).toFixed(4) }],
          ['5 ... and it faces the same way', Math.abs(((y1 - y0 + Math.PI * 3) % (Math.PI * 2)) - Math.PI) < 1e-6, { deg: +((y1 - y0) * 180 / Math.PI).toFixed(6) }],
        ] };
      });
    }

    // ============================================================ 6. paste mirrored = mirrorPoseData; twice = original
    if (want(6)) {
      await pe(page, () => {
        const { F } = __T.fresh('solo');
        const v = app.simViews.get(F.id);
        v.resetPose();                    // at the origin, facing +Z: the pasted key needs no moving
        F.keys = [{ frame: 0, ease: 'auto', pose: app._bodyPose(v) }];
        __T.keyAt(F, 0, 25);
        const k0 = F.keys[0];
        k0.pose.rot.b__R_Hand__ = __T.turn(k0.pose.rot.b__R_Hand__, [0, 1, 1], 40);
        k0.pose.rot.b__Head__ = __T.turn(k0.pose.rot.b__Head__, [0, 1, 0], 30);
        app.refreshAll();
        app.selectSim(F.id);
        app.timeline.selectOnly([__T.KO.kid(F.id, 0)]);
        app.copySelectedKeys();
        app.setFrame(30);
        app.pasteKeys({ flipped: true });
        const rig = app.assets.rig;
        const want = __T.KO.mirrorPoseData(k0.pose, rig), got = F.keys.find(k => k.frame === 30).pose;
        const d = __T.poseDiff(want, got);
        // mirror twice, on every ready pose's sims
        let worstQ = 0, worstM = 0;
        for (const pr of (app.posePresets || []).slice(0, 40)) for (const ps of pr.sims) {
          const back = __T.KO.mirrorPoseData(__T.KO.mirrorPoseData(ps.pose, rig), rig);
          for (const [n, q] of Object.entries(ps.pose.rot || {})) { const b = back.rot[n]; if (!b) { worstQ = 9; continue; } worstQ = Math.max(worstQ, __T.qang(q, b)); }
          for (const [n, t] of Object.entries(ps.pose.pos || {})) { const b = back.pos[n]; if (!b) { worstM = 9; continue; } for (let i = 0; i < 3; i++) worstM = Math.max(worstM, Math.abs(t[i] - b[i])); }
        }
        return { checks: [['6 paste mirrored of one key = mirrorPoseData (every bone)', d.deg < 1e-4 && d.mm < 1e-3, d],
          ['6 mirrorPoseData twice = the original (turns 1e-4 rad, places 1e-6 m)', worstQ < 1e-4 && worstM < 1e-6, { worstRad: worstQ, worstM, poses: Math.min(40, (app.posePresets || []).length) }]] };
      });
    }

    // ============================================================ 7. mirror the whole animation twice
    if (want(7)) {
      await pe(page, () => {
        const pr = (app.posePresets || []).find(x => x.group === 'couple');
        const { F, M } = __T.fresh();
        app.setFrame(0);
        if (pr) app.applyPosePreset(pr, { quiet: true });
        __T.keyAt(F, 30, 20); __T.keyAt(M, 45, -25);
        F.pins = { 'L hand': [0.1, 0.9, 0.2], 'R foot': { at: [-0.2, 0.05, 0.1], from: 20, to: 45, fade: 3 } };
        F.layers = [{ id: 'm1', type: 'thrust', on: true, weight: 1, phase: 0.1, params: { strokes: 4, distance: 5, sharp: 0.6, tilt: 8, follow: 0.6, axis: 'forward', reverse: false } },
          { id: 'm2', type: 'sway', on: true, weight: 1, phase: 0.3, params: { strokes: 1, distance: 3, sharp: 0, tilt: 0, follow: 0.6, axis: 'side', reverse: false } }];
        M.layers = [{ id: 'm3', type: 'stroke', on: true, weight: 1, phase: 0, params: { strokes: 3, distance: 8, sharp: 0.2, limb: 'R hand', axis: 'penis', reverse: false } }];
        app.refreshAll();
        const p0 = JSON.parse(JSON.stringify(app.store.project));
        app.mirrorAnimation();
        const once = JSON.parse(JSON.stringify(app.store.project));
        app.mirrorAnimation();
        const p2 = app.store.project;
        // compare numbers (quaternions either sign) within 1e-4
        let worst = 0, shape = true;
        const cmp = (a, b, pth) => {
          if (typeof a === 'number' && typeof b === 'number') { worst = Math.max(worst, Math.abs(a - b)); return; }
          if (Array.isArray(a) && a.length === 4 && Array.isArray(b) && a.every(x => typeof x === 'number') && /rot/.test(pth)) { worst = Math.max(worst, __T.qang(a, b)); return; }
          if (a && b && typeof a === 'object') { const ka = Object.keys(a).sort(), kb = Object.keys(b).sort(); if (ka.join() !== kb.join()) { shape = false; return; } for (const k of ka) cmp(a[k], b[k], pth + '.' + k); return; }
          if (a !== b) shape = false;
        };
        cmp(p0.sims.map(s => ({ keys: s.keys, pins: s.pins, layers: s.layers })), p2.sims.map(s => ({ keys: s.keys, pins: s.pins, layers: s.layers })), '');
        const flippedPins = once.sims[0].pins && once.sims[0].pins['R hand'] && once.sims[0].pins['L foot'];
        return { checks: [['7 mirror the whole animation twice: every key (turns 1e-4 rad), pin and motion setting as before (1e-4)', shape && worst < 1e-4, { worst, shape }],
          ['7 ... one mirror makes a new animation (new uid, "(mirrored)"), pins swap sides', once.uid !== p0.uid && /\(mirrored\)$/.test(once.name) && !!flippedPins && once.sims[0].layers[1].phase !== p0.sims[0].layers[1].phase && once.sims[1].layers[0].params.limb === 'L hand',
            { uid: [p0.uid, once.uid], name: once.name }],
          ['7 ... mirroring back gives the old name', p2.name === p0.name, p2.name]] };
      });
    }

    // ============================================================ 9 + 10. the clamped Auto curve
    if (want(9) || want(10)) {
      await pe(page, () => {
        const A = __T.A, checks = [];
        const pose = (deg, x = 0) => ({ rot: { b__Spine1__: __T.turn([0, 0, 0, 1], [0, 0, 1], deg) }, pos: { b__Pelvis__: [1 + x, 0, 0] } });
        const angle = p => 2 * Math.atan2(p.rot.b__Spine1__[2], p.rot.b__Spine1__[3]) * 180 / Math.PI;
        // A, B, B, C: between the two B keys it holds exactly B
        const keys = [{ frame: 0, ease: 'auto', pose: pose(0) }, { frame: 10, ease: 'auto', pose: pose(40) }, { frame: 20, ease: 'auto', pose: pose(40) }, { frame: 30, ease: 'auto', pose: pose(90) }];
        let worst = 0;
        for (let f = 10; f <= 20; f += 0.5) { const e = A.evaluate(keys, f, 40, false, 'clamped'); worst = Math.max(worst, __T.qang(e.rot.b__Spine1__, keys[1].pose.rot.b__Spine1__)); }
        const legacyDrift = Math.max(...[12, 15, 18].map(f => __T.qang(A.evaluate(keys, f, 40, false, 'legacy').rot.b__Spine1__, keys[1].pose.rot.b__Spine1__)));
        checks.push(['9 clamped Auto: keys A, B, B, C hold B exactly between the two B keys (1e-6 rad)', worst < 1e-6, { worstRad: worst, legacyDriftRad: +legacyDrift.toFixed(5) }]);
        // a monotone run with uneven spacing never passes outside its neighbouring keys
        const run = [[0, 0, 0], [5, 10, 0.01], [20, 40, 0.05], [22, 45, 0.06], [40, 90, 0.2]].map(([f, d, x]) => ({ frame: f, ease: 'auto', pose: pose(d, x) }));
        let out = 0, outPos = 0;
        for (let i = 0; i + 1 < run.length; i++) {
          const a0 = angle(run[i].pose), a1 = angle(run[i + 1].pose), x0 = run[i].pose.pos.b__Pelvis__[0], x1 = run[i + 1].pose.pos.b__Pelvis__[0];
          for (let f = run[i].frame; f <= run[i + 1].frame; f += 0.25) {
            const e = A.evaluate(run, f, 41, false, 'clamped'), a = angle(e), x = e.pos.b__Pelvis__[0];
            out = Math.max(out, Math.min(a0, a1) - a, a - Math.max(a0, a1));
            outPos = Math.max(outPos, Math.min(x0, x1) - x, x - Math.max(x0, x1));
          }
        }
        checks.push(['9 ... on a monotone run no channel passes outside its neighbouring keys', out <= 1e-9 && outPos <= 1e-12, { degOut: out, posOut: outPos }]);
        // 10: across the loop, the step L-1 -> 0 is like its neighbours
        const L = 60, loopKeys = [[0, 0], [15, 30], [30, 0], [45, -30]].map(([f, d]) => ({ frame: f, ease: 'auto', pose: pose(d) }));
        const ang = f => angle(A.evaluate(loopKeys, f, L, true, 'clamped'));
        const step = (a, b) => Math.abs(ang(b) - ang(a));
        const seam = step(L - 1, 0), before = step(L - 2, L - 1), after = step(0, 1);
        const ratio = [seam / before, seam / after];
        checks.push(['10 clamped Auto across the loop: the step from the last frame to frame 0 is like its neighbours (0.8-1.25)', ratio.every(r => r >= 0.8 && r <= 1.25), { seam: +seam.toFixed(4), before: +before.toFixed(4), after: +after.toFixed(4), ratio: ratio.map(r => +r.toFixed(3)) }]);
        // uneven spacing across the seam too
        const L2 = 50, k2 = [[3, 5], [20, 35], [31, 10], [44, -20]].map(([f, d]) => ({ frame: f, ease: 'auto', pose: pose(d) }));
        const ang2 = f => angle(A.evaluate(k2, f, L2, true, 'clamped'));
        const s2 = [ang2(L2 - 2), ang2(L2 - 1), ang2(0), ang2(1)];
        const r2 = [Math.abs(s2[2] - s2[1]) / Math.abs(s2[1] - s2[0]), Math.abs(s2[2] - s2[1]) / Math.abs(s2[3] - s2[2])];
        checks.push(['10 ... also with keys unevenly spaced round the loop point', r2.every(r => r >= 0.8 && r <= 1.25), r2.map(r => +r.toFixed(3))]);
        // new projects use it; loaded old ones keep the old curve
        const p = app.store.project;
        const store = new (app.store.constructor)();
        store.load({ name: 'old', sims: [], length: 90 });
        checks.push(['9 new animations use the clamped curve; an old file keeps the legacy one', p.autoCurve === 'clamped' && store.project.autoCurve === 'legacy', [p.autoCurve, store.project.autoCurve]]);
        return { checks };
      });
    }

    // ============================================================ 11. offsetCycle
    if (want(11)) {
      await pe(page, async () => {
        const A = __T.A, KO = __T.KO, checks = [];
        const { F, M } = __T.fresh();
        const pr = (app.posePresets || []).find(x => x.group === 'couple');
        if (pr) app.applyPosePreset(pr, { quiet: true });
        __T.keyAt(F, 20, 25, 'easeIn'); __T.keyAt(F, 50, -20, 'auto'); __T.keyAt(F, 70, 10, 'custom'); F.keys.find(k => k.frame === 70).curve = [0.3, 0.2, 0.6, 1.2];
        __T.keyAt(M, 33, 15, 'auto'); __T.keyAt(M, 80, -10, 'smooth');
        app.addLayer(F.id, 'thrust'); app.setPlaying(false);
        app.refreshAll();
        const p = app.store.project, L = p.length, n = 17;
        const old = JSON.parse(JSON.stringify(p));
        const neu = JSON.parse(JSON.stringify(p));
        KO.offsetCycle(neu, null, n);
        let worst = 0;
        for (const curve of ['legacy', 'clamped']) for (let si = 0; si < old.sims.length; si++) for (let f = 0; f < L; f++) {
          const a = A.evaluate(neu.sims[si].keys, f, L, true, curve), b = A.evaluate(old.sims[si].keys, ((f - n) % L + L) % L, L, true, curve);
          const d = __T.poseDiff(a, b);
          worst = Math.max(worst, d.deg * Math.PI / 180, d.mm / 1000);
        }
        checks.push(['11 offsetCycle: evaluate(new, f) == evaluate(old, f - n) for every f, both curves (1e-6)', worst < 1e-6, { worst }]);
        // motions: the whole pipeline (keys + motions) at f vs f - n
        const mk = project => { const store = new (app.store.constructor)(); store.project = project; const views = new Map(); for (const s of project.sims) views.set(s.id, app.simViews.get(s.id)); return { store, simViews: views }; };
        const { Pipeline } = await import('/js/pipeline.js');
        const bodyBones = (await import('/js/bones.js')).POSABLE;
        const snap = () => app.store.project.sims.map(s => { const v = app.simViews.get(s.id); return bodyBones.filter(b => v.bone(b)).map(b => v.bone(b).quaternion.toArray()); });
        const plOld = new Pipeline(mk(old)), plNew = new Pipeline(mk(neu));
        let wl = 0;
        for (const f of [0, 5, 13, 29, 44, 61, 77, 89]) {
          plNew.apply(f, { physics: false, overrides: false }); const a = snap();
          plOld.apply(((f - n) % L + L) % L, { physics: false, overrides: false }); const b = snap();
          a.forEach((s, i) => s.forEach((q, j) => { wl = Math.max(wl, __T.qang(q, b[i][j])); }));
        }
        app.applyPoses();
        checks.push(['11 ... with the motions too (the whole body, 8 frames, 1e-6 rad)', wl < 1e-6, { worstRad: wl }]);
        return { checks };
      });
    }

    // ============================================================ 12. custom curve = CSS ease-in-out
    if (want(12)) {
      await pe(page, () => {
        const f = __T.A.bezierEase([0.42, 0, 0.58, 1]);
        // reference: CSS cubic-bezier(.42,0,.58,1) solved by bisection (60 steps)
        const ref = t => { const bx = u => 3 * (1 - u) * (1 - u) * u * 0.42 + 3 * (1 - u) * u * u * 0.58 + u * u * u, by = u => 3 * (1 - u) * u * u + u * u * u; let lo = 0, hi = 1; for (let i = 0; i < 60; i++) { const m = (lo + hi) / 2; if (bx(m) < t) lo = m; else hi = m; } return by((lo + hi) / 2); };
        let worst = 0;
        const vals = [];
        for (let i = 1; i <= 9; i++) { const t = i / 10; worst = Math.max(worst, Math.abs(f(t) - ref(t))); vals.push(+f(t).toFixed(4)); }
        return { checks: [['12 custom curve [0.42,0,0.58,1] matches CSS ease-in-out at t=.1...9 (1e-3)', worst < 1e-3, { worst, vals }]] };
      });
    }

    // ============================================================ 13. simplify an import with a key every 3 frames
    if (want(13)) {
      const r = await pe(page, async () => {
        const checks = [];
        const lib = await __T.A;
        void lib;
        const imp = await import('/js/dialogs/import.js');
        const api = (await import('/js/api.js')).api;
        __T.fresh();
        const list = await api.library({});
        const items = (list.items || list || []).filter(x => x && x.id !== undefined);
        const pick = items.find(x => (x.actors || x.sims || 2) >= 2) || items[0];
        const anim = await api.animation(pick.id, 1);
        app.library.startPreview(anim);
        const pv = app.library.preview;
        const len = Math.min(240, pv.length - 1);
        imp.importKeys(app, pv, 3, 0, len, true);
        const p = app.store.project;
        const before = p.sims.map(s => s.keys.filter(k => !k.faceOnly).length);
        const truth = p.sims.map(s => { const out = []; for (let f = 0; f < p.length; f++) out.push(__T.A.evaluate(s.keys, f, p.length, p.loop, p.autoCurve)); return out; });
        app.timeline.clearSel();
        const res = [];
        for (const s of p.sims) { app.selectSim(s.id); const t0 = performance.now(); const r = app.simplifySelection(1.5); res.push({ ...r, ms: Math.round(performance.now() - t0) }); }
        const after = p.sims.map(s => s.keys.filter(k => !k.faceOnly).length);
        let worst = 0;
        p.sims.forEach((s, i) => { for (let f = 0; f < p.length; f++) worst = Math.max(worst, __T.poseDiff(__T.A.evaluate(s.keys, f, p.length, p.loop, p.autoCurve), truth[i][f]).deg); });
        checks.push(['13 Simplify on an import with a key every 3 frames: fewer keys', after.every((a, i) => a < before[i]), { before, after, ms: res.map(r => r.ms), anim: pick.name }]);
        checks.push(['13 ... the largest angle over all frames stays within the tolerance (1.5 deg)', worst <= 1.5 + 1e-6, { worstDeg: +worst.toFixed(4), reported: res.map(r => +r.maxDeg.toFixed(3)) }]);
        const baked = app.bake();
        let nan = 0;
        for (const a of baked.actors) for (const tr of Object.values(a.tracks)) for (const arr of Object.values(tr)) for (const row of arr) for (const x of row) if (!Number.isFinite(x)) nan++;
        checks.push(['13 ... the bake has no NaN', nan === 0, { nan }]);
        app.library.stopPreview();
        return { checks, data: { baked } };
      });
      // the offline export of that animation (built in %TEMP%, never in Documents)
      if (r && r.baked) {
        const jf = path.join(os.tmpdir(), 'wa_r21_export_job.json');
        fs.writeFileSync(jf, JSON.stringify({ kind: 'export', body: r.baked }));
        const out = cp.spawnSync('python', [path.join(H.ROOT, 'tools', 'checks', 'lib', 'offline_pkg.py'), jf], { encoding: 'utf8', maxBuffer: 64 << 20 });
        let res = null;
        try { res = JSON.parse((out.stdout || '').trim().split('\n').pop()); } catch { res = { error: (out.stderr || '').slice(-400) }; }
        C('13 ... and an offline export of it builds (package in %TEMP%)', res && !res.error && res.bytes > 1000 && String(res.path).toLowerCase().startsWith(os.tmpdir().toLowerCase()), res && { bytes: res.bytes, clips: res.clips, error: res.error });
      }
    }

    // ============================================================ 14. smooth 50%
    if (want(14)) {
      await pe(page, () => {
        const { F } = __T.fresh('solo');
        const p = app.store.project, L = 60;
        p.length = L; p.loop = true;
        const base = F.keys[0].pose;
        let seed = 3; const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280) - 0.5;
        F.keys = [];
        for (let f = 0; f < L; f++) {
          const pose = JSON.parse(JSON.stringify(base));
          const wave = 25 * Math.sin((2 * Math.PI * f) / L);
          pose.rot.b__L_Hand__ = __T.turn(pose.rot.b__L_Hand__, [1, 0, 0], wave + 4 * rnd());
          pose.rot.b__Head__ = __T.turn(pose.rot.b__Head__, [0, 1, 0], wave * 0.5 + 3 * rnd());
          F.keys.push({ frame: f, ease: 'auto', pose });
        }
        app.refreshAll();
        const series = n => { const out = []; for (let f = 0; f < L; f++) out.push(__T.A.evaluate(F.keys, f, L, true, p.autoCurve).rot[n]); return out; };
        const jitter = n => { const q = series(n); const sp = []; for (let f = 0; f < L; f++) sp.push(__T.qang(q[f], q[(f + 1) % L])); let s = 0; for (let f = 0; f < L; f++) s += Math.abs(sp[(f + 1) % L] - sp[f]); return s / L * 180 / Math.PI; };
        const seam = n => { const q = series(n); const st = f => __T.qang(q[(f + L) % L], q[(f + 1) % L]); return st(L - 1) / Math.max(st(L - 2), st(0), 1e-9); };
        const j0 = [jitter('b__L_Hand__'), jitter('b__Head__')];
        app.selectSim(F.id); app.timeline.clearSel();
        app.smoothSelection(0.5);
        const j1 = [jitter('b__L_Hand__'), jitter('b__Head__')];
        const sr = [seam('b__L_Hand__'), seam('b__Head__')];
        return { checks: [['14 Smooth 50%: the shake (mean change of speed per frame) drops', j1.every((x, i) => x < j0[i] * 0.75), { before: j0.map(x => +x.toFixed(3)), after: j1.map(x => +x.toFixed(3)) }],
          ['14 ... and the loop point stays smooth (its step no bigger than 1.25x its neighbours)', sr.every(r => r <= 1.25), sr.map(r => +r.toFixed(3))]] };
      });
    }

    // ============================================================ 15. loop check finds the old "copy to the end"
    if (want(15)) {
      await pe(page, () => {
        const { F, M } = __T.fresh();
        const p = app.store.project, L = p.length;
        for (const s of [F, M]) { __T.keyAt(s, 30, 25); __T.keyAt(s, 60, -15); s.keys.push({ ...JSON.parse(JSON.stringify(s.keys[0])), frame: L - 1 }); __T.A.sortKeys(s.keys); }
        app.refreshAll();
        const st = app.loopStatus().map(r => r.kind);
        const same = () => { const b = app.bake(); return b.actors.map(a => { const t = a.tracks.b__Spine1__.r; return __T.qang(t[t.length - 1], t[0]); }); };
        const before = same();
        app.fixLoops();
        const after = same(), st2 = app.loopStatus().map(r => r.kind);
        const frames = [F, M].map(__T.frames);
        return { checks: [['15 loop check: a last key copying the first at the last frame is a "pause"', st.every(k => k === 'pause'), st],
          ['15 ... Fix it takes that key off, and the loop is ok then', frames.every(f => !f.endsWith(',' + (L - 1))) && st2.every(k => k === 'ok'), { frames, st2 }],
          ['15 ... the bake has no two identical frames at the loop point any more', before.every(d => d < 1e-6) && after.every(d => d > 1e-4), { before, after }]] };
      });
    }

    // ============================================================ 18. partial paste "Hands"
    if (want(18)) {
      await pe(page, async () => {
        const { F, M } = __T.fresh();
        const pr = (app.posePresets || []).find(x => x.group === 'couple');
        if (pr) app.applyPosePreset(pr, { quiet: true });
        const k = M.keys[0];
        k.pose.rot.b__L_Index1__ = __T.turn(k.pose.rot.b__L_Index1__ || __T.A.restOf('b__L_Index1__').r, [0, 0, 1], 50);
        k.pose.rot.b__R_Hand__ = __T.turn(k.pose.rot.b__R_Hand__, [1, 0, 0], 35);
        app.refreshAll();
        app.selectSim(M.id); app.setFrame(0); app.copyPose(M.id);
        app.selectSim(F.id);
        const before = JSON.parse(JSON.stringify(F.keys.find(x => x.frame === 0).pose));
        app.pastePose(F.id, { mask: 'hands' });
        const after = F.keys.find(x => x.frame === 0).pose;
        const hands = new Set(__T.KO.BODY_PARTS.hands);
        const changed = [];
        for (const n of new Set([...Object.keys(before.rot), ...Object.keys(after.rot)])) { const r = __T.A.restOf(n); if (__T.qang(before.rot[n] || r.r, after.rot[n] || r.r) > 1e-6) changed.push(n); }
        const hipsSame = ['b__Pelvis__', 'b__Spine0__'].every(n => JSON.stringify(before.pos[n]) === JSON.stringify(after.pos[n]));
        return { checks: [['18 partial paste "Hands": only hand and finger bones change', changed.length > 0 && changed.every(n => hands.has(n)), { changed }],
          ['18 ... the hips stay in their place', hipsSame]] };
      });
    }

    // ============================================================ 19. drag a pose tile to 50%
    if (want(19)) {
      await page.evaluate(() => { __T.fresh(); app._poseMode = 'solo'; app.showStep('pose'); app.selectSim(app.store.project.sims[0].id); app.setFrame(0); });
      await sleep(400);
      const t = await page.evaluate(() => {
        const tiles = [...document.querySelectorAll('#panel-body .pose-tiles .tile')];
        const tile = tiles[1] || tiles[0];
        tile.scrollIntoView({ block: 'center' });
        const r = tile.getBoundingClientRect();
        const pr = app.posePresets.filter(x => !x.mine && x.group === 'solo')[tiles.indexOf(tile)];
        const sim = app.store.sim();
        const tg = app._presetTarget(sim, pr.sims[0], 0, {});
        window.__blend = { before: tg.base, target: tg.pose, id: pr.id };
        return { x: r.left + 30, y: r.top + r.height / 2, label: pr.label };
      });
      await page.mouse.move(t.x, t.y); await page.mouse.down();
      for (let k = 1; k <= 8; k++) await page.mouse.move(t.x + 10 * k, t.y);
      if (SHOTS) await H.shot(page, path.join(OUT, 'shot_pose_blend_1366.png'));
      await page.mouse.up();
      await sleep(250);
      await pe(page, () => {
        const sim = app.store.sim(), key = sim.keys.find(k => k.frame === 0);
        const want = __T.A.blendPoses(window.__blend.before, window.__blend.target, 0.5);
        const d = __T.poseDiff(want, key.pose);
        const toFull = __T.poseDiff(window.__blend.target, key.pose), toBefore = __T.poseDiff(window.__blend.before, key.pose);
        return { checks: [['19 a pose tile dragged 80 px sideways blends it in at 50% (= blendPoses(before, pose, .5), 1e-6)', d.deg * Math.PI / 180 < 1e-6 && d.mm < 1e-3, { d, toFull, toBefore, undo: app.store.history(3).map(e => e.label) }]] };
      });
    }

    // ============================================================ 20. references: a PNG and an MP4, save, reopen
    if (want(20)) {
      const mp4 = path.join(os.tmpdir(), 'wa_r21_ref.mp4');
      if (!fs.existsSync(mp4)) cp.spawnSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=duration=4:size=320x240:rate=30', '-pix_fmt', 'yuv420p', '-c:v', 'libx264', '-movflags', '+faststart', mp4]);
      const b64 = fs.existsSync(mp4) ? fs.readFileSync(mp4).toString('base64') : '';
      C('20 a test MP4 made locally (ffmpeg testsrc, nothing downloaded)', !!b64, { bytes: b64.length * 0.75 });
      // a browser whose requests go straight to our test server (its saves and reference files are in %TEMP%): the
      // harness proxy can't forward a file's bytes
      const b2 = await H.open(PORT, { w: 1366, h: 768, intercept: false });
      const page2 = b2.page;
      try {
      await helpers(page2);
      await page2.evaluate(() => { document.getElementById('home').classList.add('hidden'); __T.fresh(); app.showStep('scene'); });
      await pe(page2, async b64 => {
        const checks = [];
        // a PNG drawn here, and the MP4
        const c = document.createElement('canvas'); c.width = 320; c.height = 200;
        const g = c.getContext('2d'); g.fillStyle = '#3a8'; g.fillRect(0, 0, 320, 200); g.fillStyle = '#fff'; g.font = '40px sans-serif'; g.fillText('REF', 110, 115);
        const png = await new Promise(r => c.toBlob(r, 'image/png'));
        const bin = Uint8Array.from(atob(b64), ch => ch.charCodeAt(0));
        const files = [new File([png], 'pose photo.png', { type: 'image/png' }), new File([bin], 'reference.mp4', { type: 'video/mp4' })];
        const dt = new DataTransfer(); for (const f of files) dt.items.add(f);
        const wrap = document.getElementById('viewport-wrap');
        wrap.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
        const zone = !document.getElementById('drop-zone').classList.contains('hidden');
        wrap.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
        const t0 = Date.now();
        while ((app.store.project.refs || []).length < 2 && Date.now() - t0 < 15000) await new Promise(r => setTimeout(r, 100));
        const refs = app.store.project.refs;
        checks.push(['20 dropping a PNG and an MP4 on the view adds two references (the drop zone shows while dragging)', refs.length === 2 && zone && refs[0].kind === 'image' && refs[1].kind === 'video', { n: refs.length, zone, kinds: refs.map(r => r.kind), files: refs.map(r => r.file) }]);
        // the video as a board in the scene, a start offset and a speed
        const vid = refs[1];
        app.store.checkpoint('test');
        app.refs.update(vid.id, { mode: 'board', board: app.refs._defaultBoard(vid, 'front'), offset: 0.5, speed: 0.5 });
        app.store.project.name = 'R21 reference test ' + Date.now().toString(36);
        const ok = await app.save();
        const name = app.store.project.name;
        // open something else, then the saved one again
        __T.fresh();
        await app.loadProject(name);
        const t1 = Date.now();
        const ready = () => [...app.refs.items.values()].filter(it => it.ready).length;
        while (ready() < 2 && Date.now() - t1 < 15000) await new Promise(r => setTimeout(r, 100));
        const back = app.store.project.refs || [];
        checks.push(['20 ... save and reopen: both come back and load', ok && back.length === 2 && ready() === 2, { saved: ok, n: back.length, ready: ready() }]);
        const it = [...app.refs.items.values()].find(x => x.ref.kind === 'video');
        const p = app.store.project, L = p.length, fps = p.fps;
        const times = [];
        for (const f of [0, Math.round(L / 2), L - 1]) {
          app.setFrame(f);
          await new Promise(r => setTimeout(r, 150));
          const want = (0.5 + (f / fps) * 0.5) % (it.media.duration || 4);
          times.push({ f, got: +it.media.currentTime.toFixed(4), want: +want.toFixed(4), ok: Math.abs(it.media.currentTime - want) <= 1 / fps + 1e-3 });
        }
        checks.push(['20 ... at frames 0, L/2 and L-1 the video shows offset + f/fps x speed (1 frame)', times.every(t => t.ok), times]);
        checks.push(['20 ... the video stands in the scene as a board', !!(it.mesh && it.mesh.visible && it.mesh.parent), { board: !!it.mesh }]);
        return { checks };
      }, b64);
      if (SHOTS) {
        await page2.evaluate(() => { const r = app.store.project.refs[1]; if (r) app.refs.select(r.id); app.setFrame(20); app.frameSims({ fromFront: true }); });
        await sleep(1200);
        await H.shot(page2, path.join(OUT, 'shot_reference_board_1366.png'));
      }
      // leave no unfinished-work copy behind for the next test on this server
      await page2.evaluate(() => { app.store.setDirty(false); app._clearRecovery(); }).catch(() => {});
      await sleep(300);
      const e2 = b2.logs.filter(l => l.type === 'pageerror');
      C('20 ... no page errors in that browser', !e2.length, e2.map(e => e.text).slice(0, 3));
      } finally { await b2.browser.close(); }
    }

    // ============================================================ 21. undo history
    if (want(21)) {
      await page.evaluate(() => { __T.fresh(); app.showStep('pose'); app.store.undo.length = 0; app.store.redo.length = 0; });
      const r = await pe(page, () => {
        const { F } = { F: app.store.project.sims[0] };
        app.selectSim(F.id);
        window.__before = JSON.stringify(app.store.project);
        app.setFrame(20); app.keyPose(F.id);
        app.mirrorPose(F.id);
        app.setFrame(40); app.insertInBetween([F.id]);
        const hist = app.store.history(3).map(e => e.label);
        return { checks: [['21 three labelled actions are listed newest first', hist.join(' | ') === 'In-between key | Mirror pose | Key pose', hist]], data: hist };
      });
      void r;
      const b = await page.evaluate(() => { const r = document.getElementById('btn-undo').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
      await page.mouse.click(b.x, b.y, { button: 'right' });
      await sleep(200);
      const items = await page.evaluate(() => [...document.querySelectorAll('.ctx-menu button')].map(x => x.textContent));
      if (SHOTS) await H.shot(page, path.join(OUT, 'shot_undo_history_1366.png'));
      await page.evaluate(() => { window.__emits = 0; app.store.on(w => { if (w === 'project') window.__emits++; }); [...document.querySelectorAll('.ctx-menu button')][2].click(); });
      await sleep(200);
      const back = await page.evaluate(() => ({ same: JSON.stringify(app.store.project) === window.__before, emits: window.__emits }));
      C('21 right-click Undo lists them; clicking the oldest goes back before all three in one step', items.length >= 3 && /In-between key/.test(items[0]) && /Key pose/.test(items[2]) && back.same && back.emits === 1, { items, back });
    }

    // ============================================================ 22. the Curves view at 1000 frames
    if (want(22)) {
      await pe(page, () => {
        const { F } = __T.fresh('solo');
        const p = app.store.project;
        p.length = 1000;
        const base = F.keys[0].pose;
        F.keys = [];
        for (let f = 0; f < 1000; f += 3) { const pose = JSON.parse(JSON.stringify(base)); pose.rot.b__L_UpperArm__ = __T.turn(pose.rot.b__L_UpperArm__, [1, 0.3, 0], 40 * Math.sin(f / 20)); F.keys.push({ frame: f, ease: 'auto', pose }); }
        app.refreshAll(); app.timeline.fit();
        app.selectSim(F.id);
        app.store.selected.bone = 'b__L_UpperArm__';
        app.setTimelineView('curves', { quiet: true });
        const cv = app.curves;
        const builds = [], draws = [];
        for (let i = 0; i < 7; i++) { cv.invalidate(); const t0 = performance.now(); cv._build(); builds.push(performance.now() - t0); }
        for (let i = 0; i < 9; i++) { const t0 = performance.now(); cv.draw(true); draws.push(performance.now() - t0); }
        const med = a => a.sort((x, y) => x - y)[a.length >> 1];
        return { checks: [['22 Curves view at 1000 frames: rebuild under 20 ms (median)', med(builds) < 20, { buildMs: +med(builds).toFixed(2) }],
          ['22 ... redraw under 8 ms (median)', med(draws) < 8, { drawMs: +med(draws).toFixed(2) }]] };
      });
      if (SHOTS) {
        await page.evaluate(() => { app.curves.frameAll(); app.timeline.fit(); app.setFrame(120); });
        await sleep(400);
        await H.shot(page, path.join(OUT, 'shot_curves_1000_1366.png'));
      }
      await page.evaluate(() => app.setTimelineView('keys', { quiet: true }));
    }

    // ============================================================ 24. screenshots: Curves with Bend/Twist/Tilt, the timing editor
    if (want(24) && SHOTS) {
      await page.evaluate(() => {
        const { F, M } = __T.fresh();
        const pr = (app.posePresets || []).find(x => x.group === 'couple');
        if (pr) app.applyPosePreset(pr, { quiet: true });
        __T.keyAt(F, 20, 30, 'easeOut'); __T.keyAt(F, 45, -25, 'auto'); __T.keyAt(F, 70, 15, 'custom'); F.keys.find(k => k.frame === 70).curve = [0.2, 1.3, 0.5, 1];
        void M;
        app.refreshAll();
        app.selectSim(F.id);
        app.store.selected.bone = 'b__Spine1__';
        app.emitSelection();
        app.setTimelineView('curves', { quiet: true });
        app.setFrame(30);
      });
      await sleep(600);
      await page.evaluate(() => app.curves.frameAll());
      await sleep(200);
      await H.shot(page, path.join(OUT, 'shot_curves_bend_twist_tilt_1366.png'));
      await page.evaluate(() => { const F = app.store.sim(); app.timingEditor(F.id, 70, 520, 180); });
      await sleep(300);
      await H.shot(page, path.join(OUT, 'shot_timing_editor_1366.png'));
      await page.keyboard.press('Escape');
      await page.evaluate(() => app.setTimelineView('keys', { quiet: true }));
    }

    const errs = logs.filter(l => l.type === 'pageerror' || (l.type === 'error' && !/favicon|Failed to load resource/.test(l.text)));
    C('no page errors', !errs.length, errs.map(e => e.text).slice(0, 5));
  } finally {
    await browser.close();
  }
  const ok = L.table(rows, 'R2-1 editing checks (spec_editing 16)');
  fs.writeFileSync(path.join(L.OUT, 'editing_results.json'), JSON.stringify({ when: new Date().toISOString(), rows, results }, null, 1));
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
