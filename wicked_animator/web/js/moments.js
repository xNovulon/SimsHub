// Moments (spec_game 3): what WickedWhims does to the sims at a time in the loop - cum on a body part, undressing,
// taking a condom off, an effect at a body part (drool, splash...) - plus notes for yourself (never exported).
// They live in project.events (one list for the project; each has a target sim) and are written into the
// animation's XML on Send to game.
//
// This file: the plain sentence for a moment, who it happens to by default, the moment dialog (with the effect
// picker), the Finish preset and the right-click menu of the Moments row. features/game.js wires it into the app.
import { h, icon, modal, toast, choiceBar, fillRange } from './ui.js';
import { uid } from './state.js';
import { nakedFor } from './tags.js';
import { simVoice } from './audio.js';
import { activeCum } from './cumskin.js';
import { effectKind, drawPreview, rememberEffectGroups } from './effects.js';

export { activeCum };

// ---------------------------------------------------------------- words
export const CUM_PARTS = [['FACE', 'Face'], ['CHEST', 'Chest'], ['BELLY', 'Belly'], ['UPPER_BACK', 'Upper back'],
  ['LOWER_BACK', 'Lower back'], ['VAGINA', 'Vagina'], ['BUTT', 'Butt'], ['FEET', 'Feet']];
export const CUM_LABEL = Object.fromEntries(CUM_PARTS);
export const LEVELS = [[1, 'A little'], [2, 'More'], [3, 'A lot']];
export const NAKED_PARTS = [['TOP', 'Top'], ['BOTTOM', 'Bottom'], ['TOP_UNDERWEAR', 'Top to underwear'],
  ['BOTTOM_UNDERWEAR', 'Bottom to underwear'], ['SHOES', 'Shoes'], ['ALL', 'Everything']];
const NAKED_LABEL = { ...Object.fromEntries(NAKED_PARTS), FORCE_ALL: 'Everything' };
export const TYPES = [['CUM', 'Cum', 'drop'], ['UNDRESS', 'Undress', 'shirt'], ['REMOVE_CONDOM', 'Condom off', 'ring'],
  ['EFFECT', 'Effect', 'fx'], ['NOTE', 'Note', 'pin']];
export const TYPE_LABEL = Object.fromEntries(TYPES.map(([k, t]) => [k, t]));
// the Finish buttons (the Sounds & moments step, Magic's Finish select): part -> where the cum goes
export const FINISH_PARTS = [['inside', 'Inside'], ['face', 'Face'], ['chest', 'Chest'], ['belly', 'Belly'], ['back', 'Back'],
  ['butt', 'Butt'], ['feet', 'Feet']];
const PART_OF = { inside: 'INSIDE', face: 'FACE', chest: 'CHEST', belly: 'BELLY', back: 'UPPER_BACK', upper_back: 'UPPER_BACK',
  lower_back: 'LOWER_BACK', butt: 'BUTT', feet: 'FEET', vagina: 'VAGINA', mouth: 'FACE' };
// the body parts effects play at (checked rig bones; the server's /api/effects gives the same list)
export const JOINTS = [
  { id: 'penis_tip', label: 'Tip of the penis', bone: 'b__Penis_Tip', needs: 'penis' },
  { id: 'penis_mid', label: 'Middle of the penis', bone: 'b__Penis_Mid', needs: 'penis' },
  { id: 'penis_base', label: 'Base of the penis', bone: 'b__Penis_Base', needs: 'penis' },
  { id: 'balls', label: 'Balls', bone: 'b__Penis_Testicles', needs: 'penis' },
  { id: 'mouth', label: 'Mouth (lower lip)', bone: 'b__LoLip__', needs: null },
  { id: 'tongue', label: 'Tongue', bone: 'b__Tounge__3', needs: null },
  { id: 'chin', label: 'Chin', bone: 'b__CAS_Chin__', needs: null },
  { id: 'l_palm', label: 'Left palm', bone: 'b__L_Stigmata', needs: null },
  { id: 'r_palm', label: 'Right palm', bone: 'b__R_Stigmata', needs: null },
  { id: 'anus', label: 'Anus', bone: 'b__Low_Anus', needs: null },
  { id: 'vagina', label: 'Vagina', bone: 'b__Low_Vagina__', needs: 'vagina' },
  { id: 'forehead', label: 'Forehead (sweat)', bone: 'b__L_MidBrow__', needs: null },
  { id: 'eyes', label: 'Eyes (tears)', bone: 'b__Head__', needs: null },
  { id: 'l_breast', label: 'Left breast', bone: 'b__CAS_L_Breast__', needs: null },
  { id: 'r_breast', label: 'Right breast', bone: 'b__CAS_R_Breast__', needs: null },
  { id: 'chest', label: 'Chest', bone: 'b__Spine2__', needs: null },
  { id: 'hips', label: 'Hips', bone: 'b__Pelvis__', needs: null },
];
export const EFFECT_GROUPS = ['Cum & splashes', 'Drool & strands', 'Drips & sweat', 'Streams', 'Tears', 'Steam & breath', 'Sparkles & flash'];
const nice = s => String(s || '').replace(/^b__|__$/g, '').replace(/_/g, ' ').trim();
export const secs = (frame, fps = 30) => (frame / fps).toFixed(1).replace(/\.0$/, '') + ' s';

