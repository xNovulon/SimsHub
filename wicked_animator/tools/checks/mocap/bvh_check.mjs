// Motion files (BVH) -> the sim: parser, skeleton recognition and retargeting, in Node (no browser, no game).
//   node tools/checks/mocap/bvh_check.mjs            (three.js: see lib/three.mjs - WA_THREE=<folder> to point at one)
// Reads tools/checks/mocap/fixtures (hand-written arm files + make_fixtures.mjs's synthetic bodies) and poses the
// synthetic A-pose rig of lib/rig.mjs through web/js/capture/bvh.js solveFile - the same path the app uses.
// Prints a PASS/FAIL table, exits 1 when anything fails.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { useThree, webUrl } from './lib/three.mjs';

await useThree();
const THREE = await import('three');
const B = await import(webUrl('js/capture/bvh.js'));
const { Solver } = await import(webUrl('js/capture/retarget.js'));
const { RigPose, lowestSkin } = await import(webUrl('js/capture/rigpose.js'));
const K = await import(webUrl('js/capture/keys.js'));
const A = await import(webUrl('js/animation.js'));
const { makeRig } = await import('./lib/rig.mjs');

const DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures');
const read = f => fs.readFileSync(path.join(DIR, f), 'utf8').replace(/\r\n/g, '\n');   // git may check the samples out with Windows line endings
const rows = [];
const row = (name, ok, detail = '') => { rows.push({ name, ok: !!ok, detail }); return ok; };
const deg = r => (r * 180) / Math.PI;
const r2 = x => Math.round(x * 100) / 100;
const V = a => new THREE.Vector3(...a);
const near = (a, b, tol) => a.every((x, i) => Math.abs(x - b[i]) <= tol);

// ---------------------------------------------------------------- 1. parser + forward kinematics (hand-computed)
{
  const expect = [
    // frame: [shoulder, elbow, wrist, end site]
    [[0, 0, 0], [10, 0, 0], [20, 0, 0], [25, 0, 0]],
    [[0, 0, 0], [0, 10, 0], [-10, 10, 0], [-15, 10, 0]],     // shoulder Z 90, elbow Z 90
    [[1, 2, 3], [1, 2, -7], [1, 2, -17], [1, 2, -22]],        // moved (1, 2, 3); Z 90 then Y 90 (ZXY) = X -90, Z 90 (XYZ)
  ];
  for (const f of ['arm3_zxy.bvh', 'arm3_xyz.bvh']) {
    const bvh = B.parseBVH(read(f));
    row(`parse ${f}: 3 joints, 12 channels, 3 frames, 30 fps`, bvh.joints.length === 3 && bvh.channels === 12 && bvh.frames === 3 && Math.abs(bvh.fps - 30) < 0.01,
      `${bvh.joints.length} joints, ${bvh.channels} ch, ${bvh.frames} frames, ${r2(bvh.fps)} fps, order ${bvh.joints[1].channels.join(' ')}`);
    let worst = 0;
    for (let i = 0; i < 3; i++) {
      const pose = B.fk(bvh, i);
      const got = [0, 1, 2].map(j => [pose.P[j * 3], pose.P[j * 3 + 1], pose.P[j * 3 + 2]]);
      const e = new THREE.Vector3().fromArray(bvh.joints[2].end).applyQuaternion(new THREE.Quaternion().fromArray(pose.Q, 8)).add(V(got[2]));
      got.push(e.toArray());
      got.forEach((p, j) => { worst = Math.max(worst, V(p).distanceTo(V(expect[i][j]))); });
    }
    row(`fk ${f}: joint places match the hand-worked answer`, worst < 1e-4, `worst ${worst.toExponential(2)} units`);
  }
  // CRLF, tabs, "{" on the joint line, a joint name with spaces, a short last frame
  const crlf = read('arm3_xyz.bvh').replace(/\n/g, '\r\n').replace('ROOT Shoulder', 'ROOT Bip01 L UpperArm');
  const b2 = B.parseBVH(crlf);
  row('parse CRLF + a joint name with spaces', b2.joints[0].name === 'Bip01 L UpperArm' && b2.frames === 3, b2.joints[0].name);
  const short = read('arm3_zxy.bvh').replace(/1 2 3 90 0 90 0 0 0 0 0 0\s*$/, '1 2 3 90 0\n');
  const b3 = B.parseBVH(short);
  row('a cut-off file keeps its complete frames (and says so)', b3.frames === 2 && b3.warnings.length === 1, b3.warnings.join(' '));
  const bad = [['not a bvh', 'hello'], ['no motion', 'HIERARCHY\nROOT a\n{\nOFFSET 0 0 0\nCHANNELS 3 Xrotation Yrotation Zrotation\n}\n'],
    ['bad channel', read('arm3_zxy.bvh').replace('Zrotation Xrotation Yrotation\n\t\tJOINT', 'Zrotation Xrotation Wrotation\n\t\tJOINT')],
    ['a word in the numbers', read('arm3_zxy.bvh').replace('0 0 0 90 0 0 90', '0 0 0 90 x 0 90')],
    ['unclosed', read('arm3_zxy.bvh').replace(/}\s*MOTION/, 'MOTION')]];
  for (const [n, t] of bad) {
    let msg = null;
    try { B.parseBVH(t); } catch (e) { msg = e instanceof B.BVHError ? e.message : 'OTHER: ' + e.message; }
    row(`refuses ${n} with a plain message`, msg && !msg.startsWith('OTHER'), msg);
  }
  const fbx = B.formatProblem('dance.fbx', 'Kaydara FBX Binary  \u0000');
  row('an .fbx gets the "export BVH" message', /BVH/.test(fbx || '') && /Mixamo/.test(fbx || ''), (fbx || '').slice(0, 90));
  row('a .bvh gets no format message', B.formatProblem('dance.bvh', 'HIERARCHY') === null);
}

