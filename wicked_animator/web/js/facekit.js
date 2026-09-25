// Everything the Face tool, the All bones list and face keys need from the engine (bones.js, animation.js, sim.js,
// face.js, pipeline.js - plan 2.2, spec_face_bones section 4). The engine provides these; until one of them exists,
// a small local version here stands in, so the app works either way. Face bones: local x = up, y = forward,
// z = the sim's left; the jaw is turned 180 degrees, the lower lips and the tongue sit in the head frame again.
import * as THREE from 'three';
import * as B from './bones.js';
import * as A from './animation.js';
import * as F from './face.js';

const deg = THREE.MathUtils.degToRad;
const X = new THREE.Vector3(1, 0, 0), Z = new THREE.Vector3(0, 0, 1);
const clamp = THREE.MathUtils.clamp;

// ---------------------------------------------------------------- lists (bones.js)
export const NOSTRILS = B.NOSTRILS || ['b__CAS_L_Nostril__', 'b__CAS_R_Nostril__'];
export const FACE_CHANNEL = B.FACE_CHANNEL || [...B.FACE, 'b__Jaw__', ...B.TONGUE, ...NOSTRILS];
export const FACE_SET = B.FACE_SET || new Set(FACE_CHANNEL);
export const TWIST = B.TWIST || [
  ...['L', 'R'].map(s => ({ bone: `b__${s}_ForearmTwist__`, driver: `b__${s}_Hand__`, ratio: 0.5 })),
  ...['L', 'R'].map(s => ({ bone: `b__${s}_ShoulderTwist__`, driver: `b__${s}_UpperArm__`, ratio: -0.4 })),
  ...['L', 'R'].map(s => ({ bone: `b__${s}_ThighTwist__`, driver: `b__${s}_Thigh__`, ratio: -0.75, opt: 'hipTwist' })),
];
export const TWIST_SET = B.TWIST_SET || new Set(TWIST.map(t => t.bone));
export const WW_BODY = B.WW_BODY || [...B.BREASTS, ...B.BUTT, 'b__Penis_Tip', 'b__Penis_Testicles', 'b__Penis_L_Testicle',
  'b__Penis_R_Testicle', 'b__Up_Vagina__', 'b__Low_Vagina__', 'b__Anus', 'b__L_Anus__', 'b__R_Anus__', 'b__Up_Anus', 'b__Low_Anus'];
export const EXPERT = B.EXPERT || ['b__L_Elbow__', 'b__R_Elbow__', 'b__L_Skirt__', 'b__R_Skirt__', 'b__CAS_Glasses__',
  'b__CAS_L_EyeArea__', 'b__CAS_R_EyeArea__', 'b__CAS_L_EyeScale__', 'b__CAS_R_EyeScale__', 'b__CAS_NoseArea__', 'b__CAS_NoseTip__',
  'b__CAS_NoseBridge__', 'b__CAS_UpperMouthArea__', 'b__CAS_LowerMouthArea__', 'b__CAS_JawComp__', 'b__CAS_Chin__',
  'b__L_Prop__', 'b__R_Prop__', 'b__Carry__', 'b__L_Stigmata', 'b__R_Stigmata'];
export const EXPERT_SET = new Set(EXPERT);
// the body channel's always-keyed bones (today's POSABLE without the jaw and tongue, once the engine has moved them)
export const BODY = B.KEYABLE ? B.POSABLE : B.POSABLE.filter(n => !FACE_SET.has(n));
export const BODY_SET = new Set(BODY);
export const EXTRA = B.EXTRA || [...TWIST.map(t => t.bone), ...WW_BODY, ...EXPERT];
export const EXTRA_SET = new Set(EXTRA);
export const KEYABLE = B.KEYABLE || [...BODY, ...EXTRA, ...FACE_CHANNEL];
export const KEYABLE_SET = B.KEYABLE_SET || new Set(KEYABLE);
export const isFace = n => FACE_SET.has(n);
export const isTwist = n => TWIST_SET.has(n);
export const isExtra = n => EXTRA_SET.has(n) && !FACE_SET.has(n);
export const isCenterFace = B.isCenterFace || (n => FACE_SET.has(n) && !/_(L|R)_/.test(n));
export const mirrorName = B.mirrorName;
/** True once the engine owner's bone lists are in (the body pose leaves the face out, extra bones are kept). */
export const ENGINE_BONES = !!B.KEYABLE;
/** True once the engine owner's face-bone engine is in (the pipeline sets face bones from keys). */
export const engineHasFace = app => !!(app && app.pipeline && typeof app.pipeline.keyedFace === 'function');

