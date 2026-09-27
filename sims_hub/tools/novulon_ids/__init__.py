"""Every resource/string id Novulon writes, one file per build package.

SPEC.md's own design (`§3`, `§14.4`) calls for a single, shared, append-only `tools/novulon_ids.py` that
every feature package adds a line to. Several packages are built in parallel in this working tree, so a
single shared file is a write race; the build task overrides that one point of the design: each package
gets its own file here (`novulon_ids/<package>.py`), and this `__init__.py` is the aggregator - it imports
every sibling module and re-exports every UPPER_CASE name they define, so calling code still writes the
one-shared-file API the spec describes:

    from tools import novulon_ids as ids
    ids.INTERACTION_OPEN_MENU

Import fails loudly, at import time, if:
  * two sibling files define the same NAME (a name collision - a merge conflict two builders both missed), or
  * two different NAMEs resolve to the same numeric id (a hash collision or a copy-pasted constant).
Never edit another package's file here - add your own `<package>.py` next to the others.
"""
import importlib
import os
import pkgutil

_owners = {}      # name -> (package, value)
_by_value = {}     # value -> (package, name), int-valued names only


def _collect():
    pkg_dir = os.path.dirname(__file__)
    mods = sorted(m.name for m in pkgutil.iter_modules([pkg_dir]) if not m.name.startswith('_'))
    for modname in mods:
        mod = importlib.import_module('.' + modname, __name__)
        for name in dir(mod):
            if not name.isupper():
                continue
            value = getattr(mod, name)
            if name in _owners:
                other_pkg, other_value = _owners[name]
                if other_pkg != modname:
                    raise ValueError('novulon_ids: %r is defined by both %s and %s' % (name, other_pkg, modname))
                continue
            _owners[name] = (modname, value)
            globals()[name] = value
            if isinstance(value, int):
                if value in _by_value and _by_value[value][1] != name:
                    prev_pkg, prev_name = _by_value[value]
                    raise ValueError('novulon_ids: %s.%s and %s.%s both resolve to id 0x%X'
                                     % (modname, name, prev_pkg, prev_name, value))
                _by_value[value] = (modname, name)


def owner_of(name):
    """Which package file defines a given id name, e.g. owner_of('INTERACTION_OPEN_MENU') -> 'bp13_package_build'."""
    return _owners[name][0]


_collect()
