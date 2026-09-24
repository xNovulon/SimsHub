// Pins and holds: a pinned hand or foot stays where it is while the body moves (for the whole loop or only part of
// it); a hand or foot holding on to a partner follows that body. Each limb is free, pinned, or holding - the ▾ menu
// (or a right-click) has the rest: pin for part of the loop, hold a named part, let go, let go and keep the look.
import { h, icon, section, contextMenu } from '../ui.js';
import { LIMBS, LIMB_LABEL, isHold, pinAt } from '../bones.js';
import * as Holds from '../holds.js';

const isMan = s => !!(s && s.gender === 'MALE' && s.frame === 'ym');
const partnerWord = s => (isMan(s) ? 'him' : 'her');           // "Hold him…"
const partnerPoss = s => (isMan(s) ? 'his' : 'her');           // "holding his forearm"
// holds shown before (sim|limb -> where it holds): a new or moved hold pops in once, not on every redraw
const seen = new Map();

// The frames of the selected keys on the timeline (spec_editing 2.5: 'k|simId|frame' ids), or null.
function selectedRange(app, simId) {
  const sel = app.timeline && app.timeline.sel;
  if (!sel || !sel.size) return null;
  const frames = [];
  for (const id of sel) {
    const m = /^k\|([^|]+)\|(\d+)$/.exec(id);
    if (m && (m[1] === simId || !frames.length)) frames.push(+m[2]);
  }
  return frames.length ? [Math.min(...frames), Math.max(...frames)] : null;
}
// From the playhead to the next body key (or the last frame).
function toNextKey(app, sim) {
  const f = Math.round(app.store.frame), L = app.store.project.length;
  const next = sim.keys.filter(k => !k.faceOnly && k.frame > f).map(k => k.frame).sort((a, b) => a - b)[0];
  return [f, next !== undefined ? next : L - 1];
}

function limbMenu(app, sim, limb, x, y) {
  const pin = sim.pins && sim.pins[limb];
  const hold = isHold(pin), pinned = !!pin && !hold;
  const ranged = pin && !Array.isArray(pin) && pin.from !== undefined;
  const items = [];
  const [f0, f1] = toNextKey(app, sim);
  const selR = selectedRange(app, sim.id);
  const what = hold ? 'Hold' : 'Pin';
  if (!pin) items.push({ label: 'Pin here for the whole loop', icon: 'pin', onClick: () => app.interact.togglePin(sim.id, limb) });
  else if (ranged) items.push({ label: `${what} for the whole loop`, icon: 'pin', onClick: () => Holds.setPin(app, sim.id, limb, {}) });
  if (f1 > f0) items.push({ label: `${what} only from here to the next key (${f0}-${f1})`, icon: 'pin', onClick: () => Holds.setPin(app, sim.id, limb, { from: f0, to: f1 }) });
  if (selR) items.push({ label: `${what} only for the selected part (${selR[0]}-${selR[1]})`, icon: 'pin', onClick: () => Holds.setPin(app, sim.id, limb, { from: selR[0], to: selR[1] }) });
  const others = app.store.project.sims.filter(s => s.id !== sim.id && s.visible !== false && app.simViews.get(s.id));
  if (others.length) {
    items.push('-');
    if (!hold) items.push({ label: 'Hold the nearest partner', icon: 'grab', onClick: () => Holds.holdNearest(app, sim.id, limb) });
    for (const o of others) {
      const parts = Holds.reachableGrabs(app, sim.id, limb, o.id);
      if (!parts.length) continue;
      items.push({ heading: `Hold ${others.length > 1 ? o.label + "'s" : partnerWord(o)}…` });
      // the 10 nearest parts, listed in the usual order (hip, waist, lower back, back...)
      const near = new Set([...parts].sort((x, y) => x.dist - y.dist).slice(0, 10).map(g => g.key));
      for (const g of parts.filter(x => near.has(x.key))) {
        items.push({ label: g.key[0].toUpperCase() + g.key.slice(1), dot: o.color, checked: hold && pin.sim === o.id && pin.label === g.key,
          onClick: () => Holds.holdNamed(app, sim.id, limb, o.id, g.key) });
      }
    }
  }
  if (pin) {
    items.push('-');
    items.push({ label: 'Let go', icon: 'letgo', onClick: () => Holds.letGo(app, sim.id, limb) });
    items.push({ label: 'Let go, keep the look', icon: 'key', onClick: () => Holds.bakePin(app, sim.id, limb) });
  }
  contextMenu(x, y, items);
}

