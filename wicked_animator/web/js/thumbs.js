// Little pictures of poses for the pose gallery, rendered off screen a few at a time. A pose of one part is framed on
// that part: hands close up, a face from the front (with its expression).
import * as THREE from 'three';
import { Sim } from './sim.js';
import { applyFace } from './face.js';
import { spaceQuat } from './posemath.js';
import { rigInfo } from './keyops.js';

// the cache key: a renamed or changed pose (updated) gets a new picture
const keyOf = pr => pr.id + '|' + (pr.updated || '');
const FINGER_TIPS = s => [`b__${s}_Hand__`, `b__${s}_Thumb2__`, `b__${s}_Index2__`, `b__${s}_Mid2__`, `b__${s}_Ring2__`, `b__${s}_Pinky2__`];

export class ThumbRenderer {
  constructor(app) {
    this.app = app;
    this.cache = new Map();
    this.todo = [];
    this.busy = false;
  }

  _setup() {
    if (this.renderer) return;
    this.w = 240; this.h = 180;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    this.renderer.setSize(this.w, this.h);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.55;
    this.scene = new THREE.Scene();
    this.scene.add(new THREE.HemisphereLight(0xfff6f0, 0x3a2f3c, 1.6));
    const key = new THREE.DirectionalLight(0xffffff, 2.6); key.position.set(2, 4, 3); this.scene.add(key);
    this.fill = new THREE.DirectionalLight(0xffefe6, 1.4); this.scene.add(this.fill);   // follows the camera
    const rim = new THREE.DirectionalLight(0xff8cc4, 0.9); rim.position.set(-3, 2, -3); this.scene.add(rim);
    this.camera = new THREE.PerspectiveCamera(30, this.w / this.h, 0.05, 50);
    this.sims = {};
  }

  _sim(frame) {
    if (!this.sims[frame]) {
      const body = this.app.assets.bodies[frame] || this.app.assets.bodies.yf;
      const s = new Sim(this.app.assets.rig, body, { skin: frame === 'ym' ? '#d9a585' : '#f0c4a8' });
      this.app.applySkin && this.app.applySkin(s, frame);
      this.scene.add(s.group);
      this.sims[frame] = [s];
    }
    return this.sims[frame];
  }

  get(pr) { return this.cache.get(keyOf(pr)) || null; }

  queue(list, onDone) {
    for (const pr of list) if (!this.cache.has(keyOf(pr)) && !this.todo.includes(pr)) this.todo.push(pr);
    this.onDone = onDone;
    this._pump();
  }

  // The game's skin pictures arrive a moment after the bodies: wait for them before the first picture is taken,
  // or the first thumbnails come out as dark, untextured figures (never longer than a few seconds).
  _skinsReady() {
    if (!this._ready) {
      this._setup();
      this._sim('yf'); this._sim('ym');             // starts loading both skins
      const wait = this.app.skinReady ? Promise.all([this.app.skinReady('yf'), this.app.skinReady('ym')]) : Promise.resolve();
      this._ready = Promise.race([wait, new Promise(r => setTimeout(r, 8000))]);
    }
    return this._ready;
  }

  _pump() {
    if (this.busy || !this.todo.length) return;
    this.busy = true;
    const step = () => {
      const batch = this.todo.splice(0, 3);
      for (const pr of batch) { try { this.cache.set(keyOf(pr), this.render(pr)); } catch (e) { console.warn('thumb', e); } }
      if (this.todo.length) setTimeout(step, 30);
      else { this.busy = false; this.onDone && this.onDone(); }
      if (batch.length && this.todo.length % 9 === 0) this.onDone && this.onDone();
    };
    this._skinsReady().then(() => setTimeout(step, 50));
  }

