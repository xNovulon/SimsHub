const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');
const fs = require('fs');
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new' });
  const p = await b.newPage();
  await p.setViewport({ width: 640, height: 220 });
  const svg = fs.readFileSync('web/img/logo.svg', 'utf8');
  await p.setContent(`<body style="margin:0;background:#0b0a10;display:flex;gap:28px;align-items:center;padding:24px;font-family:Segoe UI">
    <div style="width:160px;height:160px">${svg}</div><div style="width:48px;height:48px">${svg}</div><div style="width:24px;height:24px">${svg}</div>
    <div style="color:#fff"><div style="color:#a39bb2;font-weight:700;font-size:14px">Novulon's</div><div style="font-size:22px;font-weight:800;background:linear-gradient(135deg,#ff4f9a,#8b5cf6);-webkit-background-clip:text;color:transparent">Wicked Animator</div></div></body>`);
  await p.screenshot({ path: 'cache/logo_check.png' });
  await b.close();
})();
