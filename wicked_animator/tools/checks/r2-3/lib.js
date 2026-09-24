// R2-3 check helpers: the engine page and the full app (through the shared harness), fixtures, a PASS/FAIL table.
// Nothing is ever written into the game's folders: every writing route is answered inside the browser.
'use strict';
const fs = require('fs');
const path = require('path');
const os = require('os');
const H = require('../lib/harness.js');
const L1 = require('../r1a/lib.js');

const ROOT = path.resolve(__dirname, '..', '..', '..');
const OUT = path.join(ROOT, 'cache', 'checks', 'r2-3');
const FIX = path.join(os.tmpdir(), 'wa_fixtures');
fs.mkdirSync(OUT, { recursive: true });

function argPort(def = 8853) {
  const i = process.argv.indexOf('--port');
  return i > 0 ? +process.argv[i + 1] : def;
}
function arg(name, def = null) {
  const i = process.argv.indexOf('--' + name);
  return i > 0 ? process.argv[i + 1] : def;
}

function fixtures() {
  if (!fs.existsSync(FIX)) return [];
  return fs.readdirSync(FIX).filter(f => f.endsWith('.json')).sort()
    .map(f => ({ name: f.replace(/\.json$/, ''), project: JSON.parse(fs.readFileSync(path.join(FIX, f), 'utf8')) }));
}

// The bare engine page of R1-A (engine modules only, a stand-in app per project: R.scene(project)).
async function enginePage(port, { w = 1366, h = 768 } = {}) {
  const browser = await L1.launch(w, h);
  const { page, logs } = await L1.open(browser, port, { kind: 'engine' });
  return { browser, page, logs };
}

// While another round-2 slice is half-way through main.js (it imports modules it has not written yet), the app can't
// start from the files on disk. Then R2-1's own round-1 copies of the files it owns (cache/checks/r2-1/orig) are
// served instead, so R2-3's parts are still tested in the real app. Everything else comes from disk.
const R21 = path.join(ROOT, 'cache', 'checks', 'r2-1', 'orig');
const R21_FILES = { '/js/main.js': 'js/main.js', '/js/timeline.js': 'js/timeline.js', '/js/animation.js': 'js/animation.js',
  '/js/state.js': 'js/state.js', '/js/api.js': 'js/api.js', '/': 'index.html', '/index.html': 'index.html',
  '/css/app.css': 'css/app.css', '/css/motion.css': 'css/motion.css' };
function mainBroken() {
  try {
    const src = fs.readFileSync(path.join(ROOT, 'web', 'js', 'main.js'), 'utf8');
    const deps = [...src.matchAll(/from '\.\/([a-z0-9_\-/]+\.js)'/g)].map(m => m[1]);
    return deps.filter(d => !fs.existsSync(path.join(ROOT, 'web', 'js', d)));
  } catch { return []; }
}
function pinR21(page, base) {
  const types = { js: 'text/javascript', html: 'text/html; charset=utf-8', css: 'text/css' };
  page.on('request', req => {
    if (req.isInterceptResolutionHandled && req.isInterceptResolutionHandled()) return;
    const u = new URL(req.url());
    if (u.origin !== base) return;
    const rel = R21_FILES[u.pathname];
    if (!rel || !fs.existsSync(path.join(R21, rel))) return;
    req.respond({ status: 200, contentType: types[rel.split('.').pop()], headers: { 'Cache-Control': 'no-store' }, body: fs.readFileSync(path.join(R21, rel)) }).catch(() => {});
  });
}

// The full app through the shared harness (writing routes intercepted).
async function appPage(port, opts = {}) {
  const missing = opts.pin21 === false ? [] : mainBroken();
  if (missing.length || opts.pin21) {
    console.log(`(main.js on disk needs ${missing.join(', ') || 'nothing missing'} - serving R2-1's round-1 main.js and the files it owns)`);
    const before = opts.beforeLoad;
    opts = { ...opts, beforeLoad: async page => { pinR21(page, `http://127.0.0.1:${port}`); if (before) await before(page); } };
  }
  return H.open(port, opts);
}

function table(rows, title) {
  return H.report(rows.map(r => Array.isArray(r) ? { name: r[0], ok: !!r[1], detail: r[2] } : r), title);
}

const shot = (page, name, opts) => H.shot(page, path.join(OUT, name), opts);

module.exports = { ROOT, OUT, FIX, H, argPort, arg, fixtures, enginePage, appPage, table, shot, sleep: H.sleep };
