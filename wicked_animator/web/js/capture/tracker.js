// The motion reader: MediaPipe Tasks Vision 1.0.1, served from this PC (web/vendor/mediapipe, installed once by the
// Download button) and loaded only when capture is opened. Body, hands and face run as three landmarkers; small faces
// and hands in full-body videos are cut out and read again at a larger size. Frames are read one by one from a video
// (at the speed the PC manages), live from the webcam, or once from a photo. Landmarks are kept, never pixels.
// One person, or two (experimental): each keeps following the body nearest to where it was.
// The live mirror can read in a worker thread (capture/worker.js), so the 3D view keeps its own pace.
// With ?captureMock=1 (or window.__captureMock) a stand-in reads the mock video instead (capture/mock.js).
import { emptyPerson } from './clean.js';
import { writeFrame, isMock } from './mock.js';
import { BASE, makeTasks, detectFrame, transferables } from './detect.js';

export { BASE, detectFrame };
let mp = null;
async function lib() { return (mp = mp || await import(`${BASE}/vision_bundle.mjs`)); }

// createTracker({body, hands, face, quality: 'best' | 'fast', people: 1 | 2, mode: 'VIDEO' | 'IMAGE', onStatus}) -> Tracker
export async function createTracker({ body = true, hands = true, face = true, quality = 'best', people = 1, mode = 'VIDEO', onStatus = null, mock = null } = {}) {
  people = Math.max(1, Math.min(2, people | 0 || 1));
  if (mock || isMock()) return { mock: true, mode, body, hands, face, people, stats: { ms: [] }, close() {} };
  onStatus && onStatus('Warming up the motion reader...');
  return makeTasks(await lib(), { body, hands, face, quality, people, mode });
}

// Is MediaPipe on this PC? (the files the Download button puts in web/vendor/mediapipe)
export async function readerInstalled() {
  try { const r = await fetch('/api/capture_status'); if (!r.ok) return false; return !!(await r.json()).installed; } catch { return false; }
}

// ---------------------------------------------------------------- the reader in a worker thread
// createWorkerTracker(opts, {mockTake}) -> a tracker whose detectAsync(src, tMs) reads a frame in the worker: the
// picture goes over as an ImageBitmap (moved, not copied), the landmarks come back. The page only waits for the
// answer, so the 3D view keeps drawing meanwhile. mockTake: the stand-in's take (tests; no MediaPipe needed).
// Throws when the worker can't start (then the page reads on its own thread, as before).
export async function createWorkerTracker(opts = {}, { mockTake = null, timeout = 30000 } = {}) {
  const people = Math.max(1, Math.min(2, opts.people | 0 || 1));
  const w = new Worker(new URL('./worker.js', import.meta.url));        // a classic worker (see worker.js)
  const pending = new Map();
  let seq = 0, closed = false;
  const tr = {
    worker: true, mock: !!mockTake, mode: opts.mode || 'VIDEO', people, body: opts.body !== false, hands: opts.hands !== false, face: opts.face !== false,
    stats: { pose: [], hands: [], face: [], roundTrip: [] }, busy: 0,
    async detectAsync(src, tMs, { W, H } = {}) {
      if (closed) throw new Error('closed');
      const el = src.el || src;
      const bitmap = await createImageBitmap(el);
      const id = ++seq, t0 = performance.now();
      tr.busy++;
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve: rec => { tr.busy--; tr.stats.roundTrip.push(performance.now() - t0); resolve(rec); }, reject: e => { tr.busy--; reject(e); } });
        w.postMessage({ type: 'frame', id, bitmap, ts: tMs, t: src.currentTime || 0, W: W || src.videoWidth, H: H || src.videoHeight }, [bitmap]);
      });
    },
    close() {
      if (closed) return;
      closed = true;
      try { w.postMessage({ type: 'close' }); } catch { /* gone */ }
      setTimeout(() => w.terminate(), 200);
      for (const p of pending.values()) p.reject(new DOMException('closed', 'AbortError'));
      pending.clear();
    },
  };
  const ready = new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('The motion reader thread did not start in time.')), timeout);
    w.onmessage = e => {
      const m = e.data || {};
      if (m.type === 'ready') { clearTimeout(timer); tr.delegates = m.delegates || {}; resolve(); }
      else if (m.type === 'error') { clearTimeout(timer); reject(new Error(m.error || 'The motion reader thread failed.')); }
      else if (m.type === 'result' || m.type === 'frame-error') {
        const p = pending.get(m.id);
        if (!p) return;
        pending.delete(m.id);
        if (m.type === 'result') {
          const r = m.record;
          if (r && r.ms) for (const k of ['pose', 'hands', 'face']) if (r.ms[k] !== undefined) tr.stats[k].push(r.ms[k]);
          p.resolve(r);
        } else p.reject(new Error(m.error || 'frame'));
      }
    };
    w.onerror = e => { clearTimeout(timer); e.preventDefault && e.preventDefault(); reject(new Error(e.message || 'The motion reader thread failed.')); };
  });
  const mock = mockTake ? { t: mockTake.t, people: mockTake.people } : null;
  w.postMessage({ type: 'init', opts: { ...opts, people }, mock });
  try { await ready; } catch (e) { tr.close(); throw e; }
  return tr;
}
export { transferables };

