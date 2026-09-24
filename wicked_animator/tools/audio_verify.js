// Independent browser check of backend/eaaudio.py output (see tools/audio_verify.py).
//   node tools/audio_verify.js files   decode every file of cache/audio/verify/manifest.json in headless Chrome
//                                      (fetched over HTTP), measure it -> cache/audio/verify/chrome.json
//   node tools/audio_verify.js route   start the app's real HTTP handler on a free port, load /js/audio.js
//                                      (SoundPlayer, the app's own code) and play every sound through it
//                                      -> cache/audio/verify/route.json
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');
const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const ROOT = path.join(__dirname, '..');
const OUT = path.join(ROOT, 'cache', 'audio', 'verify');
const FILES = path.join(OUT, 'files');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const TYPES = { '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.html': 'text/html' };

// ---------------------------------------------------------------- measurements (run inside the page)
const MEASURE = `
window.fft = function (re, im) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { [re[i], re[j]] = [re[j], re[i]]; [im[i], im[j]] = [im[j], im[i]]; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = -2 * Math.PI / len, wr = Math.cos(ang), wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < len / 2; k++) {
        const a = i + k, b = a + len / 2;
        const tr = re[b] * cr - im[b] * ci, ti = re[b] * ci + im[b] * cr;
        re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
        const t = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = t;
      }
    }
  }
};
window.measure = function (ab) {
  const n = ab.length, sr = ab.sampleRate, C = ab.numberOfChannels;
  const mono = new Float64Array(n);
  let nan = 0, peak = 0, clipRuns = 0;
  for (let c = 0; c < C; c++) {
    const d = ab.getChannelData(c);
    let run = 0;
    for (let i = 0; i < n; i++) {
      const v = d[i];
      if (!Number.isFinite(v)) { nan++; continue; }
      mono[i] += v / C;
      const a = Math.abs(v);
      if (a > peak) peak = a;
      if (a >= 0.999) { if (++run === 3) clipRuns++; } else run = 0;
    }
  }
  let e = 0;
  for (let i = 0; i < n; i++) e += mono[i] * mono[i];
  const k150 = Math.min(n, Math.round(0.15 * sr));
  let e150 = 0;
  for (let i = 0; i < k150; i++) e150 += mono[i] * mono[i];
  // 10 ms RMS envelope
  const win = Math.max(1, Math.round(0.01 * sr));
  const env = [];
  for (let i = 0; i + win <= n; i += win) {
    let s = 0;
    for (let k = i; k < i + win; k++) s += mono[k] * mono[k];
    env.push(Math.sqrt(s / win));
  }
  const envMax = Math.max(1e-12, ...env);
  const activeIdx = env.map((v, i) => [v, i]).filter(([v]) => v > envMax * 0.01).map(([, i]) => i);   // within 40 dB
  const act = activeIdx.map(i => env[i]);
  const mean = act.reduce((a, b) => a + b, 0) / Math.max(1, act.length);
  const sd = Math.sqrt(act.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, act.length));
  let lead = env.findIndex(v => v > envMax * 0.1);
  // zero-crossing rate over active windows
  let zc = 0, zn = 0;
  for (const w of activeIdx) {
    for (let k = w * win + 1; k < (w + 1) * win; k++) { if ((mono[k] >= 0) !== (mono[k - 1] >= 0)) zc++; zn++; }
  }
  // spectrum: 2048-point Hann frames centred in active windows (at most 120 of them)
  const N = 2048, hann = new Float64Array(N);
  for (let i = 0; i < N; i++) hann[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / N);
  const step = Math.max(1, Math.floor(activeIdx.length / 120));
  const lo = Math.max(1, Math.round(100 * N / sr)), hi = Math.min(N / 2, Math.round(8000 * N / sr));
  let cw = 0, cs = 0; const flats = [];
  for (let a = 0; a < activeIdx.length; a += step) {
    const start = Math.min(Math.max(0, activeIdx[a] * win + (win >> 1) - N / 2), Math.max(0, n - N));
    if (n < N) break;
    const re = new Float64Array(N), im = new Float64Array(N);
    for (let i = 0; i < N; i++) re[i] = mono[start + i] * hann[i];
    fft(re, im);
    let pw = 0, pf = 0, lg = 0, pb = 0;
    for (let k = 1; k < N / 2; k++) { const p = re[k] * re[k] + im[k] * im[k]; pw += p; pf += p * k * sr / N; }
    for (let k = lo; k < hi; k++) { const p = re[k] * re[k] + im[k] * im[k] + 1e-20; lg += Math.log(p); pb += p; }
    if (pw > 0) { cs += pf; cw += pw; }
    if (pb > 1e-15) flats.push(Math.exp(lg / (hi - lo)) / (pb / (hi - lo)));
  }
  flats.sort((a, b) => a - b);
  const head = [];
  for (let c = 0; c < C; c++) head.push(Array.from(ab.getChannelData(c).slice(0, 256)));
  return {
    length: n, sampleRate: sr, channels: C, duration: n / sr, nan, peak, clip_runs: clipRuns,
    rms: Math.sqrt(e / Math.max(1, n)), rms_db: 20 * Math.log10(Math.sqrt(e / Math.max(1, n)) + 1e-12),
    early150: e > 0 ? e150 / e : 0, env_cv: mean > 0 ? sd / mean : 0, active: act.length * win / sr,
    lead_ms: lead < 0 ? null : lead * 10, zcr: zn ? zc / zn : 0, centroid: cw ? cs / cw : 0,
    flatness: flats.length ? flats[flats.length >> 1] : null, head,
  };
};
`;

