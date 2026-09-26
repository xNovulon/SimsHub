// The game's own features (R2-4, spec_game 2-5): each sim's game voice, the Moments row (cum, undress, condom,
// effects, notes), stand-in effect particles and WickedWhims' cum on the skin. Everything plugs in through
// app.hooks (plan 2.4) and timeline.addRow (2.5), so main.js, timeline.js and index.html stay as they are.
import { h, toast, addIcon, addToolbarButton, contextMenu } from '../ui.js';
import { localStorageGet, localStorageSet, uid } from '../state.js';
import { simVoice, voiceFor, voiceCode, isVoiceLine, soundFitsSim, VOICE_SETS, tagsOf, SAMPLE_LINE, ADULT_CODES, voiceLabel } from '../audio.js';
import * as M from '../moments.js';
import { EffectLayer, effectKind } from '../effects.js';
import * as Cum from '../cumskin.js';

// ---------------------------------------------------------------- icons (24x24, stroked like the app's own)
const ICONS = {
  drop: '<path d="M12 3.5c3 4.2 5.5 7.4 5.5 10.4a5.5 5.5 0 0 1-11 0c0-3 2.5-6.2 5.5-10.4z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M9.6 14.6a2.6 2.6 0 0 0 2.2 2.3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
  shirt: '<path d="M8.5 4 4 6.5 5.8 10l2.2-1v11h8V9l2.2 1L20 6.5 15.5 4c-.6 1.4-1.9 2.2-3.5 2.2S9.1 5.4 8.5 4z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
  ring: '<circle cx="12" cy="12" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".6"/>',
  fx: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="12" r="2" fill="currentColor"/>',
  wave: '<path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 11v2M21 12h0" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  flag: '<path d="M6 21V4M6 4h11l-2.5 4L17 12H6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>',
};

const clone = x => JSON.parse(JSON.stringify(x));
const ROW_H = 22;

