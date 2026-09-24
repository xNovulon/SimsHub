// Step 8 - Share: try it in your game, build progressions (chains of animations), export a mod for others.
import { h, icon, modal, toast, toggle, section, tip, confirmBox, emitWA, addIcon } from './ui.js';
import { successHero, celebrateAt } from './fx.js';
import { api } from './api.js';
import { KINDS } from './tags.js';
import { ensureNamed } from './dialogs.js';
import { Store } from './state.js';
import { simBody } from './pipeline.js';
import { $t } from './i18n.js';

const kindName = k => (KINDS.find(x => x[0] === k) || ['', k || '?'])[1];

// Icons for the promo kit and pose packs (added to the app's icon sheet once).
const SHARE_ICONS = {
  'pk-gif': '<rect x="3" y="5" width="18" height="14" rx="3" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M10.2 10.2H8.4a1.8 1.8 0 0 0 0 3.6h1.8v-1.6M12.6 10.2v3.6M15 13.8v-3.6h2.4M15 12h1.8" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  'pk-thumb': '<rect x="4" y="4" width="16" height="16" rx="3" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="m5.5 17 4.5-4.5 3 3 2-2 3.5 3.5" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round"/><circle cx="15" cy="9" r="1.6" fill="currentColor"/>',
  'pk-text': '<path d="M5 5h14v10H10l-4 4v-4H5z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="M8.5 8.5h7M8.5 11.5h4.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
  'pp-couple': '<circle cx="8.5" cy="6.5" r="2.3" stroke="currentColor" stroke-width="1.6" fill="none"/><circle cx="15.5" cy="6.5" r="2.3" stroke="currentColor" stroke-width="1.6" fill="none"/><path d="M5 20v-5.5a3.5 3.5 0 0 1 7 0M12 14.5a3.5 3.5 0 0 1 7 0V20M3.5 21h17" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/>',
  'pp-lock': '<rect x="5" y="10.5" width="14" height="10" rx="2.5" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5M12 14.5v2.5" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round"/>',
};
export function ensureShareIcons() { for (const [id, svg] of Object.entries(SHARE_ICONS)) addIcon(id, svg); }

// The promo kit and pose packs load only when used.
export const openPromo = app => import('./promo.js').then(m => m.openPromoKit(app)).catch(e => { console.error('promo kit', e); toast($t('share.could_not_open_promo_kit', { message: e.message }), 'err'); });
export const openPoses = app => import('./posepack.js').then(m => m.openPosePack(app)).catch(e => { console.error('pose pack', e); toast($t('share.could_not_open_pose_pack', { message: e.message }), 'err'); });
const nice = s => (s || '').toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

// ---------------------------------------------------------------- data
// The saved animations and progressions, read fresh whenever the Share step is shown (animations saved or
// renamed since then must show up) - unless a progression save is still on its way.
async function loadData(app, force = false) {
  if (app.shareData && !force) return app.shareData;
  if (app._progSaving) await app._progSaving.catch(() => {});
  const [projects, progressions] = await Promise.all([api.projects(), api.progressions()]);
  app.shareData = { projects, progressions, byUid: Object.fromEntries(projects.map(p => [p.uid, p])) };
  return app.shareData;
}

// Progression edits are saved one after another, never two at once, so an older answer from the server can't
// replace a newer change. The edited objects are kept (only their new ids are copied in).
function saveProgs(app) {
  const run = async () => {
    const d = app.shareData;
    if (!d) return;
    const sent = d.progressions;
    const saved = await api.saveProgressions(sent);
    saved.forEach((g, i) => { if (sent[i] && !sent[i].id) sent[i].id = g.id; });
  };
  const next = (app._progSaving || Promise.resolve()).catch(() => {}).then(run);
  app._progSaving = next;
  next.finally(() => { if (app._progSaving === next) app._progSaving = null; }).catch(() => {});
  return next;
}

