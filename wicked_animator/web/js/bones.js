// Which bones of the Sims 4 rig (with WickedWhims' extra bones) can be posed, what they are called, and their pairs.
// Every one of the rig's 185 bones is in exactly one group: KEYABLE (128: body, twist helpers, WickedWhims body
// extras, expert bones and the 30 face bones) or never keyed (57: the two root bones, the 4 IK export poles and the
// 51 "_slot" bones).

import { $t } from './i18n.js';
const SIDES = ['Clavicle', 'UpperArm', 'Forearm', 'Hand',
  'Thumb0', 'Thumb1', 'Thumb2', 'Index0', 'Index1', 'Index2', 'Mid0', 'Mid1', 'Mid2',
  'Ring0', 'Ring1', 'Ring2', 'Pinky0', 'Pinky1', 'Pinky2',
  'Thigh', 'Calf', 'Foot', 'Toe'];

// The body channel: posed in every key. The jaw and tongue live in the face channel (key.faceBones).
export const CENTER = ['b__Pelvis__', 'b__Spine0__', 'b__Spine1__', 'b__Spine2__', 'b__Neck__', 'b__Head__'];
// WickedWhims: the penis can be aimed and bent, the tongue moved (only on bodies that have them)
export const PENIS = ['b__Penis_Base', 'b__Penis_Base01', 'b__Penis_Mid', 'b__Penis_Mid01', 'b__Penis_Tip'];
export const TONGUE = ['b__Tounge__1', 'b__Tounge__2', 'b__Tounge__3'];
export const POSABLE = [...CENTER, ...SIDES.flatMap(s => [`b__L_${s}__`, `b__R_${s}__`]), ...PENIS.slice(0, 4)];   // 56
export const POSABLE_SET = new Set(POSABLE);

// Bones the automatic layers drive: soft tissue, holes, face.
export const BREASTS = ['b__CAS_L_Breast__', 'b__CAS_R_Breast__'];
export const BUTT = ['b__L_Butt__', 'b__R_Butt__'];
export const VAGINA = ['b__Penis_L_Testicle', 'b__Penis_R_Testicle', 'b__Up_Vagina__', 'b__Low_Vagina__'];
export const ANUS = ['b__L_Anus__', 'b__R_Anus__', 'b__Up_Anus', 'b__Low_Anus'];
export const FACE = ['b__L_UpLid__', 'b__R_UpLid__', 'b__L_LoLid__', 'b__R_LoLid__', 'b__L_Mouth__', 'b__R_Mouth__',
  'b__UpLip__', 'b__LoLip__', 'b__L_UpLip__', 'b__R_UpLip__', 'b__L_LoLip__', 'b__R_LoLip__',
  'b__L_InBrow__', 'b__R_InBrow__', 'b__L_MidBrow__', 'b__R_MidBrow__', 'b__L_OutBrow__', 'b__R_OutBrow__',
  'b__L_Cheek__', 'b__R_Cheek__', 'b__L_Squint__', 'b__R_Squint__', 'b__L_Eye__', 'b__R_Eye__'];
// bones the bake always records with their position
export const AUTO = [...BREASTS, ...BUTT, ...VAGINA, ...ANUS, ...FACE, 'b__Penis_Testicles', 'b__Anus'];

// ---------------------------------------------------------------- the face channel (key.faceBones)
export const NOSTRILS = ['b__CAS_L_Nostril__', 'b__CAS_R_Nostril__'];
export const FACE_CHANNEL = [...FACE, 'b__Jaw__', ...TONGUE, ...NOSTRILS];          // 30
export const FACE_SET = new Set(FACE_CHANNEL);

// ---------------------------------------------------------------- twist helpers
// Each follows its driver's turn about the bone's own x axis (measured on EA's and creators' clips).
// opt: only while the sim's body setting of that name is on ("Smooth hip twist", on by default - see pipeline.simBody).
export const TWIST = [
  ...['L', 'R'].map(s => ({ bone: `b__${s}_ForearmTwist__`, driver: `b__${s}_Hand__`, ratio: 0.5 })),
  ...['L', 'R'].map(s => ({ bone: `b__${s}_ShoulderTwist__`, driver: `b__${s}_UpperArm__`, ratio: -0.4 })),
  ...['L', 'R'].map(s => ({ bone: `b__${s}_ThighTwist__`, driver: `b__${s}_Thigh__`, ratio: -0.75, opt: 'hipTwist' })),
];
export const TWIST_SET = new Set(TWIST.map(t => t.bone));

// ---------------------------------------------------------------- the body channel's extra bones (sparse in keys)
export const WW_BODY = [...BREASTS, ...BUTT, 'b__Penis_Tip', 'b__Penis_Testicles', 'b__Penis_L_Testicle',
  'b__Penis_R_Testicle', 'b__Up_Vagina__', 'b__Low_Vagina__', 'b__Anus', 'b__L_Anus__', 'b__R_Anus__', 'b__Up_Anus', 'b__Low_Anus'];
