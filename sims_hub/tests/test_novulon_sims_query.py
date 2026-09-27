"""Tier-1 pure-Python tests for ingame/novulon/sims/query.py (SPEC.md Sec 16 Tier 1: "sims.query.
matches/filtered/sorted_for_display as plain-Python unit tests"). No game import anywhere in this
file or in query.py itself - `tests/novulon_fakes.FakeSimInfo` plus the real game's own verified
Gender/Age/Species/OccultType bit VALUES (copied here as plain ints, the same convention
novulon_fakes.py's own docstring describes: "the real game's own ... values, copied over from
whatever the package under test imports at runtime" - the actual values are re-verified against this
machine's install in tools/novulon_api_manifest/bp4_sims_browser.py, not re-checked here)."""
import os
import sys
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon.sims import query  # noqa: E402
from tests.novulon_fakes import FakeSimInfo, FakeHousehold  # noqa: E402

# Real, verified values (tools/novulon_api_manifest/bp4_sims_browser.py) - copied here as plain ints
# so this file never imports the game.
MALE, FEMALE = 4096, 8192
BABY, TODDLER, CHILD, TEEN, YOUNGADULT, ADULT, ELDER, INFANT = 1, 2, 4, 8, 16, 32, 64, 128
SP_HUMAN, SP_DOG, SP_CAT, SP_FOX, SP_HORSE = 1, 2, 3, 5, 6
OC_HUMAN, OC_ALIEN, OC_VAMPIRE, OC_MERMAID, OC_WITCH, OC_WEREWOLF, OC_FAIRY = 1, 2, 4, 8, 16, 32, 64

AGE_PAIRS = [(YOUNGADULT, 'Young Adult'), (ADULT, 'Adult'), (ELDER, 'Elder'), (TEEN, 'Teen')]
OCCULT_PAIRS = [(OC_VAMPIRE, 'Vampire'), (OC_WITCH, 'Spellcaster'), (OC_ALIEN, 'Alien')]
SPECIES_PAIRS = [(SP_HUMAN, 'Human'), (SP_DOG, 'Dog'), (SP_CAT, 'Cat')]


def sim(**kw):
    kw.setdefault('gender', FEMALE)
    kw.setdefault('age', YOUNGADULT)
    kw.setdefault('species', SP_HUMAN)
    return FakeSimInfo(**kw)


class TestMatches(unittest.TestCase):
    def test_empty_filters_matches_everyone(self):
        self.assertTrue(query.matches(sim(), {}))
        self.assertTrue(query.matches(sim(), None))

    def test_gender_filter(self):
        m = sim(gender=MALE)
        f = sim(gender=FEMALE)
        self.assertTrue(query.matches(m, {'gender': MALE}))
        self.assertFalse(query.matches(f, {'gender': MALE}))

    def test_species_ne_excludes_that_species_only(self):
        human = sim(species=SP_HUMAN)
        dog = sim(species=SP_DOG)
        self.assertFalse(query.matches(human, {'species_ne': SP_HUMAN}))
        self.assertTrue(query.matches(dog, {'species_ne': SP_HUMAN}))

    def test_life_stage_any_bit_matches(self):
        elder = sim(age=ELDER)
        child = sim(age=CHILD)
        self.assertTrue(query.matches(elder, {'life_stages': {YOUNGADULT, ELDER}}))
        self.assertFalse(query.matches(child, {'life_stages': {YOUNGADULT, ELDER}}))

    def test_occult_any_bit_matches(self):
        vamp = sim(occult_types=OC_VAMPIRE)
        human = sim(occult_types=OC_HUMAN)
        self.assertTrue(query.matches(vamp, {'occults': {OC_VAMPIRE, OC_WITCH}}))
        self.assertFalse(query.matches(human, {'occults': {OC_VAMPIRE, OC_WITCH}}))

    def test_household_id_filter(self):
        s = sim(household=FakeHousehold(7))
        self.assertTrue(query.matches(s, {'household_id': 7}))
        self.assertFalse(query.matches(s, {'household_id': 8}))

    def test_here_filter_requires_instanced(self):
        here = sim(instanced=True)
        away = sim(instanced=False)
        self.assertTrue(query.matches(here, {'here': True}))
        self.assertFalse(query.matches(away, {'here': True}))

    def test_played_vs_npc_are_exclusive_constraints(self):
        active_hh = FakeHousehold(1)
        other_hh = FakeHousehold(2)
        played_sim = sim(household=active_hh)
        npc_sim = sim(household=other_hh)
        self.assertTrue(query.matches(played_sim, {'played': True}, active_household_id=1))
        self.assertFalse(query.matches(npc_sim, {'played': True}, active_household_id=1))
        self.assertTrue(query.matches(npc_sim, {'npc': True}, active_household_id=1))
        self.assertFalse(query.matches(played_sim, {'npc': True}, active_household_id=1))

    def test_played_and_npc_both_checked_applies_no_constraint(self):
        s1 = sim(household=FakeHousehold(1))
        s2 = sim(household=FakeHousehold(2))
        filters = {'played': True, 'npc': True}
        self.assertTrue(query.matches(s1, filters, active_household_id=1))
        self.assertTrue(query.matches(s2, filters, active_household_id=1))

    def test_filters_combine_with_and(self):
        target = sim(gender=FEMALE, age=ELDER, species=SP_HUMAN)
        wrong_age = sim(gender=FEMALE, age=CHILD, species=SP_HUMAN)
        filters = {'gender': FEMALE, 'life_stages': {ELDER}}
        self.assertTrue(query.matches(target, filters))
        self.assertFalse(query.matches(wrong_age, filters))


