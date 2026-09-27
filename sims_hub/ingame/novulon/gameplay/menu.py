"""Gameplay - the named subgroups (SPEC.md `gameplay/` §9, build package BP9) plus the MCCC-defer guard
(§9.1) every subgroup below it respects.

**Calling convention used everywhere in this file (a deliberate policy, not per-row improvisation)**: every
command below is run through `sims4.commands.execute('<literal> <args...>', connection)` with **every
argument passed explicitly** - never by omitting a middle positional and hoping the console parser's own
default-skipping applies. Several of the handler functions disassembled this session take an optional
target (`opt_sim`) as their **first** parameter, before required arguments (`add_career_performance`,
`career_promote_sim`) - skipping a non-trailing optional in a plain space-separated command line is not a
pattern this pass verified, so this file always resolves and interpolates a real id (the active Sim's,
or one typed/looked-up by name) instead of ever trying to omit one. Trailing optionals the handler itself
never null-checks (e.g. `households.modify_funds`'s `reason`, `autonomy.global`'s `settings_group`) are
left off entirely, the same as a player who just doesn't type that word.

Every command literal, its handler's real signature, and where each was checked are listed in
`tools/novulon_api_manifest/bp8_bp9_bp10.py` - not repeated in full here, only cited briefly per row.

**MCCC-defer guard (§9.1)**: `_should_defer(feature)` prefers the real, live `compat.mccc.should_defer`
(BP7) when that package has been built and is importable; `compat/` does not exist yet in every checkout
of this shared working tree, so this falls back to reading the same `compat.defer_to_mccc.<feature>`
settings snapshot `settings.py` (BP1) already computes at first run from its own MCCC probe - exactly the
same "compat/ not built yet == treat as MCCC absent, the safer direction" pattern `settings.py`'s own
`_mccc_present()` already documents and uses. Once BP7 lands, this file starts using the live probe with
no code change needed here.

**Free-text fields** (skill/trait/career/buff/relationship-bit names, and the partner/target Sim's name)
are collected with `menukit.search.open_search_box` - the same generic, already-guarded text-entry
primitive `menukit` ships for its own pinned "Search…" row, reused here for plain data entry (its own
docstring/`search.py`'s module doc note it degrades safely, never crashes, if the dialog shape doesn't
match this build - SPEC.md §18's own prescribed handling for that exact open item). This mod does not
carry its own copy of the game's skill/trait/career catalog, so these are typed, matching how a player
would type the equivalent console cheat by hand - not a picker over hidden data this pass never verified.
"""
from .. import common
from ..menukit import Row, Page, search as _search, notify as _notify

BREADCRUMB_ROOT = ('Gameplay',)


# ------------------------------------------------------------------ MCCC-defer guard (§9.1)
def mccc_present():
    try:
        from ..compat import mccc
    except Exception:
        return False
    try:
        return bool(mccc.is_present())
    except Exception:
        return False


def _should_defer(feature):
    try:
        from ..compat import mccc
        return bool(mccc.should_defer(feature))
    except Exception:
        pass
    try:
        from .. import settings
        return bool(settings.get('compat.defer_to_mccc.' + feature, False))
    except Exception:
        return False


def _banner_subtitle():
    return 'MC Command Center detected — Gameplay tools deferred to it.' if mccc_present() else None


# ------------------------------------------------------------------ small shared helpers
def _active_sim_id(connection):
    try:
        import services
        info = services.active_sim_info()
        return info.id if info is not None else None
    except Exception:
        return None


def _active_household_id(connection):
    try:
        import services
        return services.active_household_id()
    except Exception:
        return None


def _require_active_sim(connection):
    sim_id = _active_sim_id(connection)
    if sim_id is None:
        _notify('Nothing changed.', 'No active Sim.', urgent=True)
    return sim_id


def _exec(connection, command_line, ok_text):
    try:
        import sims4.commands
    except Exception:
        _notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return False
    common.guarded('novulon.gameplay: ' + command_line.split(' ', 1)[0],
                    sims4.commands.execute, command_line, connection)
    _notify('Done.', ok_text)
    return True


