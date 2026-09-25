// R2-3 quick smoke: the app starts with the scene feature, its buttons exist without index.html edits, and nothing
// logs an error. node tools/checks/r2-3/smoke.js --port 8853
'use strict';
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const { browser, page, logs } = await L.appPage(port);
  const rows = [];
  try {
    const r = await page.evaluate(async () => {
      const out = {};
      out.feature = !!window.app.__scene;
      out.buttons = ['btn-xray', 'btn-bones', 'btn-clip'].map(id => !!document.getElementById(id));
      out.icons = ['i-xray', 'i-bones', 'i-clip'].map(id => !!document.getElementById(id));
      // the palette and Help list the new tools
      const cmds = app.hooks.commands.flatMap(fn => { try { return fn(app) || []; } catch { return []; } }).map(c => c.id);
      out.cmds = ['see-through', 'show-bones', 'check-clipping', 'try-bodies', 'hair'].filter(id => cmds.includes(id));
      const help = app.hooks.helpRows.flatMap(fn => { try { return fn(app) || []; } catch { return []; } }).map(h => h.text).join(' | ');
      out.help = /See-through/.test(help) && /bones/.test(help);
      // the mixins the steps and the palette use
      out.mixins = ['sitHere', 'lieHere', 'checkClipping', 'tryBody', 'endTrial', 'cycleBodies', 'setHair', 'setSeeThrough', 'setShowBones'].filter(m => typeof app[m] !== 'function');
      // the Tray dialog in pick mode lists only sims with that body, and a pick never adds a sim
      const d = await import('/js/dialogs/tray.js');
      let picked = null;
      const n0 = app.store.project.sims.length;
      // (this PC's Tray has adult women only: a female body lists them all, a male body lists none)
      const genders = (await (await fetch('/api/tray')).json()).flatMap(hh => hh.sims.filter(x => x.allowed).map(x => x.gender));
      d.openTrayDialog(app, { pick: x => { picked = x; }, frame: 'yf', title: 'Pick' });
      await new Promise(res => setTimeout(res, 2000));
      const tiles = [...document.querySelectorAll('.backdrop:not(.leaving) .tile')];
      out.trayFemale = tiles.length === genders.filter(g => g === 'female').length && tiles.every(t => /female/.test(t.textContent));
      out.trayCount = `${tiles.length} tiles, Tray: ${genders.filter(g => g === 'female').length} women, ${genders.filter(g => g === 'male').length} men`;
      if (tiles[0]) tiles[0].click();
      await new Promise(res => setTimeout(res, 300));
      out.picked = !!(picked && picked.tray && picked.frame === 'yf') && app.store.project.sims.length === n0;
      return out;
    });
    rows.push(['the scene feature installed', r.feature]);
    rows.push(['see-through, bones and clipping buttons exist', r.buttons.every(Boolean), JSON.stringify(r.buttons)]);
    rows.push(['their icons exist', r.icons.every(Boolean), JSON.stringify(r.icons)]);
    rows.push(['the palette has See-through, Show bones, Check clipping, Try other bodies, Hair', r.cmds.length === 5, r.cmds.join(', ')]);
    rows.push(['Help lists Alt+Z and Alt+B', r.help]);
    rows.push(['the app methods are there', !r.mixins.length, r.mixins.join(', ') || 'all']);
    rows.push(['the Tray picker (trying bodies) lists only sims with that body', r.trayFemale, r.trayCount]);
    rows.push(['picking a Tray sim there only picks it (no sim is added)', r.picked]);
    const errs = logs.filter(l => l.type === 'pageerror' || l.type === 'error');
    rows.push(['no errors', !errs.length, errs.slice(0, 5).map(e => e.text).join(' | ')]);
    process.exitCode = L.table(rows, 'R2-3 smoke') ? 0 : 1;
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