function staticServer(dir) {
  return new Promise(resolve => {
    const srv = http.createServer((req, res) => {
      const u = decodeURIComponent(new URL(req.url, 'http://x').pathname);
      if (u === '/' || u === '/index.html') { res.writeHead(200, { 'Content-Type': 'text/html' }); return res.end('<!doctype html><title>verify</title>'); }
      const f = path.join(dir, path.basename(u));
      if (!fs.existsSync(f)) { res.writeHead(404); return res.end(); }
      const body = fs.readFileSync(f);
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream', 'Content-Length': body.length });
      res.end(body);
    });
    srv.listen(0, '127.0.0.1', () => resolve(srv));
  });
}

async function launch() {
  return puppeteer.launch({ executablePath: CHROME, headless: 'new', protocolTimeout: 900000,
    args: ['--autoplay-policy=no-user-gesture-required'] });
}

async function files() {
  const man = JSON.parse(fs.readFileSync(path.join(OUT, 'manifest.json'), 'utf8'));
  const srv = await staticServer(FILES);
  const port = srv.address().port;
  const browser = await launch();
  const page = await browser.newPage();
  await page.goto(`http://127.0.0.1:${port}/index.html`);
  await page.evaluate(MEASURE);
  const results = [];
  for (const it of man.files) {
    const r = await page.evaluate(async (file, sr, ch) => {
      const out = { file };
      try {
        const resp = await fetch('/' + encodeURIComponent(file));
        out.http = resp.status; out.ctype = resp.headers.get('content-type');
        const buf = await resp.arrayBuffer();
        // 1) at the file's own rate: exact length, no resampling
        const off = new OfflineAudioContext(Math.max(1, ch), 1, sr);
        const ab = await off.decodeAudioData(buf.slice(0));
        Object.assign(out, measure(ab));
        // 2) like the app: a normal AudioContext at the device rate (resamples)
        const live = new AudioContext();
        const ab2 = await live.decodeAudioData(buf.slice(0));
        out.dur48 = ab2.duration; out.live_rate = live.sampleRate; out.live_len = ab2.length;
        await live.close();
        out.ok = true;
      } catch (e) { out.ok = false; out.error = String(e && (e.message || e)); }
      return out;
    }, it.file, it.sample_rate, it.channels);
    results.push(r);
    process.stdout.write(r.ok ? '.' : 'X');
  }
  const version = await browser.version();
  await browser.close();
  srv.close();
  fs.writeFileSync(path.join(OUT, 'chrome.json'), JSON.stringify({ chrome: version, results }));
  console.log('\n' + version, 'decoded', results.filter(r => r.ok).length, 'of', results.length);
}

function freePort() {
  return new Promise(resolve => { const s = http.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); }); });
}

