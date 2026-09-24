// Home: start something new, open your animations, see your progressions.
// The start grid never leaves holes: Magic is a 2 x 2 card, "Blank animation" is one wide card with five pills,
// and cards other parts of the app add (app.hooks.homeCards) fill whole rows. Going between Home and the editor is a
// View Transition (the logo flies to the top bar; a clicked animation's picture grows into the stage).
import { h, icon, confirmBox, contextMenu, toast, emitWA } from './ui.js';
import { api } from './api.js';
import { KINDS } from './tags.js';
import { maybeTour } from './tour.js';
import { finishSplash } from './splash.js';
import { reducedMotion } from './fx.js';

const kindName = k => (KINDS.find(x => x[0] === k) || ['', k || 'Animation'])[1];
const $ = id => document.getElementById(id);

// View Transitions only for people: automated test browsers get the plain switch (unless ?vt=1), and so does
// reduced motion
export const canTransition = () => !!document.startViewTransition && !reducedMotion() && document.visibilityState === 'visible'
  && (!navigator.webdriver || /[?&]vt=1\b/.test(location.search)) && !$('splash');

function setStepMark(app, home) {
  document.body.dataset.step = home ? 'home' : (app.step || 'scene');
}

export function hideHome(app, { from = null } = {}) {
  const home = $('home'), wrap = $('viewport-wrap');
  if (home.classList.contains('hidden')) { setStepMark(app, false); maybeTour(app); return; }
  const go = () => {
    if (from) { from.style.viewTransitionName = ''; if (wrap) wrap.style.viewTransitionName = 'stage-hero'; }
    home.classList.add('hidden');
    setStepMark(app, false);
    app._moveGlider?.();
    emitWA(app, 'home', { shown: false });
  };
  if (!canTransition()) { go(); maybeTour(app); return; }
  if (from && from.isConnected) from.style.viewTransitionName = 'stage-hero';   // the old state: the card's picture
  try {
    document.startViewTransition(go).finished.catch(() => {}).finally(() => { if (wrap) wrap.style.viewTransitionName = ''; maybeTour(app); });
  } catch { go(); maybeTour(app); }
}

// The start cards: [{id, title, text, icon, onClick, big?, wide?, pills?}]
function startCards(app) {
  const blank = template => () => app.newScene(true, true, template, () => { hideHome(app); app.showStep('pose'); });
  const cards = [
    { id: 'magic', title: 'Magic Animation', badge: 'Beta', icon: 'wand', big: true, cls: 'magic-card',
      text: 'Pick a position and a place - one click gives you a complete animation: posed on the real furniture, moving, with physics, faces, claps and wet sounds. Ready to send to the game.',
      onClick: () => { hideHome(app); app.openMagic(); }, art: magicStrip(app) },
    { id: 'blank', title: 'Blank animation', icon: 'blank', wide: true, text: 'Start from scratch - pick who is in it:',
      pills: [['couple', 'Woman & man'], ['ff', 'Two women'], ['mm', 'Two men'], ['futa', 'Woman & futa'], ['solo', 'One sim']].map(([t, l]) => ({ label: l, onClick: blank(t) })) },
    { id: 'library', title: 'Start from an animation', icon: 'library', text: 'Pick any WickedWhims animation you have and make your own version of it.',
      onClick: () => { hideHome(app); app.showStep('library'); } },
    { id: 'tray', title: 'With my own sims', icon: 'couple', text: 'Load sims from your Tray with their body shape and skin.',
      onClick: () => { app.newScene(true, true, 'couple', () => { hideHome(app); app.showStep('scene'); app.openTray(); }); } },
  ];
  // cards other parts of the app add (a failing one is skipped)
  for (const fn of (app.hooks && app.hooks.homeCards) || []) {
    try {
      for (const c of fn(app) || []) {
        if (!c || !c.title || cards.some(x => x.id && x.id === c.id)) continue;
        cards.push({ ...c, hook: true, big: false, wide: !!(c.big || c.wide) });     // a big extra card is a wide one
      }
    }
    catch (e) { console.error('home card', e); }
  }
  return cards;
}

