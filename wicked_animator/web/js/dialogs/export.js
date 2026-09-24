// Send to game: what WickedWhims needs is checked first, then the package goes into the Mods folder.
import { h, icon, modal, toast } from '../ui.js';
import { api } from '../api.js';
import { localStorageSet, localStorageGet } from '../state.js';
import { tagLabel, nakedFor, NAKED_CHOICES, KINDS } from '../tags.js';
import { namedField } from './name.js';
const NAKED_LABEL = Object.fromEntries(NAKED_CHOICES);
const nice = s => s.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

export const WW_LOCATIONS = ['FLOOR', 'DOUBLE_BED', 'SINGLE_BED', 'BUNK_BED', 'MURPHY_DOUBLE_BED', 'BED_ROLL', 'SOFA', 'LOVESEAT',
  'SECTIONAL_SOFA', 'CHAIR_LIVING', 'CHAIR_DINING', 'CHAIR_DESK', 'CHAIR_STOOL', 'CHAIR_LOUNGE', 'OTTOMAN', 'COUNTER',
  'COUNTER_ISLAND', 'BAR', 'DESK', 'TABLE_DINING_1X', 'TABLE_DINING_2X', 'TABLE_DINING_3X', 'TABLE_COFFEE', 'TABLE_PICNIC',
  'WALL', 'DOOR', 'WINDOW', 'MIRROR', 'SINK', 'SHOWER', 'OPEN_SHOWER', 'BATHTUB', 'HOTTUB', 'TOILET', 'SAUNA',
  'MASSAGE_TABLE', 'YOGA_MAT', 'BEACH_TOWEL', 'BLANKET', 'DANCE_FLOOR', 'WORKOUT_MACHINE', 'TREADMILL', 'STOVE', 'COFFIN', 'SWING_SET', 'UNDERWATER'];

// What WickedWhims needs, checked before anything is written (the mistakes creators make most), plus what other
// features add through app.hooks.exportChecks: [{level: 'warn'|'error', text, frame?, simId?, fix?: {label, run}}].
export function exportChecks(app) {
  const p = app.store.project, out = [];
  const add = (level, text, fix, key) => out.push({ level, text, fix, key });
  if (!p.name || /^untitled/i.test(p.name)) add('error', 'Give the animation a name.', () => app.showStep('details'), 'name');
  if (!p.author) add('error', 'Add a creator name - WickedWhims shows "by ..." and needs it.', () => app.showStep('details'), 'author');
  if (!(p.locations || []).length) add('error', 'Pick at least one place it is offered on.', () => app.showStep('details'));
  if (!p.sims.length) add('error', 'Add at least one sim.', () => app.showStep('scene'));
  // a face key alone is not a pose: every sim needs a body key
  if (p.sims.some(s => !s.keys.some(k => !k.faceOnly))) add('error', 'Every sim needs at least one pose.', () => app.showStep('pose'));
  if (p.category === 'CLIMAX' && (p.loops || 10) > 2) add('info', 'Climax animations usually play once: set "Plays for" to 1 in Details.', () => app.showStep('details'));
  if ((p.tags || []).length === 0) add('info', 'No tags yet - tags help people find it in WickedWhims.', () => app.showStep('details'));
  if (!p.sims.some(s => (s.sounds || []).length)) add('info', 'No sounds - "Place sounds for me" in step 6 adds claps and wet sounds.', () => app.showStep('sounds'));
  for (const list of app.runHook ? app.runHook('exportChecks', p) : []) {
    for (const x of Array.isArray(list) ? list : []) {
      if (!x || !x.text) continue;
      const go = () => {
        if (x.simId && app.store.sim(x.simId)) app.selectSim(x.simId);
        if (typeof x.frame === 'number') app.setFrame(x.frame);
      };
      out.push({ level: x.level === 'error' ? 'error' : 'warn', text: x.text,
        fix: x.fix && typeof x.fix.run === 'function' ? () => { go(); x.fix.run(); } : (typeof x.frame === 'number' || x.simId ? go : null),
        fixLabel: x.fix && x.fix.label ? x.fix.label : (typeof x.frame === 'number' ? 'Show me' : null) });
    }
  }
  return out;
}

