// Left (scene) and right (inspector) panels.
import * as THREE from 'three';
import { h, icon, contextMenu } from './ui.js';
import { label, LIMBS, SKIN_TONES, SIM_COLORS } from './bones.js';

const BODY_NAMES = { yf: 'Female body', ym: 'Male body' };
const GENDERS = { FEMALE: 'Female part', MALE: 'Male part', BOTH: 'Either' };
const LIMB_LABEL = { 'L hand': 'Left hand', 'R hand': 'Right hand', 'L foot': 'Left foot', 'R foot': 'Right foot' };

export function renderSimList(app) {
  const list = document.getElementById('sim-list');
  list.innerHTML = '';
  const { project } = app.store;
  if (!project.sims.length) {
    list.append(h('div', { class: 'empty' }, 'No sims yet. ', h('b', {}, 'Add a sim'), ' with the + above, or pick an animation in the ', h('b', {}, 'Library'), ' and import it.'));
  }
  project.sims.forEach((s, k) => {
    const active = s.id === app.store.selected.sim;
    const card = h('div', { class: 'sim-card' + (active ? ' active' : ''), style: { '--sim': s.color }, onclick: () => app.selectSim(s.id) },
      h('div', { class: 'sim-avatar' }, String(k + 1)),
      h('div', { class: 'meta' }, h('b', {}, s.label), h('span', {}, `${BODY_NAMES[s.frame]} · ${s.keys.length} key${s.keys.length === 1 ? '' : 's'}`)),
      h('div', { class: 'row-actions' },
        h('button', { class: 'icon-btn', title: s.visible ? 'Hide' : 'Show', onclick: e => { e.stopPropagation(); app.toggleVisible(s.id); } }, icon('eye')),
        h('button', { class: 'icon-btn', title: 'More', onclick: e => { e.stopPropagation(); simMenu(app, s, e.clientX, e.clientY); } }, h('span', { style: { fontWeight: 800 } }, '⋯'))));
    if (!s.visible) card.style.opacity = '0.5';
    list.append(card);
  });
}

function simMenu(app, s, x, y) {
  contextMenu(x, y, [
    { label: 'Duplicate', onClick: () => app.duplicateSim(s.id) },
    { label: s.frame === 'yf' ? 'Switch to male body' : 'Switch to female body', onClick: () => app.setSimBody(s.id, s.frame === 'yf' ? 'ym' : 'yf') },
    { label: 'Clear all keys', onClick: () => app.clearKeys(s.id) },
    '-',
    { label: 'Remove sim', danger: true, icon: 'trash', onClick: () => app.removeSim(s.id) },
  ]);
}

export function renderFurniture(app) {
  const grid = document.getElementById('furniture-grid');
  grid.innerHTML = '';
  for (const f of app.furniture) {
    grid.append(h('button', { class: 'furn' + (f.id === app.store.project.furniture ? ' active' : ''), onclick: () => app.setFurniture(f.id), title: 'WickedWhims: ' + f.locations.join(', ') },
      h('span', { class: 'glyph' }), f.label));
  }
  const cur = app.furniture.find(f => f.id === app.store.project.furniture);
  document.getElementById('furniture-hint').textContent = cur
    ? `Plays in WickedWhims on: ${app.store.project.locations.join(', ')}. The green ring is the object's origin.` : '';
}

// ---------------------------------------------------------------- inspector
export function renderInspector(app) {
  const root = document.getElementById('inspector');
  root.innerHTML = '';
  const sim = app.store.sim();
  if (!sim) {
    root.append(h('div', { class: 'empty' },
      h('p', {}, h('b', {}, 'Start here')),
      h('p', {}, '1. Add sims in the Scene tab, or import an animation from the Library as a starting point.'),
      h('p', {}, '2. Click a body part to rotate it, or switch to ', h('b', {}, 'Drag'), ' to move hands, feet and hips.'),
      h('p', {}, '3. Press ', h('kbd', {}, 'K'), ' to keep the pose at this frame. Move to another frame, pose again, key again - the app fills in the motion.'),
      h('p', {}, '4. ', h('b', {}, 'Send to game'), ' writes it into your Mods folder for WickedWhims.')));
    return;
  }
  const view = app.simViews.get(sim.id);
  root.append(h('div', { class: 'insp-head', style: { '--sim': sim.color } }, h('div', { class: 'swatch' }),
    h('div', {}, h('b', {}, sim.label), h('span', {}, app.store.selected.bone ? label(app.store.selected.bone) : 'Whole sim'))));

  if (app.store.selected.bone && view) root.append(boneSection(app, sim, view));
  root.append(pinSection(app, sim));
  root.append(poseSection(app, sim));
  root.append(soundSection(app, sim));
  root.append(simSection(app, sim));
}

