// Novulon's Sims Hub - patch day, "which mod caused this error?", save backups & save health, load-time savings.
// hub.js imports this module, hands it its helpers (init), puts these sections into its pages and adds these buttons
// to its click table. The server routes are in speedkit/hub/care_routes.py (docs/care.md).
// Its words come from the language catalogs (i18n/<code>.json, keys care.*).
import * as I from './i18n.js';
import * as bf from './batchfix.js';           // CC that may need a Sims 4 Studio fix (Tools page)
const { t } = I;

let H = null;                                  // hub.js helpers: esc, ic, call, render, runTask, confirmBox, ...
export function init(helpers) { H = helpers; bf.init(helpers); }

// what these pages show: the last answer of each read, and what is being read now
const C = { patch: null, errors: null, health: null, savings: null, loading: new Set(), pick: null, pickKey: '' };
const READS = { patch: 'patchday', errors: 'errors', health: 'save_health', savings: 'load_savings' };
const NEEDS = { home: ['patch', 'errors', 'savings'], saves: ['health'], tools: ['patch', 'errors'] };

export async function load(page, force = false) {
  const want = NEEDS[page] || [];
  await Promise.all(want.map(k => read(k, force)).concat(page === 'tools' ? [bf.load(force)] : []));
}

async function read(key, force) {
  if (C.loading.has(key) || (C[key] && !force)) return;
  C.loading.add(key);
  const r = await H.call(READS[key] + (force ? '?refresh=1' : ''));
  C.loading.delete(key);
  if (r.busy) return;                         // a change is running: asked again when it is done
  C[key] = r.http === 200 ? r : { ok: false, message: r.message || t('care.read_error') };
  if (key === 'patch') resetPick();
  if ((NEEDS[H.page()] || []).includes(key)) H.render();
}

// a finished task may have changed any of these
export function afterTask() {
  C.patch = C.errors = C.health = C.savings = null;
  bf.reset();
  load(H.page(), true);
}

// a new language: what the server said is asked for again
export function forget() {
  C.patch = C.errors = C.health = C.savings = null;
  C.loading.clear();
  bf.reset();
}

const noChange = () => H.busy() || H.gameRunning();
const esc = v => H.esc(v);
const ic = (id, cls) => H.ic(id, cls);

// "41 min", "2 min", "45 s", "1 h 5 min" - load times, rounded the way people say them
function mins(s) {
  if (!H.isNum(s)) return '—';
  s = Math.round(Number(s));
  if (s < 90) return t('unit.s', { n: s });
  const m = Math.round(s / 60);
  return m < 60 ? t('unit.min', { n: m }) : t('unit.h_min', { h: Math.floor(m / 60), m: m % 60 });
}
const MODE = { fast: 'mode.quick', save: 'mode.save', full: 'mode.full', studio: 'mode.studio', other: 'mode.other' };
const modeName = m => t(MODE[m] || 'mode.other');
const fileOf = rel => String(rel || '').split('/').pop();

// -------------------------------------------------------------------------------- Home
export function homeBanner() {
  const p = C.patch, out = [];
  if (p && p.ok && p.game && p.game.updated) {
    const n = (p.older || []).length;
    out.push(`<div class="care-banner" data-care="patch-banner"><div class="ic warn">${ic('warn')}</div><div class="grow">
      <b>${esc(p.game.version ? t('care.patch.updated_to', { version: p.game.version }) : t('care.patch.updated'))}</b>
      <span>${esc(n ? t('care.patch.older', { n }) : t('care.patch.all_newer'))}</span>${bf.patchLine(p.batch_fixes)}</div>
      ${n ? `<a class="btn small primary" href="#tools" data-care-scroll="care-patch">${ic('search')}${esc(t('care.patch.review'))}</a>` : ''}
      <button class="btn small ghost" data-act="care-patch-seen">${esc(t('care.dismiss'))}</button></div>`);
  }
  const e = C.errors;
  const fresh = e && e.ok ? (e.errors || []).filter(g => g.new) : [];
  if (fresh.length) {
    const named = fresh.filter(g => g.mod).length;
    out.push(`<div class="care-banner soft" data-care="errors-banner"><div class="ic pink">${ic('bug')}</div><div class="grow">
      <b>${esc(t('care.errors.new', { n: fresh.length }))}</b>
      <span>${esc(named ? t('care.errors.named', { named, n: fresh.length }) : t('care.errors.none_named'))}</span></div>
      <a class="btn small" href="#tools" data-care-scroll="care-errors">${ic('arrow')}${esc(t('care.errors.view'))}</a></div>`);
  }
  return out.join('');
}

