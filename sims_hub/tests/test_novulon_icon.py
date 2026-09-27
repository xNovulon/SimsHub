"""Tests for tools/novulon_icon.py. Pure 3.12, no game (Tier 1)."""
import os
import sys
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(PROJECT)
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'wicked_animator', 'backend'))

from tools import novulon_icon  # noqa: E402
import texfmt  # noqa: E402


def _gradient_rgba(w, h):
    """A distinct value per channel per pixel, so a channel swap or off-by-one would show up."""
    out = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 4
            out[i + 0] = x * 7 % 256          # R
            out[i + 1] = y * 11 % 256         # G
            out[i + 2] = (x + y) * 3 % 256    # B
            out[i + 3] = 255 if (x + y) % 5 else 40   # A (some non-opaque pixels too)
    return bytes(out)


class RoundTripTests(unittest.TestCase):
    def test_round_trip_32x32(self):
        rgba = _gradient_rgba(32, 32)
        dds = novulon_icon.encode_dds_rgba32(32, 32, rgba)
        info = texfmt.dds_info(dds)
        self.assertEqual((info['width'], info['height'], info['format']), (32, 32, 'RAW'))
        px = texfmt.decode_dds(dds)
        self.assertEqual(px.shape, (32, 32, 4))
        self.assertEqual(px.tobytes(), rgba)

    def test_round_trip_48x48(self):
        rgba = _gradient_rgba(48, 48)
        dds = novulon_icon.encode_dds_rgba32(48, 48, rgba)
        px = texfmt.decode_dds(dds)
        self.assertEqual(px.tobytes(), rgba)

    def test_header_layout_matches_the_verified_sample(self):
        """gaps.md §A.3 / build_plan.md §2b: header flags 0x0000100F, 128-byte header + width*height*4."""
        rgba = bytes(32 * 32 * 4)
        dds = novulon_icon.encode_dds_rgba32(32, 32, rgba)
        self.assertEqual(dds[:4], b'DDS ')
        self.assertEqual(len(dds), 128 + 32 * 32 * 4)
        import struct
        size, flags, h, w, pitch, depth, mips = struct.unpack_from('<7I', dds, 4)
        self.assertEqual((size, flags, h, w, pitch, depth, mips), (124, 0x0000100F, 32, 32, 128, 0, 0))
        pf_size, pf_flags = struct.unpack_from('<II', dds, 76)
        self.assertEqual((pf_size, pf_flags), (32, 0x41))

    def test_solid_colour(self):
        rgba = bytes([10, 20, 30, 255]) * (32 * 32)
        dds = novulon_icon.encode_dds_rgba32(32, 32, rgba)
        px = texfmt.decode_dds(dds)
        self.assertTrue((px[..., 0] == 10).all())
        self.assertTrue((px[..., 1] == 20).all())
        self.assertTrue((px[..., 2] == 30).all())
        self.assertTrue((px[..., 3] == 255).all())

    def test_wrong_byte_count_raises(self):
        with self.assertRaises(ValueError):
            novulon_icon.encode_dds_rgba32(32, 32, bytes(10))

    def test_non_positive_dimensions_raise(self):
        with self.assertRaises(ValueError):
            novulon_icon.encode_dds_rgba32(0, 32, b'')


if __name__ == '__main__':
    unittest.main(verbosity=2)
