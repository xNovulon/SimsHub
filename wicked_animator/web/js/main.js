// Novulon's Wicked Animator - the app.
import * as THREE from 'three';
import { Viewport } from './viewport.js';
import { Sim } from './sim.js';
import { api, projectFileName, RECOVERY_SLOT } from './api.js';
import { Store, newSim, newProject, localStorageGet, localStorageSet, localStorageRemove, BODY_TYPES, uid } from './state.js';
import { evaluate, evaluateFace, sortKeys, blendPoses, EASE_INFO, EASE_CURVE, validCurve, setRig, roomEnd } from './animation.js';
import { Interaction } from './interact.js';
import { Timeline } from './timeline.js';
import * as KO from './keyops.js';
import { CurveView, openTimingEditor } from './curves.js';
import { References } from './reference.js';
import { buildFurniture, loadGameFurniture, disposeFurniture } from './furniture.js';
import { renderInspector } from './inspector.js';
import { focusBoneSearch } from './inspector/index.js';
import { renderScene, renderPose, renderBody, renderFace, renderSounds } from './steps.js';
import { renderMotion } from './step-motion.js';
import { renderShare, openShareDialog } from './share.js';
import { renderDetails } from './details.js';
import { nakedFor, KINDS } from './tags.js';
import { Library } from './library.js';
import { autoSounds } from './sounds.js';
import { HIPS, LIMBS, TONGUE, MOUTH, mirrorName } from './bones.js';
import * as K from './facekit.js';
import * as FaceMod from './face.js';
import * as PipeMod from './pipeline.js';
import { spaceQuat, setSpaceQuat, mirrorQuat, spacePos, segSegDist } from './posemath.js';
import { h, icon, toast, modal, confirmBox, choiceBox, choiceBar, contextMenu, fillRange } from './ui.js';
import { openExportDialog, openProjectDialog, openAddSoundDialog, openNameDialog, openTrayDialog } from './dialogs.js';
import { Pipeline, simBody } from './pipeline.js';
import { newLayer, MOTIONS, offsetHips, applyLayer } from './motion.js';
import { ThumbRenderer } from './thumbs.js';
import { showHome, hideHome } from './home.js';
import { ensureGame } from './findgame.js';
import { openHelp, maybeTour } from './tour.js';
import { SoundPlayer, VOICE_SETS, VOICE_FALLBACK, voiceCode, simVoiceCode, soundFitsSim } from './audio.js';
import { openMagicDialog } from './magic.js';
import { recordVideo } from './record.js';

const $ = id => document.getElementById(id);
const UP = new THREE.Vector3(0, 1, 0);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const label = K.label;
const POSABLE = K.BODY;                   // the body channel (the jaw and tongue are face bones now)
const clone = x => JSON.parse(JSON.stringify(x));
// "is a dialog open": a dialog that is closing (fading out) no longer counts
const dialogOpen = () => !!document.querySelector('.backdrop:not(.leaving)');

const STEPS = {
  scene: { title: 'Scene', sub: 'Who is in it and where it happens', render: renderScene, next: 'pose' },
  pose: { title: 'Pose', sub: 'Start from a ready pose, then adjust it', render: renderPose, next: 'motion' },
  motion: { title: 'Motion', sub: 'Make it move - one-click motions or your own keys', render: renderMotion, next: 'body' },
  body: { title: 'Body', sub: 'Erection, holes that open by themselves, physics', render: renderBody, next: 'face' },
  face: { title: 'Face', sub: 'Expressions, blinking and talking', render: renderFace, next: 'sounds' },
  sounds: { title: 'Sounds & moments', short: 'Sounds', sub: 'Voices, claps, cum and effects', render: renderSounds, next: 'details' },
  details: { title: 'Details', sub: 'Name, kind, tags and places WickedWhims shows', render: (app, root) => renderDetails(app, root), next: 'share' },
  share: { title: 'Share', sub: 'Try it in your game, chain animations, export a mod', render: renderShare, next: null },
  library: { title: 'Library', sub: 'Every WickedWhims animation you have: preview, copy poses, import' },
};

const BED_OR_SOFA = /BED|SOFA|LOVESEAT/;
// The Face step's close-up: never nearer to the face than this (the lens shows about 36 cm of height there - the
// whole head with a little room), and the camera never lower than this above the floor.
const FACE_NEAR = 0.58, FACE_FLOOR = 0.06;

class App {
  constructor() {
    this.store = new Store();
    this.vp = new Viewport($('viewport'));
    this.simViews = new Map();
    this.assets = { rig: null, bodies: {} };
    this.playing = false;
    this.speed = 1;
    this.autoKey = localStorageGet('autoKey', true);
    this.clipboard = null;
    this.preview = null;
    this.ghosts = [];
    this.onion = false;
    this.trail = false;
    this.mirrorEdit = false;
    this.step = 'scene';
    this.pipeline = new Pipeline(this);
    this.audio = new SoundPlayer();
    this.altDown = false;          // Alt held: go past a face part's safe range (and Alt+click picks the exact bone)
    this.focus = 'view';           // where the last click was: 'view' | 'timeline' | 'curves' | 'panel'
    this.faceClipboard = null;
    this._progress = 0;
    this.editRev = 0;              // goes up with every change (the Curves view and the loop check cache by it)
    this.playRange = null;         // [a, b]: play only this part (not saved in the project)
    this.keyClip = localStorageGet('keyClip', null);          // copied keys (also across animations)
    this.onionMode = localStorageGet('onionMode', 'keys');    // ghosts: 'keys' | 'frames' | 'partner'
    this.tlView = localStorageGet('tlView', 'keys');           // the timeline shows 'keys' or 'curves'
    // Plug-in points (plan 2.4): features register here; every call is wrapped, so a failing feature never breaks
    // the app. Hooks run in the order they were registered.
    this.hooks = {
      afterApply: [], tick: [], frameSet: [], playing: [], bake: [], beforeBake: [], beforeSave: [], projectLoaded: [],
      simRemoved: [], viewCreated: [], viewsSynced: [], traySimAdded: [], furnitureBuilt: [], selection: [], keys: [], retime: [], fitFloor: [],
      menus: { key: [], lane: [], sound: [], ruler: [] },
      exportChecks: [], soundOpts: [], bodyOverride: [], imported: [],
      sections: { scene: [], pose: [], motion: [], body: [], face: [], sounds: [], details: [], share: [] },
      inspector: [], homeCards: [], commands: [], helpRows: [],
    };
    // the face tools and Blender-habit keys in Help (?) and in the command palette (Ctrl+K)
    this.hooks.helpRows.push(() => [
      ['Shift', 'F', 'Face tool: click a dot on the face, drag the arrows or rings'],
      ['T', null, 'A face or extra part: switch arrows (move) / rings (turn)'],
      ['X', null, 'Symmetry on / off: pose both sides at once'],
      ['Hold Alt while dragging', null, "Go past a face part's safe range"],
      ['Alt + click', null, 'Pick the exact bone (twist and helper bones too)'],
      ['/', null, 'Find a bone (the All bones list)'],
      ['I', null, "Key the selected sim here (like K, Blender's key)"],
      ['Alt', 'R', "Reset the selected part's turn"],
      ['Alt', 'G', 'Put the selected part back in its place'],
      ['Numpad 1 / 3 / 7 / 5', null, 'Front / side / top / free 3D view'],
      ['Numpad .', null, 'Frame the selection'],
    ].map(([a, b, text]) => ({ group: 'Face and every bone', keys: b ? [a, b] : /^[A-Z/]$/.test(a) ? [a] : a, text })));
    this.hooks.commands.push(app => {
      const sim = app.store.sim(), when = () => !!app.store.sim(), id = sim && sim.id;
      const face = sim ? sim.keys.some(k => k.face && Object.keys(k.face).length) : false;
      return [
        { group: 'Tools', id: 'symmetry', label: app.mirrorEdit ? 'Symmetry off' : 'Symmetry on', run: () => app.setMirrorEdit(!app.mirrorEdit), icon: 'mirror', keys: ['X'], sub: 'pose both sides at once', words: 'mirror x-axis both sides' },
        { group: 'Tools', id: 'find-bone', label: 'Find a bone', run: () => setTimeout(() => focusBoneSearch() || toast('Select a sim to see its bones.'), 60), icon: 'search', keys: ['/'], sub: "every bone, like Blender's outliner", words: 'outliner bone list all bones search', when },
        { group: 'Faces', id: 'face-editable-all', label: 'Make every expression editable', run: () => app.bakeFace(id, { all: true }), icon: 'face', sub: 'turn the expressions into face dots', words: 'bake expression face bones', when: () => when() && face },
        { group: 'Faces', id: 'face-copy', label: 'Copy face', run: () => app.copyFace(id), icon: 'copy', words: 'expression clipboard', when },
        { group: 'Faces', id: 'face-paste', label: 'Paste face', run: () => app.pasteFace(id), icon: 'paste', words: 'expression clipboard', when: () => when() && !!app.faceClipboard },
        { group: 'Faces', id: 'face-mirror', label: 'Mirror face', run: () => app.mirrorFace(id), icon: 'mirror', sub: 'left and right swap', words: 'flip expression', when },
        { group: 'Faces', id: 'face-reset', label: 'Reset face here', run: () => app.resetFace(id), icon: 'reset', words: 'clear expression rest', when },
      ];
    });
    // the editing tools (spec_editing 7.11) in the command palette
    this.hooks.commands.push(app => app._editCommands());
    // the selected part over time (spec_editing 8.2): like the keys around it, onto the selected keys, its curves
    this.hooks.inspector.push((app, root, { sim, bone }) => app._partTimeCard(root, sim, bone));
  }

  _partTimeCard(root, sim, bone) {
    if (!sim || !bone || !this.simViews.get(sim.id)?.bone(bone)) return;
    const n = this.timeline.selKeysOf(sim.id).filter(k => !k.faceOnly).length;
    const name = label(bone, sim.frame);
    root.append(h('div', { class: 'section' }, h('div', { class: 'section-title' }, 'Over time', h('span', { class: 'count' }, name)),
      h('div', { class: 'btn-grid' },
        h('button', { class: 'btn small', title: `${name}: the turn it has at the key before`, onclick: () => this.matchPart(sim.id, bone, -1) }, icon('prev'), 'Same as previous key'),
        h('button', { class: 'btn small', title: `${name}: the turn it has at the key after`, onclick: () => this.matchPart(sim.id, bone, 1) }, icon('next'), 'Same as next key'),
        n ? h('button', { class: 'btn small', title: `${name} as it is here, on the ${n} selected key${n > 1 ? 's' : ''}`, onclick: () => this.putPartOnSelectedKeys(sim.id, bone) }, icon('key'), `Put this on ${n} selected key${n > 1 ? 's' : ''}`) : null,
        this.curves ? h('button', { class: 'btn small', title: 'How this part turns over the whole loop (Tab over the timeline)', onclick: () => { this.curves.part = null; this.setTimelineView('curves'); } }, icon('curve'), 'Show its curves') : null)));
  }

  // One part's turn (and place) at the key here, copied from the key before or after (the key is made if needed).
  matchPart(simId, bone, dir) {
    const sim = this.store.sim(simId), v = this.simViews.get(simId);
    if (!sim || !v) return;
    const f = Math.round(this.store.frame), face = K.isFace(bone);
    const has = k => (face ? !!k.faceBones : !k.faceOnly);
    const others = sim.keys.filter(k => k.frame !== f && has(k));
    const nb = dir < 0 ? [...others].reverse().find(k => k.frame < f) : others.find(k => k.frame > f);
    if (!nb) return toast(dir < 0 ? 'There is no key before this one.' : 'There is no key after this one.');
    this.store.checkpoint(dir < 0 ? 'Match previous key' : 'Match next key');
    if (this.playing) this.setPlaying(false);
    let key = sim.keys.find(k => k.frame === f);
    if (!key || (!face && key.faceOnly)) key = this._keyOne(sim, v, f, { face });
    const src = face ? nb.faceBones : nb.pose;
    if (face && !key.faceBones) key.faceBones = { rot: {}, pos: {} };
    const dst = face ? key.faceBones : key.pose;
    dst.rot = dst.rot || {}; dst.pos = dst.pos || {};
    if (src.rot && src.rot[bone]) dst.rot[bone] = src.rot[bone].slice(); else delete dst.rot[bone];
    if (!HIPS.includes(bone)) { if (src.pos && src.pos[bone]) dst.pos[bone] = src.pos[bone].slice(); else delete dst.pos[bone]; }
    this.pipeline.overrides.clear();
    this.keysChanged(); this.afterEdit();
    toast(`${label(bone, sim.frame)} now matches the ${dir < 0 ? 'previous' : 'next'} key.`, 'ok');
  }

  _editCommands() {
    const sel = () => this.timeline && this.timeline.sel.size > 0, sim = () => !!this.store.sim();
    const n = this.timeline ? this.timeline.sel.size : 0;
    const G = 'Keys';
    return [
      { group: G, id: 'keys-select-all', label: 'Select every key', run: () => this.selectAllKeys(), icon: 'key', keys: ['Ctrl', 'A'], sub: 'over the timeline', words: 'select all keyframes dope sheet' },
      { group: G, id: 'keys-copy', label: `Copy ${n > 1 ? n + ' keys' : 'the selected keys'}`, run: () => this.copySelectedKeys(), icon: 'copy', keys: ['Ctrl', 'C'], words: 'copy keyframes clipboard', when: sel },
      { group: G, id: 'keys-paste', label: 'Paste keys at the playhead', run: () => this.pasteKeys(), icon: 'paste', keys: ['Ctrl', 'V'], words: 'paste keyframes clipboard', when: () => !!this.keyClip },
      { group: G, id: 'keys-paste-mirrored', label: 'Paste keys mirrored', run: () => this.pasteKeys({ flipped: true }), icon: 'mirror', keys: ['Ctrl', 'Shift', 'V'], words: 'paste flipped x-flip keyframes', when: () => !!this.keyClip },
      { group: G, id: 'keys-duplicate', label: 'Duplicate keys to the playhead', run: () => this.duplicateSelectedKeys(), icon: 'copy', keys: ['Ctrl', 'D'], words: 'duplicate keyframes', when: sel },
      { group: G, id: 'keys-reverse', label: 'Play the selected keys backwards', run: () => this.reverseSelectedKeys(), icon: 'turn', words: 'reverse keyframes time flip', when: sel },
      { group: G, id: 'keys-mirror', label: 'Mirror the selected keys', run: () => this.mirrorSelectedKeys(), icon: 'mirror', words: 'flip keyframes left right', when: sel },
      { group: G, id: 'keys-smooth', label: 'Smooth the keys', run: () => this.smoothSelection(0.5), icon: 'motion', sub: 'takes out small shakes', words: 'smooth jitter filter butterworth gaussian', when: sim },
      { group: G, id: 'keys-simplify', label: 'Simplify (fewer keys)', run: () => this.simplifySelection(1.5), icon: 'key', sub: 'keeps the motion within 1.5°', words: 'decimate reduce clean keyframes', when: sim },
      { group: G, id: 'keys-cleanup', label: 'Clean up the keys', run: () => this.cleanUpSelection(), icon: 'spark', sub: 'smooth a little, then fewer keys', words: 'clean decimate smooth imported mocap', when: sim },
      { group: G, id: 'inbetween', label: 'In-between key here', run: () => this.insertInBetween(), icon: 'key', keys: ['Shift', 'E'], sub: 'halfway between the keys around it', words: 'breakdown tween breakdowner', when: sim },
      { group: 'Loop', id: 'loop-check', label: 'Loop check', run: () => this.loopMenu(innerWidth / 2 - 150, innerHeight / 2 - 120), icon: 'loop', sub: 'does the end flow back into the start?', words: 'cycle seam seamless', when: sim },
      { group: 'Loop', id: 'loop-start-here', label: 'Start the loop here', run: () => this.startLoopHere(), icon: 'loop', sub: 'the loop begins at the playhead', words: 'cycle offset shift', when: () => !!this.store.project.loop },
      { group: 'Loop', id: 'mirror-animation', label: 'Mirror the whole animation', run: () => this.mirrorAnimation(), icon: 'mirror', sub: 'left and right swap - a new animation', words: 'flip whole x-mirror', when: sim },
      { group: 'View', id: 'view-curves', label: this.tlView === 'curves' ? 'Show the keys' : 'Show the curves', run: () => this.setTimelineView(this.tlView === 'curves' ? 'keys' : 'curves'), icon: 'curve', keys: ['Tab'], sub: 'how the selected part turns over time', words: 'graph editor f-curves fcurve' },
      { group: 'View', id: 'play-range', label: this.playRange ? 'Play the whole loop' : 'Play only the selected part', run: () => this.togglePlayRange(), icon: 'play', keys: ['P'], words: 'preview range loop region' },
      { group: 'View', id: 'ref-add', label: 'Add a reference picture or video', run: () => this.pickReference(), icon: 'image', sub: 'trace real motion', words: 'reference image video rotoscope trace background' },
      { group: 'View', id: 'onion-options', label: 'Ghost options', run: () => this.onionMenu(innerWidth / 2 - 120, innerHeight / 2 - 80), icon: 'ghost', words: 'ghost every 3 frames partner' },
    ];
  }

  // ---------------------------------------------------------------- plug-in points
  // Events on window: 'wa:' + name, detail = {...detail, app}.
  emit(name, detail = {}) {
    try { window.dispatchEvent(new CustomEvent('wa:' + name, { detail: { ...detail, app: this } })); }
    catch (err) { console.error(`wa:${name} listener failed:`, err); }
  }
  on(name, fn) {
    const h = e => { try { fn(e.detail, e); } catch (err) { console.error(`wa:${name} listener failed:`, err); } };
    window.addEventListener('wa:' + name, h);
    return () => window.removeEventListener('wa:' + name, h);
  }
  _hookList(name) {
    let h = this.hooks;
    for (const p of name.split('.')) h = h && h[p];
    return Array.isArray(h) ? h : [];
  }
  // Run every function registered for a hook ('afterApply', 'menus.key', 'sections.pose'...) -> their results.
  runHook(name, ...args) {
    const out = [];
    for (const fn of [...this._hookList(name)]) {
      try {
        const r = fn(...args);
        if (r && typeof r.then === 'function') r.catch(err => console.error(`hook ${name} failed:`, err));
        out.push(r);
      } catch (err) { console.error(`hook ${name} failed:`, err); }
    }
    return out;
  }

  // Feature modules (web/js/features/*.js): each gets install(app) (or its default export), at most 3 s each.
  // A feature that fails logs one error and is skipped. -> [{url, ok, error?}]
  async loadFeatures(urls) {
    const out = [];
    for (const url of urls || []) {
      try {
        const mod = await import(url);
        const fn = mod.install || mod.default;
        if (typeof fn === 'function') await Promise.race([Promise.resolve(fn(this)), sleep(3000)]);
        out.push({ url, ok: true });
      } catch (err) {
        console.error(`The feature ${url} could not start:`, err);
        out.push({ url, ok: false, error: String((err && err.message) || err) });
      }
    }
    return out;
  }

  async _installFeatures(listPromise) {
    let list = null;
    try { list = await listPromise; } catch { list = null; }
    if (!list || typeof list !== 'object') return [];
    const ok = n => typeof n === 'string' && /^[a-z0-9_-]+\.(js|css)$/.test(n.split('/').pop());
    for (const c of (list.css || []).filter(ok)) {
      const href = c.includes('/') ? c : `css/features/${c}`;
      if (!document.querySelector(`link[data-feature="${href}"]`)) document.head.append(h('link', { rel: 'stylesheet', href, 'data-feature': href }));
    }
    return this.loadFeatures((list.js || []).filter(ok).map(n => (n.includes('/') ? n : `./features/${n}`)));
  }

  async init() {
    // the feature list is asked for first, so it is there by the time the app can plug them in
    const featureList = Promise.race([fetch('/api/features').then(r => (r.ok ? r.json() : null)).catch(() => null), sleep(6000).then(() => null)]);
    const steps = 5;
    let done = 0;
    const tick = text => x => { done++; this._progress = done / steps; this._setLoading(text); return x; };
    this._setLoading('Reading the game\'s skeleton and WickedWhims bodies...');
    const readAll = () => Promise.all([
      api.rig('au').then(tick('Bones ready - loading bodies...')),
      api.body('yf').then(tick('Loading bodies...')),
      api.body('ym').then(tick('Loading bodies...')),
      api.body('yf_futa').catch(() => null).then(tick('Loading furniture...')),
      api.furniture().then(tick('Setting up the stage...'))]);
    // where the game is, asked alongside the first reads (no wait when it is found). When the engine can't find
    // The Sims 4, the start waits on "The Sims 4 wasn't found" until it is shown where, then reads again.
    const gameAsk = api.game().catch(() => null);
    let reads = readAll();
    reads.catch(() => {});
    this.gameInfo = await gameAsk;
    if (this.gameInfo && !this.gameInfo.found) {
      this.gameInfo = await ensureGame();
      done = 0;
      this._setLoading('Reading the game\'s skeleton and WickedWhims bodies...');
      reads = readAll();
    }
    const [rig, yf, ym, futa, furniture] = await reads;
    this.assets.rig = rig;
    setRig(rig);
    K.setRig(rig);
    this.assets.bodies = { yf, ym, yf_futa: futa || yf };
    this.furniture = furniture;
    this.interact = new Interaction(this);
    this.timeline = new Timeline($('tl-canvas'), this);
    // the Curves view (Keys | Curves) and reference pictures / videos
    try { if ($('curve-canvas')) this.curves = new CurveView($('curve-canvas'), $('curve-bar'), this); } catch (err) { console.error('The Curves view could not start:', err); }
    try { this.refs = new References(this); } catch (err) { console.error('References could not start:', err); this.refs = null; }
    this.library = new Library(this);
    this.thumbs = new ThumbRenderer(this);
    this.store.on(what => this._onStore(what));
    this._ensureFaceToolButton();
    this._wireUI();
    this.vp.onFrame.push(dt => this._tick(dt));
    // Magic, the Place tool and ready poses on furniture share these helpers (when they are there)
    import('./placing.js').then(m => { this._placing = m; }).catch(() => { this._placing = null; });

    const legacy = localStorageGet('autosave', null);        // read before the blank scene below clears it
    const legacyState = localStorageGet('autosaveState', {});
    this.newScene(false, false, 'empty');               // the app opens on an empty scene: you add your own sims
    this.timeline.fit();
    this.showStep('scene');
    if (this.tlView === 'curves') this.setTimelineView('curves', { quiet: true });
    this.refreshAll();
    api.sounds().then(s => { this.sounds = s; if (this.step === 'sounds') this.renderStep(); }).catch(() => { this.sounds = []; });
    api.tones().then(t => { this.tones = t; if (this.store.sim()) this.refreshPanels(); }).catch(() => {});
    this.loadPosePresets();
    // features plug in, then the splash hands over (it may hold the start for at most 4 s)
    await this._installFeatures(featureList);
    const holds = [];
    this.emit('ready', { hold: p => { if (p && typeof p.then === 'function') holds.push(p); } });
    if (holds.length) await Promise.race([Promise.allSettled(holds), sleep(4000)]);
    showHome(this);
    $('loading').classList.add('done');
    // work that was never saved (the app closed or the PC crashed): offer to bring it back. The recovery file is
    // the main copy; the browser's own storage keeps a second copy in case the file could not be written.
    const fromBrowser = legacy && legacy.sims && legacy.sims.length ? { dirty: true, project: legacy, state: legacyState, written: Date.now() / 1000 } : null;
    if (fromBrowser) { localStorageSet('autosave', legacy); localStorageSet('autosaveState', legacyState); }
    // both kept: whichever copy is newer wins (the file can lag behind when the engine was down or busy)
    const when = x => (x.state && x.state.time) || (x.written || 0) * 1000;
    api.recovery().catch(err => { this._recoveryMissing(err); return null; })
      .then(r => {
        const file = r && r.dirty && r.project && r.project.sims && r.project.sims.length ? r : null;
        if (!file || !fromBrowser) return file || fromBrowser;
        return legacyState && legacyState.time && legacyState.time > when(file) ? fromBrowser : file;
      })
      .then(r => { if (r) this._offerRecovery(r); })
      .finally(() => this._startRecovery());
  }

  // ---------------------------------------------------------------- crash-safe autosave
  // While there are unsaved changes everything is written to a recovery file every few seconds and when the
  // window closes. Saving clears it - a clean close never asks about recovery. A server without the recovery
  // file (an older one still running) is asked once; after that only the browser's own copy is kept.
  _recoveryMissing(err) {
    if (err && err.status === 404 && !this._noRecovery) {
      this._noRecovery = true;
      console.warn('This server has no crash-recovery file yet (restart it to get one) - using the browser\'s copy only.');
    }
  }

  _clearRecovery() {
    localStorageSet('autosave', null);
    if (!this._noRecovery) api.clearRecovery().catch(err => this._recoveryMissing(err));
  }

  _recoveryState() {
    const c = this.vp.camera, t = this.vp.controls.target;
    return { frame: Math.round(this.store.frame), step: this.step, selected: this.store.selected, tool: this.interact.tool,
      camera: { pos: c.position.toArray(), target: t.toArray() }, time: Date.now(), tlView: this.tlView, playRange: this.playRange };
  }

  _startRecovery() {
    this._recoveryRev = null;
    setInterval(() => {
      if (!this.store.dirty || this._recovering) return;
      const rev = JSON.stringify(this.store.project);          // any change at all, even one that keeps the length
      if (rev === this._recoveryRev) return;
      this._recoveryRev = rev;
      const state = this._recoveryState();
      if (!this._noRecovery) api.saveRecovery({ dirty: true, project: this.store.project, state }).catch(err => this._recoveryMissing(err));
      localStorageSet('autosave', this.store.project);
      localStorageSet('autosaveState', state);
    }, 3000);
    const flush = () => {
      if (this._recovering) return;
      const state = this._recoveryState();
      if (!this._noRecovery) {
        const body = this.store.dirty ? JSON.stringify({ dirty: true, project: this.store.project, state }) : '{}';
        navigator.sendBeacon((this.store.dirty ? '/api/recovery' : '/api/recovery_clear') + RECOVERY_SLOT, new Blob([body], { type: 'text/plain' }));
      }
      if (this.store.dirty) { localStorageSet('autosave', this.store.project); localStorageSet('autosaveState', state); }
      else localStorageSet('autosave', null);
    };
    window.addEventListener('pagehide', flush);
    window.addEventListener('beforeunload', flush);
    // The desktop app calls this before it closes: the whole project is written and confirmed before the window
    // goes (a page's last-moment message is limited to 64 KB, and real animations are bigger than that).
    window.wickedFlushSync = () => {
      if (this._recovering) return 'skip';
      const state = this._recoveryState();
      const dirty = this.store.dirty;
      if (dirty) { localStorageSet('autosave', this.store.project); localStorageSet('autosaveState', state); }
      else localStorageSet('autosave', null);
      if (this._noRecovery) return 'local';
      try {
        const x = new XMLHttpRequest();
        x.open('POST', (dirty ? '/api/recovery' : '/api/recovery_clear') + RECOVERY_SLOT, false);   // waits until written
        x.setRequestHeader('Content-Type', 'application/json');
        x.send(dirty ? JSON.stringify({ dirty: true, project: this.store.project, state }) : '{}');
        return x.status;
      } catch { return 'fail'; }
    };
  }

  _offerRecovery(r) {
    const p = r.project;
    const when = new Date(((r.state && r.state.time) || r.written * 1000 || Date.now())).toLocaleString();
    this._recovering = true;
    modal({
      title: 'Some work was not saved',
      text: `"${p.name || 'Untitled animation'}"${p.author ? ' by ' + p.author : ''} was being worked on (${when}) when the app closed without saving.`,
      body: h('div', { class: 'tip' }, icon('spark'), h('div', {}, 'Open puts everything back exactly as it was - the animation, the frame you were on, the step, the selected sim and the camera.')),
      onClose: () => { this._recovering = false; },
      buttons: [
        { label: 'Ignore', kind: 'ghost', onClick: () => this._clearRecovery() },
        { label: 'Open', kind: 'primary', onClick: () => this.restoreRecovery(r) },
      ],
    });
  }

