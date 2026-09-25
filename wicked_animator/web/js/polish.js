// "Velvet Stage": the app's look and feel, plugged in from outside main.js (design.md). It listens to the app's
// events (wa:step, wa:rendered, wa:selection, wa:undo, wa:saved, wa:project, wa:sent...) and, where an event is not
// there, watches the page itself, so every part works with or without them:
//   step transitions and the rail glider · lighting looks (app.setLook) and the Light button · cinematic mode in
//   Showcase · the selected sim's rim light (and a flash on undo) · the "Fast mode" chip · the command palette
//   (Ctrl+K) and the search pill · tooltips with shortcut chips, hold-Ctrl key tips and the live hint row
//   (app.hint) · celebrations when an animation reaches the game · thumbnails that fade in · empty states.
// Nothing here may break the app: every part is wrapped, and a failure is only logged.
import { h, icon, addToolbarButton, dialogOpen } from './ui.js';
import { installTooltips, installKeyTips } from './tooltip.js';
import { openPalette, paletteOpen } from './palette.js';
import { allCommands } from './commands.js';
import { successHero, celebrateAt, rain, firstCard, reducedMotion } from './fx.js';
import { LOOKS, addRim } from './stage.js';

const $ = id => document.getElementById(id);
const ORDER = ['scene', 'pose', 'motion', 'body', 'face', 'sounds', 'details', 'share', 'library'];
const safe = (name, fn) => { try { return fn(); } catch (e) { console.error(`polish: ${name} failed`, e); return undefined; } };
const on = (name, fn) => addEventListener('wa:' + name, e => safe(name, () => fn(e.detail || {}, e)));

// ---------------------------------------------------------------- start as soon as the app object exists
function whenApp(fn) {
  const t = () => (window.app && window.app.vp ? safe('install', () => fn(window.app)) : setTimeout(t, 0));
  t();
}
whenApp(install);

function install(app) {
  if (app._polish) return;
  app._polish = true;
  ensureHooks(app);
  safe('tooltips', () => { installTooltips(); installKeyTips(); });
  safe('palette', () => installPalette(app));
  safe('steps', () => installSteps(app));
  safe('looks', () => installLooks(app));
  safe('rim', () => installRim(app));
  safe('quality', () => installQuality(app));
  safe('hints', () => installHints(app));
  safe('celebrations', () => installCelebrations(app));
  safe('fades', () => installFades());
  safe('empty', () => installEmptyStage(app));
  safe('inspector', () => installInspectorStrip(app));
  safe('kbd hints', () => installKbdHints());
  safe('home stage', () => installHomeStage(app));
}

