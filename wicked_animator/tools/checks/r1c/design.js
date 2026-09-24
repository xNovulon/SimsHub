// R1-C design check (plan section 3, "R1-C" checks 1-11):
//   splash · reduced motion · palette · tooltips · stage · celebrations · dialogs · Magic placement (placement.js) ·
//   layout at 1366x768 · performance · screenshots + gallery.
//   node tools/checks/r1c/design.js --port 8843 [--only 1,3,5] [--skip-shots]
// Writes nothing outside cache/checks/r1c: every writing route is answered inside the browser.
const path = require('path'), fs = require('fs'), cp = require('child_process');
const L = require('./lib.js');

const PORT = L.argPort();
const ONLY = process.argv.includes('--only') ? new Set(process.argv[process.argv.indexOf('--only') + 1].split(',').map(Number)) : null;
const SKIP_SHOTS = process.argv.includes('--skip-shots');
const run = n => !ONLY || ONLY.has(n);
const OUT = L.OUT, AFTER = path.join(OUT, 'after');
const T = L.table();
const info = {};
const noTour = pg => pg.evaluateOnNewDocument(() => { try { localStorage.setItem('fsa.tourDone', 'true'); } catch { } });
const median = a => { const b = [...a].sort((x, y) => x - y); return b[Math.floor(b.length / 2)]; };
const pct = (a, p) => { const b = [...a].sort((x, y) => x - y); return b[Math.min(b.length - 1, Math.floor(b.length * p))]; };

async function openApp(opts = {}) {
  const o = await L.open(PORT, { ...opts, beforeLoad: async pg => { await noTour(pg); if (opts.beforeLoad) await opts.beforeLoad(pg); } });
  await o.page.waitForFunction(() => window.app && window.app._polish, { timeout: 60000 });
  return o;
}
const toEditor = page => page.evaluate(() => { const b = [...document.querySelectorAll('#home button')].find(x => /editor|Continue/.test(x.textContent)); if (b) b.click(); else document.getElementById('home').classList.add('hidden'); });
const presets = page => page.waitForFunction(() => window.app && window.app.posePresets && window.app.posePresets.length, { timeout: 60000 });

// ------------------------------------------------------------------------------------------------ 1. splash
async function checkSplash() {
  // on the graphics card, as the desktop app runs (headless software rendering makes every frame slow)
  const browser = await L.launch({ w: 1366, h: 768, gpu: true });
  try {
    // time to #loading.done under webdriver: the app with R1-C's splash and polish vs the same app without them
    const readyOnce = async (block, timeout = 120000) => {
      const page = await browser.newPage();
      await page.setViewport({ width: 1366, height: 768 });
      await page.evaluateOnNewDocument(() => {
        new MutationObserver(() => { const l = document.getElementById('loading'); if (l && l.classList.contains('done') && !window.__doneAt) window.__doneAt = performance.now(); })
          .observe(document, { subtree: true, attributes: true, attributeFilter: ['class'], childList: true });
      });
      await page.setRequestInterception(true);
      page.on('request', r => {
        const u = r.url();
        // the baseline: no polish at all, and a splash module that does nothing (home.js still imports it)
        if (block && /\/js\/polish\.js/.test(u)) return r.respond({ status: 200, contentType: 'text/javascript', body: 'export {};' });
        if (block && /\/js\/splash\.js/.test(u)) return r.respond({ status: 200, contentType: 'text/javascript',
          body: 'export const splashProgress = () => {}, splashStatus = () => {}, waitShow = () => Promise.resolve(), finishSplash = () => Promise.resolve();' });
        if (r.method() === 'POST') return r.respond({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
        r.continue();
      });
      await page.goto(`http://127.0.0.1:${PORT}/?slot=test`, { waitUntil: 'domcontentloaded', timeout });
      await page.waitForFunction(() => window.__doneAt, { timeout });
      const ms = await page.evaluate(() => window.__doneAt);
      await page.close();
      return ms;
    };
    await readyOnce(false, 400000); await readyOnce(true, 400000);    // warm the server caches (a cold start can be slow)
    const withSplash = [], without = [];
    for (let i = 0; i < 7; i++) { without.push(await readyOnce(true)); withSplash.push(await readyOnce(false)); }
    info.readyWith = withSplash.map(Math.round); info.readyWithout = without.map(Math.round);
    T.check('1 splash: time to #loading.done under webdriver <= baseline + 50 ms', median(withSplash) <= median(without) + 50,
      `median ${Math.round(median(withSplash))} ms vs ${Math.round(median(without))} ms without splash/polish`);

    // the show itself (?splash=show plays it under webdriver); the app's start is held back 4 s so it can be seen
    const slowStart = async page => {
      await page.setRequestInterception(true);
      page.on('request', r => {
        if (/\/api\/rig/.test(r.url())) return setTimeout(() => r.continue(), 4000);
        if (r.method() === 'POST') return r.respond({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
        r.continue();
      });
    };
    let page = await browser.newPage();
    await page.setViewport({ width: 1366, height: 768 });
    await slowStart(page);
    await page.goto(`http://127.0.0.1:${PORT}/?slot=test&splash=show`, { waitUntil: 'domcontentloaded' });
    await L.sleep(250);
    for (const t of [300, 800, 1300]) {
      await page.evaluate(t => document.getAnimations().forEach(a => { try { a.pause(); a.currentTime = t; } catch { } }), t);
      await L.sleep(120);
      await L.shot(page, path.join(AFTER, `splash_${t}ms.png`));
    }
    const shown = await page.evaluate(() => !!document.getElementById('splash'));
    T.check('1 splash: shows while the app loads (?splash=show)', shown);
    await page.evaluate(() => document.getAnimations().forEach(a => { try { a.play(); } catch { } }));
    await page.waitForFunction(() => window.__splashGone, { timeout: 60000 });
    const gone = await page.evaluate(() => ({ ready: window.__splashReadyAt, gone: window.__splashGone, inDom: !!document.getElementById('splash'), done: document.getElementById('loading').classList.contains('done') }));
    T.check('1 splash: removed from the DOM within 700 ms of ready', !gone.inDom && gone.ready && gone.gone - gone.ready <= 700, `${Math.round(gone.gone - gone.ready)} ms after #loading.done`);
    await page.close();
    // a key press skips the show: the splash goes as soon as the app is ready (no wait, no transition)
    page = await browser.newPage();
    await page.setViewport({ width: 1366, height: 768 });
    await slowStart(page);
    await page.goto(`http://127.0.0.1:${PORT}/?slot=test&splash=show`, { waitUntil: 'domcontentloaded' });
    await L.sleep(300);
    await page.keyboard.press('Space');
    const fast = await page.evaluate(() => document.getElementById('splash')?.classList.contains('fast'));
    await page.waitForFunction(() => window.__splashGone, { timeout: 60000 });
    const g2 = await page.evaluate(() => ({ ready: window.__splashReadyAt, gone: window.__splashGone, skipped: window.__splashSkipped }));
    T.check('1 splash: a key press skips the show', fast && g2.skipped && g2.gone - g2.ready <= 120, `skipped at ${Math.round(g2.skipped)} ms, gone ${Math.round(g2.gone - g2.ready)} ms after ready`);
    await page.close();
  } finally { await browser.close(); }
}

// ------------------------------------------------------------------------------------------------ 2. reduced motion
async function checkReduced() {
  const { browser, page } = await openApp({ reducedMotion: true, beforeLoad: pg => pg.evaluateOnNewDocument(() => {
    try { localStorage.setItem('fsa.reduceMotion', 'true'); } catch { }
    window.__vt = 0;
    const o = document.startViewTransition && document.startViewTransition.bind(document);
    if (o) document.startViewTransition = cb => { window.__vt++; return o(cb); };
  }) });
  try {
    await presets(page);
    await L.sleep(2000);
    const moving = () => page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running').map(a => {
      const kf = a.effect && a.effect.getKeyframes ? a.effect.getKeyframes() : [];
      const props = [...new Set(kf.flatMap(k => Object.keys(k).filter(x => !['offset', 'computedOffset', 'easing', 'composite'].includes(x))))];
      const t = a.effect.getComputedTiming();
      return { name: a.animationName || a.constructor.name, props, dur: t.duration, iter: t.iterations, target: a.effect.target ? (a.effect.target.id || a.effect.target.className || a.effect.target.tagName) : '' };
    }));
    const bad = r => r.filter(a => !(a.props.every(p => p === 'opacity') && a.dur <= 150 && a.iter !== Infinity));
    const r1 = await moving();
    T.check('2 reduced motion: 2 s after load nothing moves (except short fades)', bad(r1).length === 0, JSON.stringify(bad(r1)).slice(0, 300));
    // open the editor, a dialog, Magic: still no confetti, spell, View Transition
    await toEditor(page);
    await page.evaluate(() => window.app.showStep('pose'));
    await page.evaluate(() => window.app.openMagic());
    await L.sleep(400);
    await page.evaluate(() => { const b = [...document.querySelectorAll('.modal footer button')].find(x => /Make it/.test(x.textContent)); b && b.click(); });
    await L.sleep(3500);
    const st = await page.evaluate(() => ({ spell: document.querySelectorAll('.wa-spell').length, fx: window.__fxPeak || 0, vt: window.__vt, reduce: document.documentElement.classList.contains('reduce-motion') }));
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('wa:sent', { detail: { app: window.app, heroSlot: document.body.appendChild(document.createElement('div')), project: window.app.store.project, first: true } })));
    await L.sleep(600);
    const st2 = await page.evaluate(() => ({ fx: window.__fxPeak || 0 }));
    const r2 = await moving();
    T.check('2 reduced motion: no confetti, spell or View Transition', st.spell === 0 && st.fx === 0 && st2.fx === 0 && st.vt === 0 && st.reduce, JSON.stringify({ ...st, fx2: st2.fx }));
    T.check('2 reduced motion: after Magic and a dialog, still nothing moving', bad(r2).length === 0, JSON.stringify(bad(r2)).slice(0, 300));
    if (!SKIP_SHOTS) await L.shot(page, path.join(AFTER, 'reduced_motion_magic_1366.png'));
  } finally { await browser.close(); }
}