async function route() {
  const man = JSON.parse(fs.readFileSync(path.join(OUT, 'manifest.json'), 'utf8'));
  const names = [...new Set(man.sounds.filter(s => s.set !== 'odd_clip').map(s => s.name))];
  // odd characters in names: the route must not mangle them
  names.push('WET_PL_1 ', 'plaps_normal', 'VO_ROMANTIC_KISS_SUCC_X', 'no_such_sound_xyz');
  const port = await freePort();
  const py = spawn('python', [path.join(__dirname, 'audio_verify.py'), 'serve', String(port)], { cwd: ROOT });
  let log = '';
  py.stdout.on('data', d => { log += d; }); py.stderr.on('data', d => { log += d; });
  for (let i = 0; i < 100 && !log.includes('serving'); i++) await new Promise(r => setTimeout(r, 200));
  const browser = await launch();
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${port}/api/does_not_exist`);
  await page.evaluate(MEASURE);
  // the list the app offers
  const list = await page.evaluate(async () => (await (await fetch('/api/sounds')).json()).map(s => s.name));
  const results = await page.evaluate(async (names, list) => {
    const { SoundPlayer } = await import('/js/audio.js');
    const player = new SoundPlayer();
    player.muted = false;
    player.ensure = () => player.ctx;     // an OfflineAudioContext can't resume() before rendering; the rest is the app's code
    const inList = new Set(list);
    const out = [];
    for (const name of names) {
      const r = { name, in_api_sounds: inList.has(name) };
      const t0 = performance.now();
      try {
        const resp = await fetch('/api/sound?name=' + encodeURIComponent(name));
        r.http = resp.status; r.ctype = resp.headers.get('content-type'); r.cache = resp.headers.get('cache-control');
        r.bytes = (await resp.arrayBuffer()).byteLength;
        if (!resp.ok) r.body = r.bytes < 400 ? await (await fetch('/api/sound?name=' + encodeURIComponent(name))).text() : '';
      } catch (e) { r.fetch_error = String(e); }
      r.fetch_ms = Math.round(performance.now() - t0);
      // the app's own path: SoundPlayer.load -> AudioBuffer, then play() through gain/panner/master
      const off = new OfflineAudioContext(2, 48000 * 30, 48000);
      player.ctx = off;
      player.master = off.createGain(); player.master.gain.value = player.volume; player.master.connect(off.destination);
      const b = await player.load(name);
      r.loaded = !!b;
      if (b) {
        r.buf_duration = b.duration;
        const played = await player.play(name, { force: false, pan: 0.3, gain: 0.9 });
        r.played = played;
        const rendered = await off.startRendering();
        const m = measure(rendered);
        r.out_peak = m.peak; r.out_rms_db = m.rms_db;
        // audible = something above -60 dBFS in the rendered output
        r.audible = m.peak > 0.001;
      }
      out.push(r);
    }
    return out;
  }, names, list);
  const version = await browser.version();
  await browser.close();
  py.kill();
  fs.writeFileSync(path.join(OUT, 'route.json'), JSON.stringify({ chrome: version, port, page_errors: errors, api_sounds: list.length, results }, null, 1));
  console.log(version, 'route: loaded', results.filter(r => r.loaded).length, 'audible', results.filter(r => r.audible).length, 'of', results.length, 'page errors', errors.length);
  if (errors.length) console.log(errors);
}

// node tools/audio_verify.js dir <folder>: decode <folder>/manifest.json's files, save Chrome's PCM as <file>.f32
// (channel-planar float32) + <folder>/chrome.json
async function dir(folder) {
  const man = JSON.parse(fs.readFileSync(path.join(folder, 'manifest.json'), 'utf8'));
  const srv = await staticServer(folder);
  const port = srv.address().port;
  const browser = await launch();
  const page = await browser.newPage();
  await page.goto(`http://127.0.0.1:${port}/index.html`);
  await page.evaluate(MEASURE);
  const results = [];
  for (const it of man) {
    const r = await page.evaluate(async (file, sr, ch) => {
      const out = { file };
      try {
        const buf = await (await fetch('/' + encodeURIComponent(file))).arrayBuffer();
        const ab = await new OfflineAudioContext(ch, 1, sr).decodeAudioData(buf);
        Object.assign(out, measure(ab));
        delete out.head;
        const parts = [];
        for (let c = 0; c < ab.numberOfChannels; c++) {
          const u8 = new Uint8Array(ab.getChannelData(c).slice().buffer);
          let s = '';
          for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
          parts.push(btoa(s));
        }
        out.pcm = parts; out.ok = true;
      } catch (e) { out.ok = false; out.error = String(e && (e.message || e)); }
      return out;
    }, it.file, it.sample_rate, it.channels);
    if (r.pcm) {
      fs.writeFileSync(path.join(folder, it.file + '.f32'), Buffer.concat(r.pcm.map(b => Buffer.from(b, 'base64'))));
      delete r.pcm;
    }
    results.push(r);
  }
  await browser.close();
  srv.close();
  fs.writeFileSync(path.join(folder, 'chrome.json'), JSON.stringify(results, null, 1));
  console.log('decoded', results.filter(r => r.ok).length, 'of', results.length);
}

(async () => {
  const cmd = process.argv[2] || 'files';
  if (cmd === 'dir') await dir(process.argv[3]);
  else if (cmd === 'files') await files();
  else if (cmd === 'route') await route();
})().catch(e => { console.error(e); process.exit(1); });
