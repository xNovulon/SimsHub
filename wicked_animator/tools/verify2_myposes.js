// Verifier round 2: "My poses" in the browser's storage move to the server once (master_plan item 2.3). TEST port only.
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');
const PORT = process.env.ANIMATOR_PORT || '8777';
(async () => {
  const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', args: ['--use-angle=d3d11', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage();
  await page.evaluateOnNewDocument(() => { try { if (!sessionStorage.getItem('seeded')) { sessionStorage.setItem('seeded', '1'); localStorage.setItem('fsa.tourDone', 'true'); localStorage.setItem('fsa.myPoses', JSON.stringify([{ id: 'mine_v2', label: 'VERIFY2 old pose', group: 'solo', sims: [{ gender: 'FEMALE', pose: { rot: { b__Head__: [0, 0, 0, 1] } } }] }])); } } catch { /* */ } });
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0', timeout: 180000 });
  await page.waitForSelector('#loading.done', { timeout: 120000 });
  await new Promise(r => setTimeout(r, 1500));
  const r = await page.evaluate(async () => {
    const server = await (await fetch('/api/my_poses')).json();
    return { onServer: server.map(x => x.label), local: localStorage.getItem('fsa.myPoses'), inApp: (app.posePresets || []).filter(x => x.mine).map(x => x.label) };
  });
  console.log((r.onServer.includes('VERIFY2 old pose') && !r.local ? 'PASS' : 'FAIL') + ' item 2.3 old browser My poses move to the server once :: ' + JSON.stringify(r));
  await page.evaluate(async () => {
    const list = await (await fetch('/api/my_poses')).json();
    await fetch('/api/my_poses', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(list.filter(x => x.label !== 'VERIFY2 old pose')) });
    app.store.setDirty(false);
    await fetch('/api/recovery_clear?slot=test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  });
  await browser.close();
})();
