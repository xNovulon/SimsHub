// Open a saved animation.
import { h, modal, toast, confirmBox } from '../ui.js';
import { api } from '../api.js';
import { $t } from '../i18n.js';

export async function openProjectDialog(app) {
  let list;
  try { list = await api.projects(); } catch (e) { toast($t('dialogs.project.could_not_read_your_animations', { message: e.message }), 'err'); return; }
  const body = h('div', { class: 'proj-list' });
  if (!list.length) body.append(h('div', { class: 'empty' }, $t('dialogs.project.no_saved_animations_yet_save')));
  const dlg = modal({ title: $t('dialogs.project.open'), body, buttons: [{ label: $t('dialogs.project.close'), kind: 'ghost' }] });
  for (const it of list) {
    body.append(h('div', { class: 'proj-item', tabindex: '0', onclick: async () => {
      if (app.store.dirty && it.uid !== app.store.project.uid && !(await confirmBox($t('dialogs.project.open_another_animation'), $t('dialogs.project.unsaved_changes_to_this_one'), $t('dialogs.project.open'), true))) return;
      dlg.close();
      app.loadProject(it.file || it.name);
    }, onkeydown: e => { if (e.key === 'Enter') e.currentTarget.click(); } },
    h('b', {}, it.name, it.author ? h('span', { class: 'muted' }, ' by ' + it.author) : ''), h('span', { class: 'muted' }, new Date(it.modified * 1000).toLocaleString())));
  }
}
