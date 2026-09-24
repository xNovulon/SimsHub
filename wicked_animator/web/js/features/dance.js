// Strip-club dances (R3-4): a pole dance, a dance on WickedWhims' dance spot or a lap dance, timed to a song.
//
//   "Make a strip-club dance" (Home card, Ctrl+K): the kind of dance, who dances, and the tempo - from a song dropped
//     in (its beat is found on this PC by web/js/beat.js; the song never leaves the PC and never goes into the mod),
//     by tapping along, or typed. The loop is a whole number of beats (16 = four bars) as whole frames, so it never
//     drifts from the music when WickedWhims repeats it.
//   On the stage: WickedWhims' own pole or dance spot (/api/dance_pole, /api/dance_spot - a stand-in of the same size
//     when WickedWhims isn't on this PC), a Beats row on the timeline, and the song playing along while it plays.
//   Share step: the dance's settings and "Send dance to game" / "Export as a mod" / "Show the XML" (/api/dance_export:
//     the dancer's clip, the watcher's for a lap dance, and WickedWhims' StripClubDanceAnimationPackage XML).
// The dance settings live in project.dance ({type, dancer, watcher, genders, loops, set, order, bpm, beats}).
import * as THREE from 'three';
import { h, icon, modal, toast, section, addIcon, slider } from '../ui.js';
import { newProject, newSim, localStorageGet } from '../state.js';
import { newLayer } from '../motion.js';
import { hideHome } from '../home.js';
import { fetchJson, plainError } from '../gamehelp.js';
import * as B from '../beat.js';
import { $t } from '../i18n.js';

const ICONS = {
  'dance-pole': '<path d="M12 2.5v19" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M8.5 21.5h7" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="16.8" cy="6.2" r="1.7" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M12.4 9.2c2.2.2 3.8 1 4.4 2.6l-1.4 3.4 2 4.2M15.8 12.2l-3.4 1.8" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
  'dance-tap': '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="12" r="3.2" fill="currentColor"/>',
};
export const TYPES = [
  ['POLE_DANCE', $t('features.dance.pole_dance'), $t('features.dance.on_wickedwhims_dance_pole')],
  ['SPOT_DANCE', $t('features.dance.dance_spot'), $t('features.dance.on_wickedwhims_stage_mark')],
  ['LAP_DANCE', $t('features.dance.lap_dance'), $t('features.dance.for_sim_sitting_on_seat')],
];
const TYPE_LABEL = Object.fromEntries(TYPES.map(([k, l]) => [k, l]));
const MOVES = [['sway', $t('features.dance.sway')], ['twerk', $t('features.dance.twerk')], ['grind', $t('features.dance.grind')], ['none', $t('features.dance.keep_still_pose_it_yourself')]];
const SEATS = [['chair_living', $t('features.dance.armchair')], ['chair_dining', $t('features.dance.dining_chair')], ['loveseat', $t('features.dance.loveseat')], ['sofa', $t('features.dance.sofa')]];
const song = { buffer: null, name: '', bpm: 0, offset: 0, confidence: 0, src: null, startedAt: 0, on: true };

