// Novulon's Sims Hub - the app. A plain ES module with no libraries; it talks to speedkit/hub/server.py.
import * as care from './care.js';          // patch day, game errors, save backups, load-time savings

// ------------------------------------------------------------------------------------------ small helpers
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ESC[c]);
const ic = (id, cls = '') => `<svg${cls ? ` class="${cls}"` : ''} aria-hidden="true"><use href="#i-${id}"/></svg>`;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const isNum = n => n !== null && n !== undefined && n !== '' && !isNaN(Number(n));
const num = n => isNum(n) ? Math.round(Number(n)).toLocaleString('en-US') : '—';
const gb = g => !isNum(g) ? '—' : (Number(g) >= 100 ? Math.round(g).toLocaleString('en-US') : Number(g).toFixed(1).replace(/\.0$/, '')) + ' GB';
const plural = (n, one, many = one + 's') => `${num(n)} ${Number(n) === 1 ? one : many}`;
// how much the duplicate clean-up frees: small amounts in MB, never "0 GB"
const planSize = p => !p || !isNum(p.gb) || Number(p.gb) >= 0.1 || !isNum(p.mb) ? gb(p && p.gb)
  : Number(p.mb) < 1 ? 'less than 1 MB' : `${Math.round(Number(p.mb))} MB`;

function dur(s, short = false) {
  if (!isNum(s)) return '—';
  s = Math.round(Number(s));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60), r = s % 60;
  if (m < 60) return short ? `${m}m ${String(r).padStart(2, '0')}s` : `${m} min ${String(r).padStart(2, '0')} s`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

function ago(iso) {
  const t = Date.parse(iso);
  if (!t) return '';
  const s = (Date.now() - t) / 1000;
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) { const h = Math.round(s / 3600); return `${h} hour${h === 1 ? '' : 's'} ago`; }
  if (s < 2 * 86400) return 'yesterday';
  if (s < 14 * 86400) return `${Math.floor(s / 86400)} days ago`;
  const d = new Date(t);
  return d.toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: d.getFullYear() === new Date().getFullYear() ? undefined : 'numeric' });
}

const dayTime = iso => {
  const d = new Date(iso);
  return isNaN(d) ? '' : `${d.toLocaleDateString('en-US', { day: 'numeric', month: 'short' })}, ${d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`;
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
    return { ok: false, http: 0, message: "The Hub isn't answering. Close this window and open Novulon's Sims Hub again." };
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

function modeInfo(p = {}) {
  switch (p.name) {
    case 'fast': return { key: 'QUICK', title: 'Quick Start', sub: 'Only the CC your saves use is loaded.' };
    case 'full': return { key: 'FULL', title: 'Full Start', sub: 'Every CC item you have is loaded.', cls: 'full' };
    case 'save': {
      const s = saveBySlot(p.save_slot), m = /'(.+)'\s*$/.exec(p.label || '');
      return { key: 'ONE SAVE', title: s ? s.name : m ? m[1] : 'One save', sub: 'Only the CC this save uses is loaded.' };
    }
    case 'studio': return { key: 'STUDIO', title: 'Studio mode', sub: 'Only WickedWhims and your animations are loaded.' };
    case 'custom': return { key: 'CUSTOM', title: 'Your own mix', sub: 'Your Mods folder was changed by hand or by another tool.', cls: 'full' };
    default: return { key: '…', title: p.label || 'Not known yet', sub: '' };
  }
}
const PROFILE_WORDS = { fast: 'Quick Start', full: 'Full Start', save: 'One save', studio: 'Studio mode', custom: 'Your own mix' };
const profileWords = p => PROFILE_WORDS[p] || 'Your mods';

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
  $$('#rail a').forEach(a => a.classList.toggle('active', a.dataset.page === S.page));
  document.title = S.page === 'home' ? "Novulon's Sims Hub" : `${$(`#rail a[data-page="${S.page}"] span`).textContent} - Novulon's Sims Hub`;
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
  page.innerHTML = PAGES[S.page]();
  if (open) $$('details', page).forEach((d, i) => { if (open[i]) d.open = true; });
  if (fresh) {
    $('#main').scrollTop = 0;
    page.style.animation = 'none'; void page.offsetWidth; page.style.animation = '';
  }
  if (S.page === 'performance') drawChart();
  AFTER_RENDER.forEach(fn => fn(fresh));
  const back = keep && document.getElementById(keep.id);
  if (back && back !== document.activeElement) { back.focus(); try { back.setSelectionRange(keep.a, keep.b); } catch { /* not a text box */ } }
}

function renderTop() {
  const s = st(), chip = $('#mode-chip');
  if (S.status && s.profile) {
    const m = modeInfo(s.profile);
    chip.innerHTML = `<i class="${m.cls || ''}"></i><span>Right now:</span><b>${esc(m.title)}</b>`;
    chip.title = 'How the game starts right now: ' + m.title;
    chip.classList.remove('hidden');
  } else chip.classList.add('hidden');
  $('#preview-chip').classList.toggle('hidden', !(s.hub && s.hub.preview));
  $('#game-chip').classList.toggle('hidden', !gameRunning());
}

function loadingBlock(text) {
  return `<div class="page-loading"><div class="spinner"></div><span>${esc(text)}</span></div>`;
}

function errorBlock(text) {
  return `<div class="note err" style="margin-top:40px">${ic('warn')}<div><b>${esc(text)}</b><div class="actions" style="margin-top:10px">
    <button class="btn small" data-act="refresh">${ic('refresh')}Try again</button></div></div></div>`;
}

// -------------------------------------------------------------------------------- Home
function renderHome() {
  if (!S.status) return S.statusErr ? errorBlock(S.statusErr) : loadingBlock('Checking your game...');
  const s = st(), lib = s.library || {}, times = starts();
  const lastOf = names => times.find(t => names.includes(t.profile) && isNum(t.launch_to_menu_s));
  const lastFast = lastOf(['fast']), lastFull = lastOf(['full']);
  const fp = s.fastpack || {};
  const g = s.game || {};
  const off = canPlay() ? '' : ' disabled';

  let top = '';
  if (gameRunning()) {
    top = `<div class="play-row"><div class="state-card running"><div class="big-dot"><i></i></div><div class="grow">
      <h2>The Sims 4 is running</h2><p>When the game closes, you can choose a different way to start it here.</p></div></div></div>`;
  } else {
    if (!gameFound()) {
      const moved = gameMoved(g), where = gamePath(g);
      top += `<div class="state-card find"><svg class="bob" viewBox="0 0 24 36" aria-hidden="true"><use href="#i-bob"/></svg><div class="grow">
        <h2>${moved ? "The game isn't where it used to be" : "The Sims 4 wasn't found on this PC"}</h2>
        <p>${moved ? (where ? `The game is no longer at <span class="path">${esc(where)}</span>. Show the Hub where it is now.` : esc(g.message || 'Show the Hub where it is now.'))
          : 'Show the Hub where the game is installed. You only have to do this once.'}</p></div>
        <button class="btn primary big" data-act="find-game">${ic('search')}Locate The Sims 4</button></div>`;
    }
    const fastMeta = [];
    if (isNum(lib.cas_fast) && isNum(lib.cas_full)) fastMeta.push(`<span class="pill">Loads ${num(lib.cas_fast)} of ${num(lib.cas_full)} CC items</span>`);
    if (lastFast) fastMeta.push(`<span>Last load: ${dur(lastFast.launch_to_menu_s)}</span>`);
    if (fp.state === 'stale' || fp.state === 'missing') fastMeta.push(`<span>First start takes a few extra minutes to get ready</span>`);
    const fullMeta = [];
    if (isNum(lib.cas_full)) fullMeta.push(`<span class="pill">Loads all ${num(lib.cas_full)} CC items</span>`);
    if (lastFull) fullMeta.push(`<span>Last load: ${dur(lastFull.launch_to_menu_s)}</span>`);
    top += `<div class="play-row">
      <button class="play fast" data-act="play" data-target="fast"${off}>
        <div class="top"><div class="pic">${ic('bolt-fill')}</div><div class="t">Quick Start</div></div>
        <div class="d">Starts the game with only the custom content (CC) your sims and lots use. It loads much faster, and your sims look exactly the same.</div>
        <div class="m">${fastMeta.join('')}</div>
        <span class="go">${ic('play')}</span>
      </button>
      <button class="play all" data-act="play" data-target="full"${off}>
        <div class="top"><div class="pic">${ic('stack')}</div><div class="t">Full Start</div></div>
        <div class="d">Starts the game with all of your custom content. Use this to build, or to browse all your CC in Create a Sim.</div>
        <div class="m">${fullMeta.join('')}</div>
        <span class="go">${ic('play')}</span>
      </button></div>`;
  }

  const [h1, line] = gameRunning() ? ['The Sims 4 is running', 'Changes are paused until the game is closed.']
    : !gameFound() ? ['Game not found', 'Locate The Sims 4 to start playing.']
    : ['Start The Sims 4', 'Choose how the game loads your custom content.'];
  return `<div class="hello">
      <div><h1>${esc(h1)}</h1><p>${esc(line)}</p></div>
    </div>
    ${care.homeBanner()}
    ${top}
    <h3 class="sec">Right now</h3>
    <div class="stats">${statCards().join('')}</div>
    ${care.homeSavings()}`;
}

// what the "CC items loaded" card says, by the way the game starts right now
const CC_LOADED = {
  full: 'Everything is loaded.',
  fast: 'Only what your sims and lots need.',
  save: 'Only what this save needs.',
  studio: 'Only WickedWhims and your animations - for animation work.',
  custom: 'Changed by hand or by another tool.',
};

