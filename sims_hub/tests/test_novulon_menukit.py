"""Tests for ingame/novulon/menukit/ (BP2 - the dialog framework, SPEC.md §4).

Tier 1 (pure Python, no game): page.py/paging.py/stack.py's pure pieces/search.py's pure
filter/confirm.py's naming helpers/notify.py's constants - imported directly, no fakes needed, since
menukit's whole design point is that none of this touches the game at import time.

A second layer below drives render.py/confirm.py/search.py's game-facing halves against small, hand
written fake `ui.*`/`sims4.localization` modules that reproduce the REAL, disassembly-verified behavior
this package's own docstrings cite (option_id auto-assignment, ObjectPickerRow-only validation,
title/text as callables, text_inputs as an attribute-holder, ...) - not just enough to not-crash, but
enough that a wrong option_id mapping or a wrong callable-vs-value field would make one of these tests
fail. Nothing here starts the game or touches E:\\The Sims 4 or the real Mods folder.
"""
import os
import sys
import types
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon.menukit import page as mk_page          # noqa: E402
from novulon.menukit import paging as mk_paging      # noqa: E402
from novulon.menukit import stack as mk_stack        # noqa: E402
from novulon.menukit import search as mk_search      # noqa: E402
from novulon.menukit import confirm as mk_confirm    # noqa: E402
from novulon.menukit import render as mk_render      # noqa: E402
from novulon import menukit as mk                    # noqa: E402

# menukit/__init__.py deliberately re-exports notify.py's own `notify` FUNCTION as `menukit.notify`
# (see menukit/__init__.py's docstring/quickstart - `menukit.notify('Done.', ...)` is the whole point of
# that name), which permanently shadows the `notify` SUBMODULE under that same attribute name once
# __init__.py has run - `from novulon.menukit import notify`/`import novulon.menukit.notify` both
# resolve via attribute access on the already-initialized `menukit` package and would get the function,
# not the submodule. Reach the real submodule (its LEVEL_PLAYER/etc. constants, its own notify() for the
# fallback-degrade tests below) straight out of sys.modules instead - it is already cached there as a
# side effect of `menukit`/`render.py` importing it.
mk_notify = sys.modules['novulon.menukit.notify']

Row = mk_page.Row
Page = mk_page.Page


def _install_fake_module(test, name, module):
    """Install `module` as `sys.modules[name]` for the duration of one test, restoring BOTH the
    `sys.modules` entry and the parent package's own attribute afterwards (e.g. `novulon.common` as an
    object on the real `novulon` package, not just the `sys.modules['novulon.common']` dict entry) -
    `from package import submodule` resolves via `getattr(package, 'submodule')` first, so restoring
    only the dict entry leaves a later `from novulon import common` (or `from .. import common` inside
    menukit) seeing whichever test last overwrote that attribute instead of the real module."""
    parts = name.split('.')
    parent_name = '.'.join(parts[:-1])
    leaf = parts[-1]

    saved_in_modules = sys.modules.get(name)
    created_parents = []
    for i in range(1, len(parts)):
        pkg_name = '.'.join(parts[:i])
        if pkg_name not in sys.modules:
            sys.modules[pkg_name] = types.ModuleType(pkg_name)
            created_parents.append(pkg_name)

    parent = sys.modules[parent_name] if parent_name else None
    had_attr = parent is not None and leaf in parent.__dict__
    saved_attr = getattr(parent, leaf, None) if parent is not None else None

    sys.modules[name] = module
    if parent is not None:
        setattr(parent, leaf, module)

    def _restore():
        if saved_in_modules is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved_in_modules
        if parent is not None:
            if had_attr:
                setattr(parent, leaf, saved_attr)
            else:
                parent.__dict__.pop(leaf, None)
        for pkg_name in reversed(created_parents):
            sys.modules.pop(pkg_name, None)
    test.addCleanup(_restore)


def _make_unimportable(test, name):
    """Force `from parent import leaf` to raise for `name`, for the duration of one test, and restore
    both the real module and the parent's attribute afterwards. Two things make this trickier than a
    plain `sys.modules.pop`, now that BP1's real `novulon/commands.py`/`common.py` exist on disk in this
    working tree: (1) popping the `sys.modules` entry alone just makes Python re-import the real file
    fresh - `sys.modules[name] = None` is the documented sentinel that actually forces an ImportError
    instead; (2) `from X import Y` resolves via `getattr(X, 'Y')` FIRST (see `_install_fake_module`'s
    docstring), so a real module already imported once this process (e.g. by an interop test) leaves
    that attribute cached on the real `novulon` package object even after `sys.modules[name]` is
    poisoned - the attribute has to be cleared too."""
    parts = name.split('.')
    parent = sys.modules.get('.'.join(parts[:-1])) if len(parts) > 1 else None
    leaf = parts[-1]

    saved_in_modules = sys.modules.get(name)
    had_attr = parent is not None and leaf in parent.__dict__
    saved_attr = getattr(parent, leaf, None) if parent is not None else None

    sys.modules[name] = None
    if parent is not None:
        parent.__dict__.pop(leaf, None)

    def _restore():
        if saved_in_modules is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved_in_modules
        if parent is not None and had_attr:
            setattr(parent, leaf, saved_attr)
    test.addCleanup(_restore)


