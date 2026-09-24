// The app's languages: message catalogs (web/i18n/<code>.json), t(key, vars) with plurals, numbers and dates, and
// the static text of index.html (data-i18n attributes).
//
//   import { $t } from './i18n.js';
//   $t('scene.add_sim')                              -> "Add a sim"
//   $t('scene.keys', { n: 3 })                       -> "3 keys"     ("{n, plural, one {# key} other {# keys}}")
//   $t('home.total', { n: 12345 })                   -> "12,345 animations" / "12.345 Animationen"
//
// Message syntax (a small part of ICU MessageFormat, the same in every catalog):
//   {name}                      the value (a number gets the language's decimal sign, no thousands separator)
//   {name, number}              a number with thousands separators
//   {name, plural, one {..} few {..} many {..} other {..} =0 {..}}   the form for the language's plural rules;
//                               # inside is the number
//   {name, select, her {..} him {..} other {..}}                     a form picked by a word
//   {name, date} {name, datetime} {name, time}                       a Date, or seconds / milliseconds since 1970
//
// The language is picked once, before any other module runs (this file uses top-level await, and every module that
// shows text imports it): ?lang=xx in the address (checks), else the one saved in the app's settings on this PC
// (/api/settings), else the browser's / Windows' language on the first start (then saved). Changing it saves it
// and reloads the app (unsaved work goes through the recovery file, like any close).
// Modules import it as $t: `t` is taken by many local variables (times, tweens) in this code.

export const LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'es', name: 'Español' },
  { code: 'pt-BR', name: 'Português (Brasil)' },
  { code: 'fr', name: 'Français' },
  { code: 'de', name: 'Deutsch' },
  { code: 'it', name: 'Italiano' },
  { code: 'pl', name: 'Polski' },
];
export const DEFAULT_LANGUAGE = 'en';
const CODES = LANGUAGES.map(l => l.code);
const BROWSER = typeof window !== 'undefined' && typeof document !== 'undefined' && typeof fetch === 'function';

// The best of our languages for a list of language tags ("de-AT", "pt", "es-419"...), or 'en'.
export function matchLanguage(tags) {
  const list = (Array.isArray(tags) ? tags : [tags]).filter(Boolean).map(x => String(x).trim().replace('_', '-'));
  for (const tag of list) {
    const exact = CODES.find(c => c.toLowerCase() === tag.toLowerCase());
    if (exact) return exact;
    const base = tag.split('-')[0].toLowerCase();
    const same = CODES.find(c => c.split('-')[0].toLowerCase() === base);
    if (same) return same;
  }
  return DEFAULT_LANGUAGE;
}

let lang = DEFAULT_LANGUAGE;
let messages = {};            // the chosen language
let english = {};             // what a message missing in it falls back to
const missing = new Set();    // keys asked for that no catalog has (the checks look at window.__i18nMissing)

async function readCatalog(code) {
  if (!BROWSER) {
    const fs = await import('node:fs');
    try { return JSON.parse(fs.readFileSync(new URL(`../i18n/${code}.json`, import.meta.url), 'utf8')); } catch { return {}; }
  }
  try {
    const r = await fetch(`i18n/${code}.json`, { cache: 'no-cache' });
    return r.ok ? await r.json() : {};
  } catch { return {}; }
}

async function savedLanguage() {
  try {
    const r = await fetch('/api/settings', { cache: 'no-store' });
    if (r.ok) { const s = await r.json(); if (s && s.language) return s.language; }
  } catch { /* an older server without settings */ }
  try { return localStorage.getItem('wa.language'); } catch { return null; }
}

function saveLanguage(code, auto = false) {
  try { localStorage.setItem('wa.language', code); } catch { /* storage blocked */ }
  return fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language: code, language_auto: !!auto }) }).then(r => r.ok).catch(() => false);
}

