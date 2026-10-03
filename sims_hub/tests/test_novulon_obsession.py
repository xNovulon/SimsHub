"""Novulon's Obsession switch (ingame/novulon/obsession.py and its page on a Sim's own page), played through the
stand-in game (tests/novulon_game.py). No game needed.

    python -m unittest tests.test_novulon_obsession

Who is obsessed (adults attracted to the Sim's gender, never family, never teens), that nothing between them changes
but the fans' own one-way attraction (turn-ons and turn-offs stop counting, also after the game works it out again),
chasing, jealousy at whoever the Sim talks to, fights between fans, Sims the player plays never being pushed, the
alarm, and Off.
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


class ObsessionTest(unittest.TestCase):
    def setUp(self):
        self.game = g = G.install()
        self.home = home = g.add_household('Doe')
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
        mod = __import__('novulon', fromlist=['obsession', 'entry', 'ui', 'settings'])
        self.o, self.entry, self.ui, self.settings = mod.obsession, mod.entry, mod.ui, mod.settings
        for name in (self.o.CHAT, self.o.FIGHT) + self.o.FLIRTS + self.o.CONFRONTS:
            g.manager(g.Types.INTERACTION).classes.append(G.tuning(name))
        self.settings._values['obsession'] = {}
        self.o._alarm = None
        self.o._tuning.clear()
        self.o._roll = lambda: 0.0                   # every chance comes up
        self.o._pick = lambda seq: list(seq)[0]
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

    def attraction(self, si, of=None):
        return self.game.score(si, of or self.adam, self.game.attraction_track)

    def pushes(self):
        """[(who, to whom, mixer)] pushed so far, by first name."""
        return [(p[0].sim_info.first_name, p[1].sim_info.first_name, p[2]) for p in self.game.pushes]

    def jealous_ones(self):
        return sorted(si.first_name for si in self.game.sims.values()
                      if si.get_sim_instance() is not None and self.jealous in si.get_sim_instance().buffs)

    def open_sim(self, si):
        self.game.commands['novulon.sim'](si.id, _connection=7)
        return self.game.screen

    # ---------------------------------------------------------------- the page
    def test_adults_have_the_row_and_teens_dont(self):
        self.assertEqual(self.open_sim(self.adam).row('Obsession').desc, 'Off')
        self.assertNotIn('Obsession', self.open_sim(self.dana).labels())

    def test_turning_it_on_from_the_page(self):
        self.open_sim(self.adam).pick('Obsession')
        page = self.game.screen
        self.assertEqual(page.labels(), ['Back', 'Off', 'Obsessed', 'Extremely obsessed'])
        page.pick('Obsessed')
        self.assertEqual(self.o.level(self.adam), self.o.OBSESSED)
        self.assertEqual(G.text_of(self.game.notifications[-1].kw['text']), 'Everyone into Adam\'s gender is obsessed with them.')
        self.assertEqual(self.settings.get('obsession'), {str(self.adam.id): 1})
        self.assertEqual(self.open_sim(self.adam).row('Obsession').desc, 'Obsessed')

    def test_a_teen_can_never_be_the_one_they_are_obsessed_with(self):
        self.assertEqual(self.o.set_level(self.dana, self.o.EXTREME), (False, 'Only for young adult and older Sims.'))
        self.assertEqual(self.settings.get('obsession'), {})

    # ---------------------------------------------------------------- strangers stay strangers
    def test_nothing_between_them_changes_but_the_fans_own_attraction(self):
        self.o.set_level(self.adam, self.o.EXTREME)
        self.game.talk(self.adam, self.cara)
        for _ in range(5):
            self.game.alarms[-1].fire()
        tracks = {key[2] for key in self.game.rel}
        self.assertEqual(tracks, {self.game.attraction_track})          # no friendship, no romance
        self.assertEqual(sorted((a, b) for a, b, _ in self.game.rel),
                         sorted([(self.bella.id, self.adam.id), (self.finn.id, self.adam.id)]))   # fan -> Adam only

    # ---------------------------------------------------------------- who is obsessed
    def test_only_adults_attracted_to_his_gender_who_arent_family(self):
        self.o.set_level(self.adam, self.o.OBSESSED)
        self.assertEqual(self.attraction(self.bella), 100)
        self.assertEqual(self.attraction(self.finn), 100)        # an elder man into men
        for si in (self.cara, self.dana, self.eve, self.gina):     # into women / a teen / family / not here
            self.assertEqual(self.attraction(si), 0)
        self.assertFalse(self.o.is_fan(self.adam, self.adam))

    def test_attraction_stays_perfect_and_his_own_is_left_alone(self):
        self.o.set_level(self.adam, self.o.OBSESSED)
        self.game.attraction_service.refresh_attraction(self.bella.id, self.adam.id)     # her turn-offs, worked out
        self.assertEqual(self.attraction(self.bella), 100)
        self.game.attraction_service.refresh_attraction(self.adam.id, self.bella.id)     # his to her: the game's
        self.assertEqual(self.attraction(self.adam, of=self.bella), -40)
        self.game.attraction_service.refresh_attraction(self.cara.id, self.adam.id)      # not into men
        self.assertEqual(self.attraction(self.cara), -40)
        self.game.attraction_service.refresh_attraction(self.gina.id, self.adam.id)      # a fan arriving later
        self.assertEqual(self.attraction(self.gina), 100)

    def test_without_lovestruck_they_still_chase(self):
        self.game.attraction_service = None
        self.o.set_level(self.adam, self.o.OBSESSED)
        self.assertEqual(self.game.rel, {})
        self.assertIn(('Bella', 'Adam', self.o.FLIRTS[0]), self.pushes())

    # ---------------------------------------------------------------- chasing
    def test_obsessed_fans_come_after_him_sometimes(self):
        self.o.set_level(self.adam, self.o.OBSESSED)
        self.assertEqual(sorted(self.pushes()), [('Bella', 'Adam', self.o.FLIRTS[0]), ('Finn', 'Adam', self.o.FLIRTS[0])])
        p = self.game.pushes[0]
        self.assertEqual((p[3], p[4], p[5]), ('sim_Chat', True, 'Low'))     # under a new chat, low priority
        self.game.pushes.clear()
        self.o._roll = lambda: 0.9                                           # above the 35% chance
        self.game.alarms[-1].fire()
        self.assertEqual(self.game.pushes, [])

    def test_extreme_fans_chase_him_every_check(self):
        self.o._roll = lambda: 0.9
        self.o.set_level(self.adam, self.o.EXTREME)
        self.assertEqual(sorted(self.pushes()), [('Bella', 'Adam', self.o.FLIRTS[0]), ('Finn', 'Adam', self.o.FLIRTS[0])])
        self.assertEqual(self.game.pushes[0][5], 'High')

    def test_a_fan_already_with_him_isnt_sent_again_and_a_running_chat_is_used(self):
        self.game.talk(self.adam, self.bella)
        chat = self.o._named(self.game.Types.INTERACTION, self.o.CHAT)
        self.game.running[self.finn.get_sim_instance().id] = [type('SI', (), {'affordance': chat})()]
        self.o.set_level(self.adam, self.o.OBSESSED)
        self.assertNotIn('Bella', [w for w, _, _ in self.pushes()])
        finn = [p for p in self.game.pushes if p[0].sim_info is self.finn]
        self.assertEqual(finn[0][4], False)                                  # the chat Finn is in, not a new one

    def test_sims_the_player_plays_are_never_pushed(self):
        self.game.selectable.append(self.bella)
        self.o.set_level(self.adam, self.o.EXTREME)
        self.assertNotIn('Bella', [w for w, _, _ in self.pushes()])
        self.assertEqual(self.attraction(self.bella), 100)                  # she is still obsessed

    # ---------------------------------------------------------------- jealousy
    def test_obsessed_fans_are_jealous_but_stay_put(self):
        self.o.set_level(self.adam, self.o.OBSESSED)
        self.game.pushes.clear()
        self.game.talk(self.adam, self.cara)
        self.game.alarms[-1].fire()
        self.assertEqual(self.jealous_ones(), ['Bella', 'Finn'])
        self.assertNotIn(self.o.CONFRONTS[0], [m for _, _, m in self.pushes()])

    def test_extreme_fans_storm_over_to_whoever_he_talks_to(self):
        self.o._roll = lambda: 0.5                                           # confronts (60%), no fight (12%)
        self.o.set_level(self.adam, self.o.EXTREME)
        self.game.pushes.clear()                                           # confronts (60%), no fight (12%)
        self.game.talk(self.adam, self.cara)
        self.game.alarms[-1].fire()
        self.assertEqual(sorted(self.pushes()), [('Bella', 'Cara', self.o.CONFRONTS[0]), ('Finn', 'Cara', self.o.CONFRONTS[0])])
        self.assertEqual(self.jealous_ones(), ['Bella', 'Finn'])

    def test_the_one_he_talks_to_isnt_jealous_of_herself(self):
        self.o._roll = lambda: 0.5                                           # confronts (60%), no fight (12%)
        self.o.set_level(self.adam, self.o.EXTREME)
        self.game.pushes.clear()
        self.game.talk(self.adam, self.bella)
        self.game.alarms[-1].fire()
        self.assertEqual(self.jealous_ones(), ['Finn'])
        self.assertEqual(self.pushes(), [('Finn', 'Bella', self.o.CONFRONTS[0])])

    # ---------------------------------------------------------------- fights
    def test_two_fans_now_and_then_fight_over_him(self):
        self.o.set_level(self.adam, self.o.EXTREME)
        self.assertIn(('Bella', 'Finn', self.o.FIGHT), self.pushes())
        self.assertEqual(self.jealous_ones(), ['Bella', 'Finn'])

    def test_when_the_game_wont_let_them_fight_they_yell(self):
        self.game.refuse.add(self.o.FIGHT)
        self.o.set_level(self.adam, self.o.EXTREME)
        self.assertIn(('Bella', 'Finn', self.o.CONFRONTS[0]), self.pushes())

    def test_fights_are_rare(self):
        self.o._roll = lambda: 0.5
        self.o.set_level(self.adam, self.o.EXTREME)
        self.assertNotIn(self.o.FIGHT, [m for _, _, m in self.pushes()])

    def test_a_fight_needs_two_fans_the_player_doesnt_play(self):
        self.game.selectable.append(self.finn)
        self.o.set_level(self.adam, self.o.EXTREME)
        self.assertNotIn(self.o.FIGHT, [m for _, _, m in self.pushes()])

    # ---------------------------------------------------------------- off, and a new lot
    def test_off_stops_everything(self):
        self.o.set_level(self.adam, self.o.EXTREME)
        self.assertEqual(self.o.set_level(self.adam, self.o.OFF), (True, 'No one is obsessed with Adam now.'))
        self.game.pushes.clear()
        for si in self.game.sims.values():
            if si.get_sim_instance():
                si.get_sim_instance().buffs.clear()
        self.game.talk(self.adam, self.cara)
        self.game.alarms[-1].fire()
        self.assertEqual((self.game.pushes, self.jealous_ones()), ([], []))
        self.game.attraction_service.refresh_attraction(self.bella.id, self.adam.id)
        self.assertEqual(self.attraction(self.bella), -40)

    def test_a_new_lot_starts_a_fresh_check(self):
        self.o.install()
        self.settings._values['obsession'] = {str(self.adam.id): self.o.EXTREME}
        self.game.Zone().on_loading_screen_animation_finished()
        self.assertEqual(len(self.game.alarms), 1)
        self.assertEqual(self.attraction(self.bella), 100)
        self.game.Zone().on_loading_screen_animation_finished()
        self.assertEqual(len(self.game.alarms), 2)          # the old lot's alarm went with the old lot

    def test_a_new_lot_with_no_switch_on_does_nothing(self):
        self.o.install()
        self.game.Zone().on_loading_screen_animation_finished()
        self.assertEqual(self.game.alarms, [])


if __name__ == '__main__':
    unittest.main()
