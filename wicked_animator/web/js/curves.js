// The Curves view (spec_editing 6): how the selected part turns over time. One line per channel (Bend / Twist / Tilt
// for a body part, Height / Forward / Side for the hips, the face sliders), the keys as dots you drag up and down,
// the segment between two keys opens its timing. It shares the ruler, the zoom and the key selection with the
// timeline. Curves show the keys only (motions, pins and physics come on top; "With motions" shows that too).
import * as THREE from 'three';
import { evaluate, evaluateFace, evaluateFaceBones, EASE_INFO, EASE_CURVE, EASES, easeFn, validCurve, restOf } from './animation.js';
import { drawRuler } from './timeline.js';
import * as KO from './keyops.js';
import * as B from './bones.js';
import * as PM from './posemath.js';
import { FACE_SLIDERS } from './face.js';
import { h, icon, toast, contextMenu, fillRange } from './ui.js';
import { localStorageGet, localStorageSet } from './state.js';

const GUTTER = 168, RULER = 28;
const DEG = 180 / Math.PI;
const FONT = 'Plus Jakarta Sans, Segoe UI, sans-serif';
const MONO = 'JetBrains Mono, monospace';
const reducedMotion = () => (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  || document.documentElement.classList.contains('reduce-motion');
const clone = x => JSON.parse(JSON.stringify(x));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const FACE_SET = B.FACE_SET || new Set();
const HIPS = B.HIPS || ['b__Spine0__', 'b__Pelvis__'];

// Bend / Twist / Tilt from standing (degrees), and back (the inspector's numbers).
export function restEuler(q, r) {
  const e = new THREE.Euler().setFromQuaternion(r.clone().invert().multiply(q), 'XYZ');
  return [e.x * DEG, e.y * DEG, e.z * DEG];
}
export function fromRestEuler(r, deg) {
  return r.clone().multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(deg[0] / DEG, deg[1] / DEG, deg[2] / DEG, 'XYZ')));
}

// The parts the bar offers (the selected part first).
const PARTS = [
  ['b__Pelvis__', 'Hips'], ['b__Spine0__', 'Lower back'], ['b__Spine1__', 'Middle back'], ['b__Spine2__', 'Chest'], ['b__Neck__', 'Neck'], ['b__Head__', 'Head'],
  ['b__Jaw__', 'Jaw'], ['face', 'Face sliders'],
  ...['L', 'R'].flatMap(s => { const w = s === 'L' ? 'left' : 'right'; return [[`b__${s}_Clavicle__`, `Shoulder (${w})`], [`b__${s}_UpperArm__`, `Upper arm (${w})`], [`b__${s}_Forearm__`, `Forearm (${w})`],
    [`b__${s}_Hand__`, `Hand (${w})`], [`b__${s}_Thigh__`, `Thigh (${w})`], [`b__${s}_Calf__`, `Shin (${w})`], [`b__${s}_Foot__`, `Foot (${w})`]]; }),
  ['b__Penis_Base', 'Penis'], ['b__Tounge__1', 'Tongue'],
];
const ROT = [
  { id: 'rx', label: 'Bend', color: '#ff5d7a', axis: 0 },
  { id: 'ry', label: 'Twist', color: '#3ddc97', axis: 1 },
  { id: 'rz', label: 'Tilt', color: '#57b8ff', axis: 2 },
];
const POS = [
  { id: 'up', label: 'Height', color: '#ffb547', axis: 0 },
  { id: 'fwd', label: 'Forward', color: '#c9a7ff', axis: 1 },
  { id: 'side', label: 'Side', color: '#ff8a5b', axis: 2 },
];
const FACE_SHADES = ['#ff7ab6', '#ff9ecb', '#e85d9f', '#ffb3d6', '#d9468a', '#ff8fc0'];
const niceStep = (pxPerUnit, units) => { for (const u of units) if (u * pxPerUnit >= 28) return u; return units[units.length - 1]; };

export class CurveView {
  constructor(canvas, bar, app) {
    this.canvas = canvas;
    this.bar = bar;
    this.app = app;
    this.ctx = canvas.getContext('2d');
    this.shown = false;
    this.part = null;                 // the part picked in the bar (else the selected part, else the last one, else Hips)
    this.lastPart = 'b__Pelvis__';
    this.hidden = new Set(localStorageGet('curveChannelsOff', []));
    this.withMotions = false;
    this.smoothScope = 'body';        // Smooth: 'body' (whole body) or 'part' (this part)
    this.vCenter = 0;                 // the value at the middle of the plot
    this.vScale = 2;                  // pixels per unit
    this._framed = '';
    this.series = null;
    this._sig = '';
    this.drag = null;
    this.hover = null;
    this.box = null;
    new ResizeObserver(() => { if (this.shown) this.draw(); }).observe(canvas);
    canvas.addEventListener('pointerdown', e => this._down(e));
    window.addEventListener('pointermove', e => this._move(e));
    window.addEventListener('pointerup', e => this._up(e));
    canvas.addEventListener('pointermove', e => this._hoverAt(e));
    canvas.addEventListener('pointerleave', () => { this.hover = null; this.draw(); });
    canvas.addEventListener('wheel', e => this._wheel(e), { passive: false });
    canvas.addEventListener('contextmenu', e => this._context(e));
    canvas.addEventListener('dblclick', e => this._dbl(e));
  }

  get store() { return this.app.store; }
  get tl() { return this.app.timeline; }
  xAt(f) { return this.tl.xAt(f); }
  frameAt(x) { return this.tl.frameAt(x); }
  get plotTop() { return RULER + 4; }
  get plotH() { return Math.max(40, this.canvas.clientHeight - this.plotTop - 6); }
  yAt(v) { return this.plotTop + this.plotH / 2 - (v - this.vCenter) * this.vScale; }
  valAt(y) { return this.vCenter + (this.plotTop + this.plotH / 2 - y) / this.vScale; }

  show(on) {
    this.shown = !!on;
    if (on) { this._syncBar(true); this.invalidate(); requestAnimationFrame(() => { this.draw(true); if (this._framed !== this._key()) this.frameAll(); }); }
  }
  invalidate() { this._sig = ''; }

  // ---------------------------------------------------------------- what is shown
  sim() { return this.store.sim() || this.store.project.sims[0] || null; }
  currentPart() {
    const sel = this.store.selected.bone;
    const p = this.part || sel || this.lastPart || 'b__Pelvis__';
    return p;
  }
  _key() { const s = this.sim(); return `${s ? s.id : ''}|${this.currentPart()}`; }

