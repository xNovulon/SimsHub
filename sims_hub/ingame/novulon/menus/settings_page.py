"""Settings: the Adult tile on or off, which other mods Novulon sees, and where its log is."""
from .. import common, compat, settings, ui


def _toggle_adult(conn):
    if not compat.wickedwhims_present() or compat.adult_blocked():
        return ui.STAY
    settings.set('adult_enabled', not settings.get('adult_enabled'))
    return ui.STAY


def build(conn):
    ww = compat.wickedwhims_present()
    blocked = ww and compat.adult_blocked()
    usable = ww and not blocked
    on = bool(settings.get('adult_enabled')) and usable
    rows = [
        ui.Row('Adult tile: %s' % ('On' if on else 'Off'), _toggle_adult if usable else None,
               icon='on' if on else 'off',
               desc=('WickedWhims settings in the main menu, for adult Sims only' if usable else
                     'Off while mods for sexual content with minors are installed' if blocked else 'Needs WickedWhims'),
               reason=compat.BLOCKED_NOTE if blocked else 'WickedWhims isn\'t installed.'),
        ui.Row('Mods Novulon works with', lambda c: compat_page, icon='compat'),
        ui.Row('About Novulon', lambda c: about_page, icon='info', desc='Version %s' % common.VERSION),
    ]
    return ui.Page('Settings', rows, icon='settings')


def compat_page(conn):
    ww = compat.wickedwhims_version() if compat.wickedwhims_present() else None
    rows = [
        ui.info('WickedWhims', ('Installed (%s)' % ww) if ww else 'Not installed', icon='adult' if ww else 'off'),
        ui.info('MC Command Center', 'Installed - both work side by side' if compat.mccc_present() else 'Not installed',
                icon='check' if compat.mccc_present() else 'off'),
    ]
    return ui.Page('Mods Novulon works with', rows, icon='compat')


def about_page(conn):
    rows = [
        ui.info('Novulon %s' % common.VERSION, 'novulon.pages.dev', icon='logo'),
        ui.info('Log file', common.log_path() or 'No log yet', icon='log'),
    ]
    return ui.Page('About Novulon', rows, icon='info')
