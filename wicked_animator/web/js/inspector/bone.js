// The selected part: turn it (body bones), or - for extra bones (breasts, penis tip, helpers) - turn and move it.
// Face bones and twist helpers have their own cards (inspector/face.js). A hand or finger also gets the hand shapes
// (one click for the whole hand, Curl / Spread / Thumb); the back, neck and head can turn together; fingers,
// elbows, knees, the back, neck and head stop at natural limits (a switch turns them off for special poses).
import * as THREE from 'three';
import { h, icon, section, fillRange, slider, toggle, toast } from '../ui.js';
import { FACE_SET, TWIST_SET, EXPERT_SET, EXTRA_SET, label, twist } from '../facekit.js';
import { limitsFor, TURN_GROUPS } from '../bones.js';
import { clampToLimits } from '../posemath.js';
import { HAND_SHAPES, SHAPE_ORDER, shapeIcon, readHand, handSide, currentShape } from '../hands.js';
import { faceBoneSection, twistSection } from './face.js';
import { $t } from '../i18n.js';

export function boneSection(app, sim, view, name) {
  if (FACE_SET.has(name)) return faceBoneSection(app, sim, view, name);
  if (TWIST_SET.has(name)) return twistSection(app, sim, view, name);
  if (EXTRA_SET.has(name)) return extraSection(app, sim, view, name);
  const side = handSide(name);
  if (side) {
    const frag = document.createDocumentFragment();
    frag.append(handSection(app, sim, view, name, side), turnSection(app, sim, view, name));
    return frag;
  }
  return turnSection(app, sim, view, name);
}

const limitsOn = app => app.naturalLimits !== false;

// Bend / Twist / Tilt from standing, -180..180 degrees (or the part's natural range while Natural limits is on).
function turnRows(app, sim, view, name, sec) {
  const bone = view.bone(name);
  const rest = view.rest[view.index(name)].quat;
  const rel = rest.clone().invert().multiply(bone.quaternion);
  const e = new THREE.Euler().setFromQuaternion(rel, 'XYZ');
  const deg = [e.x, e.y, e.z].map(r => Math.round(THREE.MathUtils.radToDeg(r)));
  const lim = limitsOn(app) ? limitsFor(name) : null;
  const setAxis = (axis, value, commit) => {
    app.setBoneTurn(sim.id, name, axis, value, commit);
    // past its natural range: it stops there (the key gets the stopped turn)
    if (lim && clampToLimits(view, view.bone(name))) {
      if (app.mirrorEdit && app.mirrorLive) app.mirrorLive(sim.id, name);
      app.pipeline.pins({ sim, v: view }, Math.round(app.store.frame));
      twist(app, { sim, v: view });
      app.poseEdited(sim.id, !commit, 'body');
      app.hud && app.hud($t('inspector.bone.natural_limit_reached_switch_off'), { hold: 1400 });
    }
  };
  const NAMES = { x: 'Bend', y: 'Twist', z: 'Tilt' };
  ['x', 'y', 'z'].forEach((axis, k) => {
    const r = lim && lim[axis];
    const locked = !!(r && r[0] === 0 && r[1] === 0);          // a hinge only bends one way
    const lo = r && !locked ? Math.floor(Math.min(r[0], deg[k])) : -180, hi = r && !locked ? Math.ceil(Math.max(r[1], deg[k])) : 180;
    const num = h('input', { class: 'num', type: 'number', value: deg[k], step: 1, disabled: locked || null });
    const range = h('input', { type: 'range', min: lo, max: hi, step: 1, value: deg[k], disabled: locked || null });
    fillRange(range);                    // filled from 0 (standing) to the thumb, both ways
    range.addEventListener('pointerdown', () => app.store.checkpoint());
    range.addEventListener('input', () => { num.value = range.value; setAxis(axis, +range.value, false); });
    range.addEventListener('change', () => app.afterEdit());
    num.addEventListener('change', () => { app.store.checkpoint(); range.value = num.value; fillRange(range); setAxis(axis, +num.value, true); num.blur(); });
    sec.append(h('div', { class: 'slider-row', title: locked ? $t('inspector.bone.hinge_only_bends_one_way', { v: NAMES[axis] }) : r ? $t('inspector.bone.to_natural_limits', { v: NAMES[axis], v2: r[0], v3: r[1] }) : NAMES[axis] },
      h('label', { class: axis }, axis.toUpperCase()), range, num));
  });
}

