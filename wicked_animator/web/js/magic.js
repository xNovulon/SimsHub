// Magic Animation: pick a position and a place, press one button - both sims are posed on the real furniture,
// moving, with faces, physics, opening holes, claps, wet sounds and moans - playing with sound in seconds. Hands hold
// on to the partner by themselves (his hands on her hips in cowgirl...), heads and eyes look at the partner, legs
// tremble at a hard finish, and a Finish can end it (cum, drool, the game's finish voices).
import * as THREE from 'three';
import { h, icon, modal, toast, slider, confirmBox, emitWA } from './ui.js';
import { newProject, newSim, localStorageGet, localStorageSet } from './state.js';
import { newLayer, MOTIONS } from './motion.js';
import { FACE_PRESETS } from './face.js';
import { simBody } from './pipeline.js';
import { furnitureInfo, fitOnSurface, restOn, inFrontOf, bodyPoints, longAxis, surfaceAxis, lowestSkin, sitOn, gridOf, gridHeight, surfaceY } from './placing.js';
import { LIMBS, GRAB, PALM, PALM_GAP } from './bones.js';
import { spacePos, spaceQuat } from './posemath.js';
import { holdNamed, limbPoint } from './holds.js';
import { shapeQuats } from './hands.js';
import { spell, reducedMotion } from './fx.js';

// layers: [type, params] per part; faces: preset id per part; voice: random voice set per part
export const RECIPES = [
  { id: 'cowgirl', label: 'Cowgirl', kind: 'VAGINAL', tags: ['COWGIRL', 'VAGINAL', 'PASSIONATE'], blurb: 'She rides him',
    layers: { FEMALE: [['ride', {}]], MALE: [['thrust', { distance: 3 }]] }, faces: { FEMALE: 'moan', MALE: 'pleasure' }, voice: { FEMALE: 'moan', MALE: 'woohoo' } },
  { id: 'missionary', label: 'Missionary', kind: 'VAGINAL', tags: ['MISSIONARY', 'VAGINAL', 'PASSIONATE'], blurb: 'Face to face, him on top',
    layers: { MALE: [['thrust', {}]], FEMALE: [['breathe', {}]] }, faces: { FEMALE: 'ecstasy', MALE: 'intense' }, voice: { FEMALE: 'moan', MALE: 'woohoo' } },
  { id: 'doggy', label: 'Doggy', kind: 'VAGINAL', tags: ['DOGGY', 'VAGINAL', 'ROUGH'], blurb: 'From behind, hard',
    layers: { MALE: [['thrust', { sharp: 0.85 }]], FEMALE: [['bounce', { distance: 1.2, tilt: 4 }]] }, faces: { FEMALE: 'moan', MALE: 'intense' }, voice: { FEMALE: 'moan', MALE: 'woohoo' } },
  { id: 'standing', label: 'Standing', kind: 'VAGINAL', tags: ['STANDING', 'VAGINAL'], blurb: 'Up against each other',
    layers: { MALE: [['thrust', {}]], FEMALE: [['breathe', {}]] }, faces: { FEMALE: 'pleasure', MALE: 'pleasure' }, voice: { FEMALE: 'moan_soft' } },
  { id: 'spooning', label: 'Spooning', kind: 'VAGINAL', tags: ['SPOONING', 'VAGINAL', 'SLOW'], blurb: 'Slow, lying on their sides',
    layers: { MALE: [['thrust', { distance: 3, sharp: 0.3 }]], FEMALE: [['breathe', {}]] }, faces: { FEMALE: 'bite', MALE: 'relaxed' }, voice: { FEMALE: 'moan_soft' }, calm: true },
  { id: 'pronebone', label: 'Prone bone', kind: 'VAGINAL', tags: ['PRONEBONE', 'VAGINAL', 'ROUGH'], blurb: 'She lies flat, him on top',
    layers: { MALE: [['thrust', { sharp: 0.8 }]] }, faces: { FEMALE: 'ahegao', MALE: 'intense' }, voice: { FEMALE: 'moan' } },
  { id: 'sitting', label: 'Lap ride', kind: 'VAGINAL', tags: ['SITTING', 'VAGINAL'], blurb: 'She sits on his lap',
    layers: { FEMALE: [['ride', { distance: 4 }]] }, faces: { FEMALE: 'moan', MALE: 'pleasure' }, voice: { FEMALE: 'moan_soft' } },
  { id: 'anal', label: 'Anal', kind: 'ANAL', tags: ['ANAL', 'DOGGY'], blurb: 'From behind, anal',
    layers: { MALE: [['thrust', { distance: 3.5 }]] }, faces: { FEMALE: 'intense', MALE: 'intense' }, voice: { FEMALE: 'moan', MALE: 'woohoo' } },
  { id: 'bj', label: 'Blowjob', kind: 'ORALJOB', tags: ['BLOWJOB', 'KNEELING'], blurb: 'She kneels, head bobbing',
    layers: { FEMALE: [['headbob', {}]], MALE: [['breathe', {}]] }, faces: { FEMALE: 'kiss', MALE: 'pleasure' }, voice: { MALE: 'breath' }, noOpenFace: true },
  { id: 'handjob', label: 'Handjob', kind: 'HANDJOB', tags: ['FOREPLAY'], blurb: 'Her hand strokes him',
    layers: { FEMALE: [['stroke', { limb: 'R hand' }]], MALE: [['breathe', {}]] }, faces: { FEMALE: 'seductive', MALE: 'pleasure' }, voice: { MALE: 'breath' }, calm: true },
  { id: 'cunni', label: 'Cunnilingus', kind: 'ORALJOB', tags: ['CUNNILINGUS', 'LICKING'], blurb: 'He goes down on her',
    layers: { MALE: [['headbob', { angle: 8 }]], FEMALE: [['grind', { distance: 1.5, tilt: 8 }]] }, faces: { FEMALE: 'ecstasy', MALE: 'tongue' }, voice: { FEMALE: 'moan_soft' } },
  { id: 'titjob', label: 'Titjob', kind: 'HANDJOB', tags: ['TITJOB'], blurb: 'Between her breasts',
    layers: { FEMALE: [['bounce', { distance: 4 }]], MALE: [['breathe', {}]] }, faces: { FEMALE: 'seductive', MALE: 'pleasure' }, voice: { MALE: 'breath' } },
  { id: 'kiss', label: 'Making out', kind: 'TEASING', tags: ['KISSING', 'FOREPLAY'], blurb: 'Close, kissing, hands roaming',
    layers: { FEMALE: [['sway', {}], ['breathe', {}]], MALE: [['sway', {}], ['breathe', {}]] }, faces: { FEMALE: 'kiss', MALE: 'kiss' }, voice: { FEMALE: 'moan_soft' }, calm: true },
  { id: 'carry', label: 'Carry', kind: 'VAGINAL', tags: ['CARRY', 'STANDING', 'FLEXIBLE'], blurb: 'He holds her up',
    layers: { MALE: [['thrust', { axis: 'up', distance: 4 }]] }, faces: { FEMALE: 'moan', MALE: 'intense' }, voice: { FEMALE: 'moan' } },
];

