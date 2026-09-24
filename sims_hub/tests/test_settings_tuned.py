"""Tests for 'SpeedKit Max Quality' (speedkit.settings.graphics_use_tuned and friends).

The user asked: "keep graphics at highest but fix the lag". SpeedKit Max Quality is the user's Simp4Sims
SGR Full rules file with only its lag-causing values brought back to sane, still high-end values.

Everything that changes files runs on FAKE Sims 4 trees under E:\\speedkit_test\\graphics:
  * a template built from COPIES of the user's ConfigOverride files (SGR Full from ConfigOverride, or
    from SpeedKit's quarantine if a real run moved it there), Simps_GraphicsRules_Setters, Options.ini
    (graphics levels pinned to the user's Ultra / Very High), Config.log and the stock rules from
    E:\\The Sims 4\\Game\\Bin - the originals are only read;
  * small synthetic rules files for the patcher's text handling.
The adversarial review tests at the end (ReviewReal, ReviewSynthetic) use fake trees under
E:\\speedkit_test\\graphics_review: game-parser validity, if-branches for other hardware (the laptop's AMD iGPU,
less memory), never below stock, Setters leftovers in ConfigOverride, refusal while the game runs, and the
self-check itself. The game is never started.

    python tests/test_settings_tuned.py
"""
import os, re, shutil, sys, tempfile, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import speedkit.journal as J
import speedkit.launch as L
import speedkit.settings as S
from speedkit import settings_sgr
from speedkit.journal import JournalError, file_digest
from speedkit.library import SIMS as REAL_SIMS

BASE = r'E:\speedkit_test\graphics'
TEMPLATE = os.path.join(BASE, 'template')
REVIEW_BASE = r'E:\speedkit_test\graphics_review'       # fake trees of the adversarial review tests (end of file)
REAL_BIN = r'E:\The Sims 4\Game\Bin'
# The user's graphics levels (Options.ini, 9/23 and 9/24): Ultra / Very High everywhere.
LEVELS = {'visualquality': 5, 'simquality': 4, 'useuncompressedtextures': 1, 'objectquality': 3, 'lightingquality': 4,
          'generalreflections': 3, 'edgesmoothing': 3, 'visualeffects': 3, 'viewdistance': 3, 'terrainquality': 3}
# What SpeedKit Max Quality must give at those levels (the spec's numbers).
EXPECTED_AFTER = {
    'RenderSimLODDistances': [50, 100, 200, 2000],      # 2x stock 25/50/100/1000
    'RenderSimTextureSizes': [2048, 2048, 1024, 512],   # stock 2048/1024/512/128, SGR Full 2048 x4
    'ObjectSizeCullFactor': [200],                      # stock
    'ObjectLODBias': [0.6666],                          # stock
    'ClipPlaneDistances': [0.1, 0.42, 1000, 1500],      # far = stock, near = SGR Full
    'FSAALevel': [8],                                   # stock max
    'ShadowMapSize': [4096],                            # between stock 2048 and SGR Full 5120
    'MirrorFadeRadiusThreshold': [2.6],                 # 2x stock 1.3
    'InteriorMirrorFarPlane': [150],                    # 2x stock 75
    'ExteriorMirrorFarPlane': [300],                    # 2x stock 150
    'TerrainLODBoost': [2],
}
EXPECTED_BEFORE = {       # SGR Full at the same levels
    'RenderSimLODDistances': [2999.97, 2999.98, 2999.99, 3000], 'RenderSimTextureSizes': [2048] * 4,
    'ObjectSizeCullFactor': [9999], 'ObjectLODBias': [0], 'ClipPlaneDistances': [0.1, 0.42, 9999, 9999],
    'FSAALevel': [512], 'ShadowMapSize': [5120], 'MirrorFadeRadiusThreshold': [120], 'InteriorMirrorFarPlane': [900],
    'ExteriorMirrorFarPlane': [1200], 'TerrainLODBoost': [6]}
PROTECTED = ['saves/Slot_00000001.save', 'Tray/0x1.trayitem', 'UserSetting.ini', 'Mods/Resource.cfg']
SGR_FULL = None


