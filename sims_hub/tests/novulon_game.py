"""A stand-in game for Novulon's tests: the game modules Novulon imports, as small fakes in sys.modules.

    from tests import novulon_game as G
    game = G.install()                 # fakes in place, a fresh world; returns the FakeGame
    alex = game.add_sim('Alex', 'Doe', age=32, gender='FEMALE')
    import novulon.entry ...           # import Novulon after install()
    game.dialogs[-1].pick('Sims')      # press a row of the dialog on screen
    game.dialogs[-1].ok('Bella')       # type into a text box and press OK
    G.uninstall()

Every dialog Novulon shows is recorded (game.dialogs) with what it was given - title, rows with their labels, icons
and descriptions - so a test can read the screen and press rows like a player. The fakes only model what Novulon
uses; anything else raises AttributeError, so a test fails loudly if Novulon starts using something new.
"""
import sys
import types

MODULE_NAMES = ('services', 'sims4', 'sims4.resources', 'sims4.localization', 'sims4.collections', 'sims4.commands',
                'ui', 'ui.ui_dialog_picker', 'ui.ui_dialog', 'ui.ui_dialog_generic', 'ui.ui_text_input',
                'ui.ui_dialog_notification', 'distributor', 'distributor.shared_messages', 'zone', 'sims', 'sims.sim',
                'sims.sim_info_types', 'sims.household_enums', 'sims.occult', 'sims.occult.occult_enums',
                'sims.occult.occult_tracker', 'objects', 'objects.object_enums', 'relationships',
                'relationships.relationship_track', 'protocolbuffers', 'autonomy', 'autonomy.settings', 'sims4.math',
                'alarms', 'clock')
_saved = {}
GAME = None


# ------------------------------------------------------------------ text and keys
class Text:
    def __init__(self, s):
        self.text = s

    def __repr__(self):
        return 'Text(%r)' % self.text


def text_of(x):
    if callable(x) and not isinstance(x, Text):
        x = x()
    return x.text if isinstance(x, (Text, Loc)) else x


class Key:
    def __init__(self, type, instance, group=0):
        self.type, self.instance, self.group = type, instance, group

    def __eq__(self, o):
        return isinstance(o, Key) and (self.type, self.instance, self.group) == (o.type, o.instance, o.group)

    def __hash__(self):
        return hash((self.type, self.instance, self.group))


class IconInfoData:
    def __init__(self, icon_resource=None, obj_instance=None, **_kw):
        self.icon_resource, self.obj_instance = icon_resource, obj_instance