// ---------------------------------------------------------------- the new-dance window
export function openNewDance(app) {
  const st = { type: 'POLE_DANCE', gender: 'FEMALE', both: false, seat: 'chair_living', move: 'sway', bpm: 120, beats: 16, loops: 4, set: '', found: null };
  const tap = new B.TapTempo();
  const typeRow = h('div', { class: 'tiles three dn-types' });
  const drawTypes = () => {
    typeRow.innerHTML = '';
    for (const [k, label, sub] of TYPES) typeRow.append(h('button', { class: 'tile' + (st.type === k ? ' on' : ''), type: 'button', 'data-type': k,
      onclick: () => { st.type = k; drawTypes(); seatBox.classList.toggle('hidden', k !== 'LAP_DANCE'); } }, h('b', {}, label), h('small', {}, sub)));
  };
  const who = h('select', { 'aria-label': $t('features.dance.who_dances') }, h('option', { value: 'FEMALE' }, $t('features.dance.woman')), h('option', { value: 'MALE' }, $t('features.dance.man')));
  who.onchange = () => { st.gender = who.value; };
  const both = h('label', { class: 'check', title: $t('features.dance.wickedwhims_own_list_names_most') },
    h('input', { type: 'checkbox', onchange: e => { st.both = e.target.checked; } }), $t('features.dance.women_and_men_can_dance'));
  const seat = h('select', { 'aria-label': $t('features.dance.seat') }, SEATS.map(([v, t]) => h('option', { value: v }, t)));
  seat.onchange = () => { st.seat = seat.value; };
  const seatBox = h('label', { class: 'field hidden' }, h('span', {}, $t('features.dance.watcher_sits_on')), seat);
  const move = h('select', { 'aria-label': $t('features.dance.starting_moves') }, MOVES.map(([v, t]) => h('option', { value: v }, t)));
  move.onchange = () => { st.move = move.value; };
  // tempo
  const bpmIn = h('input', { type: 'number', min: 40, max: 240, step: 0.1, value: st.bpm, class: 'text dn-bpm', 'aria-label': $t('features.dance.beats_per_minute') });
  const beatsSel = h('select', { 'aria-label': $t('features.dance.beats_per_loop') }, [[8, $t('features.dance.8_beats_2_bars')], [16, $t('features.dance.16_beats_4_bars')], [32, $t('features.dance.32_beats_8_bars')]].map(([v, t]) => h('option', { value: v, selected: v === st.beats }, t)));
  const loopInfo = h('div', { class: 'hint dn-loop', role: 'status', 'aria-live': 'polite' });
  const songInfo = h('div', { class: 'hint dn-song' }, song.buffer ? `Song: ${song.name} (${song.bpm} BPM)` : $t('features.dance.no_song_type_tempo_tap'));
  const fileIn = h('input', { type: 'file', accept: 'audio/*', class: 'hidden' });
  const tapBtn = h('button', { class: 'btn small', type: 'button', title: $t('features.dance.tap_along_with_music_3') }, icon('dance-tap'), $t('features.dance.tap_beat'));
  const drop = h('div', { class: 'dn-drop' }, h('button', { class: 'btn small', type: 'button', onclick: () => fileIn.click() }, icon('sound'), $t('features.dance.pick_song')), tapBtn, songInfo);
  const showLoop = () => {
    const ph = B.phrase(+bpmIn.value || 120, { fps: 30, beats: st.beats });
    loopInfo.textContent = $t('features.dance.one_loop_beats_frames_s', { beats: ph.beats, frames: ph.frames, frames2: (ph.frames / 30).toFixed(2), bpm: ph.bpm, loops: st.loops, loops2: (st.loops * ph.frames / 30).toFixed(0) });
  };
  bpmIn.addEventListener('input', () => { st.bpm = +bpmIn.value || 120; showLoop(); });
  beatsSel.addEventListener('change', () => { st.beats = +beatsSel.value; showLoop(); });
  tapBtn.addEventListener('click', () => {
    const b = tap.tap(performance.now());
    tapBtn.classList.add('on'); setTimeout(() => tapBtn.classList.remove('on'), 90);
    if (b) { st.bpm = b; bpmIn.value = b; showLoop(); songInfo.textContent = $t('features.dance.tapped_bpm', { bpm: b }); }
    else songInfo.textContent = $t('features.dance.keep_tapping_along');
  });
  const useSong = async file => {
    if (!file) return;
    songInfo.textContent = $t('features.dance.listening_to', { fileName: file.name });
    try {
      const r = await B.findBeat(file);
      if (!r.bpm) { songInfo.textContent = $t('features.dance.no_steady_beat_found_in', { fileName: file.name }); return; }
      Object.assign(song, { buffer: r.buffer, name: file.name, bpm: r.bpm, offset: r.offset, confidence: r.confidence });
      st.bpm = r.bpm; bpmIn.value = r.bpm; showLoop();
      songInfo.textContent = $t(r.confidence < 0.3 ? 'features.dance.song_bpm_unsure' : 'features.dance.song_bpm', { name: file.name, bpm: r.bpm });
    } catch (e) {
      songInfo.textContent = $t('features.dance.that_file_could_not_be', { message: e.message || e });
    }
  };
  fileIn.addEventListener('change', () => useSong(fileIn.files && fileIn.files[0]));
  drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('over'); useSong(e.dataTransfer.files && e.dataTransfer.files[0]); });
  const loops = slider({ label: $t('features.dance.plays_in_row'), min: 1, max: 12, step: 1, value: st.loops, fmt: v => v + 'x', onInput: v => { st.loops = v; showLoop(); } });
  const setIn = h('input', { type: 'text', maxlength: 60, class: 'text', placeholder: $t('features.dance.e_g_neon_nights_optional'), 'aria-label': $t('features.dance.routine_name') });
  setIn.addEventListener('input', () => { st.set = setIn.value; });
  drawTypes();
  showLoop();
  const dlg = modal({
    title: $t('features.dance.make_strip_club_dance'), wide: true,
    text: $t('features.dance.for_wickedwhims_strip_clubs_pick'),
    body: h('div', { class: 'dn' },
      typeRow,
      h('div', { class: 'grid-2 dn-grid' },
        h('label', { class: 'field' }, h('span', {}, $t('features.dance.who_dances')), who), h('label', { class: 'field' }, h('span', {}, $t('features.dance.starting_moves')), move)),
      both, seatBox,
      section($t('features.dance.tempo'), drop, fileIn,
        h('div', { class: 'grid-2 dn-grid' }, h('label', { class: 'field' }, h('span', {}, $t('features.dance.beats_per_minute')), bpmIn), h('label', { class: 'field' }, h('span', {}, $t('features.dance.loop')), beatsSel)),
        loops, loopInfo),
      h('label', { class: 'field' }, h('span', {}, $t('features.dance.part_of_routine_dances_with')), setIn)),
    buttons: [
      { label: $t('features.dance.cancel'), kind: 'ghost' },
      { label: $t('features.dance.make_dance'), kind: 'primary', onClick: () => { makeDance(app, st); } },
    ],
  });
  dlg.dialog.classList.add('dn-modal');
  return dlg;
}

