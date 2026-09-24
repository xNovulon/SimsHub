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

const ICONS = {
  'rf-move': '<path d="M3.5 17.5h11v-5h-11zM5 12.5V9.8a1.8 1.8 0 0 1 1.8-1.8h4.4a1.8 1.8 0 0 1 1.8 1.8v2.7M3.5 17.5V20M14.5 17.5V20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/><path d="M15.5 6.5h5m0 0-2-2m2 2-2 2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  'rf-versions': '<circle cx="7" cy="7.5" r="2.4" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M3 20v-3.5A3.5 3.5 0 0 1 6.5 13h1A3.5 3.5 0 0 1 11 16.5V20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="16.5" cy="5.8" r="2.7" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M12.5 20v-4.8a4 4 0 0 1 4-4 4 4 0 0 1 4 4V20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
};
const WHERE = { on: 'on it', front: 'in front of it', lap: 'sitting on it', floor: 'on the floor by it' };
const KIND = { bed: 'to lie on', seat: 'to sit on', surface: 'a table top', water: 'in the water', floor: 'on the floor', wall: 'against it' };
const needSims = app => {
  if (app.store.project.sims.length) return true;
  toast('Open or make an animation first.');
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
  const search = h('input', { placeholder: 'Search places: bathtub, desk, hot tub...', spellcheck: 'false', 'aria-label': 'Search places' });
  const groups = h('div', { class: 'rf-groups' }, h('div', { class: 'hint' }, 'Reading the places from the game...'));
  const info = h('div', { class: 'rf-info hint', role: 'status', 'aria-live': 'polite' }, 'Pick where it should happen.');
  const ccNote = h('div', { class: 'hint rf-cc' });
  let rows = [], pick = null;
  const dlg = modal({
    title: 'Move to another place', wide: true,
    text: `"${p.name}" is copied onto the new place as a new animation - resting on its real top, lying along it or sitting on its seats. The original stays as it is.`,
    body: h('div', { class: 'rf' }, h('div', { class: 'search' }, icon('search'), search), groups, ccNote, info),
    buttons: [
      { label: 'Cancel', kind: 'ghost' },
      { label: 'Move it', kind: 'primary', onClick: () => go() },
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
    if (!byGroup.size) { groups.append(h('div', { class: 'hint' }, rows.length ? 'No place has that name.' : 'No places.')); return; }
    for (const [g, list] of byGroup) {
      groups.append(h('div', { class: 'tag-group' }, h('span', {}, g), h('div', { class: 'chips' }, list.map(r =>
        h('button', { class: 'chipbtn place' + (pick === r ? ' on' : '') + (r.id === here ? ' here' : ''), type: 'button', 'data-place': r.id,
          title: r.id === here ? 'It is here now' : (KIND[r.kind] || ''), onclick: () => choose(r) }, r.label, r.id === here ? ' (now)' : '')))));
    }
  };
  const choose = r => {
    pick = r;
    btn.disabled = r.id === here;
    const bits = [KIND[r.kind] || '', r.surface_height ? `top ${Math.round(r.surface_height * 100)} cm high` : '',
      r.seats ? `${r.seats} seat${r.seats === 1 ? '' : 's'}` : '', r.lying ? 'room to lie down' : '', r.cc ? 'custom content' + (r.package ? ` (${String(r.package).split(/[\\/]/).pop()})` : '') : ''].filter(Boolean);
    info.textContent = r.id === here ? `It is on the ${r.label.toLowerCase()} already.` : `${r.label}: ${bits.join(' · ')}.`
      + (r.cc ? ' Players need this object in their game too - the animation only shows up on it.' : '');
    draw();
  };
  search.addEventListener('input', draw);

  try {
    const res = await R.loadPlaces();
    rows = [{ id: 'floor', label: 'Floor', kind: 'floor', location: 'FLOOR', group: 'Floor and walls' }, ...(res.places || []), ...(res.cc || [])];
    const order = [...(res.groups || [])];
    rows.sort((a, b) => ((order.indexOf(a.group) + 1 || 99) - (order.indexOf(b.group) + 1 || 99)) || a.label.localeCompare(b.label));
    draw();
    if (res.cc_status && res.cc_status !== 'ok' && res.cc_note) ccNote.textContent = res.cc_note;
  } catch (e) {
    groups.innerHTML = '';
    groups.append(h('div', { class: 'hint warn rf-err' }, plainError(e, 'the places')));
  }

  async function go() {
    if (!pick || pick.id === here) return false;
    btn.textContent = 'Moving...';
    let r;
    try { r = await R.moveToPlace(app, pick); }
    catch (e) { btn.textContent = 'Move it'; toast(e.message || String(e), 'err'); return false; }
    report(app, r);
    return undefined;
  }
  return dlg;
}

function report(app, r) {
  const lines = [];
  lines.push(`${r.to}: ${WHERE[r.where] || 'there'}.`);
  if (r.pins) lines.push(`${r.pins} resting hand${r.pins === 1 ? '' : 's'} or foot put back on its top.`);
  if (r.lifted > 0.002) lines.push(`Lifted ${Math.round(r.lifted * 100)} cm so nothing sinks into it.`);
  const deep = (r.deep || []).length;
  lines.push(deep ? `${deep} spot${deep === 1 ? '' : 's'} where a body still goes into the furniture or the partner - Check clipping shows where.`
    : 'No body goes into the furniture or the partner.');
  if (r.credit) lines.push(`Made from ${r.credit.author}'s animation: for your own game - share it only with their okay.`);
  modal({
    title: r.saved ? `Saved as "${r.name}"` : `"${r.name}" is ready`,
    text: `A new animation, copied from "${r.from.name}" (${r.from.label.toLowerCase()}). The original is unchanged.`,
    body: h('ul', { class: 'rf-report' }, lines.map(t => h('li', {}, t))),
    buttons: [
      deep && typeof app.checkClipping === 'function' ? { label: 'Check clipping', kind: 'ghost', onClick: () => app.checkClipping() } : null,
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
      chip(`h:${s.id}:${size}`, { kind: 'height', simId: s.id, size }, `${x.word}er (${Math.round(Math.abs(x.scale - 1) * 100)}%)`,
        `${s.label} ${x.label} - feet stay planted, hands stay on the partner`))))));
  const now = pairingOf(p);
  const pairs = h('div', { class: 'chips' },
    ...(p.sims.length === 2 ? Object.entries(R.PAIRINGS).filter(([k]) => k !== now).map(([k, x]) => chip('p:' + k, { kind: 'pair', pair: k }, x.label,
      k === 'ff' ? 'The one who gives wears a strap-on' : k === 'mm' ? 'Vaginal becomes anal' : null)) : []),
    p.sims.length === 2 ? chip('swap', { kind: 'swap' }, 'Roles swapped', 'The two sims trade bodies - the one who gave now receives') : null);
  const tray = h('div', { class: 'rf-tray' }, h('div', { class: 'hint' }, 'Looking for your Tray sims...'));
  const status = h('div', { class: 'hint rf-status', role: 'status', 'aria-live': 'polite' });
  const dlg = modal({
    title: 'Make versions', wide: true,
    text: `Other bodies and pairings for "${p.name}". Each is its own animation, saved next to this one: feet stay planted, hands stay on the partner, heads meet for a kiss and the penis (or strap-on) stays in.`,
    body: h('div', { class: 'rf' },
      section('Taller or shorter', heights),
      p.sims.length === 2 ? section('Who is in it', pairs) : null,
      section("On a Tray sim's body", tray),
      status),
    buttons: [
      { label: 'Cancel', kind: 'ghost' },
      { label: 'Make them', kind: 'primary', onClick: () => go() },
    ],
  });
  dlg.dialog.classList.add('rf-modal');
  const btn = dlg.footer.querySelector('.btn.primary');
  function setCount() {
    btn.disabled = !picked.size;
    btn.textContent = picked.size ? `Make ${picked.size} version${picked.size === 1 ? '' : 's'}` : 'Make them';
  }
  setCount();

  api.tray().then(households => {
    tray.innerHTML = '';
    const adults = (households || []).flatMap(hh => (hh.sims || []).map(s => ({ ...s, hh })));
    if (!adults.length) { tray.append(h('div', { class: 'hint' }, 'No adult sims in your Tray yet.')); return; }
    const who = h('select', { 'aria-label': 'Which sim of the animation' }, p.sims.map(s => h('option', { value: s.id }, s.label)));
    const body = h('select', { 'aria-label': 'Tray sim' }, adults.map((s, i) => h('option', { value: i }, `${s.name || 'Sim'} (${s.hh.name || 'household'})`)));
    const addBtn = h('button', { class: 'btn small', type: 'button' }, icon('plus'), 'Add');
    const chosen = h('div', { class: 'chips' });
    addBtn.onclick = () => {
      const s = adults[+body.value], sim = p.sims.find(x => x.id === who.value);
      if (!s || !sim) return;
      const frame = s.frame === 'ym' || s.gender === 'male' || s.gender === 'MALE' ? 'ym' : 'yf';
      const key = `t:${sim.id}:${s.hh.id}:${s.index}`;
      if (picked.has(key)) return;
      const el = chip(key, { kind: 'tray', simId: sim.id, tray: { id: s.hh.id, index: s.index, name: s.name || 'Tray sim', frame } }, `${sim.label} as ${s.name || 'a Tray sim'}`);
      chosen.append(el);
      el.click();
    };
    tray.append(h('div', { class: 'filters' }, who, body, addBtn), chosen);
  }).catch(e => { tray.innerHTML = ''; tray.append(h('div', { class: 'hint' }, plainError(e, 'your Tray'))); });

  async function go() {
    if (!picked.size) return false;
    const specs = [...picked.values()];
    btn.disabled = true;
    let out;
    try {
      out = await R.makeVersions(app, specs, { onProgress: (i, n, text) => { status.textContent = i < n ? `Making ${i + 1} of ${n}: ${text}...` : 'Saving...'; } });
    } catch (e) { status.textContent = ''; setCount(); toast('The versions could not be made: ' + (e.message || e), 'err'); return false; }
    results(app, out);
    return undefined;
  }
  return dlg;
}

