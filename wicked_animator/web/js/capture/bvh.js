// Motion files (BVH) for "Copy real moves": a .bvh from a mocap library (CMU, Mixamo converted to BVH) or a free AI
// video tool (Rokoko Vision, DeepMotion, Plask) becomes the same kind of "take" the video capture makes, so it goes
// through the capture pipeline unchanged: clean.js (30 fps, optional smoothing) -> retarget.js (the solver, hips
// place, floor, sticky feet) -> keys.js (loop, keys on a sim).
//
//   parseBVH(text)                 -> bvh {joints, frames, frameTime, channels, data, warnings}
//   fk(bvh, frame)                 -> {P: Float64Array(J*3), Q: Float64Array(J*4)} world positions and turns
//   analyze(bvh)                   -> which joint is which body part, the rest pose's up / left / forward, units, ...
//   buildTake(bvh, info, rig, opt) -> a capture take (pose landmarks in sim space, hands when the file has fingers)
//
// Why a take and not a bone-by-bone copy: a take is made of joint PLACES, and the solver turns the sim's bones to
// match directions. So the file's rest pose (T-pose or A-pose), its up axis (Y or Z), its units (cm, m, inches)
// and its bone axes never matter - only where its joints are. Points the file has no joint for (ears, eyes, heels,
// knuckles without fingers) are fixed to its head, foot and hand joints where they sit on the game's rig at rest.
import * as THREE from 'three';
import { PL, FINGERS } from './rigpose.js';
import { cleanTake, resample, FPS } from './clean.js';
import { Solver, solveTake } from './retarget.js';
import { findLoop, closeLoop, seamError } from './keys.js';

// ---------------------------------------------------------------- parsing
const CHANNELS = ['Xposition', 'Yposition', 'Zposition', 'Xrotation', 'Yrotation', 'Zrotation'];
const CH_LOWER = Object.fromEntries(CHANNELS.map(c => [c.toLowerCase(), c]));

export class BVHError extends Error {}

