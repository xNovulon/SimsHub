// "Copy real moves": the capture studio. A video, the webcam or a photo of a real (adult) person becomes the selected
// sim's animation - body, hands and fingers, face - all on this PC (capture.md section 9). Steps for a video:
//   1 Pick  2 Choose the part  3 Reading  4 Check and trim  5 Put it on
// The webcam records after a 3-2-1 count-in (Space starts and stops), "Copy my face" reads only the face (hold T for
// the tongue), and a photo gives one pose. MediaPipe is a one-time download (the first-time panel); with
// ?captureMock=1 a stand-in reads a library dance instead, so everything can be tried and tested without it.
// Capture 2: the live mirror (the sim copies you in the main view - capture/dock.js, capture/mirror.js), two people
// at once (experimental; a couple from one video, webcam or photo), "Match the rhythm" for a partner's take, and
// "photo -> couple pose" whose hands snap onto the partner (capture/couple.js).
import * as THREE from 'three';
import { h, icon, toast, confirmBox } from './ui.js';
import { Sim } from './sim.js';
import { applyFace } from './face.js';
import { spaceQuat } from './posemath.js';
import * as A from './animation.js';
import { createTracker, trackVideo, trackWebcam, trackPhoto, detectFrame, seenPeople } from './capture/tracker.js';
import { cleanTake } from './capture/clean.js';
import { Solver, solveTake, solveOne } from './capture/retarget.js';
import { RigPose } from './capture/rigpose.js';
import { faceTrack } from './capture/facemap.js';
import { findLoop, closeLoop, seamError, applyToSim, retime } from './capture/keys.js';
import { isMock, loadMockMotion, loadMockCouple, sceneMotion, takeFromMotion, MockVideo } from './capture/mock.js';
import { ensureIcons, ensureStyles } from './capture/icons.js';
import { frameTake } from './capture/mirror.js';
import { solvePair, snapContacts, matchRhythm, shiftLoop } from './capture/couple.js';
import { dockMethods } from './capture/dock.js';
import { $t } from './i18n.js';

export { ensureIcons, ensureStyles };

const MAX_PART = 60;                           // seconds read at most
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('reduce-motion');
const secs = t => (Math.round(t * 10) / 10).toFixed(1) + ' s';

// ---------------------------------------------------------------- install
export async function captureStatus() {
  try {
    const r = await fetch('/api/capture_status');
    if (!r.ok) return { installed: false, unavailable: true, missing: [], bytes_needed: 0 };
    return await r.json();
  } catch { return { installed: false, unavailable: true, missing: [], bytes_needed: 0 }; }
}

// Starts the one-time download (only ever from the user's click) and follows it every 500 ms.
export async function installCapture(onProgress) {
  const r = await fetch('/api/capture_install', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  let st = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(st.error || $t('capture.download_could_not_start'));
  onProgress && onProgress(st);
  while (st.busy) {
    await new Promise(res => setTimeout(res, 500));
    st = await captureStatus();
    onProgress && onProgress(st);
  }
  if (st.error) throw new Error(st.error);
  return st;
}

// ---------------------------------------------------------------- the pose skeleton (MediaPipe's 33 points)
const BONES = [[11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [11, 23], [12, 24], [23, 24], [23, 25], [25, 27], [24, 26], [26, 28],
  [27, 29], [29, 31], [27, 31], [28, 30], [30, 32], [28, 32], [15, 19], [15, 17], [17, 19], [16, 20], [16, 18], [18, 20], [0, 7], [0, 8], [9, 10]];
const HAND = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12], [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17]];

// ---------------------------------------------------------------- the small 3D preview (the sim moving along)
class Preview3D {
  constructor(app, simId, canvas) {
    this.app = app; this.canvas = canvas;
    const s = app.store.sim(simId);
    this.sim = s;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.05, 30);
    const color = new THREE.Color(s ? s.color : '#ff4f9a');
    this.scene.add(new THREE.HemisphereLight('#f4ecff', '#2a2034', 1.15));
    const key = new THREE.DirectionalLight('#fff4ea', 2.1); key.position.set(1.6, 3, 2.4); this.scene.add(key);
    const rim = new THREE.DirectionalLight(color, 2.2); rim.position.set(-2, 2.2, -2.4); this.scene.add(rim);
    const disc = new THREE.Mesh(new THREE.CircleGeometry(1.4, 64), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.12 }));
    disc.rotation.x = -Math.PI / 2; this.disc = disc; this.scene.add(disc);
    this.vs = [this._view(simId)];
    this.v = this.vs[0];
    this.facing = 0;
    this._ro = new ResizeObserver(() => this.resize());
    this._ro.observe(canvas);
    this.resize();
  }
  _view(simId) {
    const app = this.app, s = app.store.sim(simId);
    if (!s || !app.assets || !app.assets.rig) return null;
    const main = app.simViews && app.simViews.get(simId);
    const bodyKey = (main && main.frameKey) || s.frame;
    const body = (app.assets.bodies && (app.assets.bodies[bodyKey] || app.assets.bodies[s.frame] || app.assets.bodies.yf));
    if (!body) return null;
    const v = new Sim(app.assets.rig, body, { color: s.color, skin: s.skin });
    v.setErect && v.setErect(s.body ? s.body.erect !== false : true);
    try {
      app.applySkin && app.applySkin(v, s.frame, s.tone || '');
      app.skinReady && app.skinReady(s.frame, s.tone || '').then(() => { if (this.vs && this.vs.includes(v)) { v.material.needsUpdate = true; this.render(); } });
    } catch { /* plain skin colour */ }
    this.scene.add(v.group);
    v.simId = simId;
    return v;
  }
  // a second sim beside the first (two people), or none
  setSecond(simId) {
    const old = this.vs[1];
    if (old && old.simId === simId) return;
    if (old) { this.scene.remove(old.group); old.dispose(); }
    this.vs.length = 1;
    if (simId) { const v = this._view(simId); if (v) this.vs.push(v); }
    this.render();
  }
  resize() {
    const w = this.canvas.clientWidth || 300, hh = this.canvas.clientHeight || 300;
    this.renderer.setSize(w, hh, false);
    this.camera.aspect = w / hh; this.camera.updateProjectionMatrix();
    this.render();
  }
  setPose(pose, face = null, k = 0) {
    const v = this.vs[k];
    if (!v || !pose) return;
    v.resetPose();
    v.setPose(pose);
    if (face) applyFace(v, face);
    this.render();
  }
  render() {
    if (!this.v) { this.renderer.render(this.scene, this.camera); return; }
    // follow the hips (both sims' middle for two), look at the first sim's front
    const hp = new THREE.Vector3(), tmp = new THREE.Vector3();
    const vs = this.vs.filter(Boolean);
    for (const v of vs) hp.add(v.byName.b__Pelvis__.getWorldPosition(tmp));
    hp.multiplyScalar(1 / vs.length);
    const c = this._c = this._c ? this._c.lerp(hp, 0.25) : hp.clone();
    const dir = new THREE.Vector3(Math.sin(this.facing), 0, Math.cos(this.facing));
    this.camera.position.copy(c).add(dir.multiplyScalar(vs.length > 1 ? 3.8 : 2.9)).add(new THREE.Vector3(0, 0.25, 0));
    this.camera.lookAt(c.x, c.y + 0.05, c.z);
    this.disc.position.set(c.x, Math.max(0, this._floor || 0) + 0.002, c.z);
    this.renderer.render(this.scene, this.camera);
  }
  dispose() {
    this._ro.disconnect();
    for (const v of this.vs) if (v) v.dispose();
    this.disc.geometry.dispose(); this.disc.material.dispose();
    this.renderer.dispose();
    try { this.renderer.forceContextLoss(); } catch { /* gone */ }
  }
}

// ---------------------------------------------------------------- the studio
const STEPS = {
  video: [$t('capture.pick'), $t('capture.part'), $t('capture.reading'), $t('capture.check'), $t('capture.put_it_on')],
  webcam: [$t('capture.get_ready'), $t('capture.record'), $t('capture.check'), $t('capture.put_it_on')],
  face: [$t('capture.get_ready'), $t('capture.record'), $t('capture.check'), $t('capture.put_it_on')],
  photo: [$t('capture.pick'), $t('capture.use_this_pose')],
};
const TITLES = { video: $t('capture.copy_moves_from_video'), webcam: $t('capture.copy_moves_from_your_webcam'), face: $t('capture.copy_your_face'), photo: $t('capture.copy_pose_from_photo') };

let current = null;
// options: mirror - the webcam studio starts the live mirror as soon as the adults-only box is ticked;
// two - two people (experimental) from the start
export function openCaptureStudio(app, { source = 'video', simId = app.store.selected.sim, mirror = false, two = false } = {}) {
  ensureIcons(); ensureStyles();
  if (current) current.close(true);
  if (!simId || !app.store.sim(simId)) {
    const s = app.store.project.sims[0];
    if (!s) { toast($t('capture.add_sim_first_then_copy')); return null; }
    simId = s.id;
  }
  current = new Studio(app, source, simId, { mirror: mirror && (source === 'webcam' || source === 'face'), two });
  return current;
}
export const studioOpen = () => current;

