// R1-F: bake the export fixtures in the real app (read-only), for the byte-identical export check.
//   node tools/checks/r1f/bake_fixtures.js <port> <out_dir>
// Fixtures: the saved projects in saves\FitStudio\animator_projects (read straight from disk, read-only) and four
// Magic-made projects (cowgirl, missionary, doggy, bj). Every writing route is answered inside the browser.
const path = require('path');
const fs = require('fs');
const os = require('os');
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');

const PORT = +(process.argv[2] || 8846);
const OUT = process.argv[3] || path.join(__dirname, '..', '..', '..', 'cache', 'checks', 'r1f', 'baseline');
if ([8765, 8766, 8777, 8802, 8804].includes(PORT)) { console.error('refusing port', PORT); process.exit(2); }
const SAVES = path.join(os.homedir(), 'Documents', 'Electronic Arts', 'The Sims 4', 'saves', 'FitStudio', 'animator_projects');
const WRITES = ['/api/export', '/api/bundle', '/api/project', '/api/project_remove', '/api/progressions', '/api/my_poses',
  '/api/recovery', '/api/recovery_clear', '/api/save_video', '/api/reveal', '/api/doctor_fix', '/api/promo_save'];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: 'new', args: ['--window-size=1366,768', '--autoplay-policy=no-user-gesture-required', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1366, height: 768 });
  await page.setRequestInterception(true);
  page.on('request', r => {
    const u = new URL(r.url());
    if (r.method() === 'POST' && WRITES.includes(u.pathname)) return r.respond({ status: 200, contentType: 'application/json', body: '{"ok":true,"fake":true}' });
    r.continue();
  });
  const logs = [];
  page.on('console', m => { if (m.type() === 'error') logs.push(m.text()); });
  page.on('pageerror', e => logs.push('pageerror ' + e.message));
  await page.goto(`http://127.0.0.1:${PORT}/?slot=test`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#loading.done', { timeout: 120000 });
  const made = [];
  // saved projects (read-only copies)
  const files = fs.existsSync(SAVES) ? fs.readdirSync(SAVES).filter(f => f.endsWith('.json')).slice(0, 5) : [];
  for (const f of files) {
    const proj = JSON.parse(fs.readFileSync(path.join(SAVES, f), 'utf8'));
    const baked = await page.evaluate(async p => JSON.stringify(await window.app.bakeOther(p)), proj);
    const id = 'saved_' + f.replace(/[^A-Za-z0-9]+/g, '_').replace(/_json$/, '');
    fs.writeFileSync(path.join(OUT, id + '.baked.json'), baked);
    made.push(id);
  }
  // Magic-made projects
  for (const recipe of ['cowgirl', 'missionary', 'doggy', 'bj']) {
    const baked = await page.evaluate(async recipe => {
      const m = await import('/js/magic.js');
      Math.random = (() => { let s = 12345; return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; })();
      const ok = await m.makeMagic(window.app, { recipe, place: recipe === 'bj' ? 'floor' : 'double_bed', seconds: 3, name: 'R1F ' + recipe, author: 'R1F test' });
      if (!ok) return null;
      window.app.setPlaying(false);
      window.app.showcase?.(false);
      const b = window.app.bake();
      b.uid = 'r1f-fixture-' + recipe;       // a fixed uid: the same package name every run
      return JSON.stringify(b);
    }, recipe);
    if (!baked) { console.error('magic failed', recipe); continue; }
    fs.writeFileSync(path.join(OUT, 'magic_' + recipe + '.baked.json'), baked);
    made.push('magic_' + recipe);
  }
  console.log(JSON.stringify({ made, errors: logs.slice(0, 10) }));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
