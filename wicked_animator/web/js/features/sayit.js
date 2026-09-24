// "Say it, see it" (R3-5): type one sentence - "slow cowgirl on the sofa, she's teasing him, 5 seconds" - and Magic
// makes it. The words are read on this PC by web/js/sayit.js (no AI model, nothing leaves the PC); this plug-in is
// the window you type in, the chips that show what was understood (click one to change it), and what Magic's own
// options don't cover yet: speed and strength apart, faces over the loop, the voices, eye contact, trembling and a
// condom.
//
// With a Say it animation open, the window changes that one: "rougher", "longer", "add kissing", "on the bed
// instead". The sentence and what it made are kept in the animation (project.sayit), so this works after reopening.
// Entry points: a Home card, Ctrl+K "Say it", and a "Change it in words" button in the Motion step of a Say it
// animation.
import { h, icon, modal, toast, contextMenu, confirmBox, addIcon, section } from '../ui.js';
import * as S from '../sayit.js';
import { makeMagic, RECIPES } from '../magic.js';
import { newLayer, MOTIONS } from '../motion.js';
import { FACE_PRESETS } from '../face.js';
import { hideHome } from '../home.js';

const ICONS = {
  'say-it': '<path d="M4.5 5.5h15a1.5 1.5 0 0 1 1.5 1.5v8a1.5 1.5 0 0 1-1.5 1.5H10l-4.5 3.5V16.5h-1A1.5 1.5 0 0 1 3 15V7a1.5 1.5 0 0 1 1.5-1.5z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M7.5 9.5h9M7.5 12.5h6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
};
const part = s => (s.frame === 'ym' || s.frame === 'yf_futa' ? 'MALE' : 'FEMALE');
const RECEIVER_MALE = new Set(['bj', 'handjob', 'titjob']);
const clamp01 = x => Math.min(1, Math.max(0, x));

// What Magic can make here: the positions it has a ready pose for, and the places that are in the app.
export function envOf(app) {
  const have = new Set((app.posePresets || []).filter(x => !x.mine).map(x => x.id));
  const recipes = new Set(RECIPES.map(r => r.id));
  return {
    acts: Object.keys(S.ACTS).filter(a => recipes.has(a) && have.has(a)),
    places: (app.furniture || []).filter(f => S.PLACES[f.id]).map(f => ({ id: f.id, label: f.label, kind: f.kind })),
  };
}

// The Say it animation that is open (its sentence and spec), or null.
const openSayit = app => {
  const p = app.store && app.store.project;
  return p && p.sayit && p.sayit.spec && p.sims.length ? p.sayit : null;
};