  // the channels of the part: [{id, label, color, unit, kind: 'rot'|'pos'|'face', axis?, slider?, locked?}]
  channels() {
    const part = this.currentPart(), sim = this.sim();
    if (!sim) return [];
    if (part === 'face') {
      const used = new Set();
      for (const k of sim.keys) for (const n of Object.keys(k.face || {})) used.add(n);
      const list = [...used].filter(n => FACE_SLIDERS[n]);
      if (!list.length) list.push('open', 'smile', 'eyes');
      return list.map((n, i) => ({ id: 'face:' + n, label: (FACE_SLIDERS[n] || { label: n }).label.replace(/\s*\(.*\)$/, ''), color: FACE_SHADES[i % FACE_SHADES.length], unit: '%', kind: 'face', slider: n }));
    }
    const hinge = B.HINGE && B.HINGE[part];
    const out = ROT.map(c => ({ ...c, unit: '°', kind: 'rot', label: hinge && c.axis === 2 ? 'Bend (hinge)' : c.label, locked: !!(hinge && c.axis !== 2) }));
    if (part === 'b__Pelvis__') out.push(...POS.map(c => ({ ...c, unit: 'cm', kind: 'pos' })));
    return out;
  }
  _faceBone(part) { return FACE_SET.has(part); }

  // Every frame's value of every channel (keys only), plus the keys' own values. Rebuilt only when something changed.
  _build() {
    const sim = this.sim(), p = this.store.project;
    const part = this.currentPart();
    const sig = `${this.app.editRev}|${sim ? sim.id : ''}|${part}|${p.length}|${p.loop}|${p.autoCurve}|${this.withMotions}`;
    if (sig === this._sig && this.series) return this.series;
    const t0 = performance.now();
    this._sig = sig;
    const L = p.length, curve = p.autoCurve || 'legacy';
    const chans = this.channels();
    const out = { chans, values: {}, keys: [], motion: null, part };
    if (!sim) { this.series = out; return out; }
    for (const c of chans) out.values[c.id] = new Float64Array(L);
    const rest = restOf(part);
    const restQ = rest ? new THREE.Quaternion().fromArray(rest.r) : new THREE.Quaternion();
    const restP = rest ? rest.t : [0, 0, 0];
    const q = new THREE.Quaternion();
    if (part === 'face') {
      for (let f = 0; f < L; f++) {
        const fc = evaluateFace(sim.keys, f, L, p.loop) || {};
        for (const c of chans) out.values[c.id][f] = (fc[c.slider] || 0) * 100;
      }
      for (const k of sim.keys) if (k.face) out.keys.push({ key: k, frame: k.frame, v: Object.fromEntries(chans.map(c => [c.id, (k.face[c.slider] || 0) * 100])) });
    } else {
      const face = this._faceBone(part);
      // only this bone: a key list that carries just it (the same rest fallbacks as the whole pose)
      const src = k => (face ? k.faceBones : (!k.faceOnly ? k.pose : null));
      const lite = sim.keys.filter(k => src(k)).map(k => {
        const s = src(k), pose = { rot: {}, pos: {} };
        if (s.rot && s.rot[part]) pose.rot[part] = s.rot[part];
        if (part === 'b__Pelvis__') for (const n of HIPS) if (s.pos && s.pos[n]) pose.pos[n] = s.pos[n];
        return k.ease === 'custom' ? { frame: k.frame, ease: k.ease, curve: k.curve, pose } : { frame: k.frame, ease: k.ease, pose };
      });
      const valOf = pose => {
        const r = (pose && pose.rot && pose.rot[part]) || (rest && rest.r) || [0, 0, 0, 1];
        const e = restEuler(q.fromArray(r), restQ);
        const pp = (pose && pose.pos && pose.pos[part]) || restP;
        return [e[0], e[1], e[2], (pp[0] - restP[0]) * 100, (pp[1] - restP[1]) * 100, (pp[2] - restP[2]) * 100];
      };
      const prev = [0, 0, 0];
      for (let f = 0; f < L; f++) {
        // (face bones flow as they play: the face channel keeps the old Auto curve)
        const pose = lite.length ? evaluate(lite, f, L, p.loop, face ? 'legacy' : curve) : null;
        const v = valOf(pose);
        // unwrap: no step over 180 degrees
        for (let a = 0; a < 3; a++) { if (f) { while (v[a] - prev[a] > 180) v[a] -= 360; while (v[a] - prev[a] < -180) v[a] += 360; } prev[a] = v[a]; }
        for (const c of chans) out.values[c.id][f] = c.kind === 'rot' ? v[c.axis] : v[3 + c.axis];
      }
      for (const k of sim.keys) {
        const s = src(k);
        if (!s || k.frame >= L) continue;
        const v = valOf(s);
        const at = {};
        for (const c of chans) {
          let x = c.kind === 'rot' ? v[c.axis] : v[3 + c.axis];
          if (c.kind === 'rot') { const ser = out.values[c.id][Math.min(L - 1, k.frame)]; while (x - ser > 180) x -= 360; while (x - ser < -180) x += 360; }
          at[c.id] = x;
        }
        out.keys.push({ key: k, frame: k.frame, v: at });
      }
      if (this.withMotions) out.motion = this._motionSeries(sim, part, chans, restQ, restP);
    }
    out.ms = performance.now() - t0;
    this.lastBuildMs = out.ms;
    this.series = out;
    return out;
  }

  // "With motions": the final result (keys + motions + pins), cached by the pipeline's signature and the part.
  _motionSeries(sim, part, chans, restQ, restP) {
    const app = this.app, pl = app.pipeline, v = app.simViews.get(sim.id);
    if (!v || !v.bone(part) || part === 'face') return null;
    let sig = '';
    try { sig = (pl.signature ? pl.signature() : '') + '|' + part + '|' + sim.id; } catch { sig = ''; }
    if (sig && this._motionCache && this._motionCache.sig === sig) return this._motionCache.values;
    const L = this.store.project.length, values = {};
    for (const c of chans) values[c.id] = new Float64Array(L);
    const saved = pl.editing; pl.editing = null;
    const pending = new Map(pl.overrides); pl.overrides.clear();
    const prev = [0, 0, 0];
    try {
      for (let f = 0; f < L; f++) {
        pl.apply(f, { physics: false, overrides: false });
        const b = v.bone(part);
        const e = restEuler(b.quaternion, restQ);
        for (let a = 0; a < 3; a++) { if (f) { while (e[a] - prev[a] > 180) e[a] -= 360; while (e[a] - prev[a] < -180) e[a] += 360; } prev[a] = e[a]; }
        const pp = b.position;
        const pv = [(pp.x - restP[0]) * 100, (pp.y - restP[1]) * 100, (pp.z - restP[2]) * 100];
        for (const c of chans) values[c.id][f] = c.kind === 'rot' ? e[c.axis] : pv[c.axis];
      }
    } catch (err) { console.error(err); return null; }
    finally { pl.editing = saved; for (const [k, x] of pending) pl.overrides.set(k, x); app.applyPoses(false); }
    this._motionCache = { sig, values };
    return values;
  }

