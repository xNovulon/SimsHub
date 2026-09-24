// R1-A: the new engine inside the whole app (whatever main.js is at the moment): it starts without errors, Magic
// makes a v3 'creator' animation that plays, bakes with face and twist tracks, and an old saved project still loads.
//   node tools/checks/r1a/app_smoke.js --port 8841
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const rows = [];
  const add = (n, ok, d) => rows.push([n, !!ok, d]);
  const server = await L.startServer(port);
  let browser;
  try {
    browser = await L.launch();
    const { page, logs, writes } = await L.open(browser, port, { kind: 'app' });
    await page.waitForFunction('app.posePresets && app.posePresets.length > 0', { timeout: 120000 });
    add('app starts with the new engine', true);
    const r = await page.evaluate(async () => {
      const m = await import('/js/magic.js');
      app.store.setDirty(false);
      const ok = await m.makeMagic(app, { recipe: 'missionary', place: 'double_bed', intensity: 0.6, seconds: 3, name: 'r1a smoke', author: 'r1a' });
      app.setPlaying(false); app.showcase(false);
      const p = app.store.project;
      const t = [];
      for (let k = 0; k < 120; k++) { const t0 = performance.now(); app.pipeline.apply(k % p.length); t.push(performance.now() - t0); }
      t.sort((a, b) => a - b);
      const baked = app.bake();
      const a0 = baked.actors[0];
      const bones = Object.keys(a0.tracks);
      const leak = p.sims.flatMap(s => s.keys).some(k => Object.keys((k.pose && k.pose.rot) || {}).some(n => /Jaw|Tounge|Brow|Lid|Lip|Mouth|Cheek|Squint|_Eye__|Nostril/.test(n)));
      return { ok, version: p.version, style: p.faceStyle, applyMedian: t[60], bones: bones.length, twist: bones.includes('b__L_ForearmTwist__'), nostril: bones.includes('b__CAS_L_Nostril__'),
        mouth: a0.mouthMoves, leak, keys: p.sims.map(s => s.keys.length), hip: p.sims.map(s => s.body.hipTwist) };
    });
    add('Magic makes a v3 creator animation', r.ok && r.version === 3 && r.style === 'creator', JSON.stringify({ version: r.version, style: r.style, keys: r.keys, hipTwist: r.hip }));
    add('app.bake() has twist and nostril tracks', r.twist && r.nostril, `${r.bones} tracks`);
    add('no face bone in any key.pose', !r.leak);
    add('app pipeline.apply median <= 1 ms', r.applyMedian <= 1, `${r.applyMedian.toFixed(3)} ms`);
    // an old saved project (version 1) loads as classic, v3
    const old = JSON.parse(fs.readFileSync(path.join(L.FIX, 'Cowgirl 1.json'), 'utf8'));
    const o = await page.evaluate(p => {
      app.store.setDirty(false);
      app.store.load(p); app.syncViews(); app.refreshAll && app.refreshAll();
      app.pipeline.apply(0);
      const q = app.store.project;
      return { version: q.version, style: q.faceStyle, fb: q.sims.map(s => s.keys.every(k => k.faceBones)) };
    }, old);
    add('an old project loads: version 3, classic, face keys', o.version === 3 && o.style === 'classic' && o.fb.every(Boolean), JSON.stringify(o));
    await new Promise(r => setTimeout(r, 1500));
    const f = path.join(L.OUT, 'app_smoke.png');
    await page.screenshot({ path: f });
    add('screenshot', fs.existsSync(f), f);
    const bad = logs.filter(l => /pageerror|error:/.test(l) && !/404|favicon/.test(l));
    add('no page errors', !bad.length, bad.slice(0, 5).join(' | '));
    add('nothing written to the server', true, `${writes.length} writes answered in the browser: ${[...new Set(writes.map(w => w.url))].join(', ')}`);
  } finally {
    if (browser) await browser.close();
    L.stopServer(server);
  }
  process.exit(L.table(rows) ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
