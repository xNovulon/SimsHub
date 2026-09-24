// "Copy real moves" in the app (plan 2.4 / 2.6): a Pose-step section (From a video / From my webcam / From a photo), a
// Face-step button (Copy my face), palette commands, a Home card "Film it, play it" and Help rows. The studio itself
// (web/js/capture.js and web/js/capture/*) loads only when one of these is used.
import { h, icon, section } from '../ui.js';
import { ensureIcons, ensureStyles } from '../capture/icons.js';

let studio = null;
const load = () => (studio = studio || import('../capture.js'));
const open = (app, source) => load().then(m => m.openCaptureStudio(app, { source, simId: app.store.selected.sim })).catch(e => console.error('capture', e));

function entryButton(app, source, ic, title, sub) {
  return h('button', { class: 'cap-entry-btn', 'data-capture': source, title: sub, onclick: () => open(app, source) },
    h('span', { class: 'cap-entry-icon' }, icon(ic)), h('b', {}, title), h('small', {}, sub));
}

export function install(app) {
  ensureIcons();
  ensureStyles();
  const hk = app.hooks;
  if (!hk) { console.warn('capture: this app has no plug-in points yet'); return; }
  // Pose step: "Copy real moves"
  hk.sections && hk.sections.pose && hk.sections.pose.push((a, root) => {
    root.append(section('Copy real moves',
      h('div', { class: 'cap-entry' },
        entryButton(a, 'video', 'cap-video', 'From a video', 'Any video of a real person'),
        entryButton(a, 'webcam', 'cap-webcam', 'From my webcam', 'Act it out yourself'),
        entryButton(a, 'photo', 'cap-photo', 'From a photo', 'Copy one pose')),
      h('div', { class: 'cap-private' }, icon('cap-shield'), 'Adults only. Your videos never leave this PC.')));
  });
  // Face step: "Copy my face (webcam)"
  hk.sections && hk.sections.face && hk.sections.face.push((a, root) => {
    root.append(section('Copy your face',
      h('button', { class: 'btn block soft cap-face-btn', 'data-capture': 'face', onclick: () => open(a, 'face') }, icon('cap-face'), 'Copy my face (webcam)'),
      h('div', { class: 'hint' }, 'Your sim copies your expressions, blinks and mouth. Hold T to stick your tongue out.')));
  });
  // command palette
  hk.commands && hk.commands.push(a => [
    { group: 'Actions', id: 'capture-video', label: 'Copy moves from a video', icon: 'cap-video', words: 'motion capture mocap video film record copy real moves', run: () => open(a, 'video') },
    { group: 'Actions', id: 'capture-webcam', label: 'Copy moves from my webcam', icon: 'cap-webcam', words: 'motion capture mocap webcam camera act live', run: () => open(a, 'webcam') },
    { group: 'Actions', id: 'capture-photo', label: 'Copy a pose from a photo', icon: 'cap-photo', words: 'pose from picture photo image reference scan', run: () => open(a, 'photo') },
    { group: 'Actions', id: 'capture-face', label: 'Copy my face (webcam)', icon: 'cap-face', words: 'face capture facial mocap expression webcam', run: () => open(a, 'face') },
  ]);
  // Home: "Film it, play it"
  hk.homeCards && hk.homeCards.push(a => [{
    id: 'capture', title: 'Film it, play it', text: 'Turn a video or your webcam into an animation - on this PC, no Blender.', icon: 'cap-film',
    onClick: () => {
      // a scene with a sim to put the moves on: start one when Home has none open
      if (!a.store.project.sims.length && typeof a.newScene === 'function') a.newScene(false, false, 'solo');
      open(a, 'video');
    },
  }]);
  // Help
  hk.helpRows && hk.helpRows.push(() => [
    { group: 'Copy real moves', keys: ['Space'], text: 'Start and stop recording from the webcam' },
    { group: 'Copy real moves', keys: ['T'], text: 'Hold it: tongue out while copying your face' },
    { group: 'Copy real moves', keys: ['Esc'], text: 'Close the capture studio' },
    { group: 'Copy real moves', keys: ['Ctrl', 'K'], text: 'Type "copy" to copy moves from a video, your webcam or a photo' },
  ]);
}

export default install;
