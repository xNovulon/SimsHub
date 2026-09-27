"""UI Cheats Extension - documented no-op (SPEC.md Sec 10).

UI Cheats Extension binds to existing HUD elements (right-click a need/relationship bar) - it ships no
custom STBL, no custom dialogs, and shares no resource-id surface with Novulon at all (confirmed
installed on this machine as `UI_Cheats_Extension.package` + `UI_Cheats_Extension_Scripts.ts4script`;
not opened further - by SPEC.md Sec 10's own description there is nothing here to probe against). This
file exists purely so a future audit has one obvious place to add a real check if that ever stops being
true.

`is_present()` returns `None`, not `False` - deliberately distinct from every other probe in this
package, so a caller can tell "not checked, nothing to know" from "checked, and it's genuinely absent".
`should_defer()` always returns `False` (no known conflict surface to defer for). Both are safe to call
unconditionally from `settings_ui`/`gameplay` today, and will keep returning the same answer even if a
real probe is filled in here later - no caller needs to change when that happens.
"""


def is_present():
    return None


def should_defer(_feature):
    return False
