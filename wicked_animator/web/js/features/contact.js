// Hold on to the partner, hand shapes and natural limits (build plan R2-2): the app methods other parts call
// (app.makeHold, app.holdNamed, app.holdNearest, app.letGo, app.bakePin, app.setPinRange, app.setHandShape,
// app.setHandSlider, app.setNaturalLimits, app.setTurnGroup), the palette commands, the help rows, and the
// clean-up of holds whose partner is gone. Everything plugs in through app.hooks (plan 2.4) - main.js is untouched.
import { toast, addIcon } from '../ui.js';
import { localStorageGet, localStorageSet } from '../state.js';
import { LIMBS, LIMB_LABEL, isHold, TURN_GROUPS } from '../bones.js';
import * as Holds from '../holds.js';
import { HAND_SHAPES, SHAPE_ORDER, applyHandShape, setCurl, setSpread, setThumb, handSide } from '../hands.js';
import { $t } from '../i18n.js';

const SIDE_WORD = { L: 'left', R: 'right' };
const ICONS = {
  hand: '<path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V12M11 11V4a1.5 1.5 0 0 1 3 0v7M14 11V5a1.5 1.5 0 0 1 3 0v8M17 13v-5a1.5 1.5 0 0 1 3 0v6.5c0 4.1-2.9 7.5-7 7.5h-.6a6.6 6.6 0 0 1-5.4-2.9L4.1 14.8a1.6 1.6 0 0 1 2.5-2L8 14.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  grab: '<path d="M7 11.5V9a1.5 1.5 0 0 1 3 0v2M10 10.5V8a1.5 1.5 0 0 1 3 0v2.5M13 10.5V9a1.5 1.5 0 0 1 3 0v2M16 11v-.5a1.5 1.5 0 0 1 3 0V14c0 3.9-2.7 7-6.5 7h-.4a6 6 0 0 1-4.9-2.6L4.5 15a1.6 1.6 0 0 1 2.5-1.9L7 13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 4.5c3 2 5 2 9 0s6-2 9 0" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" opacity=".7"/>',
  limit: '<path d="M4 18a8 8 0 0 1 16 0" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M12 18 7.5 9.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M4 18h3M17 18h3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="18" r="1.6" fill="currentColor"/>',
  letgo: '<path d="M8 12V6.5a1.5 1.5 0 0 1 3 0V11M11 10V5a1.5 1.5 0 0 1 3 0v6M14 10.5V6a1.5 1.5 0 0 1 3 0v7M17 12V9.5a1.5 1.5 0 0 1 3 0V14c0 4-2.8 7-6.8 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 21 10 14M3 14l7 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" opacity=".8"/>',
};

