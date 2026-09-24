"""Tests for speedkit.settings, speedkit.settings_sgr and speedkit.launch.

Everything that changes files runs on a FAKE Sims 4 tree under E:\\speedkit_test\\settings, built from
copies of the user's Options.ini, Config.log, ConfigOverride and Simps_GraphicsRules_Setters files and
of the stock rules from E:\\The Sims 4\\Game\\Bin (originals are only read). The game is never started:
launch() is tested with a tiny .bat file.

    python tests/test_settings.py
"""
import json, os, re, shutil, sys, tempfile, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import speedkit.journal as J
import speedkit.launch as L
import speedkit.settings as S
from speedkit import settings_sgr
from speedkit.journal import JournalError, file_digest
from speedkit.library import SIMS as REAL_SIMS

BASE = r'E:\speedkit_test\settings'
TEMPLATE = os.path.join(BASE, 'template')
REAL_BIN = r'E:\The Sims 4\Game\Bin'
LEVELS = {'simquality': 4, 'objectquality': 3, 'lightingquality': 4, 'generalreflections': 3, 'edgesmoothing': 3,
          'visualeffects': 3, 'viewdistance': 3, 'terrainquality': 3, 'useuncompressedtextures': 1}
PROTECTED = ['saves/Slot_00000001.save', 'Tray/0x1.trayitem', 'UserSetting.ini', 'accountDataDB.package',
             'notify.glob', 'content/x.dat', 'Mods_parked/_old_caches/localthumbcache_20260924.package']