# ============================================================================================ page.py
class RowTests(unittest.TestCase):
    def test_requires_an_id(self):
        with self.assertRaises(ValueError):
            Row('', 'Label')

    def test_enabled_reflects_disabled_text(self):
        self.assertTrue(Row('a', 'A').enabled)
        self.assertFalse(Row('a', 'A', disabled_text='nope').enabled)

    def test_defaults(self):
        r = Row('a', 'A')
        self.assertEqual(r.description, '')
        self.assertEqual(r.tags, ())
        self.assertFalse(r.selected)
        self.assertIsNone(r.on_activate)


class PageTests(unittest.TestCase):
    def test_rejects_bad_style(self):
        with self.assertRaises(ValueError):
            Page('T', [], style='grid')
        with self.assertRaises(ValueError):
            Page('T', [], row_style='oops')

    def test_single_select_defaults_to_one(self):
        p = Page('T', [])
        self.assertEqual(p.min_selectable, 1)
        self.assertEqual(p.max_selectable, 1)
        self.assertFalse(p.multi_select)

    def test_multi_select_defaults_to_unlimited(self):
        p = Page('T', [], multi_select=True)
        self.assertEqual(p.min_selectable, 0)
        self.assertEqual(p.max_selectable, 0)

    def test_multi_select_explicit_max_is_kept(self):
        p = Page('T', [], multi_select=True, max_selectable=5, min_selectable=2)
        self.assertEqual(p.max_selectable, 5)
        self.assertEqual(p.min_selectable, 2)

    def test_never_leaves_selectable_fields_none(self):
        # render.py's docstring: the engine crashes on None for both fields - this must never regress.
        for kw in ({}, {'multi_select': True}, {'multi_select': True, 'max_selectable': 3}):
            p = Page('T', [], **kw)
            self.assertIsInstance(p.min_selectable, int)
            self.assertIsInstance(p.max_selectable, int)


# ============================================================================================ paging.py
class PagingTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(mk_paging.page_of([], 60, 0), ([], False, False))

    def test_single_page(self):
        rows, has_prev, has_next = mk_paging.page_of(list(range(10)), 60, 0)
        self.assertEqual(rows, list(range(10)))
        self.assertFalse(has_prev)
        self.assertFalse(has_next)

    def test_middle_page_has_both_neighbors(self):
        items = list(range(200))
        rows, has_prev, has_next = mk_paging.page_of(items, 60, 1)
        self.assertEqual(rows, list(range(60, 120)))
        self.assertTrue(has_prev)
        self.assertTrue(has_next)

    def test_last_page_partial(self):
        items = list(range(148))
        rows, has_prev, has_next = mk_paging.page_of(items, 60, 2)
        self.assertEqual(rows, list(range(120, 148)))
        self.assertTrue(has_prev)
        self.assertFalse(has_next)

    def test_out_of_range_index_clamps_instead_of_raising(self):
        items = list(range(10))
        rows, has_prev, has_next = mk_paging.page_of(items, 60, 99)
        self.assertEqual(rows, items)
        rows, has_prev, has_next = mk_paging.page_of(items, 60, -5)
        self.assertEqual(rows, items)

    def test_never_builds_more_than_one_page(self):
        # gaps.md §B.2: no native row-count ceiling, so this is the actual backstop - a 5000-Sim save
        # must never see more than page_size rows built in one call.
        rows, _, _ = mk_paging.page_of(list(range(5000)), 80, 3)
        self.assertLessEqual(len(rows), 80)

    def test_footer_text_matches_spec_shape(self):
        self.assertEqual(mk_paging.footer_text(148, 60, 0), 'Page 1 of 3 (1-60 of 148)')
        self.assertEqual(mk_paging.footer_text(148, 60, 2), 'Page 3 of 3 (121-148 of 148)')
        self.assertEqual(mk_paging.footer_text(0, 60, 0), 'Page 1 of 1 (0 of 0)')


# ============================================================================================ search.py
class SearchApplyTests(unittest.TestCase):
    def test_no_query_returns_everything(self):
        self.assertEqual(mk_search.apply(['Bob', 'Ann'], None), ['Bob', 'Ann'])
        self.assertEqual(mk_search.apply(['Bob', 'Ann'], ''), ['Bob', 'Ann'])
        self.assertEqual(mk_search.apply(['Bob', 'Ann'], '   '), ['Bob', 'Ann'])

    def test_case_insensitive_substring(self):
        self.assertEqual(mk_search.apply(['Bob Pancakes', 'Ann Lee'], 'bob'), ['Bob Pancakes'])
        self.assertEqual(mk_search.apply(['Bob Pancakes', 'Ann Lee'], 'PANCAKES'), ['Bob Pancakes'])

    def test_custom_key(self):
        items = [{'name': 'Bob'}, {'name': 'Ann'}]
        self.assertEqual(mk_search.apply(items, 'an', key=lambda i: i['name']), [{'name': 'Ann'}])

    def test_row_for_label_remembers_last_query(self):
        self.assertEqual(mk_search.row_for(None).label, 'Search…')
        self.assertEqual(mk_search.row_for('Bob').label, 'Search… (last: "Bob")')
        self.assertEqual(mk_search.row_for(None).id, mk_search.SEARCH_ID)


# ============================================================================================ stack.py
class FakeSimInfo(object):
    def __init__(self, id, first_name, last_name, full_name=None):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        if full_name is not None:
            self.full_name = full_name


