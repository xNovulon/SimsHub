// Furniture at the game's sizes. The origin (the pink ring) is where WickedWhims puts the object.
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const mats = {
  fabric: new THREE.MeshStandardMaterial({ color: 0x5a6a86, roughness: 0.92 }),
  sheet: new THREE.MeshStandardMaterial({ color: 0xe9e4dc, roughness: 0.95 }),
  blanket: new THREE.MeshStandardMaterial({ color: 0x7d5a8c, roughness: 0.9 }),
  pillow: new THREE.MeshStandardMaterial({ color: 0xf4f1ea, roughness: 0.95 }),
  wood: new THREE.MeshStandardMaterial({ color: 0x6b4a33, roughness: 0.6 }),
  darkwood: new THREE.MeshStandardMaterial({ color: 0x3f2c22, roughness: 0.55 }),
  stone: new THREE.MeshStandardMaterial({ color: 0xcfd3d8, roughness: 0.35, metalness: 0.05 }),
  cabinet: new THREE.MeshStandardMaterial({ color: 0x2f3a4c, roughness: 0.5 }),
  wall: new THREE.MeshStandardMaterial({ color: 0x9aa3b5, roughness: 0.9 }),
  leather: new THREE.MeshStandardMaterial({ color: 0x8a5a3c, roughness: 0.55 }),
};

// ---------------------------------------------------------------- furniture never hides the sims
// Like the game's cutaway: the part of the furniture between the camera and what it looks at (the sims) turns
// see-through in a soft round window - a headboard, a sofa back or a bed post never blocks the view, in Showcase,
// in recordings and while posing. The window shrinks to nothing near the sims, so the mattress or seat under them
// stays solid. stage.js moves it with the camera every frame (updateCutaway). Costs a few maths per furniture pixel.
export const CUTAWAY = {
  cam: { value: new THREE.Vector3(0, 1, 3) }, target: { value: new THREE.Vector3(0, 0.8, 0) },
  radius: { value: 0.5 }, on: { value: 1 },
};
export function updateCutaway(camera, target, on = true) {
  CUTAWAY.cam.value.copy(camera.position);
  CUTAWAY.target.value.copy(target);
  CUTAWAY.radius.value = THREE.MathUtils.clamp(camera.position.distanceTo(target) * 0.2, 0.18, 0.6);
  CUTAWAY.on.value = on ? 1 : 0;
}
export function addCutaway(mat) {
  if (!mat || mat.userData.waCut) return mat;
  mat.userData.waCut = true;
  mat.transparent = true;                 // fully solid everywhere except inside the window (depth still written)
  const before = mat.onBeforeCompile;
  mat.onBeforeCompile = (shader, r) => {
    if (before) before.call(mat, shader, r);
    shader.uniforms.cutCam = CUTAWAY.cam; shader.uniforms.cutTarget = CUTAWAY.target;
    shader.uniforms.cutRadius = CUTAWAY.radius; shader.uniforms.cutOn = CUTAWAY.on;
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vCutW;')
      .replace('#include <project_vertex>', '#include <project_vertex>\n  vCutW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    const out = shader.fragmentShader.includes('#include <opaque_fragment>') ? '#include <opaque_fragment>' : '#include <output_fragment>';
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vCutW;\nuniform vec3 cutCam, cutTarget;\nuniform float cutRadius, cutOn;')
      .replace(out, `${out}
  if (cutOn > 0.5) {
    vec3 cutAB = cutTarget - cutCam;
    float cutT = clamp(dot(vCutW - cutCam, cutAB) / max(dot(cutAB, cutAB), 1e-4), 0.0, 1.0);
    float cutR = cutRadius * (1.0 - smoothstep(0.7, 0.95, cutT));
    float cutD = length(vCutW - (cutCam + cutAB * cutT));
    float cutIn = 1.0 - smoothstep(cutR * 0.5, cutR + 1e-4, cutD);
    gl_FragColor.a *= mix(1.0, 0.12, cutIn);
  }`);
  };
  const key = mat.customProgramCacheKey ? mat.customProgramCacheKey.bind(mat) : () => '';
  mat.customProgramCacheKey = () => key() + '|wa-cut';
  mat.needsUpdate = true;
  return mat;
}
for (const m of Object.values(mats)) addCutaway(m);

function box(w, h, d, mat, x = 0, y = 0, z = 0, r = 0.03) {
  const m = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2, h / 2, d / 2)), mat);
  m.position.set(x, y, z);
  m.castShadow = true; m.receiveShadow = true;
  return m;
}