def _ask_text(connection, title, prompt, on_result):
    _search.open_search_box(connection, None, on_result, title=title, text=prompt)


def _prompt_chain(connection, fields, build_command, ok_text):
    """Collects one text value per (title, prompt) pair in `fields`, in order (each via `_ask_text`,
    chained through `open_search_box`'s own callback - there is no native multi-field dialog, per
    `menukit/search.py`'s own docstring); an empty/cancelled answer at any step stops the whole chain
    silently (matches `search.apply`'s own "empty query changes nothing" convention). Once every field is
    collected, `build_command(values)` turns them into a full command-line string (or None to abort after
    reporting its own problem) and `_exec` runs it."""
    values = []

    def _next(i):
        if i >= len(fields):
            cmd = build_command(values)
            if cmd:
                _exec(connection, cmd, ok_text)
            return
        title, prompt = fields[i]

        def _got(text):
            if not text:
                return
            values.append(str(text).strip())
            _next(i + 1)
        _ask_text(connection, title, prompt, _got)
    _next(0)


def _resolve_sim_by_name(full_text):
    """`services.sim_info_manager().get_sim_info_by_name(first, last)` - verified pure-Python lookup
    (`sims/sim_info_manager.pyc:707`), case-insensitive exact first/last match, `None` if not found. This
    mod has no Sim search/browse of its own (that is the Sim Browser, BP4) - typing a full name is the
    verified, simplest way this package can resolve a *second* Sim for a Relationships/Pregnancy action."""
    try:
        import services
    except Exception:
        return None
    parts = str(full_text).strip().rsplit(' ', 1)
    first, last = (parts[0], parts[1]) if len(parts) == 2 else (parts[0], '')
    try:
        return services.sim_info_manager().get_sim_info_by_name(first, last)
    except Exception:
        return None


