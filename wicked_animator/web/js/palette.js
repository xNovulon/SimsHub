// Ctrl+K: find and do anything by typing (design.md 4.6). Self-contained (no imports); the app passes its commands
// (commands.js + app.hooks.commands). Keyboard: type, Up/Down to move, Enter to run, Esc to close. Mouse: hover +
// click. ARIA combobox: the text box keeps focus, aria-activedescendant points at the highlighted row. Letters typed
// in the box never reach the app's one-key shortcuts (K, R, G, W...).

import { $t } from './i18n.js';
const RECENT_KEY = 'fsa.recentCommands';
let current = null;

const el = (tag, cls, ...kids) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
};
const svgIcon = name => {
  const ns = 'http://www.w3.org/2000/svg';
  const s = document.createElementNS(ns, 'svg'), u = document.createElementNS(ns, 'use');
  u.setAttribute('href', '#i-' + name); s.append(u); return s;
};
const recent = () => { try { return JSON.parse(localStorage.getItem(RECENT_KEY)) || []; } catch { return []; } };
const remember = id => { try { localStorage.setItem(RECENT_KEY, JSON.stringify([id, ...recent().filter(x => x !== id)].slice(0, 6))); } catch { /* blocked */ } };

// How well `q` matches a command: every word typed must be found (as a word start, inside a word, or as
// letters in order). Label hits beat alias hits, word starts beat the middle, short labels beat long ones.
export function scoreCommand(q, c) {
  const label = c.label.toLowerCase(), extra = ((c.words || '') + ' ' + (c.group || '') + ' ' + (c.sub || '')).toLowerCase();
  let total = 0;
  for (const t of q.toLowerCase().split(/\s+/).filter(Boolean)) {
    let s = 0;
    const i = label.indexOf(t);
    if (i === 0) s = 12; else if (i > 0 && label[i - 1] === ' ') s = 10; else if (i > 0) s = 6;
    else {
      const j = extra.indexOf(t);
      if (j >= 0) s = (j === 0 || extra[j - 1] === ' ') ? 5 : 3;
      else if (subseq(t, label)) s = 2;
      else return 0;                     // one word not found at all: no match
    }
    total += s;
  }
  return total + Math.max(0, 3 - label.length / 16);
}
function subseq(t, s) { let k = 0; for (const ch of s) if (ch === t[k]) k++; return k === t.length; }

function highlight(label, q) {
  const frag = document.createDocumentFragment();
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  const lower = label.toLowerCase();
  const marks = new Array(label.length).fill(false);
  for (const w of words) { const i = lower.indexOf(w); if (i >= 0) for (let k = i; k < i + w.length; k++) marks[k] = true; }
  let run = '', on = false;
  const flush = () => { if (!run) return; frag.append(on ? el('mark', null, run) : document.createTextNode(run)); run = ''; };
  for (let k = 0; k < label.length; k++) { if (marks[k] !== on) { flush(); on = marks[k]; } run += label[k]; }
  flush();
  return frag;
}

