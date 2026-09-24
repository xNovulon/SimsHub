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
import { $t } from '../i18n.js';

export function renderBody(app, root) {
  const sim = app.store.sim();
  if (!sim) { root.append(h('div', { class: 'empty' }, $t('steps.body.select_sim_first'))); return; }
  root.append(simTabs(app));
  const b = simBody(sim), v = app.simViews.get(sim.id);
  const set = (fn, label) => app.setBody(sim.id, fn, label);

  const bodySeg = h('div', { class: 'seg-inline' }, Object.entries(BODY_TYPES).map(([k, bt]) =>
    h('button', { class: sim.frame === k ? 'on' : '', onclick: () => app.setSimBody(sim.id, k) }, bt.label)));
  root.append(section($t('steps.body.body'), bodySeg,
    v && v.hasPenis ? toggleRow($t('steps.body.erection'), $t('steps.body.hard_or_soft_penis_wickedwhims'), b.erect, on => set(x => { x.erect = on; })) : null,
    toggleRow($t('steps.body.tongue'), $t('steps.body.wickedwhims_tongue_inside_mouth_for'), b.tongue, on => set(x => { x.tongue = on; })),
    // the twist helpers follow the hand, arm and leg by themselves (a missing setting means on / off as below)
    toggleRow($t('steps.body.smooth_wrists_and_shoulders'), $t('steps.body.wrists_and_shoulders_twist_softly'), b.twist !== false, on => set(x => { x.twist = on; })),
    toggleRow($t('steps.body.smooth_hip_twist'), $t('steps.body.like_game_s_own_animations'), b.hipTwist !== false, on => set(x => { x.hipTwist = on; }))));

  if (app.setHair) root.append(hairSection(app, sim, v));
  if (app.tryBody) root.append(otherBodies(app, sim, v));

  // automatic openings
  const o = b.open;
  const live = app.pipeline.lastOpen.get(sim.id) || {};
  const holes = h('div', {});
  for (const [key, info] of Object.entries(HOLES)) {
    if (key === 'vagina' && !(v && v.hasVagina)) continue;
    const now = live[key];
    const state = now && now.open > 0.02 ? $t('steps.body.pct_open', { pct: pct(Math.min(1, now.open)) }) + (now.by ? ' · ' + now.by : '') + (now.depth > 0.004 ? $t('steps.body.cm_in', { depth: (now.depth * 100).toFixed(1) }) : '') : $t('steps.body.closed');
    holes.append(toggleRow(info.label, state, o[key] !== false && o.on, on => set(x => { x.open[key] = on; if (on) x.open.on = true; })));
  }
  root.append(section($t('steps.body.holes_open_by_themselves'), h('div', { class: 'hint', style: { marginTop: 0 } }, $t('steps.body.when_penis_finger_or_tongue')),
    toggleRow($t('steps.body.automatic_opening'), o.on ? $t('steps.body.on_for_this_sim') : $t('steps.body.off_holes_stay_as_posed'), o.on, on => set(x => { x.open.on = on; })), holes));

  // physics (up to 300%: the top of the sliders jiggles as much as creators bake it)
  const ph = b.physics;
  const sliders = h('div', {});
  for (const [key, part] of Object.entries(PARTS)) {
    if ((key === 'penis' || key === 'balls') && !(v && v.hasPenis)) continue;
    sliders.append(slider({ label: part.label, min: 0, max: PHYSICS_MAX || 2, step: 0.05, value: ph[key] ?? 0, fmt: pct,
      title: $t('steps.body.above_200_parts_also_swing'),
      onStart: () => app.store.checkpoint(), onInput: (val, done) => { ph[key] = val; app.store.setDirty(true); if (done) app.physicsChanged(); } }));
  }
  root.append(section([$t('steps.body.physics'), h('span', { class: 'count' }, ph.on ? 'on' : 'off')],
    h('div', { class: 'hint', style: { marginTop: 0 } }, $t('steps.body.breasts_butt_penis_and_balls')),
    toggleRow($t('steps.body.automatic_physics'), $t('steps.body.simulated_from_motion_baked_into'), ph.on, on => set(x => { x.physics.on = on; })),
    ph.on ? sliders : null));
}

// ---------------------------------------------------------------- hair
const COLOUR_NAME = { Black: 'Black', DarkBrown: $t('steps.body.dark_brown'), Brown: 'Brown', LightBrown: $t('steps.body.light_brown'), Blonde: 'Blonde', Auburn: 'Auburn', Red: 'Red', Platinum: 'Platinum' };

