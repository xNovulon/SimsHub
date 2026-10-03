"""Novulon's own settings, in <Sims 4>\\Novulon\\settings.json. Read once when the mod starts, written when one changes."""
import os

from . import common

DEFAULTS = {
    'adult_enabled': False,         # the Adult tile (needs WickedWhims); off until the player turns it on
    'adult_notice_seen': False,     # the one-time "for adult Sims only" note before the Adult page
    'obsession': {},                # Sim id -> 1 (obsessed) or 2 (extremely obsessed): obsession.py
    'obsession_fans': {},           # Sim id -> ids of the Sims who have seen them and are obsessed
}

_values = dict(DEFAULTS)


def _path():
    d = common.data_dir()
    return os.path.join(d, 'settings.json') if d else None


def load():
    path = _path()
    data = common.read_json(path) if path else None
    _values.clear()
    _values.update(DEFAULTS)
    if isinstance(data, dict):
        for k, v in data.items():
            if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])):
                _values[k] = v


def get(name):
    return _values.get(name, DEFAULTS.get(name))


def set(name, value):                       # noqa: A001 - settings' own verb
    _values[name] = value
    path = _path()
    if path:
        common.write_json(path, _values)
