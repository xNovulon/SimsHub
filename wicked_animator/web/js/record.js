// Record a video of the stage (with the sounds) while the animation plays, to show it off or post it.
// captureVideo() films and hands back the video; recordVideo() also saves it (through /api/save_video) and shows the
// success card. Both put everything back as it was afterwards: the camera, the frame, playing or not, Showcase, the
// cinematic look, the sound, the tool, ghosts and trail, and the selected part.
import { h, icon, modal, toast, emitWA } from './ui.js';
import { api } from './api.js';
import { successHero, celebrateAt } from './fx.js';
import { $t } from './i18n.js';

// Let go of the gizmo for a moment (filming): -> a function that puts it back on the same part, as it was.
export function holdGizmo(app) {
  const gz = app.vp.gizmo, obj = gz.object, active = app.interact.active;
  const st = { mode: gz.mode, space: gz.space, size: gz.size, x: gz.showX, y: gz.showY, z: gz.showZ };
  gz.detach(); app.interact.active = null; app.interact.clearHover();
  return () => {
    if (!obj || !obj.parent || app.playing) return;
    gz.setMode(st.mode); gz.setSpace(st.space); gz.setSize(st.size);
    gz.showX = st.x; gz.showY = st.y; gz.showZ = st.z;
    gz.attach(obj);
    app.interact.active = active;
  };
}

// Film the stage for `seconds` (default: `loops` times the loop, at most 60 s). -> {blob, seconds, mime} or null.
//   view: {pos, target} - film from there (the camera goes back afterwards)
//   composite: {width, height, draw(ctx)} - film a picture made from the stage every frame instead of the stage
//              itself (the promo kit's safe teaser: a closer cut or a blur band)
export async function captureVideo(app, { loops = 2, seconds = null, showcase = true, badge = true, view = null, composite = null } = {}) {
  if (app._recordingVideo) return null;
  let canvas = app.vp.canvas, drawLoop = 0, comp = null;
  if (composite) {
    comp = document.createElement('canvas');
    comp.width = composite.width; comp.height = composite.height;
    canvas = comp;
  }
  if (!canvas.captureStream || !window.MediaRecorder) { toast($t('record.this_browser_cannot_record_video'), 'err'); return null; }
  const p = app.store.project;
  const secs = Math.max(1, Math.min(60, seconds || (p.length / p.fps) * loops));
  if (comp) {
    const g = comp.getContext('2d');
    const paint = () => { try { composite.draw(g); } catch (e) { console.warn('video picture', e); } drawLoop = requestAnimationFrame(paint); };
    paint();
  }
  const stopDraw = () => { if (drawLoop) cancelAnimationFrame(drawLoop); drawLoop = 0; };
  const video = canvas.captureStream(30);
  const ctx = app.audio.ensure();
  let tracks = [...video.getVideoTracks()];
  let dest = null;
  if (ctx && app.audio.master) {
    dest = ctx.createMediaStreamDestination();
    app.audio.master.connect(dest);
    tracks = tracks.concat(dest.stream.getAudioTracks());
  }
  const mime = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm'].find(m => MediaRecorder.isTypeSupported(m));
  let rec;
  try { rec = new MediaRecorder(new MediaStream(tracks), mime ? { mimeType: mime, videoBitsPerSecond: 12_000_000 } : {}); }
  catch (e) {
    if (dest) app.audio.master.disconnect(dest);
    video.getTracks().forEach(t => t.stop());
    stopDraw();
    toast($t('record.could_not_start_recording', { message: e.message }), 'err');
    return null;
  }
  app._recordingVideo = true;
  const recBtn = document.getElementById('btn-record');
  if (recBtn) recBtn.disabled = true;
  const chunks = [];
  rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
  const done = new Promise(res => { rec.onstop = res; });
  // what is put back afterwards
  const vp = app.vp;
  const was = {
    muted: app.audio.muted, tool: app.interact.tool, frame: app.store.frame, playing: app.playing,
    showcase: !!document.querySelector('#btn-showcase.on'), cine: !!(vp.stage && vp.stage.isCinematic),
    view: vp.savedView(), roll: vp.controls.roll || 0, onion: app.onion, trail: app.trail,
    selected: { ...app.store.selected },
  };
  app.audio.setMuted(false);
  const gizmoBack = holdGizmo(app);
  if (was.tool === 'ik') app.setTool('rotate');
  if (was.onion) { app.onion = false; document.getElementById('btn-onion')?.classList.remove('on'); app.updateGhosts(); }
  if (was.trail) { app.trail = false; document.getElementById('btn-trail')?.classList.remove('on'); app.updateTrail(); }
  if (was.playing) app.setPlaying(false);
  if (view) { if (was.showcase) app.showcase(false); vp.stopCamera(); vp.controls.lookFrom(view.pos, view.target, 0); }
  app.setFrame(0);
  app.setPlaying(true);
  if (showcase && !was.showcase && !view) app.showcase(true);
  document.body.classList.add('recording');
  // the cinematic look (glow, vignette, grain) is part of the picture while recording
  if (vp.stage) vp.stage.cinematic(true);
  const tag = badge ? h('div', { class: 'rec-badge' }, h('span', { class: 'dot' }), $t('record.recording')) : null;
  if (tag) document.getElementById('viewport-wrap').append(tag);
  try {
    rec.start(250);
    await new Promise(r => setTimeout(r, secs * 1000));
    rec.stop();
    await done;
  } finally {
    // everything back as it was: no circling camera (unless it was circling), the same view, frame and sound
    if (tag) tag.remove();
    stopDraw();
    document.body.classList.remove('recording');
    if (showcase && !was.showcase && !view) app.showcase(false);
    app.setPlaying(false);
    if (!was.showcase || view) { vp.stopCamera(); vp.controls.lookFrom(was.view.pos, was.view.target, was.roll); }
    if (view && was.showcase) app.showcase(true);
    if (vp.stage) vp.stage.cinematic(was.cine || !!document.querySelector('#btn-showcase.on'));
    app.audio.setMuted(was.muted);
    if (dest) { try { app.audio.master.disconnect(dest); } catch { /* already */ } }
    video.getTracks().forEach(t => t.stop());
    if (was.tool === 'ik') app.setTool('ik');
    if (was.onion) { app.onion = true; document.getElementById('btn-onion')?.classList.add('on'); }
    if (was.trail) { app.trail = true; document.getElementById('btn-trail')?.classList.add('on'); app.updateTrail(); }
    if (was.selected.sim !== app.store.selected.sim || was.selected.bone !== app.store.selected.bone) {
      app.store.selected = was.selected; app.emitSelection();
    }
    app.setFrame(was.frame);
    if (was.playing) app.setPlaying(true);
    else { if (was.onion) app.updateGhosts(); gizmoBack(); }
    app._recordingVideo = false;
    if (recBtn) recBtn.disabled = false;
  }
  return { blob: new Blob(chunks, { type: 'video/webm' }), seconds: secs, mime: mime || 'video/webm' };
}

