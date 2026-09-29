"""The Wicked Animator logo and credit in WickedWhims' own animation lists.

    python tools/checks/wwcredit/test_credit.py

WickedWhims shows an animation's own picture next to its name when animation_display_icon names one
(SexAnimationInstance.get_picker_row), and the author in the line under the name. The key is PNG-typed, but the game
draws the DDS picture (0x00B2D882, 'DST5') with the same instance - a PNG resource alone shows a llama. Every export
carries the logo (one shared picture) and "<author> · Made with Novulon's Wicked Animator"; file, stage and clip names
keep the plain author, and the app's own readers (library, Game Doctor, identifier) read the plain author back.
Packages are written into a temp folder only (never the real Mods). The export rows need the game's rig (E:\\The
Sims 4) and are skipped without it.
"""
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
BACKEND = os.path.join(ROOT, 'backend')
TMP = tempfile.mkdtemp(prefix='wa_credit_')
os.environ.setdefault('ANIMATOR_SAVES', os.path.join(TMP, 'saves'))
for p in (BACKEND, os.path.join(ROOT, 'tools', 'checks', 'bedanim')):
    if p not in sys.path:
        sys.path.insert(0, p)

import dbpf                                                        # noqa: E402
import exporter as X                                               # noqa: E402
import wwpackage as W                                              # noqa: E402
import gamedata                                                    # noqa: E402
import doctor                                                      # noqa: E402
import wwlists                                                     # noqa: E402
from test_bed_export import baked_project, HAS_GAME, NO_GAME       # noqa: E402


def _field(root, name):
    el = next((t for t in root.iter('T') if t.get('n') == name), None)
    return el.text if el is not None else None


class Credit(unittest.TestCase):
    def test_credited_and_plain_author(self):
        self.assertEqual(W.credited('Novulon'), "Novulon \u00b7 Made with Novulon's Wicked Animator")
        self.assertEqual(W.credited(W.credited('Novulon')), W.credited('Novulon'))      # never twice
        self.assertEqual(W.credited('  '), W.CREDIT)
        self.assertEqual(W.plain_author(W.credited('Novulon')), 'Novulon')
        self.assertEqual(W.plain_author('TURBODRIVER'), 'TURBODRIVER')                  # other creators untouched
        self.assertEqual(W.plain_author(W.CREDIT), '')

    def test_icon_is_a_128px_dst5_like_wickedwhims_own(self):
        from PIL import Image
        import numpy as np
        import texfmt
        t, g, i, data = W.icon_resource()
        self.assertEqual((t, g, i), (W.T_IMG, 0, W.ICON_INSTANCE))
        info = texfmt.dds_info(data)
        self.assertEqual((info['format'], info['width'], info['height']), ('DST5', 128, 128))
        # the same header WickedWhims' own 128 px icons have
        self.assertEqual(data[:128].hex(), '444453207c00000007100200800000008000000000000000010000000800000000000000'
                         '0000000000000000000000000000000000000000000000000000000000000000000000000000000020000000'
                         '040000004453543500000000000000000000000000000000000000000810400000000000000000000000000000000000')
        # it is the logo (made from the PNG next to it)
        got = texfmt.decode_dds(data)[:128, :128].astype(int)
        png = np.asarray(Image.open(os.path.join(os.path.dirname(W.ICON_FILE), 'wickedwhims_icon.png')).convert('RGBA'), int)
        self.assertLess(np.abs(got - png).mean(), 6)
        self.assertEqual(W.ICON_KEY, '2f7d0004:00000000:%016x' % W.ICON_INSTANCE)

    def test_xml_names_the_icon_and_credits_the_author(self):
        anim = {'name': 'Test', 'author': 'Novulon', 'author_display': W.credited('Novulon'), 'icon': W.ICON_KEY,
                'category': 'VAGINAL', 'locations': ['FLOOR'], 'actors': [{'clip': 'c1', 'gender': 'FEMALE'}]}
        root = ET.fromstring(W.snippet_xml('FitStudio_Novulon_Test', [anim]))
        self.assertEqual(_field(root, 'animation_display_icon'), W.ICON_KEY)
        self.assertEqual(_field(root, 'animation_author'), W.credited('Novulon'))
        name, pkg = W.animation_package(anim)
        self.assertEqual(name, 'FitStudio_Novulon_Test.package')                        # the file keeps the plain author
        path = os.path.join(TMP, name)
        with open(path, 'wb') as f:
            f.write(pkg)
        keys = {(e['type'], e['group'], e['inst']) for e in dbpf.read_index(path)}
        self.assertIn((W.T_IMG, 0, W.ICON_INSTANCE), keys)


