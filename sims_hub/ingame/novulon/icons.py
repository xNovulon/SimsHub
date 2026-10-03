"""Novulon's icons by name - the same names as tools/novulon_glyphs.py, drawn into Novulon_Tuning.package.

Each icon is an image resource (type 0x00B2D882, group 0) whose instance is instance(name). The game asks for an icon
by the key type 0x2F7D0004, group 0x80000000 and that same instance - the pairing the pie menu's own icon uses in
the package's interaction tuning ('2f7d0004:80000000:<instance>'), which the game shows. A row, a dialog or a
notification given key(name) therefore shows the same picture.
"""
ICON_TYPE = 0x2F7D0004
ICON_GROUP = 0x80000000
LOGO = 'logo'


def fnv64(text):
    """FNV-1 64-bit of the lower-cased text (tools/novulon_ids does the same at build time)."""
    h = 0xCBF29CE484222325
    for b in text.lower().encode('utf-8'):
        h = ((h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF) ^ b
    return h


def instance(name):
    """The icon resource's instance id: top bit set, so it can never be one of the game's own."""
    return fnv64('novulon_icon_' + name) | 0x8000000000000000


def key(name):
    """The resource key a picker row, a dialog or a notification takes as its icon; None for no name. A key the game
    already has (a trait's or a skill's own icon) is passed through."""
    if not name:
        return None
    if not isinstance(name, str):
        return name if getattr(name, 'instance', 0) else None
    from sims4.resources import Key
    return Key(ICON_TYPE, instance(name), ICON_GROUP)


def info(name):
    """The icon as the IconInfoData dialogs and notifications use; None for no name."""
    k = key(name)
    if k is None:
        return None
    from distributor.shared_messages import IconInfoData
    return IconInfoData(icon_resource=k)


def of_sim(sim_info):
    """A Sim's own portrait as dialog icon data, or the Novulon logo when the portrait can't be made."""
    try:
        from distributor.shared_messages import IconInfoData
        return IconInfoData(obj_instance=sim_info)
    except Exception:
        return info(LOGO)