class Studio {
  constructor(app, source, simId, { mirror = false, two = false } = {}) {
    this.app = app; this.source = source; this.simId = simId; this.target = simId;
    this.mock = isMock();
    this.adult = false;
    // Capture 2: two people (person 1 -> the chosen sim, person 2 -> the next one), the live mirror, the rhythm
    const partner = app.store.project.sims.find(x => x.id !== simId);
    this.assign = [simId, partner ? partner.id : null];
    this.twoPeople = !!two && !!partner && source !== 'face';
    this.mirrorWanted = !!mirror;
    this.rhythm = false; this.snap = true; this.keepPhoto = false; this.copyBoth = true;
    this.opts = { body: source !== 'face', hands: source !== 'face', face: source !== 'photo' };
    this.faceSmall = false;
    this.smooth = 0.5; this.feet = true; this.stay = true; this.headTurns = true; this.swap = false; this.exaggerate = 1.2;
    this.mode = 'replace';
    this.useLoop = !!app.store.project.loop;
    this.chips = new Map();
    this.step = 'pick';
    this.solver = new Solver(app.assets.rig);
    this.rp = this.solver.rp;
    this._build();
    try { app.vp && app.vp.pause && app.vp.pause(); } catch { /* the view keeps drawing */ }
    this._onKey = e => this._key(e);
    document.addEventListener('keydown', this._onKey, true);
    document.addEventListener('keyup', this._onKey, true);
    this._startState();
  }

  // ---------------------------------------------------------------- frame and layout
  _build() {
    const s = this.app.store.sim(this.simId);
    const steps = STEPS[this.source];
    this.stepEls = steps.map((label, i) => h('li', { class: 'cap-step' }, h('span', { class: 'cap-step-dot' }, String(i + 1)), h('span', {}, label)));
    this.media = h('div', { class: 'cap-media' });
    this.overlay = h('canvas', { class: 'cap-overlay' });
    this.scan = h('div', { class: 'cap-scan hidden' });
    this.chipBox = h('div', { class: 'cap-chips', role: 'status' });
    this.ringBox = h('div', { class: 'cap-ring hidden' });
    this.countEl = h('div', { class: 'cap-count hidden' });
    this.stage = h('div', { class: 'cap-stage' }, this.media, this.overlay, this.scan, this.ringBox, this.countEl, this.chipBox);
    this.previewCanvas = h('canvas', { class: 'cap-preview-canvas' });
    this.previewTag = h('div', { class: 'cap-preview-tag' }, h('span', { class: 'dot' }), s ? s.label : $t('capture.sim'));
    this.panel = h('div', { class: 'cap-panel' });
    this.foot = h('div', { class: 'cap-foot' });
    this.root = h('div', { class: 'cap-studio', role: 'dialog', 'aria-modal': 'true', 'aria-label': TITLES[this.source], tabindex: '-1', style: { '--sim': s ? s.color : '#ff4f9a' } },
      h('header', { class: 'cap-top' },
        h('div', { class: 'cap-brand' }, h('span', { class: 'cap-brand-icon' }, icon(this.source === 'face' ? 'cap-face' : this.source === 'photo' ? 'cap-photo' : this.source === 'webcam' ? 'cap-webcam' : 'cap-video')),
          h('div', {}, h('b', {}, TITLES[this.source]), h('span', {}, $t('capture.everything_stays_on_this_pc')))),
        h('ol', { class: 'cap-steps' }, this.stepEls),
        h('button', { class: 'icon-btn cap-x', title: $t('capture.close_esc'), onclick: () => this.tryClose() }, icon('x'))),
      h('div', { class: 'cap-body' },
        this.stage,
        h('aside', { class: 'cap-side' },
          h('div', { class: 'cap-preview' }, this.previewCanvas, this.previewTag),
          this.panel)),
      this.foot);
    this.back = h('div', { class: 'backdrop cap-backdrop' }, this.root);
    (document.getElementById('modal-root') || document.body).append(this.back);
    requestAnimationFrame(() => this.root.classList.add('in'));
    this.preview = new Preview3D(this.app, this.simId, this.previewCanvas);
    // where the sim is now: its facing, its hips' place, the floor it stands on
    this._readSim();
    this.preview.facing = this.facing;
    if (this.basePose) this.preview.setPose(this.basePose);
    this.root.focus({ preventScroll: true });
  }

  _readSim(simId = this.target) {
    const app = this.app, s = app.store.sim(simId), p = app.store.project;
    const f = Math.round(app.store.frame);
    this.baseFrame = f;
    this.basePose = s ? A.evaluate(s.keys, f, p.length, p.loop) : null;
    const rp = this.rp;
    rp.resetPose(); if (this.basePose) rp.setPose(this.basePose); rp.fk();
    const q = spaceQuat(rp, rp.bone('b__Pelvis__'));
    const fwd = new THREE.Vector3(0, 1, 0).applyQuaternion(q), left = new THREE.Vector3(0, 0, -1).applyQuaternion(q);
    this.facing = Math.hypot(fwd.x, fwd.z) >= Math.hypot(left.x, left.z) ? Math.atan2(fwd.x, fwd.z) : Math.atan2(-left.z, left.x);
    // the app's own facing, when it has it (the same rule)
    try {
      const v = app.simViews && app.simViews.get(simId);
      if (v && typeof app._facing === 'function') { const fq = app._facing(v); this.facing = 2 * Math.atan2(fq.y, fq.w); }
    } catch { /* keep ours */ }
  }

  _setStep(step) {
    this.step = step;
    const order = { video: ['pick', 'part', 'reading', 'check', 'apply'], webcam: ['pick', 'record', 'check', 'apply'], face: ['pick', 'record', 'check', 'apply'], photo: ['pick', 'photo'] }[this.source];
    const idx = Math.max(0, order.indexOf(step === 'install' ? 'pick' : step));
    this.stepEls.forEach((el, i) => { el.classList.toggle('on', i === idx); el.classList.toggle('done', i < idx); });
    this.root.dataset.step = step;
    this.render();
  }

  chip(id, text, kind = '', action = null) {
    let el = this.chips.get(id);
    if (!text) { if (el) { el.classList.add('leaving'); setTimeout(() => el.remove(), 200); this.chips.delete(id); } return; }
    if (!el) { el = h('div', { class: 'cap-chip' }); this.chips.set(id, el); this.chipBox.append(el); }
    el.className = 'cap-chip ' + kind;
    el.innerHTML = '';
    el.append(h('span', {}, text));
    if (action) el.append(h('button', { class: 'cap-chip-btn', onclick: action.run }, action.label));
  }

  // ---------------------------------------------------------------- start
  async _startState() {
    const st = this.mock ? { installed: true } : await captureStatus();
    this.status = st;
    if (!st.installed) return this._setStep('install');
    if (this.source === 'webcam' || this.source === 'face') return this._setStep('pick');
    this._setStep('pick');
    if (this.mock && this.source === 'video') await this._useMockVideo();   // (a photo gets its own test picture)
  }

  async _useMockVideo() {
    const motion = await this._mockMotion();
    if (this.closed) return;
    const take = takeFromMotion(this.app.assets.rig, motion, { seconds: 20, face: true, hands: true, noise: 0.002 });
    this._setVideo(new MockVideo(take, { live: this.source === 'webcam' || this.source === 'face' }), $t('capture.test_clip', { name: motion.name || $t('capture.test_clip_dance') }));
  }
  // the stand-in's motion: a dance, a couple (two people), or the scene itself (window.__captureMockScene)
  async _mockMotion(still = false) {
    if (this.twoPeople || still === 'two') {
      if (window.__captureMockScene) return sceneMotion(this.app, still ? { frames: [Math.round(this.app.store.frame)] } : {});
      return loadMockCouple();
    }
    return loadMockMotion();
  }

  // ---------------------------------------------------------------- rendering the side panel and the foot
  render() {
    const P = this.panel, F = this.foot;
    P.innerHTML = ''; F.innerHTML = '';
    const fn = this['_render_' + this.step];
    if (fn) fn.call(this, P, F);
  }