// A new dance project from the window's choices.
export function makeDance(app, st) {
  const ph = B.phrase(st.bpm || 120, { fps: 30, beats: st.beats || 16 });
  const p = newProject();
  const lap = st.type === 'LAP_DANCE';
  p.name = TYPE_LABEL[st.type] || 'Dance';
  p.author = localStorageGet('author', '') || p.author;
  p.category = 'TEASING';
  p.tags = ['DANCE'];
  p.length = ph.frames;
  p.loops = Math.max(1, Math.min(99, st.loops | 0 || 4));
  p.furniture = lap ? (st.seat || 'chair_living') : 'floor';
  const furn = (app.furniture || []).find(f => f.id === p.furniture);
  p.locations = furn ? [...furn.locations] : ['FLOOR'];
  const dancerFrame = st.gender === 'MALE' ? 'ym' : 'yf';
  p.sims.push(newSim(p, dancerFrame));
  if (lap) p.sims.push(newSim(p, dancerFrame === 'ym' ? 'yf' : 'ym'));
  p.dance = { type: st.type, dancer: 0, watcher: lap ? 1 : null, genders: st.both ? ['FEMALE', 'MALE'] : [st.gender === 'MALE' ? 'MALE' : 'FEMALE'],
    loops: p.loops, set: (st.set || '').trim(), order: 1, bpm: ph.bpm, beats: ph.beats };
  app.store.load(p);
  app.store.selected.sim = p.sims[0].id;
  app.playRange = null;
  app.pipeline.overrides.clear();
  app._lastPreset = null;
  app._file = null;
  // where they stand: the dancer 35 cm in front of the pole (facing it), on the spot's middle, or in front of the seat
  // facing the watcher; the watcher stands by the seat (the Place tool's seat marker sits them down)
  app.syncViews();
  p.sims.forEach((s, k) => {
    const v = app.simViews.get(s.id);
    if (!v) return;
    v.resetPose();
    if (k === 0 && st.type === 'POLE_DANCE') app.interact.moveHips(v, new THREE.Vector3(0, 0, -0.35));
    if (k === 0 && lap) { app.interact.moveHips(v, new THREE.Vector3(0, 0, 0.75)); app.interact.turnHips(v, Math.PI, new THREE.Vector3(0, 0, 0.75)); }
    s.keys.push({ frame: 0, ease: 'auto', pose: app._bodyPose(v) });
  });
  // starting moves, one per two beats (a whole number per loop, so the loop joins up)
  const dancer = p.sims[0];
  if (st.move && st.move !== 'none') {
    const l = newLayer(st.move);
    if (l.params.strokes !== undefined) l.params.strokes = Math.max(1, Math.round(ph.beats / 2));
    dancer.layers.push(l);
  }
  for (const s of p.sims) s.layers.push(newLayer('breathe'));
  app.buildFurniture();
  app.store.setDirty(true);
  hideHome(app);
  app.showStep('motion');
  app.refreshAll();
  app.frameSims({ fromFront: true });
  app.timeline.fit();
  app._projectLoaded();
  toast($t('features.dance.made', { name: p.name, beats: ph.beats, bpm: ph.bpm }) + (lap ? $t('features.dance.seat_watcher_with_place_tool') : ''), 'ok');
  return p;
}

