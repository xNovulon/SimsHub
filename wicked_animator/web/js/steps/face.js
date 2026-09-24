// Step 5, Face: pose the face by hand (the Face tool and the face map), expressions (one-click and the game's own
// faces), lip-sync from a sound, face keys, sliders on top, talking and blinking.
import { h, icon, slider, toggleRow, section } from '../ui.js';
import { simBody } from '../pipeline.js';
import { evaluateFace } from '../animation.js';
import { localStorageGet, localStorageSet } from '../state.js';
import { simTabs } from './common.js';
import { FACE_SLIDERS, FACE_PRESETS, REGIONS, REGION_LABEL, regionColor } from '../facekit.js';
import { faceMap } from '../facemap2d.js';
import { gameFacesPanel, facesNow } from '../gamefaces.js';
import { lipSyncPanel } from '../lipsyncui.js';
import { $t } from '../i18n.js';

// two-way sliders say both ends (the eyes one goes a little past open: wide eyes)
const FACE_LABEL = { eyes: $t('steps.face.eyes_wide_closed') };
const EMOJI = { neutral: '😐', relaxed: '😌', smile: '😊', seductive: '😏', pleasure: '😣', moan: '😮', ecstasy: '😫', bite: '🫦', surprised: '😲', intense: '😖', tongue: '😛', ahegao: '🤪', kiss: '😘', sleepy: '😑' };

