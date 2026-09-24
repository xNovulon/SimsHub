// node tools/grab.js out.png w h script.js elementId : runs the script, then saves the data URL found in #elementId's href
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');
const fs = require('fs');
(async () => {
  const [out, w, h, scriptPath, id] = process.argv.slice(2);
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', protocolTimeout: 900000, args: ['--use-angle=d3d11', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const p = await b.newPage();
  await p.setViewport({ width: +w, height: +h });
  const logs = [];
  p.on('pageerror', e => logs.push('[pageerror] ' + e.message));
  await p.goto('http://127.0.0.1:8765/', { waitUntil: 'networkidle0', timeout: 180000 });
  await p.waitForSelector('#loading.done', { timeout: 180000 });
  const r = await p.evaluate(`(async () => { ${fs.readFileSync(scriptPath, 'utf8')} })()`).catch(e => 'ERR ' + e.message);
  const data = await p.evaluate(i => document.getElementById(i)?.href || '', id);
  if (data.startsWith('data:image/png;base64,')) fs.writeFileSync(out, Buffer.from(data.split(',')[1], 'base64'));
  console.log(JSON.stringify(r), logs.join('\n'), data ? 'saved ' + out : 'no image');
  await b.close();
})();