// ------------------------------------------------------------------------------------------------ 3. palette
async function checkPalette() {
  const { browser, page, logs } = await openApp();
  try {
    await presets(page);
    await toEditor(page);
    await page.evaluate(() => { window.app.showStep('pose'); window.app.setFrame(20); window.app.setTool('rotate'); });
    await page.click('#viewport');                                  // the keyboard is on the app, not a box
    await L.sleep(200);
    // Ctrl held a moment before K (as people do): the hold-Ctrl key tips must not pop up over the palette or stay
    await page.keyboard.down('Control'); await L.sleep(250); await page.keyboard.press('KeyK'); await L.sleep(700); await page.keyboard.up('Control');
    await L.sleep(250);
    T.check('3 palette: Ctrl+K opens it', await page.evaluate(() => !!document.querySelector('.palette-back')));
    const tipsOver = await page.evaluate(() => document.querySelectorAll('.key-tip').length);
    T.check('3 palette: no key tips over the palette after Ctrl+K', tipsOver === 0, `${tipsOver} key tips`);
    const keysBefore = await page.evaluate(() => window.app.store.sim().keys.length);
    await page.keyboard.type('insert keyframe', { delay: 15 });
    await L.sleep(150);
    const first = await page.evaluate(() => document.querySelector('.palette-item .t')?.childNodes[0]?.textContent || document.querySelector('.palette-item .t')?.textContent);
    if (!SKIP_SHOTS) await L.shot(page, path.join(AFTER, 'palette_1366.png'));
    T.check('3 palette: "insert keyframe" puts Key pose first', /^Key pose/.test(first || ''), first);
    await page.keyboard.press('Enter');
    await L.sleep(400);
    const keysAfter = await page.evaluate(() => window.app.store.sim().keys.length);
    T.check('3 palette: Enter keys a pose (key count +1)', keysAfter === keysBefore + 1, `${keysBefore} -> ${keysAfter}`);
    const firstFor = async q => {
      await page.keyboard.down('Control'); await page.keyboard.press('KeyK'); await page.keyboard.up('Control');
      await L.sleep(150);
      await page.keyboard.type(q, { delay: 10 });
      await L.sleep(120);
      const t = await page.evaluate(() => document.querySelector('.palette-item .t')?.textContent || '');
      await page.keyboard.press('Escape');
      await L.sleep(120);
      return t;
    };
    const onion = await firstFor('onion skin');
    T.check('3 palette: "onion skin" -> Ghosts', /^Ghosts/.test(onion), onion);
    const turn = await firstFor('turntable');
    T.check('3 palette: "turntable" -> Showcase', /^Showcase/.test(turn), turn);
    // letters typed in the box never reach the app's shortcuts (G = Drag tool, M = Place tool, K = key)
    const before = await page.evaluate(() => ({ tool: window.app.interact.tool, keys: window.app.store.sim().keys.length }));
    await page.keyboard.down('Control'); await page.keyboard.press('KeyK'); await page.keyboard.up('Control');
    await L.sleep(120);
    await page.keyboard.type('gmk wasd', { delay: 20 });
    await L.sleep(150);
    const after = await page.evaluate(() => ({ tool: window.app.interact.tool, keys: window.app.store.sim().keys.length }));
    await page.keyboard.press('Escape');
    T.check('3 palette: typed letters never trigger app shortcuts', before.tool === after.tool && before.keys === after.keys, JSON.stringify({ before, after }));
    // a command from app.hooks.commands shows up
    await page.evaluate(() => window.app.hooks.commands.push(() => [{ id: 'zz-test', group: 'Test', label: 'Zebra test command', icon: 'spark', run: () => { window.__zz = 1; } }]));
    const z = await firstFor('zebra');
    T.check('3 palette: a hooks.commands entry shows up', /Zebra test command/.test(z), z);
    await L.sleep(800);
    const stuck = await page.evaluate(() => document.querySelectorAll('.key-tip').length);
    T.check('3 palette: key tips never stay on screen afterwards', stuck === 0, `${stuck} key tips`);
    T.check('3 palette: no page errors', !logs.some(l => /pageerror/.test(l)), logs.filter(l => /pageerror/.test(l)).join(' | ').slice(0, 200));
  } finally { await browser.close(); }
}

