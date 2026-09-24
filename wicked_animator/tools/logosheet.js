// Renders a sheet of logo options side by side: node tools/logosheet.js
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');
const fs = require('fs');
const path = require('path');
const defs = fs.readFileSync(path.join(__dirname, '..', 'cache', 'logos', 'defs.txt'), 'utf8');
const tile = '<rect x="2" y="2" width="60" height="60" rx="16" fill="url(#tile)"/><rect x="2.75" y="2.75" width="58.5" height="58.5" rx="15.3" fill="none" stroke="url(#rim)" stroke-width="1.5"/>';
const gem = (cx, top, w, hgt) => {
  const eq = top + hgt * 0.53, b = top + hgt, l = cx - w / 2, r = cx + w / 2;
  return `<path d="M${cx} ${top} ${l} ${eq} ${cx} ${eq}z" fill="url(#ul)"/><path d="M${cx} ${top} ${r} ${eq} ${cx} ${eq}z" fill="url(#ur)"/>` +
    `<path d="M${l} ${eq} ${cx} ${b} ${cx} ${eq}z" fill="url(#ll)"/><path d="M${r} ${eq} ${cx} ${b} ${cx} ${eq}z" fill="url(#lr)"/>`;
};
const OPTIONS = {
  A: `${tile}<g fill="none" stroke="#fff" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 50V15"/><path d="M17 15C26 27 36 40 46.5 50"/><path d="M46.5 50V30.5"/></g>${gem(46.5, 4, 12, 19.6)}`,
  C: `${tile}<defs><linearGradient id="brandU" x1="13" y1="12" x2="51" y2="52" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#ff6fb0"/><stop offset="1" stop-color="#9b5cf6"/></linearGradient></defs><g fill="none" stroke="url(#brandU)" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 50V15"/><path d="M17 15C26 27 36 40 46.5 50"/><path d="M46.5 50V30.5"/></g>${gem(46.5, 4, 12, 19.6)}`,
  D: `<rect x="2" y="2" width="60" height="60" rx="16" fill="url(#tile)"/><rect x="2.75" y="2.75" width="58.5" height="58.5" rx="15.3" fill="none" stroke="url(#rim)" stroke-width="1.5"/>${gem(32, 6, 34, 53)}<g fill="none" stroke="#fff" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"><path d="M24.5 39V24M24.5 24 39.5 39M39.5 39V24"/></g>`,
  E: `<rect x="2" y="2" width="60" height="60" rx="16" fill="url(#brand)"/><g fill="none" stroke="#fff" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 50V15"/><path d="M17 15C26 27 36 40 46.5 50"/><path d="M46.5 50V30.5"/></g><g transform="translate(0 0)"><path d="M46.5 4 40.5 14.4 46.5 14.4z" fill="#ffffff"/><path d="M46.5 4 52.5 14.4 46.5 14.4z" fill="#ffe3f0"/><path d="M40.5 14.4 46.5 23.6 46.5 14.4z" fill="#f3dcff"/><path d="M52.5 14.4 46.5 23.6 46.5 14.4z" fill="#d7b8ff"/></g>`,
  F: `${tile}<text x="31" y="50" text-anchor="middle" font-family="Plus Jakarta Sans, Segoe UI, sans-serif" font-weight="800" font-size="44" fill="#fff">N</text>${gem(47.5, 4, 11, 18)}`,
};
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new' });
  const p = await b.newPage();
  await p.setViewport({ width: 1000, height: 330 });
  const cells = Object.entries(OPTIONS).map(([k, body]) => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs>${defs}</defs>${body}</svg>`;
    fs.writeFileSync(path.join(__dirname, '..', 'cache', 'logos', `logo_${k}.svg`), svg);
    return `<div style="display:flex;flex-direction:column;align-items:center;gap:12px"><div style="width:150px;height:150px">${svg}</div>
      <div style="display:flex;gap:10px;align-items:center"><div style="width:40px;height:40px">${svg}</div><div style="width:20px;height:20px">${svg}</div></div>
      <div style="color:#fff;font:800 22px Segoe UI">${k}</div></div>`;
  }).join('');
  await p.setContent(`<body style="margin:0;background:#0b0a10;display:flex;gap:36px;padding:24px 28px;font-family:Segoe UI">${cells}</body>`);
  await p.screenshot({ path: path.join(__dirname, '..', 'cache', 'logo_options.png') });
  await b.close();
})();
