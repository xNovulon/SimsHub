import sys
p = sys.argv[1]
data = open(p, 'rb').read()
fixed = data.replace(b"b'\x00'", b"b'\\x00'")
open(p, 'wb').write(fixed)
print(p, 'NUL bytes:', data.count(b'\x00'), '->', fixed.count(b'\x00'))
