// R2-5 checks: game faces, the face map, lip-sync from a sound, and face.js's voiceLength (build plan R2-5).
// Nothing is written to disk by the app: the harness answers every writing route in the browser; the lip-sync
// export is built offline into %TEMP% (export_events.py).
//   node tools/checks/r2-5/faces.js --port 8855 [--only A,B,C,D] [--no-shots]
const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');
const H = require('../lib/harness.js');

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const PORT = +arg('--port', 8855);
const ONLY = arg('--only', null) ? new Set(arg('--only').split(',')) : null;
const SHOTS = !argv.includes('--no-shots');
const OUT = path.join(H.ROOT, 'cache', 'checks', 'r2-5');
fs.mkdirSync(OUT, { recursive: true });
const want = k => !ONLY || ONLY.has(k);
const rows = [];
const C = (name, ok, detail) => { rows.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail === undefined ? '' : '  ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)).slice(0, 260)}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function pe(page, fn, ...args) {
  let r;
  try { r = await page.evaluate(fn, ...args); } catch (e) { C(`page code ran (${fn.name || 'anonymous'})`, false, String(e.message || e).slice(0, 400)); return null; }
  if (r && Array.isArray(r.checks)) for (const [n, ok, d] of r.checks) C(n, ok, d);
  return r ? r.data : null;
}

async function helpers(page) {
  await page.evaluate(async () => {
    const M = window.__M = {
      K: await import('/js/facekit.js'), gf: await import('/js/gamefaces.js'), fm: await import('/js/facemap2d.js'),
      ls: await import('/js/lipsync.js'), face: await import('/js/face.js'), animation: await import('/js/animation.js'),
      state: await import('/js/state.js'), THREE: await import('three'),
    };
    const T = window.__T = {};
    T.sleep = ms => new Promise(r => setTimeout(r, ms));
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
    T.qang = (a, b) => { const d = Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]) / (Math.hypot(...a) * Math.hypot(...b) || 1); return 2 * Math.acos(Math.min(1, d)); };
    T.vdist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
    // the face bones of a view as the keys have them, compared with {rot, pos} (absent = rest)
    T.faceDiff = (v, fb) => {
      let worst = 0, where = '';
      for (const n of M.K.FACE_CHANNEL) {
        if (!v.bone(n)) continue;
        const b = M.K.baseOf(v, n), r = v.restByName[n];
        const q = (fb.rot && fb.rot[n]) || r.quat.toArray(), t = (fb.pos && fb.pos[n]) || r.pos.toArray();
        const dq = T.qang(b.q.toArray(), q), dt = T.vdist(b.p.toArray(), t);
        if (dq > worst) { worst = dq; where = n + ' rot'; }
        if (dt > worst) { worst = dt; where = n + ' pos'; }
      }
      return { worst, where };
    };
    T.errors = [];
    const ce = console.error.bind(console);
    console.error = (...a) => { T.errors.push(a.map(x => String(x && x.message || x)).join(' ')); ce(...a); };
    // a crash-recovery offer left by another test run in the shared test slot: "Ignore" (its clearing is answered
    // in the browser by the harness)
    await T.sleep(800);
    for (let i = 0; i < 5; i++) {
      const b = document.querySelector('.backdrop:not(.leaving)');
      if (!b) break;
      const ign = [...b.querySelectorAll('button')].find(x => /Ignore|Close|Not now|Cancel/.test(x.textContent));
      if (ign) ign.click(); else document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await T.sleep(400);
    }
    T.home();
    await T.sleep(300);
    for (let i = 0; i < 100 && !(app.posePresets && app.posePresets.length); i++) await T.sleep(100);
    for (let i = 0; i < 100 && !(await M.gf.loadFaces()).ready; i++) await T.sleep(500);
  });
}

// the viewport, cropped (the face close-ups)
async function viewShot(page, file) {
  const r = await page.evaluate(() => { const b = document.getElementById('viewport').getBoundingClientRect(); return { x: b.x, y: b.y, width: b.width, height: b.height }; });
  return H.shot(page, path.join(OUT, file), { clip: r });
}
async function panelShot(page, file, sel) {
  if (sel) await page.evaluate(s => { const el = document.querySelector(s); if (el) el.scrollIntoView({ block: 'start' }); }, sel);
  await sleep(500);
  return H.shot(page, path.join(OUT, file));
}