@unittest.skipUnless(HAS_GAME, NO_GAME)
class Export(unittest.TestCase):
    def test_send_to_game_package(self):
        saved = X.MY_ANIMATIONS
        X.MY_ANIMATIONS = os.path.join(TMP, 'MyAnimations')
        proj = baked_project(with_bed=False)
        try:
            r = X.export(proj)
        finally:
            X.MY_ANIMATIONS = saved
        path = r['path']
        self.assertTrue(path.startswith(TMP), path)
        idx = dbpf.read_index(path)
        # no custom icon: WickedWhims' picker only puts its own check mark on the animation currently playing when
        # the animation names no animation_display_icon (SexAnimationInstance.get_picker_row) - so exports never
        # carry one (the Wicked Animator logo used to be embedded here; the credit stays in the author text instead).
        self.assertEqual([e for e in idx if e['type'] == W.T_IMG], [])
        xml = next(dbpf.read_resource(path, e) for e in idx if e['type'] == W.SNIPPET)
        root = ET.fromstring(xml)
        self.assertIsNone(_field(root, 'animation_display_icon'))
        author = (proj.get('author') or '').strip() or 'Fit Studio'
        self.assertEqual(_field(root, 'animation_author'), W.credited(author))
        self.assertNotIn(W.CREDIT, os.path.basename(path))                             # names keep the plain author
        # the app's own readers get the plain author back
        self.assertEqual(gamedata._parse_animation_xml(xml.decode('utf-8'))[0]['author'], author)
        self.assertEqual(doctor.parse_animation_xml(xml.decode('utf-8'))[0]['author'], author)
        self.assertEqual(wwlists.parse_xml(xml)[0]['author'], author)
        # Roles/Orientation/Duration preview info (Details step): a solo actor with no gender chosen guesses BOTH
        self.assertIn('roles', r)
        self.assertIn('orientation', r)
        self.assertGreaterEqual(r['picker_seconds'], 1)

    def test_a_shared_mod_carries_no_icon(self):
        saved = X.EXPORTS
        X.EXPORTS = os.path.join(TMP, 'Exports')
        a, b = baked_project(with_bed=False, uid='u-credit-a'), baked_project(with_bed=False, uid='u-credit-b')
        b['name'] = (b.get('name') or 'Anim') + ' two'
        try:
            r = X.bundle({'name': 'Credit test', 'author': 'Novulon', 'animations': [a, b], 'include_sounds': False})
        finally:
            X.EXPORTS = saved
        idx = dbpf.read_index(r['package'])
        self.assertEqual(sum(1 for e in idx if e['type'] == W.T_IMG), 0)
        roots = [ET.fromstring(dbpf.read_resource(r['package'], e)) for e in idx if e['type'] == W.SNIPPET]
        self.assertEqual(len(roots), 2)
        self.assertTrue(all(_field(x, 'animation_display_icon') is None for x in roots))
        # each animation keeps its own author (the bundle's 'Novulon' is only the mod's title/README credit)
        self.assertTrue(all(_field(x, 'animation_author') == W.credited(a['author']) for x in roots))


if __name__ == '__main__':
    unittest.main(verbosity=2)
