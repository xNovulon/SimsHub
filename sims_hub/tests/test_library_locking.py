"""The Hub's own work never trips over itself on the library index ("Something went wrong: Database is locked").

A user opened the Saves page while the Hub was scanning a big Mods folder, and the page failed with "Database is
locked": the scan held the library file for minutes, and another connection gave up after SQLite's default 5 s.
The library file now uses WAL (speedkit/dbconn.py), scans take turns, and a scan stays one transaction. These tests
hold real SQLite locks in threads on a temporary folder (the real Sims 4 folder is never touched)."""
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from speedkit import dbconn, library as L  # noqa: E402


def slow_read_entries(delay):
    real = L.read_entries

    def read(f):
        time.sleep(delay)
        return real(f)
    return read


class LibraryLockingTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='sk_lock_')
        self.mods = os.path.join(self.dir, 'Mods')
        os.makedirs(self.mods)
        self.db = os.path.join(self.dir, 'data', 'library.sqlite')
        self.add_files(0, 12)
        self.libs = []

    def tearDown(self):
        for lib in self.libs:
            try:
                lib.close()
            except Exception:
                pass
        shutil.rmtree(self.dir, ignore_errors=True)

    def add_files(self, start, n):
        # not real packages: the scan still lists each one (with its read error), which is all these tests need
        for i in range(start, start + n):
            with open(os.path.join(self.mods, 'cc_%03d.package' % i), 'wb') as f:
                f.write(b'x' * (100 + i))

    def library(self):
        lib = L.Library(self.db, roots={'Mods': self.mods})
        self.libs.append(lib)
        return lib

    def count(self):
        with dbconn.connect(self.db) as db:
            return db.execute('select count(*) from pkg').fetchone()[0]

    def scan_in_thread(self, errors):
        # its own connection on its own thread, as each Hub request opens the library
        def run():
            lib = None
            try:
                lib = L.Library(self.db, roots={'Mods': self.mods})
                lib.scan()
            except Exception as e:          # the bug surfaced here as sqlite3.OperationalError
                errors.append(e)
            finally:
                if lib is not None:
                    lib.close()
        t = threading.Thread(target=run)
        t.start()
        return t

    def test_library_file_uses_wal(self):
        lib = self.library()
        self.assertEqual(lib.db.execute('pragma journal_mode').fetchone()[0].lower(), 'wal')

    def test_reading_during_a_scan_does_not_wait_and_sees_the_library_as_it_was(self):
        self.library().scan()
        self.assertEqual(self.count(), 12)
        self.add_files(12, 8)
        errors = []
        with mock.patch.object(L, 'read_entries', slow_read_entries(0.15)):
            t = self.scan_in_thread(errors)
            time.sleep(0.6)                                    # the scan is writing now
            t0 = time.time()
            during = self.count()
            waited = time.time() - t0
            # a fresh Library (the Saves page's own connection) also opens without waiting
            t1 = time.time()
            lib2 = self.library()
            packages = len(lib2.packages())
            opened = time.time() - t1
            t.join(60)
        self.assertEqual(errors, [])
        self.assertLess(waited, 0.5, 'a read waited for the scan')
        self.assertLess(opened, 0.5, 'opening the library waited for the scan')
        self.assertEqual(during, 12, 'a reader saw a half-finished scan')      # all-or-nothing
        self.assertEqual(packages, 12)
        self.assertEqual(self.count(), 20)

    def test_two_scans_at_once_take_turns_instead_of_failing(self):
        # the first scan writes for ~6 s: longer than SQLite's default 5 s wait, which the old code failed on
        errors = []
        with mock.patch.object(L, 'read_entries', slow_read_entries(0.5)):
            a = self.scan_in_thread(errors)
            time.sleep(0.2)
            b = self.scan_in_thread(errors)
            a.join(60)
            b.join(60)
        self.assertEqual(errors, [])
        self.assertEqual(self.count(), 12)

    def test_a_write_from_another_connection_waits_for_the_scan(self):
        # e.g. another tool writing the same file: it waits for the scan's commit instead of failing after 5 s
        self.library().scan()
        self.add_files(12, 10)
        errors = []
        with mock.patch.object(L, 'read_entries', slow_read_entries(0.6)):
            t = self.scan_in_thread(errors)
            time.sleep(0.8)
            other = dbconn.connect(self.db)
            t0 = time.time()
            other.execute("insert or replace into other values('Mods', 'note.txt', 1, '.txt')")
            other.commit()
            waited = time.time() - t0
            other.close()
            t.join(60)
        self.assertEqual(errors, [])
        self.assertGreater(waited, 1.0, 'the write did not wait for the scan (the test did not hold a lock)')

    def test_everyday_use_waits_60_s_and_only_a_scan_waits_longer(self):
        lib = self.library()
        self.assertEqual(lib.db.execute('pragma busy_timeout').fetchone()[0], int(dbconn.DEFAULT_TIMEOUT * 1000))
        seen = []
        real = L.Library._scan

        def spy(this, verbose=False):
            seen.append(this.db.execute('pragma busy_timeout').fetchone()[0])
            return real(this, verbose)
        with mock.patch.object(L.Library, '_scan', spy):
            lib.scan()
        self.assertEqual(seen, [L.SCAN_WAIT * 1000])
        self.assertEqual(lib.db.execute('pragma busy_timeout').fetchone()[0], int(dbconn.DEFAULT_TIMEOUT * 1000))

    def test_a_scan_waiting_too_long_for_another_says_so(self):
        L._SCAN_LOCK.acquire()                                # another scan that never ends
        try:
            with mock.patch.object(L, 'SCAN_WAIT', 0.2):
                with self.assertRaises(L.StillScanning) as cm:
                    self.library().scan()
            self.assertIn('still being read', str(cm.exception))
        finally:
            L._SCAN_LOCK.release()

    def test_the_hub_says_it_plainly(self):
        from speedkit import api

        @api._safe
        def scanning():
            raise L.StillScanning('Your mods are still being read. Try again in a few minutes.')

        @api._safe
        def locked():
            raise sqlite3.OperationalError('database is locked')
        with mock.patch.object(api, '_log_error', lambda *a: None):
            self.assertEqual(scanning(), {'ok': False, 'message': 'Your mods are still being read. Try again in a few minutes.'})
            self.assertEqual(locked()['message'], 'Another program is using your CC list right now. Try again in a moment.')

    def test_control_a_short_wait_still_reports_the_lock(self):
        # proves the tests above really hold SQLite locks: with a tiny wait the old error comes back
        lib = self.library()
        lib.db.execute('delete from script')                  # an open write transaction
        quick = dbconn.connect(self.db, timeout=0.1)
        try:
            with self.assertRaises(sqlite3.OperationalError) as cm:
                quick.execute("insert into other values('Mods', 'x.txt', 1, '.txt')")
            self.assertIn('locked', str(cm.exception))
        finally:
            quick.close()
            lib.db.rollback()


if __name__ == '__main__':
    unittest.main()
