// Novulon's Sims Hub - languages. The words of the app live in i18n/<code>.json (one flat catalog per language,
// English is the reference and the fallback); this module picks the language, looks words up and formats numbers
// and dates for it. It has no DOM work at import time, so node can test it too (tests/test_i18n.py).
//
//   t('saves.play')                       plain text (for textContent, titles, toasts)
//   t('saves.sims', { n: 3 })             a plural entry {"one": "{n} sim", "other": "{n} sims"} picks its form
//                                         with Intl.PluralRules; numbers in {placeholders} are formatted locally
//   h('library.inbox.empty', { ... })     the entry as HTML (catalogs may hold <b>, <kbd>, <code>...): the values
//                                         are escaped unless wrapped in raw('<b>...</b>')
//
// The engine's own sentences (task steps, errors...) are translated by the server (speedkit/hub/i18n.py).

export const LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'es', name: 'Español' },
  { code: 'pt-BR', name: 'Português (Brasil)' },
  { code: 'fr', name: 'Français' },
  { code: 'de', name: 'Deutsch' },
  { code: 'it', name: 'Italiano' },
  { code: 'pl', name: 'Polski' },
];
export const DEFAULT = 'en';
const CODES = LANGUAGES.map(l => l.code);

let LANG = DEFAULT;
let CAT = {};
let EN = {};
let RULES = new Intl.PluralRules(DEFAULT);
const FORMATS = new Map();

export const lang = () => LANG;
export const supported = code => CODES.includes(code);

// the best language for a list of browser / Windows languages ('de-AT' -> 'de', 'pt-PT' -> 'pt-BR'); null if none
export function match(prefs) {
  for (const raw of [].concat(prefs || [])) {
    const p = String(raw || '').trim().replace('_', '-').toLowerCase();
    if (!p) continue;
    const exact = CODES.find(c => c.toLowerCase() === p);
    if (exact) return exact;
    const base = p.split('-')[0];
    const near = CODES.find(c => c.toLowerCase().split('-')[0] === base);
    if (near) return near;
  }
  return null;
}

// use a catalog (english: the reference catalog, for keys a translation lacks)
export function use(code, catalog, english) {
  LANG = supported(code) ? code : DEFAULT;
  EN = english || catalog || {};
  CAT = catalog || EN;
  RULES = new Intl.PluralRules(LANG);
  FORMATS.clear();
  return LANG;
}

let enCache = null;
async function fetchCatalog(code) {
  const r = await fetch(`i18n/${code}.json`, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`no catalog for ${code}`);
  return r.json();
}

// load and use a language's catalog; English stays underneath for any missing key
export async function load(code) {
  if (!supported(code)) code = DEFAULT;
  if (!enCache) enCache = await fetchCatalog(DEFAULT);
  let cat = enCache;
  if (code !== DEFAULT) {
    try { cat = await fetchCatalog(code); } catch { code = DEFAULT; cat = enCache; }
  }
  return use(code, cat, enCache);
}

// ------------------------------------------------------------------------------------------ numbers and dates
function nf(opts) {
  const key = JSON.stringify(opts || {});
  if (!FORMATS.has(key)) FORMATS.set(key, new Intl.NumberFormat(LANG, opts));
  return FORMATS.get(key);
}
// 12345 -> "12,345" / "12.345" / "12 345"; decimals: at most `digits` after the point
export const num = (n, digits = 0) => nf({ maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(Number(n));
export const date = (d, opts) => new Date(d).toLocaleDateString(LANG, opts);
export const time = (d, opts) => new Date(d).toLocaleTimeString(LANG, opts);
export const list = items => {
  try { return new Intl.ListFormat(LANG, { style: 'long', type: 'conjunction' }).format(items.map(String)); }
  catch { return items.join(', '); }
};

// ------------------------------------------------------------------------------------------ looking words up
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const escape = v => String(v ?? '').replace(/[&<>"']/g, c => ESC[c]);
export const raw = html => ({ __html: String(html ?? '') });

export const has = key => Object.prototype.hasOwnProperty.call(CAT, key) || Object.prototype.hasOwnProperty.call(EN, key);

function entry(key, vars) {
  let e = Object.prototype.hasOwnProperty.call(CAT, key) ? CAT[key] : EN[key];
  if (e === undefined) return key;
  if (e && typeof e === 'object') {
    const n = Number(vars && vars.n);
    const form = isNaN(n) ? 'other' : RULES.select(n);
    e = e[form] ?? e.other ?? e.one ?? key;
  }
  return String(e);
}

function value(v, html) {
  if (v && typeof v === 'object' && '__html' in v) return html ? v.__html : v.__html.replace(/<[^>]*>/g, '');
  if (typeof v === 'number') return num(v, Number.isInteger(v) ? 0 : 1);
  return html ? escape(v) : String(v ?? '');
}

function fill(text, vars, html) {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, k) => (Object.prototype.hasOwnProperty.call(vars, k) ? value(vars[k], html) : m));
}

// plain text
export const t = (key, vars) => fill(entry(key, vars), vars, false);
// HTML: the catalog's own markup stays, the values are escaped (unless raw())
export const h = (key, vars) => fill(entry(key, vars), vars, true);
