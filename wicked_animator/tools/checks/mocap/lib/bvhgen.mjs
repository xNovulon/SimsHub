// Writes the synthetic BVH files the motion-file checks read (tools/checks/mocap/fixtures). One body and one known
// motion, written the ways real files differ:
//   names:  'mixamo' (mixamorig:LeftUpLeg, with fingers), 'cmu' (LHipJoint, LowerBack, Neck1, LThumb), 'daz'
//           (hip, lThigh, lShin, lShldr), 'biped' (Bip01 L Thigh), 'deepmotion' (l_upleg_JNT), 'kinect'
//           (ShoulderLeft, ElbowLeft - the shoulder joint is the arm)
//   axes:   Y up (the default) or Z up (Blender); units: centimetres (the default) or metres
//   rest:   T-pose (the default) or A-pose (arms 45 degrees down in the OFFSETs; the motion is the same in the world)
//   fps:    any frame rate (the motion is a function of time)
//   orders: every joint's rotation channel order can be chosen (ZXY, XYZ, ZYX, YXZ...)
import * as THREE from 'three';

const D2R = Math.PI / 180;
const q = (x, y, z, deg) => new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(x, y, z).normalize(), deg * D2R);

// ---------------------------------------------------------------- the body (T-pose, cm, Y up, facing +Z, left = +X)
// [key, parent key, offset]
export function bodyJoints({ fingers = true } = {}) {
  const J = [['hips', null, [0, 98, 0]], ['spine', 'hips', [0, 8, 0]], ['spine1', 'spine', [0, 12, 0]], ['spine2', 'spine1', [0, 12, 0]],
    ['neck', 'spine2', [0, 16, 0]], ['head', 'neck', [0, 9, 1]]];
  for (const [s, k] of [['L', 1], ['R', -1]]) {
    J.push([`${s}.clav`, 'spine2', [3 * k, 12, 0]], [`${s}.arm`, `${s}.clav`, [13 * k, 0, 0]], [`${s}.fore`, `${s}.arm`, [27 * k, 0, 0]],
      [`${s}.hand`, `${s}.fore`, [25 * k, 0, 0]]);
    if (fingers) {
      for (const [f, o, segs] of [['Thumb', [2.5, -1, 3], [[3, 0, 2], [2.5, 0, 1.5], [2, 0, 1]]], ['Index', [9, 0, 2.5], [[4, 0, 0], [2.5, 0, 0], [2, 0, 0]]],
        ['Middle', [9.5, 0, 0.8], [[4.5, 0, 0], [2.8, 0, 0], [2.1, 0, 0]]], ['Ring', [9, 0, -0.9], [[4.2, 0, 0], [2.6, 0, 0], [2, 0, 0]]],
        ['Pinky', [8, 0, -2.5], [[3.3, 0, 0], [2, 0, 0], [1.7, 0, 0]]]]) {
        J.push([`${s}.${f}1`, `${s}.hand`, [o[0] * k, o[1], o[2]]]);
        segs.forEach((sg, i) => J.push([`${s}.${f}${i + 2}`, `${s}.${f}${i + 1}`, [sg[0] * k, sg[1], sg[2]]]));
      }
    }
    J.push([`${s}.upleg`, 'hips', [9 * k, -6, 0]], [`${s}.leg`, `${s}.upleg`, [0, -43, 0]], [`${s}.foot`, `${s}.leg`, [0, -41, 0]],
      [`${s}.toe`, `${s}.foot`, [0, -7, 12]]);
  }
  return J;
}
// End Sites (key -> offset)
export const ENDS = { head: [0, 18, 0], 'L.toe': [0, 0, 5], 'R.toe': [0, 0, 5], 'L.hand': [8, 0, 0], 'R.hand': [-8, 0, 0] };
for (const s of ['L', 'R']) for (const f of ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']) ENDS[`${s}.${f}4`] = [s === 'L' ? 0.6 : -0.6, 0, 0];

// ---------------------------------------------------------------- the motion (local turns in the T-pose's frames)
// motionAt(t) -> {root: [x, y, z] cm, q: {key: Quaternion}}. Two seconds: walking forward 50 cm/s with a bounce, the
// hips swaying, the left arm down and swinging with the elbow bending 40..100 degrees, the right arm lower with a
// 45..75 degree elbow, the legs stepping (knees 25..75), the head turning +-30 degrees and nodding, the left index
// finger curling 0..60 degrees at each joint, the right one straight.
export function motionAt(t) {
  const w = 2 * Math.PI * t / 2, s = Math.sin(w), c = Math.cos(w);
  const Q = {};
  Q.hips = q(0, 1, 0, 10 * s);
  Q.spine1 = q(1, 0, 0, 8 + 6 * s);
  Q.spine2 = q(0, 1, 0, -6 * s);
  Q.neck = q(1, 0, 0, 5 * c);
  Q.head = q(0, 1, 0, 30 * s).multiply(q(1, 0, 0, 10 * c));
  Q['L.arm'] = q(0, 1, 0, -25 * s).multiply(q(0, 0, 1, -60));                  // down 60, swinging forward and back
  Q['L.fore'] = q(0, 1, 0, -(70 + 30 * s));                                   // elbow 40..100, bending forward
  Q['L.hand'] = q(0, 0, 1, 15 * c).multiply(q(1, 0, 0, 20 * s));
  Q['R.arm'] = q(0, 1, 0, 20 * s).multiply(q(0, 0, 1, 70));
  Q['R.fore'] = q(0, 1, 0, 60 + 15 * c);                                      // elbow 45..75 (the right arm bends about +Y)
  Q['R.hand'] = q(1, 0, 0, -15 * c);
  Q['L.upleg'] = q(1, 0, 0, -(20 + 25 * s));
  Q['L.leg'] = q(1, 0, 0, 50 + 25 * s);                                       // knee 25..75, bending backward
  Q['L.foot'] = q(1, 0, 0, 10 * c);
  Q['R.upleg'] = q(1, 0, 0, -(20 - 25 * s));
  Q['R.leg'] = q(1, 0, 0, 50 - 25 * s);
  const curl = 30 + 30 * s;                                                   // 0..60
  for (let i = 1; i <= 3; i++) Q[`L.Index${i}`] = q(0, 0, 1, -curl);
  return { root: [0, 98 + 3 * Math.sin(2 * w), 50 * t], q: Q };
}

// ---------------------------------------------------------------- naming schemes
const SIDE_WORD = { L: 'Left', R: 'Right' };
const FINGER_NAME = { Thumb: 'Thumb', Index: 'Index', Middle: 'Middle', Ring: 'Ring', Pinky: 'Pinky' };
export function namer(style) {
  return key => {
    const [s, part] = key.includes('.') ? key.split('.') : [null, key];
    const fm = part && /^(Thumb|Index|Middle|Ring|Pinky)(\d)$/.exec(part);
    const L = s && SIDE_WORD[s];
    switch (style) {
      case 'mixamo': {
        const c = { hips: 'Hips', spine: 'Spine', spine1: 'Spine1', spine2: 'Spine2', neck: 'Neck', head: 'Head' };
        if (!s) return 'mixamorig:' + c[part];
        if (fm) return `mixamorig:${L}Hand${FINGER_NAME[fm[1]]}${fm[2]}`;
        return 'mixamorig:' + L + { clav: 'Shoulder', arm: 'Arm', fore: 'ForeArm', hand: 'Hand', upleg: 'UpLeg', leg: 'Leg', foot: 'Foot', toe: 'ToeBase' }[part];
      }
      case 'cmu': {
        const c = { hips: 'Hips', spine: 'Spine', spine1: 'Spine1', spine2: 'Neck', neck: 'Neck1', head: 'Head' };
        if (!s) return c[part];
        if (fm) return fm[1] === 'Thumb' ? `${s}Thumb${fm[2]}` : `${L}Hand${FINGER_NAME[fm[1]]}${fm[2]}`;
        return L + { clav: 'Shoulder', arm: 'Arm', fore: 'ForeArm', hand: 'Hand', upleg: 'UpLeg', leg: 'Leg', foot: 'Foot', toe: 'ToeBase' }[part];
      }
      case 'daz': {
        const c = { hips: 'hip', spine: 'abdomen', spine1: 'abdomen2', spine2: 'chest', neck: 'neck', head: 'head' };
        if (!s) return c[part];
        if (fm) return `${s.toLowerCase()}${FINGER_NAME[fm[1]]}${fm[2]}`;
        return s.toLowerCase() + { clav: 'Collar', arm: 'Shldr', fore: 'ForeArm', hand: 'Hand', upleg: 'Thigh', leg: 'Shin', foot: 'Foot', toe: 'Toe' }[part];
      }
      case 'biped': {
        const c = { hips: 'Bip01 Pelvis', spine: 'Bip01 Spine', spine1: 'Bip01 Spine1', spine2: 'Bip01 Spine2', neck: 'Bip01 Neck', head: 'Bip01 Head' };
        if (!s) return c[part];
        if (fm) return `Bip01 ${s} Finger${'TIMRP'.indexOf(fm[1][0])}${fm[2] - 1 || ''}`;
        return `Bip01 ${s} ` + { clav: 'Clavicle', arm: 'UpperArm', fore: 'Forearm', hand: 'Hand', upleg: 'Thigh', leg: 'Calf', foot: 'Foot', toe: 'Toe0' }[part];
      }
      case 'deepmotion': {
        const c = { hips: 'hips_JNT', spine: 'spine_JNT', spine1: 'spine1_JNT', spine2: 'spine2_JNT', neck: 'neck_JNT', head: 'head_JNT' };
        if (!s) return c[part];
        const sl = s.toLowerCase();
        if (fm) return `${sl}_hand${FINGER_NAME[fm[1]]}${fm[2]}_JNT`;
        return `${sl}_` + { clav: 'shoulder', arm: 'arm', fore: 'forearm', hand: 'hand', upleg: 'upleg', leg: 'leg', foot: 'foot', toe: 'toebase' }[part] + '_JNT';
      }
      case 'kinect': {
        const c = { hips: 'Hips', spine: 'SpineBase', spine1: 'SpineMid', spine2: 'SpineShoulder', neck: 'Neck', head: 'Head' };
        if (!s) return c[part];
        if (fm) return `${FINGER_NAME[fm[1]]}${fm[2]}${L}`;
        return { clav: 'Clavicle', arm: 'Shoulder', fore: 'Elbow', hand: 'Wrist', upleg: 'Hip', leg: 'Knee', foot: 'Ankle', toe: 'Foot' }[part] + L;
      }
      default: throw new Error('unknown naming ' + style);
    }
  };
}

// ---------------------------------------------------------------- writing
// writeBVH({names, fingers, zUp, metres, apose, fps, seconds, orders, rootOrder, motion}) -> BVH text
export function writeBVH({ names = 'mixamo', fingers = true, zUp = false, metres = false, apose = false, fps = 30, seconds = 2,
  order = 'ZXY', rootOrder = 'ZXY', orders = {}, motion = motionAt, frames = null } = {}) {
  const joints = bodyJoints({ fingers });
  const name = namer(names);
  // CMU's helpers: LHipJoint / RHipJoint between the hips and the thighs, LowerBack between the hips and the spine
  const list = [];
  for (const [key, parent, off] of joints) {
    if (names === 'cmu' && /^[LR]\.upleg$/.test(key)) {
      const s = key[0];
      list.push({ key: `${s}.hipjoint`, name: `${s}HipJoint`, parent, off: [0, 0, 0] });
      list.push({ key, name: name(key), parent: `${s}.hipjoint`, off });
      continue;
    }
    if (names === 'cmu' && key === 'spine') {
      list.push({ key: 'lowerback', name: 'LowerBack', parent, off: [0, 0, 0] });
      list.push({ key, name: name(key), parent: 'lowerback', off });
      continue;
    }
    list.push({ key, name: name(key), parent, off });
  }
  // A-pose: the arm subtrees' rest turned 45 degrees down about the forward axis (G); the motion stays the same in
  // the world: local(arm) = local_T(arm) G^-1, local(below) = G local_T G^-1
  const G = { L: q(0, 0, 1, -45), R: q(0, 0, 1, 45) };
  const armSide = key => { const m = /^([LR])\.(fore|hand|Thumb|Index|Middle|Ring|Pinky)/.exec(key); return m ? m[1] : null; };
  const isArm = key => /^[LR]\.arm$/.test(key);
  const restOff = j => {
    const v = new THREE.Vector3(...j.off);
    const s = armSide(j.key);
    if (apose && s) v.applyQuaternion(G[s]);
    return v;
  };
  // axes: Z up = the Y-up world turned +90 degrees about X (y -> z, z -> -y)
  const A = zUp ? q(1, 0, 0, 90) : new THREE.Quaternion();
  const unit = metres ? 0.01 : 1;
  const fmt = x => (Math.abs(x) < 5e-5 ? '0' : x.toFixed(4));
  const vec = v => { const w = v.clone().applyQuaternion(A).multiplyScalar(unit); return `${fmt(w.x)} ${fmt(w.y)} ${fmt(w.z)}`; };
  const chanOrder = key => (key === 'hips' ? rootOrder : orders[key] || order);
  const lines = ['HIERARCHY'];
  const kids = p => list.filter(j => j.parent === p);
  const endOf = key => {
    if (!ENDS[key]) return null;
    const v = new THREE.Vector3(...ENDS[key]);
    const s = armSide(key);
    if (apose && s) v.applyQuaternion(G[s]);
    return v;
  };
  const emit = (j, depth) => {
    const ind = '  '.repeat(depth);
    lines.push(`${ind}${j.parent ? 'JOINT' : 'ROOT'} ${j.name}`, `${ind}{`, `${ind}  OFFSET ${vec(restOff(j))}`);
    const rot = chanOrder(j.key).split('').map(a => `${a}rotation`).join(' ');
    lines.push(j.parent ? `${ind}  CHANNELS 3 ${rot}` : `${ind}  CHANNELS 6 Xposition Yposition Zposition ${rot}`);
    const ch = kids(j.key);
    for (const c of ch) emit(c, depth + 1);
    const e = endOf(j.key);
    if (!ch.length || e) {
      const v = e || new THREE.Vector3(0, 5, 0);
      lines.push(`${ind}  End Site`, `${ind}  {`, `${ind}    OFFSET ${vec(v)}`, `${ind}  }`);
    }
    lines.push(`${ind}}`);
  };
  emit(list[0], 0);
  const order_ = [];
  const walk = j => { order_.push(j); for (const c of kids(j.key)) walk(c); };
  walk(list[0]);
  const n = frames || Math.round(seconds * fps) + 1;
  lines.push('MOTION', `Frames: ${n}`, `Frame Time: ${(1 / fps).toFixed(7)}`);
  for (let i = 0; i < n; i++) {
    const m = motion(i / fps);
    const vals = [];
    for (const j of order_) {
      let lq = (m.q[j.key] || new THREE.Quaternion()).clone();
      const s = armSide(j.key);
      if (apose && isArm(j.key)) lq = lq.multiply(G[j.key[0]].clone().invert());
      else if (apose && s) lq = G[s].clone().multiply(lq).multiply(G[s].clone().invert());
      // Z up: every turn is seen in the turned world (A q A^-1)
      lq = A.clone().multiply(lq).multiply(A.clone().invert());
      const ord = chanOrder(j.key);
      const e = new THREE.Euler().setFromQuaternion(lq, ord);
      const rot = ord.split('').map(a => fmt(e[a.toLowerCase()] / D2R));
      if (!j.parent) vals.push(vec(new THREE.Vector3(...m.root)), ...rot);
      else vals.push(...rot);
    }
    lines.push(vals.join(' '));
  }
  return lines.join('\n') + '\n';
}
