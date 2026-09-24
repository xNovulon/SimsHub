// R1-A goal 5: measure whether "Smooth hip twist" (ThighTwist = ratio x the thigh's twist) makes the hip and buttock
// cleaner, for the hip-twist default decision (spec_face_bones section 6 check 13), with the wrist as a control.
// Metric: the skin is skinned on the CPU (three.js getVertexPosition) and every mesh edge whose two ends are weighted
// to the leg (Thigh + ThighTwist >= 5%) is compared with its bind-pose length: mean |stretch - 1| (lower = less
// pinching and stretching). Poses: pure twists, and the thighs of every fixture's ready pose.
//   node tools/checks/r1a/hip_twist.js --port 8841
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const fx = Object.fromEntries(L.fixtures().map(f => [f.name, f.project]));
  const server = await L.startServer(port);
  let browser;
  try {
    browser = await L.launch();
    const { page } = await L.open(browser, port, { kind: 'engine' });
    const res = await page.evaluate(async FX => {
      const THREE = R.THREE;
      const mulAxis = (q, axis, deg) => new THREE.Quaternion().fromArray(q).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(...axis).normalize(), THREE.MathUtils.degToRad(deg))).toArray();
      // edges of the meshes touching the given bones (both ends weighted >= 5%)
      function edgesFor(v, bones) {
        const ids = new Set(bones.map(n => v.index(n)));
        const out = [];
        for (const mesh of v.meshes) {
          if (!['top', 'bottom', 'body'].includes(mesh.userData.role)) continue;
          const g = mesh.geometry, si = g.attributes.skinIndex, sw = g.attributes.skinWeight, idx = g.index.array;
          const wOf = i => { let w = 0; for (let k = 0; k < 4; k++) if (ids.has(si.getComponent(i, k))) w += sw.getComponent(i, k); return w; };
          const ok = new Uint8Array(si.count); for (let i = 0; i < si.count; i++) ok[i] = wOf(i) >= 0.05 ? 1 : 0;
          const seen = new Set();
          for (let t = 0; t < idx.length; t += 3) for (const [a, b] of [[idx[t], idx[t + 1]], [idx[t + 1], idx[t + 2]], [idx[t + 2], idx[t]]]) {
            if (!ok[a] || !ok[b]) continue;
            const key = a < b ? a * 1e6 + b : b * 1e6 + a;
            if (seen.has(key)) continue; seen.add(key);
            out.push([mesh, a, b]);
          }
        }
        return out;
      }
      function strain(v, edges) {
        v.group.updateMatrixWorld(true);
        const pa = new THREE.Vector3(), pb = new THREE.Vector3(), ra = new THREE.Vector3(), rb = new THREE.Vector3();
        let s = 0;
        for (const [mesh, a, b] of edges) {
          mesh.getVertexPosition(a, pa); mesh.getVertexPosition(b, pb);
          ra.fromBufferAttribute(mesh.geometry.attributes.position, a); rb.fromBufferAttribute(mesh.geometry.attributes.position, b);
          const l0 = ra.distanceTo(rb);
          if (l0 > 1e-6) s += Math.abs(pa.distanceTo(pb) / l0 - 1);
        }
        return s / Math.max(1, edges.length);
      }
      const p = R.state.newProject(); p.sims.push(R.state.newSim(p, 'yf'));
      const app = R.scene(p), s = app.store.project.sims[0], v = app.simViews.get(s.id);
      R.pipeline.simBody(s);
      const legEdges = edgesFor(v, ['b__L_Thigh__', 'b__L_ThighTwist__']);
      const armEdges = edgesFor(v, ['b__L_Forearm__', 'b__L_ForearmTwist__', 'b__L_Hand__']);
      const hipT = R.bones.TWIST.filter(t => t.opt === 'hipTwist');
      const run = (pose, ratio, which) => {
        s.keys = [{ frame: 0, ease: 'auto', pose }];
        for (const t of hipT) t.ratio = ratio || -0.75;
        s.body.hipTwist = !!ratio;
        s.body.twist = true;
        app.pipeline.apply(0, { overrides: false, physics: false });
        const r = strain(v, which);
        for (const t of hipT) t.ratio = -0.75;
        return r;
      };
      v.resetPose();
      const rest = v.getPose();
      const rq = n => v.restByName[n].quat.toArray();
      const poses = {
        'twist 45': { rot: { b__L_Thigh__: mulAxis(rq('b__L_Thigh__'), [1, 0, 0], 45) } },
        'twist -45': { rot: { b__L_Thigh__: mulAxis(rq('b__L_Thigh__'), [1, 0, 0], -45) } },
        'raised 35 + twist 45': { rot: { b__L_Thigh__: mulAxis(mulAxis(rq('b__L_Thigh__'), [0, 0, 1], 35), [1, 0, 0], 45) } },
        'raised 80 + twist -30 (knee up, turned in)': { rot: { b__L_Thigh__: mulAxis(mulAxis(rq('b__L_Thigh__'), [0, 0, 1], 80), [1, 0, 0], -30) } },
        'spread 40 + twist 30 (turned out)': { rot: { b__L_Thigh__: mulAxis(mulAxis(rq('b__L_Thigh__'), [0, 1, 0], 40), [1, 0, 0], 30) } },
      };
      const legs = {};
      for (const [name, over] of Object.entries(poses)) {
        const pose = JSON.parse(JSON.stringify(rest)); Object.assign(pose.rot, over.rot);
        legs[name] = { off: run(pose, 0, legEdges), on075: run(pose, -0.75, legEdges), on040: run(pose, -0.4, legEdges) };
      }
      // ready poses from real creator clips (the fixtures made by Magic): the woman's left leg as posed
      for (const [fname, proj] of Object.entries(FX)) {
        if (!/^magic_(cowgirl|missionary|doggy|bj)$/.test(fname)) continue;
        const f = proj.sims.find(x => x.frame === 'yf');
        if (!f) continue;
        const pose = JSON.parse(JSON.stringify(f.keys[0].pose));
        for (const n of Object.keys(pose.rot)) if (R.bones.FACE_SET.has(n)) delete pose.rot[n];
        const tw = R.animation.twistAngle(v.restByName.b__L_Thigh__.quat, new THREE.Quaternion().fromArray(pose.rot.b__L_Thigh__)) * 180 / Math.PI;
        legs[`${fname} (thigh twist ${tw.toFixed(0)} deg)`] = { off: run(pose, 0, legEdges), on075: run(pose, -0.75, legEdges), on040: run(pose, -0.4, legEdges) };
      }
      // control: the wrist with and without its helper (the forearm helper is known to help)
      const hand = JSON.parse(JSON.stringify(rest)); hand.rot.b__L_Hand__ = mulAxis(rq('b__L_Hand__'), [1, 0, 0], 70);
      s.keys = [{ frame: 0, ease: 'auto', pose: hand }];
      s.body.twist = false; app.pipeline.apply(0, { overrides: false, physics: false }); const wOff = strain(v, armEdges);
      s.body.twist = true; app.pipeline.apply(0, { overrides: false, physics: false }); const wOn = strain(v, armEdges);
      return { legs, wrist: { off: wOff, on: wOn }, legEdges: legEdges.length, armEdges: armEdges.length };
    }, fx);
    const rows = Object.entries(res.legs).map(([k, x]) => [k, x.off, x.on075, x.on040]);
    console.log('mean |edge stretch - 1| on the left leg and hip (lower is cleaner)');
    console.log('pose'.padEnd(52), 'off'.padStart(8), '-0.75'.padStart(8), '-0.40'.padStart(8));
    for (const [k, a, b, c] of rows) console.log(k.padEnd(52), a.toFixed(5).padStart(8), b.toFixed(5).padStart(8), c.toFixed(5).padStart(8));
    console.log(`wrist control (hand rolled 70): off ${res.wrist.off.toFixed(5)}, on ${res.wrist.on.toFixed(5)}`);
    const sum = i => rows.reduce((a, r) => a + r[i], 0);
    const verdict = { off: sum(1), on075: sum(2), on040: sum(3) };
    const best = Object.entries(verdict).sort((a, b) => a[1] - b[1])[0][0];
    console.log('totals', JSON.stringify(verdict), 'cleanest:', best);
    fs.writeFileSync(path.join(L.OUT, 'hip_twist.json'), JSON.stringify({ ...res, totals: verdict, cleanest: best }, null, 1));
  } finally {
    if (browser) await browser.close();
    L.stopServer(server);
  }
})().catch(e => { console.error(e); process.exit(1); });
