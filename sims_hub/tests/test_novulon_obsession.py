"""Novulon's Obsession switch (ingame/novulon/obsession.py and its page on a Sim's own page), played through the
stand-in game (tests/novulon_game.py). No game needed.

    python -m unittest tests.test_novulon_obsession

Who falls for the Sim (adults attracted to their gender, never family, never teens), the two levels (romance rising
every check vs at the top at once), turn-ons and turn-offs not counting (Lovestruck's attraction kept at the top,
also after the game works it out again), jealousy at the extreme level, the Enamored sentiment, the alarm, and Off.
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


class LootRecorder:
    applied = []

    @classmethod
    def apply_to_resolver(cls, resolver, skip_test=False):
        cls.applied.append((resolver.actor.id, resolver.target.id))


class ObsessionTest(unittest.TestCase):
    def setUp(self):
        self.game = g = G.install()
        home = g.add_household('Doe')
        self.adam = g.add_sim('Adam', 'Doe', age=32, gender='MALE', household=home, npc=False, here=True, active=True)
        self.eve = g.add_sim('Eve', 'Doe', age=32, household=home, npc=False, here=True)           # family
        self.bella = g.add_sim('Bella', 'Goth', age=32, household=g.add_household('Goth'), here=True)
        self.cara = g.add_sim('Cara', 'Lane', age=32, household=g.add_household('Lane'), here=True)  # into women
        self.dana = g.add_sim('Dana', 'Lane', age=8, household=self.cara.household, here=True)     # a teen
        self.finn = g.add_sim('Finn', 'Ray', age=64, gender='MALE', household=g.add_household('Ray'), here=True)
        self.gina = g.add_sim('Gina', 'Far', age=16, household=g.add_household('Far'))              # not on the lot
        for si in (self.eve, self.bella, self.dana, self.finn, self.gina):
            si.attracted = {'MALE'}
        self.cara.attracted = {'FEMALE'}
        self.adam.attracted = {'FEMALE'}
        self.adam.family.add(self.eve.id)
        self.eve.family.add(self.adam.id)
        self.jealous = G.tuning('Buff_Jealousy_LoveInterest', visible=True)
        g.manager(g.Types.BUFF).classes.append(self.jealous)
        LootRecorder.applied = []
        loot = type('loot_Sentiment_AddSentiment_Enamored_generic_LT', (LootRecorder,), {})
        g.manager(g.Types.ACTION).classes.append(loot)
        mod = __import__('novulon', fromlist=['obsession', 'entry', 'ui', 'settings'])
        self.o, self.entry, self.ui, self.settings = mod.obsession, mod.entry, mod.ui, mod.settings
        self.settings._values['obsession'] = {}
        self.o._alarm = None
        self.o._enamored.clear()
        self.o._tuning.clear()
        self.entry._registered = False
        self.entry.register_commands()
        self.ui.reset_all()
        self.errors = []
        common = sys.modules['novulon.common']
        self.addCleanup(setattr, common, 'log_exception', common.log_exception)
        common.log_exception = lambda where: self.errors.append((where, traceback.format_exc()))

    def tearDown(self):
        errors, self.errors = self.errors, []
        G.uninstall()
        self.assertEqual(errors, [])

    def romance(self, si):
        return self.game.score(si, self.adam, self.game.tracks[1])

    def friendship(self, a, b):
        return self.game.score(a, b, self.game.tracks[0])

    def attraction(self, si):
        return self.game.score(si, self.adam, self.game.attraction_track)

    def note(self):
        return G.text_of(self.game.notifications[-1].kw['text'])

    def open_obsession(self, si):
        self.game.commands['novulon.sim'](si.id, _connection=7)
        self.game.screen.pick('Obsession')
        return self.game.screen

    # ---------------------------------------------------------------- the page
    def test_adults_have_the_row_and_teens_dont(self):
        self.game.commands['novulon.sim'](self.adam.id, _connection=7)
        self.assertEqual(self.game.screen.row('Obsession').desc, 'Off')
        self.game.commands['novulon.sim'](self.dana.id, _connection=7)
        self.assertNotIn('Obsession', self.game.screen.labels())

    def test_turning_it_on_from_the_page(self):
        page = self.open_obsession(self.adam)
        self.assertEqual(page.labels(), ['Back', 'Off', 'Obsessed', 'Extremely obsessed'])
        page.pick('Obsessed')
        self.assertEqual(self.o.level(self.adam), self.o.OBSESSED)
        self.assertIn('falls for them', self.note())
        self.assertEqual(self.settings.get('obsession'), {str(self.adam.id): 1})
        self.game.commands['novulon.sim'](self.adam.id, _connection=7)
        self.assertEqual(self.game.screen.row('Obsession').desc, 'Obsessed')

    def test_a_teen_can_never_be_the_one_everyone_falls_for(self):
        self.assertEqual(self.o.set_level(self.dana, self.o.EXTREME), (False, 'Only for young adult and older Sims.'))
        self.assertEqual(self.settings.get('obsession'), {})

    # ---------------------------------------------------------------- who falls for them
    def test_only_adults_attracted_to_his_gender_who_arent_family(self):
        self.o.set_level(self.adam, self.o.OBSESSED)
        self.assertEqual(self.romance(self.bella), 10)       # into men: falls for him
        self.assertEqual(self.romance(self.finn), 10)        # an elder man into men: too
        self.assertEqual(self.romance(self.cara), 0)         # into women only
        self.assertEqual(self.romance(self.dana), 0)         # a teen: never
        self.assertEqual(self.romance(self.eve), 0)          # family: never
        self.assertEqual(self.romance(self.gina), 0)         # not on the lot (yet)
        self.assertFalse(self.o.is_fan(self.adam, self.adam))

    def test_obsessed_rises_every_check_up_to_full(self):
        self.o.set_level(self.adam, self.o.OBSESSED)
        alarm = self.game.alarms[-1]
        self.assertEqual((alarm.minutes, alarm.repeating), (self.o.CHECK_MINUTES, True))
        self.assertEqual((self.romance(self.bella), self.friendship(self.bella, self.adam)), (10, 5))
        for _ in range(3):
            alarm.fire()
        self.assertEqual((self.romance(self.bella), self.friendship(self.bella, self.adam)), (40, 20))
        for _ in range(20):
            alarm.fire()
        self.assertEqual((self.romance(self.bella), self.friendship(self.bella, self.adam)), (100, 100))
        self.assertEqual(len(self.game.alarms), 1)          # one alarm, however often it was switched on

    def test_extreme_is_full_at_once(self):
        worked, message = self.o.set_level(self.adam, self.o.EXTREME)
        self.assertEqual((self.romance(self.bella), self.friendship(self.bella, self.adam)), (100, 100))
        self.assertTrue(worked)
        self.assertIn('madly in love', message)

    def test_never_lowers_what_is_already_there(self):
        rs = sys.modules['services'].relationship_service()
        rs.set_relationship_score(self.bella.id, self.adam.id, 95, self.game.tracks[1])
        self.o.set_level(self.adam, self.o.OBSESSED)
        self.assertEqual(self.romance(self.bella), 100)

    def test_enamored_once_per_fan_per_lot(self):
        self.o.set_level(self.adam, self.o.OBSESSED)
        for _ in range(4):
            self.game.alarms[-1].fire()
        self.assertEqual(sorted(LootRecorder.applied), sorted([(self.bella.id, self.adam.id), (self.finn.id, self.adam.id)]))

    # ---------------------------------------------------------------- turn-ons and turn-offs
    def test_attraction_is_perfect_and_stays_perfect(self):
        self.o.set_level(self.adam, self.o.OBSESSED)
        self.assertEqual(self.attraction(self.bella), 100)
        # the game works attraction out again from her turn-offs: it goes straight back to the top
        self.game.attraction_service.refresh_attraction(self.bella.id, self.adam.id)
        self.assertEqual(self.attraction(self.bella), 100)
        # someone not into men keeps what the game worked out
        self.game.attraction_service.refresh_attraction(self.cara.id, self.adam.id)
        self.assertEqual(self.attraction(self.cara), -40)
        # a fan who arrives later is perfect too as soon as the game looks at her attraction
        self.game.attraction_service.refresh_attraction(self.gina.id, self.adam.id)
        self.assertEqual(self.attraction(self.gina), 100)

    def test_without_lovestruck_the_rest_still_works(self):
        self.game.attraction_service = None
        self.o.set_level(self.adam, self.o.EXTREME)
        self.assertEqual(self.attraction(self.bella), 0)
        self.assertEqual(self.romance(self.bella), 100)

    # ---------------------------------------------------------------- jealousy
    def test_extreme_fans_are_jealous_of_anyone_he_talks_to(self):
        self.o.set_level(self.adam, self.o.EXTREME)
        self.game.talk(self.adam, self.cara)
        self.game.alarms[-1].fire()
        for fan in (self.bella, self.finn):
            self.assertIn(self.jealous, fan.get_sim_instance().buffs)
            self.assertEqual(self.friendship(fan, self.cara), -self.o.RIVAL_STEP)
        self.assertNotIn(self.jealous, self.cara.get_sim_instance().buffs)
        self.game.alarms[-1].fire()
        self.assertEqual(self.bella.get_sim_instance().buffs.count(self.jealous), 1)
        self.assertEqual(self.friendship(self.bella, self.cara), -2 * self.o.RIVAL_STEP)

    def test_the_one_he_talks_to_isnt_jealous_of_herself(self):
        self.o.set_level(self.adam, self.o.EXTREME)
        self.game.talk(self.adam, self.bella)
        self.game.alarms[-1].fire()
        self.assertNotIn(self.jealous, self.bella.get_sim_instance().buffs)
        self.assertIn(self.jealous, self.finn.get_sim_instance().buffs)
        self.assertEqual(self.friendship(self.finn, self.bella), -self.o.RIVAL_STEP)

    def test_obsessed_alone_is_not_jealous(self):
        self.o.set_level(self.adam, self.o.OBSESSED)
        self.game.talk(self.adam, self.cara)
        self.game.alarms[-1].fire()
        self.assertNotIn(self.jealous, self.bella.get_sim_instance().buffs)

    # ---------------------------------------------------------------- off, and a new lot
    def test_off_stops_it(self):
        self.o.set_level(self.adam, self.o.OBSESSED)
        self.assertEqual(self.o.set_level(self.adam, self.o.OFF), (True, 'No one is obsessed with Adam now.'))
        before = self.romance(self.bella)
        self.game.alarms[-1].fire()
        self.assertEqual(self.romance(self.bella), before)
        self.game.attraction_service.refresh_attraction(self.bella.id, self.adam.id)
        self.assertEqual(self.attraction(self.bella), -40)

    def test_a_new_lot_starts_a_fresh_check(self):
        self.o.install()
        self.settings._values['obsession'] = {str(self.adam.id): self.o.EXTREME}
        self.game.Zone().on_loading_screen_animation_finished()
        self.assertEqual(len(self.game.alarms), 1)
        self.assertEqual(self.romance(self.bella), 100)
        self.game.Zone().on_loading_screen_animation_finished()
        self.assertEqual(len(self.game.alarms), 2)          # the old lot's alarm went with the old lot

    def test_a_new_lot_with_no_switch_on_does_nothing(self):
        self.o.install()
        self.game.Zone().on_loading_screen_animation_finished()
        self.assertEqual(self.game.alarms, [])


if __name__ == '__main__':
    unittest.main()
