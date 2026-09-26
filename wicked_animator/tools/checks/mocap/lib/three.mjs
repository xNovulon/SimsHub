// Lets Node import the app's ES modules (web/js/**), which import 'three' by its bare name (index.html maps it to a
// CDN). The same three.js version the app uses (0.160.0) is looked up, in this order:
//   WA_THREE (a three.module.js file, or a folder with node_modules/three), a 'three' Node can already find,
//   <root>/cache/checks/_vendor/node_modules/three - installed there once with npm when none is found (cache/ is not
//   in git).
// Usage (top of a check):  import { useThree } from './lib/three.mjs'; await useThree();  then dynamic import()s.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire, register } from 'node:module';
import { execSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(HERE, '..', '..', '..', '..');
export const WEB = path.join(ROOT, 'web');
const VERSION = '0.160.0';

function findThree() {
  const env = process.env.WA_THREE;
  if (env) {
    if (fs.statSync(env).isFile()) return env;
    for (const p of [path.join(env, 'node_modules', 'three', 'build', 'three.module.js'), path.join(env, 'build', 'three.module.js')]) if (fs.existsSync(p)) return p;
  }
  for (const base of [process.cwd(), HERE, ROOT]) {
    try {
      const main = createRequire(path.join(base, 'x.js')).resolve('three');        // .../three/build/three.cjs
      const f = path.join(path.dirname(main), 'three.module.js');
      if (fs.existsSync(f)) return f;
    } catch { /* next */ }
  }
  const vendor = path.join(ROOT, 'cache', 'checks', '_vendor');
  const file = path.join(vendor, 'node_modules', 'three', 'build', 'three.module.js');
  if (!fs.existsSync(file)) {
    fs.mkdirSync(vendor, { recursive: true });
    console.log(`(installing three@${VERSION} into ${vendor} for the checks - once)`);
    execSync(`npm install --no-save --no-audit --no-fund --prefix "${vendor}" three@${VERSION}`, { stdio: 'inherit' });
  }
  return file;
}

let done = false;
export async function useThree() {
  if (done) return;
  const file = findThree();
  const url = pathToFileURL(file).href;
  // 'three/addons/...' -> examples/jsm/... (index.html's importmap does the same on the CDN)
  const addons = pathToFileURL(path.join(path.dirname(path.dirname(file)), 'examples', 'jsm')).href + '/';
  const web = pathToFileURL(path.join(WEB, 'js')).href + '/';
  // the app's own files are ES modules (the browser reads them so); older Node versions would guess CommonJS
  register('data:text/javascript,' + encodeURIComponent(`
    export async function resolve(spec, ctx, next) {
      if (spec === 'three') return { url: ${JSON.stringify(url)}, shortCircuit: true };
      if (spec.startsWith('three/addons/')) return { url: ${JSON.stringify(addons)} + spec.slice(13), shortCircuit: true };
      return next(spec, ctx);
    }
    export async function load(url, ctx, next) {
      if (url.startsWith(${JSON.stringify(web)}) && url.endsWith('.js')) {
        const r = await next(url, { ...ctx, format: 'module' });
        return { ...r, format: 'module' };
      }
      return next(url, ctx);
    }`));
  done = true;
}

export const webUrl = rel => pathToFileURL(path.join(WEB, rel)).href;
export const threeFile = () => findThree();