// ---------------------------------------------------------------- 2. which joint is which (six naming schemes)
const load = f => { const bvh = B.parseBVH(read(f)); return { bvh, info: B.analyze(bvh) }; };
{
  const cases = [['body_mixamo_tpose.bvh', 'Mixamo', true], ['body_cmu_120fps.bvh', 'CMU', false], ['body_daz.bvh', 'Daz / Second Life', false],
    ['body_biped.bvh', '3ds Max Biped', false], ['body_deepmotion.bvh', 'DeepMotion', false], ['body_kinect.bvh', 'Other', false]];
  for (const [f, style, fingers] of cases) {
    const { bvh, info } = load(f);
    const name = k => (k >= 0 ? bvh.joints[k].name : '-');
    const want = { wrist: /hand|wrist/i, elbow: /forearm|elbow/i, shoulder: /arm|shldr|shoulder/i, thigh: /upleg|thigh|hip/i, knee: /leg|shin|calf|knee/i, ankle: /foot|ankle/i };
    const bad = [];
    for (const s of ['L', 'R']) for (const [p, rx] of Object.entries(want)) if (!rx.test(name(info.roles[s][p]))) bad.push(`${s}.${p}=${name(info.roles[s][p])}`);
    // the Mixamo / DeepMotion shoulder joint is the clavicle, never the arm
    if (/LeftShoulder|l_shoulder/.test(bvh.joints.map(j => j.name).join(' ')) && /Shoulder|shoulder/.test(name(info.roles.L.shoulder)) && !/kinect/.test(f)) bad.push('clavicle taken for the arm');
    row(`${f}: every body part found (${style})`, !info.missing.length && !bad.length && info.style === style && info.fingers.L === fingers && info.fingers.R === fingers,
      `style ${info.style}, missing [${info.missing}], ${bad.join(' ')} L arm: ${name(info.roles.L.shoulder)} > ${name(info.roles.L.elbow)} > ${name(info.roles.L.wrist)}, fingers ${info.fingers.L}`);
  }
  const t = load('body_mixamo_tpose.bvh').info, a = load('body_mixamo_apose.bvh').info, z = load('body_mixamo_zup_metres.bvh').info;
  row('rest pose, axes and units are read', t.restPose === 'T-pose' && a.restPose === 'A-pose' && t.up === 'Y up' && z.up === 'Z up' && t.units === 'centimetres' && z.units === 'metres',
    `T: ${t.restPose} ${t.up} ${t.units} (${r2(t.height)}), A: ${a.restPose} (${r2(a.armDrop)} deg), Blender: ${z.up} ${z.units} (${r2(z.height)})`);
  const partial = B.analyze(B.parseBVH(read('arm3_zxy.bvh')));
  row('a file without a body says what is missing', partial.missing.length > 5, partial.missing.join(', '));
  // the name reader on its own
  const np = [['mixamorig:LeftUpLeg', 'L', 'upleg'], ['mixamorig1:RightHandIndex2', 'R', 'handindex2'], ['LHipJoint', 'L', 'hipjoint'], ['Bip01 R Calf', 'R', 'calf'],
    ['l_forearm_JNT', 'L', 'forearm'], ['lShldr', 'L', 'shldr'], ['UpperArm.R', 'R', 'upperarm'], ['ShoulderLeft', 'L', 'shoulder'], ['LowerBack', '', 'lowerback'], ['Hips', '', 'hips']];
  const wrong = np.filter(([n, s, p]) => { const r = B.nameParts(n); return r.side !== s || r.part !== p; }).map(([n]) => `${n}->${JSON.stringify(B.nameParts(n))}`);
  row('joint names: side and part', !wrong.length, wrong.join(' ') || np.map(x => x[0]).join(', '));
}

