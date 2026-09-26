// Scene tools (R2-3): see-through, bones like Blender, the clipping check, seat and lying spots in the Place tool,
// trying the animation on other bodies, and hair. Everything plugs in through app.hooks (plan 2.4), ui.addIcon and
// ui.addToolbarButton - main.js, index.html and app.css stay as they are.
import * as THREE from 'three';
import { h, icon, toast, addIcon, addToolbarButton, section } from '../ui.js';
import { Xray } from '../xray.js';
import { checkClipping, scanClipping, capsulesOf, capsuleNow } from '../clipcheck.js';
import { slotMarkers } from '../furniture.js';
import { spotsOf, sitOn, lieOn, surfaceY } from '../placing.js';
import * as B from '../bodies.js';
import { label as boneLabel, isFace } from '../facekit.js';
import { renderInspector } from '../inspector.js';

const ICONS = {
  // an eye with a dashed outline
  xray: '<path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-dasharray="3 2.2" stroke-linejoin="round"/><circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" stroke-width="1.8"/>',
  // two octahedral bones
  bones: '<path d="M5 20l2.2-6.4L9.4 14 5 20zM7.2 13.6l1.5-.9 1.5 1.2-.8 .1zM7.2 13.6L12 4l-1.8 10.1" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M13 20l3-5.5 1.6 1.3L13 20zM16 14.5l1.4-.5 1.2 1-.9.8zM16 14.5L20 7l-1.4 8" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="12" cy="4" r="1.3" fill="currentColor"/><circle cx="20" cy="7" r="1.3" fill="currentColor"/>',
  // two circles overlapping, with a spark
  clip: '<circle cx="9" cy="13" r="5.5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="15" cy="13" r="5.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M18 2.5v3M16.5 4h3M20.5 6.5l1.5 1.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
  seat: '<path d="M5 11V6a2 2 0 012-2h10a2 2 0 012 2v5M3 11h18v5H3zM5 16v3M19 16v3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>',
  hair: '<path d="M5 20c-1-6 0-14 7-15 7 1 8 9 7 15M8 19c0-4 1-8 4-10 3 2 4 6 4 10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
};
const RED = '#fb5471';

