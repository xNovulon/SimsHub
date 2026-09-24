// One frame through MediaPipe (body, hands, face) -> a frame record, for one person or two. This file imports nothing,
// so the same code runs on the page and inside the capture worker (capture/worker.js), where a bare 'three' import
// could not be resolved. Landmarks are kept, never pixels.
//
// Frame record: { pose: {world: Float32Array(132), img: Float32Array(99)} | null, hands: {L, R} (Float32Array(63) world
//   points or null), handsImg?: {L, R}, face: {bs, m, eyeL, eyeR} | null, people: how many bodies were seen,
//   others?: [the same fields for person 2 ...] (two-people mode only), ms: {pose, hands, face} }

// MediaPipe FaceLandmarker blendshape order (index 0 '_neutral' is ignored; there is no tongueOut).
export const BS_NAMES = ['_neutral', 'browDownLeft', 'browDownRight', 'browInnerUp', 'browOuterUpLeft', 'browOuterUpRight',
  'cheekPuff', 'cheekSquintLeft', 'cheekSquintRight', 'eyeBlinkLeft', 'eyeBlinkRight', 'eyeLookDownLeft', 'eyeLookDownRight',
  'eyeLookInLeft', 'eyeLookInRight', 'eyeLookOutLeft', 'eyeLookOutRight', 'eyeLookUpLeft', 'eyeLookUpRight', 'eyeSquintLeft',
  'eyeSquintRight', 'eyeWideLeft', 'eyeWideRight', 'jawForward', 'jawLeft', 'jawOpen', 'jawRight', 'mouthClose',
  'mouthDimpleLeft', 'mouthDimpleRight', 'mouthFrownLeft', 'mouthFrownRight', 'mouthFunnel', 'mouthLeft', 'mouthLowerDownLeft',
  'mouthLowerDownRight', 'mouthPressLeft', 'mouthPressRight', 'mouthPucker', 'mouthRight', 'mouthRollLower', 'mouthRollUpper',
  'mouthShrugLower', 'mouthShrugUpper', 'mouthSmileLeft', 'mouthSmileRight', 'mouthStretchLeft', 'mouthStretchRight',
  'mouthUpperUpLeft', 'mouthUpperUpRight', 'noseSneerLeft', 'noseSneerRight'];
export const BS = Object.fromEntries(BS_NAMES.map((nm, i) => [nm, i]));

export const BASE = '/vendor/mediapipe';
const now = () => performance.now();

// ---------------------------------------------------------------- the readers
// makeTasks(mp, {body, hands, face, quality, people, mode}) -> tracker: the three landmarkers (GPU first, the CPU when
// a driver refuses), plus a small hand reader for cut-outs. `mp` is the loaded vision_bundle.mjs module.
export async function makeTasks(mp, { body = true, hands = true, face = true, quality = 'best', people = 1, mode = 'VIDEO', base = BASE } = {}) {
  const { FilesetResolver, PoseLandmarker, HandLandmarker, FaceLandmarker } = mp;
  const files = await FilesetResolver.forVisionTasks(`${base}/wasm`);
  const delegates = {};
  const make = async (Cls, model, extra, runningMode = mode) => {
    for (const delegate of ['GPU', 'CPU']) {          // GPU first; some drivers fail -> the CPU still works
      try {
        const t = await Cls.createFromOptions(files, { baseOptions: { modelAssetPath: `${base}/models/${model}`, delegate }, runningMode, ...extra });
        delegates[model] = delegate;
        return t;
      } catch (e) { if (delegate === 'CPU') throw e; }
    }
    return null;
  };
  people = Math.max(1, Math.min(2, people | 0 || 1));
  const tr = { mock: false, mode, body, hands, face, people, delegates, stats: { pose: [], hands: [], face: [] }, last: {} };
  tr.pose = body && await make(PoseLandmarker, quality === 'best' ? 'pose_landmarker_heavy.task' : 'pose_landmarker_full.task',
    { numPoses: Math.max(1, people + (mode === 'VIDEO' ? 1 : 0)), minPoseDetectionConfidence: 0.5, minPosePresenceConfidence: 0.5, minTrackingConfidence: 0.5, outputSegmentationMasks: false });
  tr.hands = hands && await make(HandLandmarker, 'hand_landmarker.task', { numHands: 2 * people, minHandDetectionConfidence: 0.4, minHandPresenceConfidence: 0.4, minTrackingConfidence: 0.4 });
  // a second hand reader for cut-outs around a wrist whose hand the full picture missed
  tr.handsCrop = hands && mode === 'VIDEO' && await make(HandLandmarker, 'hand_landmarker.task', { numHands: 1, minHandDetectionConfidence: 0.3, minHandPresenceConfidence: 0.3, minTrackingConfidence: 0.3 }, 'IMAGE');
  tr.face = face && await make(FaceLandmarker, 'face_landmarker.task', { numFaces: people, outputFaceBlendshapes: true, outputFacialTransformationMatrixes: true });
  tr.close = () => { for (const k of ['pose', 'hands', 'handsCrop', 'face']) try { tr[k] && tr[k].close(); } catch { /* gone */ } };
  return tr;
}