export function install(app) {
  if (!app || app.__contact) return;
  app.__contact = true;
  for (const [id, svg] of Object.entries(ICONS)) { try { addIcon(id, svg); } catch { /* the sprite sheet is not there (a bare test page) */ } }
  const hooks = app.hooks || {};
  const add = (name, fn) => { if (Array.isArray(hooks[name])) hooks[name].push(fn); };

  // ---------------------------------------------------------------- settings (browser only)
  if (app.naturalLimits === undefined) app.naturalLimits = localStorageGet('limits', true) !== false;
  if (app.turnGroup === undefined) app.turnGroup = localStorageGet('turnGroup', 'none');
  if (!TURN_GROUPS[app.turnGroup]) app.turnGroup = 'none';
  if (app.handsBoth === undefined) app.handsBoth = !!localStorageGet('handsBoth', false);
  const mixin = (name, fn) => { if (typeof app[name] !== 'function') app[name] = fn; };

  mixin('setNaturalLimits', on => {
    app.naturalLimits = !!on;
    localStorageSet('limits', app.naturalLimits);
    const sel = app.store.selected;
    if (sel.sim && sel.bone && app.interact.tool === 'rotate' && app.interact.active && app.interact.active.kind === 'bone') app.interact.selectBone(sel.sim, sel.bone);
    app.refreshPanels();
    toast(on ? $t('features.contact.natural_limits_on_fingers_elbows') : $t('features.contact.natural_limits_off_every_part'));
  });
  mixin('setTurnGroup', g => {
    app.turnGroup = TURN_GROUPS[g] ? g : 'none';
    localStorageSet('turnGroup', app.turnGroup);
    app.refreshPanels();
  });
  mixin('setHandsBoth', on => { app.handsBoth = !!on; localStorageSet('handsBoth', app.handsBoth); app.refreshPanels(); });

  // ---------------------------------------------------------------- holds and pins
  mixin('makeHold', (simId, limb, other, hit, opts) => Holds.makeHold(app, simId, limb, other, hit, opts));
  mixin('holdNamed', (simId, limb, otherId, grabKey, opts) => Holds.holdNamed(app, simId, limb, otherId, grabKey, opts));
  mixin('holdNearest', (simId, limb) => Holds.holdNearest(app, simId, limb));
  mixin('letGo', (simId, limb) => Holds.letGo(app, simId, limb));
  mixin('bakePin', (simId, limb) => Holds.bakePin(app, simId, limb));
  mixin('setPinRange', (simId, limb, from, to, fade) => Holds.setPinRange(app, simId, limb, from, to, fade));
  mixin('pinFor', (simId, limb, opts) => Holds.setPin(app, simId, limb, opts));
  mixin('rebindHold', (simId, limb) => Holds.rebindHold(app, simId, limb));

  // ---------------------------------------------------------------- hand shapes
  // A shape on one hand (and the other with "Same for both hands"), at this frame, as a key.
  mixin('setHandShape', (simId, side, id, { both = app.handsBoth, amount = 1 } = {}) => {
    const sim = app.store.sim(simId), v = app.simViews.get(simId), sh = HAND_SHAPES[id];
    if (!sim || !v || !sh) return false;
    app.store.checkpoint($t('features.contact.hand_shape', { shLabel: sh.label }));
    app.beginEdit(simId);
    const sides = both ? ['L', 'R'] : [side];
    for (const s of sides) applyHandShape(v, s, id, amount);
    app.pipeline.pins({ sim, v }, Math.round(app.store.frame));
    app.poseEdited(simId, false);
    app.afterEdit();
    toast(both ? $t('features.contact.shape_on_both_hands', { shape: sh.label }) : side === 'L' ? $t('features.contact.shape_on_left_hand', { shape: sh.label }) : $t('features.contact.shape_on_right_hand', { shape: sh.label }), 'ok');
    return true;
  });
  // Curl / Spread / Thumb (live while dragging, a key when released).
  mixin('setHandSlider', (simId, side, kind, value, live = false) => {
    const sim = app.store.sim(simId), v = app.simViews.get(simId);
    const fn = { curl: setCurl, spread: setSpread, thumb: setThumb }[kind];
    if (!sim || !v || !fn) return false;
    app.beginEdit(simId);
    for (const s of app.handsBoth ? ['L', 'R'] : [side]) fn(v, s, value);
    app.poseEdited(simId, live);
    if (!live) app.afterEdit();
    return true;
  });

  // ---------------------------------------------------------------- clean-up
  // a hold on a sim that is gone (removed, or a project saved with one) is dropped
  add('projectLoaded', p => { Holds.cleanHolds(p); });
  add('simRemoved', (id, p) => { if (Holds.cleanHolds(p, id)) { app.interact && app.interact.refreshHandles(); } });

  // ---------------------------------------------------------------- palette (Ctrl+K) and help (?)
  add('commands', a => {
    const sim = a.store.sim(), id = sim && sim.id, when = () => !!a.store.sim();
    const others = sim ? a.store.project.sims.filter(s => s.id !== id) : [];
    const out = [];
    if (sim && others.length) {
      for (const limb of Object.keys(LIMBS)) {
        const pin = sim.pins && sim.pins[limb];
        if (isHold(pin)) {
          out.push({ group: $t('features.contact.hold_on'), id: `letgo-${limb}`, label: $t('features.contact.let_go', { v: LIMB_LABEL[limb] }), icon: 'letgo', sub: Holds.holdText(a, pin), words: 'release hold free unpin', run: () => a.letGo(id, limb), when });
          out.push({ group: $t('features.contact.hold_on'), id: `bakepin-${limb}`, label: $t('features.contact.let_go_keep_look', { v: LIMB_LABEL[limb] }), icon: 'letgo', sub: $t('features.contact.turn_hold_into_keys'), words: 'bake hold keys release', run: () => a.bakePin(id, limb), when });
        } else {
          out.push({ group: $t('features.contact.hold_on'), id: `hold-${limb}`, label: $t('features.contact.hold_nearest_partner', { v: LIMB_LABEL[limb] }), icon: 'grab', sub: $t('features.contact.nearest_skin_within_30_cm'), words: 'hold grab touch partner stick child of attach', run: () => a.holdNearest(id, limb), when });
        }
      }
    }
    out.push({ group: $t('features.contact.tools'), id: 'natural-limits', label: a.naturalLimits ? $t('features.contact.natural_limits_off') : $t('features.contact.natural_limits_on'), icon: 'limit', sub: $t('features.contact.fingers_elbows_knees_back_and'), words: 'joint limits clamp constraint range rotation limit', run: () => a.setNaturalLimits(!a.naturalLimits) });
    const sel = a.store.selected, side = handSide(sel.bone);
    if (sim) {
      for (const sh of SHAPE_ORDER) {
        const s = side || 'R';
        out.push({ group: $t('features.contact.hands'), id: `hand-${sh}`, label: $t('features.contact.hand_shape_2', { vLabel: HAND_SHAPES[sh].label }), icon: 'hand', sub: a.handsBoth ? $t('features.contact.both_hands') : s === 'L' ? $t('features.contact.left_hand') : $t('features.contact.right_hand'), words: `fingers pose ${HAND_SHAPES[sh].tip || ''}`, run: () => a.setHandShape(id, s, sh), when });
      }
    }
    for (const [g, G] of Object.entries(TURN_GROUPS)) {
      out.push({ group: $t('features.contact.tools'), id: `turn-${g}`, label: a.turnGroup === g ? $t('features.contact.off', { GLabel: G.label }) : $t('features.contact.turn_together', { GLabel: G.label }), icon: 'rotate', sub: $t('features.contact.one_turn_spread_over_chain'), words: 'spine chain bend together', run: () => a.setTurnGroup(a.turnGroup === g ? 'none' : g) });
    }
    return out;
  });
  add('helpRows', () => [
    { group: $t('features.contact.hold_on_to_partner'), keys: 'Drag tool (G)', text: $t('features.contact.drop_hand_or_foot_on') },
    { group: $t('features.contact.hold_on_to_partner'), keys: ['Alt', 'click'], text: $t('features.contact.on_hand_or_foot_dot') },
    { group: $t('features.contact.hold_on_to_partner'), keys: 'Hold Alt while dragging', text: $t('features.contact.turn_part_past_its_natural') },
  ]);

  // for checks and the console
  window.wickedContact = { Holds, limbs: Object.keys(LIMBS) };
}

export default install;
