"""Pure-Python `Row`/`Page` data model (SPEC.md `menukit/` §4). No game imports here at all - every
other file in this package (and every feature package built on top of it) can construct/inspect these
without the game, which is the whole point of separating them out.

`Row` fields map onto the real `ui.ui_dialog_picker.BasePickerRow`/`ObjectPickerRow` constructor fields
(verified directly against this build's `ui/ui_dialog_picker.pyc` - see `render.py`'s module docstring
for the citations): `id` -> `option_id` (index-assigned by the engine, §render.py), `label` -> `name`,
`description` -> `row_description`, `tooltip` -> `row_tooltip`, `icon` -> `icon`, `selected` ->
`is_selected`, `disabled_text` sets `is_enable=False` and doubles as the row's tooltip when no other
tooltip is given (BasePickerRow has no separate "why is this disabled" field - `gaps.md`/`game_api.md`
name none - so the disabled reason is the most useful thing to put in the tooltip slot).
"""

BACK_ID = '__back__'


class Row(object):
    """One row. `on_activate(connection, selected_ids=None) -> Page | None` (SPEC.md §4):
    returning a `Page` pushes it; returning `None` means the row already did everything itself (a
    destructive row that shows its own confirm/notify flow, or a filter chip that mutated caller-owned
    state and called `menukit.show_page(connection, rebuilt_page, push=False)` itself to rebuild the
    current page in place instead of going deeper - see `stack.py`/`render.py`).
    """

    __slots__ = ('id', 'label', 'description', 'tooltip', 'icon', 'disabled_text', 'selected', 'tags',
                 'sim_id', 'household_id', 'on_activate')

    def __init__(self, id, label, description='', tooltip='', icon=None, disabled_text=None,
                 selected=False, tags=(), sim_id=None, household_id=None, on_activate=None):
        if not id:
            raise ValueError('menukit.Row: id is required (%r)' % (label,))
        self.id = id
        self.label = label
        self.description = description
        self.tooltip = tooltip
        self.icon = icon
        self.disabled_text = disabled_text
        self.selected = bool(selected)
        self.tags = tuple(tags)
        # sim_id/household_id are NOT part of SPEC.md's illustrative Row signature - they exist only
        # so a caller can tag a Row as "this represents this Sim" for its own bookkeeping (e.g. the
        # tray-delta helpers in stack.py). menukit's own render.py never builds a game SimPickerRow
        # from a Row - see render.py's module docstring for the verified reason a Sim Browser row
        # can't be a generic Row at all (UiSimPicker only accepts SimPickerRow, UiObjectPicker only
        # accepts ObjectPickerRow - the two dialog classes are mutually exclusive about row type).
        self.sim_id = sim_id
        self.household_id = household_id
        self.on_activate = on_activate

    @property
    def enabled(self):
        return self.disabled_text is None

    def __repr__(self):
        return 'Row(%r, %r)' % (self.id, self.label)


class Page(object):
    """One screen. `rows` is the content only - never include the synthetic Back row or the search
    row yourselves; `stack.py` prepends Back (§stack.py) and `search.py` builds the pinned search row
    for you when `search=True`.

    style: 'list' (UiObjectPicker, ObjectPickerType.OBJECT) or 'tiles' (UiObjectPicker,
    ObjectPickerType.OBJECT_LARGE - Main Menu only, verified value 12, SPEC.md §2/§21).
    row_style: 'default' or 'delete' -> ObjectPickerRow.object_picker_style (verified enum,
    render.py's docstring). Every row on a page shares one row_style; `sims/delete.py` (BP6) is the
    only caller expected to pass 'delete'.
    multi_select / min_selectable / max_selectable: SPEC.md's own §4 signature. Passing a plain int for
    max_selectable is verified safe (render.py's docstring, `build_object_picker`'s own
    `isinstance(self.max_selectable, int)` fast path) - this closes `gaps.md` §B.6's open item, at
    least for the plain-int path menukit always uses. `max_selectable=0` means "unlimited" (matches
    the engine's own `multi_select` property treating 0 as multi-select-unlimited).
    on_select(connection, selected_ids) -> Page | None: only used when multi_select is True; called
    once when the dialog's OK response comes back, with every id CHECKED ON THIS PAGE (not the whole
    cross-page tray - see stack.apply_selection_delta for folding this into a persistent tray).
    """

    __slots__ = ('title', 'rows', 'breadcrumb', 'subtitle', 'multi_select', 'min_selectable',
                 'max_selectable', 'search', 'style', 'row_style', 'on_select')

    def __init__(self, title, rows, breadcrumb=(), subtitle=None, multi_select=False,
                 min_selectable=None, max_selectable=None, search=False, style='list',
                 row_style='default', on_select=None):
        if style not in ('list', 'tiles'):
            raise ValueError('menukit.Page: style must be list or tiles, got %r' % (style,))
        if row_style not in ('default', 'delete'):
            raise ValueError('menukit.Page: row_style must be default or delete, got %r' % (row_style,))
        self.title = title
        self.rows = list(rows)
        self.breadcrumb = tuple(breadcrumb)
        self.subtitle = subtitle
        self.multi_select = bool(multi_select)
        # Both fields are always resolved to a plain int here, never left None: `render.py`'s
        # docstring shows `UiDialogObjectPicker.multi_select` doing a raw `self.min_selectable < 1`
        # comparison (crashes on None) and `build_object_picker` branching on
        # `isinstance(self.max_selectable, int)` (the other branch calls `.get_max_selectable(...)` on
        # it, which crashes on None too) - so menukit never hands the engine a None here.
        if min_selectable is None:
            min_selectable = 0 if self.multi_select else 1
        self.min_selectable = min_selectable
        if max_selectable is None:
            max_selectable = 0 if self.multi_select else 1   # 0 == unlimited (verified, render.py)
        self.max_selectable = max_selectable
        self.search = bool(search)
        self.style = style
        self.row_style = row_style
        self.on_select = on_select

    def __repr__(self):
        return 'Page(%r, %d row(s))' % (self.title, len(self.rows))
