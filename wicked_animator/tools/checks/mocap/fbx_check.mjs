// Motion files (FBX) -> the sim: three.js's FBXLoader + web/js/capture/fbx.js, in Node (no browser, no game).
//   node tools/checks/mocap/fbx_check.mjs          (three.js: see lib/three.mjs - WA_THREE=<folder> to point at one)
// Reads tools/checks/mocap/fixtures: arm3.fbx (ASCII, written by hand, with a joint orient), and make_fixtures.mjs's
// FBX files - the same body and known motion as the BVH fixtures, binary and ASCII, with pre-rotations and another
// rotation order under a Z-up, 0.01-scaled Armature, two animation stacks, a skinned mesh, other naming schemes, and a
// skeleton without animation. Joint places and turns must match the hand-worked answers and the BVH files; the sim's
// poses (capture/bvh.js solveFile, the same path the app uses) must match the BVH import's.
// Prints a PASS/FAIL table, exits 1 when anything fails.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { useThree, webUrl } from './lib/three.mjs';

await useThree();
const THREE = await import('three');
const B = await import(webUrl('js/capture/bvh.js'));
const F = await import(webUrl('js/capture/fbx.js'));
const { Solver } = await import(webUrl('js/capture/retarget.js'));
const { makeRig } = await import('./lib/rig.mjs');

const DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures');
const bytes = f => { const b = fs.readFileSync(path.join(DIR, f)); return b.buffer.slice(b.byteOffset, b.byteOffset + b.length); };
const rows = [];
const row = (name, ok, detail = '') => { rows.push({ name, ok: !!ok, detail }); return ok; };
const r2 = x => Math.round(x * 100) / 100;
const deg = r => (r * 180) / Math.PI;
const V = a => new THREE.Vector3(...a);
const errOf = async fn => { try { await fn(); return null; } catch (e) { return e instanceof B.BVHError ? e.message : 'OTHER: ' + e.message; } };

// ---------------------------------------------------------------- 1. the hand-written arm (ASCII) and its binary twin
{
  const expect = [
    [[0, 0, 0], [10, 0, 0], [20, 0, 0], [25, 0, 0]],
    [[0, 0, 0], [0, 10, 0], [-10, 10, 0], [-15, 10, 0]],
    [[1, 2, 3], [1, 2, -7], [1, 2, -17], [1, 2, -22]],
  ];
  const bvh = B.parseBVH(fs.readFileSync(path.join(DIR, 'arm3_zxy.bvh'), 'utf8'));
  for (const f of ['arm3.fbx', 'arm3_binary.fbx']) {
    const fbx = await F.readFBX(bytes(f));
    const m = fbx.motion(0);
    row(`${f}: 4 joints, 1 stack, 3 frames at 30 fps`, fbx.joints.length === 4 && fbx.stacks.length === 1 && m.frames === 3 && m.fps === 30 && fbx.stacks[0].name === 'Arm test',
      `${fbx.joints.map(j => j.name).join(' > ')}; "${fbx.stacks[0].name}", ${m.frames} frames at ${m.fps} fps`);
    let worst = 0, worstQ = 0;
    for (let i = 0; i < 3; i++) {
      const p = B.fk(m, i), b = B.fk(bvh, i);
      for (let j = 0; j < 4; j++) worst = Math.max(worst, V([p.P[j * 3], p.P[j * 3 + 1], p.P[j * 3 + 2]]).distanceTo(V(expect[i][j])));
      // the turns from the rest equal the BVH's world turns (the elbow's joint orient drops out)
      for (let j = 0; j < 3; j++) worstQ = Math.max(worstQ, deg(new THREE.Quaternion().fromArray(p.Q, j * 4).angleTo(new THREE.Quaternion().fromArray(b.Q, j * 4))));
    }
    row(`${f}: joint places match the hand-worked answer`, worst < 1e-4, `worst ${worst.toExponential(2)} units`);
    row(`${f}: turns from the rest match the BVH arm (joint orient drops out)`, worstQ < 1e-3, `worst ${worstQ.toExponential(2)} deg`);
  }
}

