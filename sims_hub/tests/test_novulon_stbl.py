"""Tests for tools/novulon_stbl.py. Pure 3.12, no game, no fake Sims folder (Tier 1)."""
import os
import sys
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(PROJECT)
sys.path.insert(0, PROJECT)
# wicked_animator/backend/*.py import each other with flat names (e.g. "from dbpf import ..."), so it must
# be put on sys.path directly rather than imported as the wicked_animator.backend package.
sys.path.insert(0, os.path.join(REPO_ROOT, 'wicked_animator', 'backend'))

from tools import novulon_stbl  # noqa: E402
import doctor as wa_doctor  # noqa: E402
import posepack as wa_posepack  # noqa: E402


class RoundTripTests(unittest.TestCase):
    def test_own_reader_round_trip(self):
        strings = {0x110B1E89: 'Novulon', 0xABCDEF01: 'Open the Novulon menu.', 0x1: ''}
        data = novulon_stbl.build_stbl(strings)
        self.assertEqual(novulon_stbl.read_stbl(data), strings)

    def test_header_byte_layout_matches_the_verified_mc_cmd_center_sample(self):
        """build_plan.md §2b: header 'STBL' + version(u16,=5) + compressed(u8,=0) + numEntries(u64) +
        reserved(u16) + stringLen(u32) = 21 bytes total before the first entry."""
        data = novulon_stbl.build_stbl({1: 'x'})
        self.assertEqual(data[:4], b'STBL')
        self.assertEqual(data[4:6], (5).to_bytes(2, 'little'))     # version 5
        self.assertEqual(data[6], 0)                               # not compressed
        self.assertEqual(int.from_bytes(data[7:15], 'little'), 1)  # numEntries
        self.assertEqual(len(data), 21 + 7 + 1)                    # header + one entry (key+flags+len+"x")

    def test_cross_checked_against_this_repos_own_trusted_reader(self):
        """Validates the new writer against a reader this repo already relies on for a live feature
        (wicked_animator/backend/doctor.py:_stbl(), engineering.md §13.1) - test-only cross-app import,
        never shipped as part of the mod itself."""
        strings = {0x1: 'Alpha', 0x2: 'Bravo Charlie', 0x3: 'unicode é☃'}
        data = novulon_stbl.build_stbl(strings)
        self.assertEqual(wa_doctor._stbl(data), strings)
        self.assertEqual(wa_posepack.read_stbl(data), strings)

    def test_empty_table(self):
        data = novulon_stbl.build_stbl({})
        self.assertEqual(novulon_stbl.read_stbl(data), {})
        self.assertEqual(int.from_bytes(data[7:15], 'little'), 0)

    def test_read_stbl_rejects_bad_magic(self):
        with self.assertRaises(ValueError):
            novulon_stbl.read_stbl(b'NOPE' + b'\x00' * 20)

    def test_key_is_masked_to_32_bits(self):
        data = novulon_stbl.build_stbl({0x1_0000_0001: 'x'})
        self.assertEqual(novulon_stbl.read_stbl(data), {0x00000001: 'x'})

    def test_string_too_long_for_u16_length_raises(self):
        with self.assertRaises(ValueError):
            novulon_stbl.build_stbl({1: 'x' * 70000})


if __name__ == '__main__':
    unittest.main(verbosity=2)
