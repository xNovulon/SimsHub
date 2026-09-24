// Any furniture, any body, any pairing (R3-3): the windows for web/js/refit.js.
//
//   "Move to another place": one of WickedWhims' ~75 places or a CC object from the Mods folder (/api/refit_places).
//     The animation is copied onto it as a NEW animation (the original is saved first and never changed).
//   "Make versions": shorter or taller, on a Tray sim's body, two women, two men, a woman and a man, or the roles
//     swapped - each saved as its own animation next to the original.
// Also: a saved animation on one of those places shows its real object again when it is opened, a woman who gives
// wears a strap-on in the preview, and a CC place goes to the game as WickedWhims' custom location (the object id).
// Entry points: the Scene step ("Another place or body"), Ctrl+K "Move to another place" / "Make versions".
import { h, icon, modal, toast, section, addIcon } from '../ui.js';
import { api } from '../api.js';
import * as R from '../refit.js';
import { plainError } from '../gamehelp.js';
import { $t } from '../i18n.js';

const ICONS = {
  'rf-move': '<path d="M3.5 17.5h11v-5h-11zM5 12.5V9.8a1.8 1.8 0 0 1 1.8-1.8h4.4a1.8 1.8 0 0 1 1.8 1.8v2.7M3.5 17.5V20M14.5 17.5V20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/><path d="M15.5 6.5h5m0 0-2-2m2 2-2 2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  'rf-versions': '<circle cx="7" cy="7.5" r="2.4" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M3 20v-3.5A3.5 3.5 0 0 1 6.5 13h1A3.5 3.5 0 0 1 11 16.5V20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="16.5" cy="5.8" r="2.7" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M12.5 20v-4.8a4 4 0 0 1 4-4 4 4 0 0 1 4 4V20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
};
const WHERE = { on: $t('features.refit.on_it'), front: $t('features.refit.in_front_of_it'), lap: $t('features.refit.sitting_on_it'), floor: $t('features.refit.on_floor_by_it') };
const KIND = { bed: $t('features.refit.to_lie_on'), seat: $t('features.refit.to_sit_on'), surface: $t('features.refit.table_top'), water: $t('features.refit.in_water'), floor: $t('features.refit.on_floor'), wall: $t('features.refit.against_it') };
const needSims = app => {
  if (app.store.project.sims.length) return true;
  toast($t('features.refit.open_or_make_animation_first'));
  return false;
};
const pairingOf = p => {
  const f = p.sims.map(s => s.frame).sort().join(',');
  return f === 'yf,yf' ? 'ff' : f === 'ym,ym' ? 'mm' : f === 'yf,ym' ? 'fm' : null;
};