# ==================================================================== Needs & Moods (§9.2)
def _needs_fill_active(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None
    _exec(connection, 'sims.fill_all_commodities %s' % sim_id, 'Needs filled.')
    return None


def _needs_fill_household(connection, selected_ids=None):
    _exec(connection, 'stats.fill_commodities_household', 'Household needs filled.')
    return None


def _needs_set_individual(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _build(values):
        stat, value = values
        return 'stats.set_commodity %s %s %s' % (stat, value, sim_id)
    _prompt_chain(connection,
                  [('Need', 'Type the need name (e.g. Hunger, Hygiene, Bladder, Fun, Social, Energy).'),
                   ('Value', 'Type a value, 0-100 (100 is best).')],
                  _build, 'Need updated.')
    return None


def _needs_add_moodlet(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _got(name):
        if not name:
            return
        _exec(connection, 'sims.add_buff %s %s' % (name.strip(), sim_id), 'Moodlet added.')
    _ask_text(connection, 'Add Moodlet', 'Type the moodlet/buff name.', _got)
    return None


def _needs_remove_moodlet(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _got(name):
        if not name:
            return
        _exec(connection, 'sims.remove_buff %s %s' % (name.strip(), sim_id), 'Moodlet removed.')
    _ask_text(connection, 'Remove Moodlet', 'Type the moodlet/buff name.', _got)
    return None


def _needs_page(connection, selected_ids=None):
    return Page('Needs & Moods', [
        Row('novulon.gameplay.needs.fill_active', 'Fill All Needs',
            description='The active Sim.', on_activate=_needs_fill_active),
        Row('novulon.gameplay.needs.fill_household', 'Fill All Needs (Household)',
            description='Every Sim in the active household.', on_activate=_needs_fill_household),
        Row('novulon.gameplay.needs.set_individual', 'Set Individual Need…',
            on_activate=_needs_set_individual),
        Row('novulon.gameplay.needs.add_moodlet', 'Add Moodlet…', on_activate=_needs_add_moodlet),
        Row('novulon.gameplay.needs.remove_moodlet', 'Remove Moodlet…', on_activate=_needs_remove_moodlet),
    ], breadcrumb=BREADCRUMB_ROOT + ('Needs & Moods',))


# ==================================================================== Skills & Careers (§9.3)
# Cut, per the build override ("verify or cut"): **Add Gig** (`careers.add_gig`). Verified present
# (`career_commands.pyc:830`), but its real signature is `add_gig(gig, opt_sim, sim_filter, _connection)`
# - `sim_filter` is a tuning `SimFilter` object, not a plain typed string like every other free-text field
# in this file, and no research pass (this one included) verified what a mod can safely pass there
# (`None`, a specific tuning instance, something else). Left out rather than guessed at; **Reset Branch**
# was also considered and cut - no `careers.reset_branch` (or any "reset branch" literal) exists anywhere
# in `career_commands.pyc`'s own string table, so unlike Promote/Demote there was nothing to verify.
def _skills_set_level(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _build(values):
        skill, level = values
        return 'stats.set_skill_level %s %s %s' % (skill, level, sim_id)
    _prompt_chain(connection,
                  [('Skill', 'Type the skill name (e.g. Major_Charisma, Major_Cooking).'),
                   ('Level', 'Type the level, 1-10 (some skills go higher).')],
                  _build, 'Skill updated.')
    return None


def _skills_max_all(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None
    _exec(connection, 'stats.set_all_skills_max %s' % sim_id, 'Skills maxed.')
    return None


def _skills_clear_all(connection, selected_ids=None):
    """`stats.clear_skill <sim>` - **verified finding**: this clears *every* skill for the Sim (it iterates
    every tracked statistic where `is_skill` is true and removes each one), not one named skill despite
    the name - see this package's manifest citation. Labeled 'Clear All Skills' to match what it actually
    does, not the spec's original 'Clear Skill' wording."""
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None
    _exec(connection, 'stats.clear_skill %s' % sim_id, 'Skills cleared.')
    return None


def _careers_add(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _got(name):
        if not name:
            return
        _exec(connection, 'careers.add_career %s %s' % (name.strip(), sim_id), 'Career added.')
    _ask_text(connection, 'Add Career', 'Type the career name.', _got)
    return None


def _careers_add_performance(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _build(values):
        career, amount = values
        return 'careers.add_performance %s %s %s' % (sim_id, amount, career)
    _prompt_chain(connection,
                  [('Career', 'Type the career name.'), ('Amount', 'Type a performance amount, e.g. 500.')],
                  _build, 'Performance added.')
    return None


def _careers_add_pto(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _got(amount):
        if not amount:
            return
        _exec(connection, 'careers.add_pto %s %s' % (amount.strip(), sim_id), 'PTO added.')
    _ask_text(connection, 'Add PTO', 'Type a number of PTO hours/days to add.', _got)
    return None


def _careers_promote(connection, selected_ids=None):
    """`careers.promote <career> <sim> <check_can_change_level>` - verified command (this build's own
    `career_promote_sim`, `career_commands.pyc:335`; SPEC.md §5.5/§9.3 flagged Promote/Demote as
    unverified before this pass). `check_can_change_level` is always sent as `False` here, so it always
    promotes rather than first checking the vanilla eligibility gate (`career.can_change_level()`) - a
    deliberate cheat-mod choice, not a default this pass discovered; documented rather than left silent."""
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _got(name):
        if not name:
            return
        _exec(connection, 'careers.promote %s %s False' % (name.strip(), sim_id), 'Promoted.')
    _ask_text(connection, 'Promote', 'Type the career name.', _got)
    return None


def _careers_demote(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _got(name):
        if not name:
            return
        _exec(connection, 'careers.demote %s %s' % (name.strip(), sim_id), 'Demoted.')
    _ask_text(connection, 'Demote', 'Type the career name.', _got)
    return None


def _skills_page(connection, selected_ids=None):
    return Page('Skills & Careers', [
        Row('novulon.gameplay.skills.set_level', 'Set Skill Level…', on_activate=_skills_set_level),
        Row('novulon.gameplay.skills.max_all', 'Max All Skills', on_activate=_skills_max_all),
        Row('novulon.gameplay.skills.clear_all', 'Clear All Skills', on_activate=_skills_clear_all),
        Row('novulon.gameplay.skills.add_career', 'Add Career…', on_activate=_careers_add),
        Row('novulon.gameplay.skills.add_performance', 'Add Career Performance…',
            on_activate=_careers_add_performance),
        Row('novulon.gameplay.skills.add_pto', 'Add PTO…', on_activate=_careers_add_pto),
        Row('novulon.gameplay.skills.promote', 'Promote…', on_activate=_careers_promote),
        Row('novulon.gameplay.skills.demote', 'Demote…', on_activate=_careers_demote),
    ], breadcrumb=BREADCRUMB_ROOT + ('Skills & Careers',))


# ==================================================================== Traits & Aspirations (§9.5)
def _traits_add(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _got(name):
        if not name:
            return
        _exec(connection, 'traits.equip_trait %s %s' % (name.strip(), sim_id), 'Trait added.')
    _ask_text(connection, 'Add Trait', 'Type the trait name.', _got)
    return None


def _traits_remove(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _got(name):
        if not name:
            return
        _exec(connection, 'traits.remove_trait %s %s' % (name.strip(), sim_id), 'Trait removed.')
    _ask_text(connection, 'Remove Trait', 'Type the trait name.', _got)
    return None


def _traits_clear_all(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None
    _exec(connection, 'traits.clear_traits %s' % sim_id, 'Traits cleared.')
    return None


def _traits_clear_personality(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None
    _exec(connection, 'traits.clear_personality_traits %s' % sim_id, 'Personality traits cleared.')
    return None


def _aspiration_complete_milestone(connection, selected_ids=None):
    """`aspirations.complete_current_milestone <sim>` - verified command
    (`aspiration_commands.pyc:69`; SPEC.md §5.5/§9.5 flagged this as unverified before this pass)."""
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None
    _exec(connection, 'aspirations.complete_current_milestone %s' % sim_id, 'Milestone completed.')
    return None


def _aspiration_reset(connection, selected_ids=None):
    """`aspirations.reset_data <sim>` -> `reset_aspirations` (`aspiration_commands.pyc:27`) - verified."""
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None
    _exec(connection, 'aspirations.reset_data %s' % sim_id, 'Aspiration reset.')
    return None


def _traits_page(connection, selected_ids=None):
    return Page('Traits & Aspirations', [
        Row('novulon.gameplay.traits.add', 'Add Trait…', on_activate=_traits_add),
        Row('novulon.gameplay.traits.remove', 'Remove Trait…', on_activate=_traits_remove),
        Row('novulon.gameplay.traits.clear_all', 'Clear All Traits', on_activate=_traits_clear_all),
        Row('novulon.gameplay.traits.clear_personality', 'Clear Personality Traits',
            on_activate=_traits_clear_personality),
        Row('novulon.gameplay.traits.complete_milestone', 'Complete Aspiration Milestone',
            on_activate=_aspiration_complete_milestone),
        Row('novulon.gameplay.traits.reset_aspiration', 'Reset Aspiration', on_activate=_aspiration_reset),
    ], breadcrumb=BREADCRUMB_ROOT + ('Traits & Aspirations',))


# ==================================================================== Relationships (§9.4, delegated)
def _relationships_page(connection, selected_ids=None):
    from ..relationships import menu as _rel_menu
    return _rel_menu.relationships_page(connection, selected_ids)


# ==================================================================== Life & Aging (§9.6)
def _life_age_up(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None
    _exec(connection, 'sims.age_up %s' % sim_id, 'Aged up.')
    return None


def _life_age_down(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None
    _exec(connection, 'sims.age_down %s' % sim_id, 'Aged down.')
    return None


def _life_add_progress(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _got(amount):
        if not amount:
            return
        _exec(connection, 'sims.age_add_progress_percentage %s %s' % (amount.strip(), sim_id),
              'Age progress updated.')
    _ask_text(connection, 'Add Age Progress %', 'Type a percentage to add, e.g. 10.', _got)
    return None


def _life_set_progress(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _got(amount):
        if not amount:
            return
        _exec(connection, 'sims.set_age_progress_percentage %s %s' % (amount.strip(), sim_id),
              'Age progress updated.')
    _ask_text(connection, 'Set Age Progress %', 'Type a percentage, 0-100.', _got)
    return None


def _life_page(connection, selected_ids=None):
    return Page('Life & Aging', [
        Row('novulon.gameplay.life.age_up', 'Age Up', on_activate=_life_age_up),
        Row('novulon.gameplay.life.age_down', 'Age Down', on_activate=_life_age_down),
        Row('novulon.gameplay.life.add_progress', 'Add Age Progress %…', on_activate=_life_add_progress),
        Row('novulon.gameplay.life.set_progress', 'Set Age Progress %…', on_activate=_life_set_progress),
    ], breadcrumb=BREADCRUMB_ROOT + ('Life & Aging',))


# ==================================================================== Occults (§9.7)
# OccultType (sims/occult/occult_enums.pyc:10, verified this session): HUMAN=1, ALIEN=2, VAMPIRE=4,
# MERMAID=8, WITCH=16 (players see "Spellcaster"), WEREWOLF=32, FAIRY=64. `occult.add_occult`/
# `occult.remove_occult`/`occult.switch_to_occult` (sims/occult/occult_commands.pyc, verified this
# session) take the occult type by its enum MEMBER NAME. Human is left out of both lists below - "turn
# into human" and "remove human" are not meaningful actions for this row.
_OCCULT_CHOICES = (
    ('Vampire', 'VAMPIRE'),
    ('Spellcaster', 'WITCH'),
    ('Mermaid', 'MERMAID'),
    ('Alien', 'ALIEN'),
    ('Werewolf', 'WEREWOLF'),
    ('Fairy', 'FAIRY'),
)


def _occult_add_row(occult_name):
    def _fn(connection, selected_ids=None):
        sim_id = _require_active_sim(connection)
        if sim_id is None:
            return None
        _exec(connection, 'occult.add_occult %s %s' % (occult_name, sim_id), 'Occult type added.')
        return None
    return _fn


def _occult_remove_row(occult_name):
    def _fn(connection, selected_ids=None):
        sim_id = _require_active_sim(connection)
        if sim_id is None:
            return None
        _exec(connection, 'occult.remove_occult %s %s' % (occult_name, sim_id), 'Occult type removed.')
        return None
    return _fn


def _occults_turn_into_page(connection, selected_ids=None):
    return Page('Turn Into…', [
        Row('novulon.gameplay.occults.turn_into.%s' % token, label,
            on_activate=_occult_add_row(token))
        for label, token in _OCCULT_CHOICES
    ], breadcrumb=BREADCRUMB_ROOT + ('Occults', 'Turn Into…'))


def _occults_remove_page(connection, selected_ids=None):
    return Page('Remove Occult Type…', [
        Row('novulon.gameplay.occults.remove.%s' % token, label,
            on_activate=_occult_remove_row(token))
        for label, token in _OCCULT_CHOICES
    ], breadcrumb=BREADCRUMB_ROOT + ('Occults', 'Remove Occult Type…'))


def _occults_page(connection, selected_ids=None):
    return Page('Occults', [
        Row('novulon.gameplay.occults.turn_into', 'Turn Into…', on_activate=_occults_turn_into_page),
        Row('novulon.gameplay.occults.remove', 'Remove Occult Type…', on_activate=_occults_remove_page),
    ], breadcrumb=BREADCRUMB_ROOT + ('Occults',))


# ==================================================================== Pregnancy & Family (§9.8)
def _pregnancy_start(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None

    def _got(name):
        if not name:
            return
        partner = _resolve_sim_by_name(name)
        if partner is None:
            _notify('Nothing changed.', 'No Sim found with that name.', urgent=True)
            return
        _exec(connection, 'pregnancy.start %s %s' % (sim_id, partner.id), 'Pregnancy started.')
    _ask_text(connection, 'Start Pregnancy', "Type the partner's full name (First Last).", _got)
    return None


def _pregnancy_clear(connection, selected_ids=None):
    sim_id = _require_active_sim(connection)
    if sim_id is None:
        return None
    _exec(connection, 'pregnancy.clear %s' % sim_id, 'Pregnancy cleared.')
    return None


def _pregnancy_page(connection, selected_ids=None):
    return Page('Pregnancy & Family', [
        Row('novulon.gameplay.pregnancy.start', 'Start Pregnancy…', on_activate=_pregnancy_start),
        Row('novulon.gameplay.pregnancy.clear', 'Clear Pregnancy', on_activate=_pregnancy_clear),
    ], breadcrumb=BREADCRUMB_ROOT + ('Pregnancy & Family',))


# ==================================================================== World, Time & Weather (§9.9)
def _world_set_speed(connection, selected_ids=None):
    def _got(speed):
        if not speed:
            return
        _exec(connection, 'clock.setspeed %s' % speed.strip(), 'Clock speed updated.')
    _ask_text(connection, 'Clock Speed', 'Type a speed, 0-3.', _got)
    return None


def _world_set_anim_speed(connection, selected_ids=None):
    def _got(scale):
        if not scale:
            return
        _exec(connection, 'clock.setanimspeed %s' % scale.strip(), 'Animation speed updated.')
    _ask_text(connection, 'Animation Speed', 'Type a scale, e.g. 1.0.', _got)
    return None


def _world_set_game_time(connection, selected_ids=None):
    def _build(values):
        h, m, s = values
        return 'clock.setgametime %s %s %s' % (h, m, s)
    _prompt_chain(connection,
                  [('Hour', 'Type the hour, 0-23.'), ('Minute', 'Type the minute, 0-59.'),
                   ('Second', 'Type the second, 0-59.')],
                  _build, 'Game time updated.')
    return None


def _world_page(connection, selected_ids=None):
    return Page('World, Time & Weather', [
        Row('novulon.gameplay.world.set_speed', 'Set Clock Speed…', on_activate=_world_set_speed),
        Row('novulon.gameplay.world.set_anim_speed', 'Set Animation Speed…',
            on_activate=_world_set_anim_speed),
        Row('novulon.gameplay.world.set_game_time', 'Set Game Time…', on_activate=_world_set_game_time),
    ], breadcrumb=BREADCRUMB_ROOT + ('World, Time & Weather',))


# ==================================================================== Story Progression & Population (§9.10)
def _story_noop(connection, selected_ids=None):
    return None


def _story_page(connection, selected_ids=None):
    """V1 guard only (SPEC.md §9.10): the MCCC-defer banner is the whole feature here. Everything else
    (curated presets, population dashboard) is V2, and only meaningful once MCCC is absent - nothing to
    build yet either way, so this page is one informational row, not an empty page."""
    deferred = _should_defer('story_progression')
    if mccc_present() and deferred:
        text = 'MC Command Center handles story progression on this save.'
    else:
        text = 'Population and story-progression tools are coming in a future update.'
    return Page('Story Progression & Population', [
        Row('novulon.gameplay.story.info', text, disabled_text=text, on_activate=_story_noop),
    ], breadcrumb=BREADCRUMB_ROOT + ('Story Progression & Population',))


# ==================================================================== Performance (§9.11)
def _performance_autonomy(state):
    def _fn(connection, selected_ids=None):
        _exec(connection, 'autonomy.global %s' % state, 'Autonomy updated.')
        return None
    return _fn


def _performance_page(connection, selected_ids=None):
    return Page('Performance', [
        Row('novulon.gameplay.performance.autonomy_on', 'Autonomy On',
            on_activate=_performance_autonomy('on')),
        Row('novulon.gameplay.performance.autonomy_off', 'Autonomy Off',
            on_activate=_performance_autonomy('off')),
        Row('novulon.gameplay.performance.autonomy_default', 'Restore Autonomy Defaults',
            on_activate=_performance_autonomy('default')),
    ], breadcrumb=BREADCRUMB_ROOT + ('Performance',))


# ==================================================================== root page
_SUBGROUPS = (
    ('novulon.gameplay.needs', 'Needs & Moods', 'Fill needs, add or remove moodlets.', _needs_page),
    ('novulon.gameplay.skills', 'Skills & Careers', 'Skills, careers, promotions.', _skills_page),
    ('novulon.gameplay.traits', 'Traits & Aspirations', 'Traits and aspiration progress.', _traits_page),
    ('novulon.gameplay.relationships', 'Relationships', 'Scores and relationship bits.',
     _relationships_page),
    ('novulon.gameplay.life', 'Life & Aging', 'Age up, down, or set progress.', _life_page),
    ('novulon.gameplay.occults', 'Occults', 'Turn into or remove an occult type.', _occults_page),
    ('novulon.gameplay.pregnancy', 'Pregnancy & Family', 'Start or clear a pregnancy.', _pregnancy_page),
    ('novulon.gameplay.world', 'World, Time & Weather', 'Clock speed and game time.', _world_page),
    ('novulon.gameplay.story', 'Story Progression & Population', 'Population and story progression.',
     _story_page),
    ('novulon.gameplay.performance', 'Performance', 'Autonomy on or off.', _performance_page),
)


def gameplay_root(connection, selected_ids=None):
    return Page('Gameplay', [
        Row(action_id, label, description=description, on_activate=handler)
        for action_id, label, description, handler in _SUBGROUPS
    ], breadcrumb=BREADCRUMB_ROOT, subtitle=_banner_subtitle())


def all_actions():
    """Every (action_id, handler) this file registers - used by `__init__.py` and by tests that want the
    full list without hand-maintaining it twice."""
    actions = list((action_id, handler) for action_id, _label, _desc, handler in _SUBGROUPS)
    actions += [
        ('novulon.gameplay.needs.fill_active', _needs_fill_active),
        ('novulon.gameplay.needs.fill_household', _needs_fill_household),
        ('novulon.gameplay.needs.set_individual', _needs_set_individual),
        ('novulon.gameplay.needs.add_moodlet', _needs_add_moodlet),
        ('novulon.gameplay.needs.remove_moodlet', _needs_remove_moodlet),
        ('novulon.gameplay.skills.set_level', _skills_set_level),
        ('novulon.gameplay.skills.max_all', _skills_max_all),
        ('novulon.gameplay.skills.clear_all', _skills_clear_all),
        ('novulon.gameplay.skills.add_career', _careers_add),
        ('novulon.gameplay.skills.add_performance', _careers_add_performance),
        ('novulon.gameplay.skills.add_pto', _careers_add_pto),
        ('novulon.gameplay.skills.promote', _careers_promote),
        ('novulon.gameplay.skills.demote', _careers_demote),
        ('novulon.gameplay.traits.add', _traits_add),
        ('novulon.gameplay.traits.remove', _traits_remove),
        ('novulon.gameplay.traits.clear_all', _traits_clear_all),
        ('novulon.gameplay.traits.clear_personality', _traits_clear_personality),
        ('novulon.gameplay.traits.complete_milestone', _aspiration_complete_milestone),
        ('novulon.gameplay.traits.reset_aspiration', _aspiration_reset),
        ('novulon.gameplay.life.age_up', _life_age_up),
        ('novulon.gameplay.life.age_down', _life_age_down),
        ('novulon.gameplay.life.add_progress', _life_add_progress),
        ('novulon.gameplay.life.set_progress', _life_set_progress),
        ('novulon.gameplay.occults.turn_into', _occults_turn_into_page),
        ('novulon.gameplay.occults.remove', _occults_remove_page),
        ('novulon.gameplay.pregnancy.start', _pregnancy_start),
        ('novulon.gameplay.pregnancy.clear', _pregnancy_clear),
        ('novulon.gameplay.world.set_speed', _world_set_speed),
        ('novulon.gameplay.world.set_anim_speed', _world_set_anim_speed),
        ('novulon.gameplay.world.set_game_time', _world_set_game_time),
        ('novulon.gameplay.story.info', _story_noop),
        ('novulon.gameplay.performance.autonomy_on', _performance_autonomy('on')),
        ('novulon.gameplay.performance.autonomy_off', _performance_autonomy('off')),
        ('novulon.gameplay.performance.autonomy_default', _performance_autonomy('default')),
    ]
    for label, token in _OCCULT_CHOICES:
        actions.append(('novulon.gameplay.occults.turn_into.%s' % token, _occult_add_row(token)))
        actions.append(('novulon.gameplay.occults.remove.%s' % token, _occult_remove_row(token)))
    return actions