function statCards() {
  const s = st(), lib = s.library || {}, mem = s.memory || {}, gfx = s.graphics || {}, disk = s.disk || {};
  const cards = [];
  const m = modeInfo(s.profile);
  cards.push(`<div class="stat"><div class="lbl">${ic('swap')}How it starts</div><div class="v">${esc(m.title)}</div><div class="s">${esc(m.sub)}</div></div>`);

  const now = ccNow(), all = lib.cas_full, mode = (s.profile || {}).name;
  const pct = isNum(now) && isNum(all) && all > 0 ? Math.max(0.5, Math.min(100, now / all * 100)) : null;
  cards.push(`<div class="stat"><div class="lbl">${ic('shirt')}CC items loaded</div>
    <div class="v">${num(now)} <small>of ${num(all)}</small></div>
    <div class="s">${isNum(now) ? (CC_LOADED[mode] || (now >= all ? CC_LOADED.full : 'Only part of your CC is loaded.'))
      : ['studio', 'custom'].includes(mode) ? "Not counted for this way of playing." : 'This shows up after you play with the Hub.'}</div>
    ${pct === null ? '' : `<div class="meter"><i class="${now >= all ? 'full' : ''}" style="width:${pct.toFixed(2)}%"></i></div>`}</div>`);

  const last = starts()[0];
  cards.push(last
    ? `<div class="stat"><div class="lbl">${ic('clock')}Last start</div><div class="v">${dur(last.launch_to_menu_s)}</div>
       <div class="s">to the main menu, with <b>${esc(profileWords(last.profile))}</b> · ${esc(ago(last.time))}</div>
       ${isNum(last.lot_load_s) ? `<div class="s">Loading a lot took ${dur(last.lot_load_s)}.</div>` : ''}</div>`
    : `<div class="stat"><div class="lbl">${ic('clock')}Last start</div><div class="v">Not timed yet</div>
       <div class="s">Start times show up after you play with the Hub.</div></div>`);

  if (gfx.state === 'tuned') {
    cards.push(`<div class="stat good"><div class="lbl">${ic('image')}Graphics</div><div class="v">Max Quality, lag fixed</div>
      <div class="ok-line">${ic('check')}Looks its best, without the lag</div></div>`);
  } else if (gfx.can_tune) {
    cards.push(`<div class="stat warn"><div class="lbl">${ic('image')}Graphics</div><div class="v">Max graphics, with lag</div>
      <div class="s">${esc(gfx.label || 'Your graphics file makes the game lag.')}</div>
      <div class="foot"><button class="btn small primary" data-act="gfx-fix"${busy() || gameRunning() ? ' disabled' : ''}>${ic('spark')}Fix the lag in one click</button></div></div>`);
  } else if (gfx.state === 'stock') {
    cards.push(`<div class="stat"><div class="lbl">${ic('image')}Graphics</div><div class="v">The game's own settings</div>
      <div class="s">Nothing to fix here.</div></div>`);
  } else {
    cards.push(`<div class="stat"><div class="lbl">${ic('image')}Graphics</div><div class="v">${esc(gfx.label || 'Not known yet')}</div>
      <div class="s">${esc((gfx.details || [])[0] || '')}</div></div>`);
  }

  const warns = mem.warnings || [];
  cards.push(`<div class="stat${warns.length ? ' warn' : ' good'}"><div class="lbl">${ic('chip')}Memory</div>
    <div class="v">${gb(mem.free_gb)} free <small>of ${gb(mem.total_gb)}</small></div>
    ${warns.length ? warns.slice(0, 2).map(w => `<div class="warn-line">${ic('warn')}<span>${esc(w)}</span></div>`).join('')
      : `<div class="ok-line">${ic('check')}Enough for a smooth start</div>`}</div>`);

  const low = isNum(disk.c_free_gb) && disk.c_free_gb < 25;
  cards.push(`<div class="stat${low ? ' warn' : ''}"><div class="lbl">${ic('drive')}Free space</div>
    <div class="v">${gb(disk.c_free_gb)} <small>on drive C:</small></div>
    ${low ? `<div class="warn-line">${ic('warn')}<span>Your C: drive is getting full.</span></div>
      <div class="foot"><a class="btn small" href="#library">${ic('broom')}Free up space</a></div>`
      : `<div class="s">Your CC library: ${num(lib.packages)} files, ${gb(lib.gb)}.</div>`}</div>`);
  return cards;
}

// -------------------------------------------------------------------------------- Saves
function renderSaves() {
  const head = `<div class="page-head"><div class="grow"><h1>Your <span>saves</span></h1>
    <p>Play one save, and only the CC that save uses is loaded. It's the fastest way to start.</p></div>
    <button class="btn" data-act="saves-refresh"${S.savesLoading ? ' disabled' : ''}>${ic('refresh')}Look again</button></div>`;
  if (!S.saves) {
    return head + (S.savesLoading || !S.status ? `<div class="saves-loading"><div class="spinner"></div><div><b>Looking at your saves...</b>
      <div class="muted">The first time can take a minute.</div></div></div>` : '');
  }
  if (!S.saves.ok) return head + `<div class="note err">${ic('warn')}<span>${esc(S.saves.message || "Your saves couldn't be read right now.")}</span></div>`;
  const saves = [...(S.saves.saves || [])].sort((a, b) => (Date.parse(b.last_played) || 0) - (Date.parse(a.last_played) || 0));
  if (!saves.length) {
    return head + `<div class="card empty"><b>No saves yet.</b><br>Play The Sims 4 and save your game - it shows up here.</div>`;
  }
  const p = st().profile || {};
  const why = gameRunning() ? 'The Sims 4 is running' : !gameFound() ? 'Find your game first' : '';
  return head + `<div class="saves">${saves.map(s => {
    const sub = [s.household, s.world].filter(Boolean).join(' · ');
    const pack = s.pack || {};
    const extra = pack.state === 'fresh' ? `${ic('bolt')}Ready for a fast start${isNum(s.cas_loaded) ? ` · loads ${num(s.cas_loaded)} CC items` : ''}`
      : pack.state === 'stale' ? `${ic('clock')}Gets a quick update when you press Play`
      : `${ic('clock')}The first start takes a few extra minutes`;
    const current = p.name === 'save' && p.save_slot === s.slot;
    const letter = (String(s.name || '?').trim()[0] || '?').toUpperCase();
    return `<div class="save">
      <div class="head"><div class="avatar">${esc(letter)}</div><div class="who"><b title="${esc(s.name)}">${esc(s.name || s.slot)}</b>
        ${sub ? `<span title="${esc(sub)}">${esc(sub)}</span>` : ''}</div></div>
      <div class="when">${ic('clock')}Played ${esc(ago(s.last_played))}${current ? ' <span class="chip ok" style="margin-left:4px">Set up now</span>' : ''}</div>
      <div class="facts"><span class="chip">${ic('users')}${plural(s.sims, 'sim')}</span><span class="chip">${ic('lot')}${plural(s.lots, 'lot')}</span>
        ${isNum(s.cc_parts) ? `<span class="chip hot">${ic('shirt')}${num(s.cc_parts)} CC items</span>` : ''}
        ${isNum(s.cc_missing) && s.cc_missing > 0 ? `<span class="chip warn" title="CC this save uses that isn't in your Mods folder any more">${ic('warn')}${num(s.cc_missing)} missing</span>` : ''}</div>
      <div class="extra">${s.problem ? `${ic('warn')}${esc(s.problem)}` : extra}</div>
      ${care.saveLine(s)}
      ${saveCcButton(s)}
      <button class="btn primary block" data-act="play" data-target="save:${esc(s.slot)}"${canPlay() ? '' : ' disabled'}>
        ${ic('play')}${why ? esc(why) : 'Play this save'}</button>
    </div>`;
  }).join('')}</div>${care.savesSection()}` + trayCcCard();
}

// -------------------------------------------------------------------------------- Library
function renderLibrary() {
  if (!S.status) return S.statusErr ? errorBlock(S.statusErr) : loadingBlock('Looking at your library...');
  const lib = st().library || {};
  const ib = S.inbox;
  const items = (ib && ib.ok && ib.items) || [];
  const stateOf = i => String(i.status || '').toLowerCase();
  const waiting = items.filter(i => !['added', 'done', 'installed'].includes(stateOf(i)));
  const addable = waiting.filter(i => !['refused', 'skipped'].includes(stateOf(i)));
  const noChange = busy() || gameRunning();
  let inboxBody;
  if (!ib) inboxBody = `<div class="saves-loading" style="padding:16px 4px"><div class="spinner sm"></div>Looking in your Inbox folder...</div>`;
  else if (!ib.ok) inboxBody = `<div class="note err">${ic('warn')}<span>${esc(ib.message || "The Inbox folder couldn't be read.")}</span></div>`;
  else if (!waiting.length) inboxBody = `<div class="empty" style="padding:14px 2px 0">Nothing is waiting right now. Put new downloads in the folder above, then press <b>Look again</b>.</div>`;
  else inboxBody = `<div class="items">${waiting.slice(0, 12).map(i => `<div class="item">${ic(/\.ts4script$/i.test(i.name) ? 'terminal' : 'download')}
      <span class="n" title="${esc(i.name)}">${esc(i.name)}</span><span class="r" title="${esc(i.reason || '')}">${
        stateOf(i) === 'refused' ? `<span class="chip warn">Can't be added</span> ` : stateOf(i) === 'skipped' ? '<span class="chip">Skipped</span> ' : ''}${esc(i.reason || '')}</span></div>`).join('')}
      ${waiting.length > 12 ? `<div class="muted" style="padding:4px 2px">and ${num(waiting.length - 12)} more</div>` : ''}</div>`;
  const plan = S.plan;
  return `<div class="page-head"><div class="grow"><h1>Your <span>CC library</span></h1>
      <p>${isNum(lib.packages) ? `${num(lib.packages)} CC and mod files, ${gb(lib.gb)} in total.` : 'Add new downloads, free up space, and see what you have.'}</p></div></div>
    ${ccSlot()}

    <div class="card"><div class="card-head"><div class="ic">${ic('download')}</div><div class="grow"><h2>Add new downloads</h2>
      <p>Put the CC and mods you download into this folder. Press <b>Add to game</b>, and the Hub puts them in the right place, the safe way.</p></div></div>
      <div class="path-box">${ic('folder', 'fold')}<span class="path">${esc((ib && ib.inbox_path) || 'Finding your Inbox folder...')}</span>
        <button class="btn small" data-act="open" data-what="inbox">${ic('folder')}Open folder</button></div>
      ${inboxBody}
      <div class="actions"><button class="btn primary" data-act="inbox-apply"${addable.length && !noChange ? '' : ' disabled'}>${ic('check')}Add to game${addable.length ? ` (${num(addable.length)})` : ''}</button>
        <button class="btn ghost" data-act="inbox-refresh"${S.inboxLoading ? ' disabled' : ''}>${ic('refresh')}Look again</button></div>
    </div>

    <div class="card"><div class="card-head"><div class="ic pink">${ic('broom')}</div><div class="grow"><h2>Free up space</h2>
      <p>Some CC is stored more than once. The Hub can remove the extra copies. Your game looks exactly the same, and you can undo it on the Tools page.</p></div></div>
      ${plan && plan.ok ? `<div class="plan"><div><b>${planSize(plan)}</b><span>can be freed</span></div><div><b>${num(plan.copies)}</b><span>extra copies</span></div>
        <div><b>${num((plan.rewritten || 0) + (plan.removed || 0))}</b><span>files made smaller or removed</span></div></div>` : ''}
      <div class="actions"><button class="btn primary" data-act="cleanup-plan"${noChange ? ' disabled' : ''}>${ic('search')}${plan ? 'Check again' : 'Check how much space can be freed'}</button>
        ${plan && plan.ok && plan.copies > 0 ? `<button class="btn soft" data-act="cleanup-confirm"${noChange ? ' disabled' : ''}>${ic('broom')}Free up ${planSize(plan)}</button>` : ''}</div>
    </div>

    <div class="card"><div class="card-head"><div class="ic violet">${ic('doc')}</div><div class="grow"><h2>Library report</h2>
      <p>One page with an overview of your CC, your saves and the CC they use, your graphics settings, memory and how fast the game starts.</p></div></div>
      <div class="actions"><button class="btn" data-act="report"${busy() ? ' disabled' : ''}>${ic('doc')}Open library report</button></div>
    </div>`;
}