// ---------------------------------------------------------------- the pole or the spot on the stage
class DanceStage {
  constructor(app) {
    this.app = app;
    this.group = new THREE.Group();
    this.group.name = 'dance-object';
    app.vp.scene.add(this.group);
    this.kind = null;
    this.info = null;
    this.standIn = false;
  }
  async show(kind) {
    if (kind === this.kind) return;
    this.kind = kind;
    this.group.clear();
    this.standIn = false;
    if (!kind) return;
    const route = kind === 'POLE_DANCE' ? '/api/dance_pole' : '/api/dance_spot';
    let obj = null;
    try { obj = await fetchJson(route); } catch { obj = null; }
    if (this.kind !== kind) return;
    if (obj && obj.meshes && obj.meshes.length) this.group.add(meshGroup(obj));
    else {
      // WickedWhims isn't on this PC: a stand-in of the same size where the real one stands
      this.standIn = true;
      if (!this.info) { try { this.info = await fetchJson('/api/dance_info'); } catch { this.info = null; } }
      const mat = new THREE.MeshStandardMaterial({ color: 0xd9d4e3, roughness: 0.25, metalness: 0.8 });
      if (kind === 'POLE_DANCE') {
        const b = (this.info && this.info.pole && this.info.pole.bounds) || { min: [-0.06, 0, -0.06], max: [0.06, 2.91, 0.06] };
        const r = Math.max(0.02, (b.max[0] - b.min[0]) / 2), hgt = Math.max(1, b.max[1] - b.min[1]);
        const pole = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.7, r * 0.7, hgt, 24), mat);
        pole.position.set((b.max[0] + b.min[0]) / 2, b.min[1] + hgt / 2, (b.max[2] + b.min[2]) / 2);
        const base = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.32, 0.04, 32), mat);
        base.position.y = 0.02;
        this.group.add(pole, base);
      } else {
        const ring = new THREE.Mesh(new THREE.RingGeometry(0.45, 0.5, 48), new THREE.MeshBasicMaterial({ color: 0xff4f9a, transparent: true, opacity: 0.7, side: THREE.DoubleSide }));
        ring.rotation.x = -Math.PI / 2; ring.position.y = 0.005;
        this.group.add(ring);
      }
    }
  }
}
function meshGroup(obj) {
  const g = new THREE.Group();
  const loader = new THREE.TextureLoader();
  for (const m of obj.meshes) {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(m.positions, 3));
    if (m.normals && m.normals.length) geo.setAttribute('normal', new THREE.Float32BufferAttribute(m.normals, 3));
    if (m.uvs && m.uvs.length) geo.setAttribute('uv', new THREE.Float32BufferAttribute(m.uvs, 2));
    geo.setIndex(m.faces);
    if (!m.normals || !m.normals.length) geo.computeVertexNormals();
    const mat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.4, metalness: 0.3, side: THREE.DoubleSide, transparent: !!m.transparent, opacity: m.transparent ? 0.6 : 1 });
    if (m.texture) { const t = loader.load('/api/furniture_tex?file=' + encodeURIComponent(m.texture)); t.colorSpace = THREE.SRGBColorSpace; t.flipY = !!m.flipY; mat.map = t; }
    const mesh = new THREE.Mesh(geo, mat);
    mesh.castShadow = true; mesh.receiveShadow = true;
    g.add(mesh);
  }
  return g;
}

