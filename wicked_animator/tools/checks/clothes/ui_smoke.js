// The Clothes control in the running app (Playwright, no game needed), with SYNTHETIC stand-in parts.
//   node tools/checks/clothes/ui_smoke.js [--port 8871] [--keep]
// Starts tools/checks/clothes/clothes_server.py (fake_game_server.py + tubes around the stand-in rig's chest, hips and
// feet read by the real clothes.py through /api/clothes_*), opens the app and checks: the plug-in and its view button,
// the Body step's Clothes row (None / basic outfits / a Tray sim's outfits by category), parts skinned to the skeleton
// and following a pose, the "hide clothes" toggle, an undress moment hiding the top only after its time, parts that
// are not installed or painted on the skin named in the note, Fast mode, undo, and the export staying the same with
// and without clothes. Writing routes are answered in the browser (pw.js). Fails on any console error.
// Chromium: PLAYWRIGHT_BROWSERS_PATH or the default; three.js: WA_THREE_DIR (a local copy for PCs without the CDN).
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn } = require('child_process');
const P = require('../lib/pw.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const PORT = +(argv[argv.indexOf('--port') + 1] || 0) || 8871;
const KEEP = argv.includes('--keep');
const OUT = path.join(ROOT, 'cache', 'checks', 'clothes');

const get = url => new Promise(res => {
  http.get(url, r => { let b = ''; r.on('data', c => { b += c; }); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', () => res(null));
});

async function startServer() {
  if (await get(`http://127.0.0.1:${PORT}/api/status`)) throw new Error(`port ${PORT} is already in use - pass --port`);
  const proc = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'clothes_server.py')], {
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
  throw new Error('the clothes server did not start:\n' + log);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const server = await startServer();
  const rows = [];
  let browser;
  const ok = (name, cond, detail) => rows.push({ name, ok: !!cond, detail });
  try {
    const o = await P.open(PORT, { scene: 'couple' });
    browser = o.browser;
    const { page, logs } = o;
    const bad = [];
    page.on('response', r => { if (r.status() >= 400 && !/favicon|fonts\.g/.test(r.url())) bad.push(`${r.status()} ${r.url().replace(/^https?:\/\/[^/]+/, '')}`); });
    const step = async (name, fn) => {
      try { const r = await fn(); ok(name, r !== false, typeof r === 'string' ? r : undefined); }
      catch (e) { ok(name, false, (e && e.message || String(e)).split('\n')[0]); }
    };
    const shot = name => page.screenshot({ path: path.join(OUT, name + '.png') }).catch(() => {});
    // what the selected sim's view wears: [{kind, visible, verts, maxBone, bones}]
    const worn = (simId = null) => page.evaluate(id => {
      const app = window.app, sid = id || app.store.selected.sim, v = app.simViews.get(sid);
      return ((v && v.parts) || []).filter(m => m.userData.role === 'clothes').map(m => {
        const si = m.geometry.attributes.skinIndex;
        let max = 0; for (let k = 0; k < si.array.length; k++) max = Math.max(max, si.array[k]);
        return { kind: m.userData.kind, visible: m.visible, verts: m.geometry.attributes.position.count, maxBone: max, bones: v.bones.length, map: !!m.material.map };
      });
    }, simId);
    const waitWorn = (n, ms = 10000) => page.waitForFunction(k => {
      const app = window.app, v = app.simViews.get(app.store.selected.sim);
      const count = v ? (v.parts || []).filter(m => m.userData.role === 'clothes').length : -1;
      return count === k && (k === 0 || (v.clothesInfo && !v.clothesInfo.loading));
    }, n, { timeout: ms }).catch(async () => {
      const st = await page.evaluate(() => { const app = window.app, s = app.store.sim(), v = app.simViews.get(s.id);
        return { clothes: s.clothes, key: v.clothesKey, info: v.clothesInfo, parts: (v.parts || []).map(m => m.userData.role + ':' + m.userData.kind) }; });
      throw new Error(`expected ${n} clothes parts: ${JSON.stringify(st)}`);
    });
    const bakeJson = () => page.evaluate(() => JSON.stringify(window.app.bake()));

    // ---------------------------------------------------------------- boot
    await step('the Clothes plug-in starts (script, style, view button)', async () => {
      const r = await page.evaluate(() => ({ g: !!window.wickedClothes, css: !!document.querySelector('link[data-feature="css/features/clothes.css"]'),
        btn: !!document.getElementById('btn-clothes'), set: typeof window.app.setClothes }));
      if (!r.g || !r.css || !r.btn || r.set !== 'function') throw new Error(JSON.stringify(r));
      return 'window.wickedClothes, clothes.css, #btn-clothes, app.setClothes';
    });
    let bakeBefore = null;
    await step('Body step: a Clothes row with None on and the basic outfits', async () => {
      await page.evaluate(async () => {
        const app = window.app, home = await import('/js/home.js');
        home.hideHome(app);
        const s = app.store.project.sims.find(x => x.frame === 'yf') || app.store.project.sims[0];
        app.selectSim(s.id); app.showStep('body');
      });
      bakeBefore = await bakeJson();
      await page.waitForSelector('.clothes-row.ready', { timeout: 30000 });
      const r = await page.evaluate(() => ({ chips: [...document.querySelectorAll('.clothes-row [data-clothes]')].map(b => b.dataset.clothes + (b.classList.contains('on') ? '*' : '')),
        text: document.querySelector('.clothes-row').innerText, after: document.querySelector('.clothes-row').previousElementSibling?.className || '' }));
      if (!r.chips.includes('none*') || !r.chips.includes('basic:casual') || !r.chips.includes('basic:underwear')) throw new Error(JSON.stringify(r));
      if (!/never go into the exported animation/.test(r.text)) throw new Error('no export note: ' + r.text);
      return `${r.chips.join(', ')} (after: ${r.after || 'start'})`;
    });
    await step('Casual: tee, jeans and sneakers on the skeleton, textured', async () => {
      await page.click('.clothes-row [data-clothes="basic:casual"]');
      await waitWorn(3);
      const w = await worn();
      if (w.map(x => x.kind).join() !== 'top,bottom,shoes' || w.some(x => !x.visible || !x.map || x.maxBone >= x.bones || x.verts < 16)) throw new Error(JSON.stringify(w));
      await page.waitForFunction(() => /3 of 3 pieces on/.test(document.querySelector('.clothes-row .pieces-head')?.innerText || ''), null, { timeout: 5000 });
      await shot('casual');
      return w.map(x => `${x.kind} ${x.verts} verts`).join(', ');
    });
    await step('the export is the same with and without clothes', async () => {
      const withClothes = await bakeJson();
      if (withClothes !== bakeBefore) throw new Error('the bake changed with clothes on');
      return `${withClothes.length} bytes, identical`;
    });
    await step('the clothes follow a pose (the chest bone turned moves the tee)', async () => {
      const r = await page.evaluate(async () => {
        const THREE = await import('three');
        const app = window.app, v = app.simViews.get(app.store.selected.sim);
        const tee = v.parts.find(m => m.userData.kind === 'top');
        const at = () => { v.group.updateMatrixWorld(true); tee.skeleton.update(); const p = new THREE.Vector3(); tee.getVertexPosition(20, p); return p.toArray(); };
        const a = at();
        const b = v.bone('b__Spine1__'); const q = b.quaternion.clone();
        b.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), 0.6));
        const c = at();
        b.quaternion.copy(q);
        return { a, c, moved: Math.hypot(a[0] - c[0], a[1] - c[1], a[2] - c[2]) };
      });
      if (!(r.moved > 0.02)) throw new Error(JSON.stringify(r));
      return `a top vertex moved ${(r.moved * 100).toFixed(1)} cm`;
    });
    await step('the view button hides and shows everyone\'s clothes', async () => {
      await page.click('#btn-clothes');
      const off = await worn();
      await page.click('#btn-clothes');
      const on = await worn();
      if (off.some(x => x.visible) || on.some(x => !x.visible)) throw new Error(JSON.stringify({ off, on }));
      return 'hidden, then shown again';
    });
    await step('an undress moment (top at frame 10) hides the tee from frame 10 on', async () => {
      const r = await page.evaluate(() => {
        const app = window.app, id = app.store.selected.sim;
        app.addMoment({ type: 'UNDRESS', frame: 10, sim: id, naked: 'TOP' });
        const vis = f => { app.setFrame(f); return window.app.simViews.get(id).parts.filter(m => m.userData.role === 'clothes').map(m => m.userData.kind + (m.visible ? '' : '(off)')).join(','); };
        return { f0: vis(0), f5: vis(5), f20: vis(20), back: vis(2) };
      });
      if (r.f0 !== 'top,bottom,shoes' || r.f5 !== 'top,bottom,shoes' || r.f20 !== 'top(off),bottom,shoes' || r.back !== 'top,bottom,shoes') throw new Error(JSON.stringify(r));
      await page.waitForFunction(() => /Undress moments take/.test(document.querySelector('.clothes-note')?.innerText || ''), null, { timeout: 5000 }).catch(() => {});
      return JSON.stringify(r);
    });
    await step('Fast mode renders with clothes on', async () => {
      await page.evaluate(() => window.app.vp.setQualityLevel(3));
      await P.sleep(400);
      await shot('fast_mode');
      const q = await page.evaluate(() => { const q = window.app.vp.quality; window.app.vp.setQualityLevel(0); return q; });
      if (q !== 'fast') throw new Error(q);
      return 'quality level 3 (fast), back to full';
    });
    await step('Undo brings the last choice back; None takes everything off', async () => {
      await page.click('.clothes-row [data-clothes="basic:underwear"]');
      await waitWorn(2);
      await page.evaluate(() => window.app.undo());
      await waitWorn(3);
      await page.click('.clothes-row [data-clothes="none"]');
      await waitWorn(0);
      const s = await page.evaluate(() => window.app.store.sim().clothes);
      if (s) throw new Error(JSON.stringify(s));
      return 'underwear (2) -> undo -> casual (3) -> none (0)';
    });

    // ---------------------------------------------------------------- a Tray sim's outfits
    let trayId = null;
    await step('a Tray sim: its outfits by category (bathing left out)', async () => {
      trayId = await page.evaluate(async () => { const app = window.app; await app.addTraySim('0x0000000000000001', 0, 'Test Sim'); app.showStep('body'); return app.store.selected.sim; });
      await page.waitForSelector('.clothes-row.ready', { timeout: 30000 });
      const chips = await page.evaluate(() => [...document.querySelectorAll('.clothes-row [data-clothes]')].map(b => b.dataset.clothes));
      const want = ['none', 'outfit:EVERYDAY:0', 'outfit:FORMAL:0', 'outfit:SWIMWEAR:0', 'basic:underwear', 'basic:casual'];
      if (JSON.stringify(chips) !== JSON.stringify(want)) throw new Error(chips.join(', '));
      return chips.join(', ');
    });
    await step('Everyday: 4 parts on the Tray body, the tights painted on the skin as in the game', async () => {
      await page.click('.clothes-row [data-clothes="outfit:EVERYDAY:0"]');
      await waitWorn(4);
      const w = await worn(trayId);
      // a piece the game paints on the skin is drawn into the sim's skin picture; only one that can't be is noted
      const info = await page.evaluate(() => { const app = window.app, v = app.simViews.get(app.store.selected.sim); return v.clothesInfo; });
      const note = await page.evaluate(() => document.querySelector('.clothes-row .clothes-note')?.innerText || '');
      if (w.map(x => x.kind).join() !== 'top,bottom,shoes,accessory' || info.painted.length || /painted on the skin/.test(note)) throw new Error(JSON.stringify({ w, info, note }));
      await shot('tray_everyday');
      return `${w.length} parts shown, the tights painted on the skin`;
    });
    // the picked part's tint and the hover glow show on what the sim wears, not only on the skin under it
    const tintOn = () => page.evaluate(() => {
      const app = window.app, v = app.simViews.get(app.store.selected.sim);
      return (v.parts || []).filter(m => m.userData.role === 'clothes').map(m => {
        const col = m.geometry.attributes.color, glow = m.geometry.attributes.glow;
        if (!col || !glow) return { kind: m.userData.kind, attrs: false };
        let tint = 0, lit = 0;
        for (let i = 0; i < col.count; i++) { tint += 1 - col.getY(i); lit += glow.getX(i); }
        return { kind: m.userData.kind, attrs: true, vc: !!m.material.vertexColors, tint: +tint.toFixed(2), lit: +lit.toFixed(2) };
      });
    });
    await step('the selection tint and hover glow reach the worn clothes', async () => {
      await page.evaluate(() => {
        const app = window.app, v = app.simViews.get(app.store.selected.sim);
        v.setPickMode('body');
        v.highlight(v.index('b__Pelvis__'), '#ff2255');
        v.hover(v.index('b__Pelvis__'));
      });
      await P.sleep(300);
      const t = await tintOn();
      const bottom = t.find(x => x.kind === 'bottom');
      if (!t.every(x => x.attrs && x.vc) || !bottom || !(bottom.tint > 1) || !(bottom.lit > 1)) throw new Error(JSON.stringify(t));
      await shot('tray_everyday_hips_picked');
      return t.map(x => `${x.kind}: tint ${x.tint}, glow ${x.lit}`).join('; ');
    });
    await step('clothes put on while a part is picked show its tint at once', async () => {
      await page.click('.clothes-row [data-clothes="basic:casual"]');
      await page.waitForFunction(() => { const app = window.app, v = app.simViews.get(app.store.selected.sim);
        return v.clothesInfo && !v.clothesInfo.loading && (v.parts || []).some(m => m.userData.role === 'clothes' && m.userData.kind === 'bottom'); }, null, { timeout: 10000 });
      const t = await tintOn();
      const bottom = t.find(x => x.kind === 'bottom');
      if (!bottom || !(bottom.tint > 1) || !(bottom.lit > 1)) throw new Error(JSON.stringify(t));
      return t.map(x => `${x.kind}: tint ${x.tint}, glow ${x.lit}`).join('; ');
    });
    await step('nothing picked: the clothes look as they did', async () => {
      await page.evaluate(() => { const app = window.app, v = app.simViews.get(app.store.selected.sim); v.highlight(-1); v.hover(-1); });
      await P.sleep(300);
      const t = await tintOn();
      if (!t.length || !t.every(x => x.tint === 0 && x.lit === 0)) throw new Error(JSON.stringify(t));
      await page.click('.clothes-row [data-clothes="outfit:EVERYDAY:0"]');
      await waitWorn(4);
      return 'no tint, no glow';
    });
    await step('Formal: the part that is not installed is named, the rest shows', async () => {
      await page.click('.clothes-row [data-clothes="outfit:FORMAL:0"]');
      await waitWorn(1);
      await page.waitForFunction(() => /1 piece isn't installed on this PC/.test(document.querySelector('.clothes-row .clothes-note')?.innerText || ''), null, { timeout: 5000 });
      const note = await page.evaluate(() => document.querySelector('.clothes-row .clothes-note').innerText);
      return note;
    });
    await step('the palette lists Clothes and Hide clothes', async () => {
      const ids = await page.evaluate(async () => { const m = await import('/js/commands.js'); return m.allCommands(window.app).map(c => c.id); });
      if (!ids.includes('clothes') || !ids.includes('hide-clothes')) throw new Error('missing');
      return 'clothes, hide-clothes';
    });
    await step('the choice is kept in the animation (sim.clothes), not in the export', async () => {
      const r = await page.evaluate(() => { const app = window.app; const s = app.store.sim(); const b = JSON.stringify(app.bake()); return { clothes: s.clothes, inBake: /clothes|FORMAL/.test(b) }; });
      if (!r.clothes || r.clothes.outfit !== 'FORMAL:0' || r.inBake) throw new Error(JSON.stringify(r));
      return JSON.stringify(r.clothes);
    });

    // ---------------------------------------------------------------- nothing broke
    const expected = [/Failed to load resource/, /GPU stall|WebGL|swiftshader|GroupMarkerNotSet/i, /fonts\.googleapis/];
    const errs = P.problems(logs, { ignore: expected });
    ok('no uncaught errors, failed module loads or console errors', !errs.length, errs.slice(0, 6).map(e => `${e.type}: ${e.text.slice(0, 200)}`).join(' | ') || 'clean');
    const missing = [...new Set(bad)].filter(x => /api\/clothes/.test(x));
    ok('no failed clothes requests', !missing.length, missing.slice(0, 8).join(' | ') || 'none');
  } catch (e) {
    ok('the check ran to the end', false, e.stack || String(e));
  } finally {
    if (browser && !KEEP) await browser.close();
    server.proc.kill();
  }
  const pass = P.report(rows, 'Clothes preview in the app (Playwright, synthetic parts, no game)');
  process.exit(pass ? 0 : 1);
})();