export const PLACES = [
  { id: 'floor', label: 'Floor' }, { id: 'double_bed', label: 'Double bed' }, { id: 'single_bed', label: 'Single bed' },
  { id: 'sofa', label: 'Sofa' }, { id: 'loveseat', label: 'Loveseat' }, { id: 'chair_living', label: 'Armchair' },
  { id: 'counter', label: 'Counter' }, { id: 'table_dining', label: 'Table' },
];

// Intensity 0 (slow & gentle) .. 1 (hard & fast): strokes per loop, distance and hardness.
function tune(layer, intensity, calm) {
  const p = layer.params;
  const k = calm ? intensity * 0.6 : intensity;
  if (p.strokes !== undefined && layer.type !== 'breathe' && layer.type !== 'sway') p.strokes = Math.max(1, Math.round((p.strokes || 3) * (0.6 + k * 1.1)));
  if (p.sharp !== undefined && layer.type !== 'breathe') p.sharp = Math.min(1, (p.sharp || 0) * 0.5 + k * 0.6);
  if (p.distance !== undefined && ['thrust', 'ride', 'bounce'].includes(layer.type)) p.distance = Math.round(p.distance * (0.75 + k * 0.5) * 2) / 2;
}

// Put the posed couple where it belongs. Every key moves with it (placing.js goes through app.transformSim), so the
// whole animation lands there, not only the frame on screen.
//   floor: resting on the floor;  beds: lying or kneeling along the bed, heads at the headboard, on the mattress;
//   seats, tables, counters: lying bodies on the surface only when it is as long as they are (a sofa, a table - not a
//   loveseat, where a foot would go into the armrest), else on the floor in front of it; a lap ride sits him on the
//   seat with her on his lap;  a couple where someone stands (standing, carry, blowjob): on the floor in front of it
//   (a bed's foot end).
// -> 'floor' | 'on' | 'front' | 'lap'
async function placeCouple(app, sims, furn, recipe) {
  const info = furn.kind === 'floor' ? null
    : (await furnitureInfo(app, furn.id)) || (furn.size ? { surface_height: furn.size[1] } : null);
  if (!info) { restOn(app, sims, 0, { frame: 0 }); return 'floor'; }
  const pts = bodyPoints(app, sims, 0), body = longAxis(pts.all, pts.heads);
  // someone stands (standing, carry, him in a blowjob): they stay on the floor, at the foot of the bed or in front
  // of the seat - nobody stands on a mattress or a cushion
  const standing = sims.some(s => {
    const v = app.simViews.get(s.id), hd = v && v.bone('b__Head__');
    if (!hd) return false;
    const low = lowestSkin(app, [s], 0);
    return spacePos(v, hd).y - low > 1.25;
  });
  if (standing && recipe.id !== 'sitting') { inFrontOf(app, sims, info, { frame: 0 }); return 'front'; }
  if (furn.kind === 'bed') { await fitOnSurface(app, sims, info, { frame: 0 }); return 'on'; }
  if (recipe.id === 'sitting' && await lapRide(app, sims, info)) return 'lap';
  const surf = surfaceAxis(info);
  const lying = body.length > 1.1;
  if (lying && surf && surf.length >= body.length - 0.1) {
    await fitOnSurface(app, sims, info, { frame: 0 });
    return 'on';
  }
  inFrontOf(app, sims, info, { frame: 0 });
  return 'front';
}

