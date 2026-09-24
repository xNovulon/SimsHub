// Left (scene) and right (inspector) panels.
import * as THREE from 'three';
import { h, icon, contextMenu } from './ui.js';
import { label, LIMBS, SKIN_TONES, SIM_COLORS } from './bones.js';
import { $t } from './i18n.js';

const BODY_NAMES = { yf: $t('panels.female_body'), ym: $t('panels.male_body') };
const GENDERS = { FEMALE: $t('panels.female_part'), MALE: $t('panels.male_part'), BOTH: $t('panels.either') };
const LIMB_LABEL = { 'L hand': $t('panels.left_hand'), 'R hand': $t('panels.right_hand'), 'L foot': $t('panels.left_foot'), 'R foot': $t('panels.right_foot') };

export function renderSimList(app) {
  const list = document.getElementById('sim-list');
  list.innerHTML = '';
  const { project } = app.store;
  if (!project.sims.length) {
    list.append(h('div', { class: 'empty' }, $t('panels.no_sims_yet'), h('b', {}, $t('panels.add_sim')), $t('panels.with_above_or_pick_animation'), h('b', {}, $t('panels.library')), $t('panels.and_import_it')));
  }
  project.sims.forEach((s, k) => {
    const active = s.id === app.store.selected.sim;
    const card = h('div', { class: 'sim-card' + (active ? ' active' : ''), style: { '--sim': s.color }, onclick: () => app.selectSim(s.id) },
      h('div', { class: 'sim-avatar' }, String(k + 1)),
      h('div', { class: 'meta' }, h('b', {}, s.label), h('span', {}, $t('panels.keys', { v: BODY_NAMES[s.frame], keyCount: s.keys.length }))),
      h('div', { class: 'row-actions' },
        h('button', { class: 'icon-btn', title: s.visible ? $t('panels.hide') : $t('panels.show'), onclick: e => { e.stopPropagation(); app.toggleVisible(s.id); } }, icon('eye')),
        h('button', { class: 'icon-btn', title: $t('panels.more'), onclick: e => { e.stopPropagation(); simMenu(app, s, e.clientX, e.clientY); } }, h('span', { style: { fontWeight: 800 } }, '⋯'))));
    if (!s.visible) card.style.opacity = '0.5';
    list.append(card);
  });
}

function simMenu(app, s, x, y) {
  contextMenu(x, y, [
    { label: $t('panels.duplicate'), onClick: () => app.duplicateSim(s.id) },
    { label: s.frame === 'yf' ? $t('panels.switch_to_male_body') : $t('panels.switch_to_female_body'), onClick: () => app.setSimBody(s.id, s.frame === 'yf' ? 'ym' : 'yf') },
    { label: $t('panels.clear_all_keys'), onClick: () => app.clearKeys(s.id) },
    '-',
    { label: $t('panels.remove_sim'), danger: true, icon: 'trash', onClick: () => app.removeSim(s.id) },
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
    ? $t('panels.plays_in_wickedwhims_on_green', { locations: app.store.project.locations.join(', ') }) : '';
}

// ---------------------------------------------------------------- inspector
export function renderInspector(app) {
  const root = document.getElementById('inspector');
  root.innerHTML = '';
  const sim = app.store.sim();
  if (!sim) {
    root.append(h('div', { class: 'empty' },
      h('p', {}, h('b', {}, $t('panels.start_here'))),
      h('p', {}, $t('panels.1_add_sims_in_scene')),
      h('p', {}, $t('panels.2_click_body_part_to'), h('b', {}, $t('panels.drag')), $t('panels.to_move_hands_feet_and')),
      h('p', {}, $t('panels.3_press'), h('kbd', {}, 'K'), $t('panels.to_keep_pose_at_this')),
      h('p', {}, '4. ', h('b', {}, $t('panels.send_to_game')), $t('panels.writes_it_into_your_mods'))));
    return;
  }
  const view = app.simViews.get(sim.id);
  root.append(h('div', { class: 'insp-head', style: { '--sim': sim.color } }, h('div', { class: 'swatch' }),
    h('div', {}, h('b', {}, sim.label), h('span', {}, app.store.selected.bone ? label(app.store.selected.bone) : $t('panels.whole_sim')))));

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
  const sec = h('div', { class: 'insp-section' }, h('h4', {}, $t('panels.rotation_from_rest')));
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
    h('button', { class: 'btn small', onclick: () => app.resetBone(sim.id, name) }, icon('reset'), $t('panels.reset_part')),
    h('button', { class: 'btn small', onclick: () => app.mirrorBone(sim.id, name), disabled: !/_(L|R)_/.test(name) }, icon('mirror'), $t('panels.copy_to_other_side'))));
  return sec;
}

