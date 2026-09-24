// A prop's movement for the game (spec_bodies 10.2): one position and turn per frame of the prop rig's
// transformBone, in the animation's space - the space the sims' clips play in (their b__ROOT__ at the origin, like
// the object WickedWhims plays them on). The exporter (backend/exporter.prop_resources) writes it as the prop's own
// clip. Pure maths, no three.js: tools/checks/r3-6 runs it in Node.
//
//   boneWorld(rig, tracks, name, frame) -> {pos, quat}   a bone of a baked sim at a frame (forward kinematics over the
//                                                        baked tracks; the rig's rest place where a bone has none)
//   propTrack(prop, {rig, actors, sims, frames}) -> {t: [[x, y, z]], r: [[x, y, z, w]]} or null
//     prop: {hold: {sim, bone, offset: {pos, quat}}} held in a hand (it follows that bone)
//           {at: {pos, quat}}                        standing still in the scene

export const qmul = (a, b) => [
  a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
  a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
  a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
  a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2]];

export function qrot(q, v) {
  const [x, y, z, w] = q;
  const cx = y * v[2] - z * v[1] + w * v[0], cy = z * v[0] - x * v[2] + w * v[1], cz = x * v[1] - y * v[0] + w * v[2];
  return [v[0] + 2 * (y * cz - z * cy), v[1] + 2 * (z * cx - x * cz), v[2] + 2 * (x * cy - y * cx)];
}

export function qnorm(q) {
  const n = Math.hypot(q[0], q[1], q[2], q[3]) || 1;
  return [q[0] / n, q[1] / n, q[2] / n, q[3] / n];
}

const at = (list, frame) => (list && list.length ? list[Math.min(list.length - 1, Math.max(0, frame))] : null);

// {name: index} and the chain from the root down to a bone, cached per rig
const _chains = new WeakMap();
function chainOf(rig, name) {
  let c = _chains.get(rig);
  if (!c) { c = { index: new Map(rig.bones.map((b, i) => [b.name, i])), chains: new Map() }; _chains.set(rig, c); }
  if (c.chains.has(name)) return c.chains.get(name);
  const i0 = c.index.get(name);
  if (i0 === undefined) { c.chains.set(name, null); return null; }
  const chain = [];
  for (let i = i0; i >= 0; i = rig.bones[i].parent) chain.unshift(rig.bones[i]);
  c.chains.set(name, chain);
  return chain;
}

// A bone's place and turn in the animation's space at a frame. tracks: one baked sim's {bone: {t, r}}.
export function boneWorld(rig, tracks, name, frame) {
  const chain = chainOf(rig, name);
  if (!chain) return null;
  let pos = [0, 0, 0], quat = [0, 0, 0, 1], scale = [1, 1, 1];
  for (const b of chain) {
    const tr = (tracks && tracks[b.name]) || {};
    const lp = at(tr.t, frame) || b.pos, lq = at(tr.r, frame) || b.rot, ls = b.scale || [1, 1, 1];
    const off = qrot(quat, [lp[0] * scale[0], lp[1] * scale[1], lp[2] * scale[2]]);
    pos = [pos[0] + off[0], pos[1] + off[1], pos[2] + off[2]];
    quat = qnorm(qmul(quat, lq));
    scale = [scale[0] * ls[0], scale[1] * ls[1], scale[2] * ls[2]];
  }
  return { pos, quat };
}

// Every frame of a prop. sims: the project's sims (to find the holder's index in `actors`).
export function propTrack(prop, { rig, actors, sims, frames }) {
  const n = Math.max(1, frames | 0), t = [], r = [];
  const round = (v, k = 1e5) => v.map(x => Math.round(x * k) / k);
  if (prop && prop.hold && prop.hold.sim) {
    const i = (sims || []).findIndex(s => s.id === prop.hold.sim);
    const tracks = i >= 0 && actors && actors[i] ? actors[i].tracks : null;
    if (!tracks || !chainOf(rig, prop.hold.bone)) return null;
    const off = prop.hold.offset || {}, op = off.pos || [0, 0, 0], oq = qnorm(off.quat || [0, 0, 0, 1]);
    for (let f = 0; f < n; f++) {
      const w = boneWorld(rig, tracks, prop.hold.bone, f);
      const p = qrot(w.quat, op);
      t.push(round([w.pos[0] + p[0], w.pos[1] + p[1], w.pos[2] + p[2]]));
      r.push(round(qnorm(qmul(w.quat, oq)), 1e6));
    }
    return { t, r };
  }
  const a = (prop && prop.at) || {};
  const p = round(a.pos || [0, 0, 0]), q = round(qnorm(a.quat || [0, 0, 0, 1]), 1e6);
  for (let f = 0; f < n; f++) { t.push(p); r.push(q); }
  return { t, r };
}
