// Other bodies and hair (spec_bodies 8 and 9).
//   Try it on other bodies: show the animation on a Tray sim's body or with another penis size, for a while. Only the
//   view changes (app.trial + hooks.bodyOverride): the project is never touched, and nothing is saved or sent to the
//   game with a trial body (it ends before every bake and save).
//   Hair: the sim's own CAS hair from the game (a preset style and colour, or a Tray sim's own hair), skinned to the
//   skeleton in the view. Preview only: the game dresses the sim itself.
import * as THREE from 'three';
import { api } from './api.js';
import { toast } from './ui.js';

export const SIZE_PRESETS = {
  small: { label: 'Small', vals: { length: -1, girth: -0.6, balls: -0.5 } },
  average: { label: 'Average', vals: {} },
  large: { label: 'Large', vals: { length: 0.7, girth: 0.5 } },
  xl: { label: 'Very large', vals: { length: 1, girth: 1, balls: 0.5 } },
};
const FRAME_OF = { male: 'ym', female: 'yf', MALE: 'ym', FEMALE: 'yf', m: 'ym', f: 'yf' };

const json = async url => {
  const r = await fetch(url);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(body.error || ('HTTP ' + r.status)), { status: r.status });
  return body;
};
const q = o => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString();

// ---------------------------------------------------------------- the Tray sims to try
let _tray = null;
export function traySims() {
  if (!_tray) {
    _tray = api.tray().then(hs => {
      const out = [];
      for (const hh of hs || []) (hh.sims || []).forEach(s => {
        if (!s.allowed) return;
        const frame = FRAME_OF[s.gender] || null;
        if (!frame) return;
        out.push({ tray: hh.id, index: s.index, name: `${s.first || ''} ${s.last || ''}`.trim() || 'Sim', first: s.first || 'Sim', simId: s.sim_id, frame, household: hh.name });
      });
      return out;
    }).catch(err => { _tray = null; throw err; });
  }
  return _tray;
}

// ---------------------------------------------------------------- trials
const trialOf = (app, id) => {
  const t = app.trial && app.trial.get(id);
  return t && t.uid === app.store.project.uid ? t : null;
};
export function activeTrial(app, simId) { return trialOf(app, simId); }

// hooks.bodyOverride: the trial body, once it has arrived
export function bodyOverride(app, s) {
  const t = trialOf(app, s.id);
  if (!t || !app.assets.bodies[t.bodyKey] || (t.frame && t.frame !== s.frame)) return null;   // the body type changed since
  return t.toneKey === undefined ? { bodyKey: t.bodyKey } : { bodyKey: t.bodyKey, toneKey: t.toneKey };
}

// Load the body an option shows (kept for the session). -> {bodyKey, toneKey?, label, hair?}
async function loadOption(app, s, opt) {
  app._trialMeta = app._trialMeta || new Map();
  if (opt.kind === 'tray') {
    const key = `trial:tray:${opt.tray}:${opt.index}`;
    if (!app.assets.bodies[key]) {
      const r = await json('/api/body_variant?' + q({ tray: opt.tray, index: opt.index }));
      app.assets.bodies[key] = r.body;
      app._trialMeta.set(key, { tone: r.tone || '', hair: r.hair || null, name: r.name || opt.name });
    }
    const m = app._trialMeta.get(key) || {};
    return { bodyKey: key, toneKey: m.tone || '', label: `${opt.name || m.name || 'a Tray sim'}'s body`, hair: m.hair || null };
  }
  if (opt.kind === 'size') {
    const pr = SIZE_PRESETS[opt.preset] || SIZE_PRESETS.average;
    const base = s.tray ? { tray: s.tray.id, index: s.tray.index } : { frame: s.frame };
    const key = `trial:size:${s.tray ? `tray:${s.tray.id}:${s.tray.index}` : s.frame}:${opt.preset}`;
    if (!app.assets.bodies[key]) {
      const r = await json('/api/body_variant?' + q({ ...base, ...pr.vals }));
      app.assets.bodies[key] = r.body;
      app._trialMeta.set(key, { tone: s.tray ? (r.tone || '') : undefined });
    }
    const m = app._trialMeta.get(key) || {};
    return { bodyKey: key, toneKey: s.tray ? m.tone : undefined, label: `a ${pr.label.toLowerCase()} penis` };
  }
  return null;
}

// Show `opt` on the sim: {kind: 'own'} | {kind: 'tray', tray, index, name} | {kind: 'size', preset}.
export async function tryBody(app, simId, opt) {
  const s = app.store.sim(simId);
  if (!s || !opt) return false;
  app.trial = app.trial || new Map();
  if (opt.kind === 'own' || (opt.kind === 'size' && opt.preset === 'average')) { endTrial(app, simId, { quiet: true }); return true; }
  const token = (app._trialToken = (app._trialToken || 0) + 1);
  let o;
  try { o = await loadOption(app, s, opt); } catch (err) {
    toast(`Could not load that body: ${err.message}`, 'err');
    return false;
  }
  if (!o || token !== app._trialToken || !app.store.sim(simId)) return false;
  app.trial.set(simId, { ...o, opt, uid: app.store.project.uid, frame: s.frame });
  refreshBodies(app);
  return true;
}

