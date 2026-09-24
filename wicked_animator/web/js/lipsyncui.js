// The Face step's "Lip-sync from a sound" card: lip-sync the sim's voice sounds in one click, pick a game voice line,
// or drop your own sound file (WAV, MP3, OGG). The work itself is in lipsync.js.
import { h, icon, slider, toggleRow, section, toast } from './ui.js';
import { lipSync, lipSyncVoices, decodeSound, voiceOf, voiceLineUrl } from './lipsync.js';
import { uploadMySound } from './mysounds.js';
import { $t } from './i18n.js';

const TAGS = [['moan', $t('lipsyncui.moans')], ['woohoo', $t('lipsyncui.woohoo')], ['climax', $t('lipsyncui.climax')], ['breath', $t('lipsyncui.breathing')], ['kiss', $t('lipsyncui.kisses')], ['flirt', $t('lipsyncui.flirty')], ['laugh', $t('lipsyncui.laughs')], ['pain', $t('lipsyncui.pain')], ['', $t('lipsyncui.all')]];

// A voice line's plain name: "vo_expr_moan_pleasure_30f_cm" -> "moan pleasure".
export function prettyLine(name) {
  const w = String(name || '').replace(/^voe?_/i, '').split('_')
    .filter(x => x && !/^\d+f$/i.test(x) && !/^(cm|cas|expr|lowprob|m|f|fa|fb|fc|fd|ma|mb|mc|md|x|y)$/i.test(x));
  return w.join(' ') || name;
}
const secOf = (s, fps) => `${(s / fps).toFixed(2)} s`;

// ---------------------------------------------------------------- the game's voice lines (loaded once, on demand)
let _lines = null, _linesP = null;
function loadLines() {
  if (_lines) return Promise.resolve(_lines);
  if (!_linesP) {
    _linesP = fetch('/api/voices').then(r => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status))))
      .then(d => (_lines = ((d && d.lines) || []).filter(l => l && /^voe?_/i.test(l.name || ''))))
      .catch(() => { _linesP = null; return null; });
  }
  return _linesP;
}

// one sound playing at a time (the listen buttons, and your own file along the animation)
let _audio = null, _ctx = null, _src = null;
function stopListening() {
  try { if (_audio) { _audio.pause(); _audio = null; } } catch { /* gone */ }
  try { if (_src) { _src.stop(); _src = null; } } catch { /* ended */ }
}
function listen(url) {
  stopListening();
  _audio = new Audio(url);
  _audio.play().catch(() => toast($t('lipsyncui.that_sound_could_not_be')));
}
// The lip-synced file as one of your own sounds, placed where the lip-sync starts (packed into every export).
async function fileToGame(app, sim, btn) {
  const f = app._lipFile;
  if (!f || !f.file) return;
  if (btn) btn.disabled = true;
  try {
    const s = await uploadMySound(f.file, 'voice');
    const target = app.store.sim(f.simId) || sim;
    app.store.checkpoint();
    target.sounds = target.sounds || [];
    if (!target.sounds.some(x => x.name === s.name && x.frame === f.frame)) target.sounds.push({ frame: f.frame, name: s.name, kind: 'voice' });
    app.afterEdit();
    toast($t('lipsyncui.plays_in_game_at_frame', { sLabel: s.label, frame: f.frame }), 'ok');
  } catch (err) {
    toast(err.message || String(err), 'err');
  } finally { if (btn && btn.isConnected) btn.disabled = false; }
}

// Your own file, played along the animation from where it was lip-synced (a preview: it is not part of the export).
export function playFileAlong(app) {
  const f = app._lipFile;
  if (!f || !f.buffer) return;
  stopListening();
  try {
    _ctx = _ctx || new (window.AudioContext || window.webkitAudioContext)();
    _ctx.resume && _ctx.resume();
    _src = _ctx.createBufferSource();
    _src.buffer = f.buffer;
    _src.connect(_ctx.destination);
    app.setFrame(f.frame);
    app.setPlaying(true);
    _src.start();
    _src.onended = () => { _src = null; };
  } catch (e) { console.error(e); }
}
export { stopListening };