// parseBVH(text) -> { joints: [{name, parent, offset: [x, y, z], channels: ['Zrotation', ...], chanStart, end: [x, y, z] | null,
//                     children: [index]}], frames, frameTime, fps, channels (per frame), data: Float32Array, warnings }
// Joint names may contain spaces ("Bip01 L Thigh"). Parents always come before their children.
export function parseBVH(text) {
  if (typeof text !== 'string') throw new BVHError('That is not a text file.');
  const src = text.replace(/^﻿/, '');
  const lines = src.split(/\r\n|\r|\n/);
  let li = 0;
  const next = () => { while (li < lines.length) { const s = lines[li++].trim(); if (s) return s; } return null; };
  const first = next();
  if (!first || !/^HIERARCHY\b/i.test(first)) throw new BVHError("This doesn't look like a BVH file (it should start with HIERARCHY).");
  const joints = [], warnings = [];
  let chanCount = 0;
  // a stack of open blocks: {joint index} or {end: parent index}
  const stack = [];
  let pending = null;                       // the joint (or end site) whose '{' is expected next
  const num = (s, what) => { const v = Number(s); if (!Number.isFinite(v)) throw new BVHError(`A number in ${what} can't be read ("${s}").`); return v; };
  for (;;) {
    let line = next();
    if (line === null) throw new BVHError('The file ends before its MOTION part.');
    if (/^MOTION\b/i.test(line)) { if (stack.length) throw new BVHError('The skeleton part is not closed (a "}" is missing).'); break; }
    // "{" and "}" may share a line with other words
    const opens = line.endsWith('{') && line !== '{';
    if (opens) line = line.slice(0, -1).trim();
    const m = /^(ROOT|JOINT)\s+(.+)$/i.exec(line);
    if (m) {
      const parent = m[1].toUpperCase() === 'ROOT' ? -1 : (stack.length ? stack[stack.length - 1].joint : undefined);
      if (parent === undefined || (parent !== -1 && parent === null)) throw new BVHError(`The joint "${m[2]}" is outside any other joint.`);
      if (m[1].toUpperCase() === 'ROOT' && stack.length) throw new BVHError('A second ROOT sits inside the first one.');
      joints.push({ name: m[2].trim(), parent, offset: [0, 0, 0], channels: [], chanStart: chanCount, end: null, children: [] });
      if (parent >= 0) joints[parent].children.push(joints.length - 1);
      pending = { joint: joints.length - 1 };
      if (opens) { stack.push(pending); pending = null; }
      continue;
    }
    if (/^End\s+Site$/i.test(line) || /^End$/i.test(line)) {
      if (!stack.length) throw new BVHError('An "End Site" is outside any joint.');
      pending = { joint: null, end: stack[stack.length - 1].joint };
      if (opens) { stack.push(pending); pending = null; }
      continue;
    }
    if (line === '{' || opens) {
      if (!pending) throw new BVHError('A "{" is in the wrong place.');
      stack.push(pending); pending = null;
      continue;
    }
    if (line === '}') {
      if (!stack.length) throw new BVHError('There is one "}" too many.');
      stack.pop();
      continue;
    }
    const w = line.split(/\s+/);
    const key = w[0].toUpperCase();
    const top = stack[stack.length - 1];
    if (key === 'OFFSET') {
      if (!top) throw new BVHError('An OFFSET is outside any joint.');
      const v = [num(w[1], 'an OFFSET'), num(w[2], 'an OFFSET'), num(w[3], 'an OFFSET')];
      if (top.joint === null) joints[top.end].end = v; else joints[top.joint].offset = v;
      continue;
    }
    if (key === 'CHANNELS') {
      if (!top || top.joint === null) throw new BVHError('CHANNELS are outside a joint.');
      const n = num(w[1], 'CHANNELS') | 0;
      const names = w.slice(2, 2 + n).map(c => CH_LOWER[c.toLowerCase()]);
      if (names.length !== n || names.some(c => !c)) throw new BVHError(`The joint "${joints[top.joint].name}" has channels this app can't read (${w.slice(2).join(' ')}).`);
      const j = joints[top.joint];
      j.channels = names; j.chanStart = chanCount;
      chanCount += n;
      continue;
    }
    throw new BVHError(`A line in the skeleton part can't be read: "${line.slice(0, 60)}"`);
  }
  if (!joints.length) throw new BVHError('The file has no skeleton.');
  // MOTION: Frames, Frame Time, then the numbers (one frame per line - but any layout is read)
  let frames = null, frameTime = null;
  for (let k = 0; k < 2; k++) {
    const line = next();
    if (line === null) break;
    let mm;
    if ((mm = /^Frames\s*:\s*(\S+)/i.exec(line))) frames = Math.max(0, Math.floor(Number(mm[1])) || 0);
    else if ((mm = /^Frame\s*Time\s*:\s*(\S+)/i.exec(line))) frameTime = Number(mm[1]);
    else { li--; break; }
  }
  const rest = lines.slice(li).join(' ').trim();
  const values = rest ? rest.split(/\s+/) : [];
  if (frames === null) { frames = chanCount ? Math.floor(values.length / chanCount) : 0; warnings.push('The file does not say how many frames it has; all complete frames were read.'); }
  if (!(frameTime > 0) || !Number.isFinite(frameTime)) { warnings.push("The file's frame time is missing, so 30 frames a second is used."); frameTime = 1 / 30; }
  const have = chanCount ? Math.floor(values.length / chanCount) : frames;
  if (chanCount && have < frames) { warnings.push(`The file says ${frames} frames but has ${have}; the ${have} were read.`); frames = have; }
  if (!frames) throw new BVHError('The file has no frames of motion.');
  // "Frame Time: 0.0333333" is 30 fps: a frame time written with few digits is snapped to the usual rate it means,
  // so a 2-second file stays 61 frames on the app's 30 fps grid
  const nice = [24, 25, 30, 48, 50, 60, 90, 100, 120, 240].find(r => Math.abs(1 / frameTime - r) / r < 5e-4);
  if (nice) frameTime = 1 / nice;
  const data = new Float32Array(frames * chanCount);
  for (let i = 0; i < data.length; i++) {
    const v = Number(values[i]);
    if (!Number.isFinite(v)) throw new BVHError(`Frame ${Math.floor(i / chanCount) + 1} has something that is not a number ("${String(values[i]).slice(0, 20)}").`);
    data[i] = v;
  }
  return { joints, frames, frameTime, fps: 1 / frameTime, channels: chanCount, data, warnings };
}

// ---------------------------------------------------------------- forward kinematics
const _q = new THREE.Quaternion(), _qa = new THREE.Quaternion(), _v = new THREE.Vector3();
const AXES = { X: new THREE.Vector3(1, 0, 0), Y: new THREE.Vector3(0, 1, 0), Z: new THREE.Vector3(0, 0, 1) };
const D2R = Math.PI / 180;

// A joint's own turn in a frame: the rotation channels applied in the order they are listed (R = R1 * R2 * R3).
export function localQuat(bvh, j, frame, target = new THREE.Quaternion()) {
  const jt = bvh.joints[j];
  target.identity();
  if (frame === null || frame === undefined) return target;
  const base = frame * bvh.channels + jt.chanStart;
  jt.channels.forEach((c, k) => {
    if (c[1] !== 'r') return;
    target.multiply(_qa.setFromAxisAngle(AXES[c[0]], bvh.data[base + k] * D2R));
  });
  return target;
}

