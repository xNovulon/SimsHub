// The live mirror in the studio (capture.md 9, "Webcam"): with the "Live mirror" switch the studio folds into a
// small panel over the main 3D view - your webcam picture with its glowing skeleton, Record and "Keep this pose" -
// and the selected sim (two sims for two people) copies you there, live. The main view keeps its own camera, keys
// and playback; nothing is keyed until you press K or record a take (Space). Mixed into the studio's class
// (capture.js), so the studio's own count-in, recording and Check step are used as they are.
import * as THREE from 'three';
import { h, icon, toast } from '../ui.js';
import { LiveMirror } from './mirror.js';
import { createWorkerTracker, detectFrame } from './tracker.js';

const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('reduce-motion');
const wantsWorker = () => {
  try { return !!window.__captureWorker || new URLSearchParams(location.search).has('captureWorker'); } catch { return false; }
};

export const dockMethods = {
  // the sims that copy you: the chosen one (and, for two people, the second one)
  _mirrorSims() {
    const ids = [this.target];
    if (this.twoPeople && this.assign && this.assign[1] && this.assign[1] !== this.target) ids.push(this.assign[1]);
    return ids.filter(id => this.app.store.sim(id));
  },

  _mirrorSwitch() {
    const ok = this.adult && this.cam;
    const sub = !this.adult ? 'Tick the box first' : !this.cam ? 'Starting the camera...' : this.twoPeople ? 'Both sims copy you two live in the big view' : 'Your sim copies you live in the big view';
    const input = h('input', { type: 'checkbox', checked: !!this.docked || !!this.mirrorWanted, disabled: !ok && !this.mirrorWanted });
    input.addEventListener('change', () => {
      if (input.checked) { this.mirrorWanted = true; if (ok) this.startMirror(); else this.render(); }
      else { this.mirrorWanted = false; this.render(); }
    });
    return h('div', { class: 'toggle-row cap-switch cap-mirror-switch' + (ok || this.mirrorWanted ? '' : ' off') },
      h('div', {}, h('b', {}, 'Live mirror'), h('span', {}, sub)), h('label', { class: 'switch' }, input, h('span')));
  },

  // ---------------------------------------------------------------- on / off
  async startMirror() {
    if (this.docked || this.closed || !this.adult || !this.cam) return;
    this.mirrorWanted = false;
    this.docked = true;
    this._live = false;                                    // the pick step's own live check stops
    const ids = this._mirrorSims();
    this.mirror = new LiveMirror(this.app, { simIds: ids, solver: this.solver, hands: this.opts.hands, face: this.opts.face || this.source === 'face', smooth: this.smooth }).start();
    this._dock();
    this.chip('thread', 'Warming up the motion reader...', 'soft');
    try { this.mirrorTr = await this._mirrorTracker(); } catch (e) {
      this.chip('thread', 'The motion reader could not start: ' + (e.message || e), 'warn');
      return;
    }
    this.chip('thread', null);
    if (!this.docked || this.closed) { this._closeMirrorTracker(); return; }
    this._frameCamera();
    this._mirrorLoop();
    this.render();
  },

  stopMirror({ undock = true } = {}) {
    if (this.mirror) { this.mirror.stop(); this.mirror = null; }
    this._closeMirrorTracker();
    if (undock && this.docked) this._undock();
  },

  _closeMirrorTracker() {
    const tr = this.mirrorTr;
    this.mirrorTr = null;
    if (tr && tr !== this._tr) { try { tr.close(); } catch { /* gone */ } }
  },

  // The reader for the mirror: its own thread when it can have one (MediaPipe; the stand-in with ?captureWorker=1),
  // else the page's.
  async _mirrorTracker() {
    const worker = typeof Worker !== 'undefined' && (this.mock ? wantsWorker() : true);
    if (worker) {
      try {
        const tr = await createWorkerTracker({ body: true, hands: this.opts.hands, face: this.opts.face || this.source === 'face', quality: 'fast', people: this.twoPeople ? 2 : 1, mode: 'VIDEO' },
          { mockTake: this.mock && this.cam && this.cam.take ? this.cam.take : null });
        // one reader is enough: the page's goes (it is made again when the mirror stops)
        if (!this.mock && this._tr) { try { this._tr.close(); } catch { /* gone */ } this._tr = null; this._trPromise = null; }
        return tr;
      } catch (e) { console.warn('capture: the reader thread did not start - reading on the page instead.', e); }
    }
    return this._tracker();
  },

  _mirrorLoop() {
    const cam = this.cam, tr = this.mirrorTr;
    if (!cam || !tr) return;
    const W = cam.videoWidth, H = cam.videoHeight;
    let busy = false, lastUi = 0;
    const step = () => {
      if (!this.mirror || !this.mirror.on || this.closed || this.cam !== cam) return;
      if (!this.recording) {
        if (tr.detectAsync) {
          if (!busy) {
            busy = true;
            tr.detectAsync(cam, performance.now(), { W, H }).then(fr => this._mirrorFrame(fr, W, H)).catch(() => { /* one frame */ }).finally(() => { busy = false; });
          }
        } else {
          try { this._mirrorFrame(detectFrame(tr, cam, performance.now(), { W, H }), W, H); } catch (e) { console.warn('capture: mirror', e); }
        }
      }
      const now = performance.now();
      if (now - lastUi > 400) { lastUi = now; this._mirrorStatus(); }
      if (cam.requestVideoFrameCallback) cam.requestVideoFrameCallback(step); else requestAnimationFrame(step);
    };
    step();
  },

  _mirrorFrame(fr, W, H) {
    if (!this.mirror || this.closed) return;
    this.mirror.feed(fr, performance.now() / 1000, { W, H });
    this._drawSkeleton(fr);
    const po = fr.pose && fr.pose.world;
    const feet = po && po[27 * 4 + 3] >= 0.5 && po[28 * 4 + 3] >= 0.5;
    if (this.source !== 'face') this.chip('feet', !po ? 'Step into the picture' : feet ? 'Feet in view' : 'Step back until your feet are in view', feet ? 'ok' : 'warn');
    if (this.twoPeople && !(fr.others && fr.others[0] && fr.others[0].pose)) this.chip('two', 'Only one person in view', 'warn');
    else this.chip('two', null);
  },

  _mirrorStatus() {
    if (!this.mirror || !this.statEl) return;
    const f = this.mirror.fps();
    this.statEl.textContent = f.shown ? `Live - ${f.shown} moves a second` : 'Waiting for you...';
    this.statEl.classList.toggle('on', f.shown > 0);
  },

  // the main view looks at the sim's front (a mirror: you see it copy you face to face)
  _frameCamera() {
    const app = this.app, vp = app.vp;
    try {
      const views = this._mirrorSims().map(id => app.simViews.get(id)).filter(Boolean);
      if (!views.length || !vp || typeof vp.frame !== 'function') return;
      const c = new THREE.Vector3();
      for (const v of views) c.add(v.worldPos('b__Pelvis__'));
      c.multiplyScalar(1 / views.length);
      c.y = Math.max(0.55, c.y + 0.1);
      const f = this.facing || 0;
      vp.frame(c, views.length > 1 ? 1.5 : 1.15, new THREE.Vector3(Math.sin(f), 0.22, Math.cos(f)).normalize());
    } catch (e) { console.warn('capture: camera', e); }
  },

  // ---------------------------------------------------------------- the small panel over the view
  _dock() {
    const host = document.getElementById('viewport-wrap') || document.body;
    if (!this.dockHost) {
      this.dockCount = h('div', { class: 'cap-dock-count hidden' });
      this.dockHost = h('div', { class: 'cap-dock-host' }, this.dockCount);
    }
    host.append(this.dockHost);
    this.dockHost.append(this.root);
    this.back.remove();
    this.root.classList.add('docked');
    this.root.setAttribute('aria-modal', 'false');
    try { this.app.vp && this.app.vp.resume && this.app.vp.resume(); } catch { /* fine */ }
    requestAnimationFrame(() => { this._fitOverlay(); });
    this.render();
  },

  _undock() {
    this.docked = false;
    this.root.classList.remove('docked');
    this.root.setAttribute('aria-modal', 'true');
    (document.getElementById('modal-root') || document.body).append(this.back);
    this.back.append(this.root);
    if (this.dockHost) this.dockHost.remove();
    try { this.app.vp && this.app.vp.pause && this.app.vp.pause(); } catch { /* fine */ }
    this.chip('feet', null); this.chip('two', null); this.chip('thread', null);
    requestAnimationFrame(() => { this._fitOverlay(); try { this.preview.resize(); } catch { /* gone */ } });
    this.root.focus({ preventScroll: true });
  },

  _render_dock(P, F) {
    const app = this.app;
    const names = this._mirrorSims().map(id => app.store.sim(id)).filter(Boolean).map(s => s.label);
    const who = names.length > 1 ? `${names[0]} and ${names[1]} copy you two` : `${names[0] || 'Your sim'} copies you`;
    this.statEl = h('span', { class: 'cap-dock-stat' }, 'Waiting for you...');
    if (this.recording || this.counting) {
      P.append(h('div', { class: 'cap-dock-line rec' }, h('span', { class: 'cap-rec-dot' }), h('b', {}, this.recording ? 'Recording' : 'Get ready...'),
        this.recStat = h('span', { class: 'cap-dock-time' }, '0.0 s')));
      F.append(h('div', { class: 'grow' }),
        h('button', { class: 'btn primary cap-go cap-dock-rec', disabled: !this.recording, onclick: () => this.abort && this.abort.abort() }, icon('pause'), 'Stop (Space)'));
      return;
    }
    P.append(h('div', { class: 'cap-dock-line' }, h('span', { class: 'cap-live-dot' }), h('b', {}, who), this.statEl));
    F.append(
      h('button', { class: 'btn small ghost cap-dock-back', title: 'Back to the full capture studio', onclick: () => { this.stopMirror(); this.render(); this._restartLive(); } }, icon('prev'), 'Studio'),
      h('div', { class: 'grow' }),
      h('button', { class: 'btn small soft cap-dock-keep', title: 'Key this pose at the current frame (K)', onclick: () => this.keepPose() }, icon('key'), 'Keep pose'),
      h('button', { class: 'btn small primary cap-dock-rec', title: 'Record a take: 3-2-1, then act it out (Space)', onclick: () => this.countIn() }, icon('rec'), 'Record'));
    this._mirrorStatus();
  },

  async _restartLive() {
    try { const tr = await this._tracker(); if (!this.closed && !this.docked && this.cam && !this.recording) this._liveLoop(tr); } catch { /* the chip says so */ }
  },

  keepPose() {
    if (!this.mirror || !this.adult) return;
    const app = this.app, f = Math.round(app.store.frame), p = app.store.project;
    const done = this.mirror.keep();
    if (!done.length) { toast('Step into the picture first - then K keeps your pose.'); return; }
    const names = done.map(id => app.store.sim(id).label);
    toast(`Pose kept on ${names.join(' and ')} at ${(f / (p.fps || 30)).toFixed(2)} s. Undo with Ctrl+Z.`, 'ok');
    try { app.emit && app.emit('keyed', { simId: done[0], frame: f, kind: 'add' }); } catch { /* optional */ }
    if (!reduced()) for (const id of done) try { app.timeline && app.timeline.flash && app.timeline.flash(id, f, 'add'); } catch { /* optional */ }
  },
};
