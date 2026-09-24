// The Game Doctor's Browse tab (R3-2): every WickedWhims animation installed on this PC, with a star for WickedWhims'
// Favorites and a switch for its "Turn off" list (backend/wwlists.py, route doctor_browse; the two lists change
// through doctor_fix {action: 'favorite' | 'turn_off', id, on}).
//
// WickedWhims knows an animation by an "identifier" the server works out the way WickedWhims does. When that is
// proven on this PC (it matches WickedWhims' own lists) a star or a switch changes WickedWhims' own files (only with
// the game closed, backed up first). When it is not proven, Favorites and Turn off are kept in this app only (the
// browser's storage) and the tab says so - WickedWhims' files are never touched then.
import { h, icon, toast } from './ui.js';
import { fetchJson, plainError } from './gamehelp.js';

const PAGE = 150;
const LOCAL = 'fsa.doctor.lists';
const ACTS = [['', 'Any kind'], ['TEASING', 'Teasing'], ['HANDJOB', 'Handjob'], ['FOOTJOB', 'Footjob'], ['ORALJOB', 'Oral'],
  ['VAGINAL', 'Vaginal'], ['ANAL', 'Anal'], ['CLIMAX', 'Climax']];
const nicePlace = p => (p === 'CUSTOM' ? 'Custom object' : p.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()));

// Favorites and Turn off kept in the app (when WickedWhims' own lists can't be written): {fav: [id], off: [id]}
export const localLists = {
  get() {
    try { const v = JSON.parse(localStorage.getItem(LOCAL) || 'null'); return { fav: new Set((v && v.fav) || []), off: new Set((v && v.off) || []) }; }
    catch { return { fav: new Set(), off: new Set() }; }
  },
  set(lists) { try { localStorage.setItem(LOCAL, JSON.stringify({ fav: [...lists.fav], off: [...lists.off] })); } catch { /* private mode */ } },
};

