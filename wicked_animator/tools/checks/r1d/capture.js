// R1-D capture checks (build_plan R1-D checks 3-9):  node tools/checks/r1d/capture.js --port 8844 [--only 3,4]
//  3 retarget round trip, 4 cleaning, 5 loop and keys, 6 face mapping  (in the page, tools/checks/r1d/inpage.js)
//  7 the studio with the mock tracker (steps 1-5, webcam count-in, adults-only box, Make keys + key pop)
//  8 offline: every request not to 127.0.0.1 is blocked; the studio still opens and runs
//  9 real MediaPipe (T1, T2, T4, T6): waiting for the user's OK to download (run when the files are there)
// Starts its own server on the port when nothing answers there (never 8765/8766/8777). Nothing is written to the
// game or the saves (the harness answers every writing route in the browser). Outputs: cache/checks/r1d/.
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn } = require('child_process');
const H = require('../lib/harness.js');

const ROOT = H.ROOT;
const OUT = path.join(ROOT, 'cache', 'checks', 'r1d');
const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
let port = +arg('--port', 8844);
const only = arg('--only', null) ? arg('--only').split(',').map(Number) : null;
const want = n => !only || only.includes(n);
const rows = [];
const row = (name, ok, detail) => { rows.push({ name, ok: !!ok, detail }); return ok; };
const sleep = ms => new Promise(r => setTimeout(r, ms));

function status(p) {
  return new Promise(res => {
    const r = http.get({ host: '127.0.0.1', port: p, path: '/api/status', timeout: 1500 }, resp => {
      let b = ''; resp.on('data', c => { b += c; }); resp.on('end', () => { try { res(JSON.parse(b)); } catch { res(null); } });
    });
    r.on('error', () => res(null)); r.on('timeout', () => { r.destroy(); res(null); });
  });
}

async function ensureServer() {
  if (H.REFUSED.has(port)) throw new Error('refused port ' + port);
  if (await status(port)) return null;
  const env = { ...process.env, ANIMATOR_PORT: String(port), PYTHONUNBUFFERED: '1' };
  fs.mkdirSync(path.join(ROOT, 'cache', 'checks', '_servers'), { recursive: true });
  const log = fs.openSync(path.join(ROOT, 'cache', 'checks', '_servers', `port${port}.log`), 'a');
  const p = spawn('python', [path.join(ROOT, 'backend', 'server.py')], { cwd: ROOT, env, stdio: ['ignore', log, log], windowsHide: true });
  for (let i = 0; i < 300; i++) { const s = await status(port); if (s && s.pid === p.pid) return p; if (p.exitCode !== null) break; await sleep(400); }
  p.kill();
  throw new Error('the server did not start on ' + port);
}

const INPAGE = fs.readFileSync(path.join(__dirname, 'inpage.js'), 'utf8');
async function runInPage(page, which) {
  return page.evaluate(async (src, w) => {
    // eslint-disable-next-line no-new-func
    const fn = new Function(src + '\nreturn r1dTests;')();
    return fn(w);
  }, INPAGE, which);
}

const shotsDone = [];
async function shot(page, name) { const f = await H.shot(page, path.join('cache', 'checks', 'r1d', name)); shotsDone.push(path.relative(ROOT, f)); return f; }
const waitStep = (page, step, timeout = 90000) => page.waitForFunction(s => { const st = window.__cap && window.__cap.studioOpen(); return st && st.step === s; }, { timeout }, step);

