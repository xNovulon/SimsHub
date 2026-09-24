// Roblox Studio style camera.
//   W A S D   fly forward / left / back / right (where you look)     Q / E   down / up
//   Shift     slower, for fine framing                                  wheel   move in / out
//   right-drag  look around (360°)                                      middle-drag  slide the view
// The left button is never used, so clicking always picks body parts.
import * as THREE from 'three';

const MOVE_KEYS = { KeyW: 'f', KeyS: 'b', KeyA: 'l', KeyD: 'r', KeyE: 'u', KeyQ: 'd' };
const LOOK = 0.0035;           // radians per pixel of mouse movement
const SPEED = 2.4, SLOW = 0.28; // metres per second; Shift multiplies by SLOW

export class FlyControls {
  constructor(camera, dom, target) {
    this.camera = camera;
    this.dom = dom;
    this.enabled = true;
    this.keys = new Set();
    this.shift = false;
    this.vel = new THREE.Vector3();
    this.euler = new THREE.Euler(0, 0, 0, 'YXZ');
    this.focus = 3;             // how far ahead the focus point is (used by F, views and the wheel)
    this.looking = false;
    this.panning = false;
    this.lookFrom(camera.position.clone(), target);

    dom.addEventListener('contextmenu', e => e.preventDefault());
    dom.addEventListener('pointerdown', e => this._down(e));
    window.addEventListener('pointermove', e => this._move(e));
    window.addEventListener('pointerup', e => this._up(e));
    dom.addEventListener('wheel', e => this._wheel(e), { passive: false });
    window.addEventListener('keydown', e => this._key(e, true));
    window.addEventListener('keyup', e => this._key(e, false));
    window.addEventListener('blur', () => { this.keys.clear(); this.shift = false; this._stopLook(); });
  }

  // Busy = the user is steering the camera right now (hover picking and camera animations wait).
  get busy() { return this.looking || this.panning || this.keys.size > 0; }

  get target() {
    return this.camera.position.clone().add(this._forward().multiplyScalar(this.focus));
  }

  // roll: a tilt of the picture (radians, about the view direction). Only the Face step uses it, to show a lying
  // sim's face upright; the camera levels itself again as soon as you look around.
  lookFrom(position, target, roll = 0) {
    this.camera.position.copy(position);
    const d = target.clone().sub(position);
    this.focus = Math.max(0.3, d.length());
    d.normalize();
    this.euler.set(Math.asin(THREE.MathUtils.clamp(d.y, -1, 1)), Math.atan2(-d.x, -d.z), roll, 'YXZ');
    this._apply();
  }

  get roll() { return this.euler.z; }

  _forward() { return new THREE.Vector3(0, 0, -1).applyQuaternion(this.camera.quaternion); }

  _apply() {
    const lim = Math.PI / 2 - 0.001;
    this.euler.x = THREE.MathUtils.clamp(this.euler.x, -lim, lim);
    this.camera.quaternion.setFromEuler(this.euler);
  }

  _down(e) {
    if (!this.enabled) return;
    if (e.button === 2) {
      this.looking = true;
      this._lookStart = [e.clientX, e.clientY];
      this._locked = false;
      this.dom.setPointerCapture?.(e.pointerId);
    } else if (e.button === 1) {
      e.preventDefault();
      this.panning = true;
      this.dom.setPointerCapture?.(e.pointerId);
    }
  }

  _move(e) {
    if (this.looking) {
      // hide and lock the cursor once it really is a drag, so you can keep turning all the way round
      if (!this._locked && Math.hypot(e.clientX - this._lookStart[0], e.clientY - this._lookStart[1]) > 3) {
        this._locked = true;
        try { const r = this.dom.requestPointerLock?.(); r && r.catch && r.catch(() => {}); } catch { /* not allowed here */ }
        this.dom.style.cursor = 'none';
      }
      this.euler.y -= e.movementX * LOOK;
      this.euler.x -= e.movementY * LOOK;
      // a tilted picture (Face step) straightens out while you turn, so looking around feels normal
      if (this.euler.z) this.euler.z = Math.abs(this.euler.z) < 0.01 ? 0 : this.euler.z * 0.9;
      this._apply();
    } else if (this.panning) {
      const k = Math.max(0.4, this.focus) * 0.0016;
      const right = new THREE.Vector3(1, 0, 0).applyQuaternion(this.camera.quaternion);
      const up = new THREE.Vector3(0, 1, 0).applyQuaternion(this.camera.quaternion);
      this.camera.position.addScaledVector(right, -e.movementX * k).addScaledVector(up, e.movementY * k);
    }
  }

  _up(e) {
    if (e.button === 2) this._stopLook();
    if (e.button === 1) this.panning = false;
  }

  _stopLook() {
    this.looking = false;
    if (document.pointerLockElement === this.dom) document.exitPointerLock();
    this.dom.style.cursor = '';
  }

  _wheel(e) {
    e.preventDefault();
    if (!this.enabled) return;
    const step = -Math.sign(e.deltaY) * Math.min(1.5, Math.abs(e.deltaY) / 100) * 0.35 * (e.shiftKey ? SLOW : 1) * Math.max(0.5, this.focus / 3);
    this.camera.position.addScaledVector(this._forward(), step);
    this.focus = Math.max(0.3, this.focus - step);
  }

  _key(e, down) {
    this.shift = e.shiftKey;
    if (e.key === 'Shift') return;
    const dir = MOVE_KEYS[e.code];
    if (!dir) return;
    if (down) {
      if (e.ctrlKey || e.metaKey || e.altKey || e.target.matches?.('input:not([type=range]):not([type=checkbox]), select, textarea, [contenteditable]')) return;
      if (document.querySelector('.backdrop:not(.leaving), .palette-back')) return;   // a dialog or the palette is open
      // Home (or the first-run tour) covers the stage: the hidden camera must not wander off meanwhile
      const home = document.getElementById('home');
      if ((home && !home.classList.contains('hidden')) || document.getElementById('tour-root')?.childElementCount) return;
      this.keys.add(dir);
      e.preventDefault();
    } else {
      this.keys.delete(dir);
    }
  }

  update(dt) {
    dt = Math.min(dt, 0.05);
    const want = new THREE.Vector3();
    if (this.enabled && this.keys.size) {
      const f = this._forward(), r = new THREE.Vector3(1, 0, 0).applyQuaternion(this.camera.quaternion);
      if (this.keys.has('f')) want.add(f);
      if (this.keys.has('b')) want.sub(f);
      if (this.keys.has('r')) want.add(r);
      if (this.keys.has('l')) want.sub(r);
      if (this.keys.has('u')) want.y += 1;
      if (this.keys.has('d')) want.y -= 1;
      if (want.lengthSq()) want.normalize().multiplyScalar(SPEED * (this.shift ? SLOW : 1));
    }
    // quick ease in and out so flying feels smooth, not jerky
    this.vel.lerp(want, 1 - Math.exp(-dt * 14));
    if (this.vel.lengthSq() < 1e-7) { this.vel.set(0, 0, 0); return; }
    this.camera.position.addScaledVector(this.vel, dt);
  }
}
