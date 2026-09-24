// Add one sound at the playhead: creator sounds by kind, the game's own voice lines (in the sim's own voice), or a
// sound file of your own (mysounds.js: packed into the animation, so it plays in the game).
import { h, icon, modal, toast } from '../ui.js';
import { soundFitsSim, simVoice, voiceFor, isVoiceLine, voiceLabel, lineRank } from '../audio.js';
import { ACCEPT, listMySounds, uploadMySound } from '../mysounds.js';

const select = (options, value) => h('select', {}, options.map(([v, t]) => h('option', { value: v, selected: v === value }, t)));
// tag chips for the game's voice lines
const GAME_TAGS = [['moan', 'Moan'], ['woohoo', 'WooHoo'], ['climax', 'Climax'], ['breath', 'Breath'], ['kiss', 'Kiss'], ['flirt', 'Flirt']];

export function openAddSoundDialog(app, simId) {
  // voice lines of another gender or of children are never offered for this sim
  const forSim = app.store.sim(simId);
  const voice = simVoice(forSim);
  const sounds = (app.sounds || []).filter(s => soundFitsSim(s.name, forSim));
  const rank = s => (s.source === 'mods' ? 0 : s.source === 'game' ? 1 : 2);
  sounds.sort((a, b) => rank(a) - rank(b) || b.count - a.count);
  const kindSel = select([['clap', 'Claps & slaps'], ['wet', 'Wet / oral / kisses'], ['voice', 'Voice'], ['game', 'Game voices'], ['other', 'Other'], ['mine', 'Your own sound files'], ['', 'All']], 'clap');
  const filter = h('input', { class: 'text', placeholder: 'Filter by name' });
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
      .then(ok => ok || toast('Could not play this one here.'));
  };
  const place = (name, kind, label) => {
    const sim = app.store.sim(simId);
    app.store.checkpoint();
    sim.sounds = sim.sounds || [];
    sim.sounds.push({ frame: Math.round(app.store.frame), name, kind });
    dlg.close();
    app.afterEdit();
    toast(`${label || name} at frame ${Math.round(app.store.frame)}.`, 'ok');
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
      if (s.turned_down) toast(`"${s.label}" was turned down a little so it never clips.`);
      place(s.name, s.kind === 'voice' ? 'voice' : 'other', s.label);
    } catch (err) {
      adding = false; mineErr = err.message || String(err); render();
    }
  };
  fileIn.addEventListener('change', () => { addFile(fileIn.files && fileIn.files[0]); fileIn.value = ''; });
  const renderMine = () => {
    if (mine === null) loadMine();
    const drop = h('button', { class: 'ls-drop my-sound-drop', type: 'button', disabled: adding, style: { width: '100%' }, onclick: () => fileIn.click(), title: 'WAV, MP3, OGG or FLAC, up to 30 seconds' },
      icon(adding ? 'wave' : 'folder'), h('span', {}, h('b', {}, adding ? 'Making it a game sound...' : 'Add a sound file'), h('small', {}, 'or drop it here - WAV, MP3, OGG or FLAC, up to 30 s')));
    drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('over'));
    drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('over'); addFile(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]); });
    list.append(h('div', { class: 'hint', style: { margin: '0 2px 6px' } }, 'Your own sound is packed into the animation, so it plays in the game - for you and for everyone you share the mod with.'),
      drop, fileIn,
      h('label', { class: 'check', style: { display: 'flex', alignItems: 'center', gap: '6px', margin: '6px 2px' } }, asVoice, 'It\'s a voice (moans, words) - WickedWhims\' own voice sounds stay quiet'),
      mineErr ? h('div', { class: 'warn-box error my-sound-error' }, mineErr) : null);
    const f = filter.value.toLowerCase();
    const rows = (mine || []).filter(s => !f || (s.label + ' ' + s.name).toLowerCase().includes(f));
    for (const s of rows) {
      list.append(h('div', { class: 'proj-item my-sound', onclick: () => place(s.name, s.kind === 'voice' ? 'voice' : 'other', s.label) }, h('span', { style: { display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 } },
        h('button', { class: 'icon-btn sm', title: 'Listen (as the game will play it)', onclick: e => listen(s.name, e) }, icon('play')),
        h('span', { class: 'tag ' + (s.kind === 'voice' ? 'voice' : 'other') }, s.kind === 'voice' ? 'voice' : 'yours'), h('span', { class: 'n', title: s.name }, s.label)),
      h('span', { class: 'muted' }, `${(+s.seconds || 0).toFixed(1)} s · ${Math.max(1, Math.round((s.bytes || 0) / 1024))} KB`)));
    }
    if (mine && !rows.length && !adding) list.append(h('div', { class: 'empty' }, mine.length ? 'Nothing matches.' : 'No sound files of your own yet.'));
  };
  const render = () => {
    list.innerHTML = '';
    const game = kindSel.value === 'game';
    chips.style.display = game ? '' : 'none';
    if (kindSel.value === 'mine') { renderMine(); return; }
    if (game) {
      if (!app.voiceLines) { list.append(h('div', { class: 'empty' }, 'Reading the game\'s voice lines...')); return; }
      const { out, total } = gameRows();
      const note = `${total.toLocaleString('en-US')} game lines · plays in each sim's own voice (here: ${voiceLabel(voice)}, ${voice[0] === 'm' ? 'male' : 'female'})`;
      list.append(h('div', { class: 'hint', style: { margin: '0 2px 4px' } }, note));
      for (const x of out.slice(0, 200)) {
        list.append(h('div', { class: 'proj-item', onclick: () => place(x.name, 'voice') },
          h('span', { style: { display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 } },
            h('button', { class: 'icon-btn sm', title: `Listen (${voiceLabel(voice)})`, onclick: e => listen(x.name, e) }, icon('play')),
            h('span', { class: 'tag voice' }, (x.tags || [])[0] || 'voice'), h('span', { class: 'n' }, x.name)),
          h('span', { class: 'muted' }, `${x.sec ? x.sec.toFixed(1) + ' s · ' : ''}game voice`)));
      }
      if (!out.length) list.append(h('div', { class: 'empty' }, 'Nothing matches.'));
      else if (out.length > 200) list.append(h('div', { class: 'hint' }, `${out.length - 200} more - type to narrow it down.`));
      return;
    }
    const f = filter.value.toLowerCase();
    const rows = sounds.filter(s => (!kindSel.value || s.kind === kindSel.value) && (!f || s.name.toLowerCase().includes(f))).slice(0, 200);
    for (const s of rows) {
      list.append(h('div', { class: 'proj-item', onclick: () => place(s.name, s.kind) }, h('span', { style: { display: 'flex', alignItems: 'center', gap: '6px' } },
        h('button', { class: 'icon-btn sm', title: 'Listen', onclick: e => listen(s.name, e) }, icon('play')),
        h('span', { class: 'tag ' + (s.kind || 'other') }, s.kind), s.name),
      h('span', { class: 'muted' }, s.source === 'mods' ? 'in your Mods' : s.source === 'game' ? 'game' : 'parked pack', ` · used ${s.count}×`)));
    }
    if (!rows.length) list.append(h('div', { class: 'empty' }, 'Nothing matches.'));
  };
  kindSel.onchange = () => { render(); kindSel.blur(); };
  filter.oninput = render;
  drawChips();
  const dlg = modal({ title: 'Add a sound at frame ' + Math.round(app.store.frame), text: 'Sounds used by WickedWhims animations, the game\'s own voice lines, or a sound file of your own. "In your Mods" and "game" sounds play with your current Mods folder.',
    body: h('div', {}, h('div', { class: 'grid-2' }, kindSel, filter), chips, h('div', { style: { height: '8px' } }), list), buttons: [{ label: 'Close', kind: 'ghost' }] });
  render();
  // the game's lines arrive a moment after start: show them when they do
  if (!app.voiceLines && app.voicesReady) app.voicesReady.then(() => { if (list.isConnected && kindSel.value === 'game') render(); });
}
