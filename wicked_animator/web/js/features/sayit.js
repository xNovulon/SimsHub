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
import { $t, inSentence, getLanguage } from '../i18n.js';

const ICONS = {
  'say-it': '<path d="M4.5 5.5h15a1.5 1.5 0 0 1 1.5 1.5v8a1.5 1.5 0 0 1-1.5 1.5H10l-4.5 3.5V16.5h-1A1.5 1.5 0 0 1 3 15V7a1.5 1.5 0 0 1 1.5-1.5z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M7.5 9.5h9M7.5 12.5h6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
};
const part = s => (s.frame === 'ym' || s.frame === 'yf_futa' ? 'MALE' : 'FEMALE');
const RECEIVER_MALE = new Set(['bj', 'handjob', 'titjob']);
const clamp01 = x => Math.min(1, Math.max(0, x));

// ---------------------------------------------------------------- what was understood, in the app's language
// The sentence itself is read in English (web/js/sayit.js keeps its English words); the chips, notes and choices
// are shown in the app's language.
const sayAct = id => (S.ACTS[id] ? $t('features.sayit.act_' + id) : String(id || ''));
const sayPlace = (id, env) => { const p = ((env && env.places) || []).find(x => x.id === id); return p ? p.label : S.PLACES[id] ? $t('features.sayit.place_' + id) : String(id || '').replace(/_/g, ' '); };
const sayPair = id => (S.PAIRS[id] ? $t('features.sayit.pair_' + id) : String(id || ''));
const sayMood = id => (S.MOODS[id] ? $t('features.sayit.mood_' + id) : String(id || ''));
const sayFinish = id => (S.FINISHES[id] ? $t('features.sayit.finish_' + id) : String(id || ''));
const sayExtra = id => (S.EXTRAS[id] ? $t('features.sayit.extra_' + id) : String(id || ''));
const SPEEDS = [[0.12, 'very_slow'], [0.35, 'slow'], [0.65, 'steady'], [0.9, 'fast'], [Infinity, 'very_fast']];
const FORCES = [[0.3, 'gentle'], [0.7, 'firm'], [Infinity, 'hard']];
const saySpeed = v => $t('features.sayit.speed_' + SPEEDS.find(([m]) => v <= m)[1]);
const sayForce = v => $t('features.sayit.force_' + FORCES.find(([m]) => v <= m)[1]);
// an English name from sayit.js (a position, place, mood...) -> the app's language
function sayName(en, env) {
  const low = String(en || '').toLowerCase();
  for (const [id, a] of Object.entries(S.ACTS)) if (a.label.toLowerCase() === low) return sayAct(id);
  for (const [id, l] of Object.entries(S.PLACES)) if (l.toLowerCase() === low) return sayPlace(id, env);
  for (const [id, m] of Object.entries(S.MOODS)) if (m.label.toLowerCase() === low) return sayMood(id);
  return en;
}
// the notes sayit.js writes (English) -> the app's language
function sayNote(text, env) {
  const t = String(text || '');
  let m;
  if ((m = /^(.+) is not there - used the (.+)$/.exec(t))) return $t('features.sayit.note_place_missing', { place: sayName(m[1], env), used: inSentence(sayName(m[2], env)) });
  if ((m = /^(.+) is not in your library - made another position$/.exec(t))) return $t('features.sayit.note_act_missing', { act: sayName(m[1], env) });
  if ((m = /^Left out: not the (.+)$/.exec(t))) return $t('features.sayit.note_left_out', { what: inSentence(sayName(m[1], env)) });
  if ((m = /^Left out: not (.+)$/.exec(t))) return $t('features.sayit.note_left_out', { what: inSentence(sayName(m[1], env)) });
  if ((m = /^No (.+) to put them in yet - pick another place$/.exec(t))) return $t('features.sayit.note_no_place', { what: m[1] });
  const fixed = { 'Say it makes scenes for two sims': 'features.sayit.note_two_sims', 'Dances are not part of Say it': 'features.sayit.note_no_dances',
    'Toys are not part of Say it yet': 'features.sayit.note_no_toys' };
  return fixed[t] ? $t(fixed[t]) : t;
}
// S.chipsFor, with every label and value in the app's language
function chipsUI(spec, env) {
  const r = S.resolve(spec, env);
  return S.chipsFor(spec, env).map(c => {
    const k = c.slot;
    const label = c.label ? $t('features.sayit.slot_' + k) : '';
    let text = c.text;
    if (k === 'act') text = r.reverse ? $t('features.sayit.act_reverse', { act: sayAct(r.act) }) : sayAct(r.act);
    else if (k === 'place') text = sayPlace(r.place, env);
    else if (k === 'pair') text = sayPair(r.pair);
    else if (k === 'mood') text = S.MOODS[r.mood] && S.MOODS[r.mood].teaser ? $t(r.moodBy === 'MALE' ? 'features.sayit.mood_by_him' : 'features.sayit.mood_by_her', { mood: sayMood(r.mood) }) : sayMood(r.mood);
    else if (k === 'speed') text = saySpeed(r.speed);
    else if (k === 'force') text = sayForce(r.force);
    else if (k === 'seconds') text = $t('features.sayit.seconds', { n: r.seconds });
    else if (k === 'finish') text = sayFinish(r.finishPart);
    else if (k === 'build') text = $t('features.sayit.build');
    else if (k.startsWith('extra:')) text = c.warn ? $t('features.sayit.extra_too_far', { extra: sayExtra(k.slice(6)), act: inSentence(sayAct(r.act)) }) : sayExtra(k.slice(6));
    else if (k === 'note') text = sayNote(c.text, env);
    return { ...c, label, text };
  });
}
// S.choicesFor, in the app's language
function choicesUI(slot, env) {
  return S.choicesFor(slot, env).map(x => {
    let label = x.label;
    if (slot === 'act') label = sayAct(x.value);
    else if (slot === 'place') label = sayPlace(x.value, env);
    else if (slot === 'pair') label = sayPair(x.value);
    else if (slot === 'mood') label = x.value ? sayMood(x.value) : $t('features.sayit.no_mood');
    else if (slot === 'speed') label = saySpeed(x.value);
    else if (slot === 'force') label = sayForce(x.value);
    else if (slot === 'seconds') label = $t('features.sayit.seconds', { n: x.value });
    else if (slot === 'finish') label = sayFinish(x.value);
    return { ...x, label };
  });
}
// S.describeChanges ("rougher and longer"), in the app's language
function changesUI(before, after, env) {
  if (!before) return '';
  const a = S.resolve(before, env), b = S.resolve(after, env), out = [];
  if (a.act !== b.act) out.push(inSentence(sayAct(b.act)));
  if (a.place !== b.place) out.push($t('features.sayit.change_place', { place: inSentence(sayPlace(b.place, env)) }));
  if (a.pair !== b.pair) out.push(inSentence(sayPair(b.pair)));
  if (a.mood !== b.mood) out.push(b.mood ? inSentence(sayMood(b.mood)) : $t('features.sayit.change_no_mood'));
  if (Math.abs(a.force - b.force) > 0.01) out.push(b.force > a.force ? $t('features.sayit.change_harder') : $t('features.sayit.change_gentler'));
  if (Math.abs(a.speed - b.speed) > 0.01) out.push(b.speed > a.speed ? $t('features.sayit.change_faster') : $t('features.sayit.change_slower'));
  if (a.seconds !== b.seconds) out.push($t('features.sayit.change_loop', { n: b.seconds }));
  if (a.finishPart !== b.finishPart) out.push(b.finishPart === 'none' ? $t('features.sayit.change_no_finish') : $t('features.sayit.change_finish', { finish: inSentence(sayFinish(b.finishPart)) }));
  if (a.build !== b.build) out.push(b.build ? $t('features.sayit.change_edge') : $t('features.sayit.change_not_edge'));
  for (const k of new Set([...Object.keys(a.extras || {}), ...Object.keys(b.extras || {})])) {
    if (!!a.extras[k] !== !!b.extras[k] && S.EXTRAS[k]) out.push((b.extras[k] ? '+ ' : '- ') + inSentence(sayExtra(k)));
  }
  return out.join(', ');
}

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
  if (!env.acts.length) { toast($t('features.sayit.positions_are_still_loading_try')); return false; }
  const plan = S.toMagic(spec, env);
  // a Say it change remakes the animation that is open; anything else is new work, never replaced without asking
  const sameScene = before && openSayit(app);
  // (a change to a Say it animation nobody touched since is simply made again)
  const untouched = sameScene && app._sayitRev !== undefined && app._sayitRev === app.editRev && app._sayitUid === app.store.project.uid;
  if (ask && app.store.dirty && !untouched
    && !(await confirmBox($t('features.sayit.make_new_animation'), $t('features.sayit.unsaved_changes_to_will_be', { projectName: app.store.project.name }), $t('features.sayit.make_it'), true))) return false;
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
  toast(changed ? $t('features.sayit.made_again', { changed }) : $t('features.sayit.tune_anything_or_say_what', { planName: plan.name, v: chips ? ': ' + chips : '' }), 'ok');
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
    'aria-label': $t('features.sayit.what_should_happen'),
    placeholder: current ? $t('features.sayit.say_what_to_change_rougher') : $t('features.sayit.e_g_slow_cowgirl_on') });
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
    refusal.textContent = res.refused ? (S.REFUSALS[res.refused] ? $t('features.sayit.refuse_' + res.refused) : res.message) : '';
    chips.innerHTML = ''; notes.innerHTML = '';
    if (res.refused) { spec = null; setButton(); return; }
    spec = res.spec;
    for (const [slot, value] of edits) spec = S.setField(spec, slot, value);
    for (const c of chipsUI(spec, env)) chips.append(chipEl(c));
    const lines = [];
    if (res.fixes.length) lines.push({ text: $t('features.sayit.read_as', { fixes: res.fixes.map(([a, b]) => $t('features.sayit.read_pair', { a, b })).join(', ') }) });
    for (const n of res.notes) lines.push({ ...n, text: sayNote(n.text, env) });
    if (res.unknown.length) lines.push({ text: $t('features.sayit.not_understood', { unknown: res.unknown.slice(0, 8).join(', ') }) });
    if (res.surprise) lines.push({ text: $t('features.sayit.surprise_position_and_place_are') });
    if (current && !res.empty && !res.fresh) {
      const d = changesUI(current, spec, env);
      if (d) lines.push({ text: $t('features.sayit.changes_open_animation', { d }) });
    } else if (current && res.fresh && !res.empty) lines.push({ text: $t('features.sayit.makes_new_animation') });
    for (const n of lines) notes.append(h('div', { class: 'sayit-note' + (n.warn ? ' warn' : '') }, icon(n.warn ? 'x' : 'spark'), h('span', {}, n.text)));
    if (!text.trim()) suggest(current ? $t('features.sayit.change_it') : $t('features.sayit.try'), current ? S.FOLLOW_UPS : S.EXAMPLES);
    else ideas.innerHTML = '';
    setButton();
  }

  // a chip: its value, picked for you (faint) or said; click to pick another; x to take it away
  function chipEl(c) {
    if (c.slot === 'note') return h('span', { class: 'sayit-chip warn' }, icon('x'), c.text);
    const el = h('button', { class: 'sayit-chip' + (c.auto ? ' auto' : '') + (c.warn ? ' warn' : ''), type: 'button', 'data-slot': c.slot,
      title: c.auto ? $t('features.sayit.picked_for_you_click_to') : $t('features.sayit.click_to_change') },
    c.label ? h('small', {}, c.label) : null, h('b', {}, c.text));
    const choices = choicesUI(c.slot, env);
    el.onclick = e => {
      const r = el.getBoundingClientRect();
      const items = choices.map(x => ({ label: x.label, onClick: () => { edits.push([c.slot, x.value]); update(); } }));
      if (c.remove) items.push('-', { label: $t('features.sayit.take_it_away'), icon: 'x', onClick: () => { edits.push([c.slot, null]); update(); } });
      if (items.length) contextMenu(r.left, r.bottom + 4, items);
      e.stopPropagation();
    };
    return el;
  }

  const dlg = modal({
    title: $t('features.sayit.say_it_see_it'), wide: true,
    text: current ? $t('features.sayit.say_what_to_change_in', { projectName: app.store.project.name })
      : $t('features.sayit.say_what_should_happen_who'),
    body: h('div', { class: 'sayit' },
      h('div', { class: 'search sayit-box' }, icon('say-it'), input),
      getLanguage() !== 'en' ? h('div', { class: 'hint sayit-english' }, $t('features.sayit.english_only')) : null,
      refusal, chips, notes, ideas,
      h('div', { class: 'hint sayit-adults' }, $t('features.sayit.adults_only_two_grown_up'))),
    buttons: [
      { label: $t('features.sayit.cancel'), kind: 'ghost' },
      { label: current ? $t('features.sayit.change_it_2') : $t('features.sayit.make_it'), kind: 'primary', onClick: () => go() },
    ],
  });
  dlg.dialog.classList.add('sayit-modal');
  const mainBtn = dlg.footer.querySelector('.btn.primary');
  function setButton() {
    const change = current && res && !res.fresh && !res.refused;
    mainBtn.textContent = change ? $t('features.sayit.change_it_2') : $t('features.sayit.make_it');
    mainBtn.disabled = !!(res && res.refused);
  }
  input.addEventListener('input', () => { edits = edits.filter(([slot]) => slot.startsWith('extra:') || slot === 'build'); update(); });
  input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); if (!mainBtn.disabled) mainBtn.click(); } });

  async function go() {
    update();
    if (!res || res.refused) return false;
    if (res.empty && !res.surprise && !edits.length && !current) { toast($t('features.sayit.type_what_should_happen_or')); return false; }
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

  add('homeCards', a => [{ id: 'sayit', icon: 'say-it', title: $t('features.sayit.say_it_see_it'),
    text: $t('features.sayit.slow_cowgirl_on_sofa_5'), onClick: () => openSayIt(a) }]);
  add('commands', a => [
    { group: $t('features.sayit.actions'), id: 'sayit', label: openSayit(a) ? $t('features.sayit.say_it_change_this_animation') : $t('features.sayit.say_it_see_it'), icon: 'say-it',
      sub: openSayit(a) ? $t('features.sayit.rougher_longer_add_kissing_on') : $t('features.sayit.type_sentence_get_animation'),
      words: 'say it type text sentence describe words prompt write magic make generate', run: () => openSayIt(a) },
  ]);
  add('helpRows', () => [{ group: $t('features.sayit.making_animations'), keys: ['Ctrl', 'K'], text: $t('features.sayit.type_say_it_then_describe') }]);
  // a Say it animation: change it in words from the Motion step
  add('sections.motion', (a, root) => {
    const cur = openSayit(a);
    if (!cur) return;
    root.append(section($t('features.sayit.made_from_your_words'),
      cur.text ? h('div', { class: 'hint sayit-said' }, `"${cur.text}"`) : null,
      h('button', { class: 'btn block soft', type: 'button', onclick: () => openSayIt(a) }, icon('say-it'), $t('features.sayit.change_it_in_words')),
      h('div', { class: 'hint' }, $t('features.sayit.say_rougher_longer_add_kissing'))));
  });
  window.wickedSayIt = { open: opts => openSayIt(app, opts), make: (text, opts) => { const r = S.parse(text, { current: opts && opts.change && openSayit(app) ? openSayit(app).spec : null }); return r.refused ? Promise.resolve(false) : makeFromSpec(app, r.spec, { text, ask: false, before: r.fresh ? null : openSayit(app)?.spec }); } };
}

export default install;
