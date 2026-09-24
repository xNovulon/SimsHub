// Novulon's Sims Hub - patch day, "which mod caused this error?", save backups & save health, load-time savings.
// hub.js imports this module, hands it its helpers (init), puts these sections into its pages and adds these buttons
// to its click table. The server routes are in speedkit/hub/care_routes.py (docs/care.md).

let H = null;                                  // hub.js helpers: $, esc, ic, call, render, runTask, confirmBox, ...
export function init(helpers) { H = helpers; }

// what these pages show: the last answer of each read, and what is being read now
const C = { patch: null, errors: null, health: null, savings: null, loading: new Set(), pick: null, pickKey: '' };
const READS = { patch: 'patchday', errors: 'errors', health: 'save_health', savings: 'load_savings' };
const NEEDS = { home: ['patch', 'errors', 'savings'], saves: ['health'], tools: ['patch', 'errors'] };

export async function load(page, force = false) {
  const want = NEEDS[page] || [];
  await Promise.all(want.map(k => read(k, force)));
}

async function read(key, force) {
  if (C.loading.has(key) || (C[key] && !force)) return;
  C.loading.add(key);
  const r = await H.call(READS[key] + (force ? '?refresh=1' : ''));
  C.loading.delete(key);
  if (r.busy) return;                         // a change is running: asked again when it is done
  C[key] = r.http === 200 ? r : { ok: false, message: r.message || "This couldn't be read right now." };
  if (key === 'patch') resetPick();
  if ((NEEDS[H.page()] || []).includes(key)) H.render();
}

// a finished task may have changed any of these
export function afterTask() {
  C.patch = C.errors = C.health = C.savings = null;
  load(H.page(), true);
}

const noChange = () => H.busy() || H.gameRunning();
const esc = v => H.esc(v);
const ic = (id, cls) => H.ic(id, cls);

