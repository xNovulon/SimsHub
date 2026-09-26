// Capture studio: the whole video frame must show on the stage (letterboxed, nothing cut) for any shape - portrait,
// landscape, square - and the pose overlay's box math must match where the picture actually renders (so the
// skeleton lands on the people, not floating off to one side). Regression check for the "tall video shows only its
// cropped, zoomed-in top" bug (a `.cap-media` grid track with no definite size - web/css/capture.css).
//
//   node tools/checks/capture/display.js --port 8960
//
// Makes its own quadrant test videos with ffmpeg into cache/checks/capture/ at run time (nothing binary in git) and
// skips cleanly, with a clear line, when ffmpeg is not on PATH. The pose half also needs the owner's installed
// MediaPipe copy (%USERPROFILE%/Tools/sims4_animator/web/vendor/mediapipe - not in the repo) and skips the same way
// when it is missing. Starts its own server on the port (never 8765/8766/8777); nothing is written to the game.
const path = require('path');
const fs = require('fs');
const os = require('os');
const http = require('http');
const { spawn, spawnSync } = require('child_process');
const P = require('../lib/pw.js');
const H = require('../lib/harness.js');

const ROOT = H.ROOT;
const OUT = path.join(ROOT, 'cache', 'checks', 'capture');
const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
let port = +arg('--port', 8960);
const rows = [];
const row = (name, ok, detail) => { rows.push({ name, ok: !!ok, detail }); return ok; };
const sleep = ms => new Promise(r => setTimeout(r, ms));

const VENDOR = path.join(os.homedir(), 'Tools', 'sims4_animator', 'web', 'vendor', 'mediapipe');
const hasFfmpeg = () => { try { return spawnSync('ffmpeg', ['-version']).status === 0; } catch { return false; } };
const hasMediapipe = () => fs.existsSync(path.join(VENDOR, 'vision_bundle.mjs')) && fs.existsSync(path.join(VENDOR, 'wasm')) && fs.existsSync(path.join(VENDOR, 'models'));

// ---------------------------------------------------------------- test videos (quadrant colours, made with ffmpeg)
function makeQuad(file, w, h) {
  const args = ['-y', '-f', 'lavfi', '-i', `color=c=black:s=${w}x${h}:d=2:r=12`, '-vf',
    `drawbox=x=0:y=0:w=${w / 2}:h=${h / 2}:color=red@1:t=fill,` +
    `drawbox=x=${w / 2}:y=0:w=${w / 2}:h=${h / 2}:color=lime@1:t=fill,` +
    `drawbox=x=0:y=${h / 2}:w=${w / 2}:h=${h / 2}:color=blue@1:t=fill,` +
    `drawbox=x=${w / 2}:y=${h / 2}:w=${w / 2}:h=${h / 2}:color=yellow@1:t=fill,` +
    `drawbox=x=0:y=0:w=${w}:h=${h}:color=white:t=8`,
    '-pix_fmt', 'yuv420p', file];
  const r = spawnSync('ffmpeg', args, { cwd: OUT });
  if (r.status !== 0) throw new Error('ffmpeg failed for ' + file + ': ' + (r.stderr || '').toString().slice(-800));
}

// ---------------------------------------------------------------- server (never 8765/8766/8777)
function status(p) {
  return new Promise(res => {
    const r = http.get({ host: '127.0.0.1', port: p, path: '/api/status', timeout: 1500 }, resp => {
      let b = ''; resp.on('data', c => { b += c; }); resp.on('end', () => { try { res(JSON.parse(b)); } catch { res(null); } });
    });
    r.on('error', () => res(null)); r.on('timeout', () => { r.destroy(); res(null); });
  });
}
async function ensureServer() {
  if (H.REFUSED.has(port)) throw new Error('refused port ' + port);
  if (await status(port)) return null;
  const saves = fs.mkdtempSync(path.join(os.tmpdir(), 'wa_capture_check_'));
  const env = { ...process.env, ANIMATOR_PORT: String(port), ANIMATOR_SAVES: saves, PYTHONUNBUFFERED: '1' };
  fs.mkdirSync(path.join(ROOT, 'cache', 'checks', '_servers'), { recursive: true });
  const log = fs.openSync(path.join(ROOT, 'cache', 'checks', '_servers', `port${port}.log`), 'a');
  const p = spawn('python', [path.join(ROOT, 'backend', 'server.py')], { cwd: ROOT, env, stdio: ['ignore', log, log], windowsHide: true });
  for (let i = 0; i < 300; i++) { const s = await status(port); if (s && s.pid === p.pid) return p; if (p.exitCode !== null) break; await sleep(400); }
  p.kill();
  throw new Error('the server did not start on ' + port);
}

