// Faces: sliders (eyes closed, smile, mouth open...) and one-click expressions, keyed like poses, added on top of
// the face posed by hand (key.faceBones). Talking moves the mouth by itself while a voice sound plays.
// Face bones in the Sims 4 rig: local x = up, y = forward, z = the sim's left (jaw: x down, z right; the lower lips
// and the tongue sit under the jaw and another half turn, so their frame is the head frame again).
// Everything the sliders, blinking, talking and the jaw do is recorded as the sim's automatic layer
// (Sim.addLayer), so it can be taken off again when the hand-posed face is keyed.
import * as THREE from 'three';

// `more: true`: the extra channels (one-sided faces and more expression), shown under "More".
export const FACE_SLIDERS = {
  eyes: { label: 'Eyes closed', min: -0.3, max: 1 },
  squint: { label: 'Squint', min: 0, max: 1 },
  brows: { label: 'Brows (down ↔ up)', min: -1, max: 1 },
  inner: { label: 'Worried / pleasure brows', min: 0, max: 1 },
  smile: { label: 'Smile (frown ↔ smile)', min: -1, max: 1 },
  open: { label: 'Mouth open', min: 0, max: 1 },
  pout: { label: 'O mouth / kiss', min: 0, max: 1 },
  bite: { label: 'Bite lip', min: 0, max: 1 },
  tongue: { label: 'Tongue out', min: 0, max: 1 },
  lookUp: { label: 'Look (down ↔ up)', min: -1, max: 1 },
  lookSide: { label: 'Look (right ↔ left)', min: -1, max: 1 },
  wink: { label: 'Wink (right eye ↔ left eye)', min: -1, max: 1, more: true },
  smileSide: { label: 'Smile on one side (right ↔ left)', min: -1, max: 1, more: true },
  browSide: { label: 'One brow up (right ↔ left)', min: -1, max: 1, more: true },
  browTilt: { label: 'Brow tilt (angry ↔ sad)', min: -1, max: 1, more: true },
  sneer: { label: 'Sneer', min: 0, max: 1, more: true },
  jawSide: { label: 'Jaw to the side (right ↔ left)', min: -1, max: 1, more: true },
  puff: { label: 'Puff cheeks', min: 0, max: 1, more: true },
};

// One-click expressions. Tuned on the creators' faces (wave2/bone_stats.md): brows, cheeks and mouth corners move
// as far as creators move them, with a tilt to the brows and a little asymmetry where a real face has it.
export const FACE_PRESETS = {
  neutral: { label: 'Neutral', face: {} },
  relaxed: { label: 'Relaxed', face: { eyes: 0.2, smile: 0.15, inner: 0.1 } },
  smile: { label: 'Smile', face: { smile: 0.8, squint: 0.3, eyes: 0.1, brows: 0.15 } },
  seductive: { label: 'Seductive', face: { eyes: 0.45, smile: 0.3, smileSide: 0.25, browSide: 0.2, brows: 0.1, lookUp: -0.2 } },
  pleasure: { label: 'Pleasure', face: { eyes: 0.6, inner: 0.75, browTilt: 0.45, open: 0.3, squint: 0.3 } },
  moan: { label: 'Moaning', face: { eyes: 0.55, inner: 0.85, browTilt: 0.55, open: 0.55, pout: 0.25 } },
  ecstasy: { label: 'O face', face: { eyes: 0.85, inner: 1, browTilt: 0.7, open: 0.7, pout: 0.6, squint: 0.15 } },
  bite: { label: 'Biting lip', face: { bite: 1, eyes: 0.35, smile: 0.25, smileSide: 0.2, inner: 0.35, browTilt: 0.3 } },
  surprised: { label: 'Surprised', face: { brows: 1, open: 0.45, eyes: -0.25 } },
  intense: { label: 'Intense', face: { brows: -0.6, browTilt: -0.4, squint: 0.8, sneer: 0.3, open: 0.25, eyes: 0.3 } },
  tongue: { label: 'Tongue out', face: { tongue: 1, open: 0.6, eyes: 0.3, inner: 0.4, browTilt: 0.3 } },
  ahegao: { label: 'Ahegao', face: { tongue: 1, open: 0.8, lookUp: 0.85, eyes: 0.15, inner: 1, browTilt: 0.8 } },
  kiss: { label: 'Kiss', face: { pout: 1, eyes: 0.9 } },
  sleepy: { label: 'Eyes shut', face: { eyes: 1 } },
};

