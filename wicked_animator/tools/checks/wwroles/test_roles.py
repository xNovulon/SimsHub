"""Roles / Orientation / Duration - what WickedWhims' own animation picker shows (needs.md: "learn the roles
system... F+M in the tags menu, same with orientation... duration automatically").

    python tools/checks/wwroles/test_roles.py

WickedWhims' picker line ("Category: X | Author: Y / Roles: M+F / Orientation: HE / Duration: 51s") comes straight
from SexAnimationInstance.get_picker_row and get_gender_signature (wickedwhims/sex/animations/animation_instance.pyc)
and get_sex_gender_signature / SexualOrientation.get_signature (wickedwhims/sex/enums/sex_gender.pyc,
sex_orientation.pyc), disassembled from the installed TURBODRIVER_WickedWhims_Scripts.ts4script (v185k). wwpackage.py's
gender_signature/roles_signature/orientation_signature/picker_duration_seconds mirror that read.

'Fallen:InfantDemoAnimations' inside Mods\\!!!!!SpeedKit_Save_00000019_001.package is a real WickedWhims package (not
ours) whose first actor has animation_genders=BOTH and animation_pref_gender=FEMALE - WickedWhims shows that actor as
'B/F' (get_gender_signature's '{}/{}'.format(...) branch, taken because animation_pref_gender differs from
animation_genders). test_matches_a_real_creator_package below checks our own reader gets the same fields out of it.

Packages are written into a temp folder only (never the real Mods). The parts that export for real need the game's
rig (E:\\The Sims 4) and are skipped without it.
"""
import glob
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
BACKEND = os.path.join(ROOT, 'backend')
TMP = tempfile.mkdtemp(prefix='wa_roles_')
os.environ.setdefault('ANIMATOR_SAVES', os.path.join(TMP, 'saves'))
for p in (BACKEND, os.path.join(ROOT, 'tools', 'checks', 'bedanim')):
    if p not in sys.path:
        sys.path.insert(0, p)

import dbpf                                                        # noqa: E402
import exporter as X                                               # noqa: E402
import wwpackage as W                                              # noqa: E402
from test_bed_export import baked_project, HAS_GAME, NO_GAME       # noqa: E402


def _field(root, name):
    el = next((t for t in root.iter('T') if t.get('n') == name), None)
    return el.text if el is not None else None


class GenderSignature(unittest.TestCase):
    """Per-actor 'Roles' letter (SexAnimationActor.get_gender_signature)."""

    def test_plain_letters(self):
        self.assertEqual(W.gender_signature('FEMALE'), 'F')
        self.assertEqual(W.gender_signature('MALE'), 'M')
        self.assertEqual(W.gender_signature('BOTH'), 'B')
        self.assertEqual(W.gender_signature(None), 'B')            # no gender set: judged as BOTH, never blank

    def test_preferred_gender_shows_both_letters(self):
        # a real creator's actor (see module docstring): animation_genders=BOTH, animation_pref_gender=FEMALE
        self.assertEqual(W.gender_signature('BOTH', 'FEMALE'), 'B/F')
        self.assertEqual(W.gender_signature('BOTH', 'MALE'), 'B/M')
        # a plain-gendered actor's own gender always wins when there is no preference, or it matches already
        self.assertEqual(W.gender_signature('MALE', None), 'M')
        self.assertEqual(W.gender_signature('MALE', 'MALE'), 'M')


class RolesSignature(unittest.TestCase):
    def test_two_actors(self):
        self.assertEqual(W.roles_signature([{'gender': 'MALE'}, {'gender': 'FEMALE'}]), 'M+F')

    def test_both_actors_with_preferences(self):
        actors = [{'gender': 'BOTH', 'pref_gender': 'MALE'}, {'gender': 'BOTH', 'pref_gender': 'FEMALE'}]
        self.assertEqual(W.roles_signature(actors), 'B/M+B/F')

    def test_order_is_actor_order(self):
        self.assertEqual(W.roles_signature([{'gender': 'FEMALE'}, {'gender': 'MALE'}]), 'F+M')


class OrientationSignature(unittest.TestCase):
    def test_solo_has_no_orientation(self):
        self.assertEqual(W.orientation_signature([{'gender': 'FEMALE'}]), '-')

    def test_opposite_genders_is_heterosexual(self):
        self.assertEqual(W.orientation_signature([{'gender': 'MALE'}, {'gender': 'FEMALE'}]), 'HE')

    def test_same_gender_is_homosexual(self):
        self.assertEqual(W.orientation_signature([{'gender': 'MALE'}, {'gender': 'MALE'}]), 'HO')
        self.assertEqual(W.orientation_signature([{'gender': 'FEMALE'}, {'gender': 'FEMALE'}]), 'HO')

    def test_both_actor_follows_its_preference(self):
        # a BOTH actor that prefers male counts as male for the orientation guess, like WickedWhims' own signature
        actors = [{'gender': 'BOTH', 'pref_gender': 'MALE'}, {'gender': 'FEMALE'}]
        self.assertEqual(W.orientation_signature(actors), 'HE')

    def test_mixed_group_of_three_is_bisexual(self):
        actors = [{'gender': 'MALE'}, {'gender': 'FEMALE'}, {'gender': 'FEMALE'}]
        self.assertEqual(W.orientation_signature(actors), 'BI')

    def test_all_same_group_of_three_is_homosexual(self):
        actors = [{'gender': 'FEMALE'}, {'gender': 'FEMALE'}, {'gender': 'FEMALE'}]
        self.assertEqual(W.orientation_signature(actors), 'HO')


