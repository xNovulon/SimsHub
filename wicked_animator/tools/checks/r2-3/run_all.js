// R2-3: every check of the slice, one after the other, against a running server (the slice's own: 8853).
//   node tools/checks/r2-3/run_all.js --port 8853 [--quick]
// Each script prints its own PASS/FAIL table; this prints the summary and exits 0 only when all of them passed.
'use strict';
const cp = require('child_process');
const path = require('path');
const fs = require('fs');
const L = require('./lib');

const port = String(L.argPort());
const quick = process.argv.includes('--quick');
const RUNS = [
  ['smoke', ['smoke.js']],
  ['old projects bake the same', ['baseline.js', '--compare']],
  ['jiggle strength', ['jiggle.js']],
  ['spots, sit, lie, Magic on furniture (3.9)', ['places.js', ...(quick ? ['--quick'] : [])]],
  ['look at, tremble, follow-through (6.5)', ['motions.js']],
  ['see-through, bones, clipping (7.8)', ['xray_clip.js', ...(quick ? ['--quick'] : [])]],
  ['other bodies and hair (8.6, 9.5)', ['bodies_hair.js']],
  ['hair on every Tray sim\'s head', ['hair_fit.js']],
];
const summary = [];
for (const [name, [file, ...args]] of RUNS) {
  const t0 = Date.now();
  const r = cp.spawnSync('node', [path.join(__dirname, file), '--port', port, ...args], { encoding: 'utf8', timeout: 3000000 });
  const out = (r.stdout || '') + (r.stderr || '');
  fs.writeFileSync(path.join(L.OUT, `run_${file.replace(/\.js$/, '')}.log`), out);
  const tail = (out.match(/(\d+) PASS, (\d+) FAIL/g) || []).pop() || 'no table';
  summary.push({ name: `${name} (${file})`, ok: r.status === 0, detail: `${tail} · ${Math.round((Date.now() - t0) / 1000)} s` });
  process.stdout.write(`${r.status === 0 ? 'PASS' : 'FAIL'}  ${name}: ${tail}\n`);
}
process.exitCode = L.table(summary, 'R2-3: all checks') ? 0 : 1;
