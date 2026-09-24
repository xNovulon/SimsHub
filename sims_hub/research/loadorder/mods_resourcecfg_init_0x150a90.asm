; function start 0x150a90
  0x00150a90: push     rbp
  0x00150a92: push     rbx
  0x00150a93: push     rsi
  0x00150a94: push     rdi
  0x00150a95: push     r12
  0x00150a97: push     r14
  0x00150a99: push     r15
  0x00150a9b: mov      rbp, rsp
  0x00150a9e: sub      rsp, 0x80
  0x00150aa5: mov      qword ptr [rbp - 0x50], 0xfffffffffffffffe
  0x00150aad: mov      r14, rcx
  0x00150ab0: xor      r15d, r15d
  0x00150ab3: mov      dword ptr [rbp + 0x58], r15d
  0x00150ab7: xor      edx, edx
  0x00150ab9: lea      rcx, [rbp + 0x48]
  0x00150abd: call     0x6a630
  0x00150ac2: nop      
  0x00150ac3: mov      rdx, rax
  0x00150ac6: lea      rcx, [rbp - 0x30]
  0x00150aca: call     0x6a630
  0x00150acf: xor      eax, eax
  0x00150ad1: mov      qword ptr [rbp - 0x30], rax
  0x00150ad5: mov      qword ptr [rbp - 0x28], rax
  0x00150ad9: mov      byte ptr [rbp - 0x21], 7
  0x00150add: lea      rdx, [rip + 0x1c9f1ac]
  0x00150ae4: lea      rcx, [rbp + 0x50]
  0x00150ae8: call     0x6a630
  0x00150aed: mov      rbx, rax
  0x00150af0: call     0x1630ca0
  0x00150af5: mov      rdx, qword ptr [rax]
  0x00150af8: mov      rcx, rax
  0x00150afb: call     qword ptr [rdx + 0x20]
  0x00150afe: mov      rdi, rax
  0x00150b01: mov      rdx, rbx
  0x00150b04: lea      rcx, [rbp - 0x10]
  0x00150b08: call     0x6a630
  0x00150b0d: xor      eax, eax
  0x00150b0f: mov      qword ptr [rbp - 0x10], rax
  0x00150b13: mov      qword ptr [rbp - 8], rax
  0x00150b17: mov      byte ptr [rbp - 1], 7
  0x00150b1b: mov      rcx, rdi
  0x00150b1e: cmp      word ptr [rdi], ax
  0x00150b21: je       0x150b2c
  0x00150b23: add      rcx, 2
  0x00150b27: cmp      word ptr [rcx], ax
  0x00150b2a: jne      0x150b23
  0x00150b2c: sub      rcx, rdi
  0x00150b2f: sar      rcx, 1
  0x00150b32: lea      r8, [rdi + rcx*2]
  0x00150b36: mov      rdx, rdi
  0x00150b39: lea      rcx, [rbp - 0x10]
  0x00150b3d: call     0x69a20
  0x00150b42: nop      
  0x00150b43: lea      r12, [rip + 0x1cc881e]
  0x00150b4a: mov      rbx, r12
  0x00150b4d: nop      dword ptr [rax]
  0x00150b50: add      rbx, 2
  0x00150b54: cmp      word ptr [rbx], 0
  0x00150b58: jne      0x150b50
  0x00150b5a: sub      rbx, r12
  0x00150b5d: sar      rbx, 1
  0x00150b60: movsx    ecx, byte ptr [rbp - 1]
  0x00150b64: mov      eax, ecx
  0x00150b66: shr      eax, 7
  0x00150b69: mov      esi, 7
  0x00150b6e: and      al, 1
  0x00150b70: je       0x150b77
  0x00150b72: mov      eax, dword ptr [rbp - 8]
  0x00150b75: jmp      0x150b7b
  0x00150b77: mov      eax, esi
  0x00150b79: sub      eax, ecx
  0x00150b7b: lea      edi, [rax + rbx]
  0x00150b7e: lea      rdx, [rbp - 0x10]
  0x00150b82: lea      rcx, [rbp - 0x40]
  0x00150b86: call     0x6a630
  0x00150b8b: xor      eax, eax
  0x00150b8d: mov      qword ptr [rbp - 0x40], rax
  0x00150b91: mov      qword ptr [rbp - 0x38], rax
  0x00150b95: mov      byte ptr [rbp - 0x31], sil
  0x00150b99: cmp      edi, esi
  0x00150b9b: jbe      0x150bc8
  0x00150b9d: lea      edx, [rdi + 1]
  0x00150ba0: add      rdx, rdx
  0x00150ba3: xor      r8d, r8d
  0x00150ba6: lea      rcx, [rbp - 0x40]
  0x00150baa: call     0x6aaf0
  0x00150baf: mov      rcx, rax
  0x00150bb2: mov      qword ptr [rbp - 0x40], rax
  0x00150bb6: bts      edi, 0x1f
  0x00150bba: mov      dword ptr [rbp - 0x34], edi
  0x00150bbd: mov      edx, r15d
  0x00150bc0: mov      dword ptr [rbp - 0x38], edx
  0x00150bc3: shr      edi, 0x18
  0x00150bc6: jmp      0x150bdd
  0x00150bc8: xor      ecx, ecx
  0x00150bca: mov      qword ptr [rbp - 0x40], rcx
  0x00150bce: mov      qword ptr [rbp - 0x38], rcx
  0x00150bd2: mov      byte ptr [rbp - 0x31], sil
  0x00150bd6: movzx    edi, sil
  0x00150bda: mov      edx, dword ptr [rbp - 0x38]
  0x00150bdd: movsx    r8d, dil
  0x00150be1: mov      eax, r8d
  0x00150be4: shr      eax, 7
  0x00150be7: and      al, 1
  0x00150be9: je       0x150bf3
  0x00150beb: mov      eax, edx
  0x00150bed: lea      rdx, [rcx + rax*2]
  0x00150bf1: jmp      0x150c00
  0x00150bf3: mov      eax, esi
  0x00150bf5: sub      eax, r8d
  0x00150bf8: lea      rdx, [rbp - 0x40]
  0x00150bfc: lea      rdx, [rdx + rax*2]
  0x00150c00: mov      word ptr [rdx], r15w
  0x00150c04: mov      dword ptr [rbp + 0x58], 1
  0x00150c0b: movsx    edx, byte ptr [rbp - 1]
  0x00150c0f: mov      ecx, edx
  0x00150c11: shr      ecx, 7
  0x00150c14: and      cl, 1
  0x00150c17: mov      r9, qword ptr [rbp - 0x10]
  0x00150c1b: je       0x150c26
  0x00150c1d: mov      eax, dword ptr [rbp - 8]
  0x00150c20: lea      r8, [r9 + rax*2]
  0x00150c24: jmp      0x150c32
  0x00150c26: mov      eax, esi
  0x00150c28: sub      eax, edx
  0x00150c2a: lea      r8, [rbp - 0x10]
  0x00150c2e: lea      r8, [r8 + rax*2]
  0x00150c32: lea      rdx, [rbp - 0x10]
  0x00150c36: test     cl, cl
  0x00150c38: cmovne   rdx, r9
  0x00150c3c: lea      rcx, [rbp - 0x40]
  0x00150c40: call     0x7dce0
  0x00150c45: mov      eax, ebx
  0x00150c47: lea      r8, [r12 + rax*2]
  0x00150c4b: mov      rdx, r12
  0x00150c4e: lea      rcx, [rbp - 0x40]
  0x00150c52: call     0x7dce0
  0x00150c57: lea      rdx, [rbp - 0x40]
  0x00150c5b: lea      rcx, [rbp - 0x30]
  0x00150c5f: call     0x6a760
  0x00150c64: test     al, al
  0x00150c66: je       0x150c7c
  0x00150c68: movaps   xmm1, xmmword ptr [rbp - 0x30]
  0x00150c6c: movaps   xmm0, xmmword ptr [rbp - 0x40]
  0x00150c70: movdqa   xmmword ptr [rbp - 0x30], xmm0
  0x00150c75: movdqa   xmmword ptr [rbp - 0x40], xmm1
  0x00150c7a: jmp      0x150cb7
  0x00150c7c: movsx    edx, byte ptr [rbp - 0x31]
  0x00150c80: mov      ecx, edx
  0x00150c82: shr      ecx, 7
  0x00150c85: and      cl, 1
  0x00150c88: mov      r9, qword ptr [rbp - 0x40]
  0x00150c8c: je       0x150c97
  0x00150c8e: mov      eax, dword ptr [rbp - 0x38]
  0x00150c91: lea      r8, [r9 + rax*2]
  0x00150c95: jmp      0x150ca3
  0x00150c97: mov      eax, esi
  0x00150c99: sub      eax, edx
  0x00150c9b: lea      r8, [rbp - 0x40]
  0x00150c9f: lea      r8, [r8 + rax*2]
  0x00150ca3: lea      rdx, [rbp - 0x40]
  0x00150ca7: test     cl, cl
  0x00150ca9: cmovne   rdx, r9
  0x00150cad: lea      rcx, [rbp - 0x30]
  0x00150cb1: call     0x7dfe0
  0x00150cb6: nop      
  0x00150cb7: movsx    eax, byte ptr [rbp - 0x31]
  0x00150cbb: shr      eax, 7
  0x00150cbe: and      al, 1
  0x00150cc0: je       0x150ce4
  0x00150cc2: mov      eax, dword ptr [rbp - 0x34]
  0x00150cc5: btr      eax, 0x1f
  0x00150cc9: inc      eax
  0x00150ccb: mov      rdx, qword ptr [rbp - 0x40]
  0x00150ccf: test     rdx, rdx
  0x00150cd2: je       0x150ce4
  0x00150cd4: mov      r8d, eax
  0x00150cd7: add      r8, r8
  0x00150cda: lea      rcx, [rbp - 0x40]
  0x00150cde: call     0x6ab30
  0x00150ce3: nop      
  0x00150ce4: movsx    eax, byte ptr [rbp - 0x21]
  0x00150ce8: shr      eax, 7
  0x00150ceb: and      al, 1
  0x00150ced: lea      rcx, [rbp - 0x30]
  0x00150cf1: cmovne   rcx, qword ptr [rbp - 0x30]
  0x00150cf6: call     0x13ed030
  0x00150cfb: test     al, al
  0x00150cfd: jne      0x150d06
  0x00150cff: xor      bl, bl
  0x00150d01: jmp      0x150ff6
  0x00150d06: lea      rdx, [rbp - 0x30]
  0x00150d0a: lea      rcx, [rbp - 0x20]
  0x00150d0e: call     0x6a630
  0x00150d13: xor      eax, eax
  0x00150d15: mov      qword ptr [rbp - 0x20], rax
  0x00150d19: mov      qword ptr [rbp - 0x18], rax
  0x00150d1d: mov      byte ptr [rbp - 0x11], 7
  0x00150d21: movsx    edx, byte ptr [rbp - 0x21]
  0x00150d25: mov      ecx, edx
  0x00150d27: shr      ecx, 7
  0x00150d2a: and      cl, 1
  0x00150d2d: mov      r9, qword ptr [rbp - 0x30]
  0x00150d31: je       0x150d3c
  0x00150d33: mov      eax, dword ptr [rbp - 0x28]
  0x00150d36: lea      r8, [r9 + rax*2]
  0x00150d3a: jmp      0x150d48
  0x00150d3c: mov      eax, esi
  0x00150d3e: sub      eax, edx
  0x00150d40: lea      r8, [rbp - 0x30]
  0x00150d44: lea      r8, [r8 + rax*2]
  0x00150d48: lea      rdx, [rbp - 0x30]
  0x00150d4c: test     cl, cl
  0x00150d4e: cmovne   rdx, r9
  0x00150d52: lea      rcx, [rbp - 0x20]
  0x00150d56: call     0x69a20
  0x00150d5b: nop      
  0x00150d5c: lea      rdx, [rip + 0x1ca74f5]
  0x00150d63: mov      rax, rdx
  0x00150d66: add      rax, 2
  0x00150d6a: cmp      word ptr [rax], 0
  0x00150d6e: jne      0x150d66
  0x00150d70: sub      rax, rdx
  0x00150d73: sar      rax, 1
  0x00150d76: lea      r8, [rdx + rax*2]
  0x00150d7a: lea      rcx, [rbp - 0x20]
  0x00150d7e: call     0x7dce0
  0x00150d83: movsx    eax, byte ptr [rbp - 0x11]
  0x00150d87: shr      eax, 7
  0x00150d8a: and      al, 1
  0x00150d8c: lea      rcx, [rbp - 0x20]
  0x00150d90: cmovne   rcx, qword ptr [rbp - 0x20]
  0x00150d95: call     0x13ed2f0
  0x00150d9a: test     al, al
  0x00150d9c: jne      0x150f89
  0x00150da2: lea      rdx, [rbp - 0x20]
  0x00150da6: lea      rcx, [rbp - 0x40]
  0x00150daa: call     0x6a630
  0x00150daf: xor      eax, eax
  0x00150db1: mov      qword ptr [rbp - 0x40], rax
  0x00150db5: mov      qword ptr [rbp - 0x38], rax
  0x00150db9: mov      byte ptr [rbp - 0x31], 7
  0x00150dbd: movsx    eax, byte ptr [rbp - 0x11]
  0x00150dc1: mov      ecx, eax
  0x00150dc3: shr      ecx, 7
  0x00150dc6: and      cl, 1
  0x00150dc9: mov      r9, qword ptr [rbp - 0x20]
  0x00150dcd: je       0x150dd8
  0x00150dcf: mov      eax, dword ptr [rbp - 0x18]
  0x00150dd2: lea      r8, [r9 + rax*2]
  0x00150dd6: jmp      0x150de2
  0x00150dd8: sub      esi, eax
  0x00150dda: lea      r8, [rbp - 0x20]
  0x00150dde: lea      r8, [r8 + rsi*2]
  0x00150de2: lea      rdx, [rbp - 0x20]
  0x00150de6: test     cl, cl
  0x00150de8: cmovne   rdx, r9
  0x00150dec: lea      rcx, [rbp - 0x40]
  0x00150df0: call     0x69a20
  0x00150df5: nop      
  0x00150df6: mov      dword ptr [rsp + 0x28], r15d
  0x00150dfb: mov      qword ptr [rsp + 0x20], r15
  0x00150e00: xor      r9d, r9d
  0x00150e03: xor      r8d, r8d
  0x00150e06: xor      edx, edx
  0x00150e08: mov      ecx, 0x250
  0x00150e0d: call     0x6a690
  0x00150e12: mov      qword ptr [rbp + 0x50], rax
  0x00150e16: test     rax, rax
  0x00150e19: je       0x150e3b
  0x00150e1b: movsx    ecx, byte ptr [rbp - 0x31]
  0x00150e1f: shr      ecx, 7
  0x00150e22: and      cl, 1
  0x00150e25: lea      rdx, [rbp - 0x40]
  0x00150e29: cmovne   rdx, qword ptr [rbp - 0x40]
  0x00150e2e: mov      rcx, rax
  0x00150e31: call     0x13ef000
  0x00150e36: mov      rbx, rax
  0x00150e39: jmp      0x150e3e
  0x00150e3b: mov      rbx, r15
  0x00150e3e: mov      qword ptr [rbp + 0x48], rbx
  0x00150e42: test     rbx, rbx
  0x00150e45: je       0x150e51
  0x00150e47: mov      rax, qword ptr [rbx]
  0x00150e4a: mov      rcx, rbx
  0x00150e4d: call     qword ptr [rax + 8]
  0x00150e50: nop      
  0x00150e51: test     rbx, rbx
  0x00150e54: je       0x150f4d
  0x00150e5a: mov      rax, qword ptr [rbx]
  0x00150e5d: mov      dword ptr [rsp + 0x20], r15d
  0x00150e62: mov      edx, 2
  0x00150e67: lea      r9d, [rdx - 1]
  0x00150e6b: mov      r8d, edx
  0x00150e6e: mov      rcx, rbx
  0x00150e71: call     qword ptr [rax + 0x110]
  0x00150e77: test     al, al
  0x00150e79: je       0x150f4d
  0x00150e7f: mov      r9d, 1
  0x00150e85: mov      r8, 0xffffffffffffffff
  0x00150e8c: lea      rdx, [rip + 0x1cc84e5]
  0x00150e93: mov      rcx, rbx
  0x00150e96: call     0x13f1b80
  0x00150e9b: mov      r9d, 1
  0x00150ea1: mov      r8, 0xffffffffffffffff
  0x00150ea8: lea      rdx, [rip + 0x1cc84d9]
  0x00150eaf: mov      rcx, rbx
  0x00150eb2: call     0x13f1b80
  0x00150eb7: mov      r9d, 1
  0x00150ebd: mov      r8, 0xffffffffffffffff
  0x00150ec4: lea      rdx, [rip + 0x1cc84d5]
  0x00150ecb: mov      rcx, rbx
  0x00150ece: call     0x13f1b80
  0x00150ed3: mov      r9d, 1
  0x00150ed9: mov      r8, 0xffffffffffffffff
  0x00150ee0: lea      rdx, [rip + 0x1cc84d1]
  0x00150ee7: mov      rcx, rbx
  0x00150eea: call     0x13f1b80
  0x00150eef: mov      r9d, 1
  0x00150ef5: mov      r8, 0xffffffffffffffff
  0x00150efc: lea      rdx, [rip + 0x1cc84d5]
  0x00150f03: mov      rcx, rbx
  0x00150f06: call     0x13f1b80
  0x00150f0b: mov      r9d, 1
  0x00150f11: mov      r8, 0xffffffffffffffff
  0x00150f18: lea      rdx, [rip + 0x1cc84d9]
  0x00150f1f: mov      rcx, rbx
  0x00150f22: call     0x13f1b80
  0x00150f27: mov      r9d, 1
  0x00150f2d: mov      r8, 0xffffffffffffffff
  0x00150f34: lea      rdx, [rip + 0x1cc84dd]
  0x00150f3b: mov      rcx, rbx
  0x00150f3e: call     0x13f1b80
  0x00150f43: mov      rax, qword ptr [rbx]
  0x00150f46: mov      rcx, rbx
  0x00150f49: call     qword ptr [rax + 0x30]
  0x00150f4c: nop      
  0x00150f4d: test     rbx, rbx
  0x00150f50: je       0x150f5c
  0x00150f52: mov      rax, qword ptr [rbx]
  0x00150f55: mov      rcx, rbx
  0x00150f58: call     qword ptr [rax + 0x10]
  0x00150f5b: nop      
  0x00150f5c: movsx    eax, byte ptr [rbp - 0x31]
  0x00150f60: shr      eax, 7
  0x00150f63: and      al, 1
  0x00150f65: je       0x150f89
  0x00150f67: mov      eax, dword ptr [rbp - 0x34]
  0x00150f6a: btr      eax, 0x1f
  0x00150f6e: inc      eax
  0x00150f70: mov      rdx, qword ptr [rbp - 0x40]
  0x00150f74: test     rdx, rdx
  0x00150f77: je       0x150f89
  0x00150f79: mov      r8d, eax
  0x00150f7c: add      r8, r8
  0x00150f7f: lea      rcx, [rbp - 0x40]
  0x00150f83: call     0x6ab30
  0x00150f88: nop      
  0x00150f89: mov      rax, qword ptr [r14]
  0x00150f8c: mov      r8, qword ptr [rax + 0x10]
  0x00150f90: movsx    eax, byte ptr [rbp - 0x21]
  0x00150f94: shr      eax, 7
  0x00150f97: and      al, 1
  0x00150f99: lea      rdx, [rbp - 0x30]
  0x00150f9d: cmovne   rdx, qword ptr [rbp - 0x30]
  0x00150fa2: mov      rcx, r14
  0x00150fa5: call     r8
  0x00150fa8: mov      rax, qword ptr [r14]
  0x00150fab: mov      r8, qword ptr [rax + 0x20]
  0x00150faf: movsx    eax, byte ptr [rbp - 0x11]
  0x00150fb3: shr      eax, 7
  0x00150fb6: and      al, 1
  0x00150fb8: lea      rdx, [rbp - 0x20]
  0x00150fbc: cmovne   rdx, qword ptr [rbp - 0x20]
  0x00150fc1: mov      rcx, r14
  0x00150fc4: call     r8
  0x00150fc7: mov      bl, 1
  0x00150fc9: movsx    eax, byte ptr [rbp - 0x11]
  0x00150fcd: shr      eax, 7
  0x00150fd0: and      al, bl
  0x00150fd2: je       0x150ff6
  0x00150fd4: mov      eax, dword ptr [rbp - 0x14]
  0x00150fd7: btr      eax, 0x1f
  0x00150fdb: inc      eax
  0x00150fdd: mov      rdx, qword ptr [rbp - 0x20]
  0x00150fe1: test     rdx, rdx
  0x00150fe4: je       0x150ff6
  0x00150fe6: mov      r8d, eax
  0x00150fe9: add      r8, r8
  0x00150fec: lea      rcx, [rbp - 0x20]
  0x00150ff0: call     0x6ab30
  0x00150ff5: nop      
  0x00150ff6: movsx    eax, byte ptr [rbp - 1]
  0x00150ffa: shr      eax, 7
  0x00150ffd: and      al, 1
  0x00150fff: je       0x151023
  0x00151001: mov      eax, dword ptr [rbp - 4]
  0x00151004: btr      eax, 0x1f
  0x00151008: inc      eax
  0x0015100a: mov      rdx, qword ptr [rbp - 0x10]
  0x0015100e: test     rdx, rdx
  0x00151011: je       0x151023
  0x00151013: mov      r8d, eax
  0x00151016: add      r8, r8
  0x00151019: lea      rcx, [rbp - 0x10]
  0x0015101d: call     0x6ab30
  0x00151022: nop      
  0x00151023: movsx    eax, byte ptr [rbp - 0x21]
  0x00151027: shr      eax, 7
  0x0015102a: and      al, 1
  0x0015102c: je       0x151050
  0x0015102e: mov      ecx, dword ptr [rbp - 0x24]
  0x00151031: btr      ecx, 0x1f
  0x00151035: inc      ecx
  0x00151037: mov      rdx, qword ptr [rbp - 0x30]
  0x0015103b: test     rdx, rdx
  0x0015103e: je       0x151050
  0x00151040: mov      r8d, ecx
  0x00151043: add      r8, r8
  0x00151046: lea      rcx, [rbp - 0x30]
  0x0015104a: call     0x6ab30
  0x0015104f: nop      
  0x00151050: movzx    eax, bl
  0x00151053: add      rsp, 0x80
  0x0015105a: pop      r15
  0x0015105c: pop      r14
  0x0015105e: pop      r12
  0x00151060: pop      rdi
  0x00151061: pop      rsi
  0x00151062: pop      rbx
  0x00151063: pop      rbp
  0x00151064: ret      
  0x00151065: int3     