// ---------------------------------------------------------------- open the studio on a video, same-origin (the
// app's CSP is connect-src 'self'; a plain file input gives a 0-byte File under this Playwright build), and
// measure where the video element and its object-fit:contain content actually land on the stage
async function measureStage(page, file, label, opts = {}) {
  await page.route('**/__cap_check_asset__/**', route => {
    const name = decodeURIComponent(route.request().url().split('/__cap_check_asset__/')[1]);
    const f = path.join(OUT, name);
    if (!fs.existsSync(f)) return route.fulfill({ status: 404, body: 'nf' });
    return route.fulfill({ status: 200, contentType: 'video/mp4', body: fs.readFileSync(f) });
  }).catch(() => {}); // already routed for a later call
  await page.evaluate(() => { const s = document.querySelector('.cap-backdrop'); if (s) s.remove(); });
  await page.evaluate(() => { if (!window.app.store.project.sims.length) window.app.newScene(false, false, 'solo'); });
  await page.evaluate(async () => {
    window.__cap = await import('/js/capture.js');
    window.__cap.openCaptureStudio(window.app, { source: 'video', simId: window.app.store.selected.sim });
  });
  await page.waitForSelector('.cap-studio', { timeout: 10000 });
  await page.evaluate(async (u) => {
    const resp = await fetch(u);
    const blob = await resp.blob();
    const f = new File([blob], u.split('/').pop(), { type: 'video/mp4' });
    const dt = new DataTransfer();
    dt.items.add(f);
    const input = document.querySelector('.cap-drop input[type=file]');
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }, '/__cap_check_asset__/' + path.basename(file));
  await page.waitForFunction(() => document.querySelector('.cap-media video'), { timeout: 15000 });
  await page.waitForTimeout(500);
  if (opts.play) { await page.evaluate(() => document.querySelector('.cap-media video').play().catch(() => {})); await page.waitForTimeout(400); }
  const m = await page.evaluate(() => {
    const stage = document.querySelector('.cap-stage').getBoundingClientRect();
    const v = document.querySelector('.cap-media video');
    const vr = v.getBoundingClientRect();
    const st = (window.__cap && window.__cap.studioOpen && window.__cap.studioOpen()) || null;
    return {
      stage: { w: stage.width, h: stage.height },
      video: { x: vr.x - stage.x, y: vr.y - stage.y, w: vr.width, h: vr.height },
      native: { w: v.videoWidth, h: v.videoHeight },
      box: st && st.box ? { ...st.box } : null,
    };
  });
  // sample pixels at the four quadrant centres, in the picture's *actual* letterboxed rect (object-fit:contain
  // math applied to the video ELEMENT's own box - not the element's box itself, which the CSS always stretches
  // to fill the stage): a bugged layout crops/distorts the picture inside that box, so the wrong colour shows up.
  const s = Math.min(m.video.w / m.native.w, m.video.h / m.native.h);
  const picW = m.native.w * s, picH = m.native.h * s;
  const picX = m.video.x + (m.video.w - picW) / 2, picY = m.video.y + (m.video.h - picH) / 2;
  const pt = (fx, fy) => ({ x: Math.round(picX + picW * fx), y: Math.round(picY + picH * fy) });
  const samples = { TL: pt(0.25, 0.25), TR: pt(0.75, 0.25), BL: pt(0.25, 0.75), BR: pt(0.75, 0.75) };
  const pixels = await page.evaluate(async (pts) => {
    const v = document.querySelector('.cap-media video');
    const stageEl = document.querySelector('.cap-stage');
    const c = document.createElement('canvas'); c.width = stageEl.clientWidth; c.height = stageEl.clientHeight;
    const g = c.getContext('2d');
    // draw the video exactly as the CSS does (object-fit:contain into the stage box) so the sample matches what a
    // person actually sees, whatever the CSS bug does underneath
    const vr = document.querySelector('.cap-media video').getBoundingClientRect(), sr = stageEl.getBoundingClientRect();
    g.drawImage(v, vr.left - sr.left, vr.top - sr.top, vr.width, vr.height);
    const out = {};
    for (const k of Object.keys(pts)) { const { x, y } = pts[k]; const d = g.getImageData(Math.max(0, Math.min(c.width - 1, x)), Math.max(0, Math.min(c.height - 1, y)), 1, 1).data; out[k] = [d[0], d[1], d[2]]; }
    return out;
  }, samples);
  await fs.promises.mkdir(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, `stage_${label}.png`) });
  return { ...m, pixels };
}

