"""Novulon's Sims Hub - the language of what the server says (docs/hub_contract.md, "Languages").

The page's own words live in speedkit/hub/web/i18n/<code>.json and are looked up in the browser (js/i18n.js).
The sentences the engine writes (task steps and results, errors, notices, labels) stay plain English in
speedkit/*.py; the server translates them on their way out, with the language saved in the Hub's settings:

  messages/source.json   the engine's exact English sentences, by key, with {placeholders}
  messages/<code>.json   what each language shows for those keys (en.json included: the English the Hub shows)

A sentence is recognised whole, else sentence by sentence, else as a list ('1 new CC file, 2 already in your
game.'); a text placeholder is itself translated when it is a known sentence; numbers are written the language's
way (12,345.6 -> 12.345,6). A sentence nobody knows is left as the engine wrote it, so nothing is ever lost.
localize() keeps each original next to its translation as '<field>_en', for code that looks for words in it.

The choice itself is kept in data\\hub_settings.json ({"language": "de"}), see Settings.
"""
import json
import locale
import os
import re
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
MESSAGES = os.path.join(HERE, 'messages')
WEB_CATALOGS = os.path.join(HERE, 'web', 'i18n')

LANGUAGES = [('en', 'English'), ('es', 'Español'), ('pt-BR', 'Português (Brasil)'), ('fr', 'Français'),
             ('de', 'Deutsch'), ('it', 'Italiano'), ('pl', 'Polski')]
CODES = [c for c, _ in LANGUAGES]
DEFAULT = 'en'

# placeholders that hold numbers (they are re-written the language's way); every other one holds text
NUMERIC = {'n', 'n2', 'k', 'gb', 'gb2', 'mb', 'pct', 'port'}
# the fields of the server's answers that carry sentences for people (dicts anywhere in the answer)
TEXT_FIELDS = {'message', 'label', 'why', 'reason', 'note', 'title', 'hint', 'problem', 'broken', 'body',
               'category_label', 'what', 'source', 'detail', 'update'}
LIST_FIELDS = {'warnings', 'details'}          # lists of sentences (a 'details' string is technical: left alone)
EXACT_FIELDS = {'name'}                         # names: only a whole known phrase ('In-game library')

_PH = re.compile(r'\{(\w+)\}')
_SENTENCE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"\'(])')
_NUMBER = re.compile(r'^-?\d{1,3}(?:,\d{3})+(?:\.\d+)?$|^-?\d+(?:\.\d+)?$')
# decimal point and thousands separator; the second number: group only from this many digits (CLDR)
_SEPARATORS = {'en': ('.', ',', 4), 'es': (',', '.', 5), 'pt-BR': (',', '.', 4), 'fr': (',', ' ', 4),
               'de': (',', '.', 4), 'it': (',', '.', 4), 'pl': (',', ' ', 5)}


def match(prefs):
    """The best supported code for language tags ('de-AT' -> 'de', 'pt_PT' -> 'pt-BR', 'C' -> None)."""
    if isinstance(prefs, str):
        prefs = [prefs]
    for raw in prefs or []:
        p = str(raw or '').strip().replace('_', '-').split('.')[0].lower()
        if not p:
            continue
        for c in CODES:
            if c.lower() == p:
                return c
        base = p.split('-')[0]
        for c in CODES:
            if c.lower().split('-')[0] == base:
                return c
    return None


def system_language():
    """The Windows display language (or the POSIX locale), as a supported code, else None."""
    try:
        if os.name == 'nt':
            import ctypes
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            found = match(locale.windows_locale.get(lcid, ''))
            if found:
                return found
    except Exception:
        pass
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG', 'LANGUAGE'):
        found = match((os.environ.get(var) or '').split(':'))
        if found:
            return found
    try:
        return match(locale.getlocale()[0] or '')
    except Exception:
        return None