// Hidden until switched on: helpers creators almost never key, and the game's Create-a-Sim shape bones.
export const EXPERT = ['b__L_Elbow__', 'b__R_Elbow__', 'b__L_Skirt__', 'b__R_Skirt__', 'b__CAS_Glasses__',
  'b__CAS_L_EyeArea__', 'b__CAS_R_EyeArea__', 'b__CAS_L_EyeScale__', 'b__CAS_R_EyeScale__', 'b__CAS_NoseArea__', 'b__CAS_NoseTip__',
  'b__CAS_NoseBridge__', 'b__CAS_UpperMouthArea__', 'b__CAS_LowerMouthArea__', 'b__CAS_JawComp__', 'b__CAS_Chin__',
  'b__L_Prop__', 'b__R_Prop__', 'b__Carry__', 'b__L_Stigmata', 'b__R_Stigmata'];
export const EXPERT_SET = new Set(EXPERT);
export const EXTRA = [...TWIST.map(t => t.bone), ...WW_BODY, ...EXPERT];
export const EXTRA_SET = new Set(EXTRA);
export const KEYABLE = [...POSABLE, ...EXTRA, ...FACE_CHANNEL];                       // 128
export const KEYABLE_SET = new Set(KEYABLE);
// Which body a WickedWhims bone needs ('penis', 'vagina', or either: the testicle bones are the vagina lips on women)
export const WW_NEEDS = {
  b__Penis_Base: 'penis', b__Penis_Base01: 'penis', b__Penis_Mid: 'penis', b__Penis_Mid01: 'penis', b__Penis_Tip: 'penis',
  b__Up_Vagina__: 'vagina', b__Low_Vagina__: 'vagina',
};

// These two carry each sim's place in the scene (WickedWhims clips have no root motion).
export const HIPS = ['b__Spine0__', 'b__Pelvis__'];
export const HIPS_SET = new Set(HIPS);

// The mouth: jaw, lips, corners and tongue. When any of them is animated the game must not lip-sync over it.
export const MOUTH = ['b__Jaw__', 'b__UpLip__', 'b__LoLip__', 'b__L_UpLip__', 'b__R_UpLip__', 'b__L_LoLip__', 'b__R_LoLip__',
  'b__L_Mouth__', 'b__R_Mouth__', ...TONGUE];

// Joints that only bend one way, like a door hinge: elbows, knees and the middle and tip joints of the fingers.
// In the game they must only turn about their own local Z axis. Checked on the rig (their rest turn is a pure Z
// turn) and on ~280 creator clips (median off-Z part 0°; forearms bend to +Z, calves to -Z, fingers curl to +Z).
// Value = which way the joint bends from straight.
export const HINGE = {};
for (const s of ['L', 'R']) {
  HINGE[`b__${s}_Forearm__`] = 1;
  HINGE[`b__${s}_Calf__`] = -1;
  for (const f of ['Thumb', 'Index', 'Mid', 'Ring', 'Pinky']) { HINGE[`b__${s}_${f}1__`] = 1; HINGE[`b__${s}_${f}2__`] = 1; }
}

// Two-bone chains dragged by their end.
export const LIMBS = {
  'L hand': ['b__L_UpperArm__', 'b__L_Forearm__', 'b__L_Hand__'],
  'R hand': ['b__R_UpperArm__', 'b__R_Forearm__', 'b__R_Hand__'],
  'L foot': ['b__L_Thigh__', 'b__L_Calf__', 'b__L_Foot__'],
  'R foot': ['b__R_Thigh__', 'b__R_Calf__', 'b__R_Foot__'],
};
export const LIMB_LABEL = { 'L hand': $t('bones.left_hand'), 'R hand': $t('bones.right_hand'), 'L foot': $t('bones.left_foot'), 'R foot': $t('bones.right_foot') };

// ---------------------------------------------------------------- safe ranges for face parts (spec_face_bones 3.1)
// Creators' per-clip p5..p95, widened about 1.5x. [default gizmo, move x, y, z (mm), turn x, y, z (degrees)] for the
// left side and the middle; null = locked by default (the gizmo hides that axis, Alt unlocks it). Moves: x down-/up+,
// y back-/forward+, z in-/out+ on the left side (right-/left+ on middle bones).
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
  UpLip: ['move', [-4, 12], [-4, 5], [-2, 8], null, null, [-35, 20]],
  LoLip: ['move', [-8, 8], [-5, 6], [-2, 10], null, null, [-50, 30]],
  b__UpLip__: ['move', [-5, 9], [-4, 8], [-2, 2], null, null, [-35, 15]],
  b__LoLip__: ['move', [-8, 7], [-3, 9], [-2, 2], null, null, [-50, 30]],
  b__Jaw__: ['turn', null, [-6, 10], null, [-4, 4], [-5, 5], [-40, 3]],
  b__Tounge__1: ['move', [-4, 10], [-2, 70], [-4, 4], [-12, 12], [-12, 12], [-30, 25]],
  b__Tounge__2: ['turn', null, [-10, 40], null, [-20, 20], [-15, 15], [-60, 50]],
  b__Tounge__3: ['turn', null, null, null, [-28, 12], [-18, 12], [-60, 50]],
};
export const FACE_LIMITS = LIM;

