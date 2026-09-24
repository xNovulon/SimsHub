// A sim: the game's rig as a three.js skeleton with the game's nude body meshes skinned to it.
import * as THREE from 'three';
import { POSABLE, HIPS, HIPS_SET, EXTRA, FACE_CHANNEL, controllableIndex } from './bones.js';

const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _v = new THREE.Vector3();
const _q1 = new THREE.Quaternion(), _v1 = new THREE.Vector3();
const ID_Q = new THREE.Quaternion(), ZERO = new THREE.Vector3();
const reducedMotion = () => {
  try {
    return document.documentElement.classList.contains('reduce-motion') || !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  } catch { return false; }
};
const HOVER_MS = 90;            // the hover glow fades in and out over about 90 ms (design.md 4.3)
// The angle between two rotations. The rig's rest quaternions are stored as float32 and are not exactly unit
// length (the tongue's is off by 1e-6, which three.js's angleTo reads as 0.15 degrees), so both are normalised.
const angleBetween = (a, b) => {
  const d = Math.abs(a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w) / ((Math.hypot(a.x, a.y, a.z, a.w) * Math.hypot(b.x, b.y, b.z, b.w)) || 1);
  return 2 * Math.acos(Math.min(1, d));
};

export class Sim {
  constructor(rig, body, { color = '#ff6b9a', skin = '#e9b999' } = {}) {
    this.rig = rig;
    this.color = color;
    this.group = new THREE.Group();
    // Game space: Y up, sims face +Z, their left is +X - the same handedness as three.js, so the
    // data is shown as-is. `space` is where every pose computation happens.
    this.space = new THREE.Group();
    this.group.add(this.space);

    this.bones = rig.bones.map(b => {
      const bone = new THREE.Bone();
      bone.name = b.name;
      bone.position.fromArray(b.pos);
      bone.quaternion.fromArray(b.rot);
      bone.scale.fromArray(b.scale);
      return bone;
    });
    this.byName = {};
    this.bones.forEach((bone, k) => {
      this.byName[bone.name] = bone;
      const p = rig.bones[k].parent;
      if (p >= 0) this.bones[p].add(bone); else this.space.add(bone);
    });
    // another body's joints (a Tray sim's body sliders, WickedWhims' penis sizes): its bones rest somewhere else, and
    // its meshes were made for that bind pose (backend morph.rest_delta)
    this.restDelta = body.rest_delta && Object.keys(body.rest_delta).length ? body.rest_delta : null;
    if (this.restDelta) for (const [n, d] of Object.entries(this.restDelta)) { const b = this.byName[n]; if (b && Array.isArray(d)) b.position.add(new THREE.Vector3(d[0], d[1], d[2])); }
    this.rest = this.bones.map(b => ({ pos: b.position.clone(), quat: b.quaternion.clone() }));
    this.restByName = {};
    this.bones.forEach((b, k) => { this.restByName[b.name] = this.rest[k]; });
    this.group.updateMatrixWorld(true);
    this.skeleton = new THREE.Skeleton(this.bones);

    // What the automatic layers (face sliders, blinking, talking, the jaw carrying the mouth, the safety clamp,
    // twist helpers) added on top of the keys since resetPose(): bone name -> {q, p, abs}. The keys' own value of a
    // bone is `_base(name)`, so keying never bakes an automatic layer into a key.
    this.layerDelta = new Map();
    this._layerPool = [];
    this.pickMode = 'body';

    // skin: a soft sheen so the body reads as skin, not plastic
    this.material = new THREE.MeshPhysicalMaterial({ color: skin, roughness: 0.55, metalness: 0.0, vertexColors: true, sheen: 0.45, sheenRoughness: 0.55, sheenColor: new THREE.Color('#ffc9b8'), clearcoat: 0.04, clearcoatRoughness: 0.6 });
    // hover glow: a per-vertex amount added as light, on top of the skin, cross-faded from the part glowing before;
    // rim: a Fresnel edge light in the sim's colour (the selected sim, design.md 4.5)
    const u = this._fxU = {
      glowColor: { value: new THREE.Color('#8fe3ff') }, glowT: { value: 1 },
      rimColor: { value: new THREE.Color(color) }, rimAmount: { value: 0 },
    };
    this._glowT0 = -1e9;
    this._rim = { from: 0, to: 0, t0: 0, ms: 0 };
    this.material.onBeforeCompile = shader => {
      Object.assign(shader.uniforms, u);
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nattribute float glow;\nattribute float glowPrev;\nuniform float glowT;\nvarying float vGlow;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvGlow = mix(glowPrev, glow, glowT);');
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\nuniform vec3 glowColor;\nvarying float vGlow;\nuniform vec3 rimColor;\nuniform float rimAmount;')
        .replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\ntotalEmissiveRadiance += glowColor * vGlow * 0.42;\ndiffuseColor.rgb = mix(diffuseColor.rgb, glowColor, vGlow * 0.35);\n'
          + 'if (rimAmount > 0.0) { float waF = pow(1.0 - clamp(dot(normalize(normal), normalize(vViewPosition)), 0.0, 1.0), 3.2); totalEmissiveRadiance += rimColor * waF * rimAmount; }');
    };
    this.material.customProgramCacheKey = () => 'wa-sim-v2';
    const tick = () => this._tickFx();
    this.meshes = [];
    for (const part of body.meshes) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(part.positions, 3));
      if (part.normals.length) g.setAttribute('normal', new THREE.Float32BufferAttribute(part.normals, 3));
      if (part.uvs && part.uvs.length) g.setAttribute('uv', new THREE.Float32BufferAttribute(part.uvs, 2));
      g.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(part.bones, 4));
      g.setAttribute('skinWeight', new THREE.Float32BufferAttribute(part.weights, 4));
      const n = part.positions.length / 3;
      g.setAttribute('color', new THREE.Float32BufferAttribute(new Float32Array(n * 3).fill(1), 3));
      g.setAttribute('glow', new THREE.Float32BufferAttribute(new Float32Array(n), 1));
      g.setAttribute('glowPrev', new THREE.Float32BufferAttribute(new Float32Array(n), 1));
      g.setIndex(part.faces);
      if (!part.normals.length) g.computeVertexNormals();
      const mesh = new THREE.SkinnedMesh(g, this.material);
      mesh.name = part.part;
      mesh.userData.role = part.role || 'body';
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      mesh.frustumCulled = false;
      mesh.userData.sim = this;
      mesh.onBeforeRender = tick;
      this.space.add(mesh);
      mesh.bind(this.skeleton, new THREE.Matrix4());
      this.meshes.push(mesh);
    }
    this.highlighted = null;
    this.hovered = -1;
    const roles = new Set(this.meshes.map(m => m.userData.role));
    this.hasPenis = roles.has('penis_soft') || roles.has('penis_hard');
    this.hasVagina = body.frame === 'yf' && roles.has('bottom') && /NudeBottom_AF/.test(this.meshes.find(m => m.userData.role === 'bottom')?.name || '');
    this.setErect(true);
  }

  // Every bone's rest transform in the sim's space: the actual bind pose the meshes are skinned to (a body with moved
  // joints - rest_delta - included), computed once.
  _restWorld() {
    if (this._rw) return this._rw;
    const rw = [], one = new THREE.Vector3(1, 1, 1);
    this.rig.bones.forEach((b, k) => {
      const m = new THREE.Matrix4().compose(this.rest[k].pos, this.rest[k].quat, one);
      rw[k] = b.parent >= 0 ? rw[b.parent].clone().multiply(m) : m;
    });
    return (this._rw = rw);
  }

  // Where a group of bones actually sits on the skin: the centre of the vertices they move (bind pose), kept
  // relative to `anchor` so it follows the body. WickedWhims' vagina bones sit in front of the vulva they move,
  // so openings are found from the mesh, not the bones.
  skinPoint(boneNames, anchor = 'b__Pelvis__') {
    const key = boneNames.join() + '|' + anchor;
    this._skinPts = this._skinPts || {};
    if (key in this._skinPts) return this._skinPts[key];
    const ids = new Set(boneNames.map(n => this.index(n)).filter(i => i >= 0));
    const sum = new THREE.Vector3(); let wsum = 0;
    for (const mesh of this.meshes) {
      if (mesh.userData.role === 'penis_hard' || mesh.userData.role === 'tongue') continue;
      const pos = mesh.geometry.attributes.position, si = mesh.geometry.attributes.skinIndex, sw = mesh.geometry.attributes.skinWeight;
      for (let v = 0; v < pos.count; v++) {
        let w = 0;
        for (let k = 0; k < 4; k++) if (ids.has(si.getComponent(v, k))) w += sw.getComponent(v, k);
        if (w > 0.02) { sum.x += pos.getX(v) * w; sum.y += pos.getY(v) * w; sum.z += pos.getZ(v) * w; wsum += w; }
      }
    }
    if (!wsum) return (this._skinPts[key] = null);
    sum.multiplyScalar(1 / wsum);
    // bind pose = the rig's rest: express the point in the anchor bone's rest frame
    const a = this._restWorld()[this.index(anchor)];
    return (this._skinPts[key] = { anchor, local: sum.clone().applyMatrix4(a.clone().invert()) });
  }

  // The skin point now (world space).
  skinPointWorld(boneNames, anchor = 'b__Pelvis__') {
    const sp = this.skinPoint(boneNames, anchor);
    if (!sp) return null;
    const b = this.bone(sp.anchor);
    b.updateWorldMatrix(true, false);             // its own chain only: the pose may have changed since the last draw
    return b.localToWorld(sp.local.clone());
  }

  // Where a face bone's dot sits, in the bone's own rest frame (so bone.localToWorld() of it follows the face): the
  // centre of the skin that bone moves most (vertices with at least 60% of its strongest weight), on every mesh but
  // the penis. The jaw's dot sits on the chin; an eye's on the pupil. Cached per bone (a sim keeps its body).
  faceHandlePoint(name) {
    this._fhp = this._fhp || {};
    if (name in this._fhp) return this._fhp[name];
    // the lids: the dot sits on the lid's edge (its skin in front of the eye's middle, lowest for the upper lid,
    // highest for the lower one), so it follows the edge as the lid closes
    const up = /_UpLid__$/.test(name), lo = /_LoLid__$/.test(name);
    if ((up || lo) && this.index(name) >= 0) {
      const edge = this._lidEdge(name, up);
      if (edge) return (this._fhp[name] = edge);
    }
    const src = name === 'b__Jaw__' ? 'b__CAS_Chin__' : name;
    const id = this.index(src), anchor = this.index(name);
    const out = new THREE.Vector3();
    if (id >= 0 && anchor >= 0) {
      let best = 0;
      const hits = [];
      for (const mesh of this.meshes) {
        if (/penis/.test(mesh.userData.role || '')) continue;
        const pa = mesh.geometry.attributes.position, si = mesh.geometry.attributes.skinIndex, sw = mesh.geometry.attributes.skinWeight;
        for (let i = 0; i < pa.count; i++) {
          let w = 0;
          for (let k = 0; k < 4; k++) if (si.getComponent(i, k) === id) w += sw.getComponent(i, k);
          if (w > 0) { hits.push(pa.getX(i), pa.getY(i), pa.getZ(i), w); if (w > best) best = w; }
        }
      }
      let c = 0;
      for (let i = 0; i < hits.length; i += 4) if (hits[i + 3] >= best * 0.6) { out.x += hits[i]; out.y += hits[i + 1]; out.z += hits[i + 2]; c++; }
      if (c) {
        out.multiplyScalar(1 / c);
        // a curved part (a lid, a lip) has its centre under the skin: the dot goes to the skin point nearest to it
        // (an eye keeps the eyeball's centre: its dot goes on the pupil below)
        if (!/_Eye__$/.test(name)) {
          let bd = Infinity, bx = 0, by = 0, bz = 0;
          for (let i = 0; i < hits.length; i += 4) {
            if (hits[i + 3] < best * 0.6) continue;
            const d = (hits[i] - out.x) ** 2 + (hits[i + 1] - out.y) ** 2 + (hits[i + 2] - out.z) ** 2;
            if (d < bd) { bd = d; bx = hits[i]; by = hits[i + 1]; bz = hits[i + 2]; }
          }
          out.set(bx, by, bz);
        }
        out.applyMatrix4(this._restWorld()[anchor].clone().invert());
      }
    }
    if (/_Eye__$/.test(name)) out.y += 0.011;                  // on the pupil (y = forward)
    return (this._fhp[name] = out);
  }

  // A lid's edge in its bone's rest frame (bind pose): among the skin the lid moves most, the point in front of the
  // eye's middle that is lowest (upper lid) or highest (lower lid). null when the lid has no skin of its own.
  _lidEdge(name, upper) {
    const id = this.index(name), eye = this.index(name.replace(/_(Up|Lo)Lid__$/, '_Eye__'));
    if (id < 0 || eye < 0) return null;
    const rw = this._restWorld(), eyeAt = new THREE.Vector3().setFromMatrixPosition(rw[eye]);
    const hits = [];
    let most = 0;
    for (const mesh of this.meshes) {
      if (/penis/.test(mesh.userData.role || '')) continue;
      const pa = mesh.geometry.attributes.position, si = mesh.geometry.attributes.skinIndex, sw = mesh.geometry.attributes.skinWeight;
      for (let i = 0; i < pa.count; i++) {
        let w = 0;
        for (let k = 0; k < 4; k++) if (si.getComponent(i, k) === id) w += sw.getComponent(i, k);
        if (w > 0) { hits.push([pa.getX(i), pa.getY(i), pa.getZ(i), w]); if (w > most) most = w; }
      }
    }
    let best = null;
    for (const [x, y, z, w] of hits) {
      if (w < most * 0.5 || Math.abs(x - eyeAt.x) > 0.006 || z < eyeAt.z) continue;          // in front of the eye's middle
      if (!best || (upper ? y < best[1] : y > best[1])) best = [x, y, z];
    }
    if (!best) return null;
    return new THREE.Vector3(...best).applyMatrix4(rw[id].clone().invert());
  }

  // WickedWhims' soft and hard penis are two meshes on the same bones; show one.
  setErect(on) {
    this.erect = !!on;
    const hasHard = this.meshes.some(m => m.userData.role === 'penis_hard');
    for (const m of this.meshes) {
      if (m.userData.role === 'penis_hard') m.visible = this.erect;
      if (m.userData.role === 'penis_soft') m.visible = !this.erect || !hasHard;
    }
  }

  setTongue(on) { for (const m of this.meshes) if (m.userData.role === 'tongue') m.visible = !!on; }

  bone(name) { return this.byName[name]; }
  index(name) { return this.bones.indexOf(this.byName[name]); }

  setSkin(hex) { if (!this.textured) this.material.color.set(hex); }

  // See-through (1 = normal): the body and its hair together, no shadow while see-through.
  setOpacity(a) {
    const m = this.material, see = a < 1;
    m.transparent = see; m.opacity = a; m.depthWrite = !see; m.needsUpdate = true;
    for (const mesh of this.meshes) mesh.castShadow = !see;
    this._syncParts(true);
  }

  // ---------------------------------------------------------------- hair (and later other CAS parts)
  // A skinned CAS part on this skeleton. Two passes for soft hair edges: solid where alpha >= 0.5, then the thin
  // see-through edges blended on top without writing depth. data = /api/hair's {meshes: [{positions, normals, uvs,
  // faces, bones, weights}]}, texture = its diffuse (or null: a plain hair colour).
  addPart(data, texture, { role = 'hair', color = '#3b2a20' } = {}) {
    this.parts = this.parts || [];
    this.partMaterials = this.partMaterials || [];
    this._partGeoms = this._partGeoms || [];
    for (const part of (data && data.meshes) || []) {
      if (!part.positions || part.positions.length < 9 || !part.faces || !part.faces.length) continue;
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(part.positions, 3));
      if (part.normals && part.normals.length === part.positions.length) g.setAttribute('normal', new THREE.Float32BufferAttribute(part.normals, 3));
      if (part.uvs && part.uvs.length) g.setAttribute('uv', new THREE.Float32BufferAttribute(part.uvs, 2));
      g.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(part.bones, 4));
      g.setAttribute('skinWeight', new THREE.Float32BufferAttribute(part.weights, 4));
      g.setIndex(part.faces);
      if (!g.attributes.normal) g.computeVertexNormals();
      const base = texture ? { map: texture } : { color };
      const solid = new THREE.MeshStandardMaterial({ ...base, alphaTest: 0.5, side: THREE.DoubleSide, roughness: 0.5, metalness: 0 });
      const soft = new THREE.MeshStandardMaterial({ ...base, transparent: true, alphaTest: 0.04, depthWrite: false, side: THREE.DoubleSide, roughness: 0.5, metalness: 0 });
      for (const [mat, order] of [[solid, 0], [soft, 1]]) {
        const m = new THREE.SkinnedMesh(g, mat);
        m.renderOrder = order;
        m.castShadow = order === 0;
        m.receiveShadow = true;
        m.frustumCulled = false;
        m.name = (data.name || role) + (order ? ' (edges)' : '');
        m.userData.sim = this; m.userData.role = role; m.userData.soft = order === 1;
        this.space.add(m);
        m.bind(this.skeleton, new THREE.Matrix4());
        this.parts.push(m);
      }
      this.partMaterials.push(solid, soft);
      this._partGeoms.push(g);
    }
    this._partKey = null;
    this._syncParts(true);
    return this.parts.length;
  }

  removeParts(role = null) {
    if (!this.parts || !this.parts.length) return;
    const keep = [], gone = new Set(), mats = new Set();
    for (const m of this.parts) {
      if (role && m.userData.role !== role) { keep.push(m); continue; }
      m.removeFromParent();
      gone.add(m.geometry); mats.add(m.material);
    }
    for (const g of gone) g.dispose();
    for (const mt of mats) mt.dispose();          // the texture stays: it is shared (cached by the app)
    this.parts = keep;
    this.partMaterials = (this.partMaterials || []).filter(mt => !mats.has(mt));
    this._partGeoms = (this._partGeoms || []).filter(g => !gone.has(g));
  }

  // The hair follows the body's see-through state (see-through, the Face step fading a partner): same opacity, no
  // depth writing and no shadow while the body is see-through.
  _syncParts(force = false) {
    if (!this.parts || !this.parts.length) return;
    const m = this.material;
    const a = m.transparent ? m.opacity : 1;
    const key = a + '|' + m.depthWrite;
    if (!force && key === this._partKey) return;
    this._partKey = key;
    for (const p of this.parts) {
      const mat = p.material, soft = !!p.userData.soft;
      if (a < 1) { mat.transparent = true; mat.opacity = a; mat.depthWrite = false; }
      else { mat.transparent = soft; mat.opacity = 1; mat.depthWrite = !soft; }
      mat.needsUpdate = true;
      p.castShadow = a >= 1 && !soft;
    }
  }

  // The game's skin (skin tone + WickedWhims' body details), painted with the meshes' own UVs.
  setTexture(tex) {
    this.textured = !!tex;
    this.material.map = tex || null;
    this.material.color.set(tex ? '#ffffff' : this.material.color);
    this.material.needsUpdate = true;
  }

  // ---------------------------------------------------------------- automatic layers
  _layer(n) {
    let d = this.layerDelta.get(n);
    if (!d) {
      d = this._layerPool.pop() || { q: new THREE.Quaternion(), p: new THREE.Vector3(), abs: false };
      d.q.identity(); d.p.set(0, 0, 0); d.abs = false;
      this.layerDelta.set(n, d);
    }
    return d;
  }
  // An additive layer was put on a bone (final = base * dq, position + dp): face sliders, blinking, talking, the jaw
  // carrying the mouth, the safety clamp. Call it after changing the bone.
  addLayer(n, dq, dp) {
    const d = this._layer(n);
    if (dq) d.q.multiply(dq);
    if (dp) d.p.add(dp);
  }
  // An absolute layer (set from rest, e.g. the twist helpers): the keys have this bone at rest.
  setLayer(n, dq, dp) {
    const d = this._layer(n);
    d.q.copy(dq || ID_Q); d.p.copy(dp || ZERO); d.abs = true;
  }
  // The bone as the keys have it, without the automatic layers: {q, p} (new objects).
  _base(n) {
    const b = this.byName[n];
    const q = b.quaternion.clone(), p = b.position.clone();
    const d = this.layerDelta.get(n);
    if (!d) return { q, p };
    if (d.abs) {
      // still exactly what the layer set (rest * dq): the keys have it at rest; turned by hand since: what shows
      const r = this.restByName[n];
      _q1.copy(r.quat).multiply(d.q);
      if (angleBetween(_q1, q) < 1e-6) q.copy(r.quat);
      if (_v1.copy(r.pos).add(d.p).distanceToSquared(p) < 1e-14) p.copy(r.pos);
      return { q, p };
    }
    return { q: q.multiply(_q1.copy(d.q).invert()), p: p.sub(d.p) };
  }

  // ---------------------------------------------------------------- poses
  // A pose = local rotations of the posable bones + local positions of the hip bones, in game space.
  // Any other posable bone that sits away from its rest place (a stretched arm or spine from an imported clip)
  // keeps its place too, so the pose shows exactly the same when it is set again. Extra bones (twist helpers,
  // breasts, penis tip, expert bones) are only written where they are posed. Face bones are not part of it (see
  // getFaceBones), and automatic layers never are: everything is read as the keys have it.
  getPose() {
    const rot = {}, pos = {};
    for (const n of POSABLE) {
      const b = this.byName[n];
      if (!b) continue;
      const { q, p } = this._base(n);
      rot[n] = q.toArray();
      if (HIPS_SET.has(n) || p.distanceToSquared(this.restByName[n].pos) > 1e-10) pos[n] = p.toArray();
    }
    for (const n of HIPS) if (this.byName[n]) pos[n] = this._base(n).p.toArray();
    for (const n of EXTRA) {
      const b = this.byName[n];
      if (!b) continue;
      const { q, p } = this._base(n), r = this.restByName[n];
      if (angleBetween(q, r.quat) > 1e-3) rot[n] = q.toArray();
      if (p.distanceToSquared(r.pos) > 2.5e-9) pos[n] = p.toArray();       // 0.05 mm
    }
    return { rot, pos };
  }

  setPose(pose) {
    if (!pose) return;
    for (const [n, q] of Object.entries(pose.rot || {})) { const b = this.byName[n]; if (b) b.quaternion.fromArray(q); }
    for (const [n, p] of Object.entries(pose.pos || {})) { const b = this.byName[n]; if (b) b.position.fromArray(p); }
  }

  // The face as posed by hand: sparse {rot, pos} of the 30 face bones, as the keys have them. `withLayer` reads
  // what shows instead (sliders, blinking and talking included) - "Make this expression editable".
  getFaceBones({ withLayer = false } = {}) {
    const rot = {}, pos = {};
    for (const n of FACE_CHANNEL) {
      const b = this.byName[n], r = this.restByName[n];
      if (!b || !r) continue;
      const { q, p } = withLayer ? { q: b.quaternion, p: b.position } : this._base(n);
      if (angleBetween(q, r.quat) > 1e-4) rot[n] = q.toArray();
      if (p.distanceToSquared(r.pos) > 2.5e-11) pos[n] = p.toArray();      // 0.005 mm
    }
    return { rot, pos };
  }

  // Set the face bones as the keys have them: the mentioned bones take their values, every other face bone goes to
  // rest. Automatic layers already on a face bone stay on top.
  setFaceBones(fb) {
    const rot = (fb && fb.rot) || {}, pos = (fb && fb.pos) || {};
    for (const n of FACE_CHANNEL) {
      const b = this.byName[n], r = this.restByName[n];
      if (!b || !r) continue;
      if (rot[n]) b.quaternion.fromArray(rot[n]); else b.quaternion.copy(r.quat);
      if (pos[n]) b.position.fromArray(pos[n]); else b.position.copy(r.pos);
      const d = this.layerDelta.size ? this.layerDelta.get(n) : null;
      if (d && !d.abs) { b.quaternion.multiply(d.q); b.position.add(d.p); }
    }
  }

  resetPose() {
    this.bones.forEach((b, k) => { b.position.copy(this.rest[k].pos); b.quaternion.copy(this.rest[k].quat); });
    if (this.layerDelta.size) { for (const d of this.layerDelta.values()) this._layerPool.push(d); this.layerDelta.clear(); }
  }

  // Full local transforms of every bone (for playing clips and for export).
  applyTracks(sample) {
    for (const [n, tr] of Object.entries(sample)) {
      const b = this.byName[n];
      if (!b) continue;
      if (tr.r) b.quaternion.fromArray(tr.r);
      if (tr.t) b.position.fromArray(tr.t);
    }
  }

  // ---------------------------------------------------------------- world helpers
  worldPos(name, target = new THREE.Vector3()) {
    return this.byName[name].getWorldPosition(target);
  }

  // ---------------------------------------------------------------- highlight
  // What a click picks: 'body' (today's parts), or 'face' (every face bone its own part, for the Face tool and the
  // Pose tool close to a face). The hover glow and the selection tint follow it.
  setPickMode(mode) {
    if (mode === this.pickMode) return;
    this.pickMode = mode;
    this.highlighted = null;
    this.hovered = undefined;
  }

  // How much of each vertex belongs to a part (twist, face and CAS bones count for the part they sit on, in the
  // current pick mode).
  _partWeight(mesh, part) {
    this._ctrlBy = this._ctrlBy || {};
    const mode = this.pickMode || 'body';
    const ctrl = this._ctrlBy[mode] || (this._ctrlBy[mode] = this.rig.bones.map((b, k) => controllableIndex(this.rig, k, mode)));
    const si = mesh.geometry.attributes.skinIndex, sw = mesh.geometry.attributes.skinWeight;
    const out = new Float32Array(si.count);
    if (part === 'all') return out.fill(1);
    if (part === undefined || part === null || part < 0) return out;
    for (let v = 0; v < si.count; v++) {
      let w = 0;
      for (let k = 0; k < 4; k++) if (ctrl[si.getComponent(v, k)] === part) w += sw.getComponent(v, k);
      out[v] = Math.min(1, w);
    }
    return out;
  }

  // The selected part, tinted in the sim's colour.
  highlight(boneIndex, color = this.color) {
    const key = boneIndex + '|' + color + '|' + this.pickMode;
    if (key === this.highlighted) return;
    this.highlighted = key;
    const c = new THREE.Color(color);
    for (const mesh of this.meshes) {
      const w = this._partWeight(mesh, boneIndex), col = mesh.geometry.attributes.color;
      for (let v = 0; v < w.length; v++) {
        const t = w[v] * 0.75;
        col.setXYZ(v, 1 + (c.r - 1) * t, 1 + (c.g - 1) * t, 1 + (c.b - 1) * t);
      }
      col.needsUpdate = true;
    }
  }

  // The part under the mouse glows, so you can see what a click will pick. 'all' lights the whole sim. The glow
  // fades from the part that glowed before over about 90 ms.
  hover(part) {
    if (part === this.hovered) return;
    this.hovered = part;
    const now = performance.now();
    const t = reducedMotion() ? 1 : this._glowMix(now);
    for (const mesh of this.meshes) {
      const g = mesh.geometry.attributes.glow, g0 = mesh.geometry.attributes.glowPrev;
      const a = g.array, a0 = g0.array;
      for (let i = 0; i < a.length; i++) a0[i] += (a[i] - a0[i]) * t;       // what shows now fades out from here
      a.set(this._partWeight(mesh, part));
      g.needsUpdate = true; g0.needsUpdate = true;
    }
    this._glowT0 = reducedMotion() ? -1e9 : now;
    this._fxU.glowT.value = this._glowMix(now);
  }
  _glowMix(now) { return Math.min(1, Math.max(0, (now - this._glowT0) / HOVER_MS)); }

  // A Fresnel rim light in `colorHex` (the sim's colour for the selected sim), amount 0..1. `ms` fades to it.
  setRim(colorHex, amount = 0.5, ms = 0) {
    const now = performance.now();
    if (colorHex) this._fxU.rimColor.value.set(colorHex);
    const r = this._rim;
    r.from = this._rimAt(now); r.to = Math.max(0, Math.min(1, +amount || 0)); r.t0 = now; r.ms = reducedMotion() ? 0 : Math.max(0, ms);
    this._fxU.rimAmount.value = this._rimAt(now);
  }
  get rimAmount() { return this._rim.to; }
  _rimAt(now) {
    const r = this._rim;
    if (!r.ms) return r.to;
    const k = Math.min(1, (now - r.t0) / r.ms), e = 1 - Math.pow(1 - k, 3);
    return r.from + (r.to - r.from) * e;
  }
  // per render: advance the glow cross-fade and the rim fade (cheap; runs only while this sim is drawn)
  _tickFx() {
    const now = performance.now();
    this._fxU.glowT.value = this._glowMix(now);
    this._fxU.rimAmount.value = this._rimAt(now);
    if (this.parts && this.parts.length) this._syncParts();
  }

  // Which bone a raycast hit landed on: the strongest influence at the hit triangle.
  boneAtHit(hit) {
    const g = hit.object.geometry, si = g.attributes.skinIndex, sw = g.attributes.skinWeight;
    const acc = new Map();
    for (const v of [hit.face.a, hit.face.b, hit.face.c]) {
      for (let k = 0; k < 4; k++) {
        const b = si.getComponent(v, k), w = sw.getComponent(v, k);
        acc.set(b, (acc.get(b) || 0) + w);
      }
    }
    let best = -1, bw = -1;
    for (const [b, w] of acc) if (w > bw) { best = b; bw = w; }
    return best;
  }

  dispose() {
    this.removeParts();
    for (const m of this.meshes) m.geometry.dispose();
    this.material.dispose();
    this.skeleton.dispose();                      // the bone texture on the GPU
    this.group.removeFromParent();
  }
}

export { _m, _q, _v };