// ---------------------------------------------------------------- safe ranges (spec 3.1)
// [mode, move x, y, z (mm), turn x, y, z (degrees)] for the left side and the middle; null = locked (Alt unlocks)
const LIM = {
  InBrow: ['move', [-15, 40], [-6, 6], [-10, 6], null, [-30, 15], null],
  MidBrow: ['move', [-35, 20], [-4, 6], [-6, 4], null, null, null],
  OutBrow: ['move', [-12, 15], [-4, 4], [-3, 4], null, null, null],
  UpLid: ['turn', null, null, null, [-6, 6], [-4, 4], [-15, 46]],
  LoLid: ['turn', null, null, null, [-5, 5], [-3, 3], [-40, 22]],
  Eye: ['turn', null, null, null, [-32, 32], null, [-30, 30]],
  Cheek: ['move', [-3, 14], [-3, 4], [-3, 5], null, null, null],
  Squint: ['move', [-2, 20], [-2, 3], [-3, 3], null, null, null],
  Nostril: ['move', [-2, 8], [-3, 3], [-2, 4], null, null, null],
  Mouth: ['move', [-20, 12], [-12, 8], [-8, 10], [-15, 15], [-15, 15], [-15, 15]],
  UpLipSide: ['move', [-4, 12], [-4, 12], [-2, 8], null, null, [-35, 20]],
  LoLipSide: ['move', [-8, 8], [-5, 12], [-2, 10], null, null, [-50, 30]],
  b__UpLip__: ['move', [-5, 9], [-4, 16], [-2, 2], null, null, [-35, 15]],
  b__LoLip__: ['move', [-8, 7], [-3, 16], [-2, 2], null, null, [-50, 30]],
  b__Jaw__: ['turn', null, [-6, 10], null, [-4, 4], [-5, 5], [-40, 3]],
  b__Tounge__1: ['move', [-4, 10], [-2, 70], [-4, 4], [-12, 12], [-12, 12], [-30, 25]],
  b__Tounge__2: ['turn', null, [-10, 40], null, [-20, 20], [-15, 15], [-60, 50]],
  b__Tounge__3: ['turn', null, null, null, [-28, 12], [-18, 12], [-60, 50]],
};
function limKey(name) {
  if (LIM[name]) return name;
  if (/Nostril/.test(name)) return 'Nostril';
  const m = /^b__(L|R)_(\w+?)__$/.exec(name);
  if (!m) return null;
  if (m[2] === 'UpLip') return 'UpLipSide';
  if (m[2] === 'LoLip') return 'LoLipSide';
  return LIM[m[2]] ? m[2] : null;
}
const flip = r => (r ? [-r[1], -r[0]] : null);
/** {mode: 'move'|'turn', move: [[lo, hi] | null] x3 in metres, turn: [...] x3 in radians}; right bones mirrored. */
export function faceLimits(name) {
  if (B.faceLimits) { const l = B.faceLimits(name); if (l) return l; }
  const k = limKey(name);
  if (!k) return null;
  const [mode, mx, my, mz, tx, ty, tz] = LIM[k];
  const right = /_R_/.test(name);
  const mm = r => (r ? [r[0] / 1000, r[1] / 1000] : null), dg = r => (r ? [deg(r[0]), deg(r[1])] : null);
  return {
    mode,
    move: [mm(mx), mm(my), mm(right ? flip(mz) : mz)],
    turn: [dg(right ? flip(tx) : tx), dg(right ? flip(ty) : ty), dg(tz)],
  };
}

// ---------------------------------------------------------------- dots: regions and colours (spec 3.2)
export const REGIONS = ['brows', 'eyes', 'cheeks', 'mouth', 'jaw'];
const REGION_COLOR = { brows: '#ff7ab6', eyes: '#57b8ff', cheeks: '#ffb547', mouth: '#ff4f6a', jaw: '#a78bfa' };
export const REGION_LABEL = { brows: 'Brows', eyes: 'Eyes and lids', cheeks: 'Cheeks and nose', mouth: 'Mouth', jaw: 'Jaw and tongue' };
export function faceRegion(name) {
  if (B.faceRegion) { const r = B.faceRegion(name); if (r) return r; }
  if (/Brow/.test(name)) return 'brows';
  if (/Lid__|_Eye__/.test(name)) return 'eyes';
  if (/Cheek|Squint|Nostril/.test(name)) return 'cheeks';
  if (/Lip|Mouth/.test(name)) return 'mouth';
  if (/Jaw|Tounge/.test(name)) return 'jaw';
  return null;
}
export function regionColor(region) {
  const H = B.FACE_HANDLES;
  const c = H && ((H[region] && H[region].color) || (Array.isArray(H) && (H.find(x => x && x.region === region) || {}).color));
  return c || REGION_COLOR[region] || '#ffffff';
}
// guide lines: each brow Out-Mid-In, and the lip loop
export const FACE_LINES = [
  ['b__L_OutBrow__', 'b__L_MidBrow__'], ['b__L_MidBrow__', 'b__L_InBrow__'],
  ['b__R_OutBrow__', 'b__R_MidBrow__'], ['b__R_MidBrow__', 'b__R_InBrow__'],
  ['b__L_Mouth__', 'b__L_UpLip__'], ['b__L_UpLip__', 'b__UpLip__'], ['b__UpLip__', 'b__R_UpLip__'], ['b__R_UpLip__', 'b__R_Mouth__'],
  ['b__R_Mouth__', 'b__R_LoLip__'], ['b__R_LoLip__', 'b__LoLip__'], ['b__LoLip__', 'b__L_LoLip__'], ['b__L_LoLip__', 'b__L_Mouth__'],
];

