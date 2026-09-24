// Renders web/img/logo.svg to PNGs for the Windows icon: node tools/make_icon.js
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');
const fs = require('fs'), path = require('path');
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new' });
  const p = await b.newPage();
  const svg = fs.readFileSync(path.join(__dirname, '..', 'web', 'img', 'logo.svg'), 'utf8');
  await p.setViewport({ width: 256, height: 256 });
  await p.setContent(`<body style="margin:0;background:transparent">${svg.replace('<svg ', '<svg width="256" height="256" ')}</body>`);
  await p.screenshot({ path: path.join(__dirname, '..', 'cache', 'logo_256.png'), omitBackground: true });
  await b.close();
})();
