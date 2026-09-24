// Novulon's Sims Hub - "CC that may need a Sims 4 Studio fix" (Tools page) and its line in the patch-day notice.
// care.js imports this module, hands it the Hub's helpers (init) and puts card() into the Tools page. The server
// routes are GET /api/batchfix, POST /api/batchfix/open and the task batch_fix_scan (docs/batchfix.md). The Hub
// never changes a CC file: it names the Sims 4 Studio batch fix to run, and can set files aside (undoable).
// Its words come from the language catalogs (i18n/<code>.json, keys bf.*). The names of the fixes and the menu path
// stay as Sims 4 Studio writes them (its menus are in English), so they can be found there.
import * as I from './i18n.js';
const { t, h, raw } = I;

let H = null;
export function init(helpers) { H = helpers; }

const B = { data: null, loading: false };
const esc = v => H.esc(v);
const ic = (id, cls) => H.ic(id, cls);
const noChange = () => H.busy() || H.gameRunning();
const MAX_ASIDE = 500;                        // the server takes at most this many files per change

export async function load(force = false) {
  if (B.loading || (B.data && !force)) return;
  B.loading = true;
  const r = await H.call('batchfix' + (force ? '?refresh=1' : ''));
  B.loading = false;
  if (r.busy) return;                         // a change is running: asked again when it is done
  B.data = r.http === 200 ? r : { ok: false, message: r.message || t('care.read_error') };
  if (H.page() === 'tools') H.render();
}

export function reset() { B.data = null; }

// "A, B and 3 more"
const names = (list, most) => list.length > most ? t('care.aside.names_more', { names: list.slice(0, most).join(', '), n: list.length - most })
  : list.join(', ');

// the line in the patch-day notice (Home banner and the "After a game update" card)
export function patchLine(sum) {
  if (!sum || !sum.files) return '';
  const fixes = (sum.fixes || []).map(f => f.name);
  return `<span class="bf-line" data-care="batchfix-line">${ic('info')}<span>${esc(t('bf.line', { n: Number(sum.files), fixes: names(fixes, 2) }))}
    <a href="#tools" data-care-scroll="care-batchfix">${esc(t('bf.line.link'))}</a></span></span>`;
}

function steps(fx) {
  const path = (fx.menu || []).map(esc).join(' › ');
  return `<ol class="bf-steps">
    <li>${esc(t('bf.step1'))}</li>
    <li>${h('bf.step2', { path: raw(path) })}</li>
    <li>${esc(t('bf.step3'))}</li>
    <li>${h('bf.step4')}</li></ol>`;
}

function fileRow(f) {
  const where = f.set_aside ? `<span class="chip ok">${ic('pause')}${esc(t('bf.set_aside'))}</span>` : !f.in_mods ? `<span class="chip">${esc(t('bf.parked'))}</span>` : '';
  return `<div class="care-row" data-bf-file="${esc(f.rel)}"><div class="ci">${ic('doc')}</div>
    <div class="grow"><b title="${esc(f.rel)}">${esc(f.name)}</b><span title="${esc(f.why)}">${f.folder ? `${esc(f.folder)} · ` : ''}${esc(f.why)}</span></div>
    ${where}<button class="btn small ghost" data-act="bf-open" data-rel="${esc(f.rel)}" title="${esc(t('bf.open_title'))}">${ic('folder')}${esc(t('common.open_folder'))}</button></div>`;
}

