// Little head close-ups of the game faces, rendered off screen a few at a time, once per face and body. Kept in
// memory and in the browser's IndexedDB (never localStorage: it is small and the crash-safe autosave lives there),
// so the next start shows them at once. Nothing is rendered until the Game faces tab is open.
import * as THREE from 'three';
import { Sim } from './sim.js';

const VERSION = 'v4';
const SIZE = 144;                               // shown at about 80 px: sharp on a 1.5x screen too
const DB = 'wa-facethumbs', STORE = 'thumbs';

// ---------------------------------------------------------------- IndexedDB (optional; every failure is quiet)
let _db = null;
function db() {
  if (_db) return _db;
  _db = new Promise(resolve => {
    try {
      const req = indexedDB.open(DB, 1);
      req.onupgradeneeded = () => { try { req.result.createObjectStore(STORE); } catch { /* exists */ } };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
      req.onblocked = () => resolve(null);
    } catch { resolve(null); }
  });
  return _db;
}
async function dbGet(key) {
  const d = await db();
  if (!d) return null;
  return new Promise(resolve => {
    try {
      const r = d.transaction(STORE, 'readonly').objectStore(STORE).get(key);
      r.onsuccess = () => resolve(typeof r.result === 'string' ? r.result : null);
      r.onerror = () => resolve(null);
    } catch { resolve(null); }
  });
}
async function dbPut(key, value) {
  const d = await db();
  if (!d) return;
  try { d.transaction(STORE, 'readwrite').objectStore(STORE).put(value, key); } catch { /* full or blocked: memory only */ }
}

// ---------------------------------------------------------------- the renderer
export class FaceThumbs {
  constructor(app) {
    this.app = app;
    this.mem = new Map();          // key -> data URL
    this.todo = [];                // [{frame, face}]
    this.queued = new Set();
    this.busy = false;
    this.listeners = new Set();
  }

