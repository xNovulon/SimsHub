"""One way to open the Hub's SQLite files, so its own work never trips over itself ("database is locked").

    db = dbconn.connect(path)                    # WAL, and a busy wait of 60 s before giving up
    db = dbconn.connect(path, timeout=600)       # for a file a long scan writes (library.sqlite)

WAL (write-ahead log): reading never waits for a write and a write never waits for reads, so a page can read the
library while a scan is writing it (it sees the library as it was before the scan). Two writes still take turns:
the second one waits up to `timeout` seconds instead of failing after SQLite's default 5 s. A file system that
can't do WAL (some network drives) keeps the old journal; the longer wait still applies.

Beside a WAL file SQLite keeps <name>-wal and <name>-shm while it's open. They belong to it: never copy the .sqlite
file alone while it's open (use Connection.backup), and never delete them by hand.
"""
import os
import sqlite3

DEFAULT_TIMEOUT = 60.0


def connect(path, timeout=DEFAULT_TIMEOUT, wal=True, **kw):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    db = sqlite3.connect(path, timeout=timeout, **kw)
    if wal:
        try:
            db.execute('pragma journal_mode=wal')
        except sqlite3.Error:
            pass
    return db
