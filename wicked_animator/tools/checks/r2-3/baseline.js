// R2-3 baseline: every fixture baked at every frame on the engine page (pipeline.bake), written before R2-3 edits
// the engine-side files it owns (sim.js, motion.js, physics.js). compare mode checks that projects without the new
// fields still bake the same (1e-6).
//   node tools/checks/r2-3/baseline.js --port 8853            (record)
//   node tools/checks/r2-3/baseline.js --port 8853 --compare  (compare with the record)
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const compare = process.argv.includes('--compare');
  const file = path.join(L.OUT, 'baseline_bake.json');
  const fx = L.fixtures();
  if (!fx.length) throw new Error('no fixtures in ' + L.FIX);
  const { browser, page, logs } = await L.enginePage(port);
  const rows = [];
  try {
    const out = {};
    for (const { name, project } of fx) {
      out[name] = await page.evaluate(project => {
        const app = R.scene(project);
        const res = app.pipeline.bake();
        return { sims: res.sims.map(s => s.id), tracks: res.tracks, flags: res.flags };
      }, project);
    }
    if (!compare) {
      fs.writeFileSync(file, JSON.stringify({ made: new Date().toISOString(), fixtures: out }));
      console.log('baseline written:', file, Object.keys(out).join(', '));
      return;
    }
    const base = JSON.parse(fs.readFileSync(file, 'utf8')).fixtures;
    for (const [name, now] of Object.entries(out)) {
      const was = base[name];
      if (!was) { rows.push([`${name}: in the baseline`, false, 'missing']); continue; }
      let worst = 0, where = '', missing = 0;
      now.tracks.forEach((tr, i) => {
        const b = was.tracks[i] || {};
        for (const bone of new Set([...Object.keys(tr), ...Object.keys(b)])) {
          for (const ch of ['r', 't']) {
            const A = tr[bone] && tr[bone][ch], B = b[bone] && b[bone][ch];
            if (!A && !B) continue;
            if (!A || !B || A.length !== B.length) { missing++; where = where || `${bone}.${ch}`; continue; }
            for (let k = 0; k < A.length; k++) for (let c = 0; c < A[k].length; c++) {
              const d = Math.abs(A[k][c] - B[k][c]);
              if (d > worst) { worst = d; where = `${bone}.${ch}[${k}]`; }
            }
          }
        }
      });
      rows.push([`${name}: bakes as before (1e-6)`, worst <= 1e-6 && !missing, `max diff ${worst.toExponential(2)} at ${where || '-'}${missing ? `, ${missing} tracks differ in shape` : ''}`]);
      rows.push([`${name}: flags as before`, JSON.stringify(now.flags) === JSON.stringify(was.flags), JSON.stringify(now.flags)]);
    }
    const errs = logs.filter(l => /pageerror/.test(l));
    rows.push(['no page errors', !errs.length, errs.slice(0, 3).join(' | ')]);
    process.exitCode = L.table(rows, 'R2-3: old projects bake the same') ? 0 : 1;
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
