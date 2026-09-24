// node tools/camtest.js : drives the camera with a real mouse and keyboard in headless Chrome and checks it.
const path = require('path');
const puppeteer = require('C:/Users/basim/Tools/asws/node_modules/puppeteer-core');

(async () => {
  const out = path.join(__dirname, '..', 'cache');
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: 'new', args: ['--use-angle=d3d11', '--enable-webgl', '--ignore-gpu-blocklist', '--window-size=1600,900'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const logs = [];
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') logs.push(`[${m.type()}] ${m.text()}`); });
  page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`));
  await page.goto('http://127.0.0.1:8765/', { waitUntil: 'networkidle0', timeout: 120000 });
  await page.waitForSelector('#loading.done', { timeout: 120000 });
  await page.evaluate(() => document.querySelectorAll('.backdrop').forEach(b => b.remove()));
  const cam = () => page.evaluate(() => {
    const c = app.vp.camera;
    return { pos: c.position.toArray().map(v => +v.toFixed(3)), yaw: +app.vp.controls.euler.y.toFixed(3), pitch: +app.vp.controls.euler.x.toFixed(3) };
  });
  const r = {};
  r.start = await cam();
  const box = await page.$eval('#viewport', el => { const b = el.getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height }; });
  const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
  await page.mouse.move(box.x + 20, box.y + box.h - 20);
  // W for 0.6 s
  await page.keyboard.down('KeyW'); await new Promise(r => setTimeout(r, 600)); await page.keyboard.up('KeyW');
  await new Promise(r => setTimeout(r, 300));
  r.afterW = await cam();
  // Shift+W for 0.6 s (slower)
  await page.keyboard.down('ShiftLeft'); await page.keyboard.down('KeyW'); await new Promise(r => setTimeout(r, 600));
  await page.keyboard.up('KeyW'); await page.keyboard.up('ShiftLeft');
  await new Promise(r => setTimeout(r, 300));
  r.afterShiftW = await cam();
  // E up
  await page.keyboard.down('KeyE'); await new Promise(r => setTimeout(r, 300)); await page.keyboard.up('KeyE');
  await new Promise(r => setTimeout(r, 300));
  r.afterE = await cam();
  // right-drag to look
  await page.mouse.move(cx, cy);
  await page.mouse.down({ button: 'right' });
  for (let k = 1; k <= 10; k++) await page.mouse.move(cx + k * 20, cy + k * 4);
  await page.mouse.up({ button: 'right' });
  r.afterLook = await cam();
  // left-drag on empty floor must not move the camera
  const before = await cam();
  await page.mouse.move(box.x + 60, box.y + box.h - 60);
  await page.mouse.down(); for (let k = 1; k <= 10; k++) await page.mouse.move(box.x + 60 + k * 20, box.y + box.h - 60); await page.mouse.up();
  const after = await cam();
  r.leftDragMovedCamera = JSON.stringify(before) !== JSON.stringify(after);
  // put the camera back looking at the sims, then hover the middle of a sim
  await page.evaluate(() => { const T = app.vp.camera.position.constructor; app.vp.controls.lookFrom(new T(0, 1.1, 3.2), new T(0, 0.95, 0)); });
  await new Promise(r => setTimeout(r, 200));
  const spot = await page.evaluate(() => {
    const [id, v] = [...app.simViews][0];
    const p = v.worldPos('b__L_Forearm__').project(app.vp.camera);
    const b = app.vp.canvas.getBoundingClientRect();
    return { x: b.left + (p.x + 1) / 2 * b.width, y: b.top + (1 - p.y) / 2 * b.height };
  });
  await page.mouse.move(spot.x - 3, spot.y); await page.mouse.move(spot.x, spot.y);
  await new Promise(r => setTimeout(r, 150));
  r.hover = await page.evaluate(() => [...app.simViews].map(([id, v]) => ({ id, hovered: v.hovered, name: v.hovered >= 0 ? v.bones[v.hovered].name : v.hovered })));
  r.hud = await page.$eval('#vp-hud', el => el.textContent);
  await page.screenshot({ path: path.join(out, 'cam_hover.png') });
  await page.mouse.click(spot.x, spot.y);
  await new Promise(r => setTimeout(r, 200));
  r.selected = await page.evaluate(() => app.store.selected);
  await page.screenshot({ path: path.join(out, 'cam_select.png') });
  console.log(JSON.stringify(r, null, 1));
  console.log(logs.join('\n') || 'no errors');
  await browser.close();
})();
