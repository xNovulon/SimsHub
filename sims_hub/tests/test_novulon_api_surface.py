"""Tests for the Novulon API-manifest aggregator and Tier 3 checker (tools/novulon_api_manifest,
tools/novulon_api_check.py), plus a light self-check of tests/novulon_fakes.py.

  * Aggregator logic (_normalize/_merge/_aggregate) is pure Python - no sibling files, no game, tested
    directly with made-up sources.
  * The live aggregator (ALL_ROWS, built from whatever novulon_api_manifest/<package>.py files
    actually exist in this working tree right now) is smoke-tested: it must import without raising and
    ALL_ROWS must be a list of Row - this is the same import every real check run depends on.
  * The checker's name-descent (resolve()/GameZips) is Tier 3 proper: verified against this machine's
    real, installed game zips, skipped when they're not present. Every fact asserted here was read
    directly off this build with tools/pyc37.py before being written down (see the inline comments).
"""
import os
import sys
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

from tools import novulon_api_manifest as manifest  # noqa: E402
from tools import novulon_api_check as check_tool    # noqa: E402
from tests import novulon_fakes as fakes             # noqa: E402


# ====================================================================== aggregator, pure
class AggregateTests(unittest.TestCase):
    def test_normalize_accepts_3_and_4_tuples(self):
        row = manifest._normalize(('sims.sim_info', 'SimInfo.reset', 'method'), 'pkg_a')
        self.assertEqual((row.module, row.path, row.kind, row.expected, row.source),
                         ('sims.sim_info', 'SimInfo.reset', 'method', None, 'pkg_a'))
        row2 = manifest._normalize(('sims.sim_info_types', 'Age.ADULT', 'const', 32), 'pkg_b')
        self.assertEqual(row2.expected, 32)

    def test_normalize_rejects_bad_shapes(self):
        for bad in [('only', 'two'), ('a', 'b', 'c', 'd', 'e'), 'not-a-tuple', (1, 'b', 'c'),
                    ('a', 'b', 3), ('a', '', 'method')]:
            with self.assertRaises(ValueError):
                manifest._normalize(bad, 'pkg')

    def test_normalize_module_kind_needs_no_path(self):
        row = manifest._normalize(('some.module', None, 'module'), 'pkg')
        self.assertIsNone(row.path)

    def test_aggregate_concatenates_and_pulls_out_game_version(self):
        rows, versions = manifest._aggregate([
            ('pkg_a', [('game_version', None, '1.2.3.4'), ('m.a', 'X', 'class')], None),
            ('pkg_b', [('m.b', 'Y', 'function')], None),
        ])
        self.assertEqual(sorted((r.module, r.path) for r in rows), [('m.a', 'X'), ('m.b', 'Y')])
        self.assertEqual(versions, {'pkg_a': '1.2.3.4'})

    def test_aggregate_checked_against_attribute(self):
        _, versions = manifest._aggregate([('pkg_a', [('m.a', 'X', 'class')], '1.2.3.4')])
        self.assertEqual(versions, {'pkg_a': '1.2.3.4'})

    def test_aggregate_conflicting_version_notes_raise(self):
        with self.assertRaises(ValueError):
            manifest._aggregate([
                ('pkg_a', [('game_version', None, '1.2.3.4')], '9.9.9.9'),
            ])

    def test_aggregate_same_row_from_two_files_is_fine_when_it_agrees(self):
        rows, _ = manifest._aggregate([
            ('pkg_a', [('m.a', 'X', 'const')], None),
            ('pkg_b', [('m.a', 'X', 'const')], None),
        ])
        self.assertEqual(len(rows), 1)                      # kept once, not duplicated
        self.assertEqual(rows[0].source, 'pkg_a')            # first writer wins for the report's source

    def test_aggregate_same_row_upgrades_expected_from_whichever_file_has_it(self):
        rows, _ = manifest._aggregate([
            ('pkg_a', [('m.a', 'X', 'const')], None),
            ('pkg_b', [('m.a', 'X', 'const', 5)], None),
        ])
        self.assertEqual(rows[0].expected, 5)

    def test_aggregate_conflicting_kind_raises(self):
        with self.assertRaises(ValueError):
            manifest._aggregate([
                ('pkg_a', [('m.a', 'X', 'class')], None),
                ('pkg_b', [('m.a', 'X', 'method')], None),
            ])

    def test_aggregate_conflicting_expected_raises(self):
        with self.assertRaises(ValueError):
            manifest._aggregate([
                ('pkg_a', [('m.a', 'X', 'const', 1)], None),
                ('pkg_b', [('m.a', 'X', 'const', 2)], None),
            ])

    def test_aggregate_rejects_non_list_rows(self):
        with self.assertRaises(ValueError):
            manifest._aggregate([('pkg_a', 'not-a-list', None)])

    def test_live_package_imports_and_all_rows_is_a_list_of_row(self):
        """Whatever real novulon_api_manifest/<package>.py files exist in this working tree right now
        must already satisfy the contract - this import already ran once at test-collection time
        (that's how `manifest` got bound above); re-asserting its shape here is the regression guard."""
        self.assertIsInstance(manifest.ALL_ROWS, list)
        for row in manifest.ALL_ROWS:
            self.assertIsInstance(row, manifest.Row)
            self.assertIsInstance(row.module, str)