// ------------------------------------------------------------------------------------------------ 4. tooltips
async function checkTooltips() {
  const { browser, page } = await openApp();
  try {
    await presets(page);
    await toEditor(page);
    // something to redo, so the Redo button is live (a disabled button takes no pointer)
    await page.evaluate(() => { const a = window.app; a.showStep('pose'); a.setFrame(12); a.keyPose(); a.store.undoStep(); });
    // the Redo button must be live before the pointer goes over it (a disabled button takes no pointer)
    await page.waitForFunction(() => { const r = document.getElementById('btn-redo'); return r && !r.disabled; }, { timeout: 5000 }).catch(() => {});
    await L.sleep(150);
    const b = await page.$('#btn-redo');
    const box = await b.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    // the tooltip waits 450 ms; a slow (software-rendered) frame can delay that timer, so wait for it up to 2 s
    await page.waitForSelector('.wa-tip.show', { timeout: 2000 }).catch(() => {});
    const tip = await page.evaluate(() => { const t = document.querySelector('.wa-tip.show'); return t ? { text: t.childNodes[0]?.textContent, keys: [...t.querySelectorAll('kbd')].map(k => k.textContent) } : null; });
    T.check('4 tooltips: "Redo (Ctrl+Shift+Z or Ctrl+Y)" shows Ctrl, Shift, Z', tip && tip.keys.join(',') === 'Ctrl,Shift,Z' && tip.text === 'Redo', JSON.stringify(tip));
    if (!SKIP_SHOTS) await L.shot(page, path.join(AFTER, 'tooltip_1366.png'));
    await page.mouse.move(600, 400);
    await L.sleep(200);
    const back = await page.evaluate(() => document.getElementById('btn-redo').getAttribute('title'));
    T.check('4 tooltips: the title goes back when the pointer leaves', back === 'Redo (Ctrl+Shift+Z or Ctrl+Y)', back);
    // a title with words in brackets stays text
    await page.evaluate(() => { const x = document.createElement('button'); x.id = 'zz-tip'; x.className = 'btn'; x.textContent = 'Ride'; x.title = 'Rises and drops (cowgirl, reverse cowgirl)';
      x.style.cssText = 'position:fixed;left:700px;top:300px;z-index:99'; document.body.append(x); });
    await page.mouse.move(720, 312);
    await page.waitForFunction(() => { const t = document.querySelector('.wa-tip.show'); return t && /cowgirl/.test(t.textContent); }, { timeout: 2000 }).catch(() => {});
    const t2 = await page.evaluate(() => { const t = document.querySelector('.wa-tip.show'); return t ? { text: t.textContent, kbd: t.querySelectorAll('kbd').length } : null; });
    const split = await page.evaluate(async () => (await import('/js/tooltip.js')).splitTitle('Rises and drops (cowgirl, reverse cowgirl)'));
    T.check('4 tooltips: "(cowgirl, reverse cowgirl)" stays text', t2 && t2.kbd === 0 && /cowgirl, reverse cowgirl/.test(t2.text) && split.keys.length === 0, JSON.stringify({ t2, split }));
    // hold Ctrl: key tips
    await page.mouse.move(600, 400);
    await page.keyboard.down('Control');
    await L.sleep(700);
    const tips = await page.evaluate(() => document.querySelectorAll('.key-tip').length);
    await page.keyboard.up('Control');
    await L.sleep(100);
    const tipsAfter = await page.evaluate(() => document.querySelectorAll('.key-tip').length);
    T.check('4 tooltips: holding Ctrl shows key tips, letting go hides them', tips >= 5 && tipsAfter === 0, `${tips} shown, ${tipsAfter} after`);
  } finally { await browser.close(); }
}