async function boot() {
  if (!BROWSER) { english = await readCatalog('en'); messages = english; return; }
  const asked = new URLSearchParams(location.search).get('lang');
  let saved = null;
  if (asked) lang = matchLanguage([asked]);
  else {
    saved = await savedLanguage();
    lang = saved && CODES.includes(saved) ? saved : matchLanguage(navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language]);
    if (!saved) saveLanguage(lang, true);          // the first start: remembered from now on
  }
  const [en, own] = await Promise.all([readCatalog('en'), lang === 'en' ? null : readCatalog(lang)]);
  english = en;
  messages = own || en;
  document.documentElement.lang = lang;
  window.__i18nMissing = missing;
  applyTranslations(document);
  // the few lines index.html shows before (or without) any module, in this language next time
  try {
    localStorage.setItem('wa.i18n.boot', JSON.stringify(Object.fromEntries(
      ['boot.loading', 'boot.waking', 'boot.failed', 'boot.offline', 'boot.part_missing', 'boot.engine_missing', 'boot.css_missing', 'boot.error', 'boot.reload']
        .map(k => [k, t(k)]))));
  } catch { /* storage blocked */ }
}

export const getLanguage = () => lang;
export const languageName = code => (LANGUAGES.find(l => l.code === code) || {}).name || code;

// Change the language: saved in the app's settings, then the app starts again in it.
export async function setLanguage(code, { reload = true } = {}) {
  code = matchLanguage([code]);
  await saveLanguage(code);
  if (reload && BROWSER) {
    const u = new URL(location.href);
    u.searchParams.delete('lang');
    location.replace(u.toString());
  }
  return code;
}

// ---------------------------------------------------------------- formatting
const nf = {};
const numberFormat = (opts = {}) => {
  const k = lang + JSON.stringify(opts);
  return nf[k] || (nf[k] = new Intl.NumberFormat(lang, opts));
};
// 1234.5 -> "1,234.5" (en) / "1.234,5" (de) / "1 234,5" (fr, pl)
export const fmtNumber = (n, opts) => (Number.isFinite(+n) ? numberFormat(opts).format(+n) : String(n));
const plainNumber = n => numberFormat({ useGrouping: false, maximumFractionDigits: 3 }).format(n);
const toDate = v => (v instanceof Date ? v : new Date(typeof v === 'number' && v < 1e11 ? v * 1000 : v));
export const fmtDate = (d, opts = { dateStyle: 'medium' }) => new Intl.DateTimeFormat(lang, opts).format(toDate(d));
export const fmtDateTime = d => fmtDate(d, { dateStyle: 'medium', timeStyle: 'short' });
// ['a', 'b', 'c'] -> "a, b and c" / "a, b y c" / "a, b und c"
export const fmtList = list => { const a = (list || []).map(String); try { return new Intl.ListFormat(lang, { style: 'long', type: 'conjunction' }).format(a); } catch { return a.join(', '); } };
let pr = null, prLang = null;
export function pluralCategory(n) {
  if (prLang !== lang) { pr = new Intl.PluralRules(lang); prLang = lang; }
  return pr.select(Math.abs(+n) || 0);
}

// ---------------------------------------------------------------- the message syntax
// Splits "a {x} b {n, plural, one {# c} other {# d}}" at the top level: [text, {arg, type, rest}, text...]
function parse(msg) {
  const out = [];
  let i = 0, text = '';
  while (i < msg.length) {
    const c = msg[i];
    if (c !== '{') { text += c; i++; continue; }
    let depth = 1, j = i + 1;
    while (j < msg.length && depth) { if (msg[j] === '{') depth++; else if (msg[j] === '}') depth--; j++; }
    if (depth) { text += msg.slice(i); break; }             // an unclosed brace is plain text
    if (text) out.push(text), (text = '');
    const inner = msg.slice(i + 1, j - 1);
    const m = /^\s*([\w.]+)\s*(?:,\s*(\w+)\s*(?:,([\s\S]*))?)?$/.exec(inner);
    out.push(m ? { arg: m[1], type: m[2] || '', rest: m[3] || '' } : '{' + inner + '}');
    i = j;
  }
  if (text) out.push(text);
  return out;
}

