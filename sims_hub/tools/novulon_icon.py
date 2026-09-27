"""Encode an uncompressed RAW DDS image, DBPF type 0x00B2D882 (group 0) - the Sims 4's pie-menu icon format.

`gaps.md` §A.3 resolves a contradiction between two research passes in favor of this format:
`mc_cmd_center.package`'s actual pie-menu icon is uncompressed 32bpp RAW DDS (32x32 and 48x48, header
flags `0x0000100F`, no FourCC) - not DXT5, which a different pass measured from WickedWhims's much larger
128x128 interaction icons, a different asset class. `wicked_animator/backend/texfmt.py` can only decode a
RAW DDS today (`decode_dds()`/`dds_info()`); it has no encoder of any kind - this is new code, the exact
inverse of that decoder, matched so a round trip through it agrees byte for byte.

Layout (128-byte header = 4-byte 'DDS ' magic + 124-byte DDS_HEADER, matching `dds_info()`'s own unpacking
at absolute offsets 4 and 76):
    dwSize=124, dwFlags=0x0000100F (CAPS|HEIGHT|WIDTH|PITCH|PIXELFORMAT), dwHeight, dwWidth,
    dwPitchOrLinearSize=width*4, dwDepth=0, dwMipMapCount=0, dwReserved1[11]=0,
    DDS_PIXELFORMAT: dwSize=32, dwFlags=0x41 (ALPHAPIXELS|RGB), dwFourCC=0, dwRGBBitCount=32,
        dwRBitMask=0x00FF0000, dwGBitMask=0x0000FF00, dwBBitMask=0x000000FF, dwABitMask=0xFF000000,
    dwCaps=0x1000 (TEXTURE), dwCaps2=0, dwCaps3=0, dwCaps4=0, dwReserved2=0
then width*height*4 bytes of pixel data, one BGRA dword per pixel (little-endian, so byte order in the
file is B, G, R, A - the masks above read that back as R/G/B/A in `texfmt.py:decode_dds()`).
"""
import struct

HEADER_SIZE = 128           # 4-byte magic + 124-byte DDS_HEADER
DDS_FLAGS = 0x0000100F       # DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PITCH | DDSD_PIXELFORMAT
PF_FLAGS = 0x00000041        # DDPF_ALPHAPIXELS | DDPF_RGB
DDS_CAPS_TEXTURE = 0x1000
MASK_R, MASK_G, MASK_B, MASK_A = 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000


def encode_dds_rgba32(width, height, rgba):
    """width*height*4 bytes of straight RGBA (R, G, B, A per pixel) -> an uncompressed 32bpp RAW DDS file."""
    if width <= 0 or height <= 0:
        raise ValueError('width/height must be positive')
    expected = width * height * 4
    if len(rgba) != expected:
        raise ValueError('rgba must be %d bytes for a %dx%d RGBA image (got %d)' % (expected, width, height, len(rgba)))
    header = bytearray(HEADER_SIZE)
    header[0:4] = b'DDS '
    struct.pack_into('<7I', header, 4, 124, DDS_FLAGS, height, width, width * 4, 0, 0)
    # bytes 32:76 are dwReserved1[11] - already zero
    struct.pack_into('<II', header, 76, 32, PF_FLAGS)             # DDS_PIXELFORMAT.dwSize, dwFlags
    # bytes 84:88 are dwFourCC - already zero (no FourCC: this is the RAW branch)
    struct.pack_into('<5I', header, 88, 32, MASK_R, MASK_G, MASK_B, MASK_A)   # bits, R/G/B/A masks
    struct.pack_into('<5I', header, 108, DDS_CAPS_TEXTURE, 0, 0, 0, 0)         # caps/caps2/caps3/caps4/reserved2
    return bytes(header) + _rgba_to_bgra(rgba)


def _rgba_to_bgra(rgba):
    """Swap the R and G/B position so a little-endian dword read of each pixel is 0xAARRGGBB, matching
    the R/G/B/A masks above (byte order in the file per pixel: B, G, R, A)."""
    out = bytearray(len(rgba))
    out[0::4] = rgba[2::4]     # B
    out[1::4] = rgba[1::4]     # G
    out[2::4] = rgba[0::4]     # R
    out[3::4] = rgba[3::4]     # A
    return bytes(out)