// The part name of a face bone ('InBrow', 'Nostril', 'b__UpLip__'...) and its side ('L', 'R' or '').
function facePart(name) {
  if (LIM[name]) return { part: name, side: '' };
  const m = /^b__(?:CAS_)?(L|R)_(\w+?)__$/.exec(name);
  return m && LIM[m[2]] ? { part: m[2], side: m[1] } : null;
}
const DEG = Math.PI / 180;
const flip = r => (r ? [-r[1], -r[0]] : null);
const _limCache = new Map();
// {mode: 'move'|'turn', move: [[lo, hi] | null] x3 in metres, turn: [[lo, hi] | null] x3 in radians}, relative to
// rest. Right-side bones are mirrored: their move-z range and turn-x and turn-y ranges are negated and swapped.
export function faceLimits(name) {
  if (_limCache.has(name)) return _limCache.get(name);
  const fp = facePart(name);
  let out = null;
  if (fp) {
    const [mode, mx, my, mz, tx, ty, tz] = LIM[fp.part], R = fp.side === 'R';
    const mm = r => (r ? [r[0] / 1000, r[1] / 1000] : null), dg = r => (r ? [r[0] * DEG, r[1] * DEG] : null);
    out = { mode, move: [mm(mx), mm(my), mm(R ? flip(mz) : mz)], turn: [dg(R ? flip(tx) : tx), dg(R ? flip(ty) : ty), dg(tz)] };
  }
  _limCache.set(name, out);
  return out;
}

// ---------------------------------------------------------------- face dots (spec_face_bones 3.2)
// Region order is the order the dots bloom in.
export const FACE_HANDLES = {
  brows: { label: $t('bones.brows'), color: '#ff7ab6', bones: ['b__L_InBrow__', 'b__L_MidBrow__', 'b__L_OutBrow__', 'b__R_InBrow__', 'b__R_MidBrow__', 'b__R_OutBrow__'] },
  eyes: { label: $t('bones.eyes_and_lids'), color: '#57b8ff', bones: ['b__L_Eye__', 'b__L_UpLid__', 'b__L_LoLid__', 'b__R_Eye__', 'b__R_UpLid__', 'b__R_LoLid__'] },
  cheeks: { label: $t('bones.cheeks_and_nose'), color: '#ffb547', bones: ['b__L_Cheek__', 'b__L_Squint__', 'b__CAS_L_Nostril__', 'b__R_Cheek__', 'b__R_Squint__', 'b__CAS_R_Nostril__'] },
  mouth: { label: $t('bones.mouth'), color: '#ff4f6a', bones: ['b__UpLip__', 'b__L_UpLip__', 'b__R_UpLip__', 'b__L_Mouth__', 'b__R_Mouth__', 'b__LoLip__', 'b__L_LoLip__', 'b__R_LoLip__'] },
  jaw: { label: $t('bones.jaw_and_tongue'), color: '#a78bfa', bones: ['b__Jaw__', ...TONGUE] },
};
export const FACE_REGIONS = Object.keys(FACE_HANDLES);
// Guide lines (drawn at 35% in the region colour): each brow Out-Mid-In, and the lip loop. Each eye also gets a ring.
export const FACE_GUIDES = [
  ['b__L_OutBrow__', 'b__L_MidBrow__'], ['b__L_MidBrow__', 'b__L_InBrow__'],
  ['b__R_OutBrow__', 'b__R_MidBrow__'], ['b__R_MidBrow__', 'b__R_InBrow__'],
  ['b__L_Mouth__', 'b__L_UpLip__'], ['b__L_UpLip__', 'b__UpLip__'], ['b__UpLip__', 'b__R_UpLip__'], ['b__R_UpLip__', 'b__R_Mouth__'],
  ['b__R_Mouth__', 'b__R_LoLip__'], ['b__R_LoLip__', 'b__LoLip__'], ['b__LoLip__', 'b__L_LoLip__'], ['b__L_LoLip__', 'b__L_Mouth__'],
];
const _region = {};
for (const [r, x] of Object.entries(FACE_HANDLES)) for (const b of x.bones) _region[b] = r;
export function faceRegion(name) { return _region[name] || null; }
export const isCenterFace = n => FACE_SET.has(n) && !/_(L|R)_/.test(n);