// ---------------------------------------------------------------- Home over the live stage
// Behind Home's glass the stage keeps playing: your animation in slow motion (no sound), or - for a new, empty
// one - a couple in a ready pose, in the Candle look with a slow Showcase orbit. Off with reduced motion, in Fast
// mode and in automated test browsers; everything is put back the moment Home closes (camera, look, frame,
// playback), so it costs nothing while the editor is open.
function installHomeStage(app) {
  let live = null;
  const allowed = () => !reducedMotion() && (!navigator.webdriver || /[?&]homestage=1\b/.test(location.search))
    && app.vp && app.vp.stage && (app.vp.qualityLevel || 0) === 0 && !app.vp.paused && document.visibilityState === 'visible';
  const demoPoses = () => {
    const pr = (app.posePresets || []).find(x => x.id === 'kiss' && !x.mine) || (app.posePresets || []).find(x => x.group === 'couple' && !x.mine);
    if (!pr) return null;
    const free = [...app.store.project.sims], out = [];
    for (const ps of pr.sims) {
      const want = ps.gender === 'MALE' ? ['ym', 'yf_futa'] : ['yf'];
      let i = free.findIndex(s => want.includes(s.frame));
      if (i < 0) i = free.length ? 0 : -1;
      if (i < 0) break;
      out.push([free.splice(i, 1)[0].id, ps.pose]);
    }
    return out.length ? out : null;
  };
  const start = () => {
    if (live || !allowed() || !app.simViews || !app.simViews.size || !app.store) return;
    const p = app.store.project;
    const moving = p.sims.some(s => (s.layers || []).some(l => l.on) || s.keys.length > 1);
    const demo = moving ? null : demoPoses();
    if (!moving && !demo) return;
    live = { project: p, view: app.vp.savedView(), speed: app.speed, playing: app.playing, frame: app.store.frame, demo, ang: null, centre: null };
    if (app._showStep) app.showcase(false);
    document.body.classList.add('home-live');
    app.vp.stage.apply('candle');
    if (moving) { app.speed = 0.45; if (!app.playing) app.setPlaying(true); }      // below half speed: no sounds
    else app.applyPoses?.(false);
  };
  const stop = () => {
    if (!live) return;
    const l = live; live = null;
    document.body.classList.remove('home-live');
    app.speed = l.speed;
    if (!l.playing && app.playing) app.setPlaying(false);
    if (app.store.project === l.project) { if (!l.playing) app.setFrame?.(l.frame); }
    const look = app.store.project && app.store.project.look;
    if (app.setLook) app.setLook(look || 'studio', { remember: false }); else app.vp.stage.apply(look || 'studio');
    app.vp.stopCamera();
    if (app.store.project === l.project) app.vp.controls.lookFrom(l.view.pos, l.view.target);
    app.applyPoses?.(false);
  };
  // the demo pose goes on after the app has posed the sims (it never touches the animation itself)
  if (app.hooks && Array.isArray(app.hooks.afterApply)) app.hooks.afterApply.push(() => {
    if (!live || !live.demo) return;
    for (const [id, pose] of live.demo) { const v = app.simViews.get(id); if (v) { v.resetPose(); v.setPose(pose); } }
  });
  app.vp.onFrame.push(dt => {
    if (!live) return;
    if (!allowed() || $('home').classList.contains('hidden')) { stop(); return; }
    if (!live.centre) {
      const c = [];
      for (const [, v] of app.simViews) if (v.group.visible && v.bone('b__Pelvis__')) { v.group.updateMatrixWorld(true); c.push(v.worldPos('b__Pelvis__')); }
      if (!c.length) return;
      live.centre = c.reduce((a, b) => a.add(b), c[0].clone().multiplyScalar(0)).multiplyScalar(1 / c.length);
      const cam = app.vp.camera.position;
      live.ang = Math.atan2(cam.x - live.centre.x, cam.z - live.centre.z);
    }
    live.ang += dt * 0.12;
    const cx = live.centre, pos = cx.clone();
    pos.x += Math.sin(live.ang) * 3.1; pos.z += Math.cos(live.ang) * 3.1; pos.y = cx.y + 0.45 + Math.sin(live.ang * 0.6) * 0.12;
    app.vp.controls.lookFrom(pos, cx.clone().setY(cx.y + 0.05));
  });
  on('home', d => { if (d.shown) setTimeout(start, 60); else stop(); });
}

// Small key chips in the two most used buttons (shown on wide windows): Key pose [K], Save [Ctrl S]
function installKbdHints() {
  for (const [id, keys] of [['btn-key', ['K']], ['btn-save', ['Ctrl', 'S']]]) {
    const b = $(id);
    if (b && !b.querySelector('.kbd-hint')) b.append(h('kbd', { class: 'kbd-hint', 'aria-hidden': 'true' }, keys.join(' ')));
  }
}

// The registries R1-C reads (plan 2.4); the app normally makes them, this only fills in what is missing.
function ensureHooks(app) {
  app.hooks = app.hooks || {};
  for (const k of ['homeCards', 'commands', 'helpRows']) if (!Array.isArray(app.hooks[k])) app.hooks[k] = [];
}

// ---------------------------------------------------------------- command palette
function installPalette(app) {
  const open = () => {
    if (dialogOpen() || paletteOpen()) return;
    openPalette(() => allCommands(app), {
      onSearchLibrary: q => {
        app.showStep('library');
        const box = app.library && (app.library.el?.search || app.library.root?.querySelector('input'));
        if (box) { box.value = q; box.dispatchEvent(new Event('input', { bubbles: true })); app.library.search?.(); }
      },
    });
  };
  app.openPalette = open;
  // Ctrl+K anywhere (also while typing in a box), never over a dialog; the app's own shortcuts never see it
  addEventListener('keydown', e => {
    if (!(e.ctrlKey || e.metaKey) || e.code !== 'KeyK' || e.altKey) return;
    e.preventDefault(); e.stopImmediatePropagation();
    if (paletteOpen()) return;
    if (!dialogOpen()) open();
  }, true);
  const pill = $('btn-palette');
  if (pill) pill.addEventListener('click', () => { pill.blur(); open(); });
}