// ---------------------------------------------------------------- 2. the body: every way of writing it reads the same
const rig = makeRig();
const solver = new Solver(rig);
const bvhOf = f => { const bvh = B.parseBVH(fs.readFileSync(path.join(DIR, f), 'utf8')); return { bvh, info: B.analyze(bvh) }; };
const solveM = (m, info, opts = {}) => B.solveFile(m, info, solver, { loop: 'none', stay: false, facing: 0, psi: 0, ...opts }).result.poses;
function poseDiff(pa, pb) {
  let worst = 0, where = '', hips = 0;
  const n = Math.min(pa.length, pb.length);
  for (let i = 0; i < n; i++) {
    for (const [b, q] of Object.entries(pa[i].rot)) {
      const o = pb[i].rot[b];
      if (!o) continue;
      const e = deg(new THREE.Quaternion().fromArray(q).angleTo(new THREE.Quaternion().fromArray(o)));
      if (e > worst) { worst = e; where = `${b} @${i}`; }
    }
    hips = Math.max(hips, V(pa[i].pos.b__Pelvis__).distanceTo(V(pb[i].pos.b__Pelvis__)));
  }
  return { worst, where, hips, n };
}
// the FBX bodies hold the first second of the BVH motion: compared with the BVH's same second ("height as in the
// file" puts the lowest point of the part that is read on the floor, so the part must be the same)
const ref = bvhOf('body_mixamo_tpose.bvh'), refNF = bvhOf('body_mixamo_nofingers.bvh');
const refPoses = solveM(ref.bvh, ref.info, { to: 30 }), refPosesNF = solveM(refNF.bvh, refNF.info, { to: 30 });
const cases = [
  ['body_mixamo.fbx', 'ASCII, Mixamo names, fingers', ref, refPoses, { stack: 'mixamo.com', style: 'Mixamo', fingers: true, same: true }],
  ['body_mixamo_binary.fbx', 'binary, compressed arrays', ref, refPoses, { style: 'Mixamo', fingers: true, same: true }],
  ['body_prerot_zup_60fps.fbx', 'joint orients, rotation order 4, Z-up 0.01 Armature, 60 fps', ref, refPoses, { style: 'Mixamo', fingers: true, fps: 60 }],
  ['body_skinned.fbx', 'with a skinned mesh and bind pose', ref, refPoses, { style: 'Mixamo', fingers: true, meshes: 1, same: true }],
  ['body_deepmotion.fbx', 'DeepMotion names', refNF, refPosesNF, { style: 'DeepMotion', fingers: false, same: true }],
  ['body_plain_names.fbx', 'plain HumanIK / Rokoko names, rotation order 3', refNF, refPosesNF, { style: 'HumanIK / Rokoko', fingers: false, same: true }],
];
for (const [f, what, R, poses, want] of cases) {
  const fbx = await F.readFBX(bytes(f));
  const m = fbx.motion(0), info = B.analyze(m);
  const okRead = !info.missing.length && info.style === want.style && info.fingers.L === want.fingers && (!want.stack || fbx.stacks[0].name === want.stack)
    && m.fps === (want.fps || 30) && fbx.meshes === (want.meshes || 0);
  row(`${f}: read and recognised (${what})`, okRead, `${fbx.joints.length} joints, "${fbx.stacks[0].name}", ${m.frames} frames at ${m.fps} fps, ${info.style}, ${info.restPose}, ${info.up}, ${info.units}, fingers ${info.fingers.L}, meshes ${fbx.meshes}, missing [${info.missing}]`);
  if (want.same) {
    // same axes and units as the BVH: the joints are in the very same places
    let worst = 0;
    for (let i = 0; i < m.frames; i++) {
      const a = B.fk(m, i), b = B.fk(R.bvh, i);
      for (const s of ['L', 'R']) for (const part of ['shoulder', 'elbow', 'wrist', 'thigh', 'knee', 'ankle']) {
        const ja = info.roles[s][part], jb = R.info.roles[s][part];
        worst = Math.max(worst, V([a.P[ja * 3], a.P[ja * 3 + 1], a.P[ja * 3 + 2]]).distanceTo(V([b.P[jb * 3], b.P[jb * 3 + 1], b.P[jb * 3 + 2]])));
      }
    }
    row(`${f}: the limbs are where the BVH has them, every frame`, worst < 0.01, `worst ${r2(worst * 1000) / 1000} cm`);
  }
  const d = poseDiff(solveM(m, info), poses);
  row(`${f}: the sim's poses equal the BVH import's`, d.worst < 0.5 && d.hips < 0.002, `${d.n} frames, worst ${r2(d.worst)} deg (${d.where}), hips ${r2(d.hips * 1000)} mm`);
}