// ---------------------------------------------------------------- names
const EXTRA_NAMES = {
  InBrow: 'Inner brow', MidBrow: 'Middle brow', OutBrow: 'Outer brow', UpLid: 'Upper eyelid', LoLid: 'Lower eyelid', Eye: 'Eye',
  Cheek: 'Cheek', Squint: 'Under the eye', Mouth: 'Mouth corner', UpLip: 'Upper lip (side)', LoLip: 'Lower lip (side)',
  ShoulderTwist: 'Upper arm twist', ForearmTwist: 'Wrist twist', ThighTwist: 'Thigh twist', Elbow: 'Elbow helper', Skirt: 'Skirt helper',
  Butt: 'Butt cheek', Prop: 'Held object', Stigmata: 'Palm spot',
};
const FULL_NAMES = {
  b__UpLip__: 'Upper lip (middle)', b__LoLip__: 'Lower lip (middle)', b__Jaw__: 'Jaw', b__Carry__: 'Carry helper',
  b__CAS_L_Nostril__: 'Nostril (left)', b__CAS_R_Nostril__: 'Nostril (right)', b__CAS_L_Breast__: 'Breast (left)', b__CAS_R_Breast__: 'Breast (right)',
  b__Penis_Testicles: 'Balls', b__Up_Vagina__: 'Vagina (top)', b__Low_Vagina__: 'Vagina (bottom)', b__Anus: 'Anus',
  b__L_Anus__: 'Anus (left)', b__R_Anus__: 'Anus (right)', b__Up_Anus: 'Anus (top)', b__Low_Anus: 'Anus (bottom)',
  b__L_Stigmata: 'Palm spot (left)', b__R_Stigmata: 'Palm spot (right)', b__L_Prop__: 'Held object (left)', b__R_Prop__: 'Held object (right)',
  b__CAS_Glasses__: 'Glasses (shape)', b__CAS_L_EyeArea__: 'Eye area (left) (shape)', b__CAS_R_EyeArea__: 'Eye area (right) (shape)',
  b__CAS_L_EyeScale__: 'Eye size (left) (shape)', b__CAS_R_EyeScale__: 'Eye size (right) (shape)', b__CAS_NoseArea__: 'Nose (shape)',
  b__CAS_NoseTip__: 'Nose tip (shape)', b__CAS_NoseBridge__: 'Nose bridge (shape)', b__CAS_UpperMouthArea__: 'Upper mouth (shape)',
  b__CAS_LowerMouthArea__: 'Lower mouth (shape)', b__CAS_JawComp__: 'Jaw width (shape)', b__CAS_Chin__: 'Chin (shape)',
};
/** Plain name of any bone ("Inner brow (left)"); `frame` is the body ('yf' names the testicle bones as vagina lips). */
export function label(name, frame) {
  if (B.KEYABLE && B.label) return B.label(name, frame);
  if (/^b__Penis_(L|R)_Testicle$/.test(name)) {
    const side = name.includes('_L_') ? 'left' : 'right';
    return frame === 'yf' ? `Vagina lip (${side})` : `${side === 'left' ? 'Left' : 'Right'} ball`;
  }
  if (FULL_NAMES[name]) return FULL_NAMES[name];
  const m = /^b__(?:(L|R)_)?(.+?)__$/.exec(name);
  if (m && EXTRA_NAMES[m[2]]) return m[1] ? `${EXTRA_NAMES[m[2]]} (${m[1] === 'L' ? 'left' : 'right'})` : EXTRA_NAMES[m[2]];
  return B.label(name);
}

