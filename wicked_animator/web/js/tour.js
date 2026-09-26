// Help (all controls), the "Reduce motion" switch, and a short first-run tour that points at the important parts.
import { h, modal, toggle } from './ui.js';
import { localStorageGet, localStorageSet } from './state.js';

// Reduce motion: the in-app switch (the OS setting works too). Stored as fsa.reduceMotion; index.html applies it
// before anything paints.
export const reduceMotionOn = () => document.documentElement.classList.contains('reduce-motion');
export function setReduceMotion(on) {
  document.documentElement.classList.toggle('reduce-motion', !!on);
  localStorageSet('reduceMotion', !!on);
}

export function openHelp(app = window.app) {
  const row = (a, b) => h('div', {}, h('span', {}, a), h('span', {}, b));
  const k = (...keys) => h('span', {}, ...keys.map(x => h('kbd', {}, x)));
  // rows other parts of the app add (app.hooks.helpRows: fn(app) -> [{group, keys, text}]), under their own headings
  const extra = new Map();
  for (const fn of (app && app.hooks && app.hooks.helpRows) || []) {
    try { for (const r of fn(app) || []) { if (!r || !r.text) continue; if (!extra.has(r.group || 'More')) extra.set(r.group || 'More', []); extra.get(r.group || 'More').push(r); } }
    catch (e) { console.error('help rows', e); }
  }
  const keyCell = keys => (Array.isArray(keys) ? k(...keys) : keys || '');
  const extraBlocks = [...extra.entries()].flatMap(([g, rows]) => [h('div', { class: 'help-h' }, g), h('div', { class: 'help-grid' }, rows.map(r => row(keyCell(r.keys), r.text)))]);
  modal({
    title: 'Controls', wide: true,
    body: h('div', {},
      h('div', { class: 'help-h' }, 'Camera (like Roblox Studio)'),
      h('div', { class: 'help-grid' },
        row(k('W', 'A', 'S', 'D'), 'Fly forward, left, back, right'), row(k('Q', 'E'), 'Down / up'),
        row(k('Shift'), 'Hold to fly slower'), row('Right mouse drag', 'Look around (360°)'),
        row('Mouse wheel', 'Move in / out'), row('Middle mouse drag', 'Slide the view'),
        row(k('F'), 'Focus on the selected part'), row('Left click', 'Never moves the camera - it picks body parts')),
      h('div', { class: 'help-h' }, 'Posing'),
      h('div', { class: 'help-grid' },
        row(k('R'), 'Turn the picked part (rings)'), row(k('T'), 'Move the picked part (arrows)'),
        row(k('G'), 'Drag tool: pull hands, feet, hips'), row(k('M'), "Move tool · the circle at a sim's feet moves the whole sim"),
        row('Alt + click a dot', 'Pin a hand or foot (Drag tool)'), row(k('Esc'), 'Let go of the selection'),
        row(k('Ctrl', 'C'), 'Copy pose'), row(k('Ctrl', 'V'), 'Paste pose'),
        row(k('Ctrl', 'Shift', 'V'), 'Paste pose mirrored'), row('Hover', 'The part under the mouse glows'),
        row('Ctrl + click a pose', 'Use it mirrored'), row('Drag a pose sideways', 'Blend it in (0-150%)'),
        row('Right-click a pose', 'Only a part, on the selected keys, folders, favourites')),
      h('div', { class: 'help-h' }, 'Timeline'),
      h('div', { class: 'help-grid' },
        row(k('Space'), 'Play / pause'), row(k('K'), 'Key the selected sim here'),
        row(k('Shift', 'K'), 'Key every sim here'), row(k('Delete'), 'Delete the key here'),
        row(k(','), 'Previous key'), row(k('.'), 'Next key'),
        row(k('←', '→'), 'One frame back / forward'), row(k('Home'), 'First frame'),
        row('Double-click a lane', 'Key there'), row('Right-click a key', 'Easing, copy, delete'),
        row('Shift + drag a key', 'Move that key on every sim'), row('Wheel on the timeline', 'Zoom (Shift: scroll)'),
        row('Wheel on the sim names', 'Scroll when there are many sims'), row('Loop length box', 'Stretch the animation, or keep its speed'),
        row('Ctrl + click a key', 'Add it to the selection'), row('Shift + click a key', "Every sim's key on that frame"),
        row('Ctrl + drag on the lanes', 'Select keys with a box'), row('Drag selected keys', 'Move them'),
        row('Alt + drag', 'Stretch them from the playhead'), row(k('Ctrl', 'C') , 'Copy keys (over the timeline)'),
        row(k('Ctrl', 'V'), 'Paste keys at the playhead'), row(k('Ctrl', 'Shift', 'V'), 'Paste keys mirrored'),
        row(k('Ctrl', 'D'), 'Duplicate keys to the playhead'), row(k('Ctrl', '←', '→'), 'Move selected keys a frame (Shift: 5)'),
        row(k('Ctrl', 'A'), 'Select every key'), row(k('Shift', 'E'), 'In-between key here (over the timeline)'),
        row(k('P'), 'Play only the selected part'), row(k('Tab'), 'Keys / Curves'),
        row('Ctrl + drag in the ruler', 'Play only a part'), row('Right-click Undo', 'Undo history'),
        row('Right-click the ruler', 'Loop tools, play range'), row('Right-click the Ghosts button', 'Ghost options')),
      h('div', { class: 'help-h' }, 'Files'),
      h('div', { class: 'help-grid' },
        row(k('Ctrl', 'S'), 'Save'), row(k('Ctrl', 'O'), 'Open'), row(k('Ctrl', 'Z'), 'Undo'), row(k('Ctrl', 'Shift', 'Z'), 'Redo (or Ctrl+Y)'),
        row(k('Ctrl', 'K'), 'Search or do anything'), row('Hold ' + 'Ctrl', 'Show every shortcut on screen')),
      ...extraBlocks,
      h('div', { class: 'help-h' }, 'Comfort'),
      h('div', { class: 'toggle-row help-motion' }, h('div', {}, h('b', {}, 'Reduce motion'), h('span', {}, 'No sliding, bouncing or confetti - things simply appear. The camera still moves where it helps you see.')),
        toggle(reduceMotionOn(), on => setReduceMotion(on))),
      h('p', { class: 'credits' }, 'Motion capture uses MediaPipe © Google LLC, Apache License 2.0.')),
    buttons: [{ label: 'Show the tour again', kind: 'ghost', onClick: () => { localStorageSet('tourDone', false); setTimeout(() => maybeTour(window.app), 100); } }, { label: 'Got it', kind: 'primary' }],
  });
}