// fk(bvh, frame) -> {P, Q} in the file's own axes and units. frame null = the rest pose (every channel 0, the root at
// its OFFSET). Position channels replace the OFFSET part they cover (Blender's reading of the format).
export function fk(bvh, frame, out = null) {
  const J = bvh.joints.length;
  out = out || { P: new Float64Array(J * 3), Q: new Float64Array(J * 4) };
  const P = out.P, Q = out.Q, t = new THREE.Vector3(), qp = new THREE.Quaternion();
  for (let j = 0; j < J; j++) {
    const jt = bvh.joints[j];
    t.fromArray(jt.offset);
    if (frame !== null && frame !== undefined) {
      const base = frame * bvh.channels + jt.chanStart;
      jt.channels.forEach((c, k) => { if (c[1] === 'p') t.setComponent('XYZ'.indexOf(c[0]), bvh.data[base + k]); });
    }
    localQuat(bvh, j, frame, _q);
    if (jt.parent < 0) {
      P[j * 3] = t.x; P[j * 3 + 1] = t.y; P[j * 3 + 2] = t.z;
      Q[j * 4] = _q.x; Q[j * 4 + 1] = _q.y; Q[j * 4 + 2] = _q.z; Q[j * 4 + 3] = _q.w;
      continue;
    }
    const p = jt.parent;
    qp.fromArray(Q, p * 4);
    t.applyQuaternion(qp);
    P[j * 3] = P[p * 3] + t.x; P[j * 3 + 1] = P[p * 3 + 1] + t.y; P[j * 3 + 2] = P[p * 3 + 2] + t.z;
    qp.multiply(_q);
    Q[j * 4] = qp.x; Q[j * 4 + 1] = qp.y; Q[j * 4 + 2] = qp.z; Q[j * 4 + 3] = qp.w;
  }
  return out;
}

// the world place of a joint's End Site (or null)
function endPoint(bvh, pose, j, target = new THREE.Vector3()) {
  const e = bvh.joints[j].end;
  if (!e) return null;
  return target.fromArray(e).applyQuaternion(_q.fromArray(pose.Q, j * 4)).add(_v.fromArray(pose.P, j * 3));
}

// ---------------------------------------------------------------- which joint is which
// Names are read the way the common skeletons spell them:
//   Mixamo / MotionBuilder / Rokoko:  mixamorig:Hips, LeftUpLeg, LeftLeg, LeftFoot, LeftToeBase, LeftShoulder,
//                                     LeftArm, LeftForeArm, LeftHand, LeftHandIndex1..4, Neck, Head
//   CMU (cgspeed):                    Hips, LHipJoint, LeftUpLeg, ..., LowerBack, Spine1, Neck1, LThumb
//   DeepMotion / game rigs:           l_upleg_JNT, hips_JNT, ... ; Daz / Second Life: hip, lThigh, lShin, lShldr
//   3ds Max Biped:                    Bip01 Pelvis, Bip01 L Thigh, Bip01 L Calf, Bip01 L UpperArm, Bip01 L Forearm
// When a name is not known, the chain decides: a hand's parent is the elbow and its grandparent the shoulder, a
// foot's parent the knee and its grandparent the hip (twist and roll helpers are stepped over).
const SKIP = /roll|twist|nub|_end$|end$|site|helper|ik$|pole|target|dummy/i;

export function nameParts(raw) {
  let s = String(raw || '').trim();
  s = s.replace(/^.*[:|]/, '');                                   // namespaces: mixamorig:Hips, Character1:Hips
  s = s.replace(/^mixamorig\d*_?/i, '').replace(/^(bip|bip0|bip00)\d*[\s_]+/i, '').replace(/^character\d*_/i, '');
  s = s.replace(/_?(jnt|joint|bone|bn|jt)$/i, m => (/hipjoint/i.test(s) ? m : ''));
  let side = '';
  const tests = [
    [/^left[\s_.-]*|[\s_.-]*left$/i, 'L'], [/^right[\s_.-]*|[\s_.-]*right$/i, 'R'],
    [/^l[\s_.-]+|[\s_.-]+l$/i, 'L'], [/^r[\s_.-]+|[\s_.-]+r$/i, 'R'],
    [/(^|[\s_.-])l([\s_.-])/i, 'L', true], [/(^|[\s_.-])r([\s_.-])/i, 'R', true],
    [/^[lL](?=[A-Z])/, 'L'], [/^[rR](?=[A-Z])/, 'R'],
  ];
  for (const [rx, sd, mid] of tests) {
    if (rx.test(s)) { side = sd; s = mid ? s.replace(rx, '$1$2') : s.replace(rx, ''); break; }
  }
  if (!side && /left/i.test(s)) { side = 'L'; s = s.replace(/left/i, ''); }
  else if (!side && /right/i.test(s)) { side = 'R'; s = s.replace(/right/i, ''); }
  const part = s.toLowerCase().replace(/[^a-z0-9]/g, '');
  return { side, part };
}

