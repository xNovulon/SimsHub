// Verifier round 1: targeted checks of the fix wave in headless Chrome against a TEST server (default port 8777).
//   node tools/verify1_ui.js [groups] [width] [height]
// groups: comma list (default all). Screenshots + report.json go to cache/fixwave/verify1/ui/.
// Everything the checks save is named "VERIFY ..." and moved out again at the end (api.removeProject).
const path = require('path'), fs = require('fs');
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');

const PORT = process.env.ANIMATOR_PORT || '8777';
const APP = `http://127.0.0.1:${PORT}/`;
const OUT = path.join(__dirname, '..', 'cache', 'fixwave', 'verify3', 'ui');
const GROUPS = process.argv[2] && process.argv[2] !== 'all' ? new Set(process.argv[2].split(',')) : null;
const W = +(process.argv[3] || 1600), H = +(process.argv[4] || 900);
const results = [], logs = [];
let page, browser, GROUP = 'boot';
const sleep = ms => new Promise(r => setTimeout(r, ms));

function check(name, ok, detail) {
  results.push({ group: GROUP, name, ok: !!ok, detail: detail === undefined ? null : detail });
  const d = detail === undefined ? '' : ' :: ' + JSON.stringify(detail).slice(0, 600);
  console.log(`${ok ? 'PASS' : 'FAIL'} [${GROUP}] ${name}${d}`);
}
async function pe(fn, ...args) {
  const r = await page.evaluate(fn, ...args);
  if (r && Array.isArray(r.checks)) for (const [n, ok, d] of r.checks) check(n, ok, d);
  return r ? r.data : undefined;
}
async function shot(name, clip) {
  const f = path.join(OUT, `${W}x${H}-${name}.png`);
  await page.screenshot({ path: f, clip });
  return f;
}

async function boot({ tourDone = true, intercept = null } = {}) {
  if (page) await page.close().catch(() => {});
  page = await browser.newPage();
  await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
  page.on('console', m => { const t = m.type(); if (t === 'error' || t === 'warning' || t === 'warn') logs.push({ group: GROUP, type: t, text: m.text() }); });
  page.on('pageerror', e => logs.push({ group: GROUP, type: 'pageerror', text: e.message }));
  page.on('response', r => { if (r.status() >= 400) logs.push({ group: GROUP, type: 'http', text: `${r.status()} ${r.request().method()} ${r.url()}` }); });
  page.on('dialog', d => { logs.push({ group: GROUP, type: 'dialog', text: d.message() }); d.dismiss().catch(() => {}); });
  await page.evaluateOnNewDocument(t => { try { if (t) localStorage.setItem('fsa.tourDone', 'true'); else localStorage.removeItem('fsa.tourDone'); localStorage.removeItem('fsa.autosave'); } catch { /* */ } }, tourDone);
  if (intercept) { await page.setRequestInterception(true); page.on('request', intercept); }
  await page.goto(APP, { waitUntil: 'networkidle0', timeout: 180000 });
  await page.waitForSelector('#loading.done', { timeout: 120000 });
  await page.evaluate(async () => {
    window.__m = {
      motion: await import('/js/motion.js'), animation: await import('/js/animation.js'), share: await import('/js/share.js'),
      api: (await import('/js/api.js')).api, face: await import('/js/face.js'), physics: await import('/js/physics.js'),
      pipeline: await import('/js/pipeline.js'), state: await import('/js/state.js'), posemath: await import('/js/posemath.js'),
      bones: await import('/js/bones.js'), ui: await import('/js/ui.js'),
    };
    const E = window.__v = {};
    E.sleep = ms => new Promise(r => setTimeout(r, ms));
    E.waitFor = async (fn, ms = 8000) => { const t0 = performance.now(); while (performance.now() - t0 < ms) { try { const v = await fn(); if (v) return v; } catch { /* */ } await E.sleep(40); } return null; };
    E.V = (x = 0, y = 0, z = 0) => app.vp.camera.position.clone().set(x, y, z);
    E.F = () => app.store.project.sims.find(s => s.frame === 'yf');
    E.M = () => app.store.project.sims.find(s => s.frame === 'ym');
    E.view = s => app.simViews.get(s.id);
    E.wp = (s, bone) => { const v = app.simViews.get(s.id); v.group.updateMatrixWorld(true); return v.worldPos(bone).toArray(); };
    E.dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
    E.qang = (a, b) => { const d = Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]) / (Math.hypot(...a) || 1) / (Math.hypot(...b) || 1); return 2 * Math.acos(Math.min(1, d)) * 180 / Math.PI; };
    E.badBones = () => { const out = []; for (const [, v] of app.simViews) for (const b of v.bones) { const a = b.position.toArray().concat(b.quaternion.toArray()); if (!a.every(Number.isFinite)) out.push(b.name); } return out; };
    E.btn = (text, root = document) => [...root.querySelectorAll('button')].find(b => b.textContent.trim().includes(text));
    E.modal = title => [...document.querySelectorAll('#modal-root .modal')].find(m => !title || (m.querySelector('h2')?.textContent || '').includes(title)) || null;
    E.modalBtn = (title, label) => { const m = E.modal(title); return m ? [...m.querySelectorAll('footer button')].find(b => b.textContent.trim().includes(label)) : null; };
    E.closeModals = () => { for (const b of [...document.querySelectorAll('#modal-root .backdrop')]) b.remove(); };
    E.toasts = [];
    new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) if (n.classList && n.classList.contains('toast')) E.toasts.push(n.textContent); }).observe(document.getElementById('toasts'), { childList: true });
    E.couple = (presetId = 'cowgirl') => {
      const p = app.store.project;
      app.setPlaying(false);
      app.vp.gizmo.detach(); app.interact.active = null; app.pipeline.editing = null;
      let F = p.sims.find(s => s.frame === 'yf'), M = p.sims.find(s => s.frame === 'ym');
      if (!F) { F = __m.state.newSim(p, 'yf'); p.sims.push(F); }
      if (!M) { M = __m.state.newSim(p, 'ym'); p.sims.push(M); }
      p.sims = [F, M];
      for (const s of p.sims) { s.layers = []; s.sounds = []; s.pins = {}; s.keys = []; s.body = undefined; s.visible = true; }
      p.length = 90; p.loop = true; p.fps = 30;
      app.store.undo.length = 0; app.store.redo.length = 0;
      app.store.frame = 0;
      app.store.selected = { sim: F.id, bone: null };
      app.syncViews();
      if (presetId) app.applyPosePreset(app.posePresets.find(x => x.id === presetId));
      app.pipeline.overrides.clear();
      app.setFrame(0);
      return { F, M };
    };
  });
}

const groups = {};

