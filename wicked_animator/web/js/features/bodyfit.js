// "Fit hands to each sim's body" (experimental, off by default; the switch is in Send to game, the choice is kept in
// the animation as project.fitBodies). When it is on, the baked animation tells the exporter which hands and feet
// hold on to a partner for the whole loop (backend/exporter.py ik_parts): their clips get an in-game IK target, so the
// game bends that arm or leg until the hand or foot reaches the spot it held in the editor, whatever the sim's own
// proportions. The partner's body is not followed (WickedWhims plays each sim's clip on its own). Holds that last
// only part of the loop are listed as skipped.
import { LIMBS, isHold } from '../bones.js';

export const FIT_TITLE = 'Fit hands to each sim’s body (experimental – test in game)';
export const FIT_TEXT = 'Hands and feet that hold a partner for the whole loop get an in-game IK target, so each sim\u2019s arm '
  + 'or leg bends to reach the spot recorded here - not the partner\u2019s own body, which WickedWhims clips can\u2019t '
  + 'point to. Needs a check in the game.';

// {fit: [{sim, limb}], partial: [{sim, limb}]}: the holds a project would fit, and the ones it would skip
export function fitHolds(p) {
  const fit = [], partial = [];
  (p.sims || []).forEach((s, i) => {
    for (const [limb, pin] of Object.entries(s.pins || {})) {
      if (!LIMBS[limb] || !isHold(pin) || !(p.sims || []).some(o => o.id === pin.sim)) continue;
      const whole = pin.from === undefined || pin.from === null || pin.to === undefined || pin.to === null;
      (whole ? fit : partial).push({ sim: i, limb });
    }
  });
  return { fit, partial };
}

export function install(app) {
  if (!app || app.__bodyfit) return;
  app.__bodyfit = true;
  const hooks = app.hooks || {};
  const add = (name, fn) => { if (Array.isArray(hooks[name])) hooks[name].push(fn); };

  add('bake', (payload, p) => {
    if (!p || !p.fitBodies || !Array.isArray(payload.actors)) return;
    payload.fitBodies = true;
    const { fit, partial } = fitHolds(p);
    for (const { sim, limb } of fit) {
      const a = payload.actors[sim];
      if (a) (a.ik = a.ik || []).push({ limb });
    }
    for (const { sim, limb } of partial) {
      const a = payload.actors[sim];
      if (a) (a.ikSkipped = a.ikSkipped || []).push(limb);
    }
  });

  add('exportChecks', p => {
    if (!p || !p.fitBodies) return [];
    const { fit } = fitHolds(p);
    return fit.length ? [] : [{ level: 'warn', text: '"Fit hands to each sim’s body" is on, but no hand or foot holds on to a partner for the whole loop, so nothing is fitted.' }];
  });
}

export default install;