// -------------------------------------------------------------------------------- Performance
const GFX = {
  RenderSimLODDistances: ['How far away sims keep full detail', 'Further away means more work for your PC'],
  RenderSimTextureSizes: ["How sharp sims' skin and clothes are", 'Up close, sims stay just as sharp'],
  ObjectSizeCullFactor: ['How far away small objects are drawn', ''],
  ObjectLODBias: ['When far objects switch to simpler shapes', ''],
  ClipPlaneDistances: ['How far the camera can see', ''],
  FSAALevel: ['Edge smoothing', '8 is the highest level the game really has'],
  ShadowMapSize: ['Shadow sharpness', ''],
  MirrorFadeRadiusThreshold: ['How far away mirrors still reflect', ''],
  InteriorMirrorFarPlane: ['How far indoor reflections reach', ''],
  ExteriorMirrorFarPlane: ['How far outdoor reflections reach', ''],
  TerrainLODBoost: ['Ground detail far away', ''],
};
const words = k => String(k || '').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/_/g, ' ');

function renderPerformance() {
  if (!S.status) return S.statusErr ? errorBlock(S.statusErr) : loadingBlock('Checking your game...');
  const s = st(), gfx = s.graphics || {}, mon = s.monitor || {};
  const tuned = gfx.state === 'tuned';
  const noChange = busy() || gameRunning();
  const table = (S.graphics && S.graphics.ok && S.graphics.table) || [];
  const good = tuned || gfx.state === 'stock';
  const gState = `<div class="gfx-state ${good ? 'good' : gfx.can_tune ? 'bad' : ''}"><div class="dot">${ic(good ? 'check' : 'warn')}</div>
    <div><b>${esc(tuned ? 'Max Quality, lag fixed' : gfx.label || 'Not known yet')}</b>
    <span>${tuned ? 'Everything still looks like your max graphics - only the settings that caused lag were fixed.'
      : gfx.can_tune ? 'Your graphics file asks for more than the game can handle smoothly. One click fixes it and keeps max quality.'
      : gfx.state === 'stock' ? "You use the game's own graphics settings. There's nothing to fix." : ''}</span></div></div>`;
  const details = (gfx.details || []).length ? `<ul class="details">${gfx.details.map(d => `<li>${esc(d)}</li>`).join('')}</ul>` : '';
  let tableHtml = '';
  if (table.length) {
    tableHtml = `<div class="table-wrap"><table class="t"><thead><tr><th>What it controls</th><th>Game's own</th>
      <th>${tuned ? 'Before the fix' : 'Your file now'}</th><th>${tuned ? 'Now' : 'With the fix'}</th></tr></thead><tbody>
      ${table.map(r => {
        const [what, why] = GFX[r.prop] || GFX[r.setting] || [r.prop ? r.setting : words(r.setting), ''];
        return `<tr><td><span class="what">${esc(what)}</span>${why ? `<span class="why">${esc(why)}</span>` : ''}</td>
          <td class="num">${esc(r.stock)}</td><td class="num before">${esc(r.before)}</td><td class="num after">${esc(r.after)}</td></tr>`;
      }).join('')}</tbody></table></div>`;
  } else if (S.graphicsLoading) {
    tableHtml = `<div class="saves-loading" style="padding:16px 4px"><div class="spinner sm"></div>Reading your graphics settings...</div>`;
  }
  let gActions = '';
  if (gfx.can_tune) gActions = `<button class="btn primary" data-act="gfx-fix"${noChange ? ' disabled' : ''}>${ic('spark')}Fix the lag, keep max quality</button>`;
  else if (tuned) gActions = `<button class="btn ghost" data-act="gfx-restore"${noChange ? ' disabled' : ''}>${ic('undo')}Restore previous graphics</button>`;

  return `<div class="page-head"><div class="grow"><h1><span>Performance</span></h1>
      <p>Faster loading and less lag, with the same max graphics.</p></div></div>

    <div class="card"><div class="card-head"><div class="ic">${ic('image')}</div><div class="grow"><h2>Graphics</h2>
      <p>Your graphics settings file decides how good the game looks, and how much it lags.</p></div></div>
      ${gState}${details}${tableHtml}${gActions ? `<div class="actions">${gActions}</div>` : ''}</div>

    <div class="card"><div class="card-head"><div class="ic blue">${ic('clock')}</div><div class="grow"><h2>How long the game takes to start</h2>
      <p>Timed by the SpeedKit Monitor every time you play: from pressing Play to the main menu.</p></div></div>
      ${loadTimes()}</div>

    <div class="card"><div class="card-head"><div class="ic green">${ic('gauge')}</div><div class="grow"><h2>Find what makes your game lag</h2>
      <p>The SpeedKit Monitor has a lag meter built in. It shows which mods slow your game down.</p></div>
      ${mon.installed ? `<span class="chip ok">${ic('check')}Installed</span>` : ''}</div>
      <ol class="steps">
        <li><div><b>Load your game and go to a lot</b><span>Play the way you usually do, where it feels slow.</span></div></li>
        <li><div><b>Press <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>C</kbd></b><span>The cheat box opens at the top of the screen.</span></div></li>
        <li><div><b>Type <code class="cheat">speedkit.lag</code> and press <kbd>Enter</kbd></b><span>Then keep playing normally for one minute.</span></div></li>
        <li><div><b>Read the result</b><span>A message in the game names the 5 mods that slow it down the most. A full report is saved in your reports folder.</span></div></li>
      </ol>
      <div class="note">${ic('info')}<span>Want a longer test? Type <code class="cheat">speedkit.lag 120</code> to measure for 2 minutes.</span></div>
      ${mon.installed ? '' : `<div class="note warn">${ic('warn')}<span>The lag meter isn't in your game yet. It's added the next time you press Play.</span></div>`}
      <div class="actions"><button class="btn" data-act="open" data-what="reports">${ic('folder')}Open reports folder</button></div></div>`;
}

