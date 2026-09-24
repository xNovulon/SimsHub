// Inspector cards for a face part (move / turn inside its safe range) and for a twist helper (follows by itself).
import * as THREE from 'three';
import { h, icon, slider, section } from '../ui.js';
import { simBody } from '../pipeline.js';
import { faceLimits, faceRegion, baseOf, isCenterFace, twistAngle, TWIST } from '../facekit.js';
import { $t } from '../i18n.js';

const R2D = THREE.MathUtils.radToDeg;
const AX = ['x', 'y', 'z'];

// Plain names for each axis (left end ↔ right end of the slider) and the sign that makes the slider read that way.
function axisNames(name) {
  const right = /_R_/.test(name);
  const part = (/^b__(?:CAS_)?(?:L_|R_)?(\w+?)(?:__)?$/.exec(name) || [])[1] || '';
  const side = right ? -1 : 1;                       // z is the sim's left: out on the left side, in on the right
  const move = [[$t('inspector.face.down_up'), 1], [$t('inspector.face.back_forward'), 1], [$t('inspector.face.in_out'), side]];
  // turns in the head frame (x up, y forward, z the sim's left): about x = sideways, about y = tilt, about z = nod
  const turn = [[$t('inspector.face.turn_sideways'), 1], [$t('inspector.face.tilt'), 1], [$t('inspector.face.nod'), 1]];
  if (part === 'Mouth') move[2] = [$t('inspector.face.narrow_wide'), side];
  if (name === 'b__UpLip__' || name === 'b__LoLip__') { move[1] = [$t('inspector.face.in_pout'), 1]; move[2] = [$t('inspector.face.sideways'), 1]; turn[2] = [$t('inspector.face.curl'), 1]; }
  if (part === 'UpLip' || part === 'LoLip') turn[2] = [$t('inspector.face.curl'), 1];
  if (part === 'UpLid') turn[2] = [$t('inspector.face.open_closed'), 1];
  if (part === 'LoLid') turn[2] = [$t('inspector.face.open_closed'), -1];          // the lower lid closes upward (minus)
  if (part === 'Eye') { turn[0] = [$t('inspector.face.look_right_left'), 1]; turn[2] = [$t('inspector.face.look_up_down'), 1]; }
  if (name === 'b__Jaw__') { turn[2] = [$t('inspector.face.closed_open'), -1]; move[1] = [$t('inspector.face.back_forward'), 1]; turn[0] = [$t('inspector.face.chin_sideways'), 1]; turn[1] = [$t('inspector.face.tilt'), 1]; }
  if (name === 'b__Tounge__1') move[1] = [$t('inspector.face.in_out'), 1];
  if (/^b__Tounge__/.test(name)) { move[2] = [$t('inspector.face.sideways'), 1]; turn[2] = [$t('inspector.face.curl'), 1]; }
  return { move, turn };
}

