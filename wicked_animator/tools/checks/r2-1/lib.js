// R2-1 check helpers: our own server (ANIMATOR_SAVES and WICKED_PROJECTS_DIR in %TEMP%), Chrome, and either the full
// app (through the shared harness: every writing route is answered inside the browser) or a bare "engine page" that
// imports only the engine modules. `orig: true` serves animation.js / state.js as they were before R2-1's edits
// (cache/checks/r2-1/orig), so "old projects bake exactly as before" compares only this slice's changes.
'use strict';
const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');

const ROOT = path.resolve(__dirname, '..', '..', '..');
const OUT = path.join(ROOT, 'cache', 'checks', 'r2-1');
const ORIG = path.join(OUT, 'orig', 'js');
const FIX = path.join(os.tmpdir(), 'wa_fixtures');
const SAVES = path.join(os.tmpdir(), 'wa_r2-1_saves');
const FORBIDDEN = new Set([8765, 8766, 8777, 8802, 8804]);
const ENGINE_FILES = ['bones', 'animation', 'sim', 'face', 'pipeline', 'state', 'posemath', 'keyops', 'motion', 'facekit'];
const ORIG_FILES = ['animation', 'state'];        // this slice's engine files
const sleep = ms => new Promise(r => setTimeout(r, ms));
fs.mkdirSync(OUT, { recursive: true });

function argPort(def = 8851) {
  const i = process.argv.indexOf('--port');
  return i > 0 ? +process.argv[i + 1] : def;
}

async function up(port) {
  try { const r = await fetch(`http://127.0.0.1:${port}/api/status`); return r.ok; } catch { return false; }
}

// Start backend/server.py on `port`. Saves (projects, My poses, references, recovery) go to a folder in %TEMP%.
async function startServer(port, env = {}) {
  if (FORBIDDEN.has(port)) throw new Error(`port ${port} is not ours`);
  if (await up(port)) throw new Error(`port ${port} is already in use`);
  fs.mkdirSync(SAVES, { recursive: true });
  fs.mkdirSync(path.join(OUT, 'logs'), { recursive: true });
  const log = fs.openSync(path.join(OUT, 'logs', `server_${port}.log`), 'a');
  const p = spawn('python', [path.join(ROOT, 'backend', 'server.py')], {
    cwd: ROOT, env: { ...process.env, ANIMATOR_PORT: String(port), ANIMATOR_SAVES: SAVES, WICKED_PROJECTS_DIR: SAVES, PYTHONUNBUFFERED: '1', ...env },
    stdio: ['ignore', log, log], windowsHide: true,
  });
  for (let i = 0; i < 240; i++) {
    if (await up(port)) return p;
    if (p.exitCode !== null) throw new Error('server exited: see ' + path.join(OUT, 'logs', `server_${port}.log`));
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

const ENGINE_HTML = `<!doctype html><html><head><meta charset="utf-8"><title>r2-1 engine</title>
<script type="importmap">{ "imports": {
  "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/" } }</script>
<style>html,body{margin:0;background:#15101c;overflow:hidden}canvas{display:block}</style></head>
<body><script type="module">
import * as THREE from 'three';
const mods = {};
for (const n of ${JSON.stringify(ENGINE_FILES)}) { try { mods[n] = await import('/js/' + n + '.js'); } catch (e) { mods[n] = null; console.warn('no module', n, e.message); } }
const [rig, yf, ym, futa] = await Promise.all(['/api/rig?key=au', '/api/body?frame=yf', '/api/body?frame=ym', '/api/body?frame=yf_futa']
  .map(u => fetch(u).then(r => r.ok ? r.json() : null)));
mods.animation.setRig(rig);
if (mods.facekit && mods.facekit.setRig) mods.facekit.setRig(rig);
const bodies = { yf, ym, yf_futa: futa || yf };
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

const WRITES = ['/api/export', '/api/bundle', '/api/project', '/api/project_remove', '/api/progressions', '/api/my_poses',
  '/api/recovery', '/api/recovery_clear', '/api/save_video', '/api/reveal', '/api/doctor_fix', '/api/promo_save'];

// The bare engine page. orig: animation.js and state.js as they were before this slice.
async function openEngine(browser, port, { orig = false, w = 1280, h = 800 } = {}) {
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
  const logs = [];
  page.on('console', m => { const t = m.type(); if (t === 'error' || t === 'warn' || t === 'warning') logs.push(`${t}: ${m.text()}`); });
  page.on('pageerror', e => logs.push('pageerror: ' + e.message));
  await page.setRequestInterception(true);
  const base = `http://127.0.0.1:${port}`;
  page.on('request', req => {
    const u = new URL(req.url());
    if (u.origin === base) {
      if (u.pathname === '/__r21.html') return req.respond({ status: 200, contentType: 'text/html', body: ENGINE_HTML });
      const m = /^\/js\/([a-z]+)\.js$/.exec(u.pathname);
      if (orig && m && ORIG_FILES.includes(m[1])) return req.respond({ status: 200, contentType: 'text/javascript', body: fs.readFileSync(path.join(ORIG, m[1] + '.js'), 'utf8') });
      if (req.method() === 'POST' && WRITES.includes(u.pathname)) return req.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, fake: true }) });
    }
    req.continue();
  });
  await page.goto(base + '/__r21.html', { waitUntil: 'load', timeout: 120000 });
  await page.waitForFunction('window.__ready === true', { timeout: 120000 });
  return { page, logs };
}

function fixtures() {
  if (!fs.existsSync(FIX)) return [];
  return fs.readdirSync(FIX).filter(f => f.endsWith('.json')).sort().map(f => ({ name: f.replace(/\.json$/, ''), project: JSON.parse(fs.readFileSync(path.join(FIX, f), 'utf8')) }));
}

// rows: [name, pass, detail]; prints a PASS/FAIL table, returns true when all passed
function table(rows, title = '') {
  if (title) console.log('\n' + title);
  const w = Math.max(...rows.map(r => r[0].length), 10);
  let ok = true;
  for (const [name, pass, detail] of rows) {
    if (!pass) ok = false;
    console.log(`${pass ? 'PASS' : 'FAIL'}  ${name.padEnd(w)}  ${detail === undefined ? '' : (typeof detail === 'string' ? detail : JSON.stringify(detail)).slice(0, 400)}`);
  }
  console.log(ok ? `\nALL ${rows.length} PASS` : `\n${rows.filter(r => !r[1]).length} of ${rows.length} FAILED`);
  return ok;
}

module.exports = { ROOT, OUT, ORIG, FIX, SAVES, sleep, argPort, startServer, stopServer, launch, openEngine, fixtures, table, up };
