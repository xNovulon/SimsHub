// Diagnostic: which body part goes lowest while a Magic animation plays (the ride / thrust dips).
//   node tools/checks/r1c/diag_dip.js --port 8843 [recipe] [place]
const L = require('./lib.js');
const PORT = L.argPort();
const args = process.argv.slice(2).filter(a => !a.startsWith('--') && !/^\d+$/.test(a));
const recipe = args[0] || 'cowgirl', place = args[1] || 'floor';
(async () => {
  const server = await L.startServer(PORT);
  try {
    const { browser, page } = await L.open(PORT, { beforeLoad: pg => pg.evaluateOnNewDocument(() => { try { localStorage.setItem('fsa.tourDone', 'true'); } catch { } }) });
    await page.waitForFunction(() => window.app && window.app.posePresets && window.app.posePresets.length, { timeout: 60000 });
    const r = await page.evaluate(async (recipe, place) => {
      const THREE = await import('three');
      const app = window.app, magic = await import('/js/magic.js');
      await magic.makeMagic(app, { recipe, place, intensity: 0.5, seconds: 3 });
      app.setPlaying(false); app.showcase(false);
      const v3 = new THREE.Vector3(), out = [];
      const Lf = app.store.project.length;
      for (let f = 0; f < Lf; f += 3) {
        app.pipeline.apply(f, { physics: true, overrides: false });
        let best = { y: Infinity };
        for (const s of app.store.project.sims) {
          const v = app.simViews.get(s.id);
          v.group.updateMatrixWorld(true);
          for (const mesh of v.meshes) {
            if (!mesh.visible) continue;
            const n = mesh.geometry.attributes.position.count, si = mesh.geometry.attributes.skinIndex, sw = mesh.geometry.attributes.skinWeight;
            for (let i = 0; i < n; i += 2) {
              mesh.getVertexPosition(i, v3);
              if (v3.y < best.y) {
                let bi = 0, bw = -1; for (let k = 0; k < 4; k++) if (sw.getComponent(i, k) > bw) { bw = sw.getComponent(i, k); bi = si.getComponent(i, k); }
                best = { y: +v3.y.toFixed(4), sim: s.label, mesh: mesh.name, bone: v.bones[bi].name, x: +v3.x.toFixed(3), z: +v3.z.toFixed(3) };
              }
            }
          }
        }
        out.push({ f, ...best });
      }
      return { layers: app.store.project.sims.map(s => [s.label, (s.layers || []).map(l => l.type + ' ' + JSON.stringify(l.params))]), out };
    }, recipe, place);
    console.log(JSON.stringify(r.layers));
    for (const o of r.out) console.log(o.f, o.y, o.sim, o.mesh, o.bone, o.x, o.z);
    await browser.close();
  } finally { L.stopServer(server); }
})().catch(e => { console.error(e); process.exit(1); });
