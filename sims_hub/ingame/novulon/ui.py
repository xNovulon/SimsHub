"""Novulon's menus: pages of rows with icons, Back, text boxes, OK/Cancel questions, Sim pickers and notifications.

The only file that builds the game's dialogs. Every feature describes what it wants as a Page of Rows; this file
turns it into the game's object picker (a list, or big tiles for the main menu), shows it, and runs the picked row.

How a page works:
  * A page is made by a builder - a function of the connection returning a Page - so going Back, or coming back
    after an action, always shows fresh values (counts, toggles, names) instead of a stale copy.
  * open(conn, builder) starts a new menu; push(conn, builder) goes one page deeper (it gets a Back row); show(conn)
    redraws the page on top.
  * A row's action(conn) may return a builder or a Page (shown one deeper), STAY (the page is drawn again), BACK, or
    None when it shows something itself (a text box, a question, a Sim picker) and carries on from there.

Verified against this game build's own code (ui/ui_dialog_picker.pyc, ui/ui_dialog.pyc, ui/ui_dialog_generic.pyc,
ui/ui_text_input.pyc):
  * ObjectPickerRow(name=, row_description=, icon=, is_enable=, is_selected=, row_tooltip=): name and description
    are string values, the tooltip is a callable; icon is a resource key (.type/.group/.instance are read).
  * UiObjectPicker / UiSimPicker / UiDialogOkCancel / UiDialogTextInputOkCancel take title=, text=, subtitle= as
    callables, and icon= as a callable of the resolver returning IconInfoData. Pickers take picker_type,
    min_selectable and max_selectable as plain ints.
  * A text box: UiTextInput.TunableFactory(locked_args={'sort_order': n}).default() - exactly how the game makes the
    inputs of its own text dialogs - with default_text / initial_value replaced by callables; the dialog's
    text_inputs must be dict-like AND read by attribute (it calls .items() and hasattr()), so an AttributeDict. The
    typed text is in dialog.text_input_responses[name] once OK is pressed.
  * OK is ButtonType.DIALOG_RESPONSE_OK (10001).
"""
from . import common, icons

STAY = object()
BACK = object()
DIALOG_RESPONSE_OK = 10001


class Row:
    """One line of a page. action(conn) -> builder / Page / STAY / BACK / None. A disabled row shows `reason` as its
    tooltip and can't be picked. label and desc are text or the game's own strings; icon is a Novulon icon name or
    the game's own icon key."""
    __slots__ = ('label', 'action', 'icon', 'desc', 'enabled', 'reason', 'selected')

    def __init__(self, label, action=None, icon=None, desc='', enabled=True, reason='', selected=False):
        self.label = label
        self.action = action
        self.icon = icon
        self.desc = desc
        self.enabled = enabled and action is not None
        self.reason = reason
        self.selected = selected


def info(label, desc='', icon='info'):
    """A row that only shows something (picking it just shows the page again)."""
    return Row(label, lambda c: STAY, icon=icon, desc=desc)


class Page:
    """What a page shows. style 'tiles' = the main menu's big tiles, else a list. icon = an icon name for the top of
    the dialog (the logo when none); sim = a SimInfo whose portrait shows there instead."""
    __slots__ = ('title', 'rows', 'subtitle', 'style', 'icon', 'sim')

    def __init__(self, title, rows, subtitle='', style='list', icon=None, sim=None):
        self.title = title
        self.rows = [r for r in rows if r is not None]
        self.subtitle = subtitle
        self.style = style
        self.icon = icon
        self.sim = sim


# ------------------------------------------------------------------ the page stack, one per player connection
_stacks = {}


def _key(conn):
    """The game passes a command's connection as a number; anything else is keyed by its id attribute."""
    if conn is None:
        return 0
    if isinstance(conn, int):
        return conn
    return getattr(conn, 'id', None) or 0


def _stack(conn):
    return _stacks.setdefault(_key(conn), [])


def reset_all():
    """Forget every open menu (going back to the game's main menu)."""
    _stacks.clear()


def _as_builder(x):
    if isinstance(x, Page):
        return lambda _conn, _p=x: _p
    return x


def open(conn, builder):                       # noqa: A001 - the menu's own verb
    """Start a new menu with this page."""
    st = _stack(conn)
    del st[:]
    st.append(_as_builder(builder))
    show(conn)


def push(conn, builder):
    """One page deeper (it gets a Back row)."""
    _stack(conn).append(_as_builder(builder))
    show(conn)


