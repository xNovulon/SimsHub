// Mouse work in the 3D view: pick a body part, rotate it, drag hands/feet/hips, pin limbs, place sims - and the Face
// tool: small coloured dots bloom onto the face (brows, eyes, lids, cheeks, nostrils, lips, corners, jaw, tongue);
// click one for arrows (move) or rings (turn), T moves and R turns, each part stops at a safe range (Alt goes further),
// and a look-at ring in front of the face aims both eyes. T moves any picked part without moving the sim; the circle at
// each sim's feet (always shown, always clickable) is the whole sim.
// Hands and feet can hold on to a partner: drop one on the partner's skin in the Drag tool and it follows that body;
// drag it away to let go. Fingers, elbows, knees, the back, the neck and the head stop at natural limits (switch
// them off for special poses; Alt goes past them while dragging). "Whole back" / "Neck & head" spread one turn over
// the chain.
// Plug-in points: `pickers` (fn(event, 'down' | 'click' | 'hover') -> true when it used the event; tried before the
// bodies are picked - slot markers, bones in the see-through view, reference boards) and `attachGizmo(object3d,
// {onChange, onEnd, onStart, modes, space, size})` for anything else the gizmo should move (props, boards).
import * as THREE from 'three';
import { LIMBS, HIPS, HINGE, KNUCKLE, TURN_GROUPS, LIMB_LABEL, isHold } from './bones.js';
import { spacePos, worldToSpace, spaceToWorld, solveTwoBone, spaceQuat, setSpaceQuat, rotateInSpace, clampToLimits } from './posemath.js';
import * as K from './facekit.js';
import * as Holds from './holds.js';

const UP = new THREE.Vector3(0, 1, 0);
const ROOT_COLOR = 0xff4f9a;          // the circle at each sim's feet: the whole sim (move and turn it)
const ROOT_R = 0.075;
// T on a part that isn't a hand, a foot or the hips: the joints that bend to move it (nearest first) and where it is
// held - the joint at its far end (tip), or a point along its own length past its joint (len, metres) for an end part.
const PULL = {
  b__Spine1__: { tip: 'b__Spine2__', chain: ['b__Spine1__', 'b__Spine0__'] },
  b__Spine2__: { tip: 'b__Neck__', chain: ['b__Spine2__', 'b__Spine1__', 'b__Spine0__'] },
  b__Neck__: { tip: 'b__Head__', chain: ['b__Neck__', 'b__Spine2__'] },
  b__Head__: { len: 0.12, chain: ['b__Head__', 'b__Neck__'] },
  b__Penis_Base: { tip: 'b__Penis_Base01', chain: ['b__Penis_Base'] },
  b__Penis_Base01: { tip: 'b__Penis_Mid', chain: ['b__Penis_Base01', 'b__Penis_Base'] },
  b__Penis_Mid: { tip: 'b__Penis_Mid01', chain: ['b__Penis_Mid', 'b__Penis_Base01', 'b__Penis_Base'] },
  b__Penis_Mid01: { tip: 'b__Penis_Tip', chain: ['b__Penis_Mid01', 'b__Penis_Mid', 'b__Penis_Base01'] },
};
for (const s of ['L', 'R']) {
  const n = x => `b__${s}_${x}__`;
  PULL[n('Clavicle')] = { tip: n('UpperArm'), chain: [n('Clavicle')] };
  PULL[n('UpperArm')] = { tip: n('Forearm'), chain: [n('UpperArm')] };
  PULL[n('Thigh')] = { tip: n('Calf'), chain: [n('Thigh')] };
  PULL[n('Toe')] = { len: 0.05, chain: [n('Toe')] };
  for (const f of ['Thumb', 'Index', 'Mid', 'Ring', 'Pinky']) {
    PULL[n(f + '0')] = { tip: n(f + '1'), chain: [n(f + '0')] };
    PULL[n(f + '1')] = { tip: n(f + '2'), chain: [n(f + '1'), n(f + '0')] };
    PULL[n(f + '2')] = { len: 0.022, chain: [n(f + '2'), n(f + '1'), n(f + '0')] };
  }
}
// the limb a forearm, calf, hand or foot moves with (its hand or foot is pulled, the arm or leg follows)
const LIMB_OF = {};
for (const [limb, chain] of Object.entries(LIMBS)) for (const n of chain.slice(1)) LIMB_OF[n] = limb;
const OTHER_LIMB = { 'L hand': 'R hand', 'R hand': 'L hand', 'L foot': 'R foot', 'R foot': 'L foot' };
const FACE_NEAR = 0.9;                // the dots also show in the Pose tool when the camera is this close to a face
const FACE_STEP_NEAR = 1.6;           // ... and in the Face step on the selected sim's face (its close-up is ~0.9 m away)
const PICK_PX = 14;                   // face dots are picked in screen space (they are too small to raycast)
const easeOutBack = k => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); };
const reducedMotion = () => (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  || document.documentElement.classList.contains('reduce-motion');
let HALO = null;
function haloTexture() {
  if (HALO) return HALO;
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d'), grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,255,255,0.9)'); grad.addColorStop(0.35, 'rgba(255,255,255,0.35)'); grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
  HALO = new THREE.CanvasTexture(c);
  return HALO;
}
const _v = new THREE.Vector3(), _q = new THREE.Quaternion();

export class Interaction {
  constructor(app) {
    this.app = app;
    this.vp = app.vp;
    this.tool = 'rotate';
    this.proxy = new THREE.Object3D();
    this.vp.scene.add(this.proxy);
    this.handles = new THREE.Group();
    this.handles.renderOrder = 10;
    this.vp.overlay.add(this.handles);
    this.handleList = [];
    // the circle at each sim's feet: always drawn over everything, always the first thing a click finds
    this.roots = new THREE.Group();
    this.vp.overlay.add(this.roots);
    this.rootMeshes = new Map();   // simId -> {group, ring, fill}
    this._hotRoot = null;
    this.active = null;            // {simId, kind: 'bone'|'limb'|'hips'|'pull'|'place'|'eyes', bone?, limb?, face?}
    this.lastProxy = new THREE.Vector3();
    this.hoverSimId = null;
    // the Face tool
    this.faceOn = false;
    this.faceSimId = null;
    this.faceHandles = [];         // {mesh, halo, simId, bone, region, i}
    this.faceLines = null;
    this.eyeRings = [];
    this.eyeTarget = null;
    this.faceGizmo = {};           // the move / turn choice per bone (T)
    this.faceGroup = new THREE.Group();
    this.vp.overlay.add(this.faceGroup);
    this._faceT = 0;
    this._hotDot = null;
    this.pickers = [];             // fn(event, 'down' | 'click' | 'hover') -> true: used (tried before mesh picking)
    this.pickers.push((e, kind) => this._pickRoot(e, kind));      // first: the circles win over everything
    this.dragHold = null;          // {simId, limb}: a held limb being dragged (its hold waits until it is dropped)
    this.groupTurn = null;         // Whole back / Neck & head: the chain's turns when the drag started
    this.multi = [];               // Ctrl+click: more parts of the same sim that move with the selected one [{simId, bone}]
    this.multiStart = null;        // ...and where they were when the drag started

    const c = this.vp.canvas;
    // a press on a hand, foot or hips dot (Drag tool) drags it freely in the screen plane - before the gizmo sees the
    // press, so an arrow drawn over the dot (one pointing at the camera) can't take it
    c.addEventListener('pointerdown', e => this._dotDown(e), true);
    // a press on a sim's circle slides the whole sim over the floor (the circle wins over the gizmo too)
    c.addEventListener('pointerdown', e => this._rootDown(e), true);
    c.addEventListener('pointermove', e => { this.lastPointer = { clientX: e.clientX, clientY: e.clientY }; this._hover(e); });
    c.addEventListener('pointerleave', () => this.clearHover());
    c.addEventListener('pointerdown', e => { this.downAt = [e.clientX, e.clientY]; if (e.button === 0) this._runPickers(e, 'down'); });
    c.addEventListener('pointerup', e => {
      if (!this.downAt || this.vp.dragging) return;
      const moved = Math.hypot(e.clientX - this.downAt[0], e.clientY - this.downAt[1]);
      this.downAt = null;
      if (moved < 5 && e.button === 0) this._click(e);
    });
    const gz = this.vp.gizmo;
    gz.addEventListener('mouseDown', () => {
      // never pose while it plays: every played frame would get a key. The gizmo is only offered when paused
      // (select* pause first); this is the safety net, and the drag then starts from the paused pose.
      if (this.app.playing) {
        this.app.setPlaying(false);
        if (this.active) this.app.beginEdit(this.active.simId);
        const o = gz.object;
        if (o && gz._quaternionStart) { gz._quaternionStart.copy(o.quaternion); gz._positionStart.copy(o.position); }
      }
      this.dragFrame = Math.round(this.app.store.frame);     // the frame this drag edits
      const a0 = this.active;
      if (a0 && a0.kind === 'custom') {
        this.lastProxy.copy(this.proxy.position);
        try { a0.onStart && a0.onStart(a0.obj); } catch (err) { console.error(err); }
        return;
      }
      if (this.active) this.app.beginEdit(this.active.simId);
      this.app.store.checkpoint(); this.lastProxy.copy(this.proxy.position); this.turnStart = this.proxy.quaternion.clone();
      // turning the hips turns the whole body: remember where the upper body was
      const a = this.active;
      this.hipTurn = a && a.kind === 'bone' && a.bone === 'b__Pelvis__' ? this.beginHipTurn(this.views().get(a.simId)) : null;
      // moving the hips: the feet stay planted and the upper body keeps its place
      // (T on the hips; the Drag tool's hips dot still carries the legs along - lifting a sim, a jump)
      this.hipShift = a && a.kind === 'hips' && a.bone ? this.beginHipShift(this.views().get(a.simId)) : null;
      // a held hand being dragged: the hold waits until it is dropped (then it holds where it lands, or lets go)
      const sim = a && a.kind === 'limb' && this.app.store.sim(a.simId);
      this.dragHold = sim && isHold(sim.pins && sim.pins[a.limb]) ? { simId: a.simId, limb: a.limb } : null;
      this.groupTurn = a && a.kind === 'bone' && !a.face ? this.beginGroupTurn(this.views().get(a.simId), a.bone) : null;
      this.multiStart = a && a.kind === 'bone' && this.multi.length ? this.beginMulti(this.views().get(a.simId), a) : null;
    });
    gz.addEventListener('objectChange', () => this._gizmoChange());
    this._fadeFacingArrows(gz);
    gz.addEventListener('mouseUp', () => {
      const a = this.active;
      if (a && a.kind === 'custom') {
        try { a.onEnd && a.onEnd(a.obj); } catch (err) { console.error(err); }
        return;
      }
      this.groupTurn = null;
      this.multiStart = null;
      this.hipShift = null;
      // a hand or foot dropped on a partner (within 4 cm of the skin) holds on; a held one dragged away lets go
      if (a && a.kind === 'limb') {
        try { Holds.tryHold(this.app, a.simId, a.limb, { maxDist: 0.04, fromDrag: true, pointer: this.lastPointer }); } catch (err) { console.error('hold:', err); }
      }
      this.dragHold = null;
      this.app.afterEdit();
    });
  }