// ---------------------------------------------------------------- the bone list: groups and search words
const SIDE_ARM = s => [`b__${s}_Clavicle__`, `b__${s}_UpperArm__`, `b__${s}_ShoulderTwist__`, `b__${s}_Forearm__`, `b__${s}_ForearmTwist__`, `b__${s}_Hand__`];
const SIDE_FINGERS = s => ['Thumb', 'Index', 'Mid', 'Ring', 'Pinky'].flatMap(f => [0, 1, 2].map(i => `b__${s}_${f}${i}__`));
const SIDE_LEG = s => [`b__${s}_Thigh__`, `b__${s}_ThighTwist__`, `b__${s}_Calf__`, `b__${s}_Foot__`, `b__${s}_Toe__`];
const FALLBACK_GROUPS = [
  { id: 'body', label: 'Body', bones: ['b__Pelvis__', 'b__Spine0__', 'b__Spine1__', 'b__Spine2__', 'b__Neck__', 'b__Head__'] },
  { id: 'larm', label: 'Left arm', bones: SIDE_ARM('L') }, { id: 'rarm', label: 'Right arm', bones: SIDE_ARM('R') },
  { id: 'lfing', label: 'Left fingers', bones: SIDE_FINGERS('L') }, { id: 'rfing', label: 'Right fingers', bones: SIDE_FINGERS('R') },
  { id: 'lleg', label: 'Left leg', bones: SIDE_LEG('L') }, { id: 'rleg', label: 'Right leg', bones: SIDE_LEG('R') },
  { id: 'face', label: 'Face', face: true, sub: [
    { label: 'Brows', bones: ['b__L_InBrow__', 'b__L_MidBrow__', 'b__L_OutBrow__', 'b__R_InBrow__', 'b__R_MidBrow__', 'b__R_OutBrow__'] },
    { label: 'Eyes and lids', bones: ['b__L_Eye__', 'b__L_UpLid__', 'b__L_LoLid__', 'b__R_Eye__', 'b__R_UpLid__', 'b__R_LoLid__'] },
    { label: 'Cheeks and nose', bones: ['b__L_Cheek__', 'b__L_Squint__', 'b__R_Cheek__', 'b__R_Squint__', ...NOSTRILS] },
    { label: 'Mouth', bones: ['b__UpLip__', 'b__L_UpLip__', 'b__R_UpLip__', 'b__L_Mouth__', 'b__R_Mouth__', 'b__LoLip__', 'b__L_LoLip__', 'b__R_LoLip__'] },
    { label: 'Jaw and tongue', bones: ['b__Jaw__', 'b__Tounge__1', 'b__Tounge__2', 'b__Tounge__3'] },
  ] },
  { id: 'ww', label: 'WickedWhims body', ww: true, bones: [...B.PENIS.slice(0, 4), ...WW_BODY] },
  { id: 'expert', label: 'Expert bones', expert: true, bones: EXPERT },
];
// The engine's BONE_GROUPS when it has them in a shape this list understands, else the table above.
function normGroups(G) {
  if (!Array.isArray(G) || !G.length) return null;
  try {
    const out = G.map((g, i) => {
      const lab = g.label || g.name || g.title;
      const sub = g.sub || g.groups || g.subgroups;
      const bones = g.bones || g.list;
      if (!lab || (!Array.isArray(bones) && !Array.isArray(sub))) throw new Error('shape');
      return { id: g.id || String(lab).toLowerCase().replace(/\W+/g, '') || 'g' + i, label: lab, expert: !!g.expert, face: /face/i.test(lab), ww: /wicked/i.test(lab),
        bones: Array.isArray(bones) ? bones : null,
        sub: Array.isArray(sub) ? sub.map(s => ({ label: s.label || s.name || s.title, bones: s.bones || s.list || [] })) : null };
    });
    return out;
  } catch { return null; }
}
export const BONE_GROUPS = normGroups(B.BONE_GROUPS) || FALLBACK_GROUPS;
const FALLBACK_WORDS = {
  eyebrow: 'Brow', brow: 'Brow', eyelid: 'Lid', lid: 'Lid', blink: 'Lid', look: 'Eye', eye: 'Eye', smile: 'Mouth', corner: 'Mouth',
  lip: 'Lip', lips: 'Lip', chin: 'Jaw|Chin', jaw: 'Jaw', tongue: 'Tounge', nose: 'Nostril|Nose', nostril: 'Nostril',
  wrist: 'ForearmTwist|Hand', knee: 'Calf', shin: 'Calf', ankle: 'Foot', hip: 'Pelvis|Thigh', hips: 'Pelvis|Thigh',
  back: 'Spine', chest: 'Spine2', boob: 'Breast', boobs: 'Breast', breast: 'Breast', tit: 'Breast', tits: 'Breast',
  ass: 'Butt', butt: 'Butt', dick: 'Penis', cock: 'Penis', penis: 'Penis', balls: 'Testicle', pussy: 'Vagina', vagina: 'Vagina',
  finger: 'Thumb|Index|Mid|Ring|Pinky', fingers: 'Thumb|Index|Mid|Ring|Pinky', thumb: 'Thumb', toe: 'Toe', toes: 'Toe',
  shoulder: 'Clavicle|ShoulderTwist', elbow: 'Forearm|Elbow', twist: 'Twist', cheek: 'Cheek|Squint', mouth: 'Mouth|Lip|Jaw',
};
// (the list also finds the mouth corners for "lip": they are the ends of the lips)
export const SEARCH_WORDS = { ...FALLBACK_WORDS, ...((B.SEARCH_WORDS && typeof B.SEARCH_WORDS === 'object') ? B.SEARCH_WORDS : {}), lip: 'Lip|Mouth', lips: 'Lip|Mouth' };

/** Does a bone match what was typed in the list's search box (plain name, raw name, or a search word)? */
export function boneMatches(name, query, frame) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return true;
  const plain = label(name, frame).toLowerCase(), raw = name.toLowerCase();
  return q.split(/\s+/).every(w => {
    if (plain.includes(w) || raw.includes(w)) return true;
    for (const [word, pat] of Object.entries(SEARCH_WORDS)) {
      if (!(w.length >= 3 ? word.startsWith(w) : word === w)) continue;
      const parts = String(pat).split('|');
      if (parts.some(p => raw.includes(p.toLowerCase()))) return true;
    }
    return false;
  });
}

// ---------------------------------------------------------------- picking (bones.controllableIndex with modes)
const POSABLE_SET = B.POSABLE_SET || new Set(B.POSABLE);
const CAS_TO = { CAS_L_EyeScale: 'b__L_UpLid__', CAS_R_EyeScale: 'b__R_UpLid__', CAS_L_EyeArea: 'b__L_MidBrow__', CAS_R_EyeArea: 'b__R_MidBrow__',
  CAS_UpperMouthArea: 'b__UpLip__', CAS_LowerMouthArea: 'b__LoLip__', CAS_JawComp: 'b__Jaw__', CAS_Chin: 'b__Jaw__',
  CAS_NoseArea: 'b__Head__', CAS_NoseTip: 'b__Head__', CAS_NoseBridge: 'b__Head__' };
