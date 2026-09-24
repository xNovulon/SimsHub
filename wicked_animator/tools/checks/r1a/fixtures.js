// R1-A: make the test fixtures in %TEMP%\wa_fixtures (run once, before the engine edits; the files are then fixed).
//   - copies of the saved projects (made by the caller: saves\FitStudio\animator_projects\*.json, read-only)
//   - Magic-made projects: cowgirl (double bed), missionary, doggy, bj
//   - "multikey": missionary with extra keys that turn the jaw and tongue, varied eases and a face slider change
//   node tools/checks/r1a/fixtures.js --port 8841
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  fs.mkdirSync(L.FIX, { recursive: true });
  const server = await L.startServer(port);
  let browser;
  try {
    browser = await L.launch();
    const { page, logs } = await L.open(browser, port, { kind: 'app', orig: true });
    await page.waitForFunction('app.posePresets && app.posePresets.length > 0', { timeout: 120000 });
    const made = {};
    for (const [recipe, place] of [['cowgirl', 'double_bed'], ['missionary', 'floor'], ['doggy', 'single_bed'], ['bj', 'floor']]) {
      const p = await page.evaluate(async (recipe, place) => {
        const m = await import('/js/magic.js');
        app.store.setDirty(false);
        const ok = await m.makeMagic(app, { recipe, place, intensity: 0.6, seconds: 3, name: 'fixture ' + recipe, author: 'r1a' });
        app.setPlaying(false);
        app.showcase(false);
        return ok ? JSON.parse(JSON.stringify(app.store.project)) : null;
      }, recipe, place);
      if (!p) throw new Error('Magic failed for ' + recipe);
      fs.writeFileSync(path.join(L.FIX, `magic_${recipe}.json`), JSON.stringify(p));
      made[recipe] = p;
      console.log('made', recipe, p.sims.map(s => [s.frame, s.keys.length, (s.layers || []).map(l => l.type).join('+'), (s.sounds || []).length]));
    }
    // multikey: extra keys that move the jaw and the tongue (old projects keep them in key.pose)
    const mk = JSON.parse(JSON.stringify(made.missionary));
    mk.name = 'fixture multikey';
    const Q = (ax, deg) => { const h = deg * Math.PI / 360, s = Math.sin(h); return [ax[0] * s, ax[1] * s, ax[2] * s, Math.cos(h)]; };
    const mul = (a, b) => [
      a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
      a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
      a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
      a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2]];
    const eases = ['auto', 'easeIn', 'smooth', 'auto'];
    mk.sims.forEach((s, si) => {
      const k0 = s.keys[0];
      const jaw0 = k0.pose.rot.b__Jaw__, t1 = k0.pose.rot.b__Tounge__1, t2 = k0.pose.rot.b__Tounge__2;
      [[20, 12, 0], [45, 26, 8], [70, 6, -5]].forEach(([f, jawDeg, tongueDeg], i) => {
        const pose = JSON.parse(JSON.stringify(k0.pose));
        pose.rot.b__Jaw__ = mul(jaw0, Q([0, 0, -1], jawDeg + si * 3));
        if (t1) pose.rot.b__Tounge__1 = mul(t1, Q([0, 0, 1], tongueDeg));
        if (t2) pose.rot.b__Tounge__2 = mul(t2, Q([1, 0, 0], tongueDeg / 2));
        pose.rot.b__Head__ = mul(pose.rot.b__Head__, Q([0, 1, 0], 10 * (i - 1)));
        pose.rot.b__L_Hand__ = mul(pose.rot.b__L_Hand__, Q([1, 0, 0], 25 * (i + 1)));
        if (i === 1) pose.pos.b__Tounge__1 = [0.0343 + 0.001, -0.0165 + 0.02, 0];
        const key = { frame: f, ease: eases[i + 1], pose };
        if (i === 1) key.face = { open: 0.4, eyes: 0.6, inner: 0.5 };
        s.keys.push(key);
      });
      k0.ease = eases[0];
      s.keys.sort((a, b) => a.frame - b.frame);
    });
    fs.writeFileSync(path.join(L.FIX, 'magic_multikey.json'), JSON.stringify(mk));
    console.log('fixtures in', L.FIX, fs.readdirSync(L.FIX));
    if (logs.length) console.log('page logs:', logs.slice(0, 10));
  } finally {
    if (browser) await browser.close();
    L.stopServer(server);
  }
})().catch(e => { console.error(e); process.exit(1); });
