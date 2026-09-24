// Open a saved animation.
import { h, modal, toast, confirmBox } from '../ui.js';
import { api } from '../api.js';

export async function openProjectDialog(app) {
  let list;
  try { list = await api.projects(); } catch (e) { toast('Could not read your animations: ' + e.message, 'err'); return; }
  const body = h('div', { class: 'proj-list' });
  if (!list.length) body.append(h('div', { class: 'empty' }, 'No saved animations yet. Save with Ctrl+S.'));
  const dlg = modal({ title: 'Open', body, buttons: [{ label: 'Close', kind: 'ghost' }] });
  for (const it of list) {
    body.append(h('div', { class: 'proj-item', tabindex: '0', onclick: async () => {
      if (app.store.dirty && it.uid !== app.store.project.uid && !(await confirmBox('Open another animation?', 'Unsaved changes to this one will be lost.', 'Open', true))) return;
      dlg.close();
      app.loadProject(it.file || it.name);
    }, onkeydown: e => { if (e.key === 'Enter') e.currentTarget.click(); } },
    h('b', {}, it.name, it.author ? h('span', { class: 'muted' }, ' by ' + it.author) : ''), h('span', { class: 'muted' }, new Date(it.modified * 1000).toLocaleString())));
  }
}