class NavStackTests(unittest.TestCase):
    def setUp(self):
        mk_stack.set_command_checker(lambda action_id: True)   # every id "registered" by default
        self.addCleanup(mk_stack.set_command_checker, None)

    def test_root_page_gets_no_back_row(self):
        nav = mk_stack.NavStack()
        nav.push(Page('Root', [Row('a', 'A')]))
        rows = nav.rows_for_render()
        self.assertEqual([r.id for r in rows], ['a'])

    def test_deeper_page_gets_back_row_first(self):
        nav = mk_stack.NavStack()
        nav.push(Page('Root', [Row('a', 'A')]))
        nav.push(Page('Deeper', [Row('b', 'B')]))
        rows = nav.rows_for_render()
        self.assertEqual([r.id for r in rows], [mk_stack.BACK_ID, 'b'])

    def test_multi_select_page_never_gets_a_back_row(self):
        nav = mk_stack.NavStack()
        nav.push(Page('Root', [Row('a', 'A')]))
        nav.push(Page('Pick some', [Row('b', 'B')], multi_select=True))
        rows = nav.rows_for_render()
        self.assertEqual([r.id for r in rows], ['b'])

    def test_pop_never_empties_the_root(self):
        nav = mk_stack.NavStack()
        nav.push(Page('Root', [Row('a', 'A')]))
        nav.pop()
        self.assertEqual(nav.depth(), 1)
        self.assertEqual(nav.current().title, 'Root')

    def test_pop_leaves_the_previous_page(self):
        nav = mk_stack.NavStack()
        nav.push(Page('Root', []))
        nav.push(Page('Deeper', []))
        nav.pop()
        self.assertEqual(nav.current().title, 'Root')

    def test_replace_top_does_not_grow_the_stack(self):
        nav = mk_stack.NavStack()
        nav.push(Page('Root', []))
        nav.push(Page('List v1', [Row('a', 'A')]))
        nav.replace_top(Page('List v2', [Row('b', 'B')]))
        self.assertEqual(nav.depth(), 2)
        self.assertEqual(nav.current().title, 'List v2')

    def test_clear_resets_everything(self):
        nav = mk_stack.NavStack()
        nav.push(Page('Root', []))
        nav.tray.add(1)
        nav.state['x'] = 1
        nav.clear()
        self.assertEqual(nav.depth(), 0)
        self.assertEqual(nav.tray, set())
        self.assertEqual(nav.state, {})

    def test_title_for_joins_breadcrumb_with_novulon_prefix(self):
        nav = mk_stack.NavStack()
        page = Page('Females', [], breadcrumb=('Sims', 'Females'))
        nav.push(page)
        self.assertEqual(nav.title_for(), 'Novulon \u203a Sims \u203a Females')

    def test_title_for_root_with_no_breadcrumb_is_just_novulon(self):
        nav = mk_stack.NavStack()
        nav.push(Page('Main Menu', []))
        self.assertEqual(nav.title_for(), 'Novulon')

    def test_for_connection_returns_the_same_stack_for_the_same_id(self):
        a = mk_stack.for_connection('conn-1')
        b = mk_stack.for_connection('conn-1')
        self.assertIs(a, b)
        c = mk_stack.for_connection('conn-2')
        self.assertIsNot(a, c)
        mk_stack.reset('conn-1')
        mk_stack.reset('conn-2')

    def test_reset_all_drops_every_connection(self):
        mk_stack.for_connection('x').push(Page('T', []))
        mk_stack.for_connection('y').push(Page('T', []))
        mk_stack.reset_all()
        self.assertEqual(mk_stack.for_connection('x').depth(), 0)
        mk_stack.reset_all()


class CommandRegistrationGuardTests(unittest.TestCase):
    def tearDown(self):
        mk_stack.set_command_checker(None)

    def test_raises_when_a_row_has_no_registered_command(self):
        mk_stack.set_command_checker(lambda action_id: False)
        nav = mk_stack.NavStack()
        with self.assertRaises(ValueError):
            nav.push(Page('T', [Row('unregistered.thing', 'Do it')]))

    def test_back_and_search_rows_are_always_exempt(self):
        mk_stack.set_command_checker(lambda action_id: False)
        nav = mk_stack.NavStack()
        nav.push(Page('T', [mk_stack.back_row(), mk_search.row_for(None)]))   # must not raise

    def test_passes_when_the_checker_approves(self):
        seen = []
        mk_stack.set_command_checker(lambda action_id: seen.append(action_id) or True)
        nav = mk_stack.NavStack()
        nav.push(Page('T', [Row('registered.thing', 'Do it')]))
        self.assertEqual(seen, ['registered.thing'])

    def test_unimportable_commands_module_degrades_to_allow_not_crash(self):
        # No checker installed, and commands.py is unavailable (a build-order issue only, never expected
        # once the mod is finished) - validate_page must not block every other package's own development
        # over that. `sys.modules[name] = None` is the documented way to force an ImportError on a
        # relative import without needing the real file to actually be missing from disk.
        mk_stack.set_command_checker(None)
        _make_unimportable(self, 'novulon.commands')
        nav = mk_stack.NavStack()
        nav.push(Page('T', [Row('whatever.id', 'X')]))   # must not raise

    def test_interops_with_the_real_bp1_commands_module_when_present(self):
        # BP1's real commands.py (ingame/novulon/commands.py) exposes exactly is_registered(action_id) -
        # this drives menukit's own guard against the ACTUAL file, not a stand-in, so a signature drift
        # between the two packages is caught here rather than only at Tier 2/5.
        try:
            from novulon import commands as real_commands
        except Exception:
            self.skipTest('novulon.commands not present in this working tree yet')
        mk_stack.set_command_checker(None)
        marker = 'test.novulon.menukit.interop.marker'
        real_commands.add(marker, lambda connection=None, *a: None)
        nav = mk_stack.NavStack()
        nav.push(Page('T', [Row(marker, 'X')]))   # must not raise - it really is registered
        with self.assertRaises(ValueError):
            nav.push(Page('T2', [Row('test.novulon.menukit.interop.never_registered', 'Y')]))


