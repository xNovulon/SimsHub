"""Tier-4-style tests for ingame/novulon/sims/{__init__,browser}.py: the category chooser, the
Advanced filter picker, the Browse Controls screen, the raw Sim-list dialog, and the Sim Card -
driven with fake `services`/`sims.sim_info_types`/`sims.occult.occult_enums`/`ui.ui_dialog_picker`/
`sims4.localization` modules (the same style `tests/test_novulon_inject.py`'s own `FakeGameEnv`
already uses for a different package), plus the REAL menukit (BP2, already built) for
`Row`/`Page`/`stack`/`paging`/`search`. No dialog is ever really shown; a `FakeUiSimPicker` records
what would have been sent and lets a test hand back a fake response, the same round trip
`test_novulon_menukit.py` already exercises for the generic `Page`/`Row` path.
"""
import os
import shutil
import sys
import tempfile
import types
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon import commands, common  # noqa: E402
from novulon.menukit import stack as menukit_stack  # noqa: E402
from novulon.menukit.page import Page  # noqa: E402
from novulon.sims import browser  # noqa: E402


# ------------------------------------------------------------------ fake game enums (real, verified
# values - tools/novulon_api_manifest/bp4_sims_browser.py - copied here as plain ints)
class FakeGender(object):
    MALE = 4096
    FEMALE = 8192


class FakeAge(object):
    BABY, TODDLER, CHILD, TEEN, YOUNGADULT, ADULT, ELDER, INFANT = 1, 2, 4, 8, 16, 32, 64, 128


class FakeSpecies(object):
    INVALID, HUMAN, DOG, CAT = 0, 1, 2, 3
    FOX, HORSE = 5, 6


class FakeOccultType(object):
    HUMAN, ALIEN, VAMPIRE, MERMAID, WITCH, WEREWOLF, FAIRY = 1, 2, 4, 8, 16, 32, 64


class FakeL(object):
    """Stand-in for sims4.localization.LocalizationHelperTuning - identity get_raw_text, good enough
    to assert on the plain strings browser.py builds."""
    @classmethod
    def get_raw_text(cls, text):
        return text


class FakeSimInfo(object):
    _next_id = [1000]

    def __init__(self, first_name='Test', last_name='Sim', gender=FakeGender.FEMALE,
                 age=FakeAge.YOUNGADULT, species=FakeSpecies.HUMAN, occult_types=FakeOccultType.HUMAN,
                 household=None, instanced=False, pregnant=False, id=None):
        if id is None:
            id = FakeSimInfo._next_id[0]
            FakeSimInfo._next_id[0] += 1
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        self.gender = gender
        self.age = age
        self.species = species
        self.occult_types = occult_types
        self.household = household
        self.household_id = household.id if household is not None else None
        self._instanced = instanced
        self._pregnant = pregnant

    @property
    def full_name(self):
        return ('%s %s' % (self.first_name, self.last_name)).strip()

    def is_instanced(self):
        return self._instanced

    def is_pregnant(self):
        return self._pregnant


class FakeHousehold(object):
    def __init__(self, id, name='Fake Household'):
        self.id = id
        self.name = name


class FakeSimInfoManager(object):
    def __init__(self, sim_infos):
        self._by_id = dict((s.id, s) for s in sim_infos)

    def values(self):
        return list(self._by_id.values())

    def get(self, sim_id):
        return self._by_id.get(sim_id)


class FakeHouseholdManager(object):
    def __init__(self, households):
        self._by_id = dict((h.id, h) for h in households)

    def values(self):
        return list(self._by_id.values())

    def get(self, household_id):
        return self._by_id.get(household_id)


class FakeSimPickerRow(object):
    def __init__(self, sim_id, select_default, sim_location, household_id, **kwargs):
        self.sim_id = sim_id
        self.select_default = select_default
        self.sim_location = sim_location
        self.household_id = household_id
        self.name = kwargs.get('name')
        self.row_description = kwargs.get('row_description')
        self.is_selected = kwargs.get('is_selected', False)
        self.option_id = None


class _Factory(object):
    def __init__(self, cls):
        self._cls = cls

    def default(self, owner, **kwargs):
        return self._cls(**kwargs)


