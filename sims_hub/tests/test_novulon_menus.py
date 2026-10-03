"""Novulon's menus, played through the stand-in game (tests/novulon_game.py): the entries, the main menu's tiles and
icons, Back, text boxes, the Sim picker, and the age rules. No game needed.

    python -m unittest tests.test_novulon_menus
"""
import os
import sys
import traceback
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from tests import novulon_game as G          # noqa: E402


class MenuTest(unittest.TestCase):
    def setUp(self):
        self.game = G.install()
        g = self.game
        self.home = g.add_household('Doe')
        self.alex = g.add_sim('Alex', 'Doe', age=32, gender='FEMALE', household=self.home, npc=False, here=True, active=True)
        self.sam = g.add_sim('Sam', 'Doe', age=8, gender='MALE', household=self.home, npc=False, here=True)
        self.bella = g.add_sim('Bella', 'Goth', age=32, gender='FEMALE', household=g.add_household('Goth'))
        self.mortimer = g.add_sim('Mortimer', 'Goth', age=64, gender='MALE', household=self.bella.household)
        self.cat = g.add_sim('Kitty', '', age=32, species=3, household=self.home)
        import novulon as nv                   # the package under test
        self.nv = nv
        from novulon import entry, ui, icons
        self.entry, self.ui, self.icons = entry, ui, icons
        entry._registered = False
        entry.register_commands()
        ui.reset_all()
        self.errors = []                            # anything Novulon caught and logged fails the test
        common = sys.modules['novulon.common']
        self.addCleanup(setattr, common, 'log_exception', common.log_exception)
        common.log_exception = lambda where: self.errors.append((where, traceback.format_exc()))

    def tearDown(self):
        errors, self.errors = self.errors, []
        G.uninstall()
        self.assertEqual(errors, [])
        for n in [n for n in sys.modules if n == 'novulon' or n.startswith('novulon.')]:
            del sys.modules[n]

    # ---------------------------------------------------------------- opening
    def open_main(self):
        self.game.commands['novulon.menu'](_connection=7)
        return self.game.screen

    def test_main_menu_is_tiles_with_an_icon_on_every_tile(self):
        d = self.open_main()
        self.assertEqual(d.kind, 'UiObjectPicker')
        self.assertEqual(d.kw['picker_type'], 12)                       # big tiles
        self.assertEqual(d.labels()[:6], ['My Sim', 'Sims', 'Household', 'Cheats', 'World', 'Settings'])
        for r in d.rows:
            self.assertIsNotNone(r.icon, r.label)
            self.assertEqual((r.icon.type, r.icon.group), (self.icons.ICON_TYPE, self.icons.ICON_GROUP))
        self.assertEqual(d.kw['icon']().icon_resource, self.icons.key('logo'))
        self.assertNotIn('Adult', d.labels())                            # off until turned on

    def test_sim_entry_opens_that_sims_page_with_their_portrait(self):
        self.game.commands['novulon.sim'](self.bella.id, _connection=7)
        d = self.game.screen
        self.assertEqual(d.title, 'Bella Goth')
        self.assertIs(d.kw['icon']().obj_instance, self.bella)
        self.assertNotIn('Back', d.labels())

    def test_back_returns_to_the_page_before(self):
        self.open_main().pick('Settings')
        self.assertEqual(self.game.screen.title, 'Settings')
        self.assertEqual(self.game.screen.labels()[0], 'Back')
        self.game.screen.pick('Back')
        self.assertEqual(self.game.screen.title, 'Novulon')

    # ---------------------------------------------------------------- the Sims browser
    def test_sims_groups_count_humans_only_and_open_the_portrait_picker(self):
        self.open_main().pick('Sims')
        d = self.game.screen
        self.assertEqual(d.row('Everyone').desc, '4 Sims')
        self.assertEqual(d.row('Women').desc, '2 Sims')                  # the cat is not a woman
        self.assertEqual(d.row('Pets').desc, '1 Sim')
        d.pick('Men')
        p = self.game.screen
        self.assertEqual(p.kind, 'UiSimPicker')
        self.assertEqual(sorted(r.label for r in p.rows), ['Mortimer Goth', 'Sam Doe'])
        p.pick('Mortimer Goth')
        self.assertEqual(self.game.screen.title, 'Mortimer Goth')

    def test_cancel_in_the_picker_comes_back_to_the_page(self):
        self.open_main().pick('Sims')
        self.game.screen.pick('Women')
        self.game.screen.cancel()
        self.assertEqual(self.game.screen.title, 'Sims')

    def test_find_by_name_uses_a_real_text_box(self):
        self.open_main().pick('Sims')
        self.game.screen.pick('Find by name')
        box = self.game.screen
        self.assertEqual(box.kind, 'UiDialogTextInputOkCancel')
        inputs = box.kw['text_inputs']
        self.assertTrue(hasattr(inputs, 'items') and hasattr(inputs, 'text'))   # dict-like and by attribute
        self.assertEqual(inputs.text.sort_order, 0)
        self.assertTrue(box.kw.get('include_cancel_response'))
        box.ok('goth')
        p = self.game.screen
        self.assertEqual(p.kind, 'UiSimPicker')
        self.assertEqual(sorted(r.label for r in p.rows), ['Bella Goth', 'Mortimer Goth'])

    # ---------------------------------------------------------------- age rules
    def test_romance_and_pregnancy_never_show_for_a_child(self):
        self.game.commands['novulon.sim'](self.sam.id, _connection=7)
        d = self.game.screen
        self.assertNotIn('Pregnancy', d.labels())
        d.pick('Relationship with Alex')
        self.assertNotIn('Fall in love', self.game.screen.labels())

    def test_pregnancy_partners_are_adults_only(self):
        self.game.commands['novulon.sim'](self.alex.id, _connection=7)
        self.game.screen.pick('Pregnancy')
        self.game.screen.pick('Get pregnant with')
        p = self.game.screen
        self.assertEqual(p.kind, 'UiSimPicker')
        names = [r.label for r in p.rows]
        self.assertNotIn('Sam Doe', names)
        self.assertNotIn('Kitty', names)

    def test_adult_tile_needs_the_setting_wickedwhims_and_an_adult_at_the_computer(self):
        from novulon import settings, compat
        settings.set('adult_enabled', True)
        compat.wickedwhims_present = lambda: True
        self.assertIn('Adult', self.open_main().labels())
        self.game.active = self.sam
        self.assertNotIn('Adult', self.open_main().labels())

    def test_adult_page_stays_off_while_child_content_mods_are_installed(self):
        import shutil
        import tempfile
        from novulon import common, compat, settings
        sims = tempfile.mkdtemp(prefix='novulon_test_')
        self.addCleanup(shutil.rmtree, sims, True)
        self.addCleanup(common.configure, None)
        os.makedirs(os.path.join(sims, 'Mods', 'Some_Folder'))
        open(os.path.join(sims, 'Mods', 'Some_Folder', 'AllTheFallen_Children_Scripts.ts4script'), 'w').close()
        common.configure(sims)
        compat._child_content = None
        compat.wickedwhims_present = lambda: True
        settings.set('adult_enabled', True)
        self.assertNotIn('Adult', self.open_main().labels())
        self.game.screen.pick('Settings')
        row = self.game.screen.row('Adult tile')
        self.assertFalse(row.enabled)
        self.assertEqual(G.text_of(row.kw['row_tooltip']), compat.BLOCKED_NOTE)
        from novulon.menus import adult
        self.assertFalse(adult.allowed())
        os.remove(os.path.join(sims, 'Mods', 'Some_Folder', 'AllTheFallen_Children_Scripts.ts4script'))
        compat._child_content = None                                    # a new game session after removing them
        self.assertIn('Adult', self.open_main().labels())


