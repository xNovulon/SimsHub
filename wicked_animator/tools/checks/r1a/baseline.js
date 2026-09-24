// R1-A goal 1: record the baseline with the engine as it was before R1-A (cache/checks/r1a/orig): every fixture baked
// at every frame with pipeline.bake(), plus the old evaluate() of the jaw and tongue at every frame (for the
// migration check) and the old pipeline.apply timing. Writes cache/checks/r1a/baseline.json.
//   node tools/checks/r1a/baseline.js --port 8841
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const fx = L.fixtures();
  if (!fx.length) throw new Error('no fixtures: run fixtures.js first');
  const server = await L.startServer(port);
  let browser;
  try {
    browser = await L.launch();
    const { page, logs } = await L.open(browser, port, { kind: 'engine', orig: true });
    const out = { made: new Date().toISOString(), fixtures: {} };
    for (const { name, project } of fx) {
      out.fixtures[name] = await page.evaluate(project => {
        const app = R.scene(project);
        const res = app.pipeline.bake();
        const p = app.store.project;
        const FACEB = ['b__Jaw__', 'b__Tounge__1', 'b__Tounge__2', 'b__Tounge__3'];
        const evalFace = p.sims.map(s => {
          const fr = [];
          for (let f = 0; f < p.length; f++) {
            const e = R.animation.evaluate(s.keys, f, p.length, p.loop);
            const o = { rot: {}, pos: {} };
            for (const b of FACEB) { if (e && e.rot[b]) o.rot[b] = e.rot[b]; if (e && e.pos && e.pos[b]) o.pos[b] = e.pos[b]; }
            fr.push(o);
          }
          return fr;
        });
        // timing: pipeline.apply for this project's sims
        const t = [];
        for (let k = 0; k < 300; k++) { const t0 = performance.now(); app.pipeline.apply(k % p.length, { physics: true, overrides: false }); t.push(performance.now() - t0); }
        t.sort((a, b) => a - b);
        return { sims: res.sims.map(s => s.id), tracks: res.tracks, flags: res.flags, evalFace, applyMedianMs: t[t.length >> 1] };
      }, project);
      const b = out.fixtures[name];
      console.log(name, 'sims', b.sims.length, 'bones', b.tracks.map(t => Object.keys(t).length), 'apply median ms', b.applyMedianMs.toFixed(3), 'flags', JSON.stringify(b.flags));
    }
    fs.mkdirSync(L.OUT, { recursive: true });
    fs.writeFileSync(path.join(L.OUT, 'baseline.json'), JSON.stringify(out));
    console.log('wrote', path.join(L.OUT, 'baseline.json'), (fs.statSync(path.join(L.OUT, 'baseline.json')).size / 1e6).toFixed(1), 'MB');
    if (logs.length) console.log('page logs:', logs.slice(0, 10));
  } finally {
    if (browser) await browser.close();
    L.stopServer(server);
  }
})().catch(e => { console.error(e); process.exit(1); });
