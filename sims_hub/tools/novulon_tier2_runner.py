r"""Tier 2 smoke test: import every Novulon module inside the game's own Python 3.7 (SPEC.md Sec 16,
overridden to cover every module rather than one entry point's own scenario: "the Tier 2 runner: import
every novulon module inside the game's own Python with simulation.zip on the path and minimal stubs
only where a module can't load outside the running game; report which").

    python tools/novulon_tier2_runner.py            # report only, exit != 0 on a real failure

What "can't load outside the running game" turned out to mean, checked directly against this
machine's own install (python37_x64.dll loaded standalone via tools/game_python.py - the game itself
never started - with simulation.zip added to sys.path, no stub at all): almost every simulation.zip
module - not just services/zone/ui/cas, every one of sims4.commands, sims4.resources, sims.sim_info,
sims4.tuning.tunable, ... - imports transitively through a handful of native (C-extension) modules the
game's own .exe supplies at runtime that python37_x64.dll never sees standalone: _common_types,
_trace, _math, _sims4_collections, _resourceman, _hashutil, _animation, _pythonutils,
protocolbuffers. A generic permissive stand-in for those gets a *pure-enum* module like
sims.occult.occult_enums importing for real (checked: it does) - but sims4.resources/sims4.commands/
sims.sim_info go one step further and need an exact value back from one of those natives (e.g.
`_resourceman.__all__`, a real `Key` class) that a generic stand-in can't fabricate without guessing
the real native surface - out of scope for a test harness ("never ship a guess"). This is exactly why
sims_hub/tests/test_ingame.py already hand-writes small Python stand-ins for services/zone/
sims4.commands/sims4.localization/ui/cas/areaserver/paths instead of trying to load the real ones -
that finding is reused here rather than re-derived the hard way a second time.

`services`, `zone`, `areaserver` and `paths` have no .pyc anywhere in base/core/simulation.zip at all
(confirmed: the real game injects them directly at runtime) - a stand-in for them is never shadowing a
real, checkable module. `ui`/`cas` DO exist for real, only in simulation.zip; this runner's stand-ins
for them are only reached by inserting a stub directory at sys.path[0] *inside* the child script
(confirmed live: this is what makes a stand-in win over the real, broken one - passing extra
directories to tools/game_python.py's own `path=` argument is NOT enough, since that always lands
*after* game_path()'s fixed base.zip/core.zip prefix, which the fixed `sims4` package (entirely inside
core.zip, no fragments in simulation.zip) can never be shadowed past this way). Nothing here changes
tools/game_python.py itself - the same technique sims_hub/tests/test_ingame.py's own SCENARIO already
uses (`sys.path.insert(0, ...)` as its first executable line).

So the runner tries each discovered novulon module twice:
  1. Real game zips only (base.zip/lib + core.zip already on sys.path via tools/game_python.py, plus
     simulation.zip and the ingame source tree added here) - whatever imports cleanly this way is
     exercising the real EA module, not a guess about its behaviour. In practice this is most of
     Novulon's own modules: the repo's own convention (already followed by every module built so far)
     defers a game import to inside a guarded function body, never at module import time, so importing
     the module itself never touches services/zone/sims4.commands/ui/cas at all.
  2. Only the modules that failed pass 1 are retried with STUBS (below) inserted ahead of everything
     else.
A module that still fails after (2) is a real problem - a name our own code got wrong, or a name this
small stub set doesn't cover yet (extend STUBS, in that case) - Tier 2 fails on that, never on falling
back to a stub, since falling back is the expected, reported outcome for a module that does need one
of these eight names.
"""
import json
import os
import sys
import tempfile
import textwrap

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)
from tools import game_python  # noqa: E402

INGAME_DIR = os.path.join(PROJECT, 'ingame')
PACKAGE = 'novulon'