export function pinSection(app, sim) {
  // one row per hand / foot: free, pinned (for the whole loop or part of it), or holding the partner (a chip in the
  // partner's colour; amber when the arm can't reach at the frame shown). A click pins / lets go; ▾ has the rest.
  const grid = h('div', { class: 'pin-grid pin-list' });
  const reach = (app.pipeline && app.pipeline.reach && app.pipeline.reach.get(sim.id)) || {};
  const many = app.store.project.sims.length > 2;
  for (const limb of Object.keys(LIMBS)) {
    const pin = (sim.pins || {})[limb];
    const hold = isHold(pin), on = !!pin;
    const ranged = pin && !Array.isArray(pin) && pin.from !== undefined;
    const partner = hold && app.store.sim(pin.sim);
    const far = hold && (reach[limb] || 0) > 0.01;
    const who = partner ? (many ? `${partner.label}'s` : partnerPoss(partner)) : "the partner's";
    const state = hold ? `holding ${who} ${pin.label || 'body'}${ranged ? ` · ${pin.from}-${pin.to}` : ''}` : on ? (ranged ? `pinned ${pin.from}-${pin.to}` : 'pinned') : 'free';
    const title = hold ? `${LIMB_LABEL[limb]} is ${Holds.holdText(app, pin)} - it follows the body${far ? ". It can't reach there at this frame - move the sims closer or let go" : ''}. Click to let go.`
      : on ? (ranged ? `Pinned from frame ${pin.from} to ${pin.to} - click to let go` : 'Pinned: stays put while the body moves - click to let go') : 'Pin it where it is now (▾: hold the partner, pin for part of the loop)';
    const sig = hold ? `${pin.sim}|${pin.bone}|${(pin.off || []).join()}` : '';
    const fresh = hold && seen.has(`${sim.id}|${limb}`) && seen.get(`${sim.id}|${limb}`) !== sig;
    seen.set(`${sim.id}|${limb}`, sig);
    const btn = h('button', { class: 'pin' + (on ? ' on' : '') + (hold ? ' held hold-chip' : '') + (fresh ? ' grab' : '') + (far ? ' far' : ''), style: partner ? { '--partner': partner.color } : null,
      onclick: () => app.interact.togglePin(sim.id, limb), title },
      hold ? h('span', { class: 'pdot' }) : null, h('span', { class: 'lbl' }, LIMB_LABEL[limb]),
      h('span', { class: 'state' }, far ? "can't reach here" : state));
    btn.addEventListener('contextmenu', e => { e.preventDefault(); limbMenu(app, sim, limb, e.clientX, e.clientY); });
    const more = h('button', { class: 'pin-more', title: 'More: hold the partner, pin for part of the loop, let go…', 'aria-label': `${LIMB_LABEL[limb]} options`,
      onclick: e => { const r = e.currentTarget.getBoundingClientRect(); limbMenu(app, sim, limb, r.left - 160, r.bottom + 4); } }, icon('down'));
    grid.append(h('div', { class: 'pin-cell' }, btn, more));
  }
  const pinnedAny = Object.values(sim.pins || {}).some(p => p && !isHold(p) && pinAt(p));
  const hint = h('div', { class: 'hint' },
    'In the Drag tool (G), drop a hand or foot on the partner and it holds on - it follows the body. Drag it away to let go.',
    pinnedAny ? ' "Let go, keep the look" (▾) turns a pinned arm or leg into keys, so nothing jumps when it is free.' : '');
  return section(['Pins & holds', h('span', { class: 'count' }, 'hands and feet')], grid, hint);
}