// ---------------------------------------------------------------- names
const NICE = {
  Pelvis: $t('bones.hips'), Spine0: $t('bones.lower_back'), Spine1: $t('bones.middle_back'), Spine2: $t('bones.chest'), Neck: $t('bones.neck'), Head: $t('bones.head'), Jaw: $t('bones.jaw'),
  Clavicle: $t('bones.shoulder'), UpperArm: $t('bones.upper_arm'), Forearm: $t('bones.forearm'), Hand: $t('bones.hand'),
  Thumb0: $t('bones.thumb_base'), Thumb1: $t('bones.thumb_middle'), Thumb2: $t('bones.thumb_tip'),
  Index0: $t('bones.index_base'), Index1: $t('bones.index_middle'), Index2: $t('bones.index_tip'),
  Mid0: $t('bones.middle_finger_base'), Mid1: $t('bones.middle_finger_middle'), Mid2: $t('bones.middle_finger_tip'),
  Ring0: $t('bones.ring_finger_base'), Ring1: $t('bones.ring_finger_middle'), Ring2: $t('bones.ring_finger_tip'),
  Pinky0: $t('bones.pinky_base'), Pinky1: $t('bones.pinky_middle'), Pinky2: $t('bones.pinky_tip'),
  Thigh: $t('bones.thigh'), Calf: $t('bones.shin'), Foot: $t('bones.foot'), Toe: $t('bones.toes'),
  // face
  InBrow: $t('bones.inner_brow'), MidBrow: $t('bones.middle_brow'), OutBrow: $t('bones.outer_brow'), UpLid: $t('bones.upper_eyelid'), LoLid: $t('bones.lower_eyelid'), Eye: $t('bones.eye'),
  Cheek: $t('bones.cheek'), Squint: $t('bones.under_eye'), Mouth: $t('bones.mouth_corner'), UpLip: $t('bones.upper_lip'), LoLip: $t('bones.lower_lip'), Nostril: $t('bones.nostril'),
  // helpers and WickedWhims
  ShoulderTwist: $t('bones.upper_arm_twist'), ForearmTwist: $t('bones.wrist_twist'), ThighTwist: $t('bones.thigh_twist'), Elbow: $t('bones.elbow_helper'), Skirt: $t('bones.skirt_helper'),
  Breast: $t('bones.breast'), Butt: $t('bones.butt_cheek'), Prop: $t('bones.held_object'), Stigmata: $t('bones.palm_spot'), Anus: $t('bones.anus'),
};
const SPECIAL = {
  b__Penis_Base: $t('bones.penis_base'), b__Penis_Base01: $t('bones.penis_lower'), b__Penis_Mid: $t('bones.penis_middle'), b__Penis_Mid01: $t('bones.penis_upper'),
  b__Penis_Tip: $t('bones.penis_tip'), b__Tounge__1: $t('bones.tongue_back'), b__Tounge__2: $t('bones.tongue_middle'), b__Tounge__3: $t('bones.tongue_tip'),
  b__UpLip__: $t('bones.upper_lip_middle'), b__LoLip__: $t('bones.lower_lip_middle'), b__Penis_Testicles: $t('bones.balls'),
  b__Up_Vagina__: $t('bones.vagina_top'), b__Low_Vagina__: $t('bones.vagina_bottom'), b__Anus: $t('bones.anus'), b__Up_Anus: $t('bones.anus_top'), b__Low_Anus: $t('bones.anus_bottom'),
  b__Carry__: $t('bones.carry_helper'), b__CAS_Glasses__: $t('bones.glasses_shape'), b__CAS_NoseArea__: $t('bones.nose_shape'), b__CAS_NoseTip__: $t('bones.nose_tip_shape'),
  b__CAS_NoseBridge__: $t('bones.nose_bridge_shape'), b__CAS_UpperMouthArea__: $t('bones.upper_mouth_shape'), b__CAS_LowerMouthArea__: $t('bones.lower_mouth_shape'),
  b__CAS_JawComp__: $t('bones.jaw_width_shape'), b__CAS_Chin__: $t('bones.chin_shape'),
  b__CAS_L_EyeArea__: $t('bones.eye_area_left_shape'), b__CAS_R_EyeArea__: $t('bones.eye_area_right_shape'),
  b__CAS_L_EyeScale__: $t('bones.eye_size_left_shape'), b__CAS_R_EyeScale__: $t('bones.eye_size_right_shape'),
  b__ROOT__: $t('bones.root'), b__ROOT_bind__: $t('bones.root_placement'),
};

