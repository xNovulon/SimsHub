"""EA names BP4 (`ingame/novulon/sims/{__init__,query,browser}.py` - the Sim Browser) cites, every
row verified this session against this machine's real, installed game build with
`sims_hub/tools/pyc37.py "E:/The Sims 4/Data/Simulation/Gameplay/{simulation,core}.zip" <module>.pyc
[name]`, by hand, then cross-checked with `python tools/novulon_api_check.py` before being committed
here - not carried over from `research/game_api.md` on trust, even where that file already covered
the same class, because this build's exact enum member VALUES (not just their existence) are load-
bearing for `sims/query.py`'s bitflag filtering.

`query.py` itself imports nothing from the game (its own docstring: "no game import anywhere in this
file") - it only calls `getattr(sim_info, 'age', 0)`-style accesses on whatever object a caller hands
it. The `sims.sim_info`/`sims.sim_info_base_wrapper` rows below are cited because `browser.py` (the
one caller that ever hands `query.py` a REAL `SimInfo`) depends on those exact attributes existing on
it - "every EA name the code uses," per the build override, covers an attribute the code reads via
`getattr` on a real game object just as much as one it imports directly.

Rows this pass confirms match `research/game_api.md` Sec 3 exactly (Gender/Age/Species/OccultType's
member values, `services.sim_info_manager`/`household_manager`/`active_household_id` all being real
functions, `SimInfo.is_npc`/`household`/`household_id`/`is_instanced` all being real properties/
methods) - re-verified independently rather than assumed, plus one row `game_api.md` did not already
cite: `SimInfo.is_pregnant` (`sims/sim_info.pyc:1698`, guards `self._pregnancy_tracker is None` before
delegating - safe to call on any Sim, never raises), used by `query.badges_for`'s 'Pregnant' badge.

Game build note: this machine's installed build is `1.126.73.1030` (the Delta-folder Version.ini
value, the same one `bp1_bp3_core_inject.py`/`bp2_menukit.py` already cite and explain the two-
different-version-strings situation for - see either of those files' docstrings, not repeated here).
"""

CHECKED_AGAINST = '1.126.73.1030'