// ---------------------------------------------------------------- 3. retargeting: the sim's bones follow the file
const rig = makeRig();
const solver = new Solver(rig);
const rp = new RigPose(rig);
const solve = (f, opts = {}) => { const { bvh, info } = load(f); return { bvh, info, ...B.solveFile(bvh, info, solver, { loop: 'none', stay: false, facing: 0, psi: 0, ...opts }) }; };
const posed = pose => { rp.resetPose(); rp.setPose(pose); rp.fk(); return rp; };
const dirRig = (a, b) => rp.pos(b).clone().sub(rp.pos(a)).normalize();
const Drig = n => rp.quat(n).clone().multiply(rp.restQuat(n).clone().invert());
const qAngle = (a, b) => deg(a.angleTo(b));
{
  const { bvh, info, result } = solve('body_mixamo_tpose.bvh');
  const N = result.poses.length;
  row('30 fps file: one pose per frame', N === bvh.frames, `${N} poses, ${bvh.frames} frames`);
  const R = info.roles;
  const errs = { upperArm: 0, forearm: 0, thigh: 0, shin: 0, elbow: 0, knee: 0, head: 0, foot: 0, torso: 0, shoulders: 0, index1: 0, index2: 0, hand: 0 };
  const jp = (pose, k) => V([pose.P[k * 3], pose.P[k * 3 + 1], pose.P[k * 3 + 2]]);
  const jq = (pose, k) => new THREE.Quaternion().fromArray(pose.Q, k * 4);
  const dirFile = (pose, a, b) => jp(pose, b).sub(jp(pose, a)).normalize();
  const G = await import('./lib/bvhgen.mjs');
  for (let i = 0; i < N; i++) {
    const fp = B.fk(bvh, i);
    posed(result.poses[i]);
    const m = (k, e) => { errs[k] = Math.max(errs[k], e); };
    for (const s of ['L', 'R']) {
      const r = R[s];
      m('upperArm', deg(dirRig(`b__${s}_UpperArm__`, `b__${s}_Forearm__`).angleTo(dirFile(fp, r.shoulder, r.elbow))));
      m('forearm', deg(dirRig(`b__${s}_Forearm__`, `b__${s}_Hand__`).angleTo(dirFile(fp, r.elbow, r.wrist))));
      m('thigh', deg(dirRig(`b__${s}_Thigh__`, `b__${s}_Calf__`).angleTo(dirFile(fp, r.thigh, r.knee))));
      m('shin', deg(dirRig(`b__${s}_Calf__`, `b__${s}_Foot__`).angleTo(dirFile(fp, r.knee, r.ankle))));
      // the elbow and knee bend (the file's is known from the motion)
      const bendFile = deg(dirFile(fp, r.shoulder, r.elbow).angleTo(dirFile(fp, r.elbow, r.wrist)));
      const bendRig = deg(dirRig(`b__${s}_UpperArm__`, `b__${s}_Forearm__`).angleTo(dirRig(`b__${s}_Forearm__`, `b__${s}_Hand__`)));
      m('elbow', Math.abs(bendFile - bendRig));
      const kneeFile = deg(dirFile(fp, r.thigh, r.knee).angleTo(dirFile(fp, r.knee, r.ankle)));
      const kneeRig = deg(dirRig(`b__${s}_Thigh__`, `b__${s}_Calf__`).angleTo(dirRig(`b__${s}_Calf__`, `b__${s}_Foot__`)));
      m('knee', Math.abs(kneeFile - kneeRig));
      m('foot', qAngle(Drig(`b__${s}_Foot__`), jq(fp, r.ankle)));
    }
    m('head', qAngle(Drig('b__Head__'), jq(fp, R.head)));
    const mid = (p, a, b) => jp(p, a).add(jp(p, b)).multiplyScalar(0.5);
    const torsoFile = mid(fp, R.L.shoulder, R.R.shoulder).sub(mid(fp, R.L.thigh, R.R.thigh)).normalize();
    const torsoRig = rp.pos('b__L_UpperArm__').clone().add(rp.pos('b__R_UpperArm__')).multiplyScalar(0.5).sub(rp.pos('b__L_Thigh__').clone().add(rp.pos('b__R_Thigh__')).multiplyScalar(0.5)).normalize();
    m('torso', deg(torsoRig.angleTo(torsoFile)));
    m('shoulders', deg(dirRig('b__R_UpperArm__', 'b__L_UpperArm__').angleTo(dirFile(fp, R.R.shoulder, R.L.shoulder))));
    // the left index finger curls 0..60 degrees at each joint (the motion's own numbers)
    const curl = 30 + 30 * Math.sin(2 * Math.PI * (i / 30) / 2);
    const hingeDeg = n => { const q = rp.bone(n).quaternion; return deg(2 * Math.atan2(q.z, q.w)); };
    m('index1', Math.abs(hingeDeg('b__L_Index1__') - curl));
    m('index2', Math.abs(hingeDeg('b__L_Index2__') - curl));
    void G;
  }
  const lim = { upperArm: 1, forearm: 1.5, thigh: 1, shin: 1.5, elbow: 1.5, knee: 1.5, head: 1, foot: 1, torso: 2, shoulders: 4, index1: 3, index2: 3 };
  for (const [k, tol] of Object.entries(lim)) row(`T-pose file on the A-pose rig: ${k} within ${tol} deg`, errs[k] <= tol, `worst ${r2(errs[k])} deg over ${N} frames`);
}

