// A stand-in for MediaPipe, so the whole capture flow can be tried and tested without the one-time download: a
// library animation (or a built-in dance) is played on a bare rig, and "filmed" - the rig's own joints become the
// landmarks, a virtual camera 3.4 m in front gives the picture points, and a canvas draws the performer as a video.
// Loaded by ?captureMock=1 or window.__captureMock (tests), and offered in the studio when MediaPipe is missing.
// Two people: a couple animation from the library (both actors filmed by the same camera), or the scene itself
// (window.__captureMockScene: the project's own sims as they play, holds included).
import * as THREE from 'three';
import { api } from '../api.js';
import { ClipPlayer, sampleToPose } from '../animation.js';
import { RigPose, landmarks, PL } from './rigpose.js';
import { emptyPerson } from './clean.js';
import { BS } from './facemap.js';
import { recordAt, frameIndexAt } from './detect.js';

export const isMock = () => {
  try { return !!window.__captureMock || new URLSearchParams(location.search).has('captureMock'); } catch { return false; }
};

const UP = new THREE.Vector3(0, 1, 0);

// ---------------------------------------------------------------- the motion that gets "filmed"
// -> { poseAt(t) -> {rot, pos}, duration, name }
export async function loadMockMotion({ animId = null, query = 'Stripper' } = {}) {
  try {
    let id = animId;
    if (id === null || id === undefined) {
      let items = (await api.library({ q: query, actors: 1 })).items || [];
      if (!items.length) items = (await api.library({ actors: 1 })).items || [];
      if (!items.length) throw new Error('no solo animation');
      id = items[0].id;
    }
    const a = await api.animation(id);
    const clip = a.clips[0];
    const player = new ClipPlayer(clip);
    const fps = clip.fps || 30, last = Math.max(1, clip.ticks - 1);
    return {
      name: a.name, duration: last / fps,
      poseAt: t => sampleToPose(player.sample(Math.max(0, Math.min(last, t * fps)))),
    };
  } catch (e) {
    return builtInDance();
  }
}

// A slow sway with arm waves (used when there is no library): periodic, 2.1 s long.
export function builtInDance(period = 2.1, seconds = 8) {
  const q = (x, y, z, a) => new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(x, y, z).normalize(), a);
  return {
    name: 'Built-in dance', duration: seconds, synthetic: true, rig: null,
    poseAt(t, rig) {
      const w = (2 * Math.PI * t) / period, s = Math.sin(w), c = Math.cos(w);
      const rest = rig ? Object.fromEntries(rig.bones.map(b => [b.name, b.rot])) : {};
      const mul = (name, dq) => { const r = new THREE.Quaternion().fromArray(rest[name] || [0, 0, 0, 1]); return r.multiply(dq).toArray(); };
      const rot = {
        b__Pelvis__: mul('b__Pelvis__', q(1, 0, 0, 0.12 * s)),
        b__Spine1__: mul('b__Spine1__', q(1, 0, 0, -0.08 * s)),
        b__Spine2__: mul('b__Spine2__', q(0, 1, 0, 0.1 * c)),
        b__Head__: mul('b__Head__', q(0, 0, 1, 0.1 * s)),
        b__L_UpperArm__: mul('b__L_UpperArm__', q(0, 1, 0.3, 0.6 + 0.35 * s)),
        b__R_UpperArm__: mul('b__R_UpperArm__', q(0, 1, -0.3, -0.6 - 0.35 * c)),
        b__L_Forearm__: q(0, 0, 1, 0.9 + 0.4 * s).toArray(),
        b__R_Forearm__: q(0, 0, 1, 0.9 + 0.4 * c).toArray(),
        b__L_Thigh__: mul('b__L_Thigh__', q(0, 0, 1, 0.25 + 0.2 * s)),
        b__R_Thigh__: mul('b__R_Thigh__', q(0, 0, 1, 0.25 - 0.2 * s)),
        b__L_Calf__: q(0, 0, 1, -0.4 - 0.3 * s).toArray(),
        b__R_Calf__: q(0, 0, 1, -0.4 + 0.3 * s).toArray(),
      };
      return { rot, pos: {} };
    },
  };
}

