"""data/wickedwhims_icon.png -> data/wickedwhims_icon.dds, the logo WickedWhims shows next to our animations.

    python tools/make_ww_icon.py

The game draws list icons from DDS pictures (type 0x00B2D882, 'DST5'), the way WickedWhims ships its own 128 px
icons; the tuning still names them with a PNG-typed key (see backend/wwpackage.py). Run it again after changing the PNG.
"""
import os
import sys

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
import posepack  # noqa: E402

SRC = os.path.join(ROOT, 'data', 'wickedwhims_icon.png')
OUT = os.path.join(ROOT, 'data', 'wickedwhims_icon.dds')
SIZE = 128

im = Image.open(SRC).convert('RGBA').resize((SIZE, SIZE), Image.LANCZOS)
with open(OUT, 'wb') as f:
    f.write(posepack.dst5(im.tobytes(), SIZE, SIZE))
print('wrote', OUT, os.path.getsize(OUT), 'bytes')
