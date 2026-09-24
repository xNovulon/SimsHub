// The game's own clips (spec_game 6-7): EA's romance animations as a library to start from, and the game's idle
// loops for the "Idle (from the game)" motion.
//
//   - "Game animations" (Home card and Ctrl+K): WooHoo, kisses, make-outs, cuddles... read from The Sims 4 itself
//     (/api/ea_library, /api/ea_animation). One opens on the stage in the Library's preview bar, so "Use this pose"
//     and "Import as keys" work on it like on any WickedWhims animation.
//   - Motion step: which game idle an "Idle (from the game)" motion plays (/api/ea_idles).
//   - motion.js loads an idle clip only when it is first played and says so with 'wa:idle-loaded': the sims are
//     posed again then, so the idle shows at once (not on the next change).
// The first read of the game's clips takes a minute or two (the server builds it in the background): the dialog
// waits for it and says so. Without The Sims 4 on the PC it says that instead.
import { h, icon, modal, toast, section, addIcon } from '../ui.js';
import { fetchJson, plainError, gameMissing } from '../gamehelp.js';
import { hideHome } from '../home.js';
import { IDLE_CACHE } from '../motion.js';

const ICONS = {
  'ea-heart': '<path d="M12 20.2s-7.6-4.6-7.6-10.1A4.3 4.3 0 0 1 12 7.4a4.3 4.3 0 0 1 7.6 2.7c0 5.5-7.6 10.1-7.6 10.1z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 2.8 9.6 6.4 12 8.2l2.4-1.8z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
};

// the bodies a pair of the game's clips (made for any two sims) is shown and imported on
const PAIRINGS = [['couple', 'Woman & man', ['FEMALE', 'MALE']], ['ff', 'Two women', ['FEMALE', 'FEMALE']], ['mm', 'Two men', ['MALE', 'MALE']]];
// the game's places (eaclips.PLACE_NAMES) as WickedWhims places, for an imported animation
const WW_PLACE = { Bed: 'DOUBLE_BED', 'Heart bed': 'DOUBLE_BED', Sofa: 'SOFA', Loveseat: 'LOVESEAT', Seated: 'SOFA', 'Hot tub': 'HOTTUB',
  'Massage table': 'MASSAGE_TABLE', 'Picnic blanket': 'BLANKET', 'Shower tub': 'SHOWER_TUB', 'Sleeping bag': 'BED_ROLL',
  Standing: 'FLOOR', Anywhere: 'FLOOR', 'Picnic table': 'TABLE_PICNIC', 'Massage chair': 'CHAIR_LIVING' };
// WickedWhims' kind for each of the game's groups (a first guess - Details changes it)
const WW_KIND = { woohoo: 'VAGINAL', makeout: 'TEASING', kiss: 'TEASING', cuddle: 'TEASING', bed: 'TEASING', massage: 'TEASING', hug: 'TEASING' };
const WW_TAGS = { kiss: ['KISSING'], makeout: ['KISSING'], cuddle: ['CUDDLING'] };

const state = { pairing: 'couple', q: '', cat: '' };

// ---------------------------------------------------------------- the game's romance animations
// A pair from /api/ea_animation made ready for the Library's preview and "Import as keys" (actors with genders,
// WickedWhims' kind and place).
export function asLibraryAnimation(a, pairing = 'couple') {
  const genders = (PAIRINGS.find(p => p[0] === pairing) || PAIRINGS[0])[2];
  const place = (a.locations || [])[0];
  return { ...a, id: a.id, name: a.name, author: a.author || 'The Sims 4', category: WW_KIND[a.kind] || 'TEASING', tags: [...(WW_TAGS[a.kind] || [])],
    locations: [WW_PLACE[place] || 'FLOOR'], gamePlace: place || null,
    actors: (a.clips || []).map((c, k) => ({ gender: genders[k] || genders[genders.length - 1], clip: (a.actors && a.actors[k] && a.actors[k].clip) || null })),
    events: [] };
}

