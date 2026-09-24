// The name + creator dialog for a new animation, and "name it first" for flows that save.
import { h, modal } from '../ui.js';
import { localStorageSet, localStorageGet } from '../state.js';
import { $t } from '../i18n.js';

// A text box with its label and a red line under it when something is missing.
export function namedField(labelText, input) {
  const err = h('div', { class: 'field-err' });
  const field = h('label', { class: 'field' }, h('span', {}, labelText), input, err);
  const set = msg => { field.classList.toggle('invalid', !!msg); err.textContent = msg || ''; };
  input.addEventListener('input', () => set(''));
  return { field, set };
}

// title/text/okLabel let other flows reuse it (e.g. "Name it before exporting"); skip: false hides "Skip for now".
export function openNameDialog(app, done, { title = $t('dialogs.name.new_animation'), text = $t('dialogs.name.name_it_and_credit_creator'), okLabel = $t('dialogs.name.start_animating'), skip = true, value = '', onClose } = {}) {
  const last = app.store.project.author || localStorageGet('author', '') || '';
  const name = h('input', { class: 'text', placeholder: $t('dialogs.name.e_g_cowgirl_1'), spellcheck: 'false', value: value || '' });
  const author = h('input', { class: 'text', value: last, placeholder: $t('dialogs.name.e_g_novulon'), spellcheck: 'false' });
  const nameF = namedField($t('dialogs.name.animation_name'), name), authorF = namedField($t('dialogs.name.creator'), author);
  const preview = h('div', { class: 'name-preview' });
  const update = () => { preview.innerHTML = ''; preview.append(h('b', {}, name.value.trim() || $t('dialogs.name.animation_name')), h('span', {}, 'by ' + (author.value.trim() || 'creator'))); };
  name.addEventListener('input', update); author.addEventListener('input', update); update();
  // the problem is shown right at the box that needs it (not in a message far away)
  const submit = () => {
    let bad = null;
    if (!author.value.trim()) { authorF.set($t('dialogs.name.add_creator_name_short')); bad = author; }
    if (!name.value.trim() || /^untitled/i.test(name.value.trim())) { nameF.set($t('dialogs.name.give_animation_name')); bad = name; }
    if (bad) { bad.focus(); return false; }
    localStorageSet('author', author.value.trim());
    done(name.value.trim(), author.value.trim());
  };
  const buttons = [{ label: okLabel, kind: 'primary', onClick: submit }];
  // skipping starts right away with an untitled animation (a name can be given later in Details)
  if (skip) buttons.unshift({ label: $t('dialogs.name.skip_for_now'), kind: 'ghost', onClick: () => done(null, null) });
  else buttons.unshift({ label: $t('dialogs.name.cancel'), kind: 'ghost' });
  const dlg = modal({
    title, text, onClose,
    body: h('div', {}, h('div', { class: 'grid-2' }, nameF.field, authorF.field), preview),
    buttons,
  });
  [name, author].forEach(el => el.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); if (submit() !== false) dlg.close(); } }));
  return dlg;
}

// Make sure the open animation has a name and a creator before it is saved by another flow (progressions,
// exporting a mod). Resolves true when it has them (asking only if needed), false when the user cancelled.
export function ensureNamed(app, why = $t('dialogs.name.name_it_first')) {
  const p = app.store.project;
  if (p.name && !/^untitled/i.test(p.name) && p.author) return Promise.resolve(true);
  return new Promise(res => {
    let ok = false;
    openNameDialog(app, (name, author) => {
      ok = true;
      app.store.checkpoint();
      p.name = name; p.author = author;
      app.refreshTitle();
      if (app.step === 'details') app.renderStep();
      res(true);
    }, { title: why, text: $t('dialogs.name.it_is_saved_into_your'), okLabel: $t('dialogs.name.save'), skip: false,
      value: /^untitled/i.test(p.name || '') ? '' : p.name, onClose: () => { if (!ok) res(false); } });
  });
}