async function run(app, sim, work, what) {
  if (app._lipBusy) return;
  app._lipBusy = true;
  app._lipStatus = { busy: true, text: $t('lipsyncui.listening_to', { what }) };
  app.renderStep();
  try {
    const r = await work();
    const list = Array.isArray(r) ? r : [{ result: r }];
    const ok = list.filter(x => x.result), bad = list.filter(x => x.error);
    const keys = ok.reduce((a, x) => a + x.result.keys, 0);
    const fps = app.store.project.fps || 30;
    const text = ok.length === 1
      ? $t('lipsyncui.mouth_follows_face_keys_from', { what, keys, secOf: secOf(ok[0].result.frame, fps), sec: ok[0].result.sec.toFixed(2) })
      : `The mouth follows ${ok.length} sounds: ${keys} face keys.`;
    app._lipStatus = { ok: ok.length > 0, text: ok.length ? text + (bad.length ? $t('lipsyncui.could_not_be_read', { badCount: bad.length }) : '') : (bad[0] && bad[0].error) || $t('lipsyncui.nothing_to_follow') };
    if (ok.length) toast(text, 'ok'); else toast(app._lipStatus.text);
  } catch (err) {
    app._lipStatus = { ok: false, text: String((err && err.message) || err) };
    toast(app._lipStatus.text);
  } finally {
    app._lipBusy = false;
    if (app.step === 'face') app.renderStep();
  }
}