def _write(path, data=b'x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


# The user's files change under us (the game rewrites Options.ini and Config.log at every start, and the
# user is meant to run use-stock / use-preset for real), so the template pins the state these tests
# expect: Options.ini keys at the 9/23 values, SGR Full as the override (from ConfigOverride, or from
# SpeedKit's quarantine once use-stock has moved it there), Config.log naming it.
OPTIONS_PINNED = {'visualquality': 5, 'simquality': 4, 'useuncompressedtextures': 1, 'lightingquality': 4,
                  'generalreflections': 3, 'edgesmoothing': 3, 'visualeffects': 3, 'viewdistance': 3,
                  'objectquality': 3, 'terrainquality': 3, 'frameratelimit': 240, 'verticalsync': 0,
                  'fullscreen': 1, 'windowedfullscreen': 1, 'maxprotectedsims': 1}
SGR_FULL = None             # the SGR Full file the template uses, or None (those tests are skipped)


def _pin_options(data):
    for k, v in OPTIONS_PINNED.items():
        data, n = re.subn(rb'(?im)^(%s[ \t]*=[ \t]*)[^\r\n]*' % k.encode(), rb'\g<1>' + str(v).encode(), data)
        if not n:
            data += b'%s = %d\r\n\r\n' % (k.encode(), v)
    return data


def _find_sgr_full():
    """The user's SGR Full GraphicsRules.sgr: in ConfigOverride, else the newest quarantined copy."""
    cands = [os.path.join(REAL_SIMS, 'ConfigOverride', 'GraphicsRules.sgr')]
    for dp, _, fn in os.walk(os.path.join(REAL_SIMS, 'SpeedKit', 'quarantine')):
        if 'GraphicsRules.sgr' in fn:
            cands.append(os.path.join(dp, 'GraphicsRules.sgr'))
    found = [p for p in cands if os.path.isfile(p) and S._identify(p)[0] == 'simp_sgr_full']
    return max(found, key=os.path.getmtime) if found else None


def setUpModule():
    """Copy the user's settings files (read-only use of the originals) into a template fake tree."""
    global SGR_FULL
    if os.path.exists(TEMPLATE):
        shutil.rmtree(TEMPLATE)
    os.makedirs(TEMPLATE)
    with open(os.path.join(REAL_SIMS, 'Options.ini'), 'rb') as f:
        _write(os.path.join(TEMPLATE, 'Options.ini'), _pin_options(f.read()))
    shutil.copytree(os.path.join(REAL_SIMS, S.SETTERS_DIR), os.path.join(TEMPLATE, S.SETTERS_DIR))
    setters = os.path.join(TEMPLATE, S.SETTERS_DIR)
    co = os.path.join(TEMPLATE, 'ConfigOverride')
    os.makedirs(co)
    SGR_FULL = _find_sgr_full()
    if SGR_FULL:
        shutil.copy2(SGR_FULL, os.path.join(co, 'GraphicsRules.sgr'))
    shutil.copy2(os.path.join(setters, 'SimpsSetters.sgr'), os.path.join(co, 'SimpsSetters.sgr'))
    mine = os.path.join(REAL_SIMS, 'ConfigOverride', 'MySetters.sgr')
    up = os.path.join(setters, S.PRESETS_DIR, 'Ultimate Performance', 'MySetters.sgr')
    if not os.path.isfile(mine) or file_digest(mine) == file_digest(up):
        mine = os.path.join(setters, S.PRESETS_DIR, 'Ultimate Quality', 'MySetters.sgr')
    shutil.copy2(mine, os.path.join(co, 'MySetters.sgr'))
    with open(os.path.join(REAL_SIMS, 'Config.log'), 'rb') as f:
        log = f.read()
    if SGR_FULL and not log.startswith(b'+++ Edited by Simp4Sims +++'):
        start = log.find(b'=== Application info ===')
        log = b'+++ Edited by Simp4Sims +++\r\n+++ 19-08-2021 SGR Full +++\r\n' + log[max(start, 0):]
    _write(os.path.join(TEMPLATE, 'Config.log'), log)
    os.makedirs(os.path.join(TEMPLATE, 'GameBin'))
    for n in ('GraphicsRules.sgr', 'Ts4CommonRules.sgr'):
        shutil.copy2(os.path.join(REAL_BIN, n), os.path.join(TEMPLATE, 'GameBin', n))
    # caches (synthetic) and things that must never be touched
    _write(os.path.join(TEMPLATE, 'localthumbcache.package'), b'DBPF' + b'\0' * 92)
    _write(os.path.join(TEMPLATE, 'localsimtexturecache.package'), b'DBPF' + b'\1' * 5000)
    _write(os.path.join(TEMPLATE, 'avatarcache.package'), b'DBPF' + b'\2' * 300)
    _write(os.path.join(TEMPLATE, 'cachestr', 'spotlight_en-us.package'), b'DBPF' + b'\3' * 100)
    _write(os.path.join(TEMPLATE, 'onlinethumbnailcache', 'a.jpg'), b'\xff\xd8jpg')
    _write(os.path.join(TEMPLATE, 'onlinethumbnailcache', 'b.png'), b'\x89PNG')
    for rel in PROTECTED:
        _write(os.path.join(TEMPLATE, rel.replace('/', os.sep)), rel.encode())
    _write(os.path.join(TEMPLATE, 'Mods', 'Resource.cfg'), b'Priority 500\r\nPackedFile *.package\r\n')
    _write(os.path.join(TEMPLATE, 'Mods_parked', 'sim', 'a.package'), b'DBPF' + b'\0' * 200)
    _write(os.path.join(TEMPLATE, 'Mods_parked', '_manifest.json'), json.dumps({'moved': ['sim/']}).encode())


def tearDownModule():
    shutil.rmtree(TEMPLATE, ignore_errors=True)


class Fake(unittest.TestCase):
    """A fresh copy of the template tree for every test."""

    def setUp(self):
        self.sims = tempfile.mkdtemp(dir=BASE)
        shutil.rmtree(self.sims)
        shutil.copytree(TEMPLATE, self.sims)
        self.home = os.path.join(self.sims, 'SpeedKit')
        self.bin = os.path.join(self.sims, 'GameBin')
        self.co = os.path.join(self.sims, 'ConfigOverride')
        self.kw = dict(sims=self.sims, check_game=False)

    def tearDown(self):
        shutil.rmtree(self.sims, ignore_errors=True)

    def p(self, rel):
        return os.path.join(self.sims, rel.replace('/', os.sep))

    def digests(self, rels):
        return {r: file_digest(self.p(r)) for r in rels}

    def fake_game_running(self):
        """Pretend TS4_x64.exe runs (patches every module that asks)."""
        saved = (S.game_running, J.game_running, L.game_running)
        S.game_running = J.game_running = L.game_running = lambda: True
        self.addCleanup(self._unpatch, saved)

    @staticmethod
    def _unpatch(saved):
        S.game_running, J.game_running, L.game_running = saved

    def need_sgr_full(self):
        if not SGR_FULL:
            self.skipTest("the user's SGR Full GraphicsRules.sgr is neither in ConfigOverride nor in SpeedKit's quarantine")


# ================================================================================ rules interpreter
class SgrTests(Fake):
    def test_language(self):
        inc = self.p('rules/inc_7.sgr')
        _write(inc, b'seti fromInclude ($base * 2)\r\n')
        main = self.p('rules/main.sgr')
        _write(main, b'\r\n'.join([
            b'set ConfigGroup Config', b'seti Low 1', b'seti High 3', b'seti base 7   # comment',
            b'set incName "inc_${base}.sgr"', b'include "${incName}"', b'sinclude "missing.sgr"',
            b'if ($base > 10)', b'    seti branch 1', b'elseif(match("${cardVendor}", "NV*"))',
            b'    if (not $isMac and $cpuCount >= 4)', b'        seti branch 2', b'    else', b'        seti branch 3',
            b'    endif', b'else', b'    seti branch 4', b'endif',
            b'setf half (floor($base / 2) + 0.5)', b'seti rounded (round(2.5))',
            b'setProp $ConfigGroup GlobalThing "${fromInclude}, ${half}"',
            b'option Quality', b'    setting $Low', b'        prop $ConfigGroup Detail 10',
            b'    setting $High', b'        if ($branch == 2)', b'            prop $ConfigGroup Detail "${rounded}"',
            b'        endif', b'        prop $ConfigGroup Other $base', b'end', b'setOption Quality $Low',
            b'#<', b'garbage that is not sgr', b'#>', b'logSystemInfo "hello ${base}"']))
        r = settings_sgr.evaluate(main)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.vars['fromInclude'], 14)
        self.assertEqual(r.vars['branch'], 2)
        self.assertEqual(r.vars['half'], 3.5)
        self.assertEqual(r.vars['rounded'], 3)
        self.assertEqual([os.path.basename(f) for f in r.files], ['main.sgr', 'inc_7.sgr'])
        self.assertEqual(r.missing, [('sinclude', 'missing.sgr')])
        self.assertEqual(r.info, ['hello 7'])
        self.assertEqual(r.effective({})['Detail'], ('10', 'Quality=1'))            # setOption default
        eff = r.effective({'quality': 3})
        self.assertEqual(eff['Detail'][0], '3')
        self.assertEqual(eff['Other'][0], '7')
        self.assertEqual(eff['GlobalThing'], ('14, 3.5', 'global'))

    def test_stock_rules(self):
        r = settings_sgr.evaluate(os.path.join(self.bin, 'GraphicsRules.sgr'))
        self.assertEqual(r.errors, [])
        self.assertEqual([os.path.basename(f) for f in r.files], ['GraphicsRules.sgr', 'Ts4CommonRules.sgr'])
        e = {k: v[0] for k, v in r.effective(LEVELS).items()}
        self.assertEqual(e['ObjectSizeCullFactor'], '200')
        self.assertEqual(e['RenderSimLODDistances'], '25, 50, 100, 1000')
        self.assertEqual(e['RenderSimTextureSizes'], '2048, 1024, 512, 128')
        self.assertEqual(e['ClipPlaneDistances'], '0.1, 5, 1000, 1500')
        self.assertEqual(e['ObjectLODBias'], '0.6666')
        self.assertEqual(e['ShadowMapSize'], '2048')
        self.assertEqual(e['FSAALevel'], '8')
        self.assertEqual(r.effective({**LEVELS, 'simquality': 3})['RenderSimLODDistances'][0], '5, 30, 85, 250')

    def test_user_override_and_presets(self):
        self.need_sgr_full()
        full = settings_sgr.evaluate(os.path.join(self.co, 'GraphicsRules.sgr'))
        self.assertEqual(full.errors, [])
        self.assertEqual(full.info[:2], ['+++ Edited by Simp4Sims +++', '+++ 19-08-2021 SGR Full +++'])
        e = {k: v[0] for k, v in full.effective(LEVELS).items()}
        self.assertEqual((e['ObjectSizeCullFactor'], e['ShadowMapSize'], e['FSAALevel']), ('9999', '5120', '512'))
        self.assertEqual(e['RenderSimLODDistances'], '2999.97, 2999.98, 2999.99, 3000')
        setters = os.path.join(self.sims, S.SETTERS_DIR)
        up = os.path.join(setters, S.PRESETS_DIR, 'Ultimate Performance', 'MySetters.sgr')
        r = settings_sgr.evaluate(os.path.join(setters, 'GraphicsRules.sgr'), None, {'MySetters.sgr': up})
        self.assertEqual(r.errors, [])
        self.assertEqual(os.path.normcase(r.files[-1]), os.path.normcase(up))
        e = {k: v[0] for k, v in r.effective(LEVELS).items()}
        self.assertEqual(e['ObjectSizeCullFactor'], '-1')                 # X_Pixelated_Bread_Shop overrides B_Object_Cull 200
        self.assertEqual(e['RenderSimLODDistances'], '8997, 8998, 8999, 9000')
        self.assertEqual(e['ShadowMapSize'], '2048')
        self.assertEqual(e['NormalMappingEnabled'], 'false')
        self.assertEqual(e['ObjectLODBias'], '0.6666')