// the body part a (side-less) name means, or null
function partRole(part, side) {
  if (!part) return null;
  // fingers: LeftHandIndex1 (Mixamo), LeftIndexProximal (Unity / Rokoko), l_index_01, Bip01 L Finger1 is not read
  const finger = /^(?:hand|finger)?(thumb|index|middle|mid|ring|pinky|pinkie|little)(?:finger)?(.*)$/.exec(part);
  if (finger && side) {
    const f = { thumb: 'Thumb', index: 'Index', middle: 'Mid', mid: 'Mid', ring: 'Ring', pinky: 'Pinky', pinkie: 'Pinky', little: 'Pinky' }[finger[1]];
    const d = /(\d+)/.exec(finger[2]);
    const word = { metacarpal: 0, proximal: 1, intermediate: 2, medial: 2, middle: 2, distal: 3 };
    const w = Object.keys(word).find(x => finger[2].includes(x));
    return { role: 'finger', finger: f, n: d ? +d[1] : w !== undefined ? word[w] : null, carpal: /carpal/.test(finger[2]) };
  }
  if (side) {
    if (/^(hipjoint|hipbone)$/.test(part)) return null;
    if (/^(upleg|upperleg|thigh|femur|hip|upperlegs)$/.test(part)) return { role: 'thigh' };
    if (/^(leg|lowerleg|knee|shin|calf|tibia|crus|lowleg)$/.test(part)) return { role: 'knee' };
    if (/^(foot|ankle|feet)$/.test(part)) return { role: 'ankle' };
    if (/^(toebase|toe|toes|ball|toe0|toe1|foottoe|toes0)$/.test(part)) return { role: 'toe' };
    if (/^(collar|clavicle|clav|collarbone|shoulderblade)$/.test(part)) return { role: 'clavicle' };
    if (/^shoulder$/.test(part)) return { role: 'shoulder?' };            // Mixamo: the clavicle; Kinect style: the arm
    if (/^(arm|upperarm|shldr|humerus|uparm|arm1)$/.test(part)) return { role: 'shoulder' };
    if (/^(forearm|lowerarm|elbow|radius|lowarm|arm2)$/.test(part)) return { role: 'elbow' };
    if (/^(hand|wrist|palm)$/.test(part)) return { role: 'wrist' };
    return null;
  }
  if (/^(hips|hip|pelvis|root|hipsroot|hipjoint)$/.test(part)) return { role: 'hips' };
  if (/^head$/.test(part)) return { role: 'head' };
  if (/^(neck|neck0|neck1|necklower)$/.test(part)) return { role: 'neck' };
  if (/^(spine|spine\d|chest|upperchest|abdomen|lowerback|torso|back|chest\d)$/.test(part)) return { role: 'spine' };
  return null;
}

const STYLES = [
  ['Mixamo', names => names.some(n => /^mixamorig/i.test(n))],
  ['CMU', names => names.some(n => /^LHipJoint$/i.test(n)) || names.some(n => /^LowerBack$/i.test(n))],
  ['DeepMotion', names => names.filter(n => /_JNT$/i.test(n)).length > 5],
  ['3ds Max Biped', names => names.some(n => /^Bip0*\d*\s/i.test(n))],
  ['Daz / Second Life', names => names.some(n => /^[lr]Shldr$/.test(n)) || names.some(n => /^[lr]Thigh$/.test(n))],
  ['HumanIK / Rokoko', names => names.some(n => /^LeftUpLeg$/i.test(n)) && names.some(n => /^LeftForeArm$/i.test(n))],
];