  _render_install(P, F) {
    const st = this.status || {};
    // rounded up: the whole set is 63.1-63.9 MB (the npm package's size varies a little), "64 MB" in capture.md 9
    const mb = Math.max(1, Math.ceil((st.bytes_needed || 63875911) / 1e6));
    this.bar = h('div', { class: 'cap-bar' }, h('i', {}));
    this.barText = h('div', { class: 'cap-bar-text' }, '');
    if (navigator.onLine === false) { this.barText.textContent = $t('capture.no_internet_right_now_connect'); this.barText.classList.add('err'); }
    // the stage says what the download gives (it would be an empty box otherwise)
    if (!this.media.querySelector('.cap-intro')) {
      const item = (ic, b, t) => h('li', {}, h('span', { class: 'cap-intro-icon' }, icon(ic)), h('div', {}, h('b', {}, b), h('span', {}, t)));
      this.media.innerHTML = '';
      this.media.append(h('div', { class: 'cap-intro' },
        h('span', { class: 'cap-drop-icon' }, icon('cap-film')),
        h('b', { class: 'cap-intro-title' }, $t('capture.film_it_play_it')),
        h('ul', {},
          item('cap-video', $t('capture.video_your_webcam_or_photo'), $t('capture.any_real_adult_sim_copies')),
          item('cap-face', $t('capture.body_hands_fingers_and_face'), $t('capture.blinks_smiles_mouth_even_wink')),
          item('cap-shield', $t('capture.everything_stays_on_this_pc'), $t('capture.nothing_is_uploaded_after_download')))));
    }
    P.append(h('div', { class: 'cap-card cap-install' },
      h('div', { class: 'cap-card-icon' }, icon('cap-download')),
      h('h3', {}, $t('capture.one_time_download')),
      h('p', {}, $t('capture.motion_capture_needs_one_time', { mb })),
      this.bar, this.barText,
      h('p', { class: 'cap-fine' }, $t('capture.mediapipe_google_llc_apache_license'))));
    const btn = h('button', { class: 'btn primary big cap-go' }, icon('cap-download'), $t('capture.download'));
    btn.onclick = async () => {
      btn.disabled = true;
      this.barText.classList.remove('err');
      this.barText.textContent = $t('capture.starting');
      this.root.classList.add('busy');
      try {
        const done = await installCapture(s => {
          const f = s.total_bytes ? Math.min(1, s.done_bytes / s.total_bytes) : 0;
          this.bar.firstChild.style.transform = `scaleX(${f})`;
          this.barText.textContent = s.busy ? `${Math.round(f * 100)}% - ${s.stage || $t('capture.downloading')}` : '';
        });
        this.status = done;
        this.bar.firstChild.style.transform = 'scaleX(1)';
        this.bar.classList.add('ok');
        this.barText.innerHTML = '';
        this.barText.append(icon('check'), ' Ready!');
        setTimeout(() => { this.media.innerHTML = ''; this._setStep('pick'); }, 900);
      } catch (e) {
        this.barText.textContent = e.message || $t('capture.download_did_not_finish');
        this.barText.classList.add('err');
        btn.disabled = false;
      } finally { this.root.classList.remove('busy'); }
    };
    F.append(h('div', { class: 'grow' }), btn);
  }

  _adultBox() {
    const box = h('input', { type: 'checkbox', checked: this.adult });
    box.addEventListener('change', () => { this.adult = box.checked; this.render(); });
    const text = this.source === 'photo' ? $t('capture.everyone_in_this_picture_is')
      : this.source === 'video' ? $t('capture.everyone_in_this_video_is')
      : $t('capture.i_am_adult_18_and');
    return h('label', { class: 'cap-adult' + (this.adult ? ' on' : '') }, box, h('span', { class: 'cap-tick' }, icon('check')), h('span', {}, text));
  }

  _switch(label, sub, on, change, disabled = false) {
    const input = h('input', { type: 'checkbox', checked: on && !disabled, disabled });
    input.addEventListener('change', () => change(input.checked));
    return h('div', { class: 'toggle-row cap-switch' + (disabled ? ' off' : '') }, h('div', {}, h('b', {}, label), sub ? h('span', {}, sub) : null), h('label', { class: 'switch' }, input, h('span')));
  }

  _render_pick(P, F) {
    if (this.source === 'photo') return this._render_pickPhoto(P, F);
    if (this.source === 'webcam' || this.source === 'face') return this._render_pickCam(P, F);
    if (!this.video) {
      this._dropZone('video/*,.mp4,.webm,.mov', $t('capture.drop_video_here_or_click'), $t('capture.video_types_hint'));
    }
    P.append(h('div', { class: 'cap-card' },
      h('h3', {}, this.video ? (this.videoName || $t('capture.your_video')) : $t('capture.pick_video')),
      h('p', {}, this.video ? $t('capture.secs_long', { secs: secs(this.video.duration) }) : $t('capture.film_yourself_or_use_any')),
      this.video ? h('button', { class: 'btn small ghost', onclick: () => this._clearVideo() }, icon('reset'), $t('capture.pick_another_video')) : null,
      h('button', { class: 'btn small ghost', onclick: () => this._switchSource('webcam') }, icon('cap-webcam'), $t('capture.use_my_webcam'))));
    P.append(this._adultBox());
    P.append(h('div', { class: 'cap-switches' },
      this._switch($t('capture.body'), $t('capture.arms_legs_hips_and_head'), this.opts.body, v => { this.opts.body = v; }),
      this._switch($t('capture.hands_and_fingers'), $t('capture.needs_hands_in_view'), this.opts.hands, v => { this.opts.hands = v; }),
      this._switch($t('capture.face'), this.faceSmall ? $t('capture.face_too_small_in_this') : $t('capture.expressions_blinks_mouth'), this.opts.face && !this.faceSmall, v => { this.opts.face = v; }, this.faceSmall)));
    const long = this.video && this.video.duration > 12;
    const next = h('button', { class: 'btn primary big cap-go', disabled: !this.video || !this.adult }, long ? $t('capture.next') : $t('capture.read_moves'), icon('arrow'));
    next.onclick = () => (long ? this._setStep('part') : this.read());
    F.append(h('div', { class: 'cap-foot-note' }, !this.adult ? $t('capture.tick_box_to_go_on') : !this.video ? $t('capture.pick_video_to_go_on') : ''), h('div', { class: 'grow' }), next);
  }

  _dropZone(accept, title, sub) {
    this.media.innerHTML = '';
    const input = h('input', { type: 'file', accept, class: 'hidden' });
    const zone = h('button', { class: 'cap-drop', onclick: () => input.click() },
      h('span', { class: 'cap-drop-icon' }, icon(this.source === 'photo' ? 'cap-photo' : 'cap-film')), h('b', {}, title), h('span', {}, sub), input);
    input.addEventListener('change', () => { if (input.files[0]) this._loadFile(input.files[0]); });
    this.stage.addEventListener('dragover', this._dragOver = e => { e.preventDefault(); zone.classList.add('over'); });
    this.stage.addEventListener('dragleave', this._dragLeave = () => zone.classList.remove('over'));
    this.stage.addEventListener('drop', this._drop = e => { e.preventDefault(); zone.classList.remove('over'); const f = e.dataTransfer.files[0]; if (f) this._loadFile(f); });
    this.media.append(zone);
  }

