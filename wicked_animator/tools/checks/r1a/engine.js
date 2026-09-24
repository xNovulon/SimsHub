// R1-A checks 1-12: the face engine and all bones (build_plan.md R1-A, spec_face_bones section 6).
// Runs the engine modules in a bare page (import('/js/...'), no main.js), against our own server.
//   node tools/checks/r1a/engine.js --port 8841 [--no-shots]
// Needs the fixtures (fixtures.js) and the baseline (baseline.js, recorded before the engine edits).
// Output: a PASS/FAIL table, cache/checks/r1a/engine_results.json and the screenshots in cache/checks/r1a/.
'use strict';
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');
const L = require('./lib');

const rows = [];
const add = (name, pass, detail) => { rows.push([name, !!pass, detail]); };
const results = {};

(async () => {
  const port = L.argPort();
  const shots = !process.argv.includes('--no-shots');
  const fx = L.fixtures();
  const basePath = path.join(L.OUT, 'baseline.json');
  if (!fx.length || !fs.existsSync(basePath)) throw new Error('run fixtures.js and baseline.js first');
  const baseline = JSON.parse(fs.readFileSync(basePath, 'utf8'));
  const server = await L.startServer(port);
  let browser;
  try {
    browser = await L.launch();
    const { page, logs } = await L.open(browser, port, { kind: 'engine', w: 1280, h: 800 });
    await page.evaluate(installHelpers);
    if (process.argv.includes('--shots-only')) {
      const list = await screenshots(page);
      add('12 screenshots written', list.every(x => fs.existsSync(x)), list.map(x => path.basename(x)).join(', '));
      await browser.close(); L.stopServer(server);
      process.exit(L.table(rows) ? 0 : 1);
    }

    // ------------------------------------------------------------------ 1. classification
    const c1 = await page.evaluate(() => {
      const B = R.bones, names = R.rig.bones.map(b => b.name);
      const never = names.filter(n => !B.KEYABLE_SET.has(n));
      const grouped = B.BONE_GROUPS.flatMap(g => g.bones || g.sub.flatMap(s => s.bones));
      return {
        rig: names.length, keyable: B.KEYABLE.length, keyableUnique: new Set(B.KEYABLE).size, never: never.length,
        neverKinds: never.filter(n => !/_slot$/.test(n)), keyableNotInRig: B.KEYABLE.filter(n => !names.includes(n)),
        tip: B.WW_BODY.includes('b__Penis_Tip'), faceChannel: B.FACE_CHANNEL.length, posable: B.POSABLE.length,
        jawInPosable: B.POSABLE.includes('b__Jaw__') || B.POSABLE.some(n => /Tounge/.test(n)),
        grouped: grouped.length, groupedUnique: new Set(grouped).size, ungrouped: B.KEYABLE.filter(n => !grouped.includes(n)),
        search: Object.fromEntries(['lip', 'Tounge', 'tongue', 'eyebrow', 'wrist', 'boob'].map(q => [q, B.KEYABLE.filter(n => B.boneMatches(n, q, 'ym'))])),
        lipWoman: B.KEYABLE.filter(n => B.boneMatches(n, 'lip', 'yf')),
        labels: B.KEYABLE.filter(n => /_|b__/.test(B.label(n, 'yf'))),
        limits: B.FACE_CHANNEL.filter(n => !B.faceLimits(n)), regions: B.FACE_CHANNEL.filter(n => !B.faceRegion(n)),
      };
    });
    results.c1 = c1;
    add('1 classification: 128 keyable + 57 never = 185', c1.rig === 185 && c1.keyable === 128 && c1.keyableUnique === 128 && c1.never === 57 && !c1.keyableNotInRig.length,
      `rig ${c1.rig}, keyable ${c1.keyable}, never ${c1.never} (${c1.neverKinds.join(', ')} + slots)`);
    add('1 WW_BODY has b__Penis_Tip; jaw/tongue out of POSABLE', c1.tip && !c1.jawInPosable && c1.posable === 56 && c1.faceChannel === 30, `POSABLE ${c1.posable}, FACE_CHANNEL ${c1.faceChannel}`);
    add('1 every keyable bone in exactly one list group', c1.grouped === 128 && c1.groupedUnique === 128 && !c1.ungrouped.length, `${c1.groupedUnique} grouped`);
    const sw = c1.search;
    add('1 names, safe ranges, regions and search words', !c1.labels.length && !c1.limits.length && !c1.regions.length && sw.lip.length === 8 && sw.Tounge.length === 3
      && sw.tongue.length === 3 && sw.eyebrow.length === 6 && sw.wrist.includes('b__L_ForearmTwist__') && sw.boob.length === 2,
      `lip ${sw.lip.length} (6 lips + 2 corners; on a woman also the 2 vagina lips: ${c1.lipWoman.length}), Tounge ${sw.Tounge.length}, tongue ${sw.tongue.length}, eyebrow ${sw.eyebrow.length}, wrist ${sw.wrist.length}; unnamed ${c1.labels}`);

    // ------------------------------------------------------------------ 2. migration is lossless
    let worst2 = 0, poseLeak = 0, styleOk = true, n2 = 0;
    for (const { name, project } of fx) {
      const b = baseline.fixtures[name];
      const r = await page.evaluate((project, evalFace) => {
        const app = R.scene(project), p = app.store.project, T = R.T;
        let worst = 0, leak = 0, n = 0;
        p.sims.forEach((s, i) => {
          for (const k of s.keys) for (const part of ['rot', 'pos']) for (const nm in (k.pose && k.pose[part]) || {}) if (R.bones.FACE_SET.has(nm)) leak++;
          for (let f = 0; f < p.length; f++) {
            const fb = R.animation.evaluateFaceBones(s.keys, f, p.length, p.loop) || { rot: {}, pos: {} };
            const old = evalFace[i][f];
            for (const bn of ['b__Jaw__', 'b__Tounge__1', 'b__Tounge__2', 'b__Tounge__3']) {
              const rest = R.animation.restOf(bn);
              worst = Math.max(worst, T.qdiff(fb.rot[bn] || rest.r, old.rot[bn] || rest.r), T.vdiff(fb.pos[bn] || rest.t, old.pos[bn] || rest.t));
              n++;
            }
          }
        });
        return { worst, leak, n, style: p.faceStyle, version: p.version };
      }, project, b.evalFace);
      worst2 = Math.max(worst2, r.worst); poseLeak += r.leak; n2 += r.n;
      if (r.style !== 'classic' || r.version !== 3) styleOk = false;
    }
    results.c2 = { worst: worst2, poseLeak, compared: n2 };
    add('2 migration: evaluateFaceBones = old jaw/tongue, every frame', worst2 < 1e-6, `max diff ${worst2.toExponential(2)} over ${n2} bone-frames, ${fx.length} fixtures`);
    add('2 migration: no key.pose holds a face bone', poseLeak === 0, `${poseLeak} found`);
    add('2 migration: faceStyle classic, version 3', styleOk);

    // ------------------------------------------------------------------ 3. old projects play the same
    const TW = new Set(['b__L_ForearmTwist__', 'b__R_ForearmTwist__', 'b__L_ShoulderTwist__', 'b__R_ShoulderTwist__', 'b__L_ThighTwist__', 'b__R_ThighTwist__']);
    let worst3 = 0, tracks3 = 0, missing3 = [], flags3 = true, where3 = '';
    for (const { name, project } of fx) {
      const b = baseline.fixtures[name];
      const r = await page.evaluate(project => {
        const app = R.scene(project);
        const res = app.pipeline.bake();
        return { tracks: res.tracks, flags: res.flags };
      }, project);
      if (JSON.stringify(r.flags) !== JSON.stringify(b.flags)) { flags3 = false; where3 += ` flags(${name})`; }
      b.tracks.forEach((bt, i) => {
        for (const [bone, tr] of Object.entries(bt)) {
          if (TW.has(bone)) continue;
          const nt = r.tracks[i][bone];
          for (const part of ['r', 't']) {
            if (!tr[part]) continue;
            if (!nt || !nt[part]) { missing3.push(`${name}:${bone}.${part}`); continue; }
            tracks3++;
            for (let f = 0; f < tr[part].length; f++) {
              const d = part === 'r' ? qdiff(tr.r[f], nt.r[f]) : vdiff(tr.t[f], nt.t[f]);
              if (d > worst3) { worst3 = d; where3 = `${name} ${bone}.${part} f${f}`; }
            }
          }
        }
      });
    }
    results.c3 = { worst: worst3, where: where3, tracks: tracks3, missing: missing3.slice(0, 20), flags: flags3 };
    add('3 old projects bake the same (all but the 6 twist bones)', worst3 < 1e-6 && !missing3.length && flags3,
      `${tracks3} tracks x every frame, max diff ${worst3.toExponential(2)}${where3 ? ' at ' + where3 : ''}${missing3.length ? ', missing ' + missing3.slice(0, 5) : ''}`);

    // ------------------------------------------------------------------ 4. face keys don't touch the body
    const c4 = await page.evaluate(project => {
      const T = R.T, B = R.bones;
      const app = R.scene(project), p = app.store.project;
      const q = (arr, ax, deg) => T.mulAxis(arr, ax, deg);
      for (const s of p.sims) {
        const k0 = s.keys[0];
        const pose30 = T.clone(k0.pose), pose60 = T.clone(k0.pose);
        pose30.rot.b__Head__ = q(pose30.rot.b__Head__, [0, 1, 0], 20); pose30.rot.b__L_UpperArm__ = q(pose30.rot.b__L_UpperArm__, [0, 0, 1], 25);
        pose60.rot.b__Spine2__ = q(pose60.rot.b__Spine2__, [0, 0, 1], -12); pose60.rot.b__R_Hand__ = q(pose60.rot.b__R_Hand__, [1, 0, 0], 40);
        s.keys = [{ frame: 0, ease: 'easeIn', pose: k0.pose }, { frame: 30, ease: 'easeIn', pose: pose30 }, { frame: 60, ease: 'easeIn', pose: pose60 }];
      }
      const A = app.pipeline.bake();
      const s0 = p.sims[0], rest = R.animation.restOf('b__L_InBrow__');
      s0.keys.push({ frame: 45, ease: 'easeIn', faceOnly: true, pose: T.clone(s0.keys[1].pose), faceBones: { rot: {}, pos: { b__L_InBrow__: [rest.t[0] + 0.008, rest.t[1], rest.t[2]] } } });
      R.animation.sortKeys(s0.keys);
      const Bk = app.pipeline.bake();
      let body = 0, brow = 0, n = 0;
      A.tracks.forEach((tr, i) => {
        for (const [bone, x] of Object.entries(tr)) {
          const y = Bk.tracks[i][bone];
          if (B.FACE_SET.has(bone)) { if (bone === 'b__L_InBrow__' && x.t) for (let f = 0; f < x.t.length; f++) brow = Math.max(brow, T.vdiff(x.t[f], y.t[f])); continue; }
          for (let f = 0; f < p.length; f++) { if (x.r) body = Math.max(body, T.qdiff(x.r[f], y.r[f])); if (x.t) body = Math.max(body, T.vdiff(x.t[f], y.t[f])); n++; }
        }
      });
      return { body, brow, n };
    }, fx.find(f => f.name === 'magic_missionary').project);
    results.c4 = c4;
    add('4 a face key at 45 leaves the body tracks unchanged', c4.body < 1e-6, `max body diff ${c4.body.toExponential(2)} over ${c4.n} track-frames`);
    add('4 ...while the brow track changes', c4.brow > 0.005, `brow moved ${(c4.brow * 1000).toFixed(2)} mm`);

    // ------------------------------------------------------------------ 5. nothing automatic leaks into keys
    const c5 = await page.evaluate(() => {
      const T = R.T, B = R.bones;
      const app = T.make(['yf']), p = app.store.project, s = p.sims[0], v = app.simViews.get(s.id), e = { sim: s, v };
      s.keys[0].face = { ...R.face.FACE_PRESETS.smile.face };
      app.pipeline.editing = s.id;
      app.pipeline.apply(0, { physics: true, overrides: true });
      // pose the left hand like the rotate rings do (the wrist twist follows live)
      v.bone('b__L_Hand__').quaternion.multiply(new R.THREE.Quaternion().setFromAxisAngle(new R.THREE.Vector3(1, 0.3, 0.2).normalize(), R.THREE.MathUtils.degToRad(50)));
      app.pipeline.twist(e);
      const pose = v.getPose(), fb = v.getFaceBones();
      const twistInPose = Object.keys(pose.rot).filter(n => B.TWIST_SET.has(n));
      const faceInPose = [...Object.keys(pose.rot), ...Object.keys(pose.pos)].filter(n => B.FACE_SET.has(n));
      const ftAuto = R.animation.twistAngle(v.restByName.b__L_ForearmTwist__.quat, v.bone('b__L_ForearmTwist__').quaternion);
      // the left inner brow up 5 mm (the smile already moves it: that must not end up in the key)
      const brow = v.bone('b__L_InBrow__'), rest = v.restByName.b__L_InBrow__.pos;
      const shownBefore = brow.position.x - rest.x;
      brow.position.x += 0.005;
      const fb2 = v.getFaceBones();
      const stored = fb2.pos.b__L_InBrow__ ? fb2.pos.b__L_InBrow__[0] - rest.x : 0;
      const others = Object.keys(fb2.rot).length + Object.keys(fb2.pos).length - 1;
      return { fbEmpty: !Object.keys(fb.rot).length && !Object.keys(fb.pos).length, fbCount: Object.keys(fb.rot).length + Object.keys(fb.pos).length,
        twistInPose, faceInPose, ftAutoDeg: ftAuto * 180 / Math.PI, shownBeforeMm: shownBefore * 1000, storedMm: stored * 1000, others };
    });
    results.c5 = c5;
    add('5 Smile + hand posed: key.faceBones stays empty', c5.fbEmpty, `${c5.fbCount} face bones read`);
    add('5 ...and key.pose has no twist or face bone', !c5.twistInPose.length && !c5.faceInPose.length, `twist ${c5.twistInPose}, face ${c5.faceInPose} (auto wrist twist shown ${c5.ftAutoDeg.toFixed(1)} deg)`);
    add('5 left inner brow +5 mm stores +5 mm (no smile in it)', Math.abs(c5.storedMm - 5) <= 0.05 && c5.others === 0, `stored ${c5.storedMm.toFixed(3)} mm (the smile showed ${c5.shownBeforeMm.toFixed(2)} mm), other face bones ${c5.others}`);

    // ------------------------------------------------------------------ 6. twist
    const c6 = await page.evaluate(() => {
      const T = R.T, THREE = R.THREE;
      const app = T.make(['yf']), p = app.store.project, s = p.sims[0], v = app.simViews.get(s.id);
      const rest = n => v.restByName[n].quat;
      s.keys[0].pose.rot.b__L_Hand__ = T.mulAxis(rest('b__L_Hand__').toArray(), [1, 0, 0], 60);
      const ang = () => R.animation.twistAngle(rest('b__L_ForearmTwist__'), v.bone('b__L_ForearmTwist__').quaternion) * 180 / Math.PI;
      app.pipeline.apply(0, { overrides: false });
      const view = ang();
      const bake = app.pipeline.bake();
      const bq = new THREE.Quaternion().fromArray(bake.tracks[0].b__L_ForearmTwist__.r[0]);
      const baked = R.animation.twistAngle(rest('b__L_ForearmTwist__'), bq) * 180 / Math.PI;
      const handTwist = R.animation.twistAngle(rest('b__L_Hand__'), new THREE.Quaternion().fromArray(bake.tracks[0].b__L_Hand__.r[0])) * 180 / Math.PI;
      // keyed by hand: stops following
      s.keys[0].pose.rot.b__L_ForearmTwist__ = T.mulAxis(rest('b__L_ForearmTwist__').toArray(), [1, 0, 0], -10);
      app.pipeline.apply(0, { overrides: false });
      const keyed = ang();
      // switched off
      delete s.keys[0].pose.rot.b__L_ForearmTwist__;
      s.body.twist = false;
      app.pipeline.apply(0, { overrides: false });
      const off = ang();
      // shoulder: -0.4 x the upper arm's twist; hip: off by default, -0.75 when on
      s.body.twist = true;
      s.keys[0].pose.rot.b__L_UpperArm__ = T.mulAxis(rest('b__L_UpperArm__').toArray(), [1, 0, 0], 50);
      s.keys[0].pose.rot.b__L_Thigh__ = T.mulAxis(rest('b__L_Thigh__').toArray(), [1, 0, 0], 40);
      const hipDefault = s.body.hipTwist;
      app.pipeline.apply(0, { overrides: false });
      const sh = R.animation.twistAngle(rest('b__L_ShoulderTwist__'), v.bone('b__L_ShoulderTwist__').quaternion) * 180 / Math.PI;
      const hipOn = R.animation.twistAngle(rest('b__L_ThighTwist__'), v.bone('b__L_ThighTwist__').quaternion) * 180 / Math.PI;
      s.body.hipTwist = false;
      app.pipeline.apply(0, { overrides: false });
      const hipOff = R.animation.twistAngle(rest('b__L_ThighTwist__'), v.bone('b__L_ThighTwist__').quaternion) * 180 / Math.PI;
      // the rings on the wrist twist itself (not keyed yet): the live follow of the hand leaves it alone, and the
      // key gets what shows
      s.body.hipTwist = true; delete s.keys[0].pose.rot.b__L_UpperArm__; delete s.keys[0].pose.rot.b__L_Thigh__;
      app.pipeline.editing = s.id;
      app.pipeline.apply(0, { overrides: false });
      const ft = v.bone('b__L_ForearmTwist__');
      ft.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), THREE.MathUtils.degToRad(15)));
      const shown = ang();
      app.pipeline.twist({ sim: s, v });
      const afterFollow = ang();
      const keyedTw = v.getPose().rot.b__L_ForearmTwist__;
      const keyedAng = keyedTw ? R.animation.twistAngle(rest('b__L_ForearmTwist__'), new THREE.Quaternion().fromArray(keyedTw)) * 180 / Math.PI : null;
      app.pipeline.editing = null;
      return { view, baked, handTwist, keyed, off, sh, hipOff, hipOn, hipDefault, shown, afterFollow, keyedAng };
    });
    results.c6 = c6;
    add('6 60 deg hand roll -> 30 deg wrist twist in the view', Math.abs(c6.view - 30) <= 0.5, `${c6.view.toFixed(2)} deg`);
    add('6 ...and in the bake', Math.abs(c6.baked - 30) <= 0.5 && Math.abs(c6.handTwist - 60) < 0.01, `${c6.baked.toFixed(2)} deg (hand ${c6.handTwist.toFixed(2)})`);
    add('6 a hand-keyed twist bone stops following', Math.abs(c6.keyed + 10) < 0.01, `${c6.keyed.toFixed(2)} deg (keyed -10)`);
    add('6 body.twist = false turns the helpers off', Math.abs(c6.off) < 0.01, `${c6.off.toFixed(3)} deg`);
    add('6 rings on the twist bone itself: the live follow leaves it, the key gets it', Math.abs(c6.shown - 45) < 0.01 && Math.abs(c6.afterFollow - 45) < 0.01 && c6.keyedAng !== null && Math.abs(c6.keyedAng - 45) < 0.01,
      `shown ${c6.shown.toFixed(2)}, after follow ${c6.afterFollow.toFixed(2)}, keyed ${c6.keyedAng === null ? 'none' : c6.keyedAng.toFixed(2)} deg (auto 30 + 15 by hand)`);
    add('6 shoulder -0.4 x upper arm; hip -0.75 (on by default), off works', Math.abs(c6.sh + 20) < 0.5 && Math.abs(c6.hipOff) < 0.01 && Math.abs(c6.hipOn + 30) < 0.5 && c6.hipDefault === true,
      `shoulder ${c6.sh.toFixed(2)} (arm 50), hip default ${c6.hipDefault}: ${c6.hipOn.toFixed(2)}, switched off ${c6.hipOff.toFixed(2)} (thigh 40)`);

    // ------------------------------------------------------------------ 7. limits and mirror
    const c7 = await page.evaluate(() => {
      const T = R.T, THREE = R.THREE;
      const app = T.make(['yf']), p = app.store.project, s = p.sims[0], v = app.simViews.get(s.id);
      s.keys[0].face = { ...R.face.FACE_PRESETS.smile.face };             // a slider layer on top: limits act on the keyed value
      app.pipeline.editing = s.id;
      app.pipeline.apply(0, { overrides: false });
      const brow = v.bone('b__L_InBrow__'), rb = v.restByName.b__L_InBrow__.pos;
      const layerX = brow.position.x - rb.x;
      brow.position.x = rb.x + layerX + 0.060;                            // dragged 60 mm up
      const clamped = R.face.clampFaceBone(v, 'b__L_InBrow__', R.bones.faceLimits('b__L_InBrow__'));
      const keyedMm = (v.getFaceBones().pos.b__L_InBrow__[0] - rb.x) * 1000;
      const again = R.face.clampFaceBone(v, 'b__L_InBrow__', R.bones.faceLimits('b__L_InBrow__'));
      // a corner +5 up, +3 out mirrored onto the right
      const lm = v.bone('b__L_Mouth__'), rl = v.restByName.b__L_Mouth__.pos, rr = v.restByName.b__R_Mouth__.pos;
      const lLayer = lm.position.clone().sub(rl);
      lm.position.copy(rl).add(lLayer).add(new THREE.Vector3(0.005, 0, 0.003));
      R.face.mirrorFaceBone(v, 'b__L_Mouth__', 'b__R_Mouth__');
      const rKeyed = v.getFaceBones().pos.b__R_Mouth__;
      const rOff = rKeyed ? [0, 1, 2].map(i => (rKeyed[i] - rr.toArray()[i]) * 1000) : null;
      // the middle of the upper lip moved sideways: symmetry keeps it in the middle
      const ul = v.bone('b__UpLip__'), rul = v.restByName.b__UpLip__.pos;
      ul.position.z += 0.004; ul.position.x += 0.002;
      R.face.mirrorFaceBone(v, 'b__UpLip__', 'b__UpLip__');
      const ulk = v.getFaceBones().pos.b__UpLip__;
      const ulZ = ulk ? (ulk[2] - rul.z) * 1000 : 0, ulX = ulk ? (ulk[0] - rul.x) * 1000 : 0;
      // data mirror twice = the original
      const fb = { rot: {}, pos: {} };
      for (const n of ['b__L_UpLid__', 'b__R_Eye__', 'b__Jaw__', 'b__Tounge__2', 'b__L_Mouth__', 'b__UpLip__']) fb.rot[n] = T.mulAxis(R.animation.restOf(n).r, [0.3, -0.5, 0.8], 17);
      for (const n of ['b__L_InBrow__', 'b__R_Cheek__', 'b__Tounge__1', 'b__CAS_L_Nostril__']) { const r = R.animation.restOf(n).t; fb.pos[n] = [r[0] + 0.003, r[1] - 0.002, r[2] + 0.004]; }
      const twice = R.animation.mirrorFaceBonesData(R.animation.mirrorFaceBonesData(fb));
      let d = 0;
      for (const n in fb.rot) d = Math.max(d, T.qdiff(fb.rot[n], twice.rot[n]));
      for (const n in fb.pos) d = Math.max(d, T.vdiff(fb.pos[n], twice.pos[n]));
      const once = R.animation.mirrorFaceBonesData(fb);
      const sideOk = once.pos.b__R_InBrow__ && Math.abs((once.pos.b__R_InBrow__[2] - R.animation.restOf('b__R_InBrow__').t[2]) + 0.004) < 1e-9;
      return { clamped, keyedMm, again, rOff, ulZ, ulX, twiceDiff: d, sideOk, sameKeys: JSON.stringify(Object.keys(twice.rot).sort()) === JSON.stringify(Object.keys(fb.rot).sort()) };
    });
    results.c7 = c7;
    add('7 clampFaceBone stops the inner brow at 40 mm', c7.clamped && Math.abs(c7.keyedMm - 40) < 0.01 && !c7.again, `keyed ${c7.keyedMm.toFixed(3)} mm`);
    add('7 mirrorFaceBone: corner +5 up +3 out -> right x +5, z -3', c7.rOff && Math.abs(c7.rOff[0] - 5) < 1e-6 && Math.abs(c7.rOff[2] + 3) < 1e-6 && Math.abs(c7.rOff[1]) < 1e-6,
      c7.rOff ? `right offset ${c7.rOff.map(x => x.toFixed(3)).join(', ')} mm` : 'no key');
    add('7 symmetry keeps the middle upper lip in the middle', Math.abs(c7.ulZ) < 1e-6 && Math.abs(c7.ulX - 2) < 1e-6, `z ${c7.ulZ.toFixed(4)} mm, x ${c7.ulX.toFixed(3)} mm`);
    add('7 mirrorFaceBonesData twice = the original', c7.twiceDiff < 1e-6 && c7.sideOk && c7.sameKeys, `max diff ${c7.twiceDiff.toExponential(2)}`);

    // ------------------------------------------------------------------ 8. new channels
    const c8 = await page.evaluate(async () => {
      const T = R.T, THREE = R.THREE, OLD = await import('/orig/js/face.js');
      const app = T.make(['yf']), p = app.store.project, s = p.sims[0], v = app.simViews.get(s.id);
      const snap = () => v.bones.map(b => [...b.quaternion.toArray(), ...b.position.toArray()]);
      const diffSnap = (a, b) => { let d = 0; a.forEach((x, i) => x.forEach((y, j) => { d = Math.max(d, Math.abs(y - b[i][j])); })); return d; };
      const NEW = ['wink', 'smileSide', 'browSide', 'browTilt', 'sneer', 'jawSide', 'puff'];
      let zeroDiff = 0;
      for (const style of ['classic', 'creator']) for (const base of [{}, R.face.FACE_PRESETS.ecstasy.face, { smile: -0.6, brows: -0.8, bite: 0.5 }]) {
        v.resetPose(); R.face.applyFace(v, base, style); const a = snap();
        const f = { ...base }; for (const k of NEW) if (!(k in f)) f[k] = 0;
        v.resetPose(); R.face.applyFace(v, f, style); const b = snap();
        zeroDiff = Math.max(zeroDiff, diffSnap(a, b));
      }
      const newInSliders = NEW.every(k => R.face.FACE_SLIDERS[k] && R.face.FACE_SLIDERS[k].more);
      // classic style = exactly the face the app made before (the old face.js, loaded side by side)
      let classicDiff = 0;
      for (const f of Object.values(R.face.FACE_PRESETS).map(x => x.face).concat([{ smile: -0.7, brows: -1, bite: 0.6, lookSide: 0.5, lookUp: -0.4 }, { eyes: -0.3, tongue: 1, open: 1, pout: 1, squint: 1, inner: 1 }])) {
        const old = {}; for (const k of Object.keys(OLD.FACE_SLIDERS)) if (k in f) old[k] = f[k];
        v.resetPose(); OLD.applyFace(v, old); const a = snap();
        v.resetPose(); R.face.applyFace(v, old, 'classic'); const b = snap();
        classicDiff = Math.max(classicDiff, diffSnap(a, b));
      }
      // wink 1: only the left lids
      const z = n => R.animation.twistAngle(v.restByName[n].quat, v.bone(n).quaternion, new THREE.Vector3(0, 0, 1)) * 180 / Math.PI;
      v.resetPose(); R.face.applyFace(v, { wink: 1 }, 'creator');
      const wink = { LUp: z('b__L_UpLid__'), RUp: z('b__R_UpLid__'), LLo: z('b__L_LoLid__'), RLo: z('b__R_LoLid__') };
      // jawSide 1: the chin swings to the sim's left (+x in the sim's space; it faces +z)
      const chin = () => { v.group.updateMatrixWorld(true); return v.bone('b__Jaw__').localToWorld(v.faceHandlePoint('b__Jaw__').clone()); };
      v.resetPose(); const c0 = chin();
      R.face.applyFace(v, { jawSide: 1 }, 'creator'); const c1 = chin();
      return { zeroDiff, classicDiff, newInSliders, wink, chinDx: (c1.x - c0.x) * 1000, chinDz: (c1.z - c0.z) * 1000 };
    });
    results.c8 = c8;
    add('8 each new channel at 0 changes no bone', c8.zeroDiff === 0 && c8.newInSliders, `max diff ${c8.zeroDiff}`);
    add('8 classic style = the old face.js exactly (every preset)', c8.classicDiff === 0, `max diff ${c8.classicDiff}`);
    add('8 wink 1 closes only the left lids', c8.wink.LUp > 35 && Math.abs(c8.wink.RUp) < 1e-9 && c8.wink.LLo < -5 && Math.abs(c8.wink.RLo) < 1e-9,
      `left up ${c8.wink.LUp.toFixed(1)}, lo ${c8.wink.LLo.toFixed(1)}; right up ${c8.wink.RUp.toFixed(2)}, lo ${c8.wink.RLo.toFixed(2)} deg`);
    add("8 jawSide 1 swings the chin to the sim's left", c8.chinDx > 2, `chin +x ${c8.chinDx.toFixed(2)} mm`);

    // ------------------------------------------------------------------ 9. bake + offline export
    const c9 = await page.evaluate(() => {
      const T = R.T, THREE = R.THREE;
      const app = T.make(['yf']), p = app.store.project, s = p.sims[0], v = app.simViews.get(s.id);
      s.sounds = []; s.body.blink = false;
      const plain = app.pipeline.bake();
      const rb = R.animation.restOf('b__L_InBrow__').t, rm = R.animation.restOf('b__L_Mouth__').t;
      const k0 = s.keys[0];
      k0.faceBones = { rot: {}, pos: {} };
      s.keys.push({ frame: 45, ease: 'auto', pose: T.clone(k0.pose), faceBones: { rot: {}, pos: {
        b__L_InBrow__: [rb[0] + 0.012, rb[1], rb[2]], b__L_Mouth__: [rm[0] - 0.005, rm[1], rm[2] + 0.002] } } });
      s.keys[1].pose.rot.b__L_Hand__ = T.mulAxis(v.restByName.b__L_Hand__.quat.toArray(), [1, 0, 0], 60);
      const res = app.pipeline.bake();
      const tr = res.tracks[0];
      const span = (list, i) => Math.max(...list.map(x => x[i])) - Math.min(...list.map(x => x[i]));
      const ft = tr.b__L_ForearmTwist__.r.map(q => R.animation.twistAngle(v.restByName.b__L_ForearmTwist__.quat, new THREE.Quaternion().fromArray(q)) * 180 / Math.PI);
      // what main.js bake() hands the exporter
      const baked = { uid: p.uid, act: 'VAGINAL', name: 'r1a export check', author: 'r1a', category: p.category, tags: [], next: [], loops: 10, naked: 'ALL',
        locations: ['FLOOR'], fps: 30, frames: p.length, actors: res.sims.map((sm, i) => ({ gender: sm.gender, naked: 'ALL', tracks: res.tracks[i], body: sm.frame,
          invisibleTeeth: false, animatedVagina: false, sounds: [], mouthMoves: res.flags[i].mouthMoves, tongueUsed: res.flags[i].tongueUsed, bareFeet: false, role: null, strapon: false })) };
      return { browSpanMm: span(tr.b__L_InBrow__.t, 0) * 1000, mouthMoves: res.flags[0].mouthMoves, plainMouth: plain.flags[0].mouthMoves,
        twistSpan: Math.max(...ft) - Math.min(...ft), baked };
    });
    results.c9 = { browSpanMm: c9.browSpanMm, mouthMoves: c9.mouthMoves, plainMouth: c9.plainMouth, twistSpan: c9.twistSpan };
    add('9 keyed brow -> non-constant L_InBrow position track', c9.browSpanMm > 10, `span ${c9.browSpanMm.toFixed(2)} mm`);
    add('9 keyed mouth corner -> flags.mouthMoves', c9.mouthMoves && !c9.plainMouth, `with corner ${c9.mouthMoves}, without ${c9.plainMouth}`);
    add('9 twisted hand -> non-constant ForearmTwist track', c9.twistSpan > 25, `span ${c9.twistSpan.toFixed(2)} deg`);
    const bakedPath = path.join(os.tmpdir(), 'wa_r1a_baked.json');
    fs.writeFileSync(bakedPath, JSON.stringify(c9.baked));
    let ex = null;
    try {
      ex = JSON.parse(execFileSync('python', [path.join(__dirname, 'export_check.py'), bakedPath, 'b__L_InBrow__:t', 'b__L_ForearmTwist__:r', 'b__L_Mouth__:t', 'b__L_Hand__:r'],
        { cwd: L.ROOT, encoding: 'utf8', env: { ...process.env, ANIMATOR_SAVES: path.join(os.tmpdir(), 'wa_r1a_saves') } }).trim().split('\n').pop());
    } catch (e) { ex = { error: String(e.stderr || e.message).slice(-600) }; }
    results.c9.export = ex;
    const a0 = ex && ex.actors && ex.actors[0];
    const ch = (b, k) => a0 && a0.bones[b] && a0.bones[b][k];
    add('9 offline export has the channels (clipfmt.parse_clip)', a0 && ch('b__L_InBrow__', 't') && ch('b__L_InBrow__', 't').span > 0.01 && ch('b__L_ForearmTwist__', 'r') && ch('b__L_ForearmTwist__', 'r').frames > 1
      && ch('b__L_Mouth__', 't') && ch('b__L_Mouth__', 't').span > 0.003 && a0.events.includes(19),
      a0 ? `InBrow t span ${(ch('b__L_InBrow__', 't') || {}).span}, ForearmTwist r frames ${(ch('b__L_ForearmTwist__', 'r') || {}).frames}, Mouth t span ${(ch('b__L_Mouth__', 't') || {}).span}, events ${a0.events}, ${ex.bytes} bytes in %TEMP%` : JSON.stringify(ex).slice(0, 300));

    // ------------------------------------------------------------------ 10. expression baking equivalence
    const c10 = await page.evaluate(() => {
      const T = R.T, THREE = R.THREE;
      const out = {};
      for (const style of ['creator', 'classic']) {
        const app = T.make(['yf'], style), p = app.store.project, s = p.sims[0], v = app.simViews.get(s.id);
        const eco = R.face.FACE_PRESETS.ecstasy.face;
        s.sounds = []; s.body.blink = false; s.body.talk = { mouth: false };
        // sliders on the key
        s.keys[0].face = { ...eco };
        app.pipeline.apply(0, { overrides: false, physics: false });
        const shown = {};
        for (const n of R.bones.FACE_CHANNEL) shown[n] = { q: v.bone(n).quaternion.clone(), p: v.bone(n).position.clone() };
        // the same face read as face bones (layer included), keyed instead of the sliders
        v.resetPose(); v.setPose(s.keys[0].pose); v.setFaceBones(null); R.face.applyFace(v, eco, style);
        const fb = v.getFaceBones({ withLayer: true });
        delete s.keys[0].face; s.keys[0].faceBones = fb;
        app.pipeline.apply(0, { overrides: false, physics: false });
        let mm = 0, dg = 0;
        for (const n of R.bones.FACE_CHANNEL) {
          mm = Math.max(mm, shown[n].p.distanceTo(v.bone(n).position) * 1000);
          dg = Math.max(dg, shown[n].q.angleTo(v.bone(n).quaternion) * 180 / Math.PI);
        }
        out[style] = { mm, dg, bones: Object.keys(fb.rot).length + Object.keys(fb.pos).length };
      }
      return out;
    });
    results.c10 = c10;
    add('10 "Ecstasy" sliders = the same face as face bones (creator)', c10.creator.mm <= 0.3 && c10.creator.dg <= 0.5, `${c10.creator.mm.toFixed(4)} mm, ${c10.creator.dg.toFixed(4)} deg (${c10.creator.bones} channels)`);
    add('10 ...and in classic style', c10.classic.mm <= 0.3 && c10.classic.dg <= 0.5, `${c10.classic.mm.toFixed(4)} mm, ${c10.classic.dg.toFixed(4)} deg`);

    // ------------------------------------------------------------------ 11. performance
    const c11 = await page.evaluate(project => {
      const app = R.scene(project), p = app.store.project;
      p.faceStyle = 'creator';                                 // the heavier path: give-way and the clamp
      app.pipeline.simulateIfNeeded(true);
      for (let k = 0; k < 60; k++) app.pipeline.apply(k % p.length, { physics: true, overrides: false });
      const t = [];
      for (let k = 0; k < 300; k++) { const t0 = performance.now(); app.pipeline.apply(k % p.length, { physics: true, overrides: false }); t.push(performance.now() - t0); }
      t.sort((a, b) => a - b);
      const t0 = performance.now();
      for (let k = 0; k < 300; k++) app.pipeline.apply(k % p.length, { physics: true, overrides: false });
      const mean = (performance.now() - t0) / 300;
      return { median: t[150], p90: t[270], mean, sims: p.sims.length };
    }, fx.find(f => f.name === 'magic_cowgirl').project);
    results.c11 = c11;
    add('11 pipeline.apply, 2 sims: median <= 1.0 ms', c11.median <= 1.0 && c11.sims === 2, `median ${c11.median.toFixed(3)} ms, p90 ${c11.p90.toFixed(3)}, mean ${c11.mean.toFixed(3)} ms over 300 frames`);

    // ------------------------------------------------------------------ face extras: eyes, give-way, clamp, dots
    const cx = await page.evaluate(() => {
      const T = R.T, THREE = R.THREE;
      const app = T.make(['yf']), p = app.store.project, s = p.sims[0], v = app.simViews.get(s.id);
      s.body.talk = { mouth: true }; s.sounds = [];
      app.pipeline.editing = s.id;
      app.pipeline.apply(0, { overrides: false });
      v.group.updateMatrixWorld(true);
      // the look-at ring 35 cm in front of the eyes, moved 30 cm to the sim's left at eye height
      const eyes = v.bone('b__L_Eye__').getWorldPosition(new THREE.Vector3()).add(v.bone('b__R_Eye__').getWorldPosition(new THREE.Vector3())).multiplyScalar(0.5);
      const target = eyes.clone().add(new THREE.Vector3(0.30, 0, 0.35));
      const lim = R.bones.faceLimits('b__L_Eye__');
      R.face.aimEye(v, 'b__L_Eye__', target, lim); R.face.aimEye(v, 'b__R_Eye__', target, lim);
      const ax = n => { const b = v._base(n).q; const rel = v.restByName[n].quat.clone().invert().multiply(b); return new THREE.Euler().setFromQuaternion(rel, 'XYZ'); };
      const eyeL = ax('b__L_Eye__'), eyeR = ax('b__R_Eye__');
      // a small move to the left: not clamped, looks left by atan(0.1/0.35)
      const t2 = eyes.clone().add(new THREE.Vector3(0.10, 0, 0.35));
      R.face.aimEye(v, 'b__L_Eye__', t2, lim);
      // unclamped, the eye's own forward (local +y) points at the target
      const eb = v.bone('b__L_Eye__'); eb.updateWorldMatrix(true, false);
      const fwd = new THREE.Vector3(0, 1, 0).applyQuaternion(eb.getWorldQuaternion(new THREE.Quaternion()));
      const small = fwd.angleTo(t2.clone().sub(eb.getWorldPosition(new THREE.Vector3()))) * 180 / Math.PI;
      // blinking gives way to lids posed shut (creator style), and the clamp keeps lids under 46 deg
      app.pipeline.editing = null;
      const lidShut = T.mulAxis(v.restByName.b__L_UpLid__.quat.toArray(), [0, 0, 1], 40);
      s.keys[0].faceBones = { rot: { b__L_UpLid__: lidShut, b__R_UpLid__: T.mulAxis(v.restByName.b__R_UpLid__.quat.toArray(), [0, 0, 1], 40) }, pos: {} };
      const z = n => R.animation.twistAngle(v.restByName[n].quat, v.bone(n).quaternion, new THREE.Vector3(0, 0, 1)) * 180 / Math.PI;
      let most = 0;
      for (let f = 0; f < p.length; f++) { app.pipeline.apply(f, { overrides: false, physics: false }); most = Math.max(most, z('b__L_UpLid__')); }
      s.keys[0].face = { eyes: 1 };
      app.pipeline.apply(0, { overrides: false, physics: false });
      const clamped = z('b__L_UpLid__');
      // every face dot sits on (or just in) the skin
      let far = 0, farName = '';
      const pos = []; for (const m of v.meshes) { if (/penis/.test(m.userData.role)) continue; const t = new THREE.Vector3(); for (let i = 0; i < m.geometry.attributes.position.count; i++) { m.getVertexPosition(i, t); pos.push(t.clone()); } }
      v.resetPose(); v.group.updateMatrixWorld(true);
      const pos0 = []; for (const m of v.meshes) { if (/penis/.test(m.userData.role)) continue; const t = new THREE.Vector3(); for (let i = 0; i < m.geometry.attributes.position.count; i++) { m.getVertexPosition(i, t); pos0.push(t.clone()); } }
      for (const n of R.bones.FACE_CHANNEL) {
        const w = v.bone(n).localToWorld(v.faceHandlePoint(n).clone());
        let d = Infinity; for (const q of pos0) d = Math.min(d, q.distanceTo(w));
        if (/_Eye__/.test(n)) d = Math.max(0, d - 0.011);              // the pupil dot sits 11 mm in front of the eye's centre
        if (d > far) { far = d; farName = n; }
      }
      return { eyeL: [eyeL.x, eyeL.z].map(x => x * 180 / Math.PI), eyeR: [eyeR.x, eyeR.z].map(x => x * 180 / Math.PI), small, blinkMost: most, clamped, farMm: far * 1000, farName };
    });
    results.extras = cx;
    add('eyes: ring 30 cm to the left -> both eyes +x, clamped at 32', Math.abs(cx.eyeL[0] - 32) < 0.01 && Math.abs(cx.eyeR[0] - 32) < 0.01 && cx.small < 1,
      `left ${cx.eyeL[0].toFixed(2)}, right ${cx.eyeR[0].toFixed(2)} deg; 10 cm to the left: the eye looks ${cx.small.toFixed(2)} deg off the target`);
    add('blinking gives way to lids posed shut; clamp at 46 deg', cx.blinkMost < 40.01 && Math.abs(cx.clamped - 46) < 0.01, `lid max over the loop ${cx.blinkMost.toFixed(2)} deg (posed 40); posed 40 + slider 40 -> ${cx.clamped.toFixed(2)}`);
    add('face dots sit on the skin', cx.farMm < 3, `farthest ${cx.farMm.toFixed(2)} mm (${cx.farName})`);

    // ------------------------------------------------------------------ for R1-C: rim, highlight colour, hover glow fade
    const cfx = await page.evaluate(async () => {
      const app = R.T.make(['yf']), s = app.store.project.sims[0], v = app.simViews.get(s.id);
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const part = v.index('b__L_Hand__');
      v.hover(part); v._tickFx();
      const t0 = v._fxU.glowT.value;
      const glowOn = v.meshes.some(m => m.geometry.attributes.glow.array.some(x => x > 0.5));
      await wait(120); v._tickFx();
      const t1 = v._fxU.glowT.value;
      v.setRim('#ff4f9a', 0.5, 200); v._tickFx();
      const r0 = v._fxU.rimAmount.value;
      await wait(250); v._tickFx();
      const r1 = v._fxU.rimAmount.value, rimColor = v._fxU.rimColor.value.getHexString();
      v.highlight(part);                                        // default colour = the sim's own
      const c = new R.THREE.Color(v.color);
      let tinted = false;
      // a tinted vertex is white moved toward the sim's colour: (1 - col) is parallel to (1 - c)
      for (const m of v.meshes) {
        const col = m.geometry.attributes.color;
        for (let i = 0; i < col.count && !tinted; i++) {
          const d = [1 - col.getX(i), 1 - col.getY(i), 1 - col.getZ(i)], e = [1 - c.r, 1 - c.g, 1 - c.b];
          if (Math.max(...d) < 0.05) continue;
          const cross = Math.hypot(d[1] * e[2] - d[2] * e[1], d[2] * e[0] - d[0] * e[2], d[0] * e[1] - d[1] * e[0]);
          tinted = cross / (Math.hypot(...d) * Math.hypot(...e)) < 1e-4;
        }
      }
      v.setPickMode('face');
      const facePart = R.bones.controllableIndex(v.rig, v.index('b__CAS_L_EyeScale__'), 'face') === v.index('b__L_UpLid__');
      const bodyPart = R.bones.controllableIndex(v.rig, v.index('b__L_InBrow__'), 'body') === v.index('b__Head__');
      const exact = R.bones.controllableIndex(v.rig, v.index('b__L_Bracelet_slot'), 'exact') === v.index('b__L_ForearmTwist__');
      const dot = v.faceHandlePoint('b__L_Eye__');
      return { t0, t1, glowOn, r0, r1, rimColor, tinted, facePart, bodyPart, exact, eyeDot: dot.toArray() };
    });
    results.fx = cfx;
    add('R1-C: hover glow fades in over ~90 ms', cfx.glowOn && cfx.t0 < 0.2 && cfx.t1 === 1, `glowT ${cfx.t0.toFixed(2)} -> ${cfx.t1}`);
    add('R1-C: setRim(color, amount, ms) fades the Fresnel rim', cfx.r0 < 0.1 && Math.abs(cfx.r1 - 0.5) < 1e-9 && cfx.rimColor === 'ff4f9a', `${cfx.r0.toFixed(2)} -> ${cfx.r1}, ${cfx.rimColor}`);
    add('R1-C: highlight() tints in the sim colour', cfx.tinted);
    add('picking modes: face / body / exact (Alt+click)', cfx.facePart && cfx.bodyPart && cfx.exact, JSON.stringify({ face: cfx.facePart, body: cfx.bodyPart, exact: cfx.exact }));

    // ------------------------------------------------------------------ 12. screenshots
    if (shots) {
      const list = await screenshots(page);
      results.shots = list;
      add('12 screenshots written', list.every(x => fs.existsSync(x)), list.map(x => path.basename(x)).join(', '));
    }
    if (logs.filter(l => !/favicon|404/.test(l)).length) results.pageLogs = logs;
    add('no page errors', !logs.some(l => /pageerror|error:/.test(l) && !/404/.test(l)), logs.slice(0, 3).join(' | '));
  } finally {
    if (browser) await browser.close();
    L.stopServer(server);
  }
  fs.writeFileSync(path.join(L.OUT, 'engine_results.json'), JSON.stringify({ at: new Date().toISOString(), rows, results }, null, 1));
  const ok = L.table(rows);
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); L.table(rows); process.exit(1); });

