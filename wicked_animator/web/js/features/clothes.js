// Clothes in the preview (to check clipping with outfits): the Body step's Clothes row for each sim (None, the Tray
// sim's own outfits by category, or a few basic outfits), a view button that hides everyone's clothes, and undress
// moments taking parts off while the animation plays. A Tray sim arrives in the outfit it was saved in (as its Tray
// picture shows it), and the clothes remover lists every piece each sim wears to take them off one by one or all at
// once. Everything plugs in through app.hooks, ui.addIcon and
// ui.addToolbarButton. Clothes are for the preview only: nothing about them goes into the exported animation.
import { h, toast, addIcon, addToolbarButton, section, toggleRow, modal } from '../ui.js';
import * as C from '../clothes.js';

const ICONS = {
  // a coat hanger
  hanger: '<path d="M12 7.2V6.6a1.9 1.9 0 1 1 1.9-1.9M12 7.2 3.4 13.6c-.9.7-.4 2.1.7 2.1h15.8c1.1 0 1.6-1.4.7-2.1L12 7.2z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
};
const HIDE_KEY = 'wa.clothesHidden';
const readHidden = () => { try { return localStorage.getItem(HIDE_KEY) === '1'; } catch { return false; } };
const saveHidden = on => { try { localStorage.setItem(HIDE_KEY, on ? '1' : '0'); } catch { /* private window: this session only */ } };
const EXPORT_NOTE = 'Clothes are for the preview only - they never go into the exported animation.';

