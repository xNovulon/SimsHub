// Writes the FBX fixtures the motion-file checks read. One node tree, written either as ASCII FBX 7.4 (tab-indented,
// "Class::Name", Properties70 "P:" lines, "C:" connections) or as binary FBX 7.4 (the documented record layout:
// uint32 end offset, property count, property bytes, name; typed properties; zlib-compressed arrays; a 13-byte null
// record after every nested list; the file footer). Read back by three.js's FBXLoader in the checks.
//
//   bodyFBX(opts) -> tree   the test body of bvhgen.mjs with its known motion, as FBX:
//     names ('mixamo' | 'plain' | 'deepmotion' ...), fingers, prerot (every joint gets a joint orient / PreRotation),
//     rotOrder (FBX enum 0..5 on every joint), armature ({rot: [x, y, z] degrees, scale}: a Null parent, like
//     Blender's), fps, seconds, stacks ([{name, motion}]), skinned (a small skinned mesh + bind pose), noAnim
//   toASCII(tree), toBinary(tree, {compress}) -> text / Uint8Array
import zlib from 'node:zlib';
import * as THREE from 'three';
import { bodyJoints, ENDS, motionAt, namer } from './bvhgen.mjs';

export const TICKS = 46186158000;
const D2R = Math.PI / 180;
const THREE_ORDER = ['ZYX', 'YZX', 'XZY', 'ZXY', 'YXZ', 'XYZ'];      // FBX RotationOrder enum -> three.js (FBXLoader)

// ---------------------------------------------------------------- the node tree
// node: {name, props: [{t, v, cls?}], children: [], block}   t: L I D F S N(name: v + cls) C Y + arrays l d f i
export const node = (name, props = [], children = [], block = children.length > 0) => ({ name, props, children, block });
const L = v => ({ t: 'L', v }), I = v => ({ t: 'I', v }), D = v => ({ t: 'D', v }), S = v => ({ t: 'S', v });
const NM = (cls, v) => ({ t: 'N', cls, v });
const arr = (t, v) => ({ t, v: Array.from(v) });
// Properties70 "P" line
const P = (name, t1, t2, flag, ...vals) => node('P', [S(name), S(t1), S(t2), S(flag), ...vals.map(v => (['int', 'enum', 'bool'].includes(t1) ? I(v) : D(v)))]);
const vec3 = (name, v, t1 = name, t2 = '', flag = 'A') => P(name, t1, t2, flag, ...v);

// ---------------------------------------------------------------- ASCII
const num = v => (Number.isInteger(v) ? String(v) : String(+v.toPrecision(12)));
function asciiProps(props) {
  return props.map(p => {
    if (p.t === 'S') return `"${p.v}"`;
    if (p.t === 'N') return `"${p.cls}::${p.v}"`;
    if (p.t === 'C') return p.v ? 'T' : 'F';
    return num(p.v);
  }).join(', ');
}
export function toASCII(tree) {
  const out = ['; FBX 7.4.0 project file', '; Written by tools/checks/mocap/lib/fbxgen.mjs (test fixture)', ''];
  const write = (n, depth) => {
    const tab = '\t'.repeat(depth);
    const a = n.props.find(p => p.t.length === 1 && 'ldfib'.includes(p.t) && Array.isArray(p.v));
    if (a) {
      out.push(`${tab}${n.name}: *${a.v.length} {`, `${tab}\ta: ${a.v.map(num).join(',')}`, `${tab}}`);
      return;
    }
    if (n.name === 'P') {
      const s = n.props.slice(0, 4).map(p => `"${p.v}"`).join(', ');
      const vals = n.props.slice(4).map(p => (p.t === 'S' ? `"${p.v}"` : num(p.v)));
      out.push(`${tab}P: ${s}${vals.length ? ',' + vals.join(',') : ''}`);
      return;
    }
    if (n.name === 'C') {
      const [kind, ...rest] = n.props;
      out.push(`${tab}C: "${kind.v}",${rest.slice(0, 2).map(p => num(p.v)).join(',')}${rest[2] ? `, "${rest[2].v}"` : ''}`);
      return;
    }
    const ps = asciiProps(n.props);
    if (n.block || n.children.length) {
      out.push(`${tab}${n.name}: ${ps} {`);
      for (const c of n.children) write(c, depth + 1);
      out.push(`${tab}}`);
    } else out.push(`${tab}${n.name}: ${ps}`);
  };
  for (const n of tree) { write(n, 0); out.push(''); }
  return out.join('\n');
}

