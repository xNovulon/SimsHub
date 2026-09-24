// The live stage behind Home (R1-C stretch goal): pictures of Home over the demo couple (a new animation) and over a
// Magic animation playing in slow motion, and that everything is put back when Home closes.
//   node tools/checks/r1c/homestage.js --port 8851
const path = require('path');
const L = require('./lib.js');
const PORT = L.argPort(8851);
(async () => {
  const server = await L.startServer(PORT);
  const T = L.table();
  try {
    const { browser, page, logs } = await L.open(PORT, { w: 1366, h: 768, gpu: true, query: 'homestage=1',
      beforeLoad: pg => pg.evaluateOnNewDocument(() => { try { localStorage.setItem('fsa.tourDone', 'true'); } catch { } }) });
    await page.waitForFunction(() => window.app && window.app.posePresets && window.app.posePresets.length, { timeout: 60000 });
    // Home at start: a new, empty animation -> the demo couple
    await page.evaluate(() => { window.app.showStep('scene'); });
    await page.evaluate(async () => { const h = await import('/js/home.js'); await h.showHome(window.app); });
    await L.sleep(2500);
    const a = await page.evaluate(() => ({ live: document.body.classList.contains('home-live'), look: window.app.vp.stage.look, w: document.getElementById('viewport-wrap').getBoundingClientRect().width }));
    await L.shot(page, path.join(L.OUT, 'after', 'home_live_demo_1366.png'));
    T.check('Home: the live stage plays behind the glass (demo couple, Candle look)', a.live && a.look === 'candle' && a.w >= 1360, JSON.stringify(a));
    // Magic, then Home: the animation plays slowly behind Home, silently
    await page.evaluate(async () => {
      const h = await import('/js/home.js'); h.hideHome(window.app);
      const m = await import('/js/magic.js');
      await m.makeMagic(window.app, { recipe: 'cowgirl', place: 'double_bed', intensity: 0.5, seconds: 3 });
      clearTimeout(window.app._magicShow); window.app.showcase(false); window.app.setPlaying(false); window.app.setFrame(12);
    });
    await L.sleep(800);
    // Magic's camera swoop (about 1.1 s) must have landed before the camera is read
    await page.waitForFunction(() => !window.app.vp._camStep, { timeout: 15000 }).catch(() => {});
    await L.sleep(200);
    const before = await page.evaluate(() => ({ frame: window.app.store.frame, playing: window.app.playing, speed: window.app.speed, look: window.app.vp.stage.look, cam: window.app.vp.camera.position.toArray().map(x => +x.toFixed(3)) }));
    await page.evaluate(async () => { const h = await import('/js/home.js'); await h.showHome(window.app); });
    await L.sleep(2500);
    const during = await page.evaluate(() => ({ live: document.body.classList.contains('home-live'), playing: window.app.playing, speed: window.app.speed, look: window.app.vp.stage.look }));
    await L.shot(page, path.join(L.OUT, 'after', 'home_live_magic_1366.png'));
    T.check('Home: your animation plays behind it in slow motion (no sound)', during.live && during.playing && during.speed < 0.5 && during.look === 'candle', JSON.stringify(during));
    await page.evaluate(async () => { const h = await import('/js/home.js'); h.hideHome(window.app); });
    await L.sleep(500);
    const after = await page.evaluate(() => ({ live: document.body.classList.contains('home-live'), frame: window.app.store.frame, playing: window.app.playing, speed: window.app.speed, look: window.app.vp.stage.look, cam: window.app.vp.camera.position.toArray().map(x => +x.toFixed(3)), w: document.getElementById('viewport-wrap').getBoundingClientRect().width }));
    T.check('Home closed: frame, playback, speed, look and camera are back', !after.live && after.frame === before.frame && after.playing === before.playing && after.speed === before.speed && after.look === before.look
      && after.cam.every((x, i) => Math.abs(x - before.cam[i]) < 0.01) && after.w < 1000, JSON.stringify({ before, after }));
    T.check('no page errors', !logs.some(l => /pageerror|\[error\].*polish/.test(l)), logs.filter(l => /pageerror|polish/.test(l)).join(' | ').slice(0, 300));
    await browser.close();
  } finally { L.stopServer(server); }
  process.exit(T.print('Home over the live stage') ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