export function install(app) {
  if (!app || app.__scene) return;
  app.__scene = true;
  const hooks = app.hooks || {};
  const add = (name, fn) => {
    let t = hooks;
    const parts = name.split('.');
    for (const p of parts.slice(0, -1)) t = t && t[p];
    if (t && Array.isArray(t[parts[parts.length - 1]])) t[parts[parts.length - 1]].push(fn);
  };
  for (const [id, svg] of Object.entries(ICONS)) addIcon(id, svg);

  // ---------------------------------------------------------------- see-through and bones
  const xray = app.xray = new Xray(app);
  const btnSee = addToolbarButton({ cell: 'view', id: 'btn-xray', icon: 'xray', toggle: true,
    title: 'See-through: see hands and contact behind bodies (Alt+Z)', onClick: (e, b) => setSee(b.classList.contains('on')) });
  const btnBones = addToolbarButton({ cell: 'view', id: 'btn-bones', icon: 'bones', toggle: true,
    title: 'Show bones, like Blender (Alt+B)', onClick: (e, b) => setBones(b.classList.contains('on')) });
  const btnClip = addToolbarButton({ cell: 'view', id: 'btn-clip', icon: 'clip',
    title: 'Check clipping: find hands and legs that go through a body', onClick: () => app.checkClipping() });
  function setSee(on) {
    xray.setSeeThrough(on);
    if (btnSee) btnSee.classList.toggle('on', on);
    toast(on ? 'See-through on - the other sims are see-through.' : 'See-through off.');
  }
  function setBones(on) {
    xray.setBones(on);
    if (btnBones) btnBones.classList.toggle('on', on);
    toast(on ? 'Bones on - click a bone to pick that part.' : 'Bones off.');
  }
  app.setSeeThrough = on => setSee(on === undefined ? !xray.seeOn : !!on);
  app.setShowBones = on => setBones(on === undefined ? !xray.bonesOn : !!on);

  add('keys', (e, info) => {
    if (!info.alt || info.ctrl) return false;
    if (info.code === 'KeyZ') { setSee(!xray.seeOn); return true; }
    if (info.code === 'KeyB') { setBones(!xray.bonesOn); return true; }
    return false;
  });
  add('selection', () => { if (xray.seeOn) xray.applySee(); if (xray.bonesOn) xray.update(); });
  add('viewsSynced', () => { if (xray.seeOn) xray.applySee(); if (xray.bonesOn) xray.syncViews(); });
  add('furnitureBuilt', () => { if (xray.seeOn) xray.applySee(); slots.refresh(true); });

  // ---------------------------------------------------------------- the Place tool's spots
  const slots = { group: null, key: '', hot: null, t0: 0, info: null, token: 0 };
  const dropMarkers = () => {
    if (slots.group) { slots.group.traverse(o => { o.geometry?.dispose(); o.material?.dispose(); }); slots.group.removeFromParent(); slots.group = null; }
  };
  slots.refresh = (force = false) => {
    const I = app.interact, id = app.store.project.furniture;
    const want = I && I.tool === 'move' && id && id !== 'floor';
    const key = want ? id : '';
    if (!force && key === slots.key) return;
    slots.key = key;
    const token = ++slots.token;                      // only the latest call puts markers up
    dropMarkers();
    slots.hot = null; slots.info = null;
    if (!want) return;
    app._furnitureInfo(id).then(info => {
      if (token !== slots.token || slots.key !== key || !info) return;
      dropMarkers();
      const list = spotsOf(info);
      if (!list.length) return;
      slots.info = info;
      slots.group = slotMarkers(list.map(x => x.slot));
      slots.group.children.forEach((m, i) => { m.userData.spot = list[i]; });
      app.vp.overlay.add(slots.group);
      renderInspectorSoon();
    });
  };
  const pickSpot = e => {
    if (!slots.group) return null;
    const hit = app.vp.pick(e, [slots.group]);
    if (!hit) return null;
    // a sim in front of the spot (a leg, a foot over it) is picked instead: the spot only takes the click on its own
    const body = app.interact && app.interact._meshes ? app.vp.pick(e, app.interact._meshes()) : null;
    if (body && body.distance < hit.distance) return null;
    let o = hit.object;
    while (o && !o.userData.spot) o = o.parent;
    return o || null;
  };
  // the sim a spot click is for: the selected sim, else the one under the mouse, else the first
  const spotSim = () => app.store.sim() || app.store.project.sims[0] || null;
  const doSpot = spot => {
    const s = spotSim();
    if (!s || !spot) return;
    if (spot.action === 'lie') app.lieHere(s.id, spot.slot, spot);
    else app.sitHere(s.id, spot.slot, spot);
  };
  let tool = null;
  add('tick', (dt, frame, { wrapped }) => {
    const t = app.interact && app.interact.tool;
    if (t !== tool) { tool = t; slots.refresh(); renderInspectorSoon(); }
    if (xray.bonesOn) xray.update();
    // the hovered spot breathes (1 -> 1.12, 1.2 s)
    if (slots.group) {
      const now = performance.now();
      for (const m of slots.group.children) {
        const k = m === slots.hot && !reduced() ? 1 + 0.06 * (1 - Math.cos((now - slots.t0) / 1200 * Math.PI * 2)) : 1;
        m.scale.setScalar(k);
      }
    }
    B.onTick(app, wrapped);
  });
  let inspT = 0;
  function renderInspectorSoon() {
    clearTimeout(inspT);
    inspT = setTimeout(() => { try { renderInspector(app); } catch (e) { console.error(e); } }, 30);
  }

  // hover: the spot and the bone under the mouse (after the app's own hover, so its words win)
  const canvas = app.vp.canvas;
  canvas.addEventListener('pointermove', e => {
    if (app.vp.dragging || app.vp.controls.busy) return;
    const spot = pickSpot(e);
    if (spot !== slots.hot) { slots.hot = spot; slots.t0 = performance.now(); }
    if (spot) {
      const s = spotSim(), sp = spot.userData.spot;
      canvas.style.cursor = 'pointer';
      app.hud(`${sp.label} · click: ${sp.verb} ${s ? s.label : ''} here${sp.kind === 'seat' || sp.kind === 'edge' ? ' (feet on the floor)' : ''}`);
      return;
    }
    if (xray.bonesOn) {
      const hb = xray.pick(e);
      xray.setHot(hb);
      if (hb) {
        const s = app.store.sim(hb.simId);
        canvas.style.cursor = 'pointer';
        app.hud(`${s ? s.label + ' · ' : ''}${boneLabel(hb.bone, s && s.frame)} · ${hb.bone} · click to pick it`);
      }
    }
  });

  // clicks: spots and bones come before the bodies (interact.pickers when the app has them, else first on the canvas)
  // kind: 'click' (act), 'hover' (say it is ours, so the body under it does not glow), 'down' (nothing to do)
  const picker = (e, kind = 'click') => {
    if (kind === 'down') return false;
    const spot = pickSpot(e);
    const hb = !spot && xray.bonesOn ? xray.pick(e) : null;
    if (kind === 'hover') return !!(spot || hb);
    if (spot) { doSpot(spot.userData.spot); return true; }
    if (hb) { selectBone(hb.simId, hb.bone); return true; }
    return false;
  };
  const I = app.interact;
  if (I && Array.isArray(I.pickers)) I.pickers.push(picker);
  else {
    let down = null;
    canvas.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; }, true);
    canvas.addEventListener('pointerup', e => {
      if (!down || e.button !== 0 || app.vp.dragging) { down = null; return; }
      const moved = Math.hypot(e.clientX - down[0], e.clientY - down[1]);
      down = null;
      if (moved >= 5) return;
      if (picker(e)) { e.stopImmediatePropagation(); if (app.interact) app.interact.downAt = null; }
    }, true);
  }
  function selectBone(simId, bone) {
    const I = app.interact;
    if (!I) return;
    if (I.tool === 'move') { app.selectSim(simId); return; }
    if (I.tool !== 'rotate' && I.tool !== 'face') app.setTool('rotate');
    app.store.selected = { sim: simId, bone };
    if (isFace(bone) && I.selectFaceBone) I.selectFaceBone(simId, bone); else I.selectBone(simId, bone);
    app.emitSelection();
  }

  // "Sit here" / "Lie here" (spec_bodies 3.7): every key, a pending pose and the pins move together
  app.sitHere = (simId, slot, spot = null) => {
    const sim = app.store.sim(simId);
    if (!sim || !slot) return false;
    app.store.checkpoint();
    if (app.playing) app.setPlaying(false);
    if (!sitOn(app, sim, slot)) return false;
    after();
    const where = spot ? spot.label.toLowerCase() : 'the seat';
    toast(slot.kind === 'in' ? `${sim.label} sits up in bed.`
      : `${sim.label} sits on ${/^edge/.test(where) ? 'the edge' : where} - the feet are pinned on the floor spots, so the knees bend by themselves.`, 'ok');
    return true;
  };
  app.lieHere = (simId, slot, spot = null) => {
    const sim = app.store.sim(simId);
    if (!sim || !slot) return Promise.resolve(false);
    app.store.checkpoint();
    if (app.playing) app.setPlaying(false);
    const id = app.store.project.furniture;
    return app._furnitureInfo(id).then(info => lieOn(app, sim, slot, info || { surface_height: slot.pos[1] })).then(ok => {
      if (!ok) return false;
      after();
      const def = (app.furniture || []).find(f => f.id === id);
      toast(`${sim.label} lies on the ${def ? def.label.toLowerCase() : 'furniture'}.`, 'ok');
      return true;
    });
  };
  function after() {
    app.refreshAll();
    app.physicsChanged();
    if (app.interact) { app.interact.refreshHandles(); if (app.interact.tool === 'move' && app.store.selected.sim) app.interact.selectPlace(app.store.selected.sim); }
    app.store.setDirty(true);
  }

  // the spots card in the inspector while the Place tool is on
  add('inspector', (a, root, { sim }) => {
    if (!sim || !app.interact || app.interact.tool !== 'move' || !slots.info) return;
    const list = spotsOf(slots.info);
    if (!list.length) return;
    const btns = h('div', { class: 'spot-grid' }, list.map(sp => h('button', { class: 'btn small spot-btn ' + sp.kind, title: `${sp.label}: ${sp.verb} ${sim.label} here`, onclick: () => doSpot(sp) },
      h('span', { class: 'spot-dot' }), sp.label)));
    const sec = section(['Spots on this furniture', h('span', { class: 'count' }, String(list.length))],
      h('div', { class: 'hint', style: { marginTop: 0 } }, `Click a spot (here or on the furniture) - ${sim.label} sits or lies exactly there, and the whole animation moves with it.`), btns);
    sec.classList.add('spots-card');
    root.append(sec);
  });

  // ---------------------------------------------------------------- clipping check
  const card = { el: null, issues: [] };
  const setMarks = issues => {
    if (!app.timeline) return;
    app.timeline.marks = (app.timeline.marks || []).filter(m => !m._clip).concat(issues.flatMap(it => (it.ranges || [[it.from, it.to]])
      .map(([f, t]) => ({ frame: f, to: t, simId: it.simId, color: RED, title: it.text, _clip: true }))));
    app.timeline.draw();
  };
  app.checkClipping = async ({ step = 1, quiet = false } = {}) => {
    if (app._clipping) return app._clipping;
    if (app.playing) app.setPlaying(false);
    btnClip && btnClip.classList.add('busy');
    const t0 = performance.now();
    app._clipping = checkClipping(app, { step, onProgress: p => { if (btnClip) btnClip.style.setProperty('--p', Math.round(p * 100) + '%'); } })
      .then(issues => {
        card.issues = issues; card.ms = Math.round(performance.now() - t0);
        setMarks(issues);
        if (!quiet) showCard(issues);
        return issues;
      })
      .finally(() => { app._clipping = null; btnClip && btnClip.classList.remove('busy'); btnClip && btnClip.style.removeProperty('--p'); });
    return app._clipping;
  };
  function closeCard() { if (card.el) { card.el.remove(); card.el = null; } }
  function showCard(issues) {
    closeCard();
    const wrap = document.getElementById('viewport-wrap');
    if (!wrap) return;
    const n = issues.length;
    const rows = h('div', { class: 'clip-rows' });
    for (const it of issues.slice(0, 12)) {
      const canHold = it.limb && typeof app.holdNearest === 'function' && it.otherId && it.otherId !== it.simId;
      rows.append(h('div', { class: 'clip-row' }, h('span', { class: 'clip-dot' }), h('span', { class: 'clip-text' }, it.text),
        h('div', { class: 'clip-actions' },
          h('button', { class: 'btn small', onclick: () => showIssue(it) }, 'Show'),
          canHold ? h('button', { class: 'btn small primary', title: 'The hand or foot holds on to the body there instead of going through it', onclick: () => fixHold(it) }, 'Fix: hold here') : null)));
    }
    if (n > 12) rows.append(h('div', { class: 'hint' }, `…and ${n - 12} more (red ticks on the timeline).`));
    card.el = h('div', { class: 'clip-card', id: 'clip-card', role: 'dialog' },
      h('div', { class: 'clip-head' }, icon('clip'), h('b', {}, n ? `Clipping check: ${n} place${n === 1 ? '' : 's'}` : 'No clipping found'),
        h('button', { class: 'icon-btn sm', title: 'Close', onclick: () => { closeCard(); } }, icon('x'))),
      n ? rows : h('div', { class: 'hint' }, 'Hands, arms and legs stay out of the bodies and the furniture over the whole loop.'),
      n ? h('div', { class: 'hint clip-foot' }, 'Red ticks on the timeline show where. Parts that only touch are fine.') : null);
    wrap.append(card.el);
  }
  function showIssue(it) {
    app.selectSim(it.simId);
    app.setFrame(it.peak ?? it.from);
    const v = app.simViews.get(it.simId);
    const c = v && capsulesOf(v).find(x => x.name === it.part);
    const now = c && capsuleNow(v, c);
    if (now) app.vp.frame(now.a.clone().add(now.b).multiplyScalar(0.5), 0.5);
    app.hud(it.text, { hold: 3000 });
  }
  async function fixHold(it) {
    app.setFrame(it.peak ?? it.from);
    try { await app.holdNearest(it.simId, it.limb); } catch (e) { console.error(e); }
    app.checkClipping();
  }
  app.clipIssues = () => card.issues;
  const stale = () => { if (app.timeline && (app.timeline.marks || []).some(m => m._clip)) setMarks([]); };
  if (app.on) { app.on('keyed', stale); app.on('undo', stale); }
  add('simRemoved', id => { if (app.timeline) { app.timeline.marks = (app.timeline.marks || []).filter(m => m.simId !== id); } B.endTrial(app, id, { quiet: true }); });
  // before Send to game: a quick look (every 2nd frame); a warning, never a stop
  let lastSig = '', lastIssues = [];
  add('exportChecks', p => {
    let issues;
    const sig = JSON.stringify([p.length, p.loop, p.furniture, p.sims.map(s => [s.id, s.frame, s.keys, s.layers, s.pins, s.body, s.visible])]);
    if (sig === lastSig) issues = lastIssues;
    else { issues = scanClipping(app, { step: 2 }); lastSig = sig; lastIssues = issues; card.issues = issues; }
    if (!issues.length) return [];
    const bodies = issues.filter(i => i.otherId !== null).length, furn = issues.length - bodies;
    const what = bodies && furn ? 'a body or the furniture' : bodies ? 'a body' : 'the furniture';
    return [{ level: 'warn', text: `Hands or legs go through ${what} in ${issues.length} place${issues.length === 1 ? '' : 's'}.`,
      fix: { label: 'Show me', run: () => { setMarks(issues); showCard(issues); } } }];
  });

  // ---------------------------------------------------------------- other bodies
  app.trial = app.trial || new Map();
  add('bodyOverride', s => B.bodyOverride(app, s));
  app.tryBody = (simId, opt) => B.tryBody(app, simId, opt);
  app.endTrial = (simId = null) => B.endTrial(app, simId);
  app.nextBody = simId => B.nextBody(app, simId);
  app.cycleBodies = (on, simId = app.store.selected.sim) => B.setCycle(app, simId, on);
  // nothing is ever baked or saved with a trial body
  const stopTrials = () => { if (app._cycle) app._cycle = null; if (app.trial.size) B.endTrial(app, null, { quiet: true }); };
  add('beforeBake', () => { if (app.trial.size) stopTrials(); });
  add('beforeSave', () => { if (app.trial.size) { stopTrials(); toast('Trying other bodies stopped - your own bodies are back.'); } });

  // ---------------------------------------------------------------- hair
  // the hair arrives a moment after the body; the Body step's hair row then says what the sim wears
  const hairShown = s => {
    const a = document.activeElement;
    if (a && a.closest && a.closest('#panel-body') && a.matches('input, select')) return;       // not under a slider being dragged
    if (app.step === 'body' && app.store.selected.sim === s.id && !app.vp.dragging) app.renderStep();
  };
  add('viewCreated', (v, s) => { B.loadHair(app, v, s).then(n => { if (n) hairShown(s); }).catch(err => console.warn('hair', err)); });
  app.setHair = (simId, hair) => {
    const s = app.store.sim(simId);
    if (!s) return;
    app.store.checkpoint();
    s.hair = hair === undefined ? null : hair;
    app.store.setDirty(true);
    B.reloadHair(app, simId).then(() => { if (app.step === 'body') app.renderStep(); });
    if (app.step === 'body') app.renderStep();
  };
  // a new animation's sims get the default hair of their body (a Tray sim keeps its own); old animations keep what
  // they had (no hair), until a hair is picked in the Body step
  let known = new Set(), knownUid = null;
  const giveDefaults = async (sims, { dirty = false } = {}) => {
    const todo = sims.filter(s => !('hair' in s) && !s.tray);
    if (!todo.length) return;
    for (const s of todo) {
      const hh = await B.defaultHair(s.frame);
      if (hh && !('hair' in s)) s.hair = hh;
      if (dirty) app.store.setDirty(true);
      B.reloadHair(app, s.id);
    }
    if (app.step === 'body') app.renderStep();
  };
  const isFresh = p => !app._file && p.sims.length && p.sims.every(s => !('hair' in s) && (s.keys || []).length <= 1);
  add('projectLoaded', p => {
    stopTrials();
    closeCard();
    setMarks([]);
    card.issues = []; lastSig = '';
    known = new Set(p.sims.map(s => s.id)); knownUid = p.uid;
    if (isFresh(p)) giveDefaults(p.sims);
    slots.refresh(true);
  });
  // the blank couple the app starts with was made before this feature plugged in
  {
    const p = app.store.project;
    known = new Set(p.sims.map(s => s.id)); knownUid = p.uid;
    if (isFresh(p)) giveDefaults(p.sims);
  }
  app.on && app.on('magic', () => {
    const p = app.store.project;
    known = new Set(p.sims.map(s => s.id)); knownUid = p.uid;
    closeCard(); setMarks([]);
    giveDefaults(p.sims);
  });
  // a sim added later to an animation whose sims wear hair gets the default hair too; and a view whose sim's hair
  // changed without a new view (undo, redo) gets the right hair again
  add('viewsSynced', () => {
    const p = app.store.project;
    for (const s of p.sims) { const v = app.simViews.get(s.id); if (v) B.loadHair(app, v, s).catch(() => {}); }
    if (p.uid !== knownUid) { known = new Set(p.sims.map(s => s.id)); knownUid = p.uid; return; }
    const fresh = p.sims.filter(s => !known.has(s.id));
    fresh.forEach(s => known.add(s.id));
    if (fresh.length && p.sims.some(s => s.hair && !fresh.includes(s))) giveDefaults(fresh, { dirty: true });
  });

  // ---------------------------------------------------------------- palette and help
  add('commands', a => {
    const sim = a.store.sim();
    return [
      { group: 'View', id: 'see-through', label: xray.seeOn ? 'See-through off' : 'See-through', icon: 'xray', keys: ['Alt', 'Z'], sub: 'see hands and contact behind bodies', words: 'x-ray xray transparent ghost see through alt z', run: () => setSee(!xray.seeOn) },
      { group: 'View', id: 'show-bones', label: xray.bonesOn ? 'Hide bones' : 'Show bones', icon: 'bones', keys: ['Alt', 'B'], sub: 'like Blender', words: 'skeleton armature rig octahedral bones', run: () => setBones(!xray.bonesOn) },
      { group: 'Check', id: 'check-clipping', label: 'Check clipping', icon: 'clip', sub: 'hands and legs that go through a body', words: 'clip intersect penetrate through body collision', run: () => a.checkClipping() },
      { group: 'Bodies', id: 'try-bodies', label: 'Try it on other bodies', icon: 'user', sub: 'Tray sims and penis sizes - your animation does not change', words: 'body swap tray size penis preview other bodies', when: () => !!sim, run: () => { a.showStep('body'); setTimeout(() => document.querySelector('.try-bodies')?.scrollIntoView({ block: 'start', behavior: 'smooth' }), 80); } },
      { group: 'Bodies', id: 'hair', label: 'Hair', icon: 'hair', sub: 'pick a hairstyle for the preview', words: 'hair hairstyle wig cas', when: () => !!sim, run: () => { a.showStep('body'); setTimeout(() => document.querySelector('.hair-row')?.scrollIntoView({ block: 'start', behavior: 'smooth' }), 80); } },
    ];
  });
  add('helpRows', () => [
    { group: 'Seeing better', keys: ['Alt', 'Z'], text: 'See-through: the other sims turn see-through' },
    { group: 'Seeing better', keys: ['Alt', 'B'], text: 'Show bones like Blender - click a bone to pick it' },
    { group: 'Seeing better', keys: 'Move (M)', text: 'Seats and lying spots show on the furniture - click one to sit or lie there' },
  ]);

  // Every place's surface and spots are read once in the background (one at a time, when the app is idle): a ready
  // pose or Magic on a place used for the first time then lands on its real top at once, instead of being lifted a
  // moment later (after it was already placed).
  const idle = fn => (window.requestIdleCallback ? window.requestIdleCallback(fn, { timeout: 4000 }) : setTimeout(fn, 400));
  setTimeout(async () => {
    for (const f of app.furniture || []) {
      if (!f || f.kind === 'floor' || f.kind === 'wall') continue;
      await new Promise(res => idle(res));
      try { await app._furnitureInfo(f.id); } catch { /* read again when it is used */ }
    }
  }, 2500);

  window.wickedScene = { xray, check: o => app.checkClipping(o), scan: o => scanClipping(app, o), bodies: B, slots, surfaceY };
}

const reduced = () => (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) || document.documentElement.classList.contains('reduce-motion');

export default install;
