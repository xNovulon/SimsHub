"""Draw Novulon's menu icons: tools/novulon_glyphs.py -> tools/novulon_assets/icons/<name>.png (128 x 128 RGBA).

    python tools/build_novulon_icons.py            (needs Playwright's Chromium: pip install playwright)

Each icon is the glyph in white on Novulon's pink-to-purple rounded tile (the look of the Wicked Animator's own
icon tiles); 'logo' is the brand mark on its dark tile. The PNGs are kept in the repository, so building the mod's
package (tools/build_novulon_package.py) never needs a browser. contact_sheet.png shows them all side by side.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from tools.novulon_glyphs import GLYPHS, LOGO   # noqa: E402

OUT = os.path.join(HERE, 'novulon_assets', 'icons')
SIZE = 128

TILE_CSS = """
* { margin: 0; padding: 0; }
body { background: transparent; }
.t { width: %(s)dpx; height: %(s)dpx; border-radius: 30px; position: relative; overflow: hidden;
     background: linear-gradient(140deg, #ff5fa6 0%%, #e04fd0 48%%, #8b5cf6 100%%); }
.t::before { content: ''; position: absolute; inset: 0; border-radius: 30px;
     background: radial-gradient(circle at 28%% 18%%, rgba(255,255,255,.34), rgba(255,255,255,0) 58%%); }
.t::after { content: ''; position: absolute; inset: 0; border-radius: 30px; box-shadow: inset 0 0 0 2px rgba(255,255,255,.22),
     inset 0 -10px 22px rgba(60,10,90,.28); }
.t svg { position: absolute; left: 50%%; top: 50%%; width: 66px; height: 66px; transform: translate(-50%%, -50%%);
     fill: none; stroke: #fff; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
     filter: drop-shadow(0 2px 3px rgba(70, 0, 80, .35)); }
.logo { width: %(s)dpx; height: %(s)dpx; }
.logo svg { width: %(s)dpx; height: %(s)dpx; }
""" % {'s': SIZE}


def page_html(name):
    if name == LOGO:
        with open(os.path.join(HERE, 'novulon_assets', 'novulon-mark.svg'), encoding='utf-8') as f:
            body = '<div class="logo" id="x">%s</div>' % f.read()
    else:
        body = '<div class="t" id="x"><svg viewBox="0 0 24 24">%s</svg></div>' % GLYPHS[name]
    return '<!doctype html><html><head><style>%s</style></head><body>%s</body></html>' % (TILE_CSS, body)


def main():
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    names = sorted(GLYPHS) + [LOGO]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': SIZE, 'height': SIZE}, device_scale_factor=1)
        for n in names:
            page.set_content(page_html(n))
            page.locator('#x').screenshot(path=os.path.join(OUT, n + '.png'), omit_background=True)
        # every icon on one sheet, for looking them over
        cells = ''.join('<figure><img src="file:///%s"><figcaption>%s</figcaption></figure>'
                        % (os.path.join(OUT, n + '.png').replace('\\', '/'), n) for n in names)
        sheet = ('<!doctype html><html><head><style>body{margin:0;padding:24px;background:#f3f1f6;font:13px sans-serif;'
                 'display:grid;grid-template-columns:repeat(10,140px);gap:14px}figure{margin:0;text-align:center}'
                 'img{width:96px;height:96px}figcaption{color:#444;margin-top:4px}</style></head><body>%s</body></html>' % cells)
        sheet_path = os.path.join(OUT, '_sheet.html')
        with open(sheet_path, 'w', encoding='utf-8') as f:
            f.write(sheet)
        page.set_viewport_size({'width': 10 * 154 + 48, 'height': 200})
        page.goto('file:///' + sheet_path.replace('\\', '/'))
        page.screenshot(path=os.path.join(HERE, 'novulon_assets', 'contact_sheet.png'), full_page=True)
        os.remove(sheet_path)
        browser.close()
    print('%d icons in %s' % (len(names), OUT))


if __name__ == '__main__':
    main()
