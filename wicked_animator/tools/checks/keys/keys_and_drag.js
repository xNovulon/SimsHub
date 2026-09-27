// Deleting every body key of a sim (it holds the pose it showed, never the bind pose), and a gizmo drag that keeps
// following the mouse even when something pauses playback or resimulates physics mid-drag (Playwright, no game).
//   node tools/checks/keys/keys_and_drag.js [--port 8927]
// Starts tools/checks/lib/fake_game_server.py, opens the app on the ready-made couple and checks:
//   - "Select all of a sim's keys" (the timeline's own lane-menu path) then Delete takes every body key to zero:
//     the sim does not move (never a jump to the T-pose), sim.basePose holds what it showed, a short toast says so
//   - Ctrl+Z brings the keys back (same pose); Ctrl+Shift+Z (redo) takes them to zero again
//   - K with zero keys makes one key from exactly what shows; deleting that one key (Delete on the current frame,
//     the "Delete key" path) clears it to zero again the same way
//   - the project still round-trips through save/load with zero keys (basePose survives the JSON)
//   - the export dialog's checks no longer block a zero-key sim, and the baked clip holds that pose on every frame
//   - a real mouse drag on a rotate ring, started while the animation plays, pauses once (the gizmo keeps the part
//     it had picked instead of losing it) and keeps following the mouse to the end - the bone turns by about the
//     angle dragged, not stuck partway
//   - the same real drag, started right after a delete brings a sim down to one key (crossing the debounced physics
//     resim's 260 ms window mid-drag), also follows the mouse to the end
// Writing routes are answered in the browser (pw.js). Chromium: PLAYWRIGHT_BROWSERS_PATH or the default.
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');
const P = require('../lib/pw.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const PORT = +(argv[argv.indexOf('--port') + 1] || 0) || 8927;
const get = url => new Promise(res => { http.get(url, r => { let b = ''; r.on('data', c => { b += c; }); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', () => res(null)); });

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
    await page.waitForFunction(() => window.app && app.simViews && app.simViews.size >= 2, null, { timeout: 30000 });
    // off the Home screen (the stage's keys only work on the stage)
    await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true })));
    await page.waitForFunction(() => document.getElementById('home').classList.contains('hidden'), null, { timeout: 10000 });
    await P.sleep(600);

    // helpers in the page (the same shapes tools/checks/posetools/pose_tools.js uses)
    await page.evaluate(() => {
      const app = window.app, THREE_V = () => app.vp.camera.position.constructor, THREE_Q = () => app.vp.camera.quaternion.constructor;
      window.__t = {
        id: i => app.store.project.sims[i].id,
        v: id => app.simViews.get(id),
        wp: (bone, id) => { const p = window.__t.v(id).worldPos(bone); return [p.x, p.y, p.z]; },
        quat: (bone, id) => window.__t.v(id).bone(bone).quaternion.toArray(),
        screen: w => { const V = THREE_V(), p = new V(w[0], w[1], w[2]).project(app.vp.camera), r = app.vp.canvas.getBoundingClientRect();
          return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; },
        pick: (id, bone) => { const s = app.store.sim(id); s.pins = {}; app.setTool('rotate'); app.store.selected = { sim: id, bone }; app.interact.selectBone(id, bone); app.emitSelection(); },
        key: code => window.dispatchEvent(new KeyboardEvent('keydown', { code, key: code.replace('Key', '').toLowerCase(), bubbles: true })),
        toast: () => (document.querySelector('#toasts .toast span') || {}).textContent || '',
      };
      void THREE_Q;
    });
    // the angle between two quaternions (degrees) - a separate step since it needs a real `import('three')`
    await page.evaluate(async () => {
      const T = await import('three');
      window.__t.angleDeg = (a, b) => {
        const qa = new T.Quaternion(...a), qb = new T.Quaternion(...b);
        const d = Math.min(1, Math.abs(qa.x * qb.x + qa.y * qb.y + qa.z * qb.z + qa.w * qb.w));
        return 2 * Math.acos(d) * 180 / Math.PI;
      };
    });

    const active = () => page.evaluate(() => { const a = window.app.interact.active; return a ? { kind: a.kind, bone: a.bone || null, simId: a.simId || null } : null; });
    const bodyKeys = id => page.evaluate(i => window.app.store.sim(i).keys.filter(k => !k.faceOnly).length, id);
    const basePose = id => page.evaluate(i => window.app.store.sim(i).basePose || null, id);

    // Finds a screen point where the gizmo's picker sees a ring or arrow, by hovering outward from `center` (the
    // technique tools/checks/posetools/pose_tools.js uses for the circle's own turn ring).
    const findGizmoPoint = async center => {
      for (let r = 8; r < 220; r += 3) {
        for (let a = 0; a < 360; a += 15) {
          const x = center[0] + r * Math.cos(a * Math.PI / 180), y = center[1] + r * Math.sin(a * Math.PI / 180);
          await page.mouse.move(x, y);
          const axis = await page.evaluate(() => window.app.vp.gizmo.axis);
          if (axis) return { x, y, angle: a * Math.PI / 180, radius: r, axis };
        }
      }
      return null;
    };

    // A real mouse drag on a rotate ring: finds one near the bone, presses down, sweeps an arc around it, releases.
    // Returns the bone's quaternion sampled after every step (so a frozen stretch mid-drag shows up), plus whether
    // the app looked paused/mid-edit right after mouseDown and settled (not dragging) right after mouseUp.
    const dragRing = async (id, bone, { sweepDeg = 70, steps = 16, stepDelayMs = 0 } = {}) => {
      const center = await page.evaluate(([b, i]) => window.__t.screen(window.__t.wp(b, i)), [bone, id]);
      const hit = await findGizmoPoint(center);
      if (!hit) throw new Error('no ring/arrow found near ' + bone);
      await page.mouse.down();
      const afterDown = await page.evaluate(() => ({ playing: window.app.playing, editing: window.app.pipeline.editing }));
      const samples = [];
      for (let k = 1; k <= steps; k++) {
        const a = hit.angle + (k / steps) * (sweepDeg * Math.PI / 180);
        await page.mouse.move(center[0] + hit.radius * Math.cos(a), center[1] + hit.radius * Math.sin(a), { steps: 1 });
        if (stepDelayMs) await P.sleep(stepDelayMs);
        samples.push(await page.evaluate(([b, i]) => window.__t.quat(b, i), [bone, id]));
      }
      await page.mouse.up();
      const afterUp = await page.evaluate(() => ({ dragging: window.app.vp.dragging, playing: window.app.playing }));
      return { hit, afterDown, samples, afterUp };
    };

    // ---------------------------------------------------------------- 1. deleting every body key
    let m; // Male 1's id, re-read after every undo/redo/load (those replace app.store.project wholesale)
    await step('select all of a sim\'s keys, then Delete: 0 keys, the sim did not move, a short toast says so', async () => {
      m = await page.evaluate(() => window.__t.id(1));
      const before = await page.evaluate(id => window.__t.quat('b__R_UpperArm__', id), m);
      // two more keys (same pose - a fresh key just copies what already shows), so this is a real multi-key delete
      await page.evaluate(id => { window.app.selectSim(id); window.app.setFrame(30); window.app.keyPose(id); }, m);
      await page.evaluate(id => { window.app.setFrame(60); window.app.keyPose(id); }, m);
      const n0 = await bodyKeys(m);
      await page.evaluate(id => window.app.timeline.selectAll([id]), m); // "Select all of Male 1's keys" (laneMenu)
      await page.evaluate(() => window.app.deleteSelectedKeys());
      const n1 = await bodyKeys(m), bp = await basePose(m), after = await page.evaluate(id => window.__t.quat('b__R_UpperArm__', id), m);
      const toastText = await page.evaluate(() => window.__t.toast());
      const angle = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [before, after]);
      if (!(n0 === 3 && n1 === 0 && bp && bp.rot && angle < 0.5 && /pose stays/i.test(toastText)))
        throw new Error(JSON.stringify({ n0, n1, hasBasePose: !!bp, angle, toastText }));
      return `${n0} keys -> ${n1}; the arm stayed within ${angle.toFixed(3)}°; toast: "${toastText}"`;
    });

    await step('undo brings the 3 keys back (same pose); redo clears them to 0 again', async () => {
      const beforeQ = await page.evaluate(id => window.__t.quat('b__R_UpperArm__', id), m);
      await page.evaluate(() => window.app.undo());
      const n1 = await bodyKeys(m), q1 = await page.evaluate(id => window.__t.quat('b__R_UpperArm__', id), m);
      await page.evaluate(() => window.app.redo());
      const n2 = await bodyKeys(m), q2 = await page.evaluate(id => window.__t.quat('b__R_UpperArm__', id), m), bp2 = await basePose(m);
      const a1 = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [beforeQ, q1]);
      const a2 = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [beforeQ, q2]);
      if (!(n1 === 3 && a1 < 0.5 && n2 === 0 && a2 < 0.5 && bp2)) throw new Error(JSON.stringify({ n1, a1, n2, a2, hasBasePose: !!bp2 }));
      return `undo -> ${n1} keys (${a1.toFixed(3)}° off); redo -> ${n2} keys (${a2.toFixed(3)}° off), still holding the pose`;
    });

    await step('K with 0 keys makes one key from exactly what shows', async () => {
      const shown = await page.evaluate(id => window.__t.quat('b__R_UpperArm__', id), m);
      await page.evaluate(id => window.app.setFrame(45), m);
      await page.evaluate(id => window.app.keyPose(id), m);
      const n = await bodyKeys(m);
      const key = await page.evaluate(id => { const k = window.app.store.sim(id).keys.find(x => !x.faceOnly); return k ? { frame: k.frame, rot: k.pose.rot.b__R_UpperArm__ } : null; }, m);
      const angle = key ? await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [shown, key.rot]) : 999;
      if (!(n === 1 && key && key.frame === 45 && angle < 0.5)) throw new Error(JSON.stringify({ n, key, angle }));
      return `1 key at frame ${key.frame}, ${angle.toFixed(3)}° off what was shown`;
    });

    await step('Delete on the current frame ("Delete key") clears the last key the same way', async () => {
      const shown = await page.evaluate(id => window.__t.quat('b__R_UpperArm__', id), m);
      await page.evaluate(id => window.app.deleteKey(id), m);
      const n = await bodyKeys(m), bp = await basePose(m), after = await page.evaluate(id => window.__t.quat('b__R_UpperArm__', id), m);
      const angle = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [shown, after]);
      const toastText = await page.evaluate(() => window.__t.toast());
      if (!(n === 0 && bp && angle < 0.5 && /pose stays/i.test(toastText))) throw new Error(JSON.stringify({ n, hasBasePose: !!bp, angle, toastText }));
      return `0 keys, ${angle.toFixed(3)}° off, toast: "${toastText}"`;
    });

    await step('save/load with 0 keys: basePose round-trips through JSON and the pose still shows after loading', async () => {
      const shown = await page.evaluate(id => window.__t.quat('b__R_UpperArm__', id), m);
      const r = await page.evaluate(id => {
        const app = window.app, before = JSON.stringify(app.store.project);
        const copy = JSON.parse(before);
        const label = app.store.sim(id).label;
        app.store.load(copy);
        const s2 = app.store.project.sims.find(x => x.label === label);
        return { hadBasePoseInJson: before.includes('"basePose"'), id2: s2 ? s2.id : null, n: s2 ? s2.keys.filter(k => !k.faceOnly).length : -1 };
      }, m);
      if (!r.id2) throw new Error('the sim did not survive the load: ' + JSON.stringify(r));
      m = r.id2; // store.load() replaced every sim object; keep following the same one by its (unchanged) label -> id
      await P.sleep(150); // refreshAll()/applyPoses() run off the 'project' event
      const after = await page.evaluate(id => window.__t.quat('b__R_UpperArm__', id), m);
      const angle = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [shown, after]);
      const bp = await basePose(m);
      if (!(r.hadBasePoseInJson && r.n === 0 && bp && angle < 0.5)) throw new Error(JSON.stringify({ ...r, angle, hasBasePose: !!bp }));
      return `basePose was in the saved JSON; after loading, 0 keys and ${angle.toFixed(3)}° off`;
    });

    await step('the export dialog no longer blocks a 0-key sim, and the baked clip holds the pose on every frame', async () => {
      const r = await page.evaluate(async id => {
        const app = window.app;
        const { exportChecks } = await import('/js/dialogs/export.js');
        const blocked = exportChecks(app).some(x => x.level === 'error' && /needs at least one pose/i.test(x.text));
        const payload = app.bake();
        const i = app.store.project.sims.findIndex(s => s.id === id);
        const want = app.store.sim(id).basePose.rot.b__R_UpperArm__;
        const track = payload.actors[i].tracks.b__R_UpperArm__.r;
        return { blocked, frames: track.length, sample: track[0], mid: track[Math.floor(track.length / 2)], last: track[track.length - 1], want };
      }, m);
      const a0 = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [r.sample, r.want]);
      const a1 = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [r.mid, r.want]);
      const a2 = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [r.last, r.want]);
      if (!(!r.blocked && r.frames > 1 && a0 < 0.5 && a1 < 0.5 && a2 < 0.5)) throw new Error(JSON.stringify({ ...r, a0, a1, a2 }));
      return `export not blocked; ${r.frames} baked frames all within 0.5° of the held pose (start/mid/end: ${a0.toFixed(3)}/${a1.toFixed(3)}/${a2.toFixed(3)})`;
    });

    // ---------------------------------------------------------------- 2. a drag that must not stop mid-way
    await step('a real ring drag started while the animation plays pauses once and follows the mouse to the end', async () => {
      const f = await page.evaluate(() => window.__t.id(0)); // Female 1: her one key never changes while she "plays"
      const bone = 'b__L_UpperArm__';
      await page.evaluate(([id, b]) => window.__t.pick(id, b), [f, bone]);
      const before = await active();
      await page.evaluate(() => document.getElementById('btn-play').click());
      const whilePlaying = await page.evaluate(() => window.app.playing);
      const stillPicked = await active();
      const r = await dragRing(f, bone, { sweepDeg: 75, steps: 16 });
      const angle = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [r.samples[0], r.samples[r.samples.length - 1]]);
      // "frozen mid-way" would show up as several back-to-back steps in the second half with ~no change
      let stuck = 0;
      for (let k = Math.floor(r.samples.length / 2); k < r.samples.length - 1; k++) {
        const d = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [r.samples[k], r.samples[k + 1]]);
        if (d < 0.02) stuck++;
      }
      // paused once, resumes normally afterwards
      await page.evaluate(() => document.getElementById('btn-play').click());
      const resumed = await page.evaluate(() => window.app.playing);
      await page.evaluate(() => document.getElementById('btn-play').click());
      const pausedAgain = await page.evaluate(() => window.app.playing);
      if (!(before && before.kind === 'bone' && whilePlaying && stillPicked && stillPicked.kind === 'bone' && stillPicked.bone === bone
        && r.afterDown.playing === false && r.afterDown.editing === f && angle > 8 && stuck < 3 && !r.afterUp.dragging && !r.afterUp.playing
        && resumed && !pausedAgain))
        throw new Error(JSON.stringify({ before, whilePlaying, stillPicked, afterDown: r.afterDown, angle, stuck, afterUp: r.afterUp, resumed, pausedAgain }));
      return `picked before Play, still picked while playing; grabbing the ring paused it once, turned the arm ${angle.toFixed(1)}° with no frozen stretch, then Play resumed normally`;
    });

    await step('a real ring drag started right after deleting down to one key also follows the mouse to the end', async () => {
      // back to a known 2-key state on Male 1 (K makes a key from what shows, same as the earlier steps)
      await page.evaluate(id => { window.app.setFrame(10); window.app.keyPose(id); }, m);
      await page.evaluate(id => { window.app.setFrame(70); window.app.keyPose(id); }, m);
      const bone = 'b__R_Forearm__';
      await page.evaluate(([id, b]) => window.__t.pick(id, b), [m, bone]);
      await page.evaluate(id => window.app.setFrame(70), m);              // the frame Delete will remove
      await page.evaluate(id => window.app.deleteKey(id), m);             // 2 keys -> 1 (the physics resim timer arms here)
      const n = await bodyKeys(m);
      // the drag straddles the debounced 260 ms resim (main.js physicsChanged) on purpose
      const r = await dragRing(m, bone, { sweepDeg: 60, steps: 20, stepDelayMs: 25 });
      const angle = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [r.samples[0], r.samples[r.samples.length - 1]]);
      let stuck = 0;
      for (let k = Math.floor(r.samples.length / 2); k < r.samples.length - 1; k++) {
        const d = await page.evaluate(([a, b]) => window.__t.angleDeg(a, b), [r.samples[k], r.samples[k + 1]]);
        if (d < 0.02) stuck++;
      }
      if (!(n === 1 && angle > 6 && stuck < 3 && !r.afterUp.dragging)) throw new Error(JSON.stringify({ n, angle, stuck, afterUp: r.afterUp }));
      return `1 key remained; the drag (spanning the 260 ms resim) turned the forearm ${angle.toFixed(1)}° with no frozen stretch`;
    });

    const expected = [/Failed to load resource/, /GPU stall|WebGL|swiftshader|GroupMarkerNotSet/i, /fonts\.googleapis/];
    const bad = P.problems(logs, { ignore: expected });
    ok('no uncaught errors or console errors', !bad.length, bad.slice(0, 5).map(l => `${l.type}: ${l.text.slice(0, 200)}`).join(' | ') || 'clean');
  } catch (e) {
    ok('the check ran to the end', false, e.stack || String(e));
  } finally {
    if (browser) await browser.close().catch(() => {});
    proc.kill();
  }
  const pass = P.report(rows, 'Zero-key sims hold their pose; a gizmo drag never stops mid-way (Playwright, no game)');
  process.exit(pass ? 0 : 1);
})();