export function install(app) {
  if (!app || app.__clothes) return;
  app.__clothes = true;
  const hooks = app.hooks || {};
  const add = (name, fn) => {
    let t = hooks;
    const parts = name.split('.');
    for (const p of parts.slice(0, -1)) t = t && t[p];
    if (t && Array.isArray(t[parts[parts.length - 1]])) t[parts[parts.length - 1]].push(fn);
  };
  for (const [id, svg] of Object.entries(ICONS)) addIcon(id, svg);

  // ---------------------------------------------------------------- hide everyone's clothes
  app.clothesHidden = readHidden();
  const btn = addToolbarButton({ cell: 'view', id: 'btn-clothes', icon: 'hanger', toggle: true,
    title: 'Hide clothes in the view (preview only)', onClick: (e, b) => setHidden(b.classList.contains('on')) });
  if (btn) btn.classList.toggle('on', app.clothesHidden);
  function setHidden(on, { quiet = false } = {}) {
    app.clothesHidden = !!on;
    saveHidden(app.clothesHidden);
    if (btn) btn.classList.toggle('on', app.clothesHidden);
    C.applyVisibility(app);
    if (!quiet) toast(app.clothesHidden ? 'Clothes hidden.' : 'Clothes shown.');
    if (app.step === 'body') app.renderStep();
  }
  app.setClothesHidden = on => setHidden(on === undefined ? !app.clothesHidden : !!on);

  // ---------------------------------------------------------------- each sim's clothes
  // the parts arrive a moment after the body; the Body step's Clothes row then says what the sim wears
  const shown = s => {
    const a = document.activeElement;
    if (a && a.closest && a.closest('#panel-body') && a.matches('input, select')) return;
    if (app.step === 'body' && app.store.selected.sim === s.id && !app.vp.dragging) app.renderStep();
  };
  const load = (v, s) => C.loadClothes(app, v, s).then(() => shown(s)).catch(err => console.warn('clothes', err));
  add('viewCreated', (v, s) => { if (C.clothesSpecOf(app, s)) load(v, s); });
  // undo / redo, a trial body, a sim's choice changing without a new view
  add('viewsSynced', () => {
    for (const s of app.store.project.sims) {
      const v = app.simViews.get(s.id);
      if (v && (v.clothesKey || '') !== C.specKey(C.clothesSpecOf(app, s))) load(v, s);
    }
  });
  add('afterApply', frame => C.applyVisibility(app, frame));
  app.setClothes = (simId, choice) => {
    const s = app.store.sim(simId);
    if (!s) return;
    app.store.checkpoint();
    s.clothes = choice || null;
    app.store.setDirty(true);
    C.reloadClothes(app, simId).then(() => { if (app.step === 'body') app.renderStep(); });
    if (app.step === 'body') app.renderStep();
  };

  // a Tray sim arrives wearing the outfit it was saved in, accessories and all (part of adding it, no undo step)
  add('traySimAdded', s => {
    C.outfitList(app, { kind: 'tray', tray: s.tray.id, index: s.tray.index || 0 }).then(list => {
      const live = app.store.sim(s.id);
      if (!live || live.clothes || !list.current || !list.items.some(o => o.key === list.current)) return;
      live.clothes = { outfit: list.current };
      C.reloadClothes(app, s.id).then(() => { shown(live); refreshRemover(); });
    }).catch(err => console.warn('clothes', err.message));
  });

  // ---------------------------------------------------------------- the clothes remover
  // off: the pieces of the sim's outfit taken off. undress: 'clothes' takes off the clothes (accessories and hats
  // stay), 'all' everything, 'none' puts it all back on.
  app.setPiecesOff = (simId, off) => {
    const s = app.store.sim(simId);
    if (!s || !s.clothes || typeof s.clothes !== 'object') return;
    app.store.checkpoint();
    const next = { ...s.clothes, off: [...new Set(off)] };
    if (!next.off.length) delete next.off;
    s.clothes = next;
    app.store.setDirty(true);
    C.reloadClothes(app, simId).then(() => { if (app.step === 'body') app.renderStep(); refreshRemover(); });
    if (app.step === 'body') app.renderStep();
    refreshRemover();
  };
  app.undress = async (simId, what = 'clothes') => {
    const s = app.store.sim(simId);
    const pieces = s && await C.piecesOf(app, s).catch(() => null);
    if (!pieces) return;
    app.setPiecesOff(simId, what === 'none' ? [] : pieces.parts.filter(p => what === 'all' || C.isClothing(p)).map(p => p.casp));
  };
  let remover = null;
  function refreshRemover() {
    if (!remover || !remover.isConnected) { remover = null; return; }
    remover.replaceChildren(...removerRows(app));
  }
  app.openClothesRemover = () => {
    remover = h('div', { class: 'remover' }, ...removerRows(app));
    modal({ title: 'Clothes remover', text: 'Every piece each sim wears. ' + EXPORT_NOTE, body: remover, wide: true,
      buttons: [{ label: 'Done', kind: 'primary' }], onClose: () => { remover = null; } });
  };

  add('sections.body', (a, root) => {
    const sim = a.store.sim();
    if (!sim) return;
    const sec = clothesSection(a, sim, a.simViews.get(sim.id), setHidden);
    const after = root.querySelector('.hair-row');
    if (after && after.parentNode === root) after.after(sec); else root.append(sec);
  });

  add('commands', a => {
    const sim = a.store.sim();
    return [
      { group: 'Bodies', id: 'clothes', label: 'Clothes', icon: 'hanger', sub: 'show an outfit to check clipping', words: 'clothes outfit dress dressed wear clothing cas preview clipping',
        when: () => !!sim, run: () => { a.showStep('body'); setTimeout(() => document.querySelector('.clothes-row')?.scrollIntoView({ block: 'start', behavior: 'smooth' }), 80); } },
      { group: 'Bodies', id: 'clothes-remover', label: 'Clothes remover', icon: 'hanger', sub: 'every piece each sim wears - take them off', words: 'clothes remover undress naked nude strip take off pieces accessories',
        when: () => a.store.project.sims.length > 0, run: () => a.openClothesRemover() },
      { group: 'View', id: 'hide-clothes', label: a.clothesHidden ? 'Show clothes' : 'Hide clothes', icon: 'hanger', sub: 'every sim, in the view only', words: 'clothes outfit naked nude hide show',
        run: () => setHidden(!a.clothesHidden) },
    ];
  });

  window.wickedClothes = { C, setHidden };
}

