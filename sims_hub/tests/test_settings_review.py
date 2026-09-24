"""Adversarial tests for speedkit.settings / settings_sgr / launch (review pass).

Everything runs on small synthetic FAKE Sims 4 trees under E:\\speedkit_test\\settings_review; the
real Sims 4 folder and E:\\The Sims 4 are never written (the stock rules are only read when present).

    python tests/test_settings_review.py
"""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import speedkit.journal as J
import speedkit.launch as L
import speedkit.settings as S
from speedkit import settings_sgr
from speedkit.journal import JournalError, file_digest

BASE = r'E:\speedkit_test\settings_review'

# A tiny rules set in the shape of the real ones (stock + Setters) so the tests do not depend on the
# user's live files.
STOCK_RULES = b'\r\n'.join([
    b'seti Off 0', b'seti On 1', b'seti Low 1', b'seti Medium 2', b'seti High 3', b'seti VeryHigh 4',
    b'set ConfigGroup Config',
    b'setProp $ConfigGroup ObjectSizeCullFactor 200',
    b'option SimQuality',
    b'    setting $High', b'        prop $ConfigGroup RenderSimLODDistances "5, 30, 85, 250"',
    b'    setting $VeryHigh', b'        prop $ConfigGroup RenderSimLODDistances "25, 50, 100, 1000"',
    b'end', b'setOption SimQuality $High',
    b'option LightingQuality',
    b'    setting $High', b'        prop $ConfigGroup ShadowMapSize 1024',
    b'    setting $VeryHigh', b'        prop $ConfigGroup ShadowMapSize 2048',
    b'end',
    b'logSystemInfo "=== Application info ==="', b''])
SETTERS_RULES = b'\r\n'.join([
    b'include "SimpsSetters.sgr"', b'seti High 3', b'seti VeryHigh 4', b'set ConfigGroup Config',
    b'setProp $ConfigGroup ObjectSizeCullFactor "${SBCull}"',
    b'option SimQuality', b'    setting $VeryHigh', b'        prop $ConfigGroup RenderSimLODDistances "${SBDist}"', b'end',
    b'logSystemInfo "BGN: Simp4Sims Info"', b'logSystemInfo "   - Release Date       : 27 Feb 2022"', b''])
SIMPS_SETTERS = b'seti B_Object_Cull 9999\r\nseti SBDist 3000\r\ninclude "MySetters.sgr"\r\nseti SBCull $B_Object_Cull\r\n'
UP_PRESET = b'seti B_Object_Cull 200\r\nseti SBDist 900\r\n'
UQ_PRESET = b'seti B_Object_Cull 9999\r\n'
SGR_FULL = b'\r\n'.join([
    b'seti VeryHigh 4', b'set ConfigGroup Config', b'setProp $ConfigGroup ObjectSizeCullFactor 9999',
    b'option SimQuality', b'    setting $VeryHigh', b'        prop $ConfigGroup RenderSimLODDistances "2999.97, 3000"', b'end',
    b'logSystemInfo "+++ Edited by Simp4Sims +++"', b'logSystemInfo "+++ 19-08-2021 SGR Full +++"', b''])
OPTIONS = (b'[options]\r\nsimquality = 4\r\n\r\nlightingquality = 4\r\n\r\nvisualquality = 5\r\n\r\n'
           b'fullscreen = 1\r\n\r\nwindowedfullscreen = 1\r\n\r\nframeratelimit = 240\r\n\r\n')