function fixBlock(fx) {
  const canAside = (fx.files || []).filter(f => f.in_mods && !f.set_aside).length;
  const parked = fx.parked ? `<div class="note warn">${ic('warn')}<span>${esc(t('bf.parked_note', { n: Number(fx.parked) }))}</span></div>` : '';
  const count = t('bf.files', { n: Number(fx.count) || 0 });
  return `<div class="bf-fix" data-fix="${esc(fx.id)}">
    <div class="top"><div class="ci">${ic('spark')}</div><div class="grow"><b>${esc(fx.name)}</b>
      <span>${esc(fx.problem)} ${esc(fx.update)}</span></div>
      <span class="chip warn">${esc(count)}</span></div>
    ${steps(fx)}${parked}
    <details class="more"><summary>${esc(fx.set_aside ? t('bf.show_files_aside', { n: Number(fx.count) || 0, k: Number(fx.set_aside) }) : t('bf.show_files', { n: Number(fx.count) || 0 }))}</summary>
      <div class="care-list">${(fx.files || []).map(fileRow).join('')}</div>
      ${fx.more ? `<div class="muted" style="font-size:12px;margin-top:6px">${esc(t('bf.more_files', { n: Number(fx.more) }))}</div>` : ''}
      <div class="actions"><button class="btn small soft" data-act="bf-aside" data-fix="${esc(fx.id)}"${canAside && !noChange() ? '' : ' disabled'}>${ic('pause')}${esc(t('bf.aside_btn'))}${canAside ? ` (${I.num(canAside)})` : ''}</button></div>
    </details></div>`;
}

export function card() {
  const r = B.data;
  let body;
  if (!r) body = `<div class="saves-loading" style="padding:16px 4px"><div class="spinner sm"></div>${esc(t('bf.loading'))}</div>`;
  else if (!r.ok) body = `<div class="note err">${ic('warn')}<span>${esc(r.message)}</span></div>`;
  else if (!r.scanned) body = `<div class="note">${ic('info')}<span>${esc(r.message)}</span></div>`;
  else {
    const fixes = r.fixes || [];
    body = `<div class="care-status${fixes.length ? ' hot' : ''}">${ic(fixes.length ? 'warn' : 'check')}<div><b>${esc(r.message)}</b>
      <span>${esc(t('bf.checked', { n: Number(r.files_checked) || 0, ago: H.ago(r.scanned) }))}</span></div></div>`;
    if (fixes.length) {
      body += `<div class="bf-fixes">${fixes.map(fixBlock).join('')}</div>
        <div class="note">${ic('info')}<span>${esc(t('bf.note'))}</span></div>`;
    }
  }
  const scanned = r && r.ok && r.scanned;
  return `<div class="card" id="care-batchfix" data-care="batchfix"><div class="card-head"><div class="ic blue">${ic('spark')}</div><div class="grow">
      <h2>${esc(t('bf.title'))}</h2><p>${esc(t('bf.text'))}</p></div>
      <button class="btn${scanned ? '' : ' primary'}" data-act="bf-scan"${noChange() ? ' disabled' : ''}>${ic(scanned ? 'refresh' : 'search')}${esc(t(scanned ? 'bf.scan_again' : 'bf.scan'))}</button></div>
      ${body}</div>`;
}

async function setAside(btn) {
  const fx = ((B.data && B.data.fixes) || []).find(f => f.id === btn.dataset.fix);
  if (!fx) return;
  const list = (fx.files || []).filter(f => f.in_mods && !f.set_aside).slice(0, MAX_ASIDE);
  if (!list.length) return;
  const yes = await H.confirmBox({
    title: t('bf.aside.title', { n: list.length }),
    text: esc(t('bf.aside.text', { n: list.length })),
    what: `<div class="confirm-what"><b>${esc(names(list.map(f => f.name), 5))}</b>
      <span>${esc(t('bf.aside.what'))}</span></div>`,
    ok: t('care.aside.ok'), cancel: t('common.cancel'),
  });
  if (yes) H.runTask('set_aside', { rels: list.map(f => f.rel), why: 'fix' });
}

async function openFolder(btn) {
  const r = await H.call('batchfix/open', { rel: btn.dataset.rel });
  H.toast(r.message || t(r.ok ? 'common.opened' : 'common.cant_open'), r.ok ? 'ok' : 'err');
}

export const TITLES = { batch_fix_scan: () => t('bf.task') };
export const DONE = { batch_fix_scan: () => t('done.cleanup_plan') };
export const ACTS = {
  'bf-scan': () => H.runTask('batch_fix_scan'),
  'bf-open': btn => openFolder(btn),
  'bf-aside': btn => setAside(btn),
};
