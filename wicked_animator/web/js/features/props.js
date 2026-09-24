// Props (spec_bodies 10): objects a sim holds or that stand in the scene - a glass, a phone, a whip... any prop the
// WickedWhims animations on this PC use, from the game or from Mods (/api/props, adults only).
//
// A prop is shown on the stage as the real object (/api/prop_mesh; a small stand-in box when its mesh can't be read),
// held in a sim's hand (it follows the hand's prop bone every frame) or standing still. "Move" puts the gizmo on it;
// a held prop keeps where it sits in the hand. Send to game writes each prop's movement as its own clip with the
// animation (backend/exporter.prop_resources): project.props -> the baked `props` [{guid, name, source, track}]
// (web/js/proptrack.js works out the track from the baked sims, the way the game plays them).
// Entry points: the Scene step's "Props" section and Ctrl+K "Add a prop".
import * as THREE from 'three';
import { h, icon, modal, toast, section, addIcon } from '../ui.js';
import { uid } from '../state.js';
import { fetchJson, plainError } from '../gamehelp.js';
import { propTrack } from '../proptrack.js';
import { $t } from '../i18n.js';

const ICONS = {
  'prop': '<path d="M8 3.5h8l-1 7.2a3 3 0 0 1-3 2.6 3 3 0 0 1-3-2.6z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M12 13.3v6.2M8.5 20.5h7" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M8.6 7.5h6.8" stroke="currentColor" stroke-width="1.4" opacity=".6"/>',
};
const HANDS = [['R', $t('features.props.right_hand')], ['L', $t('features.props.left_hand')]];
const handBone = (v, side) => (v && v.bone(`b__${side}_Prop__`) ? `b__${side}_Prop__` : `b__${side}_Hand__`);
const texLoader = new THREE.TextureLoader();
const meshCache = new Map();        // guid -> Promise<{obj, standIn} | null>

// ---------------------------------------------------------------- the prop's 3D object
function buildMesh(obj) {
  const g = new THREE.Group();
  for (const m of obj.meshes || []) {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(m.positions, 3));
    if (m.normals && m.normals.length) geo.setAttribute('normal', new THREE.Float32BufferAttribute(m.normals, 3));
    if (m.uvs && m.uvs.length) geo.setAttribute('uv', new THREE.Float32BufferAttribute(m.uvs, 2));
    geo.setIndex(m.faces);
    if (!m.normals || !m.normals.length) geo.computeVertexNormals();
    const mat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.6, metalness: 0, side: THREE.DoubleSide,
      transparent: !!m.transparent, opacity: m.transparent ? 0.6 : 1 });
    if (m.texture) {
      const tex = texLoader.load('/api/furniture_tex?file=' + encodeURIComponent(m.texture));
      tex.colorSpace = THREE.SRGBColorSpace; tex.flipY = !!m.flipY;
      mat.map = tex;
    } else mat.color.set(0x9a8fb0);
    const mesh = new THREE.Mesh(geo, mat);
    mesh.castShadow = !m.transparent;
    g.add(mesh);
  }
  return g;
}
function standIn() {
  const g = new THREE.Group();
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.12, 0.06), new THREE.MeshStandardMaterial({ color: 0xff4f9a, roughness: 0.5, transparent: true, opacity: 0.8 }));
  mesh.position.y = 0.06;
  g.add(mesh);
  return g;
}
function loadMesh(guid) {
  if (!meshCache.has(guid)) {
    meshCache.set(guid, fetchJson('/api/prop_mesh?guid=' + encodeURIComponent(guid))
      .then(obj => (obj && obj.meshes && obj.meshes.length ? { group: buildMesh(obj), standIn: false } : { group: standIn(), standIn: true }))
      .catch(err => ({ group: standIn(), standIn: true, error: err })));
  }
  return meshCache.get(guid);
}

// ---------------------------------------------------------------- the props of the open animation
const propsOf = app => (Array.isArray(app.store.project.props) ? app.store.project.props : (app.store.project.props = []));

class PropStage {
  constructor(app) {
    this.app = app;
    this.group = new THREE.Group();
    this.group.name = 'props';
    app.vp.scene.add(this.group);
    this.objs = new Map();            // prop id -> Object3D
    this.dragging = null;
    this.detach = null;
  }

