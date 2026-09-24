// Entry points for the Game Doctor and "Did it play in the game?" (R1-E): a Home card, palette commands (the Doctor,
// its Browse tab for Favorites and Turn off, "Did it play"), help rows, the line under every Send-to-game result
// (wa:sent), and one quiet look at WickedWhims' log when the window comes back after a send. Everything registers through app.hooks (plan 2.4), so main.js, index.html and app.css
// stay untouched.
import { openDoctor, openDidItPlay, onSent, checkPending, ensureIcons, ensureStyles } from '../doctor.js';
import { $t } from '../i18n.js';

export function install(app) {
  if (!app || app.__doctor) return;
  app.__doctor = true;
  ensureIcons();
  ensureStyles();
  const hooks = app.hooks || {};
  const add = (name, fn) => { if (Array.isArray(hooks[name])) hooks[name].push(fn); };

  add('homeCards', () => [{
    id: 'doctor', icon: 'doctor', title: $t('features.doctor.check_my_game'),
    text: $t('features.doctor.why_don_t_my_animations'),
    onClick: () => openDoctor(app),
  }]);

  add('commands', a => [
    { group: $t('features.doctor.game'), id: 'doctor', label: $t('features.doctor.doctor'), icon: 'doctor', sub: $t('features.doctor.check_my_game_why_don'),
      words: 'check game mods why animations not showing missing broken fix scan conflict clash rig body folder disabled',
      run: () => openDoctor(a) },
    { group: $t('features.doctor.game'), id: 'doctor-browse', label: $t('features.doctor.browse_my_wickedwhims_animations'), icon: 'doc-star',
      sub: $t('features.doctor.favorites_and_turn_off_for'),
      words: 'browse favorites favourite star turn off disable hide animations list installed mods wickedwhims identifier',
      run: () => openDoctor(a, { tab: 'browse' }) },
    { group: $t('features.doctor.game'), id: 'did-it-play', label: $t('features.doctor.did_it_play_in_game'), icon: 'doc-game',
      sub: $t('features.doctor.read_wickedwhims_log_for_this'), words: 'played test log worked game result wickedwhims',
      run: () => openDidItPlay(a) },
  ]);

  add('helpRows', () => [
    { group: $t('features.doctor.game_2'), keys: ['Ctrl', 'K'], text: $t('features.doctor.type_doctor_to_check_why') },
    { group: $t('features.doctor.game_2'), keys: ['Ctrl', 'K'], text: $t('features.doctor.type_did_it_play_to') },
    { group: $t('features.doctor.game_2'), keys: ['Ctrl', 'K'], text: $t('features.doctor.type_browse_to_star_favorites') },
  ]);

  // the Send result's bottom slot
  const sent = d => { try { onSent(app, d); } catch (e) { console.error('Did it play:', e); } };
  if (typeof app.on === 'function') app.on('sent', sent);
  else window.addEventListener('wa:sent', e => sent(e.detail));

  // back from the game: one look at the log (never while typing, never more than every 15 s)
  const back = () => { if (document.visibilityState === 'visible') checkPending(app).catch(() => {}); };
  window.addEventListener('focus', back);
  document.addEventListener('visibilitychange', back);

  window.wickedDoctor = { open: () => openDoctor(app), browse: () => openDoctor(app, { tab: 'browse' }), didItPlay: opts => openDidItPlay(app, opts) };
}

export default install;
