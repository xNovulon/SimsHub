// Test harness for Novulon's Wicked Animator checks (plan 2.9). Every slice may use it.
//
//   const H = require('../lib/harness.js');
//   const { browser, page, logs, writes } = await H.open(8842, { w: 1366, h: 768 });
//   ... await H.shot(page, 'cache/checks/r1b/x.png'); const baked = await H.bake(page); ...
//   await browser.close();
//
// - Chrome from C:/Program Files, puppeteer-core from Tools/asws (nothing is downloaded).
// - The page opens with ?slot=test and waits for #loading.done (the app's ready signal).
// - intercept (default on): every writing route is answered inside the browser with {ok: true, fake: true} (plus a
//   few harmless fields the app reads) and recorded in `writes` - nothing reaches the server's disk. `allow` lets
//   named routes through; only use it against a server started with a fake-folder override (plan 2.8). `passed`
//   lists the writing requests that did go through (only `allow`ed ones).
// - memory: true also keeps what the app saves (animations, progressions, My poses) in the test's memory and answers
//   the reading routes from it on top of the server's own lists, so saving, opening and chaining work like for a
//   user (tools/e2e.js uses it). tools/checks/lib/offline_pkg.py builds the packages offline in %TEMP%.
// - Ports 8765 (the user's app), 8766 (Sims Hub) and 8777 (verifier) are refused.
const path = require('path');
const fs = require('fs');
const http = require('http');
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const REFUSED = new Set([8765, 8766, 8777]);
const ROOT = path.join(__dirname, '..', '..', '..');

// POST routes that write something (files, the Mods folder, saves). Answered in the browser when intercepting.
const WRITES = ['/api/export', '/api/bundle', '/api/project', '/api/project_remove', '/api/progressions', '/api/my_poses',
  '/api/recovery', '/api/recovery_clear', '/api/save_video', '/api/reveal', '/api/doctor_fix', '/api/promo_save', '/api/posepack', '/api/reference'];

