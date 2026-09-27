"""Tier-4-style tests for ingame/novulon/inject.py: is_computer_tuning_class/inject_if_computer/sweep/
on_new_object driven with small fake tuning classes and a fake services/sims4.resources/indexed_manager,
the same way the rest of this project's Tier-4 tests use a FakeSimInfo instead of the real game (SPEC.md
Sec 16 Tier 2 describes the same scenario - "a fake tuning class carrying _super_affordances=() and a
fake _anim_overrides_cls.params" - driven here directly under plain Python instead of inside the game's
3.7 DLL, since none of this logic touches anything game-specific beyond getattr/plain data).

Also cross-checks NOVULON_INTERACTION_ID against tools/novulon_ids (BP13)'s own INTERACTION_OPEN_MENU -
inject.py hardcodes the same numeric value because tools/ is dev-side build tooling never bundled into
Novulon.ts4script, so the shipped runtime code cannot import it at runtime; this test is what keeps the
two definitions from silently drifting apart.
"""
import os
import sys
import types
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon import inject  # noqa: E402

FAKE_INTERACTION_ID = 0xABCDEF


class AnimOverrides(object):
    def __init__(self, params):
        self.params = params


class FakeTuningClass(object):
    """Mirrors the real shape inject.py reads: _anim_overrides_cls.params (a dict) and
    _super_affordances (a tuple), both class-level in the real game."""
    def __init__(self, params=None, super_affordances=()):
        if params is not None:
            self._anim_overrides_cls = AnimOverrides(params)
        self._super_affordances = super_affordances


class TestInteractionIdCrossCheck(unittest.TestCase):
    def test_matches_bp13_novulon_ids(self):
        from tools import novulon_ids
        self.assertEqual(inject.NOVULON_INTERACTION_ID, novulon_ids.INTERACTION_OPEN_MENU,
                          'inject.py\'s hardcoded id must equal tools/novulon_ids (BP13)\'s '
                          'INTERACTION_OPEN_MENU - see inject.py\'s comment on NOVULON_INTERACTION_ID')


class TestIsComputerTuningClass(unittest.TestCase):
    def test_computer_type_key(self):
        cls = FakeTuningClass(params={'computerType': 'laptop'})
        self.assertTrue(inject.is_computer_tuning_class(cls))

    def test_tablet_carry_object(self):
        cls = FakeTuningClass(params={'carryObject': 'tablet'})
        self.assertTrue(inject.is_computer_tuning_class(cls))

    def test_other_carry_object_is_not_a_computer(self):
        cls = FakeTuningClass(params={'carryObject': 'book'})
        self.assertFalse(inject.is_computer_tuning_class(cls))

    def test_no_anim_overrides_at_all(self):
        cls = FakeTuningClass()
        self.assertFalse(inject.is_computer_tuning_class(cls))

    def test_anim_overrides_with_no_params(self):
        cls = FakeTuningClass(params=None)
        cls._anim_overrides_cls = AnimOverrides(params=None)
        self.assertFalse(inject.is_computer_tuning_class(cls))

    def test_empty_params_dict(self):
        cls = FakeTuningClass(params={})
        self.assertFalse(inject.is_computer_tuning_class(cls))

    def test_params_not_a_mapping_never_raises(self):
        cls = FakeTuningClass(params='not-a-dict')
        self.assertFalse(inject.is_computer_tuning_class(cls))   # 'in' works on str, .get() doesn't - guarded

    def test_plain_object_with_no_tuning_attrs(self):
        self.assertFalse(inject.is_computer_tuning_class(object()))


class FakeInteractionManager(object):
    def __init__(self, interactions):
        self._interactions = interactions

    def get(self, interaction_id):
        return self._interactions.get(interaction_id)


class FakeObjectManager(object):
    def __init__(self, types_dict):
        self._types = types_dict

    @property
    def types(self):
        return self._types


