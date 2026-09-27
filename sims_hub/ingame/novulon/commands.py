"""Cheat-console commands and the two registries every other Novulon package builds against.

  novulon.menu                     open the Main Menu
  novulon.do <action_id> [args]    call one registered action directly, no menu needed

sims4.commands.Command(*aliases, command_type=...) registers the function; CommandType.Live is valid in
the retail game (verified in this build's core.zip:sims4/commands.pyc, already used live by
speedkit_monitor/commands.py). `novulon.do`'s trailing `[args]` is a real `*args: str` vararg parameter -
confirmed this session against sims4/commands.pyc:parse_args (`spec.varargs`/`spec.annotations.get(...)`
are read and each extra token is parsed with that annotation), not guessed.

Two registries live here, both core-owned (feature packages only ever CALL these two, never edit this
file):

1. Action registry - add(action_id, fn) / do(action_id, connection, *args). Every interactive thing in
   Novulon (a menu row, a Sim Card button, a Cheats-tile shortcut) is registered once, under one stable
   action_id, as fn(connection, *args) -> Page | None | anything. A menukit Row's on_activate and the
   function registered here for the SAME action_id must be the literal same function (SPEC.md Sec.3.7 and
   Sec.4: "the menu is one interface to a function, never a separate code path" - and every Tier-4 test
   calls do() directly, with no dialog at all, which only works if do() never shows anything itself). do()
   is therefore pure: it calls the function and returns whatever it returns; it is guarded, so a broken
   action logs and returns None instead of taking the caller down.

2. Section registry - add_section(key, provider, label=..., ...) / build_main_menu_page(). Feature
   packages (sims/, household/, gameplay/, adult/, settings_ui/, ...) each register their own Main Menu
   tile here at their own import time; this file never hard-codes their names or how many there are.
   build_main_menu_page() is itself registered as the 'novulon.menu' action, so 'novulon.do novulon.menu'
   and the 'novulon.menu' cheat both go through the exact same code.

This file also owns the one hook menukit's own stack.py asks core to install (its module docstring:
"hooks.py/__init__.py, BP1, call reset_all() from that hook"): wrapping services.on_enter_main_menu to
clear every connection's NavStack, so a stale page tree from a previous save/session never leaks into a
new one - install_session_reset_hook() below, called once from __init__.py's start-up sequence.

The other place this file depends on menukit (BP2, not core): showing a Page for the first time, when
there is no dialog open yet to push onto (the 'novulon.menu'/'novulon.do' console commands) - _show()
below resets that connection's NavStack and calls menukit's own `render.show_page` (menukit/render.py,
verified present and its call shape read directly from source this session). Guarded anyway at both call
sites, so a mismatch after some future menukit change only logs; it never breaks the game. Once a dialog
IS open, pushing a Page a row's on_activate returned is entirely menukit's own job (render.py's own
_dispatch), not this file's.
"""
from . import common, hooks

_actions = {}          # action_id -> fn(connection, *args)
_sections = {}          # key -> {label, description, icon, order, is_visible, provider, action_id}
_SECTION_PREFIX = 'novulon.menu.'
_registered = False


# ------------------------------------------------------------------ action registry
def add(action_id, fn):
    """Register fn(connection, *args) under action_id. Re-registering the same id with a *different*
    function is logged (two feature modules picking the same id is almost certainly a bug) but never
    raises; re-registering with the same function again (a module reloaded by a test) is silent."""
    prev = _actions.get(action_id)
    if prev is not None and prev is not fn:
        common.log('novulon: action %r re-registered with a different function' % (action_id,))
    _actions[action_id] = fn


def is_registered(action_id):
    """True if action_id is registered. This exact name/signature is menukit/stack.py's own contract
    (validate_page calls commands.is_registered(row.id) for every non-Back row before a page can be
    pushed) - do not rename without also fixing menukit."""
    return action_id in _actions


def do(action_id, connection=None, *args):
    """Call the function registered under action_id with (connection, *args). Returns whatever it
    returns (often a menukit Page, or None); logs and returns None for an unknown id or a raised
    exception - never shows a dialog itself, see the module docstring."""
    fn = _actions.get(action_id)
    if fn is None:
        common.log('novulon.do: unknown action %r' % (action_id,))
        return None
    return common.guarded('novulon.do %r' % (action_id,), fn, connection, *args)


# ------------------------------------------------------------------ section registry (Main Menu tiles)
def add_section(key, provider, *, label, description='', icon=None, order=0, is_visible=None):
    """Register one Main Menu tile. `provider(connection, selected_ids=None)` returns that section's
    root Page - the exact function used both as the tile Row's on_activate and as the action registered
    under 'novulon.menu.<key>' (so 'novulon.do novulon.menu.<key>' opens the same section from the
    console, with no menu navigation needed). `is_visible()`, if given, is re-checked every time the root
    page is built; any exception or a plain False hides the tile entirely - SPEC.md's hard rule for the
    Adult tile is "not present at all", never "present but greyed out or broken". Re-registering the same
    key replaces it (last import wins; the real game imports a module once, a test may reload it)."""
    action_id = _SECTION_PREFIX + key
    add(action_id, provider)
    _sections[key] = {'label': label, 'description': description, 'icon': icon, 'order': order,
                       'is_visible': is_visible, 'provider': provider, 'action_id': action_id}