// Plain name of any bone ("Inner brow (left)"). `frame` is the body: on a woman ('yf') the WickedWhims testicle
// bones are the vagina lips.
export function label(name, frame) {
  if (SPECIAL[name]) return SPECIAL[name];
  let m = /^b__Penis_(L|R)_Testicle$/.exec(name);
  if (m) {
    const side = m[1] === 'L' ? $t('bones.left') : $t('bones.right');
    return frame === 'yf' ? $t('bones.vagina_lip', { side }) : $t(m[1] === 'L' ? 'bones.left_ball' : 'bones.right_ball');
  }
  m = /^b__(?:CAS_)?(?:(L|R)_)?(.+?)(?:__)?$/.exec(name);
  if (!m) return name;
  const base = NICE[m[2]] || m[2];
  return m[1] ? $t('bones.part_side', { part: base, side: m[1] === 'L' ? $t('bones.left') : $t('bones.right') }) : base;
}

export function mirrorName(name) {
  if (name.includes('_L_')) return name.replace('_L_', '_R_');
  if (name.includes('_R_')) return name.replace('_R_', '_L_');
  return name;
}

// ---------------------------------------------------------------- the All bones list
const SIDE_ARM = s => [`b__${s}_Clavicle__`, `b__${s}_UpperArm__`, `b__${s}_ShoulderTwist__`, `b__${s}_Forearm__`, `b__${s}_ForearmTwist__`, `b__${s}_Hand__`];
const SIDE_FINGERS = s => ['Thumb', 'Index', 'Mid', 'Ring', 'Pinky'].flatMap(f => [0, 1, 2].map(i => `b__${s}_${f}${i}__`));
const SIDE_LEG = s => [`b__${s}_Thigh__`, `b__${s}_ThighTwist__`, `b__${s}_Calf__`, `b__${s}_Foot__`, `b__${s}_Toe__`];
// Grouped like Blender's outliner. Every KEYABLE bone is in exactly one group.
export const BONE_GROUPS = [
  { id: 'body', label: $t('bones.body'), bones: [...CENTER] },
  { id: 'larm', label: $t('bones.left_arm'), bones: SIDE_ARM('L') },
  { id: 'rarm', label: $t('bones.right_arm'), bones: SIDE_ARM('R') },
  { id: 'lfing', label: $t('bones.left_fingers'), bones: SIDE_FINGERS('L') },
  { id: 'rfing', label: $t('bones.right_fingers'), bones: SIDE_FINGERS('R') },
  { id: 'lleg', label: $t('bones.left_leg'), bones: SIDE_LEG('L') },
  { id: 'rleg', label: $t('bones.right_leg'), bones: SIDE_LEG('R') },
  { id: 'face', label: $t('bones.face'), face: true, sub: [
    { label: $t('bones.brows'), bones: FACE_HANDLES.brows.bones },
    { label: $t('bones.eyes_and_lids'), bones: FACE_HANDLES.eyes.bones },
    { label: $t('bones.cheeks_and_nose'), bones: FACE_HANDLES.cheeks.bones },
    { label: $t('bones.mouth'), bones: FACE_HANDLES.mouth.bones },
    { label: $t('bones.jaw_and_tongue'), bones: FACE_HANDLES.jaw.bones },
  ] },
  { id: 'ww', label: $t('bones.wickedwhims_body'), ww: true, bones: [...PENIS.slice(0, 4), ...WW_BODY] },
  { id: 'expert', label: $t('bones.expert_bones'), expert: true, bones: [...EXPERT] },
];

// Search words for the list: what people type -> parts of raw bone names ('|' = or). The rig's own spelling
// ("Tounge") and the plain names are matched as well.
export const SEARCH_WORDS = {
  eyebrow: 'Brow', eyebrows: 'Brow', brow: 'Brow', brows: 'Brow', forehead: 'Brow',
  eyelid: 'Lid', eyelids: 'Lid', lid: 'Lid', blink: 'Lid', wink: 'Lid', look: 'Eye', eye: 'Eye|Lid', eyes: 'Eye|Lid', pupil: 'Eye',
  smile: '_Mouth__', corner: '_Mouth__', frown: '_Mouth__', lip: 'Lip|_Mouth__', lips: 'Lip|_Mouth__', kiss: 'Lip|_Mouth__', pout: 'Lip',
  mouth: '_Mouth__|Lip|Jaw', chin: 'Jaw|Chin', jaw: 'Jaw', tongue: 'Tounge', lick: 'Tounge',
  cheek: 'Cheek|Squint', cheeks: 'Cheek|Squint', squint: 'Squint', nose: 'Nostril|Nose', nostril: 'Nostril',
  face: 'Brow|Lid|Eye|Cheek|Squint|Nostril|Mouth|Lip|Jaw|Tounge',
  wrist: 'ForearmTwist|Hand', knee: 'Calf', shin: 'Calf', leg: 'Thigh|Calf', ankle: 'Foot', heel: 'Foot', toe: 'Toe', toes: 'Toe',
  hip: 'Pelvis|Thigh', hips: 'Pelvis|Thigh', waist: 'Pelvis|Spine0', back: 'Spine', spine: 'Spine', chest: 'Spine2', torso: 'Spine',
  neck: 'Neck', head: 'Head', shoulder: 'Clavicle|ShoulderTwist', arm: 'UpperArm|Forearm', elbow: 'Forearm|Elbow',
  twist: 'Twist', helper: 'Twist|Elbow|Skirt',
  boob: 'Breast', boobs: 'Breast', breast: 'Breast', breasts: 'Breast', tit: 'Breast', tits: 'Breast',
  ass: 'Butt', butt: 'Butt', bum: 'Butt',
  dick: 'Penis', cock: 'Penis', penis: 'Penis', balls: 'Testicle', ball: 'Testicle', pussy: 'Vagina|Testicle', vagina: 'Vagina|Testicle',
  anal: 'Anus', anus: 'Anus',
  finger: 'Thumb|Index|Mid|Ring|Pinky', fingers: 'Thumb|Index|Mid|Ring|Pinky', hand: 'Hand|Thumb|Index|Mid|Ring|Pinky',
  thumb: 'Thumb', index: 'Index', pinky: 'Pinky', ring: 'Ring',
  shape: 'CAS_', expert: 'Elbow|Skirt|CAS_|Prop|Carry|Stigmata', prop: 'Prop', palm: 'Stigmata',
};