class TestIsNpc(unittest.TestCase):
    def test_none_active_household_means_never_npc(self):
        s = sim(household=FakeHousehold(5))
        self.assertFalse(query.is_npc(s, None))

    def test_matches_active_household_id(self):
        s = sim(household=FakeHousehold(5))
        self.assertFalse(query.is_npc(s, 5))
        self.assertTrue(query.is_npc(s, 6))


class TestFilteredAndSorted(unittest.TestCase):
    def test_filtered_keeps_only_matches(self):
        a = sim(gender=MALE)
        b = sim(gender=FEMALE)
        self.assertEqual(query.filtered([a, b], {'gender': MALE}), [a])

    def test_sorted_for_display_is_last_then_first_name(self):
        a = sim(first_name='Bob', last_name='Zed')
        b = sim(first_name='Amy', last_name='Ant')
        c = sim(first_name='Amy', last_name='Ant')  # tie broken by id (insertion order)
        ordered = query.sorted_for_display([a, b, c])
        self.assertEqual([s.full_name for s in ordered], ['Amy Ant', 'Amy Ant', 'Bob Zed'])
        self.assertEqual(ordered[0], b)  # b was created before c, so b sorts first on the tie

    def test_sorted_for_display_is_stable_and_pure(self):
        sims = [sim(first_name='Z'), sim(first_name='A')]
        query.sorted_for_display(sims)
        self.assertEqual([s.first_name for s in sims], ['Z', 'A'])  # input list untouched


class TestCounts(unittest.TestCase):
    def test_counts_all_categories(self):
        sims = [sim(gender=MALE, species=SP_HUMAN), sim(gender=FEMALE, species=SP_HUMAN),
                 sim(gender=FEMALE, species=SP_DOG)]
        c = query.counts(sims, MALE, FEMALE, SP_HUMAN)
        self.assertEqual(c, {'males': 1, 'females': 2, 'pets': 1, 'all': 3})

    def test_counts_empty_list(self):
        self.assertEqual(query.counts([], MALE, FEMALE, SP_HUMAN),
                          {'males': 0, 'females': 0, 'pets': 0, 'all': 0})


class TestLabelHelpers(unittest.TestCase):
    def test_first_bit_label_returns_first_match(self):
        self.assertEqual(query.first_bit_label(ELDER, AGE_PAIRS), 'Elder')
        self.assertIsNone(query.first_bit_label(CHILD, AGE_PAIRS))
        self.assertIsNone(query.first_bit_label(ELDER, []))

    def test_first_equal_label_uses_equality_not_bits(self):
        # SP_HUMAN=1 and OC_VAMPIRE-style bit tests would wrongly match with `&` - equality must not
        self.assertEqual(query.first_equal_label(SP_DOG, SPECIES_PAIRS), 'Dog')
        self.assertIsNone(query.first_equal_label(99, SPECIES_PAIRS))


