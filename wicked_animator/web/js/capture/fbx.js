// FBX motion files for "Import a motion file": three.js's own FBXLoader (examples/jsm, loaded like the app's other
// three.js add-ons) reads the file - binary or ASCII, FBX 7.x - into a scene with its skeleton and one AnimationClip
// per animation stack. Every joint's WORLD place and turn is then sampled per frame, at the file's own frame rate,
// and handed over in the same shape parseBVH gives (joints, frames, frameTime + the sampled poses), so the rest of
// the way is exactly the BVH one: capture/bvh.js analyze -> buildTake -> solveFile. Turns are stored relative to the
// file's default pose (its rest), the way a BVH's rest pose has every turn at zero.
//
//   readFBX(arrayBuffer) -> { stacks: [{name, seconds, fps, frames}], joints, meshes, motion(i) -> bvh-like }
//   isFBX(name, headBytes) -> true for .fbx files (binary or ASCII)
// Models, materials and textures in the file are left out (textures are never fetched).
import * as THREE from 'three';
import { BVHError } from './bvh.js';

const TICKS = 46186158000;                                   // FBX time units per second
const MAX_SAMPLE_FPS = 60;                                    // denser files are sampled at 60 (the app works at 30)
const MAX_FRAMES = 60 * 60 * 10;                              // ten minutes at 60 fps
const EMPTY_PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';
const NICE = [12, 15, 24, 25, 30, 48, 50, 60, 90, 100, 120, 240];

export const isFBX = (name, head = '') => /\.fbx$/i.test(String(name || '')) || /^Kaydara FBX Binary/.test(head) || /^; FBX/.test(head);

let mod = null;
async function loaderClass() {
  mod = mod || (await import('three/addons/loaders/FBXLoader.js'));
  return mod.FBXLoader;
}

// the file's frame rate from its keys: the most common gap between key times (sparse keys: 30)
function keyRate(clip) {
  const count = new Map();
  for (const t of clip.tracks) {
    for (let i = 1; i < t.times.length; i++) {
      const d = Math.round((t.times[i] - t.times[i - 1]) * 1e5) / 1e5;
      if (d > 0) count.set(d, (count.get(d) || 0) + 1);
    }
  }
  let best = 0, n = 0;
  for (const [d, c] of count) if (c > n || (c === n && d < best)) { best = d; n = c; }
  if (!best) return 30;
  const fps = 1 / best;
  const nice = NICE.find(r => Math.abs(fps - r) / r < 0.01);
  if (nice) return nice;
  return fps >= 12 && fps <= 240 ? Math.round(fps * 100) / 100 : 30;
}