// ---------------------------------------------------------------- engine findings
groups.engine = async () => {
  await pe(async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const E = __v, A = __m.animation;
    // C0: thrust/grind groin travel along the stroke equals the distance, no sideways drift
    {
      const { F, M } = E.couple('cowgirl');
      const measure = (sim, type, params = {}) => {
        const s = sim; s.layers = [];
        app.addLayer(s.id, type); app.setPlaying(false);
        const l = s.layers[s.layers.length - 1]; Object.assign(l.params, params);
        app.layersChanged && app.layersChanged();
        const v = E.view(s); const pts = [];
        for (let f = 0; f < 90; f++) { app.pipeline.apply(f, { physics: false }); v.group.updateMatrixWorld(true); pts.push(v.worldPos(v.bone('b__Penis_Base') ? 'b__Penis_Base' : 'b__Pelvis__').toArray()); }
        s.layers = []; app.layersChanged && app.layersChanged();
        let best = 0; for (const a of pts) for (const b of pts) best = Math.max(best, E.dist(a, b));
        return { travel_cm: +(best * 100).toFixed(2), dist: l.params.distance ?? l.params.depth ?? null, params: { ...l.params } };
      };
      const th = measure(M, 'thrust');
      C('C0 Thrust: the groin travels about the Distance (>= 85%)', th.dist == null ? th.travel_cm > 3.5 : th.travel_cm >= 0.85 * th.dist, th);
      const gr = measure(M, 'grind');
      C('C0 Grind: groin travel is positive and <= its distance + 20%', gr.travel_cm > 0.5 && (gr.dist == null || gr.travel_cm <= gr.dist * 1.2 + 0.2), gr);
    }
    // C2: a pending (unkeyed) pose is not baked
    {
      const { F } = E.couple('cowgirl');
      app.autoKey = false;
      app.selectSim(F.id); app.setFrame(30);
      app.beginEdit(F.id);
      const v = E.view(F); v.bone('b__Head__').rotateY(0.6); app.poseEdited(F.id);
      const pending = app.pipeline.overrides.has(F.id);
      const b = app.bake();
      const i = app.store.project.sims.indexOf(F);
      const r = b.actors[i].tracks['b__Head__'] && b.actors[i].tracks['b__Head__'].r;
      const jump = r ? E.qang(r[29], r[30]) : null;
      C('C2 pending pose is pending (not keyed)', pending && !F.keys.some(k => k.frame === 30));
      C('C2 the pending head turn is not in the bake (frame 29->30 jump < 1 deg)', jump !== null && jump < 1, jump);
      C('C2 the pending pose is still shown while paused', app.pipeline.overrides.has(F.id));
      app.pipeline.overrides.clear(); app.autoKey = true;
    }
    // C3: keys past the end are ignored
    {
      const { F } = E.couple('cowgirl');
      const v = E.view(F);
      const k0 = F.keys[0];
      const other = JSON.parse(JSON.stringify(k0)); other.frame = 60; other.pose.rot['b__Head__'] = [0, 0.5, 0, 0.866];
      const keys = [k0, other];
      const e44 = A.evaluate(keys, 44, 45, true), e0 = A.evaluate(keys, 0, 45, true);
      C('C3 frame 44 of a 45-frame loop equals key 0 (key at 60 ignored)', e44 && E.qang(e44.rot['b__Head__'], e0.rot['b__Head__']) < 0.01, e44 && E.qang(e44.rot['b__Head__'], e0.rot['b__Head__']));
    }
    // C6: a bone missing from one key blends through rest instead of snapping
    {
      const pa = { rot: { b__Head__: [0, 0.3827, 0, 0.9239] }, pos: {} }, pb = { rot: {}, pos: {} };
      const mid = A.blendPoses(pa, pb, 0.5);
      const ang = mid.rot && mid.rot.b__Head__ ? E.qang(mid.rot.b__Head__, [0, 0, 0, 1]) : null;
      C('C6 blendPoses: a bone only in key A is halfway to rest at t=0.5 (union of bones)', ang !== null && ang > 15 && ang < 30, { ang, mid: mid.rot && mid.rot.b__Head__ });
      const mid2 = A.blendPoses(pb, pa, 0.5);
      const ang2 = mid2.rot && mid2.rot.b__Head__ ? E.qang(mid2.rot.b__Head__, [0, 0, 0, 1]) : null;
      C('C6 blendPoses: a bone only in key B also blends (not stuck at rest)', ang2 !== null && ang2 > 15 && ang2 < 30, ang2);
    }
    // C7: negative eyes (Surprised) survive a word voice
    {
      const { F } = E.couple('cowgirl');
      const sur = __m.face.FACE_PRESETS.surprised || Object.values(__m.face.FACE_PRESETS).find(f => (f.face || {}).eyes < 0);
      app.setFace(F.id, { ...(sur.face || sur) }, 'Surprised');
      const base = { ...(sur.face || sur) };
      const word = ((app.sounds || []).find(s => s.kind === 'voice' && /_FA$/.test(s.name) && !/moan|sigh|breath|pant|gasp/i.test(s.name)) || { name: 'vo_cas_talk_generic_FA' }).name;
      const talk = __m.face.talkAt({ ...F, sounds: [{ frame: 10, name: word, kind: 'voice' }] }, 16, 90, true, 30);
      const merged = __m.face.mergeFace({ ...base }, talk);
      C('C7 mergeFace keeps negative eyes while talking', merged.eyes <= base.eyes + 0.05, { base: base.eyes, talk, merged: merged.eyes });
    }
    // C8: physics after lengthening before re-simulation
    {
      const { F, M } = E.couple('cowgirl');
      app.addLayer(M.id, 'thrust'); app.setPlaying(false);
      app.pipeline.simulateIfNeeded && app.pipeline.simulateIfNeeded(true);
      await E.sleep(600);
      app.store.project.length = 150;
      let bad = [];
      for (const f of [100, 120, 149]) { app.pipeline.apply(f, { physics: true }); bad = bad.concat(E.badBones()); }
      C('C8 frames past the old length give no NaN bones before re-simulation', bad.length === 0, bad.slice(0, 5));
      app.store.project.length = 90; app.physicsChanged();
    }
    // E4 is in e2e; C22 GPU leaks: scrub with ghosts on
    {
      const { F } = E.couple('cowgirl');
      app.setFrame(45); app.keyPose(); app.setFrame(0);
      app.onion = true;
      const info = app.vp.renderer.info.memory;
      for (let i = 0; i < 5; i++) { app.setFrame(i * 7 % 90); app.updateGhosts(); app.vp.render && app.vp.render(); }
      const t0 = info.textures, g0 = info.geometries;
      for (let i = 0; i < 40; i++) { app.setFrame((i * 3) % 90); app.updateGhosts(); app.vp.render && app.vp.render(); }
      const t1 = info.textures, g1 = info.geometries;
      C('C22 scrubbing 40 frames with ghosts: textures and geometries stay flat', t1 - t0 <= 1 && g1 - g0 <= 2, { t0, t1, g0, g1 });
      app.onion = false; app.updateGhosts();
      // furniture switching
      const gA = info.geometries;
      for (const id of ['double_bed', 'sofa', 'floor', 'double_bed', 'sofa', 'floor', 'chair_dining', 'floor']) { app.setFurniture(id); await E.sleep(30); }
      await E.sleep(400);
      const gB = info.geometries;
      C('C22 switching furniture 8 times does not pile up geometries', gB - gA <= 6, { gA, gB });
      // handle refreshes with a pin
      app.setTool('ik');
      app.interact.togglePin(F.id, 'R hand');
      const h0 = info.geometries;
      for (let i = 0; i < 10; i++) app.interact.refreshHandles();
      const h1 = info.geometries;
      C('C22 10 handle refreshes with a pin keep geometries flat', h1 - h0 <= 2, { h0, h1 });
      app.interact.togglePin(F.id, 'R hand');
      app.setTool('rotate');
    }
    return { checks: out };
  });
};

