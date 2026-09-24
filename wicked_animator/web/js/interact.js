// Mouse work in the 3D view: pick a body part, rotate it, drag hands/feet/hips, pin limbs, place sims - and the Face
// tool: small coloured dots bloom onto the face (brows, eyes, lids, cheeks, nostrils, lips, corners, jaw, tongue);
// click one for arrows (move) or rings (turn), T switches, each part stops at a safe range (Alt goes further), and
// a look-at ring in front of the face aims both eyes.
// Hands and feet can hold on to a partner: drop one on the partner's skin in the Drag tool and it follows that body;
// drag it away to let go. Fingers, elbows, knees, the back, the neck and the head stop at natural limits (switch
// them off for special poses; Alt goes past them while dragging). "Whole back" / "Neck & head" spread one turn over
// the chain.
// Plug-in points: `pickers` (fn(event, 'down' | 'click' | 'hover') -> true when it used the event; tried before the
// bodies are picked - slot markers, bones in the see-through view, reference boards) and `attachGizmo(object3d,
// {onChange, onEnd, onStart, modes, space, size})` for anything else the gizmo should move (props, boards).
import * as THREE from 'three';
import { LIMBS, HIPS, HINGE, KNUCKLE, TURN_GROUPS, LIMB_LABEL, isHold } from './bones.js';
import { spacePos, worldToSpace, spaceToWorld, solveTwoBone, spaceQuat, setSpaceQuat, clampToLimits } from './posemath.js';
import * as K from './facekit.js';
import * as Holds from './holds.js';

const UP = new THREE.Vector3(0, 1, 0);
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
    this.active = null;            // {simId, kind: 'bone'|'limb'|'hips'|'place'|'eyes', bone?, limb?, face?}
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
    this.dragHold = null;          // {simId, limb}: a held limb being dragged (its hold waits until it is dropped)
    this.groupTurn = null;         // Whole back / Neck & head: the chain's turns when the drag started

    const c = this.vp.canvas;
    // a press on a hand, foot or hips dot (Drag tool) drags it freely in the screen plane - before the gizmo sees the
    // press, so an arrow drawn over the dot (one pointing at the camera) can't take it
    c.addEventListener('pointerdown', e => this._dotDown(e), true);
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
      // a held hand being dragged: the hold waits until it is dropped (then it holds where it lands, or lets go)
      const sim = a && a.kind === 'limb' && this.app.store.sim(a.simId);
      this.dragHold = sim && isHold(sim.pins && sim.pins[a.limb]) ? { simId: a.simId, limb: a.limb } : null;
      this.groupTurn = a && a.kind === 'bone' && !a.face ? this.beginGroupTurn(this.views().get(a.simId), a.bone) : null;
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
    if ((tool === 'rotate' || tool === 'face') && sel.sim && sel.bone) {
      if (K.isFace(sel.bone)) this.selectFaceBone(sel.sim, sel.bone);
      else this.selectBone(sel.sim, sel.bone);
    }
    if (tool === 'move' && sel.sim) this.selectPlace(sel.sim);
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
        this.app.hud(`${sim ? sim.label + ' · ' : ''}${K.label(d.bone, sim && sim.frame)} · ${d.bone} · drag · T move/turn`);
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
    for (const [, v] of this.views()) v.hover(v !== hoverSim ? -1 : this.tool === 'move' ? 'all' : hoverBone);
    this.vp.canvas.style.cursor = hit ? 'pointer' : 'default';
    this.app.setHotBone?.(hit && this.tool !== 'move' ? hoverSim.bones[hoverBone].name : null);
    this.app.hud(hit ? (this.tool === 'move' ? `${this.app.store.sim(this.app.idOf(hoverSim))?.label || 'Sim'} · click to place` : this.app.boneLabel(hoverSim, hoverBone)) : null);
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
      if (this.tool !== 'move') { this.vp.gizmo.detach(); this.active = null; this.app.store.selected.bone = null; this.app.emitSelection(); }
      return;
    }
    const view = hit.object.userData.sim;
    const simId = this.app.idOf(view);
    const boneIdx = K.controllableIndex(view.rig, view.boneAtHit(hit), this._pickMode(view, e));
    const name = view.bones[boneIdx].name;
    this.app.store.selected = { sim: simId, bone: name };
    if (this.tool === 'rotate' || this.tool === 'face') {
      // a face part (the jaw and the tongue even in the body pick mode) gets the face gizmo
      if (K.isFace(name)) this.selectFaceBone(simId, name);
      else this.selectBone(simId, name);
    } else if (this.tool === 'move') this.selectPlace(simId);
    else this.refreshHandles();
    this.app.emitSelection();
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
        if (this.app.mirrorEdit) this.app.mirrorLive(a.simId, a.bone);
      } else {
        if (a.bone === 'b__Pelvis__' && this.hipTurn) this.applyHipTurn(v, this.hipTurn);
        const touched = this.groupTurn ? this.applyGroupTurn(v, a.bone, this.groupTurn) : [a.bone];
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
      K.twist(this.app, { sim, v });
    } else if (a.kind === 'hips') {
      const d = worldToSpace(v, this.proxy.position).sub(worldToSpace(v, this.lastProxy));
      this.moveHips(v, d);
      this.lastProxy.copy(this.proxy.position);
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
