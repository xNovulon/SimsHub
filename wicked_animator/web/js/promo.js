// The promo kit: seamless-loop GIFs from 2-3 camera angles, a square thumbnail, a 10-second video with sound and the
// text to post - all made from the app's own stage (no game, no OBS, no ezgif) and saved into one folder next to the
// exports (/api/promo_save). A "safe teaser" option frames only heads and shoulders, or lays a blur band over the
// bodies, for sites that ban explicit pictures.
//
// Also the stage helpers the pose packs use: withStage() (pause the stage, hide the helpers, film, then put everything
// back), fitView(), sphereOf(), grab() and pickAngles().
import * as THREE from 'three';
import { h, icon, modal, toast, emitWA } from './ui.js';
import { successHero, celebrateAt } from './fx.js';
import { api } from './api.js';
import { GifMaker } from './gif.js';
import { captureVideo, holdGizmo } from './record.js';
import { KINDS, tagLabel } from './tags.js';

export const MAX_GIF = 5 * 1024 * 1024;           // Tumblr's advice: under 5 MB
const BODY = ['b__Head__', 'b__Pelvis__', 'b__L_Foot__', 'b__R_Foot__', 'b__L_Hand__', 'b__R_Hand__', 'b__L_Calf__', 'b__R_Calf__', 'b__Spine2__'];
const HEADS = ['b__Head__', 'b__Neck__'];
const BAND = ['b__Spine2__', 'b__Spine1__', 'b__Pelvis__', 'b__L_Thigh__', 'b__R_Thigh__', 'b__L_Calf__', 'b__R_Calf__'];
export const TEASERS = [['none', 'Off'], ['shoulders', 'Shoulders up'], ['blur', 'Blur band']];