// C1 gizmo during playback, C4 place moves every key, C5 pinned hand stroke bake
groups.interact = async () => {
  await pe(async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const E = __v, it = app.interact, gz = app.vp.gizmo;
    // C1
    {
      const { F } = E.couple('cowgirl');
      const n0 = F.keys.length;
      app.setTool('rotate');
      app.setPlaying(true);
      await E.sleep(200);
      it.selectBone(F.id, 'b__Head__');
      const stoppedBySelect = !app.playing;
      if (!stoppedBySelect) { /* the safety net: mouseDown stops it */ }
      gz.dispatchEvent({ type: 'mouseDown' });
      const stopped = !app.playing;
      for (let i = 0; i < 20; i++) { app._tick && app._tick(); E.view(F).bone('b__Head__').rotateY(0.01); gz.dispatchEvent({ type: 'objectChange' }); await E.sleep(16); }
      gz.dispatchEvent({ type: 'mouseUp' });
      C('C1 picking a bone while playing pauses playback', stoppedBySelect && stopped);
      C('C1 a gizmo drag during playback writes at most one key', F.keys.length - n0 <= 1, { before: n0, after: F.keys.length, frames: F.keys.map(k => k.frame) });
    }
    // C4 place tool moves every key
    {
      const { F } = E.couple('cowgirl');
      app.setFrame(45); app.keyPose(); app.setFrame(0);
      const hip = f => { app.setFrame(f); app.pipeline.apply(f, { physics: false }); return E.wp(F, 'b__Pelvis__'); };
      const a0 = hip(0), a45 = hip(45);
      app.setTool('move');
      it.selectPlace(F.id, 'translate');
      gz.dispatchEvent({ type: 'mouseDown' });
      it.proxy.position.x += 0.4; gz.dispatchEvent({ type: 'objectChange' });
      gz.dispatchEvent({ type: 'mouseUp' });
      const b0 = hip(0), b45 = hip(45);
      C('C4 Place move at frame 0 moves key 0 by 40 cm', Math.abs(E.dist(a0, b0) - 0.4) < 0.01, E.dist(a0, b0));
      C('C4 ... and key 45 by 40 cm too', Math.abs(E.dist(a45, b45) - 0.4) < 0.01, E.dist(a45, b45));
      C('C4 no extra key written by Place', F.keys.map(k => k.frame).join() === '0,45', F.keys.map(k => k.frame));
      // turn
      it.selectPlace(F.id, 'rotate');
      gz.dispatchEvent({ type: 'mouseDown' });
      it.proxy.quaternion.setFromAxisAngle(E.V(0, 1, 0), Math.PI / 2); gz.dispatchEvent({ type: 'objectChange' });
      gz.dispatchEvent({ type: 'mouseUp' });
      const fwd = f => { app.setFrame(f); app.pipeline.apply(f, { physics: false }); const v = E.view(F); v.group.updateMatrixWorld(true); const q = v.bone('b__Pelvis__').getWorldQuaternion(v.bone('b__Pelvis__').quaternion.clone()); const d = E.V(0, 1, 0).applyQuaternion(q); return Math.atan2(d.x, d.z) * 180 / Math.PI; };
      const t0 = fwd(0), t45 = fwd(45);
      app.store.undoStep(); const u0 = fwd(0), u45 = fwd(45);
      let turned0 = ((t0 - u0 + 540) % 360) - 180, turned45 = ((t45 - u45 + 540) % 360) - 180;
      C('C4 Place turn 90 deg turns key 0 and key 45 alike', Math.abs(Math.abs(turned0) - 90) < 2 && Math.abs(Math.abs(turned45) - 90) < 2, { turned0, turned45 });
      app.setTool('rotate');
    }
    // C5 pinned hand + Hand stroke, then Turn into keys
    {
      const { F, M } = E.couple('handjob');
      app.selectSim(F.id);
      app.setTool('ik');
      it.togglePin(F.id, 'R hand');
      app.addLayer(F.id, 'stroke'); app.setPlaying(false);
      const l = F.layers[F.layers.length - 1];
      const path = () => { const pts = []; for (let f = 0; f < 90; f += 3) { app.pipeline.apply(f, { physics: false }); pts.push(E.wp(F, 'b__R_Hand__')); } return pts; };
      const live = path();
      let amp = 0; for (const a of live) for (const b of live) amp = Math.max(amp, E.dist(a, b));
      app.bakeLayer(F.id, l.id);
      const baked = path();
      let err = 0; live.forEach((p, i) => { err = Math.max(err, E.dist(p, baked[i])); });
      C('C5 pinned hand stroke survives Turn into keys (error < 5 mm)', amp > 0.02 && err < 0.005, { amp_cm: +(amp * 100).toFixed(2), maxErr_cm: +(err * 100).toFixed(2), pinsLeft: Object.keys(F.pins || {}) });
      app.setTool('rotate');
    }
    // E1 mirror keeps a turned sim facing its partner
    {
      app.newScene(false, false, 'couple');
      const F = E.F();
      const v = E.view(F);
      const fw = () => { v.group.updateMatrixWorld(true); const q = v.bone('b__Pelvis__').getWorldQuaternion(v.bone('b__Pelvis__').quaternion.clone()); return E.V(0, 1, 0).applyQuaternion(q).toArray(); };
      app.pipeline.apply(0, { physics: false });
      const before = fw();
      app.mirrorPose(F.id);
      app.pipeline.apply(0, { physics: false });
      const after = fw();
      const dot = before[0] * after[0] + before[1] * after[1] + before[2] * after[2];
      C('E1 mirroring the standing (turned) woman keeps her facing (dot > 0.95)', dot > 0.95, { before, after, dot });
    }
    return { checks: out };
  });
};

