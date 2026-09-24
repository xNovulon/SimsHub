// Stand-in particles for the game's effects (spec_game 4): drool, splashes, drips, streams, tears, steam and
// sparkles, played from a body part while an Effect moment runs. The game's own effects (Swarm files) can't be drawn
// here; these show where, when and roughly what - and they look the same on every loop, in scrubbing and in videos.
//
// Same every loop: particle k of a moment is born at tb = start + k / rate (bursts at the start) and everything about
// it comes from a seeded random (the moment's id and k). Where it starts is the body part's place and direction at
// the frame it was born, read from the keys (a quiet pass over the needed frames, like Send to game does) - so the
// picture at frame 45 is the same in loop 1, loop 2 and in a recording.
import * as THREE from 'three';

// ---------------------------------------------------------------- the kinds
// emission: burst (at the start), rate (per second); speed m/s along the body part's direction (cone: spread in
// degrees; random: any direction); gravity m/s² (negative rises); life s; size m (grow: times bigger at the end);
// colour and alpha; additive blending for light.
export const KINDS = {
  splash: { burst: 60, rate: 20, speed: 1.2, cone: 50, gravity: 5.9, life: 0.7, size: 0.012, color: '#f4f4f2', alpha: 0.85, jitter: 0.004 },
  drool: { rate: 25, speed: 0.05, cone: 12, gravity: 1.2, life: 1.6, size: 0.008, color: '#eef3f6', alpha: 0.7, jitter: 0.01 },
  drip: { rate: 4, speed: 0, cone: 0, gravity: 9.8, life: 0.9, size: 0.006, color: '#dfe9f0', alpha: 0.8, jitter: 0.012 },
  stream: { rate: 120, speed: 2.2, cone: 6, gravity: 9.8, life: 0.6, size: 0.006, color: '#eef5ff', alpha: 0.8, jitter: 0.002 },
  tears: { rate: 3, speed: 0.02, cone: 20, gravity: 1.5, life: 1.2, size: 0.004, color: '#dff3ff', alpha: 0.9, jitter: 0.002, eyes: true },
  steam: { rate: 10, speed: 0.15, up: true, cone: 35, gravity: -0.3, life: 1.8, size: 0.05, grow: 2, color: '#ffffff', alpha: 0.18, jitter: 0.02 },
  sparkle: { rate: 20, speed: 0.3, random: true, gravity: 0, life: 0.8, size: 0.01, color: '#fff2b8', alpha: 1, additive: true, twinkle: true, jitter: 0.03 },
};
const PEE = '#f3e38a';
const MAX_EACH = 400, MAX_ALL = 1500;
// the effect picker's groups -> the kind of stand-in
export const GROUP_KIND = { 'Cum & splashes': 'splash', 'Drool & strands': 'drool', 'Drips & sweat': 'drip', Streams: 'stream',
  Tears: 'tears', 'Steam & breath': 'steam', 'Sparkles & flash': 'sparkle' };
const known = new Map();           // effect name -> its group, from the server's list (features/game.js fills it)
export function rememberEffectGroups(items) { for (const x of items || []) if (x && x.name && x.group) known.set(String(x.name).toLowerCase(), x.group); }
export function effectKind(name, group) {
  const g = group || known.get(String(name || '').toLowerCase());
  if (g && GROUP_KIND[g]) return GROUP_KIND[g];
  const n = String(name || '').toLowerCase();
  if (/drool|strand|puke/.test(n)) return 'drool';
  if (/splash/.test(n)) return 'splash';
  if (/drip|sweat|wet/.test(n)) return 'drip';
  if (/pee|spray|fountain|squirt|stream|pour/.test(n)) return 'stream';
  if (/cry|tear|weep/.test(n)) return 'tears';
  if (/steam|breath|smoke|fog|mist/.test(n)) return 'steam';
  if (/sparkle|flash|glow|magic/.test(n)) return 'sparkle';
  return 'drip';
}
export function kindColor(kind, name) { return kind === 'stream' && /pee/i.test(name || '') ? PEE : KINDS[kind].color; }

