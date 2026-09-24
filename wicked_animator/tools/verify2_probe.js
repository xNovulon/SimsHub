// Verifier probe: runs a page script file (async function body) against the test server and prints its result.
//   node tools/verify1_probe.js <script.js> [width] [height] [shot.png]
const path = require('path'), fs = require('fs');
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');
const PORT = process.env.ANIMATOR_PORT || '8777';
(async () => {
  const script = fs.readFileSync(process.argv[2], 'utf8');
  const w = +(process.argv[3] || 1600), h = +(process.argv[4] || 900), out = process.argv[5];
  const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', protocolTimeout: 900000,
    args: ['--use-angle=d3d11', '--enable-webgl', '--ignore-gpu-blocklist', `--window-size=${w},${h}`] });
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
  const logs = [];
  page.on('console', m => { if (['error', 'warning', 'warn'].includes(m.type())) logs.push(`[${m.type()}] ${m.text()}`); });
  page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`));
  if (!process.env.TOUR) await page.evaluateOnNewDocument(() => { try { localStorage.setItem('fsa.tourDone', 'true'); localStorage.removeItem('fsa.autosave'); } catch { /* */ } });
  else await page.evaluateOnNewDocument(() => { try { localStorage.removeItem('fsa.tourDone'); localStorage.removeItem('fsa.autosave'); } catch { /* */ } });
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0', timeout: 180000 });
  await page.waitForSelector('#loading.done', { timeout: 120000 });
  try {
    const r = await page.evaluate(`(async () => { ${script} })()`);
    console.log(JSON.stringify(r, null, 1));
  } catch (e) { console.log('script error', e.message); }
  if (out) { await new Promise(r => setTimeout(r, 500)); await page.screenshot({ path: out }); console.log('saved', out); }
  console.log(logs.join('\n'));
  await page.evaluate(() => { try { app.store.setDirty(false); fetch('/api/recovery_clear?slot=test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); } catch { /* */ } });
  await new Promise(r => setTimeout(r, 300));
  await browser.close();
})();