// ---------------------------------------------------------------- recording frames into a Take
export class TakeRecorder {
  constructor(source, W, H, fov = 60, cap = 60 * 60, people = 1) {
    this.source = source; this.W = W; this.H = H; this.fov = fov;
    this.cap = cap; this.n = 0;
    this.t = new Float64Array(cap);
    this.persons = Array.from({ length: Math.max(1, people) }, () => emptyPerson(cap));
    this.tongue = new Float32Array(cap);
    this.people = new Uint8Array(cap);
  }
  get person() { return this.persons[0]; }
  add(t, fr, tongue = 0) {
    if (this.n >= this.cap) this._grow();
    const i = this.n++;
    this.t[i] = t;
    writeFrame(this.persons[0], i, { pose: fr.pose, hands: fr.hands, face: fr.face });
    for (let k = 1; k < this.persons.length; k++) { const o = fr.others && fr.others[k - 1]; if (o) writeFrame(this.persons[k], i, o); }
    this.tongue[i] = tongue;
    this.people[i] = fr.people || 0;
    return i;
  }
  _grow() {
    const cap = this.cap * 2;
    this.persons = this.persons.map(o => {
      const p = emptyPerson(cap);
      p.pose.set(o.pose); p.img.set(o.img);
      for (const s of ['L', 'R']) { p.hand[s].set(o.hand[s]); p.hand[s + 'ok'].set(o.hand[s + 'ok']); }
      for (const k of ['bs', 'm', 'ok', 'eyeL', 'eyeR']) p.face[k].set(o.face[k]);
      return p;
    });
    const t = new Float64Array(cap); t.set(this.t);
    const tg = new Float32Array(cap); tg.set(this.tongue);
    const pp = new Uint8Array(cap); pp.set(this.people);
    Object.assign(this, { cap, t, tongue: tg, people: pp });
  }
  take() {
    const n = this.n;
    const sl = (a, w) => a.slice(0, n * w);
    const people = this.persons.map(o => ({
      pose: sl(o.pose, 132), img: sl(o.img, 99),
      hand: { L: sl(o.hand.L, 63), R: sl(o.hand.R, 63), Lok: sl(o.hand.Lok, 1), Rok: sl(o.hand.Rok, 1) },
      face: { bs: sl(o.face.bs, 52), m: sl(o.face.m, 16), ok: sl(o.face.ok, 1), eyeL: sl(o.face.eyeL, 1), eyeR: sl(o.face.eyeR, 1) },
    }));
    const tongue = this.tongue.slice(0, n);
    return { source: this.source, width: this.W, height: this.H, fov: this.fov, t: this.t.slice(0, n), people,
      tongue: tongue.some(x => x > 0.01) ? tongue : undefined, crowd: Math.max(0, ...this.people.slice(0, n)) };
  }
}

// How many people a take really has (a person never seen is left out).
export function seenPeople(take) {
  return take.people.filter(pe => { for (let i = 0; i < take.t.length; i++) if (pe.pose[i * 132 + 23 * 4 + 3] > 0) return true; return false; }).length;
}