// ---------------------------------------------------------------- seeded random
export function hashStr(s) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
  return h >>> 0;
}
export function mulberry32(a) {
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------------------------------------------------------------- the particles of one effect at time t
// em = {id, kind, start, end (seconds), name}; at(tb) -> {pos: [x,y,z], dir: [x,y,z], side?: [x,y,z]} where the part
// was when a particle was born; ground(pos) -> the height drops land on. Writes into out (x, y, z, alpha, size per
// particle) and returns how many.
const _v = new THREE.Vector3(), _a = new THREE.Vector3(), _b = new THREE.Vector3(), _up = new THREE.Vector3(0, 1, 0);
const _ax = new THREE.Vector3(), _u1 = new THREE.Vector3(), _u2 = new THREE.Vector3();
export function particlesAt(em, t, at, ground, out, max = MAX_EACH) {
  const K = KINDS[em.kind] || KINDS.drip;
  const end = Math.max(em.start, em.end);
  if (t < em.start) return 0;
  const seed = hashStr(String(em.id));
  let n = 0;
  const born = [];
  // the burst at the start, then the steady ones
  const burst = K.burst || 0;
  const tNow = Math.min(t, end);
  for (let k = 0; k < burst; k++) if (t - em.start <= K.life) born.push([k, em.start]);
  const k0 = Math.max(0, Math.ceil((t - K.life - em.start) * K.rate - 1e-9));
  const k1 = Math.floor((tNow - em.start) * K.rate + 1e-9);
  for (let k = k0; k <= k1; k++) born.push([burst + k, em.start + k / K.rate]);
  for (const [k, tb] of born) {
    if (n >= max) break;
    const dt = t - tb;
    if (dt < 0 || dt > K.life || tb > end) continue;
    const rnd = mulberry32(seed ^ Math.imul(k + 1, 0x9E3779B1));
    const e = at(tb);
    if (!e) continue;
    const p0 = _a.fromArray(e.pos);
    const dir = _b.fromArray(e.dir);
    if (dir.lengthSq() < 1e-8) dir.set(0, 0, 1);
    dir.normalize();
    // where it leaves the body (tears: beside the eyes)
    if (K.eyes && e.eyes) p0.fromArray(e.eyes[k % 2]);
    p0.x += (rnd() - 0.5) * 2 * K.jitter; p0.y += (rnd() - 0.5) * 2 * K.jitter; p0.z += (rnd() - 0.5) * 2 * K.jitter;
    // which way it flies
    const v = _v;
    if (K.random) {
      const u = rnd() * 2 - 1, th = rnd() * Math.PI * 2, r = Math.sqrt(1 - u * u);
      v.set(r * Math.cos(th), u, r * Math.sin(th));
    } else {
      v.copy(K.up ? _up : dir);
      if (K.cone) {
        // a random direction inside the cone around v
        const c = Math.cos(THREE.MathUtils.degToRad(K.cone) * Math.sqrt(rnd()));
        const phi = rnd() * Math.PI * 2, s = Math.sqrt(Math.max(0, 1 - c * c));
        _ax.set(Math.abs(v.x) < 0.9 ? 1 : 0, Math.abs(v.x) < 0.9 ? 0 : 1, 0);
        const u1 = _u1.crossVectors(_ax, v).normalize(), u2 = _u2.crossVectors(v, u1);
        v.multiplyScalar(c).addScaledVector(u1, s * Math.cos(phi)).addScaledVector(u2, s * Math.sin(phi));
      }
    }
    const speed = K.speed * (0.75 + 0.5 * rnd());
    const vx = v.x * speed, vy = v.y * speed, vz = v.z * speed, g = K.gravity;
    let x = p0.x + vx * dt, y = p0.y + vy * dt - 0.5 * g * dt * dt, z = p0.z + vz * dt;
    // drops land and stay (on the floor, or on the bed when it starts above it)
    const floor = ground ? ground(p0) : 0;
    if (g > 0 && y < floor && p0.y >= floor) {
      const disc = vy * vy + 2 * g * (p0.y - floor);
      const tl = (vy + Math.sqrt(Math.max(0, disc))) / g;
      x = p0.x + vx * tl; z = p0.z + vz * tl; y = floor + 0.001;
    }
    const life = dt / K.life;
    let alpha = K.alpha * Math.min(1, dt / 0.05) * (life > 0.75 ? Math.max(0, 1 - (life - 0.75) / 0.25) : 1);
    if (K.twinkle) alpha *= 0.55 + 0.45 * Math.sin(dt * 28 + k * 1.7);
    const size = K.size * (K.grow ? 1 + (K.grow - 1) * life : 1) * (0.8 + 0.4 * rnd());
    const o = n * 5;
    out[o] = x; out[o + 1] = y; out[o + 2] = z; out[o + 3] = alpha; out[o + 4] = size;
    n++;
  }
  return n;
}

// ---------------------------------------------------------------- where a body part points
const _p = new THREE.Vector3(), _q = new THREE.Vector3();
// {pos, dir, eyes?} of a sim's bone right now (world space)
export function jointFrame(v, bone) {
  if (!v || !v.bone(bone)) return null;
  v.group.updateMatrixWorld(true);
  const pos = v.worldPos(bone, new THREE.Vector3());
  const dir = new THREE.Vector3();
  const has = n => !!v.bone(n);
  const w = (n, t = new THREE.Vector3()) => v.worldPos(n, t);
  if (/^b__Penis_/.test(bone) && has('b__Penis_Tip') && has('b__Penis_Mid')) dir.copy(w('b__Penis_Tip')).sub(w('b__Penis_Mid', _p));
  else if (/LoLip|Chin|Tounge|mouth|UpLip/.test(bone) && has('b__LoLip__') && has('b__Head__')) {
    // the head's forward, tipped down: from the head bone to the lower lip
    dir.copy(w('b__LoLip__')).sub(w('b__Head__', _p));
  } else if (/Stigmata/.test(bone)) {
    const hand = bone.includes('_L_') ? 'b__L_Hand__' : 'b__R_Hand__';
    if (has(hand)) dir.copy(pos).sub(w(hand, _p));
  } else if (bone === 'b__Head__' || /Brow|Eye/.test(bone)) dir.set(0, -1, 0);
  else {
    const b = v.bone(bone);
    if (b.parent && b.parent.isBone) dir.copy(pos).sub(b.parent.getWorldPosition(_p));
  }
  if (dir.lengthSq() < 1e-10) {
    // the sim's forward
    dir.set(0, 0, 1).applyQuaternion(v.group.getWorldQuaternion(new THREE.Quaternion()));
  }
  dir.normalize();
  const out = { pos: pos.toArray(), dir: dir.toArray() };
  if (has('b__L_Eye__') && has('b__R_Eye__') && (bone === 'b__Head__' || /Eye|Brow/.test(bone))) {
    // tears run from beside each eye (a little in front and below it)
    const fwd = has('b__LoLip__') ? w('b__LoLip__', _q).sub(w('b__Head__', _p)).setY(0) : new THREE.Vector3(0, 0, 1);
    if (fwd.lengthSq() < 1e-8) fwd.set(0, 0, 1);
    fwd.normalize();
    out.eyes = ['b__L_Eye__', 'b__R_Eye__'].map(n => w(n).addScaledVector(fwd, 0.012).add(new THREE.Vector3(0, -0.012, 0)).toArray());
  }
  return out;
}

// ---------------------------------------------------------------- sprites
// soft: a blurred round puff (steam, sparkles); drop: a wet droplet with a small highlight (everything liquid)
const _sprites = {};
function sprite(kind) {
  const name = kind === 'steam' || kind === 'sparkle' ? 'soft' : 'drop';
  if (_sprites[name]) return _sprites[name];
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  if (name === 'soft') {
    const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.45, 'rgba(255,255,255,0.85)'); grd.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
  } else {
    const body = g.createRadialGradient(32, 32, 0, 32, 32, 30);
    body.addColorStop(0, 'rgba(235,238,242,1)'); body.addColorStop(0.7, 'rgba(205,212,220,0.95)'); body.addColorStop(0.9, 'rgba(170,178,190,0.8)'); body.addColorStop(1, 'rgba(170,178,190,0)');
    g.fillStyle = body; g.fillRect(0, 0, 64, 64);
    const hi = g.createRadialGradient(24, 22, 0, 24, 22, 11);
    hi.addColorStop(0, 'rgba(255,255,255,1)'); hi.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = hi; g.fillRect(0, 0, 64, 64);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return (_sprites[name] = t);
}

function material(kind, color) {
  const K = KINDS[kind];
  // liquids stay under the stage's glow threshold (they are wet, not lights); sparkles and flashes glow
  const col = new THREE.Color(color).multiplyScalar(K.additive ? 1 : kind === 'steam' ? 0.9 : 0.78);
  return new THREE.ShaderMaterial({
    uniforms: { map: { value: sprite(kind) }, color: { value: col }, scale: { value: 400 } },
    vertexShader: `attribute float aAlpha; attribute float aSize; uniform float scale; varying float vAlpha;
      void main() { vAlpha = aAlpha; vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = max(2.0, aSize * scale / max(0.05, -mv.z)); gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform sampler2D map; uniform vec3 color; varying float vAlpha;
      void main() { vec4 t = texture2D(map, gl_PointCoord); float a = t.a * vAlpha; if (a < 0.01) discard;
        gl_FragColor = vec4(color * t.rgb, a); }`,
    transparent: true, depthWrite: false, depthTest: true,
    blending: K.additive ? THREE.AdditiveBlending : THREE.NormalBlending,
  });
}

// ---------------------------------------------------------------- the layer in the viewport
// moments(app) -> [{id, kind, name, start, end, simId, bone}] of the effects playing (features/game.js decides:
// visible, the sim is there, not skipped because of a condom).
export class EffectLayer {
  constructor(app, { scene = app.vp && app.vp.scene, moments = () => [] } = {}) {
    this.app = app;
    this.moments = moments;
    this.group = new THREE.Group();
    this.group.name = 'wa-effects';
    this.group.renderOrder = 5;
    if (scene) scene.add(this.group);
    this.visible = true;
    this.systems = new Map();        // moment id -> {points, geo, kind, color}
    this.history = new Map();        // simId|bone -> Map(frame -> {pos, dir, eyes})
    this._buf = new Float32Array(MAX_EACH * 5);
    this._timer = 0;
    this.lastCounts = {};
  }

  setVisible(on) { this.visible = !!on; this.group.visible = this.visible; }

  // The keys changed: where the body parts are is read again (a moment later, in one quiet pass).
  invalidate() { this.history.clear(); this._schedule(); }

  _schedule(ms = 350) {
    clearTimeout(this._timer);
    this._timer = setTimeout(() => { this._timerSet = false; this.sampleNow(); }, ms);
  }

  // The frames each playing effect needs (from its start to its end), for every sim and body part.
  _needed(list) {
    const p = this.app.store.project, fps = p.fps || 30, n = p.length;
    const need = new Map();
    for (const m of list) {
      const key = m.simId + '|' + m.bone;
      const f0 = Math.max(0, Math.floor(m.start * fps)), f1 = Math.min(n - 1, Math.ceil(m.end * fps));
      let set = need.get(key);
      if (!set) need.set(key, set = new Set());
      for (let f = f0; f <= f1; f++) set.add(f);
    }
    return need;
  }

  // One quiet pass over the frames the effects need, from the keys (never the unkeyed pose being edited), then the
  // current frame is put back. Returns how many frames were read.
  sampleNow() {
    const app = this.app;
    clearTimeout(this._timer);
    if (!app.pipeline || app.preview) return 0;
    if (app.vp && app.vp.dragging) { this._schedule(500); return 0; }
    const list = this.moments(app, { all: true });
    if (!list.length) return 0;
    const need = this._needed(list);
    const frames = new Set();
    for (const [key, set] of need) {
      const have = this.history.get(key);
      for (const f of set) if (!have || !have.has(f)) frames.add(f);
    }
    if (!frames.size) return 0;
    const order = [...frames].sort((a, b) => a - b);
    this._sampling = true;
    // like Send to game: a sim being posed by hand still moves with its motions here
    const editing = app.pipeline.editing;
    app.pipeline.editing = null;
    try {
      for (const f of order) {
        app.pipeline.apply(f, { physics: true, overrides: false });
        for (const [key, set] of need) {
          if (!set.has(f)) continue;
          const [simId, bone] = key.split('|');
          const fr = jointFrame(app.simViews.get(simId), bone);
          if (!fr) continue;
          let h = this.history.get(key);
          if (!h) this.history.set(key, h = new Map());
          h.set(f, fr);
        }
      }
    } finally {
      app.pipeline.editing = editing;
      this._sampling = false;
      app.applyPoses(false);             // the frame on screen again (with the pose being edited, if any)
    }
    return order.length;
  }

  // Where the part was at time tb (the frame it was born on), else where it is now.
  _at(m, tb, fps, live) {
    const h = this.history.get(m.simId + '|' + m.bone);
    const hit = h && h.get(Math.floor(tb * fps + 1e-6));
    if (hit) return hit;
    this._missing = true;
    return live(m);
  }

  _ground(p0) {
    const top = typeof this.app._surfaceTop === 'function' ? this.app._surfaceTop() : 0;
    return top > 0 && p0.y >= top - 0.02 ? top : 0;
  }

  // Put every playing effect's particles where they are at this frame.
  update(frame, playing = false) {
    if (this._sampling) return;
    const app = this.app;
    const p = app.store.project, fps = p.fps || 30;
    const list = this.visible && !app.preview ? this.moments(app) : [];
    const alive = new Set(list.map(m => m.id));
    for (const [id, s] of this.systems) if (!alive.has(id)) this._drop(id, s);
    if (!list.length) { this.lastCounts = {}; return; }
    const t = frame / fps;
    const now = new Map();
    const live = m => {
      const key = m.simId + '|' + m.bone;
      if (!now.has(key)) now.set(key, jointFrame(app.simViews.get(m.simId), m.bone));
      return now.get(key);
    };
    let total = 0;
    this._missing = false;
    this.lastCounts = {};
    for (const m of list) {
      let s = this.systems.get(m.id);
      const color = kindColor(m.kind, m.name);
      if (s && (s.kind !== m.kind || s.color !== color)) { this._drop(m.id, s); s = null; }
      if (!s) s = this._make(m, color);
      // a sim being posed by hand: its effects follow the pose on screen
      const editing = app.pipeline && app.pipeline.editing === m.simId;
      const at = editing ? () => live(m) : tb => this._at(m, tb, fps, live);
      const n = particlesAt(m, t, at, q => this._ground(q), this._buf, Math.min(MAX_EACH, MAX_ALL - total));
      total += n;
      this.lastCounts[m.id] = n;
      const pos = s.geo.attributes.position.array, al = s.geo.attributes.aAlpha.array, sz = s.geo.attributes.aSize.array;
      for (let i = 0; i < n; i++) {
        pos[i * 3] = this._buf[i * 5]; pos[i * 3 + 1] = this._buf[i * 5 + 1]; pos[i * 3 + 2] = this._buf[i * 5 + 2];
        al[i] = this._buf[i * 5 + 3]; sz[i] = this._buf[i * 5 + 4];
      }
      s.geo.setDrawRange(0, n);
      s.geo.attributes.position.needsUpdate = true; s.geo.attributes.aAlpha.needsUpdate = true; s.geo.attributes.aSize.needsUpdate = true;
      s.points.visible = n > 0;
    }
    // the size of a particle on screen follows the window's height and the lens
    const cam = app.vp && app.vp.camera, r = app.vp && app.vp.renderer;
    if (cam && r) {
      const hgt = r.domElement.clientHeight || 600;
      const scale = hgt / (2 * Math.tan(THREE.MathUtils.degToRad((cam.fov || 40) / 2)));
      for (const [, s] of this.systems) s.points.material.uniforms.scale.value = scale;
    }
    // a frame that was never read (an edit meanwhile): read it soon
    if (this._missing && !this._timerSet) { this._timerSet = true; this._schedule(playing ? 120 : 400); }
  }

  // positions of every particle right now, for checks: {momentId: [[x, y, z], ...]}
  snapshot() {
    const out = {};
    for (const [id, s] of this.systems) {
      const n = s.geo.drawRange.count === Infinity ? 0 : s.geo.drawRange.count;
      const a = s.geo.attributes.position.array;
      out[id] = [];
      for (let i = 0; i < n; i++) out[id].push([a[i * 3], a[i * 3 + 1], a[i * 3 + 2]]);
    }
    return out;
  }

  _make(m, color) {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(MAX_EACH * 3), 3).setUsage(THREE.DynamicDrawUsage));
    geo.setAttribute('aAlpha', new THREE.BufferAttribute(new Float32Array(MAX_EACH), 1).setUsage(THREE.DynamicDrawUsage));
    geo.setAttribute('aSize', new THREE.BufferAttribute(new Float32Array(MAX_EACH), 1).setUsage(THREE.DynamicDrawUsage));
    geo.setDrawRange(0, 0);
    const points = new THREE.Points(geo, material(m.kind, color));
    points.frustumCulled = false;
    points.renderOrder = 5;
    points.raycast = () => {};
    this.group.add(points);
    const s = { points, geo, kind: m.kind, color };
    this.systems.set(m.id, s);
    return s;
  }

  _drop(id, s) {
    this.group.remove(s.points);
    s.geo.dispose(); s.points.material.dispose();
    this.systems.delete(id);
  }

  clear() { for (const [id, s] of [...this.systems]) this._drop(id, s); }

  dispose() {
    clearTimeout(this._timer);
    this.clear();
    if (this.group.parent) this.group.parent.remove(this.group);
    this.history.clear();
  }
}