def sections():
    """Every registered section, in Main Menu order: declared `order`, then key, for a stable sort."""
    return sorted(_sections.items(), key=lambda kv: (kv[1]['order'], kv[0]))


def visible_sections(connection=None):
    """`sections()` filtered to the ones whose `is_visible()` (if any) is true right now."""
    out = []
    for key, sec in sections():
        vis = sec['is_visible']
        if vis is None:
            out.append((key, sec))
            continue
        if common.guarded('novulon: %s section visibility' % (key,), vis):
            out.append((key, sec))
    return out


def build_main_menu_page(connection=None, selected_ids=None):
    """The root 'Novulon' Page: one tile Row per currently visible section, in declared order. The
    actual set/order of tiles (Sims, Household, Gameplay, Cheats, Settings, Adult when unlocked -
    SPEC.md Sec.2/Sec.19) comes entirely from what other packages registered; nothing is hard-coded here."""
    from .menukit.page import Row, Page
    rows = [Row(id=sec['action_id'], label=sec['label'], description=sec['description'],
                icon=sec['icon'], on_activate=sec['provider'])
            for _key, sec in visible_sections(connection)]
    return Page(title='Novulon', rows=rows, style='tiles')


add('novulon.menu', lambda connection=None, *args: build_main_menu_page(connection))


# ------------------------------------------------------------------ showing a page for the first time
def _looks_like_page(x):
    """Duck-typed instead of importing menukit.page.Page at module load: a Page has at least these two
    attributes (title, rows) per its SPEC.md Sec.4 constructor."""
    return x is not None and hasattr(x, 'rows') and hasattr(x, 'title')


def _show(connection, page):
    """Open `page` for `connection` right now: reset that connection's menukit NavStack (a console
    command has no navigation history to push onto - SPEC.md's Main Menu/console entry points always
    start fresh, never stacked on top of whatever a player happened to have open) and hand it to
    menukit's own render.show_page, which pushes the page (validating every row's id is a registered
    action first - menukit/stack.py's own contract, raises ValueError if not, left to propagate to the
    caller's common.guarded() since that is a real bug in whichever feature package built the page) and
    actually builds/shows the dialog."""
    from .menukit import render, stack
    stack.reset(connection)
    render.show_page(connection, page)


# ------------------------------------------------------------------ cheat command bodies
def menu_command(_connection=None):
    """Body of 'novulon.menu': open the root Main Menu page fresh."""
    out = common.cheat_output(_connection)
    page = do('novulon.menu', _connection)
    if not _looks_like_page(page):
        out('Novulon menu is not available yet - see Novulon\\logs\\novulon.log')
        return
    if common.guarded('novulon.menu: show root page', _show, _connection, page) is None:
        out('Novulon menu could not be shown - see Novulon\\logs\\novulon.log')


def do_command(action_id, *args, _connection=None):
    """Body of 'novulon.do <action_id> [args]': call the action directly. If it returns a Page (the
    action is itself a menu section or sub-page), show it too, so a typed command and a menu click always
    end up in the same place - never a separate code path."""
    out = common.cheat_output(_connection)
    if not action_id:
        out('Usage: novulon.do <action_id> [args]')
        return None
    if not is_registered(action_id):
        out('novulon.do: unknown action %r' % (action_id,))
        return None
    result = do(action_id, _connection, *args)
    if _looks_like_page(result):
        common.guarded('novulon.do %r: show page' % (action_id,), _show, _connection, result)
    return result


def register():
    """Register 'novulon.menu' and 'novulon.do' with the game (once). Returns True on success."""
    global _registered
    if _registered:
        return True
    import sims4.commands
    live = sims4.commands.CommandType.Live

    @sims4.commands.Command('novulon.menu', command_type=live)
    def novulon_menu(_connection=None):
        common.guarded('novulon.menu', menu_command, _connection)

    @sims4.commands.Command('novulon.do', command_type=live)
    def novulon_do(action_id: str = '', *args: str, _connection=None):
        common.guarded('novulon.do', do_command, action_id, *args, _connection=_connection)

    _registered = True
    return True


# ------------------------------------------------------------------ menukit session-reset hook
def _reset_navstacks():
    from .menukit import stack
    stack.reset_all()


def install_session_reset_hook():
    """Wrap services.on_enter_main_menu to clear every connection's menukit NavStack - the exact hook
    point speedkit_monitor/loadtimer.py already wraps live for its own per-session reset, and the one
    menukit/stack.py's own docstring asks core (this file) to install ('hooks.py/__init__.py, BP1, call
    reset_all() from that hook'), so a stale page tree from a previous save/session never leaks into a
    new one. Returns True on success."""
    try:
        import services
    except Exception:
        common.log_exception('novulon: hook services.on_enter_main_menu')
        return False
    ok = hooks.install(
        services, 'on_enter_main_menu',
        lambda orig: hooks.around(
            orig, after=lambda a, r: common.guarded('novulon: reset menukit NavStacks', _reset_navstacks),
            label='novulon session reset', always=True),
        'services.on_enter_main_menu (novulon session reset)')
    return ok