// the note under the load-time bars: how far the numbers can be trusted (the same rules as speedkit/loadstats.py)
function savingsNote(r, modes) {
  if (r.confidence === 'none') return t('care.load.none');
  if (r.confidence === 'one_mode') return t(modes.full && H.isNum(modes.full.total_s) ? 'care.load.try_quick' : 'care.load.try_full');
  if (H.isNum(r.saved_s) && r.saved_s <= 0) return t('care.load.not_quicker');
  if (r.confidence === 'low') return t('care.load.few');
  return '';
}

export function homeSavings() {
  const r = C.savings;
  if (!r || !r.ok) return '';
  const modes = r.modes || {};
  const shown = ['fast', 'save', 'full', 'studio'].filter(m => modes[m] && H.isNum(modes[m].total_s));
  let body;
  if (!shown.length) {
    body = `<div class="empty" style="padding:12px 2px 0">${esc(t('care.load.none'))}</div>`;
  } else {
    const max = Math.max(...shown.map(m => modes[m].total_s));
    body = `<div class="care-bars">${shown.map(m => {
      const d = modes[m], w = Math.max(2, d.total_s / max * 100);
      return `<div class="care-bar"><span class="lbl">${esc(modeName(m))}</span>
        <span class="track"><i class="${m === 'full' ? 'full' : m === 'studio' ? 'studio' : ''}" style="width:${w.toFixed(1)}%"></i></span>
        <b>${esc(mins(d.total_s))}</b><small>${esc(t('care.load.starts', { n: Number(d.starts) || 0 }))}</small></div>`;
    }).join('')}</div>`;
    if (H.isNum(r.saved_s) && r.saved_s > 0) {
      body += `<div class="care-saved">${ic('bolt')}<div><b>${esc(t('care.load.saved', { mode: modeName(r.compare || 'fast'), time: mins(r.saved_s) }))}</b>
        ${H.isNum(r.saved_total_s) && r.saved_total_s >= 120 ? `<span>${esc(t('care.load.saved_total', { time: mins(r.saved_total_s) }))}</span>` : ''}</div></div>`;
    }
    const note = savingsNote(r, modes);
    if (r.confidence !== 'ok' && note) body += `<div class="note">${ic('info')}<span>${esc(note)}</span></div>`;
  }
  return `<h3 class="sec">${esc(t('care.load.section'))}</h3>
    <div class="card care-load" data-care="savings"><div class="card-head"><div class="ic blue">${ic('clock')}</div><div class="grow">
      <h2>${esc(t('care.load.title'))}</h2><p>${esc(t('care.load.text'))}</p></div></div>
      ${body}</div>`;
}

// -------------------------------------------------------------------------------- Saves
function healthOf(slot) {
  const x = C.health;
  return x && x.ok ? (x.saves || []).find(s => s.slot === slot || s.file === slot + '.save') : null;
}

const LEVEL = { growing: 'care.size.growing', very_big: 'care.size.very_big', big: 'care.size.big' };

export function saveLine(save) {
  const x = healthOf(save.slot);
  if (!x) return '';
  const size = t('unit.mb', { v: I.num(Math.round(x.size_mb)) });
  const grow = H.isNum(x.growth_mb) && x.growth_mb >= 1
    ? ' · ' + t('care.size.grew', { mb: t('unit.mb', { v: I.num(Math.round(x.growth_mb)) }), n: Number(x.growth_days) || 0 }) : '';
  const warn = x.level !== 'ok';
  return `<div class="care-size${warn ? ' warn' : ''}" title="${esc(x.note || '')}">${ic(warn ? 'warn' : 'saves')}<span>${esc(size + grow)}</span>
    ${warn ? `<span class="chip warn">${esc(t(LEVEL[x.level] || 'care.size.big'))}</span>` : ''}</div>`;
}