// ---------------------------------------------------------------- after Magic: what its options don't cover
// Magic tunes the motions for one number (how hard and fast together); Say it knows speed and strength apart, the
// faces over the loop, the voices, eye contact, trembling and a condom. -> the project, changed
export function applyPlan(app, plan) {
  const p = app.store.project, sims = p.sims, L = Math.max(2, p.length);
  const k = plan.intensity;
  // 1. speed: strokes per loop; strength: how far and how hard (relative to what Magic made for `intensity`)
  for (const s of sims) {
    for (const l of s.layers || []) {
      if (['breathe', 'sway', 'look', 'tremble', 'idle'].includes(l.type)) continue;
      const P = l.params || {};
      if (P.strokes !== undefined) P.strokes = Math.max(1, Math.round(P.strokes * (0.6 + plan.speed * 1.1) / (0.6 + k * 1.1)));
      if (P.distance !== undefined && ['thrust', 'ride', 'bounce'].includes(l.type)) P.distance = Math.max(0.5, Math.round(P.distance * (0.75 + plan.force * 0.5) / (0.75 + k * 0.5) * 2) / 2);
      if (P.sharp !== undefined) P.sharp = Math.round(clamp01(P.sharp + (plan.force - k) * 0.6) * 100) / 100;
    }
  }
  // partners still share one rhythm (Magic's rule): the leading stroke's count and phase
  const lead = sims.flatMap(s => s.layers || []).find(l => ['thrust', 'ride', 'headbob', 'stroke'].includes(l.type));
  if (lead) for (const s of sims) for (const l of s.layers || []) if (l !== lead && l.params && l.params.strokes !== undefined && !['breathe', 'look', 'tremble', 'idle'].includes(l.type)) { l.params.strokes = lead.params.strokes; l.phase = lead.phase || 0; }
  // 2. faces over the loop: [[t 0..1, preset]] per part (a busy mouth keeps the act's own face)
  for (const s of sims) {
    const tl = plan.faces && plan.faces[part(s)];
    if (!Array.isArray(tl)) continue;
    for (const [t, preset] of tl) {
      const f = FACE_PRESETS[preset];
      if (!f) continue;
      const frame = Math.min(L - 1, Math.max(0, Math.round(t * L)));
      const key = app._faceKeyAt ? app._faceKeyAt(s, frame) : s.keys.find(x => x.frame === frame);
      if (key) key.face = { ...f.face };
    }
  }
  if (plan.eyesMix) {
    for (const s of sims) {
      const mix = plan.eyesMix[part(s)];
      if (!mix) continue;
      const faced = s.keys.filter(x => x.face);
      for (const key of faced.length ? faced : s.keys.filter(x => x.frame === 0)) key.face = { ...(key.face || {}), ...mix };
    }
  }
  // 3. sounds and voices
  if (!plan.sounds) for (const s of sims) s.sounds = [];
  else if (plan.voices === 'none') for (const s of sims) s.sounds = (s.sounds || []).filter(x => x.kind !== 'voice');
  else if (plan.voices && typeof plan.voices === 'object') {
    for (const s of sims) {
      if (!(part(s) in plan.voices)) continue;
      const v = plan.voices[part(s)];
      if (v === undefined) continue;
      if (!v) { s.sounds = (s.sounds || []).filter(x => x.kind !== 'voice'); continue; }
      if (typeof app.randomVoices === 'function') app.randomVoices(s.id, v.set, v.every, { quiet: true });
    }
  }
  // 4. eye contact, trembling
  const add = (s, type, params, weight = 1) => {
    if (!MOTIONS[type] || (s.layers || []).some(l => l.type === type)) return;
    const l = newLayer(type);
    Object.assign(l.params, params);
    l.weight = weight;
    (s.layers = s.layers || []).push(l);
  };
  const recipe = plan.recipe;
  if (plan.eyeContact) for (const s of sims) add(s, 'look', { target: 'face', who: 'auto' }, 0.6);
  if (plan.tremble) {
    const want = RECEIVER_MALE.has(recipe) ? 'MALE' : 'FEMALE';
    const r = sims.find(s => part(s) === want) || sims[0];
    if (r) add(r, 'tremble', { amount: 2, parts: 'legs', start: 0.6, end: 1 });
  }
  // 5. a condom: the giver wears one in the preview, and cum moments are left out while it is on
  if (plan.condom) {
    const giver = sims.find(s => part(s) === 'MALE');
    if (giver) {
      giver.previewCondom = true;
      for (const e of p.events || []) if (e.type === 'CUM') e.skipWithCondom = true;
    }
  }
  return p;
}

// Make (or remake) the scene for a spec. -> true when made
export async function makeFromSpec(app, spec, { text = '', before = null, ask = true } = {}) {
  const env = envOf(app);
  if (!env.acts.length) { toast('The positions are still loading - try again in a moment.'); return false; }
  const plan = S.toMagic(spec, env);
  // a Say it change remakes the animation that is open; anything else is new work, never replaced without asking
  const sameScene = before && openSayit(app);
  // (a change to a Say it animation nobody touched since is simply made again)
  const untouched = sameScene && app._sayitRev !== undefined && app._sayitRev === app.editRev && app._sayitUid === app.store.project.uid;
  if (ask && app.store.dirty && !untouched
    && !(await confirmBox('Make a new animation?', `Unsaved changes to "${app.store.project.name}" will be lost. Save first (Ctrl+S) to keep them.`, 'Make it', true))) return false;
  const keepName = sameScene ? app.store.project.name : null;
  const keepUid = sameScene ? app.store.project.uid : null;
  const ok = await makeMagic(app, { recipe: plan.recipe, place: plan.place, intensity: plan.intensity, seconds: plan.seconds,
    bodies: plan.bodies, name: keepName || plan.name, finish: plan.finish });
  if (!ok) return false;
  applyPlan(app, plan);
  const p = app.store.project;
  // a change keeps its animation's name and id (it is the same animation, made again)
  if (keepUid) p.uid = keepUid;
  p.sayit = { text: String(text || '').slice(0, 300), spec: JSON.parse(JSON.stringify(spec)) };
  app.store.setDirty(true);
  try { app.layersChanged(true); } catch (err) { console.error('Say it:', err); }
  app.refreshAll();
  app.pipeline.simulateIfNeeded(true);
  app._sayitRev = app.editRev;
  app._sayitUid = p.uid;
  const changed = before ? S.describeChanges(before, spec, env) : '';
  const chips = S.chipsFor(spec, env).filter(c => !c.auto && c.slot !== 'note').map(c => c.text).join(' · ');
  toast(changed ? `${changed} - made again.` : `${plan.name}${chips ? ': ' + chips : ''}. Tune anything, or say what to change.`, 'ok');
  app.emit && app.emit('sayit', { spec, plan, text });
  return true;
}

