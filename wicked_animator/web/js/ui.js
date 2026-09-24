// Small UI helpers: element builder, toasts, modal dialogs, context menus, and the plug-in helpers other parts use
// to add toolbar buttons and icons without touching index.html.
import { $t } from './i18n.js';
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') {
      for (const [sk, sv] of Object.entries(v)) sk.startsWith('--') ? el.style.setProperty(sk, sv) : (el.style[sk] = sv);
    }
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'html') el.innerHTML = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) el.append(c.nodeType ? c : document.createTextNode(c));
  return el;
}

export function icon(name, flip = false) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  const use = document.createElementNS(ns, 'use');
  use.setAttribute('href', '#i-' + name);
  svg.append(use);
  if (flip) svg.style.transform = 'scaleX(-1)';
  return svg;
}

// A short message over the stage, just above the hint row. Only one shows at a time: a new message replaces
// the old one, so they never pile up over the sims.
let toastEl = null, toastTimers = [];
export function toast(text, kind = '') {
  const root = document.getElementById('toasts');
  toastTimers.forEach(clearTimeout); toastTimers = [];
  if (toastEl && toastEl.isConnected) toastEl.remove();
  const el = toastEl = h('div', { class: 'toast ' + kind, role: 'status' }, kind === 'ok' ? icon('check') : kind === 'err' ? icon('x') : null, h('span', {}, text));
  root.append(el);
  // Raised while a dialog is open (e.g. "Pick at least one animation." from its button): the dialog would hide
  // it, so it shows inside the dialog. Checked a moment later: a button that closes its dialog right after the
  // message leaves it over the stage, where it can be read.
  setTimeout(() => { if (el.isConnected && el.parentElement === root) intoDialog(el); }, 0);
  const ms = kind === 'err' ? 5200 : 3000;
  toastTimers.push(setTimeout(() => { el.style.transition = '.3s'; el.style.opacity = '0'; el.style.transform = 'translateY(6px)'; }, ms));
  toastTimers.push(setTimeout(() => { el.remove(); if (toastEl === el) toastEl = null; }, ms + 400));
}

function intoDialog(el) {
  const backs = document.querySelectorAll('#modal-root > .backdrop:not(.leaving)');
  const dlg = backs.length && backs[backs.length - 1].querySelector('.modal');
  if (!dlg) return;
  let slot = dlg.querySelector(':scope > .modal-note');
  if (!slot) {
    slot = h('div', { class: 'modal-note' });
    const foot = dlg.querySelector(':scope > footer');
    foot ? dlg.insertBefore(slot, foot) : dlg.append(slot);
  }
  slot.innerHTML = '';
  slot.append(el);
}

// A message with buttons that stays a little longer and never blocks the app (no dark backdrop):
// e.g. "Loop is 6 s now - everything plays slower. [Keep the speed instead] [Undo]".
// actions: [{label, primary, onClick -> false keeps the bar open}]. Returns {update(text, actions), close()}.
let barEl = null;
export function choiceBar(text, actions = [], { timeout = 12000 } = {}) {
  closeChoiceBar();
  const root = document.getElementById('toasts');
  let timer = null;
  const el = barEl = h('div', { class: 'choice-bar', role: 'status' });
  if (timeout) el.style.setProperty('--timeout', timeout + 'ms');
  // a thin line under the bar counts down to when it closes by itself (restarted whenever the timer is)
  const arm = () => {
    clearTimeout(timer);
    if (!timeout) return;
    timer = setTimeout(close, timeout);
    el.classList.remove('counting'); void el.offsetWidth; el.classList.add('counting');
  };
  const close = () => { clearTimeout(timer); el.remove(); if (barEl === el) barEl = null; };
  const fill = (t, acts) => {
    el.innerHTML = '';
    el.append(h('span', { class: 'msg' }, t),
      ...acts.map(a => h('button', { class: 'btn small ' + (a.primary ? 'soft' : 'ghost'), onclick: () => { if (a.onClick() !== false) close(); else arm(); } }, a.label)),
      h('button', { class: 'icon-btn sm', title: $t('ui.close'), onclick: close }, icon('x')));
    arm();
  };
  fill(text, actions);
  el.addEventListener('pointerenter', () => { clearTimeout(timer); el.classList.remove('counting'); });
  el.addEventListener('pointerleave', arm);
  root.append(el);
  return { update: fill, close };
}
export function closeChoiceBar() { if (barEl) { barEl.remove(); barEl = null; } }

