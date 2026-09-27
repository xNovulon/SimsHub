"""Build the Novulon pie-menu interaction's tuning XML (DBPF type 0xE882D22F, "Interaction tuning").

Shaped like the verified MCCC example `build_plan.md` §2a reads out of its real, installed package
(`mc_cmd_center.package`, resource `0xE882D22F:0:0xD27DB58CF1DAF8FA`, class `ImmediateSuperInteraction`,
module `interactions.base.immediate_interaction` - confirmed present in THIS game build's own
`simulation.zip` via `pyc37.py --outline`, see `tools/novulon_api_manifest/bp13_package_build.py`):
a `basic_extras` list with one `do_command` extra running our own registered command; `target_type="OBJECT"`,
`simless="True"`, `test_globals` empty - the computer restriction happens entirely at runtime in
`ingame/novulon/inject.py`, never in this XML (SPEC.md §6). `display_name` is a plain STBL key (u32);
`pie_menu_icon` uses the symbolic placeholder `resource_key` type:group `2f7d0004:80000000` with our icon's
instance id - the game resolves this to the real backing resource at type `0x00B2D882` group `0`
(`build_plan.md` §2b); writing the XML field and the packaged resource type the same way round is the
easiest mistake to make here, called out explicitly.

No bytes are copied from any third-party mod's package - this XML is new text, built field by field.
"""
from xml.sax.saxutils import escape

ICON_PLACEHOLDER_TYPE = 0x2F7D0004
ICON_PLACEHOLDER_GROUP = 0x80000000


def build_interaction_xml(instance_id, name, title_stbl_key, icon_instance_id, command, pie_menu_priority=10):
    """One ImmediateSuperInteraction resource, as UTF-8 XML text.

    instance_id: our own FNV64 custom id (top bit set) for this interaction.
    name: the tuning's own debug name (never shown to the player - display_name is what shows).
    title_stbl_key: the STBL key (u32) whose text is the pie-menu label (e.g. "Novulon").
    icon_instance_id: the instance id the DDS icon resource is written under (novulon_icon.py's output).
    command: the console command basic_extras.do_command runs, e.g. 'novulon.open_menu'.
    """
    icon_key = '%08x:%08x:%016x' % (ICON_PLACEHOLDER_TYPE, ICON_PLACEHOLDER_GROUP, icon_instance_id & 0xFFFFFFFFFFFFFFFF)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<I c="ImmediateSuperInteraction" i="interaction" m="interactions.base.immediate_interaction" '
        'n="%s" s="%d">\n'
        '  <T n="target_type">OBJECT</T>\n'
        '  <T n="simless">True</T>\n'
        '  <T n="display_name">0x%08X</T>\n'
        '  <T n="pie_menu_priority">%d</T>\n'
        '  <T n="pie_menu_icon">%s</T>\n'
        '  <L n="test_globals"/>\n'
        '  <L n="basic_extras">\n'
        '    <U>\n'
        '      <T n="extra_type">do_command</T>\n'
        '      <T n="command">%s</T>\n'
        '    </U>\n'
        '  </L>\n'
        '</I>\n'
    ) % (escape(name), instance_id & 0xFFFFFFFFFFFFFFFF, title_stbl_key & 0xFFFFFFFF, pie_menu_priority,
         icon_key, escape(command))