// "41 min", "2 min", "45 s", "1 h 5 min" - load times, rounded the way people say them
function mins(s) {
  if (!H.isNum(s)) return '—';
  s = Math.round(Number(s));
  if (s < 90) return `${s} s`;
  const m = Math.round(s / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}
const MODE = { fast: 'Play FAST', save: 'One save', full: 'All CC', studio: 'Studio mode', other: 'Other' };
const fileOf = rel => String(rel || '').split('/').pop();

// -------------------------------------------------------------------------------- Home
export function homeBanner() {
  const p = C.patch, out = [];
  if (p && p.ok && p.game && p.game.updated) {
    const n = (p.older || []).length;
    out.push(`<div class="care-banner" data-care="patch-banner"><div class="ic warn">${ic('warn')}</div><div class="grow">
      <b>The Sims 4 was updated${p.game.version ? ` (${esc(p.game.version)})` : ''}</b>
      <span>${n ? `${H.plural(n, 'script mod')} ${n === 1 ? 'is' : 'are'} older than the latest game update. Game updates often break script mods.`
        : 'All script mods are newer than the latest game update.'}</span></div>
      ${n ? `<a class="btn small primary" href="#tools" data-care-scroll="care-patch">${ic('search')}Review script mods</a>` : ''}
      <button class="btn small ghost" data-act="care-patch-seen">Dismiss</button></div>`);
  }
  const e = C.errors;
  const fresh = e && e.ok ? (e.errors || []).filter(g => g.new) : [];
  if (fresh.length) {
    const named = fresh.filter(g => g.mod).length;
    out.push(`<div class="care-banner soft" data-care="errors-banner"><div class="ic pink">${ic('bug')}</div><div class="grow">
      <b>${H.plural(fresh.length, 'new game error')}</b>
      <span>${named ? `Mod identified for ${named} of ${fresh.length}.` : 'No mod identified.'}</span></div>
      <a class="btn small" href="#tools" data-care-scroll="care-errors">${ic('arrow')}View errors</a></div>`);
  }
  return out.join('');
}

export function homeSavings() {
  const r = C.savings;
  if (!r || !r.ok) return '';
  const modes = r.modes || {};
  const shown = ['fast', 'save', 'full', 'studio'].filter(m => modes[m] && H.isNum(modes[m].total_s));
  let body;
  if (!shown.length) {
    body = `<div class="empty" style="padding:12px 2px 0">${esc(r.message)}</div>`;
  } else {
    const max = Math.max(...shown.map(m => modes[m].total_s));
    body = `<div class="care-bars">${shown.map(m => {
      const d = modes[m], w = Math.max(2, d.total_s / max * 100);
      return `<div class="care-bar"><span class="lbl">${esc(MODE[m])}</span>
        <span class="track"><i class="${m === 'full' ? 'full' : m === 'studio' ? 'studio' : ''}" style="width:${w.toFixed(1)}%"></i></span>
        <b>${mins(d.total_s)}</b><small>${H.plural(d.starts, 'start')}</small></div>`;
    }).join('')}</div>`;
    if (H.isNum(r.saved_s) && r.saved_s > 0) {
      body += `<div class="care-saved">${ic('bolt')}<div><b>${esc(MODE[r.compare] || 'Play FAST')}: about ${mins(r.saved_s)} less per start than All CC</b>
        ${H.isNum(r.saved_total_s) && r.saved_total_s >= 120 ? `<span>${mins(r.saved_total_s)} saved in total so far.</span>` : ''}</div></div>`;
    }
    if (r.confidence !== 'ok') body += `<div class="note">${ic('info')}<span>${esc(r.message)}</span></div>`;
  }
  return `<h3 class="sec">Loading times</h3>
    <div class="card care-load" data-care="savings"><div class="card-head"><div class="ic blue">${ic('clock')}</div><div class="grow">
      <h2>How long the game takes to load</h2><p>Time from pressing Play to the main menu, plus loading the save. Measured by the SpeedKit Monitor; typical value per mode.</p></div></div>
      ${body}</div>`;
}

// -------------------------------------------------------------------------------- Saves
function healthOf(slot) {
  const h = C.health;
  return h && h.ok ? (h.saves || []).find(s => s.slot === slot || s.file === slot + '.save') : null;
}

export function saveLine(save) {
  const h = healthOf(save.slot);
  if (!h) return '';
  const grow = H.isNum(h.growth_mb) && h.growth_mb >= 1 ? ` · grew ${Math.round(h.growth_mb)} MB in ${H.plural(h.growth_days, 'day')}` : '';
  const warn = h.level !== 'ok';
  return `<div class="care-size${warn ? ' warn' : ''}" title="${esc(h.note || '')}">${ic(warn ? 'warn' : 'saves')}<span>${esc(Math.round(h.size_mb))} MB${esc(grow)}</span>
    ${warn ? `<span class="chip warn">${h.level === 'growing' ? 'Growing fast' : h.level === 'very_big' ? 'Very big' : 'Getting big'}</span>` : ''}</div>`;
}

const REASON = { 'by hand': 'Made manually', 'before restore': 'Made just before a restore', 'before setting mods aside': 'Made on patch day, before mods were set aside' };
const mb = b => H.isNum(b) ? (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(b / 1e6))} MB`) : '—';

export function savesSection() {
  const h = C.health;
  let body;
  if (!h) body = `<div class="saves-loading" style="padding:16px 4px"><div class="spinner sm"></div>Looking at your backups...</div>`;
  else if (!h.ok) body = `<div class="note err">${ic('warn')}<span>${esc(h.message)}</span></div>`;
  else {
    const list = h.backups || [];
    const warn = (h.saves || []).filter(s => s.level !== 'ok');
    body = (warn.length ? warn.map(s => `<div class="note warn">${ic('warn')}<span><b>${esc(s.name)}</b>: ${esc(s.note)}</span></div>`).join('') : '')
      + (list.length ? `<div class="care-list">${list.map(b => `<div class="care-row" data-backup="${esc(b.id)}">
          <div class="ci">${ic('shield')}</div><div class="grow"><b>${esc(H.dayTime(b.when))}</b>
          <span>${esc(REASON[b.reason] || 'Backup')} · ${H.plural(b.files, 'save')} · ${mb(b.bytes)} · ${esc(H.ago(b.when))}</span></div>
          ${b.complete ? `<button class="btn small" data-act="care-restore" data-backup="${esc(b.id)}"${noChange() ? ' disabled' : ''}>${ic('undo')}Restore these saves</button>`
            : `<span class="chip warn">Incomplete</span>`}</div>`).join('')}</div>`
        : `<div class="empty" style="padding:12px 2px 0">No backups yet. A backup copies the saves; it never changes them.</div>`);
  }
  return `<div class="card care-backups" style="margin-top:22px" data-care="backups"><div class="card-head"><div class="ic green">${ic('shield')}</div><div class="grow">
      <h2>Save backups</h2><p>Copies of every save, stored outside the game's folders. The newest ${h && h.keep ? h.keep : 5} backups are kept,
      and one is made automatically before patch-day changes. Save contents are never changed.</p></div>
      <button class="btn primary" data-act="care-backup"${noChange() ? ' disabled' : ''}>${ic('shield')}Back up now</button></div>
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