// ---------------------------------------------------------------- the Body step's Clothes row
function clothesSection(app, sim, v, setHidden) {
  const cur = sim.clothes && typeof sim.clothes === 'object' ? sim.clothes : null;
  const body = h('div', {}, h('div', { class: 'hint', style: { marginTop: 0 } }, 'Check clipping with an outfit on. ' + EXPORT_NOTE));
  const chips = h('div', { class: 'chips clothes-chips' });
  chips.append(h('button', { class: 'chipbtn' + (!cur ? ' on' : ''), 'data-clothes': 'none', onclick: () => app.setClothes(sim.id, null) }, 'None'));
  body.append(chips);
  const status = h('div', { class: 'clothes-note' });
  const sec = section(['Clothes', h('span', { class: 'count' }, 'preview')], body);
  sec.classList.add('clothes-row');
  const chip = (label, on, choice, title, cls = '') => h('button', { class: 'chipbtn ' + cls + (on ? ' on' : ''), title: title || null,
    'data-clothes': choice.outfit ? 'outfit:' + choice.outfit : 'basic:' + choice.basic, onclick: () => app.setClothes(sim.id, choice) }, label);

  const pending = [];
  if (sim.tray && sim.tray.id) {
    const own = h('div', { class: 'chips clothes-chips' }, h('span', { class: 'clothes-label' }, `${sim.tray.name || 'Tray'}'s outfits`));
    body.append(own);
    pending.push(C.outfitList(app, { kind: 'tray', tray: sim.tray.id, index: sim.tray.index || 0 }).then(list => {
      if (!list.items.length) { own.append(h('span', { class: 'clothes-empty' }, 'none saved')); return; }
      for (const o of list.items) {
        const miss = (o.parts || []).filter(p => p.origin === null).length;
        own.append(chip(o.label, cur && cur.outfit === o.key, { outfit: o.key },
          `${o.parts.length} part${o.parts.length === 1 ? '' : 's'}${miss ? ` (${miss} not installed)` : ''}${list.current === o.key ? ' - the outfit the sim was saved in' : ''}`, 'tray'));
      }
    }).catch(err => { own.append(h('span', { class: 'clothes-empty' }, 'could not be read')); console.warn('clothes', err.message); }));
  }
  const basic = h('div', { class: 'chips clothes-chips' }, h('span', { class: 'clothes-label' }, 'Basic'));
  body.append(basic);
  pending.push(C.outfitList(app, { kind: 'basic', frame: sim.frame === 'ym' ? 'ym' : 'yf' }).then(list => {
    if (!list.items.length) { basic.append(h('span', { class: 'clothes-empty' }, 'none found in the game')); return; }
    for (const o of list.items) basic.append(chip(o.label, cur && cur.basic === o.key, { basic: o.key }, (o.parts || []).map(p => p.name).join(', ')));
  }).catch(() => basic.append(h('span', { class: 'clothes-empty' }, 'need the game'))));

  // what shows now
  const info = v && v.clothesInfo;
  let note = '';
  if (cur && (!info || info.loading)) note = 'Loading the clothes…';
  else if (cur && info && info.error) note = `No clothes shown: ${info.error}`;
  else if (cur && info) {
    const bits = [`${info.label || 'Outfit'}: ${info.shown} part${info.shown === 1 ? '' : 's'} shown.`];
    if (info.missing.length) bits.push(`Not installed: ${info.missing.join(', ')}.`);
    if (info.painted.length) bits.push(`Painted on the skin in the game, not shown here: ${info.painted.join(', ')}.`);
    if ((app.store.project.events || []).some(e => e.type === 'UNDRESS' && e.sim === sim.id)) bits.push('Undress moments take the matching parts off while it plays.');
    note = bits.join(' ');
  }
  if (note) { status.textContent = note; body.append(status); }
  if (cur) body.append(pieceList(app, sim));
  if (app.store.project.sims.length > 1) body.append(h('button', { class: 'btn small ghost', style: { marginTop: '8px' }, onclick: () => app.openClothesRemover() }, 'Clothes remover for everyone…'));
  body.append(toggleRow('Hide everyone\'s clothes', 'In the view only', !!app.clothesHidden, on => setHidden(on, { quiet: true })));
  Promise.allSettled(pending).then(() => sec.classList.add('ready'));
  return sec;
}