const deg = THREE.MathUtils.degToRad;
const X = new THREE.Vector3(1, 0, 0), Y = new THREE.Vector3(0, 1, 0), Z = new THREE.Vector3(0, 0, 1), NZ = new THREE.Vector3(0, 0, -1);
const _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _v = new THREE.Vector3();
const clamp01 = x => Math.min(1, Math.max(0, x));

function rot(v, name, axis, degrees) {
  const b = v.byName[name];
  if (b && degrees) {
    b.quaternion.multiply(_q.setFromAxisAngle(axis, deg(degrees)));
    if (v.addLayer) v.addLayer(name, _q, null);
  }
}
function move(v, name, up, fwd, left) {
  const b = v.byName[name];
  if (b) {
    b.position.x += up; b.position.y += fwd; b.position.z += left;
    if (v.addLayer && (up || fwd || left)) v.addLayer(name, null, _v.set(up, fwd, left));
  }
}

// Apply face settings (added on top of whatever the bones are doing). `style` is the project's face style:
// 'creator' (new projects: brows, cheeks and mouth corners move as far as creators move them, with lip curl and
// corner roll) or 'classic' (projects made before: exactly the look they always had). Missing: the view's own
// `faceStyle`, else 'creator'.
export function applyFace(v, f, style) {
  if (!f) return;
  const creator = (style || v.faceStyle || 'creator') !== 'classic';
  const g = k => f[k] || 0;
  const eyes = g('eyes'), squint = g('squint'), brows = g('brows'), inner = g('inner'), smile = g('smile');
  const open = g('open'), pout = g('pout'), bite = g('bite'), tongue = g('tongue'), lookUp = g('lookUp'), lookSide = g('lookSide');
  const wink = g('wink'), smileSide = g('smileSide'), browSide = g('browSide'), browTilt = g('browTilt');
  const sneer = g('sneer'), jawSide = g('jawSide'), puff = g('puff');
  for (const s of ['L', 'R']) {
    const side = s === 'L' ? 1 : -1;
    const eyesS = eyes + Math.max(0, side * wink);             // a wink closes one eye more
    const browsS = brows + side * browSide, smileS = smile + side * smileSide;
    rot(v, `b__${s}_UpLid__`, Z, 40 * eyesS + 6 * squint - 12 * Math.max(0, lookUp) * (1 - eyesS));
    rot(v, `b__${s}_LoLid__`, Z, -(8 * Math.max(0, eyesS) + 14 * squint));
    if (creator) {
      move(v, `b__${s}_Squint__`, 0.021 * squint, 0, 0);
      move(v, `b__${s}_Cheek__`, 0.012 * Math.max(0, smileS) + 0.007 * squint + 0.002 * sneer, 0.001 * puff, side * 0.004 * puff);
      move(v, `b__${s}_InBrow__`, 0.012 * browsS + 0.022 * inner - 0.002 * sneer, 0, -side * 0.004 * Math.max(0, -browsS) - side * 0.001 * sneer);
      rot(v, `b__${s}_InBrow__`, Y, -side * 30 * browTilt);   // + lifts the inner end (worried / pleasure)
      move(v, `b__${s}_MidBrow__`, (browsS > 0 ? 0.012 : 0.030) * browsS + 0.004 * inner, 0, 0);
      move(v, `b__${s}_OutBrow__`, 0.009 * browsS - 0.004 * inner, 0, 0);
      // mouth corners: up and out for a smile (rolling up at the outer end), down for a frown, in for an O
      move(v, `b__${s}_Mouth__`, (smileS > 0 ? 0.009 : 0.016) * smileS, -0.003 * Math.abs(smileS),
        side * (0.009 * Math.max(0, smileS) - 0.003 * Math.max(0, -smileS) - 0.009 * pout + 0.001 * puff));
      rot(v, `b__${s}_Mouth__`, Y, side * 20 * smileS);
      move(v, `b__${s}_UpLip__`, 0.006 * sneer, 0.005 * pout, -side * 0.003 * pout);
      rot(v, `b__${s}_UpLip__`, Z, -15 * pout);                // lips curl out for an O
      move(v, `b__${s}_LoLip__`, 0.004 * bite, 0.005 * pout - 0.003 * bite, -side * 0.003 * pout);
      rot(v, `b__${s}_LoLip__`, Z, 15 * pout - 15 * bite);
    } else {
      move(v, `b__${s}_Squint__`, 0.004 * squint, 0, 0);
      move(v, `b__${s}_Cheek__`, 0.003 * Math.max(0, smileS) + 0.002 * squint + 0.002 * sneer, 0.001 * puff, side * 0.004 * puff);
      move(v, `b__${s}_InBrow__`, 0.005 * browsS + 0.006 * inner - 0.002 * sneer, 0, -side * 0.002 * Math.max(0, -browsS) - side * 0.001 * sneer);
      rot(v, `b__${s}_InBrow__`, Y, -side * 30 * browTilt);
      move(v, `b__${s}_MidBrow__`, 0.004 * browsS + 0.002 * inner, 0, 0);
      move(v, `b__${s}_OutBrow__`, 0.003 * browsS - 0.002 * inner, 0, 0);
      // mouth corners: up and out for a smile, in for an O (they also come down with the jaw - see followJaw)
      move(v, `b__${s}_Mouth__`, 0.006 * smileS, -0.002 * Math.abs(smileS), side * (0.004 * smileS - 0.006 * pout) + side * 0.001 * puff);
      move(v, `b__${s}_UpLip__`, 0.003 * sneer, 0.003 * pout, -side * 0.002 * pout);
      move(v, `b__${s}_LoLip__`, 0.003 * bite, 0.003 * pout - 0.002 * bite, -side * 0.002 * pout);
    }
    rot(v, `b__${s}_Eye__`, Z, -22 * lookUp);
    rot(v, `b__${s}_Eye__`, X, 22 * lookSide);
  }
  // opening the mouth is the lower jaw dropping; the upper lip belongs to the skull and stays (as in the game)
  if (creator) {
    move(v, 'b__UpLip__', 0.001 * pout, 0.007 * pout, 0);
    rot(v, 'b__UpLip__', Z, -25 * pout);
    move(v, 'b__LoLip__', 0.005 * bite, 0.008 * pout - 0.004 * bite, 0.002 * jawSide);
    rot(v, 'b__LoLip__', Z, 25 * pout - 25 * bite);
  } else {
    move(v, 'b__UpLip__', 0.001 * pout, 0.004 * pout, 0);
    move(v, 'b__LoLip__', 0.004 * bite, 0.004 * pout - 0.003 * bite, 0.002 * jawSide);
  }
  rot(v, 'b__Jaw__', NZ, 24 * open + 8 * pout + 10 * tongue);
  rot(v, 'b__Jaw__', X, -8 * jawSide);                         // the jaw's x points down: + swings the chin right
  move(v, 'b__Tounge__1', 0, 0.045 * tongue, 0);
  rot(v, 'b__Tounge__2', NZ, -10 * tongue);
}