export function browsePanel(app, { onPreview = null } = {}) {
  const q = { q: '', where: 'mods', place: '', act: '', sims: '', only: '' };
  let items = [], total = 0, page = 0, mode = 'ww', timer = 0, loading = 0;
  const search = h('input', { placeholder: 'Search animations or creators', spellcheck: 'false', 'aria-label': 'Search' });
  const where = h('select', { 'aria-label': 'Which folder' }, [['mods', 'In Mods'], ['parked', 'Set aside (Mods_parked)'], ['all', 'Both']].map(([v, t]) => h('option', { value: v }, t)));
  const place = h('select', { 'aria-label': 'Place' }, h('option', { value: '' }, 'Anywhere'));
  const act = h('select', { 'aria-label': 'Kind' }, ACTS.map(([v, t]) => h('option', { value: v }, t)));
  const sims = h('select', { 'aria-label': 'Sims' }, [['', 'Any sims'], ['1', '1 sim'], ['2', '2 sims'], ['3', '3 sims'], ['4', '4 sims']].map(([v, t]) => h('option', { value: v }, t)));
  const only = h('div', { class: 'seg-inline db-only', role: 'tablist' });
  const onlyBtns = [['', 'All'], ['fav', 'Favorites'], ['off', 'Turned off']].map(([v, t]) => {
    const b = h('button', { type: 'button', class: v === q.only ? 'on' : '', 'data-only': v }, t);
    b.onclick = () => { q.only = v; onlyBtns.forEach(x => x.classList.toggle('on', x === b)); reload(); };
    return b;
  });
  only.append(...onlyBtns);
  const proof = h('div', { class: 'db-proof' });
  const count = h('div', { class: 'hint db-count', role: 'status', 'aria-live': 'polite' }, 'Reading your animations...');
  const list = h('div', { class: 'db-list' });
  const root = h('div', { class: 'db' },
    proof,
    h('div', { class: 'search' }, icon('search'), search),
    h('div', { class: 'filters' }, where, place, act, sims),
    h('div', { class: 'db-bar' }, only, count),
    list);

  let st = 0;
  search.addEventListener('input', () => { clearTimeout(st); st = setTimeout(() => { q.q = search.value; reload(); }, 220); });
  for (const [el, k] of [[where, 'where'], [place, 'place'], [act, 'act'], [sims, 'sims']]) el.addEventListener('change', () => { q[k] = el.value; reload(); });

  const params = (p, extra = {}) => new URLSearchParams(Object.entries({ ...q, page: p, ...extra }).filter(([, v]) => v !== '' && v !== null && v !== undefined));

  function drawProof(r) {
    const pr = r.proof || {};
    mode = r.writes === 'ww' ? 'ww' : 'app';
    proof.className = 'db-proof ' + (mode === 'ww' ? 'ok' : 'app');
    proof.innerHTML = '';
    proof.append(icon(mode === 'ww' ? 'doc-ok' : 'doc-info'), h('div', {},
      h('b', {}, mode === 'ww' ? "Stars and switches change WickedWhims' own lists" : 'Stars and switches are kept in this app'),
      h('small', {}, pr.text || '')));
  }

  function drawPlaces(r) {
    const keep = place.value;
    place.innerHTML = '';
    place.append(h('option', { value: '' }, 'Anywhere'),
      ...Object.entries(r.places || {}).sort((a, b) => b[1] - a[1]).map(([p, n]) => h('option', { value: p, selected: p === keep }, `${nicePlace(p)} (${n})`)));
  }

  // the app's own lists on top of the server's answer (only when WickedWhims' files can't be written)
  function withLocal(rows) {
    if (mode === 'ww') return rows;
    const l = localLists.get();
    return rows.map(x => ({ ...x, fav: l.fav.has(x.id), off: l.off.has(x.id) }));
  }

  async function reload() { page = 0; items = []; await load(); }

  async function load() {
    clearTimeout(timer);
    const my = ++loading;
    let r;
    // in the app's own lists, Favorites / Turned off are sorted out here (the server only knows WickedWhims' lists)
    const localOnly = mode === 'app' && q.only;
    try { r = await fetchJson('/api/doctor_browse?' + params(page, localOnly ? { only: '' } : {})); }
    catch (e) { if (my === loading) { count.textContent = plainError(e, 'your animations'); list.innerHTML = ''; } return; }
    if (my !== loading || !root.isConnected) return;
    if (!r.ready) {
      count.textContent = r.error ? plainError(r.error, 'your animations')
        : `Reading your animations${r.total ? ` (${r.done} of ${r.total} packages)` : ''}... the first time takes a moment.`;
      list.innerHTML = '';
      timer = setTimeout(load, 900);
      return;
    }
    drawProof(r);
    drawPlaces(r);
    let rows = withLocal(r.items || []);
    if (mode === 'app' && q.only) {
      // gather every page, then keep the app's favorites / turned-off ones (at most 20 pages)
      for (let p = page + 1; rows.length < 20 * PAGE && p * PAGE < r.total && p < 20; p++) {
        try { rows = rows.concat(withLocal((await fetchJson('/api/doctor_browse?' + params(p, { only: '' }))).items || [])); } catch { break; }
      }
      rows = rows.filter(x => (q.only === 'fav' ? x.fav : x.off));
      total = rows.length;
      items = rows;
    } else {
      items = page ? items.concat(rows) : rows;
      total = r.total;
    }
    const c = r.counts || {};
    count.textContent = `${total.toLocaleString()} animation${total === 1 ? '' : 's'}` + (q.where === 'mods' && c.parked ? ` · ${c.parked} more set aside` : '')
      + (r.not_shown ? ` · ${r.not_shown} not shown (not for adults)` : '');
    draw();
  }

  function draw() {
    list.innerHTML = '';
    if (!items.length) {
      list.append(h('div', { class: 'empty-state compact' }, h('b', {}, q.q || q.place || q.act || q.sims || q.only ? 'Nothing matches' : 'No WickedWhims animations here'),
        h('p', {}, q.q || q.place || q.act || q.sims || q.only ? 'Change the search or the filters.' : 'Animation packs in your Mods folder show up here - with a star for your favorites and a switch to turn one off.')));
      return;
    }
    for (const x of items) list.append(row(x));
    if (items.length < total && !(mode === 'app' && q.only)) {
      list.append(h('button', { class: 'btn small db-more', type: 'button', onclick: () => { page++; load(); } }, `Show more (${(total - items.length).toLocaleString()} left)`));
    }
  }

  function row(x) {
    const star = h('button', { class: 'icon-btn sm db-star' + (x.fav ? ' on' : ''), type: 'button', 'aria-pressed': String(!!x.fav),
      title: x.fav ? 'A favorite - click to take it off' : 'Make it a favorite' }, icon('doc-star'));
    const power = h('button', { class: 'btn small ghost db-off' + (x.off ? ' on' : ''), type: 'button', 'aria-pressed': String(!!x.off),
      title: x.off ? 'Turned off: WickedWhims never offers it - click to turn it back on' : 'Turn it off: WickedWhims will not offer it' },
    icon('doc-power'), x.off ? 'Turned off' : 'On');
    star.onclick = () => mark(x, 'favorite', !x.fav, el);
    power.onclick = () => mark(x, 'turn_off', !x.off, el);
    const who = x.genders && x.genders.length ? x.genders.map(g => ({ FEMALE: 'woman', MALE: 'man' }[g] || 'anyone')).join(' + ') : '';
    const watch = x.lib !== null && x.lib !== undefined && onPreview
      ? h('button', { class: 'btn small ghost db-watch', type: 'button', title: 'Watch it on the stage', onclick: () => onPreview(x) }, icon('play'), 'Watch') : null;
    const el = h('div', { class: 'db-row' + (x.off ? ' is-off' : ''), 'data-id': x.id },
      star,
      h('div', { class: 'db-t' }, h('b', {}, x.name),
        h('small', {}, [x.author, x.act_label, (x.places || []).join(', '), who || `${x.sims} sim${x.sims === 1 ? '' : 's'}`,
          x.props ? `${x.props} prop${x.props === 1 ? '' : 's'}` : '', x.hidden ? 'hidden in menus' : '', x.where === 'parked' ? 'set aside' : ''].filter(Boolean).join(' · ')),
        h('small', { class: 'db-file', title: x.file }, x.file)),
      watch, power);
    return el;
  }

  async function mark(x, action, on, el) {
    const key = action === 'favorite' ? 'fav' : 'off';
    const apply = () => { x[key] = on; const fresh = row(x); el.replaceWith(fresh); if (q.only && !x[q.only === 'fav' ? 'fav' : 'off']) fresh.classList.add('db-gone'); };
    if (mode === 'app') {
      const l = localLists.get();
      l[key][on ? 'add' : 'delete'](x.id);
      localLists.set(l);
      apply();
      toast(action === 'favorite' ? (on ? `"${x.name}" is a favorite (kept in this app).` : `"${x.name}" is no longer a favorite.`)
        : (on ? `"${x.name}" is turned off (kept in this app).` : `"${x.name}" is turned back on.`), 'ok');
      return;
    }
    el.classList.add('busy');
    let r;
    try { r = await fetchJson('/api/doctor_fix', { body: { action, id: x.id, on } }); }
    catch (e) { r = { ok: false, error: plainError(e, "WickedWhims' lists") }; }
    el.classList.remove('busy');
    if (!r || !r.ok) {
      if (r && r.reason === 'not_proven') { mode = 'app'; toast(r.error, 'err'); return mark(x, action, on, el); }
      toast((r && r.error) || 'That did not work.', 'err');
      return;
    }
    apply();
    toast(r.text || 'Done.', 'ok');
  }

  reload();
  root.refresh = () => { fetchJson('/api/doctor_browse?refresh=1').catch(() => null).finally(reload); };
  root.stop = () => { clearTimeout(timer); loading++; };
  return root;
}
