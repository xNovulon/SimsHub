// The Details tab: name, creator, kind, tags, places, undressing - what WickedWhims shows and sorts by.
import { h, icon } from './ui.js';
import { KINDS, TAG_GROUPS, tagLabel, kindForTags, NAKED_CHOICES, nakedFor } from './tags.js';
import { WW_LOCATIONS } from './dialogs.js';
import { localStorageSet } from './state.js';

const ROLE_LABEL = { giver: 'Gives', receiver: 'Receives', both: 'Both' };
// where WickedWhims puts cum on a sim when the sex ends (sim.cumAfter: missing/'AUTO' | 'NONE' | [parts])
const CUM_AFTER_PARTS = [['FACE', 'Face'], ['CHEST', 'Chest'], ['BELLY', 'Belly'], ['UPPER_BACK', 'Upper back'], ['LOWER_BACK', 'Lower back'],
  ['VAGINA', 'Vagina'], ['BUTT', 'Butt'], ['FEET', 'Feet']];

function cumAfterRow(app, sim, change) {
  const cur = sim.cumAfter;
  const mode = Array.isArray(cur) ? 'PICK' : cur === 'NONE' ? 'NONE' : 'AUTO';
  const penis = sim.frame === 'ym' || sim.frame === 'yf_futa';
  const sel = h('select', {}, [['AUTO', 'Automatic'], ['NONE', 'Nowhere'], ['PICK', 'Pick the parts…']].map(([v, t]) => h('option', { value: v, selected: v === mode }, t)));
  sel.addEventListener('change', () => change(() => {
    if (sel.value === 'AUTO') delete sim.cumAfter;
    else if (sel.value === 'NONE') sim.cumAfter = 'NONE';
    else sim.cumAfter = Array.isArray(sim.cumAfter) && sim.cumAfter.length ? sim.cumAfter : ['FACE'];
  }));
  const parts = mode === 'PICK' ? h('div', { class: 'chips cum-after' }, CUM_AFTER_PARTS.filter(([t]) => !(t === 'VAGINA' && penis)).map(([t, label]) => h('button', {
    class: 'chipbtn' + (cur.includes(t) ? ' on' : ''), type: 'button',
    onclick: () => change(() => {
      const next = cur.includes(t) ? cur.filter(x => x !== t) : [...cur, t];
      sim.cumAfter = next.length ? next : 'NONE';
    }),
  }, label))) : null;
  return h('div', { class: 'cum-after-row' }, h('label', { class: 'field row' }, h('span', {}, 'After sex, cum shows on'), sel), parts);
}
const nice = s => s.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