// ---------------------------------------------------------------- the song playing along
function songStop() {
  if (song.src) { try { song.src.stop(); } catch { /* stopped */ } song.src = null; }
}
function songPlay(app) {
  songStop();
  const p = app.store.project;
  if (!song.buffer || !song.on || !p.dance || !app.playing || (app.audio && app.audio.muted)) return;
  const ctx = app.audio && app.audio.ensure ? (app.audio.ensure(), app.audio.ctx) : null;
  if (!ctx) return;
  const src = ctx.createBufferSource();
  src.buffer = song.buffer;
  src.connect(app.audio.master || ctx.destination);
  // the first beat of the song is the loop's frame 0
  const at = (song.offset + app.store.frame / (p.fps || 30)) % Math.max(1, song.buffer.duration);
  src.start(0, at);
  song.src = src;
}

// ---------------------------------------------------------------- sending the dance
async function sendDance(app, mode) {
  const p = app.store.project;
  if (!p.dance) return null;
  const baked = { ...app.bake(), dance: { ...p.dance } };
  let r;
  try { r = await fetchJson('/api/dance_export', { body: { baked, mode } }); }
  catch (e) { toast((e.status === 404 && /unknown api/i.test(e.message)) ? plainError(e) : $t('features.dance.dance_could_not_be_made', { message: e.message }), 'err'); return null; }
  if (mode === 'check') {
    modal({ title: $t('features.dance.dance_for_wickedwhims'), wide: true,
      text: $t('features.dance.clips_s_loop_x_s', { package: r.package, clipCount: r.clips.length, seconds: r.seconds.toFixed(2), loops: r.loops, total_seconds: r.total_seconds, bytes: Math.round(r.bytes / 1024) }),
      body: h('pre', { class: 'dn-xml' }, r.xml || ''), buttons: [{ label: 'OK', kind: 'primary' }] });
    return r;
  }
  if (r.fake) { toast($t('features.dance.checked_test_mode_nothing_was'), 'ok'); return r; }
  const where = mode === 'mod' ? $t('features.dance.saved_in_share_that_folder', { folder: r.folder }) : $t('features.dance.in_your_mods_folder_restart', { package: r.package });
  modal({ title: mode === 'mod' ? $t('features.dance.exported_as_mod') : $t('features.dance.sent_to_your_game'), text: where,
    body: h('ul', { class: 'rf-report' }, h('li', {}, $t('features.dance.type_for', { type: TYPE_LABEL[r.type] || r.type, who: r.genders.every(g => g === 'FEMALE') ? $t('features.dance.for_women') : r.genders.every(g => g !== 'FEMALE') ? $t('features.dance.for_men') : $t('features.dance.for_women_and_men') })),
      h('li', {}, $t('features.dance.s_loop_x_in_row', { seconds: r.seconds.toFixed(2), loops: r.loops, total_seconds: r.total_seconds })),
      r.set ? h('li', {}, $t('features.dance.part_of_routine', { set: r.set })) : null,
      (r.replaced || []).length ? h('li', {}, $t('features.dance.older_copy_under_another_name', { replaced: r.replaced.join(', ') })) : null),
    buttons: [{ label: 'OK', kind: 'primary' }] });
  return r;
}