// Does a bone match what was typed in the list's search box (plain name, raw name, or a search word)?
export function boneMatches(name, query, frame) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return true;
  const plain = label(name, frame).toLowerCase(), raw = name.toLowerCase();
  return q.split(/\s+/).every(w => {
    if (plain.includes(w) || raw.includes(w)) return true;
    for (const [word, pat] of Object.entries(SEARCH_WORDS)) {
      if (!(w.length >= 3 ? word.startsWith(w) : word === w)) continue;
      if (pat.split('|').some(p => raw.includes(p.toLowerCase()))) return true;
    }
    return false;
  });
}

// ---------------------------------------------------------------- picking
// Face helpers of the Create-a-Sim shape hand over to the face part they move.
const CAS_TO = {
  b__CAS_L_EyeScale__: 'b__L_UpLid__', b__CAS_R_EyeScale__: 'b__R_UpLid__', b__CAS_L_EyeArea__: 'b__L_MidBrow__', b__CAS_R_EyeArea__: 'b__R_MidBrow__',
  b__CAS_UpperMouthArea__: 'b__UpLip__', b__CAS_LowerMouthArea__: 'b__LoLip__', b__CAS_JawComp__: 'b__Jaw__', b__CAS_Chin__: 'b__Jaw__',
  b__CAS_NoseArea__: 'b__Head__', b__CAS_NoseTip__: 'b__Head__', b__CAS_NoseBridge__: 'b__Head__', b__CAS_Glasses__: 'b__Head__',
};
const BODY_DIRECT = new Set(['b__Jaw__', ...TONGUE]);
function nameIndex(rig) {
  if (!rig._waIdx) { rig._waIdx = new Map(); rig.bones.forEach((b, k) => rig._waIdx.set(b.name, k)); }
  return rig._waIdx;
}

// The part a clicked bone belongs to.
//   'body'  (default) today's parts: twist/face/slot/CAS bones hand over to a posable parent; the jaw and the
//           tongue are picked directly
//   'face'  every face bone is its own part; CAS helpers under the face hand over to what they move
//   'exact' the first keyable bone up the chain (Alt+click)
export function controllableIndex(rig, index, mode = 'body') {
  const idx = nameIndex(rig), pelvis = idx.get('b__Pelvis__') ?? 0;
  for (let k = index; k >= 0; k = rig.bones[k].parent) {
    const n = rig.bones[k].name;
    if (n === 'b__ROOT_bind__' || n === 'b__ROOT__') return pelvis;
    if (mode === 'exact') { if (KEYABLE_SET.has(n)) return k; continue; }
    if (mode === 'face') {
      if (FACE_SET.has(n)) return k;
      if (CAS_TO[n] && idx.has(CAS_TO[n])) return idx.get(CAS_TO[n]);
    } else if (BODY_DIRECT.has(n)) return k;
    if (POSABLE_SET.has(n)) return k;
  }
  return pelvis;
}