// Can WickedWhims move from animation a to b? (same place, same sims) - and notes worth knowing.
export function linkCheck(a, b) {
  if (!a || !b) return { ok: false, text: $t('share.this_animation_is_missing_it') };
  const shared = (a.locations || []).filter(l => (b.locations || []).includes(l));
  if (!shared.length) return { ok: false, text: $t('share.no_place_in_common_wickedwhims', { map: (a.locations || []).map(nice).join(', '), map2: (b.locations || []).map(nice).join(', ') }) };
  if (a.sims !== b.sims) return { ok: false, text: $t('share.sims_sims_both_need_same', { sims: a.sims, sims2: b.sims }) };
  const g = x => [...(x.genders || [])].map(v => v === 'BOTH' ? '*' : v).sort().join();
  if (g(a) !== g(b) && !(a.genders || []).includes('BOTH') && !(b.genders || []).includes('BOTH')) return { ok: true, warn: true, text: $t('share.parts_are_cast_differently_check') };
  if (b.category === 'CLIMAX') return { ok: true, text: $t('share.moves_on_to_climax_when') };
  return { ok: true, text: $t('share.then_plays_on', { map: shared.map(nice).join(', ') }) };
}

// ---------------------------------------------------------------- panel
export function renderShare(app, root) {
  ensureShareIcons();
  // (the step's one main button is "Send to game" at the bottom - it is not repeated here)
  root.append(section($t('share.try_it_in_your_game'),
    h('div', { class: 'hint', style: { marginTop: 0 } }, $t('share.send_to_game_below_puts'))));

  const progBox = h('div', {}, h('div', { class: 'hint' }, $t('share.loading')));
  root.append(section([$t('share.progressions'), h('button', { class: 'btn small soft', onclick: () => newProgression(app) }, icon('plus'), $t('share.new'))], progBox));
  root.append(section($t('share.share_it'),
    h('div', { class: 'hint', style: { marginTop: 0 } }, $t('share.pack_any_of_your_animations')),
    h('button', { class: 'btn block big', onclick: () => openShareDialog(app) }, icon('package'), $t('share.export_mod'))));
  root.append(section($t('share.show_it_off'),
    h('div', { class: 'hint', style: { marginTop: 0 } }, $t('share.looping_gifs_from_2_3')),
    h('button', { class: 'btn block soft sh-promo', 'data-share': 'promo', onclick: () => openPromo(app) }, icon('pk-gif'), $t('share.make_promo_kit')),
    h('div', { class: 'hint' }, $t('share.pose_packs_for_andrew_s')),
    h('button', { class: 'btn block soft sh-pose', 'data-share': 'posepack', onclick: () => openPoses(app) }, icon('pp-couple'), $t('share.export_as_pose_pack'))));

  // shown from what is known right away, then again once the fresh list has arrived
  if (app.shareData) drawProgressions(app, progBox, app.shareData);
  loadData(app, true).then(d => { if (progBox.isConnected) drawProgressions(app, progBox, d); })
    .catch(err => { progBox.innerHTML = ''; progBox.append(h('div', { class: 'warn-box' }, $t('share.could_not_load', { message: err.message }))); });
}

function drawProgressions(app, box, d) {
  box.innerHTML = '';
  box.append(h('div', { class: 'hint', style: { marginTop: 0 } }, $t('share.progression_plays_your_animations_on')));
  if (!d.progressions.length) box.append(tip($t('share.no_progressions_yet_save_your')));
  for (const g of d.progressions) box.append(progressionCard(app, g, d));
}

