"""Install wrappers around game functions, once, without ever changing what the game does.

Why class/module attributes work for every hook we use (checked in the game's bytecode, build 1.126.73):
  * areaserver.c_api_notify_client_in_main_menu calls services.on_enter_main_menu() via
    LOAD_GLOBAL services + LOAD_METHOD, i.e. an attribute lookup on the module at call time;
  * areaserver.c_api_zone_init calls zone.start_services(...) and areaserver.c_api_server_tick calls
    zone.update(...) via LOAD_METHOD on the Zone instance, i.e. a lookup on the class at call time;
  * the cheat 'zone.loading_screen_animation_finished' calls
    services.current_zone().on_loading_screen_animation_finished() the same way.
So replacing the attribute on the module/class takes effect for every later call, even if C++ caches
the areaserver function objects themselves.

A wrapper made here:
  * calls the original with exactly the arguments it got and returns (or raises) exactly what it did;
  * runs our 'before'/'after' code through common.guarded(), so our errors are logged, never raised;
  * is installed at most once per attribute (marked with __speedkit_orig__) and never removed, so a
    mod that wraps on top of us later is never cut out of the chain.
"""
from . import common

MARK = '__speedkit_orig__'


def current(owner, name):
    """The attribute as stored on owner (its own __dict__ for classes, so inherited ones are not moved)."""
    if isinstance(owner, type) and name in owner.__dict__:
        return owner.__dict__[name]
    return getattr(owner, name)


def is_wrapped(owner, name):
    """True if owner.name is (still) one of our wrappers."""
    try:
        return getattr(current(owner, name), MARK, None) is not None
    except Exception:
        return False


def install(owner, name, make_wrapper, label):
    """Replace owner.name by make_wrapper(original) unless we already did. Returns True on success."""
    try:
        if is_wrapped(owner, name):
            return True
        orig = current(owner, name)
        if not callable(orig):
            common.log('hook %s: %r is not callable, not hooked' % (label, orig))
            return False
        wrapper = make_wrapper(orig)
        for attr in ('__name__', '__qualname__', '__doc__'):
            try:
                setattr(wrapper, attr, getattr(orig, attr))
            except Exception:
                pass
        setattr(wrapper, MARK, orig)
        wrapper.__wrapped__ = orig
        setattr(owner, name, wrapper)
        return True
    except Exception:
        common.log_exception('installing hook ' + label)
        return False


def around(orig, before=None, after=None, label='', always=False):
    """A wrapper that runs before(args) and after(args, result) around orig; our code can never raise.

    before/after receive the positional arguments orig was called with (self first for methods).
    after runs when orig returned normally, or also when it raised if always=True (result is then None;
    the game's exception still propagates unchanged). Events such as 'the loading screen finished' did
    happen even when some mod broke inside the game's handler, so their hooks use always=True."""
    def wrapper(*args, **kwargs):
        if before is not None:
            common.guarded(label + ' (before)', before, args)
        ok, result = False, None
        try:
            result = orig(*args, **kwargs)
            ok = True
            return result
        finally:
            if after is not None and (ok or always):
                common.guarded(label + ' (after)', after, args, result)
    return wrapper
