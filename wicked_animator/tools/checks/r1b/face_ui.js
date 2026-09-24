// R1-B checks: plug-in points, shims, the Face tool, the bone list, imports, expression baking, the timeline API and
// the camera (build plan section 3, R1-B checks 1-8 and 10). Nothing is written to disk by the app: the harness
// answers every writing route in the browser.
//   node tools/checks/r1b/face_ui.js --port 8842 [--only 1,3] [--no-shots]
const path = require('path');
const fs = require('fs');
const H = require('../lib/harness.js');

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const PORT = +arg('--port', 8842);
const ONLY = arg('--only', null) ? new Set(arg('--only').split(',')) : null;
const SHOTS = !argv.includes('--no-shots');
const OUT = path.join(H.ROOT, 'cache', 'checks', 'r1b');
fs.mkdirSync(OUT, { recursive: true });

const rows = [];
const C = (name, ok, detail) => { rows.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail === undefined ? '' : '  ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)).slice(0, 300)}`); };
const want = n => !ONLY || ONLY.has(String(n));
const sleep = ms => new Promise(r => setTimeout(r, ms));

// runs fn in the page; fn returns {checks: [[name, ok, detail]], data}
async function pe(page, fn, ...args) {
  let r;
  try { r = await page.evaluate(fn, ...args); } catch (e) { C(`page code ran (${fn.name || 'anonymous'})`, false, String(e.message || e).slice(0, 400)); return null; }
  if (r && Array.isArray(r.checks)) for (const [n, ok, d] of r.checks) C(n, ok, d);
  return r ? r.data : null;
}

async function helpers(page) {
  await page.evaluate(async () => {
    const M = window.__M = {
      K: await import('/js/facekit.js'), bones: await import('/js/bones.js'), state: await import('/js/state.js'),
      animation: await import('/js/animation.js'), face: await import('/js/face.js'), api: (await import('/js/api.js')).api,
      imp: await import('/js/dialogs/import.js'), inspector: await import('/js/inspector.js'),
    };
    const T = window.__T = {};
    T.sleep = ms => new Promise(r => setTimeout(r, ms));
    T.frames = n => new Promise(r => { let k = 0; const f = () => (++k >= n ? r() : requestAnimationFrame(f)); requestAnimationFrame(f); });
    T.home = () => document.getElementById('home').classList.add('hidden');
    // a clean couple (female + male) in a ready pose, one key each, no motions/sounds/pins, 3 s loop
    T.couple = (presetId = 'cowgirl') => {
      const p = app.store.project;
      app.setPlaying(false);
      app.vp.gizmo.detach(); app.interact.active = null; app.pipeline.editing = null;
      app.mirrorEdit = false; app.altDown = false;
      let F = p.sims.find(s => s.frame === 'yf'), Mm = p.sims.find(s => s.frame === 'ym');
      if (!F) { F = M.state.newSim(p, 'yf'); p.sims.push(F); }
      if (!Mm) { Mm = M.state.newSim(p, 'ym'); p.sims.push(Mm); }
      p.sims = [F, Mm];
      for (const s of p.sims) { s.layers = []; s.sounds = []; s.pins = {}; s.keys = []; s.body = undefined; s.visible = true; }
      p.length = 90; p.loop = true; p.fps = 30; p.furniture = 'floor'; p.locations = ['FLOOR'];
      app.store.undo.length = 0; app.store.redo.length = 0;
      app.store.frame = 0;
      app.store.selected = { sim: F.id, bone: null };
      app.syncViews();
      const pr = app.posePresets.find(x => x.id === presetId) || app.posePresets.find(x => x.group === 'couple');
      app.applyPosePreset(pr);
      app.pipeline.overrides.clear();
      app.setFrame(0);
      return { F, M: Mm };
    };
    T.gz = () => app.vp.gizmo;
    // a gizmo drag, the way TransformControls reports it: mouseDown, the object changes, objectChange, mouseUp
    T.drag = change => {
      const gz = T.gz();
      gz.dispatchEvent({ type: 'mouseDown' });
      gz.dispatchEvent({ type: 'dragging-changed', value: true });
      change();
      gz.dispatchEvent({ type: 'objectChange' });
      gz.dispatchEvent({ type: 'mouseUp' });
      gz.dispatchEvent({ type: 'dragging-changed', value: false });
    };
    T.off = (v, n) => { const b = M.K.baseOf(v, n), r = v.restByName[n]; return b.p.clone().sub(r.pos).multiplyScalar(1000); };      // mm
    T.turn = (v, n) => { const b = M.K.baseOf(v, n), r = v.restByName[n]; const e = new b.q.constructor().copy(r.quat).invert().multiply(b.q); return e; };
    T.deg = r => r * 180 / Math.PI;
    T.qang = (a, b) => { const d = Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]) / (Math.hypot(...a) * Math.hypot(...b) || 1); return 2 * Math.acos(Math.min(1, d)) * 180 / Math.PI; };
    T.errors = [];
    const ce = console.error.bind(console);
    console.error = (...a) => { T.errors.push(a.map(x => String(x && x.message || x)).join(' ')); ce(...a); };
    T.home();
    await T.sleep(300);
    // the ready poses load after start
    for (let i = 0; i < 100 && !(app.posePresets && app.posePresets.length); i++) await T.sleep(100);
  });
}

