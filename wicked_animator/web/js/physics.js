// Automatic physics: breasts, butt, penis and balls bounce by themselves from how the body moves.
// Each part is a damped spring chasing where the animation puts it (frame-rate independent, 240 steps a second).
// For a looping animation it simulates three loops and keeps the last, then removes the tiny leftover drift,
// so the jiggle joins up perfectly at the loop point.
import * as THREE from 'three';
import { $t } from './i18n.js';

export const PARTS = {
  breasts: { label: $t('physics.breasts'), bones: ['b__CAS_L_Breast__', 'b__CAS_R_Breast__'], hz: 3.0, damping: 0.22, max: 0.035, gain: 1.15, needs: 'breasts' },
  butt: { label: $t('physics.butt'), bones: ['b__L_Butt__', 'b__R_Butt__'], hz: 3.4, damping: 0.28, max: 0.028, gain: 1.0 },
  penis: { label: $t('physics.penis'), bones: ['b__Penis_Tip'], swing: 'b__Penis_Base', hz: 2.6, damping: 0.3, max: 0.08, gain: 1.0, needs: 'penis' },
  balls: { label: $t('physics.balls'), bones: ['b__Penis_Testicles'], hz: 2.8, damping: 0.25, max: 0.025, gain: 1.0, needs: 'balls' },
};

// The sliders go up to 300%. Up to 200% everything bakes exactly as it always did; above that the springs also swing
// further (their reach grows with the setting), so the top setting jiggles as much as creators bake it (breast travel
// about 49 mm, butt about 80 mm - bone_stats.md, blender_workflow.md 5.9).
export const PHYSICS_MAX = 3;
const reach = (part, setting) => (setting > 2 ? part.max * (setting - 1) : part.max);

export function defaultPhysics(frame) {
  return { on: true, breasts: frame === 'ym' ? 0.35 : 1, butt: 1, penis: 1, balls: frame === 'ym' ? 1 : 0 };
}

export function partsFor(v, settings) {
  const out = [];
  if (!settings || settings.on === false) return out;
  for (const [key, p] of Object.entries(PARTS)) {
    const amt = settings[key] ?? 0;
    if (amt <= 0) continue;
    if (p.needs === 'penis' && !v.hasPenis) continue;
    if (p.needs === 'balls' && !(v.hasPenis)) continue;
    if (!p.bones.every(b => v.byName[b])) continue;
    out.push({ key, ...p, amount: amt * (key === 'penis' && v.erect ? 0.35 : 1), max: reach(p, amt) });
  }
  return out;
}

// samples[k] = {bone: {pos: Vector3 (world), parentQ: Quaternion (world), base?: Vector3}} for frames 0..n-1.
// Returns {bone: Float32Array(n*3)} of offsets in the parent's local space (or swing axis-angle for penis).
export function simulate(parts, samples, fps, loop) {
  const n = samples.length;
  const out = {};
  if (!n) return out;
  const sub = 8, dt = 1 / (fps * sub);
  for (const part of parts) {
    const w = 2 * Math.PI * part.hz, z = part.damping;
    for (const bone of part.bones) {
      const x = samples[0][bone].pos.clone(), vel = new THREE.Vector3();
      const res = new Array(n);
      const passes = loop ? 3 : 1;
      const tgt = new THREE.Vector3(), acc = new THREE.Vector3();
      for (let pass = 0; pass < passes; pass++) {
        for (let k = 0; k < n; k++) {
          const a = samples[k][bone].pos, b = samples[(k + 1) % n][bone].pos;
          const last = !loop && k === n - 1;
          if (pass === passes - 1) res[k] = x.clone().sub(a);
          for (let s = 0; s < sub; s++) {
            tgt.copy(a).lerp(last ? a : b, s / sub);
            acc.copy(x).sub(tgt).multiplyScalar(-w * w).addScaledVector(vel, -2 * z * w);
            vel.addScaledVector(acc, dt);
            x.addScaledVector(vel, dt);
          }
        }
      }
      // loop seam: spread the leftover over the loop so frame n-1 flows into frame 0
      if (loop) {
        const end = x.clone().sub(samples[0][bone].pos).sub(res[0]);
        for (let k = 0; k < n; k++) res[k].addScaledVector(end, -k / n);
      }
      const arr = new Float32Array(n * 3);
      const inv = new THREE.Quaternion();
      for (let k = 0; k < n; k++) {
        const off = res[k].multiplyScalar(part.gain * part.amount);
        const len = off.length();
        if (len > part.max) off.multiplyScalar(part.max / len);
        if (part.swing) {
          // store the world offset; the pipeline turns it into a swing of the root bone
          arr[k * 3] = off.x; arr[k * 3 + 1] = off.y; arr[k * 3 + 2] = off.z;
        } else {
          inv.copy(samples[k][bone].parentQ).invert();
          off.applyQuaternion(inv);
          arr[k * 3] = off.x; arr[k * 3 + 1] = off.y; arr[k * 3 + 2] = off.z;
        }
      }
      out[bone] = { arr, swing: part.swing || null };
    }
  }
  return out;
}

// Apply one frame of the simulated offsets to a view (frame may be fractional).
export function applyFrame(v, sim, frame, n, loop) {
  if (!sim || !n) return;
  const k0 = Math.floor(frame) % n, k1 = loop ? (k0 + 1) % n : Math.min(n - 1, k0 + 1), t = frame - Math.floor(frame);
  for (const [bone, { arr, swing }] of Object.entries(sim)) {
    // simulated for another length (the animation was just made longer or shorter and the new simulation is
    // still on its way): show no jiggle rather than read past the end
    if (arr.length !== n * 3) continue;
    const ox = arr[k0 * 3] + (arr[k1 * 3] - arr[k0 * 3]) * t;
    const oy = arr[k0 * 3 + 1] + (arr[k1 * 3 + 1] - arr[k0 * 3 + 1]) * t;
    const oz = arr[k0 * 3 + 2] + (arr[k1 * 3 + 2] - arr[k0 * 3 + 2]) * t;
    if (!Number.isFinite(ox) || !Number.isFinite(oy) || !Number.isFinite(oz)) continue;
    if (swing) {
      const root = v.byName[swing], tip = v.byName[bone];
      if (!root || !tip) continue;
      const R = v.worldPos(swing), T = v.worldPos(bone);
      const from = T.clone().sub(R), to = from.clone().add(new THREE.Vector3(ox, oy, oz));
      if (from.lengthSq() < 1e-8 || to.lengthSq() < 1e-8) continue;
      const dq = new THREE.Quaternion().setFromUnitVectors(from.normalize(), to.normalize());
      const wq = root.getWorldQuaternion(new THREE.Quaternion());
      const pq = root.parent.getWorldQuaternion(new THREE.Quaternion());
      root.quaternion.copy(pq.invert().multiply(dq.multiply(wq)));
    } else {
      const b = v.byName[bone];
      if (b) { b.position.x += ox; b.position.y += oy; b.position.z += oz; }
    }
  }
}
