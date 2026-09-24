// Step 8 - Share: try it in your game, build progressions (chains of animations), export a mod for others.
import { h, icon, modal, toast, toggle, section, tip, confirmBox, emitWA, addIcon } from './ui.js';
import { successHero, celebrateAt } from './fx.js';
import { api } from './api.js';
import { KINDS } from './tags.js';
import { ensureNamed } from './dialogs.js';
import { Store } from './state.js';
import { simBody } from './pipeline.js';

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
export const openPromo = app => import('./promo.js').then(m => m.openPromoKit(app)).catch(e => { console.error('promo kit', e); toast('Could not open the promo kit: ' + e.message, 'err'); });
export const openPoses = app => import('./posepack.js').then(m => m.openPosePack(app)).catch(e => { console.error('pose pack', e); toast('Could not open the pose pack: ' + e.message, 'err'); });
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
  if (!a || !b) return { ok: false, text: 'This animation is missing - it was renamed or removed.' };
  const shared = (a.locations || []).filter(l => (b.locations || []).includes(l));
  if (!shared.length) return { ok: false, text: `No place in common (${(a.locations || []).map(nice).join(', ')} → ${(b.locations || []).map(nice).join(', ')}): WickedWhims can't move on here.` };
  if (a.sims !== b.sims) return { ok: false, text: `${a.sims} sims → ${b.sims} sims: both need the same number of sims.` };
  const g = x => [...(x.genders || [])].map(v => v === 'BOTH' ? '*' : v).sort().join();
  if (g(a) !== g(b) && !(a.genders || []).includes('BOTH') && !(b.genders || []).includes('BOTH')) return { ok: true, warn: true, text: 'The parts are cast differently - check each sim plays the same part.' };
  if (b.category === 'CLIMAX') return { ok: true, text: 'Moves on to the climax when the sims reach it.' };
  return { ok: true, text: `Then plays on ${shared.map(nice).join(', ')}` };
}

// ---------------------------------------------------------------- panel
export function renderShare(app, root) {
  ensureShareIcons();
  // (the step's one main button is "Send to game" at the bottom - it is not repeated here)
  root.append(section('Try it in your game',
    h('div', { class: 'hint', style: { marginTop: 0 } }, 'Send to game (below) puts this animation in your Mods folder. Restart the game, then start sex with WickedWhims and pick it. Changed it? Send it again and restart the game - the new version replaces the old one.')));

  const progBox = h('div', {}, h('div', { class: 'hint' }, 'Loading...'));
  root.append(section(['Progressions', h('button', { class: 'btn small soft', onclick: () => newProgression(app) }, icon('plus'), 'New')], progBox));
  root.append(section('Share it',
    h('div', { class: 'hint', style: { marginTop: 0 } }, 'Pack any of your animations and progressions into one mod file. People drop it in their Mods folder and get the animations - and the progressions work the same for them.'),
    h('button', { class: 'btn block big', onclick: () => openShareDialog(app) }, icon('package'), 'Export a mod...')));
  root.append(section('Show it off',
    h('div', { class: 'hint', style: { marginTop: 0 } }, 'Looping GIFs from 2-3 angles, a thumbnail, a 10-second video and the text to post - made from the stage, in one folder.'),
    h('button', { class: 'btn block soft sh-promo', 'data-share': 'promo', onclick: () => openPromo(app) }, icon('pk-gif'), 'Make a promo kit...'),
    h('div', { class: 'hint' }, "Pose packs for Andrew's Pose Player: each key becomes a pose, couples line up on one spot. Non-explicit poses only."),
    h('button', { class: 'btn block soft sh-pose', 'data-share': 'posepack', onclick: () => openPoses(app) }, icon('pp-couple'), 'Export as a pose pack...')));

  // shown from what is known right away, then again once the fresh list has arrived
  if (app.shareData) drawProgressions(app, progBox, app.shareData);
  loadData(app, true).then(d => { if (progBox.isConnected) drawProgressions(app, progBox, d); })
    .catch(err => { progBox.innerHTML = ''; progBox.append(h('div', { class: 'warn-box' }, 'Could not load: ' + err.message)); });
}

function drawProgressions(app, box, d) {
  box.innerHTML = '';
  box.append(h('div', { class: 'hint', style: { marginTop: 0 } }, 'A progression plays your animations one after another - e.g. "Lullaby": oral → handjob → cowgirl. Each keeps its own kind and tags. Starting any step carries on down the chain; animations not in a progression move on to a random one.'));
  if (!d.progressions.length) box.append(tip('No progressions yet. Save your animations, then press New.'));
  for (const g of d.progressions) box.append(progressionCard(app, g, d));
}

