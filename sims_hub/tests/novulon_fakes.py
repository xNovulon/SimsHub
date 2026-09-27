"""Shared Tier 4 fakes for Novulon (SPEC.md Sec 16 Tier 4: "unit tests of the actual logic with a
small FakeSimInfo ..., driving sims/query.py's pure functions and commands.do(action_id,
fake_connection, ...) directly - no fake Sims folder or game DLL needed").

These are plain Python objects, no game import anywhere in this file - a Tier 4 test drives a
package's own real logic (sims/query.py, sims/delete.py, compat/*.py, gate.py, ...) with these
instead of a live SimInfo/services/reset service, entirely under this Python (no fake Sims 4 folder,
no game DLL). age/gender/species/occult_types on FakeSimInfo are plain ints or bitflags the *caller*
supplies (usually the real game's own Age/Gender/Species/OccultType values, copied over from whatever
the package under test imports at runtime) - this module never invents its own copies of those values,
so a test is only ever as wrong as the real enum it was given.

    from tests.novulon_fakes import FakeSimInfo, FakeHousehold, FakeConnection, FakeServices, \\
        FakeResetAndDeleteService, FakeInstanceManager

    active = FakeSimInfo(first_name='Alex', last_name='Doe')
    household = FakeHousehold(1, active=True, sims=[active])
    active.household = household
    bob = FakeSimInfo(first_name='Bob', last_name='Pancakes', household=FakeHousehold(2))
    services = FakeServices(active_sim_info=active, active_household_id=household.id)
    conn = FakeConnection()
    # drive delete.py's is_protected()/_delete_one() directly, or commands.do(action_id, conn, ...)
"""


class FakeHousehold:
    """Stand-in for sims.household.Household - just the surface is_protected()/menu code reads:
    is_active_household() and a name for a Household Funds-style row. `sims` is only kept for a test
    that wants to iterate a household's members; real Household.sim_info_gen() is the game name."""

    def __init__(self, id, name='Fake Household', active=False, sims=(), funds=0):
        self.id = id
        self.name = name
        self.funds = funds
        self._active = active
        self._sims = list(sims)

    def is_active_household(self):
        return self._active

    def sim_info_gen(self):
        for s in self._sims:
            yield s

    def __repr__(self):
        return 'FakeHousehold(%r, id=%r, active=%r)' % (self.name, self.id, self._active)


class _FakeSimInstance:
    """What FakeSimInfo.get_sim_instance() returns - just enough for FakeResetAndDeleteService to
    find its way back to the owning SimInfo, the same back-reference a real sim_instance carries."""

    def __init__(self, sim_info):
        self.sim_info = sim_info

    def __repr__(self):
        return 'FakeSimInstance(%r)' % (self.sim_info,)


class FakeSimInfo:
    """Stand-in for sims.sim_info.SimInfo. Fields SPEC.md Sec 16 Tier 4 names directly: id, first_name,
    last_name, age, gender, species, occult_types, household_id, is_instanced(). Extended with
    .household (a FakeHousehold or None), .get_sim_instance() and .remove_permanently() so
    sims/delete.py's is_protected()/_delete_one()/_finish() can be driven end to end with no game
    import at all.
    """
    _next_id = [1]

    def __init__(self, first_name='Test', last_name='Sim', age=0, gender=0, species=0, occult_types=0,
                 household=None, id=None, instanced=True):
        if id is None:
            id = FakeSimInfo._next_id[0]
            FakeSimInfo._next_id[0] += 1
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        self.age = age
        self.gender = gender
        self.species = species
        self.occult_types = occult_types
        self.household = household
        self.household_id = household.id if household is not None else None
        self._instanced = instanced
        self.removed = False
        self.remove_calls = []

    @property
    def full_name(self):
        return ('%s %s' % (self.first_name, self.last_name)).strip()

    def is_instanced(self):
        return self._instanced

    def get_sim_instance(self):
        return _FakeSimInstance(self) if self._instanced else None

    def remove_permanently(self, household=None):
        """Stand-in for SimInfo.remove_permanently - gaps.md Sec A.4: this is the point of no return,
        no undo path exists once it has run. Records the call; a real assertion is
        `sim_info.removed is True` / `sim_info.remove_calls == [household]`, never a return value."""
        self.removed = True
        self.remove_calls.append(household)

    def __repr__(self):
        return 'FakeSimInfo(%r, id=%r)' % (self.full_name, self.id)