// the same motion written other ways gives the same sim poses
function poseDiff(pa, pb) {
  let worst = 0, where = '';
  const n = Math.min(pa.length, pb.length);
  for (let i = 0; i < n; i++) {
    for (const [b, q] of Object.entries(pa[i].rot)) {
      const o = pb[i].rot[b];
      if (!o) continue;
      const e = deg(new THREE.Quaternion().fromArray(q).angleTo(new THREE.Quaternion().fromArray(o)));
      if (e > worst) { worst = e; where = `${b} @${i}`; }
    }
  }
  return { worst, where };
}
function placeDiff(pa, pb) {
  let worst = 0;
  for (let i = 0; i < Math.min(pa.length, pb.length); i++) worst = Math.max(worst, V(pa[i].pos.b__Pelvis__).distanceTo(V(pb[i].pos.b__Pelvis__)));
  return worst;
}
{
  const base = solve('body_mixamo_tpose.bvh').result.poses;
  for (const [f, what, tol] of [['body_mixamo_apose.bvh', 'A-pose rest', 0.5], ['body_mixamo_zup_metres.bvh', 'Z up, metres, XYZ channels', 0.5],
    ['body_mixamo_60fps.bvh', '60 fps', 1], ['body_mixamo_24fps.bvh', '24 fps', 3]]) {
    const other = solve(f).result.poses;
    const d = poseDiff(base, other), p = placeDiff(base, other);
    row(`same sim poses from ${what}`, other.length === base.length && d.worst <= tol && p < 0.004, `${other.length}/${base.length} frames, worst ${r2(d.worst)} deg (${d.where}), hips ${r2(p * 1000)} mm`);
  }
  const nf = solve('body_mixamo_nofingers.bvh').result.poses;
  for (const [f, what] of [['body_cmu_120fps.bvh', 'CMU names, 120 fps, ZYX'], ['body_daz.bvh', 'Daz names, YXZ'], ['body_biped.bvh', 'Biped names'],
    ['body_deepmotion.bvh', 'DeepMotion names, XZY'], ['body_kinect.bvh', 'Kinect-style names']]) {
    const other = solve(f).result.poses;
    const d = poseDiff(nf, other);
    row(`same sim poses from ${what}`, other.length === nf.length && d.worst <= 1, `${other.length}/${nf.length} frames, worst ${r2(d.worst)} deg (${d.where})`);
  }
  // with fingers or without, the hand turns the same way (knuckles from the fingers, or fixed to the hand)
  const d = poseDiff(base.map(p => ({ rot: { h: p.rot.b__L_Hand__, r: p.rot.b__R_Hand__ } })), nf.map(p => ({ rot: { h: p.rot.b__L_Hand__, r: p.rot.b__R_Hand__ } })));
  row('hands: from the fingers = from the hand joint', d.worst <= 6, `worst ${r2(d.worst)} deg`);
}

