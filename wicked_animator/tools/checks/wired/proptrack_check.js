// Props for the game: the prop track maths (web/js/proptrack.js) in Node (no browser, nothing written).
//   node tools/checks/wired/proptrack_check.js
// Forward kinematics over baked tracks against hand-worked answers, and - when three.js is found (WA_THREE_DIR or
// node's own 'three') - against three.js's own skeleton on a random chain; a held prop follows its bone with its
// offset, a standing prop stays put, and a prop whose holder is gone is left out.
const fs = require('fs');
const path = require('path');
const H = require('../lib/harness.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const load = async () => import('data:text/javascript;base64,' + Buffer.from(fs.readFileSync(path.join(ROOT, 'web', 'js', 'proptrack.js'), 'utf8')).toString('base64'));
const close = (a, b, eps = 1e-6) => a && b && a.length === b.length && a.every((x, i) => Math.abs(x - b[i]) < eps);
const qy = deg => { const h = deg * Math.PI / 360; return [0, Math.sin(h), 0, Math.cos(h)]; };

async function three() {
  const dirs = [process.env.WA_THREE_DIR];
  try { dirs.push(path.dirname(require.resolve('three/package.json'))); } catch { /* not installed */ }
  for (const d of dirs) {
    const f = d && path.join(d, 'build', 'three.module.js');
    if (f && fs.existsSync(f)) return import('file://' + f);
  }
  return null;
}

(async () => {
  const T = await load();
  const rows = [];
  const row = (name, ok, detail) => rows.push({ name, ok: !!ok, detail });
  const rig = { bones: [
    { name: 'b__ROOT__', parent: -1, pos: [0, 0, 0], rot: [0, 0, 0, 1], scale: [1, 1, 1] },
    { name: 'b__Arm__', parent: 0, pos: [0, 1, 0], rot: [0, 0, 0, 1], scale: [1, 1, 1] },
    { name: 'b__Hand__', parent: 1, pos: [1, 0, 0], rot: [0, 0, 0, 1], scale: [1, 1, 1] },
    { name: 'b__R_Prop__', parent: 2, pos: [0.1, 0, 0], rot: [0, 0, 0, 1], scale: [1, 1, 1] },
  ] };
  const tracks = { b__Arm__: { r: [[0, 0, 0, 1], qy(90), qy(180)] }, b__Hand__: { t: [[1, 0, 0], [2, 0, 0], [1, 0, 0]] } };
  const w0 = T.boneWorld(rig, tracks, 'b__R_Prop__', 0), w1 = T.boneWorld(rig, tracks, 'b__R_Prop__', 1), w2 = T.boneWorld(rig, tracks, 'b__R_Prop__', 2);
  row('rest: the prop bone at (1.1, 1, 0)', close(w0.pos, [1.1, 1, 0]) && close(w0.quat, [0, 0, 0, 1]), JSON.stringify(w0));
  row('arm turned 90 deg, hand 2 m out: at (0, 1, -2.1)', close(w1.pos, [0, 1, -2.1]) && close(w1.quat, qy(90)), JSON.stringify(w1));
  row('turned 180 deg: at (-1.1, 1, 0)', close(w2.pos, [-1.1, 1, 0]), JSON.stringify(w2.pos));
  row('a bone past the last frame keeps the last value', close(T.boneWorld(rig, tracks, 'b__R_Prop__', 9).pos, w2.pos), '');
  row('an unknown bone gives null', T.boneWorld(rig, tracks, 'b__Nope__', 0) === null, '');
  const scaled = { bones: rig.bones.map(b => (b.name === 'b__Arm__' ? { ...b, scale: [2, 2, 2] } : b)) };
  row("a parent's scale stretches its children's places", close(T.boneWorld(scaled, {}, 'b__Hand__', 0).pos, [2, 1, 0]), JSON.stringify(T.boneWorld(scaled, {}, 'b__Hand__', 0).pos));

  const sims = [{ id: 's1' }, { id: 's2' }];
  const actors = [{ tracks: {} }, { tracks }];
  const held = T.propTrack({ hold: { sim: 's2', bone: 'b__R_Prop__', offset: { pos: [0, 0, 0.2], quat: qy(90) } } }, { rig, actors, sims, frames: 3 });
  row('held: follows the bone, with its offset in the hand', held.t.length === 3 && close(held.t[0], [1.1, 1, 0.2], 1e-5) && close(held.t[1], [0.2, 1, -2.1], 1e-5)
    && close(held.r[1], [0, 1, 0, 0], 1e-5), JSON.stringify(held.t));           // 90 deg arm + 90 deg in the hand
  const still = T.propTrack({ at: { pos: [0.3, 0.8, 0.1], quat: qy(45) } }, { rig, actors, sims, frames: 4 });
  row('standing: the same place on every frame', still.t.length === 4 && still.t.every(p => close(p, [0.3, 0.8, 0.1])) && still.r.every(q => close(q, qy(45), 1e-6)), JSON.stringify(still.t[0]));
  const gone = T.propTrack({ hold: { sim: 'nobody', bone: 'b__R_Prop__' } }, { rig, actors, sims, frames: 3 });
  row('held by a sim that is gone: left out (null)', gone === null, '');

  // against three.js on a random chain
  const THREE = await three();
  if (!THREE) row('three.js comparison', true, 'skipped - three.js not found (set WA_THREE_DIR)');
  else {
    let seed = 3;
    const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
    const rq = () => { const q = new THREE.Quaternion(rnd() - 0.5, rnd() - 0.5, rnd() - 0.5, rnd() - 0.5).normalize(); return q.toArray(); };
    const bones = [];
    for (let i = 0; i < 8; i++) bones.push({ name: 'b' + i, parent: i - 1, pos: [rnd() - 0.5, rnd(), rnd() - 0.5], rot: rq(), scale: [1, 1, 1] });
    const rr = { bones };
    const tr = { b2: { r: [rq(), rq()] }, b5: { t: [[0.1, 0.2, 0.3], [0.3, 0.1, 0]], r: [rq(), rq()] } };
    let worst = 0;
    for (const f of [0, 1]) {
      const objs = bones.map(b => new THREE.Object3D());
      bones.forEach((b, i) => {
        const t = tr[b.name] || {};
        objs[i].position.fromArray((t.t && t.t[f]) || b.pos); objs[i].quaternion.fromArray((t.r && t.r[f]) || b.rot);
        if (b.parent >= 0) objs[b.parent].add(objs[i]);
      });
      objs[0].updateMatrixWorld(true);
      const want = objs[7].getWorldPosition(new THREE.Vector3()).toArray();
      const wq = objs[7].getWorldQuaternion(new THREE.Quaternion());
      const got = T.boneWorld(rr, tr, 'b7', f);
      worst = Math.max(worst, Math.hypot(...want.map((x, i) => x - got.pos[i])), new THREE.Quaternion().fromArray(got.quat).angleTo(wq));
    }
    row('the same as three.js on a random 8-bone chain', worst < 1e-6, `worst difference ${worst.toExponential(2)}`);
  }
  const ok = H.report(rows, 'Props: the track for the game (web/js/proptrack.js)');
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