// ---------------------------------------------------------------- 3. several stacks, no animation, broken files
{
  const fbx = await F.readFBX(bytes('body_two_stacks.fbx'));
  row('two stacks: both listed by name', fbx.stacks.map(s => s.name).join(',') === 'Idle,Walk', fbx.stacks.map(s => `${s.name} ${r2(s.seconds)} s`).join(', '));
  const idle = fbx.motion(0), walk = fbx.motion(1);
  const iInfo = B.analyze(idle), wInfo = B.analyze(walk);
  const ip = solveM(idle, iInfo), wp = solveM(walk, wInfo);
  const still = poseDiff(ip.slice(0, 1).concat(ip.slice(0, 1)), [ip[0], ip[ip.length - 1]]);
  row('two stacks: "Idle" holds still', still.worst < 0.01, `first vs last frame ${r2(still.worst)} deg`);
  const d = poseDiff(wp, refPoses);
  row('two stacks: "Walk" (the second) equals the BVH import', d.worst < 0.5, `worst ${r2(d.worst)} deg (${d.where})`);
  // the rest is put back after a stack is sampled: "Walk" read first, or after "Idle", is the same
  const fresh = (await F.readFBX(bytes('body_two_stacks.fbx'))).motion(1);
  let most = 0;
  for (let k = 0; k < walk.sampled.P.length; k++) most = Math.max(most, Math.abs(walk.sampled.P[k] - fresh.sampled.P[k]));
  for (let k = 0; k < walk.sampled.Q.length; k++) most = Math.max(most, Math.abs(walk.sampled.Q[k] - fresh.sampled.Q[k]));
  row('two stacks: sampling one does not disturb the other', most === 0, `"Walk" after "Idle" vs "Walk" alone: largest difference ${most}`);
}
{
  const msg = await errOf(() => F.readFBX(bytes('skeleton_only.fbx')));
  row('a skeleton without animation: a plain message', msg && /no animation/.test(msg) && !msg.startsWith('OTHER'), msg);
  const full = new Uint8Array(bytes('body_mixamo_binary.fbx'));
  const cut = await errOf(() => F.readFBX(full.slice(0, 5000).buffer));
  row('a cut-off binary file: a plain message', cut && !cut.startsWith('OTHER'), cut);
  const old = await errOf(() => F.readFBX(new TextEncoder().encode('; FBX 6.1.0 project file\nFBXHeaderExtension:  {\n\tFBXHeaderVersion: 1003\n\tFBXVersion: 6100\n}\n').buffer));
  row('an FBX 6 file: "too old, export FBX 7 or BVH"', old && /too old/.test(old), old);
  const junk = await errOf(() => F.readFBX(new TextEncoder().encode('hello, this is not an fbx').buffer));
  row('a file that is not FBX: a plain message', junk && !junk.startsWith('OTHER'), junk);
  row('.fbx files are recognised; BVH and FBX get no "unsupported" message', F.isFBX('Walk.FBX') && F.isFBX('x', 'Kaydara FBX Binary  ') && F.isFBX('x', '; FBX 7.4.0 project file')
    && !F.isFBX('walk.bvh', 'HIERARCHY') && B.formatProblem('a.fbx', '') === null && B.formatProblem('a.bvh', '') === null && /BVH and FBX/.test(B.formatProblem('a.glb', '') || ''));
}

// ---------------------------------------------------------------- report
const w = Math.max(...rows.map(r => r.name.length));
console.log('\nMotion files (FBX) - reading and retargeting\n' + '-'.repeat(w + 20));
for (const r of rows) console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name.padEnd(w)}  ${String(r.detail).slice(0, 230)}`);
const bad = rows.filter(r => !r.ok).length;
console.log('-'.repeat(w + 20) + `\n${rows.length - bad} PASS, ${bad} FAIL`);
process.exit(bad ? 1 : 0);