// ---------------------------------------------------------------- binary (FBX 7.4: 32-bit offsets)
class Bytes {
  constructor() { this.chunks = []; this.length = 0; }
  push(u8) { this.chunks.push(u8); this.length += u8.length; }
  u8(v) { this.push(Uint8Array.of(v)); }
  num(type, v) {
    const size = { Y: 2, I: 4, F: 4, D: 8, L: 8 }[type];
    const b = new Uint8Array(size), dv = new DataView(b.buffer);
    if (type === 'Y') dv.setInt16(0, v, true); else if (type === 'I') dv.setInt32(0, v, true);
    else if (type === 'F') dv.setFloat32(0, v, true); else if (type === 'D') dv.setFloat64(0, v, true);
    else dv.setBigInt64(0, BigInt(Math.round(v)), true);
    this.push(b);
  }
  u32(v) { const b = new Uint8Array(4); new DataView(b.buffer).setUint32(0, v, true); this.push(b); }
  bytes() { const out = new Uint8Array(this.length); let o = 0; for (const c of this.chunks) { out.set(c, o); o += c.length; } return out; }
}
const enc = new TextEncoder();
function propBytes(p, compress) {
  const b = new Bytes();
  const t = p.t === 'N' ? 'S' : p.t;
  b.push(enc.encode(t));
  if (t === 'S') {
    const s = p.t === 'N' ? enc.encode(p.v + '\u0000\u0001' + p.cls) : enc.encode(p.v);
    b.u32(s.length); b.push(s);
  } else if (t === 'C') b.u8(p.v ? 1 : 0);
  else if ('YIFDL'.includes(t)) b.num(t, p.v);
  else {
    const size = { f: 4, d: 8, i: 4, l: 8, b: 1 }[t];
    const raw = new Uint8Array(p.v.length * size), dv = new DataView(raw.buffer);
    p.v.forEach((x, k) => {
      if (t === 'f') dv.setFloat32(k * 4, x, true); else if (t === 'd') dv.setFloat64(k * 8, x, true);
      else if (t === 'i') dv.setInt32(k * 4, x, true); else if (t === 'l') dv.setBigInt64(k * 8, BigInt(Math.round(x)), true);
      else raw[k] = x ? 1 : 0;
    });
    const packed = compress && p.v.length > 8 ? new Uint8Array(zlib.deflateSync(raw)) : null;
    b.u32(p.v.length); b.u32(packed ? 1 : 0); b.u32(packed ? packed.length : raw.length); b.push(packed || raw);
  }
  return b.bytes();
}
function nodeBytes(n, start, compress) {
  const name = enc.encode(n.name);
  const props = n.props.map(p => propBytes(p, compress));
  const plen = props.reduce((a, x) => a + x.length, 0);
  let off = start + 13 + name.length + plen;
  const kids = [];
  for (const c of n.children) { const k = nodeBytes(c, off, compress); kids.push(k); off += k.length; }
  const nested = n.children.length > 0 || n.block;          // a nested list (possibly empty) ends with a null record
  if (nested) off += 13;
  const b = new Bytes();
  b.u32(off); b.u32(props.length); b.u32(plen); b.u8(name.length); b.push(name);
  for (const x of props) b.push(x);
  for (const k of kids) b.push(k);
  if (nested) b.push(new Uint8Array(13));
  return b.bytes();
}
export function toBinary(tree, { compress = true, version = 7400 } = {}) {
  const b = new Bytes();
  b.push(enc.encode('Kaydara FBX Binary  ')); b.push(Uint8Array.of(0, 0x1a, 0)); b.u32(version);
  for (const n of tree) b.push(nodeBytes(n, b.length, compress));
  b.push(new Uint8Array(13));                                 // the top-level null record
  // footer: id, padding to 16, zeros, version, zeros, magic
  b.push(Uint8Array.from([0xfa, 0xbc, 0xab, 0x09, 0xd0, 0xc8, 0xd4, 0x66, 0xb1, 0x76, 0xfb, 0x83, 0x1c, 0xf7, 0x26, 0x7e]));
  const pad = 16 - (b.length % 16);
  b.push(new Uint8Array(pad === 0 ? 16 : pad));
  b.u32(0); b.u32(version); b.push(new Uint8Array(120));
  b.push(Uint8Array.from([0xf8, 0x5a, 0x8c, 0x6a, 0xde, 0xf5, 0xd9, 0x7e, 0xec, 0xe9, 0x0c, 0xe3, 0x75, 0x8f, 0x29, 0x0b]));
  return b.bytes();
}

