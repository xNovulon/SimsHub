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
import { $t } from '../i18n.js';

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
    root.append(h('div', { class: 'section' }, h('div', { class: 'section-title' }, $t('inspector.index.getting_started')),
      h('div', { class: 'card' },
        h('p', { style: { marginTop: 0 } }, h('b', {}, $t('inspector.index.1_scene')), $t('inspector.index.add_sims_and_pick_where')),
        h('p', {}, h('b', {}, $t('inspector.index.2_pose')), $t('inspector.index.one_click_on_ready_pose')),
        h('p', {}, h('b', {}, $t('inspector.index.3_motion')), $t('inspector.index.add_thrust_ride_head_bob')),
        h('p', {}, h('b', {}, '4-6'), $t('inspector.index.body_face_and_sounds_are')),
        h('p', { style: { marginBottom: 0 } }, h('b', {}, '7-8'), $t('inspector.index.name_it_then_send_to'))),
      h('div', { class: 'hint' }, $t('inspector.index.click_sim_in_3d_view'), h('kbd', {}, '?'), $t('inspector.index.for_all_controls'))));
    return;
  }
  const view = app.simViews.get(sim.id);
  const bone = app.store.selected.bone;
  const bt = BODY_TYPES[sim.frame] || BODY_TYPES.yf;
  const copy = e => {
    e.stopPropagation();
    const text = e.currentTarget.textContent;
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(() => toast($t('inspector.index.copied', { text })), () => toast(text));
  };
  root.append(h('div', { class: 'insp-head', style: { '--sim': sim.color } }, h('div', { class: 'swatch' }, bt.short),
    h('div', {}, h('b', {}, sim.label), h('span', {}, bone ? label(bone, sim.frame) : $t('inspector.index.whole_sim_click_body_part')),
      bone ? h('code', { class: 'raw-name', title: $t('inspector.index.name_in_blender_and_game'), onclick: copy }, bone) : null)));
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
