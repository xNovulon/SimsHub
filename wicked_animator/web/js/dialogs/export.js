// Send to game: what WickedWhims needs is checked first, then the package goes into the Mods folder.
import { h, icon, modal, toast, toggleRow } from '../ui.js';
import { api } from '../api.js';
import { localStorageSet, localStorageGet } from '../state.js';
import { tagLabel, nakedFor, NAKED_CHOICES, KINDS } from '../tags.js';
import { namedField } from './name.js';
<<<<<<< ours
import { FIT_TITLE, FIT_TEXT, fitHolds } from '../features/bodyfit.js';
=======
import { $t } from '../i18n.js';
>>>>>>> theirs
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
  if (!p.name || /^untitled/i.test(p.name)) add('error', $t('dialogs.export.give_animation_name'), () => app.showStep('details'), 'name');
  if (!p.author) add('error', $t('dialogs.export.add_creator_name_wickedwhims_shows'), () => app.showStep('details'), 'author');
  if (!(p.locations || []).length) add('error', $t('dialogs.export.pick_at_least_one_place'), () => app.showStep('details'));
  if (!p.sims.length) add('error', $t('dialogs.export.add_at_least_one_sim'), () => app.showStep('scene'));
  // a face key alone is not a pose: every sim needs a body key
  if (p.sims.some(s => !s.keys.some(k => !k.faceOnly))) add('error', $t('dialogs.export.every_sim_needs_at_least'), () => app.showStep('pose'));
  if (p.category === 'CLIMAX' && (p.loops || 10) > 2) add('info', $t('dialogs.export.climax_animations_usually_play_once'), () => app.showStep('details'));
  if ((p.tags || []).length === 0) add('info', $t('dialogs.export.no_tags_yet_tags_help'), () => app.showStep('details'));
  if (!p.sims.some(s => (s.sounds || []).length)) add('info', $t('dialogs.export.no_sounds_place_sounds_for'), () => app.showStep('sounds'));
  for (const list of app.runHook ? app.runHook('exportChecks', p) : []) {
    for (const x of Array.isArray(list) ? list : []) {
      if (!x || !x.text) continue;
      const go = () => {
        if (x.simId && app.store.sim(x.simId)) app.selectSim(x.simId);
        if (typeof x.frame === 'number') app.setFrame(x.frame);
      };
      out.push({ level: x.level === 'error' ? 'error' : 'warn', text: x.text,
        fix: x.fix && typeof x.fix.run === 'function' ? () => { go(); x.fix.run(); } : (typeof x.frame === 'number' || x.simId ? go : null),
        fixLabel: x.fix && x.fix.label ? x.fix.label : (typeof x.frame === 'number' ? $t('dialogs.export.show_me') : null) });
    }
  }
  return out;
}