// ---------------------------------------------------------------- safety
// The signed turn of a bone about its local z, relative to rest (degrees).
function zTurn(v, name) {
  const b = v.byName[name], r = v.restByName && v.restByName[name];
  if (!b || !r) return 0;
  return zTurnOf(r.quat, b.quaternion);
}
function zTurnOf(restQ, q) {
  const d = _q2.copy(restQ).invert().multiply(q);
  const s = d.w < 0 ? -1 : 1;
  return THREE.MathUtils.radToDeg(2 * Math.atan2(s * d.z, s * d.w));
}
const LID_JAW = [
  ...['L', 'R'].flatMap(s => [[`b__${s}_UpLid__`, -15, 46], [`b__${s}_LoLid__`, -40, 22]]),
  ['b__Jaw__', -40, 3],
];
// After the whole face stage: keep the upper lids, lower lids and the jaw inside what a face can do, so stacked
// blinks, sliders and hand-posed lids never pass through each other. The correction is part of the automatic layer.
// A lid or jaw keyed past the safe range on purpose (Alt, a game face, an imported creator clip) keeps its keyed
// value: only what the automatic layers add on top of it is held back. A bone no layer touched is left as keyed.
export function clampFace(v) {
  for (const [n, lo0, hi0] of LID_JAW) {
    const d = v.layerDelta && v.layerDelta.get(n);
    if (v.layerDelta && !d) continue;
    let lo = lo0, hi = hi0;
    if (d && !d.abs && typeof v._base === 'function' && v.restByName && v.restByName[n]) {
      const k = zTurnOf(v.restByName[n].quat, v._base(n).q);
      lo = Math.min(lo, k); hi = Math.max(hi, k);
    }
    const t = zTurn(v, n);
    const c = Math.min(hi, Math.max(lo, t));
    if (Math.abs(c - t) < 1e-6) continue;
    rot(v, n, Z, c - t);
  }
}