# ================================================================================ graphics
class GraphicsTests(Fake):
    def setUp(self):
        super().setUp()
        self.need_sgr_full()

    def test_status_sgr_full(self):
        g = S.graphics_status(self.sims, game_bin=self.bin)
        self.assertEqual(g['active'], 'simp_sgr_full')
        self.assertIn('19-08-2021', g['label'])
        loaded = {f['name']: f['loaded'] for f in g['files']}
        self.assertEqual(loaded, {'GraphicsRules.sgr': True, 'MySetters.sgr': False, 'SimpsSetters.sgr': False})
        self.assertTrue(g['config_log']['matches'])
        d = {x['prop']: x for x in g['differences']}
        self.assertEqual((d['ObjectSizeCullFactor']['stock'], d['ObjectSizeCullFactor']['active']), ('200', '9999'))
        self.assertEqual(d['ObjectSizeCullFactor']['effect'], 'heavier')
        self.assertEqual(d['ObjectLODBias']['effect'], 'heavier')
        self.assertEqual(d['SsaoEnabled']['effect'], 'lighter')
        self.assertGreater(len(g['missing_stock_options']), 30)
        self.assertTrue(any('not loaded' in n for n in g['notes']))

    def test_use_stock_and_restore(self):
        before = self.digests(['ConfigOverride/' + n for n in S.SETTER_FILES])
        plan = S.graphics_use_stock(**self.kw)
        self.assertTrue(plan['dry_run'])
        self.assertEqual(len(plan['actions']), 3)
        self.assertEqual(self.digests(before), before)                     # dry run changed nothing
        self.assertFalse(os.path.exists(self.home))
        plan = S.graphics_use_stock(dry_run=False, **self.kw)
        self.assertEqual([n for n in os.listdir(self.co) if n.endswith('.sgr')], [])
        g = S.graphics_status(self.sims, game_bin=self.bin)
        self.assertEqual((g['active'], g['differences']), ('stock', []))
        self.assertTrue(any('changed after the last game start' in n or 'not what' in n for n in g['notes']))
        acts = S.graphics_restore(plan['journal'], **self.kw)              # dry run by default
        self.assertEqual(len(acts), 3)
        self.assertEqual(os.listdir(self.co), [])
        S.graphics_restore(plan['journal'], dry_run=False, **self.kw)
        self.assertEqual(self.digests(before), before)
        self.assertEqual(S.graphics_use_stock(**self.kw)['actions'][0][0], 'quarantine')

    def test_use_preset_and_restore(self):
        before = self.digests(['ConfigOverride/' + n for n in S.SETTER_FILES])
        simps_mtime = os.path.getmtime(os.path.join(self.co, 'SimpsSetters.sgr'))
        plan = S.graphics_use_preset('ultimate performance', game_bin=self.bin, **self.kw)
        self.assertEqual(plan['preset'], 'Ultimate Performance')
        self.assertEqual([a for a, _ in plan['actions']], ['replace', 'keep (identical)', 'replace'])
        self.assertEqual(self.digests(before), before)
        prev = {d['prop']: d for d in plan['preview']}
        self.assertEqual(prev['RenderSimLODDistances']['active'], '8997, 8998, 8999, 9000')
        plan = S.graphics_use_preset('Ultimate Performance', dry_run=False, game_bin=self.bin, **self.kw)
        src = os.path.join(self.sims, S.SETTERS_DIR)
        self.assertEqual(file_digest(os.path.join(self.co, 'GraphicsRules.sgr')), file_digest(os.path.join(src, 'GraphicsRules.sgr')))
        self.assertEqual(file_digest(os.path.join(self.co, 'MySetters.sgr')),
                         file_digest(os.path.join(src, S.PRESETS_DIR, 'Ultimate Performance', 'MySetters.sgr')))
        self.assertEqual(os.path.getmtime(os.path.join(self.co, 'SimpsSetters.sgr')), simps_mtime)
        self.assertFalse(os.path.exists(os.path.join(self.home, 'staging')))
        g = S.graphics_status(self.sims, game_bin=self.bin)
        self.assertEqual((g['active'], g['preset']), ('simp_setters', 'Ultimate Performance'))
        self.assertTrue(all(f['loaded'] for f in g['files']))
        self.assertTrue(any('9000 m' in n for n in g['notes']))
        again = S.graphics_use_preset('Ultimate Performance', dry_run=False, game_bin=self.bin, **self.kw)
        self.assertIsNone(again['journal'])
        S.graphics_restore(plan['journal'], dry_run=False, **self.kw)
        self.assertEqual(self.digests(before), before)

    def test_preset_into_empty_folder_then_undo_both(self):
        before = self.digests(['ConfigOverride/' + n for n in S.SETTER_FILES])
        j1 = S.graphics_use_stock(dry_run=False, **self.kw)['journal']
        p = S.graphics_use_preset('Defaults', dry_run=False, game_bin=self.bin, **self.kw)
        self.assertNotEqual(p['journal'], j1)
        self.assertEqual([a for a, _ in p['actions']], ['add', 'add', 'add'])
        self.assertEqual(os.path.getsize(os.path.join(self.co, 'MySetters.sgr')), 0)
        with self.assertRaises(JournalError):                              # stock undo would restore over new files
            S.graphics_restore(j1, dry_run=False, **self.kw)
        S.graphics_restore(p['journal'], dry_run=False, **self.kw)
        S.graphics_restore(j1, dry_run=False, **self.kw)
        self.assertEqual(self.digests(before), before)

    def test_bad_preset_and_game_running(self):
        with self.assertRaises(ValueError):
            S.graphics_use_preset('Nope', game_bin=self.bin, **self.kw)
        before = self.digests(['ConfigOverride/' + n for n in S.SETTER_FILES])
        self.fake_game_running()
        self.assertTrue(S.graphics_use_stock(sims=self.sims)['game_running'])
        with self.assertRaises(JournalError):
            S.graphics_use_stock(dry_run=False, sims=self.sims)
        with self.assertRaises(JournalError):
            S.graphics_use_preset('Ultimate Performance', dry_run=False, sims=self.sims, game_bin=self.bin)
        self.assertEqual(self.digests(before), before)


