// Help (all controls), the "Reduce motion" switch, and a short first-run tour that points at the important parts.
import { h, modal, toggle } from './ui.js';
import { localStorageGet, localStorageSet } from './state.js';
import { $t } from './i18n.js';

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
    title: $t('tour.controls'), wide: true,
    body: h('div', {},
      h('div', { class: 'help-h' }, $t('tour.camera_like_roblox_studio')),
      h('div', { class: 'help-grid' },
        row(k('W', 'A', 'S', 'D'), $t('tour.fly_forward_left_back_right')), row(k('Q', 'E'), $t('tour.down_up')),
        row(k('Shift'), $t('tour.hold_to_fly_slower')), row($t('tour.right_mouse_drag'), $t('tour.look_around_360')),
        row($t('tour.mouse_wheel'), $t('tour.move_in_out')), row($t('tour.middle_mouse_drag'), $t('tour.slide_view')),
        row(k('F'), $t('tour.focus_on_selected_part')), row($t('tour.left_click'), $t('tour.never_moves_camera_it_picks'))),
      h('div', { class: 'help-h' }, $t('tour.posing')),
      h('div', { class: 'help-grid' },
        row(k('R'), $t('tour.pose_tool_click_part_turn')), row(k('G'), $t('tour.drag_tool_pull_hands_feet')),
        row(k('M'), $t('tour.place_tool_move_turn_whole')), row(k('T'), $t('tour.place_switch_move_turn')),
        row($t('tour.alt_click_dot'), $t('tour.pin_hand_or_foot_drag')), row(k('Esc'), $t('tour.let_go_of_selection')),
        row(k('Ctrl', 'C'), $t('tour.copy_pose')), row(k('Ctrl', 'V'), $t('tour.paste_pose')),
        row(k('Ctrl', 'Shift', 'V'), $t('tour.paste_pose_mirrored')), row($t('tour.hover'), $t('tour.part_under_mouse_glows')),
        row($t('tour.ctrl_click_pose'), $t('tour.use_it_mirrored')), row($t('tour.drag_pose_sideways'), $t('tour.blend_it_in_0_150')),
        row($t('tour.right_click_pose'), $t('tour.only_part_on_selected_keys'))),
      h('div', { class: 'help-h' }, $t('tour.timeline')),
      h('div', { class: 'help-grid' },
        row(k('Space'), $t('tour.play_pause')), row(k('K'), $t('tour.key_selected_sim_here')),
        row(k('Shift', 'K'), $t('tour.key_every_sim_here')), row(k('Delete'), $t('tour.delete_key_here')),
        row(k(','), $t('tour.previous_key')), row(k('.'), $t('tour.next_key')),
        row(k('←', '→'), $t('tour.one_frame_back_forward')), row(k('Home'), $t('tour.first_frame')),
        row($t('tour.double_click_lane'), $t('tour.key_there')), row($t('tour.right_click_key'), $t('tour.easing_copy_delete')),
        row($t('tour.shift_drag_key'), $t('tour.move_that_key_on_every')), row($t('tour.wheel_on_timeline'), $t('tour.zoom_shift_scroll')),
        row($t('tour.wheel_on_sim_names'), $t('tour.scroll_when_there_are_many')), row($t('tour.loop_length_box'), $t('tour.stretch_animation_or_keep_its')),
        row($t('tour.ctrl_click_key'), $t('tour.add_it_to_selection')), row($t('tour.shift_click_key'), $t('tour.every_sim_s_key_on')),
        row($t('tour.ctrl_drag_on_lanes'), $t('tour.select_keys_with_box')), row($t('tour.drag_selected_keys'), $t('tour.move_them')),
        row($t('tour.alt_drag'), $t('tour.stretch_them_from_playhead')), row(k('Ctrl', 'C') , $t('tour.copy_keys_over_timeline')),
        row(k('Ctrl', 'V'), $t('tour.paste_keys_at_playhead')), row(k('Ctrl', 'Shift', 'V'), $t('tour.paste_keys_mirrored')),
        row(k('Ctrl', 'D'), $t('tour.duplicate_keys_to_playhead')), row(k('Ctrl', '←', '→'), $t('tour.move_selected_keys_frame_shift')),
        row(k('Ctrl', 'A'), $t('tour.select_every_key')), row(k('Shift', 'E'), $t('tour.in_between_key_here_over')),
        row(k('P'), $t('tour.play_only_selected_part')), row(k('Tab'), $t('tour.keys_curves')),
        row($t('tour.ctrl_drag_in_ruler'), $t('tour.play_only_part')), row($t('tour.right_click_undo'), $t('tour.undo_history')),
        row($t('tour.right_click_ruler'), $t('tour.loop_tools_play_range')), row($t('tour.right_click_ghosts_button'), $t('tour.ghost_options'))),
      h('div', { class: 'help-h' }, $t('tour.files')),
      h('div', { class: 'help-grid' },
        row(k('Ctrl', 'S'), $t('tour.save')), row(k('Ctrl', 'O'), $t('tour.open')), row(k('Ctrl', 'Z'), $t('tour.undo')), row(k('Ctrl', 'Shift', 'Z'), $t('tour.redo_or_ctrl_y')),
        row(k('Ctrl', 'K'), $t('tour.search_or_do_anything')), row($t('tour.hold_ctrl'), $t('tour.show_every_shortcut_on_screen'))),
      ...extraBlocks,
      h('div', { class: 'help-h' }, $t('tour.comfort')),
      h('div', { class: 'toggle-row help-motion' }, h('div', {}, h('b', {}, $t('tour.reduce_motion')), h('span', {}, $t('tour.no_sliding_bouncing_or_confetti'))),
        toggle(reduceMotionOn(), on => setReduceMotion(on))),
      h('p', { class: 'credits' }, $t('tour.motion_capture_uses_mediapipe_google'))),
    buttons: [{ label: $t('tour.show_tour_again'), kind: 'ghost', onClick: () => { localStorageSet('tourDone', false); setTimeout(() => maybeTour(window.app), 100); } }, { label: $t('tour.got_it'), kind: 'primary' }],
  });
}

// sel: what the ring goes around; at: what the card sits next to (default: the same); clip: the scrolling panel it
// is shown in; when: only if it applies now
const TOUR = [
  { sel: '#panel-body .tiles', title: $t('tour.start_here'), text: $t('tour.click_ready_pose_both_sims'), side: 'right', at: '#left',
    clip: '#panel-body', when: app => app.step === 'pose' },
  { sel: '#rail', title: $t('tour.eight_simple_steps'), text: $t('tour.go_down_list_scene_pose'), side: 'right', at: '#left' },
  { sel: '#tool-seg', title: $t('tour.three_tools'), text: $t('tour.pose_click_body_part_and'), side: 'bottom' },
  { sel: '#vp-cam', title: $t('tour.fly_around'), text: $t('tour.w_s_d_to_fly'), side: 'top' },
  { sel: '#timeline', title: $t('tour.timeline_2'), text: $t('tour.your_keys_diamonds_motions_bars'), side: 'top' },
  { sel: '#tl-view-seg', title: $t('tour.curves'), text: $t('tour.see_how_body_part_turns'), side: 'top' },
  { sel: '#btn-export', title: $t('tour.try_it_in_game'), text: $t('tour.send_to_game_puts_it'), side: 'bottom' },
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
        h('button', { class: 'btn small ghost', onclick: end }, $t('tour.skip')),
        h('button', { class: 'btn small primary', onclick: () => { i++; i < steps.length ? show() : end(); } }, i < steps.length - 1 ? $t('tour.next') : $t('tour.start_animating'))));
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