  // Zoom the values so every visible curve fits.
  frameAll() {
    const s = this._build();
    let lo = Infinity, hi = -Infinity;
    for (const c of s.chans) {
      if (this.hidden.has(c.id)) continue;
      for (const v of s.values[c.id]) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    }
    if (!Number.isFinite(lo)) { lo = -10; hi = 10; }
    lo = Math.min(lo, 0); hi = Math.max(hi, 0);
    const span = Math.max(8, hi - lo);
    this.vCenter = (lo + hi) / 2;
    this.vScale = (this.plotH * 0.84) / span;
    this._framed = this._key();
    this.draw(true);
  }

  // ---------------------------------------------------------------- the bar
  _syncBar(force = false) {
    const sim = this.sim(), p = this.store.project;
    const sig = `${sim ? sim.id : ''}|${this.currentPart()}|${this.store.selected.bone}|${[...this.hidden].join()}|${this.withMotions}|${p.autoCurve}|${this.smoothScope}|${this.app.timeline ? this.app.timeline.sel.size > 0 : ''}`;
    if (!force && sig === this._barSig) return;
    this._barSig = sig;
    const bar = this.bar;
    bar.innerHTML = '';
    if (!sim) { bar.append(h('span', { class: 'cb-label' }, 'Add a sim to see its curves.')); return; }
    const part = this.currentPart(), sel = this.store.selected.bone;
    const nameOf = n => (PARTS.find(x => x[0] === n) || [n, B.label ? B.label(n, sim.frame) : n])[1];
    const opts = [];
    if (sel && !PARTS.some(x => x[0] === sel)) opts.push([sel, `Selected: ${nameOf(sel)}`]);
    opts.push(...PARTS.filter(([n]) => n === 'face' || (this.app.simViews.get(sim.id)?.bone(n))));
    const select = h('select', { title: 'Which part the curves show (picking one selects it in the 3D view)' }, opts.map(([v, t]) => h('option', { value: v, selected: v === part }, t)));
    select.onchange = () => { this.pickPart(select.value); select.blur(); };
    bar.append(select);
    for (const c of this.channels()) {
      const b = h('button', { class: 'chipbtn' + (this.hidden.has(c.id) ? ' off' : ''), title: c.locked ? `${c.label}: a hinge only bends one way` : `Show / hide ${c.label}`, style: { '--c': c.color } },
        h('span', { class: 'sw' }), c.label);
      b.onclick = () => { if (this.hidden.has(c.id)) this.hidden.delete(c.id); else this.hidden.add(c.id); localStorageSet('curveChannelsOff', [...this.hidden]); this._syncBar(true); this.draw(true); };
      bar.append(b);
    }
    if (part !== 'face') bar.append(h('button', { class: 'chipbtn', title: 'The face sliders over time', onclick: () => this.pickPart('face') }, icon('face'), ' Face'));
    bar.append(h('span', { class: 'cb-sep' }));
    bar.append(h('button', { class: 'chipbtn', title: 'Zoom so every curve fits (F)', onclick: () => this.frameAll() }, 'Frame all'));
    const wm = h('button', { class: 'chipbtn' + (this.withMotions ? ' on' : ''), title: 'Also show the final motion (keys + motions + pins) as a dashed line' }, 'With motions');
    wm.onclick = () => { this.withMotions = !this.withMotions; this.invalidate(); this._syncBar(true); this.draw(true); };
    bar.append(wm);
    bar.append(h('span', { class: 'cb-sep' }));
    // Smooth: a live slider (one undo step); This part | Whole body
    const scope = h('div', { class: 'seg-inline', title: 'Smooth this part only, or the whole body' },
      h('button', { class: this.smoothScope === 'part' ? 'on' : '', onclick: () => { this.smoothScope = 'part'; this._syncBar(true); } }, 'This part'),
      h('button', { class: this.smoothScope === 'body' ? 'on' : '', onclick: () => { this.smoothScope = 'body'; this._syncBar(true); } }, 'Whole body'));
    const bones = () => (this.smoothScope === 'part' && part !== 'face' ? new Set(part === 'b__Pelvis__' ? HIPS : [part]) : null);
    const sm = h('input', { type: 'range', min: 0, max: 100, step: 1, value: 0, title: 'Smooth: drag to take out small shakes (on the selected keys, or every key of this sim)' });
    fillRange(sm);
    sm.addEventListener('pointerdown', () => this.app.smoothLive('start', 0, bones()));
    sm.addEventListener('input', () => this.app.smoothLive('input', +sm.value / 100, bones()));
    sm.addEventListener('change', () => { this.app.smoothLive('end', +sm.value / 100, bones()); sm.value = 0; fillRange(sm); sm.blur(); });
    bar.append(h('span', { class: 'cb-label' }, 'Smooth'), sm, scope);
    const simp = h('button', { class: 'chipbtn', title: 'Fewer keys - the motion stays within 1.5° (right-click for other amounts)' }, 'Simplify');
    simp.onclick = () => this.app.simplifySelection(1.5);
    simp.oncontextmenu = e => { e.preventDefault(); contextMenu(e.clientX, e.clientY, [{ heading: 'Keep the motion within' }, ...[0.5, 1.5, 3, 6].map(t => ({ label: `${t}°`, onClick: () => this.app.simplifySelection(t) }))]); };
    bar.append(simp, h('button', { class: 'chipbtn', title: 'Smooth a little, then fewer keys - for imported or captured motion', onclick: () => this.app.cleanUpSelection() }, 'Clean up'));
    bar.append(h('span', { class: 'cb-sep' }));
    const lc = h('button', { class: 'chipbtn', title: 'Does the end flow back into the start?' }, icon('loop'), ' Loop check');
    lc.onclick = () => { const r = lc.getBoundingClientRect(); this.app.loopMenu(r.left, r.top - 8 - 200); };
    bar.append(lc);
    if (p.autoCurve === 'legacy') {
      bar.append(h('button', { class: 'chipbtn on', title: 'Auto smooth keys then flow without overshooting, and two equal keys really hold still (this animation was made before)',
        onclick: () => { this.store.checkpoint('Smoother Auto curve'); p.autoCurve = 'clamped'; this.app.keysChanged(); this.app.afterEdit(); toast('The smoother Auto curve is on: no overshoot, holds stay still. Undo with Ctrl+Z.', 'ok'); } }, 'Use the smoother Auto curve'));
    }
  }

  pickPart(n) {
    this.part = n;
    if (n !== 'face') {
      this.lastPart = n;
      const sim = this.sim(), v = sim && this.app.simViews.get(sim.id);
      if (sim && v && v.bone(n)) {
        this.store.selected = { sim: sim.id, bone: n };
        const it = this.app.interact;
        if (FACE_SET.has(n)) { if (it.tool === 'face') it.selectFaceBone(sim.id, n); }
        else if (it.tool === 'rotate') it.selectBone(sim.id, n);
        this.app.emitSelection();
        this.part = null;                 // follow the selection from now on
      }
    }
    this.invalidate();
    this._syncBar(true);
    this.frameAll();
  }

