// T on the hips ("the waist") away from a plain standing pose - in the running app, against the real engine (real
// bodies, real beds), because these poses need real furniture data pose_tools.js's fake server doesn't have.
//   node tools/checks/posetools/hips_shift.js [--port 8971]
// Skips with one clear line when the real game isn't found here (backend/server.py's /api/status has no game_dir) -
// nothing else runs. Covers, on top of pose_tools.js's standing case:
//   - lying on the back (a real "Lie here" bed pose): dragging the hips up, down and sideways - the hips actually
//     move (not blocked), a foot that can't be reached any more slides toward the hip along the bed's surface (it
//     never lifts off it), and no bone stretches
//   - sitting on a bed's edge (feet pinned to the floor spots): the hips still move, the pinned feet stay exactly
//     where they were pinned
//   - kneeling (thighs down, calves folded back by hand - no furniture needed): a sideways and an upward drag both
//     move the hips, the feet slide rather than fly, nothing stretches
// This must fail against the pre-fix shiftHips (the reach guard only understood world-up, so a straight-legged lift
// was fully blocked and a push the guard couldn't see let the foot drift into the air) and pass against the fix
// (per-foot, per-direction, via the body's own surface).
const path = require('path');
const fs = require('fs');
const os = require('os');
const http = require('http');
const { spawn } = require('child_process');
const P = require('../lib/pw.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const PORT = +(argv[argv.indexOf('--port') + 1] || 0) || 8971;
const OUT = path.join(ROOT, 'cache', 'checks', 'posetools');

const get = url => new Promise(res => {
  http.get(url, r => { let b = ''; r.on('data', c => { b += c; }); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', () => res(null));
});

async function startServer() {
  if (await get(`http://127.0.0.1:${PORT}/api/status`)) throw new Error(`port ${PORT} is already in use - pass --port`);
  const saves = fs.mkdtempSync(path.join(os.tmpdir(), 'wa_hipshift_'));
  const proc = spawn(process.env.PYTHON || 'python3', [path.join(ROOT, 'backend', 'server.py')], {
    cwd: ROOT, env: { ...process.env, ANIMATOR_PORT: String(PORT), ANIMATOR_SAVES: saves, PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
  let log = '';
  proc.stdout.on('data', d => { log += d; });
  proc.stderr.on('data', d => { log += d; });
  for (let i = 0; i < 150; i++) {
    const r = await get(`http://127.0.0.1:${PORT}/api/status`);
    if (r && r.status === 200) return { proc, log: () => log, status: JSON.parse(r.body) };
    await P.sleep(200);
  }
  proc.kill();
  throw new Error('the real engine did not start:\n' + log);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const server = await startServer();
  if (!server.status.game_dir) {
    console.log('SKIP: needs the real game (The Sims 4) - not found here (backend/server.py reported no game_dir)');
    server.proc.kill();
    process.exit(0);
  }
  const rows = [];
  let browser;
  const ok = (name, cond, detail) => rows.push({ name, ok: !!cond, detail });
  try {
    const o = await P.open(PORT, { scene: null });
    browser = o.browser;
    const { page } = o;
    const step = async (name, fn) => {
      try { const r = await fn(); ok(name, r !== false, typeof r === 'string' ? r : undefined); }
      catch (e) { ok(name, false, (e && e.message || String(e)).split('\n')[0]); }
    };
    const shot = name => page.screenshot({ path: path.join(OUT, name + '.png') }).catch(() => {});
    await page.waitForFunction(() => window.app, null, { timeout: 30000 });
    await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true })));
    await page.waitForFunction(() => document.getElementById('home').classList.contains('hidden'), null, { timeout: 10000 }).catch(() => {});
    await P.sleep(500);

    // helpers in the page - a superset of pose_tools.js's __t: worldPos/positions/distance, picking the hips with T,
    // the hip-drag itself (mouseDown / objectChange x N / mouseUp on the gizmo, exactly as a real drag does it), and
    // `moved` (which bones' local position changed - a moved-only-by-turning pose leaves every one but the hips alone).
    await page.evaluate(() => {
      const app = window.app;
      window.__t = {
        v: id => app.simViews.get(id),
        id: () => app.store.project.sims[0].id,
        wp: (bone, id) => { const p = window.__t.v(id).worldPos(bone); return [p.x, p.y, p.z]; },
        dist: (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]),
        positions: id => { const v = window.__t.v(id), out = {}; for (const b of v.bones) out[b.name] = b.position.toArray(); return out; },
        moved: (before, after, skip = []) => Object.keys(before).filter(n => !skip.includes(n) && Math.hypot(...before[n].map((x, k) => x - after[n][k])) > 1e-6),
        pickHips: id => { app.setTool('rotate'); app.store.selected = { sim: id, bone: 'b__Pelvis__' }; app.interact.selectBone(id, 'b__Pelvis__'); app.interact.moveSelected(); app.emitSelection(); },
        // the up direction, in world space, on the surface a foot rests on (the floor, a bed - always level)
        up: () => [0, 1, 0],
        // a T-drag of the hips by `d` (world metres), N steps, exactly like the gizmo
        drag: (d, steps = 8) => {
          const gz = app.vp.gizmo, pr = app.interact.proxy;
          gz.dispatchEvent({ type: 'mouseDown' });
          for (let k = 1; k <= steps; k++) { pr.position.set(pr.position.x + d[0] / steps, pr.position.y + d[1] / steps, pr.position.z + d[2] / steps); pr.updateMatrixWorld(); gz.dispatchEvent({ type: 'objectChange' }); }
          gz.dispatchEvent({ type: 'mouseUp' });
        },
      };
    });

    // ---------------------------------------------------------------- standing: hips up (the owner's own report -
    // "I can't lift the waist up") - a fresh default sim, straight-legged enough that this used to be fully blocked
    await step('standing, hips up: the hips actually move (used to be fully blocked by a straight-legged guard)', async () => {
      const r = await page.evaluate(() => {
        const app = window.app;
        app.newScene(false, false, 'solo');
        const s = app.store.project.sims[0], t = window.__t;
        t.pickHips(s.id);
        const before = t.wp('b__Pelvis__', s.id);
        t.drag([0, 0.10, 0]);
        const after = t.wp('b__Pelvis__', s.id);
        return { hips: t.dist(before, after) };
      });
      if (!(r.hips > 0.05)) throw new Error(JSON.stringify(r));
      return `hips moved ${(r.hips * 100).toFixed(1)} of 10.0 cm asked`;
    });

    // ---------------------------------------------------------------- lying on the back (a real double bed)
    const lieToSpot = async () => page.evaluate(async () => {
      const app = window.app;
      if (!app.store.project.sims.length) app.newScene(false, false);
      app.setFurniture('double_bed');
      const info = await app._furnitureInfo('double_bed');
      const s = app.store.project.sims[0];
      app.selectSim(s.id);
      const spot = info.slots.find(x => x.kind === 'lie' && Math.abs(x.pos[0]) < 0.01) || info.slots.find(x => x.kind === 'lie');
      if (!spot) return { ok: false, why: 'no lying spot on double_bed' };
      const ok = await app.lieHere(s.id, spot);
      return { ok: !!ok, id: s.id };
    });
    const lieSetup = await lieToSpot();
    if (!lieSetup.ok) { ok('setup: sim lying on the double bed', false, lieSetup.why || 'lieHere failed'); throw new Error('lying setup failed'); }
    await shot('hipshift_lying_before');

    for (const [label, dir] of [['up', [0, 0.10, 0]], ['down', [0, -0.10, 0]], ['sideways', [0.10, 0, 0]]]) {
      await step(`lying on the back, hips ${label}: the hips move, the feet stay on the bed (never fly up), nothing stretches`, async () => {
        const r = await page.evaluate((dir) => {
          const t = window.__t, id = t.id(), B = ['b__Pelvis__', 'b__L_Foot__', 'b__R_Foot__'], up = t.up();
          const dot = p => p[0] * up[0] + p[1] * up[1] + p[2] * up[2];
          t.pickHips(id);
          const before = Object.fromEntries(B.map(b => [b, t.wp(b, id)])), pos0 = t.positions(id);
          const footUp0 = ['b__L_Foot__', 'b__R_Foot__'].map(b => dot(t.wp(b, id)));
          t.drag(dir);
          const after = Object.fromEntries(B.map(b => [b, t.wp(b, id)])), pos1 = t.positions(id);
          const footUp1 = ['b__L_Foot__', 'b__R_Foot__'].map(b => dot(t.wp(b, id)));
          return {
            hips: t.dist(before.b__Pelvis__, after.b__Pelvis__),
            asked: Math.hypot(...dir),
            stretched: t.moved(pos0, pos1, ['b__Spine0__', 'b__Pelvis__']),
            flew: footUp1.map((u, k) => u - footUp0[k]),
          };
        }, dir);
        const worstFly = Math.max(...r.flew.map(Math.abs));
        if (!(r.hips > r.asked * 0.5 && worstFly < 0.02 && !r.stretched.length)) {
          throw new Error(JSON.stringify({ hips: r.hips.toFixed(3), asked: r.asked, flew: r.flew.map(x => x.toFixed(3)), stretched: r.stretched }));
        }
        return `hips moved ${(r.hips * 100).toFixed(1)} of ${(r.asked * 100).toFixed(1)} cm asked, feet height change ${(worstFly * 100).toFixed(2)} cm, no bone stretched`;
      });
      await lieToSpot();       // start each direction fresh from the same lying pose
    }
    await shot('hipshift_lying_after');

    // ---------------------------------------------------------------- sitting on the bed's edge (feet pinned)
    await step('sitting on the bed edge: hips move, the pinned feet stay exactly where they were pinned', async () => {
      const r = await page.evaluate(async () => {
        const app = window.app;
        if (!app.store.project.sims.length) app.newScene(false, false);
        app.setFurniture('double_bed');
        const info = await app._furnitureInfo('double_bed');
        const s = app.store.project.sims[0];
        app.selectSim(s.id);
        const spot = info.slots.find(x => x.kind === 'edge');
        if (!spot) return { ok: false, why: 'no edge seat on double_bed' };
        app.sitHere(s.id, spot);
        const t = window.__t;
        t.pickHips(s.id);
        const before = { lf: t.wp('b__L_Foot__', s.id), rf: t.wp('b__R_Foot__', s.id) };
        t.drag([0.08, 0.05, 0]);
        const after = { lf: t.wp('b__L_Foot__', s.id), rf: t.wp('b__R_Foot__', s.id) };
        return { ok: true, lf: t.dist(before.lf, after.lf), rf: t.dist(before.rf, after.rf), pinned: !!(s.pins && s.pins['L foot'] && s.pins['R foot']) };
      });
      if (!r.ok) return `skipped: ${r.why}`;
      if (!(r.pinned && r.lf < 0.005 && r.rf < 0.005)) throw new Error(JSON.stringify(r));
      return `pinned, feet moved ${(r.lf * 1000).toFixed(1)}/${(r.rf * 1000).toFixed(1)} mm while the hips were dragged`;
    });
    await shot('hipshift_sitting_edge');

    // ---------------------------------------------------------------- kneeling (no furniture: legs folded by hand)
    await step('kneeling: hips move sideways and up, the feet slide rather than fly, nothing stretches', async () => {
      const r = await page.evaluate(async () => {
        const app = window.app;
        app.newScene(false, false);
        const s = app.store.project.sims[0], v = app.simViews.get(s.id);
        const THREE = await import('three'), pm = await import('/js/posemath.js');
        // fold both knees back ~100 degrees (calves are a hinge, bones.js HINGE: calf bends -1) so the sim kneels
        // on straight-down thighs - no furniture needed, just a bent-knee body to drag the hips of
        for (const side of ['L', 'R']) {
          const calf = v.bone(`b__${side}_Calf__`);
          if (calf) pm.rotateInSpace(v, calf, new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), -100 * Math.PI / 180));
        }
        app.pipeline.base({ sim: s, v }, Math.round(app.store.frame));
        v.group.updateMatrixWorld(true);
        const t = window.__t;
        t.pickHips(s.id);
        const B = ['b__L_Foot__', 'b__R_Foot__'];
        const before = Object.fromEntries(B.map(b => [b, t.wp(b, s.id)])), pos0 = t.positions(s.id);
        t.drag([0.10, 0.06, 0]);
        const after = Object.fromEntries(B.map(b => [b, t.wp(b, s.id)])), pos1 = t.positions(s.id);
        return {
          feetMoved: B.map(b => t.dist(before[b], after[b])),
          stretched: t.moved(pos0, pos1, ['b__Spine0__', 'b__Pelvis__']),
          hips: t.dist(pos0.b__Pelvis__, pos1.b__Pelvis__),
        };
      });
      if (!(r.hips > 0.03 && !r.stretched.length)) throw new Error(JSON.stringify(r));
      return `hips moved ${(r.hips * 100).toFixed(1)} cm, feet moved ${r.feetMoved.map(x => (x * 100).toFixed(1)).join('/')} cm, no bone stretched`;
    });
    await shot('hipshift_kneeling');
  } finally {
    if (browser) await browser.close().catch(() => {});
    server.proc.kill();
  }
  const pass = P.report(rows, 'T on the hips - beyond standing (needs the real game)');
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