# ---- hand-written stand-ins, same spirit and (where they overlap) same content as
# tests/test_ingame.py's own STUBS, extended with the handful of extra dialog/menu names menukit
# needs. Add a name here (never guess a whole behaviour) the moment Tier 2 reports an AttributeError
# against one of these modules for a real novulon file - see TESTING.md.
STUBS = {
    'services.py': textwrap.dedent('''\
        _ACTIVE_HOUSEHOLD_ID = None
        _ACTIVE_SIM_INFO = None
        def active_household_id():
            return _ACTIVE_HOUSEHOLD_ID
        def active_household():
            return None
        def active_sim_info():
            return _ACTIVE_SIM_INFO
        def current_zone():
            return None
        def current_zone_id():
            return None
        class _ObjectManager:
            def register_callback(self, *a, **k):
                pass
            def get(self, *a, **k):
                return None
        def object_manager():
            return _ObjectManager()
        _MANAGERS = {}
        def get_instance_manager(instance_type):
            return _MANAGERS.get(instance_type)
        class _ResetService:
            def trigger_destroy(self, *a, **k):
                pass
        def get_reset_and_delete_service():
            return _ResetService()
        def on_enter_main_menu():
            pass
        '''),
    'zone.py': textwrap.dedent('''\
        class Zone:
            def __init__(self, zone_id=0):
                self.id = zone_id
            def start_services(self, *a, **k):
                pass
        '''),
    'areaserver.py': 'server_init_load_time = 0.0\n',
    'paths.py': 'IS_ARCHIVE = True\n',
    'sims4/__init__.py': '',
    'sims4/log.py': textwrap.dedent('''\
        class Logger:
            def __init__(self, *a, **k):
                pass
            def __getattr__(self, name):
                return lambda *a, **k: None
        '''),
    'sims4/commands.py': textwrap.dedent('''\
        class CommandType:
            DebugOnly = 1
            Automation = 3
            Cheat = 4
            Live = 5
        def Command(*aliases, command_type=CommandType.DebugOnly, **kw):
            def named_command(func):
                return func
            return named_command
        class CheatOutput:
            def __init__(self, connection):
                self.connection = connection
            def __call__(self, s):
                pass
        '''),
    'sims4/localization.py': textwrap.dedent('''\
        class LocalizationHelperTuning:
            @classmethod
            def get_raw_text(cls, text):
                return text
            @classmethod
            def get_bulleted_list(cls, *a, **k):
                return ''
            @classmethod
            def get_comma_separated_list(cls, *a, **k):
                return ''
        '''),
    'sims4/resources.py': textwrap.dedent('''\
        class Types:
            INTERACTION = 1
            OBJECT = 2
            SNIPPET = 3
        '''),
    'ui/__init__.py': '',
    'ui/ui_dialog.py': textwrap.dedent('''\
        class _Factory:
            def __init__(self, cls):
                self.cls = cls
            def default(self, *a, **k):
                return self.cls()
        class UiDialogOkCancel:
            @classmethod
            def TunableFactory(cls):
                return _Factory(cls)
        class UiDialogTextInputOkCancel:
            @classmethod
            def TunableFactory(cls):
                return _Factory(cls)
        class UiDialogOk:
            @classmethod
            def TunableFactory(cls):
                return _Factory(cls)
        '''),
    'ui/ui_dialog_picker.py': textwrap.dedent('''\
        class ObjectPickerStyle:
            DEFAULT = 0
            DELETE = 1
        class BasePickerRow:
            def __init__(self, *a, **k):
                pass
        class SimPickerRow(BasePickerRow):
            pass
        class _Factory:
            def __init__(self, cls):
                self.cls = cls
            def default(self, *a, **k):
                return self.cls()
        class UiObjectPicker:
            @classmethod
            def TunableFactory(cls):
                return _Factory(cls)
        '''),
    'ui/ui_dialog_notification.py': textwrap.dedent('''\
        class UiDialogNotificationUrgency:
            DEFAULT = 0
            URGENT = 1
        class VisualType:
            INFORMATION = 0
        class _Dialog:
            def __init__(self, owner=None, **kw):
                self.owner, self.kw = owner, kw
            def show_dialog(self):
                pass
        class _Factory:
            def default(self, owner=None, **kw):
                return _Dialog(owner, **kw)
        class UiDialogNotification:
            UiDialogNotificationUrgency = UiDialogNotificationUrgency
            @classmethod
            def TunableFactory(cls):
                return _Factory()
        '''),
    'cas/__init__.py': '',
    'cas/cas.py': textwrap.dedent('''\
        def get_caspart_bodytype(part_id):
            return 0
        '''),
}


def discover_modules(src_dir):
    """Sorted dotted module names ('novulon', 'novulon.menukit.page', ...) for every .py file under
    src_dir/novulon, recursively; [] if the package doesn't exist yet - other build packages own those
    files, so that is a valid state here, not an error."""
    root = os.path.join(src_dir, PACKAGE)
    if not os.path.isdir(root):
        return []
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        rel = os.path.relpath(dirpath, src_dir)
        rel_parts = [] if rel == '.' else rel.split(os.sep)
        for filename in filenames:
            if not filename.endswith('.py'):
                continue
            stem = filename[:-3]
            parts = rel_parts if stem == '__init__' else rel_parts + [stem]
            out.append('.'.join(parts))
    return sorted(set(out))


