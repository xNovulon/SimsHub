// The Details tab: name, creator, kind, tags, places, undressing - what WickedWhims shows and sorts by.
import { h, icon } from './ui.js';
import { KINDS, TAG_GROUPS, tagLabel, kindForTags, NAKED_CHOICES, nakedFor } from './tags.js';
import { WW_LOCATIONS } from './dialogs.js';
import { localStorageSet } from './state.js';
import { $t, inSentence } from './i18n.js';

const ROLE_LABEL = { giver: $t('details.gives'), receiver: $t('details.receives'), both: $t('details.both') };
// where WickedWhims puts cum on a sim when the sex ends (sim.cumAfter: missing/'AUTO' | 'NONE' | [parts])
const CUM_AFTER_PARTS = [['FACE', $t('details.face')], ['CHEST', $t('details.chest')], ['BELLY', $t('details.belly')], ['UPPER_BACK', $t('details.upper_back')], ['LOWER_BACK', $t('details.lower_back')],
  ['VAGINA', $t('details.vagina')], ['BUTT', $t('details.butt')], ['FEET', $t('details.feet')]];

function cumAfterRow(app, sim, change) {
  const cur = sim.cumAfter;
  const mode = Array.isArray(cur) ? 'PICK' : cur === 'NONE' ? 'NONE' : 'AUTO';
  const penis = sim.frame === 'ym' || sim.frame === 'yf_futa';
  const sel = h('select', {}, [['AUTO', $t('details.automatic')], ['NONE', $t('details.nowhere')], ['PICK', $t('details.pick_parts')]].map(([v, t]) => h('option', { value: v, selected: v === mode }, t)));
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
  return h('div', { class: 'cum-after-row' }, h('label', { class: 'field row' }, h('span', {}, $t('details.after_sex_cum_shows_on')), sel), parts);
}
const nice = s => s.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

