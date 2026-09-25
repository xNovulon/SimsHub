// Novulon's Sims Hub - "CC that may need a Sims 4 Studio fix" (Tools page) and its line in the patch-day notice.
// care.js imports this module, hands it the Hub's helpers (init) and puts card() into the Tools page. The server
// routes are GET /api/batchfix, POST /api/batchfix/open and the task batch_fix_scan (docs/batchfix.md). The Hub
// never changes a CC file: it names the Sims 4 Studio batch fix to run, and can set files aside (undoable).

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
  B.data = r.http === 200 ? r : { ok: false, message: r.message || "This couldn't be read right now." };
  if (H.page() === 'tools') H.render();
}

export function reset() { B.data = null; }

// the line in the patch-day notice (Home banner and the "After a game update" card)
export function patchLine(sum) {
  if (!sum || !sum.files) return '';
  const names = (sum.fixes || []).map(f => f.name);
  return `<span class="bf-line" data-care="batchfix-line">${ic('info')}<span>${H.plural(sum.files, 'CC file')} may need a Sims 4 Studio fix
    (${esc(names.slice(0, 2).join(', '))}${names.length > 2 ? ` and ${names.length - 2} more` : ''}).
    <a href="#tools" data-care-scroll="care-batchfix">See which fix</a></span></span>`;
}

function steps(fx) {
  const path = (fx.menu || []).map(esc).join(' › ');
  return `<details class="more"><summary>How to fix</summary><ol class="bf-steps">
    <li>Close The Sims 4.</li>
    <li>In Sims 4 Studio, choose <b>${path}</b>.</li>
    <li>Pick your Mods folder. Sims 4 Studio keeps a copy of each file it changes.</li>
    <li>Come back and press <b>Check again</b>.</li></ol></details>`;
}

function fileRow(f) {
  const where = f.set_aside ? `<span class="chip ok">${ic('pause')}Set aside</span>` : !f.in_mods ? '<span class="chip">Parked</span>' : '';
  return `<div class="care-row" data-bf-file="${esc(f.rel)}"><div class="ci">${ic('doc')}</div>
    <div class="grow"><b title="${esc(f.rel)}">${esc(f.name)}</b><span title="${esc(f.why)}">${f.folder ? `${esc(f.folder)} · ` : ''}${esc(f.why)}</span></div>
    ${where}<button class="btn small ghost" data-act="bf-open" data-rel="${esc(f.rel)}" title="Show this file in its folder">${ic('folder')}Open folder</button></div>`;
}

function fixBlock(fx) {
  const canAside = (fx.files || []).filter(f => f.in_mods && !f.set_aside).length;
  const parked = fx.parked ? `<div class="note warn">${ic('warn')}<span>${H.plural(fx.parked, 'of these files is', 'of these files are')}
    parked by Quick Start. Switch to Full Start before running the fix.</span></div>` : '';
  return `<div class="bf-fix" data-fix="${esc(fx.id)}">
    <div class="top"><div class="ci">${ic('spark')}</div><div class="grow"><b>${esc(fx.name)}</b>
      <span title="${esc(fx.update)}">${esc(fx.problem)}</span></div>
      <span class="chip warn">${H.plural(fx.count, 'file')}</span></div>
    ${steps(fx)}${parked}
    <details class="more"><summary>Show the ${H.plural(fx.count, 'file')}${fx.set_aside ? ` (${fx.set_aside} set aside)` : ''}</summary>
      <div class="care-list">${(fx.files || []).map(fileRow).join('')}</div>
      ${fx.more ? `<div class="muted" style="font-size:12px;margin-top:6px">And ${H.plural(fx.more, 'more file')}.</div>` : ''}
      <div class="actions"><button class="btn small soft" data-act="bf-aside" data-fix="${esc(fx.id)}"${canAside && !noChange() ? '' : ' disabled'}>${ic('pause')}Set these aside instead${canAside ? ` (${canAside})` : ''}</button></div>
    </details></div>`;
}

export function card() {
  const r = B.data;
  let body;
  if (!r) body = `<div class="saves-loading" style="padding:16px 4px"><div class="spinner sm"></div>Reading the last check...</div>`;
  else if (!r.ok) body = `<div class="note err">${ic('warn')}<span>${esc(r.message)}</span></div>`;
  else if (!r.scanned) body = `<div class="note">${ic('info')}<span>${esc(r.message)}</span></div>`;
  else {
    const fixes = r.fixes || [];
    body = `<div class="care-status${fixes.length ? ' hot' : ''}">${ic(fixes.length ? 'warn' : 'check')}<div><b>${esc(r.message)}</b>
      <span>Checked ${H.plural(r.files_checked, 'file')} · ${esc(H.ago(r.scanned))}</span></div></div>`;
    if (fixes.length) {
      body += `<div class="bf-fixes">${fixes.map(fixBlock).join('')}</div>
        <details class="more why"><summary>What "may need" means</summary><p>The file matches a problem a batch fix is known for.
        It may still look fine in your game. Setting a file aside deletes nothing.</p></details>`;
    }
  }
  const scanned = r && r.ok && r.scanned;
  return `<div class="card" id="care-batchfix" data-care="batchfix"><div class="card-head"><div class="ic blue">${ic('spark')}</div><div class="grow">
      <h2>CC that may need a Sims 4 Studio fix</h2><p>Finds CC that needs a batch fix, and names the fix. Your files are never changed here.</p></div>
      <button class="btn${scanned ? '' : ' primary'}" data-act="bf-scan"${noChange() ? ' disabled' : ''}>${ic(scanned ? 'refresh' : 'search')}${scanned ? 'Check again' : 'Check my CC'}</button></div>
      ${body}</div>`;
}

async function setAside(btn) {
  const fx = ((B.data && B.data.fixes) || []).find(f => f.id === btn.dataset.fix);
  if (!fx) return;
  const list = (fx.files || []).filter(f => f.in_mods && !f.set_aside).slice(0, MAX_ASIDE);
  if (!list.length) return;
  const yes = await H.confirmBox({
    title: `Set ${H.plural(list.length, 'file')} aside?`,
    text: `The game stops loading ${list.length === 1 ? 'it' : 'them'} until ${list.length === 1 ? 'it is' : 'they are'} put back.`,
    what: `<div class="confirm-what"><b>${list.slice(0, 5).map(f => esc(f.name)).join(', ')}${list.length > 5 ? ` and ${list.length - 5} more` : ''}</b>
      <span>Nothing is deleted. Files that are set aside are not included when Sims 4 Studio runs the fix on your Mods folder; put them back first.
      The change can be undone on the Tools page.</span></div>`,
    ok: 'Set them aside', cancel: 'Cancel',
  });
  if (yes) H.runTask('set_aside', { rels: list.map(f => f.rel), why: 'fix' });
}

async function openFolder(btn) {
  const r = await H.call('batchfix/open', { rel: btn.dataset.rel });
  H.toast(r.message || (r.ok ? 'Opened.' : "That couldn't be opened."), r.ok ? 'ok' : 'err');
}

export const TITLES = { batch_fix_scan: () => 'Checking your CC for Sims 4 Studio fixes' };
export const DONE = { batch_fix_scan: () => 'Check finished' };
export const ACTS = {
  'bf-scan': () => H.runTask('batch_fix_scan'),
  'bf-open': btn => openFolder(btn),
  'bf-aside': btn => setAside(btn),
};
