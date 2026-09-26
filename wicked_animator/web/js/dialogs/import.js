// Import a library animation as keys you can change - the body where it needs keys ("Smart": every frame, then only
// the keys the motion needs) or every few frames, and the creator's face (blinks included) wherever it changes.
import * as THREE from 'three';
import { h, modal, toast, choiceBar } from '../ui.js';
import { newSim } from '../state.js';
import { sampleToPose, sortKeys } from '../animation.js';
import { sampleToFaceBones, keyFramesFor, sparseFaceBones } from '../facekit.js';
import * as KO from '../keyops.js';

const select = (options, value) => h('select', {}, options.map(([v, t]) => h('option', { value: v, selected: v === value }, t)));

export function openImportDialog(app, preview) {
  const total = preview.length;
  const every = select([['smart', 'Smart - keys only where needed (recommended)'], ['3', 'Every 3 frames (very detailed)'], ['6', 'Every 6 frames'], ['10', 'Every 10 frames'], ['15', 'Every 15 frames (simple)']], 'smart');
  const smooth = h('input', { type: 'checkbox' });
  const start = h('input', { class: 'text', type: 'number', min: 0, step: 0.5, value: 0 });
  const dur = h('input', { class: 'text', type: 'number', min: 0.5, step: 0.5, value: Math.min(total / 30, 10).toFixed(1) });
  const replace = h('input', { type: 'checkbox', checked: true });
  modal({
    title: 'Import as keys',
    text: `${preview.anim.name} by ${preview.anim.author} · ${(total / 30).toFixed(1)} s, ${preview.anim.actors.length} sims. Keys you can then change.`,
    body: h('div', {},
      h('div', { class: 'grid-2' },
        h('label', { class: 'field' }, h('span', {}, 'Key spacing'), every),
        h('label', { class: 'field' }, h('span', {}, 'Start at (seconds)'), start),
        h('label', { class: 'field' }, h('span', {}, 'Length (seconds)'), dur)),
      h('label', { class: 'check' }, replace, 'Replace my sims with this animation\'s sims'),
      h('label', { class: 'check', title: 'Takes out small shakes (captured or hand-shaky motion) before the keys are chosen' }, smooth, 'Smooth out small shakes')),
    buttons: [
      { label: 'Cancel', kind: 'ghost' },
      { label: 'Import', kind: 'primary', onClick: () => importKeys(app, preview, every.value === 'smart' ? 'smart' : +every.value, Math.round(+start.value * 30), Math.round(+dur.value * 30), replace.checked, { smooth: smooth.checked }) },
    ],
  });
}

// Does the clip open and close the eyelids (a blink, eyes shutting)? More than 10 degrees over the take.
function lidsMove(faces) {
  const qa = new THREE.Quaternion(), qb = new THREE.Quaternion();
  for (const n of ['b__L_UpLid__', 'b__R_UpLid__']) {
    const qs = faces.map(fb => fb.rot && fb.rot[n]).filter(Boolean);
    if (qs.length < 2) continue;
    qa.fromArray(qs[0]);
    for (const q of qs) if (qa.angleTo(qb.fromArray(q)) > THREE.MathUtils.degToRad(10)) return true;
  }
  return false;
}

export function importKeys(app, preview, every, from, length, replace, { smooth = false } = {}) {
  const smart = every === 'smart';
  if (smart) every = 1;
  const anim = preview.anim;
  from = Math.max(0, Math.min(from, preview.length - 2));
  length = Math.max(10, Math.min(length, preview.length - from));
  app.store.checkpoint('Import as keys');
  const p = app.store.project;
  if (replace) p.sims = [];
  const made = [];
  anim.clips.forEach((clip, k) => {
    const frame = anim.actors[k].gender === 'MALE' ? 'ym' : 'yf';
    const s = newSim(p, frame);
    s.gender = anim.actors[k].gender;
    const player = preview.players[k];
    let keys = [];
    for (let f = 0; f < length; f += every) keys.push({ frame: f, ease: 'auto', pose: sampleToPose(player.sample(from + f)) });
    if (keys[keys.length - 1].frame !== length - 1) keys.push({ frame: length - 1, ease: 'auto', pose: sampleToPose(player.sample(from + length - 1)) });
    // Smart: every frame first, then only the keys the motion needs (within 1 degree); shakes smoothed first if asked
    if (smooth) KO.smoothKeys(keys, { strength: 0.3, length, loop: true });
    if (smart) keys = KO.simplifyKeys(keys, { tolDeg: 1, tolMm: 1.5, length, loop: true, curve: p.autoCurve || 'legacy' }).keys;
    // the face channel: face keys wherever the creator's face changes (a 7-frame blink is kept), few where it is still
    const faces = [];
    for (let f = 0; f < length; f++) faces.push(sampleToFaceBones(player.sample(from + f), { dense: true }));
    if (faces.some(fb => Object.keys(fb.rot).length || Object.keys(fb.pos).length)) {
      const at = keyFramesFor(faces, null, true, { angle: THREE.MathUtils.degToRad(0.5), pos: 0.0003 });
      for (const f of at) {
        let key = keys.find(x => x.frame === f);
        if (!key) { key = { frame: f, ease: 'linear', faceOnly: true, pose: sampleToPose(player.sample(from + f)) }; keys.push(key); }
        key.faceBones = sparseFaceBones(faces[f]);
      }
      sortKeys(keys);
      // the creator's own blinks are kept: the automatic blinking stays off, so the eyes never blink twice
      if (lidsMove(faces)) s.body = { ...(s.body || {}), blink: false };
    }
    s.keys = keys;
    p.sims.push(s);
    made.push({ sim: s, player, from, length, keys });
  });
  p.length = length;
  p.fitLength = false;             // sample-derived - Fit to keys never moves it
  p.loop = true;
  p.name = anim.name + ' (my version)';
  p.category = anim.category || p.category;
  p.tags = [...(anim.tags || [])];
  p.locations = anim.locations.length ? [...anim.locations] : p.locations;
  const f = app.furniture.find(x => x.locations.some(l => p.locations.includes(l)));
  if (f) p.furniture = f.id;
  for (const m of made) app.runHook && app.runHook('imported', m);
  app.store.selected = { sim: p.sims[0].id, bone: null };
  app.library.stopPreview();
  app.store.frame = 0;
  app._lastPreset = null;
  app.refreshAll();
  app.timeline.fit();
  app.physicsChanged();
  app.frameSims();
  const nKeys = p.sims.map(s => s.keys.filter(k => !k.faceOnly).length);
  toast(smart ? `Imported ${anim.clips.length} sims - ${nKeys.join(' and ')} keys, only where the motion needs them.` : `Imported ${anim.clips.length} sims with keys every ${every} frames.`, 'ok');
  // a part of a clip often doesn't loop cleanly: offer to blend the end into the start
  const pop = KO.loopCheck(p).filter(r => r.kind === 'pop');
  if (pop.length) {
    choiceBar("This part doesn't loop smoothly - the end jumps back to the start.", [
      { label: 'Blend the end into the start', primary: true, onClick: () => {
        app.store.checkpoint('Blend the end into the start');
        for (const r of pop) { const s = p.sims.find(x => x.id === r.simId); if (s) KO.fixLoop(p, s, 'pop'); }
        app.keysChanged(); app.afterEdit();
        toast('The end now flows back into the start.', 'ok');
      } },
    ], { timeout: 16000 });
  }
}