// Move in millimetres from the rest place (extra bones: -60..60 mm).
function moveRows(app, sim, view, name, sec, span = 60) {
  const bone = view.bone(name), rest = view.restByName[name].pos;
  const d = bone.position.clone().sub(rest);
  ['x', 'y', 'z'].forEach(axis => {
    const mm = Math.round(d[axis] * 10000) / 10;
    const num = h('input', { class: 'num', type: 'number', value: mm, step: 0.5 });
    const range = h('input', { type: 'range', min: -span, max: span, step: 0.5, value: mm });
    fillRange(range);
    const set = (v, commit) => app.setBoneMove(sim.id, name, axis, v / 1000, commit);
    range.addEventListener('pointerdown', () => app.store.checkpoint());
    range.addEventListener('input', () => { num.value = range.value; set(+range.value, false); });
    range.addEventListener('change', () => app.afterEdit());
    num.addEventListener('change', () => { app.store.checkpoint(); range.value = num.value; fillRange(range); set(+num.value, true); num.blur(); });
    sec.append(h('div', { class: 'slider-row', title: $t('inspector.bone.move_mm') }, h('label', { class: axis }, axis.toUpperCase()), range, num));
  });
}

// "Turn: Just this part · Whole back · Neck & head" (spec_editing 8.2 / 9.1)
function turnGroupRow(app, name) {
  const groups = Object.entries(TURN_GROUPS).filter(([, G]) => G.bones.includes(name));
  if (!groups.length || typeof app.setTurnGroup !== 'function') return null;
  const cur = app.turnGroup || 'none';
  const btn = (id, text, tip) => h('button', { class: cur === id ? 'on' : '', title: tip, onclick: () => app.setTurnGroup(id) }, text);
  return h('div', { class: 'turn-group', title: $t('inspector.bone.whole_back_spreads_your_turn') },
    h('div', { class: 'sub-title' }, $t('inspector.bone.turn')),
    h('div', { class: 'seg-inline' }, btn('none', $t('inspector.bone.just_this_part'), $t('inspector.bone.only_selected_part_turns')),
      ...groups.map(([id, G]) => btn(id, G.label, id === 'back' ? $t('inspector.bone.your_turn_is_spread_over') : $t('inspector.bone.your_turn_is_spread_over_2')))));
}

// This part's turn copied from the key before / after (the key here gets it; one undo step).
function matchKey(app, sim, view, name, dir) {
  const f = Math.round(app.store.frame);
  const body = sim.keys.filter(k => !k.faceOnly && k.pose);
  const nb = dir < 0 ? [...body].reverse().find(k => k.frame < f) : body.find(k => k.frame > f);
  if (!nb) { toast(dir < 0 ? $t('inspector.bone.there_is_no_key_before') : $t('inspector.bone.there_is_no_key_after')); return; }
  const r = view.restByName[name];
  app.store.checkpoint(dir < 0 ? $t('inspector.bone.match_previous_key') : $t('inspector.bone.match_next_key'));
  app.beginEdit(sim.id);
  const q = nb.pose.rot && nb.pose.rot[name];
  view.bone(name).quaternion.copy(q ? new THREE.Quaternion().fromArray(q) : r.quat);
  app.pipeline.pins({ sim, v: view }, f);
  twist(app, { sim, v: view });
  app.poseEdited(sim.id, false, 'body');
  app.afterEdit();
  toast($t(dir < 0 ? 'inspector.bone.turns_as_previous' : 'inspector.bone.turns_as_next', { part: label(name, sim.frame) }));
}

function partTools(app, sim, view, name) {
  const f = Math.round(app.store.frame);
  const body = sim.keys.filter(k => !k.faceOnly && k.pose);
  const prev = body.some(k => k.frame < f), next = body.some(k => k.frame > f);
  const sel = app.timeline && app.timeline.sel;
  const selKeys = sel ? [...sel].filter(id => id.startsWith(`k|${sim.id}|`)).length : 0;
  const btns = [
    h('button', { class: 'btn small', disabled: !prev || null, title: $t('inspector.bone.copy_this_part_s_turn'), onclick: () => matchKey(app, sim, view, name, -1) }, icon('prev'), $t('inspector.bone.same_as_previous_key')),
    h('button', { class: 'btn small', disabled: !next || null, title: $t('inspector.bone.copy_this_part_s_turn_2'), onclick: () => matchKey(app, sim, view, name, 1) }, icon('next'), $t('inspector.bone.same_as_next_key')),
  ];
  if (typeof app.putPartOnSelectedKeys === 'function' && selKeys) btns.push(h('button', { class: 'btn small', onclick: () => app.putPartOnSelectedKeys(sim.id, name) }, icon('copy'), $t('inspector.bone.put_this_on_selected_keys', { selKeys })));
  if (typeof app.setTimelineView === 'function') btns.push(h('button', { class: 'btn small', onclick: () => app.setTimelineView('curves') }, icon('trail'), $t('inspector.bone.show_its_curves')));
  return h('div', { class: 'btn-grid part-tools' }, ...btns);
}

function limitsRow(app) {
  return h('div', { class: 'toggle-row limit-row' },
    h('div', {}, h('b', {}, $t('inspector.bone.natural_limits')), h('span', {}, $t('inspector.bone.fingers_elbows_knees_back_and'))),
    toggle(limitsOn(app), on => (app.setNaturalLimits ? app.setNaturalLimits(on) : (app.naturalLimits = on))));
}

