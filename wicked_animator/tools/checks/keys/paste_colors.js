// Pasting keys goes back onto the sim they came from, and each sim's colour follows its body (Playwright, no game).
//   node tools/checks/keys/paste_colors.js [--port 8921]
// Starts tools/checks/lib/fake_game_server.py, opens the app on the couple and checks:
//   - a female's key copied with Ctrl+C and pasted with Ctrl+V lands on her again, even with the male selected
//   - "Paste Female 1's keys onto Male 1" (right-click his row) is the one way to put them on him
//   - colours: female pink, male blue, female with penis purple, whatever order they were added in; a second female
//     gets a colour none of those use; changing a body recolours it; a colour picked by hand stays (also after a load)
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');
const P = require('../lib/pw.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const PORT = +(argv[argv.indexOf('--port') + 1] || 0) || 8921;
const get = url => new Promise(res => { http.get(url, r => { let b = ''; r.on('data', c => { b += c; }); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', () => res(null)); });
const PINK = '#ff4f9a', BLUE = '#57b8ff', PURPLE = '#a78bfa';

(async () => {
  if (await get(`http://127.0.0.1:${PORT}/api/status`)) throw new Error(`port ${PORT} is already in use - pass --port`);
  const proc = spawn(process.env.PYTHON || 'python3', [path.join(ROOT, 'tools', 'checks', 'lib', 'fake_game_server.py')], {
    cwd: ROOT, env: { ...process.env, ANIMATOR_PORT: String(PORT), PYTHONUNBUFFERED: '1' }, stdio: 'ignore' });
  for (let i = 0; i < 100 && !(await get(`http://127.0.0.1:${PORT}/api/status`)); i++) await P.sleep(200);
  const rows = [];
  let browser;
  const ok = (name, cond, detail) => rows.push({ name, ok: !!cond, detail });
  const step = async (name, fn) => { try { const r = await fn(); ok(name, r !== false, typeof r === 'string' ? r : undefined); } catch (e) { ok(name, false, (e && e.message || String(e)).split('\n')[0]); } };
  try {
    const o = await P.open(PORT, { scene: 'couple' });
    browser = o.browser;
    const { page, logs } = o;
    await page.waitForFunction(() => window.app && app.simViews.size >= 2, null, { timeout: 30000 });
    await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true })));
    await P.sleep(300);
    // lane y of sim row i, x of a frame, in page coordinates
    const at = (frame, row) => page.evaluate(([f, r]) => { const tl = app.timeline, b = tl.canvas.getBoundingClientRect(); return [b.left + tl.xAt(f), b.top + tl._y(r, 15)]; }, [frame, row]);
    const keysOf = () => page.evaluate(() => app.store.project.sims.map(s => ({ label: s.label, keys: s.keys.filter(k => !k.faceOnly).map(k => k.frame) })));

    await step('Ctrl+V puts a female\'s copied key back on her, even with the male selected', async () => {
      await page.evaluate(() => {
        const [F] = app.store.project.sims;
        app.selectSim(F.id); app.setFrame(20); app.keyPose(F.id);                     // her second key, at 20
      });
      await P.sleep(200);
      const [xk, yk] = await at(20, 0);
      await page.mouse.click(xk, yk); await P.sleep(120);                            // select her key
      await page.keyboard.press('Control+c'); await P.sleep(120);
      const [xm, ym] = await at(0, 1);
      await page.mouse.click(xm, ym); await P.sleep(120);                            // click his key: he is selected now
      const sel = await page.evaluate(() => app.store.sim().label);
      const [x40] = await at(40, 0);
      const ruler = await page.evaluate(() => app.timeline.canvas.getBoundingClientRect().top + 10);
      await page.mouse.click(x40, ruler); await P.sleep(120);
      await page.keyboard.press('Control+v'); await P.sleep(250);
      const k = await keysOf();
      if (!(sel === 'Male 1' && k[0].keys.includes(40) && !k[1].keys.includes(40))) throw new Error(JSON.stringify({ sel, k }));
      return `with ${sel} selected, the key went to ${k[0].label} (${k[0].keys.join(', ')}); ${k[1].label} keeps ${k[1].keys.join(', ')}`;
    });

    await step('right-click his row: "Paste Female 1\'s keys onto Male 1" puts them on him', async () => {
      const [x, y] = await at(60, 1);
      await page.mouse.click(x, y, { button: 'right' }); await P.sleep(250);
      const label = await page.evaluate(() => [...document.querySelectorAll('.ctx-menu button, .menu button, [role=menu] button, .ctx button')].map(b => b.innerText.trim()).find(t => /Paste .*keys/.test(t)) || null);
      if (!label) throw new Error('no paste item in the menu');
      await page.evaluate(t => { const b = [...document.querySelectorAll('button')].find(x => x.innerText.trim() === t); b && b.click(); }, label);
      await P.sleep(250);
      const k = await keysOf();
      if (!(label === "Paste Female 1's keys onto Male 1" && k[1].keys.includes(60))) throw new Error(JSON.stringify({ label, k }));
      return `"${label}" -> ${k[1].label} has a key at 60`;
    });

    await step('Ctrl+A selects every key, and a bar offers the sounds too; they then move with the keys', async () => {
      await page.evaluate(() => { const s = app.store.project.sims[0]; s.sounds = [{ frame: 10, name: 'WET_PL_1', kind: 'wet', auto: false }]; app.timeline.draw(); });
      const [x, y] = await at(0, 0);
      await page.mouse.click(x, y); await P.sleep(120);                              // focus the timeline
      await page.keyboard.press('Control+a'); await P.sleep(250);
      const bar = await page.evaluate(() => { const b = document.querySelector('.choice-bar'); return b ? { text: b.innerText, sel: app.timeline.sel.size } : null; });
      if (!bar) throw new Error('no bar after Ctrl+A');
      await page.evaluate(() => { const b = [...document.querySelectorAll('.choice-bar button')].find(x => /sound/.test(x.innerText)); b.click(); });
      await P.sleep(150);
      const r = await page.evaluate(async () => {
        const KO = await import('/js/keyops.js'), p = app.store.project;
        const sel = [...app.timeline.sel], hasSound = sel.some(id => id.startsWith('s|'));
        const keysBefore = p.sims.map(s => s.keys.map(k => k.frame));
        KO.moveSel(p, app.timeline.sel, 5);
        return { hasSound, count: sel.length, sound: p.sims[0].sounds[0].frame, keysBefore, keysAfter: p.sims.map(s => s.keys.map(k => k.frame)) };
      });
      if (!(/key/.test(bar.text) && r.hasSound && r.sound === 15 && r.keysAfter[0][0] === r.keysBefore[0][0] + 5)) throw new Error(JSON.stringify({ bar, r }));
      return `bar: "${bar.text.split('\n')[0]}"; after the button ${r.count} selected, sound moved 10 -> ${r.sound} with the keys`;
    });

    await step('colours follow the body, not the order: pink female, blue male, purple female with penis', async () => {
      const r = await page.evaluate(async () => {
        const { newProject } = await import('/js/state.js');
        const p = newProject();
        // an older save: the male first, coloured pink by his place in the list
        p.sims.push({ id: 'm', label: 'Male 1', frame: 'ym', gender: 'MALE', color: '#ff4f9a', keys: [{ frame: 0, ease: 'auto', pose: { rot: {}, pos: {} } }] });
        p.sims.push({ id: 'f', label: 'Female 1', frame: 'yf', gender: 'FEMALE', color: '#57b8ff', keys: [{ frame: 0, ease: 'auto', pose: { rot: {}, pos: {} } }] });
        app.store.load(p);
        const loaded = app.store.project.sims.map(s => [s.frame, s.color]);
        app.addSim('yf');                                                            // a second female
        app.addSim('yf_futa');
        const added = app.store.project.sims.map(s => [s.frame, s.color]);
        app.setSimBody('m', 'yf');                                                   // he becomes a female body
        const changed = app.store.sim('m').color;
        return { loaded, added, changed };
      });
      const c = Object.fromEntries(r.loaded);
      const second = r.added[2][1], futa = r.added[3][1];
      if (!(c.ym === BLUE && c.yf === PINK && ![PINK, BLUE, PURPLE].includes(second) && futa === PURPLE && r.changed !== BLUE && r.changed !== PINK))
        throw new Error(JSON.stringify(r));
      return `male ${c.ym}, female ${c.yf}, second female ${second}, female with penis ${futa}; a male turned female: ${r.changed}`;
    });

    await step('a colour picked by hand stays (also after saving and loading)', async () => {
      const r = await page.evaluate(() => {
        const s = app.store.project.sims[1];
        app.setColor(s.id, '#3ddc97');
        const copy = JSON.parse(JSON.stringify(app.store.project));
        app.store.load(copy);
        return { color: app.store.sim(s.id).color, picked: !!app.store.sim(s.id).colorPicked };
      });
      if (!(r.color === '#3ddc97' && r.picked)) throw new Error(JSON.stringify(r));
      return `kept ${r.color} after a load`;
    });

    const bad = P.problems(logs, { ignore: [/Failed to load resource/, /GPU stall|WebGL|swiftshader|GroupMarkerNotSet/i] });
    ok('no uncaught errors or console errors', !bad.length, bad.slice(0, 3).map(l => l.text.slice(0, 160)).join(' | ') || 'clean');
  } catch (e) {
    ok('the check ran to the end', false, e.stack || String(e));
  } finally {
    if (browser) await browser.close().catch(() => {});
    proc.kill();
  }
  const pass = P.report(rows, 'Paste onto the right sim, colours by body (Playwright, no game)');
  process.exit(pass ? 0 : 1);
})();
