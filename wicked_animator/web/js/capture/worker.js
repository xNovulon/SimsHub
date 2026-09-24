// The motion reader's own thread (a classic worker; capture/tracker.js createWorkerTracker starts it). Reading a
// webcam frame takes 20-45 ms with body, hands and face; here it runs beside the page, so the live mirror's 3D view
// keeps drawing at its own pace. The page sends each picture as an ImageBitmap (moved, not copied) and gets the
// landmarks back (a frame record, capture/detect.js). Nothing but landmarks ever leaves this thread.
// A classic worker (not a module worker) because MediaPipe's WASM loader is a classic script it loads with
// importScripts; the ES module bundle itself comes in through import(), which classic workers allow.
// Stand-in mode (tests): `mock` carries a take, and each frame's landmarks are looked up by its time.
/* eslint-env worker */
let D = null, tr = null, mock = null;

self.onmessage = async e => {
  const m = e.data || {};
  try {
    if (m.type === 'init') {
      D = await import('./detect.js');
      if (m.mock) { mock = m.mock; self.postMessage({ type: 'ready', mock: true }); return; }
      const mp = await import(D.BASE + '/vision_bundle.mjs');
      tr = await D.makeTasks(mp, m.opts || {});
      self.postMessage({ type: 'ready', delegates: tr.delegates });
    } else if (m.type === 'frame') {
      let rec;
      if (mock) rec = { ...D.recordAt(mock, D.frameIndexAt(mock.t, m.t || 0)), ms: { pose: 0, hands: 0, face: 0 } };
      else rec = D.detectFrame(tr, m.bitmap, m.ts, { W: m.W, H: m.H });
      try { m.bitmap && m.bitmap.close && m.bitmap.close(); } catch { /* gone */ }
      self.postMessage({ type: 'result', id: m.id, record: rec }, D.transferables(rec));
    } else if (m.type === 'close') {
      try { tr && tr.close && tr.close(); } catch { /* gone */ }
      self.close();
    }
  } catch (err) {
    try { m.bitmap && m.bitmap.close && m.bitmap.close(); } catch { /* gone */ }
    self.postMessage({ type: m.type === 'init' ? 'error' : 'frame-error', id: m.id, error: String((err && err.message) || err) });
  }
};
