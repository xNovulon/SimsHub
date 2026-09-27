// Random voices (autovoice.js), in the real app (Playwright + tools/checks/lib/fake_game_server.py - no game
// needed; the voice catalogue is stood in by hand below so the check is the same on every PC).
//   node tools/checks/voices/random_voices.js [--port 8946] [--keep]
// Covers: random cues never enter sim.sounds (so the timeline, drag and export-of-legacy-only stay untouched),
// they are spaced apart from each other and from every other voice, the mouth moves for them in preview, the
// switch ("Pick a sound here") still puts a voice at an exact, drawn, draggable frame, claps and your own sound
// files are left alone, an old project's voices keep their times, a project with random voices only still bakes
// voice sound events for the export, and baking a saved-but-not-open animation (app.bakeOther - "Export a mod",
// "Update in my game" on several at once) moves the mouth for them exactly like baking the open one does.
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn } = require('child_process');
const P = require('../lib/pw.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const PORT = +(argv[argv.indexOf('--port') + 1] || 0) || 8946;
const KEEP = argv.includes('--keep');
const OUT = path.join(ROOT, 'cache', 'checks', 'voices');

const get = url => new Promise(res => {
  http.get(url, r => { let b = ''; r.on('data', c => { b += c; }); r.on('end', () => res({ status: r.statusCode, body: b })); }).on('error', () => res(null));
});

async function startServer() {
  const up = await get(`http://127.0.0.1:${PORT}/api/status`);
  if (up) throw new Error(`port ${PORT} is already in use - pass --port`);
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
  throw new Error('the fake-game server did not start:\n' + log);
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
    const requests = [];
    page.on('request', r => { if (/\/api\/sound\?/.test(r.url())) requests.push(r.url()); });

    // ---------------------------------------------------------------- a fixed voice catalogue (no game needed)
    await page.evaluate(() => {
      window.app.voiceLines = [
        { name: 'vo_test_moan_fa_1', voices: ['fa'], tags: ['moan'], sec: 1.2, lowprob: false, gender: 'f' },
        { name: 'vo_test_moan_fa_2', voices: ['fa'], tags: ['moan'], sec: 1.0, lowprob: false, gender: 'f' },
        { name: 'vo_test_moan_fa_3', voices: ['fa'], tags: ['moan'], sec: 1.4, lowprob: false, gender: 'f' },
        { name: 'vo_test_moan_ma_1', voices: ['ma'], tags: ['moan'], sec: 1.2, lowprob: false, gender: 'm' },
        { name: 'vo_test_moan_ma_2', voices: ['ma'], tags: ['moan'], sec: 1.0, lowprob: false, gender: 'm' },
      ];
      window.app.sounds = [];
    });

    // ---------------------------------------------------------------- 1. the switch: on, off, and what it changes
    const r1 = await page.evaluate(() => {
      const out = [], C = (n, c, d) => out.push([n, !!c, d]);
      const app = window.app, p = app.store.project, F = p.sims.find(s => s.frame !== 'ym'), M = p.sims.find(s => s.frame === 'ym');
      app.setLength(900, 'stretch');           // 30 s at 30 fps: room for several cues without crowding
      C('random voices: off by default on a new sim', !F.autoVoice, F.autoVoice);
      const added = app.randomVoices(F.id, 'moan', 3);
      C('randomVoices(...) reports it turned on', added === 1, added);
      C('the switch is sim.autoVoice = {on, set, every, shuffle}', F.autoVoice && F.autoVoice.on === true && F.autoVoice.set === 'moan' && F.autoVoice.every === 3 && typeof F.autoVoice.shuffle === 'number', F.autoVoice);
      C('nothing was written to sim.sounds (not on the timeline)', (F.sounds || []).length === 0, F.sounds);
      const cues = app.autoVoiceCuesFor(F);
      C('the scheduler made cues for it, all kind "voice"', cues.length > 0 && cues.every(c => c.kind === 'voice'), cues.length);
      const cues2 = app.autoVoiceCuesFor(F);
      C('the same schedule comes back until Shuffle is pressed (deterministic seed)', JSON.stringify(cues) === JSON.stringify(cues2), '');
      app.shuffleAutoVoice(F.id);
      const cues3 = app.autoVoiceCuesFor(F);
      C('Shuffle changes the pattern', JSON.stringify(cues) !== JSON.stringify(cues3), { before: cues.map(c => c.frame), after: cues3.map(c => c.frame) });
      app.clearAutoVoice(F.id);
      C('turning it off clears sim.autoVoice', !F.autoVoice, F.autoVoice);
      C('...and the scheduler then makes nothing for it', app.autoVoiceCuesFor(F).length === 0, app.autoVoiceCuesFor(F));
      // back on for the checks below - "Rarely" (fewer cues) so the spacing check has room to hold every pair, not
      // just most of them ("accepted anyway" is the honest fallback for a crowded pace, not the normal case)
      app.randomVoices(F.id, 'moan', 6);
      app.randomVoices(M.id, 'moan', 6);
      return { checks: out };
    });
    for (const [n, c, d] of r1.checks) ok(n, c, d);

    // ---------------------------------------------------------------- 2. spacing: own cues, and across the two sims
    const r2 = await page.evaluate(() => {
      const out = [], C = (n, c, d) => out.push([n, !!c, d]);
      const app = window.app, p = app.store.project, F = p.sims.find(s => s.frame !== 'ym'), M = p.sims.find(s => s.frame === 'ym');
      const fps = p.fps, L = p.length;
      const gap = (a, b) => { const d = Math.abs(a - b) % L; return Math.min(d, L - d); };
      const fCues = app.autoVoiceCuesFor(F), mCues = app.autoVoiceCuesFor(M);
      const ownMin = Math.round(Math.max(1.6, F.autoVoice.every * 0.45) * fps);
      let ownGaps = [];
      for (let i = 0; i < fCues.length; i++) for (let j = i + 1; j < fCues.length; j++) ownGaps.push(gap(fCues[i].frame, fCues[j].frame));
      C(`Female's own cues never sit closer than ${ownMin} frames (its "not too close" floor)`, fCues.length < 2 || Math.min(...ownGaps) >= ownMin, { min: Math.min(...ownGaps), want: ownMin, frames: fCues.map(c => c.frame) });
      let crossGaps = [];
      for (const a of fCues) for (const b of mCues) crossGaps.push(gap(a.frame, b.frame));
      const crossMin = Math.round(0.9 * fps);
      C('the two sims\' random voices never land on top of each other', crossGaps.length === 0 || Math.min(...crossGaps) >= crossMin, { min: Math.min(...crossGaps), want: crossMin });
      return { checks: out };
    });
    for (const [n, c, d] of r2.checks) ok(n, c, d);

    // ---------------------------------------------------------------- 3. claps and your own sound files: untouched
    const r3 = await page.evaluate(() => {
      const out = [], C = (n, c, d) => out.push([n, !!c, d]);
      const app = window.app, p = app.store.project, F = p.sims.find(s => s.frame !== 'ym');
      const before = JSON.stringify(F.sounds);
      F.sounds = [{ frame: 5, name: 'clap_test', kind: 'clap' }, { frame: 200, name: 'WA_myfile.wav', kind: 'other' }];
      app.afterEdit();
      const cues = app.autoVoiceCuesFor(F);
      C('a clap and an own sound file are not touched by the scheduler', cues.every(c => c.name !== 'clap_test' && c.name !== 'WA_myfile.wav'), cues.map(c => c.name));
      C('they stay exactly where they were put', F.sounds.some(x => x.frame === 5 && x.kind === 'clap') && F.sounds.some(x => x.frame === 200 && x.kind === 'other'), F.sounds);
      return { checks: out, data: { before } };
    });
    for (const [n, c, d] of r3.checks) ok(n, c, d);

    // ---------------------------------------------------------------- 4. "Pick a sound here": a set-time voice
    const r4 = await page.evaluate(async () => {
      const out = [], C = (n, c, d) => out.push([n, !!c, d]);
      const app = window.app, p = app.store.project, F = p.sims.find(s => s.frame !== 'ym');
      const KO = await import('/js/keyops.js');
      const frame = 60;
      app.store.checkpoint();
      const snd = { frame, name: 'vo_test_moan_fa_1', kind: 'voice' };
      F.sounds.push(snd);
      app.afterEdit();
      C('a sound picked at a frame goes on the timeline (sim.sounds)', F.sounds.includes(snd), F.sounds.length);
      const cuesBefore = app.autoVoiceCuesFor(F);
      C('random cues stay a separate list from it', !cuesBefore.some(c => c === snd), '');
      // draggable: keyops.moveSel is what a timeline drag calls
      const id = KO.sndId(F.id, snd);
      const moved = KO.moveSel(p, new Set([id]), 12);
      const newId = KO.sndId(F.id, snd);
      C('dragging it (keyops.moveSel) moves its frame and nothing else', snd.frame === frame + 12 && moved.sel.has(newId), snd.frame);
      app.afterEdit();
      const baked = app.bake();
      const a = baked.actors[p.sims.indexOf(F)];
      C('it is baked at its exact frame, kind "voice"', a && a.sounds.some(x => x.frame === snd.frame && x.name === snd.name && x.kind === 'voice'), a && a.sounds);
      return { checks: out };
    });
    for (const [n, c, d] of r4.checks) ok(n, c, d);

    // ---------------------------------------------------------------- 5. old projects: legacy voices keep their time
    const r5 = await page.evaluate(() => {
      const out = [], C = (n, c, d) => out.push([n, !!c, d]);
      const app = window.app;
      const legacy = { name: 'Legacy', author: 'Test', version: 3, length: 90, fps: 30, loop: true,
        sims: [{ id: 'legacy-sim', label: 'Female 1', frame: 'yf', gender: 'FEMALE', color: '#fff', skin: 0, keys: [{ frame: 0, pose: {} }],
          pins: {}, sounds: [{ frame: 42, name: 'vo_expr_moan_pleasure_30f_cm', kind: 'voice', auto: true }], layers: [], visible: true }] };
      app.store.load(JSON.parse(JSON.stringify(legacy)));
      const s = app.store.project.sims[0];
      C('a voice saved by an older version keeps its exact frame', s.sounds.length === 1 && s.sounds[0].frame === 42 && s.sounds[0].kind === 'voice', s.sounds);
      C('loading never invents an autoVoice field for it', !s.autoVoice, s.autoVoice);
      return { checks: out };
    });
    for (const [n, c, d] of r5.checks) ok(n, c, d);

    // ---------------------------------------------------------------- 6. export: random-only still yields voice events
    const r6 = await page.evaluate(() => {
      const out = [], C = (n, c, d) => out.push([n, !!c, d]);
      const app = window.app;
      app.newScene(false, false, 'solo');
      const p = app.store.project, F = p.sims[0];
      app.setLength(300, 'stretch');
      app.randomVoices(F.id, 'moan', 3);
      C('random-only: no manual voice sounds before export', (F.sounds || []).filter(x => x.kind === 'voice').length === 0, F.sounds);
      const baked = app.bake();
      const a = baked.actors[0];
      C('the bake still lists voice sound events for it', a.sounds.some(x => x.kind === 'voice'), a.sounds);
      C('...and the mouth is flagged as moving (so the game does not lip-sync over it)', a.mouthMoves === true, a.mouthMoves);
      return { checks: out };
    });
    for (const [n, c, d] of r6.checks) ok(n, c, d);

    // ---------------------------------------------------------------- 6b. "Export a mod" / sending a saved-but-not-
    // open animation (share.js bakeByUid -> app.bakeOther): its throwaway pipeline must move the mouth for random
    // voices too, exactly like baking the open project does above
    const r6b = await page.evaluate(async () => {
      const out = [], C = (n, c, d) => out.push([n, !!c, d]);
      const app = window.app;
      app.newScene(false, false, 'solo');
      const p = app.store.project, F = p.sims[0];
      app.setLength(300, 'stretch');
      app.randomVoices(F.id, 'moan', 3);
      const direct = app.bake();
      const other = await app.bakeOther(JSON.parse(JSON.stringify(p)));
      const a = other.actors[0];
      C('bakeOther also lists the random voice sound events', a.sounds.some(x => x.kind === 'voice'), a.sounds);
      C('bakeOther flags the mouth as moving too (not just the open project\'s own bake)', a.mouthMoves === true, { direct: direct.actors[0].mouthMoves, other: a.mouthMoves });
      return { checks: out };
    });
    for (const [n, c, d] of r6b.checks) ok(n, c, d);

    // ---------------------------------------------------------------- 7. the mouth moves for a random voice, live
    const r7 = await page.evaluate(() => {
      const out = [], C = (n, c, d) => out.push([n, !!c, d]);
      const app = window.app;
      app.newScene(false, false, 'solo');
      const p = app.store.project, F = p.sims[0];
      app.setLength(300, 'stretch');
      app.randomVoices(F.id, 'moan', 3);
      const cue = app.autoVoiceCuesFor(F)[0];
      if (!cue) return { checks: [['(no cue to test - the pool was empty)', false, '']] };
      // no face keys and blinking off: lastFace is legitimately null where nothing overlays the (absent) face -
      // same as an empty mouth
      const openAt = f => { app.pipeline.apply(f); const face = app.pipeline.lastFace.get(F.id); return (face && face.open) || 0; };
      const before = openAt(Math.max(0, cue.frame - 20));
      // the swell starts at 0 right at the cue's own frame (talkAt's envelope) - it peaks a little into it
      let peak = 0; for (let d = 1; d <= 15; d++) peak = Math.max(peak, openAt(cue.frame + d));
      C('the mouth opens for a random voice cue that is not in sim.sounds', peak > before + 0.05, { before, peak, cueFrame: cue.frame });
      return { checks: out };
    });
    for (const [n, c, d] of r7.checks) ok(n, c, d);

    // ---------------------------------------------------------------- 8. preview plays them, spaced apart
    requests.length = 0;
    const r8 = await page.evaluate(async () => {
      const app = window.app;
      app.newScene(false, false, 'solo');
      const p = app.store.project, F = p.sims[0];
      app.setLength(300, 'stretch');
      app.randomVoices(F.id, 'moan', 3);
      app.audio.setMuted(false);
      const cues = app.autoVoiceCuesFor(F);
      for (const c of cues) app._playSounds(Math.max(0, c.frame - 1), c.frame);
      return { names: cues.map(c => c.name) };
    });
    const played = requests.map(u => decodeURIComponent((/name=([^&]+)/.exec(u) || [])[1] || ''));
    ok('preview: crossing each cue\'s frame fetches its sound (/api/sound?...)', r8.names.length > 0 && r8.names.every(n => played.includes(n)),
      { scheduled: r8.names, requested: played });

    const expected = [/Failed to load resource/, /GPU stall|WebGL|swiftshader|GroupMarkerNotSet/i, /fonts\.googleapis/];
    const errs = P.problems(logs, { ignore: expected });
    ok('no uncaught errors, failed module loads or console errors', !errs.length, errs.slice(0, 6).map(e => `${e.type}: ${e.text.slice(0, 200)}`).join(' | ') || 'clean');
  } catch (e) {
    ok('the check ran to the end', false, e.stack || String(e));
  } finally {
    if (browser && !KEEP) await browser.close();
    server.proc.kill();
  }
  const pass = P.report(rows, 'Random voices (autovoice.js) in the real app');
  process.exit(pass ? 0 : 1);
})();