// ---------------------------------------------------------------- helpers
let cropCanvas = null;
function canvas(size) {
  if (!cropCanvas) cropCanvas = typeof document !== 'undefined' ? document.createElement('canvas') : new OffscreenCanvas(size, size);
  return cropCanvas;
}
function crop(src, sx, sy, sw, sh, size = 384) {
  const c = canvas(size);
  c.width = size; c.height = size;
  const g = c.getContext('2d', { willReadFrequently: false });
  g.clearRect(0, 0, size, size);
  g.drawImage(src, sx, sy, sw, sh, 0, 0, size, size);
  return c;
}

// Eye opening from the face mesh (lid gap / eye width), for the performer's left and right eye (unmirrored picture:
// the eye whose corners sit further right is the performer's left).
export function eyeOpenings(pts) {
  if (!pts || pts.length < 400) return [1, 1];
  const d = (a, b) => Math.hypot(pts[a].x - pts[b].x, pts[a].y - pts[b].y);
  const A = { up: 386, lo: 374, c1: 362, c2: 263 }, B = { up: 159, lo: 145, c1: 33, c2: 133 };
  const open = e => d(e.up, e.lo) / Math.max(1e-6, d(e.c1, e.c2));
  const ax = (pts[A.c1].x + pts[A.c2].x) / 2, bx = (pts[B.c1].x + pts[B.c2].x) / 2;
  return ax > bx ? [open(A), open(B)] : [open(B), open(A)];
}

const hipOf = lm => [(lm[23].x + lm[24].x) / 2, (lm[23].y + lm[24].y) / 2];
const boxSize = lm => { let x0 = 1, x1 = 0, y0 = 1, y1 = 0; for (const p of lm) { x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y); } return (x1 - x0) * (y1 - y0); };
const dist2 = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

// Which detected body is which person. One person: the one nearest to where the copied person was (else the
// biggest). Two people: on the first frame left to right in the picture; after that each keeps following the body
// nearest to where it was (the pairing with the smallest total jump). -> [detection index | -1 per person]
export function pickPeople(all, want, last) {
  const n = all.length;
  if (!n) return new Array(want).fill(-1);
  const cents = all.map(hipOf);
  if (want === 1) {
    if (n === 1) return [0];
    if (last.hip) return [cents.map((c, i) => [i, dist2(c, last.hip)]).sort((a, b) => a[1] - b[1])[0][0]];
    return [all.map((lm, i) => [i, boxSize(lm)]).sort((a, b) => b[1] - a[1])[0][0]];
  }
  const prev = last.hips;
  if (!prev) {
    // the two biggest bodies, left to right
    const big = all.map((lm, i) => [i, boxSize(lm)]).sort((a, b) => b[1] - a[1]).slice(0, want).map(x => x[0]);
    big.sort((a, b) => cents[a][0] - cents[b][0]);
    while (big.length < want) big.push(-1);
    return big;
  }
  let best = null;
  for (let i = -1; i < n; i++) {
    for (let j = -1; j < n; j++) {
      if (i >= 0 && i === j) continue;
      if (i < 0 && j < 0) continue;
      const miss = (i < 0 ? 1 : 0) + (j < 0 ? 1 : 0);
      const cost = (i >= 0 && prev[0] ? dist2(cents[i], prev[0]) : 0.5) + (j >= 0 && prev[1] ? dist2(cents[j], prev[1]) : 0.5) + miss * (n >= 2 ? 1 : 0.2);
      if (!best || cost < best.cost) best = { cost, pick: [i, j] };
    }
  }
  return best.pick;
}