// ---------------------------------------------------------------- steps: transitions, glider, density
function installSteps(app) {
  const rail = $('rail'), left = $('left');
  if (!rail || !left) return;
  let glider = rail.querySelector('.rail-glider');
  if (!glider) { glider = h('div', { class: 'rail-glider off', 'aria-hidden': 'true' }); rail.prepend(glider); }
  rail.classList.add('has-glider');
  const moveGlider = () => {
    const homeOpen = !$('home').classList.contains('hidden');
    const b = homeOpen ? null : rail.querySelector('button.active[data-step]');
    if (!b) { glider.classList.add('off'); return; }
    glider.classList.remove('off');
    glider.style.setProperty('--gy', b.offsetTop + 'px');
    glider.style.setProperty('--gh', b.offsetHeight + 'px');
  };
  app._moveGlider = moveGlider;
  addEventListener('resize', () => moveGlider());

  let last = app.step || null, enterT = 0;
  const entered = (prev, step) => {
    if (!step || step === last) return;
    const from = last;
    last = step;
    document.body.dataset.step = $('home').classList.contains('hidden') ? step : 'home';
    moveGlider();
    if (!from || reducedMotion()) return;
    left.dataset.dir = ORDER.indexOf(step) >= ORDER.indexOf(from) ? 'fwd' : 'back';
    left.classList.remove('entering'); void left.offsetWidth; left.classList.add('entering');
    clearTimeout(enterT); enterT = setTimeout(() => left.classList.remove('entering'), 650);
  };
  on('step', d => entered(d.prev, d.step));
  // without the event: the rail's active button tells which step is shown
  new MutationObserver(() => {
    const b = rail.querySelector('button.active[data-step]');
    if (b) entered(last, b.dataset.step); else moveGlider();
  }).observe(rail, { subtree: true, attributes: true, attributeFilter: ['class'] });
  // the stagger index of the panel's top-level blocks (the entrance only runs while #left.entering)
  const stagger = root => { if (root) [...root.children].forEach((c, i) => c.style.setProperty('--i', Math.min(i, 8))); };
  on('rendered', d => stagger(d.root || $('panel-body')));
  new MutationObserver(() => stagger($('panel-body'))).observe($('panel-body'), { childList: true });
  new MutationObserver(() => { document.body.dataset.step = $('home').classList.contains('hidden') ? (app.step || 'scene') : 'home'; moveGlider(); })
    .observe($('home'), { attributes: true, attributeFilter: ['class'] });
  document.body.dataset.step = $('home').classList.contains('hidden') ? (app.step || 'scene') : 'home';
  requestAnimationFrame(moveGlider);
  // the unsaved dot turns into a green tick for a moment after saving
  const tick = () => { const d = $('dirty-dot'); if (!d) return; d.classList.remove('saved'); void d.offsetWidth; d.classList.add('saved'); setTimeout(() => d.classList.remove('saved'), 1500); };
  let sawSaved = false;
  on('saved', () => { sawSaved = true; tick(); });
  new MutationObserver(recs => {
    if (sawSaved) return;
    for (const r of recs) for (const n of r.addedNodes) if (n.nodeType === 1 && /^Saved\b/.test(n.textContent || '')) tick();
  }).observe($('toasts'), { childList: true, subtree: true });
}

