"""Unmerge: split a merged package back into the files that went into it.

A merge made by Sims 4 Studio - or by a tool that writes the same merge list (Sims 4 Mod Manager reads it, and the
Hub's own merger writes it) - starts with a resource of type 0x7FB6AD8A that names every source file and the
resources that came from it (speedkit.manifest). unmerge() writes each source back as its own .package, in a folder
next to the merged file named "<merged name> (unmerged)", with the folders the merge list has. Every resource is
copied exactly as stored. Nothing is dropped: resources the list names under no source go to one extra file
("Not in the merge list.package"), and a resource listed under several sources is written to each (as Sims 4 Studio
does). Every new file is read back and compared with the merged file byte for byte before the merged file is moved
to the quarantine, all through a Journal, so the whole unmerge can be undone. A merge without a merge list can't be
split back into its original files (their names and boundaries are not stored anywhere): info() says so.

    info(path)                                  # read-only: {'merged', 'sources': [...], 'resources', 'unlisted', ...}
    unmerge(path, sims=..., journal_home=...)   # real run; refuses while the game runs (unless check_game=False)
"""
import os

from . import manifest
from .dbpf import Package, PackageWriter, DELETED
from .journal import Journal

MASK = 0xFFFFFFFFFFFFFFFF
EXTRA_NAME = 'Not in the merge list'


class UnmergeError(Exception):
    pass


def _key(t, g, i):
    return (t & 0xFFFFFFFF, g & 0xFFFFFFFF, i & MASK)


def _entries(p):
    """{key: first entry} of a package, the merge list itself left out."""
    out = {}
    for e in p.entries:
        if e.comp == DELETED or e.t == manifest.MANIFEST_TYPE:
            continue
        out.setdefault(_key(e.t, e.g, e.i), e)
    return out


def info(path):
    """What an unmerge of this file would make, read-only:
    {'merged': bool, 'sources': [{'name', 'folder', 'resources'}], 'resources', 'unlisted', 'missing'}.
    merged is False for a file without a merge list (nothing can be split back)."""
    with Package(path) as p:
        root = manifest.read(p)
        ents = _entries(p)
    if root is None:
        return {'merged': False, 'sources': [], 'resources': len(ents), 'unlisted': 0, 'missing': 0}
    listed, sources = set(), []
    for folder, s in root.walk():
        keys = {_key(*k) for k in s.keys}
        listed |= keys
        sources.append({'name': s.name, 'folder': folder, 'resources': len(keys & set(ents))})
    return {'merged': True, 'sources': sources, 'resources': len(ents),
            'unlisted': len(set(ents) - listed), 'missing': len(listed - set(ents))}


def _plan(root, ents, out_dir):
    """[(final path, [keys])] for every file to write, names made safe and unique per folder."""
    taken, files, listed = {}, [], set()
    for folder, s in root.walk():
        parts = [manifest.sanitize_name(x) for x in folder.split('/') if x] if folder else []
        d = os.path.join(out_dir, *parts)
        name = manifest.sanitize_name(s.name, taken.setdefault(os.path.normcase(d), set()))
        keys = [k for k in dict.fromkeys(_key(*k) for k in s.keys) if k in ents]
        listed.update(_key(*k) for k in s.keys)
        if keys:
            files.append((os.path.join(d, name + '.package'), keys))
    extra = [k for k in ents if k not in listed]
    if extra:
        name = manifest.sanitize_name(EXTRA_NAME, taken.setdefault(os.path.normcase(out_dir), set()))
        files.append((os.path.join(out_dir, name + '.package'), extra))
    return files


def unmerge(path, sims, journal_home=None, check_game=True, progress=None):
    """Split a merged file into its sources (see the module doc). Returns {'ok', 'journal', 'folder', 'written',
    'resources'}. Raises UnmergeError when there is no merge list or a check fails (every change is undone then)."""
    path = os.path.abspath(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    out_dir = os.path.join(os.path.dirname(path), manifest.sanitize_name(stem + ' (unmerged)'))
    if os.path.exists(out_dir):
        raise UnmergeError('%s already exists - move it away first' % out_dir)
    with Package(path) as p:
        root = manifest.read(p)
        if root is None:
            raise UnmergeError("this file has no merge list, so it can't be split back into the files that went into it")
        ents = _entries(p)
        files = _plan(root, ents, out_dir)
        kw = {'home': journal_home} if journal_home else {}
        j = Journal('unmerge', 'Unmerged %s into %d files' % (os.path.basename(path), len(files)), sims=sims,
                    check_game=check_game, **kw)
        written, tmp = [], None
        try:
            for n, (final, keys) in enumerate(files):
                if progress:
                    progress('unmerge', n, len(files), os.path.basename(final))
                os.makedirs(os.path.dirname(final), exist_ok=True)
                tmp = final + '.speedkit-unmerge'
                with PackageWriter(tmp) as w:
                    for k in keys:
                        w.add_raw(ents[k], p.raw(ents[k]))
                # read it back: the same resources, byte for byte
                with Package(tmp) as q:
                    got = _entries(q)
                    if set(got) != set(keys):
                        raise UnmergeError('%s came out with %d resources instead of %d' % (final, len(got), len(keys)))
                    for k in keys:
                        if q.raw(got[k]) != p.raw(ents[k]) or got[k].comp != ents[k].comp or got[k].msize != ents[k].msize:
                            raise UnmergeError('a resource in %s differs from the merged file' % final)
                j.put_new(tmp, final)
                tmp = None
                written.append(final)
        except BaseException as e:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
            j.close('failed: %s' % e)
            _roll_back(j, journal_home, check_game)
            if isinstance(e, UnmergeError):
                raise
            raise UnmergeError('%s (nothing was changed)' % e) from e
    # every resource of the merged file is in at least one new file
    covered = set()
    for final, keys in files:
        covered.update(keys)
    if covered != set(ents):
        j.close('failed: resources left out')
        _roll_back(j, journal_home, check_game)
        raise UnmergeError('%d resources would be left out (nothing was changed)' % len(set(ents) - covered))
    j.quarantine(path)
    j.close('committed')
    return {'ok': True, 'journal': j.id, 'folder': out_dir, 'written': written, 'resources': len(ents)}


def _roll_back(j, journal_home, check_game):
    from .journal import undo
    kw = {'home': journal_home} if journal_home else {}
    try:
        undo(j.id, check_game=check_game, **kw)
    except Exception:
        pass