def back(conn):
    st = _stack(conn)
    if len(st) > 1:
        st.pop()
    show(conn)


def replace(conn, builder):
    """Show another page in place of the one on top (no extra Back step)."""
    st = _stack(conn)
    if st:
        st[-1] = _as_builder(builder)
    else:
        st.append(_as_builder(builder))
    show(conn)


def show(conn):
    """Draw the page on top again."""
    st = _stack(conn)
    if not st:
        return
    try:
        page = st[-1](conn)
    except Exception:
        common.log_exception('building a page')
        notify('Novulon', "That page couldn't open. The details are in Novulon's log.", icon='warning')
        return
    if page is None:
        return
    if not isinstance(page, Page):              # a row gave an action where a page belongs: it has run, so show
        common.log_exception('a page builder gave %r' % (page,))     # the page underneath instead of a blank one
        if len(st) > 1:
            st.pop()
            show(conn)
        return
    rows = list(page.rows)
    if len(st) > 1:
        rows.insert(0, Row('Back', lambda c: BACK, icon='back'))
    _show_picker(conn, page, rows)


def _run(conn, row):
    try:
        result = row.action(conn)
    except Exception:
        common.log_exception('running "%s"' % (row.label if isinstance(row.label, str) else 'a row'))
        notify('Novulon', 'Something went wrong. The details are in Novulon\'s log.', icon='warning')
        return
    if result is None:
        return
    if result is STAY:
        show(conn)
    elif result is BACK:
        back(conn)
    else:
        push(conn, result)


# ------------------------------------------------------------------ dialog pieces
def _dialog_icon(name=None, sim=None):
    if sim is not None:
        return lambda *_a, **_k: icons.of_sim(sim)
    data = icons.info(name or icons.LOGO)
    return lambda *_a, **_k: data


def _accepted(dialog):
    acc = getattr(dialog, 'accepted', None)
    if acc is not None:
        return bool(acc)
    return getattr(dialog, 'response', None) == DIALOG_RESPONSE_OK


def _show_picker(conn, page, rows):
    from ui.ui_dialog_picker import UiObjectPicker, ObjectPickerRow, ObjectPickerType
    raw = common.raw
    by_id = {}
    kw = dict(title=common.raw_fn(page.title),
              picker_type=ObjectPickerType.OBJECT_LARGE if page.style == 'tiles' else ObjectPickerType.OBJECT,
              min_selectable=1, max_selectable=1, icon=_dialog_icon(page.icon, page.sim))
    if page.subtitle:
        kw['text'] = common.raw_fn(page.subtitle)
    dlg = UiObjectPicker.TunableFactory().default(None, **kw)
    for row in rows:
        rkw = dict(name=raw(row.label), is_enable=row.enabled, is_selected=bool(row.selected))
        if row.desc:
            rkw['row_description'] = raw(row.desc)
        if not row.enabled and row.reason:
            rkw['row_tooltip'] = (lambda _t=row.reason: raw(_t))
        k = icons.key(row.icon)
        if k is not None:
            rkw['icon'] = k
        built = ObjectPickerRow(**rkw)
        dlg.add_row(built)
        by_id[id(built)] = row

    def on_response(dialog):
        if not _accepted(dialog):
            return
        try:
            picked = [by_id[id(o)] for o in dialog.get_result_rows() if id(o) in by_id]
        except Exception:
            return
        if picked:
            _run(conn, picked[0])

    dlg.show_dialog(on_response=lambda d: common.guarded('menu answer', on_response, d))


def notify(title, text, icon=icons.LOGO, sim=None):
    """A notification in the corner, with the Novulon logo (or a Sim's portrait). Returns True when shown."""
    try:
        from ui.ui_dialog_notification import UiDialogNotification
        dlg = UiDialogNotification.TunableFactory().default(
            None, title=common.raw_fn(title), text=common.raw_fn(text), icon=_dialog_icon(icon, sim))
        dlg.show_dialog()
        return True
    except Exception:
        common.log_exception('notify')
        return False


def confirm(conn, title, text, on_yes, ok='OK', cancel='Cancel', icon='warning', on_no=None):
    """An OK / Cancel question. on_yes(conn) runs on OK; on Cancel on_no(conn) runs, or the page shows again."""
    from ui.ui_dialog import UiDialogOkCancel

    def on_response(dialog):
        if _accepted(dialog):
            on_yes(conn)
        elif on_no is not None:
            on_no(conn)
        else:
            show(conn)                  # Cancel: back to the page the question came from

    dlg = UiDialogOkCancel.TunableFactory().default(
        None, title=common.raw_fn(title), text=common.raw_fn(text), icon=_dialog_icon(icon),
        text_ok=common.raw_fn(ok), text_cancel=common.raw_fn(cancel), include_cancel_response=True)
    dlg.show_dialog(on_response=lambda d: common.guarded('question answer', on_response, d))


