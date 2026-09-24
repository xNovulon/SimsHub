// Screenshots of R2-4's UI (development + report): node tools/checks/r2-4/shots.js <port> [pinDir] [w] [h]
const H = require('../lib/harness.js');
const { pinFiles } = require('./pin.js');
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const port = +(process.argv[2] || 8854), pin = process.argv[3] && process.argv[3] !== '-' ? process.argv[3] : null;
  const w = +(process.argv[4] || 1366), hgt = +(process.argv[5] || 768);
  const { browser, page, logs } = await H.open(port, { w, h: hgt, beforeLoad: pin ? p => pinFiles(p, pin) : null });
  const tag = `${w}x${hgt}`;
  const ev = (fn, ...a) => page.evaluate(fn, ...a);
  await ev(async () => {
    const app = window.app;
    (await import('/js/home.js')).hideHome(app);
    const m = await import('/js/magic.js');
    Math.random = (() => { let s = 12345; return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; })();
    await m.makeMagic(app, { recipe: 'cowgirl', place: 'double_bed', seconds: 3, name: 'R24 shots', author: 'R24' });
    app.setPlaying(false); clearTimeout(app._magicShow); app.showcase && app.showcase(false);
    await new Promise(r => setTimeout(r, 1300)); clearTimeout(app._magicShow); app.showcase && app.showcase(false);
    await app.voicesReady;
    const F = app.store.project.sims.find(s => s.frame === 'yf');
    app.selectSim(F.id);
    app.showStep('sounds');
    app.setFrame(60);
    app.finishPreset('face', 60);
    app.addMoment({ type: 'UNDRESS', frame: 12, sim: F.id, naked: 'TOP' });
    app.addMoment({ type: 'NOTE', frame: 30, text: 'she looks up at him' });
    app.setFrame(66);
  });
  await sleep(2500);
  await H.shot(page, `cache/checks/r2-4/sounds_${tag}.png`);
  // scroll the panel to the moments
  await ev(() => { const b = document.getElementById('panel-body'); const s = [...b.querySelectorAll('.section-title')].find(x => /Finish/.test(x.textContent)); s && s.scrollIntoView(); });
  await sleep(400);
  await H.shot(page, `cache/checks/r2-4/sounds_finish_${tag}.png`);
  // moment dialog: cum
  await ev(() => { const app = window.app; const e = app.store.project.events.find(x => x.type === 'CUM'); app.editMoment(e.id); });
  await sleep(700);
  await H.shot(page, `cache/checks/r2-4/dialog_cum_${tag}.png`);
  await ev(() => document.querySelectorAll('#modal-root .modal-x').forEach(b => b.click()));
  await sleep(400);
  // moment dialog: effect
  await ev(() => { const app = window.app; const e = app.store.project.events.find(x => x.type === 'EFFECT'); app.editMoment(e.id); });
  await sleep(1800);
  await H.shot(page, `cache/checks/r2-4/dialog_effect_${tag}.png`);
  await ev(() => document.querySelectorAll('#modal-root .modal-x').forEach(b => b.click()));
  await sleep(400);
  // the moments row menu
  const box = await ev(() => { const c = document.getElementById('tl-canvas').getBoundingClientRect(); return { x: c.left + 400, y: c.top + 28 + 11 }; });
  await page.mouse.click(box.x, box.y, { button: 'right' });
  await sleep(400);
  await H.shot(page, `cache/checks/r2-4/menu_${tag}.png`);
  await page.keyboard.press('Escape');
  await ev(() => document.querySelectorAll('.ctx-menu').forEach(m => m.remove()));
  // add sound dialog: game voices
  await ev(() => { const app = window.app; app.addSoundDialog(app.store.sim().id); });
  await sleep(300);
  await ev(() => { const s = document.querySelector('#modal-root select'); s.value = 'game'; s.dispatchEvent(new Event('change')); });
  await sleep(400);
  await H.shot(page, `cache/checks/r2-4/dialog_gamevoices_${tag}.png`);
  await ev(() => document.querySelectorAll('#modal-root .modal-x').forEach(b => b.click()));
  await sleep(300);
  // effect particles playing + cum on the face (close up)
  // a close look at her face from the front (cum at level 2 after frame 60), then at his tip (the drool stand-in)
  const look = async (simFrame, bone, dist, frame, up = 0.05) => ev(({ simFrame, bone, dist, frame, up }) => {
    const app = window.app, THREE = window.__THREE;
    const s = app.store.project.sims.find(x => x.frame === simFrame), v = app.simViews.get(s.id);
    app.setFrame(frame);
    v.group.updateMatrixWorld(true);
    const at = v.worldPos(bone).clone();
    const head = v.worldPos('b__Head__'), lip = v.worldPos('b__LoLip__');
    const fwd = bone === 'b__Head__' ? lip.clone().sub(head).setY(0).normalize() : new THREE.Vector3(0.6, 0.35, 0.72).normalize();
    const pos = at.clone().addScaledVector(fwd, dist).add(new THREE.Vector3(0, up, 0));
    clearTimeout(app._magicShow); app.showcase && app.showcase(false);
    app.vp.stopCamera && app.vp.stopCamera();
    app.vp.controls.lookFrom(pos, bone === 'b__Head__' ? at.clone().add(new THREE.Vector3(0, 0.06, 0)) : at);
  }, { simFrame, bone, dist, frame, up });
  await ev(async () => { window.__THREE = await import('three'); });
  // a standing couple (nothing in front of the faces): cum on her face (level 3) and the drool at his tip
  await ev(() => {
    const app = window.app;
    app.newScene(false, false, 'couple');
    const p = app.store.project, F = p.sims.find(s => s.frame === 'yf'), M = p.sims.find(s => s.frame === 'ym');
    app.addLayer(M.id, 'thrust'); app.setPlaying(false);
    app.addMoment({ type: 'CUM', frame: 5, sim: F.id, cum: 'FACE', level: 3 });
    app.addMoment({ type: 'CUM', frame: 5, sim: F.id, cum: 'CHEST', level: 2 });
    app.addMoment({ type: 'EFFECT', frame: 10, end: 90, sim: M.id, effect: 'pet_small_drool_front', joint: 'b__Penis_Tip' });
    app.selectSim(F.id);
    app.effects.sampleNow();
  });
  await sleep(1500);
  await look('yf', 'b__Head__', 0.5, 40, 0.02);
  await sleep(2200);
  await H.shot(page, `cache/checks/r2-4/cum_face_${tag}.png`);
  await look('ym', 'b__Penis_Tip', 0.7, 60, 0.15);
  await sleep(1500);
  await H.shot(page, `cache/checks/r2-4/effect_${tag}.png`);
  // details
  await ev(() => { const app = window.app; app.showStep('details'); const F = app.store.project.sims.find(s => s.frame === 'yf'); F.cumAfter = ['FACE', 'CHEST']; app.renderStep(); const c = document.querySelector('.cum-after-row'); c && c.scrollIntoView(); });
  await sleep(500);
  await H.shot(page, `cache/checks/r2-4/details_${tag}.png`);
  console.log(logs.filter(l => ['error', 'pageerror'].includes(l.type)).slice(0, 20));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
