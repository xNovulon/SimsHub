// The face map (spec_face_bones section 4, "Phase B"): a flat front view of the face with the same coloured dots as
// the Face tool, always upright - it helps when the head lies at an odd angle in the 3D view.
//   - a dot sits where that face part is now (its skin spot, in the head's own frame: x up, z the sim's left, so the
//     sim's left shows on the viewer's right, like looking at them);
//   - drag a dot to move that part in the face plane (1.2 px = 1 mm); lids and the jaw close/open with an up/down
//     drag (1 px = 0.5 degrees); an eye drags like a look pad (both eyes look together); the tongue comes out when
//     dragged down;
//   - Symmetry (X) and Alt (past the safe range) work as in 3D; the dot flashes amber at the safe range;
//   - double-click a dot: that part goes back to rest (both sides with Symmetry).
// Everything goes through the app's own face editing (the keyed face, never the automatic layer), so it is keyed
// and undone exactly like the 3D Face tool.
import * as THREE from 'three';
import { h } from './ui.js';
import * as K from './facekit.js';
import { $t } from './i18n.js';

export const W = 260, H = 300;
export const PX_PER_MM = 1.2;              // a move drag: 1.2 px = 1 mm
export const DEG_PER_PX = 0.5;             // a turn drag: 1 px = 0.5 degrees
const NS = 'http://www.w3.org/2000/svg';
const s = (tag, attrs = {}) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v); return e; };
const deg = THREE.MathUtils.degToRad;
const EYE = /_Eye__$/, TONGUE1 = 'b__Tounge__1';
const BROWS = [['b__L_OutBrow__', 'b__L_MidBrow__', 'b__L_InBrow__'], ['b__R_OutBrow__', 'b__R_MidBrow__', 'b__R_InBrow__']];
const LIP_LOOP = ['b__L_Mouth__', 'b__L_UpLip__', 'b__UpLip__', 'b__R_UpLip__', 'b__R_Mouth__', 'b__R_LoLip__', 'b__LoLip__', 'b__L_LoLip__'];
const _v = new THREE.Vector3(), _q = new THREE.Quaternion();

// ---------------------------------------------------------------- geometry
// A point given in a face bone's own frame, in the head's frame (walking up the bones; `rest`: the rig's rest).
function inHead(v, name, point, rest = false) {
  const out = point.clone();
  let b = v.bone(name);
  while (b && b.name !== 'b__Head__') {
    const r = rest ? v.restByName[b.name] : null;
    out.multiply(b.scale).applyQuaternion(rest ? r.quat : b.quaternion).add(rest ? r.pos : b.position);
    b = b.parent;
  }
  return b ? out : null;
}
// The turn of a bone's parent in the head's frame (to turn a face-plane drag into the parent's axes).
function parentInHead(v, name) {
  const q = new THREE.Quaternion();
  let b = v.bone(name) && v.bone(name).parent;
  while (b && b.name !== 'b__Head__') { q.premultiply(b.quaternion); b = b.parent; }
  return q;
}
// Where a part's dot sits, in its bone's own frame: exactly where the 3D Face tool puts it (Sim.faceHandlePoint -
// for the lids, the measured lid edge in front of the eye), so the map and the 3D dots always agree. Only a Sim
// without a lid-edge point (an older sim.js) gets the fixed edge below (13 mm forward, 4.5 mm above / 4 mm below
// the pupil): the lid's weight centre lies behind its pivot and would move up while the lid closes.
const LID_EDGE = { UpLid: new THREE.Vector3(0.0045, 0.013, 0), LoLid: new THREE.Vector3(-0.004, 0.013, 0) };
const handle = (v, n) => {
  const lid = /_(UpLid|LoLid)__$/.exec(n);
  if (lid && typeof v._lidEdge !== 'function') return LID_EDGE[lid[1]];
  return (typeof v.faceHandlePoint === 'function' ? v.faceHandlePoint(n) : K.faceHandlePoint(v, n)) || new THREE.Vector3();
};

