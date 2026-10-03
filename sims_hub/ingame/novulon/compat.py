"""Other mods Novulon knows about: WickedWhims (the Adult page uses its own settings functions) and MC Command Center
(only shown in Settings, so it's clear the two work side by side).

Mods that add sexual content with children or infants (All The Fallen and its core scripts) switch the Adult page off
for as long as any of their files are in the Mods folder: Novulon's adult features never run alongside them.

Checked when asked (the menu is open, so the game and every mod are loaded), never at import time.

WickedWhims' settings are read and written through its own functions, checked in WickedWhims' scripts:
wickedwhims/sex/sex_settings.pyc get_sex_setting(variable_name) / set_sex_setting(variable_name, value), and the same
pair in wickedwhims/nudity/nudity_settings and wickedwhims/relationships/relationship_settings - each takes the
setting's name as a string.
"""
import os
import sys

from . import common

CHILD_CONTENT_MARKS = ('allthefallen', 'fallencore')
BLOCKED_NOTE = ('The Adult page is off: mods for sexual content with minors (All The Fallen) are in the Mods folder. '
                'Remove them to use it.')
_child_content = None

WW_ROOT_ACTION_ID = 18173180371816048676         # WickedWhims' root Action tuning (an ACTION instance, not an interaction)
WW_MODULES = {'sex': 'wickedwhims.sex.sex_settings', 'nudity': 'wickedwhims.nudity.nudity_settings',
              'relationship': 'wickedwhims.relationships.relationship_settings'}


def wickedwhims_present():
    try:
        import services
        import sims4.resources
        mgr = services.get_instance_manager(sims4.resources.Types.ACTION)
        return mgr is not None and mgr.get(WW_ROOT_ACTION_ID) is not None
    except Exception:
        return False


def wickedwhims_version():
    def read():
        import importlib
        return importlib.import_module('wickedwhims.version_registry').get_mod_version_str()
    return common.guarded('WickedWhims version', read) if wickedwhims_present() else None


def child_content_mods():
    """File names in the Mods folder from mods for sexual content with minors. Looked up once per game session."""
    global _child_content
    if _child_content is None:
        found = []
        mods = os.path.join(common.sims_dir() or '', 'Mods')
        if common.sims_dir() and os.path.isdir(mods):
            for _root, _dirs, files in os.walk(mods):
                found += [f for f in files if any(m in f.lower() for m in CHILD_CONTENT_MARKS)]
        _child_content = sorted(found)
        if found:
            common.log('Adult page off: %d file(s) from mods for sexual content with minors in Mods' % len(found))
    return list(_child_content)


def adult_blocked():
    return bool(child_content_mods())


def mccc_present():
    return any(name.startswith('mc_') for name in list(sys.modules))


def ww_get(domain, name):
    """A WickedWhims setting's value, or None when it can't be read."""
    def read():
        import importlib
        mod = importlib.import_module(WW_MODULES[domain])
        return getattr(mod, 'get_%s_setting' % domain)(name)
    return common.guarded('WickedWhims setting ' + name, read) if wickedwhims_present() else None


def ww_set(domain, name, value):
    def write():
        import importlib
        mod = importlib.import_module(WW_MODULES[domain])
        getattr(mod, 'set_%s_setting' % domain)(name, value)
        return True
    return bool(common.guarded('WickedWhims setting ' + name, write)) if wickedwhims_present() else False