const kindName = k => (KINDS.find(x => x[0] === k) || ['', k || ''])[1];
const PLACE_NAMES = { CHAIR_LIVING: 'Armchair', CHAIR_DINING: 'Dining chair', TABLE_DINING_2X: 'Dining table' };
const nice = s => PLACE_NAMES[s] || (x => x.charAt(0).toUpperCase() + x.slice(1))(String(s || '').toLowerCase().replace(/_/g, ' '));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const nextPaint = () => new Promise(r => requestAnimationFrame(() => r()));
// file names the server accepts (letters, digits and a few signs)
export const fileSafe = s => String(s || '').normalize('NFKD').replace(/[^A-Za-z0-9 _().,+&'-]+/g, '').replace(/\s+/g, ' ').trim().slice(0, 60) || 'Animation';

// ---------------------------------------------------------------- the stage, filmed
// Run fn(stage) with the stage paused and ready to film: no gizmo, handles, trail, ghosts, origin ring or selection
// glow; the cinematic look on (grain off: it would change every pixel of every frame). Afterwards everything is put
// back: camera, frame, playing, Showcase, look, helpers, which sims show, and the render loop.
export async function withStage(app, fn, { cinematic = true } = {}) {
  if (app._stageBusy) throw new Error('The stage is busy - wait for the other picture-taking to finish.');
  if (app._recordingVideo) throw new Error('A video is being recorded - wait for it to finish.');
  app._stageBusy = true;
  const vp = app.vp, stage = vp.stage;
  if (app.preview && app.library && app.library.stopPreview) app.library.stopPreview();
  const was = {
    frame: app.store.frame, playing: app.playing, showcase: !!document.querySelector('#btn-showcase.on'),
    view: vp.savedView(), roll: vp.controls.roll || 0, cine: !!(stage && stage.isCinematic),
    overlay: vp.overlay.visible, gizmo: vp.gizmo.visible, origin: vp.origin ? vp.origin.visible : null,
    onion: app.onion, trail: app.trail, recording: document.body.classList.contains('recording'), paused: vp.paused,
    visible: new Map([...app.simViews].map(([id, v]) => [id, v.group.visible])),
  };
  let gizmoBack = () => {};
  try {
    if (was.playing) app.setPlaying(false);
    if (was.showcase) app.showcase(false);
    vp.stopCamera();
    vp.pause();
    if (was.onion) { app.onion = false; app.updateGhosts(); }
    if (was.trail) { app.trail = false; app.updateTrail(); }
    gizmoBack = holdGizmo(app);
    vp.overlay.visible = false; vp.gizmo.visible = false;
    if (vp.origin) vp.origin.visible = false;
    document.body.classList.add('recording');
    if (stage) { stage.cinematic(cinematic); if (stage.vignette) stage.vignette.uniforms.grain.value = 0; }
    try { app.pipeline.simulateIfNeeded && app.pipeline.simulateIfNeeded(); } catch (e) { console.warn('physics', e); }
    tickStage(app, 0.5);                       // the selection glow fades out at once
    return await fn({
      render: () => renderNow(app),
      pose: f => poseAt(app, f),
      only: ids => { for (const [id, v] of app.simViews) v.group.visible = (was.visible.get(id) !== false) && (!ids || ids.includes(id)); },
    });
  } finally {
    for (const [id, vis] of was.visible) { const v = app.simViews.get(id); if (v) v.group.visible = vis; }
    vp.overlay.visible = was.overlay; vp.gizmo.visible = was.gizmo;
    if (vp.origin && was.origin !== null) vp.origin.visible = was.origin;
    if (!was.recording) document.body.classList.remove('recording');
    if (stage) stage.cinematic(was.cine);
    vp.controls.lookFrom(was.view.pos, was.view.target, was.roll);
    if (was.onion) app.onion = true;
    if (was.trail) { app.trail = true; app.updateTrail(); }
    app.setFrame(was.frame);
    gizmoBack();
    if (!was.paused) vp.resume();
    if (was.showcase) app.showcase(true);
    if (was.playing) app.setPlaying(true);
    app._stageBusy = false;
  }
}

function tickStage(app, dt) {
  for (const f of [...app.vp.onFrame]) { try { f(dt); } catch (e) { console.warn(e); } }
}

// The pose at frame f (fractions too), shown.
export function poseAt(app, f) {
  app.store.frame = f;
  app.applyPoses(false);
}

// One picture of the stage, now (the loop is paused while filming).
export function renderNow(app) {
  const vp = app.vp;
  tickStage(app, 0);
  vp.camera.updateMatrixWorld(true);
  if (vp.quality === 'fast') vp.renderer.render(vp.scene, vp.camera);
  else vp.composer.render(0);
  return vp.canvas;
}

// Where bones of the shown sims are over some frames -> {center, radius, pts} (bones sit inside the skin: + margin).
export function sphereOf(app, frames, { bones = BODY, simIds = null, margin = 0.14, min = 0.3 } = {}) {
  const box = new THREE.Box3(), pts = [], v3 = new THREE.Vector3();
  for (const f of frames) {
    poseAt(app, f);
    for (const [id, v] of app.simViews) {
      if (!v.group.visible || (simIds && !simIds.includes(id))) continue;
      v.group.updateMatrixWorld(true);
      for (const n of bones) if (v.byName[n]) { v.worldPos(n, v3); box.expandByPoint(v3); pts.push(v3.clone()); }
    }
  }
  if (box.isEmpty()) return { center: new THREE.Vector3(0, 0.9, 0), radius: 1, pts };
  const center = box.getCenter(new THREE.Vector3());
  let r = 0;
  for (const p of pts) r = Math.max(r, p.distanceTo(center));
  return { center, radius: Math.max(min, r + margin), pts };
}

// The part of the stage a picture of this width / height is cut from (the middle), and how far the camera must be
// for the sphere to fill it.
function fitOf(app, radius, aspect) {
  const vp = app.vp, cw = vp.canvas.width, ch = vp.canvas.height, ca = cw / ch;
  let cropW, cropH;
  if (aspect > ca) { cropW = cw; cropH = cw / aspect; } else { cropH = ch; cropW = ch * aspect; }
  const tanV = Math.tan(THREE.MathUtils.degToRad(vp.camera.fov / 2));
  const half = Math.min(Math.atan(tanV * cropH / ch), Math.atan(tanV * cropW / ch));
  return { dist: radius / Math.sin(half), crop: { x: (cw - cropW) / 2, y: (ch - cropH) / 2, w: cropW, h: cropH } };
}
const camAt = (sphere, dir, dist) => { const pos = sphere.center.clone().add(dir.clone().normalize().multiplyScalar(dist)); if (pos.y < 0.15) pos.y = 0.15; return pos; };

// A camera that fits the sphere into a picture of the given width / height (cut from the middle of the stage).
export function fitView(app, sphere, dir, aspect) {
  const { dist, crop } = fitOf(app, sphere.radius, aspect);
  app.vp.controls.lookFrom(camAt(sphere, dir, dist), sphere.center, 0);
  app.vp.camera.updateMatrixWorld(true);
  return { crop };
}

// The picture just rendered, cut and scaled into a canvas (two steps for small pictures: smoother).
export function grab(app, crop, out) {
  const g = out.getContext('2d', { willReadFrequently: true });
  g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
  const src = app.vp.canvas;
  if (out.width * 3 < crop.w) {
    const mid = grab.mid || (grab.mid = document.createElement('canvas'));
    mid.width = out.width * 3; mid.height = out.height * 3;
    const m = mid.getContext('2d');
    m.imageSmoothingEnabled = true; m.imageSmoothingQuality = 'high';
    m.drawImage(src, crop.x, crop.y, crop.w, crop.h, 0, 0, mid.width, mid.height);
    g.drawImage(mid, 0, 0, out.width, out.height);
  } else g.drawImage(src, crop.x, crop.y, crop.w, crop.h, 0, 0, out.width, out.height);
  return g;
}

// How much of the sims a camera there sees past the furniture (0..1): rays to their bones.
const _ray = new THREE.Raycaster();
function seenFrom(app, cam, pts) {
  const furn = app.vp.furniture ? app.vp.furniture.children.filter(o => o.visible) : [];
  if (!furn.length || !pts.length) return 1;
  let seen = 0;
  const dir = new THREE.Vector3();
  for (const p of pts) {
    dir.copy(p).sub(cam);
    const far = dir.length();
    _ray.set(cam, dir.normalize()); _ray.far = Math.max(0.01, far - 0.06);
    if (!_ray.intersectObjects(furn, true).length) seen++;
  }
  return seen / pts.length;
}

// The camera angles: the one you look from now (kept 10-50 degrees up) when furniture doesn't hide the sims from
// there, then the clearest views around them that are different enough (60 degrees around or 25 up).
export function pickAngles(app, n, frames, aspect = 4 / 3) {
  const d = app.vp.viewDir().clone();
  const flat = new THREE.Vector3(d.x, 0, d.z);
  if (flat.lengthSq() < 1e-6) flat.set(0.62, 0, 0.66);
  flat.normalize();
  const deg = THREE.MathUtils.degToRad;
  const up = THREE.MathUtils.clamp(Math.asin(THREE.MathUtils.clamp(d.y, -1, 1)), deg(10), deg(50));
  const at = (turn, elev) => flat.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), deg(turn)).multiplyScalar(Math.cos(elev)).setY(Math.sin(elev));
  const name = (turn, elev) => (elev > deg(45) ? ['above', 'From above'] : Math.abs(turn) >= 160 ? ['back', 'From behind']
    : Math.abs(turn) >= 115 ? ['back-side', 'Back three-quarter'] : Math.abs(turn) >= 70 ? ['side', 'Side'] : ['angle', 'Three-quarter']);
  const cands = [{ turn: 0, elev: up, first: true }];
  for (const t of [90, -90, 45, -45, 135, -135, 180]) cands.push({ turn: t, elev: deg(20) });
  for (const t of [90, -90, 135, -135, 180]) cands.push({ turn: t, elev: deg(38) });
  for (const t of [-35, 35, 145]) cands.push({ turn: t, elev: deg(58) });
  const sphere = sphereOf(app, frames.filter((_, i) => i % Math.max(1, Math.floor(frames.length / 3)) === 0));
  const pts = sphere.pts.filter((_, i) => i % 2 === 0);
  const { dist } = fitOf(app, sphere.radius, aspect);
  for (const c of cands) { c.dir = at(c.turn, c.elev); c.seen = seenFrom(app, camAt(sphere, c.dir, dist), pts); }
  const apart = (a, b) => { const t = Math.abs(((a.turn - b.turn) % 360 + 540) % 360 - 180); return t >= 60 || Math.abs(a.elev - b.elev) >= deg(25); };
  const chosen = [];
  const spread = c => Math.min(...chosen.map(x => Math.abs(c.elev - x.elev) * 2 + Math.abs(((c.turn - x.turn) % 360 + 540) % 360 - 180) * Math.PI / 180));
  const first = cands[0].seen >= 0.8 ? cands[0] : [...cands].sort((a, b) => b.seen - a.seen || Math.abs(a.turn) - Math.abs(b.turn))[0];
  chosen.push(first);
  while (chosen.length < n) {
    const next = cands.filter(c => !chosen.includes(c) && chosen.every(x => apart(c, x)))
      .sort((a, b) => Math.round((b.seen - a.seen) * 10) || spread(b) - spread(a) || Math.abs(a.turn) - Math.abs(b.turn))[0];
    if (!next) break;
    chosen.push(next);
  }
  const used = new Set();
  return chosen.map((c, i) => {
    let [id, label] = i === 0 && c.first ? ['front', 'Your view'] : name(c.turn, c.elev);
    while (used.has(id)) id += '2';
    used.add(id);
    return { id, label, dir: c.dir, seen: c.seen };
  });
}

