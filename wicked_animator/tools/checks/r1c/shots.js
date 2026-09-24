// Screenshots of Home and every step at 1366x768 and 1920x1080 (plus Magic on the double bed), and the time to
// #loading.done under webdriver. Used for the "before" set (run before R1-C's edits) and the "after" set.
//   node tools/checks/r1c/shots.js --port 8843 --tag before
const path = require('path'), fs = require('fs');
const L = require('./lib.js');

const PORT = L.argPort();
const TAG = process.argv.includes('--tag') ? process.argv[process.argv.indexOf('--tag') + 1] : 'after';
const DIR = path.join(L.OUT, TAG);
const STEPS = ['scene', 'pose', 'motion', 'body', 'face', 'sounds', 'details', 'share', 'library'];

async function readyTime(browser) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1366, height: 768 });
  await page.evaluateOnNewDocument(() => {
    const t = () => { const l = document.getElementById('loading'); if (l && l.classList.contains('done') && !window.__doneAt) window.__doneAt = performance.now(); };
    new MutationObserver(t).observe(document, { subtree: true, attributes: true, attributeFilter: ['class'], childList: true });
  });
  await page.setRequestInterception(true);
  page.on('request', r => (r.method() === 'POST' ? r.respond({ status: 200, contentType: 'application/json', body: '{"ok":true}' }) : r.continue()));
  await page.goto(`http://127.0.0.1:${PORT}/?slot=test`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.__doneAt, { timeout: 120000 });
  const ms = await page.evaluate(() => window.__doneAt);
  await page.close();
  return ms;
}

(async () => {
  const server = await L.startServer(PORT);
  const out = { tag: TAG, readyMs: [] };
  try {
    for (const [w, h] of [[1366, 768], [1920, 1080]]) {
      const { browser, page, logs } = await L.open(PORT, { w, h, beforeLoad: pg => pg.evaluateOnNewDocument(() => { try { localStorage.setItem('fsa.tourDone', 'true'); } catch { } }) });
      if (w === 1366) { await readyTime(browser); for (let i = 0; i < 3; i++) out.readyMs.push(Math.round(await readyTime(browser))); }
      await L.sleep(1500);
      await L.shot(page, path.join(DIR, `home_${w}.png`));
      await page.evaluate(() => { const b = [...document.querySelectorAll('#home button')].find(x => /editor|Continue/.test(x.textContent)); if (b) b.click(); else document.getElementById('home').classList.add('hidden'); });
      await page.waitForFunction(() => window.app && window.app.posePresets && window.app.posePresets.length, { timeout: 60000 });
      for (const s of STEPS) {
        await page.evaluate(st => window.app.showStep(st), s);
        await L.sleep(s === 'face' ? 1400 : 700);
        await L.shot(page, path.join(DIR, `step_${s}_${w}.png`));
      }
      // Magic on the double bed
      await page.evaluate(() => window.app.showStep('scene'));
      const r = await page.evaluate(async () => {
        const m = await import('/js/magic.js');
        await m.makeMagic(window.app, { recipe: 'cowgirl', place: 'double_bed', intensity: 0.5, seconds: 3 });
        window.app.setPlaying(false); window.app.setFrame(0); window.app.showcase(false);
        return true;
      });
      await L.sleep(1800);
      await L.shot(page, path.join(DIR, `magic_double_bed_${w}.png`));
      out[`logs_${w}`] = logs.filter(x => /error|pageerror|polish/i.test(x)).slice(0, 20);
      await browser.close();
    }
  } finally { L.stopServer(server); }
  fs.mkdirSync(DIR, { recursive: true });
  fs.writeFileSync(path.join(DIR, 'shots.json'), JSON.stringify(out, null, 1));
  console.log(JSON.stringify(out, null, 1));
})().catch(e => { console.error(e); process.exit(1); });
