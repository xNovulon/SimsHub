// The timeline: seconds ruler, one lane per sim with its keys (coloured by easing), its face keys (pink), its motions
// (a bar with a tick at every stroke) and its sounds (notes; voices show how long they last). Drag to scrub,
// double-click to key, right-click for options.
// Selecting keys (spec_editing 5): click a key, Ctrl+click adds, Shift+click takes every sim's key on that frame,
// Ctrl+drag on the lanes draws a box. Dragging selected keys moves them (Alt+drag stretches them from the playhead,
// the bracket's ends stretch from the other end). The ruler shows a diamond on every frame with keys, the play range
// (Ctrl+drag in the ruler) and the loop badge.
// Lanes shrink a little when there are many sims; when even that doesn't fit, the wheel over the sim names
// scrolls the lanes up and down (the ruler stays put).
// Other features add rows between the ruler and the lanes (addRow), marks in a sim's lane (marks) and read the lane
// geometry from laneTop() - never hard-coded.
import { EASE_INFO, roomEnd } from './animation.js';
import { MOTIONS } from './motion.js';
import { voiceLength } from './face.js';
import * as KO from './keyops.js';
import { toast } from './ui.js';

const GUTTER = 168, RULER = 28, LANE = 48, MIN_LANE = 34;
const SOUND_COL = { wet: '#60a5fa', clap: '#fbbf24', voice: '#ff7ab6', other: '#c9a7ff' };
const FACE_PINK = '#ff7ab6';
const RANGE = '#ffb547';
const springAt = t => (t >= 1 ? 1 : 1 - Math.exp(-6 * t) * Math.cos(9 * t));
const reducedMotion = () => (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  || document.documentElement.classList.contains('reduce-motion');
const isFaceKey = k => !!k.faceOnly;
const hasFace = k => !!((k.face && Object.keys(k.face).length) || k.faceBones);
const clone = x => (typeof structuredClone === 'function' ? structuredClone(x) : JSON.parse(JSON.stringify(x)));
const FONT = 'Plus Jakarta Sans, Segoe UI, sans-serif';
const MONO = 'JetBrains Mono, monospace';

// The seconds ruler with the playhead, the loop label and its badge, the play range and the key summary. Shared by
// the Keys and the Curves view (curves.js), so both show the identical ruler. -> hit geometry {loopBadge, rangeX}
export function drawRuler(g, o) {
  const { x0 = GUTTER, w, h, xAt, pxPerFrame, scroll = 0, length, frame, playing, range = null, loopBadge = null, summary = null, css } = o;
  const col = n => css.getPropertyValue(n).trim();
  const line = col('--line'), muted = col('--muted'), faint = col('--faint');
  const endX = xAt(length);
  const geo = { loopBadge: null, rangeX: null, range: null };
  g.fillStyle = col('--panel-2'); g.fillRect(x0, 0, w - x0, RULER);
  // the play range: a band in the ruler with two ends (and a small x to clear it)
  if (range) {
    const ra = Math.max(x0, xAt(range[0])), rb = Math.min(w, xAt(range[1]));
    if (rb >= x0 && ra <= w) {
      g.fillStyle = 'rgba(255,181,71,.18)'; g.fillRect(ra, 0, Math.max(2, rb - ra), RULER);
      g.fillStyle = RANGE;
      if (xAt(range[0]) >= x0) g.fillRect(xAt(range[0]) - 1, 0, 2, RULER);
      if (xAt(range[1]) <= w) g.fillRect(xAt(range[1]) - 1, 0, 2, RULER);
    }
    const cx = xAt(range[1]) + 10;
    if (cx > x0 && cx < w - 4) {
      g.fillStyle = RANGE; g.beginPath(); g.arc(cx, RULER - 8, 6, 0, Math.PI * 2); g.fill();
      g.strokeStyle = '#1b1510'; g.lineWidth = 1.6; g.beginPath(); g.moveTo(cx - 2.5, RULER - 10.5); g.lineTo(cx + 2.5, RULER - 5.5); g.moveTo(cx + 2.5, RULER - 10.5); g.lineTo(cx - 2.5, RULER - 5.5); g.stroke(); g.lineWidth = 1;
      geo.rangeX = { x: cx, y: RULER - 8, r: 7 };
    }
    geo.range = { a: xAt(range[0]), b: xAt(range[1]) };
  }
  g.strokeStyle = line; g.beginPath(); g.moveTo(0, RULER + 0.5); g.lineTo(w, RULER + 0.5); g.stroke();
  // the loop marker and the playhead's number go first; tick numbers under them are left out
  const px = xAt(frame);
  const showHead = px >= x0 && px <= w;
  const busy = [];
  let loopAt = null;
  if (endX > x0 && endX < w) {
    g.font = `700 10px ${FONT}`;
    const lw = g.measureText('loop ↺').width + (loopBadge ? 16 : 0);
    const right = endX + 5 + lw > w - 4;                  // no room after the end: put it just before
    loopAt = { x: right ? endX - 6 - lw : endX + 5, w: lw };
    busy.push([loopAt.x - 4, loopAt.x + lw + 4], [endX - 1, endX + 1]);
  }
  if (showHead) busy.push([px - 19, px + 19]);
  const steps = [1, 2, 5, 10, 15, 30, 60, 150, 300];
  const step = steps.find(s => s * pxPerFrame >= 46) || 600;
  const first = Math.max(0, Math.floor(scroll / step) * step);
  g.font = `500 10.5px ${MONO}`; g.textBaseline = 'middle';
  for (let f = first; xAt(f) < w; f += step) {
    const x = Math.round(xAt(f)) + 0.5;
    if (x < x0) continue;
    const sec = f % 30 === 0;
    g.strokeStyle = sec ? 'rgba(255,255,255,0.09)' : 'rgba(255,255,255,0.04)';
    g.beginPath(); g.moveTo(x, RULER - (sec ? 10 : 6)); g.lineTo(x, h); g.stroke();
    const label = sec ? `${f / 30}s` : String(f);
    const lx0 = x + 4, lx1 = lx0 + g.measureText(label).width;
    if (busy.some(([a, b]) => lx1 > a && lx0 < b)) continue;
    g.fillStyle = sec ? muted : faint;
    g.fillText(label, lx0, RULER / 2 - 2);
  }
  // every frame with keys: a small diamond under the numbers (white when all its keys are selected)
  if (summary) {
    for (const [f, all] of summary) {
      const x = xAt(f);
      if (x < x0 - 4 || x > w + 4) continue;
      g.save(); g.translate(x, RULER - 5); g.rotate(Math.PI / 4);
      g.fillStyle = all ? '#ffffff' : 'rgba(163,155,178,0.75)'; g.fillRect(-2.6, -2.6, 5.2, 5.2); g.restore();
    }
  }
  // (hidden while the playhead's number sits on it, near the end of the loop)
  if (loopAt && !(showHead && loopAt.x < px + 17 && loopAt.x + loopAt.w > px - 17)) {
    g.fillStyle = '#ff4f9a'; g.font = `700 10px ${FONT}`; g.textAlign = 'left'; g.textBaseline = 'middle';
    g.fillText('loop ↺', loopAt.x, RULER / 2 - 2);
    if (loopBadge) {
      const bx = loopAt.x + loopAt.w - 7, by = RULER / 2 - 2;
      g.fillStyle = loopBadge === 'ok' ? '#3ddc97' : '#ffb547';
      g.beginPath(); g.arc(bx, by, 6, 0, Math.PI * 2); g.fill();
      g.strokeStyle = '#10251c'; g.fillStyle = '#2a1a05'; g.lineWidth = 1.7;
      if (loopBadge === 'ok') { g.beginPath(); g.moveTo(bx - 2.8, by); g.lineTo(bx - 0.6, by + 2.2); g.lineTo(bx + 3, by - 2.2); g.stroke(); }
      else { g.font = `800 9px ${FONT}`; g.textAlign = 'center'; g.fillText('!', bx, by + 0.5); g.textAlign = 'left'; }
      g.lineWidth = 1;
      geo.loopBadge = { x: bx, y: by, r: 8 };
    }
  }
  // playhead (its number matches the frame counter: whole frames passed while playing)
  if (showHead) {
    // playing: a soft pink trail behind the playhead line
    if (playing) {
      const tg = g.createLinearGradient(px - 36, 0, px, 0); tg.addColorStop(0, 'rgba(255,79,154,0)'); tg.addColorStop(1, 'rgba(255,79,154,0.16)');
      g.fillStyle = tg; g.fillRect(Math.max(x0, px - 36), RULER, Math.min(36, px - x0), h - RULER);
    }
    const grad = g.createLinearGradient(0, 0, 0, h); grad.addColorStop(0, '#ff4f9a'); grad.addColorStop(1, 'rgba(168,85,247,0.6)');
    g.strokeStyle = grad; g.lineWidth = 2;
    g.beginPath(); g.moveTo(px, 0); g.lineTo(px, h); g.stroke(); g.lineWidth = 1;
    g.fillStyle = '#ff4f9a'; g.beginPath(); g.roundRect(px - 15, 3, 30, 17, 6); g.fill();
    g.fillStyle = '#fff'; g.font = `700 10px ${MONO}`; g.textAlign = 'center'; g.textBaseline = 'middle';
    const shown = playing ? Math.floor(frame) : Math.round(frame);
    g.fillText(String(shown), px, 12); g.textAlign = 'left';
  }
  return geo;
}

export class Timeline {
  constructor(canvas, app) {
    this.canvas = canvas;
    this.app = app;
    this.ctx = canvas.getContext('2d');
    this.scroll = 0;
    this.vscroll = 0;
    this.lane = LANE;
    this.pxPerFrame = 9;
    this.drag = null;
    this.hover = null;
    this.rows = [];          // extra rows between the ruler and the lanes (addRow)
    this.marks = [];         // [{frame, to, simId, color, title}] ticks in a sim's lane; a click jumps there
    this.fx = [];            // key pops alive now
    this.sel = new Set();    // selected keys, sounds and moments (keyops ids: 'k|sim|frame', 's|sim|frame|name', 'e|id')
    this.box = null;         // box selection being drawn: {x0, y0, x1, y1, base}
    this.pops = new Map();   // id -> start time: keys that pop after a paste, stretch or reverse
    this._geo = {};
    new ResizeObserver(() => this.draw()).observe(canvas);
    canvas.addEventListener('pointerdown', e => this._down(e));
    window.addEventListener('pointermove', e => this._move(e));
    window.addEventListener('pointerup', e => this._up(e));
    canvas.addEventListener('pointermove', e => this._hoverAt(e));
    canvas.addEventListener('pointerleave', () => { this.hover = null; });
    canvas.addEventListener('wheel', e => this._wheel(e), { passive: false });
    canvas.addEventListener('contextmenu', e => this._context(e));
    canvas.addEventListener('dblclick', e => this._dbl(e));
  }

  get store() { return this.app.store; }
  frameAt(x) { return Math.round(this.scroll + (x - GUTTER) / this.pxPerFrame); }
  xAt(frame) { return GUTTER + (frame - this.scroll) * this.pxPerFrame; }

  // ---------------------------------------------------------------- rows between the ruler and the lanes
  // row = {id, height, label, order, draw(g, ctx), hit(x, y, ctx) -> item|null, tooltip(item), onDown(item, e, ctx),
  //        onMove(item, frame, e, ctx), onUp(item, e, ctx), onContext(item|null, frame, e), onDblClick(item|null, frame, e)}
  // ctx = {x0, x1, y, h, xAt(frame), frameAt(x), app, playing}. Returns a function that takes the row away again.
  addRow(row) {
    if (!row || !row.id) throw new Error('timeline.addRow needs an id');
    this.rows = this.rows.filter(r => r.id !== row.id);
    this.rows.push(row);
    this.rows.sort((a, b) => (a.order || 0) - (b.order || 0));
    this.app._fitTimeline?.();
    this.draw();
    return () => { this.rows = this.rows.filter(r => r !== row); this.app._fitTimeline?.(); this.draw(); };
  }
  rowsHeight() { return this.rows.reduce((s, r) => s + (r.height || 0), 0); }
  _rowTop(row) { let y = RULER; for (const r of this.rows) { if (r === row) return y; y += r.height || 0; } return y; }
  _rowCtx(row) {
    return { x0: GUTTER, x1: this.canvas.clientWidth, y: this._rowTop(row), h: row.height || 0, xAt: f => this.xAt(f), frameAt: x => this.frameAt(x),
      app: this.app, playing: !!this.app.playing };
  }
  _rowAt(y) {
    let top = RULER;
    for (const r of this.rows) { const hh = r.height || 0; if (y >= top && y < top + hh) return r; top += hh; }
    return null;
  }

  // Lane height and how far the lanes can scroll, for the canvas' current size.
  _layout() {
    const n = this.store.project.sims.length, avail = Math.max(1, this.canvas.clientHeight - RULER - this.rowsHeight());
    this.lane = n ? Math.max(MIN_LANE, Math.min(LANE, Math.floor(avail / n))) : LANE;
    this.maxV = Math.max(0, n * this.lane - avail);
    this.vscroll = Math.max(0, Math.min(this.maxV, this.vscroll));
  }
  /** Top of lane r in canvas pixels (tests and other features read lane geometry from here). */
  laneTop(r) { this._layout(); return this.top(r); }
  top(r) { return RULER + this.rowsHeight() + r * this.lane - this.vscroll; }
  // positions inside a lane (designed for 48 px, scaled down with the lane)
  _y(r, at) { return this.top(r) + at * this.lane / LANE; }
  get lanesTop() { return RULER + this.rowsHeight(); }

  fit() {
    const w = this.canvas.clientWidth - GUTTER - 24;
    const p = this.store.project;
    this.pxPerFrame = Math.max(1.5, Math.min(26, w / Math.max(10, roomEnd(p))));
    this.scroll = 0;
    this._fitLength = p.length;                   // the loop's length, not the room's - see main.js's re-fit check
    this.draw();
    this.app.curves?.shown && this.app.curves.draw();
  }

  // ---------------------------------------------------------------- the selection
  isSel(id) { return this.sel.has(id); }
  _changed() { this.draw(); this.app.selectionChanged?.(); }
  selectOnly(ids) { this.sel = new Set(ids); this._changed(); }
  toggle(id) { if (this.sel.has(id)) this.sel.delete(id); else this.sel.add(id); this._changed(); }
  selectColumn(frame, add = false) { const ids = KO.columnIds(this.store.project, frame); if (!add) this.sel.clear(); for (const i of ids) this.sel.add(i); this._changed(); }
  selectAll(simIds = null) { this.sel = new Set(KO.allKeyIds(this.store.project, simIds)); this._changed(); }
  clearSel() { if (!this.sel.size) return; this.sel.clear(); this._changed(); }
  // ids of keys, sounds and moments that no longer exist are dropped (after undo, a new animation...)
  pruneSel() {
    if (!this.sel.size) return;
    const r = KO.readSel(this.store.project, this.sel), keep = new Set();
    for (const { sim, key } of r.keys) keep.add(KO.kid(sim.id, key.frame));
    for (const { sim, snd } of r.sounds) keep.add(KO.sndId(sim.id, snd));
    for (const ev of r.events) keep.add(KO.evId(ev));
    if (keep.size !== this.sel.size) { this.sel = keep; this.app.selectionChanged?.(); }
  }
  selKeysOf(simId) { const s = this.store.sim(simId); return s ? s.keys.filter(k => this.sel.has(KO.kid(simId, k.frame))) : []; }
  // min / max frame of the selection and the topmost lane it has keys in
  selRange() {
    const r = KO.readSel(this.store.project, this.sel);
    if (!r.keys.length && !r.sounds.length && !r.events.length) return null;
    const rows = r.keys.map(x => this.store.project.sims.indexOf(x.sim)).concat(r.sounds.map(x => this.store.project.sims.indexOf(x.sim)));
    return { min: r.min, max: r.max, topRow: rows.length ? Math.min(...rows) : 0, count: r.keys.length, sims: r.sims.size, sounds: r.sounds.length };
  }

  // ---------------------------------------------------------------- key pop (design 4.3.6)
  // A new key springs in with a ring in the sim's colour; a deleted one shrinks away. Frames are drawn only while an
  // effect is alive; with reduced motion nothing animates.
  flash(simId, frame, kind = 'add') {
    if (reducedMotion()) { this.draw(); return; }
    this.fx = (this.fx || []).filter(f => !(f.simId === simId && f.frame === frame));
    this.fx.push({ simId, frame, kind, t0: performance.now() });
    this._animate();
  }
  // Many keys pop at once (after a paste, a stretch, a reverse).
  pop(ids) {
    if (reducedMotion()) { this.draw(); return; }
    const t0 = performance.now();
    for (const id of ids || []) this.pops.set(id, t0);
    this._animate();
  }
  // One animation-frame loop while anything moves (key pops, the marching box), then it stops.
  _animate() {
    if (this._fxRaf) return;
    const loop = () => {
      const now = performance.now();
      this.fx = (this.fx || []).filter(f => now - f.t0 < 380);
      for (const [id, t0] of this.pops) if (now - t0 > 300) this.pops.delete(id);
      this.draw();
      const alive = this.fx.length || this.pops.size || (this.box && !reducedMotion());
      this._fxRaf = alive ? requestAnimationFrame(loop) : 0;
      if (!alive) this.draw();
    };
    this._fxRaf = requestAnimationFrame(loop);
  }

  _local(e) { const r = this.canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }

  // The selection's bracket (a bar over the selected keys with two ends to stretch): its geometry, or null.
  _bracket() {
    if (this.sel.size < 2) return null;
    const r = this.selRange();
    if (!r || r.max <= r.min) return null;
    const y = Math.max(this.lanesTop + 1, this.top(r.topRow) + 3);
    return { x0: this.xAt(r.min), x1: this.xAt(r.max), y, min: r.min, max: r.max };
  }

  _hit(x, y) {
    this._layout();
    const sims = this.store.project.sims;
    const p = this.store.project;
    // the ruler: the play range's x, the loop badge, the range ends, a key summary diamond
    if (y < RULER && x > GUTTER) {
      const g = this._geo || {};
      if (g.rangeX && Math.hypot(x - g.rangeX.x, y - g.rangeX.y) <= g.rangeX.r) return { row: -1, rangeClear: true };
      if (g.loopBadge && Math.hypot(x - g.loopBadge.x, y - g.loopBadge.y) <= g.loopBadge.r) return { row: -1, loopBadge: true };
      const range = this.app.playRange;
      if (range) {
        if (Math.abs(x - this.xAt(range[0])) <= 5) return { row: -1, rangeEnd: 'a' };
        if (Math.abs(x - this.xAt(range[1])) <= 5) return { row: -1, rangeEnd: 'b' };
      }
      if (y >= RULER - 9) {
        const f = this.frameAt(x);
        let best = null;
        for (const s of sims) for (const k of s.keys) if (Math.abs(this.xAt(k.frame) - x) <= 5 && (best === null || Math.abs(this.xAt(k.frame) - x) < Math.abs(this.xAt(best) - x))) best = k.frame;
        if (best !== null && best < p.length + 1) return { row: -1, summary: best };
        void f;
      }
      return { row: -1, ruler: true };
    }
    if (y >= RULER && y < this.lanesTop) {
      const row = this._rowAt(y);
      if (row) {
        let item = null;
        try { item = row.hit ? row.hit(x, y, this._rowCtx(row)) : null; } catch (err) { console.error(err); }
        return { extra: row, item, row: -1 };
      }
    }
    // the selection's bracket ends
    const br = this._bracket();
    if (br && x > GUTTER && Math.abs(y - (br.y + 2)) <= 7) {
      if (Math.abs(x - br.x0) <= 6) return { row: -1, bracket: 'left', br };
      if (Math.abs(x - br.x1) <= 6) return { row: -1, bracket: 'right', br };
    }
    const row = Math.floor((y - this.lanesTop + this.vscroll) / this.lane);
    if (y < this.lanesTop || row < 0 || row >= sims.length) return { row: -1 };
    const sim = sims[row];
    // face-only keys first (a small pink diamond on the face row), then full keys
    for (const k of sim.keys) if (isFaceKey(k) && Math.abs(this.xAt(k.frame) - x) < 6 && Math.abs(this._y(row, 4) + 1 - y) < 6) return { row, sim, key: k };
    for (const k of sim.keys) if (!isFaceKey(k) && Math.abs(this.xAt(k.frame) - x) < 8 && Math.abs(this._y(row, 15) - y) < 9) return { row, sim, key: k };
    for (const s of sim.sounds || []) if (Math.abs(this.xAt(s.frame) - x) < 6 && y > this._y(row, 32) && y < this._y(row, 47)) return { row, sim, sound: s };
    for (const m of this.marks || []) {
      if (m.simId !== sim.id) continue;
      const x0 = this.xAt(m.frame), x1 = this.xAt(m.to ?? m.frame);
      if (x >= Math.min(x0, x1) - 4 && x <= Math.max(x0, x1) + 4 && Math.abs(y - this._y(row, 45)) < 5) return { row, sim, mark: m };
    }
    return { row, sim };
  }

  // Interactive frame picks (scrub, click, drag) may land in the room past the loop's end, but never past it.
  _clampFrame(f) { return Math.max(0, Math.min(roomEnd(this.store.project) - 1, f)); }

  _down(e) {
    if (e.button !== 0) return;
    const { x, y } = this._local(e);
    const ctrl = e.ctrlKey || e.metaKey;
    if (x < GUTTER) { const h = this._hit(GUTTER + 1, y); if (h.sim) this.app.selectSim(h.sim.id); return; }
    const h = this._hit(x, y);
    if (h.rangeClear) { this.app.setPlayRange(null); return; }
    if (h.loopBadge) { const r = this.canvas.getBoundingClientRect(); this.app.loopMenu?.(r.left + x, r.top + y + 12); return; }
    if (h.rangeEnd) { this.drag = { kind: 'rangeEnd', end: h.rangeEnd }; return; }
    if (h.summary !== undefined) {
      this.selectColumn(h.summary, e.shiftKey);
      this.app.setFrame(this._clampFrame(h.summary));
      this._startKeys(x, h.summary, e, null);
      return;
    }
    if (h.ruler) {
      if (ctrl) { const f = this._clampFrame(this.frameAt(x)); this.drag = { kind: 'range', from: f }; this.app.setPlayRange([f, f], { quiet: true }); return; }
      this.drag = { kind: 'scrub' };
      this.app.setFrame(this._clampFrame(this.frameAt(x)));
      return;
    }
    if (h.extra) {
      if (h.item && h.extra.onDown) {
        try { h.extra.onDown(h.item, e, this._rowCtx(h.extra)); } catch (err) { console.error(err); }
        this.drag = { kind: 'row', row: h.extra, item: h.item };
        return;
      }
      this.drag = { kind: 'scrub' };
      this.app.setFrame(this._clampFrame(this.frameAt(x)));
      return;
    }
    if (h.bracket) {
      const pivot = h.bracket === 'left' ? h.br.max : h.br.min, grab = h.bracket === 'left' ? h.br.min : h.br.max;
      this.drag = { kind: 'keys', mode: 'stretch', sel0: new Set(this.sel), startX: x, pivot, grab, moved: false };
      return;
    }
    if (h.mark) { this.app.selectSim(h.sim.id); this.app.setFrame(this._clampFrame(h.mark.frame)); return; }
    if (h.key) {
      const id = KO.kid(h.sim.id, h.key.frame);
      if (ctrl) { this.toggle(id); return; }
      const was = this.sel.has(id);
      if (e.shiftKey) this.selectColumn(h.key.frame);
      else if (!was) this.selectOnly([id]);
      // Alt stretches from the playhead: it stays where it is (a plain press jumps to the key)
      const stretch = e.altKey && this.sel.size > 1;
      if (stretch) this._startKeys(x, h.key.frame, e, { simId: h.sim.id, frame: h.key.frame, was: false, id });
      this.app.selectSim(h.sim.id);
      if (!stretch) {
        this.app.setFrame(h.key.frame);
        this._startKeys(x, h.key.frame, e, { simId: h.sim.id, frame: h.key.frame, was: was && !e.shiftKey && this.sel.size > 1, id });
      }
      return;
    }
    if (h.sound) {
      const id = KO.sndId(h.sim.id, h.sound);
      if (ctrl) { this.toggle(id); return; }
      const was = this.sel.has(id);
      if (!was) this.selectOnly([id]);
      this._startKeys(x, h.sound.frame, e, { simId: h.sim.id, frame: h.sound.frame, was: was && this.sel.size > 1, id, sound: true });
      return;
    }
    // an empty lane: Ctrl draws a box (Ctrl+Shift adds to the selection); a plain drag scrubs
    if (ctrl) {
      this.box = { x0: x, y0: y, x1: x, y1: y, base: e.shiftKey ? new Set(this.sel) : new Set() };
      this.drag = { kind: 'box' };
      if (!e.shiftKey) this.sel.clear();
      this._animate();
      return;
    }
    if (!e.shiftKey) this.clearSel();
    if (h.sim && h.sim.id !== this.store.selected.sim) this.app.selectSim(h.sim.id);
    this.drag = { kind: 'scrub' };
    this.app.setFrame(this._clampFrame(this.frameAt(x)));
  }

  // A press on a selected key (or sound): dragging moves the whole selection; Alt stretches it from the playhead.
  _startKeys(x, frame, e, anchor) {
    let mode = 'move', pivot = null;
    if (e.altKey && this.sel.size > 1) {
      mode = 'stretch';
      const r = this.selRange();
      const xp = this.xAt(this.store.frame);
      pivot = Math.abs(x - xp) >= 6 ? Math.round(this.store.frame) : (r ? r.min : frame);
    }
    this.drag = { kind: 'keys', mode, sel0: new Set(this.sel), startX: x, grab: frame, pivot, anchor, moved: false };
  }

  // The drag contract (spec 4.2): the first real move makes one undo step and keeps a copy of what can change; every
  // later move starts again from that copy with the total offset - dragging across another key and back never
  // deletes it.
  _snapKeys() {
    const p = this.store.project;
    return { sims: p.sims.map(s => ({ id: s.id, keys: clone(s.keys), sounds: clone(s.sounds || []) })), events: Array.isArray(p.events) ? clone(p.events) : undefined };
  }
  _restoreKeys(snap) {
    const p = this.store.project;
    for (const x of snap.sims) { const s = p.sims.find(y => y.id === x.id); if (s) { s.keys = clone(x.keys); s.sounds = clone(x.sounds); } }
    if (snap.events !== undefined) p.events = clone(snap.events);
  }

  _move(e) {
    if (!this.drag) return;
    const { x, y } = this._local(e);
    const d = this.drag;
    if (d.kind === 'scrub') { this.app.setFrame(this._clampFrame(this.frameAt(x))); return; }
    if (d.kind === 'row') {
      try { d.row.onMove && d.row.onMove(d.item, this._clampFrame(this.frameAt(x)), e, this._rowCtx(d.row)); } catch (err) { console.error(err); }
      this.draw();
      return;
    }
    if (d.kind === 'range' || d.kind === 'rangeEnd') {
      const f = this._clampFrame(this.frameAt(x));
      const r = this.app.playRange || [f, f];
      const a = d.kind === 'range' ? d.from : d.end === 'a' ? r[1] : r[0];
      this.app.setPlayRange([Math.min(a, f), Math.max(a, f)], { quiet: true });
      return;
    }
    if (d.kind === 'box') {
      this.box.x1 = x; this.box.y1 = y;
      this._boxSelect();
      this.draw();
      return;
    }
    if (d.kind !== 'keys') return;
    if (!d.moved && Math.abs(x - d.startX) < 3) return;
    const p = this.store.project;
    let rep;
    if (d.mode === 'stretch') {
      const xp = this.xAt(d.pivot), x0 = this.xAt(d.grab);
      if (Math.abs(x0 - xp) < 1) return;
      const s = Math.max(0.05, (x - xp) / (x0 - xp));
      if (!d.moved) { this.store.checkpoint('Stretch keys'); d.snap = this._snapKeys(); d.moved = true; }
      this._restoreKeys(d.snap);
      rep = KO.scaleSel(p, d.sel0, d.pivot, s);
      d.s = s;
    } else {
      const df = Math.round((x - d.startX) / this.pxPerFrame);
      if (!d.moved && !df) return;
      if (!d.moved) { this.store.checkpoint(this.sel.size > 1 ? `Move ${this.sel.size} keys` : 'Move key'); d.snap = this._snapKeys(); d.moved = true; }
      if (df === d.df && d.moved && d.rep) return;
      this._restoreKeys(d.snap);
      rep = KO.moveSel(p, d.sel0, df);
      d.df = rep.df;
    }
    d.rep = rep;
    this.sel = rep.sel;
    const to = d.mode === 'stretch' ? Math.round(d.pivot + (d.grab - d.pivot) * d.s) : d.grab + (d.df || 0);
    const f = this._clampFrame(to);
    if (f !== Math.round(this.store.frame)) this.app.setFrame(f); else { this.app.keysChanged(); }
    this.draw();
  }

  // keys and sounds inside the box (added to what was selected before with Ctrl+Shift)
  _boxSelect() {
    const b = this.box, sims = this.store.project.sims;
    const x0 = Math.min(b.x0, b.x1), x1 = Math.max(b.x0, b.x1), y0 = Math.min(b.y0, b.y1), y1 = Math.max(b.y0, b.y1);
    const sel = new Set(b.base);
    sims.forEach((s, r) => {
      for (const k of s.keys) {
        const kx = this.xAt(k.frame), ky = k.faceOnly ? this._y(r, 4) + 1 : this._y(r, 15);
        if (kx >= x0 && kx <= x1 && ky >= y0 && ky <= y1) sel.add(KO.kid(s.id, k.frame));
      }
      for (const snd of s.sounds || []) {
        const sx = this.xAt(snd.frame), sy = this._y(r, 39);
        if (sx >= x0 && sx <= x1 && sy >= y0 && sy <= y1) sel.add(KO.sndId(s.id, snd));
      }
    });
    this.sel = sel;
  }

  _up(e) {
    const d = this.drag;
    this.drag = null;
    if (!d) return;
    if (d.kind === 'row') {
      try { d.row.onUp && d.row.onUp(d.item, e, this._rowCtx(d.row)); } catch (err) { console.error(err); }
    }
    if (d.kind === 'box') { this.box = null; this._changed(); return; }
    if (d.kind === 'range' || d.kind === 'rangeEnd') {
      const r = this.app.playRange;
      if (r && r[1] - r[0] < 1) this.app.setPlayRange(null, { quiet: true });
      else if (r) this.app.setPlayRange(r);
      return;
    }
    if (d.kind === 'keys') {
      if (d.moved) {
        for (const s of this.store.project.sims) s.keys.sort((a, b) => a.frame - b.frame);
        const rep = d.rep || { replaced: [], joined: [] };
        this.app._applyFit();      // dragged/stretched keys: the loop follows their new last frame and gap
        this.app.afterEdit();
        this.pop([...this.sel]);
        if (rep.replaced && rep.replaced.length) toast(`${rep.replaced.length} key${rep.replaced.length > 1 ? 's were' : ' was'} replaced - Ctrl+Z brings ${rep.replaced.length > 1 ? 'them' : 'it'} back.`);
        else if (rep.joined && rep.joined.length) {
          const s = this.store.sim(rep.joined[0].simId);
          this.app.hud(`${s ? s.label : 'The sim'}: the face key joined the key at ${rep.joined[0].frame}`);
        }
        this.app.selectionChanged?.();
      } else if (d.anchor && d.anchor.was) {
        // a click (no drag) on a key of a bigger selection selects just that key
        this.selectOnly([d.anchor.id]);
      }
    }
    this.draw();
  }

  // A key dropped onto another key of the same sim: they become one. The full key keeps its body; the dropped key's
  // face (sliders and face bones) wins. (keyops.moveSel does this now; kept for callers from before.)
  _mergeAt(sim, key) {
    const other = sim.keys.find(k => k !== key && k.frame === key.frame);
    if (!other) return;
    const body = key.faceOnly ? other : key, face = key;
    const merged = { ...body };
    if (face.face) merged.face = { ...face.face }; else if (body === other && other.face) merged.face = other.face;
    if (face.faceBones) merged.faceBones = JSON.parse(JSON.stringify(face.faceBones));
    if (!(key.faceOnly && other.faceOnly)) delete merged.faceOnly;
    sim.keys = sim.keys.filter(k => k !== key && k !== other);
    sim.keys.push(merged);
    this.app.hud(`${sim.label}: the face key joined the key at ${merged.frame}`);
  }

  _hoverAt(e) {
    const { x, y } = this._local(e);
    const h = this._hit(x, y);
    this.hover = h;
    let c = h.key || h.sound || h.mark || h.summary !== undefined ? 'grab' : h.bracket || h.rangeEnd ? 'ew-resize' : h.loopBadge || h.rangeClear ? 'pointer'
      : x > GUTTER && y > RULER ? 'default' : x > GUTTER ? 'ew-resize' : 'pointer';
    const n = this.sel.size;
    const selKey = h.key && this.sel.has(KO.kid(h.sim.id, h.key.frame)) && n > 1;
    let tip = selKey ? `${n} keys selected · drag to move · Alt+drag to stretch from the playhead · right-click for more`
      : h.key ? (h.key.faceOnly ? `Face key at ${h.key.frame} · right-click for options`
        : `${h.key.type === 'breakdown' ? 'In-between key' : 'Key'} at ${h.key.frame} · ${(EASE_INFO[h.key.ease || 'auto'] || EASE_INFO.auto)[0]} into the next (right-click to change) · Ctrl+click to add to the selection`)
      : h.sound ? `${h.sound.name} (${h.sound.kind || 'sound'}) · drag to move, right-click to remove`
      : h.mark ? (h.mark.title || `Frame ${h.mark.frame}`) + ' · click to go there'
      : h.summary !== undefined ? `Every sim's key at frame ${h.summary} · click to select them all`
      : h.bracket ? 'Drag to stretch the selected keys'
      : h.loopBadge ? 'Loop check · click for loop tools'
      : h.rangeClear ? 'Play the whole loop again'
      : h.rangeEnd ? 'Drag to change the part that plays'
      : h.ruler ? 'Click to jump · Ctrl+drag to play only a part'
      : x < GUTTER && this.maxV > 0 ? 'Scroll here to see the other sims'
      : h.sim && x > GUTTER ? 'Drag to scrub · double-click to key · Ctrl+drag to select keys' : '';
    if (h.extra) {
      c = h.item ? 'pointer' : 'default';
      try { tip = h.item && h.extra.tooltip ? h.extra.tooltip(h.item) || '' : (h.extra.label || ''); } catch { tip = ''; }
    }
    this.canvas.style.cursor = c;
    this.canvas.title = tip;
  }

  _wheel(e) {
    e.preventDefault();
    const { x, y } = this._local(e);
    this._layout();
    if (this.maxV > 0 && x < GUTTER && y > this.lanesTop && !e.shiftKey) {
      // over the sim names: scroll the lanes up and down
      this.vscroll = Math.max(0, Math.min(this.maxV, this.vscroll + e.deltaY * 0.5));
    } else this.zoomAt(x, e);
    this.draw();
  }
  // Wheel zoom / Shift+wheel scroll in time, shared with the Curves view (spec 5.7).
  zoomAt(x, e) {
    if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      this.scroll = Math.max(0, this.scroll + (e.deltaX || e.deltaY) / this.pxPerFrame);
    } else {
      const f = this.scroll + (x - GUTTER) / this.pxPerFrame;
      this.pxPerFrame = Math.max(1.2, Math.min(44, this.pxPerFrame * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
      this.scroll = Math.max(0, f - (x - GUTTER) / this.pxPerFrame);
    }
  }

  _dbl(e) {
    const { x, y } = this._local(e);
    const h = this._hit(x, y);
    if (h.extra) {
      try { h.extra.onDblClick && h.extra.onDblClick(h.item, this._clampFrame(this.frameAt(x)), e); } catch (err) { console.error(err); }
      return;
    }
    if (h.sim && !h.key && !h.sound && x > GUTTER) {
      this.app.selectSim(h.sim.id);
      this.app.setFrame(this._clampFrame(this.frameAt(x)));
      this.app.keyPose(h.sim.id);
    }
  }

  _context(e) {
    e.preventDefault();
    const { x, y } = this._local(e);
    const h = this._hit(x, y);
    const frame = this._clampFrame(this.frameAt(x));
    if (h.extra) {
      try { h.extra.onContext && h.extra.onContext(h.item, frame, e); } catch (err) { console.error(err); }
      return;
    }
    if (h.loopBadge) { this.app.loopMenu?.(e.clientX, e.clientY); return; }
    if (y < RULER && x > GUTTER) { this.app.rulerMenu?.(e.clientX, e.clientY, h.summary !== undefined ? h.summary : frame); return; }
    if (h.key) {
      const id = KO.kid(h.sim.id, h.key.frame);
      if (this.sel.has(id) && this.sel.size > 1 && this.app.selectionMenu) this.app.selectionMenu(e.clientX, e.clientY);
      else this.app.keyMenu(e.clientX, e.clientY, h.sim, h.key);
    } else if (h.sound) {
      const id = KO.sndId(h.sim.id, h.sound);
      if (this.sel.has(id) && this.sel.size > 1 && this.app.selectionMenu) this.app.selectionMenu(e.clientX, e.clientY);
      else this.app.soundMenu(e.clientX, e.clientY, h.sim, h.sound);
    } else if (h.sim && x > GUTTER) this.app.laneMenu(e.clientX, e.clientY, h.sim, frame);
  }

  draw() {
    const c = this.canvas, dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth, hgt = c.clientHeight;
    if (!w || !hgt) return;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(hgt * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(hgt * dpr); }
    this._layout();
    const g = this.ctx;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, hgt);
    const p = this.store.project;
    const css = getComputedStyle(document.documentElement);
    const col = n => css.getPropertyValue(n).trim();
    const line = col('--line'), muted = col('--muted'), text = col('--text');
    const endX = this.xAt(p.length);
    const roomX = this.xAt(roomEnd(p));            // the room past the loop's end always shows a little, dimmed
    const LN = this.lane, sy = v => v * LN / LANE;
    const lanesTop = this.lanesTop;
    const now = performance.now();
    const frameNow = Math.round(this.store.frame);
    const sel = this.sel;
    const range = this.app.playRange;

    // lanes (kept below the ruler and the extra rows when they scroll) - nothing is drawn past the room's end
    g.save();
    g.beginPath(); g.rect(0, lanesTop, Math.min(w, roomX), hgt - lanesTop); g.clip();
    p.sims.forEach((s, r) => {
      const y = this.top(r);
      if (y > hgt || y + LN < lanesTop) return;
      const selSim = s.id === this.store.selected.sim;
      g.fillStyle = selSim ? 'rgba(255,79,154,0.05)' : (r % 2 ? 'rgba(255,255,255,0.015)' : 'transparent');
      g.fillRect(0, y, w, LN);
      if (selSim) { g.fillStyle = s.color; g.fillRect(0, y, 3, LN); }
      const badge = Math.min(22, LN - 12);
      g.fillStyle = s.color; g.beginPath(); g.roundRect(14, y + (LN - badge) / 2, badge, badge, 7); g.fill();
      g.fillStyle = '#140e19'; g.font = `800 11px ${FONT}`; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillText(s.frame === 'ym' ? 'M' : s.frame === 'yf_futa' ? 'F+' : 'F', 14 + badge / 2, y + LN / 2 + 0.5);
      g.textAlign = 'left';
      g.fillStyle = selSim ? text : muted; g.font = `${selSim ? 700 : 600} 12.5px ${FONT}`;
      g.fillText(s.label, 46, y + sy(17));
      g.fillStyle = muted; g.font = `500 11px ${FONT}`;
      const layers = (s.layers || []).filter(l => l.on);
      const bodyKeys = s.keys.filter(k => !k.faceOnly).length, faceKeys = s.keys.filter(hasFace).length;
      const info = `${bodyKeys} key${bodyKeys === 1 ? '' : 's'}${faceKeys ? ` · ${faceKeys} face` : ''}`;
      g.fillText(`${info}${layers.length ? ' · ' + layers.map(l => MOTIONS[l.type]?.label).join(', ') : ''}`.slice(0, 26), 46, y + sy(32));
      g.strokeStyle = line; g.beginPath(); g.moveTo(0, y + LN + 0.5); g.lineTo(w, y + LN + 0.5); g.stroke();
    });

    // the room past the loop's end: dimmed, clearly not part of the loop, with the end itself marked
    if (endX < roomX) {
      g.fillStyle = 'rgba(0,0,0,0.3)';
      g.fillRect(Math.max(GUTTER, endX), lanesTop, Math.min(w, roomX) - Math.max(GUTTER, endX), hgt - lanesTop);
    }
    if (endX >= GUTTER && endX <= w) {
      g.strokeStyle = muted; g.lineWidth = 1; g.setLineDash([3, 3]);
      g.beginPath(); g.moveTo(Math.round(endX) + 0.5, lanesTop); g.lineTo(Math.round(endX) + 0.5, hgt); g.stroke();
      g.setLineDash([]);
    }
    // outside the play range: dimmed
    if (range) {
      g.fillStyle = 'rgba(0,0,0,0.18)';
      const ra = this.xAt(range[0]), rb = this.xAt(range[1]);
      if (ra > GUTTER) g.fillRect(GUTTER, lanesTop, Math.min(w, ra) - GUTTER, hgt - lanesTop);
      if (rb < Math.min(w, endX)) g.fillRect(Math.max(GUTTER, rb), lanesTop, Math.min(w, endX) - Math.max(GUTTER, rb), hgt - lanesTop);
    }

    const drag = this.drag && this.drag.kind === 'keys' && this.drag.moved ? this.drag : null;
    // while dragging: where the keys were (faint) and the keys that will be replaced (a red x)
    if (drag && drag.snap) {
      const rows = new Map(p.sims.map((s, r) => [s.id, r]));
      g.save(); g.globalAlpha = 0.25;
      for (const id of drag.sel0) {
        const q = KO.parseId(id);
        if (q.kind !== 'key' || !rows.has(q.simId)) continue;
        const r = rows.get(q.simId), s = p.sims[r], x = this.xAt(q.frame);
        const snapSim = drag.snap.sims.find(z => z.id === q.simId), k0 = snapSim && snapSim.keys.find(k => k.frame === q.frame);
        const cy = k0 && k0.faceOnly ? this._y(r, 4) + 1 : this._y(r, 15);
        g.save(); g.translate(x, cy); g.rotate(Math.PI / 4); g.fillStyle = k0 && k0.faceOnly ? FACE_PINK : s.color; g.fillRect(-5, -5, 10, 10); g.restore();
      }
      g.restore();
      for (const rp of (drag.rep && drag.rep.replaced) || []) {
        if (!rows.has(rp.simId)) continue;
        const r = rows.get(rp.simId), x = this.xAt(rp.frame), cy = this._y(r, 15);
        g.save(); g.strokeStyle = '#fb5471'; g.lineWidth = 2.4; g.lineCap = 'round';
        g.beginPath(); g.moveTo(x - 6, cy - 6 - 10); g.lineTo(x + 6, cy + 6 - 10); g.moveTo(x + 6, cy - 6 - 10); g.lineTo(x - 6, cy + 6 - 10); g.stroke(); g.restore();
      }
    }

    p.sims.forEach((s, r) => {
      const top = this.top(r);
      if (top > hgt || top + LN < lanesTop) return;
      // motion bars with a tick at each stroke
      (s.layers || []).filter(l => l.on).forEach((l, i) => {
        const m = MOTIONS[l.type]; if (!m) return;
        const strokes = Math.max(1, Math.round(l.params?.strokes ?? m.params.strokes ?? 1));
        const y = top + sy(26) + i * 3;
        const x0 = Math.max(GUTTER, this.xAt(0)), x1 = Math.min(w, endX);
        if (x1 <= x0) return;
        const grad = g.createLinearGradient(x0, 0, x1, 0); grad.addColorStop(0, 'rgba(255,79,154,0.55)'); grad.addColorStop(1, 'rgba(168,85,247,0.55)');
        g.fillStyle = grad; g.fillRect(x0, y, x1 - x0, 2);
        g.fillStyle = '#ffd1e6';
        for (let k = 0; k < strokes; k++) {
          const f = (((k - (l.phase || 0)) / strokes) % 1 + 1) % 1 * p.length;
          const x = this.xAt(f);
          if (x >= GUTTER && x <= w) g.fillRect(x - 1, y - 2, 2, 6);
        }
      });
      // path between body keys
      const ky = top + sy(15);
      const body = s.keys.filter(k => !k.faceOnly);
      if (body.length > 1) {
        g.strokeStyle = s.color + '55'; g.lineWidth = 2;
        g.beginPath(); g.moveTo(Math.max(GUTTER, this.xAt(body[0].frame)), ky); g.lineTo(Math.min(w, this.xAt(body[body.length - 1].frame)), ky); g.stroke();
        g.lineWidth = 1;
      }
      const fy = top + sy(4) + 1;
      for (const k of s.keys) {
        const x = this.xAt(k.frame);
        if (x < GUTTER - 10 || x > w + 10) continue;
        const id = KO.kid(s.id, k.frame);
        const isSel = sel.has(id);
        const on = k.frame === frameNow && s.id === this.store.selected.sim;
        const fxe = this.fx && this.fx.find(q => q.simId === s.id && q.frame === k.frame && q.kind !== 'del');
        const age = fxe ? (now - fxe.t0) / 280 : 1;
        let sc = fxe ? springAt(age) : 1;
        const popT = this.pops.get(id);
        if (popT !== undefined) { const u = Math.min(1, (now - popT) / 260); sc *= 1 + 0.35 * Math.sin(Math.PI * u); }
        const dragged = drag && isSel;
        if (dragged) sc *= 1.3;
        const cy = k.faceOnly ? fy : ky;
        if (fxe && age < 1.35) {
          g.save(); g.globalAlpha = Math.max(0, 1 - age / 1.35); g.strokeStyle = k.faceOnly ? FACE_PINK : s.color; g.lineWidth = 2;
          g.beginPath(); g.arc(x, cy, 6 + 14 * Math.min(1, age), 0, Math.PI * 2); g.stroke(); g.restore();
        }
        if (k.faceOnly) {
          // a face key where the body has no key: a small pink diamond on the face row
          g.save(); g.translate(x, fy); g.rotate(Math.PI / 4); g.scale(sc, sc);
          if (dragged || isSel) { g.shadowColor = FACE_PINK; g.shadowBlur = isSel ? 10 : 12; }
          const sz = 3.6;
          g.fillStyle = FACE_PINK; g.fillRect(-sz, -sz, sz * 2, sz * 2);
          if (on) { g.strokeStyle = '#ffffff'; g.lineWidth = 1.6; g.strokeRect(-sz, -sz, sz * 2, sz * 2); }
          if (isSel) { g.strokeStyle = '#ffffff'; g.lineWidth = 1.6; g.strokeRect(-sz - 2, -sz - 2, sz * 2 + 4, sz * 2 + 4); }
          g.restore();
          continue;
        }
        const ec = k.ease === 'custom' ? EASE_INFO.custom[2] : (EASE_INFO[k.ease || 'auto'] || EASE_INFO.auto)[2];
        const tween = k.type === 'breakdown';
        g.save(); g.translate(x, ky); g.rotate(Math.PI / 4); g.scale(sc, sc);
        if (dragged) { g.shadowColor = s.color; g.shadowBlur = 12; }
        let sz = on ? 7 : 5.6;
        if (tween) sz *= 0.7;
        if (tween) { g.globalAlpha = 0.55; g.fillStyle = s.color; g.fillRect(-sz, -sz, sz * 2, sz * 2); g.globalAlpha = 1; }
        else { g.fillStyle = k.ease === 'hold' ? '#1b1722' : s.color; g.fillRect(-sz, -sz, sz * 2, sz * 2); }
        g.shadowBlur = 0;
        g.strokeStyle = on ? '#ffffff' : ec; g.lineWidth = on ? 2.2 : 1.8;
        g.strokeRect(-sz, -sz, sz * 2, sz * 2);
        // selected: a white outline a little outside, glowing in the sim's colour
        if (isSel) {
          g.shadowColor = s.color; g.shadowBlur = 10;
          g.strokeStyle = '#ffffff'; g.lineWidth = 2;
          g.strokeRect(-sz - 2.5, -sz - 2.5, sz * 2 + 5, sz * 2 + 5);
          g.shadowBlur = 0;
        }
        g.restore();
        // the face dot: this key holds a face too
        if (hasFace(k)) { g.fillStyle = FACE_PINK; g.beginPath(); g.arc(x, fy, 2.2, 0, Math.PI * 2); g.fill(); }
      }
      // keys that were just deleted shrink away
      for (const fxe of this.fx || []) {
        if (fxe.kind !== 'del' || fxe.simId !== s.id) continue;
        const age = (now - fxe.t0) / 160;
        if (age >= 1) continue;
        const x = this.xAt(fxe.frame);
        g.save(); g.globalAlpha = 1 - age; g.translate(x, ky); g.rotate(Math.PI / 4); g.scale(1 - age, 1 - age);
        g.fillStyle = s.color; g.fillRect(-5.6, -5.6, 11.2, 11.2); g.restore();
      }
      for (const snd of s.sounds || []) {
        const x = this.xAt(snd.frame);
        if (x < GUTTER - 40 || x > w) continue;
        const colr = SOUND_COL[snd.kind] || SOUND_COL.other;
        g.fillStyle = colr;
        if (snd.kind === 'voice') {
          const len = voiceLength(snd.name, p.fps || 30, this.app.voiceSec && this.app.voiceSec.get ? this.app.voiceSec.get(snd.name) : 0) * this.pxPerFrame;
          g.globalAlpha = 0.35; g.fillRect(Math.max(GUTTER, x), top + sy(36), Math.max(3, Math.min(len, w - x)), 6); g.globalAlpha = 1;
        }
        if (x >= GUTTER) {
          g.beginPath(); g.roundRect(x - 2, top + sy(35), 4, Math.max(7, sy(9)), 2); g.fill();
          if (sel.has(KO.sndId(s.id, snd))) { g.strokeStyle = '#ffffff'; g.lineWidth = 1.6; g.beginPath(); g.roundRect(x - 4, top + sy(33), 8, Math.max(11, sy(13)), 3); g.stroke(); g.lineWidth = 1; }
        }
      }
      // marks other features put in this lane (clipping ticks...)
      for (const m of this.marks || []) {
        if (m.simId !== s.id) continue;
        const x0 = Math.max(GUTTER, this.xAt(m.frame)), x1 = Math.min(w, this.xAt(m.to ?? m.frame));
        if (x1 < GUTTER || x0 > w) continue;
        g.fillStyle = m.color || '#fbbf24';
        g.fillRect(x0 - 1, top + sy(44), Math.max(2, x1 - x0 + 2), 3);
      }
      // an empty lane says what to do (it disappears once there is anything in it)
      if (s.keys.length <= 1 && !(s.layers || []).length && !(s.sounds || []).length && LN >= 40) {
        g.fillStyle = 'rgba(255,255,255,0.28)'; g.font = `500 11px ${FONT}`;
        const x = Math.max(GUTTER + 24, (s.keys[0] ? this.xAt(s.keys[0].frame) : GUTTER) + 22);
        if (x < w - 60) g.fillText('Press K to keep a pose here · or add a one-click Motion (step 3)', x, top + sy(26));
      }
    });
    // the selection's bracket: a bar over the selected keys, with two ends that stretch them
    const br = this._bracket();
    if (br && !(drag && drag.mode === 'move')) {
      const x0 = Math.max(GUTTER, br.x0), x1 = Math.min(w, br.x1);
      if (x1 > x0) {
        const grad = g.createLinearGradient(x0, 0, x1, 0); grad.addColorStop(0, '#ff4f9a'); grad.addColorStop(1, '#a855f7');
        g.fillStyle = grad; g.beginPath(); g.roundRect(x0, br.y, x1 - x0, 4, 2); g.fill();
        g.fillStyle = '#ffffff';
        if (br.x0 >= GUTTER) { g.beginPath(); g.roundRect(br.x0 - 3, br.y - 5, 6, 14, 3); g.fill(); }
        if (br.x1 <= w) { g.beginPath(); g.roundRect(br.x1 - 3, br.y - 5, 6, 14, 3); g.fill(); }
      }
    }
    // the box being drawn (marching ants)
    if (this.box) {
      const b = this.box, x0 = Math.min(b.x0, b.x1), y0 = Math.min(b.y0, b.y1);
      g.fillStyle = 'rgba(255,79,154,.08)'; g.fillRect(x0, y0, Math.abs(b.x1 - b.x0), Math.abs(b.y1 - b.y0));
      g.save(); g.setLineDash([5, 4]); g.lineDashOffset = reducedMotion() ? 0 : -(now / 16) * 0.5; g.strokeStyle = '#ff8cc4'; g.lineWidth = 1.2;
      g.strokeRect(x0 + 0.5, y0 + 0.5, Math.abs(b.x1 - b.x0), Math.abs(b.y1 - b.y0)); g.restore();
    }
    g.restore();

    // the extra rows other features added (between the ruler and the lanes)
    if (this.rows.length) {
      let y = RULER;
      for (const r of this.rows) {
        const hh = r.height || 0;
        g.save();
        g.beginPath(); g.rect(0, y, w, hh); g.clip();
        g.fillStyle = 'rgba(255,255,255,0.02)'; g.fillRect(0, y, w, hh);
        if (r.label) { g.fillStyle = muted; g.font = `600 11px ${FONT}`; g.textBaseline = 'middle'; g.fillText(r.label, 14, y + hh / 2); }
        try { r.draw && r.draw(g, { x0: GUTTER, x1: w, y, h: hh, xAt: f => this.xAt(f), frameAt: x => this.frameAt(x), app: this.app, playing: !!this.app.playing }); }
        catch (err) { if (!r._warned) { r._warned = true; console.error(err); } }
        g.restore();
        g.strokeStyle = line; g.beginPath(); g.moveTo(0, y + hh + 0.5); g.lineTo(w, y + hh + 0.5); g.stroke();
        y += hh;
      }
    }

    // lanes scrolled: a thin bar on the right shows where you are
    if (this.maxV > 0) {
      const track = hgt - lanesTop - 8, all = p.sims.length * LN;
      const len = Math.max(18, track * (track / all)), pos = lanesTop + 4 + (track - len) * (this.vscroll / this.maxV);
      g.fillStyle = 'rgba(255,255,255,0.18)'; g.beginPath(); g.roundRect(w - 6, pos, 3, len, 2); g.fill();
    }

    // ruler (shared with the Curves view)
    this._geo = drawRuler(g, { x0: GUTTER, w, h: hgt, xAt: f => this.xAt(f), pxPerFrame: this.pxPerFrame, scroll: this.scroll, length: p.length,
      frame: this.store.frame, playing: !!this.app.playing, range, loopBadge: this._loopBadge(), summary: this._summary(), css });
    this._geo.endX = endX; this._geo.roomEndX = roomX;   // for tests: where the loop ends and where the room ends

    // dragging keys: a dashed guide down the lanes and a bubble with the frame and how far it moved
    if (drag) {
      const f = drag.mode === 'stretch' ? Math.round(drag.pivot + (drag.grab - drag.pivot) * (drag.s || 1)) : drag.grab + (drag.df || 0), x = this.xAt(f);
      if (x >= GUTTER && x <= w) {
        g.save(); g.setLineDash([3, 4]); g.strokeStyle = 'rgba(255,255,255,0.35)';
        g.beginPath(); g.moveTo(x + 0.5, RULER); g.lineTo(x + 0.5, hgt); g.stroke(); g.restore();
        const dlt = drag.df || 0, n = drag.sel0.size;
        const txt = drag.mode === 'stretch' ? `Stretch ×${(drag.s || 1).toFixed(2).replace(/\.?0+$/, '')}`
          : n > 1 ? `${n} keys · ${dlt >= 0 ? '+' : ''}${dlt} frame${Math.abs(dlt) === 1 ? '' : 's'}` : `frame ${f}  ${dlt >= 0 ? '+' : ''}${dlt}`;
        g.font = `700 10px ${MONO}`;
        const tw = g.measureText(txt).width + 12, bx = Math.min(w - tw - 2, Math.max(GUTTER + 2, x - tw / 2));
        g.fillStyle = 'rgba(20,14,25,0.92)'; g.beginPath(); g.roundRect(bx, RULER + 2, tw, 16, 6); g.fill();
        g.fillStyle = '#fff'; g.textAlign = 'left'; g.textBaseline = 'middle'; g.fillText(txt, bx + 6, RULER + 10);
      }
    }
    g.strokeStyle = line; g.beginPath(); g.moveTo(GUTTER + 0.5, 0); g.lineTo(GUTTER + 0.5, hgt); g.stroke();
    if (!p.sims.length) {
      g.fillStyle = muted; g.font = `500 12.5px ${FONT}`;
      g.fillText('Add a sim in step 1 (Scene), or open the Library and import an animation.', GUTTER + 16, lanesTop + 24);
    }
  }

  // [frame, every key there selected] for the ruler's summary diamonds
  _summary() {
    const byFrame = new Map();
    for (const s of this.store.project.sims) for (const k of s.keys) {
      const all = byFrame.has(k.frame) ? byFrame.get(k.frame) : true;
      byFrame.set(k.frame, all && this.sel.has(KO.kid(s.id, k.frame)));
    }
    return [...byFrame.entries()];
  }
  _loopBadge() {
    if (!this.store.project.loop || !this.app.loopStatus) return null;
    let st;
    try { st = this.app.loopStatus(); } catch { return null; }
    if (!st || !st.length) return null;
    return st.some(x => x.kind === 'pause' || x.kind === 'snap' || x.kind === 'pop') ? 'warn' : 'ok';
  }
}