export function openExportDialog(app) {
  const p = app.store.project;
  let dlg = null, sending = false;
  // a missing name or creator is typed right here - no trip to Details and back
  const nameIn = h('input', { class: 'text', value: /^untitled/i.test(p.name || '') ? '' : (p.name || ''), placeholder: 'e.g. Cowgirl 1', spellcheck: 'false' });
  const authorIn = h('input', { class: 'text', value: p.author || localStorageGet('author', '') || '', placeholder: 'e.g. Novulon', spellcheck: 'false' });
  const needName = !p.name || /^untitled/i.test(p.name), needAuthor = !p.author;
  // an empty box that is needed is marked red with what to type, and the cursor waits in the first one
  const nameF = namedField('Animation name', nameIn), authorF = namedField('Creator', authorIn);
  const inline = needName || needAuthor ? h('div', { class: 'card inline-name' },
    h('div', { class: 'section-title' }, 'Name it'),
    h('div', { class: 'grid-2' }, nameF.field, authorF.field)) : null;
  const badName = () => !nameIn.value.trim() || /^untitled/i.test(nameIn.value.trim()), badAuthor = () => !authorIn.value.trim();
  const markBoxes = () => {
    if (!inline) return null;
    nameF.set(badName() ? 'Give the animation a name.' : '');
    authorF.set(badAuthor() ? 'Add a creator name - WickedWhims shows "by ..."' : '');
    return badName() ? nameIn : badAuthor() ? authorIn : null;
  };
  // when the boxes are shown, what is typed in them is what gets used (both boxes)
  const typedName = () => (inline ? nameIn.value.trim() : p.name);
  const typedAuthor = () => (inline ? authorIn.value.trim() : p.author);
  // the name and creator are checked at their boxes above when they are typed here
  const current = () => exportChecks(app).filter(x => !(inline && (x.key === 'name' || x.key === 'author')));
  const listBox = h('div', { style: { marginTop: '10px' } });
  const preview = h('div', { class: 'name-preview' });
  const drawPreview = () => { preview.innerHTML = ''; preview.append(h('b', {}, typedName() || 'Animation name'), h('span', {}, 'by ' + (typedAuthor() || '?'))); };
  const missingTyped = () => !!inline && (!typedName() || /^untitled/i.test(typedName()) || !typedAuthor());
  const draw = () => {
    drawPreview();
    const list = current();
    listBox.innerHTML = '';
    for (const x of list) listBox.append(h('div', { class: x.level === 'error' ? 'warn-box error' : x.level === 'warn' ? 'warn-box' : 'tip' }, h('span', {}, x.text),
      x.fix ? h('button', { class: 'btn small', style: { marginLeft: 'auto' }, onclick: () => { dlg.close(); x.fix(); } }, x.fixLabel || 'Fix') : null));
    const blocked = list.some(x => x.level === 'error') || missingTyped();
    if (dlg) {
      const btn = dlg.footer.lastChild;
      if (!sending) { btn.disabled = blocked; btn.textContent = blocked ? 'Fill in the missing items above' : 'Send to game'; }
    }
    return blocked;
  };
  // typing clears a box's red mark (namedField), and a box left empty again is marked again
  nameIn.addEventListener('input', () => { if (badName()) nameF.set('Give the animation a name.'); draw(); });
  authorIn.addEventListener('input', () => { if (badAuthor()) authorF.set('Add a creator name - WickedWhims shows "by ..."'); draw(); });
  const body = h('div', {},
    preview, inline,
    h('div', { class: 'grid-2', style: { marginTop: '10px' } },
      h('div', { class: 'card' }, h('div', { class: 'section-title' }, 'In WickedWhims'),
        h('div', {}, h('b', {}, (KINDS.find(k => k[0] === p.category) || ['', p.category])[1]), ' · ', (p.locations || []).map(nice).join(', ') || 'no place yet'),
        h('div', { class: 'hint' }, (p.tags || []).map(tagLabel).join(', ') || 'no tags')),
      h('div', { class: 'card' }, h('div', { class: 'section-title' }, 'The animation'),
        h('div', {}, `${(p.length / p.fps).toFixed(1)} s loop · plays ${p.loops || 10}×`),
        h('div', { class: 'hint' }, p.sims.map(s => `${s.label}: ${(NAKED_LABEL[nakedFor(p.category, s)] || '').toLowerCase()}`).join(' · ')))),
    listBox,
    h('p', { class: 'hint' }, 'Writes it into your Mods folder. Restart The Sims 4 to see it. Motions, physics, faces, opening holes and sounds are all baked in.'));
  dlg = modal({
    title: 'Send to game', body,
    buttons: [
      { label: 'Cancel', kind: 'ghost' },
      { label: 'Send to game', kind: 'primary', onClick: async () => {
        if (sending) return false;
        if (draw()) { const f = markBoxes(); if (f) f.focus(); return false; }
        const btn = dlg.footer.lastChild;
        sending = true; btn.textContent = 'Sending...';
        try {
          if (inline && (typedName() !== p.name || typedAuthor() !== p.author)) {
            app.store.checkpoint();
            p.name = typedName();
            p.author = typedAuthor();
            app.refreshTitle();
          }
          localStorageSet('author', p.author);
          // saved first, so a name that is already used is sorted out before the package gets that name
          if (!(await app.save())) { sending = false; draw(); return false; }
          const res = await api.export(app.bake());
          showExported(app, res, p);
        } catch (err) {
          toast('Could not write the package: ' + err.message, 'err');
          sending = false; draw();
          return false;
        }
      } },
    ],
  });
  draw();
  // the first empty box gets the cursor (after the dialog's own focus, which would pick the first box)
  const first = markBoxes();
  if (first) setTimeout(() => { if (first.isConnected) first.focus({ preventScroll: true }); }, 60);
  return dlg;
}