// ---------------------------------------------------------------- body parts (partial paste, pose library, lag)
// The bones of each part in key.pose (a twist helper counts with its arm or leg: a key may pose it by hand). The
// face part is key.face (sliders) + key.faceBones (the 30 face bones, jaw and tongue included) - never key.pose -
// so no part lists the jaw or the tongue, and 'face' lists no key.pose bone at all (plan 2.1).
const P_FINGERS = s => ['Thumb', 'Index', 'Mid', 'Ring', 'Pinky'].flatMap(f => [0, 1, 2].map(k => `b__${s}_${f}${k}__`));
const P_ARM = s => [`b__${s}_Clavicle__`, `b__${s}_UpperArm__`, `b__${s}_ShoulderTwist__`, `b__${s}_Forearm__`, `b__${s}_ForearmTwist__`, `b__${s}_Hand__`];
const P_LEG = s => [`b__${s}_Thigh__`, `b__${s}_ThighTwist__`, `b__${s}_Calf__`, `b__${s}_Foot__`, `b__${s}_Toe__`];
export const BODY_PARTS = {
  all: POSABLE,
  upper: ['b__Spine0__', 'b__Spine1__', 'b__Spine2__', 'b__Neck__', 'b__Head__', ...P_ARM('L'), ...P_ARM('R'), ...P_FINGERS('L'), ...P_FINGERS('R')],
  lower: ['b__Pelvis__', ...P_LEG('L'), ...P_LEG('R'), ...PENIS.slice(0, 4)],
  hands: ['b__L_Hand__', 'b__R_Hand__', ...P_FINGERS('L'), ...P_FINGERS('R')],
  'L hand': ['b__L_Hand__', ...P_FINGERS('L')],
  'R hand': ['b__R_Hand__', ...P_FINGERS('R')],
  face: [],
};
export const PART_LABEL = { all: $t('bones.whole_body'), upper: $t('bones.upper_body'), lower: $t('bones.lower_body'), hands: $t('bones.both_hands'),
  'L hand': $t('bones.left_hand'), 'R hand': $t('bones.right_hand'), face: 'Face' };

// Turn together: one turn spread over a chain (parents first), each bone its share (the shares add up to 1).
export const TURN_GROUPS = {
  back: { label: $t('bones.whole_back'), bones: ['b__Spine0__', 'b__Spine1__', 'b__Spine2__', 'b__Neck__'], w: [0.25, 0.3, 0.3, 0.15] },
  neckHead: { label: $t('bones.neck_head'), bones: ['b__Neck__', 'b__Head__'], w: [0.45, 0.55] },
};

// ---------------------------------------------------------------- pins and holds (one union, plan 2.1)
//   [x, y, z]                              pinned for the whole loop (sim space)
//   { at: [x, y, z], from, to, fade }      pinned only between frames from..to (inclusive; wraps when the animation
//                                          loops and from > to), fading in and out over `fade` frames
//   { sim, bone, off, n, rot, label, from?, to?, fade? }   holding on to a partner (off / n / rot in that bone's frame)
export const mirrorLimb = l => (l[0] === 'L' ? 'R' + l.slice(1) : l[0] === 'R' ? 'L' + l.slice(1) : l);
export const pinAt = p => (Array.isArray(p) ? p : (p && Array.isArray(p.at) ? p.at : null));
export const isHold = p => !!(p && !Array.isArray(p) && p.sim && p.bone);
export function pinWeight(p, frame, length, loop) {
  if (Array.isArray(p) || !p || p.from === undefined || p.to === undefined || p.from === null || p.to === null) return 1;
  const { from, to } = p, fade = Math.max(0, p.fade ?? 3);
  const wrap = loop && from > to;
  const inside = wrap ? (frame >= from || frame <= to) : (frame >= from && frame <= to);
  if (inside) return 1;
  let d = wrap ? Math.min(from - frame, frame - to) : (frame < from ? from - frame : frame - to);
  if (loop && !wrap) d = Math.min(d, frame + length - to, from + length - frame);
  if (!fade || d >= fade) return 0;
  const u = 1 - d / fade;
  return u * u * (3 - 2 * u);
}

// The palm centre of each hand (EA's palm slot, 0.5 cm from the palm skin) and how far the palm centre / the foot
// bone stay off the skin they hold.
export const PALM = { 'L hand': 'b__L_Stigmata', 'R hand': 'b__R_Stigmata' };
export const PALM_GAP = 0.012, SOLE_GAP = 0.03;
// Named grab points: EA's touch-target slots on the rig (0.1-3 cm from the skin) - the hold chip's words and the
// "Hold her..." menu. [slot bones]; each name without a side is looked up with _L_ and _R_ (spec_bodies Appendix D).
const LR = n => [`b__L_${n}`, `b__R_${n}`];
export const GRAB = {
  hip: LR('ThighTarget_slot'),
  waist: LR('backBellyTarget_slot'),
  'lower back': LR('lowBackTarget_slot'),
  belly: [...LR('BellyTarget_slot'), ...LR('frontBellyTarget_slot')],
  back: [...LR('BackTarget_slot'), ...LR('sideBackTorsoTarget_slot')],
  chest: [...LR('chestTarget_slot'), ...LR('frontTorsoTarget_slot')],
  breast: LR('breastTarget_slot'),
  'shoulder blade': LR('shoulderbladeTarget_slot'),
  shoulder: LR('ShoulderTarget_slot'),
  thigh: [...LR('outThighTarget_slot'), ...LR('ThighFrontTarget_slot')],
  knee: LR('KneeTarget_slot'),
  calf: [...LR('frontCalfTarget_slot'), ...LR('inCalfTarget_slot')],
  forearm: LR('ForearmTarget_slot'),
  neck: ['b__Neck_slot', 'b__backNeck_slot'],
  face: ['b__mouth_slot'],
};
// The order the "Hold her..." menu lists them in.
export const GRAB_MENU = ['hip', 'waist', $t('bones.lower_back_2'), 'back', $t('bones.shoulder_blade'), 'shoulder', 'chest', 'breast', 'belly', 'thigh', 'knee', 'calf', 'neck', 'face'];
// The chip word for a point on a sim's skin: the nearest grab point within 15 cm, else the part's own name
// ('thigh (left)'). `v` is a Sim view; `pointWorld` any object with distanceTo (a THREE.Vector3).
export function grabLabel(v, pointWorld, anchor = null) {
  let best = null, bd = 0.15;
  for (const [word, slots] of Object.entries(GRAB)) {
    for (const s of slots) {
      if (!v.bone(s)) continue;
      const d = v.worldPos(s).distanceTo(pointWorld);
      if (d < bd) { bd = d; best = word; }
    }
  }
  return best || (anchor ? label(anchor).toLowerCase() : 'body');
}