function nameIndex(rig) {
  if (!rig._waIdx) { rig._waIdx = new Map(); rig.bones.forEach((b, k) => rig._waIdx.set(b.name, k)); }
  return rig._waIdx;
}
/** The part a clicked bone belongs to. mode 'body' (today's parts; the jaw and tongue are picked directly),
 * 'face' (every face bone is its own part, CAS helpers hand over to what they move) or 'exact' (Alt+click). */
export function controllableIndex(rig, index, mode = 'body') {
  if (B.KEYABLE && B.controllableIndex) return B.controllableIndex(rig, index, mode);
  const idx = nameIndex(rig), pelvis = idx.get('b__Pelvis__') ?? 0;
  for (let k = index; k >= 0; k = rig.bones[k].parent) {
    const n = rig.bones[k].name;
    if (n === 'b__ROOT_bind__' || n === 'b__ROOT__') return pelvis;
    if (mode === 'exact') { if (KEYABLE_SET.has(n)) return k; continue; }
    if (mode === 'face') {
      if (FACE_SET.has(n)) return k;
      const cas = CAS_TO[n.replace(/^b__|__$/g, '')];
      if (cas && idx.has(cas)) return idx.get(cas);
    } else if (n === 'b__Jaw__' || /^b__Tounge__/.test(n)) return k;
    if (POSABLE_SET.has(n) && !FACE_SET.has(n)) return k;
  }
  return pelvis;
}

// ---------------------------------------------------------------- rest values (animation.restOf)
const REST = {};
export function setRig(rig) {
  for (const b of rig.bones) REST[b.name] = { t: b.pos.slice(), r: b.rot.slice() };
}
export function restOf(name) {
  if (A.restOf) { const r = A.restOf(name); if (r) return r; }
  return REST[name] || null;
}
const qRest = n => new THREE.Quaternion().fromArray(restOf(n).r);
const pRest = n => new THREE.Vector3().fromArray(restOf(n).t);

// ---------------------------------------------------------------- the face channel (animation.js)
const NEAR_ROT = deg(0.2), NEAR_POS = 0.0002;
function farFromRest(n, r, t) {
  const rest = restOf(n);
  if (!rest) return true;
  if (r) { const a = new THREE.Quaternion().fromArray(r).normalize().angleTo(qRest(n)); if (a > NEAR_ROT) return true; }
  if (t) { const d = Math.hypot(t[0] - rest.t[0], t[1] - rest.t[1], t[2] - rest.t[2]); if (d > NEAR_POS) return true; }
  return false;
}
/** The face bones of a clip sample: sparse (only bones away from rest) or dense (every face bone in the sample). */
export function sampleToFaceBones(sample, opts = {}) {
  if (A.sampleToFaceBones) return A.sampleToFaceBones(sample, opts);
  const dense = !!opts.dense, rot = {}, pos = {};
  for (const n of FACE_CHANNEL) {
    const s = sample[n];
    if (!s) continue;
    if (!dense && !farFromRest(n, s.r, s.t)) continue;
    if (s.r) rot[n] = s.r.slice();
    if (s.t) pos[n] = s.t.slice();
  }
  return { rot, pos };
}
/** Only the face bones away from rest (0.2 degrees / 0.2 mm), as a key stores them. */
export function sparseFaceBones(fb) {
  const rot = {}, pos = {};
  for (const [n, q] of Object.entries((fb && fb.rot) || {})) if (farFromRest(n, q, null)) rot[n] = q.slice();
  for (const [n, t] of Object.entries((fb && fb.pos) || {})) if (farFromRest(n, null, t)) pos[n] = t.slice();
  return { rot, pos };
}
/** The hand-posed face between face keys (null when the sim has none). */
export function evaluateFaceBones(keys, frame, length, loop) {
  if (A.evaluateFaceBones) return A.evaluateFaceBones(keys, frame, length, loop);
  const fk = keys.filter(k => k.faceBones && k.frame < (length || Infinity));
  if (!fk.length) return null;
  // a face bone a key does not mention is at rest in that key
  const rn = new Set(), pn = new Set();
  for (const k of fk) { for (const n in k.faceBones.rot || {}) rn.add(n); for (const n in k.faceBones.pos || {}) pn.add(n); }
  const dense = k => {
    const rot = {}, pos = {};
    for (const n of rn) rot[n] = (k.faceBones.rot || {})[n] || (restOf(n) ? restOf(n).r : null);
    for (const n of pn) pos[n] = (k.faceBones.pos || {})[n] || (restOf(n) ? restOf(n).t : null);
    for (const n in rot) if (!rot[n]) delete rot[n];
    for (const n in pos) if (!pos[n]) delete pos[n];
    return { rot, pos };
  };
  return A.evaluate(fk.map(k => ({ frame: k.frame, ease: k.ease, pose: dense(k) })), frame, length, loop);
}
/** One mirror rule for face bones: position (x, y, z) -> (x, y, -z), turn from rest (x, y, z, w) -> (-x, -y, z, w). */
export function mirrorFaceBonesData(fb) {
  if (A.mirrorFaceBonesData) return A.mirrorFaceBonesData(fb);
  const out = { rot: {}, pos: {} };
  for (const [n, q] of Object.entries((fb && fb.rot) || {})) {
    const to = mirrorName(n);
    if (!restOf(n) || !restOf(to)) { out.rot[to] = q.slice(); continue; }
    const rel = qRest(n).invert().multiply(new THREE.Quaternion().fromArray(q));
    out.rot[to] = qRest(to).multiply(new THREE.Quaternion(-rel.x, -rel.y, rel.z, rel.w)).toArray();
  }
  for (const [n, p] of Object.entries((fb && fb.pos) || {})) {
    const to = mirrorName(n);
    if (!restOf(n) || !restOf(to)) { out.pos[to] = p.slice(); continue; }
    const d = new THREE.Vector3().fromArray(p).sub(pRest(n));
    out.pos[to] = pRest(to).add(new THREE.Vector3(d.x, d.y, -d.z)).toArray();
  }
  return out;
}
/** The signed turn of restQ^-1 * q about `axis` (swing-twist), in radians. */
export function twistAngle(restQ, q, axis = X) {
  if (A.twistAngle) return A.twistAngle(restQ, q, axis);
  const d = restQ.clone().invert().multiply(q);
  const s = d.w < 0 ? -1 : 1;
  const p = new THREE.Vector3(d.x, d.y, d.z).multiplyScalar(s).dot(axis);
  return 2 * Math.atan2(p, s * d.w);
}