// The success card. heroSlot (top) and extraSlot (bottom) stay empty here: the celebration and the "Did it play in
// the game?" line fill them from the wa:sent event.
export function showExported(app, res, p) {
  // the names of the animations that play next (older servers only sent the stage names)
  const next = res.next_names && res.next_names.length ? res.next_names
    : (res.next || []).map(x => x.replace(/^FitStudio_[^_]+_/, '').replace(/_[0-9a-f]{6}$/, '').replace(/_/g, ' '));
  const warnings = res.warnings || [];
  const heroSlot = h('div', { class: 'hero-slot' }), extraSlot = h('div', { class: 'extra-slot' });
  const dlg = modal({
    title: "It's in your Mods folder",
    body: h('div', {},
      heroSlot,
      h('div', { class: 'success' }, icon('check'), h('div', {},
        h('b', {}, `"${p.name}" by ${p.author} is ready.`),
        h('div', { class: 'path' }, res.path))),
      h('ol', {},
        h('li', {}, 'Start The Sims 4 (close and restart it if it is running - the game reads animations when it starts).'),
        h('li', {}, `Start sex with WickedWhims on ${(p.locations || []).map(nice).join(', ')} and pick "${p.name}".`)),
      next.length ? h('p', { class: 'hint' }, 'Then plays: ' + next.join(', ') + (res.random === false ? ' · reached only through its progression' : '')) : null,
      // things worth knowing: a progression step that is not in the game yet, an older copy that could not be moved...
      ...warnings.map(w => h('div', { class: 'warn-box' }, w)),
      res.replaced && res.replaced.length ? h('p', { class: 'hint' }, 'The older copy was taken out of your Mods folder, so it never shows twice.') : null,
      res.sound_kit ? h('p', { class: 'hint' }, `${res.sound_kit.sounds} sounds from parked packs were copied into your Mods so they play.`) : null,
      h('p', { class: 'hint' }, `${((res.bytes || 0) / 1024).toFixed(0)} KB. Sending again replaces it.`),
      extraSlot),
    buttons: [{ label: 'Done', kind: 'primary' }],
  });
  const first = localStorageGet('firstSend', null) === null;
  if (app && app.emit) app.emit('sent', { project: p, result: res, heroSlot, extraSlot, first });
  if (first) localStorageSet('firstSend', Date.now());
  return dlg;
}
