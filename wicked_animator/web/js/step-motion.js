// Step 3 - Motion: one-click motion layers with sliders first, and how keys work in a short tip below.
import { h, icon, slider, toggle, section, tip } from './ui.js';
import { MOTIONS, MOTION_PARAMS, AXES, awayCurve, LOOK_TARGETS, TREMBLE_PARTS, trembleEnvelope, trembleWave, trembleCycles } from './motion.js';
import { worldToSpace } from './posemath.js';
import { LIMB_LABEL } from './bones.js';
import { simTabs } from './steps.js';
import { $t } from './i18n.js';

const MOTION_ICON = { thrust: 'motion', ride: 'motion', grind: 'motion', bounce: 'motion', twerk: 'motion', sway: 'motion', headbob: 'face', stroke: 'hand', breathe: 'body', look: 'eye', tremble: 'bolt' };

// A tiny picture of each motion: its wave (the dashes move only while the pointer is on the tile)
const WAVES = {
  thrust: 'M0 9 C10 1 20 1 30 9 S50 17 60 9 S80 1 90 9 S110 17 120 9',
  ride: 'M0 14 Q15 2 30 14 T60 14 T90 14 T120 14', bounce: 'M0 16 Q15 0 30 16 Q45 0 60 16 Q75 0 90 16 Q105 0 120 16',
  grind: 'M0 9 C20 0 40 18 60 9 S100 0 120 9', twerk: 'M0 9 l10 -7 10 14 10 -14 10 14 10 -14 10 14 10 -14 10 14 10 -14 10 14 10 -14 10 7',
  sway: 'M0 9 C30 2 30 16 60 9 S90 2 120 9', headbob: 'M0 12 C8 4 16 4 24 12 S40 20 48 12 S64 4 72 12 S88 20 96 12 S112 4 120 12',
  stroke: 'M0 9 H120', breathe: 'M0 13 C30 3 45 3 60 9 S90 15 120 5',
  look: 'M0 14 C30 14 40 4 60 4 S100 4 120 4',
  tremble: 'M0 9 l4 -4 3 7 4 -6 3 5 4 -7 3 6 4 -3 3 5 4 -6 3 4 4 -5 3 7 4 -6 3 4 4 -5 3 6 4 -4 3 5 4 -6 3 5 4 -4 3 6 4 -5 3 4 4 -6 3 5 4 -4 3 4 4 -3 3 2',
};
function wave(type) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('class', 'mwave'); s.setAttribute('viewBox', '0 0 120 18'); s.setAttribute('preserveAspectRatio', 'none');
  s.setAttribute('aria-hidden', 'true');
  s.innerHTML = `<path d="${WAVES[type] || WAVES.thrust}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" vector-effect="non-scaling-stroke"/>`;
  return s;
}

export function renderMotion(app, root) {
  const p = app.store.project;
  const sim = app.store.sim();
  if (!sim) { root.append(h('div', { class: 'empty-state' }, h('b', {}, $t('step-motion.add_sim_first')), h('p', {}, $t('step-motion.go_to_step_1_scene')))); return; }
  root.append(simTabs(app));

  // the motions on this sim (with their sliders), then the catalogue to add more
  const groups = {};
  for (const [type, m] of Object.entries(MOTIONS)) (groups[m.group] = groups[m.group] || []).push([type, m]);
  const add = h('div', {});
  for (const [g, items] of Object.entries(groups)) {
    add.append(h('div', { class: 'tag-group' }, h('span', {}, g), h('div', { class: 'tiles' }, items.map(([type, m]) =>
      h('button', { class: 'tile motion-tile' + (app._justPicked === type ? ' pop' : ''), title: m.desc, 'data-motion': type, onclick: () => app.addLayer(sim.id, type) },
        wave(type), h('b', {}, '+ ' + m.label), h('small', {}, m.desc.split('.')[0] + '.'))))));
  }
  const layers = sim.layers || [];
  if (layers.length) {
    const list = h('div', {});
    for (const l of layers) list.append(layerCard(app, sim, l));
    root.append(section([$t('step-motion.motions_on', { simLabel: sim.label }), h('span', { class: 'count' }, `${layers.filter(l => l.on).length} on`)], list));
  }
  if (!layers.length) root.append(h('div', { class: 'empty-state compact' },
    h('b', {}, $t('step-motion.nothing_moves_yet')), h('p', {}, $t('step-motion.pick_motion_below_it_loops'))));
  root.append(section(layers.length ? $t('step-motion.add_another_motion') : $t('step-motion.add_motion_to', { simLabel: sim.label }), add));
  root.append(followThrough(app, sim));
  root.append(tip($t('step-motion.want_full_control_pose_press')));
  root.append(h('div', { class: 'hint' }, $t('step-motion.loop_is_s_times_per', { pCount: (p.length / 30).toFixed(1) })));
}

