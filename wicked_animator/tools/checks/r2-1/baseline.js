// R2-1 baseline (plan rule 8): recorded BEFORE this slice's first edit. Every fixture (%TEMP%\wa_fixtures) baked at
// every frame with pipeline.bake(), plus evaluate() / evaluateFaceBones() / evaluateFace() of every sim at every
// frame. The check (engine.js "old projects bake the same") compares against this and against the orig files.
//   node tools/checks/r2-1/baseline.js --port 8851
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const fx = L.fixtures();
  if (!fx.length) throw new Error('no fixtures in ' + L.FIX);
  const server = await L.startServer(port);
  let browser;
  try {
    browser = await L.launch();
    const { page, logs } = await L.openEngine(browser, port, { orig: true });
    const out = { made: new Date().toISOString(), fixtures: {} };
    for (const { name, project } of fx) {
      out.fixtures[name] = await page.evaluate(project => {
        const app = R.scene(project);
        const res = app.pipeline.bake();
        const p = app.store.project;
        const A = R.animation;
        const ev = p.sims.map(s => { const fr = []; for (let f = 0; f < p.length; f++) fr.push(A.evaluate(s.keys, f, p.length, p.loop)); return fr; });
        const evFB = p.sims.map(s => { const fr = []; for (let f = 0; f < p.length; f++) fr.push(A.evaluateFaceBones(s.keys, f, p.length, p.loop)); return fr; });
        const evF = p.sims.map(s => { const fr = []; for (let f = 0; f < p.length; f++) fr.push(A.evaluateFace(s.keys, f, p.length, p.loop)); return fr; });
        return { sims: res.sims.map(s => s.id), tracks: res.tracks, ev, evFB, evF, length: p.length };
      }, project);
      const b = out.fixtures[name];
      console.log(name, 'sims', b.sims.length, 'frames', b.length, 'bones', b.tracks.map(t => Object.keys(t).length));
    }
    fs.writeFileSync(path.join(L.OUT, 'baseline.json'), JSON.stringify(out));
    console.log('wrote', path.join(L.OUT, 'baseline.json'), (fs.statSync(path.join(L.OUT, 'baseline.json')).size / 1e6).toFixed(1), 'MB');
    if (logs.length) console.log('page logs:', logs.slice(0, 10));
  } finally {
    if (browser) await browser.close();
    L.stopServer(server);
  }
})().catch(e => { console.error(e); process.exit(1); });