export function openGameAnimations(app) {
  const list = h('div', { class: 'lib-list ea-list' });
  const count = h('div', { class: 'hint', role: 'status', 'aria-live': 'polite' }, 'Looking...');
  const search = h('input', { placeholder: 'Search: kiss, make out, bed, sofa...', spellcheck: 'false', value: state.q });
  const cats = h('div', { class: 'chips ea-cats' });
  const pair = h('select', { title: 'The bodies the two sims are shown on (the game made these for any two sims)' },
    PAIRINGS.map(([v, t]) => h('option', { value: v, selected: v === state.pairing }, t)));
  let timer = 0, closed = false, busy = false;
  const dlg = modal({
    title: 'Game animations', wide: true,
    text: "The Sims 4's own romance animations - WooHoo, kisses, make-outs, cuddles. Watch one on the stage, then use its pose or import it as keys to make your own.",
    body: h('div', { class: 'ea-dlg' },
      h('div', { class: 'filters' }, h('div', { class: 'search' }, icon('search'), search), pair),
      cats, count, list),
    onClose: () => { closed = true; clearTimeout(timer); },
    buttons: [{ label: 'Close', kind: 'ghost' }],
  });
  dlg.dialog.classList.add('ea-modal');
  let t = 0;
  search.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => { state.q = search.value; load(); }, 220); });
  pair.addEventListener('change', () => { state.pairing = pair.value; });

  const drawCats = categories => {
    cats.innerHTML = '';
    const all = Object.values(categories || {}).reduce((a, b) => a + b, 0);
    const chip = (v, text, n) => h('button', { class: 'chipbtn' + (state.cat === v ? ' on' : ''), type: 'button',
      onclick: () => { state.cat = state.cat === v ? '' : v; load(); } }, text, n ? h('small', {}, ' ' + n) : null);
    cats.append(chip('', 'Everything', all), ...Object.entries(categories || {}).map(([k, n]) => chip(k, k, n)));
  };

  async function load() {
    clearTimeout(timer);
    if (closed) return;
    let r;
    try { r = await fetchJson('/api/ea_library?' + new URLSearchParams({ q: state.q, cat: state.cat })); }
    catch (e) { count.textContent = plainError(e, "the game's animations"); list.innerHTML = ''; return; }
    if (!r.ready) return waitForGame();
    drawCats(r.categories);
    count.textContent = `${r.total.toLocaleString()} animation${r.total === 1 ? '' : 's'} from the game (adults only)`;
    list.innerHTML = '';
    if (!r.items.length) list.append(h('div', { class: 'empty-state compact' }, h('b', {}, 'Nothing found'), h('p', {}, 'Try another word, or pick "Everything".')));
    for (const it of r.items) {
      list.append(h('button', { class: 'lib-item ea-item', type: 'button', 'data-ea': it.id, title: 'Watch it on the stage',
        onclick: () => open(it) },
      h('b', {}, it.name),
      h('div', { class: 'sub' }, h('span', { class: 'chip' }, it.category), h('span', {}, (it.locations || [])[0] || ''),
        it.seconds ? h('span', {}, `${(+it.seconds).toFixed(1)} s`) : null, it.loop ? h('span', { class: 'chip' }, 'loops') : null)));
    }
    if (r.total > r.items.length) list.append(h('div', { class: 'hint' }, `Showing the first ${r.items.length} - search to narrow it down.`));
  }

  // the server reads the game's clips once in the background: say how far it is, and look again every 1.5 s
  async function waitForGame() {
    let st = null;
    try { st = await fetchJson('/api/ea_status'); } catch (e) { count.textContent = plainError(e, "the game's animations"); return; }
    if (closed) return;
    list.innerHTML = '';
    if (st.error && !st.ready) {
      count.textContent = gameMissing(st.error) ? plainError(st.error, "the game's own animations")
        : `The game's animations could not be read: ${st.error}`;
      return;
    }
    const steps = ['index', 'library'].filter(k => ['ready', 'cached'].includes(st[k])).length;
    count.textContent = `Reading the game's own animations (${steps + 1} of 3) - the first time takes a minute or two. This window fills in by itself.`;
    timer = setTimeout(load, 1500);
  }

  async function open(it) {
    if (busy) return;
    busy = true;
    const row = list.querySelector(`[data-ea="${CSS.escape(it.id)}"]`);
    row && row.classList.add('active');
    try {
      const a = await fetchJson('/api/ea_animation?' + new URLSearchParams({ id: it.id, step: 1 }));
      const anim = asLibraryAnimation(a, state.pairing);
      dlg.close();
      hideHome(app);
      app.library.startPreview(anim);
      toast(`"${anim.name}" from The Sims 4 - "Use this pose" or "Import as keys" in the bar under the stage.`, 'ok');
    } catch (e) {
      toast(plainError(e, 'that animation'), 'err');
      row && row.classList.remove('active');
    } finally { busy = false; }
  }
  load();
  return dlg;
}

// ---------------------------------------------------------------- the game's idles (Motion step)
let idles = null;           // {ready, groups} once read
function loadIdles() {
  if (idles && idles.ready) return Promise.resolve(idles);
  return fetchJson('/api/ea_idles').then(r => { idles = r; return r; });
}