class FakeGameEnv(object):
    """Installs fake `services`/`sims4.resources`/`indexed_manager` modules for the duration of one
    test, mirroring inject.py's own import shape (`import services`, `import sims4.resources`,
    `import indexed_manager`, `import zone`)."""

    def __init__(self, interaction=None, object_types=None, object_manager_present=True):
        self.interaction = interaction
        self.object_types = object_types or {}
        self.object_manager_present = object_manager_present
        self.registered_callbacks = []

    def __enter__(self):
        fake_sims4 = types.ModuleType('sims4')
        fake_resources = types.ModuleType('sims4.resources')

        class Types(object):
            OBJECT = 'OBJECT'
            INTERACTION = 'INTERACTION'
        fake_resources.Types = Types
        fake_sims4.resources = fake_resources

        interaction_mgr = FakeInteractionManager(
            {inject.NOVULON_INTERACTION_ID: self.interaction} if self.interaction is not None else {})
        object_mgr = FakeObjectManager(self.object_types)

        def get_instance_manager(t):
            if t == Types.INTERACTION:
                return interaction_mgr
            if t == Types.OBJECT:
                return object_mgr
            return None

        fake_services = types.ModuleType('services')
        fake_services.get_instance_manager = get_instance_manager
        fake_services.object_manager = (lambda: object_mgr if self.object_manager_present else None)

        fake_indexed_manager = types.ModuleType('indexed_manager')

        class CallbackTypes(object):
            ON_OBJECT_ADD = 0

        def register_callback(callback_type, callback):
            self.registered_callbacks.append((callback_type, callback))
        object_mgr.register_callback = register_callback
        fake_indexed_manager.CallbackTypes = CallbackTypes

        self._saved = {name: sys.modules.get(name) for name in
                       ('sims4', 'sims4.resources', 'services', 'indexed_manager')}
        sys.modules['sims4'] = fake_sims4
        sys.modules['sims4.resources'] = fake_resources
        sys.modules['services'] = fake_services
        sys.modules['indexed_manager'] = fake_indexed_manager
        self.services = fake_services
        return self

    def __exit__(self, *exc):
        for name, mod in self._saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod


class TestInjectIfComputer(unittest.TestCase):
    def test_not_a_computer_returns_false_untouched(self):
        with FakeGameEnv(interaction='AFF'):
            cls = FakeTuningClass(params={'carryObject': 'book'}, super_affordances=('x',))
            ok = inject.inject_if_computer(cls, inject.NOVULON_INTERACTION_ID)
            self.assertFalse(ok)
            self.assertEqual(cls._super_affordances, ('x',))

    def test_computer_gets_affordance_added_exactly_once(self):
        with FakeGameEnv(interaction='AFF'):
            cls = FakeTuningClass(params={'computerType': 'desktop'}, super_affordances=('existing',))
            ok = inject.inject_if_computer(cls, inject.NOVULON_INTERACTION_ID)
            self.assertTrue(ok)
            self.assertEqual(cls._super_affordances, ('existing', 'AFF'))
            self.assertTrue(getattr(cls, inject.MARK))

    def test_sweeping_twice_does_not_grow_the_tuple_again(self):
        with FakeGameEnv(interaction='AFF'):
            cls = FakeTuningClass(params={'computerType': 'desktop'})
            inject.inject_if_computer(cls, inject.NOVULON_INTERACTION_ID)
            inject.inject_if_computer(cls, inject.NOVULON_INTERACTION_ID)
            self.assertEqual(cls._super_affordances, ('AFF',))   # exactly one, not two

    def test_interaction_not_loaded_yet_returns_false(self):
        with FakeGameEnv(interaction=None):
            cls = FakeTuningClass(params={'computerType': 'desktop'})
            ok = inject.inject_if_computer(cls, inject.NOVULON_INTERACTION_ID)
            self.assertFalse(ok)
            self.assertEqual(cls._super_affordances, ())

    def test_no_game_modules_at_all_never_raises(self):
        cls = FakeTuningClass(params={'computerType': 'desktop'})
        ok = inject.inject_if_computer(cls, inject.NOVULON_INTERACTION_ID)   # no fake env installed
        self.assertFalse(ok)