function progressionCard(app, g, d) {
  const redraw = () => {
    saveProgs(app).then(() => { if (app.step === 'share') app.renderStep(); })
      .catch(err => toast($t('share.could_not_save_progression', { message: err.message }), 'err'));
  };
  const name = h('input', { class: 'text', value: g.name, style: { fontWeight: 700 } });
  name.onchange = () => { g.name = name.value.trim() || 'Progression'; redraw(); };
  const chain = h('div', { class: 'chain' });
  g.steps.forEach((uid, i) => {
    const m = d.byUid[uid];
    if (i > 0) {
      const c = linkCheck(d.byUid[g.steps[i - 1]], m);
      chain.append(h('div', { class: 'chain-link' + (c.ok && !c.warn ? '' : ' bad') }, icon('arrow'), c.text));
    }
    chain.append(h('div', { class: 'chain-step' },
      h('span', { class: 'n' }, String(i + 1)),
      h('div', { class: 't' }, h('b', {}, m ? m.name : $t('share.missing_animation')), h('span', {}, m ? `${kindName(m.category)} · ${$t('share.n_sims', { n: m.sims })}${m.uid === app.store.project.uid ? $t('share.open_now') : ''}` : $t('share.renamed_or_removed'))),
      h('button', { class: 'icon-btn sm', title: $t('share.earlier'), disabled: i === 0, onclick: () => { [g.steps[i - 1], g.steps[i]] = [g.steps[i], g.steps[i - 1]]; redraw(); } }, icon('up')),
      h('button', { class: 'icon-btn sm', title: $t('share.later'), disabled: i === g.steps.length - 1, onclick: () => { [g.steps[i + 1], g.steps[i]] = [g.steps[i], g.steps[i + 1]]; redraw(); } }, icon('down')),
      h('button', { class: 'icon-btn sm', title: $t('share.take_out'), onclick: () => { g.steps.splice(i, 1); redraw(); } }, icon('x'))));
  });
  if (g.repeat && g.steps.length > 1) chain.append(h('div', { class: 'chain-link' }, icon('loop'), $t('share.then_back_to_first_step')));
  const add = h('select', {}, h('option', { value: '' }, $t('share.add_animation')),
    d.projects.filter(p => !g.steps.includes(p.uid)).map(p => h('option', { value: p.uid }, `${p.name}${p.author ? ' by ' + p.author : ''} (${kindName(p.category)})`)));
  add.onchange = () => { if (add.value) { g.steps.push(add.value); redraw(); } };
  return h('div', { class: 'card', style: { marginBottom: '10px' } },
    h('div', { style: { display: 'flex', gap: '8px', alignItems: 'center' } }, icon('chain'), name,
      h('button', { class: 'icon-btn sm', title: $t('share.delete_this_progression'), onclick: async () => {
        if (!(await confirmBox($t('share.delete_progression'), $t('share.animations_themselves_stay', { gName: g.name }), $t('share.delete'), true))) return;
        app.shareData.progressions = app.shareData.progressions.filter(x => x !== g); redraw();
      } }, icon('trash'))),
    chain, add,
    h('label', { class: 'check', style: { marginTop: '10px' } }, toggle(g.repeat, on => { g.repeat = on; redraw(); }), $t('share.start_over_after_last_step')),
    h('div', { class: 'btn-grid', style: { marginTop: '8px' } },
      h('button', { class: 'btn small', disabled: !g.steps.length, onclick: () => sendMany(app, g.steps) }, icon('send'), $t('share.update_in_my_game')),
      h('button', { class: 'btn small soft', disabled: !g.steps.length, onclick: () => openShareDialog(app, { progression: g.id, name: g.name }) }, icon('package'), $t('share.export_as_mod'))));
}

async function newProgression(app) {
  const p = app.store.project;
  let d = await loadData(app, true);
  if (!d.byUid[p.uid]) {
    // the open animation becomes the first step, so it must be saved - with a real name, never "Untitled"
    if (!(await ensureNamed(app, $t('share.name_it_to_start_progression')))) return;
    if (!(await app.save())) return;
    d = await loadData(app, true);
  }
  d.progressions.push({ id: '', name: $t('share.new_progression'), author: p.author || '', steps: [p.uid], repeat: false });
  try { await saveProgs(app); } catch (err) { toast($t('share.could_not_save_progression', { message: err.message }), 'err'); return; }
  app.renderStep();
  toast($t('share.progression_started_with_this_animat'), 'ok');
}

// ---------------------------------------------------------------- baking other saved animations
// A saved animation that is not the open one is baked with its own temporary sims (app.bakeOther): the stage,
// the selected part and the rotate rings stay exactly as they are.
export async function bakeByUid(app, uid) {
  if (uid === app.store.project.uid) return app.bake();
  const data = await api.projectByUid(uid);
  const temp = new Store();
  temp.listeners = new Set();
  temp.load(data);
  for (const s of temp.project.sims) simBody(s);
  return app.bakeOther(temp.project);
}

async function sendMany(app, uids) {
  toast($t('share.sending_animations_to_your_game', { uidCount: uids.length }));
  let n = 0, replaced = 0;
  const warnings = [], failed = [];
  for (const uid of uids) {
    try {
      const res = await api.export(await bakeByUid(app, uid));
      n++;
      replaced += (res.replaced || []).length;
      for (const w of res.warnings || []) if (!warnings.includes(w)) warnings.push(w);
    } catch (e) { failed.push(`${app.shareData?.byUid[uid]?.name || $t('share.one_animation')}: ${e.message}`); }
  }
  const done = $t('share.sent_to_your_mods_folder', { n });
  if (!warnings.length && !failed.length) { toast(done, 'ok'); return; }
  // notes worth reading (a step that is not in the game yet, an older copy still in Mods...) stay on screen
  modal({
    title: n ? $t('share.sent_to_your_game') : $t('share.nothing_was_sent'),
    body: h('div', {},
      n ? h('p', {}, done) : null,
      ...failed.map(f => h('div', { class: 'warn-box error' }, $t('share.could_not_send', { f }))),
      ...warnings.map(w => h('div', { class: 'warn-box' }, w)),
      replaced ? h('p', { class: 'hint' }, $t('share.older_copies_were_taken_out')) : null),
    buttons: [{ label: $t('share.done'), kind: 'primary' }],
  });
}