class FakeConnection:
    """Stand-in for the game's client connection id (an opaque int on the real client - server_commands
    functions never inspect it structurally, they just pass it through to
    sims4.commands.CheatOutput(connection) or a dialog's owner). `.sent` records anything a test's own
    fake CheatOutput/notify hands it, so a Tier 4 test can assert on the console/notification text
    commands.do(action_id, conn, ...) produced, the same way real cheat output is read back in
    tests/test_ingame.py's own GameDllTests."""

    def __init__(self, id=1):
        self.id = id
        self.sent = []

    def write(self, text):
        self.sent.append(text)

    def __int__(self):
        return self.id

    def __repr__(self):
        return 'FakeConnection(%r)' % (self.id,)


class FakeInstanceManager:
    """Stand-in for services.get_instance_manager(...) - compat/*.py's probe() only ever calls
    .get(instance_id) is not None (SPEC.md Sec 10). `known` is the set of instance ids this manager
    'has' (e.g. MCCC's or WickedWhims's own pinned interaction-tuning id)."""

    def __init__(self, known=()):
        self.known = set(known)

    def get(self, instance_id):
        return object() if instance_id in self.known else None


class FakeResetAndDeleteService:
    """Stand-in for services.get_reset_and_delete_service(). gaps.md Sec A.2 disassembled the real
    trigger_destroy() as the start of an async state machine (PENDING -> ... -> DESTROY), never a
    synchronous call - this fake matches that shape: trigger_destroy() itself only records the call and
    never mutates anything by itself. Call `finish_now(sim_info)` (or let `auto_finish=True` do it
    immediately) to simulate the Sim actually leaving the instanced set, the way delete.py's own
    _await_uninstanced poll would eventually observe. A sim id left out of both is a Sim that "never
    leaves the instanced set" - the exact bounded-timeout-and-skip path SPEC.md Sec 16 Tier 4 asks be
    provably exercised, not just the happy path."""

    def __init__(self, auto_finish=True):
        self.calls = []
        self.auto_finish = auto_finish

    def trigger_destroy(self, sim_instance, *args, **kwargs):
        self.calls.append(sim_instance)
        if self.auto_finish:
            self.finish_now(sim_instance)

    def finish_now(self, sim_instance_or_info):
        """Flip the target FakeSimInfo's is_instanced() to False right now, simulating the async
        state machine having reached DESTROY. Safe to call whether given a _FakeSimInstance (what
        FakeSimInfo.get_sim_instance() returns) or a bare FakeSimInfo."""
        sim_info = getattr(sim_instance_or_info, 'sim_info', sim_instance_or_info)
        sim_info._instanced = False


class FakeServices:
    """Stand-in for the handful of `services` module names Novulon's own code calls directly (per
    SPEC.md's own snippets in Sec 5.6/Sec 10/Sec 11): active_sim_info(), active_household_id(),
    get_reset_and_delete_service(), get_instance_manager(instance_type). Not the whole `services`
    module - just enough that a package's own code can have its `services` import monkeypatched to one
    of these in a Tier 4 test, with no game import anywhere in the test."""

    def __init__(self, active_sim_info=None, active_household_id=None, reset_and_delete_service=None,
                 instance_managers=None):
        self._active_sim_info = active_sim_info
        self._active_household_id = active_household_id
        self.reset_and_delete_service = reset_and_delete_service or FakeResetAndDeleteService()
        self.instance_managers = dict(instance_managers or {})

    def active_sim_info(self):
        return self._active_sim_info

    def active_household_id(self):
        return self._active_household_id

    def get_reset_and_delete_service(self):
        return self.reset_and_delete_service

    def get_instance_manager(self, instance_type):
        return self.instance_managers.get(instance_type)