export function faceBoneSection(app, sim, view, name) {
  const lim = faceLimits(name) || { mode: 'move', move: [null, null, null], turn: [null, null, null] };
  const base = baseOf(view, name), rest = view.restByName[name];
  const names = axisNames(name);
  const sec = section([$t('inspector.face.face_part'), h('span', { class: 'count' }, $t('inspector.face.from_rest'))]);
  const off = base.p.clone().sub(rest.pos);
  const e = new THREE.Euler().setFromQuaternion(rest.quat.clone().invert().multiply(base.q), 'XYZ');
  const rows = [];
  // Move rows (mm) for each unlocked move axis
  lim.move.forEach((r, i) => {
    if (!r) return;
    const [text, sgn] = names.move[i];
    const lo = Math.min(r[0] * sgn, r[1] * sgn) * 1000, hi = Math.max(r[0] * sgn, r[1] * sgn) * 1000;
    rows.push(slider({ label: text, min: Math.floor(lo * 2) / 2, max: Math.ceil(hi * 2) / 2, step: 0.5, value: Math.round(off[AX[i]] * sgn * 2000) / 2,
      fmt: v => `${v > 0 ? '+' : ''}${(+v).toFixed(1)} mm`,
      onStart: () => app.store.checkpoint(),
      onInput: (v, done) => app.setFaceBoneAxis(sim.id, name, 'move', AX[i], (v * sgn) / 1000, done) }));
  });
  // Turn rows (degrees) for each unlocked turn axis
  lim.turn.forEach((r, i) => {
    if (!r) return;
    const [text, sgn] = names.turn[i];
    const lo = R2D(Math.min(r[0] * sgn, r[1] * sgn)), hi = R2D(Math.max(r[0] * sgn, r[1] * sgn));
    rows.push(slider({ label: text, min: Math.floor(lo), max: Math.ceil(hi), step: 0.5, value: Math.round(R2D(e[AX[i]]) * sgn * 2) / 2,
      fmt: v => `${v > 0 ? '+' : ''}${(+v).toFixed(1)}°`,
      onStart: () => app.store.checkpoint(),
      onInput: (v, done) => app.setFaceBoneAxis(sim.id, name, 'turn', AX[i], THREE.MathUtils.degToRad(v * sgn), done) }));
  });
  const moveRows = rows.slice(0, lim.move.filter(Boolean).length), turnRows = rows.slice(moveRows.length);
  if (moveRows.length) sec.append(h('div', { class: 'sub-title' }, $t('inspector.face.move')), ...moveRows);
  if (turnRows.length) sec.append(h('div', { class: 'sub-title' }, $t('inspector.face.turn')), ...turnRows);
  if (faceRegion(name) === 'eyes' && /_Eye__$/.test(name)) {
    sec.append(h('div', { class: 'btn-grid', style: { marginTop: '8px' } },
      h('button', { class: 'btn small', onclick: () => app.aimEyes(sim.id, 'partner'), disabled: app.store.project.sims.length < 2 }, icon('eye'), $t('inspector.face.look_at_partner')),
      h('button', { class: 'btn small', onclick: () => app.aimEyes(sim.id, 'camera') }, icon('eye'), $t('inspector.face.look_at_camera')),
      h('button', { class: 'btn small', onclick: () => app.aimEyes(sim.id, 'ahead') }, icon('reset'), $t('inspector.face.look_ahead'))));
  }
  sec.append(h('div', { class: 'btn-grid', style: { marginTop: '8px' } },
    h('button', { class: 'btn small', onclick: () => app.resetBone(sim.id, name) }, icon('reset'), $t('inspector.face.reset_part')),
    h('button', { class: 'btn small', disabled: isCenterFace(name), onclick: () => app.mirrorBone(sim.id, name) }, icon('mirror'), $t('inspector.face.copy_to_other_side')),
    h('button', { class: 'btn small', onclick: () => app.resetFace(sim.id) }, icon('reset'), $t('inspector.face.reset_whole_face_here'))),
  h('div', { class: 'hint' }, $t('inspector.face.face_sliders_and_expressions_are')));
  return sec;
}

export function twistSection(app, sim, view, name) {
  const t = TWIST.find(x => x.bone === name);
  const keyed = sim.keys.some(k => k.pose && k.pose.rot && k.pose.rot[name]);
  const b = simBody(sim);
  const driver = t && /Hand/.test(t.driver) ? $t('inspector.face.hand') : t && /UpperArm/.test(t.driver) ? $t('inspector.face.arm') : $t('inspector.face.leg');
  const off = t && (t.opt ? !b[t.opt] : b.twist === false);
  const sec = section([$t('inspector.face.twist_helper'), h('span', { class: 'count' }, keyed ? $t('inspector.face.posed_by_hand') : off ? 'off' : 'automatic')]);
  const rest = view.restByName[name];
  const base = baseOf(view, name);
  const now = R2D(twistAngle(rest.quat, base.q));
  sec.append(slider({ label: $t('inspector.face.twist'), min: -90, max: 90, step: 0.5, value: Math.round(now * 2) / 2, fmt: v => `${v > 0 ? '+' : ''}${(+v).toFixed(1)}°`,
    onStart: () => app.store.checkpoint(),
    onInput: (v, done) => app.setBoneTwist(sim.id, name, THREE.MathUtils.degToRad(v), done) }));
  if (keyed) {
    sec.append(h('div', { class: 'hint' }, $t('inspector.face.you_turned_it_by_hand')),
      h('button', { class: 'btn small block', onclick: () => app.unkeyTwist(sim.id, name) }, icon('reset'), $t('inspector.face.let_it_follow_again')));
  } else if (off) {
    sec.append(h('div', { class: 'hint' }, t.opt ? $t('inspector.face.smooth_hip_twist_is_off') : $t('inspector.face.smooth_wrists_and_shoulders_is')));
  } else {
    sec.append(h('div', { class: 'hint' }, $t('inspector.face.follows_by_itself', { driver })));
  }
  return sec;
}
