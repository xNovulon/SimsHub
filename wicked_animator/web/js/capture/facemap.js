// Face capture: MediaPipe's 52 expression scores -> the app's face sliders (capture.md section 6). The result is
// slider values in keys (key.face), so everything stays editable in the Face step and talking and blinking still mix
// on top; the hand-posed face (key.faceBones) is never touched.
import * as THREE from 'three';

// MediaPipe FaceLandmarker blendshape order (index 0 '_neutral' is ignored; there is no tongueOut): kept in detect.js,
// which the reader's worker thread shares.
import { BS_NAMES, BS } from './detect.js';
export { BS_NAMES, BS };
// every Left name with its Right partner (for the left/right self-check)
const PAIRS = BS_NAMES.filter(nm => /Left$/.test(nm)).map(nm => [BS[nm], BS[nm.replace(/Left$/, 'Right')]]);

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
function percentile(arr, p) {
  if (!arr.length) return 0;
  const s = Array.from(arr).sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.max(0, Math.round((s.length - 1) * p)))];
}
function corr(a, b) {
  const n = a.length;
  if (n < 3) return 0;
  let ma = 0, mb = 0;
  for (let i = 0; i < n; i++) { ma += a[i]; mb += b[i]; }
  ma /= n; mb /= n;
  let sab = 0, saa = 0, sbb = 0;
  for (let i = 0; i < n; i++) { const x = a[i] - ma, y = b[i] - mb; sab += x * y; saa += x * x; sbb += y * y; }
  return saa > 1e-9 && sbb > 1e-9 ? sab / Math.sqrt(saa * sbb) : 0;
}

// 6.5 left/right self-check: each eye's opening measured from the face points (for the eye whose corners sit further
// right in the picture - the performer's left in an unmirrored picture) must go down when eyeBlinkLeft goes up. If it
// matches eyeBlinkRight better, every Left/Right pair is swapped. Returns true when it swapped.
export function checkLeftRight(face, frames) {
  const open = [], bl = [], br = [];
  for (const i of frames) { open.push(face.eyeL[i]); bl.push(face.bs[i * 52 + BS.eyeBlinkLeft]); br.push(face.bs[i * 52 + BS.eyeBlinkRight]); }
  const cl = corr(open, bl), cr = corr(open, br);
  // opening and blinking go opposite ways: the more negative correlation is the real partner
  if (cr < cl - 0.2 && cr < -0.3) {
    for (const i of frames) for (const [a, b] of PAIRS) {
      const x = face.bs[i * 52 + a]; face.bs[i * 52 + a] = face.bs[i * 52 + b]; face.bs[i * 52 + b] = x;
    }
    return true;
  }
  return false;
}