// ---------------------------------------------------------------- scene helpers
const header = () => [
  node('FBXHeaderExtension', [], [node('FBXHeaderVersion', [I(1003)]), node('FBXVersion', [I(7400)])]),
  node('GlobalSettings', [], [node('Version', [I(1000)]), node('Properties70', [], [
    P('UpAxis', 'int', 'Integer', '', 1), P('UnitScaleFactor', 'double', 'Number', '', 1), P('TimeMode', 'enum', '', '', 6)])]),
];
function model(id, name, type, props) {
  return node('Model', [L(id), NM('Model', name), S(type)], [node('Version', [I(232)]), node('Properties70', [], props)]);
}
const curve = (id, times, values) => node('AnimationCurve', [L(id), NM('AnimCurve', ''), S('')], [
  node('Default', [D(0)]), node('KeyVer', [I(4009)]),
  node('KeyTime', [arr('l', times)]), node('KeyValueFloat', [arr('f', values)]),
], true);
const C = (kind, a, b, rel) => node('C', [S(kind), L(a), L(b), ...(rel ? [S(rel)] : [])]);

// ---------------------------------------------------------------- the hand-written arm, as a tree (for binary)
// The same content as fixtures/arm3.fbx: Shoulder > Elbow (PreRotation 0,0,90) > Wrist > WristEnd; 3 frames at 30 fps.
export function armFBX() {
  const t = [0, 1539538600, 3079077200];
  const objects = [
    model(1001, 'Shoulder', 'LimbNode', [vec3('Lcl Translation', [0, 0, 0])]),
    model(1002, 'Elbow', 'LimbNode', [P('RotationActive', 'bool', '', '', 1), vec3('PreRotation', [0, 0, 90], 'Vector3D', 'Vector', ''), vec3('Lcl Translation', [10, 0, 0])]),
    model(1003, 'Wrist', 'LimbNode', [vec3('Lcl Translation', [0, -10, 0])]),
    model(1004, 'WristEnd', 'LimbNode', [vec3('Lcl Translation', [0, -5, 0])]),
    node('AnimationStack', [L(2001), NM('AnimStack', 'Arm test'), S('')], [node('Properties70', [], [P('LocalStop', 'KTime', 'Time', '', 3079077200)])]),
    node('AnimationLayer', [L(2002), NM('AnimLayer', 'BaseLayer'), S('')], [], true),
    node('AnimationCurveNode', [L(3001), NM('AnimCurveNode', 'T'), S('')], [], true),
    node('AnimationCurveNode', [L(3002), NM('AnimCurveNode', 'R'), S('')], [], true),
    node('AnimationCurveNode', [L(3003), NM('AnimCurveNode', 'R'), S('')], [], true),
    curve(4001, t, [0, 0, 1]), curve(4002, t, [0, 0, 2]), curve(4003, t, [0, 0, 3]),
    curve(4004, t, [0, 0, 0]), curve(4005, t, [0, 0, 90]), curve(4006, t, [0, 90, 90]),
    curve(4007, t, [0, 0, 0]), curve(4008, t, [0, 0, 0]), curve(4009, t, [0, 90, 0]),
  ];
  const conns = [C('OO', 1001, 0), C('OO', 1002, 1001), C('OO', 1003, 1002), C('OO', 1004, 1003), C('OO', 2002, 2001),
    C('OO', 3001, 2002), C('OO', 3002, 2002), C('OO', 3003, 2002),
    C('OP', 3001, 1001, 'Lcl Translation'), C('OP', 3002, 1001, 'Lcl Rotation'), C('OP', 3003, 1002, 'Lcl Rotation')];
  [[4001, 3001, 'd|X'], [4002, 3001, 'd|Y'], [4003, 3001, 'd|Z'], [4004, 3002, 'd|X'], [4005, 3002, 'd|Y'], [4006, 3002, 'd|Z'],
    [4007, 3003, 'd|X'], [4008, 3003, 'd|Y'], [4009, 3003, 'd|Z']].forEach(([a, b, r]) => conns.push(C('OP', a, b, r)));
  return [...header(), node('Objects', [], objects), node('Connections', [], conns)];
}