// ---------------------------------------------------------------- lighting looks
function installLooks(app) {
  const stage = app.vp.stage;
  if (!stage) return;
  let current = 'studio';
  const apply = id => { current = stage.apply(id); markPop(); return current; };
  // app.setLook(id): the look of the stage, remembered in the animation (project.look) so recordings match
  app.setLook = (id, { remember = true } = {}) => {
    if (!LOOKS[id]) id = 'studio';
    apply(id);
    const p = app.store && app.store.project;
    if (remember && p && p.look !== id) {
      p.look = id;
      if (app.store.setDirty) app.store.setDirty(true);
    }
    return id;
  };
  app.getLook = () => current;
  let lastProject = null;
  const follow = () => {
    const p = app.store && app.store.project;
    if (!p || p === lastProject) return;
    lastProject = p;
    const want = LOOKS[p.look] ? p.look : 'studio';
    if (want !== current) apply(want);
  };
  on('project', follow);
  app.vp.onFrame.push(() => follow());         // one pointer compare per frame (undo/redo, load, new)

  // the Light button and its popover
  let pop = null;
  const close = () => { if (pop) { pop.remove(); pop = null; btn && btn.classList.remove('on'); } };
  const markPop = () => { if (pop) pop.querySelectorAll('button[data-look]').forEach(b => b.classList.toggle('on', b.dataset.look === current)); };
  const openPop = () => {
    if (pop) return close();
    pop = h('div', { class: 'light-pop', role: 'menu' }, h('div', { class: 'lp-title' }, 'Lighting'),
      ...Object.entries(LOOKS).map(([k, l]) => h('button', { 'data-look': k, role: 'menuitemradio', class: k === current ? 'on' : '',
        onclick: () => { app.setLook(k); } },
      h('span', { class: 'sw', style: { background: `radial-gradient(120% 90% at 30% 20%, ${l.key[0]} 0%, transparent 55%), radial-gradient(90% 90% at 90% 90%, ${l.rim[0]} 0%, transparent 60%), linear-gradient(180deg, ${l.sky[0]}, ${l.sky[1]})` } }),
      h('span', {}, h('b', {}, l.label), h('small', {}, l.sub)))));
    $('viewport-wrap').append(pop);
    btn && btn.classList.add('on');
    setTimeout(() => addEventListener('pointerdown', outside, true), 0);
  };
  const outside = e => { if (pop && !pop.contains(e.target) && e.target !== btn && !btn.contains(e.target)) { close(); removeEventListener('pointerdown', outside, true); } };
  const btn = addToolbarButton({ cell: 'view', id: 'btn-light', icon: 'light', title: 'Lighting: Studio, Boudoir, Neon night, Daylight or Candle', onClick: openPop, before: '#btn-onion' });
  addEventListener('keydown', e => { if (e.key === 'Escape' && pop) close(); });

  // cinematic mode (bloom, vignette, letterbox) while Showcase runs
  const sc = $('btn-showcase');
  if (sc) new MutationObserver(() => stage.cinematic(sc.classList.contains('on') || document.body.classList.contains('recording')))
    .observe(sc, { attributes: true, attributeFilter: ['class'] });
}

// ---------------------------------------------------------------- selected sim: rim light, undo flash
function installRim(app) {
  const state = new WeakMap();
  const flash = new Map();                       // sim id -> 0..1
  const setRim = (v, color, a) => {
    if (typeof v.setRim === 'function') { v.setRim(color, a); return; }
    if (a <= 0 && !v.material?.userData?.waRim) return;          // never compiled a rim: nothing to switch off
    const r = addRim(v.material, color);
    r.rim.value = a; r.rimColor.value.set(color);
  };
  on('undo', d => { for (const id of d.simIds || []) flash.set(id, 1); });
  // the inspector cross-fades when another sim or part is selected
  let lastSel = '';
  const swap = key => {
    if (key === lastSel) return;
    const had = lastSel; lastSel = key;
    const insp = $('inspector');
    if (!had || !insp || reducedMotion()) return;
    insp.classList.remove('swap'); void insp.offsetWidth; insp.classList.add('swap');
    clearTimeout(swap.t); swap.t = setTimeout(() => insp.classList.remove('swap'), 200);
  };
  on('selection', d => swap(`${d.simId || ''}|${d.bone || ''}`));
  app.vp.onFrame.push(dt => {
    if (!app.simViews) return;
    const sel = app.store.selected && app.store.selected.sim;
    // no rim while Home covers the stage (nothing to see, and no shader work while the app starts), while recording,
    // in cinematic mode or while a library animation is previewed
    const quiet = document.body.classList.contains('recording') || document.body.classList.contains('cinematic') || !!app.preview
      || document.body.dataset.step === 'home';
    const k = Math.min(1, dt / 0.2 * 2.6);       // about 200 ms
    for (const [id, v] of app.simViews) {
      let st = state.get(v);
      if (!st) { st = { amt: 0, last: -1, color: '' }; state.set(v, st); }
      const target = !quiet && id === sel && app.simViews.size > 0 ? 0.5 : 0;
      st.amt += (target - st.amt) * k;
      if (Math.abs(st.amt - target) < 0.004) st.amt = target;
      let f = flash.get(id) || 0;
      if (f > 0) { f = Math.max(0, f - dt / 0.3); if (f) flash.set(id, f); else flash.delete(id); }
      const a = Math.min(1, st.amt + f * 0.7);
      const color = (app.store.sim(id) || {}).color || v.color || '#ff8cc4';
      if (Math.abs(a - st.last) > 0.003 || color !== st.color) { setRim(v, color, a); st.last = a; st.color = color; }
    }
  });
}

