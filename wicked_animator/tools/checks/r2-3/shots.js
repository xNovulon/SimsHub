// R2-3 screenshot tour at 1366x768 and 1920x1080: the Place tool's spots, sitting on the sofa, see-through with
// bones, the clipping card and its Send warning, the Body step (hair, other bodies, the trial pill), the Motion step
// (Look at, Follow-through), a Tray sim's hair up close and the Tray picker. Writes cache/checks/r2-3/tour_*.png.
//   node tools/checks/r2-3/shots.js --port 8853
'use strict';
const L = require('./lib');

const TRAY_CC = ['0x003516eecbb510e6', 0], TRAY_EA = ['0x003d1736d3ca0019', 0];

(async () => {
  const port = L.argPort();
  const rows = [];
  for (const [w, hgt] of [[1366, 768], [1920, 1080]]) {
    const { browser, page, logs } = await L.appPage(port, { w, h: hgt });
    const shot = async name => { await L.sleep(900); await L.shot(page, `tour_${name}_${w}.png`); };
    const cam = (pos, at) => page.evaluate(async (pos, at) => {
      const THREE = await import('three');
      app.vp.stopCamera && app.vp.stopCamera();
      app.vp.controls.lookFrom(new THREE.Vector3(...pos), new THREE.Vector3(...at));
    }, pos, at);
    try {
      await page.waitForFunction('app.posePresets && app.posePresets.length > 0 && window.wickedScene', { timeout: 180000 });
      // 1. the Place tool on the double bed: the spots and the spots card
      await page.evaluate(async () => {
        const home = await import('/js/home.js'); home.hideHome(app);
        app.newScene(false, false);
        app.setFurniture('double_bed');
        await app._furnitureInfo('double_bed');
        app.selectSim(app.store.project.sims[0].id);
        app.setTool('move');
        await new Promise(r => setTimeout(r, 1500));
      });
      await cam([1.9, 2.1, 2.2], [0, 0.55, -0.1]);
      await shot('place_spots');
      // 2. sit on the sofa (seat 2), and the other on the edge
      await page.evaluate(async () => {
        app.newScene(false, false);
        app.setFurniture('sofa');
        const info = await app._furnitureInfo('sofa');
        const [a, b] = app.store.project.sims;
        app.setTool('move');
        app.sitHere(a.id, info.slots.find(s => s.n === 0));
        app.sitHere(b.id, info.slots.find(s => s.n === 1));
        app.selectSim(a.id);
        await new Promise(r => setTimeout(r, 1200));
      });
      await cam([0.6, 1.4, 2.6], [-0.3, 0.6, 0]);
      await shot('sit_sofa');
      // 3. see-through and bones on a Magic missionary
      await page.evaluate(async () => {
        const magic = await import('/js/magic.js');
        await magic.makeMagic(app, { recipe: 'missionary', place: 'double_bed', intensity: 0.6, seconds: 3 });
        app.setPlaying(false); app.showcase(false); clearTimeout(app._magicShow);
        app.setTool('rotate');
        app.selectSim(app.store.project.sims[1].id);
        app.setSeeThrough(true); app.setShowBones(true);
      });
      await cam([1.7, 1.5, 0.9], [0, 0.75, -0.2]);
      await shot('xray_bones');
      // 4. the clipping card (the kiss ready pose has hands deep in the partner)
      await page.evaluate(async () => {
        app.setSeeThrough(false); app.setShowBones(false);
        app.newScene(false, false);
        app.applyPosePreset(app.posePresets.find(x => x.id === 'kiss'), { places: 'never' });
        app.frameSims({ fromFront: true });
        await app.checkClipping();
      });
      await shot('clip_card');
      // 5. ... and the Send to game warning
      await page.evaluate(async () => {
        const p = app.store.project; p.name = 'Kiss test'; p.author = 'R2-3';
        app.exportDialog();
        await new Promise(r => setTimeout(r, 500));
      });
      await shot('send_warning');
      await page.evaluate(() => { const b = [...document.querySelectorAll('.backdrop:not(.leaving) button')].find(x => /Cancel/.test(x.textContent)); if (b) b.click(); });
      // 6. the Body step: hair, other bodies, a trial on
      await page.evaluate(async () => {
        const magic = await import('/js/magic.js');
        await magic.makeMagic(app, { recipe: 'cowgirl', place: 'double_bed', intensity: 0.6, seconds: 3 });
        app.setPlaying(false); app.showcase(false); clearTimeout(app._magicShow);
        const him = app.store.project.sims.find(s => s.frame === 'ym');
        app.selectSim(him.id);
        await app.tryBody(him.id, { kind: 'size', preset: 'large' });
        app.showStep('body');
        await new Promise(r => setTimeout(r, 900));
        document.querySelector('.hair-row').scrollIntoView({ block: 'start' });
      });
      await cam([1.5, 1.6, 1.6], [0, 0.8, -0.2]);
      await shot('body_step');
      // 7. the Motion step: Look at open, Follow-through
      await page.evaluate(async () => {
        app.endTrial();
        const her = app.store.project.sims.find(s => s.frame === 'yf');
        app.selectSim(her.id);
        const look = her.layers.find(l => l.type === 'look') || (app.addLayer(her.id, 'look'), her.layers.find(l => l.type === 'look'));
        app._openLayer = look.id;
        app.showStep('motion');
        await new Promise(r => setTimeout(r, 600));
      });
      await shot('motion_look');
      await page.evaluate(() => { const s = [...document.querySelectorAll('#panel-body .section')].find(x => /Follow-through/.test(x.textContent)); if (s) s.scrollIntoView({ block: 'center' }); });
      await shot('motion_follow');
      // 8. a Tray sim's own hair up close (CC and EA)
      for (const [tag, t] of [['cc', TRAY_CC], ['ea', TRAY_EA]]) {
        const head = await page.evaluate(async t => {
          app.newScene(false, false, 'solo');
          await app.addTraySim(t[0], t[1], 'Tray');
          app.removeSim(app.store.project.sims[0].id);
          app.showStep('body');
          await new Promise(r => setTimeout(r, 2500));
          const v = app.simViews.get(app.store.project.sims[0].id);
          v.group.updateMatrixWorld(true);
          return v.worldPos('b__Head__').toArray();
        }, t);
        await cam([head[0] + 0.3, head[1] + 0.12, head[2] + 0.55], [head[0], head[1] + 0.08, head[2]]);
        await shot('hair_' + tag);
      }
      // 9. the Tray picker for trying bodies
      await page.evaluate(async () => {
        app.newScene(false, false);
        const her = app.store.project.sims[0];
        app.selectSim(her.id);
        app.showStep('body');
        await new Promise(r => setTimeout(r, 300));
        const more = [...document.querySelectorAll('.try-bodies .chipbtn')].find(b => /More/.test(b.textContent));
        if (more) more.click();
        await new Promise(r => setTimeout(r, 1500));
      });
      await shot('tray_pick');
      const errs = logs.filter(l => l.type === 'pageerror' || (l.type === 'error' && !/Failed to load resource/.test(l.text)));
      rows.push([`${w}x${hgt}: the tour ran without page errors`, !errs.length, errs.slice(0, 3).map(e => e.text).join(' | ')]);
      // nothing sticks out of the window or under the inspector
      const layout = await page.evaluate(() => {
        const vp = document.getElementById('viewport-wrap').getBoundingClientRect();
        const out = [];
        for (const id of ['btn-xray', 'btn-bones', 'btn-clip']) { const r = document.getElementById(id).getBoundingClientRect(); if (r.right > vp.right + 1 || r.left < vp.left - 1) out.push(id); }
        return out;
      });
      rows.push([`${w}x${hgt}: the stage buttons stay on the stage`, !layout.length, layout.join(', ') || 'all inside']);
    } finally { await browser.close(); }
  }
  process.exitCode = L.table(rows, 'R2-3 screenshot tour (cache/checks/r2-3/tour_*.png)') ? 0 : 1;
})().catch(e => { console.error(e); process.exit(1); });
