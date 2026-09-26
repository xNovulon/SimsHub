// Furniture animation in the running app (Playwright, no game: the stand-in bed and chair).
//   node tools/checks/furnanim/furn_anim.js [--port 8875]
// Starts tools/checks/lib/fake_game_server.py, opens the app on the couple and checks:
//   - "Bed animation" shows for a bed (rows Bed / Blanket / Pillows on the timeline, the panel), "Chair animation" for a
//     chair, nothing for the floor
//   - the blanket by itself: pulled back to the foot, or covering the sims when they are under it (it rises over them)
//   - a pillow gives under a head
//   - by hand: dragging a blanket dot keys it at that frame (from the automatic movement), in between it blends
//   - the chair: Tip over ends lying on its back on the floor, Lift and throw arcs up and lands on the floor, all inside
//     the loop; a shorter loop cuts the keys; undo brings them back; the keys are saved with the animation
//   - the export: no bed clip for a chair or the stand-in bed; no console errors
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn } = require('child_process');
const P = require('../lib/pw.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const PORT = +(argv[argv.indexOf('--port') + 1] || 0) || 8875;
const OUT = path.join(ROOT, 'cache', 'checks', 'furnanim');
const get = url => new Promise(res => { http.get(url, r => { let b = ''; r.on('data', c => { b += c; }); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', () => res(null)); });

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  if (await get(`http://127.0.0.1:${PORT}/api/status`)) throw new Error(`port ${PORT} is already in use - pass --port`);
  const proc = spawn(process.env.PYTHON || 'python3', [path.join(ROOT, 'tools', 'checks', 'lib', 'fake_game_server.py')], {
    cwd: ROOT, env: { ...process.env, ANIMATOR_PORT: String(PORT), PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
  let log = ''; proc.stdout.on('data', d => { log += d; }); proc.stderr.on('data', d => { log += d; });
  for (let i = 0; i < 100 && !(await get(`http://127.0.0.1:${PORT}/api/status`)); i++) await P.sleep(200);
  const rows = [];
  let browser;
  const ok = (name, cond, detail) => rows.push({ name, ok: !!cond, detail });
  try {
    const o = await P.open(PORT, { scene: 'couple' });
    browser = o.browser;
    const { page, logs } = o;
    const step = async (name, fn) => {
      try { const r = await fn(); ok(name, r !== false, typeof r === 'string' ? r : undefined); }
      catch (e) { ok(name, false, (e && e.message || String(e)).split('\n')[0]); }
    };
    const shot = name => page.screenshot({ path: path.join(OUT, name + '.png') }).catch(() => {});
    await page.waitForFunction(() => window.app && window.app.simViews && window.app.simViews.size >= 2 && window.wickedFurnAnim, null, { timeout: 30000 });
    await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true })));
    await page.waitForFunction(() => document.getElementById('home').classList.contains('hidden'), null, { timeout: 10000 });
    await page.evaluate(() => {
      const app = window.app, A = window.wickedFurnAnim;
      window.__f = {
        btn: () => { const b = document.getElementById('btn-furn-anim'); return b ? { hidden: b.hidden, text: b.innerText.trim(), on: b.classList.contains('on') } : null; },
        rows: () => app.timeline.rows.filter(r => r.id.startsWith('furn-')).map(r => r.label),
        place: id => { app.setFurniture(id); },
        waitRig: () => new Promise(res => { const t0 = performance.now(); const tick = () => { app.applyPoses(false); const F = A.state; if (F.rig && (F.rig.bed || F.rig.def.kind !== 'bed')) res(true); else if (performance.now() - t0 > 8000) res(false); else setTimeout(tick, 100); }; tick(); }),
        // how far the vertices that follow a part's handles moved up, on average (the game bed or the stand-in)
        shift: (part, only) => {
          const bed = A.state.rig.bed, H = Object.keys(bed.handles[part]).filter(x => !only || x === only);
          let s = 0, n = 0;
          for (const M of bed.meshes) {
            const a = M.mesh.geometry.attributes.position.array;
            for (let v = 0; v < a.length / 3; v++) {
              let w = 0;
              for (let k = 0; k < 4; k++) { const mm = M.map[M.skin.idx[v * 4 + k]]; if (mm && (H.includes(mm.handle) || (mm.mean && mm.mean.some(x => H.includes(x))))) w += M.skin.w[v * 4 + k]; }
              if (w > 0.5) { s += a[v * 3 + 1] - M.base[v * 3 + 1]; n++; }
            }
          }
          return n ? s / n : 0;
        },
        real: () => !!(A.state.rig && A.state.rig.bed && A.state.rig.bed.real),
        root: () => { const g = A.state.rig.g; return { p: g.position.toArray(), q: g.quaternion.toArray() }; },
      };
    });
    // three's Box3 for measuring (from the loaded module)
    await page.evaluate(async () => { const T = await import('three'); window.__T = T; });
    const lowestNow = () => page.evaluate(() => { const T = window.__T, g = window.wickedFurnAnim.state.rig.g; g.updateMatrixWorld(true); const b = new T.Box3().setFromObject(g); return { min: b.min.y, max: b.max.y }; });

    await step('nothing for the floor; "Bed animation" for a bed', async () => {
      const floor = await page.evaluate(() => { window.__f.place('floor'); return window.__f.btn(); });
      const bed = await page.evaluate(() => { window.__f.place('double_bed'); return window.__f.btn(); });
      if (!floor || !floor.hidden || !bed || bed.hidden || bed.text !== 'Bed animation') throw new Error(JSON.stringify({ floor, bed }));
      return `floor: hidden, bed: "${bed.text}"`;
    });
    await step('opening it: rows Bed / Blanket / Pillows on the timeline and the panel', async () => {
      await page.click('#btn-furn-anim');
      const ok2 = await page.evaluate(() => window.__f.waitRig());
      const r = await page.evaluate(() => ({ rows: window.__f.rows(), card: !document.querySelector('.fa-card').hidden, text: document.querySelector('.fa-card').innerText, double: window.wickedFurnAnim.state.rig.bed && window.wickedFurnAnim.state.rig.bed.double,
        handles: window.wickedFurnAnim.state.rig.bed && Object.keys(window.wickedFurnAnim.state.rig.bed.handles.blanket) }));
      await shot('bed_open');
      if (!ok2 || r.rows.join() !== 'Bed,Blanket · automatic,Pillows · automatic' || !r.card || !/Bed animation/.test(r.text) || /null|undefined/.test(r.text) || !r.double || r.handles.length !== 6) throw new Error(JSON.stringify(r));
      return `${r.rows.join(' | ')}; ${r.handles.length} blanket handles`;
    });
    await step('the blanket by itself: pulled back to the foot, or over the sims when they are under it', async () => {
      const r = await page.evaluate(() => {
        const app = window.app, A = window.wickedFurnAnim;
        A.select('blanket');
        app.applyPoses(false);
        const pulled = window.__f.shift('blanket');
        const head = app.store.project.furnAnim.parts.blanket;
        A.setUnder(true);
        app.applyPoses(false);
        const under = window.__f.shift('blanket');
        const tags = app.store.project.tags || [];
        return { pulled, under, tag: tags.includes('UNDER_COVERS'), mode: head.mode, real: window.__f.real() };
      });
      await shot('blanket_under');
      // the couple stands in the middle of the bed: under the blanket it rises over them
      if (!(r.under > r.pulled + 0.1 && r.tag && r.mode === 'auto')) throw new Error(JSON.stringify(r));
      return `${r.real ? 'the game bed' : 'the stand-in bed'}: blanket up ${(r.pulled * 100).toFixed(1)} cm pulled back -> ${(r.under * 100).toFixed(1)} cm over the sims; UNDER_COVERS tag set`;
    });
    await step('by hand: dragging a blanket dot keys it at that frame, starting from the automatic movement', async () => {
      const r = await page.evaluate(() => {
        const app = window.app, A = window.wickedFurnAnim, F = A.state, gz = app.vp.gizmo;
        app.setFrame(30);
        A.select('blanket', 'headL');
        const before = F.proxy.position.y;
        gz.dispatchEvent({ type: 'mouseDown' });
        F.proxy.position.y += 0.2; F.proxy.updateMatrixWorld();
        gz.dispatchEvent({ type: 'objectChange' });
        gz.dispatchEvent({ type: 'mouseUp' });
        const pt = app.store.project.furnAnim.parts.blanket;
        const k30 = pt.keys.find(k => k.f === 30);
        return { mode: pt.mode, keys: pt.keys.length, lift: k30 && k30.v.headL[1], before, dots: F.dots.visible };
      });
      if (!(r.mode === 'hand' && r.keys > 5 && r.lift > 0.15 && r.dots)) throw new Error(JSON.stringify(r));
      return `by hand: ${r.keys} keys (the automatic movement), the dragged one lifted ${r.lift.toFixed(2)} m`;
    });
    await step('a pillow gives under a head (automatic)', async () => {
      const r = await page.evaluate(() => {
        const app = window.app, A = window.wickedFurnAnim, F = A.state, T = window.__T;
        A.select('pillows');
        const bed = F.rig.bed, pl = bed.handles.pillows.left, g = F.rig.g;
        // a head just above the left pillow: move the first sim so its head is there
        const s = app.store.project.sims[0], v = app.simViews.get(s.id);
        const head = v.worldPos('b__Head__', new T.Vector3()), want = g.localToWorld(pl.clone().add(new T.Vector3(0, 0.12, 0)));
        app.interact.placeSim(s.id, { move: want.clone().sub(head) });
        app.applyPoses(false);
        return { dy: window.__f.shift('pillows', 'left') };
      });
      if (!(r.dy < -0.02)) throw new Error(JSON.stringify(r));
      return `the left pillow sank ${(-r.dy * 100).toFixed(1)} cm under the head`;
    });
    await step('the single bed: one pillow, three blanket handles, the blanket covers the sims too', async () => {
      const r = await page.evaluate(async () => {
        const app = window.app, A = window.wickedFurnAnim;
        window.__f.place('single_bed');
        await window.__f.waitRig();
        const bed = A.state.rig.bed;
        A.select('blanket');
        app.applyPoses(false);
        return { real: bed.real, double: bed.double, blanket: Object.keys(bed.handles.blanket), pillows: Object.keys(bed.handles.pillows), up: window.__f.shift('blanket'), rows: window.__f.rows() };
      });
      await shot('single_bed');
      if (!(r.double === false && r.blanket.join() === 'head,middle,foot' && r.pillows.join() === 'pillow' && r.up > 0.1 && r.rows.length === 3)) throw new Error(JSON.stringify(r));
      return `${r.real ? 'the game bed' : 'the stand-in'}: handles ${r.blanket.join('/')} + ${r.pillows.join()}; the blanket is up ${(r.up * 100).toFixed(1)} cm over the sims`;
    });
    await step('"Couch animation" for a couch', async () => {
      const r = await page.evaluate(async () => { window.__f.place('sofa'); await window.__f.waitRig(); return { btn: window.__f.btn(), rows: window.__f.rows() }; });
      if (!(r.btn && !r.btn.hidden && r.btn.text === 'Couch animation' && r.rows.join() === 'Couch')) throw new Error(JSON.stringify(r));
      return `"${r.btn.text}", row: ${r.rows.join()}`;
    });
    await step('"Chair animation" for a chair: one row; Tip over ends on its back, on the floor, inside the loop', async () => {
      const r = await page.evaluate(async () => {
        const app = window.app, A = window.wickedFurnAnim;
        window.__f.place('chair_dining');
        await window.__f.waitRig();
        const btn = window.__f.btn(), rowsNow = window.__f.rows();
        app.setFrame(10);
        A.tipOver('back');
        const keys = app.store.project.furnAnim.parts.object.keys;
        const last = keys[keys.length - 1];
        app.setFrame(last.f);
        return { btn, rowsNow, n: keys.length, first: keys[0].f, lastF: last.f, len: app.store.project.length, q: window.__f.root().q };
      });
      const lo = await lowestNow();
      const ang = 2 * Math.acos(Math.min(1, Math.abs(r.q[3]))) * 180 / Math.PI;
      await shot('chair_tipped');
      if (!(r.btn.text === 'Chair animation' && r.rowsNow.join() === 'Chair' && r.first === 10 && r.lastF < r.len && Math.abs(ang - 90) < 3 && Math.abs(lo.min) < 0.03)) throw new Error(JSON.stringify({ ...r, ang, lo }));
      return `${r.n} keys, frames ${r.first}-${r.lastF}; ends turned ${ang.toFixed(1)}°, lowest point ${(lo.min * 100).toFixed(1)} cm`;
    });
    await step('Lift and throw: up, an arc forward, lands on the floor', async () => {
      const r = await page.evaluate(() => {
        const app = window.app, A = window.wickedFurnAnim;
        app.store.project.furnAnim.parts.object.keys = [];
        app.setFrame(5);
        A.liftAndThrow();
        const keys = app.store.project.furnAnim.parts.object.keys;
        const ys = keys.map(k => k.v.root[1]), zs = keys.map(k => Math.hypot(k.v.root[0], k.v.root[2]));
        const last = keys[keys.length - 1];
        app.setFrame(last.f);
        return { n: keys.length, top: Math.max(...ys), far: zs[zs.length - 1], lastF: last.f, len: app.store.project.length };
      });
      const lo = await lowestNow();
      await shot('chair_thrown');
      if (!(r.top > 0.55 && r.far > 1.4 && r.lastF < r.len && Math.abs(lo.min) < 0.04)) throw new Error(JSON.stringify({ ...r, lo }));
      return `${r.n} keys: up ${r.top.toFixed(2)} m, lands ${r.far.toFixed(2)} m away on the floor (${(lo.min * 100).toFixed(1)} cm)`;
    });
    await step('a shorter loop cuts the keys; undo brings them back', async () => {
      const r = await page.evaluate(() => {
        const app = window.app;
        const before = app.store.project.furnAnim.parts.object.keys.length;
        app.setLength(20, 'cut');
        const cut = app.store.project.furnAnim.parts.object.keys;
        const allIn = cut.every(k => k.f < 20);
        app.undo();
        return { before, after: cut.length, allIn, back: app.store.project.furnAnim.parts.object.keys.length, len: app.store.project.length };
      });
      if (!(r.allIn && r.after < r.before && r.back === r.before)) throw new Error(JSON.stringify(r));
      return `${r.before} keys -> ${r.after} in a 20-frame loop -> ${r.back} after undo`;
    });
    await step('the keys are saved with the animation (and load back)', async () => {
      const r = await page.evaluate(() => {
        const app = window.app;
        const copy = JSON.parse(JSON.stringify(app.store.project));
        app.store.load(copy);
        app.refreshAll && app.refreshAll();
        const fa = app.store.project.furnAnim;
        return { keys: fa && fa.parts.object.keys.length, blanket: fa && fa.parts.blanket.keys.length, mode: fa && fa.parts.blanket.mode };
      });
      if (!(r.keys > 5 && r.blanket > 5 && r.mode === 'hand')) throw new Error(JSON.stringify(r));
      return `object ${r.keys} keys, blanket ${r.blanket} keys (by hand) after loading`;
    });
    await step('the export: no bed clip for a chair or the stand-in bed', async () => {
      const r = await page.evaluate(async () => {
        const app = window.app;
        const chair = app.bake();
        window.__f.place('double_bed'); await window.__f.waitRig();
        const bed = app.bake(), b = bed.bedAnim;
        return { chair: !!chair.bedAnim, bed: !!b, frames: bed.frames, real: window.__f.real(), n: b && b.frames.length, width: b && b.frames[0].length,
          bones: b && b.bones.length, names: b && b.bones.join(',') };
      });
      // the game bed (when this PC has it cached): its blanket and pillow bones, one row per frame; the stand-in: none
      const good = !r.chair && (r.real ? r.bed && r.n === r.frames && r.width === r.bones * 7 && r.bones >= 10 && /_bind_DB_blanket_Top_L_/.test(r.names) : !r.bed);
      if (!good) throw new Error(JSON.stringify(r));
      return r.real ? `the game bed: ${r.bones} bones x ${r.n} frames; a chair: none` : 'none (the stand-in bed has no game bones)';
    });
    const expected = [/Failed to load resource/, /GPU stall|WebGL|swiftshader|GroupMarkerNotSet/i, /fonts\.googleapis/];
    const bad = P.problems(logs, { ignore: expected });
    ok('no uncaught errors, failed module loads or console errors', !bad.length, bad.slice(0, 5).map(l => `${l.type}: ${l.text.slice(0, 200)}`).join(' | ') || 'clean');
  } catch (e) {
    ok('the check ran to the end', false, (e.stack || String(e)) + '\n' + log.slice(-600));
  } finally {
    if (browser) await browser.close().catch(() => {});
    proc.kill();
  }
  const pass = P.report(rows, 'Furniture animation (Playwright, no game)');
  process.exit(pass ? 0 : 1);
})();