function qdiff(a, b) {
  const s = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]) < 0 ? -1 : 1;
  return Math.max(Math.abs(a[0] - s * b[0]), Math.abs(a[1] - s * b[1]), Math.abs(a[2] - s * b[2]), Math.abs(a[3] - s * b[3]));
}
function vdiff(a, b) { return Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1]), Math.abs(a[2] - b[2])); }

// ------------------------------------------------------------------ in-page helpers
function installHelpers() {
  const { THREE } = R;
  const T = {
    clone: x => JSON.parse(JSON.stringify(x)),
    qdiff(a, b) {
      const s = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]) < 0 ? -1 : 1;
      return Math.max(Math.abs(a[0] - s * b[0]), Math.abs(a[1] - s * b[1]), Math.abs(a[2] - s * b[2]), Math.abs(a[3] - s * b[3]));
    },
    vdiff: (a, b) => Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1]), Math.abs(a[2] - b[2])),
    // q * R(axis, deg), local axis
    mulAxis(q, axis, deg) {
      return new THREE.Quaternion().fromArray(q).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(...axis).normalize(), THREE.MathUtils.degToRad(deg))).toArray();
    },
    // a new project (v3) with sims standing at rest, one key each at frame 0
    make(frames, style = 'creator') {
      const p = R.state.newProject();
      p.faceStyle = style;
      frames.forEach((f, i) => { const s = R.state.newSim(p, f); p.sims.push(s); });
      const app = R.scene(p);
      app.store.project.sims.forEach((s, i) => {
        const v = app.simViews.get(s.id);
        v.resetPose();
        if (i) { v.bone('b__Pelvis__').position.z += 0.8 * i; v.bone('b__Spine0__').position.z += 0.8 * i; }
        s.keys = [{ frame: 0, ease: 'auto', pose: v.getPose() }];
        R.pipeline.simBody(s);
      });
      return app;
    },
  };
  R.T = T;
}