// Where keys are needed to follow a sampled motion (one pose per frame) with straight in-betweens: the first
// frame (and the last one when it doesn't loop), then - split by split - the frame that strays most, until no frame
// is further than the tolerance (0.25 degrees, 1 mm, 2% of a face slider by default) from the real motion.
const _qa = new THREE.Quaternion(), _qb = new THREE.Quaternion(), _qc = new THREE.Quaternion();
export function keyFramesFor(poses, faces, loop, opts = {}) {
  if (A.keyFramesFor) return A.keyFramesFor(poses, faces, loop, opts);
  const { angle = deg(0.25), pos: tolPos = 0.001, face: tolFace = 0.02 } = opts;
  const n = poses.length;
  if (n <= 2) return poses.map((p, i) => i);
  const at = i => (i === n ? 0 : i);
  const err = (a, b, i) => {
    const t = (i - a) / (b - a), P0 = poses[at(a)], P1 = poses[at(b)], P = poses[i];
    let e = 0;
    for (const bone of Object.keys(P.rot || {})) {
      const qa = (P0.rot || {})[bone], qb = (P1.rot || {})[bone];
      if (!qa || !qb) continue;
      _qa.fromArray(qa).normalize(); _qb.fromArray(qb).normalize(); _qc.fromArray(P.rot[bone]).normalize();
      _qa.slerp(_qb, t);
      e = Math.max(e, _qa.angleTo(_qc) / angle);
    }
    for (const bone of Object.keys(P.pos || {})) {
      const va = (P0.pos || {})[bone], vb = (P1.pos || {})[bone], v = P.pos[bone];
      if (!va || !vb) continue;
      const d = Math.hypot(va[0] + (vb[0] - va[0]) * t - v[0], va[1] + (vb[1] - va[1]) * t - v[1], va[2] + (vb[2] - va[2]) * t - v[2]);
      e = Math.max(e, d / tolPos);
    }
    if (faces) {
      const Fa = faces[at(a)], Fb = faces[at(b)], Fi = faces[i];
      if (Fa || Fb || Fi) {
        for (const k of new Set([...Object.keys(Fa || {}), ...Object.keys(Fb || {}), ...Object.keys(Fi || {})])) {
          const x = ((Fa || {})[k] || 0) + (((Fb || {})[k] || 0) - ((Fa || {})[k] || 0)) * t;
          e = Math.max(e, Math.abs(x - ((Fi || {})[k] || 0)) / tolFace);
        }
      }
    }
    return e;
  };
  const keys = new Set([0]);
  const stack = [[0, loop ? n : n - 1]];
  if (!loop) keys.add(n - 1);
  while (stack.length) {
    const [a, b] = stack.pop();
    if (b - a < 2) continue;
    let worst = -1, we = 1;
    for (let i = a + 1; i < b; i++) { const e = err(a, b, i); if (e > we) { we = e; worst = i; } }
    if (worst < 0) continue;
    keys.add(worst);
    stack.push([a, worst], [worst, b]);
  }
  return [...keys].sort((x, y) => x - y);
}