// ------------------------------------------------------------------------------------------------ 5. stage
async function checkStage() {
  const { browser, page } = await openApp();
  try {
    await toEditor(page);
    const r = await page.evaluate(() => {
      const vp = window.app.vp, st = vp.stage;
      const fog = vp.scene.fog.color.getHexString(), hz = st.horizon().getHexString();
      return { radius: vp.floor.geometry.parameters.radius, fog, hz, dome: !!st.dome, grid: !!st.grid, lights: Object.keys(vp.lights || {}) };
    });
    T.check('5 stage: floor radius is 20', r.radius === 20, String(r.radius));
    T.check('5 stage: fog colour = the dome\'s horizon colour', r.fog === r.hz, `fog #${r.fog} dome #${r.hz}`);
    T.check('5 stage: this.lights = {hemi, key, rim, rim2, fill}', ['hemi', 'key', 'rim', 'rim2', 'fill'].every(k => r.lights.includes(k)), r.lights.join(','));
    // a level camera: the horizon is the middle row of the picture; the brightness step across it
    const horizon = await page.evaluate(async () => {
      const app = window.app, vp = app.vp;
      vp.keepQuality = true; vp.setQualityLevel(0);
      for (const [, v] of app.simViews) v.group.visible = false;
      app.showcase(false); vp.stopCamera();
      const THREE = await import('three');
      vp.controls.lookFrom(new THREE.Vector3(0.3, 1.1, 7.5), new THREE.Vector3(0.3, 1.1, 0));
      await new Promise(r => setTimeout(r, 600));
      const c = vp.canvas, w = c.width, hgt = c.height;
      const cv = document.createElement('canvas'); cv.width = w; cv.height = hgt;
      const g = cv.getContext('2d'); g.drawImage(c, 0, 0);
      const d = g.getImageData(0, 0, w, hgt).data;
      const lum = y => { let s = 0, n = 0; for (let x = Math.floor(w * 0.1); x < w * 0.9; x += 2) { const i = (y * w + x) * 4; s += 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]; n++; } return s / n; };
      const mid = Math.round(hgt / 2);
      let worst = 0, at = 0;
      const rows = [];
      for (let y = mid - 40; y < mid + 40; y++) { const a = lum(y), b = lum(y + 1); rows.push(+a.toFixed(1)); if (Math.abs(b - a) > worst) { worst = Math.abs(b - a); at = y; } }
      for (const [, v] of app.simViews) v.group.visible = true;
      return { worst: +worst.toFixed(2), at: at - mid, rows: rows.filter((_, i) => i % 8 === 0) };
    });
    info.horizon = horizon;
    if (!SKIP_SHOTS) await L.shot(page, path.join(AFTER, 'stage_level_horizon_1366.png'));
    T.check('5 stage: no horizon edge (brightness step across the horizon < 6 levels)', horizon.worst < 6, `worst step ${horizon.worst} levels at row ${horizon.at} from the middle`);
    // five looks switch and are kept in project.look
    await page.evaluate(() => { window.app.vp.keepQuality = false; window.app.frameSims({ fromFront: true }); });
    const looks = ['studio', 'boudoir', 'neon', 'daylight', 'candle'];
    let ok = true; const got = [];
    for (const k of looks) {
      const r2 = await page.evaluate(k => { window.app.setLook(k); return { look: window.app.vp.stage.look, p: window.app.store.project.look, exp: window.app.vp.renderer.toneMappingExposure }; }, k);
      got.push(`${k}:${r2.look}/${r2.p}`);
      ok = ok && r2.look === k && r2.p === k;
      if (!SKIP_SHOTS) { await L.sleep(500); await L.shot(page, path.join(AFTER, `look_${k}_1366.png`)); }
    }
    T.check('5 stage: all five looks switch and are saved in project.look', ok, got.join(' '));
    // the Light button opens its popover
    await page.click('#btn-light');
    await L.sleep(250);
    const pop = await page.evaluate(() => document.querySelectorAll('.light-pop button[data-look]').length);
    if (!SKIP_SHOTS) await L.shot(page, path.join(AFTER, 'light_popover_1366.png'));
    T.check('5 stage: the Light button lists the five looks', pop === 5, String(pop));
    await page.evaluate(() => window.app.setLook('studio'));
  } finally { await browser.close(); }
}

// ------------------------------------------------------------------------------------------------ 6. celebrations
async function checkCelebrations() {
  const { browser, page } = await openApp();
  try {
    await toEditor(page);
    const send = async first => page.evaluate(async first => {
      const ui = await import('/js/ui.js');
      window.__fxPeak = 0; window.__clicked = 0;
      const heroSlot = document.createElement('div'), extraSlot = document.createElement('div');
      const dlg = ui.modal({ title: "It's in your Mods folder", body: ui.h('div', {}, heroSlot, ui.h('p', {}, 'Restart the game, then pick it in WickedWhims.'), extraSlot),
        buttons: [{ label: 'Try the button', kind: '', onClick: () => { window.__clicked++; return false; } }, { label: 'Done', kind: 'primary' }] });
      window.app.emit ? window.app.emit('sent', { project: window.app.store.project, result: { ok: true }, heroSlot, extraSlot, first })
        : window.dispatchEvent(new CustomEvent('wa:sent', { detail: { app: window.app, project: window.app.store.project, result: {}, heroSlot, extraSlot, first } }));
      window.__dlg = dlg;
      return { hero: !!heroSlot.querySelector('.success-hero'), card: !!heroSlot.querySelector('.first-card') };
    }, first);
    const a = await send(false);
    await L.sleep(700);
    // a click on the dialog button lands on the button (the particle canvas never takes a click)
    const btn = await page.evaluate(() => { const b = [...document.querySelectorAll('.modal footer button')].find(x => /Try the button/.test(x.textContent)); const r = b.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
    const top = await page.evaluate(p => { const e = document.elementFromPoint(p.x, p.y); return e && (e.closest('button') ? e.closest('button').textContent : e.tagName); }, btn);
    await page.mouse.click(btn.x, btn.y);
    if (!SKIP_SHOTS) await L.shot(page, path.join(AFTER, 'sent_burst_1366.png'));
    await L.sleep(1300);
    const s1 = await page.evaluate(() => ({ peak: window.__fxPeak, clicked: window.__clicked }));
    T.check('6 celebrations: wa:sent fills the hero slot (tick + burst)', a.hero && !a.card, JSON.stringify(a));
    T.check('6 celebrations: the burst runs at most 160 particles', s1.peak > 0 && s1.peak <= 160, `peak ${s1.peak}`);
    T.check('6 celebrations: the dialog button is clickable during the burst', s1.clicked === 1 && /Try the button/.test(top || ''), `clicked ${s1.clicked}, top element ${top}`);
    await page.evaluate(() => window.__dlg.close());
    await L.sleep(300);
    const b1 = await send(true);
    await L.sleep(900);
    if (!SKIP_SHOTS) await L.shot(page, path.join(AFTER, 'first_animation_card_1366.png'));
    const peak2 = await page.evaluate(() => window.__fxPeak);
    await page.evaluate(() => window.__dlg.close());
    await L.sleep(1800);
    const b2 = await send(false);
    await page.evaluate(() => window.__dlg.close());
    T.check('6 celebrations: the first send gets the "Creator #1" card and plumbob rain', b1.card && !b1.hero && peak2 > 0 && peak2 <= 160, JSON.stringify({ ...b1, peak: peak2 }));
    T.check('6 celebrations: the second send uses the normal burst', b2.hero && !b2.card, JSON.stringify(b2));
  } finally { await browser.close(); }
}

// Magic's entrance on the graphics card: the swoop is a real flight (not a cut), Showcase starts only after it, and
// from behind the headboard the sims show through the furniture (the cutaway).
async function checkMagicCamera() {
  const { browser, page, logs } = await openApp({ gpu: true });
  const meshReq = [];
  page.on('request', r => { if (/\/api\/furniture_mesh/.test(r.url())) meshReq.push(r.url()); });
  try {
    await presets(page);
    await toEditor(page);
    const fly = await page.evaluate(async () => {
      const app = window.app, m = await import('/js/magic.js');
      await m.makeMagic(app, { recipe: 'cowgirl', place: 'double_bed', intensity: 0.5, seconds: 3 });
      const c = app.vp.controls.target.clone(), out = [];
      const t0 = performance.now();
      while (performance.now() - t0 < 1500) {
        await new Promise(r => requestAnimationFrame(r));
        out.push({ t: Math.round(performance.now() - t0), d: +app.vp.camera.position.distanceTo(c).toFixed(3), show: !!app._showStep });
      }
      return out;
    });
    const first = fly[0], last = fly[fly.length - 1];
    const moving = fly.filter((x, i) => i && Math.abs(x.d - fly[i - 1].d) > 1e-4).length;
    const showDuring = fly.filter(x => x.t < 1000 && x.show).length;
    T.check('6 Magic: the camera swoop is a real flight, not a cut', first.d > 1.5 * last.d && moving >= 10, `distance ${first.d} -> ${last.d} m, ${moving} moving frames of ${fly.length}`);
    await L.sleep(1200);
    const showAfter = await page.evaluate(() => !!window.app._showStep);
    T.check('6 Magic: Showcase starts only after the swoop', showDuring === 0 && showAfter, `during swoop ${showDuring} frames, after: ${showAfter}`);
    // behind the headboard: toggling the sims must change the picture (they show through the furniture)
    const see = await page.evaluate(async () => {
      const app = window.app, vp = app.vp, THREE = await import('three');
      clearTimeout(app._magicShow); app.showcase(false); vp.stopCamera(); app.setPlaying(false); app.setFrame(0);
      const c = new THREE.Vector3(); let n = 0;
      for (const [, v] of app.simViews) { v.group.updateMatrixWorld(true); c.add(v.worldPos('b__Pelvis__')); n++; }
      c.multiplyScalar(1 / n);
      vp.controls.lookFrom(new THREE.Vector3(c.x, c.y + 0.55, c.z - 2.9), c);
      const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      const grab = async () => {
        await frame(); await frame();
        const cv = vp.canvas, w = cv.width, h = cv.height, x0 = Math.round(w * 0.35), y0 = Math.round(h * 0.3), cw = Math.round(w * 0.3), ch = Math.round(h * 0.4);
        const t = document.createElement('canvas'); t.width = cw; t.height = ch;
        t.getContext('2d').drawImage(cv, x0, y0, cw, ch, 0, 0, cw, ch);
        return t.getContext('2d').getImageData(0, 0, cw, ch).data;
      };
      const diff = (a, b) => { let s = 0; for (let i = 0; i < a.length; i += 4) s += Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2]); return s / (a.length / 4) / 3; };
      const show = on => { for (const [, v] of app.simViews) v.group.visible = on; };
      const measure = async () => { show(true); const a = await grab(); show(false); const b = await grab(); show(true); return diff(a, b); };
      vp.cutaway = true; const withCut = await measure();
      vp.cutaway = false; const noCut = await measure();
      vp.cutaway = true; await frame();
      return { withCut: +withCut.toFixed(2), noCut: +noCut.toFixed(2) };
    });
    if (!SKIP_SHOTS) await L.shot(page, path.join(AFTER, 'cutaway_headboard_1366.png'));
    T.check('6 Magic: behind the headboard the sims show through the furniture', see.withCut > 6 && see.withCut > 3 * see.noCut, `picture change when the sims hide: ${see.withCut} levels with the cutaway, ${see.noCut} without`);
    // furniture.js keeps the v2 data on the real object and can draw its spots (for the Place tool)
    const bedReq = meshReq.filter(u => /[?&]id=double_bed\b/.test(u));   // counted before this check's own fetch below
    T.check('8 Magic: the furniture data of the bed is fetched once (shared by furniture.js, placing.js and the app), with v=2',
      bedReq.length === 1 && bedReq.every(u => /[?&]v=2\b/.test(u)), `${bedReq.length} request(s): ${bedReq.map(u => u.replace(/^.*\/api\//, '')).join(' ')}`);
    const v2 = await page.evaluate(async () => {
      const f = await import('/js/furniture.js'), app = window.app;
      const g = app.vp.furniture.children[0], info = await fetch('/api/furniture_mesh?v=2&id=double_bed').then(r => r.json());
      const mk = f.slotMarkers(info.slots || []);
      return { real: !!(g && g.userData.real), slots: (g && g.userData.slots || []).length, surface: g && g.userData.surface, grid: !!(g && g.userData.grid),
        markers: mk.children.length, infoSlots: (info.slots || []).length, allTagged: mk.children.every(c => c.userData.slot) };
    });
    T.check('8 Magic: the bed keeps its spots, surface and grid (v2), and slotMarkers draws every spot', v2.real && v2.slots > 0 && Math.abs(v2.surface - 0.562) < 0.01 && v2.grid && v2.markers === v2.infoSlots && v2.allTagged, JSON.stringify(v2));
    T.check('6 Magic: no page errors', !logs.some(l => /pageerror/.test(l)), logs.filter(l => /pageerror/.test(l)).join(' | ').slice(0, 200));
  } finally { await browser.close(); }
}

