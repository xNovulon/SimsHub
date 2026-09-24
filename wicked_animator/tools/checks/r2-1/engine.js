// R2-1: "an old project without autoCurve bakes identically to before the round (1e-6)".
//   a) this slice's engine files (animation.js, state.js) as they were before R2-1 (cache/checks/r2-1/orig) against
//      today's, with everything else as it is now: every fixture baked at every frame must be identical (1e-6);
//   b) evaluate / evaluateFaceBones / evaluateFace of every sim at every frame against the baseline recorded before
//      the first edit (baseline.js) - pure functions, so the other slices' work doesn't change them;
//   c) the whole bake against that baseline too (for the report: other slices changed the pipeline since).
//   node tools/checks/r2-1/engine.js --port 8853        (starts and stops its own server)
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const rows = [];
const add = (name, pass, detail) => { rows.push([name, !!pass, detail]); };

function maxDiffTracks(a, b) {
  let worst = 0, where = '';
  for (let i = 0; i < a.length; i++) {
    for (const [bone, tr] of Object.entries(a[i])) {
      const tb = b[i] && b[i][bone];
      if (!tb) { worst = Math.max(worst, 1); where = `${i}:${bone} missing`; continue; }
      for (const ch of ['r', 't']) {
        if (!tr[ch]) continue;
        if (!tb[ch]) { worst = 1; where = `${i}:${bone}.${ch} missing`; continue; }
        for (let f = 0; f < tr[ch].length; f++) for (let k = 0; k < tr[ch][f].length; k++) {
          const d = Math.abs(tr[ch][f][k] - tb[ch][f][k]);
          if (d > worst) { worst = d; where = `${i}:${bone}.${ch}[${f}][${k}]`; }
        }
      }
    }
  }
  return { worst, where };
}
function maxDiffPoses(A, B) {
  let worst = 0;
  const cmp = (x, y) => {
    if (x === null || y === null || x === undefined || y === undefined) { if ((x == null) !== (y == null)) worst = Math.max(worst, 1); return; }
    if (typeof x === 'number') { worst = Math.max(worst, Math.abs(x - y)); return; }
    if (Array.isArray(x)) { for (let i = 0; i < x.length; i++) cmp(x[i], y[i]); return; }
    const keys = new Set([...Object.keys(x), ...Object.keys(y)]);
    for (const k of keys) { if (!(k in x) || !(k in y)) { worst = Math.max(worst, 1); continue; } cmp(x[k], y[k]); }
  };
  cmp(A, B);
  return worst;
}

(async () => {
  const port = L.argPort(8853);
  const fx = L.fixtures();
  const basePath = path.join(L.OUT, 'baseline.json');
  if (!fx.length || !fs.existsSync(basePath)) throw new Error('fixtures or baseline missing (run baseline.js first)');
  const baseline = JSON.parse(fs.readFileSync(basePath, 'utf8'));
  const server = await L.startServer(port);
  let browser;
  try {
    browser = await L.launch();
    const bakeAll = async page => {
      const out = {};
      for (const { name, project } of fx) {
        out[name] = await page.evaluate(project => {
          const app = R.scene(project);
          const res = app.pipeline.bake();
          const p = app.store.project, A = R.animation;
          const ev = p.sims.map(s => { const fr = []; for (let f = 0; f < p.length; f++) fr.push(A.evaluate(s.keys, f, p.length, p.loop, p.autoCurve)); return fr; });
          const evFB = p.sims.map(s => { const fr = []; for (let f = 0; f < p.length; f++) fr.push(A.evaluateFaceBones(s.keys, f, p.length, p.loop)); return fr; });
          const evF = p.sims.map(s => { const fr = []; for (let f = 0; f < p.length; f++) fr.push(A.evaluateFace(s.keys, f, p.length, p.loop)); return fr; });
          return { tracks: res.tracks, ev, evFB, evF, autoCurve: p.autoCurve, hadField: 'autoCurve' in project };
        }, project);
      }
      return out;
    };
    const o = await L.openEngine(browser, port, { orig: true });
    const before = await bakeAll(o.page);
    const n = await L.openEngine(browser, port, { orig: false });
    const now = await bakeAll(n.page);
    for (const { name } of fx) {
      const a = before[name], b = now[name], base = baseline.fixtures[name];
      add(`${name}: loads with the old curve (no autoCurve in the file -> 'legacy')`, !b.hadField && b.autoCurve === 'legacy', { hadField: b.hadField, autoCurve: b.autoCurve });
      const d = maxDiffTracks(a.tracks, b.tracks);
      add(`${name}: a) bake with R2-1's engine files = bake with the files from before (1e-6)`, d.worst <= 1e-6, d);
      const dEv = Math.max(maxDiffPoses(base.ev, b.ev), maxDiffPoses(base.evFB, b.evFB), maxDiffPoses(base.evF, b.evF));
      add(`${name}: b) evaluate / face bones / face sliders = the baseline, every frame (1e-6)`, dEv <= 1e-6, { worst: dEv });
      const dB = maxDiffTracks(base.tracks, b.tracks);
      add(`${name}: c) the whole bake = the baseline (info: other slices' changes count here too)`, true, dB);
    }
    const logs = [...o.logs, ...n.logs].filter(l => /pageerror|error/.test(l) && !/404|Failed to load resource/.test(l));
    add('no page errors', !logs.length, logs.slice(0, 4));
  } finally {
    if (browser) await browser.close();
    L.stopServer(server);
  }
  const ok = L.table(rows, 'R2-1 engine: old projects play exactly as before');
  fs.writeFileSync(path.join(L.OUT, 'engine_results.json'), JSON.stringify(rows, null, 1));
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
