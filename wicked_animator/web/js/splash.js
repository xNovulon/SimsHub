// The launch intro. The #splash markup is static in index.html, so it paints before any module, font or model has
// loaded; this file plays it while the app really loads and never adds waiting:
//   - the show lasts at least 1.3 s only on the first launch of a session (350 ms on a reload), 0 with reduced motion;
//   - any key or click skips it (the bar stays until the app is ready);
//   - real progress comes from the app ('wa:loading'), or else from the loading text the app already shows;
//   - when the app is ready ('wa:ready' holds its start for the rest of the show) and Home is shown, the splash
//     goes: the logo flies into its place on Home (a View Transition), or it simply fades.
// Automated browsers never see it (index.html removes it for navigator.webdriver / ?slot=test).
import { reducedMotion } from './fx.js';

const el = () => document.getElementById('splash');
let seen = false;
try { seen = !!sessionStorage.getItem('wa.splashSeen'); } catch { /* storage blocked */ }
const forced = /[?&]splash=show\b/.test(location.search);
const MIN = reducedMotion() ? 0 : seen && !forced ? 350 : 1300;
let skipped = false, finishing = null, gotProgress = false;

if (el()) {
  if (seen && !forced) el().classList.add('fast');
  if (reducedMotion()) el().classList.add('still');
  const skip = e => {
    if (!el() || finishing) return;
    if (e && e.type === 'keydown' && /^(Shift|Control|Alt|Meta)$/.test(e.key)) return;
    skipped = true;
    el().classList.add('fast');
    window.__splashSkipped = performance.now();
    if (_readyAt) finishSplash();
  };
  addEventListener('keydown', skip, { capture: true });
  addEventListener('pointerdown', skip, { capture: true });
}

// p: 0..1 of the real loading; text: what is loading now (plain words)
export function splashProgress(p, text) {
  const s = el();
  if (!s) return;
  gotProgress = true;
  s.classList.add('has-p');
  s.style.setProperty('--p', String(Math.max(0.04, Math.min(1, +p || 0))));
  if (text) splashStatus(text);
}

export function splashStatus(text) {
  const s = el();
  if (!s || !text) return;
  const st = s.querySelector('.sp-status');
  if (st && st.textContent !== text) st.textContent = text;
}

// Resolves when the minimum show time has passed (at once when skipped, reduced motion or no splash).
export function waitShow() {
  const s = el();
  if (!s || skipped) return Promise.resolve();
  const wait = Math.max(0, MIN - performance.now());
  return wait ? new Promise(r => setTimeout(r, wait)) : Promise.resolve();
}

// swap(): what to do underneath at the moment the splash goes (e.g. show Home). Called when the app is ready;
// safe to call more than once.
export function finishSplash(swap) {
  if (finishing) { if (swap) finishing.then(() => {}); return finishing; }
  const s = el();
  if (!s || !s.isConnected) { swap && swap(); return Promise.resolve(); }
  finishing = (async () => {
    splashProgress(1);
    await waitShow();
    // the words are in the brand font when it is there (never waits long: the fonts come from the internet)
    if (!skipped) { try { await Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 100))]); } catch { /* no font API */ } }
    try { sessionStorage.setItem('wa.splashSeen', '1'); } catch { /* storage blocked */ }
    const run = () => { s.remove(); window.__splashGone = performance.now(); swap && swap(); };
    if (document.startViewTransition && !reducedMotion() && !skipped && document.visibilityState === 'visible') {
      // the logo flies to the Home logo (both carry view-transition-name: brand-logo, see motion.css)
      try { const vt = document.startViewTransition(run); await vt.finished.catch(() => {}); } catch { if (s.isConnected) run(); }
    } else if (skipped || reducedMotion()) {
      run();
    } else {
      s.classList.add('out');
      await new Promise(r => setTimeout(r, 380));
      run();
    }
  })();
  return finishing;
}

// ---------------------------------------------------------------- wiring (works with or without the app's events)
let _readyAt = 0;
if (el()) {
  addEventListener('wa:loading', e => { const d = e.detail || {}; splashProgress(d.progress, d.text); });
  // the app waits for the rest of the show before it opens Home (its recovery offer then never hides under the splash)
  addEventListener('wa:ready', e => { const d = e.detail || {}; if (typeof d.hold === 'function') d.hold(waitShow()); });
  addEventListener('wa:home', () => finishSplash());
  // without the app's events: follow its own loading text and its ready signal (#loading.done)
  const watch = () => {
    const text = document.getElementById('loading-text'), box = document.getElementById('loading');
    if (!text || !box) return false;
    const mo = new MutationObserver(() => {
      if (!gotProgress) splashStatus(text.textContent);
      if (box.classList.contains('done') && !_readyAt) {
        _readyAt = performance.now();
        window.__splashReadyAt = _readyAt;
        splashProgress(1);
        // Home normally takes it from here (home.js); if the app opens straight into the editor, go anyway
        setTimeout(() => { if (el()) finishSplash(); }, skipped ? 0 : Math.max(250, MIN - performance.now() + 50));
        if (skipped) finishSplash();
      }
    });
    mo.observe(text, { childList: true, characterData: true, subtree: true });
    mo.observe(box, { attributes: true, attributeFilter: ['class'] });
    return true;
  };
  if (!watch()) addEventListener('DOMContentLoaded', watch, { once: true });
}
