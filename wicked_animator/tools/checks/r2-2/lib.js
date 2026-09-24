// Shared bits for the R2-2 checks.
//   stubMissing(page): while the other round-2 slices are still writing their modules, a module main.js imports
//   that is not on disk yet (e.g. curves.js) is answered with a harmless stand-in, so these checks can run. Only
//   files that do not exist are stubbed; nothing on disk is touched.
const fs = require('fs');
const path = require('path');
const H = require('../lib/harness.js');

const WEBJS = path.join(H.ROOT, 'web', 'js');

function stubSource(names) {
  const body = `const noop = () => {};
const make = () => new Proxy(function () {}, {
  get: (t, k) => (k === 'then' ? undefined : k === Symbol.toPrimitive ? () => '' : noop),
  construct: () => make(), apply: () => undefined });
`;
  return body + names.map(n => (n === 'default' ? 'export default make();' : `export const ${n} = make();`)).join('\n') + '\n';
}

// names imported from each relative module by the given file
function importsOf(file) {
  const src = fs.readFileSync(file, 'utf8');
  const out = {};
  for (const m of src.matchAll(/import\s*(?:(\w+)\s*,?\s*)?(?:\{([^}]*)\})?\s*from\s*['"]\.\/([\w/-]+\.js)['"]/g)) {
    const names = (m[2] || '').split(',').map(x => x.trim().split(/\s+as\s+/)[0]).filter(Boolean);
    if (m[1]) names.push('default');
    out[m[3]] = [...new Set([...(out[m[3]] || []), ...names])];
  }
  return out;
}

async function stubMissing(page, log = []) {
  const want = {};
  for (const f of ['main.js', 'steps.js', 'dialogs.js', 'inspector.js']) {
    const p = path.join(WEBJS, f);
    if (!fs.existsSync(p)) continue;
    for (const [mod, names] of Object.entries(importsOf(p))) want[mod] = [...new Set([...(want[mod] || []), ...names])];
  }
  page.on('request', req => {
    const u = new URL(req.url());
    const m = /^\/js\/([\w/-]+\.js)$/.exec(u.pathname);
    if (!m || !want[m[1]] || fs.existsSync(path.join(WEBJS, m[1]))) return;
    log.push(`stubbed missing module ${m[1]} (${want[m[1]].join(', ')})`);
    req.respond({ status: 200, contentType: 'application/javascript', body: stubSource(want[m[1]]) }).catch(() => {});
  });
}

async function open(port, opts = {}) {
  const stubbed = [];
  const r = await H.open(port, { ...opts, beforeLoad: async page => { await stubMissing(page, stubbed); if (opts.beforeLoad) await opts.beforeLoad(page); } });
  r.stubbed = stubbed;
  return r;
}

module.exports = { stubMissing, open };
