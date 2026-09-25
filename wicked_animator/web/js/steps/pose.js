// Step 2, Pose: ready poses, My poses (search, folders, stars, parts), and the posing tools.
// A pose tile: click = use it; Ctrl+click = use it mirrored; press and drag sideways = blend it in (0-150%, Esc takes
// it back); right-click = more (mirrored, only one part, on the selected keys, rename, folder, favourite...).
import { h, icon, contextMenu, section } from '../ui.js';
import { PART_LABEL } from '../keyops.js';

const BADGE = { upper: 'Upper', lower: 'Lower', hands: 'Hands', 'L hand': 'L hand', 'R hand': 'R hand', face: 'Face' };

// A press on a tile: a click (the button's own click - also a keyboard press or a test's click()), or, after 8 px
// sideways, a live blend (the click that follows it is swallowed).
function tileGestures(app, tile, pr) {
  let start = null, blend = null, badge = null;
  const onKey = e => { if (e.key === 'Escape' && blend) { e.preventDefault(); e.stopPropagation(); const b = blend; finish(); app._swallowTileClick = performance.now(); b.cancel(); } };
  const finish = () => {
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', up);
    window.removeEventListener('keydown', onKey, true);
    tile.classList.remove('blending');
    if (badge) { badge.remove(); badge = null; }
    blend = null; start = null;
  };
  const move = e => {
    if (!start) return;
    const dx = e.clientX - start.x;
    if (!blend) {
      if (Math.abs(dx) < 8) return;
      blend = app.beginPoseBlend(pr);
      tile.classList.add('blending');
      badge = h('span', { class: 'blend-badge' }, '0%');
      tile.append(badge);
    }
    const amount = Math.max(0, Math.min(1.5, Math.abs(dx) / 160));
    blend.update(amount);
    badge.textContent = Math.round(amount * 100) + '%';
  };
  const up = () => {
    const was = blend;
    finish();
    // (the panel may be drawn again before the click arrives: the app remembers to swallow it)
    if (was) { app._swallowTileClick = performance.now(); was.end(); }
  };
  // the picture must never start the browser's own drag (it would take the pointer away)
  tile.addEventListener('dragstart', e => e.preventDefault());
  tile.addEventListener('pointerdown', e => {
    if (e.button !== 0 || e.target.closest('.tile-del')) return;
    start = { x: e.clientX };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('keydown', onKey, true);
  });
  tile.addEventListener('click', e => {
    if (performance.now() - (app._swallowTileClick || -1e9) < 500) { app._swallowTileClick = 0; return; }
    if (e.target.closest('.tile-del')) return;
    app.applyPosePreset(pr, e.ctrlKey || e.metaKey ? { flipped: true } : {});
  });
}