// ---------------------------------------------------------------- the three sources
// trackVideo(tracker, video, {from, to, onFrame(record, t, progress), signal}) -> Take. The video plays at the speed
// the PC can read it (slower when reading takes longer than a frame), and every presented frame is read with its
// real time stamp (phone videos have a variable frame rate; the cleaner resamples them).
export async function trackVideo(tr, video, { from = 0, to = null, onFrame = null, signal = null, fov = 60 } = {}) {
  const W = video.videoWidth, H = video.videoHeight;
  const end = Math.min(to ?? video.duration, video.duration);
  const rec = new TakeRecorder(video instanceof HTMLVideoElement ? 'video' : 'mock', W, H, fov, 60 * 60, tr.people || 1);
  if (video.seek) video.seek(from);
  else { video.currentTime = from; await new Promise(r => video.addEventListener('seeked', r, { once: true })); }
  let rate = tr.mock ? 1 : 0.5, lastMedia = -1;
  video.playbackRate = rate;
  return new Promise((resolve, reject) => {
    let done = false;
    const finish = () => { if (done) return; done = true; video.pause(); resolve(rec.take()); };
    if (signal) signal.addEventListener('abort', () => { if (!done) { done = true; video.pause(); reject(new DOMException('stopped', 'AbortError')); } });
    const onVideoFrame = (nowMs, meta) => {
      if (done) return;
      const t = meta && meta.mediaTime !== undefined ? meta.mediaTime : video.currentTime;
      if (t >= end - 1e-3 || video.ended) {
        if (t > lastMedia && t <= end + 0.05) { const fr = detectFrame(tr, video, t * 1000, { W, H }); rec.add(t, fr); onFrame && onFrame(fr, t, 1); }
        return finish();
      }
      if (t > lastMedia) {
        lastMedia = t;
        const t0 = performance.now();
        const fr = detectFrame(tr, video, t * 1000, { W, H });
        rec.add(t, fr);
        const ms = performance.now() - t0;
        // keep up: slow the video down when reading a frame takes longer than showing it
        // (at speed r a 30 fps video shows a frame every 33/r ms; reading takes `ms`)
        if (!tr.mock) { rate = Math.max(0.1, Math.min(1, 0.8 * rate + 0.2 * (30 / Math.max(1, ms + 4)))); video.playbackRate = rate; }
        onFrame && onFrame(fr, t, (t - from) / Math.max(1e-3, end - from));
      }
      video.requestVideoFrameCallback(onVideoFrame);
    };
    video.requestVideoFrameCallback(onVideoFrame);
    const onEnded = () => finish();
    video.addEventListener('ended', onEnded, { once: true });
    Promise.resolve(video.play()).catch(reject);
  });
}

// trackWebcam(tracker, video (playing the camera), {onFrame, signal, keys: {tongue: () => 0..1}}) -> Take, when the
// signal says stop (the studio's Space / Stop). A worker tracker reads one frame at a time and skips the frames that
// come while it is busy (the take is resampled to 30 fps anyway).
export async function trackWebcam(tr, video, { onFrame = null, signal = null, keys = null, fov = 60 } = {}) {
  const W = video.videoWidth, H = video.videoHeight;
  const rec = new TakeRecorder('webcam', W, H, fov, 60 * 60, tr.people || 1);
  const t0 = performance.now();
  return new Promise(resolve => {
    let done = false, last = -1, busy = false;
    const stop = () => { if (done) return; done = true; resolve(rec.take()); };
    if (signal) signal.addEventListener('abort', stop);
    const step = (nowMs, meta) => {
      if (done) return;
      const t = (performance.now() - t0) / 1000;
      const mt = meta && meta.mediaTime !== undefined ? meta.mediaTime : t;
      if (mt !== last) {
        last = mt;
        const tongue = keys && keys.tongue ? keys.tongue() : 0;
        if (tr.detectAsync) {
          if (!busy) {
            busy = true;
            tr.detectAsync(video, performance.now(), { W, H }).then(fr => { if (!done) { rec.add(t, fr, tongue); onFrame && onFrame(fr, t); } })
              .catch(() => { /* a frame that could not be read */ }).finally(() => { busy = false; });
          }
        } else {
          const fr = detectFrame(tr, video, performance.now(), { W, H });
          rec.add(t, fr, tongue);
          onFrame && onFrame(fr, t);
        }
      }
      if (t > 60) return stop();                       // a minute at most
      video.requestVideoFrameCallback(step);
    };
    video.requestVideoFrameCallback(step);
  });
}

// trackPhoto(tracker (IMAGE mode), image) -> a one-frame Take
export async function trackPhoto(tr, image) {
  const W = image.naturalWidth || image.videoWidth || image.width, H = image.naturalHeight || image.videoHeight || image.height;
  const rec = new TakeRecorder('photo', W, H, 60, 4, tr.people || 1);
  const fr = detectFrame(tr, image, 0, { W, H, image: true });
  rec.add(0, fr);
  return { take: rec.take(), record: fr };
}
