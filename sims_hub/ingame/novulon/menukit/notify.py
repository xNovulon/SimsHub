"""Toast notifications with fixed defaults (SPEC.md `menukit/` §4).

Wraps `common.notify` (core-owned, BP1) with `UiDialogNotificationLevel.PLAYER`,
`UiDialogNotificationVisualType.INFORMATION`, `UiDialogNotificationUrgency.DEFAULT` - `URGENT` only for
a genuine failure toast. `ScreenSlam` is never used anywhere in this mod (SPEC.md §4).

Every one of these four enum members was independently re-verified for THIS installed game build
(`sims_hub/tools/pyc37.py "E:/The Sims 4/Data/Simulation/Gameplay/simulation.zip"
ui/ui_dialog_notification.pyc <EnumName>`, disassembling each nested enum body directly rather than
trusting the name):
    UiDialogNotification.UiDialogNotificationLevel:       PLAYER = 0, SIM = 1
    UiDialogNotification.UiDialogNotificationVisualType:  INFORMATION = 0, SPEECH = 1, SPECIAL_MOMENT = 2
    UiDialogNotification.UiDialogNotificationUrgency:     DEFAULT = 0, URGENT = 1
`UiDialogNotification.build_msg` (line 199) was also disassembled directly and stores these onto the
outgoing message as `self.urgency` -> `criticality`, `self.information_level` -> `information_level`,
`self.visual_type` -> `visual_type` - all three assigned with a plain `STORE_ATTR`, no `isinstance`/enum
check in that function, so passing the raw ints above (rather than importing the enum classes) is
verified-equivalent, not a guess. This module passes the raw ints so it never needs to import
`ui.ui_dialog_notification` itself (that stays `common.notify`'s job, matching SPEC.md §3's "menukit
never improvises its own dialog chaining" - here, its own notification chaining).

`common.notify`'s expected shape (this file's own contract with BP1, since `common.py` doesn't exist in
this working tree yet - see this package's build report): `notify(title, text, urgent=False,
level=None, visual_type=None)`. If BP1 ships a simpler `notify(title, text, urgent=False)` (the shape
`speedkit_monitor/common.py` already has), the `TypeError` from the extra kwargs is caught below and we
retry with just the three SpeedKit-compatible arguments - so this module works either way and never
hard-depends on BP1 landing the exact extended signature first.
"""

LEVEL_PLAYER = 0
VISUAL_INFORMATION = 0
URGENCY_DEFAULT = 0
URGENCY_URGENT = 1


def notify(title, text, urgent=False):
    """Show a toast: PLAYER level, INFORMATION visual type, DEFAULT urgency (URGENT if urgent=True).
    Never raises - returns False (and swallows the error) on any failure, same as every other
    game-facing menukit function."""
    try:
        from .. import common
    except Exception:
        return False
    try:
        return common.notify(title, text, urgent=urgent, level=LEVEL_PLAYER,
                              visual_type=VISUAL_INFORMATION)
    except TypeError:
        try:
            return common.notify(title, text, urgent=urgent)
        except Exception:
            return False
    except Exception:
        return False