export async function recordVideo(app, opts = {}) {
  const got = await captureVideo(app, opts);
  if (!got) return;
  const { blob, seconds } = got;
  const p = app.store.project;
  const name = `${p.name}${p.author ? ' by ' + p.author : ''}`;
  try {
    const r = await fetch('/api/save_video?name=' + encodeURIComponent(name), { method: 'POST', headers: { 'Content-Type': 'video/webm' }, body: blob })
      .then(x => (x.ok ? x.json() : x.json().then(b => { throw new Error(b.error || x.statusText); })));
    const hero = successHero();
    modal({
      title: $t('record.your_video_is_ready'),
      body: h('div', {}, hero, h('div', { class: 'success' }, icon('check'), h('div', {}, h('b', {}, $t('record.s_with_sound_mb', { seconds: seconds.toFixed(1), bytes: ((r.bytes || blob.size) / 1048576).toFixed(1) })), h('div', { class: 'path' }, r.path || ''))),
        h('video', { src: URL.createObjectURL(blob), controls: true, autoplay: true, loop: true, style: { width: '100%', borderRadius: '12px', marginTop: '10px', background: '#000' } })),
      buttons: [{ label: $t('record.open_folder'), onClick: () => { if (r.folder) api.reveal(r.folder); return false; } }, { label: $t('record.done'), kind: 'primary' }],
    });
    celebrateAt(hero, { delay: 480 });
    emitWA(app, 'recorded', { file: r.path });
  } catch (e) { toast($t('record.could_not_save_video', { message: e.message }), 'err'); }
}
