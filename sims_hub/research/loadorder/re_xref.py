"""Static, read-only reverse-engineering helpers for TS4_x64.exe.
- imports: list imported functions of interest with their IAT RVAs
- xref <fileoff_hex>...: find RIP-relative references (lea/mov/call/jmp [rip+x]) to a file offset / RVA
- callers <import-name>: find `call [rip+IAT]` sites of an import
- dis <rva_hex> [n]: disassemble n instructions at RVA
"""
import sys, struct
import numpy as np
import pefile
import capstone

EXE = r'E:\The Sims 4\Game\Bin\TS4_x64.exe'
pe = pefile.PE(EXE, fast_load=True)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
data = open(EXE, 'rb').read()
IB = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
T_RVA, T_OFF, T_SZ = text.VirtualAddress, text.PointerToRawData, text.SizeOfRawData
tb = np.frombuffer(data, dtype=np.uint8, count=T_SZ, offset=T_OFF)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = False


def off2rva(off):
    return pe.get_rva_from_offset(off)


def rva2off(rva):
    return pe.get_offset_from_rva(rva)


def imports():
    out = {}
    for e in pe.DIRECTORY_ENTRY_IMPORT:
        for imp in e.imports:
            if imp.name:
                out[imp.name.decode()] = imp.address - IB
    return out


def rip_refs(target_rva):
    """All positions in .text where a disp32 at pos p satisfies next_ip + disp == target, for common encodings.
    We brute force: for every offset i, treat bytes[i:i+4] as disp32 and assume instruction ends at i+4+k (k=0..1)."""
    n = T_SZ - 8
    disp = np.frombuffer(data, dtype='<i4', count=n // 1, offset=T_OFF) if False else None
    # build disp32 at every byte offset using 4 shifted views
    b = tb.astype(np.int64)
    d = b[0:n] | (b[1:n + 1] << 8) | (b[2:n + 2] << 16) | (b[3:n + 3] << 24)
    d = np.where(d >= 2 ** 31, d - 2 ** 32, d)
    idx = np.arange(n, dtype=np.int64)
    hits = []
    for k in (0, 1, 4):  # imm8 / imm32 trailing
        ip_after = T_RVA + idx + 4 + k
        m = np.nonzero(ip_after + d == target_rva)[0]
        for i in m:
            hits.append((int(i), k))
    return hits


def insn_containing(disp_pos):
    """Try to decode an instruction that places disp32 at disp_pos (text-relative)."""
    res = []
    for back in range(1, 8):
        start = disp_pos - back
        if start < 0:
            continue
        code = bytes(tb[start:start + 16])
        for ins in md.disasm(code, T_RVA + start, count=1):
            if ins.size >= back + 4 and 'rip' in ins.op_str:
                res.append(ins)
    return res


def dis(rva, n=40):
    off = rva2off(rva)
    code = data[off:off + n * 15]
    for i, ins in enumerate(md.disasm(code, rva)):
        if i >= n:
            break
        print(f"  {ins.address:#010x}: {ins.mnemonic:8s} {ins.op_str}")


def xref(rva):
    seen = set()
    for pos, k in rip_refs(rva):
        for ins in insn_containing(pos):
            if ins.address in seen:
                continue
            seen.add(ins.address)
            print(f"{ins.address:#010x}: {ins.mnemonic} {ins.op_str}")


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'imports':
        imp = imports()
        import re
        pat = re.compile(sys.argv[2] if len(sys.argv) > 2 else '.', re.I)
        for k, v in sorted(imp.items()):
            if pat.search(k):
                print(f"{v:#010x} {k}")
    elif cmd == 'xref':
        for a in sys.argv[2:]:
            v = int(a, 16)
            rva = off2rva(v) if a.startswith('f') is False and len(sys.argv) and v > 0x1000000 and False else v
            print('== target', a)
            xref(rva)
    elif cmd == 'xoff':
        for a in sys.argv[2:]:
            rva = off2rva(int(a, 16))
            print(f'== file off {a} -> rva {rva:#x}')
            xref(rva)
    elif cmd == 'callers':
        imp = imports()
        for name in sys.argv[2:]:
            print('== callers of', name)
            xref(imp[name])
    elif cmd == 'dis':
        dis(int(sys.argv[2], 16), int(sys.argv[3]) if len(sys.argv) > 3 else 40)


def func_start(rva, maxback=0x4000):
    off = rva2off(rva)
    i = off
    while i > off - maxback:
        if data[i - 1] == 0xCC and data[i - 2] == 0xCC:
            return pe.get_rva_from_offset(i)
        i -= 1
    return None


def dis_func(rva, maxn=3000):
    start = func_start(rva)
    off = rva2off(start)
    code = data[off:off + maxn * 15]
    out = []
    for i, ins in enumerate(md.disasm(code, start)):
        if i >= maxn:
            break
        out.append(f"  {ins.address:#010x}: {ins.mnemonic:8s} {ins.op_str}")
        if ins.mnemonic == 'int3' and len(out) > 3 and out[-2].split()[1] == 'ret':
            break
    return start, out


if __name__ == '__main__' and sys.argv[1] == 'func':
    s, out = dis_func(int(sys.argv[2], 16), int(sys.argv[3]) if len(sys.argv) > 3 else 3000)
    print(f'; function start {s:#x}')
    print('\n'.join(out))


def call_sites(target_rva):
    """direct `call rel32` / `jmp rel32` sites targeting target_rva"""
    res = []
    for pos, k in rip_refs(target_rva):
        if k != 0 or pos < 1:
            continue
        op = int(tb[pos - 1])
        if op in (0xE8, 0xE9):
            res.append((T_RVA + pos - 1, 'call' if op == 0xE8 else 'jmp'))
    return res


if __name__ == '__main__' and sys.argv[1] == 'calls':
    for a in sys.argv[2:]:
        print('== direct calls to', a)
        for rva, kind in call_sites(int(a, 16)):
            print(f'  {rva:#010x} {kind}  (func {func_start(rva):#x})')
