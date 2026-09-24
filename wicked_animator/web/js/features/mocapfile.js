// "Import a motion file" (BVH) in the app: a button under the Pose step's "Copy real moves" (next to From a video /
// webcam / photo), a card in the Library, Ctrl+K commands, a Help row, and a .bvh (or .fbx, which gets the "export
// BVH instead" message) dropped anywhere on the window. The dialog (web/js/mocapfile.js) loads only when used.
// Everything registers through app.hooks and the DOM, so main.js, index.html and features/capture.js stay untouched.
import { h, icon, section, addIcon } from '../ui.js';
import { $t } from '../i18n.js';

// the icons this uses (added to the app's sprite sheet once)
function ensureIcons() {
  addIcon('mf-bvh', '<path d="M14 3H7.5A1.5 1.5 0 0 0 6 4.5v15A1.5 1.5 0 0 0 7.5 21h9a1.5 1.5 0 0 0 1.5-1.5V7z" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round"/><path d="M14 3v4h4" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round"/><circle cx="12" cy="9.3" r="1.3" fill="currentColor"/><path d="M12 11v3.6m0 0-2 3m2-3 2 3M9.3 12.4h5.4" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/>');
  addIcon('mf-warn', '<path d="M12 4 21 19.5H3z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="M12 10v4.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17" r="1.05" fill="currentColor"/>');
}

let mod = null, loaded = null;
const load = () => (mod = mod || import('../mocapfile.js').then(m => (loaded = m)));
const open = (app, file = null) => load().then(m => m.openMotionFile(app, { file, simId: app.store.selected && app.store.selected.sim }))
  .catch(e => console.error('motion file', e));
const isMotionFile = f => /\.(bvh|fbx)$/i.test((f && f.name) || '');

function button(app, cls) {
  return h('button', { class: cls, 'data-mocapfile': 'open', title: $t('features.mocapfile.bvh_file_from_mocap_library'), onclick: () => open(app) },
    h('span', { class: 'mf-entry-icon' }, icon('mf-bvh')),
    h('span', { class: 'mf-entry-text' }, h('b', {}, $t('features.mocapfile.from_motion_file')), h('small', {}, $t('features.mocapfile.bvh_from_mocap_or_ai'))));
}

export function install(app) {
  if (!app || app.__mocapfile) return;
  app.__mocapfile = true;
  ensureIcons();
  const hk = app.hooks || {};
  const add = (name, fn) => { if (Array.isArray(hk[name])) hk[name].push(fn); };

  // Pose step: right under the capture's three buttons (its own section when "Copy real moves" isn't there)
  if (hk.sections && Array.isArray(hk.sections.pose)) {
    hk.sections.pose.push((a, root) => {
      const btn = button(a, 'mf-entry-btn');
      const cap = root.querySelector('.cap-entry');
      if (cap) cap.after(btn);
      else root.append(section($t('features.mocapfile.copy_real_moves'), btn));
    });
  }

  // Library: a card under the search list
  try {
    const lib = app.library && app.library.root;
    if (lib && !lib.querySelector('[data-mocapfile]')) {
      lib.append(h('div', { class: 'mf-lib' },
        h('div', { class: 'mf-lib-text' }, h('b', {}, $t('features.mocapfile.have_motion_file')),
          h('span', {}, $t('features.mocapfile.import_bvh_from_mocap_library'))),
        h('button', { class: 'btn soft small', 'data-mocapfile': 'library', onclick: () => open(app) }, icon('mf-bvh'), $t('features.mocapfile.import_motion_file'))));
    }
  } catch (e) { console.error('motion file: library card', e); }

  add('commands', a => [
    { group: $t('features.mocapfile.actions'), id: 'mocap-file', label: $t('features.mocapfile.import_motion_file_bvh'), icon: 'mf-bvh', sub: $t('features.mocapfile.mocap_or_ai_tools_rokoko'),
      words: 'bvh mocap motion capture file import rokoko deepmotion plask mixamo cmu fbx animation keys', run: () => open(a) },
  ]);
  add('helpRows', () => [
    { group: $t('features.mocapfile.copy_real_moves'), keys: ['Ctrl', 'K'], text: $t('features.mocapfile.type_motion_file_to_import') },
    { group: $t('features.mocapfile.copy_real_moves'), keys: 'Drop a .bvh file', text: $t('features.mocapfile.on_stage_to_put_its') },
  ]);

  // a .bvh / .fbx dropped anywhere: the dialog (before the stage's own drop, which only takes pictures and videos)
  window.addEventListener('drop', e => {
    const files = [...((e.dataTransfer && e.dataTransfer.files) || [])];
    const f = files.find(isMotionFile);
    if (!f) return;
    // another dialog is open (the capture studio, the reference picker...): leave it to that one, unless it's ours
    const ours = !!(loaded && loaded.isOpen());
    if (!ours && document.querySelector('#modal-root .backdrop:not(.leaving), .cap-backdrop')) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const zone = document.getElementById('drop-zone');
    if (zone) zone.classList.add('hidden');
    open(app, f);
  }, true);
}

export default install;
