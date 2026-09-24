// The 3D view: renderer, studio stage, lights, camera, picking, gizmos, motion trails.
// The look (dome, grid, lighting looks, cinematic passes) comes from stage.js; adaptive quality steps down when
// frames get slow and says so with a "Fast mode" chip (see polish.js).
import * as THREE from 'three';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { FlyControls } from './flycam.js';
import { installStage } from './stage.js';
import { $t } from './i18n.js';

export class Viewport {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.08;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x241a2f);
    // the fog colour is the dome's horizon colour (stage.js), so the floor's far edge melts into the backdrop
    this.scene.fog = new THREE.Fog(0x241a2f, 5.5, 15);
    this.camera = new THREE.PerspectiveCamera(36, 1, 0.03, 80);
    this.camera.position.set(2.4, 1.7, 3.4);

    // Roblox Studio camera: WASD fly (Q/E down/up, Shift slower), right-drag looks around, wheel moves in and out.
    // The left button never moves the camera - it picks body parts.
    this.controls = new FlyControls(this.camera, canvas, new THREE.Vector3(0, 0.85, 0));

    this._stage();
    this._lights();

    this.furniture = new THREE.Group();
    this.scene.add(this.furniture);
    this.sims = new THREE.Group();
    this.scene.add(this.sims);
    this.overlay = new THREE.Group();           // handles and trails drawn on top
    this.scene.add(this.overlay);

    this.gizmo = new TransformControls(this.camera, canvas);
    this.gizmo.setSize(0.85);
    this.gizmo.addEventListener('dragging-changed', e => { this.controls.enabled = !e.value; this.dragging = e.value; });
    this.scene.add(this.gizmo);

    // soft ambient occlusion where bodies touch each other and the floor
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    try {
      this.ao = new GTAOPass(this.scene, this.camera, 1, 1);
      this.ao.updateGtaoMaterial({ radius: 0.28, distanceExponent: 1.6, thickness: 1.2, scale: 1.1, samples: 12 });
      this.ao.blendIntensity = 0.85;
      // overlays never cast ambient occlusion: GTAO draws every visible object into its depth/normal pass and
      // leaves out only points and lines, so the face dots' glow sprites showed as dark squares close up
      if (typeof this.ao.overrideVisibility === 'function') {
        const hideOverlays = this.ao.overrideVisibility.bind(this.ao);
        this.ao.overrideVisibility = () => {
          hideOverlays();
          this.scene.traverse(o => {
            if (!o.visible) return;
            const mats = Array.isArray(o.material) ? o.material : [o.material];
            if (o.isSprite || o.userData.noAO || mats.some(m => m && m.depthTest === false)) o.visible = false;
          });
        };
      }
      this.composer.addPass(this.ao);
    } catch (e) { console.warn('ambient occlusion unavailable', e); }
    this.composer.addPass(new OutputPass());

    this.quality = 'full';
    this._qLevel = 0;              // adaptive quality: 0 full, 1 no cinematic bloom, 2 fewer AO samples, 3 fast
    this._ft = 16; this._slow = 0;
    this.onQuality = null;         // fn(level, text, auto) - the "Fast mode" chip

    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.onFrame = [];
    // the studio look: dome, fading grid, lighting looks, cinematic passes
    try { this.stage = installStage(this); } catch (e) { console.error('stage', e); this.stage = null; }
    this._resize = this._resize.bind(this);
    new ResizeObserver(this._resize).observe(canvas.parentElement);
    this._resize();
    this._loop = this._loop.bind(this);
    this.clock = new THREE.Clock();
    requestAnimationFrame(this._loop);
  }

  _stage() {
    // a round studio floor, 40 m across so its edge is always deep inside the fog (no hard horizon); the lit
    // centre and the 1 m grid come from stage.js
    const size = 40;
    const tex = (() => {
      const c = document.createElement('canvas'); c.width = c.height = 512;
      const g = c.getContext('2d');
      const grad = g.createRadialGradient(256, 256, 20, 256, 256, 256);
      grad.addColorStop(0, '#3a3046'); grad.addColorStop(0.45, '#241d2d'); grad.addColorStop(1, '#100d16');
      g.fillStyle = grad; g.fillRect(0, 0, 512, 512);
      const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
    })();
    const floor = new THREE.Mesh(new THREE.CircleGeometry(size / 2, 96), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.92, metalness: 0 }));
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    floor.name = 'floor';
    this.scene.add(floor);
    this.floor = floor;
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.055, 0.075, 40), new THREE.MeshBasicMaterial({ color: 0xff4f9a, transparent: true, opacity: 0.85 }));
    ring.rotation.x = -Math.PI / 2; ring.position.y = 0.004;
    this.scene.add(ring);
    this.origin = ring;
  }

  _lights() {
    const hemi = new THREE.HemisphereLight(0xfff4ee, 0x2a2228, 0.85);
    this.scene.add(hemi);
    const key = new THREE.DirectionalLight(0xfff3ea, 2.5);
    key.position.set(2.6, 5, 3.6);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.left = -3; key.shadow.camera.right = 3; key.shadow.camera.top = 3; key.shadow.camera.bottom = -3;
    key.shadow.bias = -0.0003; key.shadow.normalBias = 0.02;
    key.shadow.radius = 5;
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(0xff7ab8, 0.75);       // the "wicked" pink rim, kept subtle so skin stays skin
    rim.position.set(-4, 2.6, -3.5);
    this.scene.add(rim);
    const rim2 = new THREE.DirectionalLight(0xa88bff, 0.55);
    rim2.position.set(4, 2.2, -3);
    this.scene.add(rim2);
    const fill = new THREE.DirectionalLight(0xfff0e8, 0.6);
    fill.position.set(-2, 1.2, 4);
    this.scene.add(fill);
    this.lights = { hemi, key, rim, rim2, fill };
  }

  _resize() {
    const el = this.canvas.parentElement;
    const w = el.clientWidth, h = el.clientHeight;
    if (!w || !h) return;                       // hidden (e.g. a collapsed window) - keep the last size
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    // ambient occlusion: 12 samples on big stages, 8 on laptop-sized ones (6 when adaptive quality stepped down)
    if (this.ao) { try { this.ao.updateGtaoMaterial({ samples: this._qLevel >= 2 ? 6 : w * h > 1.1e6 ? 12 : 8 }); } catch { /* older GTAO */ } }
    this.camera.aspect = w / Math.max(1, h);
    this.camera.updateProjectionMatrix();
  }

  _loop() {
    if (this._paused) { this._raf = 0; return; }
    this._raf = requestAnimationFrame(this._loop);
    const dt = this.clock.getDelta();
    for (const f of [...this.onFrame]) f(dt);
    this.controls.update(dt);
    if (!this.canvas.clientWidth || !this.canvas.clientHeight) return;
    const t0 = performance.now();
    if (this.quality === 'fast') this.renderer.render(this.scene, this.camera);
    else this.composer.render(dt);
    this._adapt(dt, performance.now() - t0);
  }

  // Stop / restart the main render loop (a full-screen tool, e.g. capture, needs the GPU to itself).
  pause() { this._paused = true; if (this._raf) { cancelAnimationFrame(this._raf); this._raf = 0; } }
  resume() {
    if (!this._paused) return;
    this._paused = false;
    this.clock.getDelta();                        // no jump after the pause
    if (!this._raf) this._raf = requestAnimationFrame(this._loop);
  }
  get paused() { return !!this._paused; }

  // Adaptive quality: a rolling average of the frame time; above 22 ms for 90 frames in a row it steps down once
  // (cinematic bloom off, then fewer AO samples, then the fast renderer) and tells onQuality. Hitches (a hidden
  // window, a pause) do not count, and nothing changes once the user chose full quality by hand (keepQuality).
  _adapt(dt, renderMs) {
    if (dt > 0.25 || document.hidden || this.keepQuality) return;
    this._ft += (Math.max(dt * 1000, renderMs) - this._ft) * 0.08;
    if (this._ft > 22) this._slow++; else this._slow = Math.max(0, this._slow - 2);
    if (this._slow < 90 || this._qLevel >= 3) return;
    this._slow = 0; this._ft = 16;
    this.setQualityLevel(this._qLevel + 1, true);
  }

  setQualityLevel(level, auto = false) {
    this._qLevel = Math.max(0, Math.min(3, level));
    if (this.stage) this.stage.allowBloom(this._qLevel < 1);
    this.quality = this._qLevel >= 3 ? 'fast' : 'full';
    this._resize();
    const text = [$t('viewport.full_quality'), $t('viewport.fast_mode_no_glow'), $t('viewport.fast_mode_lighter_shadows'), $t('viewport.fast_mode')][this._qLevel];
    if (this.onQuality) { try { this.onQuality(this._qLevel, text, auto); } catch (e) { console.error(e); } }
  }
  get qualityLevel() { return this._qLevel; }

  setView(kind) {
    const t = this.controls.target.clone();
    const d = this.camera.position.distanceTo(t);
    const pos = {
      front: new THREE.Vector3(0, 0.2, 1), side: new THREE.Vector3(1, 0.2, 0), top: new THREE.Vector3(0, 1, 0.02),
      persp: new THREE.Vector3(0.62, 0.42, 0.66),
    }[kind] || new THREE.Vector3(0.62, 0.42, 0.66);
    this._animateCamera(t.clone().add(pos.normalize().multiplyScalar(d)), t);
  }

  // Fly to a point, keeping the direction you look from (or from `dir`, e.g. a three-quarter front view).
  frame(center, radius = 1.4, dir = null) {
    dir = (dir ? dir.clone() : this.camera.position.clone().sub(this.controls.target)).normalize();
    const pos = center.clone().add(dir.multiplyScalar(radius * 2.6));
    if (pos.y < 0.15) pos.y = 0.15;               // never under the floor
    this._animateCamera(pos, center);
  }

  // The direction the camera looks from now, tipped back toward the side when it is (almost) straight above or
  // below - so framing the whole scene never shows the bodies as a flat outline.
  viewDir() {
    const dir = this.camera.position.clone().sub(this.controls.target).normalize();
    if (Math.abs(dir.y) > 0.85) {
      const flat = new THREE.Vector3(dir.x, 0, dir.z);
      if (flat.lengthSq() < 1e-6) flat.set(0.62, 0, 0.66);
      flat.normalize().multiplyScalar(Math.sqrt(1 - 0.85 * 0.85));
      dir.set(flat.x, Math.sign(dir.y) * 0.85, flat.z);
    }
    return dir;
  }

  // Fly to a place. toRoll tilts the picture (the Face step, for a lying sim's face); every other move levels it.
  // duration in seconds (with reduced motion at most 0.2 s), ease: t -> 0..1.
  _animateCamera(toPos, toTarget, toRoll = 0, { duration = 0.286, ease = t => 1 - Math.pow(1 - t, 3) } = {}) {
    const fromPos = this.camera.position.clone(), fromT = this.controls.target.clone(), fromRoll = this.controls.roll || 0;
    this.stopCamera();
    toPos = toPos.clone(); toTarget = toTarget.clone();
    if (reduced()) duration = Math.min(duration, 0.2);
    // the first frame after a busy moment (Magic builds a whole scene before the camera flies) brings one long
    // time step: it is not counted, and later steps count at most 1/15 s, so a flight is never skipped as a cut
    let k = 0, first = true;
    const step = dt => {
      const d = first ? 0 : Math.min(dt, 1 / 15);
      first = false;
      k = Math.min(1, k + d / Math.max(0.001, duration));
      const e = ease(k);
      this.controls.lookFrom(new THREE.Vector3().lerpVectors(fromPos, toPos, e), new THREE.Vector3().lerpVectors(fromT, toTarget, e), fromRoll + (toRoll - fromRoll) * e);
      if (k >= 1 || this.controls.busy) { this.onFrame.splice(this.onFrame.indexOf(step), 1); this._camStep = null; this._camTo = null; }
    };
    this._camStep = step;
    this._camTo = { pos: toPos, target: toTarget };
    this.onFrame.push(step);
  }

  // Magic's entrance: the camera starts twice as far away and higher, then glides in (1.1 s). A cut with reduced motion.
  swoop(center, radius, dir = this.viewDir()) {
    const d = dir.clone().normalize();
    const end = center.clone().add(d.clone().multiplyScalar(radius * 2.6));
    if (end.y < 0.15) end.y = 0.15;
    this.stopCamera();
    if (reduced()) { this.controls.lookFrom(end, center); return; }
    this.controls.lookFrom(center.clone().add(d.multiplyScalar(radius * 5.2)).add(new THREE.Vector3(0, radius * 1.6, 0)), center);
    this._animateCamera(end, center, 0, { duration: 1.1, ease: t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2) });
  }

  // The pink origin ring pulses out once over the floor (800 ms).
  pulseOrigin() {
    const r = this.origin, m = r && r.material;
    if (!r || reduced()) return;
    if (this._pulse) { const i = this.onFrame.indexOf(this._pulse); if (i >= 0) this.onFrame.splice(i, 1); }
    let t = 0;
    const step = dt => {
      t += dt / 0.8;
      r.scale.setScalar(1 + 8 * (1 - Math.pow(1 - Math.min(1, t), 3)));
      m.opacity = 0.85 * (1 - Math.min(1, t));
      if (t >= 1) { r.scale.setScalar(1); m.opacity = 0.85; const i = this.onFrame.indexOf(step); if (i >= 0) this.onFrame.splice(i, 1); this._pulse = null; }
    };
    this._pulse = step;
    this.onFrame.push(step);
  }

  // Stop a camera flight where it is (the camera stays put).
  stopCamera() {
    if (this._camStep) { const i = this.onFrame.indexOf(this._camStep); if (i >= 0) this.onFrame.splice(i, 1); }
    this._camStep = null; this._camTo = null;
  }

  // The view to come back to later: where the camera is - or, while it flies somewhere, where it is going.
  savedView() {
    const to = this._camStep && this._camTo;
    return { pos: (to ? to.pos : this.camera.position).clone(), target: (to ? to.target : this.controls.target).clone() };
  }

  // Fly back to a view from savedView(), level.
  restoreView(view) { this._animateCamera(view.pos, view.target, 0); }

  // Pointer -> first hit among `objects` (hidden meshes are skipped).
  pick(event, objects) {
    const r = this.canvas.getBoundingClientRect();
    this.pointer.set(((event.clientX - r.left) / r.width) * 2 - 1, -((event.clientY - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    return this.raycaster.intersectObjects(objects.filter(o => o.visible), true)[0] || null;
  }

  // ---------------------------------------------------------------- motion trail
  setTrail(points, keyIndices = [], color = '#ff4f9a') {
    if (this.trail) { this.trail.traverse(o => { o.geometry?.dispose(); o.material?.dispose(); }); this.trail.removeFromParent(); this.trail = null; }
    if (!points || points.length < 2) return;
    const g = new THREE.Group();
    const geo = new THREE.BufferGeometry().setFromPoints(points);
    const n = points.length;
    const cols = new Float32Array(n * 3), c0 = new THREE.Color(color), c1 = new THREE.Color('#8b5cf6');
    for (let k = 0; k < n; k++) { const c = c0.clone().lerp(c1, k / n); cols.set([c.r, c.g, c.b], k * 3); }
    geo.setAttribute('color', new THREE.BufferAttribute(cols, 3));
    const line = new THREE.LineLoop(geo, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.9, depthTest: false }));
    line.renderOrder = 15;
    g.add(line);
    const dotGeo = new THREE.SphereGeometry(0.006, 8, 6), keyGeo = new THREE.SphereGeometry(0.013, 12, 8);
    const dotMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.55, depthTest: false });
    const keyMat = new THREE.MeshBasicMaterial({ color: 0xffd1e6, depthTest: false });
    points.forEach((p, k) => {
      const m = new THREE.Mesh(keyIndices.includes(k) ? keyGeo : dotGeo, keyIndices.includes(k) ? keyMat : dotMat);
      m.position.copy(p); m.renderOrder = 16; g.add(m);
    });
    this.trail = g;
    this.overlay.add(g);
  }

  // A picture of the view (for project thumbnails).
  snapshot(w = 360, h = 225) {
    const src = this.canvas;
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    const g = c.getContext('2d');
    const r = Math.max(w / src.width, h / src.height);
    const sw = w / r, sh = h / r;
    g.drawImage(src, (src.width - sw) / 2, (src.height - sh) / 2, sw, sh, 0, 0, w, h);
    return c.toDataURL('image/jpeg', 0.82);
  }
}

const reduced = () => (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) || document.documentElement.classList.contains('reduce-motion');