export function install(app) {
  if (!app || app.__game) return;
  app.__game = true;
  for (const [id, svg] of Object.entries(ICONS)) addIcon(id, svg);
  const hooks = app.hooks || {};
  const add = (name, fn) => { const list = name.split('.').reduce((o, k) => o && o[k], hooks); if (Array.isArray(list)) list.push(fn); };
  // new app methods only (never replacing one that exists; app.voicePool is the one the plan lets this replace)
  const mix = (name, fn) => { if (typeof app[name] !== 'function') app[name] = fn; };

  app.selectedEvent = null;
  app.loopPass = 0;
  app.showEffects = localStorageGet('showEffects', true);
  app.showCum = localStorageGet('showCum', true);
  app.voiceLines = app.voiceLines || null;
  app.voiceSec = app.voiceSec || new Map();
  if (app.audio) app.audio.voiceAware = true;

  // ---------------------------------------------------------------- data from the server
  app.voicesReady = fetch('/api/voices').then(r => (r.ok ? r.json() : null)).catch(() => null).then(v => {
    if (!v || !Array.isArray(v.lines)) { app.voiceLines = app.voiceLines || []; return app.voiceLines; }
    app.voiceLines = v.lines;
    app.voiceSec = new Map(v.lines.filter(x => x.sec).map(x => [x.name, x.sec]));
    if (app.step === 'sounds' && typeof app.renderStep === 'function') app.renderStep();
    return app.voiceLines;
  });
  M.effectCatalog('').catch(() => {});
  Cum.load().then(() => Cum.preload(app.store.project)).catch(() => {});

  // ---------------------------------------------------------------- voices
  // The voice lines a sim can use for a kind: the game's lines in its voice, plus creator voice sounds that fit it.
  // Real lines first (not EA's rare "lowprob" takes), then the ones for its body's gender, then the ones creators
  // use most.
  app.voicePool = (sim, set) => voicePool(app, sim, set);
  mix('setVoice', (simId, code) => {
    const s = app.store.sim(simId);
    if (!s || ![...ADULT_CODES.female, ...ADULT_CODES.male].includes(code)) return;
    if (s.voice !== code) {
      app.store.checkpoint();
      s.voice = code;
      app.store.setDirty(true);
    }
    app.audio.ensure();
    app.audio.play(SAMPLE_LINE, { force: true, voice: code, detune: (s.voicePitch || 0) * 300 })
      .then(ok => ok || toast('This voice could not be played here.'));
    if (typeof app.refreshPanels === 'function') app.refreshPanels();
  });
  // how a sound plays: voice lines in the sim's own voice, at its own pitch
  add('soundOpts', (s, snd) => {
    if (!isVoiceLine(snd.name)) return null;
    return { voice: voiceFor(snd.name, s), detune: (s.voicePitch || 0) * 300 };
  });

  // Tray sims come with their own voice (asked once per sim; the body is built elsewhere)
  const trayVoices = new Map();
  app.trayVoiceOf = s => { const x = s && s.tray && trayVoices.get(s.tray.id + '|' + s.tray.index); return x && !(x instanceof Promise) ? x : null; };
  const trayVoice = s => {
    if (!s || !s.tray) return;
    const key = s.tray.id + '|' + s.tray.index;
    if (!trayVoices.has(key)) {
      trayVoices.set(key, fetch(`/api/tray_voice?tray=${encodeURIComponent(s.tray.id)}&index=${encodeURIComponent(s.tray.index)}`)
        .then(r => (r.ok ? r.json() : null)).catch(() => null).then(r => { trayVoices.set(key, r || {}); return r; }));
    }
    const hit = trayVoices.get(key);
    Promise.resolve(hit).then(r => {
      if (!r || !r.voice) return;
      const live = app.store.project.sims.find(x => x.id === s.id);
      if (!live || live.voice) return;
      live.voice = r.voice;                  // part of adding / loading this sim (no undo step of its own)
      live.voicePitch = r.voicePitch || 0;
      if (app.step === 'sounds') app.renderStep();
    });
  };

  // the body changed from female to male (or back): a voice that matched the old body follows the new one
  const lastBody = new Map();
  const bodyGender = s => (s.frame === 'ym' ? 'm' : 'f');
  const followBodies = () => {
    for (const s of app.store.project.sims) {
      const was = lastBody.get(s.id), now = bodyGender(s);
      lastBody.set(s.id, now);
      if (was && was !== now && s.voice && s.voice[0] === was && !s.tray) { delete s.voice; delete s.voicePitch; }
    }
  };

  // ---------------------------------------------------------------- moments
  mix('addMoment', (ev, o) => M.addMomentTo(app, ev, o));
  mix('updateMoment', (id, patch, o) => M.updateMomentIn(app, id, patch, o));
  mix('removeMoment', (id, o) => M.removeMomentFrom(app, id, o));
  mix('momentMenu', (x, y, ev, frame) => contextMenu(x, y, M.momentMenuItems(app, ev, frame === undefined ? Math.round(app.store.frame) : frame)));
  mix('editMoment', (id, frame, opts) => M.openMomentDialog(app, id ? (app.store.project.events || []).find(e => e.id === id) || null : null, frame, opts || {}));
  mix('finishPreset', (part, frame, o) => M.finishPreset(app, part, frame, o));
  mix('momentsChanged', () => {
    Cum.preload(app.store.project);
    M.checkEffects((app.store.project.events || []).filter(e => e.type === 'EFFECT').map(e => e.effect)).then(() => app.timeline && app.timeline.draw());
    if (app.timeline) app.timeline.draw();
  });

  // the Moments row between the ruler and the lanes
  if (app.timeline && typeof app.timeline.addRow === 'function') app.timeline.addRow(momentsRow(app));
  // a click anywhere else on the timeline lets go of the moment (Delete then works on keys again)
  const tl = document.getElementById('timeline') || (app.timeline && app.timeline.canvas);
  if (tl) tl.addEventListener('pointerdown', e => {
    if (!app.selectedEvent || !app.timeline) return;
    const r = app.timeline.canvas.getBoundingClientRect();
    const hit = e.target === app.timeline.canvas ? app.timeline._hit(e.clientX - r.left, e.clientY - r.top) : null;
    if (!(hit && hit.extra && hit.extra.id === 'moments' && hit.item)) { app.selectedEvent = null; app.timeline.draw(); }
  }, true);

  // ---------------------------------------------------------------- effects in the viewport
  app.effects = new EffectLayer(app, { moments: (a, o) => playingEffects(app, o) });
  app.effects.setVisible(app.showEffects);
  const fxBtn = addToolbarButton({ cell: 'view', id: 'btn-fx', icon: 'fx', toggle: true, title: 'Show effects: stand-in drool, splashes and drips where your Effect moments are',
    onClick: (e, b) => setEffects(b.classList.contains('on')) });
  if (fxBtn) fxBtn.classList.toggle('on', app.showEffects);
  const cumBtn = addToolbarButton({ cell: 'view', id: 'btn-cum', icon: 'drop', toggle: true, title: "Show cum: WickedWhims' cum on the skin after a Cum moment",
    onClick: (e, b) => setCum(b.classList.contains('on')) });
  if (cumBtn) cumBtn.classList.toggle('on', app.showCum);
  function setEffects(on) {
    app.showEffects = !!on; localStorageSet('showEffects', app.showEffects);
    app.effects.setVisible(app.showEffects);
    document.getElementById('btn-fx')?.classList.toggle('on', app.showEffects);
    app.applyPoses(false);
    if (app.step === 'sounds') app.renderStep();
  }
  function setCum(on) {
    app.showCum = !!on; localStorageSet('showCum', app.showCum);
    document.getElementById('btn-cum')?.classList.toggle('on', app.showCum);
    app.applyPoses(false);
    if (app.step === 'sounds') app.renderStep();
  }
  app.setShowEffects = setEffects;
  app.setShowCum = setCum;

  // the joints' places are read again after edits (keys, motions, undo)
  let rev = null;
  const editRev = () => `${app.store.undo.length}|${app.store.redo.length}|${app.store.project.uid}|${app.store.project.length}`;
  if (app.store && typeof app.store.on === 'function') app.store.on(what => { if (what === 'project' || what === 'dirty') { const r = editRev(); if (r !== rev) { rev = r; app.effects.invalidate(); } } });
  app.on && app.on('keyed', () => app.effects.invalidate());
  app.on && app.on('undo', () => app.effects.invalidate());

  // ---------------------------------------------------------------- per frame
  let lastEditing = null;
  // the loop got longer or shorter: an effect that ran "to the end of the loop" still does, and none runs past it
  let lastLen = { uid: app.store.project.uid, len: app.store.project.length };
  const lengthChanged = () => {
    const p = app.store.project;
    if (lastLen.uid === p.uid && lastLen.len !== p.length && Array.isArray(p.events)) {
      for (const e of p.events) {
        if (e.type !== 'EFFECT' || e.end === undefined) continue;
        if (e.end >= lastLen.len && lastLen.len < p.length) e.end = p.length;
        if (e.end > p.length) e.end = p.length;
        if (e.end < e.frame) e.end = e.frame;
      }
      for (const e of p.events) if (e.frame > p.length - 1) e.frame = p.length - 1;
    }
    lastLen = { uid: p.uid, len: p.length };
  };
  add('afterApply', frame => {
    if (lastLen.len !== app.store.project.length || lastLen.uid !== app.store.project.uid) lengthChanged();
    // a sim was posed by hand: where its body parts are is read again once that ends
    const editing = app.pipeline ? app.pipeline.editing : null;
    if (editing !== lastEditing) { if (lastEditing) app.effects.invalidate(); lastEditing = editing; }
    app.effects.update(frame, !!app.playing);
    paintCum(app, frame);
  });
  add('tick', (dt, frame, { playing, wrapped }) => { if (playing && wrapped) app.loopPass = (app.loopPass || 0) + 1; });
  add('frameSet', () => { app.loopPass = 0; });
  add('playing', on => {
    app.loopPass = 0;
    if (!on) return;
    // voice lines in each sim's own voice (plain names were left out of main's preload)
    const items = [];
    for (const s of app.store.project.sims) for (const x of s.sounds || []) items.push({ name: x.name, voice: voiceFor(x.name, s) });
    app.audio.preload(items);
    if ((app.store.project.events || []).some(e => e.type === 'EFFECT')) app.effects.sampleNow();
  });

  // ---------------------------------------------------------------- project life
  add('projectLoaded', p => {
    lastLen = { uid: p.uid, len: p.length };
    app.selectedEvent = null;
    app.loopPass = 0;
    app.effects.invalidate();
    lastBody.clear();
    for (const s of p.sims) lastBody.set(s.id, bodyGender(s));
    if (Array.isArray(p.events)) {
      const ids = new Set(p.sims.map(s => s.id));
      p.events = p.events.filter(e => e && typeof e === 'object' && e.type && (e.type === 'NOTE' || ids.has(e.sim)));
      M.checkEffects(p.events.filter(e => e.type === 'EFFECT').map(e => e.effect)).then(() => app.timeline && app.timeline.draw());
    }
    Cum.load().then(() => Cum.preload(p));
    for (const s of p.sims) if (s.tray && !s.voice) trayVoice(s);
  });
  add('simRemoved', (id, p) => {
    if (!Array.isArray(p.events)) return;
    p.events = p.events.filter(e => e.sim !== id || e.type === 'NOTE');
    for (const e of p.events) if (e.sim === id) delete e.sim;
    if (app.selectedEvent && !p.events.some(e => e.id === app.selectedEvent)) app.selectedEvent = null;
    app.effects.invalidate();
  });
  add('viewCreated', (v, s) => { if (s && s.tray && !s.voice) trayVoice(s); });
  add('viewsSynced', () => followBodies());

  // ---------------------------------------------------------------- Send to game
  add('bake', (payload, p, { views } = {}) => bakeMoments(app, payload, p, views));
  add('exportChecks', p => exportChecks(app, p));
  // nothing moves: every sim has one pose and no motion - in the game it stands still in that pose
  add('exportChecks', p => {
    const moves = s => (s.keys || []).filter(k => !k.faceOnly).length > 1 || (s.layers || []).some(l => l && l.on !== false);
    if (!p.sims.length || p.sims.some(moves)) return [];
    return [{ level: 'warn', text: 'Nothing moves yet: each sim has one pose, so in the game they hold it. Add keys on the timeline (K) or a Motion.',
      fix: { label: 'Add a Motion', run: () => app.showStep('motion') } }];
  });

  // ---------------------------------------------------------------- keys, menus, palette, help
  add('keys', (e, info) => {
    if (!app.selectedEvent || info.ctrl || info.alt) return false;
    if ((info.key === 'Delete' || info.key === 'Backspace') && info.focus === 'timeline') {
      const ev = (app.store.project.events || []).find(x => x.id === app.selectedEvent);
      if (!ev) { app.selectedEvent = null; return false; }
      const label = M.momentLabel(ev, app);
      app.removeMoment(ev.id, { group: false });
      toast(`Deleted: ${label}`);
      return true;
    }
    if (info.key === 'Escape') { app.selectedEvent = null; app.timeline.draw(); }
    return false;
  });
  add('menus.lane', (items, ctx) => { if (ctx && ctx.sim) items.push({ label: 'Add a moment here…', icon: 'flag', onClick: () => app.editMoment(null, ctx.frame, { sim: ctx.sim.id, type: 'CUM' }) }); });
  add('menus.ruler', (items, ctx) => { items.push({ label: 'Add a moment here…', icon: 'flag', onClick: () => app.editMoment(null, ctx.frame) }); });
  add('commands', a => {
    const f = () => Math.round(a.store.frame);
    const has = () => a.store.project.sims.length > 0;
    return [
      { group: 'Moments', id: 'moment-add', label: 'Add a moment here', icon: 'flag', sub: 'cum, undress, condom off, an effect or a note', words: 'event cum undress condom effect note moments track', run: () => a.editMoment(null, f()), when: has },
      ...M.FINISH_PARTS.map(([part, label]) => ({ group: 'Moments', id: 'finish-' + part, label: `Finish: ${part === 'inside' ? 'inside' : 'cum on the ' + label.toLowerCase()}`, icon: 'drop', sub: 'cum, drool and the finish voices at the playhead', words: 'climax cum finish orgasm ' + label, run: () => a.finishPreset(part, f()), when: has })),
      { group: 'Moments', id: 'effect-add', label: 'Effect at a body part…', icon: 'fx', sub: 'drool, splash, drips, tears, steam', words: 'fluids vfx drool splash sweat squirt pee tears', run: () => a.editMoment(null, f(), { type: 'EFFECT' }), when: has },
      { group: 'Moments', id: 'make-climax', label: 'Make it a climax', icon: 'loop', sub: 'plays once, so cum shows once', words: 'climax once loops finish', run: () => M.makeClimax(a), when: () => a.store.project.category !== 'CLIMAX' },
      { group: 'View', id: 'toggle-fx', label: a.showEffects ? 'Hide effects' : 'Show effects', icon: 'fx', words: 'particles drool splash stand-in', run: () => setEffects(!a.showEffects) },
      { group: 'View', id: 'toggle-cum', label: a.showCum ? 'Hide cum' : 'Show cum', icon: 'drop', words: 'cum layers skin texture', run: () => setCum(!a.showCum) },
    ];
  });
  add('helpRows', () => [
    { group: 'Moments', keys: 'Right-click the Moments row', text: 'Cum, undress, a condom coming off, an effect or a note - at that time' },
    { group: 'Moments', keys: 'Double-click the Moments row', text: 'Add a moment there (or change the one you double-clicked)' },
    { group: 'Moments', keys: ['Delete'], text: 'Delete the moment you clicked on the timeline' },
  ]);

  // ---------------------------------------------------------------- creator moments come along with "Import as keys"
  let importToast = 0, importCount = 0;
  add('imported', m => {
    const pv = app.library && app.library.preview, anim = pv && pv.anim;
    if (!anim || !Array.isArray(anim.events) || !anim.events.length || !m || !m.sim) return;
    const k = (pv.players || []).indexOf(m.player);
    if (k < 0) return;
    const p = app.store.project, fps = p.fps || 30;
    const ids = new Set(p.sims.map(s => s.id));
    p.events = (Array.isArray(p.events) ? p.events : []).filter(e => e.type === 'NOTE' || ids.has(e.sim));
    const len = m.length || p.length;
    for (const ev of anim.events) {
      if (ev.target !== k) continue;
      const frame = Math.round(ev.start * 30) - m.from;
      if (frame < 0 || frame >= len) continue;
      const out = { type: ev.type, frame, sim: m.sim.id, skipWithCondom: !!ev.skip_with_condom };
      if (ev.type === 'CUM') Object.assign(out, { cum: ev.cum_layer_type, level: ev.cum_layer_level || 1 });
      else if (ev.type === 'UNDRESS') out.naked = ev.naked_type;
      else if (ev.type === 'EFFECT') {
        const end = ev.end === undefined || ev.end >= 9999 ? len : Math.round(ev.end * 30) - m.from;
        Object.assign(out, { effect: ev.effect_name, joint: ev.effect_joint_name, end: Math.max(frame, Math.min(len, end)) });
      } else if (ev.type !== 'REMOVE_CONDOM') continue;
      const clean = M.cleanMoment({ id: uid('e'), ...out });
      clean.frame = Math.max(0, Math.min(len - 1, clean.frame));
      p.events.push(clean);
      importCount++;
    }
    clearTimeout(importToast);
    importToast = setTimeout(async () => {
      const n = importCount; importCount = 0;
      if (!n) return;
      let dropped = 0;
      try { const r = await fetch('/api/animation_events?id=' + encodeURIComponent(anim.id)); if (r.ok) dropped = (await r.json()).dropped || 0; } catch { /* no count */ }
      M.checkEffects((p.events || []).filter(e => e.type === 'EFFECT').map(e => e.effect)).then(() => app.timeline && app.timeline.draw());
      toast(`${n} moment${n === 1 ? '' : 's'} came along (cum, undressing, effects) - on the Moments row.${dropped ? ` ${dropped} that the game can't play ${dropped === 1 ? 'was' : 'were'} left out.` : ''}`, 'ok');
      app.timeline && app.timeline.draw();
    }, 3300);
  });

  // a first look for projects that are already open
  for (const s of app.store.project.sims) lastBody.set(s.id, bodyGender(s));
  window.wickedMoments = { M, Cum, effects: app.effects };
}

export default install;

// ---------------------------------------------------------------- the voice pool
// (the same voice, body and lists give the same pool: kept until the game's lines or the sound list change)
const _pools = { lines: null, sounds: null, cands: new Map(), pools: new Map() };
export function voicePool(app, sim, set) {
  const entry = VOICE_SETS.find(x => x[0] === set) || VOICE_SETS[VOICE_SETS.length - 1];
  const voice = simVoice(sim), body = sim && sim.frame === 'ym' ? 'm' : 'f';
  if (_pools.lines !== app.voiceLines || _pools.sounds !== app.sounds) {
    _pools.lines = app.voiceLines; _pools.sounds = app.sounds; _pools.cands.clear(); _pools.pools.clear();
  }
  const key = voice + '|' + body + '|' + entry[0];
  let hit = _pools.pools.get(key);
  if (!hit) {
    let cands = _pools.cands.get(voice + '|' + body);
    if (!cands) _pools.cands.set(voice + '|' + body, cands = poolCandidates(app, sim, voice, body));
    hit = cands.filter(c => entry[2](c)).slice(0, 16);
    _pools.pools.set(key, hit);
  }
  return hit.map(x => ({ ...x }));
}

function poolCandidates(app, sim, voice, body) {
  const uses = new Map((app.sounds || []).map(s => [String(s.name).toLowerCase(), s.count || 0]));
  const seen = new Set(), cands = [];
  for (const l of app.voiceLines || []) {
    if (!(l.voices || []).includes(voice)) continue;
    const k = l.name.toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    cands.push({ name: l.name, tags: l.tags || tagsOf(l.name), lowprob: !!l.lowprob, gender: l.gender || '', sec: l.sec || 0, count: uses.get(k) || 0, kind: 'voice', source: 'game' });
  }
  for (const s of app.sounds || []) {
    if (s.kind !== 'voice' || !soundFitsSim(s.name, sim)) continue;
    // only sounds that play in the game after Send to game: the game's own, or a mod that is in Mods now (a parked
    // pack's sound would be silent) - and a creator line recorded for one voice only is used for that gender only
    if (s.source !== 'game' && s.source !== 'mods') continue;
    const rc = voiceCode(s.resolved || '');
    if (rc && (rc[0] === 'm') !== (voice[0] === 'm')) continue;
    const k = String(s.name).toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    const g = /(^|_)f(_|$)/.test(k) ? 'f' : /(^|_)m(_|$)/.test(k) ? 'm' : '';
    cands.push({ ...s, tags: tagsOf(s.name), lowprob: /lowprob/.test(k), gender: g, count: s.count || 0 });
  }
  const genderRank = c => (c.gender === body ? 0 : c.gender ? 2 : 1);
  return cands.sort((a, b) => (a.lowprob - b.lowprob) || (genderRank(a) - genderRank(b)) || (b.count - a.count) || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

// ---------------------------------------------------------------- the effects that play now
function playingEffects(app, { all = false } = {}) {
  const p = app.store.project, fps = p.fps || 30;
  const out = [];
  for (const e of p.events || []) {
    if (e.type !== 'EFFECT' || !e.effect || !e.joint) continue;
    const v = app.simViews && app.simViews.get(e.sim);
    if (!v || !v.bone(e.joint) || !v.group.visible) continue;
    if (!all && M.skippedByCondom(app, e, e.frame)) continue;
    const end = e.end !== undefined ? e.end : e.frame + fps;
    out.push({ id: e.id, kind: effectKind(e.effect), name: e.effect, start: e.frame / fps, end: Math.max(e.frame, end) / fps, simId: e.sim, bone: e.joint });
  }
  return out;
}

// ---------------------------------------------------------------- cum on the skin
function paintCum(app, frame) {
  const p = app.store.project;
  const any = (p.events || []).some(e => e.type === 'CUM');
  for (const s of p.sims) {
    const v = app.simViews && app.simViews.get(s.id);
    if (!v) continue;
    const active = any && app.showCum && !app.preview
      ? Cum.activeCum(app, s, frame, app.loopPass || 0, { skipped: e => M.skippedByCondom(app, e, frame) }) : {};
    Cum.apply(app, s, v, active);
  }
}

// ---------------------------------------------------------------- the moments in the game's XML (via bake)
export function bakeMoments(app, payload, p, views) {
  const baked = p.sims.filter(s => !views || typeof views.get !== 'function' || views.get(s.id));
  const list = baked.length === (payload.actors || []).length ? baked : p.sims;
  const idx = new Map(list.map((s, i) => [s.id, i]));
  const fps = p.fps || 30;
  const evs = (p.events || []).filter(e => e && e.type && e.type !== 'NOTE' && idx.has(e.sim)).map(e => {
    const o = { type: e.type, target: idx.get(e.sim), start: e.frame / fps };
    if (e.type === 'EFFECT') Object.assign(o, { end: Math.max(e.frame, e.end !== undefined ? e.end : e.frame + fps) / fps, effect_name: e.effect, effect_joint_name: e.joint });
    if (e.type === 'CUM') Object.assign(o, { cum_layer_type: e.cum, cum_layer_level: e.level || 1 });
    if (e.type === 'UNDRESS') o.naked_type = e.naked;
    o.skip_with_condom = !!e.skipWithCondom;
    return o;
  });
  if (evs.length) payload.events = evs;
  list.forEach((s, i) => {
    const a = payload.actors && payload.actors[i];
    if (a && s.cumAfter && s.cumAfter !== 'AUTO') a.cumAfter = Array.isArray(s.cumAfter) ? [...s.cumAfter] : s.cumAfter;
  });
  if (p.category === 'CLIMAX' && p.act) payload.act = p.act;
}

// ---------------------------------------------------------------- what Send to game warns about
function exportChecks(app, p) {
  const out = [];
  const evs = (p.events || []).filter(e => e && e.type && e.type !== 'NOTE');
  if (!evs.length) return out;
  const sim = id => p.sims.find(s => s.id === id);
  const penis = s => M.hasPenis(app, s);
  const cums = evs.filter(e => e.type === 'CUM');
  if (cums.length && !p.sims.some(penis)) out.push({ level: 'warn', text: 'WickedWhims only shows cum when someone in the act has a penis.', frame: cums[0].frame, simId: cums[0].sim });
  if (cums.length && p.category !== 'CLIMAX' && (p.loops || 10) > 1) {
    out.push({ level: 'warn', text: `Cum adds up every loop in the game (this plays ${p.loops || 10}×). For a one-time finish, make it a Climax.`, frame: cums[0].frame,
      fix: { label: 'Make it a climax', run: () => M.makeClimax(app) } });
  }
  const rig = new Set(((app.assets && app.assets.rig && app.assets.rig.bones) || []).map(b => b.name));
  const seen = new Set();
  const once = (key, x) => { if (!seen.has(key)) { seen.add(key); out.push(x); } };
  for (const e of evs) {
    const s = sim(e.sim);
    if (!s) continue;
    if (e.type === 'UNDRESS' && M.nakedFromStart(app, s)) {
      once('undress' + s.id, { level: 'warn', text: `${s.label} is naked from the start, so "undress" does nothing.`, frame: e.frame, simId: s.id,
        fix: { label: 'Start dressed', run: () => { app.store.checkpoint(); s.naked = 'NONE'; app.afterEdit(); } } });
    }
    if (e.type === 'REMOVE_CONDOM' && !penis(s)) once('condom' + s.id, { level: 'warn', text: `${s.label} has no penis, so there is no condom to take off.`, frame: e.frame, simId: s.id });
    if (e.type === 'EFFECT') {
      if (/^b__Penis_/.test(e.joint || '') && !penis(s)) once('pj' + e.id, { level: 'warn', text: `An effect plays at ${s.label}'s penis, but ${s.label} has none.`, frame: e.frame, simId: s.id });
      const v = M.validity.get(String(e.effect || '').toLowerCase());
      if (!e.effect) out.push({ level: 'error', text: 'An effect moment has no effect picked.', frame: e.frame, simId: s.id, fix: { label: 'Pick one', run: () => app.editMoment(e.id) } });
      else if (v && !v.valid) {
        const eq = v.equivalent && v.equivalent !== e.effect ? v.equivalent : null;
        out.push({ level: 'error', text: `‘${e.effect}’ is not an adult game effect${eq ? '' : ', so WickedWhims would skip it'}.`, frame: e.frame, simId: s.id,
          fix: eq ? { label: `Use ${eq}`, run: () => app.updateMoment(e.id, { effect: eq }) } : { label: 'Change it', run: () => app.editMoment(e.id) } });
      } else if (!v) M.checkEffects([e.effect]);
      if (e.joint && rig.size && !rig.has(e.joint)) out.push({ level: 'error', text: `‘${e.joint}’ is not a body part of the game's skeleton.`, frame: e.frame, simId: s.id, fix: { label: 'Change it', run: () => app.editMoment(e.id) } });
    }
  }
  return out;
}

// ---------------------------------------------------------------- the Moments row on the timeline
function momentsRow(app) {
  let drag = null;
  const canvasX = e => { const r = app.timeline.canvas.getBoundingClientRect(); return e.clientX - r.left; };
  const list = () => (app.store.project.events || []).filter(e => e && e.type);
  const colorOf = ev => (ev.type === 'NOTE' ? '#fbbf24' : ((app.store.project.sims.find(s => s.id === ev.sim) || {}).color || '#a39bb2'));
  const endOf = ev => (ev.end !== undefined ? ev.end : ev.frame + (app.store.project.fps || 30));
  const row = {
    id: 'moments', height: ROW_H, order: 10,
    get label() { const n = list().length; return n ? `Moments · ${n}` : 'Moments'; },
    draw(g, ctx) {
      const evs = list();
      const { x0, x1, y, h: hh, xAt, playing } = ctx;
      const font = 'Plus Jakarta Sans, Segoe UI, sans-serif';
      if (!evs.length) {
        g.fillStyle = 'rgba(255,255,255,0.26)'; g.font = `500 11px ${font}`; g.textBaseline = 'middle';
        g.fillText('Right-click here to add cum, undressing, a condom coming off or an effect', x0 + 10, y + hh / 2 + 0.5);
        return;
      }
      g.save();
      g.beginPath(); g.rect(x0, y, x1 - x0, hh); g.clip();
      const now = performance.now();
      // effect bars (under the flags), shimmering while it plays
      for (const ev of evs) {
        if (ev.type !== 'EFFECT') continue;
        const a = xAt(ev.frame), b = xAt(endOf(ev));
        if (b < x0 || a > x1) continue;
        const col = colorOf(ev);
        g.globalAlpha = 0.35; g.fillStyle = col;
        g.beginPath(); g.roundRect(a, y + 8, Math.max(3, b - a), 6, 3); g.fill();
        if (playing && !reduced()) {
          const w = Math.max(3, b - a), sx = a + ((now / 6) % (w + 40)) - 20;
          const grd = g.createLinearGradient(sx - 20, 0, sx + 20, 0);
          grd.addColorStop(0, 'rgba(255,255,255,0)'); grd.addColorStop(0.5, 'rgba(255,255,255,0.55)'); grd.addColorStop(1, 'rgba(255,255,255,0)');
          g.globalAlpha = 0.6; g.fillStyle = grd; g.fillRect(Math.max(a, sx - 20), y + 8, Math.min(40, b - Math.max(a, sx - 20)), 6);
        }
        g.globalAlpha = 1;
      }
      // a thin line joins the moments a Finish placed together
      const groups = new Map();
      for (const ev of evs) if (ev.group) { const gx = groups.get(ev.group) || []; gx.push(ev); groups.set(ev.group, gx); }
      for (const [, gx] of groups) {
        if (gx.length < 2) continue;
        const xs = gx.map(e => xAt(e.frame));
        g.strokeStyle = colorOf(gx[0]) + '88'; g.lineWidth = 1; g.setLineDash([2, 3]);
        g.beginPath(); g.moveTo(Math.min(...xs), y + hh - 2.5); g.lineTo(Math.max(...xs), y + hh - 2.5); g.stroke(); g.setLineDash([]);
      }
      // the flags
      for (const ev of [...evs].sort((a, b) => a.frame - b.frame)) {
        const x = Math.round(xAt(ev.frame)) + 0.5;
        if (x < x0 - 16 || x > x1 + 2) continue;
        const col = colorOf(ev), sel = app.selectedEvent === ev.id;
        const skipped = M.skippedByCondom(app, ev);
        g.fillStyle = col; g.globalAlpha = skipped ? 0.4 : 1;
        g.fillRect(x - 0.75, y + 2, 1.5, hh - 4);
        g.save();
        g.shadowColor = col; g.shadowBlur = sel ? 12 : 8;
        g.beginPath();
        g.moveTo(x, y + 3); g.lineTo(x + 12, y + 3); g.quadraticCurveTo(x + 14, y + 3, x + 13, y + 5);
        g.lineTo(x + 10.5, y + 9.5); g.lineTo(x + 13, y + 14); g.quadraticCurveTo(x + 14, y + 16, x + 12, y + 16); g.lineTo(x, y + 16); g.closePath();
        g.fill();
        g.restore();
        if (sel) { g.strokeStyle = '#ffffff'; g.lineWidth = 1.5; g.stroke(); }
        glyph(g, ev.type, x + 5.5, y + 9.5);
        g.globalAlpha = 1;
        if (ev.type === 'NOTE' && ev.text) {
          g.save(); g.beginPath(); g.rect(x + 16, y, 80, hh); g.clip();
          g.fillStyle = '#fde9b5'; g.font = `600 10.5px ${font}`; g.textBaseline = 'middle'; g.fillText(ev.text, x + 17, y + hh / 2 + 0.5);
          g.restore();
        }
      }
      g.restore();
    },
    hit(x, y, ctx) {
      const evs = [...list()].sort((a, b) => b.frame - a.frame);
      for (const ev of evs) { const fx = ctx.xAt(ev.frame); if (x >= fx - 4 && x <= fx + 15) return ev; }
      for (const ev of evs) if (ev.type === 'EFFECT' && x >= ctx.xAt(ev.frame) && x <= ctx.xAt(endOf(ev))) return ev;
      return null;
    },
    tooltip(ev) { return `${M.momentLabel(ev, app)} · drag to move, double-click to change, right-click for more`; },
    onDown(ev, e, ctx) {
      app.selectedEvent = ev.id;
      const grab = ctx.frameAt(canvasX(e));
      const members = ev.group ? list().filter(x => x.group === ev.group) : [ev];
      const sounds = [];
      if (ev.group) for (const s of app.store.project.sims) for (const snd of s.sounds || []) if (snd.moment === ev.group) sounds.push([snd, snd.frame]);
      drag = { id: ev.id, grab, moved: false, orig: members.map(m => [m, m.frame, m.end]), sounds, last: 0 };
      app.setFrame(ev.frame);
      app.timeline.draw();
    },
    onMove(ev, frame) {
      if (!drag || drag.id !== ev.id) return;
      const len = app.store.project.length;
      const d = frame - drag.grab;
      if (d === drag.last) return;
      drag.last = d;
      if (!drag.moved) { app.store.checkpoint(); drag.moved = true; }
      // the whole group moves together, and stays inside the loop
      const lo = Math.min(...drag.orig.map(([, f]) => f)), hi = Math.max(...drag.orig.map(([, f]) => f));
      const dd = Math.max(-lo, Math.min(len - 1 - hi, d));
      for (const [m, f, en] of drag.orig) {
        m.frame = f + dd;
        if (en !== undefined) m.end = Math.max(m.frame, Math.min(len, en + dd));
        if (m.auto) delete m.auto;              // moved by hand: yours now (a new Finish keeps it)
      }
      for (const [snd, f] of drag.sounds) snd.frame = Math.max(0, Math.min(len - 1, f + dd));
      app.setFrame(ev.frame);
    },
    onUp() {
      const d = drag;
      drag = null;
      if (d && d.moved) { app.afterEdit(); if (app.momentsChanged) app.momentsChanged(); }
    },
    onContext(ev, frame, e) { app.momentMenu(e.clientX, e.clientY, ev || null, frame); },
    onDblClick(ev, frame) { app.editMoment(ev ? ev.id : null, frame); },
  };
  return row;
}

const reduced = () => (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) || document.documentElement.classList.contains('reduce-motion');

// small pictures on the flags (dark ink on the sim's colour; the cum drop is a pearl)
function glyph(g, type, cx, cy) {
  g.save();
  g.translate(cx, cy);
  g.fillStyle = '#140e19'; g.strokeStyle = '#140e19'; g.lineWidth = 1.3; g.lineJoin = 'round'; g.lineCap = 'round';
  if (type === 'CUM') {
    g.fillStyle = '#ffffff';
    g.beginPath(); g.moveTo(0, -4.2); g.bezierCurveTo(1.2, -2, 3, -0.4, 3, 1.4); g.arc(0, 1.4, 3, 0, Math.PI); g.bezierCurveTo(-3, -0.4, -1.2, -2, 0, -4.2); g.fill();
    g.strokeStyle = 'rgba(20,14,25,0.55)'; g.lineWidth = 0.8; g.stroke();
  } else if (type === 'UNDRESS') {
    g.beginPath(); g.moveTo(-1.6, -3.6); g.lineTo(-4, -2.2); g.lineTo(-3, -0.4); g.lineTo(-2, -0.9); g.lineTo(-2, 3.6); g.lineTo(2, 3.6); g.lineTo(2, -0.9); g.lineTo(3, -0.4); g.lineTo(4, -2.2); g.lineTo(1.6, -3.6); g.quadraticCurveTo(0, -2.2, -1.6, -3.6); g.fill();
  } else if (type === 'REMOVE_CONDOM') {
    g.lineWidth = 1.6; g.beginPath(); g.arc(0, 0, 3, 0, Math.PI * 2); g.stroke();
  } else if (type === 'EFFECT') {
    g.beginPath();
    for (let i = 0; i < 8; i++) { const r = i % 2 ? 1.3 : 4, a = i * Math.PI / 4 - Math.PI / 2; g.lineTo(Math.cos(a) * r, Math.sin(a) * r); }
    g.closePath(); g.fill();
  } else {
    g.beginPath(); g.arc(0, -1.2, 2.3, 0, Math.PI * 2); g.fill(); g.fillRect(-0.6, 0.6, 1.2, 3.4);
  }
  g.restore();
}

export { clone, voiceLabel };
