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
import { $t } from './i18n.js';

const PAGE = 150;
const LOCAL = 'fsa.doctor.lists';
const ACTS = [['', $t('doctorbrowse.any_kind')], ['TEASING', $t('doctorbrowse.teasing')], ['HANDJOB', $t('doctorbrowse.handjob')], ['FOOTJOB', $t('doctorbrowse.footjob')], ['ORALJOB', $t('doctorbrowse.oral')],
  ['VAGINAL', $t('doctorbrowse.vaginal')], ['ANAL', $t('doctorbrowse.anal')], ['CLIMAX', $t('doctorbrowse.climax')]];
const nicePlace = p => (p === 'CUSTOM' ? $t('doctorbrowse.custom_object') : p.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()));

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
  const search = h('input', { placeholder: $t('doctorbrowse.search_animations_or_creators'), spellcheck: 'false', 'aria-label': $t('doctorbrowse.search') });
  const where = h('select', { 'aria-label': $t('doctorbrowse.which_folder') }, [['mods', $t('doctorbrowse.in_mods')], ['parked', $t('doctorbrowse.set_aside_mods_parked')], ['all', $t('doctorbrowse.both')]].map(([v, t]) => h('option', { value: v }, t)));
  const place = h('select', { 'aria-label': $t('doctorbrowse.place') }, h('option', { value: '' }, $t('doctorbrowse.anywhere')));
  const act = h('select', { 'aria-label': $t('doctorbrowse.kind') }, ACTS.map(([v, t]) => h('option', { value: v }, t)));
  const sims = h('select', { 'aria-label': $t('doctorbrowse.sims') }, [['', $t('doctorbrowse.any_sims')], ['1', $t('doctorbrowse.1_sim')], ['2', $t('doctorbrowse.2_sims')], ['3', $t('doctorbrowse.3_sims')], ['4', $t('doctorbrowse.4_sims')]].map(([v, t]) => h('option', { value: v }, t)));
  const only = h('div', { class: 'seg-inline db-only', role: 'tablist' });
  const onlyBtns = [['', $t('doctorbrowse.all')], ['fav', $t('doctorbrowse.favorites')], ['off', $t('doctorbrowse.turned_off')]].map(([v, t]) => {
    const b = h('button', { type: 'button', class: v === q.only ? 'on' : '', 'data-only': v }, t);
    b.onclick = () => { q.only = v; onlyBtns.forEach(x => x.classList.toggle('on', x === b)); reload(); };
    return b;
  });
  only.append(...onlyBtns);
  const proof = h('div', { class: 'db-proof' });
  const count = h('div', { class: 'hint db-count', role: 'status', 'aria-live': 'polite' }, $t('doctorbrowse.reading_your_animations'));
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
      h('b', {}, mode === 'ww' ? $t('doctorbrowse.stars_and_switches_change_wickedwhim') : $t('doctorbrowse.stars_and_switches_are_kept')),
      h('small', {}, pr.text || '')));
  }

  function drawPlaces(r) {
    const keep = place.value;
    place.innerHTML = '';
    place.append(h('option', { value: '' }, $t('doctorbrowse.anywhere')),
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
    catch (e) { if (my === loading) { count.textContent = plainError(e, $t('doctorbrowse.your_animations')); list.innerHTML = ''; } return; }
    if (my !== loading || !root.isConnected) return;
    if (!r.ready) {
      count.textContent = r.error ? plainError(r.error, $t('doctorbrowse.your_animations'))
        : r.total ? $t('doctorbrowse.reading_progress', { done: r.done, total: r.total }) : $t('doctorbrowse.reading');
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
    count.textContent = $t('doctorbrowse.count', { n: total }) + (q.where === 'mods' && c.parked ? $t('doctorbrowse.more_set_aside', { parked: c.parked }) : '')
      + (r.not_shown ? $t('doctorbrowse.not_shown_not_for_adults', { not_shown: r.not_shown }) : '');
    draw();
  }

  function draw() {
    list.innerHTML = '';
    if (!items.length) {
      list.append(h('div', { class: 'empty-state compact' }, h('b', {}, q.q || q.place || q.act || q.sims || q.only ? $t('doctorbrowse.nothing_matches') : $t('doctorbrowse.no_wickedwhims_animations_here')),
        h('p', {}, q.q || q.place || q.act || q.sims || q.only ? $t('doctorbrowse.change_search_or_filters') : $t('doctorbrowse.animation_packs_in_your_mods'))));
      return;
    }
    for (const x of items) list.append(row(x));
    if (items.length < total && !(mode === 'app' && q.only)) {
      list.append(h('button', { class: 'btn small db-more', type: 'button', onclick: () => { page++; load(); } }, $t('doctorbrowse.show_more_left', { total: (total - items.length).toLocaleString() })));
    }
  }

  function row(x) {
    const star = h('button', { class: 'icon-btn sm db-star' + (x.fav ? ' on' : ''), type: 'button', 'aria-pressed': String(!!x.fav),
      title: x.fav ? $t('doctorbrowse.favorite_click_to_take_it') : $t('doctorbrowse.make_it_favorite') }, icon('doc-star'));
    const power = h('button', { class: 'btn small ghost db-off' + (x.off ? ' on' : ''), type: 'button', 'aria-pressed': String(!!x.off),
      title: x.off ? $t('doctorbrowse.turned_off_wickedwhims_never_offers') : $t('doctorbrowse.turn_it_off_wickedwhims_will') },
    icon('doc-power'), x.off ? $t('doctorbrowse.turned_off') : $t('doctorbrowse.on'));
    star.onclick = () => mark(x, 'favorite', !x.fav, el);
    power.onclick = () => mark(x, 'turn_off', !x.off, el);
    const who = x.genders && x.genders.length ? x.genders.map(g => ({ FEMALE: 'woman', MALE: 'man' }[g] || 'anyone')).join(' + ') : '';
    const watch = x.lib !== null && x.lib !== undefined && onPreview
      ? h('button', { class: 'btn small ghost db-watch', type: 'button', title: $t('doctorbrowse.watch_it_on_stage'), onclick: () => onPreview(x) }, icon('play'), $t('doctorbrowse.watch')) : null;
    const el = h('div', { class: 'db-row' + (x.off ? ' is-off' : ''), 'data-id': x.id },
      star,
      h('div', { class: 'db-t' }, h('b', {}, x.name),
        h('small', {}, [x.author, x.act_label, (x.places || []).join(', '), who || $t('doctorbrowse.sims', { n: x.sims }),
          x.props ? $t('doctorbrowse.props', { n: x.props }) : '', x.hidden ? $t('doctorbrowse.hidden_in_menus') : '', x.where === 'parked' ? $t('doctorbrowse.set_aside') : ''].filter(Boolean).join(' · ')),
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
      toast(action === 'favorite' ? (on ? $t('doctorbrowse.is_favorite_kept_in_this', { xName: x.name }) : $t('doctorbrowse.is_no_longer_favorite', { xName: x.name }))
        : (on ? $t('doctorbrowse.is_turned_off_kept_in', { xName: x.name }) : $t('doctorbrowse.is_turned_back_on', { xName: x.name })), 'ok');
      return;
    }
    el.classList.add('busy');
    let r;
    try { r = await fetchJson('/api/doctor_fix', { body: { action, id: x.id, on } }); }
    catch (e) { r = { ok: false, error: plainError(e, $t('doctorbrowse.wickedwhims_lists')) }; }
    el.classList.remove('busy');
    if (!r || !r.ok) {
      if (r && r.reason === 'not_proven') { mode = 'app'; toast(r.error, 'err'); return mark(x, action, on, el); }
      toast((r && r.error) || $t('doctorbrowse.that_did_not_work'), 'err');
      return;
    }
    apply();
    toast(r.text || $t('doctorbrowse.done'), 'ok');
  }

  reload();
  root.refresh = () => { fetchJson('/api/doctor_browse?refresh=1').catch(() => null).finally(reload); };
  root.stop = () => { clearTimeout(timer); loading++; };
  return root;
}
