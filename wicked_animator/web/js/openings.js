// Automatic openings: the vagina, anus and mouth open by themselves when a penis, finger or tongue comes close
// or goes in, sized by what goes in. Each sim can switch it off (all holes or one by one) - e.g. for a
// "kissing the tip" animation where the mouth should stay closed.
import * as THREE from 'three';
import { distToSegment } from './motion.js';

export const HOLES = {
  vagina: { label: 'Vagina', hint: 'On the female body with WickedWhims\' animated vagina' },
  anus: { label: 'Anus' },
  mouth: { label: 'Mouth', hint: 'The jaw opens around what goes in' },
};

// What can go in, with its thickness (radius, metres).
const PENETRATORS = [
  { kind: 'penis', chain: ['b__Penis_Base', 'b__Penis_Base01', 'b__Penis_Mid', 'b__Penis_Mid01', 'b__Penis_Tip'], radius: 0.017, needs: 'penis' },
  { kind: 'finger', chain: ['b__L_Index0__', 'b__L_Index1__', 'b__L_Index2__'], radius: 0.008 },
  { kind: 'finger', chain: ['b__R_Index0__', 'b__R_Index1__', 'b__R_Index2__'], radius: 0.008 },
  { kind: 'finger', chain: ['b__L_Mid0__', 'b__L_Mid1__', 'b__L_Mid2__'], radius: 0.008 },
  { kind: 'finger', chain: ['b__R_Mid0__', 'b__R_Mid1__', 'b__R_Mid2__'], radius: 0.008 },
  { kind: 'tongue', chain: ['b__Tounge__1', 'b__Tounge__2', 'b__Tounge__3'], radius: 0.009 },
];

const _a = new THREE.Vector3(), _b = new THREE.Vector3();
const smooth = (e0, e1, x) => { const t = THREE.MathUtils.clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); };

function chainPoints(v, names) {
  const pts = names.map(n => v.byName[n] ? v.worldPos(n) : null).filter(Boolean);
  if (pts.length >= 2) {        // the last bone sits at the start of the fingertip / tip - reach a bit past it
    const n = pts.length, ext = pts[n - 1].clone().sub(pts[n - 2]).multiplyScalar(0.7).add(pts[n - 1]);
    pts.push(ext);
  }
  return pts;
}

// Where each hole is and which way is "in" (world space), from the body's current pose.
function holeFrames(v) {
  const out = {};
  const pel = v.bone('b__Pelvis__');
  const q = pel.getWorldQuaternion(new THREE.Quaternion());
  const up = new THREE.Vector3(-1, 0, 0).applyQuaternion(q), fwd = new THREE.Vector3(0, 1, 0).applyQuaternion(q);
  if (v.hasVagina) {
    const c = v.skinPointWorld(['b__Penis_L_Testicle', 'b__Penis_R_Testicle', 'b__Penis_Testicles', 'b__Up_Vagina__', 'b__Low_Vagina__']);
    if (c) out.vagina = { at: c, into: up.clone().multiplyScalar(0.8).addScaledVector(fwd, -0.6).normalize() };
  }
  if (v.byName.b__Up_Anus) {
    const c = v.skinPointWorld(['b__Anus', 'b__L_Anus__', 'b__R_Anus__', 'b__Up_Anus', 'b__Low_Anus']) ||
      v.worldPos('b__Up_Anus').add(v.worldPos('b__Low_Anus')).multiplyScalar(0.5);
    out.anus = { at: c, into: up.clone().multiplyScalar(0.7).addScaledVector(fwd, 0.7).normalize() };
  }
  const lips = v.worldPos('b__UpLip__').add(v.worldPos('b__LoLip__')).multiplyScalar(0.5);
  const hq = v.bone('b__Head__').getWorldQuaternion(new THREE.Quaternion());
  out.mouth = { at: lips, into: v.worldPos('b__Head__').sub(lips).normalize(), down: new THREE.Vector3(-1, 0, 0).applyQuaternion(hq) };
  return out;
}

// For every sim: how open each hole should be (0..1), how deep something is in (m), what it is (`by`) and whose
// it is (`from`, the sim id).
// entries: [{sim, v}] with the current pose applied (before openings).
export function measure(entries) {
  const frames = entries.map(e => holeFrames(e.v));
  const pens = [];
  for (const e of entries) {
    for (const p of PENETRATORS) {
      if (p.needs === 'penis' && !e.v.hasPenis) continue;
      if (!e.v.byName[p.chain[0]]) continue;
      const radius = p.kind === 'penis' && !e.v.erect ? 0.012 : p.radius;
      pens.push({ owner: e, kind: p.kind, pts: chainPoints(e.v, p.chain), radius });
    }
  }
  return entries.map((e, i) => {
    const res = {};
    for (const [hole, f] of Object.entries(frames[i])) {
      let best = { open: 0, depth: 0, by: null };
      for (const pen of pens) {
        if (pen.owner === e && (hole === 'mouth' ? pen.kind === 'tongue' : pen.kind === 'penis')) continue;
        let r = Infinity, depth = 0;
        const near = new THREE.Vector3();
        for (let k = 0; k + 1 < pen.pts.length; k++) {
          const c = closestOnSegment(f.at, pen.pts[k], pen.pts[k + 1]);
          const d = c.distanceTo(f.at);
          if (d < r) { r = d; near.copy(c); }
        }
        const mouth = hole === 'mouth';
        const reach = mouth ? 0.045 : 0.03;
        for (const p of pen.pts) {
          _a.copy(p).sub(f.at);
          const along = _a.dot(f.into);
          const side = _b.copy(_a).addScaledVector(f.into, -along).length();
          if (along > 0 && side < reach) depth = Math.max(depth, along);
        }
        // opens from 5 cm away, fully at contact; anything inside keeps it open
        let open = smooth(0.05, 0.008, r);
        if (depth > 0.004 && (r < reach || depth > 0.01)) open = 1;
        open *= THREE.MathUtils.clamp(pen.radius / 0.017, 0.35, 1.3);
        // the mouth opens as wide as it has to: the lower lip must clear the bottom of whatever is in it
        const need = mouth && f.down && open > 0.05 ? Math.max(0, near.clone().sub(f.at).dot(f.down) + pen.radius + 0.004) : 0;
        if (open > best.open || (open === best.open && need > (best.need || 0))) best = { open, depth, by: pen.kind, need, from: pen.owner.sim && pen.owner.sim.id };
      }
      res[hole] = best;
    }
    return res;
  });
}

