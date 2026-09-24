// Fast, styled tooltips with the keyboard shortcut, for every element that has a title (design.md 4.6). No markup
// changes: it reads the existing titles, e.g. "Play / pause (Space)" -> "Play / pause" + [Space];
// "Undo (Ctrl+Z)" -> [Ctrl][Z]. The first tooltip waits 450 ms; the next control within 700 ms shows at once.
// While the pointer is over a control its title is parked in data-tip (so the slow native tooltip stays away) and
// put back when the pointer leaves. Hold Ctrl for half a second: every control with a shortcut shows its key.

const DELAY = 450, WARM_MS = 700;
const KEY_RE = /\s*\(([^()]*(?:Ctrl|Shift|Alt|Space|Delete|Home|Esc|[A-Z0-9?,.←→])[^()]*)\)\s*$/;

export function splitTitle(title) {
  const m = title.match(KEY_RE);
  if (!m) return { text: title, keys: [] };
  const first = m[1].split(/\s+or\s+/)[0];                       // "Ctrl+Shift+Z or Ctrl+Y" -> first form
  const keys = first.split('+').map(s => s.trim()).filter(Boolean);
  if (!keys.length || !keys.every(k => /^(Ctrl|Shift|Alt|Space|Delete|Home|End|Esc|Enter|Tab|F\d{1,2}|[A-Z0-9?,.←→/])$/.test(k))) return { text: title, keys: [] };
  return { text: title.slice(0, m.index).trim(), keys };
}

let installed = false;
export function installTooltips(root = document) {
  if (installed) return; installed = true;
  const tip = document.createElement('div');
  tip.className = 'wa-tip'; tip.setAttribute('role', 'tooltip');
  document.body.append(tip);
  let target = null, timer = 0, hiddenAt = 0;

  const show = el => {
    const title = el.dataset.tip;
    if (!title) return;
    const { text, keys } = splitTitle(title);
    tip.innerHTML = '';
    tip.append(document.createTextNode(text));
    if (keys.length) {
      const k = document.createElement('span'); k.className = 'keys';
      for (const x of keys) { const kb = document.createElement('kbd'); kb.textContent = x; k.append(kb); }
      tip.append(k);
    }
    tip.classList.toggle('warm', performance.now() - hiddenAt < WARM_MS);
    // below the control; above it when there is no room; kept inside the window
    const r = el.getBoundingClientRect(), t = tip.getBoundingClientRect();
    let x = r.left + r.width / 2 - t.width / 2, y = r.bottom + 8;
    if (y + t.height > innerHeight - 6) y = r.top - t.height - 8;
    x = Math.max(6, Math.min(innerWidth - t.width - 6, x));
    tip.style.setProperty('--tx', x + 'px'); tip.style.setProperty('--ty', y + 'px');
    tip.classList.add('show');
  };
  // hide: the styled tip goes (a click, a key); release: the pointer left - the title goes back on the control
  // (it was only parked in data-tip while the pointer was over it, to keep the slow native tooltip away)
  const hide = () => {
    clearTimeout(timer);
    if (tip.classList.contains('show')) hiddenAt = performance.now();
    tip.classList.remove('show');
  };
  const release = () => {
    hide();
    if (target && target.dataset.tipParked && !target.hasAttribute('title')) { target.setAttribute('title', target.dataset.tip); delete target.dataset.tipParked; }
    target = null;
  };

  root.addEventListener('pointerover', e => {
    const el = e.target.closest?.('[title], [data-tip]');
    if (!el || el === target) return;
    release();
    if (el.title) { el.dataset.tip = el.title; el.dataset.tipParked = '1'; el.removeAttribute('title'); }
    target = el;
    const warm = performance.now() - hiddenAt < WARM_MS;
    timer = setTimeout(() => { if (target === el && el.isConnected) show(el); }, warm ? 0 : DELAY);
  });
  root.addEventListener('pointerout', e => { if (target && !target.contains(e.relatedTarget)) release(); });
  root.addEventListener('pointerdown', hide, true);
  addEventListener('keydown', hide, true);
  addEventListener('blur', release);
}

// Key tips: hold Ctrl for half a second (without pressing anything else) and every control with a shortcut shows
// its key next to it - a map of the keyboard that disappears when Ctrl is let go.
// The listeners run in the capture phase, so a box or the palette that keeps keys to itself (Ctrl+K, typing) can
// never hide the key-up from them; a pointer move without Ctrl, a click, the wheel or leaving the window also
// clears them, so the chips can never get stuck on screen.
let keyTips = false;
export function installKeyTips() {
  if (keyTips) return; keyTips = true;
  let t = 0, shown = [], held = false;
  const busy = () => !!document.querySelector('.backdrop:not(.leaving), .palette-back');
  const clear = () => { clearTimeout(t); t = 0; if (shown.length) { shown.forEach(x => x.remove()); shown = []; } };
  const place = () => {
    if (!held || busy()) return;
    for (const el of document.querySelectorAll('[data-tip], [title]')) {
      const r = el.getBoundingClientRect();
      if (!r.width || r.bottom < 0 || r.top > innerHeight) continue;
      const { keys } = splitTitle(el.title || el.dataset.tip || '');
      if (!keys.length) continue;
      const chip = document.createElement('div');
      chip.className = 'key-tip'; chip.textContent = keys.join(' ');
      chip.style.left = Math.round(Math.min(innerWidth - 40, r.right - 10)) + 'px'; chip.style.top = Math.round(Math.max(2, r.top - 8)) + 'px';
      document.body.append(chip); shown.push(chip);
    }
  };
  addEventListener('keydown', e => {
    if (e.key !== 'Control') { held = false; clear(); return; }
    if (e.repeat) return;
    held = true; clear();
    if (busy()) return;
    t = setTimeout(place, 500);
  }, true);
  addEventListener('keyup', e => { if (e.key === 'Control' || !e.ctrlKey) { held = false; clear(); } }, true);
  addEventListener('pointermove', e => { if ((held || shown.length) && !e.ctrlKey) { held = false; clear(); } }, true);
  addEventListener('pointerdown', () => { held = false; clear(); }, true);
  addEventListener('wheel', () => clear(), { capture: true, passive: true });
  addEventListener('blur', () => { held = false; clear(); });
  document.addEventListener('visibilitychange', () => { held = false; clear(); });
}
