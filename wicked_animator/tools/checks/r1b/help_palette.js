// R1-B: the face tools and Blender-habit keys show in Help (?) and in the command palette (Ctrl+K).
//   node tools/checks/r1b/help_palette.js --port 8842
const path = require('path');
const H = require('../lib/harness.js');

const argv = process.argv.slice(2);
const PORT = +((argv.indexOf('--port') >= 0 && argv[argv.indexOf('--port') + 1]) || 8842);
const OUT = path.join(H.ROOT, 'cache', 'checks', 'r1b');
const rows = [];
const C = (name, ok, detail) => { rows.push({ name, ok: !!ok, detail }); };

(async () => {
  const { browser, page, logs } = await H.open(PORT, { w: 1366, h: 768 });
  await page.evaluate(async () => {
    document.getElementById('home').classList.add('hidden');
    for (let i = 0; i < 100 && !(app.posePresets && app.posePresets.length); i++) await new Promise(r => setTimeout(r, 100));
  });
  await page.evaluate(() => document.body.focus());
  await page.keyboard.type('?');
  await H.sleep(500);
  const help = await page.evaluate(() => {
    const m = document.querySelector('#modal-root .backdrop:not(.leaving) .modal');
    const t = m ? m.textContent : '';
    const hs = m ? [...m.querySelectorAll('.help-h')].map(x => x.textContent) : [];
    const g = m && [...m.querySelectorAll('.help-h')].find(x => /Face and every bone/.test(x.textContent));
    if (g) g.scrollIntoView({ block: 'start' });
    return { heads: hs, face: /Face tool: click a dot/.test(t), sym: /Symmetry on \/ off/.test(t), alt: /safe range/.test(t), find: /Find a bone/.test(t), num: /Numpad/.test(t) };
  });
  C('Help lists the face tools and Blender-habit keys under "Face and every bone"', help.heads.includes('Face and every bone') && help.face && help.sym && help.alt && help.find && help.num, help);
  await H.sleep(300);
  await H.shot(page, path.join(OUT, 'help_face_keys.png'));
  await page.keyboard.press('Escape');
  await H.sleep(400);
  // the palette: "symmetry", "find a bone" and the face commands
  await page.keyboard.down('Control'); await page.keyboard.press('KeyK'); await page.keyboard.up('Control');
  await H.sleep(400);
  const open = await page.evaluate(() => !!document.querySelector('.palette-back, .palette'));
  if (open) {
    await page.keyboard.type('face');
    await H.sleep(300);
  }
  const pal = await page.evaluate(() => [...document.querySelectorAll('.palette [role=option], .palette li, .palette .row, .palette button')].map(x => x.textContent.trim()).filter(Boolean).slice(0, 40));
  C('the command palette offers the face commands (Copy / Mirror / Reset face)', open && pal.some(t => /Copy face/.test(t)) && pal.some(t => /Mirror face/.test(t)) && pal.some(t => /Reset face here/.test(t)), { open, pal: pal.slice(0, 14) });
  await H.shot(page, path.join(OUT, 'palette_face.png'));
  if (open) {
    await page.evaluate(() => { const i = document.querySelector('.palette input'); if (i) { i.value = ''; i.dispatchEvent(new Event('input', { bubbles: true })); } });
    await page.keyboard.type('symmetry');
    await H.sleep(300);
  }
  const pal2 = await page.evaluate(() => [...document.querySelectorAll('.palette [role=option], .palette li, .palette .row, .palette button')].map(x => x.textContent.trim()).filter(Boolean).slice(0, 10));
  C('the command palette finds "Symmetry on"', pal2.some(t => /Symmetry on/.test(t)), pal2);
  await page.keyboard.press('Enter');
  await H.sleep(300);
  C('... and Enter switches Symmetry on', await page.evaluate(() => app.mirrorEdit === true));
  const errs = logs.filter(l => l.type === 'pageerror' || (l.type === 'error' && !/favicon/.test(l.text)));
  C('no page errors', !errs.length, errs.map(e => e.text).slice(0, 4));
  await browser.close();
  process.exit(H.report(rows, 'R1-B help and palette') ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