# ================================================================================ Options.ini
class OptionsTests(Fake):
    def read(self):
        with open(self.p('Options.ini'), 'rb') as f:
            return f.read()

    def test_status(self):
        o = S.options_status(self.sims)
        rows = {r['key']: r for r in o['settings']}
        self.assertEqual((rows['simquality']['value'], rows['simquality']['meaning']), ('4', 'Very High'))
        self.assertEqual(rows['simquality']['suggested'], 3)
        self.assertNotIn('suggested', rows['viewdistance'])
        self.assertTrue(any('windowedfullscreen' in n for n in o['notes']))

    def test_apply_only_listed_keys_and_restore(self):
        orig = self.read()
        plan = S.options_apply(**self.kw)
        self.assertEqual(self.read(), orig)                               # dry run
        want = {'visualquality': '0', 'simquality': '3', 'useuncompressedtextures': '0', 'lightingquality': '3',
                'generalreflections': '1', 'edgesmoothing': '1', 'visualeffects': '2', 'frameratelimit': '60',
                'windowedfullscreen': '0'}
        self.assertEqual({c['key']: str(c['new']) for c in plan['changes']}, want)
        plan = S.options_apply(dry_run=False, **self.kw)
        new = self.read()
        a, b = orig.splitlines(keepends=True), new.splitlines(keepends=True)
        self.assertEqual(len(a), len(b))
        changed = 0
        for x, y in zip(a, b):
            if x == y:
                continue
            changed += 1
            key = x.split(b'=')[0].strip().decode()
            self.assertIn(key, want)
            self.assertEqual(y, ('%s = %s\r\n' % (key, want[key])).encode())
        self.assertEqual(changed, len(want))
        self.assertEqual(S.read_options(self.sims)['fullscreen'], '1')
        self.assertEqual(S.read_options(self.sims)['verticalsync'], '0')
        self.assertIsNone(S.options_apply(dry_run=False, **self.kw)['journal'])   # nothing left to change
        S.restore(plan['journal'], dry_run=False, **self.kw)
        self.assertEqual(self.read(), orig)

    def test_display_modes_extra_and_missing_key(self):
        orig = self.read()
        self.assertNotIn('fullscreen', {c['key'] for c in S.options_apply(display='keep', **self.kw)['changes']})
        with self.assertRaises(ValueError):
            S.options_apply(display='huge', **self.kw)
        with self.assertRaises(ValueError):
            S.options_apply(extra={'numboots': 0}, **self.kw)
        with self.assertRaises(ValueError):
            S.options_apply(extra={'onlineaccess': '0\r\nmodsdisabled = 1'}, **self.kw)
        # drop the verticalsync line: it must be appended, everything before stays identical
        stripped = orig.replace(b'verticalsync = 0\r\n\r\n', b'')
        _write(self.p('Options.ini'), stripped)
        plan = S.options_apply('performance', dry_run=False, display='borderless', extra={'maxprotectedsims': 0}, **self.kw)
        o = S.read_options(self.sims)
        self.assertEqual((o['fullscreen'], o['windowedfullscreen'], o['maxprotectedsims']), ('0', '1', '0'))
        self.assertEqual((o['simquality'], o['objectquality'], o['verticalsync']), ('2', '2', '0'))
        changed = {c['key'] for c in plan['changes']}
        old, new = stripped.splitlines(keepends=True), self.read().splitlines(keepends=True)
        for x, y in zip(old, new):                                        # only the listed keys differ
            if x != y:
                self.assertIn(x.split(b'=')[0].strip().decode(), changed)
        tail = new[len(old):]
        if old[-1].strip():                                               # the game's style: one blank line per entry
            self.assertEqual(tail, [b'\r\n', b'verticalsync = 0\r\n'])
        else:
            self.assertEqual(tail, [b'verticalsync = 0\r\n', b'\r\n'])
        self.assertNotIn(b'\r\n\r\n\r\n', self.read())

    def test_refuses_while_game_runs(self):
        orig = self.read()
        self.fake_game_running()
        plan = S.options_apply(sims=self.sims)
        self.assertTrue(plan['game_running'])
        with self.assertRaises(JournalError):
            S.options_apply(dry_run=False, sims=self.sims)
        self.assertEqual(self.read(), orig)
        self.assertFalse(os.path.exists(self.home))

    def test_journal_ids_do_not_collide(self):
        a = S.options_apply(dry_run=False, **self.kw)['journal']
        b = S.graphics_use_stock(dry_run=False, **self.kw)['journal']
        self.assertNotEqual(a, b)
        self.assertEqual({j[0] for j in S.journals(self.sims)}, {a, b})
        S.restore(b, dry_run=False, **self.kw)
        S.restore(a, dry_run=False, **self.kw)