def _write(path, data=b'x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


def _nums(v):
    return [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', v or '')]


def _find_sgr_full():
    """The user's SGR Full: ConfigOverride, else the newest copy in SpeedKit's quarantine (read-only)."""
    cands = [os.path.join(REAL_SIMS, 'ConfigOverride', 'GraphicsRules.sgr')]
    q = os.path.join(REAL_SIMS, 'SpeedKit', 'quarantine')
    if os.path.isdir(q):
        for jid in os.listdir(q):
            cands.append(os.path.join(q, jid, 'ConfigOverride', 'GraphicsRules.sgr'))
    found = [p for p in cands if os.path.isfile(p) and S._identify(p)[0] == 'simp_sgr_full']
    return max(found, key=os.path.getmtime) if found else None


def _pin_options(data):
    for k, v in LEVELS.items():
        data, n = re.subn(rb'(?im)^(%s[ \t]*=[ \t]*)[^\r\n]*' % k.encode(), rb'\g<1>' + str(v).encode(), data)
        if not n:
            data += b'%s = %d\r\n\r\n' % (k.encode(), v)
    return data


def setUpModule():
    global SGR_FULL
    os.makedirs(BASE, exist_ok=True)
    if os.path.exists(TEMPLATE):
        shutil.rmtree(TEMPLATE)
    os.makedirs(TEMPLATE)
    SGR_FULL = _find_sgr_full()
    co = os.path.join(TEMPLATE, 'ConfigOverride')
    os.makedirs(co)
    if SGR_FULL:
        shutil.copy2(SGR_FULL, os.path.join(co, 'GraphicsRules.sgr'))
    setters = os.path.join(REAL_SIMS, S.SETTERS_DIR)
    if os.path.isdir(setters):
        shutil.copytree(setters, os.path.join(TEMPLATE, S.SETTERS_DIR))
    for n in ('MySetters.sgr', 'SimpsSetters.sgr'):         # the user's two unused leftovers
        p = os.path.join(REAL_SIMS, 'ConfigOverride', n)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(co, n))
    opts = os.path.join(REAL_SIMS, 'Options.ini')
    _write(os.path.join(TEMPLATE, 'Options.ini'), _pin_options(_read(opts) if os.path.isfile(opts) else b'[options]\r\n'))
    log = _read(os.path.join(REAL_SIMS, 'Config.log')) if os.path.isfile(os.path.join(REAL_SIMS, 'Config.log')) else b''
    start = log.find(b'=== Application info ===')
    log = b'+++ Edited by Simp4Sims +++\r\n+++ 19-08-2021 SGR Full +++\r\n' + (log[start:] if start >= 0 else b'')
    _write(os.path.join(TEMPLATE, 'Config.log'), log)
    os.makedirs(os.path.join(TEMPLATE, 'GameBin'))
    for n in ('GraphicsRules.sgr', 'Ts4CommonRules.sgr'):
        if os.path.isfile(os.path.join(REAL_BIN, n)):
            shutil.copy2(os.path.join(REAL_BIN, n), os.path.join(TEMPLATE, 'GameBin', n))
    for rel in PROTECTED:
        _write(os.path.join(TEMPLATE, rel.replace('/', os.sep)), rel.encode())
    old = time.time() - 3600                                # Config.log is from the last game start
    os.utime(os.path.join(TEMPLATE, 'Config.log'), (old, old))


def tearDownModule():
    shutil.rmtree(TEMPLATE, ignore_errors=True)
    for d in (BASE, REVIEW_BASE):
        try:
            os.rmdir(d)
        except OSError:
            pass


class Fake(unittest.TestCase):
    """A fresh copy of the template tree for every test."""
    ROOT = BASE

    def setUp(self):
        if not SGR_FULL or not os.path.isfile(os.path.join(TEMPLATE, 'GameBin', 'GraphicsRules.sgr')):
            self.skipTest("the user's SGR Full or the stock rules are not available")
        os.makedirs(self.ROOT, exist_ok=True)
        self.sims = tempfile.mkdtemp(dir=self.ROOT)
        shutil.rmtree(self.sims)
        shutil.copytree(TEMPLATE, self.sims)
        self.home = os.path.join(self.sims, 'SpeedKit')
        self.bin = os.path.join(self.sims, 'GameBin')
        self.co = os.path.join(self.sims, 'ConfigOverride')
        self.rules = os.path.join(self.co, 'GraphicsRules.sgr')
        self.kw = dict(sims=self.sims, check_game=False, game_bin=self.bin)

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
                out[os.path.relpath(os.path.join(dp, n), self.sims)] = file_digest(os.path.join(dp, n))
        return out

    def status(self):
        return S.graphics_status(self.sims, game_bin=self.bin)

    def fake_game_running(self):
        saved = (S.game_running, J.game_running, L.game_running)
        S.game_running = J.game_running = L.game_running = lambda: True
        self.addCleanup(self._unpatch, saved)

    @staticmethod
    def _unpatch(saved):
        S.game_running, J.game_running, L.game_running = saved

    def effective(self, path=None, text=None):
        machine = settings_sgr.machine_vars(self.p('Config.log'))
        r = settings_sgr.evaluate(path or self.rules, machine, text=text)
        return r, {k: v[0] for k, v in r.effective(LEVELS).items()}


# ================================================================================ values
class TunedValues(Fake):
    def test_values_at_the_users_levels(self):
        plan = S.graphics_use_tuned(**self.kw)
        self.assertEqual((plan['action'], plan['refused'], plan['journal']), ('replace', None, None))
        self.assertEqual(plan['active'], 'simp_sgr_full')
        rows = {r['prop']: r for r in plan['table']}
        self.assertEqual(set(rows), set(EXPECTED_AFTER))
        for prop, want in EXPECTED_AFTER.items():
            self.assertEqual(_nums(rows[prop]['after']), want, prop)
            self.assertEqual(_nums(rows[prop]['before']), EXPECTED_BEFORE[prop], prop)
        # the rules behind the numbers, against the stock values of this very game version
        st = {p: _nums(r['stock']) for p, r in rows.items()}
        self.assertEqual(_nums(rows['RenderSimLODDistances']['after']), [2 * x for x in st['RenderSimLODDistances']])
        self.assertEqual(_nums(rows['ClipPlaneDistances']['after'])[2:], st['ClipPlaneDistances'][2:])
        for p in ('MirrorFadeRadiusThreshold', 'InteriorMirrorFarPlane', 'ExteriorMirrorFarPlane'):
            self.assertAlmostEqual(_nums(rows[p]['after'])[0], 2 * st[p][0])
        for p in ('ObjectSizeCullFactor', 'ObjectLODBias', 'FSAALevel'):
            self.assertEqual(_nums(rows[p]['after']), st[p])

    def test_result_evaluates_to_the_intended_values_and_nothing_else_changed(self):
        t = S.build_tuned_rules(self.rules, self.sims, self.bin, target=self.rules)
        text = t['data'].decode('latin-1')
        base, before = self.effective()
        tuned, after = self.effective(text=text)
        self.assertEqual(tuned.errors, [])
        for prop, want in EXPECTED_AFTER.items():
            self.assertEqual(_nums(after[prop]), want, prop)
        for prop in set(before) | set(after):
            if prop not in S.TUNED_PROPS:
                self.assertEqual(before.get(prop), after.get(prop), prop)
        # SGR Full's visual improvements stay (spot checks at the user's levels)
        for prop in ('SsaoEnabled', 'DofEnabled', 'WaterReflectionAreaThresholdLot', 'WaterReflectionAreaThresholdWorld',
                     'ObjectLODInterestBias', 'ClipPlaneZoomDistant', 'TextureSizeThreshold', 'SimCacheSizeLimit',
                     'FogDistances', 'NormalMappingEnabled', 'UseUncompressedTextures'):
            self.assertEqual(after.get(prop), before.get(prop), prop)
        # at EVERY level of every option only the tuned props differ
        for name, opt in base.options.items():
            for level, props in opt['settings'].items():
                tprops = tuned.options[name]['settings'][level]
                for prop in set(props) | set(tprops):
                    if prop not in S.TUNED_PROPS:
                        self.assertEqual(props.get(prop), tprops.get(prop), '%s=%s %s' % (name, level, prop))
        self.assertEqual({k: v for k, v in base.globals.items() if k != 'ObjectSizeCullFactor'},
                         {k: v for k, v in tuned.globals.items() if k != 'ObjectSizeCullFactor'})
        self.assertEqual(tuned.info[:3], ['+++ Edited by Simp4Sims +++', '+++ 19-08-2021 SGR Full +++', S.TUNED_LOG_TEXT])

    def test_minimal_textual_patch(self):
        orig = _read(self.rules).decode('latin-1').splitlines(keepends=True)
        t = S.build_tuned_rules(self.rules, self.sims, self.bin, target=self.rules)
        new = t['data'].decode('latin-1').splitlines(keepends=True)
        header = len(S.TUNED_HEADER)
        self.assertTrue(new[0].startswith(S.TUNED_MARK) and 'Tuned by SpeedKit' in new[0])
        self.assertTrue(all(l.startswith('#') and not l.startswith(('#<', '#>')) for l in new[:header]))
        body = [l for l in new[header:] if l.strip() != S.TUNED_LOG]
        self.assertEqual(len(new) - header - len(body), 1)                  # exactly one log line added
        self.assertEqual(len(body), len(orig))
        changed = [(a, b) for a, b in zip(orig, body) if a != b]
        self.assertEqual(len(changed), len(t['changes']))
        self.assertEqual(sorted(c['line'] for c in t['changes']),
                         [n + 1 for n, (a, b) in enumerate(zip(orig, body)) if a != b])
        for a, b in changed:                        # same prop line, same indentation, same line ending
            ma, mb = S._PROP_LINE.match(a.rstrip('\r\n')), S._PROP_LINE.match(b.rstrip('\r\n'))
            self.assertEqual(ma.group(1), mb.group(1))
            self.assertIn(ma.group(2), S.TUNED_PROPS)
            self.assertEqual(a[len(a.rstrip('\r\n')):], b[len(b.rstrip('\r\n')):])
        self.assertTrue(all(l.endswith('\r\n') for l in new))                # CRLF like the original
        self.assertEqual(t['problems'], [])


# ================================================================================ install / undo
class TunedInstall(Fake):
    def test_dry_run_changes_nothing(self):
        before = self.tree()
        S.graphics_use_tuned(**self.kw)
        self.status()
        self.assertEqual(self.tree(), before)
        self.assertFalse(os.path.exists(self.home))

    def test_install_status_and_restore(self):
        before = self.tree()
        orig = _read(self.rules)
        plan = S.graphics_use_tuned(dry_run=False, **self.kw)
        self.assertEqual(plan['action'], 'replace')
        jid = plan['journal']
        self.assertTrue(jid)
        new = _read(self.rules)
        self.assertTrue(new.startswith(S.TUNED_MARK.encode()))
        self.assertEqual(_read(os.path.join(self.home, 'quarantine', jid, 'ConfigOverride', 'GraphicsRules.sgr')), orig)
        after = self.tree()
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        self.assertEqual(changed, {os.path.join('ConfigOverride', 'GraphicsRules.sgr')})   # Options.ini untouched
        self.assertFalse(os.path.exists(os.path.join(self.home, 'staging')))
        self.assertEqual(S.journals(self.sims)[-1][1:3], ('settings', 'committed'))
        self.assertTrue(S.journals(self.sims)[-1][4].startswith(S.TUNED_NOTE))
        g = self.status()
        self.assertEqual(g['active'], 'speedkit_tuned')
        self.assertTrue(g['label'].startswith('SpeedKit Max Quality'), g['label'])
        self.assertEqual(g['tuned'], {'ok': True, 'over': [], 'journal': jid, 'confirmed': False})
        self.assertEqual(g['tune']['action'], 'none')
        self.assertEqual(g['tuned_journal'], jid)
        self.assertTrue(any('changed after the last game start' in n for n in g['notes']), g['notes'])
        d = {x['prop'] for x in g['differences']}
        self.assertFalse(d & {'ObjectSizeCullFactor', 'ObjectLODBias', 'FSAALevel'})    # back to stock
        # undo: dry run first (nothing moves), then for real -> the original bytes are back
        acts = S.graphics_restore(sims=self.sims, check_game=False)
        self.assertEqual([a for a, _ in acts], ['remove new file (kept in quarantine)', 'restore'])
        self.assertEqual(_read(self.rules), new)
        S.graphics_restore(dry_run=False, sims=self.sims, check_game=False)
        self.assertEqual(self.tree(), before)
        g = self.status()
        self.assertEqual((g['active'], g['tuned'], g['tuned_journal']), ('simp_sgr_full', None, None))
        self.assertEqual(g['tune']['action'], 'replace')
        with self.assertRaises(JournalError):
            S.graphics_restore(sims=self.sims, check_game=False)          # nothing left to undo

    def test_idempotent(self):
        first = S.graphics_use_tuned(dry_run=False, **self.kw)
        data = _read(self.rules)
        n = len(S.journals(self.sims))
        again = S.graphics_use_tuned(dry_run=False, **self.kw)
        self.assertEqual((again['action'], again['journal'], again['changes']), ('none', None, []))
        self.assertEqual(_read(self.rules), data)
        self.assertEqual(len(S.journals(self.sims)), n)
        self.assertEqual(S.build_tuned_rules(self.rules, self.sims, self.bin, target=self.rules)['data'], data)
        # tuning the tuned file gives the same bytes as tuning the original SGR Full
        orig = os.path.join(self.home, 'quarantine', first['journal'], 'ConfigOverride', 'GraphicsRules.sgr')
        self.assertEqual(S.build_tuned_rules(orig, self.sims, self.bin, target=self.rules)['data'], data)

    def test_config_log_confirms(self):
        S.graphics_use_tuned(dry_run=False, **self.kw)
        _write(self.p('Config.log'), ('+++ Edited by Simp4Sims +++\r\n+++ 19-08-2021 SGR Full +++\r\n%s\r\n'
                                      '=== Application info ===\r\n' % S.TUNED_LOG_TEXT).encode())
        future = time.time() + 5
        os.utime(self.p('Config.log'), (future, future))
        g = self.status()
        self.assertTrue(g['config_log']['tuned_logged'] and g['config_log']['matches'])
        self.assertTrue(g['tuned']['confirmed'])
        self.assertTrue(any('Config.log confirms' in n for n in g['notes']))

    def test_user_replaces_the_file_later(self):
        jid = S.graphics_use_tuned(dry_run=False, **self.kw)['journal']
        setters = os.path.join(self.sims, S.SETTERS_DIR, 'GraphicsRules.sgr')
        if not os.path.isfile(setters):
            self.skipTest('no Setters rules to replace with')
        os.remove(self.rules)                                # the user swaps in another rules file (fake tree)
        shutil.copy2(setters, self.rules)
        g = self.status()
        self.assertEqual(g['active'], 'simp_setters')
        self.assertEqual(g['tuned_journal'], jid)
        self.assertTrue(any('has been replaced since' in n and jid in n for n in g['notes']), g['notes'])
        self.assertEqual(g['tune']['action'], 'refused')
        before = self.tree()
        plan = S.graphics_use_tuned(dry_run=False, **self.kw)          # never replaces the user's own file
        self.assertEqual((plan['action'], plan['journal']), ('refused', None))
        self.assertIn('leaves your own rules file alone', plan['refused'])
        self.assertEqual(self.tree(), before)
        plan = S.graphics_use_tuned(dry_run=False, replace_other=True, **self.kw)
        self.assertEqual(plan['action'], 'replace')
        self.assertIn(os.path.join('quarantine', jid), plan['source'])   # made from the quarantined SGR Full
        self.assertEqual(self.status()['active'], 'speedkit_tuned')
        S.graphics_restore(plan['journal'], dry_run=False, sims=self.sims, check_game=False)
        self.assertEqual(file_digest(self.rules), file_digest(setters))

    def test_edited_tuned_file(self):
        S.graphics_use_tuned(dry_run=False, **self.kw)
        text = _read(self.rules)
        heavier = text.replace(b'ShadowMapSize 4096', b'ShadowMapSize 8192')
        self.assertNotEqual(heavier, text)
        _write(self.rules, heavier)
        g = self.status()
        self.assertFalse(g['tuned']['ok'])
        self.assertEqual(g['tuned']['over'], ['ShadowMapSize (LightingQuality=4)'])
        plan = S.graphics_use_tuned(dry_run=False, **self.kw)
        self.assertEqual((plan['action'], len(plan['changes'])), ('replace', 1))
        self.assertEqual(_read(self.rules), text)
        # a LIGHTER value the user chose is kept (every rule is a cap)
        _write(self.rules, text.replace(b'ShadowMapSize 4096', b'ShadowMapSize 2048'))
        self.assertTrue(self.status()['tuned']['ok'])
        self.assertEqual(S.graphics_use_tuned(**self.kw)['action'], 'none')

    def test_from_stock_with_leftovers(self):
        before = self.tree()
        j1 = S.graphics_use_stock(dry_run=False, sims=self.sims, check_game=False)['journal']
        g = self.status()
        self.assertEqual(g['active'], 'stock')
        self.assertEqual(g['tune']['action'], 'add')
        plan = S.graphics_use_tuned(dry_run=False, **self.kw)
        self.assertEqual(plan['action'], 'add')
        self.assertIn(os.path.join('quarantine', j1), plan['source'])
        self.assertEqual(sorted(os.listdir(self.co)), ['GraphicsRules.sgr'])        # the unused setters stay parked
        self.assertEqual(self.status()['active'], 'speedkit_tuned')
        with self.assertRaises(JournalError):                  # stock undo would restore over the tuned file
            S.restore(j1, dry_run=False, sims=self.sims, check_game=False)
        S.graphics_restore(plan['journal'], dry_run=False, sims=self.sims, check_game=False)
        S.restore(j1, dry_run=False, sims=self.sims, check_game=False)
        self.assertEqual(self.tree(), before)

    def test_report_table_before_and_after_install(self):
        before = S.graphics_tuned_table(self.sims, game_bin=self.bin)
        S.graphics_use_tuned(dry_run=False, **self.kw)
        after = S.graphics_tuned_table(self.sims, game_bin=self.bin)     # original now read from quarantine
        self.assertEqual(before, after)
        rows = {r['prop']: r for r in after}
        self.assertEqual(_nums(rows['ShadowMapSize']['before']), [5120])
        self.assertEqual(_nums(rows['ShadowMapSize']['after']), [4096])
        os.remove(self.rules)
        shutil.rmtree(os.path.join(self.home, 'quarantine'))           # fake tree: no original left
        self.assertEqual(S.graphics_tuned_table(self.sims, game_bin=self.bin), [])

    def test_undone_tuned_copy_is_a_source_too(self):
        plan = S.graphics_use_tuned(dry_run=False, **self.kw)
        S.graphics_restore(plan['journal'], dry_run=False, sims=self.sims, check_game=False)
        srcs = S.tuned_sources(self.sims)
        self.assertEqual(os.path.normcase(srcs[0]), os.path.normcase(self.rules))       # the live SGR Full first
        self.assertTrue(any('_undone_new' in s for s in srcs))

    def test_refuses_while_game_runs(self):
        before = self.tree()
        self.fake_game_running()
        plan = S.graphics_use_tuned(sims=self.sims, game_bin=self.bin)
        self.assertTrue(plan['game_running'])
        self.assertTrue(any('running' in n for n in plan['notes']))
        with self.assertRaises(JournalError):
            S.graphics_use_tuned(dry_run=False, sims=self.sims, game_bin=self.bin)
        self.assertEqual(self.tree(), before)
        self.assertFalse(os.path.exists(self.home))

    def test_no_source_is_refused(self):
        os.remove(self.rules)                                 # fake tree: nothing to tune from
        before = self.tree()
        plan = S.graphics_use_tuned(dry_run=False, **self.kw)
        self.assertEqual(plan['action'], 'refused')
        self.assertIn('No Simp4Sims SGR Full', plan['refused'])
        self.assertEqual(self.tree(), before)
        self.assertFalse(os.path.exists(self.home))
        self.assertEqual(self.status()['tune']['action'], 'refused')

    def test_missing_stock_rules_is_refused(self):
        plan = S.graphics_use_tuned(dry_run=False, sims=self.sims, check_game=False, game_bin=self.p('nothing'))
        self.assertEqual(plan['action'], 'refused')
        self.assertFalse(os.path.exists(self.home))

    def test_bad_source_argument(self):
        with self.assertRaises(ValueError):
            S.graphics_use_tuned(source=os.path.join(self.bin, 'GraphicsRules.sgr'), **self.kw)
        with self.assertRaises(FileNotFoundError):
            S.graphics_use_tuned(source=self.p('nothing.sgr'), **self.kw)

    def test_file_changed_while_preparing(self):
        real_build = S.build_tuned_rules

        def build_then_someone_edits(*a, **k):
            r = real_build(*a, **k)
            with open(self.rules, 'ab') as f:
                f.write(b'\r\n# edited meanwhile\r\n')
            return r
        S.build_tuned_rules = build_then_someone_edits
        try:
            with self.assertRaises(JournalError):
                S.graphics_use_tuned(dry_run=False, **self.kw)
        finally:
            S.build_tuned_rules = real_build
        self.assertTrue(_read(self.rules).endswith(b'# edited meanwhile\r\n'))
        self.assertFalse(os.path.exists(os.path.join(self.home, 'journal')))

    def test_preflight_names_it(self):
        S.graphics_use_tuned(dry_run=False, **self.kw)
        r = S.preflight(self.sims, processes=False)            # reads the real stock rules (read-only)
        if r['graphics'] is None:
            self.skipTest('stock rules not readable from the real game folder')
        self.assertEqual(r['graphics']['active'], 'speedkit_tuned')
        self.assertTrue(any(n.startswith('Graphics rules: SpeedKit Max Quality') for n in r['notes']), r['notes'])


# ================================================================================ synthetic text handling
STOCK = b'\r\n'.join([
    b'seti Off 0', b'seti Low 1', b'seti Medium 2', b'seti High 3', b'seti VeryHigh 4', b'set ConfigGroup Config',
    b'setProp $ConfigGroup ObjectSizeCullFactor "200"',
    b'option SimQuality',
    b'    setting $High', b'        prop $ConfigGroup RenderSimLODDistances "5, 30, 85, 250"',
    b'        prop $ConfigGroup RenderSimTextureSizes "1024, 512, 256, 128"',
    b'    setting $VeryHigh', b'        prop $ConfigGroup RenderSimLODDistances "25, 50, 100, 1000"',
    b'        prop $ConfigGroup RenderSimTextureSizes "2048, 1024, 512, 128"',
    b'end',
    b'option GeneralReflections',
    b'    setting $High', b'        prop $ConfigGroup ExteriorMirrorFarPlane 150.0f',
    b'        prop $ConfigGroup MirrorFadeRadiusThreshold 1.3f',
    b'end',
    b'option ObjectQuality', b'    setting $High', b'        if ($cpuCount > 0)',
    b'            prop $ConfigGroup ObjectLODBias "0.6666"', b'        endif', b'end', b''])
# SGR-Full-like, LF endings, tabs, a trailing comment, a value from a variable, an include that sets a prop
FULL = b'\n'.join([
    b'set ConfigGroup Config', b'seti Low 1', b'seti High 3', b'seti VeryHigh 4', b'seti far 9999',
    b'include "extra.sgr"',
    b'setProp $ConfigGroup ObjectSizeCullFactor 9999   # keep small things',
    b'option SimQuality',
    b'\tsetting $High', b'\t\tprop $ConfigGroup RenderSimLODDistances "2999.97,2999.98,2999.99,3000"',
    b'\t\tprop $ConfigGroup RenderSimTextureSizes "1024, 1024, 1024, 1024"',
    b'\tsetting $VeryHigh', b'\t\tprop $ConfigGroup RenderSimLODDistances "${far}, ${far}, ${far}, ${far}"',
    b'\t\tprop $ConfigGroup RenderSimTextureSizes "2048, 2048, 2048, 2048" # sharp',
    b'end',
    b'option GeneralReflections',
    b'    setting $High', b'        prop $ConfigGroup ExteriorMirrorFarPlane 1200.0f',
    b'        prop $ConfigGroup MirrorFadeRadiusThreshold 120.0f',
    b'        prop $ConfigGroup WaterReflectionAreaThresholdLot 0',
    b'end',
    b'option ObjectQuality', b'    setting $High', b'        prop $ConfigGroup ObjectLODBias 0.00', b'end',
    b'logSystemInfo "+++ Edited by Simp4Sims +++"', b'logSystemInfo "+++ 01-01-2020 SGR Full +++"',
    b'logSystemInfo "=== Application info ==="', b'#<', b' signature', b'#>', b''])
EXTRA = b'setProp $ConfigGroup ShadowMapSize 5120\n'


class SyntheticTree(unittest.TestCase):
    """A small synthetic stock + SGR-Full-like tree (no tests of its own)."""
    ROOT = BASE

    def setUp(self):
        os.makedirs(self.ROOT, exist_ok=True)
        self.sims = tempfile.mkdtemp(dir=self.ROOT)
        self.bin = os.path.join(self.sims, 'GameBin')
        self.co = os.path.join(self.sims, 'ConfigOverride')
        self.rules = os.path.join(self.co, 'GraphicsRules.sgr')
        _write(os.path.join(self.bin, 'GraphicsRules.sgr'), STOCK)
        _write(self.rules, FULL)
        _write(os.path.join(self.co, 'extra.sgr'), EXTRA)
        _write(os.path.join(self.sims, 'Options.ini'), b'[options]\r\nsimquality = 4\r\n\r\ngeneralreflections = 3\r\n'
                                                        b'\r\nobjectquality = 3\r\n\r\n')

    def tearDown(self):
        shutil.rmtree(self.sims, ignore_errors=True)

    def build(self, levels=None):
        return S.build_tuned_rules(self.rules, self.sims, self.bin, levels=levels)


class TunedSynthetic(SyntheticTree):
    def test_text_style_is_kept(self):
        t = self.build()
        text = t['data'].decode('latin-1')
        self.assertNotIn('\r', text)                                                # LF file stays LF
        self.assertIn('setProp $ConfigGroup ObjectSizeCullFactor 200   # keep small things\n', text)
        self.assertIn('\t\tprop $ConfigGroup RenderSimLODDistances "10,60,170,500"\n', text)
        self.assertIn('\t\tprop $ConfigGroup RenderSimTextureSizes "1024, 1024, 512, 256"\n', text)
        self.assertIn('\t\tprop $ConfigGroup RenderSimTextureSizes "2048, 2048, 1024, 512" # sharp\n', text)
        self.assertIn('        prop $ConfigGroup ExteriorMirrorFarPlane 300.0f\n', text)
        self.assertIn('        prop $ConfigGroup MirrorFadeRadiusThreshold 2.6f\n', text)
        self.assertIn('        prop $ConfigGroup WaterReflectionAreaThresholdLot 0\n', text)      # untouched
        self.assertIn('        prop $ConfigGroup ObjectLODBias 0.6666\n', text)
        self.assertIn('logSystemInfo "+++ 01-01-2020 SGR Full +++"\n%s\nlogSystemInfo "=== Application info ==="'
                      % S.TUNED_LOG, text)
        self.assertTrue(text.endswith('#<\n signature\n#>\n'))
        # variables and included files are not patched, and the plan says so
        self.assertIn('"${far}, ${far}, ${far}, ${far}"', text)
        self.assertEqual(EXTRA, _read(os.path.join(self.co, 'extra.sgr')))
        self.assertEqual(len(t['problems']), 2, t['problems'])
        self.assertTrue(any('not a plain number' in p for p in t['problems']))
        self.assertTrue(any('included file' in p for p in t['problems']))

    def test_tuned_identified_and_retuning_is_stable(self):
        t = self.build()
        _write(self.rules, t['data'])
        self.assertEqual(S._identify(self.rules)[0], 'speedkit_tuned')
        self.assertIn('01-01-2020', S._identify(self.rules)[1])
        again = self.build()
        self.assertEqual((again['data'], again['changes']), (t['data'], []))

    def test_bom_stays_first(self):
        _write(self.rules, b'\xef\xbb\xbf' + FULL)
        t = self.build()
        self.assertTrue(t['data'].startswith(b'\xef\xbb\xbf' + S.TUNED_MARK.encode()))
        _write(self.rules, t['data'])
        self.assertEqual(S._identify(self.rules)[0], 'speedkit_tuned')
        self.assertEqual(self.build()['data'], t['data'])

    def test_a_patching_bug_is_caught_before_anything_is_written(self):
        real = S._format_like
        S._format_like = lambda el, x, keep_point=False: '7'
        try:
            with self.assertRaises(ValueError):
                self.build()
            with self.assertRaises(ValueError):
                S.graphics_use_tuned(dry_run=False, sims=self.sims, check_game=False, game_bin=self.bin)
        finally:
            S._format_like = real
        self.assertEqual(_read(self.rules), FULL)
        self.assertFalse(os.path.exists(os.path.join(self.sims, 'SpeedKit')))

    def test_prop_assigned_twice_in_one_block(self):
        twice = FULL.replace(b'\t\tprop $ConfigGroup RenderSimTextureSizes "1024, 1024, 1024, 1024"',
                             b'\t\tprop $ConfigGroup RenderSimTextureSizes "1024, 1024, 1024, 1024"\n'
                             b'\t\tprop $ConfigGroup RenderSimTextureSizes "1024, 512, 256, 128"')
        self.assertNotEqual(twice, FULL)
        _write(self.rules, twice)
        t = self.build(levels={'simquality': 3})           # the later (lighter) line is the one that counts
        self.assertEqual({r['prop']: r['after'] for r in t['table']}['RenderSimTextureSizes'], '1024, 512, 256, 128')
        self.assertIn(b'RenderSimTextureSizes "1024, 1024, 512, 256"\n\t\tprop $ConfigGroup RenderSimTextureSizes '
                      b'"1024, 512, 256, 128"', t['data'])

    def test_levels_parameter_only_changes_the_table(self):
        a, b = self.build(), self.build(levels={'SimQuality': 3})
        self.assertEqual(a['data'], b['data'])
        rows = {r['prop']: r for r in b['table']}
        self.assertEqual(rows['RenderSimLODDistances']['after'], '10,60,170,500')

    def test_evaluate_text_equals_file_and_where(self):
        machine = settings_sgr.machine_vars(None)
        r1 = settings_sgr.evaluate(self.rules, machine)
        r2 = settings_sgr.evaluate(self.rules, machine, text=FULL.decode())
        self.assertEqual(r1.effective({'simquality': 3}), r2.effective({'simquality': 3}))
        self.assertEqual(r1.where, r2.where)
        me = os.path.normcase(self.rules)
        self.assertEqual([(os.path.normcase(p), n) for p, n in r1.where[('SimQuality', 3, 'RenderSimLODDistances')]],
                         [(me, 10)])
        self.assertEqual([(os.path.normcase(p), n) for p, n in r1.where[(None, None, 'ObjectSizeCullFactor')]], [(me, 7)])
        self.assertEqual(os.path.basename(r1.where[(None, None, 'ShadowMapSize')][0][0]), 'extra.sgr')


# ================================================================================ adversarial review
# Other hardware the game may start on: this laptop also has an AMD Radeon 780M iGPU next to the RTX 4050, and
# smaller PCs take the memory branches of the rules.
MACHINES = {
    'this PC (RTX 4050 Laptop, 6 GB, 16 GB RAM)': {},
    'AMD Radeon 780M iGPU': {'cardVendor': 'ATI', 'textureMemory': 512},
    'Intel, 8 GB RAM': {'cardVendor': 'Intel', 'textureMemory': 1024, 'memory': 7900, 'cpuCount': 4},
    'low memory': {'textureMemory': 400, 'memory': 3000, 'virtualMemory': 2000},
}


def _tuned_prop_lines(text):
    """{line number: prop} of every prop/setProp line of a TUNED_PROPS prop, by the text alone (any branch)."""
    out, in_sig = {}, False
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if in_sig or s.startswith('#<'):
            in_sig = not s.startswith('#>')
            continue
        m = S._PROP_LINE.match(line)
        if m and m.group(2) in S.TUNED_PROPS:
            out[n] = m.group(2)
    return out


class ReviewReal(Fake):
    """The user's real SGR Full (a copy), on fake trees under E:\\speedkit_test\\graphics_review."""
    ROOT = REVIEW_BASE

    def machine(self, **over):
        m = settings_sgr.machine_vars(self.p('Config.log'))
        m.update(over)
        return m

    def test_file_stays_valid_for_the_games_parser(self):
        orig = _read(self.rules)
        data = S.build_tuned_rules(self.rules, self.sims, self.bin, target=self.rules)['data']
        data.decode('ascii')                                         # plain ASCII like SGR Full and EA's files
        sig = orig[orig.rindex(b'#<'):]
        self.assertTrue(sig.startswith(b'#<') and b'#>' in sig)
        self.assertTrue(data.endswith(sig))                          # EA's signature block, byte for byte, last
        self.assertEqual(data.count(b'#<'), orig.count(b'#<'))
        self.assertEqual(data.count(b'\r'), data.count(b'\r\n'))      # CRLF everywhere, no lone CR or LF
        self.assertEqual(data.count(b'\n'), data.count(b'\r\n'))
        lines, olines = data.split(b'\r\n'), orig.split(b'\r\n')
        h = len(S.TUNED_HEADER)
        for l in lines[:h]:                                          # full-line comments only (like Simp's Setters)
            self.assertTrue(l.startswith(b'# ') and not l.startswith((b'#<', b'#>')) and b'"' not in l, l)
        self.assertEqual(lines[h], olines[0])                        # then SGR Full from its first line on
        i = lines.index(S.TUNED_LOG.encode())
        self.assertRegex(lines[i - 1], rb'^logSystemInfo "\+\+\+ \S+ SGR Full \+\+\+"$')
        self.assertRegex(lines[i], rb'^logSystemInfo "[^"$#]*"$')
        self.assertEqual(lines.count(S.TUNED_LOG.encode()), 1)
        m = self.machine()
        base, tuned = settings_sgr.evaluate(self.rules, m), settings_sgr.evaluate(self.rules, m, text=data.decode('ascii'))
        self.assertEqual((tuned.errors, tuned.undefined, tuned.missing), (base.errors, base.undefined, base.missing))

    def test_every_tuned_prop_line_is_considered_in_every_branch(self):
        text = _read(self.rules).decode('latin-1')
        by_text = _tuned_prop_lines(text)
        self.assertTrue(by_text)
        base = settings_sgr.evaluate(self.rules, self.machine())
        seen = {n for (o, l, p), places in list(base.where.items()) + list(base.dormant.items())
                if p in S.TUNED_PROPS for _, n in places}
        self.assertEqual(set(by_text), seen)                         # none is skipped, whatever branch it is in
        t = S.build_tuned_rules(self.rules, self.sims, self.bin, target=self.rules)
        self.assertEqual(t['problems'], [])
        # in the tuned file every one of those lines is at its cap: tuning it again changes nothing
        _write(self.rules, t['data'])
        self.assertEqual(S.build_tuned_rules(self.rules, self.sims, self.bin, target=self.rules)['changes'], [])

    def test_other_hardware_gets_the_same_caps_and_nothing_else_changes(self):
        tuned_text = S.build_tuned_rules(self.rules, self.sims, self.bin, target=self.rules)['data'].decode('latin-1')
        stock_path = os.path.join(self.bin, 'GraphicsRules.sgr')
        for name, over in MACHINES.items():
            m = self.machine(**over)
            se = settings_sgr.evaluate(stock_path, m).effective(LEVELS)
            fe = settings_sgr.evaluate(self.rules, m).effective(LEVELS)
            te = settings_sgr.evaluate(self.rules, m, text=tuned_text).effective(LEVELS)
            for p in set(fe) | set(te):
                if p not in S.TUNED_PROPS:
                    self.assertEqual(te.get(p), fe.get(p), '%s: %s' % (name, p))
                    continue
                want = S.TUNED_PROPS[p][1](_nums(fe[p][0]), _nums(se[p][0]))
                self.assertEqual(_nums(te[p][0]), [float(x) for x in want], '%s: %s' % (name, p))
            self.assertEqual(_nums(te['ShadowMapSize'][0]), [4096], name)
            self.assertEqual(_nums(te['RenderSimLODDistances'][0]), [50, 100, 200, 2000], name)

    def test_never_below_stock(self):
        """The user wants the highest graphics: no value SpeedKit changes ends up below stock, at any level."""
        t = S.build_tuned_rules(self.rules, self.sims, self.bin, target=self.rules)
        self.assertTrue(t['changes'])
        for c in t['changes']:
            old, new, stock = _nums(c['old']), _nums(c['new']), _nums(c['stock'])
            for i, (a, b) in enumerate(zip(old, new)):
                if a == b:
                    continue                                          # untouched element (e.g. SGR Full's near clip)
                what = '%s=%s %s[%d]' % (c['option'], c['level'], c['prop'], i)
                if c['prop'] == 'ObjectLODBias':                     # lower bias = more detail: exactly stock
                    self.assertEqual(b, stock[i], what)
                else:
                    self.assertGreaterEqual(b, stock[i], what)
        for r in t['table']:                                         # and at the user's own levels
            st, after = _nums(r['stock']), _nums(r['after'])
            if r['prop'] == 'ObjectLODBias':
                self.assertEqual(after, st)
            elif r['prop'] == 'ClipPlaneDistances':
                self.assertEqual(after[2:], st[2:])
            else:
                self.assertTrue(all(a >= s for a, s in zip(after, st)), r)

    def test_setters_leftovers_in_configoverride_are_left_alone(self):
        for n, body in (('MySetters.sgr', b'setb S_Ambient_Occlusion true\r\nsetf B_LOD_Bias 0.4\r\n'),
                        ('SimpsSetters.sgr', b'seti SFSimDist1 9000\r\nsetProp $ConfigGroup ShadowMapSize 8192\r\n')):
            if not os.path.isfile(os.path.join(self.co, n)):                 # the user's copies when they exist
                _write(os.path.join(self.co, n), body)
        before = self.tree()
        plan = S.graphics_use_tuned(dry_run=False, **self.kw)
        after = self.tree()
        self.assertEqual({k for k in set(before) | set(after) if before.get(k) != after.get(k)},
                         {os.path.join('ConfigOverride', 'GraphicsRules.sgr')})
        r = settings_sgr.evaluate(self.rules, self.machine())
        self.assertEqual([os.path.normcase(f) for f in r.files], [os.path.normcase(self.rules)])   # not included
        g = self.status()
        self.assertEqual(g['active'], 'speedkit_tuned')
        self.assertEqual({f['name']: f['loaded'] for f in g['files']},
                         {'GraphicsRules.sgr': True, 'MySetters.sgr': False, 'SimpsSetters.sgr': False})
        self.assertEqual(_nums(r.effective(LEVELS)['ShadowMapSize'][0]), [4096])     # the leftover's 8192 is not used
        S.graphics_restore(plan['journal'], dry_run=False, sims=self.sims, check_game=False)
        self.assertEqual(self.tree(), before)

    def test_restore_refused_while_game_runs(self):
        plan = S.graphics_use_tuned(dry_run=False, **self.kw)
        installed = self.tree()
        self.fake_game_running()
        with self.assertRaises(JournalError):
            S.graphics_restore(dry_run=False, sims=self.sims)
        with self.assertRaises(JournalError):
            S.restore(plan['journal'], dry_run=False, sims=self.sims)
        self.assertEqual(self.tree(), installed)                                    # nothing moved
        self.assertEqual(S.tuned_journal(self.sims), plan['journal'])               # nothing was undone
        _write(self.rules, _read(self.rules).replace(b'ShadowMapSize 4096', b'ShadowMapSize 8192'))
        edited = self.tree()
        self.assertNotEqual(installed, edited)
        with self.assertRaises(JournalError):                                       # re-tuning refuses too
            S.graphics_use_tuned(dry_run=False, sims=self.sims, game_bin=self.bin)
        self.assertEqual(self.tree(), edited)
        self.assertEqual(len(S.journals(self.sims)), 1)


FULL_BRANCHES = FULL.replace(
    b'\t\tprop $ConfigGroup RenderSimTextureSizes "2048, 2048, 2048, 2048" # sharp',
    b'\t\tif (match("${cardVendor}", "ATI"))\n'
    b'\t\t\tprop $ConfigGroup RenderSimTextureSizes "4096, 4096, 4096, 4096"\n'
    b'\t\telseif ($textureMemory < ${slow})\n'
    b'\t\t\tprop $ConfigGroup RenderSimTextureSizes "${far}, 2048, 2048, 2048"\n'
    b'\t\telse\n'
    b'\t\t\tprop $ConfigGroup RenderSimTextureSizes "2048, 2048, 2048, 2048" # sharp\n'
    b'\t\tendif').replace(
    b'option GeneralReflections',
    b'if ($memory < 4000)\n    setProp $ConfigGroup ObjectSizeCullFactor 9999\nendif\noption GeneralReflections').replace(
    b'seti far 9999', b'seti far 9999\nseti slow 2048')


class ReviewSynthetic(SyntheticTree):
    ROOT = REVIEW_BASE

    def test_branches_for_other_hardware_are_capped_too(self):
        self.assertEqual(FULL_BRANCHES.count(b'\n'), FULL.count(b'\n') + 10)
        _write(self.rules, FULL_BRANCHES)
        t = self.build()
        text = t['data'].decode('latin-1')
        self.assertIn('\t\t\tprop $ConfigGroup RenderSimTextureSizes "2048, 2048, 1024, 512"\n\t\telseif', text)  # ATI
        self.assertIn('\t\t\tprop $ConfigGroup RenderSimTextureSizes "2048, 2048, 1024, 512" # sharp\n', text)
        self.assertIn('    setProp $ConfigGroup ObjectSizeCullFactor 200\nendif', text)                   # < 4 GB RAM
        other = {(c['prop'], c['new']) for c in t['changes'] if c['other_hardware']}
        self.assertEqual(other, {('RenderSimTextureSizes', '"2048, 2048, 1024, 512"'), ('ObjectSizeCullFactor', '200')})
        self.assertTrue(any('${far}' in p and 'not a plain number' in p for p in t['problems']), t['problems'])
        # on that hardware the game gets the same caps as on this PC
        for over in ({'cardVendor': 'ATI'}, {'memory': 3000}):
            m = dict(settings_sgr.machine_vars(None), **over)
            e = settings_sgr.evaluate(self.rules, m, text=text).effective({'simquality': 4})
            self.assertEqual(_nums(e['RenderSimTextureSizes'][0]), [2048, 2048, 1024, 512], over)
            self.assertEqual(_nums(e['ObjectSizeCullFactor'][0]), [200], over)
        plan = S.graphics_use_tuned(sims=self.sims, check_game=False, game_bin=self.bin)
        self.assertTrue(any('this PC does not use' in n for n in plan['notes']), plan['notes'])
        _write(self.rules, t['data'])
        self.assertEqual(self.build()['changes'], [])                               # idempotent

    def test_last_assignment_that_cannot_be_tuned_does_not_block_the_rest(self):
        """A prop set twice whose LAST line is a ${variable}: the first line is capped, the second is reported and
        left alone - the install must not fail its own self-check over it."""
        _write(self.rules, FULL.replace(
            b'\t\tprop $ConfigGroup RenderSimTextureSizes "1024, 1024, 1024, 1024"',
            b'\t\tprop $ConfigGroup RenderSimTextureSizes "1024, 1024, 1024, 1024"\n'
            b'\t\tprop $ConfigGroup RenderSimTextureSizes "${far}, 1024, 1024, 1024"'))
        t = self.build(levels={'simquality': 3})
        self.assertIn(b'RenderSimTextureSizes "1024, 1024, 512, 256"\n\t\tprop $ConfigGroup RenderSimTextureSizes '
                      b'"${far}, 1024, 1024, 1024"', t['data'])
        self.assertTrue(any('${far}, 1024' in p for p in t['problems']), t['problems'])
        self.assertEqual({r['prop']: r['after'] for r in t['table']}['RenderSimTextureSizes'], '9999, 1024, 1024, 1024')

    def test_status_names_lines_that_could_not_be_tuned(self):
        plan = S.graphics_use_tuned(dry_run=False, sims=self.sims, check_game=False, game_bin=self.bin)
        self.assertEqual(len(plan['problems']), 2, plan['problems'])        # ${far} Sim LOD + the included file
        g = S.graphics_status(self.sims, game_bin=self.bin)
        self.assertEqual((g['active'], g['tuned']['ok']), ('speedkit_tuned', True))
        self.assertTrue(any('2 lines of the SpeedKit Max Quality file could not be tuned' in n for n in g['notes']),
                        g['notes'])

    def test_self_check_catches_unintended_changes(self):
        """The self-check itself: it must find every kind of change the patch must not make."""
        seen = []
        real = S._check_tuned

        def spy(*a):
            seen.append(a)
            return real(*a)
        S._check_tuned = spy
        try:
            _write(self.rules, FULL_BRANCHES)
            self.build()
        finally:
            S._check_tuned = real
        base, tuned, want, changes, levels, before, after, hlen, log_at, want_dormant = seen[0]
        self.assertEqual(real(*seen[0]), [])
        self.assertTrue(want_dormant)

        def problems(edit):
            lines = list(after)
            edit(lines)
            t = settings_sgr.evaluate(self.rules, settings_sgr.machine_vars(None), text=''.join(lines))
            return real(base, t, want, changes, levels, before, lines, hlen, log_at, want_dormant)

        def sub(old, new):
            def edit(lines):
                i = next(i for i, l in enumerate(lines) if old in l)
                lines[i] = lines[i].replace(old, new)
            return edit
        cases = {
            'untuned prop': sub('WaterReflectionAreaThresholdLot 0', 'WaterReflectionAreaThresholdLot 5'),
            'tuned prop off its cap': sub('ExteriorMirrorFarPlane 300.0f', 'ExteriorMirrorFarPlane 301.0f'),
            'other-hardware line off its cap': sub('"2048, 2048, 1024, 512"\n', '"4096, 2048, 1024, 512"\n'),
            'variable': sub('seti far 9999', 'seti far 9998'),
            'signature removed': lambda lines: lines.__delitem__(slice(-3, None)),
            'branch removed': sub('if ($memory < 4000)', 'if (1)'),
        }
        for name, edit in cases.items():
            self.assertTrue(problems(edit), name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