// the Share step: the dance's settings and the buttons
function danceSection(app, root) {
  const p = app.store.project, d = p.dance;
  if (!d) return;
  const change = fn => { app.store.checkpoint('Dance'); fn(); app.store.setDirty(true); app.renderStep(); };
  const type = h('select', { 'aria-label': $t('features.dance.kind_of_dance') }, TYPES.map(([k, l]) => h('option', { value: k, selected: d.type === k }, l)));
  type.onchange = () => change(() => {
    d.type = type.value;
    if (d.type === 'LAP_DANCE' && p.sims.length < 2) toast($t('features.dance.lap_dance_needs_second_sim'));
    d.watcher = d.type === 'LAP_DANCE' ? (d.dancer === 0 ? 1 : 0) : null;
  });
  const genders = h('select', { 'aria-label': $t('features.dance.who_can_dance_it') },
    [['FEMALE', $t('features.dance.women')], ['MALE', $t('features.dance.men')], [$t('features.dance.female_male'), $t('features.dance.women_and_men')]].map(([v, t]) => h('option', { value: v, selected: (d.genders || []).join(',') === v }, t)));
  genders.onchange = () => change(() => { d.genders = genders.value.split(','); });
  const loops = slider({ label: $t('features.dance.plays_in_row'), min: 1, max: 12, step: 1, value: d.loops || p.loops || 4, fmt: v => v + 'x',
    onInput: (v, done) => { d.loops = v; p.loops = v; if (done) app.store.setDirty(true); } });
  const setIn = h('input', { type: 'text', maxlength: 60, value: d.set || '', class: 'text', placeholder: $t('features.dance.routine_name_optional'), 'aria-label': $t('features.dance.routine_name') });
  setIn.onchange = () => change(() => { d.set = setIn.value.trim(); });
  const order = h('input', { type: 'number', min: 1, max: 20, value: d.order || 1, 'aria-label': $t('features.dance.place_in_routine'), class: 'text dn-order' });
  order.onchange = () => change(() => { d.order = Math.max(1, Math.min(20, +order.value || 1)); });
  const lapProblem = d.type === 'LAP_DANCE' && p.sims.length < 2;
  root.append(section([$t('features.dance.strip_club_dance'), h('span', { class: 'count' }, TYPE_LABEL[d.type] || '')],
    h('div', { class: 'grid-2 dn-grid' }, h('label', { class: 'field' }, h('span', {}, $t('features.dance.kind')), type), h('label', { class: 'field' }, h('span', {}, $t('features.dance.who_can_dance_it')), genders)),
    loops,
    h('div', { class: 'grid-2 dn-grid' }, h('label', { class: 'field' }, h('span', {}, $t('features.dance.routine')), setIn), h('label', { class: 'field' }, h('span', {}, $t('features.dance.its_place_in_it')), order)),
    lapProblem ? h('div', { class: 'hint warn' }, $t('features.dance.lap_dance_needs_second_sim')) : null,
    h('div', { class: 'btn-grid' },
      h('button', { class: 'btn small primary', type: 'button', 'data-dance': 'send', disabled: lapProblem, onclick: () => sendDance(app, 'send') }, icon('send'), $t('features.dance.send_dance_to_game')),
      h('button', { class: 'btn small', type: 'button', 'data-dance': 'mod', disabled: lapProblem, onclick: () => sendDance(app, 'mod') }, icon('package'), $t('features.dance.export_as_mod')),
      h('button', { class: 'btn small ghost', type: 'button', 'data-dance': 'check', disabled: lapProblem, onclick: () => sendDance(app, 'check') }, icon('eye'), $t('features.dance.show_xml'))),
    h('div', { class: 'hint' }, $t('features.dance.wickedwhims_plays_it_in_strip'))));
}

// the Motion step: the tempo, the beats and the song
function tempoSection(app, root) {
  const p = app.store.project, d = p.dance;
  if (!d) return;
  const ph = B.phrase(d.bpm || 120, { fps: p.fps || 30, beats: d.beats || 16 });
  const fits = ph.frames === p.length;
  const toggleSong = h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: song.on, onchange: e => { song.on = e.target.checked; if (song.on) songPlay(app); else songStop(); } }), $t('features.dance.play_song_with_it'));
  root.append(section([$t('features.dance.dance_tempo'), h('span', { class: 'count' }, $t('features.dance.n_bpm', { bpm: d.bpm }))],
    h('div', { class: 'hint' }, fits ? $t('features.dance.beats_loop_fits', { beats: d.beats || 16, secs: (ph.frames / (p.fps || 30)).toFixed(2) }) : $t('features.dance.beats_loop_off', { beats: d.beats || 16, pCount: p.length, frames: ph.frames })),
    fits ? null : h('button', { class: 'btn small soft', type: 'button', onclick: () => { app.store.checkpoint($t('features.dance.fit_loop_to_beat')); p.length = ph.frames; app.store.setDirty(true); app.refreshAll(); app.timeline.fit(); } }, icon('loop'), $t('features.dance.make_loop_frames', { frames: ph.frames })),
    song.buffer ? toggleSong : h('div', { class: 'hint' }, $t('features.dance.tip_make_strip_club_dance'))));
}

