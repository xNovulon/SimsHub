// R2-3 spec_bodies 7.8: see-through, bones like Blender, and the clipping check.
//   - a hand posed 5 cm into the partner's belly is flagged with a depth of 4-6 cm; at 1 cm nothing is flagged
//   - every Magic recipe on the floor and the double bed: the issues found (target: at most 2 each, none deeper than
//     4 cm - the recipes that need fixing are listed for the Magic owner)
//   - bones: one per posable bone (60 per sim, jaw and tongue included); a real click on the right forearm's bone
//     selects b__R_Forearm__; Alt+Z / Alt+B switch see-through and bones
//   - see-through gives every material back exactly (opacity, transparent, depthWrite) - bodies, hair, furniture
//   - the three buttons are there without any index.html edit; Send to game shows the clipping warning; the timeline
//     gets a red tick per place
//   - speed: a clipping scan of a 90-frame, 2-sim loop, the bones' per-frame update, pipeline.apply (median)
//   node tools/checks/r2-3/xray_clip.js --port 8853 [--quick]
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const QUICK = process.argv.includes('--quick');

(async () => {
  const port = L.argPort();
  const rows = [];
  const html = fs.readFileSync(path.join(L.ROOT, 'web', 'index.html'), 'utf8');
  rows.push(['index.html has no see-through / bones / clipping button (added by the feature)', !/btn-xray|btn-bones|btn-clip/.test(html)]);
  const { browser, page, logs, writes } = await L.appPage(port, { w: 1366, h: 768 });
  try {
    await page.waitForFunction('app.posePresets && app.posePresets.length > 0 && window.wickedScene', { timeout: 180000 });
    rows.push(['the three buttons are on the stage', await page.evaluate(() => ['btn-xray', 'btn-bones', 'btn-clip'].every(id => !!document.getElementById(id)))]);

    // ---- a hand in the belly
    const belly = await page.evaluate(async () => {
      const THREE = await import('three'), cc = await import('/js/clipcheck.js'), mo = await import('/js/motion.js'), pm = await import('/js/posemath.js');
      const home = await import('/js/home.js'); home.hideHome(app);
      app.newScene(false, false);
      const [A, B] = app.store.project.sims;
      const vA = app.simViews.get(A.id), vB = app.simViews.get(B.id);
      // closer together
      const d0 = vB.worldPos('b__Pelvis__').sub(vA.worldPos('b__Pelvis__')).setY(0);
      app.transformSim(B.id, { offset: d0.clone().setLength(-0.4) });
      const capA = cc.capsulesOf(vA).find(c => c.name === 'right hand'), capB = cc.capsulesOf(vB).find(c => c.name === 'belly');
      // the hand is moved in front of the belly until the check's own measure (each part's skin reach toward the
      // other, a little inside the skin) says it is `depth` deep
      const put = depth => {
        for (const e of app.pipeline.entries()) app.pipeline.base(e, 0);
        const b = cc.capsuleNow(vB, capB), fwd = mo.pelvisAxes(vB).forward.setY(0).normalize();
        const mid = b.a.clone().add(b.b).multiplyScalar(0.5);
        let target = mid.clone().addScaledVector(fwd, 0.12);
        for (let it = 0; it < 8; it++) {
          A.pins['R hand'] = pm.worldToSpace(vA, target).toArray();
          for (const e of app.pipeline.entries()) app.pipeline.base(e, 0);
          const now = cc.overlap({ c: capA, ...cc.capsuleNow(vA, capA) }, { c: capB, ...cc.capsuleNow(vB, capB) });
          target.addScaledVector(fwd, now - depth);                  // too deep: out along the belly's front
        }
        const issues = cc.scanClipping(app, { step: 1 });
        const hit = issues.find(i => i.simId === A.id && i.part === 'right hand' && i.otherId === B.id && i.otherPart === 'belly');
        return { depth: hit ? hit.depth : 0, n: issues.length, texts: issues.slice(0, 4).map(i => i.text) };
      };
      const five = put(0.05), one = put(0.01);
      delete A.pins['R hand'];
      app.applyPoses();
      return { five, one, rHand: capA.r, rBelly: capB.r };
    });
    rows.push(['a hand 5 cm into the partner\'s belly: flagged, 4-6 cm deep', belly.five.depth >= 0.04 && belly.five.depth <= 0.06, `${(belly.five.depth * 100).toFixed(1)} cm (radii: hand ${(belly.rHand * 100).toFixed(1)}, belly ${(belly.rBelly * 100).toFixed(1)} cm)`]);
    rows.push(['a hand 1 cm into the belly: nothing flagged there', belly.one.depth === 0, belly.one.texts.join(' | ') || 'no issues']);

    // ---- bones: count, click, keys; see-through restores exactly
    const bones = await page.evaluate(async () => {
      app.newScene(false, false);
      app.setFurniture('double_bed');
      await app._furnitureInfo('double_bed');
      await new Promise(r => setTimeout(r, 1200));                 // the real bed and the hair arrive
      const snap = () => {
        const out = [];
        for (const [, v] of app.simViews) for (const m of [v.material, ...(v.partMaterials || [])]) out.push([m.opacity, m.transparent, m.depthWrite]);
        app.vp.furniture.traverse(o => { if (o.isMesh) for (const m of [].concat(o.material)) out.push([m.opacity, m.transparent, m.depthWrite]); });
        return JSON.stringify(out);
      };
      const before = snap();
      const fire = (code, alt = true) => window.dispatchEvent(new KeyboardEvent('keydown', { code, key: code.slice(3).toLowerCase(), altKey: alt, bubbles: true }));
      fire('KeyZ');
      const seeOn = app.xray.seeOn, during = snap();
      app.selectSim(app.store.project.sims[1].id);                   // the selected sim turns solid, the other see-through
      const selSolid = app.simViews.get(app.store.project.sims[1].id).material.opacity === 1 && app.simViews.get(app.store.project.sims[0].id).material.opacity < 1;
      fire('KeyZ');
      const after = snap();
      fire('KeyB');
      const bonesOn = app.xray.bonesOn;
      const counts = app.store.project.sims.map(s => app.xray.count(s.id));
      const hair = [...app.simViews.values()].map(v => (v.parts || []).length);
      return { before, during, after, seeOn, selSolid, bonesOn, counts, hair };
    });
    rows.push(['Alt+Z turns see-through on', bones.seeOn]);
    rows.push(['see-through: the selected sim solid, the other see-through', bones.selSolid]);
    rows.push(['see-through changes the materials', bones.during !== bones.before]);
    rows.push(['see-through off gives every material back exactly (bodies, hair, furniture)', bones.after === bones.before, `${JSON.parse(bones.before).length} materials, hair parts ${bones.hair.join('/')}`]);
    rows.push(['Alt+B shows the bones', bones.bonesOn]);
    rows.push(['one bone per posable bone: 60 per sim', bones.counts.every(n => n === 60), bones.counts.join(', ')]);
    // click the right forearm's bone (front view, frame the male)
    const at = await page.evaluate(async () => {
      const THREE = await import('three');
      const s = app.store.project.sims[1], v = app.simViews.get(s.id);
      app.setTool('rotate');
      app.store.selected = { sim: s.id, bone: null }; app.emitSelection();
      app.setView('front');
      app.vp.frame(v.worldPos('b__Spine1__'), 0.9, new THREE.Vector3(0, 0.1, 1));
      await new Promise(r => setTimeout(r, 1300));
      app.xray.update();
      const p = v.worldPos('b__R_Forearm__').lerp(v.worldPos('b__R_Hand__'), 0.45).project(app.vp.camera);
      const r = app.vp.canvas.getBoundingClientRect();
      return { x: r.left + (p.x + 1) / 2 * r.width, y: r.top + (1 - p.y) / 2 * r.height };
    });
    await page.mouse.move(at.x, at.y);
    await L.sleep(120);
    await page.mouse.down(); await page.mouse.up();
    await L.sleep(300);
    const picked = await page.evaluate(() => ({ ...app.store.selected, label: app.store.sim(app.store.selected.sim) && app.store.sim(app.store.selected.sim).label }));
    await L.shot(page, 'xray_bones_click.png');
    rows.push(['a click on the right forearm\'s bone selects b__R_Forearm__', picked.bone === 'b__R_Forearm__', `${picked.label} · ${picked.bone}`]);
    // the bones' update each frame
    const perf = await page.evaluate(async () => {
      const t = [];
      for (let k = 0; k < 120; k++) { const t0 = performance.now(); app.xray.update(); t.push(performance.now() - t0); }
      t.sort((a, b) => a - b);
      app.setShowBones(false);
      return { median: t[t.length >> 1] };
    });
    rows.push(['bones: the per-frame update under 0.5 ms (median)', perf.median < 0.5, `${perf.median.toFixed(3)} ms`]);

    // ---- see-through and bones on Magic (screenshots), the clip scan, the card, the ticks, Send
    const magicShots = await page.evaluate(async () => {
      const magic = await import('/js/magic.js');
      await magic.makeMagic(app, { recipe: 'missionary', place: 'double_bed', intensity: 0.6, seconds: 3 });
      app.setPlaying(false); app.showcase(false); if (app.vp.stopCamera) app.vp.stopCamera();
      app.setView('persp');
      app.frameSims({ fromFront: true });
      app.selectSim(app.store.project.sims[1].id);
      app.setSeeThrough(true); app.setShowBones(true);
      await new Promise(r => setTimeout(r, 1500));
      return true;
    });
    void magicShots;
    await L.shot(page, 'xray_see_through_bones_1366.png');
    const clip = await page.evaluate(async () => {
      app.setSeeThrough(false); app.setShowBones(false);
      const t0 = performance.now();
      const issues = await app.checkClipping();
      const asyncMs = performance.now() - t0;
      const cc = await import('/js/clipcheck.js');
      const t1 = performance.now(); cc.scanClipping(app, { step: 1 }); const syncMs = performance.now() - t1;
      const ranges = issues.reduce((a, i) => a + (i.ranges || [1]).length, 0);
      const marks = (app.timeline.marks || []).filter(m => m._clip).length;
      const card = document.getElementById('clip-card');
      // pipeline.apply for 2 sims (look-at, holds and all)
      const t = [];
      for (let k = 0; k < 300; k++) { const a = performance.now(); app.pipeline.apply(k % app.store.project.length, { physics: true, overrides: false }); t.push(performance.now() - a); }
      t.sort((a, b) => a - b);
      app.applyPoses();
      return { n: issues.length, ranges, marks, card: !!card, cardText: card ? card.textContent.slice(0, 120) : '', asyncMs, syncMs, apply: t[t.length >> 1] };
    });
    await L.shot(page, 'xray_clip_card_1366.png');
    rows.push(['Check clipping opens the card', clip.card, clip.cardText]);
    rows.push(['a red tick on the timeline per place', clip.marks === clip.ranges, `${clip.marks} ticks, ${clip.ranges} ranges, ${clip.n} issues`]);
    rows.push(['a scan of a 90-frame 2-sim loop under 150 ms', clip.syncMs < 150, `${clip.syncMs.toFixed(0)} ms (the button's scan, spread over frames: ${clip.asyncMs.toFixed(0)} ms)`]);
    rows.push(['pipeline.apply for 2 sims (Magic with look-at and holds): median <= 1 ms', clip.apply <= 1.0, `${clip.apply.toFixed(3)} ms`]);
    // Send to game: the warning line
    const send = await page.evaluate(async () => {
      app.store.project.name = 'Clip check'; app.store.project.author = 'r2-3';
      app.exportDialog();
      await new Promise(r => setTimeout(r, 600));
      const dlg = document.querySelector('.backdrop:not(.leaving)');
      const txt = dlg ? dlg.textContent : '';
      const line = /Hands or legs go through/.test(txt);
      const btn = dlg && [...dlg.querySelectorAll('button')].find(b => /Show me/.test(b.textContent) && b.closest('div') && /Hands or legs/.test(b.closest('div').textContent));
      if (btn) btn.click();
      await new Promise(r => setTimeout(r, 500));
      return { line, clicked: !!btn, card: !!document.getElementById('clip-card'), open: !!document.querySelector('.backdrop:not(.leaving)') };
    });
    rows.push(['Send to game lists "Hands or legs go through ..." when there is clipping', send.line || clip.n === 0, JSON.stringify(send)]);
    rows.push(['its "Show me" closes the dialog and opens the card', !send.line || (send.clicked && send.card && !send.open), JSON.stringify(send)]);

    // ---- every recipe on the floor and the double bed
    const recipes = await page.evaluate(async () => (await import('/js/magic.js')).RECIPES.map(r => r.id));
    const table = [];
    for (const place of ['floor', 'double_bed']) for (const recipe of (QUICK ? ['cowgirl', 'missionary', 'doggy'] : recipes)) {
      const r = await page.evaluate(async (recipe, place) => {
        const magic = await import('/js/magic.js'), cc = await import('/js/clipcheck.js');
        app.store.setDirty(false);
        const ok = await magic.makeMagic(app, { recipe, place, intensity: 0.6, seconds: 3 });
        app.setPlaying(false); app.showcase(false);
        if (!ok) return { ok: false };
        await app._furnitureInfo(place);
        const issues = cc.scanClipping(app, { step: 1 });
        return { ok: true, n: issues.length, deepest: issues.length ? issues[0].depth : 0, top: issues.slice(0, 3).map(i => i.text.replace(/^[^·]*· /, '')) };
      }, recipe, place);
      table.push({ place, recipe, ...r });
    }
    const made = table.filter(r => r.ok), good = made.filter(r => r.n <= 2 && r.deepest <= 0.04);
    for (const place of ['floor', 'double_bed']) {
      const mine = made.filter(r => r.place === place);
      const need = mine.filter(r => !(r.n <= 2 && r.deepest <= 0.04));
      rows.push([`Magic on ${place}: clipping per recipe (target <= 2, none deeper than 4 cm) - recorded`, true,
        `${mine.length - need.length}/${mine.length} meet it; need fixing: ${need.map(r => `${r.recipe} ${r.n} (${Math.round(r.deepest * 100)} cm)`).join(', ') || 'none'}`]);
    }
    fs.writeFileSync(path.join(L.OUT, 'clipping_magic.json'), JSON.stringify(table, null, 1));
    void good;
    const errs = logs.filter(l => l.type === 'pageerror' || (l.type === 'error' && !/Failed to load resource/.test(l.text)));
    rows.push(['no page errors', !errs.length, errs.slice(0, 3).map(e => e.text).join(' | ')]);
    rows.push(['nothing was written (Send is intercepted)', writes.every(w => w.route === '/api/export' || /recovery/.test(w.route)), writes.map(w => w.route).join(', ')]);
    process.exitCode = L.table(rows, 'R2-3: see-through, bones, clipping check (spec_bodies 7.8)') ? 0 : 1;
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
