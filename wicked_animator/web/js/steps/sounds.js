// Step 6, Sounds & moments: automatic sounds, each sim's own game voice, the Finish, the moments (cum, undress,
// condom, effects, notes) and the list of sounds on the timeline.
import { h, icon, section, toast } from '../ui.js';
import { simTabs } from './common.js';
import { ADULT_CODES, SAMPLE_LINE, simVoice, voiceFor, voiceLabel, isVoiceLine } from '../audio.js';
import * as M from '../moments.js';
import { $t, inSentence } from '../i18n.js';

const TITLE = $t('steps.sounds.sounds_moments'), SUB = $t('steps.sounds.voices_claps_cum_and_effects');

export function renderSounds(app, root) {
  const p = app.store.project;
  const rail = document.querySelector('#rail button[data-step=sounds]');
  if (rail && !rail.title) rail.title = TITLE;

  root.append(section($t('steps.sounds.automatic_sounds'),
    h('div', { class: 'hint', style: { marginTop: 0 } }, $t('steps.sounds.finds_where_bodies_hit_claps')),
    h('button', { class: 'btn primary block big', onclick: () => app.autoSounds() }, icon('wand'), $t('steps.sounds.place_sounds_for_me'))));

  const sim = app.store.sim();
  if (sim) root.append(voiceSection(app, sim));
  root.append(finishSection(app));
  root.append(momentsSection(app));

  const lists = h('div', {});
  for (const s of p.sims) {
    const sounds = [...(s.sounds || [])].sort((a, b) => a.frame - b.frame);
    const box = h('div', { class: 'sound-list' });
    if (!sounds.length) box.append(h('div', { class: 'hint' }, $t('steps.sounds.no_sounds_yet')));
    for (const snd of sounds) {
      const sec = isVoiceLine(snd.name) && app.voiceSec ? app.voiceSec.get(snd.name) : 0;
      box.append(h('div', { class: 'sound-row' },
        h('button', { class: 'icon-btn sm', title: isVoiceLine(snd.name) ? $t('steps.sounds.listen_in_voice', { sLabel: s.label }) : $t('steps.sounds.listen'), onclick: () => app.audio.play(snd.name, { force: true, voice: voiceFor(snd.name, s), detune: isVoiceLine(snd.name) ? (s.voicePitch || 0) * 300 : 0 }).then(ok => ok || toast($t('steps.sounds.this_sound_could_not_be'))) }, icon('play')),
        h('span', { class: 'f' }, (snd.frame / 30).toFixed(2) + 's'),
        h('span', { class: 'n', title: snd.name }, h('span', { class: 'tag ' + (snd.kind || 'other') }, snd.kind || 'sound'), snd.name,
          sec ? h('span', { class: 'muted sec' }, ` · ${sec.toFixed(1)} s`) : '', snd.auto ? h('span', { class: 'muted' }, $t('steps.sounds.auto')) : '', snd.moment ? h('span', { class: 'muted' }, $t('steps.sounds.finish')) : ''),
        h('button', { class: 'icon-btn sm', title: $t('steps.sounds.remove'), onclick: () => app.removeSound(s.id, snd) }, icon('trash'))));
    }
    lists.append(h('div', { style: { margin: '10px 0 4px', fontWeight: 700, color: s.color } }, `${s.label} · ${sounds.length}`), box);
  }
  root.append(section($t('steps.sounds.on_timeline'), lists, h('div', { class: 'hint' }, $t('steps.sounds.drag_notes_on_timeline_to'))));
}

// ---------------------------------------------------------------- the sim's voice
function voiceSection(app, sim) {
  // only kinds this sim has voice lines for (its own adult voice), with how many there are
  const sets = app.sounds ? app.voiceSets(sim) : [];
  const who = sim.frame === 'ym' ? 'male' : 'female';
  const setSel = h('select', { disabled: !sets.length }, sets.length ? sets.map(([v, t, n]) => h('option', { value: v }, `${t} (${n})`))
    : h('option', { value: '' }, app.sounds ? $t('steps.sounds.no_voice_lines_found', { who }) : $t('steps.sounds.reading_your_sounds')));
  setSel.onchange = () => setSel.blur();
  const every = h('select', {}, [[1.5, $t('steps.sounds.often')], [3, $t('steps.sounds.now_and_then')], [6, $t('steps.sounds.rarely')]].map(([v, t]) => h('option', { value: v, selected: v === 3 }, t)));
  every.onchange = () => every.blur();
  const lines = app.voiceLines ? app.voiceLines.length : 0;
  return section([$t('steps.sounds.voice'), h('span', { class: 'count' }, sim.label)], simTabs(app),
    voicePicker(app, sim),
    h('div', { class: 'hint', style: { marginTop: '6px' } }, $t('steps.sounds.in_game_each_sim_uses')),
    h('div', { class: 'grid-2 voice-kind' }, h('label', { class: 'field' }, h('span', {}, $t('steps.sounds.kind')), setSel), h('label', { class: 'field' }, h('span', {}, $t('steps.sounds.how_often')), every)),
    h('div', { class: 'btn-grid' },
      h('button', { class: 'btn small', disabled: !sets.length, onclick: () => app.randomVoices(sim.id, setSel.value, +every.value) }, icon('mic'), $t('steps.sounds.add_random_voice')),
      h('button', { class: 'btn small', onclick: () => app.addSoundDialog(sim.id) }, icon('plus'), $t('steps.sounds.pick_sound_here'))),
    h('div', { class: 'hint' }, $t('steps.sounds.let_moan', { sim: sim.label }) + (lines ? $t('steps.sounds.n_game_voice_lines', { n: lines }) : '')));
}