function pinSection(app, sim) {
  const sec = h('div', { class: 'insp-section' }, h('h4', {}, $t('panels.pins')));
  const grid = h('div', { class: 'pin-grid' });
  for (const limb of Object.keys(LIMBS)) {
    const on = !!(sim.pins || {})[limb];
    grid.append(h('button', { class: 'pin' + (on ? ' on' : ''), onclick: () => app.interact.togglePin(sim.id, limb), title: on ? $t('panels.pinned_stays_put_while_body') : $t('panels.pin_it_where_it_is') },
      LIMB_LABEL[limb], h('span', { class: 'state' }, on ? 'pinned' : 'free')));
  }
  sec.append(grid, h('div', { class: 'hint' }, $t('panels.pinned_hands_and_feet_stay')));
  return sec;
}

function poseSection(app, sim) {
  const sec = h('div', { class: 'insp-section' }, h('h4', {}, $t('panels.pose')));
  sec.append(h('div', { class: 'btn-grid' },
    h('button', { class: 'btn small', onclick: () => app.mirrorPose(sim.id) }, icon('mirror'), $t('panels.mirror_pose')),
    h('button', { class: 'btn small', onclick: () => app.resetPose(sim.id) }, icon('reset'), $t('panels.reset_pose')),
    h('button', { class: 'btn small', onclick: () => app.copyPose(sim.id) }, $t('panels.copy_pose')),
    h('button', { class: 'btn small', onclick: () => app.pastePose(sim.id), disabled: !app.clipboard }, $t('panels.paste_pose')),
    h('button', { class: 'btn small', onclick: () => app.turnSim(sim.id, 90) }, $t('panels.turn_90')),
    h('button', { class: 'btn small', onclick: () => app.turnSim(sim.id, -90) }, $t('panels.turn_90_2'))));
  return sec;
}

function soundSection(app, sim) {
  const sec = h('div', { class: 'insp-section' }, h('h4', {}, $t('panels.sounds')));
  const list = h('div', { class: 'sound-list' });
  const sounds = [...(sim.sounds || [])].sort((a, b) => a.frame - b.frame);
  if (!sounds.length) list.append(h('div', { class: 'hint' }, $t('panels.no_sounds_auto_sounds_finds')));
  for (const s of sounds) {
    list.append(h('div', { class: 'sound-row' },
      h('span', { class: 'f' }, String(s.frame)),
      h('span', { class: 'n', title: s.name }, h('span', { class: 'tag ' + (s.kind || 'other') }, s.kind || 'sound'), s.name),
      h('button', { class: 'icon-btn', title: $t('panels.remove'), onclick: () => app.removeSound(sim.id, s) }, icon('trash'))));
  }
  sec.append(list, h('div', { class: 'btn-grid', style: { marginTop: '8px' } },
    h('button', { class: 'btn small', onclick: () => app.autoSounds() }, $t('panels.auto_sounds')),
    h('button', { class: 'btn small', onclick: () => app.addSoundDialog(sim.id) }, $t('panels.add_sound_here'))));
  return sec;
}

function simSection(app, sim) {
  const sec = h('div', { class: 'insp-section' }, h('h4', {}, $t('panels.sim')));
  const name = h('input', { class: 'text', value: sim.label });
  name.addEventListener('change', () => { app.store.checkpoint(); sim.label = name.value || sim.label; app.refreshPanels(); });
  const gender = h('select', {}, Object.entries(GENDERS).map(([v, t]) => h('option', { value: v, selected: sim.gender === v }, t)));
  gender.addEventListener('change', () => { app.store.checkpoint(); sim.gender = gender.value; app.store.setDirty(true); });
  const skins = h('div', { class: 'swatches' }, SKIN_TONES.map(c => h('button', { class: sim.skin === c ? 'active' : '', style: { background: c }, onclick: () => app.setSkin(sim.id, c) })));
  const colors = h('div', { class: 'swatches' }, SIM_COLORS.map(c => h('button', { class: sim.color === c ? 'active' : '', style: { background: c }, onclick: () => app.setColor(sim.id, c) })));
  sec.append(
    h('label', { class: 'field' }, h('span', {}, $t('panels.name')), name),
    h('label', { class: 'field' }, h('span', {}, $t('panels.plays_which_part_in_wickedwhims')), gender),
    h('div', { class: 'field' }, h('span', {}, $t('panels.skin')), skins),
    h('div', { class: 'field' }, h('span', {}, $t('panels.colour_on_timeline')), colors));
  return sec;
}