// ---------------------------------------------------------------- sims
export const hasPenis = (app, s) => !!s && (s.frame === 'ym' || s.frame === 'yf_futa' || !!(app.simViews && app.simViews.get(s.id) && app.simViews.get(s.id).hasPenis));
export const penisSims = app => app.store.project.sims.filter(s => hasPenis(app, s));
export const giverOf = app => penisSims(app)[0] || null;
const roleOf = (app, s) => (typeof app.roleOf === 'function' ? app.roleOf(s) : hasPenis(app, s) ? 'giver' : 'receiver');
const simById = (app, id) => app.store.project.sims.find(s => s.id === id) || null;
const nameOf = (app, id) => (simById(app, id) || { label: 'a sim that is gone' }).label;

// Who a new moment happens to: cum on the selected sim unless it only gives (then the first who receives); the
// condom comes off the first sim with a penis; undressing and effects: the selected sim.
export function defaultTarget(app, type) {
  const p = app.store.project, sel = app.store.sim && app.store.sim();
  const first = sel || p.sims[0] || null;
  if (type === 'CUM') {
    if (sel && roleOf(app, sel) !== 'giver') return sel;
    return p.sims.find(s => ['receiver', 'both'].includes(roleOf(app, s))) || p.sims.find(s => !hasPenis(app, s)) || first;
  }
  if (type === 'REMOVE_CONDOM') return giverOf(app) || first;
  return first;
}

// The act WickedWhims gives a finish (vaginal, anal, oral...).
export function actOf(app) {
  const p = app.store.project;
  if (p.act) return p.act;
  if (['VAGINAL', 'ANAL', 'ORALJOB', 'HANDJOB', 'FOOTJOB'].includes(p.category)) return p.category;
  const tags = p.tags || [];
  if (tags.includes('ANAL')) return 'ANAL';
  if (tags.some(t => ['BLOWJOB', 'DEEP_THROAT', 'CUNNILINGUS', 'CUM_IN_MOUTH'].includes(t))) return 'ORALJOB';
  return 'VAGINAL';
}

// ---------------------------------------------------------------- effect names
const effectInfo = new Map();              // name (lower) -> {name, label, group, uses}
export const validity = new Map();         // name (lower) -> {valid, equivalent}
let catalogs = new Map();                  // joint -> Promise<{popular, joints, groups}>
export function rememberEffects(items) {
  for (const x of items || []) if (x && x.name) effectInfo.set(String(x.name).toLowerCase(), x);
  rememberEffectGroups(items);
  for (const x of items || []) if (x && x.name && !validity.has(String(x.name).toLowerCase())) validity.set(String(x.name).toLowerCase(), { valid: true, equivalent: x.name });
}
export function effectCatalog(joint = '') {
  if (!catalogs.has(joint)) {
    catalogs.set(joint, fetch('/api/effects' + (joint ? '?joint=' + encodeURIComponent(joint) : ''))
      .then(r => (r.ok ? r.json() : { popular: [] })).catch(() => ({ popular: [] }))
      .then(d => { rememberEffects(d.popular); return d; }));
  }
  return catalogs.get(joint);
}
export function searchEffects(q) {
  return fetch('/api/effects?q=' + encodeURIComponent(q)).then(r => (r.ok ? r.json() : { items: [] })).catch(() => ({ items: [] }))
    .then(d => { rememberEffects(d.items); return d.items || []; });
}
// Are these real, adult game effects? (import, export checks) -> fills `validity`
export async function checkEffects(names) {
  const todo = [...new Set((names || []).filter(Boolean).map(n => String(n).trim()))].filter(n => !validity.has(n.toLowerCase()));
  if (!todo.length) return validity;
  for (let i = 0; i < todo.length; i += 60) {
    const part = todo.slice(i, i + 60);
    try {
      const r = await fetch('/api/effects?check=' + encodeURIComponent(part.join(',')));
      const d = r.ok ? await r.json() : { checks: {} };
      for (const [n, v] of Object.entries(d.checks || {})) validity.set(n.toLowerCase(), v);
    } catch { /* no server: nothing known */ }
  }
  return validity;
}
export function effectLabel(name) {
  const x = effectInfo.get(String(name || '').toLowerCase());
  return x && x.label ? x.label : nice(name).replace(/\b(ep|gp|sp|s)\d+\b/g, '').replace(/\s+/g, ' ').trim() || 'Effect';
}
export function jointLabel(bone) { const j = JOINTS.find(x => x.bone === bone); return j ? j.label.replace(/ \(.*\)$/, '').toLowerCase() : nice(bone).toLowerCase(); }
export function jointsFor(app, sim) {
  const penis = hasPenis(app, sim);
  return JOINTS.filter(j => j.needs === null || (j.needs === 'penis' ? penis : !penis));
}