// E9 voices, E10 retime, C15 undo length, C19 undo buttons, C21 undo add sim, C23 motion header
groups.edit = async () => {
  await pe(async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const E = __v;
    await E.waitFor(() => app.sounds && app.sounds.length, 20000);
    const { F, M } = E.couple('cowgirl');
    // E9
    const sets = ['any', 'moan', 'moan_soft', 'breath'];
    const fem = new Set(), mal = new Set();
    for (const k of sets) { app.voicePool(F, k).forEach(x => fem.add(x.name)); app.voicePool(M, k).forEach(x => mal.add(x.name)); }
    C('E9 female voice pool only has _FA lines', [...fem].every(n => /_FA$/i.test(n)), [...fem].slice(0, 10));
    C('E9 male voice pool only has _MA lines', [...mal].every(n => /_MA$/i.test(n)), [...mal].slice(0, 10));
    C('E9 no child/other-age voice lines offered', ![...fem, ...mal].some(n => /_(FC|MC|CA|C\w?)$/i.test(n)), null);
    const kinds = app.voiceSets(F);
    C('E8 the Kind list only shows kinds with lines (counts > 0)', kinds.length > 0 && kinds.every(k => k[2] > 0), kinds);
    // E10 retime stretch 90 -> 180
    {
      const { F, M } = E.couple('cowgirl');
      app.setFrame(45); app.keyPose(); app.setFrame(89); app.keyPose(); app.setFrame(0);
      F.sounds = [{ frame: 30, name: 'clapPlaps_Normal', kind: 'clap' }];
      app.setLength(180, 'stretch');
      const keys = F.keys.map(k => k.frame), snd = F.sounds.map(s => s.frame);
      C('E10 stretch 90->180: keys 0/45/89 -> 0/90/179', keys.join() === '0,90,179', keys);
      C('E10 stretch: sound frame doubles (30 -> 60)', snd.join() === '60', snd);
      let nan = 0; for (let f = 0; f < 180; f += 5) { app.pipeline.apply(f, { physics: false }); nan += E.badBones().length; }
      C('E10 stretched animation: no NaN bones', nan === 0, nan);
      C('C19 Undo button enabled after changing the length', !document.getElementById('btn-undo').disabled);
      app.store.undoStep();
      C('E10 Undo restores 90 frames and keys', app.store.project.length === 90 && E.F().keys.map(k => k.frame).join() === '0,45,89', [app.store.project.length, E.F().keys.map(k => k.frame)]);
      // keep speed 90 -> 45
      app.addLayer(E.M().id, 'thrust'); app.setPlaying(false);
      const st0 = E.M().layers[0].params.strokes ?? __m.motion.MOTIONS.thrust.params.strokes;
      E.F().sounds = [{ frame: 70, name: 'clapPlaps_Normal', kind: 'clap' }];
      app.setLength(45, 'keep');
      const k2 = E.F().keys.map(k => k.frame);
      C('E10 keep speed 90->45: keys end at 44 (last pose moved), no key past the end', k2.every(f => f < 45) && k2.includes(44), k2);
      C('E10 keep speed: the sound past the end is removed', E.F().sounds.length === 0, E.F().sounds);
      C('E10 keep speed: strokes halve', E.M().layers[0].params.strokes === Math.max(1, Math.round(st0 / 2)), [st0, E.M().layers[0].params.strokes]);
      __m.ui.closeChoiceBar && __m.ui.closeChoiceBar();
    }
    // C15 undo length clamps playhead
    {
      E.couple('cowgirl');
      app.setLength(300, 'stretch'); __m.ui.closeChoiceBar && __m.ui.closeChoiceBar();
      app.setFrame(250);
      app.store.undoStep();
      const fr = app.store.frame, shown = document.getElementById('tl-frame').textContent;
      C('C15 undoing a length change clamps the playhead into the loop', app.store.project.length === 90 && fr <= 89, { len: app.store.project.length, frame: fr, shown });
      C('C15 ... and the frame counter shows it', String(shown).includes(String(Math.round(fr))) || +shown === Math.round(fr), shown);
    }
    // C21 undo add sim
    {
      E.couple('cowgirl');
      app.addSim('yf');
      app.store.undoStep();
      C('C21 after undoing "add sim" a real sim is selected', !!app.store.sim(), app.store.selected);
    }
    // C19 undo button after a face change
    {
      E.couple('cowgirl');
      app.store.undo.length = 0; app.refreshPanels && app.refreshPanels();
      app.setFace(E.F().id, { smile: 0.5 }, 'Smile');
      await E.sleep(50);
      C('C19 Undo button enabled after a face change', !document.getElementById('btn-undo').disabled);
    }
    // C23 motion card header/wave follow the slider
    {
      const { M } = E.couple('cowgirl');
      app.selectSim(M.id);
      app.showStep('motion'); await E.sleep(100);
      app.addLayer(M.id, 'thrust'); app.setPlaying(false); await E.sleep(150);
      const card = document.querySelector('#panel-body .layer.open') || document.querySelector('#panel-body .layer');
      const sl = card && [...card.querySelectorAll('.slider')].find(s => /times per loop/i.test(s.querySelector('label')?.textContent || ''));
      const input = sl && sl.querySelector('input');
      const head0 = card && card.querySelector('.layer-head small')?.textContent;
      if (input) { input.value = 12; input.dispatchEvent(new Event('input', { bubbles: true })); }
      await E.sleep(60);
      const card2 = document.querySelector('#panel-body .layer.open') || document.querySelector('#panel-body .layer');
      const head1 = card2 && card2.querySelector('.layer-head small')?.textContent;
      C('C23 motion card header follows "Times per loop"', !!input && /12/.test(head1 || '') && head0 !== head1, { head0, head1 });
      // C46 the new motion card is scrolled into view
      const body = document.getElementById('panel-body');
      app.addLayer(M.id, 'headbob'); app.setPlaying(false);
      await E.sleep(700);
      const open = document.querySelector('#panel-body .layer.open');
      const r = open && open.getBoundingClientRect(), br = body.getBoundingClientRect();
      const sliderVisible = open && [...open.querySelectorAll('input[type=range]')].some(s => { const q = s.getBoundingClientRect(); return q.top >= br.top && q.bottom <= br.bottom; });
      C('C46 a new motion card is scrolled so its sliders show', !!open && sliderVisible, r && { top: r.top, bodyTop: br.top, bodyBottom: br.bottom });
    }
    return { checks: out };
  });
};