// Where each dot goes at rest, and the framing (cached per body: a sim keeps its body).
function layoutOf(v) {
  if (v._fm2d) return v._fm2d;
  const pts = {};
  for (const n of K.FACE_CHANNEL) {
    if (!v.bone(n)) continue;
    const p = inHead(v, n, handle(v, n), true);
    if (p) pts[n] = p;
  }
  const xs = Object.entries(pts).filter(([n]) => !/Tounge/.test(n)).map(([, p]) => p.x);
  const top = Math.max(...xs), bottom = Math.min(...xs);
  // the oval: a forehead above the brows, a little room under the chin; the whole face centred in the card
  const foreheadMm = 40, chinMm = 12;
  const ovalTop = top * 1000 + foreheadMm, ovalBottom = bottom * 1000 - chinMm;
  const mid = (ovalTop + ovalBottom) / 2;
  const cheek = Math.max(...['b__L_Cheek__', 'b__R_Cheek__', 'b__L_OutBrow__', 'b__R_OutBrow__'].filter(n => pts[n]).map(n => Math.abs(pts[n].z))) * 1000;
  return (v._fm2d = { pts, mid, top: ovalTop, bottom: ovalBottom, halfW: cheek + 17, chinW: 17 });
}
// head frame (metres) -> map (px)
const mapX = z => W / 2 + z * 1000 * PX_PER_MM;
const mapY = (x, L) => H / 2 - (x * 1000 - L.mid) * PX_PER_MM;

// The dots' map positions now.
function positions(v) {
  const L = layoutOf(v), out = {};
  for (const n of Object.keys(L.pts)) {
    const p = inHead(v, n, handle(v, n));
    if (p) out[n] = [mapX(p.z), mapY(p.x, L)];
  }
  return out;
}

// A smooth open curve through points (Catmull-Rom as cubic Beziers), for the lips; `move` starts a new path.
function smooth(pts, move = true) {
  const f = p => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`;
  let d = move ? `M${f(pts[0])}` : ` L${f(pts[0])}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
    d += ` C${f([p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6])} ${f([p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6])} ${f(p2)}`;
  }
  return d;
}

// the soft face outline: an egg, widest at the cheekbones, narrowing to a rounded chin
function outlinePath(L) {
  const top = mapY(L.top / 1000, L), bottom = mapY(L.bottom / 1000, L), cx = W / 2;
  const hw = L.halfW * PX_PER_MM, cw = L.chinW * PX_PER_MM;
  const pts = [];
  for (let i = 0; i <= 40; i++) {
    const u = i / 40;                                     // 0 = top, 1 = chin
    const y = top + (bottom - top) * u;
    const upper = Math.sqrt(Math.max(0, 1 - ((0.42 - u) / 0.42) ** 2));
    const lower = cw / hw + (1 - cw / hw) * Math.sqrt(Math.max(0, 1 - ((u - 0.42) / 0.58) ** 2.2));
    const w = hw * (u < 0.42 ? upper : lower);
    pts.push([w, y]);
  }
  const right = pts.map(([w, y]) => `${(cx + w).toFixed(1)},${y.toFixed(1)}`);
  const left = pts.slice().reverse().map(([w, y]) => `${(cx - w).toFixed(1)},${y.toFixed(1)}`);
  return `M${right.join(' L')} L${left.join(' L')} Z`;
}

// ---------------------------------------------------------------- the live map
let live = null;                      // the map on screen: {app, simId, svg, dots, ...}
let drag = null;                      // the drag going on (kept here: a redraw of the panel never breaks it)
let lastDown = { name: null, t: 0 };  // for double-clicks across redraws

const plain = (sim, n) => K.label(n, sim && sim.frame);
function kindOf(n) {
  if (EYE.test(n)) return 'look';
  if (n === TONGUE1) return 'tongue';
  const lim = K.faceLimits(n);
  return lim && lim.mode === 'turn' ? 'turn' : 'move';
}
const HOW = { move: $t('facemap2d.drag_to_move_it'), turn: $t('facemap2d.drag_up_or_down'), look: $t('facemap2d.drag_to_look_around_both'), tongue: $t('facemap2d.drag_down_to_stick_it') };