function turnSection(app, sim, view, name) {
  const sec = section([$t('inspector.bone.turn_this_part'), h('span', { class: 'count' }, $t('inspector.bone.from_standing'))]);
  const tg = turnGroupRow(app, name);
  if (tg) sec.append(tg);
  turnRows(app, sim, view, name, sec);
  sec.append(h('div', { class: 'btn-grid', style: { marginTop: '10px' } },
    h('button', { class: 'btn small', onclick: () => app.resetBone(sim.id, name), title: $t('inspector.bone.back_to_standing_alt_r') }, icon('reset'), $t('inspector.bone.reset_part')),
    h('button', { class: 'btn small', onclick: () => app.mirrorBone(sim.id, name), disabled: !/_(L|R)_/.test(name) }, icon('mirror'), $t('inspector.bone.copy_to_other_side'))));
  sec.append(partTools(app, sim, view, name));
  if (limitsFor(name)) sec.append(limitsRow(app));
  return sec;
}

// "Hand shape" (spec_bodies 5.4): ten shapes, Curl / Spread / Thumb, "Same for both hands", "Natural limits".
function handSection(app, sim, view, name, side) {
  const word = side === 'L' ? 'left' : 'right';
  const cur = currentShape(view, side);
  const sec = section([$t('inspector.bone.hand_shape'), h('span', { class: 'count' }, app.handsBoth ? $t('inspector.bone.both_hands') : word === 'left' ? $t('inspector.bone.left_hand') : $t('inspector.bone.right_hand'))]);
  const grid = h('div', { class: 'hand-shapes' });
  for (const id of SHAPE_ORDER) {
    const sh = HAND_SHAPES[id];
    grid.append(h('button', { class: 'hand-shape' + (cur === id ? ' on' : ''), title: `${sh.label} - ${sh.tip}`, 'data-shape': id,
      onclick: () => app.setHandShape && app.setHandShape(sim.id, side, id) }, h('i', { html: shapeIcon(id), style: { display: 'contents' } }), h('span', {}, sh.short || sh.label)));
  }
  sec.append(grid);
  const hv = readHand(view, side);
  const pct = v => Math.round(v * 100) + '%';
  const sl = (kind, text, min, max, value, tip) => slider({ label: text, min, max, step: 0.01, value: Math.max(min, Math.min(max, value)), fmt: pct, title: tip,
    onStart: () => app.store.checkpoint($t('inspector.bone.hand_change')), onInput: (v, done) => app.setHandSlider && app.setHandSlider(sim.id, side, kind, v, !done) });
  sec.append(h('div', { class: 'hand-sliders' },
    sl('curl', $t('inspector.bone.curl'), 0, 1, hv.curl, $t('inspector.bone.bend_all_four_fingers_toward')),
    sl('spread', $t('inspector.bone.spread'), -0.5, 1, hv.spread, $t('inspector.bone.fan_fingers_apart_below_0')),
    sl('thumb', $t('inspector.bone.thumb'), 0, 1, hv.thumb, $t('inspector.bone.fold_thumb_across_palm'))));
  sec.append(h('div', { class: 'toggle-row' }, h('div', {}, h('b', {}, $t('inspector.bone.same_for_both_hands')), h('span', {}, $t('inspector.bone.shape_or_slider_changes_both'))),
    toggle(!!app.handsBoth, on => app.setHandsBoth && app.setHandsBoth(on))));
  sec.append(limitsRow(app));
  return sec;
}

function extraSection(app, sim, view, name) {
  const sec = section([$t('inspector.bone.turn_and_move_this_part'), h('span', { class: 'count' }, $t('inspector.bone.from_rest'))]);
  if (EXPERT_SET.has(name)) {
    sec.append(h('div', { class: 'warn-box' }, $t('inspector.bone.game_shapes_each_sim_with')));
  }
  sec.append(h('div', { class: 'sub-title' }, $t('inspector.bone.turn')));
  turnRows(app, sim, view, name, sec);
  sec.append(h('div', { class: 'sub-title' }, $t('inspector.bone.move_mm')));
  moveRows(app, sim, view, name, sec);
  sec.append(h('div', { class: 'hint' }, $t('inspector.bone.t_switches_arrows_and_rings', { label: label(name, sim.frame) })),
    h('div', { class: 'btn-grid', style: { marginTop: '6px' } },
      h('button', { class: 'btn small', onclick: () => app.resetBone(sim.id, name) }, icon('reset'), $t('inspector.bone.reset_part')),
      h('button', { class: 'btn small', onclick: () => app.mirrorBone(sim.id, name), disabled: !/_(L|R)_/.test(name) }, icon('mirror'), $t('inspector.bone.copy_to_other_side'))));
  return sec;
}
