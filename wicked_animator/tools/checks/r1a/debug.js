// R1-A: ad-hoc probe - run a function body (file given as argv) in the engine page and print its JSON result.
//   node tools/checks/r1a/debug.js --port 8841 <probe.js>
'use strict';
const fs = require('fs');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const file = process.argv[process.argv.length - 1];
  const body = fs.readFileSync(file, 'utf8');
  const fx = Object.fromEntries(L.fixtures().map(f => [f.name, f.project]));
  const server = await L.startServer(port);
  let browser;
  try {
    browser = await L.launch();
    const { page, logs } = await L.open(browser, port, { kind: 'engine' });
    const res = await page.evaluate(new Function('FX', `return (async () => { ${body} })();`), fx);
    console.log(JSON.stringify(res, null, 1));
    if (logs.length) console.log(logs.slice(0, 10));
  } finally {
    if (browser) await browser.close();
    L.stopServer(server);
  }
})().catch(e => { console.error(e); process.exit(1); });