// The face map card for this sim (null when the sim has no face bones).
export function faceMap(app, sim, view) {
  if (!sim || !view || !view.bone('b__Head__')) return null;
  const L = layoutOf(view);
  const svg = s('svg', { class: 'fm-svg', width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': $t('facemap2d.face_map_drag_dot_to') });
  const defs = s('defs');
  const grad = s('radialGradient', { id: 'fm-skin', cx: '50%', cy: '42%', r: '62%' });
  grad.append(s('stop', { offset: '0%', 'stop-color': 'var(--fm-skin-1, #3a2c3c)' }), s('stop', { offset: '100%', 'stop-color': 'var(--fm-skin-2, #1f1926)' }));
  defs.append(grad);
  svg.append(defs);
  // neck, ears and the face
  const cx = W / 2, bottom = mapY(L.bottom / 1000, L), hw = L.halfW * PX_PER_MM;
  const eyeY = ['b__L_Eye__', 'b__R_Eye__'].map(n => L.pts[n]).filter(Boolean).map(p => mapY(p.x, L));
  const ey = eyeY.length ? eyeY[0] : H / 2 - 20;
  svg.append(s('path', { class: 'fm-neck', d: `M${cx - L.chinW * 1.9} ${bottom - 26} L${cx - L.chinW * 2.2} ${H + 2} M${cx + L.chinW * 1.9} ${bottom - 26} L${cx + L.chinW * 2.2} ${H + 2}` }));
  for (const sx of [-1, 1]) svg.append(s('ellipse', { class: 'fm-ear', cx: cx + sx * (hw + 1), cy: ey + 14, rx: 7, ry: 17 }));
  svg.append(s('path', { class: 'fm-face', d: outlinePath(L), fill: 'url(#fm-skin)' }));
  // the nose: a soft line from between the eyes down to the nostrils
  const nl = L.pts.b__CAS_L_Nostril__, nr = L.pts.b__CAS_R_Nostril__;
  if (nl && nr) {
    const ny = mapY((nl.x + nr.x) / 2, L), nxL = mapX(nl.z), nxR = mapX(nr.z);
    svg.append(s('path', { class: 'fm-nose', d: `M${cx - 3} ${ey + 6} C${cx - 5} ${ey + 22}, ${nxR - 3} ${ny - 12}, ${nxR - 1} ${ny - 2} M${nxR + 2} ${ny + 3} Q${cx} ${ny + 8} ${nxL - 2} ${ny + 3}` }));
  }
  // live parts: eyes (almond + iris), the open mouth, brow strokes, lip lines
  const eyes = {};
  for (const side of ['L', 'R']) {
    const clip = s('clipPath', { id: `fm-eye-${side}` });
    const almond = s('path', { class: 'fm-almond' });
    clip.append(s('path'));
    defs.append(clip);
    const iris = s('circle', { class: 'fm-iris', r: 6.2, 'clip-path': `url(#fm-eye-${side})` });
    svg.append(almond, iris);
    eyes[side] = { almond, clipPath: clip.firstChild, iris };
  }
  const mouth = s('path', { class: 'fm-mouth' });
  const lines = s('g', { class: 'fm-lines' });
  const brow = {}, lip = s('path', { class: 'fm-line', stroke: K.regionColor('mouth') });
  svg.append(lip, mouth, lines);
  for (const [i, trio] of BROWS.entries()) { brow[i] = s('path', { class: 'fm-brow', stroke: K.regionColor('brows') }); lines.append(brow[i]); }
  // the dots (tongue first: it sits behind the lips)
  const dots = {};
  // (the tongue shows one dot, drawn last: it sits just under the lips; its other two parts are posed in 3D)
  const order = Object.keys(L.pts).filter(n => !/^b__Tounge__[23]$/.test(n)).sort((a, b) => (/Tounge/.test(a) ? 1 : 0) - (/Tounge/.test(b) ? 1 : 0));
  const dotLayer = s('g', { class: 'fm-dots' });
  for (const n of order) {
    const region = K.faceRegion(n), color = K.regionColor(region);
    const g = s('g', { class: 'fm-dot' + (/Tounge/.test(n) ? ' tongue' : '') + (EYE.test(n) ? ' eye' : ''), 'data-bone': n, style: `--c:${color}`, tabindex: '-1' });
    const title = s('title'); title.textContent = `${plain(sim, n)} - ${HOW[kindOf(n)]}`;
    g.append(title, s('circle', { class: 'halo', r: 8 }), s('circle', { class: 'hit', r: 8 }), s('circle', { class: 'core', r: /Tounge/.test(n) ? 3.2 : 3.7 }));
    dotLayer.append(g);
    dots[n] = g;
  }
  svg.append(dotLayer);
  const caption = h('div', { class: 'fm-caption' }, $t('facemap2d.drag_dot_up_down_closes'));
  const wrap = h('div', { class: 'face-map', 'data-sim': sim.id }, svg, caption);
  live = { app, simId: sim.id, wrap, svg, dots, eyes, mouth, brow, lip, caption, sig: '' };
  wire(live);
  update(true);
  return wrap;
}

// Put the dots and live lines where the face is now. Cheap; skipped when nothing moved.
function update(force = false) {
  const m = live;
  if (!m || !m.svg.isConnected) return;
  const app = m.app, v = app.simViews.get(m.simId);
  if (!v) return;
  const P = positions(v);
  const sel = app.store.selected, selBone = sel && sel.sim === m.simId ? sel.bone : null;
  const sig = Object.values(P).map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(';') + '|' + selBone;
  if (!force && sig === m.sig) return;
  m.sig = sig;
  // where each dot is drawn: its spot (the lids on their measured edge, exactly as in 3D), except the tongue's dot,
  // which sits under the lips and goes down as the tongue comes out (it follows the pointer)
  const shown = n => {
    const p = P[n];
    if (!p) return null;
    if (n === TONGUE1) {
      const now = inHead(v, n, _v.set(0, 0, 0)), rest = inHead(v, n, _v.set(0, 0, 0), true);
      return [p[0], p[1] + 11 + (now && rest ? Math.max(0, now.y - rest.y) * 1000 * PX_PER_MM : 0)];
    }
    return p;
  };
  for (const [n, g] of Object.entries(m.dots)) {
    const p = shown(n);
    if (!p) continue;
    g.setAttribute('transform', `translate(${p[0].toFixed(2)} ${p[1].toFixed(2)})`);
    g.classList.toggle('sel', n === selBone);
  }
  const pt = n => P[n] || null;
  // brows
  BROWS.forEach((trio, i) => {
    const ps = trio.map(pt);
    m.brow[i].setAttribute('d', ps.every(Boolean) ? `M${ps[0][0]} ${ps[0][1]} Q${ps[1][0]} ${ps[1][1] - 2} ${ps[2][0]} ${ps[2][1]}` : '');
  });
  // the lips: a smooth upper and lower curve meeting at the pointed corners; the mouth's opening shows between them
  // as far as the lips are further apart than at rest (the jaw drops, an O mouth)
  const loop = LIP_LOOP.map(pt);
  if (loop.every(Boolean)) {
    const up = [0, 1, 2, 3, 4].map(i => loop[i]), lo = [4, 5, 6, 7, 0].map(i => loop[i]);
    m.lip.setAttribute('d', smooth(up) + smooth(lo, false).replace(/^ L[^C]*/, '') + ' Z');
    const L = layoutOf(v), ru = L.pts.b__UpLip__, rl = L.pts.b__LoLip__;
    const restGap = ru && rl ? (ru.x - rl.x) * 1000 * PX_PER_MM : 0;
    const gap = Math.max(0, (loop[6][1] - loop[2][1]) - restGap);
    if (gap > 0.6) {
      const a = loop[0], b = loop[4], mx = (loop[2][0] + loop[6][0]) / 2, my = (loop[2][1] + loop[6][1]) / 2;
      const inset = 0.18;                                   // the opening starts a little inside the corners
      const a2 = [a[0] + (mx - a[0]) * inset, a[1] + (my - a[1]) * inset], b2 = [b[0] + (mx - b[0]) * inset, b[1] + (my - b[1]) * inset];
      const top = [mx, my - gap / 2], bot = [mx, my + gap / 2];
      const cu = [2 * top[0] - (a2[0] + b2[0]) / 2, 2 * top[1] - (a2[1] + b2[1]) / 2], cl = [2 * bot[0] - (a2[0] + b2[0]) / 2, 2 * bot[1] - (a2[1] + b2[1]) / 2];
      m.mouth.setAttribute('d', `M${a2[0].toFixed(1)} ${a2[1].toFixed(1)} Q${cu[0].toFixed(1)} ${cu[1].toFixed(1)} ${b2[0].toFixed(1)} ${b2[1].toFixed(1)} Q${cl[0].toFixed(1)} ${cl[1].toFixed(1)} ${a2[0].toFixed(1)} ${a2[1].toFixed(1)} Z`);
    } else m.mouth.setAttribute('d', '');
  }
  // eyes: an almond centred on the eye whose upper and lower curves pass through the lid dots (a lid's edge dot sits
  // a little toward the nose, so each curve's top is lifted to meet it there), the iris where the eye looks
  for (const side of ['L', 'R']) {
    const e = pt(`b__${side}_Eye__`), u = pt(`b__${side}_UpLid__`), l = pt(`b__${side}_LoLid__`), el = m.eyes[side];
    if (!e || !u || !l) continue;
    const L = layoutOf(v), rest = L.pts[`b__${side}_Eye__`];
    const cxE = mapX(rest.z), cyE = mapY(rest.x, L), half = 13 * PX_PER_MM;
    const a = [cxE - half, cyE + 1], b = [cxE + half, cyE + 1];
    // a symmetric curve from a to b with its top at (cxE, top): y(x) = a.y + (top - a.y) * (1 - ((x - cxE) / half)^2)
    const topThrough = p => a[1] + (p[1] - a[1]) / Math.max(0.5, 1 - ((p[0] - cxE) / half) ** 2);
    const cu = [cxE, 2 * (topThrough(u) - 1) - a[1]];
    const cl = [cxE, 2 * (topThrough(l) + 1) - a[1]];
    const d = `M${a[0].toFixed(1)} ${a[1].toFixed(1)} Q${cu[0].toFixed(1)} ${cu[1].toFixed(1)} ${b[0].toFixed(1)} ${b[1].toFixed(1)} Q${cl[0].toFixed(1)} ${cl[1].toFixed(1)} ${a[0].toFixed(1)} ${a[1].toFixed(1)} Z`;
    el.almond.setAttribute('d', d);
    el.clipPath.setAttribute('d', d);
    el.iris.setAttribute('cx', e[0].toFixed(2));
    el.iris.setAttribute('cy', e[1].toFixed(2));
  }
}

// Called by the app after every frame it shows (hooks.afterApply): at most ~20 times a second, only while a map is on
// screen, and nothing is written to the page when nothing moved.
let lastT = 0;
export function updateFaceMaps(app, { force = false } = {}) {
  if (!live || live.app !== app || !live.svg.isConnected) return;
  const now = performance.now();
  if (!force && !drag && now - lastT < 50) return;
  lastT = now;
  update(force);
}

// ---------------------------------------------------------------- dragging
function wire(m) {
  const { svg } = m;
  svg.addEventListener('pointerdown', e => {
    const g = e.target.closest && e.target.closest('.fm-dot');
    if (!g || e.button !== 0) return;
    e.preventDefault();
    const app = m.app, simId = m.simId, n = g.dataset.bone;
    const v = app.simViews.get(simId);
    if (!v || !v.bone(n)) return;
    const now = performance.now();
    const dbl = lastDown.name === n && lastDown.sim === simId && now - lastDown.t < 380;
    lastDown = { name: n, sim: simId, t: now };
    if (dbl) { lastDown.t = 0; resetPart(app, simId, n); return; }
    startDrag(app, simId, n, e);
  });
  svg.addEventListener('pointerover', e => {
    const g = e.target.closest && e.target.closest('.fm-dot');
    if (!g || drag) return;
    hoverPart(m, g.dataset.bone);
  });
  svg.addEventListener('pointerout', e => {
    const g = e.target.closest && e.target.closest('.fm-dot');
    if (!g || drag) return;
    if (e.relatedTarget && g.contains(e.relatedTarget)) return;
    hoverPart(m, null);
  });
}

function hoverPart(m, n) {
  const app = m.app, v = app.simViews.get(m.simId), sim = app.store.sim(m.simId);
  if (v) {
    if (n) { const k = v.index(n); if (k >= 0) { v._listHover = true; K.setPickMode(v, 'face'); v.hover(k); } }
    else { v._listHover = false; v.hover(-1); }
  }
  if (m.caption && m.caption.isConnected) m.caption.textContent = n ? $t('facemap2d.double_click_puts_it_back', { plain: plain(sim, n), v: HOW[kindOf(n)] }) : $t('facemap2d.drag_dot_up_down_closes');
}

function startDrag(app, simId, n, e) {
  const v = app.simViews.get(simId);
  const kind = kindOf(n);
  drag = { app, simId, name: n, kind, x0: e.clientX, y0: e.clientY, moved: false, pointerId: e.pointerId };
  // the dot is selected at once (the 3D gizmo follows in the Face tool); the panels are redrawn when it ends
  app.store.selected = { sim: simId, bone: n };
  if (app.interact && app.interact.tool === 'face' && typeof app.interact.selectFaceBone === 'function') {
    try { app.interact.selectFaceBone(simId, n); } catch (err) { console.error(err); }
  }
  for (const [id, w] of app.simViews) w.highlight(id === simId ? v.index(n) : -1, w.color);
  update(true);
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  window.addEventListener('pointercancel', onUp);
}

// the start of a drag, read once the sim is being edited (so it is exactly the keyed face)
function begin(d) {
  const app = d.app, v = app.simViews.get(d.simId);
  app.store.checkpoint();
  if (typeof app.beginEdit === 'function') app.beginEdit(d.simId);
  const names = d.kind === 'look' ? ['b__L_Eye__', 'b__R_Eye__'].filter(x => v.bone(x)) : [d.name];
  d.start = {};
  for (const x of names) { const b = K.baseOf(v, x); d.start[x] = { q: b.q.clone(), p: b.p.clone() }; }
  d.inv = parentInHead(v, d.name).invert();
  if (d.kind === 'turn') {
    // which way a turn about the bone's own z moves its dot on the map: the drag direction follows the pointer
    const b = v.bone(d.name), p0 = inHead(v, d.name, handle(v, d.name));
    const q0 = b.quaternion.clone();
    b.quaternion.multiply(_q.setFromAxisAngle(_v.set(0, 0, 1), deg(2)));
    const p1 = inHead(v, d.name, handle(v, d.name));
    b.quaternion.copy(q0);
    d.sign = p0 && p1 && p1.x > p0.x ? -1 : 1;           // + dragging down turns +z when +z moves the dot down
  }
}

function onMove(e) {
  const d = drag;
  if (!d || (d.pointerId != null && e.pointerId !== d.pointerId)) return;
  const dx = e.clientX - d.x0, dy = e.clientY - d.y0;
  if (!d.moved) {
    if (Math.abs(dx) + Math.abs(dy) < 2) return;
    d.moved = true;
    begin(d);
  }
  applyDrag(d, dx, dy, !!(d.app.altDown || e.altKey));
  d.app.poseEdited(d.simId, true, 'face');
  updateFaceMaps(d.app, { force: true });
}

function onUp(e) {
  const d = drag;
  if (!d || (d.pointerId != null && e.pointerId !== d.pointerId && e.type !== 'pointercancel')) return;
  drag = null;
  window.removeEventListener('pointermove', onMove);
  window.removeEventListener('pointerup', onUp);
  window.removeEventListener('pointercancel', onUp);
  const app = d.app;
  if (d.moved) {
    app.poseEdited(d.simId, false, 'face');
    app.afterEdit();
  } else {
    app.emitSelection();
  }
}

// One drag step (dx, dy in screen px from where it started), from the face as it was when the drag started.
export function applyDrag(d, dx, dy, alt = false) {
  const app = d.app, v = app.simViews.get(d.simId), n = d.name;
  if (!v) return false;
  if (!d.start) begin(d);
  const lim = K.faceLimits(n);
  let hit = false;
  if (d.kind === 'look') {
    // both eyes turn the same way: right = toward the sim's left (+x), down = look down (+z)
    const st = d.start.b__L_Eye__ || Object.values(d.start)[0];
    const r0 = v.restByName.b__L_Eye__ || v.restByName[n];
    const e0 = new THREE.Euler().setFromQuaternion(r0.quat.clone().invert().multiply(st.q), 'XYZ');
    let yaw = e0.x + deg(dx * DEG_PER_PX), pitch = e0.z + deg(dy * DEG_PER_PX);
    const tx = (lim && lim.turn && lim.turn[0]) || [-deg(32), deg(32)], tz = (lim && lim.turn && lim.turn[2]) || [-deg(30), deg(30)];
    if (!alt) {
      const cy = Math.min(tx[1], Math.max(tx[0], yaw)), cp = Math.min(tz[1], Math.max(tz[0], pitch));
      hit = cy !== yaw || cp !== pitch; yaw = cy; pitch = cp;
    }
    for (const x of Object.keys(d.start)) {
      const r = v.restByName[x];
      K.setBase(v, x, r.quat.clone().multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(yaw, 0, pitch, 'XYZ'))), null);
    }
  } else if (d.kind === 'turn') {
    const st = d.start[n], r = v.restByName[n];
    const e = new THREE.Euler().setFromQuaternion(r.quat.clone().invert().multiply(st.q), 'XYZ');
    e.z += d.sign * deg(dy * DEG_PER_PX);
    K.setBase(v, n, r.quat.clone().multiply(new THREE.Quaternion().setFromEuler(e)), null);
    if (!alt && K.clampFaceBone(v, n, lim)) hit = true;
  } else {
    // a move in the face plane: right = toward the sim's left (+z), up = up (+x); the tongue comes out (+y) downward
    const mm = 1 / (1000 * PX_PER_MM);
    const inHeadMove = d.kind === 'tongue' ? new THREE.Vector3(0, dy * mm, dx * mm) : new THREE.Vector3(-dy * mm, 0, dx * mm);
    const local = inHeadMove.applyQuaternion(d.inv);
    // an axis the part cannot use (locked in its safe range) stays as it was, unless Alt is held
    if (!alt && lim && lim.move) ['x', 'y', 'z'].forEach((ax, i) => { if (!lim.move[i]) local[ax] = 0; });
    const st = d.start[n];
    K.setBase(v, n, null, st.p.clone().add(local));
    if (!alt && K.clampFaceBone(v, n, lim)) hit = true;
  }
  // Symmetry: the other side does the same (a middle part stays in the middle); the eyes already move together
  if (app.mirrorEdit && d.kind !== 'look') app.mirrorLive(d.simId, n);
  if (hit) flash(d);
  return hit;
}

