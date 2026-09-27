"""The "Sims" Main Menu tile - the Sim Browser (SPEC.md `sims/` Sec 5, BP4: __init__/query/browser).

Registers Novulon's "Sims" section with core's section registry (`commands.add_section` -
`commands.py` Sec 3.7, BP1) at IMPORT TIME, the same way every feature package is documented to
(`novulon/__init__.py`'s own docstring: "Feature packages ... register their own Main Menu tile with
commands.add_section(...) at their own import time; this file does not know their names"). Nothing in
`novulon/__init__.py`'s start-up sequence imports this package by name, on purpose - what makes this
run anyway is the game's OWN bulk importer, which that same docstring also cites:
"The game imports every .pyc in a .ts4script on its own (sims4.importer.utils.module_names_gen)".
That importer reaches every .pyc in the archive, including this package's three files; Python's
ordinary import semantics run a package's `__init__.py` the first time anything imports one of its
submodules, so simply shipping inside `Novulon.ts4script` is what wires this tile in - no change
needed to any BP1/BP3-owned file.
"""
from . import browser  # noqa: F401  (import alone registers every 'novulon.sims.*' action - see
                        # browser.py's own _register_commands())
from .. import commands

commands.add_section(
    'sims', browser.open_root,
    label='Sims', description='Browse, filter, search.', order=10)