// ---------------------------------------------------------------- one frame
// detectFrame(tracker, src, tMs, {W, H, image}) -> frame record (see the top)
export function detectFrame(tr, src, tMs, { W, H, image = false } = {}) {
  if (tr.mock) {
    const fr = src && src.record ? src.record() : null;
    return fr ? { ...fr, ms: { pose: 0, hands: 0, face: 0 } } : { pose: null, hands: { L: null, R: null }, face: null, people: 0, ms: {} };
  }
  // timestamps must go strictly up for each landmarker
  const ts = Math.max((tr.lastTs || 0) + 1, Math.round(tMs));
  tr.lastTs = ts;
  const run = (lm, s) => (image ? lm.detect(s) : lm.detectForVideo(s, ts));
  const want = Math.max(1, tr.people || 1);
  const W_ = W || src.videoWidth || src.naturalWidth || src.width || 1, H_ = H || src.videoHeight || src.naturalHeight || src.height || 1;
  const persons = Array.from({ length: want }, () => ({ pose: null, hands: { L: null, R: null }, face: null }));
  const out = { people: 0, ms: {} };
  let t0 = now();
  if (tr.pose) {
    const r = run(tr.pose, src);
    out.ms.pose = now() - t0;
    const all = r.landmarks || [], wl = r.worldLandmarks || [];
    out.people = all.length;
    const pick = pickPeople(all, want, tr.last);
    pick.forEach((k, p) => {
      if (k < 0) return;
      const lm = all[k], w = wl[k];
      const world = new Float32Array(132), img = new Float32Array(99);
      for (let j = 0; j < 33; j++) {
        const pw = w[j], q = lm[j];
        world[j * 4] = pw.x; world[j * 4 + 1] = pw.y; world[j * 4 + 2] = pw.z;
        world[j * 4 + 3] = Math.min(q.visibility ?? pw.visibility ?? 1, q.presence ?? 1);
        img[j * 3] = q.x; img[j * 3 + 1] = q.y; img[j * 3 + 2] = q.z;
      }
      persons[p].pose = { world, img };
    });
    if (want === 1) { if (persons[0].pose) tr.last.hip = hipOf(all[pick[0]]); }
    else tr.last.hips = pick.map((k, p) => (k >= 0 ? hipOf(all[k]) : (tr.last.hips ? tr.last.hips[p] : null)));
  }
  // hands: which is which comes from the nearest pose wrist, never from MediaPipe's "handedness" (it assumes a
  // mirrored selfie picture)
  if (tr.hands) {
    t0 = now();
    const r = run(tr.hands, src);
    out.ms.hands = now() - t0;
    const lms = r.landmarks || [], wls = r.worldLandmarks || [];
    const pack = w => { const a = new Float32Array(63); for (let j = 0; j < 21; j++) { a[j * 3] = w[j].x; a[j * 3 + 1] = w[j].y; a[j * 3 + 2] = w[j].z; } return a; };
    const wrist = (pe, s) => {
      const k = s === 'L' ? 15 : 16;
      return pe.pose && pe.pose.world[k * 4 + 3] >= 0.3 ? [pe.pose.img[k * 3], pe.pose.img[k * 3 + 1]] : null;
    };
    // every (person, side) wrist against every hand found: the nearest pairs first, at most 12% of the picture away
    const pairs = [];
    persons.forEach((pe, p) => { for (const s of ['L', 'R']) { const wr = wrist(pe, s); if (!wr) continue; lms.forEach((lm, i) => { const dd = Math.hypot(lm[0].x - wr[0], (lm[0].y - wr[1]) * H_ / W_); if (dd < 0.12) pairs.push([dd, p, s, i]); }); } });
    pairs.sort((a, b) => a[0] - b[0]);
    const takenHand = new Set(), takenWrist = new Set();
    for (const [, p, s, i] of pairs) {
      if (takenHand.has(i) || takenWrist.has(p + s)) continue;
      takenHand.add(i); takenWrist.add(p + s);
      persons[p].hands[s] = pack(wls[i]);
      (persons[p].handsImg = persons[p].handsImg || {})[s] = pack(lms[i]);
    }
    // a wrist whose hand the whole picture missed: read a cut-out around it (2.5 x the forearm)
    if (tr.handsCrop) persons.forEach((pe, p) => {
      for (const s of ['L', 'R']) {
        const wr = wrist(pe, s);
        if (!wr || takenWrist.has(p + s)) continue;
        const e = s === 'L' ? 13 : 14;
        const fx = (pe.pose.img[e * 3] - wr[0]) * W_, fy = (pe.pose.img[e * 3 + 1] - wr[1]) * H_;
        const size = Math.max(48, 2.5 * Math.hypot(fx, fy));
        const sx = wr[0] * W_ - size / 2, sy = wr[1] * H_ - size / 2;
        try {
          const rr = tr.handsCrop.detect(crop(src, sx, sy, size, size, 256));
          if (rr.worldLandmarks && rr.worldLandmarks[0]) pe.hands[s] = pack(rr.worldLandmarks[0]);
        } catch { /* keep going without it */ }
      }
    });
  }
  // face: one person - a small face in a full-body video is cut out (the head box x 2.2) and read at 384 x 384;
  // two people - both faces from the whole picture, each given to the person whose nose is nearest
  if (tr.face) {
    t0 = now();
    const readFace = (r, f) => {
      if (!r.faceBlendshapes || !r.faceBlendshapes[f]) return null;
      const bs = new Float32Array(52);
      for (const c of r.faceBlendshapes[f].categories) { const k = BS[c.categoryName]; if (k !== undefined) bs[k] = c.score; }
      const m = r.facialTransformationMatrixes && r.facialTransformationMatrixes[f] ? Float32Array.from(r.facialTransformationMatrixes[f].data) : null;
      const [eyeL, eyeR] = eyeOpenings(r.faceLandmarks && r.faceLandmarks[f]);
      return m ? { bs, m, eyeL, eyeR } : null;
    };
    try {
      if (want === 1) {
        const pe = persons[0];
        let target = src;
        if (pe.pose) {
          const ids = [0, 2, 5, 7, 8];
          let x0 = 1, x1 = 0, y0 = 1, y1 = 0;
          for (const j of ids) { x0 = Math.min(x0, pe.pose.img[j * 3]); x1 = Math.max(x1, pe.pose.img[j * 3]); y0 = Math.min(y0, pe.pose.img[j * 3 + 1]); y1 = Math.max(y1, pe.pose.img[j * 3 + 1]); }
          const side = Math.max((x1 - x0) * W_, (y1 - y0) * H_) * 2.2;
          if (side < 0.3 * H_) {
            const cx = (x0 + x1) / 2 * W_, cy = (y0 + y1) / 2 * H_;
            target = crop(src, cx - side / 2, cy - side / 2, side, side, 384);
          }
        }
        pe.face = readFace(run(tr.face, target), 0);
      } else {
        const r = run(tr.face, src);
        const faces = (r.faceLandmarks || []).map((pts, f) => { let x = 0, y = 0; for (const q of pts) { x += q.x; y += q.y; } return [f, [x / pts.length, y / pts.length]]; });
        const used = new Set();
        persons.forEach(pe => {
          if (!pe.pose) return;
          const nose = [pe.pose.img[0], pe.pose.img[1]];
          let best = -1, bd = 0.15;
          for (const [f, c] of faces) { if (used.has(f)) continue; const d = dist2(c, nose); if (d < bd) { bd = d; best = f; } }
          if (best >= 0) { used.add(best); pe.face = readFace(r, best); }
        });
      }
    } catch { /* a face that can't be read this frame */ }
    out.ms.face = now() - t0;
  }
  for (const k of ['pose', 'hands', 'face']) if (out.ms[k] !== undefined && tr.stats && tr.stats[k]) tr.stats[k].push(out.ms[k]);
  const first = persons[0];
  const rec = { pose: first.pose, hands: first.hands, face: first.face, people: out.people, ms: out.ms };
  if (first.handsImg) rec.handsImg = first.handsImg;
  if (want > 1) rec.others = persons.slice(1);
  return rec;
}