// ---------------------------------------------------------------- the plain sentence
// "Cum on Female 1's face, level 2 · 2.3 s"
export function momentLabel(ev, app) {
  if (!ev) return '';
  const fps = app.store.project.fps || 30, at = secs(ev.frame, fps);
  const who = ev.sim ? nameOf(app, ev.sim) : '';
  let s;
  switch (ev.type) {
    case 'CUM': s = `Cum on ${who}'s ${(CUM_LABEL[ev.cum] || 'body').toLowerCase()}, level ${ev.level || 1}`; break;
    case 'UNDRESS': s = `Undress ${who}: ${(NAKED_LABEL[ev.naked] || 'clothes').toLowerCase()}`; break;
    case 'REMOVE_CONDOM': s = `${who}'s condom comes off`; break;
    case 'EFFECT': {
      const endF = ev.end !== undefined ? ev.end : ev.frame + fps;
      s = `${effectLabel(ev.effect)} at ${who}'s ${jointLabel(ev.joint)}`;
      return `${s} · ${secs(ev.frame, fps).replace(' s', '')}-${secs(endF, fps)}${ev.skipWithCondom ? ' · not with a condom' : ''}`;
    }
    case 'NOTE': return `Note: ${ev.text || '(empty)'} · ${at}`;
    default: s = ev.type;
  }
  return `${s} · ${at}${ev.skipWithCondom ? ' · not with a condom' : ''}`;
}

// ---------------------------------------------------------------- condoms (preview only)
// A moment that is skipped when its sim wears a condom, on a sim that wears one here, before any "condom off".
export function skippedByCondom(app, ev, frame) {
  if (!ev || !ev.skipWithCondom) return false;
  const s = simById(app, ev.sim);
  if (!s || !s.previewCondom) return false;
  const f = frame === undefined ? ev.frame : frame;
  return !(app.store.project.events || []).some(e => e.type === 'REMOVE_CONDOM' && e.sim === s.id && e.frame <= f);
}

// ---------------------------------------------------------------- changing moments (one checkpoint each)
function events(app) {
  const p = app.store.project;
  if (!Array.isArray(p.events)) p.events = [];
  return p.events;
}
function clampMoment(app, ev) {
  const len = app.store.project.length;
  ev.frame = Math.max(0, Math.min(len - 1, Math.round(ev.frame || 0)));
  if (ev.type === 'EFFECT') ev.end = Math.max(ev.frame, Math.min(len, Math.round(ev.end !== undefined ? ev.end : ev.frame + (app.store.project.fps || 30))));
  else delete ev.end;
  if (ev.type === 'CUM') ev.level = Math.max(1, Math.min(3, Math.round(ev.level || 1)));
  return ev;
}
// only the fields a type uses are kept (a clean project file)
const FIELDS = { CUM: ['cum', 'level'], UNDRESS: ['naked'], REMOVE_CONDOM: [], EFFECT: ['end', 'effect', 'joint'], NOTE: ['text'] };
export function cleanMoment(ev) {
  const keep = new Set(['id', 'type', 'frame', 'sim', 'skipWithCondom', 'group', 'auto', ...(FIELDS[ev.type] || [])]);
  for (const k of Object.keys(ev)) if (!keep.has(k)) delete ev[k];
  if (!ev.skipWithCondom) delete ev.skipWithCondom;
  if (!ev.group) delete ev.group;
  if (!ev.auto) delete ev.auto;
  return ev;
}

export const nakedFromStart = (app, s) => !!s && nakedFor(app.store.project.category, s) === 'ALL';
// Undressing a sim that is naked from the start does nothing: it starts dressed then (same undo step).
function dressFirst(app, ev) {
  if (ev.type !== 'UNDRESS') return false;
  const s = simById(app, ev.sim);
  if (!s || !nakedFromStart(app, s)) return false;
  s.naked = 'NONE';
  toast(`${s.label} now starts dressed, so there is something to take off.`);
  return true;
}

export function addMomentTo(app, ev, { checkpoint = true, quiet = false } = {}) {
  const m = cleanMoment(clampMoment(app, { id: uid('e'), ...ev }));
  if (checkpoint) app.store.checkpoint();
  events(app).push(m);
  dressFirst(app, m);
  if (!quiet) afterMoments(app);
  return m;
}
export function updateMomentIn(app, id, patch, { checkpoint = true } = {}) {
  const ev = events(app).find(e => e.id === id);
  if (!ev) return null;
  if (checkpoint) app.store.checkpoint();
  Object.assign(ev, patch);
  cleanMoment(clampMoment(app, ev));
  if (patch.type || patch.sim || patch.naked) dressFirst(app, ev);
  afterMoments(app);
  return ev;
}
// A moment placed by a preset takes its group with it (group: false removes only that one).
export function removeMomentFrom(app, id, { group = true, checkpoint = true } = {}) {
  const list = events(app), ev = list.find(e => e.id === id);
  if (!ev) return 0;
  if (checkpoint) app.store.checkpoint();
  const gone = new Set(group && ev.group ? list.filter(e => e.group === ev.group).map(e => e.id) : [id]);
  app.store.project.events = list.filter(e => !gone.has(e.id));
  // the preset's voices go with it
  if (group && ev.group) for (const s of app.store.project.sims) if ((s.sounds || []).some(x => x.moment === ev.group)) s.sounds = s.sounds.filter(x => x.moment !== ev.group);
  if (app.selectedEvent && gone.has(app.selectedEvent)) app.selectedEvent = null;
  afterMoments(app);
  return gone.size;
}
function afterMoments(app) {
  if (typeof app.afterEdit === 'function') app.afterEdit();
  if (typeof app.momentsChanged === 'function') app.momentsChanged();
}