class TestSweep(unittest.TestCase):
    def test_sweep_counts_only_computers_and_is_idempotent(self):
        computer = FakeTuningClass(params={'computerType': 'desktop'})
        tablet = FakeTuningClass(params={'carryObject': 'tablet'})
        other = FakeTuningClass(params={'carryObject': 'book'})
        with FakeGameEnv(interaction='AFF', object_types={1: computer, 2: tablet, 3: other}):
            count1 = inject.sweep(inject.NOVULON_INTERACTION_ID)
            self.assertEqual(count1, 2)
            self.assertEqual(computer._super_affordances, ('AFF',))
            self.assertEqual(tablet._super_affordances, ('AFF',))
            self.assertEqual(other._super_affordances, ())
            count2 = inject.sweep(inject.NOVULON_INTERACTION_ID)   # already-marked classes count as ok...
            self.assertEqual(computer._super_affordances, ('AFF',))   # ...but never grow the tuple again
            self.assertEqual(tablet._super_affordances, ('AFF',))

    def test_sweep_with_no_object_manager_returns_zero(self):
        with FakeGameEnv(interaction='AFF', object_types={}):
            self.assertEqual(inject.sweep(inject.NOVULON_INTERACTION_ID), 0)

    def test_sweep_never_raises_with_no_game_modules(self):
        self.assertEqual(inject.sweep(inject.NOVULON_INTERACTION_ID), 0)


class FakeDefinition(object):
    def __init__(self, cls, def_id):
        self.cls = cls
        self.id = def_id


class FakeObject(object):
    def __init__(self, definition):
        self.definition = definition


class TestOnNewObject(unittest.TestCase):
    def test_injects_into_new_computer_object(self):
        with FakeGameEnv(interaction='AFF'):
            cls = FakeTuningClass(params={'computerType': 'desktop'})
            obj = FakeObject(FakeDefinition(cls, def_id=100))
            inject._seen_definitions.discard(100)
            inject.on_new_object(obj, inject.NOVULON_INTERACTION_ID)
            self.assertEqual(cls._super_affordances, ('AFF',))

    def test_dedupes_by_definition_id(self):
        with FakeGameEnv(interaction='AFF'):
            cls = FakeTuningClass(params={'computerType': 'desktop'})
            defn = FakeDefinition(cls, def_id=101)
            inject._seen_definitions.discard(101)
            inject.on_new_object(FakeObject(defn), inject.NOVULON_INTERACTION_ID)
            # simulate the exact same catalog object streaming in again with a fresh tuning-class
            # instance reset to empty - if on_new_object did NOT dedupe, this would add a second time
            cls._super_affordances = ()
            delattr(cls, inject.MARK)
            inject.on_new_object(FakeObject(defn), inject.NOVULON_INTERACTION_ID)
            self.assertEqual(cls._super_affordances, ())   # skipped entirely on the second call

    def test_no_definition_or_cls_never_raises(self):
        inject.on_new_object(FakeObject(None), inject.NOVULON_INTERACTION_ID)
        inject.on_new_object(object(), inject.NOVULON_INTERACTION_ID)


class TestInstall(unittest.TestCase):
    def test_install_hooks_zone_start_services(self):
        calls = []

        class FakeZone(object):
            def start_services(self, *a, **k):
                calls.append('orig-start-services')

        fake_zone_mod = types.ModuleType('zone')
        fake_zone_mod.Zone = FakeZone
        saved = sys.modules.get('zone')
        sys.modules['zone'] = fake_zone_mod
        try:
            with FakeGameEnv(interaction='AFF', object_types={}):
                done = inject.install(inject.NOVULON_INTERACTION_ID)
                self.assertTrue(done.get('Zone.start_services'))
                FakeZone().start_services()   # simulate the game starting a zone
                self.assertEqual(calls, ['orig-start-services'])   # original still runs, no crash
        finally:
            if saved is None:
                sys.modules.pop('zone', None)
            else:
                sys.modules['zone'] = saved

    def test_install_never_raises_with_no_zone_module(self):
        sys.modules.pop('zone', None)
        done = inject.install(inject.NOVULON_INTERACTION_ID)
        self.assertFalse(done['Zone.start_services'])


if __name__ == '__main__':
    unittest.main(verbosity=1)
