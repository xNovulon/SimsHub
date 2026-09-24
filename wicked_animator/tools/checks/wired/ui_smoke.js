// The newly wired features in the running app (Playwright, no game needed): Say it, Move to another place / Make
// versions, strip-club dances, props, the game's own animations and idles, and the Doctor's Browse tab.
//   node tools/checks/wired/ui_smoke.js [--port 8792] [--keep]
// Starts tools/checks/lib/fake_game_server.py on the port (a stand-in rig and bodies, a throw-away home folder),
// opens the app, and for each feature: its Home card / palette command / step section opens, the no-game case says
// so plainly, and - with the game's answers stood in by page.route where a real game would give them - the whole
// path works (made, saved, baked, exported). Writing routes are answered in the browser (pw.js), except
// /api/dance_export in "check" mode, which only builds the package in memory. Fails on any uncaught error, failed
// module load or console error that is not an expected missing-game answer.
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn } = require('child_process');
const P = require('../lib/pw.js');

const ROOT = path.join(__dirname, '..', '..', '..');
const argv = process.argv.slice(2);
const PORT = +(argv[argv.indexOf('--port') + 1] || 0) || 8792;
const KEEP = argv.includes('--keep');
const OUT = path.join(ROOT, 'cache', 'checks', 'wired');

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

// a WAV click track (mono, 44.1 kHz): a click on every beat at `bpm`, first beat at `offset` s
function clickTrack(bpm, secs = 16, offset = 0.25) {
  const sr = 44100, n = sr * secs, data = Buffer.alloc(44 + n * 2);
  data.write('RIFF', 0); data.writeUInt32LE(36 + n * 2, 4); data.write('WAVE', 8); data.write('fmt ', 12);
  data.writeUInt32LE(16, 16); data.writeUInt16LE(1, 20); data.writeUInt16LE(1, 22); data.writeUInt32LE(sr, 24);
  data.writeUInt32LE(sr * 2, 28); data.writeUInt16LE(2, 32); data.writeUInt16LE(16, 34); data.write('data', 36); data.writeUInt32LE(n * 2, 40);
  for (let t = offset; t < secs; t += 60 / bpm) {
    const a = Math.round(t * sr);
    for (let i = 0; i < sr * 0.03 && a + i < n; i++) data.writeInt16LE(Math.round(26000 * Math.sin(2 * Math.PI * 1500 * i / sr) * Math.exp(-i / (sr * 0.006))), 44 + (a + i) * 2);
  }
  return data;
}

