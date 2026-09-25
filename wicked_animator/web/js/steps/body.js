// Step 4, Body: erection, tongue, twist helpers, hair, trying other bodies, holes that open by themselves, physics.
import { h, slider, toggle, toggleRow, section } from '../ui.js';
import { BODY_TYPES } from '../state.js';
import { simBody } from '../pipeline.js';
import { HOLES } from '../openings.js';
import { PARTS, PHYSICS_MAX } from '../physics.js';
import { api } from '../api.js';
import * as B from '../bodies.js';
import { openTrayDialog } from '../dialogs/tray.js';
import { simTabs, pct } from './common.js';

export function renderBody(app, root) {
  const sim = app.store.sim();
  if (!sim) { root.append(h('div', { class: 'empty' }, 'Select a sim first.')); return; }
  root.append(simTabs(app));
  const b = simBody(sim), v = app.simViews.get(sim.id);
  const set = (fn, label) => app.setBody(sim.id, fn, label);

  const bodySeg = h('div', { class: 'seg-inline' }, Object.entries(BODY_TYPES).map(([k, bt]) =>
    h('button', { class: sim.frame === k ? 'on' : '', onclick: () => app.setSimBody(sim.id, k) }, bt.label)));
  root.append(section('Body', bodySeg,
    v && v.hasPenis ? toggleRow('Erection', 'Hard or soft penis. WickedWhims switches it in the game by itself; this is for posing and aiming.', b.erect, on => set(x => { x.erect = on; if (!on) delete x.grow; })) : null,
    v && v.hasPenis ? growRow(app, sim, b, set) : null,
    toggleRow('Tongue', 'WickedWhims\' tongue inside the mouth (for licking and oral).', b.tongue, on => set(x => { x.tongue = on; })),
    // the twist helpers follow the hand, arm and leg by themselves (a missing setting means on / off as below)
    toggleRow('Smooth wrists and shoulders', 'Wrists and shoulders twist softly with the hand and arm, like the game\'s own animations', b.twist !== false, on => set(x => { x.twist = on; })),
    toggleRow('Smooth hip twist', 'Like the game\'s own animations - the thighs twist softly with the legs', b.hipTwist !== false, on => set(x => { x.hipTwist = on; }))));

  if (app.setHair) root.append(hairSection(app, sim, v));
  if (app.tryBody) root.append(otherBodies(app, sim, v));

  // automatic openings
  const o = b.open;
  const live = app.pipeline.lastOpen.get(sim.id) || {};
  const holes = h('div', {});
  for (const [key, info] of Object.entries(HOLES)) {
    if (key === 'vagina' && !(v && v.hasVagina)) continue;
    const now = live[key];
    const state = now && now.open > 0.02 ? `${pct(Math.min(1, now.open))} open${now.by ? ' · ' + now.by : ''}${now.depth > 0.004 ? ` · ${(now.depth * 100).toFixed(1)} cm in` : ''}` : 'closed';
    holes.append(toggleRow(info.label, state, o[key] !== false && o.on, on => set(x => { x.open[key] = on; if (on) x.open.on = true; })));
    if (key === 'mouth' && o.on && o.mouth !== false) holes.append(toggleRow('Lips pull along', 'The lips cling to what is in the mouth: they stretch out as it pulls back and tuck in as it goes in',
      o.lipPull === true, on => set(x => { x.open.lipPull = on; })));
  }
  root.append(section('Holes open by themselves', h('div', { class: 'hint', style: { marginTop: 0 } }, 'When a penis, finger or tongue comes close or goes in, the vagina, anus and mouth open around it - sized to what goes in. Switch one off for animations like kissing the tip, where the mouth should stay closed.'),
    toggleRow('Automatic opening', o.on ? 'On for this sim' : 'Off - holes stay as posed', o.on, on => set(x => { x.open.on = on; })), holes));

  // physics (up to 300%: the top of the sliders jiggles as much as creators bake it)
  const ph = b.physics;
  const sliders = h('div', {});
  for (const [key, part] of Object.entries(PARTS)) {
    if ((key === 'penis' || key === 'balls') && !(v && v.hasPenis)) continue;
    sliders.append(slider({ label: part.label, min: 0, max: PHYSICS_MAX || 2, step: 0.05, value: ph[key] ?? 0, fmt: pct,
      title: 'Above 200% the parts also swing further - as much as creators bake into their animations',
      onStart: () => app.store.checkpoint(), onInput: (val, done) => { ph[key] = val; app.store.setDirty(true); if (done) app.physicsChanged(); } }));
  }
  root.append(section(['Physics', h('span', { class: 'count' }, ph.on ? 'on' : 'off')],
    h('div', { class: 'hint', style: { marginTop: 0 } }, 'Breasts, butt, penis and balls bounce by themselves from how the body moves - no need to animate them. It loops perfectly. Up to 300% for creator-strength jiggle.'),
    toggleRow('Automatic physics', 'Simulated from the motion, baked into the animation', ph.on, on => set(x => { x.physics.on = on; })),
    ph.on ? sliders : null));
}