export function lipSyncPanel(app, sim) {
  const p = app.store.project, fps = p.fps || 30, frame = Math.round(app.store.frame);
  const opts = () => ({ strength: app._lipStrength ?? 1, brows: app._lipBrows !== false });
  const voices = (sim.sounds || []).filter(x => x.kind === 'voice');
  const todo = voices.filter(x => !x.lipsync);
  const sec = section([$t('lipsyncui.lip_sync_from_sound'), h('span', { class: 'count' }, $t('lipsyncui.mouth_follows_it'))]);
  sec.classList.add('lipsync');
  sec.append(h('div', { class: 'hint', style: { marginTop: 0 } }, $t('lipsyncui.loud_opens_mouth_bright_sounds')));

  // 1. the sim's own voice sounds, in one click
  if (voices.length) {
    sec.append(h('button', { class: 'btn primary block ls-go', disabled: app._lipBusy ? true : null,
      onclick: () => run(app, sim, () => lipSyncVoices(app, sim.id, { ...opts(), all: !todo.length }), todo.length === 1 || voices.length === 1 ? $t('lipsyncui.voice_sound') : $t('lipsyncui.voice_sounds')) },
    icon('mic'), todo.length ? $t(todo.length === voices.length ? 'lipsyncui.lip_sync_n' : 'lipsyncui.lip_sync_other_n', { n: todo.length }) : $t('lipsyncui.lip_sync_voice_sounds_again')));
    sec.append(h('div', { class: 'ls-cues' }, voices.slice(0, 8).map(c => h('button', {
      class: 'ls-cue' + (c.lipsync ? ' done' : ''), title: $t('lipsyncui.at_click_to_lip_sync', { cName: c.name, secOf: secOf(c.frame, fps) }),
      onclick: () => run(app, sim, () => lipSync(app, sim.id, { name: c.name }, { ...opts(), frame: c.frame }), prettyLine(c.name)) },
    h('span', { class: 'dot' }), h('b', {}, prettyLine(c.name)), h('span', { class: 't' }, secOf(c.frame, fps)), c.lipsync ? icon('check') : null)),
    voices.length > 8 ? h('div', { class: 'hint' }, $t('lipsyncui.and_more', { voiceCount: voices.length - 8 })) : null));
  } else {
    sec.append(h('div', { class: 'hint' }, $t('lipsyncui.this_sim_has_no_voice')));
  }

  // 2. a game voice line, put at the playhead (it becomes one of the sim's voice sounds: it plays in the game too)
  const lineBox = h('details', { class: 'ls-box', open: app._lipLinesOpen ? true : null, ontoggle: e => { app._lipLinesOpen = e.currentTarget.open; if (e.currentTarget.open) fillLines(); } },
    h('summary', {}, icon('sound'), $t('lipsyncui.game_voice_line'), h('span', { class: 'fm-sub' }, `at ${secOf(frame, fps)}`)));
  const tag = app._lipTag ?? 'moan';
  const find = h('input', { class: 'text', type: 'search', placeholder: $t('lipsyncui.find_voice_line_moan_sigh'), value: app._lipQuery || '', spellcheck: 'false' });
  const chips = h('div', { class: 'gf-groups' }, TAGS.map(([id, text]) => h('button', { class: 'chip' + (tag === id ? ' on' : ''),
    onclick: e => { app._lipTag = id; const me = e.currentTarget; chips.querySelectorAll('.chip').forEach(c => c.classList.toggle('on', c === me)); fillLines(); } }, text)));
  const list = h('div', { class: 'ls-lines' }, h('div', { class: 'hint' }, $t('lipsyncui.loading_game_s_voice_lines')));
  lineBox.append(h('div', { class: 'gf-find' }, icon('search'), find), chips, list);
  const voice = voiceOf(sim);
  function fillLines() {
    loadLines().then(lines => {
      if (!list.isConnected && !lineBox.open) return;
      list.innerHTML = '';
      if (!lines) { list.append(h('div', { class: 'hint' }, $t('lipsyncui.game_s_voice_lines_could'))); return; }
      const q = (app._lipQuery || '').toLowerCase().split(/\s+/).filter(Boolean), t = app._lipTag ?? 'moan';
      const hits = lines.filter(l => (l.voices || []).includes(voice) && !l.lowprob && (t ? (l.tags || []).includes(t) : (l.tags || []).length || q.length)
        && q.every(w => l.name.toLowerCase().includes(w))).slice(0, 60);
      if (!hits.length) { list.append(h('div', { class: 'hint' }, $t('lipsyncui.no_voice_line_matches'))); return; }
      for (const l of hits) {
        list.append(h('div', { class: 'ls-line' },
          h('button', { class: 'icon-btn', title: $t('lipsyncui.listen_in_this_sim_s'), onclick: () => listen(voiceLineUrl(l.name, voice)) }, icon('play')),
          h('span', { class: 'nm', title: l.name }, prettyLine(l.name), h('small', {}, l.sec ? `${(+l.sec).toFixed(1)} s` : '')),
          h('button', { class: 'btn small', disabled: app._lipBusy ? true : null, title: $t('lipsyncui.add_it_at_playhead_and'),
            onclick: () => run(app, sim, () => lipSync(app, sim.id, { name: l.name }, { ...opts(), frame: Math.round(app.store.frame) }), prettyLine(l.name)) }, $t('lipsyncui.use'))));
      }
    });
  }
  find.addEventListener('input', () => { app._lipQuery = find.value; fillLines(); });
  if (lineBox.open) fillLines();
  sec.append(lineBox);

  // 3. your own sound file: the face follows it; "Play it in the game too" packs the file itself (mysounds.js)
  const input = h('input', { type: 'file', accept: 'audio/*,.wav,.mp3,.ogg', hidden: true });
  const useFile = async file => {
    if (!file) return;
    const at = Math.round(app.store.frame);
    await run(app, sim, async () => {
      const buffer = await decodeSound(file);
      const r = await lipSync(app, sim.id, { buffer, file }, { ...opts(), frame: at });
      app._lipFile = { name: file.name, buffer, frame: at, simId: sim.id, file };
      return r;
    }, file.name);
  };
  input.addEventListener('change', () => useFile(input.files && input.files[0]));
  const drop = h('button', { class: 'ls-drop', type: 'button', onclick: () => input.click(), title: $t('lipsyncui.wav_mp3_or_ogg') },
    icon('mic'), h('span', {}, h('b', {}, $t('lipsyncui.drop_sound_file_here')), h('small', {}, $t('lipsyncui.or_click_to_choose_wav'))));
  drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('over'); useFile(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]); });
  const fileBox = h('details', { class: 'ls-box', open: app._lipFileOpen ? true : null, ontoggle: e => { app._lipFileOpen = e.currentTarget.open; } },
    h('summary', {}, icon('folder'), $t('lipsyncui.your_own_sound_file'), h('span', { class: 'fm-sub' }, `at ${secOf(frame, fps)}`)),
    drop, input,
    app._lipFile && app._lipFile.simId === sim.id ? h('button', { class: 'btn small block', onclick: () => playFileAlong(app) }, icon('play'), $t('lipsyncui.hear_with_animation', { _lipFileName: app._lipFile.name })) : null,
    app._lipFile && app._lipFile.simId === sim.id && app._lipFile.file ? h('button', { class: 'btn small block ls-to-game', onclick: e => fileToGame(app, sim, e.currentTarget) }, icon('wave'), $t('lipsyncui.play_this_sound_in_game')) : null,
    h('div', { class: 'hint' }, $t('lipsyncui.face_follows_file_to_hear')));
  sec.append(fileBox);

  // how strong
  sec.append(slider({ label: $t('lipsyncui.how_wide_mouth_opens'), min: 0.5, max: 1.5, step: 0.05, value: app._lipStrength ?? 1, fmt: v => Math.round(v * 100) + '%',
    title: $t('lipsyncui.for_next_lip_sync'), onInput: v => { app._lipStrength = v; } }),
  toggleRow($t('lipsyncui.brows_and_eyes_follow_loud'), $t('lipsyncui.worried_brows_and_half_closed'), app._lipBrows !== false, on => { app._lipBrows = on; }));
  if (app._lipStatus) sec.append(h('div', { class: 'ls-status' + (app._lipStatus.busy ? ' busy' : app._lipStatus.ok ? ' ok' : ' bad') }, app._lipStatus.busy ? h('span', { class: 'gf-spin' }) : icon(app._lipStatus.ok ? 'check' : 'x'), h('span', {}, app._lipStatus.text)));
  return sec;
}