// a small textured-less box object like objmesh.object_mesh answers (for a stood-in place or prop)
function boxMesh(w, h, d, { surface = null, slots = [] } = {}) {
  const x = w / 2, z = d / 2;
  const v = [[-x, 0, -z], [x, 0, -z], [x, h, -z], [-x, h, -z], [-x, 0, z], [x, 0, z], [x, h, z], [-x, h, z]];
  const f = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 3, 7, 6, 3, 6, 2, 1, 2, 6, 1, 6, 5, 0, 4, 7, 0, 7, 3];
  const cell = 0.05, gw = Math.ceil(w / cell), gd = Math.ceil(d / cell);
  return { id: 1, name: 'stand-in', meshes: [{ positions: v.flat(), normals: [], uvs: [], faces: f, texture: null, transparent: false }],
    bounds: { min: [-x, 0, -z], max: [x, h, z] }, surface_height: surface === null ? h : surface,
    surface_grid: { x0: -x, z0: -z, cell, w: gw, d: gd, h: new Array(gw * gd).fill(Math.round(h * 1000)) }, slots };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const server = await startServer();
  const rows = [];
  let browser;
  const ok = (name, cond, detail) => rows.push({ name, ok: !!cond, detail });
  try {
    const o = await P.open(PORT);
    browser = o.browser;
    const { page, logs, writes } = o;
    const bad = [];                           // HTTP answers >= 400 that were not expected
    page.on('response', r => { if (r.status() >= 400 && !/favicon|fonts\.g/.test(r.url())) bad.push(`${r.status()} ${r.url().replace(/^https?:\/\/[^/]+/, '')}`); });
    const step = async (name, fn) => {
      try { const r = await fn(); ok(name, r !== false, typeof r === 'string' ? r : undefined); }
      catch (e) { ok(name, false, (e && e.message || String(e)).split('\n')[0]); await closeDialogs().catch(() => {}); }
    };
    // (a failed step leaves no dialog over the next one)
    const closeDialogs = () => page.evaluate(() => { document.querySelectorAll('#modal-root .backdrop .modal-x').forEach(b => b.click()); document.querySelector('.ctx-menu')?.remove(); });
    const shot = name => page.screenshot({ path: path.join(OUT, name + '.png') }).catch(() => {});
    const dialogText = () => page.evaluate(() => [...document.querySelectorAll('#modal-root .backdrop:not(.leaving) .modal')].map(m => m.innerText).join('\n---\n'));
    const waitText = (sel, rx, ms = 8000) => page.waitForFunction(([s, r]) => { const e = document.querySelector(s); return e && new RegExp(r, 'i').test(e.innerText); }, [sel, rx.source], { timeout: ms });

    // ---------------------------------------------------------------- boot
    await step('app boots with every plug-in', async () => {
      const r = await page.evaluate(() => ({ features: [...document.querySelectorAll('link[data-feature]')].map(l => l.getAttribute('href')),
        g: ['wickedEA', 'wickedSayIt', 'wickedRefit', 'wickedProps', 'wickedDance', 'wickedDoctor'].filter(k => !window[k]) }));
      if (r.g.length) throw new Error('not installed: ' + r.g.join(', '));
      return `css: ${r.features.join(', ')}`;
    });
    await step('Home: the new cards are there', async () => {
      const ids = await page.evaluate(() => [...document.querySelectorAll('#home [data-card]')].map(e => e.dataset.card));
      const want = ['sayit', 'ea-library', 'dance', 'doctor'];
      const miss = want.filter(x => !ids.includes(x));
      if (miss.length) throw new Error('missing ' + miss.join(', ') + ' in ' + ids.join(','));
      return ids.join(', ');
    });
    await step('palette (Ctrl+K): the new commands are listed', async () => {
      const ids = await page.evaluate(async () => { const m = await import('/js/commands.js'); return m.allCommands(window.app).map(c => c.id); });
      const want = ['sayit', 'ea-library', 'dance-new', 'doctor-browse', 'refit-move', 'refit-versions', 'prop-add'];
      const miss = want.filter(x => !ids.includes(x));
      if (miss.length) throw new Error('missing ' + miss.join(', '));
      await page.keyboard.press('Control+KeyK');
      await page.waitForSelector('.palette input', { timeout: 4000 });
      await page.keyboard.type('say it');
      await page.waitForFunction(() => /Say it/.test(document.querySelector('.palette-list')?.innerText || ''), null, { timeout: 4000 });
      await page.keyboard.press('Enter');
      await page.waitForSelector('.sayit-modal', { timeout: 4000 });
      await closeDialogs();
      return 'Ctrl+K -> "say it" -> Enter opens Say it';
    });

    // ---------------------------------------------------------------- Say it
    await step('Say it: the sentence becomes chips', async () => {
      await page.click('#home [data-card="sayit"]');
      await page.waitForSelector('.sayit-input');
      await page.fill('.sayit-input', 'slow cowgril on the sofa, she\'s teasing him, 5 seconds');
      const chips = await page.$$eval('.sayit-chip', els => els.map(e => e.innerText.replace(/\s+/g, ' ')));
      const notes = await page.$eval('.sayit-notes', e => e.innerText);
      for (const want of ['Cowgirl', 'Sofa', 'Teasing', 'Slow', '5 s']) if (!chips.some(c => c.includes(want))) throw new Error(`no ${want} chip: ${chips.join(' | ')}`);
      if (!/cowgril.*cowgirl/i.test(notes)) throw new Error('the spelling fix is not shown: ' + notes);
      await shot('sayit');
      return chips.join(' | ');
    });
    await step('Say it: a sentence about minors is refused', async () => {
      await page.fill('.sayit-input', 'a teen and her boyfriend on the bed');
      const r = await page.evaluate(() => ({ text: document.querySelector('.sayit-refused').innerText, hidden: document.querySelector('.sayit-refused').classList.contains('hidden'),
        disabled: document.querySelector('.sayit-modal footer .btn.primary').disabled, chips: document.querySelectorAll('.sayit-chip').length }));
      if (r.hidden || !r.disabled || r.chips) throw new Error(JSON.stringify(r));
      return r.text;
    });
    await step('Say it: a chip can be changed by clicking it', async () => {
      await page.fill('.sayit-input', 'slow cowgirl on the sofa, 5 seconds, eye contact');
      await page.click('.sayit-chip[data-slot="place"]');
      await page.waitForSelector('.ctx-menu');
      await page.click('.ctx-menu button:has-text("Loveseat")');
      await page.waitForFunction(() => /Loveseat/.test(document.querySelector('.sayit-chip[data-slot="place"]').innerText));
      return 'Place: Sofa -> Loveseat';
    });
    await step('Say it: Make it builds the scene', async () => {
      await page.click('.sayit-modal footer .btn.primary');
      await page.waitForFunction(() => app.store.project.sayit && !document.querySelector('.sayit-modal'), null, { timeout: 30000 });
      const r = await page.evaluate(() => { const p = app.store.project; return { furniture: p.furniture, length: p.length, sims: p.sims.length, spec: p.sayit.spec,
        look: p.sims.filter(s => (s.layers || []).some(l => l.type === 'look')).length, layers: p.sims.map(s => (s.layers || []).map(l => l.type).join('+')), step: app.step }; });
      if (r.furniture !== 'loveseat' || r.length !== 150 || r.sims !== 2 || r.spec.act !== 'cowgirl' || r.look !== 2) throw new Error(JSON.stringify(r));
      return `loveseat, 150 frames, motions ${r.layers.join(' / ')}, eye contact on both`;
    });
    await step('Say it: a follow-up changes the same animation', async () => {
      const before = await page.evaluate(() => ({ uid: app.store.project.uid, name: app.store.project.name, strokes: app.store.project.sims.flatMap(s => s.layers).find(l => ['ride', 'thrust'].includes(l.type)).params }));
      await page.evaluate(() => window.wickedSayIt.open());
      await page.waitForSelector('.sayit-input');
      await page.fill('.sayit-input', 'much rougher and longer');
      const label = await page.$eval('.sayit-modal footer .btn.primary', b => b.textContent);
      if (label !== 'Change it') throw new Error('button says ' + label);
      await page.click('.sayit-modal footer .btn.primary');
      await page.waitForFunction(() => !document.querySelector('.sayit-modal'), null, { timeout: 30000 });
      const after = await page.evaluate(() => ({ uid: app.store.project.uid, name: app.store.project.name, length: app.store.project.length, force: app.store.project.sayit.spec.force }));
      if (after.uid !== before.uid || after.name !== before.name || after.length !== 225 || !(after.force > 0.55)) throw new Error(JSON.stringify({ before, after }));
      return `same animation (${after.name}), 7.5 s, strength ${after.force}`;
    });
    await step('Say it: the Motion step offers "Change it in words"', async () => {
      await page.evaluate(() => app.showStep('motion'));
      const t = await page.$eval('#panel-body', e => e.textContent);
      if (!/Made from your words/i.test(t) || !/Change it in words/.test(t)) throw new Error('no section: ' + JSON.stringify(await page.evaluate(() => ({ step: app.step, sayit: !!app.store.project.sayit, modals: document.querySelectorAll('#modal-root .backdrop').length, tail: document.querySelector('#panel-body').textContent.slice(-300) }))));
      return 'section shown';
    });

    // ---------------------------------------------------------------- the game's own animations and idles
    await step('Game animations: no game -> a plain message', async () => {
      await page.evaluate(() => window.wickedEA.open());
      await waitText('.ea-dlg .hint', /not found on this PC|being read|Reading/);
      await page.waitForFunction(() => /not found on this PC/.test(document.querySelector('.ea-dlg').innerText), null, { timeout: 10000 });
      const t = await page.$eval('.ea-dlg .hint', e => e.innerText);
      await closeDialogs();
      return t;
    });
    await step('Game animations: with the game, one opens in the preview bar', async () => {
      const clip = x => ({ ticks: 60, fps: 30, tracks: { b__Pelvis__: { t: [[0, x, 1, 0], [59, x, 1.03, 0]], r: [[0, 0, 0, 0, 1]] }, b__Spine0__: { t: [[0, x, 1.03, 0]] } } });
      await page.route('**/api/ea_library?*', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ ready: true, total: 1, categories: { Kisses: 1 },
        items: [{ id: 'ea:a2a_kiss_romantic', name: 'Kiss romantic', author: 'The Sims 4', locations: ['Standing'], category: 'Kisses', kind: 'kiss', loop: true, seconds: 2, actors: ['BOTH', 'BOTH'], tags: [] }] }) }));
      await page.route('**/api/ea_animation?*', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'ea:a2a_kiss_romantic', name: 'Kiss romantic', author: 'The Sims 4',
        locations: ['Standing'], category: 'Kisses', kind: 'kiss', actors: ['BOTH', 'BOTH'], clips: [clip(0), clip(0.3)], events: [] }) }));
      await page.evaluate(() => window.wickedEA.open());
      await page.waitForSelector('.ea-item');
      await shot('ea_library');
      await page.click('.ea-item');
      await page.waitForFunction(() => app.preview && !document.querySelector('#preview-bar').classList.contains('hidden'), null, { timeout: 8000 });
      const r = await page.evaluate(() => ({ title: document.querySelector('#preview-title').textContent, genders: app.preview.anim.actors.map(a => a.gender), locations: app.preview.anim.locations, category: app.preview.anim.category }));
      if (r.genders.join() !== 'FEMALE,MALE' || r.locations[0] !== 'FLOOR' || r.category !== 'TEASING') throw new Error(JSON.stringify(r));
      await page.evaluate(() => app.library.stopPreview());
      await page.unroute('**/api/ea_library?*'); await page.unroute('**/api/ea_animation?*');
      return `${r.title} - ${r.genders.join(' + ')}, ${r.category}, ${r.locations}`;
    });
    await step('Motion step: an idle from the game gets a picker (no game -> says so)', async () => {
      await page.evaluate(() => { const s = app.store.sim() || app.store.project.sims[0]; app.store.selected.sim = s.id; app.addLayer(s.id, 'idle'); app.showStep('motion'); });
      await page.waitForFunction(() => /Idle from the game/i.test(document.querySelector('#panel-body').textContent) && /not found on this PC/.test(document.querySelector('.ea-idles')?.textContent || ''), null, { timeout: 10000 });
      return 'no-game message shown';
    });

    await step('Motion step: with the game, the idle picker changes the clip', async () => {
      await page.route('**/api/ea_idles', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ ready: true, groups: [
        { id: 'stand', label: 'Standing', items: [{ name: 'a_idle_neutral_loop_3_x', label: 'Neutral loop 3' }, { name: 'a_idle_female_sway_x', label: 'Female sway' }] },
        { id: 'bed', label: 'In bed', items: [{ name: 'a2o_bed_relax_idle_breathe_x', label: 'Bed relax breathing' }] }] }) }));
      await page.evaluate(() => app.renderStep());
      await page.waitForSelector('.ea-idles select', { timeout: 8000 });
      await page.selectOption('.ea-idles select', 'a_idle_female_sway_x');
      const clip = await page.evaluate(() => (app.store.sim().layers || []).find(l => l.type === 'idle').params.clip);
      await page.unroute('**/api/ea_idles');
      if (clip !== 'a_idle_female_sway_x') throw new Error(clip);
      return 'idle clip -> ' + clip;
    });

    // ---------------------------------------------------------------- props
    await step('Props: no game -> "No props found"', async () => {
      await page.evaluate(() => app.showStep('scene'));
      await page.waitForSelector('[data-props="add"]');
      await page.click('[data-props="add"]');
      await waitText('.pr', /No props found|not found/);
      const t = await page.$eval('.pr', e => e.innerText);
      await closeDialogs();
      return t.split('\n').pop();
    });
    await step('Props: a prop goes in the hand, follows it, and is baked for the game', async () => {
      await page.route('**/api/props', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify([{ guid: '14961458478131052544', objName: 'glassWine', name: 'Wine glass', uses: 7, source: 'game' }]) }));
      await page.click('[data-props="add"]');
      await page.waitForSelector('.pr-item');
      await page.click('.pr-item');
      await page.waitForFunction(() => (app.store.project.props || []).length === 1 && document.querySelector('.pr-row'), null, { timeout: 8000 });
      await P.sleep(300);
      await shot('props_scene');
      const r = await page.evaluate(() => {
        const p = app.store.project, prop = p.props[0];
        app.setFrame(20);
        const o = window.wickedProps.stage.objs.get(prop.id);
        const v = app.simViews.get(prop.hold.sim), b = v.bone(prop.hold.bone);
        const bw = b.getWorldPosition(new o.position.constructor());
        const baked = app.bake();
        const t = baked.props && baked.props[0] && baked.props[0].track.t;
        return { hold: prop.hold.bone, guid: baked.props && baked.props[0].guid, frames: t && t.length, len: p.length, obj: o.position.toArray(), bone: bw.toArray(), t20: t && t[20], standIn: !!o.userData.standIn };
      });
      const d = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
      if (r.frames !== r.len || d(r.obj, r.bone) > 1e-4 || d(r.t20, r.bone) > 2e-3) throw new Error(JSON.stringify(r));
      return `${r.hold}, ${r.frames} frames, track at frame 20 within ${(d(r.t20, r.bone) * 1000).toFixed(2)} mm of the hand's prop bone${r.standIn ? ' (stand-in box: no mesh without the game)' : ''}`;
    });
    await step('Props: Send to game carries the prop track', async () => {
      const n0 = writes.length;
      await page.evaluate(async () => { const { api } = await import('/js/api.js'); await api.export(app.bake()); });
      const w = writes.slice(n0).find(x => x.route === '/api/export');
      const body = w && JSON.parse(w.body);
      if (!body || !body.props || body.props.length !== 1 || body.props[0].track.r.length !== body.frames) throw new Error('no props in the export');
      await page.evaluate(() => { app.store.project.props = []; window.wickedProps.stage.sync(); });
      return `props: ${body.props.map(p => p.name).join(', ')}`;
    });

    // ---------------------------------------------------------------- move to another place, versions
    await step('Move to another place: no game -> a plain message', async () => {
      await page.evaluate(() => app.showStep('scene'));
      await page.click('[data-refit="move"]');
      await waitText('.rf', /not found on this PC|could not be read/, 10000);
      const t = await page.$eval('.rf-groups', e => e.innerText);
      await closeDialogs();
      return t;
    });
    await step('Move to another place: onto a bathtub, as a new animation', async () => {
      const tub = boxMesh(1.7, 0.55, 0.8);
      await page.route('**/api/refit_places', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ groups: ['Beds', 'Bath and water', 'My CC furniture'], cc_status: 'none', cc_note: 'No CC furniture with a top surface was found in the Mods folder.', cc: [],
        places: [{ id: 'ww:BATHTUB', location: 'BATHTUB', label: 'Bathtub', group: 'Bath and water', kind: 'water', object_id: 123, surface_height: 0.55, seats: 0, lying: 1 }] }) }));
      await page.route('**/api/refit_places?place=*', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify(tub) }));
      await page.evaluate(async () => { const R = await import('/js/refit.js'); R.loadPlaces({ force: true }).catch(() => {}); });
      const before = await page.evaluate(() => ({ uid: app.store.project.uid, name: app.store.project.name }));
      await page.click('[data-refit="move"]');
      await page.waitForSelector('.rf-groups [data-place="ww:BATHTUB"]');
      await page.click('.rf-groups [data-place="ww:BATHTUB"]');
      await shot('refit_move');
      await page.click('.rf-modal footer .btn.primary');
      await page.waitForFunction(() => app.store.project.furniture === 'ww:BATHTUB' && /Saved as|is ready/.test(document.querySelector('#modal-root')?.innerText || ''), null, { timeout: 60000 });
      const r = await page.evaluate(() => ({ uid: app.store.project.uid, name: app.store.project.name, loc: app.store.project.locations, def: app.furniture.find(f => f.id === 'ww:BATHTUB')?.label,
        report: [...document.querySelectorAll('#modal-root .backdrop:not(.leaving) .modal')].pop()?.innerText, onStage: app.vp.furniture.children.length }));
      const saves = writes.filter(x => x.route === '/api/project').map(x => JSON.parse(x.body).name);
      await closeDialogs();
      if (r.uid === before.uid || r.loc[0] !== 'BATHTUB' || !r.def || !saves.includes(r.name)) throw new Error(JSON.stringify({ r, saves }));
      return `"${r.name}" (${r.loc}), saved; ${r.report.split('\n').slice(2, 4).join(' ')}`;
    });
    await step('Make versions: taller + two women, each saved', async () => {
      await page.evaluate(() => app.showStep('scene'));
      await page.click('[data-refit="versions"]');
      await page.waitForSelector('.rf-modal [data-version]');
      const first = await page.$eval('.rf-modal [data-version^="h:"][data-version$=":tall"]', e => e.dataset.version);
      await page.click(`.rf-modal [data-version="${first}"]`);
      await page.click('.rf-modal [data-version="p:ff"]');
      await shot('refit_versions');
      const n0 = writes.filter(x => x.route === '/api/project').length;
      await page.click('.rf-modal footer .btn.primary');
      await page.waitForFunction(() => /versions? saved/.test(document.querySelector('#modal-root')?.innerText || ''), null, { timeout: 60000 });
      const names = writes.filter(x => x.route === '/api/project').slice(n0).map(x => { const b = JSON.parse(x.body); return `${b.name} [${b.sims.map(s => s.frame + (s.strapon ? '+strap-on' : '')).join(', ')}]`; });
      const tray = await page.evaluate(() => document.querySelector('.rf-tray')?.innerText || '');
      await closeDialogs();
      if (names.length !== 2 || !names.some(n => /yf\+strap-on/.test(n))) throw new Error(names.join(' | '));
      return names.join(' | ');
    });

    await step('Two women: the one who gives wears a strap-on in the preview (and keeps it for the game)', async () => {
      const r = await page.evaluate(() => {
        const p = app.store.project, giver = p.sims.find(s => s.frame === 'ym') || p.sims[1];
        giver.frame = 'yf'; giver.gender = 'FEMALE'; giver.strapon = true; giver.strapView = true;
        app.syncViews();
        const v = app.simViews.get(giver.id);
        const baked = app.bake();
        const i = p.sims.indexOf(giver);
        return { strap: !!(v && v._strap), strapon: baked.actors[i].strapon };
      });
      if (!r.strap || !r.strapon) throw new Error(JSON.stringify(r));
      return 'strap-on shown; animation_allow_strapon kept';
    });

    // ---------------------------------------------------------------- strip-club dances
    await step('Dance: the new-dance window finds the beat of a song', async () => {
      await page.evaluate(() => window.wickedDance.open());
      await page.waitForSelector('.dn-modal input[type=file]', { state: 'attached' });
      await page.setInputFiles('.dn-modal input[type=file]', { name: 'clicks_128.wav', mimeType: 'audio/wav', buffer: clickTrack(128) });
      await page.waitForFunction(() => /BPM/.test(document.querySelector('.dn-song').innerText) && !/Listening/.test(document.querySelector('.dn-song').innerText), null, { timeout: 30000 });
      const r = await page.evaluate(() => ({ song: document.querySelector('.dn-song').innerText, bpm: +document.querySelector('.dn-bpm').value, loop: document.querySelector('.dn-loop').innerText }));
      if (Math.abs(r.bpm - 128) > 2) throw new Error(JSON.stringify(r));
      await shot('dance_new');
      return `${r.song.split('.')[0]}. ${r.loop}`;
    });
    await step('Dance: Make the dance -> a pole dance on the beat, with the pole and a Beats row', async () => {
      await page.click('.dn-modal footer .btn.primary');
      await page.waitForFunction(() => app.store.project.dance, null, { timeout: 8000 });
      await P.sleep(600);
      const r = await page.evaluate(() => ({ d: app.store.project.dance, len: app.store.project.length, pole: window.wickedDance.stage.group.children.length, standIn: window.wickedDance.stage.standIn,
        row: app.timeline.rows.some(x => x.id === 'dance-beats'), song: !!window.wickedDance.song.buffer }));
      const want = Math.round(16 * 60 / r.d.bpm * 30);
      if (r.d.type !== 'POLE_DANCE' || Math.abs(r.len - want) > 1 || !r.pole || !r.row) throw new Error(JSON.stringify(r));
      return `${r.d.bpm} BPM, ${r.len} frames, ${r.d.loops}x; pole ${r.standIn ? 'stand-in (no WickedWhims here)' : 'from WickedWhims'}; song kept: ${r.song}`;
    });
    await step('Dance: Share step -> Show the XML (built in memory by the server)', async () => {
      await page.evaluate(() => app.showStep('share'));
      await page.waitForSelector('[data-dance="check"]');
      await shot('dance_share');
      await page.click('[data-dance="check"]');
      await page.waitForSelector('.dn-xml', { timeout: 20000 });
      const xml = await page.$eval('.dn-xml', e => e.textContent);
      await closeDialogs();
      for (const want of ['StripClubDanceAnimationPackage', '<T n="dance_type">POLE_DANCE</T>', 'dancer_animation_clip_name', '<T n="animation_loops">4</T>']) if (!xml.includes(want)) throw new Error('missing ' + want);
      return xml.split('\n').find(l => l.includes('dancer_animation_clip_name')).trim();
    });
    await step('Dance: Send dance to game (answered in the browser)', async () => {
      await page.route('**/api/dance_export', async r => {
        const b = JSON.parse(r.request().postData());
        if (b.mode === 'check') return r.continue();
        return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true, fake: true, mode: b.mode }) });
      });
      await page.click('[data-dance="send"]');
      await page.waitForFunction(() => /test mode/.test(document.querySelector('#toasts')?.innerText || ''), null, { timeout: 8000 });
      const checks = await page.evaluate(async () => { const m = await import('/js/dialogs/export.js'); return m.exportChecks(app).map(x => x.text); });
      if (!checks.some(t => /strip-club dance/.test(t))) throw new Error('no warning on Send to game: ' + checks.join(' | '));
      return 'sent; plain Send to game warns that it makes a normal animation';
    });

    // ---------------------------------------------------------------- the Doctor's Browse tab
    await step('Doctor: the Browse tab (no animations here)', async () => {
      await page.evaluate(() => window.wickedDoctor.browse());
      await waitText('.db', /No WickedWhims animations here|animations/, 20000);
      const t = await page.$eval('.db', e => e.innerText);
      await closeDialogs();
      return t.split('\n').slice(0, 2).join(' / ');
    });
    await step('Doctor: Browse lists, stars and turns off (kept in the app when not proven)', async () => {
      const items = [
        { id: 'a'.repeat(40), name: 'Slow ride', author: 'Anna', act: 'VAGINAL', act_label: 'Vaginal', places: ['Double bed'], sims: 2, genders: ['FEMALE', 'MALE'], where: 'mods', file: 'Mods/Anna/ride.package', fav: false, off: false, props: 0, hidden: false, lib: null },
        { id: 'b'.repeat(40), name: 'Kiss', author: 'Bo', act: 'TEASING', act_label: 'Teasing', places: ['Floor'], sims: 2, genders: ['BOTH', 'BOTH'], where: 'mods', file: 'Mods/Bo/kiss.package', fav: false, off: false, props: 1, hidden: false, lib: 3 }];
      await page.route('**/api/doctor_browse?*', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ ready: true, total: 2, items, writes: 'app', places: { DOUBLE_BED: 1, FLOOR: 1 }, acts: { VAGINAL: 1, TEASING: 1 },
        counts: { mods: 2, parked: 0, fav: 0, off: 0 }, proof: { proven: false, text: "WickedWhims hasn't listed your animations yet." } }) }));
      await page.evaluate(() => window.wickedDoctor.browse());
      await page.waitForSelector('.db-row');
      await page.click(`.db-row[data-id="${'a'.repeat(40)}"] .db-star`);
      await page.click(`.db-row[data-id="${'b'.repeat(40)}"] .db-off`);
      await shot('doctor_browse');
      const r = await page.evaluate(() => ({ lists: JSON.parse(localStorage.getItem('fsa.doctor.lists')), rows: document.querySelectorAll('.db-row').length,
        star: document.querySelector('.db-row .db-star.on') !== null, watch: document.querySelectorAll('.db-watch').length, proof: document.querySelector('.db-proof').innerText }));
      await page.click('.doc-tabs [data-tab="check"]');
      const checkShown = await page.evaluate(() => !document.querySelector('.doc-tab-check').classList.contains('hidden'));
      await closeDialogs();
      await page.unroute('**/api/doctor_browse?*');
      if (r.rows !== 2 || !r.lists || r.lists.fav.length !== 1 || r.lists.off.length !== 1 || !r.star || r.watch !== 1 || !checkShown) throw new Error(JSON.stringify(r));
      return `2 rows, 1 favorite + 1 turned off kept in the app; "${r.proof.split('\n')[0]}"`;
    });
    await step('Doctor: with the identifier proven, a star goes to WickedWhims (doctor_fix)', async () => {
      const item = { id: 'c'.repeat(40), name: 'Sofa ride', author: 'Cy', act: 'VAGINAL', act_label: 'Vaginal', places: ['Sofa'], sims: 2, genders: ['FEMALE', 'MALE'], where: 'mods', file: 'Mods/x.package', fav: false, off: false, props: 0, hidden: false, lib: null };
      await page.route('**/api/doctor_browse?*', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ ready: true, total: 1, items: [item], writes: 'ww', places: {}, acts: {}, counts: { mods: 1 }, proof: { proven: true, text: 'Checked against WickedWhims\' own lists.' } }) }));
      let sent = null;
      await page.route('**/api/doctor_fix', r => { sent = JSON.parse(r.request().postData()); return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true, changed: true, on: true, text: '"Sofa ride" is a favorite in WickedWhims now.' }) }); });
      await page.evaluate(() => window.wickedDoctor.browse());
      await page.waitForSelector('.db-row .db-star');
      await page.click('.db-row .db-star');
      await page.waitForSelector('.db-row .db-star.on');
      await closeDialogs();
      await page.unroute('**/api/doctor_browse?*'); await page.unroute('**/api/doctor_fix');
      if (!sent || sent.action !== 'favorite' || sent.on !== true || sent.id !== item.id) throw new Error(JSON.stringify(sent));
      return JSON.stringify(sent);
    });

    await page.screenshot({ path: path.join(OUT, 'last.png') });
    // ---------------------------------------------------------------- nothing broke
    const expected = [/Failed to load resource/, /GPU stall|WebGL|swiftshader|GroupMarkerNotSet/i, /fonts\.googleapis/];
    const errs = P.problems(logs, { ignore: expected });
    ok('no uncaught errors, failed module loads or console errors', !errs.length, errs.slice(0, 6).map(e => `${e.type}: ${e.text.slice(0, 200)}`).join(' | ') || 'clean');
    const missing = [...new Set(bad)].filter(x => !/api\/(tones|sounds|sound|voices|effects|cum_layers|ea_|refit_places|prop_mesh|dance_pole|dance_spot|skin|furniture_mesh|tray|exports|animation_events|recovery|library|hair|project_thumb)/.test(x));
    ok('no unexpected HTTP errors (only missing-game answers)', !missing.length, missing.slice(0, 8).join(' | ') || [...new Set(bad)].length + ' expected missing-game answers');
  } catch (e) {
    ok('the check ran to the end', false, e.stack || String(e));
  } finally {
    if (browser && !KEEP) await browser.close();
    server.proc.kill();
  }
  const pass = P.report(rows, 'Wired features in the app (Playwright, no game)');
  process.exit(pass ? 0 : 1);
})();