// "Lap ride" on something with seats (a sofa, a loveseat, an armchair): he sits on the middle of it (placing.sitOn:
// the pelvis on the seat, the feet on its foot spots), she sits on his lap facing the same way, her knees outside his
// and her feet on the floor, her hands on his knees (holds) and his on her hips. Built from the standing couple (the
// 'sitting' ready pose lies down, so it can't sit on a chair). -> false when there is no seat (then the couple is
// placed like any other).
const LAP = { seat: 0.10, up: 0.17, fwd: 0.12, feetFwd: 0.1, feetOut: 0.2 };
async function lapRide(app, sims, info) {
  const seats = ((info && info.slots) || []).filter(x => x.kind === 'seat' && x.pos && x.dir);
  const standing = (app.posePresets || []).find(x => x.id === 'standing' && !x.mine);
  const him = sims.find(x => x.frame === 'ym' || x.frame === 'yf_futa'), her = sims.find(x => x !== him);
  if (!seats.length || !standing || !him || !her) return false;
  // the middle of the seats (between the two middle ones when there are two)
  const mx = seats.reduce((a, x) => a + x.pos[0], 0) / seats.length;
  const near = [...seats].sort((a, b) => Math.abs(a.pos[0] - mx) - Math.abs(b.pos[0] - mx));
  let seat = near[0];
  if (near.length > 1 && Math.abs(Math.abs(near[0].pos[0] - mx) - Math.abs(near[1].pos[0] - mx)) < 0.02) {
    const a = near[0], b = near[1], mid = (u, v) => u.map((x, i) => (x + v[i]) / 2);
    const shift = x => [x[0] - (a.pos[0] - mx), x[1], x[2]];
    seat = { ...a, pos: mid(a.pos, b.pos), feet: a.feet ? { L: shift(a.feet.L), R: shift(a.feet.R) } : null };
  }
  const p = app.store.project, furniture = p.furniture, locations = [...(p.locations || [])];
  app.applyPosePreset(standing, { quiet: true, checkpoint: false });
  await Promise.resolve(app._lifting);
  if (p.furniture !== furniture) { p.furniture = furniture; p.locations = locations; app.buildFurniture(); }
  const UPV = new THREE.Vector3(0, 1, 0);
  const dir = new THREE.Vector3(seat.dir[0], 0, seat.dir[2]).normalize(), left = UPV.clone().cross(dir);
  const floorFeet = side => new THREE.Vector3(...seat.pos).addScaledVector(dir, 0.44).addScaledVector(left, side === 'L' ? 0.1 : -0.1).setY(0.111);
  const feetOf = x => ({ L: x.feet ? new THREE.Vector3(...x.feet.L) : floorFeet('L'), R: x.feet ? new THREE.Vector3(...x.feet.R) : floorFeet('R') });
  const hisFeet = feetOf(seat);
  const g = gridOf(info), cushion = (g && gridHeight(g, seat.pos[0] + dir.x * 0.1, seat.pos[2] + dir.z * 0.1)) ?? surfaceY(info, seat.pos[1] - 0.05);
  const hips = (sim) => { const v = app.simViews.get(sim.id); app.pipeline.base({ sim, v }, 0);
    return spacePos(v, v.bone('b__L_Thigh__')).add(spacePos(v, v.bone('b__R_Thigh__'))).multiplyScalar(0.5); };
  // sit where the hip joints (the tops of the thighs) come out `want` (sitOn seats the pelvis joint; a pose's hip
  // tilt decides where the thighs are, so it is measured and corrected once)
  const seatAt = (sim, slot, want) => {
    sitOn(app, sim, slot, { frame: 0 });
    const d = want.clone().sub(hips(sim));
    if (d.length() > 0.004) sitOn(app, sim, { ...slot, pos: new THREE.Vector3(...slot.pos).add(d).toArray() }, { frame: 0 });
  };
  // him: on the seat, his hip joints 10 cm over the cushion (only the height is corrected)
  const hisSlot = { ...seat, feet: { L: hisFeet.L.toArray(), R: hisFeet.R.toArray() } };
  sitOn(app, him, hisSlot, { frame: 0 });
  seatAt(him, hisSlot, hips(him).setY(cushion + LAP.seat));
  // her hips: on his thighs, a little in front of his; knees outside his, feet on the floor
  const lapAt = hips(him).addScaledVector(dir, LAP.fwd).addScaledVector(UPV, LAP.up);
  const lap = { kind: 'seat', dir: [dir.x, 0, dir.z], pos: lapAt.clone().addScaledVector(dir, -0.03).addScaledVector(UPV, -0.11).toArray(),
    feet: { L: hisFeet.L.clone().addScaledVector(dir, LAP.feetFwd).addScaledVector(left, LAP.feetOut).toArray(),
      R: hisFeet.R.clone().addScaledVector(dir, LAP.feetFwd).addScaledVector(left, -LAP.feetOut).toArray() } };
  seatAt(her, lap, lapAt);
  // her hands rest on her own knees (pinned, palms down), so her arms come forward instead of reaching back through
  // his head
  const hv = app.simViews.get(her.id);
  for (const limb of ['L hand', 'R hand']) {
    const side = limb[0];
    app.pipeline.base({ sim: her, v: hv }, 0);
    const knee = spacePos(hv, hv.bone(`b__${side}_Calf__`)), hip = spacePos(hv, hv.bone(`b__${side}_Thigh__`));
    restHandOn(app, her, limb, knee.lerp(hip, 0.25).addScaledVector(UPV, 0.075));
  }
  return true;
}