function patchCard() {
  const p = C.patch;
  let body;
  if (!p) body = `<div class="saves-loading" style="padding:16px 4px"><div class="spinner sm"></div>Checking your game's version...</div>`;
  else if (!p.ok) body = `<div class="note err">${ic('warn')}<span>${esc(p.message)}</span></div>`;
  else {
    if (!C.pick) resetPick();
    const g = p.game || {}, older = p.older || [], aside = p.set_aside || [];
    const status = `<div class="care-status${g.updated ? ' hot' : ''}">${ic(g.updated ? 'warn' : 'check')}<div>
        <b>${g.updated ? `Updated${g.version ? ` to ${esc(g.version)}` : ''}${g.update_time ? ` · ${esc(H.ago(g.update_time))}` : ''}`
          : g.version ? `The Sims 4 ${esc(g.version)}` : 'The Sims 4'}</b>
        <span>${esc(p.message)}</span></div></div>`;
    const rows = older.map(o => `<label class="care-row pick"><input type="checkbox" data-care-pick="${esc(o.rel)}"${C.pick.has(o.rel) ? ' checked' : ''}>
        <div class="ci">${ic('terminal')}</div><div class="grow"><b title="${esc(o.rel)}">${esc(o.mod)}</b>
        <span>${esc(fileOf(o.rel))} · from ${esc(H.dayTime(o.date).split(',')[0])}, ${H.plural(o.days_before, 'day')} before the update${(o.goes_with || []).length ? ` · ${H.plural(o.goes_with.length, 'file')} that go${o.goes_with.length === 1 ? 'es' : ''} with it` : ''}</span></div></label>`).join('');
    const n = older.filter(o => C.pick.has(o.rel)).length;
    const listBlock = older.length ? `<div class="care-list">${rows}</div>
      <div class="actions"><button class="btn primary" data-act="care-aside" data-care-count${n && !noChange() ? '' : ' disabled'}>${ic('pause')}Set these aside until they're updated${n ? ` (${n})` : ''}</button>
        <button class="btn ghost small" data-act="care-pick-all">${n === older.length ? 'Select none' : 'Select all'}</button></div>
      <div class="note">${ic('info')}<span>An older file does not prove that a mod is broken, and a newer file does not prove that it is fixed. Setting a mod aside
        deletes nothing: the game stops loading it until it is put back or the change is undone.</span></div>` : '';
    body = status + (older.length ? (g.updated ? listBlock
      : `<details class="more care-more"><summary>Show the ${H.plural(older.length, 'script mod')} older than the last update</summary>${listBlock}</details>`) : '');
    if (aside.length) {
      body += `<h3 class="sec" style="margin:22px 0 8px">Set aside for now <span class="n">${aside.length}</span></h3><div class="care-list">${aside.map(h => `<div class="care-row">
        <div class="ci">${ic('pause')}</div><div class="grow"><b title="${esc(h.rel)}">${esc(h.mod)}</b>
        <span>${esc(fileOf(h.rel))} · set aside ${esc(H.ago(h.since))}${h.why === 'error' ? ' because of an error' : ' after an update'}${h.state === 'updated' ? ' · a newer copy is in your Mods folder now' : ''}</span></div>
        ${h.state === 'aside' ? `<button class="btn small" data-act="care-back" data-rel="${esc(h.rel)}"${noChange() ? ' disabled' : ''}>${ic('undo')}Put back</button>` : '<span class="chip ok">Updated</span>'}</div>`).join('')}</div>`;
    }
  }
  return `<div class="card" id="care-patch" data-care="patch"><div class="card-head"><div class="ic warn">${ic('pause')}</div><div class="grow">
      <h2>After a game update</h2><p>Game updates often break script mods until their creators release updates. Script mods older than the latest game update are listed here.</p></div>
      <button class="btn small ghost" data-act="care-refresh" title="Look again">${ic('refresh')}</button></div>${body}</div>`;
}

