"""EA names BP1 (core: __init__/common/hooks/settings/commands) and BP3 (inject.py, computer/tablet pie
menu) cite - see this package's __init__.py for the MANIFEST row shape. Every row below was verified this
session against this machine's real game zips two ways: by hand with `tools/pyc37.py --outline`/direct
bytecode reads, and then again by running `tools/novulon_api_check.py`'s own `check()` against the exact
rows below (not a hand-picked subset) before they were committed here - so the result is exactly what
`python tools/novulon_api_check.py` will report, not a hopeful guess at how its checker works.

`services` and `sims4.localization` are PACKAGES in this build (`services/__init__.pyc`,
`sims4/localization/__init__.pyc`), not flat modules - `novulon_api_check.py`'s `GameZips.find_module`
appends '.pyc' directly to the dotted module path with no package fallback, so the row's `module` field
has to spell the real archive path: 'services.__init__' -> 'services/__init__.pyc',
'sims4.localization.__init__' -> 'sims4/localization/__init__.pyc'. Both confirmed present this session.

`services.get_instance_manager` is not a `def` in `services/__init__.pyc`, so `pyc37.py --outline` alone
will not show it - it is a plain module-level attribute assigned once, at module load
(`tuning_managers = InstanceTuningManagers(); get_instance_manager = tuning_managers.__getitem__`),
confirmed by disassembling the module's own top-level bytecode directly (STORE_NAME at that point). The
checker's own generic name-descent still finds it (a STORE_NAME always lands in `co_names`, whether it
backs a `def`, a class, or a plain assignment) - recorded here as kind 'member' since it is not itself a
`def`.

`InstanceManager.types` (sims4/tuning/instance_manager.pyc) is a `@property` (confirmed: `LOAD_NAME
property` immediately precedes its `MAKE_FUNCTION`/`CALL_FUNCTION 1`/`STORE_NAME types`) returning
`self._tuned_classes` - so `services.get_instance_manager(sims4.resources.Types.OBJECT).types` is read
without calling it. This closes SPEC.md Sec 18's open item "the exact caller of every loaded object tuning
class inside inject.py's sweep()": `services.get_instance_manager(...).types.values()` is exactly that. A
decorator does not remove the underlying function's own code object, so the checker's descent (which only
looks for a same-named child code object) finds `types` the same way it finds an ordinary method.

`objects.script_object.ScriptObject._super_affordances` is NOT listed below, on purpose, even though
`inject.py` reads/writes exactly that attribute: it is referenced only inside several of `ScriptObject`'s
own METHOD bodies (confirmed this session by scoping the search to `ScriptObject`'s own class-body
`co_names` specifically, which does NOT contain it - unlike `_anim_overrides_cls`, which IS a class-body
tunable declaration and is listed below), not bound at the class body's own level. The checker's descent
only looks one name at a time inside whichever code object it has already reached, so it cannot see an
attribute that is only read/written inside a method - the correct, checkable citation for the same fact is
the method game_api.md already names, `ScriptObject.super_affordances` (confirmed a nested method of
`ScriptObject`, line 1819, matching game_api.md Sec 1's own citation), listed below instead. This is a
narrower, more accurate claim than "the attribute name appears somewhere in the file", which is all a
whole-module string search (this session's first pass) actually proves.

`is_computer_tuning_class`'s tuning-VALUE comparisons ('computerType', 'carryObject', 'tablet' as string
content of a `params` mapping) are not listed below either - they are per-object XML tuning data, never
Python symbols in any .pyc, so this checker cannot find them by construction (there is no name to look
up). They are carried forward unchanged from gaps.md Sec A.1's disassembly of an installed, working mod
(MC Command Center) that performs exactly this comparison in production; that disassembly is the
verification for the comparison itself, while `_anim_overrides_cls` (the attribute name the comparison
starts from) is freshly confirmed below against this game's own script_object.pyc.

Game build note: `novulon_api_check.py`'s own `game_build_version()` reads `Delta\\<pack>\\Version.ini`
(every installed pack agrees, confirmed on this machine), which is `1.126.73.1030` - a different string
from the non-Delta `E:/The Sims 4/EP21/Version.ini`'s `packversion` (`109.0.465.1030`). `CHECKED_AGAINST`
below uses the Delta value specifically so it matches what a real `novulon_api_check.py` run compares
against, not the other file.
"""

CHECKED_AGAINST = '1.126.73.1030'

ROWS = [
    # services/__init__.pyc (a package - see module docstring for the '.__init__' spelling)
    ('services.__init__', 'get_instance_manager', 'member'),   # tuning_managers.__getitem__, see docstring
    ('services.__init__', 'object_manager', 'function'),        # line 663: zone.object_manager if a zone
    ('services.__init__', 'on_enter_main_menu', 'function'),     # already live in speedkit_monitor/loadtimer.py

    # zone.pyc - already used live by speedkit_monitor/loadtimer.py; re-confirmed present this session
    ('zone', 'Zone.start_services', 'method'),

    # sims4/resources.pyc - Types.OBJECT/INTERACTION are real class-level members (STORE_NAME inside the
    # Types class body, built by a factory call at class-body execution time - no plain int is pinned)
    ('sims4.resources', 'Types', 'class'),
    ('sims4.resources', 'Types.OBJECT', 'member'),
    ('sims4.resources', 'Types.INTERACTION', 'member'),

    # sims4/tuning/instance_manager.pyc
    ('sims4.tuning.instance_manager', 'InstanceManager.types', 'method'),   # a @property, see docstring
    ('sims4.tuning.instance_manager', 'InstanceManager.get', 'method'),

    # indexed_manager.pyc (top-level module, not a package)
    ('indexed_manager', 'CallbackTypes', 'class'),
    ('indexed_manager', 'CallbackTypes.ON_OBJECT_ADD', 'member', 0),
    ('indexed_manager', 'IndexedManager.register_callback', 'method'),

    # objects/script_object.pyc - see module docstring for why _super_affordances itself isn't listed
    ('objects.script_object', 'ScriptObject._anim_overrides_cls', 'member'),
    ('objects.script_object', 'ScriptObject.super_affordances', 'method'),

    # sims4/commands.pyc - already used live by speedkit_monitor/commands.py; re-confirmed present this
    # session, including that Command's own argument parsing supports a trailing `*args: str` vararg
    # ('novulon.do <action_id> [args]'), read directly from parse_args's own bytecode (spec.varargs)
    ('sims4.commands', 'Command', 'class'),
    ('sims4.commands', 'CommandType', 'class'),
    ('sims4.commands', 'CommandType.Live', 'member'),
    ('sims4.commands', 'CheatOutput', 'class'),

    # ui/ui_dialog_notification.pyc + sims4/localization's __init__.pyc - common.notify(), same call
    # shape already used live by speedkit_monitor/common.py
    ('ui.ui_dialog_notification', 'UiDialogNotification', 'class'),
    ('ui.ui_dialog_notification', 'UiDialogNotification.UiDialogNotificationUrgency', 'class'),
    ('ui.ui_dialog_notification', 'UiDialogNotification.UiDialogNotificationUrgency.URGENT', 'member'),
    ('sims4.localization.__init__', 'LocalizationHelperTuning.get_raw_text', 'method'),
]
