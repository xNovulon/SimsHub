// A synthetic Sims 4-like rig for the motion-file checks (the real one is read from the game, which a check machine
// may not have). It follows the conventions the capture solver relies on (web/js/capture/retarget.js, rigpose.js):
//   - sim space: Y up, the sim faces +Z, its left is +X;
//   - b__ROOT_bind__'s rest turns local x -> up, y -> forward, z -> left; b__Pelvis__ and b__Spine0__ are its
//     children (both carry the hips' place);
//   - every limb bone's local X runs along the bone to its child; hinges (forearm, calf, finger 1 and 2) turn about
//     their local Z only: forearms and fingers bend towards their parent's +Y, calves towards -Y;
//   - it stands in an A-POSE (arms 45 degrees down, palms in) - so a T-pose file checks the rest-pose handling.
// makeRig({full}) -> {name, bones: [{name, parent, pos, rot, scale, hash, opposite}]} like /api/rig. full: true adds
// every other bone web/js/bones.js names (face, twist, WickedWhims extras, slots) so the whole app can start on it.
import * as THREE from 'three';

const V = (x, y, z) => new THREE.Vector3(x, y, z);
const n = v => v.clone().normalize();

export function makeRig({ full = false } = {}) {
  const list = [];            // {name, parent, P (world), X, Y (world axes)}
  const add = (name, parent, P, X = V(1, 0, 0), Y = V(0, 1, 0)) => {
    X = n(X); Y = Y.clone().sub(X.clone().multiplyScalar(Y.dot(X))).normalize();
    list.push({ name, parent, P: P.clone(), X, Y });
  };
  const UP = V(0, 1, 0), FWD = V(0, 0, 1), LEFT = V(1, 0, 0);
  add('b__ROOT__', null, V(0, 0, 0));
  add('b__ROOT_bind__', 'b__ROOT__', V(0, 0, 0), UP, FWD);
  add('b__Pelvis__', 'b__ROOT_bind__', V(0, 1.0, 0), UP, FWD);
  add('b__Spine0__', 'b__ROOT_bind__', V(0, 1.03, 0), UP, FWD);
  add('b__Spine1__', 'b__Spine0__', V(0, 1.16, 0), UP, FWD);
  add('b__Spine2__', 'b__Spine1__', V(0, 1.30, 0), UP, FWD);
  add('b__Neck__', 'b__Spine2__', V(0, 1.47, 0.0), UP, FWD);
  add('b__Head__', 'b__Neck__', V(0, 1.57, 0.0), UP, FWD);
  add('b__CAS_NoseTip__', 'b__Head__', V(0, 1.66, 0.105), UP, FWD);
  for (const [s, k] of [['L', 1], ['R', -1]]) {
    add(`b__${s}_Eye__`, 'b__Head__', V(0.032 * k, 1.70, 0.075), UP, FWD);
    add(`b__${s}_Mouth__`, 'b__Head__', V(0.024 * k, 1.615, 0.085), UP, FWD);
    // arm (A-pose: 45 degrees down), bending forward
    const dA = n(V(k, -1, 0));
    const sh = V(0.17 * k, 1.42, 0);
    add(`b__${s}_Clavicle__`, 'b__Spine2__', V(0.03 * k, 1.42, 0), V(k, 0, 0), FWD);
    add(`b__${s}_UpperArm__`, `b__${s}_Clavicle__`, sh, dA, FWD);
    const el = sh.clone().add(dA.clone().multiplyScalar(0.28));
    add(`b__${s}_Forearm__`, `b__${s}_UpperArm__`, el, dA, FWD);
    const wr = el.clone().add(dA.clone().multiplyScalar(0.25));
    add(`b__${s}_Hand__`, `b__${s}_Forearm__`, wr, dA, FWD);
    // fingers: palm facing the thigh (inwards and down), thumb forward; they curl towards the palm (+Y)
    const palm = n(V(-k, -1, 0));
    for (const [f, along, side, lens] of [['Index', 0.095, 0.025, [0.04, 0.025, 0.02]], ['Mid', 0.10, 0.008, [0.045, 0.028, 0.021]],
      ['Ring', 0.095, -0.01, [0.042, 0.026, 0.02]], ['Pinky', 0.085, -0.027, [0.033, 0.02, 0.017]]]) {
      let p = wr.clone().add(dA.clone().multiplyScalar(along)).add(FWD.clone().multiplyScalar(side));
      let parent = `b__${s}_Hand__`;
      for (let j = 0; j < 3; j++) {
        add(`b__${s}_${f}${j}__`, parent, p, dA, palm);
        parent = `b__${s}_${f}${j}__`;
        p = p.clone().add(dA.clone().multiplyScalar(lens[j]));
      }
    }
    const tdir = n(dA.clone().add(FWD.clone().multiplyScalar(0.8)));
    let tp = wr.clone().add(dA.clone().multiplyScalar(0.025)).add(FWD.clone().multiplyScalar(0.02)).add(palm.clone().multiplyScalar(0.01));
    let tparent = `b__${s}_Hand__`;
    for (const [j, len] of [[0, 0.04], [1, 0.03], [2, 0.025]]) {
      add(`b__${s}_Thumb${j}__`, tparent, tp, tdir, palm);
      tparent = `b__${s}_Thumb${j}__`;
      tp = tp.clone().add(tdir.clone().multiplyScalar(len));
    }
    // leg, bending backward at the knee (calf: towards the thigh's -Y)
    add(`b__${s}_Thigh__`, 'b__Pelvis__', V(0.09 * k, 0.95, 0), V(0, -1, 0), FWD);
    add(`b__${s}_Calf__`, `b__${s}_Thigh__`, V(0.09 * k, 0.52, 0), V(0, -1, 0), FWD);
    const foot = V(0.09 * k, 0.085, 0), toe = V(0.09 * k, 0.0005, 0.14);
    add(`b__${s}_Foot__`, `b__${s}_Calf__`, foot, toe.clone().sub(foot), UP);
    add(`b__${s}_Toe__`, `b__${s}_Foot__`, toe, FWD, UP);
  }
  if (full) addTheRest(list, add);
  // local transforms (parents first)
  const idx = new Map(list.map((b, i) => [b.name, i]));
  const W = list.map(b => new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(b.X, b.Y, b.X.clone().cross(b.Y))));
  const bones = list.map((b, i) => {
    const p = b.parent === null ? -1 : idx.get(b.parent);
    const Wp = p < 0 ? new THREE.Quaternion() : W[p], Pp = p < 0 ? V(0, 0, 0) : list[p].P;
    const rot = Wp.clone().invert().multiply(W[i]).normalize();
    const pos = b.P.clone().sub(Pp).applyQuaternion(Wp.clone().invert());
    return { name: b.name, parent: p, pos: pos.toArray(), rot: rot.toArray(), scale: [1, 1, 1], hash: i + 1, opposite: -1 };
  });
  for (const b of bones) {
    const m = /^b__(CAS_)?([LR])_/.exec(b.name);
    if (m) { const other = b.name.replace(`${m[2]}_`, `${m[2] === 'L' ? 'R' : 'L'}_`); b.opposite = idx.has(other) ? idx.get(other) : -1; }
  }
  return { name: 'synthetic auRig (tests)', bones };
}

