// Add one sound at the playhead: creator sounds by kind, the game's own voice lines (in the sim's own voice), or a
// sound file of your own (mysounds.js: packed into the animation, so it plays in the game).
import { h, icon, modal, toast } from '../ui.js';
import { soundFitsSim, simVoice, voiceFor, isVoiceLine, voiceLabel, lineRank } from '../audio.js';
import { ACCEPT, listMySounds, uploadMySound } from '../mysounds.js';
import { $t } from '../i18n.js';

const select = (options, value) => h('select', {}, options.map(([v, t]) => h('option', { value: v, selected: v === value }, t)));
// tag chips for the game's voice lines
const GAME_TAGS = [['moan', $t('dialogs.sound.moan')], ['woohoo', $t('dialogs.sound.woohoo')], ['climax', $t('dialogs.sound.climax')], ['breath', $t('dialogs.sound.breath')], ['kiss', $t('dialogs.sound.kiss')], ['flirt', $t('dialogs.sound.flirt')]];

export function openAddSoundDialog(app, simId) {
  // voice lines of another gender or of children are never offered for this sim
  const forSim = app.store.sim(simId);
  const voice = simVoice(forSim);
  const sounds = (app.sounds || []).filter(s => soundFitsSim(s.name, forSim));
  const rank = s => (s.source === 'mods' ? 0 : s.source === 'game' ? 1 : 2);
  sounds.sort((a, b) => rank(a) - rank(b) || b.count - a.count);
  const kindSel = select([['clap', $t('dialogs.sound.claps_slaps')], ['wet', $t('dialogs.sound.wet_oral_kisses')], ['voice', $t('dialogs.sound.voice')], ['game', $t('dialogs.sound.game_voices')], ['other', $t('dialogs.sound.other')], ['mine', $t('dialogs.sound.your_own_sound_files')], ['', $t('dialogs.sound.all')]], 'clap');
  const filter = h('input', { class: 'text', placeholder: $t('dialogs.sound.filter_by_name') });
  const list = h('div', { class: 'proj-list', style: { maxHeight: '44vh' } });
  const tagOn = new Set();
  const chips = h('div', { class: 'chips game-voice-chips' });
  const drawChips = () => {
    chips.innerHTML = '';
    chips.append(...GAME_TAGS.map(([t, label]) => h('button', { class: 'chipbtn' + (tagOn.has(t) ? ' on' : ''), type: 'button',
      onclick: () => { if (tagOn.has(t)) tagOn.delete(t); else tagOn.add(t); drawChips(); render(); } }, label)));
  };
  const listen = (name, e) => {
    e.stopPropagation();
    const v = voiceFor(name, forSim);
    app.audio.play(name, { force: true, voice: v, detune: isVoiceLine(name) ? ((forSim && forSim.voicePitch) || 0) * 300 : 0 })
      .then(ok => ok || toast($t('dialogs.sound.could_not_play_this_one')));
  };
  const place = (name, kind, label) => {
    const sim = app.store.sim(simId);
    app.store.checkpoint();
    sim.sounds = sim.sounds || [];
    sim.sounds.push({ frame: Math.round(app.store.frame), name, kind });
    dlg.close();
    app.afterEdit();
    toast($t('dialogs.sound.at_frame', { label: label || name, frame: Math.round(app.store.frame) }), 'ok');
  };
  const gameRows = () => {
    const f = filter.value.toLowerCase().trim();
    const words = f.split(/\s+/).filter(Boolean);
    const lines = (app.voiceLines || []).filter(x => (x.voices || []).includes(voice));
    const out = lines.filter(x => (!tagOn.size || [...tagOn].every(t => (x.tags || []).includes(t))) && words.every(w => x.name.toLowerCase().includes(w)));
    // moans, WooHoo, climax, breathing and kisses first; lines that never sound sexy and the rare "lowprob" takes last
    const rank = new Map(out.map(x => [x, lineRank(x)]));
    out.sort((a, b) => rank.get(a) - rank.get(b) || (a.name < b.name ? -1 : 1));
    return { out, total: lines.length };
  };
  // ---- your own sound files
  let mine = null, mineErr = '', adding = false;
  const asVoice = h('input', { type: 'checkbox' });
  const fileIn = h('input', { type: 'file', accept: ACCEPT, hidden: true });
  const loadMine = () => listMySounds().then(x => { mine = x; }).catch(() => { mine = []; }).then(() => { if (list.isConnected && kindSel.value === 'mine') render(); });
  const addFile = async file => {
    if (!file || adding) return;
    adding = true; mineErr = ''; render();
    try {
      const s = await uploadMySound(file, asVoice.checked ? 'voice' : 'other');
      mine = [s, ...(mine || []).filter(x => x.name !== s.name)];
      adding = false;
      if (s.turned_down) toast($t('dialogs.sound.was_turned_down_little_so', { sLabel: s.label }));
      place(s.name, s.kind === 'voice' ? 'voice' : 'other', s.label);
    } catch (err) {
      adding = false; mineErr = err.message || String(err); render();
    }
  };
  fileIn.addEventListener('change', () => { addFile(fileIn.files && fileIn.files[0]); fileIn.value = ''; });
  const renderMine = () => {
    if (mine === null) loadMine();
    const drop = h('button', { class: 'ls-drop my-sound-drop', type: 'button', disabled: adding, style: { width: '100%' }, onclick: () => fileIn.click(), title: $t('dialogs.sound.wav_mp3_ogg_or_flac') },
      icon(adding ? 'wave' : 'folder'), h('span', {}, h('b', {}, adding ? $t('dialogs.sound.making_it_game_sound') : $t('dialogs.sound.add_sound_file')), h('small', {}, $t('dialogs.sound.or_drop_it_here_wav'))));
    drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('over'));
    drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('over'); addFile(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]); });
    list.append(h('div', { class: 'hint', style: { margin: '0 2px 6px' } }, $t('dialogs.sound.your_own_sound_is_packed')),
      drop, fileIn,
      h('label', { class: 'check', style: { display: 'flex', alignItems: 'center', gap: '6px', margin: '6px 2px' } }, asVoice, $t('dialogs.sound.it_s_voice_moans_words')),
      mineErr ? h('div', { class: 'warn-box error my-sound-error' }, mineErr) : null);
    const f = filter.value.toLowerCase();
    const rows = (mine || []).filter(s => !f || (s.label + ' ' + s.name).toLowerCase().includes(f));
    for (const s of rows) {
      list.append(h('div', { class: 'proj-item my-sound', onclick: () => place(s.name, s.kind === 'voice' ? 'voice' : 'other', s.label) }, h('span', { style: { display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 } },
        h('button', { class: 'icon-btn sm', title: $t('dialogs.sound.listen_as_game_will_play'), onclick: e => listen(s.name, e) }, icon('play')),
        h('span', { class: 'tag ' + (s.kind === 'voice' ? 'voice' : 'other') }, s.kind === 'voice' ? 'voice' : 'yours'), h('span', { class: 'n', title: s.name }, s.label)),
      h('span', { class: 'muted' }, $t('dialogs.sound.s_kb', { seconds: (+s.seconds || 0).toFixed(1), v: Math.max(1, Math.round((s.bytes || 0) / 1024)) }))));
    }
    if (mine && !rows.length && !adding) list.append(h('div', { class: 'empty' }, mine.length ? $t('dialogs.sound.nothing_matches') : $t('dialogs.sound.no_sound_files_of_your')));
  };
  const render = () => {
    list.innerHTML = '';
    const game = kindSel.value === 'game';
    chips.style.display = game ? '' : 'none';
    if (kindSel.value === 'mine') { renderMine(); return; }
    if (game) {
      if (!app.voiceLines) { list.append(h('div', { class: 'empty' }, $t('dialogs.sound.reading_game_s_voice_lines'))); return; }
      const { out, total } = gameRows();
      const note = (voice[0] === 'm' ? $t('dialogs.sound.game_lines_male', { total, voice: voiceLabel(voice) }) : $t('dialogs.sound.game_lines_female', { total, voice: voiceLabel(voice) }));
      list.append(h('div', { class: 'hint', style: { margin: '0 2px 4px' } }, note));
      for (const x of out.slice(0, 200)) {
        list.append(h('div', { class: 'proj-item', onclick: () => place(x.name, 'voice') },
          h('span', { style: { display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 } },
            h('button', { class: 'icon-btn sm', title: $t('dialogs.sound.listen', { voiceLabel: voiceLabel(voice) }), onclick: e => listen(x.name, e) }, icon('play')),
            h('span', { class: 'tag voice' }, (x.tags || [])[0] || 'voice'), h('span', { class: 'n' }, x.name)),
          h('span', { class: 'muted' }, $t('dialogs.sound.game_voice', { v: x.sec ? x.sec.toFixed(1) + ' s · ' : '' }))));
      }
      if (!out.length) list.append(h('div', { class: 'empty' }, $t('dialogs.sound.nothing_matches')));
      else if (out.length > 200) list.append(h('div', { class: 'hint' }, $t('dialogs.sound.more_type_to_narrow_it', { outCount: out.length - 200 })));
      return;
    }
    const f = filter.value.toLowerCase();
    const rows = sounds.filter(s => (!kindSel.value || s.kind === kindSel.value) && (!f || s.name.toLowerCase().includes(f))).slice(0, 200);
    for (const s of rows) {
      list.append(h('div', { class: 'proj-item', onclick: () => place(s.name, s.kind) }, h('span', { style: { display: 'flex', alignItems: 'center', gap: '6px' } },
        h('button', { class: 'icon-btn sm', title: $t('dialogs.sound.listen_2'), onclick: e => listen(s.name, e) }, icon('play')),
        h('span', { class: 'tag ' + (s.kind || 'other') }, s.kind), s.name),
      h('span', { class: 'muted' }, s.source === 'mods' ? $t('dialogs.sound.in_your_mods') : s.source === 'game' ? $t('dialogs.sound.game') : $t('dialogs.sound.parked_pack'), $t('dialogs.sound.used', { count: s.count }))));
    }
    if (!rows.length) list.append(h('div', { class: 'empty' }, $t('dialogs.sound.nothing_matches')));
  };
  kindSel.onchange = () => { render(); kindSel.blur(); };
  filter.oninput = render;
  drawChips();
  const dlg = modal({ title: $t('dialogs.sound.add_sound_at_frame', { frame: Math.round(app.store.frame) }), text: $t('dialogs.sound.sounds_used_by_wickedwhims_animation'),
    body: h('div', {}, h('div', { class: 'grid-2' }, kindSel, filter), chips, h('div', { style: { height: '8px' } }), list), buttons: [{ label: $t('dialogs.sound.close'), kind: 'ghost' }] });
  render();
  // the game's lines arrive a moment after start: show them when they do
  if (!app.voiceLines && app.voicesReady) app.voicesReady.then(() => { if (list.isConnected && kindSel.value === 'game') render(); });
}
