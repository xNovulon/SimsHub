// Step 6, Sounds & moments: automatic sounds, each sim's own game voice, the Finish, the moments (cum, undress,
// condom, effects, notes) and the list of sounds on the timeline.
import { h, icon, section, toast } from '../ui.js';
import { simTabs } from './common.js';
import { ADULT_CODES, SAMPLE_LINE, simVoice, voiceFor, voiceLabel, isVoiceLine } from '../audio.js';
import * as M from '../moments.js';

const TITLE = 'Sounds & moments', SUB = 'Voices, claps, cum and effects';

export function renderSounds(app, root) {
  const p = app.store.project;
  const rail = document.querySelector('#rail button[data-step=sounds]');
  if (rail && !rail.title) rail.title = TITLE;

  root.append(section('Automatic sounds',
    h('div', { class: 'hint', style: { marginTop: 0 } }, 'Finds where bodies hit (claps), where something goes in or slides (wet sounds) and places the right sounds on the timeline. Run it again after changing the motion.'),
    h('button', { class: 'btn primary block big', onclick: () => app.autoSounds() }, icon('wand'), 'Place sounds for me')));

  const sim = app.store.sim();
  if (sim) root.append(voiceSection(app, sim));
  root.append(finishSection(app));
  root.append(momentsSection(app));

  const lists = h('div', {});
  for (const s of p.sims) {
    const sounds = [...(s.sounds || [])].sort((a, b) => a.frame - b.frame);
    const box = h('div', { class: 'sound-list' });
    if (!sounds.length) box.append(h('div', { class: 'hint' }, 'No sounds yet.'));
    for (const snd of sounds) {
      const sec = isVoiceLine(snd.name) && app.voiceSec ? app.voiceSec.get(snd.name) : 0;
      box.append(h('div', { class: 'sound-row' },
        h('button', { class: 'icon-btn sm', title: `Listen${isVoiceLine(snd.name) ? ' (in ' + s.label + "'s voice)" : ''}`, onclick: () => app.audio.play(snd.name, { force: true, voice: voiceFor(snd.name, s), detune: isVoiceLine(snd.name) ? (s.voicePitch || 0) * 300 : 0 }).then(ok => ok || toast('This sound could not be played here (it still works in the game if its mod is installed).')) }, icon('play')),
        h('span', { class: 'f' }, (snd.frame / 30).toFixed(2) + 's'),
        h('span', { class: 'n', title: snd.name }, h('span', { class: 'tag ' + (snd.kind || 'other') }, snd.kind || 'sound'), snd.name,
          sec ? h('span', { class: 'muted sec' }, ` · ${sec.toFixed(1)} s`) : '', snd.auto ? h('span', { class: 'muted' }, ' · auto') : '', snd.moment ? h('span', { class: 'muted' }, ' · finish') : ''),
        h('button', { class: 'icon-btn sm', title: 'Remove', onclick: () => app.removeSound(s.id, snd) }, icon('trash'))));
    }
    lists.append(h('div', { style: { margin: '10px 0 4px', fontWeight: 700, color: s.color } }, `${s.label} · ${sounds.length}`), box);
  }
  root.append(section('On the timeline', lists, h('div', { class: 'hint' }, 'Drag the notes on the timeline to move sounds. Right-click one to remove it.')));
}

