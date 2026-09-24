"""Pull the game's own protobuf schemas (serialized FileDescriptorProtos inside the 3.7 .pyc
files of Game/Bin/Python/generated.zip) and build real message classes with google.protobuf.
Read-only on the game folder."""
import os, sys, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools'))
import pyc37
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

GEN = r'E:\The Sims 4\Game\Bin\Python\generated.zip'


def _walk(o):
    yield o
    if isinstance(o, pyc37.Code):
        for c in o.co_consts:
            yield from _walk(c)
    elif isinstance(o, (tuple, list)):
        for c in o:
            yield from _walk(c)


def file_protos(zpath=GEN):
    out = {}
    zf = zipfile.ZipFile(zpath)
    for n in zf.namelist():
        if not n.endswith('_pb2.pyc'):
            continue
        code = pyc37.load(zf.read(n))
        for c in _walk(code):
            if isinstance(c, str):  # 3.7 generated code: serialized_pb=_b('...') (latin-1 str)
                try:
                    c = c.encode('latin1')
                except UnicodeEncodeError:
                    continue
            if isinstance(c, bytes) and len(c) > 20 and c[:1] == b'\n':
                fd = descriptor_pb2.FileDescriptorProto()
                try:
                    fd.ParseFromString(c)
                except Exception:
                    continue
                if fd.name.endswith('.proto'):
                    out[fd.name] = fd
    return out


_POOL = None


def pool():
    global _POOL
    if _POOL is None:
        fds = file_protos()
        p = descriptor_pool.DescriptorPool()
        dfd = descriptor_pb2.FileDescriptorProto()
        descriptor_pb2.DESCRIPTOR.CopyToProto(dfd)
        p.Add(dfd)
        added = {dfd.name}

        def add(name):
            if name in added:
                return
            fd = fds.get(name)
            if fd is None:
                return
            for d in fd.dependency:
                add(d)
            p.Add(fd)
            added.add(name)
        for n in fds:
            add(n)
        _POOL = p
    return _POOL


def msg(full_name):
    return message_factory.GetMessageClass(pool().FindMessageTypeByName(full_name))


if __name__ == '__main__':
    fds = file_protos()
    for n, fd in sorted(fds.items()):
        print(n, fd.package, [m.name for m in fd.message_type][:15], len(fd.message_type))
