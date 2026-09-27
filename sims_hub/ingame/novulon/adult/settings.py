"""adult/settings.py - the Adult section's own two settings.json fields, named (SPEC.md Sec.7/
Sec.11):

    adult.enabled              - player opt-in, off by default (core `settings.py`'s own DEFAULTS)
    adult.interstitial_shown   - mod-wide, shown-once-ever flag ("a deliberate V1 simplification...
                                  mod-wide is strictly safer [than per-save]" - SPEC.md Sec.7)

The settings.json FILE itself (schema, migration, atomic write, the dotted-path `get`/`set`) is
core's (BP1, `ingame/novulon/settings.py`) - this file is only a thin, named wrapper so no other
package has to spell out either dotted path by hand. `settings_ui/` (BP12) is expected to call
`is_enabled()`/`set_enabled()` for its own "Adult Content" toggle row rather than reaching into core
settings directly.
"""
from .. import settings as _settings


def is_enabled():
    """The player's own Adult-content opt-in (off by default)."""
    return bool(_settings.get('adult.enabled', False))


def set_enabled(value):
    """Flip the player's opt-in. Does not itself check whether WickedWhims is present -
    `gate.is_adult_section_available()` is what actually decides whether the tile appears, so a
    player can switch this on ahead of installing WickedWhims with no ill effect."""
    return _settings.set('adult.enabled', bool(value))


def interstitial_shown():
    """Whether the "Adults only" notice has already been shown, ever (mod-wide, not per-save)."""
    return bool(_settings.get('adult.interstitial_shown', False))


def mark_interstitial_shown():
    """Record that the notice has now been shown - never shown again after this."""
    return _settings.set('adult.interstitial_shown', True)