function errorRow(g) {
  const m = g.mod;
  const who = m ? (g.how === 'named' ? `<b>${esc(m.name)}</b>` : `<b>Probably ${esc(m.name)}</b>`)
    : `<b>No mod named</b>`;
  const hint = m ? `${esc(m.file)}${m.root !== 'Mods' && !g.set_aside ? ' · already set aside' : ''}`
    : g.kind === 'ui' ? "An error in the game's menus. Mods that change the menus can cause these." : 'The cause may be the game itself, or a mod that changes the game\'s files.';
  const act = m && g.set_aside ? `<span class="chip ok">${ic('check')}Set aside</span>`
    : m && m.can_set_aside ? `<button class="btn small soft" data-act="care-error-aside" data-rel="${esc(m.rel)}" data-name="${esc(m.name)}"${noChange() ? ' disabled' : ''}>${ic('pause')}Set ${esc(m.name)} aside</button>` : '';
  return `<div class="care-error${g.new ? ' new' : ''}" data-error="${esc(g.id)}"><div class="top"><div class="ci">${ic(g.kind === 'ui' ? 'image' : 'bug')}</div>
      <div class="grow">${who}<span>${hint}</span></div>${act}</div>
    <div class="what">${esc(g.error)}</div>
    <div class="meta">${esc(H.ago(g.last))}${g.count > 1 ? ` · ${g.count} times since ${esc(H.dayTime(g.first).split(',')[0])}` : ''}${g.how === 'mentioned' ? ' · the report mentions this mod; it is not certain to be the cause' : ''}</div>
    <details class="more"><summary>Technical details (for the mod's creator)</summary><pre class="care-raw">${esc(g.details)}</pre>
      <div class="muted" style="font-size:12px;margin-top:6px">From ${esc((g.files || []).join(', '))}</div></details></div>`;
}

function errorsCard() {
  const e = C.errors;
  let body;
  if (!e) body = `<div class="saves-loading" style="padding:16px 4px"><div class="spinner sm"></div>Reading the game's error reports...</div>`;
  else if (!e.ok) body = `<div class="note err">${ic('warn')}<span>${esc(e.message)}</span></div>`;
  else {
    const all = e.errors || [], fresh = all.filter(g => g.new), old = all.filter(g => !g.new);
    body = `<div class="care-status${fresh.length ? ' hot' : ''}">${ic(fresh.length ? 'bug' : 'check')}<div><b>${esc(e.message)}</b>
      <span>${all.length ? 'Newest first. Repeated errors are shown once, with how often they happened.' : 'Error reports written by the game are read here.'}</span></div></div>`;
    if (fresh.length) body += `<div class="care-errors">${fresh.map(errorRow).join('')}</div>`;
    if (old.length) body += `<details class="more care-more"><summary>Errors marked as seen (${old.length})</summary><div class="care-errors">${old.map(errorRow).join('')}</div></details>`;
    if (fresh.length) body += `<div class="actions"><button class="btn small" data-act="care-errors-seen">${ic('check')}Mark as seen</button></div>`;
  }
  return `<div class="card" id="care-errors" data-care="errors"><div class="card-head"><div class="ic pink">${ic('bug')}</div><div class="grow">
      <h2>Which mod caused this error?</h2><p>The game writes an error report when something goes wrong. Each error is matched to the mod behind it, where possible.</p></div>
      <button class="btn small ghost" data-act="care-refresh" title="Look again">${ic('refresh')}</button></div>${body}</div>`;
}