// Every piece faces +Z (the side sims use), centred on the origin.
const BUILDERS = {
  floor() { return new THREE.Group(); },
  bed(w, d) {
    const g = new THREE.Group();
    const top = 0.52;
    g.add(box(w + 0.06, 0.26, d + 0.04, mats.darkwood, 0, 0.13, 0, 0.02));
    g.add(box(w, top - 0.26, d, mats.sheet, 0, 0.26 + (top - 0.26) / 2, 0, 0.05));
    g.add(box(w + 0.02, 0.05, d * 0.55, mats.blanket, 0, top + 0.01, d * 0.2, 0.025));
    const pillows = w > 1.4 ? [-w / 4, w / 4] : [0];
    for (const x of pillows) g.add(box(Math.min(0.62, w * 0.42), 0.13, 0.36, mats.pillow, x, top + 0.07, -d / 2 + 0.26, 0.06));
    g.add(box(w + 0.1, 1.1, 0.08, mats.darkwood, 0, 0.55, -d / 2 - 0.04, 0.02));
    return g;
  },
  sofa(w, d) {
    const g = new THREE.Group();
    const seat = 0.45;
    g.add(box(w, 0.22, d, mats.darkwood, 0, 0.11, 0, 0.02));
    const n = w > 2 ? 3 : 2;
    for (let k = 0; k < n; k++) {
      const cw = (w - 0.3) / n;
      g.add(box(cw - 0.02, seat - 0.22, d - 0.28, mats.fabric, -((w - 0.3) / 2) + cw * (k + 0.5), 0.22 + (seat - 0.22) / 2, 0.1, 0.06));
    }
    g.add(box(w, 0.5, 0.24, mats.fabric, 0, seat + 0.2, -d / 2 + 0.12, 0.08));
    g.add(box(0.15, 0.62, d, mats.fabric, -w / 2 + 0.075, 0.31, 0, 0.06));
    g.add(box(0.15, 0.62, d, mats.fabric, w / 2 - 0.075, 0.31, 0, 0.06));
    return g;
  },
  armchair(w, d) { return BUILDERS.sofa(w, d); },
  chair(w, d) {
    const g = new THREE.Group();
    const seat = 0.47;
    for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) g.add(box(0.04, seat, 0.04, mats.wood, x * (w / 2 - 0.03), seat / 2, z * (d / 2 - 0.03), 0.01));
    g.add(box(w, 0.05, d, mats.wood, 0, seat, 0, 0.015));
    g.add(box(w, 0.45, 0.04, mats.wood, 0, seat + 0.25, -d / 2 + 0.02, 0.015));
    return g;
  },
  counter(w, d) {
    const g = new THREE.Group();
    const h = 0.92;
    g.add(box(w, h - 0.04, d - 0.04, mats.cabinet, 0, (h - 0.04) / 2, -0.02, 0.01));
    g.add(box(w + 0.02, 0.04, d, mats.stone, 0, h - 0.02, 0, 0.01));
    return g;
  },
  table(w, d) {
    const g = new THREE.Group();
    const h = 0.76;
    for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) g.add(box(0.06, h - 0.04, 0.06, mats.wood, x * (w / 2 - 0.08), (h - 0.04) / 2, z * (d / 2 - 0.08), 0.01));
    g.add(box(w, 0.04, d, mats.wood, 0, h - 0.02, 0, 0.01));
    return g;
  },
  wall(w, h, d) {
    const g = new THREE.Group();
    g.add(box(w, h, d, mats.wall, 0, h / 2, -d / 2, 0.005));
    return g;
  },
};

export function buildFurniture(def) {
  if (!def || def.kind === 'floor' || !BUILDERS[def.kind] || !def.size) return new THREE.Group();
  const [w, h, d] = def.size;
  const fn = BUILDERS[def.kind];
  const g = def.kind === 'wall' ? fn(w, h, d) : fn(w, d);
  g.userData.furniture = def.id;
  g.userData.procedural = true;
  return g;
}

// Give back the GPU memory of furniture taken off the stage. Only the simple shapes' own geometry is freed:
// their materials are shared by every piece, and the real game object's meshes stay cached for next time
// (every copy on stage shares them).
export function disposeFurniture(g) {
  if (!g || !g.userData || !g.userData.procedural) return;
  g.traverse(o => { if (o.isMesh && o.geometry) o.geometry.dispose(); });
}

// ---------------------------------------------------------------- the real game object
// The exact mesh and textures of the object WickedWhims uses for this place (read from the game by the server),
// at its true size, with its origin where WickedWhims puts the sims. Falls back to the shapes above.
const _texLoader = new THREE.TextureLoader();
const _cache = new Map();

// The object's data (meshes, surface, spots) is fetched once per place and shared: the same promise sits in
// app._furnInfo, which placing.furnitureInfo and the app's own surface lookup use too.
function sharedInfo(id, app = window.app) {
  const map = app ? (app._furnInfo = app._furnInfo instanceof Map ? app._furnInfo : new Map()) : _infoFallback;
  if (!map.has(id)) {
    map.set(id, fetch('/api/furniture_mesh?v=2&id=' + encodeURIComponent(id)).then(r => (r.ok ? r.json() : null)).catch(() => null));
  }
  return Promise.resolve(map.get(id));
}
const _infoFallback = new Map();

