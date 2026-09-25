// Clothes in the preview (to check clipping with outfits): the Body step's Clothes row for each sim (None, the Tray
// sim's own outfits by category, or a few basic outfits), a view button that hides everyone's clothes, and undress
// moments taking parts off while the animation plays. A Tray sim arrives in the outfit it was saved in (as its Tray
// picture shows it), and the clothes remover lists every piece each sim wears to take them off one by one or all at
// once. Everything plugs in through app.hooks, ui.addIcon and
// ui.addToolbarButton. Clothes are for the preview only: nothing about them goes into the exported animation.
import { h, icon, toast, addIcon, addToolbarButton, section, toggle, toggleRow, modal } from '../ui.js';
import * as C from '../clothes.js';

const S = 'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"';
const ICONS = {
  // a coat hanger
  hanger: '<path d="M12 7.2V6.6a1.9 1.9 0 1 1 1.9-1.9M12 7.2 3.4 13.6c-.9.7-.4 2.1.7 2.1h15.8c1.1 0 1.6-1.4.7-2.1L12 7.2z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  // the clothes remover's pieces
  'pc-top': `<path d="M8.5 4 4 6.5l1.8 4 2.2-1V20h8V9.5l2.2 1 1.8-4L15.5 4a3.5 3.5 0 0 1-7 0z" ${S}/>`,
  'pc-full': `<path d="M9 3.5h6l-.6 4 3.6 12.5H6L9.6 7.5z M9.6 7.5h4.8" ${S}/>`,
  'pc-bottom': `<path d="M6.5 4h11l1 16h-4.5l-2-10-2 10H5.5z M6.5 7.5h11" ${S}/>`,
  'pc-shoes': `<path d="M3.5 15.5V9l4 1.5 2.5 2.5 6.5 1.5c2 .5 4 1.5 4 3.5H3.5z M3.5 17.5h17" ${S}/>`,
  'pc-socks': `<path d="M8 3.5h6v8l2.8 3.2a3 3 0 0 1-4.3 4.2L8 14z M8 7h6" ${S}/>`,
  'pc-tights': `<path d="M7 3.5h10l-.8 17h-3.4L12 10l-.8 10.5H7.8z" ${S}/>`,
  'pc-hat': `<path d="M4 16.5c0-5 3.6-9 8-9s8 4 8 9 M2.5 16.5h19 M12 7.5V5.5" ${S}/>`,
  'pc-glasses': `<circle cx="7" cy="14" r="3.5" ${S}/><circle cx="17" cy="14" r="3.5" ${S}/><path d="M10.5 13.5c1-.8 2-.8 3 0M3.5 13 2.5 9M20.5 13l1-4" ${S}/>`,
  'pc-earrings': `<path d="M9 3.5a3 3 0 0 1 3 3v2" ${S}/><circle cx="12" cy="14" r="4" ${S}/><circle cx="12" cy="14" r="1.2" fill="currentColor"/>`,
  'pc-necklace': `<path d="M4 4c1 7 4 11 8 11s7-4 8-11" ${S}/><path d="M12 15l-2.2 3L12 21l2.2-3z" ${S}/>`,
  'pc-ring': `<circle cx="12" cy="14.5" r="5.5" ${S}/><path d="M9.5 6.5 12 3.5l2.5 3L12 9z" ${S}/>`,
  'pc-bracelet': `<ellipse cx="12" cy="12" rx="8" ry="5" ${S}/><ellipse cx="12" cy="12" rx="5.5" ry="2.8" ${S}/>`,
  'pc-piercing': `<circle cx="12" cy="12" r="5" ${S}/><circle cx="12" cy="7" r="1.6" fill="currentColor"/>`,
  'pc-gloves': `<path d="M7 20v-7L5 9.5a1.4 1.4 0 0 1 2.4-1.4L9 10.5V5a1.5 1.5 0 0 1 3 0v4.5V4a1.5 1.5 0 0 1 3 0v6V6a1.5 1.5 0 0 1 3 0v9c0 3-2 5-5 5z" ${S}/>`,
  'pc-other': `<path d="M12 3.5 20 8v8l-8 4.5L4 16V8z" ${S}/>`,
};
// which icon a piece gets (by its body type, then its kind)
const PIECE_ICON = t => {
  const n = t.body_type_name || '';
  if (/GLASSES/.test(n)) return 'pc-glasses';
  if (/EARRINGS/.test(n)) return 'pc-earrings';
  if (/NECKLACE/.test(n)) return 'pc-necklace';
  if (/FINGER/.test(n)) return 'pc-ring';
  if (/WRIST/.test(n)) return 'pc-bracelet';
  if (/_RING_/.test(n)) return 'pc-piercing';
  if (/GLOVES/.test(n)) return 'pc-gloves';
  return 'pc-' + ({ full: 'full', top: 'top', bottom: 'bottom', shoes: 'shoes', socks: 'socks', tights: 'tights', hat: 'hat' }[t.kind] || 'other');
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
  // (app.trayDressing: sim id -> a promise that settles once the outfit is on, for the Tray's loading card)
  add('traySimAdded', s => {
    const done = C.outfitList(app, { kind: 'tray', tray: s.tray.id, index: s.tray.index || 0 }).then(list => {
      const live = app.store.sim(s.id);
      if (!live || live.clothes || !list.current || !list.items.some(o => o.key === list.current)) return;
      live.clothes = { outfit: list.current };
      return C.reloadClothes(app, s.id).then(() => { shown(live); refreshRemover(); });
    }).catch(err => console.warn('clothes', err.message));
    (app.trayDressing = app.trayDressing || new Map()).set(s.id, done);
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
  const body = h('div', {}, h('div', { class: 'hint', style: { marginTop: 0 } }, 'Dress a sim to check clipping. Clothes never go into the exported animation.'));
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
    const bits = [];
    if (info.missing.length) bits.push(`${info.missing.length} ${info.missing.length === 1 ? 'piece isn\'t' : 'pieces aren\'t'} installed on this PC.`);
    if (info.painted.length) bits.push(`${info.painted.map(n => shortName(n) || 'A piece').join(', ')}: painted on the skin in the game, not shown here.`);
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
// "Mably_yfBody_LingerieCorsetLaceSides_SolidBlue_2025..." -> "Lingerie Corset Lace Sides · Solid Blue"
const CAS_WORD = /^(Acc|Body|Top|Bottom|Shoes|Hair|Hat|Makeup|Skin|Detail)(?=[A-Z]|$)/;
const shortName = n => {
  const bits = String(n || '').replace(/^.*?_(?=[yaeptc][fmu][A-Z])/, '').replace(/^[yaeptc][fmu](?=[A-Z])/, '')
    .replace(/_\d{12,}.*$/, '').split(/[_ ]+/).filter(Boolean);
  if (bits.length > 1 && CAS_WORD.test(bits[0])) bits[0] = bits[0].replace(CAS_WORD, '');
  const words = bits.map(b => b.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/([A-Za-z])(\d)/g, '$1 $2').trim()).filter(Boolean);
  return words.join(' · ').slice(0, 60);
};

// One sim's pieces: what it wears now (a bar), Take off clothes / Take off everything / Put all back, and every piece
// with its icon, a readable name and a switch - clothes first, then hats and accessories.
function pieceList(app, sim) {
  const box = h('div', { class: 'pieces' }, h('div', { class: 'hint' }, 'Reading the clothes…'));
  C.piecesOf(app, sim).then(pc => {
    box.replaceChildren();
    if (!pc) { box.append(h('div', { class: 'hint' }, 'Wearing nothing.')); return; }
    const worn = pc.parts.filter(p => p.on).length, all = pc.parts.length;
    const set = (p, on) => app.setPiecesOff(sim.id, pc.parts.filter(x => (x === p ? !on : !x.on)).map(x => x.casp));
    box.append(h('div', { class: 'pieces-card' },
      h('div', { class: 'pieces-head' }, h('div', {}, h('b', {}, pc.label), h('small', {}, `${worn} of ${all} ${all === 1 ? 'piece' : 'pieces'} on`)),
        h('div', { class: 'pieces-meter', style: { '--on': (all ? worn / all : 0).toFixed(3) } }, h('i'))),
      h('div', { class: 'pieces-btns' },
        h('button', { class: 'btn small', title: 'Hats and accessories stay on', disabled: !pc.parts.some(p => p.on && C.isClothing(p)), onclick: () => app.undress(sim.id, 'clothes') }, icon('hanger'), 'Take off clothes'),
        h('button', { class: 'btn small', disabled: !worn, onclick: () => app.undress(sim.id, 'all') }, 'Take off everything'),
        h('button', { class: 'btn small ghost', disabled: worn === all, onclick: () => app.undress(sim.id, 'none') }, icon('undo'), 'Put all back'))));
    const group = (title, list) => {
      if (!list.length) return;
      box.append(h('div', { class: 'pieces-group' }, title, h('span', {}, `${list.filter(p => p.on).length}/${list.length}`)));
      for (const p of list) {
        const missing = p.origin === null;
        const sw = toggle(p.on, on => set(p, on));
        box.append(h('div', { class: 'piece' + (p.on ? '' : ' off') + (missing ? ' missing' : ''), title: p.name || null },
          h('span', { class: 'piece-ic' }, icon(PIECE_ICON(p))),
          h('span', { class: 'piece-text' }, h('b', {}, C.pieceLabel(p)), h('small', {}, missing ? 'Not installed on this PC' : shortName(p.name) || 'Custom content')),
          sw));
      }
    };
    group('Clothes', pc.parts.filter(p => C.isClothing(p)));
    group('Hats and accessories', pc.parts.filter(p => !C.isClothing(p)));
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