export function endTrial(app, simId = null, { quiet = false } = {}) {
  if (!app.trial || !app.trial.size) { showBanner(app); return false; }
  if (simId) app.trial.delete(simId); else app.trial.clear();
  app._trialToken = (app._trialToken || 0) + 1;
  refreshBodies(app);
  if (!quiet) toast('Back to your own bodies.');
  return true;
}

function refreshBodies(app) {
  app.syncViews();
  app.applyPoses();
  if (app.interact) app.interact.refreshHandles();
  // the jiggle is simulated again on the body now shown (a moment later, so the swap itself is quick)
  clearTimeout(app._trialSim);
  app._trialSim = setTimeout(() => { try { app.pipeline.simulateIfNeeded(true); app.applyPoses(false); } catch (e) { console.error(e); } }, 60);
  showBanner(app);
  if (app.step === 'body') app.renderStep();
}

// The options "Change body every loop" goes through for a sim: own, the Tray sims with the same body, the sizes.
export async function trialOptions(app, s) {
  const out = [{ kind: 'own', label: 'Own body' }];
  if (s.frame !== 'yf_futa') {
    try {
      const list = (await traySims()).filter(t => t.frame === s.frame).slice(0, 8);
      for (const t of list) out.push({ kind: 'tray', tray: t.tray, index: t.index, name: t.name, label: t.first });
    } catch { /* no Tray */ }
  }
  const v = app.simViews.get(s.id);
  if (v && v.hasPenis) for (const k of ['small', 'large', 'xl']) out.push({ kind: 'size', preset: k, label: SIZE_PRESETS[k].label });
  return out;
}

const sameOpt = (a, b) => a && b && a.kind === b.kind && (a.kind !== 'tray' || (a.tray === b.tray && a.index === b.index)) && (a.kind !== 'size' || a.preset === b.preset);

// The next option after the one shown (or the first other one).
export async function nextBody(app, simId) {
  const s = app.store.sim(simId);
  if (!s) return;
  const list = await trialOptions(app, s);
  if (list.length < 2) { toast('No other bodies to try - add adult sims to your Tray in the game.'); return; }
  const t = trialOf(app, simId);
  const i = t ? list.findIndex(o => sameOpt(o, t.opt)) : 0;
  const next = list[(i + 1) % list.length];
  await tryBody(app, simId, next);
  // get the one after ready meanwhile
  const after = list[(i + 2) % list.length];
  if (after && after.kind !== 'own') loadOption(app, s, after).catch(() => {});
}

// "Change body every loop while playing": at every loop wrap the next body (hooks.tick).
export function setCycle(app, simId, on) {
  app._cycle = on ? { simId, busy: false } : null;
  if (on && !app.playing) app.setPlaying(true);
  if (on) nextBody(app, simId);
  showBanner(app);
}
export function onTick(app, wrapped) {
  const c = app._cycle;
  if (!c || !wrapped || c.busy || !app.playing) return;
  if (!app.store.sim(c.simId)) { app._cycle = null; return; }
  c.busy = true;
  nextBody(app, c.simId).finally(() => { c.busy = false; });
}

// The pill over the stage: "Trying Mia Stone's body on Female 1 · Next · Stop".
export function showBanner(app) {
  const wrap = document.getElementById('viewport-wrap');
  if (!wrap) return;
  let el = document.getElementById('vp-trial');
  const entries = [...(app.trial || new Map())].filter(([id]) => trialOf(app, id) && app.store.sim(id));
  if (!entries.length && !app._cycle) { if (el) el.classList.add('hidden'); return; }
  if (!el) {
    el = document.createElement('div');
    el.id = 'vp-trial';
    el.className = 'vp-trial hidden';
    wrap.append(el);
  }
  el.innerHTML = '';
  const [id, t] = entries[0] || [app._cycle && app._cycle.simId, null];
  const sim = app.store.sim(id);
  const txt = document.createElement('span');
  txt.innerHTML = t ? `Trying <b></b> on <b></b>` : `Changing bodies every loop on <b></b>`;
  const bs = txt.querySelectorAll('b');
  if (t) { bs[0].textContent = t.label; bs[1].textContent = sim ? sim.label : ''; } else bs[0].textContent = sim ? sim.label : '';
  const btn = (label, fn, cls = '') => { const b = document.createElement('button'); b.type = 'button'; b.className = 'vp-trial-btn ' + cls; b.textContent = label; b.onclick = fn; return b; };
  el.append(txt,
    btn('Next', () => nextBody(app, id)),
    btn('Stop', () => { setCycle(app, null, false); endTrial(app); }, 'stop'));
  el.classList.remove('hidden');
}

