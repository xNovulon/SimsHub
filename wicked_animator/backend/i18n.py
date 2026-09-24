"""The app's settings on this PC (the language, for now) and the server's own messages in that language.

The settings are one small JSON file next to the saved animations (projects.ROOT, like the progressions and the
exports map): animator_settings.json. It survives restarts and updates, and every copy of the app shares it.

tr(key, **vars) looks a message up in the same catalogs the page uses (web/i18n/<code>.json) and fills it in with
the same syntax: {name}, {name, number} and {name, plural, one {# thing} other {# things}}. A message the chosen
language lacks falls back to English, and a key no catalog has comes back as it is."""
import json, os, threading

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOGS = os.path.normpath(os.path.join(HERE, '..', 'web', 'i18n'))
LANGUAGES = ('en', 'es', 'pt-BR', 'fr', 'de', 'it', 'pl')
DEFAULT = 'en'
SETTINGS_FILE = 'animator_settings.json'
# what a setting may be: name -> check(value) -> the value to keep (or ValueError)
_KNOWN = {
    'language': lambda v: _language(v),
    'language_auto': lambda v: bool(v),
}

_lock = threading.RLock()
_cache = {}            # path -> (mtime_ns, data)


def _projects():
    import projects          # here, not at the top: projects (and the modules it uses) may call tr() too
    return projects


def _path():
    return os.path.join(_projects().ROOT, SETTINGS_FILE)


def _language(v):
    code = str(v or '').strip().replace('_', '-')
    for c in LANGUAGES:
        if c.lower() == code.lower():
            return c
    base = code.split('-')[0].lower()
    for c in LANGUAGES:
        if c.split('-')[0].lower() == base:
            return c
    raise ValueError('Unknown language: %s' % (v,))


def _read_json(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    hit = _cache.get(path)
    if hit and hit[0] == st.st_mtime_ns:
        return hit[1]
    try:
        data = _projects()._read(path)
    except (OSError, ValueError):
        return None
    _cache[path] = (st.st_mtime_ns, data)
    return data


def settings():
    """Every saved setting ({} before the first start that saved one)."""
    with _lock:
        data = _read_json(_path())
        return dict(data) if isinstance(data, dict) else {}


def save_settings(patch):
    """Merges the known settings in `patch` into the file -> all settings. Unknown names are ignored."""
    if not isinstance(patch, dict):
        raise ValueError('Send the settings as a JSON object.')
    with _lock:
        data = settings()
        for k, v in patch.items():
            if k in _KNOWN:
                data[k] = _KNOWN[k](v)
        os.makedirs(_projects().ROOT, exist_ok=True)
        _projects()._write(_path(), data)
        _cache.pop(_path(), None)
        return data


def language():
    """The app's language code ('en' until one is saved)."""
    lang = settings().get('language')
    return lang if lang in LANGUAGES else DEFAULT


def catalog(code):
    """{key: message} of one language ({} when it has no catalog)."""
    data = _read_json(os.path.join(CATALOGS, code + '.json'))
    return data if isinstance(data, dict) else {}


# ------------------------------------------------------------------ numbers and plurals (CLDR, for our languages)
def plural_category(n, lang=None):
    lang = lang or language()
    try:
        x = float(n)
    except (TypeError, ValueError):
        return 'other'
    whole = x == int(x)
    i = int(abs(x))
    if lang == 'pl':
        if not whole:
            return 'other'
        if i == 1:
            return 'one'
        if 2 <= i % 10 <= 4 and not 12 <= i % 100 <= 14:
            return 'few'
        return 'many'
    if lang in ('fr', 'pt-BR'):
        return 'one' if i in (0, 1) else 'other'
    return 'one' if whole and i == 1 else 'other'


_SEPS = {'en': (',', '.'), 'de': ('.', ','), 'es': ('.', ','), 'it': ('.', ','), 'pt-BR': ('.', ','),
         'fr': (' ', ','), 'pl': (' ', ',')}


def fmt_number(n, group=True, lang=None):
    lang = lang or language()
    try:
        x = float(n)
    except (TypeError, ValueError):
        return str(n)
    th, dec = _SEPS.get(lang, _SEPS['en'])
    text = ('%d' % x) if x == int(x) else ('%.3f' % x).rstrip('0').rstrip('.')
    whole, _, frac = text.partition('.')
    sign = '-' if whole.startswith('-') else ''
    whole = whole.lstrip('-')
    # Spanish and Polish group only from five digits (10 000); the others from four
    if group and len(whole) > (4 if lang in ('es', 'pl') else 3):
        parts = []
        while whole:
            parts.insert(0, whole[-3:])
            whole = whole[:-3]
        whole = th.join(parts)
    return sign + whole + (dec + frac if frac else '')


def _parse(msg):
    out, i, text = [], 0, ''
    while i < len(msg):
        c = msg[i]
        if c != '{':
            text += c
            i += 1
            continue
        depth, j = 1, i + 1
        while j < len(msg) and depth:
            depth += 1 if msg[j] == '{' else -1 if msg[j] == '}' else 0
            j += 1
        if depth:
            text += msg[i:]
            break
        if text:
            out.append(text)
            text = ''
        inner = msg[i + 1:j - 1]
        name, _, rest = inner.partition(',')
        kind, _, opts = rest.partition(',')
        out.append((name.strip(), kind.strip(), opts))
        i = j
    if text:
        out.append(text)
    return out


def _options(rest):
    o, i = {}, 0
    while True:
        b = rest.find('{', i)
        if b < 0:
            return o
        name = rest[i:b].strip()
        depth, j = 1, b + 1
        while j < len(rest) and depth:
            depth += 1 if rest[j] == '{' else -1 if rest[j] == '}' else 0
            j += 1
        o[name] = rest[b + 1:j - 1]
        i = j


def format_message(msg, vars=None, lang=None, _hash=None):
    vars = vars or {}
    lang = lang or language()
    out = []
    for p in _parse(msg):
        if isinstance(p, str):
            out.append(p if _hash is None else p.replace('#', _hash))
            continue
        name, kind, rest = p
        v = vars.get(name)
        if kind in ('plural', 'select'):
            o = _options(rest)
            if kind == 'plural':
                try:
                    n = float(v or 0)
                except (TypeError, ValueError):
                    n = 0
                exact = '=%d' % n if n == int(n) else None
                pick = o.get(exact) if exact in o else o.get(plural_category(n, lang), o.get('other', ''))
                out.append(format_message(pick, vars, lang, fmt_number(n, lang=lang)))
            else:
                out.append(format_message(o.get(str(v), o.get('other', '')), vars, lang, _hash))
        elif v is None:
            continue
        elif kind == 'number':
            out.append(fmt_number(v, lang=lang))
        elif isinstance(v, float):
            out.append(fmt_number(v, group=False, lang=lang))
        else:
            out.append(str(v))
    return ''.join(out)


def tr(key, **vars):
    """The message `key` in the app's language, filled in with vars."""
    lang = language()
    msg = catalog(lang).get(key) if lang != DEFAULT else None
    if msg is None:
        msg = catalog(DEFAULT).get(key)
    if msg is None:
        return key
    return format_message(msg, vars, lang) if (vars or '{' in msg) else msg