// faceTrack(take, person, {calibrate: [t0, t1] | null, exaggerate, psi, relativeHead}) ->
//   { faces: [{eyes, squint, ...} | null], headDelta: [Quaternion | null], found, swapped, ok, message }
// ok = false (and every face null) when the face was found in less than half of the frames.
export function faceTrack(take, person = 0, { calibrate = null, exaggerate = 1, psi = 0, relativeHead = true, wink = true, still = false } = {}) {
  const pe = take.people[person];
  const n = take.t.length;
  const face = pe && pe.face;
  const out = { faces: new Array(n).fill(null), headDelta: new Array(n).fill(null), found: 0, swapped: false, ok: false, message: '' };
  if (!face || !n) { out.message = 'No face in this take.'; return out; }
  const seen = [];
  for (let i = 0; i < n; i++) if (face.ok[i]) seen.push(i);
  out.found = seen.length / n;
  if (out.found < 0.5 || (still && !seen.length)) {
    out.message = 'Your face was too small or turned away for most of the video; the face was left as it was.';
    return out;
  }
  // work on a copy (the self-check may swap sides)
  const bs = Float32Array.from(face.bs);
  const f2 = { ...face, bs };
  out.swapped = checkLeftRight(f2, seen);
  // calibration: the first 2 s of a face take ("look at the camera with a relaxed face"), or else the 10th
  // percentile over the whole take
  let calFrames = seen;
  if (calibrate) {
    const [t0, t1] = calibrate;
    const c = seen.filter(i => take.t[i] - take.t[0] >= t0 && take.t[i] - take.t[0] <= t1);
    if (c.length >= 5) calFrames = c;
  }
  const base = new Float32Array(52), p95 = new Float32Array(52);
  for (let k = 1; k < 52; k++) {
    const col = seen.map(i => bs[i * 52 + k]);
    const calCol = calFrames.map(i => bs[i * 52 + k]);
    // a photo (one frame) can't calibrate against itself: the scores are used as they are
    base[k] = still ? (k === BS.eyeBlinkLeft || k === BS.eyeBlinkRight ? 0.1 : 0)
      : calibrate && calFrames !== seen ? calCol.reduce((a, b) => a + b, 0) / Math.max(1, calCol.length) : percentile(col, 0.1);
    p95[k] = still ? 0.45 : percentile(col, 0.95);
  }
  const cal = (i, name) => {
    const k = BS[name], raw = bs[i * 52 + k], b = Math.min(0.95, base[k]);
    return clamp((raw - b) / (1 - b), 0, 1);
  };
  const blink = (i, name) => {
    const k = BS[name], open = base[k], closed = Math.max(0.45, p95[k]);
    return clamp((bs[i * 52 + k] - open) / Math.max(0.05, closed - open), 0, 1);
  };
  const ex = v => v * exaggerate;
  const r2 = v => Math.round(v * 1000) / 1000;
  const avg = (i, a, b) => 0.5 * (cal(i, a) + cal(i, b));
  for (const i of seen) {
    const nL = blink(i, 'eyeBlinkLeft'), nR = blink(i, 'eyeBlinkRight');
    const wide = avg(i, 'eyeWideLeft', 'eyeWideRight');
    const eyes = clamp((wink ? Math.min(nL, nR) : 0.5 * (nL + nR)) - 0.35 * wide, -0.3, 1);
    const open = clamp(ex((bs[i * 52 + BS.jawOpen] - 0.03) / 0.55), 0, 1);
    const f = {
      eyes,
      squint: clamp(ex(1.2 * avg(i, 'eyeSquintLeft', 'eyeSquintRight')), 0, 1),
      brows: clamp(ex(1.3 * avg(i, 'browOuterUpLeft', 'browOuterUpRight') - 1.3 * avg(i, 'browDownLeft', 'browDownRight')), -1, 1),
      inner: clamp(ex(1.4 * cal(i, 'browInnerUp')), 0, 1),
      smile: clamp(ex(1.3 * avg(i, 'mouthSmileLeft', 'mouthSmileRight') - 1.2 * avg(i, 'mouthFrownLeft', 'mouthFrownRight')), -1, 1),
      open,
      pout: clamp(ex(1.2 * Math.max(cal(i, 'mouthPucker'), 0.8 * cal(i, 'mouthFunnel'))), 0, 1),
      bite: clamp(ex(1.5 * cal(i, 'mouthRollLower') * (1 - open)), 0, 1),
      lookUp: clamp(2 * (avg(i, 'eyeLookUpLeft', 'eyeLookUpRight') - avg(i, 'eyeLookDownLeft', 'eyeLookDownRight')) * (1 - Math.max(0, eyes)), -1, 1),
      lookSide: clamp(2 * 0.5 * ((cal(i, 'eyeLookOutLeft') + cal(i, 'eyeLookInRight')) - (cal(i, 'eyeLookInLeft') + cal(i, 'eyeLookOutRight'))), -1, 1),
      // the one-sided channels (they read 0 on a symmetric face)
      wink: clamp(nL - nR, -1, 1),
      smileSide: clamp(ex(0.65 * (cal(i, 'mouthSmileLeft') - cal(i, 'mouthSmileRight'))), -1, 1),
      browSide: clamp(ex(0.65 * (cal(i, 'browOuterUpLeft') - cal(i, 'browOuterUpRight')) - 0.65 * (cal(i, 'browDownLeft') - cal(i, 'browDownRight'))), -1, 1),
      sneer: clamp(ex(avg(i, 'noseSneerLeft', 'noseSneerRight')), 0, 1),
      jawSide: clamp(1.5 * (cal(i, 'jawLeft') - cal(i, 'jawRight')), -1, 1),
      puff: clamp(ex(cal(i, 'cheekPuff')), 0, 1),
    };
    if (take.tongue && take.tongue.some(x => x > 0.01)) f.tongue = clamp(take.tongue[i], 0, 1);
    for (const k of Object.keys(f)) f[k] = r2(f[k]);
    out.faces[i] = f;
  }
  // fill frames without a face from the nearest ones (so keys never jump to a blank face)
  let last = null;
  for (let i = 0; i < n; i++) { if (out.faces[i]) last = out.faces[i]; else if (last) out.faces[i] = { ...last }; }
  last = null;
  for (let i = n - 1; i >= 0; i--) { if (out.faces[i]) last = out.faces[i]; else if (last) out.faces[i] = { ...last }; }
  // the head's own turn from the face (6.4): relative to the calibration frames for a face-only take
  const rotY = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), psi);
  const R = i => {
    const M = new THREE.Matrix4().fromArray(face.m.subarray(i * 16, i * 16 + 16));
    return rotY.clone().multiply(new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().extractRotation(M)).normalize());
  };
  let neutralInv = new THREE.Quaternion();
  if (relativeHead) {
    // average of the calibration frames (quaternions kept in one hemisphere)
    const acc = new THREE.Vector4();
    let ref = null;
    for (const i of calFrames) {
      const q = R(i);
      if (!ref) ref = q.clone();
      const s = q.dot(ref) < 0 ? -1 : 1;
      acc.x += s * q.x; acc.y += s * q.y; acc.z += s * q.z; acc.w += s * q.w;
    }
    neutralInv = new THREE.Quaternion(acc.x, acc.y, acc.z, acc.w).normalize().invert();
  }
  for (const i of seen) out.headDelta[i] = R(i).multiply(neutralInv);
  out.ok = true;
  return out;
}