class SelectionDeltaTests(unittest.TestCase):
    def test_adds_newly_checked_ids_from_this_page(self):
        tray = mk_stack.apply_selection_delta(set(), page_ids=[1, 2, 3], checked_ids=[1, 3])
        self.assertEqual(tray, {1, 3})

    def test_removes_unchecked_ids_that_were_shown_on_this_page(self):
        tray = mk_stack.apply_selection_delta({1, 2}, page_ids=[1, 2], checked_ids=[1])
        self.assertEqual(tray, {1})

    def test_leaves_ids_from_other_pages_untouched(self):
        # SPEC.md §5.3: selections persist across a filter change or page turn.
        tray = mk_stack.apply_selection_delta({99}, page_ids=[1, 2], checked_ids=[1])
        self.assertEqual(tray, {1, 99})

    def test_does_not_mutate_the_input_set(self):
        original = {1}
        mk_stack.apply_selection_delta(original, page_ids=[1], checked_ids=[])
        self.assertEqual(original, {1})


# ============================================================================================ confirm.py
class DisplayNameTests(unittest.TestCase):
    def test_prefers_full_name(self):
        self.assertEqual(mk_confirm.display_name(FakeSimInfo(1, 'Bob', 'Pancakes', full_name='Bob P.')),
                          'Bob P.')

    def test_falls_back_to_first_last(self):
        self.assertEqual(mk_confirm.display_name(FakeSimInfo(1, 'Bob', 'Pancakes')), 'Bob Pancakes')

    def test_falls_back_to_id_if_nothing_else(self):
        class Bare(object):
            id = 42
        self.assertEqual(mk_confirm.display_name(Bare()), 'Sim 42')


class CappedNamesTests(unittest.TestCase):
    def test_under_cap_reports_zero_remaining(self):
        sims = [FakeSimInfo(i, 'S', str(i)) for i in range(3)]
        shown, more = mk_confirm.capped_names(sims, cap=10)
        self.assertEqual(len(shown), 3)
        self.assertEqual(more, 0)

    def test_over_cap_stops_at_ten_and_counts_the_rest(self):
        sims = [FakeSimInfo(i, 'S', str(i)) for i in range(23)]
        shown, more = mk_confirm.capped_names(sims, cap=10)
        self.assertEqual(len(shown), 10)
        self.assertEqual(more, 13)

    def test_format_note_shape(self):
        sims = [FakeSimInfo(1, 'Alex', 'Doe')]
        self.assertEqual(mk_confirm.format_note(sims), 'Alex Doe')
        sims = [FakeSimInfo(i, 'S', str(i)) for i in range(12)]
        note = mk_confirm.format_note(sims)
        self.assertTrue(note.endswith('(+2 more)'), note)

    def test_format_note_empty(self):
        self.assertEqual(mk_confirm.format_note([]), '')


# ==================================================================== fake game modules (render/confirm/search)
class _Recorder(object):
    """Trivial ('KIND', ...) marker objects standing in for a real LocalizedString - lets a test assert
    exactly what text a callable resolves to without needing the real protobuf-backed type."""


def _raw(text):
    return ('RAW', text)


class FakeLocalizationHelperTuning(object):
    @classmethod
    def get_raw_text(cls, text):
        return _raw(text)

    @classmethod
    def get_bulleted_list(cls, header_string, *localized_strings):
        return ('BULLETED', header_string, localized_strings)

    @classmethod
    def get_comma_separated_list(cls, *strings):
        return ('COMMA', strings)


class FakeObjectPickerStyle(object):
    DEFAULT = 0
    NUMBERED = 1
    DELETE = 2


class FakeObjectPickerType(object):
    OBJECT = 4
    OBJECT_LARGE = 12


class FakeObjectPickerRow(object):
    def __init__(self, option_id=None, name=None, row_description=None, row_tooltip=None,
                 is_enable=True, is_selected=False, object_picker_style=0, icon=None, **kw):
        self.option_id = option_id
        self.name = name
        self.row_description = row_description
        self.row_tooltip = row_tooltip
        self.is_enable = is_enable
        self.is_selected = is_selected
        self.object_picker_style = object_picker_style
        self.icon = icon


class _TunableFactory(object):
    def __init__(self, cls):
        self._cls = cls

    def default(self, owner, **kwargs):
        return self._cls(owner, **kwargs)


class FakeUiObjectPicker(object):
    """Reproduces the three verified behaviors render.py depends on: option_id auto-assignment,
    ObjectPickerRow-only validation, and get_result_rows() returning picked objects in insertion order."""

    def __init__(self, owner=None, title=None, subtitle=None, picker_type=None,
                 min_selectable=None, max_selectable=None):
        self.owner = owner
        self.title = title
        self.subtitle = subtitle
        self.picker_type = picker_type
        self.min_selectable = min_selectable
        self.max_selectable = max_selectable
        self.picker_rows = []
        self.picked_results = []
        self._on_response = None

    @classmethod
    def TunableFactory(cls):
        return _TunableFactory(cls)

    def add_row(self, row):
        if not isinstance(row, FakeObjectPickerRow):
            raise TypeError('only ObjectPickerRow is accepted')
        if row.option_id is None:
            row.option_id = len(self.picker_rows)
        self.picker_rows.append(row)

    def get_result_rows(self):
        return [r for r in self.picker_rows if r.option_id in self.picked_results]

    def show_dialog(self, on_response=None):
        self._on_response = on_response

    def respond(self, option_ids):
        """Test-only: simulate the player checking these option_ids and closing the dialog."""
        self.picked_results = list(option_ids)
        if self._on_response is not None:
            self._on_response(self)


