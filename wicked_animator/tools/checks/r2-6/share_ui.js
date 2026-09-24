// R2-6 check (the app): pose packs and the promo kit, in the real app through the test harness.
//
//   node tools/checks/r2-6/share_ui.js [--port 8856] [--reuse]
//
// Starts the app's server (WICKED_EXPORTS_DIR = a %TEMP% folder) unless --reuse finds one answering on the port, then
// in Chrome (harness: every writing route - /api/posepack and /api/promo_save included - is answered in the browser,
// nothing reaches a disk):
//   - the Share step shows "Make a promo kit" and "Export as a pose pack";
//   - pose packs: 3 keys of one sim give 3 poses (each with a 64 x 64 picture and one frame of tracks); a couple with
//     1 key gives 2 poses; the requests are kept in cache/checks/r2-6/ for posepack_check.py (built offline there);
//   - an explicit project (Magic cowgirl) is refused with the one-line message and nothing is sent;
//   - the promo kit on a 3 s loop: 3 GIFs at 480 px, each < 5 MB, decoding in the page (Image.decode) and here, their
//     first and last frames differ by about one step (seamless); a PNG thumbnail; a 10 s video; the post text has the
//     name, acts, places and credits; everything is put back afterwards (camera, frame, playing, helpers...);
//   - the safe teaser (shoulders up, blur band);
//   - screenshots at 1366 x 768 and 1920 x 1080 (and reduced motion).
// Exits 0 only when everything passes.
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn, execFileSync } = require('child_process');
const H = require('../lib/harness.js');
const { decodeGif } = require('./gifdecode.js');