// Six round buttons: Voice 1-3 female, Voice 1-3 male. The sim's own glows in its colour; the other gender's are dim
// (still allowed: a female body with a male voice, or the other way round).
function voicePicker(app, sim) {
  const mine = simVoice(sim), own = app.trayVoiceOf ? app.trayVoiceOf(sim) : null;
  const male = sim.frame === 'ym';
  const btn = code => {
    const other = (code[0] === 'm') !== male;
    const on = mine === code;
    return h('button', {
      class: 'vp-btn' + (on ? ' on' : '') + (other ? ' other' : ''), type: 'button', 'data-voice': code,
      title: $t(code[0] === 'm' ? (on ? 'steps.sounds.voice_male_hear' : 'steps.sounds.voice_male_use') : (on ? 'steps.sounds.voice_female_hear' : 'steps.sounds.voice_female_use'), { voice: voiceLabel(code) }),
      'aria-pressed': on ? 'true' : 'false',
      onclick: () => app.setVoice ? app.setVoice(sim.id, code) : app.audio.play(SAMPLE_LINE, { force: true, voice: code }),
    }, h('span', { class: 'vp-dot' }, icon('wave')), h('span', { class: 'vp-lab' }, voiceLabel(code).replace('Voice ', '')),
    own && own.voice === code ? h('small', { class: 'vp-own' }, $t('steps.sounds.their_voice')) : null);
  };
  return h('div', { class: 'voice-picker', style: { '--sim': sim.color }, role: 'group', 'aria-label': $t('steps.sounds.s_voice', { simLabel: sim.label }) },
    h('div', { class: 'vp-group' }, h('span', { class: 'vp-gl' }, $t('steps.sounds.female')), ...ADULT_CODES.female.map(btn)),
    h('div', { class: 'vp-group' }, h('span', { class: 'vp-gl' }, $t('steps.sounds.male')), ...ADULT_CODES.male.map(btn)),
    h('div', { class: 'vp-now' }, $t('steps.sounds.speaks_with', { simLabel: sim.label }), h('b', {}, `${voiceLabel(mine)} (${mine[0] === 'm' ? 'male' : 'female'})`),
      own && own.voice === mine ? $t('steps.sounds.their_own_game_voice') : ''));
}

// ---------------------------------------------------------------- the Finish
function finishSection(app) {
  const p = app.store.project;
  const r = M.defaultTarget(app, 'CUM'), g = M.giverOf(app);
  const nobody = !M.penisSims(app).length;
  const F = Math.round(app.store.frame), len = p.length;
  const at = F > 0 && F < len - 8 ? F : Math.round(0.7 * len);
  const current = [...M.finishGroups(p.events)];
  const grid = h('div', { class: 'finish-grid' }, M.FINISH_PARTS.map(([part, label]) => h('button', {
    class: 'finish-btn', type: 'button', 'data-part': part,
    title: part === 'inside' ? $t('steps.sounds.cum_inside_by_kind_of', { v: r ? r.label : '' }) : $t(r && g ? 'steps.sounds.finish_title_named' : 'steps.sounds.finish_title', { part: inSentence(label), receiver: r ? r.label : '', giver: g ? g.label : '' }),
    onclick: () => app.finishPreset ? app.finishPreset(part, F) : M.finishPreset(app, part, F),
  }, icon(part === 'inside' ? 'bolt' : 'drop'), h('span', {}, label))));
  return section([$t('steps.sounds.finish_2'), h('span', { class: 'count' }, current.length ? 'placed' : '')],
    h('div', { class: 'card finish-card' + (nobody ? ' muted-card' : '') },
      h('div', { class: 'hint', style: { marginTop: 0 } }, $t(F > 0 && F < len - 8 ? 'steps.sounds.finish_hint_playhead' : 'steps.sounds.finish_hint', { who: r ? r.label : $t('steps.sounds.receiver'), at: M.secs(at, p.fps || 30) })),
      grid,
      nobody ? h('div', { class: 'hint warn-line' }, $t('steps.sounds.wickedwhims_won_t_show_it')) : null,
      !nobody && p.category !== 'CLIMAX' && (p.loops || 10) > 1 ? h('div', { class: 'hint' }, $t('steps.sounds.cum_adds_up_every_loop'),
        h('button', { class: 'linkbtn', type: 'button', onclick: () => M.makeClimax(app) }, $t('steps.sounds.make_it_climax')), $t('steps.sounds.to_show_it_once')) : null));
}