export function toolsSections() {
  return `<div class="care-tools">${patchCard()}${errorsCard()}</div>`;
}

// -------------------------------------------------------------------------------- the progress window
export const TITLES = {
  set_aside: a => a.why === 'error' ? 'Setting the mod aside' : 'Setting mods aside', put_back: () => 'Putting mods back',
  backup_saves: () => 'Backing up saves', restore_saves: () => 'Restoring saves',
};
export const DONE = {
  set_aside: () => 'Set aside', put_back: () => 'Mods put back', backup_saves: () => 'Saves backed up',
  restore_saves: () => 'Saves restored',
};
export const KIND = { aside: ['Set mods aside', 'pause'], saves: ['Put back saves from a backup', 'shield'] };

// -------------------------------------------------------------------------------- buttons
function picked() {
  const p = C.patch;
  return p && p.ok ? (p.older || []).filter(o => C.pick && C.pick.has(o.rel)) : [];
}

async function setAside() {
  const list = picked();
  if (!list.length) return;
  const extra = list.reduce((a, o) => a + (o.goes_with || []).length, 0);
  const yes = await H.confirmBox({
    title: `Set ${H.plural(list.length, 'script mod')} aside?`,
    text: 'The game stops loading them until they are put back. The saves are backed up first.',
    what: `<div class="confirm-what"><b>${list.slice(0, 6).map(o => esc(o.mod)).join(', ')}${list.length > 6 ? ` and ${list.length - 6} more` : ''}</b>
      <span>${extra ? `${H.plural(extra, 'file')} that belong${extra === 1 ? 's' : ''} to them go${extra === 1 ? 'es' : ''} too. ` : ''}Nothing is deleted. Each mod can be put back once it is updated, or the change can be undone on the Tools page.</span></div>`,
    ok: 'Set them aside', cancel: 'Cancel',
  });
  if (yes) H.runTask('set_aside', { rels: list.map(o => o.rel), why: 'patch' });
}

async function errorAside(btn) {
  const name = btn.dataset.name, rel = btn.dataset.rel;
  const yes = await H.confirmBox({
    title: `Set ${name} aside?`,
    text: 'The game stops loading this mod until it is put back. Nothing is deleted.',
    what: `<div class="confirm-what"><b>${esc(fileOf(rel))}</b><span>If the errors stop, this mod was the cause; check for an update from its creator. It can be put back on this page, or the change can be undone.</span></div>`,
    ok: 'Set it aside', cancel: 'Cancel',
  });
  if (yes) H.runTask('set_aside', { rels: [rel], why: 'error' });
}

async function restore(btn) {
  const b = ((C.health && C.health.backups) || []).find(x => x.id === btn.dataset.backup);
  if (!b) return;
  const yes = await H.confirmBox({
    title: 'Restore these saves?', danger: true,
    text: `The saves return to their state on ${esc(H.dayTime(b.when))}. The current saves are backed up first.`,
    what: `<div class="confirm-what"><b>${(b.saves || []).slice(0, 5).map(s => esc(s.save_name || s.name)).join(', ')}</b>
      <span>Saves created after this backup are not changed. "Undo last change" on the Tools page restores the current saves.</span></div>`,
    ok: 'Restore', cancel: 'Cancel',
  });
  if (yes) H.runTask('restore_saves', { backup: b.id });
}

async function seen(route, key) {
  const r = await H.call(route, {});
  if (!r.ok) { H.toast(r.message || "That didn't work.", 'err'); return; }
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
    btn.innerHTML = `${ic('pause')}Set these aside until they're updated${n ? ` (${n})` : ''}`;
  }
});
document.addEventListener('click', e => {
  const a = e.target.closest && e.target.closest('[data-care-scroll]');
  if (!a) return;
  const id = a.dataset.careScroll;
  setTimeout(() => { const el = document.getElementById(id); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 250);
});