export function loadGameFurniture(def, app = window.app) {
  if (!def || def.kind === 'floor') return Promise.resolve(null);
  if (_cache.has(def.id)) return _cache.get(def.id);
  const p = sharedInfo(def.id, app)
    .then(obj => {
      if (!obj || !obj.meshes || !obj.meshes.length) return null;
      const g = new THREE.Group();
      g.name = obj.name || def.label;
      for (const m of obj.meshes) {
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.Float32BufferAttribute(m.positions, 3));
        if (m.normals && m.normals.length) geo.setAttribute('normal', new THREE.Float32BufferAttribute(m.normals, 3));
        if (m.uvs && m.uvs.length) geo.setAttribute('uv', new THREE.Float32BufferAttribute(m.uvs, 2));
        geo.setIndex(m.faces);
        if (!m.normals || !m.normals.length) geo.computeVertexNormals();
        const mat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.78, metalness: 0, side: THREE.DoubleSide,
          transparent: !!m.transparent, opacity: m.transparent ? 0.55 : 1 });
        if (m.texture) {
          const tex = _texLoader.load('/api/furniture_tex?file=' + encodeURIComponent(m.texture));
          tex.colorSpace = THREE.SRGBColorSpace; tex.flipY = !!m.flipY; tex.anisotropy = 8;
          mat.map = tex;
        } else mat.color.set(0x8a7f95);
        addCutaway(mat);
        const mesh = new THREE.Mesh(geo, mat);
        mesh.castShadow = !m.transparent; mesh.receiveShadow = true;
        g.add(mesh);
      }
      g.userData.bounds = obj.bounds;
      g.userData.real = true;
      // where sims sit and lie (objmesh v2; empty before the server has them), and the top surface
      g.userData.slots = obj.slots || [];
      g.userData.grid = obj.surface_grid || null;
      g.userData.surface = obj.surface_height ?? null;
      return g;
    })
    .catch(() => null);
  _cache.set(def.id, p);
  return p;
}

// Flat markers for the furniture's spots (objmesh v2 slots), for the Place tool (spec_bodies 3.5): seats are a
// ring with a small arrow pointing the way the seat faces; bed edge seats are amber, sitting up in bed violet; lying
// spots are a green rounded outline (0.25 x 1.7 m) along the spot's direction. Each has a soft fill (easy to click).
// Each marker's userData.slot is its slot.
export function slotMarkers(slots = []) {
  const g = new THREE.Group();
  g.name = 'slot-markers';
  const matFor = color => new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.8, depthTest: false, side: THREE.DoubleSide });
  const fillFor = color => new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.16, depthTest: false, depthWrite: false, side: THREE.DoubleSide });
  for (const s of slots) {
    if (!s || !s.pos) continue;
    const dir = new THREE.Vector3(...(s.dir || [0, 0, 1])).setY(0);
    if (dir.lengthSq() < 1e-6) dir.set(0, 0, 1);
    dir.normalize();
    const m = new THREE.Group();
    m.position.set(s.pos[0], s.pos[1] + 0.01, s.pos[2]);
    m.rotation.y = Math.atan2(dir.x, dir.z);
    m.userData.slot = s;
    if (s.kind === 'lie') {
      const path = new THREE.Shape();
      const w = 0.125, l = 0.85;
      path.absarc(0, l - w, w, 0, Math.PI, false);
      path.absarc(0, -(l - w), w, Math.PI, Math.PI * 2, false);
      path.closePath();
      const hole = new THREE.Path();
      hole.absarc(0, l - w, w - 0.02, 0, Math.PI, false);
      hole.absarc(0, -(l - w), w - 0.02, Math.PI, Math.PI * 2, false);
      hole.closePath();
      path.holes.push(hole);
      const mesh = new THREE.Mesh(new THREE.ShapeGeometry(path, 24), matFor(0x3ddc97));
      mesh.rotation.x = -Math.PI / 2;
      // a soft fill inside the outline: easy to see and to click anywhere inside
      const fillShape = new THREE.Shape();
      fillShape.absarc(0, l - w, w, 0, Math.PI, false);
      fillShape.absarc(0, -(l - w), w, Math.PI, Math.PI * 2, false);
      fillShape.closePath();
      const fill = new THREE.Mesh(new THREE.ShapeGeometry(fillShape, 24), fillFor(0x3ddc97));
      fill.rotation.x = -Math.PI / 2;
      fill.position.y = -0.001;
      m.add(fill, mesh);
    } else {
      const col = s.kind === 'edge' ? 0xfbbf24 : s.kind === 'in' ? 0xa78bfa : 0x60a5fa;
      const mat = matFor(col);
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.07, 0.095, 40), mat);
      ring.rotation.x = -Math.PI / 2;
      const fill = new THREE.Mesh(new THREE.CircleGeometry(0.07, 32), fillFor(col));
      fill.rotation.x = -Math.PI / 2;
      fill.position.y = -0.001;
      const arrow = new THREE.Mesh(new THREE.ConeGeometry(0.03, 0.06, 12), mat);
      arrow.rotation.x = Math.PI / 2;
      arrow.position.set(0, 0, 0.14);
      m.add(fill, ring, arrow);
    }
    m.traverse(o => { if (o.isMesh) { o.renderOrder = 15; o.userData.slot = s; } });
    g.add(m);
  }
  return g;
}