function hairSection(app, sim, v) {
  const body = h('div', {}, h('div', { class: 'hint', style: { marginTop: 0 } }, $t('steps.body.loading_hairstyles')));
  const sec = section([$t('steps.body.hair'), h('span', { class: 'count' }, 'preview')], body);
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
    chips.append(h('button', { class: 'chipbtn' + (none ? ' on' : ''), onclick: () => app.setHair(sim.id, false) }, $t('steps.body.none')));
    if (sim.tray) chips.append(h('button', { class: 'chipbtn tray' + (trayOwn ? ' on' : ''), title: $t('steps.body.s_own_hair_from_tray', { trayName: sim.tray.name }),
      onclick: () => { app.store.checkpoint(); delete sim.hair; app.store.setDirty(true); B.reloadHair(app, sim.id).then(() => app.renderStep()); app.renderStep(); } }, $t('steps.body.tray_hair')));
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
<<<<<<< ours
    const note = trayOwn ? (v && v.parts && v.parts.some(m => m.userData.role === 'hair') ? `${sim.tray.name}'s own hair.` : `${sim.tray.name}'s hair is not installed (or still loading) - pick one above.`)
      : none ? 'No hair in the view. Hair is for the preview only - the game dresses the sim itself.' : shown ? 'Preview only - the game dresses the sim itself.' : '';
=======
    const note = trayOwn ? (v && v.parts && v.parts.length ? $t('steps.body.s_own_hair', { trayName: sim.tray.name }) : $t('steps.body.s_hair_is_not_installed', { trayName: sim.tray.name }))
      : none ? $t('steps.body.no_hair_in_view_hair') : shown ? $t('steps.body.preview_only_game_dresses_sim') : '';
>>>>>>> theirs
    if (note) body.append(h('div', { class: 'hair-note' }, note));
  }).catch(() => { body.innerHTML = ''; body.append(h('div', { class: 'hint', style: { marginTop: 0 } }, $t('steps.body.hairstyles_could_not_be_read'))); });
  return sec;
}

// ---------------------------------------------------------------- other bodies
function otherBodies(app, sim, v) {
  const t = B.activeTrial(app, sim.id), opt = t && t.opt;
  const chips = h('div', { class: 'chips' });
  chips.append(h('button', { class: 'chipbtn body-chip' + (!t ? ' on' : ''), onclick: () => app.tryBody(sim.id, { kind: 'own' }) },
    h('span', { class: 'dot' }, (BODY_TYPES[sim.frame] || BODY_TYPES.yf).short), h('span', {}, $t('steps.body.own_body'))));
  const more = h('button', { class: 'chipbtn', title: $t('steps.body.pick_any_adult_sim_from'), onclick: () => openTrayDialog(app, {
    title: $t('steps.body.try_tray_sim_s_body', { simLabel: sim.label }), frame: sim.frame,
    pick: x => app.tryBody(sim.id, { kind: 'tray', tray: x.tray, index: x.index, name: x.name }) }) }, $t('steps.body.more'));
  if (sim.frame !== 'yf_futa') {
    B.traySims().then(list => {
      const mine = list.filter(x => x.frame === sim.frame).slice(0, 8);
      for (const x of mine) {
        const on = opt && opt.kind === 'tray' && opt.tray === x.tray && opt.index === x.index;
        chips.insertBefore(h('button', { class: 'chipbtn body-chip' + (on ? ' on' : ''), title: $t('steps.body.see_animation_on_this_body', { xName: x.name, household: x.household }),
          onclick: e => { e.currentTarget.classList.add('loading'); app.tryBody(sim.id, { kind: 'tray', tray: x.tray, index: x.index, name: x.name }); } },
          h('img', { src: api.trayThumb(x.simId), alt: '', loading: 'lazy' }), h('span', {}, x.first)), more);
      }
    }).catch(() => {});
    chips.append(more);
  }
  const kids = [h('div', { class: 'hint', style: { marginTop: 0 } }, $t('steps.body.see_your_animation_on_other')), chips];
  if (v && v.hasPenis) {
    const cur = opt && opt.kind === 'size' ? opt.preset : 'average';
    kids.push(h('div', { class: 'size-row' }, h('span', {}, $t('steps.body.penis')), h('div', { class: 'seg-inline' },
      Object.entries(B.SIZE_PRESETS).map(([k, p]) => h('button', { class: cur === k ? 'on' : '', onclick: () => app.tryBody(sim.id, { kind: 'size', preset: k }) }, p.label)))));
  }
  const cycling = !!(app._cycle && app._cycle.simId === sim.id);
  kids.push(h('div', { class: 'toggle-row' }, h('div', {}, h('b', {}, $t('steps.body.change_body_every_loop_while')), h('span', {}, $t('steps.body.catches_hands_and_contact_that'))),
    toggle(cycling, on => { app.cycleBodies(on, sim.id); if (!on) app.endTrial(sim.id); })));
  const sec = section([$t('steps.body.try_it_on_other_bodies'), t ? h('span', { class: 'count' }, 'trying') : null], ...kids);
  sec.classList.add('try-bodies');
  return sec;
}