// A hand resting on a point (sim space): palm down, its centre 1.2 cm above the point, the arm pinned there (the key's
// hand turned palm-down, the fingers eased flat).
function restHandOn(app, sim, limb, point) {
  const v = app.simViews.get(sim.id), key = sim.keys.find(k => k.frame === 0 && !k.faceOnly && k.pose);
  if (!v || !key || !LIMBS[limb]) return false;
  const [ua, fa, hd] = LIMBS[limb].map(n => v.bone(n));
  v.resetPose(); v.setPose(key.pose);
  const handW = spaceQuat(v, hd), palmN = new THREE.Vector3(0, 1, 0).applyQuaternion(handW);
  const want = new THREE.Quaternion().setFromUnitVectors(palmN, new THREE.Vector3(0, -1, 0)).multiply(handW);
  key.pose.rot[hd.name] = spaceQuat(v, fa).invert().multiply(want).normalize().toArray();
  const flat = shapeQuats(v, limb[0], 'flat');
  for (const [n, q] of Object.entries(flat)) { const b = v.bone(n); if (b) key.pose.rot[n] = b.quaternion.clone().slerp(q, 0.6).normalize().toArray(); }
  const palm = v.restByName[PALM[limb]];
  const wrist = point.clone().add(new THREE.Vector3(0, PALM_GAP, 0)).sub(palm ? palm.pos.clone().applyQuaternion(want) : new THREE.Vector3());
  sim.pins = sim.pins || {};
  sim.pins[limb] = wrist.toArray();
  void ua;
  app.pipeline.base({ sim, v }, 0);
  return true;
}

// Hold `key` of the partner with one hand, and keep the hold only if the arm reaches it on every frame of the loop
// (1 cm). -> true when it holds.
function tryHoldAll(app, holder, limb, partner, key, slot = null) {
  const keysBefore = JSON.stringify(holder.keys);
  if (!holdNamed(app, holder.id, limb, partner.id, key, { slot, checkpoint: false, quiet: true })) return false;
  let short = 0;
  for (let f = 0; f < app.store.project.length; f += 3) {
    app.pipeline.apply(f, { physics: false, overrides: false });
    short = Math.max(short, (app.pipeline.reach.get(holder.id) || {})[limb] || 0);
  }
  if (short > 0.01) { delete holder.pins[limb]; holder.keys = JSON.parse(keysBefore); return false; }
  return true;
}

// Hands that rest on the bed, a seat or the floor stay there while the body moves (like the feet), so a ride or a
// thrust never pushes the fingers into the mattress or the pillows. A hand that holds the partner is left alone.
function pinRestingHands(app, sims, info) {
  const g = info ? gridOf(info) : null, pinned = [];
  for (const s of sims) {
    const v = app.simViews.get(s.id);
    if (!v || !(s.layers || []).length) continue;
    app.pipeline.base({ sim: s, v }, 0);
    s.pins = s.pins || {};
    for (const limb of ['L hand', 'R hand']) {
      const side = limb[0], hand = v.bone(LIMBS[limb][2]);
      if (!hand || s.pins[limb]) continue;
      let resting = false;
      for (const n of [LIMBS[limb][2], ...['Index', 'Mid', 'Ring', 'Pinky'].flatMap(f => [`b__${side}_${f}1__`, `b__${side}_${f}2__`])]) {
        const b = v.bone(n);
        if (!b) continue;
        const q = spacePos(v, b), h = g ? gridHeight(g, q.x, q.z) : null;
        if (q.y - (h !== null ? h : 0) < 0.05) { resting = true; break; }
      }
      if (resting) { s.pins[limb] = spacePos(v, hand).toArray(); pinned.push({ sim: s, limb }); }
    }
  }
  settleHands(app, info, pinned);
  return pinned;
}