// why a backup was made (the engine's reason words) -> catalog key
const REASON = { 'by hand': 'care.backup.by_hand', 'before restore': 'care.backup.before_restore', 'before setting mods aside': 'care.backup.before_aside' };
const size = b => H.isNum(b) ? (b >= 1e9 ? t('unit.gb', { v: I.num(b / 1e9, 1) }) : t('unit.mb', { v: I.num(Math.max(1, Math.round(b / 1e6))) })) : '—';

export function savesSection() {
  const x = C.health;
  let body;
  if (!x) body = `<div class="saves-loading" style="padding:16px 4px"><div class="spinner sm"></div>${esc(t('care.backup.loading'))}</div>`;
  else if (!x.ok) body = `<div class="note err">${ic('warn')}<span>${esc(x.message)}</span></div>`;
  else {
    const list = x.backups || [];
    const warn = (x.saves || []).filter(s => s.level !== 'ok');
    body = (warn.length ? warn.map(s => `<div class="note warn">${ic('warn')}<span><b>${esc(s.name)}</b>: ${esc(s.note)}</span></div>`).join('') : '')
      + (list.length ? `<div class="care-list">${list.map(b => `<div class="care-row" data-backup="${esc(b.id)}">
          <div class="ci">${ic('shield')}</div><div class="grow"><b>${esc(H.dayTime(b.when))}</b>
          <span>${esc([t(REASON[H.en(b, 'reason')] || 'care.backup.backup'), t('care.backup.saves', { n: Number(b.files) || 0 }), size(b.bytes), H.ago(b.when)].join(' · '))}</span></div>
          ${b.complete ? `<button class="btn small" data-act="care-restore" data-backup="${esc(b.id)}"${noChange() ? ' disabled' : ''}>${ic('undo')}${esc(t('care.backup.restore'))}</button>`
            : `<span class="chip warn">${esc(t('care.backup.incomplete'))}</span>`}</div>`).join('')}</div>`
        : `<div class="empty" style="padding:12px 2px 0">${esc(t('care.backup.none'))}</div>`);
  }
  return `<div class="card care-backups" style="margin-top:22px" data-care="backups"><div class="card-head"><div class="ic green">${ic('shield')}</div><div class="grow">
      <h2>${esc(t('care.backup.title'))}</h2><p>${esc(t('care.backup.text', { n: x && x.keep ? Number(x.keep) : 5 }))}</p></div>
      <button class="btn primary" data-act="care-backup"${noChange() ? ' disabled' : ''}>${ic('shield')}${esc(t('care.backup.now'))}</button></div>
      ${body}</div>`;
}

// -------------------------------------------------------------------------------- Tools
function resetPick() {
  const p = C.patch;
  const key = p && p.ok ? (p.older || []).map(o => o.rel).join('|') : '';
  if (key === C.pickKey && C.pick) return;
  C.pickKey = key;
  // on patch day every older script is ticked; otherwise none (the list is just for looking)
  C.pick = new Set(p && p.ok && p.game && p.game.updated ? (p.older || []).map(o => o.rel) : []);
}

const asideLabel = n => `${ic('pause')}${esc(t('care.patch.aside_btn'))}${n ? ` (${I.num(n)})` : ''}`;