// ---------------------------------------------------------------- Finish preset (one click, one undo step)
// part: inside | face | chest | belly | back | butt | feet (or a cum type). frame: where it happens (the playhead when
// it is inside the loop, else 70% of it). Cum on the receiver (level 2), the drool of the finish at the giver's tip
// (or dripping out, for inside), and the game's finish voices when the sims' voices have them.
export function finishPreset(app, part = 'face', frame = null, { checkpoint = true, quiet = false, voices = true } = {}) {
  const p = app.store.project, len = p.length, fps = p.fps || 30;
  const r = defaultTarget(app, 'CUM'), g = giverOf(app);
  if (!r) { if (!quiet) toast('Add a sim first.'); return null; }
  let F = Math.round(frame === null || frame === undefined ? app.store.frame : frame);
  if (!(F > 0 && F < len - 8)) F = Math.round(0.7 * len);
  const key = PART_OF[String(part || '').toLowerCase()] || (CUM_LABEL[String(part || '').toUpperCase()] ? String(part).toUpperCase() : 'FACE');
  const act = actOf(app);
  let cum = key === 'INSIDE' ? ({ VAGINAL: 'VAGINA', ANAL: 'BUTT', ORALJOB: 'FACE', FOOTJOB: 'FEET', HANDJOB: 'BELLY' }[act] || 'VAGINA') : key;
  if (cum === 'VAGINA' && hasPenis(app, r)) cum = 'BUTT';
  if (checkpoint) app.store.checkpoint();
  const list = events(app);
  // a new Finish replaces the last one (a group placed by a preset with a cum moment in it), and its voices
  const old = finishGroups(list);
  p.events = list.filter(e => !(e.group && old.has(e.group)));
  for (const s of p.sims) if ((s.sounds || []).some(x => old.has(x.moment))) s.sounds = s.sounds.filter(x => !old.has(x.moment));
  const group = uid('g');
  const add = ev => { const m = cleanMoment(clampMoment(app, { id: uid('e'), group, auto: true, ...ev })); p.events.push(m); return m; };
  const made = [add({ type: 'CUM', frame: F, sim: r.id, cum, level: 2 })];
  if (key === 'INSIDE') {
    const joint = cum === 'BUTT' || act === 'ANAL' || hasPenis(app, r) ? 'b__Low_Anus' : cum === 'FACE' ? 'b__LoLip__' : 'b__Low_Vagina__';
    const s0 = Math.min(len - 1, F + 15);
    made.push(add({ type: 'EFFECT', frame: s0, end: Math.min(len, F + 60), sim: r.id, effect: 'pet_small_drool', joint }));
  } else if (g) {
    made.push(add({ type: 'EFFECT', frame: Math.max(0, F - 6), end: Math.min(len, F + 30), sim: g.id, effect: 'pet_small_drool_front', joint: 'b__Penis_Tip', skipWithCondom: true }));
  }
  // the game's own finish voices, in each sim's voice (when that voice has the line)
  const lines = app.voiceLines;
  const hasLine = (name, s) => !lines || lines.some(x => x.name === name && (x.voices || []).includes(simVoice(s)));
  const say = (s, name, at) => {
    if (!s || !hasLine(name, s)) return;
    s.sounds = s.sounds || [];
    s.sounds.push({ frame: Math.max(0, Math.min(len - 1, Math.round(at))), name, kind: 'voice', moment: group });
  };
  if (voices && g && g !== r) say(g, 'vo_expr_woohoo_big_1finish_x', F - 10);
  if (voices) say(r, 'vo_expr_woohoo_big_1finish_y', F - 5);
  afterMoments(app);
  if (!quiet) {
    const where = cum === 'VAGINA' ? 'inside' : `on ${r.label}'s ${CUM_LABEL[cum].toLowerCase()}`;
    if (!penisSims(app).length) toast(`Finish ${where} at ${secs(F, fps)} - but WickedWhims only shows cum when someone in the act has a penis.`);
    else if (p.category !== 'CLIMAX' && (p.loops || 10) > 1) climaxBar(app);
    else toast(`Finish ${where} at ${secs(F, fps)}.`, 'ok');
  }
  return made;
}

// The groups a Finish placed (auto moments with a cum moment among them).
export function finishGroups(list) {
  const out = new Set();
  for (const e of list || []) if (e.auto && e.group && e.type === 'CUM') out.add(e.group);
  return out;
}

