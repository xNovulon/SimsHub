// Pose packs for Pose Player and the promo kit (R2-6): the icons, palette commands (Ctrl+K) and Help rows. The Share
// step's "Show it off" section lives in web/js/share.js; the tools themselves (web/js/promo.js, posepack.js, gif.js)
// load only when used. Everything registers through app.hooks (plan 2.4).
import { ensureShareIcons, openPromo, openPoses } from '../share.js';

export function install(app) {
  if (!app || app.__share26) return;
  app.__share26 = true;
  ensureShareIcons();
  const hooks = app.hooks || {};
  const add = (name, fn) => { if (Array.isArray(hooks[name])) hooks[name].push(fn); };
  const hasSims = a => !!(a.store && a.store.project && a.store.project.sims.length);

  add('commands', a => [
    { group: 'Share', id: 'promo-kit', label: 'Make a promo kit', icon: 'pk-gif', sub: 'looping GIFs, a thumbnail, a video and the text to post',
      words: 'gif gifs thumbnail preview video promo post tumblr advertise release trailer teaser screenshot', run: () => openPromo(a), when: () => hasSims(a) },
    { group: 'Share', id: 'pose-pack', label: 'Export as a pose pack', icon: 'pp-couple', sub: "for Andrew's Pose Player - non-explicit poses only",
      words: 'pose player poses pack s4s sims 4 studio screenshot story couple', run: () => openPoses(a), when: () => hasSims(a) },
  ]);

  add('helpRows', () => [
    { group: 'Show it off', keys: ['Ctrl', 'K'], text: 'Type "promo" for looping GIFs, a thumbnail, a video and the text to post' },
    { group: 'Show it off', keys: ['Ctrl', 'K'], text: 'Type "pose pack" to make a Pose Player pack from your keys (non-explicit poses only)' },
  ]);

  window.wickedShare = { promo: () => openPromo(app), posePack: () => openPoses(app) };
}

export default install;
