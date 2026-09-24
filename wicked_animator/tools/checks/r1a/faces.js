// R1-A: a picture sheet of the one-click expressions in 'classic' (top row) and 'creator' style (bottom row), plus
// the new one-sided channels, so the creator-like faces can be judged by eye.
//   node tools/checks/r1a/faces.js --port 8841   -> cache/checks/r1a/faces_sheet.png, faces_new_channels.png
'use strict';
const path = require('path');
const fs = require('fs');
const L = require('./lib');

(async () => {
  const port = L.argPort();
  const server = await L.startServer(port);
  let browser;
  try {
    browser = await L.launch(1600, 900);
    const { page } = await L.open(browser, port, { kind: 'engine', w: 1600, h: 900 });
    const sheet = async (file, rows, cols, W, H) => {
      await page.evaluate(async (rows, cols, W, H) => {
        const THREE = R.THREE;
        document.querySelectorAll('canvas').forEach(c => c.remove());
        const canvas = document.createElement('canvas');
        document.body.appendChild(canvas);
        const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
        renderer.setPixelRatio(1); renderer.setSize(W * cols.length, H * rows.length);
        renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.08;
        renderer.setScissorTest(true);
        const tex = await new Promise(res => new THREE.TextureLoader().load('/api/skin?frame=yf', t => { t.flipY = false; t.colorSpace = THREE.SRGBColorSpace; res(t); }, undefined, () => res(null)));
        for (let r = 0; r < rows.length; r++) for (let c = 0; c < cols.length; c++) {
          const scene = new THREE.Scene(); scene.background = new THREE.Color(r % 2 ? 0x2a1f36 : 0x241a2f);
          scene.add(new THREE.HemisphereLight(0xfff4ee, 0x2a2228, 0.85));
          const key = new THREE.DirectionalLight(0xfff3ea, 2.3); key.position.set(1.2, 3, 3.6); scene.add(key);
          const fill = new THREE.DirectionalLight(0xfff0e8, 0.6); fill.position.set(-2, 1.2, 4); scene.add(fill);
          const p = R.state.newProject(); p.faceStyle = rows[r]; p.sims.push(R.state.newSim(p, 'yf'));
          const app = R.scene(p), s = app.store.project.sims[0], v = app.simViews.get(s.id);
          v.resetPose(); s.keys = [{ frame: 0, ease: 'auto', pose: v.getPose(), face: typeof cols[c] === 'string' ? { ...R.face.FACE_PRESETS[cols[c]].face } : cols[c] }];
          R.pipeline.simBody(s); s.body.blink = false;
          if (tex) v.setTexture(tex);
          app.pipeline.apply(0, { overrides: false, physics: false });
          scene.add(v.group); v.group.updateMatrixWorld(true);
          const head = v.bone('b__Head__').getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(0, 0.075, 0.03));
          const cam = new THREE.PerspectiveCamera(20, W / H, 0.01, 10);
          cam.position.copy(head).add(new THREE.Vector3(0.12, 0.02, 0.62)); cam.lookAt(head);
          const y = (rows.length - 1 - r) * H;
          renderer.setViewport(c * W, y, W, H); renderer.setScissor(c * W, y, W, H);
          renderer.render(scene, cam);
        }
      }, rows, cols, W, H);
      const f = path.join(L.OUT, file);
      await page.screenshot({ path: f, clip: { x: 0, y: 0, width: W * cols.length, height: H * rows.length } });
      console.log('wrote', f);
    };
    await sheet('faces_sheet.png', ['classic', 'creator'], ['smile', 'seductive', 'moan', 'ecstasy', 'intense', 'surprised'], 260, 330);
    await sheet('faces_new_channels.png', ['creator'], [{}, { wink: 1, smile: 0.5 }, { smileSide: 0.8 }, { browSide: 1 }, { browTilt: 1, inner: 0.6 }, { sneer: 1 }, { jawSide: 1, open: 0.3 }, { puff: 1 }], 200, 260);
  } finally {
    if (browser) await browser.close();
    L.stopServer(server);
  }
})().catch(e => { console.error(e); process.exit(1); });