function loadTimes() {
  const rows = starts();
  if (!rows.length) return `<div class="empty">No start times yet. They show up here after you play with the Hub.</div>`;
  const avg = list => list.length ? list.reduce((a, r) => a + Number(r.launch_to_menu_s), 0) / list.length : null;
  const fast = avg(rows.filter(r => FASTISH.has(r.profile))), full = avg(rows.filter(r => !FASTISH.has(r.profile)));
  const tiles = [
    `<div class="tile"><div class="lbl"><i class="sw" style="background:var(--fast)"></i>Fast start, on average</div><b>${fast === null ? '—' : dur(fast)}</b></div>`,
    `<div class="tile"><div class="lbl"><i class="sw" style="background:var(--full)"></i>Full Start, on average</div><b>${full === null ? '—' : dur(full)}</b></div>`,
    fast && full && full > fast
      ? `<div class="tile hero"><div class="lbl">${ic('bolt')}Fast start is</div><b>${(full / fast).toFixed(1).replace(/\.0$/, '')}x faster</b></div>`
      : `<div class="tile"><div class="lbl">${ic('clock')}Starts timed</div><b>${num(rows.length)}</b></div>`,
  ];
  return `<div class="tiles">${tiles.join('')}</div>
    <div class="chart" id="chart" role="img" aria-label="Start times, oldest on the left"></div>
    <div class="legend"><span><i style="background:var(--fast)"></i>Quicker starts (Quick Start, one save or Studio)</span><span><i style="background:var(--full)"></i>Full Start</span></div>
    <details class="more"><summary>See every start as a list</summary><div class="table-wrap"><table class="t">
      <thead><tr><th>When</th><th>How it started</th><th>To the main menu</th><th>Loading a lot</th></tr></thead><tbody>
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
  const slot = pw / rows.length, bw = Math.min(24, slot * 0.62);
  let g = '';
  for (let v = 0; v <= top + 1e-6; v += step * 60) {
    g += `<line class="grid-line" x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/>
      <text class="axis-t" x="${L - 10}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end">${v === 0 ? '0' : `${+(v / 60).toFixed(1)} min`}</text>`;
  }
  const every = Math.max(1, Math.ceil(rows.length / Math.max(1, Math.floor(pw / 74))));
  rows.forEach((r, i) => {
    const v = Number(r.launch_to_menu_s), x = L + i * slot + (slot - bw) / 2, y0 = T + ph, h = Math.max(2, y0 - y(v)), yt = y0 - h;
    const rad = Math.min(4, bw / 2, h);
    const color = FASTISH.has(r.profile) ? 'var(--fast)' : 'var(--full)';
    g += `<path class="bar" data-i="${i}" fill="${color}" d="M${x.toFixed(1)},${y0} V${(yt + rad).toFixed(1)} Q${x.toFixed(1)},${yt.toFixed(1)} ${(x + rad).toFixed(1)},${yt.toFixed(1)}
      H${(x + bw - rad).toFixed(1)} Q${(x + bw).toFixed(1)},${yt.toFixed(1)} ${(x + bw).toFixed(1)},${(yt + rad).toFixed(1)} V${y0} Z"/>`;
    if (i === rows.length - 1) g += `<text class="val-t" x="${(x + bw / 2).toFixed(1)}" y="${(yt - 7).toFixed(1)}" text-anchor="middle">${dur(v, true)}</text>`;
    if ((rows.length - 1 - i) % every === 0) {
      const d = new Date(r.time);
      g += `<text class="axis-t" x="${(L + i * slot + slot / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle">${isNaN(d) ? '' : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</text>`;
    }
    g += `<rect class="hit" data-i="${i}" x="${(L + i * slot).toFixed(1)}" y="${T}" width="${slot.toFixed(1)}" height="${ph}"/>`;
  });
  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">${g}</svg>`;
  const tip = $('#tooltip');
  host.onmousemove = e => {
    const hit = e.target.closest('.hit');
    if (!hit) { host.onmouseleave(); return; }
    const i = +hit.dataset.i, r = rows[i];
    host.classList.add('hovering');
    $$('.bar', host).forEach(b => b.classList.toggle('on', +b.dataset.i === i));
    tip.innerHTML = `<b><i class="k" style="background:${FASTISH.has(r.profile) ? 'var(--fast)' : 'var(--full)'}"></i>${esc(profileWords(r.profile))}</b>
      <span class="muted">${esc(dayTime(r.time))}</span><br>${dur(r.launch_to_menu_s)} to the main menu${isNum(r.lot_load_s) ? `<br>${dur(r.lot_load_s)} to load a lot` : ''}`;
    tip.classList.remove('hidden');
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.min(window.innerWidth - tw - 10, e.clientX + 14) + 'px';
    tip.style.top = Math.max(10, e.clientY - th - 12) + 'px';
  };
  host.onmouseleave = () => { host.classList.remove('hovering'); tip.classList.add('hidden'); };
}

// -------------------------------------------------------------------------------- Tools
const KIND = {
  profile: ['Changed how the game starts', 'swap'], inbox: ['Added new downloads', 'download'], dedup: ['Removed extra copies of CC', 'broom'],
  merge: ['Tidied your CC into fewer files', 'layers'], settings: ['Changed the graphics', 'image'], caches: ["Cleared the game's caches", 'broom'],
  fastpack: ['Prepared Quick Start', 'bolt'], savepack: ['Prepared a save to play', 'bolt'], usedpack: ["Prepared your saves' CC", 'bolt'],
  install: ['Updated the SpeedKit Monitor', 'gauge'], monitor: ['Updated the SpeedKit Monitor', 'gauge'], cleanup: ['Removed extra copies of CC', 'broom'],
};
const kindOf = k => KIND[k] || ['A change', 'spark'];
// the same rule as the engine's undo_last: finished (or failed) changes, not the small helper steps of a switch
const HELPER = ['thumbnail cache moved aside', 'bring the fast pack home'];
const isHelper = j => HELPER.some(h => String(j.note || '').startsWith(h));
// the engine says which change is next (it also skips a change whose files were changed since); the local rule
// is only for engines that do not say
const undoable = j => 'undoable' in j ? !!j.undoable
  : (s => (s === 'committed' || s.startsWith('failed')) && !isHelper(j))(String(j.state || '').toLowerCase());
const nextUndo = journals => journals.some(j => 'next_undo' in j) ? journals.find(j => j.next_undo) : journals.find(undoable);
function describeChange(j) {
  const note = String(j.note || ''), [label, icon] = kindOf(j.kind);
  let m, title = label;
  if (j.kind === 'profile' && (m = /^switch to (\w+)/i.exec(note))) {
    title = { fast: 'Switched to Quick Start', full: 'Switched to Full Start', studio: 'Switched to Studio mode', custom: 'Switched to your own mix' }[m[1].toLowerCase()]
      || 'Switched to one save';
  } else if (j.kind === 'inbox' && (m = /^(\d+) download/.exec(note))) title = `Added ${plural(+m[1], 'new download')}`;
  else if (j.kind === 'settings' && /max quality/i.test(note)) title = 'Graphics: Max Quality, lag fixed';
  else if (j.kind === 'settings' && /restore|put back/i.test(note)) title = 'Graphics: old file put back';
  else if (j.kind === 'install' && /^uninstall/i.test(note)) title = 'Removed the SpeedKit Monitor';
  else if (j.kind === 'install') title = 'Installed the SpeedKit Monitor';
  else if (j.kind === 'aside') title = /^put back/i.test(note) ? 'Put mods back' : "Set mods aside until they're updated";
  return { title, label, icon };
}