async function studioFlow(page, logs) {
  // entry points: the Home card "Film it, play it", then the Pose step section (features/capture.js)
  const card = await page.evaluate(() => [...document.querySelectorAll('#home *')].some(e => e.children.length === 0 && /Film it, play it/.test(e.textContent)));
  await shot(page, 'entry_home_card.png');
  row('7a0 Home shows the card "Film it, play it"', card, { found: card });
  await page.evaluate(async () => { const m = await import('/js/home.js'); m.hideHome(window.app); window.app.showStep('pose'); });
  await sleep(900);
  await page.evaluate(() => { const b = document.querySelector('button[data-capture="video"]'); if (b) b.scrollIntoView({ block: 'center' }); });
  await sleep(300);
  const entry = await page.evaluate(() => {
    const sec = [...document.querySelectorAll('.section')].find(s => /Copy real moves/i.test(s.textContent));
    return { section: !!sec, buttons: sec ? [...sec.querySelectorAll('button[data-capture]')].map(b => b.dataset.capture) : [], hooks: !!window.app.hooks };
  });
  row('7a Pose step shows "Copy real moves" (video, webcam, photo)', entry.section && ['video', 'webcam', 'photo'].every(x => entry.buttons.includes(x)), entry);
  await shot(page, 'entry_pose_step.png');
  const faceEntry = await page.evaluate(async () => { window.app.showStep('face'); await new Promise(r => setTimeout(r, 300)); return !!document.querySelector('button[data-capture="face"]'); });
  row('7b Face step shows "Copy my face (webcam)"', faceEntry, { found: faceEntry });
  await page.evaluate(() => window.app.showStep('pose'));
  await sleep(300);
  // 1. Pick (open from the section's own button). The playhead sits late in the loop (frame 60), so a shorter
  // animation from "Make the animation this long" must bring it back inside (round-1 gate finding)
  await page.evaluate(async () => { window.__cap = await import('/js/capture.js'); window.app.setFrame(Math.min(60, window.app.store.project.length - 1)); });
  await page.click('button[data-capture="video"]');
  await page.waitForFunction(() => window.__cap.studioOpen() && window.__cap.studioOpen().video, { timeout: 60000 });
  await sleep(700);
  const gate = await page.evaluate(() => {
    const st = window.__cap.studioOpen();
    const go = document.querySelector('.cap-foot .cap-go');
    return { step: st.step, disabled: go.disabled, adult: st.adult, label: go.textContent.trim() };
  });
  await shot(page, 'studio_1_pick.png');
  // clicking the disabled button does nothing; read() refuses without the tick too
  await page.evaluate(() => { document.querySelector('.cap-foot .cap-go').click(); window.__cap.studioOpen().read(); });
  await sleep(300);
  const still = await page.evaluate(() => window.__cap.studioOpen().step);
  row('7c Reading is disabled until the adults-only box is ticked', gate.disabled && !gate.adult && still === 'pick', { ...gate, step_after_trying: still });
  // tick the box (a real click on the label)
  await page.click('.cap-adult');
  await sleep(200);
  const ticked = await page.evaluate(() => ({ adult: window.__cap.studioOpen().adult, disabled: document.querySelector('.cap-foot .cap-go').disabled }));
  // 2. Part (the test clip is 20 s long)
  await page.click('.cap-foot .cap-go');
  await waitStep(page, 'part');
  await sleep(1200);
  await page.evaluate(() => { const st = window.__cap.studioOpen(); st.range = [2, 8]; st.render(); });
  await sleep(1200);
  await shot(page, 'studio_2_part.png');
  // 3. Reading
  await page.click('.cap-foot .cap-go');
  await waitStep(page, 'reading');
  await sleep(1400);
  await shot(page, 'studio_3_reading.png');
  await waitStep(page, 'check', 120000);
  await sleep(900);
  // 4. Check and trim
  await page.evaluate(() => { const b = [...document.querySelectorAll('.cap-loop-btn')][0]; if (b) b.click(); });
  await sleep(900);
  const chk = await page.evaluate(() => { const st = window.__cap.studioOpen(); return { frames: st.clean.t.length, loop: st.loop, report: st.clean.report, readMs: Math.round(st.readMs || 0) }; });
  await shot(page, 'studio_4_check.png');
  // 5. Put it on
  await page.click('.cap-foot .cap-go');
  await waitStep(page, 'apply');
  await sleep(500);
  // with a partner in the scene "Make the animation this long" starts off; turned on, it says the partner stretches
  const fitSwitch = () => [...document.querySelectorAll('.cap-switch')].find(el => /Make the animation this long/.test(el.textContent));
  const fitDefault = await page.evaluate(fs => { const el = (0, eval)(fs)(); return { sims: window.app.store.project.sims.length, length: window.app.store.project.length, frame: window.app.store.frame, on: !!(el && el.querySelector('input').checked), note: el ? el.textContent : null }; }, `(${fitSwitch})`);
  await page.evaluate(fs => { (0, eval)(fs)().querySelector('input').click(); }, `(${fitSwitch})`);
  await sleep(300);
  const fitOn = await page.evaluate(fs => { const el = (0, eval)(fs)(); return { on: el.querySelector('input').checked, note: el.textContent, stored: window.__cap.studioOpen().fitLength }; }, `(${fitSwitch})`);
  row('7c2 two sims: "Make the animation this long" starts off; on, it says the partner is stretched too',
    fitDefault.sims >= 2 && !fitDefault.on && !/stretched/.test(fitDefault.note || '') && fitOn.on && fitOn.stored === true && /animation is stretched to this length too/.test(fitOn.note),
    { default: fitDefault, turned_on: fitOn });
  await shot(page, 'studio_5_put_it_on.png');
  // Make keys: count keys, and see them pop in on the timeline
  const res = await page.evaluate(async () => {
    const app = window.app, st = window.__cap.studioOpen();
    const sim = app.store.sim(st.target);
    const before = sim.keys.length, undo = app.store.undo.length;
    const flashes = [];
    const tl = app.timeline, orig = tl && tl.flash;
    if (tl && orig) tl.flash = function (...a) { flashes.push(a[1]); return orig.apply(this, a); };
    document.querySelector('.cap-make').click();
    await new Promise(r => setTimeout(r, 2200));
    if (tl && orig) tl.flash = orig;
    const after = app.store.sim(sim.id).keys;
    const toastText = [...document.querySelectorAll('#toasts .toast')].map(t => t.textContent).join(' | ');
    const p = app.store.project, partner = p.sims.find(x => x.id !== sim.id);
    const fr = document.getElementById('tl-frame');
    const timing = { frame: app.store.frame, length: p.length, timelineFit: app.timeline && app.timeline._fitLength, frameBox: fr ? +fr.textContent : null,
      partnerKeysInside: partner ? partner.keys.every(k => k.frame < p.length) : true };
    return { timing, before, after: after.length, bodyKeys: after.filter(k => !k.faceOnly).length, withFace: after.filter(k => k.face).length, undoSteps: app.store.undo.length - undo, flashes: flashes.length, toast: toastText, studioClosed: !window.__cap.studioOpen(), length: app.store.project.length };
  });
  await shot(page, 'studio_6_keys_made.png');
  const tm = res.timing;
  row('7d2 a new length keeps the playhead inside it, refits the timeline and says so', tm.length !== fitDefault.length && fitDefault.frame >= tm.length && tm.frame < tm.length && tm.frame >= 0
    && tm.timelineFit === tm.length && (tm.frameBox === null || tm.frameBox === tm.frame) && tm.partnerKeysInside
    && /The animation is [\d.]+ s long now\. .+'s animation was stretched to match\./.test(res.toast), { length_before: fitDefault.length, frame_before: fitDefault.frame, ...tm, toast: res.toast });
  row('7d "Make keys" adds keys that pop in (one undo step)', res.after > 1 && res.flashes > 0 && res.undoSteps === 1 && res.studioClosed && /Made \d+ keys? on .+ from your video\.( .+)? Undo with Ctrl\+Z\./.test(res.toast),
    { ...res, check_step: chk });
  // undo gives the old keys back
  const undoneAll = await page.evaluate(() => { const app = window.app; app.store.undoStep(); const p = app.store.project; return { keys: app.store.sim(app.store.selected.sim).keys.length, length: p.length, frame: app.store.frame, timelineFit: app.timeline && app.timeline._fitLength }; });
  const undone = undoneAll.keys;
  row('7e Ctrl+Z after Make keys brings the old animation back (and its length)', undone === res.before && undoneAll.length === fitDefault.length && undoneAll.frame < undoneAll.length && undoneAll.timelineFit === undoneAll.length,
    { keys_after_undo: undone, before: res.before, ...undoneAll });
  // webcam: count-in, recording, check
  await page.evaluate(async () => { window.__captureFast = false; window.__cap.openCaptureStudio(window.app, { source: 'webcam' }); });
  await page.waitForFunction(() => window.__cap.studioOpen() && window.__cap.studioOpen().cam, { timeout: 60000 });
  await sleep(900);
  await page.click('.cap-adult');
  await sleep(300);
  await shot(page, 'studio_webcam_ready.png');
  await page.keyboard.press('Space');
  await sleep(450);
  await page.evaluate(() => document.querySelectorAll('.cap-count b').forEach(b => b.getAnimations().forEach(a => { a.currentTime = 250; a.pause(); })));
  await shot(page, 'studio_webcam_countin.png');
  const counted = await page.evaluate(() => { const b = document.querySelector('.cap-count b'); return b ? b.textContent : null; });
  await page.evaluate(() => document.querySelectorAll('.cap-count b').forEach(b => b.getAnimations().forEach(a => a.play())));
  await page.waitForFunction(() => window.__cap.studioOpen() && window.__cap.studioOpen().recording, { timeout: 15000 });
  await sleep(2600);
  await shot(page, 'studio_webcam_recording.png');
  await page.keyboard.press('Space');
  await waitStep(page, 'check', 60000);
  await sleep(700);
  await shot(page, 'studio_webcam_check.png');
  const cam = await page.evaluate(() => { const st = window.__cap.studioOpen(); return { frames: st.clean && st.clean.t.length, mirrored: st.stage.classList.contains('mirror') }; });
  row('7f webcam: 3-2-1 count-in, Space records and stops, then Check', counted === '3' && cam.frames > 30, { count_shown: counted, ...cam });
  await page.evaluate(() => window.__cap.studioOpen().close());
  // face and photo
  await page.evaluate(() => window.__cap.openCaptureStudio(window.app, { source: 'face' }));
  await page.waitForFunction(() => window.__cap.studioOpen() && window.__cap.studioOpen().cam, { timeout: 60000 });
  await sleep(900);
  await shot(page, 'studio_face_ready.png');
  await page.evaluate(() => window.__cap.studioOpen().close());
  await page.evaluate(() => window.__cap.openCaptureStudio(window.app, { source: 'photo' }));
  await waitStep(page, 'photo', 60000);
  await page.click('.cap-adult');
  await sleep(700);
  await shot(page, 'studio_photo.png');
  const photo = await page.evaluate(async () => {
    const app = window.app, sim = app.store.sim(window.__cap.studioOpen().target);
    const before = sim.keys.length;
    app.setFrame(15);
    document.querySelector('.cap-foot .cap-go').click();
    await new Promise(r => setTimeout(r, 400));
    const after = app.store.sim(sim.id).keys;
    const res = { before, after: after.length, keyAt15: !!after.find(k => k.frame === 15), closed: !window.__cap.studioOpen() };
    app.store.undoStep();
    return res;
  });
  row('7g "From a photo" gives one key at the current frame', photo.keyAt15 && photo.closed && photo.after <= photo.before + 1, photo);
  const errs = logs.filter(l => l.type === 'pageerror' || (l.type === 'error' && !/favicon|Failed to load resource/.test(l.text)));
  row('7h no page errors during the studio flow', !errs.length, errs.slice(0, 5));
}

async function offline(logs) {
  // load normally (three.js comes from its CDN in index.html - the app shell, not capture), then cut every request
  // that does not go to 127.0.0.1 and use capture from start to finish
  const { browser, page } = await H.open(port, { query: 'captureMock=1', intercept: false });
  const outside = [], shell = [];
  let strict = false;
  page.on('request', r => { const u = r.url(); if (!/^(https?:\/\/127\.0\.0\.1[:/]|data:|blob:)/.test(u)) (strict ? outside : shell).push(u); });
  try {
    await page.setRequestInterception(true);
    page.on('request', r => {
      const u = r.url();
      if (strict && !/^(https?:\/\/127\.0\.0\.1[:/]|data:|blob:)/.test(u)) return r.abort('internetdisconnected').catch(() => {});
      return r.continue().catch(() => {});
    });
    strict = true;
    const res = await page.evaluate(async () => {
      const cap = await import('/js/capture.js');
      const st = cap.openCaptureStudio(window.app, { source: 'video' });
      for (let i = 0; i < 200 && !st.video; i++) await new Promise(r => setTimeout(r, 100));
      st.adult = true; st.range = [0, 4]; st.render();
      await st.read();
      const frames = st.clean ? st.clean.t.length : 0;
      st._setStep('apply');
      const sim = window.app.store.sim(st.target), before = sim.keys.length;
      document.querySelector('.cap-make').click();
      await new Promise(r => setTimeout(r, 800));
      const after = window.app.store.sim(sim.id).keys.length;
      window.app.store.undoStep();
      return { frames, before, after };
    });
    row('8 offline: the studio opens and runs; no request left 127.0.0.1', res.frames > 30 && res.after > 1 && outside.length === 0,
      { ...res, requests_outside_127_after_cut: outside, app_shell_before_cut: [...new Set(shell.map(u => new URL(u).host))] });
  } catch (e) { row('8 offline: the studio opens and runs; no request left 127.0.0.1', false, String(e && e.stack || e)); }
  await browser.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  let server = null;
  try { server = await ensureServer(); } catch (e) { port = 8851; server = await ensureServer(); }
  const t0 = Date.now();
  try {
    if ([3, 4, 5, 6].some(want)) {
      const { browser, page, logs } = await H.open(port, {});
      const which = [3, 4, 5, 6].filter(want);
      const res = await runInPage(page, which);
      for (const r of res) row(r.name, r.ok, r.detail);
      await browser.close();
    }
    if (want(7)) {
      const { browser, page, logs } = await H.open(port, { query: 'captureMock=1' });
      try { await studioFlow(page, logs); } catch (e) { row('7 studio flow', false, String(e && e.stack || e)); await shot(page, 'studio_error.png').catch(() => {}); }
      // the first-time download panel (the real reader is not installed): shown, never clicked
      await page.evaluate(() => { window.__captureMock = false; });
      const inst = await page.evaluate(async () => {
        const u = new URL(location.href);
        // without the mock the studio asks for the one-time download (it is not clicked here)
        history.replaceState(null, '', u.pathname + '?slot=test');
        const cap = await import('/js/capture.js');
        const st = cap.openCaptureStudio(window.app, { source: 'video' });
        await new Promise(r => setTimeout(r, 900));
        const txt = document.querySelector('.cap-install') ? document.querySelector('.cap-install').textContent : '';
        return { step: st.step, text: txt, intro: !!document.querySelector('.cap-intro') };
      });
      await shot(page, 'studio_0_first_time_download.png');
      row('7i first-time download panel (not installed: shown, not clicked)', inst.step === 'install' && /one-time download \(64 MB\)/.test(inst.text) && inst.intro && /never leave this PC/.test(inst.text), inst);
      await browser.close();
    }
    if (want(8)) await offline();
    if (want(9)) {
      const st = await new Promise(res => http.get({ host: '127.0.0.1', port, path: '/api/capture_status' }, r => { let b = ''; r.on('data', c => { b += c; }); r.on('end', () => res(JSON.parse(b))); }).on('error', () => res({})));
      if (!st.installed) row('9 T1/T2/T4/T6 on real MediaPipe: waiting for the user\'s OK to download (skipped)', true, { installed: false, missing: st.missing, bytes_needed: st.bytes_needed });
      else row('9 T1/T2/T4/T6 on real MediaPipe', false, 'MediaPipe is installed - run tools/checks/r1d/realmp.js (not part of round 1)');
    }
  } finally {
    if (server) server.kill();
  }
  const ok = rows.every(r => r.ok);
  fs.writeFileSync(path.join(OUT, 'capture_check.json'), JSON.stringify({ port, ok, seconds: Math.round((Date.now() - t0) / 1000), rows, screenshots: shotsDone }, null, 1));
  H.report(rows, `R1-D capture checks (port ${port})`);
  if (shotsDone.length) console.log('screenshots:\n  ' + shotsDone.join('\n  '));
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