// ---------------------------------------------------------------- the sim's voice
function voiceSection(app, sim) {
  // only kinds this sim has voice lines for (its own adult voice), with how many there are
  const sets = app.sounds ? app.voiceSets(sim) : [];
  const who = sim.frame === 'ym' ? 'male' : 'female';
  const setSel = h('select', { disabled: !sets.length }, sets.length ? sets.map(([v, t, n]) => h('option', { value: v }, `${t} (${n})`))
    : h('option', { value: '' }, app.sounds ? `No ${who} voice lines found` : 'Reading your sounds...'));
  setSel.onchange = () => setSel.blur();
  const every = h('select', {}, [[1.5, 'Often'], [3, 'Now and then'], [6, 'Rarely']].map(([v, t]) => h('option', { value: v, selected: v === 3 }, t)));
  every.onchange = () => every.blur();
  const lines = app.voiceLines ? app.voiceLines.length : 0;
  return section(['Voice', h('span', { class: 'count' }, sim.label)], simTabs(app),
    voicePicker(app, sim),
    h('div', { class: 'hint', style: { marginTop: '6px' } }, 'In the game each sim uses their own voice. This only sets what you hear here.'),
    h('div', { class: 'grid-2 voice-kind' }, h('label', { class: 'field' }, h('span', {}, 'Kind'), setSel), h('label', { class: 'field' }, h('span', {}, 'How often'), every)),
    h('div', { class: 'btn-grid' },
      h('button', { class: 'btn small', disabled: !sets.length, onclick: () => app.randomVoices(sim.id, setSel.value, +every.value) }, icon('mic'), 'Add random voice'),
      h('button', { class: 'btn small', onclick: () => app.addSoundDialog(sim.id) }, icon('plus'), 'Pick a sound here')),
    h('div', { class: 'hint' }, `Let ${sim.label} moan or talk through the animation - random but natural. The mouth moves by itself.${lines ? ` ${lines.toLocaleString('en-US')} game voice lines.` : ''}`));
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
      title: `${voiceLabel(code)} (${code[0] === 'm' ? 'male' : 'female'}) - click to hear it${on ? '' : ' and use it'}`,
      'aria-pressed': on ? 'true' : 'false',
      onclick: () => app.setVoice ? app.setVoice(sim.id, code) : app.audio.play(SAMPLE_LINE, { force: true, voice: code }),
    }, h('span', { class: 'vp-dot' }, icon('wave')), h('span', { class: 'vp-lab' }, voiceLabel(code).replace('Voice ', '')),
    own && own.voice === code ? h('small', { class: 'vp-own' }, 'their voice') : null);
  };
  return h('div', { class: 'voice-picker', style: { '--sim': sim.color }, role: 'group', 'aria-label': `${sim.label}'s voice` },
    h('div', { class: 'vp-group' }, h('span', { class: 'vp-gl' }, 'Female'), ...ADULT_CODES.female.map(btn)),
    h('div', { class: 'vp-group' }, h('span', { class: 'vp-gl' }, 'Male'), ...ADULT_CODES.male.map(btn)),
    h('div', { class: 'vp-now' }, `${sim.label} speaks with `, h('b', {}, `${voiceLabel(mine)} (${mine[0] === 'm' ? 'male' : 'female'})`),
      own && own.voice === mine ? ' - their own game voice' : ''));
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
    title: part === 'inside' ? `Cum inside ${r ? r.label : ''} (by the kind of sex), with drips after` : `Cum on ${r ? r.label + "'s" : 'the'} ${label.toLowerCase()}, drool from ${g ? g.label + "'s" : 'the'} tip and the finish voices`,
    onclick: () => app.finishPreset ? app.finishPreset(part, F) : M.finishPreset(app, part, F),
  }, icon(part === 'inside' ? 'bolt' : 'drop'), h('span', {}, label))));
  return section(['Finish', h('span', { class: 'count' }, current.length ? 'placed' : '')],
    h('div', { class: 'card finish-card' + (nobody ? ' muted-card' : '') },
      h('div', { class: 'hint', style: { marginTop: 0 } }, `One click: cum on ${r ? r.label : 'the receiver'} at ${M.secs(at, p.fps || 30)}${F > 0 && F < len - 8 ? ' (the playhead)' : ''}, the drool of the finish and the game's own finish voices. Drag its flags on the Moments row to move it.`),
      grid,
      nobody ? h('div', { class: 'hint warn-line' }, "(WickedWhims won't show it: nobody here has a penis)") : null,
      !nobody && p.category !== 'CLIMAX' && (p.loops || 10) > 1 ? h('div', { class: 'hint' }, 'Cum adds up every loop in the game. ',
        h('button', { class: 'linkbtn', type: 'button', onclick: () => M.makeClimax(app) }, 'Make it a climax'), ' to show it once.') : null));
}