function renderTools() {
  if (!S.status) return S.statusErr ? errorBlock(S.statusErr) : loadingBlock('Checking your game...');
  const s = st(), anim = s.animator || {}, g = s.game || {};
  const noChange = busy() || gameRunning();
  const journals = s.journals || [];
  const next = nextUndo(journals);
  const where = gamePath(g);
  const shown = journals.filter(j => !isHelper(j));
  const changes = shown.length ? `<div class="changes">${shown.map(j => {
    const d = describeChange(j);
    const state = String(j.state || '').toLowerCase();
    const chip = state === 'undone' ? '<span class="chip">Undone</span>' : state === 'rolled_back' ? '<span class="chip">Cancelled</span>'
      : j === next ? '<span class="chip hot">Next to undo</span>'
      : j.cannot_undo ? '<span class="chip" title="Its files were changed or moved since, so it cannot be undone now">Can\'t be undone</span>'
      : state === 'open' || state.startsWith('failed') ? '<span class="chip warn">Didn\'t finish</span>' : '';
    return `<div class="change${state === 'undone' || state === 'rolled_back' ? ' undone' : ''}${j === next ? ' next' : ''}">
      <div class="ci">${ic(d.icon)}</div><div style="min-width:0"><b>${esc(d.title)}</b>
      <span>${esc(d.title !== d.label ? d.label + ' · ' : '')}${esc(ago(j.when))}</span></div>${chip}</div>`;
  }).join('')}</div>` : `<div class="empty">No changes yet. When the Hub changes something, it shows up here, and you can undo it.</div>`;

  return `<div class="page-head"><div class="grow"><h1><span>Tools</span></h1><p>Everything else, in one place.</p></div></div>
    <div class="two">
      <div class="card"><div class="card-head"><img class="anim-logo" src="img/animator.svg" alt=""><div class="grow"><h2>Novulon's Wicked Animator</h2>
        <p>Make WickedWhims animations and send them straight to your game.</p></div></div>
        <div class="actions"><button class="btn primary" data-act="open" data-what="animator"${anim.installed === false ? ' disabled' : ''}>${ic('arrow')}Open Novulon's Wicked Animator</button></div>
        ${anim.installed === false ? `<div class="note warn">${ic('warn')}<span>The Wicked Animator isn't installed on this PC.</span></div>` : ''}
        <div class="note">${ic('bolt')}<div><b>Testing an animation?</b> Studio mode starts the game with only WickedWhims and your animations - the quickest start there is.
          <div style="margin-top:10px"><button class="btn small soft" data-act="play" data-target="studio"${canPlay() ? '' : ' disabled'}>${ic('play')}Play in Studio mode</button></div></div></div>
      </div>
      <div class="card"><div class="card-head"><div class="ic green"><svg viewBox="0 0 24 36" style="width:17px;height:26px" aria-hidden="true"><use href="#i-bob"/></svg></div>
        <div class="grow"><h2>The Sims 4</h2><p>Where the game is installed on this PC.</p></div></div>
        ${gameFound() && where ? `<div class="game-where"><div class="grow"><small>${g.saved ? 'You picked this folder' : 'Found automatically'}</small><span class="path">${esc(where)}</span></div>
            <button class="btn small" data-act="find-game"${busy() ? ' disabled' : ''}>Change</button></div>`
          : gameFound() ? `<div class="game-where"><div class="grow muted">Found automatically.</div><button class="btn small" data-act="find-game">Change</button></div>`
          : `<div class="note warn">${ic('warn')}<span>${gameMoved(g) ? (where ? `The game is no longer at <span class="path">${esc(where)}</span>.` : esc(g.message || "The game isn't where it used to be."))
              : "The Hub couldn't find the game yet."}</span></div>
            <div class="actions"><button class="btn primary" data-act="find-game">${ic('search')}Locate The Sims 4</button></div>`}
        <h3 class="sec" style="margin:20px 0 0">Open a folder</h3>
        <div class="folders">
          <button class="btn small" data-act="open" data-what="mods" title="Your Mods folder">${ic('folder')}<span>Mods</span></button>
          <button class="btn small" data-act="open" data-what="saves" title="Your saved games">${ic('folder')}<span>Saves</span></button>
          <button class="btn small" data-act="open" data-what="inbox" title="Where you put new downloads">${ic('folder')}<span>Inbox</span></button>
          <button class="btn small" data-act="open" data-what="reports" title="Library and lag reports">${ic('folder')}<span>Reports</span></button>
          <button class="btn small" data-act="open" data-what="quarantine" title="Files the Hub removed are kept here, so they can come back">${ic('folder')}<span>Safe copies</span></button>
        </div>
      </div>
    </div>
    ${care.toolsSections()}
    <div class="card" style="margin-top:16px"><div class="card-head"><div class="ic pink">${ic('undo')}</div><div class="grow"><h2>Recent changes</h2>
      <p>Everything the Hub changed in your game folders, newest first. You can undo the newest change.</p></div>
      <button class="btn" data-act="undo"${next && !noChange ? '' : ' disabled'}>${ic('undo')}Undo last change</button></div>
      ${changes}</div>`;
}

// ------------------------------------------------------------------------------------------ data loading
async function refreshStatus(force = false) {
  const r = await call('status' + (force ? '?refresh=1' : ''));
  if (r.http !== 200 || !r.profile) {
    S.statusErr = r.message || "The Hub couldn't check your game right now.";
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
  if (target === 'fast') return 'Starting with Quick Start';
  if (target === 'full') return 'Starting with Full Start';
  if (target === 'studio') return 'Starting Studio mode';
  const s = saveBySlot(String(target || '').replace(/^save:/, ''));
  return s ? `Starting "${s.name}"` : 'Starting your save';
}
const TITLES = {
  play: a => playTitle(a.target), prepare: () => 'Getting the game ready', undo_last: () => 'Undoing the last change',
  inbox: a => a.apply ? 'Adding your new downloads' : 'Looking at your new downloads',
  cleanup_plan: () => 'Checking for extra copies', cleanup_apply: () => 'Freeing up space',
  graphics_tune: a => a.apply ? 'Fixing the graphics lag' : 'Checking your graphics',
  graphics_restore: () => 'Putting your old graphics back', report: () => 'Making your library report',
};
const DONE = {
  play: r => r.launched ? 'The Sims 4 is starting!' : 'All set', prepare: () => 'All set', undo_last: () => 'Change undone',
  inbox: () => 'New downloads added', cleanup_plan: () => 'Check finished', cleanup_apply: () => 'Space freed up',
  graphics_tune: () => 'Graphics fixed', graphics_restore: () => 'Your old graphics are back', report: () => 'Your report is ready',
};

async function runTask(action, args = {}, opts = {}) {
  if (busy()) { toast('Please wait - the Hub is still busy.', 'err'); return null; }
  const r = await call('task', { action, args });
  if (r.http === 409) {
    toast(r.message || 'Please wait - the Hub is still busy.', 'err');
    if (r.task && !S.taskId) watchTask(r.task, {});
    return null;
  }
  if (!r.ok || !r.task) { toast(r.message || "That didn't work.", 'err'); return null; }
  return watchTask(r.task, Object.assign({ action, args }, opts));
}

async function watchTask(id, opts) {
  S.taskId = id;
  renderTop(); render();
  const ov = Overlay(opts.action ? (TITLES[opts.action] || (() => 'Working...'))(opts.args || {}) : 'Working...');
  let view = null, misses = 0;
  for (;;) {
    const v = await call('task/' + encodeURIComponent(id));
    if (v.http === 200 && v.state) {
      misses = 0;
      view = v;
      if (!opts.action && v.action) { opts.action = v.action; opts.args = v.args || {}; ov.title((TITLES[v.action] || (() => 'Working...'))(opts.args)); }
      ov.update(v);
      if (v.state !== 'running') break;
    } else if (v.http === 404 || ++misses > 20) {
      view = { state: 'failed', result: { ok: false, message: v.http === 404
        ? 'The Hub was restarted while this was running. Look at Recent changes on the Tools page to see what happened.'
        : "The Hub stopped answering. Close this window and open Novulon's Sims Hub again." } };
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
    ov.finish(view, { ok: true, message: o.ok ? (o.message || 'Your library report is open in your browser.')
      : "Your library report is ready, but it didn't open by itself. It's in your Reports folder (Tools page)." });
    return view;
  }
  ov.finish(view);
  return view;
}

function Overlay(title) {
  const root = $('#overlay-root');
  root.innerHTML = `<div class="overlay"><div class="task" role="dialog" aria-modal="true" aria-live="polite">
    <div class="top"><div class="big"><div class="spinner"></div></div><div class="grow"><h2></h2><p class="now">Getting started...</p></div></div>
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
      else if (!$('.tx', r).textContent) $('.tx', r).textContent = words(ev.step);
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
    $('h2', el).textContent = ok ? (DONE[action] || (() => 'Done!'))(res) : "That didn't work";
    $('.now', el).textContent = ok ? (res.message || 'All done.') : '';
    const bar = $('.bar-track', el);
    bar.classList.remove('indet');
    if (ok) $('i', bar).style.width = '100%'; else bar.classList.add('hidden');
    const steps = ((view.result || {}).steps || []).filter(x => x && x.message);
    const isWarn = x => x.ok !== false && x.step === 'memory' && !/fine\.?$/i.test(x.message);
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
    if (!ok) msg += `<div class="note err">${ic('warn')}<span>${esc(res.message || 'Something went wrong.')}</span></div>`;
    steps.filter(isWarn).forEach(x => { msg += `<div class="note warn">${ic('warn')}<span>${esc(x.message)}</span></div>`; });
    $('.msg', el).innerHTML = msg;
    const foot = $('footer', el);
    foot.classList.remove('hidden');
    const hint = ok && action === 'play' && res.launched ? 'The game keeps running when you close the Hub.' : '';
    foot.innerHTML = `${hint ? `<span class="hint">${esc(hint)}</span>` : ''}<button class="btn primary" data-close>${ok ? 'OK' : 'Close'}</button>`;
    $('[data-close]', foot).onclick = close;
    $('[data-close]', foot).focus();
  }
  return { update, finish, close, title: t => { $('h2', el).textContent = t; } };
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

function confirmBox({ title, text, what = '', ok = 'OK', cancel = 'Cancel', danger = false }) {
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
    await confirmBox({ title: 'Nothing to free up', text: 'Your CC has no extra copies. Everything is already as small as it can be.', ok: 'OK', cancel: 'Close' });
    return;
  }
  const yes = await confirmBox({
    title: `Free up ${planSize(p)}?`,
    text: `The Hub will remove ${num(p.copies)} extra copies of CC you already have. Your game will look exactly the same.`,
    what: `<div class="confirm-what"><b>You can undo this later</b><span>Removed copies are kept safe, and <b>Undo last change</b> on the Tools page puts everything back.</span></div>`,
    ok: `Free up ${planSize(p)}`, cancel: 'Not now',
  });
  if (yes) runTask('cleanup_apply');
}

async function confirmUndo() {
  const next = nextUndo(st().journals || []);
  if (!next) return;
  const d = describeChange(next);
  const yes = await confirmBox({
    title: 'Undo the last change?', danger: true,
    text: 'The Hub puts your files back the way they were before this change.',
    what: `<div class="confirm-what"><b>${esc(d.title)}</b><span>${esc(d.title !== d.label ? d.label + ' · ' : '')}${esc(ago(next.when))}</span></div>`,
    ok: 'Undo it', cancel: 'Keep it',
  });
  if (yes) runTask('undo_last');
}

async function confirmRestore() {
  const yes = await confirmBox({
    title: 'Put your old graphics back?', danger: true,
    text: 'Your game goes back to the graphics file you had before the fix. It looks the same, but the lag comes back.',
    ok: 'Put it back', cancel: 'Keep the fix',
  });
  if (yes) runTask('graphics_restore', { apply: true });
}