export function renderDetails(app, root) {
  if (!root) return;
  const p = app.store.project;
  p.tags = p.tags || [];
  const change = (fn, rerender = true) => { app.store.checkpoint(); fn(); app.store.setDirty(true); app.refreshTitle(); if (rerender) app.renderStep(); };

  // name and creator
  const name = h('input', { class: 'text', value: /^untitled animation$/i.test(p.name || '') ? $t('details.untitled_animation') : p.name, placeholder: $t('details.e_g_cowgirl_1'), spellcheck: 'false' });
  name.addEventListener('change', () => change(() => { p.name = name.value.trim() || 'Untitled animation'; }, false));
  const creator = h('input', { class: 'text', value: p.author || '', placeholder: $t('details.e_g_novulon'), spellcheck: 'false' });
  creator.addEventListener('change', () => change(() => { p.author = creator.value.trim(); localStorageSet('author', p.author); }, false));
  root.append(
    h('div', { class: 'section-title' }, $t('details.name_creator')),
    h('label', { class: 'field' }, h('span', {}, $t('details.animation_name')), name),
    h('label', { class: 'field' }, h('span', {}, $t('details.creator_shown_as_by_in')), creator));

  // kind
  root.append(h('div', { class: 'section-title', style: { marginTop: '18px' } }, $t('details.kind')),
    h('div', { class: 'chips' }, KINDS.map(([v, t]) => h('button', {
      class: 'chipbtn kind' + (p.category === v ? ' on' : ''), onclick: () => change(() => { p.category = v; }),
    }, t))));

  // tags
  const selected = new Set(p.tags);
  root.append(h('div', { class: 'section-title', style: { marginTop: '18px' } }, $t('details.tags'), h('span', { class: 'count' }, selected.size ? $t('details.n_picked', { n: selected.size }) : '')));
  if (selected.size) {
    root.append(h('div', { class: 'chips picked' }, [...selected].map(t => h('button', {
      class: 'chipbtn on', title: $t('details.remove'), onclick: () => change(() => { p.tags = p.tags.filter(x => x !== t); }),
    }, tagLabel(t), ' ×'))));
  }
  const filter = h('input', { class: 'text', placeholder: $t('details.find_tag_cowgirl_femdom_vampire'), spellcheck: 'false', value: app._tagFilter || '' });
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
  root.append(h('div', { class: 'section-title', style: { marginTop: '18px' } }, $t('details.offered_on'), h('span', { class: 'count' }, $t('details.n_places', { n: locs.size }))),
    h('div', { class: 'chips' }, WW_LOCATIONS.map(l => h('button', {
      class: 'chipbtn place' + (locs.has(l) ? ' on' : ''),
      onclick: () => change(() => { p.locations = locs.has(l) ? p.locations.filter(x => x !== l) : [...(p.locations || []), l]; }),
    }, nice(l)))));

  // each sim in the game: undressing, its part in the act, bare feet, strap-on
  const NAKED_LABEL = Object.fromEntries(NAKED_CHOICES);
  root.append(h('div', { class: 'section-title', style: { marginTop: '18px' } }, $t('details.each_sim_in_game')));
  for (const sim of p.sims) {
    const auto = nakedFor(p.category, { gender: sim.gender });
    const sel = h('select', {}, NAKED_CHOICES.map(([v, t]) => h('option', { value: v, selected: (sim.naked || 'AUTO') === v },
      v === 'AUTO' ? $t('details.auto', { v: NAKED_LABEL[auto].toLowerCase() }) : t)));
    sel.addEventListener('change', () => change(() => { sim.naked = sel.value; }));
    const autoRole = app.roleOf({ ...sim, role: undefined });
    const role = h('select', {}, [['', $t('details.auto_role', { role: inSentence(ROLE_LABEL[autoRole]) })], ['giver', ROLE_LABEL.giver], ['receiver', ROLE_LABEL.receiver], ['both', ROLE_LABEL.both]]
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
      h('label', { class: 'field row' }, h('span', {}, $t('details.undressing')), sel),
      h('label', { class: 'field row' }, h('span', {}, $t('details.in_act')), role),
      h('label', { class: 'check', title: feetAuto ? $t('details.on_by_itself_for_footjobs') : '' }, feet, $t('details.bare_feet'), h('span', { class: 'muted small' }, feetAuto ? $t('details.on_by_itself_here') : '')),
      female ? h('label', { class: 'check', title: $t('details.wickedwhims_may_give_this_sim') }, strap, $t('details.allow_strap_on')) : null,
      cumAfterRow(app, sim, change)));
  }
  root.append(h('div', { class: 'hint' }, $t('details.automatic_undressing_follows_kind_va')));

  // progressions live in step 8 now
  root.append(...[
    h('div', { class: 'section-title', style: { marginTop: '18px' } }, $t('details.plays_next')),
    (p.next || []).length ? h('div', { class: 'hint' }, $t('details.old_link_then_plays'), h('b', {}, p.next.map(n => n.name).join(', ')), ' ',
      h('button', { class: 'btn small ghost', onclick: () => change(() => { p.next = []; }) }, $t('details.remove'))) : null,
    h('div', { class: 'hint' }, $t('details.to_play_animations_one_after')),
    h('button', { class: 'btn small', onclick: () => app.showStep('share') }, icon('chain'), $t('details.progressions')),
  ].filter(Boolean));

  // how long it plays in the game
  const loops = h('input', { class: 'text', type: 'number', min: 1, max: 120, value: p.loops || 10 });
  loops.addEventListener('change', () => change(() => { p.loops = Math.max(1, +loops.value || 10); }, false));
  root.append(h('div', { class: 'section-title', style: { marginTop: '18px' } }, $t('details.in_game')),
    h('label', { class: 'field' }, h('span', {}, $t('details.how_many_times_it_repeats')), loops),
    h('div', { class: 'hint' }, $t('details.one_loop_is_s_so', { pCount: (p.length / (p.fps || 30)).toFixed(1), pCount2: Math.round(p.length / (p.fps || 30) * (p.loops || 10)) })));
}
