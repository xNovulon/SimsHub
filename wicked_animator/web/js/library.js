// The Library tab: search every WickedWhims animation, preview it, copy a pose or import it as keys.
import * as THREE from 'three';
import { api } from './api.js';
import { h, icon, toast } from './ui.js';
import { Sim } from './sim.js';
import { ClipPlayer, sampleToPose, sortKeys } from './animation.js';
import { openImportDialog } from './dialogs.js';
import { sampleToFaceBones } from './facekit.js';
import { KINDS, TAG_GROUPS, tagLabel } from './tags.js';
import { $t } from './i18n.js';

const $ = id => document.getElementById(id);
const LOCS = ['FLOOR', 'DOUBLE_BED', 'SINGLE_BED', 'SOFA', 'LOVESEAT', 'CHAIR_LIVING', 'CHAIR_DINING', 'COUNTER', 'TABLE_DINING_2X',
  'DESK', 'WALL', 'SHOWER', 'BATHTUB', 'HOTTUB', 'TOILET', 'BEACH_TOWEL', 'YOGA_MAT', 'DANCE_FLOOR', 'MASSAGE_TABLE', 'BAR'];
const NICE_LOC = l => l.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

export class Library {
  constructor(app) {
    this.app = app;
    this.page = 0;
    this.items = [];
    // the panel is built once and kept, so the search stays when you switch steps
    const el = this.el = {
      search: h('input', { placeholder: $t('library.search_animations_or_creators'), spellcheck: 'false' }),
      actors: h('select', {}, [['0', $t('library.any_sims')], ['1', '1 sim'], ['2', '2 sims'], ['3', '3 sims'], ['4', '4 sims']].map(([v, t]) => h('option', { value: v, selected: v === '2' }, t))),
      loc: h('select', {}, h('option', { value: '' }, $t('library.anywhere')), LOCS.map(l => h('option', { value: l }, NICE_LOC(l)))),
      cat: h('select', {}, h('option', { value: '' }, $t('library.any_kind')), KINDS.map(([v, t]) => h('option', { value: v }, t))),
      tag: h('select', {}, h('option', { value: '' }, $t('library.any_tag')), TAG_GROUPS.map(([group, tags]) => h('optgroup', { label: group }, tags.map(t => h('option', { value: t }, tagLabel(t)))))),
      count: h('div', { class: 'hint' }),
      list: h('div', { class: 'lib-list' }),
    };
    this.root = h('div', {},
      h('div', { class: 'search' }, icon('search'), el.search),
      h('div', { class: 'filters' }, el.actors, el.loc),
      h('div', { class: 'filters' }, el.cat, el.tag),
      el.count, el.list,
      h('div', { class: 'hint' }, $t('library.click_one_to_watch_it')));
    let t = null;
    el.search.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => this.search(), 220); });
    for (const k of ['actors', 'loc', 'cat', 'tag']) el[k].addEventListener('change', () => this.search());
    $('btn-preview-close').onclick = () => this.stopPreview();
    $('btn-preview-play').onclick = () => { if (this.preview) { this.preview.playing = !this.preview.playing; this._playIcon(); } };
    $('preview-scrub').addEventListener('input', e => { if (this.preview) { this.preview.frame = +e.target.value; this.preview.playing = false; this._playIcon(); } });
    $('btn-preview-pose').onclick = () => this.usePose();
    $('btn-preview-import').onclick = () => this.preview && openImportDialog(this.app, this.preview);
    this.search();
  }

  async search(more = false) {
    this.page = more ? this.page + 1 : 0;
    const el = this.el;
    const q = { q: el.search.value, actors: el.actors.value, loc: el.loc.value, cat: el.cat.value, tag: el.tag.value, page: this.page };
    el.count.textContent = $t('library.searching');
    let r;
    try { r = await api.library(q); } catch (e) { el.count.textContent = $t('library.could_not_search', { message: e.message }); return; }
    this.items = more ? this.items.concat(r.items) : r.items;
    el.count.textContent = $t('library.animations_adults_only', { total: r.total.toLocaleString(), total2: r.total });
    const list = el.list;
    list.innerHTML = '';
    for (const it of this.items) {
      list.append(h('div', { class: 'lib-item' + (this.preview && this.preview.anim.id === it.id ? ' active' : ''), onclick: e => this.open(it, e.currentTarget), title: it.locations.join(', ') },
        h('b', {}, it.name),
        h('div', { class: 'sub' }, h('span', {}, it.author), h('span', { class: 'chip' }, $t('library.n_sims', { n: it.actors.length })),
          h('span', { class: 'chip' }, (it.category || '').toLowerCase() || 'other'), h('span', {}, NICE_LOC(it.locations[0] || ''))),
        (it.tags || []).length ? h('div', { class: 'tagline' }, it.tags.slice(0, 5).map(t => h('span', { class: 'chip' }, tagLabel(t)))) : null));
    }
    if (this.items.length < r.total) list.append(h('button', { class: 'btn small lib-more', onclick: () => this.search(true) }, $t('library.show_more')));
  }

  async open(item, el) {
    document.querySelectorAll('.lib-item.active').forEach(x => x.classList.remove('active'));
    el && el.classList.add('active');
    $('preview-title').textContent = $t('library.loading', { itemName: item.name });
    $('preview-bar').classList.remove('hidden');
    let anim;
    try { anim = await api.animation(item.id, 1); }
    catch (e) { toast($t('library.could_not_load_that_animation', { message: e.message }), 'err'); if (!this.preview) $('preview-bar').classList.add('hidden'); return; }
    this.startPreview(anim);
  }

  startPreview(anim) {
    this.stopPreview(true);
    const app = this.app;
    app.setPlaying(false);
    app.vp.gizmo.detach();
    const views = anim.clips.map((c, k) => {
      const frame = anim.actors[k].gender === 'MALE' ? 'ym' : 'yf';
      const v = new Sim(app.assets.rig, app.assets.bodies[frame], { skin: frame === 'ym' ? '#9fc4ff' : '#c9d9ff' });
      app.applySkin && app.applySkin(v, frame);
      v.frameKey = frame;
      app.vp.sims.add(v.group);
      return v;
    });
    const players = anim.clips.map(c => new ClipPlayer(c));
    const length = Math.max(...players.map(p => p.frames));
    this.preview = { anim, views, players, frame: 0, playing: true, length };
    app.preview = this.preview;
    app.syncViews();              // hides the project's sims
    app.interact.refreshHandles();
    $('preview-title').textContent = `${anim.name} · ${anim.author}`;
    $('preview-title').title = `${anim.name} by ${anim.author}`;
    $('preview-scrub').max = length - 1;
    $('preview-bar').classList.remove('hidden');
    this._playIcon();
    // show the preview's sims in full (posed at their first frame)
    players.forEach((pl, k) => views[k].applyTracks(pl.sample(0)));
    if (app.frameSims) app.frameSims({ views });
  }

  _playIcon() { $('btn-preview-play').innerHTML = `<svg><use href="#i-${this.preview && this.preview.playing ? 'pause' : 'play'}"/></svg>`; }

  tickPreview(dt) {
    const p = this.preview;
    if (!p) return;
    if (p.playing) p.frame = (p.frame + dt * 30) % p.length;
    p.players.forEach((pl, k) => p.views[k].applyTracks(pl.sample(p.frame)));
    $('preview-scrub').value = Math.floor(p.frame);
    $('preview-frame').textContent = `${Math.floor(p.frame)} / ${p.length}`;
  }

  stopPreview(keepBar = false) {
    const p = this.preview;
    if (p) for (const v of p.views) this.app.disposeView ? this.app.disposeView(v) : v.dispose();
    this.preview = null;
    this.app.preview = null;
    if (!keepBar) $('preview-bar').classList.add('hidden');
    this.app.syncViews();
    this.app.applyPoses();
    this.app.interact.refreshHandles();
    // back to your own sims, framed again (the preview may have moved the camera)
    if (p && !keepBar && this.app.frameSims) this.app.frameSims();
  }

  // Copy the pose shown in the preview into the sims at the current frame (every part, like a ready pose).
  usePose() {
    const p = this.preview, app = this.app;
    if (!p) return;
    // the body and the creator's face as shown (the face comes along as face bones)
    const sims = p.anim.actors.map((a, k) => {
      const s = p.players[k].sample(p.frame);
      return { gender: a.gender, pose: sampleToPose(s), faceBones: sampleToFaceBones(s) };
    });
    const pr = { id: 'lib' + p.anim.id, label: p.anim.name, group: sims.length > 1 ? 'couple' : 'solo', sims, locations: p.anim.locations };
    this.stopPreview();
    app.applyPosePreset(pr);
  }
}