// The loop, sampled evenly: frame k of n at (k / n) of the loop, so the last one leads straight back into the first.
export function loopFrames(project, maxFrames = 120, fps = 20) {
  const seconds = project.length / (project.fps || 30);
  const n = Math.max(8, Math.min(maxFrames, Math.round(seconds * fps)));
  const frames = [];
  for (let k = 0; k < n; k++) frames.push((k / n) * project.length);
  return { frames, delay: Math.max(2, Math.round((seconds * 100) / n)), seconds };
}

// ---------------------------------------------------------------- the safe teaser
// Blur band: from the chest to the knees of every sim, over the whole loop (one band per angle, so it holds still).
// -> [y0, y1] in picture pixels.
function bandOf(app, frames, crop, H) {
  const v3 = new THREE.Vector3(), cam = app.vp.camera, ch = app.vp.canvas.height;
  let lo = Infinity, hi = -Infinity;
  for (const f of frames) {
    poseAt(app, f);
    for (const [, v] of app.simViews) {
      if (!v.group.visible) continue;
      v.group.updateMatrixWorld(true);
      for (const n of BAND) if (v.byName[n]) {
        v.worldPos(n, v3).project(cam);
        const y = ((1 - v3.y) / 2 * ch - crop.y) / crop.h * H;
        lo = Math.min(lo, y); hi = Math.max(hi, y);
      }
    }
  }
  if (!isFinite(lo)) return [H * 0.3, H * 0.8];
  const pad = H * 0.07;
  return [Math.max(0, lo - pad), Math.min(H, hi + pad)];
}

