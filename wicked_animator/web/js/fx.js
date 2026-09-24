// Celebrations: one-shot particles (little spinning plumbobs and sparks) on one canvas over everything, the success
// tick, the Magic "spell" glow and the first-animation card. The particle loop runs ONLY while particles are alive,
// then stops and clears itself; never more than 160 on screen; nothing at all with reduced motion. The canvas never
// takes a click (pointer-events: none).

export const reducedMotion = () =>
  (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) || document.documentElement.classList.contains('reduce-motion');

export const MAX_PARTICLES = 160;
export const particleCount = () => parts.length;

const SPARKS = ['#ff4f9a', '#ff8cc4', '#c04fe0', '#8b5cf6', '#ffffff'];
// the logo's plumbob facets: light top, lilac bottom (and now and then a Sims-green one)
const BOB = [['#ffffff', '#ffe3f0', '#f3dcff', '#d7b8ff'], ['#7df0ad', '#3ddc84', '#29b86b', '#1f9656']];

let cvs = null, ctx = null, parts = [], raf = 0, last = 0;

function ensure() {
  if (!cvs) {
    cvs = document.createElement('canvas');
    cvs.id = 'fx';
    cvs.setAttribute('aria-hidden', 'true');
    document.body.append(cvs);
    ctx = cvs.getContext('2d');
  }
  if (!raf) {
    const d = Math.min(2, window.devicePixelRatio || 1);
    cvs.width = Math.round(innerWidth * d); cvs.height = Math.round(innerHeight * d);
    ctx.setTransform(d, 0, 0, d, 0, 0);
  }
}

function add(p) {
  parts.push(p);
  if (parts.length > MAX_PARTICLES) parts.shift();   // hard cap, never more than this on screen
}

// A burst from a point (a button, the success tick): sparks fly up and out, then fall.
export function burst(x, y, { count = 26, power = 1, spread = 1, plumbobs = 0.34 } = {}) {
  if (reducedMotion()) return;
  ensure();
  for (let i = 0; i < count; i++) {
    const a = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 1.15 * spread;
    const v = (300 + Math.random() * 330) * power;
    add({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 0, max: 0.85 + Math.random() * 0.65,
      s: 4.5 + Math.random() * 4.5, spin: Math.random() * 6, vs: 7 + Math.random() * 9,
      c: SPARKS[i % SPARKS.length], bob: Math.random() < plumbobs ? (Math.random() < 0.18 ? 1 : 0) + 1 : 0 });
  }
  start();
}

// A gentle rain over the whole window (first animation ever sent to the game).
export function rain({ count = 56, seconds = 1.6 } = {}) {
  if (reducedMotion()) return;
  ensure();
  for (let i = 0; i < count; i++) {
    add({ x: Math.random() * innerWidth, y: -20 - Math.random() * innerHeight * 0.35, vx: (Math.random() - 0.5) * 60, vy: 120 + Math.random() * 180,
      life: 0, max: seconds + Math.random() * 0.8, s: 5 + Math.random() * 5, spin: Math.random() * 6, vs: 4 + Math.random() * 6,
      c: SPARKS[i % SPARKS.length], bob: Math.random() < 0.45 ? (Math.random() < 0.2 ? 1 : 0) + 1 : 0, g: 260 });
  }
  start();
}

function start() {
  if (raf) return;
  last = performance.now();
  raf = requestAnimationFrame(tick);
}

function drawBob(p, k) {
  const w = Math.cos(p.spin) * p.s, h = p.s * 1.45, c = BOB[p.bob - 1];
  const front = Math.cos(p.spin) > 0;
  ctx.fillStyle = front ? c[0] : c[1];
  ctx.beginPath(); ctx.moveTo(p.x, p.y - h); ctx.lineTo(p.x + w, p.y); ctx.lineTo(p.x, p.y); ctx.fill();
  ctx.fillStyle = front ? c[1] : c[0];
  ctx.beginPath(); ctx.moveTo(p.x, p.y - h); ctx.lineTo(p.x - w, p.y); ctx.lineTo(p.x, p.y); ctx.fill();
  ctx.fillStyle = front ? c[2] : c[3];
  ctx.beginPath(); ctx.moveTo(p.x, p.y + h); ctx.lineTo(p.x + w, p.y); ctx.lineTo(p.x, p.y); ctx.fill();
  ctx.fillStyle = front ? c[3] : c[2];
  ctx.beginPath(); ctx.moveTo(p.x, p.y + h); ctx.lineTo(p.x - w, p.y); ctx.lineTo(p.x, p.y); ctx.fill();
}