// ---------------------------------------------------------------- hair
const COLOUR_NAME = { Black: 'Black', DarkBrown: 'Dark brown', Brown: 'Brown', LightBrown: 'Light brown', Blonde: 'Blonde', Auburn: 'Auburn', Red: 'Red', Platinum: 'Platinum' };

function hairSection(app, sim, v) {
  const body = h('div', {}, h('div', { class: 'hint', style: { marginTop: 0 } }, 'Loading hairstyles…'));
  const sec = section(['Hair', h('span', { class: 'count' }, 'preview')], body);
  sec.classList.add('hair-row');
  B.hairPresets().then(pr => {
    body.innerHTML = '';
    const frame = sim.frame === 'ym' ? 'ym' : 'yf';
    const items = (pr.items || []).filter(p => p.frame === frame);
    const styles = [];
    for (const p of items) if (!styles.some(s => s.style === p.style)) styles.push({ style: p.style, label: p.label });
    const cur = sim.hair && sim.hair.name ? items.find(p => p.name === sim.hair.name) : null;
    const trayOwn = sim.tray && (sim.hair === undefined || (sim.hair && sim.hair.casp));
    const none = sim.hair === false || sim.hair === null || (sim.hair === undefined && !sim.tray);
    const chips = h('div', { class: 'chips' });
    chips.append(h('button', { class: 'chipbtn' + (none ? ' on' : ''), onclick: () => app.setHair(sim.id, false) }, 'None'));
    if (sim.tray) chips.append(h('button', { class: 'chipbtn tray' + (trayOwn ? ' on' : ''), title: `${sim.tray.name}'s own hair from the Tray`,
      onclick: () => { app.store.checkpoint(); delete sim.hair; app.store.setDirty(true); B.reloadHair(app, sim.id).then(() => app.renderStep()); app.renderStep(); } }, 'Tray hair'));
    for (const st of styles) {
      chips.append(h('button', { class: 'chipbtn' + (cur && cur.style === st.style ? ' on' : ''), onclick: () => {
        const colour = cur ? cur.colour : 'Brown';
        const pick = items.find(p => p.style === st.style && p.colour === colour) || items.find(p => p.style === st.style);
        if (pick) app.setHair(sim.id, { name: pick.name });
      } }, st.label));
    }
    body.append(chips);
    if (cur) {
      body.append(h('div', { class: 'hair-dots' }, items.filter(p => p.style === cur.style).map(p => h('button', {
        class: p.name === cur.name ? 'active' : '', style: { background: p.swatch }, title: COLOUR_NAME[p.colour] || p.colour,
        onclick: () => app.setHair(sim.id, { name: p.name }) }))));
    }
    const shown = v && v.hairName;
    const note = trayOwn ? (v && v.parts && v.parts.some(m => m.userData.role === 'hair') ? `${sim.tray.name}'s own hair.` : `${sim.tray.name}'s hair is not installed (or still loading) - pick one above.`)
      : none ? 'No hair in the view. Hair is for the preview only - the game dresses the sim itself.' : shown ? 'Preview only - the game dresses the sim itself.' : '';
    if (note) body.append(h('div', { class: 'hair-note' }, note));
  }).catch(() => { body.innerHTML = ''; body.append(h('div', { class: 'hint', style: { marginTop: 0 } }, 'Hairstyles could not be read from the game.')); });
  return sec;
}

