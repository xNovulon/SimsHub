"""adult/gate.py - the two independent, hard-coded gates the whole Adult section stands behind
(SPEC.md Sec.0 hard rule 1 / Sec.11). Neither is a player-facing toggle:

  * `is_adult_content_allowed(sim_info)` - the per-Sim predicate every Adult picker/interaction must
    run at the QUERY stage (a filtered-out Sim is never sent to the client dialog, never just hidden
    by a UI check). Young adult and older, human-species Sims only. Novulon's OWN, independent check
    - never borrowed from WickedWhims at runtime, per SPEC.md Sec.0's own wording ("WW might not be
    installed, might be an old version, or a player could disable its own gate").
  * `is_adult_section_available()` - whether the "Adult" Main Menu tile is built AT ALL: WickedWhims
    detected present AND the player switched Adult on in Settings (`adult.enabled`). SPEC.md Sec.11:
    "If either is false, no 'Adult' tile is built on the Main Menu at all - not greyed out, not
    present." This is `adult/menu.py`'s `is_visible` callback for `commands.add_section` - re-checked
    every time the Main Menu is built (commands.py's own contract), never cached, so turning
    WickedWhims off or flipping the setting off hides the tile on the very next menu open.

ADULT_AGES/HUMAN_SPECIES are plain ints, not `from sims.sim_info_types import Age, Species` at import
time - same convention `inject.py` already uses for `NOVULON_INTERACTION_ID`, so this predicate stays
pure Python: importable and unit-testable with no game and no Mods folder (SPEC.md Sec.16 Tier 4).
Verified THIS session directly against this installed game build's own `sims/sim_info_types.pyc`
(`tools/pyc37.py`, class-body disassembly, not just re-citing `research/game_api.md`) - see
`tools/novulon_api_manifest/bp11_adult.py` for the exact values and how each was read:
    Age:     BABY=1 TODDLER=2 CHILD=4 TEEN=8 YOUNGADULT=16 ADULT=32 ELDER=64 INFANT=128 (bit flags)
    Species: INVALID=0 HUMAN=1 DOG=2 CAT=3 FOX=5 HORSE=6
A vampire/spellcaster/alien/mermaid/werewolf/fairy Sim's `.species` stays `Species.HUMAN` - only
`.occult_types` changes (`game_api.md` Sec.3's `SpeciesExtended` note: "small dog" is still
`Species.DOG`, never a separate species member; the same is true of every human-form occult). So the
single `species == HUMAN` check below already covers "human/human-like occults" exactly as SPEC.md
Sec.11 asks, and a pet's `.species` is never `HUMAN` - no separate species allow-list needed.

Not built here, on purpose (SPEC.md Sec.11/Sec.18's family-pairing open item): a two-Sim
"is this pairing okay" predicate (`adult_wants.md` Sec.0 sketches `is_mutual_consent_ok(actor,
target)`). SPEC.md Sec.11 explicitly scopes that build-blocking check to pairing-based features only
(V2's fertility picker) - none of BP11's three V1 rows (the interstitial, the settings front door, the
panic action) ever pick a Sim pair, so this file has nothing to gate there yet.
"""
from .. import common, settings

ADULT_AGES = 16 | 32 | 64          # Age.YOUNGADULT | Age.ADULT | Age.ELDER
HUMAN_SPECIES = 1                  # Species.HUMAN


def is_adult_content_allowed(sim_info):
    """True only for a young adult/adult/elder, human-species Sim. Never raises - anything that
    doesn't look like a real SimInfo (missing age/species) is treated as "not allowed", never as an
    error to propagate."""
    try:
        age = sim_info.age
        species = sim_info.species
    except AttributeError:
        return False
    if not isinstance(age, int) or not (age & ADULT_AGES):
        return False
    return species == HUMAN_SPECIES


def _ww_present():
    """`compat.wickedwhims.is_present()` (BP7's own safe, non-import resource probe - SPEC.md Sec.0/
    Sec.10), or False if `compat/` isn't importable for any reason (a build-order accident; the
    package exists in this tree, but this file never assumes that), or the probe itself raises.

    SAFE-DEFAULT DIRECTION - the opposite of `settings.py`'s own MCCC fallback: `settings._mccc_
    present()` defaults to False-when-missing because that keeps Novulon's OWN gameplay features on
    (the safer direction for that guard). Here, "not detected" IS the safe default for a gate that
    unlocks the Adult section - this file must never show adult content on the strength of a presence
    check it could not actually perform. The real probe (a specific, pinned interaction/tuning
    instance id, re-verified against a fresh disassembly of the installed WickedWhims copy - see
    `compat/wickedwhims.py`'s own docstring for how it corrected a real type/id-pairing bug in the
    spec's own carried-forward citation) is `compat/wickedwhims.py`'s charter (BP7, SPEC.md Sec.10),
    not duplicated or guessed at here - this file only ever calls its public `is_present()`."""
    try:
        from ..compat import wickedwhims as ww_compat
    except Exception:
        return False
    try:
        return bool(ww_compat.is_present())
    except Exception:
        common.log_exception('adult.gate: compat.wickedwhims.is_present()')
        return False


def is_adult_section_available():
    """WickedWhims present AND the player opted in (`adult.enabled`, off by default). Both must be
    true - SPEC.md Sec.11's own wording, "If either is false, no 'Adult' tile is built ... at all"."""
    return _ww_present() and bool(settings.get('adult.enabled', False))