  restoreRecovery(r) {
    const st = r.state || {};
    this.store.load(r.project);
    this.store.setDirty(true);
    this.pipeline.overrides.clear();
    this.shareData = null;
    hideHome(this);
    this.refreshAll();
    this.timeline.fit();
    this.setFrame(st.frame || 0);
    if (st.tool) this.setTool(st.tool);
    if (st.selected && this.store.sim(st.selected.sim)) { this.store.selected = { sim: st.selected.sim, bone: st.selected.bone || null }; this.emitSelection(); }
    const wasFace = this.step === 'face';
    if (st.step && st.step !== 'home') this.showStep(st.step);
    if (this.step === 'face') {
      // the Face step makes its close-up again (the saved camera is that close-up, without its tilt); there is no
      // view from before it to go back to, so leaving the step frames all the sims
      if (wasFace) this.frameFace();
      this._camBeforeFace = null;
    } else if (st.camera) {
      this.vp.stopCamera();
      this.vp.controls.lookFrom(new THREE.Vector3().fromArray(st.camera.pos), new THREE.Vector3().fromArray(st.camera.target));
    }
    if (st.tlView === 'curves' || st.tlView === 'keys') this.setTimelineView(st.tlView, { quiet: true });
    if (Array.isArray(st.playRange) && st.playRange.length === 2 && st.playRange[1] < this.store.project.length) this.setPlayRange(st.playRange, { quiet: true });
    this.pipeline.simulateIfNeeded(true);
    this.applyPoses();
    this._projectLoaded();
    toast(`"${this.store.project.name}" is back where you left it. Save with Ctrl+S to keep it.`, 'ok');
  }

  // Loading text under the spinner, and the splash's progress (wa:loading).
  _setLoading(text) {
    const el = $('loading-text');
    if (el) el.textContent = text;
    this.emit('loading', { progress: this._progress || 0, text });
  }

  // A project was loaded, started or restored: features that keep their own state per project hear about it.
  _projectLoaded() {
    const p = this.store.project;
    this.runHook('projectLoaded', p);
    this.emit('project', { project: p });
  }

  // ---------------------------------------------------------------- scene building
  // template: 'couple' (female + male facing each other), 'solo', 'futa'
  // template: 'empty' (no sims - you add your own; what the app starts with and the Home cards use), 'couple' (the
  // default for code that doesn't say), 'ff', 'mm', 'futa' or 'solo'
  newScene(confirmFirst = true, ask = true, template = 'couple', done = null) {
    const go = () => ask ? openNameDialog(this, (name, author) => build(name, author)) : build(null, null);
    const build = (name, author) => {
      const p = newProject();
      if (name) p.name = name;
      if (author) p.author = author;
      if (template === 'solo') p.sims.push(newSim(p, 'yf'));
      else if (template === 'futa') { p.sims.push(newSim(p, 'yf')); p.sims.push(newSim(p, 'yf_futa')); }
      else if (template === 'mm') { p.sims.push(newSim(p, 'ym')); p.sims.push(newSim(p, 'ym')); }
      else if (template === 'ff') { p.sims.push(newSim(p, 'yf')); p.sims.push(newSim(p, 'yf')); }
      else if (template === 'couple') { p.sims.push(newSim(p, 'yf')); p.sims.push(newSim(p, 'ym')); }
      this.store.load(p);
      this.store.selected.sim = p.sims[0] ? p.sims[0].id : null;
      this.playRange = null;
      this.pipeline.overrides.clear();
      this._lastPreset = null;
      this._file = null;
      this._placeDefault();
      localStorageSet('autosave', null);
      this.showStep('scene');
      this.frameSims({ fromFront: true });
      this.timeline.fit();              // the new loop fills the timeline (its length may differ from the old one)
      this._projectLoaded();
      done && done();
    };
    if (!confirmFirst || !this.store.dirty) return go();
    confirmBox('Start a new animation?', 'Unsaved changes to this one will be lost.', 'Start new', true).then(ok => ok && go());
  }

  _placeDefault() {
    const sims = this.store.project.sims;
    this.syncViews();
    sims.forEach((s, k) => {
      const v = this.simViews.get(s.id);
      if (!v || s.keys.length) return;
      const x = (k - (sims.length - 1) / 2) * 0.9;
      v.resetPose();
      this.interact.moveHips(v, new THREE.Vector3(x, 0, 0));
      if (sims.length > 1) this.interact.turnHips(v, (x <= 0 ? 1 : -1) * Math.PI / 2, new THREE.Vector3(x, 0, 0));
      this._relaxArms(v);
      s.keys.push({ frame: 0, ease: 'auto', pose: this._bodyPose(v) });
    });
    this.store.setDirty(false);
    this.refreshAll();
  }

  // The game's rest pose already stands relaxed with the arms down.
  _relaxArms() {}

  // A sim view's GPU memory (meshes, material and the skeleton's bone texture) is given back.
  disposeView(v) {
    if (!v) return;
    try { v.skeleton && v.skeleton.dispose(); } catch { /* already gone */ }
    v.dispose();
  }

  syncViews() {
    const p = this.store.project;
    const ids = new Set(p.sims.map(s => s.id));
    for (const [id, v] of this.simViews) if (!ids.has(id)) { this.disposeView(v); this.simViews.delete(id); }
    for (const s of p.sims) {
      simBody(s);
      if ('_loading' in s) delete s._loading;          // left in animations saved before (see _loadTray)
      let v = this.simViews.get(s.id);
      // a Tray sim has its own body shape (loaded once, then kept)
      if (s.tray && !this.assets.bodies['tray:' + s.id]) this._loadTray(s);
      let bodyKey = s.tray && this.assets.bodies['tray:' + s.id] ? 'tray:' + s.id : s.frame;
      // a Tray sim wears its own look on the skin (makeup, brows, eye colour, skin details, tattoos)
      let toneKey = (s.tone || '') + (s.tray && s.tray.id ? `~${s.tray.id}:${s.tray.index || 0}` : '');
      // a feature may show another body for a while (trying an animation on other bodies): the first answer wins
      const over = this.runHook('bodyOverride', s).find(x => x && x.bodyKey);
      if (over && this.assets.bodies[over.bodyKey]) { bodyKey = over.bodyKey; if (over.toneKey !== undefined) toneKey = over.toneKey || ''; }
      if (v && (v.frameKey !== bodyKey || v.toneKey !== toneKey)) { this.disposeView(v); this.simViews.delete(s.id); v = null; }
      if (!v) {
        v = new Sim(this.assets.rig, this.assets.bodies[bodyKey] || this.assets.bodies.yf, { color: s.color, skin: s.skin });
        v.frameKey = bodyKey;
        v.toneKey = toneKey;
        this.applySkin(v, s.frame, toneKey);
        this.vp.sims.add(v.group);
        this.simViews.set(s.id, v);
        this.runHook('viewCreated', v, s);
      }
      v.color = s.color;
      v.setSkin(s.skin);
      v.group.visible = s.visible !== false && !this.preview;
    }
    if (this.preview) this.updateGhosts();
    this.buildFurniture();
    this.runHook('viewsSynced');
  }

  // Real skin textures from the game (cached per body and skin tone). skinReady() tells when one has arrived,
  // so pictures (pose thumbnails) are never taken of a still untextured, dark body.
  applySkin(v, frame, tone = '') {
    this._tex = this._tex || new Map();
    this._texReady = this._texReady || new Map();
    const key = frame + '|' + tone;
    let tex = this._tex.get(key);
    if (!tex) {
      let ready;
      this._texReady.set(key, new Promise(res => { ready = res; }));
      tex = new THREE.TextureLoader().load(api.skinUrl(frame, tone),
        () => { for (const [, sv] of this.simViews) sv.material.needsUpdate = true; ready(true); },
        undefined, () => { this._tex.delete(key); v.setTexture(null); ready(false); });
      tex.flipY = false;
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 8;
      this._tex.set(key, tex);
    }
    v.setTexture(this._tex.has(key) ? tex : null);
  }

  skinReady(frame, tone = '') {
    const key = frame + '|' + tone;
    return (this._texReady && this._texReady.get(key)) || Promise.resolve(false);
  }

  // A Tray sim's own body (and with it her hair and look), once per sim. What is loading is kept here, never on the
  // sim itself: the sim is saved (autosave, recovery), and a "loading" left in a saved sim made her come back bald.
  async _loadTray(s) {
    this._trayLoading = this._trayLoading || new Set();
    if (this._trayLoading.has(s.id)) return;
    this._trayLoading.add(s.id);
    try {
      const r = await api.traySim(s.tray.id, s.tray.index);
      this.assets.bodies['tray:' + s.id] = r.body;
      if (!s.tone && r.tone) s.tone = r.tone;
      this.syncViews();
      this.applyPoses();
    } catch (e) { toast(`Could not load ${s.tray.name}'s body: ${e.message}`, 'err'); }
    finally { this._trayLoading.delete(s.id); }
  }

  async addTraySim(trayId, index, name) {
    const r = await api.traySim(trayId, index);
    this.store.checkpoint('Add a Tray sim');
    const p = this.store.project;
    const s = newSim(p, r.frame);
    s.label = (name || '').split(' ')[0].replace(/^./, c => c.toUpperCase()) || s.label;
    s.tray = { id: trayId, index, name };
    s.tone = r.tone || '';
    this.assets.bodies['tray:' + s.id] = r.body;
    p.sims.push(s);
    this.store.selected = { sim: s.id, bone: null };
    this.syncViews();
    const v = this.simViews.get(s.id);
    v.resetPose();
    this.interact.moveHips(v, new THREE.Vector3((p.sims.length - 1) * 0.8 - 0.4, 0, 0));
    s.keys.push({ frame: Math.round(this.store.frame), ease: 'auto', pose: this._bodyPose(v) });
    this.runHook('traySimAdded', s);
    this.refreshAll();
    toast(`${name} is in the scene. Pick a pose for them in step 2.`, 'ok');
    return s;
  }

  setTone(id, tone) { this.store.checkpoint(); this.store.sim(id).tone = tone; this.syncViews(); this.applyPoses(); this.refreshPanels(); }

  buildFurniture() {
    const id = this.store.project.furniture;
    if (this._furnId === id) return;
    this._furnId = id;
    const def = this.furniture.find(f => f.id === id);
    const swap = g => {
      // the simple shapes are thrown away; the real game object's meshes stay cached for next time
      for (const old of [...this.vp.furniture.children]) disposeFurniture(old);
      this.vp.furniture.clear();
      if (g) this.vp.furniture.add(g);
      this.runHook('furnitureBuilt', g, id);
    };
    if (def && def.kind !== 'floor') this._furnitureInfo(id);        // the surface height, for ready poses
    swap(buildFurniture(def));
    // swap in the real game object (exact size) as soon as it has loaded
    loadGameFurniture(def).then(g => {
      if (!g || this._furnId !== id) return;
      swap(g.clone());
    });
  }

  idOf(view) { for (const [id, v] of this.simViews) if (v === view) return id; return null; }
  // "Female 1 · Inner brow (left) · b__L_InBrow__": the plain name and the rig's own name (Blender and the game use it)
  boneLabel(view, idx) {
    const s = this.store.sim(this.idOf(view)), n = view.bones[idx].name;
    return `${s ? s.label + ' · ' : ''}${label(n, s ? s.frame : undefined)} · ${n}`;
  }

  // The surface of the furniture the sims are on (its height; null for the floor or when it can't be read). Cached;
  // _furnInfoKnown keeps the answers that already arrived, so a ready pose can use them at once.
  // One promise per place, shared with placing.furnitureInfo (both keep it in app._furnInfo, same URL).
  _furnitureInfo(id) {
    this._furnInfoKnown = this._furnInfoKnown || new Map();
    if (!id || id === 'floor') return Promise.resolve(null);
    const pl = this._placing;
    if (pl && typeof pl.furnitureInfo === 'function') {
      return Promise.resolve(pl.furnitureInfo(this, id)).then(info => { this._furnInfoKnown.set(id, info || null); return info; }).catch(() => null);
    }
    this._furnInfo = this._furnInfo || new Map();
    if (!this._furnInfo.has(id)) {
      this._furnInfo.set(id, fetch('/api/furniture_mesh?v=4&id=' + encodeURIComponent(id)).then(r => (r.ok ? r.json() : null)).catch(() => null));
    }
    return this._furnInfo.get(id).then(info => { this._furnInfoKnown.set(id, info || null); return info; });
  }

  // ---------------------------------------------------------------- camera
  // Point the camera at all the sims (after a ready pose, opening an animation or starting a new one), so the
  // bodies fill the view instead of standing small at the bottom.
  frameSims({ fromFront = false, fromAbove = false, views = null } = {}) {
    // a fresh view of the whole scene replaces the one saved before the Face step's close-up
    this._camBeforeFace = null;
    const box = new THREE.Box3();
    let n = 0;
    for (const v of views || this.simViews.values()) {
      if (!v.group.visible) continue;
      v.group.updateMatrixWorld(true);
      for (const b of ['b__Head__', 'b__L_Hand__', 'b__R_Hand__', 'b__L_Foot__', 'b__R_Foot__', 'b__Pelvis__']) if (v.bone(b)) { box.expandByPoint(v.worldPos(b)); n++; }
      // the head bone sits at the bottom of the skull: reach on to the top of the head
      if (v.bone('b__Head__') && v.bone('b__Neck__')) {
        const head = v.worldPos('b__Head__'), up = head.clone().sub(v.worldPos('b__Neck__'));
        if (up.lengthSq() > 1e-8) box.expandByPoint(head.add(up.setLength(0.2)));
      }
    }
    if (!n) return;
    const c = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
    const radius = Math.max(0.5, size.length() / 2) * 1.2;
    c.y += radius * 0.06;                 // a little room at the top, under the tool buttons
    const dir = fromFront ? new THREE.Vector3(0.62, 0.42, 0.66) : this.vp.viewDir();
    // fromAbove: the way you look now, but from above (as the 3D view button does) - a close-up that looked up at a
    // face never turns into a view from under the floor or the bed
    if (fromAbove && dir.y < 0.42) {
      const flat = new THREE.Vector3(dir.x, 0, dir.z);
      if (flat.lengthSq() < 1e-6) flat.set(0.62, 0, 0.66);
      flat.normalize().multiplyScalar(Math.sqrt(1 - 0.42 * 0.42));
      dir.set(flat.x, 0.42, flat.z);
    }
    // never below the top of the bed, sofa or table the sims are on (the camera would look up through it)
    const dist = radius * 2.6, low = this._surfaceTop() + 0.3;
    dir.normalize();
    if (low > 0.3 && c.y + dir.y * dist < low) {
      const y = Math.min(0.95, (low - c.y) / dist + 0.02);
      const flat = new THREE.Vector3(dir.x, 0, dir.z);
      if (flat.lengthSq() < 1e-6) flat.set(0.62, 0, 0.66);
      flat.normalize().multiplyScalar(Math.sqrt(1 - y * y));
      dir.set(flat.x, y, flat.z);
    }
    this.vp.frame(c, radius, dir);
  }

  // The top of the furniture the sims are on (0 on the floor; a wall has no top to be on).
  _surfaceTop() {
    const id = this.store.project.furniture;
    if (!id || id === 'floor') return 0;
    const def = (this.furniture || []).find(f => f.id === id);
    if (!def || def.kind === 'wall' || def.kind === 'floor') return 0;
    const fallback = def.size ? def.size[1] : 0;
    const info = this._furnInfoKnown ? this._furnInfoKnown.get(id) : undefined;
    const pl = this._placing;
    try { if (pl && typeof pl.surfaceY === 'function') { const y = pl.surfaceY(info || null, fallback); if (Number.isFinite(y)) return y; } } catch { /* the plain numbers below */ }
    return info && typeof info.surface_height === 'number' ? info.surface_height : fallback;
  }

  // The Face step: fly to the selected sim's face, from the front of the face (whichever way the sim lies).
  // In close poses the partner (or the sim's own arm) can be right in front of the face: then the camera looks
  // from a little to the side or from above instead, where nothing is in the way. When the partner covers the
  // face from every side (a kiss, cowgirl leaning in), the other sims fade to see-through while the Face step is
  // shown. A lying face is shown upright: the camera looks from the chin side, and tilts the picture if needed.
  frameFace() {
    this._fadeOthers(null);
    const sim = this.store.sim(), v = sim && this.simViews.get(sim.id);
    if (!v || !v.group.visible || !v.bone('b__Head__')) return;
    const head = v.bone('b__Head__');
    const rs = this._restSpace(v)[v.index('b__Head__')];
    const q = spaceQuat(v, head), inv = rs.clone().invert();
    const toWorld = d => d.applyQuaternion(v.space.getWorldQuaternion(new THREE.Quaternion())).normalize();
    const fwd = toWorld(new THREE.Vector3(0, 0, 1).applyQuaternion(inv).applyQuaternion(q));    // out of the face
    const up = toWorld(new THREE.Vector3(0, 1, 0).applyQuaternion(inv).applyQuaternion(q));     // top of the head
    v.group.updateMatrixWorld(true);
    const at = v.worldPos('b__Head__').add(fwd.clone().multiplyScalar(0.07)).add(up.clone().multiplyScalar(0.07));
    // the bodies as rough capsules (joint to joint, with a thickness); own: this sim's own arms and body
    const caps = [];
    const LIMB = [['b__Pelvis__', 'b__Spine2__', 0.15], ['b__Spine2__', 'b__Neck__', 0.12], ['b__Neck__', 'b__Head__', 0.07],
      ['b__L_UpperArm__', 'b__L_Forearm__', 0.06], ['b__L_Forearm__', 'b__L_Hand__', 0.05], ['b__R_UpperArm__', 'b__R_Forearm__', 0.06], ['b__R_Forearm__', 'b__R_Hand__', 0.05],
      ['b__L_Thigh__', 'b__L_Calf__', 0.09], ['b__L_Calf__', 'b__L_Foot__', 0.07], ['b__R_Thigh__', 'b__R_Calf__', 0.09], ['b__R_Calf__', 'b__R_Foot__', 0.07]];
    const others = [];
    for (const [id, w] of this.simViews) {
      if (!w.group.visible) continue;
      if (w !== v) others.push(id);
      w.group.updateMatrixWorld(true);
      const own = w === v;
      for (const [a, b, r] of LIMB) {
        if (own && (b === 'b__Head__' || b === 'b__Neck__')) continue;       // the face's own neck: never in front
        if (w.bone(a) && w.bone(b)) caps.push([w.worldPos(a), w.worldPos(b), r, own]);
      }
      // the hands reach on past the wrist bone (a hand on the cheek, arms around the partner's head)
      for (const [fa, hd] of [['b__L_Forearm__', 'b__L_Hand__'], ['b__R_Forearm__', 'b__R_Hand__']]) {
        if (!w.bone(fa) || !w.bone(hd)) continue;
        const wr = w.worldPos(hd), dir = wr.clone().sub(w.worldPos(fa));
        if (dir.lengthSq() > 1e-8) caps.push([wr, wr.clone().add(dir.setLength(0.1)), 0.045, own]);
      }
      if (w.bone('b__Head__') && w.bone('b__Neck__')) {
        const hp = w.worldPos('b__Head__'), top = hp.clone().sub(w.worldPos('b__Neck__')).setLength(0.1).add(hp);
        if (!own) caps.push([hp, top, 0.12, false]);
        else caps.push([hp.clone().sub(fwd.clone().multiplyScalar(0.03)), top.clone().sub(fwd.clone().multiplyScalar(0.03)), 0.075, true]);   // its own skull (seen from behind)
      }
    }
    // how clear the lines from the face to a camera spot are (below 0: something is in the way). Five points
    // spread over the face (middle, both cheeks, brow, chin), so a head right beside it counts too.
    const side0 = fwd.clone().cross(up).normalize();
    const spots = [at, at.clone().addScaledVector(side0, 0.045), at.clone().addScaledVector(side0, -0.045),
      at.clone().addScaledVector(up, 0.05), at.clone().addScaledVector(up, -0.06)];
    const clearance = (pos, ownOnly) => {
      let c = Infinity;
      for (const f of spots) {
        const s0 = f.clone().add(pos.clone().sub(f).setLength(0.1));
        for (const [a, b, r, own] of caps) if (own || !ownOnly) c = Math.min(c, segSegDist(s0, pos, a, b) - r);
      }
      return c;
    };
    // The camera never tilts by itself: what points up on screen is the world's up. So from direction d (face ->
    // camera) the top of the head shows at this angle from straight up (0 upright, ±PI upside down).
    const WY = new THREE.Vector3(0, 1, 0);
    const tiltOf = d => {
      const right = WY.clone().cross(d);                      // the screen's right, seen from d
      if (right.lengthSq() < 1e-6) return Math.PI / 2;        // straight above or below: no clear up
      right.normalize();
      const scrUp = d.clone().cross(right).normalize();
      return Math.atan2(up.dot(right), up.dot(scrUp));
    };
    const side = side0;
    const cands = [];
    // straight at the face first, then turning toward a profile (around the head's own axes), from above the
    // brow or from the chin side - whichever shows the face upright
    for (const yaw of [0, 15, -15, 30, -30, 45, -45, 60, -60, 80, -80, 100, -100]) {
      for (const lift of [0.18, 0, -0.15, -0.3, 0.4, 0.6, -0.5, -0.65]) {
        const r = THREE.MathUtils.degToRad(yaw);
        let d = fwd.clone().multiplyScalar(Math.cos(r)).add(side.clone().multiplyScalar(Math.sin(r))).add(up.clone().multiplyScalar(lift)).normalize();
        // never under the floor: a face close to the floor is seen from a little nearer, from just above the floor -
        // but never nearer than FACE_NEAR, or the brow and chin fall out of the picture. Still under the floor at
        // that distance: the camera goes onto the floor line instead (the same way round, looking up a bit flatter).
        let dist = 0.92;
        if (d.y < 0 && at.y + d.y * dist < FACE_FLOOR) dist = Math.max(FACE_NEAR, (FACE_FLOOR - at.y) / d.y);
        let pos = at.clone().add(d.clone().multiplyScalar(dist));
        if (pos.y < FACE_FLOOR) {
          const flat = new THREE.Vector3(d.x, 0, d.z);
          const dy = FACE_FLOOR - at.y, across = Math.sqrt(Math.max(0, dist * dist - dy * dy));
          if (flat.lengthSq() < 1e-6 || across < 0.05) continue;        // straight below the face: no room at all
          pos = at.clone().add(flat.setLength(across)).setY(FACE_FLOOR);
          d = pos.clone().sub(at).normalize();
        }
        const tilt = tiltOf(d);
        // facing the face matters most; a face upright on screen next (a tilted picture is the last resort)
        cands.push({ pos, d, dist, tilt, lift, front: d.dot(fwd), score: d.dot(fwd) + 0.55 * Math.cos(tilt) });
      }
    }
    if (!cands.length) { this.vp._animateCamera(at.clone().add(new THREE.Vector3(0, 0.92, 0)), at); return; }
    // the best view with nothing in the way that still shows the face (not just a profile)
    const pick = (ownOnly, list = cands) => {
      let best = null;
      for (const c of list) {
        if (c.front < 0.5 || (best && c.score <= best.score)) continue;
        if (clearance(c.pos, ownOnly) > 0.02) best = c;
      }
      return best;
    };
    // a lying head (its top points sideways): from the chest side first, where the face shows upright
    const lying = up.y < 0.35;
    let best = (lying && pick(false, cands.filter(c => c.lift < 0))) || pick(false);
    if (!best) {
      // the partner covers the face from every side: they fade while you work on the face
      this._fadeOthers(others);
      // its own arms can still be in the way: then the view where they cover the least
      if (!(best = pick(true))) {
        const facing = cands.filter(c => c.front >= 0.5);
        for (const c of facing) c.own = clearance(c.pos, true);
        best = facing.length ? facing.reduce((x, y) => (y.own > x.own + 0.01 || (Math.abs(y.own - x.own) <= 0.01 && y.score > x.score) ? y : x))
          : cands.reduce((x, y) => (y.score > x.score ? y : x));
      }
    }
    // a face still turned more than about 25 degrees: tilt the picture so it stands upright
    const roll = Math.abs(best.tilt) > 0.45 ? -best.tilt : 0;
    // seen from close up (a face near the floor), aim a little lower so the mouth and chin are in the picture
    const aim = best.dist && best.dist < 0.6 ? at.clone().addScaledVector(up, -0.035) : at;
    this.vp._animateCamera(best.pos.clone().add(aim).sub(at), aim, roll);
  }

  // See-through sims (the Face step, when they cover the face). ids: the sims to fade; null: all solid again.
  _fadeOthers(ids) {
    const want = new Set(ids || []);
    for (const [id, w] of this.simViews) {
      const fade = want.has(id);
      if (!!w._faded === fade) continue;
      const m = w.material;
      if (fade) w._faded = { transparent: m.transparent, opacity: m.opacity, depthWrite: m.depthWrite };
      const o = fade ? { transparent: true, opacity: 0.15, depthWrite: false } : w._faded;
      m.transparent = o.transparent; m.opacity = o.opacity; m.depthWrite = o.depthWrite;
      m.needsUpdate = true;
      for (const mesh of w.meshes) mesh.castShadow = !fade;   // no shadow over the face either
      if (!fade) w._faded = null;
    }
    this._faceFaded = want.size > 0;
  }

  // ---------------------------------------------------------------- playback
  _tick(dt) {
    const p = this.store.project;
    if (this.preview) { this.library.tickPreview(dt); return; }
    if (this.playing) {
      // the first step after pressing Play also plays the sounds on the frame it started from
      const prev = this._playStart !== undefined ? this._playStart : this.store.frame;
      this._playStart = undefined;
      let f = this.store.frame + dt * p.fps * this.speed;
      const R = this.playRange;
      if (R && R[1] < p.length) {
        // play only a part: from its end straight back to its start (the sounds of both sides of the jump play)
        const a = R[0], end = R[1] + 1, span = Math.max(1, end - a);
        if (f >= end) { const w = a + ((f - end) % span); this._playSounds(prev, end); this._playSounds(a - 1, w); f = w; this._wrapped = true; }
        else if (f < a) { f = a; this._playSounds(a - 1, a); }
        else this._playSounds(prev, f);
        this.store.frame = f;
      } else {
        if (f >= p.length) { if (p.loop) { f %= p.length; this._wrapped = true; } else { f = p.length - 1; this.setPlaying(false); } }
        this.store.frame = f;
        this._playSounds(prev, f);
      }
      $('tl-frame').textContent = Math.floor(f);
      this.timeline.draw();
      if (this.curves && this.curves.shown) this.curves.draw();
      this.refs && this.refs.sync(f, true);
    }
    // posing a sim by hand pauses its motions and physics, so edits never bake them into the keys (the face and the
    // twist helpers stay visible: the engine keeps them out of the keys)
    const a = this.interact.active;
    const editing = !this.playing && a && a.simId ? a.simId : null;
    if (editing !== this.pipeline.editing) {
      this.pipeline.editing = editing;
      const s = editing && this.store.sim(editing);
      $('vp-editing').classList.toggle('hidden', !(s && (s.layers || []).some(l => l.on)));
    }
    if (!this.vp.dragging) this.applyPoses(false);
    this.interact.updateFaceMode();
    this.interact.placeHandles();
    const wrapped = !!this._wrapped;
    this._wrapped = false;
    this.runHook('tick', dt, this.store.frame, { playing: this.playing, wrapped });
  }

  // Sounds whose frame the playhead just passed, panned a little toward where each sim is on screen.
  _playSounds(from, to) {
    if (this.audio.muted || this.speed < 0.5) return;
    const p = this.store.project;
    for (const s of p.sims) {
      const hits = SoundPlayer.crossed(s.sounds, Math.floor(from), Math.floor(to), p.length);
      if (!hits.length) continue;
      let pan = 0;
      const v = this.simViews.get(s.id);
      if (v) { const q = v.worldPos('b__Pelvis__').project(this.vp.camera); pan = Math.max(-0.7, Math.min(0.7, q.x * 0.7)); }
      for (const snd of hits) {
        // features may change how a sound plays (a sim's own voice, a pitch): merged in, in the order they answer
        const opts = { pan, gain: snd.kind === 'voice' ? 1 : 0.9 };
        for (const o of this.runHook('soundOpts', s, snd)) if (o && typeof o === 'object') Object.assign(opts, o);
        this.audio.play(snd.name, opts);
      }
    }
  }

  applyPoses(ghosts = true) {
    const all = this.pipeline.apply(this.store.frame, { physics: true });
    // until the engine sets face keys itself, they are put under what is shown here
    if (!K.engineHasFace(this)) for (const e of all || this.pipeline.entries()) K.overlayFaceKeys(this, e, this.store.frame, { editing: this.pipeline.editing === e.sim.id, useOverrides: !this.playing });
    if (ghosts) this.updateGhosts();
    this.runHook('afterApply', this.store.frame, { playing: this.playing, ghosts });
  }

  // Keys (and pins) only, for posing by hand: the body and the face as the keys have them at this frame.
  _base(e, frame) {
    this.pipeline.base(e, frame);
    if (!K.engineHasFace(this)) K.overlayFaceKeys(this, e, frame, { editing: true });
  }

