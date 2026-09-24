// Automatic sounds: one wet sound on the deepest moment of every stroke, a clap there too when the hips meet, found
// from how the sims move.
import * as THREE from 'three';
import { Sim } from './sim.js';

// Preferred sounds per kind, best first; only names the catalogue knows are used, in this order. Wet kinds hold wet
// strokes only (no impacts - those are claps - and no mouth sounds outside the mouth).
const SETS = {
  clap: ['Plaps_Normal', 'Slap_Sounds_01', 'Slap_Sounds_02', 'Slap_Sounds_03', 'PLAPS_2026_1', 'PLAPS_2026_2', 'plaps', 'bush_woohoo_getin_slap'],
  oral: ['Oj_Sounds_01', 'Oj_Sounds_02', 'Oj_Sounds_03', 'Oj_Sounds_04', 'Oj_Sounds_05', 'Oj_Sounds_06', 'Sx_Suck13F', 'Sx_Fastsuck9F', 'vo_romantic_kiss_succ_x'],
  vaginal: ['WET_PL_1', 'WET_PL_2', 'WET_PL_3', 'WET_PL_4', 'WET_PL_5', 'Sx_WetPump8F', 'E404P_wet_pussy'],
  anal: ['WET_PL_3', 'WET_PL_2', 'WET_PL_4', 'Sx_WetPump8F', 'WET_PL_1', 'WET_PL_5'],
  breasts: ['Sx_WetPump8F', 'sfx_slaps_wet_fast'],
  insert: ['E404P_wet_pussy', 'WET_PL_1', 'Sx_WetPump8F'],
  finger: ['Sx_WetPump8F', 'WET_PL_2', 'WET_PL_4', 'E404P_wet_pussy'],
  lick: ['Oj_Sounds_02', 'Oj_Sounds_05', 'vo_romantic_kiss_succ_x', 'Sx_Suck13F'],
};
const HOLE_KIND = { vagina: 'vaginal', anus: 'anal', mouth: 'oral' };
const HOLE_POINT = { vagina: 'genital', anus: 'anus', mouth: 'mouth' };

// Contact points, as offsets from a bone, measured once on a sim standing at rest (+Z is forward).
const POINTS = {
  genital: { bone: 'b__Pelvis__', from: ['b__L_Thigh__', 'b__R_Thigh__'], add: [0, -0.07, 0.085] },
  anus: { bone: 'b__Pelvis__', from: ['b__L_Thigh__', 'b__R_Thigh__'], add: [0, -0.07, -0.075] },
  butt: { bone: 'b__Pelvis__', from: ['b__L_Thigh__', 'b__R_Thigh__'], add: [0, -0.01, -0.13] },
  front: { bone: 'b__Pelvis__', from: ['b__L_Thigh__', 'b__R_Thigh__'], add: [0, 0.02, 0.11] },
  mouth: { bone: 'b__Head__', from: ['b__mouth_slot'], add: [0, 0, 0.01] },
  cleavage: { bone: 'b__Spine2__', from: ['b__CAS_L_Breast__', 'b__CAS_R_Breast__'], add: [0, -0.03, 0.06] },
};

// Stroke tuning: a stroke moves at least 6 mm and strokes are at least 0.2 s apart. A clap: on the deepest moment the
// hips are within 17 cm of each other (the points sit a few cm inside the skin), after the stroke or the hips closed in
// at 10 cm/s or more on the way there (slow, gentle strokes do not clap).
const STROKE_M = 0.006, STROKE_S = 0.2, CLAP_NEAR = 0.17, CLAP_SPEED = 0.10;

let _offsets = null;
function offsets(app) {
  if (_offsets) return _offsets;
  _offsets = {};
  for (const frame of ['yf', 'ym']) {
    if (!app.assets.bodies[frame]) continue;
    const s = new Sim(app.assets.rig, app.assets.bodies[frame]);
    s.group.updateMatrixWorld(true);
    const out = {};
    for (const [name, def] of Object.entries(POINTS)) {
      const p = new THREE.Vector3();
      def.from.forEach(n => p.add(s.worldPos(n)));
      p.multiplyScalar(1 / def.from.length).add(new THREE.Vector3(...def.add));
      const bone = s.bone(def.bone);
      out[name] = { bone: def.bone, local: bone.worldToLocal(p.clone()) };
    }
    _offsets[frame] = out;
    s.dispose();
  }
  return _offsets;
}

function pick(app, kind, n) {
  const known = new Set((app.sounds || []).map(s => s.name));
  const list = SETS[kind].filter(x => known.has(x));
  const names = list.length ? list : SETS[kind];
  return names[n % Math.min(names.length, kind === 'clap' ? 4 : 6)];
}

