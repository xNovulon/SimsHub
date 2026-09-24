// "All bones": every bone Blender animators key, in one searchable list (like Blender's outliner). Each row: a status
// dot, the plain name and the rig's own name. Click a row to pick that bone (face bones open the Face tool).
import { h, icon } from './ui.js';
import { localStorageGet, localStorageSet } from './state.js';
import { PARTS } from './physics.js';
import { simBody } from './pipeline.js';
import { BONE_GROUPS, FACE_SET, TWIST_SET, EXPERT_SET, label, boneMatches, isFace, setPickMode } from './facekit.js';
import { $t } from './i18n.js';

const PHYS = new Set(Object.values(PARTS).flatMap(p => [...p.bones, p.swing].filter(Boolean)));
const NEAR = 0.0035;                     // 0.2 degrees (quaternion angle) / 0.2 mm - "away from rest"

// Which rows a body has: no penis rows without a penis, no vagina rows on a male body.
function bodyHas(view, sim, n) {
  if (!view || !view.byName[n]) return false;
  if (/^b__Penis_(Base|Mid|Tip)/.test(n) || n === 'b__Penis_Testicles') return !!view.hasPenis;
  if (/Vagina/.test(n)) return sim.frame !== 'ym';
  if (/^b__Penis_(L|R)_Testicle$/.test(n)) return !!view.hasPenis || sim.frame !== 'ym';
  return true;
}

// status of a bone at this frame: 'keyed' | 'animated' | 'auto' | 'rest'
function statusOf(app, sim, view, n, frame) {
  const r = view.restByName[n];
  if (!r) return 'rest';
  const away = key => {
    const src = FACE_SET.has(n) ? key.faceBones : key.pose;
    if (!src) return false;
    const q = src.rot && src.rot[n], t = src.pos && src.pos[n];
    if (q && Math.abs(q[0] * r.quat.x + q[1] * r.quat.y + q[2] * r.quat.z + q[3] * r.quat.w) < Math.cos(NEAR / 2)) return true;
    if (t && Math.hypot(t[0] - r.pos.x, t[1] - r.pos.y, t[2] - r.pos.z) > 0.0002) return true;
    return false;
  };
  const here = sim.keys.find(k => k.frame === frame);
  if (here && away(here)) return 'keyed';
  if (sim.keys.some(away)) return 'animated';
  if (TWIST_SET.has(n)) return 'auto';
  const b = simBody(sim);
  if (PHYS.has(n) && b.physics && b.physics.on) return 'auto';
  if (isFace(n) && sim.keys.some(k => k.face && Object.values(k.face).some(x => Math.abs(x) > 0.01))) return 'auto';
  return 'rest';
}

const STATUS_TIP = { keyed: $t('outliner.posed_in_key_at_this'), animated: $t('outliner.animated_posed_in_another_key'), auto: $t('outliner.moves_by_itself'), rest: $t('outliner.at_rest') };