function progressionCard(app, g, d) {
  const redraw = () => {
    saveProgs(app).then(() => { if (app.step === 'share') app.renderStep(); })
      .catch(err => toast('Could not save the progression: ' + err.message, 'err'));
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
      h('div', { class: 't' }, h('b', {}, m ? m.name : '(missing animation)'), h('span', {}, m ? `${kindName(m.category)} · ${m.sims} sims${m.uid === app.store.project.uid ? ' · open now' : ''}` : 'renamed or removed')),
      h('button', { class: 'icon-btn sm', title: 'Earlier', disabled: i === 0, onclick: () => { [g.steps[i - 1], g.steps[i]] = [g.steps[i], g.steps[i - 1]]; redraw(); } }, icon('up')),
      h('button', { class: 'icon-btn sm', title: 'Later', disabled: i === g.steps.length - 1, onclick: () => { [g.steps[i + 1], g.steps[i]] = [g.steps[i], g.steps[i + 1]]; redraw(); } }, icon('down')),
      h('button', { class: 'icon-btn sm', title: 'Take out', onclick: () => { g.steps.splice(i, 1); redraw(); } }, icon('x'))));
  });
  if (g.repeat && g.steps.length > 1) chain.append(h('div', { class: 'chain-link' }, icon('loop'), 'Then back to the first step'));
  const add = h('select', {}, h('option', { value: '' }, '+ Add an animation...'),
    d.projects.filter(p => !g.steps.includes(p.uid)).map(p => h('option', { value: p.uid }, `${p.name}${p.author ? ' by ' + p.author : ''} (${kindName(p.category)})`)));
  add.onchange = () => { if (add.value) { g.steps.push(add.value); redraw(); } };
  return h('div', { class: 'card', style: { marginBottom: '10px' } },
    h('div', { style: { display: 'flex', gap: '8px', alignItems: 'center' } }, icon('chain'), name,
      h('button', { class: 'icon-btn sm', title: 'Delete this progression', onclick: async () => {
        if (!(await confirmBox('Delete progression?', `"${g.name}" - the animations themselves stay.`, 'Delete', true))) return;
        app.shareData.progressions = app.shareData.progressions.filter(x => x !== g); redraw();
      } }, icon('trash'))),
    chain, add,
    h('label', { class: 'check', style: { marginTop: '10px' } }, toggle(g.repeat, on => { g.repeat = on; redraw(); }), 'Start over after the last step'),
    h('div', { class: 'btn-grid', style: { marginTop: '8px' } },
      h('button', { class: 'btn small', disabled: !g.steps.length, onclick: () => sendMany(app, g.steps) }, icon('send'), 'Update in my game'),
      h('button', { class: 'btn small soft', disabled: !g.steps.length, onclick: () => openShareDialog(app, { progression: g.id, name: g.name }) }, icon('package'), 'Export as mod')));
}

async function newProgression(app) {
  const p = app.store.project;
  let d = await loadData(app, true);
  if (!d.byUid[p.uid]) {
    // the open animation becomes the first step, so it must be saved - with a real name, never "Untitled"
    if (!(await ensureNamed(app, 'Name it to start a progression'))) return;
    if (!(await app.save())) return;
    d = await loadData(app, true);
  }
  d.progressions.push({ id: '', name: 'New progression', author: p.author || '', steps: [p.uid], repeat: false });
  try { await saveProgs(app); } catch (err) { toast('Could not save the progression: ' + err.message, 'err'); return; }
  app.renderStep();
  toast('Progression started with this animation. Add the next ones below it.', 'ok');
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
  toast(`Sending ${uids.length} animation${uids.length > 1 ? 's' : ''} to your game...`);
  let n = 0, replaced = 0;
  const warnings = [], failed = [];
  for (const uid of uids) {
    try {
      const res = await api.export(await bakeByUid(app, uid));
      n++;
      replaced += (res.replaced || []).length;
      for (const w of res.warnings || []) if (!warnings.includes(w)) warnings.push(w);
    } catch (e) { failed.push(`${app.shareData?.byUid[uid]?.name || 'One animation'}: ${e.message}`); }
  }
  const done = `${n} sent to your Mods folder with their progression links. Restart the game to see them.`;
  if (!warnings.length && !failed.length) { toast(done, 'ok'); return; }
  // notes worth reading (a step that is not in the game yet, an older copy still in Mods...) stay on screen
  modal({
    title: n ? 'Sent to your game' : 'Nothing was sent',
    body: h('div', {},
      n ? h('p', {}, done) : null,
      ...failed.map(f => h('div', { class: 'warn-box error' }, 'Could not send ' + f)),
      ...warnings.map(w => h('div', { class: 'warn-box' }, w)),
      replaced ? h('p', { class: 'hint' }, 'Older copies were taken out of your Mods folder, so nothing shows twice.') : null),
    buttons: [{ label: 'Done', kind: 'primary' }],
  });
}

