// End-to-end browser test of Novulon's Wicked Animator (puppeteer-core + headless Chrome).
//   node tools/e2e.js          (the server must already run at http://127.0.0.1:8777)
// Screenshots, report.json and the test's own exported packages end up in cache/e2e/.
// It only creates files through the app's own endpoints and moves them out of the Mods / Documents folders again.
const path = require('path'), fs = require('fs'), os = require('os'), cp = require('child_process');
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');

const ROOT = path.join(__dirname, '..');
const OUT = path.join(ROOT, 'cache', 'fixwave', 'verify1', 'e2e');
const APP_URL = 'http://127.0.0.1:8777/';
const DOCS = path.join(os.homedir(), 'Documents');
const FITSTUDIO = path.join(DOCS, 'Electronic Arts', 'The Sims 4', 'Mods', 'FitStudio');
const MYANIM = path.join(FITSTUDIO, 'MyAnimations');
const SOUNDKIT = path.join(FITSTUDIO, 'FitStudio_Sounds.package');
const EXPORTS = path.join(DOCS, 'Wicked Animator Exports');
const W = 1600, H = 900;
const ONLY = process.argv[2] ? new Set(process.argv[2].split(',')) : null;   // e.g. "1,2,3" runs only those steps (1 always runs)

const results = [], logs = [], info = {};
let STEP = 'boot', shotN = 0, page, browser;
const sleep = ms => new Promise(r => setTimeout(r, ms));

function check(name, ok, detail) {
  results.push({ step: STEP, name, ok: !!ok, detail: detail === undefined ? null : detail });
  const d = detail === undefined || detail === null || detail === '' ? '' : ' :: ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)).slice(0, 700);
  console.log(`${ok ? 'PASS' : 'FAIL'} [${STEP}] ${name}${d}`);
}

async function step(id, name, fn) {
  if (ONLY && id !== 1 && !ONLY.has(String(id))) return;
  STEP = `${id} ${name}`;
  console.log(`\n=== ${STEP}`);
  try { await page.evaluate(n => { if (window.__e2e) window.__e2e.step = n; }, STEP); } catch { /* not loaded yet */ }
  const t0 = Date.now();
  try { await fn(); } catch (e) {
    check('step ran without exception', false, String(e && (e.stack || e.message)));
    try { await shot(`step${id}-exception`); } catch { /* ignore */ }
  }
  info[`stepMs ${STEP}`] = Date.now() - t0;
}

// Run a page function that returns {checks: [[name, ok, detail]], data}; the checks are recorded here.
async function pe(fn, ...args) {
  const r = await page.evaluate(fn, ...args);
  if (r && Array.isArray(r.checks)) for (const [n, ok, d] of r.checks) check(n, ok, d);
  return r ? r.data : undefined;
}

async function shot(name) {
  const f = path.join(OUT, `${String(++shotN).padStart(2, '0')}-${name}.png`);
  await page.screenshot({ path: f });
  return f;
}

function listDir(d) { try { return fs.readdirSync(d); } catch { return []; } }
function moveInto(src, destDir) {
  fs.mkdirSync(destDir, { recursive: true });
  const dst = path.join(destDir, path.basename(src));
  if (fs.existsSync(dst)) fs.rmSync(dst, { recursive: true, force: true });   // an older copy from a previous test run
  fs.renameSync(src, dst);
  return dst;
}

// A small proxy for the page's requests to the app server: at most 4 at a time, refused connections retried.
const http = require('http');
const proxy = { on: false, retries: 0, failed: 0, served: 0 };
const proxyAgent = new http.Agent({ keepAlive: false, maxSockets: 4 });
function proxyFetch(req) {
  const u = new URL(req.url());
  const headers = { ...req.headers() };
  const body = req.postData();
  const once = () => new Promise((res, rej) => {
    const r = http.request({ method: req.method(), hostname: u.hostname, port: u.port, path: u.pathname + u.search, headers, agent: proxyAgent }, resp => {
      const chunks = []; resp.on('data', c => chunks.push(c)); resp.on('end', () => res({ status: resp.statusCode, headers: resp.headers, body: Buffer.concat(chunks) })); resp.on('error', rej);
    });
    r.on('error', rej);
    if (body) r.write(body);
    r.end();
  });
  return (async () => {
    for (let i = 0; ; i++) {
      try { return await once(); } catch (e) {
        if (i >= 12 || !['ECONNREFUSED', 'ECONNRESET'].includes(e.code)) throw e;
        proxy.retries++; await sleep(60 * (i + 1));
      }
    }
  })();
}
async function enableProxy() {
  proxy.on = true;
  await page.setRequestInterception(true);
  page.on('request', async req => {
    if (req.isInterceptResolutionHandled && req.isInterceptResolutionHandled()) return;
    if (!req.url().startsWith('http://127.0.0.1:8777/')) return req.continue().catch(() => {});
    try {
      const r = await proxyFetch(req);
      const h = {};
      for (const [k, v] of Object.entries(r.headers)) if (!['content-length', 'connection', 'transfer-encoding', 'keep-alive'].includes(k)) h[k] = Array.isArray(v) ? v.join(', ') : v;
      proxy.served++;
      await req.respond({ status: r.status, headers: h, body: r.body });
    } catch (e) { proxy.failed++; proxy.lastError = String(e && e.stack || e).slice(0, 400); if (proxy.failed < 3) console.log('proxy error', req.url(), proxy.lastError); await req.abort('connectionrefused').catch(() => {}); }
  });
}

function verifyPkg(mode, pkg, expect, tag) {
  const ef = path.join(OUT, `expect_${tag}.json`);
  fs.writeFileSync(ef, JSON.stringify(expect));
  const r = cp.spawnSync('python', [path.join(OUT, 'verify_pkg.py'), mode, pkg, ef], { encoding: 'utf8', maxBuffer: 256 << 20 });
  const last = (r.stdout || '').trim().split('\n').pop();
  let j = null;
  try { j = JSON.parse(last); } catch { check(`python verifier (${tag}) ran`, false, (r.stderr || '').slice(-1500) + last); return null; }
  for (const [n, ok, d] of j.checks) check(`[${tag}] ${n}`, ok, d);
  return j.info;
}

// ------------------------------------------------------------------ page helpers
async function installHelpers() {
  await page.evaluate(async () => {
    window.__m = {
      motion: await import('/js/motion.js'), animation: await import('/js/animation.js'), share: await import('/js/share.js'),
      api: (await import('/js/api.js')).api, face: await import('/js/face.js'), physics: await import('/js/physics.js'),
      pipeline: await import('/js/pipeline.js'), state: await import('/js/state.js'), posemath: await import('/js/posemath.js'),
      bones: await import('/js/bones.js'),
    };
    const E = window.__e2e = window.__e2e || { toasts: [], step: 'boot' };
    E.sleep = ms => new Promise(r => setTimeout(r, ms));
    E.waitFor = async (fn, ms = 10000, every = 50) => {
      const t0 = performance.now();
      while (performance.now() - t0 < ms) { try { const v = await fn(); if (v) return v; } catch { /* keep waiting */ } await E.sleep(every); }
      return null;
    };
    E.V = (x = 0, y = 0, z = 0) => app.vp.camera.position.clone().set(x, y, z);
    E.Q = () => app.vp.camera.quaternion.clone().identity();
    E.F = () => app.store.project.sims.find(s => s.frame === 'yf');
    E.M = () => app.store.project.sims.find(s => s.frame === 'ym');
    E.view = s => app.simViews.get(s.id);
    E.badBones = () => {
      const out = [];
      for (const [, v] of app.simViews) for (const b of v.bones) {
        const a = b.position.toArray().concat(b.quaternion.toArray());
        if (!a.every(Number.isFinite)) { out.push(b.name); if (out.length > 10) return out; }
      }
      return out;
    };
    E.wp = (s, bone) => { const v = app.simViews.get(s.id); v.group.updateMatrixWorld(true); return v.worldPos(bone).toArray(); };
    E.dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
    E.qang = (a, b) => { const na = Math.hypot(a[0], a[1], a[2], a[3]) || 1, nb = Math.hypot(b[0], b[1], b[2], b[3]) || 1; const d = Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]) / na / nb; return 2 * Math.acos(Math.min(1, d)) * 180 / Math.PI; };
    E.hang = (a, b) => { let d = Math.atan2(b[0], b[2]) - Math.atan2(a[0], a[2]); while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI; return d * 180 / Math.PI; };
    E.poseFinite = pose => Object.values(pose.rot || {}).every(q => q.every(Number.isFinite)) && Object.values(pose.pos || {}).every(q => q.every(Number.isFinite));
    E.poseDiff = (a, b) => { let m = 0; for (const n of Object.keys(a.rot)) if (b.rot[n]) m = Math.max(m, E.qang(a.rot[n], b.rot[n])); return m; };
    E.btn = (text, root = document) => [...root.querySelectorAll('button')].find(b => b.textContent.trim().includes(text));
    E.findToggle = (title, root = document) => { const row = [...root.querySelectorAll('.toggle-row')].find(r => r.querySelector('b')?.textContent.trim() === title); return row ? row.querySelector('input[type=checkbox]') : null; };
    E.findSlider = (label, root = document) => { const s = [...root.querySelectorAll('.slider')].find(r => r.querySelector('label')?.textContent.trim().includes(label)); return s ? s.querySelector('input[type=range]') : null; };
    E.setRange = (el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); };
    E.setValue = (el, v, ev = 'change') => { el.value = v; el.dispatchEvent(new Event(ev, { bubbles: true })); };
    E.modal = title => [...document.querySelectorAll('#modal-root .modal')].find(m => !title || (m.querySelector('h2')?.textContent || '').includes(title)) || null;
    E.modalBtn = (title, label) => { const m = E.modal(title); return m ? [...m.querySelectorAll('footer button')].find(b => b.textContent.trim().includes(label)) : null; };
    E.closeModals = () => { for (const b of [...document.querySelectorAll('#modal-root .backdrop')]) b.remove(); };
    E.newToasts = n => E.toasts.slice(n).map(t => t.text);
    E.flush = () => new Promise(r => setTimeout(r, 30));
    E.screen = (s, bone) => {
      const v = app.simViews.get(s.id); v.group.updateMatrixWorld(true);
      const p = v.worldPos(bone).project(app.vp.camera); const r = app.vp.canvas.getBoundingClientRect();
      return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height];
    };
    E.screenOfWorld = w => { const p = E.V(...w).project(app.vp.camera); const r = app.vp.canvas.getBoundingClientRect(); return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; };
    // a clean couple (one female, one male body) in a ready pose, no motions/sounds/pins, 3 s loop
    E.resetCouple = (presetId = 'cowgirl') => {
      const p = app.store.project;
      app.setPlaying(false);
      app.vp.gizmo.detach(); app.interact.active = null; app.pipeline.editing = null;
      let F = p.sims.find(s => s.frame === 'yf'), M = p.sims.find(s => s.frame === 'ym');
      if (!F) { F = __m.state.newSim(p, 'yf'); p.sims.push(F); }
      if (!M) { M = __m.state.newSim(p, 'ym'); p.sims.push(M); }
      p.sims = [F, M];
      for (const s of p.sims) { s.layers = []; s.sounds = []; s.pins = {}; s.keys = []; s.body = undefined; s.naked = undefined; s.visible = true; }
      p.length = 90; p.loop = true; p.fps = 30;
      app.store.undo.length = 0; app.store.redo.length = 0;
      app.store.frame = 0;
      app.store.selected = { sim: F.id, bone: null };
      app.syncViews();
      const pr = app.posePresets.find(x => x.id === presetId);
      app.applyPosePreset(pr);
      app.pipeline.overrides.clear();
      app.setFrame(0);
      return { F, M };
    };
    if (!E._obs) {
      E._obs = new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) if (n.classList && n.classList.contains('toast')) E.toasts.push({ kind: n.className, text: n.textContent, step: E.step }); });
      E._obs.observe(document.getElementById('toasts'), { childList: true });
    }
  });
}

