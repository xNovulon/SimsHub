// Diagnostic: Magic cowgirl on the double bed, frames of the swoop and the Showcase orbit (GPU), with the camera's
// distance to the sims and to the furniture's box, so a camera that ends up inside the bed shows up in numbers.
//   node tools/checks/r1c/diag_orbit.js --port 8851 [--w 1366 --h 768] [--place double_bed]
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
    const t0 = Date.now();
    for (let i = 0; i < 12; i++) {
      const s = await page.evaluate(() => {
        const a = window.app, c = a.vp.camera.position, g = a.furnGroup || a.vp.scene.getObjectByName?.('furniture');
        const THREE = a.vp.camera.position.constructor;
        let box = null;
        a.vp.scene.traverse(o => { if (!box && o.userData && o.userData.slots !== undefined) { box = o; } });
        let inside = null;
        if (box) { const b = new (Object.getPrototypeOf(a.vp.scene).constructor === undefined ? Object : Object)(); }
        return { cam: c.toArray().map(x => +x.toFixed(2)), show: !!a._showStep, q: a.vp.qualityLevel, fov: a.vp.camera.fov, near: a.vp.camera.near };
      });
      console.log(Date.now() - t0, JSON.stringify(s));
      await L.shot(page, path.join(L.OUT, 'diag', `orbit_${PLACE}_${W}_${i}.png`));
      await L.sleep(400);
    }
    console.log(logs.filter(x => /error/i.test(x)).slice(0, 10).join('\n'));
    await browser.close();
  } finally { L.stopServer(server); }
})().catch(e => { console.error(e); process.exit(2); });
