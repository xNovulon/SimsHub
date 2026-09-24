// "Import a motion file": a BVH from a mocap library (CMU, Mixamo converted to BVH) or a free AI video tool
// (Rokoko Vision, DeepMotion, Plask) put on a sim as keys. The file is read in the browser (nothing is uploaded or
// written), turned into a capture take and put on through the capture's own pipeline (capture/bvh.js solveFile ->
// capture/keys.js applyToSim), so it behaves like "Copy real moves": one Ctrl+Z takes it all back.
// Opened by features/mocapfile.js (Pose step, Library, Ctrl+K, a .bvh dropped on the stage).
import * as THREE from 'three';
import { h, icon, modal, toast, choiceBar } from './ui.js';
import * as A from './animation.js';
import * as KO from './keyops.js';
import { spaceQuat } from './posemath.js';
import { RigPose } from './capture/rigpose.js';
import { Solver } from './capture/retarget.js';
import { applyToSim } from './capture/keys.js';
import { parseBVH, analyze, fk, solveFile, formatProblem, BVHError, MAX_SECONDS } from './capture/bvh.js';

const OPTS_KEY = 'wa.mocapfile.opts';
const MAX_BYTES = 200 * 1024 * 1024;
const secs = s => (Math.round(s * 10) / 10).toFixed(1);
const loadOpts = () => { try { return JSON.parse(localStorage.getItem(OPTS_KEY) || '{}') || {}; } catch { return {}; } };
const saveOpts = o => { try { localStorage.setItem(OPTS_KEY, JSON.stringify(o)); } catch { /* private window */ } };
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('reduce-motion');

let current = null;          // the open dialog (a second open only hands it the file)

export function isOpen() { return !!(current && !current.closed); }

// openMotionFile(app, {file, simId}) - the dialog; with a file it is read at once
export function openMotionFile(app, { file = null, simId = null } = {}) {
  if (isOpen()) { if (file) current.load(file); return current; }
  const d = new MotionFileDialog(app, simId || (app.store.selected && app.store.selected.sim));
  current = d;
  if (file) d.load(file);
  return d;
}

class MotionFileDialog {
  constructor(app, simId) {
    this.app = app;
    this.simId = simId;
    this.closed = false;
    this.file = null; this.bvh = null; this.info = null;
    const o = { every: 'smart', place: 'stay', height: 'file', loop: 'best', smooth: false, fingers: true, mirror: false, fit: true, mode: 'replace', ...loadOpts() };
    this.o = o;
    this.frame = 0; this.playing = !reduced();
    this.root = h('div', { class: 'mf' });
    this.input = h('input', { type: 'file', accept: '.bvh,.fbx', class: 'mf-input', onchange: () => { const f = this.input.files && this.input.files[0]; this.input.value = ''; if (f) this.load(f); } });
    const m = modal({
      title: 'Import a motion file',
      text: 'A BVH file from a motion-capture library or a free AI video tool (Rokoko Vision, DeepMotion, Plask) becomes keys on a sim.',
      body: h('div', {}, this.input, this.root),
      wide: true,
      onClose: () => { this.closed = true; cancelAnimationFrame(this._raf); if (current === this) current = null; },
      buttons: [
        { label: 'Cancel', kind: 'ghost' },
        { label: 'Make keys', kind: 'primary', onClick: () => this.makeKeys() },
      ],
    });
    this.modal = m;
    m.dialog.classList.add('mf-dialog');
    this.go = m.footer.querySelector('.btn.primary');
    this.warnings = [];
    this.render();
    // the keyboard starts on the drop zone (Enter or Space picks a file)
    setTimeout(() => { const z = this.root.querySelector('.mf-drop'); if (z && !this.closed) z.focus({ preventScroll: true }); }, 60);
  }

