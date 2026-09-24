// "This frame": the key here (its timing, main or in-between, soften / exaggerate, hold), a face-only key, or the
// in-between slider. Above it, when several keys are selected on the timeline, the selection card (spec_editing 8.1).
import { h, icon, slider, section, toast } from '../ui.js';
import { EASE_INFO, EASE_CURVE, EASES, easeFn, validCurve } from '../animation.js';
import * as KO from '../keyops.js';

// A small picture of a custom timing curve.
function curvePreview(key) {
  const c = h('canvas', { class: 'curve-mini', width: 120, height: 80 });
  const g = c.getContext('2d'), f = easeFn(key);
  g.scale(2, 2);
  g.strokeStyle = 'rgba(255,255,255,.15)'; g.strokeRect(4.5, 4.5, 51, 31);
  g.beginPath();
  for (let i = 0; i <= 40; i++) { const t = i / 40, v = f(t); const x = 5 + t * 50, y = 35 - v * 30; if (!i) g.moveTo(x, y); else g.lineTo(x, y); }
  g.strokeStyle = '#ff8cc4'; g.lineWidth = 1.6; g.stroke();
  return c;
}

// The timing list: every timing, plus "Custom curve..." (opens the timing editor).
function easeSelect(app, current, onPick, onCustom, mixed = false) {
  const sel = h('select', {}, [
    mixed ? h('option', { value: '', selected: true, disabled: true }, 'Mixed') : null,
    ...Object.entries(EASE_INFO).map(([v, [t]]) => h('option', { value: v, selected: !mixed && current === v }, v === 'custom' ? 'Custom curve…' : t))].filter(Boolean));
  sel.onchange = () => { const v = sel.value; sel.blur(); if (v === 'custom') onCustom(sel); else onPick(v); };
  return sel;
}

// Several keys selected: what they are, one timing for all, and the tools.
function selectionCard(app) {
  const r = KO.readSel(app.store.project, app.timeline.sel);
  const n = r.keys.length;
  if (n + r.sounds.length < 2) return null;
  const fps = app.store.project.fps || 30;
  const eases = new Set(r.keys.map(x => x.key.ease || 'auto'));
  const cur = eases.size === 1 ? [...eases][0] : null;
  const btn = (ic, text, fn, title) => h('button', { class: 'btn small', title: title || null, onclick: fn }, icon(ic), text);
  const card = h('div', { class: 'card sel-card' },
    h('div', { class: 'sel-head' }, h('b', {}, `${n} key${n === 1 ? '' : 's'}${r.sims.size ? ` on ${r.sims.size} sim${r.sims.size === 1 ? '' : 's'}` : ''}`),
      h('small', {}, `${(r.min / fps).toFixed(2)}-${(r.max / fps).toFixed(2)} s${r.sounds.length ? ` · ${r.sounds.length} sound${r.sounds.length === 1 ? '' : 's'}` : ''}`)),
    n ? h('label', { class: 'field', style: { marginTop: 0 } }, h('span', {}, 'Timing into the next key (all of them)'),
      easeSelect(app, cur, v => app.setEaseForSelection(v), el => {
        const k = r.keys[0];
        app.setEaseForSelection('custom', validCurve(k.key.curve) ? k.key.curve : EASE_CURVE[k.key.ease || 'auto']);
        const b = el.getBoundingClientRect();
        app.timingEditor(k.sim.id, k.key.frame, b.left - 240, b.top - 120);
      }, !cur)) : null,
    h('div', { class: 'btn-grid' },
      btn('motion', 'Smooth', () => app.smoothSelection(0.5), 'Take out small shakes between these keys'),
      btn('key', 'Simplify', () => app.simplifySelection(1.5), 'Fewer keys - the motion stays within 1.5°'),
      btn('mirror', 'Mirror', () => app.mirrorSelectedKeys(), 'Left and right swap on these keys'),
      btn('turn', 'Reverse', () => app.reverseSelectedKeys(), 'Play them backwards'),
      btn('copy', 'Copy', () => app.copySelectedKeys(), 'Ctrl+C over the timeline'),
      btn('trash', 'Delete', () => app.deleteSelectedKeys(), 'Delete over the timeline'),
      btn('key', 'In-between keys', () => app.setKeyType('breakdown'), 'Mark them as in-between keys (drawn smaller)'),
      btn('play', 'Play only this part', () => app.playSelection(), 'P - plays just this stretch, over and over')),
    h('div', { class: 'hint', style: { marginBottom: 0 } }, 'Drag one of them to move them all · Alt+drag stretches them from the playhead · Ctrl+D duplicates to the playhead.'));
  return card;
}