# ================================================================================ caches
class CachesTests(Fake):
    CACHE_FILES = ['localthumbcache.package', 'localsimtexturecache.package', 'avatarcache.package',
                   'cachestr/spotlight_en-us.package', 'onlinethumbnailcache/a.jpg', 'onlinethumbnailcache/b.png']
    KEEP = PROTECTED + ['Options.ini', 'ConfigOverride/SimpsSetters.sgr', 'Mods/Resource.cfg']

    def test_status(self):
        c = {r['name']: r for r in S.caches_status(self.sims)['caches']}
        self.assertEqual(c['onlinethumbnailcache']['files'], 2)
        self.assertEqual(c['localsimtexturecache']['bytes'], 5004)
        self.assertEqual(S.caches_status(self.sims)['parked_old_caches']['files'], 1)

    def test_default_is_localthumbcache_only(self):
        plan = S.caches_clean(**self.kw)
        self.assertEqual(plan['actions'], [('quarantine', self.p('localthumbcache.package'))])

    def test_clean_all_and_restore(self):
        caches = self.digests(self.CACHE_FILES)
        keep = self.digests(self.KEEP)
        plan = S.caches_clean(tuple(S.CACHES), **self.kw)
        self.assertEqual(len(plan['actions']), 6)
        self.assertEqual(self.digests(caches), caches)
        plan = S.caches_clean(tuple(S.CACHES), dry_run=False, **self.kw)
        for rel in self.CACHE_FILES:
            self.assertFalse(os.path.exists(self.p(rel)), rel)
        self.assertTrue(os.path.isdir(self.p('cachestr')) and os.path.isdir(self.p('onlinethumbnailcache')))
        self.assertEqual(self.digests(keep), keep)
        q = os.path.join(self.home, 'quarantine', plan['journal'])
        self.assertTrue(os.path.exists(os.path.join(q, 'onlinethumbnailcache', 'a.jpg')))
        self.assertEqual(S.caches_clean(tuple(S.CACHES), **self.kw)['note'], 'nothing to clean')
        S.restore(plan['journal'], dry_run=False, **self.kw)
        self.assertEqual(self.digests(caches), caches)
        self.assertEqual(self.digests(keep), keep)

    def test_refuses_other_names(self):
        for bad in ('saves', 'Options.ini', 'Tray', '../Mods'):
            with self.assertRaises(ValueError):
                S.caches_clean((bad,), dry_run=False, **self.kw)


