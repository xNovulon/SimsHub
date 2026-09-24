// Diagnostic: load the app and print its console, errors and loading state after a while.
//   node tools/checks/r1c/diag_boot.js --port 8843 [seconds]
const L = require('./lib.js');
const PORT = L.argPort();
const secs = +(process.argv.slice(2).find(a => /^\d+$/.test(a) && +a < 300) || 15);
(async () => {
  const server = await L.startServer(PORT);
  try {
    const { browser, page, logs } = await L.open(PORT, { wait: false });
    page.on('requestfailed', r => logs.push(`[requestfailed] ${r.url()} ${r.failure() && r.failure().errorText}`));
    page.on('response', r => { if (r.status() >= 400) logs.push(`[http ${r.status()}] ${r.url()}`); });
    await L.sleep(secs * 1000);
    const st = await page.evaluate(() => ({ done: document.getElementById('loading')?.className, text: document.getElementById('loading-text')?.textContent,
      splash: !!document.getElementById('splash'), app: !!window.app, home: document.getElementById('home')?.className, step: document.body.dataset.step }));
    console.log(JSON.stringify(st));
    console.log(logs.join('\n'));
    await browser.close();
  } finally { L.stopServer(server); }
})().catch(e => { console.error(e); process.exit(1); });