// ---------------------------------------------------------------- the window
export function openSayIt(app, { text: startText = '' } = {}) {
  const cur = openSayit(app);
  const current = cur ? cur.spec : null;
  let edits = [];                          // chip changes: [[slot, value]], applied after the words
  let res = null, spec = null;
  const env = envOf(app);
  const input = h('input', { class: 'sayit-input', type: 'text', spellcheck: 'false', autocomplete: 'off', maxlength: '300', value: startText,
    'aria-label': 'What should happen',
    placeholder: current ? 'Say what to change: rougher, longer, add kissing, on the bed instead...' : 'e.g. slow cowgirl on the sofa, she\'s teasing him, 5 seconds' });
  const chips = h('div', { class: 'chips sayit-chips', 'aria-live': 'polite' });
  const notes = h('div', { class: 'sayit-notes' });
  const ideas = h('div', { class: 'sayit-ideas' });
  const refusal = h('div', { class: 'sayit-refused hidden', role: 'alert' });

  const suggest = (label, list) => {
    ideas.innerHTML = '';
    ideas.append(h('span', { class: 'sayit-ideas-h' }, label), ...list.map(t => h('button', { class: 'chipbtn', type: 'button',
      onclick: () => { input.value = t; update(); input.focus(); } }, t)));
  };

  function update() {
    const text = input.value;
    res = S.parse(text, { current });
    refusal.classList.toggle('hidden', !res.refused);
    refusal.textContent = res.refused ? res.message : '';
    chips.innerHTML = ''; notes.innerHTML = '';
    if (res.refused) { spec = null; setButton(); return; }
    spec = res.spec;
    for (const [slot, value] of edits) spec = S.setField(spec, slot, value);
    for (const c of S.chipsFor(spec, env)) chips.append(chipEl(c));
    const lines = [];
    if (res.fixes.length) lines.push({ text: 'Read ' + res.fixes.map(([a, b]) => `"${a}" as "${b}"`).join(', ') });
    for (const n of res.notes) lines.push(n);
    if (res.unknown.length) lines.push({ text: `Not understood: ${res.unknown.slice(0, 8).join(', ')}` });
    if (res.surprise) lines.push({ text: 'A surprise: the position and the place are picked for you' });
    if (current && !res.empty && !res.fresh) {
      const d = S.describeChanges(current, spec, env);
      if (d) lines.push({ text: `Changes the open animation: ${d.toLowerCase()}` });
    } else if (current && res.fresh && !res.empty) lines.push({ text: 'Makes a new animation' });
    for (const n of lines) notes.append(h('div', { class: 'sayit-note' + (n.warn ? ' warn' : '') }, icon(n.warn ? 'x' : 'spark'), h('span', {}, n.text)));
    if (!text.trim()) suggest(current ? 'Change it:' : 'Try:', current ? S.FOLLOW_UPS : S.EXAMPLES);
    else ideas.innerHTML = '';
    setButton();
  }

  // a chip: its value, picked for you (faint) or said; click to pick another; x to take it away
  function chipEl(c) {
    if (c.slot === 'note') return h('span', { class: 'sayit-chip warn' }, icon('x'), c.text);
    const el = h('button', { class: 'sayit-chip' + (c.auto ? ' auto' : '') + (c.warn ? ' warn' : ''), type: 'button', 'data-slot': c.slot,
      title: c.auto ? 'Picked for you - click to choose' : 'Click to change' },
    c.label ? h('small', {}, c.label) : null, h('b', {}, c.text));
    const choices = S.choicesFor(c.slot, env);
    el.onclick = e => {
      const r = el.getBoundingClientRect();
      const items = choices.map(x => ({ label: x.label, onClick: () => { edits.push([c.slot, x.value]); update(); } }));
      if (c.remove) items.push('-', { label: 'Take it away', icon: 'x', onClick: () => { edits.push([c.slot, null]); update(); } });
      if (items.length) contextMenu(r.left, r.bottom + 4, items);
      e.stopPropagation();
    };
    return el;
  }

  const dlg = modal({
    title: 'Say it, see it', wide: true,
    text: current ? `Say what to change in "${app.store.project.name}" - or describe a new one.`
      : 'Say what should happen - who, where, how, how long. It is made for you on this PC, ready to tune and send to the game.',
    body: h('div', { class: 'sayit' },
      h('div', { class: 'search sayit-box' }, icon('say-it'), input),
      refusal, chips, notes, ideas,
      h('div', { class: 'hint sayit-adults' }, 'Adults only: two grown-up sims who both want it. Click a chip to change it.')),
    buttons: [
      { label: 'Cancel', kind: 'ghost' },
      { label: current ? 'Change it' : 'Make it', kind: 'primary', onClick: () => go() },
    ],
  });
  dlg.dialog.classList.add('sayit-modal');
  const mainBtn = dlg.footer.querySelector('.btn.primary');
  function setButton() {
    const change = current && res && !res.fresh && !res.refused;
    mainBtn.textContent = change ? 'Change it' : 'Make it';
    mainBtn.disabled = !!(res && res.refused);
  }
  input.addEventListener('input', () => { edits = edits.filter(([slot]) => slot.startsWith('extra:') || slot === 'build'); update(); });
  input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); if (!mainBtn.disabled) mainBtn.click(); } });

  async function go() {
    update();
    if (!res || res.refused) return false;
    if (res.empty && !res.surprise && !edits.length && !current) { toast('Type what should happen - or pick one of the ideas.'); return false; }
    let s = spec;
    if (res.surprise) {
      const pick = a => a[Math.floor(Math.random() * a.length)];
      const places = env.places.filter(p => ['floor', 'double_bed', 'single_bed', 'sofa'].includes(p.id)).map(p => p.id);
      if (!edits.some(([k]) => k === 'act')) s = S.setField(s, 'act', pick(env.acts));
      if (!edits.some(([k]) => k === 'place') && places.length) s = S.setField(s, 'place', pick(places));
    }
    const ok = await makeFromSpec(app, s, { text: input.value, before: res.fresh ? null : current });
    if (ok) hideHome(app);
    return ok ? undefined : false;
  }

  update();
  setTimeout(() => { input.focus(); input.setSelectionRange(input.value.length, input.value.length); }, 40);
  return dlg;
}