// ---------------------------------------------------------------- export a mod
export async function openShareDialog(app, opts = {}) {
  const p = app.store.project;
  // just opening the dialog never saves anything: the open animation is listed as it is, and saved (asking for a
  // name if it has none) only when you press Export mod with it ticked
  let d;
  try { d = await loadData(app, true); } catch (e) { toast($t('share.could_not_read_your_animations', { message: e.message }), 'err'); return; }
  const savedMeta = d.byUid[p.uid];
  const openMeta = () => ({ uid: p.uid, name: p.name, author: p.author, category: p.category, locations: p.locations || [],
    sims: p.sims.length, keys: p.sims.reduce((n, s) => n + s.keys.length, 0), unsaved: !savedMeta, changed: !!savedMeta && app.store.dirty });
  const projects = savedMeta ? d.projects.map(m => (m.uid === p.uid ? { ...m, changed: app.store.dirty } : m)) : [openMeta(), ...d.projects];
  const picked = new Set();
  const progPicked = new Set();
  if (opts.progression) { progPicked.add(opts.progression); (d.progressions.find(g => g.id === opts.progression)?.steps || []).forEach(u => picked.add(u)); }
  else if (p.sims.length) picked.add(p.uid);

  const name = h('input', { class: 'text', value: opts.name ? (p.author ? $t('share.name_by_author', { name: opts.name, author: p.author }) : opts.name) : p.author ? $t('share.authors_animations', { author: p.author }) : $t('share.my_animations'), placeholder: $t('share.e_g_novulon_lullaby_pack') });
  const author = h('input', { class: 'text', value: p.author || '', placeholder: $t('share.your_creator_name') });
  let sounds = true, install = false;
  const list = h('div', { class: 'pick-list' });
  const summary = h('div', { class: 'summary' });

  // what stops an animation from going in (the open one is asked for a name when you export, so that one's fine)
  const problems = m => {
    const out = [];
    const open = m.uid === p.uid;
    if (!open && (!m.name || /^untitled/i.test(m.name))) out.push($t('share.needs_name'));
    if (!open && !m.author) out.push($t('share.needs_creator'));
    if (!(m.locations || []).length) out.push($t('share.no_place_picked'));
    if (!m.keys) out.push($t('share.no_keys'));
    return out;
  };
  const openNote = m => (m.unsaved ? $t('share.not_saved_yet_saved_when') : m.changed ? $t('share.unsaved_changes_saved_when_you') : '');
  const draw = () => {
    list.innerHTML = '';
    if (d.progressions.length) list.append(h('div', { class: 'section-title', style: { margin: '2px 0 6px' } }, $t('share.progressions')));
    for (const g of d.progressions) {
      const on = g.steps.length && g.steps.every(u => picked.has(u));
      const cb = h('input', { type: 'checkbox', checked: on });
      list.append(h('label', { class: 'pick prog' + (on ? ' on' : '') }, cb,
        h('div', {}, h('b', {}, g.name), h('small', {}, g.steps.map(u => d.byUid[u]?.name || '?').join(' → '))), h('span', { class: 'chip hot' }, $t('share.n_steps', { n: g.steps.length }))));
      cb.onchange = () => { g.steps.forEach(u => cb.checked ? picked.add(u) : picked.delete(u)); cb.checked ? progPicked.add(g.id) : progPicked.delete(g.id); draw(); };
    }
    list.append(h('div', { class: 'section-title', style: { margin: '12px 0 6px' } }, h('span', {}, $t('share.animations')),
      h('span', {}, h('button', { class: 'btn small ghost', onclick: () => { projects.forEach(m => !problems(m).length && picked.add(m.uid)); draw(); } }, $t('share.all')),
        h('button', { class: 'btn small ghost', onclick: () => { picked.clear(); progPicked.clear(); draw(); } }, $t('share.none')))));
    for (const m of projects) {
      const bad = problems(m), note = m.uid === p.uid ? openNote(m) : '';
      const cb = h('input', { type: 'checkbox', checked: picked.has(m.uid), disabled: !!bad.length });
      list.append(h('label', { class: 'pick' + (picked.has(m.uid) ? ' on' : '') + (bad.length ? ' disabled' : ''), title: bad.join(', ') }, cb,
        h('div', {}, h('b', {}, m.name, m.author ? h('span', { class: 'muted' }, ' by ' + m.author) : ''),
          h('small', {}, bad.length ? $t('share.can_t_export_yet', { bad: bad.join(', ') }) : $t('share.sims', { kindName: kindName(m.category), map: (m.locations || []).map(nice).join(', '), sims: m.sims, v: note ? ' · ' + note : '' }))),
        m.uid === p.uid ? h('span', { class: 'chip hot' }, 'open') : h('span')));
      cb.onchange = () => { cb.checked ? picked.add(m.uid) : picked.delete(m.uid); draw(); };
    }
    drawSummary();
  };
  const drawSummary = () => {
    summary.innerHTML = '';
    const chosen = projects.filter(m => picked.has(m.uid));
    const full = d.progressions.filter(g => g.steps.length && g.steps.every(u => picked.has(u)));
    const partial = d.progressions.filter(g => g.steps.some(u => picked.has(u)) && !g.steps.every(u => picked.has(u)));
    summary.append(h('div', { class: 'big' }, $t('share.n_animations', { n: chosen.length })),
      h('div', { class: 'muted' }, full.length ? $t('share.complete_progressions', { fullCount: full.length, map: full.map(g => g.name).join(', ') }) : $t('share.no_complete_progressions')));
    for (const g of partial) {
      const miss = g.steps.filter(u => !picked.has(u)).map(u => d.byUid[u]?.name || '?');
      summary.append(h('div', { class: 'warn-box' }, $t('share.is_missing_that_step_will', { gName: g.name, miss: miss.join(', ') }),
        h('button', { class: 'btn small', onclick: () => { g.steps.forEach(u => picked.add(u)); draw(); } }, $t('share.add_them'))));
    }
  };

  const body = h('div', { class: 'share-grid' },
    h('div', {}, list),
    h('div', {},
      h('label', { class: 'field' }, h('span', {}, $t('share.mod_name_file_people_get')), name),
      h('label', { class: 'field' }, h('span', {}, $t('share.creator')), author),
      h('div', { class: 'toggle-row' }, h('div', {}, h('b', {}, $t('share.pack_sounds_inside')), h('span', {}, $t('share.sounds_from_other_mods_are'))), toggle(true, on => { sounds = on; })),
      h('div', { class: 'toggle-row' }, h('div', {}, h('b', {}, $t('share.also_update_them_in_my')), h('span', {}, $t('share.sends_each_one_to_your'))), toggle(false, on => { install = on; })),
      summary,
      h('div', { class: 'hint' }, $t('share.you_get_folder_with_package'))));
  const dlg = modal({
    title: $t('share.export_mod_2'), text: $t('share.pick_what_goes_in_progressions'), body, wide: true,
    buttons: [{ label: $t('share.cancel'), kind: 'ghost' }, { label: $t('share.export_mod_3'), kind: 'primary', onClick: async () => {
      const uids = projects.filter(m => picked.has(m.uid)).map(m => m.uid);
      if (!uids.length) { toast($t('share.pick_at_least_one_animation'), 'err'); return false; }
      if (!name.value.trim()) { toast($t('share.give_mod_name'), 'err'); name.focus(); return false; }
      // the open animation goes in as it is now: it is saved first (the mod reads saved animations)
      if (picked.has(p.uid) && (app.store.dirty || !savedMeta)) {
        if (!(await ensureNamed(app, $t('share.name_it_before_exporting')))) return false;
        if (!(await app.save())) return false;
      }
      const btn = dlg.footer.lastChild; btn.disabled = true; btn.textContent = $t('share.baking');
      try {
        const animations = [];
        for (const [i, uid] of uids.entries()) { btn.textContent = $t('share.baking_2', { i: i + 1, uidCount: uids.length }); animations.push(await bakeByUid(app, uid)); }
        btn.textContent = $t('share.packing');
        const res = await api.bundle({ name: name.value.trim(), author: author.value.trim(), animations, include_sounds: sounds, install, progressions: [...progPicked] });
        showBundle(res, app);
      } catch (e) { toast($t('share.export_failed', { message: e.message }), 'err'); btn.disabled = false; btn.textContent = $t('share.export_mod_3'); return false; }
    } }],
  });
  draw();
}