const ROOT = H.ROOT;
const OUT = path.join(ROOT, 'cache', 'checks', 'r2-6');
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
let PORT = +arg('--port', 8856);
const REUSE = process.argv.includes('--reuse');
const rows = [];
const check = (name, ok, detail) => { rows.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  ${detail === undefined ? '' : typeof detail === 'string' ? detail : JSON.stringify(detail)}`.slice(0, 400)); return ok; };
const shot = (page, f) => H.shot(page, path.join(OUT, f));
const TMP = path.join(os.tmpdir(), 'wa_r26_ui');

function startServer(port, env) {
  return new Promise((resolve, reject) => {
    const p = spawn('python', [path.join(ROOT, 'tools', 'checks', 'lib', 'harness.py'), 'start', String(port)],
      { cwd: ROOT, env: { ...process.env, ...env }, windowsHide: true });
    let buf = '', err = '';
    const timer = setTimeout(() => reject(new Error('server did not start: ' + err.slice(-400))), 240000);
    p.stdout.on('data', d => { buf += d; const line = buf.split('\n').find(l => l.trim().startsWith('{')); if (line) { clearTimeout(timer); resolve({ proc: p, info: JSON.parse(line) }); } });
    p.stderr.on('data', d => { err += d; });
    p.on('exit', code => { clearTimeout(timer); reject(new Error(`harness exited (${code}): ${err.slice(-600)}`)); });
  });
}
function stopServer(s) { if (s) { try { execFileSync('taskkill', ['/PID', String(s.proc.pid), '/T', '/F'], { stdio: 'ignore' }); } catch { /* gone */ } } }
async function answering(port) { try { const r = await fetch(`http://127.0.0.1:${port}/api/status`); return r.ok; } catch { return false; } }

// ---------------------------------------------------------------- in-page helpers
async function ready(page) {
  await page.waitForFunction(() => window.app && typeof window.app.newScene === 'function' && document.querySelector('#loading.done'), { timeout: 180000 });
  await page.evaluate(async () => {
    const home = await import('/js/home.js');
    window.__r26 = {
      hideHome: () => home.hideHome(window.app),
      closeModals: () => document.querySelectorAll('#modal-root .backdrop').forEach(b => b.remove()),
      state: () => {
        const a = window.app, vp = a.vp, r = x => Math.round(x * 1000) / 1000;
        return { cam: vp.camera.position.toArray().map(r), target: vp.controls.target.toArray().map(r), frame: a.store.frame, playing: a.playing,
          tool: a.interact.tool, showcase: !!document.querySelector('#btn-showcase.on'), overlay: vp.overlay.visible, gizmo: vp.gizmo.visible,
          origin: vp.origin ? vp.origin.visible : null, sims: [...a.simViews.values()].map(v => v.group.visible), paused: vp.paused,
          recording: document.body.classList.contains('recording'), cine: !!(vp.stage && vp.stage.isCinematic), busy: !!a._stageBusy,
          gizmoOn: vp.gizmo.object ? vp.gizmo.object.name : null, active: a.interact.active ? a.interact.active.bone || a.interact.active.kind : null };
      },
    };
  });
}

// A scene: 'solo3' / 'couple3' (Teasing, clothes on, keys at 0 / 30 / 60 with different arms), 'cowgirl' (Magic, 3 s).
async function scene(page, kind) {
  await page.evaluate(async kind => {
    const a = window.app;
    __r26.closeModals();
    if (kind === 'cowgirl') {
      const magic = await import('/js/magic.js');
      await magic.makeMagic(a, { recipe: 'cowgirl', place: 'double_bed', intensity: 0.55, seconds: 3, name: 'R26 Promo Test', author: 'Novulon' });
      a.store.project.name = 'R26 Promo Test'; a.store.project.author = 'Novulon';
      await new Promise(r => setTimeout(r, 1600));          // Magic starts Showcase after its camera swoop
      if (document.querySelector('#btn-showcase.on')) a.showcase(false);
      a.vp.stopCamera();
    } else {
      a.newScene(false, false, kind === 'solo3' ? 'solo' : 'couple');
      const p = a.store.project;
      p.name = kind === 'solo3' ? 'R26 Solo poses' : 'R26 Couple poses'; p.author = 'Novulon';
      p.category = 'TEASING'; p.tags = ['STANDING'];
      for (const s of p.sims) s.naked = 'NONE';
      for (const f of [30, 60]) { a.setFrame(f); a.keyAll(); }
      // different arms per key, so the poses differ
      for (const s of p.sims) s.keys.forEach((k, i) => {
        if (!k.pose || !k.pose.rot) return;
        for (const [bone, ax] of [['b__L_UpperArm__', 1], ['b__R_UpperArm__', -1]]) {
          const q = k.pose.rot[bone];
          if (!q) continue;
          const ang = i * 0.55 * ax, s2 = Math.sin(ang / 2), c2 = Math.cos(ang / 2);   // turn about z
          const [x, y, z, w] = q;
          k.pose.rot[bone] = [w * 0 + x * c2 + y * s2 - z * 0, y * c2 - x * s2 + w * 0, z * c2 + w * s2, w * c2 - z * s2];
        }
      });
      a.pipeline.overrides.clear();
      a.setFrame(0);
    }
    __r26.hideHome();
    a.showStep('share');
  }, kind);
  await H.sleep(900);
}

async function openPose(page) {
  await page.evaluate(() => document.querySelector('[data-share="posepack"]').click());
  await page.waitForSelector('.pp-dialog', { timeout: 30000 });
  await page.waitForFunction(() => document.querySelector('.pp-dialog .pp-lock') || document.querySelectorAll('.pp-dialog .pp-pic img').length === document.querySelectorAll('.pp-dialog .pp-pic').length, { timeout: 60000 }).catch(() => {});
  await H.sleep(500);
}

async function lastWrite(writes, route, since) {
  for (let i = 0; i < 200; i++) {
    const w = writes.filter(x => x.route === route && x.t >= since).pop();
    if (w) return w;
    await H.sleep(150);
  }
  return null;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  fs.mkdirSync(TMP, { recursive: true });
  let server = null;
  if (REUSE && await answering(PORT)) console.log(`using the server already on ${PORT}`);
  else {
    for (const port of [PORT, 8871, 8872, 8873, 8874, 8875]) {
      try { server = await startServer(port, { WICKED_EXPORTS_DIR: path.join(TMP, 'exports') }); PORT = port; break; }
      catch (e) { console.log(`port ${port}: ${e.message.split('\n')[0]}`); }
    }
    if (!server) { check('server', false, 'no port'); H.report(rows, 'R2-6 share UI'); process.exit(1); }
  }
  let B = null;
  try {
    // ================================================================ 1366 x 768
    B = await H.open(PORT, { w: 1366, h: 768, extraWrites: ['/api/posepack'] });
    const { page, writes, logs } = B;
    await ready(page);

    // ---- Share step
    await scene(page, 'couple3');
    const btns = await page.evaluate(() => [...document.querySelectorAll('[data-share]')].map(b => b.dataset.share + ':' + b.textContent.trim()));
    check('share step: promo kit + pose pack buttons', btns.length === 2, btns);
    await page.evaluate(() => document.querySelector('[data-share="posepack"]').scrollIntoView({ block: 'end' }));
    await H.sleep(300);
    await shot(page, 'share_step_1366.png');

    // ---- pose pack: one sim, 3 keys -> 3 poses
    await scene(page, 'solo3');
    await openPose(page);
    const tiles = await page.evaluate(() => [...document.querySelectorAll('.pp-dialog .pp-tile')].map(t => ({ frame: +t.dataset.frame, img: !!t.querySelector('img') })));
    check('pose pack: 3 keys -> 3 tiles with pictures', tiles.length === 3 && tiles.every(t => t.img), tiles);
    const okLine = await page.evaluate(() => (document.querySelector('.pp-dialog .pp-ok') || {}).innerText || '');
    check('pose pack: non-explicit scene passes the lock', /non-explicit/i.test(okLine) && /teens too/.test(okLine), okLine.slice(0, 120));
    await page.evaluate(() => { const i = document.querySelector('.pp-dialog .pp-side input.text'); i.value = 'R26 Solo poses'; i.dispatchEvent(new Event('input')); });
    let t0 = Date.now();
    await page.evaluate(() => [...document.querySelectorAll('.pp-dialog footer .btn')].pop().click());
    let w = await lastWrite(writes, '/api/posepack', t0);
    let req = w ? JSON.parse(w.body) : null;
    const iconOk = p => p.icon && p.icon.w === 64 && p.icon.h === 64 && Buffer.from(p.icon.rgba, 'base64').length === 64 * 64 * 4;
    check('pose pack: 3 keys give 3 poses', req && req.poses.length === 3 && req.poses.map(p => p.frame).join() === '0,30,60', req && req.poses.map(p => [p.label, p.frame]));
    check('pose pack: each pose has a 64x64 picture and one frame of tracks', req && req.poses.every(p => iconOk(p) && Object.keys(p.tracks).length > 60 && Object.values(p.tracks).every(t => (!t.r || t.r.length === 1) && (!t.t || t.t.length === 1))),
      req && req.poses.map(p => Object.keys(p.tracks).length));
    check('pose pack: no genital bones in the poses', req && req.poses.every(p => !Object.keys(p.tracks).some(n => /Penis|Vagina|Anus/.test(n))));
    check('pose pack: pack picture 64x64', req && iconOk({ icon: req.icon }));
    if (req) fs.writeFileSync(path.join(OUT, 'posepack_solo3.json'), JSON.stringify(req));
    await page.waitForFunction(() => /pose pack is ready/i.test(document.querySelector('#modal-root .modal:last-child h2')?.textContent || ''), { timeout: 15000 }).catch(() => {});
    await H.sleep(700);
    await shot(page, 'posepack_done_1366.png');
    check('pose pack: success card', await page.evaluate(() => !!document.querySelector('#modal-root .success-hero')));

    // ---- pose pack: a couple, 1 of 3 keys picked -> 2 poses (one per sim)
    await scene(page, 'couple3');
    await openPose(page);
    await shot(page, 'posepack_dialog_1366.png');
    await page.evaluate(() => { const cbs = [...document.querySelectorAll('.pp-dialog .pp-tile input[type=checkbox]')]; cbs.slice(1).forEach(c => c.click()); });
    await page.evaluate(() => { const i = document.querySelector('.pp-dialog .pp-side input.text'); i.value = 'R26 Couple poses'; });
    const countTxt = await page.evaluate(() => document.querySelector('.pp-dialog .pp-count').textContent);
    t0 = Date.now();
    await page.evaluate(() => [...document.querySelectorAll('.pp-dialog footer .btn')].pop().click());
    w = await lastWrite(writes, '/api/posepack', t0);
    req = w ? JSON.parse(w.body) : null;
    check('pose pack: couple, 1 key -> 2 poses (one per sim, one shared origin)', req && req.poses.length === 2 && req.poses[0].sim === 0 && req.poses[1].sim === 1 && /2 in Pose Player/.test(countTxt),
      { count: countTxt, poses: req && req.poses.map(p => p.label) });
    if (req) {
      // one shared origin: the two sims keep their places relative to each other (0.9 m apart, as on the stage)
      const pel = i => (req.poses[i].tracks.b__Pelvis__ || {}).t?.[0];
      const a = pel(0), b = pel(1);
      const gap = a && b ? Math.hypot(a[0] - b[0], a[2] - b[2]) : null;
      check('pose pack: couple keeps its spacing (shared origin)', gap !== null && gap > 0.5 && gap < 1.4, gap && gap.toFixed(3) + ' m');
      fs.writeFileSync(path.join(OUT, 'posepack_couple1.json'), JSON.stringify(req));
    }
    await page.evaluate(() => __r26.closeModals());

    // ---- explicit: refused with the message, nothing sent
    await scene(page, 'cowgirl');
    const nBefore = writes.filter(x => x.route === '/api/posepack').length;
    await openPose(page);
    const lock = await page.evaluate(() => ({ text: (document.querySelector('.pp-dialog .pp-lock') || {}).innerText || '',
      disabled: [...document.querySelectorAll('.pp-dialog footer .btn')].pop().disabled }));
    check('lock: explicit project refused with the one-line message', /non-explicit poses only/.test(lock.text) && /teens too/.test(lock.text) && /Vaginal/.test(lock.text) && /undressed/.test(lock.text) && !lock.text.includes('\n'),
      lock.text);
    check('lock: export button disabled', lock.disabled);
    check('lock: no pictures taken of a refused scene', await page.evaluate(() => !document.querySelector('.pp-dialog .pp-pic img') && !!document.querySelector('.pp-dialog .pp-locked-pic')));
    await shot(page, 'posepack_refused_1366.png');
    await page.evaluate(() => [...document.querySelectorAll('.pp-dialog footer .btn')].pop().click());
    await H.sleep(600);
    check('lock: nothing sent for the explicit project', writes.filter(x => x.route === '/api/posepack').length === nBefore);
    // each reason alone (the app's lock, same wording as the server's)
    const alone = await page.evaluate(async () => {
      const m = await import('/js/posepack.js');
      const base = { category: 'TEASING', tags: [], events: [], actors: [{ naked: 'NONE', keyed: [] }] };
      const c = x => m.lockReasons({ ...base, ...x });
      return { clean: c({}), nude: c({ actors: [{ naked: 'TOP' }] }), genital: c({ actors: [{ naked: 'NONE', keyed: ['b__Penis_Tip'] }] }),
        act: c({ category: 'ORALJOB' }), tag: c({ tags: ['DOGGY'] }), kiss: c({ tags: ['KISSING'] }), open: c({ actors: [{ naked: 'NONE', open: true }] }),
        moments: c({ events: ['CUM'] }), strapon: c({ actors: [{ naked: 'NONE', strapon: true }] }) };
    });
    check('lock: each reason on its own', !alone.clean.length && !alone.kiss.length && alone.nude[0] === 'undressed sims' && alone.genital[0] === 'genital or opening keys'
      && /Oral/.test(alone.act[0]) && /Doggy/.test(alone.tag[0]) && alone.open[0] === 'an opening that is open' && /moments/.test(alone.moments[0]) && alone.strapon[0] === 'a strap-on', alone);
    await page.evaluate(() => __r26.closeModals());

    // ---- promo kit on the 3 s cowgirl loop (dialog, default options: 3 angles, 480 px, a 10 s video)
    await page.evaluate(() => { app.setPlaying(false); app.setFrame(17); app.selectBoneByName(app.store.project.sims[0].id, 'b__L_Forearm__'); });
    const before = await page.evaluate(() => __r26.state());
    check('promo kit test starts with a part selected (gizmo on it)', before.gizmoOn === 'b__L_Forearm__', before.gizmoOn);
    await page.evaluate(() => document.querySelector('[data-share="promo"]').click());
    await page.waitForSelector('.pk-grid', { timeout: 20000 });
    await H.sleep(500);
    await shot(page, 'promo_dialog_1366.png');
    t0 = Date.now();
    await page.evaluate(() => [...document.querySelectorAll('#modal-root .modal:last-child footer .btn')].pop().click());
    await H.sleep(2500);
    await shot(page, 'promo_working_1366.png');
    w = await lastWrite(writes, '/api/promo_save', t0);
    for (let i = 0; !w && i < 4; i++) w = await lastWrite(writes, '/api/promo_save', t0);
    const took = ((Date.now() - t0) / 1000).toFixed(1);
    const kit = w ? JSON.parse(w.body) : null;
    check('promo kit: saved through /api/promo_save (intercepted)', !!kit, `${took} s`);
    await page.waitForFunction(() => /promo kit is ready/i.test(document.querySelector('#modal-root .modal:last-child h2')?.textContent || ''), { timeout: 20000 }).catch(() => {});
    await H.sleep(900);
    await shot(page, 'promo_done_1366.png');
    const after = await page.evaluate(() => __r26.state());
    const diff = Object.keys(before).filter(k => JSON.stringify(before[k]) !== JSON.stringify(after[k]));
    check('promo kit: everything put back (camera, frame, playing, helpers, look, loop)', !diff.length, diff.length ? { before, after } : 'same');
    if (kit) {
      const names = kit.files.map(f => f.name);
      const gifs = kit.files.filter(f => f.name.endsWith('.gif'));
      check('promo kit: 3 GIFs + thumbnail + video', gifs.length === 3 && names.some(n => n.endsWith('thumbnail.png')) && names.some(n => n.endsWith('.webm')), names);
      const proj = await page.evaluate(() => ({ length: app.store.project.length, fps: app.store.project.fps }));
      for (const g of gifs) {
        const bytes = Buffer.from(g.data.split(',').pop(), 'base64');
        fs.writeFileSync(path.join(OUT, g.name.replace(/^.* - /, 'promo_')), bytes);
        const d = decodeGif(bytes);
        const px = (a, b) => { let s = 0; for (let i = 0; i < a.length; i += 4) s += Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2]); return s / (a.length / 4 * 3); };
        const steps = [];
        for (let k = 0; k + 1 < d.frames.length; k++) steps.push(px(d.frames[k].rgba, d.frames[k + 1].rgba));
        const sorted = [...steps].sort((x, y) => x - y), med = sorted[Math.floor(sorted.length / 2)], mx = sorted[sorted.length - 1];
        const wrap = px(d.frames[d.frames.length - 1].rgba, d.frames[0].rgba);
        const secs = d.frames.reduce((s, f) => s + f.delay, 0) / 100;
        check(`GIF ${g.name.replace(/^.* - /, '')}: 480 px, < 5 MB, ${d.frames.length} frames, loops`, d.width === 480 && bytes.length < 5 * 1024 * 1024 && d.loop === 0 && d.frames.length >= 40,
          `${d.width}x${d.height} ${(bytes.length / 1048576).toFixed(2)} MB ${secs.toFixed(2)} s (loop ${(proj.length / proj.fps).toFixed(2)} s)`);
        check(`GIF ${g.name.replace(/^.* - /, '')}: seamless (last -> first is about one step)`, wrap > 0.15 * med && wrap <= Math.max(2.5 * med, med + 1.5) && wrap <= mx * 1.25,
          `last->first ${wrap.toFixed(2)}, median step ${med.toFixed(2)}, biggest step ${mx.toFixed(2)}`);
      }
      const th = kit.files.find(f => f.name.endsWith('thumbnail.png'));
      if (th) {
        const b = Buffer.from(th.data.split(',').pop(), 'base64');
        fs.writeFileSync(path.join(OUT, 'promo_thumbnail.png'), b);
        check('thumbnail: square PNG', b.readUInt32BE(16) === b.readUInt32BE(20) && b.readUInt32BE(16) >= 400, `${b.readUInt32BE(16)}x${b.readUInt32BE(20)}`);
      }
      const vid = kit.files.find(f => f.name.endsWith('.webm'));
      if (vid) { const b = Buffer.from(vid.data.split(',').pop(), 'base64'); fs.writeFileSync(path.join(OUT, 'promo_preview.webm'), b); check('video: webm recorded', b.length > 20000 && b.readUInt32BE(0) === 0x1A45DFA3, `${(b.length / 1048576).toFixed(2)} MB`); }
      fs.writeFileSync(path.join(OUT, 'promo_request_names.json'), JSON.stringify({ names, baked: !!kit.baked }));
      if (kit.baked) fs.writeFileSync(path.join(OUT, 'baked_cowgirl.json'), JSON.stringify(kit.baked));
    }
    // decodes in the page
    const dec = await page.evaluate(async () => {
      const out = [];
      for (const img of document.querySelectorAll('.pk-shelf img')) {
        const i = new Image(); i.src = img.src;
        try { await i.decode(); out.push([i.naturalWidth, i.naturalHeight]); } catch (e) { out.push(String(e)); }
      }
      let frames = null;
      if (window.ImageDecoder) {
        const blob = await fetch(document.querySelector('.pk-shelf img').src).then(r => r.blob());
        const d = new ImageDecoder({ data: blob.stream(), type: 'image/gif' });
        await d.tracks.ready; await d.completed; frames = d.tracks.selectedTrack.frameCount;
      }
      return { out, frames };
    });
    check('GIFs and thumbnail decode in the page (Image.decode)', dec.out.length === 4 && dec.out.every(x => Array.isArray(x) && x[0] > 0) && (dec.frames === null || dec.frames >= 40), dec);
    // the post text
    const text = await page.evaluate(async () => {
      const m = await import('/js/promo.js');
      const shown = document.querySelector('.pk-text')?.value || '';
      return { local: m.postText(app.store.project, null), shown };
    });
    check('post text: name, acts, places, sims, credits', ['"R26 Promo Test"', 'Vaginal', 'Cowgirl', 'Double bed', 'Sims: 2', 'Animation by Novulon', "Novulon's Wicked Animator", 'WickedWhims'].every(s => text.local.includes(s)) && text.shown === text.local,
      text.local.split('\n').slice(0, 6).join(' | '));
    fs.writeFileSync(path.join(OUT, 'post_text_app.txt'), text.local);
    await page.evaluate(() => __r26.closeModals());

    // ---- safe teaser: shoulders up and blur band (2 angles, no video), straight through makeKit - while playing
    await page.evaluate(() => app.setPlaying(true));
    const playingBefore = await page.evaluate(() => __r26.state());
    for (const teaser of ['shoulders', 'blur']) {
      const r = await page.evaluate(async teaser => {
        const m = await import('/js/promo.js');
        const kit = await m.makeKit(app, { angles: 2, width: 400, teaser, video: false });
        const b64 = async blob => btoa(String.fromCharCode(...new Uint8Array(await blob.arrayBuffer())));
        const toB64 = async blob => { const buf = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000)); return btoa(s); };
        return { gifs: await Promise.all(kit.gifs.map(async g => ({ name: g.name, size: g.bytes.length, data: await toB64(g.blob) }))), thumb: await toB64(kit.thumb.blob), busy: !!app._stageBusy };
      }, teaser);
      r.gifs.forEach((g, i) => fs.writeFileSync(path.join(OUT, `teaser_${teaser}_${i + 1}.gif`), Buffer.from(g.data, 'base64')));
      fs.writeFileSync(path.join(OUT, `teaser_${teaser}_thumb.png`), Buffer.from(r.thumb, 'base64'));
      check(`safe teaser "${teaser}": 2 GIFs under 5 MB`, r.gifs.length === 2 && r.gifs.every(g => g.size < 5 * 1024 * 1024) && !r.busy, r.gifs.map(g => (g.size / 1048576).toFixed(2) + ' MB'));
    }
    const after2 = await page.evaluate(() => __r26.state());
    const moved = Object.keys(after2).filter(k => k !== 'frame' && JSON.stringify(playingBefore[k]) !== JSON.stringify(after2[k]));
    check('safe teaser: everything put back (still playing)', !moved.length && after2.playing === true, moved.length ? { playingBefore, after2 } : 'same');
    await page.evaluate(() => app.setPlaying(false));

    // ---- the Record button (record.js, now captureVideo + recordVideo): films, saves, puts everything back
    await page.evaluate(() => { __r26.closeModals(); app.setPlaying(false); app.setFrame(11); app.selectBoneByName(app.store.project.sims[1].id, 'b__R_Hand__'); });
    const recBefore = await page.evaluate(() => __r26.state());
    t0 = Date.now();
    await page.evaluate(() => document.getElementById('btn-record').click());
    const recW = await lastWrite(writes, '/api/save_video', t0);
    await page.waitForFunction(() => /video is ready/i.test(document.querySelector('#modal-root .modal:last-child h2')?.textContent || ''), { timeout: 20000 }).catch(() => {});
    await H.sleep(700);
    const recAfter = await page.evaluate(() => __r26.state());
    const recDiff = Object.keys(recBefore).filter(k => JSON.stringify(recBefore[k]) !== JSON.stringify(recAfter[k]));
    const recCard = await page.evaluate(() => !!document.querySelector('#modal-root .modal:last-child video'));
    check('Record button: films, saves through /api/save_video, shows the video and puts everything back', !!recW && recCard && !recDiff.length,
      { saved: !!recW, secs: ((Date.now() - t0) / 1000).toFixed(1), card: recCard, changed: recDiff });
    await shot(page, 'record_done_1366.png');
    await page.evaluate(() => __r26.closeModals());

    const errs = logs.filter(l => (l.type === 'error' || l.type === 'pageerror') && !/favicon|Failed to load resource/.test(l.text));
    check('no page errors (1366)', !errs.length, errs.slice(0, 5));
    await B.browser.close(); B = null;

    // ================================================================ 1920 x 1080 (+ reduced motion)
    const info = await fetch(`http://127.0.0.1:${PORT}/api/posepack`).then(r => r.json()).catch(() => ({}));
    const tmpRoot = path.resolve(os.tmpdir()).toLowerCase();
    const real = !!(info.test_folder && info.exports && path.resolve(info.exports).toLowerCase().startsWith(tmpRoot));
    check('test server writes only into %TEMP%', real, info.exports);
    B = await H.open(PORT, { w: 1920, h: 1080, extraWrites: ['/api/posepack'], allow: real ? ['/api/posepack', '/api/promo_save'] : [] });
    await ready(B.page);
    await scene(B.page, 'couple3');
    await B.page.evaluate(() => document.querySelector('[data-share="posepack"]').scrollIntoView({ block: 'end' }));
    await H.sleep(300);
    await shot(B.page, 'share_step_1920.png');
    await openPose(B.page);
    await shot(B.page, 'posepack_dialog_1920.png');
    if (real) {
      // the real thing, into the test folder: the server builds and writes the pack
      await B.page.evaluate(() => [...document.querySelectorAll('.pp-dialog footer .btn')].pop().click());
      await B.page.waitForFunction(() => /pose pack is ready/i.test(document.querySelector('#modal-root .modal:last-child h2')?.textContent || ''), { timeout: 60000 }).catch(() => {});
      await H.sleep(900);
      await shot(B.page, 'posepack_done_1920.png');
      const pathShown = await B.page.evaluate(() => document.querySelector('#modal-root .modal:last-child .path')?.textContent || '');
      check('pose pack (real server, test folder): written into %TEMP%', pathShown.toLowerCase().startsWith(tmpRoot) && fs.existsSync(pathShown) && fs.statSync(pathShown).size > 10000,
        pathShown + (fs.existsSync(pathShown) ? ` ${fs.statSync(pathShown).size} bytes` : ' (missing)'));
      if (fs.existsSync(pathShown)) fs.writeFileSync(path.join(OUT, 'posepack_real_path.txt'), pathShown);
    }
    await B.page.evaluate(() => __r26.closeModals());
    await B.page.evaluate(() => document.querySelector('[data-share="promo"]').click());
    await B.page.waitForSelector('.pk-grid', { timeout: 20000 });
    await H.sleep(500);
    await shot(B.page, 'promo_dialog_1920.png');
    // make a small kit (2 angles, no video) to see the result card at this size
    await B.page.evaluate(() => {
      const m = document.querySelector('#modal-root .modal:last-child');
      m.querySelectorAll('.pk-seg')[0].querySelector('button').click();
      m.querySelector('.pk-opts input[type=checkbox]').click();
      [...m.querySelectorAll('footer .btn')].pop().click();
    });
    await B.page.waitForFunction(() => /promo kit is ready/i.test(document.querySelector('#modal-root .modal:last-child h2')?.textContent || ''), { timeout: 120000 }).catch(() => {});
    await H.sleep(900);
    await shot(B.page, 'promo_done_1920.png');
    if (real) {
      const folder = await B.page.evaluate(() => document.querySelector('#modal-root .modal:last-child .path')?.textContent || '');
      const files = folder && fs.existsSync(folder) ? fs.readdirSync(folder) : [];
      check('promo kit (real server, test folder): one folder in %TEMP% with the GIFs, thumbnail and post text',
        folder.toLowerCase().startsWith(tmpRoot) && files.filter(f => f.endsWith('.gif')).length === 2 && files.some(f => f.endsWith('thumbnail.png')) && files.includes('Post text.txt'), { folder, files });
      if (files.includes('Post text.txt')) fs.copyFileSync(path.join(folder, 'Post text.txt'), path.join(OUT, 'post_text_server.txt'));
    }
    const errs2 = B.logs.filter(l => (l.type === 'error' || l.type === 'pageerror') && !/favicon|Failed to load resource/.test(l.text));
    check('no page errors (1920)', !errs2.length, errs2.slice(0, 5));
    await B.browser.close(); B = null;

    B = await H.open(PORT, { w: 1366, h: 768, reducedMotion: true, extraWrites: ['/api/posepack'] });
    await ready(B.page);
    await scene(B.page, 'cowgirl');
    await openPose(B.page);
    await shot(B.page, 'posepack_refused_reduced.png');
    const anims = await B.page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running' && a.effect && a.effect.target && a.effect.target.closest && a.effect.target.closest('.pp-dialog, .pk-grid')).length);
    check('reduced motion: nothing of ours animates', anims === 0, anims);
    await B.browser.close(); B = null;
  } catch (e) {
    check('run', false, e.stack || String(e));
  } finally {
    if (B) await B.browser.close().catch(() => {});
    stopServer(server);
  }
  fs.writeFileSync(path.join(OUT, 'share_ui_report.json'), JSON.stringify(rows, null, 1));
  const ok = H.report(rows, 'R2-6 share UI');
  process.exit(ok ? 0 : 1);
})();
