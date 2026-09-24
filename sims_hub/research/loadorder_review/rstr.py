import sys, pefile
EXE = r'E:\The Sims 4\Game\Bin\TS4_x64.exe'
pe = pefile.PE(EXE, fast_load=True); data = open(EXE,'rb').read()
for a in sys.argv[1:]:
    rva = int(a,16); off = pe.get_offset_from_rva(rva)
    raw = data[off:off+64]
    try: w = raw.decode('utf-16le', 'replace').split('\0')[0]
    except Exception: w = ''
    print(f'rva 0x{rva:x} off 0x{off:x}: utf16={w!r} bytes={raw[:24].hex()}')