  sync() {
    const list = propsOf(this.app), ids = new Set(list.map(p => p.id));
    for (const [id, o] of this.objs) if (!ids.has(id)) { this.group.remove(o); this.objs.delete(id); }
    for (const p of list) {
      if (this.objs.has(p.id)) continue;
      const holder = new THREE.Group();
      holder.name = 'prop:' + p.id;
      holder.userData.prop = p.id;
      this.objs.set(p.id, holder);
      this.group.add(holder);
      loadMesh(p.guid).then(r => {
        if (!r || this.objs.get(p.id) !== holder) return;
        holder.add(r.group.clone());
        if (r.standIn) holder.userData.standIn = true;
      });
    }
    this.update();
  }

  // every frame: held props follow their bone, standing ones stay where they were put
  update() {
    const app = this.app;
    this.group.visible = !app.preview;
    for (const p of propsOf(app)) {
      const o = this.objs.get(p.id);
      if (!o || this.dragging === p.id) continue;
      const w = this.worldOf(p);
      if (!w) { o.visible = false; continue; }
      o.visible = true;
      o.position.copy(w.pos); o.quaternion.copy(w.quat);
    }
  }

  boneMatrix(p) {
    const v = p.hold && this.app.simViews.get(p.hold.sim);
    const b = v && v.bone(p.hold.bone);
    if (!b) return null;
    b.updateWorldMatrix(true, false);
    return b.matrixWorld;
  }

  worldOf(p) {
    if (p.hold) {
      const M = this.boneMatrix(p);
      if (!M) return null;
      const off = p.hold.offset || {};
      const local = new THREE.Matrix4().compose(new THREE.Vector3().fromArray(off.pos || [0, 0, 0]),
        new THREE.Quaternion().fromArray(off.quat || [0, 0, 0, 1]).normalize(), new THREE.Vector3(1, 1, 1));
      const W = M.clone().multiply(local), pos = new THREE.Vector3(), quat = new THREE.Quaternion(), sc = new THREE.Vector3();
      W.decompose(pos, quat, sc);
      return { pos, quat };
    }
    const a = p.at || {};
    return { pos: new THREE.Vector3().fromArray(a.pos || [0, 0, 0]), quat: new THREE.Quaternion().fromArray(a.quat || [0, 0, 0, 1]).normalize() };
  }

  // the gizmo on a prop; a held prop keeps its new place in the hand
  move(p) {
    const app = this.app, o = this.objs.get(p.id);
    if (!o || !app.interact || typeof app.interact.attachGizmo !== 'function') return false;
    if (app.playing) app.setPlaying(false);
    if (this.detach) this.detach();
    this.detach = app.interact.attachGizmo(o, {
      modes: ['translate', 'rotate'], size: 0.6,
      onStart: () => { app.store.checkpoint($t('features.props.move_prop')); this.dragging = p.id; },
      onChange: () => this.keep(p, o),
      onEnd: () => { this.keep(p, o); this.dragging = null; app.store.setDirty(true); },
    });
    toast($t('features.props.drag_to_move', { name: p.name }) + (p.hold ? $t('features.props.it_stays_in_hand_like') : ''));
    return true;
  }

  keep(p, o) {
    o.updateMatrixWorld(true);
    if (p.hold) {
      const M = this.boneMatrix(p);
      if (!M) return;
      const local = M.clone().invert().multiply(o.matrixWorld), pos = new THREE.Vector3(), quat = new THREE.Quaternion(), sc = new THREE.Vector3();
      local.decompose(pos, quat, sc);
      p.hold.offset = { pos: pos.toArray().map(x => Math.round(x * 1e5) / 1e5), quat: quat.toArray().map(x => Math.round(x * 1e6) / 1e6) };
    } else {
      p.at = { pos: o.position.toArray().map(x => Math.round(x * 1e5) / 1e5), quat: o.quaternion.toArray().map(x => Math.round(x * 1e6) / 1e6) };
    }
  }
}