// "Find The Sims 4": the Hub's own folder browser
function openFinder(startPath = '') {
  const F ={ data: null, hist: [], loading: true, err: '', saving: '', saved: '', sugs: null };
  const m = modal(`<header><div class="ic green"><svg viewBox="0 0 24 36" style="width:17px;height:26px" aria-hidden="true"><use href="#i-bob"/></svg></div>
      <div class="grow"><h2>Find The Sims 4</h2><p>Pick the folder where The Sims 4 is installed (the one with the Game and Data folders).</p></div>
      <button class="icon-btn" data-f="close" title="Close">${ic('x')}</button></header>
    <div class="body finder"></div>
    <footer><span class="hint">The Hub only reads folders here. Nothing is changed.</span><button class="btn ghost" data-f="close">Cancel</button></footer>`, { wide: true });
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
      F.err = r.message || "That folder can't be opened.";
      if (!F.data) F.data = { ok: true, path: '', drives: r.drives || [], entries: [] };
    }
    draw();
  }
  async function pick(path) {
    F.saving = path; F.err = ''; draw();
    const r = await call('game_path', { path });
    if (r.ok) {
      F.saved = r.message || 'Saved - the Hub will remember this.';
      draw();
      await refreshStatus(true);
      setTimeout(m.close, 1500);
    } else {
      F.saving = ''; F.err = r.message || "That folder isn't The Sims 4."; draw();
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
  function draw() {
    if (F.saved) {
      body.innerHTML = `<div class="saved"><div class="big">${ic('check')}</div><b>${esc(F.saved)}</b><span class="muted">You're all set to play.</span></div>`;
      return;
    }
    const d = F.data || {};
    const path = d.path || '';
    let h = '';
    const sugs = F.sugs || [];
    if (sugs.length) {
      h += `<div class="lbl" style="margin-top:4px">Found on this PC</div><div class="sug">${sugs.map(s => {
        const p = s.path || gamePath(s);
        return `<div class="sug-card"><svg class="b" viewBox="0 0 24 36" aria-hidden="true"><use href="#i-bob"/></svg><div class="grow">
          <b>The Sims 4</b><span class="path">${esc(p)}</span>${s.hint || s.source ? `<small>${esc(s.hint || s.source)}</small>` : ''}</div>
          <button class="btn primary small" data-f="pick" data-path="${esc(p)}"${F.saving ? ' disabled' : ''}>${F.saving === p ? 'Saving...' : 'Use this'}</button></div>`;
      }).join('')}</div>`;
    }
    const trail = crumbs(path);
    const shown = trail.length > 4 ? [trail[0], null, ...trail.slice(-2)] : trail;
    h += `<div class="lbl">${sugs.length ? 'Or look for it yourself' : 'Look for it'}</div>
      <div class="crumbs"><button class="icon-btn" data-f="back" title="Back"${F.hist.length ? '' : ' disabled'}>${ic('back')}</button>
      <button class="icon-btn" data-f="up" title="Up one folder"${path ? '' : ' disabled'}>${ic('up')}</button>
      <div class="trail"><button data-f="go" data-path="" class="${path ? '' : 'cur'}">${ic('pc')} This PC</button>
      ${shown.map((c, i) => c === null ? `${ic('chev')}<span class="ell">…</span>` : `${ic('chev')}<button data-f="go" data-path="${esc(c.path)}" class="${i === shown.length - 1 ? 'cur' : ''}" title="${esc(c.path)}">${esc(c.label)}</button>`).join('')}</div></div>`;
    if (F.err) h += `<div class="note err">${ic('warn')}<span>${esc(F.err)}</span></div>`;
    if (F.loading) h += `<div class="state"><div class="spinner sm"></div>Opening...</div>`;
    else if (!path) {
      const drives = d.drives || [];
      h += drives.length ? `<div class="drives">${drives.map(x => `<button class="drive" data-f="go" data-path="${esc(norm(x.path || x.name))}">${ic('drive')}<div class="grow">
          <b>${esc(x.label ? `${x.label} (${String(x.name).replace(/\\$/, '')})` : x.name)}</b><span>${isNum(x.free_gb) ? gb(x.free_gb) + ' free' : ''}</span></div></button>`).join('')}</div>`
        : `<div class="state">No drives were found.</div>`;
    } else {
      const entries = d.entries || [];
      const names = new Set(entries.map(e => String(e.name).toLowerCase()));
      const here = d.is_game || (names.has('game') && names.has('data'));
      if (here) {
        h += `<div class="sug-card" style="margin-top:10px"><svg class="b" viewBox="0 0 24 36" aria-hidden="true"><use href="#i-bob"/></svg><div class="grow">
          <b>This folder is The Sims 4</b><span class="path">${esc(path)}</span></div>
          <button class="btn primary small" data-f="pick" data-path="${esc(path)}"${F.saving ? ' disabled' : ''}>${F.saving === path ? 'Saving...' : 'Select'}</button></div>`;
      }
      h += entries.length ? `<div class="folder-list">${entries.map(e => `<div class="frow${e.is_game ? ' game' : ''}">
          <button class="row-btn" data-f="go" data-path="${esc(e.path)}" title="${esc(e.path)}">${ic('folder', 'f')}<span class="name">${esc(e.name)}</span>
          ${e.hint && !e.is_game ? `<span class="tag">${esc(e.hint)}</span>` : ''}${e.is_game ? '' : ic('chev', 'c')}</button>
          ${e.is_game ? `<span class="gbadge"><svg viewBox="0 0 24 36" aria-hidden="true"><use href="#i-bob"/></svg>The Sims 4</span>
            <button class="btn primary small" data-f="pick" data-path="${esc(e.path)}"${F.saving ? ' disabled' : ''}>${F.saving === e.path ? 'Saving...' : 'Select'}</button>` : ''}
        </div>`).join('')}</div>`
        : `<div class="state">This folder has no folders inside.</div>`;
    }
    body.innerHTML = h;
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
  const t = document.createElement('div');
  t.className = 'toast ' + kind;
  t.textContent = text;
  $('#toasts').appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

async function openThing(what) {
  const r = await call('open', { what });
  toast(r.message || (r.ok ? 'Opened.' : "That couldn't be opened."), r.ok ? 'ok' : 'err');
}

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
};
(() => {
  const box = document.createElement('div');
  box.innerHTML = `<svg width="0" height="0" style="position:absolute" aria-hidden="true">${Object.entries(CC_ICONS).map(([k, d]) =>
    `<symbol id="i-cc-${k}" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${d}</g></symbol>`).join('')}</svg>`;
  document.body.appendChild(box.firstChild);
})();
const ccIc = (cat, cls = '') => ic('cc-' + (CC_ICONS[cat] ? cat : 'other'), cls);
const CC_PER = 60;
const CC_SORTS = [['name', 'Name A-Z'], ['newest', 'Newest first'], ['biggest', 'Biggest first'], ['folder', 'By folder']];
const CCB = {
  el: null, data: null, loading: false, err: '', f: { category: '', folder: '', creator: '', q: '', used: '', flag: '', sort: 'name' },
  page: 0, facets: null, sel: new Set(), scan: null, req: 0, qTimer: null,
};

// everything that needs a hook in the rest of the app
AFTER_RENDER.push(() => { if (S.page === 'library') ccMount(); });
Object.assign(TITLES, { cc_scan: () => 'Sorting CC files', cc_set_aside: () => 'Setting CC files aside' });
Object.assign(DONE, { cc_scan: () => 'CC files sorted', cc_set_aside: () => 'Files set aside' });
KIND.setaside = ['Set CC files aside', 'folder'];
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
  el.innerHTML = `<div class="card-head"><div class="ic">${ccIc('hanger')}</div><div class="grow"><h2>CC browser</h2>
      <p>All CC files, sorted into categories with pictures. Select a file to see its location and the saves that use it.</p></div>
      <div class="cc-head-right"></div></div>
    <div class="cc-progress hidden"><div class="spinner sm"></div><div class="grow"><b>Sorting CC files...</b><span class="cc-ptext"></span>
      <div class="bar-track indet"><i style="width:0"></i></div></div></div>
    <div class="cc-cats" role="tablist" aria-label="Categories"></div>
    <div class="cc-tools">
      <label class="cc-search">${ic('search')}<input id="cc-q" type="search" placeholder="Search by name, creator or folder" autocomplete="off" spellcheck="false" aria-label="Search CC files"></label>
      <select data-cc-f="folder" aria-label="Folder"><option value="">All folders</option></select>
      <select data-cc-f="creator" aria-label="Creator"><option value="">All creators</option></select>
      <select data-cc-f="used" aria-label="Used by saves"><option value="">Used or not</option><option value="used">Used in a save</option><option value="unused">Not used anywhere</option></select>
      <select data-cc-f="flag" aria-label="Problems"><option value="">All files</option><option value="duplicate">Duplicates</option><option value="broken">Damaged files</option></select>
      <select data-cc-f="sort" aria-label="Sort">${CC_SORTS.map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join('')}</select>
    </div>
    <div class="cc-bar"><span class="cc-count"></span><span class="cc-selbar"></span></div>
    <div class="cc-grid" aria-live="polite"></div>
    <div class="cc-pager"></div>`;
  CCB.el = el;
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
    CCB.err = r.message || "Your CC list couldn't be read right now.";
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
    ? `<span class="cc-when">${idx.when ? `Sorted ${esc(ago(idx.when))}` : ''}</span><button class="btn small" data-cc="scan"${off}>${ic('refresh')}Look again</button>`
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
  $('.cc-cats', el).innerHTML = !ready ? '' : [`<button class="cc-cat${CCB.f.category ? '' : ' on'}" data-cc="cat" data-key="" role="tab" aria-selected="${!CCB.f.category}">${ccIc('all')}<span>All</span></button>`]
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
  if (CCB.facets) { fill('folder', CCB.facets.folders, 'All folders'); fill('creator', CCB.facets.creators, 'All creators'); }
  ['used', 'flag', 'sort'].forEach(k => { const s = $(`[data-cc-f="${k}"]`, el); if (s) s.value = CCB.f[k] || (k === 'sort' ? 'name' : ''); });
  const used = $('[data-cc-f="used"]', el);
  used.disabled = !idx.used_known;
  used.title = idx.used_known ? 'CC worn or placed in a save, or by a household or lot in the in-game library' : 'Available after the next "Look again".';
  $('.cc-tools', el).classList.toggle('hidden', !ready);
  const grid = $('.cc-grid', el), pager = $('.cc-pager', el), count = $('.cc-count', el);
  if (!d) {
    grid.innerHTML = CCB.err ? `<div class="note err">${ic('warn')}<span>${esc(CCB.err)}</span></div>`
      : `<div class="saves-loading" style="padding:30px 4px"><div class="spinner sm"></div>Loading CC files...</div>`;
    pager.innerHTML = count.innerHTML = '';
    return;
  }
  if (!ready) {
    grid.innerHTML = `<div class="cc-empty"><div class="ic">${ccIc('all')}</div><div>
      <h3>CC files not sorted yet</h3>
      <p>Sorting reads every CC file once, finds its picture and assigns a category: hair, tops, shoes, makeup, Build/Buy and more. Duplicates, damaged files and CC that no save uses are marked too.</p>
      <p class="muted">The first run takes a few minutes for a large library. Game files are not changed.</p>
      <button class="btn primary" data-cc="scan"${busy() ? ' disabled' : ''}>${ic('search')}Sort CC files</button></div></div>`;
    pager.innerHTML = count.innerHTML = '';
    ccDrawSel();
    return;
  }
  const items = d.items || [];
  const filtered = Object.entries(CCB.f).some(([k, v]) => v && k !== 'sort');
  const from = d.total ? d.offset + 1 : 0, to = d.offset + items.length;
  count.innerHTML = d.total ? `Showing <b>${num(from)}-${num(to)}</b> of <b>${num(d.total)}</b>${filtered ? ` <button class="linkish" data-cc="clear">Clear filters</button>` : ''}`
    : '';
  grid.innerHTML = items.length ? items.map(ccCard).join('')
    : `<div class="cc-none">${ic('search')}<div><b>No CC files match these filters.</b><span>Change the search words or the category.</span></div>
       ${filtered ? `<button class="btn small" data-cc="clear">Clear filters</button>` : ''}</div>`;
  const pages = Math.max(1, Math.ceil(d.total / CC_PER)), pg = CCB.page;
  pager.innerHTML = pages < 2 ? '' : `<button class="btn small" data-cc="page" data-page="0"${pg ? '' : ' disabled'} title="First page">«</button>
    <button class="btn small" data-cc="page" data-page="${pg - 1}"${pg ? '' : ' disabled'}>${ic('back')}Back</button>
    <span>Page <b>${num(pg + 1)}</b> of ${num(pages)}</span>
    <button class="btn small" data-cc="page" data-page="${pg + 1}"${pg + 1 < pages ? '' : ' disabled'}>Next${ic('arrow')}</button>
    <button class="btn small" data-cc="page" data-page="${pages - 1}"${pg + 1 < pages ? '' : ' disabled'} title="Last page">»</button>`;
  if (CCB.err) grid.insertAdjacentHTML('afterbegin', `<div class="note err">${ic('warn')}<span>${esc(CCB.err)}</span></div>`);
  ccDrawSel();
}

const ccThumb = it => it && it.pic ? `/api/cc/thumb/${it.id}?v=${encodeURIComponent(it.pic)}` : '';

function ccCard(it) {
  const src = ccThumb(it), sel = CCB.sel.has(it.id);
  const badges = [];
  if (it.broken) badges.push(`<span class="cc-badge bad" title="${esc(it.broken)}">Damaged</span>`);
  if (it.duplicate_of) badges.push(`<span class="cc-badge dup" title="Everything in it is also in ${esc(it.duplicate_of)}">Duplicate</span>`);
  if (it.used === false) badges.push(`<span class="cc-badge" title="Not used by any save or in-game library household">Not used</span>`);
  if (!it.in_mods) badges.push(`<span class="cc-badge" title="Moved out of Mods by Quick Start or one-save mode; back with Full Start">Put away</span>`);
  const sub = [it.body && it.body !== it.category_label ? it.body : it.category_label, it.creator || it.folder].filter(Boolean).join(' · ');
  return `<div class="cc-card${sel ? ' selected' : ''}" data-id="${it.id}" data-cat="${esc(it.category)}" tabindex="0" title="${esc(it.rel || it.name)}">
    <div class="cc-pic">${src ? `<img src="${src}" alt="" loading="lazy" decoding="async" data-cat="${esc(it.category)}">` : `<div class="cc-ph">${ccIc(it.category)}</div>`}
      ${it.kind === 'script' ? '' : `<label class="cc-check" title="Select"><input type="checkbox" data-cc-sel="${it.id}"${sel ? ' checked' : ''} aria-label="Select ${esc(it.name)}"></label>`}
      ${badges.length ? `<div class="cc-badges">${badges.join('')}</div>` : ''}</div>
    <div class="cc-meta"><b>${esc(it.name.replace(/\.(package|ts4script)$/i, ''))}</b><span>${esc(sub)}</span></div></div>`;
}

function ccDrawSel() {
  if (!CCB.el) return;
  const n = CCB.sel.size;
  $('.cc-selbar', CCB.el).innerHTML = !n ? '' : `<b>${plural(n, 'file')} picked</b>
    <button class="btn small soft" data-cc="aside"${busy() || gameRunning() ? ' disabled' : ''}>${ic('folder')}Set aside</button>
    <button class="btn small ghost" data-cc="unselect">Clear</button>`;
}

// --------------------------------------------------------------- sorting (a quiet task: progress shows in the card)
async function ccScan() {
  if (busy()) { toast('Please wait - the Hub is still busy.', 'err'); return; }
  const r = await call('task', { action: 'cc_scan', args: {} });
  if (r.http === 409) { toast(r.message || 'Please wait - the Hub is still busy.', 'err'); return; }
  if (!r.ok || !r.task) { toast(r.message || "That didn't work.", 'err'); return; }
  ccWatch(r.task);
}

async function ccWatch(id) {
  S.taskId = id;
  CCB.scan = { text: 'Getting started...', frac: null };
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
    } else if (v.http === 404 || ++misses > 20) { view = { state: 'failed', result: { ok: false, message: 'The Hub stopped answering while sorting CC files.' } }; break; }
    await sleep(600);
  }
  S.taskId = null;
  CCB.scan = null;
  const res = (view && view.result) || {};
  toast(res.message || (res.ok ? 'CC files sorted.' : 'Sorting CC files did not finish.'), res.ok ? 'ok' : 'err');
  CCB.facets = null;
  refreshStatus(true);
  render();
  ccLoad(true);
}