// The bone as the keys have it and its automatic layer: {q, p, dq, dp}.
function baseAndLayer(v, name) {
  const b = v.byName[name];
  const base = v._base ? v._base(name) : { q: b.quaternion.clone(), p: b.position.clone() };
  const d = v.layerDelta && v.layerDelta.get(name);
  return { q: base.q, p: base.p, d: d && !d.abs ? d : null };
}
// Put a keyed value back with the automatic layer on top (final = base * layer).
function setBase(v, name, q, p) {
  const b = v.byName[name];
  const d = v.layerDelta && v.layerDelta.get(name);
  const on = d && !d.abs;
  if (q) { b.quaternion.copy(q); if (on) b.quaternion.multiply(d.q); }
  if (p) { b.position.copy(p); if (on) b.position.add(d.p); }
}

// Keep one face bone's keyed value (without the automatic layer) inside its safe range, axis by axis: moves per
// axis, turns as a small-angle XYZ Euler of rest^-1 * base. Locked axes (null) are left as they are. `limits` is
// bones.faceLimits(name). Returns true when it had to stop the bone.
export function clampFaceBone(v, name, limits) {
  const b = v.byName[name], r = v.restByName && v.restByName[name];
  if (!b || !r || !limits) return false;
  const { q, p } = baseAndLayer(v, name);
  const d = p.clone().sub(r.pos);
  let moved = false, turned = false;
  ['x', 'y', 'z'].forEach((ax, i) => {
    const lim = limits.move && limits.move[i];
    if (!lim) return;
    const c = Math.min(lim[1], Math.max(lim[0], d[ax]));
    if (Math.abs(c - d[ax]) > 1e-9) { d[ax] = c; moved = true; }
  });
  const e = new THREE.Euler().setFromQuaternion(r.quat.clone().invert().multiply(q), 'XYZ');
  ['x', 'y', 'z'].forEach((ax, i) => {
    const lim = limits.turn && limits.turn[i];
    if (!lim) return;
    const c = Math.min(lim[1], Math.max(lim[0], e[ax]));
    if (Math.abs(c - e[ax]) > 1e-7) { e[ax] = c; turned = true; }
  });
  if (!moved && !turned) return false;
  setBase(v, name, turned ? r.quat.clone().multiply(new THREE.Quaternion().setFromEuler(e)) : null, moved ? r.pos.clone().add(d) : null);
  return true;
}

// Aim an eye at a point (world space), inside its safe range: yaw about x (+ looks to the sim's left), pitch about
// z (+ looks down). The eye's rest frame is the head frame. `limits` is bones.faceLimits(eyeName) (optional).
export function aimEye(v, eyeName, targetWorld, limits) {
  const eye = v.byName[eyeName], r = v.restByName && v.restByName[eyeName];
  if (!eye || !r) return;
  eye.parent.updateWorldMatrix(true, false);
  const local = eye.parent.worldToLocal(targetWorld.clone()).sub(r.pos);
  const tx = (limits && limits.turn && limits.turn[0]) || [-deg(32), deg(32)];
  const tz = (limits && limits.turn && limits.turn[2]) || [-deg(30), deg(30)];
  const yaw = Math.min(tx[1], Math.max(tx[0], Math.atan2(local.z, local.y)));
  const pitch = Math.min(tz[1], Math.max(tz[0], -Math.atan2(local.x, Math.hypot(local.y, local.z))));
  const base = r.quat.clone().multiply(new THREE.Quaternion().setFromAxisAngle(X, yaw)).multiply(new THREE.Quaternion().setFromAxisAngle(Z, pitch));
  setBase(v, eyeName, base, null);
}

// Symmetry for a middle face bone (upper and lower lip middles, jaw, tongue): drop its sideways part - no turn
// about x or y, no move along z - so the middle of the mouth stays in the middle.
export function symmetrize(v, name) {
  const b = v.byName[name], r = v.restByName && v.restByName[name];
  if (!b || !r) return;
  const { q, p } = baseAndLayer(v, name);
  const rel = r.quat.clone().invert().multiply(q);
  const sym = new THREE.Quaternion(0, 0, rel.z, rel.w);
  if (sym.lengthSq() < 1e-12) sym.identity(); else sym.normalize();
  const d = p.clone().sub(r.pos);
  setBase(v, name, r.quat.clone().multiply(sym), r.pos.clone().add(new THREE.Vector3(d.x, d.y, 0)));
}

