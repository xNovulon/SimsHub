r"""Build dist/Novulon_Tuning.package: one interaction tuning resource, one STBL table, one pie-menu icon.

    python tools/build_novulon_package.py

Composes the three resources `SPEC.md` §14 describes with `speedkit/dbpf.py:PackageWriter` - the DBPF
container writer this repo already has and already tests (`tests/test_dbpf_roundtrip.py`), NOT
`wicked_animator/backend/dbpf.py` (that file is read-only: `read_index`/`read_resource`, no writer). Source
art is `tools/novulon_assets/novulon-mark-32.png` (already rasterized during the design phase from
`novulon-mark.svg` - see that folder's own note on provenance); this file only re-encodes it as the DDS
bytes the game expects, it does not rasterize SVG itself.

V1 scope only ships what tuning actually needs: the pie-menu interaction's own label and hover text.
Everything else Novulon shows is a dynamically-built dialog (`common.notify`-style `get_raw_text`), which
needs no STBL entry at all (SPEC.md §4's `menukit` design) - so this package's STBL table has exactly two
strings, not a growing shared list every feature module has to append to.
"""
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)
from speedkit.dbpf import Package, PackageWriter  # noqa: E402
from tools import novulon_icon, novulon_stbl, novulon_tuning  # noqa: E402
from tools import novulon_ids as ids  # noqa: E402

DIST = os.path.join(PROJECT, 'dist', 'Novulon_Tuning.package')
ASSET_DIR = os.path.join(PROJECT, 'tools', 'novulon_assets')
ICON_PNG_32 = os.path.join(ASSET_DIR, 'novulon-mark-32.png')

T_INTERACTION = 0xE882D22F
T_STBL = 0x220557DA
T_DDS = 0x00B2D882

COMMAND = 'novulon.open_menu'
MENU_TITLE = 'Novulon'
MENU_HOVER = 'Open the Novulon menu.'


def load_icon_rgba(path=ICON_PNG_32, size=32):
    """The pie-menu icon's raw RGBA bytes, read from the already-rasterized PNG (design phase output)."""
    from PIL import Image
    im = Image.open(path).convert('RGBA')
    if im.size != (size, size):
        raise ValueError('%s is %dx%d, expected %dx%d' % (path, im.size[0], im.size[1], size, size))
    return im.tobytes()


def build(dist=DIST, icon_png=ICON_PNG_32):
    """Write dist. Returns {'dist', 'bytes', 'entries': [(t, g, i), ...]}."""
    xml = novulon_tuning.build_interaction_xml(
        ids.INTERACTION_OPEN_MENU, 'Novulon_OpenMenu', ids.STR_MENU_TITLE, ids.ICON_PIE_MENU_32, COMMAND)
    stbl = novulon_stbl.build_stbl({ids.STR_MENU_TITLE: MENU_TITLE, ids.STR_MENU_HOVER: MENU_HOVER})
    rgba = load_icon_rgba(icon_png, 32)
    dds = novulon_icon.encode_dds_rgba32(32, 32, rgba)
    os.makedirs(os.path.dirname(dist), exist_ok=True)
    entries = [(T_INTERACTION, 0, ids.INTERACTION_OPEN_MENU), (T_STBL, 0, ids.STBL_MAIN_EN),
               (T_DDS, 0, ids.ICON_PIE_MENU_32)]
    with PackageWriter(dist) as w:
        w.add(entries[0], xml.encode('utf-8'))
        w.add(entries[1], stbl)
        w.add(entries[2], dds)
    return {'dist': dist, 'bytes': os.path.getsize(dist), 'entries': entries}


def verify(dist=DIST):
    """Read dist back and check the three resources are present, the XML parses, and its display_name/
    pie_menu_icon fields point at the STBL/icon instance ids actually written. Returns a problem list."""
    import xml.etree.ElementTree as ET
    problems = []
    try:
        with Package(dist) as p:
            byi = {e.i: e for e in p.entries}
            interaction = byi.get(ids.INTERACTION_OPEN_MENU)
            if interaction is None or interaction.t != T_INTERACTION:
                problems.append('interaction tuning resource missing or wrong type')
            else:
                root = ET.fromstring(p.read(interaction))
                display = root.findtext("T[@n='display_name']")
                if display is None or int(display, 16) != ids.STR_MENU_TITLE:
                    problems.append('display_name does not match STR_MENU_TITLE')
                icon_field = root.findtext("T[@n='pie_menu_icon']")
                icon_inst = icon_field.split(':')[-1] if icon_field else ''
                if not icon_field or int(icon_inst, 16) != (ids.ICON_PIE_MENU_32 & 0xFFFFFFFFFFFFFFFF):
                    problems.append('pie_menu_icon does not point at ICON_PIE_MENU_32')
            stbl_entry = byi.get(ids.STBL_MAIN_EN)
            if stbl_entry is None or stbl_entry.t != T_STBL:
                problems.append('STBL resource missing or wrong type')
            icon_entry = byi.get(ids.ICON_PIE_MENU_32)
            if icon_entry is None or icon_entry.t != T_DDS:
                problems.append('icon resource missing or wrong type')
    except Exception as e:
        problems.append('could not read %s: %s' % (dist, e))
    return problems


def main():
    r = build()
    print('built %s: %d bytes, %d resources' % (r['dist'], r['bytes'], len(r['entries'])))
    problems = verify(r['dist'])
    if problems:
        print('PROBLEMS:', *problems, sep='\n  ')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
