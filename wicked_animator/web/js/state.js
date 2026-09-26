// The project being edited, undo/redo, and change notifications.
import { SIM_COLORS, SKIN_TONES } from './bones.js';
import { splitFaceBones } from './animation.js';

export function uid(prefix = 'p') { return prefix + Date.now().toString(36) + Math.random().toString(36).slice(2, 7); }

export function newProject() {
  return {
    version: 3,
    faceStyle: 'creator',       // faces move as far as creators move them; projects from before keep 'classic'
    uid: uid('a'),
    name: 'Untitled animation',
    author: localStorageGet('author', ''),
    category: 'VAGINAL',
    tags: [],
    loops: 10,
    naked: 'ALL',
    furniture: 'floor',
    locations: ['FLOOR'],
    length: 90,
    fitLength: true,            // the loop length follows the last body key; typing a length turns this off
    fps: 30,
    loop: true,
    autoCurve: 'clamped',       // "Auto smooth" never overshoots; projects saved before this keep 'legacy' (Store.load)
    refs: [],                   // reference pictures and videos (never exported)
    events: [],                 // moments (cum, undress...) on the project's own track
    sims: [],
  };
}

// Key clean-up when loading (spec_editing 2.2): a custom timing without a valid curve becomes "Ease in & out", and
// the only key type there is is 'breakdown' (an in-between key).
const validCurve = c => Array.isArray(c) && c.length === 4 && c.every(Number.isFinite) && c[0] >= 0 && c[0] <= 1 && c[2] >= 0 && c[2] <= 1;
export function cleanKey(k) {
  if (!k || typeof k !== 'object') return k;
  if (k.ease === 'custom' && !validCurve(k.curve)) { k.ease = 'smooth'; delete k.curve; }
  else if (k.ease !== 'custom' && 'curve' in k) delete k.curve;
  if ('type' in k && k.type !== 'breakdown') delete k.type;
  return k;
}

export const BODY_TYPES = {
  yf: { label: 'Female', short: 'F', gender: 'FEMALE' },
  ym: { label: 'Male', short: 'M', gender: 'MALE' },
  yf_futa: { label: 'Female with penis', short: 'F+', gender: 'MALE' },
};

export function newSim(project, frame = 'yf') {
  const k = project.sims.length;
  // "Female 2", never a second "Female 1" (a female body with a penis is also called Female)
  const word = BODY_TYPES[frame]?.label.split(' ')[0] || 'Sim';
  const used = new Set(project.sims.map(s => s.label));
  let n = 1;
  while (used.has(`${word} ${n}`)) n++;
  return {
    id: uid('s') + k,
    label: `${word} ${n}`,
    frame,
    gender: BODY_TYPES[frame]?.gender || 'BOTH',
    color: SIM_COLORS[k % SIM_COLORS.length],
    skin: SKIN_TONES[(k * 3 + 1) % SKIN_TONES.length],
    keys: [],
    pins: {},
    sounds: [],
    layers: [],
    visible: true,
  };
}

// Bring a project from an older version up to date, in place (safe to call more than once).
// Version 3: the jaw and the tongue moved from key.pose into the face channel (key.faceBones). Every key becomes a
// face key with the same frame and ease, so the face plays exactly as before; the old look stays ('classic').
export function migrateProject(project) {
  if (!project || (project.version || 1) >= 3) return project;
  for (const s of project.sims || []) for (const k of s.keys || []) if (k && k.pose) splitFaceBones(k, { always: true });
  if (!project.faceStyle) project.faceStyle = 'classic';
  project.version = 3;
  return project;
}

export function localStorageGet(k, d) {
  try { const v = localStorage.getItem('fsa.' + k); return v === null ? d : JSON.parse(v); } catch { return d; }
}
export function localStorageSet(k, v) {
  try { localStorage.setItem('fsa.' + k, JSON.stringify(v)); } catch { /* private mode */ }
}
export function localStorageRemove(k) {
  try { localStorage.removeItem('fsa.' + k); } catch { /* private mode */ }
}

// Undo keeps up to 200 steps, and at most about 60 million characters of them (~120 MB) once there are more than 10 -
// big imported animations would otherwise fill the memory.
const UNDO_STEPS = 200, UNDO_CHARS = 60e6;