// Three ready poses Magic can make, as pictures (they render in the background; filled in when ready)
function magicStrip(app) {
  const strip = h('div', { class: 'magic-strip', 'aria-hidden': 'true' });
  const ids = ['cowgirl', 'missionary', 'doggy'];
  const slots = ids.map(() => h('div', { class: 'ms skel' }));
  strip.append(...slots);
  let tries = 0;
  const fill = () => {
    if (!strip.isConnected && tries > 0) return;
    let missing = 0;
    ids.forEach((id, k) => {
      if (slots[k].querySelector('img')) return;
      const pr = (app.posePresets || []).find(x => x.id === id && !x.mine);
      const src = pr && app.poseThumb && app.poseThumb(pr);
      if (src) { const img = h('img', { src, alt: '', class: 'fade' }); img.onload = () => img.classList.add('in'); slots[k].classList.remove('skel'); slots[k].append(img); }
      else missing++;
    });
    if (missing && ++tries < 60) setTimeout(fill, 500);
    else if (missing) slots.forEach(s => { if (!s.querySelector('img')) { s.classList.remove('skel'); s.append(icon('pose')); } });
  };
  setTimeout(fill, 0);
  return strip;
}

function cardEl(c, i) {
  const pills = c.pills ? h('div', { class: 'start-pills' }, c.pills.map(p => h('button', { class: 'chipbtn start-pill', type: 'button',
    onclick: e => { e.stopPropagation(); p.onClick(); } }, p.label))) : null;
  const el = h(c.pills ? 'div' : 'button', {
    class: 'start' + (c.cls ? ' ' + c.cls : '') + (c.big ? ' big' : '') + (c.wide ? ' wide' : '') + (c.hook ? ' hooked' : ''),
    'data-card': c.id || null, type: c.pills ? null : 'button', style: { '--i': Math.min(i, 8) },
    onclick: c.pills ? null : () => c.onClick && c.onClick() },
  c.art || null, h('div', { class: 'ic' }, icon(c.icon || 'spark')), h('b', {}, c.title, c.badge ? h('span', { class: 'beta' }, c.badge) : null), c.text ? h('small', {}, c.text) : null, pills);
  return el;
}

// Lay the cards out with no holes: Magic 2 x 2 on the left; the four slots beside it; then full rows of four (the
// last card of a short row stretches).
function layoutStarts(grid, cards) {
  const els = cards.map(cardEl);
  const small = cards.map((c, i) => [c, els[i]]).filter(([c]) => !c.big);
  let used = 0;
  const slots = c => (c.wide ? 2 : 1);
  const beside = [], rest = [];
  for (const pair of small) { if (used + slots(pair[0]) <= 4) { beside.push(pair); used += slots(pair[0]); } else rest.push(pair); }
  // fewer than four slots filled beside Magic: the first card grows to fill them
  if (used < 4 && beside.length) {
    const [c, el] = beside[0];
    const need = 4 - used;
    if (c.wide || need >= 2) el.style.gridRow = 'span 2';
    else el.style.gridColumn = 'span 2';
  }
  // the rows under: the last card of a short row stretches to the end; these cards are flat (one line high)
  let col = 0;
  rest.forEach(([c, el], k) => {
    el.classList.add('flat');
    const w = Math.min(4, slots(c));
    if (col + w > 4) col = 0;
    col += w;
    if (k === rest.length - 1 && col < 4) el.style.gridColumn = `span ${w + 4 - col}`;
    else if (w === 2) el.style.gridColumn = 'span 2';
    if (col >= 4) col = 0;
  });
  grid.append(...els);
}

function svgArt(inner) {
  const box = document.createElement('div');
  box.innerHTML = `<svg class="art" viewBox="0 0 84 64" aria-hidden="true">${inner}</svg>`;
  return box.firstChild;
}

