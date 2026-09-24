// Quick look at the Face step (exploration helper for R2-5; not a check).
//   node tools/checks/r2-5/peek.js --port 8855 [--w 1366 --h 768] [--out name] [--tab game] [--scroll 400]
const path = require('path');
const H = require('../lib/harness.js');
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
(async () => {
  const port = +arg('--port', 8855), w = +arg('--w', 1366), h = +arg('--h', 768), out = arg('--out', 'peek');
  const { browser, page, logs } = await H.open(port, { w, h });
  const info = await page.evaluate(async (tab, scroll, sel) => {
    document.getElementById('home').classList.add('hidden');
    for (let i = 0; i < 100 && !(app.posePresets && app.posePresets.length); i++) await new Promise(r => setTimeout(r, 100));
    const pr = app.posePresets.find(x => x.id === 'cowgirl') || app.posePresets.find(x => x.group === 'couple');
    app.applyPosePreset(pr);
    if (tab) app._faceTab = tab;
    app.showStep('face');
    await new Promise(r => setTimeout(r, 4000));
    if (tab) app.renderStep();
    await new Promise(r => setTimeout(r, 3000));
    document.getElementById('panel-body').scrollTop = +scroll || 0;
    if (sel && document.querySelector(sel)) document.querySelector(sel).scrollIntoView({ block: 'start' });
    return { features: !!app.__faces2, setFaceBones: typeof app.setFaceBones, css: !!document.querySelector('link[data-feature*="faces.css"]') };
  }, arg('--tab', ''), arg('--scroll', '0'), arg('--sel', ''));
  console.log(info);
  await new Promise(r => setTimeout(r, 800));
  await H.shot(page, path.join(H.ROOT, 'cache', 'checks', 'r2-5', out + '.png'));
  console.log(logs.filter(l => l.type === 'error' || l.type === 'pageerror' || l.type === 'warning').map(l => l.text).slice(0, 10));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