// ---------------------------------------------------------------- natural limits (spec_bodies 5.2, Appendix C)
// Left-side rotation vectors from rest, degrees: { x: [lo, hi], y: [lo, hi], z: [lo, hi] }; hinges are z only (x and
// y at 0). The right side mirrors x and y. The middle bones (spine, neck, head) turn and lean the same both ways, so
// their x and y ranges are made symmetric (creators' data leans one way). Pelvis, Spine0, UpperArm, Thigh, Hand and
// Foot carry placement or reach +-90-180 degrees: not limited.
const HINGE_Z = z => ({ x: [0, 0], y: [0, 0], z, hinge: true });
const SYM = ({ x, y, z }) => { const m = r => Math.max(Math.abs(r[0]), Math.abs(r[1])); return { x: [-m(x), m(x)], y: [-m(y), m(y)], z }; };
export const LIMITS = {
  b__L_Thumb0__: { x: [-30, 58], y: [-26, 58], z: [-36, 25] },
  b__L_Thumb1__: HINGE_Z([-16, 55]),
  b__L_Thumb2__: HINGE_Z([-17, 72]),
  b__L_Index0__: { x: [-23, 20], y: [-24, 20], z: [-12, 95] },
  b__L_Mid0__: { x: [-19, 12], y: [-19, 12], z: [-11, 97] },
  b__L_Ring0__: { x: [-23, 10], y: [-20, 14], z: [-11, 97] },
  b__L_Pinky0__: { x: [-28, 10], y: [-30, 14], z: [-12, 100] },
  b__L_Forearm__: HINGE_Z([-10, 155]),
  b__L_Calf__: HINGE_Z([-170, 5]),
  b__L_Clavicle__: { x: [-57, 38], y: [-15, 48], z: [-43, 36] },
  b__L_Toe__: { x: [-12, 12], y: [-10, 10], z: [-51, 77] },
  b__Spine1__: SYM({ x: [-17, 19], y: [-26, 19], z: [-35, 45] }),
  b__Spine2__: SYM({ x: [-15, 14], y: [-15, 15], z: [-30, 41] }),
  b__Neck__: SYM({ x: [-34, 49], y: [-34, 34], z: [-65, 47] }),
  b__Head__: SYM({ x: [-51, 69], y: [-35, 29], z: [-61, 44] }),
};
for (const f of ['Index', 'Mid', 'Ring', 'Pinky']) {
  LIMITS[`b__L_${f}1__`] = HINGE_Z([-3, 100]);
  LIMITS[`b__L_${f}2__`] = HINGE_Z([-7, 95]);
}
// Knuckles (finger base joints): spread (y) and curl (z) only in the view - no twist ring.
export const KNUCKLE = new Set(['Index0', 'Mid0', 'Ring0', 'Pinky0'].flatMap(f => [`b__L_${f}__`, `b__R_${f}__`]));
const _limR = new Map();
export function limitsFor(name) {
  const L = LIMITS[name.replace('_R_', '_L_')];
  if (!L) return null;
  if (!name.includes('_R_')) return L;
  if (!_limR.has(name)) _limR.set(name, { x: [-L.x[1], -L.x[0]], y: [-L.y[1], -L.y[0]], z: L.z, hinge: L.hinge });
  return _limR.get(name);
}

export const SIM_COLORS = ['#ff4f9a', '#57b8ff', '#ffb547', '#a78bfa', '#3ddc97', '#ff8a5b'];
export const SKIN_TONES = ['#f3d2bd', '#e9b999', '#d59b76', '#b87a55', '#8d5a3b', '#5e3a26', '#f7e0cf', '#c98f6a'];
