// The Toilet in the Scene step's furniture (Playwright, no game).
//   node tools/checks/toilet/toilet.js [--port 8931] [--shot out.png]
// Starts tools/checks/lib/fake_game_server.py, opens the app on the ready-made couple and checks:
//   - the Scene step lists a Toilet next to the other furniture, and picking it offers the animation on TOILET
//   - the stage shows the game's real toilet (its meshes arrive from /api/furniture_mesh), not an empty stand-in
//   - the toilet has a seat, and "Sit here" puts a sim on it: hips at seat height (not on the tank or the floor)
//     and over the toilet's footprint
// Writing routes are answered in the browser (pw.js). Chromium: PLAYWRIGHT_BROWSERS_PATH or the default.
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');
const P = require('../lib/pw.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const arg = (k, d) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : d);
const PORT = +arg('--port', 8931);
const SHOT = arg('--shot', null);
const get = url => new Promise(res => { http.get(url, r => { let b = ''; r.on('data', c => { b += c; }); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', () => res(null)); });

(async () => {
  if (await get(`http://127.0.0.1:${PORT}/api/status`)) throw new Error(`port ${PORT} is already in use - pass --port`);
  const proc = spawn(process.env.PYTHON || 'python3', [path.join(ROOT, 'tools', 'checks', 'lib', 'fake_game_server.py')], {
    cwd: ROOT, env: { ...process.env, ANIMATOR_PORT: String(PORT), PYTHONUNBUFFERED: '1' }, stdio: 'ignore' });
  for (let i = 0; i < 100 && !(await get(`http://127.0.0.1:${PORT}/api/status`)); i++) await P.sleep(200);
  const rows = [];
  let browser;
  const ok = (name, cond, detail) => rows.push({ name, ok: !!cond, detail });
  try {
    const list = JSON.parse((await get(`http://127.0.0.1:${PORT}/api/furniture`)).body);
    const def = list.find(f => f.id === 'toilet');
    ok('the furniture list has a Toilet offered on TOILET', def && def.label === 'Toilet' && def.locations.join() === 'TOILET', JSON.stringify(def));
    const mesh = await get(`http://127.0.0.1:${PORT}/api/furniture_mesh?id=toilet`);
    ok('the real toilet object is served', mesh && mesh.status === 200 && /"meshes"/.test(mesh.body), mesh && mesh.status);

    const o = await P.open(PORT, { scene: 'couple' });
    browser = o.browser;
    const { page } = o;
    await page.waitForFunction(() => window.app && app.simViews && app.simViews.size >= 2, null, { timeout: 30000 });
    await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true })));
    await page.waitForFunction(() => document.getElementById('home').classList.contains('hidden'), null, { timeout: 10000 });
    await P.sleep(400);

    const r = await page.evaluate(async () => {
      const app = window.app;
      app.setStep && app.setStep('scene');
      await new Promise(res => setTimeout(res, 300));
      const btn = [...document.querySelectorAll('.furniture-grid .furn')].find(b => b.textContent.trim() === 'Toilet');
      if (!btn) return { btn: false };
      btn.click();
      for (let i = 0; i < 100; i++) {
        const info = app._furnInfoKnown && app._furnInfoKnown.get('toilet');
        if (info && info.meshes) break;
        await new Promise(res => setTimeout(res, 100));
      }
      const info = app._furnInfoKnown && app._furnInfoKnown.get('toilet');
      const PL = await import('/js/placing.js');
      const spots = info ? PL.spotsOf(info) : [];
      const seat = spots.find(s => s.action === 'sit');
      const sim = app.store.project.sims[0];
      let hips = null;
      if (seat) {
        PL.sitOn(app, sim, seat.slot, { frame: 0 });
        app.requestRender && app.requestRender();
        await new Promise(res => setTimeout(res, 500));
        const v = app.simViews.get(sim.id);
        const p = v.worldPos('b__Pelvis__');
        hips = [p.x, p.y, p.z];
      }
      let meshes = 0;
      (app.furnGroup || app.vp && app.vp.scene).traverse && (app.furnGroup || app.vp.scene).traverse(n => { if (n.isMesh && n.userData && n.userData.furniture !== false) meshes++; });
      return { btn: true, active: btn.classList.contains('active') || !!document.querySelector('.furniture-grid .furn.active'),
        furniture: app.store.project.furniture, locations: app.store.project.locations, hasMeshes: !!(info && info.meshes && info.meshes.length),
        bounds: info && info.bounds, spots: spots.map(s => s.action), hips };
    });
    ok('the Scene step shows a Toilet button', r.btn, JSON.stringify(r).slice(0, 200));
    ok('picking it makes the toilet the furniture, offered on TOILET', r.furniture === 'toilet' && (r.locations || []).includes('TOILET'), `${r.furniture} ${JSON.stringify(r.locations)}`);
    ok('the stage gets the game toilet (meshes, not a stand-in)', r.hasMeshes, JSON.stringify(r.bounds));
    ok('the toilet offers a seat to sit on', (r.spots || []).includes('sit'), JSON.stringify(r.spots));
    const b = r.bounds || { min: [-1, 0, -1], max: [1, 1, 1] };
    const h = r.hips && r.hips[1];
    ok('"Sit here" seats the sim: hips at seat height, over the toilet', r.hips && h > 0.3 && h < 0.75
      && r.hips[0] > b.min[0] - 0.25 && r.hips[0] < b.max[0] + 0.25 && r.hips[2] > b.min[2] - 0.35 && r.hips[2] < b.max[2] + 0.35,
      r.hips && r.hips.map(x => x.toFixed(2)).join(','));
    if (SHOT) await page.screenshot({ path: SHOT });
  } catch (e) {
    ok('run', false, (e && e.message || String(e)).split('\n')[0]);
  } finally {
    if (browser) await browser.close().catch(() => {});
    proc.kill();
  }
  for (const r of rows) console.log(`${r.ok ? 'PASS' : 'FAIL'} ${r.name}${r.detail && !r.ok ? '  -- ' + r.detail : r.detail ? '  (' + r.detail + ')' : ''}`);
  const bad = rows.filter(r => !r.ok).length;
  console.log(bad ? `\n${bad} FAILED` : `\nALL ${rows.length} PASS`);
  process.exit(bad ? 1 : 0);
})();
