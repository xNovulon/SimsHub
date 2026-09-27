"""Pure filter/sort/count/label logic for the Sim Browser (SPEC.md `sims/` Sec 5.1-5.4, BP4).

No game import anywhere in this file, on purpose - every function here takes plain SimInfo-shaped
objects (a real game SimInfo, or tests/novulon_fakes.FakeSimInfo) and plain ints/bitflags the
*caller* supplies (the real Gender/Age/Species/OccultType values, or a test's own made-up numbers).
This mirrors settings.py/menukit/paging.py's own "no game import in the pure logic" split, and is
what SPEC.md Sec 16 Tier 1 explicitly names: "sims.query.matches/filtered/sorted_for_display as
plain-Python unit tests." `browser.py` is the one file in this package that actually imports
sims.sim_info_types/sims.occult.occult_enums and hands their values in here - see its own docstring.

Filter dict shape (every key optional; a missing/falsy key means "no constraint from this filter"):
    {
        'gender':        int bitflag or None,      # sim_info.gender must have this bit set
        'species_ne':    int or None,               # sim_info.species must NOT equal this (Pets tab)
        'life_stages':   set of int bitflags,        # sim_info.age must have at least one bit set
        'occults':       set of int bitflags,         # sim_info.occult_types must have at least one set
        'household_id':  int or None,                  # sim_info.household_id must equal this
        'played':        bool,                          # SPEC.md Sec 5.2's three independent
        'npc':           bool,                           # household-status checkboxes; 'played' and
        'here':          bool,                            # 'npc' combine as XOR (exactly one checked
    }                                                       # is a real constraint; both/neither isn't -
                                                             # see is_npc()/matches() below.
"""


def _any_bit(value, bits):
    """True if `bits` is empty/None (no constraint), or `value` has at least one of its bits set."""
    if not bits:
        return True
    combined = 0
    for b in bits:
        combined |= b
    return bool(value & combined)


def _safe_call(obj, name, default):
    """bool(obj.name()) if that method exists and doesn't raise, else `default` - a FakeSimInfo (or a
    real SimInfo missing some tracker) never blows up a filter pass over the whole save."""
    fn = getattr(obj, name, None)
    if fn is None:
        return default
    try:
        return bool(fn())
    except Exception:
        return default


def is_npc(sim_info, active_household_id):
    """Mirrors the verified `SimInfo.is_npc` property (sims/sim_info.pyc:786, this session's own
    pyc37.py check): `services.active_household_id() != sim_info.household_id`, computed live, never
    a stored flag (SPEC.md Sec 5.2). `active_household_id=None` (no active household known - a test
    with no household set up, or a save between loads) is treated as "every Sim counts as played" -
    the safer default for a filter that would otherwise mark the whole save NPC."""
    if active_household_id is None:
        return False
    return getattr(sim_info, 'household_id', None) != active_household_id


def matches(sim_info, filters, active_household_id=None):
    """True if `sim_info` passes every constraint set in `filters` (module docstring has the shape).
    Filters combine as AND, except 'played'/'npc' which combine as XOR (checking both, or neither,
    applies no household-status constraint - SPEC.md Sec 5.2: "filters combine")."""
    filters = filters or {}
    gender = filters.get('gender')
    if gender and not (getattr(sim_info, 'gender', 0) & gender):
        return False
    species_ne = filters.get('species_ne')
    if species_ne is not None and getattr(sim_info, 'species', None) == species_ne:
        return False
    if not _any_bit(getattr(sim_info, 'age', 0), filters.get('life_stages')):
        return False
    if not _any_bit(getattr(sim_info, 'occult_types', 0), filters.get('occults')):
        return False
    household_id = filters.get('household_id')
    if household_id is not None and getattr(sim_info, 'household_id', None) != household_id:
        return False
    if filters.get('here') and not _safe_call(sim_info, 'is_instanced', False):
        return False
    played = bool(filters.get('played'))
    npc = bool(filters.get('npc'))
    if played != npc:
        sim_is_npc = is_npc(sim_info, active_household_id)
        if played and sim_is_npc:
            return False
        if npc and not sim_is_npc:
            return False
    return True


def filtered(sim_infos, filters, active_household_id=None):
    """Every sim_info in `sim_infos` that matches() `filters` - a plain list, no game import. Callers
    filter FIRST, then page the result (menukit/paging.py's own hard requirement, SPEC.md Sec 5.3) -
    this function never builds more than one pass over `sim_infos`."""
    return [s for s in sim_infos if matches(s, filters, active_household_id)]


def _sort_key(sim_info):
    last = (getattr(sim_info, 'last_name', '') or '').lower()
    first = (getattr(sim_info, 'first_name', '') or '').lower()
    return (last, first, getattr(sim_info, 'id', 0))