// ---------------------------------------------------------------- controls
// Range inputs show how far they are filled. Two-way sliders (min below 0, e.g. frown <-> smile) fill from
// the middle (the zero point) to the thumb, so "0" looks empty instead of half on.
export function fillRange(el) {
  const min = +el.min || 0, max = +el.max || 100, v = +el.value;
  const span = Math.max(1e-9, max - min);
  const f = ((v - min) / span) * 100;
  if (min < 0 && max > 0) {
    const z = ((0 - min) / span) * 100;
    el.classList.add('bipolar');
    el.style.setProperty('--a', `${Math.min(z, f)}%`);
    el.style.setProperty('--b', `${Math.max(z, f)}%`);
    el.style.setProperty('--z', `${z}%`);
  } else {
    el.classList.remove('bipolar');
  }
  el.style.setProperty('--fill', `${f}%`);
}
document.addEventListener('input', e => { if (e.target.matches?.('input[type=range]')) fillRange(e.target); });

// A labelled slider. fmt(v) -> shown value. onInput(v, done) is called live (done=false) and on release (done=true).
export function slider({ label, min = 0, max = 1, step = 0.01, value = 0, fmt = v => v, onStart, onInput, title }) {
  const input = h('input', { type: 'range', min, max, step, value });
  const out = h('output', {}, fmt(+value));
  input.addEventListener('pointerdown', () => onStart && onStart());
  input.addEventListener('input', () => { out.textContent = fmt(+input.value); onInput && onInput(+input.value, false); });
  input.addEventListener('change', () => onInput && onInput(+input.value, true));
  fillRange(input);
  return h('div', { class: 'slider', title: title || null }, h('label', {}, label), out, input);
}

export function toggle(checked, onChange) {
  const input = h('input', { type: 'checkbox', checked: !!checked });
  input.addEventListener('change', () => onChange(input.checked));
  return h('label', { class: 'switch' }, input, h('span'));
}

export function toggleRow(title, sub, checked, onChange) {
  return h('div', { class: 'toggle-row' }, h('div', {}, h('b', {}, title), sub ? h('span', {}, sub) : null), toggle(checked, onChange));
}

export function section(title, ...children) {
  return h('div', { class: 'section' }, h('div', { class: 'section-title' }, ...[].concat(title)), ...children);
}

export function tip(text) {
  return h('div', { class: 'tip' }, icon('spark'), h('div', {}, text));
}