// analyze(bvh) -> { roles, style, missing: [part], fingers: {L, R}, up: 'Y up'|'Z up'|..., units, height, restPose,
//                   frame: {left, up, fwd} (the rest pose's axes, in the file's axes), legLen (file units) }
export function analyze(bvh) {
  const J = bvh.joints;
  const byRole = { L: {}, R: {}, C: {} };
  const shoulderQ = { L: [], R: [] };
  const fingerJoints = { L: {}, R: {} };
  J.forEach((jt, k) => {
    if (SKIP.test(jt.name)) return;
    const { side, part } = nameParts(jt.name);
    const r = partRole(part, side);
    if (!r) return;
    const bag = side ? byRole[side] : byRole.C;
    if (r.role === 'finger') { (fingerJoints[side][r.finger] = fingerJoints[side][r.finger] || []).push({ k, n: r.n, carpal: r.carpal }); return; }
    if (r.role === 'shoulder?') { shoulderQ[side].push(k); return; }
    if (r.role === 'spine') { (bag.spine = bag.spine || []).push(k); return; }
    if (bag[r.role] === undefined) bag[r.role] = k;
  });
  const parentSkip = k => { let p = J[k].parent; while (p >= 0 && SKIP.test(J[p].name)) p = J[p].parent; return p; };
  const firstChild = k => { const c = J[k].children.filter(x => !SKIP.test(J[x].name)); return c.length ? c[0] : -1; };
  const roles = { hips: byRole.C.hips ?? 0, head: byRole.C.head ?? -1, neck: byRole.C.neck ?? -1, L: {}, R: {} };
  for (const s of ['L', 'R']) {
    const b = byRole[s], out = roles[s];
    // "LeftShoulder": the clavicle when there is also an arm joint below it, else the upper arm itself
    for (const k of shoulderQ[s]) {
      if (b.shoulder === undefined && b.elbow !== undefined && parentSkip(b.elbow) === k) b.shoulder = k;
      else if (b.clavicle === undefined) b.clavicle = k;
    }
    if (b.shoulder === undefined && shoulderQ[s].length && b.elbow === undefined) b.shoulder = shoulderQ[s][0];
    out.wrist = b.wrist ?? -1;
    out.elbow = b.elbow ?? (out.wrist >= 0 ? parentSkip(out.wrist) : -1);
    out.shoulder = b.shoulder ?? (out.elbow >= 0 ? parentSkip(out.elbow) : -1);
    out.ankle = b.ankle ?? -1;
    out.knee = b.knee ?? (out.ankle >= 0 ? parentSkip(out.ankle) : -1);
    out.thigh = b.thigh ?? (out.knee >= 0 ? parentSkip(out.knee) : -1);
    if (out.wrist < 0 && out.elbow >= 0) out.wrist = firstChild(out.elbow);
    if (out.ankle < 0 && out.knee >= 0) out.ankle = firstChild(out.knee);
    out.toe = b.toe ?? (out.ankle >= 0 ? firstChild(out.ankle) : -1);
    // fingers: each finger's chain from its first joint down (3 joints + the tip: a 4th joint or the End Site)
    const fingers = {};
    for (const f of FINGERS) {
      const list = (fingerJoints[s][f] || []).slice().sort((a, c) => (a.n ?? 0) - (c.n ?? 0) || a.k - c.k);
      if (!list.length) continue;
      // start at the one closest to the hand (its parent is not another joint of this finger)
      const own = new Set(list.map(x => x.k));
      let start = (list.find(x => !own.has(J[x.k].parent)) || list[0]).k;
      // a finger's palm bone (metacarpal) sits at the wrist: the knuckle is the joint after it (not for the thumb,
      // whose first joint is the palm joint MediaPipe calls its base)
      if (f !== 'Thumb' && list.find(x => x.k === start && x.carpal)) { const c = J[start].children.filter(x => own.has(x)); if (c.length) start = c[0]; }
      const chain = [start];
      while (chain.length < 4) {
        const kids = J[chain[chain.length - 1]].children.filter(x => !/nub/i.test(J[x].name));
        if (!kids.length) break;
        chain.push(kids.find(x => own.has(x)) ?? kids[0]);
      }
      if (chain.length >= 3) fingers[f] = { joints: chain.slice(0, 3), tip: chain.length >= 4 ? chain[3] : -1 };
    }
    out.fingers = FINGERS.every(f => fingers[f]) ? fingers : null;
    out.clavicle = b.clavicle ?? -1;
  }
  if (roles.head < 0) {
    // no head joint: the neck's first child, or the top of the spine
    const n = roles.neck >= 0 ? roles.neck : (byRole.C.spine || []).slice(-1)[0];
    roles.head = n !== undefined && n >= 0 ? (firstChild(n) >= 0 && !SKIP.test(J[firstChild(n)].name) ? firstChild(n) : n) : -1;
  }
  if (roles.neck < 0 && roles.head >= 0) roles.neck = parentSkip(roles.head);
  // what is missing (the solver needs every one of these)
  const need = [['hips', roles.hips], ['head', roles.head]];
  const nice = { thigh: 'hip', knee: 'knee', ankle: 'ankle', shoulder: 'shoulder', elbow: 'elbow', wrist: 'wrist' };
  for (const s of ['L', 'R']) for (const p of ['thigh', 'knee', 'ankle', 'shoulder', 'elbow', 'wrist']) need.push([`${s === 'L' ? 'left' : 'right'} ${nice[p]}`, roles[s][p]]);
  const missing = need.filter(([, k]) => !(k >= 0)).map(([n]) => n);
  // the same joint twice (a chain guessed wrong) counts as missing too
  const used = new Map();
  for (const [n, k] of need) if (k >= 0) { if (used.has(k)) missing.push(n); else used.set(k, n); }
  const names = J.map(j => j.name);
  const style = (STYLES.find(([, t]) => t(names)) || ['Other'])[0];
  const info = { roles, style, missing, fingers: { L: !!roles.L.fingers, R: !!roles.R.fingers }, joints: J.length };
  if (missing.length) return info;
  // the rest pose: up (hips to head), left (right hip to left hip), forward = left x up
  const rest = fk(bvh, null);
  const P = k => new THREE.Vector3().fromArray(rest.P, k * 3);
  const hipC = P(roles.L.thigh).add(P(roles.R.thigh)).multiplyScalar(0.5);
  const shC = P(roles.L.shoulder).add(P(roles.R.shoulder)).multiplyScalar(0.5);
  let up = shC.clone().sub(hipC);
  if (up.lengthSq() < 1e-12) up = P(roles.head).sub(hipC);
  up.normalize();
  let left = P(roles.L.thigh).sub(P(roles.R.thigh));
  if (left.lengthSq() < 1e-12) left = P(roles.L.shoulder).sub(P(roles.R.shoulder));
  left.sub(up.clone().multiplyScalar(left.dot(up)));
  if (left.lengthSq() < 1e-12) { info.missing.push('a left and right side'); return info; }
  left.normalize();
  const fwd = left.clone().cross(up);
  info.frame = { left: left.toArray(), up: up.toArray(), fwd: fwd.toArray() };
  const ax = v => { const a = [Math.abs(v.x), Math.abs(v.y), Math.abs(v.z)], k = a.indexOf(Math.max(...a)); return (a[k] > 0.9 ? '' : '~') + ['X', 'Y', 'Z'][k] + (v.getComponent(k) < 0 ? ' down' : ' up'); };
  info.up = ax(up);
  const len = (a, b) => P(a).distanceTo(P(b));
  const legLen = 0.5 * (len(roles.L.thigh, roles.L.knee) + len(roles.L.knee, roles.L.ankle) + len(roles.R.thigh, roles.R.knee) + len(roles.R.knee, roles.R.ankle));
  info.legLen = legLen;
  // height: the head joint above the ankles, plus a head's worth (the rest pose stands)
  const ankleUp = Math.min(P(roles.L.ankle).dot(up), P(roles.R.ankle).dot(up));
  const height = (P(roles.head).dot(up) - ankleUp) * 1.12;
  info.height = height;
  info.units = height > 100 && height < 260 ? 'centimetres' : height > 1 && height < 2.6 ? 'metres' : height > 40 && height < 100 ? 'inches' : height > 1000 && height < 2600 ? 'millimetres' : 'its own units';
  // T-pose or A-pose: how far the upper arms hang below the shoulder line
  const armDrop = s => { const d = P(roles[s].elbow).sub(P(roles[s].shoulder)).normalize(); return Math.asin(THREE.MathUtils.clamp(-d.dot(up), -1, 1)) * 180 / Math.PI; };
  const drop = 0.5 * (armDrop('L') + armDrop('R'));
  info.armDrop = drop;
  info.restPose = drop < 20 ? 'T-pose' : drop < 60 ? 'A-pose' : 'arms down';
  return info;
}