# ================================================================================ preflight and launch
class PreflightLaunchTests(Fake):
    def make_exe(self):
        exe = self.p('fakegame/TS4_x64.bat')
        _write(exe, b'@echo off\r\necho started> "%~dp0started.txt"\r\n')
        return exe, self.p('fakegame/started.txt')

    def test_preflight_reads_this_pc(self):
        self.need_sgr_full()
        r = S.preflight(self.sims)
        m = r['memory']
        self.assertGreater(m['ram_total_mb'], 1000)
        self.assertGreater(m['commit_limit_mb'], m['ram_total_mb'] - 1)
        self.assertTrue(r['apps'] and all(a['private_mb'] >= 0 for a in r['apps']))
        self.assertIn('C', r['disk'])
        self.assertIsInstance(r['game_running'], bool)
        self.assertTrue(r['parked']['lean'])
        self.assertEqual((r['parked']['files'], r['parked']['manifest_items']), (1, 1))
        self.assertTrue(all(isinstance(w, str) for w in r['warnings']))
        self.assertEqual(r['ok'], not r['warnings'])
        self.assertEqual(r['graphics']['active'], 'simp_sgr_full')

    def test_launch_dry_run_starts_nothing(self):
        exe, marker = self.make_exe()
        p = L.launch(exe=exe, sims=self.sims, check_game=False, processes=False)
        self.assertEqual((p['started'], p['dry_run'], p['refused'], p['profile']), (False, True, None, 'lean'))
        time.sleep(1.5)
        self.assertFalse(os.path.exists(marker))
        self.assertFalse(os.path.exists(p['launch_file']))

    def test_launch_fake_exe(self):
        exe, marker = self.make_exe()
        t0 = time.time()
        p = L.launch(exe=exe, dry_run=False, sims=self.sims, check_game=False, processes=False)
        t1 = time.time()
        self.assertTrue(p['started'])
        with open(os.path.join(self.home, 'launch_time.json'), encoding='utf-8') as f:
            lt = json.load(f)
        self.assertTrue(t0 <= lt['epoch'] <= t1)
        self.assertEqual((lt['profile'], lt['pid'], lt['exe']), ('lean', p['pid'], exe))
        for _ in range(100):
            if os.path.exists(marker):
                break
            time.sleep(0.1)
        self.assertTrue(os.path.exists(marker), 'the fake game did not run')

    def test_launch_refusals(self):
        p = L.launch(exe=self.p('nothing/TS4_x64.exe'), dry_run=False, sims=self.sims, check_game=False, processes=False)
        self.assertFalse(p['started'])
        self.assertIn('not found', p['refused'])
        exe, marker = self.make_exe()
        self.fake_game_running()
        p = L.launch(exe=exe, dry_run=False, sims=self.sims, processes=False)
        self.assertFalse(p['started'])
        self.assertIn('already running', p['refused'])
        self.assertFalse(os.path.exists(os.path.join(self.home, 'launch_time.json')))
        self.assertEqual(L.detect_profile(self.sims)[0], 'lean')
        _write(self.p('Mods_parked/_manifest.json'), b'{"moved": []}')
        self.assertEqual(L.detect_profile(self.sims)[0], 'full')
        _write(os.path.join(self.home, 'profile_state.json'), b'{"profile": "builder"}')
        self.assertEqual(L.detect_profile(self.sims)[0], 'builder')


if __name__ == '__main__':
    os.makedirs(BASE, exist_ok=True)
    unittest.main(verbosity=2)
