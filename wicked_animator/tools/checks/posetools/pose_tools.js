// R turns, T moves, the circle at each sim's feet moves the whole sim - in the running app (Playwright, no game).
//   node tools/checks/posetools/pose_tools.js [--port 8873]
// Starts tools/checks/lib/fake_game_server.py, opens the app on the ready-made couple and checks:
//   - one pink circle per sim under its hips, drawn over everything (no depth test); the object's centre ring is white
//   - T on the hips: arrows; moving them keeps both feet where they stood and the neck and head where they were
//   - T on a hand: arrows; the arm follows, the hips don't move, no bone is stretched (only turned)
//   - T on the head, an upper arm and a finger: the part moves toward the arrows, only turned joints, the hips stay
//   - R after T: the part's rings again; T with nothing picked says what to do
//   - a click on the circle picks the whole sim even with the legs drawn over it; dragging it slides the whole sim
//     (every key), and R/T give its turn ring / arrows
//   - the Move tool (M) moves the part clicked, never the whole sim
//   - the export gets no new position track for any turned-only bone; no console errors
// Writing routes are answered in the browser (pw.js). Chromium: PLAYWRIGHT_BROWSERS_PATH or the default.
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn } = require('child_process');
const P = require('../lib/pw.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const PORT = +(argv[argv.indexOf('--port') + 1] || 0) || 8873;
const OUT = path.join(ROOT, 'cache', 'checks', 'posetools');

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
  try {
    const o = await P.open(PORT, { scene: 'couple' });
    browser = o.browser;
    const { page, logs } = o;
    const step = async (name, fn) => {
      try { const r = await fn(); ok(name, r !== false, typeof r === 'string' ? r : undefined); }
      catch (e) { ok(name, false, (e && e.message || String(e)).split('\n')[0]); }
    };
    const shot = name => page.screenshot({ path: path.join(OUT, name + '.png') }).catch(() => {});
    await page.waitForFunction(() => window.app && window.app.simViews && window.app.simViews.size >= 2, null, { timeout: 30000 });
    // off the Home screen (the stage's keys only work on the stage)
    await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true })));
    await page.waitForFunction(() => document.getElementById('home').classList.contains('hidden'), null, { timeout: 10000 });
    await P.sleep(800);
    // helpers in the page
    await page.evaluate(() => {
      const app = window.app, THREE_V = () => app.vp.camera.position.constructor;
      window.__t = {
        sim: () => app.store.project.sims[0].id,
        v: id => app.simViews.get(id || window.__t.sim()),
        wp: (bone, id) => { const p = window.__t.v(id).worldPos(bone); return [p.x, p.y, p.z]; },
        wq: (bone, id) => { const b = window.__t.v(id).bone(bone); b.updateWorldMatrix(true, false); return b.getWorldQuaternion(new app.vp.camera.quaternion.constructor()).toArray(); },
        // every bone's local position (a moved-only-by-turning pose leaves these alone, the hips aside)
        positions: id => { const v = window.__t.v(id), out = {}; for (const b of v.bones) out[b.name] = b.position.toArray(); return out; },
        pick: (bone, id) => { const s = id || window.__t.sim(); app.store.sim(s).pins = {}; app.setTool('rotate'); app.store.selected = { sim: s, bone }; app.interact.selectBone(s, bone); app.emitSelection(); },
        key: code => window.dispatchEvent(new KeyboardEvent('keydown', { code, key: code.replace('Key', '').toLowerCase(), bubbles: true })),
        // a gizmo drag: the arrows' object moved by d (world metres)
        drag: d => { const gz = app.vp.gizmo, pr = app.interact.proxy; gz.dispatchEvent({ type: 'mouseDown' });
          const steps = 6; for (let k = 1; k <= steps; k++) { pr.position.set(pr.position.x + d[0] / steps, pr.position.y + d[1] / steps, pr.position.z + d[2] / steps); pr.updateMatrixWorld(); gz.dispatchEvent({ type: 'objectChange' }); }
          gz.dispatchEvent({ type: 'mouseUp' }); },
        dist: (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]),
        screen: w => { const V = THREE_V(), p = new V(w[0], w[1], w[2]).project(app.vp.camera), r = app.vp.canvas.getBoundingClientRect();
          return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; },
      };
    });
    const active = () => page.evaluate(() => { const a = window.app.interact.active; return a ? { kind: a.kind, bone: a.bone || null, limb: a.limb || null, mode: window.app.vp.gizmo.mode } : null; });
    const moved = (before, after, skip = []) => Object.keys(before).filter(n => !skip.includes(n) && Math.hypot(...before[n].map((x, k) => x - after[n][k])) > 1e-6);
    const HIPS = ['b__Spine0__', 'b__Pelvis__'];

    await step("one circle per sim under its hips, drawn over everything; the object's centre ring is white", async () => {
      const r = await page.evaluate(() => {
        const app = window.app, it = app.interact, out = [];
        for (const [id, m] of it.rootMeshes) {
          const p = app.simViews.get(id).worldPos('b__Pelvis__');
          out.push({ off: Math.hypot(m.group.position.x - p.x, m.group.position.z - p.z), y: m.group.position.y, vis: m.group.visible,
            noDepth: !m.ring.material.depthTest && !m.fill.material.depthTest });
        }
        return { n: it.rootMeshes.size, sims: app.store.project.sims.length, out, origin: app.vp.origin.material.color.getHex() };
      });
      if (r.n !== r.sims || r.out.some(x => x.off > 1e-4 || !x.vis || !x.noDepth || x.y > 0.01) || r.origin !== 0xffffff) throw new Error(JSON.stringify(r));
      return `${r.n} circles, no depth test, the centre ring white`;
    });

    await step('T on the hips: arrows (the rings before)', async () => {
      await page.evaluate(() => window.__t.pick('b__Pelvis__'));
      const a0 = await active();
      await page.evaluate(() => window.__t.key('KeyT'));
      const a1 = await active();
      if (!(a0.kind === 'bone' && a0.mode === 'rotate' && a1.kind === 'hips' && a1.mode === 'translate')) throw new Error(JSON.stringify({ a0, a1 }));
      return `${a0.kind}/${a0.mode} -> ${a1.kind}/${a1.mode}`;
    });
    await step('moving the hips 12 cm sideways: the feet stay, the neck and head stay, the hips move', async () => {
      const r = await page.evaluate(() => {
        const t = window.__t, B = ['b__Pelvis__', 'b__L_Foot__', 'b__R_Foot__', 'b__Neck__'];
        const before = Object.fromEntries(B.map(b => [b, t.wp(b)])), headQ = t.wq('b__Head__');
        t.drag([0.12, 0, 0]);
        const after = Object.fromEntries(B.map(b => [b, t.wp(b)])), headQ2 = t.wq('b__Head__');
        const dq = Math.abs(headQ.reduce((s, x, k) => s + x * headQ2[k], 0));
        return { hips: t.dist(before.b__Pelvis__, after.b__Pelvis__), lf: t.dist(before.b__L_Foot__, after.b__L_Foot__),
          rf: t.dist(before.b__R_Foot__, after.b__R_Foot__), neck: t.dist(before.b__Neck__, after.b__Neck__), head: 2 * Math.acos(Math.min(1, dq)) * 180 / Math.PI };
      });
      if (!(r.hips > 0.1 && r.lf < 0.005 && r.rf < 0.005 && r.neck < 0.03 && r.head < 1)) throw new Error(JSON.stringify(r));
      await shot('hips_moved');
      return `hips ${(r.hips * 100).toFixed(1)} cm, feet ${(r.lf * 1000).toFixed(1)}/${(r.rf * 1000).toFixed(1)} mm, neck ${(r.neck * 100).toFixed(1)} cm, head ${r.head.toFixed(2)}°`;
    });
    await step('R after T: the hips\' rings again', async () => {
      await page.evaluate(() => window.__t.key('KeyR'));
      const a = await active();
      if (!(a.kind === 'bone' && a.bone === 'b__Pelvis__' && a.mode === 'rotate')) throw new Error(JSON.stringify(a));
      return `${a.kind}/${a.mode}`;
    });

    await step('T on a hand: the arm follows, nothing else moves, no bone stretched', async () => {
      await page.evaluate(() => window.__t.pick('b__L_Hand__'));
      await page.evaluate(() => window.__t.key('KeyT'));
      const a = await active();
      if (!(a.kind === 'limb' && a.limb === 'L hand' && a.mode === 'translate')) throw new Error('not the hand\'s arrows: ' + JSON.stringify(a));
      const r = await page.evaluate(() => {
        const t = window.__t, pos0 = t.positions(), hand0 = t.wp('b__L_Hand__'), hips0 = t.wp('b__Pelvis__'), rf0 = t.wp('b__R_Hand__');
        const target = [hand0[0] + 0.1, hand0[1] + 0.08, hand0[2] + 0.05];
        t.drag([0.1, 0.08, 0.05]);
        return { pos0, pos1: t.positions(), hand: t.dist(t.wp('b__L_Hand__'), target), handMoved: t.dist(t.wp('b__L_Hand__'), hand0),
          hips: t.dist(hips0, t.wp('b__Pelvis__')), other: t.dist(rf0, t.wp('b__R_Hand__')) };
      });
      const m = moved(r.pos0, r.pos1);
      if (!(r.handMoved > 0.08 && r.hand < 0.01 && r.hips < 1e-6 && r.other < 1e-6 && !m.length)) throw new Error(JSON.stringify({ ...r, pos0: undefined, pos1: undefined, stretched: m }));
      await shot('hand_moved');
      return `hand ${(r.handMoved * 100).toFixed(1)} cm (${(r.hand * 1000).toFixed(1)} mm off the arrows), hips and other hand still, no bone stretched`;
    });

    for (const [bone, d, label] of [['b__Head__', [0.06, 0, 0.04], 'the head'], ['b__R_UpperArm__', [0, -0.1, 0.1], 'an upper arm'], ['b__L_Index1__', [0, 0.012, 0], 'a finger'], ['b__Spine2__', [0.05, 0, 0], 'the chest']]) {
      await step(`T on ${label}: it moves toward the arrows by turning joints only, the hips stay`, async () => {
        await page.evaluate(b => window.__t.pick(b), bone);
        await page.evaluate(() => window.__t.key('KeyT'));
        const a = await active();
        if (!(a.kind === 'pull' && a.bone === bone && a.mode === 'translate')) throw new Error('no arrows: ' + JSON.stringify(a));
        const r = await page.evaluate(([dd]) => {
          const t = window.__t, app = window.app, it = app.interact, v = t.v();
          const end = () => { const p = it.proxy.position.clone(); const e = it._pullEnd(v, it.active.pull); const w = v.space.localToWorld(e.clone()); return [w.x, w.y, w.z]; };
          const pos0 = t.positions(), e0 = end(), hips0 = t.wp('b__Pelvis__'), feet0 = [t.wp('b__L_Foot__'), t.wp('b__R_Foot__')];
          // a part turned by one joint only moves on a sphere around it: the best it can do is the nearest point there
          const chain = it.active.pull.chain, J = chain.length === 1 ? t.wp(chain[0]) : null;
          const target = [e0[0] + dd[0], e0[1] + dd[1], e0[2] + dd[2]];
          app.naturalLimits = false;
          t.drag(dd);
          app.naturalLimits = true;
          const e1 = end();
          return { pos0, pos1: t.positions(), gone: t.dist(e0, e1), left: t.dist(e1, target), want: Math.hypot(...dd), hips: t.dist(hips0, t.wp('b__Pelvis__')),
            best: J ? Math.abs(t.dist(target, J) - t.dist(e0, J)) : 0,
            feet: Math.max(t.dist(feet0[0], t.wp('b__L_Foot__')), t.dist(feet0[1], t.wp('b__R_Foot__'))) };
        }, [d]);
        const m = moved(r.pos0, r.pos1);
        if (!(r.left < Math.max(r.want * 0.35, r.best + 0.003) && r.hips < 1e-6 && r.feet < 1e-6 && !m.length)) throw new Error(JSON.stringify({ gone: r.gone, left: r.left, best: r.best, want: r.want, hips: r.hips, feet: r.feet, stretched: m }));
        return `moved ${(r.gone * 100).toFixed(1)} of ${(r.want * 100).toFixed(1)} cm (${(r.left * 1000).toFixed(1)} mm short${r.best ? `, ${(r.best * 1000).toFixed(1)} mm is out of its reach` : ''}), hips and feet still, no bone stretched`;
      });
    }

    await step('Drag tool: T on a foot dot keeps that foot (not a part picked earlier); its hips dot carries the legs', async () => {
      const r = await page.evaluate(() => {
        const app = window.app, t = window.__t, id = t.sim(), it = app.interact;
        t.pick('b__Head__');                     // picked earlier in the Pose tool
        app.setTool('ik');
        const foot = it.handleList.find(x => x.simId === id && x.limb === 'R foot'), hips = it.handleList.find(x => x.simId === id && x.kind === 'hips');
        it.selectHandle(foot);
        t.key('KeyT');
        const a = it.active, kept = a && a.kind === 'limb' && a.limb === 'R foot';
        it.selectHandle(hips);
        const f0 = t.wp('b__L_Foot__');
        t.drag([0, 0.1, 0]);
        const lift = t.wp('b__L_Foot__')[1] - f0[1];
        app.setTool('rotate');
        return { kept, active: a && { kind: a.kind, limb: a.limb, bone: a.bone }, lift };
      });
      if (!(r.kept && Math.abs(r.lift - 0.1) < 0.005)) throw new Error(JSON.stringify(r));
      return `the foot kept its arrows; lifting the hips dot 10 cm lifted the feet ${(r.lift * 100).toFixed(1)} cm`;
    });

    await step('T with nothing picked: a hint, no arrows', async () => {
      const r = await page.evaluate(() => { const app = window.app; app.vp.gizmo.detach(); app.interact.active = null; app.store.selected.bone = null; window.__t.key('KeyT');
        return { a: app.interact.active, hud: document.getElementById('vp-hud').innerText }; });
      if (r.a || !/circle at a sim's feet/.test(r.hud)) throw new Error(JSON.stringify(r));
      return r.hud;
    });

    await step('a click on the circle picks the whole sim, even with the body drawn over it', async () => {
      // straight down from above: the hips are over the circle, so a plain click there would land on the body
      await page.evaluate(() => { const app = window.app; app.vp.stopCamera && app.vp.stopCamera(); app.setTool('rotate'); app.setView('top'); });
      await P.sleep(1000);
      const r = await page.evaluate(() => {
        const app = window.app, t = window.__t, id = t.sim();
        const m = app.interact.rootMeshes.get(id);
        const [x, y] = t.screen([m.group.position.x, m.group.position.y, m.group.position.z]);
        const body = app.vp.pick({ clientX: x, clientY: y }, app.interact._meshes());
        app.interact._click({ clientX: x, clientY: y, button: 0 });
        const a = app.interact.active;
        return { x, y, overBody: !!body, kind: a && a.kind, sim: a && a.simId === id, bone: app.store.selected.bone, mode: app.vp.gizmo.mode };
      });
      await shot('root_under_body');
      if (!(r.overBody && r.kind === 'place' && r.sim && !r.bone && r.mode === 'translate')) throw new Error(JSON.stringify(r));
      // and it is drawn over the body: the other sim's circle (no arrows on it) shows pink where its hips are
      const px = await page.evaluate(([x, y]) => new Promise(res => requestAnimationFrame(() => {
        const app = window.app, c = app.vp.canvas, r = c.getBoundingClientRect(), other = app.store.project.sims[1].id, m = app.interact.rootMeshes.get(other);
        const body = app.vp.pick((([sx, sy]) => ({ clientX: sx, clientY: sy }))(window.__t.screen([m.group.position.x, 0.004, m.group.position.z])), app.interact._meshes());
        if (!body) { res(['no body over the other circle']); return; }
        const R = 0.075 * 0.87, [ex, ey] = window.__t.screen([m.group.position.x - R, m.group.position.y, m.group.position.z]);
        const g = document.createElement('canvas'); g.width = c.width; g.height = c.height;
        const k = c.width / r.width, cx = g.getContext('2d');
        app.vp.renderer.render(app.vp.scene, app.vp.camera); cx.drawImage(c, 0, 0);
        res([...cx.getImageData(Math.round((ex - r.left) * k), Math.round((ey - r.top) * k), 1, 1).data]);
      })), [r.x, r.y]);
      if (!(px[0] > 150 && px[0] > px[1] + 60 && px[2] > px[1] + 20)) throw new Error('the circle is not drawn over the body: pixel ' + px.join(','));
      return `the body was under the pointer, the circle won; its edge shows over the body (rgb ${px.slice(0, 3).join(',')})`;
    });
    await step('R / T on the circle: its turn ring, then its arrows', async () => {
      await page.evaluate(() => window.__t.key('KeyR'));
      const a = await active();
      await page.evaluate(() => window.__t.key('KeyT'));
      const b = await active();
      if (!(a.kind === 'place' && a.mode === 'rotate' && b.kind === 'place' && b.mode === 'translate')) throw new Error(JSON.stringify({ a, b }));
      return 'rotate, then translate';
    });
    await step('dragging the circle slides the whole sim over the floor (every key)', async () => {
      await page.evaluate(() => { const app = window.app; app.vp.stopCamera && app.vp.stopCamera(); app.setView('top'); });
      await P.sleep(900);
      const s = await page.evaluate(() => {
        const app = window.app, t = window.__t, id = t.sim(), m = app.interact.rootMeshes.get(id);
        const keys = app.store.sim(id).keys.map(k => (k.pose.pos && k.pose.pos.b__Pelvis__) ? k.pose.pos.b__Pelvis__.slice() : null);
        return { at: t.screen([m.group.position.x, 0.004, m.group.position.z]), hips: t.wp('b__Pelvis__'), keys, feet: t.wp('b__L_Foot__') };
      });
      await page.mouse.move(s.at[0], s.at[1]);
      await page.mouse.down();
      for (let k = 1; k <= 8; k++) await page.mouse.move(s.at[0] + k * 10, s.at[1], { steps: 1 });
      await page.mouse.up();
      await P.sleep(200);
      const e = await page.evaluate(() => {
        const app = window.app, t = window.__t, id = t.sim();
        const keys = app.store.sim(id).keys.map(k => (k.pose.pos && k.pose.pos.b__Pelvis__) ? k.pose.pos.b__Pelvis__.slice() : null);
        return { hips: t.wp('b__Pelvis__'), keys, feet: t.wp('b__L_Foot__'), kind: app.interact.active && app.interact.active.kind };
      });
      const d = Math.hypot(e.hips[0] - s.hips[0], e.hips[2] - s.hips[2]), f = Math.hypot(e.feet[0] - s.feet[0], e.feet[2] - s.feet[2]);
      const keysMoved = e.keys.filter((k, i) => k && s.keys[i] && Math.hypot(k[0] - s.keys[i][0], k[1] - s.keys[i][1], k[2] - s.keys[i][2]) > 1e-4).length;
      await shot('root_dragged');
      if (!(d > 0.03 && Math.abs(d - f) < 0.005 && Math.abs(e.hips[1] - s.hips[1]) < 1e-4 && keysMoved === e.keys.filter(Boolean).length && e.kind === 'place')) throw new Error(JSON.stringify({ d, f, dy: e.hips[1] - s.hips[1], keysMoved, keys: e.keys.length, kind: e.kind }));
      return `the sim slid ${(d * 100).toFixed(1)} cm (feet too), ${keysMoved} key(s) moved with it, same height`;
    });
    // which way the hips point on the floor (the line from the left thigh to the right one, degrees) and where they are
    const facing = () => page.evaluate(() => {
      const t = window.__t, l = t.wp('b__L_Thigh__'), r = t.wp('b__R_Thigh__');
      return { yaw: Math.atan2(r[0] - l[0], r[2] - l[2]) * 180 / Math.PI, hips: t.wp('b__Pelvis__') };
    });
    const turnBy = (a, b) => ((b - a + 540) % 360) - 180;
    await step('R, then dragging the circle itself turns the whole sim about its circle (every key)', async () => {
      await page.evaluate(() => { const app = window.app; app.vp.stopCamera && app.vp.stopCamera(); app.setView('top'); });
      await P.sleep(900);
      await page.evaluate(() => window.__t.key('KeyR'));
      const s = await page.evaluate(() => {
        const app = window.app, t = window.__t, id = t.sim(), m = app.interact.rootMeshes.get(id), R = 0.075 * 0.87;
        const c = m.group.position;
        return { c: t.screen([c.x, 0.004, c.z]), e: t.screen([c.x + R * m.group.scale.x, 0.004, c.z]), mode: app.vp.gizmo.mode,
          keys: app.store.sim(id).keys.map(k => (k.pose.rot && k.pose.rot.b__Pelvis__) ? k.pose.rot.b__Pelvis__.slice() : null) };
      });
      const f0 = await facing();
      // press on the circle's edge and go a quarter of the way round it
      const rad = Math.max(8, Math.hypot(s.e[0] - s.c[0], s.e[1] - s.c[1]) * 0.8);
      await page.mouse.move(s.c[0] + rad, s.c[1]);
      await page.mouse.down();
      for (let k = 1; k <= 12; k++) { const a = (k / 12) * Math.PI / 2; await page.mouse.move(s.c[0] + rad * Math.cos(a), s.c[1] + rad * Math.sin(a), { steps: 1 }); }
      await page.mouse.up();
      await P.sleep(200);
      const f1 = await facing();
      const e = await page.evaluate(() => { const app = window.app, id = window.__t.sim(); return { kind: app.interact.active && app.interact.active.kind, mode: app.vp.gizmo.mode,
        keys: app.store.sim(id).keys.map(k => (k.pose.rot && k.pose.rot.b__Pelvis__) ? k.pose.rot.b__Pelvis__.slice() : null) }; });
      const turned = turnBy(f0.yaw, f1.yaw), moved = Math.hypot(f1.hips[0] - f0.hips[0], f1.hips[2] - f0.hips[2]);
      const keysTurned = e.keys.filter((k, i) => k && s.keys[i] && k.some((x, j) => Math.abs(x - s.keys[i][j]) > 1e-4)).length;
      await shot('root_turned');
      if (!(s.mode === 'rotate' && Math.abs(Math.abs(turned) - 90) < 20 && moved < 0.03 && e.kind === 'place' && e.mode === 'rotate' && keysTurned === e.keys.filter(Boolean).length))
        throw new Error(JSON.stringify({ mode: s.mode, turned, moved, kind: e.kind, endMode: e.mode, keysTurned }));
      return `a quarter round the circle turned the sim ${Math.abs(turned).toFixed(1)}° (hips moved ${(moved * 100).toFixed(1)} cm), ${keysTurned} key(s) turned`;
    });
    await step('R, then dragging the green ring turns the whole sim too', async () => {
      const s = await page.evaluate(() => window.__t.screen(window.app.interact.proxy.position.toArray()));
      const f0 = await facing();
      let hit = null;
      for (let r = 10; r < 300 && !hit; r += 3) for (let a = 0; a < 360; a += 12) {
        const x = s[0] + r * Math.cos(a * Math.PI / 180), y = s[1] + r * Math.sin(a * Math.PI / 180);
        await page.mouse.move(x, y);
        if (await page.evaluate(() => window.app.vp.gizmo.axis) === 'Y' && !(await page.evaluate(([px, py]) => !!window.app.interact._rootAt({ clientX: px, clientY: py }), [x, y]))) { hit = { x, y, a }; break; }
      }
      if (!hit) throw new Error('no point on the ring outside the circle');
      await page.mouse.down();
      const t = (hit.a + 90) * Math.PI / 180;
      for (let k = 1; k <= 10; k++) await page.mouse.move(hit.x + Math.cos(t) * 6 * k, hit.y + Math.sin(t) * 6 * k, { steps: 1 });
      await page.mouse.up();
      await P.sleep(200);
      const f1 = await facing(), turned = turnBy(f0.yaw, f1.yaw);
      if (!(Math.abs(turned) > 5)) throw new Error(JSON.stringify({ turned, hit }));
      return `the ring turned it ${Math.abs(turned).toFixed(1)}°`;
    });
    await step('R on the circle: all three rings and the ball, like a hand; tipping it 30° tips the whole sim (every key, undo)', async () => {
      const r = await page.evaluate(async () => {
        const T = await import('three');
        const app = window.app, I = app.interact, gz = app.vp.gizmo, t = window.__t, id = t.sim();
        I.selectRoot(id, 'rotate');
        const shown = [gz.mode, gz.showX, gz.showY, gz.showZ];
        const up = () => { const h = t.wp('b__Head__'), p = t.wp('b__Pelvis__'); return new T.Vector3(h[0] - p[0], h[1] - p[1], h[2] - p[2]).normalize(); };
        const rot = () => JSON.stringify(app.store.sim(id).keys.map(k => k.pose.rot && k.pose.rot.b__Pelvis__));
        const u0 = up(), k0 = rot(), c0 = I.proxy.position.clone();
        gz.dispatchEvent({ type: 'mouseDown' });
        for (let s = 1; s <= 3; s++) {
          I.proxy.quaternion.premultiply(new T.Quaternion().setFromAxisAngle(new T.Vector3(1, 0, 0), T.MathUtils.degToRad(10)));
          gz.dispatchEvent({ type: 'objectChange' });
        }
        gz.dispatchEvent({ type: 'mouseUp' });
        app.applyPoses(false);
        const u1 = up(), k1 = rot();
        // the circle stays the pivot: the point of the body at the circle doesn't move sideways along the tip's axis
        const tilt = T.MathUtils.radToDeg(u0.angleTo(u1));
        app.undo(); app.applyPoses(false);
        const back = T.MathUtils.radToDeg(u0.angleTo(up()));
        return { shown, tilt, keysChanged: k0 !== k1, back, pivot: c0.toArray() };
      });
      if (!(r.shown[0] === 'rotate' && r.shown.slice(1).every(Boolean) && Math.abs(r.tilt - 30) < 1.5 && r.keysChanged && r.back < 0.5)) throw new Error(JSON.stringify(r));
      return `rings X, Y, Z shown; tipped ${r.tilt.toFixed(1)}° (asked 30), the keys changed, undo put it back (${r.back.toFixed(2)}° off)`;
    });

    await step('the Move tool (M) moves the part clicked, never the whole sim', async () => {
      const r = await page.evaluate(() => {
        const app = window.app, t = window.__t, id = t.sim();
        app.setView('front');
        app.store.selected = { sim: id, bone: 'b__R_Hand__' };
        window.__t.key('KeyM');
        const a = app.interact.active;
        return { tool: app.interact.tool, kind: a && a.kind, limb: a && a.limb, btn: document.querySelector('#tool-seg button[data-tool="move"]').innerText.trim() };
      });
      if (!(r.tool === 'move' && r.kind === 'limb' && r.limb === 'R hand' && r.btn === 'Move')) throw new Error(JSON.stringify(r));
      return `M with the right hand picked: its arrows (tool button "${r.btn}")`;
    });

    await step('the export: no new position track for any turned-only bone', async () => {
      const r = await page.evaluate(() => {
        const app = window.app, p = app.bake(), allowed = /^(b__Spine0__|b__Pelvis__|b__Tounge__1)$/;
        const out = [];
        p.actors.forEach((a, i) => { for (const [b, tr] of Object.entries(a.tracks)) if (tr.t && /^b__(Spine[12]|Neck|Head|[LR]_(Clavicle|UpperArm|Forearm|Hand|Thigh|Calf|Foot|Toe|Thumb\d|Index\d|Mid\d|Ring\d|Pinky\d))__$/.test(b) && !allowed.test(b)) out.push(i + ':' + b); });
        return out;
      });
      if (r.length) throw new Error(r.join(', '));
      return 'only the hips carry positions';
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
  const pass = P.report(rows, 'R turns, T moves, the circle moves the whole sim (Playwright, no game)');
  process.exit(pass ? 0 : 1);
})();