  // ---------------------------------------------------------------- drawing
  draw(now = false) {
    if (!this.shown) return;
    if (!now) { if (this._raf) return; this._raf = requestAnimationFrame(() => { this._raf = 0; this.draw(true); }); return; }
    const c = this.canvas, dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth, hgt = c.clientHeight;
    if (!w || !hgt) return;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(hgt * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(hgt * dpr); }
    const t0 = performance.now();
    this._syncBar();
    const s = this._build();
    if (this._framed !== this._key()) { this._framed = this._key(); this.frameAll(); return; }
    const g = this.ctx, p = this.store.project, sim = this.sim();
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, hgt);
    const css = getComputedStyle(document.documentElement);
    const col = n => css.getPropertyValue(n).trim();
    const line = col('--line'), muted = col('--muted'), text = col('--text'), faint = col('--faint');
    const top = this.plotTop, bottom = top + this.plotH;
    // value grid: the nicest step giving >= 28 px, the zero line ("standing") brighter
    const units = s.chans.some(ch => ch.kind === 'rot') ? [1, 2, 5, 10, 15, 30, 45, 90, 180] : [1, 2, 5, 10, 20, 25, 50, 100];
    const step = niceStep(this.vScale, units);
    g.save(); g.beginPath(); g.rect(GUTTER, top, w - GUTTER, bottom - top); g.clip();
    const vLo = this.valAt(bottom), vHi = this.valAt(top);
    g.font = `500 10px ${MONO}`; g.textBaseline = 'middle';
    for (let v = Math.ceil(vLo / step) * step; v <= vHi; v += step) {
      const y = Math.round(this.yAt(v)) + 0.5;
      g.strokeStyle = v === 0 ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.05)';
      g.beginPath(); g.moveTo(GUTTER, y); g.lineTo(w, y); g.stroke();
      g.fillStyle = v === 0 ? muted : faint;
      g.fillText(v === 0 ? '0 standing' : String(Math.round(v * 10) / 10), GUTTER + 6, y - 7);
    }
    // past the end of the loop
    const endX = this.xAt(p.length);
    if (endX < w) { g.fillStyle = 'rgba(0,0,0,0.3)'; g.fillRect(Math.max(GUTTER, endX), top, w - Math.max(GUTTER, endX), bottom - top); }
    if (this.app.playRange) {
      const [a, b2] = this.app.playRange;
      g.fillStyle = 'rgba(0,0,0,0.18)';
      if (this.xAt(a) > GUTTER) g.fillRect(GUTTER, top, this.xAt(a) - GUTTER, bottom - top);
      if (this.xAt(b2) < Math.min(w, endX)) g.fillRect(this.xAt(b2), top, Math.min(w, endX) - this.xAt(b2), bottom - top);
    }
    const f0 = Math.max(0, Math.floor(this.frameAt(GUTTER)) - 1), f1 = Math.min(p.length - 1, Math.ceil(this.frameAt(w)) + 1);
    const zeroY = this.yAt(0);
    const sel = this.tl.sel;
    const visible = s.chans.filter(ch => !this.hidden.has(ch.id));
    // the final motion (dashed, faint)
    if (s.motion) for (const ch of visible) {
      const vals = s.motion[ch.id];
      if (!vals) continue;
      g.save(); g.setLineDash([4, 4]); g.strokeStyle = ch.color; g.globalAlpha = 0.45; g.lineWidth = 1.4;
      g.beginPath();
      for (let f = f0; f <= f1; f++) { const x = this.xAt(f), y = this.yAt(vals[f]); if (f === f0) g.moveTo(x, y); else g.lineTo(x, y); }
      g.stroke(); g.restore();
    }
    for (const ch of visible) {
      const vals = s.values[ch.id];
      if (!vals || f1 < f0) continue;
      // a soft fill toward zero, then the line with a glow
      g.beginPath();
      g.moveTo(this.xAt(f0), zeroY);
      for (let f = f0; f <= f1; f++) g.lineTo(this.xAt(f), this.yAt(vals[f]));
      g.lineTo(this.xAt(f1), zeroY); g.closePath();
      g.globalAlpha = 0.06; g.fillStyle = ch.color; g.fill(); g.globalAlpha = 1;
      g.beginPath();
      for (let f = f0; f <= f1; f++) { const x = this.xAt(f), y = this.yAt(vals[f]); if (f === f0) g.moveTo(x, y); else g.lineTo(x, y); }
      g.strokeStyle = ch.color; g.lineWidth = 2;
      if (ch.locked) g.setLineDash([5, 4]);
      if (!reducedMotion() && f1 - f0 < 1400) { g.shadowColor = ch.color; g.shadowBlur = 6; }
      g.stroke(); g.shadowBlur = 0; g.setLineDash([]);
    }
    // the hovered segment: thicker, with its timing's name
    const hv = this.hover;
    if (hv && hv.seg && !this.drag) {
      const { ch, a, b } = hv.seg, vals = s.values[ch.id];
      g.beginPath();
      for (let f = a; f <= b; f++) { const x = this.xAt(f % p.length), y = this.yAt(vals[f % p.length]); if (f === a) g.moveTo(x, y); else g.lineTo(x, y); }
      g.strokeStyle = ch.color; g.lineWidth = 3.2; g.stroke(); g.lineWidth = 1;
      const key = hv.seg.key, name = key.ease === 'custom' ? 'Custom curve' : (EASE_INFO[key.ease || 'auto'] || EASE_INFO.auto)[0];
      const mf = Math.round((a + b) / 2) % p.length, mx = this.xAt(mf), my = this.yAt(vals[mf]) - 16;
      g.font = `700 10.5px ${FONT}`;
      const tw = g.measureText(name).width + 14;
      g.fillStyle = 'rgba(20,14,25,0.92)'; g.beginPath(); g.roundRect(mx - tw / 2, my - 9, tw, 18, 9); g.fill();
      g.fillStyle = '#fff'; g.textAlign = 'center'; g.fillText(name, mx, my); g.textAlign = 'left';
    }
    // the keys: a dot per channel (selected: white with the sim's glow)
    for (const kk of s.keys) {
      const x = this.xAt(kk.frame);
      if (x < GUTTER - 8 || x > w + 8) continue;
      const on = sel.has(KO.kid(sim.id, kk.frame));
      for (const ch of visible) {
        const y = this.yAt(kk.v[ch.id]);
        g.beginPath(); g.arc(x, y, on ? 5.5 : 4.5, 0, Math.PI * 2);
        if (on) { g.shadowColor = sim.color; g.shadowBlur = 10; g.fillStyle = '#fff'; } else { g.fillStyle = ch.color; }
        g.fill(); g.shadowBlur = 0;
        g.strokeStyle = 'rgba(12,10,16,.85)'; g.lineWidth = 1.2; g.stroke(); g.lineWidth = 1;
      }
    }
    // the box being drawn
    if (this.box) {
      const b = this.box, x0 = Math.min(b.x0, b.x1), y0 = Math.min(b.y0, b.y1);
      g.fillStyle = 'rgba(255,79,154,.08)'; g.fillRect(x0, y0, Math.abs(b.x1 - b.x0), Math.abs(b.y1 - b.y0));
      g.save(); g.setLineDash([5, 4]); g.strokeStyle = '#ff8cc4'; g.strokeRect(x0 + 0.5, y0 + 0.5, Math.abs(b.x1 - b.x0), Math.abs(b.y1 - b.y0)); g.restore();
    }
    // a value being dragged: its number
    if (this.drag && this.drag.kind === 'value' && this.drag.moved) {
      const d = this.drag, x = this.xAt(d.frame), v = d.shown;
      const txt = `${d.ch.label} ${v >= 0 ? '+' : ''}${(Math.round(v * 10) / 10)}${d.ch.unit}`;
      g.font = `700 10.5px ${MONO}`;
      const tw = g.measureText(txt).width + 12, y = this.yAt(v) - 22;
      g.fillStyle = 'rgba(20,14,25,0.92)'; g.beginPath(); g.roundRect(x - tw / 2, y - 9, tw, 18, 7); g.fill();
      g.fillStyle = '#fff'; g.textAlign = 'center'; g.fillText(txt, x, y); g.textAlign = 'left';
    }
    g.restore();
    // the channel list's background, then the ruler (shared with the timeline) with the playhead through the plot
    g.fillStyle = col('--panel'); g.fillRect(0, 0, GUTTER, hgt);
    drawRuler(g, { x0: GUTTER, w, h: hgt, xAt: f => this.xAt(f), pxPerFrame: this.tl.pxPerFrame, scroll: this.tl.scroll, length: p.length, frame: this.store.frame,
      playing: !!this.app.playing, range: this.app.playRange, loopBadge: null, summary: null, css });
    // the channel list: swatch, name, the value at the playhead
    g.fillStyle = col('--panel'); g.fillRect(0, RULER + 1, GUTTER, hgt - RULER - 1);
    g.strokeStyle = line; g.beginPath(); g.moveTo(GUTTER + 0.5, RULER); g.lineTo(GUTTER + 0.5, hgt); g.stroke();
    g.font = `700 11.5px ${FONT}`; g.fillStyle = text; g.textBaseline = 'middle';
    const partName = s.part === 'face' ? 'Face sliders' : (PARTS.find(x => x[0] === s.part) || [0, B.label ? B.label(s.part, sim && sim.frame) : s.part])[1];
    g.fillText((sim ? sim.label + ' · ' : '') + partName, 12, 14);
    const fr = Math.max(0, Math.min(p.length - 1, Math.round(this.store.frame)));
    this._chanRows = [];
    s.chans.forEach((ch, i) => {
      const y = RULER + 14 + i * 22;
      if (y > hgt - 6) return;
      const off = this.hidden.has(ch.id);
      g.globalAlpha = off ? 0.4 : 1;
      g.fillStyle = ch.color; g.beginPath(); g.arc(18, y, 4.5, 0, Math.PI * 2); g.fill();
      g.fillStyle = off ? muted : text; g.font = `600 11.5px ${FONT}`; g.fillText(ch.label, 30, y);
      const v = s.values[ch.id] ? s.values[ch.id][fr] : 0;
      g.fillStyle = muted; g.font = `500 11px ${MONO}`; g.textAlign = 'right';
      g.fillText(`${Math.round(v * 10) / 10}${ch.unit}`, GUTTER - 10, y); g.textAlign = 'left';
      g.globalAlpha = 1;
      this._chanRows.push({ ch, y0: y - 10, y1: y + 10 });
    });
    if (!sim) { g.fillStyle = muted; g.font = `500 12.5px ${FONT}`; g.fillText('Add a sim to see its curves.', GUTTER + 16, top + 30); }
    else if (!s.keys.length) { g.fillStyle = 'rgba(255,255,255,0.4)'; g.font = `500 12px ${FONT}`; g.fillText('No keys on this part yet - double-click here to key what you see.', GUTTER + 20, top + 24); }
    this.lastDrawMs = performance.now() - t0;
  }

  // ---------------------------------------------------------------- mouse
  _local(e) { const r = this.canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }

  // the key dot (and channel) under the mouse, else the curve segment, else nothing
  _hit(x, y) {
    const s = this.series;
    if (!s || x < GUTTER || y < RULER) return null;
    const vis = s.chans.filter(ch => !this.hidden.has(ch.id));
    let best = null, bd = 8;
    for (const kk of s.keys) {
      const kx = this.xAt(kk.frame);
      if (Math.abs(kx - x) > 8) continue;
      for (const ch of vis) { const d = Math.hypot(kx - x, this.yAt(kk.v[ch.id]) - y); if (d < bd) { bd = d; best = { point: kk, ch }; } }
    }
    if (best) return best;
    // a curve between two keys: which segment
    const p = this.store.project, f = clamp(Math.round(this.frameAt(x)), 0, p.length - 1);
    let near = null;
    for (const ch of vis) { const d = Math.abs(this.yAt(s.values[ch.id][f]) - y); if (d < 6 && (!near || d < near.d)) near = { ch, d }; }
    if (!near) return null;
    const keys = s.keys.map(k => k.frame).sort((a, b) => a - b);
    if (keys.length < 2 && !p.loop) return null;
    let a = null, b = null;
    for (const k of keys) { if (k <= f) a = k; else if (b === null) b = k; }
    if (a === null) { if (!p.loop) return null; a = keys[keys.length - 1] - p.length; }
    if (b === null) { if (!p.loop) return null; b = keys[0] + p.length; }
    const aa = ((a % p.length) + p.length) % p.length;
    const key = s.keys.find(k => k.frame === aa);
    return key ? { seg: { ch: near.ch, a: Math.max(0, a), b, key: key.key }, frame: f } : null;
  }

  _down(e) {
    const { x, y } = this._local(e);
    if (e.button === 1) { e.preventDefault(); this.drag = { kind: 'pan', y0: y, c0: this.vCenter }; return; }
    if (e.button !== 0) return;
    const sim = this.sim();
    if (!sim) return;
    // the channel list: click a row to hide / show that channel
    if (x < GUTTER) {
      const row = (this._chanRows || []).find(r => y >= r.y0 && y <= r.y1);
      if (row) { const id = row.ch.id; if (this.hidden.has(id)) this.hidden.delete(id); else this.hidden.add(id); localStorageSet('curveChannelsOff', [...this.hidden]); this._syncBar(true); this.draw(true); }
      return;
    }
    if (y < RULER) { this.drag = { kind: 'scrub' }; this.app.setFrame(clamp(this.frameAt(x), 0, this.store.project.length - 1)); return; }
    const ctrl = e.ctrlKey || e.metaKey;
    const hit = this._hit(x, y);
    if (hit && hit.point) {
      const id = KO.kid(sim.id, hit.point.frame);
      if (ctrl) { this.tl.toggle(id); this.draw(true); return; }
      if (e.shiftKey) this.tl.selectColumn(hit.point.frame);
      else if (!this.tl.sel.has(id)) this.tl.selectOnly([id]);
      this.app.setFrame(hit.point.frame);
      this.drag = { kind: 'point', x0: x, y0: y, frame: hit.point.frame, ch: hit.ch, id, sel0: new Set(this.tl.sel), moved: false, mode: null, fine: e.shiftKey };
      return;
    }
    if (hit && hit.seg && !ctrl) { this.drag = { kind: 'seg', seg: hit.seg, x0: x, y0: y }; return; }
    if (ctrl) { this.box = { x0: x, y0: y, x1: x, y1: y, base: e.shiftKey ? new Set(this.tl.sel) : new Set() }; this.drag = { kind: 'box' }; return; }
    this.tl.clearSel();
    this.drag = { kind: 'scrub' };
    this.app.setFrame(clamp(this.frameAt(x), 0, this.store.project.length - 1));
  }

  _move(e) {
    const d = this.drag;
    if (!d) return;
    const { x, y } = this._local(e);
    const p = this.store.project;
    if (d.kind === 'scrub') { this.app.setFrame(clamp(this.frameAt(x), 0, p.length - 1)); return; }
    if (d.kind === 'pan') { this.vCenter = d.c0 + (y - d.y0) / this.vScale; this.draw(true); return; }
    if (d.kind === 'box') { this.box.x1 = x; this.box.y1 = y; this._boxSelect(); this.draw(true); return; }
    if (d.kind === 'seg') return;
    if (d.kind !== 'point') return;
    const dx = x - d.x0, dy = y - d.y0;
    if (!d.mode) {
      if (Math.hypot(dx, dy) < 6) return;
      d.mode = Math.abs(dx) > Math.abs(dy) * 1.2 ? 'time' : 'value';
      if (d.mode === 'time' && !this._timeToastShown) { this._timeToastShown = true; toast('Keys hold the whole body - this moves the whole key.'); }
      if (d.mode === 'value' && d.ch.locked) { toast('A hinge only bends one way - drag its Bend (hinge) line.'); d.mode = 'none'; return; }
    }
    if (d.mode === 'time') {
      const df = Math.round(dx / this.tl.pxPerFrame);
      if (!d.moved && !df) return;
      if (!d.moved) { this.store.checkpoint(d.sel0.size > 1 ? `Move ${d.sel0.size} keys` : 'Move key'); d.snap = this.tl._snapKeys(); d.moved = true; }
      if (df === d.df) return;
      this.tl._restoreKeys(d.snap);
      const rep = KO.moveSel(p, d.sel0, df);
      d.df = rep.df; d.rep = rep;
      this.tl.sel = rep.sel;
      this.app.setFrame(clamp(d.frame + rep.df, 0, p.length - 1));
      this.app.keysChanged();
      return;
    }
    if (d.mode !== 'value') return;
    this._dragValue(d, (d.y0 - y) / this.vScale * (e.shiftKey ? 0.1 : 1));
  }

  // Change one channel on the dragged key - and on every selected key of this sim, by the same amount.
  _dragValue(d, dv) {
    const sim = this.sim(), p = this.store.project, part = this.currentPart();
    if (!sim) return;
    if (!d.moved) {
      this.store.checkpoint(`Change ${d.ch.label.replace(' (hinge)', '')}`);
      d.snapKeys = clone(sim.keys);
      d.moved = true;
    }
    sim.keys = clone(d.snapKeys);
    const s = this.series;
    const frames = new Set([d.frame]);
    for (const id of d.sel0) { const q = KO.parseId(id); if (q.kind === 'key' && q.simId === sim.id) frames.add(q.frame); }
    const face = this._faceBone(part);
    const rest = restOf(part);
    const restQ = rest ? new THREE.Quaternion().fromArray(rest.r) : new THREE.Quaternion();
    // natural limits (when on): the part stops at its range, exactly as when it is turned in the 3D view
    const view = this.app.simViews.get(sim.id), vb = view && view.bone(part);
    const limits = this.app.naturalLimits !== false && !face && vb && typeof PM.clampToLimits === 'function';
    for (const f of frames) {
      const key = sim.keys.find(k => k.frame === f);
      if (!key) continue;
      const kk = s.keys.find(k => k.frame === f);
      const v0 = kk ? kk.v[d.ch.id] : 0;
      let v = v0 + dv;
      if (d.ch.kind === 'face') {
        const lim2 = FACE_SLIDERS[d.ch.slider] || { min: 0, max: 1 };
        if (!key.face) key.face = { ...(evaluateFace(sim.keys, f, p.length, p.loop) || {}) };
        key.face[d.ch.slider] = clamp(v / 100, lim2.min, lim2.max);
        if (f === d.frame) d.shown = key.face[d.ch.slider] * 100;
        continue;
      }
      if (key.faceOnly && !face) continue;
      if (d.ch.kind === 'pos') {
        const addCm = dv / 100;
        if (!key.pose.pos) key.pose.pos = {};
        for (const n of HIPS) {
          const r = restOf(n);
          const cur = key.pose.pos[n] || (r ? r.t.slice() : [0, 0, 0]);
          cur[d.ch.axis] += addCm;
          key.pose.pos[n] = cur;
        }
        if (f === d.frame) d.shown = v;
        continue;
      }
      const src = face ? (key.faceBones || (key.faceBones = { rot: {}, pos: {} })) : key.pose;
      src.rot = src.rot || {};
      const q = new THREE.Quaternion().fromArray(src.rot[part] || (rest ? rest.r : [0, 0, 0, 1]));
      const e = restEuler(q, restQ);
      // the key's value may be shown shifted by whole turns (unwrapped): move by the same amount; natural limits
      // (when on) stop it at the part's range
      const before = e[d.ch.axis];
      e[d.ch.axis] = before + (v - v0);
      let nq = fromRestEuler(restQ, e).normalize();
      if (limits) {
        const saved = vb.quaternion.clone();
        vb.quaternion.copy(nq);
        if (PM.clampToLimits(view, vb)) nq = vb.quaternion.clone();
        vb.quaternion.copy(saved);
      }
      src.rot[part] = nq.toArray();
      if (f === d.frame) { let after = restEuler(nq, restQ)[d.ch.axis]; while (after - before > 180) after -= 360; while (after - before < -180) after += 360; d.shown = v0 + (after - before); }
    }
    this.app.pipeline.overrides.clear();
    this.app._edited();
    this.app.applyPoses(false);
    this.app.timeline.draw();
    this.draw(true);
  }

  _boxSelect() {
    const b = this.box, s = this.series, sim = this.sim();
    if (!s || !sim) return;
    const x0 = Math.min(b.x0, b.x1), x1 = Math.max(b.x0, b.x1), y0 = Math.min(b.y0, b.y1), y1 = Math.max(b.y0, b.y1);
    const sel = new Set(b.base);
    const vis = s.chans.filter(ch => !this.hidden.has(ch.id));
    for (const kk of s.keys) {
      const kx = this.xAt(kk.frame);
      if (kx < x0 || kx > x1) continue;
      if (vis.some(ch => { const ky = this.yAt(kk.v[ch.id]); return ky >= y0 && ky <= y1; })) sel.add(KO.kid(sim.id, kk.frame));
    }
    this.tl.sel = sel;
  }

  _up(e) {
    const d = this.drag;
    this.drag = null;
    if (!d) return;
    if (d.kind === 'box') { this.box = null; this.app.selectionChanged(); this.tl.draw(); this.draw(true); return; }
    if (d.kind === 'seg') {
      const { x, y } = this._local(e);
      if (Math.hypot(x - d.x0, y - d.y0) < 5) openTimingEditor(this.app, this.sim(), d.seg.key, e.clientX + 10, e.clientY - 120);
      return;
    }
    if (d.kind === 'point') {
      if (d.moved) {
        for (const s of this.store.project.sims) s.keys.sort((a, b) => a.frame - b.frame);
        this.app.keysChanged();
        this.app.afterEdit();
        if (d.mode === 'time') this.tl.pop([...this.tl.sel]);
        if (d.rep && d.rep.replaced && d.rep.replaced.length) toast(`${d.rep.replaced.length} key${d.rep.replaced.length > 1 ? 's were' : ' was'} replaced - Ctrl+Z brings ${d.rep.replaced.length > 1 ? 'them' : 'it'} back.`);
      } else if (d.sel0.size > 1 && !e.ctrlKey && !e.shiftKey) this.tl.selectOnly([d.id]);
      this.app.selectionChanged();
    }
    this.draw(true);
  }

  _hoverAt(e) {
    if (this.drag) return;
    const { x, y } = this._local(e);
    const hit = this._hit(x, y);
    const was = this.hover && this.hover.seg ? `${this.hover.seg.ch.id}|${this.hover.seg.a}` : '';
    this.hover = hit;
    const now = hit && hit.seg ? `${hit.seg.ch.id}|${hit.seg.a}` : '';
    this.canvas.style.cursor = hit && hit.point ? (hit.ch.locked ? 'not-allowed' : 'ns-resize') : hit && hit.seg ? 'pointer' : x < GUTTER ? 'pointer' : y < RULER ? 'ew-resize' : 'default';
    this.canvas.title = hit && hit.point ? `${hit.ch.label} at frame ${hit.point.frame}: ${Math.round(hit.point.v[hit.ch.id] * 10) / 10}${hit.ch.unit} · drag up/down to change it (Shift: finer) · sideways to move the key`
      : hit && hit.seg ? 'Click for the timing of this part of the motion'
      : x < GUTTER ? 'Click a channel to hide or show it'
      : y > RULER ? 'Double-click to key here · Ctrl+drag to select keys · wheel zooms (Ctrl+wheel: the values) · middle-drag moves the values' : '';
    if (was !== now) this.draw();
  }

  _wheel(e) {
    e.preventDefault();
    const { x, y } = this._local(e);
    if (e.ctrlKey || e.metaKey) {
      const v = this.valAt(y);
      this.vScale = clamp(this.vScale * (e.deltaY < 0 ? 1.18 : 1 / 1.18), 0.02, 400);
      this.vCenter = v - (this.plotTop + this.plotH / 2 - y) / this.vScale;
    } else this.tl.zoomAt(x, e);
    this.draw(true);
    this.tl.draw();
  }

  _dbl(e) {
    const { x, y } = this._local(e);
    if (x < GUTTER || y < RULER) return;
    const hit = this._hit(x, y);
    if (hit && hit.point) return;
    const sim = this.sim(), p = this.store.project;
    if (!sim) return;
    const f = clamp(this.frameAt(x), 0, p.length - 1);
    this.app.setFrame(f);
    this.app.keyPose(sim.id, { body: true });
    // a curve close by: its value becomes what is under the mouse
    this.invalidate();
    const s = this._build();
    let near = null;
    for (const ch of s.chans.filter(c => !this.hidden.has(c.id) && !c.locked)) { const dd = Math.abs(this.yAt(s.values[ch.id][f]) - y); if (dd < 8 && (!near || dd < near.d)) near = { ch, d: dd }; }
    if (near) {
      const kk = s.keys.find(k => k.frame === f);
      if (kk) {
        const d = { frame: f, ch: near.ch, sel0: new Set(), moved: true, snapKeys: clone(sim.keys) };
        this._dragValue(d, this.valAt(y) - kk.v[near.ch.id]);
        this.app.afterEdit();
      }
    }
  }

  _context(e) {
    e.preventDefault();
    const { x, y } = this._local(e);
    const hit = this._hit(x, y), sim = this.sim();
    if (!hit || !hit.point || !sim) return;
    const id = KO.kid(sim.id, hit.point.frame);
    if (this.tl.sel.has(id) && this.tl.sel.size > 1) this.app.selectionMenu(e.clientX, e.clientY);
    else this.app.keyMenu(e.clientX, e.clientY, sim, hit.point.key);
  }
}