// commands(): [{ id, group, label, sub?, icon?, keys?: ['Ctrl','S'], words?: 'blender words, other names', run, when? }]
export function openPalette(commands, { placeholder = $t('palette.search_or_do_anything'), onSearchLibrary } = {}) {
  if (current) { current.close(); return; }
  const before = document.activeElement;
  const all = commands().filter(c => !c.when || c.when());
  const input = el('input');
  input.type = 'text'; input.placeholder = placeholder; input.spellcheck = false;
  input.setAttribute('role', 'combobox'); input.setAttribute('aria-expanded', 'true');
  input.setAttribute('aria-controls', 'palette-list'); input.setAttribute('aria-autocomplete', 'list');
  const list = el('ul', 'palette-list'); list.id = 'palette-list'; list.setAttribute('role', 'listbox');
  const foot = el('div', 'palette-foot',
    el('span', null, el('kbd', null, '↑'), el('kbd', null, '↓'), ' move'),
    el('span', null, el('kbd', null, 'Enter'), $t('palette.do_it')),
    el('span', null, el('kbd', null, 'Esc'), ' close'));
  const box = el('div', 'palette', el('div', 'palette-in', svgIcon('search'), input, el('kbd', null, 'Ctrl K')), list, foot);
  box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', 'Search commands');
  const back = el('div', 'palette-back', box);
  let rows = [], active = 0;

  const results = q => {
    q = q.trim();
    if (!q) {
      const rec = recent().map(id => all.find(c => c.id === id)).filter(Boolean).map(c => ({ ...c, group: $t('palette.recent') }));
      const top = all.filter(c => c.pinned && !rec.some(r => r.id === c.id));
      return [...rec, ...top];
    }
    const hits = all.map(c => ({ c, s: scoreCommand(q, c) })).filter(x => x.s > 0).sort((a, b) => b.s - a.s).slice(0, 40).map(x => x.c);
    if (onSearchLibrary && q.length >= 2) hits.push({ id: 'lib-search', group: $t('palette.library'), label: $t('palette.search_library_for', { q }), icon: 'library', run: () => onSearchLibrary(q) });
    return hits;
  };

  const draw = () => {
    const q = input.value;
    rows = results(q);
    active = Math.min(active, Math.max(0, rows.length - 1));
    list.innerHTML = '';
    if (!rows.length) { list.append(el('li', 'palette-empty', $t('palette.nothing_found'))); input.removeAttribute('aria-activedescendant'); return; }
    // group in the order they first appear (best hit's group first)
    const groups = [];
    for (const r of rows) if (!groups.includes(r.group)) groups.push(r.group);
    let n = 0;
    const flat = [];
    for (const g of groups) {
      list.append(el('li', 'palette-group', g));
      for (const r of rows.filter(x => x.group === g)) {
        const i = n++;
        flat.push(r);
        const li = el('li', 'palette-item',
          el('span', 'ic', svgIcon(r.icon || 'arrow')),
          el('span', 't', highlight(r.label, q), r.sub ? el('small', null, r.sub) : null),
          r.keys ? el('span', 'keys', r.keys.map(k => el('kbd', null, k))) : el('span'));
        li.id = 'pal-' + i; li.setAttribute('role', 'option');
        li.setAttribute('aria-selected', String(i === active));
        li.addEventListener('pointermove', () => { if (active !== i) { active = i; mark(); } });
        li.addEventListener('click', () => run(i));
        list.append(li);
      }
    }
    rows = flat;
    mark();
  };
  const mark = () => {
    list.querySelectorAll('.palette-item').forEach((li, i) => li.setAttribute('aria-selected', String(i === active)));
    const cur = list.querySelector('#pal-' + active);
    if (cur) { input.setAttribute('aria-activedescendant', cur.id); cur.scrollIntoView({ block: 'nearest' }); }
  };
  const run = i => {
    const c = rows[i];
    if (!c) return;
    close();
    if (c.id !== 'lib-search') remember(c.id);
    // run after the palette is gone, so a command that opens a dialog gets the keyboard
    requestAnimationFrame(() => c.run());
  };
  const keys = e => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); close(); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); active = (active + 1) % Math.max(1, rows.length); mark(); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); active = (active - 1 + rows.length) % Math.max(1, rows.length); mark(); return; }
    if (e.key === 'Enter') { e.preventDefault(); run(active); return; }
    if (e.key === 'Tab') e.preventDefault();          // focus stays in the box
    e.stopPropagation();                               // typed letters never reach the app's shortcuts (K, R, G...)
  };
  // keyup / keypress too: nothing typed here is seen by the app's listeners on the window
  const quiet = e => { if (e.key !== 'Escape') e.stopPropagation();
  };
  const close = () => {
    if (!current) return;
    current = null;
    back.remove();
    if (before && before.isConnected && before.focus && !before.matches('button')) before.focus();
  };
  input.addEventListener('input', () => { active = 0; draw(); });
  input.addEventListener('keydown', keys);
  input.addEventListener('keyup', quiet);
  input.addEventListener('keypress', quiet);
  back.addEventListener('pointerdown', e => { if (e.target === back) close(); });
  document.body.append(back);
  current = { close };
  draw();
  input.focus();
  return current;
}
export const paletteOpen = () => !!current;
export const closePalette = () => { if (current) current.close(); };
