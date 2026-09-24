// Pose packs for Pose Player and the promo kit (R2-6): the icons, palette commands (Ctrl+K) and Help rows. The Share
// step's "Show it off" section lives in web/js/share.js; the tools themselves (web/js/promo.js, posepack.js, gif.js)
// load only when used. Everything registers through app.hooks (plan 2.4).
import { ensureShareIcons, openPromo, openPoses } from '../share.js';
import { $t } from '../i18n.js';

export function install(app) {
  if (!app || app.__share26) return;
  app.__share26 = true;
  ensureShareIcons();
  const hooks = app.hooks || {};
  const add = (name, fn) => { if (Array.isArray(hooks[name])) hooks[name].push(fn); };
  const hasSims = a => !!(a.store && a.store.project && a.store.project.sims.length);

  add('commands', a => [
    { group: $t('features.share.share'), id: 'promo-kit', label: $t('features.share.make_promo_kit'), icon: 'pk-gif', sub: $t('features.share.looping_gifs_thumbnail_video_and'),
      words: 'gif gifs thumbnail preview video promo post tumblr advertise release trailer teaser screenshot', run: () => openPromo(a), when: () => hasSims(a) },
    { group: $t('features.share.share'), id: 'pose-pack', label: $t('features.share.export_as_pose_pack'), icon: 'pp-couple', sub: $t('features.share.for_andrew_s_pose_player'),
      words: 'pose player poses pack s4s sims 4 studio screenshot story couple', run: () => openPoses(a), when: () => hasSims(a) },
  ]);

  add('helpRows', () => [
    { group: $t('features.share.show_it_off'), keys: ['Ctrl', 'K'], text: $t('features.share.type_promo_for_looping_gifs') },
    { group: $t('features.share.show_it_off'), keys: ['Ctrl', 'K'], text: $t('features.share.type_pose_pack_to_make') },
  ]);

  window.wickedShare = { promo: () => openPromo(app), posePack: () => openPoses(app) };
}

export default install;