# ====================================================================== fakes, pure
class FakesSelfTest(unittest.TestCase):
    def test_fake_sim_info_defaults_and_full_name(self):
        s = fakes.FakeSimInfo(first_name='Bob', last_name='Pancakes')
        self.assertEqual(s.full_name, 'Bob Pancakes')
        self.assertTrue(s.is_instanced())
        self.assertFalse(s.removed)
        self.assertIsNone(s.household)
        self.assertIsNone(s.household_id)

    def test_fake_sim_info_ids_are_unique_when_not_given(self):
        a, b = fakes.FakeSimInfo(), fakes.FakeSimInfo()
        self.assertNotEqual(a.id, b.id)

    def test_fake_sim_info_household_id_follows_household(self):
        h = fakes.FakeHousehold(42, active=True)
        s = fakes.FakeSimInfo(household=h)
        self.assertEqual(s.household_id, 42)
        self.assertTrue(s.household.is_active_household())

    def test_remove_permanently_is_terminal_and_recorded(self):
        s = fakes.FakeSimInfo()
        h = fakes.FakeHousehold(1)
        s.remove_permanently(h)
        self.assertTrue(s.removed)
        self.assertEqual(s.remove_calls, [h])

    def test_reset_and_delete_service_auto_finish_flips_is_instanced(self):
        svc = fakes.FakeResetAndDeleteService()
        s = fakes.FakeSimInfo(instanced=True)
        svc.trigger_destroy(s.get_sim_instance())
        self.assertFalse(s.is_instanced())
        self.assertEqual(len(svc.calls), 1)

    def test_reset_and_delete_service_can_withhold_forever(self):
        """The bounded-timeout-and-skip path (SPEC.md Sec 5.6/Sec 16 Tier 4): a Sim that never leaves
        the instanced set must be provably exercisable, not just the happy path."""
        svc = fakes.FakeResetAndDeleteService(auto_finish=False)
        s = fakes.FakeSimInfo(instanced=True)
        svc.trigger_destroy(s.get_sim_instance())
        self.assertTrue(s.is_instanced())          # never leaves the instanced set
        self.assertEqual(len(svc.calls), 1)        # trigger_destroy was still called exactly once

    def test_fake_services_surface(self):
        active = fakes.FakeSimInfo()
        services = fakes.FakeServices(active_sim_info=active, active_household_id=7)
        self.assertIs(services.active_sim_info(), active)
        self.assertEqual(services.active_household_id(), 7)
        self.assertIsInstance(services.get_reset_and_delete_service(), fakes.FakeResetAndDeleteService)

    def test_fake_instance_manager_probe_shape(self):
        mgr = fakes.FakeInstanceManager(known={0xD27DB58CF1DAF8FA})
        self.assertIsNotNone(mgr.get(0xD27DB58CF1DAF8FA))
        self.assertIsNone(mgr.get(0x1234))

    def test_fake_connection_captures_output(self):
        conn = fakes.FakeConnection(id=5)
        conn.write('hello')
        self.assertEqual(conn.sent, ['hello'])
        self.assertEqual(int(conn), 5)


# ====================================================================== checker resolve(), pure
from tools import game_python  # noqa: E402


@unittest.skipUnless(game_python.available(), 'game python37_x64.dll not found - resolve() needs a '
                     'real 3.7 .pyc, its marshal format is not what this Python (3.12) writes')