const scratch = k => (scratch[k] = scratch[k] || document.createElement('canvas'));
function blurBand(g, W, H, band) {
  const tmp = scratch('band');
  tmp.width = W; tmp.height = H;
  tmp.getContext('2d').drawImage(g.canvas, 0, 0);
  g.save();
  g.beginPath(); g.rect(0, band[0], W, band[1] - band[0]); g.clip();
  g.filter = `blur(${Math.max(6, Math.round(W / 30))}px)`;
  g.drawImage(tmp, 0, 0);
  g.filter = 'none';
  g.fillStyle = 'rgba(40, 24, 52, .38)';
  g.fillRect(0, band[0], W, band[1] - band[0]);
  g.restore();
}

// Shoulders up: the camera is close on the heads, and everything but the faces (a soft circle of 13 cm around each,
// between the eyes and the jaw) is blurred - so a leaning or lying body never shows, whatever the pose.
function headCircles(app, crop, W, H) {
  const cam = app.vp.camera, cw = app.vp.canvas.width, ch = app.vp.canvas.height, out = [];
  cam.updateMatrixWorld(true);
  const right = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 0).normalize();
  const px = q => [((q.x + 1) / 2 * cw - crop.x) / crop.w * W, ((1 - q.y) / 2 * ch - crop.y) / crop.h * H];
  for (const [, v] of app.simViews) {
    if (!v.group.visible || !v.byName.b__Head__) continue;
    v.group.updateMatrixWorld(true);
    const p = v.worldPos('b__Head__', new THREE.Vector3());
    if (v.byName.b__L_Eye__ && v.byName.b__R_Eye__ && v.byName.b__Jaw__) {
      const eyes = v.worldPos('b__L_Eye__', new THREE.Vector3()).add(v.worldPos('b__R_Eye__', new THREE.Vector3())).multiplyScalar(0.5);
      p.copy(eyes.multiplyScalar(0.65).add(v.worldPos('b__Jaw__', new THREE.Vector3()).multiplyScalar(0.35)));
    }
    const [x, y] = px(p.clone().project(cam)), [x2, y2] = px(p.clone().add(right.clone().multiplyScalar(0.13)).project(cam));
    out.push({ x, y, r: Math.max(4, Math.hypot(x2 - x, y2 - y)) });
  }
  return out;
}
function softFaces(g, W, H, circles) {
  const sharp = scratch('sharp'), mask = scratch('mask');
  for (const c of [sharp, mask]) { c.width = W; c.height = H; }
  const sg = sharp.getContext('2d'), mg = mask.getContext('2d');
  sg.drawImage(g.canvas, 0, 0);
  mg.clearRect(0, 0, W, H);
  for (const c of circles) {
    const gr = mg.createRadialGradient(c.x, c.y, c.r * 0.72, c.x, c.y, c.r);
    gr.addColorStop(0, 'rgba(0,0,0,1)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
    mg.fillStyle = gr; mg.beginPath(); mg.arc(c.x, c.y, c.r, 0, Math.PI * 2); mg.fill();
  }
  sg.globalCompositeOperation = 'destination-in';
  sg.drawImage(mask, 0, 0);
  sg.globalCompositeOperation = 'source-over';
  const tmp = scratch('whole');
  tmp.width = W; tmp.height = H;
  tmp.getContext('2d').drawImage(g.canvas, 0, 0);
  g.save();
  g.filter = `blur(${Math.max(8, Math.round(W / 22))}px)`;
  g.drawImage(tmp, 0, 0);
  g.filter = 'none';
  g.fillStyle = 'rgba(40, 24, 52, .3)';
  g.fillRect(0, 0, W, H);
  g.drawImage(sharp, 0, 0);
  g.restore();
}

// How one angle is filmed: where the camera is, the part of the stage cut out, and the safe teaser's cover.
function planCut(app, frames, dir, W, H, teaser) {
  const few = frames.filter((_, i) => i % 6 === 0);
  const sphere = teaser === 'shoulders' ? sphereOf(app, few, { bones: HEADS, margin: 0.22, min: 0.34 }) : sphereOf(app, few);
  const { crop } = fitView(app, sphere, dir, W / H);
  const band = teaser === 'blur' ? bandOf(app, frames.filter((_, i) => i % 3 === 0), crop, H) : null;
  return { crop, band, teaser, W, H, view: { pos: app.vp.camera.position.clone(), target: sphere.center.clone() } };
}
// The picture of one frame (after the stage was rendered), with the teaser's cover.
function paint(app, cut, g) {
  grab(app, cut.crop, g.canvas);
  if (cut.band) blurBand(g, cut.W, cut.H, cut.band);
  if (cut.teaser === 'shoulders') softFaces(g, cut.W, cut.H, headCircles(app, cut.crop, cut.W, cut.H));
  return g;
}

// ---------------------------------------------------------------- GIFs and the thumbnail
// Film one angle and pack it into a GIF under maxBytes. -> {bytes: Uint8Array, frames, delay, width, height}
export async function filmGif(app, st, { dir, width = 480, height = 360, teaser = 'none', frames, delay, maxBytes = MAX_GIF, onProgress } = {}) {
  const cut = planCut(app, frames, dir, width, height, teaser);
  const out = document.createElement('canvas'); out.width = width; out.height = height;
  const g = out.getContext('2d', { willReadFrequently: true });
  const shots = [];
  for (let k = 0; k < frames.length; k++) {
    st.pose(frames[k]);
    st.render();
    paint(app, cut, g);
    shots.push(g.getImageData(0, 0, width, height));
    if (onProgress && k % 4 === 0) { onProgress(k / frames.length); await nextPaint(); }
  }
  // pack; when it comes out too big, every second frame (still an even loop), then without the dither
  const tries = [{ step: 1, dither: 6 }, { step: 2, dither: 6 }, { step: 2, dither: 0 }, { step: 3, dither: 0 }];
  let best = null;
  for (const t of tries) {
    if (t.step > 1 && shots.length % t.step) continue;
    const gm = new GifMaker(width, height, { dither: t.dither });
    const use = shots.filter((_, i) => i % t.step === 0);
    const every = Math.max(1, Math.floor(use.length / 24));
    for (let i = 0; i < use.length; i += every) gm.sample(use[i]);
    for (const s of use) gm.add(s, delay * t.step);
    const bytes = gm.finish();
    best = { bytes, frames: use.length, delay: delay * t.step, width, height };
    if (bytes.length <= maxBytes) break;
    await sleep(0);
  }
  return best;
}

// A square picture of the scene (PNG), from the first angle, a third of the way into the loop.
export async function filmThumb(app, st, { dir, size = 512, teaser = 'none', frame = 0 } = {}) {
  const cut = planCut(app, [frame], dir, size, size, teaser);
  const out = document.createElement('canvas'); out.width = size; out.height = size;
  st.pose(frame);
  st.render();
  paint(app, cut, out.getContext('2d', { willReadFrequently: true }));
  return new Promise(r => out.toBlob(b => r(b), 'image/png'));
}

// ---------------------------------------------------------------- post text (the server adds the sound credits)
export function postText(project, baked) {
  const p = project, b = baked || {};
  const acts = [kindName(p.category)].filter(Boolean);
  for (const t of p.tags || []) if (t !== 'CUSTOM_VOICE_SFX' && !acts.includes(tagLabel(t))) acts.push(tagLabel(t));
  const places = (p.locations || []).map(nice);
  const g = (b.actors || p.sims || []).map(s => String(s.gender || 'BOTH').toLowerCase().replace('both', 'any'));
  return [`"${p.name}"${p.author ? ' by ' + p.author : ''} - a new WickedWhims animation`, '',
    'Acts: ' + (acts.join(', ') || 'Teasing'), 'Places: ' + (places.join(', ') || 'Floor'),
    `Sims: ${g.length}${g.length ? ' (' + g.join(', ') + ')' : ''}`, 'Needs: WickedWhims by TURBODRIVER', '',
    'Credits:', '  Animation by ' + (p.author || 'me'), "  Made with Novulon's Wicked Animator", '',
    '18+ only. #TheSims4 #WickedWhims #Sims4Animations #TS4Mods', ''].join('\n');
}

const toB64 = blob => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result)); r.onerror = () => rej(r.error); r.readAsDataURL(blob); });