// ---------------------------------------------------------------- move to another place
export async function openMovePlace(app) {
  if (!needSims(app)) return null;
  const p = app.store.project;
  const here = p.furniture || 'floor';
  const search = h('input', { placeholder: $t('features.refit.search_places_bathtub_desk_hot'), spellcheck: 'false', 'aria-label': $t('features.refit.search_places') });
  const groups = h('div', { class: 'rf-groups' }, h('div', { class: 'hint' }, $t('features.refit.reading_places_from_game')));
  const info = h('div', { class: 'rf-info hint', role: 'status', 'aria-live': 'polite' }, $t('features.refit.pick_where_it_should_happen'));
  const ccNote = h('div', { class: 'hint rf-cc' });
  let rows = [], pick = null;
  const dlg = modal({
    title: $t('features.refit.move_to_another_place'), wide: true,
    text: $t('features.refit.is_copied_onto_new_place', { pName: p.name }),
    body: h('div', { class: 'rf' }, h('div', { class: 'search' }, icon('search'), search), groups, ccNote, info),
    buttons: [
      { label: $t('features.refit.cancel'), kind: 'ghost' },
      { label: $t('features.refit.move_it'), kind: 'primary', onClick: () => go() },
    ],
  });
  dlg.dialog.classList.add('rf-modal');
  const btn = dlg.footer.querySelector('.btn.primary');
  btn.disabled = true;

  const draw = () => {
    const q = search.value.trim().toLowerCase();
    groups.innerHTML = '';
    const byGroup = new Map();
    for (const r of rows) {
      if (q && !r.label.toLowerCase().includes(q) && !(r.group || '').toLowerCase().includes(q) && !(r.location || '').toLowerCase().includes(q.replace(/ /g, '_'))) continue;
      if (!byGroup.has(r.group)) byGroup.set(r.group, []);
      byGroup.get(r.group).push(r);
    }
    if (!byGroup.size) { groups.append(h('div', { class: 'hint' }, rows.length ? $t('features.refit.no_place_has_that_name') : $t('features.refit.no_places'))); return; }
    for (const [g, list] of byGroup) {
      groups.append(h('div', { class: 'tag-group' }, h('span', {}, g), h('div', { class: 'chips' }, list.map(r =>
        h('button', { class: 'chipbtn place' + (pick === r ? ' on' : '') + (r.id === here ? ' here' : ''), type: 'button', 'data-place': r.id,
          title: r.id === here ? $t('features.refit.it_is_here_now') : (KIND[r.kind] || ''), onclick: () => choose(r) }, r.label, r.id === here ? $t('features.refit.now') : '')))));
    }
  };
  const choose = r => {
    pick = r;
    btn.disabled = r.id === here;
    const bits = [KIND[r.kind] || '', r.surface_height ? $t('features.refit.top_cm_high', { surface_height: Math.round(r.surface_height * 100) }) : '',
      r.seats ? $t('features.refit.n_seats', { n: r.seats }) : '', r.lying ? $t('features.refit.room_to_lie_down') : '', r.cc ? $t('features.refit.custom_content', { v: r.package ? ` (${String(r.package).split(/[\\/]/).pop()})` : '' }) : ''].filter(Boolean);
    info.textContent = r.id === here ? $t('features.refit.it_is_on_already', { rLabel: r.label.toLowerCase() }) : `${r.label}: ${bits.join(' · ')}.`
      + (r.cc ? $t('features.refit.players_need_this_object_in') : '');
    draw();
  };
  search.addEventListener('input', draw);

  try {
    const res = await R.loadPlaces();
    rows = [{ id: 'floor', label: $t('features.refit.floor'), kind: 'floor', location: 'FLOOR', group: $t('features.refit.floor_and_walls') }, ...(res.places || []), ...(res.cc || [])];
    const order = [...(res.groups || [])];
    rows.sort((a, b) => ((order.indexOf(a.group) + 1 || 99) - (order.indexOf(b.group) + 1 || 99)) || a.label.localeCompare(b.label));
    draw();
    if (res.cc_status && res.cc_status !== 'ok' && res.cc_note) ccNote.textContent = res.cc_note;
  } catch (e) {
    groups.innerHTML = '';
    groups.append(h('div', { class: 'hint warn rf-err' }, plainError(e, $t('features.refit.places'))));
  }

  async function go() {
    if (!pick || pick.id === here) return false;
    btn.textContent = $t('features.refit.moving');
    let r;
    try { r = await R.moveToPlace(app, pick); }
    catch (e) { btn.textContent = $t('features.refit.move_it'); toast(e.message || String(e), 'err'); return false; }
    report(app, r);
    return undefined;
  }
  return dlg;
}

function report(app, r) {
  const lines = [];
  lines.push(`${r.to}: ${WHERE[r.where] || 'there'}.`);
  if (r.pins) lines.push($t('features.refit.pins_put_back', { n: r.pins }));
  if (r.lifted > 0.002) lines.push($t('features.refit.lifted_cm', { cm: Math.round(r.lifted * 100) }));
  const deep = (r.deep || []).length;
  lines.push(deep ? $t('features.refit.spots_where_body_still_goes', { deep })
    : $t('features.refit.no_body_goes_into_furniture'));
  if (r.credit) lines.push($t('features.refit.made_from_credit', { author: r.credit.author }));
  modal({
    title: r.saved ? $t('features.refit.saved_as', { rName: r.name }) : $t('features.refit.is_ready', { rName: r.name }),
    text: $t('features.refit.new_animation_copied_from_original', { fromName: r.from.name, fromLabel: r.from.label.toLowerCase() }),
    body: h('ul', { class: 'rf-report' }, lines.map(t => h('li', {}, t))),
    buttons: [
      deep && typeof app.checkClipping === 'function' ? { label: $t('features.refit.check_clipping'), kind: 'ghost', onClick: () => app.checkClipping() } : null,
      { label: 'OK', kind: 'primary' },
    ].filter(Boolean),
  });
}

