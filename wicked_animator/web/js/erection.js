// A growing erection: sim.body.grow = {from, to} (frames). Small and hanging until `from`, then it grows and rises
// until `to`, hard from there on. The growth is posed on the penis bones (the base scaled up from GROW_SCALE and turned
// up from hanging GROW_DROOP radians, the middle bending a little), so it goes into the exported animation too: the
// bake adds a scale track for the base (exporter: scale channel). No `grow`: body.erect as before (hard or soft).
import * as THREE from 'three';

const GROW_SCALE = 0.68, GROW_DROOP = 1.25, GROW_BEND = 0.3;
const _q = new THREE.Quaternion(), _z = new THREE.Vector3(0, 0, 1);

export const hasGrow = b => !!(b && b.grow && b.grow.to > b.grow.from);

// 0 (soft) .. 1 (hard) at a frame; eased in and out
export function erectAmount(b, frame) {
  if (!hasGrow(b)) return b && b.erect === false ? 0 : 1;
  const t = Math.min(1, Math.max(0, (frame - b.grow.from) / (b.grow.to - b.grow.from)));
  return t * t * (3 - 2 * t);
}

// After the pose is on the bones: which penis shows, and how far grown it is. The base's scale is set every frame (the
// pose reset leaves scale alone).
export function applyErection(v, b, frame) {
  const base = v.bone('b__Penis_Base');
  if (base) base.scale.set(1, 1, 1);
  if (!hasGrow(b)) { v.setErect(b.erect); return; }
  v.setErect(true);                    // before `from` too: small and hanging, the same in the game
  const a = erectAmount(b, frame);
  if (a >= 1 || !base) return;
  base.scale.setScalar(GROW_SCALE + (1 - GROW_SCALE) * a);
  base.quaternion.multiply(_q.setFromAxisAngle(_z, -GROW_DROOP * (1 - a)));      // -Z turns it down
  const mid = v.bone('b__Penis_Mid');
  if (mid) mid.quaternion.multiply(_q.setFromAxisAngle(_z, -GROW_BEND * (1 - a)));
}
