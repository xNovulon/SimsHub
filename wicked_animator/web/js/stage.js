// The studio look of the 3D view: a backdrop dome with a soft gradient (no hard horizon), a floor grid that fades
// out, fog that melts the floor's edge into the dome, five lighting looks, a cinematic mode for Showcase and
// recording (bloom at half size, vignette and grain; editing stays sharp), and a rim light for the selected sim.
// Cheap while editing: the dome and the grid are one draw call each; bloom and vignette run only in cinematic mode.
import * as THREE from 'three';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { updateCutaway } from './furniture.js';
import { $t } from './i18n.js';

// sky: [top, middle (horizon), below]; glow: a soft band of light at the horizon; floor: [centre, edge]
export const LOOKS = {
  studio: { label: $t('stage.studio'), sub: $t('stage.clear_light_for_posing'), exposure: 1.08,
    sky: ['#0a0810', '#241a2f', '#150f1c'], glow: ['#6a3a78', 0.28], fog: [5.5, 15], floor: ['#3a3046', '#241a2f'],
    hemi: ['#fff4ee', '#2a2228', 0.85], key: ['#fff3ea', 2.5], rim: ['#ff7ab8', 0.75], rim2: ['#a88bff', 0.55], fill: ['#fff0e8', 0.6], bloom: 0.25 },
  boudoir: { label: $t('stage.boudoir'), sub: $t('stage.warm_pink_rim_romantic'), exposure: 1.0,
    sky: ['#080506', '#1d0f16', '#0f080c'], glow: ['#8a3050', 0.22], fog: [5, 14], floor: ['#43283a', '#2b1420'],
    hemi: ['#ffd9c2', '#2a1418', 0.6], key: ['#ffd2a8', 2.2], rim: ['#ff5fa2', 1.5], rim2: ['#c070ff', 0.7], fill: ['#ffb99a', 0.35], bloom: 0.45 },
  neon: { label: $t('stage.neon_night'), sub: $t('stage.dark_with_pink_and_blue'), exposure: 0.95,
    sky: ['#040308', '#0d0a18', '#07050c'], glow: ['#2c2466', 0.26], fog: [4.5, 13], floor: ['#241c3a', '#130f24'],
    hemi: ['#9aa6ff', '#10081a', 0.35], key: ['#e6e0ff', 1.3], rim: ['#ff3fa4', 2.4], rim2: ['#3fd8ff', 2.0], fill: ['#7a6cff', 0.25], bloom: 0.7 },
  daylight: { label: $t('stage.daylight'), sub: $t('stage.soft_and_even_check_clipping'), exposure: 1.15,
    sky: ['#2c2a36', '#56505f', '#3a3542'], glow: ['#8a7f96', 0.2], fog: [7, 20], floor: ['#6b6474', '#56505f'],
    hemi: ['#ffffff', '#6a6070', 1.5], key: ['#ffffff', 1.6], rim: ['#ffffff', 0.4], rim2: ['#dfe8ff', 0.4], fill: ['#ffffff', 0.9], bloom: 0 },
  candle: { label: $t('stage.candle'), sub: $t('stage.low_warm_light_for_showcase'), exposure: 1.05,
    sky: ['#050302', '#160c07', '#0a0604'], glow: ['#6a3814', 0.24], fog: [4, 12], floor: ['#3a2416', '#1e110a'],
    hemi: ['#ffb070', '#140a06', 0.35], key: ['#ffb36b', 2.0], rim: ['#ff8a3d', 1.1], rim2: ['#ff5fa2', 0.5], fill: ['#ff9a55', 0.3], bloom: 0.55, flicker: true },
};

const VIGNETTE = {
  uniforms: { tDiffuse: { value: null }, amount: { value: 0.0 }, grain: { value: 0.0 }, time: { value: 0 } },
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
  fragmentShader: `uniform sampler2D tDiffuse; uniform float amount, grain, time; varying vec2 vUv;
    float rnd(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233)) + time) * 43758.5453); }
    void main(){ vec4 c = texture2D(tDiffuse, vUv);
      vec2 d = vUv - 0.5; float v = smoothstep(0.85, 0.25, length(d * vec2(1.0, 1.15)));
      c.rgb *= mix(1.0, v, amount);
      c.rgb += (rnd(vUv * 900.0) - 0.5) * grain;
      gl_FragColor = c; }`,
};

// The dome's colour right at the horizon (= the fog colour, so the fogged floor meets the dome without an edge).
function horizonColor(look) {
  return new THREE.Color(look.sky[1]).add(new THREE.Color(look.glow[0]).multiplyScalar(look.glow[1]));
}