function idleSection(app, root) {
  const sim = app.store.sim();
  const layers = sim ? (sim.layers || []).filter(l => l.type === 'idle') : [];
  if (!layers.length) return;
  const box = h('div', { class: 'ea-idles' });
  root.append(section(['Idle from the game', h('span', { class: 'count' }, sim.label)], box,
    h('div', { class: 'hint' }, 'Real breathing and small shifts from The Sims 4, played on top of the pose. Pick the one that fits where the sim is.')));
  const fill = r => {
    box.innerHTML = '';
    for (const l of layers) {
      const clip = (l.params && l.params.clip) || 'a_idle_neutral_loop_3_x';
      const sel = h('select', { 'data-idle-layer': l.id },
        r.groups.map(g => h('optgroup', { label: g.label }, g.items.map(it => h('option', { value: it.name, selected: it.name === clip }, it.label)))));
      if (!r.groups.some(g => g.items.some(it => it.name === clip))) sel.prepend(h('option', { value: clip, selected: true }, clip));
      sel.onchange = () => {
        app.store.checkpoint('Game idle');
        l.params = { ...(l.params || {}), clip: sel.value };
        app.layersChanged(true);
        sel.blur();
      };
      const d = IDLE_CACHE[clip];
      box.append(h('label', { class: 'field' }, h('span', {}, layers.length > 1 ? 'Idle ' + (layers.indexOf(l) + 1) : 'Plays'), sel),
        d && d.error ? h('div', { class: 'hint warn' }, icon('x'), ' ', plainError(d.error, 'this idle')) : null);
    }
  };
  box.append(h('div', { class: 'hint' }, "Reading the game's idles..."));
  loadIdles().then(r => {
    if (!box.isConnected) return;
    if (!r.ready) {
      // still being read, or it can't be (no game on this PC): the status says which
      return fetchJson('/api/ea_status').catch(e => ({ error: e.message })).then(st => {
        if (!box.isConnected) return;
        box.innerHTML = '';
        if (st && st.error && !st.ready) { box.append(h('div', { class: 'hint warn' }, plainError(st.error, "the game's idles"))); return; }
        box.append(h('div', { class: 'hint' }, "The game's idles are being read (the first time takes a minute or two)."));
        setTimeout(() => { if (box.isConnected && app.step === 'motion') app.renderStep(); }, 2500);
      });
    }
    fill(r);
  }).catch(e => {
    if (!box.isConnected) return;
    box.innerHTML = '';
    box.append(h('div', { class: 'hint' }, plainError(e, "the game's idles")));
  });
}

// ---------------------------------------------------------------- plug in
export function install(app) {
  if (!app || app.__ea) return;
  app.__ea = true;
  for (const [id, svg] of Object.entries(ICONS)) addIcon(id, svg);
  const hooks = app.hooks || {};
  const add = (name, fn) => { const list = name.split('.').reduce((o, k) => o && o[k], hooks); if (Array.isArray(list)) list.push(fn); };

  add('homeCards', a => [{ id: 'ea-library', icon: 'ea-heart', title: 'Game animations',
    text: "Start from The Sims 4's own WooHoo, kisses and cuddles.", onClick: () => openGameAnimations(a) }]);
  add('commands', a => [
    { group: 'Actions', id: 'ea-library', label: 'Game animations', icon: 'ea-heart', sub: "The Sims 4's own romance animations",
      words: 'ea sims game romance woohoo kiss make out cuddle hug massage bed library start from', run: () => openGameAnimations(a) },
  ]);
  add('helpRows', () => [{ group: 'The game', keys: ['Ctrl', 'K'], text: 'Type "Game animations" to start from The Sims 4\'s own WooHoo, kisses and cuddles' }]);
  add('sections.motion', (a, root) => idleSection(a, root));

  // an idle clip arrived (motion.js loads it the first time it plays): pose the sims again so it shows now
  window.addEventListener('wa:idle-loaded', e => {
    const name = e.detail && e.detail.name;
    const uses = app.store.project.sims.some(s => (s.layers || []).some(l => l.type === 'idle' && l.on !== false && ((l.params && l.params.clip) || 'a_idle_neutral_loop_3_x') === name));
    if (!uses) return;
    try { app.applyPoses(); } catch (err) { console.error('Idle:', err); }
    if (e.detail.ok === false) {
      const d = IDLE_CACHE[name];
      toast(plainError(d && d.error, 'the game idle'), 'err');
      if (app.step === 'motion') app.renderStep();
    }
  });

  window.wickedEA = { open: () => openGameAnimations(app), asLibraryAnimation };
}

export default install;