export class Store {
  constructor() {
    this.project = newProject();
    this.listeners = new Set();
    this.undo = [];               // [{s: project JSON, label, t}] - oldest first
    this.redo = [];
    this.undoChars = 0;
    this.dirty = false;
    this.frame = 0;
    this.selected = { sim: null, bone: null };
  }
  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  emit(what) { for (const fn of this.listeners) fn(what); }

  sim(id = this.selected.sim) { return this.project.sims.find(s => s.id === id) || null; }

  // Call before a change that should be undoable. The label names it in the Undo list ("Move 6 keys").
  checkpoint(label = '') {
    const s = JSON.stringify(this.project);
    this.undo.push({ s, label: label || '', t: Date.now() });
    this.undoChars += s.length;
    while (this.undo.length > UNDO_STEPS || (this.undoChars > UNDO_CHARS && this.undo.length > 10)) this.undoChars -= this.undo.shift().s.length;
    this.redo.length = 0;
    this.setDirty(true);
  }
  // Name the step just made (for code that made the checkpoint before it knew what the change would be).
  labelLast(label) { const e = this.undo[this.undo.length - 1]; if (e && label) e.label = label; }
  setDirty(v) { this.dirty = v; this.emit('dirty'); }
  // -> false when there is nothing to undo, else the step's label (or true when it has none)
  undoStep() {
    if (!this.undo.length) return false;
    const e = this.undo.pop();
    this.undoChars -= e.s.length;
    this.redo.push({ s: JSON.stringify(this.project), label: e.label, t: e.t });
    this.project = JSON.parse(e.s);
    this.setDirty(true);
    this.emit('project');
    return e.label || true;
  }
  redoStep() {
    if (!this.redo.length) return false;
    const e = this.redo.pop();
    const s = JSON.stringify(this.project);
    this.undo.push({ s, label: e.label, t: Date.now() });
    this.undoChars += s.length;
    this.project = JSON.parse(e.s);
    this.setDirty(true);
    this.emit('project');
    return e.label || true;
  }
  // The JSON of the project as it was before the last change (null when there is none).
  peekUndo() { const e = this.undo[this.undo.length - 1]; return e ? e.s : null; }
  // The last n steps, newest first: [{label, t}].
  history(n = 15) { return this.undo.slice(-n).reverse().map(e => ({ label: e.label || 'Change', t: e.t })); }
  // Undo i + 1 steps at once (i = index in history()), with one 'project' notice.
  undoTo(i) {
    const n = Math.min(this.undo.length, Math.max(0, i) + 1);
    if (!n) return false;
    let cur = JSON.stringify(this.project), last = null;
    for (let k = 0; k < n; k++) {
      const e = this.undo.pop();
      this.undoChars -= e.s.length;
      this.redo.push({ s: cur, label: e.label, t: e.t });
      cur = e.s; last = e;
    }
    this.project = JSON.parse(cur);
    this.setDirty(true);
    this.emit('project');
    return (last && last.label) || true;
  }
  load(project) {
    const old = (project && project.version) || 1;
    this.project = Object.assign(newProject(), project);
    // saved before "Auto smooth" was clamped: it keeps the old curve, so nothing moves until the user switches
    if (!project || !('autoCurve' in project)) this.project.autoCurve = 'legacy';
    // saved before "Fit to keys" existed: a deliberate loop must never change length behind the owner's back
    if (!project || !('fitLength' in project)) this.project.fitLength = false;
    this.project.refs = Array.isArray(project && project.refs) ? project.refs.filter(r => r && r.file && r.kind) : [];
    if (!Array.isArray(this.project.events)) this.project.events = [];
    // a project from before faces could be posed by hand: move the jaw and tongue into the face channel and keep
    // its look (Object.assign above gave it today's version and style; the saved ones decide)
    if (old < 3) { this.project.version = old; if (!project.faceStyle) delete this.project.faceStyle; }
    if (!this.project.uid) this.project.uid = uid('a');
    for (const s of this.project.sims) {
      s.pins = s.pins || {}; s.sounds = s.sounds || []; s.keys = s.keys || []; s.layers = s.layers || [];
      if (s.visible === undefined) s.visible = true;
      for (const k of s.keys) { if (!k.ease) k.ease = 'auto'; cleanKey(k); }
    }
    migrateProject(this.project);
    this.undo.length = 0; this.redo.length = 0; this.undoChars = 0;
    this.frame = 0;
    this.selected = { sim: this.project.sims[0] ? this.project.sims[0].id : null, bone: null };
    this.setDirty(false);
    this.emit('project');
  }
}
