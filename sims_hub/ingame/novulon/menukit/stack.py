"""One `NavStack` per connection id (SPEC.md `menukit/` §4).

Pure Python except for the one guarded, lazy dependency on `commands.py` (core-owned, BP1) used to
enforce "every Row.id must already be registered" - see `validate_page`/`set_command_checker` below.
Nothing else here imports the game or `common`/`commands` at module load time, so this file (and its
tests) never depend on those other packages having been built yet.

Cleared on `on_enter_main_menu` (the same hook `speedkit_monitor/loadtimer.py` already uses for its own
per-session reset - `hooks.py`/`__init__.py`, BP1, call `reset_all()` from that hook) so a stale stack
from a previous save/session never leaks into a new one.
"""
from . import page as _page
from . import search as _search

BACK_ID = _page.BACK_ID
SEARCH_ID = _search.SEARCH_ID
_SYNTHETIC_IDS = (BACK_ID, SEARCH_ID)


def back_row():
    """The synthetic Back row every non-root page gets prepended with, automatically."""
    return _page.Row(BACK_ID, 'Back')


# --------------------------------------------------------------------- command-registration guard
_checker = None    # set_command_checker(fn); fn(action_id) -> bool. None -> use the real commands.py.


def set_command_checker(fn):
    """Feature/menukit tests inject a fake checker here instead of needing a real commands.py loaded.
    Pass None to go back to the real (lazily-imported) `commands.is_registered`."""
    global _checker
    _checker = fn


def _is_registered(action_id):
    if _checker is not None:
        return _checker(action_id)
    try:
        from .. import commands as _commands   # core-owned (BP1); lazy so menukit stays importable
    except Exception:
        return True   # commands.py not built/loadable yet - never hard-fail menukit over that
    try:
        return _commands.is_registered(action_id)
    except AttributeError:
        return True   # an older/partial commands.py without is_registered yet - skip, don't crash


def validate_page(page):
    """Raises ValueError if any row (other than the synthetic Back row) has no registered command id.
    This is SPEC.md §4's own contract ('menukit raises if a page ships a row with no command
    fallback') - every Row.id doubles as a `novulon.do <action_id>` console command, so a row with no
    matching `commands.add()` call is a real bug in the feature package that built the page, not
    something to paper over."""
    for row in page.rows:
        if row.id in _SYNTHETIC_IDS:
            continue
        if not _is_registered(row.id):
            raise ValueError(
                "menukit: row %r on page %r has no registered command - call "
                "commands.add(%r, fn) before building this page" % (row.id, page.title, row.id))


# --------------------------------------------------------------------- selection tray (persists
# across a filter change or page turn - SPEC.md §4/§5.3; lives on the NavStack, never on the dialog)
def apply_selection_delta(tray, page_ids, checked_ids):
    """Fold one dialog response into a persistent multi-select tray.

    `page_ids`: every row id that was shown (selectable) on the page that just responded.
    `checked_ids`: the ids that came back checked in that same response.
    Only rows that were actually shown on this page are added to or dropped from `tray` - ids from
    other pages/filters the player checked earlier are left alone. Returns a new set; does not mutate
    `tray` in place.
    """
    tray = set(tray)
    page_ids = set(page_ids)
    checked_ids = set(checked_ids)
    tray -= (page_ids - checked_ids)
    tray |= (page_ids & checked_ids)
    return tray


# --------------------------------------------------------------------- the stack itself
class NavStack(object):
    def __init__(self):
        self._pages = []      # root at index 0; current at [-1]
        self.state = {}       # generic per-connection scratch (filters/search query/page index/...)
        self.tray = set()     # persistent multi-select tray (SPEC.md §5.3)

    def depth(self):
        return len(self._pages)

    def is_root(self):
        return len(self._pages) <= 1

    def current(self):
        return self._pages[-1] if self._pages else None

    def push(self, page):
        """Validate and push a new page (going deeper - a row was activated)."""
        validate_page(page)
        self._pages.append(page)
        return page

    def replace_top(self, page):
        """Validate and rebuild the CURRENT page in place (search/filter/page-turn) without growing
        the stack - this is what a filter-chip toggle or a page-turn row should call, never push()."""
        validate_page(page)
        if self._pages:
            self._pages[-1] = page
        else:
            self._pages.append(page)
        return page

    def pop(self):
        """Leave the current page (Back was pressed). Never pops the root. Returns the new current
        page (or None if the stack was already empty)."""
        if len(self._pages) > 1:
            self._pages.pop()
        return self.current()

    def clear(self):
        self._pages = []
        self.state = {}
        self.tray = set()

    def title_for(self, page=None):
        """'Novulon' at the root, 'Novulon › Sims › Females' deeper in - joined from
        Page.breadcrumb, since there is no native breadcrumb widget (SPEC.md §4)."""
        page = page if page is not None else self.current()
        if page is None:
            return 'Novulon'
        crumbs = ('Novulon',) + tuple(page.breadcrumb)
        return ' › '.join(str(c) for c in crumbs)

    def rows_for_render(self, page=None):
        """The rows to actually send to the dialog: Back prepended unless we're at the root or the
        page is a multi-select checkbox picker (where a 'Back' checkbox makes no sense - the player
        exits a multi-select page by closing/cancelling the dialog, handled by render.py)."""
        page = page if page is not None else self.current()
        rows = list(page.rows)
        if not self.is_root() and not page.multi_select:
            rows = [back_row()] + rows
        return rows


_stacks = {}   # connection id -> NavStack


def for_connection(connection_id):
    """The NavStack for this connection, creating one on first use."""
    stack = _stacks.get(connection_id)
    if stack is None:
        stack = NavStack()
        _stacks[connection_id] = stack
    return stack


def reset(connection_id):
    """Drop one connection's stack entirely (e.g. it disconnected)."""
    _stacks.pop(connection_id, None)


def reset_all():
    """Drop every connection's stack - call this from the on_enter_main_menu hook (core, BP1) so a
    stale stack from a previous save never leaks into a new one."""
    _stacks.clear()