def plural(lang, n):
    """The CLDR plural category of n in this language (the same answer as Intl.PluralRules in the page)."""
    try:
        x = float(str(n).replace(',', ''))
    except ValueError:
        return 'other'
    whole = x == int(x)
    i = int(x)
    base = (lang or DEFAULT).split('-')[0]
    if base == 'pl':
        if not whole:
            return 'other'
        if i == 1:
            return 'one'
        if 2 <= i % 10 <= 4 and not 12 <= i % 100 <= 14:
            return 'few'
        return 'many'
    if base in ('fr', 'pt'):
        return 'one' if i in (0, 1) else 'other'
    return 'one' if x == 1 else 'other'


def number(text, lang):
    """An English-written number ('41,236', '18.2') the language's way; anything else as it is."""
    s = str(text)
    if lang == DEFAULT or not _NUMBER.match(s):
        return s
    point, group, least = _SEPARATORS.get(lang, _SEPARATORS[DEFAULT])
    whole, _, frac = s.replace(',', '').partition('.')
    neg = whole.startswith('-')
    whole = whole.lstrip('-')
    if len(whole) >= least:
        parts = []
        while len(whole) > 3:
            parts.insert(0, whole[-3:])
            whole = whole[:-3]
        whole = group.join([whole] + parts)
    return ('-' if neg else '') + whole + (point + frac if frac else '')


def _load(path):
    with open(path, encoding='utf-8') as f:
        doc = json.load(f)
    return {k: v for k, v in doc.items() if not k.startswith('_')}


def placeholders(value):
    """The {placeholders} of a catalog entry (a string, or a plural entry {'one': ..., 'other': ...})."""
    texts = value.values() if isinstance(value, dict) else [value]
    return {name for t in texts for name in _PH.findall(t)}


class _Pattern:
    def __init__(self, key, form, text):
        self.key, self.form, self.text = key, form, text
        parts = _PH.split(text)
        rx, self.names = [], []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                rx.append(re.escape(part))
            else:
                self.names.append(part)
                rx.append(r'(-?\d[\d,]*(?:\.\d+)?)' if part in NUMERIC else r'(.+?)')
        self.regex = re.compile(''.join(rx) + r'\Z', re.S)
        literal = ''.join(parts[0::2])
        self.weight = len(literal)
        # a pattern that is only placeholders and punctuation ('{name}: {text}') counts only when it translated
        # something inside it
        self.weak = not re.search(r'[A-Za-z]', literal)
        self.first = parts[0][:1]


