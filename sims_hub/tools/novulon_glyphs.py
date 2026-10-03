"""Novulon's menu icons: one line-drawn glyph per name (24 x 24, 2 px round strokes - the same style as the Wicked
Animator's own icons), drawn white on Novulon's pink-to-purple tile by tools/build_novulon_icons.py.

The names are what the mod asks for at runtime (ingame/novulon/icons.py turns a name into the icon's resource key),
so a name here must never be renamed without changing it there too. Every glyph is drawn for Novulon; nothing is
copied from an icon library.
"""

GLYPHS = {
    # ---- the main menu
    'sims': '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/>'
            '<path d="M16 4.6a3.5 3.5 0 0 1 0 6.8"/><path d="M18 14.3c2.2.7 3.5 2.8 3.5 5.7"/>',
    'household': '<path d="M3 11l9-8 9 8"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
    'cheats': '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
    'world': '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/>'
             '<path d="M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>',
    'settings': '<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="6.5"/>'
                '<path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
    'adult': '<path d="M12 22c4 0 7-2.8 7-6.8 0-3.2-1.8-5.4-3.6-7.3-.3 2-1.3 3.4-2.6 4.1.2-3.7-1.4-7.2-4.3-9 0 3.6-1.8 5.6-3.4 7.6C3.9 12.3 5 14 5 15.4 5 19.2 8 22 12 22z"/>',
    # ---- moving around
    'back': '<path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/>',
    'next': '<path d="M9 18l6-6-6-6"/>',
    'prev': '<path d="M15 18l-6-6 6-6"/>',
    'search': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/>',
    'filter': '<path d="M3.5 4.5h17l-6.5 8v6l-4 2v-8z"/>',
    'select': '<path d="M4 6.5l1.6 1.6L8.5 5"/><path d="M11.5 6.5H20"/><path d="M4 12.5l1.6 1.6 2.9-3.1"/>'
              '<path d="M11.5 12.5H20"/><path d="M4 18.5h4.5M11.5 18.5H20"/>',
    'clear': '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    'check': '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    'on': '<rect x="2.5" y="7" width="19" height="10" rx="5"/><circle cx="16.5" cy="12" r="2.6" fill="#fff"/>',
    'off': '<rect x="2.5" y="7" width="19" height="10" rx="5"/><circle cx="7.5" cy="12" r="2.6"/>',
    'edit': '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.5h.01"/>',
    'warning': '<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5M12 17.5h.01"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'minus': '<path d="M5 12h14"/>',
    'percent': '<path d="M19 5L5 19"/><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/>',
    # ---- who
    'user': '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
    'male': '<circle cx="10" cy="14" r="5.5"/><path d="M14 10l6-6M15 4h5v5"/>',
    'female': '<circle cx="12" cy="9" r="5.5"/><path d="M12 14.5V22M8.5 18.5h7"/>',
    'pets': '<path d="M12 21c-2.8 0-5-1.2-5-3.4 0-2.3 2.5-5.1 5-5.1s5 2.8 5 5.1c0 2.2-2.2 3.4-5 3.4z"/>'
            '<circle cx="5.5" cy="10.5" r="1.8"/><circle cx="9.3" cy="6.3" r="1.8"/><circle cx="14.7" cy="6.3" r="1.8"/>'
            '<circle cx="18.5" cy="10.5" r="1.8"/>',
    'card': '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2.3"/>'
            '<path d="M5.5 16.5c.6-1.6 1.9-2.4 3.5-2.4s2.9.8 3.5 2.4"/><path d="M14.5 10h4M14.5 13.5h3"/>',
    'played': '<path d="M3.5 18.5h17"/><path d="M4 15.5L3 7l5 4 4-6 4 6 5-4-1 8.5z"/>',
    'here': '<path d="M5 21V4a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v17"/><path d="M3 21h18"/><path d="M15 12h.01"/>',
    'playable': '<circle cx="10" cy="8" r="4"/><path d="M3 21c0-4 3.1-6.5 7-6.5 1.6 0 3 .4 4.2 1.1"/>'
                '<path d="M15.5 18.5l2 2 4-4.5"/>',
    'npc': '<circle cx="10" cy="8" r="4"/><path d="M3 21c0-4 3.1-6.5 7-6.5 1.6 0 3 .4 4.2 1.1"/><path d="M16 18.5h5"/>',
    'join': '<circle cx="10" cy="8" r="4"/><path d="M3 21c0-4 3.1-6.5 7-6.5 1.6 0 3 .4 4.2 1.1"/>'
            '<path d="M18.5 15.5v6M15.5 18.5h6"/>',
    # ---- a Sim
    'cas': '<path d="M12 7.5a2.2 2.2 0 1 1 2.2-2.2"/>'
           '<path d="M12 7.5v1.4L3.4 14.5c-1 .7-.5 2.3.8 2.3h15.6c1.3 0 1.8-1.6.8-2.3L12 8.9"/>',
    'needs': '<path d="M12 2l5 8-5 12-5-12z"/><path d="M7 10h10"/>',
    'fill': '<rect x="2.5" y="7" width="17" height="10" rx="2"/><path d="M22 10.5v3"/><path d="M6 10v4M9.5 10v4M13 10v4M16 10v4"/>',
    'mood': '<circle cx="12" cy="12" r="9"/><path d="M8.5 14.5c1.7 1.8 5.3 1.8 7 0"/><path d="M9 9.5h.01M15 9.5h.01"/>',
    'moodlet': '<path d="M12 3l1.8 5.4L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.6z"/>'
               '<path d="M19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>',
    'skills': '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    'trophy': '<path d="M8 4h8v5a4 4 0 0 1-8 0z"/><path d="M8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4"/>'
              '<path d="M12 13v4M8.5 20.5h7"/>',
    'career': '<rect x="3" y="7" width="18" height="13" rx="2"/>'
              '<path d="M9 7V5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5v2"/><path d="M3 12.5h18"/>',
    'traits': '<path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9z"/><circle cx="7.5" cy="7.5" r="1.3"/>',
    'aspiration': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
    'age': '<path d="M6 3h12M6 21h12"/><path d="M7 3c0 4 2.5 6 5 9-2.5 3-5 5-5 9M17 3c0 4-2.5 6-5 9 2.5 3 5 5 5 9"/>',
    'age_up': '<circle cx="12" cy="12" r="9"/><path d="M12 16.5v-9M8 11.5l4-4 4 4"/>',
    'age_down': '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v9M8 12.5l4 4 4-4"/>',
    'heart': '<path d="M12 20.5s-7.5-4.6-9.2-9.4C1.6 7.6 4 4.5 7.3 4.5c2 0 3.6 1.1 4.7 2.8 1.1-1.7 2.7-2.8 4.7-2.8 3.3 0 5.7 3.1 4.5 6.6-1.7 4.8-9.2 9.4-9.2 9.4z"/>',
    'friends': '<circle cx="8" cy="8" r="3"/><circle cx="16" cy="8" r="3"/>'
               '<path d="M2.5 19c0-3.1 2.4-5.2 5.5-5.2 1.5 0 2.9.5 3.9 1.4M21.5 19c0-3.1-2.4-5.2-5.5-5.2-1.5 0-2.9.5-3.9 1.4"/>',
    'occult': '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/>',
    'pregnancy': '<path d="M12 20.5s-7.5-4.6-9.2-9.4C1.6 7.6 4 4.5 7.3 4.5c2 0 3.6 1.1 4.7 2.8 1.1-1.7 2.7-2.8 4.7-2.8 3.3 0 5.7 3.1 4.5 6.6-1.7 4.8-9.2 9.4-9.2 9.4z"/>'
                 '<path d="M12 9.5v5M9.5 12h5"/>',
    'teleport': '<path d="M12 21.5s7-6.1 7-12a7 7 0 0 0-14 0c0 5.9 7 12 7 12z"/><circle cx="12" cy="9.5" r="2.5"/>',
    'reset': '<path d="M20 11a8 8 0 0 0-14.4-4.6L4 8"/><path d="M4 3.5V8h4.5"/>'
             '<path d="M4 13a8 8 0 0 0 14.4 4.6L20 16"/><path d="M20 20.5V16h-4.5"/>',
    'delete': '<path d="M4 6.5h16"/><path d="M9.5 6.5V4.5h5v2"/><path d="M6 6.5l1 13.5h10l1-13.5"/><path d="M10 10.5v6M14 10.5v6"/>',
    # ---- money and things
    'money': '<circle cx="12" cy="12" r="9"/>'
             '<path d="M14.8 9.2c-.6-1-1.7-1.6-2.9-1.6-1.6 0-2.9.9-2.9 2.2 0 3 6 1.6 6 4.5 0 1.3-1.3 2.2-3 2.2-1.3 0-2.5-.6-3.1-1.7"/>'
             '<path d="M12 5.5v13"/>',
    'wallet': '<path d="M19 7V5.5A1.5 1.5 0 0 0 17.5 4H5a2 2 0 0 0 0 4h14a1 1 0 0 1 1 1v9.5a1.5 1.5 0 0 1-1.5 1.5H5a2 2 0 0 1-2-2V6"/>'
              '<circle cx="16.5" cy="14" r="1.2"/>',
    'inventory': '<path d="M3.5 7.5L12 3l8.5 4.5v9L12 21l-8.5-4.5z"/><path d="M3.5 7.5L12 12l8.5-4.5M12 12v9"/>',
    # ---- the world
    'time': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    'speed': '<path d="M3.5 6l8 6-8 6z"/><path d="M12.5 6l8 6-8 6z"/>',
    'autonomy': '<rect x="5" y="8" width="14" height="11" rx="3"/><path d="M12 8V4.5M12 4.5h.01"/>'
                '<path d="M9.5 13h.01M14.5 13h.01"/><path d="M9.5 16.5h5"/>',
    # ---- the mod itself
    'compat': '<path d="M10 4.5a2 2 0 0 1 4 0V6h4v4h-1.5a2 2 0 0 0 0 4H18v4h-4v-1.5a2 2 0 0 0-4 0V18H6v-4h1.5a2 2 0 0 0 0-4H6V6h4z"/>',
    'log': '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6"/>',
    'stop': '<path d="M8 3h8l5 5v8l-5 5H8l-5-5V8z"/><path d="M9.5 9.5h5v5h-5z"/>',
}

# The brand mark (tools/novulon_assets/novulon-mark.svg) is rendered as the 'logo' icon on its own dark tile.
LOGO = 'logo'
NAMES = tuple(sorted(GLYPHS)) + (LOGO,)