// ---------------------------------------------------------------- versions
export function openVersions(app) {
  if (!needSims(app)) return null;
  const p = app.store.project;
  const picked = new Map();                  // key -> spec
  const toggle = (key, spec, el) => {
    if (picked.has(key)) picked.delete(key); else picked.set(key, spec);
    el.classList.toggle('on', picked.has(key));
    el.setAttribute('aria-pressed', String(picked.has(key)));
    setCount();
  };
  const chip = (key, spec, text, title) => {
    const el = h('button', { class: 'chipbtn', type: 'button', 'aria-pressed': 'false', 'data-version': key, title: title || null }, text);
    el.onclick = () => toggle(key, spec, el);
    return el;
  };
  const heights = h('div', { class: 'rf-rows' }, p.sims.map(s => h('div', { class: 'rf-row' }, h('b', {}, s.label),
    h('div', { class: 'chips' }, ...Object.entries(R.HEIGHTS).map(([size, x]) =>
      chip(`h:${s.id}:${size}`, { kind: 'height', simId: s.id, size }, $t('features.refit.er', { word: x.word, scale: Math.round(Math.abs(x.scale - 1) * 100) }),
        $t('features.refit.feet_stay_planted_hands_stay', { sLabel: s.label, xLabel: x.label })))))));
  const now = pairingOf(p);
  const pairs = h('div', { class: 'chips' },
    ...(p.sims.length === 2 ? Object.entries(R.PAIRINGS).filter(([k]) => k !== now).map(([k, x]) => chip('p:' + k, { kind: 'pair', pair: k }, x.label,
      k === 'ff' ? $t('features.refit.one_who_gives_wears_strap') : k === 'mm' ? $t('features.refit.vaginal_becomes_anal') : null)) : []),
    p.sims.length === 2 ? chip('swap', { kind: 'swap' }, $t('features.refit.roles_swapped'), $t('features.refit.two_sims_trade_bodies_one')) : null);
  const tray = h('div', { class: 'rf-tray' }, h('div', { class: 'hint' }, $t('features.refit.looking_for_your_tray_sims')));
  const status = h('div', { class: 'hint rf-status', role: 'status', 'aria-live': 'polite' });
  const dlg = modal({
    title: $t('features.refit.make_versions'), wide: true,
    text: $t('features.refit.other_bodies_and_pairings_for', { pName: p.name }),
    body: h('div', { class: 'rf' },
      section($t('features.refit.taller_or_shorter'), heights),
      p.sims.length === 2 ? section($t('features.refit.who_is_in_it'), pairs) : null,
      section($t('features.refit.on_tray_sim_s_body'), tray),
      status),
    buttons: [
      { label: $t('features.refit.cancel'), kind: 'ghost' },
      { label: $t('features.refit.make_them'), kind: 'primary', onClick: () => go() },
    ],
  });
  dlg.dialog.classList.add('rf-modal');
  const btn = dlg.footer.querySelector('.btn.primary');
  function setCount() {
    btn.disabled = !picked.size;
    btn.textContent = picked.size ? $t('features.refit.make_versions_2', { size: picked.size }) : $t('features.refit.make_them');
  }
  setCount();

  api.tray().then(households => {
    tray.innerHTML = '';
    const adults = (households || []).flatMap(hh => (hh.sims || []).map(s => ({ ...s, hh })));
    if (!adults.length) { tray.append(h('div', { class: 'hint' }, $t('features.refit.no_adult_sims_in_your'))); return; }
    const who = h('select', { 'aria-label': $t('features.refit.which_sim_of_animation') }, p.sims.map(s => h('option', { value: s.id }, s.label)));
    const body = h('select', { 'aria-label': $t('features.refit.tray_sim') }, adults.map((s, i) => h('option', { value: i }, `${s.name || $t('features.refit.sim')} (${s.hh.name || 'household'})`)));
    const addBtn = h('button', { class: 'btn small', type: 'button' }, icon('plus'), $t('features.refit.add'));
    const chosen = h('div', { class: 'chips' });
    addBtn.onclick = () => {
      const s = adults[+body.value], sim = p.sims.find(x => x.id === who.value);
      if (!s || !sim) return;
      const frame = s.frame === 'ym' || s.gender === 'male' || s.gender === 'MALE' ? 'ym' : 'yf';
      const key = `t:${sim.id}:${s.hh.id}:${s.index}`;
      if (picked.has(key)) return;
      const el = chip(key, { kind: 'tray', simId: sim.id, tray: { id: s.hh.id, index: s.index, name: s.name || $t('features.refit.tray_sim'), frame } }, `${sim.label} as ${s.name || $t('features.refit.tray_sim_2')}`);
      chosen.append(el);
      el.click();
    };
    tray.append(h('div', { class: 'filters' }, who, body, addBtn), chosen);
  }).catch(e => { tray.innerHTML = ''; tray.append(h('div', { class: 'hint' }, plainError(e, $t('features.refit.your_tray')))); });

  async function go() {
    if (!picked.size) return false;
    const specs = [...picked.values()];
    btn.disabled = true;
    let out;
    try {
      out = await R.makeVersions(app, specs, { onProgress: (i, n, text) => { status.textContent = i < n ? $t('features.refit.making_of', { i: i + 1, n, text }) : $t('features.refit.saving'); } });
    } catch (e) { status.textContent = ''; setCount(); toast($t('features.refit.versions_could_not_be_made', { message: e.message || e }), 'err'); return false; }
    results(app, out);
    return undefined;
  }
  return dlg;
}

