// Novulon's Sims Hub - the app. A plain ES module with no libraries; it talks to speedkit/hub/server.py.
// Every word it shows comes from the language catalogs (i18n/<code>.json, through js/i18n.js).
import * as care from './care.js';          // patch day, game errors, save backups, load-time savings
import * as I from './i18n.js';
const { t, h, raw } = I;

// ------------------------------------------------------------------------------------------ small helpers
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ESC[c]);
const ic = (id, cls = '') => `<svg${cls ? ` class="${cls}"` : ''} aria-hidden="true"><use href="#i-${id}"/></svg>`;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const isNum = n => n !== null && n !== undefined && n !== '' && !isNaN(Number(n));
const num = n => isNum(n) ? I.num(Math.round(Number(n))) : '—';
const gb = g => !isNum(g) ? '—' : t('unit.gb', { v: Number(g) >= 100 ? I.num(Math.round(g)) : I.num(Number(g), 1) });
const mbText = m => t('unit.mb', { v: I.num(Math.round(Number(m))) });
// how much the duplicate clean-up frees: small amounts in MB, never "0 GB"
const planSize = p => !p || !isNum(p.gb) || Number(p.gb) >= 0.1 || !isNum(p.mb) ? gb(p && p.gb)
  : Number(p.mb) < 1 ? t('unit.lt1mb') : mbText(p.mb);

function dur(s, short = false) {
  if (!isNum(s)) return '—';
  s = Math.round(Number(s));
  if (s < 60) return t('unit.s', { n: s });
  const m = Math.floor(s / 60), r = String(s % 60).padStart(2, '0');
  if (m < 60) return short ? t('unit.m_s_short', { m, s: r }) : t('unit.min_s', { m, s: r });
  return t('unit.h_min', { h: Math.floor(m / 60), m: m % 60 });
}

function ago(iso) {
  const ms = Date.parse(iso);
  if (!ms) return '';
  const s = (Date.now() - ms) / 1000;
  if (s < 90) return t('time.just_now');
  if (s < 3600) return t('time.min_ago', { n: Math.round(s / 60) });
  if (s < 86400) return t('time.hours_ago', { n: Math.round(s / 3600) });
  if (s < 2 * 86400) return t('time.yesterday');
  if (s < 14 * 86400) return t('time.days_ago', { n: Math.floor(s / 86400) });
  const d = new Date(ms);
  return I.date(d, { day: 'numeric', month: 'short', year: d.getFullYear() === new Date().getFullYear() ? undefined : 'numeric' });
}

// "24 Sep" and "24 Sep, 14:05" in the chosen language
const day = iso => { const d = new Date(iso); return isNaN(d) ? '' : I.date(d, { day: 'numeric', month: 'short' }); };
const dayTime = iso => {
  const d = new Date(iso);
  return isNaN(d) ? '' : t('time.day_time', { day: day(iso), time: I.time(d, { hour: 'numeric', minute: '2-digit' }) });
};

// the web font, without ever blocking the window (offline, Segoe UI is used)
(() => {
  const l = document.createElement('link');
  l.rel = 'stylesheet';
  l.href = 'https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap';
  document.head.appendChild(l);
})();

// ------------------------------------------------------------------------------------------ talking to the Hub
async function call(path, body) {
  const opt = body === undefined ? { cache: 'no-store' }
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  try {
    const r = await fetch('/api/' + path, opt);
    let data = {};
    try { data = await r.json(); } catch { data = {}; }
    if (!data || typeof data !== 'object' || Array.isArray(data)) data = {};
    data.http = r.status;
    if (!r.ok && data.ok === undefined) data.ok = false;
    return data;
  } catch {
    return { ok: false, http: 0, message: t('app.no_answer') };
  }
}

// ------------------------------------------------------------------------------------------ state
const S = {
  status: null, statusErr: null, statusKey: '',
  saves: null, savesLoading: false,
  graphics: null, graphicsLoading: false,
  inbox: null, inboxLoading: false,
  plan: null,
  page: 'home',
  taskId: null,
};
const st = () => S.status || {};
const gameFound = () => { const g = st().game; return !g || g.found !== false; };
const gameRunning = () => !!st().game_running;
const busy = () => !!S.taskId;
const canPlay = () => !!S.status && gameFound() && !gameRunning() && !busy();
const saveBySlot = slot => ((S.saves && S.saves.saves) || []).find(s => s.slot === slot);
const FASTISH = new Set(['fast', 'save', 'studio']);
const gamePath = g => (g && (g.game_dir || g.path || (g.exe || '').replace(/\\Game(?:\\Bin)?\\TS4_x64\.exe$/i, ''))) || '';
const gameMoved = g => !!g && g.found === false && !!(g.saved || g.exe || g.game_dir);
// the server adds the English original of each sentence it translated as <field>_en: the page reads that one
// whenever it looks for words in it
const en = (obj, field) => (obj && (obj[field + '_en'] ?? obj[field])) || '';

function modeInfo(p = {}) {
  switch (p.name) {
    case 'fast': return { title: t('mode.quick'), sub: t('mode.quick.sub') };
    case 'full': return { title: t('mode.full'), sub: t('mode.full.sub'), cls: 'full' };
    case 'save': {
      const s = saveBySlot(p.save_slot), m = /'(.+)'\s*$/.exec(en(p, 'label'));
      return { title: s ? s.name : m ? m[1] : t('mode.save'), sub: t('mode.save.sub') };
    }
    case 'studio': return { title: t('mode.studio'), sub: t('mode.studio.sub') };
    case 'custom': return { title: t('mode.custom'), sub: t('mode.custom.sub'), cls: 'full' };
    default: return { title: p.label || t('common.not_known'), sub: '' };
  }
}
const PROFILE_KEYS = { fast: 'mode.quick', full: 'mode.full', save: 'mode.save', studio: 'mode.studio', custom: 'mode.custom' };
const profileWords = p => t(PROFILE_KEYS[p] || 'mode.your_mods');

// one entry per game start: the engine logs 'main_menu' and 'lot_loaded' as separate rows (newest first), so a
// start takes the first lot load that followed it
function starts() {
  const out = [];
  let lot = null;
  for (const r of st().load_times || []) {
    if (isNum(r.launch_to_menu_s)) {
      out.push(Object.assign({}, r, { lot_load_s: isNum(r.lot_load_s) ? r.lot_load_s : lot }));
      lot = null;
    } else if (isNum(r.lot_load_s)) lot = r.lot_load_s;
  }
  return out;
}

function ccNow() {
  const lib = st().library || {}, p = st().profile || {};
  if (isNum(lib.cas_now)) return lib.cas_now;
  if (p.name === 'full') return lib.cas_full;
  if (p.name === 'fast') return lib.cas_fast;
  if (p.name === 'save') { const s = saveBySlot(p.save_slot); return s ? s.cas_loaded : null; }
  return null;
}

// ------------------------------------------------------------------------------------------ pages
const PAGES = { home: renderHome, saves: renderSaves, library: renderLibrary, performance: renderPerformance, tools: renderTools };