export function boneList(app, sim, view) {
  const open = !!localStorageGet('boneListOpen', false);
  const filter = app._boneFilter || (app._boneFilter = localStorageGet('boneFilter', { keyed: false, face: false, expert: false }) || {});
  const frame = Math.round(app.store.frame);
  const sel = app.store.selected.sim === sim.id ? app.store.selected.bone : null;
  const box = h('div', { class: 'bone-list' });
  const details = h('details', { class: 'section bone-list-wrap', open: open ? true : null },
    h('summary', { class: 'section-title' }, icon('search'), $t('outliner.all_bones'), h('span', { class: 'count' }, $t('outliner.every_bone_like_blender'))), box);
  details.addEventListener('toggle', () => {
    localStorageSet('boneListOpen', details.open);
    if (details.open && !box.childElementCount) build();
  });
  let rows = [], active = -1;
  const search = h('input', { class: 'text', type: 'search', placeholder: $t('outliner.find_bone_brow_lip_b'), spellcheck: 'false', value: app._boneQuery || '' });
  const list = h('div', { class: 'bone-groups' });
  const chip = (key, text, title) => h('button', { class: 'chip' + (filter[key] ? ' on' : ''), title, onclick: e => {
    filter[key] = !filter[key];
    localStorageSet('boneFilter', filter);
    e.currentTarget.classList.toggle('on', filter[key]);
    fill();
  } }, text);

  function fill() {
    list.innerHTML = '';
    rows = []; active = -1;
    const q = search.value.trim();
    for (const g of BONE_GROUPS) {
      if (g.expert && !filter.expert) continue;
      if (filter.face && !g.face) continue;
      const subs = g.sub ? g.sub : [{ label: null, bones: g.bones || [] }];
      const groupRows = [];
      let count = 0, holdsSel = false;
      for (const sg of subs) {
        const items = [];
        for (const n of sg.bones) {
          if (!bodyHas(view, sim, n)) continue;
          if (!boneMatches(n, q, sim.frame)) continue;
          const st = statusOf(app, sim, view, n, frame);
          if (filter.keyed && st !== 'keyed' && st !== 'animated') continue;
          if (n === sel) holdsSel = true;
          items.push(row(n, st));
        }
        if (!items.length) continue;
        count += items.length;
        if (sg.label) groupRows.push(h('div', { class: 'bone-sub' }, sg.label));
        groupRows.push(...items);
      }
      if (!count) continue;
      const openG = holdsSel || !!q || filter.keyed || (app._boneOpen || {})[g.id];
      const d = h('details', { class: 'bone-group', open: openG ? true : null },
        h('summary', {}, h('span', {}, g.label), h('span', { class: 'n' }, String(count))), ...groupRows);
      d.addEventListener('toggle', () => { (app._boneOpen = app._boneOpen || {})[g.id] = d.open; });
      // opened by a click: its rows bloom in once (a redraw of the panel never replays it)
      d.firstChild.addEventListener('click', () => {
        d.classList.add('blooming');
        clearTimeout(d._bloomT); d._bloomT = setTimeout(() => d.classList.remove('blooming'), 400);
      });
      list.append(d);
    }
    if (!list.childElementCount) list.append(h('div', { class: 'hint' }, $t('outliner.no_bone_matches')));
    rows = [...list.querySelectorAll('.bone-row')];
  }

  function row(n, st) {
    const b = h('button', { class: 'bone-row' + (n === sel ? ' on' : '') + (app._hotBone === n ? ' hot' : ''), 'data-bone': n, title: STATUS_TIP[st],
      onclick: () => app.selectBoneByName(sim.id, n),
      // hovering a row lights that part on the body (a face part in the face pick mode, so only it glows)
      onpointerenter: () => { if (view) { const k = view.index(n); if (k >= 0) { view._listHover = true; setPickMode(view, isFace(n) ? 'face' : 'body'); view.hover(k); } } },
      onpointerleave: () => { if (view) { view._listHover = false; view.hover(-1); } } },
    h('span', { class: 'dot ' + st }), h('span', { class: 'nm' }, label(n, sim.frame)), h('code', { title: n }, n),
    st === 'auto' ? h('span', { class: 'badge auto' }, 'auto') : EXPERT_SET.has(n) ? h('span', { class: 'badge' }, 'expert') : null);
    return b;
  }

  function move(d) {
    if (!rows.length) return;
    rows.forEach(r => r.classList.remove('kb'));
    active = (active + d + rows.length) % rows.length;
    rows[active].classList.add('kb');
    rows[active].scrollIntoView({ block: 'nearest' });
  }

  function build() {
    box.append(h('div', { class: 'bone-search' }, icon('search'), search),
      h('div', { class: 'bone-chips' },
        chip('keyed', $t('outliner.keyed'), $t('outliner.only_bones_posed_in_key')),
        chip('face', $t('outliner.face'), $t('outliner.only_face')),
        chip('expert', $t('outliner.expert'), $t('outliner.also_expert_bones_shape_and'))),
      list);
    fill();
  }
  search.addEventListener('input', () => { app._boneQuery = search.value; fill(); });
  search.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
    else if (e.key === 'Enter') { e.preventDefault(); const r = rows[active >= 0 ? active : 0]; if (r) r.click(); }
    else if (e.key === 'Escape') { search.value = ''; app._boneQuery = ''; fill(); search.blur(); }
  });
  if (open) build();
  details._focusSearch = () => {
    if (!details.open) { details.open = true; }
    if (!box.childElementCount) build();
    search.focus(); search.select();
  };
  details.id = 'bone-list';
  return details;
}
