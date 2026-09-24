// Diagnostic: Magic on a place, then the camera at 8 points around the sims at Showcase distance and height
// (2.9 m, pelvis + 0.55 m) - shows whether furniture ever hides the sims (the cutaway).
//   node tools/checks/r1c/diag_around.js --port 8851 [--place double_bed] [--recipe cowgirl] [--w 1366 --h 768]
const path = require('path');
const L = require('./lib.js');
const PORT = L.argPort(8851);
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const W = +arg('--w', 1366), H = +arg('--h', 768), PLACE = arg('--place', 'double_bed'), RECIPE = arg('--recipe', 'cowgirl');
(async () => {
  const server = await L.startServer(PORT);
  try {
    const { browser, page, logs } = await L.open(PORT, { w: W, h: H, gpu: true, beforeLoad: pg => pg.evaluateOnNewDocument(() => { try { localStorage.setItem('fsa.tourDone', 'true'); } catch { } }) });
    await page.waitForFunction(() => window.app && window.app.posePresets && window.app.posePresets.length, { timeout: 60000 });
    await page.evaluate(() => document.getElementById('home').classList.add('hidden'));
    await page.evaluate(async (place, recipe) => { const m = await import('/js/magic.js'); await m.makeMagic(window.app, { recipe, place, intensity: 0.5, seconds: 3 }); }, PLACE, RECIPE);
    await L.sleep(300);
    await page.evaluate(() => { const a = window.app; clearTimeout(a._magicShow); a.showcase(false); a.vp.stopCamera(); a.setPlaying(false); a.setFrame(0); });
    for (let i = 0; i < 8; i++) {
      await page.evaluate(i => {
        const a = window.app, THREE = a.vp.camera.position.constructor;
        const c = new THREE(); let n = 0;
        for (const [, v] of a.simViews) { v.group.updateMatrixWorld(true); c.add(v.worldPos('b__Pelvis__')); n++; }
        c.multiplyScalar(1 / n);
        const ang = i * Math.PI / 4;
        a.vp.controls.lookFrom(new THREE(c.x + Math.sin(ang) * 2.9, c.y + 0.55, c.z + Math.cos(ang) * 2.9), c);
      }, i);
      await L.sleep(250);
      await L.shot(page, path.join(L.OUT, 'diag', `around_${PLACE}_${i}.png`));
    }
    console.log(logs.filter(x => /error/i.test(x)).slice(0, 10).join('\n'));
    await browser.close();
  } finally { L.stopServer(server); }
})().catch(e => { console.error(e); process.exit(2); });