// Mirror one face bone's keyed value onto another (relative to rest, the one rule of spec_face_bones section 1):
// a turn (x, y, z, w) becomes (-x, -y, z, w), a move (x, y, z) becomes (x, y, -z). The target keeps its own
// automatic layer. A middle bone mirrored onto itself is symmetrized.
export function mirrorFaceBone(v, from, to = from) {
  if (from === to) return symmetrize(v, from);
  const rf = v.restByName && v.restByName[from], rt = v.restByName && v.restByName[to];
  if (!rf || !rt || !v.byName[from] || !v.byName[to]) return;
  const { q, p } = baseAndLayer(v, from);
  const rel = rf.quat.clone().invert().multiply(q);
  const d = p.clone().sub(rf.pos);
  setBase(v, to, rt.quat.clone().multiply(new THREE.Quaternion(-rel.x, -rel.y, rel.z, rel.w)), rt.pos.clone().add(new THREE.Vector3(d.x, d.y, -d.z)));
}

// How far the hand-posed face already has the mouth open and the eyes shut (read before the sliders go on):
// {jaw: 0..1 (20 degrees open = 1), lids: 0..1 (40 degrees shut = 1)}. Talking and blinking give way by that much.
export function keyedAmounts(v) {
  const open = -zTurn(v, 'b__Jaw__');
  const lids = Math.max(zTurn(v, 'b__L_UpLid__'), zTurn(v, 'b__R_UpLid__'));
  return { jaw: clamp01(open / 20), lids: clamp01(lids / 40) };
}

// ---------------------------------------------------------------- talking
// Voice sounds (moans, words) make the mouth move while they play. How long one lasts, in frames: `sec` (its real
// length, when known - e.g. from the game's voice-line list) wins; else a name ending in "_45f" lasts 45 frames;
// else about 1.1 s.
export function voiceLength(name, fps = 30, sec = 0) {
  if (sec > 0 && Number.isFinite(sec)) return Math.max(1, Math.round(sec * fps));
  const m = /_(\d+)f$/i.exec(name || '');
  return m ? +m[1] : Math.round(fps * 1.1);
}

// Real lengths of voice lines (name -> seconds), for talking in creator-style projects only (classic projects, made
// before, keep exactly the talking they had). `src`: a Map, a {name: sec} object, a [{name, sec}] list, or a
// function name -> sec (read each time, e.g. the Sounds feature's app.voiceSec once /api/voices has arrived). Empty
// until someone sets it.
let VOICE_SEC = () => 0;
export function setVoiceSeconds(src) {
  if (!src) { VOICE_SEC = () => 0; return; }
  if (typeof src === 'function') { VOICE_SEC = n => +src(n) || 0; return; }
  const m = new Map();
  const entries = src instanceof Map ? src.entries() : Array.isArray(src) ? src.map(x => [x && x.name, x && x.sec]) : Object.entries(src);
  for (const [n, s] of entries) if (n && s > 0) m.set(n, +s);
  VOICE_SEC = n => m.get(n) || 0;
}
export function voiceSeconds(name) { return VOICE_SEC(name) || 0; }

// An overlay on the keyed face (talking, blinking): its plain values are what it shows right now on a neutral
// face ({eyes: 0.9} half way through a blink), and it also carries - hidden from Object.entries/JSON - `to`, the
// face it pulls toward, and `weight`, how strongly right now. mergeFace blends with those.
function overlay(weight, to) {
  const out = {};
  for (const [k, x] of Object.entries(to)) out[k] = x * weight;
  Object.defineProperty(out, 'to', { value: to });
  Object.defineProperty(out, 'weight', { value: weight });
  return out;
}
// The same overlay, `f` times as strong (0..1): talking and blinking giving way to a hand-posed mouth or lids.
export function fadeOverlay(o, f) {
  if (!o) return o;
  return overlay((o.weight ?? 1) * clamp01(f), o.to || o);
}

