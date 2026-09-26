// "The Sims 4 wasn't found" and Find The Sims 4, in the running app (Playwright, no game).
//   node tools/checks/findgame/find_game.js [--port 8874]
// Starts tools/checks/lib/fake_game_server.py with WA_FAKE_NO_GAME=1 (the engine finds no game - also on a PC that
// has one) and WA_FAKE_FRESH=1 (the game never started: no Tray or Mods folder) and a made-up install in a temp folder (Data\Client\ClientFullBuild0.package, Game\Bin\TS4_x64.exe), then:
//   - the start stops on "The Sims 4 wasn't found" with Find The Sims 4 (not "Could not start")
//   - Look again says it is still not found
//   - Find The Sims 4 lists the drives; a pasted folder opens, its Sims 4 folder is marked and Select takes it
//   - the start then finishes (Home), and Home says to start the game once (no Documents\...\The Sims 4 yet)
//   - the Tray dialog says the same when there is no Tray folder
//   - "The Sims 4 folder" (command menu) shows the picked folder
//   - a folder that isn't the game is refused with a plain message; no console errors
const path = require('path');
const fs = require('fs');
const os = require('os');
const http = require('http');
const { spawn } = require('child_process');
const P = require('../lib/pw.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const PORT = +(argv[argv.indexOf('--port') + 1] || 0) || 8874;
const OUT = path.join(ROOT, 'cache', 'checks', 'findgame');

const get = url => new Promise(res => {
  http.get(url, r => { let b = ''; r.on('data', c => { b += c; }); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', () => res(null));
});

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  // a made-up install: what the engine checks for
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'wa_findgame_'));
  const game = path.join(tmp, 'Games', 'The Sims 4');
  fs.mkdirSync(path.join(game, 'Data', 'Client'), { recursive: true });
  fs.mkdirSync(path.join(game, 'Game', 'Bin'), { recursive: true });
  fs.writeFileSync(path.join(game, 'Data', 'Client', 'ClientFullBuild0.package'), '');
  fs.writeFileSync(path.join(game, 'Game', 'Bin', 'TS4_x64.exe'), '');
  fs.mkdirSync(path.join(tmp, 'Games', 'Other'), { recursive: true });

  if (await get(`http://127.0.0.1:${PORT}/api/status`)) throw new Error(`port ${PORT} is already in use - pass --port`);
  const proc = spawn(process.env.PYTHON || 'python3', [path.join(ROOT, 'tools', 'checks', 'lib', 'fake_game_server.py')], {
    cwd: ROOT, env: { ...process.env, ANIMATOR_PORT: String(PORT), PYTHONUNBUFFERED: '1', WA_FAKE_NO_GAME: '1', WA_FAKE_FRESH: '1', WA_FAKE_HOME: path.join(tmp, 'home') },
    stdio: ['ignore', 'pipe', 'pipe'] });
  let log = '';
  proc.stdout.on('data', d => { log += d; });
  proc.stderr.on('data', d => { log += d; });
  for (let i = 0; i < 100 && !(await get(`http://127.0.0.1:${PORT}/api/status`)); i++) await P.sleep(200);

  const rows = [];
  let browser;
  const ok = (name, cond, detail) => rows.push({ name, ok: !!cond, detail });
  try {
    const o = await P.open(PORT, { timeout: 20000 });
    browser = o.browser;
    const { page, logs } = o;
    const step = async (name, fn) => {
      try { const r = await fn(); ok(name, r !== false, typeof r === 'string' ? r : undefined); }
      catch (e) { ok(name, false, (e && e.message || String(e)).split('\n')[0]); }
    };
    const shot = name => page.screenshot({ path: path.join(OUT, name + '.png') }).catch(() => {});

    await step('the start stops on "The Sims 4 wasn\'t found" with Find The Sims 4', async () => {
      await page.waitForSelector('.need-game-card', { timeout: 20000 });
      const t = await page.$eval('.need-game-card', e => e.innerText);
      const failed = await page.evaluate(() => /Could not start/.test(document.getElementById('loading').innerText));
      await shot('not_found');
      if (!/The Sims 4 wasn't found/.test(t) || !/Find The Sims 4/.test(t) || failed) throw new Error(t);
      return t.split('\n')[0];
    });
    await step('Look again: still not found', async () => {
      await page.click('.need-game-card button:has-text("Look again")');
      await page.waitForFunction(() => /Still not found/.test(document.querySelector('.need-game-card').innerText), null, { timeout: 8000 });
      return 'says so';
    });
    await step('Find The Sims 4: the drives, then a pasted folder with its Sims 4 folder marked', async () => {
      await page.click('.need-game-card button:has-text("Find The Sims 4")');
      await page.waitForSelector('.gfind .gfind-list button.gfind-row', { timeout: 8000 });
      const drives = await page.$$eval('.gfind .gfind-list button.gfind-row', b => b.map(x => x.innerText.trim()));
      await page.fill('.gfind-path', path.join(tmp, 'Games'));
      await page.press('.gfind-path', 'Enter');
      await page.waitForSelector('.gfind-row.game', { timeout: 8000 });
      const rowsText = await page.$$eval('.gfind-row', r => r.map(x => x.innerText.replace(/\s+/g, ' ').trim()));
      await shot('finder');
      if (!drives.length || !rowsText.some(x => /The Sims 4.*The Sims 4.*Select/.test(x)) || !rowsText.some(x => /^Other$/.test(x))) throw new Error(JSON.stringify({ drives, rowsText }));
      return `${drives.length} drive(s); ${rowsText.join(' | ')}`;
    });
    await step('a folder that isn\'t the game is refused with a plain message', async () => {
      const r = await page.evaluate(async p => { const res = await fetch('/api/game_dir', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: p }) }); return { s: res.status, b: await res.json() }; }, path.join(tmp, 'Games', 'Other'));
      if (r.s !== 400 || !/isn't The Sims 4/.test(r.b.message)) throw new Error(JSON.stringify(r));
      return r.b.message;
    });
    await step('Select: the start finishes and Home opens', async () => {
      await page.click('.gfind-row.game button:has-text("Select")');
      await page.waitForSelector('#loading.done', { state: 'attached', timeout: 60000 });
      await page.waitForSelector('#home:not(.hidden) .home-top', { timeout: 20000 });
      const gone = await page.evaluate(() => !document.querySelector('.need-game-card'));
      if (!gone) throw new Error('the card stayed');
      return 'started';
    });
    await step('Home: start The Sims 4 once (no Tray or Mods folder yet)', async () => {
      await page.waitForSelector('#home .home-note', { timeout: 8000 });
      const t = await page.$eval('#home .home-note', e => e.innerText);
      await shot('home_note');
      if (!/Start The Sims 4 once/.test(t)) throw new Error(t);
      return t;
    });
    await step('the Tray dialog says the same when there is no Tray folder', async () => {
      await page.evaluate(() => import('/js/dialogs/tray.js').then(m => m.openTrayDialog(window.app)));
      await page.waitForFunction(() => /Start The Sims 4 once/.test(document.querySelector('#modal-root')?.innerText || ''), null, { timeout: 8000 });
      const t = await page.$eval('#modal-root .empty', e => e.innerText);
      await page.keyboard.press('Escape');
      return t;
    });
    await step('"The Sims 4 folder" in the command menu shows the picked folder', async () => {
      await page.evaluate(async () => { const m = await import('/js/commands.js'); const c = m.allCommands(window.app).find(x => x.id === 'game-folder'); await c.run(); });
      await page.waitForFunction(() => /Picked by you/.test(document.querySelector('#modal-root')?.innerText || ''), null, { timeout: 8000 });
      const t = await page.$eval('#modal-root .gfind-game', e => e.innerText.replace(/\s+/g, ' '));
      await shot('folder_dialog');
      await page.keyboard.press('Escape');
      if (!t.includes(game)) throw new Error(t);
      return t;
    });
    const expected = [/Failed to load resource/, /GPU stall|WebGL|swiftshader|GroupMarkerNotSet/i, /fonts\.googleapis/, /never became ready/];
    const bad = P.problems(logs, { ignore: expected });
    ok('no uncaught errors, failed module loads or console errors', !bad.length, bad.slice(0, 5).map(l => `${l.type}: ${l.text.slice(0, 200)}`).join(' | ') || 'clean');
  } catch (e) {
    ok('the check ran to the end', false, (e.stack || String(e)) + '\n' + log.slice(-800));
  } finally {
    if (browser) await browser.close().catch(() => {});
    proc.kill();
  }
  const pass = P.report(rows, '"The Sims 4 wasn\'t found" and Find The Sims 4 (Playwright, no game)');
  process.exit(pass ? 0 : 1);
})();
