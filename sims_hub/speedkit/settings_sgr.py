"""Read The Sims 4 graphics rules (.sgr) the way the game does, so SpeedKit can say what they set.

The game's GraphicsRules.sgr is a small script language. ConfigOverride\\GraphicsRules.sgr replaces
the stock E:\\The Sims 4\\Game\\Bin\\GraphicsRules.sgr completely (research 'settings', confirmed by
Config.log: only one rules file is parsed). A plain text diff is not enough for Simp4Sims' 2023
"Setters" version, because its values are computed from variables (${SBCull}, ${SFSimDist1}...)
set in SimpsSetters.sgr + MySetters.sgr. So this module runs the script:

    seti/setf/setb/set NAME expr       variables (int / float / bool / string)
    if (expr) / elseif (expr) / else / endif
    include "file" / sinclude "file"   (file names may use ${var}; resolved next to the including file)
    option NAME ... setting EXPR | integer N ... prop $ConfigGroup PROP value ... end
    setProp $ConfigGroup PROP value    global property
    setOption NAME expr                default level of an option
    log / logSystemInfo "text"         (logSystemInfo lines are what Config.log starts with)
    #< ... #>                          block comment (the signature at the end of EA's files)

Expressions: numbers, "strings" with ${var}, $var, true/false, + - * /, comparisons, and/or/not,
match(), round(), floor(), ceil(), sqrt(), min(), max(), abs(), versionLessThan().
Undefined variables read as 0 and are listed in Rules.undefined (the engine's own behaviour for them is
unknown). Machine variables ($textureMemory, $cardVendor...) come from Config.log when available.
A line this reader cannot run is listed in Rules.errors and skipped; an if/elseif condition it cannot
run counts as false, and an include loop is an error rather than endless recursion.

evaluate(path) -> Rules; Rules.effective(levels) -> {prop: value} for the player's option levels
(Options.ini). Option props win over global setProp values; later option blocks win over earlier ones
(the engine's real order for props defined twice is not known). evaluate(path, text=...) runs text that is
not on disk yet (a rules file SpeedKit is about to write) as if it were the file at path.
Rules.where tells on which lines each prop was assigned: {(option, level, prop): [(file, line)]}, with
(None, None, prop) for global setProp/prop lines - speedkit.settings patches exactly those lines.
Rules.dormant lists, the same way, the prop/setProp lines inside if-branches this machine does not take
(another GPU vendor, less memory...), so a patch can cover the other hardware too.
"""
import fnmatch, math, os, re

# Machine facts the rules test. Defaults match this user's laptop (Config.log 2026-09-24); machine_vars()
# replaces them with what the current Config.log says.
DEFAULT_MACHINE = {
    'isWindows': 1, 'isMac': 0, 'isLiveEdit': 0, 'osMajorVersion': 10,
    'cpu': 'AuthenticAMD', 'cpuSpeed': 3793, 'cpuCount': 8, 'cpuFamily': 15, 'cpuModel': 5, 'hyperthreading': 1,
    'memory': 15676, 'virtualMemory': 134217728, 'textureMemory': 5920,
    'cardVendor': 'NVIDIA', 'driverVersion': '', 'desktopWidth': 1920, 'desktopHeight': 1200,
    'forcedCardLevel': 0, 'forcedCpuLevel': 0,
    # the graphics-card database only picks default option levels; Options.ini overrides those
    'graphicsCardsSgrPath': '', 'graphicsCardsSgrOverridePath': '',
}
MAX_INCLUDE_DEPTH = 16          # a file that includes itself (directly or not) is an error, not a crash
# What one unreadable line may raise; it is listed in Rules.errors and the rest of the file still runs.
_LINE_ERRORS = (ValueError, IndexError, TypeError, KeyError, ArithmeticError, RecursionError, OSError)