// A couple: the first library animation for two sims that loads (both actors' clips share one space, so they stand
// where they stand to each other). -> { name, duration, people: 2, posesAt(t) -> [pose, pose] } (or a single-person
// motion when there is none)
export async function loadMockCouple({ animId = null, queries = ['Missionary', 'Cowgirl', 'Doggy', ''] } = {}) {
  const ids = [];
  try {
    if (animId !== null && animId !== undefined) ids.push(animId);
    else for (const q of queries) { const items = (await api.library({ q, actors: 2 })).items || []; ids.push(...items.slice(0, 3).map(x => x.id)); if (ids.length >= 3) break; }
  } catch { /* no library */ }
  for (const id of ids) {
    try {
      const a = await api.animation(id);
      if (!a || !a.clips || a.clips.length < 2) continue;
      const players = a.clips.slice(0, 2).map(c => new ClipPlayer(c));
      const fps = a.clips[0].fps || 30, last = Math.max(1, Math.min(...a.clips.slice(0, 2).map(c => c.ticks)) - 1);
      if (last < 30) continue;
      return { name: a.name, duration: last / fps, people: 2, posesAt: t => players.map(pl => sampleToPose(pl.sample(Math.max(0, Math.min(last, t * fps))))) };
    } catch { /* the next one */ }
  }
  return loadMockMotion();
}

// The scene as it plays: every sim (at most two) as the app shows it at each frame - keys, motions and holds. Poses
// are read back from the 3D views, so a hand holding the partner is filmed on the partner's skin. frames: which
// frames (default: the whole animation). The app is put back on its own frame afterwards.
export function sceneMotion(app, { frames = null } = {}) {
  const p = app.store.project, pl = app.pipeline;
  const L = Math.max(1, p.length), fps = p.fps || 30;
  const list = frames || Array.from({ length: L }, (_, f) => f);
  const sims = p.sims.filter(s => s.visible !== false && app.simViews.get(s.id)).slice(0, 2);
  const read = v => {
    const rot = {}, pos = {};
    for (const b of v.bones) { rot[b.name] = b.quaternion.toArray(); pos[b.name] = b.position.toArray(); }
    return { rot, pos };
  };
  const shots = [];
  const frame = app.store.frame;
  try {
    for (const f of list) {
      pl.apply(f, { physics: false, overrides: false });
      shots.push(sims.map(s => read(app.simViews.get(s.id))));
    }
  } finally {
    app.store.frame = frame;
    try { app.applyPoses(false); } catch { /* a bare page */ }
  }
  const n = shots.length;
  return {
    name: n === 1 ? 'Your scene (still)' : 'Your scene', duration: n > 1 ? (n - 1) / fps : 0, people: sims.length, simIds: sims.map(s => s.id),
    posesAt: t => shots[Math.max(0, Math.min(n - 1, Math.round(t * fps)))],
  };
}

// ---------------------------------------------------------------- filming it
// The virtual camera: fixed, 3.4 m in front of where the performer starts, lens at 0.95 m, 60 degrees wide.
export function camera(W = 1280, H = 720, fovDeg = 60) {
  const f = Math.max(W, H) / (2 * Math.tan(THREE.MathUtils.degToRad(fovDeg) / 2));
  const C = new THREE.Vector3(0, 0.95, 3.4);
  return {
    W, H, f, C, fov: fovDeg,
    project(p) { const d = Math.max(0.2, C.z - p.z); return [0.5 + (f * (p.x - C.x)) / d / W, 0.5 - (f * (p.y - C.y)) / d / H, (p.z - C.z) / 3]; },
  };
}

