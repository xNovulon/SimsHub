// Game Doctor ("Check my game - why don't my animations show up?") and "Did it play in the game?" (R1-E).
//
//   openDoctor(app)                         the full dialog: a radar sweep while it scans, then green / yellow / red
//                                           cards, each with one safe button (Park this file, Turn back on, ...)
//   didItPlayPanel(app, {project, since})   the "Play it in the game, then come back" line with Check now and the
//                                           "what to look at" list (fills the Send result's extraSlot)
//   openDidItPlay(app, opts)                the same in its own dialog (palette command)
//   checkPending(app)                       after a send: when the window comes back, look once for the result
//
// The server side is backend/doctor.py + gamelog.py (routes doctor_scan, doctor_status, doctor_fix, game_log,
// game_running). Nothing here changes a file without a click, and every change goes through doctor_fix.
import * as ui from './ui.js';

const { h, icon, modal, toast } = ui;
const reduced = () => (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  || document.documentElement.classList.contains('reduce-motion');

// ---------------------------------------------------------------- server
async function j(url, opts) {
  const r = await fetch(url, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const err = new Error(body.error || r.statusText || ('HTTP ' + r.status));
    err.status = r.status;
    throw err;
  }
  return body;
}
const post = (url, data) => j(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

export const doctorApi = {
  scan: (force = false) => j('/api/doctor_scan' + (force ? '?force=1' : '')),
  status: () => j('/api/doctor_status'),
  fix: body => post('/api/doctor_fix', body),
  gameLog: q => j('/api/game_log?' + new URLSearchParams(Object.entries(q).filter(([, v]) => v !== undefined && v !== null && v !== ''))),
  running: () => j('/api/game_running'),
  reveal: path => post('/api/reveal', { path }),
};
const OLD_ENGINE = 'This needs the newest engine - close Wicked Animator and open it again.';

// ---------------------------------------------------------------- icons (added once to the app's sprite sheet)
const ICONS = {
  doctor: '<path d="M12 2.5 5.2 12 12 21.5 18.8 12z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="M6.8 12h2.6l1.3-2.6 2 5.4 1.4-2.8h3.1" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'doc-alert': '<path d="M12 3.2 2.8 19.5h18.4z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="M12 9.5v4.4" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><circle cx="12" cy="16.9" r="1.1" fill="currentColor"/>',
  'doc-info': '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M12 11v5.5" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><circle cx="12" cy="7.8" r="1.1" fill="currentColor"/>',
  'doc-stop': '<path d="M8.3 3h7.4L21 8.3v7.4L15.7 21H8.3L3 15.7V8.3z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="M12 7.6v5.2" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><circle cx="12" cy="16" r="1.1" fill="currentColor"/>',
  'doc-ok': '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="m7.8 12.3 2.9 2.9 5.6-6.2" stroke="currentColor" stroke-width="1.9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'doc-park': '<path d="M4 8.5h16v10.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 19z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="M3 4.5h18v4H3zM10 12.5h4" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round" stroke-linecap="round"/>',
  'doc-power': '<path d="M12 3v8" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><path d="M7 6.3a7.5 7.5 0 1 0 10 0" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>',
  'doc-game': '<path d="M12 2.5 7.8 9.3 12 12.4 16.2 9.3z" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round"/><path d="M7.8 9.3 12 21.5l4.2-12.2" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round"/>',
  'doc-tongue': '<path d="M4 9.5c2.5 2.6 13.5 2.6 16 0" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round"/><path d="M8.5 11.3v3.2a3.5 3.5 0 0 0 7 0v-3.2M12 12v3" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round"/>',
  'doc-feet': '<path d="M7.5 3.5c2 0 3 2.2 3 5.5s-.7 6.3-2.3 8.5c-1 1.4-3.2.9-3.4-1-.4-3.9-.6-6.1-.3-8.6.3-2.6 1.2-4.4 3-4.4z" stroke="currentColor" stroke-width="1.6" fill="none"/><path d="M3 20.5h18" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M15 9.5c1.6 0 2.6 1.6 2.6 4.2s-.6 4.5-1.8 5.6" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/>',
  'doc-hand': '<path d="M8 12.5V5.8a1.4 1.4 0 0 1 2.8 0V11m0-1.5V4.4a1.4 1.4 0 0 1 2.8 0v5.8m0-.7V5.9a1.4 1.4 0 0 1 2.8 0v6.4m0-2.1a1.4 1.4 0 0 1 2.8 0v3.9c0 4-2.6 6.9-6.6 6.9-2.6 0-4.3-1.2-5.8-3.4l-2.1-3.3a1.4 1.4 0 0 1 2.3-1.6L8 13.5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
};
export function ensureIcons() {
  for (const [id, svg] of Object.entries(ICONS)) {
    if (document.getElementById('i-' + id)) continue;
    if (typeof ui.addIcon === 'function') ui.addIcon(id, svg);
    if (document.getElementById('i-' + id)) continue;
    const sheet = document.querySelector('svg[aria-hidden="true"]');           // fallback: straight into the sprite
    if (!sheet) continue;
    const sym = document.createElementNS('http://www.w3.org/2000/svg', 'symbol');
    sym.id = 'i-' + id; sym.setAttribute('viewBox', '0 0 24 24'); sym.innerHTML = svg;
    sheet.append(sym);
  }
}
export function ensureStyles() {
  if (document.querySelector('link[href$="css/doctor.css"]')) return;
  document.head.append(h('link', { rel: 'stylesheet', href: 'css/doctor.css', 'data-feature': 'css/doctor.css' }));
}

// ---------------------------------------------------------------- the doctor dialog
const LEVELS = [
  ['red', 'Needs a fix', 'doc-stop'],
  ['yellow', 'Worth a look', 'doc-alert'],
  ['info', 'Good to know', 'doc-info'],
  ['green', 'All good', 'doc-ok'],
];
const LEVEL_ICON = Object.fromEntries(LEVELS.map(([k, , ic]) => [k, ic]));
const MIN_SWEEP = 1100;              // the radar sweeps at least this long, so a cached (instant) scan still reads as one

const hash = s => { let x = 2166136261; for (const c of String(s)) x = Math.imul(x ^ c.charCodeAt(0), 16777619); return x >>> 0; };
const gb = n => (n >= 1e9 ? (n / 1e9).toFixed(n >= 1e11 ? 0 : 1) + ' GB' : n >= 1e6 ? (n / 1e6).toFixed(0) + ' MB' : Math.max(1, Math.round(n / 1e3)) + ' KB');
const plural = (n, one, many = one + 's') => `${n} ${n === 1 ? one : many}`;

let openDlg = null;

export function openDoctor(app) {
  ensureIcons(); ensureStyles();
  if (openDlg && openDlg.dialog.isConnected) return openDlg;
  const ctx = { app, simsDir: '', els: new Map(), sections: {}, timer: 0, closed: false, fixed: 0, t0: 0 };

  // -- head: radar + status
  const radar = h('div', { class: 'doc-radar', 'aria-hidden': 'true' },
    h('div', { class: 'doc-radar-grid', html: '<svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="57"/><circle cx="60" cy="60" r="39"/><circle cx="60" cy="60" r="21"/><path d="M60 3v114M3 60h114"/></svg>' }),
    h('div', { class: 'doc-sweep' }),
    h('div', { class: 'doc-blips' }),
    h('div', { class: 'doc-core' }, h('div', { class: 'doc-core-in' }, icon('doctor'))));
  const phase = h('div', { class: 'doc-phase', role: 'status', 'aria-live': 'polite' }, 'Getting ready...');
  const bar = h('div', { class: 'doc-bar' }, h('i'));
  const tally = h('div', { class: 'doc-tally' });
  const meta = h('div', { class: 'doc-meta' }, 'Read-only: nothing in your Mods changes unless you press a button.');
  const head = h('div', { class: 'doc-top' }, radar, h('div', { class: 'doc-head' }, phase, bar, tally, meta));
  const list = h('div', { class: 'doc-list' });
  for (const [lv, label] of LEVELS) {
    const count = h('span', { class: 'doc-sec-n' });
    const sec = h('section', { class: `doc-sec lv-${lv} empty` }, h('div', { class: 'doc-sec-h' }, h('span', { class: 'doc-dot' }), label, count), h('div', { class: 'doc-sec-list' }));
    ctx.sections[lv] = { el: sec, list: sec.lastChild, count };
    list.append(sec);
  }
  const note = h('div', { class: 'doc-err hidden' });
  const body = h('div', { class: 'doc' }, head, note, list);
  Object.assign(ctx, { radar, phase, bar, tally, meta, note, list });

  const dlg = modal({
    title: 'Check my game',
    text: "Why don't my animations show up? A safe look at your Mods folder and WickedWhims' settings.",
    body, wide: true,
    buttons: [
      { label: 'Rescan', kind: 'ghost', onClick: () => { start(ctx, true); return false; } },
      { label: 'Done', kind: 'primary' },
    ],
    onClose: () => { ctx.closed = true; clearTimeout(ctx.timer); openDlg = null; },
  });
  dlg.dialog.classList.add('doc-modal');
  openDlg = dlg;
  ctx.dlg = dlg;
  start(ctx, false);
  return dlg;
}

async function start(ctx, force) {
  clearTimeout(ctx.timer);
  ctx.t0 = performance.now();
  ctx.done = false;
  ctx.note.classList.add('hidden');
  if (force) {                                    // a Rescan starts over, with the sweep and the cards dropping in again
    for (const el of ctx.els.values()) el.remove();
    ctx.els.clear();
    ctx.radar.querySelector('.doc-blips').innerHTML = '';
    ctx.fixed = 0;
  }
  ctx.radar.classList.add('scanning');
  ctx.radar.classList.remove('done', 'lv-red', 'lv-yellow', 'lv-green');
  ctx.bar.classList.remove('full');
  ctx.bar.firstChild.style.transform = '';
  ctx.dlg.dialog.classList.add('doc-scanning');
  let st;
  try { st = await doctorApi.scan(force); } catch (e) { return fail(ctx, e); }
  poll(ctx, st);
}

function fail(ctx, e) {
  ctx.radar.classList.remove('scanning');
  ctx.dlg.dialog.classList.remove('doc-scanning');
  ctx.note.classList.remove('hidden');
  ctx.note.textContent = e && e.status === 404 ? OLD_ENGINE : 'The check could not run: ' + ((e && e.message) || e);
  ctx.phase.textContent = 'The check stopped';
}

async function poll(ctx, st) {
  if (ctx.closed) return;
  ctx.simsDir = st.sims_dir || ctx.simsDir;
  apply(ctx, st.cards || [], true);
  const total = st.total || 0, done = st.done || 0;
  if (st.running || performance.now() - ctx.t0 < (reduced() ? 0 : MIN_SWEEP)) {
    ctx.phase.textContent = st.running ? (st.text || 'Checking...') : 'Putting it all together...';
    const p = st.running ? (total ? 0.08 + 0.9 * (done / total) : 0.06) : 1;
    ctx.bar.firstChild.style.transform = `scaleX(${Math.max(0.03, Math.min(1, p)).toFixed(3)})`;
    ctx.timer = setTimeout(async () => {
      let next;
      try { next = st.running ? await doctorApi.status() : st; } catch (e) { return fail(ctx, e); }
      poll(ctx, next);
    }, st.running ? 160 : 90);
    return;
  }
  if (st.phase === 'error') return fail(ctx, new Error(st.error || 'unknown problem'));
  finish(ctx, st);
}

function finish(ctx, st) {
  ctx.done = true;
  apply(ctx, st.cards || [], false, true);
  ctx.radar.classList.remove('scanning');
  ctx.radar.classList.add('done');
  ctx.dlg.dialog.classList.remove('doc-scanning');
  ctx.bar.firstChild.style.transform = 'scaleX(1)';
  ctx.bar.classList.add('full');
  const s = st.summary || {};
  headline(ctx);
  const files = (s.mods_files || 0), parked = s.parked_packages || 0;
  ctx.meta.textContent = `${plural(files, 'file')} in Mods${parked ? ` + ${plural(parked, 'set-aside package')}` : ''}${s.bytes ? ` · ${gb(s.bytes)}` : ''} checked in ${(st.seconds || 0).toFixed(1)} s. Nothing was changed.`;
}

// The big line and the radar's centre: what is left to fix (solved cards no longer count).
function headline(ctx) {
  const n = lv => [...ctx.els.values()].filter(el => el.dataset.level === lv && !el.classList.contains('resolved')).length;
  const red = n('red'), yellow = n('yellow');
  ctx.radar.classList.remove('lv-red', 'lv-yellow', 'lv-green');
  ctx.radar.classList.add(red ? 'lv-red' : yellow ? 'lv-yellow' : 'lv-green');
  const core = ctx.radar.querySelector('.doc-core-in');
  core.innerHTML = '';
  if (red || yellow) core.append(h('b', {}, String(red || yellow)), h('small', {}, red ? 'to fix' : 'to check'));
  else core.append(icon('check'));
  ctx.phase.textContent = red ? `${plural(red, 'thing')} ${red === 1 ? 'needs' : 'need'} a fix` : yellow ? `${plural(yellow, 'thing')} worth a look`
    : ctx.fixed ? 'All fixed - restart The Sims 4 to see it' : 'Everything looks good';
}

// Put the cards on screen: new ones drop in (with a blip on the radar), changed ones update in place, gone ones go.
function apply(ctx, cards, animate, final = false) {
  const seen = new Set();
  let batch = 0;
  for (const c of cards) {
    seen.add(c.id);
    const json = JSON.stringify(c);
    let el = ctx.els.get(c.id);
    if (!el) {
      el = cardEl(ctx, c);
      ctx.els.set(c.id, el);
      if (animate && !reduced()) {
        el.style.setProperty('--i', batch++);
        el.classList.add('drop');
        el.addEventListener('animationend', () => el.classList.remove('drop'), { once: true });
        blip(ctx, c);
      }
      ctx.sections[c.level]?.list.append(el);
    } else if (el._json !== json && !el.classList.contains('busy') && !el.classList.contains('resolved')) {
      const fresh = cardEl(ctx, c);
      el.replaceWith(fresh);
      ctx.els.set(c.id, fresh);
      el = fresh;
      if (el.parentNode !== ctx.sections[c.level]?.list) ctx.sections[c.level]?.list.append(el);
    }
  }
  if (final) {
    for (const [id, el] of ctx.els) if (!seen.has(id) && !el.classList.contains('resolved')) { el.remove(); ctx.els.delete(id); }
    for (const c of cards) { const el = ctx.els.get(c.id); if (el && !el.classList.contains('drop')) ctx.sections[c.level]?.list.append(el); }
  }
  tallyUp(ctx);
}

function tallyUp(ctx) {
  const counts = { red: 0, yellow: 0, info: 0, green: 0 };
  for (const el of ctx.els.values()) if (!el.classList.contains('resolved')) counts[el.dataset.level] = (counts[el.dataset.level] || 0) + 1;
  for (const [lv] of LEVELS) {
    const s = ctx.sections[lv];
    const k = s.list.children.length;
    s.el.classList.toggle('empty', !k);
    s.count.textContent = k ? String(k) : '';
  }
  ctx.tally.innerHTML = '';
  const chip = (lv, n, word) => h('span', { class: `doc-chip lv-${lv}` + (n ? '' : ' zero') }, h('i'), h('b', {}, String(n)), word);
  ctx.tally.append(chip('red', counts.red, 'need a fix'), chip('yellow', counts.yellow, 'worth a look'), chip('green', counts.green + counts.info, 'fine'));
  if (ctx.fixed) ctx.tally.append(h('span', { class: 'doc-chip fixed' }, icon('check'), `${ctx.fixed} fixed`));
}

function blip(ctx, c) {
  const host = ctx.radar.querySelector('.doc-blips');
  if (host.children.length > 24) return;
  const k = hash(c.id), a = (k % 360) * Math.PI / 180, r = 16 + ((k >> 9) % 30);
  host.append(h('i', { class: `doc-blip lv-${c.level}`, style: { left: `${50 + r * Math.cos(a)}%`, top: `${50 + r * Math.sin(a)}%` } }));
}

function cardEl(ctx, c) {
  const el = h('article', { class: `doc-card lv-${c.level}`, 'data-id': c.id, 'data-level': c.level, 'data-need': c.need || null });
  el._json = JSON.stringify(c);
  const main = h('div', { class: 'doc-main' }, h('h4', {}, c.title), c.text ? h('p', {}, c.text) : null);
  if (c.items && c.items.length) {
    main.append(h('ul', { class: 'doc-items' }, c.items.map(it => {
      const row = h('li', { class: 'doc-item' }, h('div', { class: 'doc-item-t' }, h('b', {}, it.label), it.detail ? h('small', {}, it.detail) : null));
      if (it.action) row.append(actionButton(ctx, it.action, el, row));
      return row;
    })));
  }
  if (c.lines && c.lines.length) {
    const names = h('div', { class: 'doc-names hidden' });
    main.append(h('ul', { class: 'doc-lines' }, c.lines.map(l => h('li', { class: l.never === false ? 'note' : l.never ? 'never' : '' },
      h('span', {}, l.label), l.detail ? h('small', {}, l.detail) : null))));
    if (c.lines.some(l => l.names && l.names.length)) {
      for (const l of c.lines) if (l.names && l.names.length) names.append(h('div', { class: 'doc-names-g' }, h('b', {}, l.label), h('span', {}, l.names.join(' · '))));
      main.append(names);
    }
  }
  el.append(h('div', { class: 'doc-ico' }, icon(LEVEL_ICON[c.level] || 'doc-info')), main);
  if (c.action) el.append(h('div', { class: 'doc-act' }, actionButton(ctx, c.action, el, null)));
  return el;
}

function actionButton(ctx, a, card, row) {
  // the one fix a problem card offers stands out; on a "good to know" card it stays quiet
  const kind = (a.kind === 'park' || a.kind === 'enable') && card.dataset.level !== 'info' ? 'soft' : 'ghost';
  const ic = { park: 'doc-park', enable: 'doc-power', reveal: 'folder', details: 'eye' }[a.kind] || 'arrow';
  const b = h('button', { class: `btn small ${kind} doc-btn`, type: 'button', 'data-kind': a.kind }, icon(ic), a.label);
  b.addEventListener('click', () => runAction(ctx, a, card, row, b));
  return b;
}

async function runAction(ctx, a, card, row, btn) {
  if (a.kind === 'details') {
    const names = card.querySelector('.doc-names');
    if (!names) return;
    const open = names.classList.toggle('hidden') === false;
    btn.lastChild.textContent = open ? 'Hide the list' : a.label;
    return;
  }
  if (a.kind === 'reveal') {
    const path = (ctx.simsDir ? ctx.simsDir + '\\Mods\\' : '') + String(a.file || '').replace(/\//g, '\\');
    try { await doctorApi.reveal(path); } catch (e) { toast("Couldn't open that folder: " + e.message, 'err'); }
    return;
  }
  const busyText = a.kind === 'park' ? 'Parking...' : 'Turning on...';
  const old = btn.lastChild.textContent;
  btn.disabled = true; btn.lastChild.textContent = busyText;
  card.classList.add('busy');
  card.querySelector('.doc-warn')?.remove();
  let r;
  try {
    r = await doctorApi.fix(a.kind === 'park' ? { action: 'park', file: a.file } : { action: 'enable', file: a.file, list: a.list, entry: a.entry });
  } catch (e) {
    r = { ok: false, error: e.status === 404 ? OLD_ENGINE : 'That did not work: ' + e.message };
  }
  card.classList.remove('busy');
  if (!r || !r.ok) {
    btn.disabled = false; btn.lastChild.textContent = old;
    card.querySelector('.doc-main').append(h('div', { class: 'doc-warn' }, icon('doc-alert'), (r && r.error) || 'That did not work.'));
    return;
  }
  const done = h('span', { class: 'doc-done' }, icon('check'), a.kind === 'park' ? 'Parked' : 'Turned back on');
  btn.replaceWith(done);
  (row || card).classList.add('fixed');
  // solved once enough files are parked (a clash of two bodies needs one), or when every safe button was used
  card._fixed = (card._fixed || 0) + 1;
  const need = +card.dataset.need || 0;
  if ((need && card._fixed >= need) || !card.querySelector('.doc-btn[data-kind="park"], .doc-btn[data-kind="enable"]')) card.classList.add('resolved');
  ctx.fixed++;
  tallyUp(ctx);
  if (ctx.done) headline(ctx);
  toast(r.text || 'Done.', 'ok');
}

// ---------------------------------------------------------------- "Did it play in the game?"
const LIMB_WORDS = { handL: 'left hand', handR: 'right hand', footL: 'left foot', footR: 'right foot', hips: 'hips', head: 'head' };

// What to look at in the game, each with the frame to go back to.
export function lookItems(p) {
  const items = [];
  const sims = (p && p.sims) || [];
  let tongue = null, face = null, pin = null;
  for (const s of sims) {
    for (const k of s.keys || []) {
      const f = k.face || {};
      const tb = k.faceBones ? Object.keys({ ...(k.faceBones.rot || {}), ...(k.faceBones.pos || {}) }).some(b => /toun?gue/i.test(b)) : false;
      const t = Math.max(+f.tongue || 0, tb ? 0.5 : 0);
      if (t > 0 && (!tongue || t > tongue.v)) tongue = { v: t, frame: k.frame, sim: s };
      const e = Object.entries(f).reduce((a, [n, v]) => a + (n === 'tongue' ? 0 : Math.abs(+v || 0)), 0) + (k.faceBones ? 0.3 : 0);
      if (e > 0 && (!face || e > face.v)) face = { v: e, frame: k.frame, sim: s };
    }
    for (const [limb, v] of Object.entries(s.pins || {})) {
      if (!v) continue;
      const f = Array.isArray(v) ? 0 : +(v.from ?? 0) || 0;
      if (!pin || f < pin.frame) pin = { frame: f, sim: s, limb };
    }
  }
  items.push({ id: 'tongue', icon: 'doc-tongue', label: 'The tongue',
    sub: tongue ? `${tongue.sim.label} sticks it out here` : 'It stays inside the mouth', frame: tongue ? tongue.frame : 0, simId: tongue && tongue.sim.id });
  items.push({ id: 'face', icon: 'face', label: 'The face',
    sub: face ? `${face.sim.label}'s strongest expression` : 'Eyes and mouth look natural', frame: face ? face.frame : 0, simId: face && face.sim.id });
  items.push({ id: 'holds', icon: 'doc-hand', label: 'Hands that hold on',
    sub: pin ? `${pin.sim.label}'s ${LIMB_WORDS[pin.limb] || pin.limb} stays in place` : 'Hands on the partner, not through them', frame: pin ? pin.frame : 0, simId: pin && pin.sim.id });
  const bed = /bed/i.test(String(p && p.furniture || '')) || ((p && p.locations) || []).some(l => /BED/.test(l));
  items.push({ id: 'feet', icon: 'doc-feet', label: bed ? 'Feet on the bed' : 'Feet on the floor',
    sub: 'Not sinking in or floating above it', frame: 0, simId: null });
  return items;
}

function jumpTo(app, it, fromEl) {
  try {
    if (it.simId && app.selectSim) app.selectSim(it.simId);
    if (app.setFrame) app.setFrame(it.frame);
    if (app.step && ['share', 'details', 'library'].includes(app.step) && app.showStep) app.showStep('pose');
  } catch (e) { console.error(e); }
  const back = fromEl && fromEl.closest('.backdrop');
  if (back) back.querySelector('.modal-x')?.click();
  toast(`Frame ${it.frame} - fix it here, then Send to game again.`);
}

const fmtClock = x => x.clock || (x.time ? new Date(x.time * 1000).toTimeString().slice(0, 5) : '');
// the name and creator the game shows (the exporter's own fallbacks for an empty one)
const gameNames = p => ({ name: String((p && p.name) || '').trim() || 'My animation', author: String((p && p.author) || '').trim() || 'Fit Studio' });

// The line under a Send result (and in its own dialog): Check now -> "Played in the game ✓ (21:04)" or the problem.
export function didItPlayPanel(app, { project = null, since = null, look = true } = {}) {
  ensureIcons(); ensureStyles();
  const p = project || (app && app.store && app.store.project) || {};
  const result = h('div', { class: 'dip-result', role: 'status', 'aria-live': 'polite' });
  const btn = h('button', { class: 'btn small soft dip-check', type: 'button' }, icon('search'), 'Check now');
  const el = h('div', { class: 'dip' },
    h('div', { class: 'dip-row' },
      h('div', { class: 'dip-ico' }, icon('doc-game')),
      h('div', { class: 'dip-text' }, h('b', {}, 'Did it play in the game?'),
        h('span', {}, "Play it in the game, then come back - we read WickedWhims' log and tell you if it played.")),
      btn),
    result);
  if (look) {
    const rows = lookItems(p).map(it => h('li', { class: 'dip-look-row' },
      h('span', { class: 'dip-look-ic' }, icon(it.icon)),
      h('span', { class: 'dip-look-t' }, h('b', {}, it.label), h('small', {}, `${it.sub} · frame ${it.frame}`)),
      h('button', { class: 'btn small ghost dip-jump', type: 'button', onclick: e => jumpTo(app, it, e.currentTarget) }, 'Looked wrong → take me to that frame')));
    el.append(h('div', { class: 'dip-look' }, h('div', { class: 'dip-look-h' }, 'What to look at in the game'), h('ul', {}, rows)));
  }
  btn.addEventListener('click', () => check());
  async function check() {
    btn.disabled = true; btn.lastChild.textContent = 'Reading the log...';
    el.classList.add('checking');
    let r;
    try {
      r = await doctorApi.gameLog({ ...gameNames(p), since: since || '' });
    } catch (e) {
      r = { error: e.status === 404 ? OLD_ENGINE : e.message };
    }
    el.classList.remove('checking');
    btn.disabled = false; btn.lastChild.textContent = 'Check again';
    showResult(result, r, p);
  }
  el.check = check;
  return el;
}

function showResult(box, r, p) {
  box.innerHTML = '';
  box.className = 'dip-result in';
  if (r.error) { box.append(h('div', { class: 'dip-msg warn' }, icon('doc-alert'), r.error)); return; }
  const played = r.played || [], problems = r.problems || [];
  if (played.length) {
    const last = played[played.length - 1];
    box.append(h('div', { class: 'dip-msg ok' }, h('span', { class: 'dip-tick' }, icon('check')),
      h('div', {}, h('b', {}, `Played in the game ✓ (${fmtClock(last)})`),
        last.sims && last.sims.length ? h('small', {}, last.sims.join(' + ') + (played.length > 1 ? ` · ${played.length} times` : '')) : null)));
  }
  for (const x of problems.slice(0, 6)) {
    box.append(h('div', { class: 'dip-msg ' + (x.kind === 'moment' ? 'warn' : 'bad') }, icon(x.kind === 'moment' ? 'doc-alert' : 'doc-stop'),
      h('div', {}, h('b', {}, x.text), x.name && x.name.toLowerCase() !== gameNames(p).name.toLowerCase() ? h('small', {}, `"${x.name}"`) : null)));
  }
  if (played.length || problems.length) return;
  let text;
  if (!r.exists) text = "WickedWhims' log isn't there yet. Start The Sims 4 once with WickedWhims, then press Check now.";
  else if (r.running) text = `The Sims 4 is running. Play "${gameNames(p).name}", then press Check now again.`;
  else text = `Not played yet. Start The Sims 4 (restart it if it was open), play "${gameNames(p).name}", then press Check now.`;
  box.append(h('div', { class: 'dip-msg wait' }, icon('doc-info'), text));
}

export function openDidItPlay(app, { project = null, since = null } = {}) {
  const p = project || app.store.project;
  const panel = didItPlayPanel(app, { project: p, since: since ?? sentAt(p) });
  const dlg = modal({ title: 'Did it play in the game?', text: `"${p.name || 'Your animation'}"${p.author ? ' by ' + p.author : ''}`, body: panel, buttons: [{ label: 'Done', kind: 'primary' }] });
  dlg.dialog.classList.add('dip-modal');
  panel.check();
  return dlg;
}

// ---------------------------------------------------------------- after "Send to game"
const PENDING = 'fsa.doctor.pending';
const store = {
  get() { try { return JSON.parse(localStorage.getItem(PENDING) || 'null'); } catch { return null; } },
  set(v) { try { v ? localStorage.setItem(PENDING, JSON.stringify(v)) : localStorage.removeItem(PENDING); } catch { /* private mode */ } },
};
function sentAt(p) {
  const x = store.get();
  const g = gameNames(p);
  return x && p && ((x.uid && x.uid === p.uid) || (x.name === g.name && x.author === g.author)) ? x.since : null;
}

// wa:sent -> the "Did it play?" line at the bottom of the Send result
export function onSent(app, detail) {
  const p = (detail && detail.project) || (app && app.store && app.store.project);
  if (!p) return;
  const since = Math.floor(Date.now() / 1000) - 5;
  store.set({ uid: p.uid || null, ...gameNames(p), since, at: Date.now(), told: false });
  const slot = detail && detail.extraSlot;
  if (slot && slot.isConnected !== false) {
    slot.innerHTML = '';
    slot.append(didItPlayPanel(app, { project: p, since }));
  }
}

// When the window comes back after a send: look once; tell only when there is news.
let lastAuto = 0;
export async function checkPending(app) {
  const x = store.get();
  if (!x || x.told || Date.now() - x.at > 12 * 3600e3 || Date.now() - lastAuto < 15000) return;
  if (document.querySelector('#modal-root .backdrop:not(.leaving) .dip')) return;        // its own line is on screen
  lastAuto = Date.now();
  let r;
  try { r = await doctorApi.gameLog({ author: x.author || '', name: x.name || '', since: x.since, running: 0 }); } catch { return; }
  const played = r.played || [], problems = r.problems || [];
  if (!played.length && !problems.length) return;
  store.set({ ...x, told: true });
  const p = { name: x.name, author: x.author, uid: x.uid };
  const show = () => { const cur = app.store && app.store.project; openDidItPlay(app, { project: cur && cur.uid === x.uid ? cur : p, since: x.since }); };
  const text = played.length ? `"${x.name}" played in the game ✓ (${fmtClock(played[played.length - 1])})` : `"${x.name}": ${problems[0].text}`;
  if (typeof ui.choiceBar === 'function') ui.choiceBar(text, [{ label: played.length ? 'What to look at' : 'Show me', primary: true, onClick: show }], { timeout: 16000 });
  else toast(text, played.length ? 'ok' : 'err');
}