// ------------------------------------------------------------------------------------------------ 7. dialogs
async function checkDialogs() {
  const { browser, page } = await openApp();
  try {
    await toEditor(page);
    const r = await page.evaluate(async () => {
      const ui = await import('/js/ui.js');
      const d = ui.modal({ title: 'Test dialog', body: ui.h('p', {}, 'Hello'), buttons: [{ label: 'OK', kind: 'primary' }] });
      await new Promise(res => setTimeout(res, 300));
      d.close();
      const now = { open: document.querySelectorAll('.backdrop:not(.leaving)').length, any: document.querySelectorAll('.backdrop').length };
      await new Promise(res => setTimeout(res, 250));
      return { now, later: document.querySelectorAll('.backdrop').length };
    });
    T.check('7 dialogs: .backdrop:not(.leaving) is empty right after closing', r.now.open === 0, JSON.stringify(r.now));
    T.check('7 dialogs: 250 ms after closing no .backdrop exists', r.later === 0, String(r.later));
    // a toast and the choice bar
    const t = await page.evaluate(async () => { const ui = await import('/js/ui.js'); ui.toast('Saved "x".', 'ok'); const bar = ui.choiceBar('Loop is 4 s now.', [{ label: 'Undo', onClick: () => true }], { timeout: 5000 });
      await new Promise(r => setTimeout(r, 60)); const res = { icon: !!document.querySelector('#toasts .toast svg'), count: document.querySelector('.choice-bar')?.classList.contains('counting') }; bar.close(); return res; });
    T.check('7 dialogs: toasts get an icon, the choice bar counts down', t.icon && t.count, JSON.stringify(t));
  } finally { await browser.close(); }
}