  // The body pose of a view for a key: the body channel only (face bones go into key.faceBones).
  _bodyPose(v) {
    const pose = v.getPose();
    if (!K.ENGINE_BONES) {
      // until the engine keeps them apart: no face bones in the body, extra bones only where posed
      for (const n of K.FACE_CHANNEL) { delete pose.rot[n]; delete pose.pos[n]; }
      for (const n of K.EXTRA) {
        const b = v.bone(n), r = v.restByName[n];
        if (!b || !r) continue;
        if (b.quaternion.angleTo(r.quat) > 1e-3) pose.rot[n] = b.quaternion.toArray();
        if (b.position.distanceTo(r.pos) > 0.00005) pose.pos[n] = b.position.toArray();
      }
    }
    return pose;
  }

  setFrame(f) {
    const p = this.store.project;
    // paused, the playhead may sit in the room past the loop's end (to look at it, or to key it); playing never does
    const cap = (this.playing ? p.length : roomEnd(p)) - 1;
    const nf = Math.max(0, Math.min(cap, Math.round(f)));
    if (nf !== Math.round(this.store.frame) && this.pipeline.overrides.size) {
      this.pipeline.overrides.clear();
      toast('Unkeyed changes were dropped - turn on Auto key or press K to keep a pose.');
    }
    this.store.frame = nf;
    $('tl-frame').textContent = nf;
    this.applyPoses();
    this.timeline.draw();
    if (this.curves && this.curves.shown) this.curves.draw();
    this.refs && this.refs.sync(nf, false);
    this._syncEaseBox();
    if (['face', 'body'].includes(this.step)) this.renderStep();
    renderInspector(this);
    this.runHook('frameSet', nf);
  }

  setPlaying(on) {
    this.playing = on;
    $('btn-play').innerHTML = `<svg><use href="#i-${on ? 'pause' : 'play'}"/></svg>`;
    if (on) {
      // a pose that was never keyed would play only on its own frame - it is not part of the animation
      if (this.pipeline.overrides.size) {
        this.pipeline.overrides.clear();
        toast('Unkeyed changes were dropped - turn on Auto key or press K to keep a pose.');
      }
      this.vp.gizmo.detach(); this.interact.active = null; this.pipeline.simulateIfNeeded();
      this.audio.ensure();
      this.audio.preload(this.store.project.sims.flatMap(s => (s.sounds || []).map(x => x.name)));
      this._playStart = this.store.frame - 0.001;
      this.updateGhosts();
      this.refs && this.refs.sync(this.store.frame, true);
    }
    if (!on) this.setFrame(this.store.frame);
    this.runHook('playing', on);
  }

  currentKey(sim) { return sim ? sim.keys.find(k => k.frame === Math.round(this.store.frame)) : null; }

  // ---------------------------------------------------------------- editing
  beginEdit(simId) {
    // posing while it plays would key a new frame on every step of the moving playhead: stop first
    if (this.playing) this.setPlaying(false);
    if (this.pipeline.editing === simId) return;
    this.pipeline.editing = simId;
    const all = this.pipeline.entries();
    const e = all.find(x => x.sim.id === simId);
    if (e) this._base(e, this.store.frame);
  }

  // A sim's bones were changed by hand: keep it at this frame (a key, or a pending pose if auto key is off).
  // part: 'body' (key.pose), 'face' (key.faceBones - a face key where there is no key) or 'both'.
  poseEdited(simId, live = true, part = 'body') {
    const sim = this.store.sim(simId), v = this.simViews.get(simId);
    if (!sim || !v) return;
    const frame = Math.round(this.store.frame);
    const doBody = part !== 'face', doFace = part !== 'body';
    const pose = doBody ? this._bodyPose(v) : null;
    const fb = doFace ? K.getFaceBones(v) : null;
    if (!this.autoKey) {
      const ov = this.pipeline.overrides.get(simId);
      const o = ov && ov.frame === frame ? ov : { frame };
      if (pose) { o.pose = pose; delete o.poseSnapshot; }
      if (fb) o.faceBones = fb;
      // a face-only edit keeps the body as it is (a snapshot, so the body never jumps)
      if (!o.pose) { o.pose = this._bodyPose(v); o.poseSnapshot = true; }
      this.pipeline.overrides.set(simId, o);
      this.hud(`${sim.label}: not keyed yet - press K to keep this ${doBody ? 'pose' : 'face'}`);
    } else {
      let key = sim.keys.find(k => k.frame === frame);
      if (!key) {
        // a face edit where there is no key makes a face key, so the body's motion never changes (its snapshot of
        // the body keeps old code that reads key.pose safe)
        key = doBody ? { frame, ease: this._defaultEase(), pose } : { frame, ease: this._defaultEase(), faceOnly: true, pose: this._bodyPose(v) };
        sim.keys.push(key); sortKeys(sim.keys);
        this.timeline.flash(simId, frame, 'add');
        this.emit('keyed', { simId, frame, kind: doBody ? 'add' : 'face' });
      }
      if (doBody) { key.pose = pose; delete key.faceOnly; }
      if (doFace) key.faceBones = fb;
    }
    this.store.dirty = true;
    $('dirty-dot').classList.add('on');
    this._edited();
    this.timeline.draw();
    if (!live) { this.refreshPanels(); this.physicsChanged(); }
  }

  // A key's timing never becomes 'custom' by being the default for new keys (a custom curve belongs to one key).
  _defaultEase() { const e = localStorageGet('ease', 'auto'); return EASE_INFO[e] && e !== 'custom' ? e : 'auto'; }

  // Something in the keys, motions, face or body changed: the Curves view and the loop check look again.
  _edited() {
    this.editRev++;
    this._loopCache = null;
    if (this.curves) { this.curves.invalidate(); if (this.curves.shown) this.curves.draw(); }
  }

  afterEdit() {
    this.store.setDirty(true);
    this._edited();
    this.refreshPanels();
    this.timeline.draw();
    this.physicsChanged();
    this.updateTrail();
  }

  keysChanged() { this._edited(); this.applyPoses(); this.timeline.draw(); this.physicsChanged(); }
  layersChanged(done = true) { this.store.setDirty(true); this._edited(); this.timeline.draw(); if (done) { this.physicsChanged(); this.updateTrail(); } }

  // physics and trails are recomputed a moment after the last change
  physicsChanged() {
    clearTimeout(this._physT);
    this._physT = setTimeout(() => { if (this.pipeline.simulateIfNeeded()) this.applyPoses(false); }, 260);
  }

  // K: keep the pose at this frame. In the Face tool it keys the face (a face key where the body has no key);
  // a pending (unkeyed) face or pose is always included. { body: true } keys the body even in the Face tool.
  _keyOne(sim, v, frame, { face = false } = {}) {
    const ov = this.pipeline.overrides.get(sim.id);
    const pend = ov && ov.frame === frame ? ov : null;
    this._base({ sim, v }, frame);
    const pendPose = pend && pend.pose && !pend.poseSnapshot ? pend.pose : null, pendFace = pend && pend.faceBones;
    let key = sim.keys.find(k => k.frame === frame);
    const made = !key;
    if (face) {
      if (!key) { key = { frame, ease: this._defaultEase(), faceOnly: true, pose: pendPose || this._bodyPose(v) }; sim.keys.push(key); }
      if (pendPose) { key.pose = pendPose; delete key.faceOnly; }
      key.faceBones = pendFace || K.getFaceBones(v);
    } else {
      const pose = pendPose || this._bodyPose(v);
      if (!key) { key = { frame, ease: this._defaultEase(), pose }; sim.keys.push(key); }
      key.pose = pose;
      delete key.faceOnly;
      if (pendFace) key.faceBones = pendFace;
    }
    sortKeys(sim.keys);
    this.pipeline.overrides.delete(sim.id);
    const kind = face && !pendPose ? 'face' : 'add';
    if (made || kind === 'add') this.timeline.flash(sim.id, frame, 'add');
    this.emit('keyed', { simId: sim.id, frame, kind });
    return key;
  }

  keyPose(simId = this.store.selected.sim, { body = false } = {}) {
    const sim = this.store.sim(simId), v = this.simViews.get(simId);
    if (!sim || !v) return toast('Select a sim first.');
    this.store.checkpoint(body || this.interact.tool !== 'face' ? 'Key pose' : 'Face key');
    const frame = Math.round(this.store.frame);
    const face = !body && this.interact.tool === 'face';
    this._keyOne(sim, v, frame, { face });
    this._applyFit(frame);
    this.afterEdit();
    toast(face ? `Face key set for ${sim.label} at ${(frame / 30).toFixed(2)} s.` : `Key set for ${sim.label} at ${(frame / 30).toFixed(2)} s.`, 'ok');
  }

  keyAll() {
    this.store.checkpoint('Key every sim');
    const frame = Math.round(this.store.frame), face = this.interact.tool === 'face';
    for (const s of this.store.project.sims) {
      const v = this.simViews.get(s.id);
      if (v) this._keyOne(s, v, frame, { face });
    }
    this.pipeline.overrides.clear();
    this._applyFit(frame);
    this.afterEdit();
    toast(`${face ? 'Face keys' : 'Keyed every sim'} at ${(frame / 30).toFixed(2)} s.`, 'ok');
  }

  deleteKey(simId = this.store.selected.sim) {
    const sim = this.store.sim(simId);
    const key = this.currentKey(sim);
    if (!key) return toast('No key on this frame for the selected sim.');
    // a sim always keeps one body key (face keys can all go)
    if (!key.faceOnly && sim.keys.filter(k => !k.faceOnly).length === 1) return toast('That is its only key - a sim needs at least one pose.');
    this.store.checkpoint('Delete key');
    sim.keys.splice(sim.keys.indexOf(key), 1);
    this.timeline.flash(sim.id, key.frame, 'del');
    this.emit('keyed', { simId: sim.id, frame: key.frame, kind: 'del' });
    this.keysChanged();
    this._applyFit();
    this.afterEdit();
  }

  jumpKey(dir) {
    const sim = this.store.sim();
    const frames = [...new Set((sim ? sim.keys : this.store.project.sims.flatMap(s => s.keys)).map(k => k.frame))].sort((a, b) => a - b);
    if (!frames.length) return;
    const f = Math.round(this.store.frame);
    const next = dir > 0 ? frames.find(x => x > f) : [...frames].reverse().find(x => x < f);
    this.setFrame(next !== undefined ? next : (dir > 0 ? frames[0] : frames[frames.length - 1]));
  }

  // curve: a custom timing [x1, y1, x2, y2]; picking 'custom' without one starts from the key's current timing.
  setEase(simId, frame, ease, curve = null) {
    const sim = this.store.sim(simId), key = sim && sim.keys.find(k => k.frame === frame);
    if (!key) return;
    this.store.checkpoint('Change timing');
    this._setKeyEase(key, ease, curve);
    if (ease !== 'custom') localStorageSet('ease', ease);
    this.keysChanged();
    this.afterEdit();
  }
  _setKeyEase(key, ease, curve = null) {
    const old = key.ease || 'auto';
    key.ease = ease;
    if (ease === 'custom') key.curve = validCurve(curve) ? curve.slice() : validCurve(key.curve) && old === 'custom' ? key.curve : (EASE_CURVE[old] || EASE_CURVE.smooth).slice();
    else delete key.curve;
  }

  _syncEaseBox() {
    const key = this.currentKey(this.store.sim());
    const sel = $('ease-select');
    if (sel) { sel.value = key ? (key.ease || 'auto') : this._defaultEase(); sel.disabled = false; }
  }

  // In-between: blend the pose between the keys around this frame (Blender's breakdowner). Face keys don't count.
  tween(simId, t, done) {
    const sim = this.store.sim(simId), f = Math.round(this.store.frame);
    const body = sim.keys.filter(k => !k.faceOnly);
    const prev = [...body].reverse().find(k => k.frame < f), next = body.find(k => k.frame > f);
    if (!prev || !next) return;
    const pose = blendPoses(prev.pose, next.pose, t);
    let key = sim.keys.find(k => k.frame === f);
    if (!key) { key = { frame: f, ease: prev.ease || 'auto', pose }; if (prev.ease === 'custom' && validCurve(prev.curve)) key.curve = prev.curve.slice(); sim.keys.push(key); sortKeys(sim.keys); }
    else { key.pose = pose; delete key.faceOnly; }
    key.type = 'breakdown';                       // an in-between key (drawn smaller)
    this._edited();
    this.applyPoses(false);
    this.timeline.draw();
    if (done) this.afterEdit();
  }

  // A copy of a key for another frame (the face channel comes along).
  _copyKey(key, frame) {
    const k = { frame, ease: key.ease, pose: clone(key.pose) };
    if (key.ease === 'custom' && validCurve(key.curve)) k.curve = key.curve.slice();
    if (key.type === 'breakdown') k.type = 'breakdown';
    if (key.face) k.face = { ...key.face };
    if (key.faceBones) k.faceBones = clone(key.faceBones);
    if (key.faceOnly) k.faceOnly = true;
    return k;
  }

  _menu(x, y, items, hook, ctx) {
    const extra = [];
    this.runHook(hook, extra, ctx);
    const all = extra.length ? [...items, '-', ...extra.filter(it => it && (it === '-' || it.heading || typeof it.onClick === 'function'))] : items;
    if (all.length) contextMenu(x, y, all);
  }

  // Every timing with its colour dot, in EASE_INFO order; "Custom curve..." opens the timing editor.
  _easeItems(current, onPick, onCustom) {
    return Object.entries(EASE_INFO).map(([k, [t, , c]]) => (k === 'custom'
      ? { label: 'Custom curve…', dot: c, checked: current === 'custom', onClick: onCustom }
      : { label: t, dot: c, checked: current === k, onClick: () => onPick(k) }));
  }

  // The timing editor for the segment that starts at this key (a small popover with the curve and two handles).
  timingEditor(simId, frame, x = innerWidth / 2 - 110, y = innerHeight / 2 - 150) {
    const sim = this.store.sim(simId), key = sim && sim.keys.find(k => k.frame === frame);
    if (!key) return;
    try { openTimingEditor(this, sim, key, x, y); } catch (err) { console.error(err); toast('The timing editor could not open.', 'err'); }
  }

  keyMenu(x, y, sim, key) {
    const setEase = ease => this.setEase(sim.id, key.frame, ease);
    const eases = this._easeItems(key.ease || 'auto', setEase, () => this.timingEditor(sim.id, key.frame, x, y));
    const del = () => {
      if (!key.faceOnly && sim.keys.filter(k => !k.faceOnly).length < 2) return toast('A sim needs at least one key.');
      this.store.checkpoint(key.faceOnly ? 'Delete face key' : 'Delete key'); sim.keys.splice(sim.keys.indexOf(key), 1);
      this.timeline.flash(sim.id, key.frame, 'del');
      this.emit('keyed', { simId: sim.id, frame: key.frame, kind: 'del' });
      this.keysChanged(); this._applyFit(); this.afterEdit();
    };
    const copyFace = () => {
      this.faceClipboard = { face: key.face ? { ...key.face } : null, faceBones: key.faceBones ? clone(key.faceBones) : null };
      toast('Face copied.'); this.refreshPanels();
    };
    const ctx = { sim, key, frame: key.frame };
    if (key.faceOnly) {
      this._menu(x, y, [
        { label: 'Delete face key', danger: true, icon: 'trash', onClick: del },
        { label: 'Copy face', icon: 'copy', onClick: copyFace },
        '-',
        { heading: 'Into the next face key' },
        ...eases,
      ], 'menus.key', ctx);
      return;
    }
    const dup = f => {
      this.store.checkpoint('Duplicate key');
      sim.keys = sim.keys.filter(k => k.frame !== f);
      sim.keys.push(this._copyKey(key, f)); sortKeys(sim.keys);
      this.timeline.flash(sim.id, f, 'add');
      this.keysChanged(); this._applyFit(f); this.afterEdit();
    };
    const id = KO.kid(sim.id, key.frame);
    const holdLabel = { 0.25: 'Hold ¼ s', 0.5: 'Hold ½ s', 1: 'Hold 1 s' };
    this._menu(x, y, [
      { heading: 'Into the next key' },
      ...eases,
      '-',
      { label: 'Copy key', icon: 'copy', onClick: () => { this.timeline.selectOnly([id]); this.copySelectedKeys(); } },
      { label: 'Copy pose', icon: 'copy', onClick: () => { this.clipboard = clone(key.pose); toast('Pose copied.'); this.refreshPanels(); } },
      (key.face || key.faceBones) ? { label: 'Copy face', icon: 'copy', onClick: copyFace } : null,
      { label: 'Duplicate to the playhead', icon: 'key', onClick: () => dup(Math.round(this.store.frame)) },
      ...[0.25, 0.5, 1].map(sec => ({ label: holdLabel[sec], icon: 'pause', onClick: () => this.holdPose(sim.id, key.frame, sec) })),
      { label: 'Save as a pose…', icon: 'save', onClick: () => this.saveMyPose(sim.id, { pose: key.pose, faceBones: key.faceBones }) },
      key.type === 'breakdown'
        ? { label: 'Make it a main key', icon: 'key', onClick: () => this.setKeyType(null, [id]) }
        : { label: 'Make it an in-between key', icon: 'key', onClick: () => this.setKeyType('breakdown', [id]) },
      !this.store.project.loop ? { label: 'Make the end match the start', icon: 'loop', onClick: () => this.makeEndMatchStart([sim.id]) } : null,
      '-',
      { label: 'Delete key', danger: true, icon: 'trash', onClick: del },
    ].filter(Boolean), 'menus.key', ctx);
  }

  laneMenu(x, y, sim, frame) {
    const p = this.store.project;
    const nb = KO.neighbours(p, sim, frame);
    const between = nb.prev && nb.next && !sim.keys.some(k => k.frame === frame && !k.faceOnly);
    this._menu(x, y, [
      { label: `Key ${sim.label} here`, icon: 'key', onClick: () => { this.selectSim(sim.id); this.setFrame(frame); this.keyPose(sim.id); } },
      between ? { label: 'In-between key here', icon: 'key', onClick: () => { this.selectSim(sim.id); this.setFrame(frame); this.insertInBetween([sim.id]); } } : null,
      this.keyClip ? { label: 'Paste keys here', icon: 'paste', onClick: () => { this.selectSim(sim.id); this.setFrame(frame); this.pasteKeys({ target: sim.id }); } } : null,
      { label: 'Paste pose here', icon: 'paste', onClick: () => { if (!this.clipboard) return toast('Copy a pose first.'); this.selectSim(sim.id); this.setFrame(frame); this.pastePose(sim.id); } },
      { label: 'Add a sound here', icon: 'sound', onClick: () => { this.setFrame(frame); this.addSoundDialog(sim.id); } },
      '-',
      { label: `Select all of ${sim.label}'s keys`, icon: 'select', onClick: () => this.timeline.selectAll([sim.id]) },
      p.loop ? { label: `Move ${sim.label}'s whole animation 1 frame later`, icon: 'next', onClick: () => this.shiftSim(sim.id, 1) } : null,
      p.loop ? { label: `Move ${sim.label}'s whole animation 1 frame earlier`, icon: 'prev', onClick: () => this.shiftSim(sim.id, -1) } : null,
    ].filter(Boolean), 'menus.lane', { sim, frame });
  }

  soundMenu(x, y, sim, snd) {
    this._menu(x, y, [
      { heading: snd.name },
      { label: 'Remove sound', danger: true, icon: 'trash', onClick: () => this.removeSound(sim.id, snd) },
    ], 'menus.sound', { sim, snd });
  }

  // Right-click on the ruler: the keys here, the play range and the loop.
  rulerMenu(x, y, frame) {
    const p = this.store.project;
    const later = [...new Set(p.sims.flatMap(s => s.keys.map(k => k.frame)))].filter(f => f > frame).sort((a, b) => a - b);
    const next = later.length ? later[0] : p.length - 1;
    this._menu(x, y, [
      { label: `Select every key at frame ${frame}`, icon: 'select', onClick: () => { this.timeline.selectColumn(frame); this.setFrame(frame); } },
      next > frame ? { label: 'Play only from here to the next key', icon: 'play', onClick: () => this.setPlayRange([frame, next]) } : null,
      this.playRange ? { label: 'Play the whole loop', icon: 'loop', onClick: () => this.setPlayRange(null) } : null,
      p.loop ? { label: 'Start the loop here', icon: 'loop', onClick: () => this.startLoopHere(frame) } : null,
      { label: 'Loop check…', icon: 'check', onClick: () => this.loopMenu(x, y) },
    ].filter(Boolean), 'menus.ruler', { frame });
  }

  // ---------------------------------------------------------------- key selection (spec_editing 7.2)
  // The timeline's selection changed: the inspector's selection card follows (at most once per frame).
  selectionChanged() {
    // keys picked: a moment picked before is let go (Delete then deletes the keys, not the moment)
    if (this.timeline && this.timeline.sel.size && this.selectedEvent && [...this.timeline.sel].some(id => id[0] === 'k' || id[0] === 's')) { this.selectedEvent = null; this.timeline.draw(); }
    if (this._selRaf) return;
    this._selRaf = requestAnimationFrame(() => {
      this._selRaf = 0;
      renderInspector(this);
      if (this.curves && this.curves.shown) this.curves.draw();
    });
  }
  _selInfo() {
    const r = KO.readSel(this.store.project, this.timeline.sel);
    return { ...r, count: r.keys.length, simsN: r.sims.size };
  }
  _needSel() {
    if (this.timeline.sel.size) return true;
    toast('Select some keys first: click a key, Ctrl+click for more, or Ctrl+drag a box on the timeline.');
    return false;
  }
  // One command on the selection: stop playing, one undo step, the change, then everything shows it.
  _selOp(label, fn) {
    if (!this._needSel()) return null;
    if (this.playing) this.setPlaying(false);
    this.store.checkpoint(label);
    const r = fn(this.store.project, this.timeline.sel);
    this.pipeline.overrides.clear();
    if (r && r.sel) this.timeline.sel = r.sel;
    this.timeline.pruneSel();
    this.keysChanged();
    this.afterEdit();
    if (r && r.sel) this.timeline.pop([...r.sel]);
    this.selectionChanged();
    return r;
  }
  _plural(n, word) { return `${n} ${word}${n === 1 ? '' : 's'}`; }

  selectAllKeys() {
    this.timeline.selectAll();
    toast(`${this._plural(this.timeline.sel.size, 'key')} selected - drag one to move them all, or right-click for more.`);
  }
  clearKeySelection() { this.timeline.clearSel(); }

  nudgeKeys(df) {
    const r = this.timeline.selRange();
    if (!r) return this._needSel();
    const L = this.store.project.length;
    if ((df > 0 && r.max >= L - 1) || (df < 0 && r.min <= 0)) { toast(df > 0 ? 'The keys are at the end of the loop.' : 'The keys are at the start of the loop.'); return; }
    const rep = this._selOp('Move keys', (p, sel) => KO.moveSel(p, sel, df));
    this._applyFit();
    if (rep && rep.replaced.length) toast(`${this._plural(rep.replaced.length, 'key')} replaced - Ctrl+Z brings ${rep.replaced.length > 1 ? 'them' : 'it'} back.`);
  }

  deleteSelectedKeys() {
    const info = this._selInfo();
    const n = info.count + info.sounds.length + info.events.length;
    if (!n) return this.deleteKey();
    const gone = info.keys.map(x => [x.sim.id, x.key.frame]);
    const rep = this._selOp(`Delete ${this._plural(n, info.count ? 'key' : 'item')}`, (p, sel) => KO.deleteSel(p, sel));
    if (!rep) return;
    this._applyFit();
    for (const [id, f] of gone.slice(0, 40)) if (!this.store.sim(id)?.keys.some(k => k.frame === f)) this.timeline.flash(id, f, 'del');
    this.timeline.clearSel();
    const parts = [];
    if (rep.deleted) parts.push(this._plural(rep.deleted, 'key'));
    if (rep.sounds) parts.push(this._plural(rep.sounds, 'sound'));
    if (rep.events) parts.push(this._plural(rep.events, 'moment'));
    toast(`Deleted ${parts.join(', ') || 'nothing'}.${rep.kept.length ? ` Kept one key for ${rep.kept.join(', ')} - a sim needs a pose.` : ''}`, 'ok');
  }

  reverseSelectedKeys() {
    if (this._selOp('Reverse keys', (p, sel) => KO.reverseSel(p, sel))) toast('Played backwards.', 'ok');
  }

  setEaseForSelection(ease, curve = null) {
    const info = this._selInfo();
    if (!info.count) return this._needSel();
    this._selOp('Change timing', () => { for (const { key } of info.keys) this._setKeyEase(key, ease, curve); return null; });
    if (ease !== 'custom') localStorageSet('ease', ease);
    toast(`${EASE_INFO[ease] ? EASE_INFO[ease][0] : 'Timing'} on ${this._plural(info.count, 'key')}.`, 'ok');
  }

  // Each selected key mirrored left <-> right where it is (it keeps its place and the way it faces).
  mirrorSelectedKeys() {
    const info = this._selInfo();
    if (!info.count) return this._needSel();
    const rig = this.assets.rig;
    this._selOp('Mirror keys', () => {
      for (const { sim, key } of info.keys) {
        const m = KO.mirrorKeyInPlace(key, rig);
        const i = sim.keys.indexOf(key);
        if (i >= 0) sim.keys[i] = m;
      }
      return null;
    });
    toast(`Mirrored ${this._plural(info.count, 'key')}.`, 'ok');
  }

  // type: 'breakdown' (an in-between key) or null (a main key). ids: key ids (default: the selection)
  setKeyType(type, ids = null) {
    const sel = ids ? new Set(ids) : this.timeline.sel;
    const r = KO.readSel(this.store.project, sel);
    if (!r.keys.length) return this._needSel();
    this.store.checkpoint(type ? 'In-between key' : 'Main key');
    for (const { key } of r.keys) { if (type === 'breakdown') key.type = 'breakdown'; else delete key.type; }
    this.keysChanged(); this.afterEdit();
    toast(type ? `${this._plural(r.keys.length, 'key')} made in-between keys (drawn smaller).` : `${this._plural(r.keys.length, 'key')} made main keys.`);
  }

  // The keys the smooth / simplify tools work on: the selected keys, or every key of the selected sim.
  _toolScope() {
    const info = this._selInfo();
    if (info.count) {
      const bySim = new Map();
      for (const { sim, key } of info.keys) { if (!bySim.has(sim)) bySim.set(sim, new Set()); bySim.get(sim).add(key.frame); }
      return [...bySim.entries()].map(([sim, frames]) => ({ sim, frames }));
    }
    const s = this.store.sim();
    return s ? [{ sim: s, frames: null }] : [];
  }

  // Smooth: small shakes between keys are taken out. bones: null = the whole body, or a Set (one part)
  smoothSelection(strength = 0.5, bones = null, { label = 'Smooth', quiet = false } = {}) {
    const scope = this._toolScope();
    if (!scope.length) return toast('Select a sim first.');
    const p = this.store.project;
    this.store.checkpoint(label);
    let n = 0;
    for (const { sim, frames } of scope) n += KO.smoothKeys(sim.keys, { frames, bones, strength, length: p.length, loop: p.loop }).changed;
    this.pipeline.overrides.clear();
    this.keysChanged(); this.afterEdit();
    if (!quiet) toast(n ? `Smoothed ${this._plural(n, 'key')}.` : 'Nothing to smooth - it needs at least 3 keys.', n ? 'ok' : '');
    return n;
  }
  // The Smooth slider: live while dragging, one undo step. phase: 'start' | 'input' | 'end'
  smoothLive(phase, strength = 0.5, bones = null) {
    const p = this.store.project;
    if (phase === 'start' || !this._smoothSnap) {
      const scope = this._toolScope();
      if (!scope.length) return;
      this.store.checkpoint('Smooth');
      this._smoothSnap = scope.map(({ sim, frames }) => ({ id: sim.id, frames, keys: clone(sim.keys) }));
      if (phase === 'start') return;
    }
    let n = 0;
    for (const x of this._smoothSnap) {
      const sim = this.store.sim(x.id);
      if (!sim) continue;
      sim.keys = clone(x.keys);
      n += KO.smoothKeys(sim.keys, { frames: x.frames, bones, strength, length: p.length, loop: p.loop }).changed;
    }
    this.pipeline.overrides.clear();
    this._edited();
    this.applyPoses(false);
    this.timeline.draw();
    if (phase === 'end') {
      this._smoothSnap = null;
      this.afterEdit();
      toast(n ? `Smoothed ${this._plural(n, 'key')}.` : 'Nothing to smooth - it needs at least 3 keys.', n ? 'ok' : '');
    }
  }