// dialogs / keyboard: C11, C13, C14, C16, C18, C20, C44, C49, C50, E13-part, contract
groups.dialogs = async () => {
  const api = () => page.evaluate(() => 0);
  await pe(async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const E = __v, api = __m.api;
    // C16 Skip for now
    {
      app.store.setDirty(false);
      app.showStep('home'); await E.sleep(700);
      const uidBefore = app.store.project.uid;
      [...document.querySelectorAll('#home .start')].find(b => /Woman & man/.test(b.textContent)).click();
      await E.sleep(250);
      const skip = E.modalBtn('New animation', 'Skip');
      skip && skip.click();
      await E.sleep(250);
      C('C16 "Skip for now" starts the new animation and leaves Home', !!skip && app.store.project.uid !== uidBefore && document.getElementById('home').classList.contains('hidden'), { skip: !!skip, same: app.store.project.uid === uidBefore });
    }
    // C44 no literal null in Details
    app.showStep('details'); await E.sleep(100);
    C('C44 Details shows no literal "null"', !/\bnull\b/.test(document.getElementById('panel-body').textContent));
    // C18: Send to game + Enter -> one dialog; Escape closes only top
    {
      E.closeModals(); if (!document.getElementById('home').classList.contains('hidden')) document.querySelector('#home .btn.primary')?.click();
      E.couple('cowgirl');
      app.store.project.name = 'VERIFY Dlg'; app.store.project.author = 'Verifier';
      document.getElementById('btn-export').focus();
      document.getElementById('btn-export').click();
      await E.sleep(150);
      const n1 = document.querySelectorAll('#modal-root .backdrop').length;
      const ae = document.activeElement;
      C('C18 the dialog takes focus', ae && !!ae.closest('#modal-root'), ae && ae.outerHTML.slice(0, 80));
      document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
      await E.sleep(80);
      C('C18 one Send-to-game dialog and Escape closes it', n1 === 1 && document.querySelectorAll('#modal-root .backdrop').length === 0, n1);
      // stacked: confirm over Open dialog
      app.open(); await E.sleep(400);
      __m.ui.confirmBox('Stacked?', 'x', 'OK');
      await E.sleep(80);
      document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
      await E.sleep(80);
      const left = document.querySelectorAll('#modal-root .backdrop').length;
      C('C18 Escape closes only the top dialog', left === 1, left);
      E.closeModals();
      // Home + Open... + Escape keeps Home
      app.showStep('home'); await E.sleep(600);
      app.open(); await E.sleep(500);
      document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
      await E.sleep(80);
      C('C18 on Home, Escape closes the Open dialog but Home stays', !document.getElementById('home').classList.contains('hidden') && !document.querySelector('#modal-root .backdrop'));
      E.closeModals();
      document.querySelector('#home .btn.primary')?.click();
    }
    // C14 Home right-click Open asks when dirty
    {
      // a test server with an empty saves folder has no card to right-click: save one first (removed at cleanup)
      await __m.api.saveProject({ uid: 'aVERIFYc14', name: 'VERIFY C14 other', author: 'Verifier', length: 30, fps: 30, sims: [], category: 'VAGINAL' });
      E.couple('cowgirl'); app.store.setDirty(true);
      app.showStep('home'); await E.sleep(900);
      const card = [...document.querySelectorAll('#home .proj')].find(c => /VERIFY C14 other/.test(c.textContent)) || document.querySelector('#home .proj');
      card && card.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, clientX: 300, clientY: 700 }));
      await E.sleep(100);
      const item = [...document.querySelectorAll('.ctx-menu button, .menu button, .context-menu button, [class*=menu] button')].find(b => /^open$/i.test(b.textContent.trim()));
      item && item.click();
      await E.sleep(150);
      const asked = !!E.modal('Open another');
      C('C14 right-click -> Open asks before dropping unsaved work', !!card && !!item && asked, { card: !!card, item: !!item, modals: [...document.querySelectorAll('#modal-root h2')].map(x => x.textContent) });
      E.closeModals(); document.querySelector('#home .btn.primary')?.click();
      app.store.setDirty(false);
    }
    // C20 select gives keyboard back; Ctrl+S in a text box saves (not the browser dialog)
    {
      E.couple('cowgirl');
      const sel = document.getElementById('ease-select');
      if (sel) { sel.focus(); sel.value = sel.options[1].value; sel.dispatchEvent(new Event('change', { bubbles: true })); }
      await E.sleep(30);
      C('C20 the ease box gives the keyboard back after a change', !sel || document.activeElement !== sel, document.activeElement && document.activeElement.id);
      app.showStep('details'); await E.sleep(100);
      const inp = document.querySelector('#panel-body input.text');
      inp.focus();
      let called = 0; const orig = app.save; app.save = async () => { called++; return true; };
      const ev = new KeyboardEvent('keydown', { key: 's', code: 'KeyS', ctrlKey: true, bubbles: true, cancelable: true });
      inp.dispatchEvent(ev);
      await E.sleep(50);
      app.save = orig;
      C('C20 Ctrl+S while typing saves and blocks the browser dialog', called === 1 && ev.defaultPrevented, { called, prevented: ev.defaultPrevented });
      inp.blur();
      // WASD on Home
      app.showStep('home'); await E.sleep(150);
      const cam0 = app.vp.camera.position.toArray();
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'w', code: 'KeyW', bubbles: true }));
      await E.sleep(400);
      window.dispatchEvent(new KeyboardEvent('keyup', { key: 'w', code: 'KeyW', bubbles: true }));
      const moved = E.dist(cam0, app.vp.camera.position.toArray());
      C('C20 holding W on Home does not move the hidden camera', moved < 1e-4, moved);
      document.querySelector('#home .btn.primary')?.click();
    }
    // C50 opening Export mod does not save
    {
      E.couple('cowgirl'); app.store.project.name = 'Untitled animation'; app.store.project.uid = __m.state.uid('a'); app.store.setDirty(true);
      const n0 = (await api.projects()).length;
      document.getElementById('btn-share').click();
      await E.sleep(800);
      const n1 = (await api.projects()).length;
      C('C50 opening Export mod saves nothing', n0 === n1 && !!E.modal('Export'), { n0, n1 });
      E.closeModals();
      app.store.setDirty(false);
    }
    // C11: name clash asks; Replace vs server
    {
      E.couple('cowgirl');
      const p = app.store.project;
      p.name = 'VERIFY Clash'; p.author = 'Verifier'; p.uid = __m.state.uid('a');
      const first = p.uid;
      await app.save();
      p.uid = __m.state.uid('a');
      const second = p.uid;
      const saving = app.save();
      const dlg = await E.waitFor(() => E.modal('already used'), 3000);
      const labels = dlg ? [...dlg.querySelectorAll('footer button')].map(b => b.textContent.trim()) : [];
      C('C11 saving over a different animation with the same name asks first', !!dlg && labels.some(l => /Save as/.test(l)) && labels.some(l => /Replace/.test(l)), labels);
      const primary = dlg && dlg.querySelector('footer button.primary');
      C('C11 the main button is not the destructive one', primary && !/Replace/.test(primary.textContent), primary && primary.textContent);
      // pick Replace it
      const rep = dlg && [...dlg.querySelectorAll('footer button')].find(b => /Replace/.test(b.textContent));
      rep && rep.click();
      await saving;
      const list = (await api.projects()).filter(m => /^VERIFY Clash/.test(m.name));
      C('C11 "Replace it" replaces the other animation (one "VERIFY Clash" left, the new uid)', list.length === 1 && list[0].uid === second, list.map(m => ({ name: m.name, file: m.file, uid: m.uid === first ? 'first' : m.uid === second ? 'second' : m.uid })));
      C('C11 the toast says where it went', E.toasts.slice(-2).some(t => /VERIFY Clash/.test(t)), E.toasts.slice(-3));
      // Save as "Name 2"
      p.uid = __m.state.uid('a'); p.name = 'VERIFY Clash';
      const saving2 = app.save();
      const dlg2 = await E.waitFor(() => E.modal('already used'), 3000);
      const ren = dlg2 && dlg2.querySelector('footer button.primary');
      ren && ren.click();
      await saving2;
      C('C11 "Save as" renames the open animation', /^VERIFY Clash \d/.test(app.store.project.name), app.store.project.name);
      // server free name when the UI check is skipped (name with punctuation the UI strips)
      const X = { ...JSON.parse(JSON.stringify(p)), uid: __m.state.uid('a'), name: 'VERIFY Kiss!' }; delete X.thumb;
      const Y = { ...X, uid: __m.state.uid('a') };
      const rx = await api.saveProject(X), ry = await api.saveProject(Y);
      C('C27 server keeps both "VERIFY Kiss!" saves (free name for the second)', rx.file !== ry.file && ry.renamed === true, { rx, ry });
      // UI clash check for a punctuated name
      app.store.load({ ...JSON.parse(JSON.stringify(p)), uid: __m.state.uid('a'), name: 'VERIFY Kiss!' });
      const saving3 = app.save();
      const dlg3 = await E.waitFor(() => E.modal('already used'), 2500);
      if (dlg3) dlg3.querySelector('footer button')?.click();
      await saving3;
      C('C11 the UI also asks for names with punctuation (same rule as the server)', !!dlg3, { asked: !!dlg3, toasts: E.toasts.slice(-2) });
      app.store.setDirty(false);
    }
    // contract: bake payload fields
    {
      const { F, M } = E.couple('cowgirl');
      app.store.project.category = 'FOOTJOB';
      const b = app.bake();
      const need = ['gender', 'naked', 'tracks', 'body', 'sounds', 'animatedVagina', 'invisibleTeeth', 'mouthMoves', 'tongueUsed', 'bareFeet', 'role', 'strapon'];
      const missing = b.actors.map(a => need.filter(k => !(k in a)));
      C('contract: every actor carries all fields', missing.every(m => !m.length), missing);
      const top = ['uid', 'act', 'name', 'author', 'category', 'tags', 'next', 'loops', 'locations', 'fps', 'frames', 'actors'].filter(k => !(k in b));
      C('contract: project-level fields present', !top.length, top);
      C('contract: default roles (female receiver, male giver)', b.actors[0].role === 'receiver' && b.actors[1].role === 'giver', b.actors.map(a => a.role));
      C('contract: bareFeet on for FOOTJOB, strapon off by default', b.actors.every(a => a.bareFeet === true && a.strapon === false), b.actors.map(a => [a.bareFeet, a.strapon]));
      app.store.project.category = 'VAGINAL'; app.store.project.locations = ['DOUBLE_BED'];
      const b2 = app.bake();
      C('contract: bareFeet on for a bed', b2.actors.every(a => a.bareFeet === true), b2.actors.map(a => a.bareFeet));
      app.store.project.locations = ['FLOOR'];
      const b3 = app.bake();
      C('contract: bareFeet off on the floor (default)', b3.actors.every(a => a.bareFeet === false), b3.actors.map(a => a.bareFeet));
      // Details controls
      app.showStep('details'); await E.sleep(150);
      const t = document.getElementById('panel-body').textContent;
      C('contract: Details has "In the act", "Bare feet", "Allow strap-on"', /In the act/i.test(t) && /Bare feet/i.test(t) && /strap-on/i.test(t), null);
      // flags from the engine
      app.setFace(F.id, { ...__m.face.FACE_PRESETS.ahegao?.face || { open: 0.8, tongue: 0.8 } }, 'Ahegao');
      const b4 = app.bake();
      C('contract: Ahegao face -> mouthMoves and tongueUsed on the woman', b4.actors[0].mouthMoves && b4.actors[0].tongueUsed, [b4.actors[0].mouthMoves, b4.actors[0].tongueUsed]);
      app.newScene(false, false, 'couple');
      const b5 = app.bake();
      C('contract: a new scene (mouth at rest) -> mouthMoves/tongueUsed false (both)', b5.actors.every(a => !a.mouthMoves && !a.tongueUsed), b5.actors.map(a => [a.mouthMoves, a.tongueUsed]));
    }
    // C13 bakeByUid keeps the gizmo on a live bone
    {
      const { F } = E.couple('cowgirl');
      app.setTool('rotate');
      app.store.selected = { sim: F.id, bone: 'b__Head__' };
      app.interact.selectBone(F.id, 'b__Head__');
      const list = await api.projects();
      const other = list.find(m => m.uid !== app.store.project.uid);
      let baked = null;
      if (other) baked = await __m.share.bakeByUid(app, other.uid);
      const obj = app.vp.gizmo.object;
      let inScene = false; if (obj) { let o = obj; while (o.parent) o = o.parent; inScene = o === app.vp.scene; }
      const v = E.view(F);
      C('C13 after baking another animation the rings are still on a bone in the scene', !!other && !!baked && inScene && app.interact.active && app.simViews.get(app.interact.active.simId) === v, { other: other && other.name, inScene });
    }
    return { checks: out };
  });
};