// ---------------------------------------------------------------- the test body
// Euler curves the way exporters write them: continuous. Of the two Euler solutions of a turn, (a, b, c) and
// (a + 180, 180 - b, c + 180), and their 360-degree repeats, the one nearest the previous frame's.
function unroll(prev, e) {
  if (!prev) return e;
  const near = (v, ref) => v + 360 * Math.round((ref - v) / 360);
  const cands = [e, [e[0] + 180, 180 - e[1], e[2] + 180]].map(c => c.map((v, i) => near(v, prev[i])));
  const dist = c => c.reduce((a, v, i) => a + Math.abs(v - prev[i]), 0);
  return dist(cands[0]) <= dist(cands[1]) ? cands[0] : cands[1];
}

// A pseudo-random but fixed joint orient per joint (degrees), so pre-rotations are checked on every joint.
const orient = k => [((k * 37) % 90) - 45, ((k * 53) % 70) - 35, ((k * 71) % 110) - 55];

export function bodyFBX({ names = 'mixamo', fingers = true, prerot = false, rotOrder = 0, armature = null, fps = 30, seconds = 2,
  stacks = null, skinned = false, noAnim = false } = {}) {
  const joints = bodyJoints({ fingers });
  const nm = names === 'plain' ? (k => namer('mixamo')(k).replace(/^mixamorig:/, '')) : namer(names);
  const order = THREE_ORDER[rotOrder];
  let id = 10000;
  const J = joints.map(([key, parent, off]) => ({ key, parent, off: new THREE.Vector3(...off), id: ++id, name: nm(key) }));
  const byKey = Object.fromEntries(J.map(j => [j.key, j]));
  // end bones (Mixamo exports them as joints: HeadTop_End, LeftToe_End, ...)
  for (const [key, off] of Object.entries(ENDS)) {
    if (!byKey[key]) continue;
    const j = { key: key + '_end', parent: key, off: new THREE.Vector3(...off), id: ++id, name: nm(key).replace(/(\d)?$/, '') + '_End' };
    J.push(j); byKey[j.key] = j;
  }
  // G: every joint's rest turn in the file (the product of the joint orients down the chain)
  J.forEach((j, k) => {
    j.pre = prerot ? orient(k + 1) : null;
    j.P = j.pre ? new THREE.Quaternion().setFromEuler(new THREE.Euler(...j.pre.map(a => a * D2R), order)) : new THREE.Quaternion();
    const pG = j.parent ? byKey[j.parent].G : new THREE.Quaternion();
    j.G = pG.clone().multiply(j.P);
    j.T = j.off.clone().applyQuaternion(pG.clone().invert());      // the rest offset in the parent's own frame
  });
  const objects = [], conns = [];
  let parentOfRoot = 0;
  if (armature) {
    const aid = ++id;
    objects.push(model(aid, 'Armature', 'Null', [vec3('Lcl Rotation', armature.rot || [0, 0, 0]), vec3('Lcl Scaling', [armature.scale || 1, armature.scale || 1, armature.scale || 1])]));
    conns.push(C('OO', aid, 0));
    parentOfRoot = aid;
  }
  for (const j of J) {
    const props = [];
    if (rotOrder) props.push(P('RotationOrder', 'enum', '', '', rotOrder));
    if (j.pre) props.push(P('RotationActive', 'bool', '', '', 1), vec3('PreRotation', j.pre, 'Vector3D', 'Vector', ''));
    props.push(vec3('Lcl Translation', j.T.toArray()));
    objects.push(model(j.id, j.name, 'LimbNode', props));
    conns.push(C('OO', j.id, j.parent ? byKey[j.parent].id : parentOfRoot));
  }
  if (skinned) addSkin(objects, conns, J, byKey, () => ++id);
  if (!noAnim) {
    for (const st of stacks || [{ name: names === 'mixamo' ? 'mixamo.com' : 'Take 001', motion: motionAt }]) {
      const sid = ++id, lid = ++id;
      const n = Math.round(seconds * fps) + 1;
      const times = Array.from({ length: n }, (_, i) => Math.round((i * TICKS) / fps));
      objects.push(node('AnimationStack', [L(sid), NM('AnimStack', st.name), S('')], [node('Properties70', [], [P('LocalStop', 'KTime', 'Time', '', times[n - 1])])]));
      objects.push(node('AnimationLayer', [L(lid), NM('AnimLayer', 'BaseLayer'), S('')], [], true));
      conns.push(C('OO', lid, sid));
      const frames = Array.from({ length: n }, (_, i) => st.motion(i / fps));
      const addCurves = (target, attr, rel, xyz) => {
        const cn = ++id;
        objects.push(node('AnimationCurveNode', [L(cn), NM('AnimCurveNode', attr), S('')], [], true));
        conns.push(C('OO', cn, lid), C('OP', cn, target, rel));
        ['X', 'Y', 'Z'].forEach((ax, c) => {
          const cid = ++id;
          objects.push(curve(cid, times, xyz.map(v => v[c])));
          conns.push(C('OP', cid, cn, 'd|' + ax));
        });
      };
      for (const j of J) {
        if (j.key.endsWith('_end')) continue;
        // the file's own turn: R = G^-1 Q G (Q: the BVH motion's local turn), so world places match the BVH exactly
        let prev = null;
        const eul = frames.map(m => {
          const Q = m.q[j.key] || new THREE.Quaternion();
          const R = j.G.clone().invert().multiply(Q).multiply(j.G);
          const e = new THREE.Euler().setFromQuaternion(R, order);
          return (prev = unroll(prev, [e.x / D2R, e.y / D2R, e.z / D2R]));
        });
        addCurves(j.id, 'R', 'Lcl Rotation', eul);
        if (!j.parent) addCurves(j.id, 'T', 'Lcl Translation', frames.map(m => m.root));
      }
    }
  }
  return [...header(), node('Objects', [], objects), node('Connections', [], conns)];
}