def machine_vars(config_log=None):
    """Machine variables for the rules, read from Config.log when it exists (else DEFAULT_MACHINE)."""
    v = dict(DEFAULT_MACHINE)
    if not config_log or not os.path.exists(config_log):
        return v
    with open(config_log, encoding='utf-8', errors='replace') as f:
        text = f.read(20000)
    pats = {'textureMemory': r'Texture memory:\s*(\d+)MB', 'memory': r'^Memory:\s*(\d+)MB',
            'cpuSpeed': r'CPU Speed:\s*(\d+)', 'cpuCount': r'^\s*Cores:\s*(\d+)', 'hyperthreading': r'^\s*HT:\s*(\d+)',
            'osMajorVersion': r'OS major ver:\s*(\d+)', 'cpuFamily': r'^\s*Family:\s*(\d+)', 'cpuModel': r'^\s*Model:\s*(\d+)'}
    for k, p in pats.items():
        m = re.search(p, text, re.M)
        if m:
            v[k] = int(m.group(1))
    m = re.search(r'^CPU:\s*(\S+)', text, re.M)
    if m:
        v['cpu'] = m.group(1)
    m = re.search(r'^Vendor:\s*(\S+)', text, re.M)
    if m:
        v['cardVendor'] = m.group(1)
    return v


# ------------------------------------------------------------------------------------------ expressions
_TOKEN = re.compile(r'\s*(?:(\d+\.\d*|\.\d+|\d+)f?|("(?:[^"\\]|\\.)*")|\$\{(\w+)\}|\$(\w+)|(==|!=|<=|>=|[-+*/(),<>!])|(\w+))')


class _Expr:
    """Tiny recursive-descent evaluator for SGR expressions (no eval())."""

    def __init__(self, text, rules):
        self.rules = rules
        self.toks = []
        pos = 0
        text = text.strip()
        while pos < len(text):
            m = _TOKEN.match(text, pos)
            if not m or m.end() == pos:
                raise ValueError('cannot parse expression %r' % text)
            pos = m.end()
            num, s, var1, var2, op, word = m.groups()
            if num is not None:
                self.toks.append(('num', float(num) if '.' in num else int(num)))
            elif s is not None:
                self.toks.append(('str', rules.subst(s[1:-1])))
            elif var1 or var2:
                self.toks.append(('var', var1 or var2))
            elif op is not None:
                self.toks.append(('op', op))
            elif word is not None:
                self.toks.append(('word', word))
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self):
        t = self.peek()
        self.i += 1
        return t

    def is_(self, kind, val=None):
        k, v = self.peek()
        return k == kind and (val is None or (v.lower() if isinstance(v, str) and kind == 'word' else v) == val)

    def value(self):
        r = self.or_()
        if self.i != len(self.toks):
            raise ValueError('trailing tokens in expression')
        return r

    def or_(self):
        r = self.and_()
        while self.is_('word', 'or'):
            self.take()
            rhs = self.and_()
            r = bool(r) or bool(rhs)
        return r

    def and_(self):
        r = self.not_()
        while self.is_('word', 'and'):
            self.take()
            rhs = self.not_()
            r = bool(r) and bool(rhs)
        return r

    def not_(self):
        if self.is_('word', 'not') or self.is_('op', '!'):
            self.take()
            return not self.not_()
        return self.cmp()

    def cmp(self):
        a = self.add()
        k, v = self.peek()
        if k == 'op' and v in ('==', '!=', '<', '>', '<=', '>='):
            self.take()
            b = self.add()
            if isinstance(a, str) != isinstance(b, str):      # "5" == 5
                a, b = str(a), str(b)
            return {'==': a == b, '!=': a != b, '<': a < b, '>': a > b, '<=': a <= b, '>=': a >= b}[v]
        return a

    def add(self):
        r = self.mul()
        while self.is_('op', '+') or self.is_('op', '-'):
            op = self.take()[1]
            rhs = self.mul()
            r = r + rhs if op == '+' else r - rhs
        return r

    def mul(self):
        r = self.unary()
        while self.is_('op', '*') or self.is_('op', '/'):
            op = self.take()[1]
            rhs = self.unary()
            r = r * rhs if op == '*' else (r / rhs if rhs else 0)
        return r

    def unary(self):
        if self.is_('op', '-'):
            self.take()
            return -self.unary()
        return self.primary()

    def primary(self):
        k, v = self.take()
        if k == 'num' or k == 'str':
            return v
        if k == 'var':
            return self.rules.get(v)
        if k == 'op' and v == '(':
            r = self.or_()
            if self.take() != ('op', ')'):
                raise ValueError('missing )')
            return r
        if k == 'word':
            low = v.lower()
            if low == 'true':
                return True
            if low == 'false':
                return False
            if self.is_('op', '('):
                self.take()
                args = []
                while not self.is_('op', ')'):
                    args.append(self.or_())
                    if self.is_('op', ','):
                        self.take()
                self.take()
                return _call(low, args)
            return self.rules.vars.get(v, v)          # bare word: a variable if defined, else the word
        raise ValueError('unexpected token %r' % (v,))


