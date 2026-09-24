// R1-A check helpers: start our own engine server, open Chrome, and open either the full app or a bare "engine
// page" that imports only the engine modules (so the engine checks never depend on main.js or the UI).
// Every writing route is answered inside the browser (nothing is ever written into the game's folders), and the
// server runs with ANIMATOR_SAVES pointing into %TEMP%.
'use strict';
const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');

const ROOT = path.resolve(__dirname, '..', '..', '..');
const OUT = path.join(ROOT, 'cache', 'checks', 'r1a');
const ORIG = path.join(OUT, 'orig');
const FIX = path.join(os.tmpdir(), 'wa_fixtures');
const FORBIDDEN = new Set([8765, 8766, 8777, 8802, 8804]);
const ENGINE_FILES = ['bones', 'animation', 'sim', 'face', 'pipeline', 'state', 'posemath'];
const WRITES = ['/api/export', '/api/bundle', '/api/project', '/api/project_remove', '/api/progressions', '/api/my_poses',
  '/api/recovery', '/api/recovery_clear', '/api/save_video', '/api/reveal', '/api/doctor_fix', '/api/promo_save'];

const sleep = ms => new Promise(r => setTimeout(r, ms));

function argPort(def = 8841) {
  const i = process.argv.indexOf('--port');
  return i > 0 ? +process.argv[i + 1] : def;
}

async function up(port) {
  try { const r = await fetch(`http://127.0.0.1:${port}/api/status`); return r.ok; } catch { return false; }
}

// Start backend/server.py on `port` (never one of the user's or other tools' ports).
async function startServer(port) {
  if (FORBIDDEN.has(port)) throw new Error(`port ${port} is not ours`);
  if (await up(port)) throw new Error(`port ${port} is already in use`);
  const saves = path.join(os.tmpdir(), 'wa_r1a_saves');
  fs.mkdirSync(saves, { recursive: true });
  const log = fs.openSync(path.join(OUT, `server_${port}.log`), 'w');
  const p = spawn('python', [path.join(ROOT, 'backend', 'server.py')], {
    cwd: ROOT, env: { ...process.env, ANIMATOR_PORT: String(port), ANIMATOR_SAVES: saves, PYTHONUNBUFFERED: '1' },
    stdio: ['ignore', log, log], windowsHide: true,
  });
  for (let i = 0; i < 240; i++) {
    if (await up(port)) return p;
    if (p.exitCode !== null) throw new Error('server exited: see ' + path.join(OUT, `server_${port}.log`));
    await sleep(250);
  }
  p.kill();
  throw new Error('server did not start');
}

function stopServer(p) { try { p && p.kill(); } catch { /* gone */ } }

async function launch(w = 1366, h = 768) {
  return puppeteer.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: 'new', protocolTimeout: 900000,
    args: ['--use-angle=d3d11', '--enable-webgl', '--ignore-gpu-blocklist', `--window-size=${w},${h}`],
  });
}

const ENGINE_HTML = `<!doctype html><html><head><meta charset="utf-8"><title>r1a engine</title>
<script type="importmap">{ "imports": {
  "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/" } }</script>
<style>html,body{margin:0;background:#15101c;overflow:hidden}canvas{display:block}</style></head>
<body><script type="module">
import * as THREE from 'three';
const mods = {};
for (const n of ${JSON.stringify(ENGINE_FILES)}) mods[n] = await import('/js/' + n + '.js');
const [rig, yf, ym, futa] = await Promise.all(['/api/rig?key=au', '/api/body?frame=yf', '/api/body?frame=ym', '/api/body?frame=yf_futa']
  .map(u => fetch(u).then(r => r.ok ? r.json() : null)));
mods.animation.setRig(rig);
const bodies = { yf, ym, yf_futa: futa || yf };
// A stand-in app like main.bakeOther's: a Store, one Sim view per sim, and a Pipeline.
function scene(project, { load = true } = {}) {
  const store = new mods.state.Store();
  if (load) store.load(JSON.parse(JSON.stringify(project))); else store.project = JSON.parse(JSON.stringify(project));
  const simViews = new Map();
  for (const s of store.project.sims) {
    mods.pipeline.simBody(s);
    const v = new mods.sim.Sim(rig, bodies[s.frame] || bodies.yf, { color: s.color, skin: s.skin });
    v.color = s.color;
    simViews.set(s.id, v);
  }
  const app = { store, simViews, playing: false };
  app.pipeline = new mods.pipeline.Pipeline(app);
  return app;
}
window.R = { THREE, ...mods, rig, bodies, scene };
window.__ready = true;
</script></body></html>`;