// Push the hole's bones open by `amount` (0..1+) - local offsets in the pelvis frame (up = -x, forward = +y, left = -z).
function closestOnSegment(p, a, b) {
  const ab = b.clone().sub(a);
  const t = THREE.MathUtils.clamp(p.clone().sub(a).dot(ab) / Math.max(1e-9, ab.lengthSq()), 0, 1);
  return a.clone().addScaledVector(ab, t);
}

export function applyOpen(v, hole, amount, info = null) {
  if (amount <= 0.001) return;
  const w = amount;
  const move = (name, x, y, z) => { const b = v.byName[name]; if (b) { b.position.x += x; b.position.y += y; b.position.z += z; } };
  if (hole === 'vagina') {
    move('b__Penis_L_Testicle', 0, 0, -0.0075 * w);
    move('b__Penis_R_Testicle', 0, 0, 0.0075 * w);
    move('b__Up_Vagina__', -0.004 * w, 0, 0);
    move('b__Low_Vagina__', 0.004 * w, 0, 0);
  } else if (hole === 'anus') {
    move('b__L_Anus__', 0, 0, -0.0065 * w);
    move('b__R_Anus__', 0, 0, 0.0065 * w);
    move('b__Up_Anus', -0.004 * w, -0.004 * w, 0);
    move('b__Low_Anus', 0.004 * w, 0.004 * w, 0);
  } else if (hole === 'mouth') {
    // the whole mouth forms around what's inside: the jaw drops, both lips push forward and wrap (in creator
    // clips the upper lip comes a little down and forward over the teeth, it does not lift), the corners pull in
    // to a round "O" and the cheeks draw in a little. The corners also come down with the jaw (face.followJaw).
    // Face bones: x up, y forward, z the sim's left - so "inward" is -z on the left side and +z on the right.
    const jaw = v.byName.b__Jaw__;
    // lower lip is about 8.5 cm from the jaw hinge: open just enough for it to pass under what's inside
    const needDeg = info && info.need ? THREE.MathUtils.radToDeg(Math.atan2(info.need, 0.085)) : 0;
    const deg = Math.min(38, Math.max(17 * w, needDeg));
    if (jaw) jaw.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, -1), THREE.MathUtils.degToRad(deg)));
    move('b__UpLip__', -0.0015 * w, 0.004 * w, 0);
    move('b__L_UpLip__', -0.001 * w, 0.003 * w, -0.0015 * w);
    move('b__R_UpLip__', -0.001 * w, 0.003 * w, 0.0015 * w);
    move('b__LoLip__', -0.001 * w, 0.004 * w, 0);
    move('b__L_LoLip__', -0.0005 * w, 0.003 * w, -0.0015 * w);
    move('b__R_LoLip__', -0.0005 * w, 0.003 * w, 0.0015 * w);
    move('b__L_Mouth__', 0, 0.0025 * w, -0.0045 * w);
    move('b__R_Mouth__', 0, 0.0025 * w, 0.0045 * w);
    move('b__L_Cheek__', 0, 0, -0.0015 * w);
    move('b__R_Cheek__', 0, 0, 0.0015 * w);
    // the lips cling to what is in the mouth (info.pull, pipeline.lipPull): pulled forward along it on the way out,
    // tucked in a little on the way in; the cheeks hollow while it pulls
    const pull = (info && info.pull) || 0;
    if (pull) {
      const f = (pull > 0 ? 0.007 : 0.0035) * pull * Math.min(1, w);
      move('b__UpLip__', 0, f, 0);
      move('b__LoLip__', 0, 1.1 * f, 0);
      move('b__L_UpLip__', 0, 0.75 * f, 0);
      move('b__R_UpLip__', 0, 0.75 * f, 0);
      move('b__L_LoLip__', 0, 0.8 * f, 0);
      move('b__R_LoLip__', 0, 0.8 * f, 0);
      move('b__L_Mouth__', 0, 0.4 * f, 0);
      move('b__R_Mouth__', 0, 0.4 * f, 0);
      if (pull > 0) { move('b__L_Cheek__', 0, 0, -0.0025 * pull); move('b__R_Cheek__', 0, 0, 0.0025 * pull); }
    }
  }
}
