// Inspector cards for a face part (move / turn inside its safe range) and for a twist helper (follows by itself).
import * as THREE from 'three';
import { h, icon, slider, section } from '../ui.js';
import { simBody } from '../pipeline.js';
import { faceLimits, faceRegion, baseOf, isCenterFace, twistAngle, TWIST } from '../facekit.js';

const R2D = THREE.MathUtils.radToDeg;
const AX = ['x', 'y', 'z'];

// Plain names for each axis (left end ↔ right end of the slider) and the sign that makes the slider read that way.
function axisNames(name) {
  const right = /_R_/.test(name);
  const part = (/^b__(?:CAS_)?(?:L_|R_)?(\w+?)(?:__)?$/.exec(name) || [])[1] || '';
  const side = right ? -1 : 1;                       // z is the sim's left: out on the left side, in on the right
  const move = [['Down ↔ Up', 1], ['Back ↔ Forward', 1], ['In ↔ Out', side]];
  // turns in the head frame (x up, y forward, z the sim's left): about x = sideways, about y = tilt, about z = nod
  const turn = [['Turn sideways', 1], ['Tilt', 1], ['Nod', 1]];
  if (part === 'Mouth') move[2] = ['Narrow ↔ Wide', side];
  if (name === 'b__UpLip__' || name === 'b__LoLip__') { move[1] = ['In ↔ Pout', 1]; move[2] = ['Sideways', 1]; turn[2] = ['Curl', 1]; }
  if (part === 'UpLip' || part === 'LoLip') turn[2] = ['Curl', 1];
  if (part === 'UpLid') turn[2] = ['Open ↔ Closed', 1];
  if (part === 'LoLid') turn[2] = ['Open ↔ Closed', -1];          // the lower lid closes upward (minus)
  if (part === 'Eye') { turn[0] = ['Look right ↔ left', 1]; turn[2] = ['Look up ↔ down', 1]; }
  if (name === 'b__Jaw__') { turn[2] = ['Closed ↔ Open', -1]; move[1] = ['Back ↔ Forward', 1]; turn[0] = ['Chin sideways', 1]; turn[1] = ['Tilt', 1]; }
  if (name === 'b__Tounge__1') move[1] = ['In ↔ Out', 1];
  if (/^b__Tounge__/.test(name)) { move[2] = ['Sideways', 1]; turn[2] = ['Curl', 1]; }
  return { move, turn };
}

export function faceBoneSection(app, sim, view, name) {
  const lim = faceLimits(name) || { mode: 'move', move: [null, null, null], turn: [null, null, null] };
  const base = baseOf(view, name), rest = view.restByName[name];
  const names = axisNames(name);
  const sec = section(['Face part', h('span', { class: 'count' }, 'from rest')]);
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
  if (moveRows.length) sec.append(h('div', { class: 'sub-title' }, 'Move'), ...moveRows);
  if (turnRows.length) sec.append(h('div', { class: 'sub-title' }, 'Turn'), ...turnRows);
  if (faceRegion(name) === 'eyes' && /_Eye__$/.test(name)) {
    sec.append(h('div', { class: 'btn-grid', style: { marginTop: '8px' } },
      h('button', { class: 'btn small', onclick: () => app.aimEyes(sim.id, 'partner'), disabled: app.store.project.sims.length < 2 }, icon('eye'), 'Look at partner'),
      h('button', { class: 'btn small', onclick: () => app.aimEyes(sim.id, 'camera') }, icon('eye'), 'Look at camera'),
      h('button', { class: 'btn small', onclick: () => app.aimEyes(sim.id, 'ahead') }, icon('reset'), 'Look ahead')));
  }
  sec.append(h('div', { class: 'btn-grid', style: { marginTop: '8px' } },
    h('button', { class: 'btn small', onclick: () => app.resetBone(sim.id, name) }, icon('reset'), 'Reset part'),
    h('button', { class: 'btn small', disabled: isCenterFace(name), onclick: () => app.mirrorBone(sim.id, name) }, icon('mirror'), 'Copy to other side'),
    h('button', { class: 'btn small', onclick: () => app.resetFace(sim.id) }, icon('reset'), 'Reset whole face here')),
  h('div', { class: 'hint' }, 'The face sliders and expressions are added on top of this.'));
  return sec;
}

export function twistSection(app, sim, view, name) {
  const t = TWIST.find(x => x.bone === name);
  const keyed = sim.keys.some(k => k.pose && k.pose.rot && k.pose.rot[name]);
  const b = simBody(sim);
  const driver = t && /Hand/.test(t.driver) ? 'the hand' : t && /UpperArm/.test(t.driver) ? 'the arm' : 'the leg';
  const off = t && (t.opt ? !b[t.opt] : b.twist === false);
  const sec = section(['Twist helper', h('span', { class: 'count' }, keyed ? 'posed by hand' : off ? 'off' : 'automatic')]);
  const rest = view.restByName[name];
  const base = baseOf(view, name);
  const now = R2D(twistAngle(rest.quat, base.q));
  sec.append(slider({ label: 'Twist', min: -90, max: 90, step: 0.5, value: Math.round(now * 2) / 2, fmt: v => `${v > 0 ? '+' : ''}${(+v).toFixed(1)}°`,
    onStart: () => app.store.checkpoint(),
    onInput: (v, done) => app.setBoneTwist(sim.id, name, THREE.MathUtils.degToRad(v), done) }));
  if (keyed) {
    sec.append(h('div', { class: 'hint' }, 'You turned it by hand, so it no longer follows.'),
      h('button', { class: 'btn small block', onclick: () => app.unkeyTwist(sim.id, name) }, icon('reset'), 'Let it follow again'));
  } else if (off) {
    sec.append(h('div', { class: 'hint' }, t.opt ? 'Smooth hip twist is off for this sim (step 4, Body), so it stays still unless you turn it.' : 'Smooth wrists and shoulders is off for this sim (step 4, Body), so it stays still unless you turn it.'));
  } else {
    sec.append(h('div', { class: 'hint' }, `Follows ${driver} by itself.`));
  }
  return sec;
}