// ------------------------------------------------------------------ the test
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  for (const f of listDir(OUT)) if (/^\d\d-.*\.png$/.test(f)) fs.unlinkSync(path.join(OUT, f));
  const before = {
    myAnim: listDir(MYANIM), soundKit: fs.existsSync(SOUNDKIT), exports: fs.existsSync(EXPORTS),
    exportsList: listDir(EXPORTS),
  };
  info.before = before;

  browser = await puppeteer.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: 'new', protocolTimeout: 900000,
    args: ['--use-angle=d3d11', '--enable-webgl', '--ignore-gpu-blocklist', `--window-size=${W},${H}`],
  });
  page = await browser.newPage();
  await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
  page.on('console', m => { const t = m.type(); if (t === 'error' || t === 'warning' || t === 'warn') logs.push({ step: STEP, type: t, text: m.text(), loc: m.location() }); });
  page.on('pageerror', e => logs.push({ step: STEP, type: 'pageerror', text: e.message, stack: e.stack }));
  page.on('requestfailed', r => logs.push({ step: STEP, type: 'requestfailed', text: `${r.url()} ${r.failure() && r.failure().errorText}` }));
  page.on('response', r => { if (r.status() >= 400) logs.push({ step: STEP, type: 'http', text: `${r.status()} ${r.request().method()} ${r.url()}` }); });
  page.on('dialog', d => { logs.push({ step: STEP, type: 'dialog', text: d.message() }); d.dismiss().catch(() => {}); });
  await page.evaluateOnNewDocument(() => { try { localStorage.setItem('fsa.tourDone', 'true'); localStorage.removeItem('fsa.autosave'); } catch { /* ignore */ } });

  const initialServer = await (async () => {
    const j = async u => (await fetch('http://127.0.0.1:8777' + u)).json();
    return { projects: (await j('/api/projects')).map(p => p.file), progressions: await j('/api/progressions') };
  })();
  info.initialServer = initialServer;

  // ================================================================ 1
  await step(1, 'load, Home, Woman & man, name dialog', async () => {
    // First a plain start, exactly like a browser. The server may refuse connections when many arrive at once; if it
    // does, that is reported and the rest of the test goes through a small proxy that retries refused connections.
    let loaded = false, attempts = 0;
    for (attempts = 1; attempts <= 6 && !loaded; attempts++) {
      if ((attempts === 3 || process.env.E2E_PROXY) && !proxy.on) await enableProxy();
      const t0 = Date.now(), nLog = logs.length;
      await page.goto(APP_URL, { waitUntil: 'networkidle0', timeout: 180000 }).catch(e => logs.push({ step: STEP, type: 'error', text: 'goto: ' + e.message }));
      loaded = await page.waitForSelector('#loading.done', { timeout: 60000 }).then(() => true).catch(() => false);
      info.loadMs = Date.now() - t0;
      const refused = logs.slice(nLog).filter(l => /ERR_CONNECTION_REFUSED/.test(l.text));
      if (!loaded || refused.length) {
        const text = await page.evaluate(() => document.getElementById('loading-text').textContent).catch(() => '?');
        check(`app start attempt ${attempts}${proxy.on ? ' (via retry proxy)' : ' (plain browser)'}: every file loads`, false, { loadingText: text, refusedRequests: refused.filter(l => l.type === 'requestfailed').map(l => l.text.replace(/ net::.*/, '')).slice(0, 12) });
        if (refused.length && loaded) loaded = false;   // half-loaded app: start again
      }
    }
    info.proxy = proxy;
    check('app starts (#loading.done)', loaded, { attempts: attempts - 1, viaProxy: proxy.on, proxyRetries: proxy.retries });
    if (!loaded) throw new Error('the app never finished loading');
    await installHelpers();
    await sleep(600);
    await pe(() => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const home = document.getElementById('home');
      C('Home is shown on a fresh start', !home.classList.contains('hidden'));
      const starts = home.querySelectorAll('.starts .start');
      C('Home shows the start tiles', starts.length >= 8, starts.length);
      C('fresh start: no autosave, tour marked done', localStorage.getItem('fsa.autosave') === null || localStorage.getItem('fsa.autosave') === 'null', localStorage.getItem('fsa.tourDone'));
      C('default scene has 2 sims behind Home', app.store.project.sims.length === 2);
      C('no NaN bones after load', __e2e.badBones().length === 0, __e2e.badBones());
      C('no tour shown', !document.querySelector('#tour-root .tour-card'));
      return { checks: out };
    });
    await shot('home');
    await page.click('#home .start.feature');
    await page.waitForFunction(() => __e2e.modal('New animation'), { timeout: 8000 });
    const inputs = await page.$$('#modal-root .modal input.text');
    await inputs[0].click({ clickCount: 3 }); await inputs[0].type('E2E Test A');
    await inputs[1].click({ clickCount: 3 }); await inputs[1].type('E2E');
    await shot('name-dialog');
    await pe(() => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const pv = document.querySelector('#modal-root .name-preview');
      C('name dialog preview follows the typing', pv && pv.textContent.includes('E2E Test A') && pv.textContent.includes('by E2E'), pv && pv.textContent);
      return { checks: out };
    });
    await page.evaluate(() => __e2e.modalBtn('New animation', 'Start animating').click());
    await sleep(800);
    await pe(() => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const p = app.store.project;
      C('Home closes after the name dialog', document.getElementById('home').classList.contains('hidden'));
      C('dialog closed', !__e2e.modal());
      C('editor opens on step 2 (Pose)', app.step === 'pose', app.step);
      C('project named "E2E Test A" by "E2E"', p.name === 'E2E Test A' && p.author === 'E2E', [p.name, p.author]);
      C('title chip shows the name', document.getElementById('pc-name').textContent === 'E2E Test A' && document.getElementById('pc-by').textContent === 'by E2E');
      C('Woman & man = one female + one male body', p.sims.map(s => s.frame).join() === 'yf,ym', p.sims.map(s => s.frame));
      C('each sim starts with one key at frame 0', p.sims.every(s => s.keys.length === 1 && s.keys[0].frame === 0));
      C('not marked dirty right after creating', !app.store.dirty);
      return { checks: out };
    });
    await shot('editor-new');
  });

  // ================================================================ 2
  await step(2, 'every rail step renders', async () => {
    const TITLES = { scene: 'Scene', pose: 'Pose', motion: 'Motion', body: 'Body', face: 'Face', sounds: 'Sounds', details: 'Details', share: 'Share', library: 'Library' };
    for (const [s, title] of Object.entries(TITLES)) {
      const nErr = logs.length;
      await page.click(`#rail button[data-step=${s}]`);
      if (s === 'library') await page.waitForFunction(() => !app.library.el.count.textContent.includes('Searching') && app.library.el.count.textContent, { timeout: 20000 }).catch(() => {});
      if (s === 'share') await page.waitForFunction(() => !document.getElementById('panel-body').textContent.includes('Loading...'), { timeout: 20000 }).catch(() => {});
      await sleep(350);
      await pe((s, title) => {
        const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
        const body = document.getElementById('panel-body');
        C(`${title}: panel title`, document.getElementById('panel-title').textContent === title, document.getElementById('panel-title').textContent);
        C(`${title}: rail button active`, document.querySelector(`#rail button[data-step=${s}]`).classList.contains('active'));
        C(`${title}: panel has content`, body.children.length > 0 && body.textContent.trim().length > 20, body.textContent.slice(0, 80));
        C(`${title}: no "Could not load" box`, !/Could not load/.test(body.textContent), [...body.querySelectorAll('.warn-box')].map(x => x.textContent));
        if (s === 'library') C('Library lists animations', app.library.items.length > 0 && /animation/.test(app.library.el.count.textContent), app.library.el.count.textContent);
        if (s !== 'library') C(`${title}: footer navigation`, document.getElementById('panel-foot').querySelectorAll('button').length >= 1);
        return { checks: out };
      }, s, title);
      const newErr = logs.slice(nErr).filter(l => l.type === 'error' || l.type === 'pageerror');
      check(`${title}: no console errors while opening`, !newErr.length, newErr.map(l => l.text));
      await shot(`step-${s}`);
    }
    // footer Next / Back
    await page.click('#rail button[data-step=scene]');
    await sleep(200);
    await page.evaluate(() => document.querySelector('#panel-foot .btn.primary').click());
    await sleep(200);
    check('footer "Next: Pose" goes to Pose', await page.evaluate(() => app.step) === 'pose');
    await page.evaluate(() => __e2e.btn('Back', document.getElementById('panel-foot')).click());
    await sleep(200);
    check('footer "Back" goes to Scene', await page.evaluate(() => app.step) === 'scene');
    // Home
    await page.click('#rail button[data-step=home]');
    await page.waitForFunction(() => !document.getElementById('home').classList.contains('hidden') && !document.querySelector('#home .projects').textContent.includes('Loading'), { timeout: 10000 });
    await pe(() => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const home = document.getElementById('home');
      C('Home opens from the rail', !home.classList.contains('hidden'));
      C('Home lists saved animations', home.querySelectorAll('.projects .proj').length >= 1 || home.querySelector('.projects .empty'), home.querySelectorAll('.projects .proj').length);
      const cont = home.querySelector('.home-top .btn.primary');
      C('Home offers to go back to the editor', !!cont, cont && cont.textContent);
      return { checks: out };
    });
    await shot('home-from-rail');
    await page.click('#home .home-top .btn.primary');
    await sleep(300);
    check('the Continue/Go to the editor button closes Home', await page.evaluate(() => document.getElementById('home').classList.contains('hidden')));
    // Help
    await page.click('#btn-help');
    await sleep(300);
    check('Help opens the Controls dialog', await page.evaluate(() => !!__e2e.modal('Controls')));
    await shot('help');
    await page.evaluate(() => __e2e.modalBtn('Controls', 'Got it').click());
    await sleep(200);
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    await page.keyboard.press('?');
    await sleep(300);
    check('"?" opens Help too', await page.evaluate(() => !!__e2e.modal('Controls')));
    await page.keyboard.press('Escape');
    await sleep(200);
    check('Escape closes the dialog', await page.evaluate(() => !__e2e.modal()));
  });

  // ================================================================ 3
  await step(3, 'ready poses (couple + solo) and Pose tools', async () => {
    await page.waitForFunction(() => app.posePresets && app.posePresets.length, { timeout: 90000 });
    const d = await pe(() => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, p = app.store.project;
      app.setPlaying(false); app.setFrame(0);
      const couples = app.posePresets.filter(x => x.group === 'couple' && !x.mine), solos = app.posePresets.filter(x => x.group === 'solo' && !x.mine);
      C('ready poses loaded', couples.length > 0 && solos.length > 0, { couples: couples.length, solos: solos.length });
      C('every preset pose holds finite numbers', app.posePresets.every(pr => pr.sims.every(s => E.poseFinite(s.pose))));
      const rows = [];
      for (const pr of couples) {
        app.applyPosePreset(pr);
        app.pipeline.apply(0, { physics: false });
        const bad = E.badBones();
        const keyed = p.sims.every(s => s.keys.some(k => k.frame === 0));
        const cast = pr.sims.every(ps => p.sims.some(s => { const k = s.keys.find(k => k.frame === 0); return k && JSON.stringify(k.pose.rot.b__Pelvis__) === JSON.stringify(ps.pose.rot.b__Pelvis__) && (ps.gender === 'MALE' ? s.frame === 'ym' : s.frame === 'yf'); }));
        const dist = E.dist(E.wp(E.F(), 'b__Pelvis__'), E.wp(E.M(), 'b__Pelvis__'));
        rows.push({ id: pr.id, bad: bad.length, keyed, sims: p.sims.length, cast, pelvisDist_m: +dist.toFixed(3) });
      }
      const badRows = rows.filter(r => r.bad || !r.keyed || r.sims !== 2 || !r.cast);
      C(`all ${couples.length} couple poses: finite bones, both sims keyed at the frame, each part on the right body`, !badRows.length, badRows.length ? badRows : undefined);
      const far = rows.filter(r => r.pelvisDist_m > 1.0);
      C('couple poses put the partners together (hips < 1 m apart)', !far.length, far.length ? far : undefined);
      // solo poses on the selected (female) sim: it stays where it stands, the partner is untouched
      const F = E.F(), M = E.M();
      app.selectSim(F.id);
      const vF = E.view(F);
      const srows = [];
      for (const pr of solos) {
        app.pipeline.base({ sim: F, v: vF }, 0);
        const before = __m.posemath.spacePos(vF, vF.bone('b__Pelvis__')).toArray();
        const mKey = JSON.stringify(M.keys);
        app.applyPosePreset(pr);
        app.pipeline.base({ sim: F, v: vF }, 0);
        const after = __m.posemath.spacePos(vF, vF.bone('b__Pelvis__')).toArray();
        app.pipeline.apply(0, { physics: false });
        srows.push({ id: pr.id, bad: E.badBones().length, keyed: F.keys.some(k => k.frame === 0), moved_mm: +(Math.hypot(after[0] - before[0], after[2] - before[2]) * 1000).toFixed(2), partnerSame: JSON.stringify(M.keys) === mKey });
      }
      const sb = srows.filter(r => r.bad || !r.keyed || r.moved_mm > 1 || !r.partnerSame);
      C(`all ${solos.length} solo poses: finite, keyed, sim stays where it stood, partner untouched`, !sb.length, sb.length ? sb : undefined);
      return { checks: out, data: { rows, srows } };
    });
    info.couplePoses = d && d.rows;
    // the Pose panel: click a real tile, switch tabs, pose tools
    await page.click('#rail button[data-step=pose]');
    await sleep(300);
    await pe(async () => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, p = app.store.project;
      const n0 = E.toasts.length;
      const tiles = document.querySelectorAll('#panel-body .tiles .tile');
      C('Pose panel shows couple tiles', tiles.length > 0, tiles.length);
      tiles[1] && tiles[1].click();
      await E.flush();
      C('clicking a tile sets the pose (toast)', E.newToasts(n0).some(t => /pose set/.test(t)), E.newToasts(n0));
      E.btn('One sim', document.getElementById('panel-body')).click();
      await E.sleep(50);
      const solo = document.querySelectorAll('#panel-body .tiles .tile');
      C('"One sim" tab shows solo tiles', solo.length > 0 && app._poseMode === 'solo', solo.length);
      await E.waitFor(() => app.thumbs.cache.size >= app.posePresets.length, 30000);
      C('pose thumbnails rendered', app.thumbs.cache.size >= app.posePresets.length, [app.thumbs.cache.size, app.posePresets.length]);
      E.btn('Two sims', document.getElementById('panel-body')).click();
      // tools on a cowgirl pose
      E.resetCouple('cowgirl');
      const F = E.F(), M = E.M(), vF = E.view(F), vM = E.view(M);
      app.selectSim(F.id); app.showStep('pose');
      const panel = () => document.getElementById('panel-body');
      const base = s => { app.pipeline.base({ sim: s, v: E.view(s) }, 0); return E.view(s).getPose(); };
      const fwd = s => { const v = E.view(s); app.pipeline.base({ sim: s, v }, 0); return __m.motion.pelvisAxes(v).forward.toArray(); };
      const orig = base(F);
      E.btn('Mirror pose', panel()).click();
      const mir = base(F);
      E.btn('Mirror pose', panel()).click();
      const back = base(F);
      C('Mirror pose changes an asymmetric pose', E.poseDiff(orig, mir) > 2, +E.poseDiff(orig, mir).toFixed(2));
      C('Mirror pose twice gives the original pose back', E.poseDiff(orig, back) < 1, { maxDeg: +E.poseDiff(orig, back).toFixed(3) });
      const f0 = fwd(F), pel0 = E.wp(F, 'b__Pelvis__');
      E.btn('Turn left', panel()).click();
      const f1 = fwd(F);
      C('Turn left turns the sim 90 degrees', Math.abs(Math.abs(E.hang(f0, f1)) - 90) < 2, +E.hang(f0, f1).toFixed(2));
      E.btn('Turn right', panel()).click();
      const f2 = fwd(F);
      C('Turn right turns it back', Math.abs(E.hang(f0, f2)) < 2, +E.hang(f0, f2).toFixed(2));
      E.btn('Stand straight', panel()).click();
      const f3 = fwd(F), pel3 = (app.pipeline.base({ sim: F, v: vF }, 0), E.wp(F, 'b__Pelvis__'));
      C('Stand straight keeps where the sim is', E.dist(pel0, pel3) < 0.002, +E.dist(pel0, pel3).toFixed(4));
      C('Stand straight keeps which way it faces (horizontal)', Math.abs(E.hang(f0, f3)) < 3, +E.hang(f0, f3).toFixed(2));
      C('Stand straight: no NaN', E.badBones().length === 0);
      // copy the (now standing) female pose onto the male
      E.resetCouple('cowgirl');
      app.selectSim(F.id); app.showStep('pose');
      const fp = base(F);
      E.btn('Copy pose', panel()).click();
      C('Copy pose fills the clipboard', !!app.clipboard);
      app.selectSim(M.id); app.showStep('pose');
      const mHips = base(M).pos;
      const pb = E.btn('Paste pose', panel());
      C('Paste pose enabled after copying', pb && !pb.disabled);
      pb && pb.click();
      const mp = base(M);
      const same = Object.keys(fp.rot).filter(n => !/Penis|Tounge/.test(n) && n !== 'b__Pelvis__' && n !== 'b__Spine0__').every(n => E.qang(fp.rot[n], mp.rot[n]) < 0.01);
      C('Paste pose copies the limb rotations', same);
      C('Paste pose keeps where the sim stands', E.dist(mHips.b__Pelvis__, mp.pos.b__Pelvis__) < 1e-6);
      E.btn('Symmetry: off', panel()).click();
      C('Symmetry switches on', app.mirrorEdit === true);
      E.btn('Symmetry: on', panel()).click();
      C('Symmetry switches off', app.mirrorEdit === false);
      // Save to My poses
      E.btn('Save to My poses', panel()).click();
      await E.sleep(80);
      const dlg = E.modal('Save to My poses');
      C('Save to My poses opens a dialog', !!dlg);
      if (dlg) {
        dlg.querySelector('input.text').value = 'E2E pose';
        E.modalBtn('Save to My poses', 'Save').click();
        await E.sleep(100);
        C('the pose shows up under My poses', app.posePresets.some(x => x.mine && x.label === 'E2E pose') && app._poseMode === 'mine' && document.querySelectorAll('#panel-body .tiles .tile').length >= 1);
        localStorage.removeItem('fsa.myPoses');
        app.posePresets = app.posePresets.filter(x => !x.mine);
        app._poseMode = 'couple';
      }
      C('Pose tools: no NaN bones', E.badBones().length === 0, E.badBones());
      return { checks: out };
    });
    await shot('pose-tools');
  });

  // ================================================================ 4
  await step(4, 'motion layers', async () => {
    const d = await pe(async () => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, p = app.store.project, { MOTIONS } = __m.motion;
      const WATCH = ['b__Pelvis__', 'b__Spine2__', 'b__Head__', 'b__R_Hand__'];
      const who = { thrust: 'M', ride: 'F', grind: 'F', bounce: 'F', twerk: 'F', sway: 'F', headbob: 'F', stroke: 'F', breathe: 'M' };
      const mainOf = { stroke: 'b__R_Hand__', headbob: 'b__Head__', breathe: 'b__Head__' };
      const sample = (s, L) => {
        const tr = WATCH.map(() => []); let bad = null;
        for (let f = 0; f <= L; f++) {
          app.pipeline.apply(f, { physics: false });
          if (!bad && f % 3 === 0) { const bb = E.badBones(); if (bb.length) bad = { f, bones: bb.slice(0, 5) }; }
          WATCH.forEach((b, i) => tr[i].push(E.wp(s, b)));
        }
        return { tr, bad };
      };
      const rows = [];
      for (const type of Object.keys(MOTIONS)) {
        const { F, M } = E.resetCouple('cowgirl');
        const s = who[type] === 'M' ? M : F;
        app.selectSim(s.id);
        app.addLayer(s.id, type);
        const wasPlaying = app.playing;
        app.setPlaying(false);
        const l = s.layers[s.layers.length - 1];
        const L = p.length;
        const { tr, bad } = sample(s, L);
        const mi = WATCH.indexOf(mainOf[type] || 'b__Pelvis__');
        const amp = Math.max(...tr[mi].map(q => E.dist(q, tr[mi][0])));
        const steps = []; for (let f = 0; f < L; f++) steps.push(E.dist(tr[mi][f + 1], tr[mi][f]));
        const seam = E.dist(tr[mi][L], tr[mi][0]);
        const inner = Math.max(...steps.slice(0, L - 1)), wrap = steps[L - 1];
        // switch it off and on with the switch on its card
        app.showStep('motion');
        let sw = document.querySelector('#panel-body .layer .layer-head .switch input');
        let offOk = null, onOk = null, offMove = null;
        if (sw) {
          sw.click();
          offOk = l.on === false;
          app.pipeline.apply(0, { physics: false }); const a0 = E.wp(s, WATCH[mi]);
          app.pipeline.apply(Math.round(L / 8), { physics: false }); const a1 = E.wp(s, WATCH[mi]);
          offMove = E.dist(a0, a1);
          sw = document.querySelector('#panel-body .layer .layer-head .switch input');
          sw && sw.click();
          onOk = l.on === true;
        }
        rows.push({ type, sim: s.label, bone: WATCH[mi], startsPlaying: wasPlaying, amplitude_cm: +(amp * 100).toFixed(2), nan: bad, loopSeam_mm: +(seam * 1000).toFixed(3),
          wrapStep_mm: +(wrap * 1000).toFixed(2), maxInnerStep_mm: +(inner * 1000).toFixed(2), switchOff: offOk, offMove_mm: offMove === null ? null : +(offMove * 1000).toFixed(3), switchOn: onOk });
      }
      C('every motion: no NaN bones over the whole loop', rows.every(r => !r.nan), rows.filter(r => r.nan));
      C('every motion actually moves its body part', rows.every(r => r.amplitude_cm > (r.type === 'breathe' ? 0.1 : 0.3)), rows.map(r => `${r.type}:${r.amplitude_cm}cm`));
      C('every motion loops (frame length == frame 0)', rows.every(r => r.loopSeam_mm < 1), rows.map(r => `${r.type}:${r.loopSeam_mm}mm`));
      C('every motion wraps smoothly (last->first step like any other)', rows.every(r => r.wrapStep_mm <= r.maxInnerStep_mm * 1.5 + 0.5), rows.map(r => `${r.type}: wrap ${r.wrapStep_mm} / max ${r.maxInnerStep_mm}`));
      C('adding a motion starts playback', rows.every(r => r.startsPlaying));
      C('the card switch turns each motion off (no movement) and on again', rows.every(r => r.switchOff && r.switchOn && r.offMove_mm < 0.05), rows.map(r => `${r.type}: off=${r.switchOff} move=${r.offMove_mm} on=${r.switchOn}`));

      // Meet the partner
      {
        const { F, M } = E.resetCouple('cowgirl');
        app.addLayer(M.id, 'thrust'); app.setPlaying(false);
        app.addLayer(F.id, 'ride'); app.setPlaying(false);
        const lm = M.layers[0], lf = F.layers[0];
        C('a new motion takes the partner\'s rhythm', lf.params.strokes === lm.params.strokes, [lf.params.strokes, lm.params.strokes]);
        lf.params.strokes = 7; lf.phase = 0.3;
        app.selectSim(F.id); app._openLayer = lf.id; app.showStep('motion');
        const b = E.btn('Meet the partner', document.getElementById('panel-body'));
        C('"Meet the partner" button enabled', b && !b.disabled);
        b && b.click();
        C('"Meet the partner" copies the partner\'s strokes and timing', lf.params.strokes === lm.params.strokes && (lf.phase || 0) === (lm.phase || 0), { strokes: [lf.params.strokes, lm.params.strokes], phase: [lf.phase, lm.phase] });
        // sliders on the open card
        const sl = E.findSlider('Times per loop', document.getElementById('panel-body'));
        C('motion card shows its sliders', !!sl);
        if (sl) { E.setRange(sl, 5); C('the "Times per loop" slider changes the motion', lf.params.strokes === 5, lf.params.strokes); }
      }

      // Turn into keys: the keys must reproduce the motion
      const bakeRows = [];
      for (const type of ['thrust', 'ride', 'headbob', 'stroke', 'breathe']) {
        const { F, M } = E.resetCouple('cowgirl');
        const s = who[type] === 'M' ? M : F;
        app.addLayer(s.id, type); app.setPlaying(false);
        const l = s.layers[0];
        const L = p.length;
        const mi = WATCH.indexOf(mainOf[type] || 'b__Pelvis__');
        const before = sample(s, L).tr;
        app.selectSim(s.id); app._openLayer = l.id; app.showStep('motion');
        const b = E.btn('Turn into keys', document.getElementById('panel-body'));
        if (!b) { bakeRows.push({ type, error: 'no button' }); continue; }
        b.click();
        const after = sample(s, L).tr;
        const err = WATCH.map((bn, i) => Math.max(...before[i].map((q, f) => E.dist(q, after[i][f]))));
        const amp = Math.max(...before[mi].map(q => E.dist(q, before[mi][0])));
        let worstF = 0, worst = 0; before[mi].forEach((q, f) => { const e = E.dist(q, after[mi][f]); if (e > worst) { worst = e; worstF = f; } });
        bakeRows.push({ type, layerGone: !s.layers.some(x => x.id === l.id), keys: s.keys.length, mainBone: WATCH[mi], motion_cm: +(amp * 100).toFixed(2), maxErr_cm: +(err[mi] * 100).toFixed(2), atFrame: worstF, errAllBones_cm: err.map(e => +(e * 100).toFixed(2)) });
      }
      C('"Turn into keys" removes the motion and makes keys', bakeRows.every(r => r.layerGone && r.keys > 3), bakeRows.map(r => `${r.type}: gone=${r.layerGone} keys=${r.keys}`));
      C('"Turn into keys" reproduces the motion (max error < 5 mm)', bakeRows.every(r => r.maxErr_cm < 0.5), bakeRows);

      // performance: 2 sims, 2 motions, physics
      const perf = {};
      {
        const { F, M } = E.resetCouple('cowgirl');
        app.addLayer(M.id, 'thrust'); app.setPlaying(false);
        app.addLayer(F.id, 'ride'); app.setPlaying(false);
        const L = p.length;
        let t0 = performance.now(); app.pipeline.simulateIfNeeded(true); perf.simulateMs = +(performance.now() - t0).toFixed(1);
        t0 = performance.now(); for (let r = 0; r < 3; r++) for (let f = 0; f < L; f++) app.pipeline.apply(f, { physics: true });
        perf.applyWithPhysicsMsPerFrame = +((performance.now() - t0) / (3 * L)).toFixed(3);
        t0 = performance.now(); for (let r = 0; r < 3; r++) for (let f = 0; f < L; f++) app.pipeline.apply(f, { physics: false });
        perf.applyNoPhysicsMsPerFrame = +((performance.now() - t0) / (3 * L)).toFixed(3);
        t0 = performance.now(); app.bake(); perf.bakeMs = +(performance.now() - t0).toFixed(1);
        t0 = performance.now(); for (let k = 0; k < 20; k++) app.pipeline.signature(); perf.signatureMs = +((performance.now() - t0) / 20).toFixed(2);
        app.addLayer(M.id, 'breathe'); app.addLayer(F.id, 'headbob'); app.setPlaying(false);
        t0 = performance.now(); for (let f = 0; f < L; f++) app.pipeline.apply(f, { physics: true });
        perf.apply4LayersMsPerFrame = +((performance.now() - t0) / L).toFixed(3);
        app.setPlaying(true);
        let n = 0; const t1 = performance.now();
        await new Promise(res => { const tick = () => { n++; if (performance.now() - t1 < 2000) requestAnimationFrame(tick); else res(); }; requestAnimationFrame(tick); });
        perf.playingFps = +(n / ((performance.now() - t1) / 1000)).toFixed(1);
        app.setPlaying(false);
        C('pipeline.apply (2 sims, 2 motions, physics) is fast enough for 30 fps (< 20 ms/frame)', perf.applyWithPhysicsMsPerFrame < 20, perf);
      }
      return { checks: out, data: { rows, bakeRows, perf } };
    });
    if (d) { info.motions = d.rows; info.turnIntoKeys = d.bakeRows; info.perf = d.perf; }
    await shot('motion');
  });

  // ================================================================ 5
  await step(5, 'Body: erection, holes, physics', async () => {
    const d = await pe(async () => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, p = app.store.project;
      const { F, M } = E.resetCouple('cowgirl');
      app.addLayer(M.id, 'thrust'); app.setPlaying(false);
      app.addLayer(F.id, 'ride'); app.setPlaying(false);
      const vM = E.view(M), vF = E.view(F);
      app.selectSim(M.id); app.showStep('body');
      let t = E.findToggle('Erection', document.getElementById('panel-body'));
      C('Body step shows the Erection switch for the male', !!t);
      const hard = vM.meshes.filter(m => m.userData.role === 'penis_hard'), soft = vM.meshes.filter(m => m.userData.role === 'penis_soft');
      C('male body has hard and soft penis meshes', hard.length > 0 && soft.length > 0, { hard: hard.length, soft: soft.length });
      if (t) {
        t.click();
        app.pipeline.apply(0, { physics: false });
        C('Erection off: setting, view and meshes switch to soft', M.body.erect === false && vM.erect === false && hard.every(m => !m.visible) && soft.some(m => m.visible));
        E.findToggle('Erection', document.getElementById('panel-body')).click();
        app.pipeline.apply(0, { physics: false });
        C('Erection on again: hard penis shown', M.body.erect === true && vM.erect === true && hard.some(m => m.visible) && soft.every(m => !m.visible));
      }
      const iq = E.findToggle('Erection', document.getElementById('inspector'));
      C('the inspector has the same Erection switch', !!iq);
      app.selectSim(F.id); app.showStep('body');
      C('no Erection switch for the female body', !E.findToggle('Erection', document.getElementById('panel-body')));
      // automatic openings
      let maxOpen = 0, at = -1, by = null;
      for (let f = 0; f < p.length; f++) { app.pipeline.apply(f, { physics: false }); const o = (app.pipeline.lastOpen.get(F.id) || {}).vagina; if (o && o.open > maxOpen) { maxOpen = o.open; at = f; by = o.by; } }
      C('cowgirl + Ride + Thrust: the vagina opens by itself', maxOpen > 0.2, { maxOpen: +maxOpen.toFixed(3), atFrame: at, by });
      const VB = ['b__Up_Vagina__', 'b__Low_Vagina__', 'b__Penis_L_Testicle', 'b__Penis_R_Testicle'];
      const probe = () => { app.pipeline.apply(Math.max(0, at), { physics: false }); return VB.map(n => vF.bone(n).position.toArray()); };
      const rest = VB.map(n => vF.rest[vF.index(n)].pos.toArray());
      const opened = probe();
      const dmax = (a, b) => Math.max(...a.map((x, i) => E.dist(x, b[i])));
      C('opening moves the vagina bones', dmax(opened, rest) > 1e-3, +dmax(opened, rest).toFixed(5));
      E.findToggle('Automatic opening', document.getElementById('panel-body')).click();
      C('"Automatic opening" switch turns it off', F.body.open.on === false);
      const closed = probe();
      C('with it off the vagina bones stay as posed', dmax(closed, rest) < 1e-6, +dmax(closed, rest).toFixed(6));
      E.findToggle('Automatic opening', document.getElementById('panel-body')).click();
      C('"Automatic opening" switch turns it on again', F.body.open.on === true);
      for (const hole of ['Vagina', 'Anus', 'Mouth']) {
        const key = hole.toLowerCase();
        const t1 = E.findToggle(hole, document.getElementById('panel-body'));
        if (!t1) { C(`hole switch "${hole}" shown`, false); continue; }
        t1.click(); const off = F.body.open[key] === false;
        if (key === 'vagina') C('vagina switch off: no opening even when penetrated', dmax(probe(), rest) < 1e-6);
        E.findToggle(hole, document.getElementById('panel-body')).click(); const on = F.body.open[key] === true;
        C(`hole switch "${hole}" turns off and on`, off && on);
      }
      // physics
      const measure = s => {
        const ph = app.pipeline.phys.get(s.id); if (!ph) return null;
        const res = {};
        for (const [bone, { arr }] of Object.entries(ph)) {
          const n = arr.length / 3, at = k => [arr[k * 3], arr[k * 3 + 1], arr[k * 3 + 2]];
          let max = 0; const steps = [];
          for (let k = 0; k < n; k++) { max = Math.max(max, Math.hypot(...at(k))); if (k < n - 1) steps.push(E.dist(at(k + 1), at(k))); }
          const seam = E.dist(at(n - 1), at(0)); steps.sort((a, b) => a - b);
          res[bone] = { max_mm: +(max * 1000).toFixed(3), seam_mm: +(seam * 1000).toFixed(4), maxStep_mm: +(steps[steps.length - 1] * 1000).toFixed(4), medianStep_mm: +(steps[steps.length >> 1] * 1000).toFixed(4) };
        }
        return res;
      };
      app.pipeline.simulateIfNeeded(true);
      const pF = measure(F), pM = measure(M);
      C('physics simulated for both sims', pF && pM && Object.keys(pF).length > 0 && Object.keys(pM).length > 0, { F: pF && Object.keys(pF), M: pM && Object.keys(pM) });
      const moving = Object.entries(pF || {}).filter(([, r]) => r.max_mm > 0.5);
      C('physics produces real offsets on the female (> 0.5 mm)', moving.length >= 2, pF);
      const all = [...Object.entries(pF || {}).map(([b, r]) => ['F ' + b, r]), ...Object.entries(pM || {}).map(([b, r]) => ['M ' + b, r])];
      const badSeam = all.filter(([, r]) => r.seam_mm > Math.max(1.5 * r.maxStep_mm, 0.01));
      C('physics loops: frame length-1 flows into frame 0 (seam <= 1.5x the largest frame step)', !badSeam.length, badSeam.length ? badSeam : undefined);
      // sliders
      const sl = E.findSlider('Breasts', document.getElementById('panel-body'));
      C('physics sliders shown (Breasts, Butt)', !!sl && !!E.findSlider('Butt', document.getElementById('panel-body')));
      const b1 = pF && pF.b__CAS_L_Breast__ ? pF.b__CAS_L_Breast__.max_mm : 0;
      if (sl) {
        const nUndo = app.store.undo.length;
        sl.dispatchEvent(new PointerEvent('pointerdown'));
        E.setRange(sl, 2);
        C('the Breasts slider sets the amount', F.body.physics.breasts === 2, F.body.physics.breasts);
        C('the slider drag is undoable', app.store.undo.length === nUndo + 1);
        await E.waitFor(() => app.pipeline.physKey === app.pipeline.signature(), 3000);
        C('physics re-simulates after the slider', app.pipeline.physKey === app.pipeline.signature());
        const b2 = (measure(F).b__CAS_L_Breast__ || {}).max_mm || 0;
        C('more breast physics moves more (or hits the limit)', b2 > b1 * 1.15 || b2 >= 34.9, { at1: b1, at2: b2 });
      }
      E.findToggle('Automatic physics', document.getElementById('panel-body')).click();
      C('"Automatic physics" switch turns it off', F.body.physics.on === false);
      app.pipeline.simulateIfNeeded(true);
      C('no physics offsets for that sim when off', !app.pipeline.phys.get(F.id));
      E.findToggle('Automatic physics', document.getElementById('panel-body')).click();
      C('"Automatic physics" on again', F.body.physics.on === true);
      C('Body step: no NaN bones', E.badBones().length === 0);
      return { checks: out, data: { maxOpen, at, physF: pF, physM: pM } };
    });
    info.body = d;
    await shot('body');
  });

  // ================================================================ 6
  await step(6, 'Face: presets, sliders, blink', async () => {
    await pe(async () => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, p = app.store.project, FX = __m.face;
      const { F } = E.resetCouple('cowgirl');
      app.selectSim(F.id); app.showStep('face'); app.setFrame(0);
      const vF = E.view(F);
      const FB = __m.bones.FACE.concat(['b__Jaw__', 'b__Tounge__1', 'b__Tounge__2']).filter(n => vF.byName[n]);
      const snap = (f = 0) => { app.pipeline.apply(f, { physics: false }); return FB.map(n => vF.byName[n].position.toArray().concat(vF.byName[n].quaternion.toArray())); };
      const diff = (a, b) => Math.max(...a.map((x, i) => Math.max(...x.map((y, j) => Math.abs(y - b[i][j])))));
      app.setFace(F.id, {}, 'Neutral');
      const neutral = snap();
      const rows = [];
      const nUndo = app.store.undo.length;
      for (const [id, pr] of Object.entries(FX.FACE_PRESETS)) {
        app.setFace(F.id, { ...pr.face }, pr.label);
        const key = F.keys.find(k => k.frame === 0);
        rows.push({ id, keyed: JSON.stringify(key.face) === JSON.stringify(pr.face), change: +diff(snap(), neutral).toFixed(5) });
      }
      C(`all ${rows.length} face presets are keyed at the frame`, rows.every(r => r.keyed), rows.filter(r => !r.keyed));
      C('every face preset except Neutral moves face bones', rows.filter(r => r.id !== 'neutral').every(r => r.change > 1e-4), rows.map(r => `${r.id}:${r.change}`));
      C('face presets are undoable (one step each)', app.store.undo.length === nUndo + rows.length, [app.store.undo.length - nUndo, rows.length]);
      // the tiles in the panel
      const tile = [...document.querySelectorAll('#panel-body .face-tile')].find(b => b.textContent.includes('Smile'));
      C('face tiles shown', document.querySelectorAll('#panel-body .face-tile').length === rows.length);
      tile && tile.click();
      C('clicking the Smile tile keys the Smile face', JSON.stringify(F.keys.find(k => k.frame === 0).face) === JSON.stringify(FX.FACE_PRESETS.smile.face));
      // slider
      const jaw0 = (app.pipeline.apply(0, { physics: false }), vF.bone('b__Jaw__').quaternion.toArray());
      const sl = E.findSlider('Mouth open', document.getElementById('panel-body'));
      C('face sliders shown', !!sl && document.querySelectorAll('#panel-body .slider').length >= Object.keys(FX.FACE_SLIDERS).length);
      if (sl) {
        E.setRange(sl, 0.8);
        const key = F.keys.find(k => k.frame === 0);
        C('the Mouth open slider adds to the face key', key.face.open === 0.8 && key.face.smile === FX.FACE_PRESETS.smile.face.smile, key.face);
        const jaw1 = (app.pipeline.apply(0, { physics: false }), vF.bone('b__Jaw__').quaternion.toArray());
        C('the jaw opens (> 10 degrees)', E.qang(jaw0, jaw1) > 10, +E.qang(jaw0, jaw1).toFixed(2));
      }
      // a second face key: it changes smoothly between them
      app.setFrame(45); app.setFace(F.id, { ...FX.FACE_PRESETS.ecstasy.face }, 'O face');
      const mid = __m.animation.evaluateFace(F.keys, 22, p.length, p.loop);
      C('the face changes smoothly between two face keys', mid && mid.pout > 0 && mid.pout < FX.FACE_PRESETS.ecstasy.face.pout, mid);
      app.setFrame(0);
      // blinking
      const blinkFrames = []; for (let f = 0; f < p.length; f++) { const b = FX.blinkAt(F, f, p.length, p.fps); if (b && b.eyes > 0.6) blinkFrames.push(f); }
      C('natural blinking happens in the loop', blinkFrames.length > 0, blinkFrames);
      if (blinkFrames.length) {
        const fb = blinkFrames[Math.floor(blinkFrames.length / 2)];
        let fn = (fb + 20) % p.length; while (FX.blinkAt(F, fn, p.length, p.fps)) fn = (fn + 3) % p.length;
        // same face on both frames: remove the second face key first
        F.keys = F.keys.filter(k => k.frame !== 45);
        const lid = f => { app.pipeline.apply(f, { physics: false }); return vF.bone('b__L_UpLid__').quaternion.toArray(); };
        C('a blink closes the eyelids', E.qang(lid(fb), lid(fn)) > 5, { blinkFrame: fb, openFrame: fn, deg: +E.qang(lid(fb), lid(fn)).toFixed(2) });
        E.findToggle('Blink now and then', document.getElementById('panel-body')).click();
        C('"Blink now and then" switch turns blinking off', F.body.blink === false && !FX.blinkAt(F, fb, p.length, p.fps));
        C('no blink when off', E.qang(lid(fb), lid(fn)) < 0.01);
        E.findToggle('Blink now and then', document.getElementById('panel-body')).click();
        C('blinking on again', F.body.blink === true);
      }
      C('Face step: no NaN bones', E.badBones().length === 0);
      return { checks: out };
    });
    await shot('face');
  });

  // ================================================================ 7
  await step(7, 'Sounds: automatic sounds and voices', async () => {
    const d = await pe(async () => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, p = app.store.project;
      await E.waitFor(() => app.sounds && app.sounds.length, 15000);
      C('sound catalogue loaded', app.sounds && app.sounds.length > 0, app.sounds && app.sounds.length);
      const { F, M } = E.resetCouple('cowgirl');
      app.addLayer(M.id, 'thrust'); app.setPlaying(false);
      app.addLayer(F.id, 'ride'); app.setPlaying(false);
      app.showStep('sounds');
      const all = () => p.sims.flatMap(s => (s.sounds || []).map(x => ({ ...x, sim: s.label })));
      E.btn('Place sounds for me', document.getElementById('panel-body')).click();
      const placed = all().filter(x => x.auto);
      C('"Place sounds for me" places sounds on cowgirl + Ride + Thrust', placed.length > 0, placed.length);
      C('placed sounds sit on whole frames inside the loop', placed.every(x => Number.isInteger(x.frame) && x.frame >= 0 && x.frame < p.length));
      const known = new Set(app.sounds.map(s => s.name));
      C('placed sounds exist in the catalogue', placed.every(x => known.has(x.name)), placed.filter(x => !known.has(x.name)).map(x => x.name));
      const kinds = {}; placed.forEach(x => { kinds[x.kind] = (kinds[x.kind] || 0) + 1; });
      C('panel lists every placed sound', document.querySelectorAll('#panel-body .sound-row').length === all().length, [document.querySelectorAll('#panel-body .sound-row').length, all().length]);
      // selecting a body part pauses that sim's motion in the view - automatic sounds must not depend on it
      app.interact.selectBone(M.id, 'b__Spine1__'); app.store.selected = { sim: M.id, bone: 'b__Spine1__' };
      await E.sleep(250);
      const editing = app.pipeline.editing;
      app.autoSounds();
      const placedSel = all().filter(x => x.auto).length;
      C('automatic sounds are the same with a body part selected', placedSel === placed.length, { noSelection: placed.length, withMalePartSelected: placedSel, pipelineEditing: editing === M.id ? 'male (its Thrust is skipped)' : editing });
      app.vp.gizmo.detach(); app.interact.active = null; app.store.selected.bone = null;
      await E.sleep(150);
      app.autoSounds();
      // voices through the panel
      app.selectSim(F.id); app.showStep('sounds');
      const panel = () => document.getElementById('panel-body');
      const selects = () => [...panel().querySelectorAll('.grid-2 select')];
      const pool = k => (app.sounds || []).filter(x => x.kind === 'voice').map(x => x.name);
      let n0 = E.toasts.length;
      E.btn('Add random voice', panel()).click();
      await E.flush();
      const def = F.sounds.filter(x => x.kind === 'voice').length;
      C('"Add random voice" with the default choice ("Soft moans") adds voices', def > 0, { voices: def, toast: E.newToasts(n0), voiceSoundsInCatalogue: pool() });
      selects()[0].value = 'moan';
      n0 = E.toasts.length;
      E.btn('Add random voice', panel()).click();
      const voices = F.sounds.filter(x => x.kind === 'voice').sort((a, b) => a.frame - b.frame);
      C('"Moans" adds voice sounds', voices.length > 0, voices.map(v => `${v.frame}:${v.name}`));
      // "never overlapping" (the panel says so)
      const len = n => FX_len(n);
      function FX_len(n) { return __m.face.voiceLength(n, p.fps); }
      const overlaps = [];
      for (let i = 0; i < voices.length; i++) { const a = voices[i], b = voices[(i + 1) % voices.length]; if (voices.length < 2) break; let gap = b.frame - a.frame; if (gap <= 0) gap += p.length; if (gap < len(a.name)) overlaps.push(`${a.frame}+${len(a.name)}f overlaps ${b.frame}`); }
      // try the "Often" setting too
      selects()[0].value = 'moan'; selects()[1].value = '1.5';
      E.btn('Add random voice', panel()).click();
      const often = F.sounds.filter(x => x.kind === 'voice').sort((a, b) => a.frame - b.frame);
      for (let i = 0; i < often.length && often.length > 1; i++) { const a = often[i], b = often[(i + 1) % often.length]; let gap = b.frame - a.frame; if (gap <= 0) gap += p.length; if (gap < len(a.name)) overlaps.push(`often: ${a.frame}+${len(a.name)}f overlaps ${b.frame}`); }
      C('random voices never overlap (the panel promises it)', !overlaps.length, overlaps);
      // mouth moves while a voice plays
      const v0 = F.sounds.filter(x => x.kind === 'voice')[0];
      if (v0) {
        const midF = (v0.frame + Math.round(len(v0.name) / 2)) % p.length;
        const jaw = () => { app.pipeline.apply(midF, { physics: false }); return E.view(F).bone('b__Jaw__').quaternion.toArray(); };
        const withTalk = jaw();
        F.body.talk.mouth = false;
        const noTalk = jaw();
        F.body.talk.mouth = true;
        C('the mouth moves by itself while a voice plays', E.qang(withTalk, noTalk) > 2, +E.qang(withTalk, noTalk).toFixed(2));
      }
      // pick a sound by hand
      app.setFrame(12);
      E.btn('Pick a sound here', panel()).click();
      await E.sleep(80);
      const dlg = E.modal('Add a sound at frame 12');
      C('"Pick a sound here" opens the sound list', !!dlg);
      if (dlg) {
        const item = dlg.querySelector('.proj-item');
        const nm = item && item.querySelector('span').textContent;
        item && item.click();
        C('picking a sound puts it at the current frame', F.sounds.some(x => x.frame === 12 && !x.auto), nm);
        E.closeModals();
      }
      const anyPool = (app.sounds || []).filter(x => x.kind === 'voice').map(x => x.name);
      return { checks: out, data: { placed: placed.length, kinds, voices: F.sounds.filter(x => x.kind === 'voice').length, voicePool: anyPool } };
    });
    info.sounds = d;
    await shot('sounds');
  });

  // ================================================================ 8
  await step(8, 'Keys: key, key all, delete, eases, tween, undo/redo, timeline, length', async () => {
    await pe(async () => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, p = app.store.project, A = __m.animation;
      const { F, M } = E.resetCouple('cowgirl');
      app.selectSim(F.id); app.showStep('motion');
      app.setFrame(10); app.keyPose(F.id);
      C('keyPose keys the selected sim at frame 10', F.keys.some(k => k.frame === 10));
      app.setFrame(30); document.getElementById('btn-key').click();
      C('"Key pose" button keys at frame 30', F.keys.some(k => k.frame === 30));
      app.setFrame(20); document.getElementById('btn-key-all').click();
      C('"Key all" keys every sim at frame 20', F.keys.some(k => k.frame === 20) && M.keys.some(k => k.frame === 20));
      app.setFrame(10); document.getElementById('btn-del-key').click();
      C('"Delete key" removes the key at frame 10', !F.keys.some(k => k.frame === 10), F.keys.map(k => k.frame));
      app.selectSim(M.id); app.setFrame(20); app.deleteKey(M.id); app.setFrame(0);
      const n0 = E.toasts.length; app.deleteKey(M.id); await E.flush();
      C('the only key of a sim cannot be deleted', M.keys.length === 1 && E.newToasts(n0).some(t => /only key/.test(t)), E.newToasts(n0));
      app.selectSim(F.id);
      // key 20 gets a clearly different pose
      const k20 = F.keys.find(k => k.frame === 20);
      const q = __m.state && E.Q().fromArray(k20.pose.rot.b__Spine1__).multiply(E.Q().setFromAxisAngle(E.V(0, 0, 1), 0.8));
      k20.pose.rot.b__Spine1__ = q.toArray();
      const k0rot = () => F.keys.find(k => k.frame === 0).pose.rot.b__Spine1__;
      const total = E.qang(k0rot(), k20.pose.rot.b__Spine1__);
      const res = {};
      for (const e of Object.keys(A.EASE_INFO)) {
        app.setEase(F.id, 0, e);
        const vals = [5, 10, 15].map(f => A.evaluate(F.keys, f, p.length, p.loop).rot.b__Spine1__);
        res[e] = { stored: F.keys.find(k => k.frame === 0).ease, finite: vals.every(v => v.every(Number.isFinite)), deg: vals.map(v => +E.qang(k0rot(), v).toFixed(3)) };
      }
      C('setEase stores every ease', Object.entries(res).every(([e, r]) => r.stored === e), res);
      C('every ease gives finite in-betweens', Object.values(res).every(r => r.finite));
      C('"Hold" stays on the key', res.hold.deg.every(a => a < 1e-3), res.hold.deg);
      C('"Linear" is halfway in the middle', Math.abs(res.linear.deg[1] - total / 2) < 0.5, { mid: res.linear.deg[1], half: +(total / 2).toFixed(3) });
      C('the eases give different in-betweens', new Set(Object.values(res).map(r => r.deg.join())).size === Object.keys(res).length, Object.fromEntries(Object.entries(res).map(([k, r]) => [k, r.deg.join('/')])));
      app.setFrame(0);
      C('ease box shows the key\'s ease', document.getElementById('ease-select').value === F.keys.find(k => k.frame === 0).ease);
      E.setValue(document.getElementById('ease-select'), 'impact');
      C('ease box changes the key\'s ease', F.keys.find(k => k.frame === 0).ease === 'impact');
      const insp = document.querySelector('#inspector select');
      C('inspector shows the key\'s ease', insp && insp.value === 'impact', insp && insp.value);
      // tween
      app.setFrame(15); app.store.checkpoint(); app.tween(F.id, 0.5, true);
      const k15 = F.keys.find(k => k.frame === 15);
      const expect = A.blendPoses(F.keys.find(k => k.frame === 0).pose, k20.pose, 0.5);
      C('tween makes an in-between key (50% blend)', k15 && E.poseDiff(k15.pose, expect) < 1e-4, k15 ? +E.poseDiff(k15.pose, expect).toFixed(6) : 'no key');
      app.setFrame(25);
      const sl = E.findSlider('In-between', document.getElementById('inspector'));
      C('inspector shows the in-between slider between keys', !!sl);
      if (sl) { E.setRange(sl, 0.25); C('the in-between slider makes a key there', F.keys.some(k => k.frame === 25)); }
      // undo / redo
      const frames = () => E.F().keys.map(k => k.frame).join();
      app.setFrame(40);
      const before = frames(); app.keyPose(E.F().id); const after = frames();
      document.getElementById('btn-undo').click(); const u = frames();
      document.getElementById('btn-redo').click(); const r = frames();
      C('Undo removes the new key, Redo brings it back', u === before && r === after && before !== after, { before, after, undo: u, redo: r });
      C('undo/redo buttons enable correctly', !document.getElementById('btn-undo').disabled && document.getElementById('btn-redo').disabled);
      // Auto key off: an edit stays pending, K keeps it, moving the playhead drops it with a warning
      const F2 = E.F();
      document.getElementById('btn-autokey').click();
      C('Auto key button switches it off', app.autoKey === false);
      app.selectSim(F2.id); app.setFrame(60);
      const nk = F2.keys.length;
      app.beginEdit(F2.id); E.view(F2).bone('b__Spine1__').rotateX(0.2); app.poseEdited(F2.id);
      C('Auto key off: an edit is pending, not keyed', F2.keys.length === nk && app.pipeline.overrides.has(F2.id), { keys: F2.keys.map(k => k.frame) });
      document.getElementById('btn-key').click();
      C('Key pose keeps the pending edit as a key', F2.keys.some(k => k.frame === 60) && !app.pipeline.overrides.has(F2.id));
      app.beginEdit(F2.id); E.view(F2).bone('b__Spine1__').rotateX(-0.2); app.poseEdited(F2.id);
      const n1 = E.toasts.length;
      app.setFrame(61); await E.flush();
      C('moving the playhead drops a pending edit and says so', !app.pipeline.overrides.has(F2.id) && E.newToasts(n1).some(t => /dropped/.test(t)), E.newToasts(n1));
      document.getElementById('btn-autokey').click();
      C('Auto key back on', app.autoKey === true);
      return { checks: out };
    });
    // timeline with the real mouse
    const g = await page.evaluate(() => {
      const F = __e2e.F(), row = app.store.project.sims.indexOf(F), r = document.getElementById('tl-canvas').getBoundingClientRect();
      app.timeline.fit();
      return { left: r.left, top: r.top, h: r.height, w: r.width, row, x30: r.left + app.timeline.xAt(30), x50: r.left + app.timeline.xAt(50), x60: r.left + app.timeline.xAt(60), x70: r.left + app.timeline.xAt(70), y: r.top + 28 + row * 48 + 15, ppf: app.timeline.pxPerFrame };
    });
    info.timeline = g;
    check('timeline canvas is tall enough for both lanes', g.h >= 28 + 2 * 48, g.h);
    await page.mouse.move(g.x30, g.y); await page.mouse.down();
    for (let k = 1; k <= 8; k++) await page.mouse.move(g.x30 + (g.x50 - g.x30) * k / 8, g.y);
    await page.mouse.up();
    await sleep(150);
    const drag = await page.evaluate(() => __e2e.F().keys.map(k => k.frame));
    check('dragging a key on the timeline moves it (30 -> 50)', drag.includes(50) && !drag.includes(30), drag);
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    await page.keyboard.down('Control'); await page.keyboard.press('z'); await page.keyboard.up('Control');
    await sleep(100);
    const und = await page.evaluate(() => __e2e.F().keys.map(k => k.frame));
    check('Ctrl+Z undoes the key drag', und.includes(30) && !und.includes(50), und);
    await page.keyboard.down('Control'); await page.keyboard.press('y'); await page.keyboard.up('Control');
    await sleep(100);
    const red = await page.evaluate(() => __e2e.F().keys.map(k => k.frame));
    check('Ctrl+Y redoes it', red.includes(50) && !red.includes(30), red);
    await page.mouse.click(g.x60, g.top + 12);
    await sleep(100);
    check('clicking the ruler scrubs to that frame', await page.evaluate(() => Math.round(app.store.frame)) === 60, await page.evaluate(() => app.store.frame));
    await page.mouse.click(g.x70, g.y + 8, { count: 2 });
    await sleep(150);
    check('double-clicking a lane keys there', (await page.evaluate(() => __e2e.F().keys.map(k => k.frame))).includes(70), await page.evaluate(() => __e2e.F().keys.map(k => k.frame)));
    await page.mouse.click(g.x50, g.y, { button: 'right' });
    await sleep(150);
    const menu = await page.evaluate(() => { const m = document.querySelector('.ctx-menu'); return m ? [...m.querySelectorAll('button')].map(b => b.textContent) : null; });
    check('right-clicking a key opens its menu', !!menu && menu.some(t => t.includes('Bounce')), menu);
    if (menu) {
      await page.evaluate(() => [...document.querySelectorAll('.ctx-menu button')].find(b => b.textContent.includes('Bounce')).click());
      check('the key menu sets the ease', await page.evaluate(() => __e2e.F().keys.find(k => k.frame === 50).ease) === 'bounce');
    }
    // keyboard
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    await page.keyboard.press('Home'); await sleep(50);
    const fHome = await page.evaluate(() => app.store.frame);
    await page.keyboard.press('ArrowRight'); await sleep(50);
    const fRight = await page.evaluate(() => app.store.frame);
    await page.keyboard.press('.'); await sleep(50);
    const fNext = await page.evaluate(() => app.store.frame);
    check('Home / ArrowRight / "." (next key) move the playhead', fHome === 0 && fRight === 1 && fNext === 15, { fHome, fRight, fNext });
    // loop length
    await pe(() => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, p = app.store.project, A = __m.animation;
      const inp = document.getElementById('tl-seconds-in');
      E.setValue(inp, '1.5');
      C('changing the length to 1.5 s gives 45 frames', p.length === 45 && document.getElementById('tl-frames-note').textContent === '45 frames', p.length);
      C('the playhead stays inside the new length', app.store.frame <= p.length - 1, app.store.frame);
      const F = E.F();
      const past = F.keys.filter(k => k.frame >= p.length).map(k => k.frame);
      const rot = f => A.evaluate(F.keys, f, p.length, p.loop).rot.b__Spine1__;
      const steps = []; for (let f = 0; f < p.length - 1; f++) steps.push(E.qang(rot(f), rot(f + 1)));
      const seam = E.qang(rot(p.length - 1), rot(0));
      C('after shortening, no keys are left past the end of the loop', !past.length, { keysPastEnd: past, allKeys: F.keys.map(k => k.frame) });
      C('after shortening, the loop still joins up (seam step <= 1.5x largest step)', seam <= Math.max(...steps) * 1.5 + 0.05, { seamDeg: +seam.toFixed(2), maxStepDeg: +Math.max(...steps).toFixed(2) });
      E.setValue(inp, '3');
      C('length back to 3 s = 90 frames', p.length === 90);
      C('no NaN bones after key edits', E.badBones().length === 0);
      return { checks: out };
    });
    await shot('keys-timeline');
  });

  // ================================================================ 9
  await step(9, 'Details panel', async () => {
    await page.click('#rail button[data-step=details]');
    await sleep(250);
    await pe(async () => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, p = app.store.project, panel = () => document.getElementById('panel-body');
      const texts = () => [...panel().querySelectorAll('input.text')];
      E.setValue(texts()[0], 'E2E Test A renamed');
      C('name field renames the animation (and the title chip)', p.name === 'E2E Test A renamed' && document.getElementById('pc-name').textContent === 'E2E Test A renamed', p.name);
      E.setValue(texts()[0], 'E2E Test A');
      E.setValue(texts()[1], 'E2E');
      C('creator field', p.author === 'E2E' && document.getElementById('pc-by').textContent === 'by E2E');
      const chip = (cls, text) => [...panel().querySelectorAll('button.chipbtn' + cls)].find(b => b.textContent.trim() === text);
      chip('.kind', 'Oral').click();
      C('Kind chip sets the kind', p.category === 'ORALJOB' && document.getElementById('pc-kind').textContent === 'Oral', p.category);
      chip('.kind', 'Vaginal').click();
      C('Kind back to Vaginal', p.category === 'VAGINAL');
      const filter = texts()[2];
      E.setValue(filter, 'cow', 'input');
      const shown = [...panel().querySelectorAll('.tag-groups button.chipbtn')].map(b => b.textContent);
      C('tag search filters the chips', shown.length >= 1 && shown.every(t => /cow/i.test(t)), shown);
      [...panel().querySelectorAll('.tag-groups button.chipbtn')].find(b => b.textContent === 'Cowgirl').click();
      C('clicking a tag adds it', p.tags.includes('COWGIRL') && p.category === 'VAGINAL', p.tags);
      E.setValue(texts()[2], '', 'input');
      [...panel().querySelectorAll('.tag-groups button.chipbtn')].find(b => b.textContent === 'Blowjob').click();
      C('two tags; the kind stays Vaginal (cowgirl wins over blowjob)', p.tags.includes('BLOWJOB') && p.category === 'VAGINAL', { tags: p.tags, kind: p.category });
      [...panel().querySelectorAll('.chips.picked button')].find(b => b.textContent.includes('Blowjob')).click();
      C('clicking a picked tag removes it', !p.tags.includes('BLOWJOB') && p.tags.includes('COWGIRL'), p.tags);
      chip('.place', 'Double Bed').click();
      C('place chip adds a place', p.locations.includes('DOUBLE_BED') && p.locations.includes('FLOOR'), p.locations);
      chip('.place', 'Double Bed').click();
      C('place chip removes it again', !p.locations.includes('DOUBLE_BED'), p.locations);
      const sel = panel().querySelector('.field.row select');
      E.setValue(sel, 'TOP');
      C('undressing choice per sim', p.sims[0].naked === 'TOP', p.sims[0].naked);
      const bk = app.bake();
      C('the undressing choice reaches the export', bk.actors[0].naked === 'TOP', bk.actors[0].naked);
      E.setValue(panel().querySelector('.field.row select'), 'AUTO');
      const loops = panel().querySelector('input[type=number]');
      E.setValue(loops, '5');
      C('"How many times it repeats" sets loops', p.loops === 5, p.loops);
      E.setValue(panel().querySelector('input[type=number]'), '10');
      // a pose applied after picking places keeps the places?
      p.locations = ['FLOOR', 'DOUBLE_BED'];
      app.applyPosePreset(app.posePresets.find(x => x.id === 'cowgirl'));
      C('applying a ready pose keeps the places picked in Details', p.locations.includes('DOUBLE_BED'), p.locations);
      p.locations = ['FLOOR']; app.refreshAll();
      return { checks: out };
    });
    await shot('details');
  });

  // ================================================================ 10
  let exportedA = null;
  await step(10, 'Send to game + package check', async () => {
    const prep = await pe(async () => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, p = app.store.project;
      const { F, M } = E.resetCouple('cowgirl');
      // an unnamed animation cannot be sent
      const keepName = p.name; p.name = 'Untitled animation';
      app.exportDialog();
      const dlg = E.modal('Send to game');
      { const fb = dlg && [...dlg.querySelectorAll('footer button')].pop();
        C('Send to game refuses an unnamed animation (name box inside, button disabled)', dlg && !!dlg.querySelector('.inline-name input') && fb && fb.disabled, dlg && { text: dlg.textContent.slice(0, 300), btn: fb && fb.textContent, disabled: fb && fb.disabled }); }
      E.modalBtn('Send to game', 'Cancel').click();
      p.name = keepName;
      app.addLayer(M.id, 'thrust'); app.setPlaying(false);
      app.addLayer(F.id, 'ride'); app.setPlaying(false);
      app.autoSounds();
      app.randomVoices(F.id, 'moan', 3);
      app.setFrame(0); app.setFace(F.id, { ...__m.face.FACE_PRESETS.moan.face }, 'Moaning');
      p.name = 'E2E Test A'; p.author = 'E2E'; p.tags = ['COWGIRL']; p.category = 'VAGINAL'; p.locations = ['FLOOR']; p.loops = 10;
      app.refreshAll();
      C('test animation A has sounds and a voice', p.sims.some(s => s.sounds.length) && F.sounds.some(x => x.kind === 'voice'), p.sims.map(s => s.sounds.length));
      return { checks: out, data: { sounds: p.sims.map(s => s.sounds.map(x => `${x.frame}:${x.kind}:${x.name}`)) } };
    });
    info.exportSounds = prep;
    // the real button and dialog
    await page.click('#btn-export');
    await page.waitForFunction(() => __e2e.modal('Send to game'), { timeout: 8000 });
    await pe(() => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const m = __e2e.modal('Send to game');
      C('Send to game dialog: no red items', !m.querySelector('.warn-box'), [...m.querySelectorAll('.warn-box')].map(x => x.textContent));
      const b = __e2e.modalBtn('Send to game', 'Send to game');
      C('Send to game button enabled', b && !b.disabled);
      return { checks: out };
    });
    await shot('send-dialog');
    const tSend = Date.now();
    await page.evaluate(() => __e2e.modalBtn('Send to game', 'Send to game').click());
    const ok = await page.waitForFunction(() => __e2e.modal("It's in your Mods folder"), { timeout: 180000 }).then(() => true).catch(() => false);
    info.sendToGameUiMs = Date.now() - tSend;
    check('Send to game (dialog) finishes with "It\'s in your Mods folder"', ok);
    const uiPath = await page.evaluate(() => { const m = __e2e.modal("It's in your Mods folder"); return m && m.querySelector('.path') && m.querySelector('.path').textContent; });
    await shot('sent');
    await page.evaluate(() => { const b = __e2e.modalBtn("It's in your Mods folder", 'Done'); b && b.click(); });
    check('the dialog also saved the project', await page.evaluate(() => !app.store.dirty));
    // the direct call, and the package
    const r = await page.evaluate(async () => { const b = app.bake(); const res = await __m.api.export(b); return { b, res }; });
    exportedA = r;
    fs.writeFileSync(path.join(OUT, 'bake_A.json'), JSON.stringify(r.b));
    check('api.export writes into Mods\\FitStudio\\MyAnimations', r.res && r.res.path && r.res.path.startsWith(MYANIM), r.res && r.res.path);
    check('dialog and API wrote the same package', uiPath === r.res.path, [uiPath, r.res.path]);
    check('export result names both clips', r.res.clips && r.res.clips.length === 2, r.res.clips);
    info.exportA = r.res;
    const vi = verifyPkg('single', r.res.path, { bakes: [r.b] }, 'single');
    info.exportAPackage = vi;
    // move our package(s) out of the Mods folder
    const now = listDir(MYANIM);
    const ours = now.filter(f => !before.myAnim.includes(f) || /^FitStudio_E2E_/.test(f));
    const moved = ours.map(f => moveInto(path.join(MYANIM, f), path.join(OUT, 'exported')));
    if (!before.soundKit && fs.existsSync(SOUNDKIT)) moved.push(moveInto(SOUNDKIT, path.join(OUT, 'exported')));
    info.movedExports = moved;
    check('test packages moved out of the Mods folder', listDir(MYANIM).sort().join() === before.myAnim.slice().sort().join() && fs.existsSync(SOUNDKIT) === before.soundKit, moved);
  });

  // ================================================================ 11
  let uidA = null, uidB = null, uidC = null, progId = null;
  await step(11, 'save A and B, progression, export a mod', async () => {
    const s = await pe(async () => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, api = __m.api;
      const p = app.store.project;
      p.name = 'E2E Test A'; p.author = 'E2E';
      await app.save();
      const A = JSON.parse(JSON.stringify(app.store.project));
      let list = await api.projects();
      C('saving A lists it with its uid', list.some(m => m.file === 'E2E Test A' && m.uid === A.uid));
      // B: same place and sims, another pose
      const B = JSON.parse(JSON.stringify(A)); B.uid = __m.state.uid('a'); B.name = 'E2E Test B'; delete B.thumb;
      app.store.load(B);
      const { F, M } = E.resetCouple('doggy');
      app.addLayer(M.id, 'thrust'); app.setPlaying(false);
      app.autoSounds();
      app.store.project.locations = ['FLOOR'];
      await app.save();
      list = await api.projects();
      C('saving B lists it (A still there)', list.some(m => m.file === 'E2E Test B' && m.uid === B.uid) && list.some(m => m.file === 'E2E Test A'), list.map(m => m.file));
      return { checks: out, data: { A: A.uid, B: B.uid } };
    });
    uidA = s.A; uidB = s.B;
    // progression through the Share panel
    await page.evaluate(async () => { await app.loadProject('E2E Test A'); app.showStep('share'); });
    await page.waitForFunction(() => !document.getElementById('panel-body').textContent.includes('Loading...'), { timeout: 20000 });
    await page.evaluate(() => __e2e.btn('New', document.getElementById('panel-body')).click());
    await page.waitForFunction(() => document.querySelector('#panel-body .chain .chain-step'), { timeout: 20000 });
    const pr = await pe(async (uidA, uidB) => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, api = __m.api;
      let progs = await api.progressions();
      const g = progs.find(x => x.steps[0] === uidA);
      C('"New" in Share starts a progression with the open animation', !!g, progs);
      const sel = [...document.querySelectorAll('#panel-body select')].find(x => x.options[0] && x.options[0].textContent.includes('Add an animation'));
      C('the progression card offers B', sel && [...sel.options].some(o => o.value === uidB));
      if (sel) { sel.value = uidB; sel.dispatchEvent(new Event('change')); }
      const ok = await E.waitFor(async () => (await api.progressions()).some(x => x.id === g.id && x.steps.join() === [uidA, uidB].join()), 8000);
      C('adding B through the card saves A -> B', !!ok);
      await E.waitFor(() => document.querySelectorAll('#panel-body .chain .chain-step').length === 2, 5000);
      const link = document.querySelector('#panel-body .chain .chain-link');
      C('the chain says A can move on to B', link && !link.classList.contains('bad'), link && link.textContent);
      return { checks: out, data: g && g.id };
    }, uidA, uidB);
    progId = pr;
    await shot('progression');
    // a third saved animation: does the Share panel see it?
    const stale = await pe(async () => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const cur = JSON.parse(JSON.stringify(app.store.project));
      const Cp = { ...cur, uid: __m.state.uid('a'), name: 'E2E Test C' }; delete Cp.thumb;
      app.store.load(Cp);
      await app.save();
      app.showStep('share');
      await __e2e.waitFor(() => !document.getElementById('panel-body').textContent.includes('Loading...'), 8000);
      await __e2e.sleep(300);
      const sel = [...document.querySelectorAll('#panel-body select')].find(x => x.options[0] && x.options[0].textContent.includes('Add an animation'));
      C('a newly saved animation shows up in the Share panel\'s "+ Add an animation" list', sel && [...sel.options].some(o => o.value === Cp.uid), sel && [...sel.options].map(o => o.textContent));
      app.shareData = null;
      await app.loadProject('E2E Test A');
      return { checks: out, data: Cp.uid };
    });
    uidC = stale;
    // Export a mod through the dialog
    await page.click('#btn-share');
    await page.waitForFunction(() => __e2e.modal('Export a mod'), { timeout: 20000 });
    await pe(progId => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const m = __e2e.modal('Export a mod');
      const prog = m.querySelector('.pick.prog input');
      C('Export a mod lists the progression', !!prog);
      if (prog && !prog.checked) prog.click();
      const inputs = m.querySelectorAll('input.text');
      inputs[0].value = 'E2E Test Pack UI'; inputs[1].value = 'E2E';
      const picked = [...m.querySelectorAll('.pick:not(.prog)')].filter(x => x.classList.contains('on')).map(x => x.querySelector('b').textContent);
      C('ticking the progression picks both steps', picked.some(t => t.startsWith('E2E Test A')) && picked.some(t => t.startsWith('E2E Test B')), picked);
      C('summary counts one complete progression', /1 complete progression/.test(m.querySelector('.summary').textContent), m.querySelector('.summary').textContent);
      return { checks: out };
    }, progId);
    await shot('export-mod-dialog');
    const tUi = Date.now();
    await page.evaluate(() => __e2e.modalBtn('Export a mod', 'Export mod').click());
    const okUi = await page.waitForFunction(() => __e2e.modal('Your mod is ready'), { timeout: 300000 }).then(() => true).catch(() => false);
    info.exportModUiMs = Date.now() - tUi;
    check('Export a mod (dialog) finishes with "Your mod is ready"', okUi);
    const uiPkg = await page.evaluate(() => { const m = __e2e.modal('Your mod is ready'); return m && m.querySelector('.path') ? m.querySelector('.path').textContent : null; });
    await shot('mod-ready');
    await page.evaluate(() => { const b = __e2e.modalBtn('Your mod is ready', 'Done'); b && b.click(); });
    // direct bundle
    const r = await page.evaluate(async (uidA, uidB) => {
      const bakes = [await __m.share.bakeByUid(app, uidA), await __m.share.bakeByUid(app, uidB)];
      const res = await __m.api.bundle({ name: 'E2E Test Pack', author: 'E2E', animations: bakes, include_sounds: true, install: false });
      const cat = Object.fromEntries((app.sounds || []).map(s => [s.name, s]));
      const names = [...new Set(bakes.flatMap(b => b.actors.flatMap(a => a.sounds.map(s => s.name))))];
      const packable = names.filter(n => cat[n] && ['mods', 'parked'].includes(cat[n].source) && !/TURBODRIVER_WickedWhims/.test(cat[n].package || ''));
      return { bakes, res, packable, progs: await __m.api.progressions() };
    }, uidA, uidB);
    fs.writeFileSync(path.join(OUT, 'bundle_bakes.json'), JSON.stringify(r.bakes));
    info.bundle = r.res;
    const prog = r.progs.find(g => g.id === progId);
    const expect = {
      bakes: r.bakes, packable: r.packable, readme: path.join(r.res.folder, 'README.txt'), zip: r.res.zip, progression: prog && prog.name,
      next: { 'E2E Test A': ['E2E Test B'], 'E2E Test B': [] }, random: { 'E2E Test A': true, 'E2E Test B': false },
    };
    check('bundle result: 2 animations, the progression, sounds packed', r.res.animations === 2 && r.res.progressions.length === 1 && (r.packable.length === 0 || r.res.sounds_packed > 0),
      { animations: r.res.animations, progressions: r.res.progressions, sounds_packed: r.res.sounds_packed, packable: r.packable, missing: r.res.missing_sounds });
    info.bundlePackage = verifyPkg('bundle', r.res.package, expect, 'bundle');
    if (uiPkg && fs.existsSync(uiPkg)) {
      const ex2 = { ...expect, readme: path.join(path.dirname(uiPkg), 'README.txt'), zip: path.join(EXPORTS, path.basename(path.dirname(uiPkg)) + '.zip') };
      info.bundleUiPackage = verifyPkg('bundle', uiPkg, ex2, 'bundle-dialog');
    } else check('dialog bundle package exists', false, uiPkg);
    // move the bundles out of Documents
    const moved = [];
    for (const f of listDir(EXPORTS)) if (/^E2E Test Pack/.test(f)) moved.push(moveInto(path.join(EXPORTS, f), path.join(OUT, 'bundle')));
    if (!before.exports && fs.existsSync(EXPORTS) && !listDir(EXPORTS).length) fs.rmdirSync(EXPORTS);
    info.movedBundles = moved;
    check('bundles moved out of Documents\\Wicked Animator Exports', !listDir(EXPORTS).some(f => /^E2E/.test(f)), moved);
    // installing must not have happened
    check('install:false left MyAnimations alone', listDir(MYANIM).sort().join() === before.myAnim.slice().sort().join(), listDir(MYANIM));
  });

  // two different animations with the same name: does the second save keep the first?
  await step(16, 'two animations with the same name', async () => {
    const col = await page.evaluate(async () => {
      const api = __m.api;
      const base = JSON.parse(JSON.stringify(app.store.project));
      const X = { ...base, uid: __m.state.uid('a'), name: 'E2E Test Collide', loops: 7 }; delete X.thumb;
      const Y = { ...base, uid: __m.state.uid('a'), name: 'E2E Test Collide', loops: 3 }; delete Y.thumb;
      await api.saveProject(X);
      await api.saveProject(Y);
      const list = await api.projects();
      return { X: X.uid, Y: Y.uid, listed: list.filter(m => m.name === 'E2E Test Collide').map(m => m.uid) };
    });
    const backup = path.join(DOCS, 'Electronic Arts', 'The Sims 4', 'saves', 'FitStudio', 'animator_replaced');
    const inBackup = listDir(backup).filter(f => f.startsWith('E2E Test Collide')).some(f => { try { return JSON.parse(fs.readFileSync(path.join(backup, f), 'utf8')).uid === col.X; } catch { return false; } });
    check('saving another animation under an existing name keeps the first one (listed or backed up)', col.listed.includes(col.X) || inBackup, { ...col, firstInBackupFolder: inBackup });
  });

  // cleanup of the server-side test data (always, even if step 11 failed half way)
  STEP = '11 cleanup';
  try {
    const res = await page.evaluate(async (progId, uids) => {
      const api = __m.api;
      const progs = await api.progressions();
      const keep = progs.filter(g => g.id !== progId && !g.steps.some(s => uids.includes(s)));
      if (keep.length !== progs.length) await api.saveProgressions(keep);
      const list = await api.projects();
      const removed = [];
      for (const m of list) if (/^E2E Test ([ABC]|Collide)$/.test(m.name) || uids.includes(m.uid)) { await api.removeProject(m.file); removed.push(m.file); }
      return { removed, progsAfter: await api.progressions(), projectsAfter: (await api.projects()).map(m => m.file) };
    }, progId, [uidA, uidB, uidC].filter(Boolean));
    check('test progression removed', JSON.stringify(res.progsAfter) === JSON.stringify(initialServer.progressions), res.progsAfter);
    check('test projects removed (moved to the backup folder)', res.projectsAfter.sort().join() === initialServer.projects.slice().sort().join(), res);
  } catch (e) { check('cleanup ran', false, String(e.stack || e)); }

  // ================================================================ 12
  await step(12, 'Library: search, preview, Use this pose, Import as keys', async () => {
    await page.evaluate(() => { app.newScene(false, false, 'couple'); app.setFrame(0); app.showStep('library'); });
    await sleep(300);
    const input = await page.$('#panel-body .search input');
    await input.click({ clickCount: 3 });
    await input.type('Cowgirl');
    await page.waitForFunction(() => !app.library.el.count.textContent.includes('Searching') && app.library.items.length && app.library.items.every(it => /cowgirl/i.test(it.name + it.author)), { timeout: 20000 }).catch(() => {});
    const lib = await page.evaluate(() => ({ n: app.library.items.length, count: app.library.el.count.textContent, allMatch: app.library.items.every(it => /cowgirl/i.test(it.name + ' ' + it.author)), two: app.library.items.every(it => it.actors.length === 2) }));
    check('library search finds matching animations', lib.n > 0 && lib.allMatch, lib);
    check('library "2 sims" filter', lib.two);
    const idx = await page.evaluate(() => app.library.items.findIndex(it => it.actors.includes('MALE') && it.actors.includes('FEMALE') && it.locations.includes('FLOOR')));
    const pick = idx >= 0 ? idx : 0;
    await page.evaluate(i => document.querySelectorAll('#panel-body .lib-item')[i].click(), pick);
    await page.waitForFunction(() => app.library.preview && app.library.preview.players, { timeout: 30000 });
    const P = await page.evaluate(async () => {
      const E = __e2e, pv = app.library.preview;
      document.getElementById('btn-preview-play').click();
      const scrub = document.getElementById('preview-scrub');
      const BONES = ['b__R_Hand__', 'b__L_Hand__', 'b__L_Foot__', 'b__Head__', 'b__Pelvis__'];
      const at = async f => { scrub.value = f; scrub.dispatchEvent(new Event('input')); await E.sleep(150); return pv.views.map(v => { v.group.updateMatrixWorld(true); return BONES.map(b => v.worldPos(b).toArray()); }); };
      const f1 = Math.min(30, pv.length - 1), f2 = Math.min(33, pv.length - 1);
      const p1 = await at(f2); const p0 = await at(f1);
      return { id: pv.anim.id, name: pv.anim.name, genders: pv.anim.actors.map(a => a.gender), length: pv.length, playing: pv.playing, f1, f2, p0, p1, BONES, hidden: [...app.simViews.values()].every(v => !v.group.visible), frameShown: pv.frame };
    });
    info.libraryAnim = { id: P.id, name: P.name, genders: P.genders, length: P.length };
    check('preview pauses with the play button', P.playing === false);
    check('preview hides the project\'s sims', P.hidden);
    check('scrubbing the preview sets its frame', P.frameShown === P.f1, P.frameShown);
    await shot('library-preview');
    await page.click('#btn-preview-pose');
    await sleep(300);
    await pe(P => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, p = app.store.project;
      C('"Use this pose" closes the preview', !app.library.preview && document.getElementById('preview-bar').classList.contains('hidden'));
      const errs = [];
      P.genders.forEach((g, k) => {
        const s = g === 'MALE' ? E.M() : E.F();
        const v = E.view(s);
        app.pipeline.base({ sim: s, v }, Math.round(app.store.frame));
        v.group.updateMatrixWorld(true);
        P.BONES.forEach((b, i) => errs.push({ actor: k, gender: g, bone: b, cm: +(E.dist(v.worldPos(b).toArray(), P.p0[k][i]) * 100).toFixed(2) }));
      });
      const worst = errs.reduce((a, b) => (b.cm > a.cm ? b : a));
      C('"Use this pose": the sims land exactly where the preview showed them (< 1 cm)', worst.cm < 1, worst.cm < 1 ? { worstCm: worst.cm } : errs.filter(e => e.cm >= 1));
      C('"Use this pose" keys both sims at the frame', p.sims.every(s => s.keys.some(k => k.frame === Math.round(app.store.frame))));
      C('"Use this pose" takes the animation\'s place', p.locations.length > 0, p.locations);
      return { checks: out };
    }, P);
    await shot('library-used-pose');
    // Import as keys
    await page.evaluate(i => document.querySelectorAll('#panel-body .lib-item')[i].click(), pick);
    await page.waitForFunction(() => app.library.preview && app.library.preview.players, { timeout: 30000 });
    await page.click('#btn-preview-import');
    await page.waitForFunction(() => __e2e.modal('Import as keys'), { timeout: 5000 });
    await shot('import-dialog');
    await page.evaluate(() => __e2e.modalBtn('Import as keys', 'Import').click());
    await sleep(600);
    await pe(P => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const E = __e2e, p = app.store.project;
      C('import replaces the sims with the animation\'s sims', p.sims.length === P.genders.length && p.sims.every((s, k) => s.gender === P.genders[k]), p.sims.map(s => [s.frame, s.gender]));
      C('import sets the name and length', p.name.endsWith('(my version)') && p.length === Math.min(P.length, 300), { name: p.name, length: p.length, clip: P.length });
      C('import makes keys every 6 frames (+ last frame)', p.sims.every(s => s.keys.length >= Math.floor((p.length - 1) / 6) + 1 && s.keys.every(k => k.frame % 6 === 0 || k.frame === p.length - 1)), p.sims.map(s => s.keys.length));
      const errAt = (f, ref) => {
        const errs = [];
        p.sims.forEach((s, k) => {
          const v = E.view(s);
          app.pipeline.base({ sim: s, v }, f);
          v.group.updateMatrixWorld(true);
          P.BONES.forEach((b, i) => errs.push(+(E.dist(v.worldPos(b).toArray(), ref[k][i]) * 100).toFixed(2)));
        });
        return Math.max(...errs);
      };
      const e1 = errAt(P.f1, P.p0), e2 = errAt(P.f2, P.p1);
      C(`imported keys sit where the preview showed them at key frame ${P.f1} (< 1 cm)`, e1 < 1, { worstCm: e1 });
      C(`and between keys (frame ${P.f2}) within 2 cm`, e2 < 2, { worstCm: e2 });
      app.pipeline.apply(0, { physics: false });
      C('imported animation: no NaN bones', E.badBones().length === 0);
      return { checks: out };
    }, P);
    await shot('imported');
  });

  // ================================================================ 13
  await step(13, 'Tray sims (adults only)', async () => {
    const t = await pe(async () => {
      const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
      const api = __m.api;
      const hh = await api.tray();
      const sims = hh.flatMap(h => h.sims.map(s => ({ ...s, household: h.name, hid: h.id })));
      const ADULT = ['youngadult', 'adult', 'elder'];
      const nonAdult = sims.filter(s => !ADULT.includes(s.age) || (s.species || 'human') !== 'human');
      C('api.tray() lists only adult human sims', !nonAdult.length, { total: sims.length, nonAdultListed: nonAdult.map(s => `${s.age}/${s.species || 'human'} allowed=${s.allowed}`) });
      C('no non-adult sim is marked allowed', !sims.some(s => s.allowed && !ADULT.includes(s.age)));
      C('non-human sims are not allowed', !sims.some(s => s.allowed && (s.species || 'human') !== 'human'));
      // the server refuses a non-adult sim outright
      const teen = sims.find(s => !ADULT.includes(s.age));
      if (teen) {
        let refused = false, msg = '';
        try { await api.traySim(teen.hid, teen.index); } catch (e) { refused = true; msg = e.message; }
        C('the server refuses to load a non-adult Tray sim', refused, msg);
      }
      return { checks: out, data: { total: sims.length, ages: sims.reduce((a, s) => { a[s.age] = (a[s.age] || 0) + 1; return a; }, {}) } };
    });
    info.tray = t;
    await page.evaluate(() => { app.newScene(false, false, 'couple'); app.showStep('scene'); });
    await sleep(200);
    await page.evaluate(() => __e2e.btn('Use a sim from my Tray', document.getElementById('panel-body')).click());
    await page.waitForFunction(() => { const m = __e2e.modal('Use a sim from my Tray'); return m && m.querySelectorAll('.tile').length; }, { timeout: 30000 });
    await sleep(1500);
    const tiles = await page.evaluate(() => [...__e2e.modal('Use a sim from my Tray').querySelectorAll('.tile small')].map(x => x.textContent));
    check('the Tray dialog shows only adults', tiles.length > 0 && tiles.every(x => /young adult|adult|elder/.test(x) && !/teen|child|toddler|infant/.test(x)), { tiles: tiles.length, sample: tiles.slice(0, 4) });
    await shot('tray-dialog');
    const nErr = logs.length;
    await page.evaluate(() => [...__e2e.modal('Use a sim from my Tray').querySelectorAll('.tile')].find(t => /young adult/.test(t.textContent)).click());
    const ok = await page.waitForFunction(() => app.store.project.sims.length === 3 && app.simViews.size === 3, { timeout: 180000 }).then(() => true).catch(() => false);
    check('adding a young adult Tray sim works', ok);
    if (ok) {
      await sleep(800);
      await pe(() => {
        const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
        const E = __e2e, p = app.store.project, s = p.sims[2], v = E.view(s);
        C('the Tray sim has its own body shape', s.tray && v.frameKey === 'tray:' + s.id, { tray: s.tray, frameKey: v.frameKey });
        const finite = v.meshes.every(m => m.geometry.attributes.position.array.every(Number.isFinite));
        C('the Tray sim\'s mesh is finite and visible', v.meshes.length > 0 && finite && v.group.visible && v.meshes.some(m => m.visible), { meshes: v.meshes.length, finite });
        v.group.updateMatrixWorld(true);
        const head = v.worldPos('b__Head__').y, foot = v.worldPos('b__L_Foot__').y;
        C('the Tray sim stands at a human height', head - foot > 1.2 && head - foot < 2.2, +(head - foot).toFixed(3));
        C('Tray sim: no NaN bones', E.badBones().length === 0);
        app.selectSim(s.id);
        app.vp.frame(v.worldPos('b__Spine1__'), 1.1);
        return { checks: out };
      });
      await sleep(900);
      await shot('tray-sim');
      const trayErr = logs.slice(nErr).filter(l => l.type === 'error' || l.type === 'pageerror');
      check('no console errors while loading the Tray sim', !trayErr.length, trayErr.map(l => l.text));
      await page.evaluate(() => { const s = app.store.project.sims[2]; app.removeSim(s.id); });
      check('the Tray sim can be removed again', await page.evaluate(() => app.store.project.sims.length === 2 && app.simViews.size === 2));
    }
  });

  // ================================================================ 14
  await step(14, 'Camera: WASD / QE / Shift / right-drag / wheel, left drag never moves it', async () => {
    await page.evaluate(() => { __e2e.closeModals(); app.newScene(false, false, 'couple'); app.showStep('pose'); app.setTool('rotate'); app.vp.controls.lookFrom(__e2e.V(0.5, 1.3, 3.6), __e2e.V(0, 0.9, 0)); });
    await sleep(300);
    const r = await page.evaluate(() => { const b = app.vp.canvas.getBoundingClientRect(); return { l: b.left, t: b.top, w: b.width, h: b.height }; });
    const cam = () => page.evaluate(() => ({ p: app.vp.camera.position.toArray(), q: app.vp.camera.quaternion.toArray(), f: new app.vp.camera.position.constructor(0, 0, -1).applyQuaternion(app.vp.camera.quaternion).toArray(), r: new app.vp.camera.position.constructor(1, 0, 0).applyQuaternion(app.vp.camera.quaternion).toArray() }));
    const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
    // an empty spot of the floor to start from
    await page.mouse.click(r.l + r.w * 0.12, r.t + r.h * 0.55);
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    const hold = async (key, ms = 400, shift = false) => {
      await sleep(250);   // let the fly speed settle to 0
      const a = await cam();
      if (shift) await page.keyboard.down('Shift');
      await page.keyboard.down(key); await sleep(ms); await page.keyboard.up(key);
      if (shift) await page.keyboard.up('Shift');
      await sleep(350);
      const b = await cam();
      return { d: sub(b.p, a.p), f: a.f, r: a.r };
    };
    const w = await hold('w'); const s = await hold('s'); const a = await hold('a'); const d = await hold('d'); const e = await hold('e'); const q = await hold('q');
    const ws = await hold('w', 400, true);
    const len = v => Math.hypot(...v);
    info.camera = { w: len(w.d), s: len(s.d), a: len(a.d), d: len(d.d), e: e.d[1], q: q.d[1], shiftW: len(ws.d) };
    check('W flies forward', dot(w.d, w.f) > 0.2, +dot(w.d, w.f).toFixed(3));
    check('S flies back', dot(s.d, s.f) < -0.2, +dot(s.d, s.f).toFixed(3));
    check('A flies left', dot(a.d, a.r) < -0.2, +dot(a.d, a.r).toFixed(3));
    check('D flies right', dot(d.d, d.r) > 0.2, +dot(d.d, d.r).toFixed(3));
    check('E flies up', e.d[1] > 0.2, +e.d[1].toFixed(3));
    check('Q flies down', q.d[1] < -0.2, +q.d[1].toFixed(3));
    check('Shift slows the flying down', len(ws.d) < len(w.d) * 0.5 && len(ws.d) > 0.01, { plain: +len(w.d).toFixed(3), shift: +len(ws.d).toFixed(3) });
    check('WASD did not trigger app shortcuts (still Pose tool, frame 0)', await page.evaluate(() => app.interact.tool === 'rotate' && app.store.frame === 0));
    // wheel
    await page.mouse.move(r.l + r.w / 2, r.t + r.h / 2);
    let c0 = await cam();
    await page.mouse.wheel({ deltaY: -200 });
    await sleep(150);
    let c1 = await cam();
    check('wheel moves the camera in', dot(sub(c1.p, c0.p), c0.f) > 0.05, +dot(sub(c1.p, c0.p), c0.f).toFixed(3));
    // right drag looks around
    c0 = await cam();
    await page.mouse.move(r.l + r.w * 0.5, r.t + r.h * 0.5);
    await page.mouse.down({ button: 'right' });
    for (let k = 1; k <= 8; k++) await page.mouse.move(r.l + r.w * 0.5 + k * 20, r.t + r.h * 0.5 + k * 4);
    await page.mouse.up({ button: 'right' });
    await sleep(150);
    c1 = await cam();
    const turned = 2 * Math.acos(Math.min(1, Math.abs(dot(c0.q, c1.q) + c0.q[3] * c1.q[3]))) * 180 / Math.PI;
    check('right-drag turns the view', turned > 5 && len(sub(c1.p, c0.p)) < 1e-6, { turnedDeg: +turned.toFixed(2), moved: len(sub(c1.p, c0.p)) });
    // left drag: on empty floor and on a body - the camera never moves
    for (const [label, sx, sy] of [['empty floor', r.l + r.w * 0.1, r.t + r.h * 0.8], ['a body', ...(await page.evaluate(() => __e2e.screen(__e2e.F(), 'b__Spine1__')))]]) {
      c0 = await cam();
      await page.mouse.move(sx, sy); await page.mouse.down();
      for (let k = 1; k <= 8; k++) await page.mouse.move(sx + k * 25, sy - k * 6);
      await page.mouse.up();
      await sleep(150);
      c1 = await cam();
      check(`left drag on ${label} never moves the camera`, len(sub(c1.p, c0.p)) < 1e-9 && Math.abs(Math.abs(dot(c0.q, c1.q) + c0.q[3] * c1.q[3]) - 1) < 1e-9, { moved: len(sub(c1.p, c0.p)) });
    }
    check('camera: no page errors', !logs.some(l => l.step === STEP && l.type === 'pageerror'));
  });

  // ================================================================ 15
  await step(15, 'hover glow, click select, tools, pins, hip turn', async () => {
    await page.evaluate(() => { __e2e.closeModals(); app.newScene(false, false, 'couple'); app.showStep('pose'); app.setTool('rotate'); app.vp.controls.lookFrom(__e2e.V(0.3, 1.25, 3.3), __e2e.V(0, 0.95, 0)); });
    await sleep(500);
    const chest = await page.evaluate(() => __e2e.screen(__e2e.F(), 'b__Spine2__'));
    await page.mouse.move(chest[0] - 3, chest[1]); await sleep(60);
    await page.mouse.move(chest[0], chest[1]); await sleep(150);
    const hov = await page.evaluate(() => { const v = __e2e.view(__e2e.F()); let mx = 0; for (const m of v.meshes) for (const g of m.geometry.attributes.glow.array) if (g > mx) mx = g; return { hovered: v.hovered, name: v.hovered >= 0 ? v.bones[v.hovered].name : null, glow: mx, hud: document.getElementById('vp-hud').textContent, cursor: app.vp.canvas.style.cursor }; });
    check('hovering a body part makes it glow', hov.hovered >= 0 && hov.glow > 0.3, hov);
    check('the HUD names the hovered part', /Chest|back|Shoulder|Breast/i.test(hov.hud), hov.hud);
    await shot('hover-glow');
    await page.mouse.move(10 + (await page.evaluate(() => app.vp.canvas.getBoundingClientRect().left)), chest[1] + 250); await sleep(150);
    check('moving off the body clears the glow', await page.evaluate(() => __e2e.view(__e2e.F()).hovered === -1));
    // click to select
    const head = await page.evaluate(() => __e2e.screen(__e2e.F(), 'b__Head__'));
    await page.mouse.click(head[0], head[1] + 6);
    await sleep(200);
    const sel = await page.evaluate(() => { const s = app.store.selected, v = __e2e.view(__e2e.F()); return { sim: s.sim === __e2e.F().id, bone: s.bone, gizmoOn: !!app.vp.gizmo.object && app.vp.gizmo.object === v.bone(s.bone), insp: document.getElementById('inspector').textContent.includes('Turn this part') }; });
    check('clicking the head selects it with the rotate rings', sel.sim && /Head|Neck|Jaw/.test(sel.bone || '') && sel.gizmoOn && sel.insp, sel);
    await shot('selected-head');
    // are the tool buttons really clickable (not covered by another toolbar)?
    const cover = await page.evaluate(() => {
      const out = {};
      for (const b of document.querySelectorAll('#tool-seg button, #view-seg button')) {
        const r = b.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
        const top = document.elementFromPoint(x, y);
        out[(b.dataset.tool || b.dataset.view)] = { ok: !!top && b.contains(top), topIs: top ? (top.closest('button') ? (top.closest('button').dataset.tool || top.closest('button').dataset.view || top.closest('button').id || top.closest('button').textContent.trim()) : top.tagName) : null, rect: [Math.round(r.left), Math.round(r.right)] };
      }
      const a = document.querySelector('.vp-toolbar.top-center').getBoundingClientRect(), b = document.querySelector('.vp-toolbar.top-right').getBoundingClientRect();
      out.toolbars = { center: [Math.round(a.left), Math.round(a.right)], right: [Math.round(b.left), Math.round(b.right)], overlapPx: Math.max(0, Math.round(a.right - b.left)) };
      return out;
    });
    info.toolbarCover = cover;
    check('every tool / view button can be clicked (not covered by the other toolbar) at 1600x900', Object.entries(cover).filter(([k]) => k !== 'toolbars').every(([, v]) => v.ok), cover);
    // Drag tool: handles, pin with Alt+click
    await page.click('#tool-seg button[data-tool=ik]');
    await sleep(200);
    const ik = await page.evaluate(() => ({ tool: app.interact.tool, handles: app.interact.handleList.length }));
    check('Drag tool shows 5 handles per sim', ik.tool === 'ik' && ik.handles === 10, ik);
    const handle = await page.evaluate(() => { const x = app.interact.handleList.find(h => h.simId === __e2e.F().id && h.limb === 'L foot'); const p = x.mesh.position.clone().project(app.vp.camera); const r = app.vp.canvas.getBoundingClientRect(); return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; });
    await page.keyboard.down('Alt'); await page.mouse.click(handle[0], handle[1]); await page.keyboard.up('Alt');
    await sleep(200);
    const pinned = await page.evaluate(() => !!__e2e.F().pins['L foot']);
    check('Alt+click on a foot handle pins it', pinned);
    await page.keyboard.down('Alt'); await page.mouse.click(handle[0], handle[1]); await page.keyboard.up('Alt');
    await sleep(200);
    check('Alt+click again unpins it', await page.evaluate(() => !__e2e.F().pins['L foot']));
    await page.mouse.click(handle[0], handle[1]);
    await sleep(150);
    check('clicking a handle grabs that limb', await page.evaluate(() => app.interact.active && app.interact.active.kind === 'limb' && app.interact.active.limb === 'L foot'));
    await shot('drag-tool');
    // drag the right hand up 10 cm (the gizmo's events, as TransformControls sends them)
    const handMove = await page.evaluate(() => {
      const E = __e2e, F = E.F(), it = app.interact, gz = app.vp.gizmo;
      const x = it.handleList.find(h => h.simId === F.id && h.limb === 'R hand');
      it.selectHandle(x);
      const before = E.wp(F, 'b__R_Hand__'), sh = E.wp(F, 'b__R_UpperArm__');
      gz.dispatchEvent({ type: 'mouseDown' });
      it.proxy.position.y += 0.1; gz.dispatchEvent({ type: 'objectChange' });
      gz.dispatchEvent({ type: 'mouseUp' });
      const after = E.wp(F, 'b__R_Hand__');
      return { dy: after[1] - before[1], d: E.dist(after, before), shoulderMoved: E.dist(sh, E.wp(F, 'b__R_UpperArm__')), keyed: F.keys.some(k => k.frame === Math.round(app.store.frame)) };
    });
    check('dragging a hand handle moves the hand (10 cm up), the shoulder stays', Math.abs(handMove.dy - 0.1) < 0.02 && handMove.shoulderMoved < 0.002 && handMove.keyed, handMove);
    // Place tool (clicked through the DOM: at 1600x900 the button can be covered, see above)
    await page.evaluate(() => document.querySelector('#tool-seg button[data-tool=move]').click());
    await sleep(100);
    const mchest = await page.evaluate(() => __e2e.screen(__e2e.M(), 'b__Spine2__'));
    await page.mouse.click(mchest[0], mchest[1]);
    await sleep(200);
    const place = await page.evaluate(() => ({ active: app.interact.active, proxy: app.vp.gizmo.object === app.interact.proxy, mode: app.vp.gizmo.mode, M: __e2e.M().id }));
    check('Place tool: clicking a sim grabs the whole sim', place.active && place.active.kind === 'place' && place.active.simId === place.M && place.proxy && place.mode === 'translate', place);
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    await page.keyboard.press('t'); await sleep(80);
    const modeT = await page.evaluate(() => app.vp.gizmo.mode);
    await page.keyboard.press('t'); await sleep(80);
    check('T switches Place between move and turn', modeT === 'rotate' && await page.evaluate(() => app.vp.gizmo.mode) === 'translate', modeT);
    // pins keep a hand in place while the whole body moves
    const pin = await page.evaluate(() => {
      const E = __e2e, F = E.F(), it = app.interact, gz = app.vp.gizmo;
      app.selectSim(F.id); app.setTool('rotate');
      const btn = [...document.querySelectorAll('#inspector .pin-grid .pin')].find(b => b.textContent.includes('Right hand'));
      btn.click();
      const pinnedNow = !!F.pins['R hand'];
      const hand0 = E.wp(F, 'b__R_Hand__'), pel0 = E.wp(F, 'b__Pelvis__');
      app.setTool('move'); it.selectPlace(F.id);
      gz.dispatchEvent({ type: 'mouseDown' });
      it.proxy.position.x += 0.12; gz.dispatchEvent({ type: 'objectChange' });
      gz.dispatchEvent({ type: 'mouseUp' });
      app.pipeline.apply(Math.round(app.store.frame), { physics: false });
      const hand1 = E.wp(F, 'b__R_Hand__'), pel1 = E.wp(F, 'b__Pelvis__');
      const b2 = [...document.querySelectorAll('#inspector .pin-grid .pin')].find(b => b.textContent.includes('Right hand'));
      const moveKeepsPin = { pelvisMoved: E.dist(pel0, pel1), handMoved: E.dist(hand0, hand1) };
      // the pin travels with the sim when the whole sim is placed
      b2 && b2.click();
      return { pinnedNow, unpinned: !F.pins['R hand'], ...moveKeepsPin };
    });
    check('the inspector pin button pins and unpins a hand', pin.pinnedNow && pin.unpinned, pin);
    check('placing the whole sim carries its pins along (hand moves with the body)', Math.abs(pin.pelvisMoved - 0.12) < 0.01 && Math.abs(pin.handMoved - 0.12) < 0.01, pin);
    // pinned hand stays put while the hips move (Drag tool hips handle)
    const pin2 = await page.evaluate(() => {
      const E = __e2e, F = E.F(), it = app.interact, gz = app.vp.gizmo;
      app.setTool('ik');
      it.togglePin(F.id, 'R hand');
      const hand0 = E.wp(F, 'b__R_Hand__'), pel0 = E.wp(F, 'b__Pelvis__');
      const x = it.handleList.find(h => h.simId === F.id && h.kind === 'hips');
      it.selectHandle(x);
      gz.dispatchEvent({ type: 'mouseDown' });
      it.proxy.position.y -= 0.08; gz.dispatchEvent({ type: 'objectChange' });
      gz.dispatchEvent({ type: 'mouseUp' });
      app.pipeline.apply(Math.round(app.store.frame), { physics: false });
      const r = { pelvisMoved: E.dist(pel0, E.wp(F, 'b__Pelvis__')), handMoved: E.dist(hand0, E.wp(F, 'b__R_Hand__')) };
      it.togglePin(F.id, 'R hand');
      return r;
    });
    check('a pinned hand stays put when the hips move', pin2.pelvisMoved > 0.05 && pin2.handMoved < 0.01, pin2);
    // keyboard tool switching
    await page.evaluate(() => { app.vp.gizmo.detach(); app.interact.active = null; document.activeElement && document.activeElement.blur(); });
    const toolSeq = [];
    for (const k of ['g', 'm', 'r']) { await page.keyboard.press(k); await sleep(60); toolSeq.push(await page.evaluate(() => app.interact.tool)); }
    check('G / M / R switch tools', toolSeq.join() === 'ik,move,rotate', toolSeq);
    // hip turn: rotating b__Pelvis__ turns the whole body
    const hip = await page.evaluate(() => {
      const E = __e2e, F = E.F(), v = E.view(F), gz = app.vp.gizmo, it = app.interact, pm = __m.posemath;
      app.setTool('rotate');
      app.store.selected = { sim: F.id, bone: 'b__Pelvis__' };
      it.selectBone(F.id, 'b__Pelvis__');
      app.beginEdit(F.id);
      const B = ['b__Pelvis__', 'b__Spine0__', 'b__Spine2__', 'b__Head__', 'b__L_Hand__', 'b__L_Foot__', 'b__L_Clavicle__', 'b__R_Clavicle__', 'b__L_Thigh__', 'b__R_Thigh__'];
      const snap = () => { v.group.updateMatrixWorld(true); return Object.fromEntries(B.map(b => [b, v.worldPos(b).toArray()])); };
      const a = snap();
      gz.dispatchEvent({ type: 'mouseDown' });
      pm.rotateInSpace(v, v.bone('b__Pelvis__'), E.Q().setFromAxisAngle(E.V(0, 1, 0), Math.PI / 6));
      gz.dispatchEvent({ type: 'objectChange' });
      gz.dispatchEvent({ type: 'mouseUp' });
      const b = snap();
      const rel = (s, n) => [s[n][0] - s.b__Pelvis__[0], 0, s[n][2] - s.b__Pelvis__[2]];
      const ang = n => E.hang(rel(a, n), rel(b, n));
      const line = (s, l, r) => [s[l][0] - s[r][0], 0, s[l][2] - s[r][2]];
      const lineAng = (s0, s1, l, r) => +E.hang(line(s0, l, r), line(s1, l, r)).toFixed(2);
      const res = { shoulders: lineAng(a, b, 'b__L_Clavicle__', 'b__R_Clavicle__'), hipsLine: lineAng(a, b, 'b__L_Thigh__', 'b__R_Thigh__'), foot: +ang('b__L_Foot__').toFixed(2), hand: +ang('b__L_Hand__').toFixed(2),
        spineGapChange_mm: +((E.dist(b.b__Pelvis__, b.b__Spine0__) - E.dist(a.b__Pelvis__, a.b__Spine0__)) * 1000).toFixed(3),
        headMoved_cm: +(E.dist(a.b__Head__, b.b__Head__) * 100).toFixed(2), keyed: !!F.keys.find(k => k.frame === Math.round(app.store.frame)) };
      // the same with the inspector's X slider (from standing)
      const c = snap();
      const rows = [...document.querySelectorAll('#inspector .slider-row input[type=range]')];
      if (rows.length === 3) { rows[0].dispatchEvent(new PointerEvent('pointerdown')); rows[0].value = +rows[0].value + 25; rows[0].dispatchEvent(new Event('input')); rows[0].dispatchEvent(new Event('change')); }
      const d = snap();
      res.sliderRows = rows.length;
      res.sliderShoulders = lineAng(c, d, 'b__L_Clavicle__', 'b__R_Clavicle__'); res.sliderHipsLine = lineAng(c, d, 'b__L_Thigh__', 'b__R_Thigh__');
      res.sliderHeadMoved_cm = +(E.dist(c.b__Head__, d.b__Head__) * 100).toFixed(2);
      res.sliderFootMoved_cm = +(E.dist(c.b__L_Foot__, d.b__L_Foot__) * 100).toFixed(2);
      res.sliderSpineGapChange_mm = +((E.dist(d.b__Pelvis__, d.b__Spine0__) - E.dist(c.b__Pelvis__, c.b__Spine0__)) * 1000).toFixed(3);
      res.bad = E.badBones().length;
      return res;
    });
    info.hipTurn = hip;
    check('turning the hips 30 deg turns the legs 30 deg', Math.abs(Math.abs(hip.foot) - 30) < 2, hip);
    check('turning the hips turns the upper body with them (shoulder line turns like the hip line)', Math.abs(Math.abs(hip.hipsLine) - 30) < 2 && Math.abs(hip.shoulders - hip.hipsLine) < 2, hip);
    check('hips and lower back stay joined', Math.abs(hip.spineGapChange_mm) < 1, hip.spineGapChange_mm);
    check('the hip turn is keyed', hip.keyed);
    check('the inspector X slider for the hips also carries the upper body', hip.sliderRows === 3 && Math.abs(hip.sliderHipsLine) > 5 && Math.abs(hip.sliderShoulders - hip.sliderHipsLine) < 2 && Math.abs(hip.sliderSpineGapChange_mm) < 1, hip);
    check('hip turn: no NaN bones', hip.bad === 0);
    await shot('hip-turn');
    await page.keyboard.press('Escape');
    await sleep(100);
    check('Escape lets go of the selection', await page.evaluate(() => !app.vp.gizmo.object && !app.store.selected.bone));
  });

  // ================================================================ end
  STEP = 'end';
  try {
    const left = await page.evaluate(() => { app.setPlaying(false); app.store.setDirty(false); localStorage.removeItem('fsa.autosave'); localStorage.removeItem('fsa.myPoses'); return localStorage.getItem('fsa.autosave'); });
    check('autosave cleared at the end', left === null);
    const toasts = await page.evaluate(() => __e2e.toasts);
    info.toasts = toasts;
    for (const t of toasts) if (/err/.test(t.kind)) logs.push({ step: t.step, type: 'toast-error', text: t.text });
  } catch (e) { check('final cleanup', false, String(e)); }
  // server state unchanged
  try {
    const j = async u => (await fetch('http://127.0.0.1:8777' + u)).json();
    const projects = (await j('/api/projects')).map(p => p.file), progs = await j('/api/progressions');
    check('server: saved animations as before the test', projects.sort().join() === initialServer.projects.slice().sort().join(), projects);
    check('server: progressions as before the test', JSON.stringify(progs) === JSON.stringify(initialServer.progressions), progs);
    check('Mods\\FitStudio\\MyAnimations as before the test', listDir(MYANIM).sort().join() === before.myAnim.slice().sort().join(), listDir(MYANIM));
    check('no sound kit left behind', fs.existsSync(SOUNDKIT) === before.soundKit);
    check('Documents\\Wicked Animator Exports as before', fs.existsSync(EXPORTS) === before.exports);
  } catch (e) { check('server state check', false, String(e)); }
  await browser.close();

  const errors = logs.filter(l => ['error', 'pageerror', 'requestfailed', 'http', 'toast-error'].includes(l.type));
  const warnings = logs.filter(l => l.type === 'warning' || l.type === 'warn');
  const report = { when: new Date().toISOString(), passed: results.filter(r => r.ok).length, failed: results.filter(r => !r.ok).length, results, errors, warnings, info };
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 1));
  console.log('\n================ SUMMARY');
  console.log(`checks: ${report.passed} passed, ${report.failed} failed`);
  for (const r of results.filter(r => !r.ok)) console.log(`  FAIL [${r.step}] ${r.name} :: ${JSON.stringify(r.detail).slice(0, 400)}`);
  console.log(`console errors / page errors / failed requests: ${errors.length}`);
  for (const e of errors) console.log(`  [${e.step}] ${e.type}: ${e.text.slice(0, 300)}`);
  console.log(`warnings: ${warnings.length}`);
  for (const e of warnings.slice(0, 20)) console.log(`  [${e.step}] ${e.text.slice(0, 200)}`);
  console.log('report:', path.join(OUT, 'report.json'));
})().catch(async e => {
  console.error('E2E crashed:', e);
  try { await page.evaluate(() => { app.store.setDirty(false); localStorage.removeItem('fsa.autosave'); }); } catch { /* ignore */ }
  try { await browser.close(); } catch { /* ignore */ }
  process.exit(1);
});