function tick(now) {
  const dt = Math.min(0.033, (now - last) / 1000);
  last = now;
  ctx.clearRect(0, 0, innerWidth, innerHeight);
  parts = parts.filter(p => (p.life += dt) < p.max);
  window.__fxPeak = Math.max(window.__fxPeak || 0, parts.length);
  for (const p of parts) {
    const g = p.g ?? 980;
    p.vx *= 1 - 2.2 * dt;
    p.vy = p.vy * (1 - 1.1 * dt) + g * dt;
    p.x += p.vx * dt; p.y += p.vy * dt; p.spin += p.vs * dt;
    const k = 1 - p.life / p.max;
    ctx.globalAlpha = Math.min(1, k * 2.2);
    if (p.bob) drawBob(p, k);
    else {
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.spin * 0.6);
      ctx.fillStyle = p.c; ctx.fillRect(-Math.abs(Math.cos(p.spin)) * p.s * 0.5, -p.s * 0.28, Math.abs(Math.cos(p.spin)) * p.s + 1, p.s * 0.56);
      ctx.restore();
    }
  }
  ctx.globalAlpha = 1;
  if (parts.length) raf = requestAnimationFrame(tick);
  else { raf = 0; ctx.clearRect(0, 0, innerWidth, innerHeight); }
}

// The "spell" glow for Magic: a soft light that grows from (x, y) over the whole window. Transform only.
export function spell(x, y) {
  if (reducedMotion()) return;
  const el = document.createElement('div');
  el.className = 'wa-spell';
  el.style.setProperty('--x', x + 'px'); el.style.setProperty('--y', y + 'px');
  document.body.append(el);
  el.addEventListener('animationend', () => el.remove(), { once: true });
  setTimeout(() => el.remove(), 1500);
}

// The success tick used in "It's in your Mods folder" and the export/record success dialogs.
export function successHero() {
  const wrap = document.createElement('div');
  wrap.className = 'success-hero';
  wrap.innerHTML = `<svg viewBox="0 0 64 64" aria-hidden="true">
    <circle class="halo" cx="32" cy="32" r="30"/>
    <circle class="disc" cx="32" cy="32" r="24"/>
    <circle class="ring" cx="32" cy="32" r="29" pathLength="1"/>
    <path class="tick" d="M21.5 32.5 28.5 39.5 43 25" pathLength="1"/></svg>`;
  return wrap;
}

// Celebrate at an element's centre, after `delay` ms (when the tick starts drawing).
export function celebrateAt(el, { delay = 480, ...opts } = {}) {
  setTimeout(() => {
    if (!el.isConnected) return;
    const r = el.getBoundingClientRect();
    burst(r.left + r.width / 2, r.top + r.height / 2, opts);
  }, delay);
}

// The collectible card for the very first animation sent to the game: its picture, name, creator and date.
export function firstCard({ thumb = null, name = '', author = '', date = new Date() } = {}) {
  const card = document.createElement('div');
  card.className = 'first-card';
  if (thumb) { const img = document.createElement('img'); img.src = thumb; img.alt = ''; card.append(img); }
  else { const ph = document.createElement('div'); ph.className = 'ph'; card.append(ph); }
  const no = document.createElement('span'); no.className = 'no'; no.textContent = 'Creator #1'; card.append(no);
  const b = document.createElement('b'); b.textContent = name || 'Your animation'; card.append(b);
  const sm = document.createElement('small');
  sm.textContent = `${author ? 'by ' + author + ' · ' : ''}${date.toLocaleDateString()}`;
  card.append(sm);
  return card;
}