// the rest of the bones the app knows (web/js/bones.js), parked near a sensible parent
function addTheRest(list, add) {
  const have = new Set(list.map(b => b.name));
  const at = name => list.find(b => b.name === name).P;
  const put = (name, parent, dx = 0, dy = 0, dz = 0) => { if (!have.has(name)) { add(name, parent, at(parent).clone().add(V(dx, dy, dz))); have.add(name); } };
  const face = ['UpLid', 'LoLid', 'UpLip', 'LoLip', 'InBrow', 'MidBrow', 'OutBrow', 'Cheek', 'Squint'];
  for (const [s, k] of [['L', 1], ['R', -1]]) {
    for (const f of face) put(`b__${s}_${f}__`, 'b__Head__', 0.03 * k, 0.1, 0.08);
    put(`b__CAS_${s}_Nostril__`, 'b__Head__', 0.01 * k, 0.08, 0.1);
    put(`b__CAS_${s}_Breast__`, 'b__Spine2__', 0.09 * k, -0.05, 0.1);
    put(`b__${s}_Butt__`, 'b__Pelvis__', 0.08 * k, -0.05, -0.1);
    put(`b__${s}_ForearmTwist__`, `b__${s}_Forearm__`, 0.1 * k, -0.1, 0);
    put(`b__${s}_ShoulderTwist__`, `b__${s}_UpperArm__`, 0.07 * k, -0.07, 0);
    put(`b__${s}_ThighTwist__`, `b__${s}_Thigh__`, 0, -0.1, 0);
    put(`b__${s}_Elbow__`, `b__${s}_Forearm__`);
    put(`b__${s}_Skirt__`, 'b__Pelvis__', 0.1 * k, -0.1, 0);
    put(`b__${s}_Anus__`, 'b__Pelvis__', 0.01 * k, -0.08, -0.05);
    put(`b__CAS_${s}_EyeArea__`, 'b__Head__', 0.03 * k, 0.12, 0.07);
    put(`b__CAS_${s}_EyeScale__`, 'b__Head__', 0.03 * k, 0.12, 0.07);
    put(`b__${s}_Prop__`, `b__${s}_Hand__`);
    put(`b__${s}_Stigmata`, `b__${s}_Hand__`);
    put(`b__Penis_${s}_Testicle`, 'b__Pelvis__', 0.01 * k, -0.1, 0.08);
  }
  for (const [nm, parent, dy, dz] of [['b__UpLip__', 'b__Head__', 0.05, 0.1], ['b__LoLip__', 'b__Head__', 0.03, 0.1], ['b__Jaw__', 'b__Head__', 0.02, 0.03],
    ['b__Tounge__1', 'b__Jaw__', 0.02, 0.03], ['b__Tounge__2', 'b__Tounge__1', 0, 0.02], ['b__Tounge__3', 'b__Tounge__2', 0, 0.02],
    ['b__CAS_Glasses__', 'b__Head__', 0.13, 0.1], ['b__CAS_NoseArea__', 'b__Head__', 0.09, 0.1], ['b__CAS_NoseBridge__', 'b__Head__', 0.11, 0.1],
    ['b__CAS_UpperMouthArea__', 'b__Head__', 0.06, 0.1], ['b__CAS_LowerMouthArea__', 'b__Head__', 0.03, 0.1], ['b__CAS_JawComp__', 'b__Head__', 0.02, 0.08],
    ['b__CAS_Chin__', 'b__Head__', 0.0, 0.09], ['b__Carry__', 'b__Spine2__', 0, 0.3], ['b__Penis_Base', 'b__Pelvis__', -0.1, 0.1],
    ['b__Penis_Base01', 'b__Penis_Base', 0, 0.03], ['b__Penis_Mid', 'b__Penis_Base01', 0, 0.03], ['b__Penis_Mid01', 'b__Penis_Mid', 0, 0.03],
    ['b__Penis_Tip', 'b__Penis_Mid01', 0, 0.03], ['b__Penis_Testicles', 'b__Pelvis__', -0.1, 0.07], ['b__Up_Vagina__', 'b__Pelvis__', -0.1, 0.05],
    ['b__Low_Vagina__', 'b__Pelvis__', -0.12, 0.04], ['b__Anus', 'b__Pelvis__', -0.1, -0.05], ['b__Up_Anus', 'b__Anus', 0.01, 0], ['b__Low_Anus', 'b__Anus', -0.01, 0]]) {
    put(nm, parent, 0, dy, dz);
  }
}