// A pinned hand keeps its place, but the body's motion still tips it a little (it keeps the forearm's turn): over the
// loop the fingers may dip into a pillow. Such a pin is raised until no hand or finger bone goes more than 2.5 cm
// under the furniture's top on any frame (at most 3 times).
function settleHands(app, info, pinned) {
  const g = info ? gridOf(info) : null;
  if (!g || !pinned.length) return;
  const bonesOf = limb => { const side = limb[0]; return [LIMBS[limb][2], ...['Thumb', 'Index', 'Mid', 'Ring', 'Pinky'].flatMap(f => [0, 1, 2].map(k => `b__${side}_${f}${k}__`))]; };
  for (let pass = 0; pass < 3; pass++) {
    const worst = pinned.map(() => 0);
    for (let f = 0; f < app.store.project.length; f += 3) {
      app.pipeline.apply(f, { physics: false, overrides: false });
      pinned.forEach(({ sim, limb }, i) => {
        const v = app.simViews.get(sim.id);
        for (const n of bonesOf(limb)) {
          const b = v && v.bone(n);
          if (!b) continue;
          const q = spacePos(v, b), h = gridHeight(g, q.x, q.z);
          if (h !== null && q.y < h && q.y > h - 0.3) worst[i] = Math.max(worst[i], h - q.y);
        }
      });
    }
    let moved = false;
    pinned.forEach(({ sim, limb }, i) => {
      const pin = sim.pins[limb];
      if (Array.isArray(pin) && worst[i] > 0.025) { pin[1] += worst[i] - 0.02; moved = true; }
    });
    if (!moved) break;
  }
  app.pipeline.apply(0, { physics: false, overrides: false });
}

// Feet that rest on the bed or the floor stay there while the hips move (fixed pins: the knees bend by themselves),
// so a thrust or a ride never pushes a foot through the mattress.
const HIP_MOTIONS = new Set(['thrust', 'ride', 'grind', 'bounce', 'twerk', 'sway']);
function pinRestingFeet(app, sims) {
  for (const s of sims) {
    const v = app.simViews.get(s.id);
    if (!v || !(s.layers || []).some(l => HIP_MOTIONS.has(l.type))) continue;
    const low = lowestSkin(app, [s], 0);
    app.pipeline.base({ sim: s, v }, 0);
    s.pins = s.pins || {};
    for (const limb of ['L foot', 'R foot']) {
      const b = LIMBS[limb] && v.bone(LIMBS[limb][2]);
      if (!b || s.pins[limb]) continue;
      const at = spacePos(v, b);
      if (at.y - low < 0.16) s.pins[limb] = at.toArray();
    }
  }
}

// ---------------------------------------------------------------- hands hold on (spec_bodies 4.7)
// [who holds, the part of the partner, how many hands]
const HOLDS = { cowgirl: ['MALE', 'hip', 2], doggy: ['MALE', 'hip', 2], anal: ['MALE', 'hip', 2], pronebone: ['MALE', 'hip', 2], sitting: ['MALE', 'hip', 2],
  missionary: ['FEMALE', 'back', 2], spooning: ['MALE', 'hip', 1], carry: ['MALE', 'thigh', 2], kiss: ['FEMALE', 'shoulder blade', 2] };

// Each of the holder's hands takes the nearest free grab point of that part (so the two hands go to different
// points). A hand is left alone when the point is further than 0.97 x the arm's length (shoulder to palm) from its
// shoulder, or more than 35 cm from where the hand is now (the pose has it doing something else), or when - tried
// over the loop - the arm can't reach it on some frame (more than 1 cm short). -> how many hands hold.
// (The palm counts in the arm's length, and the real reach is tried: with 0.92 x shoulder-to-wrist alone, doggy's
// hands, 11 cm from her hips, were "out of reach".)
function defaultHolds(app, sims, recipe, part) {
  const rule = HOLDS[recipe.id];
  if (!rule) return 0;
  const [who, key, most] = rule;
  const holder = sims.find(s => part(s) === who), partner = sims.find(s => s !== holder);
  const hv = holder && app.simViews.get(holder.id), pv = partner && app.simViews.get(partner.id);
  if (!hv || !pv) return 0;
  app.pipeline.apply(0, { physics: false, overrides: false });
  hv.group.updateMatrixWorld(true); pv.group.updateMatrixWorld(true);
  const slots = (GRAB[key] || []).filter(n => pv.bone(n));
  const pairs = [];
  for (const limb of ['L hand', 'R hand']) {
    const [ua, fa, hd] = LIMBS[limb];
    if (!hv.bone(ua) || !hv.bone(fa) || !hv.bone(hd)) continue;
    const palmBone = PALM[limb] && hv.restByName[PALM[limb]];
    const arm = hv.restByName[fa].pos.length() + hv.restByName[hd].pos.length() + (palmBone ? palmBone.pos.length() : 0);
    const shoulder = hv.worldPos(ua), palm = limbPoint(hv, limb);
    for (const slot of slots) {
      const at = pv.worldPos(slot);
      if (at.distanceTo(shoulder) > 0.97 * arm || at.distanceTo(palm) > 0.35) continue;
      pairs.push({ limb, slot, d: at.distanceTo(palm) });
    }
  }
  pairs.sort((a, b) => a.d - b.d);
  const usedLimb = new Set(), usedSlot = new Set();
  let n = 0;
  for (const x of pairs) {
    if (n >= most || usedLimb.has(x.limb) || usedSlot.has(x.slot)) continue;
    // (the arm must stay on it the whole loop - the partner moves)
    if (!tryHoldAll(app, holder, x.limb, partner, key, x.slot)) continue;
    usedLimb.add(x.limb); usedSlot.add(x.slot); n++;
  }
  app.pipeline.apply(0, { physics: false, overrides: false });
  return n;
}