// ---------------------------------------------------------------- changing props
function addProp(app, item) {
  const p = app.store.project;
  app.store.checkpoint($t('features.props.add_prop'));
  const sim = app.store.sim() || p.sims[0];
  const v = sim && app.simViews.get(sim.id);
  const prop = { id: uid('p'), guid: String(item.guid), name: item.name || 'A prop', source: item.source || 'game' };
  if (sim && v) prop.hold = { sim: sim.id, bone: handBone(v, 'R'), offset: { pos: [0, 0, 0], quat: [0, 0, 0, 1] } };
  else prop.at = { pos: [0, 0.8, 0.3], quat: [0, 0, 0, 1] };
  propsOf(app).push(prop);
  app.store.setDirty(true);
  app._props.sync();
  app.refreshPanels && app.refreshPanels();
  toast(prop.hold ? $t('features.props.is_in_s_right_hand', { propName: prop.name, simLabel: sim.label }) : $t('features.props.stands_in_scene', { propName: prop.name }), 'ok');
  return prop;
}

function setHolder(app, prop, value) {
  app.store.checkpoint($t('features.props.prop_holder'));
  const w = app._props.worldOf(prop);
  if (value === 'still') {
    delete prop.hold;
    prop.at = w ? { pos: w.pos.toArray(), quat: w.quat.toArray() } : { pos: [0, 0.8, 0.3], quat: [0, 0, 0, 1] };
  } else {
    const [simId, side] = value.split('|');
    const v = app.simViews.get(simId);
    prop.hold = { sim: simId, bone: handBone(v, side), offset: { pos: [0, 0, 0], quat: [0, 0, 0, 1] } };
    delete prop.at;
  }
  app.store.setDirty(true);
  app._props.update();
}

function removeProp(app, prop) {
  app.store.checkpoint($t('features.props.remove_prop'));
  const list = propsOf(app);
  list.splice(list.indexOf(prop), 1);
  if (app._props.detach) { app._props.detach(); app._props.detach = null; }
  app.store.setDirty(true);
  app._props.sync();
  app.refreshPanels && app.refreshPanels();
}

// ---------------------------------------------------------------- the "Add a prop" window
export function openAddProp(app) {
  if (!app.store.project.sims.length) { toast($t('features.props.open_or_make_animation_first')); return null; }
  const search = h('input', { placeholder: $t('features.props.search_props_glass_phone_book'), spellcheck: 'false', 'aria-label': $t('features.props.search_props') });
  const list = h('div', { class: 'lib-list pr-list' }, h('div', { class: 'hint' }, $t('features.props.reading_props')));
  let items = [];
  const dlg = modal({
    title: $t('features.props.add_prop_2'), wide: true,
    text: $t('features.props.objects_wickedwhims_animations_on_th'),
    body: h('div', { class: 'pr' }, h('div', { class: 'search' }, icon('search'), search), list),
    buttons: [{ label: $t('features.props.close'), kind: 'ghost' }],
  });
  dlg.dialog.classList.add('pr-modal');
  const draw = () => {
    const q = search.value.trim().toLowerCase();
    list.innerHTML = '';
    const shown = items.filter(x => !q || (x.name || '').toLowerCase().includes(q) || (x.objName || '').toLowerCase().includes(q)).slice(0, 200);
    if (!shown.length) {
      list.append(h('div', { class: 'empty-state compact' }, h('b', {}, items.length ? $t('features.props.no_prop_has_that_name') : $t('features.props.no_props_found')),
        h('p', {}, items.length ? $t('features.props.try_another_word') : $t('features.props.props_show_up_here_when'))));
      return;
    }
    for (const x of shown) {
      list.append(h('button', { class: 'lib-item pr-item', type: 'button', 'data-guid': x.guid, onclick: () => { dlg.close(); addProp(app, x); } },
        h('b', {}, x.name), h('div', { class: 'sub' }, h('span', { class: 'chip' }, x.source === 'mods' ? $t('features.props.from_mods') : $t('features.props.from_game')),
          h('span', {}, $t('features.props.used_by_animations', { uses: x.uses })))));
    }
  };
  search.addEventListener('input', draw);
  fetchJson('/api/props').then(r => { items = Array.isArray(r) ? r : []; draw(); })
    .catch(e => { list.innerHTML = ''; list.append(h('div', { class: 'hint warn' }, plainError(e, $t('features.props.props')))); });
  return dlg;
}

