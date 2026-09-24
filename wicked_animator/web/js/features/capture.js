// "Copy real moves" in the app (plan 2.4 / 2.6): a Pose-step section (From a video / From my webcam / From a photo), a
// Face-step button (Copy my face), palette commands, a Home card "Film it, play it" and Help rows. The studio itself
// (web/js/capture.js and web/js/capture/*) loads only when one of these is used.
import { h, icon, section } from '../ui.js';
import { ensureIcons, ensureStyles } from '../capture/icons.js';
import { $t } from '../i18n.js';

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
    root.append(section($t('features.capture.copy_real_moves'),
      h('div', { class: 'cap-entry' },
        entryButton(a, 'video', 'cap-video', $t('features.capture.from_video'), $t('features.capture.any_video_of_real_person')),
        entryButton(a, 'webcam', 'cap-webcam', $t('features.capture.from_my_webcam'), $t('features.capture.act_it_out_yourself')),
        entryButton(a, 'photo', 'cap-photo', $t('features.capture.from_photo'), $t('features.capture.copy_one_pose'))),
      h('div', { class: 'cap-private' }, icon('cap-shield'), $t('features.capture.adults_only_your_videos_never'))));
  });
  // Face step: "Copy my face (webcam)"
  hk.sections && hk.sections.face && hk.sections.face.push((a, root) => {
    root.append(section($t('features.capture.copy_your_face'),
      h('button', { class: 'btn block soft cap-face-btn', 'data-capture': 'face', onclick: () => open(a, 'face') }, icon('cap-face'), $t('features.capture.copy_my_face_webcam')),
      h('div', { class: 'hint' }, $t('features.capture.your_sim_copies_your_expressions'))));
  });
  // command palette
  hk.commands && hk.commands.push(a => [
    { group: $t('features.capture.actions'), id: 'capture-video', label: $t('features.capture.copy_moves_from_video'), icon: 'cap-video', words: 'motion capture mocap video film record copy real moves', run: () => open(a, 'video') },
    { group: $t('features.capture.actions'), id: 'capture-webcam', label: $t('features.capture.copy_moves_from_my_webcam'), icon: 'cap-webcam', words: 'motion capture mocap webcam camera act live', run: () => open(a, 'webcam') },
    { group: $t('features.capture.actions'), id: 'capture-photo', label: $t('features.capture.copy_pose_from_photo'), icon: 'cap-photo', words: 'pose from picture photo image reference scan', run: () => open(a, 'photo') },
    { group: $t('features.capture.actions'), id: 'capture-face', label: $t('features.capture.copy_my_face_webcam'), icon: 'cap-face', words: 'face capture facial mocap expression webcam', run: () => open(a, 'face') },
  ]);
  // Home: "Film it, play it"
  hk.homeCards && hk.homeCards.push(a => [{
    id: 'capture', title: $t('features.capture.film_it_play_it'), text: $t('features.capture.turn_video_or_your_webcam'), icon: 'cap-film',
    onClick: () => {
      // a scene with a sim to put the moves on: start one when Home has none open
      if (!a.store.project.sims.length && typeof a.newScene === 'function') a.newScene(false, false, 'solo');
      open(a, 'video');
    },
  }]);
  // Help
  hk.helpRows && hk.helpRows.push(() => [
    { group: $t('features.capture.copy_real_moves'), keys: ['Space'], text: $t('features.capture.start_and_stop_recording_from') },
    { group: $t('features.capture.copy_real_moves'), keys: ['T'], text: $t('features.capture.hold_it_tongue_out_while') },
    { group: $t('features.capture.copy_real_moves'), keys: ['Esc'], text: $t('features.capture.close_capture_studio') },
    { group: $t('features.capture.copy_real_moves'), keys: ['Ctrl', 'K'], text: $t('features.capture.type_copy_to_copy_moves') },
  ]);
}

export default install;
