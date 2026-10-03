// Drags that always end and sims added next to each other (Playwright, no game).
//   node tools/checks/dragfix/drags_and_adding.js [--port 8961]
// Starts tools/checks/lib/fake_game_server.py, opens the app on the ready-made couple and checks:
//   - Female / Male / Female in the Scene step: each new sim stands 0.9 m beside the group (right, left, right...), never
//     on another one; every sim stays in view and the "Add a sim" buttons stay in sight
//   - each sim slides when its circle is dragged
//   - ring drags on the upper arm, the forearm and the thigh turn the part and stop the moment the button is let go
//   - the forearm has all three rings and rolls on its X ring (it turns any way, not only the elbow bend)
//   - a release the gizmo never hears about (the pointerup lost, the pointer cancelled) still ends the drag: the part
//     does not keep following the mouse - the same for a sim's circle
// Writing routes are answered in the browser (pw.js). Chromium: PLAYWRIGHT_BROWSERS_PATH or the default.
const http = require('http');
const { spawn } = require('child_process');
const path = require('path');
const P = require('../lib/pw.js');
const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const PORT = +(argv[argv.indexOf('--port') + 1] || 0) || 8961, LABEL = '';
const get = url => new Promise(res => { http.get(url, r => { let b = ''; r.on('data', c => { b += c; }); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', () => res(null)); });

(async () => {
  if (await get(`http://127.0.0.1:${PORT}/api/status`)) throw new Error(`port ${PORT} is already in use - pass --port`);
  const proc = spawn(process.env.PYTHON || 'python3', [path.join(ROOT, 'tools', 'checks', 'lib', 'fake_game_server.py')], {
    cwd: ROOT, env: { ...process.env, ANIMATOR_PORT: String(PORT), PYTHONUNBUFFERED: '1' }, stdio: 'ignore' });
  for (let i = 0; i < 100 && !(await get(`http://127.0.0.1:${PORT}/api/status`)); i++) await P.sleep(200);
  const rows = [];
  const say = (name, ok, detail) => { rows.push({ name, ok, detail }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? '  -  ' + detail : '')); };
  const o = await P.open(PORT, { scene: 'couple' });
  const { browser, page, logs } = o;
  try {
    await page.waitForFunction(() => window.app && app.simViews && app.simViews.size >= 2, null, { timeout: 60000 });
    await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true })));
    await page.waitForFunction(() => document.getElementById('home').classList.contains('hidden'), null, { timeout: 10000 });
    await P.sleep(600);
    await page.evaluate(() => {
      const app = window.app;
      window.__t = {
        ids: () => app.store.project.sims.map(s => s.id),
        wp: (bone, id) => { const p = app.simViews.get(id).worldPos(bone); return [+p.x.toFixed(3), +p.y.toFixed(3), +p.z.toFixed(3)]; },
        quat: (bone, id) => app.simViews.get(id).bone(bone).quaternion.toArray(),
        screen: w => { const V = app.vp.camera.position.constructor, p = new V(w[0], w[1], w[2]).project(app.vp.camera), r = app.vp.canvas.getBoundingClientRect(); return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; },
        pick: (id, bone) => { const s = app.store.sim(id); s.pins = {}; app.setTool('rotate'); app.store.selected = { sim: id, bone }; app.interact.selectBone(id, bone); app.emitSelection(); },
      };
    });
    await page.evaluate(async () => {
      const T = await import('three');
      window.__t.angleDeg = (a, b) => { const qa = new T.Quaternion(...a), qb = new T.Quaternion(...b); const d = Math.min(1, Math.abs(qa.x * qb.x + qa.y * qb.y + qa.z * qb.z + qa.w * qb.w)); return 2 * Math.acos(d) * 180 / Math.PI; };
    });
    const errs = () => logs.filter(l => (l.type === 'pageerror' || l.type === 'error') && !/Failed to load resource/.test(l.text)).map(l => l.text.split(/\r?\n/)[0]);

    // ---------------------------------------------------------------- 1. adding sims in the Scene step
    await page.evaluate(() => app.showStep('scene'));
    await P.sleep(400);
    const n0 = await page.evaluate(() => app.store.project.sims.length);
    const clickAdd = async label => { await page.locator('.add-tile', { hasText: new RegExp('^\\s*' + label + '\\s*$') }).first().click(); await P.sleep(1200); };
    const labels = ['Female', 'Male', 'Female'];
    for (const l of labels) await clickAdd(l);
    const pos = await page.evaluate(() => window.__t.ids().map(id => window.__t.wp('b__Pelvis__', id)));
    const xs = pos.map(p => p[0]).sort((a, b) => a - b);
    let minGap = Infinity; for (let i = 1; i < xs.length; i++) minGap = Math.min(minGap, xs[i] - xs[i - 1]);
    say(`add 3 sims: ${n0} -> ${pos.length} sims, none on top of another`, pos.length === n0 + 3 && minGap > 0.5, `x positions ${JSON.stringify(xs)} min gap ${minGap.toFixed(2)}`);
    const view = await page.evaluate(() => {
      const r = app.vp.canvas.getBoundingClientRect();
      const inView = window.__t.ids().map(id => { const s = window.__t.screen(window.__t.wp('b__Pelvis__', id)); return s[0] > r.left && s[0] < r.right && s[1] > r.top && s[1] < r.bottom; });
      const g = document.querySelector('#panel-body .add-grid'), pb = document.getElementById('panel-body').getBoundingClientRect(), gr = g ? g.getBoundingClientRect() : null;
      return { inView, grid: gr ? gr.top >= pb.top - 1 && gr.bottom <= pb.bottom + 1 : false };
    });
    say(`every sim is in view and the Add a sim buttons are in sight`, view.inView.every(Boolean) && view.grid, JSON.stringify(view));

    // ---------------------------------------------------------------- 2. sliding a sim by its circle, next to another sim
    const ids = await page.evaluate(() => window.__t.ids());
    let slid = 0, slideNotes = [];
    const onScreen = await page.evaluate(() => window.__t.ids().map(i => { const m = app.interact.rootMeshes.get(i); const p = m.group.position; const s = window.__t.screen([p.x, p.y, p.z]); const r = app.vp.canvas.getBoundingClientRect(); return s[0] > r.left + 20 && s[0] < r.right - 140 && s[1] > r.top + 20 && s[1] < r.bottom - 20; }));
    const slideIds = ids.filter((_, i) => onScreen[i]).slice(0, 3);
    for (let k = 0; k < slideIds.length; k++) {
      const id = slideIds[k];
      const before = await page.evaluate(i => window.__t.wp('b__Pelvis__', i), id);
      const c = await page.evaluate(i => { const m = app.interact.rootMeshes.get(i); const p = m.group.position; return window.__t.screen([p.x, p.y, p.z]); }, id);
      await page.mouse.move(c[0], c[1]); await page.mouse.down();
      for (let s = 1; s <= 10; s++) await page.mouse.move(c[0] + s * 12, c[1] + s * 3);
      await page.mouse.up(); await P.sleep(400);
      const after = await page.evaluate(i => window.__t.wp('b__Pelvis__', i), id);
      const moved = Math.hypot(after[0] - before[0], after[2] - before[2]);
      slideNotes.push(moved.toFixed(2)); if (moved > 0.05) slid++;
    }
    say(`each visible sim slides when its circle is dragged`, slideIds.length >= 2 && slid === slideIds.length, `moved ${slideNotes.join(', ')} m; errors: ${JSON.stringify(errs())}`);

    // ---------------------------------------------------------------- 3. ring drags
    const id0 = ids[0];
    await page.evaluate(i => { app.showStep('pose'); app.selectSim(i); }, id0);
    await P.sleep(500);
    const findGizmoPoint = async center => {
      for (let r = 8; r < 220; r += 3) for (let a = 0; a < 360; a += 15) {
        const x = center[0] + r * Math.cos(a * Math.PI / 180), y = center[1] + r * Math.sin(a * Math.PI / 180);
        await page.mouse.move(x, y);
        const axis = await page.evaluate(() => app.vp.gizmo.axis);
        if (axis) return { x, y, angle: a * Math.PI / 180, radius: r, axis };
      }
      return null;
    };
    const gizmoState = () => page.evaluate(() => ({ dragging: app.vp.gizmo.dragging, axis: app.vp.gizmo.axis, vpDragging: app.vp.dragging }));
    const sweep = async (center, hit, from, to, steps) => { for (let k = from; k <= to; k++) { const a = hit.angle + (k / steps) * (70 * Math.PI / 180); await page.mouse.move(center[0] + hit.radius * Math.cos(a), center[1] + hit.radius * Math.sin(a)); } };

    for (const bone of ['b__R_UpperArm__', 'b__L_Forearm__', 'b__R_Thigh__']) {
      await page.evaluate(([i, b]) => window.__t.pick(i, b), [id0, bone]);
      await P.sleep(250);
      const center = await page.evaluate(([b, i]) => window.__t.screen(window.__t.wp(b, i)), [bone, id0]);
      const hit = await findGizmoPoint(center);
      if (!hit) { say(`ring drag ${bone}: a ring can be grabbed`, false, 'no ring found'); continue; }
      const q0 = await page.evaluate(([b, i]) => window.__t.quat(b, i), [bone, id0]);
      await page.mouse.down();
      await sweep(center, hit, 1, 8, 16);
      const qMid = await page.evaluate(([b, i]) => window.__t.quat(b, i), [bone, id0]);
      await sweep(center, hit, 9, 16, 16);
      await page.mouse.up(); await P.sleep(200);
      const st = await gizmoState();
      const q1 = await page.evaluate(([b, i]) => window.__t.quat(b, i), [bone, id0]);
      // after the release, moving the mouse must not turn the bone any more
      for (let k = 0; k < 8; k++) await page.mouse.move(center[0] + 60 + k * 7, center[1] + 20 + k * 5);
      const q2 = await page.evaluate(([b, i]) => window.__t.quat(b, i), [bone, id0]);
      const turned = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [q0, q1]);
      const drift = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [q1, q2]);
      say(`ring drag ${bone}: turns, and stops turning at release`, turned > 3 && drift < 0.01 && !st.dragging, `turned ${turned.toFixed(1)}°, drift after release ${drift.toFixed(3)}°, gizmo.dragging=${st.dragging}`);
    }

    {
      const bone = 'b__L_Forearm__';
      await page.evaluate(([i, b]) => window.__t.pick(i, b), [id0, bone]); await P.sleep(250);
      const rings = await page.evaluate(() => ({ x: app.vp.gizmo.showX, y: app.vp.gizmo.showY, z: app.vp.gizmo.showZ }));
      const center = await page.evaluate(([b, i]) => window.__t.screen(window.__t.wp(b, i)), [bone, id0]);
      let hit = null;
      for (let r = 8; r < 220 && !hit; r += 3) for (let a = 0; a < 360; a += 10) {
        const x = center[0] + r * Math.cos(a * Math.PI / 180), y = center[1] + r * Math.sin(a * Math.PI / 180);
        await page.mouse.move(x, y);
        if ((await page.evaluate(() => app.vp.gizmo.axis)) === 'X') { hit = { x, y, angle: a * Math.PI / 180, radius: r }; break; }
      }
      let detail = `rings ${JSON.stringify(rings)}`, ok = rings.x && rings.y && rings.z && !!hit;
      if (hit) {
        const q0 = await page.evaluate(([b, i]) => window.__t.quat(b, i), [bone, id0]);
        await page.mouse.down(); await sweep(center, hit, 1, 16, 16); await page.mouse.up(); await P.sleep(200);
        const q1 = await page.evaluate(([b, i]) => window.__t.quat(b, i), [bone, id0]);
        const r = await page.evaluate(async ([a, b]) => { const T = await import('three'); const d = new T.Quaternion(...a).invert().multiply(new T.Quaternion(...b)); const s = Math.hypot(d.x, d.y, d.z) || 1; return { deg: 2 * Math.acos(Math.min(1, Math.abs(d.w))) * 180 / Math.PI, axis: [d.x / s, d.y / s, d.z / s].map(v => +v.toFixed(2)) }; }, [q0, q1]);
        detail += `, X ring turned it ${r.deg.toFixed(1)}° about ${JSON.stringify(r.axis)}`;
        ok = ok && r.deg > 3 && Math.abs(r.axis[0]) > 0.9;
      } else detail += ', no X ring found';
      say(`the forearm has all three rings and rolls on its X ring`, ok, detail);
    }

    // a release the gizmo never hears about (the button is let go outside the window or over another window, the
    // pointer is cancelled): the drag must end anyway - the part must not keep following the mouse
    for (const how of ['lost-up', 'cancel']) {
      const bone = 'b__R_UpperArm__';
      await page.evaluate(([i, b]) => window.__t.pick(i, b), [id0, bone]); await P.sleep(250);
      const center = await page.evaluate(([b, i]) => window.__t.screen(window.__t.wp(b, i)), [bone, id0]);
      const hit = await findGizmoPoint(center);
      await page.mouse.down();
      await sweep(center, hit, 1, 6, 16);
      if (how === 'lost-up') {
        // swallow the next pointerup before the gizmo sees it (what a release outside the window does)
        await page.evaluate(() => { const c = app.vp.canvas; const f = e => { e.stopImmediatePropagation(); c.removeEventListener('pointerup', f, true); }; c.addEventListener('pointerup', f, true); });
        await page.mouse.up();
      } else {
        await page.evaluate(() => { app.vp.canvas.dispatchEvent(new PointerEvent('pointercancel', { pointerId: 1, bubbles: true })); });
        await page.evaluate(() => { const c = app.vp.canvas; const f = e => { e.stopImmediatePropagation(); c.removeEventListener('pointerup', f, true); }; c.addEventListener('pointerup', f, true); });
        await page.mouse.up();
      }
      await P.sleep(100);
      const st = await gizmoState();
      const qa = await page.evaluate(([b, i]) => window.__t.quat(b, i), [bone, id0]);
      for (let k = 0; k < 8; k++) await page.mouse.move(center[0] + 30 + k * 9, center[1] + 40 + k * 6);
      const qb = await page.evaluate(([b, i]) => window.__t.quat(b, i), [bone, id0]);
      const drift = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [qa, qb]);
      const after = await gizmoState();
      say(`missed release (${how}): the part stops following the mouse`, drift < 0.01 && !after.dragging, `drift ${drift.toFixed(2)}°, gizmo.dragging right after=${st.dragging}, later=${after.dragging}`);
      // a click somewhere clears any stuck state before the next case
      await page.mouse.down(); await page.mouse.up(); await P.sleep(100);
    }
    {
      await page.evaluate(() => app.setTool('rotate'));
      const id = ids[1];
      const c = await page.evaluate(i => { const m = app.interact.rootMeshes.get(i); const p = m.group.position; return window.__t.screen([p.x, p.y, p.z]); }, id);
      await page.mouse.move(c[0], c[1]); await page.mouse.down();
      for (let k = 1; k <= 6; k++) await page.mouse.move(c[0] + k * 10, c[1] + k * 2);
      await page.evaluate(() => { const cv = app.vp.canvas; const f = e => { e.stopImmediatePropagation(); cv.removeEventListener('pointerup', f, true); }; cv.addEventListener('pointerup', f, true); });
      await page.mouse.up(); await P.sleep(100);
      const a = await page.evaluate(i => window.__t.wp('b__Pelvis__', i), id);
      for (let k = 0; k < 6; k++) await page.mouse.move(c[0] - 80 - k * 12, c[1] + 30 + k * 4);
      const b = await page.evaluate(i => window.__t.wp('b__Pelvis__', i), id);
      const moved = Math.hypot(b[0] - a[0], b[2] - a[2]);
      say(`missed release on a sim's circle: the sim stops following the mouse`, moved < 0.001 && !(await page.evaluate(() => app.vp.dragging)), `moved ${moved.toFixed(3)} m after the release`);
    }
    say(`no page errors`, errs().length === 0, JSON.stringify(errs()).slice(0, 400));
  } catch (e) {
    say(`the run`, false, String(e && e.message || e).split('\n')[0]);
  } finally {
    await browser.close();
  }
  proc.kill();
  const bad = rows.filter(r => !r.ok).length;
  console.log(`${rows.length - bad} PASS, ${bad} FAIL`);
  process.exit(bad ? 1 : 0);
})();
