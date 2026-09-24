// Automatic sounds: claps where bodies hit, wet sounds on every stroke, found from how the sims move.
import * as THREE from 'three';
import { Sim } from './sim.js';

// Preferred sounds per kind, best first; only names the catalogue knows are used, in this order.
const SETS = {
  clap: ['Plaps_Normal', 'Slap_Sounds_01', 'Slap_Sounds_02', 'Slap_Sounds_03', 'PLAPS_2026_1', 'PLAPS_2026_2', 'plaps', 'bush_woohoo_getin_slap'],
  oral: ['Oj_Sounds_01', 'Oj_Sounds_02', 'Oj_Sounds_03', 'Oj_Sounds_04', 'Oj_Sounds_05', 'Oj_Sounds_06', 'Sx_Suck13F', 'Sx_Fastsuck9F', 'vo_romantic_kiss_succ_x'],
  vaginal: ['WET_PL_1', 'WET_PL_2', 'WET_PL_3', 'WET_PL_4', 'WET_PL_5', 'Sx_WetPump8F', 'E404P_wet_pussy', 'khlas_ass_impact_wet', 'Oj_Sounds_07'],
  anal: ['khlas_ass_impact_wet', 'khlas_ass_impact_wet2', 'clap_impact_wet_1', 'WET_PL_3', 'Sx_WetPump8F', 'Oj_Sounds_08'],
  breasts: ['Sx_WetPump8F', 'sfx_slaps_wet_fast', 'Oj_Sounds_09', 'Plaps_Normal'],
  insert: ['E404P_wet_pussy', 'WET_PL_1', 'Sx_WetPump8F', 'khlas_ass_impact_wet', 'Oj_Sounds_07'],
  finger: ['Sx_WetPump8F', 'WET_PL_2', 'WET_PL_4', 'E404P_wet_pussy'],
  lick: ['Oj_Sounds_02', 'Oj_Sounds_05', 'vo_romantic_kiss_succ_x', 'Sx_Suck13F'],
};
const HOLE_KIND = { vagina: 'vaginal', anus: 'anal', mouth: 'oral' };

// Contact points, as offsets from a bone, measured once on a sim standing at rest (+Z is forward).
const POINTS = {
  genital: { bone: 'b__Pelvis__', from: ['b__L_Thigh__', 'b__R_Thigh__'], add: [0, -0.07, 0.085] },
  anus: { bone: 'b__Pelvis__', from: ['b__L_Thigh__', 'b__R_Thigh__'], add: [0, -0.07, -0.075] },
  butt: { bone: 'b__Pelvis__', from: ['b__L_Thigh__', 'b__R_Thigh__'], add: [0, -0.01, -0.13] },
  front: { bone: 'b__Pelvis__', from: ['b__L_Thigh__', 'b__R_Thigh__'], add: [0, 0.02, 0.11] },
  mouth: { bone: 'b__Head__', from: ['b__mouth_slot'], add: [0, 0, 0.01] },
  cleavage: { bone: 'b__Spine2__', from: ['b__CAS_L_Breast__', 'b__CAS_R_Breast__'], add: [0, -0.03, 0.06] },
};

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

// Local minima of a distance series that are close enough and reached fast enough.
function hits(d, fps, maxDist, minSpeed, gap, loop) {
  const n = d.length, out = [];
  const at = i => d[(i + n) % n];
  for (let i = 0; i < n; i++) {
    if (!loop && (i < 2 || i > n - 2)) continue;
    const v = at(i);
    if (v > maxDist || v > at(i - 1) || v >= at(i + 1)) continue;
    const speed = (at(i - 3) - v) * fps / 3;
    if (speed < minSpeed) continue;
    if (out.length && i - out[out.length - 1] < gap) continue;
    out.push(i);
  }
  return out;
}

