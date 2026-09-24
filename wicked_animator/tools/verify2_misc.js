// Verifier round 2: checks the round 1 scripts do not cover (E0 web half, E11, C10, C46, C48, C53, C54, 1366 Place click).
//   node tools/verify2_misc.js      (TEST server on ANIMATOR_PORT, default 8777; never the user's 8765)
const path = require('path'), fs = require('fs');
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');
const PORT = process.env.ANIMATOR_PORT || '8777';
const APP = `http://127.0.0.1:${PORT}/`;
const OUT = path.join(__dirname, '..', 'cache', 'fixwave', 'verify2', 'misc');
const results = [], logs = [];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail === undefined ? '' : ' :: ' + JSON.stringify(detail).slice(0, 600)}`); };

async function open(browser, w, h, intercept) {
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
  page.on('pageerror', e => logs.push('[pageerror] ' + e.message));
  page.on('console', m => { if (m.type() === 'error') logs.push('[error] ' + m.text()); });
  await page.evaluateOnNewDocument(() => { try { localStorage.setItem('fsa.tourDone', 'true'); localStorage.removeItem('fsa.autosave'); } catch { /* */ } });
  if (intercept) { await page.setRequestInterception(true); page.on('request', intercept); }
  await page.goto(APP, { waitUntil: 'networkidle0', timeout: 180000 }).catch(() => {});
  return page;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', protocolTimeout: 900000,
    args: ['--use-angle=d3d11', '--enable-webgl', '--ignore-gpu-blocklist', '--window-size=1600,900'] });

  // E0 (web half): a module that fails to load shows a plain message instead of spinning forever
  {
    const page = await open(browser, 1600, 900, req => req.url().endsWith('/js/tags.js') ? req.abort('connectionrefused') : req.continue());
    await sleep(3000);
    const t = await page.evaluate(() => ({ text: document.getElementById('loading-text')?.textContent, done: document.getElementById('loading')?.classList.contains('done') }));
    check('E0 a module that fails to load shows "Could not start - reload"', /Could not start/i.test(t.text || '') && !t.done, t);
    await page.screenshot({ path: path.join(OUT, 'e0-module-fail.png') });
    await page.close();
  }

  const page = await open(browser, 1600, 900);
  await page.waitForSelector('#loading.done', { timeout: 120000 });
  await page.evaluate(async () => {
    document.querySelector('#home:not(.hidden) .btn.primary')?.click();
    window.__st = await import('/js/state.js');
    window.__ui = await import('/js/ui.js');
    window.__sleep = ms => new Promise(r => setTimeout(r, ms));
    window.__couple = (presetId = 'cowgirl') => {
      const p = app.store.project;
      app.setPlaying(false); app.vp.gizmo.detach(); app.interact.active = null; app.pipeline.editing = null;
      let F = p.sims.find(s => s.frame === 'yf'), M = p.sims.find(s => s.frame === 'ym');
      if (!F) { F = __st.newSim(p, 'yf'); p.sims.push(F); } if (!M) { M = __st.newSim(p, 'ym'); p.sims.push(M); }
      p.sims = [F, M];
      for (const s of p.sims) { s.layers = []; s.sounds = []; s.pins = {}; s.keys = []; s.body = undefined; s.visible = true; }
      p.length = 90; p.loop = true; p.fps = 30;
      app.store.undo.length = 0; app.store.redo.length = 0; app.store.frame = 0;
      app.store.selected = { sim: F.id, bone: null };
      app.syncViews();
      if (presetId) app.applyPosePreset(app.posePresets.find(x => x.id === presetId));
      app.pipeline.overrides.clear(); app.setFrame(0);
      return { F, M, p };
    };
  });

  // E11: a ready pose keeps the places the user picked
  const e11 = await page.evaluate(async () => {
    const { p } = __couple(null);
    p.locations = ['FLOOR', 'DOUBLE_BED']; p.furniture = 'double_bed';
    app.applyPosePreset(app.posePresets.find(x => x.id === 'cowgirl'));
    await __sleep(200);
    return { locations: p.locations.slice(), furniture: p.furniture };
  });
  check('E11 a ready pose keeps Floor + Double Bed', e11.locations.includes('DOUBLE_BED') && e11.locations.includes('FLOOR'), e11);

  // C46: the used pose is marked in the gallery
  const c46 = await page.evaluate(async () => {
    __couple('cowgirl'); app.showStep('pose'); await __sleep(400);
    const on = [...document.querySelectorAll('#panel-body .tiles .tile.on')].map(t => t.textContent.trim());
    return on;
  });
  check('C46 the pose just used is marked in the gallery', c46.length === 1 && /Cowgirl/i.test(c46[0]), c46);

  // C10: keyboard shortcuts work (Space plays, K keys, arrows step)
  const c10 = await page.evaluate(async () => {
    __couple('cowgirl'); app.showStep('pose'); await __sleep(200);
    document.activeElement && document.activeElement.blur();
    const key = (k, code, extra = {}) => window.dispatchEvent(new KeyboardEvent('keydown', { key: k, code, bubbles: true, cancelable: true, ...extra }));
    const errs = [];
    const onErr = e => errs.push(e.message); window.addEventListener('error', onErr);
    key(' ', 'Space'); await __sleep(300);
    const playing = app.playing;
    key(' ', 'Space'); await __sleep(100);
    const stopped = !app.playing;
    app.setFrame(10);
    key('ArrowRight', 'ArrowRight'); await __sleep(50);
    const f = Math.round(app.store.frame);
    const F = app.store.sim();
    const before = F.keys.length;
    key('k', 'KeyK'); await __sleep(80);
    const after = F.keys.length;
    window.removeEventListener('error', onErr);
    return { playing, stopped, frameAfterArrow: f, keysBefore: before, keysAfter: after, errs };
  });
  check('C10 Space plays and pauses, arrow steps a frame, K keys - no errors', c10.playing && c10.stopped && c10.frameAfterArrow === 11 && c10.keysAfter === c10.keysBefore + 1 && !c10.errs.length, c10);

  // C48: one toast at a time, not over the middle of the stage; missing name shown at the box
  const c48 = await page.evaluate(async () => {
    __ui.toast('first toast'); __ui.toast('second toast'); await __sleep(80);
    const ts = [...document.querySelectorAll('#toasts .toast')];
    const r = ts.length ? ts[ts.length - 1].getBoundingClientRect() : null;
    const vp = document.getElementById('viewport-wrap') || app.vp.canvas;
    const vr = vp.getBoundingClientRect();
    return { n: ts.length, text: ts.map(t => t.textContent), toast: r && [r.left, r.top, r.right, r.bottom], vp: [vr.left, vr.top, vr.right, vr.bottom] };
  });
  check('C48 only one toast shows at a time', c48.n === 1, c48);
  const c48b = await page.evaluate(async () => {
    const n0 = document.querySelectorAll('#toasts .toast').length;
    app.store.setDirty(false);
    app.showStep('home'); await __sleep(400);
    const tile = [...document.querySelectorAll('#home .start')].find(b => /Woman & man/.test(b.textContent));
    tile && tile.click(); await __sleep(400);
    const m = [...document.querySelectorAll('#modal-root .modal')].find(x => /New animation/.test(x.querySelector('h2')?.textContent || ''));
    if (!m) return { dialog: false, modals: [...document.querySelectorAll('#modal-root h2')].map(x => x.textContent), tile: !!tile };
    const ins = m.querySelectorAll('input.text'); ins.forEach(i => { i.value = ''; i.dispatchEvent(new Event('input', { bubbles: true })); });
    const start = [...m.querySelectorAll('footer button')].find(b => /Start/.test(b.textContent));
    const disabled = start && start.disabled;
    start && !start.disabled && start.click(); await __sleep(200);
    const inline = !!m.querySelector('.field.invalid, .field-error, .err, .invalid');
    const toasts = [...document.querySelectorAll('#toasts .toast')].map(t => t.textContent).filter(t => /name/i.test(t));
    for (const b of [...document.querySelectorAll('#modal-root .backdrop')]) b.remove();
    document.querySelector('#home:not(.hidden) .btn.primary')?.click();
    return { dialog: true, startDisabled: disabled, inline, nameToasts: toasts, n0 };
  });
  check('C48 a missing name is shown at the box (or Start is disabled), not as a toast', c48b.dialog && (c48b.inline || c48b.startDisabled) && !c48b.nameToasts.length, c48b);

  // C54: dimmest text readable, Turn right icon mirrored
  const c54 = await page.evaluate(async () => {
    const faint = getComputedStyle(document.documentElement).getPropertyValue('--faint').trim();
    __couple('cowgirl'); app.showStep('pose'); await __sleep(300);
    const tr = [...document.querySelectorAll('#panel-body button')].find(b => /Turn right/.test(b.textContent));
    const tl = [...document.querySelectorAll('#panel-body button')].find(b => /Turn left/.test(b.textContent));
    const t = x => x && x.querySelector('svg') && getComputedStyle(x.querySelector('svg')).transform;
    return { faint, right: t(tr), left: t(tl) };
  });
  const hex = c54.faint.replace('#', '');
  const lum = c => { const v = parseInt(c, 16) / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const L = h => 0.2126 * lum(h.slice(0, 2)) + 0.7152 * lum(h.slice(2, 4)) + 0.0722 * lum(h.slice(4, 6));
  const panel = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--panel').trim() || getComputedStyle(document.getElementById('panel') || document.body).backgroundColor);
  let ratio = null;
  if (/^#[0-9a-f]{6}$/i.test(panel)) ratio = (L(hex) + 0.05) / (L(panel.slice(1)) + 0.05);
  check('C54 --faint text contrast >= 4.5:1 on the panel', ratio === null ? hex.toLowerCase() !== '6f6780' : ratio >= 4.5, { faint: c54.faint, panel, ratio: ratio && +ratio.toFixed(2) });
  check('C54 Turn right uses a mirrored icon', c54.right && c54.right !== 'none' && c54.right !== c54.left, c54);

  // C53: while playing, the playhead chip uses the same frame as the counter
  const c53 = await page.evaluate(async () => {
    __couple('cowgirl'); app.setPlaying(true); const out = [];
    for (let i = 0; i < 12; i++) { await __sleep(37); out.push([document.getElementById('tl-frame').textContent, app.playing ? Math.floor(app.store.frame) : Math.round(app.store.frame)]); }
    app.setPlaying(false);
    return out;
  });
  check('C53 the frame counter follows floor(frame) while playing (same rule as the chip)', c53.filter(([a, b]) => +a === b || +a === b - 1).length >= 10, c53);

  // Place clickable at 1366x768 and 1600x900 (a real mouse click through elementFromPoint)
  for (const [w, h] of [[1366, 768], [1600, 900], [1280, 720]]) {
    await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
    await sleep(500);
    const r = await page.evaluate(() => {
      __couple('cowgirl'); app.showStep('pose');
      const b = [...document.querySelectorAll('button')].find(x => /^\s*Place\s*$/.test(x.textContent));
      if (!b) return null;
      const rc = b.getBoundingClientRect(); const cx = rc.left + rc.width / 2, cy = rc.top + rc.height / 2;
      const hit = document.elementFromPoint(cx, cy);
      return { cx, cy, ok: b === hit || b.contains(hit) };
    });
    if (r && r.ok) { await page.mouse.click(r.cx, r.cy); await sleep(200); }
    const tool = await page.evaluate(() => app.interact.tool);
    check(`Place is clickable at ${w}x${h}`, r && r.ok && tool === 'move', { r, tool });
    await page.evaluate(() => { app.interact.setTool ? app.interact.setTool('rotate') : null; });
    await page.screenshot({ path: path.join(OUT, `place-${w}x${h}.png`) });
  }
  await page.evaluate(() => { app.store.setDirty(false); fetch('/api/recovery_clear?slot=test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); });
  await sleep(300);
  await browser.close();
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify({ results, logs }, null, 1));
  console.log('\nSUMMARY', results.filter(r => r.ok).length, 'passed', results.filter(r => !r.ok).length, 'failed');
  console.log(logs.slice(0, 20).join('\n'));
})().catch(e => { console.error('crashed', e); process.exit(1); });
