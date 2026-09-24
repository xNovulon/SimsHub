// node tools/shot.js [out.png] [width] [height] [script.js]
// Full-size screenshot of the running app with headless Chrome; the optional script runs in the page
// (as an async function body) before the shot, e.g. to play an animation or open a panel.
const path = require('path');
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');
const fs = require('fs');

(async () => {
  const out = process.argv[2] || path.join(__dirname, '..', 'cache', 'shot.png');
  const w = +(process.argv[3] || 1600), h = +(process.argv[4] || 900);
  const script = process.argv[5] ? fs.readFileSync(process.argv[5], 'utf8') : '';
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: 'new', protocolTimeout: 900000, args: ['--use-angle=d3d11', '--enable-webgl', '--ignore-gpu-blocklist', `--window-size=${w},${h}`],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
  const logs = [];
  page.on('console', m => logs.push(`[${m.type()}] ${m.text()}`));
  page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`));
  await page.goto('http://127.0.0.1:8765/', { waitUntil: 'networkidle0', timeout: 120000 });
  await page.waitForSelector('#loading.done', { timeout: 120000 }).catch(() => logs.push('[shot] loading never finished'));
  if (script) {
    try {
      const r = await page.evaluate(`(async () => { ${script} })()`);
      if (r !== undefined) logs.push('[script] ' + JSON.stringify(r));
    } catch (e) { logs.push('[script error] ' + e.message); }
  }
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: out });
  console.log(logs.join('\n'));
  console.log('saved', out);
  await browser.close();
})();