class DurationSeconds(unittest.TestCase):
    """Duration needs no field of its own: WickedWhims computes it from the clip's own length x animation_loops,
    minus animation_negative_duration_offset (SexAnimationInstance.update_duration), then rounds up to show it."""

    def test_loops_times_length(self):
        self.assertEqual(W.picker_duration_seconds(1.7, 30), 51)   # 1.7s x 30 loops = 51s, matches the owner's example

    def test_negative_offset_is_subtracted(self):
        self.assertEqual(W.picker_duration_seconds(2.0, 1, negative_offset=1.0), 1)

    def test_never_shows_zero_or_negative(self):
        self.assertEqual(W.picker_duration_seconds(1.0, 1, negative_offset=5.0), 1)
        self.assertEqual(W.picker_duration_seconds(0, 1), 1)


class ExportedActors(unittest.TestCase):
    """wwpackage.animation_xml only writes animation_pref_gender next to a BOTH actor (real packages pair it with
    animation_genders=BOTH; a plain MALE/FEMALE actor never gets one written, matching WickedWhims' own convention)."""

    def test_plain_genders_get_no_preference_field(self):
        anim = {'name': 'T', 'author': 'A', 'category': 'VAGINAL', 'locations': ['FLOOR'],
                'actors': [{'clip': 'c1', 'gender': 'MALE'}, {'clip': 'c2', 'gender': 'FEMALE'}]}
        root = ET.fromstring('<r>%s</r>' % W.animation_xml(anim))
        fields = [t.get('n') for t in root.iter('T') if t.get('n') == 'animation_pref_gender']
        self.assertEqual(fields, [])

    def test_both_actor_with_preference_writes_it(self):
        anim = {'name': 'T', 'author': 'A', 'category': 'VAGINAL', 'locations': ['FLOOR'],
                'actors': [{'clip': 'c1', 'gender': 'BOTH', 'pref_gender': 'FEMALE'}]}
        root = ET.fromstring('<r>%s</r>' % W.animation_xml(anim))
        self.assertEqual(_field(root, 'animation_genders'), 'BOTH')
        self.assertEqual(_field(root, 'animation_pref_gender'), 'FEMALE')


class MatchesAnExportedProject(unittest.TestCase):
    """The whole pipeline (Details step's per-sim gender + an explicit "prefers" choice -> exporter.py -> wwpackage.py)
    on a project shaped like what the app actually sends (see web/js/main.js's bake())."""

    def test_two_gendered_actors_show_as_m_plus_f(self):
        proj = baked_project(with_bed=False)   # {'gender': 'FEMALE', ...}, {'gender': 'MALE', ...}
        _res, info = X.animation_resources(proj, metas={})
        self.assertEqual(info['roles'], 'F+M')
        self.assertEqual(info['orientation'], 'HE')

    def test_explicit_prefers_choice_overrides_the_guess_from_body(self):
        proj = baked_project(with_bed=False)
        proj['actors'][0]['gender'] = 'BOTH'
        proj['actors'][0]['prefGender'] = 'MALE'     # the app's new "Prefers" control (Details step)
        _res, info = X.animation_resources(proj, metas={})
        self.assertEqual(info['roles'], 'B/M+M')

    def test_old_project_without_the_new_fields_still_gets_a_guess(self):
        # a project saved before "prefGender" existed: PREF_GENDER-by-body still guesses from the sim's own body
        proj = baked_project(with_bed=False)
        proj['actors'][0]['gender'] = 'BOTH'          # body stays 'yf' -> guessed FEMALE, same as always
        self.assertNotIn('prefGender', proj['actors'][0])
        _res, info = X.animation_resources(proj, metas={})
        self.assertEqual(info['roles'], 'B/F+M')

    def test_no_custom_icon_is_attached(self):
        proj = baked_project(with_bed=False)
        resources, anim_xml_info = X.animation_resources(proj, metas={})
        self.assertFalse(any(t == W.T_IMG for t, _g, _i, _d in resources))
        xml = next(d for t, _g, _i, d in resources if t == W.SNIPPET)
        root = ET.fromstring(xml)
        self.assertIsNone(_field(root, 'animation_display_icon'))


@unittest.skipUnless(HAS_GAME, NO_GAME)
class RealCreatorPackage(unittest.TestCase):
    """Cross-checked against a real, unmodified WickedWhims package from another creator, found read-only under the
    Mods folder (never edited or copied out): 'Fallen:InfantDemoAnimations' in
    Mods\\!!!!!SpeedKit_Save_00000019_001.package. See the module docstring for why 'B/F' is correct."""

    def test_matches_a_real_creator_package(self):
        import gamedata as G
        mods = G.MODS_DIR
        candidates = glob.glob(os.path.join(mods, '**', '*.package'), recursive=True) if os.path.isdir(mods) else []
        found = None
        for path in candidates:
            try:
                idx = dbpf.read_index(path)
            except Exception:
                continue
            for e in idx:
                if e.get('type') != 0x7DF2169C:
                    continue
                try:
                    data = dbpf.read_resource(path, e)
                except Exception:
                    continue
                if b'Fallen:InfantDemoAnimations' in data:
                    found = data
                    break
            if found:
                break
        if not found:
            self.skipTest('the real creator package used for this check is not installed here')
        root = ET.fromstring(found)
        actors = [a for a in root.iter('U') if _field(a, 'animation_clip_name')]
        first = actors[0]
        self.assertEqual(_field(first, 'animation_genders'), 'BOTH')
        self.assertEqual(_field(first, 'animation_pref_gender'), 'FEMALE')
        self.assertEqual(W.gender_signature(_field(first, 'animation_genders'), _field(first, 'animation_pref_gender')),
                         'B/F')


if __name__ == '__main__':
    unittest.main(verbosity=2)