// ---------------------------------------------------------------- the take
// The rig's rest points the file has no joint for, fixed to a joint: head points to the head, heel and toe to the
// foot, knuckles (when the file has no fingers) to the hand.
const HEAD_PTS = [PL.nose, PL.eyeInL, PL.eyeL, PL.eyeOutL, PL.eyeInR, PL.eyeR, PL.eyeOutR, PL.earL, PL.earR, PL.mouthL, PL.mouthR];

// a rotation whose columns are a and b (made perpendicular to a) and a x b
function frameOf(a, b) {
  const e1 = a.clone().normalize();
  const e2 = b.clone().sub(e1.clone().multiplyScalar(b.dot(e1)));
  if (e2.lengthSq() < 1e-10) e2.set(0, 1, 0).sub(e1.clone().multiplyScalar(e1.y));
  e2.normalize();
  const e3 = e1.clone().cross(e2);
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(e1, e2, e3));
}

// setup(bvh, info, rp) -> what buildTake needs once per file: the turn from the file's axes to sim space, the scale to
// the sim's size, and the fixed points' places relative to their joints (sim space, at the file's rest).
export function setup(bvh, info, rp) {
  const F = info.frame;
  const left = new THREE.Vector3().fromArray(F.left), up = new THREE.Vector3().fromArray(F.up), fwd = new THREE.Vector3().fromArray(F.fwd);
  // C: file axes -> sim axes (left -> +X, up -> +Y, forward -> +Z)
  const C = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(left, up, fwd)).invert();
  const rl = rp.restLm, R = info.roles;
  const rigLeg = ['L', 'R'].reduce((a, s) => a + rp.restPos(`b__${s}_Thigh__`).distanceTo(rp.restPos(`b__${s}_Calf__`)) + rp.restPos(`b__${s}_Calf__`).distanceTo(rp.restPos(`b__${s}_Foot__`)), 0) / 2;
  const k = rigLeg / info.legLen;                       // file units -> metres on the sim
  const rest = fk(bvh, null);
  const S = j => new THREE.Vector3().fromArray(rest.P, j * 3).applyQuaternion(C).multiplyScalar(k);
  const head = HEAD_PTS.map(j => [j, rl.pose[j].clone().sub(rp.restPos('b__Head__'))]);
  const feet = {}, hands = {};
  for (const [s, o] of [['L', 0], ['R', 1]]) {
    const foot = rp.restPos(`b__${s}_Foot__`);
    feet[s] = [[PL.heelL + o, rl.pose[PL.heelL + o].clone().sub(foot)], [PL.toeL + o, rl.pose[PL.toeL + o].clone().sub(foot)]];
    // knuckles: the rig's rest hand seen from its forearm (along it, thumb forward), put on the file's rest forearm
    const Z = new THREE.Vector3(0, 0, 1);
    const rigArm = rp.restPos(`b__${s}_Hand__`).clone().sub(rp.restPos(`b__${s}_Forearm__`));
    const fileArm = S(R[s].wrist).sub(S(R[s].elbow));
    const turn = frameOf(fileArm, Z).multiply(frameOf(rigArm, Z).invert());
    const wr = rp.restPos(`b__${s}_Hand__`);
    hands[s] = [PL.indexL + o, PL.pinkyL + o, PL.thumbL + o].map(j => [j, rl.pose[j].clone().sub(wr).applyQuaternion(turn)]);
  }
  return { C, Cinv: C.clone().invert(), k, head, feet, hands, rigLeg };
}