class FakeButtonType(object):
    DIALOG_RESPONSE_CLOSED = -1
    DIALOG_RESPONSE_OK = 10001
    DIALOG_RESPONSE_CANCEL = 10002


class FakeUiDialogOkCancel(object):
    def __init__(self, owner=None, title=None, text=None, subtitle=None, text_ok=None,
                 text_cancel=None, include_cancel_response=True):
        self.owner = owner
        self.title = title
        self.text = text
        self.subtitle = subtitle
        self.text_ok = text_ok
        self.text_cancel = text_cancel
        self.include_cancel_response = include_cancel_response
        self.response = None
        self._on_response = None

    @classmethod
    def TunableFactory(cls):
        return _TunableFactory(cls)

    def show_dialog(self, on_response=None):
        self._on_response = on_response

    def respond(self, response):
        self.response = response
        if self._on_response is not None:
            self._on_response(self)


class FakeUiDialogTextInputOkCancel(object):
    def __init__(self, owner=None, title=None, text=None, text_inputs=None, text_ok=None,
                 text_cancel=None, include_cancel_response=True):
        self.text_inputs = text_inputs
        self.text_input_responses = {}
        self._on_response = None

    @classmethod
    def TunableFactory(cls):
        return _TunableFactory(cls)

    def show_dialog(self, on_response=None):
        self._on_response = on_response

    def respond(self, query):
        self.text_input_responses['search'] = query
        if self._on_response is not None:
            self._on_response(self)


class FakeUiTextInput(object):
    class _F(object):
        def default(self):
            return object()

    @classmethod
    def TunableFactory(cls):
        return FakeUiTextInput._F()


class GameFakesMixin(object):
    """Installs fake ui.*/sims4.localization modules for one test, torn down afterwards."""

    def install_fakes(self):
        ui_dialog_picker = types.ModuleType('ui.ui_dialog_picker')
        ui_dialog_picker.UiObjectPicker = FakeUiObjectPicker
        ui_dialog_picker.ObjectPickerRow = FakeObjectPickerRow
        ui_dialog_picker.ObjectPickerStyle = FakeObjectPickerStyle
        ui_dialog_picker.ObjectPickerType = FakeObjectPickerType
        _install_fake_module(self, 'ui.ui_dialog_picker', ui_dialog_picker)

        ui_dialog = types.ModuleType('ui.ui_dialog')
        ui_dialog.UiDialogOkCancel = FakeUiDialogOkCancel
        ui_dialog.ButtonType = FakeButtonType
        _install_fake_module(self, 'ui.ui_dialog', ui_dialog)

        ui_dialog_generic = types.ModuleType('ui.ui_dialog_generic')
        ui_dialog_generic.UiDialogTextInputOkCancel = FakeUiDialogTextInputOkCancel
        _install_fake_module(self, 'ui.ui_dialog_generic', ui_dialog_generic)

        ui_text_input = types.ModuleType('ui.ui_text_input')
        ui_text_input.UiTextInput = FakeUiTextInput
        _install_fake_module(self, 'ui.ui_text_input', ui_text_input)

        localization = types.ModuleType('sims4.localization')
        localization.LocalizationHelperTuning = FakeLocalizationHelperTuning
        _install_fake_module(self, 'sims4.localization', localization)


# ============================================================================================ notify.py
class NotifyTests(unittest.TestCase, GameFakesMixin):
    def setUp(self):
        calls = []
        common = types.ModuleType('novulon.common')

        def fake_notify(title, text, urgent=False, level=None, visual_type=None):
            calls.append((title, text, urgent, level, visual_type))
            return True
        common.notify = fake_notify
        self.calls = calls
        _install_fake_module(self, 'novulon.common', common)

    def test_passes_fixed_defaults(self):
        mk_notify.notify('Title', 'Text')
        self.assertEqual(self.calls, [('Title', 'Text', False, mk_notify.LEVEL_PLAYER,
                                        mk_notify.VISUAL_INFORMATION)])

    def test_urgent_flag_passes_through(self):
        mk_notify.notify('Title', 'Text', urgent=True)
        self.assertEqual(self.calls[0][2], True)

    def test_verified_enum_values(self):
        self.assertEqual(mk_notify.LEVEL_PLAYER, 0)
        self.assertEqual(mk_notify.VISUAL_INFORMATION, 0)
        self.assertEqual(mk_notify.URGENCY_DEFAULT, 0)
        self.assertEqual(mk_notify.URGENCY_URGENT, 1)

    def test_falls_back_to_a_simpler_common_notify_signature(self):
        calls = []

        def simple_notify(title, text, urgent=False):
            calls.append((title, text, urgent))
        sys.modules['novulon.common'].notify = simple_notify
        result = mk_notify.notify('T', 'X', urgent=True)
        self.assertEqual(calls, [('T', 'X', True)])
        self.assertIsNone(result)   # simple_notify has no return value - notify() must not raise over that

    def test_missing_common_module_returns_false_not_raise(self):
        _make_unimportable(self, 'novulon.common')
        self.assertFalse(mk_notify.notify('T', 'X'))