export function autoSounds(app) {
  const p = app.store.project;
  const sims = p.sims;
  if (!sims.length || !sims.some(s => s.keys.length)) return 0;
  const off = offsets(app);
  const views = sims.map(s => app.simViews.get(s.id));
  // every frame through the full pipeline (keys + motions + pins + openings): contact points and what is inside.
  // Like the export: every sim with its motions (even the one being posed by hand) and only keyed poses.
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
  app.store.checkpoint();
  for (const s of sims) s.sounds = (s.sounds || []).filter(x => !x.auto);
  const counter = {};
  const add = (k, frame, set, kind) => {
    counter[set] = (counter[set] || 0) + 1;
    sims[k].sounds.push({ frame, name: pick(app, set, counter[set] - 1), kind, auto: true });
  };
  const n = p.length, at = (arr, i) => arr[((i % n) + n) % n];
  // 1. things going in: a sound when it enters and at every deepest point of a stroke
  let usedDepth = false;
  sims.forEach((s, k) => {
    for (const [hole, series] of Object.entries(inside[k])) {
      if (!series.some(x => x.d > 0)) continue;
      usedDepth = true;
      let last = -99;
      for (let i = 0; i < n; i++) {
        const cur = series[i], prev = at(series, i - 1);
        if (!p.loop && i === 0) continue;
        const by = cur.by || prev.by;
        const set = by === 'finger' ? 'finger' : by === 'tongue' ? 'lick' : HOLE_KIND[hole];
        if (cur.d > 0 && prev.d === 0 && i - last > 4) { add(k, i, cur.by === 'penis' ? 'insert' : set, 'wet'); last = i; continue; }
        // deepest point of a stroke: a local maximum that went at least 1 cm deeper than around it
        const a = at(series, i - 1).d, b = at(series, i + 1).d;
        if (cur.d > 0 && cur.d >= a && cur.d > b && i - last > 4) {
          let lo = cur.d;
          for (let j = 1; j <= 12; j++) lo = Math.min(lo, at(series, i - j).d);
          if (cur.d - lo > 0.01) { add(k, i, set, 'wet'); last = i; }
        }
      }
    }
  });
  const givers = sims.map((s, k) => k).filter(k => sims[k].gender === 'MALE' || views[k]?.hasPenis);
  const takers = sims.map((s, k) => k).filter(k => !givers.includes(k));
  const dist = (a, b) => a.map((x, i) => x.distanceTo(b[i]));
  for (const g of givers) {
    for (const t of takers) {
      const G = track[g], T = track[t];
      if (!usedDepth) {
        // no penetration measured (bodies without genitals): strokes from the giver's hips reaching an opening
        const targets = { vaginal: dist(G.genital, T.genital), anal: dist(G.genital, T.anus), oral: dist(G.genital, T.mouth), breasts: dist(G.genital, T.cleavage) };
        const taken = new Set();
        for (const [kind, d] of Object.entries(targets)) {
          for (const i of hits(d, p.fps, kind === 'oral' ? 0.12 : 0.14, 0.18, 5, p.loop)) {
            const best = Object.entries(targets).reduce((a, b) => (b[1][i] < a[1][i] ? b : a))[0];
            if (best !== kind || taken.has(i)) continue;
            taken.add(i);
            add(t, i, kind, 'wet');
          }
        }
      } else {
        for (const i of hits(dist(G.genital, T.cleavage), p.fps, 0.1, 0.18, 6, p.loop)) add(t, i, 'breasts', 'wet');
      }
      // claps: hips meeting fast (her butt or front on his hips), breasts slapping on him
      for (const d of [dist(G.front, T.butt), dist(G.front, T.front)]) for (const i of hits(d, p.fps, 0.17, 0.45, 5, p.loop)) add(t, i, 'clap', 'clap');
      for (const i of hits(dist(G.front, T.cleavage), p.fps, 0.16, 0.5, 6, p.loop)) add(t, i, 'clap', 'clap');
    }
  }
  for (const s of sims) {
    const seen = new Set();
    s.sounds = s.sounds.filter(x => { const key = x.frame + x.kind; if (x.auto && seen.has(key)) return false; seen.add(key); return true; });
  }
  app.applyPoses();
  return sims.reduce((a, s) => a + s.sounds.filter(x => x.auto).length, 0);
}