// ---------------------------------------------------------------- look at the partner, tremble (spec_bodies 6.4)
// Only when the motions exist (they come with the scene tools).
const LOOK_BOTH = new Set(['missionary', 'cowgirl', 'kiss', 'standing', 'sitting', 'carry']);
const RECEIVER_MALE = new Set(['bj', 'handjob', 'titjob']);
function lookAndTremble(sims, recipe, part, intensity, climax, where = 'on') {
  const add = (s, type, params, weight = 1) => {
    if (!MOTIONS[type]) return null;
    const l = newLayer(type);
    Object.assign(l.params, params);
    l.weight = weight;
    s.layers.push(l);
    return l;
  };
  for (const s of sims) {
    // on his lap she faces away from him: only he looks (at her)
    if (where === 'lap' && recipe.id === 'sitting' && part(s) === 'FEMALE') continue;
    if (LOOK_BOTH.has(recipe.id)) add(s, 'look', { target: 'face', who: 'auto' }, 0.6);
    else if (recipe.id === 'bj' && part(s) === 'FEMALE') add(s, 'look', { target: 'face', who: 'auto' }, 0.5);
  }
  if (intensity > 0.8 || climax) {
    const want = RECEIVER_MALE.has(recipe.id) ? 'MALE' : 'FEMALE';
    const r = sims.find(s => part(s) === want);
    if (r) add(r, 'tremble', { amount: 2, parts: 'legs', start: 0.6, end: 1 });
  }
}

// The middle of the sims and how big they are (for the camera).
function simsBox(app) {
  const box = new THREE.Box3();
  for (const [, v] of app.simViews) {
    if (!v.group.visible) continue;
    v.group.updateMatrixWorld(true);
    for (const b of ['b__Head__', 'b__L_Hand__', 'b__R_Hand__', 'b__L_Foot__', 'b__R_Foot__', 'b__Pelvis__']) if (v.bone(b)) box.expandByPoint(v.worldPos(b));
  }
  if (box.isEmpty()) return null;
  const c = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
  return { center: c, radius: Math.max(0.5, size.length() / 2) * 1.2 };
}

