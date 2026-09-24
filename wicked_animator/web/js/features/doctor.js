// Entry points for the Game Doctor and "Did it play in the game?" (R1-E): a Home card, palette commands (the Doctor,
// its Browse tab for Favorites and Turn off, "Did it play"), help rows, the line under every Send-to-game result
// (wa:sent), and one quiet look at WickedWhims' log when the window comes back after a send. Everything registers through app.hooks (plan 2.4), so main.js, index.html and app.css
// stay untouched.
import { openDoctor, openDidItPlay, onSent, checkPending, ensureIcons, ensureStyles } from '../doctor.js';

export function install(app) {
  if (!app || app.__doctor) return;
  app.__doctor = true;
  ensureIcons();
  ensureStyles();
  const hooks = app.hooks || {};
  const add = (name, fn) => { if (Array.isArray(hooks[name])) hooks[name].push(fn); };

  add('homeCards', () => [{
    id: 'doctor', icon: 'doctor', title: 'Check my game',
    text: "Why don't my animations show up? A safe check of your Mods and WickedWhims' settings.",
    onClick: () => openDoctor(app),
  }]);

  add('commands', a => [
    { group: 'Game', id: 'doctor', label: 'Doctor', icon: 'doctor', sub: "Check my game - why don't my animations show up?",
      words: 'check game mods why animations not showing missing broken fix scan conflict clash rig body folder disabled',
      run: () => openDoctor(a) },
    { group: 'Game', id: 'doctor-browse', label: 'Browse my WickedWhims animations', icon: 'doc-star',
      sub: 'favorites and "Turn off", for every animation you have',
      words: 'browse favorites favourite star turn off disable hide animations list installed mods wickedwhims identifier',
      run: () => openDoctor(a, { tab: 'browse' }) },
    { group: 'Game', id: 'did-it-play', label: 'Did it play in the game?', icon: 'doc-game',
      sub: "read WickedWhims' log for this animation", words: 'played test log worked game result wickedwhims',
      run: () => openDidItPlay(a) },
  ]);

  add('helpRows', () => [
    { group: 'The game', keys: ['Ctrl', 'K'], text: "Type \"Doctor\" to check why animations don't show up in the game" },
    { group: 'The game', keys: ['Ctrl', 'K'], text: 'Type "Did it play" to see if WickedWhims played your animation' },
    { group: 'The game', keys: ['Ctrl', 'K'], text: 'Type "Browse" to star favorites or turn off animations for WickedWhims' },
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