// ------------------------------------------------------------------------------------------------ 8. Magic placement
function checkPlacement() {
  const r = cp.spawnSync('node', [path.join(__dirname, 'placement.js'), '--port', String(PORT)], { encoding: 'utf8', timeout: 1500000 });
  const out = (r.stdout || '') + (r.stderr || '');
  fs.writeFileSync(path.join(OUT, 'placement_log.txt'), out);
  const m = /(\d+) passed, (\d+) failed/.exec(out);
  const lines = out.split('\n').filter(l => /^(PASS|FAIL)  /.test(l));
  const pick = re => lines.find(l => re.test(l)) || '';
  for (const [name, re] of [['8 Magic: cowgirl on the double bed, lowest bone - 0.06 within 2 cm of 0.562', /cowgirl on double_bed: lowest bone/],
    ['8 Magic: every bone below 1.1 m inside the bed', /every bone below 1.1 m inside the bed/], ['8 Magic: long axis within 10 deg of Z', /long axis within 10/],
    ['8 Magic: on the floor, lowest bone - 0.06 within 2 cm of 0', /cowgirl on floor: lowest bone/], ['8 Magic: every key moved, not only frame 0', /every key moved/],
    ['8 Magic (leftover bug): lowest skin on the double bed mattress', /cowgirl on double_bed: lowest skin/], ['8 Magic (leftover bug): lowest skin on the single bed', /cowgirl on single_bed: lowest skin/],
    ['8 Magic (leftover bug): lowest skin on the sofa seat', /cowgirl on sofa: lowest skin/], ['8 Magic (leftover bug): lowest skin on the floor', /cowgirl on floor: lowest skin/]]) {
    const l = pick(re);
    T.check(name, /^PASS/.test(l), l.replace(/^(PASS|FAIL)\s+/, '').replace(/\s{2,}/g, '  ').slice(0, 160));
  }
  T.check('8 Magic: the whole placement check (all recipes and places)', r.status === 0 && m && m[2] === '0', m ? `${m[1]} passed, ${m[2]} failed (cache/checks/r1c/placement_log.txt)` : 'no result');
}

// ------------------------------------------------------------------------------------------------ 9. layout at 1366x768
async function checkLayout() {
  const { browser, page } = await openApp({ w: 1366, h: 768 });
  try {
    await presets(page);
    await L.sleep(800);
    const home = await page.evaluate(() => { const h3 = [...document.querySelectorAll('#home h3')].find(x => /Your animations/.test(x.textContent)); const r = h3.getBoundingClientRect(); return { top: Math.round(r.top), bottom: Math.round(r.bottom), vh: innerHeight }; });
    T.check('9 layout: "Your animations" on Home is above the fold', home.bottom <= home.vh, `heading at ${home.top}-${home.bottom} px of ${home.vh}`);
    const holes = await page.evaluate(() => {
      // every column at the top of every row of cards is covered by some card
      const g = document.querySelector('#home .home-grid'), cs = getComputedStyle(g), gr = g.getBoundingClientRect();
      const cols = cs.gridTemplateColumns.split(' ').length, gap = parseFloat(cs.columnGap) || 0, colW = (gr.width - gap * (cols - 1)) / cols;
      const cards = [...g.children].map(c => c.getBoundingClientRect());
      const tops = [...new Set(cards.map(r => Math.round(r.top)))].sort((a, b) => a - b);
      const missing = [];
      for (const t of tops) for (let c = 0; c < cols; c++) {
        const x = gr.left + c * (colW + gap) + colW / 2, y = t + 10;
        if (!cards.some(r => r.left <= x && r.right >= x && r.top <= y && r.bottom >= y)) missing.push(`row ${Math.round(t - gr.top)} col ${c + 1}`);
      }
      return { cols, rows: tops.length, cards: cards.length, missing };
    });
    T.check('9 layout: no holes in the Home start grid', holes.missing.length === 0, JSON.stringify(holes));
    if (!SKIP_SHOTS) await L.shot(page, path.join(AFTER, 'home_1366.png'));
    await toEditor(page);
    await page.evaluate(() => { window.app.showStep('pose'); const s = window.app.store.sim(); if (s) window.app.selectSim(s.id); });
    await L.sleep(700);
    const w = await page.evaluate(() => document.getElementById('viewport-wrap').getBoundingClientRect().width);
    T.check('9 layout: the stage is >= 726 px wide in the Pose step', w >= 726, `${Math.round(w)} px`);
    const clipped = [];
    for (const bone of [null, 'b__L_Hand__']) {
      await page.evaluate(b => { const a = window.app; if (b) { a.store.selected.bone = b; a.emitSelection(); } }, bone);
      await L.sleep(300);
      clipped.push(...await page.evaluate(() => [...document.querySelectorAll('#inspector .btn')].filter(b => b.offsetParent && b.scrollWidth > b.clientWidth + 1).map(b => b.textContent.trim())));
    }
    T.check('9 layout: no button text clipped in the inspector', clipped.length === 0, clipped.join(' | ').slice(0, 200));
    // pin buttons: "Right foot  PINNED" on one line, nothing cut off (both feet pinned = the longest words)
    const pins = await page.evaluate(async () => {
      const a = window.app, s = a.store.sim();
      a.store.selected.bone = null; a.emitSelection();
      s.pins = s.pins || {}; for (const l of ['L foot', 'R foot']) s.pins[l] = s.pins[l] || [0, 0.1, 0];
      a.refreshPanels ? a.refreshPanels() : a.emitSelection();
      await new Promise(r => setTimeout(r, 250));
      const b = [...document.querySelectorAll('#inspector .pin')].filter(x => x.offsetParent);
      return { n: b.length, bad: b.filter(x => x.scrollWidth > x.clientWidth + 1 || x.getBoundingClientRect().height > 40).map(x => x.textContent.trim()) };
    });
    T.check('9 layout: pin buttons fit on one line', pins.n >= 4 && pins.bad.length === 0, JSON.stringify(pins));
    // the message box (bottom left) never overlaps the hint row (bottom right), whatever each says (R1-B's report:
    // the Face tool message under the timeline hint at 1366)
    const hudCases = [];
    for (const [msg, hint] of [
      ['<b>Female 1</b> · Click a dot on the face · T move/turn · X both sides · Alt goes past the safe range', 'timeline'],
      ['<b>Female 1</b> · Click a body part, then turn the rings', null],
      ['<b>Female 1</b> · Click a dot on the face · T move/turn · X both sides · Alt goes past the safe range', 'ring'],
      ['<b>Female 1</b> · Click a dot on the face · T move/turn · X both sides · Alt goes past the safe range', null]]) {
      hudCases.push(await page.evaluate(async (msg, hint) => {
        const hud = document.getElementById('vp-hud'), row = document.getElementById('vp-cam');
        hud.innerHTML = msg; window.app.hint(hint);
        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        const a = hud.getBoundingClientRect(), b = row.getBoundingClientRect(), wr = document.getElementById('viewport-wrap').getBoundingClientRect();
        const overlap = !!(row.offsetParent && a.width && b.width && a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom);
        return { hint, overlap, inside: a.left >= wr.left && a.right <= wr.right + 1, hud: [Math.round(a.left), Math.round(a.right), Math.round(a.top)], row: [Math.round(b.left), Math.round(b.right), Math.round(b.top)] };
      }, msg, hint));
      if (hudCases.length === 1 && !SKIP_SHOTS) await L.shot(page, path.join(AFTER, 'hud_hint_1366.png'));
    }
    await page.evaluate(() => window.app.hint(null));
    T.check('9 layout: the message box never overlaps the hint row (1366)', hudCases.every(c => !c.overlap && c.inside), JSON.stringify(hudCases));
    // the "Posing" banner says what R1-B's spec says
    const banner = await page.evaluate(async () => {
      const b = document.getElementById('vp-editing'); b.classList.remove('hidden');
      await new Promise(r => setTimeout(r, 350));
      const r = b.getBoundingClientRect(), wr = document.getElementById('viewport-wrap').getBoundingClientRect();
      return { text: b.textContent.trim(), fits: r.left >= wr.left && r.right <= wr.right };
    });
    if (!SKIP_SHOTS) await L.shot(page, path.join(AFTER, 'posing_banner_1366.png'));
    await page.evaluate(() => document.getElementById('vp-editing').classList.add('hidden'));
    T.check('9 layout: the Posing banner text (spec 4) fits in the stage', banner.text === 'Posing - motion and physics are paused on this sim until you click empty space' && banner.fits, JSON.stringify(banner));
    // the stage toolbar fits: nothing hangs outside the stage
    const tb = await page.evaluate(() => { const wr = document.getElementById('viewport-wrap').getBoundingClientRect(); return [...document.querySelectorAll('.vp-top button')].filter(b => b.offsetParent).filter(b => { const r = b.getBoundingClientRect(); return r.right > wr.right + 1 || r.left < wr.left - 1; }).map(b => b.id || b.textContent.trim()); });
    T.check('9 layout: the stage toolbar fits in the stage', tb.length === 0, tb.join(', '));
    await page.evaluate(() => window.app.showStep('details'));
    await L.sleep(500);
    const insp = await page.evaluate(() => Math.round(document.getElementById('right').getBoundingClientRect().width));
    T.check('9 layout: the inspector folds to a strip on Details', insp <= 46, `${insp} px`);
  } finally { await browser.close(); }
}