class TestBadgesFor(unittest.TestCase):
    def test_occult_then_life_stage_then_status(self):
        s = sim(age=ELDER, occult_types=OC_VAMPIRE, instanced=True)
        badges = query.badges_for(s, AGE_PAIRS, OCCULT_PAIRS, active_household_id=None, cap=3)
        self.assertEqual(badges, ['Vampire', 'Elder', 'Here'])

    def test_pregnant_badge_uses_is_pregnant_method(self):
        class PregnantSim(FakeSimInfo):
            def is_pregnant(self):
                return True
        s = PregnantSim(age=YOUNGADULT)
        badges = query.badges_for(s, AGE_PAIRS, [], active_household_id=None, cap=3)
        self.assertIn('Pregnant', badges)

    def test_cap_limits_badge_count(self):
        s = sim(age=ELDER, occult_types=OC_VAMPIRE, instanced=True)
        badges = query.badges_for(s, AGE_PAIRS, OCCULT_PAIRS, active_household_id=None, cap=1)
        self.assertEqual(badges, ['Vampire'])

    def test_npc_badge_when_not_active_household(self):
        s = sim(age=YOUNGADULT, household=FakeHousehold(9))
        badges = query.badges_for(s, AGE_PAIRS, [], active_household_id=1, cap=3)
        self.assertIn('NPC', badges)

    def test_missing_methods_never_raise(self):
        class Bare(object):
            age = ELDER
            occult_types = 0
        badges = query.badges_for(Bare(), AGE_PAIRS, OCCULT_PAIRS, active_household_id=None)
        self.assertEqual(badges, ['Elder', 'Played'])


class TestSubtitleFor(unittest.TestCase):
    def test_full_subtitle_line(self):
        s = sim(age=YOUNGADULT, species=SP_HUMAN)
        text = query.subtitle_for(s, AGE_PAIRS, SPECIES_PAIRS, household_name='Willow Creek')
        self.assertEqual(text, 'Young Adult • Human • Willow Creek')

    def test_missing_household_name_omitted(self):
        s = sim(age=YOUNGADULT, species=SP_HUMAN)
        text = query.subtitle_for(s, AGE_PAIRS, SPECIES_PAIRS, household_name=None)
        self.assertEqual(text, 'Young Adult • Human')


class TestActiveFilterLabels(unittest.TestCase):
    def test_labels_reflect_active_filters_only(self):
        filters = {'gender': FEMALE, 'life_stages': {YOUNGADULT}, 'occults': {OC_VAMPIRE},
                    'played': True}
        labels = query.active_filter_labels(filters, AGE_PAIRS, OCCULT_PAIRS,
                                              gender_labels={MALE: 'Male', FEMALE: 'Female'})
        self.assertEqual(labels, ['Female', 'Young Adult', 'Vampire', 'Played'])

    def test_no_filters_gives_empty_labels(self):
        self.assertEqual(query.active_filter_labels({}, AGE_PAIRS, OCCULT_PAIRS), [])

    def test_pets_label_from_species_ne(self):
        labels = query.active_filter_labels({'species_ne': SP_HUMAN}, [], [])
        self.assertEqual(labels, ['Pets'])


class TestHasAnyFilter(unittest.TestCase):
    def test_empty_is_false(self):
        self.assertFalse(query.has_any_filter({}))
        self.assertFalse(query.has_any_filter(None))

    def test_any_single_key_is_true(self):
        self.assertTrue(query.has_any_filter({'gender': MALE}))
        self.assertTrue(query.has_any_filter({'species_ne': SP_HUMAN}))
        self.assertTrue(query.has_any_filter({'life_stages': {ELDER}}))
        self.assertTrue(query.has_any_filter({'occults': {OC_VAMPIRE}}))
        self.assertTrue(query.has_any_filter({'household_id': 3}))
        self.assertTrue(query.has_any_filter({'played': True}))
        self.assertTrue(query.has_any_filter({'npc': True}))
        self.assertTrue(query.has_any_filter({'here': True}))

    def test_false_booleans_do_not_count(self):
        self.assertFalse(query.has_any_filter({'played': False, 'npc': False, 'here': False}))


if __name__ == '__main__':
    unittest.main(verbosity=1)