export function openExportDialog(app) {
  const p = app.store.project;
  let dlg = null, sending = false;
  // a missing name or creator is typed right here - no trip to Details and back
  const nameIn = h('input', { class: 'text', value: /^untitled/i.test(p.name || '') ? '' : (p.name || ''), placeholder: $t('dialogs.export.e_g_cowgirl_1'), spellcheck: 'false' });
  const authorIn = h('input', { class: 'text', value: p.author || localStorageGet('author', '') || '', placeholder: $t('dialogs.export.e_g_novulon'), spellcheck: 'false' });
  const needName = !p.name || /^untitled/i.test(p.name), needAuthor = !p.author;
  // an empty box that is needed is marked red with what to type, and the cursor waits in the first one
  const nameF = namedField($t('dialogs.export.animation_name'), nameIn), authorF = namedField($t('dialogs.export.creator'), authorIn);
  const inline = needName || needAuthor ? h('div', { class: 'card inline-name' },
    h('div', { class: 'section-title' }, $t('dialogs.export.name_it')),
    h('div', { class: 'grid-2' }, nameF.field, authorF.field)) : null;
  const badName = () => !nameIn.value.trim() || /^untitled/i.test(nameIn.value.trim()), badAuthor = () => !authorIn.value.trim();
  const markBoxes = () => {
    if (!inline) return null;
    nameF.set(badName() ? $t('dialogs.export.give_animation_name') : '');
    authorF.set(badAuthor() ? $t('dialogs.export.add_creator_name_wickedwhims_shows_2') : '');
    return badName() ? nameIn : badAuthor() ? authorIn : null;
  };
  // when the boxes are shown, what is typed in them is what gets used (both boxes)
  const typedName = () => (inline ? nameIn.value.trim() : p.name);
  const typedAuthor = () => (inline ? authorIn.value.trim() : p.author);
  // the name and creator are checked at their boxes above when they are typed here
  const current = () => exportChecks(app).filter(x => !(inline && (x.key === 'name' || x.key === 'author')));
  const listBox = h('div', { style: { marginTop: '10px' } });
  const preview = h('div', { class: 'name-preview' });
  const drawPreview = () => { preview.innerHTML = ''; preview.append(h('b', {}, typedName() || $t('dialogs.export.animation_name')), h('span', {}, 'by ' + (typedAuthor() || '?'))); };
  const missingTyped = () => !!inline && (!typedName() || /^untitled/i.test(typedName()) || !typedAuthor());
  const draw = () => {
    drawPreview();
    const list = current();
    listBox.innerHTML = '';
    for (const x of list) listBox.append(h('div', { class: x.level === 'error' ? 'warn-box error' : x.level === 'warn' ? 'warn-box' : 'tip' }, h('span', {}, x.text),
      x.fix ? h('button', { class: 'btn small', style: { marginLeft: 'auto' }, onclick: () => { dlg.close(); x.fix(); } }, x.fixLabel || $t('dialogs.export.fix')) : null));
    const blocked = list.some(x => x.level === 'error') || missingTyped();
    if (dlg) {
      const btn = dlg.footer.lastChild;
      if (!sending) { btn.disabled = blocked; btn.textContent = blocked ? $t('dialogs.export.fill_in_missing_items_above') : $t('dialogs.export.send_to_game'); }
    }
    return blocked;
  };
  // typing clears a box's red mark (namedField), and a box left empty again is marked again
<<<<<<< ours
  nameIn.addEventListener('input', () => { if (badName()) nameF.set('Give the animation a name.'); draw(); });
  authorIn.addEventListener('input', () => { if (badAuthor()) authorF.set('Add a creator name - WickedWhims shows "by ..."'); draw(); });
  // experimental, off by default, kept in the animation (features/bodyfit.js)
  const fitNote = h('div', { class: 'hint fit-note' });
  const drawFit = () => {
    const { fit, partial } = fitHolds(p);
    fitNote.textContent = !p.fitBodies ? '' : fit.length
      ? `${fit.length} hold${fit.length === 1 ? '' : 's'} will be fitted${partial.length ? `; ${partial.length} that hold${partial.length === 1 ? 's' : ''} for part of the loop only will not` : ''}.`
      : '';
  };
  const fitRow = () => {
    drawFit();
    return h('div', { class: 'fit-bodies' }, toggleRow(FIT_TITLE, FIT_TEXT, !!p.fitBodies, on => {
      if (on) p.fitBodies = true; else delete p.fitBodies;
      app.store.setDirty(true);
      drawFit(); draw();
    }), fitNote);
  };
=======
  nameIn.addEventListener('input', () => { if (badName()) nameF.set($t('dialogs.export.give_animation_name')); draw(); });
  authorIn.addEventListener('input', () => { if (badAuthor()) authorF.set($t('dialogs.export.add_creator_name_short')); draw(); });
>>>>>>> theirs
  const body = h('div', {},
    preview, inline,
    h('div', { class: 'grid-2', style: { marginTop: '10px' } },
      h('div', { class: 'card' }, h('div', { class: 'section-title' }, $t('dialogs.export.in_wickedwhims')),
        h('div', {}, h('b', {}, (KINDS.find(k => k[0] === p.category) || ['', p.category])[1]), ' · ', (p.locations || []).map(nice).join(', ') || $t('dialogs.export.no_place_yet')),
        h('div', { class: 'hint' }, (p.tags || []).map(tagLabel).join(', ') || $t('dialogs.export.no_tags'))),
      h('div', { class: 'card' }, h('div', { class: 'section-title' }, $t('dialogs.export.animation')),
        h('div', {}, $t('dialogs.export.s_loop_plays', { pCount: (p.length / p.fps).toFixed(1), loops: p.loops || 10 })),
        h('div', { class: 'hint' }, p.sims.map(s => `${s.label}: ${(NAKED_LABEL[nakedFor(p.category, s)] || '').toLowerCase()}`).join(' · ')))),
    fitRow(),
    listBox,
    h('p', { class: 'hint' }, $t('dialogs.export.writes_it_into_your_mods')));
  dlg = modal({
    title: $t('dialogs.export.send_to_game'), body,
    buttons: [
      { label: $t('dialogs.export.cancel'), kind: 'ghost' },
      { label: $t('dialogs.export.send_to_game'), kind: 'primary', onClick: async () => {
        if (sending) return false;
        if (draw()) { const f = markBoxes(); if (f) f.focus(); return false; }
        const btn = dlg.footer.lastChild;
        sending = true; btn.textContent = $t('dialogs.export.sending');
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
          toast($t('dialogs.export.could_not_write_package', { message: err.message }), 'err');
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
    title: $t('dialogs.export.it_s_in_your_mods'),
    body: h('div', {},
      heroSlot,
      h('div', { class: 'success' }, icon('check'), h('div', {},
        h('b', {}, $t('dialogs.export.by_is_ready', { pName: p.name, author: p.author })),
        h('div', { class: 'path' }, res.path))),
      h('ol', {},
        h('li', {}, $t('dialogs.export.start_sims_4_close_and')),
        h('li', {}, $t('dialogs.export.start_sex_with_wickedwhims_on', { map: (p.locations || []).map(nice).join(', '), pName: p.name }))),
      next.length ? h('p', { class: 'hint' }, (res.random === false ? $t('dialogs.export.then_plays_chain_only', { next: next.join(', ') }) : $t('dialogs.export.then_plays', { next: next.join(', ') }))) : null,
      // things worth knowing: a progression step that is not in the game yet, an older copy that could not be moved...
      ...warnings.map(w => h('div', { class: 'warn-box' }, w)),
<<<<<<< ours
      res.replaced && res.replaced.length ? h('p', { class: 'hint' }, 'The older copy was taken out of your Mods folder, so it never shows twice.') : null,
      res.sound_kit ? h('p', { class: 'hint' }, `${res.sound_kit.sounds} sounds from parked packs were copied into your Mods so they play.`) : null,
      res.own_sounds ? h('p', { class: 'hint' }, `${res.own_sounds === 1 ? 'Your own sound is' : res.own_sounds + ' of your own sounds are'} packed inside it.`) : null,
      res.fit_bodies ? h('div', { class: 'warn-box fit-test' }, `Experimental: ${res.fit_bodies === 1 ? '1 held hand or foot is' : res.fit_bodies + ' held hands and feet are'} fitted to each body. How to test: play it with sims of clearly different heights and builds - held hands and feet should stay on the spot they hold. If a limb looks wrong, send it again with the switch off.`) : null,
      h('p', { class: 'hint' }, `${((res.bytes || 0) / 1024).toFixed(0)} KB. Sending again replaces it.`),
=======
      res.replaced && res.replaced.length ? h('p', { class: 'hint' }, $t('dialogs.export.older_copy_was_taken_out')) : null,
      res.sound_kit ? h('p', { class: 'hint' }, $t('dialogs.export.sounds_from_parked_packs_were', { sounds: res.sound_kit.sounds })) : null,
      res.own_sounds ? h('p', { class: 'hint' }, $t('dialogs.export.own_sounds_packed', { n: res.own_sounds })) : null,
      h('p', { class: 'hint' }, $t('dialogs.export.kb_sending_again_replaces_it', { bytes: ((res.bytes || 0) / 1024).toFixed(0) })),
>>>>>>> theirs
      extraSlot),
    buttons: [{ label: $t('dialogs.export.done'), kind: 'primary' }],
  });
  const first = localStorageGet('firstSend', null) === null;
  if (app && app.emit) app.emit('sent', { project: p, result: res, heroSlot, extraSlot, first });
  if (first) localStorageSet('firstSend', Date.now());
  return dlg;
}
