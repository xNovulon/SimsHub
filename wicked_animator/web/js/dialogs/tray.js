// Use a sim from the Tray (adults only). With `pick` the dialog only picks a sim (e.g. to try its body) and calls
// pick({tray, index, name, first, frame}); `frame` ('yf' / 'ym') then lists only sims with that body.
import { h, icon, modal, toast } from '../ui.js';
import { api } from '../api.js';

const FRAME_OF = { male: 'ym', female: 'yf' };
const MINOR = { baby: 'Baby', infant: 'Infant', toddler: 'Toddler', child: 'Child', teen: 'Teen' };

// While a Tray sim loads (their body first, then hair and outfit): a card on the stage, so it's clear it's working.
function loadingCard(thumb, first) {
  const wrap = document.getElementById('viewport-wrap') || document.body;
  let list = wrap.querySelector('.tray-loads');
  if (!list) { list = h('div', { class: 'tray-loads' }); wrap.append(list); }
  const card = h('div', { class: 'tray-loading', role: 'status' },
    h('img', { src: thumb, alt: '' }),
    h('div', { class: 'grow' }, h('b', {}, `Loading ${first}...`), h('small', {}, 'Body, skin, hair and outfit')),
    h('div', { class: 'spin', 'aria-hidden': 'true' }));
  list.append(card);
  return { remove() { card.remove(); if (!list.children.length) list.remove(); } };
}

// resolves once the sim's outfit is on (or it has none, or it was removed), at most a minute and a half
async function dressed(app, sim) {
  const done = sim && app.trayDressing && app.trayDressing.get(sim.id);
  if (!done) return;
  await Promise.race([done, new Promise(r => setTimeout(r, 90000))]);
  app.trayDressing.delete(sim.id);
}

// A child or teen in the Tray: shown so the list matches the game, never loaded.
function minorNotice() {
  modal({
    title: 'Only adult sims can be used',
    body: h('div', { class: 'minor-note' },
      h('div', { class: 'minor-ic' }, icon('shield')),
      h('div', {},
        h('p', {}, 'Children and teens can\'t be added to Wicked Animator. It makes adult animations, so only young adult, adult and elder sims can be used.'),
        h('p', { class: 'muted' }, 'This is always on and can\'t be changed. Their details and pictures are never loaded.'))),
    buttons: [{ label: 'OK', kind: 'primary' }],
  });
}

export async function openTrayDialog(app, { pick = null, frame = null, title = null } = {}) {
  const body = h('div', {}, h('div', { class: 'hint' }, 'Reading your Tray...'));
  const dlg = modal({ title: title || 'Use a sim from my Tray',
    text: pick ? 'Adults only. Your animation doesn\'t change - you only see it on their body for a while.' : 'Adults only. The sim comes in looking the way they do in your game: body, skin, makeup, hair and outfit. Clothes can be taken off in the Body step.',
    body, wide: true, buttons: [{ label: 'Close', kind: 'ghost' }] });
  let households;
  try { households = await api.tray(); } catch (e) { body.innerHTML = ''; body.append(h('div', { class: 'warn-box' }, 'Could not read the Tray: ' + e.message)); return; }
  const filter = h('input', { class: 'text', placeholder: 'Search by name...' });
  const grid = h('div', { class: 'tiles', style: { maxHeight: '56vh', overflow: 'auto', gridTemplateColumns: 'repeat(4, 1fr)' } });
  const draw = () => {
    grid.innerHTML = '';
    const f = filter.value.toLowerCase().trim();
    for (const hh of households) hh.sims.forEach((s, i) => {
      if (!s.allowed) {
        // a child or teen: a locked tile without a picture
        if (pick || (f && !(s.first || '').toLowerCase().includes(f) && !hh.name.toLowerCase().includes(f))) return;
        grid.append(h('button', { class: 'tile tile-locked', title: 'Children and teens can\'t be used', onclick: minorNotice },
          h('div', { class: 'thumb tray locked' }, icon('shield')),
          h('b', {}, (s.first || MINOR[s.age] || 'Sim').replace(/^./, c => c.toUpperCase())), h('small', {}, `${MINOR[s.age] || 'Under 18'} · ${hh.name} · can't be used`)));
        return;
      }
      if (frame && frame !== 'yf_futa' && FRAME_OF[s.gender] !== frame) return;
      const nm = `${s.first} ${s.last}`.trim();
      if (f && !nm.toLowerCase().includes(f) && !hh.name.toLowerCase().includes(f)) return;
      grid.append(h('button', { class: 'tile', onclick: async () => {
        dlg.close();
        if (pick) { pick({ tray: hh.id, index: s.index, name: nm || 'Sim', first: s.first || 'Sim', frame: FRAME_OF[s.gender] || null }); return; }
        const card = loadingCard(api.trayThumb(s.sim_id), (s.first || nm || 'Sim').replace(/^./, c => c.toUpperCase()));
        try {
          const sim = await app.addTraySim(hh.id, s.index, nm);
          await dressed(app, sim);
        } catch (e) { toast('Could not load that sim: ' + e.message, 'err'); }
        finally { card.remove(); }
      } }, h('div', { class: 'thumb tray' }, h('img', { src: api.trayThumb(s.sim_id), alt: '', loading: 'lazy' })),
      h('b', {}, nm || 'Sim'), h('small', {}, `${s.gender} · ${s.age.replace('youngadult', 'young adult')} · ${hh.name}`)));
    });
    // adults first, then the locked children and teens
    [...grid.querySelectorAll('.tile-locked')].forEach(t => grid.append(t));
    if (!grid.querySelector('.tile:not(.tile-locked)')) grid.prepend(h('div', { class: 'empty', style: { gridColumn: '1 / -1' } }, frame ? 'No adult sims with this body found.' : 'No adult sims found.'));
  };
  filter.oninput = draw;
  body.innerHTML = '';
  body.append(filter, h('div', { style: { height: '10px' } }), grid);
  draw();
}
