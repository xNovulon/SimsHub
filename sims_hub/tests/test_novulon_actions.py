"""Novulon's actions (ingame/novulon/actions.py) and the pages that use them, played through the stand-in game
(tests/novulon_game.py): needs, moodlets, skills, careers, traits, age, occult, relationships, pregnancy, household,
money, time, delete - and the age rules on all of them. No game needed.

    python -m unittest tests.test_novulon_actions
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

PKG = 'novulon'


def stat(name, **attrs):
    return type(name, (G.Stat,), attrs)


class ActionTest(unittest.TestCase):
    def setUp(self):
        self.game = g = G.install()
        self.home = g.add_household('Doe')
        self.alex = g.add_sim('Alex', 'Doe', age=32, household=self.home, npc=False, here=True, active=True)
        self.sam = g.add_sim('Sam', 'Doe', age=8, gender='MALE', household=self.home, npc=False, here=True)
        self.bella = g.add_sim('Bella', 'Goth', age=32, household=g.add_household('Goth'), here=True)
        self.mortimer = g.add_sim('Mortimer', 'Goth', age=64, gender='MALE', household=self.bella.household)
        self.alex.family.add(self.sam.id)
        self.sam.family.add(self.alex.id)
        mod = __import__(PKG, fromlist=['actions', 'entry', 'ui', 'icons'])
        self.a, self.entry, self.ui, self.icons = mod.actions, mod.entry, mod.ui, mod.icons
        self.entry._registered = False
        self.entry.register_commands()
        self.ui.reset_all()
        self.errors = []                            # anything Novulon caught and logged fails the test
        common = sys.modules['novulon.common']
        self.addCleanup(setattr, common, 'log_exception', common.log_exception)
        common.log_exception = lambda where: self.errors.append((where, traceback.format_exc()))

    def tearDown(self):
        errors, self.errors = self.errors, []
        G.uninstall()
        self.assertEqual(errors, [])

    def note(self):
        return G.text_of(self.game.notifications[-1].kw['text'])

    def open_sim(self, si):
        self.game.commands['novulon.sim'](si.id, _connection=7)
        return self.game.screen

    # ---------------------------------------------------------------- needs
    def test_fill_needs_fills_this_sim_only(self):
        hunger = stat('motive_Hunger', visible=True, stat_name=G.Loc('Hunger'))
        for si in (self.alex, self.bella):
            si.commodity_tracker.set_value(hunger, -50)
        self.assertEqual(self.a.fill_needs(self.alex), (True, 'Needs are full.'))
        self.assertEqual(self.alex.commodity_tracker.get_statistic(hunger).value, 100)
        self.assertEqual(self.bella.commodity_tracker.get_statistic(hunger).value, -50)

    def test_needs_page_shows_the_games_names_and_sets_a_percent(self):
        hunger = stat('motive_Hunger', visible=True, stat_name=G.Loc('Hunger'))
        self.alex.commodity_tracker.set_value(hunger, 0)
        self.alex.commodity_tracker.set_value(stat('commodity_Hidden'), 0)
        self.open_sim(self.alex).pick('Needs and moodlets')
        d = self.game.screen
        self.assertEqual(d.row('Hunger').desc, '50%')
        self.assertNotIn('Hidden', ' '.join(d.labels()))
        d.pick('Hunger')
        self.game.screen.ok('75')
        self.assertEqual(self.alex.commodity_tracker.get_statistic(hunger).value, 50)

    # ---------------------------------------------------------------- moodlets
    def buffs(self):
        happy = G.tuning('Buff_Happy', visible=True, buff_name=lambda si: G.Loc('Happy'), icon=G.Key(1, 2, 3))
        flirty = G.tuning('Buff_Flirty', visible=True, buff_name=lambda si: G.Loc('Flirty'))
        hidden = G.tuning('Buff_HappyHidden', visible=False, buff_name=lambda si: G.Loc('x'))
        ww = G.tuning('ww_buff_happy_horny', visible=True, buff_name=lambda si: G.Loc('Horny'))
        self.game.manager(self.game.Types.BUFF).classes += [happy, flirty, hidden, ww]
        return happy, flirty, ww

    def test_moodlet_search_uses_the_games_names_and_hides_adult_ones_from_a_child(self):
        happy, flirty, ww = self.buffs()
        adult = [m['value'] for m in self.a.find_buffs('happy', self.alex)]
        self.assertEqual(sorted(b.__name__ for b in adult), ['Buff_Happy', 'ww_buff_happy_horny'])
        self.assertEqual([m['value'] for m in self.a.find_buffs('happy', self.sam)], [happy])
        self.assertEqual(self.a.find_buffs('flirty', self.sam), [])
        self.assertFalse(self.a.add_buff(self.sam, ww)[0])
        self.assertEqual(self.sam.get_sim_instance().buffs, [])

    def test_add_and_remove_a_moodlet_through_the_pages(self):
        happy, _, _ = self.buffs()
        self.open_sim(self.alex).pick('Needs and moodlets')
        self.game.screen.pick('Add a moodlet')
        self.game.screen.ok('happy')
        d = self.game.screen
        self.assertEqual(d.row('Happy').icon, G.Key(1, 2, 3))           # the game's own icon
        d.pick('Happy')
        self.assertEqual(self.alex.get_sim_instance().buffs, [happy])
        self.ui.back(7)
        self.game.screen.pick('Remove a moodlet')
        self.game.screen.pick('Happy')
        self.assertEqual(self.alex.get_sim_instance().buffs, [])

    def test_moodlets_need_the_sim_on_the_lot(self):
        happy, _, _ = self.buffs()
        self.assertFalse(self.a.add_buff(self.mortimer, happy)[0])
        self.open_sim(self.mortimer).pick('Needs and moodlets')
        self.assertFalse(self.game.screen.row('Add a moodlet').enabled)

    # ---------------------------------------------------------------- skills
    def skills(self):
        cooking = stat('statistic_Skill_AdultMajor_HomeStyleCooking', is_skill=True, max_level=10,
                       stat_name=G.Loc('Cooking'), can_add=classmethod(lambda cls, si: int(si.age) >= 8))
        motor = stat('statistic_Skill_Toddler_Movement', is_skill=True, max_level=5, stat_name=G.Loc('Movement'),
                     can_add=classmethod(lambda cls, si: int(si.age) == 2))
        hidden = stat('statistic_Skill_Hidden', is_skill=True, hidden=True, max_level=10,
                      can_add=classmethod(lambda cls, si: True))
        mgr = self.game.manager(self.game.Types.STATISTIC)
        mgr.all_skills_gen = lambda: iter([cooking, motor, hidden])
        return cooking, motor, hidden

    def test_max_skills_maxes_only_skills_the_sim_can_have(self):
        cooking, motor, hidden = self.skills()
        self.assertEqual(self.a.max_skills(self.alex), (True, '1 skills maxed.'))
        self.assertEqual(self.alex.commodity_tracker.get_statistic(cooking).value, 10)
        self.assertIsNone(self.alex.commodity_tracker.get_statistic(motor))
        self.assertIsNone(self.alex.commodity_tracker.get_statistic(hidden))

    def test_set_any_skill_through_the_pages(self):
        cooking, _, _ = self.skills()
        self.open_sim(self.alex).pick('Skills')
        self.game.screen.pick('Set any skill')
        self.assertEqual(self.game.screen.labels()[1:], ['Cooking'])
        self.game.screen.pick('Cooking')
        self.game.screen.ok('11')                                         # out of range: asked again
        self.assertIn('from 0 to 10', self.note())
        self.game.screen.ok('7')
        self.assertEqual(self.alex.commodity_tracker.get_statistic(cooking).value, 7)
        self.assertEqual(self.a.skills_of(self.alex)[0]['level'], 7)
        self.assertEqual(self.a.clear_skills(self.alex), (True, '1 skills cleared.'))
        self.assertEqual(self.a.skills_of(self.alex), [])

    # ---------------------------------------------------------------- careers
    def test_join_promote_and_leave_a_career(self):
        chef = G.career('career_Adult_Culinary')
        teen = G.career('career_Teen_Barista', ages=(8,))
        self.game.careers += [chef, teen]
        self.assertEqual([c['value'] for c in self.a.all_careers(self.alex)], [chef])
        self.assertEqual([c['value'] for c in self.a.all_careers(self.sam)], [teen])
        self.open_sim(self.alex).pick('Career')
        self.game.screen.pick('Join a career')
        self.game.screen.pick('career_Adult_Culinary')
        job = self.alex.careers[chef.guid64]
        self.assertEqual(self.a.career_summary(self.alex).text, 'career_Adult_Culinary title')
        self.ui.back(7)
        self.game.screen.pick('career_Adult_Culinary')
        self.game.screen.pick('Promote')
        self.assertEqual(job.user_level, 2)
        self.game.screen.pick('Add a day off')
        self.assertEqual(job.pto, 1)
        self.game.screen.pick('Leave this job')
        self.game.screen.ok()
        self.assertEqual(self.alex.careers, {})
        self.assertEqual(self.game.screen.title, 'Career')

    # ---------------------------------------------------------------- traits
    def traits(self):
        mk = lambda n, **kw: G.tuning(n, is_personality_trait=True, display_name=lambda si, n=n: G.Loc(n[6:]), **kw)
        cheerful, hot, romantic = mk('trait_Cheerful'), mk('trait_HotHeaded'), mk('trait_Romantic', ages=(8, 16, 32, 64))
        hidden = G.tuning('trait_HiddenThing', is_personality_trait=False)
        self.game.manager(self.game.Types.TRAIT).classes += [cheerful, hot, romantic, hidden]
        return cheerful, hot, romantic

    def test_traits_add_and_remove_with_slots_and_the_child_rule(self):
        cheerful, hot, romantic = self.traits()
        names = [t['value'] for t in self.a.addable_traits(self.alex)]
        self.assertEqual(names, [cheerful, hot, romantic])
        self.assertNotIn(romantic, [t['value'] for t in self.a.addable_traits(self.sam)])   # looks romantic
        for t in (cheerful, hot, romantic):
            self.assertTrue(self.a.add_trait(self.alex, t)[0])
        extra = G.tuning('trait_Lazy', is_personality_trait=True)
        self.assertEqual(self.a.add_trait(self.alex, extra), (False, self.a.TRAIT_SLOTS_FULL))
        self.open_sim(self.alex).pick('Traits')
        d = self.game.screen
        self.assertFalse(d.row('Add a trait').enabled)
        d.pick('Cheerful')
        self.assertFalse(self.alex.has_trait(cheerful))

    # ---------------------------------------------------------------- age
    def test_age_up_stops_at_elder_and_age_down_resets_the_sim(self):
        self.assertEqual(self.a.age_up(self.mortimer), (False, 'Elders are the last life stage.'))
        self.assertEqual(self.a.age_down(self.alex), (True, 'Now young adult.'))
        self.assertEqual(self.alex.get_sim_instance().resets, 1)
        self.open_sim(self.mortimer).pick('Age')
        self.assertFalse(self.game.screen.row('Age up').enabled)

    # ---------------------------------------------------------------- occult
    def test_one_occult_at_a_time(self):
        names = [o['name'] for o in self.a.occult_types()]
        self.assertIn('Vampire', names)
        self.assertNotIn('Human', names)
        self.assertEqual(self.a.add_occult(self.bella, 4), (True, 'Done.'))
        self.assertEqual(self.a.occult_summary(self.bella), 'Vampire')
        self.assertFalse(self.a.add_occult(self.bella, 32)[0])
        self.assertTrue(self.a.remove_occult(self.bella, 4)[0])
        self.assertEqual(self.a.occult_summary(self.bella), 'Human')

    # ---------------------------------------------------------------- relationships
    def test_romance_only_between_adults_who_arent_family(self):
        friendship, romance = self.game.tracks
        self.assertTrue(self.a.related(self.alex, self.sam))
        self.assertFalse(self.a.related(self.alex, self.bella))
        self.assertFalse(self.a.set_relationship(self.alex, self.sam, 'romance', 100)[0])
        self.assertNotIn((self.sam.id, romance), self.alex.relationship_tracker.scores)
        self.assertTrue(self.a.set_relationship(self.alex, self.bella, 'romance', 100)[0])
        self.assertEqual(self.alex.relationship_tracker.scores[(self.bella.id, romance)], 100)
        self.open_sim(self.bella).pick('Relationship with Alex')
        self.game.screen.pick('Make best friends')
        self.assertEqual(self.alex.relationship_tracker.scores[(self.bella.id, friendship)], 100)
        self.game.screen.pick('Back to neutral')
        self.assertEqual(self.alex.relationship_tracker.scores[(self.bella.id, romance)], 0)

    # ---------------------------------------------------------------- pregnancy
    def test_pregnancy_only_for_adults_who_arent_family(self):
        self.assertFalse(self.a.start_pregnancy(self.sam, self.bella)[0])
        self.assertFalse(self.a.start_pregnancy(self.alex, self.sam)[0])
        self.open_sim(self.alex).pick('Pregnancy')
        self.game.screen.pick('Get pregnant with')
        self.game.screen.pick('Mortimer Goth')
        self.assertIs(self.alex.pregnancy_tracker.partner, self.mortimer)
        self.assertEqual(self.note(), 'Pregnant with Mortimer\'s baby.')
        self.game.screen.pick('End the pregnancy')
        self.game.screen.ok()
        self.assertFalse(self.a.is_pregnant(self.alex))

    # ---------------------------------------------------------------- household, Sims bar, money
    def test_move_in_and_sims_bar(self):
        self.open_sim(self.bella).pick('Household')
        self.game.screen.pick('Add to my Sims bar')
        self.assertIn(self.bella, self.game.selectable)
        self.game.screen.pick('Take out of my Sims bar')
        self.assertNotIn(self.bella, self.game.selectable)
        self.game.screen.pick('Move into my household')
        self.game.screen.ok()
        self.assertIn(self.bella, self.home.members)
        self.assertFalse(self.game.screen.row('Move into my household').enabled)
        self.assertFalse(self.a.release(self.alex)[0])

    def test_money(self):
        self.assertEqual(self.a.add_funds(self.home, 10000), (True, 'Added §10,000. The household has §11,000.'))
        self.assertEqual(self.a.set_funds(self.home, 250), (True, 'The household has §250.'))
        self.game.commands['novulon.menu'](_connection=7)
        self.game.screen.pick('Household')
        self.game.screen.pick('Money')
        self.game.screen.pick('Set an amount')
        self.game.screen.ok('5,000')
        self.assertEqual(self.home.funds.money, 5000)

    # ---------------------------------------------------------------- lot, world, delete
    def test_bring_here_and_reset(self):
        self.assertEqual(self.a.teleport_to_active(self.bella), (True, 'Here now.'))
        sim = self.bella.get_sim_instance()
        self.assertEqual((sim.location.transform.translation.x, sim.location.transform.translation.z), (1.0, 3.0))
        self.assertEqual(sim.location.routing_surface, 'surface')
        self.assertFalse(self.a.teleport_to_active(self.mortimer)[0])
        self.assertFalse(self.a.reset(self.mortimer)[0])

    def test_time_and_autonomy(self):
        self.game.commands['novulon.menu'](_connection=7)
        self.game.screen.pick('World')
        self.assertEqual(self.game.screen.text, 'The time is 9:30.')
        self.game.screen.pick('Set the time to Evening')
        self.assertEqual((self.game.clock['hour'], self.game.clock['satisfied']), (18, 1))
        self.game.screen.pick('Autonomy off')
        self.assertEqual(self.game.autonomy, 'LIMITED_ONLY')

    def test_create_a_sim_opens_for_that_sims_household(self):
        self.open_sim(self.bella).pick('Edit in Create a Sim')
        self.assertEqual(self.game.client_cheats,
                         [('sims.exit2caswithhouseholdid %d %d' % (self.bella.id, self.bella.household_id), 7)])

    def test_delete_takes_a_sim_off_the_lot_first_and_never_your_own(self):
        self.assertFalse(self.a.can_delete(self.sam))
        self.open_sim(self.bella).pick('Delete')
        self.game.screen.ok()
        self.assertEqual(self.game.destroyed, [self.bella])
        self.assertIn('remove_permanently', self.bella.calls)
        self.assertNotIn(self.bella.id, self.game.sims)

    # ---------------------------------------------------------------- every page, every button
    def test_every_page_opens_and_every_button_works(self):
        """Walks the whole menu like a player pressing everything (questions and text boxes are cancelled), from
        the computer and from a Sim, with jobs, traits, skills, needs and moodlets to show."""
        happy, _, _ = self.buffs()
        cooking, _, _ = self.skills()
        cheerful, _, _ = self.traits()
        self.game.careers.append(G.career('career_Adult_Culinary'))
        for si in (self.alex, self.bella, self.sam):
            si.commodity_tracker.set_value(stat('motive_Hunger', visible=True, stat_name=G.Loc('Hunger')), 0)
            si.get_sim_instance().buffs.append(happy)
            si.add_trait(cheerful)
            self.a.set_skill(si, cooking, 3)
        self.a.add_career(self.bella, self.game.careers[0])
        mod = __import__(PKG, fromlist=['settings', 'compat'])
        mod.settings.set('adult_enabled', True)
        mod.settings.set('adult_notice_seen', True)
        mod.compat.wickedwhims_present = lambda: True
        mod.compat.wickedwhims_version = lambda: '183'
        mod.compat.ww_get = lambda d, k: False
        mod.compat.ww_set = lambda d, k, v: True
        seen = set()

        def crawl(depth):
            page = self.game.screen
            title = page.title
            for label in [r.label for r in page.rows if r.enabled and r.label != 'Back']:
                self.assertEqual(self.game.screen.title, title, 'lost the page while on %r' % label)
                if label not in self.game.screen.labels():          # a toggle earlier on the page changed it
                    continue
                self.game.screen.pick(label)
                new = self.game.screen
                if new.kind in ('UiDialogOkCancel', 'UiDialogTextInputOkCancel', 'UiSimPicker'):
                    new.cancel()
                elif new.kind == 'UiObjectPicker' and new.title != title and 'Back' in new.labels():
                    seen.add(new.title)
                    if depth:
                        crawl(depth - 1)
                    self.game.screen.pick('Back')
            self.assertFalse(self.errors, 'error on page %r' % title)

        self.game.commands['novulon.menu'](_connection=7)
        crawl(3)
        self.open_sim(self.bella)
        crawl(2)
        mod.settings.set('adult_enabled', True)                         # Settings' own toggle turned it off
        self.game.commands['novulon.menu'](_connection=7)
        self.game.screen.pick('Adult')
        seen.add(self.game.screen.title)
        crawl(1)
        for t in ('Sims', 'Household', 'Cheats', 'World', 'Settings', 'Adult', 'Money', 'Needs and moodlets', 'Skills',
                  'Career', 'Traits', 'Age', 'Occult', 'Relationship', 'Pregnancy', 'Set any skill', 'Join a career'):
            self.assertIn(t, seen)

    def test_a_failing_action_says_so_instead_of_crashing(self):
        self.alex.commodity_tracker = None
        worked, msg = self.a.fill_needs(self.alex)
        self.assertFalse(worked)
        self.assertIn('log', msg)
        self.assertEqual([w for w, _tb in self.errors], ['fill needs'])     # logged, as it should be
        self.errors = []


if __name__ == '__main__':
    unittest.main()
