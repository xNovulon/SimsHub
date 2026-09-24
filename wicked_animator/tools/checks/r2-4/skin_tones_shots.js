// Screenshots for tools/checks/r2-4/skin_tones.py: Tray sims whose skin tone the app could not find before, in the
// app at 1366x768 - the whole body from the front and a closer look at the face and chest.
//   node tools/checks/r2-4/skin_tones_shots.js <port> <sims.json>
// sims.json: [{tray, index, name, tag}]. Prints one JSON line: [{tag, name, tone, frame, skinReady, textured, files}].
const fs = require('fs');
const H = require('../lib/harness.js');

(async () => {
  const port = +(process.argv[2] || 8883);
  const sims = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
  const { browser, page, logs } = await H.open(port, { w: 1366, h: 768 });
  const out = [];
  try {
    await page.evaluate(async () => { (await import('/js/home.js')).hideHome(window.app); });
    for (const s of sims) {
      const info = await page.evaluate(async ({ tray, index, name }) => {
        const app = window.app;
        app.newScene(false, false, 'solo');
        await new Promise(r => setTimeout(r, 500));
        await app.addTraySim(tray, index, name);
        const p = app.store.project;
        app.removeSim(p.sims[0].id);
        const sim = p.sims[p.sims.length - 1];
        app.setPlaying(false); app.setFrame(0);
        const ready = await Promise.race([app.skinReady(sim.frame, sim.tone || ''), new Promise(r => setTimeout(() => r('timeout'), 120000))]);
        const v = app.simViews.get(sim.id);
        return { id: sim.id, tone: sim.tone, frame: sim.frame, skinReady: ready, textured: !!(v && v.material && v.material.map) };
      }, s);
      const files = [];
      // the whole body, from the front
      await page.evaluate(() => { const app = window.app; app.frameSims({ fromFront: true }); });
      await H.sleep(1800);
      files.push(await H.shot(page, `cache/checks/r2-4/skin_tone_${s.tag}_body.png`));
      // face and chest, a little from the side
      await page.evaluate(async id => {
        const THREE = await import('three');
        const app = window.app, v = app.simViews.get(id);
        v.group.updateMatrixWorld(true);
        const at = v.worldPos('b__Head__').add(new THREE.Vector3(0, -0.22, 0));
        app.vp.frame(at, 0.42, new THREE.Vector3(0.35, 0.1, 1));
      }, info.id);
      await H.sleep(1800);
      files.push(await H.shot(page, `cache/checks/r2-4/skin_tone_${s.tag}_close.png`));
      out.push({ tag: s.tag, name: s.name, ...info, files });
    }
  } finally {
    const errors = logs.filter(l => l.type === 'pageerror' || (l.type === 'error' && !/Failed to load resource/.test(l.text)));
    process.stdout.write(JSON.stringify({ sims: out, errors: errors.slice(0, 10) }) + '\n');
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
