// Everything the command palette (Ctrl+K) can do, in plain words, with the words Blender users type as aliases
// ("insert keyframe" -> Key pose, "onion skin" -> Ghosts, "turntable" -> Showcase...). Other parts of the app add
// their own through app.hooks.commands (fn(app) -> [command]); allCommands() merges them.
import { MOTIONS } from './motion.js';
import { FACE_PRESETS } from './face.js';
import { LOOKS } from './stage.js';
import { showHome } from './home.js';
import { openHelp, setReduceMotion, reduceMotionOn } from './tour.js';
import { $t } from './i18n.js';

const $ = id => document.getElementById(id);
const click = id => () => $(id)?.click();

export function commands(app) {
  const sim = app.store.sim(), id = sim && sim.id, who = sim ? sim.label : $t('commands.selected_sim'), C = [];
  const add = (group, cid, label, run, o = {}) => C.push({ group, id: cid, label, run, ...o });
  const needSim = { when: () => !!app.store.sim() };
  const STEP_NAMES = { scene: $t('commands.step_scene'), pose: $t('commands.step_pose'), motion: $t('commands.step_motion'), body: $t('commands.step_body'), face: $t('commands.step_face'),
    sounds: $t('commands.step_sounds'), details: $t('commands.step_details'), share: $t('commands.step_share'), library: $t('commands.step_library') };
  add($t('commands.actions'), 'play', app.playing ? $t('commands.pause') : $t('commands.play'), () => app.setPlaying(!app.playing), { icon: app.playing ? 'pause' : 'play', keys: ['Space'], words: 'preview run start stop', pinned: true });
  add($t('commands.actions'), 'key', $t('commands.key_pose'), () => app.keyPose(), { icon: 'key', keys: ['K'], sub: $t('commands.keep_s_pose_at_this', { who }), words: 'insert keyframe set key i', pinned: true, ...needSim });
  add($t('commands.actions'), 'keyall', $t('commands.key_every_sim'), () => app.keyAll(), { icon: 'key', keys: ['Shift', 'K'], words: 'keyframe all' });
  add($t('commands.actions'), 'delkey', $t('commands.delete_key_here'), () => app.deleteKey(), { icon: 'trash', keys: ['Delete'], words: 'remove keyframe' });
  add($t('commands.actions'), 'mirror', $t('commands.mirror_pose'), () => app.mirrorPose(id), { icon: 'mirror', sub: $t('commands.left_and_right_swap'), words: 'flip symmetry x-mirror', ...needSim });
  add($t('commands.actions'), 'reset', $t('commands.reset_pose'), () => app.resetPose(id), { icon: 'reset', words: 'rest pose alt+r clear', ...needSim });
  add($t('commands.actions'), 'copy', $t('commands.copy_pose'), () => app.copyPose(id), { icon: 'copy', keys: ['Ctrl', 'C'], ...needSim });
  add($t('commands.actions'), 'paste', $t('commands.paste_pose'), () => app.pastePose(id), { icon: 'paste', keys: ['Ctrl', 'V'], ...needSim });
  add($t('commands.actions'), 'undo', $t('commands.undo'), () => app.store.undoStep(), { icon: 'undo', keys: ['Ctrl', 'Z'] });
  add($t('commands.actions'), 'redo', $t('commands.redo'), () => app.store.redoStep(), { icon: 'redo', keys: ['Ctrl', 'Shift', 'Z'] });
  add($t('commands.actions'), 'save', $t('commands.save'), () => app.save(), { icon: 'save', keys: ['Ctrl', 'S'] });
  add($t('commands.actions'), 'open', $t('commands.open_animation'), () => app.open(), { icon: 'open', keys: ['Ctrl', 'O'] });
  add($t('commands.actions'), 'send', $t('commands.send_to_game'), () => app.exportDialog(), { icon: 'send', words: 'export package mods try', pinned: true });
  add($t('commands.actions'), 'share', $t('commands.export_mod'), click('btn-share'), { icon: 'package', words: 'bundle zip share upload' });
  add($t('commands.actions'), 'magic', $t('commands.magic_animation'), () => app.openMagic(), { icon: 'wand', words: 'auto generate one click surprise', pinned: true });
  add($t('commands.actions'), 'sounds', $t('commands.place_sounds_for_me'), () => app.autoSounds(), { icon: 'sound', words: 'auto audio claps wet' });
  add($t('commands.actions'), 'record', $t('commands.record_video'), click('btn-record'), { icon: 'rec', words: 'render capture clip' });
  add($t('commands.tools'), 'tool-r', $t('commands.pose_tool'), () => app.setTool('rotate'), { icon: 'rotate', keys: ['R'], words: 'rotate' });
  add($t('commands.tools'), 'tool-g', $t('commands.drag_tool'), () => app.setTool('ik'), { icon: 'hand', keys: ['G'], words: 'ik grab limbs' });
  add($t('commands.tools'), 'tool-m', $t('commands.place_tool'), () => app.setTool('move'), { icon: 'move', keys: ['M'], words: 'translate whole sim' });
  if (document.querySelector('#tool-seg [data-tool="face"]')) add($t('commands.tools'), 'tool-f', $t('commands.face_tool'), () => app.setTool('face'), { icon: 'face', keys: ['Shift', 'F'], words: 'face bones brows lips' });
  add($t('commands.view'), 'showcase', $t('commands.showcase'), click('btn-showcase'), { icon: 'turn', sub: $t('commands.camera_circles_sims'), words: 'turntable orbit cinematic' });
  add($t('commands.view'), 'ghosts', $t('commands.ghosts'), click('btn-onion'), { icon: 'ghost', words: 'onion skin' });
  add($t('commands.view'), 'trail', $t('commands.motion_trail'), click('btn-trail'), { icon: 'trail', words: 'motion path' });
  for (const [v, l] of [['persp', $t('commands.view_3d')], ['front', $t('commands.front_view')], ['side', $t('commands.side_view')], ['top', $t('commands.top_view')]])
    add($t('commands.view'), 'view-' + v, l, () => document.querySelector(`#view-seg [data-view="${v}"]`)?.click(), { icon: 'eye', words: 'numpad camera' });
  add($t('commands.view'), 'focus', $t('commands.frame_selection'), () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'f', code: 'KeyF' })), { icon: 'eye', keys: ['F'], words: 'frame selected focus zoom' });
  if (app.setLook) for (const [k, lk] of Object.entries(LOOKS)) add($t('commands.look'), 'look-' + k, $t('commands.lighting', { look: lk.label }), () => app.setLook(k), { icon: 'light', sub: lk.sub, words: 'light look mood' });
  const vp = app.vp;
  if (vp && vp.setQualityLevel) {
    if (vp.qualityLevel > 0) add($t('commands.view'), 'quality-full', $t('commands.full_quality'), () => { vp.keepQuality = true; vp.setQualityLevel(0); }, { icon: 'spark', words: 'fast mode graphics best' });
    else add($t('commands.view'), 'quality-fast', $t('commands.fast_mode'), () => vp.setQualityLevel(3), { icon: 'bolt', sub: $t('commands.simpler_light_smoother_on_slow'), words: 'performance speed lag' });
  }
  add($t('commands.settings'), 'reduce-motion', reduceMotionOn() ? $t('commands.reduce_motion_off') : $t('commands.reduce_motion_on'), () => setReduceMotion(!reduceMotionOn()), { icon: 'eye', words: 'animations calm accessibility still' });
  for (const k of ['scene', 'pose', 'motion', 'body', 'face', 'sounds', 'details', 'share', 'library'])
    add($t('commands.go_to'), 'go-' + k, STEP_NAMES[k] || k, () => app.showStep(k), { icon: 'arrow', words: 'step' });
  add($t('commands.go_to'), 'home', $t('commands.home'), () => showHome(app), { icon: 'home' });
  add($t('commands.go_to'), 'help', $t('commands.controls_and_shortcuts'), () => openHelp(app), { icon: 'help', keys: ['?'], words: 'help keys keyboard' });
  for (const pr of app.posePresets || []) add($t('commands.poses'), 'pose-' + pr.id, pr.label, () => app.applyPosePreset(pr), { icon: 'pose', sub: pr.mine ? $t('commands.my_pose') : (pr.hint || $t('commands.ready_pose')) });
  for (const [t, m] of Object.entries(MOTIONS)) add($t('commands.motions'), 'mot-' + t, $t('commands.add', { mLabel: m.label }), () => app.addLayer(id, t), { icon: 'motion', sub: $t('commands.to_who', { who }), words: `${m.group || ''} ${m.desc || ''}`, ...needSim });
  for (const [k, f] of Object.entries(FACE_PRESETS || {})) if (f && f.face) add($t('commands.faces'), 'face-' + k, $t('commands.face_preset', { face: f.label }), () => app.setFace(id, { ...f.face }, f.label), { icon: 'face', ...needSim });
  for (const s of app.store.project.sims) add($t('commands.sims'), 'sel-' + s.id, $t('commands.select', { sLabel: s.label }), () => app.selectSim(s.id), { icon: 'user' });
  return C;
}

// The app's commands plus every app.hooks.commands entry (a failing entry is skipped and logged).
export function allCommands(app) {
  const out = commands(app);
  const seen = new Set(out.map(c => c.id));
  for (const fn of (app.hooks && app.hooks.commands) || []) {
    try {
      for (const c of fn(app) || []) {
        if (!c || !c.label || typeof c.run !== 'function') continue;
        const id = c.id || 'hook-' + c.label;
        if (seen.has(id)) continue;
        seen.add(id);
        out.push({ group: $t('commands.more'), ...c, id });
      }
    } catch (e) { console.error('command hook failed', e); }
  }
  return out;
}