  // ---------------------------------------------------------------- dragging a dot (Drag tool)
  // The Drag tool's dot under the pointer (hands, feet, hips): within its drawn size (+4 px) on screen, the nearest.
  _dotAt(e) {
    if (this.tool !== 'ik' || !this.handleList.length) return null;
    const cam = this.vp.camera, right = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 0).normalize();
    let best = null, bd = Infinity;
    for (const x of this.handleList) {
      if (!x.mesh.visible) continue;
      const c = x.mesh.getWorldPosition(new THREE.Vector3());
      const [sx, sy, z] = this._screenOf(c);
      if (z > 1) continue;
      const g = x.mesh.geometry;
      if (!g.boundingSphere) g.computeBoundingSphere();
      const rad = (g.boundingSphere ? g.boundingSphere.radius : 0.04) * x.mesh.scale.x;
      const [ex, ey] = this._screenOf(c.clone().addScaledVector(right, rad));
      const d = Math.hypot(sx - e.clientX, sy - e.clientY), r = Math.max(8, Math.hypot(ex - sx, ey - sy) + 4);
      if (d <= r && d < bd) { bd = d; best = x; }
    }
    return best;
  }

  // A left press on a dot: it is selected and follows the pointer in the plane facing the camera (the dot wins over any
  // gizmo arrow on top of it). A press that doesn't move is an ordinary click. Alt+click still pins.
  _dotDown(e) {
    if (e.button !== 0 || e.altKey || e.ctrlKey || e.metaKey || this.vp.dragging || this.app.preview) return;
    const x = this._dotAt(e);
    if (!x) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    const c = this.vp.canvas, gz = this.vp.gizmo;
    this.downAt = [e.clientX, e.clientY];
    try { c.setPointerCapture(e.pointerId); } catch { /* not a real pointer (tests) */ }
    const drag = { x, from: [e.clientX, e.clientY], on: false, plane: null, grab: null };
    const rayAt = ev => {
      const r = c.getBoundingClientRect(), rc = new THREE.Raycaster();
      rc.setFromCamera(new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1), this.vp.camera);
      return rc.ray;
    };
    const move = ev => {
      if (ev.pointerId !== undefined && e.pointerId !== undefined && ev.pointerId !== e.pointerId) return;
      if (!drag.on) {
        if (Math.hypot(ev.clientX - drag.from[0], ev.clientY - drag.from[1]) < 4) return;
        const a = this.active;
        if (!(a && a.kind === x.kind && a.simId === x.simId && a.limb === x.limb)) { this.selectHandle(x); this.app.store.selected.sim = x.simId; }
        const n = this.vp.camera.getWorldDirection(new THREE.Vector3());
        drag.plane = new THREE.Plane().setFromNormalAndCoplanarPoint(n, this.proxy.position);
        const p0 = rayAt({ clientX: drag.from[0], clientY: drag.from[1] }).intersectPlane(drag.plane, new THREE.Vector3());
        drag.grab = p0 ? p0.sub(this.proxy.position) : new THREE.Vector3();
        drag.on = true;
        gz.dispatchEvent({ type: 'dragging-changed', value: true });
        gz.dispatchEvent({ type: 'mouseDown' });
      }
      const p = rayAt(ev).intersectPlane(drag.plane, new THREE.Vector3());
      if (!p) return;
      this.lastPointer = { clientX: ev.clientX, clientY: ev.clientY };
      this.proxy.position.copy(p.sub(drag.grab));
      gz.dispatchEvent({ type: 'objectChange' });
    };
    const up = ev => {
      c.removeEventListener('pointermove', move, true);
      c.removeEventListener('pointerup', up, true);
      c.removeEventListener('pointercancel', up, true);
      try { c.releasePointerCapture(e.pointerId); } catch { /* already released */ }
      if (!drag.on) return;                     // no move: the click that follows selects the dot
      this.lastPointer = { clientX: ev.clientX, clientY: ev.clientY };
      this.downAt = null;
      gz.dispatchEvent({ type: 'mouseUp' });
      gz.dispatchEvent({ type: 'dragging-changed', value: false });
    };
    c.addEventListener('pointermove', move, true);
    c.addEventListener('pointerup', up, true);
    c.addEventListener('pointercancel', up, true);
  }

  // ---------------------------------------------------------------- the circle at a sim's feet (the whole sim)
  // The sim whose circle is under the pointer: the circle or its inside as it looks on screen, give or take 4 px (so
  // it can still be hit when the floor is seen almost edge-on). Nothing drawn over it (a bed, a body) can hide it.
  _rootAt(e) {
    if (!this.rootMeshes.size || this.app.preview) return null;
    const shown = [...this.rootMeshes].filter(([, m]) => m.group.visible);
    if (!shown.length) return null;
    const hit = this.vp.pick(e, shown.flatMap(([, m]) => [m.ring, m.fill]));
    if (hit) {
      const f = shown.find(([, m]) => m.ring === hit.object || m.fill === hit.object);
      if (f) return f[0];
    }
    const cam = this.vp.camera, right = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 0).setY(0);
    if (right.lengthSq() < 1e-8) right.set(1, 0, 0);
    right.normalize();
    const deep = new THREE.Vector3(-right.z, 0, right.x);            // along the floor, away from / toward the camera
    let best = null, bd = Infinity;
    for (const [id, m] of shown) {
      const c = m.group.position, R = ROOT_R * m.group.scale.x;
      const [x, y, z] = this._screenOf(c);
      if (z > 1) continue;
      const [ax, ay] = this._screenOf(c.clone().addScaledVector(right, R)), [bx, by] = this._screenOf(c.clone().addScaledVector(deep, R));
      const ux = ax - x, uy = ay - y, wx = bx - x, wy = by - y, dx = e.clientX - x, dy = e.clientY - y;
      const a = Math.hypot(ux, uy) + 4, b = Math.hypot(wx, wy) + 4;
      const pu = Math.hypot(ux, uy) > 1e-6 ? (dx * ux + dy * uy) / Math.hypot(ux, uy) : 0;
      const pw = Math.hypot(wx, wy) > 1e-6 ? (dx * wx + dy * wy) / Math.hypot(wx, wy) : 0;
      const k = (pu / a) ** 2 + (pw / b) ** 2;                         // inside the (slightly grown) ellipse when <= 1
      if (k <= 1 && k < bd) { bd = k; best = id; }
    }
    return best;
  }

  _pickRoot(e, kind) {
    if (kind === 'down') return false;
    const id = this._rootAt(e);
    if (kind === 'hover') {
      this._hotRoot = id;
      if (!id) return false;
      for (const [sid, v] of this.views()) v.hover(sid === id ? 'all' : -1);
      this.vp.canvas.style.cursor = 'grab';
      this.app.setHotBone?.(null);
      const sim = this.app.store.sim(id);
      this.app.hud(`${sim ? sim.label + ' · ' : ''}the whole sim · drag to slide it`);
      return true;
    }
    if (!id) return false;
    this.selectRoot(id);
    return true;
  }

  // Pick a sim's circle: the whole sim, with arrows (T) or its turn ring (R).
  selectRoot(simId, mode = 'translate') {
    this.multi = [];
    this.app.store.selected = { sim: simId, bone: null };
    this.selectPlace(simId, mode);
    this.app.emitSelection();
    this.app.hud(mode === 'rotate' ? 'Ring: turn the whole sim' : 'Arrows: move the whole sim (R turns it)', { hold: 1400 });
  }

  // A press on a circle that then moves slides the sim over the floor (the plane of the floor, grabbed where pressed).
  // A press that doesn't move is an ordinary click (it picks the circle).
  _rootDown(e) {
    if (e.button !== 0 || e.altKey || e.ctrlKey || e.metaKey || this.vp.dragging || this.app.preview) return;
    const simId = this._rootAt(e);
    if (!simId) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    const c = this.vp.canvas, gz = this.vp.gizmo;
    this.downAt = [e.clientX, e.clientY];
    try { c.setPointerCapture(e.pointerId); } catch { /* not a real pointer (tests) */ }
    const drag = { from: [e.clientX, e.clientY], on: false, plane: null, grab: null };
    const rayAt = ev => {
      const r = c.getBoundingClientRect(), rc = new THREE.Raycaster();
      rc.setFromCamera(new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1), this.vp.camera);
      return rc.ray;
    };
    const move = ev => {
      if (ev.pointerId !== undefined && e.pointerId !== undefined && ev.pointerId !== e.pointerId) return;
      if (!drag.on) {
        if (Math.hypot(ev.clientX - drag.from[0], ev.clientY - drag.from[1]) < 4) return;
        const a = this.active;
        if (!(a && a.kind === 'place' && a.simId === simId && gz.mode === 'translate')) this.selectRoot(simId, 'translate');
        drag.plane = new THREE.Plane(UP.clone(), -this.proxy.position.y);
        const p0 = rayAt({ clientX: drag.from[0], clientY: drag.from[1] }).intersectPlane(drag.plane, new THREE.Vector3());
        drag.grab = p0 ? p0.sub(this.proxy.position) : new THREE.Vector3();
        drag.on = true;
        gz.dispatchEvent({ type: 'dragging-changed', value: true });
        gz.dispatchEvent({ type: 'mouseDown' });
      }
      const p = rayAt(ev).intersectPlane(drag.plane, new THREE.Vector3());
      if (!p) return;
      this.proxy.position.copy(p.sub(drag.grab));
      gz.dispatchEvent({ type: 'objectChange' });
    };
    const up = () => {
      c.removeEventListener('pointermove', move, true);
      c.removeEventListener('pointerup', up, true);
      c.removeEventListener('pointercancel', up, true);
      try { c.releasePointerCapture(e.pointerId); } catch { /* already released */ }
      if (!drag.on) return;                     // no move: the click that follows picks the circle
      this.downAt = null;
      gz.dispatchEvent({ type: 'mouseUp' });
      gz.dispatchEvent({ type: 'dragging-changed', value: false });
    };
    c.addEventListener('pointermove', move, true);
    c.addEventListener('pointerup', up, true);
    c.addEventListener('pointercancel', up, true);
  }

  // One circle per shown sim, kept under its hips on the floor every frame. Hidden only while a video is filmed (and
  // in the clean pictures, with the rest of the overlay).
  _syncRoots() {
    const film = !!this.app._recordingVideo;
    const seen = new Set();
    for (const [id, v] of this.views()) {
      seen.add(id);
      let m = this.rootMeshes.get(id);
      if (!m) {
        const mat = opacity => new THREE.MeshBasicMaterial({ color: ROOT_COLOR, transparent: true, opacity, depthTest: false, depthWrite: false, side: THREE.DoubleSide });
        const ring = new THREE.Mesh(new THREE.RingGeometry(ROOT_R * 0.74, ROOT_R, 48), mat(0.9));
        const fill = new THREE.Mesh(new THREE.CircleGeometry(ROOT_R * 0.74, 40), mat(0.12));
        ring.rotation.x = fill.rotation.x = -Math.PI / 2;
        ring.renderOrder = 18; fill.renderOrder = 17;
        const group = new THREE.Group();
        group.add(fill, ring);
        this.roots.add(group);
        m = { group, ring, fill };
        this.rootMeshes.set(id, m);
      }
      m.group.visible = v.group.visible && !film;
      if (!m.group.visible) continue;
      const p = v.worldPos('b__Pelvis__');
      m.group.position.set(p.x, 0.004, p.z);
      const on = this.active && this.active.kind === 'place' && this.active.simId === id;
      m.group.scale.setScalar(on ? 1.25 : this._hotRoot === id ? 1.15 : 1);
      m.fill.material.opacity = on ? 0.3 : this._hotRoot === id ? 0.22 : 0.12;
    }
    for (const [id, m] of [...this.rootMeshes]) {
      if (seen.has(id)) continue;
      m.group.traverse(o => { o.geometry?.dispose(); o.material?.dispose(); });
      m.group.removeFromParent();
      this.rootMeshes.delete(id);
    }
  }

  // Arrows (and their pickers) that point within 15 degrees of the view are hidden: seen end-on they can't be dragged
  // anyway, and they would cover the dot or the part under them.
  _fadeFacingArrows(gz) {
    const giz = gz && gz._gizmo;
    if (!giz || giz.__waFacing || typeof giz.updateMatrixWorld !== 'function') return;
    giz.__waFacing = true;
    const base = giz.updateMatrixWorld, COS = Math.cos(THREE.MathUtils.degToRad(15));
    const AX = { X: new THREE.Vector3(1, 0, 0), Y: new THREE.Vector3(0, 1, 0), Z: new THREE.Vector3(0, 0, 1) }, d = new THREE.Vector3();
    giz.updateMatrixWorld = function (force) {
      base.call(this, force);
      if ((this.mode !== 'translate' && this.mode !== 'scale') || !this.eye) return;
      for (const group of [this.picker && this.picker[this.mode], this.gizmo && this.gizmo[this.mode], this.helper && this.helper[this.mode]]) {
        if (!group) continue;
        for (const h of group.children) {
          if (!AX[h.name]) continue;
          d.copy(AX[h.name]);
          if (this.space === 'local' && this.worldQuaternion) d.applyQuaternion(this.worldQuaternion);
          if (Math.abs(d.dot(this.eye)) > COS) h.visible = false;
        }
      }
    };
  }

  // ---------------------------------------------------------------- plug-in points
  _runPickers(e, kind) {
    for (const fn of this.pickers) {
      try { if (fn(e, kind) === true) return true; } catch (err) { console.error('picker failed:', err); }
    }
    return false;
  }

  // Put the gizmo on any object (a prop, a reference board): onChange(obj) while it moves, onEnd(obj) on release,
  // onStart(obj) when a drag starts. modes: ['translate', 'rotate'] (T switches between them). Returns a detach
  // function. The whole store is not checkpointed by it - the caller decides (onStart).
  attachGizmo(obj, { onChange = null, onEnd = null, onStart = null, modes = ['translate'], space = 'world', size = 0.85 } = {}) {
    if (!obj) return () => {};
    this.pauseForEdit();
    const gz = this.vp.gizmo;
    this.active = { kind: 'custom', obj, onChange, onEnd, onStart, modes: modes.slice(), mode: 0, space, size };
    gz.setMode(modes[0] || 'translate'); gz.setSpace(space); gz.setSize(size);
    gz.showX = gz.showY = gz.showZ = true;
    gz.attach(obj);
    return () => { if (this.active && this.active.obj === obj) { gz.detach(); this.active = null; } };
  }

  views() { return this.app.simViews; }

  setTool(tool) {
    this.tool = tool;
    this.vp.gizmo.detach();
    this.active = null;
    const sel = this.app.store.selected;
    if ((tool === 'rotate' || tool === 'face' || tool === 'move') && sel.sim && sel.bone) {
      if (K.isFace(sel.bone)) this.selectFaceBone(sel.sim, sel.bone);
      else this.selectBone(sel.sim, sel.bone);
    }
    // the Move tool: the picked part's arrows, or with no part picked the sim's circle (the whole sim)
    if (tool === 'move' && sel.sim) {
      if (!sel.bone || !this.moveSelected({ quiet: true })) { sel.bone = null; this.selectPlace(sel.sim); }
    }
    this.updateFaceMode(true);
    this.refreshHandles();
    this.app.emitSelection();
  }

  // ---------------------------------------------------------------- the Face tool: when the dots show
  // On in the Face tool (the selected sim), and in the Pose tool when the camera comes close to a face. Each view
  // picks per face part (hover glow, selection tint) only while its face is being worked on.
  updateFaceMode(force = false) {
    const now = performance.now();
    if (!force && now - this._faceT < 150) return;
    this._faceT = now;
    const views = this.views();
    const cam = this.vp.camera.position;
    const headDist = v => { const b = v.bone('b__Head__'); return b ? b.getWorldPosition(_v).distanceTo(cam) : Infinity; };
    const sel = this.app.store.selected.sim;
    let faceSim = null;
    if (!this.app.preview) {
      if (this.tool === 'face') {
        faceSim = sel && views.get(sel) && views.get(sel).group.visible ? sel : null;
        if (!faceSim) for (const [id, v] of views) if (v.group.visible) { faceSim = id; break; }
      } else if (this.tool === 'rotate') {
        // only a face that looks toward the camera and is in the picture - never the back of a head. In the Face
        // step the dots belong to the selected sim (its face is the one the step is about); elsewhere the nearest
        // face close to the camera gets them, the selected sim's a little sooner.
        const faceStep = this.app.step === 'face';
        let best = Infinity;
        for (const [id, v] of views) {
          if (!v.group.visible || (faceStep && id !== sel)) continue;
          const d = headDist(v);
          if (d >= (faceStep ? FACE_STEP_NEAR : FACE_NEAR) || !this.faceSeen(v)) continue;
          const score = d - (id === sel ? 0.05 : 0);
          if (score < best) { best = score; faceSim = id; }
        }
      }
    }
    const on = !!faceSim;
    for (const [id, v] of views) {
      if (v._listHover) continue;
      K.setPickMode(v, on && (id === faceSim || (headDist(v) < FACE_NEAR && this.faceSeen(v))) ? 'face' : 'body');
    }
    if (on !== this.faceOn || faceSim !== this.faceSimId) {
      this.faceOn = on;
      this.faceSimId = faceSim;
      this._bloomT0 = now;
      this.refreshHandles();
    }
  }

  // Does the camera see this sim's face: in the picture, and the face turned toward the camera (not the back of
  // the head)? The head frame: x up, y forward (out of the face), z the sim's left.
  faceSeen(v) {
    const head = v.bone('b__Head__');
    if (!head) return false;
    const p = head.getWorldPosition(new THREE.Vector3());
    const fwd = new THREE.Vector3(0, 1, 0).applyQuaternion(head.getWorldQuaternion(_q));
    const toCam = this.vp.camera.position.clone().sub(p);
    if (toCam.lengthSq() < 1e-8 || fwd.dot(toCam.normalize()) < 0.15) return false;
    const s = p.project(this.vp.camera);
    return s.z < 1 && Math.abs(s.x) < 1.05 && Math.abs(s.y) < 1.05;
  }

  // ---------------------------------------------------------------- picking
  // What a click can land on: the bodies, and a sim's hair (its solid part - the see-through edges are left out), so a
  // click on a Tray sim's hair selects that sim (its head).
  _meshes() {
    const out = [];
    for (const [, v] of this.views()) {
      if (!v.group.visible) continue;
      out.push(...v.meshes);
      if (v.parts) for (const m of v.parts) if (!m.userData.soft && m.visible !== false) out.push(m);
    }
    return out;
  }

  _screenOf(world) {
    const p = world.clone().project(this.vp.camera), r = this.vp.canvas.getBoundingClientRect();
    return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height, p.z];
  }

  // the face dot (or the eye target) nearest the mouse, within 14 px
  _pickDot(e) {
    if (!this.faceHandles.length) return null;
    let best = null, bd = PICK_PX;
    for (const d of this.faceHandles) {
      if (!d.mesh.visible) continue;                 // a tongue dot while the mouth is shut
      const [x, y, z] = this._screenOf(d.mesh.getWorldPosition(_v));
      if (z > 1) continue;
      const dist = Math.hypot(x - e.clientX, y - e.clientY);
      if (dist < bd) { bd = dist; best = d; }
    }
    return best;
  }
  _pickEyeTarget(e) {
    const t = this.eyeTarget;
    if (!t || !t.group.visible) return false;
    const [x, y] = this._screenOf(t.group.getWorldPosition(_v));
    const [x2, y2] = this._screenOf(t.group.localToWorld(new THREE.Vector3(0.018, 0, 0)));
    return Math.hypot(x - e.clientX, y - e.clientY) < Math.max(PICK_PX, Math.hypot(x2 - x, y2 - y) + 6);
  }

  _hover(e) {
    if (this.vp.dragging || this.vp.controls.busy) return;
    const now = performance.now();
    if (now - (this._lastHover || 0) < 30) return;
    this._lastHover = now;
    if (this.pickers.length && this._runPickers(e, 'hover')) return;
    if (this.faceOn) {
      const d = this._pickDot(e);
      if (d !== this._hotDot) this._hotDot = d;
      if (d) {
        const v = this.views().get(d.simId), sim = this.app.store.sim(d.simId);
        for (const [, w] of this.views()) w.hover(w === v ? v.index(d.bone) : -1);
        this.vp.canvas.style.cursor = 'pointer';
        this.app.setHotBone?.(d.bone);
        this.app.hud(`${sim ? sim.label + ' · ' : ''}${K.label(d.bone, sim && sim.frame)} · ${d.bone} · drag · T moves, R turns`);
        return;
      }
      if (this._pickEyeTarget(e)) {
        for (const [, w] of this.views()) w.hover(-1);
        this.vp.canvas.style.cursor = 'grab';
        this.app.hud('Look-at ring · drag it and both eyes follow');
        return;
      }
    }
    if (this.tool === 'ik') {
      const h = this.vp.pick(e, this.handleList.map(x => x.mesh));
      for (const x of this.handleList) x.mesh.scale.setScalar(h && h.object === x.mesh ? 1.35 : 1);
      const x = h && this.handleList.find(y => y.mesh === h.object);
      for (const [id, v] of this.views()) v.hover(x && x.simId === id ? v.index(x.kind === 'hips' ? 'b__Pelvis__' : LIMBS[x.limb][2]) : -1);
      this.vp.canvas.style.cursor = h ? 'grab' : 'default';
      this.app.hud(x ? this.handleHint(x) : null);
      return;
    }
    const hit = this.vp.pick(e, this._meshes());
    let hoverSim = null, hoverBone = -1;
    if (hit) {
      hoverSim = hit.object.userData.sim;
      hoverBone = K.controllableIndex(hoverSim.rig, hoverSim.boneAtHit(hit), this._pickMode(hoverSim, e));
    }
    // (the Move tool picks parts too: only the circle at a sim's feet moves the whole sim)
    for (const [, v] of this.views()) v.hover(v !== hoverSim ? -1 : hoverBone);
    this.vp.canvas.style.cursor = hit ? 'pointer' : 'default';
    this.app.setHotBone?.(hit ? hoverSim.bones[hoverBone].name : null);
    this.app.hud(hit ? this.app.boneLabel(hoverSim, hoverBone) : null);
  }

  // Alt+click in the Pose / Face tool picks the exact bone (twist and helper bones too)
  _pickMode(view, e) {
    if (e && e.altKey && (this.tool === 'rotate' || this.tool === 'face')) return 'exact';
    return view.pickMode === 'face' ? 'face' : 'body';
  }

  clearHover() {
    for (const [, v] of this.views()) v.hover(-1);
    for (const x of this.handleList) x.mesh.scale.setScalar(1);
    this._hotDot = null;
    this.app.setHotBone?.(null);
    this.app.hud(null);
  }

  // The hover line for a Drag-tool handle: "Female 1 · Left hand · holding Male 1's hip (drag it away to let go)".
  handleHint(x) {
    const sim = this.app.store.sim(x.simId);
    const who = sim ? sim.label + ' · ' : '';
    if (x.kind === 'hips') return `${who}hips`;
    const pin = sim && sim.pins && sim.pins[x.limb], name = LIMB_LABEL[x.limb] || x.limb;
    if (isHold(pin)) return `${who}${name} · ${Holds.holdText(this.app, pin)} (drag it away to let go)`;
    if (pin && !Array.isArray(pin) && pin.at) return `${who}${name} · pinned from ${pin.from} to ${pin.to} (Alt+click lets go)`;
    if (pin) return `${who}${name} · pinned (Alt+click lets go)`;
    return `${who}${name} (drop it on the partner to hold on · Alt+click pins it)`;
  }

  _click(e) {
    if (this.pickers.length && this._runPickers(e, 'click')) return;
    if (this.faceOn) {
      const d = this._pickDot(e);
      if (d) {
        if (this._ctrlPick(e, d.simId, d.bone, true)) return;
        this.multi = [];
        this.app.store.selected = { sim: d.simId, bone: d.bone };
        this.selectFaceBone(d.simId, d.bone);
        this.app.emitSelection();
        return;
      }
      if (this._pickEyeTarget(e)) { this.selectEyes(this.faceSimId); return; }
    }
    if (this.tool === 'ik') {
      const h = this.vp.pick(e, this.handleList.map(x => x.mesh));
      if (h) {
        const x = this.handleList.find(y => y.mesh === h.object);
        if (e.altKey && x.kind === 'limb') return this.togglePin(x.simId, x.limb);
        return this.selectHandle(x);
      }
    }
    const hit = this.vp.pick(e, this._meshes());
    if (!hit) {
      if (this.tool !== 'move') { this.multi = []; this.vp.gizmo.detach(); this.active = null; this.app.store.selected.bone = null; this.app.emitSelection(); }
      return;
    }
    const view = hit.object.userData.sim;
    const simId = this.app.idOf(view);
    const boneIdx = K.controllableIndex(view.rig, view.boneAtHit(hit), this._pickMode(view, e));
    const name = view.bones[boneIdx].name;
    if ((this.tool === 'rotate' || this.tool === 'face') && this._ctrlPick(e, simId, name, K.isFace(name))) return;
    this.multi = [];
    this.app.store.selected = { sim: simId, bone: name };
    if (this.tool === 'rotate' || this.tool === 'face') {
      // a face part (the jaw and the tongue even in the body pick mode) gets the face gizmo
      if (K.isFace(name)) this.selectFaceBone(simId, name);
      else this.selectBone(simId, name);
    } else if (this.tool === 'move') {
      // the Move tool: that part's arrows (as T gives), never the whole sim
      if (K.isFace(name)) this.selectFaceBone(simId, name);
      else this.selectBone(simId, name);
      this.moveSelected({ quiet: true });
    } else this.refreshHandles();
    this.app.emitSelection();
  }

  // Ctrl+click on another part of the sim being posed (a body part with a body part, a face part with a face part):
  // add it to the parts that move together, or take it out again. true when the click was used that way.
  _ctrlPick(e, simId, bone, face) {
    const a = this.active;
    if (!(e.ctrlKey || e.metaKey) || !a || a.kind !== 'bone' || a.simId !== simId || !!a.face !== !!face) return false;
    const v = this.views().get(simId);
    if (!v || !v.bone(bone)) return false;
    if (bone === a.bone) return true;
    // a part the selected one hangs from would move it twice (the gizmo turns it as well): not added
    for (let p = v.bone(a.bone).parent; p; p = p.parent) if (p.name === bone) {
      this.app.hud(`${K.label(bone)} already moves ${K.label(a.bone)} - pick it first, then Ctrl+click the others`);
      return true;
    }
    const k = this.multi.findIndex(x => x.bone === bone);
    if (k >= 0) this.multi.splice(k, 1); else this.multi.push({ simId, bone });
    const n = this.multi.length + 1;
    this.app.hud(n > 1 ? `${n} parts selected - they turn and move together (Ctrl+click adds or removes one)` : `${K.label(a.bone)} selected`);
    this.placeHandles();
    return true;
  }

  // The Ctrl+click parts at the start of a drag, parents first; the selected part's own start too.
  beginMulti(v, a) {
    if (!v || !v.bone(a.bone)) return null;
    const depth = b => { let d = 0; for (let p = b.parent; p; p = p.parent) d++; return d; };
    const items = this.multi.filter(x => x.simId === a.simId && v.bone(x.bone) && x.bone !== a.bone)
      .map(x => ({ bone: x.bone, q: spaceQuat(v, v.bone(x.bone)), pos: v.bone(x.bone).position.clone(), d: depth(v.bone(x.bone)) }))
      .sort((x, y) => x.d - y.d);
    return items.length ? { q: spaceQuat(v, v.bone(a.bone)), pos: v.bone(a.bone).position.clone(), items } : null;
  }

  // The selected part moved: the others move the same way - turned by the same turn about their own joint, or moved
  // by the same step with the arrows. -> the names of the parts it changed.
  applyMulti(v, bone, M) {
    const b = v.bone(bone);
    if (this.vp.gizmo.mode === 'translate') {
      const d = b.position.clone().sub(M.pos);
      for (const it of M.items) v.bone(it.bone).position.copy(it.pos).add(d);
    } else {
      const delta = spaceQuat(v, b).multiply(M.q.clone().invert());
      for (const it of M.items) setSpaceQuat(v, v.bone(it.bone), delta.clone().multiply(it.q));
    }
    return M.items.map(it => it.bone);
  }

  // Picking something to pose stops playback first, so the pose being changed is the one on screen and the
  // playhead can't run on under the drag.
  pauseForEdit() { if (this.app.playing) this.app.setPlaying(false); }

  selectBone(simId, boneName) {
    const v = this.views().get(simId);
    if (!v || !v.bone(boneName)) return;
    this.pauseForEdit();
    const extra = K.isExtra(boneName), twist = K.isTwist(boneName);
    const move = extra && !twist && this.faceGizmo[boneName] === 'move';
    this.active = { simId, kind: 'bone', bone: boneName, extra };
    const gz = this.vp.gizmo;
    gz.setMode(move ? 'translate' : 'rotate'); gz.setSpace('local'); gz.setSize(0.85);
    if (twist) {
      // a twist helper only turns about its own length
      gz.showX = true; gz.showY = gz.showZ = false;
    } else if (extra) {
      gz.showX = gz.showY = gz.showZ = true;
    } else {
      // elbows, knees and the finger joints bend like a hinge (the game wants them turned about their own Z only):
      // only that one ring is offered. With natural limits on, the knuckles spread and curl but don't twist.
      const hinge = !!HINGE[boneName];
      gz.showX = !(hinge || (this.limitsOn() && KNUCKLE.has(boneName)));
      gz.showY = !hinge;
      gz.showZ = true;
    }
    gz.attach(v.bone(boneName));
  }

  // A face part: arrows (move) or rings (turn), only the axes it can use; Alt at the click shows every axis.
  selectFaceBone(simId, bone) {
    const v = this.views().get(simId);
    if (!v || !v.bone(bone)) return;
    this.pauseForEdit();
    const lim = K.faceLimits(bone) || { mode: 'turn', move: [1, 1, 1], turn: [1, 1, 1] };
    const mode = this.faceGizmo[bone] || lim.mode;
    const ax = mode === 'move' ? lim.move : lim.turn;
    const alt = !!this.app.altDown;
    const gz = this.vp.gizmo;
    gz.setMode(mode === 'move' ? 'translate' : 'rotate'); gz.setSpace('local'); gz.setSize(0.55);
    gz.showX = !!ax[0] || alt; gz.showY = !!ax[1] || alt; gz.showZ = !!ax[2] || alt;
    this.active = { simId, kind: 'bone', bone, face: true };
    gz.attach(v.bone(bone));
    this.placeHandles();
  }

  // T for a face or extra bone: arrows <-> rings (only when the other kind has an axis it can use).
  toggleGizmoMode() {
    const a = this.active;
    if (a && a.kind === 'custom') {
      if (a.modes.length < 2) return false;
      a.mode = (a.mode + 1) % a.modes.length;
      this.vp.gizmo.setMode(a.modes[a.mode]);
      this.app.hud(a.modes[a.mode] === 'rotate' ? 'Rings: turn it' : 'Arrows: move it');
      return true;
    }
    if (!a || a.kind !== 'bone') return false;
    if (a.face) {
      const lim = K.faceLimits(a.bone);
      if (!lim) return false;
      const cur = this.faceGizmo[a.bone] || lim.mode, other = cur === 'move' ? 'turn' : 'move';
      if (!(other === 'move' ? lim.move : lim.turn).some(Boolean)) {
        this.app.hud(`${K.label(a.bone)} only ${cur === 'move' ? 'moves' : 'turns'}`);
        return true;
      }
      this.faceGizmo[a.bone] = other;
      this.selectFaceBone(a.simId, a.bone);
      this.app.hud(other === 'move' ? 'Arrows: move it' : 'Rings: turn it');
      return true;
    }
    if (a.extra && !K.isTwist(a.bone)) {
      this.faceGizmo[a.bone] = this.faceGizmo[a.bone] === 'move' ? 'turn' : 'move';
      this.selectBone(a.simId, a.bone);
      this.app.hud(this.faceGizmo[a.bone] === 'move' ? 'Arrows: move it' : 'Rings: turn it');
      return true;
    }
    return false;
  }

  // T: arrows on the picked part - it moves, the rest of the sim stays. The hips shift with the feet planted, a hand
  // or foot (or its forearm or calf) is pulled with its arm or leg, any other part by bending the joints above it; a
  // face or extra part, a prop and the circle get their own arrows. Only the circle moves the whole sim.
  // -> true when there are arrows now.
  moveSelected({ quiet = false } = {}) {
    const a = this.active, say = (t, hold = 1400) => { if (!quiet) this.app.hud(t, { hold }); };
    if (a && a.kind === 'place') { this.selectRoot(a.simId, 'translate'); return true; }
    if (a && a.kind === 'custom') {
      const k = a.modes.indexOf('translate');
      if (k < 0) { say('This one only turns'); return false; }
      a.mode = k; this.vp.gizmo.setMode('translate'); say('Arrows: move it');
      return true;
    }
    if (a && (a.kind === 'hips' || a.kind === 'pull' || a.kind === 'limb')) return true;          // already has its arrows
    const sel = this.app.store.selected;
    const simId = a && a.simId || sel.sim, bone = a && a.kind === 'bone' ? a.bone : sel.bone;
    if (!simId || !bone) { say('Click a body part first, or the circle at a sim\'s feet to move the whole sim', 2200); return false; }
    const v = this.views().get(simId);
    if (!v || !v.bone(bone)) return false;
    const name = K.label(bone);
    if (K.isFace(bone)) {
      const lim = K.faceLimits(bone);
      if (lim && !lim.move.some(Boolean)) { say(`${name} only turns`); return false; }
      this.faceGizmo[bone] = 'move';
      this.selectFaceBone(simId, bone);
      say('Arrows: move it (R turns it)');
      return true;
    }
    if (K.isExtra(bone)) {
      if (K.isTwist(bone)) { say(`${name} only turns`); return false; }
      this.faceGizmo[bone] = 'move';
      this.selectBone(simId, bone);
      say('Arrows: move it (R turns it)');
      return true;
    }
    this.multi = [];
    if (HIPS.includes(bone)) {
      this.selectPartMove(simId, { kind: 'hips', bone });
      say('Arrows: move the hips - the feet stay, the body follows (R turns them)');
      return true;
    }
    if (LIMB_OF[bone]) {
      const limb = LIMB_OF[bone];
      this.selectPartMove(simId, { kind: 'limb', limb, bone });
      say(`Arrows: move the ${LIMB_LABEL[limb].toLowerCase()} - the ${/hand/.test(limb) ? 'arm' : 'leg'} follows (R turns it)`);
      return true;
    }
    const P = PULL[bone];
    if (!P || !P.chain.every(n => v.bone(n))) { say(`${name} only turns`); return false; }
    this.selectPartMove(simId, { kind: 'pull', bone, pull: P });
    say(`Arrows: move the ${name.toLowerCase()} (R turns it)`);
    return true;
  }

  // R: rings on the picked part (or the circle's turn ring). -> false when the caller should switch to the Pose tool
  // (a body part is then picked again with its rings).
  turnSelected() {
    const a = this.active, say = t => this.app.hud(t, { hold: 1400 });
    if (!a) return false;
    if (a.kind === 'place') { this.selectRoot(a.simId, 'rotate'); return true; }
    if (a.kind === 'custom') {
      const k = a.modes.indexOf('rotate');
      if (k < 0) { say('This one only moves'); return true; }
      a.mode = k; this.vp.gizmo.setMode('rotate'); say('Rings: turn it');
      return true;
    }
    if (a.kind !== 'bone' || this.tool === 'ik' || this.tool === 'move') return false;
    if (a.face) {
      const lim = K.faceLimits(a.bone);
      if (lim && !lim.turn.some(Boolean)) { say(`${K.label(a.bone)} only moves`); return true; }
      this.faceGizmo[a.bone] = 'turn';
      this.selectFaceBone(a.simId, a.bone);
      say('Rings: turn it (T moves it)');
      return true;
    }
    if (a.extra) { this.faceGizmo[a.bone] = 'turn'; this.selectBone(a.simId, a.bone); say('Rings: turn it (T moves it)'); return true; }
    return false;
  }

  // The picked part with arrows, moved as T says (active: {kind: 'hips' | 'limb' | 'pull', bone, limb?, pull?}).
  selectPartMove(simId, active) {
    const v = this.views().get(simId);
    if (!v) return;
    this.pauseForEdit();
    this.active = { simId, ...active };
    const at = active.kind === 'hips' ? v.worldPos('b__Pelvis__')
      : active.kind === 'limb' ? v.worldPos(LIMBS[active.limb][2]) : spaceToWorld(v, this._pullEnd(v, active.pull));
    this.proxy.position.copy(at);
    this.proxy.quaternion.identity();
    const gz = this.vp.gizmo;
    gz.setMode('translate'); gz.setSpace('world'); gz.setSize(0.75);
    gz.showX = gz.showY = gz.showZ = true;
    gz.attach(this.proxy);
  }

  // Where a pulled part is held (sim space): the joint at its far end, or a point along its own length.
  _pullEnd(v, P) {
    if (P.tip && v.bone(P.tip)) return spacePos(v, v.bone(P.tip));
    const b = v.bone(P.chain[0]), rest = v.restByName && v.restByName[b.name];
    // along the bone: the way it continues from its parent at rest, turned with it
    const dir = rest ? rest.pos.clone().applyQuaternion(rest.quat.clone().invert()) : new THREE.Vector3(1, 0, 0);
    if (dir.lengthSq() < 1e-10) dir.set(1, 0, 0);
    return spacePos(v, b).add(dir.normalize().multiplyScalar(P.len || 0.05).applyQuaternion(spaceQuat(v, b)));
  }

  // Pull a part to `target` (sim space) by turning the joints of its chain, nearest first, a little at a time so the
  // bend spreads over them (cyclic coordinate descent). Elbow-like joints only bend about their own Z. Nothing moves
  // but turns, so nothing stretches. -> true when a natural limit stopped a joint.
  _pullSolve(v, P, target) {
    const bones = P.chain.map(n => v.bone(n));
    const limits = this.limitsOn() && !this.app.altDown;
    const share = bones.length > 1 ? 0.5 : 1, id = new THREE.Quaternion();
    let hit = false;
    for (let it = 0; it < 14; it++) {
      for (const b of bones) {
        const J = spacePos(v, b);
        const from = this._pullEnd(v, P).sub(J), to = target.clone().sub(J);
        let q;
        if (HINGE[b.name]) {
          const ax = new THREE.Vector3(0, 0, 1).applyQuaternion(spaceQuat(v, b));
          from.addScaledVector(ax, -from.dot(ax)); to.addScaledVector(ax, -to.dot(ax));
          if (from.lengthSq() < 1e-10 || to.lengthSq() < 1e-10) continue;
          q = new THREE.Quaternion().setFromAxisAngle(ax, from.angleTo(to) * (Math.sign(from.clone().cross(to).dot(ax)) || 1));
        } else {
          if (from.lengthSq() < 1e-10 || to.lengthSq() < 1e-10) continue;
          q = new THREE.Quaternion().setFromUnitVectors(from.normalize(), to.normalize());
        }
        rotateInSpace(v, b, id.clone().slerp(q, share));
        if (limits && clampToLimits(v, b)) hit = true;
      }
      if (this._pullEnd(v, P).distanceToSquared(target) < 1e-8) break;
    }
    return hit;
  }

  // Moving the hips: where the feet, the neck and the head were when the drag started, and the bones it changes as
  // they were then (each step of the drag starts again from there, so nothing drifts).
  beginHipShift(v) {
    if (!v) return null;
    const feet = {};
    for (const limb of ['L foot', 'R foot']) {
      const f = v.bone(LIMBS[limb][2]);
      if (f) feet[limb] = { pos: spacePos(v, f), q: spaceQuat(v, f) };
    }
    const neck = v.bone('b__Neck__'), head = v.bone('b__Head__');
    const keep = [...HIPS, 'b__Spine1__', 'b__Spine2__', 'b__Head__', ...LIMBS['L foot'], ...LIMBS['R foot']].filter(n => v.bone(n));
    return { feet, neck: neck ? spacePos(v, neck) : null, head: head ? spaceQuat(v, head) : null, proxy0: this.proxy.position.clone(),
      start: keep.map(n => [n, v.bone(n).position.clone(), v.bone(n).quaternion.clone()]) };
  }

  // The hips moved by `d` (sim space) since the drag started, as a body does it: each foot stays where it stood (the
  // leg bends to it, and when a straight leg can't reach any more the hips drop a little), the back bends so the chest
  // and head stay where they were, and the head keeps looking the same way. A pinned foot is left to its pin.
  shiftHips(v, S, sim, d) {
    for (const [n, p, q] of S.start) { v.bone(n).position.copy(p); v.bone(n).quaternion.copy(q); }
    this.moveHips(v, d);
    const planted = Object.keys(S.feet).filter(limb => !(sim.pins && sim.pins[limb]));
    v.space.updateWorldMatrix(true, false);
    const up = UP.clone().applyQuaternion(v.space.getWorldQuaternion(new THREE.Quaternion()).invert());
    let drop = 0;
    for (const limb of planted) {
      const [a, b, c] = LIMBS[limb].map(n => v.bone(n));
      const A = spacePos(v, a), B = spacePos(v, b), L = (A.distanceTo(B) + B.distanceTo(spacePos(v, c))) * 0.999;
      const D = A.sub(S.feet[limb].pos), du = D.dot(up), c2 = D.lengthSq() - L * L;
      if (c2 <= 0) continue;
      const disc = du * du - c2;
      if (disc >= 0) drop = Math.max(drop, du - Math.sqrt(disc));
    }
    if (drop > 0) this.moveHips(v, up.clone().multiplyScalar(-drop));
    for (const limb of planted) {
      this.solveLimb(v, LIMBS[limb], S.feet[limb].pos);
      setSpaceQuat(v, v.bone(LIMBS[limb][2]), S.feet[limb].q);
    }
    const spine = ['b__Spine0__', 'b__Spine1__', 'b__Spine2__'].map(n => v.bone(n)).filter(Boolean);
    const neck = v.bone('b__Neck__');
    if (S.neck && neck && spine.length) {
      // the turn that brings the neck back over the hips, spread evenly over the back (a few passes: the joints differ)
      for (let it = 0; it < 4; it++) {
        const P0 = spacePos(v, spine[0]);
        const from = spacePos(v, neck).sub(P0), to = S.neck.clone().sub(P0);
        if (from.lengthSq() < 1e-8 || to.lengthSq() < 1e-8 || from.distanceToSquared(to) < 4e-6) break;
        const part = new THREE.Quaternion().slerp(new THREE.Quaternion().setFromUnitVectors(from.normalize(), to.normalize()), 1 / spine.length);
        for (const b of spine) rotateInSpace(v, b, part);
      }
    }
    if (S.head && v.bone('b__Head__')) setSpaceQuat(v, v.bone('b__Head__'), S.head);
    if (this.limitsOn() && !this.app.altDown) {
      let hit = false;
      for (const n of ['b__Spine0__', 'b__Spine1__', 'b__Spine2__', 'b__Neck__', 'b__Head__']) if (v.bone(n) && clampToLimits(v, v.bone(n))) hit = true;
      if (hit) this.limitHud();
    }
  }

  // The look-at ring: drag it and both eyes follow.
  selectEyes(simId) {
    const t = this.eyeTarget;
    if (!simId || !t) return;
    this.pauseForEdit();
    this.app.store.selected = { sim: simId, bone: 'b__L_Eye__' };
    this.active = { simId, kind: 'eyes' };
    this.proxy.position.copy(t.group.getWorldPosition(_v));
    this.proxy.quaternion.identity();
    const gz = this.vp.gizmo;
    gz.setMode('translate'); gz.setSpace('world'); gz.setSize(0.55);
    gz.showX = gz.showY = gz.showZ = true;
    gz.attach(this.proxy);
    this.app.emitSelection();
  }

  selectHandle(x) {
    this.pauseForEdit();
    this.app.store.selected.sim = x.simId;
    this.active = { simId: x.simId, kind: x.kind, limb: x.limb };
    this.proxy.position.copy(x.mesh.position);
    this.proxy.quaternion.identity();
    const gz = this.vp.gizmo;
    gz.setMode('translate'); gz.setSpace('world'); gz.setSize(0.85);
    gz.showX = gz.showY = gz.showZ = true;
    gz.attach(this.proxy);
    this.app.emitSelection();
  }

  selectPlace(simId, mode = 'translate') {
    const v = this.views().get(simId);
    if (!v) return;
    this.pauseForEdit();
    this.active = { simId, kind: 'place' };
    this.proxy.position.copy(v.worldPos('b__Pelvis__'));
    this.proxy.position.y = 0;
    this.proxy.quaternion.identity();
    const gz = this.vp.gizmo;
    gz.setMode(mode); gz.setSpace('world'); gz.setSize(0.85);
    gz.showX = mode === 'translate'; gz.showZ = mode === 'translate';
    gz.showY = true;
    gz.attach(this.proxy);
  }

  // ---------------------------------------------------------------- edits
  _gizmoChange() {
    const a = this.active;
    if (!a) return;
    if (a.kind === 'custom') {
      try { a.onChange && a.onChange(a.obj); } catch (err) { console.error(err); }
      return;
    }
    const sim = this.app.store.sim(a.simId), v = this.views().get(a.simId);
    if (!sim || !v) return;
    if (a.kind === 'bone') {
      if (a.face) {
        // each face part stops at its safe range (hold Alt to go further); Symmetry poses the other side too
        if (!this.app.altDown && K.clampFaceBone(v, a.bone, K.faceLimits(a.bone))) this.flashLimit(a.bone);
        if (this.multiStart) for (const n of this.applyMulti(v, a.bone, this.multiStart)) {
          if (!this.app.altDown && K.clampFaceBone(v, n, K.faceLimits(n))) this.flashLimit(n);
          if (this.app.mirrorEdit) this.app.mirrorLive(a.simId, n);
        }
        if (this.app.mirrorEdit) this.app.mirrorLive(a.simId, a.bone);
      } else {
        if (a.bone === 'b__Pelvis__' && this.hipTurn) this.applyHipTurn(v, this.hipTurn);
        const touched = [...(this.groupTurn ? this.applyGroupTurn(v, a.bone, this.groupTurn) : [a.bone])];
        if (this.multiStart) touched.push(...this.applyMulti(v, a.bone, this.multiStart));
        // fingers, elbows, knees, the back, neck and head stop at their natural limits (Alt goes past them)
        let hit = false;
        if (this.limitsOn() && !this.app.altDown) for (const n of touched) if (clampToLimits(v, v.bone(n))) hit = true;
        if (this.app.mirrorEdit) {
          this.app.mirrorLive(a.simId, a.bone);
          const m = K.mirrorName(a.bone);
          if (m !== a.bone && this.limitsOn() && !this.app.altDown && v.bone(m)) clampToLimits(v, v.bone(m));
        }
        if (hit) this.limitHud();
        this.resolvePins(sim, v);
        K.twist(this.app, { sim, v });              // the wrist follows the hand live
        this.followHolders(a.simId);
      }
      this.app.poseEdited(a.simId, true, a.face ? 'face' : 'body');
      this.placeHandles();
      return;
    }
    if (a.kind === 'eyes') {
      const p = this.proxy.position.clone();
      K.aimEye(v, 'b__L_Eye__', p);
      K.aimEye(v, 'b__R_Eye__', p);
      this.app.poseEdited(a.simId, true, 'face');
      this.placeHandles();
      return;
    }
    if (a.kind === 'limb') {
      const chain = LIMBS[a.limb];
      const target = worldToSpace(v, this.proxy.position);
      this.solveLimb(v, chain, target);
      // a pin moves with the hand; a hold waits for the drop (tryHold on release)
      const pin = sim.pins[a.limb];
      if (Array.isArray(pin)) sim.pins[a.limb] = target.toArray();
      else if (pin && pin.at) pin.at = target.toArray();
      // Symmetry: the other arm or leg does the same (unless it is pinned or holding on)
      if (this.app.mirrorEdit && !(sim.pins && sim.pins[OTHER_LIMB[a.limb]])) for (const n of chain) this.app.mirrorLive(a.simId, n);
      K.twist(this.app, { sim, v });
    } else if (a.kind === 'hips') {
      if (this.hipShift) this.shiftHips(v, this.hipShift, sim, worldToSpace(v, this.proxy.position).sub(worldToSpace(v, this.hipShift.proxy0)));
      else this.moveHips(v, worldToSpace(v, this.proxy.position).sub(worldToSpace(v, this.lastProxy)));
      this.lastProxy.copy(this.proxy.position);
      this.resolvePins(sim, v);
      K.twist(this.app, { sim, v });
      this.followHolders(a.simId);
    } else if (a.kind === 'pull') {
      if (this._pullSolve(v, a.pull, worldToSpace(v, this.proxy.position))) this.limitHud();
      if (this.app.mirrorEdit) for (const n of a.pull.chain) this.app.mirrorLive(a.simId, n);
      this.resolvePins(sim, v);
      K.twist(this.app, { sim, v });
      this.followHolders(a.simId);
    } else if (a.kind === 'place') {
      // placing moves the whole animation (every key, the pins) - no key is written at this frame
      if (this.vp.gizmo.mode === 'translate') {
        const d = worldToSpace(v, this.proxy.position).sub(worldToSpace(v, this.lastProxy));
        this.placeSim(a.simId, { move: d });
        this.lastProxy.copy(this.proxy.position);
      } else {
        const now = this.proxy.quaternion.clone();
        const delta = now.clone().multiply(this.turnStart.clone().invert());
        const ang = 2 * Math.atan2(delta.y, delta.w);
        this.placeSim(a.simId, { turn: ang, pivot: worldToSpace(v, this.proxy.position) });
        this.turnStart.copy(now);
      }
      this.app.store.dirty = true;
      this.followHolders(a.simId);
      this.placeHandles();
      return;
    }
    this.app.poseEdited(a.simId);
    this.placeHandles();
  }

  // Natural limits: on unless switched off (app.naturalLimits, remembered in the browser).
  limitsOn() { return this.app.naturalLimits !== false; }
  limitHud() {
    const now = performance.now();
    if (now - (this._limitT || 0) < 250) return;
    this._limitT = now;
    this._limitHit = (this._limitHit || 0) + 1;
    this.app.hud('Natural limit reached - switch off Natural limits for special poses (or hold Alt)', { hold: 1600 });
  }

  // Whole back / Neck & head (spec_editing 9.1): a turn of one bone of the chain is spread over the whole chain, each
  // bone by its share, so the chain adds up to the turn dialled and the head keeps its angle to the chest.
  beginGroupTurn(v, bone) {
    const g = this.app.turnGroup;
    const G = g && g !== 'none' && TURN_GROUPS[g];
    if (!v || !G || !G.bones.includes(bone) || G.bones.some(n => !v.bone(n))) return null;
    return { g, bones: G.bones, w: G.w, start: G.bones.map(n => spaceQuat(v, v.bone(n))), dragStart: spaceQuat(v, v.bone(bone)) };
  }
  applyGroupTurn(v, bone, G) {
    const delta = spaceQuat(v, v.bone(bone)).multiply(G.dragStart.clone().invert());
    if (delta.w < 0) delta.set(-delta.x, -delta.y, -delta.z, -delta.w);
    const angle = 2 * Math.acos(Math.min(1, delta.w)), s = Math.sqrt(Math.max(0, 1 - delta.w * delta.w));
    const axis = s < 1e-6 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(delta.x / s, delta.y / s, delta.z / s);
    let cum = 0;
    G.bones.forEach((n, i) => {                        // parents first
      cum += G.w[i];
      setSpaceQuat(v, v.bone(n), new THREE.Quaternion().setFromAxisAngle(axis, angle * cum).multiply(G.start[i]));
    });
    return G.bones;
  }

  // The dot flashes amber and shakes when a part reaches its safe range.
  flashLimit(bone) {
    const now = performance.now();
    const d = this.faceHandles.find(x => x.bone === bone);
    if (d && (!d.flashT || now - d.flashT > 300)) d.flashT = now;
    this._limitHit = (this._limitHit || 0) + 1;
    this.app.hud('Safe range reached - hold Alt to go further', { hold: 1600 });
  }

  // Move and/or turn a whole sim (sim space: `move` offset, `turn` radians about the vertical through `pivot`).
  // Every key, any pending pose, the pins and the view change together - otherwise the other keys stay behind
  // and pinned hands and feet stretch toward the new place. Keys hold the hips in b__ROOT_bind__'s frame (that
  // bone is always at rest), so one conversion of the change serves every key.
  placeSim(simId, { move = null, turn = 0, pivot = null } = {}) {
    const sim = this.app.store.sim(simId), v = this.views().get(simId);
    if (!sim || !v) return;
    const rb = v.bone('b__ROOT_bind__');
    const rbQ = spaceQuat(v, rb), rbP = spacePos(v, rb), toLocal = rbQ.clone().invert();
    const piv = pivot || new THREE.Vector3();
    const R = turn ? new THREE.Quaternion().setFromAxisAngle(UP, turn) : null;
    const Rl = R ? toLocal.clone().multiply(R).multiply(rbQ) : null;      // the turn, in the root's own frame
    const dl = move ? move.clone().applyQuaternion(toLocal) : null;
    const done = new Set();
    const edit = pose => {
      if (!pose || done.has(pose)) return;
      done.add(pose);
      pose.pos = pose.pos || {}; pose.rot = pose.rot || {};
      for (const n of HIPS) {
        const rest = v.restByName[n];
        const p = pose.pos[n] ? new THREE.Vector3().fromArray(pose.pos[n]) : rest.pos.clone();
        if (dl) p.add(dl);
        if (R) p.applyQuaternion(rbQ).add(rbP).sub(piv).applyQuaternion(R).add(piv).sub(rbP).applyQuaternion(toLocal);
        pose.pos[n] = p.toArray();
        if (Rl) pose.rot[n] = Rl.clone().multiply(pose.rot[n] ? new THREE.Quaternion().fromArray(pose.rot[n]) : rest.quat.clone()).normalize().toArray();
      }
    };
    for (const k of sim.keys) edit(k.pose);
    const ov = this.app.pipeline.overrides.get(simId);
    if (ov) edit(ov.pose);
    if (move) { this.moveHips(v, move); this.movePins(sim, move); }
    if (turn) { this.turnHips(v, turn, piv); this.turnPins(sim, turn, piv); }
  }

  // In the Sims rig the hips bone only carries the legs; the upper body hangs off the lower back. Turning the
  // hips should turn the whole body, so the lower back is carried along around the hips.
  beginHipTurn(v) {
    return { pelvisQ: spaceQuat(v, v.bone('b__Pelvis__')), spineQ: spaceQuat(v, v.bone('b__Spine0__')),
      spinePos: spacePos(v, v.bone('b__Spine0__')), pivot: spacePos(v, v.bone('b__Pelvis__')) };
  }

  applyHipTurn(v, t) {
    const delta = spaceQuat(v, v.bone('b__Pelvis__')).multiply(t.pelvisQ.clone().invert());
    const spine = v.bone('b__Spine0__');
    setSpaceQuat(v, spine, delta.clone().multiply(t.spineQ));
    const rb = v.bone('b__ROOT_bind__');
    const want = t.spinePos.clone().sub(t.pivot).applyQuaternion(delta).add(t.pivot);
    spine.position.copy(want.sub(spacePos(v, rb)).applyQuaternion(spaceQuat(v, rb).invert()));
  }

  solveLimb(v, chain, target) {
    const [a, b, c] = chain.map(n => v.bone(n));
    const A = spacePos(v, a), B = spacePos(v, b), C = spacePos(v, c);
    const mid = A.clone().add(C).multiplyScalar(0.5);
    const out = B.clone().sub(mid);
    const pole = out.lengthSq() > 1e-6 ? B.clone().add(out.normalize().multiplyScalar(0.4)) : null;
    solveTwoBone(v, a, b, c, target, pole);
  }

  // Pins (whole loop or part of it) and holds, while a body part is being posed: the engine's own passes, at this
  // frame, against the partner as it shows now.
  resolvePins(sim, v) {
    if (!sim.pins || !Object.keys(sim.pins).length) return;
    const pl = this.app.pipeline, e = { sim, v }, frame = Math.round(this.app.store.frame);
    pl.pins(e, frame);
    if (Object.values(sim.pins).some(isHold)) pl.holds(e, frame, pl.entries());
  }

  // While a sim is posed or placed by hand, the hands that hold on to it follow at once (the view is not
  // re-applied during a drag).
  followHolders(simId) {
    const pl = this.app.pipeline;
    let all = null;
    for (const s of this.app.store.project.sims) {
      if (s.id === simId || !s.pins || !Object.values(s.pins).some(p => isHold(p) && p.sim === simId)) continue;
      const w = this.views().get(s.id);
      if (!w) continue;
      all = all || pl.entries();
      pl.holds({ sim: s, v: w }, Math.round(this.app.store.frame), all);
      K.twist(this.app, { sim: s, v: w });
    }
  }

  // Placing a whole sim carries its pins along (a hold stays on the partner).
  movePins(sim, d) {
    for (const k of Object.keys(sim.pins || {})) {
      const p = sim.pins[k];
      if (Array.isArray(p)) sim.pins[k] = new THREE.Vector3().fromArray(p).add(d).toArray();
      else if (p && Array.isArray(p.at)) p.at = new THREE.Vector3().fromArray(p.at).add(d).toArray();
    }
  }

  turnPins(sim, ang, pivot) {
    const R = new THREE.Quaternion().setFromAxisAngle(UP, ang);
    const turn = a => new THREE.Vector3().fromArray(a).sub(pivot).applyQuaternion(R).add(pivot).toArray();
    for (const k of Object.keys(sim.pins || {})) {
      const p = sim.pins[k];
      if (Array.isArray(p)) sim.pins[k] = turn(p);
      else if (p && Array.isArray(p.at)) p.at = turn(p.at);
    }
  }

  // Both hip bones carry the sim's place; move them together (delta in sim space).
  moveHips(v, deltaSpace) {
    const rb = v.bone('b__ROOT_bind__');
    const toLocal = spaceQuat(v, rb).invert();
    const d = deltaSpace.clone().applyQuaternion(toLocal);
    for (const n of HIPS) v.bone(n).position.add(d);
  }

  turnHips(v, ang, pivot) {
    const R = new THREE.Quaternion().setFromAxisAngle(UP, ang);
    const rb = v.bone('b__ROOT_bind__');
    const rbQ = spaceQuat(v, rb), rbP = spacePos(v, rb);
    for (const n of HIPS) {
      const bone = v.bone(n);
      const p = spacePos(v, bone).sub(pivot).applyQuaternion(R).add(pivot);
      bone.position.copy(p.sub(rbP).applyQuaternion(rbQ.clone().invert()));
      setSpaceQuat(v, bone, R.clone().multiply(spaceQuat(v, bone)));
    }
  }

  // Pin a free limb where it is (the whole loop); a pinned or holding one lets go.
  togglePin(simId, limb) {
    const sim = this.app.store.sim(simId), v = this.views().get(simId);
    if (!sim || !v) return;
    this.app.store.checkpoint(sim.pins[limb] ? 'Let go' : 'Pin');
    const was = sim.pins[limb];
    if (was) delete sim.pins[limb];
    else sim.pins[limb] = spacePos(v, v.bone(LIMBS[limb][2])).toArray();
    if (isHold(was)) this.app.applyPoses(false);
    this.refreshHandles();
    this.app.afterEdit();
    this.app.emitSelection();
    if (isHold(was)) this.app.hud(`${LIMB_LABEL[limb]} let go.`, { hold: 1400 });
  }

  // Holds (spec_bodies 4.5): drop on the nearest partner, re-find after a mirror, pin for part of the loop.
  tryHold(simId, limb, opts) { return Holds.tryHold(this.app, simId, limb, opts); }
  rebindHold(simId, limb) { return Holds.rebindHold(this.app, simId, limb); }
  setPin(simId, limb, opts) { return Holds.setPin(this.app, simId, limb, opts); }

  // ---------------------------------------------------------------- handles
  refreshHandles() {
    // the pin ring is a child of its handle: free both
    for (const x of this.handleList) x.mesh.traverse(o => { o.geometry?.dispose(); o.material?.dispose(); });
    this.handles.clear();
    this.handleList = [];
    this._clearFace();
    if (this.faceOn) this._buildFace();
    if (this.tool === 'ik') {
      for (const [id, v] of this.views()) {
        const sim = this.app.store.sim(id);
        if (!sim || !v.group.visible) continue;
        const add = (kind, limb) => {
          const pin = kind === 'limb' && sim.pins[limb];
          const pinned = !!pin;
          // a held hand: the partner's colour with a ring in the holder's; a pin for part of the loop: a dashed ring
          const partner = isHold(pin) && this.app.store.sim(pin.sim);
          const geo = kind === 'hips' ? new THREE.OctahedronGeometry(0.055) : new THREE.SphereGeometry(pinned ? 0.042 : 0.036, 20, 14);
          const mat = new THREE.MeshBasicMaterial({ color: partner ? partner.color : pinned ? 0xffffff : sim.color, depthTest: false, transparent: true, opacity: 0.92 });
          const mesh = new THREE.Mesh(geo, mat);
          mesh.renderOrder = 20;
          if (pinned) {
            let ring;
            if (pin && !Array.isArray(pin) && pin.from !== undefined) {
              const pts = [];
              for (let k = 0; k <= 48; k++) { const t = k / 48 * Math.PI * 2; pts.push(new THREE.Vector3(Math.cos(t) * 0.06, Math.sin(t) * 0.06, 0)); }
              ring = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineDashedMaterial({ color: sim.color, dashSize: 0.018, gapSize: 0.012, depthTest: false }));
              ring.computeLineDistances();
            } else {
              ring = new THREE.Mesh(new THREE.TorusGeometry(0.06, 0.008, 8, 28), new THREE.MeshBasicMaterial({ color: sim.color, depthTest: false }));
            }
            ring.renderOrder = 21;
            mesh.add(ring);
          }
          this.handles.add(mesh);
          this.handleList.push({ mesh, simId: id, kind, limb });
        };
        add('hips');
        for (const limb of Object.keys(LIMBS)) add('limb', limb);
      }
    }
    this.placeHandles();
  }

  _clearFace() {
    // (materials never free the shared halo texture: that stays for the next time)
    const gone = new Set();
    this.faceGroup.traverse(o => { if (o !== this.faceGroup) { if (o.geometry) gone.add(o.geometry); if (o.material) gone.add(o.material); } });
    for (const x of gone) x.dispose();
    this.faceGroup.clear();
    this.faceHandles = [];
    this.faceLines = null;
    this.eyeRings = [];
    this.eyeTarget = null;
    this._hotDot = null;
  }

  // The dots on one face, the guide lines (brows, the lip loop, a thin ring around each eye) and the look-at ring.
  _buildFace() {
    const v = this.views().get(this.faceSimId);
    if (!v || !v.group.visible) return;
    const order = K.REGIONS;
    const bones = K.FACE_CHANNEL.filter(n => v.bone(n) && K.faceRegion(n))
      .map((n, i) => ({ n, i, r: order.indexOf(K.faceRegion(n)) })).sort((a, b) => a.r - b.r || a.i - b.i).map(x => x.n);
    const geo = new THREE.SphereGeometry(0.0032, 14, 10);
    bones.forEach((n, i) => {
      const region = K.faceRegion(n), color = new THREE.Color(K.regionColor(region));
      const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, depthTest: false, transparent: true }));
      mesh.renderOrder = 22;
      const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: haloTexture(), color, blending: THREE.AdditiveBlending, depthTest: false, transparent: true, opacity: 0.85 }));
      halo.scale.setScalar(0.0032 * 2 * 2.4);
      halo.renderOrder = 21;
      mesh.add(halo);
      mesh.scale.setScalar(reducedMotion() ? 1 : 0.0001);
      this.faceGroup.add(mesh);
      this.faceHandles.push({ mesh, halo, simId: this.faceSimId, bone: n, region, i, color, tongue: /Tounge/.test(n) });
    });
    // guide lines, 35% of the region colour
    const pairs = K.FACE_LINES.filter(([a, b]) => v.bone(a) && v.bone(b));
    if (pairs.length) {
      const g = new THREE.BufferGeometry();
      const pos = new Float32Array(pairs.length * 6), col = new Float32Array(pairs.length * 6);
      pairs.forEach(([a], k) => { const c = new THREE.Color(K.regionColor(K.faceRegion(a))); col.set([c.r, c.g, c.b, c.r, c.g, c.b], k * 6); });
      g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      g.setAttribute('color', new THREE.BufferAttribute(col, 3));
      const lines = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.35, depthTest: false }));
      lines.renderOrder = 20;
      lines.frustumCulled = false;
      lines.userData.pairs = pairs;
      this.faceGroup.add(lines);
      this.faceLines = lines;
    }
    for (const eye of ['b__L_Eye__', 'b__R_Eye__']) {
      if (!v.bone(eye)) continue;
      const pts = [];
      for (let k = 0; k < 32; k++) { const a = k / 32 * Math.PI * 2; pts.push(new THREE.Vector3(Math.cos(a) * 0.014, 0, Math.sin(a) * 0.014)); }
      const ring = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineBasicMaterial({ color: K.regionColor('eyes'), transparent: true, opacity: 0.35, depthTest: false }));
      ring.renderOrder = 20;
      ring.userData.eye = eye;
      this.faceGroup.add(ring);
      this.eyeRings.push(ring);
    }
    if (v.bone('b__L_Eye__') && v.bone('b__R_Eye__')) {
      const group = new THREE.Group();
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.018, 0.0025, 8, 40), new THREE.MeshBasicMaterial({ color: K.regionColor('eyes'), depthTest: false, transparent: true, opacity: 0.9 }));
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.004, 12, 8), new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false, transparent: true, opacity: 0.9 }));
      ring.renderOrder = dot.renderOrder = 22;
      group.add(ring, dot);
      this.faceGroup.add(group);
      this.eyeTarget = { group, ring, dot };
    }
  }

  placeHandles() {
    for (const x of this.handleList) {
      const v = this.views().get(x.simId);
      if (!v) continue;
      const bone = x.kind === 'hips' ? 'b__Pelvis__' : LIMBS[x.limb][2];
      x.mesh.position.copy(v.worldPos(bone));             // brings just that bone's chain up to date
      if (this.active && this.active.kind === x.kind && this.active.simId === x.simId && this.active.limb === x.limb && !this.vp.dragging) {
        this.proxy.position.copy(x.mesh.position);
      }
      x.mesh.children.forEach(r => r.lookAt(this.vp.camera.position));
    }
    this._syncRoots();
    // the arrows stay on the part being moved (or the circle) while it plays, is scrubbed or undone
    const a = this.active, v = a && a.simId && this.views().get(a.simId);
    if (v && !this.vp.dragging) {
      if (a.kind === 'place') { const m = this.rootMeshes.get(a.simId); if (m) this.proxy.position.set(m.group.position.x, 0, m.group.position.z); }
      else if (a.kind === 'hips' && a.bone) this.proxy.position.copy(v.worldPos('b__Pelvis__'));
      else if (a.kind === 'limb' && a.bone) this.proxy.position.copy(v.worldPos(LIMBS[a.limb][2]));
      else if (a.kind === 'pull') this.proxy.position.copy(spaceToWorld(v, this._pullEnd(v, a.pull)));
    }
    if (this.faceHandles.length) this._placeFace();
  }

  // Is the mouth shut? (the jaw within 5 degrees of rest and the tongue not pushed out - sliders, talking and posed
  // keys all count, since this reads the bones as shown)
  _mouthShut(v) {
    const jaw = v.bone('b__Jaw__'), r = v.restByName && v.restByName.b__Jaw__;
    if (!jaw || !r) return false;
    const open = 2 * Math.acos(Math.min(1, Math.abs(jaw.quaternion.dot(r.quat))));
    if (open > THREE.MathUtils.degToRad(5)) return false;
    const t = v.bone('b__Tounge__1'), tr = v.restByName.b__Tounge__1;
    return !(t && tr && t.position.distanceTo(tr.pos) > 0.006);
  }

  _placeFace() {
    const v = this.views().get(this.faceSimId);
    if (!v) return;
    v.group.updateMatrixWorld(true);
    const cam = this.vp.camera.position;
    const head = v.bone('b__Head__');
    const headPos = head.getWorldPosition(new THREE.Vector3());
    const headQ = head.getWorldQuaternion(new THREE.Quaternion());
    const fwd = new THREE.Vector3(0, 1, 0).applyQuaternion(headQ);          // the head frame: x up, y forward, z left
    const away = fwd.dot(cam.clone().sub(headPos)) < 0;
    const s = THREE.MathUtils.clamp(cam.distanceTo(headPos) / 0.6, 0.6, 3);
    const now = performance.now(), still = reducedMotion();
    const sel = this.app.store.selected, selBone = sel.sim === this.faceSimId ? sel.bone : null;
    // the tongue dots sit inside the mouth: they fade out while it is shut (unless the tongue is the selected part)
    const shut = this._mouthShut(v);
    const at = {};
    for (const d of this.faceHandles) {
      const b = v.bone(d.bone);
      const p = b.localToWorld(K.faceHandlePoint(v, d.bone).clone());
      at[d.bone] = p;
      const k = still ? 1 : THREE.MathUtils.clamp((now - (this._bloomT0 || 0) - 18 * d.i) / 240, 0, 1);
      let sc = s * (still ? 1 : Math.max(0.0001, easeOutBack(k)));
      if (d === this._hotDot) sc *= 1.5;
      const flashing = d.flashT && now - d.flashT < 300;
      if (flashing && !still) {
        // a 3-frame shake, sideways on screen
        const f = Math.floor((now - d.flashT) / 16) % 3;
        const side = new THREE.Vector3().crossVectors(fwd, cam.clone().sub(p)).normalize().multiplyScalar((f - 1) * 0.0012 * s);
        p.add(side);
      }
      d.mesh.position.copy(p);
      d.mesh.scale.setScalar(sc);
      d.mesh.material.color.set(flashing ? '#fbbf24' : d.color);
      d.halo.material.color.set(flashing ? '#fbbf24' : d.color);
      let show = 1;
      if (d.tongue) {
        const want = shut && d.bone !== selBone ? 0 : 1;
        d.fade = still ? want : (d.fade ?? want) + (want - (d.fade ?? want)) * 0.25;
        if (Math.abs(d.fade - want) < 0.02) d.fade = want;
        show = d.fade;
        d.mesh.visible = show > 0.02;
      }
      d.mesh.material.opacity = (away ? 0.25 : 1) * show;
      d.halo.material.opacity = (away ? 0.2 : 0.85) * show;
      const pulse = d.bone === selBone && !still ? 1 + 0.125 * (1 + Math.sin(now / 1000 * Math.PI * 2 * 1.4)) : 1;
      d.halo.scale.setScalar(0.0032 * 2 * 2.4 * pulse * (d.bone === selBone ? 1.35 : 1));
    }
    if (this.faceLines) {
      const a = this.faceLines.geometry.attributes.position;
      this.faceLines.userData.pairs.forEach(([p0, p1], k) => {
        const A = at[p0] || v.bone(p0).getWorldPosition(new THREE.Vector3()), B = at[p1] || v.bone(p1).getWorldPosition(new THREE.Vector3());
        a.setXYZ(k * 2, A.x, A.y, A.z); a.setXYZ(k * 2 + 1, B.x, B.y, B.z);
      });
      a.needsUpdate = true;
      this.faceLines.material.opacity = away ? 0.12 : 0.35;
    }
    for (const ring of this.eyeRings) {
      const p = at[ring.userData.eye] || v.bone(ring.userData.eye).getWorldPosition(new THREE.Vector3());
      ring.position.copy(p);
      ring.quaternion.copy(v.bone(ring.userData.eye).parent.getWorldQuaternion(_q));   // in the face's plane (x up, z left)
      ring.scale.setScalar(Math.max(1, s * 0.8));
    }
    const t = this.eyeTarget;
    if (t) {
      const dragging = this.active && this.active.kind === 'eyes' && this.vp.dragging;
      if (dragging) t.group.position.copy(this.proxy.position);
      else {
        // 0.35 m out along where the eyes look now
        const L = v.bone('b__L_Eye__'), R = v.bone('b__R_Eye__');
        const mid = L.getWorldPosition(new THREE.Vector3()).add(R.getWorldPosition(new THREE.Vector3())).multiplyScalar(0.5);
        const gaze = new THREE.Vector3(0, 1, 0).applyQuaternion(L.getWorldQuaternion(new THREE.Quaternion()))
          .add(new THREE.Vector3(0, 1, 0).applyQuaternion(R.getWorldQuaternion(new THREE.Quaternion()))).normalize();
        t.group.position.copy(mid.addScaledVector(gaze.lengthSq() > 0.5 ? gaze : fwd, 0.35));
        if (this.active && this.active.kind === 'eyes') this.proxy.position.copy(t.group.position);
      }
      t.group.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), fwd);
      t.group.scale.setScalar(Math.max(1, s * 0.7));
      t.group.visible = !away;
    }
  }
}
