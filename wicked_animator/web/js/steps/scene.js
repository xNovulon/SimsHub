// Step 1, Scene: the sims and where it happens.
import { h, icon, contextMenu, section, tip } from '../ui.js';
import { BODY_TYPES } from '../state.js';
import { nice } from './common.js';
import { spotsOf } from '../placing.js';
import { $t } from '../i18n.js';

const FURN_ICON = { floor: 'scene', double_bed: 'bed', single_bed: 'bed', sofa: 'bed', loveseat: 'bed', chair_living: 'pose', chair_dining: 'pose', counter: 'scene', table_dining: 'scene', wall: 'scene' };

// "3 keys" counts the body's keys (like the timeline's lane); face keys between them are counted apart
const keyCount = s => {
  const body = s.keys.filter(k => !k.faceOnly).length, faceOnly = s.keys.length - body;
  return $t('steps.scene.n_keys', { n: body }) + (faceOnly ? $t('steps.scene.face_keys', { faceOnly }) : '');
};

export function renderScene(app, root) {
  const p = app.store.project;
  const list = h('div', { class: 'card-list' });
  p.sims.forEach((s, k) => {
    const active = s.id === app.store.selected.sim;
    const bt = BODY_TYPES[s.frame] || BODY_TYPES.yf;
    const card = h('div', { class: 'sim-card' + (active ? ' active' : ''), style: { '--sim': s.color }, onclick: () => app.selectSim(s.id) },
      h('div', { class: 'sim-avatar' }, bt.short),
      h('div', { class: 'meta' }, h('b', {}, s.label), h('span', {}, `${bt.label}${s.tray ? ' · ' + s.tray.name : ''} · ${keyCount(s)}${(s.layers || []).length ? $t('steps.scene.n_motions', { n: s.layers.length }) : ''}`)),
      h('div', { class: 'row-actions' },
        h('button', { class: 'icon-btn sm', title: s.visible === false ? $t('steps.scene.show') : $t('steps.scene.hide'), onclick: e => { e.stopPropagation(); app.toggleVisible(s.id); } }, icon(s.visible === false ? 'eye-off' : 'eye')),
        h('button', { class: 'icon-btn sm', title: $t('steps.scene.more'), onclick: e => { e.stopPropagation(); simMenu(app, s, e.clientX, e.clientY); } }, icon('dots'))));
    if (s.visible === false) card.style.opacity = '0.55';
    list.append(card);
  });
  if (!p.sims.length) list.append(h('div', { class: 'empty' }, $t('steps.scene.no_sims_yet_add_one')));
  root.append(section([$t('steps.scene.sims'), h('span', { class: 'count' }, `${p.sims.length}`)], list));

  root.append(section($t('steps.scene.add_sim'), h('div', { class: 'add-grid' },
    h('button', { class: 'add-tile', onclick: () => app.addSim('yf') }, icon('user'), $t('steps.scene.female')),
    h('button', { class: 'add-tile', onclick: () => app.addSim('ym') }, icon('user'), $t('steps.scene.male')),
    h('button', { class: 'add-tile', onclick: () => app.addSim('yf_futa'), title: $t('steps.scene.female_body_with_wickedwhims_penis') }, icon('user'), $t('steps.scene.female_penis'))),
  h('button', { class: 'btn block', style: { marginTop: '8px' }, onclick: () => app.openTray() }, icon('folder'), $t('steps.scene.use_sim_from_my_tray'))));

  const grid = h('div', { class: 'furniture-grid' });
  for (const f of app.furniture) {
    grid.append(h('button', { class: 'furn' + (f.id === p.furniture ? ' active' : ''), onclick: () => app.setFurniture(f.id), title: $t('steps.scene.offered_by_wickedwhims_on', { locations: f.locations.join(', ') }) },
      h('span', { class: 'glyph' }, icon(FURN_ICON[f.id] || 'scene')), f.label));
  }
  // the object's own seats and lying spots (once its data has arrived): the Place tool shows them on the furniture
  const info = app._furnInfoKnown && p.furniture ? app._furnInfoKnown.get(p.furniture) : null;
  const spots = info ? spotsOf(info) : [];
  const count = k => spots.filter(x => x.action === k).length;
  root.append(section($t('steps.scene.where_it_happens'), grid,
    h('div', { class: 'hint' }, $t('steps.scene.wickedwhims_will_offer_it_on'), h('b', {}, (p.locations || []).map(nice).join(', ') || '-'), $t('steps.scene.pink_ring_is_object_s')),
    spots.length ? h('div', { class: 'hint' }, h('b', {}, [count('sit') ? $t('steps.scene.n_seats', { n: count('sit') }) : '', count('lie') ? $t('steps.scene.n_lying_spots', { n: count('lie') }) : ''].filter(Boolean).join(' · ')),
      $t('steps.scene.press'), h('kbd', {}, 'M'), $t('steps.scene.place_and_click_one_selected')) : null));
  root.append(tip($t('steps.scene.next_pick_ready_made_pose')));
}

function simMenu(app, s, x, y) {
  contextMenu(x, y, [
    { heading: $t('steps.scene.body') },
    ...Object.entries(BODY_TYPES).map(([k, bt]) => ({ label: bt.label, checked: s.frame === k, onClick: () => app.setSimBody(s.id, k) })),
    '-',
    { label: $t('steps.scene.duplicate'), icon: 'copy', onClick: () => app.duplicateSim(s.id) },
    { label: $t('steps.scene.clear_all_keys'), icon: 'reset', onClick: () => app.clearKeys(s.id) },
    '-',
    { label: $t('steps.scene.remove_sim'), danger: true, icon: 'trash', onClick: () => app.removeSim(s.id) },
  ]);
}