# ============================================================================================ render.py
class RenderTests(unittest.TestCase, GameFakesMixin):
    def setUp(self):
        self.install_fakes()
        mk_stack.set_command_checker(lambda action_id: True)
        self.addCleanup(mk_stack.set_command_checker, None)
        self.conn = object()
        mk_stack.reset(self.conn)
        self.addCleanup(mk_stack.reset, self.conn)
        notified = []
        common = types.ModuleType('novulon.common')
        common.notify = lambda *a, **k: notified.append((a, k))
        self.notified = notified
        _install_fake_module(self, 'novulon.common', common)

    def test_show_page_builds_rows_in_order_with_the_right_fields(self):
        page = Page('Root', [Row('a', 'A', description='desc a'), Row('b', 'B', disabled_text='nope')])
        mk_render.show_page(self.conn, page)
        built = self._captured_dialog()
        self.assertEqual([r.name for r in built.picker_rows], [_raw('A'), _raw('B')])
        self.assertEqual([r.option_id for r in built.picker_rows], [0, 1])
        self.assertEqual(built.picker_rows[0].row_description, _raw('desc a'))
        self.assertTrue(built.picker_rows[0].is_enable)
        self.assertFalse(built.picker_rows[1].is_enable)   # disabled_text -> is_enable=False
        self.assertEqual(built.picker_rows[1].row_tooltip(), _raw('nope'))   # doubles as tooltip
        self.assertEqual(mk_stack.for_connection(self.conn).current().title, 'Root')

    def test_activating_a_row_pushes_the_returned_page(self):
        def _open_child(connection, selected_ids=None):
            return Page('Child', [Row('leaf', 'Leaf')], breadcrumb=('Child',))

        root = Page('Root', [Row('go', 'Go', on_activate=_open_child)])
        mk_render.show_page(self.conn, root)

        built = self._captured_dialog()
        built.respond([0])   # tap the only row ("Go")

        nav = mk_stack.for_connection(self.conn)
        self.assertEqual(nav.depth(), 2)
        self.assertEqual(nav.current().title, 'Child')

    def test_back_row_pops_and_rerenders_the_previous_page(self):
        mk_render.show_page(self.conn, Page('Root', [Row('a', 'A')]))
        mk_render.show_page(self.conn, Page('Deeper', [Row('b', 'B')], breadcrumb=('Deeper',)))

        built = self._captured_dialog()
        # rows_for_render put Back first (option_id 0), 'b' second (option_id 1)
        self.assertEqual(built.picker_rows[0].name, _raw('Back'))
        built.respond([0])

        nav = mk_stack.for_connection(self.conn)
        self.assertEqual(nav.depth(), 1)
        self.assertEqual(nav.current().title, 'Root')

    def test_row_returning_none_does_not_push_anything(self):
        seen = []

        def _handled_it_myself(connection, selected_ids=None):
            seen.append(connection)
            return None

        mk_render.show_page(self.conn, Page('Root', [Row('a', 'A', on_activate=_handled_it_myself)]))
        built = self._captured_dialog()
        built.respond([0])
        self.assertEqual(seen, [self.conn])
        self.assertEqual(mk_stack.for_connection(self.conn).depth(), 1)

    def test_closing_with_nothing_picked_changes_nothing(self):
        mk_render.show_page(self.conn, Page('Root', [Row('a', 'A')]))
        built = self._captured_dialog()
        built.respond([])   # closed / cancelled
        self.assertEqual(mk_stack.for_connection(self.conn).depth(), 1)

    def test_row_exception_notifies_instead_of_raising(self):
        def _boom(connection, selected_ids=None):
            raise RuntimeError('boom')

        mk_render.show_page(self.conn, Page('Root', [Row('a', 'A', on_activate=_boom)]))
        built = self._captured_dialog()
        built.respond([0])   # must not raise
        self.assertEqual(len(self.notified), 1)

    def test_returned_page_with_unregistered_row_notifies_instead_of_raising(self):
        # Regression test: `on_activate` succeeding and returning a Page is not itself wrapped by the
        # try/except right above it in render.py's _dispatch - only pushing that Page (validate_page,
        # which raises ValueError for a row with no matching commands.add()) was left unguarded. This
        # is the exact shape of the real bug the integrator found and fixed in sims/actions.py (a page
        # shipping a row nobody registered) - here it must degrade to a toast, never raise out of the
        # dialog's own on_response callback (the raw game-facing entry point).
        def _open_broken_child(connection, selected_ids=None):
            return Page('Child', [Row('unregistered-leaf', 'Leaf')], breadcrumb=('Child',))

        mk_stack.set_command_checker(lambda action_id: action_id != 'unregistered-leaf')
        root = Page('Root', [Row('go', 'Go', on_activate=_open_broken_child)])
        mk_render.show_page(self.conn, root)

        built = self._captured_dialog()
        built.respond([0])   # must not raise

        self.assertEqual(len(self.notified), 1)
        nav = mk_stack.for_connection(self.conn)
        self.assertEqual(nav.depth(), 1)              # the broken Child page was never actually pushed
        self.assertEqual(nav.current().title, 'Root')

    def test_search_row_is_pinned_first_when_page_declares_search(self):
        mk_render.show_page(self.conn, Page('Root', [Row('a', 'A')], search=True))
        built = self._captured_dialog()
        self.assertEqual(built.picker_rows[0].name, _raw('Search…'))

    def test_multi_select_page_never_gets_a_back_row_even_when_deep(self):
        mk_render.show_page(self.conn, Page('Root', [Row('a', 'A')]))
        mk_render.show_page(self.conn, Page('Pick', [Row('s1', 'S1'), Row('s2', 'S2')],
                                             multi_select=True, breadcrumb=('Pick',)))
        built = self._captured_dialog()
        self.assertNotIn(_raw('Back'), [r.name for r in built.picker_rows])

    def test_multi_select_folds_delta_into_tray_and_calls_on_select(self):
        received = []

        def _on_select(connection, tray_ids):
            received.append(sorted(tray_ids))
            return None

        page = Page('Pick', [Row('s1', 'S1'), Row('s2', 'S2'), Row('s3', 'S3')],
                     multi_select=True, on_select=_on_select)
        mk_render.show_page(self.conn, page)
        built = self._captured_dialog()
        built.respond([0, 2])   # check s1 and s3

        self.assertEqual(received, [['s1', 's3']])
        self.assertEqual(mk_stack.for_connection(self.conn).tray, {'s1', 's3'})

    def test_multi_select_tray_persists_across_a_second_page_with_different_rows(self):
        page1 = Page('Pick p1', [Row('s1', 'S1'), Row('s2', 'S2')], multi_select=True)
        mk_render.show_page(self.conn, page1)
        self._captured_dialog().respond([0])   # check s1
        self.assertEqual(mk_stack.for_connection(self.conn).tray, {'s1'})

        page2 = Page('Pick p2', [Row('s3', 'S3'), Row('s4', 'S4')], multi_select=True)
        mk_render.show_page(self.conn, page2, push=False)
        self._captured_dialog().respond([1])   # check s4 on this different page
        # s1 (from the previous page's rows) must survive - it was never shown/unchecked on page2
        self.assertEqual(mk_stack.for_connection(self.conn).tray, {'s1', 's4'})

    def test_unregistered_row_id_refuses_to_build_the_page(self):
        mk_stack.set_command_checker(lambda action_id: False)
        with self.assertRaises(ValueError):
            mk_render.show_page(self.conn, Page('Root', [Row('nope', 'Nope')]))

    def test_missing_ui_module_notifies_instead_of_raising(self):
        del sys.modules['ui.ui_dialog_picker']
        mk_render.show_page(self.conn, Page('Root', [Row('a', 'A')]))   # must not raise
        self.assertEqual(len(self.notified), 1)

    def _captured_dialog(self):
        """The most recently constructed FakeUiObjectPicker - render.py builds one fresh dialog object
        per _render() call and this reaches into it the same way a real test double would: through the
        (test-only) instance list every FakeUiObjectPicker construction appends itself to."""
        return _ALL_BUILT[-1]