// Layout / visuals at the current size
groups.layout = async () => {
  await page.evaluate(() => { __v.closeModals(); document.querySelector('#home:not(.hidden) .btn.primary')?.click(); __v.couple('cowgirl'); app.showStep('pose'); });
  await sleep(600);
  await pe(() => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const ids = [...document.querySelectorAll('.vp-toolbar button, .vp-toolbar [data-tool], .vp-toolbar [data-view]')];
    const bad = [];
    for (const b of ids) { const r = b.getBoundingClientRect(); if (!r.width) continue; const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); if (!(el === b || b.contains(el))) bad.push({ b: b.textContent.trim() || b.dataset.tool || b.dataset.view, top: el && (el.textContent || el.className).toString().slice(0, 30) }); }
    C('E6/C12/C42 every viewport toolbar button is clickable', ids.length > 5 && !bad.length, { n: ids.length, bad });
    const place = ids.find(b => /place/i.test(b.textContent) || b.dataset.tool === 'move');
    C('Place button present and visible', place && place.getBoundingClientRect().width > 0);
    const de = document.documentElement;
    C('no page scroll (both axes)', de.scrollWidth <= innerWidth && de.scrollHeight <= innerHeight, [de.scrollWidth, de.scrollHeight, innerWidth, innerHeight]);
    const hud = document.querySelector('.vp-hud'), cam = document.querySelector('.vp-cam');
    if (hud && cam) {
      const a = hud.getBoundingClientRect(), b = cam.getBoundingClientRect();
      const vis = x => getComputedStyle(x).display !== 'none' && getComputedStyle(x).visibility !== 'hidden' && x.getBoundingClientRect().width > 0;
      const overlap = vis(hud) && vis(cam) && !(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top);
      C('C42 bottom hint and WASD hint do not overlap', !overlap, { hud: [a.left, a.right, a.top], cam: [b.left, b.right, b.top] });
    }
    const rec = document.querySelector('#btn-record, [data-action=record], button[title*=ecord]');
    C('record button present', !!rec, rec && rec.outerHTML.slice(0, 80));
    const pb = document.getElementById('panel-body').getBoundingClientRect();
    const tl = document.getElementById('tl-canvas')?.getBoundingClientRect();
    C('C43 timeline height fits 2 sims (< 236 px row)', tl && tl.height < 200, tl && { tl: tl.height, panel: pb.height });
    return { checks: out, data: { panelH: pb.height } };
  });
  await shot('pose');
  // Help dialog footer
  await page.evaluate(() => { document.querySelector('#btn-help, [data-action=help], button[title*=Help]')?.click(); });
  await sleep(300);
  await pe(() => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const m = document.querySelector('#modal-root .modal');
    const f = m && m.querySelector('footer');
    const r = f && f.getBoundingClientRect();
    C('C45 Help dialog buttons are on screen', !!m && r && r.bottom <= innerHeight && r.top >= 0 && [...f.querySelectorAll('button')].every(b => { const q = b.getBoundingClientRect(); const el = document.elementFromPoint(q.left + q.width / 2, q.top + q.height / 2); return el === b || b.contains(el); }), r && { top: r.top, bottom: r.bottom, H: innerHeight });
    return { checks: out };
  });
  await shot('help');
  await page.evaluate(() => __v.closeModals());
  // Send to game dialog buttons visible
  await page.evaluate(() => { app.store.project.name = 'Untitled animation'; app.exportDialog(); });
  await sleep(300);
  await pe(() => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const m = __v.modal('Send to game');
    const f = m && m.querySelector('footer'), r = f && f.getBoundingClientRect();
    C('Send to game dialog footer on screen', r && r.bottom <= innerHeight, r && [r.top, r.bottom, innerHeight]);
    const err = m && m.querySelector('.warn-box.error, .inline-name');
    C('C49 missing name is asked inside the dialog (inline box / red error)', !!err, m && [...m.querySelectorAll('.warn-box')].map(x => x.className));
    const last = f && [...f.querySelectorAll('button')].pop();
    C('C49 no "red items" wording', last && !/red items/i.test(last.textContent), last && last.textContent);
    return { checks: out };
  });
  await shot('send');
  await page.evaluate(() => __v.closeModals());
  // Face step: two-way sliders at zero look empty; the camera flies to the face
  await page.evaluate(() => { __v.couple('cowgirl'); app.showStep('face'); });
  await sleep(900);
  await pe(() => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const bip = [...document.querySelectorAll('#panel-body input[type=range]')].filter(i => +i.min < 0);
    const at0 = bip.filter(i => +i.value === 0);
    C('C51 two-way sliders at 0 fill nothing (bipolar, a == b)', bip.length > 0 && at0.every(i => i.classList.contains('bipolar') && i.style.getPropertyValue('--a') === i.style.getPropertyValue('--b')), at0.map(i => [i.style.getPropertyValue('--a'), i.style.getPropertyValue('--b')]));
    // head size on screen
    const F = __v.F(), v = __v.view(F); v.group.updateMatrixWorld(true);
    const r = app.vp.canvas.getBoundingClientRect();
    const pr = n => { const p = v.worldPos(n).project(app.vp.camera); return [(p.x + 1) / 2 * r.width, (1 - p.y) / 2 * r.height]; };
    const hd = pr('b__Head__'), nk = pr('b__Neck__');
    const px = Math.hypot(hd[0] - nk[0], hd[1] - nk[1]);
    C('C41 the Face step shows the face big (head-neck > 40 px on screen)', px > 40, +px.toFixed(1));
    return { checks: out };
  });
  await shot('face');
  // C40 each step opens at its top
  await pe(async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    app.showStep('scene'); await __v.sleep(100);
    const b = document.getElementById('panel-body'); b.scrollTop = 300; await __v.sleep(50);
    app.showStep('pose'); await __v.sleep(150);
    C('C40 a new step opens scrolled to its top', b.scrollTop === 0, b.scrollTop);
    return { checks: out };
  });
  // Details: C54 tag input width, null text
  await page.evaluate(() => app.showStep('details'));
  await sleep(300);
  await pe(() => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const body = document.getElementById('panel-body');
    const inp = [...body.querySelectorAll('input.text')].find(i => /tag/i.test(i.placeholder || ''));
    const w = inp && inp.getBoundingClientRect().width, bw = body.clientWidth;
    C('C54 the tag search box fills the panel width', inp && w > bw * 0.8, { w, bw });
    return { checks: out };
  });
  await shot('details');
  // Sounds panel: button grid fits
  await page.evaluate(() => app.showStep('sounds'));
  await sleep(300);
  await pe(() => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const body = document.getElementById('panel-body'), br = body.getBoundingClientRect();
    const cs = getComputedStyle(body), right = br.right - parseFloat(cs.paddingRight);
    const over = [...body.querySelectorAll('.btn-grid .btn')].filter(b => b.getBoundingClientRect().right > right + 1).map(b => b.textContent.trim());
    C('C54 Sounds buttons stay inside the panel', !over.length, over);
    return { checks: out };
  });
  await shot('sounds');
  // Motion step order
  await page.evaluate(() => app.showStep('motion'));
  await sleep(300);
  await pe(() => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const t = document.getElementById('panel-body').textContent;
    const iAdd = t.search(/Add a motion/i), iKeys = t.search(/Keys?\s*-|press K|Two ways/i);
    C('C52 Motion shows "Add a motion" before the keyframe explanation', iAdd >= 0 && (iKeys < 0 || iAdd < iKeys), { iAdd, iKeys });
    return { checks: out };
  });
  await shot('motion');
  // Timeline ruler end (loop label vs tick label) - screenshot of the ruler
  await page.evaluate(() => { __v.couple('cowgirl'); app.timeline.fit(); app.setFrame(40); });
  await sleep(300);
  const tl = await page.evaluate(() => { const r = document.getElementById('tl-canvas').getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
  await shot('timeline-ruler', { x: Math.max(0, tl.x), y: Math.max(0, tl.y), width: Math.min(W - tl.x, tl.w), height: 40 });
  // Library preview bar title
  await page.evaluate(async () => {
    app.showStep('library');
    await __v.waitFor(() => document.querySelector('#panel-body .lib-item, #panel-body .proj-item, #panel-body [data-id]'), 15000);
    const it = document.querySelector('#panel-body .lib-item, #panel-body .proj-item, #panel-body [data-id]'); it && it.click();
    await __v.waitFor(() => app.preview, 15000);
  });
  await sleep(1200);
  await pe(() => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const t = document.getElementById('preview-title');
    C('C42 library preview bar shows the title (width > 60 px)', t && t.getBoundingClientRect().width > 60, t && t.getBoundingClientRect().width);
    return { checks: out };
  });
  await shot('library-preview');
  await page.evaluate(() => { try { app.stopPreview ? app.stopPreview() : document.querySelector('.preview-bar button[title*=lose], .preview-bar .close')?.click(); } catch { /* */ } });
};