// Open a page: 'engine' (the bare engine page) or 'app' (the full app, ?slot=test). `orig` serves the engine
// files as they were before R1-A's edits (cache/checks/r1a/orig), for baselines.
async function open(browser, port, { kind = 'engine', orig = false, w = 1366, h = 768 } = {}) {
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
  const logs = [], writes = [];
  page.on('console', m => { const t = m.type(); if (t === 'error' || t === 'warn' || t === 'warning') logs.push(`${t}: ${m.text()}`); });
  page.on('pageerror', e => logs.push('pageerror: ' + e.message));
  await page.setRequestInterception(true);
  const base = `http://127.0.0.1:${port}`;
  page.on('request', req => {
    const u = new URL(req.url());
    if (u.origin === base) {
      if (u.pathname === '/__r1a.html') return req.respond({ status: 200, contentType: 'text/html', body: ENGINE_HTML });
      const m = /^\/js\/([a-z]+)\.js$/.exec(u.pathname), mo = /^\/orig\/js\/([a-z]+)\.js$/.exec(u.pathname);
      if (orig && m && ENGINE_FILES.includes(m[1])) return req.respond({ status: 200, contentType: 'text/javascript', body: fs.readFileSync(path.join(ORIG, m[1] + '.js'), 'utf8') });
      // the engine as it was before R1-A, always at /orig/js/... (for side-by-side comparisons)
      if (mo && ENGINE_FILES.includes(mo[1])) return req.respond({ status: 200, contentType: 'text/javascript', body: fs.readFileSync(path.join(ORIG, mo[1] + '.js'), 'utf8') });
      if (req.method() === 'POST' && WRITES.includes(u.pathname)) {
        writes.push({ url: u.pathname, body: req.postData() });
        return req.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, fake: true }) });
      }
    }
    req.continue();
  });
  await page.evaluateOnNewDocument(() => { try { localStorage.setItem('fsa.tourDone', 'true'); localStorage.removeItem('fsa.autosave'); } catch { /* */ } });
  if (kind === 'engine') {
    await page.goto(base + '/__r1a.html', { waitUntil: 'load', timeout: 120000 });
    await page.waitForFunction('window.__ready === true', { timeout: 120000 });
  } else {
    await page.goto(base + '/?slot=test', { waitUntil: 'load', timeout: 180000 });
    await page.waitForSelector('#loading.done', { timeout: 120000 });
  }
  return { page, logs, writes };
}

function fixtures() {
  if (!fs.existsSync(FIX)) return [];
  return fs.readdirSync(FIX).filter(f => f.endsWith('.json')).sort().map(f => ({ name: f.replace(/\.json$/, ''), project: JSON.parse(fs.readFileSync(path.join(FIX, f), 'utf8')) }));
}

// A PASS/FAIL table; returns true when everything passed.
function table(rows) {
  const w = Math.max(...rows.map(r => r[0].length), 10);
  let ok = true;
  for (const [name, pass, detail] of rows) {
    if (!pass) ok = false;
    console.log(`${pass ? 'PASS' : 'FAIL'}  ${name.padEnd(w)}  ${detail === undefined ? '' : typeof detail === 'string' ? detail : JSON.stringify(detail)}`);
  }
  console.log(ok ? `\nALL ${rows.length} PASS` : `\n${rows.filter(r => !r[1]).length} of ${rows.length} FAILED`);
  return ok;
}

module.exports = { ROOT, OUT, ORIG, FIX, sleep, argPort, startServer, stopServer, launch, open, fixtures, table };
