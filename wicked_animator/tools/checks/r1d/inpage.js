// R1-D in-page tests (run inside the app page: `await (await import('/tools-r1d...'))` is not possible, so the check
// script passes this file's text to page.evaluate). Every test returns {name, ok, detail}.
// eslint-disable-next-line no-unused-vars
async function r1dTests(which = null) {
  const THREE = await import('three');
  const R = await import('/js/capture/rigpose.js');
  const RT = await import('/js/capture/retarget.js');
  const C = await import('/js/capture/clean.js');
  const F = await import('/js/capture/facemap.js');
  const K = await import('/js/capture/keys.js');
  const M = await import('/js/capture/mock.js');
  const B = await import('/js/bones.js');
  const A = await import('/js/animation.js');
  const app = window.app, rig = app.assets.rig;
  const deg = THREE.MathUtils.radToDeg, rad = THREE.MathUtils.degToRad;
  const out = [];
  const add = (name, ok, detail) => out.push({ name, ok: !!ok, detail });
  const median = a => { const s = [...a].sort((x, y) => x - y); return s.length ? s[s.length >> 1] : NaN; };
  const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.min(s.length - 1, Math.floor(p * s.length))] : NaN; };
  const r3 = x => Math.round(x * 1000) / 1000;
  let seed = 7;
  const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
  const gauss = () => { let u = 0, v = 0; while (!u) u = rnd(); while (!v) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  const randAxis = () => new THREE.Vector3(gauss(), gauss(), gauss()).normalize();
  const randRot = maxDeg => new THREE.Quaternion().setFromAxisAngle(randAxis(), rad(rnd() * maxDeg));
  const want = n => !which || which.includes(n);

  // ---------------------------------------------------------------- 3. retarget round trip
  if (want(3)) {
    const solver = new RT.Solver(rig);
    const truth = new R.RigPose(rig);
    const names = rig.bones.map(b => b.name);
    const errs = { arm: [], leg: [], elbow: [], knee: [], hand: [], foot: [], head: [], fingerBase: [], floor: [] };
    for (let trial = 0; trial < 200; trial++) {
      truth.resetPose();
      for (const n of names) {
        const b = truth.bone(n), rest = truth.restByName[n].quat;
        if (B.HINGE[n]) b.quaternion.setFromAxisAngle(new THREE.Vector3(0, 0, 1), B.HINGE[n] * rad(8 + rnd() * 102));
        else if (/_(Index|Mid|Ring|Pinky)0__$/.test(n)) b.quaternion.copy(rest).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, gauss(), gauss()).normalize(), rad(rnd() * 45)));
        else if (/Pelvis__|Spine\d__|Neck__|Head__$|UpperArm__|Thigh__|_Hand__|_Foot__|Thumb0__/.test(n)) b.quaternion.copy(rest).multiply(randRot(45));
      }
      truth.bone('b__ROOT_bind__').quaternion.copy(truth.restByName.b__ROOT_bind__.quat).multiply(randRot(180));
      truth.fk();
      // "film" it: landmarks in MediaPipe world axes (hip-centred, y down, z away)
      const lm = R.landmarks(truth);
      const hipC = lm.pose[23].clone().add(lm.pose[24]).multiplyScalar(0.5);
      const person = C.emptyPerson(1);
      lm.pose.forEach((p, j) => { const w = p.clone().sub(hipC); person.pose.set([w.x, -w.y, -w.z, 0.99], j * 4); person.img.set([0.5, 0.5, 0], j * 3); });
      for (const s of ['L', 'R']) { lm.hands[s].forEach((p, j) => person.hand[s].set([p.x, -p.y, -p.z], j * 3)); person.hand[s + 'ok'][0] = 1; }
      const take = { t: new Float64Array([0]), width: 1280, height: 720, people: [person] };
      const r = RT.solveTake(take, 0, solver, { facing: 0, base: null, stick: false });
      const pose = r.poses[0];
      const got = solver.rp;
      got.resetPose(); got.setPose(pose); got.fk();
      const turn = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), r.psi);
      const spaceErr = n => deg(turn.clone().multiply(truth.quat(n)).angleTo(got.quat(n)));
      const localErr = n => deg(truth.bone(n).quaternion.angleTo(got.bone(n).quaternion));
      for (const s of ['L', 'R']) {
        errs.arm.push(spaceErr(`b__${s}_UpperArm__`)); errs.leg.push(spaceErr(`b__${s}_Thigh__`));
        errs.elbow.push(localErr(`b__${s}_Forearm__`)); errs.knee.push(localErr(`b__${s}_Calf__`));
        errs.hand.push(spaceErr(`b__${s}_Hand__`)); errs.foot.push(spaceErr(`b__${s}_Foot__`));
        for (const f of ['Index', 'Mid', 'Ring', 'Pinky']) errs.fingerBase.push(spaceErr(`b__${s}_${f}0__`));
      }
      errs.head.push(spaceErr('b__Head__'));
      errs.floor.push(Math.abs(R.lowestSkin(got)));
    }
    const main = ['arm', 'leg', 'elbow', 'knee', 'hand', 'foot', 'head'];
    const det = Object.fromEntries(Object.entries(errs).map(([k, v]) => [k, { median: r3(median(v)), p95: r3(pct(v, 0.95)), max: r3(Math.max(...v)) }]));
    add('3a retarget round trip: arms, legs, elbows, knees, hands, feet, head median <= 1 deg (200 poses)',
      main.every(k => median(errs[k]) <= 1), Object.fromEntries(main.map(k => [k, det[k]])));
    add('3b finger bases median <= 2 deg, p95 <= 15 deg', median(errs.fingerBase) <= 2 && pct(errs.fingerBase, 0.95) <= 15, det.fingerBase);
    add('3c "Keep on the floor": lowest skin point within 1 cm of 0', Math.max(...errs.floor) <= 0.01, { max_cm: r3(Math.max(...errs.floor) * 100), median_cm: r3(median(errs.floor) * 100) });
  }

  // ---------------------------------------------------------------- 4. cleaning
  if (want(4)) {
    // a) one-euro, zero-lag, on a noisy 1 Hz sine (30 fps, 10 s)
    const n = 300, ts = new Float64Array(n), clean = new Float64Array(n), noisy = new Float64Array(n);
    // a hand swaying 10 cm at 1 Hz, with 6 mm of tracking jitter (metres, like MediaPipe's world points)
    for (let i = 0; i < n; i++) { ts[i] = i / 30; clean[i] = 0.1 * Math.sin(2 * Math.PI * ts[i]); noisy[i] = clean[i] + 0.006 * gauss(); }
    const zl = C.zeroLag(noisy, ts, C.FILTERS.body);
    const fw = C.oneEuroSeries(noisy, ts, C.FILTERS.body);
    const rms = (a, b, from = 30, to = n - 30) => { let s = 0; for (let i = from; i < to; i++) s += (a[i] - b[i]) ** 2; return Math.sqrt(s / (to - from)); };
    const lagOf = y => {       // the shift (in frames, sub-frame) that best lines y up with the clean sine
      let best = 0, bs = Infinity;
      for (let L = -5; L <= 5; L += 0.05) {
        let s = 0;
        for (let i = 30; i < n - 30; i++) s += (y[i] - 0.1 * Math.sin(2 * Math.PI * (ts[i] - L / 30))) ** 2;
        if (s < bs) { bs = s; best = L; }
      }
      return best;
    };
    const lag = lagOf(zl), lagFwd = lagOf(fw);
    add('4a zero-lag one-euro: phase lag < 1 frame and less noise (noisy 1 Hz sine)', Math.abs(lag) < 1 && rms(zl, clean) < rms(noisy, clean),
      { lag_frames: r3(lag), one_way_lag_frames: r3(lagFwd), noise_before_mm: r3(rms(noisy, clean) * 1000), noise_after_mm: r3(rms(zl, clean) * 1000) });
    // b) left/right swaps injected into a mock take, then repaired
    const motion = await M.loadMockMotion();
    const take = M.takeFromMotion(rig, motion, { seconds: 10, face: false, hands: true, noise: 0.003 });
    const N = take.t.length;
    const orig = Float32Array.from(take.people[0].pose);
    const swapped = new Set();
    const pairs = { arm: [11, 13, 15, 17, 19, 21], leg: [23, 25, 27, 29, 31] };
    for (let run = 0; run < 24; run++) {
      const kind = rnd() < 0.5 ? 'arm' : 'leg', start = 1 + Math.floor(rnd() * (N - 8)), len = 1 + Math.floor(rnd() * 5);
      for (let i = start; i < Math.min(N, start + len); i++) {
        const key = kind + i;
        if (swapped.has(key)) continue;
        swapped.add(key);
        for (const j of pairs[kind]) for (let c = 0; c < 4; c++) {
          const a = (i * 33 + j) * 4 + c, b = (i * 33 + j + 1) * 4 + c, pe = take.people[0].pose;
          const x = pe[a]; pe[a] = pe[b]; pe[b] = x;
        }
      }
    }
    C.repairSwaps(take, 0);
    let right = 0, total = 0;
    for (const key of swapped) {
      const kind = key.startsWith('arm') ? 'arm' : 'leg', i = +key.slice(3);
      total++;
      const j = pairs[kind][0], k = (i * 33 + j) * 4;
      const pe = take.people[0].pose;
      if (Math.abs(pe[k] - orig[k]) < 1e-6 && Math.abs(pe[k + 1] - orig[k + 1]) < 1e-6) right++;
    }
    add('4b injected left/right swaps repaired in >= 95% of frames', right / total >= 0.95, { swapped_limb_frames: total, repaired: right, rate: r3(right / total) });
    // c) a 10-frame gap is filled
    const g = M.takeFromMotion(rig, motion, { seconds: 3, face: false, hands: false });
    const po = g.people[0].pose, keep = Float32Array.from(po);
    for (let i = 40; i < 50; i++) for (const j of [13, 15]) po[(i * 33 + j) * 4 + 3] = 0;
    const gc = C.cleanTake(g, { smooth: 0.5 });
    let seen = true, err = 0;
    for (let i = 40; i < 50; i++) for (const j of [13, 15]) {
      const k = (i * 33 + j) * 4;
      if (gc.people[0].pose[k + 3] < 0.5) seen = false;
      err = Math.max(err, Math.hypot(gc.people[0].pose[k] - keep[k], gc.people[0].pose[k + 1] - keep[k + 1], gc.people[0].pose[k + 2] - keep[k + 2]));
    }
    const missFlag = gc.people[0].miss.armL.slice(40, 50).some(Boolean);
    add('4c a 10-frame gap is filled', seen && !missFlag && err < 0.06, { filled: seen, marked_missing: missFlag, max_error_cm: r3(err * 100) });
    // d) 24 fps with a wobbly frame rate -> 30 fps
    const n24 = 120, t24 = new Float64Array(n24);
    for (let i = 0; i < n24; i++) t24[i] = i / 24 + (i > 0 && i < n24 - 1 ? (rnd() - 0.5) * 0.4 / 24 : 0);
    const p24 = C.emptyPerson(n24);
    for (let i = 0; i < n24; i++) for (let j = 0; j < 33; j++) p24.pose.set([t24[i], 2 * t24[i], -t24[i], 0.99], (i * 33 + j) * 4);
    const r30 = C.resample({ t: t24, width: 1, height: 1, people: [p24] }, 30);
    const want30 = Math.floor((t24[n24 - 1] - t24[0]) * 30 + 1e-6) + 1;
    let gridErr = 0, valErr = 0;
    for (let k = 0; k < r30.t.length; k++) { gridErr = Math.max(gridErr, Math.abs(r30.t[k] - (t24[0] + k / 30))); valErr = Math.max(valErr, Math.abs(r30.people[0].pose[(k * 33) * 4] - r30.t[k])); }
    add('4d 24 fps (variable) input is resampled to 30 fps', r30.t.length === want30 && gridErr < 1e-9 && valErr < 1e-5,
      { frames_in: n24, frames_out: r30.t.length, expected: want30, grid_error: gridErr, value_error: valErr });
  }

  // ---------------------------------------------------------------- 5. loop and keys
  if (want(5)) {
    const dance = M.builtInDance(2.1, 6.3);
    const take = M.takeFromMotion(rig, dance, { seconds: 6.3, face: false, hands: true, noise: 0 });
    const cl = C.cleanTake(take, { smooth: 0.5 });
    const solved = RT.solveTake(cl, 0, new RT.Solver(rig), { facing: 0, base: null });
    const t0 = performance.now();
    const L = K.findLoop(solved.poses, { minFrames: 30 });
    const ms = performance.now() - t0;
    const closed = K.closeLoop(solved.poses, null, L.a, L.b);
    const seam = K.seamError(closed.poses);
    add('5a findLoop finds the 2.1 s period (+-1 frame) with a seam <= 1 deg', Math.abs((L.b - L.a) - 63) <= 1 && seam <= 1,
      { period_frames: L.b - L.a, expected: 63, a: L.a, b: L.b, seam_deg: r3(seam), search_ms: Math.round(ms) });
    // key reduction on the closed loop and on a longer library take
    const keys = K.reduceKeys(closed.poses, null, true, 0.5);
    const tol = K.tolerances(0.5);
    let worst = 0;
    for (let f = 0; f < closed.poses.length; f++) {
      const p = A.evaluate(keys, f, closed.poses.length, true);
      for (const [b, q] of Object.entries(closed.poses[f].rot)) {
        const e = new THREE.Quaternion().fromArray(q).angleTo(new THREE.Quaternion().fromArray(p.rot[b])) / (RT.FINGER_BONES.has(b) ? tol.fingers : tol.body);
        worst = Math.max(worst, e);
      }
    }
    const motion = await M.loadMockMotion();
    const lt = C.cleanTake(M.takeFromMotion(rig, motion, { seconds: 10, face: false, hands: true, noise: 0.002 }), { smooth: 0.5 });
    const ls = RT.solveTake(lt, 0, new RT.Solver(rig), { facing: 0 });
    const lkeys = K.reduceKeys(ls.poses, null, false, 0.5);
    // for reference (not graded): a 10 s creator dance filmed with 2 mm of jitter, and the same dance's own keys
    const tp = []; for (let i = 0; i < 301; i++) tp.push(motion.poseAt(i / 30));
    const truthKeys = K.reduceKeys(tp.map(p => ({ rot: Object.fromEntries(Object.entries(p.rot).filter(([b]) => RT.SOLVED.includes(b))), pos: {} })), null, false, 0.5).length;
    add('5b keys at least 5x fewer than frames, within tolerance (the 2.1 s periodic take)', closed.poses.length / keys.length >= 5 && worst <= 1.001,
      { loop_frames: closed.poses.length, loop_keys: keys.length, ratio: r3(closed.poses.length / keys.length), loop_ease: keys[0] && keys[0].ease, worst_misfit: r3(worst),
        info_creator_dance_10s: { frames: ls.poses.length, keys_from_capture: lkeys.length, keys_the_clip_itself_needs: truthKeys } });
    // applyToSim + Ctrl+Z gives the keys back exactly
    const s = app.store.sim() || app.store.project.sims[0];
    const before = JSON.stringify(s.keys);
    const undoBefore = app.store.undo.length;
    const nk = K.applyToSim(app, s.id, closed, { mode: 'replace', fitLength: null, detail: 0.5 });
    const changed = JSON.stringify(app.store.sim(s.id).keys) !== before;
    app.store.undoStep();
    const after = JSON.stringify(app.store.sim(s.id).keys);
    add('5c applyToSim then Ctrl+Z restores sim.keys (JSON-equal)', changed && after === before && app.store.undo.length === undoBefore,
      { keys_made: nk, changed, restored: after === before, undo_steps_used: 1 });
    // "Only here": the keys outside the part stay as they were, and the part's edges blend from the old animation
    // into the take and back over 6 frames (no jump)
    {
      const p = app.store.project, loop = !!p.loop;
      K.applyToSim(app, s.id, closed, { mode: 'replace', fitLength: null, detail: 0.5 });   // an animation to insert into
      const L = p.length;
      const base = JSON.parse(JSON.stringify(app.store.sim(s.id).keys));
      const at = Math.max(0, Math.min(20, L - 31)), span = Math.min(30, L - at);
      const oldAt = f => A.evaluate(base, f, L, loop);
      const raise = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), rad(60));
      const ins = [];
      for (let i = 0; i < span; i++) {
        const o = oldAt(at + i);
        ins.push({ rot: { ...o.rot, b__L_UpperArm__: new THREE.Quaternion().fromArray(o.rot.b__L_UpperArm__).multiply(raise).toArray() }, pos: { ...o.pos } });
      }
      K.applyToSim(app, s.id, { poses: ins, faces: null }, { mode: 'insert', at, detail: 0.5 });
      const now = app.store.sim(s.id).keys;
      const outside = k => k.frame < at || k.frame >= at + span;
      const keptOutside = JSON.stringify(base.filter(outside)) === JSON.stringify(now.filter(outside));
      const ev = f => A.evaluate(now, f, L, loop);
      const ang = (x, y) => deg(new THREE.Quaternion().fromArray(x.rot.b__L_UpperArm__).angleTo(new THREE.Quaternion().fromArray(y.rot.b__L_UpperArm__)));
      const edgeIn = ang(ev(at), oldAt(at)), edgeOut = ang(ev(at + span - 1), oldAt(at + span - 1)), middle = ang(ev(at + (span >> 1)), ins[span >> 1]);
      app.store.undoStep(); app.store.undoStep();
      const restored = JSON.stringify(app.store.sim(s.id).keys) === before;
      // "Make the animation this long" with the playhead past the new end (round-1 gate): frame inside, timeline refit
      const len0 = app.store.project.length;
      app.setFrame(Math.min(60, len0 - 1));
      const frame0 = app.store.frame;
      K.applyToSim(app, s.id, { poses: closed.poses.slice(0, 39), faces: null }, { mode: 'replace', fitLength: true, detail: 0.5 });
      const t1 = { length: app.store.project.length, frame: app.store.frame, fit: app.timeline && app.timeline._fitLength };
      app.store.undoStep();
      const t2 = { length: app.store.project.length, frame: app.store.frame, fit: app.timeline && app.timeline._fitLength };
      add('5e a new length from capture keeps the playhead inside and refits the timeline (and Ctrl+Z puts both back)',
        t1.length === 39 && frame0 >= 39 && t1.frame < t1.length && t1.fit === t1.length && t2.length === len0 && t2.frame < t2.length && t2.fit === t2.length
          && JSON.stringify(app.store.sim(s.id).keys) === before,
        { length_before: len0, frame_before: frame0, after_make_keys: t1, after_undo: t2 });
      add('5d "Only here": keys outside the part stay; its edges blend in and out (no jump)', keptOutside && edgeIn < 10 && edgeOut < 10 && middle < 2 && restored,
        { at, span, length: L, kept_outside: keptOutside, jump_at_start_deg: r3(edgeIn), jump_at_end_deg: r3(edgeOut), take_in_middle_err_deg: r3(middle), full_change_deg: 60, undo_restored: restored });
    }
  }

  // ---------------------------------------------------------------- 6. face mapping
  if (want(6)) {
    const mk = (n, { swap = false, found = 1 } = {}) => {
      const p = C.emptyPerson(n);
      const t = new Float64Array(n);
      for (let i = 0; i < n; i++) {
        t[i] = i / 30;
        const bs = new Float32Array(52).fill(0.04);
        const winking = (i >= 30 && i < 40) || (i >= 70 && i < 78);
        const blinking = i >= 55 && i < 60;
        bs[F.BS.eyeBlinkLeft] = winking || blinking ? 1 : 0.05;
        bs[F.BS.eyeBlinkRight] = blinking ? 1 : 0.05;
        bs[F.BS.jawOpen] = 0.2;
        if (swap) for (const nm of F.BS_NAMES) if (/Left$/.test(nm)) { const a = F.BS[nm], b = F.BS[nm.replace(/Left$/, 'Right')]; const x = bs[a]; bs[a] = bs[b]; bs[b] = x; }
        p.face.bs.set(bs, i * 52);
        p.face.m.set(new THREE.Matrix4().identity().elements, i * 16);
        p.face.ok[i] = i < found * n ? 1 : 0;
        // the eye openings measured from the face points (the performer's left eye closes when winking)
        p.face.eyeL[i] = winking || blinking ? 0.05 : 0.3;
        p.face.eyeR[i] = blinking ? 0.05 : 0.3;
      }
      return { t, width: 640, height: 480, people: [p] };
    };
    const a = F.faceTrack(mk(90));
    add('6a eyeBlinkLeft = 1 gives wink > 0', a.ok && a.faces[35].wink > 0 && Math.abs(a.faces[10].wink) < 0.05, { wink_during: a.faces[35].wink, wink_before: a.faces[10].wink, eyes_during_blink: a.faces[57].eyes });
    const b = F.faceTrack(mk(90, { swap: true }));
    add('6b a swapped left/right stream is found and fixed by the self-check', b.swapped && b.faces[35].wink > 0, { swapped_detected: b.swapped, wink_after_fix: b.faces[35].wink });
    const c = F.faceTrack(mk(90, { found: 0.4 }));
    // and applying a take with such a face writes no face values
    const s = app.store.project.sims[0];
    const pose = A.evaluate(s.keys, 0, app.store.project.length, true) || { rot: {}, pos: {} };
    const faces = c.ok ? c.faces : null;
    K.applyToSim(app, s.id, { poses: [pose, pose, pose], faces }, { mode: 'insert', at: 0 });
    const wrote = app.store.sim(s.id).keys.some(k => k.frame < 3 && k.face && Object.keys(k.face).length && k.face.wink !== undefined);
    app.store.undoStep();
    add('6c face found in < 50% of frames writes no face values', !c.ok && c.faces.every(f => f === null) && !wrote && /too small/.test(c.message),
      { ok: c.ok, found: c.found, message: c.message, face_written: wrote });
  }
  return out;
}