// ---------------------------------------------------------------- a sim's face bones (sim.js)
/** The bone as the keys have it (without the automatic layer: sliders, blinking, twist...): {q, p}. */
export function baseOf(v, name) {
  const b = v.bone(name);
  if (!b) return null;
  if (typeof v._base === 'function') { const r = v._base(name); if (r && r.q && r.p) return { q: r.q.clone(), p: r.p.clone() }; }
  const d = v.layerDelta && v.layerDelta.get && v.layerDelta.get(name);
  if (d && d.q && d.p && !d.abs) return { q: b.quaternion.clone().multiply(d.q.clone().invert()), p: b.position.clone().sub(d.p) };
  return { q: b.quaternion.clone(), p: b.position.clone() };
}
/** Set a bone's keyed value; an additive automatic layer (sliders, blinking) stays on top (final = base * layer). */
export function setBase(v, name, q, p) {
  const b = v.bone(name);
  if (!b) return;
  const d = v.layerDelta && v.layerDelta.get && v.layerDelta.get(name);
  const on = d && d.q && d.p && !d.abs;
  if (q) b.quaternion.copy(on ? q.clone().multiply(d.q) : q);
  if (p) b.position.copy(on ? p.clone().add(d.p) : p);
}
/** Sparse {rot, pos} of the face bones as posed by hand (withLayer: as shown, sliders included). */
export function getFaceBones(v, opts = {}) {
  if (typeof v.getFaceBones === 'function') return v.getFaceBones(opts);
  const rot = {}, pos = {};
  for (const n of FACE_CHANNEL) {
    const b = v.bone(n);
    if (!b || !v.restByName[n]) continue;
    const cur = opts.withLayer ? { q: b.quaternion, p: b.position } : baseOf(v, n);
    const r = v.restByName[n];
    if (cur.q.angleTo(r.quat) > 1e-3) rot[n] = cur.q.toArray();
    if (cur.p.distanceTo(r.pos) > 0.00005) pos[n] = cur.p.toArray();
  }
  return { rot, pos };
}
/** Set the face bones (the ones not mentioned go to rest). */
export function setFaceBones(v, fb) {
  if (typeof v.setFaceBones === 'function') return v.setFaceBones(fb);
  for (const n of FACE_CHANNEL) {
    const b = v.bone(n), r = v.restByName[n];
    if (!b || !r) continue;
    b.quaternion.copy(r.quat); b.position.copy(r.pos);
  }
  if (!fb) return;
  for (const [n, q] of Object.entries(fb.rot || {})) { const b = v.bone(n); if (b) b.quaternion.fromArray(q); }
  for (const [n, p] of Object.entries(fb.pos || {})) { const b = v.bone(n); if (b) b.position.fromArray(p); }
}
/** Hover glow and selection tint per face part ('face') or per body part ('body'). */
export function setPickMode(v, mode) {
  if (typeof v.setPickMode === 'function') return v.setPickMode(mode);
  if (v.pickMode === mode) return;
  v.pickMode = mode;
  v._ctrl = v.rig.bones.map((b, k) => controllableIndex(v.rig, k, mode));
  v.highlighted = null; v.hovered = -2;
}
/** Where a face bone's dot sits, in the bone's own rest frame (cached per bone and body). */
export function faceHandlePoint(v, name) {
  if (typeof v.faceHandlePoint === 'function') { const p = v.faceHandlePoint(name); if (p) return p; }
  v._fhp = v._fhp || {};
  if (name in v._fhp) return v._fhp[name];
  const src = name === 'b__Jaw__' ? 'b__CAS_Chin__' : name;
  const id = v.index(src), anchor = v.index(name);
  let out = new THREE.Vector3();
  if (id >= 0 && anchor >= 0) {
    let best = 0;
    const hits = [];
    for (const mesh of v.meshes) {
      if (/penis/.test(mesh.userData.role || '')) continue;
      const pa = mesh.geometry.attributes.position, si = mesh.geometry.attributes.skinIndex, sw = mesh.geometry.attributes.skinWeight;
      for (let i = 0; i < pa.count; i++) {
        let w = 0;
        for (let k = 0; k < 4; k++) if (si.getComponent(i, k) === id) w += sw.getComponent(i, k);
        if (w > 0) { hits.push([pa.getX(i), pa.getY(i), pa.getZ(i), w]); if (w > best) best = w; }
      }
    }
    const sum = new THREE.Vector3(); let c = 0;
    for (const [x, y, z, w] of hits) if (w >= best * 0.6) { sum.x += x; sum.y += y; sum.z += z; c++; }
    if (c) {
      sum.multiplyScalar(1 / c);
      // bind pose = the rig's rest: into the anchor bone's rest frame
      const restWorld = [];
      v.rig.bones.forEach((b, k) => {
        const m = new THREE.Matrix4().compose(new THREE.Vector3().fromArray(b.pos), new THREE.Quaternion().fromArray(b.rot), new THREE.Vector3(1, 1, 1));
        restWorld[k] = b.parent >= 0 ? restWorld[b.parent].clone().multiply(m) : m;
      });
      out = sum.applyMatrix4(restWorld[anchor].clone().invert());
    }
  }
  if (/_Eye__$/.test(name)) out.y += 0.011;                   // on the pupil
  return (v._fhp[name] = out);
}