ROWS = [
    # services/__init__.pyc (a package - see bp1_bp3_core_inject.py's docstring for the '.__init__'
    # spelling this checker needs for a package module)
    ('services.__init__', 'sim_info_manager', 'function'),    # line 631: game_services.service_manager.sim_info_manager
    ('services.__init__', 'household_manager', 'function'),    # line 894: .household_manager
    ('services.__init__', 'active_household_id', 'function'),   # line 818: client.household_id, via get_first_client

    # sims/sim_info_types.pyc - exact bitflag values, not just presence (query.py's filters depend on
    # the actual ints, not merely on the names existing)
    ('sims.sim_info_types', 'Gender', 'class'),
    ('sims.sim_info_types', 'Gender.MALE', 'member', 4096),
    ('sims.sim_info_types', 'Gender.FEMALE', 'member', 8192),
    ('sims.sim_info_types', 'Age', 'class'),
    ('sims.sim_info_types', 'Age.BABY', 'member', 1),
    ('sims.sim_info_types', 'Age.TODDLER', 'member', 2),
    ('sims.sim_info_types', 'Age.CHILD', 'member', 4),
    ('sims.sim_info_types', 'Age.TEEN', 'member', 8),
    ('sims.sim_info_types', 'Age.YOUNGADULT', 'member', 16),
    ('sims.sim_info_types', 'Age.ADULT', 'member', 32),
    ('sims.sim_info_types', 'Age.ELDER', 'member', 64),
    ('sims.sim_info_types', 'Age.INFANT', 'member', 128),
    ('sims.sim_info_types', 'Species', 'class'),
    ('sims.sim_info_types', 'Species.INVALID', 'member', 0),
    ('sims.sim_info_types', 'Species.HUMAN', 'member', 1),
    ('sims.sim_info_types', 'Species.DOG', 'member', 2),
    ('sims.sim_info_types', 'Species.CAT', 'member', 3),
    ('sims.sim_info_types', 'Species.FOX', 'member', 5),
    ('sims.sim_info_types', 'Species.HORSE', 'member', 6),

    # sims/occult/occult_enums.pyc
    ('sims.occult.occult_enums', 'OccultType', 'class'),
    ('sims.occult.occult_enums', 'OccultType.HUMAN', 'member', 1),
    ('sims.occult.occult_enums', 'OccultType.ALIEN', 'member', 2),
    ('sims.occult.occult_enums', 'OccultType.VAMPIRE', 'member', 4),
    ('sims.occult.occult_enums', 'OccultType.MERMAID', 'member', 8),
    ('sims.occult.occult_enums', 'OccultType.WITCH', 'member', 16),   # player-facing name: Spellcaster
    ('sims.occult.occult_enums', 'OccultType.WEREWOLF', 'member', 32),
    ('sims.occult.occult_enums', 'OccultType.FAIRY', 'member', 64),

    # sims/occult/sim_info_with_occult_tracker.pyc - the mixin exposing sim_info.occult_types
    ('sims.occult.sim_info_with_occult_tracker', 'SimInfoWithOccultTracker.occult_types', 'method'),

    # sims/sim_info.pyc - properties browser.py/query.py read via getattr() on a real SimInfo
    ('sims.sim_info', 'SimInfo.is_npc', 'method'),           # line 786: active_household_id() != household_id
    ('sims.sim_info', 'SimInfo.household', 'method'),         # line 1057: household_manager().get(_household_id)
    ('sims.sim_info', 'SimInfo.household_id', 'method'),        # line 2723
    ('sims.sim_info', 'SimInfo.is_instanced', 'method'),          # line 2227
    ('sims.sim_info', 'SimInfo.is_pregnant', 'method'),              # line 1698, guards a None tracker

    # sims/sim_info_base_wrapper.pyc - SimInfo's own name properties (confirmed present on SimInfo
    # itself via this mixin, game_api.md Sec 3's own citation, re-verified this session)
    ('sims.sim_info_base_wrapper', 'SimInfoBaseWrapper.first_name', 'method'),   # line 753
    ('sims.sim_info_base_wrapper', 'SimInfoBaseWrapper.last_name', 'method'),     # line 765
    ('sims.sim_info_base_wrapper', 'SimInfoBaseWrapper.full_name', 'method'),      # line 838

    # sims/household.pyc - just the one field browser.py's household picker actually reads
    ('sims.household', 'Household.name', 'method'),   # line 289, a property

    # indexed_manager.pyc - the base every Manager services.*_manager() returns extends
    # (SimInfoManager/HouseholdManager -> DistributableObjectManager -> IndexedManager, this
    # session's own class-bases check on household_manager.pyc/objects/object_manager.pyc)
    ('indexed_manager', 'IndexedManager.values', 'method'),   # line 108: return self._objects.values()
    ('indexed_manager', 'IndexedManager.get', 'method'),        # line 291

    # ui/ui_dialog_picker.pyc - the Sim-row-only construction path menukit/render.py's own docstring
    # says BP4 must build directly (UiObjectPicker/ObjectPickerRow can't carry a Sim row)
    ('ui.ui_dialog_picker', 'UiSimPicker', 'class'),
    ('ui.ui_dialog_picker', 'UiSimPicker.__init__', 'method'),         # line 1747: picker_type=SIM,
                                                                        # forwards *args/**kwargs to
                                                                        # UiDialogObjectPicker.__init__
    ('ui.ui_dialog_picker', 'UiSimPicker._validate_row', 'method'),     # line 1752: isinstance(row, SimPickerRow)
    ('ui.ui_dialog_picker', 'ObjectPickerType.SIM', 'member', 3),        # line 66
    ('ui.ui_dialog_picker', 'SimPickerRow', 'class'),
    ('ui.ui_dialog_picker', 'SimPickerRow.__init__', 'method'),   # line 541: (sim_id, select_default,
                                                                   # sim_location, household_id, **kwargs)
                                                                   # - kwargs forwarded to BasePickerRow,
                                                                   # so name=/row_description=/
                                                                   # is_selected= all still apply
    ('ui.ui_dialog_picker', 'SimPickerRow.populate_protocol_buffer', 'method'),   # line 548: calls
                                                                   # super().populate_protocol_buffer
                                                                   # (base_data) FIRST - confirms name/
                                                                   # row_description still render on a
                                                                   # Sim row exactly like an Object row,
                                                                   # then separately stores sim_id/
                                                                   # select_default/sim_location/
                                                                   # household_id onto sim_row_data
                                                                   # itself, not base_data - closes the
                                                                   # one open question menukit's own
                                                                   # docstring left about Sim rows.
    ('ui.ui_dialog_picker', 'UiDialogObjectPicker.multi_select', 'method'),   # line 1385, a computed
                                                                   # property: min_selectable<1 or
                                                                   # max_selectable_num>1 or ==0 - NOT a
                                                                   # settable constructor kwarg, which is
                                                                   # why browser.py never passes
                                                                   # multi_select= itself, only
                                                                   # min/max_selectable=0 (already
                                                                   # verified plain-int-safe by
                                                                   # bp2_menukit.py's own manifest row).

    # sims4/localization/__init__.pyc - already cited by bp1_bp3_core_inject.py/bp2_menukit.py; kept
    # here too since browser.py calls it directly and the aggregator merges agreeing duplicate
    # citations rather than erroring (tools/novulon_api_manifest/__init__.py's own documented rule)
    ('sims4.localization.__init__', 'LocalizationHelperTuning.get_raw_text', 'method'),
]