export function renderFace(app, root) {
  const sim = app.store.sim();
  if (!sim) { root.append(h('div', { class: 'empty' }, $t('steps.face.select_sim_first'))); return; }
  root.append(simTabs(app));
  const p = app.store.project;
  const f = Math.round(app.store.frame);
  const key = sim.keys.find(k => k.frame === f);
  const cur = (key && key.face) || evaluateFace(sim.keys, f, p.length, p.loop) || {};
  const view = app.simViews && app.simViews.get(sim.id);

  // ---- pose the face by hand (+ the face map: the same dots on a flat, always upright face)
  const faceTool = app.interact && app.interact.tool === 'face';
  const mapOpen = localStorageGet('faceMapOpen', true) !== false;
  const map = h('details', { class: 'face-map-box', open: mapOpen ? true : null,
    ontoggle: e => { localStorageSet('faceMapOpen', e.currentTarget.open); } },
    h('summary', {}, icon('face'), $t('steps.face.face_map'), h('span', { class: 'fm-sub' }, $t('steps.face.always_upright'))));
  const mapEl = view ? faceMap(app, sim, view) : null;
  if (mapEl) map.append(mapEl);
  root.append(section($t('steps.face.pose_face_by_hand'),
    h('button', { class: 'btn primary block big face-go' + (faceTool ? ' on' : ''), onclick: () => app.setTool('face'),
      title: $t('steps.face.pose_face_brows_eyes_lids') }, icon('face'), faceTool ? $t('steps.face.posing_face_click_dot') : $t('steps.face.pose_face')),
    h('div', { class: 'face-legend' }, REGIONS.map(r => h('span', { class: 'chip', style: { '--c': regionColor(r) } }, h('i', {}), REGION_LABEL[r]))),
    h('div', { class: 'hint' }, $t('steps.face.click_dot_on_face_and')),
    mapEl ? map : null));

  // ---- expressions: one-click faces, or the game's own faces
  const tab = app._faceTab || localStorageGet('faceTab', 'quick');
  const setTab = t => { app._faceTab = t; localStorageSet('faceTab', t); app.renderStep(); };
  const n = (facesNow() || []).length;
  const tabs = h('div', { class: 'seg-inline face-tabs', role: 'tablist' },
    h('button', { class: tab !== 'game' ? 'on' : '', role: 'tab', 'aria-selected': String(tab !== 'game'), onclick: () => setTab('quick') }, $t('steps.face.one_click_faces')),
    h('button', { class: tab === 'game' ? 'on' : '', role: 'tab', 'aria-selected': String(tab === 'game'), onclick: () => setTab('game'),
      title: $t('steps.face.real_sims_faces_from_game') }, $t('steps.face.game_faces'), h('span', { class: 'tab-count' }, n ? String(n) : 'new')));
  let body;
  if (tab === 'game') {
    body = gameFacesPanel(app, sim);
  } else {
    body = h('div', { class: 'tiles three' });
    for (const [id, pr] of Object.entries(FACE_PRESETS)) {
      body.append(h('button', { class: 'tile face-tile' + (app._justPicked === 'face:' + id ? ' pop' : ''), onclick: () => app.setFace(sim.id, { ...pr.face }, pr.label, false, true, 'face:' + id) },
        h('span', { class: 'emoji' }, EMOJI[id] || '🙂'), h('b', {}, pr.label)));
    }
  }
  const hasFaceHere = !!(key && ((key.face && Object.keys(key.face).length) || key.faceBones));
  const anyFace = sim.keys.some(k => k.face && Object.keys(k.face).length);
  root.append(section([$t('steps.face.expressions'), h('span', { class: 'count' }, $t('steps.face.frame_n', { frame: f }))], tabs, body,
    h('div', { class: 'hint' }, tab === 'game'
      ? $t('steps.face.real_faces_from_sims_4')
      : $t('steps.face.sets_face_at_this_frame')),
    h('div', { class: 'btn-grid' },
      h('button', { class: 'btn small', disabled: !(key && key.face && Object.keys(key.face).length), onclick: () => app.bakeFace(sim.id),
        title: $t('steps.face.turn_expression_at_this_frame') }, icon('face'), $t('steps.face.make_this_expression_editable')),
      h('button', { class: 'btn small', disabled: !anyFace, onclick: () => app.bakeFace(sim.id, { all: true }),
        title: $t('steps.face.turn_every_expression_of_this') }, icon('face'), $t('steps.face.make_every_expression_editable')),
      h('button', { class: 'btn small', onclick: () => app.copyFace(sim.id) }, icon('copy'), $t('steps.face.copy_face')),
      h('button', { class: 'btn small', disabled: !app.faceClipboard, onclick: () => app.pasteFace(sim.id) }, icon('paste'), $t('steps.face.paste_face')),
      h('button', { class: 'btn small', onclick: () => app.mirrorFace(sim.id) }, icon('mirror'), $t('steps.face.mirror_face')),
      h('button', { class: 'btn small', disabled: !hasFaceHere, onclick: () => app.resetFace(sim.id) }, icon('reset'), $t('steps.face.reset_face_here')))));

  // ---- lip-sync: the face follows a sound
  root.append(lipSyncPanel(app, sim));

  // ---- face keys: one chip per frame that holds a face
  const fk = sim.keys.filter(k => (k.face && Object.keys(k.face).length) || k.faceBones);
  root.append(section([$t('steps.face.face_keys'), h('span', { class: 'count' }, String(fk.length))],
    fk.length ? h('div', { class: 'face-keys' }, fk.map(k => h('button', {
      class: 'chip' + (k.faceOnly ? ' face-only' : '') + (k.frame === f ? ' on' : ''),
      title: k.faceOnly ? $t('steps.face.face_key_at_body_has', { frame: k.frame }) : $t('steps.face.key_at_with_face', { frame: k.frame }),
      onclick: () => app.setFrame(k.frame) }, `${(k.frame / p.fps).toFixed(2)} s`)))
      : h('div', { class: 'hint', style: { marginTop: 0 } }, $t('steps.face.no_face_keys_yet_pick'))));

  // ---- sliders, added on top of the posed face
  const row = (k, s) => slider({ label: FACE_LABEL[k] || s.label, min: s.min, max: s.max, step: 0.02, value: cur[k] || 0, fmt: v => (v > 0 && s.min < 0 ? '+' : '') + Math.round(v * 100) + '%',
    onStart: () => app.store.checkpoint(), onInput: (val, done) => app.setFace(sim.id, { [k]: val }, null, true, done) });
  const sl = h('div', {}), more = h('div', {});
  for (const [k, s] of Object.entries(FACE_SLIDERS)) (s.more ? more : sl).append(row(k, s));
  // "More" stays open once opened (the panel is rebuilt after every edit), and opens by itself when one is in use
  const moreOpen = app._faceMoreOpen || Object.keys(FACE_SLIDERS).some(k => FACE_SLIDERS[k].more && cur[k]);
  const moreBox = more.children.length ? h('details', { class: 'more-sliders', open: moreOpen ? true : null,
    ontoggle: e => { app._faceMoreOpen = e.currentTarget.open; } },
    h('summary', {}, $t('steps.face.more_wink_one_sided_smile')), more) : null;
  root.append(section($t('steps.face.sliders_added_on_top_of'), sl, moreBox));

  const b = simBody(sim);
  root.append(section($t('steps.face.talking'), toggleRow($t('steps.face.mouth_moves_while_they_talk'), $t('steps.face.voice_sounds_moans_words_open'), b.talk.mouth !== false, on => app.setBody(sim.id, x => { x.talk.mouth = on; })),
    toggleRow($t('steps.face.blink_now_and_then'), $t('steps.face.natural_blinking_every_few_seconds'), b.blink !== false, on => app.setBody(sim.id, x => { x.blink = on; })),
    h('button', { class: 'btn block', onclick: () => app.showStep('sounds') }, icon('mic'), $t('steps.face.add_voices_and_moans'))));
}
