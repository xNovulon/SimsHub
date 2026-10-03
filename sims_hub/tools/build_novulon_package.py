r"""Build dist/Novulon_Tuning.package: Novulon's two pie-menu entries, their label in every language, and its icons.

    python tools/build_novulon_package.py

What goes in (all group 0, written with speedkit/dbpf.py's PackageWriter):
  * two interactions (type 0xE882D22F, tools/novulon_tuning.py): "Novulon" on computers and tablets runs
    'novulon.menu'; "Novulon" on a Sim runs 'novulon.sim <that Sim's id>'. ingame/novulon/entry.py adds them to the
    objects and registers both commands.
  * a string table (type 0x220557DA) per game language with the label "Novulon" (the same English text in each, so
    no language shows a blank entry).
  * the pie-menu icon (type 0x00B2D882, 32 x 32, from tools/novulon_assets/novulon-mark-32.png) and every menu icon
    (128 x 128, from tools/novulon_assets/icons/<name>.png, drawn by tools/build_novulon_icons.py), each an
    uncompressed RAW DDS (tools/novulon_icon.py) under icon_instance(name) - the instance ingame/novulon/icons.py
    asks for.
Everything Novulon's menus show beyond that is built at runtime from plain text.
"""
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)
from speedkit.dbpf import Package, PackageWriter  # noqa: E402
from tools import novulon_icon, novulon_stbl, novulon_tuning  # noqa: E402
from tools import novulon_ids as ids  # noqa: E402
from tools.novulon_ids.bp13_package_build import icon_instance, stbl_id  # noqa: E402
from tools.novulon_glyphs import NAMES as ICON_NAMES  # noqa: E402

DIST = os.path.join(PROJECT, 'dist', 'Novulon_Tuning.package')
ASSET_DIR = os.path.join(PROJECT, 'tools', 'novulon_assets')
ICON_PNG_32 = os.path.join(ASSET_DIR, 'novulon-mark-32.png')
ICON_DIR = os.path.join(ASSET_DIR, 'icons')
ICON_SIZE = 128

T_INTERACTION = 0xE882D22F
T_STBL = 0x220557DA
T_DDS = 0x00B2D882

MENU_COMMAND = 'novulon.menu'      # ingame/novulon/entry.py registers both commands
SIM_COMMAND = 'novulon.sim'
MENU_TITLE = 'Novulon'


def load_rgba(path, size):
    from PIL import Image
    im = Image.open(path).convert('RGBA')
    if im.size != (size, size):
        raise ValueError('%s is %dx%d, expected %dx%d' % (path, im.size[0], im.size[1], size, size))
    return im.tobytes()


def resources():
    """[((type, group, instance), bytes)] - everything the package holds, in write order."""
    out = [
        ((T_INTERACTION, 0, ids.INTERACTION_OPEN_MENU), novulon_tuning.build_interaction_xml(
            ids.INTERACTION_OPEN_MENU, 'Novulon_OpenMenu', ids.STR_MENU_TITLE, ids.ICON_PIE_MENU_32,
            MENU_COMMAND).encode('utf-8')),
        ((T_INTERACTION, 0, ids.INTERACTION_SIM_MENU), novulon_tuning.build_interaction_xml(
            ids.INTERACTION_SIM_MENU, 'Novulon_SimMenu', ids.STR_MENU_TITLE, ids.ICON_PIE_MENU_32,
            SIM_COMMAND, pass_target=True).encode('utf-8')),
    ]
    table = novulon_stbl.build_stbl({ids.STR_MENU_TITLE: MENU_TITLE})
    for loc in ids.LOCALES:
        out.append(((T_STBL, 0, stbl_id('Novulon_Strings', loc)), table))
    out.append(((T_DDS, 0, ids.ICON_PIE_MENU_32), novulon_icon.encode_dds_rgba32(32, 32, load_rgba(ICON_PNG_32, 32))))
    for name in ICON_NAMES:
        rgba = load_rgba(os.path.join(ICON_DIR, name + '.png'), ICON_SIZE)
        out.append(((T_DDS, 0, icon_instance(name)), novulon_icon.encode_dds_rgba32(ICON_SIZE, ICON_SIZE, rgba)))
    return out


def build(dist=DIST):
    """Write dist. Returns {'dist', 'bytes', 'entries': [(t, g, i), ...]}."""
    res = resources()
    os.makedirs(os.path.dirname(dist), exist_ok=True)
    with PackageWriter(dist) as w:
        for tgi, data in res:
            w.add(tgi, data)
    return {'dist': dist, 'bytes': os.path.getsize(dist), 'entries': [tgi for tgi, _ in res]}


def verify(dist=DIST):
    """Read dist back: both interactions (right command, label and icon, the Sim one passing its target), a string
    table per language holding the label, and every icon. Returns a list of problems (empty when it's right)."""
    import xml.etree.ElementTree as ET
    problems = []
    with Package(dist) as p:
        by = {(e.t, e.i): e for e in p.entries}
        for inst, command, target in ((ids.INTERACTION_OPEN_MENU, MENU_COMMAND, False),
                                      (ids.INTERACTION_SIM_MENU, SIM_COMMAND, True)):
            e = by.get((T_INTERACTION, inst))
            if e is None:
                problems.append('interaction %016X missing' % inst)
                continue
            root = ET.fromstring(p.read(e))
            if novulon_tuning.command_of(root) != command:
                problems.append('interaction %016X runs %r, not %r' % (inst, novulon_tuning.command_of(root), command))
            if novulon_tuning.passes_target(root) != target:
                problems.append('interaction %016X %s its target' % (inst, 'does not pass' if target else 'passes'))
            if int(root.findtext("T[@n='display_name']") or '0', 16) != ids.STR_MENU_TITLE:
                problems.append('interaction %016X has the wrong label key' % inst)
            key = novulon_tuning.icon_key_of(root) or ''
            if not key.upper().endswith('%016X' % ids.ICON_PIE_MENU_32):
                problems.append('interaction %016X has the wrong icon %r' % (inst, key))
        for loc in ids.LOCALES:
            e = by.get((T_STBL, stbl_id('Novulon_Strings', loc)))
            if e is None or novulon_stbl.read_stbl(p.read(e)).get(ids.STR_MENU_TITLE) != MENU_TITLE:
                problems.append('string table for language %02X missing or without the label' % loc)
        for name in ('pie_32',) + tuple(ICON_NAMES):
            inst = ids.ICON_PIE_MENU_32 if name == 'pie_32' else icon_instance(name)
            e = by.get((T_DDS, inst))
            if e is None or p.read(e)[:4] != b'DDS ':
                problems.append('icon %s missing' % name)
    return problems


def main():
    r = build()
    problems = verify(r['dist'])
    print('%s: %d resources, %d bytes' % (r['dist'], len(r['entries']), r['bytes']))
    for x in problems:
        print('PROBLEM:', x)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