// ---------------------------------------------------------------- small looping previews (the effect picker)
// Drawn on a 2D canvas with the same particles: a body part in the middle, pointing the kind's usual way.
const PREVIEW_DIR = { splash: [0.25, 1, 0], drool: [0.15, -1, 0], drip: [0, -1, 0], stream: [1, 0.35, 0], tears: [0, -1, 0], steam: [0, 1, 0], sparkle: [0, 1, 0] };
const PREVIEW_AT = { splash: [0.5, 0.62], drool: [0.5, 0.18], drip: [0.5, 0.2], stream: [0.18, 0.4], tears: [0.5, 0.25], steam: [0.5, 0.78], sparkle: [0.5, 0.5] };
const PREVIEW_SCALE = { splash: 150, drool: 70, drip: 60, stream: 110, tears: 120, steam: 150, sparkle: 180 };
export function drawPreview(canvas, kind, name, t) {
  const g = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  g.clearRect(0, 0, W, H);
  const K = KINDS[kind] || KINDS.drip;
  const loop = Math.max(1.2, K.life + 1.1);
  const tt = t % loop;
  const em = { id: 'preview:' + (name || kind), kind, start: 0, end: loop - K.life * 0.4, name };
  const [ax, ay] = PREVIEW_AT[kind] || [0.5, 0.5], sc = PREVIEW_SCALE[kind] || 100;
  const d = PREVIEW_DIR[kind] || [0, 1, 0];
  const buf = new Float32Array(MAX_EACH * 5);
  const eyes = [[-0.03, 0, 0], [0.03, 0, 0]];
  const n = particlesAt(em, tt, () => ({ pos: [0, 0, 0], dir: d, eyes }), () => -10, buf, 220);
  const col = kindColor(kind, name);
  // the body part: a small glowing dot
  g.fillStyle = 'rgba(255,79,154,0.9)';
  g.beginPath(); g.arc(ax * W, ay * H, 3, 0, Math.PI * 2); g.fill();
  g.globalCompositeOperation = K.additive ? 'lighter' : 'source-over';
  for (let i = 0; i < n; i++) {
    const x = ax * W + buf[i * 5] * sc, y = ay * H - buf[i * 5 + 1] * sc;
    const r = Math.max(1, Math.min(9, buf[i * 5 + 4] * sc * 0.9));
    g.globalAlpha = Math.max(0, Math.min(1, buf[i * 5 + 3] * (kind === 'steam' ? 2.5 : 1)));
    g.fillStyle = col;
    g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
  }
  g.globalAlpha = 1;
  g.globalCompositeOperation = 'source-over';
}