function gauss() { let u = 0, v = 0; while (!u) u = Math.random(); while (!v) v = Math.random(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }

// One filmed frame of the rig (already posed and fk()'d): the landmark record a tracker would give.
// turn: the turn that puts the performer facing the camera; origin: their start place (sim space).
export function filmFrame(rp, cam, { turn, origin, t = 0, face = true, hands = true, noise = 0, blink = null } = {}) {
  const lm = landmarks(rp);
  const put = p => p.clone().sub(origin).applyQuaternion(turn);         // sim space, performer facing the camera
  const P = lm.pose.map(put);
  const hipC = P[PL.hipL].clone().add(P[PL.hipR]).multiplyScalar(0.5);
  const world = new Float32Array(33 * 4), img = new Float32Array(33 * 3);
  for (let j = 0; j < 33; j++) {
    const w = P[j].clone().sub(hipC);
    const nz = noise ? [gauss() * noise, gauss() * noise, gauss() * noise] : [0, 0, 0];
    world[j * 4] = w.x + nz[0]; world[j * 4 + 1] = -w.y + nz[1]; world[j * 4 + 2] = -w.z + nz[2];
    world[j * 4 + 3] = 0.98;
    const ip = cam.project(P[j]);
    img[j * 3] = ip[0] + (noise ? gauss() * noise * 0.3 : 0); img[j * 3 + 1] = ip[1] + (noise ? gauss() * noise * 0.3 : 0); img[j * 3 + 2] = ip[2];
  }
  const out = { pose: { world, img }, hands: { L: null, R: null, Limg: null, Rimg: null }, face: null, people: 1 };
  if (hands) for (const s of ['L', 'R']) {
    const H = lm.hands[s].map(put), w0 = H[0].clone();
    const arr = new Float32Array(63), im = new Float32Array(63);
    H.forEach((p, j) => {
      const w = p.clone().sub(w0);
      arr[j * 3] = w.x; arr[j * 3 + 1] = -w.y; arr[j * 3 + 2] = -w.z;
      const ip = cam.project(p);
      im[j * 3] = ip[0]; im[j * 3 + 1] = ip[1]; im[j * 3 + 2] = ip[2];
    });
    out.hands[s] = arr; out.hands[s + 'img'] = im;
  }
  if (face) {
    const bs = new Float32Array(52);
    const b = blink || (() => [0, 0]);
    const [bl, br] = b(t);
    bs[BS.eyeBlinkLeft] = 0.05 + 0.9 * bl; bs[BS.eyeBlinkRight] = 0.05 + 0.9 * br;
    bs[BS.jawOpen] = 0.12 + 0.14 * (1 + Math.sin(2 * Math.PI * t / 1.7));
    bs[BS.mouthSmileLeft] = bs[BS.mouthSmileRight] = 0.2 + 0.1 * Math.sin(2 * Math.PI * t / 3.1);
    bs[BS.browInnerUp] = 0.15 + 0.15 * Math.max(0, Math.sin(2 * Math.PI * t / 4.3));
    bs[BS.eyeSquintLeft] = bs[BS.eyeSquintRight] = 0.1;
    const hk = rp.index('b__Head__');
    const D = turn.clone().multiply(rp.W[hk]).multiply(rp.restW[hk].clone().invert());
    const m = new THREE.Matrix4().makeRotationFromQuaternion(D);
    const ip = cam.project(P[PL.nose]);
    out.face = { bs, m: Float32Array.from(m.elements), eyeL: 1 - bl, eyeR: 1 - br, box: [ip[0] - 0.05, ip[1] - 0.08, 0.1, 0.16] };
  }
  return out;
}

// A whole synthetic take (for tests and the mock tracker). A motion with posesAt (a couple, a scene) gives one person
// per performer, filmed by the same camera: it looks across the line between them (so both are in the picture, side
// by side), from the side the first performer faces more.
export function takeFromMotion(rig, motion, { fps = 30, seconds = null, start = 0, jitter = 0, face = true, hands = true, noise = 0, W = 1280, H = 720, blink = defaultBlink } = {}) {
  const rp = new RigPose(rig);
  const cam = camera(W, H);
  const multi = typeof motion.posesAt === 'function';
  const posesAt = t => (multi ? motion.posesAt(t, rig) : [motion.poseAt(t, rig)]);
  const count = multi ? Math.max(1, Math.min(2, motion.people || posesAt(start).length)) : 1;
  const dur = Math.min(motion.duration, seconds || motion.duration);
  const n = Math.max(1, Math.floor(dur * fps) + 1);
  const t = new Float64Array(n);
  for (let i = 0; i < n; i++) t[i] = start + i / fps + (i > 0 && i < n - 1 ? (Math.random() - 0.5) * jitter / fps : 0);
  // face the camera: the turn that brings the first performer's start facing onto +Z, and the start place (the middle
  // of everyone's hips, on the floor) to the middle of the picture
  const first = posesAt(start);
  const hipsAt = pose => { rp.resetPose(); rp.setPose(pose); rp.fk(); return { l: rp.pos('b__L_Thigh__').clone().sub(rp.pos('b__R_Thigh__')), c: rp.pos('b__L_Thigh__').clone().add(rp.pos('b__R_Thigh__')).multiplyScalar(0.5) }; };
  const h0 = hipsAt(first[0]);
  let yaw = -Math.atan2(-h0.l.z, h0.l.x);
  const origin = h0.c.clone();
  if (count > 1) {
    const h1 = hipsAt(first[1]);
    origin.add(h1.c).multiplyScalar(0.5);
    const across = h1.c.clone().sub(h0.c).setY(0);
    if (across.length() > 0.1) {
      // the camera's right runs from the first performer to the second (or back): whichever the first faces more
      const a = Math.atan2(-across.z, across.x);
      const c = Math.cos(-a - yaw);
      yaw = c >= 0 ? -a : Math.PI - a;
    }
  }
  origin.setY(0);
  const turn = new THREE.Quaternion().setFromAxisAngle(UP, yaw);
  const people = Array.from({ length: count }, () => emptyPerson(n));
  for (let i = 0; i < n; i++) {
    const poses = posesAt(t[i]);
    for (let k = 0; k < count; k++) {
      rp.resetPose(); rp.setPose(poses[k]); rp.fk();
      const fr = filmFrame(rp, cam, { turn, origin, t: t[i] - start, face, hands, noise, blink });
      writeFrame(people[k], i, fr);
    }
  }
  return { source: 'mock', width: W, height: H, fov: cam.fov, t, people, name: motion.name };
}

export function defaultBlink(t) {
  const ph = t % 2.7;
  const both = ph > 1.2 && ph < 1.4 ? Math.sin(((ph - 1.2) / 0.2) * Math.PI) : 0;
  const w = t % 5.4, wink = w > 3.9 && w < 4.3 ? Math.sin(((w - 3.9) / 0.4) * Math.PI) : 0;       // a left wink now and then
  return [Math.max(both, wink), both];
}

// Store a frame record into a person's arrays at index i.
export function writeFrame(person, i, fr) {
  if (fr.pose) { person.pose.set(fr.pose.world, i * 132); person.img.set(fr.pose.img, i * 99); }
  if (fr.hands) for (const s of ['L', 'R']) if (fr.hands[s]) { person.hand[s].set(fr.hands[s], i * 63); person.hand[s + 'ok'][i] = 1; }
  if (fr.face) {
    person.face.bs.set(fr.face.bs, i * 52); person.face.m.set(fr.face.m, i * 16);
    person.face.ok[i] = 1; person.face.eyeL[i] = fr.face.eyeL; person.face.eyeR[i] = fr.face.eyeR;
  }
}

// ---------------------------------------------------------------- a canvas that acts like a <video>
// It draws the performer from the take's picture points (a soft, faceless figure on a studio backdrop).
export class MockVideo {
  constructor(take, { live = false, width = 640 } = {}) {
    this.take = take;
    this.live = live;
    this.el = document.createElement('canvas');
    this.el.width = width; this.el.height = Math.round(width * take.height / take.width);
    this.el.className = 'cap-mock-video';
    this.videoWidth = take.width; this.videoHeight = take.height;
    this.duration = take.t[take.t.length - 1] - take.t[0];
    this.currentTime = 0; this.paused = true; this.playbackRate = 1; this.readyState = 4; this.ended = false;
    this._cbs = []; this._raf = 0; this._last = 0; this._frames = 0;
    this.draw();
  }
  frameIndex(t = this.currentTime) { return frameIndexAt(this.take.t, t); }
  play() {
    if (!this.paused) return Promise.resolve();
    this.paused = false; this.ended = false; this._last = performance.now();
    const step = now => {
      if (this.paused) return;
      const dt = Math.min(0.1, (now - this._last) / 1000); this._last = now;
      this.currentTime += dt * this.playbackRate;
      if (this.currentTime >= this.duration) {
        if (this.live) this.currentTime %= Math.max(0.1, this.duration);
        else { this.currentTime = this.duration; this.paused = true; this.ended = true; }
      }
      this.draw();
      this._frames++;
      const cbs = this._cbs; this._cbs = [];
      for (const cb of cbs) cb(now, { mediaTime: this.currentTime, presentedFrames: this._frames });
      if (this.ended) { this.el.dispatchEvent(new Event('ended')); return; }
      this._raf = requestAnimationFrame(step);
    };
    this._raf = requestAnimationFrame(step);
    return Promise.resolve();
  }
  pause() { this.paused = true; cancelAnimationFrame(this._raf); }
  seek(t) { this.currentTime = Math.max(0, Math.min(this.duration, t)); this.draw(); this.el.dispatchEvent(new Event('seeked')); }
  requestVideoFrameCallback(cb) { this._cbs.push(cb); return this._cbs.length; }
  cancelVideoFrameCallback() { this._cbs = []; }
  addEventListener(...a) { this.el.addEventListener(...a); }
  removeEventListener(...a) { this.el.removeEventListener(...a); }
  // the frame record at the current time (what the mock tracker "sees"; person 2 in `others`)
  record() { return recordAt(this.take, this.frameIndex()); }
  draw() {
    const c = this.el, g = c.getContext('2d'), W = c.width, H = c.height;
    const grd = g.createLinearGradient(0, 0, 0, H);
    grd.addColorStop(0, '#2b2438'); grd.addColorStop(0.62, '#1b1724'); grd.addColorStop(1, '#141019');
    g.fillStyle = grd; g.fillRect(0, 0, W, H);
    g.fillStyle = 'rgba(255,255,255,.035)';
    for (let x = 0; x < W; x += W / 16) g.fillRect(x, H * 0.62, 1, H * 0.38);
    g.fillRect(0, H * 0.62, W, 1);
    const i = this.frameIndex();
    // farther performers first (picture z grows away from the camera)
    const order = this.take.people.map((pe, k) => [k, pe.img[(i * 33 + 0) * 3 + 2]]).sort((a, b) => b[1] - a[1]).map(x => x[0]);
    for (const k of order) this._drawPerson(g, this.take.people[k], i, W, H, k);
    g.shadowBlur = 0;
  }
  _drawPerson(g, pe, i, W, H, k) {
    if (!pe.pose[i * 132 + 23 * 4 + 3]) return;
    const pt = j => [pe.img[(i * 33 + j) * 3] * W, pe.img[(i * 33 + j) * 3 + 1] * H];
    const seg = (a, b, r) => { const A = pt(a), B = pt(b); g.lineWidth = r; g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.stroke(); };
    const s = H / 720;
    const skin = k ? '#9c7563' : '#c99d86', head = k ? '#a97f6b' : '#d1a58e';
    g.lineCap = 'round'; g.lineJoin = 'round';
    g.strokeStyle = skin;
    g.shadowColor = 'rgba(0,0,0,.35)'; g.shadowBlur = 12 * s;
    // torso as a filled shape
    const sh = [pt(11), pt(12), pt(24), pt(23)];
    g.fillStyle = skin;
    g.beginPath(); g.moveTo(...sh[0]); for (const p of sh.slice(1)) g.lineTo(...p); g.closePath(); g.fill();
    seg(11, 12, 34 * s); seg(23, 24, 40 * s); seg(11, 23, 30 * s); seg(12, 24, 30 * s);
    for (const [a, b, r] of [[23, 25, 34], [25, 27, 26], [24, 26, 34], [26, 28, 26], [27, 31, 14], [28, 32, 14], [11, 13, 22], [13, 15, 18], [12, 14, 22], [14, 16, 18], [15, 19, 12], [16, 20, 12]]) seg(a, b, r * s);
    const hd = pt(0), earL = pt(7), earR = pt(8);
    const hr = Math.max(14 * s, Math.hypot(earL[0] - earR[0], earL[1] - earR[1]) * 0.75);
    g.fillStyle = head;
    g.beginPath(); g.arc(hd[0], hd[1] - hr * 0.25, hr, 0, Math.PI * 2); g.fill();
  }
}
