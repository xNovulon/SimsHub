"""The Wicked Animator logo and credit in WickedWhims' own animation lists.

    python tools/checks/wwcredit/test_credit.py

WickedWhims shows an animation's own picture next to its name when animation_display_icon names a PNG resource
(SexAnimationInstance.get_picker_row), and the author in the line under the name. Every export carries the logo
(one shared PNG key) and "<author> · Made with Novulon's Wicked Animator"; file, stage and clip names keep the plain
author, and the app's own readers (library, Game Doctor, identifier) read the plain author back.
Packages are written into a temp folder only (never the real Mods). The export rows need the game's rig (E:\\The
Sims 4) and are skipped without it.
"""
import io
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

    def test_icon_is_a_128px_png(self):
        from PIL import Image
        t, g, i, data = W.icon_resource()
        self.assertEqual((t, g, i), (W.T_PNG, 0, W.ICON_INSTANCE))
        im = Image.open(io.BytesIO(data))
        self.assertEqual((im.format, im.size, im.mode), ('PNG', (128, 128), 'RGBA'))
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
        self.assertIn((W.T_PNG, 0, W.ICON_INSTANCE), keys)


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
        png = [e for e in idx if e['type'] == W.T_PNG]
        self.assertEqual([(e['group'], e['inst']) for e in png], [(0, W.ICON_INSTANCE)])
        self.assertEqual(dbpf.read_resource(path, png[0])[:8], b'\x89PNG\r\n\x1a\n')
        xml = next(dbpf.read_resource(path, e) for e in idx if e['type'] == W.SNIPPET)
        root = ET.fromstring(xml)
        self.assertEqual(_field(root, 'animation_display_icon'), W.ICON_KEY)
        author = (proj.get('author') or '').strip() or 'Fit Studio'
        self.assertEqual(_field(root, 'animation_author'), W.credited(author))
        self.assertNotIn(W.CREDIT, os.path.basename(path))                             # names keep the plain author
        # the app's own readers get the plain author back
        self.assertEqual(gamedata._parse_animation_xml(xml.decode('utf-8'))[0]['author'], author)
        self.assertEqual(doctor.parse_animation_xml(xml.decode('utf-8'))[0]['author'], author)
        self.assertEqual(wwlists.parse_xml(xml)[0]['author'], author)

    def test_a_shared_mod_holds_the_icon_once(self):
        saved = X.EXPORTS
        X.EXPORTS = os.path.join(TMP, 'Exports')
        a, b = baked_project(with_bed=False, uid='u-credit-a'), baked_project(with_bed=False, uid='u-credit-b')
        b['name'] = (b.get('name') or 'Anim') + ' two'
        try:
            r = X.bundle({'name': 'Credit test', 'author': 'Novulon', 'animations': [a, b], 'include_sounds': False})
        finally:
            X.EXPORTS = saved
        idx = dbpf.read_index(r['package'])
        self.assertEqual(sum(1 for e in idx if e['type'] == W.T_PNG), 1)
        roots = [ET.fromstring(dbpf.read_resource(r['package'], e)) for e in idx if e['type'] == W.SNIPPET]
        self.assertEqual(len(roots), 2)
        self.assertTrue(all(_field(x, 'animation_display_icon') == W.ICON_KEY for x in roots))


if __name__ == '__main__':
    unittest.main(verbosity=2)