// the Beats row on the timeline: a tick on every beat, a bigger one on every bar
function beatsRow(app) {
  return {
    id: 'dance-beats', height: 16, order: 5, label: $t('features.dance.beats'),
    draw(g, ctx) {
      const d = app.store.project.dance;
      if (!d) return;
      const { x0, x1, y, h: hh, xAt } = ctx;
      const beats = d.beats || 16, frames = app.store.project.length;
      B.beatFrames(frames, beats).forEach((f, k) => {
        const x = Math.round(xAt(f)) + 0.5;
        if (x < x0 || x > x1) return;
        const bar = k % 4 === 0;
        g.fillStyle = bar ? 'rgba(255,79,154,0.95)' : 'rgba(255,255,255,0.35)';
        g.fillRect(x - (bar ? 1 : 0.5), y + (bar ? 2 : 5), bar ? 2 : 1, hh - (bar ? 4 : 10));
      });
    },
  };
}

// ---------------------------------------------------------------- plug in
export function install(app) {
  if (!app || app.__dance) return;
  app.__dance = true;
  for (const [id, svg] of Object.entries(ICONS)) addIcon(id, svg);
  const hooks = app.hooks || {};
  const add = (name, fn) => { const list = name.split('.').reduce((o, k) => o && o[k], hooks); if (Array.isArray(list)) list.push(fn); };
  const stage = new DanceStage(app);
  let unRow = null;
  const refresh = () => {
    const d = app.store.project.dance;
    stage.show(d ? (d.type === 'LAP_DANCE' ? null : d.type) : null);
    if (d && !unRow && app.timeline && typeof app.timeline.addRow === 'function') unRow = app.timeline.addRow(beatsRow(app));
    if (!d && unRow) { unRow(); unRow = null; }
    if (!d) songStop();
  };

  add('homeCards', a => [{ id: 'dance', icon: 'dance-pole', title: $t('features.dance.strip_club_dance'),
    text: $t('features.dance.pole_dance_dance_spot_or'), onClick: () => openNewDance(a) }]);
  add('commands', a => [
    { group: $t('features.dance.actions'), id: 'dance-new', label: $t('features.dance.make_strip_club_dance'), icon: 'dance-pole', sub: $t('features.dance.pole_dance_spot_or_lap'),
      words: 'dance pole stripper strip club lap dance spot stage music song beat tempo bpm', run: () => openNewDance(a) },
    { group: $t('features.dance.share'), id: 'dance-send', label: $t('features.dance.send_dance_to_game'), icon: 'send', sub: $t('features.dance.wickedwhims_strip_clubs'), words: 'dance export strip club pole package',
      run: () => sendDance(a, 'send'), when: () => !!a.store.project.dance },
  ]);
  add('helpRows', () => [{ group: $t('features.dance.making_animations'), keys: ['Ctrl', 'K'], text: $t('features.dance.type_dance_to_make_pole') }]);
  add('sections.share', (a, root) => danceSection(a, root));
  add('sections.motion', (a, root) => tempoSection(a, root));
  add('projectLoaded', () => refresh());
  add('viewsSynced', () => refresh());        // Magic and Say it load a new animation without "projectLoaded"
  add('exportChecks', p => (p.dance ? [{ level: 'warn', text: $t('features.dance.this_is_strip_club_dance') }] : []));
  add('playing', on => { if (on) songPlay(app); else songStop(); });
  add('tick', (dt, frame, { playing, wrapped } = {}) => { if (playing && wrapped && song.src) songPlay(app); });
  refresh();
  window.wickedDance = { open: () => openNewDance(app), make: st => makeDance(app, st), send: mode => sendDance(app, mode), song, stage };
}

export default install;
