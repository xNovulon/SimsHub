// Step 1, Scene: the sims and where it happens.
import { h, icon, contextMenu, section, tip } from '../ui.js';
import { BODY_TYPES } from '../state.js';
import { nice } from './common.js';
import { spotsOf } from '../placing.js';

const FURN_ICON = { floor: 'scene', double_bed: 'bed', single_bed: 'bed', sofa: 'bed', loveseat: 'bed', chair_living: 'pose', chair_dining: 'pose', counter: 'scene', table_dining: 'scene', wall: 'scene' };

// "3 keys" counts the body's keys (like the timeline's lane); face keys between them are counted apart
const keyCount = s => {
  const body = s.keys.filter(k => !k.faceOnly).length, faceOnly = s.keys.length - body;
  return `${body} key${body === 1 ? '' : 's'}${faceOnly ? ` · ${faceOnly} face key${faceOnly === 1 ? '' : 's'}` : ''}`;
};

export function renderScene(app, root) {
  const p = app.store.project;
  const list = h('div', { class: 'card-list' });
  p.sims.forEach((s, k) => {
    const active = s.id === app.store.selected.sim;
    const bt = BODY_TYPES[s.frame] || BODY_TYPES.yf;
    const card = h('div', { class: 'sim-card' + (active ? ' active' : ''), style: { '--sim': s.color }, onclick: () => app.selectSim(s.id) },
      h('div', { class: 'sim-avatar' }, bt.short),
      h('div', { class: 'meta' }, h('b', {}, s.label), h('span', {}, `${bt.label}${s.tray ? ' · ' + s.tray.name : ''} · ${keyCount(s)}${(s.layers || []).length ? ' · ' + s.layers.length + ' motion' : ''}`)),
      h('div', { class: 'row-actions' },
        h('button', { class: 'icon-btn sm', title: s.visible === false ? 'Show' : 'Hide', onclick: e => { e.stopPropagation(); app.toggleVisible(s.id); } }, icon(s.visible === false ? 'eye-off' : 'eye')),
        h('button', { class: 'icon-btn sm', title: 'More', onclick: e => { e.stopPropagation(); simMenu(app, s, e.clientX, e.clientY); } }, icon('dots'))));
    if (s.visible === false) card.style.opacity = '0.55';
    list.append(card);
  });
  if (!p.sims.length) list.append(h('div', { class: 'empty' }, 'No sims yet - add one below.'));
  root.append(section(['Sims', h('span', { class: 'count' }, `${p.sims.length}`)], list));

  root.append(section('Add a sim', h('div', { class: 'add-grid' },
    h('button', { class: 'add-tile', onclick: () => app.addSim('yf') }, icon('user'), 'Female'),
    h('button', { class: 'add-tile', onclick: () => app.addSim('ym') }, icon('user'), 'Male'),
    h('button', { class: 'add-tile', onclick: () => app.addSim('yf_futa'), title: 'A female body with WickedWhims\' penis' }, icon('user'), 'Female + penis')),
  h('button', { class: 'btn block', style: { marginTop: '8px' }, onclick: () => app.openTray() }, icon('folder'), 'Use a sim from my Tray')));

  const grid = h('div', { class: 'furniture-grid' });
  for (const f of app.furniture) {
    grid.append(h('button', { class: 'furn' + (f.id === p.furniture ? ' active' : ''), onclick: () => app.setFurniture(f.id), title: 'Offered by WickedWhims on: ' + f.locations.join(', ') },
      h('span', { class: 'glyph' }, icon(FURN_ICON[f.id] || 'scene')), f.label));
  }
  // the object's own seats and lying spots (once its data has arrived): the Place tool shows them on the furniture
  const info = app._furnInfoKnown && p.furniture ? app._furnInfoKnown.get(p.furniture) : null;
  const spots = info ? spotsOf(info) : [];
  const count = k => spots.filter(x => x.action === k).length;
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  root.append(section('Where it happens', grid,
    h('div', { class: 'hint' }, `WickedWhims will offer it on: `, h('b', {}, (p.locations || []).map(nice).join(', ') || '-'), '. The pink ring is the object\'s centre. Add more places in Details.'),
    spots.length ? h('div', { class: 'hint' }, h('b', {}, [count('sit') ? plural(count('sit'), 'seat') : '', count('lie') ? plural(count('lie'), 'lying spot') : ''].filter(Boolean).join(' · ')),
      ' - press ', h('kbd', {}, 'M'), ' (Place) and click one: the selected sim sits or lies exactly there.') : null));
  root.append(tip('Next, pick a ready-made pose in step 2 - both sims are placed for you, then you only fine-tune.'));
}

function simMenu(app, s, x, y) {
  contextMenu(x, y, [
    { heading: 'Body' },
    ...Object.entries(BODY_TYPES).map(([k, bt]) => ({ label: bt.label, checked: s.frame === k, onClick: () => app.setSimBody(s.id, k) })),
    '-',
    { label: 'Duplicate', icon: 'copy', onClick: () => app.duplicateSim(s.id) },
    { label: 'Clear all keys', icon: 'reset', onClick: () => app.clearKeys(s.id) },
    '-',
    { label: 'Remove sim', danger: true, icon: 'trash', onClick: () => app.removeSim(s.id) },
  ]);
}
