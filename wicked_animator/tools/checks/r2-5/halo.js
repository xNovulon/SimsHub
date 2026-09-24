// R2-5: the face-dot halos with the camera very close to the face - before and after hiding sprites and face dots
// from the ambient-occlusion pass (the dark squares were the halo quads drawn into GTAO's normal/depth buffers).
//   node tools/checks/r2-5/halo.js --port 8855 [--w 1366 --h 768]
const path = require('path');
const H = require('../lib/harness.js');
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
(async () => {
  const port = +arg('--port', 8855), w = +arg('--w', 1366), h = +arg('--h', 768);
  const OUT = path.join(H.ROOT, 'cache', 'checks', 'r2-5');
  const { browser, page, logs } = await H.open(port, { w, h, query: arg('--query', '') });
  await page.evaluate(d => { window.__DIST = d; }, +arg('--dist', 0.14));
  // --patch: the change requested for web/js/viewport.js, applied here in the page only (no file is edited)
  if (argv.includes('--patch')) await page.evaluate(() => {
    const vp = app.vp;
    if (!vp.ao || vp.ao.__noSprites) return;
    const hideOverlays = vp.ao.overrideVisibility.bind(vp.ao);
    vp.ao.overrideVisibility = () => {
      hideOverlays();
      vp.scene.traverse(o => {
        if (!o.visible) return;
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        if (o.isSprite || o.userData.noAO || mats.some(m => m && m.depthTest === false)) o.visible = false;
      });
    };
    vp.ao.__noSprites = true;
  });
  const setup = await page.evaluate(async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    for (let i = 0; i < 8; i++) { const b = document.querySelector('.backdrop:not(.leaving)'); if (!b) break; const x = [...b.querySelectorAll('button')].find(y => /Ignore|Close|Cancel/.test(y.textContent)); if (x) x.click(); await sleep(300); }
    document.getElementById('home').classList.add('hidden');
    for (let i = 0; i < 100 && !(app.posePresets && app.posePresets.length); i++) await sleep(100);
    const THREE = await import('three');
    const pr = app.posePresets.find(x => x.id === 'cowgirl') || app.posePresets.find(x => x.group === 'couple');
    app.applyPosePreset(pr);
    app.showStep('face');
    app.setTool('face');
    await sleep(1500);
    // the camera very close: 14 cm in front of the left eye, looking at it
    const sim = app.store.sim(), v = app.simViews.get(sim.id);
    const head = v.bone('b__Head__'), q = head.getWorldQuaternion(new THREE.Quaternion());
    const eye = v.bone('b__L_Eye__').getWorldPosition(new THREE.Vector3());
    const fwd = new THREE.Vector3(0, 1, 0).applyQuaternion(q), up = new THREE.Vector3(1, 0, 0).applyQuaternion(q);
    const at = eye.clone().addScaledVector(up, -0.02);
    const cam = at.clone().addScaledVector(fwd, 0.14);
    // the Face step's own close-up first, then the camera straight in toward the face (the controls' own call)
    await sleep(800);
    app.vp.stopCamera();
    const dir = app.vp.camera.position.clone().sub(at).normalize();
    app.vp.controls.lookFrom(at.clone().addScaledVector(dir, +window.__DIST || 0.14), at, app.vp.controls.roll || 0);
    await sleep(1200);
    return { ao: !!app.vp.ao, dots: app.interact.faceHandles.length, patched: !!(app.vp.ao && app.vp.ao.__noSprites), dist: +app.vp.camera.position.distanceTo(at).toFixed(3) };
  });
  console.log(JSON.stringify(setup));
  const clip = await page.evaluate(() => { const b = document.getElementById('viewport').getBoundingClientRect(); return { x: b.x, y: b.y, width: b.width, height: b.height }; });
  const tag = arg('--tag', setup.patched ? 'fixed' : 'now');
  await H.shot(page, path.join(OUT, `halo_close_${tag}_${w}.png`), { clip });
  // the same view with AO off: what the halos look like with nothing under them
  await page.evaluate(async () => { if (app.vp.ao) app.vp.ao.enabled = false; await new Promise(r => setTimeout(r, 600)); });
  await H.shot(page, path.join(OUT, `halo_close_noao_${w}.png`), { clip });
  console.log(logs.filter(l => l.type === 'pageerror').map(l => l.text));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