class ResolveTests(unittest.TestCase):
    """resolve()/GameZips against a small, hand-made fake pair of zips - proves the name-descent
    algorithm itself, independent of anything in the real installed game's own zips. The fixture .pyc
    is compiled by the game's own python37_x64.dll (tools/build_ingame.py's own technique) because
    pyc37.py parses Python 3.7's marshal format specifically - a .pyc from this Python (3.12) uses a
    different, incompatible one."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        import textwrap
        import zipfile
        from tools import build_ingame
        cls.tmp = tempfile.mkdtemp(prefix='novulon_api_check_fakezip_')
        src = os.path.join(cls.tmp, 'fake_module.py')
        with open(src, 'w', encoding='utf-8') as f:
            f.write(textwrap.dedent('''\
                class Age:
                    YOUNGADULT = 16
                    ADULT = 32

                class SimInfo:
                    def remove_permanently(self, household):
                        pass

                    def is_instanced(self):
                        return True

                def register(name):
                    def deco(fn):
                        return fn
                    return deco

                @register('sims.reset')
                def _cmd_reset(*args, **kwargs):
                    pass
                '''))
        report = build_ingame.compile_in_game_python([src], cls.tmp)
        if report['errors'] or not report['compiled']:
            raise RuntimeError('could not compile the test fixture with the game python: %r %s'
                               % (report['errors'], report.get('stdout', '')))
        pyc = report['compiled'][0]
        cls.core_zip = os.path.join(cls.tmp, 'core.zip')
        cls.sim_zip = os.path.join(cls.tmp, 'simulation.zip')
        with zipfile.ZipFile(cls.core_zip, 'w'):
            pass
        with zipfile.ZipFile(cls.sim_zip, 'w') as z:
            z.write(pyc, 'fake_module.pyc')
        import tools.pyc37 as pyc37
        with zipfile.ZipFile(cls.sim_zip) as z:
            cls.code = pyc37.load(z.read('fake_module.pyc'))

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_class_found(self):
        self.assertEqual(check_tool.resolve(self.code, 'SimInfo', 'class'), (True, 'found'))

    def test_method_found(self):
        ok, detail = check_tool.resolve(self.code, 'SimInfo.remove_permanently', 'method')
        self.assertTrue(ok)
        self.assertIn('found', detail)

    def test_member_found(self):
        ok, detail = check_tool.resolve(self.code, 'Age.YOUNGADULT', 'const')
        self.assertTrue(ok)
        self.assertIn('Age', detail)

    def test_missing_member(self):
        ok, detail = check_tool.resolve(self.code, 'Age.ELDER', 'const')
        self.assertFalse(ok)
        self.assertIn('Age', detail)

    def test_missing_method(self):
        ok, _ = check_tool.resolve(self.code, 'SimInfo.teleport', 'method')
        self.assertFalse(ok)

    def test_cant_descend_past_a_plain_name(self):
        ok, detail = check_tool.resolve(self.code, 'Age.YOUNGADULT.NOPE', 'const')
        self.assertFalse(ok)
        self.assertIn("can't descend", detail)

    def test_command_literal_found_and_missing(self):
        self.assertEqual(check_tool.resolve(self.code, 'sims.reset', 'command'), (True, 'command literal present'))
        ok, _ = check_tool.resolve(self.code, 'sims.not_a_real_command', 'command')
        self.assertFalse(ok)

    def test_module_kind_needs_no_descent(self):
        self.assertEqual(check_tool.resolve(self.code, None, 'module'), (True, 'module present'))

    def test_gamezips_finds_module_in_second_zip(self):
        zips = check_tool.GameZips(gameplay=self.tmp, zip_order=('core.zip', 'simulation.zip'))
        self.assertTrue(zips.available())
        name, code = zips.find_module('fake_module')
        self.assertEqual(name, 'simulation.zip')
        self.assertIsNotNone(code)
        self.assertIsNone(zips.find_module('nope.nope')[1])
        zips.close()

    def test_check_end_to_end_against_the_fake_zips(self):
        rows = [
            manifest.Row('fake_module', 'SimInfo.remove_permanently', 'method', None, 'test'),
            manifest.Row('fake_module', 'Age.YOUNGADULT', 'const', 16, 'test'),
            manifest.Row('fake_module', 'sims.reset', 'command', None, 'test'),
            manifest.Row('fake_module', 'Nope.Nope', 'const', None, 'test'),
            manifest.Row('does.not.exist', 'X', 'class', None, 'test'),
        ]
        zips = check_tool.GameZips(gameplay=self.tmp, zip_order=('core.zip', 'simulation.zip'))
        results = check_tool.check(rows=rows, zips=zips)
        zips.close()
        by_path = {r['path']: r for r in results}
        self.assertTrue(by_path['SimInfo.remove_permanently']['ok'])
        self.assertTrue(by_path['Age.YOUNGADULT']['ok'])
        self.assertTrue(by_path['sims.reset']['ok'])
        self.assertFalse(by_path['Nope.Nope']['ok'])
        self.assertFalse(by_path['X']['ok'])
        self.assertIn('not found', by_path['X']['detail'])


class VersionWarningTests(unittest.TestCase):
    def test_no_warning_when_versions_agree(self):
        self.assertEqual(check_tool.version_warnings('1.2.3.4', {'pkg_a': '1.2.3.4'}), [])

    def test_warning_when_versions_disagree(self):
        warnings = check_tool.version_warnings('1.2.3.4', {'pkg_a': '9.9.9.9'})
        self.assertEqual(len(warnings), 1)
        self.assertIn('pkg_a', warnings[0])
        self.assertIn('9.9.9.9', warnings[0])
        self.assertIn('1.2.3.4', warnings[0])

    def test_no_warning_when_installed_version_unknown(self):
        self.assertEqual(check_tool.version_warnings(None, {'pkg_a': '1.2.3.4'}), [])

    def test_file_with_no_recorded_version_is_silent(self):
        self.assertEqual(check_tool.version_warnings('1.2.3.4', {}), [])


# ====================================================================== Tier 3 proper: the real game
@unittest.skipUnless(check_tool.GameZips().available(), 'game zips not found at %s' % check_tool.GAMEPLAY)
class RealGameCheckerTests(unittest.TestCase):
    """Every row here was independently confirmed against this machine's own installed game with
    tools/pyc37.py before being written down (see the top-level exploration this test file's author
    did before writing novulon_api_check.py - these are exactly those findings, re-asserted as a
    regression test so a future game patch that removes one of them is caught immediately)."""

    @classmethod
    def setUpClass(cls):
        cls.zips = check_tool.GameZips()

    @classmethod
    def tearDownClass(cls):
        cls.zips.close()

    def test_known_good_rows_resolve(self):
        good = [
            ('sims.sim_info', 'SimInfo.remove_permanently', 'method'),
            ('sims.sim_info', 'SimInfo.assign_to_household', 'method'),
            ('sims.sim_info', 'SimInfo.is_instanced', 'method'),
            ('sims.sim_info_types', 'Age.YOUNGADULT', 'const'),
            ('sims.sim_info_types', 'Age.INFANT', 'const'),
            ('sims.sim_info_types', 'Gender.MALE', 'const'),
            ('sims.occult.occult_enums', 'OccultType.WITCH', 'const'),
            ('sims.occult.occult_enums', 'OccultType.VAMPIRE', 'const'),
            ('traits.trait_commands', 'traits.equip_trait', 'command'),
            ('traits.trait_commands', 'traits.remove_trait', 'command'),
            ('sims4.commands', 'Command', 'class'),
            ('sims4.commands', 'CommandType.Cheat', 'const'),
            ('services', None, 'module'),          # a package, found via the __init__.pyc fallback
        ]
        for module, path, kind in good:
            zip_name, code = self.zips.find_module(module)
            self.assertIsNotNone(code, '%s not found in any zip' % module)
            ok, detail = check_tool.resolve(code, path, kind)
            self.assertTrue(ok, '%s %s (%s): %s' % (module, path, kind, detail))

    def test_known_bad_rows_are_reported_missing_not_crashed(self):
        bad = [
            ('sims.sim_info_types', 'Age.NOT_A_REAL_AGE', 'const'),
            ('sims.sim_info', 'SimInfo.not_a_real_method', 'method'),
            ('traits.trait_commands', 'traits.not_a_real_command', 'command'),
            ('does.not.exist.anywhere', 'X', 'class'),
        ]
        for module, path, kind in bad:
            zip_name, code = self.zips.find_module(module)
            if code is None:
                continue
            ok, _detail = check_tool.resolve(code, path, kind)
            self.assertFalse(ok, '%s %s (%s) unexpectedly resolved' % (module, path, kind))

    def test_game_build_version_reads_a_real_delta_version_ini(self):
        version = check_tool.game_build_version()
        self.assertIsNotNone(version)
        self.assertRegex(version, r'^\d+\.\d+\.\d+\.\d+$')

    def test_live_manifest_check_runs_clean_against_whatever_exists_right_now(self):
        """The actual, live novulon_api_manifest package, checked against the actual, live game
        install - this is exactly `python tools/novulon_api_check.py`, called as a library so the
        test asserts the same thing the command-line tool reports."""
        results = check_tool.check(zips=check_tool.GameZips())
        failures = [r for r in results if not r['ok']]
        self.assertEqual(failures, [], 'novulon_api_check reported missing names: %r' % failures)


if __name__ == '__main__':
    unittest.main(verbosity=2)
