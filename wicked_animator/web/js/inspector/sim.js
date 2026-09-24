// The sim's quick body switches and its settings (name, part, skin tone, colour).
import { h, section, toggleRow } from '../ui.js';
import { simBody } from '../pipeline.js';
import { simSettings } from '../steps/common.js';
import { $t } from '../i18n.js';

export function bodyQuickSection(app, sim, view) {
  const b = simBody(sim);
  const quick = h('div', {});
  if (view && view.hasPenis) quick.append(toggleRow($t('inspector.sim.erection'), b.erect ? $t('inspector.sim.hard') : $t('inspector.sim.soft'), b.erect, on => app.setBody(sim.id, x => { x.erect = on; })));
  quick.append(toggleRow($t('inspector.sim.holes_open_by_themselves'), b.open.on ? $t('inspector.sim.on') : $t('inspector.sim.off'), b.open.on, on => app.setBody(sim.id, x => { x.open.on = on; })));
  quick.append(toggleRow($t('inspector.sim.physics'), b.physics.on ? $t('inspector.sim.breasts_butt_and_penis_bounce') : $t('inspector.sim.off'), b.physics.on, on => app.setBody(sim.id, x => { x.physics.on = on; })));
  return section($t('inspector.sim.body'), quick);
}

export function simSection(app, sim) { return section($t('inspector.sim.sim'), simSettings(app, sim)); }
