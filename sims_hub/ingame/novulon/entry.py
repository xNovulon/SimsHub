"""How Novulon is opened: a "Novulon" entry on every computer and tablet (the main menu) and on every Sim (that Sim's
own page).

Both entries are ImmediateSuperInteractions in Novulon_Tuning.package (tools/novulon_tuning.py). Each runs one console
command through its do_command extra: 'novulon.menu' for computers and tablets, 'novulon.sim <id>' for a Sim (the
clicked Sim's id comes in as the command's argument - the interaction's Object participant). Both commands are Live,
so they work without testingcheats.

Adding the entries: an object's pie menu is built from its tuning class's _super_affordances, read live every time,
so adding our interaction to that class tuple once covers every copy of that object, now and later. The game loads
every object's tuning at startup, so one pass over the loaded object tuning classes - right after the first lot has
started - is all it takes; later lot loads only look at classes that weren't there before (normally none), so a
travel costs nothing.
  * Computers and tablets: there is no shared computer class; each one's animation overrides name a computerType, or
    carryObject 'tablet' (the check the previous version shipped and that works in the game).
  * Sims: the Sim object's tuning class is a subclass of sims.sim.Sim.
"""
from . import common, hooks

# tools/novulon_ids/bp13_package_build.py: custom_id('Novulon_OpenMenu_Interaction') / custom_id('Novulon_SimMenu_Interaction').
# tests/test_novulon_entry.py checks these stay equal to the ids the package is built with.
MENU_INTERACTION_ID = 0xB60FE75296EA0C95
SIM_INTERACTION_ID = 0xC7AC5E453A12A9EE
MARK = 'NOVULON_ENTRY'

_seen = set()           # id() of every object tuning class already looked at this session
_registered = False


# ------------------------------------------------------------------ the two commands
def register_commands():
    global _registered
    if _registered:
        return
    import sims4.commands
    live = sims4.commands.CommandType.Live

    @sims4.commands.Command('novulon.menu', command_type=live)
    def novulon_menu(_connection=None):
        common.guarded('novulon.menu', open_main_menu, _connection)

    @sims4.commands.Command('novulon.sim', command_type=live)
    def novulon_sim(sim_id: int = 0, _connection=None):
        common.guarded('novulon.sim', open_sim_menu, sim_id, _connection)

    _registered = True


def open_main_menu(conn):
    from . import ui
    from .menus import main
    ui.open(conn, main.build)


def open_sim_menu(sim_id, conn):
    from . import ui, game
    from .menus import simcard
    si = game.sim_info_by_id(sim_id)
    if si is None:
        ui.notify('Novulon', "That Sim couldn't be found.", icon='warning')
        return
    ui.open(conn, simcard.builder(si.id))


# ------------------------------------------------------------------ adding the entries
def is_computer_class(cls):
    ov = getattr(cls, '_anim_overrides_cls', None)
    params = getattr(ov, 'params', None) if ov is not None else None
    if not params:
        return False
    try:
        return 'computerType' in params or params.get('carryObject') == 'tablet'
    except Exception:
        return False


def is_sim_class(cls, sim_base):
    try:
        return sim_base is not None and isinstance(cls, type) and issubclass(cls, sim_base)
    except Exception:
        return False


def _interaction(interaction_id):
    import services
    import sims4.resources
    mgr = services.get_instance_manager(sims4.resources.Types.INTERACTION)
    return mgr.get(interaction_id) if mgr is not None else None


def _add(cls, affordance):
    marks = cls.__dict__.get(MARK, ())          # this class's own mark, never one inherited from a parent class
    if affordance in marks:
        return False
    cls._super_affordances = tuple(cls._super_affordances) + (affordance,)
    setattr(cls, MARK, tuple(marks) + (affordance,))
    return True


def add_entries():
    """One pass over the object tuning classes not looked at yet. -> (computers, sims) newly given an entry."""
    import services
    import sims4.resources
    mgr = services.get_instance_manager(sims4.resources.Types.OBJECT)
    if mgr is None:
        return 0, 0
    menu_aff, sim_aff = _interaction(MENU_INTERACTION_ID), _interaction(SIM_INTERACTION_ID)
    if menu_aff is None and sim_aff is None:
        common.log("entries: Novulon_Tuning.package isn't loaded - is it in the Mods folder?")
        return 0, 0
    try:
        from sims.sim import Sim as sim_base
    except Exception:
        sim_base = None
    computers = sims = 0
    for cls in list(mgr.types.values()):
        k = id(cls)
        if k in _seen:
            continue
        _seen.add(k)
        try:
            if menu_aff is not None and is_computer_class(cls) and _add(cls, menu_aff):
                computers += 1
            elif sim_aff is not None and is_sim_class(cls, sim_base) and _add(cls, sim_aff):
                sims += 1
        except Exception:
            common.log_exception('entries: %r' % (cls,))
    if computers or sims:
        common.log('entries: added to %d computer/tablet and %d Sim tuning class(es)' % (computers, sims))
    return computers, sims


def _forget_menus():
    from . import ui
    ui.reset_all()


def install():
    """Hooks: after each lot starts (add the entries - only new classes are looked at), and on the game's main menu
    (forget every open Novulon menu)."""
    import zone
    import services
    hooks.install(zone.Zone, 'start_services',
                  lambda orig: hooks.around(orig, after=lambda a, r: common.guarded('entries', add_entries),
                                            label='novulon entries'),
                  'Zone.start_services (novulon entries)')
    hooks.install(services, 'on_enter_main_menu',
                  lambda orig: hooks.around(orig, after=lambda a, r: common.guarded('menus reset', _forget_menus),
                                            label='novulon menus reset', always=True),
                  'services.on_enter_main_menu (novulon menus reset)')