const near = (c, [r, g, b], tol = 60) => Math.abs(c[0] - r) < tol && Math.abs(c[1] - g) < tol && Math.abs(c[2] - b) < tol;
function checkQuadrantColours(m, label) {
  const p = m.pixels;
  const ok = near(p.TL, [255, 0, 0]) && near(p.TR, [0, 255, 0]) && near(p.BL, [0, 0, 255]) && near(p.BR, [255, 255, 0]);
  row(`${label}: whole frame shows, letterboxed (no crop, no squash)`, ok, { pixels: p, videoBox: m.video, native: m.native, stage: m.stage });
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  if (!hasFfmpeg()) { console.log('SKIP: ffmpeg is not on PATH - cannot make test videos. Install ffmpeg and re-run.'); process.exit(0); }

  makeQuad(path.join(OUT, 'portrait_quad.mp4'), 1080, 1920);
  makeQuad(path.join(OUT, 'landscape_quad.mp4'), 1920, 1080);
  makeQuad(path.join(OUT, 'square_quad.mp4'), 1000, 1000);

  let server = null;
  try { server = await ensureServer(); } catch (e) { console.error(e.message); process.exit(2); }
  try {
    const { browser, page, logs } = await P.open(port, { w: 1400, h: 900 });
    await page.route('**/api/capture_status', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ installed: true, missing: [], bytes_needed: 0, busy: false }) }));
    if (hasMediapipe()) {
      await page.route('**/vendor/mediapipe/**', route => {
        const u = new URL(route.request().url());
        const rel = u.pathname.split('/vendor/mediapipe/')[1];
        const f = path.join(VENDOR, rel);
        if (!fs.existsSync(f)) return route.fulfill({ status: 404, body: 'nf' });
        const ext = path.extname(f);
        const ct = ext === '.mjs' || ext === '.js' ? 'text/javascript' : ext === '.wasm' ? 'application/wasm' : ext === '.json' ? 'application/json' : 'application/octet-stream';
        return route.fulfill({ status: 200, contentType: ct, body: fs.readFileSync(f) });
      });
    }
    await page.keyboard.press('Escape').catch(() => {});

    const portrait = await measureStage(page, path.join(OUT, 'portrait_quad.mp4'), 'portrait');
    checkQuadrantColours(portrait, 'Portrait video (1080x1920)');
    row('Portrait video: <video> box fills the stage (CSS gives the grid track a definite size)',
      Math.abs(portrait.video.w - portrait.stage.w) < 8 && Math.abs(portrait.video.h - portrait.stage.h) < 8,
      { video: portrait.video, stage: portrait.stage });

    const landscape = await measureStage(page, path.join(OUT, 'landscape_quad.mp4'), 'landscape');
    checkQuadrantColours(landscape, 'Landscape video (1920x1080, unchanged behaviour)');

    const square = await measureStage(page, path.join(OUT, 'square_quad.mp4'), 'square');
    checkQuadrantColours(square, 'Square video (1000x1000)');

    // while it plays (a video mid-playback re-lays-out the same way; catches a fix that only helps the first frame)
    const playing = await measureStage(page, path.join(OUT, 'portrait_quad.mp4'), 'portrait_playing', { play: true });
    checkQuadrantColours(playing, 'Portrait video, mid-playback');

    // the pose overlay's box math (_fitOverlay/_drawSkeleton) must land on the same rect the picture is actually
    // drawn in - the box is read straight from the live studio (window.__cap.studioOpen())
    const b = portrait.box, s = Math.min(portrait.video.w / portrait.native.w, portrait.video.h / portrait.native.h);
    const expected = { x: (portrait.video.w - portrait.native.w * s) / 2, y: (portrait.video.h - portrait.native.h * s) / 2, w: portrait.native.w * s, h: portrait.native.h * s };
    const tol = 8; // a few px of slack for layout/DPR rounding between the two measurements
    const boxOk = b && Math.abs(b.x - expected.x) < tol && Math.abs(b.y - expected.y) < tol && Math.abs(b.w - expected.w) < tol && Math.abs(b.h - expected.h) < tol;
    row('Portrait video: skeleton overlay box matches where the picture actually renders', boxOk, { box: b, expected });

    // ---------------------------------------------------------------- the detector's input (needs real MediaPipe)
    if (!hasMediapipe()) {
      console.log(`SKIP: MediaPipe is not installed at ${VENDOR} - the detector-input check needs it. Everything else above still ran.`);
    } else {
      const bodyFile = path.join(OUT, 'body_portrait.mp4');
      // record the running app's own 3D sim into a portrait mp4 (a real body, so real pose landmarks come back) -
      // a second tab in the same browser/context, on the same server, so no extra port is needed
      const bctx = await page.context().newPage();
      try {
        await bctx.goto(page.url().replace(/\?.*$/, '') + '?slot=test2', { waitUntil: 'domcontentloaded' });
        await bctx.waitForSelector('#loading.done', { state: 'attached', timeout: 30000 }).catch(() => {});
        await bctx.evaluate(() => { if (!window.app.store.project.sims.length) window.app.newScene(false, false, 'solo'); });
        await bctx.keyboard.press('Escape').catch(() => {}); // closes the Home screen (same as a person opening the app)
        await bctx.waitForTimeout(300);
        // belt and braces: Escape's view-transition can race the checks below, so make sure Home is really gone
        await bctx.evaluate(() => { const home = document.getElementById('home'); if (home && !home.classList.contains('hidden')) home.classList.add('hidden'); });
        await bctx.waitForTimeout(200);
        await bctx.setViewportSize({ width: 1400, height: 900 });
        await bctx.waitForTimeout(500);
        // frame the sim full-length so the body fills most of the frame, then take a portrait-shaped crop out of
        // the middle of the (landscape) 3D viewport for the test video
        await bctx.evaluate(() => { if (!window.app.store.selected.sim) window.app.store.selected.sim = window.app.store.project.sims[0].id; window.app.frameSelection(); });
        await bctx.waitForTimeout(500);
        const vp = await bctx.evaluate(() => { const r = document.getElementById('viewport').getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; });
        const even = n => Math.max(2, Math.floor(n / 2) * 2);
        const portraitW = even(Math.min(vp.width, vp.height * 0.6));
        const h = even(vp.height);
        const clip = { x: Math.round(vp.x + (vp.width - portraitW) / 2), y: Math.round(vp.y), width: portraitW, height: h };
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wa_capture_frames_'));
        for (let i = 0; i < 12; i++) {
          const f = path.join(dir, `f${String(i).padStart(3, '0')}.png`);
          await bctx.screenshot({ path: f, clip });
          await sleep(60);
        }
        const r = spawnSync('ffmpeg', ['-y', '-framerate', '12', '-i', path.join(dir, 'f%03d.png'), '-pix_fmt', 'yuv420p', bodyFile]);
        if (r.status !== 0) throw new Error('ffmpeg (frames->mp4) failed: ' + (r.stderr || '').toString().slice(-800));
        fs.rmSync(dir, { recursive: true, force: true });
      } finally { await bctx.close(); }

      await measureStage(page, bodyFile, 'body_portrait'); // screenshot only - no flat quadrants to sample here
      const pose = await page.evaluate(async () => {
        const v = document.querySelector('.cap-media video');
        v.currentTime = Math.min(0.4, v.duration / 2);
        await new Promise(res => { v.addEventListener('seeked', res, { once: true }); setTimeout(res, 1500); });
        const { createTracker, detectFrame } = await import('/js/capture/tracker.js');
        const tr = await createTracker({ body: true, hands: false, face: false, quality: 'best', mode: 'VIDEO', people: 1 });
        const fr = detectFrame(tr, v, v.currentTime * 1000, { W: v.videoWidth, H: v.videoHeight });
        tr.close();
        if (!fr || !fr.pose) return { ok: false };
        const img = fr.pose.img;
        return { ok: true, nose: { x: img[0], y: img[1] }, hipL: { x: img[23 * 3], y: img[23 * 3 + 1] }, hipR: { x: img[24 * 3], y: img[24 * 3 + 1] } };
      });
      // the whole frame is read (nothing cropped/squashed): a standing figure has its nose well above its hips,
      // and both land inside the visible 0..1 image, not off in a corner (the "skeleton floating in the sky" bug)
      const poseOk = pose.ok && pose.nose.y >= 0 && pose.nose.y <= 1 && pose.hipL.y >= 0 && pose.hipL.y <= 1
        && pose.nose.y < pose.hipL.y - 0.1 && Math.abs(pose.nose.x - 0.5) < 0.35;
      row('Portrait video with a body: pose landmarks land on the person (nose above hips, both in frame)', poseOk, pose);
    }

    if (logs.some(l => l.type === 'pageerror')) row('no page errors', false, logs.filter(l => l.type === 'pageerror').slice(0, 5));
    await browser.close();
  } finally {
    if (server) server.kill();
  }

  fs.writeFileSync(path.join(OUT, 'display_check.json'), JSON.stringify({ port, rows }, null, 1));
  const ok = H.report(rows, `Capture display checks (port ${port})`);
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error('FAIL', e && e.stack || e); process.exit(2); });