// C17 many sims
groups.lanes = async () => {
  await pe(async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const E = __v; E.couple('cowgirl');
    app.addSim('yf'); app.addSim('ym');
    await E.sleep(400);
    const tl = app.timeline; tl._layout();
    const c = document.getElementById('tl-canvas');
    const lastBottom = tl.top(3) + tl.lane;
    C('C17 four sims: the 4th lane fits in the timeline', lastBottom <= c.clientHeight + 1, { lastBottom, h: c.clientHeight, lane: tl.lane });
    app.addSim('yf');
    await E.sleep(300);
    tl._layout();
    const r = c.getBoundingClientRect();
    c.dispatchEvent(new WheelEvent('wheel', { deltaY: 200, clientX: r.left + 40, clientY: r.top + 80, bubbles: true, cancelable: true }));
    await E.sleep(80);
    C('C17 five sims: the wheel over the names scrolls the lanes', tl.maxV === 0 || tl.vscroll > 0, { maxV: tl.maxV, vscroll: tl.vscroll });
    return { checks: out };
  });
  await shot('five-sims');
};

// regressions: magic, recovery routes, sound route, furniture mesh, reveal & security from the page
groups.regress = async () => {
  await pe(async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const E = __v;
    let magicOk = false, detail = null;
    try {
      const mod = await import('/js/magic.js');
      C('magic.js exports makeMagic', typeof mod.makeMagic === 'function', Object.keys(mod));
      detail = await Promise.race([Promise.resolve(mod.makeMagic.length), E.sleep(10).then(() => 'x')]);
      magicOk = true;
    } catch (e) { detail = String(e); }
    C('magic module loads', magicOk, detail);
    const rec = await fetch('/api/recovery?slot=test'); C('GET /api/recovery?slot=test answers', rec.ok, rec.status);
    const w = await fetch('/api/recovery?slot=test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dirty: true, project: { name: 'VERIFY rec', sims: [] } }) });
    const r2 = await (await fetch('/api/recovery?slot=test')).json();
    C('POST then GET recovery (test slot) round-trips', w.ok && r2.project && r2.project.name === 'VERIFY rec', r2 && r2.project);
    const cl = await fetch('/api/recovery_clear?slot=test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const r3 = await (await fetch('/api/recovery?slot=test')).json();
    C('recovery_clear empties it', cl.ok && !r3.project, r3);
    const snd = app.sounds && app.sounds.find(s => s.kind === 'voice') || (app.sounds || [])[0];
    const sr = snd ? await fetch('/api/sound?name=' + encodeURIComponent(snd.name)) : null;
    C('sound route answers (200, or 404 when eaaudio is missing)', sr && (sr.status === 200 || sr.status === 404), sr && sr.status);
    const fm = await fetch('/api/furniture_mesh?id=double_bed');
    C('furniture_mesh route answers for the double bed', fm.status === 200 || fm.status === 404, fm.status);
    const fmj = fm.status === 200 ? await fm.json() : null;
    C('furniture_mesh has meshes', fmj && fmj.meshes && fmj.meshes.length > 0, fmj && fmj.meshes && fmj.meshes.length);
    const mp = await fetch('/api/my_poses'); C('GET /api/my_poses answers a list', mp.ok && Array.isArray(await mp.json()), mp.status);
    return { checks: out };
  });
  // magic run
  await pe(async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const E = __v;
    app.store.setDirty(false);
    app.openMagic(); await E.sleep(500);
    const m = document.querySelector('#modal-root .modal');
    C('Magic dialog opens', !!m, m && m.querySelector('h2')?.textContent);
    E.closeModals();
    const mg = await import('/js/magic.js');
    await mg.makeMagic(app, { recipe: mg.RECIPES[0].id, place: mg.PLACES[0].id, seconds: 3 });
    await E.sleep(1500);
    const p = app.store.project;
    C('Magic makes an animation (2 sims, motions or keys, no NaN)', p.sims.length >= 2 && p.sims.some(s => (s.layers || []).length || s.keys.length > 1) && E.badBones().length === 0, { sims: p.sims.length, layers: p.sims.map(s => (s.layers || []).length), keys: p.sims.map(s => s.keys.length) });
    return { checks: out };
  });
  await shot('magic');
  await page.evaluate(() => { app.setPlaying(false); __v.closeModals(); });
};