// "In the game cum adds up every loop" - with the one-click fix.
export function climaxBar(app) {
  return choiceBar('In the game cum adds up every loop. For a one-time finish, make it a Climax.', [
    { label: 'Make it a climax', primary: true, onClick: () => makeClimax(app) }]);
}
export function makeClimax(app) {
  const p = app.store.project;
  const act = actOf(app);
  app.store.checkpoint();
  p.act = act;
  p.category = 'CLIMAX';
  p.loops = 1;
  if (typeof app.refreshTitle === 'function') app.refreshTitle();
  afterMoments(app);
  toast('It is a climax now: it plays once, and the cum shows once.', 'ok');
}

// ---------------------------------------------------------------- the right-click menu of the Moments row
export function momentMenuItems(app, ev, frame) {
  const p = app.store.project;
  if (ev) {
    const inGroup = ev.group && (p.events || []).filter(e => e.group === ev.group).length > 1;
    const s = simById(app, ev.sim);
    return [
      { heading: momentLabel(ev, app) },
      { label: 'Change…', icon: 'pose', onClick: () => app.editMoment(ev.id) },
      { label: 'Move to the playhead', icon: 'arrow', onClick: () => {
        const d = Math.round(app.store.frame) - ev.frame;
        app.store.checkpoint();
        for (const e of p.events.filter(x => x === ev || (ev.group && x.group === ev.group))) { e.frame += d; if (e.end !== undefined) e.end += d; clampMoment(app, e); }
        afterMoments(app);
      } },
      ev.type !== 'NOTE' && s ? { label: ev.skipWithCondom ? `Also when ${s.label} wears a condom` : `Skip when ${s.label} wears a condom`, icon: 'ring',
        onClick: () => app.updateMoment(ev.id, { skipWithCondom: !ev.skipWithCondom }) } : null,
      '-',
      inGroup ? { label: 'Delete this one', danger: true, icon: 'trash', onClick: () => app.removeMoment(ev.id, { group: false }) } : null,
      { label: inGroup ? 'Delete the whole finish' : 'Delete', danger: true, icon: 'trash', onClick: () => app.removeMoment(ev.id) },
    ].filter(Boolean);
  }
  const r = defaultTarget(app, 'CUM'), u = defaultTarget(app, 'UNDRESS'), g = giverOf(app);
  const items = [{ heading: `Finish here · ${secs(frame, p.fps || 30)}` }];
  if (r) {
    for (const [t, label] of CUM_PARTS) {
      if (t === 'VAGINA' && hasPenis(app, r)) continue;
      items.push({ label: `Cum on ${r.label}'s ${label.toLowerCase()}`, icon: 'drop', onClick: () => app.addMoment({ type: 'CUM', frame, sim: r.id, cum: t, level: 2 }) });
    }
  }
  if (u) {
    items.push('-', { heading: 'Clothes' });
    for (const [n, label] of [['TOP', 'top'], ['BOTTOM', 'bottom'], ['ALL', 'everything']]) items.push({ label: `Undress ${u.label}: ${label}`, icon: 'shirt', onClick: () => app.addMoment({ type: 'UNDRESS', frame, sim: u.id, naked: n }) });
  }
  items.push('-');
  if (g) items.push({ label: `Remove ${g.label}'s condom`, icon: 'ring', onClick: () => app.addMoment({ type: 'REMOVE_CONDOM', frame, sim: g.id }) });
  items.push({ label: 'Effect at a body part…', icon: 'fx', onClick: () => app.editMoment(null, frame, { type: 'EFFECT' }) });
  items.push({ label: 'Note…', icon: 'pin', onClick: () => app.editMoment(null, frame, { type: 'NOTE' }) });
  return items;
}