function patchCard() {
  const p = C.patch;
  let body;
  if (!p) body = `<div class="saves-loading" style="padding:16px 4px"><div class="spinner sm"></div>${esc(t('care.patch.loading'))}</div>`;
  else if (!p.ok) body = `<div class="note err">${ic('warn')}<span>${esc(p.message)}</span></div>`;
  else {
    if (!C.pick) resetPick();
    const g = p.game || {}, older = p.older || [], aside = p.set_aside || [];
    const head = g.updated
      ? [g.version ? t('care.patch.now_version', { version: g.version }) : t('care.patch.updated'), g.update_time ? H.ago(g.update_time) : ''].filter(Boolean).join(' · ')
      : g.version ? t('care.patch.version', { version: g.version }) : t('app.game');
    const status = `<div class="care-status${g.updated ? ' hot' : ''}">${ic(g.updated ? 'warn' : 'check')}<div>
        <b>${esc(head)}</b>
        <span>${esc(p.message)}</span>${g.updated ? bf.patchLine(p.batch_fixes) : ''}</div></div>`;
    const rows = older.map(o => {
      const bits = [fileOf(o.rel), t('care.patch.from', { date: H.day(o.date), n: Number(o.days_before) || 0 })];
      if ((o.goes_with || []).length) bits.push(t('care.patch.goes_with', { n: o.goes_with.length }));
      return `<label class="care-row pick"><input type="checkbox" data-care-pick="${esc(o.rel)}"${C.pick.has(o.rel) ? ' checked' : ''}>
        <div class="ci">${ic('terminal')}</div><div class="grow"><b title="${esc(o.rel)}">${esc(o.mod)}</b>
        <span>${esc(bits.join(' · '))}</span></div></label>`;
    }).join('');
    const n = older.filter(o => C.pick.has(o.rel)).length;
    const listBlock = older.length ? `<div class="care-list">${rows}</div>
      <div class="actions"><button class="btn primary" data-act="care-aside" data-care-count${n && !noChange() ? '' : ' disabled'}>${asideLabel(n)}</button>
        <button class="btn ghost small" data-act="care-pick-all">${esc(t(n === older.length ? 'care.patch.select_none' : 'care.patch.select_all'))}</button></div>
      <div class="note">${ic('info')}<span>${esc(t('care.patch.note'))}</span></div>` : '';
    body = status + (older.length ? (g.updated ? listBlock
      : `<details class="more care-more"><summary>${esc(t('care.patch.show_older', { n: older.length }))}</summary>${listBlock}</details>`) : '');
    if (aside.length) {
      body += `<h3 class="sec" style="margin:22px 0 8px">${esc(t('care.patch.aside_title'))} <span class="n">${I.num(aside.length)}</span></h3><div class="care-list">${aside.map(x => {
        const why = { error: 'care.patch.aside_error', fix: 'care.patch.aside_fix' }[x.why] || 'care.patch.aside_update';
        const bits = [fileOf(x.rel), t(why, { ago: H.ago(x.since) })];
        if (x.state === 'updated') bits.push(t('care.patch.newer_copy'));
        return `<div class="care-row">
        <div class="ci">${ic('pause')}</div><div class="grow"><b title="${esc(x.rel)}">${esc(x.mod)}</b>
        <span>${esc(bits.join(' · '))}</span></div>
        ${x.state === 'aside' ? `<button class="btn small" data-act="care-back" data-rel="${esc(x.rel)}"${noChange() ? ' disabled' : ''}>${ic('undo')}${esc(t('care.put_back'))}</button>` : `<span class="chip ok">${esc(t('care.patch.updated_chip'))}</span>`}</div>`;
      }).join('')}</div>`;
    }
  }
  return `<div class="card" id="care-patch" data-care="patch"><div class="card-head"><div class="ic warn">${ic('pause')}</div><div class="grow">
      <h2>${esc(t('care.patch.title'))}</h2><p>${esc(t('care.patch.text'))}</p></div>
      <button class="btn small ghost" data-act="care-refresh" title="${esc(t('common.look_again'))}">${ic('refresh')}</button></div>${body}</div>`;
}