// "one {# key} other {# keys}" -> {one: '# key', other: '# keys'}
function options(rest) {
  const o = {};
  const rx = /\s*(=?[\w-]+)\s*\{/g;
  let m;
  while ((m = rx.exec(rest))) {
    let depth = 1, j = rx.lastIndex;
    while (j < rest.length && depth) { if (rest[j] === '{') depth++; else if (rest[j] === '}') depth--; j++; }
    o[m[1]] = rest.slice(rx.lastIndex, j - 1);
    rx.lastIndex = j;
  }
  return o;
}

const cache = new Map();
export function format(msg, vars = {}, _hash) {
  let parts = cache.get(msg);
  if (!parts) { parts = parse(msg); cache.set(msg, parts); }
  let out = '';
  for (const p of parts) {
    if (typeof p === 'string') { out += _hash === undefined ? p : p.replace(/#/g, _hash); continue; }
    const v = vars[p.arg];
    if (p.type === 'plural' || p.type === 'select') {
      const o = options(p.rest);
      let pick;
      if (p.type === 'plural') {
        const n = +v || 0;
        pick = o['=' + n] !== undefined ? o['=' + n] : o[pluralCategory(n)] !== undefined ? o[pluralCategory(n)] : o.other;
        out += format(pick || '', vars, fmtNumber(n));
      } else {
        pick = o[String(v)] !== undefined ? o[String(v)] : o.other;
        out += format(pick || '', vars, _hash);
      }
    } else if (v === undefined || v === null) out += '';
    else if (p.type === 'number') out += fmtNumber(v);
    else if (p.type === 'date') out += fmtDate(v);
    else if (p.type === 'datetime') out += fmtDateTime(v);
    else if (p.type === 'time') out += fmtDate(v, { timeStyle: 'short' });
    else out += typeof v === 'number' ? plainNumber(v) : String(v);
  }
  return out;
}

// The text for `key` in the app's language (English when it has none), with vars filled in.
export function t(key, vars) {
  let msg = messages[key];
  if (msg === undefined) msg = english[key];
  if (msg === undefined) {
    if (!missing.has(key)) { missing.add(key); if (BROWSER) console.warn('i18n: no text for', key); }
    return key;
  }
  return vars || msg.indexOf('{') >= 0 ? format(msg, vars || {}) : msg;
}
export const $t = t;
// A name (a furniture's, a body part's) as it reads inside a sentence: "Double bed" -> "double bed". German keeps
// its capitals (nouns are always capitalised there).
export const inSentence = s => (s && lang !== 'de' && !/^[A-Z]{2}/.test(s) ? s.charAt(0).toLowerCase() + s.slice(1) : s || '');
// Is there a text for this key (in any catalog)?
export const hasText = key => messages[key] !== undefined || english[key] !== undefined;

// ---------------------------------------------------------------- index.html
// data-i18n="key"          the element's own text (its child elements - icons, <kbd> - stay)
// data-i18n-html="key"     its whole content, from a message with markup in it
// data-i18n-title / -placeholder / -aria-label / -alt="key"   that attribute
export function applyTranslations(root = document) {
  const each = (sel, fn) => root.querySelectorAll(sel).forEach(el => { try { fn(el); } catch (e) { console.error('i18n', e); } });
  each('[data-i18n]', el => {
    const text = t(el.getAttribute('data-i18n'));
    const nodes = [...el.childNodes].filter(n => n.nodeType === 3 && n.nodeValue.trim());
    if (!el.children.length || !nodes.length) el.textContent = text;
    else { nodes[nodes.length - 1].nodeValue = text; nodes.slice(0, -1).forEach(n => n.remove()); }
  });
  each('[data-i18n-html]', el => { el.innerHTML = t(el.getAttribute('data-i18n-html')); });
  for (const attr of ['title', 'placeholder', 'aria-label', 'alt']) each(`[data-i18n-${attr}]`, el => el.setAttribute(attr, t(el.getAttribute(`data-i18n-${attr}`))));
}

await boot();