class AttributeDict(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


# ------------------------------------------------------------------ dialogs
class Row:
    def __init__(self, **kw):
        self.kw = kw

    @property
    def label(self):
        return text_of(self.kw.get('name'))

    @property
    def desc(self):
        return text_of(self.kw.get('row_description'))

    @property
    def enabled(self):
        return self.kw.get('is_enable', True)

    @property
    def icon(self):
        return self.kw.get('icon')


class Dialog:
    def __init__(self, kind, owner, **kw):
        self.kind, self.owner, self.kw = kind, owner, kw
        self.rows, self.listener, self.shown = [], None, False
        self.accepted, self.response, self._picked = False, None, []
        self.text_input_responses = {}

    # what the game's dialogs have
    def add_row(self, row):
        self.rows.append(row)

    def show_dialog(self, on_response=None):
        self.listener, self.shown = on_response, True
        GAME.dialogs.append(self)

    def get_result_rows(self):
        return list(self._picked)

    # reading the screen
    @property
    def title(self):
        return text_of(self.kw.get('title'))

    @property
    def text(self):
        return text_of(self.kw.get('text'))

    def labels(self):
        return [r.label for r in self.rows]

    def row(self, label):
        for r in self.rows:
            if r.label == label or (r.label or '').startswith(label):
                return r
        raise AssertionError('no row %r in %r (%s)' % (label, self.title, self.labels()))

    # pressing things like a player
    def pick(self, *labels):
        self._picked = [self.row(l) for l in labels]
        for r in self._picked:
            assert r.enabled, 'row %r is disabled' % r.label
        self.accepted, self.response = True, 10001
        self.listener(self)

    def ok(self, typed=None):
        if typed is not None:
            for name in (self.kw.get('text_inputs') or {}):
                self.text_input_responses[name] = typed
        self.accepted, self.response = True, 10001
        self.listener(self)

    def cancel(self):
        self.accepted, self.response = False, 10002
        self.listener(self)


def factory(kind):
    class Factory:
        def __init__(self, **_kw):
            pass

        def default(self, owner=None, **kw):
            return Dialog(kind, owner, **kw)

    class Cls:
        @staticmethod
        def TunableFactory(**_kw):
            return Factory()
    Cls.__name__ = kind
    return Cls


class TextInput:
    sort_order = 0
    default_text = initial_value = title = restricted_characters = None
    check_profanity = False
    length_restriction = height = None


class TextInputCls:
    @staticmethod
    def TunableFactory(locked_args=None):
        class F:
            @staticmethod
            def default():
                t = TextInput()
                t.sort_order = (locked_args or {}).get('sort_order', 0)
                return t
        return F()


# ------------------------------------------------------------------ the world
class Enum:
    def __init__(self, name, value):
        self.name, self.value = name, value

    def __int__(self):
        return self.value

    def __eq__(self, o):
        return int(o) == self.value if isinstance(o, (int, Enum)) else False

    def __hash__(self):
        return hash(self.value)


class Loc:
    """A game string (what a tuned name gives): shown as it is, never re-wrapped as raw text."""
    def __init__(self, text, hash=1):
        self.text, self.hash = text, hash

    def __repr__(self):
        return 'Loc(%r)' % self.text


def tuning(name, **attrs):
    """A tuning class, like the game's instance managers hold."""
    attrs.setdefault('guid64', sum(ord(c) * 31 ** i for i, c in enumerate(name)) % 10 ** 12)
    return type(name, (), attrs)


class Funds:
    def __init__(self, money):
        self.money = money

    def add(self, amount, reason, *_a):
        self.money = min(99999999, self.money + amount)

    def try_remove(self, amount, reason, *_a):
        if amount > self.money:
            return False
        self.money -= amount
        return True


class Household:
    def __init__(self, hid, name, funds=1000):
        self.id, self.name, self.members = hid, name, []
        self.funds = Funds(funds)

    def sim_info_gen(self):
        return iter(list(self.members))

    def can_add_sim_info(self, sim_info):
        return len(self.members) < 8


class Stat:
    """A statistic on a Sim; type(stat) is its tuning class, as in the game."""
    def get_value(self):
        return self.value

    def get_user_value(self):
        return int(self.value)


def make_stat(t, value=0.0):
    s = t.__new__(t) if issubclass(t, Stat) else Stat()
    s.value = value
    s.is_skill = getattr(t, 'is_skill', False)
    s.is_visible = getattr(t, 'visible', False)
    s.min_value, s.max_value = getattr(t, 'min_value_tuning', -100), getattr(t, 'max_value_tuning', 100)
    return s


class Tracker:
    """commodity_tracker: one statistic object per type."""
    def __init__(self):
        self.stats = {}

    def __iter__(self):
        return iter(list(self.stats.values()))

    def get_statistic(self, t):
        return self.stats.get(t)

    def add_statistic(self, t):
        if getattr(t, 'blocked', False):
            return None
        if t not in self.stats:
            self.stats[t] = make_stat(t)
        return self.stats[t]

    def set_user_value(self, t, v):
        self.stats[t].value = v

    def set_value(self, t, v):
        self.add_statistic(t).value = v

    def remove_statistic(self, t):
        self.stats.pop(t, None)

    def set_all_commodities_to_best_value(self, visible_only=True):
        for s in self.stats.values():
            if not s.is_skill and (s.is_visible or not visible_only):
                s.value = s.max_value


class TraitTracker:
    def __init__(self, si, slots=3):
        self.si, self.slots, self.traits = si, slots, []

    @property
    def personality_traits(self):
        return [t for t in self.traits if t.is_personality_trait]

    @property
    def empty_slot_number(self):
        return self.slots - len(self.personality_traits)

    def has_trait(self, t):
        return t in self.traits

    def can_add_trait(self, t, skip_count=False):
        ages = getattr(t, 'ages', None)
        return ages is None or int(self.si.age) in ages


class CareerTracker:
    def __init__(self, si):
        self.si = si

    def get_career_by_uid(self, uid):
        return self.si.careers.get(uid)

    def add_career(self, job):
        self.si.careers[job.guid64] = job

    def remove_career(self, uid, post_quit_msg=True, **_kw):
        self.si.careers.pop(uid, None)


class Career:
    """Career tuning: Career(sim_info) is a job."""
    def __init__(self, sim_info):
        self.sim_info, self.user_level, self.pto = sim_info, 1, 0
        self.current_track_tuning = self.start_track
        self.current_level_tuning = types.SimpleNamespace(title=lambda si, n=type(self).__name__: Loc(n + ' title'))

    def promote(self):
        self.user_level += 1

    def demote(self):
        self.user_level = max(1, self.user_level - 1)

    def add_pto(self, n):
        self.pto += n

    def resend_career_data(self):
        pass


def career(name, ages=(16, 32, 64)):
    track = types.SimpleNamespace(career_name=lambda si, n=name: Loc(n), icon=Key(0x2F7D0004, len(name), 0))

    def available(cls, sim_info=None, from_join=False):
        return int(sim_info.age) in ages
    return type(name, (Career,), {'guid64': sum(ord(c) * 31 ** i for i, c in enumerate(name)) % 10 ** 12,
                                  'start_track': track, 'show_career_in_join_career_picker': True,
                                  'is_career_available': classmethod(available)})


class OccultTracker:
    OCCULT_DATA = {}

    def __init__(self):
        self.types = set()

    def has_occult_type(self, t):
        return int(t) in self.types

    def add_occult_type(self, t):
        self.types.add(int(t))

    def remove_occult_type(self, t):
        self.types.discard(int(t))


class PregnancyTracker:
    def __init__(self):
        self.partner = None

    @property
    def is_pregnant(self):
        return self.partner is not None

    def start_pregnancy(self, a, b):
        self.partner = b

    def clear_pregnancy(self):
        self.partner = None


class RelationshipTracker:
    def __init__(self):
        self.scores = {}

    def set_relationship_score(self, target_id, value, track):
        self.scores[(target_id, track)] = value


class Vector3:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class FakeSim:
    """The Sim object on the lot."""
    def __init__(self, si):
        self.sim_info, self.id = si, si.id
        self.buffs, self.resets = [], 0
        self.position = Vector3(1.0, 0.0, 2.0)
        self.forward = Vector3(0.0, 0.0, 1.0)
        self.orientation = 'facing'
        self.location = types.SimpleNamespace(routing_surface='surface')
        inv = types.SimpleNamespace(purged=0)
        inv.purge_inventory = lambda: setattr(inv, 'purged', inv.purged + 1)
        self.inventory_component = inv

    def get_active_buff_types(self):
        return list(self.buffs)

    def debug_add_buff_by_type(self, b):
        self.buffs.append(b)

    def has_buff(self, b):
        return b in self.buffs

    def remove_buff_by_type(self, b):
        self.buffs.remove(b)

    def reset(self, reason, source, cause):
        self.resets += 1


class SimInfo:
    AGES = (1, 128, 2, 4, 8, 16, 32, 64)

    def __init__(self, sid, first, last, age=32, gender='FEMALE', species=1, household=None, npc=True, here=False):
        self.id = self.sim_id = sid
        self.first_name, self.last_name = first, last
        self.age = Enum('AGE', age)
        self.gender = Enum(gender, 4096 if gender == 'MALE' else 8192)
        self.species = Enum('SPECIES', species)
        self.household = household
        self.household_id = household.id if household else 0
        self.is_npc = npc
        self._sim = FakeSim(self) if here else None
        self.calls = []
        self.commodity_tracker = Tracker()
        self.trait_tracker = TraitTracker(self)
        self.careers = {}
        self.career_tracker = CareerTracker(self)
        self.occult_tracker = OccultTracker()
        self.pregnancy_tracker = PregnancyTracker()
        self.relationship_tracker = RelationshipTracker()
        self.family = set()
        self.primary_aspiration = None

    def get_sim_instance(self, **_kw):
        return self._sim

    def is_instanced(self, **_kw):
        return self._sim is not None

    def get_tracker(self, t):
        return self.commodity_tracker

    def add_trait(self, t):
        if t not in self.trait_tracker.traits:
            self.trait_tracker.traits.append(t)

    def remove_trait(self, t):
        if t in self.trait_tracker.traits:
            self.trait_tracker.traits.remove(t)

    def has_trait(self, t):
        return t in self.trait_tracker.traits

    def incest_prevention_test(self, other):
        return other.id not in self.family

    def _move_age(self, step):
        i = self.AGES.index(int(self.age)) + step
        self.age = Enum('AGE', self.AGES[max(0, min(len(self.AGES) - 1, i))])

    def callback_auto_age(self):
        self._move_age(1)

    def reverse_age(self):
        self._move_age(-1)

    def remove_permanently(self, household=None):
        self.calls.append('remove_permanently')
        GAME.sims.pop(self.id, None)
        if self.household is not None and self in self.household.members:
            self.household.members.remove(self)

    def __repr__(self):
        return 'SimInfo(%s %s)' % (self.first_name, self.last_name)


class InstanceManager:
    def __init__(self):
        self.by_id, self.classes = {}, []

    def get(self, i):
        return self.by_id.get(i)

    @property
    def types(self):
        return {id(c): c for c in self.classes}


class FakeGame:
    def __init__(self):
        self.dialogs, self.notifications, self.commands, self.hooks_installed = [], [], {}, []
        self.sims, self.households = {}, {}
        self.active = None
        self.managers = {}
        self._next = 1000
        self.careers = []                       # the career service's list
        self.clock = {'hour': 9, 'minute': 30, 'satisfied': 0}
        self.autonomy = None
        self.selectable = []                    # the Sims bar
        self.destroyed = []

    def manager(self, t):
        return self.managers.setdefault(t, InstanceManager())

    def add_household(self, name, funds=1000):
        self._next += 1
        hh = Household(self._next, name, funds)
        self.households[hh.id] = hh
        return hh

    def add_sim(self, first, last='', age=32, gender='FEMALE', species=1, household=None, npc=True, here=False, active=False):
        self._next += 1
        si = SimInfo(self._next, first, last, age, gender, species, household, npc, here)
        if household is not None:
            household.members.append(si)
        self.sims[si.id] = si
        if active:
            self.active = si
        return si

    @property
    def screen(self):
        """The newest dialog shown (not a notification)."""
        return [d for d in self.dialogs if d.kind != 'UiDialogNotification'][-1]


def _module(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


def install():
    """Put the fake game modules in place (remembering what was there) and return a fresh FakeGame."""
    global GAME
    GAME = g = FakeGame()
    for n in MODULE_NAMES:
        if n in sys.modules and n not in _saved:
            _saved[n] = sys.modules[n]

    class Types:
        INTERACTION, OBJECT, ACTION, TRAIT, BUFF, STATISTIC, CAREER, ASPIRATION_TRACK = 1, 2, 3, 4, 5, 6, 7, 8

    def satisfy():
        g.clock['satisfied'] += 1
    sim_info_manager = types.SimpleNamespace(get_all=lambda: list(g.sims.values()), get=lambda i: g.sims.get(i),
                                             auto_satisfy_sim_motives=satisfy)
    object_manager = types.SimpleNamespace(get=lambda i: None)

    def switch(sim_info, target, reason=None):
        hh = g.active.household
        if sim_info.household is not None and sim_info in sim_info.household.members:
            sim_info.household.members.remove(sim_info)
        hh.members.append(sim_info)
        sim_info.household, sim_info.household_id = hh, hh.id
    household_manager = types.SimpleNamespace(switch_sim_household=switch)

    class SelectableSims:
        def __contains__(self, si):
            return si in g.selectable
    client = types.SimpleNamespace(id=7, selectable_sims=SelectableSims(),
                                   add_selectable_sim_info=lambda si, send_relationship_update=True: g.selectable.append(si),
                                   remove_selectable_sim_info=lambda si: g.selectable.remove(si))

    def set_game_time(h, m, s):
        g.clock.update(hour=h, minute=m)
    now = types.SimpleNamespace(hour=lambda: g.clock['hour'], minute=lambda: g.clock['minute'])

    def destroy(sim, source=None, cause=None):
        g.destroyed.append(sim.sim_info)
        sim.sim_info._sim = None
    autonomy_settings = types.SimpleNamespace(set_setting=lambda state, group: setattr(g, 'autonomy', state))
    services = _module('services', sim_info_manager=lambda: sim_info_manager, object_manager=lambda: object_manager,
                       active_sim_info=lambda: g.active,
                       active_household=lambda: g.active.household if g.active else None,
                       get_active_sim=lambda: g.active.get_sim_instance() if g.active else None,
                       get_instance_manager=lambda t: g.manager(t),
                       household_manager=lambda: household_manager,
                       client_manager=lambda: types.SimpleNamespace(get_first_client=lambda: client),
                       get_career_service=lambda: types.SimpleNamespace(get_shuffled_career_list=lambda: list(g.careers)),
                       game_clock_service=lambda: types.SimpleNamespace(set_game_time=set_game_time),
                       time_service=lambda: types.SimpleNamespace(sim_now=now),
                       autonomy_service=lambda: types.SimpleNamespace(global_autonomy_settings=autonomy_settings),
                       get_reset_and_delete_service=lambda: types.SimpleNamespace(trigger_destroy=destroy),
                       on_enter_main_menu=lambda *a, **k: None)
    g.client = client

    class OccultType(int):
        pass
    occult_members = []
    for name, value in (('HUMAN', 1), ('ALIEN', 2), ('VAMPIRE', 4), ('MERMAID', 8), ('WITCH', 16), ('WEREWOLF', 32),
                        ('FAIRY', 64)):
        m = OccultType(value)
        m.name = name
        occult_members.append(m)

    class OccultEnum:
        def __iter__(self):
            return iter(occult_members)

        def __call__(self, v):
            return next(m for m in occult_members if int(m) == int(v))
    OccultEnumObj = OccultEnum()
    friendship_track, romance_track = tuning('LTR_Friendship_Main'), tuning('LTR_Romance_Main')
    g.tracks = friendship_track, romance_track

    def add_alarm_real_time(owner, interval, callback, repeating=False, **_kw):
        handle = types.SimpleNamespace(cancelled=False)
        for _ in range(40):                     # the poll runs at once, a few times, like time passing
            if handle.cancelled:
                break
            callback(handle)
        return handle

    def command(name, command_type=None, **_kw):
        def deco(fn):
            g.commands[name] = fn
            return fn
        return deco
    g.client_cheats = []
    sims4_commands = _module('sims4.commands', Command=command,
                             CommandType=types.SimpleNamespace(Live=1, Cheat=2), execute=lambda *a, **k: None,
                             client_cheat=lambda s, conn: g.client_cheats.append((s, conn)))
    loc = _module('sims4.localization', LocalizationHelperTuning=types.SimpleNamespace(get_raw_text=Text))

    class Notification(factory('UiDialogNotification')):
        pass

    def notify_default(owner=None, **kw):
        d = Dialog('UiDialogNotification', owner, **kw)
        d.show_dialog = lambda on_response=None: g.notifications.append(d)
        return d

    class NotifFactory:
        default = staticmethod(notify_default)

    class NotificationCls:
        @staticmethod
        def TunableFactory(**_kw):
            return NotifFactory()

    class Zone:
        def start_services(self, *a, **k):
            return None

    class Sim:
        pass

    mods = {
        'services': services,
        'sims4': _module('sims4'),
        'sims4.resources': _module('sims4.resources', Types=Types, Key=Key),
        'sims4.localization': loc,
        'sims4.collections': _module('sims4.collections', AttributeDict=AttributeDict),
        'sims4.commands': sims4_commands,
        'ui': _module('ui'),
        'ui.ui_dialog_picker': _module('ui.ui_dialog_picker', UiObjectPicker=factory('UiObjectPicker'),
                                       UiSimPicker=factory('UiSimPicker'), ObjectPickerRow=Row, SimPickerRow=Row,
                                       ObjectPickerType=types.SimpleNamespace(OBJECT=4, OBJECT_LARGE=12)),
        'ui.ui_dialog': _module('ui.ui_dialog', UiDialogOkCancel=factory('UiDialogOkCancel')),
        'ui.ui_dialog_generic': _module('ui.ui_dialog_generic', UiDialogTextInputOkCancel=factory('UiDialogTextInputOkCancel')),
        'ui.ui_text_input': _module('ui.ui_text_input', UiTextInput=TextInputCls),
        'ui.ui_dialog_notification': _module('ui.ui_dialog_notification', UiDialogNotification=NotificationCls),
        'distributor': _module('distributor'),
        'distributor.shared_messages': _module('distributor.shared_messages', IconInfoData=IconInfoData),
        'zone': _module('zone', Zone=Zone),
        'sims': _module('sims'),
        'sims.sim': _module('sims.sim', Sim=Sim),
        'sims.sim_info_types': _module('sims.sim_info_types'),
        'sims.household_enums': _module('sims.household_enums',
                                        HouseholdChangeOrigin=types.SimpleNamespace(CHEAT='CHEAT')),
        'sims.occult': _module('sims.occult'),
        'sims.occult.occult_enums': _module('sims.occult.occult_enums', OccultType=OccultEnumObj),
        'sims.occult.occult_tracker': _module('sims.occult.occult_tracker', OccultTracker=OccultTracker),
        'objects': _module('objects'),
        'objects.object_enums': _module('objects.object_enums',
                                        ResetReason=types.SimpleNamespace(RESET_EXPECTED='RESET_EXPECTED')),
        'relationships': _module('relationships'),
        'relationships.relationship_track': _module('relationships.relationship_track', RelationshipTrack=types.SimpleNamespace(
            FRIENDSHIP_TRACK=friendship_track, ROMANCE_TRACK=romance_track)),
        'protocolbuffers': _module('protocolbuffers', Consts_pb2=types.SimpleNamespace(TELEMETRY_MONEY_CHEAT=1)),
        'autonomy': _module('autonomy'),
        'autonomy.settings': _module('autonomy.settings',
                                     AutonomyState=types.SimpleNamespace(FULL='FULL', LIMITED_ONLY='LIMITED_ONLY'),
                                     AutonomySettingsGroup=types.SimpleNamespace(DEFAULT='DEFAULT')),
        'sims4.math': _module('sims4.math', Vector3=Vector3,
                              Location=lambda transform, surface: types.SimpleNamespace(transform=transform,
                                                                                        routing_surface=surface),
                              Transform=lambda pos, orientation: types.SimpleNamespace(translation=pos,
                                                                                       orientation=orientation)),
        'alarms': _module('alarms', add_alarm_real_time=add_alarm_real_time,
                          cancel_alarm=lambda h: setattr(h, 'cancelled', True)),
        'clock': _module('clock', interval_in_real_seconds=lambda s: s),
    }
    sys.modules.update(mods)
    for name, m in mods.items():                # a package knows its submodules, as after a real import
        if '.' in name:
            parent, child = name.rsplit('.', 1)
            setattr(mods[parent], child, m)
    g.Types, g.Zone, g.Sim = Types, Zone, Sim
    return g


def uninstall():
    for n in MODULE_NAMES:
        sys.modules.pop(n, None)
    sys.modules.update(_saved)
    _saved.clear()
    for n in [n for n in sys.modules if n.split('.')[0] == 'novulon']:
        del sys.modules[n]