function emptyState(title, text, button, art = 'film') {
  return h('div', { class: 'empty-state' },
    svgArt(art === 'chain'
      ? '<g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="6" y="20" width="22" height="24" rx="6"/><rect x="56" y="20" width="22" height="24" rx="6"/><g class="float"><rect x="31" y="14" width="22" height="24" rx="6" opacity=".7"/></g><path d="M28 32h3M53 32h3" opacity=".6"/></g>'
      : '<g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="8" y="12" width="68" height="42" rx="8" opacity=".55"/><g class="float"><path d="M36 25v16l13-8z" fill="currentColor" opacity=".9"/></g><path d="M8 46h68" opacity=".35"/></g>'),
    h('b', {}, title), h('p', {}, text), button || null);
}

let introShown = false;
try { introShown = !!sessionStorage.getItem('wa.homeIntro'); } catch { /* storage blocked */ }

export async function showHome(app) {
  const root = $('home');
  const wasHidden = root.classList.contains('hidden');
  const build = () => {
    root.classList.remove('hidden');
    setStepMark(app, true);
    app._moveGlider?.();
    root.innerHTML = '';
  };
  if (wasHidden && canTransition()) { try { await document.startViewTransition(build).updateCallbackDone; } catch { build(); } }
  else build();
  const hasWork = app.store.project.sims.some(s => s.keys.length > 1 || (s.layers || []).length);

  const projGrid = h('div', { class: 'projects' }, ...Array.from({ length: 4 }, () => h('div', { class: 'skel-card' }, h('div', { class: 'skel' }),
    h('div', { class: 'meta' }, h('div', { class: 'skel skel-line', style: { width: '70%' } }), h('div', { class: 'skel skel-line', style: { width: '45%' } })))));
  const progGrid = h('div', { class: 'home-progs' });
  const starts = h('div', { class: 'starts home-grid' });
  layoutStarts(starts, startCards(app));
  const inner = h('div', { class: 'home-inner' },
    h('div', { class: 'home-top' },
      h('img', { src: 'img/logo.svg', class: 'logo', alt: '' }),
      h('div', {}, h('h1', {}, 'Novulon\'s ', h('span', {}, 'Wicked Animator')), h('p', {}, 'Make WickedWhims animations without Blender - pose, add motion, send to the game.')),
      h('div', { class: 'grow' }),
      h('button', { class: 'btn ghost', onclick: () => app.open() }, icon('open'), 'Open...'),
      app.store.project.sims.length ? h('button', { class: 'btn primary', onclick: () => hideHome(app) }, hasWork ? `Continue "${app.store.project.name}"` : 'Go to the editor', icon('arrow')) : null),
    h('h3', {}, 'Start something new'),
    starts,
    h('h3', { class: 'with-action' }, h('span', {}, 'Your animations'), h('div', { class: 'grow' }),
      h('button', { class: 'btn small ghost', onclick: () => { hideHome(app); app.showStep('share'); } }, icon('package'), 'Share a mod')),
    projGrid,
    h('h3', {}, 'Your progressions'), progGrid,
    h('h3', {}, 'How it works'),
    h('div', { class: 'starts how' },
      ...[['1', 'Pose', 'One click on a ready pose (cowgirl, missionary, doggy...). Drag hands and feet to adjust - pinned ones stay put.'],
        ['2', 'Move', 'Add Thrust, Ride or Head bob. Set how often and how hard. It loops perfectly by itself.'],
        ['3', 'It comes alive', 'Physics, opening holes, blinking, faces and sounds are automatic - switch any of them off.'],
        ['4', 'Play it', 'Send to game, restart The Sims 4, pick it in WickedWhims. Or export a mod to share.']].map(([n, t, s]) =>
        h('div', { class: 'start static' }, h('div', { class: 'ic num' }, h('b', {}, n)), h('b', {}, t), h('small', {}, s)))));
  root.append(inner);
  // the first time Home opens in a session its parts rise in one after another
  if (!introShown && !reducedMotion()) {
    introShown = true;
    try { sessionStorage.setItem('wa.homeIntro', '1'); } catch { /* storage blocked */ }
    [...inner.children].forEach((c, i) => c.style.setProperty('--i', Math.min(i, 8)));
    root.classList.add('intro');
    setTimeout(() => root.classList.remove('intro'), 1400);
  }
  emitWA(app, 'home', { shown: true });
  finishSplash();

  try {
    const [list, progs] = await Promise.all([api.projects(), api.progressions()]);
    if (!projGrid.isConnected) return;
    projGrid.innerHTML = '';
    if (!list.length) projGrid.append(emptyState('Your animations show up here', 'Make one in a single click with Magic, or start from a pose. Save with Ctrl+S.',
      h('button', { class: 'btn primary', onclick: () => { hideHome(app); app.openMagic(); } }, icon('wand'), 'Make a Magic animation')));
    // every way of opening goes through here: unsaved work is never thrown away without asking
    const open = async (m, card) => {
      if (app.store.dirty && m.uid !== app.store.project.uid && !(await confirmBox('Open another animation?', 'Unsaved changes to the one open now will be lost.', 'Open', true))) return;
      await app.loadProject(m.file, { from: card ? card.querySelector('.thumb') : null });
    };
    for (const m of list) {
      const img = m.has_thumb ? h('img', { src: api.thumbUrl(m.file), alt: '', loading: 'lazy', class: 'fade' }) : null;
      if (img) { img.onload = () => img.classList.add('in'); img.onerror = () => img.classList.add('in'); if (img.complete && img.naturalWidth) img.classList.add('in'); }
      const card = h('div', { class: 'proj', tabindex: '0', onclick: () => open(m, card), onkeydown: e => { if (e.key === 'Enter') open(m, card); },
        oncontextmenu: e => { e.preventDefault(); contextMenu(e.clientX, e.clientY, [
        { label: 'Open', icon: 'open', onClick: () => open(m, card) },
        { label: 'Remove from the list', icon: 'trash', danger: true, onClick: async () => {
          if (!(await confirmBox('Remove this animation?', `"${m.name}" is moved to a backup folder (not deleted).`, 'Remove', true))) return;
          try { await api.removeProject(m.file); } catch (err) { toast('Could not remove it: ' + err.message, 'err'); return; }
          app.shareData = null;
          card.remove(); toast('Removed (a backup is kept).');
        } }]); } },
        h('div', { class: 'thumb' }, img || icon('scene')),
        h('div', { class: 'info' }, h('b', {}, m.name), h('span', {}, `${m.author ? 'by ' + m.author + ' · ' : ''}${new Date(m.modified * 1000).toLocaleDateString()}`),
          h('div', { class: 'row' }, h('span', { class: 'chip hot' }, kindName(m.category)), h('span', { class: 'chip' }, `${m.sims} sims`), h('span', { class: 'chip' }, `${(m.length / (m.fps || 30)).toFixed(1)} s`))));
      projGrid.append(card);
    }
    const byUid = Object.fromEntries(list.map(p => [p.uid, p]));
    if (!progs.length) progGrid.append(emptyState('Chain animations into a story', 'e.g. oral → handjob → cowgirl. Each keeps its own kind and tags.',
      h('button', { class: 'btn', onclick: () => { hideHome(app); app.showStep('share'); } }, icon('chain'), 'Make a progression'), 'chain'));
    for (const g of progs) {
      const flow = h('div', { class: 'prog-flow' });
      g.steps.forEach((u, i) => { if (i) flow.append(icon('arrow')); flow.append(h('span', { class: 'st' }, byUid[u]?.name || '?')); });
      if (g.repeat) flow.append(icon('loop'));
      progGrid.append(h('div', { class: 'prog-card' }, h('h4', {}, icon('chain'), g.name), h('span', { class: 'muted' }, `${g.steps.length} step${g.steps.length === 1 ? '' : 's'}`), flow,
        h('button', { class: 'btn small', onclick: () => { hideHome(app); app.showStep('share'); } }, 'Edit')));
    }
  } catch (e) {
    projGrid.innerHTML = '';
    projGrid.append(h('div', { class: 'warn-box' }, 'Could not load your animations: ' + e.message));
  }
}