function pageName() {
  const p = location.hash.replace(/^#/, '').split(/[?&]/)[0];
  return PAGES[p] ? p : 'home';
}

function route() {
  S.page = pageName();
  $$('#rail a').forEach(a => {
    a.classList.toggle('active', a.dataset.page === S.page);
    if (a.dataset.page === S.page) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  document.title = S.page === 'home' ? t('app.name') : t('app.page_title', { page: t('nav.' + S.page) });
  render(true);
  loadForPage();
}

function loadForPage() {
  if (!S.status) return;
  if (S.page === 'saves' || (S.page === 'home' && st().profile && st().profile.name === 'save')) ensureSaves();
  if (S.page === 'library') ensureInbox();
  if (S.page === 'performance') ensureGraphics();
  care.load(S.page);
}

// sections that keep their own elements alive across re-draws put them back here (e.g. the CC browser)
const AFTER_RENDER = [];

function render(fresh = false) {
  const page = $('#page');
  const act = document.activeElement;
  const keep = act && act.id && page.contains(act) ? { id: act.id, a: act.selectionStart, b: act.selectionEnd } : null;
  const open = !fresh && $$('details', page).map(d => d.open);      // a re-draw keeps opened sections open
  page.dataset.page = S.page;
  page.innerHTML = PAGES[S.page]();
  if (open) $$('details', page).forEach((d, i) => { if (open[i]) d.open = true; });
  if (fresh) $('#main').scrollTop = 0;
  // the page's entrance (staggered cards, growing bars) plays when a page opens or its content first arrives; a
  // re-draw while it plays carries on where it was (--el), and later quiet re-draws don't move anything
  const loading = !!page.querySelector(':scope > .page-loading, .skel-grid');
  const now = performance.now();
  if (fresh || (render.wasLoading && !loading)) {
    render.t0 = now;
    page.style.setProperty('--el', '0s');
    page.classList.remove('enter'); void page.offsetWidth; page.classList.add('enter');
    clearTimeout(render.enterT);
    render.enterT = setTimeout(() => page.classList.remove('enter'), 1400);
  } else if (page.classList.contains('enter')) page.style.setProperty('--el', ((now - render.t0) / 1000).toFixed(3) + 's');
  render.wasLoading = loading;
  if (S.page === 'performance') drawChart();
  AFTER_RENDER.forEach(fn => fn(fresh));
  const back = keep && document.getElementById(keep.id);
  if (back && back !== document.activeElement) { back.focus(); try { back.setSelectionRange(keep.a, keep.b); } catch { /* not a text box */ } }
}

function renderTop() {
  const s = st(), chip = $('#mode-chip');
  if (S.status && s.profile) {
    const m = modeInfo(s.profile);
    chip.innerHTML = `<i class="${m.cls || ''}"></i><span>${esc(t('top.right_now'))}</span><b>${esc(m.title)}</b>`;
    chip.title = t('top.right_now_title', { mode: m.title });
    chip.classList.remove('hidden');
  } else chip.classList.add('hidden');
  $('#preview-chip').classList.toggle('hidden', !(s.hub && s.hub.preview));
  $('#game-chip').classList.toggle('hidden', !gameRunning());
}

// the words in index.html itself (the rail, the top bar...): data-i18n / data-i18n-title / data-i18n-aria
function applyStatic() {
  document.documentElement.lang = I.lang();
  $$('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  $$('[data-i18n-title]').forEach(el => {
    const words = t(el.dataset.i18nTitle);
    if (el.dataset.tip) el.dataset.tip = words; else el.title = words;     // the tooltip may have taken the title
    if (el.dataset.tipAria) el.setAttribute('aria-label', words);
  });
  $$('[data-i18n-aria]').forEach(el => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
}

function loadingBlock(text) {
  return `<div class="page-loading"><div class="spinner"></div><span>${esc(text)}</span></div>
    <div class="skel-page" aria-hidden="true"><div class="skel wide"></div><div class="skel tall"></div><div class="skel"></div><div class="skel"></div><div class="skel"></div></div>`;
}

function errorBlock(text) {
  return `<div class="note err" style="margin-top:40px">${ic('warn')}<div><b>${esc(text)}</b><div class="actions" style="margin-top:10px">
    <button class="btn small" data-act="refresh">${ic('refresh')}${esc(t('common.try_again'))}</button></div></div></div>`;
}

// -------------------------------------------------------------------------------- Home
function renderHome() {
  if (!S.status) return S.statusErr ? errorBlock(S.statusErr) : loadingBlock(t('common.checking_game'));
  const s = st(), lib = s.library || {}, times = starts();
  const lastOf = names => times.find(x => names.includes(x.profile) && isNum(x.launch_to_menu_s));
  const lastFast = lastOf(['fast']), lastFull = lastOf(['full']);
  const fp = s.fastpack || {};
  const g = s.game || {};
  const off = canPlay() ? '' : ' disabled';

  let top = '';
  if (gameRunning()) {
    top = `<div class="play-row"><div class="state-card running"><div class="big-dot"><i></i></div><div class="grow">
      <h2>${esc(t('home.running.title'))}</h2><p>${esc(t('home.running.text'))}</p></div></div></div>`;
  } else {
    if (!gameFound()) {
      const moved = gameMoved(g), where = gamePath(g);
      top += `<div class="state-card find"><svg class="bob" viewBox="0 0 24 36" aria-hidden="true"><use href="#i-bob"/></svg><div class="grow">
        <h2>${esc(t(moved ? 'home.find.moved_title' : 'home.find.title'))}</h2>
        <p>${moved ? (where ? h('home.find.moved_at', { path: raw(`<span class="path">${esc(where)}</span>`) }) : esc(g.message || t('home.find.show_where')))
          : esc(t('home.find.text'))}</p></div>
        <button class="btn primary big" data-act="find-game">${ic('search')}${esc(t('common.locate'))}</button></div>`;
    }
    const fastMeta = [];
    if (isNum(lib.cas_fast) && isNum(lib.cas_full)) fastMeta.push(`<span class="pill">${esc(t('home.quick.loads', { a: num(lib.cas_fast), b: num(lib.cas_full) }))}</span>`);
    if (lastFast) fastMeta.push(`<span>${esc(t('home.last_load', { d: dur(lastFast.launch_to_menu_s) }))}</span>`);
    if (fp.state === 'stale' || fp.state === 'missing') fastMeta.push(`<span>${esc(t('home.quick.first'))}</span>`);
    const fullMeta = [];
    if (isNum(lib.cas_full)) fullMeta.push(`<span class="pill">${esc(t('home.full.loads', { n: Number(lib.cas_full) }))}</span>`);
    if (lastFull) fullMeta.push(`<span>${esc(t('home.last_load', { d: dur(lastFull.launch_to_menu_s) }))}</span>`);
    top += `<div class="play-row">
      <button class="play fast" data-act="play" data-target="fast"${off}>
        <div class="top"><div class="pic">${ic('bolt-fill')}</div><div class="t">${esc(t('mode.quick'))}</div></div>
        <div class="d">${esc(t('home.quick.desc'))}</div>
        <div class="m">${fastMeta.join('')}</div>
        <span class="go">${ic('play')}</span>
      </button>
      <button class="play all" data-act="play" data-target="full"${off}>
        <div class="top"><div class="pic">${ic('stack')}</div><div class="t">${esc(t('mode.full'))}</div></div>
        <div class="d">${esc(t('home.full.desc'))}</div>
        <div class="m">${fullMeta.join('')}</div>
        <span class="go">${ic('play')}</span>
      </button></div>`;
  }

  const [h1, line] = gameRunning() ? [t('home.running.title'), t('home.running.line')]
    : !gameFound() ? [t('home.notfound.title'), t('home.notfound.line')]
    : [t('home.title'), t('home.line')];
  return `<div class="hello">
      <div><h1>${esc(h1)}</h1><p>${esc(line)}</p></div>
    </div>
    ${top}
    <div class="notices">${care.homeBanner()}</div>
    <h3 class="sec">${esc(t('home.right_now'))}</h3>
    <div class="stats">${statCards().join('')}</div>
    ${care.homeSavings()}`;
}

// what the "CC items loaded" card says, by the way the game starts right now
const CC_LOADED = { full: 'stat.cc.full', fast: 'stat.cc.fast', save: 'stat.cc.save', studio: 'stat.cc.studio', custom: 'stat.cc.custom' };

function statCards() {
  const s = st(), lib = s.library || {}, mem = s.memory || {}, gfx = s.graphics || {}, disk = s.disk || {};
  const cards = [];
  const m = modeInfo(s.profile);
  cards.push(`<div class="stat"><div class="lbl">${ic('swap')}${esc(t('stat.how'))}</div><div class="v">${esc(m.title)}</div><div class="s">${esc(m.sub)}</div></div>`);

  const now = ccNow(), all = lib.cas_full, mode = (s.profile || {}).name;
  const pct = isNum(now) && isNum(all) && all > 0 ? Math.max(0.5, Math.min(100, now / all * 100)) : null;
  cards.push(`<div class="stat"><div class="lbl">${ic('shirt')}${esc(t('stat.cc'))}</div>
    <div class="v">${num(now)} <small>${esc(t('stat.of', { n: num(all) }))}</small></div>
    <div class="s">${esc(isNum(now) ? t(CC_LOADED[mode] || (now >= all ? CC_LOADED.full : 'stat.cc.part'))
      : ['studio', 'custom'].includes(mode) ? t('stat.cc.not_counted') : t('stat.cc.later'))}</div>
    ${pct === null ? '' : `<div class="meter"><i class="${now >= all ? 'full' : ''}" style="width:${pct.toFixed(2)}%"></i></div>`}</div>`);

  const last = starts()[0];
  cards.push(last
    ? `<div class="stat"><div class="lbl">${ic('clock')}${esc(t('stat.last'))}</div><div class="v">${dur(last.launch_to_menu_s)}</div>
       <div class="s">${h('stat.last.with', { mode: profileWords(last.profile), ago: ago(last.time) })}</div>
       ${isNum(last.lot_load_s) ? `<div class="s">${esc(t('stat.last.lot', { d: dur(last.lot_load_s) }))}</div>` : ''}</div>`
    : `<div class="stat"><div class="lbl">${ic('clock')}${esc(t('stat.last'))}</div><div class="v">${esc(t('stat.last.none'))}</div>
       <div class="s">${esc(t('stat.last.none_text'))}</div></div>`);

  if (gfx.state === 'tuned') {
    cards.push(`<div class="stat good"><div class="lbl">${ic('image')}${esc(t('stat.gfx'))}</div><div class="v">${esc(t('gfx.tuned'))}</div>
      <div class="ok-line">${ic('check')}${esc(t('stat.gfx.tuned_ok'))}</div></div>`);
  } else if (gfx.can_tune) {
    cards.push(`<div class="stat warn"><div class="lbl">${ic('image')}${esc(t('stat.gfx'))}</div><div class="v">${esc(t('stat.gfx.lag'))}</div>
      <div class="s">${esc(gfx.label || t('stat.gfx.lag_text'))}</div>
      <div class="foot"><button class="btn small primary" data-act="gfx-fix"${busy() || gameRunning() ? ' disabled' : ''}>${ic('spark')}${esc(t('stat.gfx.fix'))}</button></div></div>`);
  } else if (gfx.state === 'stock') {
    cards.push(`<div class="stat"><div class="lbl">${ic('image')}${esc(t('stat.gfx'))}</div><div class="v">${esc(t('stat.gfx.stock'))}</div>
      <div class="s">${esc(t('stat.gfx.stock_text'))}</div></div>`);
  } else {
    cards.push(`<div class="stat"><div class="lbl">${ic('image')}${esc(t('stat.gfx'))}</div><div class="v">${esc(gfx.label || t('common.not_known'))}</div>
      <div class="s">${esc((gfx.details || [])[0] || '')}</div></div>`);
  }

  const warns = mem.warnings || [];
  cards.push(`<div class="stat${warns.length ? ' warn' : ' good'}"><div class="lbl">${ic('chip')}${esc(t('stat.mem'))}</div>
    <div class="v">${h('stat.mem.value', { free: gb(mem.free_gb), total: gb(mem.total_gb) })}</div>
    ${isNum(mem.free_gb) && isNum(mem.total_gb) && mem.total_gb > 0
      ? `<div class="meter mem"><i class="${warns.length ? 'warn' : 'ok'}" style="width:${Math.max(2, Math.min(100, (1 - mem.free_gb / mem.total_gb) * 100)).toFixed(1)}%"></i></div>` : ''}
    ${warns.length ? warns.slice(0, 2).map(w => `<div class="warn-line">${ic('warn')}<span>${esc(w)}</span></div>`).join('')
      : `<div class="ok-line">${ic('check')}${esc(t('stat.mem.ok'))}</div>`}</div>`);

  const low = isNum(disk.c_free_gb) && disk.c_free_gb < 25;
  cards.push(`<div class="stat${low ? ' warn' : ''}"><div class="lbl">${ic('drive')}${esc(t('stat.disk'))}</div>
    <div class="v">${h('stat.disk.value', { gb: gb(disk.c_free_gb) })}</div>
    ${low ? `<div class="warn-line">${ic('warn')}<span>${esc(t('stat.disk.low'))}</span></div>
      <div class="foot"><a class="btn small" href="#library">${ic('broom')}${esc(t('common.free_up'))}</a></div>`
      : `<div class="s">${esc(t('stat.disk.lib', { n: Number(lib.packages) || 0, gb: gb(lib.gb) }))}</div>`}</div>`);
  return cards;
}

// -------------------------------------------------------------------------------- Saves
function renderSaves() {
  const head = `<div class="page-head"><div class="grow"><h1>${h('saves.h1')}</h1>
    <p>${esc(t('saves.intro'))}</p></div>
    <button class="btn" data-act="saves-refresh"${S.savesLoading ? ' disabled' : ''}>${ic('refresh')}${esc(t('common.look_again'))}</button></div>`;
  if (!S.saves) {
    return head + (S.savesLoading || !S.status ? `<div class="saves-loading"><div class="spinner"></div><div><b>${esc(t('saves.loading'))}</b>
      <div class="muted">${esc(t('saves.loading_note'))}</div></div></div>
      <div class="saves skel-grid" aria-hidden="true"><div class="save skel"></div><div class="save skel"></div><div class="save skel"></div></div>` : '');
  }
  if (!S.saves.ok) return head + `<div class="note err">${ic('warn')}<span>${esc(S.saves.message || t('saves.error'))}</span></div>`;
  const saves = [...(S.saves.saves || [])].sort((a, b) => (Date.parse(b.last_played) || 0) - (Date.parse(a.last_played) || 0));
  if (!saves.length) {
    return head + `<div class="card empty">${h('saves.none')}</div>`;
  }
  const p = st().profile || {};
  const why = gameRunning() ? t('saves.why_running') : !gameFound() ? t('saves.why_find') : '';
  return head + `<div class="saves">${saves.map(s => {
    const sub = [s.household, s.world].filter(Boolean).join(' · ');
    const pack = s.pack || {};
    const extra = pack.state === 'fresh' ? `${ic('bolt')}${esc(t('saves.pack.fresh'))}${isNum(s.cas_loaded) ? ` · ${esc(t('saves.pack.loads', { n: Number(s.cas_loaded) }))}` : ''}`
      : pack.state === 'stale' ? `${ic('clock')}${esc(t('saves.pack.stale'))}`
      : `${ic('clock')}${esc(t('saves.pack.missing'))}`;
    const current = p.name === 'save' && p.save_slot === s.slot;
    const letter = (String(s.name || '?').trim()[0] || '?').toUpperCase();
    return `<div class="save">
      <div class="head"><div class="avatar">${esc(letter)}</div><div class="who"><b title="${esc(s.name)}">${esc(s.name || s.slot)}</b>
        ${sub ? `<span title="${esc(sub)}">${esc(sub)}</span>` : ''}</div></div>
      <div class="when">${ic('clock')}${esc(t('saves.played', { ago: ago(s.last_played) }))}${current ? ` <span class="chip ok" style="margin-left:4px">${esc(t('saves.current'))}</span>` : ''}</div>
      <div class="facts"><span class="chip">${ic('users')}${esc(t('saves.sims', { n: Number(s.sims) || 0 }))}</span><span class="chip">${ic('lot')}${esc(t('saves.lots', { n: Number(s.lots) || 0 }))}</span>
        ${isNum(s.cc_parts) ? `<span class="chip hot">${ic('shirt')}${esc(t('saves.cc_items', { n: Number(s.cc_parts) }))}</span>` : ''}
        ${isNum(s.cc_missing) && s.cc_missing > 0 ? `<span class="chip warn" title="${esc(t('saves.missing_title'))}">${ic('warn')}${esc(t('saves.missing', { n: Number(s.cc_missing) }))}</span>` : ''}</div>
      <div class="extra">${s.problem ? `${ic('warn')}${esc(s.problem)}` : extra}</div>
      ${care.saveLine(s)}
      ${saveCcButton(s)}
      <button class="btn primary block" data-act="play" data-target="save:${esc(s.slot)}"${canPlay() ? '' : ' disabled'}>
        ${ic('play')}${esc(why || t('saves.play'))}</button>
    </div>`;
  }).join('')}</div>${care.savesSection()}` + trayCcCard();
}

// -------------------------------------------------------------------------------- Library
function renderLibrary() {
  if (!S.status) return S.statusErr ? errorBlock(S.statusErr) : loadingBlock(t('lib.loading'));
  const lib = st().library || {};
  const ib = S.inbox;
  const items = (ib && ib.ok && ib.items) || [];
  const stateOf = i => String(i.status || '').toLowerCase();
  const waiting = items.filter(i => !['added', 'done', 'installed'].includes(stateOf(i)));
  const addable = waiting.filter(i => !['refused', 'skipped'].includes(stateOf(i)));
  const noChange = busy() || gameRunning();
  let inboxBody;
  if (!ib) inboxBody = `<div class="saves-loading" style="padding:16px 4px"><div class="spinner sm"></div>${esc(t('lib.inbox.loading'))}</div>`;
  else if (!ib.ok) inboxBody = `<div class="note err">${ic('warn')}<span>${esc(ib.message || t('lib.inbox.error'))}</span></div>`;
  else if (!waiting.length) inboxBody = `<div class="empty" style="padding:14px 2px 0">${h('lib.inbox.empty')}</div>`;
  else inboxBody = `<div class="items">${waiting.slice(0, 12).map(i => `<div class="item">${ic(/\.ts4script$/i.test(i.name) ? 'terminal' : 'download')}
      <span class="n" title="${esc(i.name)}">${esc(i.name)}</span><span class="r" title="${esc(i.reason || '')}">${
        stateOf(i) === 'refused' ? `<span class="chip warn">${esc(t('lib.inbox.refused'))}</span> ` : stateOf(i) === 'skipped' ? `<span class="chip">${esc(t('lib.inbox.skipped'))}</span> ` : ''}${esc(i.reason || '')}</span></div>`).join('')}
      ${waiting.length > 12 ? `<div class="muted" style="padding:4px 2px">${esc(t('lib.inbox.more', { n: waiting.length - 12 }))}</div>` : ''}</div>`;
  const plan = S.plan;
  return `<div class="page-head"><div class="grow"><h1>${h('lib.h1')}</h1>
      <p>${esc(isNum(lib.packages) ? t('lib.summary', { n: Number(lib.packages), gb: gb(lib.gb) }) : t('lib.intro'))}</p></div></div>
    ${ccSlot()}

    <div class="lib-more">
    <div class="card"><div class="card-head"><div class="ic">${ic('download')}</div><div class="grow"><h2>${esc(t('lib.inbox.title'))}</h2>
      <p>${h('lib.inbox.text')}</p></div></div>
      <div class="path-box">${ic('folder', 'fold')}<span class="path">${esc((ib && ib.inbox_path) || t('lib.inbox.finding'))}</span>
        <button class="btn small" data-act="open" data-what="inbox">${ic('folder')}${esc(t('common.open_folder'))}</button></div>
      ${inboxBody}
      <div class="actions"><button class="btn primary" data-act="inbox-apply"${addable.length && !noChange ? '' : ' disabled'}>${ic('check')}${esc(t('lib.inbox.add'))}${addable.length ? ` (${num(addable.length)})` : ''}</button>
        <button class="btn ghost" data-act="inbox-refresh"${S.inboxLoading ? ' disabled' : ''}>${ic('refresh')}${esc(t('common.look_again'))}</button></div>
    </div>

    <div class="card"><div class="card-head"><div class="ic pink">${ic('broom')}</div><div class="grow"><h2>${esc(t('common.free_up'))}</h2>
      <p>${esc(t('lib.cleanup.text'))}</p></div></div>
      ${plan && plan.ok ? `<div class="plan"><div><b>${planSize(plan)}</b><span>${esc(t('lib.plan.freed'))}</span></div><div><b>${num(plan.copies)}</b><span>${esc(t('lib.plan.copies'))}</span></div>
        <div><b>${num((plan.rewritten || 0) + (plan.removed || 0))}</b><span>${esc(t('lib.plan.files'))}</span></div></div>` : ''}
      <div class="actions"><button class="btn" data-act="cleanup-plan"${noChange ? ' disabled' : ''}>${ic('search')}${esc(t(plan ? 'lib.cleanup.again' : 'lib.cleanup.check'))}</button>
        ${plan && plan.ok && plan.copies > 0 ? `<button class="btn soft" data-act="cleanup-confirm"${noChange ? ' disabled' : ''}>${ic('broom')}${esc(t('lib.cleanup.go', { size: planSize(plan) }))}</button>` : ''}</div>
    </div>

    <div class="card"><div class="card-head"><div class="ic violet">${ic('doc')}</div><div class="grow"><h2>${esc(t('lib.report.title'))}</h2>
      <p>${esc(t('lib.report.text'))}</p></div></div>
      <div class="actions"><button class="btn" data-act="report"${busy() ? ' disabled' : ''}>${ic('doc')}${esc(t('lib.report.open'))}</button></div>
    </div>
    </div>`;
}

// -------------------------------------------------------------------------------- Performance
// the graphics settings the lag fix changes: gfx.<name> (what it controls) and gfx.<name>.why (a note, may be empty)
const GFX = ['RenderSimLODDistances', 'RenderSimTextureSizes', 'ObjectSizeCullFactor', 'ObjectLODBias', 'ClipPlaneDistances',
  'FSAALevel', 'ShadowMapSize', 'MirrorFadeRadiusThreshold', 'InteriorMirrorFarPlane', 'ExteriorMirrorFarPlane', 'TerrainLODBoost'];
const words = k => String(k || '').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/_/g, ' ');

function renderPerformance() {
  if (!S.status) return S.statusErr ? errorBlock(S.statusErr) : loadingBlock(t('common.checking_game'));
  const s = st(), gfx = s.graphics || {}, mon = s.monitor || {};
  const tuned = gfx.state === 'tuned';
  const noChange = busy() || gameRunning();
  const table = (S.graphics && S.graphics.ok && S.graphics.table) || [];
  const good = tuned || gfx.state === 'stock';
  const gState = `<div class="gfx-state ${good ? 'good' : gfx.can_tune ? 'bad' : ''}"><div class="dot">${ic(good ? 'check' : 'warn')}</div>
    <div><b>${esc(tuned ? t('gfx.tuned') : gfx.label || t('common.not_known'))}</b>
    <span>${esc(tuned ? t('perf.gfx.tuned_text') : gfx.can_tune ? t('perf.gfx.lag_text') : gfx.state === 'stock' ? t('perf.gfx.stock_text') : '')}</span></div></div>`;
  const details = (gfx.details || []).length ? `<ul class="details">${gfx.details.map(d => `<li>${esc(d)}</li>`).join('')}</ul>` : '';
  let tableHtml = '';
  if (table.length) {
    tableHtml = `<div class="table-wrap"><table class="t"><thead><tr><th>${esc(t('perf.th.what'))}</th><th>${esc(t('perf.th.stock'))}</th>
      <th>${esc(t(tuned ? 'perf.th.before' : 'perf.th.file_now'))}</th><th>${esc(t(tuned ? 'perf.th.now' : 'perf.th.with_fix'))}</th></tr></thead><tbody>
      ${table.map(r => {
        const prop = GFX.includes(r.prop) ? r.prop : GFX.includes(r.setting) ? r.setting : null;
        const what = prop ? t('gfx.' + prop) : r.prop ? r.setting : words(r.setting);
        const why = prop ? t('gfx.' + prop + '.why') : '';
        return `<tr><td><span class="what">${esc(what)}</span>${why ? `<span class="why">${esc(why)}</span>` : ''}</td>
          <td class="num">${esc(r.stock)}</td><td class="num before">${esc(r.before)}</td><td class="num after">${esc(r.after)}</td></tr>`;
      }).join('')}</tbody></table></div>`;
  } else if (S.graphicsLoading) {
    tableHtml = `<div class="saves-loading" style="padding:16px 4px"><div class="spinner sm"></div>${esc(t('perf.gfx.loading'))}</div>`;
  }
  let gActions = '';
  if (gfx.can_tune) gActions = `<button class="btn primary" data-act="gfx-fix"${noChange ? ' disabled' : ''}>${ic('spark')}${esc(t('perf.gfx.fix'))}</button>`;
  else if (tuned) gActions = `<button class="btn ghost" data-act="gfx-restore"${noChange ? ' disabled' : ''}>${ic('undo')}${esc(t('perf.gfx.restore'))}</button>`;

  return `<div class="page-head"><div class="grow"><h1><span>${esc(t('nav.performance'))}</span></h1>
      <p>${esc(t('perf.intro'))}</p></div></div>

    <div class="card"><div class="card-head"><div class="ic">${ic('image')}</div><div class="grow"><h2>${esc(t('stat.gfx'))}</h2>
      <p>${esc(t('perf.gfx.text'))}</p></div></div>
      ${gState}${details}${gActions ? `<div class="actions">${gActions}</div>` : ''}${tableHtml}</div>

    <div class="card"><div class="card-head"><div class="ic blue">${ic('clock')}</div><div class="grow"><h2>${esc(t('perf.times.title'))}</h2>
      <p>${esc(t('perf.times.text'))}</p></div></div>
      ${loadTimes()}</div>

    <div class="card"><div class="card-head"><div class="ic green">${ic('gauge')}</div><div class="grow"><h2>${esc(t('perf.lag.title'))}</h2>
      <p>${esc(t('perf.lag.text'))}</p></div>
      ${mon.installed ? `<span class="chip ok">${ic('check')}${esc(t('perf.lag.installed'))}</span>` : ''}</div>
      <ol class="steps">
        <li><div><b>${esc(t('perf.lag.s1'))}</b><span>${esc(t('perf.lag.s1_text'))}</span></div></li>
        <li><div><b>${h('perf.lag.s2')}</b><span>${esc(t('perf.lag.s2_text'))}</span></div></li>
        <li><div><b>${h('perf.lag.s3')}</b><span>${esc(t('perf.lag.s3_text'))}</span></div></li>
        <li><div><b>${esc(t('perf.lag.s4'))}</b><span>${esc(t('perf.lag.s4_text'))}</span></div></li>
      </ol>
      <div class="note">${ic('info')}<span>${h('perf.lag.longer')}</span></div>
      ${mon.installed ? '' : `<div class="note warn">${ic('warn')}<span>${esc(t('perf.lag.missing'))}</span></div>`}
      <div class="actions"><button class="btn" data-act="open" data-what="reports">${ic('folder')}${esc(t('perf.open_reports'))}</button></div></div>`;
}

function loadTimes() {
  const rows = starts();
  if (!rows.length) return `<div class="empty">${esc(t('perf.times.none'))}</div>`;
  const avg = list => list.length ? list.reduce((a, r) => a + Number(r.launch_to_menu_s), 0) / list.length : null;
  const fast = avg(rows.filter(r => FASTISH.has(r.profile))), full = avg(rows.filter(r => !FASTISH.has(r.profile)));
  const tiles = [
    `<div class="tile"><div class="lbl"><i class="sw" style="background:var(--fast)"></i>${esc(t('perf.avg.fast'))}</div><b>${fast === null ? '—' : dur(fast)}</b></div>`,
    `<div class="tile"><div class="lbl"><i class="sw" style="background:var(--full)"></i>${esc(t('perf.avg.full'))}</div><b>${full === null ? '—' : dur(full)}</b></div>`,
    fast && full && full > fast
      ? `<div class="tile hero"><div class="lbl">${ic('bolt')}${esc(t('perf.faster.lbl'))}</div><b>${esc(t('perf.faster', { x: I.num(full / fast, 1) }))}</b></div>`
      : `<div class="tile"><div class="lbl">${ic('clock')}${esc(t('perf.timed'))}</div><b>${num(rows.length)}</b></div>`,
  ];
  return `<div class="tiles">${tiles.join('')}</div>
    <div class="chart" id="chart" role="img" aria-label="${esc(t('perf.chart'))}"></div>
    <div class="legend"><span><i style="background:var(--fast)"></i>${esc(t('perf.legend.fast'))}</span><span><i style="background:var(--full)"></i>${esc(t('mode.full'))}</span></div>
    <details class="more"><summary>${esc(t('perf.list'))}</summary><div class="table-wrap"><table class="t">
      <thead><tr><th>${esc(t('perf.th.when'))}</th><th>${esc(t('perf.th.how'))}</th><th>${esc(t('perf.th.menu'))}</th><th>${esc(t('perf.th.lot'))}</th></tr></thead><tbody>
      ${rows.map(r => `<tr><td>${esc(dayTime(r.time))}</td><td>${esc(profileWords(r.profile))}</td>
        <td class="num">${dur(r.launch_to_menu_s)}</td><td class="num">${dur(r.lot_load_s)}</td></tr>`).join('')}</tbody></table></div></details>`;
}

function drawChart() {
  const host = $('#chart');
  if (!host) return;
  const rows = starts().slice(0, 20).reverse();
  if (!rows.length) return;
  const W = Math.max(280, host.clientWidth), H = 230, L = 58, R = 12, T = 24, B = 30;
  const pw = W - L - R, ph = H - T - B;
  const maxS = Math.max(...rows.map(r => Number(r.launch_to_menu_s)), 30);
  const maxM = maxS / 60;
  const step = [0.5, 1, 2, 5, 10, 15, 30, 60].find(x => maxM / x <= 4.5) || 60;
  const top = Math.ceil(maxM / step) * step * 60;
  const y = v => T + ph - (v / top) * ph;
  const slot = pw / rows.length, bw = Math.min(34, slot * 0.56);
  let g = '';
  for (let v = 0; v <= top + 1e-6; v += step * 60) {
    g += `<line class="grid-line${v === 0 ? ' base' : ''}" x1=""${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/>
      <text class="axis-t" x="${L - 10}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end">${v === 0 ? '0' : esc(t('unit.min', { n: +(v / 60).toFixed(1) }))}</text>`;
  }
  const every = Math.max(1, Math.ceil(rows.length / Math.max(1, Math.floor(pw / 74))));
  rows.forEach((r, i) => {
    const v = Number(r.launch_to_menu_s), x = L + i * slot + (slot - bw) / 2, y0 = T + ph, hh = Math.max(2, y0 - y(v)), yt = y0 - hh;
    const rad = Math.min(4, bw / 2, hh);
    const color = FASTISH.has(r.profile) ? 'url(#bar-fast)' : 'url(#bar-full)';
    g += `<path class="bar" data-i="${i}" fill="${color}" d="M${x.toFixed(1)},${y0} V${(yt + rad).toFixed(1)} Q${x.toFixed(1)},${yt.toFixed(1)} ${(x + rad).toFixed(1)},${yt.toFixed(1)}
      H${(x + bw - rad).toFixed(1)} Q${(x + bw).toFixed(1)},${yt.toFixed(1)} ${(x + bw).toFixed(1)},${(yt + rad).toFixed(1)} V${y0} Z"/>`;
    if (i === rows.length - 1) g += `<text class="val-t" x="${(x + bw / 2).toFixed(1)}" y="${(yt - 7).toFixed(1)}" text-anchor="middle">${esc(dur(v, true))}</text>`;
    if ((rows.length - 1 - i) % every === 0) {
      const d = new Date(r.time);
      g += `<text class="axis-t" x="${(L + i * slot + slot / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle">${isNaN(d) ? '' : esc(I.date(d, { month: 'short', day: 'numeric' }))}</text>`;
    }
    g += `<rect class="hit" data-i="${i}" x="${(L + i * slot).toFixed(1)}" y="${T}" width="${slot.toFixed(1)}" height="${ph}"/>`;
  });
  const defs = `<defs><linearGradient id="bar-fast" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff7ab4"/><stop offset="1" stop-color="#d93c80"/></linearGradient>
    <linearGradient id="bar-full" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8fb3ff"/><stop offset="1" stop-color="#3f6fd6"/></linearGradient></defs>`;
  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">${defs}${g}</svg>`;
  const tip = $('#tooltip');
  host.onmousemove = e => {
    const hit = e.target.closest('.hit');
    if (!hit) { host.onmouseleave(); return; }
    const i = +hit.dataset.i, r = rows[i];
    host.classList.add('hovering');
    $$('.bar', host).forEach(b => b.classList.toggle('on', +b.dataset.i === i));
    tip.innerHTML = `<b><i class="k" style="background:${FASTISH.has(r.profile) ? 'var(--fast)' : 'var(--full)'}"></i>${esc(profileWords(r.profile))}</b>
      <span class="muted">${esc(dayTime(r.time))}</span><br>${esc(t('perf.tip.menu', { d: dur(r.launch_to_menu_s) }))}${isNum(r.lot_load_s) ? `<br>${esc(t('perf.tip.lot', { d: dur(r.lot_load_s) }))}` : ''}`;
    tip.classList.remove('hidden');
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.min(window.innerWidth - tw - 10, e.clientX + 14) + 'px';
    tip.style.top = Math.max(10, e.clientY - th - 12) + 'px';
  };
  host.onmouseleave = () => { host.classList.remove('hovering'); tip.classList.add('hidden'); };
}

// -------------------------------------------------------------------------------- Tools
// change kind -> [catalog key, icon]
const KIND = {
  profile: ['kind.profile', 'swap'], inbox: ['kind.inbox', 'download'], dedup: ['kind.dedup', 'broom'],
  merge: ['kind.merge', 'layers'], settings: ['kind.settings', 'image'], caches: ['kind.caches', 'broom'],
  fastpack: ['kind.fastpack', 'bolt'], savepack: ['kind.savepack', 'bolt'], usedpack: ['kind.usedpack', 'bolt'],
  install: ['kind.monitor', 'gauge'], monitor: ['kind.monitor', 'gauge'], cleanup: ['kind.dedup', 'broom'],
};
const kindOf = k => KIND[k] || ['kind.other', 'spark'];
// the same rule as the engine's undo_last: finished (or failed) changes, not the small helper steps of a switch
const HELPER = ['thumbnail cache moved aside', 'bring the fast pack home'];
const isHelper = j => HELPER.some(x => en(j, 'note').startsWith(x));
// the engine says which change is next (it also skips a change whose files were changed since); the local rule
// is only for engines that do not say
const undoable = j => 'undoable' in j ? !!j.undoable
  : (s => (s === 'committed' || s.startsWith('failed')) && !isHelper(j))(String(j.state || '').toLowerCase());
const nextUndo = journals => journals.some(j => 'next_undo' in j) ? journals.find(j => j.next_undo) : journals.find(undoable);
const SWITCHED = { fast: 'change.to_quick', full: 'change.to_full', studio: 'change.to_studio', custom: 'change.to_custom' };
function describeChange(j) {
  const note = en(j, 'note'), [key, icon] = kindOf(j.kind), label = t(key);
  let m, title = label;
  if (j.kind === 'profile' && (m = /^switch to (\w+)/i.exec(note))) title = t(SWITCHED[m[1].toLowerCase()] || 'change.to_save');
  else if (j.kind === 'inbox' && (m = /^(\d+) download/.exec(note))) title = t('change.downloads', { n: +m[1] });
  else if (j.kind === 'settings' && /max quality/i.test(note)) title = t('change.gfx_tuned');
  else if (j.kind === 'settings' && /restore|put back/i.test(note)) title = t('change.gfx_back');
  else if (j.kind === 'install' && /^uninstall/i.test(note)) title = t('change.monitor_removed');
  else if (j.kind === 'install') title = t('change.monitor_installed');
  else if (j.kind === 'aside') title = t(/^put back/i.test(note) ? 'change.put_back' : /\(fix\)/.test(note) ? 'change.aside_fix' : 'change.aside');
  return { title, label, icon };
}

function languageCard() {
  return `<div class="card lang-card" id="lang-card"><div class="card-head"><div class="ic violet">${ic('globe')}</div><div class="grow"><h2>${esc(t('tools.lang.title'))}</h2>
      <p>${esc(t('tools.lang.text'))}</p></div>
      <select id="lang-pick" class="lang-pick" aria-label="${esc(t('tools.lang.title'))}">${I.LANGUAGES.map(l =>
        `<option value="${esc(l.code)}" lang="${esc(l.code)}"${l.code === I.lang() ? ' selected' : ''}>${esc(l.name)}</option>`).join('')}</select></div></div>`;
}

function renderTools() {
  if (!S.status) return S.statusErr ? errorBlock(S.statusErr) : loadingBlock(t('common.checking_game'));
  const s = st(), anim = s.animator || {}, g = s.game || {};
  const noChange = busy() || gameRunning();
  const journals = s.journals || [];
  const next = nextUndo(journals);
  const where = gamePath(g);
  const shown = journals.filter(j => !isHelper(j));
  const changes = shown.length ? `<div class="changes">${shown.map(j => {
    const d = describeChange(j);
    const state = String(j.state || '').toLowerCase();
    const chip = state === 'undone' ? `<span class="chip">${esc(t('tools.chip.undone'))}</span>` : state === 'rolled_back' ? `<span class="chip">${esc(t('tools.chip.cancelled'))}</span>`
      : j === next ? `<span class="chip hot">${esc(t('tools.chip.next'))}</span>`
      : j.cannot_undo ? `<span class="chip" title="${esc(t('tools.chip.cannot_title'))}">${esc(t('tools.chip.cannot'))}</span>`
      : state === 'open' || state.startsWith('failed') ? `<span class="chip warn">${esc(t('tools.chip.unfinished'))}</span>` : '';
    return `<div class="change${state === 'undone' || state === 'rolled_back' ? ' undone' : ''}${j === next ? ' next' : ''}">
      <div class="ci">${ic(d.icon)}</div><div style="min-width:0"><b>${esc(d.title)}</b>
      <span>${esc(d.title !== d.label ? d.label + ' · ' : '')}${esc(ago(j.when))}</span></div>${chip}</div>`;
  }).join('')}</div>` : `<div class="empty">${esc(t('tools.changes.none'))}</div>`;

  return `<div class="page-head"><div class="grow"><h1><span>${esc(t('nav.tools'))}</span></h1><p>${esc(t('tools.intro'))}</p></div></div>
    <div class="two">
      <div class="card"><div class="card-head"><img class="anim-logo" src="img/animator.svg" alt=""><div class="grow"><h2>${esc(t('tools.anim.title'))}</h2>
        <p>${esc(t('tools.anim.text'))}</p></div></div>
        <div class="actions"><button class="btn primary" data-act="open" data-what="animator"${anim.installed === false ? ' disabled' : ''}>${ic('arrow')}${esc(t('tools.anim.open'))}</button></div>
        ${anim.installed === false ? `<div class="note warn">${ic('warn')}<span>${esc(t('tools.anim.missing'))}</span></div>` : ''}
        <div class="note">${ic('bolt')}<div>${h('tools.anim.studio')}
          <div style="margin-top:10px"><button class="btn small soft" data-act="play" data-target="studio"${canPlay() ? '' : ' disabled'}>${ic('play')}${esc(t('tools.anim.play_studio'))}</button></div></div></div>
      </div>
      <div class="card"><div class="card-head"><div class="ic green"><svg viewBox="0 0 24 36" style="width:17px;height:26px" aria-hidden="true"><use href="#i-bob"/></svg></div>
        <div class="grow"><h2>${esc(t('app.game'))}</h2><p>${esc(t('tools.game.text'))}</p></div></div>
        ${gameFound() && where ? `<div class="game-where"><div class="grow"><small>${esc(t(g.saved ? 'tools.game.picked' : 'tools.game.auto'))}</small><span class="path">${esc(where)}</span></div>
            <button class="btn small" data-act="find-game"${busy() ? ' disabled' : ''}>${esc(t('tools.game.change'))}</button></div>`
          : gameFound() ? `<div class="game-where"><div class="grow muted">${esc(t('tools.game.auto_dot'))}</div><button class="btn small" data-act="find-game">${esc(t('tools.game.change'))}</button></div>`
          : `<div class="note warn">${ic('warn')}<span>${gameMoved(g) ? (where ? h('tools.game.moved_at', { path: raw(`<span class="path">${esc(where)}</span>`) }) : esc(g.message || t('tools.game.moved')))
              : esc(t('tools.game.notfound'))}</span></div>
            <div class="actions"><button class="btn primary" data-act="find-game">${ic('search')}${esc(t('common.locate'))}</button></div>`}
        <h3 class="sec" style="margin:20px 0 0">${esc(t('tools.folders'))}</h3>
        <div class="folders">
          ${['mods', 'saves', 'inbox', 'reports', 'quarantine'].map(w => `<button class="btn small" data-act="open" data-what="${w}" title="${esc(t('tools.folder.' + w + '.title'))}">${ic('folder')}<span>${esc(t('tools.folder.' + w))}</span></button>`).join('\n          ')}
        </div>
      </div>
    </div>
    ${care.toolsSections()}
    ${languageCard()}
    <div class="card" style="margin-top:16px"><div class="card-head"><div class="ic pink">${ic('undo')}</div><div class="grow"><h2>${esc(t('tools.changes.title'))}</h2>
      <p>${esc(t('tools.changes.text'))}</p></div>
      <button class="btn" data-act="undo"${next && !noChange ? '' : ' disabled'}>${ic('undo')}${esc(t('common.undo_last'))}</button></div>
      ${changes}</div>`;
}

// ------------------------------------------------------------------------------------------ data loading
async function refreshStatus(force = false) {
  const r = await call('status' + (force ? '?refresh=1' : ''));
  if (r.http !== 200 || !r.profile) {
    S.statusErr = r.message || t('app.status_error');
    if (r.http === 0) S.status = null;
  } else {
    const key = JSON.stringify(r);
    const changed = key !== S.statusKey;
    const first = !S.status;
    S.status = r; S.statusErr = null; S.statusKey = key;
    renderTop();
    if (first) { render(); loadForPage(); return; }
    if (!changed) return;
  }
  renderTop();
  render();
}

async function ensureSaves(force = false) {
  if (S.savesLoading || (S.saves && !force)) return;
  S.savesLoading = true;
  if (S.page === 'saves') render();
  const r = await call('saves' + (force ? '?refresh=1' : ''));
  S.savesLoading = false;
  S.saves = r.busy ? null : r.http === 200 ? r : { ok: false, message: r.message };
  if (['saves', 'home'].includes(S.page)) render();
}

async function ensureInbox(force = false) {
  if (S.inboxLoading || (S.inbox && !force)) return;
  S.inboxLoading = true;
  if (force) { S.inbox = null; if (S.page === 'library') render(); }
  const r = await call('inbox' + (force ? '?refresh=1' : ''));
  S.inboxLoading = false;
  S.inbox = r.busy ? null : r;
  if (S.page === 'library') render();
}

async function ensureGraphics(force = false) {
  if (S.graphicsLoading || (S.graphics && !force)) return;
  S.graphicsLoading = true;
  if (S.page === 'performance') render();
  const r = await call('graphics' + (force ? '?refresh=1' : ''));
  S.graphicsLoading = false;
  S.graphics = r.busy ? null : r;
  if (S.page === 'performance') render();
}

// ------------------------------------------------------------------------------------------ tasks and the progress window
function playTitle(target) {
  if (target === 'fast') return t('task.play.fast');
  if (target === 'full') return t('task.play.full');
  if (target === 'studio') return t('task.play.studio');
  const s = saveBySlot(String(target || '').replace(/^save:/, ''));
  return s ? t('task.play.save', { name: s.name }) : t('task.play.a_save');
}
const TITLES = {
  play: a => playTitle(a.target), prepare: () => t('task.prepare'), undo_last: () => t('task.undo'),
  inbox: a => t(a.apply ? 'task.inbox.apply' : 'task.inbox.look'),
  cleanup_plan: () => t('task.cleanup_plan'), cleanup_apply: () => t('task.cleanup_apply'),
  graphics_tune: a => t(a.apply ? 'task.gfx.apply' : 'task.gfx.look'),
  graphics_restore: () => t('task.gfx.restore'), report: () => t('task.report'),
};
const DONE = {
  play: r => t(r.launched ? 'done.play' : 'done.ready'), prepare: () => t('done.ready'), undo_last: () => t('done.undo'),
  inbox: () => t('done.inbox'), cleanup_plan: () => t('done.cleanup_plan'), cleanup_apply: () => t('done.cleanup_apply'),
  graphics_tune: () => t('done.gfx'), graphics_restore: () => t('done.gfx_restore'), report: () => t('done.report'),
};
const working = () => t('task.working');

async function runTask(action, args = {}, opts = {}) {
  if (busy()) { toast(t('task.busy'), 'err'); return null; }
  const r = await call('task', { action, args });
  if (r.http === 409) {
    toast(r.message || t('task.busy'), 'err');
    if (r.task && !S.taskId) watchTask(r.task, {});
    return null;
  }
  if (!r.ok || !r.task) { toast(r.message || t('common.failed'), 'err'); return null; }
  return watchTask(r.task, Object.assign({ action, args }, opts));
}

async function watchTask(id, opts) {
  S.taskId = id;
  renderTop(); render();
  const ov = Overlay(opts.action ? (TITLES[opts.action] || working)(opts.args || {}) : working());
  let view = null, misses = 0;
  for (;;) {
    const v = await call('task/' + encodeURIComponent(id));
    if (v.http === 200 && v.state) {
      misses = 0;
      view = v;
      if (!opts.action && v.action) { opts.action = v.action; opts.args = v.args || {}; ov.title((TITLES[v.action] || working)(opts.args)); }
      ov.update(v);
      if (v.state !== 'running') break;
    } else if (v.http === 404 || ++misses > 20) {
      view = { state: 'failed', result: { ok: false, message: t(v.http === 404 ? 'task.restarted' : 'task.stopped') } };
      break;
    }
    await sleep(450);
  }
  S.taskId = null;
  const res = view.result || {};
  // what changed: forget what the pages show, then ask again
  if (opts.action !== 'cleanup_plan' && opts.action !== 'report') { S.saves = null; S.graphics = null; S.inbox = null; }
  S.savesLoading = S.graphicsLoading = S.inboxLoading = false;
  if (opts.action !== 'cleanup_plan' && opts.action !== 'report') care.afterTask();
  if (opts.action === 'cleanup_apply' && res.ok) S.plan = null;
  refreshStatus(true).then(loadForPage);
  if (opts.action === 'cleanup_plan' && res.ok) {
    S.plan = res;
    ov.close();
    render();
    confirmCleanup();
    return view;
  }
  if (opts.action === 'report' && res.ok) {
    // the report was made either way; only say so plainly when it didn't open by itself
    const o = await call('open', { what: 'report_html' });
    ov.finish(view, { ok: true, message: o.ok ? (o.message || t('task.report.open')) : t('task.report.not_opened') });
    return view;
  }
  ov.finish(view);
  return view;
}

// a progress step's name when the engine gives no sentence for it
const stepWords = step => I.has('step.' + step) ? t('step.' + step) : words(step);

function Overlay(title) {
  const root = $('#overlay-root');
  root.innerHTML = `<div class="overlay"><div class="task" role="dialog" aria-modal="true" aria-live="polite">
    <div class="top"><div class="big"><div class="spinner"></div></div><div class="grow"><h2></h2><p class="now">${esc(t('task.starting'))}</p></div></div>
    <div class="bar-track indet"><i style="width:0"></i></div>
    <div class="list"></div><div class="msg"></div><footer class="hidden"></footer></div></div>`;
  const el = $('.task', root), rows = new Map();
  $('h2', el).textContent = title;
  let finished = false;
  const onKey = e => { if (finished && (e.key === 'Escape' || e.key === 'Enter')) { e.preventDefault(); close(); } };
  document.addEventListener('keydown', onKey);
  function close() { document.removeEventListener('keydown', onKey); root.innerHTML = ''; render(); }
  function row(key) {
    let r = rows.get(key);
    if (!r) {
      r = document.createElement('div');
      r.className = 'row';
      r.innerHTML = '<span class="st"></span><span class="tx"></span>';
      $('.list', el).appendChild(r);
      rows.set(key, r);
    }
    return r;
  }
  function mark(r, cls) {
    if (r.dataset.cls === cls) return;
    r.dataset.cls = cls;
    r.className = 'row ' + cls;
    $('.st', r).innerHTML = cls === 'done' ? ic('check') : cls === 'now' ? '<div class="spinner sm"></div>' : cls === 'fail' ? ic('x') : cls === 'warn' ? ic('warn') : '<i class="dot"></i>';
  }
  function update(v) {
    const evs = v.progress || [];
    let lastKey = null;
    for (const ev of evs) {
      const key = ev.step || ev.message;
      if (!key) continue;
      const r = row(key);
      if (ev.message) $('.tx', r).textContent = ev.message;
      else if (!$('.tx', r).textContent) $('.tx', r).textContent = stepWords(ev.step);
      lastKey = key;
    }
    rows.forEach((r, k) => mark(r, k === lastKey && v.state === 'running' ? 'now' : 'done'));
    const last = evs[evs.length - 1];
    if (last && last.message) $('.now', el).textContent = last.message;
    const bar = $('.bar-track', el), fill = $('i', bar);
    const frac = last && isNum(last.fraction) ? Number(last.fraction) : null;
    bar.classList.toggle('indet', frac === null && v.state === 'running');
    if (frac !== null) fill.style.width = Math.max(3, frac * 100).toFixed(1) + '%';
    const list = $('.list', el);
    list.scrollTop = list.scrollHeight;
  }
  function finish(view, override) {
    finished = true;
    const res = override || (view && view.result) || {};
    const ok = !!res.ok && view.state !== 'failed';
    const action = view.action;
    $('.big', el).className = 'big ' + (ok ? 'ok' : 'bad');
    $('.big', el).innerHTML = ic(ok ? 'check' : 'x');
    $('h2', el).textContent = ok ? (DONE[action] || (() => t('task.done')))(res) : t('task.failed');
    $('.now', el).textContent = ok ? (res.message || t('task.all_done')) : '';
    const bar = $('.bar-track', el);
    bar.classList.remove('indet');
    if (ok) $('i', bar).style.width = '100%'; else bar.classList.add('hidden');
    const steps = ((view.result || {}).steps || []).filter(x => x && x.message);
    // a step that is fine but needs attention: the engine marks it (warn); older engines only for memory warnings
    const isWarn = x => x.ok !== false && ('warn' in x ? !!x.warn : x.step === 'memory' && !/fine\.?$/i.test(en(x, 'message')));
    if (steps.length) {
      // what really happened, in the engine's words, instead of the running commentary
      rows.clear();
      $('.list', el).innerHTML = '';
      steps.forEach((x, i) => { const r = row('s' + i); $('.tx', r).textContent = x.message; mark(r, x.ok === false ? 'fail' : isWarn(x) ? 'warn' : 'done'); });
    } else {
      const failKey = [...rows.keys()].pop();
      rows.forEach((r, k) => mark(r, !ok && k === failKey ? 'fail' : 'done'));
    }
    let msg = '';
    if (!ok) msg += `<div class="note err">${ic('warn')}<span>${esc(res.message || t('task.went_wrong'))}</span></div>`;
    steps.filter(isWarn).forEach(x => { msg += `<div class="note warn">${ic('warn')}<span>${esc(x.message)}</span></div>`; });
    $('.msg', el).innerHTML = msg;
    const foot = $('footer', el);
    foot.classList.remove('hidden');
    const hint = ok && action === 'play' && res.launched ? t('task.keeps_running') : '';
    foot.innerHTML = `${hint ? `<span class="hint">${esc(hint)}</span>` : ''}<button class="btn primary" data-close>${esc(t(ok ? 'common.ok' : 'common.close'))}</button>`;
    $('[data-close]', foot).onclick = close;
    $('[data-close]', foot).focus();
  }
  return { update, finish, close, title: x => { $('h2', el).textContent = x; } };
}

// ------------------------------------------------------------------------------------------ dialogs
function modal(html, { wide = false, onKey } = {}) {
  const root = $('#modal-root');
  root.innerHTML = `<div class="backdrop"><div class="modal${wide ? ' wide' : ''}" role="dialog" aria-modal="true" tabindex="-1">${html}</div></div>`;
  const el = $('.modal', root);
  const key = e => { if (e.key === 'Escape') { e.preventDefault(); close(); } else if (onKey) onKey(e); };
  document.addEventListener('keydown', key);
  let closed = false;
  function close() { if (closed) return; closed = true; document.removeEventListener('keydown', key); root.innerHTML = ''; if (el._onclose) el._onclose(); }
  $('.backdrop', root).addEventListener('mousedown', e => { if (e.target === e.currentTarget) close(); });
  el.focus();
  return { el, close };
}

function confirmBox({ title, text, what = '', ok = t('common.ok'), cancel = t('common.cancel'), danger = false }) {
  return new Promise(resolve => {
    const m = modal(`<header><div class="ic ${danger ? 'warn' : ''}">${ic(danger ? 'warn' : 'info')}</div><div class="grow"><h2>${esc(title)}</h2><p>${text}</p></div></header>
      ${what ? `<div class="body">${what}</div>` : ''}
      <footer><button class="btn ghost" data-no>${esc(cancel)}</button><button class="btn ${danger ? 'danger' : 'primary'}" data-yes>${esc(ok)}</button></footer>`);
    let answer = false;
    m.el._onclose = () => resolve(answer);
    $('[data-no]', m.el).onclick = () => m.close();
    $('[data-yes]', m.el).onclick = () => { answer = true; m.close(); };
    $(danger ? '[data-no]' : '[data-yes]', m.el).focus();
  });
}

async function confirmCleanup() {
  const p = S.plan;
  if (!p || !p.ok) return;
  if (!(p.copies > 0)) {
    await confirmBox({ title: t('dlg.cleanup.none_title'), text: esc(t('dlg.cleanup.none_text')), ok: t('common.ok'), cancel: t('common.close') });
    return;
  }
  const yes = await confirmBox({
    title: t('dlg.cleanup.title', { size: planSize(p) }),
    text: esc(t('dlg.cleanup.text', { n: Number(p.copies) })),
    what: `<div class="confirm-what"><b>${esc(t('dlg.cleanup.undo_title'))}</b><span>${h('dlg.cleanup.undo_text')}</span></div>`,
    ok: t('lib.cleanup.go', { size: planSize(p) }), cancel: t('common.not_now'),
  });
  if (yes) runTask('cleanup_apply');
}

async function confirmUndo() {
  const next = nextUndo(st().journals || []);
  if (!next) return;
  const d = describeChange(next);
  const yes = await confirmBox({
    title: t('dlg.undo.title'), danger: true,
    text: esc(t('dlg.undo.text')),
    what: `<div class="confirm-what"><b>${esc(d.title)}</b><span>${esc(d.title !== d.label ? d.label + ' · ' : '')}${esc(ago(next.when))}</span></div>`,
    ok: t('dlg.undo.ok'), cancel: t('dlg.undo.cancel'),
  });
  if (yes) runTask('undo_last');
}

async function confirmRestore() {
  const yes = await confirmBox({
    title: t('dlg.restore.title'), danger: true,
    text: esc(t('dlg.restore.text')),
    ok: t('dlg.restore.ok'), cancel: t('dlg.restore.cancel'),
  });
  if (yes) runTask('graphics_restore', { apply: true });
}

// "Find The Sims 4": the Hub's own folder browser
function openFinder(startPath = '') {
  const F = { data: null, hist: [], loading: true, err: '', saving: '', saved: '', sugs: null };
  const m = modal(`<header><div class="ic green"><svg viewBox="0 0 24 36" style="width:17px;height:26px" aria-hidden="true"><use href="#i-bob"/></svg></div>
      <div class="grow"><h2>${esc(t('finder.title'))}</h2><p>${esc(t('finder.text'))}</p></div>
      <button class="icon-btn" data-f="close" title="${esc(t('common.close'))}">${ic('x')}</button></header>
    <div class="body finder"></div>
    <footer><span class="hint">${esc(t('finder.hint'))}</span><button class="btn ghost" data-f="close">${esc(t('common.cancel'))}</button></footer>`, { wide: true });
  const body = $('.body', m.el);
  const norm = p => /^[A-Za-z]:$/.test(p || '') ? p + '\\' : (p || '');

  async function go(path, push = true) {
    if (push && F.data && F.data.ok !== false) F.hist.push(F.data.path || '');
    F.loading = true; F.err = ''; draw();
    const r = await call('browse' + (path ? '?path=' + encodeURIComponent(norm(path)) : ''));
    F.loading = false;
    if (r.http === 200 && r.ok !== false) {
      F.data = r;
      if (r.suggestions && (r.suggestions.length || !F.sugs)) F.sugs = r.suggestions;
    } else {
      F.err = r.message || t('finder.cant_open');
      if (!F.data) F.data = { ok: true, path: '', drives: r.drives || [], entries: [] };
    }
    draw();
  }
  async function pick(path) {
    F.saving = path; F.err = ''; draw();
    const r = await call('game_path', { path });
    if (r.ok) {
      F.saved = r.message || t('finder.saved');
      draw();
      await refreshStatus(true);
      setTimeout(m.close, 1500);
    } else {
      F.saving = ''; F.err = r.message || t('finder.not_game'); draw();
    }
  }
  function crumbs(path) {
    const out = [];
    if (!path) return out;
    const parts = path.replace(/\\+$/, '').split('\\');
    let acc = '';
    parts.forEach((p, i) => { acc = i === 0 ? p + '\\' : (acc.endsWith('\\') ? acc : acc + '\\') + p; out.push({ label: p, path: acc }); });
    return out;
  }
  const pickBtn = (path, label) => `<button class="btn primary small" data-f="pick" data-path="${esc(path)}"${F.saving ? ' disabled' : ''}>${esc(F.saving === path ? t('finder.saving') : label)}</button>`;
  function draw() {
    if (F.saved) {
      body.innerHTML = `<div class="saved"><div class="big">${ic('check')}</div><b>${esc(F.saved)}</b><span class="muted">${esc(t('finder.all_set'))}</span></div>`;
      return;
    }
    const d = F.data || {};
    const path = d.path || '';
    let out = '';
    const sugs = F.sugs || [];
    if (sugs.length) {
      out += `<div class="lbl" style="margin-top:4px">${esc(t('finder.found'))}</div><div class="sug">${sugs.map(s => {
        const p = s.path || gamePath(s);
        return `<div class="sug-card"><svg class="b" viewBox="0 0 24 36" aria-hidden="true"><use href="#i-bob"/></svg><div class="grow">
          <b>${esc(t('app.game'))}</b><span class="path">${esc(p)}</span>${s.hint || s.source ? `<small>${esc(s.hint || s.source)}</small>` : ''}</div>
          ${pickBtn(p, t('finder.use'))}</div>`;
      }).join('')}</div>`;
    }
    const trail = crumbs(path);
    const shown = trail.length > 4 ? [trail[0], null, ...trail.slice(-2)] : trail;
    out += `<div class="lbl">${esc(t(sugs.length ? 'finder.or_look' : 'finder.look'))}</div>
      <div class="crumbs"><button class="icon-btn" data-f="back" title="${esc(t('common.back'))}"${F.hist.length ? '' : ' disabled'}>${ic('back')}</button>
      <button class="icon-btn" data-f="up" title="${esc(t('finder.up'))}"${path ? '' : ' disabled'}>${ic('up')}</button>
      <div class="trail"><button data-f="go" data-path="" class="${path ? '' : 'cur'}">${ic('pc')} ${esc(t('finder.this_pc'))}</button>
      ${shown.map((c, i) => c === null ? `${ic('chev')}<span class="ell">…</span>` : `${ic('chev')}<button data-f="go" data-path="${esc(c.path)}" class="${i === shown.length - 1 ? 'cur' : ''}" title="${esc(c.path)}">${esc(c.label)}</button>`).join('')}</div></div>`;
    if (F.err) out += `<div class="note err">${ic('warn')}<span>${esc(F.err)}</span></div>`;
    if (F.loading) out += `<div class="state"><div class="spinner sm"></div>${esc(t('finder.opening'))}</div>`;
    else if (!path) {
      const drives = d.drives || [];
      out += drives.length ? `<div class="drives">${drives.map(x => `<button class="drive" data-f="go" data-path="${esc(norm(x.path || x.name))}">${ic('drive')}<div class="grow">
          <b>${esc(x.label ? `${x.label} (${String(x.name).replace(/\\$/, '')})` : x.name)}</b><span>${isNum(x.free_gb) ? esc(t('finder.free', { gb: gb(x.free_gb) })) : ''}</span></div></button>`).join('')}</div>`
        : `<div class="state">${esc(t('finder.no_drives'))}</div>`;
    } else {
      const entries = d.entries || [];
      const names = new Set(entries.map(e => String(e.name).toLowerCase()));
      const here = d.is_game || (names.has('game') && names.has('data'));
      if (here) {
        out += `<div class="sug-card" style="margin-top:10px"><svg class="b" viewBox="0 0 24 36" aria-hidden="true"><use href="#i-bob"/></svg><div class="grow">
          <b>${esc(t('finder.is_game'))}</b><span class="path">${esc(path)}</span></div>
          ${pickBtn(path, t('finder.select'))}</div>`;
      }
      out += entries.length ? `<div class="folder-list">${entries.map(e => `<div class="frow${e.is_game ? ' game' : ''}">
          <button class="row-btn" data-f="go" data-path="${esc(e.path)}" title="${esc(e.path)}">${ic('folder', 'f')}<span class="name">${esc(e.name)}</span>
          ${e.hint && !e.is_game ? `<span class="tag">${esc(e.hint)}</span>` : ''}${e.is_game ? '' : ic('chev', 'c')}</button>
          ${e.is_game ? `<span class="gbadge"><svg viewBox="0 0 24 36" aria-hidden="true"><use href="#i-bob"/></svg>${esc(t('app.game'))}</span>
            ${pickBtn(e.path, t('finder.select'))}` : ''}
        </div>`).join('')}</div>`
        : `<div class="state">${esc(t('finder.empty'))}</div>`;
    }
    body.innerHTML = out;
  }
  m.el.addEventListener('click', e => {
    const b = e.target.closest('[data-f]');
    if (!b || b.disabled) return;
    const f = b.dataset.f;
    if (f === 'close') m.close();
    else if (f === 'go') go(b.dataset.path);
    else if (f === 'pick') pick(b.dataset.path);
    else if (f === 'back' && F.hist.length) go(F.hist.pop(), false);
    else if (f === 'up' && F.data) go(F.data.parent || '');
  });
  m.el._onclose = () => render();
  draw();
  (async () => {
    await go('', false);                      // This PC first, so Back from a start folder leads there
    if (startPath) await go(startPath);
  })();
  return m;
}

// ------------------------------------------------------------------------------------------ toasts
function toast(text, kind = '') {
  if (!text) return;
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = text;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

async function openThing(what) {
  const r = await call('open', { what });
  toast(r.message || t(r.ok ? 'common.opened' : 'common.cant_open'), r.ok ? 'ok' : 'err');
}

// ------------------------------------------------------------------------------------------ the language
// First run: the browser's language (in the Hub window that is the Windows language), else the language Windows
// reports to the server, else English - and the choice is kept in the Hub's settings (data\hub_settings.json).
async function startLanguage() {
  const r = await call('settings');
  let code = I.supported(r.language) ? r.language : null;
  if (!code) {
    code = I.match(navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language])
      || I.match(r.system_language) || I.DEFAULT;
    if (r.http === 200) call('settings', { language: code, auto: true });
  }
  try { await I.load(code); } catch { I.use(I.DEFAULT, {}, {}); }
  applyStatic();
}

async function changeLanguage(code) {
  if (!I.supported(code) || code === I.lang()) return;
  const r = await call('settings', { language: code });
  if (!r.ok) { toast(r.message || t('common.failed'), 'err'); return; }
  try { await I.load(code); } catch { toast(t('common.failed'), 'err'); return; }
  applyStatic();
  // everything the server said was in the old language: ask again
  S.saves = S.graphics = S.inbox = null;
  S.savesLoading = S.graphicsLoading = S.inboxLoading = false;
  ccForget();
  care.forget();
  route();
  await refreshStatus(true);
  renderTop();
  render();
  toast(t('tools.lang.saved'), 'ok');
}

document.addEventListener('change', e => {
  if (e.target && e.target.id === 'lang-pick') changeLanguage(e.target.value);
});

// ------------------------------------------------------------------------------------------ clicks
const ACTS = {
  refresh: async btn => {
    btn.classList.add('spin');
    await refreshStatus(true);
    if (S.page === 'saves') await ensureSaves(true);
    if (S.page === 'library') await ensureInbox(true);
    if (S.page === 'performance') await ensureGraphics(true);
    await care.load(S.page, true);
    btn.classList.remove('spin');
  },
  play: btn => runTask('play', { target: btn.dataset.target }),
  'gfx-fix': () => runTask('graphics_tune', { apply: true }),
  'gfx-restore': () => confirmRestore(),
  'saves-refresh': () => ensureSaves(true),
  'inbox-refresh': () => ensureInbox(true),
  'inbox-apply': () => runTask('inbox', { apply: true }),
  'cleanup-plan': () => runTask('cleanup_plan'),
  'cleanup-confirm': () => confirmCleanup(),
  report: () => runTask('report'),
  undo: () => confirmUndo(),
  open: btn => openThing(btn.dataset.what),
  'find-game': () => openFinder(),
};

document.addEventListener('click', e => {
  const b = e.target.closest('[data-act]');
  if (!b || b.disabled) return;
  const fn = ACTS[b.dataset.act];
  if (fn) { e.preventDefault(); fn(b); }
});

// ------------------------------------------------------------------------------------------ CC browser (Library) + a save's CC (Saves)
// docs/ccbrowser.md. The browser is one element that lives across page re-draws (render() puts it back into
// #cc-slot), so the search box keeps its text and focus while the status refreshes. Only one page of cards
// (60) is ever in the page; pictures load lazily from /api/cc/thumb (cached by the browser).
const CC_ICONS = {
  hair: '<path d="M5 20c0-7 1-12.5 7-12.5S19 13 19 20M8.5 20c0-3.5.8-6.2 3.5-7.7 2.7 1.5 3.5 4.2 3.5 7.7"/>',
  hat: '<path d="M3 17.5h18M6 17.5c0-5.5 2.6-9.5 6-9.5s6 4 6 9.5"/>',
  top: '<path d="M8.5 4 4 6.5l1.8 4 2.2-1V20h8V9.5l2.2 1 1.8-4L15.5 4a3.5 3.5 0 0 1-7 0z"/>',
  bottom: '<path d="M7 3.5h10l1 17h-4.2L12 10l-1.8 10.5H6z"/>',
  fullbody: '<path d="M9.5 3.5h5l-1 5 4.5 12h-12l4.5-12z"/>',
  shoes: '<path d="M3 16.5h18v2.5H3zM3 16.5c0-4 .8-7.5 2.8-8.5l4 3c2 1.2 6 2.2 9 3 1.2.4 2.2 1.3 2.2 2.5"/>',
  accessory: '<circle cx="12" cy="14.5" r="5.5"/><path d="M9.3 4.5h5.4l1.6 2.5L12 10 7.7 7z"/>',
  makeup: '<path d="M9 21h6v-8H9zM10 13V7.5l4-3.5v9"/>',
  eyes: '<path d="M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  skin: '<path d="M12 3c3 4.5 6 7.5 6 11a6 6 0 0 1-12 0c0-3.5 3-6.5 6-11z"/>',
  cas_other: '<path d="M12 3c.6 4.5 2.5 6.4 7 7-4.5.6-6.4 2.5-7 7-.6-4.5-2.5-6.4-7-7 4.5-.6 6.4-2.5 7-7z"/>',
  pets: '<circle cx="6.5" cy="10" r="1.8"/><circle cx="10" cy="6" r="1.8"/><circle cx="14" cy="6" r="1.8"/><circle cx="17.5" cy="10" r="1.8"/><path d="M12 11.5c-3 0-6 4-6 6.5 0 1.5 1.2 2.4 3 2l3-1 3 1c1.8.4 3-.5 3-2 0-2.5-3-6.5-6-6.5z"/>',
  sliders: '<path d="M4 7h16M4 12h16M4 17h16"/><circle cx="9" cy="7" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="8" cy="17" r="2"/>',
  buildbuy: '<path d="M5 11V8a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v3M3 12a2 2 0 0 1 4 0v2h10v-2a2 2 0 0 1 4 0v5H3zM5.5 17v2.5M18.5 17v2.5"/>',
  walls: '<path d="M3 5h18v14H3zM3 9.7h18M3 14.3h18M9 5v4.7M15 5v4.7M6 9.7v4.6M12 9.7v4.6M18 9.7v4.6M9 14.3V19M15 14.3V19"/>',
  poses: '<circle cx="12" cy="4.8" r="2"/><path d="M12 7v7m0 0-3 6.5m3-6.5 3 6.5M5.5 10.5l6.5-1.5 6-2.5"/>',
  gameplay: '<path d="M7 8h10a4 4 0 0 1 4 4v2.5a2.5 2.5 0 0 1-4.5 1.5L15 14H9l-1.5 2a2.5 2.5 0 0 1-4.5-1.5V12a4 4 0 0 1 4-4zM8 10.5v3M6.5 12h3"/>',
  script: '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><path d="m7 10 3 2.5L7 15M12.5 15.5H17"/>',
  other: '<path d="M6 3h8l4 4v14H6zM14 3v4h4"/>',
  all: '<path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/>',
  hanger: '<path d="M12 7.5a2.2 2.2 0 1 1 2.2-2.2M12 7.5v1.8L3 16.5h18l-9-7.2"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.6 5.2 3.6 8.5s-1.2 6.1-3.6 8.5c-2.4-2.4-3.6-5.2-3.6-8.5S9.6 5.9 12 3.5z"/>',
};
(() => {
  const box = document.createElement('div');
  box.innerHTML = `<svg width="0" height="0" style="position:absolute" aria-hidden="true">${Object.entries(CC_ICONS).map(([k, d]) =>
    `<symbol id="i-cc-${k}" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${d}</g></symbol>`).join('')}
    <symbol id="i-globe" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${CC_ICONS.globe}</g></symbol></svg>`;
  document.body.appendChild(box.firstChild);
})();
const ccIc = (cat, cls = '') => ic('cc-' + (CC_ICONS[cat] ? cat : 'other'), cls);
const CC_PER = 60;
const CC_SORTS = ['name', 'newest', 'biggest', 'folder'];
const CCB = {
  el: null, data: null, loading: false, err: '', f: { category: '', folder: '', creator: '', q: '', used: '', flag: '', sort: 'name' },
  page: 0, facets: null, sel: new Set(), scan: null, req: 0, qTimer: null,
};
// a new language: the browser is built again (its words) and asks the server again (the category names)
function ccForget() {
  if (CCB.el) CCB.el.remove();
  CCB.el = null; CCB.data = null; CCB.facets = null; CCB.err = '';
}

// everything that needs a hook in the rest of the app
AFTER_RENDER.push(() => { if (S.page === 'library') ccMount(); });
Object.assign(TITLES, { cc_scan: () => t('task.cc_scan'), cc_set_aside: () => t('task.cc_set_aside') });
Object.assign(DONE, { cc_scan: () => t('done.cc_scan'), cc_set_aside: () => t('done.cc_set_aside') });
KIND.setaside = ['kind.setaside', 'folder'];
Object.assign(ACTS, { 'save-cc': btn => ccSaveModal(btn.dataset.slot) });

// the Library page's spot for the browser (renderLibrary puts it right under the page title)
const ccSlot = () => '<div id="cc-slot"></div>';

function ccMount() {
  const slot = $('#cc-slot');
  if (!slot) return;
  if (!CCB.el) ccBuild();
  slot.replaceWith(CCB.el);
  ccDrawHead();
  if (!CCB.data && !CCB.loading) ccLoad(true);
}

function ccBuild() {
  const el = document.createElement('section');
  el.className = 'card cc';
  el.id = 'cc-browser';
  el.innerHTML = `<div class="card-head"><div class="ic">${ccIc('hanger')}</div><div class="grow"><h2>${esc(t('cc.title'))}</h2>
      <p>${esc(t('cc.text'))}</p></div>
      <div class="cc-head-right"></div></div>
    <div class="cc-progress hidden"><div class="spinner sm"></div><div class="grow"><b>${esc(t('cc.sorting'))}</b><span class="cc-ptext"></span>
      <div class="bar-track indet"><i style="width:0"></i></div></div></div>
    <div class="cc-cats" role="tablist" aria-label="${esc(t('cc.aria.cats'))}"></div>
    <div class="cc-tools">
      <label class="cc-search">${ic('search')}<input id="cc-q" type="search" placeholder="${esc(t('cc.search'))}" autocomplete="off" spellcheck="false" aria-label="${esc(t('cc.aria.search'))}"></label>
      <select data-cc-f="folder" aria-label="${esc(t('cc.aria.folder'))}"><option value="">${esc(t('cc.all_folders'))}</option></select>
      <select data-cc-f="creator" aria-label="${esc(t('cc.aria.creator'))}"><option value="">${esc(t('cc.all_creators'))}</option></select>
      <select data-cc-f="used" aria-label="${esc(t('cc.aria.used'))}"><option value="">${esc(t('cc.used.any'))}</option><option value="used">${esc(t('cc.used.used'))}</option><option value="unused">${esc(t('cc.used.unused'))}</option></select>
      <select data-cc-f="flag" aria-label="${esc(t('cc.aria.flag'))}"><option value="">${esc(t('cc.flag.any'))}</option><option value="duplicate">${esc(t('cc.flag.dup'))}</option><option value="broken">${esc(t('cc.flag.broken'))}</option></select>
      <select data-cc-f="sort" aria-label="${esc(t('cc.aria.sort'))}">${CC_SORTS.map(k => `<option value="${k}">${esc(t('cc.sort.' + k))}</option>`).join('')}</select>
    </div>
    <div class="cc-bar"><span class="cc-count"></span><span class="cc-selbar"></span></div>
    <div class="cc-grid" aria-live="polite"></div>
    <div class="cc-pager"></div>`;
  CCB.el = el;
  $('#cc-q', el).value = CCB.f.q;
  $('#cc-q', el).addEventListener('input', e => {
    clearTimeout(CCB.qTimer);
    CCB.qTimer = setTimeout(() => { CCB.f.q = e.target.value.trim(); CCB.page = 0; ccLoad(); }, 260);
  });
  el.addEventListener('change', e => {
    const s = e.target.closest('[data-cc-f]');
    if (s) { CCB.f[s.dataset.ccF] = s.value; CCB.page = 0; ccLoad(); return; }
    const box = e.target.closest('[data-cc-sel]');
    if (box) {
      const id = +box.dataset.ccSel;
      box.checked ? CCB.sel.add(id) : CCB.sel.delete(id);
      box.closest('.cc-card').classList.toggle('selected', box.checked);
      ccDrawSel();
    }
  });
  el.addEventListener('click', e => {
    if (e.target.closest('.cc-check')) return;
    const b = e.target.closest('[data-cc]');
    if (b && !b.disabled) {
      const what = b.dataset.cc;
      if (what === 'cat') { CCB.f.category = b.dataset.key; CCB.page = 0; ccLoad(); }
      else if (what === 'page') { CCB.page = Math.max(0, +b.dataset.page); ccLoad(); CCB.el.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
      else if (what === 'scan') ccScan();
      else if (what === 'clear') ccClearFilters();
      else if (what === 'aside') ccConfirmAside([...CCB.sel]);
      else if (what === 'unselect') { CCB.sel.clear(); ccDraw(); }
      return;
    }
    const card = e.target.closest('.cc-card');
    if (card) ccDetails(+card.dataset.id);
  });
  el.addEventListener('keydown', e => {
    const card = e.target.closest('.cc-card');
    if (card && (e.key === 'Enter' || e.key === ' ') && e.target === card) { e.preventDefault(); ccDetails(+card.dataset.id); }
  });
}

function ccQuery(extra = {}) {
  const p = new URLSearchParams();
  Object.entries(CCB.f).forEach(([k, v]) => { if (v) p.set(k, v); });
  p.set('offset', CCB.page * CC_PER);
  p.set('limit', CC_PER);
  Object.entries(extra).forEach(([k, v]) => p.set(k, v));
  return 'cc?' + p.toString();
}

async function ccLoad(facets = false) {
  const id = ++CCB.req;
  CCB.loading = true;
  if (CCB.el) CCB.el.classList.add('loading');
  const r = await call(ccQuery(facets || !CCB.facets ? { facets: 1 } : {}));
  if (id !== CCB.req) return;                           // a newer request is on its way
  CCB.loading = false;
  if (r.http === 200 && r.ok !== false) {
    CCB.data = r; CCB.err = '';
    if (r.folders) CCB.facets = { folders: r.folders, creators: r.creators || [] };
    const pages = Math.max(1, Math.ceil((r.total || 0) / CC_PER));
    if (CCB.page >= pages && r.total) { CCB.page = pages - 1; return ccLoad(); }
  } else {
    CCB.err = r.message || t('cc.error');
    if (!CCB.data) CCB.data = null;
  }
  if (CCB.el) CCB.el.classList.remove('loading');
  ccDraw();
}

function ccClearFilters() {
  Object.assign(CCB.f, { category: '', folder: '', creator: '', q: '', used: '', flag: '' });
  if (CCB.el) $('#cc-q', CCB.el).value = '';
  CCB.page = 0;
  ccLoad();
}

function ccDrawHead() {
  if (!CCB.el) return;
  const d = CCB.data, idx = (d && d.index) || {};
  const off = busy() ? ' disabled' : '';
  $('.cc-head-right', CCB.el).innerHTML = idx.state === 'ready'
    ? `<span class="cc-when">${idx.when ? esc(t('cc.sorted_ago', { ago: ago(idx.when) })) : ''}</span><button class="btn small" data-cc="scan"${off}>${ic('refresh')}${esc(t('common.look_again'))}</button>`
    : '';
  const p = $('.cc-progress', CCB.el);
  p.classList.toggle('hidden', !CCB.scan);
  if (CCB.scan) {
    $('.cc-ptext', p).textContent = CCB.scan.text || '';
    const bar = $('.bar-track', p), fill = $('i', bar), f = CCB.scan.frac;
    bar.classList.toggle('indet', f === null);
    if (f !== null) fill.style.width = Math.max(3, f * 100).toFixed(1) + '%';
  }
  $$('[data-cc="aside"]', CCB.el).forEach(b => { b.disabled = busy() || gameRunning(); });
  $$('[data-cc="scan"]', CCB.el).forEach(b => { b.disabled = busy(); });
}

function ccDraw() {
  if (!CCB.el) return;
  ccDrawHead();
  const d = CCB.data, el = CCB.el;
  const idx = (d && d.index) || {};
  const ready = d && idx.state === 'ready';
  el.classList.toggle('empty-index', !ready);
  // categories: "All" plus every category that has something (and the one picked)
  const cats = ((d && d.categories) || []).filter(c => c.n > 0 || c.key === CCB.f.category);
  $('.cc-cats', el).innerHTML = !ready ? '' : [`<button class="cc-cat${CCB.f.category ? '' : ' on'}" data-cc="cat" data-key="" role="tab" aria-selected="${!CCB.f.category}">${ccIc('all')}<span>${esc(t('cc.all'))}</span></button>`]
    .concat(cats.map(c => `<button class="cc-cat${CCB.f.category === c.key ? ' on' : ''}" data-cc="cat" data-key="${esc(c.key)}" role="tab" aria-selected="${CCB.f.category === c.key}">${ccIc(c.key)}<span>${esc(c.label)}</span><i>${num(c.n)}</i></button>`)).join('');
  // the drop-downs keep what is picked; their lists come from the facets
  const fill = (name, list, first) => {
    const s = $(`[data-cc-f="${name}"]`, el);
    if (!s || !list) return;
    const want = CCB.f[name];
    const opts = [`<option value="">${esc(first)}</option>`].concat(list.map(x => `<option value="${esc(x.name)}">${esc(x.name)} (${num(x.n)})</option>`));
    if (want && !list.some(x => x.name === want)) opts.push(`<option value="${esc(want)}">${esc(want)}</option>`);
    s.innerHTML = opts.join('');
    s.value = want;
  };
  if (CCB.facets) { fill('folder', CCB.facets.folders, t('cc.all_folders')); fill('creator', CCB.facets.creators, t('cc.all_creators')); }
  ['used', 'flag', 'sort'].forEach(k => { const s = $(`[data-cc-f="${k}"]`, el); if (s) s.value = CCB.f[k] || (k === 'sort' ? 'name' : ''); });
  const used = $('[data-cc-f="used"]', el);
  used.disabled = !idx.used_known;
  used.title = t(idx.used_known ? 'cc.used.title' : 'cc.used.later');
  $('.cc-tools', el).classList.toggle('hidden', !ready);
  const grid = $('.cc-grid', el), pager = $('.cc-pager', el), count = $('.cc-count', el);
  if (!d) {
    grid.innerHTML = CCB.err ? `<div class="note err">${ic('warn')}<span>${esc(CCB.err)}</span></div>`
      : `<div class="saves-loading" style="padding:14px 4px 4px"><div class="spinner sm"></div>${esc(t('cc.loading'))}</div>${'<div class="skel" aria-hidden="true"></div>'.repeat(12)}`;
    pager.innerHTML = count.innerHTML = '';
    return;
  }
  if (!ready) {
    grid.innerHTML = `<div class="cc-empty"><div class="ic">${ccIc('all')}</div><div>
      <h3>${esc(t('cc.empty.title'))}</h3>
      <p>${esc(t('cc.empty.text'))}</p>
      <p class="muted">${esc(t('cc.empty.note'))}</p>
      <button class="btn primary" data-cc="scan"${busy() ? ' disabled' : ''}>${ic('search')}${esc(t('cc.sort_btn'))}</button></div></div>`;
    pager.innerHTML = count.innerHTML = '';
    ccDrawSel();
    return;
  }
  const items = d.items || [];
  const filtered = Object.entries(CCB.f).some(([k, v]) => v && k !== 'sort');
  const from = d.total ? d.offset + 1 : 0, to = d.offset + items.length;
  count.innerHTML = d.total ? `${h('cc.showing', { from: num(from), to: num(to), total: num(d.total) })}${filtered ? ` <button class="linkish" data-cc="clear">${esc(t('cc.clear'))}</button>` : ''}`
    : '';
  grid.innerHTML = items.length ? items.map(ccCard).join('')
    : `<div class="cc-none">${ic('search')}<div><b>${esc(t('cc.none.title'))}</b><span>${esc(t('cc.none.text'))}</span></div>
       ${filtered ? `<button class="btn small" data-cc="clear">${esc(t('cc.clear'))}</button>` : ''}</div>`;
  ccShowLoaded(grid);
  grid.classList.add('anim');                          // new cards come in once; re-mounting the browser doesn't replay it
  clearTimeout(CCB.animT);
  CCB.animT = setTimeout(() => grid.classList.remove('anim'), 900);
  const pages = Math.max(1, Math.ceil(d.total / CC_PER)), pg = CCB.page;
  pager.innerHTML = pages < 2 ? '' : `<button class="btn small" data-cc="page" data-page="0"${pg ? '' : ' disabled'} title="${esc(t('cc.page.first'))}">«</button>
    <button class="btn small" data-cc="page" data-page="${pg - 1}"${pg ? '' : ' disabled'}>${ic('back')}${esc(t('common.back'))}</button>
    <span>${h('cc.page.of', { n: num(pg + 1), total: num(pages) })}</span>
    <button class="btn small" data-cc="page" data-page="${pg + 1}"${pg + 1 < pages ? '' : ' disabled'}>${esc(t('cc.page.next'))}${ic('arrow')}</button>
    <button class="btn small" data-cc="page" data-page="${pages - 1}"${pg + 1 < pages ? '' : ' disabled'} title="${esc(t('cc.page.last'))}">»</button>`;
  if (CCB.err) grid.insertAdjacentHTML('afterbegin', `<div class="note err">${ic('warn')}<span>${esc(CCB.err)}</span></div>`);
  ccDrawSel();
}

const ccThumb = it => it && it.pic ? `/api/cc/thumb/${it.id}?v=${encodeURIComponent(it.pic)}` : '';

function ccCard(it) {
  const src = ccThumb(it), sel = CCB.sel.has(it.id);
  const badges = [];
  if (it.broken) badges.push(`<span class="cc-badge bad" title="${esc(it.broken)}">${esc(t('cc.badge.broken'))}</span>`);
  if (it.duplicate_of) badges.push(`<span class="cc-badge dup" title="${esc(t('cc.badge.dup_title', { file: it.duplicate_of }))}">${esc(t('cc.badge.dup'))}</span>`);
  if (it.used === false) badges.push(`<span class="cc-badge" title="${esc(t('cc.badge.unused_title'))}">${esc(t('cc.badge.unused'))}</span>`);
  if (!it.in_mods) badges.push(`<span class="cc-badge" title="${esc(t('cc.badge.away_title'))}">${esc(t('cc.badge.away'))}</span>`);
  const sub = [it.body && it.body !== it.category_label ? it.body : it.category_label, it.creator || it.folder].filter(Boolean).join(' · ');
  return `<div class="cc-card${sel ? ' selected' : ''}" data-id="${it.id}" data-cat="${esc(it.category)}" tabindex="0" title="${esc(it.rel || it.name)}">
    <div class="cc-pic">${src ? `<img src="${src}" alt="" loading="lazy" decoding="async" data-cat="${esc(it.category)}">` : `<div class="cc-ph">${ccIc(it.category)}</div>`}
      ${it.kind === 'script' ? '' : `<label class="cc-check" title="${esc(t('cc.select'))}"><input type="checkbox" data-cc-sel="${it.id}"${sel ? ' checked' : ''} aria-label="${esc(t('cc.select_name', { name: it.name }))}"></label>`}
      ${badges.length ? `<div class="cc-badges">${badges.join('')}</div>` : ''}</div>
    <div class="cc-meta"><b>${esc(it.name.replace(/\.(package|ts4script)$/i, ''))}</b><span>${esc(sub)}</span></div></div>`;
}

function ccDrawSel() {
  if (!CCB.el) return;
  const n = CCB.sel.size;
  $('.cc-selbar', CCB.el).innerHTML = !n ? '' : `<b>${esc(t('cc.sel.picked', { n }))}</b>
    <button class="btn small soft" data-cc="aside"${busy() || gameRunning() ? ' disabled' : ''}>${ic('folder')}${esc(t('cc.aside_btn'))}</button>
    <button class="btn small ghost" data-cc="unselect">${esc(t('cc.sel.clear'))}</button>`;
}

// --------------------------------------------------------------- sorting (a quiet task: progress shows in the card)
async function ccScan() {
  if (busy()) { toast(t('task.busy'), 'err'); return; }
  const r = await call('task', { action: 'cc_scan', args: {} });
  if (r.http === 409) { toast(r.message || t('task.busy'), 'err'); return; }
  if (!r.ok || !r.task) { toast(r.message || t('common.failed'), 'err'); return; }
  ccWatch(r.task);
}

async function ccWatch(id) {
  S.taskId = id;
  CCB.scan = { text: t('task.starting'), frac: null };
  renderTop(); render(); ccDrawHead();
  let view = null, misses = 0, last = Date.now();
  for (;;) {
    const v = await call('task/' + encodeURIComponent(id));
    if (v.http === 200 && v.state) {
      misses = 0; view = v;
      const ev = (v.progress || [])[v.progress.length - 1];
      if (ev) CCB.scan = { text: ev.message || '', frac: isNum(ev.fraction) ? Number(ev.fraction) : null };
      ccDrawHead();
      if (v.state !== 'running') break;
      if (Date.now() - last > 4000 && S.page === 'library') { last = Date.now(); ccLoad(true); }   // show what is sorted so far
    } else if (v.http === 404 || ++misses > 20) { view = { state: 'failed', result: { ok: false, message: t('cc.scan.stopped') } }; break; }
    await sleep(600);
  }
  S.taskId = null;
  CCB.scan = null;
  const res = (view && view.result) || {};
  toast(res.message || t(res.ok ? 'cc.scan.done' : 'cc.scan.failed'), res.ok ? 'ok' : 'err');
  CCB.facets = null;
  refreshStatus(true);
  render();
  ccLoad(true);
}

// --------------------------------------------------------------- one file
async function ccDetails(id) {
  const m = modal(`<header><div class="ic">${ccIc('hanger')}</div><div class="grow"><h2>${esc(t('cc.file'))}</h2><p>${esc(t('common.loading'))}</p></div>
    <button class="icon-btn" data-x title="${esc(t('common.close'))}">${ic('x')}</button></header><div class="body"><div class="saves-loading"><div class="spinner sm"></div>${esc(t('common.loading'))}</div></div>`, { wide: true });
  $('[data-x]', m.el).onclick = () => m.close();
  const r = await call('cc/item/' + id);
  if (!document.body.contains(m.el)) return;
  if (!r.ok) { $('.body', m.el).innerHTML = `<div class="note err">${ic('warn')}<span>${esc(r.message || t('cc.file.missing'))}</span></div>`; return; }
  const src = ccThumb(r);
  const facts = [
    [t('cc.f.category'), r.body && r.body !== r.category_label ? `${r.category_label} (${r.body})` : r.category_label],
    r.part_name ? [t('cc.f.internal'), r.part_name] : null,
    r.creator ? [t('cc.f.creator'), r.creator] : null,
    [t('cc.f.folder'), r.folder || t('cc.f.root')],
    r.cas_parts ? [t('cc.f.cas'), num(r.cas_parts)] : null,
    r.objects ? [t('cc.f.objects'), num(r.objects)] : null,
    [t('cc.f.size'), r.size_mb >= 1 ? t('unit.mb', { v: I.num(r.size_mb, 1) }) : t('unit.kb', { v: I.num(Math.max(1, Math.round(r.size_mb * 1000))) })],
    [t('cc.f.changed'), dayTime(r.modified)],
  ].filter(Boolean);
  const used = r.used === true ? `<div class="note ok">${ic('check')}<span>${h('cc.used_by', { names: r.used_by.join(', ') })}</span></div>`
    : r.used === false ? `<div class="note">${ic('info')}<span>${esc(t('cc.unused_note'))}</span></div>` : '';
  $('header p', m.el).textContent = r.name;
  $('header h2', m.el).textContent = r.name.replace(/\.(package|ts4script)$/i, '');
  $('.body', m.el).innerHTML = `<div class="cc-detail"><div class="cc-big">${src ? `<img src="${src}" alt="" data-cat="${esc(r.category)}">` : `<div class="cc-ph">${ccIc(r.category)}</div>`}</div>
    <div class="grow"><table class="cc-facts">${facts.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')}</table>
    <div class="path" style="margin-top:10px">${esc(r.path || r.rel)}</div></div></div>
    ${used}
    ${r.broken ? `<div class="note err">${ic('warn')}<span>${esc(r.broken)}</span></div>` : ''}
    ${r.duplicate_of ? `<div class="note warn">${ic('warn')}<span>${h('cc.dup_note', { file: r.duplicate_of })}</span></div>` : ''}
    ${r.in_mods ? '' : `<div class="note">${ic('info')}<span>${esc(t('cc.away_note'))}</span></div>`}`;
  const foot = document.createElement('footer');
  foot.innerHTML = `<span class="hint">${esc(t(r.kind === 'script' ? 'cc.script_hint' : 'cc.aside_hint'))}</span>
    <button class="btn" data-open>${ic('folder')}${esc(t('common.open_folder'))}</button>
    ${r.kind === 'script' ? '' : `<button class="btn soft" data-aside${busy() || gameRunning() || !r.in_mods ? ' disabled' : ''}>${ic('folder')}${esc(t('cc.aside_btn'))}</button>`}`;
  m.el.appendChild(foot);
  $('[data-open]', foot).onclick = async () => { const o = await call('cc/open', { id }); toast(o.message || t(o.ok ? 'common.opened' : 'common.cant_open'), o.ok ? 'ok' : 'err'); };
  const aside = $('[data-aside]', foot);
  if (aside) aside.onclick = () => { m.close(); ccConfirmAside([id], r.name); };
}

async function ccConfirmAside(ids, name = '') {
  if (!ids.length) return;
  const one = ids.length === 1;
  const yes = await confirmBox({
    title: one ? t('cc.aside.title_one') : t('cc.aside.title', { n: ids.length }),
    text: esc(t('cc.aside.text')),
    what: `<div class="confirm-what"><b>${esc(one && name ? name : t('cc.aside.count', { n: ids.length }))}</b><span>${h('cc.aside.undo')}</span></div>`,
    ok: t('cc.aside_btn'), cancel: t('cc.aside.cancel'),
  });
  if (!yes) return;
  const view = await runTask('cc_set_aside', { ids });
  if (view && view.result && view.result.ok) { ids.forEach(i => CCB.sel.delete(i)); }
  CCB.facets = null;
  ccLoad(true);
}

// --------------------------------------------------------------- Saves: the CC one save uses
const saveCcButton = s => `<button class="btn small ghost cc-save-btn" data-act="save-cc" data-slot="${esc(s.slot)}">${ccIc('hanger')}${esc(t(isNum(s.cc_missing) && s.cc_missing > 0 ? 'cc.view_missing' : 'cc.view'))}</button>`;
const trayCcCard = () => `<div class="card cc-tray"><div class="card-head"><div class="ic violet">${ic('users')}</div><div class="grow"><h2>${esc(t('cc.tray.title'))}</h2>
  <p>${esc(t('cc.tray.text'))}</p></div>
  <button class="btn" data-act="save-cc" data-slot="tray">${ccIc('hanger')}${esc(t('cc.view'))}</button></div></div>`;
const CC_KIND_ICON = { cas: 'top', object: 'buildbuy', look: 'skin' };

function ccSaveModal(slot) {
  const save = slot === 'tray' ? { name: t('ccs.tray') } : (saveBySlot(slot) || { name: slot });
  const X = { tab: 'files', data: null, more: 60 };
  const m = modal(`<header><div class="ic">${ccIc('hanger')}</div><div class="grow"><h2></h2><p>${esc(t('common.loading'))}</p></div>
    <button class="icon-btn" data-x title="${esc(t('common.close'))}">${ic('x')}</button></header>
    <div class="cc-tabs hidden" role="tablist"></div><div class="body"><div class="saves-loading"><div class="spinner sm"></div>${esc(t('ccs.loading'))}</div></div>`, { wide: true });
  m.el.classList.add('cc-wide');
  $('h2', m.el).textContent = slot === 'tray' ? t('ccs.title_tray') : t('ccs.title', { name: save.name });
  $('[data-x]', m.el).onclick = () => m.close();
  const body = $('.body', m.el), tabs = $('.cc-tabs', m.el);
  const pic = (f, cls) => {
    const main = f.pic ? `/api/cc/pic/${f.pic.kind}/${f.pic.id}` : '', fb = ccThumb(f.item);
    const src = main || fb, cat = (f.item && f.item.category) || 'other';
    return `<div class="${cls}">${src ? `<img src="${src}" alt="" loading="lazy" decoding="async" data-cat="${esc(cat)}"${main && fb ? ` data-fb="${fb}"` : ''}>` : `<div class="cc-ph">${ccIc(cat)}</div>`}</div>`;
  };
  const moreBtn = n => `<div class="actions" style="justify-content:center"><button class="btn small" data-more>${esc(t('ccs.more', { n }))}</button></div>`;
  function draw() {
    const d = X.data;
    const c = d.counts || {};
    $('header p', m.el).textContent = [t('ccs.files', { n: Number(c.files) || 0 }), c.parts ? t('ccs.parts', { n: Number(c.parts) }) : '',
      c.objects ? t('ccs.objects', { n: Number(c.objects) }) : '', c.missing ? t('saves.missing', { n: Number(c.missing) }) : t('ccs.nothing_missing')].filter(Boolean).join(' · ');
    tabs.classList.remove('hidden');
    tabs.innerHTML = [['files', `${esc(t('ccs.tab.files'))} <i>${num(c.files)}</i>`], ['sims', esc(t('ccs.tab.sims'))],
      ['missing', `${esc(t('ccs.tab.missing'))} <i class="${c.missing ? 'warn' : ''}">${num(c.missing)}</i>`]]
      .map(([k, l]) => `<button role="tab" aria-selected="${X.tab === k}" class="${X.tab === k ? 'on' : ''}" data-tab="${k}">${l}</button>`).join('');
    if (X.tab === 'files') {
      const files = d.files || [];
      body.innerHTML = !files.length ? `<div class="empty">${esc(d.message || t('ccs.none'))}</div>`
        : `<div class="cc-grid small">${files.slice(0, X.more).map((f, n) => {
            const who = f.objects && !f.parts ? t('ccs.on_lots', { n: Number(f.objects) })
              : f.sims_count ? t('ccs.worn_by', { names: f.sims.slice(0, 2).join(', ') }) + (f.sims_count > 2 ? ` +${num(f.sims_count - 2)}` : '')
              : t('ccs.items_used', { n: Number(f.parts + f.looks) || 0 });
            return `<div class="cc-card${f.item ? '' : ' plain'}" data-file="${n}" title="${esc(f.folder ? f.folder + '/' + f.name : f.name)}">${pic(f, 'cc-pic')}
              <div class="cc-meta"><b>${esc(f.name.replace(/\.package$/i, ''))}</b><span>${esc(f.category_label || t('ccs.cc'))} · ${esc(who)}</span></div></div>`;
          }).join('')}</div>${files.length > X.more ? moreBtn(files.length - X.more) : ''}`;
    } else if (X.tab === 'sims') {
      const hh = d.households || [];
      body.innerHTML = !hh.length ? `<div class="empty">${esc(t('ccs.no_sims'))}</div>` : hh.map((x, i) => `<details class="cc-hh"${i < 2 || x.played ? ' open' : ''}>
          <summary>${ic('users')}<b>${esc(x.name)}</b>${x.played ? `<span class="chip hot">${esc(t('ccs.played'))}</span>` : ''}<span class="muted">${esc(t('saves.sims', { n: x.sims.length }))}</span></summary>
          ${x.sims.map(s => `<div class="cc-sim"><div class="who"><b>${esc(s.name)}</b><span>${esc(t('saves.cc_items', { n: Number(s.parts) || 0 }))}${s.missing ? ` · <span class="warn-t">${esc(t('saves.missing', { n: Number(s.missing) }))}</span>` : ''}</span></div>
            <div class="cc-strip">${s.files.slice(0, 10).map(n => d.files[n] ? pic(d.files[n], 'cc-mini') : '').join('')}${s.files.length > 10 ? `<span class="more">+${num(s.files.length - 10)}</span>` : ''}</div></div>`).join('')}
        </details>`).join('');
    } else {
      const miss = d.missing || [];
      body.innerHTML = `<div class="note">${ic('info')}<span>${esc(t('ccs.missing_note'))}</span></div>
        ${!miss.length ? `<div class="note ok">${ic('check')}<span>${esc(t(slot === 'tray' ? 'ccs.all_here_tray' : 'ccs.all_here'))}</span></div>`
          : `<div class="cc-missing">${miss.slice(0, X.more).map(x => `<div class="cc-miss">
              <div class="cc-mpic">${x.kind !== 'look' ? `<img src="/api/cc/pic/${x.kind === 'object' ? 'object' : 'cas'}/${x.id}" alt="" loading="lazy" data-cat="${CC_KIND_ICON[x.kind]}">` : `<div class="cc-ph">${ccIc(CC_KIND_ICON[x.kind])}</div>`}</div>
              <div class="grow"><b>${esc(x.what)}</b>
                <div class="cc-id"><code>${esc(x.id)}</code><button class="icon-btn" data-copy="${esc(x.key)}" title="${esc(t('ccs.copy_title'))}">${ccIc('copy')}</button></div>
                ${x.sims && x.sims.length ? `<span class="muted">${esc(x.sims_count > 4 ? t('ccs.worn_by_more', { names: x.sims.slice(0, 4).join(', '), n: x.sims_count - 4 }) : t('ccs.worn_by', { names: x.sims.slice(0, 4).join(', ') }))}</span>`
                  : x.kind === 'object' ? `<span class="muted">${esc(t('ccs.on_lot'))}</span>` : ''}
                ${x.found && x.found.length ? x.found.map(f => `<div class="cc-found">${ic('check')}<span>${esc(t(f.place === 'Inbox' ? 'ccs.in_inbox' : 'ccs.in_safe'))}: <b>${esc(f.name)}</b>${f.creator ? ` <span class="muted">${esc(t('ccs.creator_guess', { name: f.creator }))}</span>` : ''}</span></div>`).join('')
                  : `<div class="cc-found none">${esc(t('ccs.not_found'))}</div>`}</div></div>`).join('')}</div>
            ${miss.length > X.more ? moreBtn(miss.length - X.more) : ''}`}`;
    }
  }
  m.el.addEventListener('click', async e => {
    const tab = e.target.closest('[data-tab]');
    if (tab) { X.tab = tab.dataset.tab; X.more = 60; draw(); body.scrollTop = 0; return; }
    if (e.target.closest('[data-more]')) { X.more += 120; draw(); return; }
    const cp = e.target.closest('[data-copy]');
    if (cp) {
      try { await navigator.clipboard.writeText(cp.dataset.copy); toast(t('ccs.copied', { id: cp.dataset.copy }), 'ok'); }
      catch { toast(cp.dataset.copy); }
      return;
    }
    const card = e.target.closest('[data-file]');
    if (card && X.data) {
      const f = X.data.files[+card.dataset.file];
      if (f && f.item) { const o = await call('cc/open', { id: f.item.id }); toast(o.message || t(o.ok ? 'common.opened' : 'common.cant_open'), o.ok ? 'ok' : 'err'); }
    }
  });
  (async () => {
    const r = await call(`saves/${encodeURIComponent(slot)}/cc`);
    if (!document.body.contains(m.el)) return;
    if (r.http !== 200 || !r.ok) {
      $('header p', m.el).textContent = '';
      body.innerHTML = `<div class="note ${r.busy ? 'warn' : 'err'}">${ic('warn')}<span>${esc(r.message || t('ccs.error'))}</span></div>`;
      return;
    }
    X.data = r;
    if (slot !== 'tray' && r.counts && r.counts.missing && !r.counts.files) X.tab = 'missing';
    draw();
    const note = `<span class="hint">${esc(t((r.index || {}).state !== 'ready' ? 'ccs.hint_sort' : 'ccs.hint_click'))}</span>`;
    const foot = document.createElement('footer');
    foot.innerHTML = `${note}<button class="btn primary" data-x2>${esc(t('common.close'))}</button>`;
    m.el.appendChild(foot);
    $('[data-x2]', foot).onclick = () => m.close();
  })();
}

// pictures fade in once they have arrived (a soft sheen shows until then)
document.addEventListener('load', e => {
  const img = e.target;
  if (img instanceof HTMLImageElement && img.closest('.cc-pic')) img.classList.add('in');
}, true);
function ccShowLoaded(root) {
  $$('.cc-pic img', root).forEach(i => { if (i.complete && i.naturalWidth) i.classList.add('in'); });
}

// pictures that fail: try the file's own picture, then show the category's icon
document.addEventListener('error', e => {
  const img = e.target;
  if (!(img instanceof HTMLImageElement) || !img.closest('.cc-pic, .cc-mini, .cc-mpic, .cc-big')) return;
  const fb = img.dataset.fb;
  if (fb) { img.dataset.fb = ''; img.src = fb; return; }
  const ph = document.createElement('div');
  ph.className = 'cc-ph';
  ph.innerHTML = ccIc(img.dataset.cat || 'other');
  img.replaceWith(ph);
}, true);

// ------------------------------------------------------------------------------------------ tooltips
// icons, chips and badges explain themselves in a styled tip (their title text, shown on hover and keyboard focus)
const TIP_ON = '.icon-btn, .btn, .chip, .cc-badge, .preview-chip, .mode-chip, .cc-check, .care-size, .cc-tools select, [data-tip]';
const tipEl = document.createElement('div');
tipEl.className = 'tooltip tip hidden';
tipEl.setAttribute('role', 'tooltip');
tipEl.id = 'tip';
document.body.appendChild(tipEl);
let tipFor = null, tipT = 0;
function tipTarget(node) {
  const el = node && node.closest ? node.closest(TIP_ON) : null;
  if (!el) return null;
  if (el.title) {                                  // the native tip would show twice: keep the text here instead
    el.dataset.tip = el.title;
    if (!el.getAttribute('aria-label') && !/\p{L}/u.test(el.textContent)) { el.setAttribute('aria-label', el.title); el.dataset.tipAria = '1'; }
    el.removeAttribute('title');
  }
  return el.dataset.tip ? el : null;
}
function tipShow(el) {
  tipFor = el;
  tipEl.textContent = el.dataset.tip;
  tipEl.classList.remove('hidden');
  const r = el.getBoundingClientRect(), tw = tipEl.offsetWidth, th = tipEl.offsetHeight;
  const above = r.top - th - 8 > 8;
  tipEl.style.left = Math.max(8, Math.min(window.innerWidth - tw - 8, r.left + r.width / 2 - tw / 2)) + 'px';
  tipEl.style.top = (above ? r.top - th - 8 : r.bottom + 8) + 'px';
}
function tipHide() { clearTimeout(tipT); tipFor = null; tipEl.classList.add('hidden'); }
document.addEventListener('pointerover', e => {
  const el = tipTarget(e.target);
  if (el === tipFor) return;
  tipHide();
  if (el) tipT = setTimeout(() => { if (document.body.contains(el)) tipShow(el); }, 380);
});
document.addEventListener('focusin', e => {
  const el = tipTarget(e.target);
  tipHide();
  if (el && e.target.matches(':focus-visible')) tipShow(el);
});
['pointerdown', 'focusout', 'scroll', 'keydown'].forEach(x => document.addEventListener(x, tipHide, true));

// ------------------------------------------------------------------------------------------ start
window.addEventListener('hashchange', route);
let resizeT;
window.addEventListener('resize', () => { clearTimeout(resizeT); resizeT = setTimeout(() => { if (S.page === 'performance') drawChart(); }, 120); });
document.addEventListener('visibilitychange', () => { if (!document.hidden && !busy()) refreshStatus(); });
setInterval(() => { if (!document.hidden && !busy()) refreshStatus(); }, 8000);

async function previewHooks() {
  // only with example data: lets the screenshot tests open a dialog (?open=finder|undo|cleanup|restore)
  const q = new URLSearchParams(location.search), what = q.get('open');
  if (!what || !(st().hub && st().hub.preview)) return;
  if (what === 'finder') openFinder(q.get('path') || '');
  if (what === 'last') {
    const v = await call('task/current');
    if (v.http === 200 && v.state && v.state !== 'running') {
      const ov = Overlay((TITLES[v.action] || working)(v.args || {}));
      ov.update(v);
      ov.finish(v);
    }
  }
  if (what === 'undo') confirmUndo();
  if (what === 'restore') confirmRestore();
  if (what === 'cleanup') { S.plan = { ok: true, copies: 4210, gb: 18.2, rewritten: 57, removed: 12 }; render(); confirmCleanup(); }
}

// patch day, game errors, save backups, load-time savings (care.js): its helpers, buttons, titles and change kinds
care.init({ call, esc, ic, render: () => render(), runTask, confirmBox, toast, busy, gameRunning, isNum, ago, day, dayTime, en,
  page: () => S.page });
Object.assign(ACTS, care.ACTS);
Object.assign(TITLES, care.TITLES);
Object.assign(DONE, care.DONE);
Object.assign(KIND, care.KIND);

(async function start() {
  await startLanguage();
  route();
  await refreshStatus(true);
  const cur = await call('task/current');
  if (cur.http === 200 && cur.state === 'running') {
    if (cur.action === 'cc_scan') ccWatch(cur.id); else watchTask(cur.id, { action: cur.action, args: cur.args || {} });
  }
  previewHooks();
})();