// Game pack codes the server gives -> the names players know them by.
const PACKS = {
  EP01: 'Get to Work', EP02: 'Get Together', EP03: 'City Living', EP04: 'Cats & Dogs', EP05: 'Seasons', EP06: 'Get Famous',
  EP07: 'Island Living', EP08: 'Discover University', EP09: 'Eco Lifestyle', EP10: 'Snowy Escape', EP11: 'Cottage Living',
  EP12: 'High School Years', EP13: 'Growing Together', EP14: 'Horse Ranch', EP15: 'For Rent', EP16: 'Lovestruck', EP17: 'Life & Death',
  GP01: 'Outdoor Retreat', GP02: 'Spa Day', GP03: 'Dine Out', GP04: 'Vampires', GP05: 'Parenthood', GP06: 'Jungle Adventure',
  GP07: 'StrangerVille', GP08: 'Realm of Magic', GP09: 'Journey to Batuu', GP10: 'Dream Home Decorator', GP11: 'My Wedding Stories', GP12: 'Werewolves',
};
const packName = codes => String(codes || '').split(/,\s*/).filter(Boolean).map(c => (PACKS[c] ? `${PACKS[c]} (${c})` : c)).join(', ');

function showBundle(res, app = window.app) {
  const needs = Object.entries(res.sounds_need_pack || {}).sort((a, b) => a[0].localeCompare(b[0])).map(([snd, codes]) => [snd, packName(codes)]);
  const hero = successHero();
  modal({
    title: $t('share.your_mod_is_ready'),
    body: h('div', {}, hero, h('h3', { class: 'hero-title' }, $t('share.animations_packed_into_one_mod', { animations: res.animations })),
      h('div', { class: 'success' }, icon('check'), h('div', {},
        h('b', {}, $t('share.n_animations', { n: res.animations }) + (res.progressions.length ? $t('share.progressions_2', { progressionCount: res.progressions.length }) : '') + ` · ${(res.bytes / 1048576).toFixed(1)} MB`),
        h('div', { class: 'path' }, res.package))),
<<<<<<< ours
      res.sounds_packed ? h('p', { class: 'hint' }, `${res.sounds_packed} sounds from other mods were packed in - their creators are credited in the README: `, Object.keys(res.credits || {}).join(', ')) : null,
      res.own_sounds ? h('p', { class: 'hint' }, `${res.own_sounds === 1 ? 'Your own sound is' : res.own_sounds + ' of your own sounds are'} packed in too.`) : null,
      res.fit_bodies ? h('p', { class: 'hint' }, 'Experimental: some held hands and feet are fitted to each body. The README says how to test it in the game.') : null,
      (res.missing_sounds || []).length ? h('div', { class: 'warn-box' }, 'Not found, so not packed: ' + res.missing_sounds.join(', ')) : null,
=======
      res.sounds_packed ? h('p', { class: 'hint' }, $t('share.sounds_from_other_mods_were', { sounds_packed: res.sounds_packed }), Object.keys(res.credits || {}).join(', ')) : null,
      res.own_sounds ? h('p', { class: 'hint' }, $t('share.own_sounds_packed_too', { n: res.own_sounds })) : null,
      (res.missing_sounds || []).length ? h('div', { class: 'warn-box' }, $t('share.not_found_so_not_packed', { missing_sounds: res.missing_sounds.join(', ') })) : null,
>>>>>>> theirs
      // sounds that come from a game pack: people without that pack play the animation silently there
      needs.length ? h('div', { class: 'warn-box' }, $t('share.sounds_that_need_game_pack'), needs.map(([snd, pack]) => $t('share.sound_needs_pack', { sound: snd, pack })).join(', ')) : null,
      // notes worth knowing, e.g. a progression step that is not in this mod
      ...(res.warnings || []).map(w => h('div', { class: 'warn-box' }, w)),
      h('p', {}, $t('share.give_people_zip_or_package')),
      (res.installed || []).length ? h('p', { class: 'hint' }, $t('share.also_updated_in_your_own', { installedCount: res.installed.length })) : null),
    buttons: [{ label: $t('share.open_folder'), kind: '', onClick: () => { api.reveal(res.folder); return false; } }, { label: $t('share.done'), kind: 'primary' }],
  });
  celebrateAt(hero, { delay: 480 });
  emitWA(app, 'exported', { result: res });
}