// E13: a server without the recovery route -> one console error, not repeats
groups.recovery404 = async () => {
  const hits = { n: 0 };
  await boot({ intercept: req => {
    if (req.url().includes('/api/recovery')) { hits.n++; return req.respond({ status: 404, contentType: 'application/json', body: '{"error":"unknown api recovery"}' }); }
    return req.continue();
  } });
  GROUP = 'recovery404';
  await page.evaluate(async () => { __v.couple('cowgirl'); app.store.setDirty(true); app.store.checkpoint(); });
  for (let i = 0; i < 4; i++) { await page.evaluate(() => { app.store.checkpoint(); app.store.project.loops = (app.store.project.loops || 10) + 1; app.store.setDirty(true); }); await sleep(3200); }
  const errs = logs.filter(l => l.group === 'recovery404' && /recovery/.test(l.text) && (l.type === 'error' || l.type === 'http'));
  check('E13 a missing recovery route is asked once (<= 2 requests, no repeated errors)', hits.n <= 2, { requests: hits.n, errors: errs.length });
  await page.evaluate(() => app.store.setDirty(false));
};

// C47 first thumbnails, C52 tour first step
groups.fresh = async () => {
  await boot({ tourDone: false });
  GROUP = 'fresh';
  await sleep(800);
  await page.evaluate(async () => {
    [...document.querySelectorAll('#home .start')].find(b => /Woman & man/.test(b.textContent)).click();
    await __v.sleep(300);
    const m = __v.modal('New animation'); const ins = m.querySelectorAll('input.text'); ins[0].value = 'VERIFY Tour'; ins[1].value = 'Verifier';
    ins.forEach(i => i.dispatchEvent(new Event('input', { bubbles: true })));
    __v.modalBtn('New animation', 'Start').click();
  });
  await sleep(1500);
  await shot('tour-1');
  // walk the tour until the gallery hint
  let seen = [];
  for (let i = 0; i < 6; i++) {
    const t = await page.evaluate(() => { const c = document.querySelector('#tour-root .tour-card'); if (!c) return null; const s = c.textContent.slice(0, 160); const b = [...c.querySelectorAll('button')].pop(); b && b.click(); return s; });
    if (!t) break; seen.push(t); await sleep(250);
  }
  check('C52 the tour points at the ready poses early ("Start here"/click a ready pose)', seen.slice(0, 3).some(t => /ready pose|Start here/i.test(t)), seen.slice(0, 3));
  await page.evaluate(() => { document.querySelectorAll('#tour-root *').forEach(x => x.remove()); localStorage.setItem('fsa.tourDone', 'true'); });
  await page.evaluate(() => { document.querySelector('#home:not(.hidden) .btn.primary')?.click(); app.showStep('pose'); });
  await sleep(4000);
  const thumbs = await page.evaluate(async () => {
    const imgs = [...document.querySelectorAll('#panel-body .tiles img')].slice(0, 6);
    const lum = await Promise.all(imgs.map(img => new Promise(res => {
      const c = document.createElement('canvas'); c.width = 32; c.height = 32; const x = c.getContext('2d');
      const go = () => { try { x.drawImage(img, 0, 0, 32, 32); const d = x.getImageData(0, 0, 32, 32).data; let s = 0, n = 0, mx = 0; for (let i = 0; i < d.length; i += 4) { const l = 0.3 * d[i] + 0.59 * d[i + 1] + 0.11 * d[i + 2]; s += l; n++; mx = Math.max(mx, l); } res({ mean: +(s / n).toFixed(1), max: mx }); } catch (e) { res({ err: String(e) }); } };
      img.complete ? go() : (img.onload = go);
    })));
    return lum;
  });
  const maxes = thumbs.map(t => t.max || 0);
  check('C47 the first pose thumbnails are lit like the rest (brightest pixel of the first 3 >= 70% of the others)', maxes.length >= 6 && Math.min(...maxes.slice(0, 3)) >= 0.7 * Math.max(...maxes.slice(3)), thumbs);
  await shot('pose-gallery-fresh');
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', protocolTimeout: 900000,
    args: ['--use-angle=d3d11', '--enable-webgl', '--ignore-gpu-blocklist', `--window-size=${W},${H}`] });
  await boot();
  const order = ['engine', 'interact', 'edit', 'dialogs', 'layout', 'lanes', 'regress', 'recovery404', 'fresh'];
  for (const g of order) {
    if (GROUPS && !GROUPS.has(g)) continue;
    GROUP = g; console.log('\n=== ' + g);
    try { await groups[g](); } catch (e) { check('group ran without exception', false, String(e && (e.stack || e.message)).slice(0, 800)); try { await shot(g + '-exception'); } catch { /* */ } }
  }
  // cleanup: projects this run saved
  try {
    await boot();
    GROUP = 'cleanup';
    const removed = await page.evaluate(async () => {
      const api = __m.api, list = await api.projects(), out = [];
      for (const m of list) if (/^VERIFY /.test(m.name)) { await api.removeProject(m.file); out.push(m.file); }
      await fetch('/api/recovery_clear?slot=test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      app.store.setDirty(false);
      return out;
    });
    check('cleanup: VERIFY projects moved out', true, removed);
  } catch (e) { check('cleanup', false, String(e)); }
  await browser.close();
  const errors = logs.filter(l => ['error', 'pageerror', 'http'].includes(l.type));
  fs.writeFileSync(path.join(OUT, `report_${W}x${H}_${GROUPS ? [...GROUPS].join('-') : 'all'}.json`), JSON.stringify({ results, logs }, null, 1));
  console.log('\n==== SUMMARY', results.filter(r => r.ok).length, 'passed', results.filter(r => !r.ok).length, 'failed');
  for (const r of results.filter(r => !r.ok)) console.log('  FAIL [' + r.group + '] ' + r.name + ' :: ' + JSON.stringify(r.detail).slice(0, 400));
  console.log('page errors / http errors:', errors.length);
  for (const e of errors.slice(0, 30)) console.log('  [' + e.group + '] ' + e.type + ': ' + e.text.slice(0, 250));
})().catch(async e => { console.error('crashed', e); try { await browser.close(); } catch { /* */ } process.exit(1); });