// --------------------------------------------------------------- one file
async function ccDetails(id) {
  const m = modal(`<header><div class="ic">${ccIc('hanger')}</div><div class="grow"><h2>CC file</h2><p>Loading...</p></div>
    <button class="icon-btn" data-x title="Close">${ic('x')}</button></header><div class="body"><div class="saves-loading"><div class="spinner sm"></div>Loading...</div></div>`, { wide: true });
  $('[data-x]', m.el).onclick = () => m.close();
  const r = await call('cc/item/' + id);
  if (!document.body.contains(m.el)) return;
  if (!r.ok) { $('.body', m.el).innerHTML = `<div class="note err">${ic('warn')}<span>${esc(r.message || "That file couldn't be found.")}</span></div>`; return; }
  const src = ccThumb(r);
  const facts = [
    ['Category', r.body && r.body !== r.category_label ? `${r.category_label} (${r.body})` : r.category_label],
    r.part_name ? ['Internal name', r.part_name] : null,
    r.creator ? ['Creator (guessed from the file name)', r.creator] : null,
    ['Folder', r.folder || 'Mods (not in a folder)'],
    r.cas_parts ? ['Create a Sim items', num(r.cas_parts)] : null,
    r.objects ? ['Build/Buy objects', num(r.objects)] : null,
    ['Size', r.size_mb >= 1 ? `${r.size_mb.toFixed(1)} MB` : `${Math.max(1, Math.round(r.size_mb * 1000))} KB`],
    ['Changed', dayTime(r.modified)],
  ].filter(Boolean);
  const used = r.used === true ? `<div class="note ok">${ic('check')}<span>Used by: <b>${r.used_by.map(esc).join(', ')}</b></span></div>`
    : r.used === false ? `<div class="note">${ic('info')}<span>Not used by any save or in-game library household. Walls, floors and CC needed only by a script mod are not always detected.</span></div>` : '';
  $('header p', m.el).textContent = r.name;
  $('header h2', m.el).textContent = r.name.replace(/\.(package|ts4script)$/i, '');
  $('.body', m.el).innerHTML = `<div class="cc-detail"><div class="cc-big">${src ? `<img src="${src}" alt="" data-cat="${esc(r.category)}">` : `<div class="cc-ph">${ccIc(r.category)}</div>`}</div>
    <div class="grow"><table class="cc-facts">${facts.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')}</table>
    <div class="path" style="margin-top:10px">${esc(r.path || r.rel)}</div></div></div>
    ${used}
    ${r.broken ? `<div class="note err">${ic('warn')}<span>${esc(r.broken)}</span></div>` : ''}
    ${r.duplicate_of ? `<div class="note warn">${ic('warn')}<span>Everything in this file is also in <b>${esc(r.duplicate_of)}</b>. Only one of the two is needed.</span></div>` : ''}
    ${r.in_mods ? '' : `<div class="note">${ic('info')}<span>Moved out of the Mods folder by Quick Start or one-save mode. It is back when the game starts with Full Start.</span></div>`}`;
  const foot = document.createElement('footer');
  foot.innerHTML = `<span class="hint">${r.kind === 'script' ? 'Script mods are left alone by the Hub.' : 'Setting aside can be undone on the Tools page.'}</span>
    <button class="btn" data-open>${ic('folder')}Open folder</button>
    ${r.kind === 'script' ? '' : `<button class="btn soft" data-aside${busy() || gameRunning() || !r.in_mods ? ' disabled' : ''}>${ic('folder')}Set aside</button>`}`;
  m.el.appendChild(foot);
  $('[data-open]', foot).onclick = async () => { const o = await call('cc/open', { id }); toast(o.message || (o.ok ? 'Opened.' : "That couldn't be opened."), o.ok ? 'ok' : 'err'); };
  const aside = $('[data-aside]', foot);
  if (aside) aside.onclick = () => { m.close(); ccConfirmAside([id], r.name); };
}

async function ccConfirmAside(ids, name = '') {
  if (!ids.length) return;
  const one = ids.length === 1;
  const yes = await confirmBox({
    title: one ? 'Set this file aside?' : `Set ${plural(ids.length, 'file')} aside?`,
    text: 'The files leave the Mods folder, so the game no longer loads them. Nothing is deleted: they are kept in the safe copies folder.',
    what: `<div class="confirm-what"><b>${one && name ? esc(name) : `${plural(ids.length, 'CC file')}`}</b><span><b>Undo last change</b> on the Tools page puts them back.</span></div>`,
    ok: 'Set aside', cancel: 'Keep them',
  });
  if (!yes) return;
  const view = await runTask('cc_set_aside', { ids });
  if (view && view.result && view.result.ok) { ids.forEach(i => CCB.sel.delete(i)); }
  CCB.facets = null;
  ccLoad(true);
}

// --------------------------------------------------------------- Saves: the CC one save uses
const saveCcButton = s => `<button class="btn small ghost cc-save-btn" data-act="save-cc" data-slot="${esc(s.slot)}">${ccIc('hanger')}View CC${isNum(s.cc_missing) && s.cc_missing > 0 ? ' and missing items' : ''}</button>`;
const trayCcCard = () => `<div class="card cc-tray"><div class="card-head"><div class="ic violet">${ic('users')}</div><div class="grow"><h2>In-game library households</h2>
  <p>CC used by the households and lots saved in the in-game library, including missing items.</p></div>
  <button class="btn" data-act="save-cc" data-slot="tray">${ccIc('hanger')}View CC</button></div></div>`;
