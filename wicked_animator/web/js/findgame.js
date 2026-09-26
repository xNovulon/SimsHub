// The Sims 4 on this PC. The engine looks for the game by itself (backend/gamefind.py: a folder picked here, the one
// Sims Hub found, the EA app, Steam, the usual install folders). When it can't find it, the start waits on a short
// screen with "Find The Sims 4": a folder browser that marks the game's folder. "The Sims 4 folder" in the command
// menu (Ctrl+K) opens the same browser later.
// The bodies, clothes and furniture come from the install, which is there as soon as the game is installed. The Tray
// and Mods folders only exist after the game has started once - Home says so while they are missing.
import { h, icon, modal, toast } from './ui.js';
import { api } from './api.js';

const HOW = { picked: 'Picked by you', 'Sims Hub': 'Found by Sims Hub', 'EA app': 'Found through the EA app', Steam: 'Found in Steam',
  found: 'Found on this PC', test: 'Test folder', 'stand-in': 'Stand-in game (checks)' };
export const howFound = g => HOW[g && g.source] || '';

// The folder browser. onPicked(dir) after the engine took the folder. -> the element.
export function gameFinder({ onPicked, start = '' } = {}) {
  const F = { data: null, hist: [], loading: true, err: '', saving: '', sugs: [] };
  const el = h('div', { class: 'gfind' });
  const norm = p => /^[A-Za-z]:$/.test(p || '') ? p + '\\' : (p || '');

  async function go(path, push = true) {
    if (push && F.data && F.data.ok !== false) F.hist.push(F.data.path || '');
    F.loading = true; F.err = ''; draw();
    try {
      const r = await api.browse(norm(path));
      if (r.ok === false) { F.err = r.message || "That folder can't be opened."; if (!F.data) F.data = { path: '', drives: r.drives || [], entries: [] }; }
      else F.data = r;
      if (r.suggestions) F.sugs = r.suggestions;
    } catch (e) { F.err = e.message; }
    F.loading = false; draw();
  }
  async function pick(path) {
    F.saving = path; F.err = ''; draw();
    try {
      const r = await api.setGameDir(path);
      onPicked && onPicked(r.dir || path);
    } catch (e) { F.saving = ''; F.err = (e.body && e.body.message) || e.message; draw(); }
  }
  const crumbs = path => {
    const out = [];
    if (!path) return out;
    let acc = '';
    path.replace(/\\+$/, '').split('\\').forEach((p, i) => { acc = i === 0 ? p + '\\' : (acc.endsWith('\\') ? acc : acc + '\\') + p; out.push({ label: p, path: acc }); });
    return out;
  };
  const selectBtn = (path, label = 'Select') => h('button', { class: 'btn primary small', disabled: !!F.saving, onclick: () => pick(path) }, F.saving === path ? 'Checking...' : label);
  const gameCard = (path, title, sub) => h('div', { class: 'gfind-game' }, icon('check'),
    h('div', { class: 'grow' }, h('b', {}, title), h('span', { class: 'path' }, path), sub ? h('small', {}, sub) : null), selectBtn(path, 'Use this'));

  function draw() {
    const d = F.data || {}, path = d.path || '';
    el.innerHTML = '';
    if (F.sugs.length) {
      el.append(h('div', { class: 'gfind-lbl' }, 'Found on this PC'),
        ...F.sugs.map(s => gameCard(s.path, 'The Sims 4', HOW[s.source] || '')));
    }
    const box = h('input', { class: 'text gfind-path', placeholder: 'Or paste the folder, e.g. D:\\Games\\The Sims 4', spellcheck: 'false',
      onkeydown: e => { if (e.key === 'Enter' && box.value.trim()) go(box.value.trim().replace(/^"|"$/g, '')); } });
    el.append(h('div', { class: 'gfind-lbl' }, F.sugs.length ? 'Or look for it' : 'Look for it'), box);
    const trail = crumbs(path), shown = trail.length > 4 ? [trail[0], null, ...trail.slice(-2)] : trail;
    el.append(h('div', { class: 'gfind-crumbs' },
      h('button', { class: 'icon-btn sm', title: 'Back', disabled: !F.hist.length, onclick: () => F.hist.length && go(F.hist.pop(), false) }, icon('arrow', true)),
      h('button', { class: 'icon-btn sm', title: 'Up one folder', disabled: !path, onclick: () => go(d.parent || '') }, icon('up')),
      h('div', { class: 'trail' }, h('button', { class: path ? '' : 'cur', onclick: () => go('') }, 'This PC'),
        ...shown.flatMap((c, i) => c === null ? [h('span', { class: 'sep' }, '›'), h('span', { class: 'ell' }, '…')]
          : [h('span', { class: 'sep' }, '›'), h('button', { class: i === shown.length - 1 ? 'cur' : '', title: c.path, onclick: () => go(c.path) }, c.label)]))));
    if (F.err) el.append(h('div', { class: 'warn-box error' }, F.err));
    if (F.loading) { el.append(h('div', { class: 'gfind-state' }, h('div', { class: 'spinner sm' }), 'Opening...')); return; }
    if (!path) {
      const drives = d.drives || [];
      el.append(drives.length ? h('div', { class: 'gfind-list' }, ...drives.map(x => h('button', { class: 'gfind-row', onclick: () => go(x.path) }, icon('folder'),
        h('span', { class: 'name' }, x.label ? `${x.label} (${x.path.replace(/\\$/, '')})` : x.path.replace(/\\$/, '')))))
        : h('div', { class: 'gfind-state' }, 'No drives were found.'));
      return;
    }
    if (d.is_game) el.append(gameCard(path, 'This folder is The Sims 4', ''));
    const entries = d.entries || [];
    el.append(entries.length ? h('div', { class: 'gfind-list' }, ...entries.map(e => h('div', { class: 'gfind-row' + (e.is_game ? ' game' : '') },
      h('button', { class: 'gfind-open', title: e.path, onclick: () => go(e.path) }, icon('folder'), h('span', { class: 'name' }, e.name)),
      e.is_game ? h('span', { class: 'gfind-badge' }, 'The Sims 4') : null,
      e.is_game ? selectBtn(e.path) : null)))
      : h('div', { class: 'gfind-state' }, 'No folders in here.'));
  }
  draw();
  (async () => { await go('', false); if (start) await go(start); })();
  return el;
}