// Arms and head reach each pose a few frames after the body (sim.lag, played by the pipeline).
function followThrough(app, sim) {
  const lag = () => sim.lag || { arms: 0, head: 0 };
  const set = (k, v, done) => {
    const cur = { arms: 0, head: 0, ...lag(), [k]: Math.round(v) };
    if (!cur.arms && !cur.head) delete sim.lag; else sim.lag = cur;
    app.layersChanged(done);
  };
  const fmt = v => (Math.round(v) ? $t('step-motion.n_frames', { n: Math.round(v) }) : $t('step-motion.off'));
  return section($t('step-motion.follow_through'),
    h('div', { class: 'hint', style: { marginTop: 0 } }, $t('step-motion.arms_and_head_reach_each')),
    slider({ label: $t('step-motion.arms_follow_late'), min: 0, max: 8, step: 1, value: lag().arms || 0, fmt,
      onStart: () => app.store.checkpoint(), onInput: (v, done) => set('arms', v, done) }),
    slider({ label: $t('step-motion.head_follows_late'), min: 0, max: 8, step: 1, value: lag().head || 0, fmt,
      onStart: () => app.store.checkpoint(), onInput: (v, done) => set('head', v, done) }));
}

function layerCard(app, sim, l) {
  const m = MOTIONS[l.type];
  const open = app._openLayer === l.id;
  // read fresh every time: the sliders change l.params while the card stays on screen
  const P = () => ({ ...m.params, ...l.params });
  const summary = () => {
    const q = P();
    if (l.type === 'look') return `${LOOK_TARGETS[q.target] || 'Face'}${q.eyes === false ? '' : ' · eyes'}`;
    if (l.type === 'tremble') return `${TREMBLE_PARTS[q.parts] || 'Legs'} · ${q.amount ?? 2.5}°`;
    return `${Math.round(q.strokes || 1)}× · ${q.distance !== undefined ? q.distance + ' cm' : (q.angle || 0) + '°'}`;
  };
  const wave = h('canvas', { class: 'layer-wave', width: 560, height: 60 });
  const drawWave = () => {
    const q = P();
    const g = wave.getContext('2d'), w = wave.width, hh = wave.height;
    g.clearRect(0, 0, w, hh);
    const grad = g.createLinearGradient(0, 0, w, 0); grad.addColorStop(0, '#ff4f9a'); grad.addColorStop(1, '#a855f7');
    g.strokeStyle = 'rgba(255,255,255,0.08)'; g.beginPath(); g.moveTo(0, hh - 6); g.lineTo(w, hh - 6); g.stroke();
    g.strokeStyle = grad; g.lineWidth = 3; g.beginPath();
    const strokes = Math.max(1, Math.round(q.strokes || 1));
    const p = app.store.project, cyc = l.type === 'tremble' ? trembleCycles(p.length, p.fps || 30, q.speed) : null;
    for (let x = 0; x <= w; x++) {
      const ph = (x / w) * strokes + (l.phase || 0);
      const u = x / w;
      const a = l.type === 'look' ? 1 - Math.min(1, (l.weight ?? 1))
        : l.type === 'tremble' ? 0.5 + 0.5 * trembleWave(l.id + 'wave', u, cyc) * trembleEnvelope(u, q.start ?? 0, q.end ?? 1)
          : l.type === 'sway' || l.type === 'breathe' ? (Math.sin(2 * Math.PI * ph) + 1) / 2 : awayCurve(ph, q.sharp || 0);
      const y = 6 + a * (hh - 12);
      x ? g.lineTo(x, y) : g.moveTo(x, y);
    }
    g.stroke();
    const f = (app.store.frame / app.store.project.length) * w;
    g.fillStyle = '#fff'; g.fillRect(f - 1, 0, 2, hh);
  };
  const head = h('small', {}, summary());
  const change = (fn, done) => { fn(); app.layersChanged(done); head.textContent = summary(); drawWave(); };
  const body = h('div', { class: 'layer-body' });
  if (open) {
    const Q = P();
    body.append(h('div', { class: 'hint', style: { marginTop: '8px' } }, m.desc), wave);
    for (const key of Object.keys(m.params)) {
      if (key === 'reverse' || key === 'axis' || key === 'limb') continue;
      const d = MOTION_PARAMS[key];
      if (!d) continue;
      body.append(slider({ label: d.label, min: d.min, max: d.max, step: d.step, value: Q[key], title: d.hint,
        fmt: v => d.pct ? Math.round(v * 100) + '%' : `${v}${d.unit ? ' ' + d.unit : ''}`,
        onStart: () => app.store.checkpoint(), onInput: (v, done) => change(() => { l.params[key] = v; }, done) }));
    }
    const timed = l.type !== 'look' && l.type !== 'tremble';
    if (timed) body.append(slider({ label: MOTION_PARAMS.phase.label, min: 0, max: 1, step: 0.01, value: l.phase || 0, title: MOTION_PARAMS.phase.hint, fmt: v => Math.round(v * 100) + '%',
      onStart: () => app.store.checkpoint(), onInput: (v, done) => change(() => { l.phase = v; }, done) }));
    if (l.type !== 'tremble') body.append(slider({ label: MOTION_PARAMS.weight.label, min: 0, max: l.type === 'look' ? 1 : 1.5, step: 0.05, value: l.weight ?? 1, fmt: v => Math.round(v * 100) + '%',
      title: l.type === 'look' ? $t('step-motion.how_far_head_turns_toward') : null,
      onStart: () => app.store.checkpoint(), onInput: (v, done) => change(() => { l.weight = v; }, done) }));
    if (l.type === 'look') {
      const target = h('select', {}, Object.entries(LOOK_TARGETS).map(([k, t]) => h('option', { value: k, selected: (Q.target || 'face') === k }, t)));
      target.onchange = () => {
        app.store.checkpoint();
        const v = app.simViews.get(sim.id);
        change(() => {
          l.params.target = target.value;
          // "Where the camera is now": the spot is kept in the sim's space, so the game shows the same as the view
          if (target.value === 'camera' && v) l.params.point = worldToSpace(v, app.vp.camera.position).toArray().map(x => Math.round(x * 1000) / 1000);
        }, true);
        target.blur();
      };
      const others = app.store.project.sims.filter(s => s.id !== sim.id);
      const who = h('select', {}, [h('option', { value: 'auto', selected: !Q.who || Q.who === 'auto' }, $t('step-motion.automatic_nearest')),
        ...others.map(s => h('option', { value: s.id, selected: Q.who === s.id }, s.label))]);
      who.onchange = () => { app.store.checkpoint(); change(() => { l.params.who = who.value; }, true); who.blur(); };
      body.append(h('label', { class: 'field' }, h('span', {}, $t('step-motion.look_at')), target));
      if (Q.target !== 'camera') body.append(h('label', { class: 'field' }, h('span', {}, $t('step-motion.who')), who));
      body.append(h('label', { class: 'check' }, toggle(Q.eyes !== false, on => { app.store.checkpoint(); change(() => { l.params.eyes = on; }, true); }), $t('step-motion.eyes_follow')));
    }
    if (l.type === 'tremble') {
      const parts = h('select', {}, Object.entries(TREMBLE_PARTS).map(([k, t]) => h('option', { value: k, selected: (Q.parts || 'legs') === k }, t)));
      parts.onchange = () => { app.store.checkpoint(); change(() => { l.params.parts = parts.value; }, true); parts.blur(); };
      body.append(h('label', { class: 'field' }, h('span', {}, $t('step-motion.parts')), parts));
    }
    if ('axis' in m.params) {
      const opts = l.type === 'stroke' ? ['penis', 'forearm', 'up', 'forward'] : ['forward', 'up', 'bodyUp', 'side'];
      const sel = h('select', {}, opts.map(a => h('option', { value: a, selected: Q.axis === a }, AXES[a])));
      sel.onchange = () => { app.store.checkpoint(); change(() => { l.params.axis = sel.value; }, true); sel.blur(); };
      body.append(h('label', { class: 'field' }, h('span', {}, $t('step-motion.direction')), sel));
    }
    if ('limb' in m.params) {
      const sel = h('select', {}, ['R hand', 'L hand', 'R foot', 'L foot'].map(a => h('option', { value: a, selected: Q.limb === a }, LIMB_LABEL[a])));
      sel.onchange = () => { app.store.checkpoint(); change(() => { l.params.limb = sel.value; }, true); sel.blur(); };
      body.append(h('label', { class: 'field' }, h('span', {}, $t('step-motion.which_hand')), sel));
    }
    if ('reverse' in m.params) {
      body.append(h('label', { class: 'check' }, toggle(!!Q.reverse, on => { app.store.checkpoint(); change(() => { l.params.reverse = on; }, true); }), $t('step-motion.reverse_direction')));
    }
    const partner = app.store.project.sims.find(s => s.id !== sim.id && (s.layers || []).length);
    if (timed) body.append(h('div', { class: 'btn-grid', style: { marginTop: '8px' } },
      h('button', { class: 'btn small', disabled: !partner, title: partner ? $t('step-motion.match_s_speed_and_meet', { partnerLabel: partner.label }) : $t('step-motion.other_sim_has_no_motion'), onclick: () => app.syncLayer(sim.id, l.id) }, icon('chain'), $t('step-motion.meet_partner')),
      h('button', { class: 'btn small', title: $t('step-motion.make_ordinary_keys_from_this'), onclick: () => app.bakeLayer(sim.id, l.id) }, icon('key'), $t('step-motion.turn_into_keys'))));
    requestAnimationFrame(drawWave);
  }
  return h('div', { class: 'layer' + (l.on ? '' : ' off') + (open ? ' open' : '') },
    h('div', { class: 'layer-head', onclick: () => { app._openLayer = open ? null : l.id; app.refreshPanels(); } },
      h('div', { class: 'ic' }, icon(MOTION_ICON[l.type] || 'motion')),
      h('b', {}, m.label, ' ', head),
      h('span', { onclick: e => e.stopPropagation() }, toggle(l.on, on => { app.store.checkpoint(); l.on = on; app.layersChanged(true); app.refreshPanels(); })),
      h('button', { class: 'icon-btn sm', title: $t('step-motion.remove'), onclick: e => { e.stopPropagation(); app.removeLayer(sim.id, l.id); } }, icon('trash')),
      h('button', { class: 'icon-btn sm', title: open ? $t('step-motion.hide_sliders') : $t('step-motion.show_sliders') }, icon(open ? 'up' : 'down'))),
    body);
}