export function renderPose(app, root) {
  const sim = app.store.sim();
  const mode = app._poseMode || 'couple';
  const tabs = h('div', { class: 'seg-inline' },
    h('button', { class: mode === 'couple' ? 'on' : '', onclick: () => { app._poseMode = 'couple'; app.refreshPanels(); } }, 'Two sims'),
    h('button', { class: mode === 'solo' ? 'on' : '', onclick: () => { app._poseMode = 'solo'; app.refreshPanels(); } }, 'One sim'),
    h('button', { class: mode === 'mine' ? 'on' : '', onclick: () => { app._poseMode = 'mine'; app.refreshPanels(); } }, 'My poses'));
  // search (remembered while the step is open) and, for My poses, chips: All · Whole body · Couples · Hands · Faces · ★ · folders
  const q = (app._poseSearch || '').trim().toLowerCase();
  const search = h('input', { class: 'text', type: 'search', placeholder: 'Find a pose…', value: app._poseSearch || '', 'aria-label': 'Find a pose' });
  search.addEventListener('input', () => {
    app._poseSearch = search.value;
    const pos = search.selectionStart;
    app.renderStep();
    const again = document.querySelector('#panel-body .pose-search input');
    if (again) { again.focus(); try { again.setSelectionRange(pos, pos); } catch { /* not a text box */ } }
  });
  const chip = app._poseChip || 'all';
  const mine = (app.posePresets || []).filter(x => x.mine);
  // (a folder named like a built-in chip - Hands, Faces, Couples - is that chip already)
  const folders = [...new Set(mine.map(x => x.folder).filter(Boolean))].filter(f => !/^(hands?|faces?|couples?|all|whole body|★)$/i.test(f)).sort();
  const chips = mode === 'mine' && mine.length ? h('div', { class: 'pose-chips' },
    [['all', 'All'], ['whole', 'Whole body'], ['couple', 'Couples'], ['hands', 'Hands'], ['face', 'Faces'], ['fav', '★'], ...folders.map(f => ['folder:' + f, f])]
      .map(([id, t]) => h('button', { class: 'chipbtn' + (chip === id ? ' on' : ''), onclick: () => { app._poseChip = chip === id ? 'all' : id; app.renderStep(); } }, t))) : null;
  const byChip = pr => {
    if (mode !== 'mine' || chip === 'all') return true;
    const part = pr.part || 'all';
    if (chip === 'whole') return part === 'all';
    if (chip === 'couple') return pr.group === 'couple' || (pr.sims || []).length > 1;
    if (chip === 'hands') return /hand/.test(part) || /^hands?$/i.test(pr.folder || '');
    if (chip === 'face') return part === 'face' || /^faces?$/i.test(pr.folder || '');
    if (chip === 'fav') return !!pr.fav;
    if (chip.startsWith('folder:')) return pr.folder === chip.slice(7);
    return true;
  };
  const grid = h('div', { class: 'tiles pose-tiles' });
  const presets = (app.posePresets || []).filter(x => (mode === 'mine' ? x.mine : !x.mine && x.group === mode))
    .filter(byChip)
    .filter(x => !q || `${x.label} ${x.folder || ''} ${x.hint || ''} ${x.source ? x.source.name : ''}`.toLowerCase().includes(q));
  if (mode === 'mine') presets.sort((a, b) => (b.fav ? 1 : 0) - (a.fav ? 1 : 0));
  if (!app.posePresets) grid.append(h('div', { class: 'empty' }, 'Loading poses from your animations...'));
  else if (!presets.length) grid.append(h('div', { class: 'empty', style: { gridColumn: '1/-1' } }, q ? `No pose matches "${app._poseSearch}".` : mode === 'mine' ? 'Save a pose with the button below and it shows up here.' : 'No poses found for this.'));
  for (const pr of presets) {
    const img = app.poseThumb(pr);
    const on = app._lastPreset === pr.id;          // the pose used last is marked, so you can find it again
    // the tooltip repeats the short description (short screens hide it under the name)
    const tipText = [pr.hint, pr.source ? `From "${pr.source.name}" by ${pr.source.author}` : '', 'Click to use · drag sideways to blend it in · Ctrl+click for the mirrored pose · right-click for more'].filter(Boolean).join(' · ');
    const part = pr.part && pr.part !== 'all' ? pr.part : null;
    // the tile just picked rings once and its check pops (design 4.3; the marker lives for one render)
    const tile = h('button', { class: 'tile' + (on ? ' on' : '') + (app._justPicked === pr.id ? ' pop' : ''), title: tipText,
      oncontextmenu: e => { e.preventDefault(); app.poseMenu(pr, e.clientX, e.clientY); } },
      h('div', { class: 'thumb' }, img ? h('img', { src: img, alt: '', draggable: 'false' }) : icon(part === 'face' ? 'face' : 'pose')),
      on ? h('span', { class: 'tile-check', title: 'Used last' }, icon('check')) : null,
      part && !on ? h('span', { class: 'part-badge', title: `Only the ${(PART_LABEL[part] || part).toLowerCase()}` }, BADGE[part] || part) : null,
      pr.fav ? h('span', { class: 'fav-badge', title: 'Favourite' }, '★') : null,
      // your own poses can be deleted (a click on the bin never applies the pose)
      pr.mine ? h('span', { class: 'tile-del', role: 'button', title: 'Delete this pose', onclick: e => { e.stopPropagation(); app.deleteMyPose(pr.id); } }, icon('trash')) : null,
      h('b', {}, pr.label), pr.hint ? h('small', {}, pr.hint) : pr.folder ? h('small', {}, pr.folder) : null);
    tileGestures(app, tile, pr);
    grid.append(tile);
  }
  // Magic: a card above the poses; on short screens a one-line bar under them instead, so two rows of poses fit
  const magic = compact => h('div', { class: 'magic-callout ' + (compact ? 'compact' : 'full') },
    compact ? h('div', { style: { flex: 1 } }, h('b', {}, 'Want it all done for you?'))
      : h('div', { style: { flex: 1 } }, h('b', {}, 'Want it all done for you?'), h('span', {}, 'Magic Animation poses and moves both sims, with sound, in one click.')),
    h('button', { class: 'btn magic small', onclick: () => app.openMagic() }, icon('wand'), 'Magic'));
  root.append(magic(false));
  root.append(section('Ready poses', tabs, h('div', { style: { height: '10px' } }), h('div', { class: 'pose-search' }, search), chips, grid,
    h('div', { class: 'hint' }, mode === 'couple' ? 'Puts both sims in the pose at this frame. Drag a pose sideways to blend it in. Undo with Ctrl+Z.'
      : mode === 'solo' ? `Puts ${sim ? sim.label : 'the selected sim'} in the pose, where it stands now. Ctrl+click: mirrored.`
      : 'Your saved poses. Right-click one to rename it, put it in a folder or star it.'),
    mode === 'mine' ? h('div', { class: 'btn-grid' },
      h('button', { class: 'btn small', onclick: () => app.exportPoses(), title: 'Save My poses as a file to give to a friend' }, icon('package'), 'Share my poses'),
      h('button', { class: 'btn small', onclick: () => app.pickPosesFile(), title: 'Add poses from a file someone shared' }, icon('open'), 'Add poses from a file')) : null));
  root.append(magic(true));

  // Paste pose: the main part pastes it all; the arrow offers one part only, or mirrored
  const pasteMenu = e => {
    const r = e.currentTarget.getBoundingClientRect();
    contextMenu(r.left, r.bottom + 4, [
      { heading: 'Paste pose' },
      { label: 'Upper body only', icon: 'pose', onClick: () => app.pastePose(sim.id, { mask: 'upper' }) },
      { label: 'Lower body only', icon: 'pose', onClick: () => app.pastePose(sim.id, { mask: 'lower' }) },
      { label: 'Hands only', icon: 'hand', onClick: () => app.pastePose(sim.id, { mask: 'hands' }) },
      { label: 'Face only', icon: 'face', onClick: () => app.pastePose(sim.id, { mask: 'face' }) },
      { label: 'Mirrored', icon: 'mirror', onClick: () => app.pastePose(sim.id, { flipped: true }) },
    ]);
  };
  const canPaste = !!sim && !!app.clipboard;
  const tools = h('div', { class: 'btn-grid' },
    h('button', { class: 'btn small', disabled: !sim, onclick: () => app.mirrorPose(sim.id) }, icon('mirror'), 'Mirror pose'),
    h('button', { class: 'btn small', disabled: !sim, onclick: () => app.resetPose(sim.id) }, icon('reset'), 'Stand straight'),
    h('button', { class: 'btn small', disabled: !sim, onclick: () => app.copyPose(sim.id) }, icon('copy'), 'Copy pose'),
    h('div', { class: 'split-btn' },
      h('button', { class: 'btn small', disabled: !canPaste, onclick: () => app.pastePose(sim.id) }, icon('paste'), 'Paste pose'),
      h('button', { class: 'btn small', disabled: !canPaste && !(sim && app.faceClipboard), title: 'Paste only a part, or mirrored', onclick: pasteMenu }, icon('down'))),
    h('button', { class: 'btn small', disabled: !sim, onclick: () => app.turnSim(sim.id, 90) }, icon('turn'), 'Turn left'),
    h('button', { class: 'btn small', disabled: !sim, onclick: () => app.turnSim(sim.id, -90) }, icon('turn', true), 'Turn right'),
    h('button', { class: 'btn small', disabled: !sim, onclick: () => app.saveMyPose(sim.id) }, icon('save'), 'Save to My poses'),
    h('button', { class: 'btn small', disabled: !sim, onclick: () => app.setMirrorEdit(!app.mirrorEdit), title: 'Pose both sides at once (X)' }, icon('mirror'), app.mirrorEdit ? 'Symmetry: on' : 'Symmetry: off'),
    h('button', { class: 'btn small', disabled: !app.store.project.sims.length, onclick: () => app.mirrorAnimation(), title: 'Every key of every sim, left and right swapped - it becomes a new animation' }, icon('mirror'), 'Mirror the whole animation'));
  root.append(section(['Posing', sim ? h('span', { class: 'count' }, sim.label) : ''],
    h('div', { class: 'hint' }, h('b', {}, 'Pose'), ' - click a body part, turn it with the coloured rings. ', h('b', {}, 'Drag'), ' - pull hands, feet or hips; knees and elbows follow. ', h('b', {}, 'Place'), ' - move or turn the whole sim.'),
    tools,
    h('div', { class: 'hint' }, 'Pinned hands and feet stay put when the body moves - pin them in the right panel or Alt+click a dot in Drag.')));
}