# FakeUiObjectPicker records every instance built so tests can reach into "the dialog that was just
# shown" without render.py needing to expose one (it deliberately keeps no module-level handle).
_ALL_BUILT = []
_orig_init = FakeUiObjectPicker.__init__


def _tracking_init(self, *a, **k):
    _orig_init(self, *a, **k)
    _ALL_BUILT.append(self)


FakeUiObjectPicker.__init__ = _tracking_init


# ============================================================================================ confirm.py
class ConfirmDeleteTests(unittest.TestCase, GameFakesMixin):
    def setUp(self):
        self.install_fakes()
        notified = []
        common = types.ModuleType('novulon.common')
        common.notify = lambda *a, **k: notified.append((a, k))
        self.notified = notified
        _install_fake_module(self, 'novulon.common', common)

    def test_shows_a_dialog_listing_the_real_names(self):
        sims = [FakeSimInfo(1, 'Bob', 'Pancakes'), FakeSimInfo(2, 'Maria', 'Bjergsen')]
        confirmed = []
        ok = mk_confirm.confirm_delete(connection='conn', sim_infos=sims,
                                        on_confirm=lambda c: confirmed.append(c))
        self.assertTrue(ok)
        dlg = _LAST_OK_CANCEL[-1]
        # text is the bulleted list built from get_bulleted_list, with both names as get_raw_text tokens
        kind, header, tokens = dlg.text()
        self.assertEqual(kind, 'BULLETED')
        self.assertIsNone(header)
        self.assertEqual(tokens, (_raw('Bob Pancakes'), _raw('Maria Bjergsen')))

    def test_confirming_calls_on_confirm(self):
        sims = [FakeSimInfo(1, 'Bob', 'Pancakes')]
        confirmed = []
        mk_confirm.confirm_delete(connection='conn', sim_infos=sims,
                                   on_confirm=lambda c: confirmed.append(c))
        dlg = _LAST_OK_CANCEL[-1]
        dlg.respond(FakeButtonType.DIALOG_RESPONSE_OK)
        self.assertEqual(confirmed, ['conn'])

    def test_cancelling_does_not_call_on_confirm(self):
        sims = [FakeSimInfo(1, 'Bob', 'Pancakes')]
        confirmed = []
        mk_confirm.confirm_delete(connection='conn', sim_infos=sims,
                                   on_confirm=lambda c: confirmed.append(c))
        dlg = _LAST_OK_CANCEL[-1]
        dlg.respond(FakeButtonType.DIALOG_RESPONSE_CANCEL)
        self.assertEqual(confirmed, [])

    def test_protected_note_appears_in_subtitle_not_the_bulleted_list(self):
        sims = [FakeSimInfo(1, 'Bob', 'Pancakes')]
        protected = [FakeSimInfo(2, 'Alex', 'Doe')]
        mk_confirm.confirm_delete(connection='conn', sim_infos=sims, protected_note=protected)
        dlg = _LAST_OK_CANCEL[-1]
        kind, header, tokens = dlg.text()
        self.assertNotIn('Alex Doe', str(tokens))   # protected name is not in the deletable bullet list
        subtitle = dlg.subtitle()
        self.assertEqual(subtitle[0], 'RAW')
        self.assertIn('Alex Doe', subtitle[1])
        self.assertIn("can't be undone", subtitle[1])

    def test_all_protected_shows_nothing_was_deleted_and_no_dialog(self):
        protected = [FakeSimInfo(1, 'Alex', 'Doe')]
        ok = mk_confirm.confirm_delete(connection='conn', sim_infos=[], protected_note=protected)
        self.assertFalse(ok)
        self.assertEqual(len(self.notified), 1)

    def test_missing_ui_dialog_module_degrades_safely(self):
        del sys.modules['ui.ui_dialog']
        ok = mk_confirm.confirm_delete(connection='conn', sim_infos=[FakeSimInfo(1, 'A', 'B')])
        self.assertFalse(ok)
        self.assertEqual(len(self.notified), 1)

    def test_comma_list_helper_uses_get_comma_separated_list_for_two_or_more(self):
        result = mk_confirm.comma_list(['Alex Doe', 'Sam Lee'])
        self.assertEqual(result, ('COMMA', (_raw('Alex Doe'), _raw('Sam Lee'))))

    def test_comma_list_helper_skips_the_join_for_a_single_name(self):
        self.assertEqual(mk_confirm.comma_list(['Alex Doe']), _raw('Alex Doe'))

    def test_comma_list_helper_empty(self):
        self.assertIsNone(mk_confirm.comma_list([]))