  // ---------------------------------------------------------------- reading the file
  async load(file) {
    this.error = null; this.warnings = [];
    this.file = file; this.bvh = null; this.info = null;
    this.busy = 'Reading ' + file.name + '...';
    this.render();
    try {
      if (file.size > MAX_BYTES) throw new BVHError(`That file is ${(file.size / 1048576).toFixed(0)} MB - more than this app reads at once. Cut it into a shorter part first.`);
      const head = await file.slice(0, 64).text();
      const fmt = formatProblem(file.name, head);
      if (fmt) throw new BVHError(fmt);
      const text = await file.text();
      if (this.closed || this.file !== file) return;
      const bvh = parseBVH(text);
      const info = analyze(bvh);
      this.warnings = bvh.warnings.slice();
      if (info.missing.length) {
        throw new BVHError(`This skeleton isn't one the app recognises: it can't find the ${info.missing.slice(0, 6).join(', ')}${info.missing.length > 6 ? '...' : ''}. `
          + 'Files from Mixamo, CMU, Rokoko, DeepMotion, Plask, Daz and 3ds Max Biped skeletons work; a skeleton with other joint names needs to be renamed first.');
      }
      this.bvh = bvh; this.info = info;
      const dur = (bvh.frames - 1) * bvh.frameTime;
      this.from = 0;
      this.len = Math.min(dur, MAX_SECONDS);
      if (dur > MAX_SECONDS) this.warnings.push(`The file is ${secs(dur)} s long; up to ${MAX_SECONDS} s are read at once - pick the part below.`);
      this.frame = 0;
    } catch (e) {
      if (!(e instanceof BVHError)) console.error('motion file', e);
      this.error = e instanceof BVHError ? e.message : 'That file could not be read: ' + (e && e.message ? e.message : e);
    }
    this.busy = null;
    this.render();
  }