// The deepest moments of the strokes in a series (lower = deeper): minima of the lightly smoothed curve that stand out
// from the highs on both sides by `prom` (and by a third of the whole swing), at least `gap` frames apart. Jitter on
// the curve is not a stroke: one real stroke gets one moment.
export function strokes(d, prom, gap, loop) {
  const n = d.length;
  if (n < 5) return [];
  const wrap = (arr, i) => (loop ? arr[((i % n) + n) % n] : arr[Math.max(0, Math.min(n - 1, i))]);
  const s = d.map((_, i) => (wrap(d, i - 2) + 2 * wrap(d, i - 1) + 3 * d[i] + 2 * wrap(d, i + 1) + wrap(d, i + 2)) / 9);
  const at = i => wrap(s, i);
  const swing = Math.max(...s) - Math.min(...s);
  if (swing < prom) return [];
  const need = Math.max(prom, swing / 3);
  // how far the curve rises on one side before it goes deeper than frame i (at most half the loop away)
  const rise = (i, dir) => {
    let top = s[i];
    for (let j = 1; j < n / 2; j++) {
      const k = i + dir * j;
      if (!loop && (k < 0 || k >= n)) break;
      const w = at(k);
      if (w < s[i]) break;
      if (w > top) top = w;
    }
    return top - s[i];
  };
  const out = [];
  for (let i = 0; i < n; i++) {
    if (!loop && (i < 1 || i > n - 2)) continue;
    if (s[i] > at(i - 1) || s[i] >= at(i + 1)) continue;
    if (Math.min(rise(i, -1), rise(i, 1)) < need) continue;
    const last = out[out.length - 1];
    if (last !== undefined && i - last < gap) { if (s[i] < s[last]) out[out.length - 1] = i; continue; }
    out.push(i);
  }
  if (loop && out.length > 1 && out[0] + n - out[out.length - 1] < gap) out.pop();
  // the smoothing can move a sharp stroke's low point by a frame: back to the real curve's lowest frame near it
  return out.map(i => {
    let best = i;
    for (let j = -2; j <= 2; j++) {
      const k = loop ? ((i + j) % n + n) % n : Math.max(0, Math.min(n - 1, i + j));
      if (d[k] < d[best]) best = k;
    }
    return best;
  });
}

// The openings in the order the act uses them: a penis reads as inside two of them at once (they lie close together),
// and only the act's own one gets sounds.
function actHoles(p) {
  const act = p.category === 'CLIMAX' ? p.act : p.category;
  const tags = new Set(p.tags || []);
  if (act === 'ANAL' || tags.has('ANAL')) return ['anus', 'vagina', 'mouth'];
  if (act === 'ORALJOB' || tags.has('BLOWJOB') || tags.has('DEEP_THROAT')) return ['mouth', 'vagina', 'anus'];
  return ['vagina', 'anus', 'mouth'];
}

// Every frame through the full pipeline (keys + motions + pins + openings): the contact points and what is inside.
// Like the export: every sim with its motions (even the one being posed by hand) and only keyed poses.
export function measure(app) {
  const p = app.store.project, sims = p.sims;
  const off = offsets(app);
  const views = sims.map(s => app.simViews.get(s.id));
  const track = sims.map(() => Object.fromEntries(Object.keys(POINTS).map(k => [k, []])));
  const inside = sims.map(() => ({ vagina: [], anus: [], mouth: [] }));
  const saved = app.pipeline.editing;
  app.pipeline.editing = null;
  try {
    for (let f = 0; f < p.length; f++) {
      app.pipeline.apply(f, { physics: false, overrides: false });
      sims.forEach((s, k) => {
        const v = views[k];
        const o = off[s.frame === 'ym' ? 'ym' : 'yf'];
        for (const [name, def] of Object.entries(o)) {
          const b = v.bone(def.bone);
          b.updateWorldMatrix(true, false);
          track[k][name].push(b.localToWorld(def.local.clone()));
        }
        const m = app.pipeline.lastOpen.get(s.id) || {};
        for (const hole of Object.keys(inside[k])) inside[k][hole].push(m[hole] && m[hole].depth > 0.004 && m[hole].open > 0.5 ? { d: m[hole].depth, by: m[hole].by } : { d: 0, by: null });
      });
    }
  } finally { app.pipeline.editing = saved; }
  return { track, inside, views };
}