// Before the app starts: the game's folder, or a screen that asks for it. -> the engine's answer ({found, dir,
// sims_ready, tray...}) once the game is there (null from an engine too old to say).
export async function ensureGame() {
  let g = null;
  try { g = await api.game(); } catch { return null; }
  if (g.found) return g;
  const box = document.getElementById('loading');
  const text = document.getElementById('loading-text');
  const spin = box.querySelector('.spinner');
  return new Promise(resolve => {
    // the start goes on only once the engine says the game is there
    const done = async () => {
      let now = null;
      try { now = await api.game(); } catch {
        status.textContent = "The animator's engine isn't answering. Close Wicked Animator and open it again.";
        return null;
      }
      if (!now || !now.found) return false;
      card.remove(); box.classList.remove('need-game');
      if (spin) spin.style.display = '';
      text.style.display = '';
      resolve(now);
      return true;
    };
    const finderSlot = h('div', {});
    const findBtn = h('button', { class: 'btn primary', onclick: () => {
      findBtn.style.display = 'none';
      finderSlot.append(gameFinder({ onPicked: () => { status.textContent = 'Found it. Loading the game\'s sims...'; done(); } }));
    } }, icon('search'), 'Find The Sims 4');
    const status = h('div', { class: 'hint' });
    const again = h('button', { class: 'btn ghost', onclick: async () => {
      again.disabled = true; status.textContent = 'Looking...';
      if ((await done()) === false) status.textContent = 'Still not found. Use Find The Sims 4 to show where it is.';
      again.disabled = false;
    } }, 'Look again');
    const card = h('div', { class: 'need-game-card' },
      h('h2', {}, "The Sims 4 wasn't found"),
      h('p', {}, 'Wicked Animator shows your sims, their clothes and the furniture straight from the game. Show it where The Sims 4 is installed.'),
      h('div', { class: 'row' }, findBtn, again),
      status,
      finderSlot,
      h('small', { class: 'muted' }, 'The game doesn\'t need to be running. No game on this PC? Install The Sims 4 first.'));
    if (spin) spin.style.display = 'none';
    text.style.display = 'none';
    box.classList.add('need-game');
    box.append(card);
  });
}

// "The Sims 4 folder" (command menu): where the game is read from, and the browser to pick another one.
export async function openGameFolder() {
  let g = null;
  try { g = await api.game(); } catch { /* shown as not found */ }
  const body = h('div', {});
  const dlg = modal({ title: 'The Sims 4 folder', text: 'Where the animator reads the sims, clothes and furniture from.', body, wide: true, buttons: [{ label: 'Close', kind: 'ghost' }] });
  const head = g && g.found
    ? h('div', { class: 'gfind-game here' }, icon('check'), h('div', { class: 'grow' }, h('b', {}, 'The Sims 4'), h('span', { class: 'path' }, g.dir), h('small', {}, howFound(g))))
    : h('div', { class: 'warn-box' }, "The Sims 4 wasn't found on this PC.");
  body.append(head);
  if (g && g.found && !g.sims_ready) body.append(h('div', { class: 'warn-box' }, launchNote()));
  const change = h('button', { class: 'btn small', onclick: () => {
    change.remove();
    body.append(gameFinder({ onPicked: () => {
      body.innerHTML = '';
      // what was already read from the old folder stays in the engine until the app is opened again
      body.append(h('div', { class: 'gfind-game here' }, icon('check'), h('div', { class: 'grow' }, h('b', {}, 'Saved'),
        h('small', {}, 'Close Wicked Animator and open it again to read the game from there.'))));
      toast('The Sims 4 folder saved.', 'ok');
    } }));
  } }, icon('folder'), g && g.found ? 'Pick another folder' : 'Find The Sims 4');
  body.append(h('div', { style: { marginTop: '10px' } }, change));
  return dlg;
}

// While the game has never started on this PC, there is no Tray and no Mods folder yet.
export const launchNote = () => 'Start The Sims 4 once. Your Tray sims and the Mods folder show up after its first start.';