export async function makeMagic(app, { recipe, place, intensity = 0.55, seconds = 3, bodies = ['yf', 'ym'], name, author, finish = 'none' }) {
  const r = RECIPES.find(x => x.id === recipe) || RECIPES[0];
  const presets = app.posePresets || [];
  const pr = presets.find(x => x.id === r.id && !x.mine);
  if (!pr) { toast('That position is not available (no animation of it in your library).', 'err'); return false; }
  const p = newProject();
  p.name = name || `${r.label} ${1 + Math.floor(Math.random() * 90)}`;
  p.author = author || localStorageGet('author', '') || '';
  p.category = r.kind;
  p.tags = [...r.tags];
  p.length = Math.round(seconds * 30);
  p.loops = r.kind === 'CLIMAX' ? 1 : 10;
  // a finish makes it a one-time Climax of this act (spec_game 3)
  const climax = !!finish && finish !== 'none';
  if (climax) { p.category = 'CLIMAX'; p.act = r.kind; p.loops = 1; }
  const furn = app.furniture.find(f => f.id === place) || app.furniture[0];
  p.furniture = furn.id;
  p.locations = [...furn.locations];
  for (const b of bodies) p.sims.push(newSim(p, b));
  app.store.load(p);
  app.store.selected.sim = p.sims[0].id;
  app.pipeline.overrides.clear();
  app.syncViews();
  app.store.frame = 0;
  // 1. the pose (a ready pose lifts the couple onto furniture by itself, a moment later: that must land before
  // Magic's own placement, not after it)
  app.applyPosePreset(pr);
  await Promise.resolve(app._lifting);
  const sims = app.store.project.sims;
  // the ready pose sets the place to its own (floor) - put the chosen furniture back
  app.store.project.furniture = furn.id;
  app.store.project.locations = [...furn.locations];
  app.buildFurniture();
  // 2. on the furniture: the real top surface of the game object (mattress, seat), every key together
  const where = await placeCouple(app, sims, furn, r);
  // 3. motion, 4. faces, 5. automatic body
  const part = s => (s.frame === 'ym' || s.frame === 'yf_futa' ? 'MALE' : 'FEMALE');
  for (const s of sims) {
    const b = simBody(s);
    b.erect = true; b.open.on = true; b.physics.on = true;
    if (r.noOpenFace && part(s) === 'FEMALE') b.open.mouth = true;
    s.layers = (r.layers[part(s)] || []).map(([type, params]) => {
      const l = newLayer(type);
      Object.assign(l.params, params);
      tune(l, intensity, r.calm);
      return l;
    });
  }
  // partners share one rhythm: same strokes, meeting on every stroke
  const lead = sims.flatMap(s => s.layers).find(l => ['thrust', 'ride', 'headbob', 'stroke'].includes(l.type));
  if (lead) for (const s of sims) for (const l of s.layers) if (l !== lead && l.type !== 'breathe') { l.params.strokes = lead.params.strokes; l.phase = lead.phase || 0; }
  lookAndTremble(sims, r, part, intensity, climax, where);
  pinRestingFeet(app, sims);
  // hands hold on to the partner (they follow her hips through every stroke); the others resting on the bed or the
  // floor stay there
  let held = 0;
  try { held = defaultHolds(app, sims, r, part); } catch (err) { console.error('Magic holds:', err); }
  try { pinRestingHands(app, sims, furn.kind === 'floor' ? null : await furnitureInfo(app, furn.id)); } catch (err) { console.error('Magic hands:', err); }
  for (const s of sims) {
    const face = FACE_PRESETS[r.faces[part(s)]];
    if (face) { const key = s.keys.find(k => k.frame === 0); if (key) key.face = { ...face.face }; }
  }
  app.store.setDirty(true);
  app.refreshAll();
  app.pipeline.simulateIfNeeded(true);
  // 6. sounds: claps and wet strokes from the contacts, moans on top
  app.autoSounds();
  // each sim only gets its own body's adult voice; a kind with no lines falls back quietly to a broader one
  for (const s of sims) { const set = r.voice[part(s)]; if (set) app.randomVoices(s.id, set, intensity > 0.6 ? 2 : 3.5, { quiet: true }); }
  // the finish: cum, drool and the game's finish voices at 70% of the loop (when the moments are there)
  if (climax) {
    try { const m = await import('./moments.js'); if (typeof m.finishPreset === 'function') m.finishPreset(app, finish, Math.round(0.7 * p.length), { checkpoint: false, quiet: true }); }
    catch (err) { console.warn('Magic finish:', err); }
  }
  app.showStep('motion');
  app.timeline.fit();
  app.audio.ensure();
  app.setPlaying(true);
  // the new scene arrives with a camera swoop and a ring pulse on the floor; the Showcase orbit starts after it
  // (both steer the camera)
  const box = simsBox(app);
  if (box && app.vp.swoop && !reducedMotion()) {
    app.vp.swoop(box.center, box.radius);
    app.vp.pulseOrigin?.();
    clearTimeout(app._magicShow);
    app._magicShow = setTimeout(() => { if (app.store.project.uid === p.uid && !app.vp.controls.busy) app.showcase(true); }, 1150);
  } else {
    if (box) app.vp.frame(box.center, box.radius, app.vp.viewDir());
    app.showcase(true);
  }
  const at = furn.kind === 'floor' ? 'on the floor' : where === 'front' ? `at the ${furn.label.toLowerCase()}` : where === 'lap' ? `on the ${furn.label.toLowerCase()}, she sits on his lap` : `on the ${furn.label.toLowerCase()}`;
  toast(`${r.label} ${at} - moving, with physics, faces and sound.${held ? ' Hands hold on to the partner by themselves.' : ''} Tune anything, then Send to game.`, 'ok');
  app.lastMagic = { recipe: r.id, place: furn.id, where, holds: held, finish: climax ? finish : 'none' };
  emitWA(app, 'magic', { recipe: r.id, place: furn.id, where, holds: held });
  return true;
}