// ---------------------------------------------------------------- export a mod
export async function openShareDialog(app, opts = {}) {
  const p = app.store.project;
  // just opening the dialog never saves anything: the open animation is listed as it is, and saved (asking for a
  // name if it has none) only when you press Export mod with it ticked
  let d;
  try { d = await loadData(app, true); } catch (e) { toast('Could not read your animations: ' + e.message, 'err'); return; }
  const savedMeta = d.byUid[p.uid];
  const openMeta = () => ({ uid: p.uid, name: p.name, author: p.author, category: p.category, locations: p.locations || [],
    sims: p.sims.length, keys: p.sims.reduce((n, s) => n + s.keys.length, 0), unsaved: !savedMeta, changed: !!savedMeta && app.store.dirty });
  const projects = savedMeta ? d.projects.map(m => (m.uid === p.uid ? { ...m, changed: app.store.dirty } : m)) : [openMeta(), ...d.projects];
  const picked = new Set();
  const progPicked = new Set();
  if (opts.progression) { progPicked.add(opts.progression); (d.progressions.find(g => g.id === opts.progression)?.steps || []).forEach(u => picked.add(u)); }
  else if (p.sims.length) picked.add(p.uid);

  const name = h('input', { class: 'text', value: opts.name ? `${opts.name}${p.author ? ' by ' + p.author : ''}` : `${p.author || 'My'} Animations`, placeholder: 'e.g. Novulon - Lullaby Pack' });
  const author = h('input', { class: 'text', value: p.author || '', placeholder: 'Your creator name' });
  let sounds = true, install = false;
  const list = h('div', { class: 'pick-list' });
  const summary = h('div', { class: 'summary' });

  // what stops an animation from going in (the open one is asked for a name when you export, so that one's fine)
  const problems = m => {
    const out = [];
    const open = m.uid === p.uid;
    if (!open && (!m.name || /^untitled/i.test(m.name))) out.push('needs a name');
    if (!open && !m.author) out.push('needs a creator');
    if (!(m.locations || []).length) out.push('no place picked');
    if (!m.keys) out.push('no keys');
    return out;
  };
  const openNote = m => (m.unsaved ? 'not saved yet - saved when you export' : m.changed ? 'unsaved changes - saved when you export' : '');
  const draw = () => {
    list.innerHTML = '';
    if (d.progressions.length) list.append(h('div', { class: 'section-title', style: { margin: '2px 0 6px' } }, 'Progressions'));
    for (const g of d.progressions) {
      const on = g.steps.length && g.steps.every(u => picked.has(u));
      const cb = h('input', { type: 'checkbox', checked: on });
      list.append(h('label', { class: 'pick prog' + (on ? ' on' : '') }, cb,
        h('div', {}, h('b', {}, g.name), h('small', {}, g.steps.map(u => d.byUid[u]?.name || '?').join(' → '))), h('span', { class: 'chip hot' }, `${g.steps.length} steps`)));
      cb.onchange = () => { g.steps.forEach(u => cb.checked ? picked.add(u) : picked.delete(u)); cb.checked ? progPicked.add(g.id) : progPicked.delete(g.id); draw(); };
    }
    list.append(h('div', { class: 'section-title', style: { margin: '12px 0 6px' } }, h('span', {}, 'Animations'),
      h('span', {}, h('button', { class: 'btn small ghost', onclick: () => { projects.forEach(m => !problems(m).length && picked.add(m.uid)); draw(); } }, 'All'),
        h('button', { class: 'btn small ghost', onclick: () => { picked.clear(); progPicked.clear(); draw(); } }, 'None'))));
    for (const m of projects) {
      const bad = problems(m), note = m.uid === p.uid ? openNote(m) : '';
      const cb = h('input', { type: 'checkbox', checked: picked.has(m.uid), disabled: !!bad.length });
      list.append(h('label', { class: 'pick' + (picked.has(m.uid) ? ' on' : '') + (bad.length ? ' disabled' : ''), title: bad.join(', ') }, cb,
        h('div', {}, h('b', {}, m.name, m.author ? h('span', { class: 'muted' }, ' by ' + m.author) : ''),
          h('small', {}, bad.length ? 'Can\'t export yet: ' + bad.join(', ') : `${kindName(m.category)} · ${(m.locations || []).map(nice).join(', ')} · ${m.sims} sims${note ? ' · ' + note : ''}`)),
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
    summary.append(h('div', { class: 'big' }, `${chosen.length} animation${chosen.length === 1 ? '' : 's'}`),
      h('div', { class: 'muted' }, full.length ? `${full.length} complete progression${full.length > 1 ? 's' : ''}: ${full.map(g => g.name).join(', ')}` : 'No complete progressions'));
    for (const g of partial) {
      const miss = g.steps.filter(u => !picked.has(u)).map(u => d.byUid[u]?.name || '?');
      summary.append(h('div', { class: 'warn-box' }, `"${g.name}" is missing ${miss.join(', ')} - that step will move on to a random animation instead.`,
        h('button', { class: 'btn small', onclick: () => { g.steps.forEach(u => picked.add(u)); draw(); } }, 'Add them')));
    }
  };

  const body = h('div', { class: 'share-grid' },
    h('div', {}, list),
    h('div', {},
      h('label', { class: 'field' }, h('span', {}, 'Mod name (the file people get)'), name),
      h('label', { class: 'field' }, h('span', {}, 'Creator'), author),
      h('div', { class: 'toggle-row' }, h('div', {}, h('b', {}, 'Pack the sounds inside'), h('span', {}, 'Sounds from other mods are copied in so they play for everyone. Credit is written in the README.')), toggle(true, on => { sounds = on; })),
      h('div', { class: 'toggle-row' }, h('div', {}, h('b', {}, 'Also update them in my game'), h('span', {}, 'Sends each one to your own Mods folder too')), toggle(false, on => { install = on; })),
      summary,
      h('div', { class: 'hint' }, 'You get a folder with the .package (drop it in Mods), a README and a .zip ready to upload.')));
  const dlg = modal({
    title: 'Export a mod', text: 'Pick what goes in. Progressions you tick bring all their steps.', body, wide: true,
    buttons: [{ label: 'Cancel', kind: 'ghost' }, { label: 'Export mod', kind: 'primary', onClick: async () => {
      const uids = projects.filter(m => picked.has(m.uid)).map(m => m.uid);
      if (!uids.length) { toast('Pick at least one animation.', 'err'); return false; }
      if (!name.value.trim()) { toast('Give the mod a name.', 'err'); name.focus(); return false; }
      // the open animation goes in as it is now: it is saved first (the mod reads saved animations)
      if (picked.has(p.uid) && (app.store.dirty || !savedMeta)) {
        if (!(await ensureNamed(app, 'Name it before exporting'))) return false;
        if (!(await app.save())) return false;
      }
      const btn = dlg.footer.lastChild; btn.disabled = true; btn.textContent = 'Baking...';
      try {
        const animations = [];
        for (const [i, uid] of uids.entries()) { btn.textContent = `Baking ${i + 1}/${uids.length}...`; animations.push(await bakeByUid(app, uid)); }
        btn.textContent = 'Packing...';
        const res = await api.bundle({ name: name.value.trim(), author: author.value.trim(), animations, include_sounds: sounds, install, progressions: [...progPicked] });
        showBundle(res, app);
      } catch (e) { toast('Export failed: ' + e.message, 'err'); btn.disabled = false; btn.textContent = 'Export mod'; return false; }
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
    title: 'Your mod is ready',
    body: h('div', {}, hero, h('h3', { class: 'hero-title' }, `${res.animations} animation${res.animations > 1 ? 's' : ''} packed into one mod`),
      h('div', { class: 'success' }, icon('check'), h('div', {},
        h('b', {}, `${res.animations} animation${res.animations > 1 ? 's' : ''}${res.progressions.length ? ' · ' + res.progressions.length + ' progression' + (res.progressions.length > 1 ? 's' : '') : ''} · ${(res.bytes / 1048576).toFixed(1)} MB`),
        h('div', { class: 'path' }, res.package))),
      res.sounds_packed ? h('p', { class: 'hint' }, `${res.sounds_packed} sounds from other mods were packed in - their creators are credited in the README: `, Object.keys(res.credits || {}).join(', ')) : null,
      (res.missing_sounds || []).length ? h('div', { class: 'warn-box' }, 'Not found, so not packed: ' + res.missing_sounds.join(', ')) : null,
      // sounds that come from a game pack: people without that pack play the animation silently there
      needs.length ? h('div', { class: 'warn-box' }, 'Sounds that need a game pack (the README says so too): ', needs.map(([snd, pack]) => `${snd} needs ${pack}`).join(', ')) : null,
      // notes worth knowing, e.g. a progression step that is not in this mod
      ...(res.warnings || []).map(w => h('div', { class: 'warn-box' }, w)),
      h('p', {}, 'Give people the .zip (or the .package). They put the .package in their Mods folder - that\'s all.'),
      (res.installed || []).length ? h('p', { class: 'hint' }, `Also updated ${res.installed.length} in your own game.`) : null),
    buttons: [{ label: 'Open the folder', kind: '', onClick: () => { api.reveal(res.folder); return false; } }, { label: 'Done', kind: 'primary' }],
  });
  celebrateAt(hero, { delay: 480 });
  emitWA(app, 'exported', { result: res });
}