// ---------------------------------------------------------------- other bodies
function otherBodies(app, sim, v) {
  const t = B.activeTrial(app, sim.id), opt = t && t.opt;
  const chips = h('div', { class: 'chips' });
  chips.append(h('button', { class: 'chipbtn body-chip' + (!t ? ' on' : ''), onclick: () => app.tryBody(sim.id, { kind: 'own' }) },
    h('span', { class: 'dot' }, (BODY_TYPES[sim.frame] || BODY_TYPES.yf).short), h('span', {}, 'Own body')));
  const more = h('button', { class: 'chipbtn', title: 'Pick any adult sim from your Tray', onclick: () => openTrayDialog(app, {
    title: `Try a Tray sim's body on ${sim.label}`, frame: sim.frame,
    pick: x => app.tryBody(sim.id, { kind: 'tray', tray: x.tray, index: x.index, name: x.name }) }) }, 'More…');
  if (sim.frame !== 'yf_futa') {
    B.traySims().then(list => {
      const mine = list.filter(x => x.frame === sim.frame).slice(0, 8);
      for (const x of mine) {
        const on = opt && opt.kind === 'tray' && opt.tray === x.tray && opt.index === x.index;
        chips.insertBefore(h('button', { class: 'chipbtn body-chip' + (on ? ' on' : ''), title: `${x.name} (${x.household}) - see the animation on this body`,
          onclick: e => { e.currentTarget.classList.add('loading'); app.tryBody(sim.id, { kind: 'tray', tray: x.tray, index: x.index, name: x.name }); } },
          h('img', { src: api.trayThumb(x.simId), alt: '', loading: 'lazy' }), h('span', {}, x.first)), more);
      }
    }).catch(() => {});
    chips.append(more);
  }
  const kids = [h('div', { class: 'hint', style: { marginTop: 0 } }, 'See your animation on other bodies. Your animation doesn\'t change.'), chips];
  if (v && v.hasPenis) {
    const cur = opt && opt.kind === 'size' ? opt.preset : 'average';
    kids.push(h('div', { class: 'size-row' }, h('span', {}, 'Penis'), h('div', { class: 'seg-inline' },
      Object.entries(B.SIZE_PRESETS).map(([k, p]) => h('button', { class: cur === k ? 'on' : '', onclick: () => app.tryBody(sim.id, { kind: 'size', preset: k }) }, p.label)))));
  }
  const cycling = !!(app._cycle && app._cycle.simId === sim.id);
  kids.push(h('div', { class: 'toggle-row' }, h('div', {}, h('b', {}, 'Change body every loop while playing'), h('span', {}, 'Catches hands and contact that only work on one body')),
    toggle(cycling, on => { app.cycleBodies(on, sim.id); if (!on) app.endTrial(sim.id); })));
  const sec = section(['Try it on other bodies', t ? h('span', { class: 'count' }, 'trying') : null], ...kids);
  sec.classList.add('try-bodies');
  return sec;
}

// "Grows over time": soft until one time, fully hard at another, growing and rising in between (erection.js)
function growRow(app, sim, b, set) {
  const p = app.store.project, fps = p.fps || 30, len = p.length;
  const secs = f => +(f / fps).toFixed(2);
  const on = !!(b.grow && b.grow.to > b.grow.from);
  const row = h('div', {}, toggleRow('Grows over time', on ? `Grows from ${secs(b.grow.from)} s, fully hard at ${secs(b.grow.to)} s - small and hanging before, rising as it grows (in the game too)` : 'Starts small and grows until the time you pick',
    on, v => set(x => { if (v) { x.grow = { from: 0, to: Math.min(len - 1, Math.round(2 * fps)) }; x.erect = true; } else delete x.grow; }, 'Erection grows')));
  if (!on) return row;
  const num = (label, key, title) => {
    const input = h('input', { type: 'number', min: 0, max: secs(len - 1), step: 0.1, value: secs(b.grow[key]), title });
    input.onchange = () => {
      const f = Math.max(0, Math.min(len - 1, Math.round((+input.value || 0) * fps)));
      set(x => {
        const g = { ...x.grow, [key]: f };
        if (g.to <= g.from) { if (key === 'from') g.to = Math.min(len - 1, g.from + 1); else g.from = Math.max(0, g.to - 1); }
        x.grow = g;
      }, 'Erection timing');
    };
    return h('label', { class: 'field' }, h('span', {}, label), input);
  };
  row.append(h('div', { class: 'grid-2', style: { marginTop: '6px' } },
    num('Starts growing at (s)', 'from', 'Small and hanging before this time'),
    num('Fully hard at (s)', 'to', 'Hard from this time on'),
    h('button', { class: 'btn small ghost', style: { gridColumn: '1 / -1' }, title: 'Starts growing where the playhead is now',
      onclick: () => set(x => { const f = Math.round(app.store.frame); x.grow = { from: f, to: Math.max(f + 1, Math.min(len - 1, x.grow.to > f ? x.grow.to : f + 2 * fps)) }; }, 'Erection timing') }, 'Start at the playhead'),
    h('button', { class: 'btn small ghost', style: { gridColumn: '1 / -1' }, title: 'Fully hard where the playhead is now',
      onclick: () => set(x => { const f = Math.max(1, Math.round(app.store.frame)); x.grow = { from: Math.min(x.grow.from, f - 1), to: f }; }, 'Erection timing') }, 'Fully hard at the playhead')));
  return row;
}