// ---------------------------------------------------------------- the kit
// Makes everything (no dialogs) -> {files: [{name, blob, kind}], gifs: [{name, bytes, frames, delay, url}], thumb, video, text}
export async function makeKit(app, { angles = 3, width = 480, teaser = 'none', video = true, videoSeconds = 10, onStep } = {}) {
  const p = app.store.project;
  if (!p.sims.length) throw new Error('Add a sim first - the promo kit films your animation.');
  const height = Math.round(width * 3 / 4 / 2) * 2;
  const base = fileSafe(p.name);
  const { frames, delay } = loopFrames(p);
  let dirs = [];
  const step = (text, k) => onStep && onStep(text, k);
  const gifs = [];
  let thumb = null, teaserCut = null;
  await withStage(app, async st => {
    dirs = pickAngles(app, Math.max(1, Math.min(3, angles)), frames, width / height);
    for (const [i, a] of dirs.entries()) {
      step(`Filming ${a.label.toLowerCase()} (${i + 1} of ${dirs.length})`, i / (dirs.length + 1));
      const r = await filmGif(app, st, { dir: a.dir, width, height, teaser, frames, delay,
        onProgress: k => step(`Filming ${a.label.toLowerCase()} (${i + 1} of ${dirs.length})`, (i + k) / (dirs.length + 1)) });
      const name = `${base} - ${a.id}.gif`;
      gifs.push({ name, angle: a.label, ...r, blob: new Blob([r.bytes], { type: 'image/gif' }) });
      await nextPaint();
    }
    step('The thumbnail', dirs.length / (dirs.length + 1));
    thumb = { name: `${base} - thumbnail.png`, blob: await filmThumb(app, st, { dir: dirs[0].dir, teaser, frame: Math.round(p.length / 3) }) };
    // the safe teaser's video: the same cut from the first angle (and the same band), 16:9
    if (video && teaser !== 'none') teaserCut = planCut(app, frames, dirs[0].dir, 960, 540, teaser);
  });
  let vid = null;
  if (video) {
    step(`Recording a ${videoSeconds}-second video with sound`, 0.92);
    const opts = { seconds: videoSeconds, showcase: teaser === 'none', badge: true };
    if (teaserCut) {
      opts.view = teaserCut.view;
      opts.composite = { width: teaserCut.W, height: teaserCut.H, draw: g => paint(app, teaserCut, g) };
    }
    const got = await captureVideo(app, opts);
    if (got) vid = { name: `${base} - preview.webm`, blob: got.blob, seconds: got.seconds };
  }
  return { gifs, thumb, video: vid, text: postText(p, null) };
}