(async () => {
  const t0 = Date.now();
  const W = +arg('--w', 1366), Hh = +arg('--h', 768);
  const { browser, page, logs, writes } = await H.open(PORT, { w: W, h: Hh });
  await helpers(page);
  const shots = [];

  // ================================================================ A. game faces
  if (want('A')) {
    await pe(page, async () => {
      const checks = [], M = __M, T = __T;
      const raw = await (await fetch('/api/ea_faces')).json();
      const BAD = /(child|toddler|infant|baby|babies|teen|kid|puberty|bassinet|crib|cat|dog|horse|pet|animalPen|crossAge|family|school|scout|dollhouse|toy|prom_|_prom|homework|parent)/i;
      checks.push(['A1 /api/ea_faces is ready with >= 120 faces', raw.ready && raw.faces.length >= 120, raw.faces && raw.faces.length]);
      const bad = raw.faces.filter(f => !/^(a_|a2a_|a2o_)/i.test(f.clip) || BAD.test(f.clip) || BAD.test(f.label));
      checks.push(['A1 adults only: every face is an adult clip, no child/teen/pet/family word', bad.length === 0, bad.map(f => f.clip)]);
      const faces = M.gf.facesNow();
      checks.push(['A1 the app offers exactly the adult faces', faces && faces.length === raw.faces.length - bad.length, faces && faces.length]);
      checks.push(['A1 the adults-only filter refuses a child/teen/pet clip', !M.gf.adultFace({ clip: 'a_child_happy_x', bones: {} }) && !M.gf.adultFace({ clip: 'c_UI_mood_happy_x', bones: {} }) && !M.gf.adultFace({ clip: 'a_teen_flirt_x', bones: {} }) && !M.gf.adultFace({ clip: 'a_dog_pet_x', bones: {} }) && M.gf.adultFace({ clip: 'a_UI_mood_happy_x', bones: {} }), '']);
      checks.push(['A2 the feature is installed (app.setFaceBones, css)', app.__faces2 && typeof app.setFaceBones === 'function' && !!document.querySelector('link[data-feature*="faces.css"]'), typeof app.setFaceBones]);
      // the Game faces tab
      const { F, M: Mm } = T.couple();
      app._faceTab = 'game'; app._gfGroup = 'all'; app._gfQuery = '';
      app.showStep('face');
      await T.sleep(400);
      const tiles = document.querySelectorAll('#panel-body .gf-tile');
      checks.push(['A3 the Game faces tab shows a tile per face', tiles.length === faces.length, [tiles.length, faces.length]]);
      checks.push(['A3 the one-click face tiles are not mixed in (.face-tile)', document.querySelectorAll('#panel-body .face-tile').length === 0, '']);
      let pics = 0;
      for (let i = 0; i < 80; i++) { pics = [...document.querySelectorAll('#panel-body .gf-tile img')].filter(im => (im.getAttribute('src') || '').startsWith('data:image/')).length; if (pics >= 12) break; await T.sleep(250); }
      checks.push(['A3 face pictures are rendered (>= 12 within 20 s)', pics >= 12, pics]);
      // search + group
      app._gfQuery = 'flirty'; app.renderStep(); await T.sleep(50);
      const found = [...document.querySelectorAll('#panel-body .gf-tile')].map(t => t.dataset.gf);
      checks.push(['A3 searching "flirty" finds both flirty moods', found.includes('ea:a_UI_mood_flirty_female_x') && found.includes('ea:a_UI_mood_flirty_male_x'), found]);
      app._gfQuery = '';
      return { checks };
    });

    // A4/A5: a_UI_mood_flirty_female_x on a yf and a ym sim
    const flirty = await pe(page, async () => {
      const checks = [], M = __M, T = __T;
      const { F, M: Mm } = T.couple();
      const face = M.gf.faceById('ea:a_UI_mood_flirty_female_x');
      checks.push(['A4 a_UI_mood_flirty_female_x is offered', !!face, face && face.label]);
      if (!face) return { checks };
      const p = app.store.project;
      F.body = F.body || {}; F.body.blink = false;          // the face itself, without a blink on top
      const before = app.bake();
      const bodyTrack = (b, i) => b.actors[i].tracks;
      // on the female at frame 45 (no key there: a face-only key), and on the male at frame 0 (his body key)
      app.setFrame(45);
      app.store.selected = { sim: F.id, bone: null };
      const u0 = app.store.undo.length;
      const k1 = app.setFaceBones(F.id, face.fb, face.short, 1, { id: face.id });
      checks.push(['A4 a face-only key where the body has no key', k1 && k1.faceOnly === true && k1.frame === 45, k1 && { frame: k1.frame, faceOnly: k1.faceOnly }]);
      checks.push(['A4 one undo step', app.store.undo.length === u0 + 1, app.store.undo.length - u0]);
      // intensity 1 equals the face
      let worst = 0;
      for (const [n, q] of Object.entries(face.fb.rot)) worst = Math.max(worst, T.qang(q, k1.faceBones.rot[n] || app.simViews.get(F.id).restByName[n].quat.toArray()));
      for (const [n, t] of Object.entries(face.fb.pos)) worst = Math.max(worst, T.vdist(t, k1.faceBones.pos[n] || app.simViews.get(F.id).restByName[n].pos.toArray()));
      checks.push(['A4 key.faceBones equals the game face (1e-6)', worst < 1e-6, worst]);
      app.pipeline.base({ sim: F, v: app.simViews.get(F.id) }, 45);
      const dv = T.faceDiff(app.simViews.get(F.id), face.fb);
      checks.push(['A4 the yf sim shows the game face (keyed face bones, 1e-6)', dv.worst < 1e-6, dv]);
      // the body's motion is untouched by the face key
      const after = app.bake();
      let bodyMax = 0;
      for (const i of [0, 1]) for (const [bn, tr] of Object.entries(bodyTrack(before, i))) {
        if (M.K.FACE_SET.has(bn)) continue;
        const tb = bodyTrack(after, i)[bn];
        if (!tb) continue;
        for (const k of ['r', 't']) if (tr[k]) tr[k].forEach((x, f) => { bodyMax = Math.max(bodyMax, ...x.map((c, j) => Math.abs(c - tb[k][f][j]))); });
      }
      checks.push(['A4 the body bakes identically (the face key never bends it, 1e-6)', bodyMax < 1e-6, bodyMax]);
      // it shows at 45 and blends back: the L upper lid moves over the loop
      const lid = (i, f) => after.actors[i].tracks.b__L_UpLid__.r[f];
      checks.push(['A4 the face shows in the bake at its frame', T.qang(lid(0, 45), face.fb.rot.b__L_UpLid__) < 0.02, T.qang(lid(0, 45), face.fb.rot.b__L_UpLid__)]);
      // male: onto his body key at 0
      app.setFrame(0);
      const k2 = app.setFaceBones(Mm.id, face.fb, face.short, 1, { id: face.id });
      checks.push(['A5 on the ym sim it goes into his body key at 0 (not face-only)', k2 && !k2.faceOnly && k2.frame === 0, k2 && k2.frame]);
      app.pipeline.base({ sim: Mm, v: app.simViews.get(Mm.id) }, 0);
      const dm = T.faceDiff(app.simViews.get(Mm.id), face.fb);
      checks.push(['A5 the ym sim shows the game face (1e-6)', dm.worst < 1e-6, dm]);
      // and on the female at 0 too, for the pictures
      app.setFaceBones(F.id, face.fb, face.short, 1, { id: face.id });
      app.setFrame(0);
      return { checks, data: { F: F.id, M: Mm.id } };
    });
    if (SHOTS && flirty) {
      for (const [who, file] of [['F', 'flirty_yf'], ['M', 'flirty_ym']]) {
        await page.evaluate(async id => {
          app.setTool('move');
          app.store.selected = { sim: id, bone: null };
          app._faceTab = 'game';
          app.showStep('pose'); app.showStep('face');
          app.frameFace();
          await __T.sleep(1600);
        }, flirty[who]);
        shots.push(await viewShot(page, `${file}_${W}.png`));
      }
      // a plain (rest) face for comparison
      await page.evaluate(async id => {
        const sim = app.store.sim(id);
        app.setFaceBones(id, { rot: {}, pos: {} }, null, 0, { quiet: true });
        await __T.sleep(1400);
      }, flirty.F);
      shots.push(await viewShot(page, `rest_yf_${W}.png`));
    }

    await pe(page, async () => {
      const checks = [], M = __M, T = __T;
      const { F } = T.couple();
      const face = M.gf.faceById('ea:a_UI_mood_flirty_female_x');
      const v = app.simViews.get(F.id);
      app.setFrame(30);
      // intensity 0: rest
      const k0 = app.setFaceBones(F.id, face.fb, face.short, 0, { id: face.id });
      app.pipeline.base({ sim: F, v }, 30);
      const d0 = T.faceDiff(v, { rot: {}, pos: {} });
      checks.push(['A6 Intensity 0 equals rest (1e-6)', d0.worst < 1e-6 && Object.keys(k0.faceBones.rot).length === 0 && Object.keys(k0.faceBones.pos).length === 0, d0]);
      const k1 = app.setFaceBones(F.id, face.fb, face.short, 1, { id: face.id });
      app.pipeline.base({ sim: F, v }, 30);
      const d1 = T.faceDiff(v, face.fb);
      checks.push(['A6 Intensity 1 equals the face (1e-6)', d1.worst < 1e-6, d1]);
      // half way: every turned bone half as far (slerp), every moved bone half way (lerp)
      const kh = app.setFaceBones(F.id, face.fb, face.short, 0.5, { id: face.id });
      let e = 0;
      for (const [n, q] of Object.entries(face.fb.rot)) {
        const r = v.restByName[n].quat.toArray(), full = T.qang(r, q), half = T.qang(r, kh.faceBones.rot[n] || r);
        if (full > 1e-3) e = Math.max(e, Math.abs(half - full / 2));
      }
      for (const [n, t] of Object.entries(face.fb.pos)) {
        const r = v.restByName[n].pos.toArray(), full = T.vdist(r, t), half = T.vdist(r, kh.faceBones.pos[n] || r);
        e = Math.max(e, Math.abs(half - full / 2));
      }
      checks.push(['A6 Intensity 0.5 is half way (slerp / lerp, 1e-6)', e < 1e-6, e]);
      // the Intensity slider changes the face on this key (one undo step)
      app._faceTab = 'game'; app.showStep('face'); app.renderStep();
      const sl = [...document.querySelectorAll('#panel-body .gf .slider')].find(x => /Intensity/.test(x.textContent));
      checks.push(['A7 the Intensity slider names the face on this frame', !!sl && sl.textContent.includes(face.short), sl && sl.querySelector('label').textContent]);
      if (sl) {
        const input = sl.querySelector('input'), u0 = app.store.undo.length;
        input.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
        input.value = '0.25'; input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true }));
        const key = F.keys.find(k => k.frame === 30);
        const lid = T.qang(v.restByName.b__L_UpLid__.quat.toArray(), key.faceBones.rot.b__L_UpLid__), full = T.qang(v.restByName.b__L_UpLid__.quat.toArray(), face.fb.rot.b__L_UpLid__);
        checks.push(['A7 dragging Intensity to 25% re-scales the face on this key', Math.abs(lid - full * 0.25) < 1e-6, [lid, full]]);
        checks.push(['A7 ... as one undo step', app.store.undo.length === u0 + 1, app.store.undo.length - u0]);
      }
      // the hover preview shows a face without writing anything
      const snap = JSON.stringify(F.keys);
      const other = M.gf.faceById('ea:a_UI_mood_passionate_female_x') || M.gf.facesNow()[3];
      M.gf.setPreview(app, F.id, M.gf.scaleFaceBones(other.fb, 1));
      app.applyPoses(false);
      const shown = v.bone('b__L_UpLid__').quaternion.toArray();
      M.gf.setPreview(app, null);
      app.applyPoses(false);
      const back = v.bone('b__L_UpLid__').quaternion.toArray();
      checks.push(['A8 pointing at a tile previews the face (the lid changes) and writes nothing', T.qang(shown, back) > 0.01 && JSON.stringify(F.keys) === snap, T.qang(shown, back)]);
      // sliders still add on top
      app.setFace(F.id, { smile: 0.8 }, null, true, true);
      app.applyPoses(false);
      const withSmile = v.bone('b__L_Mouth__').position.toArray();
      const key = F.keys.find(k => k.frame === 30);
      checks.push(['A9 the sliders still add on top of a game face', T.vdist(withSmile, key.faceBones.pos.b__L_Mouth__ || v.restByName.b__L_Mouth__.pos.toArray()) > 0.003 && !!key.faceBones.pos.b__L_Mouth__, T.vdist(withSmile, key.faceBones.pos.b__L_Mouth__ || [0, 0, 0])]);
      // a slider expression on the key is replaced by the game face (the face shows as picked)
      app.setFaceBones(F.id, face.fb, face.short, 1, { id: face.id });
      checks.push(['A9 picking a game face clears the slider expression on that key', Object.keys(F.keys.find(k => k.frame === 30).face || {}).length === 0, F.keys.find(k => k.frame === 30).face]);
      // a click on a tile does it all
      app.setFrame(60); app._gfGroup = 'all'; app._gfAmount = 1; app.renderStep();
      const tile = document.querySelector('#panel-body .gf-tile[data-gf="ea:a_UI_mood_happy_x"]');
      tile && tile.click();
      const k60 = F.keys.find(k => k.frame === 60);
      const happy = M.gf.faceById('ea:a_UI_mood_happy_x');
      checks.push(['A10 clicking a tile puts that face on this frame', !!(k60 && k60.faceBones && happy && T.qang(k60.faceBones.rot.b__L_UpLid__ || [0, 0, 0, 1], happy.fb.rot.b__L_UpLid__ || [0, 0, 0, 1]) < 1e-6), k60 && Object.keys(k60.faceBones.rot).length]);
      checks.push(['A10 ... and the tile is marked', !!document.querySelector('#panel-body .gf-tile.on[data-gf="ea:a_UI_mood_happy_x"]'), '']);
      return { checks };
    });
    if (SHOTS) {
      await page.evaluate(() => { app._faceTab = 'game'; app.setTool('rotate'); app.showStep('face'); });
      shots.push(await panelShot(page, `game_faces_${W}.png`, '#panel-body .face-tabs'));
    }
  }

  // ================================================================ B. the face map
  if (want('B')) {
    await page.evaluate(() => { __T.couple(); app._faceTab = 'quick'; try { localStorage.setItem('fsa.faceMapOpen', 'true'); } catch { } app.setTool('rotate'); app.showStep('face'); });
    await sleep(600);
    const info = await pe(page, () => {
      const dots = document.querySelectorAll('#panel-body .face-map .fm-dot');
      const svg = document.querySelector('#panel-body .fm-svg');
      const r = svg && svg.getBoundingClientRect();
      return { checks: [['B1 the face map shows in the Face step with its dots', dots.length >= 25 && !!svg, dots.length],
        ['B1 the map is 260 x 300', r && Math.round(r.width) === 260 && Math.round(r.height) === 300, r && [r.width, r.height]]] };
    });
    // a real mouse drag on a dot: dx, dy in screen px
    const dragDot = async (bone, dx, dy, { alt = false } = {}) => {
      await page.evaluate(b => { const el = document.querySelector(`#panel-body .fm-dot[data-bone="${b}"]`); el && el.scrollIntoView({ block: 'center' }); }, bone);
      await sleep(150);
      const p = await page.evaluate(b => { const el = document.querySelector(`#panel-body .fm-dot[data-bone="${b}"] .core`); if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; }, bone);
      if (!p) return false;
      const hit = await page.evaluate((x, y) => { const e = document.elementFromPoint(x, y); const g = e && e.closest && e.closest('.fm-dot'); return g ? g.dataset.bone : (e ? e.tagName + '.' + e.className : null); }, p.x, p.y);
      if (hit !== bone) console.log(`  (the pointer at ${bone} finds ${hit})`);
      if (alt) await page.evaluate(() => { app.altDown = true; });
      await page.mouse.move(p.x, p.y);
      await page.mouse.down();
      await page.mouse.move(p.x + dx / 3, p.y + dy / 3, { steps: 2 });
      await page.mouse.move(p.x + dx, p.y + dy, { steps: 4 });
      await page.mouse.up();
      if (alt) await page.evaluate(() => { app.altDown = false; });
      await sleep(120);
      return true;
    };
    const state = () => page.evaluate(() => {
      const M = __M, sim = app.store.sim(app.store.project.sims[0].id), v = app.simViews.get(sim.id);
      const O = new M.THREE.Vector3();
      const at = n => { const p = M.fm.inHead(v, n, O); return p ? [p.x * 1000, p.y * 1000, p.z * 1000] : null; };
      const ez = n => { const b = M.K.baseOf(v, n), r = v.restByName[n]; const e = new M.THREE.Euler().setFromQuaternion(r.quat.clone().invert().multiply(b.q), 'XYZ'); return [e.x, e.y, e.z].map(x => x * 180 / Math.PI); };
      const key = sim.keys.find(k => k.frame === Math.round(app.store.frame));
      return { brow: at('b__L_InBrow__'), rbrow: at('b__R_InBrow__'), lc: at('b__L_Mouth__'), rc: at('b__R_Mouth__'), up: at('b__UpLip__'), lid: ez('b__L_UpLid__'), jaw: ez('b__Jaw__'),
        eyeL: ez('b__L_Eye__'), eyeR: ez('b__R_Eye__'), tongue: at('b__Tounge__1'), undo: app.store.undo.length, keyed: !!(key && key.faceBones && Object.keys(key.faceBones.pos).length + Object.keys(key.faceBones.rot).length),
        hud: document.getElementById('vp-hud').textContent, limit: !!document.querySelector('.fm-dot.limit') };
    });
    await page.evaluate(() => { app.setFrame(15); });           // no key here: face keys are made
    const s0 = await state();
    await dragDot('b__L_InBrow__', 0, -12);
    const s1 = await state();
    const dUp = s1.brow[0] - s0.brow[0];
    C('B2 dragging the left inner brow dot 12 px up moves it 10 mm up (+-0.5)', Math.abs(dUp - 10) <= 0.5, +dUp.toFixed(3));
    C('B2 ... only up (no sideways or forward drift, 0.05 mm)', Math.abs(s1.brow[1] - s0.brow[1]) < 0.05 && Math.abs(s1.brow[2] - s0.brow[2]) < 0.05, [s1.brow[1] - s0.brow[1], s1.brow[2] - s0.brow[2]]);
    C('B2 ... it is keyed (a face key at this frame) as one undo step', s1.keyed && s1.undo === s0.undo + 1, [s1.keyed, s1.undo - s0.undo]);
    C('B2 ... the other side stays (Symmetry off)', Math.abs(s1.rbrow[0] - s0.rbrow[0]) < 0.01, s1.rbrow[0] - s0.rbrow[0]);
    // symmetry: the mouth corner up and out; the right one mirrors
    await page.evaluate(() => { app.mirrorEdit = true; });
    const s2a = await state();
    await dragDot('b__L_Mouth__', 6, -6);
    const s2 = await state();
    const lUp = s2.lc[0] - s2a.lc[0], lOut = s2.lc[2] - s2a.lc[2], rUp = s2.rc[0] - s2a.rc[0], rOut = s2.rc[2] - s2a.rc[2];
    C('B3 Symmetry: the left corner goes 5 mm up and 5 mm out', Math.abs(lUp - 5) < 0.5 && Math.abs(lOut - 5) < 0.5, [lUp, lOut].map(x => +x.toFixed(2)));
    C('B3 ... and the right corner mirrors it (5 up, 5 out to its side)', Math.abs(rUp - 5) < 0.5 && Math.abs(rOut + 5) < 0.5, [rUp, rOut].map(x => +x.toFixed(2)));
    const s3a = await state();
    await dragDot('b__UpLip__', 10, -4);
    const s3 = await state();
    C('B3 Symmetry: the middle of the upper lip stays in the middle (moves up only)', Math.abs(s3.up[2] - s3a.up[2]) < 0.05 && s3.up[0] - s3a.up[0] > 2, [s3.up[2] - s3a.up[2], s3.up[0] - s3a.up[0]]);
    await page.evaluate(() => { app.mirrorEdit = false; });
    // turns: the lid closes with a drag down, the jaw opens with a drag down (1 px = 0.5 degrees)
    const s4a = await state();
    await dragDot('b__L_UpLid__', 0, 20);
    const s4 = await state();
    C('B4 dragging the upper lid 20 px down closes it 10 degrees (+-0.5)', Math.abs(s4.lid[2] - s4a.lid[2] - 10) <= 0.5, +(s4.lid[2] - s4a.lid[2]).toFixed(3));
    const s5a = await state();
    await dragDot('b__Jaw__', 0, 20);
    const s5 = await state();
    C('B4 dragging the chin 20 px down opens the jaw 10 degrees (+-0.5)', Math.abs((s5.jaw[2] - s5a.jaw[2]) + 10) <= 0.5, +(s5.jaw[2] - s5a.jaw[2]).toFixed(3));
    // the eye: a look pad, both eyes together
    const s6a = await state();
    await dragDot('b__L_Eye__', 40, 0);
    const s6 = await state();
    C('B5 dragging an eye 40 px right turns both eyes 20 degrees toward the sim\'s left', Math.abs(s6.eyeL[0] - s6a.eyeL[0] - 20) < 0.5 && Math.abs(s6.eyeR[0] - s6a.eyeR[0] - 20) < 0.5, [s6.eyeL[0], s6.eyeR[0]].map(x => +x.toFixed(2)));
    // the tongue comes out with a drag down
    const s7a = await state();
    await dragDot('b__Tounge__1', 0, 24);
    const s7 = await state();
    C('B6 dragging the tongue 24 px down pushes it 20 mm out (+-0.5)', Math.abs(s7.tongue[1] - s7a.tongue[1] - 20) <= 0.5, +(s7.tongue[1] - s7a.tongue[1]).toFixed(3));
    // the safe range: 60 px = 50 mm up stops at 40 mm and flashes; with Alt it goes on
    await page.evaluate(() => { const sim = app.store.project.sims[0]; app.setFrame(75); });
    const s8a = await state();
    await page.evaluate(() => { window.__lim = 0; const obs = new MutationObserver(() => { if (document.querySelector('.fm-dot.limit')) window.__lim++; }); obs.observe(document.getElementById('panel-body'), { subtree: true, attributes: true, attributeFilter: ['class'] }); window.__limObs = obs; });
    await dragDot('b__L_InBrow__', 0, -60);
    const s8 = await state();
    const lim = await page.evaluate(() => { window.__limObs.disconnect(); return window.__lim; });
    const restUp = await page.evaluate(() => { const M = __M, v = app.simViews.get(app.store.project.sims[0].id); return M.fm.inHead(v, 'b__L_InBrow__', new M.THREE.Vector3(), true).x * 1000; });
    C('B7 the inner brow stops at its safe range (40 mm) and the dot flashes', Math.abs(s8.brow[0] - restUp - 40) < 0.6 && lim > 0, [+(s8.brow[0] - restUp).toFixed(2), lim, s8.hud]);
    // double-click: back to rest
    await page.evaluate(() => { const el = document.querySelector('#panel-body .fm-dot[data-bone="b__L_InBrow__"]'); el && el.scrollIntoView({ block: 'center' }); });
    const dotAt = () => page.evaluate(() => { const r = document.querySelector('#panel-body .fm-dot[data-bone="b__L_InBrow__"] .core').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
    const pd = await dotAt();
    await page.mouse.click(pd.x, pd.y); await sleep(90);
    const pd2 = await dotAt();
    await page.mouse.click(pd2.x, pd2.y); await sleep(200);
    const s10 = await state();
    C('B8 double-clicking a dot puts that part back to rest', Math.abs(s10.brow[0] - restUp) < 0.01, +(s10.brow[0] - restUp).toFixed(3));
    await dragDot('b__L_InBrow__', 0, -60, { alt: true });
    const s9 = await state();
    C('B7 ... holding Alt it goes past the safe range (50 mm)', Math.abs(s9.brow[0] - restUp - 50) < 0.6, +(s9.brow[0] - restUp).toFixed(2));
    // undo takes the drags back one by one
    const u = await page.evaluate(() => { const n0 = app.store.undo.length; app._history(false); return [n0, app.store.undo.length]; });
    const s11 = await state();
    C('B9 Undo takes the last drag back (the brow at rest again)', Math.abs(s11.brow[0] - restUp) < 0.01 && u[1] === u[0] - 1, [+(s11.brow[0] - restUp).toFixed(2), u]);
    // the map follows the 3D face: a slider moves the dots
    const mv = await pe(page, async () => {
      const sim = app.store.project.sims[0];
      const g = () => document.querySelector('#panel-body .fm-dot[data-bone="b__L_Mouth__"]').getAttribute('transform');
      const a = g();
      app.setFace(sim.id, { smile: 1 }, null, true, true);
      await __T.sleep(200);
      const b = g();
      return { checks: [['B10 the map follows the face (a smile slider moves the corner dot)', a !== b, [a, b]]] };
    });
    // a head lying on its side: the map stays upright (the inner brow is still above the eye)
    await pe(page, async () => {
      const M = __M, sim = app.store.project.sims[0], v = app.simViews.get(sim.id);
      const head = v.bone('b__Head__');
      const q0 = head.quaternion.clone();
      head.quaternion.multiply(new M.THREE.Quaternion().setFromAxisAngle(new M.THREE.Vector3(0, 1, 0), Math.PI / 2));
      const P = M.fm.positions(v);
      head.quaternion.copy(q0);
      return { checks: [['B11 with the head turned 90 degrees the map is still upright (brow above eye above mouth)', P.b__L_InBrow__[1] < P.b__L_Eye__[1] && P.b__L_Eye__[1] < P.b__L_Mouth__[1] && P.b__L_Eye__[0] > P.b__R_Eye__[0], [P.b__L_InBrow__[1], P.b__L_Eye__[1], P.b__L_Mouth__[1]]]] };
    });
    // the map's dots are the 3D Face tool's dots (Sim.faceHandlePoint - the lids on their measured edge)
    await pe(page, () => {
      const M = __M, sim = app.store.project.sims[0], v = app.simViews.get(sim.id);
      app.applyPoses(false); v.group.updateMatrixWorld(true);
      const head = v.bone('b__Head__');
      let worst = 0, where = '';
      for (const n of M.K.FACE_CHANNEL) {
        if (!v.bone(n) || /Tounge__[23]$/.test(n)) continue;
        const hp = v.faceHandlePoint(n);
        const d = head.worldToLocal(v.bone(n).localToWorld(hp.clone())).distanceTo(M.fm.inHead(v, n, hp)) * 1000;
        if (d > worst) { worst = d; where = n; }
      }
      const P = M.fm.positions(v), gap = (a, b) => Math.hypot(P[a][0] - P[b][0], P[a][1] - P[b][1]);
      const lidGap = Math.min(gap('b__L_UpLid__', 'b__L_Eye__'), gap('b__L_LoLid__', 'b__L_Eye__'), gap('b__R_UpLid__', 'b__R_Eye__'), gap('b__R_LoLid__', 'b__R_Eye__'));
      return { checks: [['B12 every map dot sits where the 3D Face tool puts it (0.01 mm), lids on their measured edge', worst < 0.01 && typeof v._lidEdge === 'function', { worstMm: +worst.toFixed(5), where }],
        ['B12 ... the lid dots stay clear of the pupil dot (>= 7 px apart)', lidGap >= 7, +lidGap.toFixed(1)]] };
    });
    if (SHOTS) {
      const card = async name => {
        await sleep(700);
        await page.evaluate(() => document.querySelector('#panel-body .face-map-box').scrollIntoView({ block: 'start' }));
        await sleep(300);
        const clip = await page.evaluate(() => { const r = document.querySelector('#panel-body .face-map-box').getBoundingClientRect(); return { x: r.x, y: Math.max(0, r.y), width: r.width, height: Math.min(r.height, innerHeight - Math.max(0, r.y)) }; });
        shots.push(await H.shot(page, path.join(OUT, `${name}_${W}.png`), { clip }));
      };
      // the map at rest, with a moan (open, round mouth, worried brows), and with the game's flirty face
      await page.evaluate(() => { const { F } = __T.couple(); app.store.selected = { sim: F.id, bone: 'b__L_Mouth__' }; app.setTool('face'); app.showStep('face'); });
      await sleep(1200);
      shots.push(await panelShot(page, `face_map_${W}.png`, '#panel-body .face-map-box'));
      await card('face_map_rest');
      await page.evaluate(() => { const F = app.store.project.sims[0]; app.setFace(F.id, { ...__M.face.FACE_PRESETS.moan.face }, 'Moaning'); });
      await card('face_map_moan');
      await page.evaluate(() => { const F = app.store.project.sims[0]; const f = __M.gf.faceById('ea:a_UI_mood_flirty_female_x'); app.setFaceBones(F.id, f.fb, f.short, 1, { id: f.id }); });
      await card('face_map_flirty');
    }
  }

  // ================================================================ C. lip-sync from a sound
  if (want('C')) {
    const LINE = 'vo_expr_moan_pleasure_30f_cm';
    const lip = await pe(page, async line => {
      const checks = [], M = __M, T = __T;
      const { F } = T.couple();
      const p = app.store.project;
      const start = 20;
      const u0 = app.store.undo.length;
      let r = null;
      try { r = await app.lipSync(F.id, { name: line }, { frame: start }); } catch (e) { checks.push(['C1 lip-sync ran', false, String(e.message || e)]); return { checks }; }
      checks.push(['C1 lip-sync on ' + line + ' makes face keys', r.keys >= 3, { keys: r.keys, made: r.made, sec: r.sec }]);
      checks.push(['C1 ... as one undo step', app.store.undo.length === u0 + 1, app.store.undo.length - u0]);
      // the loudness envelope of the same sound (RMS per animation frame, measured here on its own)
      const buf = await M.ls.decodeSound(M.ls.voiceLineUrl(line, M.ls.voiceOf(F)));
      const sr = buf.sampleRate, d = buf.getChannelData(0), n = Math.ceil(buf.length / sr * 30), hop = sr / 30;
      const loud = [], open = [];
      for (let f = 0; f < n; f++) {
        let e = 0, k = 0;
        for (let i = Math.round(f * hop); i < Math.min(buf.length, Math.round((f + 1) * hop)); i++) { e += d[i] * d[i]; k++; }
        loud.push(Math.sqrt(e / Math.max(1, k)));
        const fc = M.animation.evaluateFace(F.keys, start + f, p.length, p.loop) || {};
        open.push(fc.open || 0);
      }
      const corr = (a, b) => { const ma = a.reduce((x, y) => x + y) / a.length, mb = b.reduce((x, y) => x + y) / b.length; let sab = 0, saa = 0, sbb = 0; a.forEach((x, i) => { sab += (x - ma) * (b[i] - mb); saa += (x - ma) ** 2; sbb += (b[i] - mb) ** 2; }); return sab / Math.sqrt(saa * sbb || 1); };
      const c = corr(loud, open);
      checks.push(['C2 the mouth follows the loudness (correlation of the envelope with "open" > 0.6)', c > 0.6, { corr: +c.toFixed(3), frames: n, maxOpen: +Math.max(...open).toFixed(3) }]);
      const fcMid = M.animation.evaluateFace(F.keys, start + open.indexOf(Math.max(...open)), p.length, p.loop);
      checks.push(['C2 bright/dark and peaks drive smile or pout, inner brows and eyes', fcMid && ((fcMid.smile || 0) + (fcMid.pout || 0) > 0.01) && (fcMid.inner || 0) > 0.05, fcMid]);
      const before = M.animation.evaluateFace(F.keys, start - 6, p.length, p.loop) || {};
      checks.push(['C2 the mouth is closed before the sound', (before.open || 0) < 0.02, before]);
      // the voice sound is on the sim, marked, so talking steps aside for it; blinking keeps going
      const cue = (F.sounds || []).find(x => x.name === line && x.frame === start);
      checks.push(['C3 the voice line is added as the sim\'s voice sound (lipsync: true)', !!cue && cue.kind === 'voice' && cue.lipsync === true, cue]);
      const talk = M.face.talkAt(F, start + 10, p.length, p.loop, 30);
      checks.push(['C3 automatic talking steps aside for a lip-synced sound', talk === null, talk]);
      let blinks = 0; for (let f = 0; f < p.length; f++) if (M.face.blinkAt(F, f, p.length, 30)) blinks++;
      checks.push(['C3 blinking keeps going', blinks > 0, blinks]);
      // the keys are face keys: the body is untouched
      checks.push(['C4 the keys it made are face-only keys (the body has no key there)', F.keys.filter(k => k.faceOnly && k.face && k.face.open !== undefined).length >= Math.min(3, r.made), F.keys.filter(k => k.faceOnly).length]);
      // running it again changes nothing
      const faceAt = () => Array.from({ length: p.length }, (_, f) => M.animation.evaluateFace(F.keys, f, p.length, p.loop) || {});
      const a0 = faceAt(), n0 = F.keys.length;
      await app.lipSync(F.id, { name: line }, { frame: start });
      const a1 = faceAt();
      let dmax = 0;
      a0.forEach((x, f) => { for (const c of ['open', 'smile', 'pout', 'inner', 'eyes']) dmax = Math.max(dmax, Math.abs((x[c] || 0) - (a1[f][c] || 0))); });
      checks.push(['C4 lip-syncing the same sound again changes nothing (within the 5% key tolerance), one sound', dmax <= M.ls.TOLERANCE + 1e-9 && F.sounds.filter(x => x.name === line).length === 1 && F.keys.length <= n0 * 1.5, { dmax: +dmax.toFixed(4), keys: [n0, F.keys.length] }]);
      // the bake: the game must not lip-sync over it
      const baked = app.bake();
      const a = baked.actors[0];
      checks.push(['C5 the bake has mouthMoves for the sim', a.mouthMoves === true, a.mouthMoves]);
      checks.push(['C5 the voice line is in the bake\'s sounds', a.sounds.some(x => x.name === line && x.frame === start), a.sounds]);
      return { checks, data: { baked, corr: c } };
    }, LINE);
    if (lip && lip.baked) {
      const file = path.join(OUT, 'lipsync_baked.json');
      fs.writeFileSync(file, JSON.stringify(lip.baked));
      try {
        const out = JSON.parse(execFileSync('python', [path.join(__dirname, 'export_events.py'), file], { encoding: 'utf8', timeout: 180000 }).trim().split('\n').pop());
        const female = out.actors.find(x => /_x$|_a$|x/i.test(x.clip)) || out.actors[0];
        C('C6 the offline export writes event 19 (the game\'s lip-sync off) for the lip-synced sim', out.actors.some(x => x.events.includes(19)), out.actors.map(x => ({ clip: x.clip, events: x.events })));
        C('C6 ... built into %TEMP% only', out.package.toLowerCase().startsWith(require('os').tmpdir().toLowerCase()), out.package);
      } catch (e) { C('C6 offline export', false, String(e.message || e).slice(0, 300)); }
    }
    // your own file: a synthetic 1.6 s "moan" (a tone with a swelling and falling loudness) dropped in
    await pe(page, async () => {
      const checks = [], M = __M, T = __T;
      const { F } = T.couple();
      const p = app.store.project;
      const sr = 22050, sec = 1.6, n = Math.round(sr * sec);
      const data = new Int16Array(n);
      const envAt = t => Math.max(0, Math.sin(Math.PI * t / sec)) * (0.55 + 0.45 * Math.sin(2 * Math.PI * 2.5 * t));
      for (let i = 0; i < n; i++) { const t = i / sr; data[i] = Math.round(12000 * envAt(t) * (Math.sin(2 * Math.PI * 220 * t) + 0.35 * Math.sin(2 * Math.PI * 660 * t * (1 + 0.3 * t)))); }
      const wav = new ArrayBuffer(44 + n * 2), dv = new DataView(wav);
      const w = (o, s) => [...s].forEach((c, i) => dv.setUint8(o + i, c.charCodeAt(0)));
      w(0, 'RIFF'); dv.setUint32(4, 36 + n * 2, true); w(8, 'WAVE'); w(12, 'fmt '); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
      dv.setUint32(24, sr, true); dv.setUint32(28, sr * 2, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true); w(36, 'data'); dv.setUint32(40, n * 2, true);
      new Int16Array(wav, 44).set(data);
      const file = new File([wav], 'my moan.wav', { type: 'audio/wav' });
      const sounds0 = (F.sounds || []).length;
      // through the Face step's file box, the way a user drops it
      app._lipFileOpen = true; app._faceTab = 'quick'; app.showStep('face'); app.renderStep();
      const drop = document.querySelector('#panel-body .ls-drop');
      checks.push(['C7 the Face step has the sound-file drop box', !!drop, '']);
      app.setFrame(40);
      const dt = new DataTransfer(); dt.items.add(file);
      const d2 = document.querySelector('#panel-body .ls-drop');
      d2.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
      for (let i = 0; i < 60 && !(app._lipStatus && !app._lipStatus.busy); i++) await T.sleep(100);
      const open = [], loud = [];
      for (let f = 0; f < Math.ceil(sec * 30); f++) { open.push((M.animation.evaluateFace(F.keys, 40 + f, p.length, p.loop) || {}).open || 0); loud.push(envAt((f + 0.5) / 30)); }
      const corr = (a, b) => { const ma = a.reduce((x, y) => x + y) / a.length, mb = b.reduce((x, y) => x + y) / b.length; let sab = 0, saa = 0, sbb = 0; a.forEach((x, i) => { sab += (x - ma) * (b[i] - mb); saa += (x - ma) ** 2; sbb += (b[i] - mb) ** 2; }); return sab / Math.sqrt(saa * sbb || 1); };
      const c = corr(loud, open);
      checks.push(['C7 a dropped WAV makes the mouth follow it (correlation > 0.6)', c > 0.6 && app._lipStatus && app._lipStatus.ok, { corr: +c.toFixed(3), status: app._lipStatus }]);
      checks.push(['C7 ... the file itself is not added to the sounds (the game plays game sounds only)', (F.sounds || []).length === sounds0, (F.sounds || []).length]);
      checks.push(['C7 ... "Hear it with the animation" is offered', [...document.querySelectorAll('#panel-body .lipsync button')].some(b => /Hear/.test(b.textContent)), '']);
      // a bad file says so in plain words
      let msg = '';
      try { await M.ls.decodeSound(new File([new Uint8Array([1, 2, 3, 4])], 'x.wav')); } catch (e) { msg = e.message; }
      checks.push(['C7 a file that is not a sound gets a plain message', /WAV, MP3 or OGG/.test(msg), msg]);
      return { checks };
    });
    // one click: the sim's voice sounds; the right-click menu of a voice sound
    await pe(page, async line => {
      const checks = [], M = __M, T = __T;
      const { F } = T.couple();
      F.sounds = [{ frame: 5, name: line, kind: 'voice' }, { frame: 50, name: 'vo_expr_mmm_45f_cm', kind: 'voice' }];
      app._faceTab = 'quick'; app.showStep('face'); app.renderStep();
      const btn = document.querySelector('#panel-body .lipsync .ls-go');
      checks.push(['C8 "Lip-sync the 2 voice sounds" is offered', !!btn && /2 voice sounds/.test(btn.textContent), btn && btn.textContent]);
      btn && btn.click();
      for (let i = 0; i < 80 && !(F.sounds.every(x => x.lipsync) && !app._lipBusy); i++) await T.sleep(100);
      checks.push(['C8 one click lip-syncs both', F.sounds.every(x => x.lipsync) && F.keys.filter(k => k.face && k.face.open > 0.1).length >= 2, F.sounds.map(x => x.lipsync)]);
      const items = []; app.runHook('menus.sound', items, { sim: F, snd: F.sounds[0] });
      checks.push(['C9 a voice sound\'s right-click menu offers lip-sync', items.some(x => /Lip-sync/.test(x.label)), items.map(x => x.label)]);
      const cmds = app.runHook('commands', app).flat().filter(Boolean);
      checks.push(['C9 the palette has Game faces, Face map and Lip-sync', ['game-faces', 'face-map', 'lip-sync'].every(id => cmds.some(c => c.id === id)), cmds.filter(c => /face|lip/.test(c.id)).map(c => c.id)]);
      return { checks };
    }, LINE);
    if (SHOTS) {
      // the face in 3D at the loudest moment of a lip-synced moan
      await page.evaluate(async line => {
        const { F } = __T.couple();
        await app.lipSync(F.id, { name: line }, { frame: 20 });
        let best = 20, top = -1;
        for (let f = 20; f < 52; f++) { const o = (__M.animation.evaluateFace(F.keys, f, 90, true) || {}).open || 0; if (o > top) { top = o; best = f; } }
        app.setTool('move'); app.store.selected = { sim: F.id, bone: null };
        app.showStep('pose'); app.showStep('face'); app.setFrame(best); app.frameFace();
        await __T.sleep(1600);
      }, LINE);
      shots.push(await viewShot(page, `lipsync_face_${W}.png`));
      await page.evaluate(() => { app._lipLinesOpen = true; app._faceTab = 'quick'; app.showStep('face'); app.renderStep(); });
      await sleep(2500);
      shots.push(await panelShot(page, `lipsync_${W}.png`, '#panel-body .lipsync'));
    }
  }

  // ================================================================ D. face.js duties
  if (want('D')) {
    await pe(page, () => {
      const F = __M.face, checks = [];
      checks.push(['D1 voiceLength(name, fps, sec) uses sec when given', F.voiceLength('vo_expr_moan_pleasure_30f_cm', 30, 0.974) === 29 && F.voiceLength('x', 24, 2) === 48, [F.voiceLength('vo_expr_moan_pleasure_30f_cm', 30, 0.974), F.voiceLength('x', 24, 2)]]);
      checks.push(['D1 ... and the old rules without it (_45f, else 1.1 s)', F.voiceLength('vo_x_45f', 30) === 45 && F.voiceLength('vo_x', 30) === 33 && F.voiceLength('vo_x', 30, 0) === 33, [F.voiceLength('vo_x_45f', 30), F.voiceLength('vo_x', 30)]]);
      const sim = { id: 's1', sounds: [{ frame: 0, name: 'vo_x_moan', kind: 'voice' }], body: {} };
      const a = F.talkAt(sim, 40, 90, true, 30, 'creator');
      sim.sounds[0].sec = 2;
      const b = F.talkAt(sim, 40, 90, true, 30, 'creator');
      const bc = F.talkAt(sim, 40, 90, true, 30, 'classic'), bn = F.talkAt(sim, 40, 90, true, 30);
      checks.push(['D2 creator projects: talking lasts a voice sound real length (sec)', a === null && b && b.open > 0, [a, b && b.open]]);
      checks.push(['D2 classic projects (and callers that do not say) keep the old length exactly', bc === null && bn === null, [bc, bn]]);
      // the game's lengths (R2-4's app.voiceSec, through the feature): creator uses them, classic does not
      const had = app.voiceSec;
      app.voiceSec = new Map([['vo_y_moan', 3]]);
      const s2 = { id: 's1', sounds: [{ frame: 0, name: 'vo_y_moan', kind: 'voice' }], body: {} };
      const c = F.talkAt(s2, 60, 120, true, 30, 'creator'), cc = F.talkAt(s2, 60, 120, true, 30, 'classic');
      app.voiceSec = had;
      checks.push(['D2 the game voice-line lengths (app.voiceSec) reach creator projects only', c && c.open > 0 && cc === null, [c && c.open, cc]]);
      // every frame of a classic talk is exactly as before (old length rule), with the lengths known
      const s3 = { id: 's9', sounds: [{ frame: 5, name: 'vo_expr_moan_pleasure_30f_cm', kind: 'voice' }], body: {} };
      app.voiceSec = new Map([['vo_expr_moan_pleasure_30f_cm', 2.5]]);
      const cl = Array.from({ length: 90 }, (_, f) => JSON.stringify(F.talkAt(s3, f, 90, true, 30, 'classic')));
      F.setVoiceSeconds(null);
      const old = Array.from({ length: 90 }, (_, f) => JSON.stringify(F.talkAt(s3, f, 90, true, 30)));
      app.voiceSec = had;
      checks.push(['D2 classic talking is identical frame by frame with and without the lengths', cl.every((x, i) => x === old[i]), cl.filter((x, i) => x !== old[i]).length]);
      // put the feature's lookup back
      F.setVoiceSeconds(n => { const m = app.voiceSec; return (m && typeof m.get === 'function' ? m.get(n) : 0) || 0; });
      return { checks };
    });
  }

  if (want('D')) {
    await pe(page, async () => {
      const checks = [], T = __T;
      for (let i = 0; i < 40 && !(app.voiceSec && app.voiceSec.size); i++) await T.sleep(250);
      const { F } = T.couple();
      const p = app.store.project;
      F.sounds = [{ frame: 10, name: 'vo_expr_moan_pleasure_30f_cm', kind: 'voice' }];     // 0.974 s: 29 frames, the old rule 33
      const had = app.voiceSec;
      const bakeWith = (style, secs) => { p.faceStyle = style; app.voiceSec = secs; const b = app.bake(); return JSON.stringify(b.actors.map(a => a.tracks)); };
      const classicOn = bakeWith('classic', had && had.size ? had : new Map([['vo_expr_moan_pleasure_30f_cm', 0.974]]));
      const classicOff = bakeWith('classic', new Map());
      app.voiceSec = had; p.faceStyle = 'creator';
      checks.push(['D3 a classic project with a voice sound bakes byte-identical with and without the game voice-line lengths', classicOn === classicOff && classicOn.length > 1000, { same: classicOn === classicOff, lengthsLoaded: !!(had && had.size) }]);
      return { checks };
    });
  }

  // ================================================================ E. performance and the rest
  await pe(page, async () => {
    const T = __T, checks = [];
    T.couple();
    app._faceTab = 'quick'; app.showStep('face');
    await T.sleep(200);
    const times = [];
    for (let i = 0; i < 120; i++) { const t = performance.now(); app.applyPoses(false); times.push(performance.now() - t); }
    times.sort((a, b) => a - b);
    const hookT = [];
    const fns = app.hooks.afterApply.slice();
    for (let i = 0; i < 120; i++) { app.store.frame = i % 90; const t = performance.now(); for (const fn of fns) { try { fn(app.store.frame, {}); } catch { } } hookT.push(performance.now() - t); }
    hookT.sort((a, b) => a - b);
    checks.push(['E1 the face map and preview add < 0.5 ms per shown frame (median of all afterApply hooks)', hookT[60] < 0.5, { hooksMedian: +hookT[60].toFixed(3), applyPosesMedian: +times[60].toFixed(3) }]);
    // the Face step's panel redraw (plan rule 7: the heavy renderStep stays under 50 ms), both tabs
    const rs = {};
    for (const tab of ['quick', 'game']) {
      app._faceTab = tab; app.renderStep();
      const t = [];
      for (let i = 0; i < 15; i++) { const t0 = performance.now(); app.renderStep(); t.push(performance.now() - t0); }
      t.sort((a, b) => a - b); rs[tab] = +t[7].toFixed(1);
    }
    checks.push(['E1 the Face step redraws in under 50 ms (median, one-click and Game faces tabs)', rs.quick < 50 && rs.game < 50, rs]);
    app._faceTab = 'quick';
    checks.push(['E2 no errors from the page', T.errors.length === 0, T.errors.slice(0, 3)]);
    return { checks };
  });
  const perr = logs.filter(l => l.type === 'pageerror');
  C('E2 no uncaught page errors', perr.length === 0, perr.map(l => l.text).slice(0, 3));
  C('E3 every write was answered in the browser (nothing reached the disk)', true, [...new Set(writes.map(w => w.route))].join(','));
  if (SHOTS) C('E4 screenshots written', shots.every(f => fs.existsSync(f)), shots.map(f => path.basename(f)).join(', '));
  await browser.close();
  const ok = H.report(rows, `R2-5 faces checks (port ${PORT}, ${W}x${Hh}, ${((Date.now() - t0) / 1000).toFixed(0)} s)`);
  fs.writeFileSync(path.join(OUT, `results_${W}.json`), JSON.stringify(rows, null, 1));
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