  // Simplify (fewer keys): keys go wherever the motion stays within `tol` degrees of what it was.
  simplifySelection(tol = 1.5, { label = 'Simplify', quiet = false } = {}) {
    const scope = this._toolScope();
    if (!scope.length) return toast('Select a sim first.');
    const p = this.store.project;
    if (!quiet) this.store.checkpoint(label);
    let before = 0, after = 0, maxDeg = 0;
    for (const { sim, frames } of scope) {
      const body = sim.keys.filter(k => !k.faceOnly);
      const protect = new Set(frames ? body.filter(k => !frames.has(k.frame)).map(k => k.frame) : []);
      const r = KO.simplifyKeys(sim.keys, { tolDeg: tol, length: p.length, loop: p.loop, curve: p.autoCurve || 'legacy', protect });
      before += body.length; after += r.keys.filter(k => !k.faceOnly).length;
      maxDeg = Math.max(maxDeg, r.maxDeg);
      sim.keys = r.keys;
    }
    this.timeline.pruneSel();
    this.pipeline.overrides.clear();
    this.keysChanged(); this._applyFit(); this.afterEdit();
    const msg = before === after ? `Nothing to take out - every key is needed for this motion (within ${tol}°).`
      : `${before} keys → ${after} keys. It moves at most ${maxDeg.toFixed(1)}° from before.`;
    if (!quiet) toast(msg, before === after ? '' : 'ok');
    return { before, after, maxDeg, msg };
  }

  // Clean up = Smooth 35% then Simplify 1.5°, as one undo step.
  cleanUpSelection() {
    const scope = this._toolScope();
    if (!scope.length) return toast('Select a sim first.');
    this.store.checkpoint('Clean up');
    const p = this.store.project;
    for (const { sim, frames } of scope) KO.smoothKeys(sim.keys, { frames, strength: 0.35, length: p.length, loop: p.loop });
    const r = this.simplifySelection(1.5, { quiet: true });
    toast(`Cleaned up: ${r.msg}`, 'ok');
  }

  // "Put this on selected keys": one part (a bone, or 'upper' / 'hands'...) of the pose here goes onto the selected keys.
  putPartOnSelectedKeys(simId, part) {
    const sim = this.store.sim(simId), v = this.simViews.get(simId);
    if (!sim || !v) return;
    const keys = this.timeline.selKeysOf(simId).filter(k => !k.faceOnly);
    if (!keys.length) return toast(`Select some of ${sim.label}'s keys first.`);
    this._base({ sim, v }, this.store.frame);
    const src = this._bodyPose(v);
    const name = KO.PART_LABEL[part] || label(part, sim.frame);
    this.store.checkpoint(`Copy ${name} to ${this._plural(keys.length, 'key')}`);
    const n = KO.putPart(keys, src, part);
    this.pipeline.overrides.clear();
    this.keysChanged(); this.afterEdit();
    toast(`${name} copied to ${this._plural(n, 'key')}.`, 'ok');
  }

  // ---------------------------------------------------------------- copy / paste keys (spec_editing 7.3)
  copySelectedKeys() {
    if (!this._needSel()) return;
    const clip = KO.copySel(this.store.project, this.timeline.sel);
    if (!clip.count && !clip.sounds) return toast('Select some keys first.');
    this.keyClip = clip;
    try { if (JSON.stringify(clip).length < 4e6) localStorageSet('keyClip', clip); else localStorageRemove('keyClip'); } catch { /* the in-memory copy stays */ }
    toast(`Copied ${this._plural(clip.count, 'key')}${clip.sounds ? ` and ${this._plural(clip.sounds, 'sound')}` : ''} from ${this._plural(clip.rows.length, 'sim')}. Ctrl+V pastes them at the playhead - also in another animation.`, 'ok');
    this.refreshPanels();
  }

  // Which sim each copied row goes to: one row -> the selected sim (or `target`); several rows -> the same sims when
  // it is the same animation, else the project's sims in order (same body first).
  _pasteTargets(clip, target = null) {
    const p = this.store.project, map = new Map(), rows = clip.rows || [];
    if (rows.length === 1) {
      const s = this.store.sim(target || this.store.selected.sim) || p.sims[0];
      if (s) map.set(0, s);
      return map;
    }
    const used = new Set();
    rows.forEach((row, i) => {
      if (clip.projectUid === p.uid) { const s = p.sims.find(x => x.id === row.simId); if (s && !used.has(s.id)) { map.set(i, s); used.add(s.id); } }
    });
    rows.forEach((row, i) => {
      if (map.has(i)) return;
      const s = p.sims.find(x => !used.has(x.id) && x.frame === row.frame) || p.sims.find(x => !used.has(x.id));
      if (s) { map.set(i, s); used.add(s.id); }
    });
    return map;
  }

