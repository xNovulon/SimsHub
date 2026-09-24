// See-through and bones like Blender (spec_bodies 7.2).
//   See-through: every sim but the selected one turns see-through (35%; with nothing selected all are at 50%), and so
//   does the furniture (40%) - to check hands and contact behind bodies. Every material gets back exactly what it had.
//   Bones: Blender's octahedral bones in each sim's colour, drawn over the body ("In front"), with a ball at each
//   joint. A click on a bone selects that body part. The selected bone is green, the one under the mouse white.
import * as THREE from 'three';
import { POSABLE } from './bones.js';

const EXTRA_BONES = ['b__Jaw__', 'b__Tounge__1', 'b__Tounge__2', 'b__Tounge__3'];
const SEL = new THREE.Color('#3ddc84'), HOT = new THREE.Color('#ffffff');
const SEE_OTHER = 0.35, SEE_ALL = 0.5, SEE_FURN = 0.4;

// Blender's octahedral bone, 1 long along +Y: a base at 0, widest at 10% (half-width 1, scaled by the length), a tip
// at 1. Flat-shaded by giving each face its own brightness (the material is unlit, like Blender's).
function boneGeometry() {
  const H = [0, 0, 0], T = [0, 1, 0], R = [[1, 0.1, 0], [0, 0.1, 1], [-1, 0.1, 0], [0, 0.1, -1]];
  const pos = [], col = [];
  const face = (a, b, c, k) => { pos.push(...a, ...b, ...c); for (let i = 0; i < 3; i++) col.push(k, k, k); };
  for (let i = 0; i < 4; i++) {
    const a = R[i], b = R[(i + 1) % 4];
    face(H, b, a, 0.62 + 0.08 * (i % 2));
    face(a, b, T, 0.86 + 0.14 * (i % 2));
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  g.computeVertexNormals();
  return g;
}
let _boneGeo = null, _ballGeo = null;

// Which bones are drawn for a view, and where each one's tail is: its first drawn child, with a few Blender-like
// exceptions (the hips point down between the thighs, the head up, the hand to the knuckles, toes and finger tips a
// little on).
function boneList(v) {
  const names = [...POSABLE, ...EXTRA_BONES].filter(n => v.bone(n));
  const set = new Set(names);
  const out = [];
  for (const n of names) {
    const b = v.bone(n);
    let tail = null;
    if (n === 'b__Pelvis__') tail = { mid: ['b__L_Thigh__', 'b__R_Thigh__'] };
    else if (n === 'b__Head__') tail = { axis: [1, 0, 0], len: 0.2 };
    else if (/_Hand__$/.test(n)) tail = { bone: n.replace('_Hand__', '_Mid0__') };
    else if (/_Toe__$/.test(n)) tail = { extend: n.replace('_Toe__', '_Foot__'), len: 0.05 };
    else if (/_(Thumb|Index|Mid|Ring|Pinky)2__$/.test(n)) tail = { extend: n.replace(/2__$/, '1__'), len: 0.02 };
    else if (n === 'b__Jaw__') tail = { axis: [-1, 0, 0], len: 0.08 };
    else if (n === 'b__Tounge__3') tail = { extend: 'b__Tounge__2', len: 0.02 };
    else if (n === 'b__Penis_Mid01') tail = { bone: 'b__Penis_Tip' };
    else {
      const kid = b.children.find(c => c.isBone && set.has(c.name));
      tail = kid ? { bone: kid.name } : { extend: b.parent && b.parent.isBone ? b.parent.name : null, len: 0.03 };
    }
    out.push({ name: n, bone: b, tail });
  }
  return out;
}

const _h = new THREE.Vector3(), _t = new THREE.Vector3(), _d = new THREE.Vector3(), _q = new THREE.Quaternion(), _s = new THREE.Vector3();
const _m = new THREE.Matrix4(), _wq = new THREE.Quaternion(), _one = new THREE.Vector3(1, 1, 1), _Y = new THREE.Vector3(0, 1, 0);
const wpos = (b, out) => out.setFromMatrixPosition(b.matrixWorld);

export class Xray {
  constructor(app) {
    this.app = app;
    this.seeOn = false;
    this.bonesOn = false;
    this.hot = null;                     // {simId, bone} under the mouse
    this._saved = new WeakMap();         // view -> its material state before see-through
    this._savedFurn = new Map();         // material -> {opacity, transparent, depthWrite}
    this._rigs = new Map();              // simId -> {v, list, bones: InstancedMesh, balls: InstancedMesh}
    this.group = new THREE.Group();
    this.group.name = 'xray-bones';
    app.vp.overlay.add(this.group);
  }

  // ---------------------------------------------------------------- see-through
  setSeeThrough(on) {
    this.seeOn = !!on;
    this.applySee();
  }

  applySee() {
    const app = this.app, sel = app.store.selected && app.store.selected.sim;
    const hasSel = !!(sel && app.simViews.has(sel));
    for (const [id, v] of app.simViews) {
      const want = !this.seeOn ? 1 : hasSel ? (id === sel ? 1 : SEE_OTHER) : SEE_ALL;
      const saved = this._saved.get(v);
      if (want < 1) {
        if (!saved) {
          const m = v.material;
          this._saved.set(v, { transparent: m.transparent, opacity: m.opacity, depthWrite: m.depthWrite, shadows: v.meshes.map(x => x.castShadow) });
        }
        if (v.material.opacity !== want || !v.material.transparent) v.setOpacity(want);
      } else if (saved) this._restoreView(v, saved);
    }
    this._applyFurniture();
  }

  _restoreView(v, saved) {
    const m = v.material;
    m.transparent = saved.transparent; m.opacity = saved.opacity; m.depthWrite = saved.depthWrite; m.needsUpdate = true;
    v.meshes.forEach((x, i) => { x.castShadow = saved.shadows[i] ?? true; });
    if (v._syncParts) v._syncParts(true);
    this._saved.delete(v);
  }

  _furnMaterials() {
    const out = new Set();
    this.app.vp.furniture.traverse(o => { if (o.isMesh && o.material) for (const m of [].concat(o.material)) out.add(m); });
    return out;
  }

  _applyFurniture() {
    const mats = this._furnMaterials();
    if (this.seeOn) {
      for (const m of mats) {
        if (!this._savedFurn.has(m)) this._savedFurn.set(m, { opacity: m.opacity, transparent: m.transparent, depthWrite: m.depthWrite });
        const s = this._savedFurn.get(m);
        const want = Math.min(s.opacity, SEE_FURN);
        if (m.opacity !== want || !m.transparent || m.depthWrite) { m.opacity = want; m.transparent = true; m.depthWrite = false; m.needsUpdate = true; }
      }
    }
    // everything saved that is not see-through any more (see-through off, or furniture taken off the stage) gets its
    // own values back
    for (const [m, s] of [...this._savedFurn]) {
      if (this.seeOn && mats.has(m)) continue;
      m.opacity = s.opacity; m.transparent = s.transparent; m.depthWrite = s.depthWrite; m.needsUpdate = true;
      this._savedFurn.delete(m);
    }
  }

  // ---------------------------------------------------------------- bones
  setBones(on) {
    this.bonesOn = !!on;
    if (!this.bonesOn) { this._clearBones(); return; }
    this.syncViews();
    this.update();
  }

  _clearBones() {
    for (const r of this._rigs.values()) this._disposeRig(r);
    this._rigs.clear();
    this.hot = null;
  }

  _disposeRig(r) {
    for (const m of [r.bones, r.balls]) { m.removeFromParent(); m.material.dispose(); m.dispose && m.dispose(); }
  }

  // one bone set per sim view (a new view - a new body, a trial body - gets a new set)
  syncViews() {
    if (!this.bonesOn) return;
    const app = this.app;
    for (const [id, r] of [...this._rigs]) {
      const v = app.simViews.get(id);
      if (v !== r.v) { this._disposeRig(r); this._rigs.delete(id); }
    }
    _boneGeo = _boneGeo || boneGeometry();
    _ballGeo = _ballGeo || new THREE.SphereGeometry(1, 10, 8);
    for (const [id, v] of app.simViews) {
      if (this._rigs.has(id)) continue;
      const list = boneList(v);
      const color = new THREE.Color(v.color || '#ff4f9a');
      const mk = (geo, vc) => {
        const mat = new THREE.MeshBasicMaterial({ color: 0xffffff, vertexColors: vc, transparent: true, opacity: 0.85, depthTest: false, depthWrite: false });
        const m = new THREE.InstancedMesh(geo, mat, list.length);
        m.renderOrder = 12; m.frustumCulled = false; m.userData.simId = id;
        for (let i = 0; i < list.length; i++) m.setColorAt(i, color);
        return m;
      };
      const bones = mk(_boneGeo, true), balls = mk(_ballGeo, false);
      balls.material.opacity = 0.9;
      this.group.add(bones, balls);
      this._rigs.set(id, { v, list, bones, balls, color, colored: '' });
    }
    this.update();
  }

  // every frame while the bones show (from the app's tick)
  update() {
    if (!this.bonesOn) return;
    const app = this.app, sel = app.store.selected || {};
    for (const [id, r] of this._rigs) {
      const { v, list, bones, balls } = r;
      const vis = v.group.visible !== false;
      bones.visible = balls.visible = vis;
      if (!vis) continue;
      v.group.updateMatrixWorld(true);
      list.forEach((e, i) => {
        wpos(e.bone, _h);
        const t = e.tail;
        if (t.bone && v.bone(t.bone)) wpos(v.bone(t.bone), _t);
        else if (t.mid) { wpos(v.bone(t.mid[0]), _t); wpos(v.bone(t.mid[1]), _d); _t.add(_d).multiplyScalar(0.5); }
        else if (t.axis) { e.bone.matrixWorld.decompose(_s, _wq, _s); _t.set(...t.axis).applyQuaternion(_wq).multiplyScalar(t.len).add(_h); }
        else if (t.extend && v.bone(t.extend)) { wpos(v.bone(t.extend), _d); _d.subVectors(_h, _d); if (_d.lengthSq() < 1e-10) _d.set(0, 1, 0); _t.copy(_h).addScaledVector(_d.normalize(), t.len); }
        else _t.copy(_h).add(_Y.clone().multiplyScalar(0.03));
        _d.subVectors(_t, _h);
        const len = Math.max(1e-4, _d.length());
        _q.setFromUnitVectors(_Y, _d.divideScalar(len));
        const w = Math.max(0.0025, len * 0.1);
        bones.setMatrixAt(i, _m.compose(_h, _q, _s.set(w, len, w)));
        const br = Math.max(0.003, Math.min(0.012, len * 0.22));
        balls.setMatrixAt(i, _m.compose(_h, _q.identity(), _s.set(br, br, br)));
      });
      bones.instanceMatrix.needsUpdate = true;
      balls.instanceMatrix.needsUpdate = true;
      // colours: only when the selection or the hovered bone changed
      const key = `${sel.sim === id ? sel.bone : ''}|${this.hot && this.hot.simId === id ? this.hot.bone : ''}|${v.color}`;
      if (key !== r.colored) {
        r.colored = key;
        const base = new THREE.Color(v.color || '#ff4f9a');
        list.forEach((e, i) => {
          const c = this.hot && this.hot.simId === id && this.hot.bone === e.name ? HOT : sel.sim === id && sel.bone === e.name ? SEL : base;
          bones.setColorAt(i, c); balls.setColorAt(i, c);
        });
        if (bones.instanceColor) bones.instanceColor.needsUpdate = true;
        if (balls.instanceColor) balls.instanceColor.needsUpdate = true;
      }
    }
  }

  // The bone under the mouse: {simId, bone} or null.
  pick(event) {
    if (!this.bonesOn || !this._rigs.size) return null;
    const vp = this.app.vp, r = vp.canvas.getBoundingClientRect();
    vp.pointer.set(((event.clientX - r.left) / r.width) * 2 - 1, -((event.clientY - r.top) / r.height) * 2 + 1);
    vp.raycaster.setFromCamera(vp.pointer, vp.camera);
    let best = null;
    for (const [id, rig] of this._rigs) {
      if (!rig.bones.visible) continue;
      for (const m of [rig.bones, rig.balls]) {
        m.computeBoundingSphere();
        const hits = vp.raycaster.intersectObject(m, false);
        const hit = hits.find(x => x.instanceId !== undefined);
        if (hit && (!best || hit.distance < best.distance)) best = { distance: hit.distance, simId: id, bone: rig.list[hit.instanceId].name, ball: m === rig.balls };
      }
    }
    return best ? { simId: best.simId, bone: best.bone } : null;
  }

  setHot(h) {
    const same = (h && this.hot && h.simId === this.hot.simId && h.bone === this.hot.bone) || (!h && !this.hot);
    if (same) return false;
    this.hot = h;
    this.update();
    return true;
  }

  count(simId) { const r = this._rigs.get(simId); return r ? r.list.length : 0; }

  dispose() {
    this.setSeeThrough(false);
    this._clearBones();
    this.group.removeFromParent();
  }
}
