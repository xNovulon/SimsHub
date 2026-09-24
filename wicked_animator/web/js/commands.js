// Everything the command palette (Ctrl+K) can do, in plain words, with the words Blender users type as aliases
// ("insert keyframe" -> Key pose, "onion skin" -> Ghosts, "turntable" -> Showcase...). Other parts of the app add
// their own through app.hooks.commands (fn(app) -> [command]); allCommands() merges them.
import { MOTIONS } from './motion.js';
import { FACE_PRESETS } from './face.js';
import { LOOKS } from './stage.js';
import { showHome } from './home.js';
import { openHelp, setReduceMotion, reduceMotionOn } from './tour.js';

const $ = id => document.getElementById(id);
const click = id => () => $(id)?.click();

export function commands(app) {
  const sim = app.store.sim(), id = sim && sim.id, who = sim ? sim.label : 'the selected sim', C = [];
  const add = (group, cid, label, run, o = {}) => C.push({ group, id: cid, label, run, ...o });
  const needSim = { when: () => !!app.store.sim() };
  add('Actions', 'play', app.playing ? 'Pause' : 'Play', () => app.setPlaying(!app.playing), { icon: app.playing ? 'pause' : 'play', keys: ['Space'], words: 'preview run start stop', pinned: true });
  add('Actions', 'key', 'Key pose', () => app.keyPose(), { icon: 'key', keys: ['K'], sub: `keep ${who}'s pose at this frame`, words: 'insert keyframe set key i', pinned: true, ...needSim });
  add('Actions', 'keyall', 'Key every sim', () => app.keyAll(), { icon: 'key', keys: ['Shift', 'K'], words: 'keyframe all' });
  add('Actions', 'delkey', 'Delete the key here', () => app.deleteKey(), { icon: 'trash', keys: ['Delete'], words: 'remove keyframe' });
  add('Actions', 'mirror', 'Mirror pose', () => app.mirrorPose(id), { icon: 'mirror', sub: 'left and right swap', words: 'flip symmetry x-mirror', ...needSim });
  add('Actions', 'reset', 'Reset pose', () => app.resetPose(id), { icon: 'reset', words: 'rest pose alt+r clear', ...needSim });
  add('Actions', 'copy', 'Copy pose', () => app.copyPose(id), { icon: 'copy', keys: ['Ctrl', 'C'], ...needSim });
  add('Actions', 'paste', 'Paste pose', () => app.pastePose(id), { icon: 'paste', keys: ['Ctrl', 'V'], ...needSim });
  add('Actions', 'undo', 'Undo', () => app.store.undoStep(), { icon: 'undo', keys: ['Ctrl', 'Z'] });
  add('Actions', 'redo', 'Redo', () => app.store.redoStep(), { icon: 'redo', keys: ['Ctrl', 'Shift', 'Z'] });
  add('Actions', 'save', 'Save', () => app.save(), { icon: 'save', keys: ['Ctrl', 'S'] });
  add('Actions', 'open', 'Open an animation', () => app.open(), { icon: 'open', keys: ['Ctrl', 'O'] });
  add('Actions', 'send', 'Send to game', () => app.exportDialog(), { icon: 'send', words: 'export package mods try', pinned: true });
  add('Actions', 'share', 'Export mod', click('btn-share'), { icon: 'package', words: 'bundle zip share upload' });
  add('Actions', 'magic', 'Magic animation (beta)', () => app.openMagic(), { icon: 'wand', words: 'auto generate one click surprise', pinned: true });
  add('Actions', 'sounds', 'Place sounds for me', () => app.autoSounds(), { icon: 'sound', words: 'auto audio claps wet' });
  add('Actions', 'record', 'Record a video', click('btn-record'), { icon: 'rec', words: 'render capture clip' });
  add('Tools', 'tool-r', 'Pose tool', () => app.setTool('rotate'), { icon: 'rotate', keys: ['R'], words: 'rotate' });
  add('Tools', 'tool-g', 'Drag tool', () => app.setTool('ik'), { icon: 'hand', keys: ['G'], words: 'ik grab limbs' });
  add('Tools', 'tool-m', 'Place tool', () => app.setTool('move'), { icon: 'move', keys: ['M'], words: 'translate whole sim' });
  if (document.querySelector('#tool-seg [data-tool="face"]')) add('Tools', 'tool-f', 'Face tool', () => app.setTool('face'), { icon: 'face', keys: ['Shift', 'F'], words: 'face bones brows lips' });
  add('View', 'showcase', 'Showcase', click('btn-showcase'), { icon: 'turn', sub: 'the camera circles the sims', words: 'turntable orbit cinematic' });
  add('View', 'ghosts', 'Ghosts', click('btn-onion'), { icon: 'ghost', words: 'onion skin' });
  add('View', 'trail', 'Motion trail', click('btn-trail'), { icon: 'trail', words: 'motion path' });
  for (const [v, l] of [['persp', '3D view'], ['front', 'Front view'], ['side', 'Side view'], ['top', 'Top view']])
    add('View', 'view-' + v, l, () => document.querySelector(`#view-seg [data-view="${v}"]`)?.click(), { icon: 'eye', words: 'numpad camera' });
  add('View', 'focus', 'Frame the selection', () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'f', code: 'KeyF' })), { icon: 'eye', keys: ['F'], words: 'frame selected focus zoom' });
  if (app.setLook) for (const [k, lk] of Object.entries(LOOKS)) add('Look', 'look-' + k, 'Lighting: ' + lk.label, () => app.setLook(k), { icon: 'light', sub: lk.sub, words: 'light look mood' });
  const vp = app.vp;
  if (vp && vp.setQualityLevel) {
    if (vp.qualityLevel > 0) add('View', 'quality-full', 'Full quality', () => { vp.keepQuality = true; vp.setQualityLevel(0); }, { icon: 'spark', words: 'fast mode graphics best' });
    else add('View', 'quality-fast', 'Fast mode', () => vp.setQualityLevel(3), { icon: 'bolt', sub: 'simpler light, smoother on slow computers', words: 'performance speed lag' });
  }
  add('Settings', 'reduce-motion', reduceMotionOn() ? 'Reduce motion: off' : 'Reduce motion: on', () => setReduceMotion(!reduceMotionOn()), { icon: 'eye', words: 'animations calm accessibility still' });
  for (const k of ['scene', 'pose', 'motion', 'body', 'face', 'sounds', 'details', 'share', 'library'])
    add('Go to', 'go-' + k, k[0].toUpperCase() + k.slice(1), () => app.showStep(k), { icon: 'arrow', words: 'step' });
  add('Go to', 'home', 'Home', () => showHome(app), { icon: 'home' });
  add('Go to', 'help', 'Controls and shortcuts', () => openHelp(app), { icon: 'help', keys: ['?'], words: 'help keys keyboard' });
  for (const pr of app.posePresets || []) add('Poses', 'pose-' + pr.id, pr.label, () => app.applyPosePreset(pr), { icon: 'pose', sub: pr.mine ? 'my pose' : (pr.hint || 'ready pose') });
  for (const [t, m] of Object.entries(MOTIONS)) add('Motions', 'mot-' + t, 'Add ' + m.label, () => app.addLayer(id, t), { icon: 'motion', sub: 'to ' + who, words: `${m.group || ''} ${m.desc || ''}`, ...needSim });
  for (const [k, f] of Object.entries(FACE_PRESETS || {})) if (f && f.face) add('Faces', 'face-' + k, 'Face: ' + f.label, () => app.setFace(id, { ...f.face }, f.label), { icon: 'face', ...needSim });
  for (const s of app.store.project.sims) add('Sims', 'sel-' + s.id, 'Select ' + s.label, () => app.selectSim(s.id), { icon: 'user' });
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
        out.push({ group: 'More', ...c, id });
      }
    } catch (e) { console.error('command hook failed', e); }
  }
  return out;
}