// Save the kit through /api/promo_save (one folder next to the exports) -> the server's answer.
export async function saveKit(app, kit) {
  const p = app.store.project;
  const files = [...kit.gifs.map(g => ({ name: g.name, blob: g.blob })), kit.thumb, kit.video].filter(Boolean);
  const body = { name: p.name, author: p.author || '', files: [], baked: null };
  for (const f of files) body.files.push({ name: f.name, data: await toB64(f.blob) });
  try { body.baked = app.bake(); } catch (e) { console.warn('promo: no bake for the credits', e); }
  const r = await fetch('/api/promo_save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const res = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(res.error || r.statusText);
  return res;
}

// ---------------------------------------------------------------- the dialog
export function openPromoKit(app) {
  const p = app.store.project;
  if (!p.sims.length) return toast('Add a sim first - the promo kit films your animation.', 'err');
  if (app._stageBusy || app._recordingVideo) return toast('Wait a moment - the stage is busy.', 'err');
  const opt = { angles: 3, width: 480, teaser: 'none', video: true };
  const seg = (items, get, set) => {
    const box = h('div', { class: 'seg-inline pk-seg' });
    const draw = () => { box.innerHTML = ''; for (const [v, label] of items) box.append(h('button', { type: 'button', class: get() === v ? 'on' : '', onclick: () => { set(v); draw(); } }, label)); };
    draw();
    return box;
  };
  const { frames, seconds } = loopFrames(p);
  const status = h('div', { class: 'pk-status' }, h('div', { class: 'pk-bar' }, h('i')), h('span', {}, ''));
  const body = h('div', { class: 'pk-grid' },
    h('div', { class: 'pk-what' },
      h('div', { class: 'pk-item' }, icon('pk-gif'), h('div', {}, h('b', {}, 'Looping GIFs'), h('span', {}, `${seconds.toFixed(1)} s loop, ${frames.length} frames, under 5 MB each - they loop without a jump`))),
      h('div', { class: 'pk-item' }, icon('pk-thumb'), h('div', {}, h('b', {}, 'A square thumbnail'), h('span', {}, '512 x 512, for the download page'))),
      h('div', { class: 'pk-item' }, icon('rec'), h('div', {}, h('b', {}, 'A 10-second video with sound'), h('span', {}, 'Filmed from the stage while it plays'))),
      h('div', { class: 'pk-item' }, icon('pk-text'), h('div', {}, h('b', {}, 'The text to post'), h('span', {}, 'Name, acts, places, sims, needed mods and credits')))),
    h('div', { class: 'pk-opts' },
      h('label', { class: 'field' }, h('span', {}, 'Camera angles'), seg([[2, '2 angles'], [3, '3 angles']], () => opt.angles, v => { opt.angles = v; })),
      h('label', { class: 'field' }, h('span', {}, 'GIF width'), seg([[400, '400 px'], [480, '480 px'], [540, '540 px']], () => opt.width, v => { opt.width = v; })),
      h('label', { class: 'field' }, h('span', {}, 'Safe teaser (for sites that ban explicit pictures)'), seg(TEASERS, () => opt.teaser, v => { opt.teaser = v; })),
      h('div', { class: 'toggle-row' }, h('div', {}, h('b', {}, 'Record the 10-second video'), h('span', {}, 'Takes 10 seconds - the stage plays while it films')),
        (() => { const t = h('label', { class: 'switch' }, h('input', { type: 'checkbox', checked: true, onchange: e => { opt.video = e.target.checked; } }), h('span')); return t; })()),
      status));
  let busy = false;
  const dlg = modal({
    title: 'Make a promo kit', text: 'Everything to post your animation, made from the stage and saved in one folder next to your exports.', body, wide: true,
    buttons: [{ label: 'Cancel', kind: 'ghost', onClick: () => !busy }, { label: 'Make promo kit', kind: 'primary', onClick: async () => {
      if (busy) return false;
      busy = true;
      const btn = dlg.footer.lastChild;
      btn.disabled = true;
      dlg.dialog.classList.add('pk-busy');
      const bar = status.querySelector('i'), txt = status.querySelector('span');
      const onStep = (text, k) => { status.classList.add('on'); txt.textContent = text + '...'; bar.style.transform = `scaleX(${Math.max(0.02, Math.min(1, k))})`; };
      try {
        const kit = await makeKit(app, { ...opt, onStep });
        onStep('Saving', 0.97);
        let res = null;
        try { res = await saveKit(app, kit); } catch (e) { toast('Could not save the promo kit: ' + e.message, 'err'); busy = false; btn.disabled = false; dlg.dialog.classList.remove('pk-busy'); return false; }
        busy = false;
        showKit(app, kit, res);
      } catch (e) {
        console.error('promo kit', e);
        toast('Could not make the promo kit: ' + e.message, 'err');
        busy = false; btn.disabled = false; dlg.dialog.classList.remove('pk-busy'); status.classList.remove('on');
        return false;
      }
    } }],
  });
  return dlg;
}

function showKit(app, kit, res) {
  const r = res || {};
  const text = r.post_text || kit.text;
  const mb = n => (n / 1048576).toFixed(1) + ' MB';
  const area = h('textarea', { class: 'pk-text', readonly: true, rows: 9 }, text);
  const hero = successHero();
  const shelf = h('div', { class: 'pk-shelf' },
    ...kit.gifs.map((g, i) => h('figure', { style: { '--i': i } }, h('img', { src: URL.createObjectURL(g.blob), alt: g.angle }), h('figcaption', {}, `${g.angle} · ${mb(g.bytes.length)}`))),
    kit.thumb ? h('figure', { class: 'sq', style: { '--i': kit.gifs.length } }, h('img', { src: URL.createObjectURL(kit.thumb.blob), alt: 'Thumbnail' }), h('figcaption', {}, 'Thumbnail')) : null);
  modal({
    title: 'Your promo kit is ready', wide: true,
    body: h('div', { class: 'pk-done' }, hero,
      h('h3', { class: 'hero-title' }, `${kit.gifs.length} GIF${kit.gifs.length > 1 ? 's' : ''}, a thumbnail${kit.video ? ', a video' : ''} and your post text`),
      shelf,
      r.folder ? h('div', { class: 'success' }, icon('check'), h('div', {}, h('b', {}, 'Saved in one folder'), h('div', { class: 'path' }, r.folder))) : null,
      h('div', { class: 'section-title', style: { margin: '14px 0 6px' } }, 'Text to post',
        h('button', { class: 'btn small soft', type: 'button', onclick: async e => {
          try { await navigator.clipboard.writeText(area.value); } catch { area.select(); document.execCommand && document.execCommand('copy'); }
          e.currentTarget.textContent = 'Copied'; } }, icon('copy'), 'Copy')),
      area),
    buttons: [{ label: 'Open the folder', onClick: () => { if (r.folder) api.reveal(r.folder); return false; } }, { label: 'Done', kind: 'primary' }],
  });
  setTimeout(() => { area.blur(); const done = [...document.querySelectorAll('#modal-root .modal:last-child footer .btn')].pop(); if (done) done.focus({ preventScroll: true }); }, 60);
  celebrateAt(hero, { delay: 480 });
  emitWA(app, 'exported', { result: r, kind: 'promo' });
}
