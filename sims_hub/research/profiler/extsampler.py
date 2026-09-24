r"""extsampler.py <pid|process-name> [--seconds S] [--hz H] [--map mapfile.json]
External (out-of-process) sampling profiler for the game's embedded CPython 3.7.0 (python37_x64.dll).
Reads the target's memory with ReadProcessMemory - no code runs inside the game, the GIL is never touched.
  _PyRuntime (exported) +24 -> interpreters.head ; interp +8 -> tstate_head ; tstate: +8 next, +16 interp, +24 frame
  PyFrameObject: +24 f_back, +32 f_code, +104 f_lasti ; PyCodeObject: +36 co_firstlineno, +96 co_filename, +104 co_name
The main (simulation) thread is the OLDEST thread state = tail of the tstate list.
frame == NULL on the main thread means: no Python on the stack right now (C++ time).
Offsets are CPython 3.7 x64 release-build layouts; the tool validates them (sane strings, interp back-pointer)."""
import ctypes, ctypes.wintypes as W, struct, sys, os, time, json, argparse, collections, re, random

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)
PROCESS_VM_READ, PROCESS_QUERY_INFORMATION = 0x10, 0x400
k32.OpenProcess.restype = W.HANDLE
k32.ReadProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]


def find_pid(name):
    arr = (W.DWORD * 4096)(); cb = W.DWORD()
    psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(cb))
    for pid in arr[:cb.value // 4]:
        h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not h:
            continue
        buf = ctypes.create_unicode_buffer(1024)
        psapi.GetModuleBaseNameW(h, None, buf, 1024)
        k32.CloseHandle(h)
        if buf.value.lower() == name.lower():
            return pid
    return None


def export_rva(dll_path, name):
    d = open(dll_path, 'rb').read()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    nsec = struct.unpack_from('<H', d, pe + 6)[0]; optsz = struct.unpack_from('<H', d, pe + 20)[0]
    opt = pe + 24; exp_rva = struct.unpack_from('<I', d, opt + 112)[0]
    secs = [struct.unpack_from('<8sIIII', d, opt + optsz + 40 * i) for i in range(nsec)]
    def off(rva):
        for _, vsz, va, rsz, rp in secs:
            if va <= rva < va + max(vsz, rsz):
                return rva - va + rp
    e = off(exp_rva)
    n, afn, anames, aord = struct.unpack_from('<IIII', d, e + 24)
    for i in range(n):
        no = off(struct.unpack_from('<I', d, off(anames) + 4 * i)[0])
        if d[no:d.index(b'\0', no)].decode() == name:
            ordi = struct.unpack_from('<H', d, off(aord) + 2 * i)[0]
            return struct.unpack_from('<I', d, off(afn) + 4 * ordi)[0]


class Target:
    def __init__(self, pid):
        self.h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not self.h:
            raise OSError('OpenProcess failed: %d' % ctypes.get_last_error())
        mods = (W.HMODULE * 2048)(); cb = W.DWORD()
        psapi.EnumProcessModulesEx(self.h, mods, ctypes.sizeof(mods), ctypes.byref(cb), 3)
        self.pydll = None
        for m in mods[:cb.value // ctypes.sizeof(W.HMODULE)]:
            buf = ctypes.create_unicode_buffer(1024)
            psapi.GetModuleFileNameExW(self.h, ctypes.c_void_p(m), buf, 1024)
            if re.search(r'python3\d+(_x64)?\.dll$', buf.value, re.I):
                self.pydll, self.base = buf.value, m
        if not self.pydll:
            raise RuntimeError('no python3x DLL in target')
        self.runtime = self.base + export_rva(self.pydll, '_PyRuntime')
        self.buf = ctypes.create_string_buffer(4096); self.n = ctypes.c_size_t()
        self.str_cache = {}; self.code_cache = {}

    def read(self, addr, size):
        if not addr or not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), self.buf, size, ctypes.byref(self.n)):
            return None
        return self.buf.raw[:size]

    def ptr(self, addr):
        b = self.read(addr, 8)
        return struct.unpack('<Q', b)[0] if b else 0

    def pystr(self, addr):
        s = self.str_cache.get(addr)
        if s is not None:
            return s
        hdr = self.read(addr, 48)
        if not hdr:
            return '?'
        length, state = struct.unpack_from('<q', hdr, 16)[0], struct.unpack_from('<I', hdr, 32)[0]
        kind, compact, ascii_ = (state >> 2) & 7, (state >> 5) & 1, (state >> 6) & 1
        if not compact or length < 0 or length > 1000 or kind not in (1, 2, 4):
            return '?'
        data = addr + (48 if ascii_ else 72)
        raw = self.read(data, length * kind) or b''
        s = raw.decode({1: 'latin-1', 2: 'utf-16-le', 4: 'utf-32-le'}[kind], 'replace')
        if len(self.str_cache) < 200000:
            self.str_cache[addr] = s
        return s

    def code(self, addr):
        c = self.code_cache.get(addr)
        if c is None:
            b = self.read(addr, 112)
            if not b:
                return ('?', '?', 0)
            c = (self.pystr(struct.unpack_from('<Q', b, 96)[0]), self.pystr(struct.unpack_from('<Q', b, 104)[0]),
                 struct.unpack_from('<i', b, 36)[0])
            self.code_cache[addr] = c
        return c

    def threads(self):
        interp = self.ptr(self.runtime + 24)
        ts = self.ptr(interp + 8); out = []
        while ts and len(out) < 256:
            b = self.read(ts, 32)
            if not b:
                break
            nxt, back_interp, frame = struct.unpack_from('<QQQ', b, 8)
            if back_interp != interp:
                raise RuntimeError('tstate->interp mismatch: offsets wrong for this build')
            out.append((ts, frame)); ts = nxt
        return out

    def stack(self, frame, maxdepth=200):
        out = []
        while frame and len(out) < maxdepth:
            b = self.read(frame, 112)
            if not b:
                break
            back, code = struct.unpack_from('<QQ', b, 24)
            out.append(self.code(code) + (struct.unpack_from('<i', b, 104)[0],))
            frame = back
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('target'); ap.add_argument('--seconds', type=float, default=10); ap.add_argument('--hz', type=float, default=250)
    ap.add_argument('--map', help='json {co_filename: owner.ts4script}'); ap.add_argument('--top', type=int, default=12)
    a = ap.parse_args()
    pid = int(a.target) if a.target.isdigit() else find_pid(a.target)
    t = Target(pid)
    fmap = json.load(open(a.map)) if a.map else {}
    game_prefixes = tuple(fmap.get('game_prefixes', ()))       # owner_map.json from build_owner_map.py
    byfile = fmap.get('by_file', fmap)                          # or a flat {co_filename: owner} map
    def owner(fn):
        if game_prefixes and fn.startswith(game_prefixes):
            return 'game'
        o = byfile.get(fn)
        if o: return o
        i = fn.lower().find('.ts4script')                       # .py compiled from inside a ts4script
        if i >= 0: return os.path.basename(fn[:i + 10])
        return ('unknown:' + fn[-60:]) if game_prefixes else 'game'
    print('pid', pid, t.pydll, 'base 0x%x _PyRuntime 0x%x threads %d' % (t.base, t.runtime, len(t.threads())))
    selfc = collections.Counter(); inclc = collections.Counter(); funcs = collections.Counter(); n = 0; cpp = 0; errs = 0
    period = 1.0 / a.hz; end = time.perf_counter() + a.seconds; nxt = time.perf_counter(); cost = []
    while time.perf_counter() < end:
        t0 = time.perf_counter()
        try:
            th = t.threads()
        except Exception:
            errs += 1
            continue
        main_frame = th[-1][1] if th else 0
        n += 1
        if not main_frame:
            cpp += 1
        else:
            st = t.stack(main_frame)
            if st:
                owners = [owner(f[0]) for f in st]
                selfc[owners[0]] += 1; funcs[(owners[0], st[0][1], st[0][2])] += 1
                for o in set(owners):
                    inclc[o] += 1
        cost.append(time.perf_counter() - t0)
        nxt += random.expovariate(a.hz)   # Poisson sampling: no phase-locking with the game's frame/tick rhythm
        d = nxt - time.perf_counter()
        if d > 0:
            time.sleep(d)
    py = n - cpp
    print('read errors (skipped samples): %d' % errs)
    print('samples %d  (main thread outside Python/C++: %.1f%%, in Python: %.1f%%)' % (n, 100 * cpp / n, 100 * py / n))
    for o, c in selfc.most_common(a.top):
        print('   self %-34s %6d  %5.1f%% of python  incl %5.1f%%' % (o, c, 100 * c / max(py, 1), 100 * inclc[o] / max(py, 1)))
    for k, c in funcs.most_common(a.top):
        print('   func %-70s %6d' % (k, c))
    cost.sort()
    print('reader cost per sample: p50 %.0f us, p90 %.0f us (runs in THIS process, not in the game)' % (1e6 * cost[len(cost) // 2], 1e6 * cost[int(.9 * len(cost))]))


if __name__ == '__main__':
    main()