// ---------------------------------------------------------------- 4. the hips' travel, the floor, stay in place
{
  const { bvh, info, result, solver: sv } = solve('body_mixamo_tpose.bvh');
  const rest = B.fk(bvh, null), R = info.roles;
  const P = k => V([rest.P[k * 3], rest.P[k * 3 + 1], rest.P[k * 3 + 2]]);
  const perf = P(R.L.shoulder).distanceTo(P(R.L.thigh)) + P(R.L.thigh).distanceTo(P(R.L.knee)) + P(R.L.knee).distanceTo(P(R.L.ankle));
  const want = 100 * sv.legLen / perf;             // 100 cm forward in the file, at the sim's size
  const simPlace = p => V([p.pos.b__Pelvis__[2], p.pos.b__Pelvis__[0], p.pos.b__Pelvis__[1]]);   // ROOT_bind: (up, fwd, left)
  const poses = result.poses, N = poses.length;
  const travel = simPlace(poses[N - 1]).sub(simPlace(poses[0]));
  row('keep the travel: the hips go forward as far as in the file (sim size)', Math.abs(travel.z - want) / want < 0.005 && Math.abs(travel.x) < 0.01,
    `${r2(travel.z)} m forward (want ${r2(want)}), ${r2(travel.x * 1000)} mm sideways`);
  const ys = poses.map(p => simPlace(p).y);
  const bounce = Math.max(...ys) - Math.min(...ys), wantB = 2 * 3 * sv.legLen / perf;
  row('the file\'s height is kept (a 3 cm bounce stays)', Math.abs(bounce - wantB) / wantB < 0.02, `${r2(bounce * 1000)} mm up and down (want ${r2(wantB * 1000)})`);
  let low = Infinity;
  for (const p of poses) { posed(p); low = Math.min(low, lowestSkin(rp)); }
  row('the lowest the body gets is on the floor', Math.abs(low) < 0.005, `${r2(low * 1000)} mm`);
  // (the capture's "Stay in place" takes out a 2-second moving average: checked on the 4-second file, middle half)
  const go = solve('body_mixamo_4s.bvh').result.poses, st = solve('body_mixamo_4s.bvh', { stay: true }).result.poses, M = st.length;
  const drift = simPlace(st[Math.round(3 * M / 4)]).sub(simPlace(st[Math.round(M / 4)]));
  const drift0 = simPlace(go[Math.round(3 * M / 4)]).sub(simPlace(go[Math.round(M / 4)]));
  const sway = Math.max(...st.map(p => simPlace(p).y)) - Math.min(...st.map(p => simPlace(p).y));
  row('stay in place: the slow travel is gone, the bounce stays', Math.abs(drift.z) < 0.05 * Math.abs(drift0.z) && Math.abs(sway - wantB) / wantB < 0.15,
    `${r2(drift.z * 1000)} mm over the middle half (was ${r2(drift0.z * 1000)}), bounce ${r2(sway * 1000)} mm`);
  const fl = solve('body_mixamo_tpose.bvh', { ground: 'floor' }).result.poses;
  let worst = 0;
  for (const p of fl) { posed(p); worst = Math.max(worst, Math.abs(lowestSkin(rp))); }
  row('keep feet on the floor: every frame stands on it', worst < 0.02, `worst ${r2(worst * 1000)} mm off the floor`);
  // a fast hip thrust (2 Hz, 5 cm forward and back) keeps its size (the video's depth filter would flatten it)
  {
    const G = await import('./lib/bvhgen.mjs');
    const thrust = t => { const m = G.motionAt(t); m.root = [0, 98, 5 * Math.sin(2 * Math.PI * 2 * t)]; return m; };
    const bvh = B.parseBVH(G.writeBVH({ names: 'mixamo', motion: thrust })), info = B.analyze(bvh);
    const wantT = 5 * sv.legLen / perf;
    for (const [stay, tol] of [[false, 0.01], [true, 0.05]]) {
      const tp = B.solveFile(bvh, info, solver, { loop: 'none', stay, facing: 0, psi: 0 }).result.poses;
      const zs = tp.slice(15, 46).map(p => simPlace(p).z), amp = (Math.max(...zs) - Math.min(...zs)) / 2;
      row(`a 2 Hz hip thrust keeps its size (stay in place ${stay ? 'on' : 'off'})`, Math.abs(amp - wantT) / wantT < tol, `${r2(amp * 1000)} mm each way (want ${r2(wantT * 1000)})`);
    }
  }
  const sm = solve('body_mixamo_tpose.bvh', { smooth: true }).result.poses;
  const d = poseDiff(poses, sm);
  row('smoothing a clean file changes little', d.worst < 8, `worst ${r2(d.worst)} deg (${d.where})`);
  const mir = solve('body_mixamo_tpose.bvh', { mirror: true }).result.poses;
  posed(mir[15]);
  const lbend = deg(dirRig('b__L_UpperArm__', 'b__L_Forearm__').angleTo(dirRig('b__L_Forearm__', 'b__L_Hand__')));
  posed(poses[15]);
  const rbend = deg(dirRig('b__R_UpperArm__', 'b__R_Forearm__').angleTo(dirRig('b__R_Forearm__', 'b__R_Hand__')));
  row('swap left and right: the left elbow does what the right one did', Math.abs(lbend - rbend) < 2, `${r2(lbend)} vs ${r2(rbend)} deg`);
}