  static bodyOf(sim) { return sim && sim.frame === 'ym' ? 'ym' : 'yf'; }
  key(frame, id) { return `${VERSION}|${frame}|${id}`; }
  get(frame, id) { return this.mem.get(this.key(frame, id)) || null; }
  onReady(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  _tell(frame, id, url) { for (const fn of [...this.listeners]) { try { fn(frame, id, url); } catch (e) { console.error(e); } } }

  // Ask for pictures of these faces on this body; each arrives through onReady (from the cache at once when kept).
  request(frame, faces) {
    for (const f of faces) {
      const k = this.key(frame, f.id);
      if (this.mem.has(k) || this.queued.has(k)) continue;
      this.queued.add(k);
      this.todo.push({ frame, face: f, k });
    }
    this._pump();
  }
  // faces no longer on screen are not rendered first (a new request puts its faces at the front)
  clear() { this.todo.length = 0; this.queued.clear(); }

  _pump() {
    if (this.busy || !this.todo.length) return;
    this.busy = true;
    const step = async () => {
      const batch = this.todo.splice(0, 4);
      for (const job of batch) {
        let url = await dbGet(job.k);
        if (!url) {
          try { url = await this._render(job.frame, job.face); } catch (e) { console.warn('face picture', e); url = null; }
          if (url) dbPut(job.k, url);
        }
        this.queued.delete(job.k);
        if (url) { this.mem.set(job.k, url); this._tell(job.frame, job.face.id, url); }
      }
      if (this.todo.length) setTimeout(step, 16);
      else this.busy = false;
    };
    setTimeout(step, 0);
  }

  _setup() {
    if (this.renderer) return;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(1);
    this.renderer.setSize(SIZE, SIZE);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.45;
    this.scene = new THREE.Scene();
    this.scene.add(new THREE.HemisphereLight(0xfff4ee, 0x3a2f3c, 1.5));
    this.keyLight = new THREE.DirectionalLight(0xffffff, 2.4); this.scene.add(this.keyLight); this.scene.add(this.keyLight.target);
    this.fill = new THREE.DirectionalLight(0xffeee6, 1.1); this.scene.add(this.fill); this.scene.add(this.fill.target);
    this.rim = new THREE.DirectionalLight(0xff8cc4, 0.8); this.scene.add(this.rim); this.scene.add(this.rim.target);
    this.camera = new THREE.PerspectiveCamera(24, 1, 0.02, 10);
    this.sims = {};
  }

  // the game's skin pictures arrive a moment after the bodies: wait for them (never longer than a few seconds)
  async _sim(frame) {
    this._setup();
    if (!this.sims[frame]) {
      const app = this.app, body = app.assets.bodies[frame] || app.assets.bodies.yf;
      const s = new Sim(app.assets.rig, body, { skin: frame === 'ym' ? '#d9a585' : '#f0c4a8' });
      if (app.applySkin) app.applySkin(s, frame);
      s.setErect(false);
      for (const m of s.meshes) if (/penis/.test(m.userData.role || '')) m.visible = false;
      this.scene.add(s.group);
      const wait = app.skinReady ? app.skinReady(frame) : Promise.resolve();
      this.sims[frame] = { s, ready: Promise.race([wait, new Promise(r => setTimeout(r, 6000))]) };
    }
    await this.sims[frame].ready;
    return this.sims[frame].s;
  }

  async _render(frame, face) {
    const s = await this._sim(frame);
    for (const [f, x] of Object.entries(this.sims)) x.s.group.visible = f === frame;
    s.resetPose();
    s.setFaceBones(face.fb || face);
    s.group.updateMatrixWorld(true);
    // the face frame: x up, y forward, z the sim's left (head bone)
    const head = s.bone('b__Head__');
    const q = head.getWorldQuaternion(new THREE.Quaternion());
    const up = new THREE.Vector3(1, 0, 0).applyQuaternion(q), fwd = new THREE.Vector3(0, 1, 0).applyQuaternion(q), left = new THREE.Vector3(0, 0, 1).applyQuaternion(q);
    // the middle of the face: between the eyes and the upper lip
    const at = new THREE.Vector3();
    let n = 0;
    for (const b of ['b__L_Eye__', 'b__R_Eye__', 'b__UpLip__', 'b__Jaw__']) { const bone = s.bone(b); if (bone) { at.add(bone.localToWorld(s.faceHandlePoint(b).clone())); n++; } }
    if (n) at.multiplyScalar(1 / n); else head.getWorldPosition(at);
    at.addScaledVector(up, 0.016);
    // a little from the sim's right and above: the face reads round, both eyes stay in view, the whole head shows
    const dir = fwd.clone().multiplyScalar(0.97).addScaledVector(left, -0.16).addScaledVector(up, 0.08).normalize();
    this.camera.position.copy(at).addScaledVector(dir, 0.47);
    this.camera.up.copy(up);
    this.camera.lookAt(at);
    this.keyLight.position.copy(at).addScaledVector(fwd, 1).addScaledVector(up, 1.2).addScaledVector(left, -0.8); this.keyLight.target.position.copy(at);
    this.fill.position.copy(this.camera.position).sub(at).multiplyScalar(4).add(at); this.fill.target.position.copy(at);
    this.rim.position.copy(at).addScaledVector(fwd, -1).addScaledVector(left, 1).addScaledVector(up, 0.5); this.rim.target.position.copy(at);
    for (const l of [this.keyLight, this.fill, this.rim]) l.target.updateMatrixWorld();
    this.renderer.render(this.scene, this.camera);
    const c = this.renderer.domElement;
    let url = c.toDataURL('image/webp', 0.86);
    if (!url.startsWith('data:image/webp')) url = c.toDataURL('image/png');
    return url;
  }

  dispose() {
    this.clear();
    if (this.renderer) { this.renderer.dispose(); this.renderer.forceContextLoss?.(); this.renderer = null; }
    for (const x of Object.values(this.sims || {})) x.s.dispose && x.s.dispose();
    this.sims = {};
  }
}

let _one = null;
export function faceThumbs(app) { return _one || (_one = new FaceThumbs(app)); }