// modal({title, text, body: Node, buttons: [{label, kind, onClick -> false keeps it open}], wide})
// The dialog takes the keyboard while it is open: the first text box (or the main button) gets focus, Tab stays
// inside it, Enter presses the focused button and Escape closes only the top dialog - never the one below it
// and never anything behind it (Home, the selection).
const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
export function modal({ title, text, body, buttons = [], onClose, wide = false }) {
  const root = document.getElementById('modal-root');
  const before = document.activeElement;
  let closed = false;
  // leaving is faster than coming: the backdrop fades out (170 ms, motion.css) as .leaving and is removed when its
  // animation ends - within 240 ms at most (reduced motion, a hidden tab). A leaving dialog no longer counts as open.
  const close = () => {
    if (closed) return;
    closed = true;
    back.classList.add('leaving');
    const done = () => { clearTimeout(safety); back.remove(); };
    back.addEventListener('animationend', e => { if (e.target === back && back.classList.contains('leaving')) done(); });
    const safety = setTimeout(done, 240);
    document.removeEventListener('keydown', keys, true);
    onClose && onClose();
    // give the keyboard back to what had it (unless it was a button that opened this - Enter would reopen it)
    if (before && before.isConnected && before !== document.body && !before.matches('button')) before.focus?.();
    else document.activeElement?.blur?.();
  };
  const isTop = () => [...root.querySelectorAll(':scope > .backdrop:not(.leaving)')].pop() === back;
  const keys = e => {
    if (!isTop()) return;
    if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); close(); return; }
    if (e.key === 'Tab') {
      const list = [...dlg.querySelectorAll(FOCUSABLE)].filter(x => x.offsetParent !== null);
      if (!list.length) { e.preventDefault(); return; }
      const i = list.indexOf(document.activeElement);
      if (!dlg.contains(document.activeElement) || i < 0) { e.preventDefault(); list[0].focus(); return; }
      if (e.shiftKey && i === 0) { e.preventDefault(); list[list.length - 1].focus(); }
      else if (!e.shiftKey && i === list.length - 1) { e.preventDefault(); list[0].focus(); }
      return;
    }
    // Ctrl+S / Ctrl+O never open the browser's own save / open windows over a dialog
    if ((e.ctrlKey || e.metaKey) && (e.code === 'KeyS' || e.code === 'KeyO')) e.preventDefault();
    // keys typed in the dialog belong to it, not to the editor shortcuts behind it
    if (!dlg.contains(e.target) && e.key !== 'Enter') e.stopPropagation();
  };
  const footer = h('footer', {}, buttons.map(b => {
    const btn = h('button', { class: 'btn ' + (b.kind || '') }, b.label);
    btn.addEventListener('click', async () => {
      if (btn.disabled) return;
      let r = b.onClick?.();
      if (r && typeof r.then === 'function') {
        btn.disabled = true;                      // one click only while it works (no double exports)
        try { r = await r; } finally { if (!closed) btn.disabled = false; }
      }
      if (r !== false) close();
    });
    return btn;
  }));
  const dlg = h('div', { class: 'modal' + (wide ? ' wide' : ''), role: 'dialog', 'aria-modal': 'true', tabindex: '-1' },
    h('header', {}, h('div', { class: 'grow' }, h('h2', {}, title), text ? h('p', {}, text) : null),
      h('button', { class: 'icon-btn sm modal-x', title: $t('ui.close_esc'), onclick: () => close() }, icon('x'))),
    h('div', { class: 'body' }, body || null),
    buttons.length ? footer : null);
  const back = h('div', { class: 'backdrop', onmousedown: e => { if (e.target === back && !closed) close(); } }, dlg);
  root.append(back);
  document.addEventListener('keydown', keys, true);
  // take the focus away from whatever opened the dialog right now, so Enter can't press that button again
  if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur?.();
  dlg.focus({ preventScroll: true });
  setTimeout(() => {
    if (closed) return;
    // a text box first; else the main button - but never a destructive one (Enter must not delete or replace)
    const f = dlg.querySelector('.body input:not([type=checkbox]):not([type=range]), .body select, .body textarea')
      || footer.querySelector('.btn.primary:not([disabled])') || footer.querySelector('.btn.ghost:not([disabled])') || footer.querySelector('button:not([disabled]):not(.danger)');
    (f || dlg).focus({ preventScroll: true });
  }, 30);
  return { close, dialog: dlg, footer };
}

export function confirmBox(title, text, okLabel = 'OK', danger = false) {
  return new Promise(res => {
    modal({ title, text, onClose: () => res(false), buttons: [
      { label: $t('ui.cancel'), kind: 'ghost', onClick: () => res(false) },
      { label: okLabel, kind: danger ? 'danger' : 'primary', onClick: () => res(true) },
    ] });
  });
}

// A question with several answers: resolves with the chosen answer's value, or null when closed.
export function choiceBox(title, text, choices) {
  return new Promise(res => {
    let done = false;
    modal({ title, text, onClose: () => { if (!done) res(null); }, buttons: choices.map(c => ({
      label: c.label, kind: c.kind || '', onClick: () => { done = true; res(c.value); } })) });
  });
}

