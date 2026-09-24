// The right panel: what is selected and what you can do with it right now. Other features append their own cards
// through app.hooks.inspector.
import { h, icon, toast } from '../ui.js';
import { BODY_TYPES } from '../state.js';
import { label } from '../facekit.js';
import { boneList } from '../outliner.js';
import { boneSection } from './bone.js';
import { keySection } from './key.js';
import { pinSection } from './pin.js';
import { bodyQuickSection, simSection } from './sim.js';

let lastSel = '';

export function renderInspector(app) {
  const root = document.getElementById('inspector');
  if (!root) return;
  // the cards cross-fade when the selection changes (not on every redraw)
  const selKey = `${app.store.selected.sim}|${app.store.selected.bone}`;
  if (selKey !== lastSel && lastSel) {
    root.classList.remove('swap'); void root.offsetWidth; root.classList.add('swap');
    clearTimeout(root._swapT); root._swapT = setTimeout(() => root.classList.remove('swap'), 200);
  }
  lastSel = selKey;
  root.innerHTML = '';
  const sim = app.store.sim();
  if (!sim) {
    root.append(h('div', { class: 'section' }, h('div', { class: 'section-title' }, 'Getting started'),
      h('div', { class: 'card' },
        h('p', { style: { marginTop: 0 } }, h('b', {}, '1 · Scene'), ' - add the sims and pick where it happens.'),
        h('p', {}, h('b', {}, '2 · Pose'), ' - one click on a ready pose, then adjust.'),
        h('p', {}, h('b', {}, '3 · Motion'), ' - add Thrust / Ride / Head bob, or key poses over time.'),
        h('p', {}, h('b', {}, '4-6'), ' - body, face and sounds are mostly automatic.'),
        h('p', { style: { marginBottom: 0 } }, h('b', {}, '7-8'), ' - name it, then Send to game.')),
      h('div', { class: 'hint' }, 'Click a sim in the 3D view to select it. Press ', h('kbd', {}, '?'), ' for all controls.')));
    return;
  }
  const view = app.simViews.get(sim.id);
  const bone = app.store.selected.bone;
  const bt = BODY_TYPES[sim.frame] || BODY_TYPES.yf;
  const copy = e => {
    e.stopPropagation();
    const text = e.currentTarget.textContent;
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(() => toast(`Copied "${text}".`), () => toast(text));
  };
  root.append(h('div', { class: 'insp-head', style: { '--sim': sim.color } }, h('div', { class: 'swatch' }, bt.short),
    h('div', {}, h('b', {}, sim.label), h('span', {}, bone ? label(bone, sim.frame) : 'Whole sim - click a body part'),
      bone ? h('code', { class: 'raw-name', title: 'Name in Blender and the game - click to copy', onclick: copy }, bone) : null)));
  if (view) root.append(boneList(app, sim, view));

  if (bone && view && view.bone(bone)) root.append(boneSection(app, sim, view, bone));
  root.append(keySection(app, sim));
  root.append(pinSection(app, sim));
  root.append(bodyQuickSection(app, sim, view));
  root.append(simSection(app, sim));
  if (app.runHook) {
    const key = sim.keys.find(k => k.frame === Math.round(app.store.frame)) || null;
    app.runHook('inspector', app, root, { sim, bone, key });
  }
}

// "/" : open the bone list and put the cursor in its search box.
export function focusBoneSearch() {
  const el = document.getElementById('bone-list');
  if (el && el._focusSearch) { el._focusSearch(); return true; }
  return false;
}