// the Scene step's "Props" section
function propsSection(app, root) {
  const p = app.store.project;
  if (!p.sims.length) return;
  const rows = propsOf(app).map(prop => {
    const holder = h('select', { 'aria-label': $t('features.props.who_holds_it') },
      h('option', { value: 'still', selected: !prop.hold }, $t('features.props.stands_still_in_scene')),
      ...p.sims.flatMap(s => HANDS.map(([side, word]) => h('option', { value: `${s.id}|${side}`,
        selected: !!(prop.hold && prop.hold.sim === s.id && new RegExp(`_${side}_`).test(prop.hold.bone)) }, $t('features.props.in_s', { sLabel: s.label, word })))));
    holder.onchange = () => { setHolder(app, prop, holder.value); holder.blur(); };
    const o = app._props && app._props.objs.get(prop.id);
    return h('div', { class: 'pr-row', 'data-prop': prop.id },
      h('div', { class: 'pr-t' }, h('b', {}, prop.name), o && o.userData.standIn ? h('small', {}, $t('features.props.stand_in_box_its_mesh')) : null, holder),
      h('button', { class: 'icon-btn sm', type: 'button', title: $t('features.props.move_it_gizmo'), onclick: () => app._props.move(prop) }, icon('move')),
      h('button', { class: 'icon-btn sm', type: 'button', title: $t('features.props.remove_it'), onclick: () => removeProp(app, prop) }, icon('trash')));
  });
  root.append(section([$t('features.props.props_2'), rows.length ? h('span', { class: 'count' }, String(rows.length)) : null],
    ...rows,
    h('button', { class: 'btn small block', type: 'button', 'data-props': 'add', onclick: () => openAddProp(app) }, icon('prop'), $t('features.props.add_prop_2')),
    rows.length ? h('div', { class: 'hint' }, $t('features.props.props_go_to_game_with')) : null));
}

// ---------------------------------------------------------------- plug in
export function install(app) {
  if (!app || app.__props) return;
  app.__props = true;
  for (const [id, svg] of Object.entries(ICONS)) addIcon(id, svg);
  const hooks = app.hooks || {};
  const add = (name, fn) => { const list = name.split('.').reduce((o, k) => o && o[k], hooks); if (Array.isArray(list)) list.push(fn); };
  app._props = new PropStage(app);

  add('sections.scene', (a, root) => propsSection(a, root));
  add('commands', a => [
    { group: $t('features.props.scene'), id: 'prop-add', label: $t('features.props.add_prop_2'), icon: 'prop', sub: $t('features.props.glass_phone_held_in_hand'),
      words: 'prop props object item hold holding glass phone book drink toy accessory', run: () => openAddProp(a), when: () => a.store.project.sims.length > 0 },
  ]);
  add('afterApply', () => app._props.update());
  add('projectLoaded', () => { if (app._props.detach) { app._props.detach(); app._props.detach = null; } app._props.sync(); });
  add('viewsSynced', () => app._props.sync());
  if (typeof app.on === 'function') app.on('undo', () => app._props.sync());
  // Send to game: each prop's movement, worked out from the baked sims (the way the game plays them)
  add('bake', (payload, p) => {
    const list = Array.isArray(p.props) ? p.props : [];
    if (!list.length || !app.assets.rig) return;
    payload.props = list.map(pr => ({ guid: String(pr.guid), name: pr.name, source: pr.source,
      track: propTrack(pr, { rig: app.assets.rig, actors: payload.actors, sims: p.sims, frames: payload.frames }) }))
      .filter(x => x.track);
  });
  add('exportChecks', p => {
    const out = [];
    for (const pr of Array.isArray(p.props) ? p.props : []) {
      if (pr.hold && !p.sims.some(s => s.id === pr.hold.sim)) out.push({ level: 'warn', text: $t('features.props.was_held_by_sim_that', { prName: pr.name }) });
      else if (pr.source === 'mods') out.push({ level: 'warn', text: $t('features.props.comes_from_your_mods_folder', { prName: pr.name }) });
    }
    return out;
  });
  window.wickedProps = { add: () => openAddProp(app), addItem: item => addProp(app, item), stage: app._props };
}

export default install;
