// R1-B leftover bugs from the last verification:
//   E11 - a ready pose picked after choosing furniture in the Scene step lands on the furniture top, not buried in it;
//   TL-fit - the timeline fills its width again after a new animation, and after undo / redo that changes the length.
//   node tools/checks/r1b/leftovers.js --port 8842
const path = require('path');
const H = require('../lib/harness.js');

const argv = process.argv.slice(2);
const PORT = +((argv.indexOf('--port') >= 0 && argv[argv.indexOf('--port') + 1]) || 8842);
const OUT = path.join(H.ROOT, 'cache', 'checks', 'r1b');
const rows = [];
const C = (name, ok, detail) => { rows.push({ name, ok: !!ok, detail }); };

(async () => {
  const { browser, page, logs } = await H.open(PORT, { w: 1366, h: 768 });
  const r = await page.evaluate(async () => {
    const checks = [];
    const sleep = ms => new Promise(res => setTimeout(res, ms));
    document.getElementById('home').classList.add('hidden');
    for (let i = 0; i < 100 && !(app.posePresets && app.posePresets.length); i++) await sleep(100);
    const lowest = sims => {
      let low = Infinity;
      for (const s of sims) {
        const v = app.simViews.get(s.id);
        app.pipeline.base({ sim: s, v }, Math.round(app.store.frame));
        v.group.updateMatrixWorld(true);
        for (const b of v.bones) if (/^b__(L_|R_)?(Pelvis|Spine\d|Neck|Head|Clavicle|UpperArm|Forearm|Hand|Thigh|Calf|Foot|Toe|Thumb\d|Index\d|Mid\d|Ring\d|Pinky\d)__$/.test(b.name)) low = Math.min(low, v.worldPos(b.name).y);
      }
      return low;
    };
    // ---- E11: Double bed first (Scene step), then a ready pose (Pose step)
    for (const [furn, preset] of [['double_bed', 'cowgirl'], ['double_bed', 'missionary'], ['sofa', 'cowgirl']]) {
      app.newScene(false, false, 'couple');
      await sleep(200);
      app.showStep('scene');
      app.setFurniture(furn);
      await sleep(300);
      app.showStep('pose');
      const pr = app.posePresets.find(x => x.id === preset);
      app.applyPosePreset(pr);
      const liftResult = await app._lifting;
      await sleep(300);
      const p = app.store.project;
      const info = await app._furnitureInfo(furn);
      const top = info && typeof info.surface_height === 'number' ? info.surface_height : app.furniture.find(f => f.id === furn).size[1];
      const low = lowest(p.sims);
      // the lowest point of the skin (the shared placing helpers measure it on the meshes), else the lowest bone - 6 cm
      const pl = app._placing;
      const skin = pl && pl.lowestSkin ? pl.lowestSkin(app, p.sims, 0) : low - 0.06;
      const ok = Math.abs(skin - top) < 0.02;
      checks.push([`E11 ${preset} after picking ${furn}: the sims rest on its top (lowest skin within 2 cm of ${top.toFixed(3)} m)`, ok,
        { lowestSkin: +skin.toFixed(3), lowestBoneMinus6cm: +(low - 0.06).toFixed(3), top: +top.toFixed(3), lifted: liftResult, placingHelpers: !!(pl && pl.fitOnSurface), furniture: p.furniture, locations: p.locations }]);
      // keys and pending poses moved together: the key at frame 0 holds the lifted pose
      const k0 = p.sims.map(s => s.keys.find(k => k.frame === 0));
      checks.push([`E11 ${preset} on ${furn}: the lift is in the keys (the pose plays lifted)`, k0.every(Boolean) && (() => { app.setFrame(0); return Math.abs(lowest(p.sims) - low) < 0.005; })()]);
      if (furn === 'double_bed' && preset === 'cowgirl') {
        // the camera framed the lifted sims (their middle is in the picture)
        const v = app.simViews.get(p.sims[0].id);
        v.group.updateMatrixWorld(true);
        const c = v.worldPos('b__Pelvis__').project(app.vp.camera);
        checks.push(['E11 the camera frames the sims on the bed', Math.abs(c.x) < 0.9 && Math.abs(c.y) < 0.9, [c.x, c.y].map(x => +x.toFixed(3))]);
      }
    }
    // a second ready pose at another frame lifts only that key (the first key stays where it was)
    {
      app.newScene(false, false, 'couple');
      app.setFurniture('double_bed');
      app.applyPosePreset(app.posePresets.find(x => x.id === 'cowgirl'));
      await app._lifting;
      const F = app.store.project.sims[0];
      const k0 = JSON.stringify(F.keys.find(k => k.frame === 0).pose.pos);
      app.setFrame(45);
      app.applyPosePreset(app.posePresets.find(x => x.id === 'missionary'));
      await app._lifting;
      await sleep(200);
      const top = (await app._furnitureInfo('double_bed')).surface_height;
      const pl = app._placing;
      const skin45 = pl && pl.lowestSkin ? pl.lowestSkin(app, app.store.project.sims, 45) : lowest(app.store.project.sims) - 0.06;
      checks.push(['E11 a second ready pose later in the loop is lifted too, the first key stays put', JSON.stringify(F.keys.find(k => k.frame === 0).pose.pos) === k0 && Math.abs(skin45 - top) < 0.02,
        { keys: F.keys.map(k => k.frame), lowestSkin45: +skin45.toFixed(3), top }]);
    }
    // the floor is unchanged
    {
      app.newScene(false, false, 'couple');
      app.applyPosePreset(app.posePresets.find(x => x.id === 'cowgirl'));
      await app._lifting;
      const low = lowest(app.store.project.sims);
      checks.push(['E11 on the floor nothing is lifted', low < 0.2, +low.toFixed(3)]);
    }
    // ---- TL-fit
    const tl = app.timeline;
    const fitted = () => { const w = tl.canvas.clientWidth - 168 - 24; return Math.abs(tl.pxPerFrame - Math.max(1.5, Math.min(26, w / Math.max(10, app.store.project.length)))) < 1e-6 && tl.scroll === 0; };
    app.setLength(300, 'keep');
    tl.pxPerFrame = 3; tl.scroll = 40; tl.draw();
    app.newScene(false, false, 'couple');
    checks.push(['TL-fit: a new animation fills the timeline (fit at the end of newScene)', fitted() && app.store.project.length === 90, { ppf: tl.pxPerFrame, scroll: tl.scroll, len: app.store.project.length }]);
    app.setLength(240, 'keep');
    checks.push(['TL-fit: a new length fills the timeline', fitted()]);
    tl.pxPerFrame = 20; tl.draw();
    app.undo();
    checks.push(['TL-fit: undo back to 90 frames fits the timeline again', app.store.project.length === 90 && fitted(), { len: app.store.project.length, ppf: tl.pxPerFrame }]);
    tl.pxPerFrame = 20; tl.scroll = 10; tl.draw();
    app.redo();
    checks.push(['TL-fit: redo to 240 frames fits it again', app.store.project.length === 240 && fitted(), { len: app.store.project.length, ppf: tl.pxPerFrame }]);
    // an undo that keeps the length keeps the zoom (the user's own zoom is not thrown away)
    app.store.checkpoint(); app.store.project.loops = 4;
    tl.pxPerFrame = 12; tl.scroll = 5; tl.draw();
    app.undo();
    checks.push(['TL-fit: an undo that keeps the length keeps the zoom', tl.pxPerFrame === 12 && tl.scroll === 5, { ppf: tl.pxPerFrame, scroll: tl.scroll }]);
    return checks;
  });
  for (const [n, ok, d] of r) C(n, ok, d);
  // the picture: a ready pose picked after the double bed (the sims lie on the bed, framed), once the panel has settled
  await page.evaluate(async () => {
    const sleep = ms => new Promise(res => setTimeout(res, ms));
    app.newScene(false, false, 'couple');
    app.showStep('scene');
    app.setFurniture('double_bed');
    await sleep(300);
    app.showStep('pose');
    app.applyPosePreset(app.posePresets.find(x => x.id === 'cowgirl'));
    await app._lifting;
    await sleep(1200);
  });
  await H.shot(page, path.join(OUT, 'leftovers_e11.png'));
  const errs = logs.filter(l => l.type === 'pageerror');
  C('no page errors', !errs.length, errs.map(e => e.text));
  await browser.close();
  process.exit(H.report(rows, 'R1-B leftovers (E11, TL-fit)') ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