def _version_less(a, b):
    def parts(s):
        return [int(x) for x in re.findall(r'\d+', str(s))]
    return parts(a) < parts(b)


def _call(name, args):
    if name == 'match':
        return fnmatch.fnmatchcase(str(args[0]), str(args[1]))
    if name == 'round':
        return int(math.floor(args[0] + 0.5))
    if name == 'floor':
        return int(math.floor(args[0]))
    if name == 'ceil':
        return int(math.ceil(args[0]))
    if name == 'sqrt':
        return math.sqrt(args[0])
    if name in ('min', 'max', 'abs'):
        return {'min': min, 'max': max, 'abs': abs}[name](*args)
    if name == 'versionlessthan':
        return _version_less(args[0], args[1])
    raise ValueError('unknown function %s()' % name)


def fmt(v):
    """Format a variable value the way it would appear in a prop."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float):
        return ('%.6f' % v).rstrip('0').rstrip('.') if v != int(v) else str(int(v))
    return str(v)


# ------------------------------------------------------------------------------------------ interpreter
class Rules:
    """The result of running one rules file: variables, options with their props, global props."""

    def __init__(self, machine=None, include_overrides=None):
        self.vars = dict(machine or DEFAULT_MACHINE)
        self.include_overrides = {k.lower(): v for k, v in (include_overrides or {}).items()}
        self.options = {}           # name -> {'settings': {level: {prop: value}}, 'default': level, 'order': n}
        self.globals = {}           # prop -> value (setProp)
        self.files = []             # every file actually read, in order
        self.missing = []           # include/sinclude targets that were not found
        self.info = []              # logSystemInfo texts (what Config.log starts with)
        self.log = []               # log texts (parser progress messages)
        self.undefined = set()
        self.errors = []            # (file, line, message) for lines this reader could not run
        self.where = {}             # (option, level, prop) / (None, None, prop) -> [(file, line number)]
        # the same for prop/setProp lines inside if-branches this machine does not take (another GPU vendor,
        # less memory...): the game runs them on other hardware. level None = the level could not be read.
        self.dormant = {}
        self._running = []          # files being run right now (include loop guard)

    def get(self, name):
        if name in self.vars:
            return self.vars[name]
        self.undefined.add(name)
        return 0

    def subst(self, text):
        return re.sub(r'\$\{(\w+)\}', lambda m: fmt(self.get(m.group(1))), text)

    def value_text(self, raw):
        """Text of a prop value: quotes removed, ${var} and a lone $var replaced."""
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
            raw = raw[1:-1]
        m = re.fullmatch(r'\$(\w+)', raw)
        if m:
            return fmt(self.get(m.group(1)))
        return self.subst(raw)

    def eval(self, text):
        return _Expr(text, self).value()

    def _test(self, expr, path, n):
        """Truth of an if/elseif condition; a condition this reader cannot run counts as false (and is
        listed in errors) so the if/else nesting of the rest of the file stays right."""
        try:
            return bool(self.eval(expr))
        except _LINE_ERRORS as e:
            self.errors.append((path, n, '%s: %s (condition taken as false)' % (type(e).__name__, e)))
            return False

    # ---------------------------------------------------------------- running
    def run(self, path, text=None):
        """Run a rules file; text (if given) is used instead of reading path (includes still resolve
        next to path)."""
        key = os.path.normcase(os.path.abspath(path))
        if key in self._running:
            raise ValueError('include loop: %s is already being read' % path)
        if len(self._running) >= MAX_INCLUDE_DEPTH:
            raise ValueError('includes nested deeper than %d' % MAX_INCLUDE_DEPTH)
        self._running.append(key)
        try:
            return self._run(path, text)
        finally:
            self._running.pop()

    def _run(self, path, text=None):
        if text is None:
            with open(path, encoding='utf-8', errors='replace') as f:
                text = f.read()
        lines = text.splitlines()
        self.files.append(path)
        stack = []                  # [parent_active, taken, active]
        active = True
        option = None               # current option name
        setting = None
        where_now = [None, None]    # [option, setting] from the file's structure, also in branches not taken
        in_block_comment = False
        for n, raw in enumerate(lines, 1):
            s = raw.strip()
            if in_block_comment:
                if s.startswith('#>'):
                    in_block_comment = False
                continue
            if s.startswith('#<'):
                in_block_comment = True
                continue
            s = _strip_comment(s)
            if not s:
                continue
            m = re.match(r'(\w+)\s*(.*)$', s)
            if not m:
                self.errors.append((path, n, 'unreadable line'))
                continue
            kw, rest = m.group(1).lower(), m.group(2).strip()
            try:
                if kw == 'if':
                    ok = active and self._test(rest, path, n)
                    stack.append([active, ok, ok])
                    active = ok
                    continue
                if kw == 'elseif':
                    fr = stack[-1]
                    ok = fr[0] and not fr[1] and self._test(rest, path, n)
                    fr[1] = fr[1] or ok
                    fr[2] = active = ok
                    continue
                if kw == 'else':
                    fr = stack[-1]
                    ok = fr[0] and not fr[1]
                    fr[1] = True
                    fr[2] = active = ok
                    continue
                if kw == 'endif':
                    fr = stack.pop()
                    active = fr[0]
                    continue
                if not active:
                    self._dormant_line(kw, rest, path, n, where_now)
                    continue
                self._statement(kw, rest, path, n)
                if kw == 'option':
                    option, setting = rest.split()[0], None
                    self.options.setdefault(option, {'settings': {}, 'default': None, 'order': len(self.options)})
                elif kw == 'end':
                    option, setting = None, None
                elif kw == 'setting' and option:
                    setting = self.eval(rest)
                    self.options[option]['settings'].setdefault(setting, {})
                elif kw == 'integer' and option:
                    setting = 'integer'
                    self.options[option]['settings'].setdefault(setting, {})
                elif kw == 'prop':
                    parts = rest.split(None, 2)
                    if len(parts) >= 2:
                        name, val = parts[1], (parts[2] if len(parts) > 2 else '')
                        if option is not None and setting is not None:
                            self.options[option]['settings'][setting][name] = self.value_text(val)
                            self.where.setdefault((option, setting, name), []).append((path, n))
                        else:
                            self.globals[name] = self.value_text(val)
                            self.where.setdefault((None, None, name), []).append((path, n))
            except _LINE_ERRORS as e:
                self.errors.append((path, n, '%s: %s' % (type(e).__name__, e)))
            if active:
                where_now[:] = [option, setting]
        return self

    def _dormant_line(self, kw, rest, path, n, where_now):
        """Follow option/setting/end in an if-branch this machine does not take, and record its prop and setProp
        lines in self.dormant. Nothing else in such a branch is run."""
        if kw == 'option':
            where_now[:] = [(rest.split() or [None])[0], None]
        elif kw == 'end':
            where_now[:] = [None, None]
        elif kw == 'integer' and where_now[0]:
            where_now[1] = 'integer'
        elif kw == 'setting' and where_now[0]:
            undefined = set(self.undefined)         # reading the level must not change what the file reports
            try:
                where_now[1] = self.eval(rest)
            except _LINE_ERRORS:
                where_now[1] = None
            finally:
                self.undefined = undefined
        elif kw in ('prop', 'setprop'):
            parts = rest.split(None, 2)
            if len(parts) >= 2:
                key = (where_now[0], where_now[1], parts[1]) if kw == 'prop' and where_now[0] else (None, None, parts[1])
                self.dormant.setdefault(key, []).append((path, n))

    def _statement(self, kw, rest, path, n=0):
        """Run one statement that is not flow control or part of an option block (n: its line number)."""
        if kw in ('seti', 'setf', 'setb', 'set'):
            parts = rest.split(None, 1)
            name, expr = parts[0], (parts[1] if len(parts) > 1 else '')
            if kw == 'set':
                self.vars[name] = self.value_text(expr)
                return
            v = self.eval(expr)
            if kw == 'seti':
                v = int(v) if not isinstance(v, str) else int(float(v))
            elif kw == 'setf':
                v = float(v)
            else:
                v = bool(v) if not isinstance(v, str) else v.lower() == 'true'
            self.vars[name] = v
        elif kw in ('include', 'sinclude'):
            target = self.value_text(rest)
            if not target or target == '0':
                self.missing.append((kw, rest))
                return
            p = self.include_overrides.get(os.path.basename(target).lower())
            if p is None:
                p = target if os.path.isabs(target) else os.path.join(os.path.dirname(path), target)
            if os.path.exists(p):
                self.run(p)
            else:
                self.missing.append((kw, target))
        elif kw == 'setprop':
            parts = rest.split(None, 2)
            if len(parts) >= 2:
                self.globals[parts[1]] = self.value_text(parts[2] if len(parts) > 2 else '')
                self.where.setdefault((None, None, parts[1]), []).append((path, n))
        elif kw == 'setoption':
            parts = rest.split(None, 1)
            opt = self.options.setdefault(parts[0], {'settings': {}, 'default': None, 'order': len(self.options)})
            opt['default'] = self.eval(parts[1])
        elif kw == 'logsysteminfo':
            self.info.append(self.value_text(rest))
        elif kw == 'log':
            self.log.append(self.value_text(rest))

    # ---------------------------------------------------------------- results
    def option_names(self):
        return set(self.options)

    def effective(self, levels):
        """{prop: (value, where)} for the given option levels ({option name, any case: level}).

        where is 'global' or 'Option=level'. An option missing from levels uses its setOption default."""
        lv = {k.lower(): v for k, v in (levels or {}).items()}
        out = {p: (v, 'global') for p, v in self.globals.items()}
        for name, opt in sorted(self.options.items(), key=lambda kv: kv[1]['order']):
            level = lv.get(name.lower(), opt['default'])
            props = opt['settings'].get(level)
            if props is None and 'integer' in opt['settings']:
                props = opt['settings']['integer']
            for p, v in (props or {}).items():
                out[p] = (v, '%s=%s' % (name, level))
        return out


def _strip_comment(s):
    """Remove a # comment that is not inside quotes."""
    q = False
    for i, ch in enumerate(s):
        if ch == '"':
            q = not q
        elif ch == '#' and not q:
            return s[:i].strip()
    return s


def evaluate(path, machine=None, include_overrides=None, text=None):
    """Run a rules file (and what it includes). include_overrides maps a file name such as
    'MySetters.sgr' to another path to use instead (to preview a preset before installing it).
    text: run this text as the content of path (nothing is read from path itself)."""
    return Rules(machine, include_overrides).run(path, text)
