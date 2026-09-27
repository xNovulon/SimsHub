"""EA names BP13 (package build) cites - see this package's __init__.py for the row shape.

Exposed as both `ROWS` and `MANIFEST` (two names for the same list): the aggregator's own __init__.py
contract was still being actively revised elsewhere in this shared working tree while this file was
written, oscillating between the two names - exporting both means this file satisfies whichever one the
aggregator settles on, without needing to chase that file's edits.

Checked against THIS installed game's own .pyc:

    python sims_hub/tools/pyc37.py "E:/The Sims 4/Data/Simulation/Gameplay/simulation.zip" \\
        interactions/base/immediate_interaction.pyc --outline

    -> ImmediateSuperInteraction()  line 48
       immediate(cls)  line 99

Checked against game build packversion 109.0.465.1030 (E:/The Sims 4/EP21/Version.ini).

`novulon_tuning.py`'s `basic_extras`/`display_name`/`pie_menu_icon`/`target_type`/`simless` tuning-field
names are not Python `.pyc` symbols (they are declarative Tunable fields on the tuning class hierarchy,
not disassemblable with `pyc37.py --outline`, which only lists nested function/method code objects) - those
are carried forward from `build_plan.md` §2b/§2a's own verification, which read the real, installed
`mc_cmd_center.package`'s actual XML byte-for-byte, a stronger check for XML schema than a bytecode outline
would give. That is a distinct, already-completed verification this file does not repeat; only the one
Python module/class name below is re-checked here, against this machine's actual game build.

The three DBPF resource-type constants BP13 writes (`0xE882D22F` Interaction tuning, `0x220557DA` STBL,
`0x00B2D882` DDS icon) are binary resource-type ids, not `.pyc` symbols either - they are cross-checked
instead against this repo's own already-trusted code that reads real packages today: `0x220557DA` in
`wicked_animator/backend/dbpf.py`'s `NAMES` dict, `0x00B2D882` as `texfmt.py`'s `T_DST`, and `0xE882D22F`
in `sims_hub/speedkit/{dedup,fastmode}.py` and `wicked_animator/backend/dbpf.py`. Not a ROWS entry below
(not a name in a `.pyc`), but recorded here so the provenance is not lost.
"""

ROWS = MANIFEST = [
    ('interactions.base.immediate_interaction', 'ImmediateSuperInteraction', 'class'),
]