def _write(path, data=b'x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


class Fake(unittest.TestCase):
    def setUp(self):
        os.makedirs(BASE, exist_ok=True)
        self.sims = tempfile.mkdtemp(dir=BASE)
        self.home = os.path.join(self.sims, 'SpeedKit')
        self.bin = os.path.join(self.sims, 'GameBin')
        self.co = os.path.join(self.sims, 'ConfigOverride')
        self.src = os.path.join(self.sims, S.SETTERS_DIR)
        _write(os.path.join(self.bin, 'GraphicsRules.sgr'), STOCK_RULES)
        _write(os.path.join(self.co, 'GraphicsRules.sgr'), SGR_FULL)
        _write(os.path.join(self.co, 'MySetters.sgr'), UQ_PRESET)
        _write(os.path.join(self.co, 'SimpsSetters.sgr'), SIMPS_SETTERS)
        _write(os.path.join(self.src, 'GraphicsRules.sgr'), SETTERS_RULES)
        _write(os.path.join(self.src, 'SimpsSetters.sgr'), SIMPS_SETTERS)
        _write(os.path.join(self.src, 'MySetters.sgr'), b'')
        _write(os.path.join(self.src, S.PRESETS_DIR, 'Ultimate Performance', 'MySetters.sgr'), UP_PRESET)
        _write(os.path.join(self.src, S.PRESETS_DIR, 'Ultimate Quality', 'MySetters.sgr'), UQ_PRESET)
        _write(os.path.join(self.sims, 'Options.ini'), OPTIONS)
        _write(os.path.join(self.sims, 'Config.log'), b'+++ Edited by Simp4Sims +++\r\n+++ 19-08-2021 SGR Full +++\r\n')
        _write(os.path.join(self.sims, 'localthumbcache.package'), b'DBPF' + b'\0' * 50)
        _write(os.path.join(self.sims, 'cachestr', 'a.package'), b'DBPF')
        _write(os.path.join(self.sims, 'saves', 'Slot_00000001.save'), b'save')
        self.kw = dict(sims=self.sims, check_game=False)

    def tearDown(self):
        shutil.rmtree(self.sims, ignore_errors=True)

    def p(self, rel):
        return os.path.join(self.sims, rel.replace('/', os.sep))

    def tree(self):
        """{relative path: digest} of every file outside SpeedKit's own folder."""
        out = {}
        for dp, dn, fn in os.walk(self.sims):
            dn[:] = [d for d in dn if d != 'SpeedKit']
            for n in fn:
                p = os.path.join(dp, n)
                out[os.path.relpath(p, self.sims)] = file_digest(p)
        return out

    def fake_game_running(self):
        saved = (S.game_running, J.game_running, L.game_running)
        S.game_running = J.game_running = L.game_running = lambda: True
        self.addCleanup(self._unpatch, saved)

    @staticmethod
    def _unpatch(saved):
        S.game_running, J.game_running, L.game_running = saved


class SgrRobustness(Fake):
    def test_include_loop_is_an_error_not_a_crash(self):
        a, b = self.p('r/a.sgr'), self.p('r/b.sgr')
        _write(a, b'seti x 1\r\ninclude "b.sgr"\r\n')
        _write(b, b'seti y 2\r\ninclude "a.sgr"\r\n')
        r = settings_sgr.evaluate(a)                         # used to raise RecursionError
        self.assertEqual((r.vars['x'], r.vars['y']), (1, 2))
        self.assertTrue(any('include' in e[2] for e in r.errors), r.errors)

    def test_self_including_override_does_not_break_status_or_preflight(self):
        _write(os.path.join(self.co, 'GraphicsRules.sgr'), b'include "GraphicsRules.sgr"\r\n')
        g = S.graphics_status(self.sims, game_bin=self.bin)
        self.assertEqual(g['active'], 'other')
        r = S.preflight(self.sims, processes=False)
        self.assertIsNotNone(r['graphics'])

    def test_bad_if_expression_keeps_nesting(self):
        main = self.p('r/main.sgr')
        _write(main, b'\r\n'.join([
            b'seti outer 1',
            b'if ($outer == 1)',
            b'    if (@@@ broken)',                             # cannot be parsed
            b'        seti inner_true 1',
            b'    else',
            b'        seti inner_else 1',
            b'    endif',
            b'    seti after_inner 1',
            b'else',
            b'    seti outer_else 1',
            b'endif',
            b'seti tail 1', b'']))
        r = settings_sgr.evaluate(main)
        self.assertEqual(len(r.errors), 1, r.errors)
        self.assertNotIn('inner_true', r.vars)               # an unreadable condition is not taken
        self.assertNotIn('outer_else', r.vars)               # and does not unbalance the outer if
        self.assertEqual((r.vars.get('after_inner'), r.vars.get('tail')), (1, 1))


class GraphicsReview(Fake):
    def test_dry_runs_create_nothing(self):
        before = self.tree()
        S.graphics_use_stock(**self.kw)
        S.graphics_use_preset('Ultimate Performance', game_bin=self.bin, **self.kw)
        S.options_apply(**self.kw)
        S.caches_clean(tuple(S.CACHES), **self.kw)
        L.launch(exe=self.p('nothing.exe'), sims=self.sims, check_game=False, processes=False)
        self.assertEqual(self.tree(), before)
        self.assertFalse(os.path.exists(self.home))

    def test_preset_failure_midway_is_undoable(self):
        before = self.tree()
        real_put_new, calls = J.Journal.put_new, []

        def failing_put_new(j, tmp, final):
            calls.append(final)
            if len(calls) == 2:
                raise OSError('disk full (simulated)')
            return real_put_new(j, tmp, final)
        J.Journal.put_new = failing_put_new
        try:
            with self.assertRaises(OSError):
                S.graphics_use_preset('Ultimate Performance', dry_run=False, game_bin=self.bin, **self.kw)
        finally:
            J.Journal.put_new = real_put_new
        jid = S.journals(self.sims)[-1]
        self.assertTrue(jid[2].startswith('failed'), jid)
        S.graphics_restore(jid[0], dry_run=False, **self.kw)
        self.assertEqual(self.tree(), before)

    def test_restore_refuses_before_moving_anything_when_a_path_is_taken(self):
        before = self.tree()
        jid = S.graphics_use_stock(dry_run=False, **self.kw)['journal']
        # someone puts a new GraphicsRules.sgr in place; undo would restore two files, then stop
        _write(os.path.join(self.co, 'GraphicsRules.sgr'), b'# new file\r\n')
        with self.assertRaises(JournalError):
            S.graphics_restore(jid, dry_run=False, **self.kw)
        self.assertEqual(sorted(os.listdir(self.co)), ['GraphicsRules.sgr'])     # nothing was moved back
        os.remove(os.path.join(self.co, 'GraphicsRules.sgr'))                     # test's own scratch file
        S.graphics_restore(jid, dry_run=False, **self.kw)                         # and undo still works
        self.assertEqual(self.tree(), before)

    def test_restore_of_replace_journal_is_not_refused(self):
        before = self.tree()
        jid = S.graphics_use_preset('Ultimate Performance', dry_run=False, game_bin=self.bin, **self.kw)['journal']
        self.assertEqual(len(S.graphics_restore(jid, **self.kw)), 4)              # dry run: 2 removals + 2 restores
        S.graphics_restore(jid, dry_run=False, **self.kw)
        self.assertEqual(self.tree(), before)

    def test_preview_uses_the_chosen_preset(self):
        up = S.graphics_use_preset('ultimate PERFORMANCE', game_bin=self.bin, **self.kw)
        prev = {d['prop']: d for d in up['preview']}
        self.assertNotIn('ObjectSizeCullFactor', prev)                            # 200 = stock
        uq = S.graphics_use_preset('Ultimate Quality', game_bin=self.bin, **self.kw)
        self.assertEqual({d['prop']: d for d in uq['preview']}['ObjectSizeCullFactor']['active'], '9999')

    def test_status_names_a_missing_include(self):
        shutil.copy2(os.path.join(self.src, 'GraphicsRules.sgr'), os.path.join(self.co, 'GraphicsRules.sgr'))
        os.remove(os.path.join(self.co, 'SimpsSetters.sgr'))
        g = S.graphics_status(self.sims, game_bin=self.bin)
        self.assertEqual(g['active'], 'simp_setters')
        self.assertTrue(any('SimpsSetters.sgr, which is missing' in n for n in g['notes']), g['notes'])

    def test_missing_setters_folder(self):
        shutil.rmtree(self.src)
        with self.assertRaises(ValueError):
            S.graphics_use_preset('Ultimate Performance', game_bin=self.bin, **self.kw)


class OptionsReview(Fake):
    def test_lf_file_without_final_newline(self):
        path = self.p('Options.ini')
        orig = b'[options]\nsimquality = 4\n\nfullscreen = 0\n\nwindowedfullscreen = 1\n\nnumboots = 3'
        _write(path, orig)
        plan = S.options_apply(dry_run=False, extra={'maxprotectedsims': 0}, **self.kw)
        new = _read(path)
        self.assertNotIn(b'\r', new)
        self.assertTrue(new.startswith(b'[options]\nsimquality = 3\n\nfullscreen = 0\n\nwindowedfullscreen = 1\n\nnumboots = 3\n'))
        self.assertIn(b'\nmaxprotectedsims = 0\n', new)
        self.assertEqual(S.read_options(self.sims)['numboots'], '3')
        S.restore(plan['journal'], dry_run=False, **self.kw)
        self.assertEqual(_read(path), orig)

    def test_appended_keys_follow_the_game_style(self):
        path = self.p('Options.ini')
        S.options_apply(dry_run=False, extra={'maxprotectedsims': 0}, **self.kw)
        new = _read(path)
        # every entry is followed by one blank line, as the game writes it; no double blank lines
        self.assertNotIn(b'\r\n\r\n\r\n', new)
        self.assertTrue(new.endswith(b'\r\n\r\nmaxprotectedsims = 0\r\n\r\n'), new[-80:])

    def test_duplicate_and_mixed_case_keys_are_all_rewritten(self):
        path = self.p('Options.ini')
        _write(path, b'[options]\r\nSimQuality = 4\r\n\r\nsimquality=4\r\n\r\n')
        S.options_apply(dry_run=False, display='keep', **self.kw)
        new = _read(path)
        self.assertIn(b'SimQuality = 3\r\n', new)
        self.assertIn(b'simquality=3\r\n', new)

    def test_value_checks(self):
        for bad in ('1\n', '1\r\nmodsdisabled = 1', '', ' ', '1 2', '=1'):
            with self.assertRaises(ValueError, msg=repr(bad)):
                S.options_apply(extra={'simquality': bad}, **self.kw)
        for key, bad in (('simquality', 9), ('simquality', True), ('generalreflections', -1), ('frameratelimit', 6.5)):
            with self.assertRaises(ValueError, msg='%s=%r' % (key, bad)):
                S.options_apply(extra={key: bad}, **self.kw)
        plan = S.options_apply(extra={'frameratelimit': '75'}, **self.kw)
        self.assertIn(('frameratelimit', 75), [(c['key'], c['new']) for c in plan['changes']])
        with self.assertRaises(ValueError):
            S.options_apply('ultra', **self.kw)
        with self.assertRaises(ValueError):
            S.options_status(self.sims, preset='ultra')

    def test_restore_dry_run_of_options_journal(self):
        orig = _read(self.p('Options.ini'))
        jid = S.options_apply(dry_run=False, **self.kw)['journal']
        acts = S.restore(jid, **self.kw)                  # journal.undo(dry_run=True) raised here
        self.assertEqual([a for a, _ in acts], ['remove new file (kept in quarantine)', 'restore'])
        self.assertNotEqual(_read(self.p('Options.ini')), orig)
        S.restore(jid, dry_run=False, **self.kw)
        self.assertEqual(_read(self.p('Options.ini')), orig)
        with self.assertRaises(JournalError):             # already undone
            S.restore(jid, **self.kw)

    def test_restore_plan_follows_move_steps(self):
        a, b = self.p('cachestr/a.package'), self.p('cachestr/moved/a.package')
        with J.Journal('settings', 'move test', home=self.home, sims=self.sims, check_game=False) as j:
            j.move(a, b)
        _write(a, b'new')                                 # something now sits where a comes back
        with self.assertRaises(JournalError):
            S.restore(j.id, dry_run=False, **self.kw)
        self.assertTrue(os.path.exists(b))
        os.remove(a)
        self.assertEqual(S.restore(j.id, **self.kw), [('move back', a)])
        S.restore(j.id, dry_run=False, **self.kw)
        self.assertEqual(_read(a), b'DBPF')

    def test_missing_options_ini(self):
        os.remove(self.p('Options.ini'))
        self.assertFalse(S.options_status(self.sims)['exists'])
        with self.assertRaises(FileNotFoundError):
            S.options_apply(**self.kw)


class CachesReview(Fake):
    def test_refuses_while_game_runs(self):
        before = self.tree()
        self.fake_game_running()
        self.assertTrue(S.caches_clean(sims=self.sims)['game_running'])
        with self.assertRaises(JournalError):
            S.caches_clean(dry_run=False, sims=self.sims)
        self.assertEqual(self.tree(), before)
        self.assertFalse(os.path.exists(self.home))

    def test_duplicate_names_are_cleaned_once(self):
        plan = S.caches_clean(('localthumbcache', 'localthumbcache', 'cachestr'), dry_run=False, **self.kw)
        self.assertEqual(len(plan['actions']), 2)
        self.assertEqual(S.journals(self.sims)[-1][2], 'committed')
        S.restore(plan['journal'], dry_run=False, **self.kw)
        self.assertTrue(os.path.exists(self.p('localthumbcache.package')))

    def test_saves_untouched(self):
        d = file_digest(self.p('saves/Slot_00000001.save'))
        plan = S.caches_clean(tuple(S.CACHES), dry_run=False, **self.kw)
        self.assertEqual(file_digest(self.p('saves/Slot_00000001.save')), d)
        self.assertTrue(all(not p.lower().startswith(self.p('saves').lower()) for _, p in plan['actions']))


class LaunchReview(Fake):
    def test_odd_manifest_does_not_crash(self):
        _write(self.p('Mods_parked/_manifest.json'), b'["sim/"]')
        self.assertEqual(L.detect_profile(self.sims), (None, self.p('Mods_parked/_manifest.json')))
        r = S.preflight(self.sims, processes=False)
        self.assertIsNone(r['parked']['manifest_items'])
        _write(os.path.join(self.home, 'profile_state.json'), b'["lean"]')
        self.assertEqual(L.detect_profile(self.sims)[0], None)


if __name__ == '__main__':
    os.makedirs(BASE, exist_ok=True)
    try:
        unittest.main(verbosity=2)
    finally:
        try:
            os.rmdir(BASE)
        except OSError:
            pass