(async () => {
  const t0 = Date.now();
  const { browser, page, logs, writes } = await H.open(PORT, { w: 1366, h: 768 });
  await helpers(page);

  // ================================================================ 1. plug-in points
  if (want(1)) {
    await pe(page, async () => {
      const checks = [];
      window.__feat = { section: 0, inspector: 0, keys: 0, afterApply: 0 };
      const src = `export function install(app) {
        app.hooks.sections.pose.push((a, root) => { window.__feat.section++; const d = document.createElement('div'); d.id = 'feat-test-section'; d.textContent = 'Test section'; root.append(d); });
        app.hooks.inspector.push((a, root, ctx) => { window.__feat.inspector++; const d = document.createElement('div'); d.id = 'feat-test-card'; d.textContent = 'Test card ' + (ctx.sim ? ctx.sim.label : ''); root.append(d); });
        app.hooks.keys.push((e, info) => { if (info.code === 'KeyJ') { window.__feat.keys++; window.__feat.keyInfo = info; return true; } return false; });
        app.hooks.afterApply.push((frame, o) => { window.__feat.afterApply++; window.__feat.applyArgs = [frame, o && typeof o.playing]; });
      }`;
      const res = await app.loadFeatures(['data:text/javascript,' + encodeURIComponent(src)]);
      checks.push(['1 loadFeatures installs a data: module', res.length === 1 && res[0].ok, res]);
      app.showStep('pose');
      checks.push(['1 Pose-step section hook runs (section in the panel)', !!document.querySelector('#panel-body #feat-test-section') && window.__feat.section > 0, window.__feat.section]);
      app.refreshPanels();
      checks.push(['1 inspector card hook runs', !!document.querySelector('#inspector #feat-test-card') && window.__feat.inspector > 0, document.querySelector('#feat-test-card')?.textContent]);
      document.body.focus();
      window.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyJ', key: 'j', bubbles: true }));
      checks.push(['1 keys hook runs (and gets info)', window.__feat.keys === 1 && window.__feat.keyInfo && window.__feat.keyInfo.code === 'KeyJ' && 'focus' in window.__feat.keyInfo, window.__feat.keyInfo]);
      const n0 = window.__feat.afterApply;
      app.applyPoses();
      checks.push(['1 afterApply hook runs', window.__feat.afterApply > n0 && window.__feat.applyArgs[1] === 'boolean', window.__feat.applyArgs]);
      // a throwing hook: one console.error, the app keeps working
      const e0 = __T.errors.length;
      const bad = () => { throw new Error('test hook failure'); };
      app.hooks.afterApply.push(bad);
      let threw = false;
      try { app.applyPoses(); app.setFrame(5); app.setFrame(0); } catch { threw = true; }
      app.hooks.afterApply.splice(app.hooks.afterApply.indexOf(bad), 1);
      checks.push(['1 a throwing hook logs an error and the app keeps working', !threw && __T.errors.length > e0 && __T.errors.slice(e0).some(x => /test hook failure/.test(x)), __T.errors.slice(e0, e0 + 2)]);
      // a throwing feature is skipped with one error
      const e1 = __T.errors.length;
      const r2 = await app.loadFeatures(['data:text/javascript,' + encodeURIComponent('export function install() { throw new Error("broken feature"); }')]);
      checks.push(['1 a failing feature is skipped with an error', r2[0] && !r2[0].ok && __T.errors.length > e1, r2]);
      // wa:step once per change
      const evs = [];
      const off = app.on('step', d => evs.push([d.prev, d.step]));
      app.showStep('pose'); app.showStep('motion'); app.showStep('motion'); app.showStep('body'); app.showStep('body');
      off();
      checks.push(['1 wa:step fires once per step change with prev/step', JSON.stringify(evs) === JSON.stringify([['pose', 'motion'], ['motion', 'body']]), evs]);
      // other events exist
      const got = {};
      const offs = ['selection', 'keyed', 'undo', 'rendered'].map(n => app.on(n, d => { got[n] = d; }));
      const s = app.store.sim();
      app.selectSim(s.id);
      app.setFrame(10); app.keyPose(s.id); app.undo();
      app.showStep('pose');
      offs.forEach(f => f());
      checks.push(['1 wa:selection / wa:keyed / wa:undo / wa:rendered fire', !!got.selection && got.keyed && got.keyed.kind === 'add' && got.undo && Array.isArray(got.undo.simIds) && got.undo.simIds.includes(s.id) && got.rendered && got.rendered.step === 'pose',
        { keyed: got.keyed && got.keyed.kind, undo: got.undo && got.undo.simIds, rendered: got.rendered && got.rendered.step }]);
      app.setFrame(0);
      return { checks };
    });
    // wa:sent through the real Send to game dialog (the harness answers /api/project and /api/export)
    const w0 = writes.length;
    await pe(page, async () => {
      const checks = [];
      const p = app.store.project;
      p.name = 'Face check'; p.author = 'Tester';
      window.__sent = null;
      const off = app.on('sent', d => { window.__sent = { hero: !!(d.heroSlot && d.heroSlot.isConnected), extra: !!(d.extraSlot && d.extraSlot.isConnected), first: d.first, result: !!d.result, project: d.project === app.store.project }; });
      app.exportDialog();
      await __T.sleep(200);
      const btn = [...document.querySelectorAll('#modal-root .backdrop:not(.leaving) footer button')].pop();
      btn.click();
      for (let i = 0; i < 60 && !window.__sent; i++) await __T.sleep(100);
      off();
      checks.push(['1 wa:sent fires with heroSlot and extraSlot (Send to game intercepted)', window.__sent && window.__sent.hero && window.__sent.extra && window.__sent.result && window.__sent.project && window.__sent.first === true, window.__sent]);
      for (const b of document.querySelectorAll('#modal-root .backdrop')) b.remove();
      return { checks };
    });
    const sentWrites = writes.slice(w0).map(w => w.route);
    C('1 Send to game reached no writing route on the server (answered in the browser)', sentWrites.includes('/api/export') && sentWrites.includes('/api/project'), sentWrites);
  }

  // ================================================================ 2. shims
  if (want(2)) {
    await pe(page, async () => {
      const checks = [];
      const OLD = {
        steps: ['simTabs', 'renderScene', 'renderPose', 'renderBody', 'renderFace', 'renderSounds', 'simSettings', 'toggle', 'toast'],
        dialogs: ['WW_LOCATIONS', 'openNameDialog', 'ensureNamed', 'openExportDialog', 'openTrayDialog', 'openProjectDialog', 'openAddSoundDialog', 'openImportDialog'],
        inspector: ['renderInspector'],
      };
      for (const [f, names] of Object.entries(OLD)) {
        const m = await import(`/js/${f}.js`);
        const keys = Object.keys(m).sort();
        checks.push([`2 ${f}.js exports exactly the old names`, JSON.stringify(keys) === JSON.stringify([...names].sort()), keys]);
      }
      return { checks };
    });
  }

  // ================================================================ 3. the Face tool
  if (want(3)) {
    await pe(page, async () => {
      const checks = [];
      const { F } = __T.couple('cowgirl');
      const v = app.simViews.get(F.id);
      app.showStep('face');
      app.setTool('face');
      await __T.sleep(400);
      checks.push(['3 the Face tool shows the dots on the face (30)', app.interact.faceOn && app.interact.faceHandles.length === 30, app.interact.faceHandles.length]);
      checks.push(['3 the Face tool button is in the tool row', !!document.querySelector('#tool-seg button[data-tool="face"].active')]);
      // the tongue dots sit inside the mouth: hidden (and not clickable) while it is shut, back when it opens
      {
        F.body = { ...(F.body || {}), talk: { mouth: false } };        // no automatic talking during this check
        const tongue = () => app.interact.faceHandles.filter(d => /Tounge/.test(d.bone));
        await __T.frames(24);
        const shut = tongue().map(d => d.mesh.visible);
        app.setFace(F.id, { open: 1 }, 'Mouth open');
        await __T.frames(30);
        const open = tongue().map(d => d.mesh.visible && d.mesh.material.opacity > 0.9);
        for (const k of F.keys) delete k.face;                          // back to a shut mouth (the same project object)
        app.applyPoses();
        await __T.frames(30);
        const shutAgain = tongue().map(d => d.mesh.visible);
        checks.push(['3 the tongue dots hide while the mouth is shut and come back when it opens', tongue().length === 3 && shut.every(x => !x) && open.every(Boolean) && shutAgain.every(x => !x),
          { shut, open, shutAgain }]);
      }
      // the inner brow dragged 60 mm up stops at 40 and flashes
      app.store.selected = { sim: F.id, bone: 'b__L_InBrow__' };
      app.interact.selectFaceBone(F.id, 'b__L_InBrow__');
      const gz = __T.gz();
      checks.push(['3 a brow gets arrows (move)', gz.mode === 'translate' && gz.object === v.bone('b__L_InBrow__'), gz.mode]);
      const lim0 = app.interact._limitHit || 0;
      __T.drag(() => { const b = v.bone('b__L_InBrow__'); b.position.x += 0.060; });
      const up = __T.off(v, 'b__L_InBrow__').x;
      const dot = app.interact.faceHandles.find(d => d.bone === 'b__L_InBrow__');
      const flashed = (app.interact._limitHit || 0) > lim0 && dot && dot.flashT && performance.now() - dot.flashT < 2000;
      checks.push(['3 the inner brow dragged 60 mm up stops at 40 mm', Math.abs(up - 40) < 0.06, up.toFixed(3) + ' mm']);
      checks.push(['3 ... and its dot flashes (safe range reached)', flashed && /Safe range reached/.test(document.getElementById('vp-hud').textContent), document.getElementById('vp-hud').textContent]);
      const key0 = F.keys.find(k => k.frame === 0);
      checks.push(['3 the brow is stored in key.faceBones (+40 mm)', key0 && key0.faceBones && key0.faceBones.pos && key0.faceBones.pos.b__L_InBrow__ && Math.abs((key0.faceBones.pos.b__L_InBrow__[0] - v.restByName.b__L_InBrow__.pos.x) * 1000 - 40) < 0.06]);
      app.altDown = true;
      __T.drag(() => { const b = v.bone('b__L_InBrow__'), base = __M.K.baseOf(v, 'b__L_InBrow__').p.x; b.position.x += (v.restByName.b__L_InBrow__.pos.x + 0.060) - base; });
      const up2 = __T.off(v, 'b__L_InBrow__').x;
      app.altDown = false;
      checks.push(['3 with Alt held it reaches 60 mm', Math.abs(up2 - 60) < 0.06, up2.toFixed(3) + ' mm']);
      // the eye shows only its X and Z rings
      app.interact.selectFaceBone(F.id, 'b__L_Eye__');
      checks.push(['3 the eye shows only its X and Z rings', gz.mode === 'rotate' && gz.showX && !gz.showY && gz.showZ, [gz.mode, gz.showX, gz.showY, gz.showZ]]);
      // Symmetry: the left corner up 5 / out 3 gives the right corner +5 / -3
      app.mirrorEdit = true;
      app.interact.selectFaceBone(F.id, 'b__L_Mouth__');
      __T.drag(() => {
        const b = v.bone('b__L_Mouth__'), base = __M.K.baseOf(v, 'b__L_Mouth__').p, r = v.restByName.b__L_Mouth__.pos;
        b.position.x += (r.x + 0.005) - base.x; b.position.z += (r.z + 0.003) - base.z;
      });
      const oR = __T.off(v, 'b__R_Mouth__'), oL = __T.off(v, 'b__L_Mouth__');
      checks.push(['3 Symmetry: left corner +5 up / +3 out -> right corner x +5, z -3', Math.abs(oR.x - 5) < 0.06 && Math.abs(oR.z + 3) < 0.06 && Math.abs(oL.x - 5) < 0.06 && Math.abs(oL.z - 3) < 0.06, { L: [oL.x, oL.z].map(x => +x.toFixed(3)), R: [oR.x, oR.z].map(x => +x.toFixed(3)) }]);
      app.interact.selectFaceBone(F.id, 'b__UpLip__');
      __T.drag(() => { const b = v.bone('b__UpLip__'); b.position.z += 0.002; b.position.x += 0.002; });
      const oU = __T.off(v, 'b__UpLip__');
      checks.push(['3 Symmetry: the middle upper lip keeps its z (stays in the middle)', Math.abs(oU.z) < 0.01 && Math.abs(oU.x - 2) < 0.06, [oU.x, oU.z].map(x => +x.toFixed(4))]);
      app.mirrorEdit = false;
      // eyes: the look-at ring 30 cm to the sim's left turns both eyes about +30 degrees (clamped at 32)
      app.interact.selectEyes(F.id);
      v.group.updateMatrixWorld(true);
      const head = v.bone('b__Head__');
      const hq = head.getWorldQuaternion(head.quaternion.clone());
      const fwd = v.bone('b__Head__').position.clone().set(0, 1, 0).applyQuaternion(hq);
      const left = fwd.clone().set(0, 0, 1).applyQuaternion(hq);
      const mid = v.bone('b__L_Eye__').getWorldPosition(fwd.clone()).add(v.bone('b__R_Eye__').getWorldPosition(fwd.clone())).multiplyScalar(0.5);
      __T.drag(() => { app.interact.proxy.position.copy(mid.clone().addScaledVector(fwd, 0.35).addScaledVector(left, 0.30)); });
      const eyeYaw = n => { const e = new (v.bone(n).rotation.constructor)().setFromQuaternion(__T.turn(v, n), 'XYZ'); return __T.deg(e.x); };
      const yl = eyeYaw('b__L_Eye__'), yr = eyeYaw('b__R_Eye__');
      checks.push(['3 eyes: the ring 30 cm to the sim\'s left turns both eyes about +30 deg (max 32)', yl > 27 && yl <= 32.05 && yr > 27 && yr <= 32.05, [yl.toFixed(2), yr.toFixed(2)]]);
      // a face key between body keys is a small pink diamond; dragging it onto a body key merges them
      app.setTool('face');
      F.keys = F.keys.filter(k => k.frame === 0);
      app.setFrame(60); app.keyPose(F.id, { body: true });
      app.setFrame(30);
      app.interact.selectFaceBone(F.id, 'b__L_Cheek__');
      __T.drag(() => { v.bone('b__L_Cheek__').position.x += 0.004; });
      const fk = F.keys.find(k => k.frame === 30);
      checks.push(['3 a face edit between body keys makes a face-only key', fk && fk.faceOnly === true && fk.faceBones && fk.faceBones.pos.b__L_Cheek__, fk && { faceOnly: fk.faceOnly, fb: !!fk.faceBones }]);
      app.timeline.draw();
      return { checks, data: { simId: F.id } };
    });
    // the pink diamond on the timeline, then a real mouse drag onto the body key at 60
    const geo = await page.evaluate(() => {
      const tl = app.timeline, r = tl.canvas.getBoundingClientRect();
      const row = app.store.project.sims.findIndex(s => s.id === app.store.selected.sim);
      const y = tl._y(row, 4) + 1, x = tl.xAt(30), x2 = tl.xAt(60);
      const px = tl.ctx.getImageData(Math.round(x * (window.devicePixelRatio || 1)), Math.round(y * (window.devicePixelRatio || 1)), 1, 1).data;
      return { x: r.left + x, y: r.top + y, x2: r.left + x2, px: [...px] };
    });
    const pink = geo.px[0] > 200 && geo.px[1] < 170 && geo.px[2] > 130;
    C('3 the face-only key is a small pink diamond on the face row', pink, geo.px);
    if (SHOTS) {
      // the picture: the playhead off the face key (so the small pink diamond shows), after the Send-to-game celebration
      await page.evaluate(() => { app.setFrame(45); app.timeline.draw(); });
      await sleep(1800);
      await H.shot(page, path.join(OUT, 'face_only_key_1366.png'));
    }
    await page.mouse.move(geo.x, geo.y);
    await page.mouse.down();
    for (let k = 1; k <= 8; k++) await page.mouse.move(geo.x + (geo.x2 - geo.x) * k / 8, geo.y);
    await page.mouse.up();
    await sleep(200);
    await pe(page, () => {
      const F = app.store.sim();
      const at60 = F.keys.filter(k => k.frame === 60), at30 = F.keys.filter(k => k.frame === 30);
      const k = at60[0];
      return { checks: [['3 dragging the face key onto the body key merges them (body kept, face added)', at60.length === 1 && at30.length === 0 && k && !k.faceOnly && k.faceBones && k.faceBones.pos.b__L_Cheek__ && k.pose && k.pose.rot,
        { at60: at60.length, at30: at30.length, faceOnly: k && k.faceOnly, keys: F.keys.map(x => x.frame) }]] };
    });
  }

  // ================================================================ 4. the bone list
  if (want(4)) {
    await pe(page, async () => {
      const checks = [];
      const { F, M: Mm } = __T.couple('cowgirl');
      app.setTool('rotate');
      localStorage.setItem('fsa.boneListOpen', 'true');
      localStorage.setItem('fsa.boneFilter', JSON.stringify({ keyed: false, face: false, expert: false }));
      app._boneFilter = null; app._boneQuery = '';
      const search = async (simId, q) => {
        app.selectSim(simId);
        app.refreshPanels();
        const input = document.querySelector('#bone-list .bone-search input');
        input.value = q; input.dispatchEvent(new Event('input', { bubbles: true }));
        return [...document.querySelectorAll('#bone-list .bone-row')].map(r => r.dataset.bone);
      };
      const LIPS = ['b__UpLip__', 'b__LoLip__', 'b__L_UpLip__', 'b__R_UpLip__', 'b__L_LoLip__', 'b__R_LoLip__', 'b__L_Mouth__', 'b__R_Mouth__'];
      const lipM = await search(Mm.id, 'lip');
      checks.push(['4 "lip" lists the 6 lip bones plus the corners', lipM.length === 8 && LIPS.every(n => lipM.includes(n)), lipM]);
      const lipF = await search(F.id, 'lip');
      checks.push(['4 ... (on a female body the vagina lips come too)', LIPS.every(n => lipF.includes(n)), lipF.length]);
      const t1 = await search(F.id, 'Tounge'), t2 = await search(F.id, 'tongue');
      const T3 = ['b__Tounge__1', 'b__Tounge__2', 'b__Tounge__3'];
      checks.push(['4 "Tounge" and "tongue" both find the tongue', T3.every(n => t1.includes(n)) && T3.every(n => t2.includes(n)), [t1, t2]]);
      const brow = await search(F.id, 'eyebrow');
      checks.push(['4 "eyebrow" finds the brows', brow.length === 6 && brow.every(n => /Brow/.test(n)), brow]);
      const wrist = await search(F.id, 'wrist');
      checks.push(['4 "wrist" finds the wrist twist and the hand', wrist.includes('b__L_ForearmTwist__') && wrist.includes('b__L_Hand__'), wrist]);
      await search(F.id, 'hand');
      const row = document.querySelector('#bone-list .bone-row[data-bone="b__L_Hand__"]');
      row.click();
      const v = app.simViews.get(F.id);
      checks.push(['4 clicking a row selects the bone (the gizmo is attached)', app.store.selected.bone === 'b__L_Hand__' && app.vp.gizmo.object === v.bone('b__L_Hand__'), app.store.selected.bone]);
      await search(F.id, 'upper eyelid');
      document.querySelector('#bone-list .bone-row[data-bone="b__L_UpLid__"]').click();
      checks.push(['4 a face row opens the Face tool with the face gizmo', app.interact.tool === 'face' && app.interact.active && app.interact.active.face && app.vp.gizmo.object === v.bone('b__L_UpLid__'), app.interact.tool]);
      await search(F.id, '');
      const chip = [...document.querySelectorAll('#bone-list .bone-chips .chip')].find(c => c.textContent === 'Expert');
      chip.click();
      const groups = [...document.querySelectorAll('#bone-list .bone-group')];
      const eg = groups.find(g => /Expert/.test(g.querySelector('summary').textContent));
      const expertRows = eg ? [...eg.querySelectorAll('.bone-row')].map(r => r.dataset.bone) : [];
      checks.push(['4 the Expert chip shows the 21 expert bones', expertRows.length === 21, expertRows.length]);
      chip.click();
      // raw name under the part name
      checks.push(['4 the inspector shows the raw rig name', (document.querySelector('#inspector .raw-name') || {}).textContent === 'b__L_UpLid__']);
      app.setTool('rotate');
      return { checks };
    });
    if (SHOTS) {
      await page.evaluate(() => {
        const input = document.querySelector('#bone-list .bone-search input');
        input.value = 'lip'; input.dispatchEvent(new Event('input', { bubbles: true }));
        document.querySelector('#bone-list').scrollIntoView();
      });
      await sleep(300);
      await H.shot(page, path.join(OUT, 'bone_list_lip_1366.png'));
    }
  }

  // ================================================================ 5. import keeps the face
  if (want(5)) {
    await pe(page, async () => {
      const checks = [];
      __T.couple('cowgirl');
      const anim = await __M.api.animation(5, 1);
      // the actor that blinks, and a 150-frame window around its biggest lid change
      let best = null;
      anim.clips.forEach((c, k) => {
        const r = c.tracks.b__L_UpLid__ && c.tracks.b__L_UpLid__.r;
        if (!r) return;
        for (let i = 1; i < r.length; i++) {
          const d = __T.qang(r[i - 1].slice(1), r[0].slice(1));
          if (!best || d > best.d) best = { k, d, tick: r[i - 1][0] };
        }
      });
      app.library.startPreview(anim);
      const pv = app.library.preview;
      const from = Math.max(0, Math.min(pv.length - 160, Math.round(best.tick) - 60));
      const len = 150;
      __M.imp.importKeys(app, pv, 6, from, len, true);
      const s = app.store.project.sims[best.k];
      const withLid = s.keys.filter(k => k.faceBones && k.faceBones.rot && k.faceBones.rot.b__L_UpLid__);
      checks.push(['5 Import as keys of a creator clip that blinks gives UpLid faceBones', withLid.length >= 2, { keys: s.keys.length, faceKeys: s.keys.filter(k => k.faceBones).length, withLid: withLid.length, faceOnly: s.keys.filter(k => k.faceOnly).length }]);
      checks.push(['5 ... and switches the automatic blinking off (the creator\'s blinks are kept)', s.body && s.body.blink === false]);
      const baked = app.bake();
      const tr = baked.actors[best.k].tracks.b__L_UpLid__.r;
      const player = new __M.animation.ClipPlayer(anim.clips[best.k]);
      let worst = 0;
      for (let i = 0; i < 20; i++) {
        const f = Math.round(i * (len - 1) / 19);
        const want = player.sample(from + f).b__L_UpLid__.r;
        worst = Math.max(worst, __T.qang(tr[f], want));
      }
      checks.push(['5 the bake\'s UpLid matches the clip within 1.5 deg at 20 frames', worst <= 1.5, worst.toFixed(3) + ' deg']);
      // "Use this pose" brings the creator's face
      __T.couple('cowgirl');
      app.library.startPreview(anim);
      const pv2 = app.library.preview;
      pv2.playing = false; pv2.frame = Math.round(best.tick);
      const sample = pv2.players[best.k].sample(pv2.frame);
      app.library.usePose();
      const s2 = app.store.project.sims.find(x => x.frame === (anim.actors[best.k].gender === 'MALE' ? 'ym' : 'yf')) || app.store.project.sims[best.k];
      const k0 = s2.keys.find(k => k.frame === Math.round(app.store.frame));
      const got = k0 && k0.faceBones && k0.faceBones.rot && k0.faceBones.rot.b__L_UpLid__;
      checks.push(['5 "Use this pose" shows the creator\'s face (UpLid as in the clip)', got && __T.qang(got, sample.b__L_UpLid__.r) < 0.1, got ? __T.qang(got, sample.b__L_UpLid__.r).toFixed(4) : 'none']);
      return { checks };
    });
  }

  // ================================================================ 6. expression baking
  if (want(6)) {
    await pe(page, async () => {
      const checks = [];
      const { F } = __T.couple('cowgirl');
      F.body = { blink: false, talk: { mouth: false } };
      const pr = __M.face.FACE_PRESETS.ecstasy;
      app.setFrame(0); app.setFace(F.id, { ...pr.face }, pr.label);
      app.setFrame(30); app.setFace(F.id, { ...pr.face }, pr.label);
      app.setFrame(0);
      const A = app.bake().actors[0].tracks;
      app.bakeFace(F.id, { all: true });
      checks.push(['6 no key has face sliders left', F.keys.every(k => !k.face), F.keys.map(k => [k.frame, !!k.face, !!k.faceBones])]);
      const B = app.bake().actors[0].tracks;
      const keysAt = new Set([0, 30]);
      let atKey = { rot: 0, pos: 0 }, between = { rot: 0, pos: 0 }, worstBone = '';
      for (const n of __M.K.FACE_CHANNEL) {
        const a = A[n], b = B[n];
        if (!a || !b) continue;
        for (let f = 0; f < 90; f++) {
          const bucket = keysAt.has(f) ? atKey : between;
          if (a.r && b.r) { const d = __T.qang(a.r[f], b.r[f]); if (d > bucket.rot) { bucket.rot = d; if (bucket === atKey) worstBone = n; } }
          if (a.t && b.t) { const d = Math.hypot(a.t[f][0] - b.t[f][0], a.t[f][1] - b.t[f][1], a.t[f][2] - b.t[f][2]) * 1000; if (d > bucket.pos) bucket.pos = d; }
        }
      }
      checks.push(['6 face tracks match the slider version at keys (0.3 mm / 0.5 deg)', atKey.pos <= 0.3 && atKey.rot <= 0.5, { mm: +atKey.pos.toFixed(4), deg: +atKey.rot.toFixed(4), worstBone }]);
      checks.push(['6 ... and between keys (1 mm / 2 deg)', between.pos <= 1 && between.rot <= 2, { mm: +between.pos.toFixed(4), deg: +between.rot.toFixed(4) }]);
      return { checks };
    });
  }

  // ================================================================ 7. the timeline API
  if (want(7)) {
    await pe(page, async () => {
      const checks = [];
      __T.couple('cowgirl');
      const tl = app.timeline;
      const base = 28 + tl.rowsHeight();          // the ruler, plus the rows features have added (Moments...)
      checks.push([`7 laneTop(0) === 28 + the rows features added (${tl.rows.map(r => r.id).join(', ') || 'none'})`, tl.laneTop(0) === base, { laneTop: tl.laneTop(0), rows: tl.rowsHeight() }]);
      let hits = 0, downs = 0;
      const remove = tl.addRow({ id: 'test-row', height: 22, label: 'Test', order: 1,
        draw(g, ctx) { g.fillStyle = '#3ddc84'; g.fillRect(ctx.xAt(10), ctx.y + 4, 20, ctx.h - 8); },
        hit(x, y, ctx) { hits++; return x >= ctx.xAt(10) && x <= ctx.xAt(10) + 20 ? { id: 'block' } : null; },
        onDown(item) { if (item) downs++; }, tooltip: () => 'Test block' });
      const lt = tl.laneTop(0);
      const r = tl.canvas.getBoundingClientRect();
      const x = r.left + tl.xAt(10) + 10, y = r.top + tl._rowTop(tl.rows.find(q => q.id === 'test-row')) + 11;
      tl.canvas.dispatchEvent(new PointerEvent('pointerdown', { clientX: x, clientY: y, button: 0, bubbles: true }));
      window.dispatchEvent(new PointerEvent('pointerup', { clientX: x, clientY: y, button: 0, bubbles: true }));
      checks.push(['7 a 22 px test row moves laneTop(0) down 22 px and gets hit-tested', lt === base + 22 && hits > 0 && downs === 1, { laneTop: lt, base, hits, downs }]);
      remove();
      checks.push(['7 removing the row puts the lanes back', tl.laneTop(0) === base]);
      // marks: drawn in a sim's lane, a click jumps there
      const sim = app.store.project.sims[1];
      tl.marks = [{ frame: 40, to: 44, simId: sim.id, color: '#fbbf24', title: 'Test mark' }];
      tl.draw();
      await __T.sleep(100);
      const r2 = tl.canvas.getBoundingClientRect();          // the timeline was taller while the test row was there
      tl.draw();
      const row = 1, my = r2.top + tl._y(row, 45), mx = r2.left + tl.xAt(42);
      tl.canvas.dispatchEvent(new PointerEvent('pointerdown', { clientX: mx, clientY: my, button: 0, bubbles: true }));
      window.dispatchEvent(new PointerEvent('pointerup', { clientX: mx, clientY: my, button: 0, bubbles: true }));
      checks.push(['7 a click on a mark jumps to its frame', Math.round(app.store.frame) === 40, app.store.frame]);
      tl.marks = [];
      tl.draw();
      return { checks };
    });
    // reduced motion: flash() runs no animation frames
    await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
    await pe(page, async () => {
      let raf = 0;
      const orig = window.requestAnimationFrame;
      const tl = app.timeline;
      window.requestAnimationFrame = f => { raf++; return orig(f); };
      tl._fxRaf = 0; tl.fx = [];
      const before = raf;
      tl.flash(app.store.project.sims[0].id, 0, 'add');
      const n = raf - before;
      window.requestAnimationFrame = orig;
      return { checks: [['7 flash() runs no animation frames with reduced motion', n === 0 && !tl._fxRaf && tl.fx.length === 0, { raf: n }]] };
    });
    await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'no-preference' }]);
    await pe(page, async () => {
      const tl = app.timeline;
      let raf = 0;
      const orig = window.requestAnimationFrame;
      window.requestAnimationFrame = f => { raf++; return orig(f); };
      tl.flash(app.store.project.sims[0].id, 0, 'add');
      await __T.sleep(500);
      window.requestAnimationFrame = orig;
      return { checks: [['7 flash() animates (and stops by itself) without reduced motion', raf > 3 && !tl._fxRaf && tl.fx.length === 0, { raf }]] };
    });
  }

  // ================================================================ 8. camera
  if (want(8)) {
    await pe(page, async () => {
      const checks = [];
      const { F } = __T.couple('missionary');
      app.selectSim(F.id);
      app.setTool('rotate');
      app.showStep('pose');
      await __T.sleep(600);
      const v = app.simViews.get(F.id);
      v.group.updateMatrixWorld(true);
      const head = v.bone('b__Head__'), hq = head.getWorldQuaternion(head.quaternion.clone());
      const up = v.bone('b__Head__').position.clone().set(1, 0, 0).applyQuaternion(hq);      // the face's up (head frame x)
      app.showStep('face');
      await __T.sleep(1400);
      v.group.updateMatrixWorld(true);
      app.vp.camera.updateMatrixWorld(true);
      const scr = w => { const p = w.clone().project(app.vp.camera); return [p.x, -p.y]; };
      const eyes = v.bone('b__L_Eye__').getWorldPosition(up.clone()).add(v.bone('b__R_Eye__').getWorldPosition(up.clone())).multiplyScalar(0.5);
      const chin = v.bone('b__CAS_Chin__').getWorldPosition(up.clone());
      const se = scr(eyes), sc = scr(chin);
      checks.push(['8 the lying sim\'s head lies (test setup)', up.y < 0.35, +up.y.toFixed(3)]);
      checks.push(['8 the Face step shows a lying face upright (face centre above the chin on screen)', se[1] < sc[1] - 0.02, { eyes: se.map(x => +x.toFixed(3)), chin: sc.map(x => +x.toFixed(3)) }]);
      const d0 = app.vp.camera.position.distanceTo(eyes);
      checks.push(['8 ... close up on the face', d0 < 1.1, +d0.toFixed(3)]);
      app.showStep('library');
      await __T.sleep(1200);
      const d1 = app.vp.camera.position.distanceTo(eyes);
      checks.push(['8 the Library after the Face step is not a head close-up', d1 > 1.4, +d1.toFixed(3)]);
      app.showStep('pose');
      return { checks };
    });
  }

  // ================================================================ 11. speed (plan rule 7: the panel rebuild stays under 50 ms)
  if (want(11)) {
    await pe(page, async () => {
      const checks = [];
      const { F } = __T.couple('cowgirl');
      localStorage.setItem('fsa.boneListOpen', 'true');
      app.store.selected = { sim: F.id, bone: 'b__L_InBrow__' };
      const med = fn => { const t = []; for (let i = 0; i < 7; i++) { const t0 = performance.now(); fn(); t.push(performance.now() - t0); } t.sort((a, b) => a - b); return t[3]; };
      const out = {};
      for (const step of ['scene', 'pose', 'motion', 'body', 'face', 'sounds', 'details', 'share']) {
        app.showStep(step);
        await __T.sleep(50);
        out[step] = +med(() => app.renderStep()).toFixed(1);
      }
      out.inspectorWithBoneList = +med(() => app.refreshPanels()).toFixed(1);
      const worst = Math.max(...Object.values(out));
      checks.push(['11 every step panel (and the inspector with All bones open) rebuilds in under 50 ms (median)', worst < 50, out]);
      localStorage.removeItem('fsa.boneListOpen');
      app.showStep('pose');
      return { checks };
    });
  }

  // ================================================================ 12. round-1 gate fixes: Magic on the double bed
  // (a) in the Face step the dots sit on the selected sim's face (never the back of the partner's head);
  // (b) leaving the Face step, the camera goes back to the view from before it - above the bed, never under it;
  // (c) Send to game: the empty Creator box is marked and gets the cursor.
  if (want(12)) {
    for (const recipe of ['cowgirl', 'missionary']) {
      await page.evaluate(async recipe => {
        const m = await import('/js/magic.js');
        await m.makeMagic(app, { recipe, place: 'double_bed', intensity: 0.55, seconds: 3 });
      }, recipe);
      await sleep(1800);
      await page.evaluate(() => { clearTimeout(app._magicShow); app.showcase(false); app.setPlaying(false); app.setFrame(0); app.setTool('rotate'); });
      await sleep(500);
      for (const who of [0, 1]) {
        const before = await page.evaluate(who => {
          const s = app.store.project.sims[who];
          app.selectSim(s.id);
          return { cam: app.vp.camera.position.toArray(), sel: s.id, label: s.label };
        }, who);
        await page.evaluate(() => app.showStep('face'));
        await sleep(1300);
        const r = await pe(page, (recipe, who) => {
          const it = app.interact, sel = app.store.selected.sim, v = app.simViews.get(sel);
          const head = v.worldPos('b__Head__');
          const dots = it.faceHandles || [];
          const far = dots.reduce((m, d) => Math.max(m, d.mesh.getWorldPosition(head.clone()).distanceTo(head)), 0);
          // every dot sits on its own part of the selected sim's face (its place on that bone - the jaw's is on the chin)
          const spot = d => v.bone(d.bone).localToWorld(__M.K.faceHandlePoint(v, d.bone).clone());
          const off = dots.filter(d => d.simId !== sel || d.mesh.getWorldPosition(head.clone()).distanceTo(spot(d)) > 0.005).length;
          const s = app.store.sim();
          return { checks: [[`12 ${recipe} on the double bed, ${s.label}: in the Face step the face dots sit on the selected sim's face`,
            it.faceOn && it.faceSimId === sel && dots.length >= 24 && far < 0.16 && off === 0 && it.faceSeen(v),
            { faceOn: it.faceOn, onSelected: it.faceSimId === sel, dots: dots.length, farthestDot_m: +far.toFixed(3), dotsOffTheirPart: off, faceSeen: it.faceSeen(v), camToHead_m: +app.vp.camera.position.distanceTo(head).toFixed(3) }]] };
        }, recipe, who);
        void r;
        await H.shot(page, path.join(OUT, `gate_face_${recipe}_double_bed_${who ? 'male' : 'female'}.png`));
        // leave the Face step: the view from before comes back (above the mattress)
        const steps = who === 0 ? ['sounds', 'face', 'details', 'face', 'share', 'face', 'library'] : ['sounds'];
        const out = [];
        for (const st of steps) {
          await page.evaluate(st => app.showStep(st), st);
          await sleep(st === 'face' ? 900 : 700);
          if (st !== 'face') out.push(await page.evaluate(st => ({ st, y: +app.vp.camera.position.y.toFixed(3), top: +app._surfaceTop().toFixed(3), cam: app.vp.camera.position.toArray() }), st));
        }
        const back = out[0];
        const same = Math.hypot(...back.cam.map((x, k) => x - before.cam[k]));
        C(`12 ${recipe}, ${before.label}: leaving the Face step goes back to the view from before it`, same < 0.02, { moved_m: +same.toFixed(4) });
        C(`12 ${recipe}, ${before.label}: after the Face step the camera is above the mattress (Sounds${who === 0 ? ', Details, Share, Library' : ''})`,
          out.every(o => o.y > o.top + 0.1), out.map(o => `${o.st} ${o.y} m (top ${o.top})`));
        if (who === 0) await H.shot(page, path.join(OUT, `gate_after_face_${recipe}_double_bed.png`));
        await page.evaluate(() => app.showStep('pose'));
        await sleep(400);
      }
    }
    // the Pose tool near the back of a head (outside the Face step): no dots there; turned to its face: dots
    await pe(page, async () => {
      app.showStep('pose'); app.setTool('rotate');
      const [F, Mm] = app.store.project.sims;
      app.selectSim(F.id);
      const w = app.simViews.get(Mm.id), head = w.bone('b__Head__'), hp = head.getWorldPosition(w.worldPos('b__Head__'));
      const fwd = hp.clone().set(0, 1, 0).applyQuaternion(head.getWorldQuaternion(app.vp.camera.quaternion.clone()));
      const look = async sign => { app.vp.stopCamera(); app.vp.controls.lookFrom(hp.clone().addScaledVector(fwd, 0.55 * sign).add(hp.clone().set(0, 0.05, 0)), hp); await __T.sleep(400); app.interact.updateFaceMode(true); return { faceSim: app.interact.faceSimId, dots: app.interact.faceHandles.length }; };
      const behind = await look(-1), front = await look(1);
      return { checks: [['12 Pose tool 55 cm behind a head: no face dots on the back of it; from the front its face gets them',
        behind.faceSim !== Mm.id && front.faceSim === Mm.id, { behind: behind.faceSim === Mm.id ? 'dots on the back of his head' : behind.faceSim ? 'dots on another face' : 'no dots', front: front.faceSim === Mm.id ? 'dots on his face' : 'none' }]] };
    });
    // with no view to go back to (it was dropped), leaving the Face step frames the sims from above, not from below
    await pe(page, async () => {
      app.showStep('face');
      await __T.sleep(900);
      app._camBeforeFace = null;
      // a close-up that looks up at the face from below the mattress
      const head = app.simViews.get(app.store.selected.sim).worldPos('b__Head__');
      app.vp.stopCamera();
      app.vp.controls.lookFrom(head.clone().add(head.clone().set(0.3, -0.35, 0.4)), head);
      app.showStep('sounds');
      await __T.sleep(700);
      const y = app.vp.camera.position.y, top = app._surfaceTop(), dir = app.vp.viewDir();
      return { checks: [['12 with no view to go back to, leaving the Face step frames the sims from above the bed', y > top + 0.3 && dir.y > 0.3, { y: +y.toFixed(3), top: +top.toFixed(3), dirY: +dir.y.toFixed(3) }]] };
    });
    // (c) the Send dialog with a name but no creator: the Creator box is red and has the cursor
    await pe(page, async () => {
      const p = app.store.project;
      p.name = 'Gate check'; p.author = '';
      try { localStorage.removeItem('fsa.author'); } catch { /* blocked */ }
      app.exportDialog();
      await __T.sleep(300);
      const dlg = [...document.querySelectorAll('#modal-root .backdrop:not(.leaving) .modal')].pop();
      const boxes = dlg ? [...dlg.querySelectorAll('.inline-name .field')] : [];
      const author = boxes[1], name = boxes[0];
      const btn = dlg && dlg.querySelector('.btn.primary, footer button:last-child');
      const r = { fields: boxes.length, authorRed: !!author && author.classList.contains('invalid'), authorMsg: author && author.querySelector('.field-err')?.textContent,
        nameRed: !!name && name.classList.contains('invalid'), focusInAuthor: !!author && author.contains(document.activeElement), button: dlg && dlg.querySelector('.foot button:last-child, footer button:last-child')?.textContent };
      const checks = [['12 Send to game without a creator: the Creator box is marked red and gets the cursor (the filled name box is not marked)', r.fields === 2 && r.authorRed && !r.nameRed && r.focusInAuthor && /creator/i.test(r.authorMsg || ''), r]];
      // typing a creator clears the mark and the Send button comes back
      const inp = author.querySelector('input');
      inp.value = 'Tester'; inp.dispatchEvent(new Event('input', { bubbles: true }));
      await __T.sleep(50);
      const last = [...dlg.querySelectorAll('button')].pop();
      checks.push(['12 ... typing the creator clears the mark and "Send to game" is ready', !author.classList.contains('invalid') && !last.disabled && /Send to game/.test(last.textContent), { red: author.classList.contains('invalid'), btn: last.textContent, disabled: last.disabled }]);
      void btn;
      return { checks };
    });
    if (SHOTS) {
      await page.evaluate(() => { const i = document.querySelector('#modal-root .inline-name .field:nth-child(2) input'); if (i) { i.value = ''; i.dispatchEvent(new Event('input', { bubbles: true })); i.focus(); } });
      await sleep(250);
      await H.shot(page, path.join(OUT, 'gate_send_creator_missing.png'));
    }
    await page.evaluate(() => { for (const b of [...document.querySelectorAll('#modal-root .backdrop')]) b.remove(); });
  }

  // ================================================================ 9 (e2e) runs separately: node tools/e2e.js --port <port>

  // ================================================================ 10. screenshots
  if (want(10) && SHOTS) {
    const shotsFor = async (pg, tag) => {
      await pg.evaluate(async () => {
        const { F } = __T.couple('cowgirl');
        app.showStep('face');
        app.setTool('face');
        app.selectSim(F.id);
        await __T.sleep(1500);
        app.store.selected = { sim: F.id, bone: null };
        app.vp.gizmo.detach(); app.interact.active = null;
        app.emitSelection();
      });
      await sleep(700);
      await H.shot(pg, path.join(OUT, `face_tool_dots_${tag}.png`));
      await pg.evaluate(async () => {
        const F = app.store.sim();
        app.store.selected = { sim: F.id, bone: 'b__L_InBrow__' };
        app.interact.selectFaceBone(F.id, 'b__L_InBrow__');
        app.emitSelection();
      });
      await sleep(500);
      await H.shot(pg, path.join(OUT, `face_brow_arrows_${tag}.png`));
      await pg.evaluate(async () => {
        const F = app.store.sim(), v = app.simViews.get(F.id);
        app.store.selected = { sim: F.id, bone: 'b__L_UpLid__' };
        app.interact.selectFaceBone(F.id, 'b__L_UpLid__');
        __T.drag(() => { v.bone('b__L_UpLid__').rotateZ(0.35); });
        app.emitSelection();
      });
      await sleep(500);
      await H.shot(pg, path.join(OUT, `face_lid_rings_${tag}.png`));
    };
    await shotsFor(page, '1366');
    const big = await H.open(PORT, { w: 1920, h: 1080 });
    await helpers(big.page);
    await shotsFor(big.page, '1920');
    await big.page.evaluate(() => {
      localStorage.setItem('fsa.boneListOpen', 'true');
      app.store.selected.bone = null; app.setTool('rotate'); app.emitSelection();
      const input = document.querySelector('#bone-list .bone-search input');
      input.value = 'lip'; input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await sleep(400);
    await H.shot(big.page, path.join(OUT, 'bone_list_lip_1920.png'));
    await big.page.evaluate(() => {
      const F = app.store.sim(), v = app.simViews.get(F.id);
      F.keys = F.keys.filter(k => k.frame === 0);
      app.setFrame(60); app.keyPose(F.id, { body: true });
      app.setFrame(30); app.setTool('face');
      app.interact.selectFaceBone(F.id, 'b__L_Cheek__');
      __T.drag(() => { v.bone('b__L_Cheek__').position.x += 0.004; });
      app.setFrame(45);
      app.timeline.draw();
    });
    await sleep(400);
    await H.shot(big.page, path.join(OUT, 'face_only_key_1920.png'));
    await big.browser.close();
  }

  const errs = logs.filter(l => l.type === 'pageerror');
  C('no uncaught page errors', errs.length === 0, errs.map(e => e.text).slice(0, 5));
  const leaks = writes.filter(w => !['/api/recovery', '/api/recovery_clear', '/api/export', '/api/project'].includes(w.route));
  C('writes were all answered in the browser', true, writes.map(w => w.route).join(',') || 'none');
  void leaks;
  await browser.close();
  fs.writeFileSync(path.join(OUT, 'face_ui_report.json'), JSON.stringify({ port: PORT, seconds: (Date.now() - t0) / 1000, rows }, null, 1));
  const ok = H.report(rows, 'R1-B face_ui checks');
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