function results(app, out) {
  const rows = out.map(x => {
    const rp = x.report || {};
    const bits = [rp.text, rp.limbs ? $t('features.refit.contacts_put_back', { limbs: rp.limbs }) : '', rp.deep ? $t('features.refit.spots_to_check_for_clipping', { deep: rp.deep }) : $t('features.refit.no_clipping_found'),
      rp.error ? $t('features.refit.not_saved', { error: rp.error }) : ''].filter(Boolean);
    return h('li', { class: 'rf-result' }, h('div', {}, h('b', {}, x.project.name), h('small', {}, bits.join(' · '))),
      x.saved ? h('button', { class: 'btn small', type: 'button', onclick: e => { e.currentTarget.closest('.backdrop')?.querySelector('.modal-x')?.click(); app.loadProject(x.saved); } }, $t('features.refit.open')) : null);
  });
  const saved = out.filter(x => x.saved).length;
  modal({
    title: saved ? $t('features.refit.versions_saved', { saved }) : $t('features.refit.versions_made'),
    text: $t('features.refit.each_is_its_own_animation'),
    body: h('ul', { class: 'rf-results' }, rows),
    buttons: [{ label: $t('features.refit.done'), kind: 'primary' }],
  });
}

// ---------------------------------------------------------------- plug in
export function install(app) {
  if (!app || app.__refit) return;
  app.__refit = true;
  for (const [id, svg] of Object.entries(ICONS)) addIcon(id, svg);
  const hooks = app.hooks || {};
  const add = (name, fn) => { const list = name.split('.').reduce((o, k) => o && o[k], hooks); if (Array.isArray(list)) list.push(fn); };
  const has = () => app.store.project.sims.length > 0;

  add('sections.scene', (a, root) => {
    if (!a.store.project.sims.length) return;
    root.append(section($t('features.refit.another_place_or_body'),
      h('div', { class: 'rf-entry' },
        h('button', { class: 'btn small block', type: 'button', 'data-refit': 'move', title: $t('features.refit.any_of_wickedwhims_places_or'), onclick: () => openMovePlace(a) }, icon('rf-move'), $t('features.refit.move_to_another_place')),
        h('button', { class: 'btn small block', type: 'button', 'data-refit': 'versions', title: $t('features.refit.taller_shorter_two_women_two'), onclick: () => openVersions(a) }, icon('rf-versions'), $t('features.refit.make_versions'))),
      h('div', { class: 'hint' }, $t('features.refit.bathtub_desk_hot_tub_cc'))));
  });
  add('commands', a => [
    { group: $t('features.refit.scene'), id: 'refit-move', label: $t('features.refit.move_to_another_place'), icon: 'rf-move', sub: $t('features.refit.any_wickedwhims_place_or_your'),
      words: 'refit furniture location place bathtub shower desk counter hot tub bed sofa cc custom object move copy', run: () => openMovePlace(a), when: has },
    { group: $t('features.refit.scene'), id: 'refit-versions', label: $t('features.refit.make_versions'), icon: 'rf-versions', sub: $t('features.refit.taller_shorter_two_women_two_2'),
      words: 'refit versions body height tall short lesbian gay ff mm swap roles strap-on strapon tray variant', run: () => openVersions(a), when: has },
  ]);
  add('helpRows', () => [{ group: $t('features.refit.making_animations'), keys: ['Ctrl', 'K'], text: $t('features.refit.type_move_to_another_place') }]);

  // an animation saved on an extra place: its real object on the stage again
  add('projectLoaded', p => { R.restorePlace(app, p).catch(err => console.error('Place:', err)); });
  // a woman who gives wears a strap-on in the preview (the openings open around it)
  add('viewsSynced', () => {
    for (const s of app.store.project.sims) {
      const v = app.simViews.get(s.id);
      if (!v) continue;
      if (R.wantsStrap(s, v)) R.attachStrap(v); else R.detachStrap(v);
    }
  });
  add('bake', (payload, p) => {
    // the strap-on the preview shows is not the sim's own penis: WickedWhims still gives her one in the game
    (p.sims || []).forEach((s, i) => { const a = payload.actors && payload.actors[i]; if (a && s.strapon && s.frame === 'yf') a.strapon = true; });
    // a CC place: WickedWhims finds it by the object's id
    if (Array.isArray(p.customLocations) && p.customLocations.length) payload.customLocations = [...p.customLocations];
  });
  add('exportChecks', p => {
    if (!Array.isArray(p.customLocations) || !p.customLocations.length) return [];
    const def = (app.furniture || []).find(f => f.id === p.furniture);
    return [{ level: 'warn', text: def ? $t('features.refit.only_on_cc_named', { name: def.label }) : $t('features.refit.only_on_cc') }];
  });

  window.wickedRefit = { move: () => openMovePlace(app), versions: () => openVersions(app) };
}

export default install;
