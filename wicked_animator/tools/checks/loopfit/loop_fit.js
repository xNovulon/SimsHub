// "Fit to keys": the loop stops and repeats only as long as the keys placed, instead of playing on past them.
//   node tools/checks/loopfit/loop_fit.js [--port 8981]
// Starts tools/checks/lib/fake_game_server.py (a stand-in for the game, no game or Mods folder touched), opens the
// app on a fresh couple scene through Playwright (lib/pw.js) and checks project.fitLength / project.length directly
// through the in-page app and store - the fastest, least flaky way to pin down the numbers the spec asks for.
// Ports 8975-8995 only (never 8765/8766 - pw.js refuses those on its own).
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn } = require('child_process');
const P = require('../lib/pw.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const PORT = +(argv[argv.indexOf('--port') + 1] || 0) || 8981;
const OUT = path.join(ROOT, 'cache', 'checks', 'loopfit');

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
    try { const r = await fn(); ok(name, r !== false, typeof r === 'string' ? r : undefined); }
    catch (e) { ok(name, false, (e && e.message || String(e)).split('\n')[0]); }
  };
  try {
    const o = await P.open(PORT, { scene: 'couple' });
    browser = o.browser;
    const { page, logs } = o;
    await page.waitForFunction(() => window.app && window.app.simViews && window.app.simViews.size >= 2, null, { timeout: 30000 });
    await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true })));
    await page.waitForFunction(() => document.getElementById('home').classList.contains('hidden'), null, { timeout: 10000 });
    await P.sleep(500);

    // helpers in the page: the app's own methods, so a checkpoint/undo step is exactly what the owner would get
    await page.evaluate(() => {
      const app = window.app;
      window.__L = {
        p: () => app.store.project,
        simA: () => app.store.project.sims[0],
        simB: () => app.store.project.sims[1],
        // a plain body key at `frame` for sim A, through the real Key pose path (checkpoint + afterEdit + fit)
        keyAt: (frame, simIdx = 0) => {
          const s = app.store.project.sims[simIdx];
          app.selectSim(s.id);
          app.setFrame(frame);
          app.keyPose(s.id);
        },
      };
    });

    await step('fresh scene: 1 key/sim, no fit yet, Fit shown on', async () => {
      const r = await page.evaluate(() => ({ len: window.__L.p().length, fit: window.__L.p().fitLength, on: document.getElementById('btn-fit-length').classList.contains('on') }));
      if (!(r.len === 90 && r.fit !== false && r.on)) throw new Error(JSON.stringify(r));
      return `length ${r.len}, fitLength ${r.fit}, toggle on`;
    });

    await step('owner\'s example: keys at 0, 10, 20 -> loop fits to 30 frames (last 20 + gap 10)', async () => {
      await page.evaluate(() => { window.__L.keyAt(10); window.__L.keyAt(20); });
      const len = await page.evaluate(() => window.__L.p().length);
      if (len !== 30) throw new Error(`length is ${len}, wanted 30`);
      return `length is now ${len}`;
    });

    await step('the loop-end marker in the timeline sits at frame 30 (room drawn past it)', async () => {
      const r = await page.evaluate(() => {
        const app = window.app, tl = app.timeline;
        tl.draw();
        return { endX: tl._geo.endX, roomEndX: tl._geo.roomEndX, expectedEndX: tl.xAt(30) };
      });
      if (!(Math.abs(r.endX - r.expectedEndX) < 0.6 && r.roomEndX > r.endX)) throw new Error(JSON.stringify(r));
      return `endX ${r.endX.toFixed(1)} (expected ${r.expectedEndX.toFixed(1)}), roomEndX ${r.roomEndX.toFixed(1)}`;
    });

    await step('paused in the room (frame 35, inside roomEnd=40): the pose held at frame 29, not wrapped', async () => {
      const r = await page.evaluate(() => {
        const app = window.app, s = window.__L.simA();
        app.setFrame(35);
        const shownAtRoom = app.pipeline.keyed ? null : null; // placeholder (kept for readability)
        void shownAtRoom;
        const A = app.pipeline.entries().find(e => e.sim.id === s.id).v;
        const bones = A.byName ? Object.keys(A.byName).slice(0, 3) : [];
        const poseAtRoom = A.bones.map(b => b.quaternion.toArray());
        // reset, show frame 29 directly (playing mode has never been touched, so setFrame(29) is a plain, unwrapped read)
        app.setFrame(29);
        const poseAt29 = A.bones.map(b => b.quaternion.toArray());
        app.setFrame(35);
        const same = poseAtRoom.every((q, i) => q.every((x, k) => Math.abs(x - poseAt29[i][k]) < 1e-5));
        return { frame: app.store.frame, same, bones: bones.length };
      });
      if (!(r.frame === 35 && r.same)) throw new Error(JSON.stringify(r));
      return 'frame 35 shows exactly frame 29\'s pose (held, not wrapped)';
    });

    await step('K inside the room (frame 35) grows the loop to 50 (Fit on) in one undo step', async () => {
      const before = await page.evaluate(() => window.app.store.undo.length);
      await page.evaluate(() => { window.app.setFrame(35); window.__L.keyAt(35); });
      const r = await page.evaluate(() => ({ len: window.__L.p().length, hasKey: window.__L.simA().keys.some(k => k.frame === 35), undoLen: window.app.store.undo.length }));
      if (!(r.len === 50 && r.hasKey && r.undoLen === before + 1)) throw new Error(JSON.stringify({ ...r, before }));
      const back = await page.evaluate(() => { window.app.undo(); return { len: window.__L.p().length, hasKey: window.__L.simA().keys.some(k => k.frame === 35) }; });
      if (!(back.len === 30 && !back.hasKey)) throw new Error('undo did not revert key + length together: ' + JSON.stringify(back));
      await page.evaluate(() => window.app.redo());
      return 'length 30 -> 50 with the new key, one undo step reverts both';
    });

    await step('typing a length turns Fit off (one undo step)', async () => {
      const before = await page.evaluate(() => window.app.store.undo.length);
      await page.evaluate(() => {
        const el = document.getElementById('tl-seconds-in');
        el.value = '1.0';
        el.dispatchEvent(new Event('change', { bubbles: true }));
      });
      const r = await page.evaluate(() => ({ len: window.__L.p().length, fit: window.__L.p().fitLength, on: document.getElementById('btn-fit-length').classList.contains('on'), undoLen: window.app.store.undo.length }));
      if (!(r.len === 30 && r.fit === false && !r.on && r.undoLen === before + 1)) throw new Error(JSON.stringify({ ...r, before }));
      return `length ${r.len}, fitLength false, toggle off`;
    });

    await step('K in the room with Fit off grows the loop only to frame+1, not by the gap', async () => {
      await page.evaluate(() => { window.app.setFrame(40); window.__L.keyAt(40); });
      const r = await page.evaluate(() => ({ len: window.__L.p().length, fit: window.__L.p().fitLength }));
      if (!(r.len === 41 && r.fit === false)) throw new Error(JSON.stringify(r));
      return `length is exactly 41 (frame + 1), Fit stayed off`;
    });

    await step('turning Fit back on refits at once, in the same click', async () => {
      // typing "1.0" above retimed (stretched) the existing keys along with the length, as setLength always has -
      // Fit only decides whether *later* edits move the length, not what a deliberate retime does to it. The last
      // two keys are wherever that stretch put them; Fit re-derives the length from their new gap.
      const before = await page.evaluate(() => window.__L.simA().keys.map(k => k.frame));
      await page.evaluate(() => document.getElementById('btn-fit-length').click());
      const r = await page.evaluate(() => ({ len: window.__L.p().length, fit: window.__L.p().fitLength, on: document.getElementById('btn-fit-length').classList.contains('on') }));
      const want = before[before.length - 1] + (before[before.length - 1] - before[before.length - 2]);
      if (!(r.fit !== false && r.on && r.len === want)) throw new Error(JSON.stringify({ ...r, before, want }));
      return `Fit on, length refit to ${r.len} (last key ${before[before.length - 1]}, gap ${before[before.length - 1] - before[before.length - 2]})`;
    });

    await step('a sound past the fitted end keeps the length at the sound + 1 frame', async () => {
      const r = await page.evaluate(() => {
        const app = window.app, s = window.__L.simB();
        app.store.checkpoint('add test sound');
        s.sounds = s.sounds || [];
        s.sounds.push({ frame: 60, name: 'test.wav', kind: 'other' });
        app._applyFit();
        app.afterEdit();
        return { len: window.__L.p().length };
      });
      if (!(r.len >= 61)) throw new Error(JSON.stringify(r));
      return `length ${r.len} (>= sound frame + 1)`;
    });

    await step('the fitted length never falls below 12 frames', async () => {
      const r = await page.evaluate(() => {
        const app = window.app;
        app.newScene(false, false, 'solo', null);
      });
      void r;
      await P.sleep(300);
      await page.evaluate(() => { window.__L.keyAt(0); window.__L.keyAt(1); });
      const len = await page.evaluate(() => window.__L.p().length);
      if (len !== 12) throw new Error(`length is ${len}, wanted the 12-frame floor`);
      return `two keys 1 frame apart -> length floored at ${len}`;
    });

    await step('deleting the last key shrinks the fit', async () => {
      await page.evaluate(() => { window.__L.keyAt(20); }); // 0, 1, 20 -> last 20, gap 19 -> 39
      const grown = await page.evaluate(() => window.__L.p().length);
      const r = await page.evaluate(() => {
        const app = window.app, s = window.__L.simA();
        const key = s.keys.find(k => k.frame === 20);
        app.timeline.selectOnly([app.timeline.sel ? [...app.timeline.sel][0] : null].filter(Boolean));
        // select the key directly (KO id) then delete through the real selection path
        const KOid = `k|${s.id}|20`;
        app.timeline.selectOnly([KOid]);
        app.deleteSelectedKeys();
        void key;
        return { len: window.__L.p().length, has20: s.keys.some(k => k.frame === 20) };
      });
      if (!(grown === 39 && r.len === 12 && !r.has20)) throw new Error(JSON.stringify({ grown, ...r }));
      return `39 -> ${r.len} after deleting the last key (back to the 0/1 pair, floored at 12)`;
    });

    await step('Magic keeps the length it was given until Fit is switched on by hand', async () => {
      const r = await page.evaluate(() => {
        const app = window.app;
        const p = app.store.project;
        p.length = 77;
        p.fitLength = false;
        const before = p.length;
        app._applyFit();
        return { before, after: app.store.project.length, fit: app.store.project.fitLength };
      });
      if (!(r.fit === false && r.before === r.after)) throw new Error(JSON.stringify(r));
      return `length stayed ${r.after} with Fit off (as Magic/imports/mocap leave it)`;
    });

    await step('an old save (no fitLength field) loads with Fit off', async () => {
      const r = await page.evaluate(async () => {
        const app = window.app;
        const { newProject } = await import('/js/state.js');
        const legacy = newProject();
        delete legacy.fitLength;
        legacy.sims.push({ id: 's1', label: 'F', frame: 'yf', gender: 'FEMALE', color: '#fff', skin: '#fff', keys: [{ frame: 0, ease: 'auto', pose: { rot: {}, pos: {} } }], pins: {}, sounds: [], layers: [] });
        app.store.load(legacy);
        return { fit: app.store.project.fitLength };
      });
      if (r.fit !== false) throw new Error(JSON.stringify(r));
      return 'legacy project without fitLength loads with fitLength === false';
    });

    await step('export bakes exactly length frames', async () => {
      const r = await page.evaluate(() => {
        const app = window.app;
        app.newScene(false, false, 'couple', null);
        return true;
      });
      void r;
      await P.sleep(300);
      await page.evaluate(() => { window.__L.keyAt(10); window.__L.keyAt(20); }); // -> length 30
      const r2 = await page.evaluate(() => {
        const app = window.app, payload = app.bake();
        const tr = payload.actors[0].tracks;
        const anyBone = Object.values(tr).find(t => t.r) || Object.values(tr).find(t => t.t);
        return { frames: payload.frames, len: app.store.project.length, trackLen: anyBone ? (anyBone.r || anyBone.t).length : -1 };
      });
      if (!(r2.frames === 30 && r2.len === 30 && r2.trackLen === 30)) throw new Error(JSON.stringify(r2));
      return `bake() reports ${r2.frames} frames, every track has ${r2.trackLen} samples`;
    });

    await step('dragging a key later (timeline.js _up) grows the fit the same way keying does', async () => {
      const r = await page.evaluate(() => {
        const app = window.app, s = window.__L.simA();
        app.newScene(false, false, 'couple', null);
        return true;
      });
      void r;
      await P.sleep(300);
      await page.evaluate(() => { window.__L.keyAt(10); window.__L.keyAt(20); }); // -> length 30
      const before = await page.evaluate(() => window.app.store.undo.length);
      const r2 = await page.evaluate(async () => {
        const app = window.app, KO = await import('/js/keyops.js'), s = window.__L.simA();
        // exactly what timeline.js's _up() does for a completed key drag: checkpoint, KO.moveSel, then _applyFit
        app.store.checkpoint('Move key');
        const sel = new Set([`k|${s.id}|20`]);
        // KO.moveSel keeps the whole selection inside the current loop (L-1), same as a real drag can never pull a
        // key past the loop's own end - it lands at 29 (length 30 -> max frame 29), gap becomes 29-10=19
        KO.moveSel(app.store.project, sel, 15);
        app._applyFit();
        app.afterEdit();
        return { len: app.store.project.length, frames: s.keys.map(k => k.frame).sort((a, b) => a - b) };
      });
      const after = await page.evaluate(() => window.app.store.undo.length);
      if (!(r2.len === 48 && after === before + 1)) throw new Error(JSON.stringify({ r2, before, after }));
      const back = await page.evaluate(() => { window.app.undo(); return window.app.store.project.length; });
      if (back !== 30) throw new Error('undo did not restore the pre-drag length: ' + back);
      return `dragging the last key to frame 29 (gap 19) grew the loop to ${r2.len}, undo restored ${back}`;
    });

    await step('playback never enters the room', async () => {
      const r = await page.evaluate(() => new Promise(res => {
        const app = window.app;
        app.setFrame(app.store.project.length - 5);
        app.setPlaying(true);
        let maxFrame = app.store.frame, ticks = 0;
        const iv = setInterval(() => {
          maxFrame = Math.max(maxFrame, app.store.frame);
          ticks++;
          if (ticks > 40) { clearInterval(iv); app.setPlaying(false); res({ maxFrame, len: app.store.project.length }); }
        }, 30);
      }));
      if (!(r.maxFrame < r.len)) throw new Error(JSON.stringify(r));
      return `frame never reached ${r.len} while playing (max seen ${r.maxFrame.toFixed(1)})`;
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
  const pass = P.report(rows, 'Fit to keys: the loop stops and repeats only as long as the keys placed (Playwright, no game)');
  process.exit(pass ? 0 : 1);
})();