export function renderDetails(app, root) {
  if (!root) return;
  const p = app.store.project;
  p.tags = p.tags || [];
  const change = (fn, rerender = true) => { app.store.checkpoint(); fn(); app.store.setDirty(true); app.refreshTitle(); if (rerender) app.renderStep(); };

  // name and creator
  const name = h('input', { class: 'text', value: p.name, placeholder: 'e.g. Cowgirl 1', spellcheck: 'false' });
  name.addEventListener('change', () => change(() => { p.name = name.value.trim() || 'Untitled animation'; }, false));
  const creator = h('input', { class: 'text', value: p.author || '', placeholder: 'e.g. Novulon', spellcheck: 'false' });
  creator.addEventListener('change', () => change(() => { p.author = creator.value.trim(); localStorageSet('author', p.author); }, false));
  root.append(
    h('div', { class: 'section-title' }, 'Name & creator'),
    h('label', { class: 'field' }, h('span', {}, 'Animation name'), name),
    h('label', { class: 'field' }, h('span', {}, 'Creator (shown as "by ..." in WickedWhims)'), creator));

  // kind
  root.append(h('div', { class: 'section-title', style: { marginTop: '18px' } }, 'Kind'),
    h('div', { class: 'chips' }, KINDS.map(([v, t]) => h('button', {
      class: 'chipbtn kind' + (p.category === v ? ' on' : ''), onclick: () => change(() => { p.category = v; }),
    }, t))));

  // tags
  const selected = new Set(p.tags);
  root.append(h('div', { class: 'section-title', style: { marginTop: '18px' } }, 'Tags', h('span', { class: 'count' }, selected.size ? `${selected.size} picked` : '')));
  if (selected.size) {
    root.append(h('div', { class: 'chips picked' }, [...selected].map(t => h('button', {
      class: 'chipbtn on', title: 'Remove', onclick: () => change(() => { p.tags = p.tags.filter(x => x !== t); }),
    }, tagLabel(t), ' ×'))));
  }
  const filter = h('input', { class: 'text', placeholder: 'Find a tag (cowgirl, femdom, vampire...)', spellcheck: 'false', value: app._tagFilter || '' });
  root.append(filter);
  const groups = h('div', { class: 'tag-groups' });
  const draw = () => {
    groups.innerHTML = '';
    const f = filter.value.toLowerCase().trim();
    for (const [group, tags] of TAG_GROUPS) {
      const shown = tags.filter(t => !f || tagLabel(t).toLowerCase().includes(f) || t.toLowerCase().includes(f));
      if (!shown.length) continue;
      groups.append(h('div', { class: 'tag-group' }, h('span', {}, group),
        h('div', { class: 'chips' }, shown.map(t => h('button', {
          class: 'chipbtn' + (selected.has(t) ? ' on' : ''),
          onclick: () => change(() => {
            p.tags = selected.has(t) ? p.tags.filter(x => x !== t) : [...p.tags, t];
            p.category = kindForTags(p.tags, p.category);
          }),
        }, tagLabel(t))))));
    }
  };
  filter.addEventListener('input', () => { app._tagFilter = filter.value; draw(); });
  draw();
  root.append(groups);

  // places
  const locs = new Set(p.locations || []);
  root.append(h('div', { class: 'section-title', style: { marginTop: '18px' } }, 'Offered on', h('span', { class: 'count' }, `${locs.size} place${locs.size === 1 ? '' : 's'}`)),
    h('div', { class: 'chips' }, WW_LOCATIONS.map(l => h('button', {
      class: 'chipbtn place' + (locs.has(l) ? ' on' : ''),
      onclick: () => change(() => { p.locations = locs.has(l) ? p.locations.filter(x => x !== l) : [...(p.locations || []), l]; }),
    }, nice(l)))));

  // each sim in the game: undressing, its part in the act, bare feet, strap-on
  const NAKED_LABEL = Object.fromEntries(NAKED_CHOICES);
  root.append(h('div', { class: 'section-title', style: { marginTop: '18px' } }, 'Each sim in the game'));
  for (const sim of p.sims) {
    const auto = nakedFor(p.category, { gender: sim.gender });
    const sel = h('select', {}, NAKED_CHOICES.map(([v, t]) => h('option', { value: v, selected: (sim.naked || 'AUTO') === v },
      v === 'AUTO' ? `Auto - ${NAKED_LABEL[auto].toLowerCase()}` : t)));
    sel.addEventListener('change', () => change(() => { sim.naked = sel.value; }));
    const autoRole = app.roleOf({ ...sim, role: undefined });
    const role = h('select', {}, [['', `Auto - ${ROLE_LABEL[autoRole].toLowerCase()}`], ['giver', ROLE_LABEL.giver], ['receiver', ROLE_LABEL.receiver], ['both', ROLE_LABEL.both]]
      .map(([v, t]) => h('option', { value: v, selected: (sim.role || '') === v }, t)));
    role.addEventListener('change', () => change(() => { if (role.value) sim.role = role.value; else delete sim.role; }));
    const feetAuto = app.bareFeetOf({ ...sim, bareFeet: undefined }, p);
    const feet = h('input', { type: 'checkbox', checked: app.bareFeetOf(sim, p) });
    feet.addEventListener('change', () => change(() => { sim.bareFeet = feet.checked; }));
    // a strap-on only makes sense for a sim without a penis
    const female = sim.frame !== 'ym' && sim.frame !== 'yf_futa';
    const strap = h('input', { type: 'checkbox', checked: !!sim.strapon });
    strap.addEventListener('change', () => change(() => { sim.strapon = strap.checked; }));
    root.append(h('div', { class: 'sim-game', style: { '--sim': sim.color } },
      h('b', { class: 'who' }, sim.label),
      h('label', { class: 'field row' }, h('span', {}, 'Undressing'), sel),
      h('label', { class: 'field row' }, h('span', {}, 'In the act'), role),
      h('label', { class: 'check', title: feetAuto ? 'On by itself for footjobs and on beds and sofas' : '' }, feet, 'Bare feet', h('span', { class: 'muted small' }, feetAuto ? ' (on by itself here)' : '')),
      female ? h('label', { class: 'check', title: 'WickedWhims may give this sim a strap-on when the other sim has no penis' }, strap, 'Allow strap-on') : null,
      cumAfterRow(app, sim, change)));
  }
  root.append(h('div', { class: 'hint' }, 'Automatic undressing follows the kind: vaginal, anal and climax take everything off, oral and handjob the bottoms, teasing nothing. "In the act" tells WickedWhims who gives and who receives. "After sex, cum shows on": where WickedWhims puts cum on this sim when the sex ends (Automatic goes by the kind of sex).'));

  // progressions live in step 8 now
  root.append(...[
    h('div', { class: 'section-title', style: { marginTop: '18px' } }, 'Plays next'),
    (p.next || []).length ? h('div', { class: 'hint' }, 'Old link: then plays ', h('b', {}, p.next.map(n => n.name).join(', ')), ' ',
      h('button', { class: 'btn small ghost', onclick: () => change(() => { p.next = []; }) }, 'Remove')) : null,
    h('div', { class: 'hint' }, 'To play animations one after another (oral → handjob → cowgirl), make a progression in step 8.'),
    h('button', { class: 'btn small', onclick: () => app.showStep('share') }, icon('chain'), 'Progressions'),
  ].filter(Boolean));

  // how long it plays in the game
  const loops = h('input', { class: 'text', type: 'number', min: 1, max: 120, value: p.loops || 10 });
  loops.addEventListener('change', () => change(() => { p.loops = Math.max(1, +loops.value || 10); }, false));
  root.append(h('div', { class: 'section-title', style: { marginTop: '18px' } }, 'In the game'),
    h('label', { class: 'field' }, h('span', {}, 'How many times it repeats before moving on'), loops),
    h('div', { class: 'hint' }, `One loop is ${(p.length / (p.fps || 30)).toFixed(1)} s, so it plays about ${Math.round(p.length / (p.fps || 30) * (p.loops || 10))} s in the game. Climax animations usually play once.`));
}
