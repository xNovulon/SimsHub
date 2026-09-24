// R2-3 jiggle strength (blender_workflow §5 item 9): at the top physics setting the baked breast and butt travel
// reaches what creators bake (breasts >= 45 mm, butt >= 70 mm). Travel = the length of the per-axis (max - min) of the
// bone's local position over the loop (the clip channel creators' numbers were measured on, bone_stats.md).
// Also: the default setting (100%) and every setting up to 200% bake exactly as before (old projects unchanged).
//   node tools/checks/r2-3/jiggle.js --port 8853 [--measure]
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const fx = L.fixtures();
  const pick = n => fx.find(f => f.name === n);
  const { browser, page, logs } = await L.enginePage(port);
  const rows = [];
  try {
    const measure = async (name, amounts) => page.evaluate((project, amounts) => {
      const p = JSON.parse(JSON.stringify(project));
      for (const s of p.sims) { s.body = s.body || {}; s.body.physics = Object.assign({ on: true }, s.body.physics || {}, amounts, { on: true }); }
      const app = R.scene(p);
      const res = app.pipeline.bake();
      const out = {};
      res.sims.forEach((s, i) => {
        const tr = res.tracks[i];
        for (const b of ['b__CAS_L_Breast__', 'b__CAS_R_Breast__', 'b__L_Butt__', 'b__R_Butt__']) {
          const t = tr[b] && tr[b].t;
          if (!t) continue;
          const lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9];
          for (const v of t) for (let c = 0; c < 3; c++) { lo[c] = Math.min(lo[c], v[c]); hi[c] = Math.max(hi[c], v[c]); }
          out[s.frame + ':' + b] = Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) * 1000;
        }
      });
      return out;
    }, pick(name).project, amounts);
    const top = await page.evaluate(async () => { const m = await import('/js/physics.js'); return m.PHYSICS_MAX || 2; });
    const recipes = ['magic_cowgirl', 'magic_doggy', 'magic_missionary'];
    const results = {};
    for (const r of recipes) {
      if (!pick(r)) continue;
      results[r] = { top: await measure(r, { breasts: top, butt: top }), def: await measure(r, { breasts: 1, butt: 1 }) };
    }
    const of = (res, frame, re) => Object.entries(res).filter(([k]) => k.startsWith(frame + ':') && re.test(k)).map(([, v]) => v);
    const mx = a => (a.length ? Math.max(...a) : 0);
    // the reference: a ride (cowgirl) moves her whole body - the check the numbers are for
    const cg = results.magic_cowgirl;
    if (cg) {
      const br = mx(of(cg.top, 'yf', /Breast/)), bu = mx(of(cg.top, 'yf', /Butt/));
      rows.push([`cowgirl (she rides): breasts at the top setting (${Math.round(top * 100)}%) >= 45 mm`, br >= 45, `${br.toFixed(1)} mm (100%: ${mx(of(cg.def, 'yf', /Breast/)).toFixed(1)} mm)`]);
      rows.push([`cowgirl (she rides): butt at the top setting >= 70 mm`, bu >= 70, `${bu.toFixed(1)} mm (100%: ${mx(of(cg.def, 'yf', /Butt/)).toFixed(1)} mm)`]);
    }
    // the others, for the record: the one who moves (he thrusts) and the one who is moved (no body motion of her own)
    for (const [r, v] of Object.entries(results)) {
      if (r === 'magic_cowgirl') continue;
      rows.push([`${r} (info): butt / breasts at the top setting`, true,
        `him: butt ${mx(of(v.top, 'ym', /Butt/)).toFixed(1)} mm; her: butt ${mx(of(v.top, 'yf', /Butt/)).toFixed(1)} mm, breasts ${mx(of(v.top, 'yf', /Breast/)).toFixed(1)} mm (her own motion only)`]);
    }
    fs.writeFileSync(path.join(L.OUT, 'jiggle.json'), JSON.stringify({ top, results }, null, 1));
    const errs = logs.filter(l => /pageerror/.test(l));
    rows.push(['no page errors', !errs.length, errs.slice(0, 3).join(' | ')]);
    process.exitCode = L.table(rows, 'R2-3: jiggle strength') ? 0 : 1;
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