export function installStage(vp) {
  const scene = vp.scene;
  const dirs = scene.children.filter(o => o.isDirectionalLight);
  const L = vp.lights || { hemi: scene.children.find(o => o.isHemisphereLight), key: dirs[0], rim: dirs[1], rim2: dirs[2], fill: dirs[3] };

  // --- backdrop dome: a vertical gradient all around, a faint light band at the horizon, and below the horizon the
  // horizon colour first (where the floor ends in the fog), darkening further down
  const domeU = { top: { value: new THREE.Color() }, mid: { value: new THREE.Color() }, low: { value: new THREE.Color() },
    glow: { value: new THREE.Color() }, glowAmt: { value: 0.3 } };
  const dome = new THREE.Mesh(new THREE.SphereGeometry(40, 48, 24), new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false, uniforms: domeU,
    vertexShader: 'varying vec3 vDir; void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
    fragmentShader: `uniform vec3 top, mid, low, glow; uniform float glowAmt; varying vec3 vDir;
      void main(){ float h = normalize(vDir).y;
        vec3 hz = mid + glow * glowAmt;
        vec3 c = h >= 0.0 ? mix(mid, top, smoothstep(0.0, 0.6, h)) + glow * exp(-pow(h * 7.0, 2.0)) * glowAmt
                          : mix(hz, low, smoothstep(0.06, 0.35, -h));
        gl_FragColor = vec4(c, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  }));
  dome.name = 'dome'; dome.renderOrder = -10; dome.frustumCulled = false;
  dome.raycast = () => {};
  scene.add(dome);

  // --- floor grid that fades with distance: 1 m lines and faint 25 cm lines near the middle
  const oldGrid = scene.children.find(o => o.isGridHelper || o.type === 'GridHelper');
  if (oldGrid) oldGrid.visible = false;
  const grid = new THREE.Mesh(new THREE.PlaneGeometry(24, 24), new THREE.ShaderMaterial({
    transparent: true, depthWrite: false,
    uniforms: { color: { value: new THREE.Color('#c9b6e6') }, fade: { value: 4.2 } },
    vertexShader: 'varying vec3 vW; void main(){ vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }',
    fragmentShader: `uniform vec3 color; uniform float fade; varying vec3 vW;
      float line(vec2 p, float s){ vec2 q = p / s; vec2 g = abs(fract(q - 0.5) - 0.5) / fwidth(q); return 1.0 - min(min(g.x, g.y), 1.0); }
      void main(){ float d = length(vW.xz);
        float a = line(vW.xz, 1.0) * 0.085 + line(vW.xz, 0.25) * 0.025 * (1.0 - smoothstep(0.8, 1.8, d));
        a *= 1.0 - smoothstep(fade * 0.35, fade, d);
        gl_FragColor = vec4(color, a);
        #include <colorspace_fragment>
      }`,
  }));
  grid.rotation.x = -Math.PI / 2; grid.position.y = 0.0015; grid.renderOrder = 1; grid.name = 'grid';
  grid.raycast = () => {};
  scene.add(grid);

  // --- cinematic passes (off until cinematic(true)), before the OutputPass; bloom at half size
  const size = new THREE.Vector2(); vp.renderer.getSize(size);
  const bloom = new UnrealBloomPass(new THREE.Vector2(Math.max(1, size.x / 2), Math.max(1, size.y / 2)), 0.35, 0.55, 0.82);
  bloom.enabled = false;
  const vign = new ShaderPass(VIGNETTE); vign.enabled = false;
  const at = Math.max(0, vp.composer.passes.length - 1);
  vp.composer.insertPass(bloom, at);
  vp.composer.insertPass(vign, at + 1);

  let look = LOOKS.studio, lookId = 'studio', cine = false, flickerT = 0, bloomAllowed = true;
  // the lit centre stays about 3.5 m wide whatever the floor size (the floor is 20 m, its edge always in the fog)
  const floorTex = (c0, c1) => {
    const R = (vp.floor && vp.floor.geometry.parameters.radius) || 7, s = Math.min(1, 3.5 / R);
    const c = document.createElement('canvas'); c.width = c.height = 512;
    const g = c.getContext('2d'), gr = g.createRadialGradient(256, 256, 8, 256, 256, 256);
    gr.addColorStop(0, c0); gr.addColorStop(s * 0.55, c0); gr.addColorStop(s, c1); gr.addColorStop(1, c1);
    g.fillStyle = gr; g.fillRect(0, 0, 512, 512);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
  };

  function apply(name) {
    lookId = LOOKS[name] ? name : 'studio';
    look = LOOKS[lookId];
    domeU.top.value.set(look.sky[0]); domeU.mid.value.set(look.sky[1]); domeU.low.value.set(look.sky[2]);
    domeU.glow.value.set(look.glow[0]); domeU.glowAmt.value = look.glow[1];
    const hz = horizonColor(look);
    scene.background = hz.clone();
    if (scene.fog) { scene.fog.color.copy(hz); scene.fog.near = look.fog[0]; scene.fog.far = look.fog[1]; }
    else scene.fog = new THREE.Fog(hz, look.fog[0], look.fog[1]);
    if (vp.floor) { const old = vp.floor.material.map; vp.floor.material.map = floorTex(look.floor[0], look.floor[1]); vp.floor.material.needsUpdate = true; old && old.dispose(); }
    if (L.hemi) { L.hemi.color.set(look.hemi[0]); L.hemi.groundColor.set(look.hemi[1]); L.hemi.intensity = look.hemi[2]; }
    for (const k of ['key', 'rim', 'rim2', 'fill']) if (L[k]) { L[k].color.set(look[k][0]); L[k].intensity = look[k][1]; L[k].userData.base = look[k][1]; }
    vp.renderer.toneMappingExposure = look.exposure;
    bloom.strength = look.bloom || 0.3;
    bloom.enabled = cine && bloomAllowed && (look.bloom || 0) > 0;
    vp.requestRender?.();
    return lookId;
  }

  function cinematic(on) {
    cine = !!on;
    bloom.enabled = cine && bloomAllowed && (look.bloom || 0) > 0;
    vign.enabled = cine;
    vign.uniforms.amount.value = cine ? 0.55 : 0;
    vign.uniforms.grain.value = cine ? 0.006 : 0;
    document.body.classList.toggle('cinematic', cine);
  }

  // adaptive quality, step 1: no bloom (restored by allowBloom(true))
  function allowBloom(on) { bloomAllowed = !!on; bloom.enabled = cine && bloomAllowed && (look.bloom || 0) > 0; }

  vp.onFrame.push(dt => {
    dome.position.copy(vp.camera.position);                // the dome is always around the camera
    // furniture between the camera and what it looks at turns see-through (furniture.js cutaway)
    if (vp.furniture && vp.furniture.children.length) updateCutaway(vp.camera, vp.controls.target, vp.cutaway !== false);
    if (vign.enabled) vign.uniforms.time.value = (vign.uniforms.time.value + dt) % 100;
    if (look.flicker && L.key) {                           // candle: a slow, small wobble of the key light
      flickerT += dt;
      L.key.intensity = L.key.userData.base * (0.92 + 0.05 * Math.sin(flickerT * 7.1) + 0.03 * Math.sin(flickerT * 17.3));
    }
  });
  const resize = () => { const s = new THREE.Vector2(); vp.renderer.getSize(s); bloom.setSize(Math.max(1, s.x / 2), Math.max(1, s.y / 2)); };
  window.addEventListener('resize', resize);

  apply('studio');
  return {
    apply, cinematic, allowBloom, dome, grid, bloom, vignette: vign,
    get look() { return lookId; }, get lookInfo() { return look; }, get isCinematic() { return cine; },
    get bloomOn() { return bloom.enabled; }, horizon: () => horizonColor(look),
  };
}

// Rim light for a sim (used when the sim has no setRim of its own): one Fresnel term added to its shader.
// Returns {rim: {value 0..1}, rimColor: {value: Color}}.
export function addRim(material, color = '#ff8cc4') {
  if (material.userData.waRim) return material.userData.waRim;
  const rim = { value: 0 }, rimColor = { value: new THREE.Color(color) };
  const before = material.onBeforeCompile;
  material.onBeforeCompile = (shader, r) => {
    before && before.call(material, shader, r);
    shader.uniforms.rimAmount = rim; shader.uniforms.rimColor = rimColor;
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform float rimAmount;\nuniform vec3 rimColor;')
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
        float waF = pow(1.0 - clamp(dot(normalize(normal), normalize(vViewPosition)), 0.0, 1.0), 3.2);
        totalEmissiveRadiance += rimColor * waF * rimAmount;`);
  };
  const key = material.customProgramCacheKey ? material.customProgramCacheKey.bind(material) : () => '';
  material.customProgramCacheKey = () => key() + '|wa-rim';
  material.needsUpdate = true;
  material.userData.waRim = { rim, rimColor };
  return material.userData.waRim;
}