// ---------------------------------------------------------------- plug in
export function install(app) {
  if (!app || app.__sayit) return;
  app.__sayit = true;
  for (const [id, svg] of Object.entries(ICONS)) addIcon(id, svg);
  const hooks = app.hooks || {};
  const add = (name, fn) => { const list = name.split('.').reduce((o, k) => o && o[k], hooks); if (Array.isArray(list)) list.push(fn); };

  add('homeCards', a => [{ id: 'sayit', icon: 'say-it', title: 'Say it, see it',
    text: '"Slow cowgirl on the sofa, 5 seconds" - type it and it is made for you.', onClick: () => openSayIt(a) }]);
  add('commands', a => [
    { group: 'Actions', id: 'sayit', label: openSayit(a) ? 'Say it: change this animation' : 'Say it, see it', icon: 'say-it',
      sub: openSayit(a) ? '"rougher", "longer", "add kissing", "on the bed instead"' : 'type a sentence, get the animation',
      words: 'say it type text sentence describe words prompt write magic make generate', run: () => openSayIt(a) },
  ]);
  add('helpRows', () => [{ group: 'Making animations', keys: ['Ctrl', 'K'], text: 'Type "Say it" - then describe the animation in your own words' }]);
  // a Say it animation: change it in words from the Motion step
  add('sections.motion', (a, root) => {
    const cur = openSayit(a);
    if (!cur) return;
    root.append(section('Made from your words',
      cur.text ? h('div', { class: 'hint sayit-said' }, `"${cur.text}"`) : null,
      h('button', { class: 'btn block soft', type: 'button', onclick: () => openSayIt(a) }, icon('say-it'), 'Change it in words'),
      h('div', { class: 'hint' }, 'Say "rougher", "longer", "add kissing" or "on the bed instead" - it is made again with that change.')));
  });
  window.wickedSayIt = { open: opts => openSayIt(app, opts), make: (text, opts) => { const r = S.parse(text, { current: opts && opts.change && openSayit(app) ? openSayit(app).spec : null }); return r.refused ? Promise.resolve(false) : makeFromSpec(app, r.spec, { text, ask: false, before: r.fresh ? null : openSayit(app)?.spec }); } };
}

export default install;