  // ---------------------------------------------------------------- the dialog
  render() {
    if (this.closed) return;
    const root = this.root;
    root.innerHTML = '';
    this.go.disabled = !this.bvh || !!this.busy;
    if (!this.bvh) {
      root.append(this._pick());
      if (this.busy) root.append(h('div', { class: 'mf-msg' }, this.busy));
      if (this.error) root.append(h('div', { class: 'mf-msg err', role: 'alert' }, icon('mf-warn'), h('span', {}, this.error)));
      return;
    }
    const o = this.o, bvh = this.bvh, info = this.info, app = this.app, p = app.store.project;
    const dur = (bvh.frames - 1) * bvh.frameTime;
    // the preview and what the file is
    this.canvas = h('canvas', { class: 'mf-canvas', width: 360, height: 300 });
    this.scrub = h('input', { type: 'range', class: 'mf-scrub', min: 0, max: 1000, value: 0 });
    this.scrub.addEventListener('input', () => { this.playing = false; this._syncPlay(); this.frame = this._range()[0] + (+this.scrub.value / 1000) * (this._range()[1] - this._range()[0]); this.draw(); });
    this.playBtn = h('button', { class: 'icon-btn sm', title: 'Play / pause', onclick: () => { this.playing = !this.playing; this._syncPlay(); if (this.playing) this._loop(); } }, icon('play'));
    this.clock = h('span', { class: 'mf-clock' });
    const fingers = info.fingers.L || info.fingers.R;
    const facts = [
      `${info.style === 'Other' ? 'Skeleton' : info.style + ' skeleton'} · ${info.joints} joints`,
      `${bvh.frames.toLocaleString()} frames at ${Math.round(bvh.fps * 100) / 100} fps (${secs(dur)} s)`,
      `${info.restPose} · ${info.up} · ${info.units}`,
      fingers ? 'Has fingers' : 'No fingers (hands follow the wrists)',
    ];
    const left = h('div', { class: 'mf-left' },
      h('div', { class: 'mf-stage' }, this.canvas),
      h('div', { class: 'mf-bar' }, this.playBtn, this.scrub, this.clock),
      h('div', { class: 'mf-file' }, icon('mf-bvh'), h('b', { title: this.file.name }, this.file.name),
        h('button', { class: 'btn small ghost', onclick: () => this.input.click() }, 'Another file')),
      h('ul', { class: 'mf-facts' }, facts.map(f => h('li', {}, f))));
    // the part
    const start = h('input', { class: 'text', type: 'number', min: 0, max: Math.max(0, dur - 0.1).toFixed(1), step: 0.1, value: secs(this.from) });
    const len = h('input', { class: 'text', type: 'number', min: 0.2, max: Math.min(MAX_SECONDS, dur).toFixed(1), step: 0.1, value: secs(this.len) });
    const onRange = () => {
      this.from = Math.max(0, Math.min(dur - 0.1, +start.value || 0));
      this.len = Math.max(0.2, Math.min(MAX_SECONDS, dur - this.from, +len.value || 0));
      this.frame = this._range()[0];
      this.draw();
      this._lengthNote();
    };
    start.addEventListener('change', () => { onRange(); start.value = secs(this.from); len.value = secs(this.len); });
    len.addEventListener('change', () => { onRange(); len.value = secs(this.len); });
    const sel = (key, opts, onChange) => {
      const s = h('select', {}, opts.map(([v, t]) => h('option', { value: v, selected: String(o[key]) === v }, t)));
      s.addEventListener('change', () => { o[key] = s.value; saveOpts(o); onChange && onChange(); });
      return s;
    };
    const check = (key, label, title) => {
      const c = h('input', { type: 'checkbox', checked: !!o[key] });
      c.addEventListener('change', () => { o[key] = c.checked; saveOpts(o); if (key === 'fit') this._lengthNote(); });
      return h('label', { class: 'check', title: title || null }, c, label);
    };
    const sims = p.sims;
    if (!sims.find(s => s.id === this.simId)) this.simId = sims.length ? sims[0].id : null;
    const simSel = sims.length ? h('select', { class: 'mf-sim' }, sims.map(s => h('option', { value: s.id, selected: s.id === this.simId }, s.label || s.id))) : null;
    if (simSel) simSel.addEventListener('change', () => { this.simId = simSel.value; });
    const at = Math.round(app.store.frame || 0);
    const place = sel('place', [['stay', 'Stay in place (keeps sways and bounces)'], ['travel', 'Keep the travel from the file']], () => this.render());
    const loopSel = sel('loop', [['best', 'Find the best loop in this part'], ['none', 'Use the part as it is']]);
    if (o.place === 'travel') { loopSel.value = 'none'; loopSel.disabled = true; }
    this.lengthNote = h('div', { class: 'hint mf-len' });
    const right = h('div', { class: 'mf-right' },
      h('div', { class: 'grid-2' },
        h('label', { class: 'field' }, h('span', {}, 'Put it on'), simSel || h('span', { class: 'muted' }, 'A new sim')),
        h('label', { class: 'field' }, h('span', {}, 'Key spacing'), sel('every', [['smart', 'Smart - keys only where needed'], ['3', 'Every 3 frames (very detailed)'], ['6', 'Every 6 frames'], ['10', 'Every 10 frames'], ['15', 'Every 15 frames (simple)']])),
        h('label', { class: 'field' }, h('span', {}, 'Start at (seconds)'), start),
        h('label', { class: 'field' }, h('span', {}, 'Length (seconds)'), len),
        h('label', { class: 'field' }, h('span', {}, 'Where the hips go'), place),
        h('label', { class: 'field' }, h('span', {}, 'Height'), sel('height', [['file', 'As in the file (jumps stay jumps)'], ['floor', 'Keep the feet on the floor']])),
        h('label', { class: 'field' }, h('span', {}, 'Loop'), loopSel),
        h('label', { class: 'field' }, h('span', {}, 'Put it'), sel('mode', [['replace', 'Replace the whole animation'], ['insert', `Only here (from ${secs(at / (p.fps || 30))} s)`]], () => this.render()))),
      o.place === 'travel' ? h('div', { class: 'hint' }, 'A loop can\'t travel (the sim would jump back at the end), so the part is used as it is.') : null,
      h('div', { class: 'mf-checks' },
        o.mode === 'replace' ? check('fit', 'Make the animation as long as this part') : null,
        check('smooth', 'Smooth out small shakes', 'For files from AI video tools, which can tremble a little. Clean studio mocap needs no smoothing.'),
        fingers ? check('fingers', 'Copy the fingers') : null,
        check('mirror', 'Swap left and right', 'If the sim moves the wrong arm or leg')),
      this.lengthNote,
      h('p', { class: 'hint' }, 'The sim keeps its place and the way it faces; the file\'s moves are fitted to its body. One Ctrl+Z takes it all back.'));
    root.append(h('div', { class: 'mf-main' }, left, right));
    if (this.warnings.length) root.append(h('div', { class: 'mf-msg warn' }, icon('mf-warn'), h('span', {}, this.warnings.join(' '))));
    if (this.error) root.append(h('div', { class: 'mf-msg err', role: 'alert' }, icon('mf-warn'), h('span', {}, this.error)));
    if (this.busy) root.append(h('div', { class: 'mf-msg' }, this.busy));
    this._lengthNote();
    this._fit = null;
    this._syncPlay();
    this.draw();
    if (this.playing) this._loop();
  }