let menuEl = null;
export function contextMenu(x, y, items) {
  closeMenu();
  menuEl = h('div', { class: 'ctx-menu', style: { left: x + 'px', top: y + 'px' } },
    items.map(it => it === '-' ? h('div', { class: 'ctx-sep' }) : it.heading ? h('div', { class: 'ctx-label' }, it.heading) :
      h('button', { class: it.danger ? 'danger' : '', onclick: () => { closeMenu(); it.onClick(); } },
        it.dot ? h('span', { class: 'ease-dot', style: { background: it.dot } }) : null, it.icon ? icon(it.icon) : null, it.label, it.checked ? h('span', { class: 'ctx-check' }, '•') : null)));
  document.body.append(menuEl);
  const r = menuEl.getBoundingClientRect();
  if (r.bottom > innerHeight) menuEl.style.top = Math.max(4, y - r.height) + 'px';
  if (r.right > innerWidth) menuEl.style.left = Math.max(4, x - r.width) + 'px';
  setTimeout(() => document.addEventListener('mousedown', outside), 0);
}
function outside(e) { if (menuEl && !menuEl.contains(e.target)) closeMenu(); }
export function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; } document.removeEventListener('mousedown', outside); }

// ---------------------------------------------------------------- plug-in helpers (plan 2.4)
// Is a dialog open? A dialog that is fading out does not count.
export const dialogOpen = () => !!document.querySelector('#modal-root .backdrop:not(.leaving)');

// Send an app event ('wa:' + name) - through app.emit when the app has it, else straight on the window.
export function emitWA(app, name, detail = {}) {
  try {
    if (app && typeof app.emit === 'function') return app.emit(name, detail);
    window.dispatchEvent(new CustomEvent('wa:' + name, { detail: { app, ...detail } }));
  } catch (e) { console.error(e); }
}

// A new icon for the sprite sheet: ui.addIcon('light', '<path d="..."/>') then icon('light').
export function addIcon(id, svgInner, viewBox = '0 0 24 24') {
  if (document.getElementById('i-' + id)) return;
  const sheet = document.querySelector('svg[aria-hidden="true"] defs')?.parentNode || document.querySelector('body > svg');
  if (!sheet) return;
  const sym = document.createElementNS('http://www.w3.org/2000/svg', 'symbol');
  sym.id = 'i-' + id; sym.setAttribute('viewBox', viewBox);
  sym.innerHTML = svgInner;
  sheet.append(sym);
}

// A button in one of the app's toolbars, without editing index.html:
//   cell 'view' (the glass buttons over the stage, top right), 'top' (the top bar), 'tl' (the timeline's key row).
// toggle: a button that stays lit while on (button.classList 'on'). Returns the button (the same one when the id is
// already there).
export function addToolbarButton({ cell = 'view', id, icon: ic, title = '', label = null, toggle = false, onClick, before = null } = {}) {
  if (id && document.getElementById(id)) return document.getElementById(id);
  const host = cell === 'top' ? document.querySelector('#topbar .top-actions')
    : cell === 'tl' ? document.querySelector('#timeline .tl-keys')
    : document.querySelector('#viewport-wrap .view-cell');
  if (!host) return null;
  const cls = cell === 'view' ? 'icon-btn glass' : label ? 'btn small ghost' : 'icon-btn';
  const b = h('button', { class: cls + (toggle ? ' toggle' : ''), id: id || null, title: title || null, type: 'button' }, ic ? icon(ic) : null, label);
  b.addEventListener('click', e => { if (toggle) b.classList.toggle('on'); onClick && onClick(e, b); });
  const ref = before ? host.querySelector(before) : cell === 'view' ? host.querySelector('#btn-record') : cell === 'top' ? host.querySelector('.sep') : null;
  ref ? host.insertBefore(b, ref) : host.append(b);
  return b;
}