def _write_stub_tree(root, stubs):
    for rel, text in stubs.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)


def _stub_top_names(stubs):
    tops = set()
    for rel in stubs:
        first = rel.split('/')[0]
        tops.add(first[:-3] if first.endswith('.py') else first)
    return sorted(tops)


RUN_SCRIPT = r'''
import sys, json, importlib
A = json.loads(HOST_ARGS)
if A.get("stub_dir"):
    sys.path.insert(0, A["stub_dir"])
report = {}
for name in A["modules"]:
    try:
        importlib.import_module(name)
        report[name] = {"ok": True, "error": None}
    except Exception as e:
        report[name] = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
report["_touched"] = sorted(set(n.split(".")[0] for n in sys.modules) & set(A.get("stub_tops", [])))
with open(A["result"], "w", encoding="utf-8") as f:
    json.dump(report, f)
'''


def run(src_dir=None, timeout=600):
    """Runs the two-pass import inside the game's own Python. Returns a report dict; raises
    RuntimeError only if the child process itself couldn't run at all (game python missing, a crash) -
    a module failing to import is a normal, reported result, never an exception here."""
    src_dir = src_dir or INGAME_DIR
    modules = discover_modules(src_dir)
    if not modules:
        return {'modules': [], 'results': {}, 'stub_used': [],
                'note': 'no %s/ modules found under %s yet' % (PACKAGE, src_dir)}
    if not game_python.available():
        raise RuntimeError('game Python not found at %s' % game_python.DLL)

    stub_tops = _stub_top_names(STUBS)
    with tempfile.TemporaryDirectory(prefix='novulon_tier2_') as tmp:
        stub_dir = os.path.join(tmp, 'stubs')
        _write_stub_tree(stub_dir, STUBS)
        simulation_zip = os.path.join(game_python.GAMEPLAY, 'simulation.zip')

        def run_pass(mods, use_stub_dir):
            script = os.path.join(tmp, 'run_%s.py' % ('stub' if use_stub_dir else 'real'))
            with open(script, 'w', encoding='utf-8') as f:
                f.write(RUN_SCRIPT)
            result = os.path.join(tmp, 'result_%s.json' % ('stub' if use_stub_dir else 'real'))
            args = {'modules': mods, 'result': result, 'stub_tops': stub_tops,
                    'stub_dir': stub_dir if use_stub_dir else None}
            cp = game_python.run(script, path=[simulation_zip, src_dir], args=json.dumps(args), timeout=timeout)
            if cp.returncode != 0 or not os.path.exists(result):
                raise RuntimeError('game Python could not even run the Tier 2 import script:\nSTDOUT:\n%s\nSTDERR:\n%s'
                                   % (cp.stdout[-2000:], cp.stderr[-2000:]))
            with open(result, encoding='utf-8') as f:
                return json.load(f)

        pass1 = run_pass(modules, use_stub_dir=False)
        pass1.pop('_touched', None)
        failed = [m for m in modules if not pass1[m]['ok']]
        results = dict(pass1)
        stub_used = []
        if failed:
            pass2 = run_pass(failed, use_stub_dir=True)
            stub_used = sorted(pass2.pop('_touched', []))
            for m in failed:
                results[m] = dict(pass2[m], used_stub=True)
        return {'modules': modules, 'results': results, 'stub_used': stub_used,
                'real_only': sorted(m for m in modules if not results[m].get('used_stub'))}


def main():
    report = run()
    if not report['modules']:
        print(report.get('note', 'nothing to check'))
        return 0
    fails = [m for m, r in report['results'].items() if not r['ok']]
    for m in report['modules']:
        r = report['results'][m]
        tag = 'ok (real)' if r['ok'] and not r.get('used_stub') else ('ok (stub)' if r['ok'] else 'FAIL')
        line = '%-9s %s' % (tag, m)
        if not r['ok']:
            line += '  -- %s' % r['error']
        print(line)
    print('-' * 70)
    print('%d module(s), %d ok, %d failed. stub modules touched: %s' % (
        len(report['modules']), len(report['modules']) - len(fails), len(fails), report['stub_used'] or 'none'))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
