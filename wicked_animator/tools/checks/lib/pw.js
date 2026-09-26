// Playwright twin of harness.js for PCs without Chrome in C:/Program Files (Linux, CI): the same ready signal
// (#loading.done), the same console log, and the same writing routes answered inside the browser - nothing reaches
// the server's disk unless `allow` lets it through.
//
//   const P = require('../lib/pw.js');
//   const { browser, page, logs, writes } = await P.open(8792);
//   ... await browser.close();
//
// Playwright comes from the global node_modules (npm root -g) or NODE_PATH; its Chromium from PLAYWRIGHT_BROWSERS_PATH.
// Start the server with tools/checks/lib/fake_game_server.py on a PC without The Sims 4.
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const H = require('./harness.js');

function playwright() {
  try { return require('playwright'); } catch { /* not local */ }
  const root = execSync('npm root -g', { encoding: 'utf8' }).trim();
  return require(path.join(root, 'playwright'));
}

// A local three.js 0.160 (WA_THREE_DIR, or 'three' where node finds it), or null to use the CDN.
function threeDir() {
  const tries = [process.env.WA_THREE_DIR];
  try { tries.push(path.dirname(require.resolve('three/package.json'))); } catch { /* not installed here */ }
  try { tries.push(path.join(execSync('npm root -g', { encoding: 'utf8' }).trim(), 'three')); } catch { /* no npm */ }
  for (const d of tries) if (d && fs.existsSync(path.join(d, 'build', 'three.module.js'))) return path.resolve(d);
  return null;
}

async function open(port, { w = 1366, h = 768, intercept = true, allow = [], extraWrites = [], query = '', timeout = 120000, scene = null } = {}) {
  port = +port;
  if (H.REFUSED.has(port)) throw new Error(`port ${port} belongs to someone else (the user's app, the Sims Hub or the verifier)`);
  const base = `http://127.0.0.1:${port}`;
  const { chromium } = playwright();
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const context = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await context.newPage();
  const logs = [], writes = [];
  page.on('console', m => logs.push({ type: m.type(), text: m.text() }));
  page.on('pageerror', e => logs.push({ type: 'pageerror', text: e.message, stack: e.stack }));
  page.on('requestfailed', r => { if (!/favicon/.test(r.url())) logs.push({ type: 'requestfailed', text: `${r.url()} ${r.failure() && r.failure().errorText}` }); });
  page.on('dialog', d => { logs.push({ type: 'dialog', text: d.message() }); d.dismiss().catch(() => {}); });
  await page.addInitScript(() => { try { localStorage.setItem('fsa.tourDone', 'true'); localStorage.removeItem('fsa.autosave'); } catch { /* ignore */ } });
  // three.js comes from a CDN (index.html's import map); where the CDN can't be reached, a local copy stands in
  const three = threeDir();
  if (three) {
    await page.route(/^https:\/\/cdn\.jsdelivr\.net\/npm\/three@[^/]+\/(.*)$/, route => {
      const rel = route.request().url().replace(/^https:\/\/cdn\.jsdelivr\.net\/npm\/three@[^/]+\//, '').split('?')[0];
      const file = path.join(three, rel);
      if (!file.startsWith(three) || !fs.existsSync(file)) return route.fulfill({ status: 404, body: 'not found' });
      return route.fulfill({ status: 200, contentType: 'text/javascript; charset=utf-8', body: fs.readFileSync(file) });
    });
  }
  if (intercept) {
    const writing = new Set([...H.WRITES, ...extraWrites]);
    const allowed = new Set(allow);
    await page.route(base + '/api/**', async route => {
      const req = route.request();
      const u = new URL(req.url());
      if (req.method() === 'POST' && writing.has(u.pathname) && !allowed.has(u.pathname)) {
        writes.push({ route: u.pathname, body: req.postData() || '', t: Date.now() });
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(H.fakeAnswer(u.pathname, req.postData() || '')) });
      }
      return route.continue();
    });
  }
  await page.goto(`${base}/?slot=test${query ? '&' + query : ''}`, { waitUntil: 'domcontentloaded', timeout });
  await page.waitForSelector('#loading.done', { state: 'attached', timeout }).catch(() => logs.push({ type: 'harness', text: 'the app never became ready (#loading.done)' }));
  // the app opens on an empty scene; scene: 'couple' starts the check from the ready-made couple (as harness.js)
  if (scene) await page.evaluate(t => { if (!app.store.project.sims.length) app.newScene(false, false, t); }, scene).catch(e => logs.push({ type: 'harness', text: 'no ' + scene + ' scene: ' + e.message }));
  return { browser, context, page, logs, writes, base };
}

// Console lines that mean something broke: uncaught errors, failed module loads, console.error.
function problems(logs, { ignore = [] } = {}) {
  return logs.filter(l => (l.type === 'pageerror' || l.type === 'error' || l.type === 'requestfailed' || l.type === 'harness')
    && !ignore.some(rx => rx.test(l.text)));
}

module.exports = { open, problems, report: H.report, sleep: H.sleep, playwright };
