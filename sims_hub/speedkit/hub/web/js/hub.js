// Novulon's Sims Hub - the app. A plain ES module with no libraries; it talks to speedkit/hub/server.py.

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
    case 'fast': return { key: 'FAST', title: 'Play FAST', sub: 'Only the CC your saves use is loaded.' };
    case 'full': return { key: 'ALL CC', title: 'All CC', sub: 'Every CC item you have is loaded.', cls: 'full' };
    case 'save': {
      const s = saveBySlot(p.save_slot), m = /'(.+)'\s*$/.exec(p.label || '');
      return { key: 'ONE SAVE', title: s ? s.name : m ? m[1] : 'One save', sub: 'Only the CC this save uses is loaded.' };
    }
    case 'studio': return { key: 'STUDIO', title: 'Studio mode', sub: 'Only WickedWhims and your animations are loaded.' };
    case 'custom': return { key: 'CUSTOM', title: 'Your own mix', sub: 'Your Mods folder was changed by hand or by another tool.', cls: 'full' };
    default: return { key: '…', title: p.label || 'Not known yet', sub: '' };
  }
}
const PROFILE_WORDS = { fast: 'Play FAST', full: 'All CC', save: 'One save', studio: 'Studio mode', custom: 'Your own mix' };
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
}

function render(fresh = false) {
  const page = $('#page');
  const open = !fresh && $$('details', page).map(d => d.open);      // a re-draw keeps opened sections open
  page.innerHTML = PAGES[S.page]();
  if (open) $$('details', page).forEach((d, i) => { if (open[i]) d.open = true; });
  if (fresh) {
    $('#main').scrollTop = 0;
    page.style.animation = 'none'; void page.offsetWidth; page.style.animation = '';
  }
  if (S.page === 'performance') drawChart();
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
      <h2>The Sims 4 is running</h2><p>Have fun! When you close the game, you can pick a different way to play here.</p></div></div></div>`;
  } else {
    if (!gameFound()) {
      const moved = gameMoved(g), where = gamePath(g);
      top += `<div class="state-card find"><svg class="bob" viewBox="0 0 24 36" aria-hidden="true"><use href="#i-bob"/></svg><div class="grow">
        <h2>${moved ? "The game isn't where it used to be" : "We couldn't find The Sims 4 on this PC"}</h2>
        <p>${moved ? (where ? `The game is no longer at <span class="path">${esc(where)}</span>. Show the Hub where it is now.` : esc(g.message || 'Show the Hub where it is now.'))
          : 'Show the Hub where the game is installed. You only have to do this once.'}</p></div>
        <button class="btn primary big" data-act="find-game">${ic('search')}Find my game</button></div>`;
    }
    const fastMeta = [];
    if (isNum(lib.cas_fast) && isNum(lib.cas_full)) fastMeta.push(`<span class="pill">${num(lib.cas_fast)} of ${num(lib.cas_full)} CC items</span>`);
    if (lastFast) fastMeta.push(`<span>Last time: ${dur(lastFast.launch_to_menu_s)}</span>`);
    if (fp.state === 'stale' || fp.state === 'missing') fastMeta.push(`<span>First start takes a few extra minutes to get ready</span>`);
    const fullMeta = [];
    if (isNum(lib.cas_full)) fullMeta.push(`<span class="pill">All ${num(lib.cas_full)} CC items</span>`);
    if (lastFull) fullMeta.push(`<span>Last time: ${dur(lastFull.launch_to_menu_s)}</span>`);
    top += `<div class="play-row">
      <button class="play fast" data-act="play" data-target="fast"${off}>
        <div class="top"><div class="pic">${ic('bolt-fill')}</div><div class="t">Play FAST</div></div>
        <div class="d">Loads only the CC your saves use. The game starts way faster, and your sims look the same.</div>
        <div class="m">${fastMeta.join('')}</div>
        <span class="go">${ic('play')}</span>
      </button>
      <button class="play all" data-act="play" data-target="full"${off}>
        <div class="top"><div class="pic">${ic('stack')}</div><div class="t">Play with ALL CC</div></div>
        <div class="d">Loads every CC item you have - for building, or for Create a Sim with everything.</div>
        <div class="m">${fullMeta.join('')}</div>
        <span class="go">${ic('play')}</span>
      </button></div>`;
  }

  const hour = new Date().getHours();
  const hi = hour < 5 ? 'Up late?' : hour < 12 ? 'Good morning!' : hour < 18 ? 'Hi there!' : 'Good evening!';
  const [h1, line] = gameRunning() ? ['Have fun!', "The Sims 4 is running. I'll be right here when you're done."]
    : !gameFound() ? ["Let's find your game", "I'm Novi. Show me where The Sims 4 is, and then you can play."]
    : ['Ready to play?', "I'm Novi. Pick how you want to start The Sims 4, and I'll get everything ready for you."];
  return `<div class="hello">
      <div class="novi"><img src="img/novi.svg" alt="Novi, the Sims Hub mascot"></div>
      <div><h1>${hi} <span>${esc(h1)}</span></h1><p>${esc(line)}</p></div>
    </div>
    ${top}
    <h3 class="sec">Right now</h3>
    <div class="stats">${statCards().join('')}</div>`;
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
      <button class="btn primary block" data-act="play" data-target="save:${esc(s.slot)}"${canPlay() ? '' : ' disabled'}>
        ${ic('play')}${why ? esc(why) : 'Play this save'}</button>
    </div>`;
  }).join('')}</div>`;
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

    <div class="card"><div class="card-head"><div class="ic">${ic('download')}</div><div class="grow"><h2>Add new downloads</h2>
      <p>Put the CC and mods you download into this folder. Press <b>Add them to my game</b>, and the Hub puts them in the right place, the safe way.</p></div></div>
      <div class="path-box">${ic('folder', 'fold')}<span class="path">${esc((ib && ib.inbox_path) || 'Finding your Inbox folder...')}</span>
        <button class="btn small" data-act="open" data-what="inbox">${ic('folder')}Open folder</button></div>
      ${inboxBody}
      <div class="actions"><button class="btn primary" data-act="inbox-apply"${addable.length && !noChange ? '' : ' disabled'}>${ic('check')}Add them to my game${addable.length ? ` (${num(addable.length)})` : ''}</button>
        <button class="btn ghost" data-act="inbox-refresh"${S.inboxLoading ? ' disabled' : ''}>${ic('refresh')}Look again</button></div>
    </div>

    <div class="card"><div class="card-head"><div class="ic pink">${ic('broom')}</div><div class="grow"><h2>Free up space</h2>
      <p>Some CC is stored more than once. The Hub can remove the extra copies. Your game looks exactly the same, and you can undo it on the Tools page.</p></div></div>
      ${plan && plan.ok ? `<div class="plan"><div><b>${planSize(plan)}</b><span>can be freed</span></div><div><b>${num(plan.copies)}</b><span>extra copies</span></div>
        <div><b>${num((plan.rewritten || 0) + (plan.removed || 0))}</b><span>files made smaller or removed</span></div></div>` : ''}
      <div class="actions"><button class="btn primary" data-act="cleanup-plan"${noChange ? ' disabled' : ''}>${ic('search')}${plan ? 'Check again' : 'Check how much I can free'}</button>
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
  else if (tuned) gActions = `<button class="btn ghost" data-act="gfx-restore"${noChange ? ' disabled' : ''}>${ic('undo')}Put my old graphics back</button>`;

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
    `<div class="tile"><div class="lbl"><i class="sw" style="background:var(--full)"></i>All CC, on average</div><b>${full === null ? '—' : dur(full)}</b></div>`,
    fast && full && full > fast
      ? `<div class="tile hero"><div class="lbl">${ic('bolt')}Fast start is</div><b>${(full / fast).toFixed(1).replace(/\.0$/, '')}x faster</b></div>`
      : `<div class="tile"><div class="lbl">${ic('clock')}Starts timed</div><b>${num(rows.length)}</b></div>`,
  ];
  return `<div class="tiles">${tiles.join('')}</div>
    <div class="chart" id="chart" role="img" aria-label="Start times, oldest on the left"></div>
    <div class="legend"><span><i style="background:var(--fast)"></i>Fast start (Play FAST, one save or Studio)</span><span><i style="background:var(--full)"></i>All CC</span></div>
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
  fastpack: ['Got Play FAST ready', 'bolt'], savepack: ['Got a save ready to play', 'bolt'], usedpack: ["Got your saves' CC ready", 'bolt'],
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
    title = { fast: 'Switched to Play FAST', full: 'Switched to All CC', studio: 'Switched to Studio mode', custom: 'Switched to your own mix' }[m[1].toLowerCase()]
      || 'Switched to one save';
  } else if (j.kind === 'inbox' && (m = /^(\d+) download/.exec(note))) title = `Added ${plural(+m[1], 'new download')}`;
  else if (j.kind === 'settings' && /max quality/i.test(note)) title = 'Graphics: Max Quality, lag fixed';
  else if (j.kind === 'settings' && /restore|put back/i.test(note)) title = 'Graphics: old file put back';
  else if (j.kind === 'install' && /^uninstall/i.test(note)) title = 'Removed the SpeedKit Monitor';
  else if (j.kind === 'install') title = 'Installed the SpeedKit Monitor';
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
            <div class="actions"><button class="btn primary" data-act="find-game">${ic('search')}Find my game</button></div>`}
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
  if (target === 'fast') return 'Starting Play FAST';
  if (target === 'full') return 'Starting with ALL CC';
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

(async function start() {
  route();
  await refreshStatus(true);
  const cur = await call('task/current');
  if (cur.http === 200 && cur.state === 'running') watchTask(cur.id, { action: cur.action, args: cur.args || {} });
  previewHooks();
})();
