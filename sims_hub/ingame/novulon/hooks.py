"""Install wrappers around game functions, once, without ever changing what the game does.

Same verified pattern as speedkit_monitor/hooks.py (that module's docstring cites the exact bytecode
that makes attribute-replacement work: areaserver's C++ callers reach game functions through
LOAD_GLOBAL/LOAD_METHOD on the module or class, at call time, so replacing the attribute takes effect
for every later call). Novulon's own use is `zone.Zone.start_services` (entry.py) - the identical
attribute speedkit_monitor/loadtimer.py already wraps live, confirmed unchanged in this build's
simulation.zip:zone.pyc this session (`Zone.start_services` is a method of the `Zone` class).

A wrapper made here:
  * calls the original with exactly the arguments it got and returns (or raises) exactly what it did;
  * runs our 'before'/'after' code through common.guarded(), so our errors are logged, never raised;
  * is installed at most once per attribute (marked with __novulon_orig__) and never removed, so a mod
    that wraps on top of us later is never cut out of the chain.
"""
from . import common

MARK = '__novulon_orig__'


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

    before/after receive the positional arguments orig was called with (self first for methods). after
    runs when orig returned normally, or also when it raised if always=True (result is then None; the
    game's exception still propagates unchanged)."""
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