// ---------------------------------------------------------------- hair
let _presets = null;
export function hairPresets() {
  if (!_presets) _presets = json('/api/hair_presets').catch(err => { _presets = null; throw err; });
  return _presets;
}

// What hair a sim shows: its choice (sim.hair), a trial Tray body's own hair, or - when it never chose - a Tray sim's
// own hair. null: none. The hair takes the shape of the Tray body it sits on (shape_tray / shape_index; tray= already
// does): that sim's sliders move its head (a height or neck slider: 10 cm and more), and the hair has to come along.
export function hairSpecOf(app, s) {
  const t = trialOf(app, s.id);
  if (t && t.opt && t.opt.kind === 'tray') {
    return t.hair && t.hair.casp && t.hair.origin ? { casp: t.hair.casp, shape_tray: t.opt.tray, shape_index: t.opt.index } : null;
  }
  if (s.hair === false || s.hair === null) return null;
  const shape = s.tray && s.tray.id ? { shape_tray: s.tray.id, shape_index: s.tray.index || 0 } : {};
  if (s.hair && (s.hair.name || s.hair.casp)) return { ...(s.hair.name ? { name: s.hair.name } : { casp: s.hair.casp }), ...shape };
  if (s.tray && s.tray.id) return { tray: s.tray.id, index: s.tray.index };
  return null;
}
const hairKey = h => (h ? (h.name ? 'n:' + h.name : h.casp ? 'c:' + h.casp : `t:${h.tray}:${h.index}`)
  + (h.shape_tray ? `@${h.shape_tray}:${h.shape_index}` : '') : '');

const _texLoader = new THREE.TextureLoader();
// one request per hair for the session: {data, texture} (texture null when the hair has none)
function fetchHair(app, spec) {
  app._hair = app._hair || new Map();
  const key = hairKey(spec);
  if (!app._hair.has(key)) {
    const p = json('/api/hair?' + q(spec)).then(data => {
      // no hair in the answer: the engine may still be reading the game's parts - asked again next time
      if (!data || !data.meshes || !data.meshes.length) { app._hair.delete(key); return { data, texture: null }; }
      if (!data.texture) return { data, texture: null };
      return new Promise(res => {
        _texLoader.load('/api/hair_tex?file=' + encodeURIComponent(data.texture), tex => {
          tex.flipY = false; tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
          res({ data, texture: tex });
        }, undefined, () => res({ data, texture: null }));
      });
    }).catch(err => { app._hair.delete(key); console.warn('hair:', err.message); return null; });
    app._hair.set(key, p);
  }
  return app._hair.get(key);
}

// Try something again after 2, 5 and then 12 s (at most 3 times per view and thing).
export function retryLater(v, what, fn) {
  v._retries = v._retries || {};
  const n = v._retries[what] = (v._retries[what] || 0) + 1;
  if (n > 3) return false;
  setTimeout(fn, [2000, 5000, 12000][n - 1]);
  return true;
}

// Put the right hair on a view (hooks.viewCreated, and after a change). Stale answers are dropped.
export async function loadHair(app, v, s) {
  const spec = hairSpecOf(app, s), key = hairKey(spec);
  const hairParts = () => (v.parts || []).filter(m => m.userData.role === 'hair').length;       // (clothes are parts too)
  if (v.hairKey === key && (key || !hairParts())) return hairParts();
  v.hairKey = key;
  if (!spec) { v.removeParts('hair'); return 0; }
  const t0 = performance.now();
  const r = await fetchHair(app, spec);
  if (v.hairKey !== key || app.simViews.get(s.id) !== v) return 0;          // changed or replaced meanwhile
  v.removeParts('hair');
  if (!r || !r.data || !r.data.meshes || !r.data.meshes.length) {
    // a failed or empty answer (a busy start: a continued animation asks for everything at once) is tried again a
    // few times, a little later each time - never taken as "no hair" for good on the first try
    if (retryLater(v, 'hair:' + key, () => { if (app.simViews.get(s.id) === v && v.hairKey === undefined) loadHair(app, v, s).catch(() => {}); })) v.hairKey = undefined;
    return 0;
  }
  const n = v.addPart(r.data, r.texture, { role: 'hair' });
  v.hairMs = Math.round(performance.now() - t0);
  v.hairName = r.data.name || null;
  return n;
}

export function reloadHair(app, simId) {
  const s = app.store.sim(simId), v = s && app.simViews.get(simId);
  if (!v) return Promise.resolve(0);
  v.hairKey = undefined;
  return loadHair(app, v, s);
}

// The hair a new sim gets: the default preset of its body (none for a Tray sim: it keeps its own).
export async function defaultHair(frame) {
  try { const p = await hairPresets(); return p.defaults && p.defaults[frame] ? { name: p.defaults[frame] } : null; } catch { return null; }
}
