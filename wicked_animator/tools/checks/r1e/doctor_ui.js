// R1-E check 5: the Game Doctor and "Did it play?" in the real app, against the fixture server.
//
//   node tools/checks/r1e/doctor_ui.js --port 8845
//
// 1. builds a fresh fixture (%TEMP%\wa_doctor\The Sims 4) with doctor_check.py --build-fixture
// 2. starts the app's server on the port with WICKED_SIMS_DIR = the fixture and a fake tasklist (the game is "closed")
// 3. opens the app (harness: every writing route answered in the browser, except /api/doctor_fix, which may reach
//    the fixture server) and checks: the Home card, the scan (screenshot mid-sweep), the results, "Park this file"
//    moving the fixture file, the palette commands, the wa:sent line in a mocked Send result with Check now, the
//    "Looked wrong -> take me to that frame" jump, and reduced motion.
// Screenshots and a JSON report go to cache/checks/r1e/. Exits 0 only when everything passes.
const path = require('path');
const fs = require('fs');
const { spawn, execFileSync } = require('child_process');
const H = require('../lib/harness.js');

const ROOT = H.ROOT;
const OUT = path.join(ROOT, 'cache', 'checks', 'r1e');
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
let PORT = +arg('--port', 8845);
const rows = [];
const check = (name, ok, detail) => { rows.push({ name, ok: !!ok, detail }); return ok; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const shotPath = f => path.join(OUT, f);

function buildFixture() {
  const out = execFileSync('python', [path.join(__dirname, 'doctor_check.py'), '--build-fixture'], { cwd: ROOT, encoding: 'utf-8' });
  return JSON.parse(out.trim().split('\n').pop());
}

function startServer(port, env) {
  return new Promise((resolve, reject) => {
    const p = spawn('python', [path.join(ROOT, 'tools', 'checks', 'lib', 'harness.py'), 'start', String(port)],
      { cwd: ROOT, env: { ...process.env, ...env }, windowsHide: true });
    let buf = '', err = '';
    const timer = setTimeout(() => reject(new Error('server did not start: ' + err.slice(-400))), 200000);
    p.stdout.on('data', d => {
      buf += d;
      const line = buf.split('\n').find(l => l.trim().startsWith('{'));
      if (line) { clearTimeout(timer); resolve({ proc: p, info: JSON.parse(line) }); }
    });
    p.stderr.on('data', d => { err += d; });
    p.on('exit', code => { clearTimeout(timer); reject(new Error(`harness exited (${code}): ${err.slice(-600)}`)); });
  });
}

function stopServer(s) {
  if (!s) return;
  try { execFileSync('taskkill', ['/PID', String(s.proc.pid), '/T', '/F'], { stdio: 'ignore' }); } catch { /* gone */ }
}

// In the page: the "Your own files are left alone" card, and every Park button that sits on one of the user's own
// tools (Sims Hub monitor / fast packs, Mods/FitStudio, Mods/animation) - there must be none.
function ownTools() {
  const TOOL = /SpeedKit_Monitor|!!!!!SpeedKit_Fast|Mods\/FitStudio\/|Mods\/animation\//i;
  const card = document.querySelector('.doc-card[data-id="own"]');
  const park = [...document.querySelectorAll('.doc-card:not([data-id="own"]) .doc-item')].filter(li => li.querySelector('.doc-btn[data-kind="park"]'));
  return {
    own: card ? { level: card.dataset.level, rows: card.querySelectorAll('.doc-item').length, buttons: card.querySelectorAll('.doc-btn').length,
      text: card.innerText.slice(0, 400) } : null,
    parkOnTools: park.filter(li => TOOL.test(li.innerText)).map(li => li.innerText.slice(0, 120)),
    parkOnOther: park.length,
  };
}

async function freeze(page, t = null) {
  await page.evaluate(ms => { for (const a of document.getAnimations()) { a.pause(); if (ms !== null) try { a.currentTime = ms; } catch { /* */ } } }, t);
}
async function thaw(page) { await page.evaluate(() => { for (const a of document.getAnimations()) a.play(); }); }

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const fx = buildFixture();
  const FIX = fx.fixture;
  check('0 fixture built', fs.existsSync(path.join(FIX, 'Mods', 'RigMod', 'Old_Rig_Fix.package')), FIX);
  let server = null, browser = null;
  for (const port of [PORT, 8851, 8852, 8853, 8854, 8855]) {
    try { server = await startServer(port, { WICKED_SIMS_DIR: FIX, WICKED_TASKLIST: fx.tasklist }); PORT = port; break; }
    catch (e) { console.log(`port ${port}: ${e.message.split('\n')[0]}`); }
  }
  if (!server) { console.log('could not start a server'); process.exit(1); }
  const report = { port: PORT, shots: [] };
  try {
    const st = await (await fetch(`http://127.0.0.1:${PORT}/api/doctor_status`)).json().catch(() => null);
    check('1 server has the doctor routes (ext_doctor.py)', st && 'cards' in st && st.sims_dir && st.sims_dir.toLowerCase() === FIX.toLowerCase(), st && st.sims_dir);

    // /api/doctor_fix goes straight from Chrome to the fixture server: the harness proxy re-sends allowed POSTs
    // without a Content-Length (chunked), which the stdlib server can't read (reported to R1-B). This listener runs
    // before the harness's and lets the request through untouched.
    const direct = page => page.on('request', req => {
      if (req.method() === 'POST' && new URL(req.url()).pathname === '/api/doctor_fix' && !req.isInterceptResolutionHandled()) req.continue().catch(() => {});
    });
    const o = await H.open(PORT, { w: 1366, h: 768, allow: ['/api/doctor_fix'], beforeLoad: direct });
    browser = o.browser;
    const { page, logs, writes } = o;
    // the feature loads through /api/features + app.loadFeatures; if an older tree has no loader, load it by hand
    const loaded = await page.evaluate(async () => {
      if (window.app.__doctor) return 'feature loader';
      const m = await import('/js/features/doctor.js'); m.install(window.app); return 'loaded by the check';
    });
    check('2 features/doctor.js installed', loaded === 'feature loader', loaded);
    const reg = await page.evaluate(() => {
      const a = window.app, run = n => (a.hooks[n] || []).flatMap(fn => { try { return fn(a) || []; } catch { return []; } });
      return { home: run('homeCards').map(c => [c.id, c.title, c.text]), commands: run('commands').map(c => [c.id, c.label]),
        help: run('helpRows').length, card: !!document.querySelector('[data-card="doctor"]') };
    });
    check('3 Home card "Check my game" + palette "Doctor" / "Did it play in the game?"',
      reg.home.some(c => c[0] === 'doctor' && c[1] === 'Check my game' && /why don't my animations show up/i.test(c[2]))
      && reg.commands.some(c => c[1] === 'Doctor') && reg.commands.some(c => c[1] === 'Did it play in the game?'), reg);
    await page.waitForFunction(() => { const c = document.querySelector('[data-card="doctor"]'); return !c || getComputedStyle(c).opacity === '1'; }, { timeout: 5000 }).catch(() => {});
    await sleep(900);                                            // Home's intro has settled
    report.shots.push(await H.shot(page, shotPath('home_card.png')));

    // ---- open from the Home card (or the palette command when Home is not showing)
    if (reg.card) await page.click('[data-card="doctor"]');
    else await page.evaluate(() => window.wickedDoctor.open());
    await page.waitForSelector('.doc-radar.scanning', { timeout: 5000 }).catch(() => {});
    await sleep(420);
    await freeze(page);
    const mid = await page.evaluate(() => ({ scanning: !!document.querySelector('.doc-radar.scanning'),
      sweep: getComputedStyle(document.querySelector('.doc-sweep')).animationName,
      cards: document.querySelectorAll('.doc-card').length, phase: document.querySelector('.doc-phase').textContent }));
    report.shots.push(await H.shot(page, shotPath('doctor_scanning.png')));
    await thaw(page);
    check('4 scanning: radar sweep turning', mid.scanning && mid.sweep === 'docSweep', mid);

    await page.waitForSelector('.doc-radar.done', { timeout: 30000 });
    await sleep(900);
    const res = await page.evaluate(() => {
      const card = id => { const el = document.querySelector(`.doc-card[data-id="${CSS.escape(id)}"]`); return el ? { level: el.dataset.level, text: el.innerText.slice(0, 300) } : null; };
      return { phase: document.querySelector('.doc-phase').textContent, meta: document.querySelector('.doc-meta').textContent,
        red: document.querySelectorAll('.doc-sec.lv-red .doc-card').length, yellow: document.querySelectorAll('.doc-sec.lv-yellow .doc-card').length,
        green: document.querySelectorAll('.doc-sec.lv-green .doc-card').length, info: document.querySelectorAll('.doc-sec.lv-info .doc-card').length,
        rig: card('rig'), depth: card('depth:scripts'), pack: card('pack:Anims/Test_Pack_A.package'),
        dyn: [...document.querySelectorAll('.doc-card[data-id^="dyn:"]')].map(e => e.innerText.slice(0, 200)),
        clipped: [...document.querySelectorAll('.doc-modal .btn')].filter(b => b.scrollWidth > b.clientWidth + 1).map(b => b.textContent),
        hidden: document.querySelector('.doc-modal').innerText.includes('Hidden Fixture') };
    });
    report.results = res;
    report.shots.push(await H.shot(page, shotPath('doctor_results.png')));
    check('5 results: green, yellow and red cards, each with a safe button', res.red === 3 && res.yellow >= 3 && res.green >= 1
      && res.rig && res.rig.level === 'red' && res.depth && res.pack && /LOVESE/.test(res.pack.text) && res.dyn.length === 2, res);
    check('6 no clipped buttons; hidden pack never previewed', !res.clipped.length && !res.hidden, { clipped: res.clipped, hidden: res.hidden });
    const tools = await page.evaluate(ownTools);
    report.ownTools = tools;
    check('6b your own tools: one green "left alone" card, never a Park button on them', tools.own && tools.own.level === 'green'
      && tools.own.buttons === 0 && tools.own.rows === 4 && !tools.parkOnTools.length && tools.parkOnOther >= 1, tools);
    // the lower part of the list
    await page.evaluate(() => { const b = document.querySelector('.doc-modal .body'); b.scrollTop = b.scrollHeight; });
    await sleep(150);
    report.shots.push(await H.shot(page, shotPath('doctor_results_more.png')));
    await page.evaluate(() => { const b = document.querySelector('.doc-modal .body'); b.scrollTop = 0; });

    // "Show which ones" lists the animations of a pack
    await page.click('.doc-card[data-id="pack:Anims/Test_Pack_A.package"] .doc-btn[data-kind="details"]');
    const names = await page.evaluate(() => document.querySelector('.doc-card[data-id="pack:Anims/Test_Pack_A.package"] .doc-names:not(.hidden)')?.innerText || '');
    check('7 "Show which ones" lists the animations', /Fixture Loveseat/.test(names) && /Fixture Placeholder/.test(names), names.slice(0, 200));

    // ---- Park this file (reaches the fixture server: harness allow)
    const src = path.join(FIX, 'Mods', 'RigMod', 'Old_Rig_Fix.package'), dst = path.join(FIX, 'Mods_parked', 'RigMod', 'Old_Rig_Fix.package');
    const before = fs.existsSync(src);
    await page.click('.doc-card[data-id="rig"] .doc-btn[data-kind="park"]');
    await page.waitForSelector('.doc-card[data-id="rig"] .doc-done', { timeout: 10000 }).catch(() => {});
    await sleep(500);
    const after = await page.evaluate(() => ({ done: document.querySelector('.doc-card[data-id="rig"] .doc-done')?.textContent,
      resolved: document.querySelector('.doc-card[data-id="rig"]').classList.contains('resolved'),
      fixed: document.querySelector('.doc-chip.fixed')?.textContent }));
    const manifest = JSON.parse(fs.readFileSync(path.join(FIX, 'Mods_parked', '_manifest.json'), 'utf-8'));
    await page.evaluate(() => document.querySelector('.doc-card[data-id="rig"]').scrollIntoView({ block: 'center' }));
    await sleep(120);
    report.shots.push(await H.shot(page, shotPath('doctor_parked.png')));
    check('8 clicking "Park this file" moves the fixture file', before && !fs.existsSync(src) && fs.existsSync(dst)
      && manifest.moved.includes('RigMod/Old_Rig_Fix.package') && after.done === 'Parked' && after.resolved
      && !writes.some(w => w.route === '/api/doctor_fix'), { after, manifest });

    // Rescan: the parked rig is gone from the cards
    await page.evaluate(() => [...document.querySelectorAll('.doc-modal footer .btn')].find(b => b.textContent === 'Rescan').click());
    await page.waitForSelector('.doc-radar.scanning', { timeout: 3000 }).catch(() => {});
    await page.waitForSelector('.doc-radar.done', { timeout: 30000 });
    await sleep(700);
    const rescan = await page.evaluate(() => ({ rig: !!document.querySelector('.doc-card[data-id="rig"]'), red: document.querySelectorAll('.doc-sec.lv-red .doc-card').length }));
    check('9 Rescan: the rig clash is gone', !rescan.rig && rescan.red === 2, rescan);
    await page.keyboard.press('Escape');
    await sleep(400);

    // ---- palette: "doctor" finds the command (R1-C's palette)
    const pal = await page.evaluate(async () => {
      try {
        const m = await import('/js/commands.js');
        const all = (m.allCommands || m.commands)(window.app);
        return all.filter(c => /doctor|did it play/i.test(c.label)).map(c => c.label);
      } catch (e) { return String(e); }
    });
    check("10 palette lists 'Doctor' and 'Did it play in the game?'", Array.isArray(pal) && pal.includes('Doctor') && pal.includes('Did it play in the game?'), pal);
    await page.keyboard.down('Control'); await page.keyboard.press('KeyK'); await page.keyboard.up('Control');
    await sleep(350);
    const palOpen = await page.evaluate(() => !!document.querySelector('.palette input'));
    if (palOpen) {
      await page.keyboard.type('doctor', { delay: 30 });
      await sleep(400);
      report.shots.push(await H.shot(page, shotPath('palette_doctor.png')));
      await page.keyboard.press('Escape');
      await sleep(300);
    }

    // ---- a mocked Send result: showExported emits wa:sent with heroSlot / extraSlot
    const proj = { name: 'FS Proof', author: 'FitStudio test', uid: 'a_doctor_ui', locations: ['DOUBLE_BED'], furniture: 'double_bed', sims: [] };
    await page.evaluate(async p => {
      const a = window.app;
      Object.assign(a.store.project, { name: p.name, author: p.author, locations: p.locations, furniture: p.furniture });
      let showExported = null;
      try { showExported = (await import('/js/dialogs/export.js')).showExported; } catch { /* older tree */ }
      const res = { path: 'C:\\(test)\\FitStudio_FitStudio_test_FS_Proof.package', bytes: 22875, next: [], next_names: [], warnings: [], replaced: [] };
      localStorage.setItem('fsa.firstSend', '1');
      if (showExported) showExported(a, res, a.store.project);
      else {
        const ui = await import('/js/ui.js');
        const heroSlot = ui.h('div'), extraSlot = ui.h('div');
        ui.modal({ title: "It's in your Mods folder", body: ui.h('div', {}, heroSlot, extraSlot), buttons: [{ label: 'Done', kind: 'primary' }] });
        a.emit('sent', { project: a.store.project, result: res, heroSlot, extraSlot, first: false });
      }
    }, proj);
    await page.waitForSelector('.extra-slot .dip, .dip', { timeout: 5000 }).catch(() => {});
    await sleep(1700);                      // let the celebration finish
    const sent = await page.evaluate(() => { const d = document.querySelector('.dip'); if (d) d.scrollIntoView({ block: 'end' }); return d ? d.innerText : null; });
    report.shots.push(await H.shot(page, shotPath('sent_line.png')));
    check('11 wa:sent fills extraSlot with the "Did it play?" line', sent && sent.includes("Play it in the game, then come back - we read WickedWhims' log and tell you if it played.")
      && sent.includes('Check now') && sent.includes('Looked wrong → take me to that frame'), (sent || '').slice(0, 260));

    // before playing: Check now says "Not played yet"
    await page.click('.dip-check');
    await page.waitForSelector('.dip-result .dip-msg', { timeout: 8000 }).catch(() => {});
    const notYet = await page.evaluate(() => document.querySelector('.dip-result')?.innerText || '');
    check('12 Check now before playing: "Not played yet ..."', /Not played yet/.test(notYet), notYet.slice(0, 200));

    // "play it in the game": WickedWhims writes its lines (appended to the fixture log with the current time)
    const now = new Date(), pad = n => String(n).padStart(2, '0');
    const stamp = `${pad(now.getMonth() + 1)}/${pad(now.getDate())}/${pad(now.getFullYear() % 100)} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    fs.appendFileSync(path.join(FIX, 'WickedWhimsInfoLog.log'),
      `${stamp} [ANIMATIONS/WARN] [INVALID EVENT] Sex Animation 'FS Proof' by 'FitStudio test' has invalid effect event.\n` +
      `${stamp} [SEX/INFO] Sims 'Male Sim 1'+'Female Sim 2' played 'FS Proof' sex animation by 'FitStudio test'.\n` +
      `${stamp} [SEX/INFO] Sims 'Sim A'+'Sim B' played 'Someone Elses' sex animation by 'Another Creator'.\n`);
    await page.click('.dip-check');
    await page.waitForFunction(() => /Played in the game/.test(document.querySelector('.dip-result')?.innerText || ''), { timeout: 8000 }).catch(() => {});
    await sleep(500);
    const played = await page.evaluate(() => document.querySelector('.dip-result')?.innerText || '');
    await page.evaluate(() => document.querySelector('.dip')?.scrollIntoView({ block: 'end' }));
    report.shots.push(await H.shot(page, shotPath('sent_played.png')));
    const hm = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
    check(`13 Check now after playing: "Played in the game ✓ (${hm})" + the problem in plain words`,
      played.includes(`Played in the game ✓ (${hm})`) && played.includes('WickedWhims skipped a moment: the effect needs a name')
      && !played.includes('Someone Elses'), played.slice(0, 300));

    // "Looked wrong -> take me to that frame"
    const jump = await page.evaluate(async () => {
      const rows = [...document.querySelectorAll('.dip-look-row')];
      const row = rows.find(r => /face/i.test(r.innerText)) || rows[0];
      const want = +(row.innerText.match(/frame (\d+)/) || [0, 0])[1];
      row.querySelector('.dip-jump').click();
      await new Promise(r => setTimeout(r, 400));
      return { want, frame: Math.round(window.app.store.frame), open: !!document.querySelector('#modal-root .backdrop:not(.leaving) .dip'), rows: rows.length };
    });
    check('14 "Looked wrong → take me to that frame" sets the frame and closes the dialog', jump.frame === jump.want && !jump.open && jump.rows === 4, jump);

    // the palette command's own dialog (reads the log at once)
    await page.evaluate(() => window.wickedDoctor.didItPlay());
    await page.waitForFunction(() => /Played in the game/.test(document.querySelector('.dip-modal .dip-result')?.innerText || ''), { timeout: 8000 }).catch(() => {});
    await sleep(400);
    const own = await page.evaluate(() => document.querySelector('.dip-modal .dip-result')?.innerText || '');
    report.shots.push(await H.shot(page, shotPath('did_it_play_dialog.png')));
    check('15 "Did it play in the game?" dialog', /Played in the game ✓/.test(own), own.slice(0, 200));
    await page.keyboard.press('Escape');
    await sleep(300);

    const errs = logs.filter(l => (l.type === 'error' || l.type === 'pageerror') && /doctor|dip|doc-/i.test(l.text + (l.stack || '')));
    check('16 no console errors from the doctor', !errs.length, errs.slice(0, 5));
    report.consoleErrors = logs.filter(l => l.type === 'error' || l.type === 'pageerror').slice(0, 20);
    report.proxyLogs = logs.filter(l => ['proxy', 'requestfailed', 'harness'].includes(l.type)).slice(0, 30);
    await browser.close(); browser = null;

    // ---- reduced motion: the dialog is complete and still (no sweep, no drops), 2 s after opening
    const r = await H.open(PORT, { w: 1366, h: 768, reducedMotion: true });
    browser = r.browser;
    await r.page.evaluate(async () => { if (!window.app.__doctor) (await import('/js/features/doctor.js')).install(window.app); });
    await r.page.evaluate(() => window.wickedDoctor.open());
    await sleep(2000);
    const rm = await r.page.evaluate(() => {
      const running = document.getAnimations().filter(a => a.playState === 'running' && a.effect && a.effect.target && a.effect.target.closest && a.effect.target.closest('.doc-modal'));
      return { done: !!document.querySelector('.doc-radar.done'), cards: document.querySelectorAll('.doc-card').length,
        running: running.map(a => `${a.animationName || a.constructor.name}:${a.effect.getComputedTiming().duration}`) };
    });
    report.shots.push(await H.shot(r.page, shotPath('doctor_reduced_motion.png')));
    check('17 reduced motion: done, cards shown, nothing moving after 2 s', rm.done && rm.cards > 5 && !rm.running.length, rm);
    await browser.close(); browser = null;

    // ---- the user's real folders, read-only (every writing route intercepted; nothing is clicked)
    stopServer(server); server = null;
    await sleep(800);
    const REAL = path.join(process.env.USERPROFILE, 'Documents', 'Electronic Arts', 'The Sims 4');
    const snap = () => ['Mods', 'Mods_parked', path.join('saves', 'WickedWhimsMod')].map(d => {
      let n = 0, t = 0;
      const walk = p => { for (const e of fs.readdirSync(p, { withFileTypes: true })) { const q = path.join(p, e.name); if (e.isDirectory()) walk(q); else { const s = fs.statSync(q); n++; t += s.mtimeMs + s.size; } } };
      try { walk(path.join(REAL, d)); } catch { /* missing */ }
      return `${d}:${n}:${t}`;
    }).join('|');
    const realBefore = snap();
    server = await startServer(PORT, { WICKED_SIMS_DIR: '', WICKED_TASKLIST: '' });
    const real = await H.open(PORT, { w: 1366, h: 768 });
    browser = real.browser;
    await real.page.evaluate(async () => { if (!window.app.__doctor) (await import('/js/features/doctor.js')).install(window.app); });
    await real.page.evaluate(() => window.wickedDoctor.open());
    await real.page.waitForSelector('.doc-radar.done', { timeout: 240000 });
    await sleep(1200);
    const realRes = await real.page.evaluate(() => ({ phase: document.querySelector('.doc-phase').textContent,
      meta: document.querySelector('.doc-meta').textContent, cards: [...document.querySelectorAll('.doc-card')].map(e => `${e.dataset.level}: ${e.querySelector('h4').textContent}`) }));
    report.real = realRes;
    report.shots.push(await H.shot(real.page, shotPath('doctor_real.png')));
    await real.page.evaluate(() => { const b = document.querySelector('.doc-modal .body'); b.scrollTop = b.scrollHeight; });
    await sleep(200);
    report.shots.push(await H.shot(real.page, shotPath('doctor_real_more.png')));
    const realAfter = snap();
    check('18 real folders in the app: scan shown, nothing written', realRes.cards.length > 0 && realBefore === realAfter && !real.writes.length,
      { phase: realRes.phase, meta: realRes.meta, cards: realRes.cards });
    const realTools = await real.page.evaluate(ownTools);
    report.realOwnTools = realTools;
    check('19 real folders: your own tools are left alone (green card, no Park button on them)',
      realTools.own && realTools.own.level === 'green' && realTools.own.buttons === 0 && !realTools.parkOnTools.length, realTools);
    await real.page.evaluate(() => document.querySelector('.doc-card[data-id="own"]')?.scrollIntoView({ block: 'center' }));
    await sleep(200);
    report.shots.push(await H.shot(real.page, shotPath('doctor_real_own.png')));
    await browser.close(); browser = null;
  } catch (e) {
    check('run', false, String(e && e.stack || e));
  } finally {
    if (browser) await browser.close().catch(() => {});
    stopServer(server);
  }
  fs.writeFileSync(path.join(OUT, 'doctor_ui.json'), JSON.stringify({ rows, report }, null, 1));
  const ok = H.report(rows, `R1-E doctor_ui (port ${PORT})`);
  console.log('screenshots:\n  ' + report.shots.join('\n  '));
  process.exit(ok ? 0 : 1);
})();