// A small skinned mesh on the hips and the spine (a few triangles), with its bind pose - like a "with skin" download.
function addSkin(objects, conns, J, byKey, nextId) {
  const gid = nextId(), mid = nextId(), skin = nextId(), pose = nextId();
  const verts = [-10, 90, 5, 10, 90, 5, 0, 115, 5, -10, 90, -5, 10, 90, -5, 0, 115, -5];
  objects.push(node('Geometry', [L(gid), NM('Geometry', 'Body'), S('Mesh')], [
    node('Vertices', [arr('d', verts)]), node('PolygonVertexIndex', [arr('i', [0, 1, -3, 3, 5, -5])]), node('GeometryVersion', [I(124)]),
  ]));
  objects.push(model(mid, 'Body', 'Mesh', [vec3('Lcl Translation', [0, 0, 0])]));
  objects.push(node('Deformer', [L(skin), NM('Deformer', 'Skin'), S('Skin')], [node('Version', [I(101)]), node('Link_DeformAcuracy', [D(50)])]));
  conns.push(C('OO', mid, 0), C('OO', gid, mid), C('OO', skin, gid));
  const world = j => { const m = new THREE.Matrix4(); let p = new THREE.Vector3(); for (let x = j; x; x = x.parent ? byKey[x.parent] : null) p.add(x.off); return m.compose(p, j.G, new THREE.Vector3(1, 1, 1)); };
  for (const [key, idx, w] of [['hips', [0, 1, 3, 4], [1, 1, 1, 1]], ['spine1', [2, 5], [1, 1]]]) {
    const j = byKey[key], cl = nextId();
    const link = world(j);
    objects.push(node('Deformer', [L(cl), NM('SubDeformer', 'Cluster ' + j.name), S('Cluster')], [
      node('Version', [I(100)]), node('Indexes', [arr('i', idx)]), node('Weights', [arr('d', w)]),
      node('Transform', [arr('d', link.clone().invert().elements)]), node('TransformLink', [arr('d', link.elements)]),
    ]));
    conns.push(C('OO', cl, skin), C('OO', j.id, cl));
  }
  objects.push(node('Pose', [L(pose), NM('Pose', 'BIND_POSES'), S('BindPose')], [
    node('Type', [S('BindPose')]), node('Version', [I(100)]), node('NbPoseNodes', [I(1)]),
    node('PoseNode', [], [node('Node', [L(mid)]), node('Matrix', [arr('d', new THREE.Matrix4().elements)])]),
  ]));
}