// readFBX(buffer) -> the parts of the file the import needs (throws BVHError with a plain message)
export async function readFBX(buffer) {
  const FBXLoader = await loaderClass();
  const manager = new THREE.LoadingManager();
  manager.setURLModifier(() => EMPTY_PNG);                    // a texture in the file is never fetched
  let scene;
  try {
    try {
      scene = new FBXLoader(manager).parse(buffer, '');
    } catch (e) {
      // FBXLoader tells text FBX from binary by sampling a few characters at fixed places, and a valid text file can
      // fail that by chance; blank lines in front (the text reader skips them) move the sampled places
      const head = new TextDecoder().decode(new Uint8Array(buffer, 0, Math.min(buffer.byteLength, 4096)));
      if (!/Unknown format/.test(String(e && e.message)) || !/FBXHeaderExtension|^\s*; FBX/.test(head)) throw e;
      const text = new TextDecoder().decode(new Uint8Array(buffer));
      for (let k = 1; k <= 12 && !scene; k++) {
        try { scene = new FBXLoader(manager).parse(new TextEncoder().encode('\n'.repeat(k) + text).buffer, ''); } catch (e2) { if (!/Unknown format/.test(String(e2 && e2.message))) throw e2; }
      }
      if (!scene) throw e;
    }
  } catch (e) {
    const m = String((e && e.message) || e);
    const v = /FileVersion: (\d+)/.exec(m);
    if (v) throw new BVHError(`This FBX file is version ${(v[1] / 1000).toFixed(1)}, which is too old to read. Export it again as FBX 2010 or newer (version 7), or as BVH.`);
    if (/Unknown format|Cannot find the version/i.test(m)) throw new BVHError("This file doesn't look like an FBX file (neither binary nor text FBX).");
    throw new BVHError(`This FBX file could not be read (${m.replace(/^THREE\.FBXLoader:\s*/, '').slice(0, 120)}). Export it again, or export BVH instead.`);
  }
  scene.updateMatrixWorld(true);
  scene.traverse(o => { o.userData.__rest = { p: o.position.clone(), q: o.quaternion.clone(), s: o.scale.clone() }; });
  // the skeleton: every bone (LimbNode); a file without bones: its plain nodes (Null) - never meshes, cameras, lights
  let nodes = [];
  scene.traverse(o => { if (o.isBone) nodes.push(o); });
  if (!nodes.length) scene.traverse(o => { if (o !== scene && !o.isMesh && !o.isCamera && !o.isLight && !o.isLine && !o.isPoints && o.name) nodes.push(o); });
  let meshes = 0;
  scene.traverse(o => { if (o.isMesh) meshes++; });
  const index = new Map(nodes.map((o, k) => [o, k]));
  const joints = nodes.map(o => {
    let p = o.parent;
    while (p && !index.has(p)) p = p.parent;
    return { name: o.name || (o.userData && o.userData.originalName) || 'joint', parent: p ? index.get(p) : -1, offset: [0, 0, 0], channels: [], chanStart: 0, end: null, children: [] };
  });
  joints.forEach((j, k) => { if (j.parent >= 0) joints[j.parent].children.push(k); });
  // the default pose (the rest) in world space
  const J = nodes.length;
  const restP = new Float64Array(J * 3), restQ = nodes.map(() => new THREE.Quaternion());
  const v = new THREE.Vector3();
  nodes.forEach((o, k) => { o.getWorldPosition(v); restP[k * 3] = v.x; restP[k * 3 + 1] = v.y; restP[k * 3 + 2] = v.z; o.getWorldQuaternion(restQ[k]); });
  joints.forEach((j, k) => { if (j.parent >= 0) j.offset = [0, 1, 2].map(c => restP[k * 3 + c] - restP[j.parent * 3 + c]); });
  // the animation stacks that move this skeleton
  const names = new Set(nodes.map(o => o.name));
  const stacks = [];
  (scene.animations || []).forEach((clip, i) => {
    const tracks = clip.tracks.filter(t => t.times.length && names.has(t.name.slice(0, t.name.lastIndexOf('.'))));
    if (!tracks.length) return;
    const c = new THREE.AnimationClip(clip.name || `Animation ${i + 1}`, -1, tracks);
    const fps = keyRate(c);
    const sampleFps = Math.min(fps, MAX_SAMPLE_FPS);
    const frames = Math.min(MAX_FRAMES, Math.max(1, Math.round(c.duration * sampleFps) + 1));
    stacks.push({ name: c.name, seconds: c.duration, fps, sampleFps, frames, clip: c });
  });
  if (!nodes.length) throw new BVHError('This FBX file has no skeleton, so there is no motion to copy. Export it again with its skeleton (armature), or use a BVH file.');
  if (!stacks.length) {
    throw new BVHError('This FBX file has a skeleton but no animation (only a model or a pose). Export it again with the animation included '
      + '(often called "bake animation" or "with animation"), or use a BVH file.');
  }
  const cache = new Map();
  const out = {
    joints, meshes, stacks, bones: nodes.filter(o => o.isBone).length,
    // motion(i) -> the bvh-like motion of stack i (sampled once)
    motion(i = 0) {
      if (cache.has(i)) return cache.get(i);
      const st = stacks[i];
      if (!st) throw new BVHError('This FBX file has no animation for its skeleton.');
      const m = sample(scene, nodes, restQ, restP, st);
      m.joints = joints;
      m.warnings = [];
      if (st.frames >= MAX_FRAMES) m.warnings.push('Only the first ten minutes of this animation were read.');
      if (st.fps > MAX_SAMPLE_FPS) m.warnings.push(`The animation runs at ${st.fps} fps; it was read at ${MAX_SAMPLE_FPS} fps.`);
      cache.set(i, m);
      return m;
    },
    dispose() {
      scene.traverse(o => {
        if (o.geometry) o.geometry.dispose();
        const mats = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : [];
        for (const mt of mats) { for (const k of Object.keys(mt)) if (mt[k] && mt[k].isTexture) mt[k].dispose(); mt.dispose(); }
      });
    },
  };
  return out;
}

// Every joint's world place and turn (relative to the rest) in every frame of one stack.
function sample(scene, nodes, restQ, restP, st) {
  const J = nodes.length, F = st.frames;
  const P = new Float32Array(F * J * 3), Q = new Float32Array(F * J * 4);
  const mixer = new THREE.AnimationMixer(scene);
  const action = mixer.clipAction(st.clip);
  action.setLoop(THREE.LoopOnce, 1);                          // the last frame is the clip's end, not its start again
  action.clampWhenFinished = true;
  action.play();
  const v = new THREE.Vector3(), q = new THREE.Quaternion(), inv = restQ.map(r => r.clone().invert());
  for (let f = 0; f < F; f++) {
    mixer.setTime(Math.min(st.seconds, f / st.sampleFps));
    scene.updateMatrixWorld(true);
    for (let k = 0; k < J; k++) {
      nodes[k].getWorldPosition(v);
      nodes[k].getWorldQuaternion(q).multiply(inv[k]).normalize();
      const a = (f * J + k) * 3, b = (f * J + k) * 4;
      P[a] = v.x; P[a + 1] = v.y; P[a + 2] = v.z;
      Q[b] = q.x; Q[b + 1] = q.y; Q[b + 2] = q.z; Q[b + 3] = q.w;
    }
  }
  action.stop();
  mixer.uncacheRoot(scene);
  // back to the rest, so another stack starts from it
  scene.traverse(o => { if (o.userData.__rest) { o.position.copy(o.userData.__rest.p); o.quaternion.copy(o.userData.__rest.q); o.scale.copy(o.userData.__rest.s); } });
  scene.updateMatrixWorld(true);
  return { format: 'FBX', stack: st.name, frames: F, frameTime: 1 / st.sampleFps, fps: st.sampleFps, fileFps: st.fps, channels: 0, data: null, sampled: { P, Q, restP } };
}

export { TICKS };
