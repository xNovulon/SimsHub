// Shared bits of the step panels: the sim pills and the sim settings card.
import { h } from '../ui.js';
import { SIM_COLORS } from '../bones.js';

export const nice = s => s.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
export const pct = v => Math.round(v * 100) + '%';

// A row of sim pills to choose which sim a panel works on.
export function simTabs(app, onPick) {
  const p = app.store.project;
  const sel = app.store.selected.sim;
  return h('div', { class: 'seg-inline', style: { marginBottom: '10px' } }, p.sims.map(s => h('button', {
    class: s.id === sel ? 'on' : '', style: s.id === sel ? { boxShadow: `inset 0 -2px 0 ${s.color}` } : {},
    onclick: () => { app.selectSim(s.id); onPick && onPick(s); },
  }, s.label)));
}

// ---------------------------------------------------------------- sim settings (inspector)
export function simSettings(app, sim) {
  const name = h('input', { class: 'text', value: sim.label });
  name.addEventListener('change', () => { app.store.checkpoint(); sim.label = name.value || sim.label; app.refreshPanels(); });
  const role = h('select', {}, [['FEMALE', 'Female part'], ['MALE', 'Male part (gives)'], ['BOTH', 'Either']].map(([v, t]) => h('option', { value: v, selected: sim.gender === v }, t)));
  role.addEventListener('change', () => { app.store.checkpoint(); sim.gender = role.value; app.store.setDirty(true); app.refreshPanels(); });
  return h('div', {},
    h('label', { class: 'field' }, h('span', {}, 'Name'), name),
    h('label', { class: 'field' }, h('span', {}, 'Which sims WickedWhims casts in this part'), role),
    h('div', { class: 'field' }, h('span', {}, "Skin tone (the game's own skins)"), h('div', { class: 'swatches' }, pickTones(app.tones).map(t => h('button', {
      class: (sim.tone || '') === t.hex ? 'active' : '', style: { background: t.swatch }, title: t.type || '', onclick: () => app.setTone(sim.id, t.hex) })))),
    h('div', { class: 'field' }, h('span', {}, 'Colour in the app'), h('div', { class: 'swatches' }, SIM_COLORS.map(c => h('button', { class: sim.color === c ? 'active' : '', style: { background: c }, onclick: () => app.setColor(sim.id, c) })))));
}

// A spread of the game's skin tones, light to dark (the default tone first).
function pickTones(tones) {
  if (!tones || !tones.length) return [{ hex: '', swatch: '#f0c7a6', type: 'default' }];
  const lum = t => { const n = parseInt(t.swatch.slice(1), 16); return 0.3 * (n >> 16) + 0.59 * ((n >> 8) & 255) + 0.11 * (n & 255); };
  const human = tones.filter(t => !/misc|green|blue|purple/i.test(t.type || '') && lum(t) > 40).sort((a, b) => lum(b) - lum(a));
  const out = [{ hex: '', swatch: '#f3cfb1', type: 'default' }];
  const n = 13;
  for (let k = 0; k < n; k++) out.push(human[Math.round(k * (human.length - 1) / (n - 1))]);
  return out.filter(Boolean);
}