export function openMagicDialog(app) {
  let recipe = localStorageGet('magicRecipe', 'cowgirl'), place = localStorageGet('magicPlace', 'floor');
  let intensity = localStorageGet('magicIntensity', 0.55), seconds = 3, finish = 'none';
  // "Finish": only offered when the moments (cum, drool, finish voices) are there
  // (it sits beside the two sliders, so the dialog does not grow on a laptop screen)
  const finishBox = h('label', { class: 'field hidden', style: { margin: 0, minWidth: 0 } }, h('span', {}, 'Finish'));
  const tuneRow = h('div', { class: 'grid-2', style: { marginTop: '10px', alignItems: 'end' } });
  import('./moments.js').then(m => {
    if (typeof m.finishPreset !== 'function') return;
    const parts = Array.isArray(m.FINISH_PARTS) && m.FINISH_PARTS.length ? m.FINISH_PARTS
      : [['inside', 'Inside'], ['face', 'Face'], ['chest', 'Chest'], ['back', 'Back'], ['butt', 'Butt'], ['feet', 'Feet']];
    const sel = h('select', { title: 'End with cum - it becomes a one-time Climax animation' },
      h('option', { value: 'none' }, 'No finish'), ...parts.map(([id, text]) => h('option', { value: id }, text)));
    sel.onchange = () => { finish = sel.value; };
    finishBox.append(sel);
    finishBox.classList.remove('hidden');
    tuneRow.style.gridTemplateColumns = 'minmax(0, 1fr) minmax(0, 1fr) minmax(120px, .6fr)';
    // Enter still makes it: the dialog's first-field focus must not land on this select
    setTimeout(() => { if (document.activeElement === sel && dlg && dlg.footer) dlg.footer.querySelector('.btn.primary')?.focus({ preventScroll: true }); }, 80);
  }).catch(() => {});
  const grid = h('div', { class: 'tiles', style: { gridTemplateColumns: 'repeat(4, 1fr)', maxHeight: '44vh', overflow: 'auto' } });
  const places = h('div', { class: 'chips' });
  const draw = () => {
    grid.innerHTML = '';
    for (const r of RECIPES) {
      const pr = (app.posePresets || []).find(x => x.id === r.id && !x.mine);
      if (!pr) continue;
      const img = app.poseThumb(pr);
      grid.append(h('button', { class: 'tile' + (recipe === r.id ? ' on' : ''), onclick: () => { recipe = r.id; draw(); } },
        h('div', { class: 'thumb' }, img ? h('img', { src: img, alt: '' }) : icon('pose')), h('b', {}, r.label), h('small', {}, r.blurb)));
    }
    places.innerHTML = '';
    for (const pl of PLACES) if (app.furniture.some(f => f.id === pl.id)) places.append(h('button', { class: 'chipbtn place' + (place === pl.id ? ' on' : ''), onclick: () => { place = pl.id; draw(); } }, pl.label));
  };
  draw();
  const go = async () => {
    localStorageSet('magicRecipe', recipe); localStorageSet('magicPlace', place); localStorageSet('magicIntensity', intensity);
    // Magic makes a new animation: work that isn't saved is never replaced without asking
    if (app.store.dirty && !(await confirmBox('Make a new animation?', `Unsaved changes to "${app.store.project.name}" will be lost. Save first (Ctrl+S) to keep them.`, 'Make it', true))) return false;
    // a soft glow grows from the button over the window while the scene is made
    const btn = dlg && dlg.footer && dlg.footer.lastChild;
    if (btn && btn.isConnected) { const rc = btn.getBoundingClientRect(); spell(rc.left + rc.width / 2, rc.top + rc.height / 2); }
    return makeMagic(app, { recipe, place, intensity, seconds, finish });
  };
  const dlg = modal({
    title: 'Magic Animation', wide: true,
    text: 'Pick a position and a place. One click makes a complete animation - posed on the real furniture, moving, with physics, faces and sound.',
    body: h('div', {},
      grid,
      h('div', { class: 'section-title', style: { marginTop: '16px' } }, 'Where'), places,
      (tuneRow.append(
        slider({ label: 'Slow & gentle ↔ Hard & fast', min: 0, max: 1, step: 0.05, value: intensity, fmt: v => Math.round(v * 100) + '%', onInput: v => { intensity = v; } }),
        slider({ label: 'Loop length', min: 2, max: 8, step: 0.5, value: seconds, fmt: v => v + ' s', onInput: v => { seconds = v; } }),
        finishBox), tuneRow)),
    buttons: [
      { label: 'Surprise me', kind: 'ghost', onClick: () => {
        const avail = RECIPES.filter(r => (app.posePresets || []).some(x => x.id === r.id && !x.mine));
        if (!avail.length) { toast('The positions are still loading - try again in a moment.'); return false; }
        recipe = avail[Math.floor(Math.random() * avail.length)].id;
        const pls = PLACES.filter(pl => app.furniture.some(f => f.id === pl.id) && ['floor', 'double_bed', 'single_bed'].includes(pl.id));
        if (pls.length) place = pls[Math.floor(Math.random() * pls.length)].id;
        intensity = 0.3 + Math.random() * 0.6;
        return go();
      } },
      { label: 'Cancel', kind: 'ghost' },
      { label: 'Make it', kind: 'primary', onClick: go },
    ],
  });
}