// ------------------------------------------------------------------ screenshots (check 12)
async function screenshots(page) {
  const out = [];
  await page.evaluate(async () => {
    const THREE = R.THREE;
    const canvas = document.createElement('canvas');
    canvas.width = 1280; canvas.height = 800; canvas.style.width = '1280px'; canvas.style.height = '800px';
    document.body.appendChild(canvas);
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(1); renderer.setSize(1280, 800, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.08;
    const scene = new THREE.Scene(); scene.background = new THREE.Color(0x241a2f);
    scene.add(new THREE.HemisphereLight(0xfff4ee, 0x2a2228, 0.85));
    const key = new THREE.DirectionalLight(0xfff3ea, 2.5); key.position.set(2.6, 5, 3.6); scene.add(key);
    const rim = new THREE.DirectionalLight(0xff7ab8, 0.75); rim.position.set(-4, 2.6, -3.5); scene.add(rim);
    const rim2 = new THREE.DirectionalLight(0xa88bff, 0.55); rim2.position.set(4, 2.2, -3); scene.add(rim2);
    const fill = new THREE.DirectionalLight(0xfff0e8, 0.6); fill.position.set(-2, 1.2, 4); scene.add(fill);
    const camera = new THREE.PerspectiveCamera(30, 1280 / 800, 0.01, 50);
    const tex = {};
    const skin = f => tex[f] || (tex[f] = new Promise(res => new THREE.TextureLoader().load('/api/skin?frame=' + f, t => { t.flipY = false; t.colorSpace = THREE.SRGBColorSpace; res(t); }, undefined, () => res(null))));
    R.S = {
      renderer, scene, camera,
      async sim(frame = 'yf', style = 'creator') {
        const app = R.T.make([frame], style);
        const s = app.store.project.sims[0], v = app.simViews.get(s.id);
        v.setTexture(await skin(frame));
        scene.add(v.group);
        return { app, s, v };
      },
      clear() { for (const o of [...scene.children]) if (o.isGroup) scene.remove(o); },
      look(v, bone, off, at = [0, 0, 0], fov = 30) {
        v.group.updateMatrixWorld(true);
        const names = Array.isArray(bone) ? bone : [bone];
        const b = new THREE.Vector3();
        for (const n of names) b.add(v.bone(n).getWorldPosition(new THREE.Vector3()));
        b.multiplyScalar(1 / names.length).add(new THREE.Vector3(...at));
        camera.fov = fov; camera.updateProjectionMatrix();
        camera.position.copy(b).add(new THREE.Vector3(...off)); camera.lookAt(b);
      },
      render() { R.S.scene.updateMatrixWorld(true); renderer.render(scene, camera); },
    };
  });
  const snap = async name => { const f = path.join(L.OUT, name); await page.screenshot({ path: f, clip: { x: 0, y: 0, width: 1280, height: 800 } }); out.push(f); };
  const draw = async (fn, ...args) => { await page.evaluate(fn, ...args); await page.evaluate(() => new Promise(r => requestAnimationFrame(() => { R.S.render(); requestAnimationFrame(r); }))); };
  // a hand twisted 70 deg, with and without the twist helpers
  for (const on of [false, true]) {
    await draw(async on => {
      R.S.clear();
      const { app, s, v } = await R.S.sim('yf');
      const r = v.restByName;
      s.keys[0].pose.rot.b__L_UpperArm__ = R.T.mulAxis(r.b__L_UpperArm__.quat.toArray(), [0, 0, 1], -55);
      s.keys[0].pose.rot.b__L_Forearm__ = R.T.mulAxis(r.b__L_Forearm__.quat.toArray(), [0, 0, 1], 35);
      s.keys[0].pose.rot.b__L_Hand__ = R.T.mulAxis(r.b__L_Hand__.quat.toArray(), [1, 0, 0], 70);
      s.body.twist = on;
      app.pipeline.apply(0, { overrides: false, physics: false });
      R.S.look(v, ['b__L_ForearmTwist__', 'b__L_Hand__'], [0.05, 0.12, 0.42], [0, 0, 0], 30);
    }, on);
    await snap(`twist_hand70_${on ? 'helpers_on' : 'helpers_off'}.png`);
  }
  // a thigh twisted 45 deg: hip twist off, -0.75, -0.4
  for (const [tag, ratio] of [['off', 0], ['075', -0.75], ['040', -0.4]]) {
    await draw(async ratio => {
      R.S.clear();
      const { app, s, v } = await R.S.sim('yf');
      const r = v.restByName;
      s.keys[0].pose.rot.b__L_Thigh__ = R.T.mulAxis(r.b__L_Thigh__.quat.toArray(), [1, 0, 0], 45);
      for (const t of R.bones.TWIST) if (t.opt) t.ratio = ratio || -0.75;
      s.body.hipTwist = !!ratio;
      app.pipeline.apply(0, { overrides: false, physics: false });
      for (const t of R.bones.TWIST) if (t.opt) t.ratio = -0.75;
      R.S.look(v, ['b__L_Thigh__', 'b__L_Calf__'], [0.75, 0.12, 0.75], [0, 0.08, 0], 34);
    }, ratio);
    await snap(`twist_thigh45_hip_${tag}.png`);
  }
  // the same on a real ready pose (cowgirl, thigh turned in about 40 deg), from behind: hips and buttocks
  const cow = L.fixtures().find(f => f.name === 'magic_cowgirl');
  if (cow) for (const [tag, ratio] of [['off', 0], ['075', -0.75]]) {
    await draw(async (ratio, proj) => {
      R.S.clear();
      const { app, s, v } = await R.S.sim('yf');
      const f = proj.sims.find(x => x.frame === 'yf');
      const pose = JSON.parse(JSON.stringify(f.keys[0].pose));
      for (const n of Object.keys(pose.rot)) if (R.bones.FACE_SET.has(n)) delete pose.rot[n];
      s.keys[0].pose = pose;
      s.body.hipTwist = !!ratio;
      app.pipeline.apply(0, { overrides: false, physics: false });
      v.group.updateMatrixWorld(true);
      const pel = v.bone('b__Pelvis__').getWorldPosition(new R.THREE.Vector3());
      const fwd = new R.THREE.Vector3(0, 0, 1).applyQuaternion(v.bone('b__Pelvis__').getWorldQuaternion(new R.THREE.Quaternion()));
      R.S.camera.fov = 40; R.S.camera.updateProjectionMatrix();
      R.S.camera.position.copy(pel).add(new R.THREE.Vector3(-0.9, 0.25, -0.9)); R.S.camera.lookAt(pel);
    }, ratio, cow.project);
    await snap(`twist_hip_cowgirl_back_${tag}.png`);
  }
  // "Ecstasy" in classic and creator style, front and three-quarter
  for (const style of ['classic', 'creator']) for (const [view, off] of [['front', [0, 0.02, 0.62]], ['34', [0.42, 0.05, 0.45]]]) {
    await draw(async (style, off) => {
      R.S.clear();
      const { app, s, v } = await R.S.sim('yf', style);
      s.keys[0].face = { ...R.face.FACE_PRESETS.ecstasy.face };
      s.body.blink = false;
      app.pipeline.apply(0, { overrides: false, physics: false });
      R.S.look(v, 'b__Head__', off, [0, 0.07, 0.02], 24);
    }, style, off);
    await snap(`face_ecstasy_${style}_${view}.png`);
  }
  // where the face dots sit (faceHandlePoint), in the region colours, on a creator 'Smile'
  await draw(async () => {
    R.S.clear();
    const THREE = R.THREE;
    const { app, s, v } = await R.S.sim('yf');
    s.keys[0].face = { ...R.face.FACE_PRESETS.smile.face }; s.body.blink = false;
    app.pipeline.apply(0, { overrides: false, physics: false });
    v.group.updateMatrixWorld(true);
    const g = new THREE.Group();
    for (const [region, h] of Object.entries(R.bones.FACE_HANDLES)) for (const n of h.bones) {
      const m = new THREE.Mesh(new THREE.SphereGeometry(0.0022, 12, 8), new THREE.MeshBasicMaterial({ color: h.color, depthTest: false }));
      m.renderOrder = 22; m.position.copy(v.bone(n).localToWorld(v.faceHandlePoint(n).clone())); g.add(m);
    }
    R.S.scene.add(g);
    R.S.look(v, 'b__Head__', [0.2, 0.02, 0.55], [0, 0.07, 0.03], 22);
  });
  await snap('face_dots_smile_creator.png');
  // the selected sim's rim light (and the hover glow on its hand part)
  await draw(async () => {
    R.S.clear();
    const a = await R.S.sim('yf'), b = await R.S.sim('ym');
    b.v.group.position.set(0.75, 0, 0.1);
    a.app.pipeline.apply(0, { overrides: false, physics: false });
    b.app.pipeline.apply(0, { overrides: false, physics: false });
    a.v.setRim(a.v.color, 0.6);
    a.v.highlight(a.v.index('b__L_Forearm__'), a.v.color);
    b.v.setRim('#57b8ff', 0.25);
    R.S.camera.fov = 30; R.S.camera.updateProjectionMatrix();
    R.S.camera.position.set(0.4, 1.2, 3.6); R.S.camera.lookAt(0.37, 0.95, 0);
  });
  await snap('rim_selected_sim.png');
  return out;
}
