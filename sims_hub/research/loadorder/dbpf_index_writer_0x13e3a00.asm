; function start 0x13e3a00
  0x013e3a00: mov      qword ptr [rsp + 8], rbx
  0x013e3a05: mov      byte ptr [rsp + 0x20], r9b
  0x013e3a0a: mov      qword ptr [rsp + 0x18], r8
  0x013e3a0f: mov      qword ptr [rsp + 0x10], rdx
  0x013e3a14: push     rbp
  0x013e3a15: push     rsi
  0x013e3a16: push     rdi
  0x013e3a17: push     r12
  0x013e3a19: push     r13
  0x013e3a1b: push     r14
  0x013e3a1d: push     r15
  0x013e3a1f: sub      rsp, 0x20
  0x013e3a23: mov      r10, qword ptr [rcx + 0x18]
  0x013e3a27: xor      ebp, ebp
  0x013e3a29: xor      r15d, r15d
  0x013e3a2c: xor      r12d, r12d
  0x013e3a2f: mov      r14, r8
  0x013e3a32: mov      r13, rcx
  0x013e3a35: mov      bl, 1
  0x013e3a37: mov      rdx, r10
  0x013e3a3a: mov      r9, qword ptr [r10]
  0x013e3a3d: test     r9, r9
  0x013e3a40: jne      0x13e3a5d
  0x013e3a42: mov      r9, qword ptr [r10 + 8]
  0x013e3a46: lea      rdx, [r10 + 8]
  0x013e3a4a: test     r9, r9
  0x013e3a4d: jne      0x13e3a5d
  0x013e3a4f: nop      
  0x013e3a50: mov      r9, qword ptr [rdx + 8]
  0x013e3a54: add      rdx, 8
  0x013e3a58: test     r9, r9
  0x013e3a5b: je       0x13e3a50
  0x013e3a5d: cmp      dword ptr [rcx + 0x24], ebp
  0x013e3a60: je       0x13e3a8f
  0x013e3a62: mov      rax, qword ptr [r9 + 0x30]
  0x013e3a66: mov      ebp, dword ptr [r9 + 8]
  0x013e3a6a: mov      r15d, dword ptr [r9 + 0xc]
  0x013e3a6e: mov      r12d, dword ptr [r9 + 4]
  0x013e3a72: mov      r9, rax
  0x013e3a75: test     rax, rax
  0x013e3a78: jne      0x13e3a91
  0x013e3a7a: nop      word ptr [rax + rax]
  0x013e3a80: mov      r9, qword ptr [rdx + 8]
  0x013e3a84: add      rdx, 8
  0x013e3a88: test     r9, r9
  0x013e3a8b: je       0x13e3a80
  0x013e3a8d: jmp      0x13e3a91
  0x013e3a8f: xor      bl, bl
  0x013e3a91: mov      eax, dword ptr [rcx + 0x20]
  0x013e3a94: xor      r11d, r11d
  0x013e3a97: movzx    esi, bl
  0x013e3a9a: movzx    edi, bl
  0x013e3a9d: mov      r8, qword ptr [r10 + rax*8]
  0x013e3aa1: cmp      r9, r8
  0x013e3aa4: je       0x13e3b3b
  0x013e3aaa: mov      r14d, 0xffff0000
  0x013e3ab0: test     bl, bl
  0x013e3ab2: je       0x13e3abe
  0x013e3ab4: cmp      dword ptr [r9 + 8], ebp
  0x013e3ab8: jne      0x13e3abe
  0x013e3aba: mov      bl, 1
  0x013e3abc: jmp      0x13e3ac0
  0x013e3abe: xor      bl, bl
  0x013e3ac0: test     sil, sil
  0x013e3ac3: je       0x13e3ad0
  0x013e3ac5: cmp      dword ptr [r9 + 0xc], r15d
  0x013e3ac9: jne      0x13e3ad0
  0x013e3acb: mov      sil, 1
  0x013e3ace: jmp      0x13e3ad3
  0x013e3ad0: xor      sil, sil
  0x013e3ad3: test     dil, dil
  0x013e3ad6: je       0x13e3ae3
  0x013e3ad8: cmp      dword ptr [r9 + 4], r12d
  0x013e3adc: jne      0x13e3ae3
  0x013e3ade: mov      dil, 1
  0x013e3ae1: jmp      0x13e3ae6
  0x013e3ae3: xor      dil, dil
  0x013e3ae6: cmp      qword ptr [r9 + 0x10], r14
  0x013e3aea: lea      ecx, [r11 + 8]
  0x013e3aee: cmovb    ecx, r11d
  0x013e3af2: cmp      qword ptr [r9 + 0x18], 0x3fffffff
  0x013e3afa: lea      eax, [rcx + 8]
  0x013e3afd: cmovb    eax, ecx
  0x013e3b00: cmp      qword ptr [r9 + 0x20], 0x3fffffff
  0x013e3b08: lea      r11d, [rax + 8]
  0x013e3b0c: cmovb    r11d, eax
  0x013e3b10: mov      rax, qword ptr [r9 + 0x30]
  0x013e3b14: mov      r9, rax
  0x013e3b17: test     rax, rax
  0x013e3b1a: jne      0x13e3b2d
  0x013e3b1c: nop      dword ptr [rax]
  0x013e3b20: mov      r9, qword ptr [rdx + 8]
  0x013e3b24: add      rdx, 8
  0x013e3b28: test     r9, r9
  0x013e3b2b: je       0x13e3b20
  0x013e3b2d: cmp      r9, r8
  0x013e3b30: jne      0x13e3ab0
  0x013e3b36: mov      r14, qword ptr [rsp + 0x70]
  0x013e3b3b: mov      eax, 0x20
  0x013e3b40: lea      ecx, [rax - 0x1c]
  0x013e3b43: test     bl, bl
  0x013e3b45: je       0x13e3b4d
  0x013e3b47: lea      eax, [rcx + 0x18]
  0x013e3b4a: lea      ecx, [rax - 0x14]
  0x013e3b4d: test     sil, sil
  0x013e3b50: je       0x13e3b59
  0x013e3b52: add      eax, -4
  0x013e3b55: add      rcx, 4
  0x013e3b59: test     dil, dil
  0x013e3b5c: je       0x13e3b65
  0x013e3b5e: add      eax, -4
  0x013e3b61: add      rcx, 4
  0x013e3b65: imul     eax, dword ptr [r13 + 0x24]
  0x013e3b6a: xor      r9d, r9d
  0x013e3b6d: mov      edx, r11d
  0x013e3b70: mov      r8d, eax
  0x013e3b73: add      r8, rcx
  0x013e3b76: mov      qword ptr [r14], r8
  0x013e3b79: add      rdx, r8
  0x013e3b7c: mov      rcx, qword ptr [r13 + 8]
  0x013e3b80: lea      r8, [rip + 0xc74311]
  0x013e3b87: mov      rax, qword ptr [rcx]
  0x013e3b8a: call     qword ptr [rax + 0x10]
  0x013e3b8d: mov      r10, rax
  0x013e3b90: mov      rax, qword ptr [rsp + 0x68]
  0x013e3b95: mov      qword ptr [rax], r10
  0x013e3b98: test     r10, r10
  0x013e3b9b: je       0x13e3d5a
  0x013e3ba1: movzx    edx, dil
  0x013e3ba5: mov      r8d, 1
  0x013e3bab: shl      edx, 2
  0x013e3bae: movzx    ecx, sil
  0x013e3bb2: add      ecx, ecx
  0x013e3bb4: or       edx, ecx
  0x013e3bb6: movzx    ecx, bl
  0x013e3bb9: or       edx, ecx
  0x013e3bbb: mov      dword ptr [r10], edx
  0x013e3bbe: test     bl, bl
  0x013e3bc0: je       0x13e3bcc
  0x013e3bc2: mov      dword ptr [r10 + 4], ebp
  0x013e3bc6: mov      r8d, 2
  0x013e3bcc: test     sil, sil
  0x013e3bcf: je       0x13e3bdb
  0x013e3bd1: mov      eax, r8d
  0x013e3bd4: inc      r8d
  0x013e3bd7: mov      dword ptr [r10 + rax*4], r15d
  0x013e3bdb: test     dil, dil
  0x013e3bde: je       0x13e3bea
  0x013e3be0: mov      eax, r8d
  0x013e3be3: inc      r8d
  0x013e3be6: mov      dword ptr [r10 + rax*4], r12d
  0x013e3bea: mov      rdx, qword ptr [r13 + 0x18]
  0x013e3bee: mov      r9, rdx
  0x013e3bf1: mov      rax, qword ptr [rdx]
  0x013e3bf4: test     rax, rax
  0x013e3bf7: jne      0x13e3c1d
  0x013e3bf9: mov      rax, qword ptr [rdx + 8]
  0x013e3bfd: lea      r9, [rdx + 8]
  0x013e3c01: test     rax, rax
  0x013e3c04: jne      0x13e3c1d
  0x013e3c06: nop      word ptr [rax + rax]
  0x013e3c10: mov      rax, qword ptr [r9 + 8]
  0x013e3c14: add      r9, 8
  0x013e3c18: test     rax, rax
  0x013e3c1b: je       0x13e3c10
  0x013e3c1d: mov      ecx, dword ptr [r13 + 0x20]
  0x013e3c21: mov      rbp, qword ptr [rdx + rcx*8]
  0x013e3c25: cmp      rax, rbp
  0x013e3c28: je       0x13e3d56
  0x013e3c2e: movzx    r15d, byte ptr [rsp + 0x78]
  0x013e3c34: test     bl, bl
  0x013e3c36: jne      0x13e3c45
  0x013e3c38: mov      ecx, dword ptr [rax + 8]
  0x013e3c3b: mov      edx, r8d
  0x013e3c3e: inc      r8d
  0x013e3c41: mov      dword ptr [r10 + rdx*4], ecx
  0x013e3c45: test     sil, sil
  0x013e3c48: jne      0x13e3c57
  0x013e3c4a: mov      ecx, dword ptr [rax + 0xc]
  0x013e3c4d: mov      edx, r8d
  0x013e3c50: inc      r8d
  0x013e3c53: mov      dword ptr [r10 + rdx*4], ecx
  0x013e3c57: test     dil, dil
  0x013e3c5a: jne      0x13e3c69
  0x013e3c5c: mov      ecx, dword ptr [rax + 4]
  0x013e3c5f: mov      edx, r8d
  0x013e3c62: inc      r8d
  0x013e3c65: mov      dword ptr [r10 + rdx*4], ecx
  0x013e3c69: mov      ecx, dword ptr [rax]
  0x013e3c6b: mov      edx, r8d
  0x013e3c6e: mov      dword ptr [r10 + rdx*4], ecx
  0x013e3c72: lea      edx, [r8 + 1]
  0x013e3c76: mov      r11, qword ptr [rax + 0x10]
  0x013e3c7a: lea      r8d, [rdx + 1]
  0x013e3c7e: mov      ecx, edx
  0x013e3c80: mov      edx, 0xffff0000
  0x013e3c85: cmp      r11, rdx
  0x013e3c88: jae      0x13e3c90
  0x013e3c8a: mov      dword ptr [r10 + rcx*4], r11d
  0x013e3c8e: jmp      0x13e3ca4
  0x013e3c90: mov      dword ptr [r10 + rcx*4], edx
  0x013e3c94: mov      rcx, qword ptr [rax + 0x10]
  0x013e3c98: mov      qword ptr [r10 + r8*4], rcx
  0x013e3c9c: add      r8d, 2
  0x013e3ca0: add      qword ptr [r14], 8
  0x013e3ca4: mov      rdx, qword ptr [rax + 0x18]
  0x013e3ca8: mov      ecx, r8d
  0x013e3cab: inc      r8d
  0x013e3cae: cmp      rdx, 0x3fffffff
  0x013e3cb5: jae      0x13e3cc1
  0x013e3cb7: bts      edx, 0x1f
  0x013e3cbb: mov      dword ptr [r10 + rcx*4], edx
  0x013e3cbf: jmp      0x13e3cd9
  0x013e3cc1: mov      dword ptr [r10 + rcx*4], 0xbfffffff
  0x013e3cc9: mov      rcx, qword ptr [rax + 0x18]
  0x013e3ccd: mov      qword ptr [r10 + r8*4], rcx
  0x013e3cd1: add      r8d, 2
  0x013e3cd5: add      qword ptr [r14], 8
  0x013e3cd9: mov      rdx, qword ptr [rax + 0x20]
  0x013e3cdd: mov      ecx, r8d
  0x013e3ce0: inc      r8d
  0x013e3ce3: cmp      rdx, 0x3fffffff
  0x013e3cea: jae      0x13e3cf2
  0x013e3cec: mov      dword ptr [r10 + rcx*4], edx
  0x013e3cf0: jmp      0x13e3d0a
  0x013e3cf2: mov      dword ptr [r10 + rcx*4], 0x3fffffff
  0x013e3cfa: mov      rcx, qword ptr [rax + 0x18]
  0x013e3cfe: mov      qword ptr [r10 + r8*4], rcx
  0x013e3d02: add      r8d, 2
  0x013e3d06: add      qword ptr [r14], 8
  0x013e3d0a: cmp      byte ptr [rax + 0x2a], 0
  0x013e3d0e: jne      0x13e3d19
  0x013e3d10: test     r15b, r15b
  0x013e3d13: jne      0x13e3d19
  0x013e3d15: xor      ecx, ecx
  0x013e3d17: jmp      0x13e3d1e
  0x013e3d19: mov      ecx, 0x10000
  0x013e3d1e: movzx    edx, word ptr [rax + 0x28]
  0x013e3d22: or       edx, ecx
  0x013e3d24: mov      dword ptr [r10 + r8*4], edx
  0x013e3d28: inc      r8d
  0x013e3d2b: mov      rcx, qword ptr [rax + 0x30]
  0x013e3d2f: mov      rax, rcx
  0x013e3d32: test     rcx, rcx
  0x013e3d35: jne      0x13e3d4d
  0x013e3d37: nop      word ptr [rax + rax]
  0x013e3d40: mov      rax, qword ptr [r9 + 8]
  0x013e3d44: add      r9, 8
  0x013e3d48: test     rax, rax
  0x013e3d4b: je       0x13e3d40
  0x013e3d4d: cmp      rax, rbp
  0x013e3d50: jne      0x13e3c34
  0x013e3d56: mov      al, 1
  0x013e3d58: jmp      0x13e3d5c
  0x013e3d5a: xor      al, al
  0x013e3d5c: mov      rbx, qword ptr [rsp + 0x60]
  0x013e3d61: add      rsp, 0x20
  0x013e3d65: pop      r15
  0x013e3d67: pop      r14
  0x013e3d69: pop      r13
  0x013e3d6b: pop      r12
  0x013e3d6d: pop      rdi
  0x013e3d6e: pop      rsi
  0x013e3d6f: pop      rbp
  0x013e3d70: ret      
  0x013e3d71: int3     