// ---------------------------------------------------------------- face tools (face.js)
/** Keep one face bone's keyed value inside its safe range (per axis). True when it had to stop it. */
export function clampFaceBone(v, name, lim = faceLimits(name)) {
  if (F.clampFaceBone) return F.clampFaceBone(v, name, lim);
  if (!lim || !v.restByName[name]) return false;
  const base = baseOf(v, name), rest = v.restByName[name];
  let hit = false;
  const d = base.p.clone().sub(rest.pos);
  ['x', 'y', 'z'].forEach((ax, i) => {
    const r = lim.move[i];
    if (!r) return;
    const c = clamp(d[ax], r[0], r[1]);
    if (Math.abs(c - d[ax]) > 1e-7) { d[ax] = c; hit = true; }
  });
  const e = new THREE.Euler().setFromQuaternion(rest.quat.clone().invert().multiply(base.q), 'XYZ');
  let turned = false;
  ['x', 'y', 'z'].forEach((ax, i) => {
    const r = lim.turn[i];
    if (!r) return;
    const c = clamp(e[ax], r[0], r[1]);
    if (Math.abs(c - e[ax]) > 1e-6) { e[ax] = c; turned = true; }
  });
  if (!hit && !turned) return false;
  setBase(v, name, turned ? rest.quat.clone().multiply(new THREE.Quaternion().setFromEuler(e)) : null, hit ? rest.pos.clone().add(d) : null);
  return true;
}
/** Mirror one face bone onto another (relative to rest); a middle bone onto itself drops its sideways part. */
export function mirrorFaceBone(v, from, to = from) {
  if (F.mirrorFaceBone) return F.mirrorFaceBone(v, from, to);
  const rf = v.restByName[from], rt = v.restByName[to];
  if (!rf || !rt) return;
  const b = baseOf(v, from);
  const rel = rf.quat.clone().invert().multiply(b.q);
  const d = b.p.clone().sub(rf.pos);
  let q, p;
  if (from === to) {
    q = rt.quat.clone().multiply(new THREE.Quaternion(0, 0, rel.z, rel.w).normalize());
    p = rt.pos.clone().add(new THREE.Vector3(d.x, d.y, 0));
  } else {
    q = rt.quat.clone().multiply(new THREE.Quaternion(-rel.x, -rel.y, rel.z, rel.w));
    p = rt.pos.clone().add(new THREE.Vector3(d.x, d.y, -d.z));
  }
  setBase(v, to, q, p);
}
/** Turn an eye to look at a point (world space), inside its safe range. */
export function aimEye(v, eyeName, target, lim = faceLimits(eyeName)) {
  if (F.aimEye) return F.aimEye(v, eyeName, target, lim);
  const eye = v.bone(eyeName), rest = v.restByName[eyeName];
  if (!eye || !rest) return;
  eye.parent.updateWorldMatrix(true, false);
  const local = eye.parent.worldToLocal(target.clone()).sub(rest.pos);
  const tr = (lim && lim.turn) || [];
  const yaw = clamp(Math.atan2(local.z, local.y), ...(tr[0] || [-deg(32), deg(32)]));
  const pitch = clamp(-Math.atan2(local.x, Math.hypot(local.y, local.z)), ...(tr[2] || [-deg(30), deg(30)]));
  const q = rest.quat.clone().multiply(new THREE.Quaternion().setFromAxisAngle(X, yaw)).multiply(new THREE.Quaternion().setFromAxisAngle(Z, pitch));
  setBase(v, eyeName, q, null);
}

// ---------------------------------------------------------------- the face sliders (face.js)
/** The slider channels; `more: true` ones are the extra channels (shown under "More"). */
export const FACE_SLIDERS = F.FACE_SLIDERS;
export const FACE_PRESETS = F.FACE_PRESETS;

// ---------------------------------------------------------------- pipeline stand-ins
/** The hand-posed face at a frame: a pending (unkeyed) one on this frame, else the keys'. */
export function keyedFace(app, sim, frame, useOverrides = true) {
  if (engineHasFace(app)) return app.pipeline.keyedFace(sim, frame, useOverrides);
  const ov = useOverrides && app.pipeline.overrides.get(sim.id);
  if (ov && ov.faceBones && ov.frame === Math.round(frame)) return ov.faceBones;
  const p = app.store.project;
  return evaluateFaceBones(sim.keys, frame, p.length, p.loop);
}
/** Twist helpers follow the hand / arm (the engine's pipeline.twist; nothing until it exists). */
export function twist(app, e) { if (app.pipeline && typeof app.pipeline.twist === 'function') app.pipeline.twist(e); }
/** Until the engine sets face bones from keys: put the keyed face under what is shown (sliders stay on top). */
export function overlayFaceKeys(app, e, frame, { editing = false, useOverrides = true } = {}) {
  if (engineHasFace(app)) return;
  const fb = keyedFace(app, e.sim, frame, useOverrides);
  if (!fb) return;
  const { v } = e;
  if (editing) {
    // posing: exactly the keyed values (only the bones the face keys mention; the others stay as they are)
    for (const [n, q] of Object.entries(fb.rot || {})) { const b = v.bone(n); if (b) b.quaternion.fromArray(q); }
    for (const [n, p] of Object.entries(fb.pos || {})) { const b = v.bone(n); if (b) b.position.fromArray(p); }
    return;
  }
  for (const [n, q] of Object.entries(fb.rot || {})) {
    const b = v.bone(n), r = v.restByName[n];
    if (!b || !r) continue;
    b.quaternion.copy(new THREE.Quaternion().fromArray(q).multiply(r.quat.clone().invert().multiply(b.quaternion)));
  }
  for (const [n, p] of Object.entries(fb.pos || {})) {
    const b = v.bone(n), r = v.restByName[n];
    if (!b || !r) continue;
    b.position.copy(new THREE.Vector3().fromArray(p).add(b.position.clone().sub(r.pos)));
  }
}