class FakeUiSimPicker(object):
    """Records every constructor kwarg and every added row; `show_dialog` just stashes the callback -
    a test calls `.fire(picked_rows)` to simulate the player's response, exactly the round trip a real
    `UiSimPicker` would drive through `_dispatch_sim_list`/`_dispatch_sim_card`."""
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.picker_rows = []
        self._on_response = None
        FakeUiSimPicker.instances.append(self)

    def add_row(self, row):
        if row.option_id is None:
            row.option_id = len(self.picker_rows)
        self.picker_rows.append(row)

    def show_dialog(self, on_response=None):
        self._on_response = on_response

    def fire(self, picked_rows):
        """Simulate the player responding with exactly `picked_rows` checked/picked."""
        self._on_response(_FakeDialogResult(picked_rows))

    def fire_closed(self):
        """Simulate the player closing the dialog with nothing picked (get_result_rows raises, the
        same as the real engine's behavior on a cancelled dialog - render.py's own docstring)."""
        self._on_response(_FakeDialogResultClosed())

    @classmethod
    def TunableFactory(cls):
        return _Factory(cls)


class _FakeDialogResult(object):
    def __init__(self, picked_rows):
        self._picked = picked_rows

    def get_result_rows(self):
        return self._picked


class _FakeDialogResultClosed(object):
    def get_result_rows(self):
        raise RuntimeError('dialog was closed with nothing picked')


class FakeGameEnv(object):
    def __init__(self, sim_infos=(), households=(), active_household_id=None):
        self.sim_info_manager = FakeSimInfoManager(sim_infos)
        self.household_manager = FakeHouseholdManager(households)
        self._active_household_id = active_household_id

    def __enter__(self):
        fake_services = types.ModuleType('services')
        fake_services.sim_info_manager = lambda: self.sim_info_manager
        fake_services.household_manager = lambda: self.household_manager
        fake_services.active_household_id = lambda: self._active_household_id

        fake_sims = types.ModuleType('sims')
        fake_sim_info_types = types.ModuleType('sims.sim_info_types')
        fake_sim_info_types.Gender = FakeGender
        fake_sim_info_types.Age = FakeAge
        fake_sim_info_types.Species = FakeSpecies
        fake_sims.sim_info_types = fake_sim_info_types
        fake_occult_pkg = types.ModuleType('sims.occult')
        fake_occult_enums = types.ModuleType('sims.occult.occult_enums')
        fake_occult_enums.OccultType = FakeOccultType
        fake_occult_pkg.occult_enums = fake_occult_enums
        fake_sims.occult = fake_occult_pkg

        fake_sims4 = types.ModuleType('sims4')
        fake_localization = types.ModuleType('sims4.localization')
        fake_localization.LocalizationHelperTuning = FakeL
        fake_sims4.localization = fake_localization

        fake_ui = types.ModuleType('ui')
        fake_ui_dialog_picker = types.ModuleType('ui.ui_dialog_picker')
        fake_ui_dialog_picker.UiSimPicker = FakeUiSimPicker
        fake_ui_dialog_picker.SimPickerRow = FakeSimPickerRow
        fake_ui.ui_dialog_picker = fake_ui_dialog_picker

        self._saved = {}
        for name, mod in (
                ('services', fake_services), ('sims', fake_sims),
                ('sims.sim_info_types', fake_sim_info_types), ('sims.occult', fake_occult_pkg),
                ('sims.occult.occult_enums', fake_occult_enums), ('sims4', fake_sims4),
                ('sims4.localization', fake_localization), ('ui', fake_ui),
                ('ui.ui_dialog_picker', fake_ui_dialog_picker)):
            self._saved[name] = sys.modules.get(name)
            sys.modules[name] = mod
        FakeUiSimPicker.instances = []
        return self

    def __exit__(self, *exc):
        for name, mod in self._saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod


CONN = 'CONN-1'


