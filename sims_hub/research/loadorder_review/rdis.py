"""Read-only disassembly helper for review. usage: dis.py <rva_hex> [n] | vt <rva_hex> [slots]"""
import sys, struct, pefile, capstone
EXE = r'E:\The Sims 4\Game\Bin\TS4_x64.exe'
pe = pefile.PE(EXE, fast_load=True)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
data = open(EXE, 'rb').read()
IB = pe.OPTIONAL_HEADER.ImageBase
iat = {}
for e in pe.DIRECTORY_ENTRY_IMPORT:
    for imp in e.imports:
        iat[imp.address - IB] = (e.dll.decode() + '!' + (imp.name.decode() if imp.name else str(imp.ordinal)))
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
def dis(rva, n):
    off = pe.get_offset_from_rva(rva)
    code = data[off:off + n * 15]
    k = 0
    for ins in md.disasm(code, rva):
        extra = ''
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                tgt = ins.address + ins.size + op.mem.disp
                if tgt in iat: extra = '  ; ' + iat[tgt]
                else: extra = f'  ; ->0x{tgt:x}'
        print(f'  0x{ins.address:08x}: {ins.mnemonic:8s} {ins.op_str}{extra}')
        k += 1
        if k >= n: break
if sys.argv[1] == 'vt':
    rva = int(sys.argv[2], 16); slots = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    off = pe.get_offset_from_rva(rva)
    for s in range(slots):
        v = struct.unpack_from('<Q', data, off + 8 * s)[0]
        print(f'slot +0x{8*s:x}: 0x{v - IB:x}')
else:
    dis(int(sys.argv[1], 16), int(sys.argv[2]) if len(sys.argv) > 2 else 60)
