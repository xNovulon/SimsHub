// A test-only front door for R2-5 while other round-2 slices are mid-edit: serves web/ as it is, except the files
// listed below, which come from R2-1's round-start copies (cache/checks/r2-1/orig) while R2-1's own versions are
// half-written (main.js importing modules that do not exist yet). Every /api/ request goes to the real test server.
// Nothing is written anywhere.
//   node tools/checks/r2-5/overlay.js --port 8872 --api 8855 [--orig main.js,timeline.js,...|--orig r2-1] [--live]
const http = require('http');
const fs = require('fs');
const path = require('path');

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const PORT = +arg('--port', 8872), API = +arg('--api', 8855);
if ([8765, 8766, 8777, 8802, 8804].includes(PORT) || [8765, 8766, 8777, 8802, 8804].includes(API)) throw new Error('not our port');
const ROOT = path.join(__dirname, '..', '..', '..');
const WEB = path.join(ROOT, 'web');
const ORIG = path.join(ROOT, 'cache', 'checks', 'r2-1', 'orig');
// R2-1's files (build plan R2-1 "Owns") that exist in its round-start copy
const R21 = ['index.html', 'css/app.css', 'css/motion.css', 'js/main.js', 'js/timeline.js', 'js/animation.js', 'js/state.js', 'js/api.js',
  'js/thumbs.js', 'js/tour.js', 'js/inspector/key.js', 'js/steps/pose.js', 'js/dialogs/import.js'];
let orig = arg('--orig', 'r2-1');
orig = argv.includes('--live') ? [] : orig === 'r2-1' ? R21 : orig.split(',').map(x => x.trim()).filter(Boolean);
const OVERRIDE = new Set(orig.filter(f => fs.existsSync(path.join(ORIG, f))));
const FEATURES = arg('--features', null) ? arg('--features').split(',').map(x => x.trim()).filter(Boolean) : null;
const NO_RECOVERY = argv.includes('--no-recovery');
const TYPES = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2' };

http.createServer((req, res) => {
  const u = new URL(req.url, `http://127.0.0.1:${PORT}`);
  // --features a.js,b.css: only these feature files (other slices' features left out, to test R2-5 on its own)
  if (FEATURES && u.pathname === '/api/features') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ js: FEATURES.filter(f => f.endsWith('.js')), css: FEATURES.filter(f => f.endsWith('.css')) }));
    return;
  }
  // --no-recovery: no crash-recovery offer (another test run may have left one in the shared test slot)
  if (NO_RECOVERY && req.method === 'GET' && u.pathname === '/api/recovery') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    res.end('{}');
    return;
  }
  if (u.pathname.startsWith('/api/')) {
    const headers = { ...req.headers, host: `127.0.0.1:${API}` };
    if (headers.origin) headers.origin = `http://127.0.0.1:${API}`;
    if (headers.referer) headers.referer = headers.referer.replace(`:${PORT}`, `:${API}`);
    const p = http.request({ hostname: '127.0.0.1', port: API, path: u.pathname + u.search, method: req.method, headers }, r => {
      res.writeHead(r.statusCode, r.headers);
      r.pipe(res);
    });
    p.on('error', e => { res.writeHead(502); res.end(String(e.message)); });
    req.pipe(p);
    return;
  }
  let rel = decodeURIComponent(u.pathname).replace(/^\/+/, '') || 'index.html';
  const file = OVERRIDE.has(rel) ? path.join(ORIG, rel) : path.join(WEB, rel);
  if (!path.resolve(file).startsWith(path.resolve(OVERRIDE.has(rel) ? ORIG : WEB)) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    res.writeHead(404, { 'Content-Type': 'text/plain' }); res.end('not found'); return;
  }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
  fs.createReadStream(file).pipe(res);
}).listen(PORT, '127.0.0.1', () => console.log(`overlay on ${PORT} -> api ${API}; from R2-1's round-start copies: ${[...OVERRIDE].join(', ') || 'none'}; features: ${FEATURES ? FEATURES.join(',') : 'all'}; recovery: ${NO_RECOVERY ? 'hidden' : 'as is'}`));