// Mouth movement at `frame` from the sim's voice sounds (an overlay that swells and fades with the sound), or null.
// A voice sound the face was lip-synced to (`lipsync: true`) is left out: its face keys already move the mouth.
// `style` is the project's face style: in 'creator' projects a voice line talks for as long as it really plays (its
// `sec`, else setVoiceSeconds); 'classic' projects and callers that do not say keep the old length rule exactly.
export function talkAt(sim, frame, length, loop, fps = 30, style = null) {
  const cues = (sim.sounds || []).filter(s => s.kind === 'voice' && !s.lipsync);
  if (!cues.length || sim.body?.talk?.mouth === false) return null;
  const real = style === 'creator';
  let best = null, bestOpen = -1;
  for (const c of cues) {
    const len = voiceLength(c.name, fps, real ? (c.sec || VOICE_SEC(c.name)) : 0);
    let t = frame - c.frame;
    if (loop && t < 0) t += length;
    if (t < 0 || t > len) continue;
    const u = t / len;
    const env = Math.sin(Math.PI * Math.min(1, u * 1.15));             // swell and fade
    const syll = 0.55 + 0.45 * Math.sin(2 * Math.PI * (t / fps) * 4.2 + c.frame);   // ~4 syllables a second
    const moan = /moan|oj|ah|oh|breath|sigh/i.test(c.name);
    const to = { open: moan ? 0.55 : 0.4 * syll + 0.1, pout: moan ? 0.25 : 0.15 * (1 - syll), inner: moan ? 0.6 : 0.2 };
    if (moan) to.eyes = 0.35;                                             // moans half-close the eyes; words leave them
    if (env * to.open > bestOpen) { bestOpen = env * to.open; best = overlay(Math.max(0, env), to); }
  }
  return best;
}

// Put an overlay (talking, blinking) on top of the keyed face. Each channel moves from the keyed value toward the
// overlay's value by the overlay's weight, and only ever further (a moan never closes a mouth that is keyed
// wider). With weight 0 the keyed face shows unchanged, so wide-open eyes (eyes below 0) stay wide open until a
// blink or moan really starts, instead of jumping to 0. A plain {channel: value} object counts as weight 1.
export function mergeFace(a, b) {
  if (!b) return a;
  const w = b.to ? THREE.MathUtils.clamp(b.weight ?? 1, 0, 1) : 1, to = b.to || b;
  const out = { ...(a || {}) };
  for (const [k, x] of Object.entries(to)) {
    const base = out[k] || 0;
    out[k] = Math.max(base, base + (x - base) * w);
  }
  return out;
}

// Natural blinking: about every 3.5 s, spread so it loops cleanly; each blink takes 7 frames.
export function blinkAt(sim, frame, length, fps = 30) {
  if (sim.body && sim.body.blink === false) return null;
  const count = Math.max(1, Math.round(length / fps / 3.5));
  let seed = 0;
  for (const c of String(sim.id)) seed = (seed * 31 + c.charCodeAt(0)) % 1000;
  for (let k = 0; k < count; k++) {
    const at = ((k + 0.35 + ((seed * (k + 1)) % 97) / 97 * 0.3) / count) * length;
    let t = frame - at;
    if (t < -length / 2) t += length;
    if (t > length / 2) t -= length;
    if (t >= 0 && t < 7) return overlay(Math.sin(Math.PI * t / 7), { eyes: 0.95 });
  }
  return null;
}

// ---------------------------------------------------------------- the jaw carries the mouth
// Opening the mouth is the lower jaw dropping: the lower lip and chin ride on the jaw, the upper lip stays with
// the skull. The mouth corners sit between the two, so they must come down with the jaw - otherwise the lower lip
// drops away from a frozen upper mouth like a puppet's. Measured in creator clips: the corners drop about 0.5 mm
// per degree the jaw opens and move back a little; past about 15 degrees both lips also push forward.
// Runs after everything that turns the jaw (keys, face sliders, openings). Face bones: x up, y forward, z left.
export function followJaw(v) {
  const jaw = v.byName.b__Jaw__;
  if (!jaw || !v.restByName) return;
  const d = _q2.copy(v.restByName.b__Jaw__.quat).invert().multiply(jaw.quaternion);
  const s = d.w < 0 ? -1 : 1;
  const dg = Math.max(0, THREE.MathUtils.radToDeg(-2 * Math.atan2(s * d.z, s * d.w)));   // opens about -Z
  if (dg < 0.5) return;
  const wide = Math.max(0, dg - 15);
  for (const side of ['L', 'R']) {
    move(v, `b__${side}_Mouth__`, -0.0005 * dg, -0.00012 * dg, 0);
    move(v, `b__${side}_UpLip__`, 0, 0.0001 * wide, 0);
  }
  move(v, 'b__UpLip__', -0.00008 * Math.max(0, dg - 25), 0.00018 * wide, 0);
  move(v, 'b__LoLip__', 0, 0.00025 * Math.max(0, dg - 20), 0);
}