// What a fake answer looks like: always {ok: true, fake: true}, plus the fields the app reads from the real one.
function fakeAnswer(route, body) {
  const base = { ok: true, fake: true };
  let data = null;
  try { data = body ? JSON.parse(body) : null; } catch { /* not JSON */ }
  if (route === '/api/export') {
    return { ...base, path: 'C:\\(test - nothing was written)\\' + ((data && data.name) || 'animation') + '.package',
      package: 'test.package', clips: [], bytes: 0, next: [], next_names: [], random: true, sound_kit: null, replaced: [], warnings: [] };
  }
  if (route === '/api/project') {
    const name = (data && data.name) || 'untitled';
    return { ...base, saved: name, file: name, uid: data && data.uid, name, renamed: false };
  }
  if (route === '/api/bundle') {
    const n = data && Array.isArray(data.animations) ? data.animations.length : 0;
    const title = (data && data.name) || 'My Animations';
    return { ...base, folder: 'C:\\(test - nothing was written)\\' + title, package: 'C:\\(test - nothing was written)\\' + title + '\\' + title + '.package',
      zip: 'C:\\(test - nothing was written)\\' + title + '.zip', bytes: 0, animations: n, progressions: [], sounds_packed: 0, credits: {},
      missing_sounds: [], sounds_need_pack: {}, installed: [], warnings: [] };
  }
  // a reference picture/video upload (binary body): answered here, never written into saves\FitStudionimator_refs
  if (route === '/api/reference') return { ...base, file: '0123456789abcdef.png', bytes: 0 };
  if (route === '/api/my_poses' || route === '/api/progressions') return Array.isArray(data) ? data : base;
  return base;
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

// ---------------------------------------------------------------- memory mode
// With memory: true the saved animations, progressions and My poses the app writes are kept here, in the test's
// memory, and read back from here (on top of what the server really has) - so a test can save, open, chain and list
// animations like a user does while nothing reaches the server's disk.
// The file-name rule of backend/projects.py safe() (the same as web/js/api.js projectFileName).
const RESERVED_NAME = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i;
const trimDotsSpaces = x => x.replace(/^[ .]+|[ .]+$/g, '');
function projectFileName(name) {
  let s = String(name || '').replace(/[^\p{L}\p{N}_ \-().,'!&+]+/gu, '');
  s = trimDotsSpaces(s.split(' ').filter(Boolean).join(' '));
  s = trimDotsSpaces(Array.from(s).slice(0, 80).join(''));
  if (RESERVED_NAME.test(s)) s += '_';
  return s || 'untitled';
}
function metaOf(d, file, modified) {
  const sims = d.sims || [];
  return { file, uid: d.uid, name: d.name || '', author: d.author || '', category: d.category || '', tags: d.tags || [], locations: d.locations || [],
    sims: sims.length, genders: sims.map(x => x.gender || 'BOTH'), bodies: sims.map(x => x.frame || 'yf'),
    keys: sims.reduce((a, x) => a + (x.keys || []).length, 0), layers: sims.reduce((a, x) => a + (x.layers || []).length, 0),
    length: d.length || 90, fps: d.fps || 30, has_thumb: false, modified, memory: true };
}
function makeMemory() {
  return { projects: new Map(), removed: new Set(), progressions: null, myPoses: null, clock: 0 };
}

// A small proxy for the page's requests to the app server: at most 4 at a time, refused connections retried
// (the Python server refuses a burst of parallel connections now and then).
function makeProxy() {
  const agent = new http.Agent({ keepAlive: false, maxSockets: 4 });
  const stats = { served: 0, retries: 0, failed: 0 };
  const fetchVia = req => {
    const u = new URL(req.url());
    const headers = { ...req.headers() };
    const body = req.postData();
    // a forwarded POST carries its exact length and is never chunked (the Python server reads Content-Length only)
    for (const k of Object.keys(headers)) if (['transfer-encoding', 'content-length'].includes(k.toLowerCase())) delete headers[k];
    if (body != null) headers['content-length'] = String(Buffer.byteLength(body));
    else if (!/^(GET|HEAD|OPTIONS)$/i.test(req.method())) headers['content-length'] = '0';
    const once = () => new Promise((res, rej) => {
      const r = http.request({ method: req.method(), hostname: u.hostname, port: u.port, path: u.pathname + u.search, headers, agent }, resp => {
        const chunks = [];
        resp.on('data', c => chunks.push(c));
        resp.on('end', () => res({ status: resp.statusCode, headers: resp.headers, body: Buffer.concat(chunks) }));
        resp.on('error', rej);
      });
      r.on('error', rej);
      if (body) r.write(body);
      r.end();
    });
    return (async () => {
      for (let i = 0; ; i++) {
        try { return await once(); } catch (e) {
          if (i >= 12 || !['ECONNREFUSED', 'ECONNRESET'].includes(e.code)) throw e;
          stats.retries++; await sleep(60 * (i + 1));
        }
      }
    })();
  };
  return { fetchVia, stats };
}

async function open(port, { w = 1366, h = 768, reducedMotion = false, intercept = true, extraWrites = [], allow = [], memory = false,
  url = '/', query = '', headless = 'new', timeout = 180000, args = [], beforeLoad = null } = {}) {
  port = +port;
  if (REFUSED.has(port)) throw new Error(`port ${port} belongs to someone else (the user's app, the Sims Hub or the verifier)`);
  const base = `http://127.0.0.1:${port}`;
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless, protocolTimeout: 900000,
    args: ['--use-angle=d3d11', '--enable-webgl', '--ignore-gpu-blocklist', `--window-size=${w},${h}`, ...args],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
  if (reducedMotion) await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
  const logs = [], writes = [];
  page.on('console', m => logs.push({ type: m.type(), text: m.text() }));
  page.on('pageerror', e => logs.push({ type: 'pageerror', text: e.message, stack: e.stack }));
  page.on('requestfailed', r => { if (!/favicon/.test(r.url())) logs.push({ type: 'requestfailed', text: `${r.url()} ${r.failure() && r.failure().errorText}` }); });
  page.on('dialog', d => { logs.push({ type: 'dialog', text: d.message() }); d.dismiss().catch(() => {}); });
  // the guided tour never starts in a check, and no old browser autosave is offered
  await page.evaluateOnNewDocument(() => { try { localStorage.setItem('fsa.tourDone', 'true'); localStorage.removeItem('fsa.autosave'); } catch { /* ignore */ } });
  if (beforeLoad) await beforeLoad(page);
  const proxy = makeProxy();
  const writing = new Set([...WRITES, ...extraWrites]);
  const allowed = new Set(allow);
  const mem = memory ? makeMemory() : null;
  const passed = [];                 // writing requests that were let through to the server (only `allow`)
  const json = (req, obj, status = 200) => req.respond({ status, contentType: 'application/json', headers: { 'Cache-Control': 'no-store' }, body: JSON.stringify(obj) }).catch(() => {});
  const realJson = async pathQ => {
    const r = await fetch(base + pathQ);
    if (!r.ok) throw Object.assign(new Error('HTTP ' + r.status), { status: r.status });
    return r.json();
  };
  const memList = async () => {
    const real = await realJson('/api/projects').catch(() => []);
    const mine = new Set([...mem.projects.keys()]);
    const out = real.filter(m => !mem.removed.has((m.file || '').toLowerCase()) && !mine.has((m.file || '').toLowerCase()));
    for (const [, x] of mem.projects) out.push(x.meta);
    return out.sort((a, b) => b.modified - a.modified);
  };
  // answers a memory route, or returns false (the request then goes on to the server)
  const answerFromMemory = async (req, route, q, body) => {
    const post = req.method() === 'POST';
    if (!post && route === '/api/projects') return json(req, await memList());
    if (!post && route === '/api/project') {
      const byFile = q.get('name') && mem.projects.get(q.get('name').toLowerCase());
      const byUid = q.get('uid') && [...mem.projects.values()].find(x => x.project.uid === q.get('uid'));
      const byName = q.get('name') && [...mem.projects.values()].find(x => x.project.name === q.get('name'));
      const hit = byFile || byUid || byName;
      if (hit) return json(req, JSON.parse(JSON.stringify(hit.project)));
      const gone = q.get('name') && mem.removed.has(q.get('name').toLowerCase());
      if (gone) return json(req, { error: 'That animation is not saved any more.' }, 404);
      return false;
    }
    if (!post && route === '/api/project_thumb' && q.get('name') && mem.projects.has(q.get('name').toLowerCase())) return json(req, { error: 'no picture' }, 404);
    if (route === '/api/progressions') {
      if (mem.progressions === null) mem.progressions = await realJson('/api/progressions').catch(() => []);
      if (!post) return json(req, mem.progressions);
      const items = Array.isArray(body) ? body : (body && body.progressions) || [];
      mem.progressions = items.map(it => ({ id: it.id || 'g' + Math.random().toString(16).slice(2, 12), name: String(it.name || 'Progression').trim().slice(0, 60),
        author: String(it.author || '').trim().slice(0, 40), steps: (it.steps || []).filter(Boolean), repeat: !!it.repeat }));
      return json(req, mem.progressions);
    }
    if (route === '/api/my_poses') {
      if (mem.myPoses === null) mem.myPoses = await realJson('/api/my_poses').catch(() => []);
      if (!post) return json(req, mem.myPoses);
      mem.myPoses = (Array.isArray(body) ? body : (body && body.poses) || []).filter(x => x && typeof x === 'object');
      return json(req, { saved: mem.myPoses.length, fake: true });
    }
    if (post && route === '/api/project') {
      // the server's rule: a different animation under the same file name is never overwritten ('Name (2)')
      const d = body || {};
      if (!d.uid) d.uid = 'a' + Math.random().toString(16).slice(2, 14);
      const want = projectFileName(d.name || 'untitled');
      const list = await memList();
      const taken = f => list.find(m => (m.file || '').toLowerCase() === f.toLowerCase() && m.uid !== d.uid);
      let file = want, replaced = null;
      if (taken(want)) {
        if (q.get('overwrite')) { replaced = taken(want); mem.removed.add(want.toLowerCase()); mem.projects.delete(want.toLowerCase()); }
        else for (let k = 2; taken(file); k++) file = want + ' (' + k + ')';
      }
      for (const [f, x] of [...mem.projects]) if (x.project.uid === d.uid && f !== file.toLowerCase()) mem.projects.delete(f);
      for (const m of list) if (!m.memory && m.uid === d.uid && (m.file || '').toLowerCase() !== file.toLowerCase()) mem.removed.add(m.file.toLowerCase());
      mem.projects.set(file.toLowerCase(), { project: JSON.parse(JSON.stringify(d)), meta: metaOf(d, file, Date.now() / 1000 + (++mem.clock) / 1000) });
      return json(req, { ok: true, fake: true, saved: file, file, name: d.name || '', uid: d.uid, renamed: file !== want, replaced });
    }
    if (post && route === '/api/project_remove') {
      const f = String((body && body.file) || '').toLowerCase();
      mem.removed.add(f); mem.projects.delete(f);
      return json(req, { ok: true, fake: true, removed: body && body.file });
    }
    return false;
  };
  if (intercept) {
    await page.setRequestInterception(true);
    page.on('request', async req => {
      if (req.isInterceptResolutionHandled && req.isInterceptResolutionHandled()) return;
      const u = req.url();
      if (!u.startsWith(base)) return req.continue().catch(() => {});
      const url0 = new URL(u), route = url0.pathname;
      const isWrite = req.method() === 'POST' && writing.has(route) && !allowed.has(route);
      if (isWrite) writes.push({ route, url: u, body: req.postData() || '', t: Date.now() });
      if (mem) {
        let body = null;
        try { body = req.postData() ? JSON.parse(req.postData()) : null; } catch { body = null; }
        try { if (await answerFromMemory(req, route, url0.searchParams, body) !== false) return; } catch (e) { logs.push({ type: 'harness', text: 'memory route failed: ' + e.message }); }
      }
      if (isWrite) {
        const body = req.postData() || '';
        return req.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(fakeAnswer(route, body)) }).catch(() => {});
      }
      if (req.method() === 'POST' && writing.has(route)) passed.push({ route, t: Date.now() });
      try {
        const r = await proxy.fetchVia(req);
        const hd = {};
        for (const [k, v] of Object.entries(r.headers)) if (!['content-length', 'connection', 'transfer-encoding', 'keep-alive'].includes(k)) hd[k] = Array.isArray(v) ? v.join(', ') : v;
        proxy.stats.served++;
        await req.respond({ status: r.status, headers: hd, body: r.body });
      } catch (e) {
        proxy.stats.failed++;
        logs.push({ type: 'proxy', text: `${u} ${String(e && e.message || e)}` });
        await req.abort('connectionrefused').catch(() => {});
      }
    });
  }
  const sep = url.includes('?') ? '&' : '?';
  await page.goto(`${base}${url}${sep}slot=test${query ? '&' + query : ''}`, { waitUntil: 'domcontentloaded', timeout });
  await page.waitForSelector('#loading.done', { timeout }).catch(() => logs.push({ type: 'harness', text: 'the app never became ready (#loading.done)' }));
  return { browser, page, logs, writes, passed, memory: mem, proxy: proxy.stats, base };
}

async function shot(page, file, opts = {}) {
  const f = path.isAbsolute(file) ? file : path.join(ROOT, file);
  fs.mkdirSync(path.dirname(f), { recursive: true });
  await page.screenshot({ path: f, ...opts });
  return f;
}

// app.bake() of the open project (the payload Send to game would write).
async function bake(page) {
  return page.evaluate(() => window.app.bake());
}

// A PASS/FAIL table; returns true when everything passed.
function report(rows, title = 'checks') {
  const w = Math.max(10, ...rows.map(r => String(r.name).length));
  console.log(`\n${title}`);
  console.log('-'.repeat(Math.min(160, w + 20)));
  for (const r of rows) console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${String(r.name).padEnd(w)}  ${r.detail === undefined || r.detail === null ? '' : (typeof r.detail === 'string' ? r.detail : JSON.stringify(r.detail)).slice(0, 400)}`);
  const bad = rows.filter(r => !r.ok).length;
  console.log('-'.repeat(Math.min(160, w + 20)));
  console.log(`${rows.length - bad} PASS, ${bad} FAIL`);
  return bad === 0;
}

module.exports = { open, shot, bake, report, sleep, WRITES, REFUSED, ROOT, fakeAnswer, projectFileName };