  _pick() {
    const zone = h('div', { class: 'mf-drop', tabindex: '0', role: 'button', 'aria-label': 'Choose a BVH file',
      onclick: () => this.input.click(), onkeydown: e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.input.click(); } } },
    h('span', { class: 'mf-drop-icon' }, icon('mf-bvh')),
    h('b', {}, 'Drop a .bvh file here'),
    h('span', {}, 'or click to choose one'),
    h('button', { class: 'btn soft', type: 'button', onclick: e => { e.stopPropagation(); this.input.click(); } }, icon('folder'), 'Choose a BVH file'));
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('over'));
    zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('over'); const f = e.dataTransfer && e.dataTransfer.files[0]; if (f) this.load(f); });
    return h('div', { class: 'mf-pick' }, zone,
      h('ul', { class: 'mf-tips' },
        h('li', {}, h('b', {}, 'BVH files. '), 'DeepMotion, Plask and Rokoko Vision offer BVH next to FBX when you download; pick BVH. The CMU mocap library comes as BVH too.'),
        h('li', {}, h('b', {}, 'FBX can\'t be read here. '), 'Mixamo only downloads FBX - convert it to BVH first (for example with Blender\'s BVH export).'),
        h('li', {}, 'Adults only. The file is read on this PC and never uploaded.')));
  }

  _range() {
    const ft = this.bvh.frameTime;
    const a = Math.round(this.from / ft), b = Math.min(this.bvh.frames - 1, Math.round((this.from + this.len) / ft));
    return [a, Math.max(a, b)];
  }

  _lengthNote() {
    if (!this.lengthNote || !this.bvh) return;
    const p = this.app.store.project, n = Math.round(this.len * 30) + 1;
    const others = p.sims.filter(s => s.id !== this.simId).length;
    this.lengthNote.textContent = this.o.mode === 'replace' && this.o.fit && others
      ? `The animation becomes about ${secs(n / 30)} s long; the other sims' moves are stretched to match.` : '';
  }

  _syncPlay() {
    if (!this.playBtn) return;
    this.playBtn.innerHTML = '';
    this.playBtn.append(icon(this.playing ? 'pause' : 'play'));
  }

  _loop() {
    cancelAnimationFrame(this._raf);
    let last = performance.now();
    const step = now => {
      if (this.closed || !this.playing || !this.bvh) return;
      const [a, b] = this._range();
      this.frame += ((now - last) / 1000) / this.bvh.frameTime; last = now;
      if (this.frame > b || this.frame < a) this.frame = a;
      this.draw();
      this._raf = requestAnimationFrame(step);
    };
    this._raf = requestAnimationFrame(step);
  }

  // the file's skeleton, seen from a little to the side of its front (its own rest axes)
  draw() {
    const c = this.canvas, bvh = this.bvh, info = this.info;
    if (!c || !bvh || !c.isConnected) return;
    const g = c.getContext('2d');
    const W = c.width, H = c.height;
    const [a, b] = this._range();
    const f = Math.max(a, Math.min(b, Math.round(this.frame)));
    const F = info.frame;
    const L = new THREE.Vector3().fromArray(F.left), U = new THREE.Vector3().fromArray(F.up), Fw = new THREE.Vector3().fromArray(F.fwd);
    const yaw = 0.45;
    const proj = (P, j) => { const v = new THREE.Vector3(P[j * 3], P[j * 3 + 1], P[j * 3 + 2]); const x = v.dot(L), z = v.dot(Fw); return [x * Math.cos(yaw) + z * Math.sin(yaw), v.dot(U)]; };
    const hipsJ = info.roles.L.thigh;
    if (!this._fit || this._fit.key !== `${a}-${b}`) {
      // the height over the part (sampled), the body's width around its hips
      let lo = Infinity, hi = -Infinity, wd = 0;
      for (let k = 0; k <= 24; k++) {
        const P = fk(bvh, Math.round(a + (b - a) * k / 24)).P;
        const hx = proj(P, hipsJ)[0];
        for (let j = 0; j < bvh.joints.length; j++) { const [x, y] = proj(P, j); lo = Math.min(lo, y); hi = Math.max(hi, y); wd = Math.max(wd, Math.abs(x - hx)); }
      }
      const s = Math.min((H - 36) / Math.max(1e-6, hi - lo), (W - 40) / Math.max(1e-6, 2 * wd));
      this._fit = { key: `${a}-${b}`, lo, s };
    }
    const { lo, s } = this._fit;
    const P = fk(bvh, f).P;
    const hx = proj(P, hipsJ)[0];
    const X = x => W / 2 + (x - hx) * s, Y = y => H - 18 - (y - lo) * s;
    g.clearRect(0, 0, W, H);
    g.strokeStyle = 'rgba(255,255,255,.08)'; g.lineWidth = 1;
    g.beginPath(); g.moveTo(12, H - 18); g.lineTo(W - 12, H - 18); g.stroke();
    const sim = this.app.store.sim(this.simId);
    const col = (sim && sim.color) || '#ff4f9a';
    const R = info.roles;
    const limb = new Set([R.L.shoulder, R.L.elbow, R.L.wrist, R.L.thigh, R.L.knee, R.L.ankle, R.R.shoulder, R.R.elbow, R.R.wrist, R.R.thigh, R.R.knee, R.R.ankle]);
    const left = new Set([R.L.elbow, R.L.wrist, R.L.knee, R.L.ankle]);
    g.lineCap = 'round';
    bvh.joints.forEach((jt, j) => {
      if (jt.parent < 0) return;
      const [x0, y0] = proj(P, jt.parent), [x1, y1] = proj(P, j);
      const main = limb.has(j) && limb.has(jt.parent);
      g.strokeStyle = main ? (left.has(j) ? col : '#c9d9ff') : 'rgba(220,210,240,.55)';
      g.lineWidth = main ? 4 : 2;
      g.beginPath(); g.moveTo(X(x0), Y(y0)); g.lineTo(X(x1), Y(y1)); g.stroke();
    });
    const [hx0, hy0] = proj(P, R.head);
    g.fillStyle = 'rgba(220,210,240,.8)';
    g.beginPath(); g.arc(X(hx0), Y(hy0), Math.max(4, 0.05 * (info.height || 0) * s), 0, Math.PI * 2); g.fill();
    if (this.scrub && document.activeElement !== this.scrub) this.scrub.value = String(Math.round(b > a ? ((f - a) / (b - a)) * 1000 : 0));
    if (this.clock) this.clock.textContent = `${secs(f * bvh.frameTime)} s`;
  }

  // ---------------------------------------------------------------- putting it on
  async makeKeys() {
    if (!this.bvh) return false;
    const app = this.app, o = this.o;
    const btn = this.go;
    const label = btn.textContent;
    btn.textContent = 'Working...';
    this.error = null;
    await new Promise(r => setTimeout(r, 30));
    try {
      let p = app.store.project;
      if (!p.sims.length && typeof app.newScene === 'function') { app.newScene(false, false, 'solo'); p = app.store.project; }
      const s = app.store.sim(this.simId) || p.sims[0];
      if (!s) throw new Error('Add a sim to the scene first.');
      const { base, facing } = readSim(app, s.id);
      const [a, b] = this._range();
      if (!this._solver || this._solver.rig !== app.assets.rig) { this._solver = new Solver(app.assets.rig); this._solver.rig = app.assets.rig; }
      const travel = o.place === 'travel';
      const r = solveFile(this.bvh, this.info, this._solver, {
        from: a, to: b, smooth: !!o.smooth, stay: !travel, ground: o.height === 'floor' ? 'floor' : 'lowest', mirror: !!o.mirror,
        fingers: o.fingers !== false, loop: !travel && o.loop === 'best' ? 'best' : 'none', facing, base,
      });
      const res = r.result;
      const lenBefore = p.length;
      const at = Math.round(app.store.frame || 0);
      const every = o.every === 'smart' ? null : +o.every;
      const count = applyToSim(app, s.id, res, { mode: o.mode, at, fitLength: o.mode === 'replace' && o.fit ? true : null, detail: 0.5, every, source: 'file' });
      try { app.emit && app.emit('keyed', { simId: s.id, frame: 0, kind: 'add' }); } catch { /* optional */ }
      const lenNote = p.length !== lenBefore ? ` The animation is ${secs(p.length / (p.fps || 30))} s long now.` : '';
      const loopNote = r.loop ? ' It loops.' : '';
      toast(`Made ${count} key${count === 1 ? '' : 's'} on ${s.label || 'the sim'} from ${this.file.name}.${loopNote}${lenNote} Undo with Ctrl+Z.`, 'ok');
      // a part used as it is often doesn't loop cleanly: offer the app's own loop fix (as "Import as keys" does)
      if (!r.loop && p.loop && o.mode === 'replace') {
        const pop = KO.loopCheck(p).filter(x => x.kind === 'pop' && x.simId === s.id);
        if (pop.length) {
          setTimeout(() => choiceBar("This part doesn't loop smoothly - the end jumps back to the start.", [
            { label: 'Blend the end into the start', primary: true, onClick: () => {
              app.store.checkpoint('Blend the end into the start');
              KO.fixLoop(p, app.store.sim(s.id), 'pop');
              app.keysChanged && app.keysChanged(); app.afterEdit && app.afterEdit();
              toast('The end now flows back into the start.', 'ok');
            } },
          ], { timeout: 16000 }), 400);
        }
      }
      return true;
    } catch (e) {
      console.error('motion file', e);
      this.error = 'The moves could not be put on: ' + (e && e.message ? e.message : e);
      btn.textContent = label;
      this.render();
      return false;
    }
  }
}

// Where the sim is now: its pose at the playhead (its hips' place and floor) and the way it faces - the same rule as
// the capture studio (capture.js _readSim).
export function readSim(app, simId) {
  const s = app.store.sim(simId), p = app.store.project;
  const f = Math.round(app.store.frame || 0);
  const base = s && s.keys.length ? A.evaluate(s.keys, f, p.length, p.loop) : null;
  const rp = new RigPose(app.assets.rig);
  rp.resetPose(); if (base) rp.setPose(base); rp.fk();
  const q = spaceQuat(rp, rp.bone('b__Pelvis__'));
  const fwd = new THREE.Vector3(0, 1, 0).applyQuaternion(q), left = new THREE.Vector3(0, 0, -1).applyQuaternion(q);
  let facing = Math.hypot(fwd.x, fwd.z) >= Math.hypot(left.x, left.z) ? Math.atan2(fwd.x, fwd.z) : Math.atan2(-left.z, left.x);
  try {
    const v = app.simViews && app.simViews.get(simId);
    if (v && typeof app._facing === 'function') { const fq = app._facing(v); facing = 2 * Math.atan2(fq.y, fq.w); }
  } catch { /* keep ours */ }
  return { base, facing };
}
