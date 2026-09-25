// R2-4 browser checks: voices, moments, effects and cum on the skin (spec_game 2-5 "Verify").
//   node tools/checks/r2-4/game_ui_check.js <port> [--pin <dir>] [--out <file.json>]
// Uses the test harness (every writing route is answered in the browser; nothing reaches the game folders). Writes
// its results to cache/checks/r2-4/ui_report.json and the 4-moment proto's bake to cache/checks/r2-4/proto.baked.json
// (game_check.py builds that package offline in %TEMP% and compares the XML). Exits 0 only when every item passes.
const path = require('path'), fs = require('fs');
const H = require('../lib/harness.js');
const { pinFiles } = require('./pin.js');

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 && argv[i + 1] ? argv[i + 1] : d; };
const PORT = +argv[0];
const PIN = arg('--pin', null);
const OUT_DIR = path.join(H.ROOT, 'cache', 'checks', 'r2-4');
const OUT = arg('--out', path.join(OUT_DIR, 'ui_report.json'));
if (!PORT || H.REFUSED.has(PORT) || [8802, 8804].includes(PORT)) { console.error('usage: node game_ui_check.js <port> (not 8765/8766/8777/8802/8804)'); process.exit(2); }
const sleep = ms => new Promise(r => setTimeout(r, ms));
const rows = [];
const check = (name, ok, detail) => { rows.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  ${detail === undefined ? '' : JSON.stringify(detail).slice(0, 300)}`); };

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const { browser, page, logs } = await H.open(PORT, { w: 1366, h: 768, args: ['--autoplay-policy=no-user-gesture-required'], beforeLoad: PIN ? p => pinFiles(p, PIN) : null });
  const requests = [], bad = [];
  page.on('request', r => { if (/\/api\/sound\?/.test(r.url())) requests.push(r.url()); });
  page.on('response', r => { if (r.status() >= 400 && !/favicon/.test(r.url())) bad.push(`${r.status()} ${r.url().replace(/^https?:\/\/[^/]+/, '')}`); });
  const pe = (fn, ...a) => page.evaluate(fn, ...a);
  const run = async (name, fn, ...a) => {
    try {
      const res = await pe(fn, ...a);
      for (const [n, ok, d] of res.checks || []) check(`${name}: ${n}`, ok, d);
      return res;
    } catch (e) { check(`${name} (crashed)`, false, String(e.message || e).slice(0, 300)); return {}; }
  };

  // ------------------------------------------------------------------ helpers in the page
  await pe(async () => {
    const app = window.app;
    (await import('/js/home.js')).hideHome(app);
    window.__r24 = {
      M: await import('/js/moments.js'), Cum: await import('/js/cumskin.js'), A: await import('/js/audio.js'), FX: await import('/js/effects.js'),
      G: await import('/js/features/game.js'),
      couple(opts = {}) {
        app.newScene(false, false, opts.template || 'couple');
        const p = app.store.project;
        p.name = 'R24 check'; p.author = 'R24';
        if (opts.seconds) app.setLength(opts.seconds * p.fps, 'stretch');
        const F = p.sims.find(s => s.frame !== 'ym'), M = p.sims.find(s => s.frame === 'ym');
        return { p, F, M };
      },
      step(n = 1, dt = 1 / 30) { for (let i = 0; i < n; i++) app._tick(dt); },
      sleep: ms => new Promise(r => setTimeout(r, ms)),
      async waitFor(fn, ms = 8000) { const t0 = performance.now(); while (performance.now() - t0 < ms) { try { if (fn()) return true; } catch { /* not yet */ } await new Promise(r => setTimeout(r, 50)); } return false; },
    };
    await app.voicesReady;
  });

  // ------------------------------------------------------------------ 1. feature and voices
  await run('1 voices', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app, { A, G } = window.__r24;
    C('the feature installed (features/game.js)', app.__game && typeof app.addMoment === 'function' && typeof app.setVoice === 'function', Object.keys(app).filter(k => /Moment|Voice|voice/.test(k)));
    C('/api/voices lines reach the app (>= 5,500)', (app.voiceLines || []).length >= 5500, (app.voiceLines || []).length);
    const bad = (app.voiceLines || []).filter(x => /_(ca|cb|pa)$/.test(x.name) || /(child|toddler|infant|baby|teen|kid|pet|puppy|kitten|dog|cat|horse)/i.test(x.name));
    C('no child / pet line in the app\'s list', !bad.length, bad.slice(0, 3).map(x => x.name));
    // voiceCode fix (F19): '_cm' is not a voice code; child codes are caught
    C('voiceCode: _cm -> "", _ma -> ma, _ca -> ca', A.voiceCode('vo_expr_moan_pleasure_30f_cm') === '' && A.voiceCode('vo_x_ma') === 'ma' && A.voiceCode('vo_x_ca') === 'ca' && A.voiceCode('clap_1') === '',
      [A.voiceCode('vo_expr_moan_pleasure_30f_cm'), A.voiceCode('vo_x_ma'), A.voiceCode('vo_x_ca')]);
    const { F, M } = window.__r24.couple();
    C('soundFitsSim: child lines never, other gender\'s never, plain lines always',
      !A.soundFitsSim('vo_giggle_ca', F) && !A.soundFitsSim('vo_x_ma', F) && A.soundFitsSim('vo_x_ma', M) && A.soundFitsSim('vo_expr_moan_pleasure_30f_cm', F) && A.soundFitsSim('Plaps_Normal', M), 'ok');
    C('default voices: fa for her, ma for him (no field needed)', A.simVoice(F) === 'fa' && A.simVoice(M) === 'ma' && F.voice === undefined, [A.simVoice(F), A.simVoice(M)]);
    const soft = app.voicePool(F, 'moan_soft'), woo = app.voicePool(M, 'woohoo');
    C("voicePool(female, 'moan_soft') >= 8", soft.length >= 8, soft.map(x => x.name).slice(0, 8));
    C("voicePool(male, 'woohoo') >= 8", woo.length >= 8, woo.map(x => x.name).slice(0, 8));
    const allSets = A.VOICE_SETS.map(([id]) => [id, app.voicePool(F, id).length, app.voicePool(M, id).length]);
    C('every voice kind has lines for both sims (Soft moans, Moans, WooHoo, Climax, Breathing, Kisses)', allSets.every(([, a, b]) => a > 0 && b > 0), allSets);
    const pools = A.VOICE_SETS.flatMap(([id]) => app.voicePool(F, id).concat(app.voicePool(M, id)));
    C('pools: never a child line, never lowprob before a real take', pools.every(x => !/_(ca|cb|pa)$/.test(x.name)) && app.voicePool(F, 'any').findIndex(x => x.lowprob) === -1 || app.voicePool(F, 'any').filter(x => !x.lowprob).length < 16, pools.length);
    C('the male pool is in his voice (every game line resolves in ma)', woo.every(x => x.source !== 'game' || (app.voiceLines.find(l => l.name === x.name) || { voices: [] }).voices.includes('ma')), 'ok');
    // soundOpts: voice lines in the sim's voice, at its pitch; claps as they are
    M.voicePitch = 0.5;
    const opts = app.runHook('soundOpts', M, { name: 'vo_expr_woohoo_hs_1loop_x', kind: 'voice' }).filter(Boolean);
    const clap = app.runHook('soundOpts', M, { name: 'Plaps_Normal', kind: 'clap' }).filter(Boolean);
    const own = app.runHook('soundOpts', M, { name: 'vo_x_ma', kind: 'voice' }).filter(Boolean);
    C('soundOpts: {voice: ma, detune: pitch x 300} for voice lines, nothing for claps, no voice for a line with its own', opts.some(o => o.voice === 'ma' && Math.abs(o.detune - 150) < 1e-9) && !clap.length && own.every(o => !o.voice), { opts, clap, own });
    delete M.voicePitch;
    return { checks: out };
  });

  // ------------------------------------------------------------------ 2. the voice picker, setVoice, the player
  await run('2 voice picker', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app, { A } = window.__r24;
    const { F, M } = window.__r24.couple();
    app.selectSim(M.id);
    app.showStep('sounds');
    const btns = [...document.querySelectorAll('#panel-body .voice-picker .vp-btn')];
    C('six voice buttons (3 female, 3 male)', btns.length === 6 && btns.map(b => b.dataset.voice).join() === 'fa,fc,fd,ma,mb,mc', btns.map(b => b.dataset.voice));
    C("his own voice glows, the women's voices are dimmed", btns.find(b => b.dataset.voice === 'ma').classList.contains('on') && btns.filter(b => b.classList.contains('other')).map(b => b.dataset.voice).join() === 'fa,fc,fd', btns.map(b => b.className));
    const u0 = app.store.undo.length;
    btns.find(b => b.dataset.voice === 'mc').click();
    await window.__r24.sleep(200);
    C('clicking Voice 3 (male) sets his voice, one undo step', M.voice === 'mc' && app.store.undo.length === u0 + 1, { voice: M.voice, undo: app.store.undo.length - u0 });
    const again = [...document.querySelectorAll('#panel-body .voice-picker .vp-btn')].find(b => b.dataset.voice === 'mc');
    C('the picker shows the new voice', again && again.classList.contains('on'), again && again.className);
    app.undo();
    C('undo gives him his default voice back', !app.store.project.sims.find(s => s.id === M.id).voice, app.store.project.sims.find(s => s.id === M.id).voice);
    // the title and the step's parts
    const title = document.getElementById('panel-title').textContent + getComputedStyle(document.getElementById('panel-title'), '::after').content.replace(/"/g, '');
    C('the step is "Sounds & moments" ("Voices, claps, cum and effects")', /Sounds & moments/.test(title) && document.getElementById('panel-sub').textContent === 'Voices, claps, cum and effects', [title, document.getElementById('panel-sub').textContent]);
    const sec = [...document.querySelectorAll('#panel-body .section-title')].map(x => x.textContent);
    C('sections: Automatic sounds, Voice, Finish, Moments, On the timeline', ['Automatic sounds', 'Voice', 'Finish', 'Moments', 'On the timeline'].every(t => sec.some(s => s.startsWith(t))), sec);
    const t0 = performance.now();
    for (let i = 0; i < 5; i++) app.renderStep();
    const ms = (performance.now() - t0) / 5;
    C('rendering the step stays well under 50 ms', ms < 50, +ms.toFixed(1));
    // the player keeps one buffer per voice
    const P = app.audio;
    P.ensure();
    const [bf, bm] = await Promise.all([P.load(A.SAMPLE_LINE, 'fa'), P.load(A.SAMPLE_LINE, 'ma')]);
    C('the player fetches and keeps a line per voice (fa and ma are different takes)', bf && bm && bf !== bm && P.buffers.has(A.SAMPLE_LINE + '|fa') && P.buffers.has(A.SAMPLE_LINE + '|ma') && (bf.length !== bm.length || bf.duration !== bm.duration),
      bf && bm ? [bf.duration.toFixed(3), bm.duration.toFixed(3)] : [bf, bm]);
    const miss = await P.load('vo_x_does_not_exist_zz', 'fa');
    C('a line missing in that voice falls back (no crash)', miss === null, String(miss));
    return { checks: out };
  });

  // ------------------------------------------------------------------ 3. Game voices in "Add a sound"
  await run('3 game voices', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app;
    const { F } = window.__r24.couple();
    app.selectSim(F.id);
    app.setFrame(20);
    app.addSoundDialog(F.id);
    await window.__r24.sleep(150);
    const dlg = [...document.querySelectorAll('#modal-root .modal')].pop();
    const sel = dlg.querySelector('select');
    C('"Game voices" is a kind in Add a sound', [...sel.options].some(o => o.value === 'game' && o.textContent === 'Game voices'), [...sel.options].map(o => o.textContent));
    C('it opens on claps (as before)', sel.value === 'clap', sel.value);
    sel.value = 'game'; sel.dispatchEvent(new Event('change'));
    await window.__r24.sleep(100);
    const note = dlg.querySelector('.proj-list .hint').textContent;
    const items = dlg.querySelectorAll('.proj-list .proj-item');
    C('it lists the game lines in her voice ("5,5xx game lines · plays in each sim\'s own voice")', /5,5\d\d game lines · plays in each sim's own voice/.test(note) && items.length === 200, [note, items.length]);
    const first = [...items].slice(0, 12).map(x => x.querySelector('.n').textContent);
    C('moans, WooHoo, climax, breathing first', first.every(n => /woohoo|moan|mmm|purr|swoon|pleasure|finish|breath|pant|sigh|gasp|kiss|makeout/.test(n)), first);
    const chip = [...dlg.querySelectorAll('.game-voice-chips .chipbtn')].find(b => b.textContent === 'Climax');
    chip.click();
    await window.__r24.sleep(50);
    const climax = [...dlg.querySelectorAll('.proj-list .proj-item .n')].map(x => x.textContent);
    C('the Climax chip keeps only climax lines', climax.length > 5 && climax.every(n => /finish/.test(n)), climax.slice(0, 5));
    const pick = [...dlg.querySelectorAll('.proj-list .proj-item')].find(x => x.querySelector('.n').textContent === 'vo_expr_woohoo_big_1finish_y');
    pick && pick.click();
    C('picking one puts it on her lane at the playhead as a voice', F.sounds.some(x => x.name === 'vo_expr_woohoo_big_1finish_y' && x.frame === 20 && x.kind === 'voice'), F.sounds.slice(-1));
    document.querySelectorAll('#modal-root .modal-x').forEach(b => b.click());
    app.showStep('sounds');
    await window.__r24.sleep(100);
    const row = [...document.querySelectorAll('#panel-body .sound-row')].find(r => r.textContent.includes('vo_expr_woohoo_big_1finish_y'));
    C('its row shows how long the line is', row && /· \d+\.\d s/.test(row.textContent), row && row.textContent);
    return { checks: out };
  });

  // ------------------------------------------------------------------ 4. Magic cowgirl: no voices from Magic; voices added after play as voice=fa / voice=ma
  requests.length = 0;
  const magic = await run('4 magic voices', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app;
    const m = await import('/js/magic.js');
    const rnd = Math.random;
    Math.random = (() => { let s = 12345; return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; })();
    let ok;
    try { ok = await m.makeMagic(app, { recipe: 'cowgirl', place: 'double_bed', seconds: 3, name: 'R24 cowgirl', author: 'R24' }); } finally { Math.random = rnd; }
    app.setPlaying(false); app.showcase && app.showcase(false);
    const p = app.store.project, F = p.sims.find(s => s.frame !== 'ym'), M = p.sims.find(s => s.frame === 'ym');
    const v = s => (s.sounds || []).filter(x => x.kind === 'voice');
    // Magic adds no voices (looped lines sounded wrong); the player adds them in the Sounds step
    C('Magic cowgirl: made, with no voice notes on either sim', ok && v(F).length === 0 && v(M).length === 0, { her: v(F).map(x => x.name), him: v(M).map(x => x.name) });
    app.randomVoices(F.id, 'woohoo', 2, { quiet: true });
    app.randomVoices(M.id, 'woohoo', 2, { quiet: true });
    C('voices added in the Sounds step go on both', v(F).length > 0 && v(M).length > 0, { her: v(F).map(x => x.name), him: v(M).map(x => x.name) });
    app.audio.setMuted(false);
    app.setFrame(0);
    app.setPlaying(true);
    await window.__r24.sleep(3600);
    app.setPlaying(false);
    return { checks: out, data: { her: v(F).map(x => x.name), him: v(M).map(x => x.name) } };
  });
  {
    const her = (magic.data && magic.data.her) || [], him = (magic.data && magic.data.him) || [];
    const fa = requests.filter(u => /voice=fa/.test(u)), ma = requests.filter(u => /voice=ma/.test(u));
    const herOk = her.length && her.every(n => fa.some(u => u.includes(encodeURIComponent(n)))), himOk = him.length && him.every(n => ma.some(u => u.includes(encodeURIComponent(n))));
    check('4 magic voices: while playing, the network log shows voice=fa for her lines and voice=ma for his', fa.length && ma.length && herOk && himOk,
      { fa: fa.length, ma: ma.length, sample: [fa[0], ma[0]].map(u => u && u.replace(/^https?:\/\/[^/]+/, '')) });
  }

  // ------------------------------------------------------------------ 5. moments: add, label, menu, dialog, drag, delete, undo
  await run('5 moments', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app, { M: Mo } = window.__r24;
    const { p, F, M } = window.__r24.couple();
    app.showStep('sounds');
    C('the Moments row sits between the ruler and the lanes (22 px)', app.timeline.rows.some(r => r.id === 'moments' && r.height === 22) && app.timeline.laneTop(0) >= 28 + 22, { lane0: app.timeline.laneTop(0), rows: app.timeline.rows.map(r => [r.id, r.height]) });
    const u0 = app.store.undo.length;
    const e1 = app.addMoment({ type: 'CUM', frame: 63, sim: F.id, cum: 'FACE', level: 2 });
    C('addMoment: one undo step, a clean moment', app.store.undo.length === u0 + 1 && p.events.length === 1 && JSON.stringify(Object.keys(e1).sort()) === JSON.stringify(['cum', 'frame', 'id', 'level', 'sim', 'type']), e1);
    C("the plain sentence: \"Cum on Female 1's face, level 2 · 2.1 s\"", Mo.momentLabel(e1, app) === "Cum on Female 1's face, level 2 · 2.1 s", Mo.momentLabel(e1, app));
    // the Moments row: the flag is drawn and hit where it is
    const row = app.timeline.rows.find(r => r.id === 'moments');
    const ctx = { x0: 168, x1: 1000, y: 28, h: 22, xAt: f => app.timeline.xAt(f), frameAt: x => app.timeline.frameAt(x), app, playing: false };
    const hit = row.hit(app.timeline.xAt(63) + 5, 36, ctx);
    C('hit-testing finds the flag', hit === e1, hit && hit.id);
    C('the tooltip is the plain sentence', row.tooltip(e1).startsWith("Cum on Female 1's face"), row.tooltip(e1));
    // undress on a naked sim: she starts dressed (same undo step)
    const u1 = app.store.undo.length;
    const e2 = app.addMoment({ type: 'UNDRESS', frame: 15, sim: F.id, naked: 'TOP' });
    C('undress on a sim naked from the start makes her start dressed (same undo step)', F.naked === 'NONE' && app.store.undo.length === u1 + 1, { naked: F.naked, undo: app.store.undo.length - u1 });
    // updateMoment / removeMoment
    app.updateMoment(e1.id, { level: 3 });
    C('updateMoment changes it', p.events.find(e => e.id === e1.id).level === 3, p.events.find(e => e.id === e1.id));
    app.removeMoment(e2.id);
    C('removeMoment removes it', !p.events.some(e => e.id === e2.id) && p.events.length === 1, p.events.length);
    app.undo();
    C('undo brings it back', app.store.project.events.some(e => e.id === e2.id), app.store.project.events.length);
    // simRemoved cleanup
    const p2 = app.store.project;
    app.removeSim(p2.sims.find(s => s.frame !== 'ym').id);
    C('removing a sim removes its moments', !(app.store.project.events || []).length, app.store.project.events);
    app.undo();
    C('undo brings the sim and its moments back', app.store.project.events.length === 2, app.store.project.events.length);
    // a note has no sim; notes survive; never exported
    const n = app.addMoment({ type: 'NOTE', frame: 30, text: 'look up' });
    C('a note is kept, and never exported', app.store.project.events.some(e => e.id === n.id) && !(app.bake().events || []).some(e => e.type === 'NOTE'), app.bake().events);
    // the right-click menu of the row (with her selected)
    app.selectSim(app.store.project.sims.find(s => s.frame !== 'ym').id);
    const items = Mo.momentMenuItems(app, null, 40);
    const labels = items.map(x => (x === '-' ? '-' : x.heading || x.label));
    C('right-click on the row: Finish here (8 parts), Clothes (top/bottom/everything), condom, Effect…, Note…',
      labels[0].startsWith('Finish here') && labels.filter(l => /^Cum on Female 1's/.test(l)).length === 8 && labels.includes('Undress Female 1: top') && labels.includes('Undress Female 1: everything')
      && labels.includes("Remove Male 1's condom") && labels.includes('Effect at a body part…') && labels.includes('Note…'), labels);
    const chest = items.find(x => x.label === "Cum on Female 1's chest");
    chest.onClick();
    C('picking "Cum on Female 1\'s chest" adds it at that frame', app.store.project.events.some(e => e.type === 'CUM' && e.cum === 'CHEST' && e.frame === 40), app.store.project.events.map(e => [e.type, e.cum, e.frame]));
    // with a penis on the target the vagina is not offered
    app.selectSim(app.store.project.sims.find(s => s.frame === 'ym').id);
    const toHim = Mo.momentMenuItems(app, null, 40).map(x => x.label || '');
    C("cum goes to the one who receives even when he is selected", toHim.some(l => /^Cum on Female 1's face/.test(l)), toHim.slice(0, 3));
    return { checks: out };
  });

  // the real mouse: drag a flag, Delete with the timeline focused
  {
    const g = await pe(() => {
      const app = window.app, tl = app.timeline, r = tl.canvas.getBoundingClientRect();
      const e = app.store.project.events.find(x => x.type === 'CUM' && x.cum === 'FACE');
      app.timeline.fit();
      return { x: r.left + tl.xAt(e.frame) + 6, y: r.top + 28 + 10, ppf: tl.pxPerFrame, id: e.id, from: e.frame };
    });
    await page.mouse.move(g.x, g.y);
    await page.mouse.down();
    for (let i = 1; i <= 6; i++) { await page.mouse.move(g.x - i * 2 * g.ppf, g.y); await sleep(30); }
    await page.mouse.up();
    await sleep(100);
    const after = await pe(id => { const e = window.app.store.project.events.find(x => x.id === id); return { frame: e.frame, sel: window.app.selectedEvent, focus: window.app.focus, frameNow: Math.round(window.app.store.frame) }; }, g.id);
    check('5 moments: dragging a flag on the timeline moves it (and the playhead follows)', after.frame === g.from - 12 && after.sel === g.id && after.frameNow === after.frame, { from: g.from, to: after.frame, selected: after.sel === g.id });
    await page.keyboard.press('Delete');
    await sleep(100);
    const del = await pe(id => ({ gone: !window.app.store.project.events.some(x => x.id === id), keys: window.app.store.project.sims.map(s => s.keys.length) }), g.id);
    check('5 moments: Delete with the timeline focused removes the clicked moment (keys stay)', del.gone && del.keys.every(k => k >= 1), del);
    // a click on a lane lets go of it: Delete then works on keys again
    const lane = await pe(() => { const app = window.app, tl = app.timeline, r = tl.canvas.getBoundingClientRect(); const e = app.store.project.events[0]; app.selectedEvent = e.id; return { x: r.left + tl.xAt(70), y: r.top + tl.laneTop(0) + 30, id: e.id }; });
    await page.mouse.click(lane.x, lane.y);
    await sleep(80);
    const sel = await pe(() => window.app.selectedEvent);
    check('5 moments: a click on a lane lets go of the moment', sel === null, sel);
  }

  // ------------------------------------------------------------------ 6. the moment dialog and the effect picker
  await run('6 dialog', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app, S = window.__r24;
    const { p, F, M } = S.couple();
    app.selectSim(M.id);
    app.setFrame(45);
    app.editMoment(null, 45, { type: 'EFFECT' });
    await S.sleep(200);
    const dlg = () => [...document.querySelectorAll('#modal-root .modal')].pop();
    C('the dialog opens on Effect, for him (the selected sim)', dlg() && dlg().querySelector('.moment-types .on').textContent.trim() === 'Effect' && dlg().querySelector('.chipbtn.on').textContent.includes('Male 1'), dlg() && dlg().querySelector('.moment-types .on').textContent);
    const joints = [...dlg().querySelectorAll('.fx-joint')].map(b => b.textContent);
    C('body parts: only the ones he has (penis yes, vagina no), tip first', joints[0] === 'Tip of the penis' && !joints.includes('Vagina') && joints.includes('Balls') && joints.includes('Left palm'), joints);
    await S.waitFor(() => dlg().querySelectorAll('.fx-tile').length > 10, 8000);
    const tiles = [...dlg().querySelectorAll('.fx-tile')];
    C('effects grouped (Cum & splashes first), with "used in N creator animations" and a moving preview', tiles.length > 10 && dlg().querySelector('.fx-group').textContent === 'Cum & splashes'
      && /used in [\d,]+ creator animations/.test(tiles[0].textContent) && tiles[0].querySelector('canvas.fx-prev'), { tiles: tiles.length, first: tiles[0] && tiles[0].textContent });
    const cv = tiles[0].querySelector('canvas');
    const px = () => { const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data; let s = 0; for (let i = 3; i < d.length; i += 4) s += d[i]; return s; };
    const a0 = px(); await S.sleep(300); const a1 = px();
    C('the preview tiles move', a0 > 0 && a0 !== a1, [a0, a1]);
    const search = dlg().querySelector('.fx-effects input.text');
    search.value = 'drool'; search.dispatchEvent(new Event('input'));
    await S.waitFor(() => { const t = dlg().querySelector('.fx-tile b'); return t && t.textContent === 'Drool strands'; }, 5000);
    const found = [...dlg().querySelectorAll('.fx-tile')].map(t => t.title);
    C('search: "drool" finds the drool effects, the most used first', found[0] === 'pet_small_drool_front' && found.every(n => /drool/.test(n)), found.slice(0, 4));
    dlg().querySelector('.fx-tile').click();
    const skip = [...dlg().querySelectorAll('label.check input')].find(i => i.closest('label').textContent.includes('wears a condom'));
    C('"Skip when Male 1 wears a condom" is on by itself for the penis', skip && skip.checked, skip && skip.checked);
    const btn = [...dlg().querySelectorAll('footer .btn')].find(b => b.textContent === 'Add moment');
    btn.click();
    await S.sleep(250);
    const ev = (app.store.project.events || [])[0];
    C('Add moment: EFFECT pet_small_drool_front at his tip, 45 -> 75, skipped with a condom', ev && ev.type === 'EFFECT' && ev.effect === 'pet_small_drool_front' && ev.joint === 'b__Penis_Tip' && ev.frame === 45 && ev.end === 75 && ev.skipWithCondom === true && ev.sim === M.id, ev);
    // the cum dialog on her: vagina offered, silhouette lights the part
    app.editMoment(null, 30, { type: 'CUM', sim: F.id });
    await S.sleep(200);
    const d2 = dlg();
    const parts = [...d2.querySelectorAll('.cum-fields .chips .chipbtn')].map(b => b.textContent);
    C('Cum: 8 body parts for her (vagina too), 3 levels, a body that lights the part', parts.length === 8 && parts.includes('Vagina') && d2.querySelectorAll('.cum-body .spot.on').length >= 1 && d2.querySelectorAll('.cum-fields .seg-inline button').length === 3, parts);
    [...d2.querySelectorAll('.cum-fields .chips .chipbtn')].find(b => b.textContent === 'Chest').click();
    await S.sleep(50);
    C('choosing Chest lights the chest', dlg().querySelector('.cum-body .spot.on').getAttribute('data-part') === 'CHEST', dlg().querySelector('.cum-body .spot.on').getAttribute('data-part'));
    [...dlg().querySelectorAll('footer .btn')].find(b => b.textContent === 'Add moment').click();
    await S.sleep(200);
    C('Add moment: CUM on her chest at 1 s', app.store.project.events.some(e => e.type === 'CUM' && e.cum === 'CHEST' && e.frame === 30 && e.sim === F.id), app.store.project.events.map(e => [e.type, e.cum, e.frame]));
    // double-click opens it for a change; Delete in the dialog
    const cumEv = app.store.project.events.find(e => e.type === 'CUM');
    app.editMoment(cumEv.id);
    await S.sleep(150);
    C('changing a moment: the dialog says Save and offers Delete', [...dlg().querySelectorAll('footer .btn')].map(b => b.textContent).join('|') === 'Delete|Cancel|Save', [...dlg().querySelectorAll('footer .btn')].map(b => b.textContent));
    document.querySelectorAll('#modal-root .modal-x').forEach(b => b.click());
    await S.sleep(250);
    return { checks: out };
  });

  // ------------------------------------------------------------------ 7. Finish preset, climax, bake, export checks
  await run('7 finish + bake', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app, S = window.__r24, Mo = S.M;
    const { p, F, M } = S.couple();
    app.selectSim(M.id);
    p.loops = 10; p.category = 'VAGINAL';
    app.setFrame(60);
    const u0 = app.store.undo.length;
    app.finishPreset('face', 60);
    const evs = p.events || [];
    const cum = evs.find(e => e.type === 'CUM'), fx = evs.find(e => e.type === 'EFFECT');
    C('Finish (face): one undo step', app.store.undo.length === u0 + 1, app.store.undo.length - u0);
    C('Finish: cum on HER face (the receiver, although he is selected), level 2, at the playhead', cum && cum.sim === F.id && cum.cum === 'FACE' && cum.level === 2 && cum.frame === 60, cum);
    C("Finish: drool at his tip, F-6 ... F+30, skipped with a condom", fx && fx.sim === M.id && fx.effect === 'pet_small_drool_front' && fx.joint === 'b__Penis_Tip' && fx.frame === 54 && fx.end === 90 && fx.skipWithCondom, fx);
    C('Finish: the game\'s finish voices, his at F-10, hers at F-5', M.sounds.some(x => x.name === 'vo_expr_woohoo_big_1finish_x' && x.frame === 50) && F.sounds.some(x => x.name === 'vo_expr_woohoo_big_1finish_y' && x.frame === 55), [M.sounds.slice(-1), F.sounds.slice(-1)]);
    C('Finish: its moments share a group (drag one, the group moves)', cum.group && cum.group === fx.group, [cum.group, fx.group]);
    const bar = document.querySelector('.choice-bar');
    C('not a climax and loops > 1: "In the game cum adds up every loop" with "Make it a climax"', bar && /adds up every loop/.test(bar.textContent) && /Make it a climax/.test(bar.textContent), bar && bar.textContent);
    // a new Finish replaces the old one
    app.finishPreset('inside', 60);
    const cums = p.events.filter(e => e.type === 'CUM');
    C('a new Finish replaces the last one (inside a vaginal: VAGINA, drips out of her)', cums.length === 1 && cums[0].cum === 'VAGINA' && p.events.some(e => e.type === 'EFFECT' && e.joint === 'b__Low_Vagina__' && e.frame === 75 && e.end === 90)
      && M.sounds.filter(x => x.name === 'vo_expr_woohoo_big_1finish_x').length === 1, p.events.map(e => [e.type, e.cum || e.joint, e.frame]));
    // the export checks
    const list = (app.runHook('exportChecks', p).flat()).filter(Boolean);
    C('Send check: "cum adds up every loop" with "Make it a climax"', list.some(x => /adds up every loop/.test(x.text) && x.fix && x.fix.label === 'Make it a climax'), list.map(x => x.text));
    list.find(x => x.fix && x.fix.label === 'Make it a climax').fix.run();
    C('Make it a climax: CLIMAX, plays once, the act is kept', p.category === 'CLIMAX' && p.loops === 1 && p.act === 'VAGINAL', [p.category, p.loops, p.act]);
    // bake
    F.cumAfter = ['FACE', 'CHEST'];
    const b = app.bake();
    const fi = b.actors.findIndex((a, i) => p.sims[i].id === F.id);
    C('bake: events at the top level in seconds, targets are actor indexes', Array.isArray(b.events) && b.events.length === 2 && b.events.every(e => typeof e.start === 'number' && Number.isInteger(e.target)) && b.events.find(e => e.type === 'CUM').target === fi && Math.abs(b.events.find(e => e.type === 'CUM').start - 2) < 1e-9, b.events);
    C('bake: cumAfter on the actor, act for a climax', JSON.stringify(b.actors[fi].cumAfter) === '["FACE","CHEST"]' && b.act === 'VAGINAL' && !('cumAfter' in b.actors[1 - fi]), [b.actors[fi].cumAfter, b.act]);
    // other export checks
    p.events.push({ id: 'etest1', type: 'EFFECT', frame: 10, end: 40, sim: F.id, effect: 'sim_pee_c', joint: 'b__Penis_Tip' });
    p.events.push({ id: 'etest2', type: 'REMOVE_CONDOM', frame: 12, sim: F.id });
    p.events.push({ id: 'etest3', type: 'UNDRESS', frame: 14, sim: F.id, naked: 'TOP' });
    F.naked = 'ALL';
    await Mo.checkEffects(['sim_pee_c']);
    const l2 = (app.runHook('exportChecks', p).flat()).filter(Boolean);
    const T = l2.map(x => `${x.level}: ${x.text}${x.fix ? ' [' + x.fix.label + ']' : ''}`);
    C('Send check: a child effect name is red with "Use sim_pee"', l2.some(x => x.level === 'error' && /sim_pee_c/.test(x.text) && x.fix && x.fix.label === 'Use sim_pee'), T);
    C('Send check: condom off a sim without a penis; an effect at the penis of a sim without one', l2.some(x => /has no penis, so there is no condom/.test(x.text)) && l2.some(x => /plays at Female 1's penis/.test(x.text)), T);
    C('Send check: undress on a sim naked from the start, with "Start dressed"', l2.some(x => /naked from the start/.test(x.text) && x.fix && x.fix.label === 'Start dressed'), T);
    l2.find(x => x.fix && x.fix.label === 'Use sim_pee').fix.run();
    C('"Use sim_pee" fixes the name', p.events.find(e => e.id === 'etest1').effect === 'sim_pee', p.events.find(e => e.id === 'etest1').effect);
    // nobody with a penis
    const { p: p2, F: F2 } = S.couple({ template: 'ff' });
    app.addMoment({ type: 'CUM', frame: 20, sim: F2.id, cum: 'FACE', level: 1 });
    const l3 = (app.runHook('exportChecks', p2).flat()).filter(Boolean);
    C('Send check: cum when nobody has a penis', l3.some(x => /only shows cum when someone in the act has a penis/.test(x.text)), l3.map(x => x.text));
    // the export dialog lists them (warnings never block; red ones do)
    app.exportDialog();
    await S.sleep(250);
    const boxes = [...document.querySelectorAll('#modal-root .warn-box')].map(x => x.textContent);
    C('the Send to game list shows it', boxes.some(t => /penis/.test(t)), boxes);
    document.querySelectorAll('#modal-root .modal-x').forEach(x => x.click());
    await S.sleep(250);
    return { checks: out };
  });

  // ------------------------------------------------------------------ 8. the 4-moment proto (spec_game 3) for the offline export
  await run('8 proto', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app, S = window.__r24;
    app.newScene(false, false, 'couple');
    const p = app.store.project;
    // a0 = him (the giver), a1 = her
    p.sims.sort((a, b) => (a.frame === 'ym' ? -1 : 1) - (b.frame === 'ym' ? -1 : 1));
    app.refreshAll();
    p.name = 'R24 proto'; p.author = 'R24'; p.category = 'CLIMAX'; p.loops = 1; p.act = 'ORALJOB';
    const [Mm, Ff] = p.sims;
    Ff.naked = 'NONE';
    app.addMoment({ type: 'CUM', frame: 63, sim: Ff.id, cum: 'FACE', level: 2 });
    app.addMoment({ type: 'EFFECT', frame: 60, end: 90, sim: Mm.id, effect: 'pet_small_drool_front', joint: 'b__Penis_Tip', skipWithCondom: true });
    app.addMoment({ type: 'UNDRESS', frame: 15, sim: Ff.id, naked: 'TOP' });
    app.addMoment({ type: 'REMOVE_CONDOM', frame: 54, sim: Mm.id });
    app.addMoment({ type: 'NOTE', frame: 20, text: 'never exported' });
    const b = app.bake();
    C('the proto bakes 4 moments (the note stays home)', (b.events || []).length === 4 && b.act === 'ORALJOB', b.events);
    window.__r24.proto = b;
    // retime 3 s -> 6 s: frames and ends double, "to the end" stays at the end
    app.setLength(180, 'stretch');
    await S.sleep(50);
    app.applyPoses(false);
    const ev = app.store.project.events;
    const at = t => ev.find(e => e.type === t);
    C('retime 3 s -> 6 s doubles frame and end (to the end stays at the end)', at('CUM').frame === 126 && at('UNDRESS').frame === 30 && at('EFFECT').frame === 120 && at('EFFECT').end === 180, ev.map(e => [e.type, e.frame, e.end]));
    app.undo();
    return { checks: out };
  });
  const proto = await pe(() => window.__r24.proto);
  fs.writeFileSync(path.join(OUT_DIR, 'proto.baked.json'), JSON.stringify(proto));

  // ------------------------------------------------------------------ 9. old projects bake exactly as before (the bake hook adds nothing)
  await run('9 no change for old projects', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app;
    const hook = app.hooks.bake.find(f => /bakeMoments/.test(String(f)));
    const list = await (await fetch('/api/projects')).json();
    const names = list.slice(0, 5).map(x => x.file);
    const same = [];
    for (const n of names) {
      const proj = await (await fetch('/api/project?name=' + encodeURIComponent(n))).json();
      if ((proj.events || []).length) continue;
      const withHook = JSON.stringify(await app.bakeOther(JSON.parse(JSON.stringify(proj))));
      const i = app.hooks.bake.indexOf(hook);
      app.hooks.bake.splice(i, 1);
      let without;
      try { without = JSON.stringify(await app.bakeOther(JSON.parse(JSON.stringify(proj)))); } finally { app.hooks.bake.splice(i, 0, hook); }
      same.push([n, withHook === without, withHook.length]);
    }
    const { p } = window.__r24.couple();
    const a = JSON.stringify(app.bake());
    const i = app.hooks.bake.indexOf(hook);
    app.hooks.bake.splice(i, 1);
    const b2 = JSON.stringify(app.bake());
    app.hooks.bake.splice(i, 0, hook);
    same.push(['new couple', a === b2, a.length]);
    C('a project without moments bakes byte-identical with and without the feature', hook && same.length >= 2 && same.every(x => x[1]), same);
    C('no events / cumAfter / act fields added to such a bake', !/"events"|"cumAfter"/.test(a) && JSON.parse(a).act === JSON.parse(b2).act, 'ok');
    return { checks: out };
  });

  // ------------------------------------------------------------------ 10. effects: same every loop, condom, toggle
  await run('10 effects', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app, S = window.__r24;
    const { p, F, M } = S.couple();
    app.addLayer(M.id, 'thrust');
    app.setPlaying(false);
    const ev = app.addMoment({ type: 'EFFECT', frame: 30, end: 75, sim: M.id, effect: 'pet_small_drool_front', joint: 'b__Penis_Tip' });
    app.setShowEffects(true);
    const n0 = app.effects.sampleNow();
    C('the needed frames are read once from the keys (30..75)', n0 >= 40, n0);
    app.vp.pause();
    let snap1, snap2, snapOut, snapEnd, snapNext, tip45;
    try {
      app.setFrame(0);
      app.setPlaying(true);
      S.step(45);
      snap1 = app.effects.snapshot()[ev.id];
      const v = app.simViews.get(M.id);
      tip45 = v.worldPos('b__Penis_Tip').toArray();
      S.step(90);
      snap2 = app.effects.snapshot()[ev.id];
      S.step(30);
      snapEnd = (app.effects.snapshot()[ev.id] || []).length;        // frame 75: the effect's last frame
      S.step(13);
      snapOut = (app.effects.snapshot()[ev.id] || []).length;        // frame 88: only drops born before 75 are left
      S.step(22);
      snapNext = (app.effects.snapshot()[ev.id] || []).length;       // frame 20 of the next loop: before it starts
    } finally { app.setPlaying(false); app.vp.resume(); }
    const f1 = Math.round(p.length), diff = snap1 && snap2 && snap1.length === snap2.length ? Math.max(0, ...snap1.map((q, i) => Math.hypot(q[0] - snap2[i][0], q[1] - snap2[i][1], q[2] - snap2[i][2]))) : null;
    C('drool at the tip: the particles at frame 45 of loop 1 and loop 2 are identical', snap1 && snap1.length > 10 && diff !== null && diff < 1e-6, { n: snap1 && snap1.length, maxDiff: diff, loop: f1 });
    const near = snap1 ? Math.min(...snap1.map(q => Math.hypot(q[0] - tip45[0], q[1] - tip45[1], q[2] - tip45[2]))) : 1;
    C('they come from his tip (the newest drop is within 3 cm of it)', near < 0.03, +near.toFixed(4));
    C('after the effect ends no new drops (fewer at frame 88 than at 75); none before it starts in the next loop', snapEnd > 0 && snapOut < snapEnd && snapNext === 0, { at75: snapEnd, at88: snapOut, nextLoop20: snapNext });
    // condom preview
    app.updateMoment(ev.id, { skipWithCondom: true });
    M.previewCondom = true;
    app.setFrame(45);
    const withCondom = (app.effects.snapshot()[ev.id] || []).length;
    const cond = app.addMoment({ type: 'REMOVE_CONDOM', frame: 10, sim: M.id });
    app.setFrame(46); app.setFrame(45);
    const afterOff = (app.effects.snapshot()[ev.id] || []).length;
    C('"wears a condom" (preview): a skipped effect does not play, until his condom comes off', withCondom === 0 && afterOff > 0, { withCondom, afterOff });
    app.removeMoment(cond.id);
    delete M.previewCondom;
    // the toolbar toggle
    const btn = document.getElementById('btn-fx');
    btn.click();
    app.setFrame(46); app.setFrame(45);
    const hidden = (app.effects.snapshot()[ev.id] || []).length;
    btn.click();
    app.setFrame(46); app.setFrame(45);
    const shown = (app.effects.snapshot()[ev.id] || []).length;
    C('the "Show effects" button hides and shows them', btn && hidden === 0 && shown > 0 && btn.classList.contains('on'), { hidden, shown });
    // per frame cost of the feature
    const T = []; for (let i = 0; i < 40; i++) { const t = performance.now(); app.runHook('afterApply', 45 + (i % 3), { playing: false, ghosts: false }); T.push(performance.now() - t); }
    T.sort((a, b) => a - b);
    C('per-frame cost with a drool playing stays small (median < 2 ms)', T[20] < 2, +T[20].toFixed(3));
    return { checks: out };
  });

  // ------------------------------------------------------------------ 11. cum on the skin
  await run('11 cum on the skin', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app, S = window.__r24, Cum = S.Cum;
    const L = await Cum.load();
    const types = Object.keys(L);
    C('cum_layers: 8 types x 3 levels, rects inside [0, 1]', types.length === 8 && types.every(t => L[t].length === 3 && L[t].every(x => x.rect.every(v => v >= 0 && v <= 1) && x.rect[0] < x.rect[2] && x.rect[1] < x.rect[3])), types.map(t => [t, L[t].length]));
    // pixel diff: {FACE: 3} changes only pixels inside the FACE level-3 rect
    const { p, F, M } = S.couple();
    app.showCum = true;
    const v = app.simViews.get(F.id);
    await app.skinReady(F.frame, F.tone || '');
    const base = v.material.map && v.material.map.image;
    const list = Cum.layersFor({ FACE: 3 });
    await Cum.ready(list);
    const a = Cum.compose(base, [], document.createElement('canvas')), b = Cum.compose(base, list, document.createElement('canvas'));
    const W = a.width, Hh = a.height;
    const da = a.getContext('2d').getImageData(0, 0, W, Hh).data, db = b.getContext('2d').getImageData(0, 0, W, Hh).data;
    const [u0, v0, u1, v1] = list[0].rect;
    let changed = 0, outside = 0;
    for (let y = 0; y < Hh; y++) for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 4;
      if (da[i] !== db[i] || da[i + 1] !== db[i + 1] || da[i + 2] !== db[i + 2]) {
        changed++;
        if (x < u0 * W - 1 || x > u1 * W + 1 || y < v0 * Hh - 1 || y > v1 * Hh + 1) outside++;
      }
    }
    C('pixel diff of {FACE: 3}: changes only inside the FACE level-3 rect', changed > 500 && outside === 0, { changed, outside, size: [W, Hh], rect: list[0].rect });
    window.__r24.cumCanvas = b.toDataURL('image/png');
    // 3 loops of a level-1 FACE moment: L1, L2, L3; scrubbing: L1 after the frame, none before
    const e = app.addMoment({ type: 'CUM', frame: 30, sim: F.id, cum: 'FACE', level: 1 });
    Cum.preload(app.store.project);
    await Cum.ready(Cum.layersFor({ FACE: 1 }).concat(Cum.layersFor({ FACE: 2 }), Cum.layersFor({ FACE: 3 })));
    const shown = async f => { app.setFrame(f); await S.waitFor(() => { app.applyPoses(false); return Cum.shownKey(app.simViews.get(F.id)) !== null && (Cum.activeCum(app, F, f, 0).FACE ? Cum.shownKey(app.simViews.get(F.id)) !== '' : true); }, 4000); return Cum.shownKey(app.simViews.get(F.id)); };
    const before = await shown(20), after = await shown(45);
    C('scrubbing: nothing before the moment, level 1 after it', before === '' && after === '{"FACE":1}', { before, after });
    app.vp.pause();
    const seen = [];
    try {
      app.setFrame(0); app.setPlaying(true);
      for (const n of [45, 90, 90]) { S.step(n); app.applyPoses(false); seen.push([app.loopPass, Cum.activeCum(app, F, app.store.frame, app.loopPass).FACE, Cum.shownKey(app.simViews.get(F.id))]); }
    } finally { app.setPlaying(false); app.vp.resume(); }
    C('playing 3 loops shows level 1, then 2, then 3 (it adds up, like the game)', seen.map(x => x[1]).join() === '1,2,3' && seen.map(x => x[2]).join('|') === '{"FACE":1}|{"FACE":2}|{"FACE":3}', seen);
    C('stopping shows the first loop again', Cum.activeCum(app, F, app.store.frame, app.loopPass).FACE === 1 && app.loopPass === 0, app.loopPass);
    // VAGINA on a sim with a penis -> BUTT; nobody with a penis -> nothing; toggle off -> nothing
    app.addMoment({ type: 'CUM', frame: 10, sim: M.id, cum: 'VAGINA', level: 1 });
    C('VAGINA on a sim with a penis shows on the butt', JSON.stringify(Cum.activeCum(app, M, 50, 0)) === '{"BUTT":1}', Cum.activeCum(app, M, 50, 0));
    app.setShowCum(false);
    app.setFrame(50);
    await S.sleep(50); app.applyPoses(false);
    const off = Cum.shownKey(app.simViews.get(F.id));
    app.setShowCum(true);
    app.setFrame(51); app.applyPoses(false);
    C('"Show cum" off puts the plain skin back', off === '' && document.getElementById('btn-cum'), off);
    const { F: F2 } = S.couple({ template: 'ff' });
    app.addMoment({ type: 'CUM', frame: 10, sim: F2.id, cum: 'FACE', level: 2 });
    C('nobody has a penis: WickedWhims shows nothing, so neither does the app', JSON.stringify(Cum.activeCum(app, F2, 50, 0)) === '{}', Cum.activeCum(app, F2, 50, 0));
    const r404 = await fetch('/api/cum_tex?inst=0123456789abcdef');
    C('cum_tex only serves the listed parts (404 otherwise)', r404.status === 404, r404.status);
    return { checks: out };
  });
  const dataUrl = await pe(() => window.__r24.cumCanvas);
  if (dataUrl) fs.writeFileSync(path.join(OUT_DIR, 'cum_face3_atlas.png'), Buffer.from(dataUrl.split(',')[1], 'base64'));

  // ------------------------------------------------------------------ 12. Tray sims come with their own voice
  await run('12 tray voice', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app, S = window.__r24;
    const hh = await (await fetch('/api/tray')).json();
    const pick = g => { for (const x of hh) for (const s of x.sims) if (s.gender === g) return [x, s]; return null; };
    const got = [];
    S.couple({ template: 'solo' });
    for (const g of ['female', 'male']) {
      const hit = pick(g);
      if (!hit) continue;
      const [x, s] = hit;
      const want = await (await fetch(`/api/tray_voice?tray=${encodeURIComponent(x.id)}&index=${s.index}`)).json();
      await app.addTraySim(x.id, s.index, `${s.first} ${s.last}`);
      const sim = app.store.project.sims[app.store.project.sims.length - 1];
      await S.waitFor(() => sim.voice, 15000);
      got.push({ g, voice: sim.voice, want: want.voice, pitch: sim.voicePitch });
    }
    const men = hh.some(x => x.sims.some(s => s.gender === 'male'));
    C(`a woman from the Tray gets fa/fc/fd${men ? ', a man ma/mb/mc' : ' (no man in this Tray: the male side is checked in game_check.py)'} - their own game voice`,
      got.length === (men ? 2 : 1) && got.every(x => x.voice === x.want && (x.g === 'male' ? ['ma', 'mb', 'mc'] : ['fa', 'fc', 'fd']).includes(x.voice)), got);
    app.showStep('sounds');
    app.selectSim(app.store.project.sims[app.store.project.sims.length - 1].id);
    await S.sleep(100);
    C('the picker marks "their voice"', !!document.querySelector('#panel-body .vp-btn.on .vp-own'), document.querySelector('#panel-body .vp-now') && document.querySelector('#panel-body .vp-now').textContent);
    return { checks: out };
  });

  // ------------------------------------------------------------------ 13. creator moments come along with "Import as keys"
  await run('13 import creator moments', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app, S = window.__r24;
    const lib = await (await fetch('/api/library?q=')).json();
    const items = (lib.items || lib.animations || lib).filter ? (lib.items || lib.animations || lib) : [];
    let chosen = null;
    for (const it of items.slice(0, 400)) {
      if (!/LAMABOY/i.test(JSON.stringify(it))) continue;
      const ev = await (await fetch('/api/animation_events?id=' + it.id)).json();
      if ((ev.events || []).filter(e => e.type !== 'NOTE').length >= 1) { chosen = { it, n: ev.events.length }; break; }
    }
    if (!chosen) { C('a creator animation with moments was found', false, items.length); return { checks: out }; }
    const anim = await (await fetch(`/api/animation?id=${chosen.it.id}&step=1`)).json();
    app.library.startPreview(anim);
    const di = await import('/js/dialogs/import.js');
    const len = Math.max(...app.library.preview.players.map(pl => pl.frames));
    di.importKeys(app, app.library.preview, 10, 0, len, true);
    await S.sleep(200);
    const evs = app.store.project.events || [];
    C('Import as keys brings the creator\'s moments onto the Moments row', evs.length >= 1 && evs.every(e => app.store.project.sims.some(s => s.id === e.sim)), { anim: anim.name, server: chosen.n, imported: evs.map(e => [e.type, e.frame, e.cum || e.effect || e.naked || '']) });
    const bad = evs.filter(e => e.type === 'EFFECT' && (/_c_|_c$|Tip0\d|Tounge__4/.test(e.effect + e.joint)));
    C('no child effect or non-bone joint comes along', !bad.length, bad);
    return { checks: out };
  });

  // ------------------------------------------------------------------ 14. palette, help, toolbar
  await run('14 palette + help', async () => {
    const out = [], C = (n, ok, d) => out.push([n, !!ok, d]);
    const app = window.app;
    const cmds = app.runHook('commands', app).flat().filter(Boolean);
    const ids = cmds.map(c => c.id);
    C('palette: Add a moment, Finish (7), Effect…, Make it a climax, Show effects/cum', ['moment-add', 'effect-add', 'toggle-fx', 'toggle-cum'].every(i => ids.includes(i)) && ids.filter(i => /^finish-/.test(i)).length === 7, ids.filter(i => /moment|finish|effect|fx|cum|climax/.test(i)));
    const help = app.runHook('helpRows', app).flat().filter(Boolean).filter(r => r.group === 'Moments');
    C('help rows for the Moments row', help.length === 3, help.map(r => r.text));
    C('toolbar: Show effects and Show cum buttons (no index.html edit)', document.getElementById('btn-fx') && document.getElementById('btn-cum') && document.getElementById('btn-fx').closest('.view-cell'), 'ok');
    return { checks: out };
  });

  // ------------------------------------------------------------------ console
  const errs = logs.filter(l => l.type === 'pageerror' || (l.type === 'error' && !/Failed to load resource/.test(l.text)));
  check('no page errors or console errors', !errs.length, errs.slice(0, 5));
  // (only this feature's routes: other builders' routes may not be on this server yet)
  const mine = bad.filter(u => /\/api\/(voices|effects|cum_layers|cum_tex|tray_voice|sound|animation_events)/.test(u) && !/vo_x_does_not_exist_zz|cum_tex\?inst=0123456789abcdef/.test(u));
  check("no unexpected failed requests on this feature's routes", !mine.length, { mine: mine.slice(0, 5), others: [...new Set(bad.map(u => u.split('?')[0]))].slice(0, 6) });
  await browser.close();
  const passed = rows.filter(r => r.ok).length;
  fs.writeFileSync(OUT, JSON.stringify({ passed, failed: rows.length - passed, rows }, null, 1));
  H.report(rows.map(r => ({ name: r.name, ok: r.ok, detail: r.detail })), `R2-4 browser checks (port ${PORT}${PIN ? ', pinned files' : ''})`);
  process.exit(passed === rows.length ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