class EntryTest(unittest.TestCase):
    def setUp(self):
        self.game = G.install()

    def tearDown(self):
        G.uninstall()
        for n in [n for n in sys.modules if n == 'novulon' or n.startswith('novulon.')]:
            del sys.modules[n]

    def test_entries_go_on_computers_tablets_and_sims_once(self):
        from novulon import entry
        g = self.game
        menu_aff, sim_aff = object(), object()
        g.manager(g.Types.INTERACTION).by_id.update({entry.MENU_INTERACTION_ID: menu_aff, entry.SIM_INTERACTION_ID: sim_aff})

        def tuning(name, base=object, params=None):
            ov = type('Ov', (), {'params': params}) if params is not None else None
            return type(name, (base,), {'_super_affordances': (), '_anim_overrides_cls': ov})
        pc = tuning('Computer', params={'computerType': 1})
        tablet = tuning('Tablet', params={'carryObject': 'tablet'})
        sim = tuning('object_sim', base=g.Sim)
        chair = tuning('Chair', params={})
        g.manager(g.Types.OBJECT).classes += [pc, tablet, sim, chair]
        self.assertEqual(entry.add_entries(), (2, 1))
        self.assertEqual(pc._super_affordances, (menu_aff,))
        self.assertEqual(tablet._super_affordances, (menu_aff,))
        self.assertEqual(sim._super_affordances, (sim_aff,))
        self.assertEqual(chair._super_affordances, ())
        self.assertEqual(entry.add_entries(), (0, 0))                   # a second lot load adds nothing

    def test_interaction_ids_match_the_package(self):
        from novulon import entry
        from tools import novulon_ids as ids
        self.assertEqual(entry.MENU_INTERACTION_ID, ids.INTERACTION_OPEN_MENU)
        self.assertEqual(entry.SIM_INTERACTION_ID, ids.INTERACTION_SIM_MENU)

    def test_icon_ids_match_the_package(self):
        from novulon import icons
        from tools.novulon_ids.bp13_package_build import icon_instance
        from tools.novulon_glyphs import NAMES
        for n in NAMES:
            self.assertEqual(icons.instance(n), icon_instance(n), n)


if __name__ == '__main__':
    unittest.main()