class BrowserTestCase(unittest.TestCase):
    """Every test gets its own settings dir and a clean menukit NavStack/command-registry slice, the
    same isolation pattern test_novulon_commands.py already uses."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)
        browser._enum_cache.clear()
        menukit_stack.reset_all()
        self._actions_snapshot = dict(commands._actions)
        self._sections_snapshot = dict(commands._sections)

    def tearDown(self):
        commands._actions.clear()
        commands._actions.update(self._actions_snapshot)
        commands._sections.clear()
        commands._sections.update(self._sections_snapshot)
        menukit_stack.reset_all()
        browser._enum_cache.clear()
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestRegistration(BrowserTestCase):
    def test_every_row_id_ever_built_is_registered(self):
        """The one check that would have caught a real bug before it ever reached menukit's own
        raise-on-push guard: every action id this package's rows can carry must already be
        registered (SPEC.md Sec 4's own contract)."""
        household = FakeHousehold(1, 'Willow Creek')
        sims = [FakeSimInfo(first_name='Bob', last_name='Pancakes', household=household)]
        with FakeGameEnv(sim_infos=sims, households=[household], active_household_id=1):
            nav = menukit_stack.for_connection(CONN)
            for page in (browser.open_root(CONN), browser.open_advanced_filters(CONN),
                          browser.open_household_picker(CONN), browser._build_controls_page(CONN)):
                for row in page.rows:
                    self.assertTrue(commands.is_registered(row.id),
                                     'row %r has no registered command' % (row.id,))
            nav.tray = {sims[0].id}
            for row in browser._build_controls_page(CONN).rows:
                self.assertTrue(commands.is_registered(row.id))


class TestOpenRoot(BrowserTestCase):
    def test_category_rows_and_counts(self):
        males = FakeSimInfo(gender=FakeGender.MALE, species=FakeSpecies.HUMAN)
        females = FakeSimInfo(gender=FakeGender.FEMALE, species=FakeSpecies.HUMAN)
        pet = FakeSimInfo(gender=FakeGender.FEMALE, species=FakeSpecies.DOG)
        with FakeGameEnv(sim_infos=[males, females, pet]):
            page = browser.open_root(CONN)
        ids = [r.id for r in page.rows]
        self.assertEqual(ids, ['novulon.sims.category.males', 'novulon.sims.category.females',
                                 'novulon.sims.category.pets', 'novulon.sims.category.all',
                                 'novulon.sims.category.advanced'])
        by_id = dict((r.id, r) for r in page.rows)
        self.assertEqual(by_id['novulon.sims.category.males'].description, '1 Sims')
        # the pet is ALSO gender FEMALE (pets have a gender bit too, SPEC.md Sec 5.1 puts no species
        # restriction on the Females tab) - so Females counts it too, same as the real Gender.FEMALE
        # bit test in query.counts() would.
        self.assertEqual(by_id['novulon.sims.category.females'].description, '2 Sims')
        self.assertEqual(by_id['novulon.sims.category.pets'].description, '1 Sims')
        self.assertEqual(by_id['novulon.sims.category.all'].description, '3 Sims')

    def test_degrades_to_zero_counts_with_no_game(self):
        page = browser.open_root(CONN)   # no FakeGameEnv at all - must not raise
        self.assertIsInstance(page, Page)


class TestCategorySelection(BrowserTestCase):
    def test_open_males_sets_filters_and_resets_tray(self):
        with FakeGameEnv(sim_infos=[]):
            nav = menukit_stack.for_connection(CONN)
            nav.tray = {999}
            page = browser._open_males(CONN)
        self.assertEqual(nav.state['category_label'], 'Males')
        self.assertEqual(nav.state['filters'], {'gender': FakeGender.MALE})
        self.assertEqual(nav.tray, set())
        self.assertIsInstance(page, Page)

    def test_open_pets_sets_species_ne(self):
        with FakeGameEnv(sim_infos=[]):
            browser._open_pets(CONN)
        nav = menukit_stack.for_connection(CONN)
        self.assertEqual(nav.state['filters'], {'species_ne': FakeSpecies.HUMAN})

    def test_open_all_has_no_filters(self):
        with FakeGameEnv(sim_infos=[]):
            browser._open_all(CONN)
        nav = menukit_stack.for_connection(CONN)
        self.assertEqual(nav.state['filters'], {})


class TestAdvancedFilters(BrowserTestCase):
    def test_toggle_life_stage_round_trip(self):
        with FakeGameEnv(sim_infos=[]):
            browser._open_advanced_fresh(CONN)
            nav = menukit_stack.for_connection(CONN)
            page = browser.open_advanced_filters(CONN)
            row = next(r for r in page.rows if r.id == 'novulon.sims.advanced.life.ELDER')
            self.assertTrue(row.label.startswith('[ ] '))
            row.on_activate(CONN)   # check it
            self.assertEqual(nav.state['filters']['life_stages'], {FakeAge.ELDER})
            page2 = browser.open_advanced_filters(CONN)
            row2 = next(r for r in page2.rows if r.id == 'novulon.sims.advanced.life.ELDER')
            self.assertTrue(row2.label.startswith('[x] '))
            row2.on_activate(CONN)   # uncheck it
            self.assertEqual(nav.state['filters']['life_stages'], set())

    def test_show_results_only_appears_once_something_is_checked(self):
        with FakeGameEnv(sim_infos=[]):
            browser._open_advanced_fresh(CONN)
            page = browser.open_advanced_filters(CONN)
            self.assertNotIn('novulon.sims.advanced.show_results', [r.id for r in page.rows])
            occult_row = next(r for r in page.rows if r.id == 'novulon.sims.advanced.occult.VAMPIRE')
            occult_row.on_activate(CONN)
            page2 = browser.open_advanced_filters(CONN)
            self.assertIn('novulon.sims.advanced.show_results', [r.id for r in page2.rows])

    def test_status_toggle_flips_boolean(self):
        with FakeGameEnv(sim_infos=[]):
            browser._open_advanced_fresh(CONN)
            nav = menukit_stack.for_connection(CONN)
            page = browser.open_advanced_filters(CONN)
            row = next(r for r in page.rows if r.id == 'novulon.sims.advanced.status.here')
            row.on_activate(CONN)
            self.assertTrue(nav.state['filters']['here'])

    def test_unavailable_without_game_never_raises(self):
        page = browser.open_advanced_filters(CONN)   # no FakeGameEnv
        self.assertIsInstance(page, Page)


class TestHouseholdPicker(BrowserTestCase):
    def test_pick_and_clear(self):
        hh1 = FakeHousehold(1, 'Alpha House')
        hh2 = FakeHousehold(2, 'Beta House')
        with FakeGameEnv(households=[hh1, hh2]):
            browser._open_advanced_fresh(CONN)
            page = browser.open_household_picker(CONN)
            names = [r.label for r in page.rows]
            self.assertIn('Alpha House', names)
            self.assertIn('Beta House', names)
            row = next(r for r in page.rows if r.label == 'Beta House')
            row.on_activate(CONN)
            nav = menukit_stack.for_connection(CONN)
            self.assertEqual(nav.state['filters']['household_id'], 2)
            clear_row = next(r for r in browser.open_household_picker(CONN).rows
                              if r.id == 'novulon.sims.household.clear')
            clear_row.on_activate(CONN)
            self.assertIsNone(nav.state['filters']['household_id'])


class TestControlsPage(BrowserTestCase):
    def test_search_label_reflects_last_query(self):
        with FakeGameEnv(sim_infos=[]):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            page = browser._build_controls_page(CONN)
            search_row = next(r for r in page.rows if r.id == 'novulon.sims.controls.search')
            self.assertEqual(search_row.label, 'Search…')
            nav.state['search_query'] = 'Bob'
            page2 = browser._build_controls_page(CONN)
            search_row2 = next(r for r in page2.rows if r.id == 'novulon.sims.controls.search')
            self.assertEqual(search_row2.label, 'Search… (last: "Bob")')

    def test_paging_rows_appear_only_when_needed(self):
        many = [FakeSimInfo(first_name='S%d' % i) for i in range(150)]
        with FakeGameEnv(sim_infos=many):
            browser._open_all(CONN)
            page = browser._build_controls_page(CONN)
        ids = [r.id for r in page.rows]
        self.assertNotIn('novulon.sims.controls.prev_page', ids)
        self.assertIn('novulon.sims.controls.next_page', ids)

    def test_next_page_row_advances_page_index(self):
        many = [FakeSimInfo(first_name='S%d' % i) for i in range(150)]
        with FakeGameEnv(sim_infos=many):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            page = browser._build_controls_page(CONN)
            next_row = next(r for r in page.rows if r.id == 'novulon.sims.controls.next_page')
            next_row.on_activate(CONN)
            self.assertEqual(nav.state['page_index'], 1)

    def test_selection_rows_appear_only_once_tray_nonempty(self):
        with FakeGameEnv(sim_infos=[]):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            page = browser._build_controls_page(CONN)
            ids = [r.id for r in page.rows]
            self.assertNotIn('novulon.sims.controls.choose_action', ids)
            self.assertNotIn('novulon.sims.controls.view_card', ids)
            nav.tray = {42}
            page2 = browser._build_controls_page(CONN)
            ids2 = [r.id for r in page2.rows]
            self.assertIn('novulon.sims.controls.choose_action', ids2)
            self.assertIn('novulon.sims.controls.view_card', ids2)
            nav.tray = {42, 43}
            page3 = browser._build_controls_page(CONN)
            ids3 = [r.id for r in page3.rows]
            self.assertIn('novulon.sims.controls.choose_action', ids3)
            self.assertNotIn('novulon.sims.controls.view_card', ids3)   # only offered for exactly 1


class TestSimListDispatch(BrowserTestCase):
    def test_tray_persists_across_two_page_views(self):
        bob = FakeSimInfo(first_name='Bob', last_name='Pancakes')
        amy = FakeSimInfo(first_name='Amy', last_name='Ant')
        with FakeGameEnv(sim_infos=[bob, amy]):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            browser._open_sim_list(CONN)
            dlg = FakeUiSimPicker.instances[-1]
            self.assertEqual(len(dlg.picker_rows), 2)
            # simulate checking Bob only
            bob_row = next(r for r in dlg.picker_rows if r.sim_id == bob.id)
            dlg.fire([bob_row])
            self.assertEqual(nav.tray, {bob.id})
            # re-open the list (simulating "View & Select Sims" again) - Bob should show pre-checked
            browser._open_sim_list(CONN)
            dlg2 = FakeUiSimPicker.instances[-1]
            bob_row2 = next(r for r in dlg2.picker_rows if r.sim_id == bob.id)
            self.assertTrue(bob_row2.is_selected)
            # now also check Amy - tray should grow to both, Bob's own re-check preserved
            amy_row2 = next(r for r in dlg2.picker_rows if r.sim_id == amy.id)
            dlg2.fire([bob_row2, amy_row2])
            self.assertEqual(nav.tray, {bob.id, amy.id})

    def test_unchecking_everyone_on_one_page_is_treated_as_no_change(self):
        # verified real-engine constraint (see _dispatch_sim_list's own docstring): a response with
        # zero picked rows is indistinguishable from the dialog being closed, and menukit's own
        # render.py convention is to leave the tray untouched in that case - so the only way to fully
        # empty a tray is the explicit "Clear Selection" row, never unchecking-to-zero here.
        bob = FakeSimInfo(first_name='Bob', last_name='Pancakes')
        with FakeGameEnv(sim_infos=[bob]):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            nav.tray = {bob.id}
            browser._open_sim_list(CONN)
            dlg = FakeUiSimPicker.instances[-1]
            dlg.fire([])   # nothing checked this time
            self.assertEqual(nav.tray, {bob.id})

    def test_unchecking_one_of_several_still_removes_just_that_one(self):
        bob = FakeSimInfo(first_name='Bob', last_name='Pancakes')
        amy = FakeSimInfo(first_name='Amy', last_name='Ant')
        with FakeGameEnv(sim_infos=[bob, amy]):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            nav.tray = {bob.id, amy.id}
            browser._open_sim_list(CONN)
            dlg = FakeUiSimPicker.instances[-1]
            amy_row = next(r for r in dlg.picker_rows if r.sim_id == amy.id)
            dlg.fire([amy_row])   # Bob unchecked, Amy stays checked - a real delta, not an all-empty response
            self.assertEqual(nav.tray, {amy.id})

    def test_closed_dialog_leaves_tray_untouched(self):
        bob = FakeSimInfo(first_name='Bob', last_name='Pancakes')
        with FakeGameEnv(sim_infos=[bob]):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            nav.tray = {bob.id}
            browser._open_sim_list(CONN)
            dlg = FakeUiSimPicker.instances[-1]
            dlg.fire_closed()
            self.assertEqual(nav.tray, {bob.id})

    def test_dispatch_exception_notifies_instead_of_raising(self):
        # Regression test: `_on_response` is invoked directly by the game's own dialog-response
        # dispatch, so an exception from `_dispatch_sim_list`'s own trailing
        # `menukit.show_page(..., push=False)` call (NavStack.replace_top -> validate_page, which
        # raises ValueError for a row with no matching commands.add() - the same shape as the real
        # "Fill All Needs" bug the integrator already found and fixed elsewhere in this mod) must
        # never propagate out of it and into that raw callback.
        bob = FakeSimInfo(first_name='Bob', last_name='Pancakes')
        with FakeGameEnv(sim_infos=[bob]):
            browser._open_all(CONN)
            browser._open_sim_list(CONN)
            dlg = FakeUiSimPicker.instances[-1]
            bob_row = dlg.picker_rows[0]

            original = browser._build_controls_page

            def _boom(connection):
                raise RuntimeError('boom')

            browser._build_controls_page = _boom
            try:
                dlg.fire([bob_row])   # must not raise
            finally:
                browser._build_controls_page = original

    def test_row_description_includes_badges(self):
        vamp = FakeSimInfo(first_name='Vlad', last_name='Draco', age=FakeAge.ELDER,
                             occult_types=FakeOccultType.VAMPIRE)
        with FakeGameEnv(sim_infos=[vamp]):
            browser._open_all(CONN)
            browser._open_sim_list(CONN)
            dlg = FakeUiSimPicker.instances[-1]
            row = dlg.picker_rows[0]
        self.assertIn('Vampire', row.row_description)
        self.assertIn('Elder', row.row_description)


class TestSimCard(BrowserTestCase):
    def test_view_card_shown_for_single_selection(self):
        bob = FakeSimInfo(first_name='Bob', last_name='Pancakes')
        with FakeGameEnv(sim_infos=[bob]):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            nav.tray = {bob.id}
            browser._row_view_card(CONN)
            dlg = FakeUiSimPicker.instances[-1]
            self.assertEqual(dlg.kwargs['min_selectable'], 1)
            self.assertEqual(dlg.kwargs['max_selectable'], 1)
            self.assertEqual(len(dlg.picker_rows), 1)

    def test_confirming_card_hands_off_to_selection_action(self):
        seen = []
        commands.add('novulon.sims.selection_action', lambda c, *ids: seen.append(ids))
        bob = FakeSimInfo(first_name='Bob', last_name='Pancakes')
        with FakeGameEnv(sim_infos=[bob]):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            nav.tray = {bob.id}
            browser._row_view_card(CONN)
            dlg = FakeUiSimPicker.instances[-1]
            dlg.fire(dlg.picker_rows)
        self.assertEqual(seen, [(str(bob.id),)])

    def test_cancelling_card_returns_to_controls_without_crashing(self):
        bob = FakeSimInfo(first_name='Bob', last_name='Pancakes')
        with FakeGameEnv(sim_infos=[bob]):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            nav.tray = {bob.id}
            browser._row_view_card(CONN)
            dlg = FakeUiSimPicker.instances[-1]
            dlg.fire_closed()   # never raises even though nothing was picked

    def test_missing_bp5_action_degrades_to_notification_not_crash(self):
        bob = FakeSimInfo(first_name='Bob', last_name='Pancakes')
        with FakeGameEnv(sim_infos=[bob]):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            nav.tray = {bob.id}
            browser._row_view_card(CONN)
            dlg = FakeUiSimPicker.instances[-1]
            dlg.fire(dlg.picker_rows)   # 'novulon.sims.selection_action' is NOT registered - must not raise


class TestChooseAction(BrowserTestCase):
    def test_hands_off_all_tray_ids_and_clears_tray(self):
        seen = []
        commands.add('novulon.sims.selection_action', lambda c, *ids: seen.append(ids))
        with FakeGameEnv(sim_infos=[]):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            nav.tray = {5, 3, 9}
            browser._row_choose_action(CONN)
        self.assertEqual(seen, [('3', '5', '9')])
        self.assertEqual(nav.tray, set())

    def test_empty_tray_is_a_no_op(self):
        with FakeGameEnv(sim_infos=[]):
            browser._open_all(CONN)
            browser._row_choose_action(CONN)   # must not raise with an empty tray

    def test_bp5_page_result_is_pushed(self):
        sub_page = Page('Actions', [], breadcrumb=('Sims', 'Actions'))
        commands.add('novulon.sims.selection_action', lambda c, *ids: sub_page)
        with FakeGameEnv(sim_infos=[]):
            browser._open_all(CONN)
            nav = menukit_stack.for_connection(CONN)
            nav.tray = {5}
            result = browser._row_choose_action(CONN)
        self.assertIs(result, sub_page)


class TestSectionRegistration(BrowserTestCase):
    def test_sims_section_is_registered_by_init(self):
        # importing novulon.sims already ran its module-level commands.add_section() call once at
        # process start; re-affirm the contract here without re-importing (imports only run once).
        self.assertTrue(commands.is_registered('novulon.menu.sims'))
        keys = [k for k, _ in commands.sections()]
        self.assertIn('sims', keys)


if __name__ == '__main__':
    unittest.main(verbosity=1)