// ---------------------------------------------------------------- adaptive quality: the "Fast mode" chip
function installQuality(app) {
  const vp = app.vp;
  let keep = false;
  try { keep = JSON.parse(localStorage.getItem('fsa.keepQuality') || 'false'); } catch { /* blocked */ }
  if (keep) vp.keepQuality = true;
  let chip = null;
  vp.onQuality = (level, text) => {
    if (!level) { if (chip) { chip.remove(); chip = null; } return; }
    if (!chip) {
      chip = h('div', { class: 'fast-chip', role: 'status' });
      $('viewport-wrap').append(chip);
    }
    chip.innerHTML = '';
    chip.append(icon('bolt'), h('span', {}, text), h('button', { class: 'btn small ghost', title: 'Best picture again (it stays that way)', onclick: () => {
      vp.keepQuality = true;
      try { localStorage.setItem('fsa.keepQuality', 'true'); } catch { /* blocked */ }
      vp.setQualityLevel(0);
    } }, 'Full quality'));
  };
}

// ---------------------------------------------------------------- the live hint row (app.hint)
const HINTS = {
  ring: '<b>Drag the ring</b> to turn · <kbd>Esc</kbd> lets go · <b>Right-drag</b> look',
  timeline: '<b>Double-click</b> a lane: key · <b>Wheel</b> zoom · <kbd>Shift</kbd>+<b>wheel</b> scroll',
  place: '<kbd>T</kbd> move / turn · <b>Drag</b> the arrows · <kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> fly',
};
function installHints(app) {
  const row = $('vp-cam');
  if (!row) return;
  const base = row.innerHTML;
  let shown = null, forced = null, overTl = false;
  const set = ctx => {
    const key = ctx && typeof ctx === 'object' ? JSON.stringify(ctx) : ctx || '';
    if (key === shown) return;
    shown = key;
    if (!ctx) row.innerHTML = base;
    else if (typeof ctx === 'object') { row.innerHTML = ''; row.append(ctx.html ? h('span', { html: ctx.html }) : h('span', {}, ctx.text || '')); }
    else row.innerHTML = HINTS[ctx] || base;
    row.dataset.hint = typeof ctx === 'string' ? ctx : ctx ? 'custom' : '';
    fitHud();
  };
  // The message box (bottom left, #vp-hud) and the hint row (bottom right) never overlap: the message gets the
  // width left beside the row; when that is too narrow for it, it moves up above the row instead.
  const hud = $('vp-hud'), wrap = $('viewport-wrap');
  const fitHud = () => {
    if (!hud || !wrap) return;
    const W = wrap.clientWidth, rowW = row.offsetParent ? row.offsetWidth : 0;
    const beside = W - rowW - (rowW ? 14 + 14 + 12 : 28);
    if (!rowW || beside >= 300) { hud.style.maxWidth = beside + 'px'; hud.style.bottom = ''; }
    else { hud.style.maxWidth = (W - 28) + 'px'; hud.style.bottom = (14 + row.offsetHeight + 8) + 'px'; }
  };
  if (window.ResizeObserver) { const ro = new ResizeObserver(() => fitHud()); ro.observe(row); if (wrap) ro.observe(wrap); }
  fitHud();
  // app.hint(ctx): 'ring' | 'timeline' | 'place' | {text} | {html}; null = the camera keys again
  app.hint = ctx => { forced = ctx || null; set(forced); };
  const tl = $('timeline');
  if (tl) { tl.addEventListener('pointerenter', () => { overTl = true; }); tl.addEventListener('pointerleave', () => { overTl = false; }); }
  app.vp.onFrame.push(() => {
    if (forced) return;
    const tool = app.interact && app.interact.tool;
    set(app.vp.dragging ? 'ring' : overTl ? 'timeline' : tool === 'move' ? 'place' : null);
  });
}