function flash(d) {
  const g = live && live.dots[d.name];
  if (g) { g.classList.add('limit'); clearTimeout(g._lt); g._lt = setTimeout(() => g.classList.remove('limit'), 320); }
  const now = performance.now();
  if (!d._hud || now - d._hud > 900) { d._hud = now; d.app.hud($t('facemap2d.safe_range_reached_hold_alt'), { hold: 1600 }); }
}

// Double-click: the part back to rest at this frame (the other side too with Symmetry; both eyes for an eye).
function resetPart(app, simId, n) {
  const sim = app.store.sim(simId), v = app.simViews.get(simId);
  if (!sim || !v) return;
  app.store.checkpoint();
  if (typeof app.beginEdit === 'function') app.beginEdit(simId);
  const names = new Set([n]);
  if (EYE.test(n)) { names.add('b__L_Eye__'); names.add('b__R_Eye__'); }
  if (app.mirrorEdit && !K.isCenterFace(n) && K.mirrorName) names.add(K.mirrorName(n));
  for (const x of names) {
    const r = v.restByName[x];
    if (r && v.bone(x)) K.setBase(v, x, r.quat.clone(), r.pos.clone());
  }
  app.store.selected = { sim: simId, bone: n };
  app.poseEdited(simId, false, 'face');
  app.afterEdit();
  app.hud($t('facemap2d.back_to_rest', { plain: plain(sim, n) }), { hold: 1200 });
}

// For checks: the map on screen and a drag done in code (dx, dy in screen px).
export function _live() { return live; }
export function dragInCode(app, simId, name, dx, dy, { alt = false, steps = 6 } = {}) {
  const d = { app, simId, name, kind: kindOf(name), x0: 0, y0: 0, moved: true };
  begin(d);
  for (let i = 1; i <= steps; i++) { applyDrag(d, dx * i / steps, dy * i / steps, alt); app.poseEdited(simId, true, 'face'); }
  app.poseEdited(simId, false, 'face');
  app.afterEdit();
  return d;
}
export { inHead, layoutOf, positions, kindOf };
