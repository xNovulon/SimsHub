// Use a sim from the Tray (adults only). With `pick` the dialog only picks a sim (e.g. to try its body) and calls
// pick({tray, index, name, first, frame}); `frame` ('yf' / 'ym') then lists only sims with that body.
import { h, modal, toast } from '../ui.js';
import { api } from '../api.js';
import { $t } from '../i18n.js';

const FRAME_OF = { male: 'ym', female: 'yf' };

export async function openTrayDialog(app, { pick = null, frame = null, title = null } = {}) {
<<<<<<< ours
  const body = h('div', {}, h('div', { class: 'hint' }, 'Reading your Tray...'));
  const dlg = modal({ title: title || 'Use a sim from my Tray',
    text: pick ? 'Adults only. Your animation doesn\'t change - you only see it on their body for a while.' : 'Adults only. The sim comes in with their body shape, skin and hair; their outfits can be shown in the Body step.',
    body, wide: true, buttons: [{ label: 'Close', kind: 'ghost' }] });
=======
  const body = h('div', {}, h('div', { class: 'hint' }, $t('dialogs.tray.reading_your_tray')));
  const dlg = modal({ title: title || $t('dialogs.tray.use_sim_from_my_tray'),
    text: pick ? $t('dialogs.tray.adults_only_your_animation_doesn') : $t('dialogs.tray.adults_only_sim_comes_in'),
    body, wide: true, buttons: [{ label: $t('dialogs.tray.close'), kind: 'ghost' }] });
>>>>>>> theirs
  let households;
  try { households = await api.tray(); } catch (e) { body.innerHTML = ''; body.append(h('div', { class: 'warn-box' }, $t('dialogs.tray.could_not_read_tray', { message: e.message }))); return; }
  const filter = h('input', { class: 'text', placeholder: $t('dialogs.tray.search_by_name') });
  const grid = h('div', { class: 'tiles', style: { maxHeight: '56vh', overflow: 'auto', gridTemplateColumns: 'repeat(4, 1fr)' } });
  const draw = () => {
    grid.innerHTML = '';
    const f = filter.value.toLowerCase().trim();
    for (const hh of households) hh.sims.forEach((s, i) => {
      if (!s.allowed) return;
      if (frame && frame !== 'yf_futa' && FRAME_OF[s.gender] !== frame) return;
      const nm = `${s.first} ${s.last}`.trim();
      if (f && !nm.toLowerCase().includes(f) && !hh.name.toLowerCase().includes(f)) return;
      grid.append(h('button', { class: 'tile', onclick: async () => {
        dlg.close();
        if (pick) { pick({ tray: hh.id, index: s.index, name: nm || 'Sim', first: s.first || 'Sim', frame: FRAME_OF[s.gender] || null }); return; }
        toast($t('dialogs.tray.loading', { nm }));
        try { await app.addTraySim(hh.id, s.index, nm); } catch (e) { toast($t('dialogs.tray.could_not_load_that_sim', { message: e.message }), 'err'); }
      } }, h('div', { class: 'thumb tray' }, h('img', { src: api.trayThumb(s.sim_id), alt: '', loading: 'lazy' })),
      h('b', {}, nm || $t('dialogs.tray.sim')), h('small', {}, `${s.gender} · ${s.age.replace('youngadult', 'young adult')} · ${hh.name}`)));
    });
    if (!grid.children.length) grid.append(h('div', { class: 'empty' }, frame ? $t('dialogs.tray.no_adult_sims_with_this') : $t('dialogs.tray.no_adult_sims_found')));
  };
  filter.oninput = draw;
  body.innerHTML = '';
  body.append(filter, h('div', { style: { height: '10px' } }), grid);
  draw();
}