// ---------------------------------------------------------------- the stand-in's frames (mock tracker)
// The frame index of a take at time t (seconds from its start).
export function frameIndexAt(T, t) {
  const t0 = T[0];
  let lo = 0, hi = T.length - 1;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (T[m] - t0 <= t + 1e-6) lo = m; else hi = m - 1; }
  return lo;
}
// The frame record of a take's frame i (what the stand-in tracker "sees"): person 1 at the top, person 2 in others.
export function recordAt(take, i) {
  const one = pe => {
    const sl = (a, w) => a.slice(i * w, (i + 1) * w);
    return {
      pose: { world: sl(pe.pose, 132), img: sl(pe.img, 99) },
      hands: { L: pe.hand.Lok[i] ? sl(pe.hand.L, 63) : null, R: pe.hand.Rok[i] ? sl(pe.hand.R, 63) : null },
      face: pe.face.ok[i] ? { bs: sl(pe.face.bs, 52), m: sl(pe.face.m, 16), eyeL: pe.face.eyeL[i], eyeR: pe.face.eyeR[i] } : null,
    };
  };
  const rec = { ...one(take.people[0]), people: take.people.length };
  if (take.people.length > 1) rec.others = take.people.slice(1).map(one);
  return rec;
}

// ---------------------------------------------------------------- records through postMessage
// The typed arrays of a record (so they move to the other thread instead of being copied).
export function transferables(fr) {
  const out = [];
  const one = p => {
    if (!p) return;
    if (p.pose) out.push(p.pose.world.buffer, p.pose.img.buffer);
    for (const s of ['L', 'R']) { if (p.hands && p.hands[s]) out.push(p.hands[s].buffer); if (p.handsImg && p.handsImg[s]) out.push(p.handsImg[s].buffer); }
    if (p.face) out.push(p.face.bs.buffer, p.face.m.buffer);
  };
  one(fr);
  for (const o of fr.others || []) one(o);
  return [...new Set(out)];
}