// ---------------------------------------------------------------- celebrations
function installCelebrations(app) {
  // Send to game succeeded: the success tick and a burst, or - for the very first animation - the "Creator #1" card
  // with a plumbob rain. The dialog is the app's; this only fills its hero slot.
  on('sent', d => {
    const slot = d.heroSlot;
    if (!slot) return;
    const p = d.project || app.store.project || {};
    slot.innerHTML = '';
    slot.classList.add('hero-slot');
    if (d.first) {
      let thumb = p.thumb || null;
      if (!thumb) { try { thumb = app.vp.snapshot(); } catch { thumb = null; } }
      slot.append(firstCard({ thumb, name: p.name, author: p.author }), h('h3', { class: 'hero-title' }, 'Your first animation is in the game!'));
      rain();
    } else {
      const hero = successHero();
      slot.append(hero, h('h3', { class: 'hero-title' }, `"${p.name || 'Your animation'}" by ${p.author || 'you'} is ready`));
      celebrateAt(hero, { delay: 480 });
    }
  });
}

// ---------------------------------------------------------------- thumbnails fade in (dialogs: Tray, Open...)
function installFades() {
  const root = $('modal-root');
  if (!root) return;
  const fade = img => {
    if (img.classList.contains('fade') || /^data:/.test(img.getAttribute('src') || '') || img.closest('.first-card, .success-hero')) return;
    if (img.complete && img.naturalWidth) return;
    img.classList.add('fade');
    const done = () => img.classList.add('in');
    img.addEventListener('load', done, { once: true });
    img.addEventListener('error', done, { once: true });
    setTimeout(done, 4000);
  };
  new MutationObserver(recs => {
    for (const r of recs) for (const n of r.addedNodes) {
      if (n.nodeType !== 1) continue;
      if (n.tagName === 'IMG') fade(n); else n.querySelectorAll && n.querySelectorAll('img').forEach(fade);
    }
  }).observe(root, { childList: true, subtree: true });
}

// ---------------------------------------------------------------- the stage with nobody on it
function installEmptyStage(app) {
  let card = null;
  const check = () => {
    const n = app.store && app.store.project ? app.store.project.sims.length : 1;
    if (n > 0 || !app.addSim) { if (card) { card.remove(); card = null; } return; }
    if (card) return;
    const tile = (frame, label) => h('button', { class: 'add-tile', onclick: () => app.addSim(frame) }, icon('user'), label);
    card = h('div', { class: 'vp-empty' }, h('b', {}, 'Add a sim'), h('p', {}, 'Who is in this animation?'),
      h('div', { class: 'add-grid' }, tile('yf', 'Female'), tile('ym', 'Male'), tile('yf_futa', 'Female + penis')),
      app.openTray ? h('button', { class: 'btn block vp-tray', onclick: () => app.openTray() }, icon('folder'), 'Use a sim from my Tray') : null);
    $('viewport-wrap').append(card);
  };
  let t = 0;
  app.vp.onFrame.push(dt => { t += dt; if (t > 0.25) { t = 0; check(); } });
}

// ---------------------------------------------------------------- inspector strip (Details, Share, Library)
// Those steps need no per-frame controls: the inspector folds to a thin strip with a button to open it anyway.
function installInspectorStrip() {
  const right = $('right');
  if (!right || right.querySelector('.insp-strip')) return;
  const strip = h('button', { class: 'insp-strip', title: 'Show the sim\'s details', 'aria-label': 'Show the inspector',
    onclick: () => document.body.classList.toggle('insp-open') }, icon('dots'));
  right.prepend(strip);
  new MutationObserver(() => document.body.classList.remove('insp-open')).observe(document.body, { attributes: true, attributeFilter: ['data-step'] });
}