function boneSection(app, sim, view) {
  const name = app.store.selected.bone;
  const bone = view.bone(name);
  const rest = view.rest[view.index(name)].quat;
  const rel = rest.clone().invert().multiply(bone.quaternion);
  const e = new THREE.Euler().setFromQuaternion(rel, 'XYZ');
  const deg = [e.x, e.y, e.z].map(r => Math.round(THREE.MathUtils.radToDeg(r)));
  const sec = h('div', { class: 'insp-section' }, h('h4', {}, 'Rotation (from rest)'));
  const setAxis = (axis, value, commit) => {
    const cur = new THREE.Euler().setFromQuaternion(rest.clone().invert().multiply(bone.quaternion), 'XYZ');
    cur[axis] = THREE.MathUtils.degToRad(value);
    bone.quaternion.copy(rest.clone().multiply(new THREE.Quaternion().setFromEuler(cur)));
    app.poseEdited(sim.id, !commit);
    if (commit) app.afterEdit();
  };
  ['x', 'y', 'z'].forEach((axis, k) => {
    const num = h('input', { class: 'num', type: 'number', value: deg[k], step: 1 });
    const range = h('input', { type: 'range', min: -180, max: 180, step: 1, value: deg[k] });
    range.addEventListener('pointerdown', () => app.store.checkpoint());
    range.addEventListener('input', () => { num.value = range.value; setAxis(axis, +range.value, false); });
    range.addEventListener('change', () => app.afterEdit());
    num.addEventListener('change', () => { app.store.checkpoint(); range.value = num.value; setAxis(axis, +num.value, true); });
    sec.append(h('div', { class: 'slider-row' }, h('label', { class: axis }, axis.toUpperCase()), range, num));
  });
  sec.append(h('div', { class: 'btn-grid', style: { marginTop: '10px' } },
    h('button', { class: 'btn small', onclick: () => app.resetBone(sim.id, name) }, icon('reset'), 'Reset part'),
    h('button', { class: 'btn small', onclick: () => app.mirrorBone(sim.id, name), disabled: !/_(L|R)_/.test(name) }, icon('mirror'), 'Copy to other side')));
  return sec;
}

function pinSection(app, sim) {
  const sec = h('div', { class: 'insp-section' }, h('h4', {}, 'Pins'));
  const grid = h('div', { class: 'pin-grid' });
  for (const limb of Object.keys(LIMBS)) {
    const on = !!(sim.pins || {})[limb];
    grid.append(h('button', { class: 'pin' + (on ? ' on' : ''), onclick: () => app.interact.togglePin(sim.id, limb), title: on ? 'Pinned: stays put while the body moves' : 'Pin it where it is now' },
      LIMB_LABEL[limb], h('span', { class: 'state' }, on ? 'pinned' : 'free')));
  }
  sec.append(grid, h('div', { class: 'hint' }, 'Pinned hands and feet stay where they are when you move the hips or body - knees and elbows bend by themselves. In Drag mode, Alt+click a handle to pin it.'));
  return sec;
}

function poseSection(app, sim) {
  const sec = h('div', { class: 'insp-section' }, h('h4', {}, 'Pose'));
  sec.append(h('div', { class: 'btn-grid' },
    h('button', { class: 'btn small', onclick: () => app.mirrorPose(sim.id) }, icon('mirror'), 'Mirror pose'),
    h('button', { class: 'btn small', onclick: () => app.resetPose(sim.id) }, icon('reset'), 'Reset pose'),
    h('button', { class: 'btn small', onclick: () => app.copyPose(sim.id) }, 'Copy pose'),
    h('button', { class: 'btn small', onclick: () => app.pastePose(sim.id), disabled: !app.clipboard }, 'Paste pose'),
    h('button', { class: 'btn small', onclick: () => app.turnSim(sim.id, 90) }, '↺ Turn 90°'),
    h('button', { class: 'btn small', onclick: () => app.turnSim(sim.id, -90) }, '↻ Turn 90°')));
  return sec;
}

function soundSection(app, sim) {
  const sec = h('div', { class: 'insp-section' }, h('h4', {}, 'Sounds'));
  const list = h('div', { class: 'sound-list' });
  const sounds = [...(sim.sounds || [])].sort((a, b) => a.frame - b.frame);
  if (!sounds.length) list.append(h('div', { class: 'hint' }, 'No sounds. "Auto sounds" finds the claps and wet strokes from how the bodies move.'));
  for (const s of sounds) {
    list.append(h('div', { class: 'sound-row' },
      h('span', { class: 'f' }, String(s.frame)),
      h('span', { class: 'n', title: s.name }, h('span', { class: 'tag ' + (s.kind || 'other') }, s.kind || 'sound'), s.name),
      h('button', { class: 'icon-btn', title: 'Remove', onclick: () => app.removeSound(sim.id, s) }, icon('trash'))));
  }
  sec.append(list, h('div', { class: 'btn-grid', style: { marginTop: '8px' } },
    h('button', { class: 'btn small', onclick: () => app.autoSounds() }, 'Auto sounds'),
    h('button', { class: 'btn small', onclick: () => app.addSoundDialog(sim.id) }, 'Add sound here')));
  return sec;
}

function simSection(app, sim) {
  const sec = h('div', { class: 'insp-section' }, h('h4', {}, 'Sim'));
  const name = h('input', { class: 'text', value: sim.label });
  name.addEventListener('change', () => { app.store.checkpoint(); sim.label = name.value || sim.label; app.refreshPanels(); });
  const gender = h('select', {}, Object.entries(GENDERS).map(([v, t]) => h('option', { value: v, selected: sim.gender === v }, t)));
  gender.addEventListener('change', () => { app.store.checkpoint(); sim.gender = gender.value; app.store.setDirty(true); });
  const skins = h('div', { class: 'swatches' }, SKIN_TONES.map(c => h('button', { class: sim.skin === c ? 'active' : '', style: { background: c }, onclick: () => app.setSkin(sim.id, c) })));
  const colors = h('div', { class: 'swatches' }, SIM_COLORS.map(c => h('button', { class: sim.color === c ? 'active' : '', style: { background: c }, onclick: () => app.setColor(sim.id, c) })));
  sec.append(
    h('label', { class: 'field' }, h('span', {}, 'Name'), name),
    h('label', { class: 'field' }, h('span', {}, 'Plays which part in WickedWhims'), gender),
    h('div', { class: 'field' }, h('span', {}, 'Skin'), skins),
    h('div', { class: 'field' }, h('span', {}, 'Colour on the timeline'), colors));
  return sec;
}