// ---------------------------------------------------------------- the timing editor (spec 6.7)
// A popover with the progress curve of the segment from `key` to the next key (time across, how far along up), the two
// handles of a custom curve, and one dot per preset. Dragging a handle makes the timing custom (starting from the
// preset it had). Esc or a click outside closes it.
let _open = null;
export function openTimingEditor(app, sim, key, x, y) {
  if (_open) _open.close();
  if (!sim || !key) return;
  const W = 200, H = 200, Y0 = -0.6, Y1 = 1.6;
  const canvas = h('canvas', { width: W * 2, height: H * 2 });
  const name = h('div', { class: 'name' });
  const dots = h('div', { class: 'dots' });
  const count = app.timeline.selKeysOf(sim.id).filter(k => !k.faceOnly).length + [...app.timeline.sel].filter(id => KO.parseId(id).kind === 'key' && KO.parseId(id).simId !== sim.id).length;
  const allBtn = count > 1 ? h('button', { class: 'btn small soft' }, `Use on all ${count} selected keys`) : null;
  const pop = h('div', { class: 'timing-pop', role: 'dialog' }, h('h4', {}, `Timing from frame ${key.frame}`), canvas, name, dots, allBtn);
  document.body.append(pop);
  pop.style.left = clamp(x, 8, innerWidth - 236) + 'px';
  pop.style.top = clamp(y, 8, innerHeight - 330) + 'px';
  const g = canvas.getContext('2d');
  const px = t => 10 + t * (W - 20), py = v => H - 10 - (v - Y0) / (Y1 - Y0) * (H - 20);
  const ux = X => (X - 10) / (W - 20), uy = Y => Y0 + (H - 10 - Y) / (H - 20) * (Y1 - Y0);
  const findKey = () => { const s = app.store.sim(sim.id); return s && s.keys.find(k => k.frame === key.frame); };
  const fnOf = k => (k.ease === 'auto' ? EASES.smooth : easeFn(k));
  const draw = () => {
    const k = findKey();
    if (!k) return;
    g.setTransform(2, 0, 0, 2, 0, 0);
    g.clearRect(0, 0, W, H);
    g.strokeStyle = 'rgba(255,255,255,.07)';
    for (let i = 0; i <= 4; i++) { g.beginPath(); g.moveTo(px(i / 4), py(Y0)); g.lineTo(px(i / 4), py(Y1)); g.stroke(); }
    for (const v of [0, 0.5, 1]) { g.strokeStyle = v === 0 || v === 1 ? 'rgba(255,255,255,.2)' : 'rgba(255,255,255,.07)'; g.beginPath(); g.moveTo(px(0), py(v)); g.lineTo(px(1), py(v)); g.stroke(); }
    g.fillStyle = 'rgba(255,255,255,.35)'; g.font = `500 9px ${FONT}`;
    g.fillText('this key', px(0) + 2, py(0) + 11); g.fillText('next key', px(1) - 38, py(1) - 5);
    const f = fnOf(k), color = (EASE_INFO[k.ease || 'auto'] || EASE_INFO.auto)[2];
    g.beginPath();
    for (let i = 0; i <= 100; i++) { const t = i / 100, v = k.ease === 'hold' ? (t < 1 ? 0 : 1) : f(t); if (!i) g.moveTo(px(t), py(v)); else g.lineTo(px(t), py(v)); }
    g.strokeStyle = k.ease === 'custom' ? '#ff8cc4' : color; g.lineWidth = 2.4; g.shadowColor = g.strokeStyle; g.shadowBlur = 6; g.stroke(); g.shadowBlur = 0; g.lineWidth = 1;
    const c = k.ease === 'custom' && validCurve(k.curve) ? k.curve : EASE_CURVE[k.ease || 'auto'] || EASE_CURVE.smooth;
    // the two handles (dim until the timing is custom)
    g.globalAlpha = k.ease === 'custom' ? 1 : 0.45;
    g.strokeStyle = 'rgba(255,255,255,.5)';
    g.beginPath(); g.moveTo(px(0), py(0)); g.lineTo(px(c[0]), py(c[1])); g.moveTo(px(1), py(1)); g.lineTo(px(c[2]), py(c[3])); g.stroke();
    for (const [hx, hy] of [[c[0], c[1]], [c[2], c[3]]]) { g.beginPath(); g.arc(px(hx), py(hy), 5.5, 0, Math.PI * 2); g.fillStyle = '#ff4f9a'; g.fill(); g.strokeStyle = '#fff'; g.lineWidth = 1.5; g.stroke(); g.lineWidth = 1; }
    g.globalAlpha = 1;
    const info = k.ease === 'custom' ? ['Custom curve', 'Your own timing - drag the two handles'] : (EASE_INFO[k.ease || 'auto'] || EASE_INFO.auto);
    name.textContent = `${info[0]} · ${info[1]}`;
    dots.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.ease === (k.ease || 'auto')));
  };
  for (const [e, [t, , c]] of Object.entries(EASE_INFO)) {
    const b = h('button', { title: t, 'data-ease': e, style: { '--c': c } }, h('i'));
    b.onclick = () => { if (e === 'custom') { const k = findKey(); if (k && k.ease !== 'custom') app.setEase(sim.id, key.frame, 'custom'); } else app.setEase(sim.id, key.frame, e); draw(); };
    dots.append(b);
  }
  let drag = null;
  canvas.addEventListener('pointerdown', ev => {
    const r = canvas.getBoundingClientRect(), X = (ev.clientX - r.left) * W / r.width, Y = (ev.clientY - r.top) * H / r.height;
    const k = findKey();
    if (!k) return;
    const c = k.ease === 'custom' && validCurve(k.curve) ? k.curve : EASE_CURVE[k.ease || 'auto'] || EASE_CURVE.smooth;
    const d1 = Math.hypot(X - px(c[0]), Y - py(c[1])), d2 = Math.hypot(X - px(c[2]), Y - py(c[3]));
    if (Math.min(d1, d2) > 14) return;
    app.store.checkpoint('Change timing');
    const kk = findKey();
    if (kk.ease !== 'custom') { kk.curve = c.slice(); kk.ease = 'custom'; }
    drag = { h: d1 <= d2 ? 0 : 1 };
    canvas.setPointerCapture(ev.pointerId);
  });
  canvas.addEventListener('pointermove', ev => {
    if (!drag) return;
    const r = canvas.getBoundingClientRect(), X = (ev.clientX - r.left) * W / r.width, Y = (ev.clientY - r.top) * H / r.height;
    const k = findKey();
    if (!k) return;
    const c = validCurve(k.curve) ? k.curve.slice() : EASE_CURVE.smooth.slice();
    c[drag.h * 2] = Math.round(clamp(ux(X), 0, 1) * 100) / 100;
    c[drag.h * 2 + 1] = Math.round(clamp(uy(Y), Y0, Y1) * 100) / 100;
    k.curve = c;
    app.keysChanged();
    draw();
  });
  canvas.addEventListener('pointerup', () => { if (drag) { drag = null; app.afterEdit(); } });
  if (allBtn) allBtn.onclick = () => { const k = findKey(); if (!k) return; app.setEaseForSelection(k.ease || 'auto', k.curve); close(); };
  const onKey = ev => { if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); close(); } };
  const outside = ev => { if (!pop.contains(ev.target)) close(); };
  const close = () => { pop.remove(); window.removeEventListener('keydown', onKey, true); document.removeEventListener('pointerdown', outside, true); if (_open && _open.pop === pop) _open = null; };
  setTimeout(() => { window.addEventListener('keydown', onKey, true); document.addEventListener('pointerdown', outside, true); }, 0);
  _open = { pop, close };
  draw();
  return _open;
}
