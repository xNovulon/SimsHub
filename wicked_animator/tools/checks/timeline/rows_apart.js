// The ruler's key-summary diamonds and the Moments row ("right-click here to add cum, undressing, a condom coming
// off or an effect") used to share the bottom 9 px of a 28 px ruler with no gap at all - the owner: "I keep pressing
// on the 'right click here' thing and the dots under the numbers that move the keys around. Find a solution for
// that, maybe separate them." This check proves they are separated now: the key summary lives in its own row
// (Timeline._summaryRow, timeline.js), with real page.mouse clicks at the edges of each row.
//   node tools/checks/timeline/rows_apart.js [--port 8983]
// Fails on the old timeline.js (no dedicated row - the diamonds are still part of drawRuler) and passes on the new
// one. Ports 8976-8990 only (never 8765/8766/8777 - pw.js refuses those on its own). Starts the fake game server;
// never the real game, never a git command.
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn } = require('child_process');
const P = require('../lib/pw.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const PORT = +(argv[argv.indexOf('--port') + 1] || 0) || 8983;
const OUT = path.join(ROOT, 'cache', 'checks', 'timeline');

const get = url => new Promise(res => {
  http.get(url, r => { let b = ''; r.on('data', c => { b += c; }); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', () => res(null));
});

async function startServer() {
  if (await get(`http://127.0.0.1:${PORT}/api/status`)) throw new Error(`port ${PORT} is already in use - pass --port`);
  const proc = spawn(process.env.PYTHON || 'python3', [path.join(ROOT, 'tools', 'checks', 'lib', 'fake_game_server.py')], {
    cwd: ROOT, env: { ...process.env, ANIMATOR_PORT: String(PORT), PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
  let log = '';
  proc.stdout.on('data', d => { log += d; });
  proc.stderr.on('data', d => { log += d; });
  for (let i = 0; i < 100; i++) {
    const r = await get(`http://127.0.0.1:${PORT}/api/status`);
    if (r && r.status === 200) return { proc, log: () => log };
    await P.sleep(200);
  }
  proc.kill();
  throw new Error('the stand-in game server did not start:\n' + log);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const server = await startServer();
  const rows = [];
  let browser;
  const ok = (name, cond, detail) => rows.push({ name, ok: !!cond, detail });
  const step = async (name, fn) => {
    try { const r = await fn(); ok(name, r !== false, typeof r === 'string' ? r : undefined); return r; }
    catch (e) { ok(name, false, (e && e.message || String(e)).split('\n')[0]); return undefined; }
  };

  try {
    const o = await P.open(PORT, { w: 1366, h: 768, scene: 'couple' });
    browser = o.browser;
    const { page, logs } = o;
    await page.waitForFunction(() => window.app && window.app.simViews && window.app.simViews.size >= 2, null, { timeout: 30000 });
    await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true })));
    await page.waitForFunction(() => document.getElementById('home').classList.contains('hidden'), null, { timeout: 10000 });
    await P.sleep(400);

    // a key at frame 30 on both sims (so the summary diamond there is "every sim selected" white), a moment near
    // frame 60 (so the Moments row has real content, away from the diamond's x) - through the app's own methods.
    // Keying frame 30 fits the loop to 60 frames, so a moment asked for at 60 lands at 59 (frame < length) - the
    // moment's own `frame` is read back and used for every later click, never assumed.
    const momentFrame = await page.evaluate(() => {
      const app = window.app, sims = app.store.project.sims;
      for (const s of sims) { app.selectSim(s.id); app.setFrame(30); app.keyPose(s.id); }
      app.timeline.selectColumn(30);
      const m = app.addMoment({ type: 'NOTE', frame: 60, text: 'test moment' });
      app.timeline.fit();
      app.setFrame(0);
      return m.frame;
    });

    // ------------------------------------------------------------ geometry: a dedicated row for the key summary
    const geo = await step('the key summary is its own row, above the Moments row (not part of the ruler any more)', async () => {
      const g = await page.evaluate(() => {
        const tl = window.app.timeline;
        tl._layout();
        const moments = tl.rows.find(r => r.id === 'moments');
        const other = tl.rows.find(r => r.id !== 'moments');
        if (!other) return { rows: tl.rows.map(r => r.id), moments: moments && { top: tl._rowTop(moments), height: moments.height } };
        return {
          rows: tl.rows.map(r => r.id),
          summary: { id: other.id, top: tl._rowTop(other), height: other.height },
          moments: { top: tl._rowTop(moments), height: moments.height },
        };
      });
      if (!g.summary) throw new Error('no row besides "moments" - the key summary still lives inside the ruler: ' + JSON.stringify(g));
      if (!(g.summary.height >= 14)) throw new Error('the key-summary row is too thin to be a real lane: ' + JSON.stringify(g));
      if (!(g.summary.top + g.summary.height <= g.moments.top)) throw new Error('the key-summary row overlaps the Moments row: ' + JSON.stringify(g));
      return g;
    });

    if (geo && geo.summary) {
      const summaryY = geo.summary.top + geo.summary.height / 2;
      const momentsY = geo.moments.top + geo.moments.height / 2;

      // ------------------------------------------------------------ real mouse: a click on a diamond drags keys
      await step('a real drag started on the frame-30 diamond moves the whole column of keys', async () => {
        const g = await page.evaluate(y => {
          const tl = window.app.timeline, r = tl.canvas.getBoundingClientRect();
          return { x: r.left + tl.xAt(30), y: r.top + y, ppf: tl.pxPerFrame };
        }, summaryY);
        await page.mouse.move(g.x, g.y);
        await page.mouse.down();
        for (let i = 1; i <= 8; i++) { await page.mouse.move(g.x - i * 2 * g.ppf, g.y); await P.sleep(15); }
        await page.mouse.up();
        await P.sleep(120);
        const frames = await page.evaluate(() => window.app.store.project.sims.map(s => s.keys.map(k => k.frame).sort((a, b) => a - b).join(',')));
        const moved = frames.every(f => !f.split(',').includes('30') && f.split(',').some(x => x !== '0'));
        if (!moved) throw new Error('the column did not move: ' + JSON.stringify(frames));
        return `both sims' key at frame 30 moved together: ${frames.join(' | ')}`;
      });

      // put the moved keys back at frame 30 for the rest of the check (undo the drag)
      await page.evaluate(() => window.app.undo());
      await P.sleep(80);

      // ------------------------------------------------------------ real mouse: the same x, one row down, hits
      // nothing of the summary's (never drags a key) - the point of the fix
      await step('the same x, one row down (inside the Moments row, off its flag): dragging there never moves a key', async () => {
        const g = await page.evaluate(y => {
          const tl = window.app.timeline, r = tl.canvas.getBoundingClientRect();
          return { x: r.left + tl.xAt(30), y: r.top + y, ppf: tl.pxPerFrame };
        }, momentsY);
        const before = await page.evaluate(() => window.app.store.project.sims.map(s => s.keys.map(k => k.frame).sort((a, b) => a - b).join(',')));
        await page.mouse.move(g.x, g.y);
        await page.mouse.down();
        for (let i = 1; i <= 8; i++) { await page.mouse.move(g.x - i * 2 * g.ppf, g.y); await P.sleep(15); }
        await page.mouse.up();
        await P.sleep(120);
        const after = await page.evaluate(() => window.app.store.project.sims.map(s => s.keys.map(k => k.frame).sort((a, b) => a - b).join(',')));
        if (JSON.stringify(before) !== JSON.stringify(after)) throw new Error(`a key moved from the Moments row: ${JSON.stringify(before)} -> ${JSON.stringify(after)}`);
        return `keys unchanged (${after.join(' | ')})`;
      });

      // ------------------------------------------------------------ real mouse: right-click routes to the right menu
      await step('right-click on the diamond opens the ruler menu ("Select every key at frame 30"), never the Moments one', async () => {
        const g = await page.evaluate(y => {
          const tl = window.app.timeline, r = tl.canvas.getBoundingClientRect();
          return { x: r.left + tl.xAt(30), y: r.top + y };
        }, summaryY);
        await page.mouse.move(g.x, g.y);
        await page.mouse.click(g.x, g.y, { button: 'right' });
        await P.sleep(150);
        const labels = await page.evaluate(() => [...document.querySelectorAll('.ctx-menu button, .ctx-menu .ctx-label')].map(x => x.textContent.trim()));
        await page.keyboard.press('Escape');
        await P.sleep(80);
        if (!labels.some(l => /Select every key at frame 30/.test(l))) throw new Error('no "Select every key at frame 30": ' + JSON.stringify(labels));
        if (labels.some(l => /^Finish here/.test(l))) throw new Error('opened the Moments menu instead: ' + JSON.stringify(labels));
        return labels.join(' | ');
      });

      await step('right-click one row down (the Moments row, off any flag) opens its own menu ("Finish here…"), never the ruler one', async () => {
        const g = await page.evaluate(y => {
          const tl = window.app.timeline, r = tl.canvas.getBoundingClientRect();
          return { x: r.left + tl.xAt(30), y: r.top + y };
        }, momentsY);
        await page.mouse.move(g.x, g.y);
        await page.mouse.click(g.x, g.y, { button: 'right' });
        await P.sleep(150);
        const labels = await page.evaluate(() => [...document.querySelectorAll('.ctx-menu button, .ctx-menu .ctx-label')].map(x => x.textContent.trim()));
        await page.keyboard.press('Escape');
        await P.sleep(80);
        if (!labels.some(l => /^Finish here/.test(l))) throw new Error('no "Finish here…": ' + JSON.stringify(labels));
        if (labels.some(l => /Select every key at frame/.test(l))) throw new Error('opened the ruler menu instead: ' + JSON.stringify(labels));
        return labels.join(' | ');
      });

      // ------------------------------------------------------------ a right-click on the moment itself still works
      await step(`right-click exactly on the frame-${momentFrame} moment still opens its own item menu ("Change…")`, async () => {
        const g = await page.evaluate(({ y, frame }) => {
          const tl = window.app.timeline, r = tl.canvas.getBoundingClientRect();
          return { x: r.left + tl.xAt(frame) + 4, y: r.top + y };
        }, { y: momentsY, frame: momentFrame });
        await page.mouse.move(g.x, g.y);
        await page.mouse.click(g.x, g.y, { button: 'right' });
        await P.sleep(150);
        const labels = await page.evaluate(() => [...document.querySelectorAll('.ctx-menu button, .ctx-menu .ctx-label')].map(x => x.textContent.trim()));
        await page.keyboard.press('Escape');
        await P.sleep(80);
        if (!labels.some(l => /^Change…/.test(l))) throw new Error('no "Change…": ' + JSON.stringify(labels));
        return labels.join(' | ');
      });
    } else {
      ok('a real drag started on the frame-30 diamond moves the whole column of keys', false, 'skipped - no dedicated row to click');
      ok('the same x, one row down (inside the Moments row, off its flag): dragging there never moves a key', false, 'skipped - no dedicated row to click');
      ok('right-click on the diamond opens the ruler menu ("Select every key at frame 30"), never the Moments one', false, 'skipped - no dedicated row to click');
      ok('right-click one row down (the Moments row, off any flag) opens its own menu ("Finish here…"), never the ruler one', false, 'skipped - no dedicated row to click');
      ok(`right-click exactly on the frame-${momentFrame} moment still opens its own item menu ("Change…")`, false, 'skipped - no dedicated row to click');
    }

    // ------------------------------------------------------------ everything else on the timeline still works
    await step('scrubbing the ruler still sets the frame', async () => {
      const g = await page.evaluate(() => { const tl = window.app.timeline, r = tl.canvas.getBoundingClientRect(); return { x: r.left + tl.xAt(45), y: r.top + 12 }; });
      await page.mouse.click(g.x, g.y);
      await P.sleep(80);
      const f = await page.evaluate(() => Math.round(window.app.store.frame));
      if (f !== 45) throw new Error('frame is ' + f + ', wanted 45');
      return 'clicking the ruler at frame 45 set the frame to ' + f;
    });

    await step('Fit-to-keys room and two lanes still show at 1366x768', async () => {
      const g = await page.evaluate(() => {
        const tl = window.app.timeline;
        tl._layout();
        return { lane: tl.lane, n: window.app.store.project.sims.length, tlH: getComputedStyle(document.documentElement).getPropertyValue('--tl-h').trim() };
      });
      if (!(g.n === 2 && g.lane >= 40)) throw new Error('lanes too short for 2 sims: ' + JSON.stringify(g));
      return `2 sims, ${g.lane}px lanes, timeline height ${g.tlH}`;
    });

    const expected = [/Failed to load resource/, /GPU stall|WebGL|swiftshader|GroupMarkerNotSet/i, /fonts\.googleapis/];
    const bad = P.problems(logs, { ignore: expected });
    ok('no uncaught errors, failed module loads or console errors', !bad.length, bad.slice(0, 5).map(l => `${l.type}: ${l.text.slice(0, 200)}`).join(' | ') || 'clean');
  } catch (e) {
    ok('the check ran to the end', false, e.stack || String(e));
  } finally {
    if (browser) await browser.close().catch(() => {});
    server.proc.kill();
  }
  const pass = P.report(rows, 'The key summary and the Moments row are separate rows (Playwright, no game)');
  fs.writeFileSync(path.join(OUT, 'rows_apart_results.json'), JSON.stringify({ when: new Date().toISOString(), rows }, null, 1));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
