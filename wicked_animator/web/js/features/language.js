// The app's language: a picker in Help (Controls), and Ctrl+K commands ("Language: Deutsch"...). The choice is saved
// in the app's settings on this PC (/api/settings) and the app starts again in it; unsaved work goes through the
// recovery file like on any close, and is offered back when the app opens. See web/js/i18n.js.
import { h, confirmBox, addIcon } from '../ui.js';
import { $t, LANGUAGES, getLanguage, setLanguage, languageName } from '../i18n.js';

// words people type in the palette to find the language commands, in every language we have
const WORDS = 'language languages idioma idiomas lengua língua langue langues sprache sprachen lingua lingue język jezyk translate translation';

export async function switchLanguage(app, code) {
  if (!code || code === getLanguage()) return false;
  const dirty = !!(app && app.store && app.store.dirty);
  if (dirty && !(await confirmBox($t('features.language.confirm_title'), $t('features.language.confirm_text', { language: languageName(code) }),
    $t('features.language.confirm_ok'), false))) return false;
  await setLanguage(code);
  return true;
}

// a <select> with every language, the current one picked
export function languageSelect(app) {
  const sel = h('select', { class: 'lang-select', 'aria-label': $t('features.language.language') },
    LANGUAGES.map(l => h('option', { value: l.code, selected: l.code === getLanguage(), lang: l.code }, l.name)));
  sel.addEventListener('change', async () => {
    const ok = await switchLanguage(app, sel.value);
    if (!ok) sel.value = getLanguage();
  });
  return sel;
}

export function install(app) {
  if (!app || app.__language) return;
  app.__language = true;
  addIcon('lang', '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.6 5.2 3.6 8.5s-1.2 6.1-3.6 8.5c-2.4-2.4-3.6-5.2-3.6-8.5s1.2-6.1 3.6-8.5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>');
  const hooks = app.hooks || {};
  const add = (name, fn) => { if (Array.isArray(hooks[name])) hooks[name].push(fn); };

  add('commands', a => LANGUAGES.map(l => ({
    group: $t('features.language.group'), id: 'lang-' + l.code, icon: 'lang', words: WORDS + ' ' + l.code,
    label: $t('features.language.command', { language: l.name }),
    sub: l.code === getLanguage() ? $t('features.language.current') : $t('features.language.restarts'),
    run: () => switchLanguage(a, l.code),
  })));

  // Help > the language row: the picker sits where the keys usually are
  add('helpRows', a => [{ group: $t('features.language.group'), keys: languageSelect(a), text: $t('features.language.help_text') }]);

  window.wickedLanguage = { set: code => switchLanguage(app, code), get: getLanguage, list: () => LANGUAGES.map(l => l.code) };
}

export default install;