def ask_text(conn, title, text, on_done, initial='', hint='', icon='edit'):
    """A text box. on_done(conn, typed_text) runs on OK with what was typed (stripped); Cancel shows the page again."""
    from ui.ui_dialog_generic import UiDialogTextInputOkCancel
    from ui.ui_text_input import UiTextInput
    from sims4.collections import AttributeDict
    box = UiTextInput.TunableFactory(locked_args={'sort_order': 0}).default()
    if initial != '' and initial is not None:
        box.initial_value = common.raw_fn(initial)
    if hint:
        box.default_text = common.raw_fn(hint)

    def on_response(dialog):
        if not _accepted(dialog):
            show(conn)                  # Cancel: back to the page the text box came from
            return
        typed = (getattr(dialog, 'text_input_responses', None) or {}).get('text')
        on_done(conn, (typed or '').strip())

    dlg = UiDialogTextInputOkCancel.TunableFactory().default(
        None, title=common.raw_fn(title), text=common.raw_fn(text), icon=_dialog_icon(icon),
        text_inputs=AttributeDict({'text': box}), text_ok=common.raw_fn('OK'), text_cancel=common.raw_fn('Cancel'),
        include_cancel_response=True)
    dlg.show_dialog(on_response=lambda d: common.guarded('text box answer', on_response, d))


def ask_number(conn, title, text, on_done, initial=None, minimum=None, maximum=None, whole=True, icon='edit'):
    """A text box for a number. Something that isn't a number in range says so and asks again."""
    def done(c, typed):
        try:
            value = int(typed.replace(',', '')) if whole else float(typed.replace(',', '.'))
        except ValueError:
            value = None
        if value is None or (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
            rng = ''
            if minimum is not None and maximum is not None:
                rng = ' from %s to %s' % (minimum, maximum)
            notify(title, 'Type a number%s.' % rng, icon='warning')
            ask_number(c, title, text, on_done, typed, minimum, maximum, whole, icon)
            return
        on_done(c, value)
    ask_text(conn, title, text, done, '' if initial is None else initial, icon=icon)


def pick_sims(conn, title, sim_infos, on_done, subtitle='', multi=False, selected=()):
    """The game's Sim picker (portraits). on_done(conn, [SimInfo...]) runs with what was picked on OK; Cancel shows
    the page again."""
    from ui.ui_dialog_picker import UiSimPicker, SimPickerRow
    from . import game
    sims = list(sim_infos)
    if not sims:
        notify(title, 'No Sims to show here.', icon='info')
        return
    by_id = {}
    kw = dict(title=common.raw_fn(title), min_selectable=0 if multi else 1, max_selectable=len(sims) if multi else 1)
    if subtitle:
        kw['text'] = common.raw_fn(subtitle)
    dlg = UiSimPicker.TunableFactory().default(None, **kw)
    chosen = set(selected)
    for si in sims:
        row = SimPickerRow(sim_id=si.id, select_default=False, sim_location=None,
                           household_id=getattr(si, 'household_id', None),
                           name=common.raw(game.name(si)), row_description=common.raw(game.summary(si)),
                           is_selected=si.id in chosen)
        dlg.add_row(row)
        by_id[id(row)] = si

    def on_response(dialog):
        if not _accepted(dialog):
            show(conn)                  # Cancel: back to the page the picker came from
            return
        try:
            picked = [by_id[id(o)] for o in dialog.get_result_rows() if id(o) in by_id]
        except Exception:
            picked = []
        if picked or multi:
            on_done(conn, picked)

    dlg.show_dialog(on_response=lambda d: common.guarded('Sim picker answer', on_response, d))


def choose(title, options, on_pick, subtitle='', icon=None):
    """A page builder listing options [(label, value, desc, icon)]; picking one runs on_pick(conn, value)."""
    def build(_conn):
        rows = [Row(label, (lambda c, v=value: on_pick(c, v)), icon=ic or icon, desc=desc or '')
                for label, value, desc, ic in options]
        return Page(title, rows, subtitle=subtitle)
    return build