export function autoSounds(app) {
  const p = app.store.project;
  const sims = p.sims;
  if (!sims.length || !sims.some(s => s.keys.length)) return 0;
  const { track, inside, views } = measure(app);
  app.store.checkpoint();
  for (const s of sims) s.sounds = (s.sounds || []).filter(x => !x.auto);
  const counter = {};
  const add = (k, frame, set, kind) => {
    counter[set] = (counter[set] || 0) + 1;
    sims[k].sounds.push({ frame, name: pick(app, set, counter[set] - 1), kind, auto: true });
  };
  const n = p.length, at = (arr, i) => arr[((i % n) + n) % n];
  const gap = Math.max(4, Math.round(STROKE_S * (p.fps || 30)));
  const dist = (a, b) => a.map((x, i) => x.distanceTo(b[i]));
  const mean = d => d.reduce((a, b) => a + b, 0) / d.length;
  const givers = sims.map((s, k) => k).filter(k => sims[k].gender === 'MALE' || views[k]?.hasPenis);
  const takers = sims.map((s, k) => k).filter(k => !givers.includes(k));
  // a clap on a stroke's deepest moment: his front meets her butt or her front, and the stroke (`curve`) or the hips
  // closed in fast on the way there. Both count: in doggy she pushes back while he thrusts, so the stroke itself looks
  // slow while the hips meet hard.
  const clapAt = (g, t, i, curve) => {
    const G = track[g], T = track[t];
    const hips = G.front.map((x, f) => Math.min(x.distanceTo(T.butt[f]), x.distanceTo(T.front[f])));
    if (at(hips, i) > CLAP_NEAR) return;
    let speed = 0;
    for (let j = 1; j <= gap; j++) {
      speed = Math.max(speed, at(curve, i - j) - at(curve, i - j + 1), at(hips, i - j) - at(hips, i - j + 1));
    }
    if (speed * (p.fps || 30) >= CLAP_SPEED) add(t, i, 'clap', 'clap');
  };
  // 1. things going in: one wet sound on every stroke's deepest moment, in the opening that is really used
  let usedDepth = false;
  const prefer = actHoles(p);
  sims.forEach((s, k) => {
    const rows = Object.entries(inside[k]).filter(([, series]) => series.some(x => x.d > 0)).map(([hole, series]) => {
      const c = {};
      for (const x of series) if (x.by) c[x.by] = (c[x.by] || 0) + 1;
      return { hole, series, by: Object.entries(c).sort((a, b) => b[1] - a[1])[0]?.[0] || null };
    });
    if (!rows.length) return;
    usedDepth = true;
    // a penis is in as many openings as there are penises around, the act's own opening first
    const penises = Math.max(1, givers.filter(g => g !== k).length);
    const inUse = [...rows.filter(r => r.by === 'penis').sort((a, b) => prefer.indexOf(a.hole) - prefer.indexOf(b.hole)).slice(0, penises),
      ...rows.filter(r => r.by !== 'penis')];
    for (const { hole, series, by } of inUse) {
      if (hole === 'mouth' && by === 'tongue') continue;   // kissing: no stroke sounds
      const set = by === 'finger' ? 'finger' : by === 'tongue' ? 'lick' : HOLE_KIND[hole];
      // the stroke curve: for a penis, how far the nearest giver's hips are from this opening (smooth and exact in
      // time); for anything else, how deep it is
      let curve = null, giver = null;
      if (by === 'penis') {
        let best = Infinity;
        for (const g of givers) {
          if (g === k) continue;
          const d = dist(track[g].genital, track[k][HOLE_POINT[hole]]);
          if (mean(d) < best) { best = mean(d); curve = d; giver = g; }
        }
      }
      if (!curve) curve = series.map(x => -x.d);
      // a finger or tongue counts only where it stays in for a moment (a one-frame touch is not a stroke)
      const run = i => { let a = 0, b = 0; while (a < n && at(series, i - a - 1).d > 0) a++; while (b < n && at(series, i + b + 1).d > 0) b++; return a + b + 1; };
      const deep = strokes(curve, STROKE_M, gap, p.loop).filter(i => by === 'penis' || (series[i].d > 0 && run(i) >= 3));
      for (const i of deep) {
        add(k, i, set, 'wet');
        if (giver !== null && hole !== 'mouth') clapAt(giver, k, i, curve);
      }
      // going in after being out for half a second or more (slipping out for a moment at the top of a stroke is not
      // a new entry): one sound as it enters, unless a stroke sound is right there
      const out = Math.round(0.5 * (p.fps || 30));
      for (let i = p.loop ? 0 : 1; i < n; i++) {
        if (!(series[i].d > 0 && at(series, i - 1).d === 0) || run(i) < 3 || deep.some(j => Math.abs(j - i) <= 4)) continue;
        let gone = 0;
        while (gone < n && at(series, i - gone - 1).d === 0) gone++;
        if (gone >= out || (!p.loop && gone >= i)) add(k, i, by === 'penis' ? 'insert' : set, 'wet');
      }
    }
  });
  for (const g of givers) {
    for (const t of takers) {
      const G = track[g], T = track[t];
      if (!usedDepth && !views[g]?.hasPenis) {
        // no penetration can be measured (a giver without genitals): strokes of the giver's hips toward the nearest
        // opening. With genitals nothing measured means nothing goes in (kissing, a handjob): no wet sounds.
        const targets = { vaginal: dist(G.genital, T.genital), anal: dist(G.genital, T.anus), oral: dist(G.genital, T.mouth), breasts: dist(G.genital, T.cleavage) };
        const [kind, d] = Object.entries(targets).reduce((a, b) => (mean(b[1]) < mean(a[1]) ? b : a));
        if (mean(d) > 0.2) continue;
        for (const i of strokes(d, STROKE_M, gap, p.loop)) {
          add(t, i, kind, 'wet');
          if (kind === 'vaginal' || kind === 'anal') clapAt(g, t, i, d);
        }
      } else if (usedDepth || views[g]?.hasPenis) {
        // between her breasts
        const d = dist(G.genital, T.cleavage);
        for (const i of strokes(d, STROKE_M, gap, p.loop)) if (d[i] <= 0.1) add(t, i, 'breasts', 'wet');
      }
    }
  }
  app.applyPoses();
  return sims.reduce((a, s) => a + s.sounds.filter(x => x.auto).length, 0);
}
