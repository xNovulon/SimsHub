"""Build the Novulon pie-menu interaction's tuning XML (DBPF type 0xE882D22F, "Interaction tuning").

Shaped field by field like MC Command Center's working computer entry (`mc_cmd_center.package`, resource
`0xE882D22F:0:0xD27DB58CF1DAF8FA`, class `ImmediateSuperInteraction`, module
`interactions.base.immediate_interaction`), which loads in THIS game build. The shapes matter - the game's tuning
loader reads each field by its tunable type, and a field written the wrong way is dropped:
  - `target_type` is an enum: `<E>`, not `<T>`.
  - `basic_extras` is a list of variants: `<V t="do_command"><U n="do_command"><T n="command">...`. Written flat, the
    extra loads as None and the interaction's `_tuning_loaded_callback` raises "'NoneType' object has no attribute
    'factory'" (seen in the owner's lastException.txt, 2026-09-28), so clicking does nothing.
  - `pie_menu_icon` is an optional icon variant: `<V t="enabled"><V t="resource_key"><U><T n="key">`. The key uses the
    placeholder type:group `2f7d0004:80000000` with our icon's instance id; the game resolves it to the packaged DDS
    resource at type `0x00B2D882` group `0` (the same pairing MCCC ships).
  - no `arguments` on the command: `novulon.menu` takes only the connection.
`simless` is True and `test_globals` empty - the computer restriction happens at runtime in `ingame/novulon/inject.py`
(SPEC.md §6). `_saveable` is disabled, so a save never records the interaction.

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
    command: the console command basic_extras.do_command runs - one the mod registers, e.g. 'novulon.menu'.
    """
    icon_key = '%08x:%08x:%016X' % (ICON_PLACEHOLDER_TYPE, ICON_PLACEHOLDER_GROUP, icon_instance_id & 0xFFFFFFFFFFFFFFFF)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<I c="ImmediateSuperInteraction" i="interaction" m="interactions.base.immediate_interaction" '
        'n="%s" s="%d">\n'
        '  <V t="disabled" n="_saveable" />\n'
        '  <L n="basic_extras">\n'
        '    <V t="do_command">\n'
        '      <U n="do_command">\n'
        '        <T n="command">%s</T>\n'
        '      </U>\n'
        '    </V>\n'
        '  </L>\n'
        '  <T n="debug">False</T>\n'
        '  <T n="display_name">0x%08X</T>\n'
        '  <T n="pie_menu_priority">%d</T>\n'
        '  <V t="enabled" n="pie_menu_icon">\n'
        '    <V n="enabled" t="resource_key">\n'
        '      <U n="resource_key">\n'
        '        <T n="key">%s</T>\n'
        '      </U>\n'
        '    </V>\n'
        '  </V>\n'
        '  <U n="progress_bar_enabled">\n'
        '    <T n="bar_enabled">False</T>\n'
        '  </U>\n'
        '  <T n="simless">True</T>\n'
        '  <E n="target_type">OBJECT</E>\n'
        '  <L n="test_globals" />\n'
        '</I>\n'
    ) % (escape(name), instance_id & 0xFFFFFFFFFFFFFFFF, escape(command), title_stbl_key & 0xFFFFFFFF,
         pie_menu_priority, icon_key)


def icon_key_of(root):
    """The pie_menu_icon key text of a parsed interaction (xml.etree root), or None."""
    return root.findtext("V[@n='pie_menu_icon']/V[@t='resource_key']/U[@n='resource_key']/T[@n='key']")


def command_of(root):
    """The do_command extra's command of a parsed interaction, or None."""
    return root.findtext("L[@n='basic_extras']/V[@t='do_command']/U[@n='do_command']/T[@n='command']")