// sel: what the ring goes around; at: what the card sits next to (default: the same); clip: the scrolling panel it
// is shown in; when: only if it applies now
const TOUR = [
  { sel: '#panel-body .tiles', title: 'Start here', text: 'Click a ready pose - both sims are placed for you. Then fine-tune it with the tools, or add motion in step 3.', side: 'right', at: '#left',
    clip: '#panel-body', when: app => app.step === 'pose' },
  { sel: '#rail', title: 'Eight simple steps', text: 'Go down the list: Scene, Pose, Motion, Body, Face, Sounds, Details, Share. Every step explains itself - you can jump around any time.', side: 'right', at: '#left' },
  { sel: '#tool-seg', title: 'Three tools', text: "Pose: click a body part and turn it. Drag: pull hands, feet and hips - the arms and legs follow. Move: click a part to move it. The circle at a sim's feet moves the whole sim. Hovering a part makes it glow.", side: 'bottom' },
  { sel: '#vp-cam', title: 'Fly around', text: 'W A S D to fly, Q / E down and up, hold Shift to go slow, right-drag to look around. Left click never moves the camera.', side: 'top' },
  { sel: '#timeline', title: 'The timeline', text: 'Your keys (diamonds), motions (bars) and sounds (notes). Drag to scrub, drag keys to move them, right-click a key to change how it flows.', side: 'top' },
  { sel: '#tl-view-seg', title: 'Curves', text: 'See how a body part turns over time and drag its keys up or down. Smooth and Simplify clean up imported animations.', side: 'top' },
  { sel: '#btn-export', title: 'Try it in the game', text: 'Send to game puts it in your Mods folder. Export mod packs animations and progressions into one file for others.', side: 'bottom' },
];

let tourPending = false;

// an element the user can actually see right now
const shown = el => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 2 && r.height > 2 && getComputedStyle(el).visibility !== 'hidden'; };

export function maybeTour(app) {
  if (localStorageGet('tourDone', false)) return;
  if (!document.getElementById('home').classList.contains('hidden')) return;
  const root = document.getElementById('tour-root');
  if (root.childElementCount || tourPending) return;              // already running or about to start
  tourPending = true;
  let steps = [];
  let i = 0;
  const show = () => {
    root.innerHTML = '';
    const step = steps[i];
    const el = document.querySelector(step.sel);
    if (!shown(el)) { i++; return i < steps.length ? show() : end(); }
    let r = el.getBoundingClientRect();
    // a part inside a scrolling panel is ringed only where it can be seen
    const box = step.clip && document.querySelector(step.clip);
    if (box) {
      const c = box.getBoundingClientRect();
      const top = Math.max(r.top, c.top), bottom = Math.min(r.bottom, c.bottom);
      r = { left: r.left, right: r.right, width: r.width, top, bottom, height: Math.max(0, bottom - top) };
    }
    const a = (step.at && shown(document.querySelector(step.at)) ? document.querySelector(step.at) : el).getBoundingClientRect();
    const ring = h('div', { class: 'tour-ring', style: { left: r.left - 6 + 'px', top: r.top - 6 + 'px', width: r.width + 12 + 'px', height: r.height + 12 + 'px' } });
    const card = h('div', { class: 'tour-card' },
      h('h4', {}, step.title), h('p', {}, step.text),
      h('div', { class: 'row' }, h('span', { class: 'grow' }, `${i + 1} / ${steps.length}`),
        h('button', { class: 'btn small ghost', onclick: end }, 'Skip'),
        h('button', { class: 'btn small primary', onclick: () => { i++; i < steps.length ? show() : end(); } }, i < steps.length - 1 ? 'Next' : 'Start animating')));
    root.append(ring, card);
    const cw = 330, ch = card.offsetHeight || 170;
    let x = a.left, y = a.bottom + 14;
    if (step.side === 'right') { x = a.right + 16; y = Math.max(r.top, a.top) + 20; }
    if (step.side === 'top') { y = r.top - ch - 16; x = r.left + 20; }
    x = Math.max(12, Math.min(innerWidth - cw - 12, x)); y = Math.max(12, Math.min(innerHeight - ch - 12, y));
    card.style.left = x + 'px'; card.style.top = y + 'px';
  };
  const end = () => { root.innerHTML = ''; localStorageSet('tourDone', true); };
  setTimeout(() => {
    tourPending = false;
    if (root.childElementCount || !document.getElementById('home').classList.contains('hidden')) return;
    // the steps that fit what is on screen now (a missing or hidden part is skipped, not the whole tour)
    steps = TOUR.filter(s => (!s.when || s.when(app)) && shown(document.querySelector(s.sel)));
    if (steps.length) show();
  }, 600);
}