function errorRow(g) {
  const m = g.mod;
  const who = `<b>${esc(m ? (g.how === 'named' ? m.name : t('care.error.probably', { name: m.name })) : t('care.error.no_mod'))}</b>`;
  const hint = m ? (m.root !== 'Mods' && !g.set_aside ? `${m.file} · ${t('care.error.already_aside')}` : m.file)
    : t(g.kind === 'ui' ? 'care.error.ui' : 'care.error.game');
  const act = m && g.set_aside ? `<span class="chip ok">${ic('check')}${esc(t('care.error.set_aside'))}</span>`
    : m && m.can_set_aside ? `<button class="btn small soft" data-act="care-error-aside" data-rel="${esc(m.rel)}" data-name="${esc(m.name)}"${noChange() ? ' disabled' : ''}>${ic('pause')}${esc(t('care.error.aside_btn'))}</button>` : '';
  const meta = [H.ago(g.last)];
  if (g.count > 1) meta.push(t('care.error.times', { n: Number(g.count), date: H.day(g.first) }));
  if (g.how === 'mentioned') meta.push(t('care.error.mentioned'));
  return `<div class="care-error${g.new ? ' new' : ''}" data-error="${esc(g.id)}"><div class="top"><div class="ci">${ic(g.kind === 'ui' ? 'image' : 'bug')}</div>
      <div class="grow">${who}<span>${esc(hint)}</span></div>${act}</div>
    <div class="what">${esc(g.error)}</div>
    <div class="meta">${esc(meta.join(' · '))}</div>
    <details class="more"><summary>${esc(t('care.error.details'))}</summary><pre class="care-raw">${esc(g.details)}</pre>
      <div class="muted" style="font-size:12px;margin-top:6px">${esc(t('care.error.from', { files: (g.files || []).join(', ') }))}</div></details></div>`;
}

function errorsCard() {
  const e = C.errors;
  let body;
  if (!e) body = `<div class="saves-loading" style="padding:16px 4px"><div class="spinner sm"></div>${esc(t('care.errors.loading'))}</div>`;
  else if (!e.ok) body = `<div class="note err">${ic('warn')}<span>${esc(e.message)}</span></div>`;
  else {
    const all = e.errors || [], fresh = all.filter(g => g.new), old = all.filter(g => !g.new);
    body = `<div class="care-status${fresh.length ? ' hot' : ''}">${ic(fresh.length ? 'bug' : 'check')}<div><b>${esc(e.message)}</b>
      <span>${esc(t(all.length ? 'care.errors.order' : 'care.errors.empty'))}</span></div></div>`;
    if (fresh.length) body += `<div class="care-errors">${fresh.map(errorRow).join('')}</div>`;
    if (old.length) body += `<details class="more care-more"><summary>${esc(t('care.errors.seen_list', { n: old.length }))}</summary><div class="care-errors">${old.map(errorRow).join('')}</div></details>`;
    if (fresh.length) body += `<div class="actions"><button class="btn small" data-act="care-errors-seen">${ic('check')}${esc(t('care.errors.mark_seen'))}</button></div>`;
  }
  return `<div class="card" id="care-errors" data-care="errors"><div class="card-head"><div class="ic pink">${ic('bug')}</div><div class="grow">
      <h2>${esc(t('care.errors.title'))}</h2><p>${esc(t('care.errors.text'))}</p></div>
      <button class="btn small ghost" data-act="care-refresh" title="${esc(t('common.look_again'))}">${ic('refresh')}</button></div>${body}</div>`;
}

export function toolsSections() {
  return `<div class="care-tools">${patchCard()}${bf.card()}${errorsCard()}</div>`;
}

// -------------------------------------------------------------------------------- the progress window
export const TITLES = {
  set_aside: a => t({ error: 'care.task.aside_one', fix: 'care.task.aside_fix' }[a.why] || 'care.task.aside'),
  put_back: () => t('care.task.put_back'), backup_saves: () => t('care.task.backup'), restore_saves: () => t('care.task.restore'),
  ...bf.TITLES,
};
export const DONE = {
  set_aside: () => t('care.done.aside'), put_back: () => t('care.done.put_back'), backup_saves: () => t('care.done.backup'),
  restore_saves: () => t('care.done.restore'), ...bf.DONE,
};
export const KIND = { aside: ['care.kind.aside', 'pause'], saves: ['care.kind.saves', 'shield'] };