// ---------------------------------------------------------------- the clothes remover's lists
// A readable name from a CAS part name: the creator prefix, the age/gender code and the date stamp go.
const shortName = n => String(n || '').replace(/^.*?_(?=[yaeptc][fmu][A-Z])/, '').replace(/^[yaeptc][fmu](?=[A-Z])/, '')
  .replace(/_\d{12,}.*$/, '').replace(/_/g, ' ').trim().slice(0, 48);

// One sim's pieces with a switch each, and Take off clothes / Take off everything / Put all back.
function pieceList(app, sim) {
  const box = h('div', { class: 'pieces' }, h('div', { class: 'hint' }, 'Reading the clothes…'));
  C.piecesOf(app, sim).then(pc => {
    box.replaceChildren();
    if (!pc) { box.append(h('div', { class: 'hint' }, 'Wearing nothing.')); return; }
    const worn = pc.parts.filter(p => p.on).length;
    box.append(h('div', { class: 'pieces-head' }, h('b', {}, `${pc.label}: ${worn} of ${pc.parts.length} on`),
      h('div', { class: 'pieces-btns' },
        h('button', { class: 'btn small', title: 'Accessories and hats stay on', disabled: !pc.parts.some(p => p.on && C.isClothing(p)), onclick: () => app.undress(sim.id, 'clothes') }, 'Take off clothes'),
        h('button', { class: 'btn small', disabled: !worn, onclick: () => app.undress(sim.id, 'all') }, 'Take off everything'),
        h('button', { class: 'btn small ghost', disabled: worn === pc.parts.length, onclick: () => app.undress(sim.id, 'none') }, 'Put all back'))));
    for (const p of pc.parts) {
      const missing = p.origin === null;
      box.append(h('label', { class: 'piece' + (p.on ? '' : ' off') + (missing ? ' missing' : ''), title: p.name || null },
        h('input', { type: 'checkbox', checked: p.on, onchange: e => app.setPiecesOff(sim.id, pc.parts.filter(x => (x === p ? !e.target.checked : !x.on)).map(x => x.casp)) }),
        h('span', { class: 'piece-name' }, C.pieceLabel(p)),
        h('small', {}, missing ? 'not installed' : shortName(p.name))));
    }
  }).catch(err => { box.replaceChildren(h('div', { class: 'hint' }, 'Could not read the clothes: ' + err.message)); });
  return box;
}

// Every sim in the scene: its outfit's pieces (or a word on how to dress it), and buttons for everyone.
function removerRows(app) {
  const sims = app.store.project.sims;
  const rows = [h('div', { class: 'remover-all' },
    h('button', { class: 'btn small', onclick: () => sims.forEach(s => app.undress(s.id, 'clothes')) }, "Take off everyone's clothes"),
    h('button', { class: 'btn small', onclick: () => sims.forEach(s => app.undress(s.id, 'all')) }, 'Everyone naked'),
    h('button', { class: 'btn small ghost', onclick: () => sims.forEach(s => app.undress(s.id, 'none')) }, 'Dress everyone again'))];
  for (const s of sims) {
    const wear = s.clothes && typeof s.clothes === 'object';
    rows.push(h('div', { class: 'remover-sim' },
      h('div', { class: 'remover-name' }, h('span', { class: 'dot', style: { background: s.color || '#888' } }), s.label || 'Sim'),
      wear ? pieceList(app, s) : h('div', { class: 'hint' }, `Wearing nothing. Pick an outfit in the Body step to dress ${s.label || 'this sim'}.`)));
  }
  return rows;
}
