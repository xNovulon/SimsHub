// Faces 2 (build plan R2-5): the game's own faces, the face map and lip-sync from a sound. The Face step draws them
// (steps/face.js); this plugs the rest into the app through its plug-in points (plan 2.4), so main.js stays as it is:
//   - app.setFaceBones(simId, fb, label, intensity), app.gameFace(simId, id, intensity), app.lipSync(simId, source,
//     opts), app.lipSyncVoices(simId, opts) - new app methods (no existing one is replaced);
//   - the hover preview of a game face and the live face map, after every frame the app shows (hooks.afterApply);
//   - "Lip-sync this sound" on a voice sound's right-click menu, palette commands and help rows;
//   - your own sound file stops with the playback (hooks.playing).
import { setFaceBones, loadFaces, faceById, applyPreview, setPreview } from '../gamefaces.js';
import { updateFaceMaps } from '../facemap2d.js';
import { lipSync, lipSyncVoices } from '../lipsync.js';
import { stopListening, prettyLine } from '../lipsyncui.js';
import { toast } from '../ui.js';
import { setVoiceSeconds } from '../face.js';
import { $t } from '../i18n.js';

export function install(app) {
  if (!app || app.__faces2) return;
  app.__faces2 = true;
  const hooks = app.hooks || {};
  const add = (name, fn) => { const list = name.split('.').reduce((o, k) => o && o[k], hooks); if (Array.isArray(list)) list.push(fn); };

  // ---- new app methods
  if (typeof app.setFaceBones !== 'function') {
    app.setFaceBones = (simId, fb, label = null, intensity = 1, opts = {}) => setFaceBones(app, simId, fb, label, intensity, opts);
  }
  app.gameFace = async (simId, id, intensity = app._gfAmount ?? 1) => {
    await loadFaces();
    const f = faceById(id) || faceById('ea:' + id);
    if (!f) { toast($t('features.faces.that_game_face_is_not')); return null; }
    return setFaceBones(app, simId, f.fb, f.short, intensity, { id: f.id, pickId: 'gface:' + f.id });
  };
  app.lipSync = (simId, source, opts = {}) => lipSync(app, simId, typeof source === 'string' ? { name: source } : source, opts);
  app.lipSyncVoices = (simId, opts = {}) => lipSyncVoices(app, simId, opts);

  // ---- after every frame shown: the game face under the pointer, then the face map follows the face
  add('afterApply', () => { applyPreview(app); updateFaceMaps(app); });
  add('playing', on => { if (!on) stopListening(); else setPreview(app, null); });
  add('projectLoaded', () => { setPreview(app, null); app._lipFile = null; app._lipStatus = null; });
  add('simRemoved', simId => { if (app._lipFile && app._lipFile.simId === simId) app._lipFile = null; });

  // ---- a voice sound's right-click menu: lip-sync just that one
  add('menus.sound', (items, ctx) => {
    const sim = ctx && ctx.sim, snd = ctx && ctx.snd;
    if (!sim || !snd || snd.kind !== 'voice') return;
    items.push({ label: snd.lipsync ? $t('features.faces.lip_sync_this_sound_again') : $t('features.faces.lip_sync_this_sound_mouth'), icon: 'face',
      onClick: () => lipSync(app, sim.id, { name: snd.name }, { frame: snd.frame, strength: app._lipStrength ?? 1, brows: app._lipBrows !== false })
        .then(r => toast($t('features.faces.mouth_follows_face_keys', { prettyLine: prettyLine(snd.name), keys: r.keys }), 'ok'))
        .catch(err => toast(String((err && err.message) || err))) });
  });

  // ---- the command palette (Ctrl+K) and Help
  const openFace = (tab) => { if (tab) app._faceTab = tab; app.showStep('face'); };
  add('commands', a => {
    const sim = a.store.sim(), when = () => !!a.store.sim();
    const voices = sim ? (sim.sounds || []).filter(x => x.kind === 'voice').length : 0;
    return [
      { group: $t('features.faces.faces'), id: 'game-faces', label: $t('features.faces.game_faces'), icon: 'face', sub: $t('features.faces.real_sims_expressions_from_game'), words: 'ea faces expressions moods flirty passionate pleasure kiss woohoo emotions sims', run: () => openFace('game'), when },
      { group: $t('features.faces.faces'), id: 'face-map', label: $t('features.faces.face_map'), icon: 'face', sub: $t('features.faces.drag_face_dots_on_flat'), words: 'face dots 2d flat map brows lips lids', run: () => { try { localStorage.setItem('fsa.faceMapOpen', 'true'); } catch { /* private */ } openFace(); }, when },
      { group: $t('features.faces.faces'), id: 'lip-sync', label: voices ? $t('features.faces.lip_sync_voice_sounds') : $t('features.faces.lip_sync_from_sound'), icon: 'mic', sub: $t('features.faces.mouth_follows_moans_and_voices'), words: 'lipsync lip sync mouth talk voice moan audio wav mp3 ogg', when,
        run: () => { if (voices && sim) lipSyncVoices(app, sim.id, { strength: app._lipStrength ?? 1, brows: app._lipBrows !== false }).then(r => toast($t('features.faces.mouth_follows_voice_sound_s', { filterCount: r.filter(x => x.result).length }), 'ok')); openFace(); } },
    ];
  });
  add('helpRows', () => [
    { group: $t('features.faces.faces'), keys: ['Ctrl', 'K'], text: $t('features.faces.type_game_faces_for_real') },
    { group: $t('features.faces.faces'), keys: ['Ctrl', 'K'], text: $t('features.faces.type_lip_sync_to_make') },
    { group: $t('features.faces.faces'), keys: 'Double-click a face-map dot', text: $t('features.faces.put_that_part_of_face') },
  ]);

  // the game faces load in the background once the app is up (the first time the game is read it takes a minute)
  setTimeout(() => { loadFaces().catch(() => {}); }, 1500);
  // talking lasts as long as each game voice line really plays - in creator-style projects only (face.talkAt gets
  // the project's style; classic projects keep exactly the talking they had). The lengths are the Sounds feature's
  // (app.voiceSec, from /api/voices), read when needed, so they count as soon as they have arrived.
  setVoiceSeconds(name => { const m = app.voiceSec; return (m && typeof m.get === 'function' ? m.get(name) : m && m[name]) || 0; });
  window.wickedFaces = { setFaceBones: app.setFaceBones, gameFace: app.gameFace, lipSync: app.lipSync, setVoiceSeconds };
}

export default install;
