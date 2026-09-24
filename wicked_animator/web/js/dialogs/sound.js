// Add one sound at the playhead: creator sounds by kind, or the game's own voice lines (in the sim's own voice).
import { h, icon, modal, toast } from '../ui.js';
import { soundFitsSim, simVoice, voiceFor, isVoiceLine, voiceLabel, lineRank } from '../audio.js';

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
  const kindSel = select([['clap', 'Claps & slaps'], ['wet', 'Wet / oral / kisses'], ['voice', 'Voice'], ['game', 'Game voices'], ['other', 'Other'], ['', 'All']], 'clap');
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
  const place = (name, kind) => {
    const sim = app.store.sim(simId);
    app.store.checkpoint();
    sim.sounds = sim.sounds || [];
    sim.sounds.push({ frame: Math.round(app.store.frame), name, kind });
    dlg.close();
    app.afterEdit();
    toast(`${name} at frame ${Math.round(app.store.frame)}.`, 'ok');
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
  const render = () => {
    list.innerHTML = '';
    const game = kindSel.value === 'game';
    chips.style.display = game ? '' : 'none';
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
  const dlg = modal({ title: 'Add a sound at frame ' + Math.round(app.store.frame), text: 'Sounds used by WickedWhims animations, and the game\'s own voice lines. "In your Mods" and "game" sounds play with your current Mods folder.',
    body: h('div', {}, h('div', { class: 'grid-2' }, kindSel, filter), chips, h('div', { style: { height: '8px' } }), list), buttons: [{ label: 'Close', kind: 'ghost' }] });
  render();
  // the game's lines arrive a moment after start: show them when they do
  if (!app.voiceLines && app.voicesReady) app.voicesReady.then(() => { if (list.isConnected && kindSel.value === 'game') render(); });
}