// ------------------------------------------------------------------------------------------------ 10. performance
async function checkPerf() {
  const { browser, page } = await openApp({ w: 1366, h: 768, gpu: true });
  try {
    await presets(page);
    await toEditor(page);
    await page.evaluate(async () => {
      const m = await import('/js/magic.js');
      await m.makeMagic(window.app, { recipe: 'cowgirl', place: 'double_bed', intensity: 0.5, seconds: 3 });
      clearTimeout(window.app._magicShow); window.app.showcase(false); window.app.setPlaying(false); window.app.setFrame(0); window.app.showStep('pose');
    });
    await L.sleep(1500);
    const frames = n => page.evaluate(n => new Promise(res => { const t = []; let last = performance.now(); const f = now => { t.push(now - last); last = now; if (t.length < n) requestAnimationFrame(f); else res(t); }; requestAnimationFrame(f); }), n);
    await page.evaluate(() => { const vp = window.app.vp; vp.keepQuality = true; vp.setQualityLevel(0); });
    const gpu = await page.evaluate(() => { try { const gl = window.app.vp.renderer.getContext(); const e = gl.getExtension('WEBGL_debug_renderer_info'); return e ? gl.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'n/a'; } catch { return 'n/a'; } });
    info.gpu = gpu;
    await frames(30);
    const ed = await frames(120);
    const p95 = pct(ed, 0.95);
    info.editFrames = { p50: +median(ed).toFixed(1), p95: +p95.toFixed(1) };
    T.check('10 performance: editing frames p95 <= 20 ms (dome + grid on)', p95 <= 20, `p95 ${p95.toFixed(1)} ms, median ${median(ed).toFixed(1)} ms (${gpu})`);
    // Showcase: cinematic mode; adaptive quality may step down
    await page.evaluate(() => { const vp = window.app.vp; vp.keepQuality = false; vp.setQualityLevel(0); window.app.setPlaying(true); document.getElementById('btn-showcase').click(); });
    await L.sleep(800);
    const sc = await frames(120);
    const p95s = pct(sc, 0.95);
    const q = await page.evaluate(() => ({ level: window.app.vp.qualityLevel, chip: !!document.querySelector('.fast-chip'), cine: document.body.classList.contains('cinematic'), bloom: window.app.vp.stage.bloomOn }));
    info.showcaseFrames = { p50: +median(sc).toFixed(1), p95: +p95s.toFixed(1), ...q };
    if (!SKIP_SHOTS) await L.shot(page, path.join(AFTER, 'showcase_cinematic_1366.png'));
    T.check('10 performance: Showcase cinematic p95 <= 28 ms, or bloom off + Fast mode chip', q.cine && (p95s <= 28 || (q.level >= 1 && q.chip && !q.bloom)), `p95 ${p95s.toFixed(1)} ms, ${JSON.stringify(q)}`);
    // the heavy renderStep stays under 50 ms (Pose step with every tile)
    await page.evaluate(() => { document.getElementById('btn-showcase').click(); window.app.setPlaying(false); window.app.showStep('pose'); });
    const rs = await page.evaluate(() => { const t = []; for (let i = 0; i < 10; i++) { const a = performance.now(); window.app.renderStep(); t.push(performance.now() - a); } return t.sort((a, b) => a - b); });
    T.check('10 performance: renderStep() (Pose step) under 50 ms', rs[5] < 50, `median ${rs[5].toFixed(1)} ms`);
  } finally { await browser.close(); }
}