// ---------------------------------------------------------------- 5. a range, the loop, keys on a sim
{
  const part = solve('body_mixamo_tpose.bvh', { from: 15, to: 44 }).result.poses;
  const full = solve('body_mixamo_tpose.bvh').result.poses;
  row('a range of the file: 30 frames from frame 15', part.length === 30, `${part.length} poses`);
  const loop = solve('body_mixamo_4s.bvh', { stay: true, loop: 'best' });
  const L = loop.loop ? loop.loop.b - loop.loop.a : 0;
  row('find the best loop: one 2-second cycle of a 4-second file', loop.loop && Math.abs(L - 60) <= 2 && loop.loop.seam < 5, loop.loop ? `frames ${loop.loop.a}..${loop.loop.b} (${L}), seam ${r2(loop.loop.seam)} deg` : 'none');
  void full;
  // keys on a sim (applyToSim with a stand-in app: project, store, one sim)
  const app = () => {
    const project = { sims: [{ id: 's1', label: 'Sim 1', frame: 'yf', keys: [] }], length: 90, loop: true, fps: 30 };
    return { store: { project, frame: 0, sim: id => project.sims.find(s => s.id === id), checkpoint() {} } };
  };
  const take = loop.result;
  const a1 = app();
  const n6 = K.applyToSim(a1, 's1', take, { fitLength: true, every: 6 });
  const frames6 = a1.store.project.sims[0].keys.map(k => k.frame);
  const okEvery = frames6.every((f, i) => f === i * 6 || (i === frames6.length - 1 && f === take.poses.length - 1));
  row('every 6 frames: a key on 0, 6, 12 ... and the last frame', okEvery && a1.store.project.length === take.poses.length, `${n6} keys: ${frames6.join(' ')}; length ${a1.store.project.length}`);
  const a2 = app();
  const nS = K.applyToSim(a2, 's1', take, { fitLength: true });
  const s2 = a2.store.project.sims[0], Lp = a2.store.project.length;
  let worst = 0;
  const body = new Set(['b__Pelvis__', 'b__Spine1__', 'b__L_UpperArm__', 'b__L_Forearm__', 'b__R_Thigh__', 'b__R_Calf__', 'b__Head__']);
  for (let f = 0; f < Lp; f++) {
    const ev = A.evaluate(s2.keys, f, Lp, true);
    for (const b of body) worst = Math.max(worst, deg(new THREE.Quaternion().fromArray(ev.rot[b]).angleTo(new THREE.Quaternion().fromArray(take.poses[f].rot[b]))));
  }
  row('smart keys: fewer keys, the motion kept within 2 degrees', nS < take.poses.length / 2 && worst < 2, `${nS} keys for ${take.poses.length} frames, worst ${r2(worst)} deg`);
}

// ---------------------------------------------------------------- report
const w = Math.max(...rows.map(r => r.name.length));
console.log('\nMotion files (BVH) - parser and retargeting\n' + '-'.repeat(w + 20));
for (const r of rows) console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name.padEnd(w)}  ${String(r.detail).slice(0, 220)}`);
const bad = rows.filter(r => !r.ok).length;
console.log('-'.repeat(w + 20) + `\n${rows.length - bad} PASS, ${bad} FAIL`);
process.exit(bad ? 1 : 0);