// One frame's landmarks in sim space: {pose: [33 Vector3], hands: {L, R: [21] | null}}
export function framePoints(bvh, info, su, frame, pose = null) {
  pose = pose || fk(bvh, frame);
  const { C, Cinv, k } = su, R = info.roles;
  const S = j => new THREE.Vector3().fromArray(pose.P, j * 3).applyQuaternion(C).multiplyScalar(k);
  const D = j => C.clone().multiply(new THREE.Quaternion().fromArray(pose.Q, j * 4)).multiply(Cinv);    // turn from the rest, sim axes
  const out = new Array(33);
  const Dh = D(R.head), ph = S(R.head);
  for (const [j, o] of su.head) out[j] = o.clone().applyQuaternion(Dh).add(ph);
  const hands = { L: null, R: null };
  for (const [s, o] of [['L', 0], ['R', 1]]) {
    const r = R[s];
    out[PL.shL + o] = S(r.shoulder); out[PL.elL + o] = S(r.elbow); out[PL.wrL + o] = S(r.wrist);
    out[PL.hipL + o] = S(r.thigh); out[PL.knL + o] = S(r.knee); out[PL.anL + o] = S(r.ankle);
    const Df = D(r.ankle), pf = out[PL.anL + o];
    for (const [j, off] of su.feet[s]) out[j] = off.clone().applyQuaternion(Df).add(pf);
    if (r.fingers) {
      // the file's own fingers: 21 hand points (wrist, then 4 per finger base to tip)
      const H = [S(r.wrist)];
      for (const f of FINGERS) {
        const fj = r.fingers[f];
        const pts = fj.joints.map(S);
        let tip;
        if (fj.tip >= 0) tip = S(fj.tip);
        else {
          const e = endPoint(bvh, pose, fj.joints[2]);
          tip = e ? e.applyQuaternion(C).multiplyScalar(k) : pts[2].clone().add(pts[2].clone().sub(pts[1]).multiplyScalar(0.8));
        }
        H.push(...pts, tip);
      }
      hands[s] = H;
      out[PL.indexL + o] = H[5].clone(); out[PL.pinkyL + o] = H[17].clone(); out[PL.thumbL + o] = H[3].clone();
    } else {
      const Dw = D(r.wrist), pw = out[PL.wrL + o];
      for (const [j, off] of su.hands[s]) out[j] = off.clone().applyQuaternion(Dw).add(pw);
    }
  }
  return { pose: out, hands };
}

// buildTake(bvh, info, rp, {from, to}) -> a capture take over the file's frames [from, to] (its own timing; clean.js
// puts it on the 30 fps grid). The points are in sim space at the sim's size, stored in MediaPipe's axes (x, -y, -z)
// and NOT centred on the hips, so the hips' travel is in the points themselves (hipsPlace reads it back).
export function buildTake(bvh, info, rp, { from = 0, to = bvh.frames - 1, name = '' } = {}) {
  const su = setup(bvh, info, rp);
  from = Math.max(0, Math.min(bvh.frames - 1, Math.round(from)));
  to = Math.max(from, Math.min(bvh.frames - 1, Math.round(to)));
  const n = to - from + 1;
  const withHands = !!(info.roles.L.fingers || info.roles.R.fingers);
  const pe = {
    pose: new Float32Array(n * 33 * 4), img: new Float32Array(n * 33 * 3),
    hand: withHands ? { L: new Float32Array(n * 63), R: new Float32Array(n * 63), Lok: new Uint8Array(n), Rok: new Uint8Array(n) } : null,
    face: null,
  };
  const t = new Float64Array(n);
  const cache = { P: new Float64Array(bvh.joints.length * 3), Q: new Float64Array(bvh.joints.length * 4) };
  for (let i = 0; i < n; i++) {
    t[i] = i * bvh.frameTime;
    const fp = framePoints(bvh, info, su, from + i, fk(bvh, from + i, cache));
    for (let j = 0; j < 33; j++) {
      const v = fp.pose[j], b = (i * 33 + j) * 4;
      pe.pose[b] = v.x; pe.pose[b + 1] = -v.y; pe.pose[b + 2] = -v.z; pe.pose[b + 3] = 1;
      pe.img[(i * 33 + j) * 3] = 0.5; pe.img[(i * 33 + j) * 3 + 1] = 0.5;
    }
    if (withHands) for (const s of ['L', 'R']) {
      const H = fp.hands[s];
      if (!H) continue;
      for (let j = 0; j < 21; j++) { const b = (i * 21 + j) * 3; pe.hand[s][b] = H[j].x; pe.hand[s][b + 1] = -H[j].y; pe.hand[s][b + 2] = -H[j].z; }
      pe.hand[s + 'ok'][i] = 1;
    }
  }
  return { source: 'bvh', width: 1280, height: 720, fov: 60, t, people: [pe], name, from, to, scale: su.k };
}

