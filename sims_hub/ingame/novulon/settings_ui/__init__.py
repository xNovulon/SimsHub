"""Settings tile - Adult Content on/off, Compatibility status, Log Level, About (SPEC.md `settings_ui/`
Sec 12, build package BP12).

`menu.py` does the actual work and registers the 'settings' Main Menu tile at its own import time
(`commands.add_section`, same pattern every feature package uses - `novulon/__init__.py`'s own
docstring). The game auto-imports every .pyc bundled into `Novulon.ts4script`
(`sims4.importer.utils.module_names_gen`), so simply being part of the build is enough - nothing else
needs to import this package by name for its tile to register.
"""
from . import menu  # noqa: F401  (import triggers menu.py's own commands.add_section() call)
