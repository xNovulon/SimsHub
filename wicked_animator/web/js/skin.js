// The skin of a sim as it is posed right now: the nearest skin point to a place (with its outward normal and the
// bone it moves with), and which bone a hold hangs on. Free functions on a Sim view, so sim.js stays as it is.
import * as THREE from 'three';
import { controllableIndex, FACE_SET, POSABLE_SET } from './bones.js';

const _m = new THREE.Matrix4(), _n = new THREE.Matrix3();

// The skin point nearest to `pointWorld` within `maxDist` (metres) on the visible meshes of view `v`:
// { point, normal, boneIndex, dist } in world space, or null. The meshes are skinned on the CPU with each bone's
// matrixWorld x boneInverse (what the GPU draws); about 1-3 ms for a body. The normal is the bind normal turned with
// the vertex's strongest bone; boneIndex is that bone.
export function nearestSkin(v, pointWorld, maxDist = 0.08, { skip = ['penis_hard', 'tongue'] } = {}) {
  if (!v || !pointWorld) return null;
  v.group.updateMatrixWorld(true);
  const px = pointWorld.x, py = pointWorld.y, pz = pointWorld.z;
  let best = null, bd = maxDist * maxDist;
  for (const mesh of v.meshes) {
    if (!mesh.visible || skip.includes(mesh.userData.role)) continue;
    const g = mesh.geometry, pos = g.attributes.position, si = g.attributes.skinIndex, sw = g.attributes.skinWeight;
    const sk = mesh.skeleton;
    // one matrix per bone: mesh world x bindMatrixInverse x bone world x boneInverse x bindMatrix
    const mats = new Map();
    const matOf = b => {
      let m = mats.get(b);
      if (!m) {
        m = new THREE.Matrix4().multiplyMatrices(sk.bones[b].matrixWorld, sk.boneInverses[b]);
        m.premultiply(mesh.bindMatrixInverse).premultiply(mesh.matrixWorld).multiply(mesh.bindMatrix);
        mats.set(b, m.elements);
      }
      return mats.get(b);
    };
    const P = pos.array, I = si.array, W = sw.array;
    for (let i = 0; i < pos.count; i++) {
      const x = P[i * 3], y = P[i * 3 + 1], z = P[i * 3 + 2];
      let wx = 0, wy = 0, wz = 0;
      for (let k = 0; k < 4; k++) {
        const w = W[i * 4 + k];
        if (!w) continue;
        const e = matOf(I[i * 4 + k]);
        wx += w * (e[0] * x + e[4] * y + e[8] * z + e[12]);
        wy += w * (e[1] * x + e[5] * y + e[9] * z + e[13]);
        wz += w * (e[2] * x + e[6] * y + e[10] * z + e[14]);
      }
      const d = (wx - px) ** 2 + (wy - py) ** 2 + (wz - pz) ** 2;
      if (d < bd) { bd = d; best = { mesh, i, x: wx, y: wy, z: wz }; }
    }
  }
  if (!best) return null;
  const { mesh, i } = best, g = mesh.geometry, si = g.attributes.skinIndex, sw = g.attributes.skinWeight;
  let bone = si.getComponent(i, 0), bw = -1;
  for (let k = 0; k < 4; k++) if (sw.getComponent(i, k) > bw) { bw = sw.getComponent(i, k); bone = si.getComponent(i, k); }
  const normal = new THREE.Vector3(0, 1, 0);
  if (g.attributes.normal) {
    _m.multiplyMatrices(mesh.skeleton.bones[bone].matrixWorld, mesh.skeleton.boneInverses[bone]).premultiply(mesh.matrixWorld);
    normal.fromBufferAttribute(g.attributes.normal, i).applyMatrix3(_n.getNormalMatrix(_m)).normalize();
  }
  return { point: new THREE.Vector3(best.x, best.y, best.z), normal, boneIndex: bone, dist: Math.sqrt(bd) };
}

// The bone a hold on skin that moves with rig bone `boneIndex` hangs on: the posable bone that carries it (slot,
// twist, breast and butt bones hand over to the body part they sit on), never a face or physics bone (those hand
// over to the head / the chest / the hips).
export function anchorFor(v, boneIndex) {
  let k = controllableIndex(v.rig, boneIndex, 'body');
  let name = v.bones[k] && v.bones[k].name;
  // the jaw and the tongue are face bones: a hand on the face holds the head
  while (name && (FACE_SET.has(name) || !POSABLE_SET.has(name))) {
    const p = v.rig.bones[k].parent;
    if (p < 0) { name = 'b__Pelvis__'; break; }
    k = p; name = v.bones[k].name;
  }
  return name || 'b__Pelvis__';
}