// The hips' place in frame i of a take made by buildTake (MediaPipe axes, like cameraPlace in retarget.js).
export function hipsPlace(take, person, i) {
  const po = take.people[person].pose;
  const a = (i * 33 + PL.hipL) * 4, b = (i * 33 + PL.hipR) * 4;
  return new THREE.Vector3((po[a] + po[b]) / 2, (po[a + 1] + po[b + 1]) / 2, (po[a + 2] + po[b + 2]) / 2);
}

// ---------------------------------------------------------------- the whole way: file -> poses
export const MAX_SECONDS = 60;                  // the longest part read at once (like a video)

// solveFile(bvh, info, rig | Solver, opts) -> { take, solved, result: {poses, faces}, loop: {a, b, seam} | null }
// opts: from, to (the file's frames), smooth (take out small shakes), stay (remove the hips' slow travel, keep sways),
//       ground ('lowest': the file's height, jumps stay jumps | 'floor': feet kept on the floor every frame),
//       mirror (swap left and right), fingers, loop ('best': find the best loop inside the part | 'none'),
//       facing (radians: the way the sim faces now), base (the sim's pose now: its hips' place and floor), limits
export function solveFile(bvh, info, rig, { from = 0, to = bvh.frames - 1, smooth = false, stay = false, ground = 'lowest', mirror = false,
  fingers = true, loop = 'best', facing = 0, base = null, floorY = null, limits = true, psi } = {}) {
  const solver = rig instanceof Solver ? rig : new Solver(rig);
  const maxFrames = Math.round(MAX_SECONDS / bvh.frameTime);
  to = Math.min(to, from + maxFrames);
  const raw = buildTake(bvh, info, solver.rp, { from, to });
  // the file's frame rate -> the app's 30 fps (by time, like a phone video); smoothing is the capture's own filter
  const take = smooth ? cleanTake(raw, { smooth: 0.5 }) : resample(raw, FPS);
  const hasFingers = !!(info.roles.L.fingers || info.roles.R.fingers);
  const solved = solveTake(take, 0, solver, {
    facing, base, floorY, ground, stay, mirror, hands: true, fingers: fingers && hasFingers, headFromFace: false, limits,
    places: hipsPlace, smoothPlace: !!smooth, smoothRot: !!smooth, smooth: 0.5, stick: true, ...(psi !== undefined ? { psi } : {}),
  });
  const N = solved.poses.length;
  let result = { poses: solved.poses, faces: null }, lp = null;
  if (loop === 'best' && N > 45) {
    const r = findLoop(solved.poses, { minFrames: Math.min(30, N - 2), maxFrames: Math.min(N, 20 * FPS) });
    if (r.b - r.a >= 12) {
      result = closeLoop(solved.poses, null, r.a, r.b);
      lp = { a: r.a, b: r.b, seam: seamError(result.poses) };
    }
  }
  return { take, solved, result, loop: lp, solver };
}

// Is this file one this app can't read (FBX, other formats)? -> a message, or null.
export function formatProblem(fileName, head = '') {
  const n = String(fileName || '').toLowerCase();
  if (/\.fbx$/.test(n) || /^Kaydara FBX Binary/.test(head) || /^; FBX/.test(head) || /FBXHeaderExtension/.test(head)) {
    return 'FBX files can\'t be read here yet. Export your motion as BVH instead: DeepMotion, Plask and Rokoko Vision offer BVH next to FBX when you download. Mixamo only downloads FBX - convert it to BVH first (for example with Blender\'s BVH export).';
  }
  if (/\.(glb|gltf|dae|c3d|trc|anim|blend)$/.test(n)) return 'Only BVH motion files can be read here. Export (or convert) your motion as .bvh and try again.';
  return null;
}
