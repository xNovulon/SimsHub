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

// two-way sliders say both ends (the eyes one goes a little past open: wide eyes)
const FACE_LABEL = { eyes: 'Eyes (wide ↔ closed)' };
const EMOJI = { neutral: '😐', relaxed: '😌', smile: '😊', seductive: '😏', pleasure: '😣', moan: '😮', ecstasy: '😫', bite: '🫦', surprised: '😲', intense: '😖', tongue: '😛', ahegao: '🤪', kiss: '😘', sleepy: '😑' };

export function renderFace(app, root) {
  const sim = app.store.sim();
  if (!sim) { root.append(h('div', { class: 'empty' }, 'Select a sim first.')); return; }
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
    h('summary', {}, icon('face'), 'Face map', h('span', { class: 'fm-sub' }, 'always upright')));
  const mapEl = view ? faceMap(app, sim, view) : null;
  if (mapEl) map.append(mapEl);
  root.append(section('Pose the face by hand',
    h('button', { class: 'btn primary block big face-go' + (faceTool ? ' on' : ''), onclick: () => app.setTool('face'),
      title: 'Pose the face: brows, eyes, lids, cheeks, lips, jaw and tongue (Shift+F)' }, icon('face'), faceTool ? 'Posing the face - click a dot' : 'Pose the face'),
    h('div', { class: 'face-legend' }, REGIONS.map(r => h('span', { class: 'chip', style: { '--c': regionColor(r) } }, h('i', {}), REGION_LABEL[r]))),
    h('div', { class: 'hint' }, 'Click a dot on the face and drag the arrows or rings. T switches move/turn. X = both sides. Hold Alt to go past the safe range.'),
    mapEl ? map : null));

  // ---- expressions: one-click faces, or the game's own faces
  const tab = app._faceTab || localStorageGet('faceTab', 'quick');
  const setTab = t => { app._faceTab = t; localStorageSet('faceTab', t); app.renderStep(); };
  const n = (facesNow() || []).length;
  const tabs = h('div', { class: 'seg-inline face-tabs', role: 'tablist' },
    h('button', { class: tab !== 'game' ? 'on' : '', role: 'tab', 'aria-selected': String(tab !== 'game'), onclick: () => setTab('quick') }, 'One-click faces'),
    h('button', { class: tab === 'game' ? 'on' : '', role: 'tab', 'aria-selected': String(tab === 'game'), onclick: () => setTab('game'),
      title: 'Real Sims faces from the game: moods, pleasure, kisses, WooHoo...' }, 'Game faces', h('span', { class: 'tab-count' }, n ? String(n) : 'new')));
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
  root.append(section(['Expressions', h('span', { class: 'count' }, `frame ${f}`)], tabs, body,
    h('div', { class: 'hint' }, tab === 'game'
      ? 'Real faces from The Sims 4\'s own animations. Point at one to try it on, click to put it on this frame.'
      : 'Sets the face at this frame (a key). Put different faces at different frames and it changes smoothly between them.'),
    h('div', { class: 'btn-grid' },
      h('button', { class: 'btn small', disabled: !(key && key.face && Object.keys(key.face).length), onclick: () => app.bakeFace(sim.id),
        title: 'Turn the expression at this frame into face dots you can move one by one' }, icon('face'), 'Make this expression editable'),
      h('button', { class: 'btn small', disabled: !anyFace, onclick: () => app.bakeFace(sim.id, { all: true }),
        title: 'Turn every expression of this sim into face dots you can move one by one' }, icon('face'), 'Make every expression editable'),
      h('button', { class: 'btn small', onclick: () => app.copyFace(sim.id) }, icon('copy'), 'Copy face'),
      h('button', { class: 'btn small', disabled: !app.faceClipboard, onclick: () => app.pasteFace(sim.id) }, icon('paste'), 'Paste face'),
      h('button', { class: 'btn small', onclick: () => app.mirrorFace(sim.id) }, icon('mirror'), 'Mirror face'),
      h('button', { class: 'btn small', disabled: !hasFaceHere, onclick: () => app.resetFace(sim.id) }, icon('reset'), 'Reset face here'))));

  // ---- lip-sync: the face follows a sound
  root.append(lipSyncPanel(app, sim));

  // ---- face keys: one chip per frame that holds a face
  const fk = sim.keys.filter(k => (k.face && Object.keys(k.face).length) || k.faceBones);
  root.append(section(['Face keys', h('span', { class: 'count' }, String(fk.length))],
    fk.length ? h('div', { class: 'face-keys' }, fk.map(k => h('button', {
      class: 'chip' + (k.faceOnly ? ' face-only' : '') + (k.frame === f ? ' on' : ''),
      title: k.faceOnly ? `Face key at ${k.frame} (the body has no key here)` : `Key at ${k.frame} with a face`,
      onclick: () => app.setFrame(k.frame) }, `${(k.frame / p.fps).toFixed(2)} s`)))
      : h('div', { class: 'hint', style: { marginTop: 0 } }, 'No face keys yet - pick an expression or pose the face by hand.')));

  // ---- sliders, added on top of the posed face
  const row = (k, s) => slider({ label: FACE_LABEL[k] || s.label, min: s.min, max: s.max, step: 0.02, value: cur[k] || 0, fmt: v => (v > 0 && s.min < 0 ? '+' : '') + Math.round(v * 100) + '%',
    onStart: () => app.store.checkpoint(), onInput: (val, done) => app.setFace(sim.id, { [k]: val }, null, true, done) });
  const sl = h('div', {}), more = h('div', {});
  for (const [k, s] of Object.entries(FACE_SLIDERS)) (s.more ? more : sl).append(row(k, s));
  // "More" stays open once opened (the panel is rebuilt after every edit), and opens by itself when one is in use
  const moreOpen = app._faceMoreOpen || Object.keys(FACE_SLIDERS).some(k => FACE_SLIDERS[k].more && cur[k]);
  const moreBox = more.children.length ? h('details', { class: 'more-sliders', open: moreOpen ? true : null,
    ontoggle: e => { app._faceMoreOpen = e.currentTarget.open; } },
    h('summary', {}, 'More (wink, one-sided smile, sneer...)'), more) : null;
  root.append(section('Sliders - added on top of the posed face', sl, moreBox));

  const b = simBody(sim);
  root.append(section('Talking', toggleRow('Mouth moves while they talk', 'Voice sounds (moans, words) open and close the mouth by themselves', b.talk.mouth !== false, on => app.setBody(sim.id, x => { x.talk.mouth = on; })),
    toggleRow('Blink now and then', 'The eyes close for a moment every few seconds', b.blink === true, on => app.setBody(sim.id, x => { x.blink = on; })),
    h('button', { class: 'btn block', onclick: () => app.showStep('sounds') }, icon('mic'), 'Add voices and moans')));
}