function results(app, out) {
  const rows = out.map(x => {
    const rp = x.report || {};
    const bits = [rp.text, rp.limbs ? `${rp.limbs} contact${rp.limbs === 1 ? '' : 's'} put back` : '', rp.deep ? `${rp.deep} spot${rp.deep === 1 ? '' : 's'} to check for clipping` : 'no clipping found',
      rp.error ? 'not saved: ' + rp.error : ''].filter(Boolean);
    return h('li', { class: 'rf-result' }, h('div', {}, h('b', {}, x.project.name), h('small', {}, bits.join(' · '))),
      x.saved ? h('button', { class: 'btn small', type: 'button', onclick: e => { e.currentTarget.closest('.backdrop')?.querySelector('.modal-x')?.click(); app.loadProject(x.saved); } }, 'Open') : null);
  });
  const saved = out.filter(x => x.saved).length;
  modal({
    title: saved ? `${saved} version${saved === 1 ? '' : 's'} saved` : 'Versions made',
    text: 'Each is its own animation (its own name in the game), next to the original. Open one to look it over, then Send to game.',
    body: h('ul', { class: 'rf-results' }, rows),
    buttons: [{ label: 'Done', kind: 'primary' }],
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
    root.append(section('Another place or body',
      h('div', { class: 'rf-entry' },
        h('button', { class: 'btn small block', type: 'button', 'data-refit': 'move', title: 'Any of WickedWhims\' places, or your CC furniture', onclick: () => openMovePlace(a) }, icon('rf-move'), 'Move to another place'),
        h('button', { class: 'btn small block', type: 'button', 'data-refit': 'versions', title: 'Taller, shorter, two women, two men, roles swapped', onclick: () => openVersions(a) }, icon('rf-versions'), 'Make versions')),
      h('div', { class: 'hint' }, 'Bathtub, desk, hot tub, CC beds... or a taller partner, two women, the roles swapped. Each is saved as a new animation.')));
  });
  add('commands', a => [
    { group: 'Scene', id: 'refit-move', label: 'Move to another place', icon: 'rf-move', sub: "any WickedWhims place or your CC furniture - a new animation",
      words: 'refit furniture location place bathtub shower desk counter hot tub bed sofa cc custom object move copy', run: () => openMovePlace(a), when: has },
    { group: 'Scene', id: 'refit-versions', label: 'Make versions', icon: 'rf-versions', sub: 'taller, shorter, two women, two men, roles swapped, a Tray body',
      words: 'refit versions body height tall short lesbian gay ff mm swap roles strap-on strapon tray variant', run: () => openVersions(a), when: has },
  ]);
  add('helpRows', () => [{ group: 'Making animations', keys: ['Ctrl', 'K'], text: 'Type "Move to another place" or "Make versions" - any furniture, any body, any pairing' }]);

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
    return [{ level: 'warn', text: `It only shows up on ${def ? 'the ' + def.label : 'your CC object'} - players need that custom content in their game too.` }];
  });

  window.wickedRefit = { move: () => openMovePlace(app), versions: () => openVersions(app) };
}

export default install;