// ---------------------------------------------------------------- the moments
function momentsSection(app) {
  const p = app.store.project, fps = p.fps || 30;
  const evs = [...(p.events || [])].filter(e => e && e.type).sort((a, b) => a.frame - b.frame);
  const box = h('div', { class: 'moment-list' });
  if (!evs.length) box.append(h('div', { class: 'hint' }, 'No moments yet. Use Finish above, "Add a moment", or right-click the Moments row on the timeline.'));
  for (const ev of evs) {
    const s = p.sims.find(x => x.id === ev.sim);
    const col = ev.type === 'NOTE' ? '#fbbf24' : (s ? s.color : '#a39bb2');
    const ic = (M.TYPES.find(t => t[0] === ev.type) || [])[2] || 'pin';
    const skipped = M.skippedByCondom(app, ev);
    box.append(h('div', { class: 'moment-row' + (app.selectedEvent === ev.id ? ' on' : '') + (skipped ? ' skipped' : ''), style: { '--sim': col } },
      h('span', { class: 'mr-flag' }, icon(ic)),
      h('button', { class: 'mr-text', type: 'button', title: 'Go there', onclick: () => { app.selectedEvent = ev.id; app.setFrame(ev.frame); app.renderStep(); } },
        M.momentLabel(ev, app), skipped ? h('span', { class: 'muted' }, ' · skipped (condom on)') : null),
      h('button', { class: 'icon-btn sm', title: 'Change', onclick: () => app.editMoment(ev.id) }, icon('pose')),
      h('button', { class: 'icon-btn sm', title: 'Delete', onclick: () => app.removeMoment(ev.id, { group: false }) }, icon('trash'))));
  }
  const givers = M.penisSims(app);
  const condoms = givers.length ? h('div', { class: 'moment-condoms' }, givers.map(s => {
    const cb = h('input', { type: 'checkbox', checked: !!s.previewCondom });
    cb.addEventListener('change', () => { app.store.checkpoint(); if (cb.checked) s.previewCondom = true; else delete s.previewCondom; app.afterEdit(); });
    return h('label', { class: 'check', title: 'Only here, to see what "skip when wearing a condom" does. WickedWhims decides in the game.' }, cb, `${s.label} wears a condom`, h('span', { class: 'muted small' }, ' (only here)'));
  })) : null;
  const toggles = h('div', { class: 'moment-toggles' },
    h('button', { class: 'chipbtn' + (app.showEffects !== false ? ' on' : ''), type: 'button', onclick: () => app.setShowEffects && app.setShowEffects(app.showEffects === false) }, 'Show effects'),
    h('button', { class: 'chipbtn' + (app.showCum !== false ? ' on' : ''), type: 'button', onclick: () => app.setShowCum && app.setShowCum(app.showCum === false) }, 'Show cum'));
  return section(['Moments', h('span', { class: 'count' }, evs.length ? String(evs.length) : '')],
    h('div', { class: 'hint', style: { marginTop: 0 } }, `What WickedWhims does during the loop: cum, undressing, a condom coming off, effects (drool, splashes, tears). At ${M.secs(Math.round(app.store.frame), fps)} now.`),
    h('div', { class: 'btn-grid' },
      h('button', { class: 'btn small', onclick: () => app.editMoment ? app.editMoment(null, Math.round(app.store.frame)) : M.openMomentDialog(app, null, Math.round(app.store.frame)) }, icon('flag'), 'Add a moment'),
      h('button', { class: 'btn small', onclick: () => app.editMoment ? app.editMoment(null, Math.round(app.store.frame), { type: 'EFFECT' }) : M.openMomentDialog(app, null, Math.round(app.store.frame), { type: 'EFFECT' }) }, icon('fx'), 'Add an effect')),
    box, condoms, toggles);
}