// -------------------------------------------------------------------------------- buttons
function picked() {
  const p = C.patch;
  return p && p.ok ? (p.older || []).filter(o => C.pick && C.pick.has(o.rel)) : [];
}

async function setAside() {
  const list = picked();
  if (!list.length) return;
  const extra = list.reduce((a, o) => a + (o.goes_with || []).length, 0);
  const names = list.slice(0, 6).map(o => o.mod);
  const yes = await H.confirmBox({
    title: t('care.aside.title', { n: list.length }),
    text: esc(t('care.aside.text')),
    what: `<div class="confirm-what"><b>${esc(list.length > 6 ? t('care.aside.names_more', { names: names.join(', '), n: list.length - 6 }) : names.join(', '))}</b>
      <span>${esc([extra ? t('care.aside.extra', { n: extra }) : '', t('care.aside.undo')].filter(Boolean).join(' '))}</span></div>`,
    ok: t('care.aside.ok'), cancel: t('common.cancel'),
  });
  if (yes) H.runTask('set_aside', { rels: list.map(o => o.rel), why: 'patch' });
}

async function errorAside(btn) {
  const name = btn.dataset.name, rel = btn.dataset.rel;
  const yes = await H.confirmBox({
    title: t('care.aside_one.title', { name }),
    text: esc(t('care.aside_one.text')),
    what: `<div class="confirm-what"><b>${esc(fileOf(rel))}</b><span>${esc(t('care.aside_one.what'))}</span></div>`,
    ok: t('care.aside_one.ok'), cancel: t('common.cancel'),
  });
  if (yes) H.runTask('set_aside', { rels: [rel], why: 'error' });
}

async function restore(btn) {
  const b = ((C.health && C.health.backups) || []).find(x => x.id === btn.dataset.backup);
  if (!b) return;
  const yes = await H.confirmBox({
    title: t('care.restore.title'), danger: true,
    text: esc(t('care.restore.text', { date: H.dayTime(b.when) })),
    what: `<div class="confirm-what"><b>${esc((b.saves || []).slice(0, 5).map(s => s.save_name || s.name).join(', '))}</b>
      <span>${esc(t('care.restore.what'))}</span></div>`,
    ok: t('care.restore.ok'), cancel: t('common.cancel'),
  });
  if (yes) H.runTask('restore_saves', { backup: b.id });
}

async function seen(route, key) {
  const r = await H.call(route, {});
  if (!r.ok) { H.toast(r.message || t('common.failed'), 'err'); return; }
  await read(key, true);
  H.render();
}

export const ACTS = {
  'care-patch-seen': () => seen('patchday/seen', 'patch'),
  'care-errors-seen': () => seen('errors/seen', 'errors'),
  'care-aside': () => setAside(),
  'care-error-aside': btn => errorAside(btn),
  'care-back': btn => H.runTask('put_back', { rels: [btn.dataset.rel] }),
  'care-backup': () => H.runTask('backup_saves'),
  'care-restore': btn => restore(btn),
  'care-refresh': () => load(H.page(), true),
  ...bf.ACTS,
  'care-pick-all': () => {
    const older = (C.patch && C.patch.older) || [];
    const all = older.every(o => C.pick.has(o.rel));
    C.pick = new Set(all ? [] : older.map(o => o.rel));
    H.render();
  },
};

// ticking a mod updates the button without drawing the page again; a link to a section scrolls to it
document.addEventListener('change', e => {
  const box = e.target.closest && e.target.closest('[data-care-pick]');
  if (!box || !C.pick) return;
  if (box.checked) C.pick.add(box.dataset.carePick); else C.pick.delete(box.dataset.carePick);
  const n = picked().length, btn = document.querySelector('[data-care-count]');
  if (btn) {
    btn.disabled = !n || noChange();
    btn.innerHTML = asideLabel(n);
  }
});
document.addEventListener('click', e => {
  const a = e.target.closest && e.target.closest('[data-care-scroll]');
  if (!a) return;
  const id = a.dataset.careScroll;
  setTimeout(() => { const el = document.getElementById(id); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 250);
});