  pasteKeys({ flipped = false, at = null, target = null, label: lbl = null } = {}) {
    const clip = this.keyClip;
    if (!clip || !(clip.rows || []).length) return toast('Copy some keys first (select them, then Ctrl+C).');
    const p = this.store.project, rig = this.assets.rig;
    if (this.playing) this.setPlaying(false);
    const frame = at !== null ? at : Math.round(this.store.frame);
    const targets = this._pasteTargets(clip, target);
    const lost = (clip.rows || []).length - targets.size;
    // a copy of the clip, placed for where it goes
    const work = clone(clip);
    work.rows.forEach((row, i) => {
      const sim = targets.get(i);
      if (!sim) return;
      if (flipped) row.keys = row.keys.map(k => KO.mirrorKey(k, rig));
      const elsewhere = clip.projectUid !== p.uid || row.simId !== sim.id;
      const first = row.keys.find(k => k.pose && !k.faceOnly) || row.keys[0];
      if ((elsewhere || flipped) && first && first.pose) {
        // at the first pasted key the sim's hips stand where they are now, facing the same way
        const now = evaluate(sim.keys, frame, p.length, p.loop, p.autoCurve);
        if (now) {
          const p0 = KO.hipsOf(now, rig), p1 = KO.hipsOf(first.pose, rig);
          const turn = KO.facingOf(now, rig) - KO.facingOf(first.pose, rig);
          KO.placePoses(row.keys.map(k => k.pose), rig, { move: p0.clone().sub(p1), turn, pivot: p0 });
        }
      }
    });
    this.store.checkpoint(lbl || (flipped ? 'Paste mirrored' : 'Paste keys'));
    const rep = KO.pasteClip(p, work, frame, { targets });
    this.pipeline.overrides.clear();
    this.timeline.sel = rep.sel;
    this.keysChanged(); this._applyFit(); this.afterEdit();
    this.timeline.pop([...rep.sel]);
    this.selectionChanged();
    const secs = (frame / (p.fps || 30)).toFixed(2);
    toast(`Pasted ${this._plural(rep.pasted, 'key')}${flipped ? ' mirrored' : ''} at ${secs} s.${rep.dropped ? ` ${rep.dropped} didn't fit before the end.` : ''}${lost > 0 ? ` ${this._plural(lost, 'sim')} in the copied keys had no sim to go to.` : ''}`, 'ok');
    return rep;
  }

  duplicateSelectedKeys() {
    if (!this._needSel()) return;
    const clip = KO.copySel(this.store.project, this.timeline.sel);
    if (!clip.count && !clip.sounds) return;
    const keep = this.keyClip;
    this.keyClip = clip;
    try { this.pasteKeys({ label: 'Duplicate keys' }); } finally { this.keyClip = keep; }
  }

  // ---------------------------------------------------------------- in-between, exaggerate, holds (spec_editing 7.4)
  // An in-between key at the playhead (halfway, or t) for these sims.
  insertInBetween(simIds = null, t = 0.5) {
    const p = this.store.project, f = Math.round(this.store.frame);
    const ids = (simIds || [this.store.selected.sim]).filter(Boolean);
    const ok = ids.map(id => this.store.sim(id)).filter(s => { if (!s) return false; const nb = KO.neighbours(p, s, f, { exclude: s.keys.find(k => k.frame === f) }); return nb.prev && nb.next; });
    if (!ok.length) return toast('An in-between key needs a key before and after the playhead.');
    if (this.playing) this.setPlaying(false);
    this.store.checkpoint('In-between key');
    for (const s of ok) { KO.inBetween(p, s, f, t); this.timeline.flash(s.id, f, 'add'); this.emit('keyed', { simId: s.id, frame: f, kind: 'add' }); }
    this.pipeline.overrides.clear();
    this.keysChanged(); this._applyFit(); this.afterEdit();
    toast(`In-between key at ${(f / (p.fps || 30)).toFixed(2)} s${ok.length > 1 ? ` for ${this._plural(ok.length, 'sim')}` : ''} - ${Math.round(t * 100)}% of the way to the next key.`, 'ok');
  }

  // Soften (-) or exaggerate (+) the selected keys, or the key here. Live like the in-between slider: the first call
  // makes the undo step; done ends it.
  pushKeys(amount, done = true) {
    const p = this.store.project;
    if (!this._push) {
      let list = this._selInfo().keys.filter(x => !x.key.faceOnly);
      if (!list.length) { const s = this.store.sim(), k = this.currentKey(s); if (k && !k.faceOnly) list = [{ sim: s, key: k }]; }
      if (!list.length) return toast('Select a key first.');
      this.store.checkpoint(amount >= 0 ? 'Exaggerate' : 'Soften');
      this._push = list.map(({ sim, key }) => ({ id: sim.id, frame: key.frame, pose: clone(key.pose), face: key.face ? { ...key.face } : null }));
    }
    for (const x of this._push) {
      const sim = this.store.sim(x.id), key = sim && sim.keys.find(k => k.frame === x.frame);
      if (!key) continue;
      key.pose = clone(x.pose);
      if (x.face) key.face = { ...x.face };
      KO.pushKey(p, sim, key, amount);
    }
    this._edited();
    this.pipeline.overrides.clear();
    this.applyPoses(false);
    this.timeline.draw();
    if (done) { this._push = null; this.afterEdit(); }
  }

  // A moving hold: the pose stays, drifting a little, for `seconds`.
  holdPose(simId, frame, seconds) {
    const sim = this.store.sim(simId), key = sim && sim.keys.find(k => k.frame === frame && !k.faceOnly);
    if (!key) return;
    const p = this.store.project;
    this.store.checkpoint('Hold pose');
    const k = KO.movingHold(p, sim, key, Math.round(seconds * (p.fps || 30)));
    if (!k) { this.store.undoStep(); return toast('There is no room for a hold before the next key.'); }
    this.timeline.flash(simId, k.frame, 'add');
    this.pipeline.overrides.clear();
    this.keysChanged(); this._applyFit(); this.afterEdit();
    toast(`${sim.label} holds the pose until ${(k.frame / (p.fps || 30)).toFixed(2)} s (it drifts a little, so it never looks frozen).`, 'ok');
  }

  // ---------------------------------------------------------------- loop tools (spec_editing 7.5)
  // (worked out again after every change, and at most every quarter second - it is cheap, and the timeline asks on
  // every redraw)
  loopStatus() {
    const p = this.store.project, now = performance.now();
    const sig = `${this.editRev}|${p.length}|${!!p.loop}|${p.sims.map(s => s.keys.length).join()}|${p.uid}`;
    if (!this._loopCache || this._loopCache.sig !== sig || now - this._loopCache.t > 250) this._loopCache = { sig, t: now, list: KO.loopCheck(p) };
    return this._loopCache.list;
  }

  loopMenu(x, y) {
    const p = this.store.project, st = this.loopStatus();
    const bad = st.filter(r => ['pause', 'snap', 'pop'].includes(r.kind));
    const items = [{ heading: p.loop ? 'Loop check' : 'The loop is off' }];
    for (const r of st) {
      const s = this.store.sim(r.simId);
      if (!s) continue;
      items.push({ label: `${s.label}: ${KO.LOOP_TEXT[r.kind] || r.kind}`, icon: r.kind === 'ok' ? 'check' : r.kind === 'open' ? 'loop' : 'x',
        onClick: () => { this.selectSim(s.id); const last = s.keys.filter(k => !k.faceOnly).pop(); this.setFrame(last ? last.frame : p.length - 1); } });
    }
    items.push('-');
    if (bad.length) items.push({ label: bad.length > 1 ? `Fix it for all ${bad.length} sims` : 'Fix it', icon: 'spark', onClick: () => this.fixLoops() });
    if (p.loop) items.push({ label: 'Start the loop here', icon: 'loop', onClick: () => this.startLoopHere() });
    else items.push({ label: 'Make the end match the start', icon: 'loop', onClick: () => this.makeEndMatchStart() });
    items.push({ label: p.loop ? 'Loop is on - turn it off' : 'Loop is off - turn it on', icon: 'loop', onClick: () => this.toggleLoop() });
    this._menu(x, y, items, 'menus.loop', { frame: Math.round(this.store.frame), loop: true });
  }

  fixLoops() {
    const p = this.store.project, bad = this.loopStatus().filter(r => ['pause', 'snap', 'pop'].includes(r.kind));
    if (!bad.length) return toast('The loop already flows smoothly.', 'ok');
    this.store.checkpoint('Fix the loop');
    for (const r of bad) { const s = this.store.sim(r.simId); if (s) KO.fixLoop(p, s, r.kind); }
    this.pipeline.overrides.clear();
    this.timeline.pruneSel();
    this.keysChanged(); this._applyFit(); this.afterEdit();
    toast(`Loop fixed for ${bad.map(r => this.store.sim(r.simId)?.label).filter(Boolean).join(', ')} - it flows back into the start now.`, 'ok');
  }

  // Rotate the whole loop so it begins at `frame` (the same animation, starting somewhere else).
  startLoopHere(frame = Math.round(this.store.frame)) {
    const p = this.store.project;
    if (!p.loop) return toast('Turn the loop on first.');
    if (!frame) return toast('The loop already starts here.');
    if (this.playing) this.setPlaying(false);
    this.store.checkpoint('Start the loop here');
    KO.offsetCycle(p, null, -frame);
    this.pipeline.overrides.clear();
    this.timeline.clearSel();
    this.keysChanged(); this.afterEdit(); this.updateTrail();
    this.setFrame(0);
    toast(`The loop now starts at what was ${(frame / (p.fps || 30)).toFixed(2)} s.`, 'ok');
  }

  // One sim's whole animation a frame later or earlier (natural overlap between partners).
  shiftSim(simId, n) {
    const p = this.store.project, s = this.store.sim(simId);
    if (!s || !p.loop) return;
    this.store.checkpoint(`Move ${s.label}'s animation`);
    KO.offsetCycle(p, [simId], n);
    this.pipeline.overrides.clear();
    this.timeline.pruneSel();
    this.keysChanged(); this.afterEdit();
    toast(`${s.label}'s whole animation moved ${this._plural(Math.abs(n), 'frame')} ${n > 0 ? 'later' : 'earlier'}.`, 'ok');
  }

  // Loop off: the last frame gets a copy of the first pose.
  makeEndMatchStart(simIds = null) {
    const p = this.store.project;
    const sims = simIds ? simIds.map(id => this.store.sim(id)).filter(Boolean) : p.sims;
    this.store.checkpoint('Make the end match the start');
    let n = 0;
    for (const s of sims) if (KO.makeEndMatchStart(p, s)) { n++; this.timeline.flash(s.id, p.length - 1, 'add'); }
    this.keysChanged(); this._applyFit(); this.afterEdit();
    toast(n ? 'The last frame now matches the first.' : 'Nothing to change.', n ? 'ok' : '');
  }

  toggleLoop() {
    this.store.checkpoint(this.store.project.loop ? 'Loop off' : 'Loop on');
    this.store.project.loop = !this.store.project.loop;
    $('btn-loop').classList.toggle('on', this.store.project.loop);
    this._edited();
    this.applyPoses(); this.physicsChanged(); this.timeline.draw();
  }

  // ---------------------------------------------------------------- mirror the whole animation (spec_editing 7.6)
  mirrorAnimation() {
    const p = this.store.project;
    if (!p.sims.length) return;
    if (this.playing) this.setPlaying(false);
    this.store.checkpoint('Mirror the whole animation');
    const { holdsToRebind } = KO.mirrorProject(p, this.assets.rig, uid('a'));
    this._file = null;
    this.shareData = null;
    this.pipeline.overrides.clear();
    this.timeline.clearSel();
    this.refreshAll();
    this.physicsChanged();
    for (const hd of holdsToRebind) { try { this.interact.rebindHold?.(hd.simId, hd.limb); } catch (err) { console.error(err); } }
    this._edited();
    choiceBar(`Mirrored - it is a new animation "${p.name}"; your original file is unchanged. Save to keep it.`,
      [{ label: 'Save now', primary: true, onClick: () => { this.save(); } }, { label: 'Undo', onClick: () => { this.undo(); } }], { timeout: 14000 });
  }

  // ---------------------------------------------------------------- play range (spec_editing 7.7)
  setPlayRange(r, { quiet = false } = {}) {
    const L = this.store.project.length;
    if (r && Array.isArray(r)) {
      let a = Math.max(0, Math.min(L - 1, Math.round(r[0]))), b = Math.max(0, Math.min(L - 1, Math.round(r[1])));
      if (b < a) [a, b] = [b, a];
      this.playRange = [a, b];
    } else this.playRange = null;
    this.timeline.draw();
    if (this.curves && this.curves.shown) this.curves.draw();
    if (quiet) return;
    const fps = this.store.project.fps || 30;
    if (this.playRange) toast(`Playing only ${(this.playRange[0] / fps).toFixed(2)}-${(this.playRange[1] / fps).toFixed(2)} s. Press P (or the x in the ruler) to play the whole loop.`);
    else toast('Playing the whole loop.');
  }
  togglePlayRange() {
    if (this.playRange) return this.setPlayRange(null);
    this.playSelection();
  }
  playSelection() {
    const r = this.timeline.selRange();
    if (!r || r.max <= r.min) return toast('Select keys across a stretch of time first (their part plays), or Ctrl+drag in the ruler.');
    this.setPlayRange([r.min, r.max]);
    if (!this.playing) this.setPlaying(true);
  }

  // ---------------------------------------------------------------- undo history (spec_editing 7.9)
  undoHistoryMenu(x, y) {
    const list = this.store.history(15);
    if (!list.length) return toast('Nothing to undo yet.');
    const ago = t => { const s = Math.max(0, Math.round((Date.now() - t) / 1000)); return s < 60 ? `${s} s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`; };
    contextMenu(x, y, [{ heading: 'Undo back to before…' }, ...list.map((e, i) => ({ label: `${e.label} · ${ago(e.t)}`, icon: 'undo', onClick: () => this.undoTo(i) }))]);
  }
  undoTo(i) {
    const before = this.store.project;
    const r = this.store.undoTo(i);
    if (!r) return;
    this._afterHistory(before, false);
    toast(i ? `Undone ${i + 1} steps (back to before "${this.store.redo[this.store.redo.length - 1]?.label || r}").` : `Undone: ${typeof r === 'string' ? r : 'the last change'}.`);
  }
  _historyToast(r, redo) {
    if (!r) return toast(redo ? 'Nothing to redo.' : 'Nothing to undo.');
    toast(typeof r === 'string' && r ? `${redo ? 'Redone' : 'Undone'}: ${r}.` : (redo ? 'Redone.' : 'Undone.'));
  }

  // ---------------------------------------------------------------- ghosts options (spec_editing F1)
  onionMenu(x, y) {
    const pick = m => { this.onionMode = m; localStorageSet('onionMode', m); this.onion = true; $('btn-onion').classList.add('on'); this._ghostKey = ''; this.updateGhosts(); };
    contextMenu(x, y, [
      { heading: 'Ghosts show' },
      { label: 'The keys before and after', icon: 'ghost', checked: this.onionMode === 'keys', onClick: () => pick('keys') },
      { label: 'Every 3 frames, 2 before and 2 after', icon: 'ghost', checked: this.onionMode === 'frames', onClick: () => pick('frames') },
      { label: 'The keys before and after, and the partner', icon: 'couple', checked: this.onionMode === 'partner', onClick: () => pick('partner') },
      '-',
      { label: this.onion ? 'Ghosts off' : 'Ghosts on', icon: 'eye', onClick: () => $('btn-onion').click() },
    ]);
  }

  // ---------------------------------------------------------------- the timeline: Keys | Curves, height
  setTimelineView(v, { quiet = false } = {}) {
    if (v === 'curves' && !this.curves) v = 'keys';
    this.tlView = v;
    localStorageSet('tlView', v);
    $('tl-canvas').classList.toggle('hidden', v === 'curves');
    $('curve-wrap')?.classList.toggle('hidden', v !== 'curves');
    document.querySelectorAll('#tl-view-seg button').forEach(b => b.classList.toggle('active', b.dataset.tlview === v));
    this._fitTimeline();
    if (this.curves) this.curves.show(v === 'curves');
    if (v === 'keys') requestAnimationFrame(() => this.timeline.draw());
    if (!quiet && v === 'curves' && !localStorageGet('curvesSeen', false)) {
      localStorageSet('curvesSeen', true);
      toast('Curves: how the selected part turns over time. Drag a dot up or down to change that key; click a line for its timing.');
    }
  }

  pickReference() {
    const inp = h('input', { type: 'file', accept: 'image/png,image/jpeg,image/webp,image/gif,video/mp4,video/webm', multiple: true, style: { display: 'none' } });
    inp.onchange = () => { if (inp.files && inp.files.length && this.refs) this.refs.addFiles([...inp.files]); inp.remove(); };
    document.body.append(inp);
    inp.click();
  }

  // ---------------------------------------------------------------- sims
  selectSim(id) {
    const changed = this.store.selected.sim !== id;
    if (changed) this.store.selected = { sim: id, bone: null };
    if (this.interact.tool === 'move') this.interact.selectPlace(id);
    else if (this.interact.tool === 'rotate') { this.vp.gizmo.detach(); this.interact.active = null; }
    this.emitSelection();
    if (changed && this.step === 'face') this.frameFace();
  }

  emitSelection() {
    for (const [id, v] of this.simViews) {
      const sel = this.store.selected;
      v.highlight(sel.sim === id && sel.bone ? v.index(sel.bone) : -1, v.color);
    }
    this.refreshPanels();
    this.timeline.draw();
    this._syncEaseBox();
    this.updateTrail();
    const sel = { simId: this.store.selected.sim, bone: this.store.selected.bone };
    this.runHook('selection', sel);
    this.emit('selection', sel);
  }

  addSim(frame = 'yf') {
    this.store.checkpoint('Add a sim');
    const p = this.store.project;
    const s = newSim(p, frame);
    p.sims.push(s);
    this.store.selected = { sim: s.id, bone: null };
    this.syncViews();
    const v = this.simViews.get(s.id);
    v.resetPose();
    this.interact.moveHips(v, new THREE.Vector3((p.sims.length - 1) * 0.8, 0, 0));
    this._relaxArms(v);
    s.keys.push({ frame: Math.round(this.store.frame), ease: 'auto', pose: this._bodyPose(v) });
    this.refreshAll();
    toast(`${s.label} added. Put it in a pose in step 2.`, 'ok');
  }

  removeSim(id) {
    const p = this.store.project;
    this.store.checkpoint('Remove a sim');
    p.sims = p.sims.filter(s => s.id !== id);
    if (this.store.selected.sim === id) this.store.selected = { sim: p.sims[0] ? p.sims[0].id : null, bone: null };
    this.vp.gizmo.detach();
    this.interact.active = null;
    this.runHook('simRemoved', id, p);
    this.refreshAll();
  }

  duplicateSim(id) {
    this.store.checkpoint('Duplicate a sim');
    const src = this.store.sim(id);
    const copy = JSON.parse(JSON.stringify(src));
    const p = this.store.project;
    Object.assign(copy, newSim(p, src.frame), { keys: copy.keys, pins: copy.pins, layers: copy.layers, body: copy.body, sounds: [], skin: src.skin, gender: src.gender, label: src.label + ' copy' });
    p.sims.push(copy);
    this.refreshAll();
  }

  setSimBody(id, frame) {
    this.store.checkpoint('Change body');
    const s = this.store.sim(id);
    s.frame = frame;
    s.gender = BODY_TYPES[frame]?.gender || s.gender;
    if (s.body) s.body.physics = undefined;
    simBody(s);
    // voice lines follow the body: lines of the other gender are taken off
    s.sounds = (s.sounds || []).filter(x => soundFitsSim(x.name, s));
    this.refreshAll();
    this.physicsChanged();
  }

  clearKeys(id) {
    this.store.checkpoint('Clear keys');
    const s = this.store.sim(id);
    const v = this.simViews.get(id);
    this._base({ sim: s, v }, this.store.frame);
    s.keys = [{ frame: 0, ease: 'auto', pose: this._bodyPose(v) }];
    this.refreshAll();
  }

  toggleVisible(id) { const s = this.store.sim(id); s.visible = s.visible === false; this.syncViews(); this.refreshPanels(); this.interact.refreshHandles(); }
  setSkin(id, c) { this.store.checkpoint(); this.store.sim(id).skin = c; this.syncViews(); this.refreshPanels(); }
  setColor(id, c) { this.store.checkpoint(); this.store.sim(id).color = c; this.syncViews(); this.refreshAll(); }

  setFurniture(id) {
    this.store.checkpoint('Change the place');
    const f = this.furniture.find(x => x.id === id);
    this.store.project.furniture = id;
    this.store.project.locations = [...f.locations];
    this.buildFurniture();
    this.refreshPanels();
  }

  setBody(simId, fn) {
    const s = this.store.sim(simId);
    if (!s) return;
    this.store.checkpoint('Body setting');
    fn(simBody(s));
    this._edited();
    this.applyPoses(false);
    this.refreshPanels();
    this.physicsChanged();
  }

  // ---------------------------------------------------------------- pose tools
  // Back to rest: the turn, and the place too (face bones are mostly moved) - except the hips, which carry the
  // sim's place. { turn, move } choose (Alt+R resets the turn, Alt+G the move).
  resetBone(simId, name, { turn = true, move = true } = {}) {
    const v = this.simViews.get(simId);
    if (!v || !v.bone(name)) return;
    this.store.checkpoint('Reset part');
    this.beginEdit(simId);
    const r = v.restByName[name];
    const face = K.isFace(name);
    const q = turn ? r.quat.clone() : null, p = move && !HIPS.includes(name) ? r.pos.clone() : null;
    if (face) K.setBase(v, name, q, p);
    else { if (q) v.bone(name).quaternion.copy(q); if (p) v.bone(name).position.copy(p); }
    if (!face) K.twist(this, { sim: this.store.sim(simId), v });
    this.poseEdited(simId, false, face ? 'face' : 'body');
  }

  // The inspector's turn rows (degrees from standing about x / y / z).
  setBoneTurn(simId, name, axis, degrees, commit) {
    const sim = this.store.sim(simId), view = this.simViews.get(simId);
    if (!sim || !view || !view.bone(name)) return;
    this.beginEdit(simId);
    const bone = view.bone(name), rest = view.restByName[name].quat;
    const hip = name === 'b__Pelvis__' ? this.interact.beginHipTurn(view) : null;
    const cur = new THREE.Euler().setFromQuaternion(rest.clone().invert().multiply(bone.quaternion), 'XYZ');
    cur[axis] = THREE.MathUtils.degToRad(degrees);
    bone.quaternion.copy(rest.clone().multiply(new THREE.Quaternion().setFromEuler(cur)));
    if (hip) this.interact.applyHipTurn(view, hip);
    if (this.mirrorEdit) this.mirrorLive(simId, name);
    this.pipeline.pins({ sim, v: view });
    K.twist(this, { sim, v: view });
    this.poseEdited(simId, !commit, K.isFace(name) ? 'face' : 'body');
    if (commit) this.afterEdit();
  }

  // The inspector's move rows for extra bones (metres from the rest place).
  setBoneMove(simId, name, axis, metres, commit) {
    const view = this.simViews.get(simId);
    if (!view || !view.bone(name)) return;
    this.beginEdit(simId);
    const p = view.bone(name).position, r = view.restByName[name].pos;
    p[axis] = r[axis] + metres;
    if (this.mirrorEdit) this.mirrorLive(simId, name);
    this.poseEdited(simId, !commit, 'body');
    if (commit) this.afterEdit();
  }

  // A twist helper turned by hand about its own length (then it no longer follows by itself).
  setBoneTwist(simId, name, radians, commit) {
    const view = this.simViews.get(simId);
    if (!view || !view.bone(name)) return;
    this.beginEdit(simId);
    view.bone(name).quaternion.copy(view.restByName[name].quat.clone().multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), radians)));
    if (this.mirrorEdit) this.mirrorLive(simId, name);
    this.poseEdited(simId, !commit, 'body');
    if (commit) this.afterEdit();
  }

  // "Let it follow again": the twist helper is taken out of every key, so it follows the hand / arm / leg again.
  unkeyTwist(simId, bone) {
    const sim = this.store.sim(simId);
    if (!sim) return;
    this.store.checkpoint('Let the twist follow');
    for (const k of sim.keys) {
      if (k.pose && k.pose.rot) delete k.pose.rot[bone];
      if (k.pose && k.pose.pos) delete k.pose.pos[bone];
    }
    const ov = this.pipeline.overrides.get(simId);
    if (ov && ov.pose && ov.pose.rot) delete ov.pose.rot[bone];
    this.applyPoses();
    this.afterEdit();
    toast(`${label(bone, sim.frame)} follows by itself again.`, 'ok');
  }

  // Which way the sim faces, as a turn about the vertical. Taken from the hips: where they point, or - for a sim
  // lying on its back or front, whose hips point up or down - from their side-to-side line. Mirroring happens
  // in this frame, so a turned sim keeps facing its partner and mirroring twice gives the pose back exactly.
  _facing(v) {
    const q = spaceQuat(v, v.bone('b__Pelvis__'));
    const f = new THREE.Vector3(0, 1, 0).applyQuaternion(q);     // the hips' forward (+Z at rest)
    const l = new THREE.Vector3(0, 0, -1).applyQuaternion(q);    // the hips' left (+X at rest)
    const ang = Math.hypot(f.x, f.z) >= Math.hypot(l.x, l.z) ? Math.atan2(f.x, f.z) : Math.atan2(-l.z, l.x);
    return new THREE.Quaternion().setFromAxisAngle(UP, ang);
  }

  _restSpace(v) { return v.restSpace || (v.restSpace = this._restSpaceQuats(v)); }

  _restSpaceQuats(v) {
    const out = [];
    const rot = k => {
      if (out[k]) return out[k];
      const parent = v.rig.bones[k].parent;
      out[k] = parent >= 0 ? rot(parent).clone().multiply(v.rest[k].quat) : v.rest[k].quat.clone();
      return out[k];
    };
    v.rest.forEach((r, k) => rot(k));
    return out;
  }

  // Bones from the root outwards (a parent is always set before its children).
  _depthOrder(v) {
    if (v._depthOrder) return v._depthOrder;
    const depth = k => { let d = 0; for (let p = v.rig.bones[k].parent; p >= 0; p = v.rig.bones[p].parent) d++; return d; };
    return (v._depthOrder = v.bones.map((b, k) => k).sort((a, b) => depth(a) - depth(b)));
  }

  mirrorBone(simId, name) {
    const v = this.simViews.get(simId);
    if (!v) return;
    this.store.checkpoint('Mirror part');
    this.beginEdit(simId);
    this._mirrorBoneIn(v, name);
    const sim = this.store.sim(simId);
    this.poseEdited(simId, false, K.isFace(name) ? 'face' : 'body');
    toast(`${label(name, sim && sim.frame)} copied to ${label(mirrorName(name), sim && sim.frame)}.`);
  }

  // One bone onto its other side: face bones with the face mirror rule (a middle face bone keeps to the middle),
  // body bones mirrored across the sim's own middle.
  _mirrorBoneIn(v, name) {
    if (K.isFace(name)) {
      if (K.isCenterFace(name)) K.mirrorFaceBone(v, name, name);
      else K.mirrorFaceBone(v, name, mirrorName(name));
      return;
    }
    if (!/_(L|R)_/.test(name)) return;
    this._mirrorInto(v, name, mirrorName(name));
    // an extra bone that was moved (a breast, a butt cheek) is moved on the other side too
    const to = mirrorName(name), b = v.bone(name), t = v.bone(to);
    if (K.isExtra(name) && b && t) {
      const d = b.position.clone().sub(v.restByName[name].pos);
      t.position.copy(v.restByName[to].pos).add(new THREE.Vector3(d.x, d.y, -d.z));
    }
  }

  // Symmetry: while on, whatever you do to one side happens to the other (and a middle face part stays centred).
  mirrorLive(simId, name) {
    const v = this.simViews.get(simId);
    if (!v) return;
    if (!K.isFace(name) && !/_(L|R)_/.test(name)) return;
    this._mirrorBoneIn(v, name);
  }
  setMirrorEdit(on) { this.mirrorEdit = on; toast(on ? 'Symmetry on: posing one side poses the other (X).' : 'Symmetry off.'); this.refreshPanels(); }

  // One bone's turn (from standing) copied to its mirror bone, mirrored across the sim's own middle.
  _mirrorInto(v, from, to) {
    const rs = this._restSpace(v);
    const T = this._facing(v), Ti = T.clone().invert();
    const delta = Ti.clone().multiply(spaceQuat(v, v.bone(from)).normalize()).multiply(rs[v.index(from)].clone().invert());
    setSpaceQuat(v, v.bone(to), T.clone().multiply(mirrorQuat(delta, new THREE.Vector3(1, 0, 0))).multiply(rs[v.index(to)]));
  }

  mirrorPose(simId) {
    const v = this.simViews.get(simId);
    if (!v) return;
    this.store.checkpoint('Mirror pose');
    this.beginEdit(simId);
    const rs = this._restSpace(v);
    const T = this._facing(v), Ti = T.clone().invert();
    const X = new THREE.Vector3(1, 0, 0);
    const before = {};
    for (const n of POSABLE) if (v.bone(n)) before[n] = spaceQuat(v, v.bone(n)).normalize();
    const hips = spacePos(v, v.bone('b__Pelvis__')), back = spacePos(v, v.bone('b__Spine0__'));
    const set = new Set(POSABLE);
    for (const k of this._depthOrder(v)) {
      const n = v.bones[k].name;
      if (!set.has(n)) continue;
      const m = before[mirrorName(n)] ? mirrorName(n) : n;
      if (!before[m]) continue;
      // the other side's turn from standing, in the sim's own frame, mirrored left <-> right
      const delta = Ti.clone().multiply(before[m]).multiply(rs[v.index(m)].clone().invert());
      setSpaceQuat(v, v.bones[k], T.clone().multiply(mirrorQuat(delta, X)).multiply(rs[k]));
    }
    // the lower back sits where the hips are, mirrored across the sim's middle (the hips stay put)
    const side = X.clone().applyQuaternion(T);
    const d = back.sub(hips);
    d.sub(side.clone().multiplyScalar(2 * d.dot(side)));
    const spine = v.bone('b__Spine0__'), parent = spine.parent;
    spine.position.copy(hips.add(d).sub(spacePos(v, parent)).applyQuaternion(spaceQuat(v, parent).invert()));
    this._mirrorFaceIn(v);
    this.poseEdited(simId, false, 'both');
    toast('Pose mirrored.');
  }

  // The face swapped left <-> right (the middle of the mouth and the tongue kept in the middle).
  _mirrorFaceIn(v) {
    const fb = K.getFaceBones(v), m = K.mirrorFaceBonesData(fb);
    for (const n of K.FACE_CHANNEL) {
      const r = v.restByName[n];
      if (!r || !v.bone(n)) continue;
      K.setBase(v, n, m.rot[n] ? new THREE.Quaternion().fromArray(m.rot[n]) : r.quat.clone(), m.pos[n] ? new THREE.Vector3().fromArray(m.pos[n]) : r.pos.clone());
    }
    for (const n of K.FACE_CHANNEL) if (K.isCenterFace(n) && v.bone(n)) K.mirrorFaceBone(v, n, n);
  }

  resetPose(simId) {
    const v = this.simViews.get(simId);
    this.store.checkpoint('Stand straight');
    this.beginEdit(simId);
    const hips = HIPS.map(n => v.bone(n).position.clone());
    const pelvisQ = spaceQuat(v, v.bone('b__Pelvis__'));
    v.resetPose();
    HIPS.forEach((n, k) => v.bone(n).position.copy(hips[k]));
    // keep which way it faces (turn about the vertical only)
    const fwd = new THREE.Vector3(0, 1, 0).applyQuaternion(pelvisQ); fwd.y = 0;
    if (fwd.lengthSq() > 1e-6) {
      const ang = Math.atan2(fwd.x, fwd.z);
      this.interact.turnHips(v, ang, spacePos(v, v.bone('b__Pelvis__')).setY(0));
    }
    this._relaxArms(v);
    this.poseEdited(simId, false);
  }

  copyPose(simId) {
    const s = this.store.sim(simId), v = this.simViews.get(simId);
    this._base({ sim: s, v }, this.store.frame);
    this.clipboard = this._bodyPose(v);
    toast('Pose copied.');
    this.refreshPanels();
  }

  // mask: only one part ('upper', 'lower', 'hands', 'face'...) is pasted; flipped: the pose mirrored left <-> right.
  pastePose(simId, { mask = null, flipped = false } = {}) {
    if (mask === 'face') return this.faceClipboard ? this.pasteFace(simId) : toast('Copy a face first (right-click a key, or Copy face in the Face step).');
    if (!this.clipboard) return;
    const v = this.simViews.get(simId);
    if (!v) return;
    this.store.checkpoint(flipped ? 'Paste pose mirrored' : mask ? `Paste ${(KO.PART_LABEL[mask] || mask).toLowerCase()}` : 'Paste pose');
    this.beginEdit(simId);
    const rig = this.assets.rig;
    let src = clone(this.clipboard);
    // mirrored: left and right swap in the pose's own frame (it still faces the way it did)
    if (flipped) src = KO.faceLike(KO.mirrorPoseData(src, rig), src, rig);
    if (mask) {
      // one part: it takes the copied turns, fitted to the way this sim faces; its place and pins stay
      const cur = this._bodyPose(v);
      v.setPose(KO.blendInto(cur, KO.faceLike(src, cur, rig), 1, KO.partBones(mask)));
    } else {
      // the sim keeps its own place (its hips); every other bone takes the copied turn, and the copied place too
      // when it was moved off its rest place (stretched) - or its rest place, so an old stretch here is undone
      const pos = {};
      for (const n of Object.keys(src.rot || {})) if (!HIPS.includes(n) && v.restByName[n]) pos[n] = v.restByName[n].pos.toArray();
      for (const [n, p] of Object.entries(src.pos || {})) if (!HIPS.includes(n)) pos[n] = p;
      for (const n of HIPS) pos[n] = v.bone(n).position.toArray();
      v.setPose({ rot: src.rot, pos });
    }
    this.poseEdited(simId, false);
    toast(mask ? `${KO.PART_LABEL[mask] || 'Part'} pasted (the rest of the pose stays).` : flipped ? 'Pose pasted mirrored (the sim stays where it is).' : 'Pose pasted (the sim stays where it is).');
  }

  // Move and/or turn a whole sim through the whole animation: every key (and a pose not keyed yet) and its pins.
  // angle: radians about the vertical around `pivot`; offset: a move. Both in the sim's space. Keys store the
  // place in the two hip bones, relative to the root bone (always at rest), so one conversion fits every key.
  // only: a list of frames - just the keys there change (not the pending pose or the pins).
  transformSim(simId, { angle = 0, pivot = new THREE.Vector3(), offset = null, only = null } = {}) {
    const s = this.store.sim(simId), v = this.simViews.get(simId);
    if (!s || !v) return;
    const rb = v.bone('b__ROOT_bind__');
    const rbQ = spaceQuat(v, rb), rbP = spacePos(v, rb), rbQi = rbQ.clone().invert();
    const R = new THREE.Quaternion().setFromAxisAngle(UP, angle);
    const turnLocal = rbQi.clone().multiply(R).multiply(rbQ);
    const fix = pose => {
      if (!pose) return;
      pose.rot = pose.rot || {};
      pose.pos = pose.pos || {};
      for (const n of HIPS) {
        const k = v.index(n);
        if (k < 0) continue;
        const q = pose.rot[n] ? new THREE.Quaternion().fromArray(pose.rot[n]) : v.rest[k].quat.clone();
        const at = pose.pos[n] ? new THREE.Vector3().fromArray(pose.pos[n]) : v.rest[k].pos.clone();
        const sp = at.applyQuaternion(rbQ).add(rbP).sub(pivot).applyQuaternion(R).add(pivot);
        if (offset) sp.add(offset);
        pose.pos[n] = sp.sub(rbP).applyQuaternion(rbQi).toArray();
        pose.rot[n] = turnLocal.clone().multiply(q).normalize().toArray();
      }
    };
    if (only) { for (const key of s.keys) if (only.includes(key.frame)) fix(key.pose); return; }
    for (const key of s.keys) fix(key.pose);
    const ov = this.pipeline.overrides.get(simId);
    if (ov) fix(ov.pose);
    if (angle) this.interact.turnPins(s, angle, pivot);
    if (offset) this.interact.movePins(s, offset);
  }

  turnSim(simId, degrees) {
    const s = this.store.sim(simId), v = this.simViews.get(simId);
    if (!s || !v) return;
    this.store.checkpoint('Turn sim');
    if (this.playing) this.setPlaying(false);
    this._base({ sim: s, v }, this.store.frame);
    const pivot = spacePos(v, v.bone('b__Pelvis__')).setY(0);
    this.transformSim(simId, { angle: THREE.MathUtils.degToRad(degrees), pivot });
    this.applyPoses();
    this.interact.refreshHandles();
    this.afterEdit();
  }

  // ---------------------------------------------------------------- ready poses
  async loadPosePresets() {
    const [list, mine] = await Promise.all([api.poses().catch(() => []), this._loadMyPoses()]);
    this.posePresets = [...list, ...mine.map(x => ({ ...x, mine: true }))];
    if (this.step === 'pose') this.renderStep();
    this.thumbs.queue(this.posePresets, () => { if (this.step === 'pose') this.renderStep(); });
  }

  // "My poses" are kept by the server (in saves\FitStudio), so clearing the browser never loses them. Older
  // versions kept them in the browser: those are moved to the server once (added to what it has, by id).
  async _loadMyPoses() {
    const old = localStorageGet('myPoses', []);
    const local = Array.isArray(old) ? old.filter(x => x && x.id && x.sims) : [];
    let mine;
    try { mine = await api.myPoses(); }
    catch {
      this._myPosesInBrowser = true;       // an older server without My poses: they stay in the browser
      return local;
    }
    this._myPosesInBrowser = false;
    if (!Array.isArray(mine)) mine = [];
    if (local.length) {
      const have = new Set(mine.map(x => x.id));
      const add = local.filter(x => !have.has(x.id));
      try {
        if (add.length) await api.saveMyPoses([...mine, ...add]);
        localStorageRemove('myPoses');
        mine = [...mine, ...add];
        if (add.length) console.info(`Moved ${add.length} of My poses from the browser to the server.`);
      } catch { mine = [...mine, ...add]; }   // tried again next time; the browser keeps its copy meanwhile
    }
    return mine;
  }

  // Change the saved list: read what the server has now (another window may have added a pose), change it, write
  // it back. -> the new list.
  async _changeMyPoses(change) {
    const plain = x => { const { mine, ...rest } = x; return rest; };
    if (this._myPosesInBrowser) {
      const list = change(localStorageGet('myPoses', []));
      localStorageSet('myPoses', list.map(plain));
      return list;
    }
    const list = change(await api.myPoses());
    await api.saveMyPoses(list.map(plain));
    return list;
  }

  _setMyPoses(list) {
    this.posePresets = [...(this.posePresets || []).filter(x => !x.mine), ...list.map(x => ({ ...x, mine: true }))];
  }

  async deleteMyPose(id) {
    const pr = (this.posePresets || []).find(x => x.mine && x.id === id);
    if (!pr || !(await confirmBox('Delete this pose?', `"${pr.label}" leaves My poses. Animations that used it stay as they are.`, 'Delete', true))) return;
    try { this._setMyPoses(await this._changeMyPoses(list => list.filter(x => x.id !== id))); }
    catch (err) { toast('Could not delete the pose: ' + err.message, 'err'); return; }
    if (this._lastPreset === id) this._lastPreset = null;
    this.refreshPanels();
    toast(`"${pr.label}" deleted from My poses.`, 'ok');
  }

  renameMyPose(id) {
    const pr = (this.posePresets || []).find(x => x.mine && x.id === id);
    if (!pr) return;
    const name = h('input', { class: 'text', value: pr.label });
    modal({ title: 'Rename pose', body: h('label', { class: 'field' }, h('span', {}, 'Name'), name),
      buttons: [{ label: 'Cancel', kind: 'ghost' }, { label: 'Rename', kind: 'primary', onClick: async () => {
        const label = name.value.trim() || pr.label;
        try { this._setMyPoses(await this._changeMyPoses(list => list.map(x => (x.id === id ? { ...x, label } : x)))); }
        catch (err) { toast('Could not rename the pose: ' + err.message, 'err'); return false; }
        this.refreshPanels();
      } }] });
    setTimeout(() => { name.focus(); name.select(); }, 30);
  }

  poseThumb(pr) { return this.thumbs.get(pr); }

  // places: 'ifDefault' - the pose's own places are used only while the project still has the default place
  // (the Floor), so places picked in Scene or Details are never replaced; 'always'; 'never'.
  // Options (spec_editing 7.11): flipped - the pose mirrored; amount - blend it over the pose there (0..1.5);
  // mask - only one part ('upper', 'hands', 'face'...; a partial pose never changes the sim's place or pins);
  // toSelected - put it on every selected key of the matching sims instead of the playhead.
  applyPosePreset(pr, { places = 'ifDefault', flipped = false, amount = 1, mask, toSelected = false, quiet = false, checkpoint = true } = {}) {
    if (mask === undefined) mask = pr.part && pr.part !== 'all' ? pr.part : null;
    if (mask || toSelected || amount !== 1) return this._applyPresetOver(pr, { flipped, amount, mask, toSelected, quiet, checkpoint });
    const p = this.store.project;
    const frame = Math.round(this.store.frame);
    if (checkpoint) this.store.checkpoint(`Use pose "${pr.label}"${flipped ? ' mirrored' : ''}`);
    if (this.playing) this.setPlaying(false);
    const defaultPlace = (p.locations || []).join() === 'FLOOR' && (!p.furniture || p.furniture === 'floor');
    const takePlaces = places === 'always' || (places === 'ifDefault' && defaultPlace);
    const couple = pr.group === 'couple' || pr.sims.length > 1;
    const list = pr.sims.map(ps => (flipped ? this._flipPresetSim(ps, couple) : ps));
    let kept = false, posed = null, castSims = [];
    if (couple) {
      // cast the project's sims into the pose's parts (a female body for the female part...)
      const cast = castSims = this._castPreset(pr, { add: true });
      this.syncViews();
      list.forEach((ps, k) => {
        const s = cast[k], v = this.simViews.get(s.id);
        // a complete pose: bones the ready pose leaves out (penis...) stand at rest, instead of being blended
        // toward whatever the next key happens to have. A ready pose never changes the face.
        let pose = JSON.parse(JSON.stringify(ps.pose));
        if (v) { v.resetPose(); v.setPose(pose); pose = this._bodyPose(v); }
        s.pins = {};
        s.keys = this._replaceKeyAt(s.keys, frame, pose, ps);
      });
      if (pr.furniture && takePlaces) p.furniture = pr.furniture;
      if (pr.locations && pr.locations.length) {
        const same = pr.locations.every(l => (p.locations || []).includes(l));
        if (takePlaces) {
          p.locations = [...pr.locations];
          const f = this.furniture.find(x => x.locations.some(l => pr.locations.includes(l)));
          if (f) p.furniture = f.id;
        } else if (!same) kept = true;
      }
      this.buildFurniture();
    } else {
      const sim = this.store.sim() || p.sims[0];
      const v = this.simViews.get(sim.id);
      this._base({ sim, v }, frame);
      const before = spacePos(v, v.bone('b__Pelvis__'));
      v.setPose(JSON.parse(JSON.stringify(list[0].pose)));
      const after = spacePos(v, v.bone('b__Pelvis__'));
      offsetHips(v, new THREE.Vector3(before.x - after.x, 0, before.z - after.z));
      sim.pins = {};
      sim.keys = this._replaceKeyAt(sim.keys, frame, this._bodyPose(v), list[0]);
      posed = [sim];
    }
    if (!posed) posed = castSims.filter(Boolean);
    this._lastPreset = pr.id;
    this._justPicked = pr.id;
    this.pipeline.overrides.clear();
    this.refreshAll();
    this.physicsChanged();
    // on a bed, sofa or chair the sims rest on its top instead of standing in it at floor height
    this._lifting = this._liftOntoFurniture(posed, frame);
    this.frameSims();
    const nice = s => s.toLowerCase().replace(/_/g, ' ');
    if (!quiet) toast(`${pr.label} pose${flipped ? ' (mirrored)' : ''} set at ${(frame / 30).toFixed(1)} s.${kept ? ` Your places (${(p.locations || []).map(nice).join(', ')}) were kept.` : ' Adjust it, then add motion in step 3.'}`, 'ok');
    return posed;
  }

  // The project's sims cast into a pose's parts (a female body for the female part...). add: make sims that are
  // missing (a couple pose in a one-sim animation); otherwise a part without a sim is left out (null).
  _castPreset(pr, { add = true } = {}) {
    const p = this.store.project, free = [...p.sims];
    return pr.sims.map(ps => {
      const want = ps.gender === 'MALE' ? ['ym', 'yf_futa'] : ps.gender === 'FEMALE' ? ['yf'] : ['yf', 'ym', 'yf_futa'];
      let i = free.findIndex(s => want.includes(s.frame));
      if (i < 0) i = free.length ? 0 : -1;
      if (i >= 0) return free.splice(i, 1)[0];
      if (!add) return null;
      const s = newSim(p, ps.gender === 'MALE' ? 'ym' : 'yf');
      p.sims.push(s);
      return s;
    });
  }

  // A ready pose's sim, mirrored: a couple is mirrored as one scene (they swap sides, still facing each other); a
  // one-sim pose in its own frame (it keeps facing the same way). The face comes along mirrored.
  _flipPresetSim(ps, couple) {
    const rig = this.assets.rig;
    const pose = couple ? KO.mirrorPoseData(ps.pose, rig) : KO.faceLike(KO.mirrorPoseData(ps.pose, rig), ps.pose, rig);
    const out = { ...ps, pose };
    if (ps.face) out.face = KO.mirrorFace(ps.face);
    if (ps.faceBones) out.faceBones = KO.mirrorFaceBones(ps.faceBones);
    return out;
  }

  // A ready pose blended over what is there (amount), only for one part (mask), or on the selected keys.
  _applyPresetOver(pr, { flipped = false, amount = 1, mask = null, toSelected = false, quiet = false, checkpoint = true } = {}) {
    const p = this.store.project, frame = Math.round(this.store.frame);
    const couple = pr.group === 'couple' || pr.sims.length > 1;
    const list = pr.sims.map(ps => (flipped ? this._flipPresetSim(ps, couple) : ps));
    const cast = couple ? this._castPreset(pr, { add: false }) : [this.store.sim() || p.sims[0]];
    const bones = KO.partBones(mask);
    if (toSelected && !cast.some(s => s && this.timeline.selKeysOf(s.id).some(k => !k.faceOnly))) { toast('Select some keys of these sims first.'); return false; }
    const part = mask ? (KO.PART_LABEL[mask] || mask).toLowerCase() : '';
    if (checkpoint) this.store.checkpoint(toSelected ? 'Pose on selected keys' : mask ? `Use the ${part} of "${pr.label}"` : `Blend in "${pr.label}"`);
    if (this.playing) this.setPlaying(false);
    let n = 0;
    const posed = [];
    list.forEach((ps, i) => {
      const sim = cast[i];
      if (!sim) return;
      const frames = toSelected ? this.timeline.selKeysOf(sim.id).filter(k => !k.faceOnly).map(k => k.frame) : [frame];
      for (const f of frames) {
        const target = this._presetTarget(sim, ps, f, { couple, bones });
        if (!target) continue;
        const key = sim.keys.find(k => k.frame === f);
        const pose = KO.blendInto(target.base, target.pose, amount, bones);
        if (mask !== 'face') {
          if (key) { key.pose = pose; delete key.faceOnly; } else sim.keys.push({ frame: f, ease: this._defaultEase(), pose });
        }
        if (KO.partHasFace(mask) && amount >= 0.5) {
          const k2 = sim.keys.find(k => k.frame === f) || this._faceKeyAt(sim, f);
          if (ps.face && Object.keys(ps.face).length) k2.face = { ...ps.face };
          if (ps.faceBones && (Object.keys(ps.faceBones.rot || {}).length || Object.keys(ps.faceBones.pos || {}).length)) k2.faceBones = clone(ps.faceBones);
        }
        sortKeys(sim.keys);
        n++;
      }
      posed.push(sim);
    });
    this._lastPreset = pr.id;
    this._justPicked = pr.id;
    this.pipeline.overrides.clear();
    this.keysChanged();
    this.afterEdit();
    if (!quiet) toast(toSelected ? `${pr.label}${mask ? ` (${part})` : ''} put on ${this._plural(n, 'key')}.` : mask ? `${pr.label}: the ${part} is set at ${(frame / 30).toFixed(1)} s.` : `${pr.label} blended in at ${Math.round(amount * 100)}%.`, 'ok');
    return posed;
  }

  // What a ready pose would make of one sim's key at `f`: {base (the pose there now), pose (the target)}. A whole
  // one-sim pose stands where the sim stands (as a click puts it); a part fits the way the sim faces.
  _presetTarget(sim, ps, f, { couple = false, bones = null } = {}) {
    const p = this.store.project, rig = this.assets.rig;
    const key = sim.keys.find(k => k.frame === f);
    const base = clone(key && !key.faceOnly ? key.pose : evaluate(sim.keys, f, p.length, p.loop, p.autoCurve));
    if (!base) return null;
    let pose = clone(ps.pose);
    if (bones) pose = KO.faceLike(pose, base, rig);
    else if (!couple) {
      pose = { rot: { ...(base.rot || {}), ...(pose.rot || {}) }, pos: { ...(base.pos || {}), ...(pose.pos || {}) } };
      const b = KO.hipsOf(base, rig), a = KO.hipsOf(pose, rig);
      KO.placePoses([pose], rig, { move: new THREE.Vector3(b.x - a.x, 0, b.z - a.z) });
    }
    return { base, pose };
  }

  // Press a pose tile and drag sideways: the pose blends in live (0-150%). -> {update(amount), end(), cancel()}
  beginPoseBlend(pr) {
    if (this.playing) this.setPlaying(false);
    const p = this.store.project, frame = Math.round(this.store.frame);
    const couple = pr.group === 'couple' || pr.sims.length > 1;
    this.store.checkpoint(`Blend in "${pr.label}"`);
    const snap = JSON.parse(JSON.stringify(p));
    const beforeOf = id => {
      const s = snap.sims.find(x => x.id === id);
      if (!s) return null;
      const k = s.keys.find(x => x.frame === frame && !x.faceOnly);
      return clone(k ? k.pose : evaluate(s.keys, frame, snap.length, snap.loop, snap.autoCurve));
    };
    let items = null, amount = 1, ended = false;
    const ready = () => {
      if (couple) {
        // the whole pose once (casting, places, lifted onto furniture), then blended from what was there
        const posed = this.applyPosePreset(pr, { quiet: true, checkpoint: false }) || [];
        return Promise.resolve(this._lifting).then(() => {
          items = posed.map(s => { const k = s.keys.find(x => x.frame === frame); return k ? { id: s.id, before: beforeOf(s.id) || clone(k.pose), target: clone(k.pose) } : null; }).filter(Boolean);
        });
      }
      const sim = this.store.sim() || p.sims[0];
      const t = sim && this._presetTarget(sim, pr.sims[0], frame, {});
      items = t ? [{ id: sim.id, before: t.base, target: t.pose }] : [];
      return Promise.resolve();
    };
    const apply = () => {
      if (!items || ended === 'cancel') return;
      for (const it of items) {
        const s = this.store.sim(it.id);
        if (!s) continue;
        const pose = blendPoses(it.before, it.target, amount);
        const k = s.keys.find(x => x.frame === frame);
        if (k) { k.pose = pose; delete k.faceOnly; } else { s.keys.push({ frame, ease: this._defaultEase(), pose }); sortKeys(s.keys); }
      }
      this.pipeline.overrides.clear();
      this._edited();
      this.applyPoses(false);
      this.timeline.draw();
    };
    const wait = ready().then(apply);
    return {
      get amount() { return amount; },
      update: a => { amount = Math.max(0, Math.min(1.5, a)); apply(); },
      end: () => { ended = true; return wait.then(() => { apply(); this._lastPreset = pr.id; this.afterEdit(); toast(`${pr.label} blended in at ${Math.round(amount * 100)}%.`, 'ok'); }); },
      cancel: () => { ended = 'cancel'; return wait.then(() => { this.undo(); toast('Blend taken back.'); }); },
    };
  }

  // The key at `frame` gets the pose; the face it had stays (unless the pose brings its own face, from the Library).
  _replaceKeyAt(keys, frame, pose, ps) {
    const old = keys.find(x => x.frame === frame);
    const key = { frame, ease: this._defaultEase(), pose };
    if (ps && ps.faceBones && (Object.keys(ps.faceBones.rot || {}).length || Object.keys(ps.faceBones.pos || {}).length)) {
      key.faceBones = clone(ps.faceBones);
      key.face = {};
    } else if (old) {
      if (old.face) key.face = { ...old.face };
      if (old.faceBones) key.faceBones = clone(old.faceBones);
    }
    // a pose saved with its face sliders (My poses) brings them along
    if (ps && ps.face && Object.keys(ps.face).length) key.face = { ...ps.face };
    return sortKeys([...keys.filter(x => x.frame !== frame), key]);
  }

  // Ready poses come from floor animations: on furniture (a bed, a sofa, a chair...) the posed sims are lifted so they
  // rest on its top (the lowest bone 6 cm above it, as Magic does), then the camera frames them. With a single key
  // per sim the whole animation moves (the shared placing helpers also lay the bodies along a bed); with more keys,
  // only the keys at this frame move, so poses keyed earlier stay where they were.
  _liftOntoFurniture(sims, frame) {
    const p = this.store.project, def = this.furniture.find(f => f.id === p.furniture);
    if (!def || def.kind === 'floor' || def.kind === 'wall' || !sims.length) return Promise.resolve(false);
    const run = info => {
      if (this.store.project !== p || p.furniture !== def.id) return false;         // something else was opened meanwhile
      const pl = this._placing;
      const fallback = def.size ? def.size[1] : 0;
      const top = pl && pl.surfaceY ? pl.surfaceY(info, fallback) : (info && typeof info.surface_height === 'number' ? info.surface_height : fallback);
      if (!(top > 0.05)) return false;
      const whole = sims.every(s => s.keys.length === 1 && s.keys[0].frame === frame);
      if (whole && pl && typeof pl.fitOnSurface === 'function' && info) {
        return Promise.resolve(pl.fitOnSurface(this, sims, info, { frame })).then(() => this._afterLift(sims, frame), () => this._liftBy(sims, frame, top, whole));
      }
      return this._liftBy(sims, frame, top, whole);
    };
    const known = this._furnInfoKnown && this._furnInfoKnown.has(def.id) ? this._furnInfoKnown.get(def.id) : undefined;
    if (known !== undefined) return Promise.resolve(run(known));
    return this._furnitureInfo(def.id).then(run, () => run(null));
  }

  _liftBy(sims, frame, top, whole) {
    // the lowest point of the skin (the shared placing helpers measure it on the meshes), else the lowest bone - 6 cm
    const pl = this._placing;
    let skin = pl && typeof pl.lowestSkin === 'function' ? pl.lowestSkin(this, sims, frame) : NaN;
    if (!Number.isFinite(skin)) {
      let low = Infinity;
      for (const s of sims) {
        const v = this.simViews.get(s.id);
        if (!v) continue;
        this._base({ sim: s, v }, frame);
        v.group.updateMatrixWorld(true);
        for (const n of POSABLE) if (v.bone(n)) low = Math.min(low, v.worldPos(n).y);
      }
      skin = low - 0.06;
    }
    if (!Number.isFinite(skin)) return false;
    const dy = top + 0.005 - skin;
    if (Math.abs(dy) < 0.003) return false;
    for (const s of sims) this.transformSim(s.id, { offset: new THREE.Vector3(0, dy, 0), only: whole ? null : [frame] });
    return this._afterLift(sims, frame);
  }

  _afterLift() {
    this.applyPoses();
    this.refreshAll();
    this.physicsChanged();
    this.frameSims();
    return true;
  }

  // Save to My poses (spec_editing 2.6): the whole body or one part, in a folder. from: {pose, faceBones} of a key
  // (the key menu's "Save as a pose..."); otherwise the pose shown now.
  saveMyPose(simId, from = null) {
    const parts = [['all', 'Whole body'], ['upper', 'Upper body'], ['lower', 'Lower body'], ['hands', 'Both hands'], ['L hand', 'Left hand'], ['R hand', 'Right hand'], ['face', 'Face']];
    const multi = this.store.project.sims.length > 1 && !from;
    const all = h('input', { type: 'checkbox', checked: multi });
    const name = h('input', { class: 'text', placeholder: 'e.g. Kneeling, legs apart' });
    const part = h('select', {}, parts.map(([v, t]) => h('option', { value: v }, t)));
    const folders = [...new Set((this.posePresets || []).filter(x => x.mine && x.folder).map(x => x.folder))];
    const listId = 'mp-folders-' + Date.now().toString(36);
    const folder = h('input', { class: 'text', placeholder: 'e.g. Hands, Faces, Kneeling (optional)', list: listId });
    const dl = h('datalist', { id: listId }, folders.map(f => h('option', { value: f })));
    const allRow = h('label', { class: 'check' }, all, 'Save all sims together (a couple pose)');
    part.onchange = () => { if (part.value === 'face' && !folder.value) folder.placeholder = 'e.g. Faces'; else if (/hand/i.test(part.value) && !folder.value) folder.placeholder = 'e.g. Hands'; };
    modal({ title: 'Save to My poses', body: h('div', {}, h('label', { class: 'field' }, h('span', {}, 'Name'), name),
      h('div', { class: 'grid-2' }, h('label', { class: 'field' }, h('span', {}, 'What to save'), part), h('label', { class: 'field' }, h('span', {}, 'Folder'), folder, dl)),
      multi ? allRow : null),
    buttons: [{ label: 'Cancel', kind: 'ghost' }, { label: 'Save', kind: 'primary', onClick: async () => {
      const which = part.value, bones = KO.partBones(which);
      const src = multi && all.checked ? this.store.project.sims : [this.store.sim(simId)];
      const sims = src.filter(Boolean).map(s => {
        const v = this.simViews.get(s.id);
        this._base({ sim: s, v }, this.store.frame);
        // the hand-posed face comes along (a pose from My poses brings its face)
        const fb = from ? from.faceBones : K.keyedFace(this, s, this.store.frame);
        const key = this.currentKey(s);
        let pose = from && from.pose ? clone(from.pose) : this._bodyPose(v);
        if (which === 'face') pose = { rot: {}, pos: {} };
        else if (bones) pose = KO.maskPose(pose, bones, { keepHipPlace: true });
        const out = { gender: s.gender, pose };
        if (KO.partHasFace(which)) {
          if (fb && (Object.keys(fb.rot || {}).length || Object.keys(fb.pos || {}).length)) out.faceBones = clone(fb);
          if (key && key.face && Object.keys(key.face).length) out.face = { ...key.face };
        }
        return out;
      });
      this.applyPoses();
      const now = Date.now();
      const pr = { id: uid('mp'), label: name.value.trim() || (which === 'all' ? 'My pose' : `My ${parts.find(x => x[0] === which)[1].toLowerCase()}`), group: sims.length > 1 ? 'couple' : 'solo', sims, created: now, updated: now };
      if (which !== 'all') pr.part = which;
      const fo = folder.value.trim();
      if (fo) pr.folder = fo.slice(0, 40);
      try { this._setMyPoses(await this._changeMyPoses(list => [...list, pr])); }
      catch (err) { toast('Could not save the pose: ' + err.message, 'err'); return false; }
      this.thumbs.queue(this.posePresets.filter(x => x.id === pr.id), () => this.renderStep());
      this._poseMode = 'mine';
      this.refreshPanels();
      toast(`Saved to My poses${pr.folder ? ` (${pr.folder})` : ''}.`, 'ok');
    } }] });
    setTimeout(() => name.focus(), 30);
  }

  // Change one of My poses (rename, folder, favourite) - the server list is read, changed and written back.
  async updateMyPose(id, patch, doneText = '') {
    try { this._setMyPoses(await this._changeMyPoses(list => list.map(x => (x.id === id ? { ...x, ...patch, updated: Date.now() } : x)))); }
    catch (err) { toast('Could not change the pose: ' + err.message, 'err'); return false; }
    const pr = (this.posePresets || []).find(x => x.id === id);
    if (pr) this.thumbs.queue([pr], () => { if (this.step === 'pose') this.renderStep(); });
    this.refreshPanels();
    if (doneText) toast(doneText, 'ok');
    return true;
  }

  setMyPoseFolder(id) {
    const pr = (this.posePresets || []).find(x => x.mine && x.id === id);
    if (!pr) return;
    const folders = [...new Set((this.posePresets || []).filter(x => x.mine && x.folder).map(x => x.folder))];
    const listId = 'mp-folders-' + Date.now().toString(36);
    const inp = h('input', { class: 'text', value: pr.folder || '', placeholder: 'No folder', list: listId });
    modal({ title: 'Put it in a folder', body: h('label', { class: 'field' }, h('span', {}, 'Folder'), inp, h('datalist', { id: listId }, folders.map(f => h('option', { value: f })))),
      buttons: [{ label: 'Cancel', kind: 'ghost' }, { label: 'OK', kind: 'primary', onClick: () => this.updateMyPose(id, { folder: inp.value.trim().slice(0, 40) || undefined }, inp.value.trim() ? `"${pr.label}" is in ${inp.value.trim()} now.` : `"${pr.label}" is in no folder now.`) }] });
    setTimeout(() => { inp.focus(); inp.select(); }, 30);
  }

  // A ready pose (from your animations) copied into My poses, where it can be renamed and put in folders.
  async copyPoseToMine(pr) {
    const now = Date.now();
    const copy = { id: uid('mp'), label: pr.label, group: pr.group || (pr.sims.length > 1 ? 'couple' : 'solo'), sims: clone(pr.sims).map(s => ({ gender: s.gender, pose: s.pose, ...(s.face ? { face: s.face } : {}), ...(s.faceBones ? { faceBones: s.faceBones } : {}) })), created: now, updated: now };
    if (pr.part) copy.part = pr.part;
    try { this._setMyPoses(await this._changeMyPoses(list => [...list, copy])); }
    catch (err) { toast('Could not save the pose: ' + err.message, 'err'); return; }
    this.thumbs.queue(this.posePresets.filter(x => x.id === copy.id), () => this.renderStep());
    this.refreshPanels();
    toast(`"${pr.label}" copied to My poses.`, 'ok');
  }

  // Right-click a pose tile (spec_editing 11.1).
  poseMenu(pr, x, y) {
    const n = this.timeline.sel.size;
    const partItems = [['upper', 'Upper body'], ['lower', 'Lower body'], ['hands', 'Hands'], ['face', 'Face']]
      .map(([m, t]) => ({ label: `Use only: ${t}`, icon: m === 'face' ? 'face' : 'pose', onClick: () => this.applyPosePreset(pr, { mask: m }) }));
    contextMenu(x, y, [
      { heading: pr.label },
      { label: 'Use this pose', icon: 'pose', onClick: () => this.applyPosePreset(pr) },
      { label: 'Use it mirrored', icon: 'mirror', onClick: () => this.applyPosePreset(pr, { flipped: true }) },
      ...(pr.part && pr.part !== 'all' ? [] : partItems),
      n ? { label: `Put it on the ${n} selected key${n > 1 ? 's' : ''}`, icon: 'key', onClick: () => this.applyPosePreset(pr, { toSelected: true }) } : null,
      '-',
      ...(pr.mine ? [
        { label: 'Rename…', icon: 'tag', onClick: () => this.renameMyPose(pr.id) },
        { label: 'Folder…', icon: 'folder', onClick: () => this.setMyPoseFolder(pr.id) },
        { label: pr.fav ? '★ Not a favourite any more' : '★ Favourite', icon: 'spark', onClick: () => this.updateMyPose(pr.id, { fav: pr.fav ? undefined : true }, pr.fav ? '' : `"${pr.label}" is a favourite (★).`) },
        '-',
        { label: 'Delete', danger: true, icon: 'trash', onClick: () => this.deleteMyPose(pr.id) },
      ] : [
        { label: 'Save a copy to My poses', icon: 'save', onClick: () => this.copyPoseToMine(pr) },
      ]),
    ].filter(Boolean));
  }

  // "Share my poses": My poses as a file (My poses.json) to give to a friend.
  exportPoses() {
    const mine = (this.posePresets || []).filter(x => x.mine).map(({ mine, ...rest }) => rest);
    if (!mine.length) return toast('Save a pose to My poses first.');
    const blob = new Blob([JSON.stringify({ kind: 'Wicked Animator poses', version: 1, poses: mine }, null, 1)], { type: 'application/json' });
    const a = h('a', { href: URL.createObjectURL(blob), download: 'My poses.json', style: { display: 'none' } });
    document.body.append(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
    toast(`${this._plural(mine.length, 'pose')} saved as "My poses.json" (in your Downloads). Anyone can add them with "Add poses from a file".`, 'ok');
  }

  // "Add poses from a file": poses someone shared (My poses.json) join My poses, with new ids.
  pickPosesFile() {
    const inp = h('input', { type: 'file', accept: '.json,application/json', style: { display: 'none' } });
    inp.onchange = () => { const f = inp.files && inp.files[0]; inp.remove(); if (f) this.importPoses(f); };
    document.body.append(inp);
    inp.click();
  }
  async importPoses(file) {
    let data;
    try { data = JSON.parse(await file.text()); } catch { return toast('That file is not a poses file.', 'err'); }
    const list = Array.isArray(data) ? data : data && Array.isArray(data.poses) ? data.poses : [];
    const okPose = x => x && typeof x === 'object' && x.rot && typeof x.rot === 'object' && Object.values(x.rot).every(q => Array.isArray(q) && q.length === 4 && q.every(Number.isFinite));
    const valid = list.filter(x => x && Array.isArray(x.sims) && x.sims.length && x.sims.length <= 6 && x.sims.every(s => s && okPose(s.pose)));
    if (!valid.length) return toast('No poses found in that file.', 'err');
    const now = Date.now();
    const parts = new Set(['all', 'upper', 'lower', 'hands', 'L hand', 'R hand', 'face']);
    const add = valid.map(x => {
      const o = { id: uid('mp'), label: String(x.label || 'Pose').slice(0, 60), group: x.sims.length > 1 ? 'couple' : 'solo', created: now, updated: now,
        sims: x.sims.map(s => ({ gender: ['MALE', 'FEMALE', 'BOTH'].includes(s.gender) ? s.gender : 'BOTH', pose: { rot: s.pose.rot, pos: s.pose.pos && typeof s.pose.pos === 'object' ? s.pose.pos : {} },
          ...(s.face && typeof s.face === 'object' ? { face: s.face } : {}), ...(s.faceBones && typeof s.faceBones === 'object' ? { faceBones: s.faceBones } : {}) })) };
      if (x.part && parts.has(x.part) && x.part !== 'all') o.part = x.part;
      if (x.folder) o.folder = String(x.folder).slice(0, 40);
      if (x.fav) o.fav = true;
      return o;
    });
    try { this._setMyPoses(await this._changeMyPoses(l => [...l, ...add])); }
    catch (err) { return toast('Could not add the poses: ' + err.message, 'err'); }
    this.thumbs.queue(add.map(a => this.posePresets.find(x => x.id === a.id)).filter(Boolean), () => this.renderStep());
    this._poseMode = 'mine';
    this.refreshPanels();
    toast(`${this._plural(add.length, 'pose')} added to My poses.`, 'ok');
  }

  // ---------------------------------------------------------------- motion layers
  addLayer(simId, type) {
    const s = this.store.sim(simId);
    this.store.checkpoint('Add motion');
    const l = newLayer(type);
    if (!s.layers) s.layers = [];
    // match the partner's rhythm straight away
    const partner = this.store.project.sims.find(x => x.id !== simId && (x.layers || []).some(y => y.on));
    if (partner && l.params.strokes !== undefined) {
      const pl = partner.layers.find(y => y.on);
      if (pl.params.strokes !== undefined) { l.params.strokes = pl.params.strokes; l.phase = pl.phase || 0; }
      // both hips moving: they share one stroke, so neither pulls all the way out
      if (MOTIONS[type].group === 'Hips' && MOTIONS[pl.type]?.group === 'Hips' && l.params.distance !== undefined) {
        l.params.distance = Math.round(l.params.distance * 0.6 * 2) / 2;
        if (pl.params.distance !== undefined) pl.params.distance = Math.round(Math.min(pl.params.distance, MOTIONS[pl.type].params.distance * 0.6) * 2) / 2;
      }
    }
    s.layers.push(l);
    this._openLayer = l.id;
    this._justPicked = type;
    this.layersChanged(true);
    this.refreshPanels();
    // bring the new motion's sliders into view (the toast below points at them)
    // (only the step panel scrolls - scrollIntoView would also nudge the whole page)
    requestAnimationFrame(() => {
      const body = $('panel-body'), card = body.querySelector('.layer.open');
      if (card) body.scrollTo({ top: body.scrollTop + card.getBoundingClientRect().top - body.getBoundingClientRect().top - 6, behavior: 'smooth' });
    });
    if (!this.playing) this.setPlaying(true);
    toast(`${MOTIONS[type].label} added to ${s.label}. It's playing - tune it with the sliders.`, 'ok');
  }

  removeLayer(simId, id) {
    const s = this.store.sim(simId);
    this.store.checkpoint('Remove motion');
    s.layers = s.layers.filter(l => l.id !== id);
    this.layersChanged(true);
    this.refreshPanels();
  }

  syncLayer(simId, id) {
    const s = this.store.sim(simId), l = s.layers.find(x => x.id === id);
    const partner = this.store.project.sims.find(x => x.id !== simId && (x.layers || []).some(y => y.on));
    if (!partner) return;
    const pl = partner.layers.find(y => y.on);
    this.store.checkpoint('Match the partner');
    l.params.strokes = pl.params.strokes ?? l.params.strokes;
    l.phase = pl.phase || 0;
    this.layersChanged(true);
    this.refreshPanels();
    toast(`${s.label} now meets ${partner.label} on every stroke.`, 'ok');
  }

  // Turn a motion into ordinary keys (to fine-tune stroke by stroke). Faces and other motions are kept.
  // Every frame of the motion is worked out exactly as it plays, then keys are placed only where they are needed
  // to follow it closely (more around a hard hit, fewer in slow parts), joined by straight (linear) in-betweens.
  // A hand motion runs after the pins (as it does when it plays); its hand's pin is taken off, because the
  // keys now say where that hand goes.
  bakeLayer(simId, id) {
    const s = this.store.sim(simId), l = s && (s.layers || []).find(x => x.id === id), v = this.simViews.get(simId);
    if (!s || !l || !v) return;
    const p = this.store.project, L = p.length;
    if (this.playing) this.setPlaying(false);
    this.store.checkpoint('Motion to keys');
    const hand = MOTIONS[l.type]?.group === 'Hands';
    const limb = hand ? (l.params.limb || MOTIONS[l.type].params.limb) : null;
    const chain = hand ? (LIMBS[limb] || []) : [];
    const savedEditing = this.pipeline.editing;
    this.pipeline.editing = null;
    this.pipeline.overrides.delete(simId);
    const all = this.pipeline.entries();
    const me = all.find(e => e.sim.id === simId);
    const others = all.filter(e => e !== me);
    const old = s.keys.map(k => ({ ...k }));
    const oldBody = old.filter(k => !k.faceOnly);
    const poses = [];
    try {
      for (let f = 0; f < L; f++) {
        // (both passes of the pipeline when it has two: hand motions run in the second one)
        const whole = e => (typeof this.pipeline.one === 'function' ? this.pipeline.one(e, f, all) : this.pipeline.body(e, f, all));
        for (const o of others) whole(o);                              // the partners at this frame (for "along the penis")
        let live = null;
        if (hand) {
          whole(me);                                                 // keys, motions, pins, then the hand motion
          live = chain.map(n => v.bone(n) && v.bone(n).quaternion.toArray());
        }
        v.resetPose();
        const keyed = evaluate(oldBody, f, L, p.loop, p.autoCurve);
        if (keyed) v.setPose(keyed);
        if (!hand) applyLayer(v, l, { frame: f, length: L, others });
        const pose = this._bodyPose(v);
        if (hand) chain.forEach((n, i) => { if (live[i]) pose.rot[n] = live[i]; });
        for (const [n, q] of Object.entries(pose.rot)) { const l = Math.hypot(q[0], q[1], q[2], q[3]) || 1; pose.rot[n] = q.map(x => x / l); }
        poses.push(pose);
      }
    } finally { this.pipeline.editing = savedEditing; }
    // the body gets new keys; the face channel (sliders and face bones) stays exactly as it was, on the new key at
    // its frame or on a face key there
    const frames = K.keyFramesFor(poses, null, !!p.loop);
    const keys = frames.map(f => ({ frame: f, ease: 'linear', pose: poses[f] }));
    for (const k of old) {
      if (!k.face && !k.faceBones) continue;
      let nk = keys.find(x => x.frame === k.frame);
      if (!nk) { nk = { frame: k.frame, ease: k.ease || 'auto', faceOnly: true, pose: poses[Math.min(poses.length - 1, k.frame)] || poses[0] }; keys.push(nk); }
      if (k.face) nk.face = { ...k.face };
      if (k.faceBones) nk.faceBones = clone(k.faceBones);
    }
    s.keys = sortKeys(keys);
    s.layers = s.layers.filter(x => x !== l);
    if (hand && s.pins && s.pins[limb]) delete s.pins[limb];
    this.refreshAll();
    this.interact.refreshHandles();
    this.physicsChanged();
    toast(`${MOTIONS[l.type].label} turned into ${frames.length} keys you can edit.`, 'ok');
  }

  // ---------------------------------------------------------------- face
  // Sliders and expressions. Where there is no key, a face key is made (it never bends the body's motion).
  setFace(simId, patch, labelText, merge = false, done = true, pickId = null) {
    const s = this.store.sim(simId);
    const frame = Math.round(this.store.frame);
    if (labelText) this.store.checkpoint(`${labelText} face`);
    let key = s.keys.find(k => k.frame === frame);
    if (!key) {
      const v = this.simViews.get(simId);
      this._base({ sim: s, v }, frame);
      key = { frame, ease: this._defaultEase(), faceOnly: true, pose: this._bodyPose(v) };
      s.keys.push(key); sortKeys(s.keys);
      this.timeline.flash(simId, frame, 'add');
      this.emit('keyed', { simId, frame, kind: 'face' });
    }
    key.face = merge ? { ...(key.face || {}), ...patch } : { ...patch };
    if (pickId) this._justPicked = pickId;
    this._edited();
    this.applyPoses(false);
    this.timeline.draw();
    this.store.setDirty(true);
    if (done) { this.renderStep(); renderInspector(this); }
    if (labelText) toast(`${labelText} face on ${s.label} at ${(frame / 30).toFixed(2)} s.`, 'ok');
  }

  // The face key at this frame for a sim (made as a face key when there is none). -> the key
  _faceKeyAt(sim, frame) {
    let key = sim.keys.find(k => k.frame === frame);
    if (!key) {
      const v = this.simViews.get(sim.id);
      this._base({ sim, v }, frame);
      key = { frame, ease: this._defaultEase(), faceOnly: true, pose: this._bodyPose(v) };
      sim.keys.push(key); sortKeys(sim.keys);
      this.timeline.flash(sim.id, frame, 'add');
      this.emit('keyed', { simId: sim.id, frame, kind: 'face' });
    }
    return key;
  }

  // The inspector's face rows: one axis of a face part (metres or radians from rest), inside the keyed face.
  setFaceBoneAxis(simId, name, kind, axis, value, commit) {
    const v = this.simViews.get(simId);
    if (!v || !v.bone(name)) return;
    this.beginEdit(simId);
    const b = K.baseOf(v, name), rest = v.restByName[name];
    if (kind === 'move') {
      const off = b.p.clone().sub(rest.pos);
      off[axis] = value;
      K.setBase(v, name, null, rest.pos.clone().add(off));
    } else {
      const e = new THREE.Euler().setFromQuaternion(rest.quat.clone().invert().multiply(b.q), 'XYZ');
      e[axis] = value;
      K.setBase(v, name, rest.quat.clone().multiply(new THREE.Quaternion().setFromEuler(e)), null);
    }
    if (this.mirrorEdit) this.mirrorLive(simId, name);
    this.poseEdited(simId, !commit, 'face');
    if (commit) this.afterEdit();
  }

  // Both eyes look at the partner's face, at the camera, or straight ahead.
  aimEyes(simId, at = 'partner') {
    const sim = this.store.sim(simId), v = this.simViews.get(simId);
    if (!sim || !v) return;
    this.store.checkpoint('Aim the eyes');
    this.beginEdit(simId);
    v.group.updateMatrixWorld(true);
    const eyes = ['b__L_Eye__', 'b__R_Eye__'].filter(n => v.bone(n));
    if (at === 'ahead') {
      for (const n of eyes) K.setBase(v, n, v.restByName[n].quat.clone(), null);
    } else {
      let target = null;
      if (at === 'camera') target = this.vp.camera.position.clone();
      else {
        // the partner: the other sim whose head is nearest, 8 cm out in front of its face
        const me = v.bone('b__Head__').getWorldPosition(new THREE.Vector3());
        let best = Infinity;
        for (const [id, w] of this.simViews) {
          if (id === simId || !w.group.visible || !w.bone('b__Head__')) continue;
          w.group.updateMatrixWorld(true);
          const hd = w.bone('b__Head__'), hp = hd.getWorldPosition(new THREE.Vector3());
          const d = hp.distanceTo(me);
          if (d < best) { best = d; target = hp.add(new THREE.Vector3(0, 1, 0).applyQuaternion(hd.getWorldQuaternion(new THREE.Quaternion())).multiplyScalar(0.08)); }
        }
        if (!target) { toast('There is no partner to look at.'); return; }
      }
      for (const n of eyes) K.aimEye(v, n, target);
    }
    this.poseEdited(simId, false, 'face');
    this.afterEdit();
    toast(at === 'ahead' ? `${sim.label} looks ahead.` : `${sim.label} looks at the ${at === 'camera' ? 'camera' : 'partner'}.`, 'ok');
  }

  // "Make this expression editable": the slider expression at a key becomes face bones (dots you can move one by
  // one). all: every key of the sim that has a face. Everything is worked out first, then written.
  bakeFace(simId, { all = false } = {}) {
    const sim = this.store.sim(simId), v = this.simViews.get(simId);
    if (!sim || !v) return;
    const p = this.store.project, f = Math.round(this.store.frame);
    const targets = all ? sim.keys.filter(k => k.face || k.faceBones) : sim.keys.filter(k => k.frame === f && k.face && Object.keys(k.face).length);
    if (!targets.length) { toast('There is no expression here to turn into face dots.'); return; }
    this.store.checkpoint('Make the expression editable');
    const results = [];
    const saved = this.pipeline.editing;
    try {
      // exactly as the pipeline shows the sliders (the project's face style, the safety clamp)
      const style = PipeMod.faceStyleOf ? PipeMod.faceStyleOf(p) : undefined;
      for (const k of targets) {
        v.resetPose();
        K.setFaceBones(v, K.evaluateFaceBones(sim.keys, k.frame, p.length, p.loop));
        FaceMod.applyFace(v, evaluateFace(sim.keys, k.frame, p.length, p.loop), style);
        if (style !== 'classic' && FaceMod.clampFace) FaceMod.clampFace(v);
        results.push([k, K.getFaceBones(v, { withLayer: true })]);
      }
    } finally { this.pipeline.editing = saved; }
    for (const [k, fb] of results) k.faceBones = fb;
    if (all) for (const k of sim.keys) delete k.face;
    else for (const k of targets) k.face = {};
    this.applyPoses();
    this.afterEdit();
    this.renderStep();
    toast('Expression turned into face bones - click the dots to adjust it.', 'ok');
  }

  copyFace(simId) {
    const sim = this.store.sim(simId);
    if (!sim) return;
    const p = this.store.project, f = Math.round(this.store.frame);
    const key = sim.keys.find(k => k.frame === f);
    const face = (key && key.face) || evaluateFace(sim.keys, f, p.length, p.loop);
    const fb = K.keyedFace(this, sim, f);
    this.faceClipboard = { face: face ? { ...face } : null, faceBones: fb ? clone(fb) : null };
    toast('Face copied.');
    this.refreshPanels();
  }

  pasteFace(simId) {
    const sim = this.store.sim(simId), c = this.faceClipboard;
    if (!sim || !c) return toast('Copy a face first.');
    this.store.checkpoint('Paste face');
    const key = this._faceKeyAt(sim, Math.round(this.store.frame));
    if (c.face) key.face = { ...c.face }; else delete key.face;
    key.faceBones = c.faceBones ? clone(c.faceBones) : { rot: {}, pos: {} };
    this.applyPoses();
    this.afterEdit();
    toast(`Face pasted on ${sim.label}.`, 'ok');
  }

  // The face at this frame, left <-> right (the middle of the mouth stays in the middle).
  mirrorFace(simId) {
    const sim = this.store.sim(simId), v = this.simViews.get(simId);
    if (!sim || !v) return;
    this.store.checkpoint('Mirror face');
    this.beginEdit(simId);
    this._mirrorFaceIn(v);
    const key = this._faceKeyAt(sim, Math.round(this.store.frame));
    key.faceBones = K.getFaceBones(v);
    // the sliders' one-sided channels swap too
    if (key.face) for (const c of ['wink', 'smileSide', 'browSide', 'jawSide', 'lookSide']) if (typeof key.face[c] === 'number') key.face[c] = -key.face[c];
    this.applyPoses();
    this.afterEdit();
    toast('Face mirrored.', 'ok');
  }

  // Every face part back to rest at this frame (the sliders stay).
  resetFace(simId) {
    const sim = this.store.sim(simId);
    if (!sim) return;
    this.store.checkpoint('Reset face');
    const key = this._faceKeyAt(sim, Math.round(this.store.frame));
    key.faceBones = { rot: {}, pos: {} };
    const ov = this.pipeline.overrides.get(simId);
    if (ov) delete ov.faceBones;
    this.applyPoses();
    this.afterEdit();
    toast('Face parts back to rest here.', 'ok');
  }

  // A row in the bone list was clicked: face bones open the Face tool, other bones the Pose tool.
  selectBoneByName(simId, name) {
    const sim = this.store.sim(simId), v = this.simViews.get(simId);
    if (!sim || !v || !v.bone(name)) return;
    this.store.selected = { sim: simId, bone: name };
    if (K.isFace(name)) {
      if (this.interact.tool !== 'face') this.setTool('face');
      this.interact.selectFaceBone(simId, name);
    } else {
      if (this.interact.tool !== 'rotate') this.setTool('rotate');
      this.interact.selectBone(simId, name);
    }
    this.emitSelection();
  }

  // The bone under the mouse in the 3D view: its row in the bone list lights up.
  setHotBone(name) {
    if (this._hotBone === name) return;
    this._hotBone = name;
    document.querySelectorAll('#bone-list .bone-row.hot').forEach(r => r.classList.remove('hot'));
    if (name) { const r = document.querySelector(`#bone-list .bone-row[data-bone="${name}"]`); if (r) r.classList.add('hot'); }
  }

  // ---------------------------------------------------------------- sounds
  autoSounds() {
    const n = autoSounds(this);
    this.afterEdit();
    toast(n ? `Placed ${n} sounds from the bodies' contacts - they're on the timeline.` : 'No hits or strokes found - animate some contact first.', n ? 'ok' : '');
  }

  addSoundDialog(simId) { openAddSoundDialog(this, simId); }

  removeSound(simId, snd) {
    this.store.checkpoint('Remove sound');
    const s = this.store.sim(simId);
    s.sounds = s.sounds.filter(x => x !== snd);
    this.afterEdit();
  }

  // The voice lines a sim can use for a kind of voice: the game's voice lines of its own body's adult voice only.
  voicePool(sim, set) {
    const rx = (VOICE_SETS.find(x => x[0] === set) || VOICE_SETS[VOICE_SETS.length - 1])[2];
    const want = simVoiceCode(sim);
    return (this.sounds || []).filter(x => x.kind === 'voice' && voiceCode(x.name) === want && rx.test(x.name))
      .sort((a, b) => (a.source === 'mods' ? 0 : 1) - (b.source === 'mods' ? 0 : 1) || b.count - a.count).slice(0, 12);
  }

  // [set, label, how many lines] for the sets this sim has lines for.
  voiceSets(sim) { return VOICE_SETS.map(([id, t]) => [id, t, this.voicePool(sim, id).length]).filter(x => x[2] > 0); }

  randomVoices(simId, set, everySeconds, { quiet = false } = {}) {
    const s = this.store.sim(simId), p = this.store.project;
    if (!s) return 0;
    // a kind with no lines for this sim falls back to a broader one (soft moans -> moans -> any voice)
    let used = null, pool = [];
    for (const k of VOICE_FALLBACK[set] || ['any']) { pool = this.voicePool(s, k); if (pool.length) { used = k; break; } }
    if (!pool.length) {
      if (!quiet) toast(`No ${s.frame === 'ym' ? 'male' : 'female'} voice lines in your sound list.`);
      return 0;
    }
    this.store.checkpoint();
    s.sounds = (s.sounds || []).filter(x => !(x.auto && x.kind === 'voice'));
    const n = Math.max(1, Math.round(p.length / p.fps / everySeconds));
    let seed = 7;
    const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
    for (let k = 0; k < n; k++) {
      const frame = Math.round(((k + 0.2 + rnd() * 0.6) / n) * p.length) % p.length;
      const snd = pool[Math.floor(rnd() * pool.length)];
      s.sounds.push({ frame, name: snd.name, kind: 'voice', auto: true });
    }
    this.afterEdit();
    if (!quiet) {
      const setName = (VOICE_SETS.find(x => x[0] === used) || [])[1] || '';
      toast(`${n} voice sound${n > 1 ? 's' : ''} added to ${s.label}${used !== set ? ` (${setName.toLowerCase()} - there were none of the kind you picked)` : ''} - the mouth moves with them.`, 'ok');
    }
    return n;
  }

  // ---------------------------------------------------------------- ghosts and trails
  // Ghosts: see-through copies of the selected sim at the keys before and after this frame. Two ghost sims are
  // made once and only re-posed, and they are hidden while playing or previewing a library animation.
  // Ghosts (onion skin): see-through copies of the selected sim. onionMode 'keys': the keys before and after this frame
  // (the default); 'frames': every 3 frames, 2 before and 2 after, fading with the distance (motions included);
  // 'partner': the keys before and after, and the partner posed at those frames too. Ghost sims are made once per
  // slot (at most 4) and only re-posed; they are hidden while playing or previewing a library animation.
  updateGhosts() {
    const sim = this.store.sim();
    const on = this.onion && !this.playing && !this.preview && sim;
    if (!on) {
      for (const g of this.ghosts) g.group.visible = false;
      this._ghostKey = '';
      return;
    }
    const p = this.store.project, L = p.length;
    const f = Math.round(this.store.frame);
    const mode = this.onionMode || 'keys';
    const body = sim.keys.filter(k => !k.faceOnly);          // face keys have no body pose of their own
    const prev = [...body].reverse().find(k => k.frame < f), next = body.find(k => k.frame > f);
    const plan = [];
    if (mode === 'frames') {
      for (const d of [-6, -3, 3, 6]) {
        let g = f + d;
        if (p.loop) g = ((g % L) + L) % L; else if (g < 0 || g > L - 1) continue;
        plan.push({ sim, frame: g, alpha: Math.abs(d) === 3 ? 0.22 : 0.11, color: d < 0 ? '#ff8ab8' : '#8fb4ff', motion: true });
      }
    } else {
      if (prev) plan.push({ sim, pose: prev.pose, alpha: 0.2, color: '#ff8ab8' });
      if (next) plan.push({ sim, pose: next.pose, alpha: 0.2, color: '#8fb4ff' });
      if (mode === 'partner') {
        const partner = p.sims.find(s => s.id !== sim.id && s.visible !== false);
        if (partner) for (const [key, color] of [[prev, '#ff8ab8'], [next, '#8fb4ff']]) if (key) plan.push({ sim: partner, frame: key.frame, alpha: 0.13, color });
      }
    }
    const bodyOf = s => (s.tray && this.assets.bodies['tray:' + s.id] ? 'tray:' + s.id : s.frame);
    const keyStr = `${mode}|${sim.id}|${f}|${this.editRev}|${plan.map(x => `${x.sim.id}:${bodyOf(x.sim)}:${x.frame ?? 'k'}`).join(',')}|${mode === 'keys' ? JSON.stringify([prev ? prev.pose : 0, next ? next.pose : 0]) : ''}`;
    if (keyStr === this._ghostKey) return;
    this._ghostKey = keyStr;
    plan.forEach((x, i) => {
      const bk = bodyOf(x.sim);
      let g = this.ghosts[i];
      if (g && g._bodyKey !== bk) { this.disposeView(g); g = null; }
      if (!g) {
        g = new Sim(this.assets.rig, this.assets.bodies[bk] || this.assets.bodies.yf, { skin: x.color });
        g._bodyKey = bk;
        g.material.transparent = true; g.material.depthWrite = false;
        g.meshes.forEach(m => { m.castShadow = false; m.raycast = () => {}; });
        this.vp.sims.add(g.group);
        this.ghosts[i] = g;
      }
      g.setSkin(x.color);
      g.material.opacity = x.alpha;
      g.group.visible = true;
      g.resetPose();
      const pose = x.pose || evaluate(x.sim.keys, x.frame, L, p.loop, p.autoCurve);
      if (pose) g.setPose(pose);
      if (x.motion) for (const l of (x.sim.layers || []).filter(y => y.on)) { try { applyLayer(g, l, { frame: x.frame, length: L, others: [] }); } catch { /* shown without it */ } }
    });
    for (let i = plan.length; i < this.ghosts.length; i++) if (this.ghosts[i]) this.ghosts[i].group.visible = false;
  }

  updateTrail() {
    clearTimeout(this._trailT);
    if (!this.trail) { this.vp.setTrail(null); return; }
    this._trailT = setTimeout(() => {
      const sim = this.store.sim();
      if (!sim) return this.vp.setTrail(null);
      const v = this.simViews.get(sim.id);
      if (!v) return this.vp.setTrail(null);
      const bone = this.store.selected.bone || 'b__Pelvis__';
      const p = this.store.project, pts = [];
      const saved = this.pipeline.editing; this.pipeline.editing = null;
      const pending = new Map(this.pipeline.overrides); this.pipeline.overrides.clear();   // the path of the keyed animation
      try {
        for (let f = 0; f < p.length; f++) {
          this.pipeline.apply(f, { physics: false });
          v.group.updateMatrixWorld(true);
          pts.push(v.worldPos(bone));
        }
      } finally {
        this.pipeline.editing = saved;
        for (const [k, x] of pending) this.pipeline.overrides.set(k, x);
      }
      this.applyPoses(false);
      this.vp.setTrail(pts, sim.keys.map(k => k.frame), sim.color);
    }, 120);
  }

  // ---------------------------------------------------------------- files
  // A name no other saved animation uses ("Cowgirl 1" -> "Cowgirl 2", "Kiss" -> "Kiss 2").
  _freeName(name, list) {
    const taken = new Set(list.map(m => (m.file || '').toLowerCase()));
    const m = /^(.*?)(?:\s+(\d+))?$/.exec((name || 'Untitled animation').trim());
    const base = m[1] || 'Animation';
    for (let n = m[2] ? +m[2] + 1 : 2; n < 1000; n++) {
      const c = `${base} ${n}`;
      if (!taken.has(projectFileName(c).toLowerCase())) return c;
    }
    return `${base} ${Date.now() % 10000}`;
  }

  // Another animation (not this one) is saved under the same file name: replace it, or keep both.
  async _askNameClash(p, clash, list) {
    const free = this._freeName(p.name, list);
    const pick = await choiceBox('That name is already used',
      `"${clash.name || p.name}"${clash.author ? ' by ' + clash.author : ''} is a different animation saved under the same name. Keep both by saving this one as "${free}", or replace the other one? (A replaced animation is kept in a backup folder, never deleted.)`,
      [{ label: 'Cancel', kind: 'ghost', value: null }, { label: 'Replace it', kind: 'danger', value: 'replace' }, { label: `Save as "${free}"`, kind: 'primary', value: 'rename' }]);
    if (pick === 'rename') { p.name = free; this.refreshTitle(); if (this.step === 'details') this.renderStep(); }
    return pick;
  }

  async save() {
    const p = this.store.project;
    // The server never writes over a different animation (it would keep both, this one as "Name (2)"), so the
    // question is asked here first, with the same file-name rule the server uses.
    let list = null;
    try { list = await api.projects(); } catch { /* the list could not be read - the server still keeps both */ }
    if (list) {
      const file = projectFileName(p.name).toLowerCase();
      const clash = list.find(m => (m.file || '').toLowerCase() === file && m.uid !== p.uid);
      if (clash) {
        const pick = await this._askNameClash(p, clash, list);
        if (!pick) return false;
        if (pick === 'replace') {
          // the other animation leaves your list (moved to animator_replaced), then this one takes its name
          try { await api.removeProject(clash.file); }
          catch (err) { toast('Could not replace it: ' + err.message, 'err'); return false; }
        }
      }
    }
    try { p.thumb = this.vp.snapshot(); } catch { /* no thumbnail */ }
    this.runHook('beforeSave', p);
    try {
      const res = await api.saveProject(p);
      // the server says which file it used (and the name, if it had to pick another one)
      if (res && res.name && res.name !== p.name) { p.name = res.name; this.refreshTitle(); }
      this._file = (res && (res.file || res.saved)) || projectFileName(p.name);
      this.store.setDirty(false);
      this._recoveryRev = null;
      this._clearRecovery();
      this.shareData = null;             // the Share step reads the list again
      // another animation took the name after the check above: the server kept both, this one as "Name (2)"
      if (res && res.renamed) toast(`Saved as "${this._file}" - another animation already has this name.`, 'ok');
      else toast(`Saved "${p.name}".`, 'ok');
      this.emit('saved', { file: this._file, name: p.name });
      return true;
    } catch (err) { toast('Could not save: ' + err.message, 'err'); return false; }
  }

  open() { openProjectDialog(this); }

  // from: the element that was clicked (a Home card's picture grows into the stage)
  async loadProject(name, { from = null } = {}) {
    let p;
    try { p = await api.project(name); }
    catch (err) { toast('Could not open it: ' + err.message, 'err'); return false; }
    this.store.load(p);
    this._file = name;
    this.playRange = null;
    this._lastPreset = null;
    this.shareData = null;
    this._clearRecovery();
    this.pipeline.overrides.clear();
    this.refreshAll();
    this.timeline.fit();
    this.pipeline.simulateIfNeeded(true);
    hideHome(this, { from });
    this.frameSims({ fromFront: true });
    this._projectLoaded();
    toast(`Opened "${p.name}".`, 'ok');
    return true;
  }

  exportDialog() { openExportDialog(this); }

  // Parts in the act, for WickedWhims: a sim with a penis (or cast as male) gives, the others receive.
  roleOf(s) {
    if (s.role === 'giver' || s.role === 'receiver' || s.role === 'both') return s.role;
    return s.frame === 'ym' || s.frame === 'yf_futa' || s.gender === 'MALE' ? 'giver' : 'receiver';
  }

  // Bare feet in the game: on for footjobs and on beds and sofas, unless changed in Details.
  bareFeetOf(s, p = this.store.project) {
    if (typeof s.bareFeet === 'boolean') return s.bareFeet;
    return p.category === 'FOOTJOB' || (p.locations || []).some(l => BED_OR_SOFA.test(l)) || /bed|sofa|loveseat/.test(p.furniture || '');
  }

  // Does the mouth move (so the game must not lip-sync over it), and is the tongue used? Only needed when the
  // engine did not say (pipeline.bake().flags).
  _mouthFlags(s, log, v) {
    const b = simBody(s);
    const faces = s.keys.map(k => k.face).filter(Boolean);
    // a mouth bone posed by hand, in the body keys (old projects) or in the face keys (turned or moved)
    const moved = n => {
      const k = v ? v.index(n) : -1;
      if (k < 0) return false;
      const rest = v.rest[k].quat, rp = v.rest[k].pos;
      return s.keys.some(key => [key.pose, key.faceBones].some(src => {
        const q = src && src.rot && src.rot[n], t = src && src.pos && src.pos[n];
        return (q && rest.angleTo(new THREE.Quaternion().fromArray(q)) > THREE.MathUtils.degToRad(3))
          || (t && Math.hypot(t[0] - rp.x, t[1] - rp.y, t[2] - rp.z) > 0.002);
      }));
    };
    const tongueUsed = b.tongue !== false && (faces.some(f => (f.tongue || 0) > 0.05) || TONGUE.some(moved));
    const mouthMoves = tongueUsed || MOUTH.some(moved) || faces.some(f => ['open', 'pout', 'bite', 'tongue'].some(k => (f[k] || 0) > 0.05))
      || (log || []).some(o => o && o.mouth && o.mouth.open > 0.05)
      || ((b.talk && b.talk.mouth) !== false && (s.sounds || []).some(x => x.kind === 'voice'));
    return { mouthMoves, tongueUsed };
  }

  // Every frame of every sim with all layers, for the game. `pipeline` and `views` bake another saved
  // animation with its own temporary sims (see bakeOther).
  bake(project = this.store.project, { pipeline = this.pipeline, views = this.simViews } = {}) {
    const p = project;
    this.runHook('beforeBake', p);
    // a pose that was never keyed (Auto key off) is not part of the animation
    const pending = new Map(pipeline.overrides);
    pipeline.overrides.clear();
    let res;
    try { res = pipeline.bake(); } finally { for (const [k, x] of pending) pipeline.overrides.set(k, x); }
    const { tracks, sims, openLog, flags } = res;
    const actors = sims.map((s, i) => {
      const v = views.get(s.id);
      const penis = s.frame === 'ym' || s.frame === 'yf_futa' || !!(v && v.hasPenis);
      const fl = (flags && flags[i]) || this._mouthFlags(s, openLog[i], v);
      return {
        gender: s.gender, naked: nakedFor(p.category, s), tracks: tracks[i], body: s.frame,
        invisibleTeeth: openLog[i].some(o => o && o.mouth && o.mouth.by === 'penis' && o.mouth.open > 0.5),
        animatedVagina: s.frame === 'yf' && simBody(s).open.on && simBody(s).open.vagina !== false,
        sounds: (s.sounds || []).map(x => ({ frame: x.frame, name: x.name, kind: x.kind })),
        mouthMoves: !!fl.mouthMoves, tongueUsed: !!fl.tongueUsed,
        bareFeet: this.bareFeetOf(s, p), role: this.roleOf(s), strapon: !penis && !!s.strapon,
      };
    });
    if (pipeline === this.pipeline) this.applyPoses(false);
    const act = (p.tags || []).includes('ANAL') ? 'ANAL' : (p.tags || []).some(t => ['BLOWJOB', 'DEEP_THROAT', 'CUNNILINGUS', 'CUM_IN_MOUTH'].includes(t)) ? 'ORALJOB' : 'VAGINAL';
    const payload = { uid: p.uid, act, name: p.name, author: p.author, category: p.category, tags: p.tags || [], next: p.next || [], loops: p.loops, naked: p.naked,
      locations: p.locations, fps: p.fps, frames: p.length, actors };
    // features may add fields (moments, props...)
    this.runHook('bake', payload, p, { pipeline, views });
    return payload;
  }

  // Bake a saved animation that is not the open one, with its own temporary sims and pipeline: the stage, the
  // selection and the rotate rings are never touched. Tray sims get their own body shape first.
  async bakeOther(project) {
    const views = new Map();
    try {
      for (const s of project.sims) {
        simBody(s);
        let body = this.assets.bodies[s.frame] || this.assets.bodies.yf;
        if (s.tray) {
          const key = 'tray:' + s.id;
          if (!this.assets.bodies[key]) { try { this.assets.bodies[key] = (await api.traySim(s.tray.id, s.tray.index)).body; } catch { /* generic body */ } }
          body = this.assets.bodies[key] || body;
        }
        views.set(s.id, new Sim(this.assets.rig, body, { color: s.color, skin: s.skin }));
      }
      const pipeline = new Pipeline({ store: { project }, simViews: views });
      return this.bake(project, { pipeline, views });
    } finally {
      for (const v of views.values()) this.disposeView(v);
    }
  }

  openTray() { openTrayDialog(this); }

  openMagic() { openMagicDialog(this); }

  // Showcase: the camera slowly circles the sims while it plays; touching the camera stops it.
  showcase(on) {
    if (this._showStep) { this.vp.onFrame.splice(this.vp.onFrame.indexOf(this._showStep), 1); this._showStep = null; }
    $('btn-showcase')?.classList.toggle('on', !!on);
    if (!on) return;
    const center = new THREE.Vector3(); let n = 0;
    for (const [, v] of this.simViews) { if (!v.group.visible) continue; v.group.updateMatrixWorld(true); center.add(v.worldPos('b__Pelvis__')); n++; }
    if (!n) return;
    center.multiplyScalar(1 / n);
    let ang = Math.atan2(this.vp.camera.position.x - center.x, this.vp.camera.position.z - center.z);
    const dist = 2.9, height = center.y + 0.55;
    const step = dt => {
      if (this.vp.controls.busy || this.vp.dragging) { this.showcase(false); return; }
      ang += dt * 0.22;
      const pos = new THREE.Vector3(center.x + Math.sin(ang) * dist, height + Math.sin(ang * 0.7) * 0.25, center.z + Math.cos(ang) * dist);
      this.vp.controls.lookFrom(this.vp.camera.position.clone().lerp(pos, Math.min(1, dt * 2.5)), center);
    };
    this._showStep = step;
    this.vp.onFrame.push(step);
  }

  // ---------------------------------------------------------------- loop length
  // Change the loop length. 'stretch': keys, sounds and moments move with it, so the same animation plays slower
  // or faster (motions keep their whole number of strokes). 'keep': everything stays at its time and the speed
  // stays the same - making it shorter cuts the end off (a pose that would be lost moves to the new last frame),
  // and motions get more or fewer strokes (still whole numbers, so it keeps looping cleanly).
  // A retime is always a deliberate length (typed by hand, or a mocap/video take stretching the project to match
  // it - capture/keys.js's applyToSim calls this the same way) - "Fit to keys" never moves it again on its own.
  _retimeProject(p, newLen, mode) {
    p.fitLength = false;
    const oldLen = p.length, r = newLen / oldLen, last = newLen - 1;
    const info = { moved: 0, lostKeys: 0, lostSounds: 0 };
    const scale = f => Math.max(0, Math.min(last, f >= oldLen - 1 ? last : Math.round(f * r)));
    for (const s of p.sims) {
      if (mode === 'stretch') {
        const byFrame = new Map();
        for (const k of sortKeys([...s.keys])) byFrame.set(scale(k.frame), { ...k, frame: scale(k.frame) });   // the later key wins
        s.keys = sortKeys([...byFrame.values()]);
        for (const snd of s.sounds || []) snd.frame = Math.max(0, Math.min(last, Math.round(snd.frame * r)));
      } else {
        const keep = s.keys.filter(k => k.frame < newLen), gone = sortKeys(s.keys.filter(k => k.frame >= newLen));
        if (gone.length) {
          if (!keep.some(k => k.frame === last)) { keep.push({ ...gone[gone.length - 1], frame: last }); info.moved++; info.lostKeys += gone.length - 1; }
          else info.lostKeys += gone.length;
        }
        s.keys = sortKeys(keep);
        const before = (s.sounds || []).length;
        s.sounds = (s.sounds || []).filter(x => x.frame < newLen);
        info.lostSounds += before - s.sounds.length;
        for (const l of s.layers || []) {
          const st = l.params && l.params.strokes !== undefined ? l.params.strokes : MOTIONS[l.type]?.params.strokes;
          if (st !== undefined) l.params.strokes = Math.max(1, Math.round(st * r));
        }
      }
    }
    // moments (cum, undress...) on the project's own track, when there are any
    if (Array.isArray(p.events)) {
      if (mode === 'stretch') for (const e of p.events) { if (typeof e.frame === 'number') e.frame = scale(e.frame); if (typeof e.end === 'number') e.end = e.end >= oldLen ? newLen : scale(e.end); }
      else {
        p.events = p.events.filter(e => typeof e.frame !== 'number' || e.frame < newLen);
        for (const e of p.events) if (typeof e.end === 'number' && e.end >= oldLen) e.end = newLen;       // "to the end" stays at the end
      }
      // an effect's end: never before its start, never past the end of the loop (spec_game 1)
      for (const e of p.events) if (typeof e.end === 'number') e.end = Math.max(typeof e.frame === 'number' ? e.frame : 0, Math.min(newLen, e.end));
    }
    // features' own tracks (the furniture's) follow the loop the same way
    this.runHook('retime', p, { oldLen, newLen, mode, scale });
    p.length = newLen;
    return info;
  }

  // ---------------------------------------------------------------- fit to keys
  // The loop stops and repeats only as long as the keys placed: after every hand edit of body keys, the length
  // becomes the last body key over all sims plus that sim's own last gap - a "smooth return" back to the first pose,
  // never below whatever else is timed, never below 12 frames. Off for Magic/imports/mocap and old saves (they keep
  // the length they were given), and off the moment someone types a length by hand. Nothing else moves: keys keep
  // their frames.
  // frame: when given (K / Key pose / double-click), a key placed in the room while Fit is off still grows the loop
  // to just past it (no gap-based extension) - "with Fit off it grows to include the key" (plan item 3).
  _applyFit(frame = null) {
    const p = this.store.project;
    if (p.fitLength === false) {
      if (frame !== null && frame >= p.length) this._retimeLengthOnly(p, frame + 1);
      return;
    }
    const floors = this.runHook('fitFloor', p);
    const n = KO.fitLength(p, floors);
    if (n === null || n === p.length) return;
    this._retimeLengthOnly(p, n);
  }
  // Set p.length to exactly `n` - no retiming, no key moves (unlike _retimeProject, which stretches/cuts keys).
  _retimeLengthOnly(p, n) {
    p.length = Math.max(12, Math.min(3000, Math.round(n)));
    this.pipeline.overrides.clear();
    this.refreshAll();
    this.timeline.fit();
    this.physicsChanged();
  }

  setLength(newLen, mode = localStorageGet('lengthMode', 'stretch')) {
    const p = this.store.project, oldLen = p.length;
    newLen = Math.max(12, Math.min(3000, Math.round(newLen)));
    if (newLen === oldLen) { this._showLength(); return; }
    const busy = p.sims.some(s => s.keys.length > 1 || (s.sounds || []).length || (s.layers || []).length) || (Array.isArray(p.events) && p.events.length);
    this.store.checkpoint(newLen > oldLen ? 'Longer loop' : 'Shorter loop');
    p.fitLength = false;   // typing a length by hand is a deliberate choice - Fit no longer moves it
    const before = this.store.peekUndo();
    const depth = this.store.undo.length;
    this.setPlayRange(null, { quiet: true });
    const apply = m => {
      const info = this._retimeProject(this.store.project, newLen, m);
      this.vp.gizmo.detach(); this.interact.active = null;
      this.pipeline.overrides.clear();
      this.store.frame = Math.min(Math.round(this.store.frame), newLen - 1);
      this.refreshAll();
      this.timeline.fit();
      this.physicsChanged();
      return info;
    };
    const info = apply(mode);
    if (!busy) return;
    const longer = newLen > oldLen, secs = (newLen / p.fps).toFixed(1);
    const still = () => this.store.undo.length === depth && this.store.peekUndo() === before && !this.store.redo.length;
    const text = (m, i) => m === 'stretch'
      ? `Loop is ${secs} s now - keys and sounds moved with it, so everything plays ${longer ? 'slower' : 'faster'}.`
      : `Loop is ${secs} s now - same speed: ${longer ? 'time was added at the end' : 'the end was cut off'}${i.moved ? ' and the last pose moved to the new end' : ''}${i.lostSounds ? `, ${i.lostSounds} sound${i.lostSounds > 1 ? 's' : ''} past the end removed` : ''}. Motions repeat ${longer ? 'more' : 'less'} often.`;
    const actions = m => [
      { label: m === 'stretch' ? 'Keep the speed instead' : (longer ? 'Slow it all down instead' : 'Speed it all up instead'), primary: true, onClick: () => {
        if (!still()) { toast('Something changed since - use Undo (Ctrl+Z) instead.'); return true; }
        const other = m === 'stretch' ? 'keep' : 'stretch';
        this.store.project = JSON.parse(before);
        const i = apply(other);
        localStorageSet('lengthMode', other);
        bar.update(text(other, i), actions(other));
        return false;
      } },
      { label: 'Undo', onClick: () => {
        if (!still()) { toast('Something changed since - use Undo (Ctrl+Z) instead.'); return true; }
        this.undo();
        toast('Loop length put back.');
        return true;
      } },
    ];
    const bar = choiceBar(text(mode, info), actions(mode), { timeout: 14000 });
  }

  _showLength() {
    const p = this.store.project;
    $('tl-seconds-in').value = (p.length / p.fps).toFixed(1);
    $('tl-frames-note').textContent = `${p.length} frames`;
    const on = p.fitLength !== false;
    const fitBtn = $('btn-fit-length');
    fitBtn.classList.toggle('on', on);
    fitBtn.title = on ? 'Fit to keys - on: the loop follows the last key automatically' : 'Fit to keys - off: the length stays where it was set';
  }

  // ---------------------------------------------------------------- UI
  showStep(step) {
    // leaving the Face step: the see-through sims turn solid, and the camera leaves the face close-up and frames all
    // the sims again - so Motion, Sounds, the Library and the rest show the whole bodies, not a giant face.
    // (Home only covers the stage: coming back to the Face step finds it as it was)
    // It goes back to the view you had before the close-up; with none to go back to (a restored session, a new
    // animation meanwhile) it frames all the sims from above and in front - never from under a bed.
    if (step !== 'face' && step !== 'home' && this.step === 'face') {
      if (this._faceFaded) this._fadeOthers(null);
      const back = this._camBeforeFace;
      this._camBeforeFace = null;
      if (back && back.project === this.store.project && back.view.pos.y > this._surfaceTop() + 0.1) this.vp.restoreView(back.view);
      else this.frameSims({ fromAbove: true });
    }
    if (step === 'home') return showHome(this);
    const prev = this.step, changed = step !== prev;
    this.step = step;
    document.body.dataset.step = step;
    document.querySelectorAll('#rail button[data-step]').forEach(b => b.classList.toggle('active', b.dataset.step === step));
    const info = STEPS[step];
    $('panel-title').textContent = info.title;
    $('panel-sub').textContent = info.sub;
    // a new step opens at its top (its most important control); re-drawing the same step keeps the scroll
    if (changed) $('panel-body').scrollTop = 0;
    this.renderStep();
    if (changed && step === 'face') {
      // remember the view to come back to (where the camera is, or where it is flying to)
      this._camBeforeFace = { view: this.vp.savedView(), project: this.store.project };
      this.frameFace();
    }
    if (changed) this.emit('step', { prev, step });
  }

  renderStep() {
    const body = $('panel-body'), foot = $('panel-foot');
    const info = STEPS[this.step];
    if (this.step === 'library') {
      if (!this.library.root.isConnected || body.firstChild !== this.library.root) { body.innerHTML = ''; body.append(this.library.root); }
      foot.innerHTML = '';
      this.emit('rendered', { step: this.step, root: body });
      return;
    }
    const keep = body.scrollTop;
    body.innerHTML = '';
    info.render(this, body);
    // sections other features add at the end of this step's panel
    this.runHook('sections.' + this.step, this, body);
    body.scrollTop = keep;
    // sections that fill in a moment later (hair, the Tray bodies) must not move the page: the same place again once
    // they have (the panel doesn't follow them by itself: overflow-anchor is off in app.css)
    if (keep) requestAnimationFrame(() => { if (body.scrollTop !== keep) body.scrollTop = keep; });
    foot.innerHTML = '';
    const order = Object.keys(STEPS).filter(k => k !== 'library');
    const i = order.indexOf(this.step);
    if (i > 0) foot.append(h('button', { class: 'btn ghost', onclick: () => this.showStep(order[i - 1]) }, 'Back'));
    if (info.next) foot.append(h('button', { class: 'btn primary', onclick: () => this.showStep(info.next) }, `Next: ${STEPS[info.next].short || STEPS[info.next].title}`, icon('arrow')));
    else foot.append(h('button', { class: 'btn primary', onclick: () => this.exportDialog() }, 'Send to game'));
    body.querySelectorAll('input[type=range]').forEach(fillRange);
    // the tile just picked pops once: the marker lives for this render only
    if (this._justPicked) requestAnimationFrame(() => { this._justPicked = null; });
    this.emit('rendered', { step: this.step, root: body });
  }

  // The hint row over the stage. hold: keep this message a moment (a redraw right after does not wipe it).
  hud(text, { hold = 0 } = {}) {
    const el = $('vp-hud');
    const now = performance.now();
    if (hold) this._hudHold = now + hold;
    else if (this._hudHold > now) return;
    const sim = this.store.sim();
    const tool = { rotate: 'Click a body part, then turn the rings · T moves it', ik: 'Drag the dots: hands, feet, hips - drop a hand on the partner to hold on · Alt+click pins them', move: 'Click a body part to move it · the circle at a sim\'s feet moves the whole sim',
      face: 'Click a dot on the face · T moves, R turns · X both sides · Alt goes past the safe range' }[this.interact.tool];
    el.innerHTML = '';
    el.append(text ? h('span', {}, h('b', {}, text)) : h('span', {}, sim ? h('b', {}, sim.label + ' · ') : '', tool));
  }

  _historyButtons() {
    $('btn-undo').disabled = !this.store.undo.length;
    $('btn-redo').disabled = !this.store.redo.length;
  }

  refreshPanels() {
    this.renderStep();
    renderInspector(this);
    this.hud(null);
    this.refreshTitle();
    this._historyButtons();
  }

  refreshTitle() {
    const p = this.store.project;
    $('pc-name').textContent = p.name || 'Untitled animation';
    $('pc-by').textContent = p.author ? 'by ' + p.author : 'add a creator';
    $('pc-kind').textContent = (KINDS.find(k => k[0] === p.category) || ['', 'Animation'])[1];
    document.title = `${p.name}${p.author ? ' by ' + p.author : ''} · Novulon's Wicked Animator`;
  }

  // The timeline is as tall as its lanes need (1 sim: short; 3+ sims: full), so the step panel keeps the rest.
  // In the Curves view it is taller (320 px unless you dragged its top edge); a height you dragged in the Keys view is
  // kept too.
  _fitTimeline() {
    const n = Math.max(1, this.store.project.sims.length);
    const rows = this.timeline ? this.timeline.rowsHeight() : 0;      // rows other features added above the lanes
    const max = Math.round(innerHeight * 0.6);
    let px;
    if (this.tlView === 'curves') px = Math.max(220, Math.min(max, +localStorageGet('curvesH', 320) || 320));
    else {
      const kh = localStorageGet('keysH', null);
      px = kh ? Math.max(150, Math.min(max, +kh)) : Math.min(236 + rows, Math.max(150, 60 + 28 + rows + n * 48 + 8));
    }
    if (px !== this._tlH) { this._tlH = px; document.documentElement.style.setProperty('--tl-h', px + 'px'); }
  }

  // Messages (toasts, choice bars) sit over the bottom of the stage. A card there - the clipping check's, or any element
  // with data-lift-toasts - pushes them up above it while it is open, so they never cover it.
  _wireToastLift() {
    const wrap = $('viewport-wrap');
    if (!wrap || typeof MutationObserver === 'undefined') return;
    let watched = null, ro = null;
    const lift = () => {
      const card = wrap.querySelector('#clip-card, .clip-card, [data-lift-toasts]');
      if (card !== watched) {
        if (ro) ro.disconnect();
        watched = card;
        if (card && typeof ResizeObserver !== 'undefined') { ro = new ResizeObserver(() => lift()); ro.observe(card); }
      }
      let px = 0;
      if (card && card.isConnected && card.offsetParent !== null) {
        // (from the layout, not the drawn box: the card pops in with a small slide that would fool it)
        const top = card.offsetParent === wrap ? card.offsetTop : card.getBoundingClientRect().top - wrap.getBoundingClientRect().top;
        px = Math.max(0, Math.round(wrap.clientHeight - top + 10 - 60));
      }
      document.documentElement.style.setProperty('--toast-lift', px + 'px');
    };
    new MutationObserver(lift).observe(wrap, { childList: true });
    window.addEventListener('resize', lift);
    lift();
  }

  // The timeline's top edge: drag it to make the timeline taller or shorter (remembered per view).
  _wireResize() {
    const grip = $('tl-resize');
    if (!grip) return;
    grip.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      e.preventDefault();
      const y0 = e.clientY, h0 = this._tlH || $('timeline').getBoundingClientRect().height;
      const min = this.tlView === 'curves' ? 220 : 150, max = Math.round(innerHeight * 0.6);
      grip.classList.add('on');
      document.body.classList.add('tl-resizing');
      const move = ev => {
        const px = Math.max(min, Math.min(max, Math.round(h0 - (ev.clientY - y0))));
        this._tlH = px;
        document.documentElement.style.setProperty('--tl-h', px + 'px');
      };
      const up = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        grip.classList.remove('on');
        document.body.classList.remove('tl-resizing');
        localStorageSet(this.tlView === 'curves' ? 'curvesH' : 'keysH', this._tlH);
        this.timeline.draw();
        if (this.curves && this.curves.shown) this.curves.draw();
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    });
    // double-click the edge: back to the automatic height
    grip.addEventListener('dblclick', () => { localStorageRemove(this.tlView === 'curves' ? 'curvesH' : 'keysH'); this._tlH = null; this._fitTimeline(); });
  }

  refreshAll() {
    this._edited();
    this._fitTimeline();
    this.syncViews();
    this.applyPoses();
    this.refreshPanels();
    this.interact.refreshHandles();
    this._showLength();
    $('tl-frame').textContent = Math.round(this.store.frame);
    $('btn-loop').classList.toggle('on', !!this.store.project.loop);
    this.timeline.draw();
    this._syncEaseBox();
    this.updateTrail();
  }

  _onStore(what) {
    if (what === 'dirty') { $('dirty-dot').classList.toggle('on', this.store.dirty); this._historyButtons(); }
    if (what === 'project') {
      this.vp.gizmo.detach(); this.interact.active = null; this.pipeline.overrides.clear();
      // undo/redo can take away the selected sim, or shorten the loop under the playhead
      if (!this.store.sim()) this.store.selected = { sim: this.store.project.sims[0] ? this.store.project.sims[0].id : null, bone: null };
      this.store.frame = Math.max(0, Math.min(Math.round(this.store.frame), roomEnd(this.store.project) - 1));
      if (this.playRange && this.playRange[1] >= this.store.project.length) this.playRange = null;
      this._edited();
      this.timeline && this.timeline.pruneSel();
      if (this.refs) { try { this.refs.load(this.store.project); } catch (err) { console.error(err); } }
      this.refreshAll();
      // a loop of another length (undo, redo, a new or restored animation) fills the timeline again
      if (this.timeline && this.timeline._fitLength !== this.store.project.length) this.timeline.fit();
      this.physicsChanged();
    }
  }

  // Undo / redo, telling features which sims changed (their rim light flashes).
  undo() { return this._history(false); }
  redo() { return this._history(true); }
  _history(redo) {
    const before = this.store.project;
    const ok = redo ? this.store.redoStep() : this.store.undoStep();
    if (!ok) return false;
    this._afterHistory(before, redo);
    return ok;
  }
  _afterHistory(before, redo) {
    const after = this.store.project;
    const was = new Map(before.sims.map(s => [s.id, JSON.stringify(s)]));
    const simIds = [];
    for (const s of after.sims) if (was.get(s.id) !== JSON.stringify(s)) simIds.push(s.id);
    for (const id of was.keys()) if (!after.sims.some(s => s.id === id)) simIds.push(id);
    this.emit('undo', { redo, simIds });
    return true;
  }

  // The Face tool's button (index.html may not have it yet): after Pose in the tool row.
  _ensureFaceToolButton() {
    const seg = $('tool-seg');
    if (!seg || seg.querySelector('button[data-tool="face"]')) return;
    const b = h('button', { 'data-tool': 'face', title: 'Pose the face: brows, eyes, lids, cheeks, lips, jaw and tongue (Shift+F)' }, icon('face'), h('span', {}, 'Face'));
    const pose = seg.querySelector('button[data-tool="rotate"]');
    if (pose && pose.nextSibling) seg.insertBefore(b, pose.nextSibling); else seg.append(b);
  }

  _wireUI() {
    $('brand').onclick = () => showHome(this);
    $('project-chip').onclick = () => this.showStep('details');
    $('btn-undo').onclick = () => this._historyToast(this.undo(), false);
    $('btn-redo').onclick = () => this._historyToast(this.redo(), true);
    // right-click Undo: the last steps by name, to go back several at once
    $('btn-undo').addEventListener('contextmenu', e => { e.preventDefault(); this.undoHistoryMenu(e.clientX, e.clientY + 8); });
    $('btn-undo').title = 'Undo (Ctrl+Z) · right-click for the list of steps';
    // where the last click was (keys like Ctrl+A act on the timeline or the view)
    window.addEventListener('pointerdown', e => {
      const t = e.target instanceof Element ? e.target : null;
      if (!t) return;
      if (t.closest('#curve-wrap')) this.focus = 'curves';
      else if (t.closest('#timeline')) this.focus = 'timeline';
      else if (t.closest('#viewport-wrap')) this.focus = 'view';
      else if (t.closest('#left, #right')) this.focus = 'panel';
    }, true);
    // Alt: past the safe range while dragging a face part (and it never opens the window menu)
    window.addEventListener('keydown', e => { if (e.key === 'Alt') this.altDown = true; }, true);
    window.addEventListener('keyup', e => { if (e.key === 'Alt') { this.altDown = false; e.preventDefault(); } }, true);
    window.addEventListener('blur', () => { this.altDown = false; });
    $('btn-save').onclick = () => this.save();
    $('btn-export').onclick = () => this.exportDialog();
    $('btn-share').onclick = () => openShareDialog(this);
    $('btn-magic').onclick = () => this.openMagic();
    $('btn-showcase').onclick = () => this.showcase(!this._showStep);
    $('btn-record').onclick = () => {
      if (this._recordingVideo) return;
      if (this.onion) { this.onion = false; $('btn-onion').classList.remove('on'); this.updateGhosts(); }
      if (this.trail) { this.trail = false; $('btn-trail').classList.remove('on'); this.updateTrail(); }
      // reference pictures stay out of the video
      if (this.refs) this.refs.setHidden(true);
      Promise.resolve(recordVideo(this)).catch(err => console.error(err)).finally(() => { if (this.refs) this.refs.setHidden(false); });
    };
    $('btn-help').onclick = () => openHelp(this);
    document.querySelectorAll('#rail button[data-step]').forEach(b => b.onclick = () => this.showStep(b.dataset.step));
    document.querySelectorAll('#tool-seg button').forEach(b => b.onclick = () => this.setTool(b.dataset.tool));
    document.querySelectorAll('#view-seg button').forEach(b => b.onclick = () => {
      document.querySelectorAll('#view-seg button').forEach(x => x.classList.toggle('active', x === b));
      this.vp.setView(b.dataset.view);
    });
    $('btn-onion').onclick = () => { this.onion = !this.onion; $('btn-onion').classList.toggle('on', this.onion); this._ghostKey = ''; this.updateGhosts(); };
    $('btn-onion').addEventListener('contextmenu', e => { e.preventDefault(); this.onionMenu(e.clientX - 200, e.clientY + 14); });
    $('btn-onion').title = 'Ghosts: see the keys before and after this one · right-click for more ghost options';
    $('btn-trail').onclick = () => { this.trail = !this.trail; $('btn-trail').classList.toggle('on', this.trail); this.updateTrail(); };
    $('btn-play').onclick = () => this.setPlaying(!this.playing);
    $('btn-first').onclick = () => this.setFrame(0);
    $('btn-prev-key').onclick = () => this.jumpKey(-1);
    $('btn-next-key').onclick = () => this.jumpKey(1);
    $('btn-loop').onclick = () => this.toggleLoop();
    $('btn-loop').addEventListener('contextmenu', e => { e.preventDefault(); this.loopMenu(e.clientX, e.clientY - 10); });
    // Keys | Curves, the timeline's height, reference pictures (the button and dropping a file on the view)
    document.querySelectorAll('#tl-view-seg button').forEach(b => { b.onclick = () => this.setTimelineView(b.dataset.tlview); });
    this._wireResize();
    this._wireToastLift();
    if ($('btn-ref')) $('btn-ref').onclick = () => this.pickReference();
    const wrap = $('viewport-wrap'), zone = $('drop-zone');
    const isFiles = e => e.dataTransfer && [...(e.dataTransfer.types || [])].includes('Files');
    wrap.addEventListener('dragover', e => { if (!isFiles(e)) return; e.preventDefault(); zone && zone.classList.remove('hidden'); });
    wrap.addEventListener('dragleave', e => { if (!wrap.contains(e.relatedTarget)) zone && zone.classList.add('hidden'); });
    wrap.addEventListener('drop', e => {
      if (!isFiles(e)) return;
      e.preventDefault();
      zone && zone.classList.add('hidden');
      const files = [...e.dataTransfer.files].filter(f => /^(image|video)\//.test(f.type));
      if (!files.length) return toast('Drop a picture (PNG, JPG, WEBP, GIF) or a video (MP4, WEBM).');
      if (this.refs) this.refs.addFiles(files);
    });
    $('btn-key').onclick = () => this.keyPose();
    $('btn-key-all').onclick = () => this.keyAll();
    $('btn-del-key').onclick = () => this.deleteKey();
    $('btn-autokey').classList.toggle('on', this.autoKey);
    $('btn-autokey').onclick = () => {
      this.autoKey = !this.autoKey; localStorageSet('autoKey', this.autoKey);
      $('btn-autokey').classList.toggle('on', this.autoKey);
      toast(this.autoKey ? 'Auto key on: every change is kept at this frame.' : 'Auto key off: press K to keep a pose.');
    };
    // lists and number boxes let go of the keyboard once used, so arrows, K and Space work on the animation again
    const settle = el => el.blur();
    const easeSel = h('select', { id: 'ease-select' }, Object.entries(EASE_INFO).map(([v, [t]]) => h('option', { value: v }, t)));
    easeSel.onchange = () => {
      const sim = this.store.sim(), key = this.currentKey(sim);
      settle(easeSel);
      if (easeSel.value === 'custom') {
        // a custom curve belongs to one key: it opens the timing editor for the key here
        if (!key) { toast('Go to a key first - a custom curve is set on one key.'); this._syncEaseBox(); return; }
        this.setEase(sim.id, key.frame, 'custom');
        const r = easeSel.getBoundingClientRect();
        this.timingEditor(sim.id, key.frame, r.left, r.top - 330);
        return;
      }
      localStorageSet('ease', easeSel.value);
      if (key) this.setEase(sim.id, key.frame, easeSel.value);
      else toast(`New keys will use "${EASE_INFO[easeSel.value][0]}".`);
    };
    $('ease-pick').append(easeSel);
    $('tl-speed').onchange = e => { this.speed = +e.target.value; settle(e.target); };
    const soundBtn = $('btn-sound');
    const showSound = () => { soundBtn.classList.toggle('on', !this.audio.muted); soundBtn.innerHTML = `<svg><use href="#i-${this.audio.muted ? 'mute' : 'sound'}"/></svg>`; };
    soundBtn.onclick = () => { this.audio.ensure(); this.audio.setMuted(!this.audio.muted); showSound(); toast(this.audio.muted ? 'Sound off.' : 'Sound on - you hear the sounds as the animation plays.'); };
    showSound();
    $('tl-seconds-in').onchange = e => {
      const p = this.store.project;
      settle(e.target);
      this.setLength((+e.target.value || p.length / p.fps) * p.fps);
    };
    $('tl-seconds-in').addEventListener('keydown', e => { if (e.key === 'Escape') { this._showLength(); e.target.blur(); } });
    $('btn-fit-length').onclick = () => {
      const p = this.store.project, turningOn = p.fitLength === false;
      this.store.checkpoint(turningOn ? 'Fit to keys on' : 'Fit to keys off');
      p.fitLength = turningOn;
      if (turningOn) this._applyFit();      // fits at once, same undo step
      this._edited(); this.store.setDirty(true); this._showLength();
      toast(turningOn ? 'Fit to keys on - the loop follows the last key.' : 'Fit to keys off - the length stays put.');
    };
    window.addEventListener('keydown', e => this._key(e));
    // Shift+E: an in-between key (Blender's breakdowner key). It is taken before the fly camera sees it - except over
    // the 3D view, where E still flies up (Shift = slowly).
    window.addEventListener('keydown', e => {
      if (e.code !== 'KeyE' || !e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || e.repeat) return;
      if (this.focus === 'view' || dialogOpen() || !$('home').classList.contains('hidden')) return;
      const t = e.target instanceof Element ? e.target : document.body;
      if (t.matches('input:not([type=range]):not([type=checkbox]):not([type=radio]), select, textarea, [contenteditable]')) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      this.insertInBetween();
    }, true);
    window.addEventListener('keyup', e => {
      if (e.code === 'Space' && !e.target.matches('input:not([type=range]):not([type=checkbox]), select, textarea, [contenteditable]') && !dialogOpen()) e.preventDefault();
    });
  }

  setTool(tool) {
    const was = this.interact.tool;
    // the Face tool works on a sim: the first one when none is selected
    if (tool === 'face' && !this.store.sim() && this.store.project.sims[0]) this.store.selected = { sim: this.store.project.sims[0].id, bone: null };
    document.querySelectorAll('#tool-seg button').forEach(x => x.classList.toggle('active', x.dataset.tool === tool));
    this.interact.setTool(tool);
    $('viewport-wrap').classList.toggle('face-mode', tool === 'face');
    if (tool === 'face' && was !== 'face') this.frameFace();
    this.hud(null);
    if (this.step === 'face') this.renderStep();
  }

  _key(e) {
    if (e.defaultPrevented) return;           // a dialog already used this key
    const ctrl = e.ctrlKey || e.metaKey;
    // physical keys, so the shortcuts work on any keyboard layout and with Shift held
    const code = e.code || '';
    const dialog = dialogOpen();
    // Save and Open work everywhere, also while typing in a box (the box keeps what was typed)
    if (ctrl && (code === 'KeyS' || code === 'KeyO')) {
      e.preventDefault();                     // never the browser's own "Save page as" / "Open file"
      if (dialog) return;
      const a = document.activeElement;
      if (a && a !== document.body && a.blur) a.blur();
      if (code === 'KeyS') this.save(); else this.open();
      return;
    }
    // only real text boxes keep the keyboard; sliders, switches and buttons don't (so Space always plays/pauses)
    const target = e.target instanceof Element ? e.target : document.body;
    const typing = target.matches('input:not([type=range]):not([type=checkbox]):not([type=radio]):not([type=button]), select, textarea, [contenteditable]');
    if (typing || dialog || !$('home').classList.contains('hidden')) {
      if (e.key === 'Escape' && !dialog && !$('home').classList.contains('hidden') && this.store.project.sims.length) hideHome(this);
      return;
    }
    if (target !== document.body && target.matches('button, input, [tabindex]') && target.id !== 'viewport') {
      // a clicked button or slider still has focus: take the key away from it so Space/Enter don't press it again
      if (e.code === 'Space' || e.code === 'Enter') e.preventDefault();
      target.blur();
    }
    // features first (never while typing or over a dialog): one that answers true has used the key
    const info = { ctrl, shift: e.shiftKey, alt: e.altKey, code, key: e.key, focus: this.focus };
    if (this.runHook('keys', e, info).some(r => r === true)) { e.preventDefault(); return; }
    if (ctrl && code === 'KeyZ') { e.preventDefault(); this._historyToast(e.shiftKey ? this.redo() : this.undo(), e.shiftKey); return; }
    if (ctrl && code === 'KeyY') { e.preventDefault(); this._historyToast(this.redo(), true); return; }
    // over the timeline (or the Curves view), the copy / paste / select keys act on keys (spec_editing 7.10)
    const onTl = this.focus === 'timeline' || this.focus === 'curves';
    const hasSel = this.timeline.sel.size > 0;
    if (onTl && ctrl && code === 'KeyA') { e.preventDefault(); this.selectAllKeys(); return; }
    if (onTl && ctrl && code === 'KeyC' && hasSel) { e.preventDefault(); this.copySelectedKeys(); return; }
    if (onTl && ctrl && code === 'KeyV' && this.keyClip) { e.preventDefault(); this.pasteKeys({ flipped: e.shiftKey }); return; }
    if (onTl && ctrl && code === 'KeyD' && hasSel) { e.preventDefault(); this.duplicateSelectedKeys(); return; }
    if (onTl && ctrl && (code === 'ArrowLeft' || code === 'ArrowRight') && hasSel) { e.preventDefault(); this.nudgeKeys((code === 'ArrowRight' ? 1 : -1) * (e.shiftKey ? 5 : 1)); return; }
    if (ctrl && e.shiftKey && code === 'KeyV' && this.clipboard) { e.preventDefault(); const s = this.store.sim(); if (s) this.pastePose(s.id, { flipped: true }); return; }
    if (ctrl && code === 'KeyC') { const s = this.store.sim(); if (s) this.copyPose(s.id); return; }
    if (ctrl && code === 'KeyV') { const s = this.store.sim(); if (s) this.pastePose(s.id); return; }
    if (ctrl) return;
    // Tab over the timeline: Keys <-> Curves
    if (code === 'Tab' && onTl && !e.altKey) { e.preventDefault(); this.setTimelineView(this.tlView === 'curves' ? 'keys' : 'curves'); return; }
    // the number pad, as in Blender: 1 front, 3 side, 7 top, 5 the free 3D view, . frames the selection (by the
    // physical key, so it works with Num Lock on or off)
    const NUMPAD = { Numpad1: 'front', Numpad3: 'side', Numpad7: 'top', Numpad5: 'persp' };
    if (NUMPAD[code]) { e.preventDefault(); this.setView(NUMPAD[code]); return; }
    if (code === 'NumpadDecimal') { e.preventDefault(); this.frameSelection(); return; }
    // Alt+R / Alt+G: the selected part's turn / move back to rest (Blender habit)
    if (e.altKey && (code === 'KeyR' || code === 'KeyG')) {
      e.preventDefault();
      const sel = this.store.selected;
      if (!sel.sim || !sel.bone) { toast('Click a body part first.'); return; }
      if (code === 'KeyG' && HIPS.includes(sel.bone)) { toast('The hips carry the sim\'s place. The circle at its feet moves the whole sim.'); return; }
      this.resetBone(sel.sim, sel.bone, code === 'KeyR' ? { turn: true, move: false } : { turn: false, move: true });
      toast(code === 'KeyR' ? `${label(sel.bone)}: turn reset.` : `${label(sel.bone)}: back in its place.`);
      return;
    }
    if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'KeyQ', 'KeyE'].includes(code)) return;     // the fly camera
    if (code === 'Space') { e.preventDefault(); if (!e.repeat) this.setPlaying(!this.playing); return; }
    if (e.key === '/') { e.preventDefault(); if (!focusBoneSearch()) toast('Select a sim to see its bones.'); return; }
    switch (e.key) {
      case 'k': case 'K': e.shiftKey ? this.keyAll() : this.keyPose(); break;
      case 'i': case 'I': this.keyPose(); break;                    // Blender's "insert keyframe"
      case 'Delete': case 'Backspace': if (onTl && hasSel) this.deleteSelectedKeys(); else this.deleteKey(); break;
      case 'p': case 'P': this.togglePlayRange(); break;
      // R turns the picked part (its rings), T moves it (its arrows) - the circle at a sim's feet is the whole sim
      case 'r': case 'R': if (!this.interact.turnSelected()) this.setTool('rotate'); break;
      case 'g': case 'G': this.setTool('ik'); break;
      case 'm': case 'M': this.setTool('move'); break;
      case 'x': case 'X': this.setMirrorEdit(!this.mirrorEdit); break;
      case 't': case 'T': if (this.interact.moveSelected()) this.emitSelection(); break;
      case 'Home': this.setFrame(0); break;
      case ',': this.jumpKey(-1); break;
      case '.': this.jumpKey(1); break;
      case 'ArrowLeft': this.setFrame(this.store.frame - 1); break;
      case 'ArrowRight': this.setFrame(this.store.frame + 1); break;
      case '?': openHelp(this); break;
      case 'f': case 'F':
        // Shift+F: the Face tool (on / off); F frames the selection
        if (e.shiftKey) { this.setTool(this.interact.tool === 'face' ? 'rotate' : 'face'); break; }
        if (this.focus === 'curves' && this.curves && this.curves.shown) { this.curves.frameAll(); break; }
        this.frameSelection();
        break;
      case 'Escape':
        if (onTl && hasSel) { this.clearKeySelection(); break; }
        this.vp.gizmo.detach(); this.interact.active = null; this.store.selected.bone = null; this.emitSelection(); break;
    }
  }

  // The view buttons (3D / Front / Side / Top) and the number pad.
  setView(kind) {
    document.querySelectorAll('#view-seg button').forEach(x => x.classList.toggle('active', x.dataset.view === kind));
    this.vp.setView(kind);
  }

  // F: fly to the selected part (or the selected sim).
  frameSelection() {
    const v = this.simViews.get(this.store.selected.sim);
    if (!v) return;
    const bone = this.store.selected.bone;
    const face = bone && K.isFace(bone);
    this.vp.frame(v.worldPos(bone || 'b__Spine1__'), face ? 0.16 : bone ? 0.45 : 1.1);
  }
}

const app = new App();
window.app = app;
app.init().catch(err => {
  console.error(err);
  // the start-up safety net in index.html shows the message with a Reload button
  const msg = /Failed to fetch|NetworkError/i.test(err.message || '')
    ? 'The app\'s server is not answering - close this window and start Wicked Animator again.' : 'Error: ' + err.message;
  if (window.__startFailed) window.__startFailed(msg);
  else $('loading-text').textContent = 'Could not start: ' + err.message;
});