// ---------------------------------------------------------------- the moments
function momentsSection(app) {
  const p = app.store.project, fps = p.fps || 30;
  const evs = [...(p.events || [])].filter(e => e && e.type).sort((a, b) => a.frame - b.frame);
  const box = h('div', { class: 'moment-list' });
  if (!evs.length) box.append(h('div', { class: 'hint' }, $t('steps.sounds.no_moments_yet_use_finish')));
  for (const ev of evs) {
    const s = p.sims.find(x => x.id === ev.sim);
    const col = ev.type === 'NOTE' ? '#fbbf24' : (s ? s.color : '#a39bb2');
    const ic = (M.TYPES.find(t => t[0] === ev.type) || [])[2] || 'pin';
    const skipped = M.skippedByCondom(app, ev);
    box.append(h('div', { class: 'moment-row' + (app.selectedEvent === ev.id ? ' on' : '') + (skipped ? ' skipped' : ''), style: { '--sim': col } },
      h('span', { class: 'mr-flag' }, icon(ic)),
      h('button', { class: 'mr-text', type: 'button', title: $t('steps.sounds.go_there'), onclick: () => { app.selectedEvent = ev.id; app.setFrame(ev.frame); app.renderStep(); } },
        M.momentLabel(ev, app), skipped ? h('span', { class: 'muted' }, $t('steps.sounds.skipped_condom_on')) : null),
      h('button', { class: 'icon-btn sm', title: $t('steps.sounds.change'), onclick: () => app.editMoment(ev.id) }, icon('pose')),
      h('button', { class: 'icon-btn sm', title: $t('steps.sounds.delete'), onclick: () => app.removeMoment(ev.id, { group: false }) }, icon('trash'))));
  }
  const givers = M.penisSims(app);
  const condoms = givers.length ? h('div', { class: 'moment-condoms' }, givers.map(s => {
    const cb = h('input', { type: 'checkbox', checked: !!s.previewCondom });
    cb.addEventListener('change', () => { app.store.checkpoint(); if (cb.checked) s.previewCondom = true; else delete s.previewCondom; app.afterEdit(); });
    return h('label', { class: 'check', title: $t('steps.sounds.only_here_to_see_what') }, cb, $t('steps.sounds.wears_condom', { sLabel: s.label }), h('span', { class: 'muted small' }, $t('steps.sounds.only_here')));
  })) : null;
  const toggles = h('div', { class: 'moment-toggles' },
    h('button', { class: 'chipbtn' + (app.showEffects !== false ? ' on' : ''), type: 'button', onclick: () => app.setShowEffects && app.setShowEffects(app.showEffects === false) }, $t('steps.sounds.show_effects')),
    h('button', { class: 'chipbtn' + (app.showCum !== false ? ' on' : ''), type: 'button', onclick: () => app.setShowCum && app.setShowCum(app.showCum === false) }, $t('steps.sounds.show_cum')));
  return section([$t('steps.sounds.moments'), h('span', { class: 'count' }, evs.length ? String(evs.length) : '')],
    h('div', { class: 'hint', style: { marginTop: 0 } }, $t('steps.sounds.what_wickedwhims_does_during_loop', { secs: M.secs(Math.round(app.store.frame), fps) })),
    h('div', { class: 'btn-grid' },
      h('button', { class: 'btn small', onclick: () => app.editMoment ? app.editMoment(null, Math.round(app.store.frame)) : M.openMomentDialog(app, null, Math.round(app.store.frame)) }, icon('flag'), $t('steps.sounds.add_moment')),
      h('button', { class: 'btn small', onclick: () => app.editMoment ? app.editMoment(null, Math.round(app.store.frame), { type: 'EFFECT' }) : M.openMomentDialog(app, null, Math.round(app.store.frame), { type: 'EFFECT' }) }, icon('fx'), $t('steps.sounds.add_effect'))),
    box, condoms, toggles);
}