class Translator:
    """Engine sentences -> the chosen language. Thread-safe; results are cached per language."""

    def __init__(self, folder=MESSAGES):
        self.folder = folder
        self.source = _load(os.path.join(folder, 'source.json'))
        self.catalogs = {}
        self.fixed = {}
        pats = []
        for key, value in self.source.items():
            forms = value.items() if isinstance(value, dict) else [(None, value)]
            for form, text in forms:
                if _PH.search(text):
                    pats.append(_Pattern(key, form, text))
                else:
                    self.fixed.setdefault(text, (key, form))
        pats.sort(key=lambda p: -p.weight)
        self.patterns = pats
        self._lock = threading.Lock()
        self._cache = {}

    # ---------------------------------------------------------------- catalogs
    def catalog(self, lang):
        cat = self.catalogs.get(lang)
        if cat is None:
            try:
                cat = _load(os.path.join(self.folder, '%s.json' % lang))
            except (OSError, ValueError):
                cat = {}
            self.catalogs[lang] = cat
        return cat

    def _entry(self, key, lang):
        for code in (lang, DEFAULT):
            value = self.catalog(code).get(key)
            if value not in (None, ''):
                return value
        return self.source.get(key)

    def _render(self, key, form, values, lang, depth):
        value = self._entry(key, lang)
        if isinstance(value, dict):
            want = plural(lang, values['n']) if 'n' in values else (form or 'other')
            value = value.get(want) or value.get('other') or next(iter(value.values()))
        changed = [False]

        def fill(m):
            name = m.group(1)
            if name not in values:
                return m.group(0)
            v = values[name]
            if name in NUMERIC:
                return number(v, lang)
            t = self._text(v, lang, depth + 1)
            if t != v:
                changed[0] = True
            return t
        return _PH.sub(fill, value), changed[0]

    # ---------------------------------------------------------------- one sentence
    def _one(self, s, lang, depth):
        """The translation of s as one known sentence, else None."""
        hit = self.fixed.get(s)
        if hit:
            return self._render(hit[0], hit[1], {}, lang, depth)[0]
        if depth > 3:
            return None
        head = s[:1]
        for p in self.patterns:
            if p.first and p.first != head:
                continue
            m = p.regex.match(s)
            if not m:
                continue
            out, changed = self._render(p.key, p.form, dict(zip(p.names, m.groups())), lang, depth)
            if p.weak and not changed:
                continue
            return out
        return None

    def _list(self, s, lang, depth):
        """'1 new CC file, 2 already in your game.' -> each part known, joined the same way; else None."""
        end = '.' if s.endswith('.') else ''
        body = s[:-1] if end else s
        for sep in ('; ', ', '):
            if sep not in body:
                continue
            out = []
            for part in body.split(sep):
                t = self._one(part, lang, depth)
                if t is None and part[:1].isupper():
                    t = self._one(part[:1].lower() + part[1:], lang, depth)
                if t is None:
                    break
                out.append(t)
            else:
                text = sep.join(out) + end
                return text[:1].upper() + text[1:]
        return None

    def _text(self, s, lang, depth=0):
        if not s or not isinstance(s, str):
            return s
        t = self._one(s, lang, depth)
        if t is not None:
            return t
        parts = _SENTENCE.split(s)
        if len(parts) > 1:
            out = [self._one(p, lang, depth) or self._list(p, lang, depth) or p for p in parts]
            return ' '.join(out)
        return self._list(s, lang, depth) or s

    def text(self, s, lang):
        """One engine sentence (or several) in the language; unknown text comes back as it is."""
        if not isinstance(s, str) or not s:
            return s
        lang = lang if lang in CODES else DEFAULT
        key = (lang, s)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        out = self._text(s, lang)
        with self._lock:
            if len(self._cache) > 20000:
                self._cache.clear()
            self._cache[key] = out
        return out

    def exact(self, s, lang):
        """Only a whole known phrase without placeholders (for names)."""
        hit = self.fixed.get(s) if isinstance(s, str) else None
        return self._render(hit[0], hit[1], {}, lang, 0)[0] if hit else s

    # ---------------------------------------------------------------- whole answers
    def localize(self, obj, lang):
        """A copy of a server answer with its sentences translated (originals kept as '<field>_en')."""
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if isinstance(v, str) and k in TEXT_FIELDS:
                    t = self.text(v, lang)
                elif isinstance(v, str) and k in EXACT_FIELDS:
                    t = self.exact(v, lang)
                elif isinstance(v, list) and k in LIST_FIELDS and all(isinstance(x, str) for x in v):
                    t = [self.text(x, lang) for x in v]
                else:
                    out[k] = self.localize(v, lang)
                    continue
                out[k] = t
                if t != v and (k + '_en') not in obj:
                    out[k + '_en'] = v
            return out
        if isinstance(obj, list):
            return [self.localize(x, lang) for x in obj]
        return obj


_TRANSLATOR = []


def translator():
    if not _TRANSLATOR:
        _TRANSLATOR.append(Translator())
    return _TRANSLATOR[0]


# ---------------------------------------------------------------------------------------------- the Hub's settings
class Settings:
    """The Hub's own settings ({"language": code}): a JSON file (data\\hub_settings.json), or only in memory when
    path is None (example-data mode: nothing on the PC changes)."""

    def __init__(self, path=None):
        self.path = path
        self._lock = threading.Lock()
        self._doc = self._read()

    def _read(self):
        if not self.path:
            return {}
        try:
            with open(self.path, encoding='utf-8') as f:
                doc = json.load(f)
            return doc if isinstance(doc, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self, key, default=None):
        with self._lock:
            return self._doc.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._doc[key] = value
            if not self.path:
                return
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self._doc, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)

    @property
    def language(self):
        code = self.get('language')
        return code if code in CODES else None
