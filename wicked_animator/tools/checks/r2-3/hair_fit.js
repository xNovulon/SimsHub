// R2-3: every Tray sim's hair sits on its head (the round-2 gate found one 10.7 cm low: a +12 cm head slider).
//   For EVERY adult Tray sim whose hair is installed, in both ways the app shows it:
//     1. added from the Tray (its own body shape and skin), and
//     2. tried on another sim with "Try it on other bodies",
//   the hair's top sits between 2 cm below and 8 cm above the crown. Measured on what is drawn: the skinned vertices
//   of the hair and of the body's head (vertices weighted >= 0.5 to b__Head__), along the head's own up axis.
//   Read-only: Tray sims are only read (adults only, the Tray's own adult filter); nothing is saved.
//   node tools/checks/r2-3/hair_fit.js --port 8853 [--only <name part>]
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const LOW = -0.02, HIGH = 0.08;
const ONLY = L.arg('only');
const progress = t => { if (process.stdout.isTTY) process.stdout.write(t + '\r'); };

(async () => {
  const port = L.argPort();
  const base = `http://127.0.0.1:${port}`;
  const rows = [];
  // every adult Tray sim (the Tray list marks who may be used: adult humans)
  const trayList = await (await fetch(`${base}/api/tray`)).json();
  const sims = [];
  for (const hh of trayList || []) for (const s of hh.sims || []) {
    if (!s.allowed) continue;
    const name = `${s.first || ''} ${s.last || ''}`.trim();
    if (ONLY && !name.toLowerCase().includes(ONLY.toLowerCase())) continue;
    sims.push({ tray: hh.id, index: s.index, name, gender: s.gender });
  }
  const { browser, page, logs } = await L.appPage(port, { w: 1366, h: 768 });
  const t0 = Date.now();
  try {
    await page.evaluate(() => {
      // the measure: hair top minus crown along the head's up axis, on the drawn (skinned) vertices
      window.__hairFit = async (v) => {
        const THREE = await import('three');
        const head = v.bone('b__Head__');
        const hi = v.skeleton.bones.indexOf(head);
        const body = v.meshes[0];
        body.updateMatrixWorld(true);
        // the head's up: world +Y at bind, carried by the head's skinning matrix into the pose that is drawn
        const M = new THREE.Matrix4().multiplyMatrices(body.matrixWorld, head.matrixWorld).multiply(v.skeleton.boneInverses[hi]);
        const up = new THREE.Vector3(0, 1, 0).transformDirection(M);
        const tmp = new THREE.Vector3();
        let crown = -Infinity, top = -Infinity, nHead = 0, nHair = 0;
        for (const m of v.meshes) {
          const si = m.geometry.attributes.skinIndex, sw = m.geometry.attributes.skinWeight, n = m.geometry.attributes.position.count;
          for (let i = 0; i < n; i++) {
            let w = 0;
            for (let k = 0; k < 4; k++) if (si.getComponent(i, k) === hi) w += sw.getComponent(i, k);
            if (w < 0.5) continue;
            m.getVertexPosition(i, tmp); m.localToWorld(tmp);
            const y = tmp.dot(up); if (y > crown) crown = y; nHead++;
          }
        }
        const hair = (v.parts || []).filter(p => p.userData.role === 'hair' && !p.userData.soft);
        for (const m of hair) {
          const n = m.geometry.attributes.position.count;
          for (let i = 0; i < n; i++) { m.getVertexPosition(i, tmp); m.localToWorld(tmp); const y = tmp.dot(up); if (y > top) top = y; nHair++; }
        }
        return { crown, top, diff: hair.length ? top - crown : null, nHead, nHair, hair: v.hairName || null, parts: hair.length };
      };
    });

    // ---- 1. added from the Tray (batches of 6, the scene's own sim leaves)
    const added = [];
    for (let b = 0; b < sims.length; b += 6) {
      const batch = sims.slice(b, b + 6);
      const r = await page.evaluate(async (batch) => {
        const bodies = await import('/js/bodies.js');
        app.newScene(false, false, 'solo');
        await new Promise(res => setTimeout(res, 300));
        const first = app.store.project.sims.map(s => s.id);
        const out = [];
        for (const t of batch) {
          try { await app.addTraySim(t.tray, t.index, t.name); } catch (err) { out.push({ ...t, error: String(err.message || err) }); continue; }
          const s = app.store.project.sims[app.store.project.sims.length - 1];
          out.push({ ...t, simId: s.id });
        }
        for (const id of first) app.removeSim(id);
        for (const x of out) {
          if (!x.simId) continue;
          try { await bodies.reloadHair(app, x.simId); } catch (err) { x.error = String(err.message || err); }
        }
        app.applyPoses();
        for (const x of out) {
          const v = x.simId && app.simViews.get(x.simId);
          if (v) Object.assign(x, await window.__hairFit(v));
        }
        return out;
      }, batch);
      added.push(...r);
      progress(`  added ${added.length}/${sims.length}`);
    }

    // ---- 2. tried on another sim ("Try it on other bodies"): a plain female sim, each Tray body in turn
    const tried = [];
    await page.evaluate(async () => { app.newScene(false, false, 'solo'); await new Promise(res => setTimeout(res, 300)); });
    for (const t of sims) {
      const r = await page.evaluate(async (t) => {
        const bodies = await import('/js/bodies.js');
        const s = app.store.project.sims.find(x => x.frame === (t.gender === 'male' ? 'ym' : 'yf')) || app.store.project.sims[0];
        const ok = await bodies.tryBody(app, s.id, { kind: 'tray', tray: t.tray, index: t.index, name: t.name });
        if (!ok) return { ...t, error: 'the trial did not start' };
        await bodies.reloadHair(app, s.id);
        app.applyPoses();
        const v = app.simViews.get(s.id);
        return { ...t, ...(await window.__hairFit(v)), trial: (bodies.activeTrial(app, s.id) || {}).bodyKey };
      }, t);
      tried.push(r);
      progress(`  tried ${tried.length}/${sims.length}`);
    }
    const sameProject = await page.evaluate(async () => { const b = await import('/js/bodies.js'); b.endTrial(app, null, { quiet: true }); return true; });
    void sameProject;

    // ---- Таис Сфорца (the one the gate found): the measure itself catches the old fault (her hair without her body
    //      shape: about 10 cm low), then a close up at both sizes
    const tais = sims.find(s => /Таис/.test(s.name));
    let control = null;
    if (tais) {
      control = await page.evaluate(async (t) => {
        app.newScene(false, false, 'solo');
        await new Promise(res => setTimeout(res, 300));
        const first = app.store.project.sims.map(s => s.id);
        await app.addTraySim(t.tray, t.index, t.name);
        for (const id of first) app.removeSim(id);
        const s = app.store.project.sims[app.store.project.sims.length - 1];
        const info = await (await fetch(`/api/body_variant?tray=${t.tray}&index=${t.index}`)).json();
        const plain = await (await fetch('/api/hair?casp=' + info.hair.casp)).json();        // no shape_tray: the old way
        const v = app.simViews.get(s.id);
        v.hairKey = 'control'; v.removeParts('hair'); v.addPart(plain, null, { role: 'hair' });
        app.applyPoses();
        return window.__hairFit(v);
      }, tais);
      for (const [w, h] of [[1366, 768], [1920, 1080]]) {
        await page.setViewport({ width: w, height: h });
        await page.evaluate(async (t) => {
          const THREE = await import('three');
          const home = document.getElementById('home');
          if (home && !home.classList.contains('hidden')) {
            const b = [...home.querySelectorAll('button')].find(x => /editor|Continue/.test(x.textContent));
            if (b) b.click(); else home.classList.add('hidden');
          }
          app.newScene(false, false, 'solo');
          await new Promise(res => setTimeout(res, 300));
          const first = app.store.project.sims.map(s => s.id);
          await app.addTraySim(t.tray, t.index, t.name);
          for (const id of first) app.removeSim(id);
          const s = app.store.project.sims[app.store.project.sims.length - 1];
          const bodies = await import('/js/bodies.js');
          await bodies.reloadHair(app, s.id);
          app.applyPoses();
          app.setPlaying(false); if (app.showcase) app.showcase(false); if (app.vp.stopCamera) app.vp.stopCamera();
          const v = app.simViews.get(s.id);
          v.group.updateMatrixWorld(true);
          const c = v.worldPos('b__Head__').clone().add(new THREE.Vector3(0, 0.1, 0));
          app.vp.frame(c, 0.5, new THREE.Vector3(0.45, 0.1, 1).normalize());
        }, tais);
        await L.sleep(1200);
        await L.shot(page, `hair_fit_tais_${w}.png`);
      }
    }

    // ---- the table
    const judge = list => {
      const withHair = list.filter(x => x.diff !== null && x.diff !== undefined && !x.error);
      const bad = withHair.filter(x => !(x.diff >= LOW && x.diff <= HIGH));
      const ds = withHair.map(x => x.diff);
      return { withHair, bad, min: Math.min(...ds), max: Math.max(...ds), errors: list.filter(x => x.error), none: list.filter(x => !x.error && !x.parts) };
    };
    const cm = x => (x * 100).toFixed(1);
    for (const [label, list] of [['added from the Tray', added], ['tried on another sim (Try it on other bodies)', tried]]) {
      const j = judge(list);
      rows.push([`${label}: every adult Tray sim's hair top ${LOW * 100} to +${HIGH * 100} cm from the crown (${j.withHair.length} with hair of ${list.length})`,
        !j.bad.length && !j.errors.length && j.withHair.length > 0,
        j.bad.length ? j.bad.map(x => `${x.name}: ${cm(x.diff)} cm (${(x.hair || '').slice(0, 40)})`).join('; ')
          : `${cm(j.min)} to +${cm(j.max)} cm; no mesh hair: ${j.none.length}${j.errors.length ? '; errors: ' + j.errors.map(x => x.name + ' ' + x.error).join('; ') : ''}`]);
    }
    for (const [label, list] of [['added', added], ['tried', tried]]) {
      const x = list.find(s => /Таис/.test(s.name) && s.diff !== null && s.diff !== undefined);
      if (x) rows.push([`Таис Сфорца (+12 cm head slider), ${label}: hair top ${cm(x.diff)} cm from the crown`, x.diff >= LOW && x.diff <= HIGH, `${(x.hair || '').slice(0, 60)}`]);
    }
    if (control) rows.push([`the measure catches the old fault: Таис's hair without her body shape is ${cm(control.diff)} cm from the crown (out of range)`,
      control.diff < LOW, `${control.nHair} hair / ${control.nHead} head vertices`]);
    const errs = logs.filter(l => l.type === 'pageerror' || l.type === 'error');
    rows.push(['no page errors', !errs.length, errs.slice(0, 4).map(e => e.text).join(' | ')]);
    fs.writeFileSync(path.join(L.OUT, 'hair_fit.json'), JSON.stringify({ added, tried, seconds: (Date.now() - t0) / 1000 }, null, 1));
    process.exitCode = L.table(rows, `R2-3: hair on every Tray sim's head (${Math.round((Date.now() - t0) / 1000)} s)`) ? 0 : 1;
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