// ------------------------------------------------------------------------------------------------ 11. screenshots + gallery
async function shots() {
  const STEPS = ['scene', 'pose', 'motion', 'body', 'face', 'sounds', 'details', 'share', 'library'];
  for (const [w, h] of [[1366, 768], [1920, 1080]]) {
    const { browser, page } = await openApp({ w, h, gpu: true });
    try {
      await presets(page);
      await L.sleep(2500);
      await L.shot(page, path.join(AFTER, `home_${w}.png`));
      await toEditor(page);
      for (const s of STEPS) {
        await page.evaluate(st => window.app.showStep(st), s);
        await L.sleep(s === 'face' ? 1400 : 800);
        await L.shot(page, path.join(AFTER, `step_${s}_${w}.png`));
      }
      // mid-transition between two steps (animations frozen at 120 ms)
      await page.evaluate(() => window.app.showStep('pose'));
      await L.sleep(800);
      await page.evaluate(() => { window.app.showStep('motion'); document.getAnimations().forEach(a => { try { a.pause(); a.currentTime = 120; } catch { } }); });
      await L.sleep(100);
      await L.shot(page, path.join(AFTER, `step_transition_mid_${w}.png`));
      await page.evaluate(() => document.getAnimations().forEach(a => { try { a.play(); } catch { } }));
      // the palette
      await page.keyboard.down('Control'); await page.keyboard.press('KeyK'); await page.keyboard.up('Control');
      await page.keyboard.type('insert key', { delay: 10 });
      await L.sleep(250);
      await L.shot(page, path.join(AFTER, `palette_${w}.png`));
      await page.keyboard.press('Escape');
      // Magic (cowgirl on the double bed): the spell mid-frame, then the swoop mid-frame
      await page.evaluate(() => { localStorage.setItem('fsa.magicRecipe', JSON.stringify('cowgirl')); localStorage.setItem('fsa.magicPlace', JSON.stringify('double_bed')); window.app.openMagic(); });
      await L.sleep(500);
      await page.evaluate(() => { const b = [...document.querySelectorAll('.modal footer button')].find(x => /Make it/.test(x.textContent)); b && b.click(); });
      await L.sleep(40);
      await page.evaluate(() => document.querySelectorAll('.wa-spell').forEach(el => el.getAnimations().forEach(a => { a.pause(); a.currentTime = 320; })));
      await L.shot(page, path.join(AFTER, `magic_spell_${w}.png`));
      await page.evaluate(() => document.querySelectorAll('.wa-spell').forEach(el => el.getAnimations().forEach(a => a.play())));
      await page.waitForFunction(() => window.app.lastMagic && Date.now(), { timeout: 30000 }).catch(() => {});
      await L.sleep(450);
      await L.shot(page, path.join(AFTER, `magic_swoop_${w}.png`));
      await L.sleep(2500);
      await L.shot(page, path.join(AFTER, `magic_double_bed_${w}.png`));
      // the five looks on the Magic scene
      await page.evaluate(() => { clearTimeout(window.app._magicShow); window.app.showcase(false); window.app.setPlaying(false); window.app.frameSims({ fromFront: true }); });
      await L.sleep(600);
      for (const k of ['studio', 'boudoir', 'neon', 'daylight', 'candle']) {
        await page.evaluate(k => window.app.setLook(k), k);
        await L.sleep(450);
        await L.shot(page, path.join(AFTER, `look_${k}_${w}.png`));
      }
      await page.evaluate(() => window.app.setLook('studio'));
      // the first-animation card
      await page.evaluate(async () => {
        const ui = await import('/js/ui.js');
        const heroSlot = document.createElement('div');
        ui.modal({ title: "It's in your Mods folder", body: ui.h('div', {}, heroSlot, ui.h('p', {}, 'Restart the game, then pick it in WickedWhims.')), buttons: [{ label: 'Done', kind: 'primary' }] });
        window.dispatchEvent(new CustomEvent('wa:sent', { detail: { app: window.app, project: window.app.store.project, heroSlot, first: true } }));
      });
      await L.sleep(1100);
      await L.shot(page, path.join(AFTER, `first_animation_${w}.png`));
    } finally { await browser.close(); }
  }
}

function gallery() {
  const before = path.join(OUT, 'before');
  const img = (dir, f) => fs.existsSync(path.join(dir, f)) ? `<figure><img src="${path.basename(dir)}/${f}" loading="lazy"><figcaption>${path.basename(dir)}/${f}</figcaption></figure>` : '';
  const pair = f => `<div class="pair">${img(before, f)}${img(AFTER, f)}</div>`;
  const steps = ['scene', 'pose', 'motion', 'body', 'face', 'sounds', 'details', 'share', 'library'];
  const afterOnly = fs.existsSync(AFTER) ? fs.readdirSync(AFTER).filter(f => f.endsWith('.png')).sort() : [];
  const root = fs.readdirSync(OUT).filter(f => f.endsWith('.png')).sort();
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>R1-C gallery</title><meta name="color-scheme" content="dark">
<style>body{margin:0;padding:24px;background:#0b0a10;color:#f2eef8;font:13px/1.45 system-ui,sans-serif}h1{font-size:22px}h2{margin:34px 0 10px;font-size:15px;color:#ff8cc4}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:10px 0}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:12px}
figure{margin:0}img{width:100%;border-radius:8px;border:1px solid #2a2535;display:block}figcaption{color:#8b83a0;font-size:11px;margin-top:4px}</style></head><body>
<h1>Novulon's Wicked Animator - R1-C "Velvet Stage" gallery</h1><p>Left: before (the app when R1-C started). Right: after. Made by tools/checks/r1c/design.js.</p>
<h2>Home</h2>${pair('home_1366.png')}${pair('home_1920.png')}
${steps.map(s => `<h2>Step: ${s}</h2>${pair(`step_${s}_1366.png`)}${pair(`step_${s}_1920.png`)}`).join('')}
<h2>Magic on the double bed (before: the headboard-height bug)</h2>${pair('magic_double_bed_1366.png')}<div class="grid">${root.filter(f => /^magic_cowgirl/.test(f)).map(f => img(OUT, f)).join('')}</div>
<h2>Everything new (after)</h2><div class="grid">${afterOnly.filter(f => !/^(home|step_(scene|pose|motion|body|face|sounds|details|share|library))_\d+\.png$/.test(f)).map(f => img(AFTER, f)).join('')}</div>
</body></html>`;
  fs.writeFileSync(path.join(OUT, 'gallery.html'), html);
  return path.join(OUT, 'gallery.html');
}

(async () => {
  fs.mkdirSync(AFTER, { recursive: true });
  const server = await L.startServer(PORT);
  const t0 = Date.now();
  try {
    const parts = [[1, checkSplash], [2, checkReduced], [3, checkPalette], [4, checkTooltips], [5, checkStage], [6, checkCelebrations], [6, checkMagicCamera], [7, checkDialogs], [8, checkPlacement], [9, checkLayout], [10, checkPerf]];
    for (const [n, fn] of parts) {
      if (!run(n)) continue;
      console.log(`\n=== check ${n}`);
      try { await fn(); } catch (e) { T.check(`${n}: ran without an exception`, false, String(e && (e.stack || e.message)).slice(0, 300)); }
    }
    if (run(11) && !SKIP_SHOTS) {
      console.log('\n=== check 11 (screenshots)');
      try { await shots(); } catch (e) { T.check('11: screenshots ran without an exception', false, String(e && (e.stack || e.message)).slice(0, 300)); }
    }
    if (run(11)) { const g = gallery(); T.check('11 screenshots: gallery written', fs.existsSync(g), g); }
  } finally { L.stopServer(server); }
  info.seconds = Math.round((Date.now() - t0) / 1000);
  fs.writeFileSync(path.join(OUT, 'design_result.json'), JSON.stringify({ rows: T.rows, info }, null, 1));
  const ok = T.print('R1-C design check');
  console.log(JSON.stringify(info));
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
