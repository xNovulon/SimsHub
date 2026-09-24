// R1-C check helpers: a private server on the slice's port, a headless Chrome page on it with every writing route
// answered inside the browser (nothing is saved, exported or written), screenshots, and a PASS/FAIL table.
// Same shape as tools/checks/lib/harness.js (plan 2.9), kept here so the R1-C checks run on their own.
const path = require('path'), fs = require('fs'), cp = require('child_process'), http = require('http');
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');

const ROOT = path.join(__dirname, '..', '..', '..');
const OUT = path.join(ROOT, 'cache', 'checks', 'r1c');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const FORBIDDEN = new Set([8765, 8766, 8777, 8802, 8804]);
const WRITES = ['/api/export', '/api/bundle', '/api/project', '/api/project_remove', '/api/progressions', '/api/my_poses',
  '/api/recovery', '/api/recovery_clear', '/api/save_video', '/api/reveal', '/api/doctor_fix', '/api/promo_save'];
const sleep = ms => new Promise(r => setTimeout(r, ms));

function argPort(def = 8843) {
  const i = process.argv.indexOf('--port');
  return i > 0 ? +process.argv[i + 1] : def;
}

function get(url) {
  return new Promise((res, rej) => {
    const r = http.get(url, x => { let b = ''; x.on('data', d => { b += d; }); x.on('end', () => res({ status: x.statusCode, body: b })); });
    r.on('error', rej); r.setTimeout(4000, () => r.destroy(new Error('timeout')));
  });
}

// Our own server on `port` (never one of the protected ports). Returns the child process, or null when a server of
// this tree already answers there (then it is left running as it was).
async function startServer(port, env = {}) {
  if (FORBIDDEN.has(port)) throw new Error(`port ${port} is protected`);
  try { const r = await get(`http://127.0.0.1:${port}/api/status`); if (r.status === 200) return null; } catch { /* free */ }
  const p = cp.spawn('python', [path.join(ROOT, 'backend', 'server.py')], { env: { ...process.env, ANIMATOR_PORT: String(port), ...env }, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  let log = '';
  p.stdout.on('data', d => { log += d; }); p.stderr.on('data', d => { log += d; });
  p.log = () => log;
  for (let i = 0; i < 120; i++) {
    await sleep(250);
    if (/already running/.test(log)) throw new Error(`port ${port} is busy: ${log}`);
    try { const r = await get(`http://127.0.0.1:${port}/api/status`); if (r.status === 200) return p; } catch { /* not yet */ }
  }
  p.kill();
  throw new Error('server did not start: ' + log);
}
function stopServer(p) { if (p) try { p.kill(); } catch { /* gone */ } }

async function launch({ w = 1366, h = 768, gpu = false } = {}) {
  const args = ['--no-first-run', '--no-default-browser-check', '--disable-extensions', '--mute-audio', '--autoplay-policy=no-user-gesture-required',
    `--window-size=${w},${h}`];
  if (gpu) args.push('--use-angle=d3d11', '--enable-gpu-rasterization', '--ignore-gpu-blocklist');
  else args.push('--use-angle=swiftshader', '--enable-unsafe-swiftshader');
  return puppeteer.launch({ executablePath: CHROME, headless: 'new', args, defaultViewport: { width: w, height: h }, protocolTimeout: 240000 });
}

// open(port, opts) -> {browser, page, logs, writes}
async function open(port, { w = 1366, h = 768, reducedMotion = false, intercept = true, extraWrites = [], block = [], query = '', gpu = false,
  browser = null, wait = true, beforeLoad = null } = {}) {
  const own = !browser;
  browser = browser || await launch({ w, h, gpu });
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h });
  if (reducedMotion) await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
  const logs = [], writes = [];
  page.on('console', m => logs.push(`[${m.type()}] ${m.text()}`));
  page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`));
  const writeSet = new Set([...WRITES, ...extraWrites]);
  if (intercept || block.length) {
    await page.setRequestInterception(true);
    page.on('request', req => {
      const u = new URL(req.url());
      if (block.some(b => u.pathname.endsWith(b))) {
        return req.respond({ status: 200, contentType: 'text/javascript', body: 'export {};' });
      }
      if (intercept && u.hostname === '127.0.0.1' && req.method() === 'POST' && writeSet.has(u.pathname)) {
        writes.push({ path: u.pathname, body: (req.postData() || '').slice(0, 200) });
        return req.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, fake: true, file: 'fake.json', name: 'fake' }) });
      }
      req.continue();
    });
  }
  if (beforeLoad) await beforeLoad(page);
  const url = `http://127.0.0.1:${port}/?slot=test${query ? '&' + query : ''}`;
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 120000 });
  if (wait) await page.waitForSelector('#loading.done', { timeout: 120000 });
  return { browser: own ? browser : null, sharedBrowser: browser, page, logs, writes };
}

async function shot(page, file) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  await page.screenshot({ path: file });
  return file;
}

// A PASS/FAIL table. check(name, ok, detail)
function table() {
  const rows = [];
  const check = (name, ok, detail = '') => {
    rows.push({ name, ok: !!ok, detail: typeof detail === 'string' ? detail : JSON.stringify(detail) });
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail !== '' && detail != null ? '  ::  ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)) : ''}`);
    return !!ok;
  };
  const print = title => {
    const w = Math.min(90, Math.max(...rows.map(r => r.name.length), 10));
    console.log(`\n${title}\n${'-'.repeat(w + 60)}`);
    for (const r of rows) console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name.padEnd(w)}  ${r.detail.slice(0, 160)}`);
    const bad = rows.filter(r => !r.ok).length;
    console.log(`${'-'.repeat(w + 60)}\n${rows.length - bad} passed, ${bad} failed`);
    return bad === 0;
  };
  return { check, print, rows };
}

module.exports = { ROOT, OUT, sleep, argPort, startServer, stopServer, launch, open, shot, table, get };