_LAST_OK_CANCEL = []
_orig_okcancel_init = FakeUiDialogOkCancel.__init__


def _tracking_okcancel_init(self, *a, **k):
    _orig_okcancel_init(self, *a, **k)
    _LAST_OK_CANCEL.append(self)


FakeUiDialogOkCancel.__init__ = _tracking_okcancel_init


# ============================================================================================ search.py (game half)
class OpenSearchBoxTests(unittest.TestCase, GameFakesMixin):
    def setUp(self):
        self.install_fakes()
        common = types.ModuleType('novulon.common')
        common.log = lambda msg: None
        _install_fake_module(self, 'novulon.common', common)

    def test_typed_query_comes_back_through_on_result(self):
        results = []
        mk_search.open_search_box('conn', None, results.append)
        dlg = _LAST_TEXT_INPUT[-1]
        dlg.respond('Bob')
        self.assertEqual(results, ['Bob'])

    def test_empty_response_comes_back_as_none(self):
        results = []
        mk_search.open_search_box('conn', None, results.append)
        _LAST_TEXT_INPUT[-1].respond('')
        self.assertEqual(results, [None])

    def test_missing_dialog_class_degrades_to_none_not_raise(self):
        del sys.modules['ui.ui_dialog_generic']
        results = []
        ok = mk_search.open_search_box('conn', None, results.append)
        self.assertFalse(ok)
        self.assertEqual(results, [None])

    def test_on_result_raising_is_not_retried_or_reraised(self):
        # Regression test: `on_result` used to be called from inside `_on_response`'s except clause too
        # (as a "recovery"), so an `on_result` that itself raised (e.g. because it calls
        # menukit.show_page and that raises ValueError for an unregistered row) was silently invoked a
        # SECOND time with a different argument, and that second call was completely unguarded - an
        # exception from it would reach the game's own dialog dispatch directly.
        calls = []

        def _boom(query):
            calls.append(query)
            raise RuntimeError('boom')

        ok = mk_search.open_search_box('conn', None, _boom)
        self.assertTrue(ok)
        _LAST_TEXT_INPUT[-1].respond('Bob')   # must not raise
        self.assertEqual(calls, ['Bob'])       # called exactly once, never retried with None


_LAST_TEXT_INPUT = []
_orig_textinput_init = FakeUiDialogTextInputOkCancel.__init__


def _tracking_textinput_init(self, *a, **k):
    _orig_textinput_init(self, *a, **k)
    _LAST_TEXT_INPUT.append(self)


FakeUiDialogTextInputOkCancel.__init__ = _tracking_textinput_init


# ============================================================================================ public API surface
class PublicApiTests(unittest.TestCase):
    def test_top_level_names(self):
        for name in ('Row', 'Page', 'BACK_ID', 'SEARCH_ID', 'paging', 'search', 'stack',
                     'show_page', 'refresh', 'go_back', 'confirm_delete', 'notify'):
            self.assertTrue(hasattr(mk, name), name)

    def test_notify_and_confirm_delete_are_callables_not_modules(self):
        self.assertTrue(callable(mk.notify))
        self.assertTrue(callable(mk.confirm_delete))

    def test_paging_search_stack_are_modules(self):
        self.assertIsInstance(mk.paging, types.ModuleType)
        self.assertIsInstance(mk.search, types.ModuleType)
        self.assertIsInstance(mk.stack, types.ModuleType)


if __name__ == '__main__':
    unittest.main(verbosity=2)
