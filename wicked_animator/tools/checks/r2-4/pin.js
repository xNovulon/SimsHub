// Test helper (R2-4): serve some web files from a local folder instead of the server, so a check can run against a
// stable copy of files other builders are still changing (only for development runs; final runs use the live tree).
//   const { pinFiles } = require('./pin.js');  H.open(port, { beforeLoad: page => pinFiles(page, dir) })
const fs = require('fs'), path = require('path');
const TYPES = { '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.html': 'text/html; charset=utf-8' };
function walk(dir, base = dir, out = new Map()) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    if (fs.statSync(p).isDirectory()) walk(p, base, out);
    else out.set('/' + path.relative(base, p).split(path.sep).join('/'), p);
  }
  return out;
}
async function pinFiles(page, dir) {
  if (!dir || !fs.existsSync(dir)) return new Map();
  const files = walk(dir);
  await page.setRequestInterception(true);
  page.on('request', req => {
    if (req.isInterceptResolutionHandled && req.isInterceptResolutionHandled()) return;
    let u;
    try { u = new URL(req.url()); } catch { return; }
    const p = u.pathname === '/' ? '/index.html' : u.pathname;
    if (req.method() !== 'GET' || !files.has(p)) return;
    req.respond({ status: 200, contentType: TYPES[path.extname(p)] || 'application/octet-stream', headers: { 'Cache-Control': 'no-store' }, body: fs.readFileSync(files.get(p)) }).catch(() => {});
  });
  return files;
}
module.exports = { pinFiles };