  render(pr) {
    this._setup();
    // hide every cached sim, then pose the ones this picture needs
    for (const list of Object.values(this.sims)) for (const s of list) s.group.visible = false;
    const used = {};
    const box = new THREE.Box3();
    const shown = [];
    pr.sims.forEach(ps => {
      const frame = ps.gender === 'MALE' ? 'ym' : 'yf';
      used[frame] = (used[frame] || 0) + 1;
      const list = this._sim(frame);
      while (list.length < used[frame]) {
        const s = new Sim(this.app.assets.rig, this.app.assets.bodies[frame], { skin: frame === 'ym' ? '#d9a585' : '#f0c4a8' });
        this.app.applySkin && this.app.applySkin(s, frame);
        this.scene.add(s.group); list.push(s);
      }
      const s = list[used[frame] - 1];
      s.group.visible = true;
      s.resetPose();
      s.setPose(ps.pose);
      if (s.setFaceBones) s.setFaceBones(ps.faceBones || null);
      if (ps.face && Object.keys(ps.face).length) { try { applyFace(s, ps.face); } catch { /* the face as posed */ } }
      s.group.updateMatrixWorld(true);
      for (const m of s.meshes) if (m.visible) { m.geometry.computeBoundingBox(); }
      shown.push(s);
      for (const n of ['b__Head__', 'b__L_Foot__', 'b__R_Foot__', 'b__L_Hand__', 'b__R_Hand__', 'b__Pelvis__']) box.expandByPoint(s.worldPos(n));
    });
    const part = pr.part && pr.part !== 'all' ? pr.part : null;
    const s0 = shown[0];
    // which way a bone of the first sim points (in the world), from its rest direction
    const dirOf = (name, rest) => {
      const info = rigInfo(this.app.assets.rig), i = info.index[name];
      if (!s0 || i === undefined || !s0.bone(name)) return rest.clone();
      const q = spaceQuat(s0, s0.bone(name)).multiply(info.RS[i].clone().invert());
      return rest.clone().applyQuaternion(q).applyQuaternion(s0.space.getWorldQuaternion(new THREE.Quaternion())).normalize();
    };
    if (part === 'face' && s0 && s0.bone('b__Head__')) {
      // the face, from 45 cm in front of it
      const fwd = dirOf('b__Head__', new THREE.Vector3(0, 0, 1)), up = dirOf('b__Head__', new THREE.Vector3(0, 1, 0));
      const at = s0.worldPos('b__Head__').add(up.clone().multiplyScalar(0.075)).add(fwd.clone().multiplyScalar(0.05));
      this.camera.position.copy(at).add(fwd.clone().multiplyScalar(0.45)).add(up.clone().multiplyScalar(0.04));
      this.camera.up.copy(up);
      this.camera.lookAt(at);
      this.camera.up.set(0, 1, 0);
      this._shoot(at);
      return this.renderer.domElement.toDataURL('image/png');
    }
    if (part && /hand/.test(part) && s0) {
      // the hands, close up: a box round the finger tips, seen from the front of the sim
      const hb = new THREE.Box3();
      let sides = part === 'L hand' ? ['L'] : part === 'R hand' ? ['R'] : ['L', 'R'];
      // both hands far apart (at the sides): the right one close up - hand poses are about the fingers
      if (sides.length === 2 && s0.bone('b__L_Hand__') && s0.bone('b__R_Hand__') && s0.worldPos('b__L_Hand__').distanceTo(s0.worldPos('b__R_Hand__')) > 0.4) sides = ['R'];
      for (const sd of sides) for (const n of FINGER_TIPS(sd)) if (s0.bone(n)) hb.expandByPoint(s0.worldPos(n));
      if (!hb.isEmpty()) {
        const c = hb.getCenter(new THREE.Vector3()), size = hb.getSize(new THREE.Vector3());
        const fwd = dirOf('b__Pelvis__', new THREE.Vector3(0, 1, 0)).setY(0);
        if (fwd.lengthSq() < 1e-6) fwd.set(0, 0, 1);
        fwd.normalize();
        const d = Math.max(0.35, Math.max(size.x, size.y, size.z) * 1.6 + 0.2);
        this.camera.position.copy(c).add(fwd.multiplyScalar(d)).add(new THREE.Vector3(0, d * 0.35, 0));
        this.camera.lookAt(c);
        this._shoot(c);
        return this.renderer.domElement.toDataURL('image/png');
      }
    }
    const c = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
    const r = Math.max(size.x, size.y, size.z) * 0.62 + 0.25;
    this.camera.position.set(c.x + r * 1.35, c.y + r * 0.75, c.z + r * 1.9);
    this.camera.lookAt(c);
    this._shoot(c);
    return this.renderer.domElement.toDataURL('image/png');
  }

  // the fill light follows the camera, then the picture is taken
  _shoot(c) {
    this.fill.position.copy(this.camera.position).sub(c).normalize().multiplyScalar(4).add(c);
    this.fill.target.position.copy(c); this.fill.target.updateMatrixWorld();
    this.renderer.render(this.scene, this.camera);
  }
}