def sorted_for_display(sim_infos):
    """Stable last-name/first-name/id order - deterministic paging, so "Page 2 of 3" refers to the
    same 60 Sims across two renders of the same filter (SPEC.md Sec 5.3)."""
    return sorted(sim_infos, key=_sort_key)


def counts(sim_infos, gender_male, gender_female, human_species):
    """{'males', 'females', 'pets', 'all'} - the live per-tab counts SPEC.md Sec 5.1 puts in each
    category row's subtitle ('{n} Sims'). One pass over `sim_infos`."""
    males = females = pets = total = 0
    for s in sim_infos:
        total += 1
        gender = getattr(s, 'gender', 0)
        if gender & gender_male:
            males += 1
        if gender & gender_female:
            females += 1
        if getattr(s, 'species', human_species) != human_species:
            pets += 1
    return {'males': males, 'females': females, 'pets': pets, 'all': total}


def first_bit_label(value, pairs):
    """First `label` from an ordered `[(bit, label), ...]` list whose bit is set on `value` (a
    bitflag match - Age/OccultType are both bitflag enums, SPEC.md Sec 5.2). None if nothing matches
    or `pairs` is empty."""
    for bit, label in pairs or ():
        if value & bit:
            return label
    return None


def first_equal_label(value, pairs):
    """First `label` from an ordered `[(item, label), ...]` list where `item == value` (plain equality
    - Species values are small distinct ints, not independent bits, so a bitwise test would wrongly
    match HUMAN=1 against DOG=2's own bit pattern). None if nothing matches."""
    for item, label in pairs or ():
        if value == item:
            return label
    return None


def badges_for(sim_info, age_pairs, occult_pairs, active_household_id=None, cap=3):
    """Up to `cap` short badge strings for one Sim row's text (SPEC.md Sec 5.3: 'Vampire · Elder ·
    Pregnant' - shipped as plain text since SimPickerRow's own icon-badge support is unverified, Sec
    18 open item). Order: occult (only a non-empty match, i.e. never plain 'Human'), life stage,
    Pregnant, Here (instanced), then Played/NPC - stops at `cap`."""
    out = []
    occult = first_bit_label(getattr(sim_info, 'occult_types', 0), occult_pairs)
    if occult:
        out.append(occult)
    if len(out) < cap:
        stage = first_bit_label(getattr(sim_info, 'age', 0), age_pairs)
        if stage:
            out.append(stage)
    if len(out) < cap and _safe_call(sim_info, 'is_pregnant', False):
        out.append('Pregnant')
    if len(out) < cap and _safe_call(sim_info, 'is_instanced', False):
        out.append('Here')
    if len(out) < cap:
        out.append('NPC' if is_npc(sim_info, active_household_id) else 'Played')
    return out[:cap]


def subtitle_for(sim_info, age_pairs, species_pairs, household_name=None):
    """'Young Adult · Human · Willow Creek' (SPEC.md Sec 5.3's grey subtitle line)."""
    parts = []
    stage = first_bit_label(getattr(sim_info, 'age', 0), age_pairs)
    if stage:
        parts.append(stage)
    species_label = first_equal_label(getattr(sim_info, 'species', None), species_pairs)
    if species_label:
        parts.append(species_label)
    if household_name:
        parts.append(household_name)
    return ' • '.join(parts)


def active_filter_labels(filters, life_stage_pairs, occult_pairs, gender_labels=None):
    """Plain-English labels for whatever's actually set in `filters` - e.g.
    `['Female', 'Young Adult', 'Adult']` - for the browse list's 'Filters: ...' summary row (SPEC.md
    Sec 5.3). `gender_labels` is `{bit: 'Female', ...}`; life_stage_pairs/occult_pairs are the same
    ordered `[(bit, label), ...]` shape used elsewhere in this file, walked in full (every set bit
    gets its own label here, not just the first) since a summary should name every active filter."""
    filters = filters or {}
    labels = []
    gender = filters.get('gender')
    if gender and gender_labels:
        name = gender_labels.get(gender)
        if name:
            labels.append(name)
    if filters.get('species_ne') is not None:
        labels.append('Pets')
    for bit, label in life_stage_pairs or ():
        if bit in (filters.get('life_stages') or ()):
            labels.append(label)
    for bit, label in occult_pairs or ():
        if bit in (filters.get('occults') or ()):
            labels.append(label)
    if filters.get('played'):
        labels.append('Played')
    if filters.get('npc'):
        labels.append('NPC')
    if filters.get('here'):
        labels.append('Here')
    return labels


def has_any_filter(filters):
    """True if `filters` constrains anything at all - SPEC.md Sec 5.2's 'Show Results' row only
    appears once at least one box is checked."""
    filters = filters or {}
    return bool(filters.get('gender') or filters.get('species_ne') is not None
                or filters.get('life_stages') or filters.get('occults')
                or filters.get('household_id') is not None
                or filters.get('played') or filters.get('npc') or filters.get('here'))