export function keySection(app, sim) {
  const f = Math.round(app.store.frame);
  const key = sim.keys.find(k => k.frame === f);
  const p = app.store.project, fps = p.fps || 30;
  const sec = section(['This frame', h('span', { class: 'count' }, `${f} · ${(f / fps).toFixed(2)} s`)]);
  const sc = app.timeline ? selectionCard(app) : null;
  if (sc) sec.append(sc);
  const easeSel = () => easeSelect(app, key.ease || 'auto', v => app.setEase(sim.id, f, v), el => {
    app.setEase(sim.id, f, 'custom');
    const b = el.getBoundingClientRect();
    app.timingEditor(sim.id, f, b.left - 240, b.top - 120);
  });
  if (key && key.faceOnly) {
    // a face key where the body has no key: it never changes the body's motion
    const info = EASE_INFO[key.ease || 'auto'] || EASE_INFO.auto;
    sec.append(h('div', { class: 'card face-key-card' },
      h('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' } }, h('span', { class: 'ease-dot face' }), h('b', {}, 'Face key here'),
        h('button', { class: 'icon-btn sm', style: { marginLeft: 'auto' }, title: 'Delete this face key', onclick: () => app.deleteKey(sim.id) }, icon('trash'))),
      h('label', { class: 'field', style: { margin: 0 } }, h('span', {}, 'Into the next face key'), easeSel()),
      h('div', { class: 'hint' }, info[1]),
      h('button', { class: 'btn soft block', onclick: () => app.keyPose(sim.id, { body: true }) }, icon('key'), 'Key the body here too')));
  } else if (key) {
    const info = key.ease === 'custom' ? EASE_INFO.custom : (EASE_INFO[key.ease || 'auto'] || EASE_INFO.auto);
    const nb = KO.neighbours(p, sim, f, { exclude: key });
    const tween = key.type === 'breakdown';
    const card = h('div', { class: 'card' },
      h('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' } }, h('span', { class: 'ease-dot', style: { background: info[2] } }),
        h('b', {}, tween ? 'In-between key here' : 'Key here'),
        h('button', { class: 'icon-btn sm', style: { marginLeft: 'auto' }, title: 'Delete this key', onclick: () => app.deleteKey(sim.id) }, icon('trash'))),
      h('label', { class: 'field', style: { margin: 0 } }, h('span', {}, 'Into the next key'), easeSel()),
      key.ease === 'custom' ? h('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', marginTop: '6px' } }, curvePreview(key),
        h('button', { class: 'btn small', onclick: e => { const b = e.currentTarget.getBoundingClientRect(); app.timingEditor(sim.id, f, b.left - 240, b.top - 140); } }, 'Change the curve…')) : null,
      h('div', { class: 'hint', style: { marginBottom: 0 } }, info[1]),
      // main or in-between key
      h('div', { class: 'seg-inline key-type', title: 'In-between keys are drawn smaller - the poses between your main poses (Blender\'s breakdowns)' },
        h('button', { class: tween ? '' : 'on', onclick: () => tween && app.setKeyType(null, [KO.kid(sim.id, f)]) }, 'Main key'),
        h('button', { class: tween ? 'on' : '', onclick: () => !tween && app.setKeyType('breakdown', [KO.kid(sim.id, f)]) }, 'In-between key')),
      // soften <-> exaggerate, when there are keys on both sides
      nb.prev && nb.next && nb.prev !== nb.next ? slider({ label: 'Soften ↔ Exaggerate', min: -1, max: 1, step: 0.01, value: 0, fmt: v => (v > 0 ? '+' : '') + Math.round(v * 100) + '%',
        title: 'Push this pose further from the keys around it (exaggerate), or pull it toward them (soften)',
        onStart: () => { app._push = null; }, onInput: (v, done) => app.pushKeys(v, done) }) : null,
      h('div', { class: 'field', style: { margin: '8px 0 0' } }, h('span', {}, 'Hold this pose'),
        h('div', { class: 'hold-row' }, [[0.25, '¼ s'], [0.5, '½ s'], [1, '1 s']].map(([s, t]) => h('button', { class: 'chipbtn', title: `The pose stays (drifting a little) for ${t}`, onclick: () => app.holdPose(sim.id, f, s) }, t)))));
    sec.append(card);
  } else {
    const body = sim.keys.filter(k => !k.faceOnly);
    const prev = [...body].reverse().find(k => k.frame < f), next = body.find(k => k.frame > f);
    sec.append(h('div', { class: 'card' },
      h('div', { class: 'hint', style: { marginTop: 0 } }, body.length ? 'Between keys - what you see is filled in for you.' : 'No keys yet.'),
      h('button', { class: 'btn soft block', onclick: () => app.keyPose(sim.id) }, icon('key'), 'Key this pose here'),
      prev && next ? slider({ label: 'In-between: ← previous · next →', min: -0.25, max: 1.25, step: 0.01, value: 0.5, fmt: v => Math.round(v * 100) + '%',
        title: 'Blend the pose between the keys around it (past the ends exaggerates)',
        onStart: () => app.store.checkpoint('In-between key'), onInput: (v, done) => app.tween(sim.id, v, done) }) : null,
      prev && next ? h('div', { class: 'tween-chips', title: 'An in-between key at once (Shift+E: halfway)' },
        [[0.25, '¼'], [0.5, '½'], [0.75, '¾'], [1.15, 'Overshoot']].map(([t, lab]) => h('button', { class: 'chipbtn', onclick: () => app.insertInBetween([sim.id], t) }, lab))) : null));
  }
  // the loop: at the first or last frame, a problem at the loop point is explained here
  if (p.loop && (f === 0 || f === p.length - 1 || (key && key === sim.keys.filter(k => !k.faceOnly).slice(-1)[0]))) {
    const st = (app.loopStatus ? app.loopStatus() : []).find(x => x.simId === sim.id);
    if (st && ['pause', 'snap', 'pop'].includes(st.kind)) {
      sec.append(h('div', { class: 'card loop-card' }, h('b', {}, 'The loop'), h('div', { class: 'hint', style: { marginTop: 4 } }, `${sim.label}: ${KO.LOOP_TEXT[st.kind]}.`),
        h('button', { class: 'btn small soft block', onclick: () => app.fixLoops() }, icon('spark'), 'Fix it')));
    }
  }
  void EASES; void toast;
  return sec;
}