// ---------------------------------------------------------------- a small body that lights the part
const BODY_FRONT = { FACE: 'M28 6a8 9 0 1 0 0.1 0z', CHEST: 'M17 27h22v12H17z', BELLY: 'M19 40h18v11H19z', VAGINA: 'M24 52h8l-4 7z', FEET: 'M16 96h9v5h-9zM31 96h9v5h-9z' };
const BODY_BACK = { UPPER_BACK: 'M17 27h22v12H17z', LOWER_BACK: 'M19 40h18v9H19z', BUTT: 'M18 50h20v9H18z', FEET: 'M16 96h9v5h-9zM31 96h9v5h-9z' };
function silhouette(active, pick) {
  const ns = 'http://www.w3.org/2000/svg';
  const el = (tag, attrs) => { const e = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
  const figure = (parts, title) => {
    const svg = el('svg', { viewBox: '0 0 56 106', class: 'cum-body', role: 'img', 'aria-label': title });
    // the outline: head, neck, torso, arms, legs
    svg.append(el('path', { class: 'body', d: 'M28 5a8 9 0 1 0 0.1 0zM24 22h8v4h-8zM16 26h24l-2 26h-20zM16 27l-8 30 4 1 7-24zM40 27l8 30-4 1-7-24zM18 51h9l-2 45h-8zM29 51h9l-1 45h-8z' }));
    for (const [t, d] of Object.entries(parts)) {
      const path = el('path', { d, class: 'spot' + (active === t ? ' on' : ''), 'data-part': t });
      path.addEventListener('click', () => pick(t));
      const tt = el('title', {}); tt.textContent = CUM_LABEL[t]; path.append(tt);
      svg.append(path);
    }
    const lab = el('text', { x: 28, y: 105, 'text-anchor': 'middle', class: 'lab' }); lab.textContent = title;
    svg.append(lab);
    return svg;
  };
  return h('div', { class: 'cum-bodies' }, figure(BODY_FRONT, 'front'), figure(BODY_BACK, 'back'));
}

// ---------------------------------------------------------------- the moment dialog
// ev: a moment to change, or null for a new one at `frame`. opts.type / opts.sim start a new one of that kind.
export function openMomentDialog(app, ev = null, frame = null, opts = {}) {
  const p = app.store.project, fps = p.fps || 30, len = p.length;
  const editing = !!ev;
  const start = Math.max(0, Math.min(len - 1, Math.round(frame === null || frame === undefined ? (ev ? ev.frame : app.store.frame) : frame)));
  const type0 = ev ? ev.type : (opts.type || 'CUM');
  const v = {
    type: type0, frame: ev ? ev.frame : start,
    sim: ev ? ev.sim : (opts.sim || (defaultTarget(app, type0) || {}).id),
    cum: (ev && ev.cum) || 'FACE', level: (ev && ev.level) || 2, naked: (ev && ev.naked) || 'TOP',
    effect: (ev && ev.effect) || '', joint: (ev && ev.joint) || '', text: (ev && ev.text) || '',
    end: ev && ev.end !== undefined ? ev.end : Math.min(len, start + fps),
    skipWithCondom: ev ? !!ev.skipWithCondom : null,
  };
  const sim = () => simById(app, v.sim) || p.sims[0];
  const body = h('div', { class: 'moment-dlg' });
  let dlg = null, anim = 0;
  const previews = new Set();
  const skipDefault = () => (v.type === 'EFFECT' ? /^b__Penis_/.test(v.joint) : false);
  const draw = () => {
    body.innerHTML = '';
    previews.clear();
    // what happens
    body.append(h('div', { class: 'seg-inline moment-types' }, TYPES.map(([t, label, ic]) => h('button', {
      class: v.type === t ? 'on' : '', type: 'button',
      onclick: () => {
        if (v.type === t) return;
        v.type = t;
        if (!editing && t !== 'NOTE') v.sim = (defaultTarget(app, t) || sim() || {}).id;
        draw();
      } }, icon(ic), h('span', {}, label)))));
    // to whom
    if (v.type !== 'NOTE' || p.sims.length > 1) {
      body.append(h('div', { class: 'field' }, h('span', {}, v.type === 'NOTE' ? 'About' : 'Happens to'),
        h('div', { class: 'chips' }, p.sims.map(s => h('button', {
          class: 'chipbtn' + (v.sim === s.id ? ' on' : ''), type: 'button', style: { '--sim': s.color },
          onclick: () => { v.sim = s.id; if (v.type === 'EFFECT' && !jointsFor(app, s).some(j => j.bone === v.joint)) v.joint = ''; draw(); },
        }, h('i', { class: 'dot', style: { background: s.color } }), s.label)))));
    }
    const s = sim();
    if (v.type === 'CUM') {
      const penisHere = hasPenis(app, s);
      const parts = CUM_PARTS.filter(([t]) => !(t === 'VAGINA' && penisHere));
      if (v.cum === 'VAGINA' && penisHere) v.cum = 'BUTT';
      body.append(h('div', { class: 'cum-pick' },
        silhouette(v.cum, t => { if (t === 'VAGINA' && penisHere) return; v.cum = t; draw(); }),
        h('div', { class: 'cum-fields' },
          h('div', { class: 'field' }, h('span', {}, 'Where'), h('div', { class: 'chips' }, parts.map(([t, label]) => h('button', {
            class: 'chipbtn' + (v.cum === t ? ' on' : ''), type: 'button', onclick: () => { v.cum = t; draw(); } }, label)))),
          h('div', { class: 'field' }, h('span', {}, 'How much'), h('div', { class: 'seg-inline' }, LEVELS.map(([lv, label]) => h('button', {
            class: v.level === lv ? 'on' : '', type: 'button', onclick: () => { v.level = lv; draw(); } }, label)))),
          penisSims(app).length ? null : h('div', { class: 'warn-box' }, "WickedWhims won't show it: nobody here has a penis."),
          p.category !== 'CLIMAX' && (p.loops || 10) > 1 ? h('div', { class: 'hint' }, 'In the game cum adds up every time the animation loops (up to "a lot"). A Climax plays once.') : null)));
    } else if (v.type === 'UNDRESS') {
      body.append(h('div', { class: 'field' }, h('span', {}, 'What comes off'), h('div', { class: 'chips' }, NAKED_PARTS.map(([n, label]) => h('button', {
        class: 'chipbtn' + (v.naked === n ? ' on' : ''), type: 'button', onclick: () => { v.naked = n; draw(); } }, label)))));
      if (s && nakedFor(p.category, s) === 'ALL') body.append(h('div', { class: 'hint' }, `${s.label} is naked from the start now - adding this makes ${s.label} start dressed.`));
    } else if (v.type === 'REMOVE_CONDOM') {
      body.append(h('div', { class: 'hint' }, `WickedWhims takes ${s ? s.label : 'the sim'}'s condom off here, if they wear one.`));
      if (s && !hasPenis(app, s)) body.append(h('div', { class: 'warn-box' }, `${s.label} has no penis - a condom only comes off a sim with one.`));
    } else if (v.type === 'EFFECT') {
      body.append(effectPicker(app, v, s, previews, () => draw()));
    } else if (v.type === 'NOTE') {
      const t = h('input', { class: 'text', value: v.text, placeholder: 'e.g. she looks at him here', maxlength: 200 });
      t.addEventListener('input', () => { v.text = t.value; });
      body.append(h('label', { class: 'field' }, h('span', {}, 'Note (only for you - never sent to the game)'), t));
    }
    // when
    const at = h('input', { class: 'text small-num', type: 'number', min: 0, max: ((len - 1) / fps).toFixed(2), step: 0.1, value: (v.frame / fps).toFixed(2) });
    at.addEventListener('change', () => {
      const f = Math.max(0, Math.min(len - 1, Math.round((+at.value || 0) * fps)));
      const d = f - v.frame; v.frame = f;
      if (v.type === 'EFFECT') v.end = Math.max(f, Math.min(len, v.end + d));
      draw();
    });
    const when = h('div', { class: 'moment-when' }, h('label', { class: 'field row' }, h('span', {}, 'At'), at, h('span', { class: 'muted' }, `s · frame ${v.frame} of ${len}`)));
    if (v.type === 'EFFECT') {
      const toEnd = v.end >= len;
      const dur = h('input', { type: 'range', min: 0.2, max: Math.max(0.5, (len - v.frame) / fps).toFixed(2), step: 0.1, value: ((Math.min(v.end, len) - v.frame) / fps).toFixed(2), disabled: toEnd });
      const out = h('output', {}, toEnd ? 'until the loop ends' : ((v.end - v.frame) / fps).toFixed(1) + ' s');
      dur.addEventListener('input', () => { v.end = Math.min(len, v.frame + Math.round(+dur.value * fps)); out.textContent = ((v.end - v.frame) / fps).toFixed(1) + ' s'; });
      const loopEnd = h('input', { type: 'checkbox', checked: toEnd });
      loopEnd.addEventListener('change', () => { v.end = loopEnd.checked ? len : Math.min(len, v.frame + fps); draw(); });
      when.append(h('div', { class: 'slider moment-dur' }, h('label', {}, 'Lasts'), out, dur),
        h('label', { class: 'check' }, loopEnd, 'Until the loop ends'));
    }
    body.append(when);
    if (v.type !== 'NOTE') {
      const skip = h('input', { type: 'checkbox', checked: v.skipWithCondom === null ? skipDefault() : v.skipWithCondom });
      skip.addEventListener('change', () => { v.skipWithCondom = skip.checked; });
      body.append(h('label', { class: 'check' }, skip, `Skip when ${s ? s.label : 'this sim'} wears a condom`,
        h('span', { class: 'muted small' }, ' (WickedWhims checks it in the game)')));
    }
    body.querySelectorAll('input[type=range]').forEach(fillRange);
    animate();
  };
  // the effect tiles arrive after the dialog opens (the list comes from the server): the loop runs while it is open
  const reduced = () => (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) || document.documentElement.classList.contains('reduce-motion');
  const animate = () => {
    cancelAnimationFrame(anim);
    // reduced motion: the tiles show one still picture of the effect (drawn when they are made)
    if (reduced()) return;
    let last = 0;
    const loop = now => {
      if (!body.isConnected) return;
      anim = requestAnimationFrame(loop);
      if (now - last < 40) return;                 // about 25 pictures a second is plenty for a tile
      last = now;
      for (const c of previews) if (c.isConnected && c._visible !== false && !document.hidden) drawPreview(c, c._kind, c._name, now / 1000);
    };
    anim = requestAnimationFrame(loop);
  };
  const save = () => {
    if (v.type === 'EFFECT' && (!v.effect || !v.joint)) { toast(!v.joint ? 'Pick a body part first.' : 'Pick an effect first.', 'err'); return false; }
    if (v.type !== 'NOTE' && !simById(app, v.sim)) { toast('Pick a sim first.', 'err'); return false; }
    const out = { type: v.type, frame: v.frame, sim: v.sim };
    if (v.type === 'CUM') Object.assign(out, { cum: v.cum, level: v.level });
    if (v.type === 'UNDRESS') out.naked = v.naked;
    if (v.type === 'EFFECT') Object.assign(out, { effect: v.effect, joint: v.joint, end: v.end });
    if (v.type === 'NOTE') out.text = v.text.trim();
    out.skipWithCondom = v.type === 'NOTE' ? false : (v.skipWithCondom === null ? skipDefault() : !!v.skipWithCondom);
    if (editing) {
      app.store.checkpoint();
      const e = (p.events || []).find(x => x.id === ev.id);
      if (!e) return true;
      for (const k of ['cum', 'level', 'naked', 'effect', 'joint', 'end', 'text']) delete e[k];
      Object.assign(e, out);
      // a changed moment is yours now (a preset no longer replaces it)
      delete e.auto;
      cleanMoment(clampMoment(app, e));
      dressFirst(app, e);
      afterMoments(app);
      toast(momentLabel(e, app), 'ok');
    } else {
      const m = addMomentTo(app, out);
      app.selectedEvent = m.id;
      toast(`${momentLabel(m, app)} - on the Moments row.`, 'ok');
    }
    return true;
  };
  draw();
  dlg = modal({
    title: editing ? 'Change the moment' : 'Add a moment', wide: true,
    text: 'What WickedWhims does at this time in the loop: cum, undressing, a condom coming off, or an effect at a body part.',
    body,
    onClose: () => cancelAnimationFrame(anim),
    buttons: [
      ...(editing ? [{ label: 'Delete', kind: 'ghost danger-text', onClick: () => { app.removeMoment(ev.id, { group: false }); return true; } }] : []),
      { label: 'Cancel', kind: 'ghost' },
      { label: editing ? 'Save' : 'Add moment', kind: 'primary', onClick: save },
    ],
  });
  return dlg;
}

// ---------------------------------------------------------------- the effect picker (inside the moment dialog)
function effectPicker(app, v, s, previews, redraw) {
  const joints = jointsFor(app, s);
  if (v.joint && !joints.some(j => j.bone === v.joint)) v.joint = '';
  if (!v.joint) v.joint = (joints.find(j => j.id === 'penis_tip') || joints.find(j => j.id === 'mouth') || joints[0]).bone;
  const left = h('div', { class: 'fx-joints' }, h('div', { class: 'fx-col-title' }, 'Body part'),
    joints.map(j => h('button', { class: 'fx-joint' + (v.joint === j.bone ? ' on' : ''), type: 'button', title: j.bone,
      onclick: () => { v.joint = j.bone; redraw(); } }, j.label)));
  const search = h('input', { class: 'text', placeholder: 'Search every game effect (drool, splash, sweat, steam...)', value: v._q || '', spellcheck: 'false' });
  const list = h('div', { class: 'fx-list' }, h('div', { class: 'hint' }, 'Loading the effects...'));
  const seen = new IntersectionObserver(es => { for (const e of es) e.target._visible = e.isIntersecting; }, { root: list });
  const tile = x => {
    const kind = effectKind(x.name, x.group);
    const c = h('canvas', { width: 96, height: 64, class: 'fx-prev' });
    c._kind = kind; c._name = x.name;
    drawPreview(c, kind, x.name, 0.6);
    previews.add(c);
    seen.observe(c);
    const on = String(v.effect).toLowerCase() === String(x.name).toLowerCase();
    return h('button', { class: 'fx-tile' + (on ? ' on' : ''), type: 'button', title: x.name,
      onclick: e => {
        v.effect = x.name;
        list.querySelectorAll('.fx-tile.on').forEach(t => t.classList.remove('on'));
        e.currentTarget.classList.add('on');
        pickedLine.textContent = `${x.label || effectLabel(x.name)} · ${x.name}`;
      } },
    c, h('b', {}, x.label || effectLabel(x.name)),
    h('small', {}, x.uses ? `used in ${Number(x.uses).toLocaleString('en-US')} creator animations` : 'a game effect'));
  };
  const makeTile = x => tile(x);
  const pickedLine = h('div', { class: 'fx-picked' }, v.effect ? `${effectLabel(v.effect)} · ${v.effect}` : 'Pick an effect');
  const fill = (items, grouped) => {
    list.innerHTML = '';
    if (!items.length) { list.append(h('div', { class: 'empty' }, 'No game effect matches.')); return; }
    if (!grouped) { list.append(h('div', { class: 'fx-grid' }, items.map(x => makeTile(x)))); return; }
    for (const gname of EFFECT_GROUPS) {
      const g = items.filter(x => x.group === gname);
      if (!g.length) continue;
      list.append(h('div', { class: 'fx-group' }, gname), h('div', { class: 'fx-grid' }, g.map(x => makeTile(x))));
    }
    // the effect this moment has now is shown (scrolled to)
    const on = list.querySelector('.fx-tile.on');
    if (on) requestAnimationFrame(() => { list.scrollTop = Math.max(0, on.offsetTop - list.offsetTop - 28); });
  };
  const loadPopular = () => effectCatalog(v.joint).then(d => { if (!search.value.trim()) fill(d.popular || [], true); });
  let tmr = 0;
  search.addEventListener('input', () => {
    v._q = search.value;
    clearTimeout(tmr);
    tmr = setTimeout(() => {
      const q = search.value.trim();
      if (!q) return loadPopular();
      searchEffects(q).then(items => { if (search.value.trim() === q) fill(items, false); });
    }, 250);
  });
  if (search.value.trim()) searchEffects(search.value.trim()).then(items => fill(items, false)); else loadPopular();
  const right = h('div', { class: 'fx-effects' }, h('div', { class: 'fx-col-title' }, 'Effect',
    h('span', { class: 'muted small' }, ' · the ones creators use most at this part first')), search, list, pickedLine);
  return h('div', { class: 'fx-picker' }, left, right);
}