  _loadFile(file) {
    if (this.source === 'photo') {
      if (!/^image\//.test(file.type)) return this.chip('type', $t('capture.that_is_not_picture_pick'), 'warn');
      const url = URL.createObjectURL(file);
      const img = h('img', { class: 'cap-video', alt: '' });
      img.onload = () => { this._setPhoto(img, file.name); };
      img.onerror = () => this.chip('type', $t('capture.this_picture_can_t_be'), 'warn');
      img.src = url;
      this._urls = [...(this._urls || []), url];
      return;
    }
    const url = URL.createObjectURL(file);
    const v = h('video', { class: 'cap-video', muted: true, playsinline: true, preload: 'auto' });
    v.muted = true;
    v.addEventListener('loadedmetadata', () => { this._setVideo(v, file.name); }, { once: true });
    v.addEventListener('error', () => { this.chip('type', $t('capture.this_video_type_can_t'), 'warn'); }, { once: true });
    v.src = url;
    this._urls = [...(this._urls || []), url];
  }

  _setVideo(v, name) {
    this.video = v; this.videoName = name;
    this.range = [0, Math.min(v.duration, MAX_PART)];
    this.media.innerHTML = '';
    this.media.append(v.el || v);
    this.chip('type', null);
    this._fitOverlay();
    this.render();
    // warm the reader up now and check the first frame (a face too small to read turns the Face switch off)
    this._firstFrameCheck();
  }

  async _firstFrameCheck() {
    try {
      const tr = await this._tracker();
      if (!tr || !this.video || this.closed) return;
      const fr = detectFrame(tr, this.video, 1, { W: this.video.videoWidth, H: this.video.videoHeight });
      if (fr.people > 1) this.chip('people', $t('capture.two_people_found_pick_who'), 'warn', { label: $t('capture.pick'), run: () => this._pickPerson(fr) });
      if (this.opts.face && fr.pose && !fr.face) { this.faceSmall = true; this.opts.face = false; this.render(); }
      if (fr.pose) this._drawSkeleton(fr);
    } catch (e) { console.warn('capture: first frame', e); }
  }

  _pickPerson() {
    // the tracker follows whoever is nearest the chosen side
    const tr = this._tr;
    const pick = side => { if (tr) tr.last = { hip: [side === 'left' ? 0.25 : 0.75, 0.55] }; this.chip('people', side === 'left' ? $t('capture.copying_person_on_left') : $t('capture.copying_person_on_right'), 'ok'); };
    this.chip('people', $t('capture.who_should_be_copied'), 'warn', { label: $t('capture.one_on_left'), run: () => pick('left') });
    const el = this.chips.get('people');
    el.append(h('button', { class: 'cap-chip-btn', onclick: () => pick('right') }, $t('capture.one_on_right')));
  }

  _clearVideo() {
    if (this.video && this.video.pause) this.video.pause();
    this.video = null; this.raw = null; this.faceSmall = false;
    this.opts.face = this.source !== 'photo';
    this._clearOverlay();
    this.render();
  }

  _switchSource(src) {
    const app = this.app, simId = this.simId;
    this.close(true);
    openCaptureStudio(app, { source: src, simId });
  }

  // the reader: one person, or two (a photo always looks for two, so a couple picture is found)
  _people(mode = 'VIDEO') { return this.source === 'photo' ? 2 : this.twoPeople ? 2 : 1; }
  async _tracker(mode = 'VIDEO') {
    const people = this._people(mode), key = mode + people;
    if (this._tr && this._tr.mode === mode && (this._tr.people || 1) === people) return this._tr;
    if (this._tr) { this._tr.close(); this._tr = null; }
    if (this._trPromise && this._trMode === key) return this._trPromise;
    this._trMode = key;
    this.chip('warm', $t('capture.warming_up_motion_reader'), 'soft');
    this._trPromise = createTracker({ body: this.opts.body || this.source !== 'face', hands: this.opts.hands, face: this.opts.face || this.source === 'face', quality: this.source === 'webcam' || this.source === 'face' ? 'fast' : 'best', mode, people })
      .then(tr => { this._tr = tr; this.chip('warm', null); return tr; })
      .catch(e => { this.chip('warm', $t('capture.motion_reader_could_not_start', { message: e.message || e }), 'warn'); this._trPromise = null; throw e; });
    return this._trPromise;
  }

  // ---------------------------------------------------------------- 2. the part (long videos)
  _render_part(P, F) {
    const v = this.video, d = v.duration;
    P.append(h('div', { class: 'cap-card' }, h('h3', {}, $t('capture.choose_part')),
      h('p', {}, $t('capture.drag_handles_to_part_you')),
      h('div', { class: 'cap-range-text' }, $t('capture.to', { v: secs(this.range[0]), v2: secs(this.range[1]), v3: secs(this.range[1] - this.range[0]) }))));
    const strip = h('div', { class: 'cap-strip' });
    const sel = h('div', { class: 'cap-strip-sel' });
    const hA = h('div', { class: 'cap-handle', role: 'slider', 'aria-label': $t('capture.start') }), hB = h('div', { class: 'cap-handle', role: 'slider', 'aria-label': 'End' });
    const place = () => {
      const a = this.range[0] / d * 100, b = this.range[1] / d * 100;
      hA.style.left = a + '%'; hB.style.left = b + '%';
      sel.style.left = a + '%'; sel.style.width = (b - a) + '%';
      const txt = P.querySelector('.cap-range-text');
      if (txt) txt.textContent = $t('capture.to', { v: secs(this.range[0]), v2: secs(this.range[1]), v3: secs(this.range[1] - this.range[0]) });
    };
    const drag = (which, el) => el.addEventListener('pointerdown', e => {
      e.preventDefault(); el.setPointerCapture(e.pointerId);
      const r = strip.getBoundingClientRect();
      const move = ev => {
        const t = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)) * d;
        if (which === 0) this.range[0] = Math.max(0, Math.min(t, this.range[1] - 1, t)), this.range[1] = Math.min(this.range[1], this.range[0] + MAX_PART);
        else this.range[1] = Math.min(d, Math.max(t, this.range[0] + 1)), this.range[0] = Math.max(this.range[0], this.range[1] - MAX_PART);
        place();
        this._seek(which === 0 ? this.range[0] : this.range[1]);
      };
      const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); };
      el.addEventListener('pointermove', move); el.addEventListener('pointerup', up);
    });
    drag(0, hA); drag(1, hB);
    const thumbs = h('div', { class: 'cap-thumbs' });
    strip.append(thumbs, sel, hA, hB);
    F.append(h('button', { class: 'btn ghost', onclick: () => this._setStep('pick') }, icon('prev'), $t('capture.back')), strip,
      h('button', { class: 'btn primary big cap-go', disabled: !this.adult, onclick: () => this.read() }, $t('capture.read_moves'), icon('arrow')));
    place();
    this._filmstrip(thumbs, 8);
  }

  async _filmstrip(box, count) {
    const v = this.video, d = v.duration, was = v.currentTime;
    for (let i = 0; i < count && !this.closed; i++) {
      const t = (i + 0.5) / count * d;
      await this._seekWait(t);
      const c = h('canvas', { width: 96, height: 54 });
      try { c.getContext('2d').drawImage(v.el || v, 0, 0, 96, 54); } catch { /* not ready */ }
      box.append(c);
    }
    await this._seekWait(was || this.range[0]);
  }
  _seek(t) { const v = this.video; if (!v) return; if (v.seek) v.seek(t); else v.currentTime = t; }
  _seekWait(t) {
    const v = this.video;
    if (!v) return Promise.resolve();
    if (v.seek) { v.seek(t); return Promise.resolve(); }
    return new Promise(res => { const done = () => res(); v.addEventListener('seeked', done, { once: true }); v.currentTime = t; setTimeout(done, 1500); });
  }

  // ---------------------------------------------------------------- 3. reading
  _render_reading(P, F) {
    P.append(h('div', { class: 'cap-card' }, h('h3', {}, $t('capture.reading_your_moves')),
      h('p', {}, $t('capture.video_plays_at_speed_this')),
      h('div', { class: 'cap-live-stats' }, this.readStat = h('span', {}, ''))));
    F.append(h('div', { class: 'grow' }), h('button', { class: 'btn ghost', onclick: () => { this.abort && this.abort.abort(); } }, $t('capture.stop')));
  }

  _ring(fraction, text) {
    const R = 44, C = 2 * Math.PI * R;
    this.ringBox.classList.remove('hidden');
    this.ringBox.innerHTML = `<svg viewBox="0 0 100 100" class="cap-ring-svg"><circle cx="50" cy="50" r="${R}" class="bg"/><circle cx="50" cy="50" r="${R}" class="fg" style="stroke-dasharray:${C};stroke-dashoffset:${C * (1 - fraction)}"/></svg><div class="cap-ring-text"><b>${Math.round(fraction * 100)}%</b><span>${text}</span></div>`;
  }

  async read() {
    if (!this.adult) return;
    this._setStep('reading');
    this.scan.classList.remove('hidden');
    this._ring(0, $t('capture.reading_your_moves_2'));
    let tr;
    try { tr = await this._tracker(); } catch { this._setStep('pick'); return; }
    this.abort = new AbortController();
    const [from, to] = this.range;
    let feetGone = 0, feetWarned = false, lastPreview = 0, psi = null, crowd = false;
    const t0 = performance.now();
    if (this.video.playbackRate !== undefined && this.mock) this.video.playbackRate = 2;
    try {
      this.raw = await trackVideo(tr, this.video, {
        from, to, signal: this.abort.signal,
        onFrame: (fr, t, prog) => {
          this._drawSkeleton(fr);
          this._ring(Math.max(0, Math.min(1, prog)), $t('capture.reading_your_moves_2'));
          if (this.readStat) this.readStat.textContent = $t('capture.secs_read', { secs: secs(t - from) });
          const po = fr.pose && fr.pose.world;
          const ankles = po && po[27 * 4 + 3] >= 0.5 && po[28 * 4 + 3] >= 0.5;
          feetGone = po && !ankles ? feetGone + 1 : 0;
          if (feetGone === 10 && !feetWarned) { feetWarned = true; this.chip('feet', $t('capture.feet_out_of_view_at', { t: secs(t) }), 'warn'); }
          if (fr.people > 1 && !crowd) { crowd = true; this.chip('people', $t('capture.two_people_found_pick_who'), 'warn', { label: $t('capture.pick'), run: () => this._pickPerson() }); }
          // the sim copies along (a quick solve of this frame, a few times a second)
          const now = performance.now();
          if (po && now - lastPreview > 45) {
            lastPreview = now;
            const one = this._oneFrameTake(fr);
            if (psi === null) psi = this._psiFor(one);
            const pose = solveOne(this.solver, one, 0, 0, { facing: this.facing, psi, base: this.basePose, hands: this.opts.hands, fingers: this.opts.hands, headFromFace: this.opts.face });
            this.preview.setPose(pose);
          }
        },
      });
    } catch (e) {
      this.scan.classList.add('hidden');
      this.ringBox.classList.add('hidden');
      if (e && e.name === 'AbortError') { this._setStep(this.video.duration > 12 ? 'part' : 'pick'); return; }
      this.chip('err', $t('capture.reading_stopped', { message: e.message || e }), 'warn');
      this._setStep('pick');
      return;
    }
    this.readMs = performance.now() - t0;
    this.scan.classList.add('hidden');
    this._ring(1, $t('capture.tidying_up_your_moves'));
    await new Promise(r => setTimeout(r, 30));
    this.process();
    this.ringBox.classList.add('hidden');
    this._setStep('check');
  }

  _oneFrameTake(fr) {
    const rec = new TakeRecorder('frame', this.video ? this.video.videoWidth : 1280, this.video ? this.video.videoHeight : 720);
    rec.add(0, fr);
    return rec.take();
  }
  _psiFor(take) {
    const pts = this.solver.points(take, 0, 0, { mirror: this.swap });
    const l = pts.pose[23].clone().sub(pts.pose[24]);
    return this.facing - Math.atan2(-l.z, l.x);
  }

  // clean -> solve -> face -> loop (again whenever a switch in "Check" changes)
  process() {
    const raw = this.raw;
    if (!raw || !raw.t.length) return;
    this.clean = cleanTake(raw, { smooth: this.smooth });
    const s = this.app.store.sim(this.target), p = this.app.store.project;
    const oldKeys = s ? s.keys : [];
    const opts = {
      facing: this.facing, base: this.basePose, ground: this.feet ? 'floor' : 'free', stay: this.stay, mirror: this.swap,
      hands: this.opts.hands, fingers: this.opts.hands, headFromFace: this.opts.face && this.headTurns,
      basePoses: f => A.evaluate(oldKeys, f % Math.max(1, p.length), p.length, p.loop),
      fov: 60,
    };
    this.solved = this.opts.body ? solveTake(this.clean, 0, this.solver, opts) : null;
    if (this.solved && !this.headTurns) this._flattenHead(this.solved.poses);
    this.faceRes = this.opts.face ? faceTrack(this.clean, 0, {
      calibrate: this.source === 'face' ? [0, 2] : null, exaggerate: this.exaggerate,
      psi: this.solved ? this.solved.psi : 0, relativeHead: !this.opts.body,
    }) : null;
    if (this.faceRes && !this.faceRes.ok) this.chip('face', this.faceRes.message, 'warn');
    else this.chip('face', null);
    const N = this.clean.t.length;
    this.loop = { a: 0, b: N - 1, found: false };
    if (this.useLoop && this.solved && N > 45 && !this._loopSet) this.findLoop(false);
    this.cursor = this.loop.a;
  }

  _flattenHead(poses) {
    // "Also copy head turns" off: the head and neck ride with the chest
    const rp = this.rp;
    for (const pose of poses) {
      rp.resetPose(); rp.setPose(pose);
      const Dc = spaceQuat(rp, rp.bone('b__Spine2__')).multiply(rp.restQuat('b__Spine2__').clone().invert());
      for (const b of ['b__Neck__', 'b__Head__']) {
        const want = Dc.clone().multiply(rp.restQuat(b));
        const parent = spaceQuat(rp, rp.bone(b).parent);
        rp.bone(b).quaternion.copy(parent.invert().multiply(want)).normalize();
        pose.rot[b] = rp.bone(b).quaternion.toArray();
      }
    }
  }

  findLoop(animate = true) {
    const poses = this.solved && this.solved.poses;
    if (!poses) return;
    const N = poses.length;
    const r = findLoop(poses, { minFrames: Math.min(30, N - 2), maxFrames: N });
    const closed = closeLoop(poses, this.faceRes && this.faceRes.ok ? this.faceRes.faces : null, r.a, r.b);
    this.loop = { a: r.a, b: r.b, found: true, seam: seamError(closed.poses) };
    this._loopSet = true;
    if (animate) this._placeHandles(true);
  }

  // ---------------------------------------------------------------- 4. check and trim
  _render_check(P, F) {
    const N = this.clean ? this.clean.t.length : 0;
    const face = this.opts.face && this.faceRes && this.faceRes.ok;
    P.append(h('div', { class: 'cap-card' }, h('h3', {}, $t('capture.check_and_trim')),
      h('p', {}, $t('capture.green_is_clear_yellow_is')),
      this.opts.body ? h('button', { class: 'btn soft block cap-loop-btn', onclick: () => { this.findLoop(true); this.render(); } }, icon('loop'), $t('capture.find_best_loop')) : null,
      this.loop && this.loop.found ? h('div', { class: 'cap-ok' }, icon('check'), $t('capture.loops_smoothly')) : null));
    const sl = h('input', { type: 'range', min: 0, max: 1, step: 0.05, value: this.smooth });
    sl.addEventListener('change', () => { this.smooth = +sl.value; this._reprocess(); });
    P.append(h('div', { class: 'cap-slider' }, h('div', { class: 'cap-slider-ends' }, h('span', {}, $t('capture.smooth')), h('span', {}, $t('capture.detailed'))), sl));
    if (face) {
      const ex = h('input', { type: 'range', min: 1, max: 1.6, step: 0.05, value: this.exaggerate });
      ex.addEventListener('change', () => { this.exaggerate = +ex.value; this._reprocess(); });
      P.append(h('div', { class: 'cap-slider' }, h('div', { class: 'cap-slider-ends' }, h('span', {}, $t('capture.face_as_it_was')), h('span', {}, $t('capture.stronger_face'))), ex));
    }
    const sw = h('div', { class: 'cap-switches' });
    if (this.opts.body) {
      sw.append(this._switch($t('capture.keep_feet_on_floor'), null, this.feet, v => { this.feet = v; this._reprocess(); }),
        this._switch($t('capture.stay_in_place'), null, this.stay, v => { this.stay = v; this._reprocess(); }));
    }
    sw.append(this._switch($t('capture.also_copy_head_turns'), null, this.headTurns, v => { this.headTurns = v; this._reprocess(); }));
    if (this.opts.body) sw.append(this._switch($t('capture.swap_left_and_right'), $t('capture.if_sim_moves_wrong_arm'), this.swap, v => { this.swap = v; this._reprocess(); }));
    P.append(sw);
    // the timeline: quality strip, loop handles, the playhead
    this.qCanvas = h('canvas', { class: 'cap-quality' });
    this.hA = h('div', { class: 'cap-handle loop' }); this.hB = h('div', { class: 'cap-handle loop' });
    this.playhead = h('div', { class: 'cap-playhead' });
    this.loopSel = h('div', { class: 'cap-strip-sel' });
    const tl = h('div', { class: 'cap-timeline' }, this.qCanvas, this.loopSel, this.hA, this.hB, this.playhead);
    this.tl = tl;
    const playBtn = h('button', { class: 'icon-btn cap-play', title: $t('capture.play_space'), onclick: () => this.togglePlay() }, icon(this.playing ? 'pause' : 'play'));
    this.playBtn = playBtn;
    const before = h('div', { class: 'seg-inline cap-ba' },
      h('button', { class: this.before ? 'on' : '', onclick: () => { this.before = true; this.render(); this._show(this.cursor); } }, $t('capture.before')),
      h('button', { class: this.before ? '' : 'on', onclick: () => { this.before = false; this.render(); this._show(this.cursor); } }, $t('capture.after')));
    F.append(playBtn, tl, before, h('button', { class: 'btn primary big cap-go', disabled: !N, onclick: () => { this.playing && this.togglePlay(); this._setStep('apply'); } }, $t('capture.next'), icon('arrow')));
    requestAnimationFrame(() => { this._drawQuality(); this._placeHandles(false); this._wireTimeline(); this._show(this.cursor || 0); });
  }

  _reprocess() {
    const keepLoop = this.loop && this.loop.found ? { ...this.loop } : null;
    this.process();
    if (keepLoop && this.solved) { this.loop = keepLoop; const c = closeLoop(this.solved.poses, null, keepLoop.a, keepLoop.b); this.loop.seam = seamError(c.poses); }
    this.render();
  }

  _drawQuality() {
    const c = this.qCanvas;
    if (!c || !this.clean) return;
    const w = c.clientWidth || 400, hh = c.clientHeight || 34, d = Math.min(2, devicePixelRatio || 1);
    c.width = w * d; c.height = hh * d;
    const g = c.getContext('2d');
    g.scale(d, d);
    const q = this.solved ? this.solved.quality : (this.clean.people[0].quality || []);
    const N = this.clean.t.length;
    for (let i = 0; i < N; i++) {
      const v = q[i] ?? 1;
      g.fillStyle = v >= 0.75 ? '#34d399' : v >= 0.45 ? '#fbbf24' : '#fb5471';
      const x0 = i / N * w, x1 = (i + 1) / N * w + 0.6;
      g.globalAlpha = 0.9;
      g.fillRect(x0, hh - 7, x1 - x0, 5);
    }
    g.globalAlpha = 1;
    // the motion's own energy as a soft wave above it (so you can see where things happen)
    if (this.solved) {
      g.strokeStyle = 'rgba(255,255,255,.28)'; g.lineWidth = 1.2; g.beginPath();
      const P = this.solved.poses;
      let max = 1e-6;
      const e = P.map((p, i) => { if (!i) return 0; let s = 0; for (const b of ['b__L_Hand__', 'b__R_Hand__', 'b__Pelvis__', 'b__L_Foot__', 'b__R_Foot__']) { const a = p.rot[b], bb = P[i - 1].rot[b]; if (a && bb) s += 1 - Math.abs(a[0] * bb[0] + a[1] * bb[1] + a[2] * bb[2] + a[3] * bb[3]); } max = Math.max(max, s); return s; });
      e.forEach((v, i) => { const x = i / N * w, y = hh - 10 - (v / max) * (hh - 14); i ? g.lineTo(x, y) : g.moveTo(x, y); });
      g.stroke();
    }
  }

  _placeHandles(animate) {
    if (!this.hA || !this.clean) return;
    const N = this.clean.t.length;
    const a = this.loop.a / N * 100, b = this.loop.b / N * 100;
    for (const el of [this.hA, this.hB, this.loopSel]) el.classList.toggle('slide', !!animate && !reduced());
    this.hA.style.left = a + '%'; this.hB.style.left = b + '%';
    this.loopSel.style.left = a + '%'; this.loopSel.style.width = (b - a) + '%';
  }

  _wireTimeline() {
    const tl = this.tl;
    if (!tl || tl._wired) return;
    tl._wired = true;
    const N = this.clean.t.length;
    const frameAt = x => { const r = tl.getBoundingClientRect(); return Math.max(0, Math.min(N - 1, Math.round((x - r.left) / r.width * N))); };
    const dragHandle = (el, which) => el.addEventListener('pointerdown', e => {
      e.preventDefault(); e.stopPropagation(); el.setPointerCapture(e.pointerId);
      const move = ev => {
        const f = frameAt(ev.clientX);
        if (which === 'a') this.loop.a = Math.min(f, this.loop.b - 12); else this.loop.b = Math.max(f, this.loop.a + 12);
        this.loop.found = false;
        this._placeHandles(false);
        this._show(which === 'a' ? this.loop.a : this.loop.b);
      };
      const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); this.render(); };
      el.addEventListener('pointermove', move); el.addEventListener('pointerup', up);
    });
    dragHandle(this.hA, 'a'); dragHandle(this.hB, 'b');
    tl.addEventListener('pointerdown', e => {
      if (e.target.classList.contains('cap-handle')) return;
      const move = ev => this._show(frameAt(ev.clientX));
      move(e);
      tl.setPointerCapture(e.pointerId);
      const up = () => { tl.removeEventListener('pointermove', move); tl.removeEventListener('pointerup', up); };
      tl.addEventListener('pointermove', move); tl.addEventListener('pointerup', up);
    });
  }

  // show frame i of the cleaned take: the video there, the sim in the preview, the playhead
  _show(i) {
    if (!this.clean) return;
    const N = this.clean.t.length;
    i = Math.max(0, Math.min(N - 1, Math.round(i)));
    this.cursor = i;
    if (this.playhead) this.playhead.style.left = (i / N * 100) + '%';
    const t = this.clean.t[i];
    if (this.video && !this.playing) this._seek(t);
    const face = this.faceRes && this.faceRes.ok ? this.faceRes.faces[i] : null;
    if (this.before) {
      const s = this.app.store.sim(this.target), p = this.app.store.project;
      const f = (i - this.loop.a) % Math.max(1, p.length);
      this.preview.setPose(s ? A.evaluate(s.keys, f, p.length, p.loop) : null, s ? A.evaluateFace(s.keys, f, p.length, p.loop) : null);
    } else if (this.solved) this.preview.setPose(this.solved.poses[i], face);
    else if (this.basePose) this.preview.setPose(this._headOnBase(this.basePose, i), face);
    // the skeleton of that frame over the video
    const pe = this.clean.people[0];
    const fr = { pose: { world: pe.pose.subarray(i * 132, i * 132 + 132), img: pe.img.subarray(i * 99, i * 99 + 99) }, hands: {} };
    this._drawSkeleton(fr);
  }

  _headOnBase(base, i) {
    // a face-only take: the sim's own pose with the head turns from the face
    const d = this.faceRes && this.faceRes.ok && this.headTurns ? this.faceRes.headDelta[i] : null;
    if (!d) return base;
    const rp = this.rp;
    rp.resetPose(); rp.setPose(base);
    const pose = { rot: { ...base.rot }, pos: { ...base.pos } };
    for (const [b, k] of [['b__Neck__', 0.4], ['b__Head__', 1]]) {
      const bone = rp.bone(b);
      const sq = spaceQuat(rp, bone);
      const turn = new THREE.Quaternion().slerp(d, k === 1 ? 0.6 : k);
      const want = turn.multiply(sq);
      const parent = spaceQuat(rp, bone.parent);
      bone.quaternion.copy(parent.invert().multiply(want)).normalize();
      pose.rot[b] = bone.quaternion.toArray();
    }
    return pose;
  }

  togglePlay() {
    this.playing = !this.playing;
    if (this.playBtn) { this.playBtn.innerHTML = ''; this.playBtn.append(icon(this.playing ? 'pause' : 'play')); }
    if (!this.playing) { cancelAnimationFrame(this._raf); if (this.video && this.video.pause) this.video.pause(); return; }
    let last = performance.now(), f = this.cursor || this.loop.a;
    const step = now => {
      if (!this.playing || this.closed) return;
      f += (now - last) / 1000 * 30; last = now;
      if (f >= this.loop.b) f = this.loop.a + (f - this.loop.b);
      this._show(Math.floor(f));
      if (this.video) this._seek(this.clean.t[Math.floor(f)]);
      this._raf = requestAnimationFrame(step);
    };
    this._raf = requestAnimationFrame(step);
  }

  // ---------------------------------------------------------------- 5. put it on
  _render_apply(P, F) {
    const app = this.app, p = app.store.project;
    const len = this._takeLength();
    // with a partner in the scene the length stays as it is unless asked: a new length stretches everyone's moves
    const others = p.sims.filter(s => s.id !== this.target);
    if (this.fitLength === undefined) this.fitLength = !others.length && this.useLoop;
    const stretchNote = !others.length ? null : others.length === 1
      ? $t('capture.s_animation_is_stretched_to', { vLabel: others[0].label })
      : $t('capture.other_sims_animations_are_stretched');
    const sel = h('select', { class: 'cap-select' }, p.sims.map(s => h('option', { value: s.id, selected: s.id === this.target }, s.label)));
    sel.addEventListener('change', () => { this.target = sel.value; this._readSim(); const s = app.store.sim(this.target); this.root.style.setProperty('--sim', s.color); this.render(); });
    const at = Math.round(app.store.frame);
    const radio = (val, label) => {
      const r = h('input', { type: 'radio', name: 'cap-mode', value: val, checked: this.mode === val });
      r.addEventListener('change', () => { this.mode = val; this.render(); });
      return h('label', { class: 'cap-radio' + (this.mode === val ? ' on' : '') }, r, h('span', {}, label));
    };
    P.append(h('div', { class: 'cap-card' }, h('h3', {}, $t('capture.put_it_on')),
      h('div', { class: 'cap-put' }, h('span', {}, $t('capture.put_it_on_2')), sel),
      radio('replace', $t('capture.replace_whole_animation')),
      radio('insert', $t('capture.only_here_from', { at: secs(at / p.fps) })),
      this.mode === 'replace' ? this._switch($t('capture.make_animation_this_long', { len: secs(len / 30) }),
        this.fitLength && Math.round(len) !== p.length ? stretchNote : null, this.fitLength, v => { this.fitLength = v; this.render(); }) : null,
      h('p', { class: 'cap-fine' }, $t('capture.one_ctrl_z_takes_it'))));
    const go = h('button', { class: 'btn primary big cap-go cap-make' }, icon('key'), $t('capture.make_keys'));
    go.onclick = () => this.makeKeys(go);
    F.append(h('button', { class: 'btn ghost', onclick: () => this._setStep('check') }, icon('prev'), $t('capture.back')), h('div', { class: 'grow' }), go);
  }

  // after "Make the animation this long": say the new length, and whose moves were stretched along
  _lengthNote(s, lenBefore) {
    const p = this.app.store.project;
    if (p.length === lenBefore) return '';
    const others = p.sims.filter(x => x.id !== s.id);
    const who = !others.length ? '' : others.length === 1 ? $t('capture.s_animation_was_stretched_to', { vLabel: others[0].label }) : $t('capture.other_sims_animations_were_stretched');
    return $t('capture.animation_is_long_now', { pCount: secs(p.length / p.fps), who });
  }

  _takeLength() {
    if (!this.clean) return 0;
    return this.loop ? this.loop.b - this.loop.a : this.clean.t.length;
  }

  _result() {
    const faceOk = this.opts.face && this.faceRes && this.faceRes.ok;
    const faces = faceOk ? this.faceRes.faces : null;
    const { a, b } = this.loop;
    if (this.solved) {
      if (this.useLoop && this.loop.found) return closeLoop(this.solved.poses, faces, a, b);
      return { poses: this.solved.poses.slice(a, b + 1), faces: faces ? faces.slice(a, b + 1) : null };
    }
    // face only: the sim's own body (with head turns when asked)
    const s = this.app.store.sim(this.target), p = this.app.store.project;
    const poses = [], fs = [], turns = [];
    const start = this.mode === 'insert' ? Math.round(this.app.store.frame) : 0;
    for (let i = a; i <= b; i++) {
      const f = (start + i - a) % Math.max(1, p.length);
      const base = s ? A.evaluate(s.keys, f, p.length, p.loop) : null;
      poses.push(base ? this._headOnBase(base, i) : { rot: {}, pos: {} });
      fs.push(faces ? faces[i] : null);
      turns.push(!!(this.headTurns && this.faceRes && this.faceRes.headDelta[i]));
    }
    return { poses, faces: fs, headTurns: turns };
  }

  async makeKeys(btn) {
    const app = this.app, s = app.store.sim(this.target), p = app.store.project;
    if (!s) return;
    const res = this._result();
    const faceOnly = !this.solved;
    let fit = this.mode === 'replace' ? (this.fitLength ? true : null) : null;
    if (faceOnly && this.mode === 'replace' && !this.fitLength) {
      // a face take keeps its own timing: cut to the animation's length instead of stretching it
      res.poses = res.poses.slice(0, p.length); res.faces = res.faces && res.faces.slice(0, p.length);
      if (res.headTurns) res.headTurns = res.headTurns.slice(0, p.length);
      fit = res.poses.length;
    }
    const at = Math.round(app.store.frame);
    const lenBefore = p.length;
    let count;
    try {
      count = applyToSim(app, s.id, res, { mode: this.mode, at, fitLength: fit, detail: this.smooth, faceOnly, headTurns: res.headTurns, source: this.source });
    } catch (e) { this.chip('err', e.message || String(e), 'warn'); return; }
    // particles from the button toward the timeline, then the new keys pop in one by one
    try {
      const fx = await import('./fx.js').catch(() => null);
      const r = btn.getBoundingClientRect();
      if (fx && fx.burst && !reduced()) fx.burst(r.left + r.width / 2, r.top + r.height / 2, { count: 36, power: 0.9 });
    } catch { /* no particles */ }
    const src = this.source === 'webcam' ? $t('capture.your_webcam') : this.source === 'face' ? $t('capture.your_face') : this.source === 'photo' ? $t('capture.your_picture') : $t('capture.your_video_2');
    const text = this.source === 'photo' ? $t('capture.pose_from_your_picture_put', { sLabel: s.label, at: (at / p.fps).toFixed(2) })
      : $t('capture.made_keys_on_from_undo', { count, sLabel: s.label, src, _lengthNote: this._lengthNote(s, lenBefore) });
    const keys = s.keys.map(k => k.frame);
    try { app.emit && app.emit('keyed', { simId: s.id, frame: keys[0] || 0, kind: 'add' }); } catch { /* optional */ }
    this.close(true);
    toast(text, 'ok');
    const tl = app.timeline;
    if (tl && typeof tl.flash === 'function' && !reduced()) {
      const list = app.store.sim(s.id).keys.slice(0, 48);
      list.forEach((k, i) => setTimeout(() => { try { tl.flash(s.id, k.frame, 'add'); } catch { /* gone */ } }, 120 + i * 28));
    }
  }

  // ---------------------------------------------------------------- webcam
  _render_pickCam(P, F) {
    const face = this.source === 'face';
    P.append(h('div', { class: 'cap-card' },
      h('h3', {}, face ? $t('capture.copy_your_face') : $t('capture.act_it_out_yourself')),
      h('p', {}, face ? $t('capture.sit_close_to_camera_in')
        : $t('capture.stand_back_so_your_whole')),
      !face ? h('button', { class: 'btn small ghost', onclick: () => this._switchSource('video') }, icon('cap-video'), $t('capture.use_video_instead')) : null));
    P.append(this._adultBox());
    const rec = h('button', { class: 'btn primary big cap-go', disabled: !this.adult || !this.cam }, icon('rec'), $t('capture.record'));
    rec.onclick = () => this.countIn();
    F.append(h('div', { class: 'cap-foot-note' }, !this.adult ? $t('capture.tick_box_to_go_on') : !this.cam ? $t('capture.starting_camera') : $t('capture.space_starts_and_stops')), h('div', { class: 'grow' }), rec);
    if (!this.cam && !this._camStarting) this._startCamera();
  }

  async _startCamera() {
    this._camStarting = true;
    try {
      let v;
      if (this.mock) {
        const motion = await loadMockMotion();
        const take = takeFromMotion(this.app.assets.rig, motion, { seconds: 20, face: true, hands: true, noise: 0.002 });
        v = new MockVideo(take, { live: true });
        await v.play();
      } else {
        this.stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' }, audio: false });
        v = h('video', { class: 'cap-video', muted: true, playsinline: true, autoplay: true });
        v.muted = true;
        v.srcObject = this.stream;
        await new Promise(r => v.addEventListener('loadedmetadata', r, { once: true }));
        await v.play();
      }
      if (this.closed) { this._stopCamera(); return; }
      this.cam = v;
      this.video = v;
      this.media.innerHTML = '';
      this.media.append(v.el || v);
      this.stage.classList.add('mirror');           // your webcam shows like a mirror (the reading is never mirrored)
      this._fitOverlay();
      this.render();
      const tr = await this._tracker();
      this._liveLoop(tr);
    } catch (e) {
      this.chip('cam', e && e.name === 'NotAllowedError' ? $t('capture.camera_was_not_allowed') : $t('capture.no_camera_found_plug_one'), 'warn');
    } finally { this._camStarting = false; }
  }

  _stopCamera() {
    this._live = false;
    if (this.stream) { for (const t of this.stream.getTracks()) t.stop(); this.stream = null; }
    if (this.cam && this.cam.pause) this.cam.pause();
    this.cam = null;
  }

  // live checks while waiting: the skeleton, "feet in view", "good light"
  _liveLoop(tr) {
    this._live = true;
    const face = this.source === 'face';
    const light = document.createElement('canvas'); light.width = 32; light.height = 18;
    let lastLight = 0;
    const W = this.cam.videoWidth, H = this.cam.videoHeight;
    const step = () => {
      if (!this._live || this.closed || !this.cam || this.recording) return;
      try {
        const fr = detectFrame(tr, this.cam, performance.now(), { W, H });
        this._drawSkeleton(fr);
        if (!face) {
          const po = fr.pose && fr.pose.world;
          const feet = po && po[27 * 4 + 3] >= 0.5 && po[28 * 4 + 3] >= 0.5;
          this.chip('feet', feet ? $t('capture.feet_in_view') : $t('capture.step_back_until_your_feet'), feet ? 'ok' : 'warn');
          if (po) { const one = this._oneFrameTake(fr); this.preview.setPose(solveOne(this.solver, one, 0, 0, { facing: this.facing, psi: this._psiFor(one), base: this.basePose })); }
        } else {
          this.chip('facein', fr.face ? $t('capture.face_found') : $t('capture.look_at_camera'), fr.face ? 'ok' : 'warn');
        }
        const now = performance.now();
        if (now - lastLight > 500) {
          lastLight = now;
          const g = light.getContext('2d', { willReadFrequently: true });
          g.drawImage(this.cam.el || this.cam, 0, 0, 32, 18);
          const d = g.getImageData(0, 0, 32, 18).data;
          let sum = 0; for (let k = 0; k < d.length; k += 4) sum += 0.2126 * d[k] + 0.7152 * d[k + 1] + 0.0722 * d[k + 2];
          const lum = sum / (d.length / 4) / 255;
          this.chip('light', lum > 0.18 ? $t('capture.good_light') : $t('capture.more_light_please'), lum > 0.18 ? 'ok' : 'warn');
        }
      } catch (e) { console.warn('capture: live', e); }
      if (this.cam.requestVideoFrameCallback) this.cam.requestVideoFrameCallback(step); else requestAnimationFrame(step);
    };
    step();
  }

  async countIn() {
    if (!this.adult || !this.cam || this.recording || this.counting) return;
    this.counting = true;
    this._setStep('record');
    for (const nmb of [3, 2, 1]) {
      if (this.closed) return;
      this.countEl.classList.remove('hidden');
      this.countEl.innerHTML = '';
      this.countEl.append(h('b', { class: 'pop' }, String(nmb)));
      await new Promise(r => setTimeout(r, window.__captureFast ? 60 : 1000));
    }
    this.countEl.classList.add('hidden');
    this.counting = false;
    this.record();
  }

  async record() {
    const tr = await this._tracker();
    this.recording = true;
    this.root.classList.add('rec');
    this.render();
    const face = this.source === 'face';
    if (face) {
      this.chip('cal', $t('capture.look_at_camera_with_relaxed'), 'soft');
      this._calRing();
      setTimeout(() => { if (this.recording) { this.chip('cal', $t('capture.hold_t_to_stick_your'), 'soft'); } }, 2000);
    }
    this.abort = new AbortController();
    this._tongue = 0; this._tongueTarget = 0;
    let lastT = performance.now();
    const keys = { tongue: () => { const now = performance.now(), dt = (now - lastT) / 1000; lastT = now; this._tongue += Math.sign(this._tongueTarget - this._tongue) * Math.min(Math.abs(this._tongueTarget - this._tongue), dt / 0.2); return this._tongue; } };
    let preview = 0;
    this.raw = await trackWebcam(tr, this.cam, {
      signal: this.abort.signal, keys,
      onFrame: (fr, t) => {
        this._drawSkeleton(fr);
        if (this.recStat) this.recStat.textContent = secs(t);
        const now = performance.now();
        if (!face && fr.pose && now - preview > 45) {
          preview = now;
          const one = this._oneFrameTake(fr);
          this.preview.setPose(solveOne(this.solver, one, 0, 0, { facing: this.facing, psi: this._psi ?? (this._psi = this._psiFor(one)), base: this.basePose }));
        }
        if (face && fr.face && this.basePose) this.preview.setPose(this.basePose, null);
      },
    });
    this.recording = false;
    this.root.classList.remove('rec');
    this.chip('cal', null);
    this._live = false;
    if (!this.raw || this.raw.t.length < 5) { this.chip('short', $t('capture.that_was_too_short_try'), 'warn'); this._setStep('pick'); this._liveLoop(tr); return; }
    this.process();
    this._setStep('check');
  }

  _render_record(P, F) {
    const face = this.source === 'face';
    P.append(h('div', { class: 'cap-card' }, h('h3', {}, this.recording ? $t('capture.recording') : $t('capture.get_ready_2')),
      h('p', {}, face ? $t('capture.make_your_faces_sim_copies') : $t('capture.act_it_out_sim_copies')),
      h('div', { class: 'cap-rec-time' }, h('span', { class: 'cap-rec-dot' }), this.recStat = h('span', {}, '0.0 s'))));
    F.append(h('div', { class: 'cap-foot-note' }, $t('capture.space_stops')), h('div', { class: 'grow' }),
      h('button', { class: 'btn primary big cap-go', disabled: !this.recording, onclick: () => this.abort && this.abort.abort() }, icon('pause'), $t('capture.stop')));
  }

  _calRing() {
    this.ringBox.classList.remove('hidden');
    const t0 = performance.now();
    const tick = () => {
      const f = Math.min(1, (performance.now() - t0) / 2000);
      this._ring(f, $t('capture.relaxed_face'));
      if (f < 1 && !this.closed) requestAnimationFrame(tick); else setTimeout(() => this.ringBox.classList.add('hidden'), 250);
    };
    tick();
  }

  // ---------------------------------------------------------------- photo
  _render_pickPhoto(P, F) {
    if (!this.photo && !this._photoZone) { this._photoZone = true; this._dropZone('image/*', $t('capture.drop_picture_here_or_click'), $t('capture.photo_types_hint')); }
    if (this.mock && !this.photo && !this._mockPhotoing) {
      this._mockPhotoing = true;
      loadMockMotion().then(m => {
        const take = takeFromMotion(this.app.assets.rig, m, { seconds: 4, face: true, hands: true });
        const v = new MockVideo(take); v.seek(2.3);
        this._setPhoto(v, $t('capture.test_picture'));
      });
    }
    P.append(h('div', { class: 'cap-card' }, h('h3', {}, this.photo ? $t('capture.your_picture_2') : $t('capture.pick_picture')),
      h('p', {}, this.photo ? (this.photoPose ? $t('capture.this_is_pose_app_read') : $t('capture.reading_pose')) : $t('capture.sim_takes_pose_in_picture'))));
    P.append(this._adultBox());
    const use = h('button', { class: 'btn primary big cap-go', disabled: !this.photoPose || !this.adult }, icon('check'), $t('capture.use_this_pose'));
    use.onclick = () => this.usePhoto(use);
    F.append(h('div', { class: 'cap-foot-note' }, !this.adult ? $t('capture.tick_box_to_go_on') : ''), h('div', { class: 'grow' }), use);
  }
  _render_photo(P, F) { this._render_pickPhoto(P, F); }

  async _setPhoto(img, name) {
    this.photo = img; this.video = img.record ? img : null;
    this.media.innerHTML = '';
    this.media.append(img.el || img);
    this._fitOverlay();
    this.render();
    try {
      const tr = await this._tracker(this.mock ? 'VIDEO' : 'IMAGE');
      const { take, record } = await trackPhoto(tr, img);
      this._drawSkeleton(record);
      if (!record.pose) { this.chip('photo', $t('capture.no_person_found_in_this'), 'warn'); return; }
      this.photoTake = take;
      const r = solveTake(take, 0, this.solver, { facing: this.facing, base: this.basePose, hands: true, fingers: true, stick: false });
      this.photoPose = r.poses[0];
      const face = faceTrack(take, 0, { relativeHead: false, still: true });
      this.photoFace = face.ok ? face.faces[0] : null;
      this.preview.setPose(this.photoPose, this.photoFace);
      this._setStep('photo');
    } catch (e) { this.chip('photo', $t('capture.picture_could_not_be_read', { message: e.message || e }), 'warn'); }
  }

  usePhoto(btn) {
    const app = this.app, s = app.store.sim(this.target);
    if (!s || !this.photoPose) return;
    this.mode = 'insert';
    const res = { poses: [this.photoPose], faces: this.photoFace ? [this.photoFace] : null };
    this.solved = { poses: res.poses };
    this.loop = { a: 0, b: 0 };
    this._resultOverride = res;
    const at = Math.round(app.store.frame);
    try { applyToSim(app, s.id, res, { mode: 'insert', at, detail: 0.5 }); } catch (e) { this.chip('err', e.message, 'warn'); return; }
    this.close(true);
    toast($t('capture.pose_from_your_picture_put', { sLabel: s.label, at: (at / app.store.project.fps).toFixed(2) }), 'ok');
    try { app.timeline && app.timeline.flash && !reduced() && app.timeline.flash(s.id, at, 'add'); } catch { /* optional */ }
  }

  // ---------------------------------------------------------------- the skeleton over the picture
  _fitOverlay() {
    const el = this.media.firstChild;
    const r = this.stage.getBoundingClientRect();
    const d = Math.min(2, devicePixelRatio || 1);
    this.overlay.width = Math.max(1, r.width * d); this.overlay.height = Math.max(1, r.height * d);
    // where the picture sits inside the stage (object-fit: contain)
    const vw = (this.video && this.video.videoWidth) || (el && (el.naturalWidth || el.width)) || 16, vh = (this.video && this.video.videoHeight) || (el && (el.naturalHeight || el.height)) || 9;
    const s = Math.min(r.width / vw, r.height / vh);
    this.box = { x: (r.width - vw * s) / 2, y: (r.height - vh * s) / 2, w: vw * s, h: vh * s, d };
  }
  _clearOverlay() { const g = this.overlay.getContext('2d'); g.clearRect(0, 0, this.overlay.width, this.overlay.height); }
  _drawSkeleton(fr) {
    if (!this.box) this._fitOverlay();
    const g = this.overlay.getContext('2d'), b = this.box, d = b.d;
    g.setTransform(d, 0, 0, d, 0, 0);
    g.clearRect(0, 0, this.overlay.width, this.overlay.height);
    if (!fr || !fr.pose) return;
    const img = fr.pose.img, vis = fr.pose.world;
    const P = j => [b.x + img[j * 3] * b.w, b.y + img[j * 3 + 1] * b.h];
    const ok = j => vis[j * 4 + 3] >= 0.4;
    const col = getComputedStyle(this.root).getPropertyValue('--sim').trim() || '#ff4f9a';
    const pulse = reduced() ? 1 : 1 + 0.25 * Math.sin(performance.now() / 220);
    g.lineCap = 'round';
    g.shadowColor = col; g.shadowBlur = 14;
    g.strokeStyle = col; g.lineWidth = 3.2;
    g.globalAlpha = 0.95;
    g.beginPath();
    for (const [a, c] of BONES) { if (!ok(a) || !ok(c)) continue; const A = P(a), C = P(c); g.moveTo(A[0], A[1]); g.lineTo(C[0], C[1]); }
    g.stroke();
    g.shadowBlur = 8;
    g.fillStyle = '#fff';
    for (let j = 0; j < 33; j++) { if (!ok(j) || (j > 0 && j < 11 && j !== 0)) continue; const A = P(j); g.beginPath(); g.arc(A[0], A[1], 3.4 * (j >= 11 ? pulse : 1), 0, Math.PI * 2); g.fill(); }
    if (fr.handsImg) for (const s of ['L', 'R']) {
      const hi = fr.handsImg[s];
      if (!hi) continue;
      g.lineWidth = 1.6; g.strokeStyle = col; g.beginPath();
      for (const [a, c] of HAND) { g.moveTo(b.x + hi[a * 3] * b.w, b.y + hi[a * 3 + 1] * b.h); g.lineTo(b.x + hi[c * 3] * b.w, b.y + hi[c * 3 + 1] * b.h); }
      g.stroke();
    }
    g.shadowBlur = 0; g.globalAlpha = 1;
  }

  // ---------------------------------------------------------------- keys and closing
  _key(e) {
    if (this.closed || !this.back.isConnected) return;
    const top = document.querySelector('#modal-root > .backdrop:last-child');
    if (top && top !== this.back) return;          // a confirm box over the studio has the keyboard
    const typing = e.target instanceof Element && e.target.matches('input:not([type=range]):not([type=checkbox]):not([type=radio]), select, textarea');
    if (e.type === 'keyup') {
      if (e.code === 'KeyT') this._tongueTarget = 0;
      return;
    }
    if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); this.tryClose(); return; }
    if (e.code === 'KeyT' && this.recording && this.source === 'face') { this._tongueTarget = 1; e.preventDefault(); e.stopImmediatePropagation(); return; }
    if (e.code === 'Space' && !typing) {
      e.preventDefault(); e.stopImmediatePropagation();
      if (e.repeat) return;
      if (this.source === 'webcam' || this.source === 'face') {
        if (this.recording) this.abort && this.abort.abort();
        else if (this.step === 'pick') this.countIn();
        else if (this.step === 'check') this.togglePlay();
      } else if (this.step === 'check') this.togglePlay();
      return;
    }
    // keys belong to the studio, never to the editor behind it (Ctrl+Z there would undo under the studio)
    if (!this.root.contains(e.target) || !typing) e.stopPropagation();
  }

  async tryClose() {
    if ((this.step === 'check' || this.step === 'apply') && this.clean) {
      const ok = await confirmBox($t('capture.leave_without_making_keys'), $t('capture.moves_that_were_read_are'), $t('capture.leave'), true);
      if (!ok) return;
    }
    this.close();
  }

  close(quiet = false, keepBack = false) {
    if (this.closed) return;
    this.closed = true;
    this.playing = false;
    cancelAnimationFrame(this._raf);
    try { this.abort && this.abort.abort(); } catch { /* done */ }
    this._stopCamera();
    if (this.video && this.video.pause) this.video.pause();
    try { this._tr && this._tr.close(); } catch { /* gone */ }
    for (const u of this._urls || []) URL.revokeObjectURL(u);
    document.removeEventListener('keydown', this._onKey, true);
    document.removeEventListener('keyup', this._onKey, true);
    try { this.preview.dispose(); } catch { /* gone */ }
    if (this.back && !keepBack) {
      this.back.classList.add('leaving');
      this.root.classList.remove('in');
      const b = this.back;
      setTimeout(() => b.remove(), reduced() ? 0 : 180);
    }
    try { this.app.vp && this.app.vp.resume && this.app.vp.resume(); } catch { /* fine */ }
    if (current === this) current = null;
  }
}

export { Studio };
