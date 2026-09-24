// The sim's quick body switches and its settings (name, part, skin tone, colour).
import { h, section, toggleRow } from '../ui.js';
import { simBody } from '../pipeline.js';
import { simSettings } from '../steps/common.js';

export function bodyQuickSection(app, sim, view) {
  const b = simBody(sim);
  const quick = h('div', {});
  if (view && view.hasPenis) quick.append(toggleRow('Erection', b.erect ? 'Hard' : 'Soft', b.erect, on => app.setBody(sim.id, x => { x.erect = on; })));
  quick.append(toggleRow('Holes open by themselves', b.open.on ? 'On' : 'Off', b.open.on, on => app.setBody(sim.id, x => { x.open.on = on; })));
  quick.append(toggleRow('Physics', b.physics.on ? 'Breasts, butt and penis bounce' : 'Off', b.physics.on, on => app.setBody(sim.id, x => { x.physics.on = on; })));
  return section('Body', quick);
}

export function simSection(app, sim) { return section('Sim', simSettings(app, sim)); }