const CC_KIND_ICON = { cas: 'top', object: 'buildbuy', look: 'skin' };

function ccSaveModal(slot) {
  const save = slot === 'tray' ? { name: 'In-game library' } : (saveBySlot(slot) || { name: slot });
  const X = { tab: 'files', data: null, more: 60 };
  const m = modal(`<header><div class="ic">${ccIc('hanger')}</div><div class="grow"><h2></h2><p>Loading...</p></div>
    <button class="icon-btn" data-x title="Close">${ic('x')}</button></header>
    <div class="cc-tabs hidden" role="tablist"></div><div class="body"><div class="saves-loading"><div class="spinner sm"></div>Reading the CC this save uses. Large saves take a moment.</div></div>`, { wide: true });
  m.el.classList.add('cc-wide');
  $('h2', m.el).textContent = slot === 'tray' ? 'CC in the in-game library' : `CC in "${save.name}"`;
  $('[data-x]', m.el).onclick = () => m.close();
  const body = $('.body', m.el), tabs = $('.cc-tabs', m.el);
  const pic = (f, cls) => {
    const main = f.pic ? `/api/cc/pic/${f.pic.kind}/${f.pic.id}` : '', fb = ccThumb(f.item);
    const src = main || fb, cat = (f.item && f.item.category) || 'other';
    return `<div class="${cls}">${src ? `<img src="${src}" alt="" loading="lazy" decoding="async" data-cat="${esc(cat)}"${main && fb ? ` data-fb="${fb}"` : ''}>` : `<div class="cc-ph">${ccIc(cat)}</div>`}</div>`;
  };
  function draw() {
    const d = X.data;
    const c = d.counts || {};
    $('header p', m.el).textContent = [plural(c.files, 'CC file'), c.parts ? `${num(c.parts)} CC items worn` : '', c.objects ? `${plural(c.objects, 'object')} on lots` : '',
      c.missing ? `${num(c.missing)} missing` : 'nothing missing'].filter(Boolean).join(' · ');
    tabs.classList.remove('hidden');
    tabs.innerHTML = [['files', `CC it uses <i>${num(c.files)}</i>`], ['sims', 'By household'], ['missing', `Missing <i class="${c.missing ? 'warn' : ''}">${num(c.missing)}</i>`]]
      .map(([k, l]) => `<button role="tab" aria-selected="${X.tab === k}" class="${X.tab === k ? 'on' : ''}" data-tab="${k}">${l}</button>`).join('');
    if (X.tab === 'files') {
      const files = d.files || [];
      body.innerHTML = !files.length ? `<div class="empty">${esc(d.message || 'This save uses no CC.')}</div>`
        : `<div class="cc-grid small">${files.slice(0, X.more).map((f, n) => {
            const who = f.objects && !f.parts ? `On lots: ${plural(f.objects, 'object')}` : f.sims_count ? `Worn by ${f.sims.slice(0, 2).map(esc).join(', ')}${f.sims_count > 2 ? ` +${num(f.sims_count - 2)}` : ''}` : `${plural(f.parts + f.looks, 'item')} used`;
            return `<div class="cc-card${f.item ? '' : ' plain'}" data-file="${n}" title="${esc(f.folder ? f.folder + '/' + f.name : f.name)}">${pic(f, 'cc-pic')}
              <div class="cc-meta"><b>${esc(f.name.replace(/\.package$/i, ''))}</b><span>${esc(f.category_label || 'CC')} · ${who}</span></div></div>`;
          }).join('')}</div>${files.length > X.more ? `<div class="actions" style="justify-content:center"><button class="btn small" data-more>Show more (${num(files.length - X.more)} left)</button></div>` : ''}`;
    } else if (X.tab === 'sims') {
      const hh = d.households || [];
      body.innerHTML = !hh.length ? `<div class="empty">No sim here wears CC.</div>` : hh.map((h, i) => `<details class="cc-hh"${i < 2 || h.played ? ' open' : ''}>
          <summary>${ic('users')}<b>${esc(h.name)}</b>${h.played ? '<span class="chip hot">Played household</span>' : ''}<span class="muted">${plural(h.sims.length, 'sim')}</span></summary>
          ${h.sims.map(s => `<div class="cc-sim"><div class="who"><b>${esc(s.name)}</b><span>${plural(s.parts, 'CC item')}${s.missing ? ` · <span class="warn-t">${num(s.missing)} missing</span>` : ''}</span></div>
            <div class="cc-strip">${s.files.slice(0, 10).map(n => d.files[n] ? pic(d.files[n], 'cc-mini') : '').join('')}${s.files.length > 10 ? `<span class="more">+${num(s.files.length - 10)}</span>` : ''}</div></div>`).join('')}
        </details>`).join('');
    } else {
      const miss = d.missing || [];
      body.innerHTML = `<div class="note">${ic('info')}<span>Saves store only an ID number for each CC item. A name is shown only when a copy of the file
          is found in the safe copies or the Inbox; a picture only when the game's thumbnail cache still has one.</span></div>
        ${!miss.length ? `<div class="note ok">${ic('check')}<span>Nothing is missing. Every CC item this ${slot === 'tray' ? 'library' : 'save'} uses is installed.</span></div>`
          : `<div class="cc-missing">${miss.slice(0, X.more).map(x => `<div class="cc-miss">
              <div class="cc-mpic">${x.kind !== 'look' ? `<img src="/api/cc/pic/${x.kind === 'object' ? 'object' : 'cas'}/${x.id}" alt="" loading="lazy" data-cat="${CC_KIND_ICON[x.kind]}">` : `<div class="cc-ph">${ccIc(CC_KIND_ICON[x.kind])}</div>`}</div>
              <div class="grow"><b>${esc(x.what)}</b>
                <div class="cc-id"><code>${esc(x.id)}</code><button class="icon-btn" data-copy="${esc(x.key)}" title="Copy its full ID (type, group and number)">${ccIc('copy')}</button></div>
                ${x.sims && x.sims.length ? `<span class="muted">Worn by ${x.sims.slice(0, 4).map(esc).join(', ')}${x.sims_count > 4 ? ` and ${num(x.sims_count - 4)} more` : ''}</span>` : x.kind === 'object' ? '<span class="muted">Placed on a lot</span>' : ''}
                ${x.found && x.found.length ? x.found.map(f => `<div class="cc-found">${ic('check')}<span>${f.place === 'Inbox' ? 'In the Inbox' : 'In the safe copies'}: <b>${esc(f.name)}</b>${f.creator ? ` <span class="muted">(creator guessed from the file name: ${esc(f.creator)})</span>` : ''}</span></div>`).join('')
                  : '<div class="cc-found none">Not found on this PC. Only the ID is known.</div>'}</div></div>`).join('')}</div>
            ${miss.length > X.more ? `<div class="actions" style="justify-content:center"><button class="btn small" data-more>Show more (${num(miss.length - X.more)} left)</button></div>` : ''}`}`;
    }
  }
  m.el.addEventListener('click', async e => {
    const t = e.target.closest('[data-tab]');
    if (t) { X.tab = t.dataset.tab; X.more = 60; draw(); body.scrollTop = 0; return; }
    if (e.target.closest('[data-more]')) { X.more += 120; draw(); return; }
    const cp = e.target.closest('[data-copy]');
    if (cp) {
      try { await navigator.clipboard.writeText(cp.dataset.copy); toast('Copied: ' + cp.dataset.copy, 'ok'); }
      catch { toast(cp.dataset.copy); }
      return;
    }
    const card = e.target.closest('[data-file]');
    if (card && X.data) {
      const f = X.data.files[+card.dataset.file];
      if (f && f.item) { const o = await call('cc/open', { id: f.item.id }); toast(o.message || (o.ok ? 'Opened.' : "That couldn't be opened."), o.ok ? 'ok' : 'err'); }
    }
  });
  (async () => {
    const r = await call(`saves/${encodeURIComponent(slot)}/cc`);
    if (!document.body.contains(m.el)) return;
    if (r.http !== 200 || !r.ok) {
      $('header p', m.el).textContent = '';
      body.innerHTML = `<div class="note ${r.busy ? 'warn' : 'err'}">${ic('warn')}<span>${esc(r.message || "This save's CC couldn't be read right now.")}</span></div>`;
      return;
    }
    X.data = r;
    if (slot !== 'tray' && r.counts && r.counts.missing && !r.counts.files) X.tab = 'missing';
    draw();
    const note = (r.index || {}).state !== 'ready' ? `<span class="hint">Sort CC files on the Library page to show categories here.</span>` : '<span class="hint">Click a CC file to open its folder.</span>';
    const foot = document.createElement('footer');
    foot.innerHTML = `${note}<button class="btn primary" data-x2>Close</button>`;
    m.el.appendChild(foot);
    $('[data-x2]', foot).onclick = () => m.close();
  })();
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
      const ov = Overlay((TITLES[v.action] || (() => 'Working...'))(v.args || {}));
      ov.update(v);
      ov.finish(v);
    }
  }
  if (what === 'undo') confirmUndo();
  if (what === 'restore') confirmRestore();
  if (what === 'cleanup') { S.plan = { ok: true, copies: 4210, gb: 18.2, rewritten: 57, removed: 12 }; render(); confirmCleanup(); }
}

// patch day, game errors, save backups, load-time savings (care.js): its helpers, buttons, titles and change kinds
care.init({ call, esc, ic, render: () => render(), runTask, confirmBox, toast, busy, gameRunning, isNum, plural, ago, dayTime,
  page: () => S.page });
Object.assign(ACTS, care.ACTS);
Object.assign(TITLES, care.TITLES);
Object.assign(DONE, care.DONE);
Object.assign(KIND, care.KIND);

(async function start() {
  route();
  await refreshStatus(true);
  const cur = await call('task/current');
  if (cur.http === 200 && cur.state === 'running') {
    if (cur.action === 'cc_scan') ccWatch(cur.id); else watchTask(cur.id, { action: cur.action, args: cur.args || {} });
  }
  previewHooks();
})();
