// R2-1 debugging helper: open the app (harness, memory mode) and run a page script from a file.
//   node tools/checks/r2-1/debug.js --port 8851 <script.js>     (the script's text is the body of an async function)
'use strict';
const fs = require('fs');
const H = require('../lib/harness.js');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const file = process.argv[process.argv.length - 1];
  const body = fs.readFileSync(file, 'utf8');
  const { browser, page, logs } = await H.open(port, { w: 1366, h: 768, memory: true });
  try {
    const out = await page.evaluate(new Function(`return (async () => { ${body} })();`));
    console.log(JSON.stringify(out, null, 1).slice(0, 6000));
    console.log('logs:', JSON.stringify(logs.filter(l => l.type !== 'log').slice(0, 12), null, 1));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
