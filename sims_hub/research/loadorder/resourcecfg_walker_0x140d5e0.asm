; function start 0x140d5e0
  0x0140d5e0: mov      qword ptr [rsp + 8], rcx
  0x0140d5e5: push     rbp
  0x0140d5e6: push     rsi
  0x0140d5e7: push     rdi
  0x0140d5e8: push     r12
  0x0140d5ea: push     r13
  0x0140d5ec: push     r14
  0x0140d5ee: push     r15
  0x0140d5f0: lea      rbp, [rsp - 0x400]
  0x0140d5f8: sub      rsp, 0x500
  0x0140d5ff: mov      qword ptr [rbp - 0x30], 0xfffffffffffffffe
  0x0140d607: mov      qword ptr [rsp + 0x548], rbx
  0x0140d60f: mov      rdi, rdx
  0x0140d612: mov      r12, rcx
  0x0140d615: mov      eax, dword ptr [rcx + 0x3b8]
  0x0140d61b: mov      dword ptr [rsp + 0x78], eax
  0x0140d61f: mov      eax, dword ptr [rcx + 0x3bc]
  0x0140d625: mov      dword ptr [rbp + 0x458], eax
  0x0140d62b: mov      rax, qword ptr [rcx + 0x3d0]
  0x0140d632: mov      qword ptr [rbp - 0x38], rax
  0x0140d636: xorps    xmm0, xmm0
  0x0140d639: movdqu   xmmword ptr [rbp - 0x70], xmm0
  0x0140d63e: xor      ecx, ecx
  0x0140d640: mov      qword ptr [rbp - 0x60], rcx
  0x0140d644: mov      rax, qword ptr [r12]
  0x0140d648: mov      qword ptr [rbp - 0x58], rax
  0x0140d64c: mov      dword ptr [rbp - 0x50], ecx
  0x0140d64f: xor      r14b, r14b
  0x0140d652: mov      byte ptr [rbp + 0x450], r14b
  0x0140d659: xor      sil, sil
  0x0140d65c: mov      rax, qword ptr [r12 + 0x68]
  0x0140d661: mov      rbx, qword ptr [rax]
  0x0140d664: cmp      rbx, qword ptr [rax + 8]
  0x0140d668: je       0x140d6d5
  0x0140d66a: lea      r14, [r12 + 0x78]
  0x0140d66f: nop      
  0x0140d670: mov      r9d, 5
  0x0140d676: mov      r8, r14
  0x0140d679: mov      rdx, qword ptr [rbx]
  0x0140d67c: lea      rcx, [rbp - 0x20]
  0x0140d680: call     0x14118e0
  0x0140d685: test     rax, rax
  0x0140d688: je       0x140d6be
  0x0140d68a: mov      rcx, qword ptr [r12 + 0x70]
  0x0140d68f: mov      rax, qword ptr [rcx]
  0x0140d692: lea      rdx, [rbp - 0x20]
  0x0140d696: call     qword ptr [rax]
  0x0140d698: test     al, al
  0x0140d69a: je       0x140d6be
  0x0140d69c: lea      r9, [rbp + 0x450]
  0x0140d6a3: lea      r8, [rbp - 0x70]
  0x0140d6a7: lea      rdx, [rbp - 0x20]
  0x0140d6ab: mov      rcx, r12
  0x0140d6ae: call     0x140ef60
  0x0140d6b3: test     al, al
  0x0140d6b5: je       0x140d8da
  0x0140d6bb: mov      sil, 1
  0x0140d6be: add      rbx, 8
  0x0140d6c2: mov      rax, qword ptr [r12 + 0x68]
  0x0140d6c7: cmp      rbx, qword ptr [rax + 8]
  0x0140d6cb: jne      0x140d670
  0x0140d6cd: movzx    r14d, byte ptr [rbp + 0x450]
  0x0140d6d5: mov      r13, qword ptr [rbp - 0x68]
  0x0140d6d9: mov      qword ptr [rsp + 0x58], r13
  0x0140d6de: mov      rbx, qword ptr [rbp - 0x70]
  0x0140d6e2: mov      qword ptr [rsp + 0x60], rbx
  0x0140d6e7: test     sil, sil
  0x0140d6ea: je       0x140d732
  0x0140d6ec: mov      rbx, qword ptr [rdi]
  0x0140d6ef: cmp      rbx, qword ptr [rdi + 8]
  0x0140d6f3: je       0x140d72d
  0x0140d6f5: cmp      qword ptr [rbx + 0x10], 0
  0x0140d6fa: jne      0x140d723
  0x0140d6fc: mov      rcx, qword ptr [rbx + 8]
  0x0140d700: cmp      word ptr [rcx], 0
  0x0140d704: je       0x140d71c
  0x0140d706: mov      r8d, 5
  0x0140d70c: lea      rdx, [rip + 0xc4ce6d]
  0x0140d713: call     0x1410e60
  0x0140d718: test     eax, eax
  0x0140d71a: jne      0x140d723
  0x0140d71c: mov      rax, qword ptr [rbx]
  0x0140d71f: mov      byte ptr [rax + 0x16], 1
  0x0140d723: add      rbx, 0x20
  0x0140d727: cmp      rbx, qword ptr [rdi + 8]
  0x0140d72b: jne      0x140d6f5
  0x0140d72d: mov      rbx, qword ptr [rsp + 0x60]
  0x0140d732: test     r14b, r14b
  0x0140d735: jne      0x140d767
  0x0140d737: movzx    eax, byte ptr [rbp + 0x440]
  0x0140d73e: mov      byte ptr [rsp + 0x20], al
  0x0140d742: mov      r9, qword ptr [rdi + 8]
  0x0140d746: mov      r8, qword ptr [rdi]
  0x0140d749: mov      rdx, r13
  0x0140d74c: lea      rcx, [rbp - 0x70]
  0x0140d750: call     0x140ce80
  0x0140d755: mov      r13, qword ptr [rbp - 0x68]
  0x0140d759: mov      qword ptr [rsp + 0x58], r13
  0x0140d75e: mov      rbx, qword ptr [rbp - 0x70]
  0x0140d762: mov      qword ptr [rsp + 0x60], rbx
  0x0140d767: mov      eax, 0x3e8
  0x0140d76c: movzx    edi, ax
  0x0140d76f: movzx    r14d, ax
  0x0140d773: xor      esi, esi
  0x0140d775: mov      r15d, esi
  0x0140d778: lea      ecx, [rsi + 5]
  0x0140d77b: call     0x1411600
  0x0140d780: cmp      rbx, r13
  0x0140d783: je       0x140d801
  0x0140d785: add      rbx, 0x10
  0x0140d789: nop      dword ptr [rax]
  0x0140d790: mov      rsi, qword ptr [rbx - 0x10]
  0x0140d794: cmp      dword ptr [rsi], 0
  0x0140d797: jne      0x140d7dc
  0x0140d799: mov      rcx, qword ptr [rbx - 8]
  0x0140d79d: cmp      word ptr [rcx], 0
  0x0140d7a1: je       0x140d7b9
  0x0140d7a3: mov      r8d, 5
  0x0140d7a9: lea      rdx, [rip + 0xc4cdd0]
  0x0140d7b0: call     0x1410e60
  0x0140d7b5: test     eax, eax
  0x0140d7b7: jne      0x140d7dc
  0x0140d7b9: cmp      qword ptr [rbx], 0
  0x0140d7bd: jne      0x140d7dc
  0x0140d7bf: movzx    eax, word ptr [rbx + 8]
  0x0140d7c3: cmp      ax, di
  0x0140d7c6: jl       0x140d7d1
  0x0140d7c8: jne      0x140d7dc
  0x0140d7ca: cmp      word ptr [rbx + 0xa], r14w
  0x0140d7cf: jge      0x140d7dc
  0x0140d7d1: movzx    edi, ax
  0x0140d7d4: movzx    r14d, word ptr [rbx + 0xa]
  0x0140d7d9: mov      r15, rsi
  0x0140d7dc: add      rbx, 0x20
  0x0140d7e0: lea      rax, [rbx - 0x10]
  0x0140d7e4: cmp      rax, r13
  0x0140d7e7: jne      0x140d790
  0x0140d7e9: xor      esi, esi
  0x0140d7eb: test     r15, r15
  0x0140d7ee: je       0x140d801
  0x0140d7f0: mov      eax, dword ptr [r15 + 4]
  0x0140d7f4: mov      dword ptr [r12 + 0x3b8], eax
  0x0140d7fc: mov      byte ptr [r15 + 0x16], 1
  0x0140d801: mov      eax, 0x3e8
  0x0140d806: movzx    edi, ax
  0x0140d809: movzx    r15d, ax
  0x0140d80d: mov      r14, rsi
  0x0140d810: mov      ecx, 5
  0x0140d815: call     0x1411600
  0x0140d81a: mov      r12, qword ptr [rsp + 0x60]
  0x0140d81f: cmp      r12, r13
  0x0140d822: je       0x140dc50
  0x0140d828: lea      rbx, [r12 + 0x10]
  0x0140d82d: nop      dword ptr [rax]
  0x0140d830: mov      rsi, qword ptr [rbx - 0x10]
  0x0140d834: cmp      dword ptr [rsi], 1
  0x0140d837: jne      0x140d87c
  0x0140d839: mov      rcx, qword ptr [rbx - 8]
  0x0140d83d: cmp      word ptr [rcx], 0
  0x0140d841: je       0x140d859
  0x0140d843: mov      r8d, 5
  0x0140d849: lea      rdx, [rip + 0xc4cd30]
  0x0140d850: call     0x1410e60
  0x0140d855: test     eax, eax
  0x0140d857: jne      0x140d87c
  0x0140d859: cmp      qword ptr [rbx], 0
  0x0140d85d: jne      0x140d87c
  0x0140d85f: movzx    eax, word ptr [rbx + 8]
  0x0140d863: cmp      ax, di
  0x0140d866: jl       0x140d871
  0x0140d868: jne      0x140d87c
  0x0140d86a: cmp      word ptr [rbx + 0xa], r15w
  0x0140d86f: jge      0x140d87c
  0x0140d871: movzx    edi, ax
  0x0140d874: movzx    r15d, word ptr [rbx + 0xa]
  0x0140d879: mov      r14, rsi
  0x0140d87c: add      rbx, 0x20
  0x0140d880: lea      rax, [rbx - 0x10]
  0x0140d884: cmp      rax, r13
  0x0140d887: jne      0x140d830
  0x0140d889: mov      r15, qword ptr [rbp + 0x440]
  0x0140d890: test     r14, r14
  0x0140d893: je       0x140d981
  0x0140d899: mov      byte ptr [r14 + 0x16], 1
  0x0140d89e: mov      r8b, 1
  0x0140d8a1: mov      edx, 0x40
  0x0140d8a6: lea      rcx, [r15 + 8]
  0x0140d8aa: call     0x13fc960
  0x0140d8af: mov      rsi, rax
  0x0140d8b2: xor      edx, edx
  0x0140d8b4: test     rax, rax
  0x0140d8b7: je       0x140d8e5
  0x0140d8b9: mov      qword ptr [rax], rdx
  0x0140d8bc: mov      qword ptr [rax + 8], rdx
  0x0140d8c0: mov      qword ptr [rax + 0x10], rdx
  0x0140d8c4: mov      qword ptr [rax + 0x18], rdx
  0x0140d8c8: mov      qword ptr [rax + 0x20], rdx
  0x0140d8cc: mov      qword ptr [rax + 0x28], rdx
  0x0140d8d0: mov      qword ptr [rax + 0x30], rdx
  0x0140d8d4: mov      qword ptr [rax + 0x38], rdx
  0x0140d8d8: jmp      0x140d8e8
  0x0140d8da: xor      bl, bl
  0x0140d8dc: mov      r12, qword ptr [rbp - 0x70]
  0x0140d8e0: jmp      0x140e70b
  0x0140d8e5: mov      rsi, rdx
  0x0140d8e8: mov      eax, dword ptr [r14 + 4]
  0x0140d8ec: mov      dword ptr [rsi + 0x10], eax
  0x0140d8ef: mov      eax, dword ptr [r14 + 0x10]
  0x0140d8f3: mov      dword ptr [rsi + 0x20], eax
  0x0140d8f6: mov      eax, dword ptr [r15 + 0x3b8]
  0x0140d8fd: mov      dword ptr [rsi + 0x14], eax
  0x0140d900: mov      rax, qword ptr [r14 + 8]
  0x0140d904: mov      qword ptr [rsi + 0x18], rax
  0x0140d908: movzx    eax, byte ptr [r14 + 0x14]
  0x0140d90d: mov      byte ptr [rsi + 0x24], al
  0x0140d910: mov      rcx, qword ptr [rsi + 0x38]
  0x0140d914: test     rcx, rcx
  0x0140d917: je       0x140d927
  0x0140d919: mov      qword ptr [rsi + 0x38], rdx
  0x0140d91d: add      rcx, 8
  0x0140d921: mov      rax, qword ptr [rcx]
  0x0140d924: call     qword ptr [rax + 8]
  0x0140d927: lea      rdi, [r15 + 0x78]
  0x0140d92b: mov      rcx, rdi
  0x0140d92e: call     0x13ca840
  0x0140d933: lea      rdx, [rax*2 + 2]
  0x0140d93b: mov      r8b, 1
  0x0140d93e: lea      rcx, [r15 + 8]
  0x0140d942: call     0x13fc960
  0x0140d947: mov      rbx, rax
  0x0140d94a: mov      rdx, rdi
  0x0140d94d: mov      rcx, rax
  0x0140d950: call     0x13c96e0
  0x0140d955: mov      qword ptr [rsi + 0x28], rbx
  0x0140d959: mov      rax, qword ptr [r15 + 0x3d0]
  0x0140d960: mov      qword ptr [rsi + 0x30], rax
  0x0140d964: lea      rcx, [r15 + 0x3c0]
  0x0140d96b: mov      rax, qword ptr [rcx + 8]
  0x0140d96f: mov      qword ptr [rsi + 8], rax
  0x0140d973: mov      qword ptr [rsi], rcx
  0x0140d976: mov      qword ptr [rcx + 8], rsi
  0x0140d97a: mov      rax, qword ptr [rsi + 8]
  0x0140d97e: mov      qword ptr [rax], rsi
  0x0140d981: xor      esi, esi
  0x0140d983: xor      dil, dil
  0x0140d986: mov      r9d, 0x5c
  0x0140d98c: mov      r14, qword ptr [rsp + 0x58]
  0x0140d991: cmp      r12, r14
  0x0140d994: je       0x140e28e
  0x0140d99a: lea      rbx, [r12 + 0x1c]
  0x0140d99f: nop      
  0x0140d9a0: mov      byte ptr [rbx], 0
  0x0140d9a3: mov      r8, qword ptr [rbx - 0x14]
  0x0140d9a7: movzx    eax, word ptr [r8]
  0x0140d9ab: test     ax, ax
  0x0140d9ae: je       0x140dc5c
  0x0140d9b4: lea      rcx, [rbp - 0x20]
  0x0140d9b8: add      r8, 2
  0x0140d9bc: mov      edx, 1
  0x0140d9c1: cmp      edx, 0x104
  0x0140d9c7: jae      0x140d9d0
  0x0140d9c9: mov      word ptr [rcx], ax
  0x0140d9cc: add      rcx, 2
  0x0140d9d0: cmp      ax, 0x5c
  0x0140d9d4: je       0x140da01
  0x0140d9d6: cmp      ax, 0x2f
  0x0140d9da: je       0x140da01
  0x0140d9dc: cmp      ax, 0x3a
  0x0140d9e0: je       0x140da01
  0x0140d9e2: movzx    eax, word ptr [r8]
  0x0140d9e6: add      r8, 2
  0x0140d9ea: inc      edx
  0x0140d9ec: test     ax, ax
  0x0140d9ef: jne      0x140d9c1
  0x0140d9f1: cmp      edx, 0x104
  0x0140d9f7: jae      0x140da01
  0x0140d9f9: mov      word ptr [rcx], r9w
  0x0140d9fd: add      rcx, 2
  0x0140da01: mov      word ptr [rcx], si
  0x0140da04: lea      rdx, [rip + 0xc4cb81]
  0x0140da0b: lea      rcx, [rbp - 0x20]
  0x0140da0f: call     0x13cab70
  0x0140da14: test     rax, rax
  0x0140da17: jne      0x140da31
  0x0140da19: lea      r8d, [rax + 5]
  0x0140da1d: lea      rdx, [rip + 0xc4cb5c]
  0x0140da24: lea      rcx, [rbp - 0x20]
  0x0140da28: call     0x1410e60
  0x0140da2d: test     eax, eax
  0x0140da2f: jne      0x140da37
  0x0140da31: mov      dil, 1
  0x0140da34: mov      byte ptr [rbx], dil
  0x0140da37: mov      r9d, 0x5c
  0x0140da3d: add      rbx, 0x20
  0x0140da41: lea      rax, [rbx - 0x1c]
  0x0140da45: cmp      rax, r14
  0x0140da48: jne      0x140d9a0
  0x0140da4e: test     dil, dil
  0x0140da51: je       0x140e28e
  0x0140da57: xorps    xmm0, xmm0
  0x0140da5a: movdqu   xmmword ptr [rsp + 0x30], xmm0
  0x0140da60: mov      qword ptr [rsp + 0x40], rsi
  0x0140da65: mov      rax, qword ptr [r15]
  0x0140da68: mov      qword ptr [rsp + 0x48], rax
  0x0140da6d: mov      dword ptr [rsp + 0x50], esi
  0x0140da71: mov      ecx, 5
  0x0140da76: call     0x1411600
  0x0140da7b: movzx    ebx, al
  0x0140da7e: mov      byte ptr [rbp + 0x450], al
  0x0140da84: mov      rcx, qword ptr [r15 + 0x70]
  0x0140da88: mov      rdx, qword ptr [rcx]
  0x0140da8b: mov      r10, qword ptr [rdx + 0x18]
  0x0140da8f: lea      rsi, [r15 + 0x78]
  0x0140da93: mov      qword ptr [rbp - 0x78], rsi
  0x0140da97: xor      r9d, r9d
  0x0140da9a: xor      r8d, r8d
  0x0140da9d: mov      rdx, rsi
  0x0140daa0: call     r10
  0x0140daa3: mov      r13, rax
  0x0140daa6: mov      qword ptr [rbp - 0x40], rax
  0x0140daaa: test     rax, rax
  0x0140daad: je       0x140e259
  0x0140dab3: lea      rdi, [rax + 2]
  0x0140dab7: mov      qword ptr [rbp - 0x80], rdi
  0x0140dabb: nop      dword ptr [rax + rax]
  0x0140dac0: mov      r8d, 0x104
  0x0140dac6: mov      rdx, rdi
  0x0140dac9: lea      rcx, [rbp - 0x20]
  0x0140dacd: call     0x13ca450
  0x0140dad2: mov      rcx, qword ptr [rsp + 0x30]
  0x0140dad7: mov      qword ptr [rsp + 0x38], rcx
  0x0140dadc: mov      dword ptr [rsp + 0x68], 0x5c002e
  0x0140dae4: xor      eax, eax
  0x0140dae6: mov      word ptr [rsp + 0x6c], ax
  0x0140daeb: mov      dword ptr [rsp + 0x70], 0x2e002e
  0x0140daf3: mov      dword ptr [rsp + 0x74], 0x5c
  0x0140dafb: lea      rdx, [rsp + 0x68]
  0x0140db00: lea      rcx, [rbp - 0x20]
  0x0140db04: call     0x13c9620
  0x0140db09: test     eax, eax
  0x0140db0b: je       0x140e1d7
  0x0140db11: lea      rdx, [rsp + 0x70]
  0x0140db16: lea      rcx, [rbp - 0x20]
  0x0140db1a: call     0x13c9620
  0x0140db1f: test     eax, eax
  0x0140db21: je       0x140e1d7
  0x0140db27: cmp      byte ptr [r13 + 0x20a], 0
  0x0140db2f: je       0x140e015
  0x0140db35: mov      rcx, rdi
  0x0140db38: call     0x13ca840
  0x0140db3d: mov      r13, rax
  0x0140db40: mov      qword ptr [rbp - 0x48], rax
  0x0140db44: mov      rdx, qword ptr [r15 + 0x3b0]
  0x0140db4b: lea      rcx, [rax + 1]
  0x0140db4f: add      rcx, rdx
  0x0140db52: cmp      rcx, 0x104
  0x0140db59: ja       0x140e1f5
  0x0140db5f: mov      r8d, 0x104
  0x0140db65: sub      r8, rdx
  0x0140db68: add      rdx, 0x3c
  0x0140db6c: lea      rcx, [r15 + rdx*2]
  0x0140db70: mov      rdx, rdi
  0x0140db73: call     0x13ca450
  0x0140db78: add      qword ptr [r15 + 0x3b0], r13
  0x0140db7f: mov      rax, qword ptr [r15 + 0x3b0]
  0x0140db86: xor      r13d, r13d
  0x0140db89: mov      word ptr [r15 + rax*2 + 0x78], r13w
  0x0140db8f: mov      r15, r12
  0x0140db92: mov      r8, qword ptr [r15 + 8]
  0x0140db96: movzx    eax, word ptr [r8]
  0x0140db9a: test     ax, ax
  0x0140db9d: je       0x140dfb5
  0x0140dba3: lea      rdx, [rbp + 0x1f0]
  0x0140dbaa: add      r8, 2
  0x0140dbae: mov      ecx, 1
  0x0140dbb3: cmp      ecx, 0x104
  0x0140dbb9: jae      0x140dbc2
  0x0140dbbb: mov      word ptr [rdx], ax
  0x0140dbbe: add      rdx, 2
  0x0140dbc2: cmp      ax, 0x5c
  0x0140dbc6: je       0x140dbf9
  0x0140dbc8: cmp      ax, 0x2f
  0x0140dbcc: je       0x140dbf9
  0x0140dbce: cmp      ax, 0x3a
  0x0140dbd2: je       0x140dbf9
  0x0140dbd4: movzx    eax, word ptr [r8]
  0x0140dbd8: add      r8, 2
  0x0140dbdc: inc      ecx
  0x0140dbde: test     ax, ax
  0x0140dbe1: jne      0x140dbb3
  0x0140dbe3: cmp      ecx, 0x104
  0x0140dbe9: jae      0x140dbf9
  0x0140dbeb: mov      eax, 0x5c
  0x0140dbf0: mov      word ptr [rdx], ax
  0x0140dbf3: add      rdx, 2
  0x0140dbf7: inc      ecx
  0x0140dbf9: mov      word ptr [rdx], r13w
  0x0140dbfd: mov      r12d, ecx
  0x0140dc00: mov      r8d, 5
  0x0140dc06: lea      rdx, [rip + 0xc4c973]
  0x0140dc0d: lea      rcx, [rbp + 0x1f0]
  0x0140dc14: call     0x1410e60
  0x0140dc19: test     eax, eax
  0x0140dc1b: jne      0x140de76
  0x0140dc21: mov      rbx, qword ptr [rsp + 0x38]
  0x0140dc26: cmp      rbx, qword ptr [rsp + 0x40]
  0x0140dc2b: jae      0x140dc8f
  0x0140dc2d: lea      rax, [rbx + 0x20]
  0x0140dc31: mov      qword ptr [rsp + 0x38], rax
  0x0140dc36: movups   xmm0, xmmword ptr [r15]
  0x0140dc3a: movups   xmmword ptr [rbx], xmm0
  0x0140dc3d: movups   xmm1, xmmword ptr [r15 + 0x10]
  0x0140dc42: movups   xmmword ptr [rbx + 0x10], xmm1
  0x0140dc46: mov      rbx, qword ptr [rsp + 0x38]
  0x0140dc4b: jmp      0x140dd57
  0x0140dc50: mov      r15, qword ptr [rbp + 0x440]
  0x0140dc57: jmp      0x140d983
  0x0140dc5c: mov      rcx, qword ptr [rbx - 0xc]
  0x0140dc60: test     rcx, rcx
  0x0140dc63: je       0x140da3d
  0x0140dc69: lea      rdx, [rip + 0xc4c91c]
  0x0140dc70: call     0x13cab70
  0x0140dc75: mov      r9d, 0x5c
  0x0140dc7b: test     rax, rax
  0x0140dc7e: je       0x140da3d
  0x0140dc84: mov      dil, 1
  0x0140dc87: mov      byte ptr [rbx], dil
  0x0140dc8a: jmp      0x140da3d
  0x0140dc8f: mov      rax, rbx
  0x0140dc92: mov      rsi, qword ptr [rsp + 0x30]
  0x0140dc97: sub      rax, rsi
  0x0140dc9a: sar      rax, 5
  0x0140dc9e: test     eax, eax
  0x0140dca0: je       0x140dcb0
  0x0140dca2: lea      r14d, [rax + rax]
  0x0140dca6: test     r14d, r14d
  0x0140dca9: jne      0x140dcb6
  0x0140dcab: mov      rdi, r13
  0x0140dcae: jmp      0x140dcdd
  0x0140dcb0: mov      r14d, 1
  0x0140dcb6: mov      edx, r14d
  0x0140dcb9: shl      rdx, 5
  0x0140dcbd: mov      rcx, qword ptr [rsp + 0x48]
  0x0140dcc2: mov      rax, qword ptr [rcx]
  0x0140dcc5: mov      r9d, dword ptr [rsp + 0x50]
  0x0140dcca: xor      r8d, r8d
  0x0140dccd: call     qword ptr [rax + 0x10]
  0x0140dcd0: mov      rdi, rax
  0x0140dcd3: mov      rbx, qword ptr [rsp + 0x38]
  0x0140dcd8: mov      rsi, qword ptr [rsp + 0x30]
  0x0140dcdd: cmp      rsi, rbx
  0x0140dce0: jne      0x140dce7
  0x0140dce2: mov      rax, rdi
  0x0140dce5: jmp      0x140dd02
  0x0140dce7: mov      r8, rbx
  0x0140dcea: sub      r8, rsi
  0x0140dced: mov      rdx, rsi
  0x0140dcf0: mov      rcx, rdi
  0x0140dcf3: call     0x143eb60
  0x0140dcf8: sub      rbx, rsi
  0x0140dcfb: and      rbx, 0xffffffffffffffe0
  0x0140dcff: add      rax, rbx
  0x0140dd02: movups   xmm0, xmmword ptr [r15]
  0x0140dd06: movups   xmmword ptr [rax], xmm0
  0x0140dd09: movups   xmm1, xmmword ptr [r15 + 0x10]
  0x0140dd0e: movups   xmmword ptr [rax + 0x10], xmm1
  0x0140dd12: lea      rbx, [rax + 0x20]
  0x0140dd16: mov      r8, qword ptr [rsp + 0x40]
  0x0140dd1b: mov      rdx, qword ptr [rsp + 0x30]
  0x0140dd20: sub      r8, rdx
  0x0140dd23: sar      r8, 5
  0x0140dd27: test     rdx, rdx
  0x0140dd2a: je       0x140dd3e
  0x0140dd2c: mov      rcx, qword ptr [rsp + 0x48]
  0x0140dd31: mov      rax, qword ptr [rcx]
  0x0140dd34: mov      r8d, r8d
  0x0140dd37: shl      r8, 5
  0x0140dd3b: call     qword ptr [rax + 0x18]
  0x0140dd3e: mov      qword ptr [rsp + 0x30], rdi
  0x0140dd43: mov      qword ptr [rsp + 0x38], rbx
  0x0140dd48: mov      eax, r14d
  0x0140dd4b: shl      rax, 5
  0x0140dd4f: add      rax, rdi
  0x0140dd52: mov      qword ptr [rsp + 0x40], rax
  0x0140dd57: inc      word ptr [rbx - 8]
  0x0140dd5b: mov      rax, qword ptr [rsp + 0x38]
  0x0140dd60: inc      word ptr [rax - 6]
  0x0140dd64: mov      rbx, qword ptr [rsp + 0x38]
  0x0140dd69: cmp      rbx, qword ptr [rsp + 0x40]
  0x0140dd6e: jae      0x140dd93
  0x0140dd70: lea      rax, [rbx + 0x20]
  0x0140dd74: mov      qword ptr [rsp + 0x38], rax
  0x0140dd79: movups   xmm0, xmmword ptr [r15]
  0x0140dd7d: movups   xmmword ptr [rbx], xmm0
  0x0140dd80: movups   xmm1, xmmword ptr [r15 + 0x10]
  0x0140dd85: movups   xmmword ptr [rbx + 0x10], xmm1
  0x0140dd89: mov      rbx, qword ptr [rsp + 0x38]
  0x0140dd8e: jmp      0x140de5b
  0x0140dd93: mov      rax, rbx
  0x0140dd96: mov      rsi, qword ptr [rsp + 0x30]
  0x0140dd9b: sub      rax, rsi
  0x0140dd9e: sar      rax, 5
  0x0140dda2: test     eax, eax
  0x0140dda4: je       0x140ddb4
  0x0140dda6: lea      r14d, [rax + rax]
  0x0140ddaa: test     r14d, r14d
  0x0140ddad: jne      0x140ddba
  0x0140ddaf: mov      rdi, r13
  0x0140ddb2: jmp      0x140dde1
  0x0140ddb4: mov      r14d, 1
  0x0140ddba: mov      edx, r14d
  0x0140ddbd: shl      rdx, 5
  0x0140ddc1: mov      rcx, qword ptr [rsp + 0x48]
  0x0140ddc6: mov      rax, qword ptr [rcx]
  0x0140ddc9: mov      r9d, dword ptr [rsp + 0x50]
  0x0140ddce: xor      r8d, r8d
  0x0140ddd1: call     qword ptr [rax + 0x10]
  0x0140ddd4: mov      rdi, rax
  0x0140ddd7: mov      rbx, qword ptr [rsp + 0x38]
  0x0140dddc: mov      rsi, qword ptr [rsp + 0x30]
  0x0140dde1: cmp      rsi, rbx
  0x0140dde4: jne      0x140ddeb
  0x0140dde6: mov      rax, rdi
  0x0140dde9: jmp      0x140de06
  0x0140ddeb: mov      r8, rbx
  0x0140ddee: sub      r8, rsi
  0x0140ddf1: mov      rdx, rsi
  0x0140ddf4: mov      rcx, rdi
  0x0140ddf7: call     0x143eb60
  0x0140ddfc: sub      rbx, rsi
  0x0140ddff: and      rbx, 0xffffffffffffffe0
  0x0140de03: add      rax, rbx
  0x0140de06: movups   xmm0, xmmword ptr [r15]
  0x0140de0a: movups   xmmword ptr [rax], xmm0
  0x0140de0d: movups   xmm1, xmmword ptr [r15 + 0x10]
  0x0140de12: movups   xmmword ptr [rax + 0x10], xmm1
  0x0140de16: lea      rbx, [rax + 0x20]
  0x0140de1a: mov      r8, qword ptr [rsp + 0x40]
  0x0140de1f: mov      rdx, qword ptr [rsp + 0x30]
  0x0140de24: sub      r8, rdx
  0x0140de27: sar      r8, 5
  0x0140de2b: test     rdx, rdx
  0x0140de2e: je       0x140de42
  0x0140de30: mov      rcx, qword ptr [rsp + 0x48]
  0x0140de35: mov      rax, qword ptr [rcx]
  0x0140de38: mov      r8d, r8d
  0x0140de3b: shl      r8, 5
  0x0140de3f: call     qword ptr [rax + 0x18]
  0x0140de42: mov      qword ptr [rsp + 0x30], rdi
  0x0140de47: mov      qword ptr [rsp + 0x38], rbx
  0x0140de4c: mov      eax, r14d
  0x0140de4f: shl      rax, 5
  0x0140de53: add      rax, rdi
  0x0140de56: mov      qword ptr [rsp + 0x40], rax
  0x0140de5b: lea      rax, [r12 + r12]
  0x0140de5f: add      qword ptr [rbx - 0x18], rax
  0x0140de63: mov      rax, qword ptr [rsp + 0x38]
  0x0140de68: inc      word ptr [rax - 8]
  0x0140de6c: mov      r14, qword ptr [rsp + 0x58]
  0x0140de71: jmp      0x140dfa5
  0x0140de76: movzx    r8d, bl
  0x0140de7a: lea      rdx, [rbp + 0x1f0]
  0x0140de81: lea      rcx, [rbp - 0x20]
  0x0140de85: call     0x13d07b0
  0x0140de8a: test     al, al
  0x0140de8c: je       0x140dfb5
  0x0140de92: mov      rbx, qword ptr [rsp + 0x38]
  0x0140de97: cmp      rbx, qword ptr [rsp + 0x40]
  0x0140de9c: jae      0x140dec1
  0x0140de9e: lea      rax, [rbx + 0x20]
  0x0140dea2: mov      qword ptr [rsp + 0x38], rax
  0x0140dea7: movups   xmm0, xmmword ptr [r15]
  0x0140deab: movups   xmmword ptr [rbx], xmm0
  0x0140deae: movups   xmm1, xmmword ptr [r15 + 0x10]
  0x0140deb3: movups   xmmword ptr [rbx + 0x10], xmm1
  0x0140deb7: mov      rbx, qword ptr [rsp + 0x38]
  0x0140debc: jmp      0x140df8e
  0x0140dec1: mov      rax, rbx
  0x0140dec4: mov      rsi, qword ptr [rsp + 0x30]
  0x0140dec9: sub      rax, rsi
  0x0140decc: sar      rax, 5
  0x0140ded0: test     eax, eax
  0x0140ded2: je       0x140dee2
  0x0140ded4: lea      r14d, [rax + rax]
  0x0140ded8: test     r14d, r14d
  0x0140dedb: jne      0x140dee8
  0x0140dedd: mov      rdi, r13
  0x0140dee0: jmp      0x140df0f
  0x0140dee2: mov      r14d, 1
  0x0140dee8: mov      edx, r14d
  0x0140deeb: shl      rdx, 5
  0x0140deef: mov      rcx, qword ptr [rsp + 0x48]
  0x0140def4: mov      rax, qword ptr [rcx]
  0x0140def7: mov      r9d, dword ptr [rsp + 0x50]
  0x0140defc: xor      r8d, r8d
  0x0140deff: call     qword ptr [rax + 0x10]
  0x0140df02: mov      rdi, rax
  0x0140df05: mov      rbx, qword ptr [rsp + 0x38]
  0x0140df0a: mov      rsi, qword ptr [rsp + 0x30]
  0x0140df0f: cmp      rsi, rbx
  0x0140df12: jne      0x140df19
  0x0140df14: mov      rax, rdi
  0x0140df17: jmp      0x140df34
  0x0140df19: mov      r8, rbx
  0x0140df1c: sub      r8, rsi
  0x0140df1f: mov      rdx, rsi
  0x0140df22: mov      rcx, rdi
  0x0140df25: call     0x143eb60
  0x0140df2a: sub      rbx, rsi
  0x0140df2d: and      rbx, 0xffffffffffffffe0
  0x0140df31: add      rax, rbx
  0x0140df34: movups   xmm0, xmmword ptr [r15]
  0x0140df38: movups   xmmword ptr [rax], xmm0
  0x0140df3b: movups   xmm1, xmmword ptr [r15 + 0x10]
  0x0140df40: movups   xmmword ptr [rax + 0x10], xmm1
  0x0140df44: lea      rbx, [rax + 0x20]
  0x0140df48: mov      r8, qword ptr [rsp + 0x40]
  0x0140df4d: mov      rdx, qword ptr [rsp + 0x30]
  0x0140df52: sub      r8, rdx
  0x0140df55: sar      r8, 5
  0x0140df59: test     rdx, rdx
  0x0140df5c: je       0x140df70
  0x0140df5e: mov      rcx, qword ptr [rsp + 0x48]
  0x0140df63: mov      rax, qword ptr [rcx]
  0x0140df66: mov      r8d, r8d
  0x0140df69: shl      r8, 5
  0x0140df6d: call     qword ptr [rax + 0x18]
  0x0140df70: mov      qword ptr [rsp + 0x30], rdi
  0x0140df75: mov      qword ptr [rsp + 0x38], rbx
  0x0140df7a: mov      eax, r14d
  0x0140df7d: shl      rax, 5
  0x0140df81: add      rax, rdi
  0x0140df84: mov      qword ptr [rsp + 0x40], rax
  0x0140df89: mov      r14, qword ptr [rsp + 0x58]
  0x0140df8e: inc      word ptr [rbx - 8]
  0x0140df92: mov      rcx, qword ptr [rsp + 0x38]
  0x0140df97: lea      rax, [r12 + r12]
  0x0140df9b: add      qword ptr [rcx - 0x18], rax
  0x0140df9f: cmp      byte ptr [r15 + 0x1c], r13b
  0x0140dfa3: je       0x140dfae
  0x0140dfa5: mov      rax, qword ptr [rsp + 0x38]
  0x0140dfaa: inc      word ptr [rax - 6]
  0x0140dfae: movzx    ebx, byte ptr [rbp + 0x450]
  0x0140dfb5: add      r15, 0x20
  0x0140dfb9: cmp      r15, r14
  0x0140dfbc: jne      0x140db92
  0x0140dfc2: mov      r13, qword ptr [rbp - 0x48]
  0x0140dfc6: mov      rax, qword ptr [rsp + 0x38]
  0x0140dfcb: mov      r15, qword ptr [rbp + 0x440]
  0x0140dfd2: cmp      qword ptr [rsp + 0x30], rax
  0x0140dfd7: je       0x140dfee
  0x0140dfd9: lea      rdx, [rsp + 0x30]
  0x0140dfde: mov      rcx, r15
  0x0140dfe1: call     0x140d5e0
  0x0140dfe6: test     al, al
  0x0140dfe8: je       0x140e22b
  0x0140dfee: sub      qword ptr [r15 + 0x3b0], r13
  0x0140dff5: mov      rax, qword ptr [r15 + 0x3b0]
  0x0140dffc: xor      ecx, ecx
  0x0140dffe: mov      word ptr [r15 + rax*2 + 0x78], cx
  0x0140e004: mov      r13, qword ptr [rbp - 0x40]
  0x0140e008: mov      rdi, qword ptr [rbp - 0x80]
  0x0140e00c: lea      rsi, [r15 + 0x78]
  0x0140e010: jmp      0x140e1d2
  0x0140e015: mov      eax, 0x3e8
  0x0140e01a: movzx    edi, ax
  0x0140e01d: movzx    r15d, ax
  0x0140e021: xor      ecx, ecx
  0x0140e023: mov      r14d, ecx
  0x0140e026: lea      ecx, [r14 + 5]
  0x0140e02a: call     0x1411600
  0x0140e02f: movzx    r12d, al
  0x0140e033: mov      rbx, qword ptr [rsp + 0x60]
  0x0140e038: add      rbx, 0x10
  0x0140e03c: mov      rcx, qword ptr [rsp + 0x58]
  0x0140e041: mov      rsi, qword ptr [rbx - 0x10]
  0x0140e045: cmp      dword ptr [rsi], 1
  0x0140e048: jne      0x140e0a5
  0x0140e04a: mov      rcx, qword ptr [rbx - 8]
  0x0140e04e: cmp      word ptr [rcx], 0
  0x0140e052: je       0x140e06a
  0x0140e054: mov      r8d, 5
  0x0140e05a: lea      rdx, [rip + 0xc4c51f]
  0x0140e061: call     0x1410e60
  0x0140e066: test     eax, eax
  0x0140e068: jne      0x140e0a0
  0x0140e06a: mov      rdx, qword ptr [rbx]
  0x0140e06d: test     rdx, rdx
  0x0140e070: je       0x140e0a0
  0x0140e072: movzx    r8d, r12b
  0x0140e076: lea      rcx, [rbp - 0x20]
  0x0140e07a: call     0x13d07b0
  0x0140e07f: test     al, al
  0x0140e081: je       0x140e0a0
  0x0140e083: movzx    eax, word ptr [rbx + 8]
  0x0140e087: cmp      ax, di
  0x0140e08a: jl       0x140e095
  0x0140e08c: jne      0x140e0a0
  0x0140e08e: cmp      word ptr [rbx + 0xa], r15w
  0x0140e093: jge      0x140e0a0
  0x0140e095: movzx    edi, ax
  0x0140e098: movzx    r15d, word ptr [rbx + 0xa]
  0x0140e09d: mov      r14, rsi
  0x0140e0a0: mov      rcx, qword ptr [rsp + 0x58]
  0x0140e0a5: add      rbx, 0x20
  0x0140e0a9: lea      rax, [rbx - 0x10]
  0x0140e0ad: cmp      rax, rcx
  0x0140e0b0: jne      0x140e041
  0x0140e0b2: mov      rsi, qword ptr [rbp - 0x78]
  0x0140e0b6: test     r14, r14
  0x0140e0b9: je       0x140e1c2
  0x0140e0bf: mov      r9d, 5
  0x0140e0c5: mov      r8, rsi
  0x0140e0c8: lea      rdx, [rbp - 0x20]
  0x0140e0cc: lea      rcx, [rbp + 0x1f0]
  0x0140e0d3: call     0x1411150
  0x0140e0d8: mov      byte ptr [r14 + 0x16], 1
  0x0140e0dd: mov      r15, qword ptr [rbp + 0x440]
  0x0140e0e4: mov      r8b, 1
  0x0140e0e7: mov      edx, 0x40
  0x0140e0ec: lea      rcx, [r15 + 8]
  0x0140e0f0: call     0x13fc960
  0x0140e0f5: mov      rdi, rax
  0x0140e0f8: xor      edx, edx
  0x0140e0fa: test     rax, rax
  0x0140e0fd: je       0x140e120
  0x0140e0ff: mov      qword ptr [rax], rdx
  0x0140e102: mov      qword ptr [rax + 8], rdx
  0x0140e106: mov      qword ptr [rax + 0x10], rdx
  0x0140e10a: mov      qword ptr [rax + 0x18], rdx
  0x0140e10e: mov      qword ptr [rax + 0x20], rdx
  0x0140e112: mov      qword ptr [rax + 0x28], rdx
  0x0140e116: mov      qword ptr [rax + 0x30], rdx
  0x0140e11a: mov      qword ptr [rax + 0x38], rdx
  0x0140e11e: jmp      0x140e123
  0x0140e120: mov      rdi, rdx
  0x0140e123: mov      eax, dword ptr [r14 + 4]
  0x0140e127: mov      dword ptr [rdi + 0x10], eax
  0x0140e12a: mov      eax, dword ptr [r14 + 0x10]
  0x0140e12e: mov      dword ptr [rdi + 0x20], eax
  0x0140e131: mov      eax, dword ptr [r15 + 0x3b8]
  0x0140e138: mov      dword ptr [rdi + 0x14], eax
  0x0140e13b: mov      rax, qword ptr [r14 + 8]
  0x0140e13f: mov      qword ptr [rdi + 0x18], rax
  0x0140e143: movzx    eax, byte ptr [r14 + 0x14]
  0x0140e148: mov      byte ptr [rdi + 0x24], al
  0x0140e14b: mov      rcx, qword ptr [rdi + 0x38]
  0x0140e14f: test     rcx, rcx
  0x0140e152: je       0x140e162
  0x0140e154: mov      qword ptr [rdi + 0x38], rdx
  0x0140e158: add      rcx, 8
  0x0140e15c: mov      rax, qword ptr [rcx]
  0x0140e15f: call     qword ptr [rax + 8]
  0x0140e162: lea      rcx, [rbp + 0x1f0]
  0x0140e169: call     0x13ca840
  0x0140e16e: lea      rdx, [rax*2 + 2]
  0x0140e176: mov      r8b, 1
  0x0140e179: lea      rcx, [r15 + 8]
  0x0140e17d: call     0x13fc960
  0x0140e182: mov      rbx, rax
  0x0140e185: lea      rdx, [rbp + 0x1f0]
  0x0140e18c: mov      rcx, rax
  0x0140e18f: call     0x13c96e0
  0x0140e194: mov      qword ptr [rdi + 0x28], rbx
  0x0140e198: mov      rax, qword ptr [r15 + 0x3d0]
  0x0140e19f: mov      qword ptr [rdi + 0x30], rax
  0x0140e1a3: lea      rcx, [r15 + 0x3c0]
  0x0140e1aa: mov      rax, qword ptr [rcx + 8]
  0x0140e1ae: mov      qword ptr [rdi + 8], rax
  0x0140e1b2: mov      qword ptr [rdi], rcx
  0x0140e1b5: mov      qword ptr [rcx + 8], rdi
  0x0140e1b9: mov      rax, qword ptr [rdi + 8]
  0x0140e1bd: mov      qword ptr [rax], rdi
  0x0140e1c0: jmp      0x140e1c9
  0x0140e1c2: mov      r15, qword ptr [rbp + 0x440]
  0x0140e1c9: mov      r14, qword ptr [rsp + 0x58]
  0x0140e1ce: lea      rdi, [r13 + 2]
  0x0140e1d2: mov      r12, qword ptr [rsp + 0x60]
  0x0140e1d7: mov      rcx, qword ptr [r15 + 0x70]
  0x0140e1db: mov      rax, qword ptr [rcx]
  0x0140e1de: mov      rdx, r13
  0x0140e1e1: call     qword ptr [rax + 0x20]
  0x0140e1e4: test     rax, rax
  0x0140e1e7: je       0x140e259
  0x0140e1e9: movzx    ebx, byte ptr [rbp + 0x450]
  0x0140e1f0: jmp      0x140dac0
  0x0140e1f5: mov      dword ptr [r15 + 0x3e8], 0xd06b0001
  0x0140e200: mov      r10, qword ptr [r15 + 0x3d8]
  0x0140e207: test     r10, r10
  0x0140e20a: je       0x140e230
  0x0140e20c: mov      rax, qword ptr [r15 + 0x3e0]
  0x0140e213: mov      qword ptr [rsp + 0x20], rax
  0x0140e218: xor      r9d, r9d
  0x0140e21b: xor      r8d, r8d
  0x0140e21e: mov      rdx, rsi
  0x0140e221: mov      ecx, 0xd06b0001
  0x0140e226: call     r10
  0x0140e229: jmp      0x140e230
  0x0140e22b: mov      r12, qword ptr [rsp + 0x60]
  0x0140e230: mov      rdx, qword ptr [rsp + 0x30]
  0x0140e235: test     rdx, rdx
  0x0140e238: je       0x140e252
  0x0140e23a: mov      r8, qword ptr [rsp + 0x40]
  0x0140e23f: sub      r8, rdx
  0x0140e242: and      r8, 0xffffffffffffffe0
  0x0140e246: mov      rcx, qword ptr [rsp + 0x48]
  0x0140e24b: mov      rax, qword ptr [rcx]
  0x0140e24e: call     qword ptr [rax + 0x18]
  0x0140e251: nop      
  0x0140e252: xor      bl, bl
  0x0140e254: jmp      0x140e70b
  0x0140e259: mov      rcx, qword ptr [r15 + 0x70]
  0x0140e25d: mov      rax, qword ptr [rcx]
  0x0140e260: mov      rdx, r13
  0x0140e263: call     qword ptr [rax + 0x28]
  0x0140e266: nop      
  0x0140e267: mov      rdx, qword ptr [rsp + 0x30]
  0x0140e26c: test     rdx, rdx
  0x0140e26f: je       0x140e289
  0x0140e271: mov      r8, qword ptr [rsp + 0x40]
  0x0140e276: sub      r8, rdx
  0x0140e279: and      r8, 0xffffffffffffffe0
  0x0140e27d: mov      rcx, qword ptr [rsp + 0x48]
  0x0140e282: mov      rax, qword ptr [rcx]
  0x0140e285: call     qword ptr [rax + 0x18]
  0x0140e288: nop      
  0x0140e289: jmp      0x140e6e6
  0x0140e28e: xorps    xmm0, xmm0
  0x0140e291: movdqu   xmmword ptr [rsp + 0x30], xmm0
  0x0140e297: mov      qword ptr [rsp + 0x40], rsi
  0x0140e29c: mov      rax, qword ptr [r15]
  0x0140e29f: mov      qword ptr [rsp + 0x48], rax
  0x0140e2a4: mov      dword ptr [rsp + 0x50], esi
  0x0140e2a8: mov      r13, r12
  0x0140e2ab: mov      qword ptr [rbp + 0x450], r12
  0x0140e2b2: cmp      r12, r14
  0x0140e2b5: je       0x140e6c4
  0x0140e2bb: nop      dword ptr [rax + rax]
  0x0140e2c0: mov      r8, qword ptr [r13 + 8]
  0x0140e2c4: movzx    eax, word ptr [r8]
  0x0140e2c8: test     ax, ax
  0x0140e2cb: jne      0x140e3f1
  0x0140e2d1: mov      rdx, qword ptr [r13 + 0x10]
  0x0140e2d5: test     rdx, rdx
  0x0140e2d8: je       0x140e6ab
  0x0140e2de: lea      r8, [r15 + 0x78]
  0x0140e2e2: mov      r9d, 5
  0x0140e2e8: lea      rcx, [rbp - 0x20]
  0x0140e2ec: call     0x1411150
  0x0140e2f1: mov      rbx, qword ptr [r13]
  0x0140e2f5: mov      rcx, qword ptr [r15 + 0x70]
  0x0140e2f9: mov      rax, qword ptr [rcx]
  0x0140e2fc: lea      rdx, [rbp - 0x20]
  0x0140e300: call     qword ptr [rax]
  0x0140e302: test     al, al
  0x0140e304: je       0x140e6ab
  0x0140e30a: cmp      dword ptr [rbx], 1
  0x0140e30d: jne      0x140e6ab
  0x0140e313: mov      byte ptr [rbx + 0x16], 1
  0x0140e317: mov      r8b, 1
  0x0140e31a: mov      edx, 0x40
  0x0140e31f: lea      rcx, [r15 + 8]
  0x0140e323: call     0x13fc960
  0x0140e328: mov      rdi, rax
  0x0140e32b: xor      edx, edx
  0x0140e32d: test     rax, rax
  0x0140e330: je       0x140e353
  0x0140e332: mov      qword ptr [rax], rdx
  0x0140e335: mov      qword ptr [rax + 8], rdx
  0x0140e339: mov      qword ptr [rax + 0x10], rdx
  0x0140e33d: mov      qword ptr [rax + 0x18], rdx
  0x0140e341: mov      qword ptr [rax + 0x20], rdx
  0x0140e345: mov      qword ptr [rax + 0x28], rdx
  0x0140e349: mov      qword ptr [rax + 0x30], rdx
  0x0140e34d: mov      qword ptr [rax + 0x38], rdx
  0x0140e351: jmp      0x140e356
  0x0140e353: mov      rdi, rdx
  0x0140e356: mov      eax, dword ptr [rbx + 4]
  0x0140e359: mov      dword ptr [rdi + 0x10], eax
  0x0140e35c: mov      eax, dword ptr [rbx + 0x10]
  0x0140e35f: mov      dword ptr [rdi + 0x20], eax
  0x0140e362: mov      eax, dword ptr [r15 + 0x3b8]
  0x0140e369: mov      dword ptr [rdi + 0x14], eax
  0x0140e36c: mov      rax, qword ptr [rbx + 8]
  0x0140e370: mov      qword ptr [rdi + 0x18], rax
  0x0140e374: movzx    eax, byte ptr [rbx + 0x14]
  0x0140e378: mov      byte ptr [rdi + 0x24], al
  0x0140e37b: mov      rcx, qword ptr [rdi + 0x38]
  0x0140e37f: test     rcx, rcx
  0x0140e382: je       0x140e392
  0x0140e384: mov      qword ptr [rdi + 0x38], rdx
  0x0140e388: add      rcx, 8
  0x0140e38c: mov      rax, qword ptr [rcx]
  0x0140e38f: call     qword ptr [rax + 8]
  0x0140e392: lea      rcx, [rbp - 0x20]
  0x0140e396: call     0x13ca840
  0x0140e39b: lea      rdx, [rax*2 + 2]
  0x0140e3a3: mov      r8b, 1
  0x0140e3a6: lea      rcx, [r15 + 8]
  0x0140e3aa: call     0x13fc960
  0x0140e3af: mov      rbx, rax
  0x0140e3b2: lea      rdx, [rbp - 0x20]
  0x0140e3b6: mov      rcx, rax
  0x0140e3b9: call     0x13c96e0
  0x0140e3be: mov      qword ptr [rdi + 0x28], rbx
  0x0140e3c2: mov      rax, qword ptr [r15 + 0x3d0]
  0x0140e3c9: mov      qword ptr [rdi + 0x30], rax
  0x0140e3cd: lea      rcx, [r15 + 0x3c0]
  0x0140e3d4: mov      rax, qword ptr [rcx + 8]
  0x0140e3d8: mov      qword ptr [rdi + 8], rax
  0x0140e3dc: mov      qword ptr [rdi], rcx
  0x0140e3df: mov      qword ptr [rcx + 8], rdi
  0x0140e3e3: mov      rax, qword ptr [rdi + 8]
  0x0140e3e7: mov      qword ptr [rax], rdi
  0x0140e3ea: xor      esi, esi
  0x0140e3ec: jmp      0x140e6ab
  0x0140e3f1: lea      rdx, [rbp + 0x1f0]
  0x0140e3f8: add      r8, 2
  0x0140e3fc: mov      ecx, 1
  0x0140e401: cmp      ecx, 0x104
  0x0140e407: jae      0x140e410
  0x0140e409: mov      word ptr [rdx], ax
  0x0140e40c: add      rdx, 2
  0x0140e410: cmp      ax, 0x5c
  0x0140e414: je       0x140e449
  0x0140e416: cmp      ax, 0x2f
  0x0140e41a: je       0x140e449
  0x0140e41c: cmp      ax, 0x3a
  0x0140e420: je       0x140e449
  0x0140e422: movzx    eax, word ptr [r8]
  0x0140e426: add      r8, 2
  0x0140e42a: inc      ecx
  0x0140e42c: test     ax, ax
  0x0140e42f: jne      0x140e401
  0x0140e431: mov      edi, 0x5c
  0x0140e436: cmp      ecx, 0x104
  0x0140e43c: jae      0x140e44e
  0x0140e43e: mov      word ptr [rdx], di
  0x0140e441: add      rdx, 2
  0x0140e445: inc      ecx
  0x0140e447: jmp      0x140e44e
  0x0140e449: mov      edi, 0x5c
  0x0140e44e: mov      word ptr [rdx], si
  0x0140e451: mov      ebx, ecx
  0x0140e453: mov      qword ptr [rbp - 0x80], rbx
  0x0140e457: mov      rcx, qword ptr [r15 + 0x3b0]
  0x0140e45e: lea      rax, [rcx + 1]
  0x0140e462: add      rax, rbx
  0x0140e465: cmp      rax, 0x104
  0x0140e46b: ja       0x140e748
  0x0140e471: lea      r12, [rbx + rbx]
  0x0140e475: add      rcx, 0x3c
  0x0140e479: lea      rcx, [r15 + rcx*2]
  0x0140e47d: mov      r8, r12
  0x0140e480: lea      rdx, [rbp + 0x1f0]
  0x0140e487: call     0x143eb6c
  0x0140e48c: add      qword ptr [r15 + 0x3b0], rbx
  0x0140e493: mov      rax, qword ptr [r15 + 0x3b0]
  0x0140e49a: mov      word ptr [r15 + rax*2 + 0x78], si
  0x0140e4a0: mov      rcx, qword ptr [r15 + 0x70]
  0x0140e4a4: mov      rax, qword ptr [rcx]
  0x0140e4a7: lea      rdx, [r15 + 0x78]
  0x0140e4ab: call     qword ptr [rax + 8]
  0x0140e4ae: test     al, al
  0x0140e4b0: je       0x140e697
  0x0140e4b6: mov      rax, qword ptr [rsp + 0x30]
  0x0140e4bb: mov      qword ptr [rsp + 0x38], rax
  0x0140e4c0: mov      r15, r13
  0x0140e4c3: cmp      r13, r14
  0x0140e4c6: je       0x140e67b
  0x0140e4cc: xor      r13d, r13d
  0x0140e4cf: nop      
  0x0140e4d0: lea      rcx, [rbp - 0x20]
  0x0140e4d4: mov      rdx, qword ptr [r15 + 8]
  0x0140e4d8: movzx    eax, word ptr [rdx]
  0x0140e4db: add      rdx, 2
  0x0140e4df: mov      r8d, 1
  0x0140e4e5: test     ax, ax
  0x0140e4e8: je       0x140e52a
  0x0140e4ea: nop      word ptr [rax + rax]
  0x0140e4f0: cmp      r8d, 0x104
  0x0140e4f7: jae      0x140e500
  0x0140e4f9: mov      word ptr [rcx], ax
  0x0140e4fc: add      rcx, 2
  0x0140e500: cmp      ax, 0x5c
  0x0140e504: je       0x140e531
  0x0140e506: cmp      ax, 0x2f
  0x0140e50a: je       0x140e531
  0x0140e50c: cmp      ax, 0x3a
  0x0140e510: je       0x140e531
  0x0140e512: movzx    eax, word ptr [rdx]
  0x0140e515: add      rdx, 2
  0x0140e519: inc      r8d
  0x0140e51c: test     ax, ax
  0x0140e51f: jne      0x140e4f0
  0x0140e521: cmp      r8d, 0x104
  0x0140e528: jae      0x140e531
  0x0140e52a: mov      word ptr [rcx], di
  0x0140e52d: add      rcx, 2
  0x0140e531: mov      word ptr [rcx], r13w
  0x0140e535: mov      r8d, 5
  0x0140e53b: lea      rdx, [rbp - 0x20]
  0x0140e53f: lea      rcx, [rbp + 0x1f0]
  0x0140e546: call     0x1410e60
  0x0140e54b: test     eax, eax
  0x0140e54d: jne      0x140e65c
  0x0140e553: mov      rbx, qword ptr [rsp + 0x38]
  0x0140e558: cmp      rbx, qword ptr [rsp + 0x40]
  0x0140e55d: jae      0x140e582
  0x0140e55f: lea      rax, [rbx + 0x20]
  0x0140e563: mov      qword ptr [rsp + 0x38], rax
  0x0140e568: movups   xmm0, xmmword ptr [r15]
  0x0140e56c: movups   xmmword ptr [rbx], xmm0
  0x0140e56f: movups   xmm1, xmmword ptr [r15 + 0x10]
  0x0140e574: movups   xmmword ptr [rbx + 0x10], xmm1
  0x0140e578: mov      rbx, qword ptr [rsp + 0x38]
  0x0140e57d: jmp      0x140e64f
  0x0140e582: mov      rax, rbx
  0x0140e585: mov      rdi, qword ptr [rsp + 0x30]
  0x0140e58a: sub      rax, rdi
  0x0140e58d: sar      rax, 5
  0x0140e591: test     eax, eax
  0x0140e593: je       0x140e5a3
  0x0140e595: lea      r14d, [rax + rax]
  0x0140e599: test     r14d, r14d
  0x0140e59c: jne      0x140e5a9
  0x0140e59e: mov      rsi, r13
  0x0140e5a1: jmp      0x140e5d0
  0x0140e5a3: mov      r14d, 1
  0x0140e5a9: mov      edx, r14d
  0x0140e5ac: shl      rdx, 5
  0x0140e5b0: mov      rcx, qword ptr [rsp + 0x48]
  0x0140e5b5: mov      rax, qword ptr [rcx]
  0x0140e5b8: mov      r9d, dword ptr [rsp + 0x50]
  0x0140e5bd: xor      r8d, r8d
  0x0140e5c0: call     qword ptr [rax + 0x10]
  0x0140e5c3: mov      rsi, rax
  0x0140e5c6: mov      rbx, qword ptr [rsp + 0x38]
  0x0140e5cb: mov      rdi, qword ptr [rsp + 0x30]
  0x0140e5d0: cmp      rdi, rbx
  0x0140e5d3: jne      0x140e5da
  0x0140e5d5: mov      rax, rsi
  0x0140e5d8: jmp      0x140e5f5
  0x0140e5da: mov      r8, rbx
  0x0140e5dd: sub      r8, rdi
  0x0140e5e0: mov      rdx, rdi
  0x0140e5e3: mov      rcx, rsi
  0x0140e5e6: call     0x143eb60
  0x0140e5eb: sub      rbx, rdi
  0x0140e5ee: and      rbx, 0xffffffffffffffe0
  0x0140e5f2: add      rax, rbx
  0x0140e5f5: movups   xmm0, xmmword ptr [r15]
  0x0140e5f9: movups   xmmword ptr [rax], xmm0
  0x0140e5fc: movups   xmm1, xmmword ptr [r15 + 0x10]
  0x0140e601: movups   xmmword ptr [rax + 0x10], xmm1
  0x0140e605: lea      rbx, [rax + 0x20]
  0x0140e609: mov      r8, qword ptr [rsp + 0x40]
  0x0140e60e: mov      rdx, qword ptr [rsp + 0x30]
  0x0140e613: sub      r8, rdx
  0x0140e616: sar      r8, 5
  0x0140e61a: test     rdx, rdx
  0x0140e61d: je       0x140e631
  0x0140e61f: mov      rcx, qword ptr [rsp + 0x48]
  0x0140e624: mov      rax, qword ptr [rcx]
  0x0140e627: mov      r8d, r8d
  0x0140e62a: shl      r8, 5
  0x0140e62e: call     qword ptr [rax + 0x18]
  0x0140e631: mov      qword ptr [rsp + 0x30], rsi
  0x0140e636: mov      qword ptr [rsp + 0x38], rbx
  0x0140e63b: mov      eax, r14d
  0x0140e63e: shl      rax, 5
  0x0140e642: add      rax, rsi
  0x0140e645: mov      qword ptr [rsp + 0x40], rax
  0x0140e64a: mov      r14, qword ptr [rsp + 0x58]
  0x0140e64f: add      qword ptr [rbx - 0x18], r12
  0x0140e653: mov      rax, qword ptr [rsp + 0x38]
  0x0140e658: inc      word ptr [rax - 8]
  0x0140e65c: add      r15, 0x20
  0x0140e660: cmp      r15, r14
  0x0140e663: mov      edi, 0x5c
  0x0140e668: jne      0x140e4d0
  0x0140e66e: mov      r13, qword ptr [rbp + 0x450]
  0x0140e675: mov      rbx, qword ptr [rbp - 0x80]
  0x0140e679: xor      esi, esi
  0x0140e67b: lea      rdx, [rsp + 0x30]
  0x0140e680: mov      r15, qword ptr [rbp + 0x440]
  0x0140e687: mov      rcx, r15
  0x0140e68a: call     0x140d5e0
  0x0140e68f: test     al, al
  0x0140e691: je       0x140e77e
  0x0140e697: sub      qword ptr [r15 + 0x3b0], rbx
  0x0140e69e: mov      rax, qword ptr [r15 + 0x3b0]
  0x0140e6a5: mov      word ptr [r15 + rax*2 + 0x78], si
  0x0140e6ab: add      r13, 0x20
  0x0140e6af: mov      qword ptr [rbp + 0x450], r13
  0x0140e6b6: cmp      r13, r14
  0x0140e6b9: jne      0x140e2c0
  0x0140e6bf: mov      r12, qword ptr [rsp + 0x60]
  0x0140e6c4: mov      rdx, qword ptr [rsp + 0x30]
  0x0140e6c9: test     rdx, rdx
  0x0140e6cc: je       0x140e6e6
  0x0140e6ce: mov      r8, qword ptr [rsp + 0x40]
  0x0140e6d3: sub      r8, rdx
  0x0140e6d6: and      r8, 0xffffffffffffffe0
  0x0140e6da: mov      rcx, qword ptr [rsp + 0x48]
  0x0140e6df: mov      rax, qword ptr [rcx]
  0x0140e6e2: call     qword ptr [rax + 0x18]
  0x0140e6e5: nop      
  0x0140e6e6: mov      eax, dword ptr [rbp + 0x458]
  0x0140e6ec: mov      dword ptr [r15 + 0x3bc], eax
  0x0140e6f3: mov      eax, dword ptr [rsp + 0x78]
  0x0140e6f7: mov      dword ptr [r15 + 0x3b8], eax
  0x0140e6fe: mov      rax, qword ptr [rbp - 0x38]
  0x0140e702: mov      qword ptr [r15 + 0x3d0], rax
  0x0140e709: mov      bl, 1
  0x0140e70b: test     r12, r12
  0x0140e70e: je       0x140e72a
  0x0140e710: mov      r8, qword ptr [rbp - 0x60]
  0x0140e714: sub      r8, r12
  0x0140e717: and      r8, 0xffffffffffffffe0
  0x0140e71b: mov      rcx, qword ptr [rbp - 0x58]
  0x0140e71f: mov      r9, qword ptr [rcx]
  0x0140e722: mov      rdx, r12
  0x0140e725: call     qword ptr [r9 + 0x18]
  0x0140e729: nop      
  0x0140e72a: movzx    eax, bl
  0x0140e72d: mov      rbx, qword ptr [rsp + 0x548]
  0x0140e735: add      rsp, 0x500
  0x0140e73c: pop      r15
  0x0140e73e: pop      r14
  0x0140e740: pop      r13
  0x0140e742: pop      r12
  0x0140e744: pop      rdi
  0x0140e745: pop      rsi
  0x0140e746: pop      rbp
  0x0140e747: ret      
  0x0140e748: mov      dword ptr [r15 + 0x3e8], 0xd06b0001
  0x0140e753: mov      r10, qword ptr [r15 + 0x3d8]
  0x0140e75a: test     r10, r10
  0x0140e75d: je       0x140e77e
  0x0140e75f: lea      rdx, [r15 + 0x78]
  0x0140e763: mov      rax, qword ptr [r15 + 0x3e0]
  0x0140e76a: mov      qword ptr [rsp + 0x20], rax
  0x0140e76f: xor      r9d, r9d
  0x0140e772: xor      r8d, r8d
  0x0140e775: mov      ecx, 0xd06b0001
  0x0140e77a: call     r10
  0x0140e77d: nop      
  0x0140e77e: mov      rdx, qword ptr [rsp + 0x30]
  0x0140e783: test     rdx, rdx
  0x0140e786: je       0x140e7a0
  0x0140e788: mov      r8, qword ptr [rsp + 0x40]
  0x0140e78d: sub      r8, rdx
  0x0140e790: and      r8, 0xffffffffffffffe0
  0x0140e794: mov      rcx, qword ptr [rsp + 0x48]
  0x0140e799: mov      rax, qword ptr [rcx]
  0x0140e79c: call     qword ptr [rax + 0x18]
  0x0140e79f: nop      
  0x0140e7a0: xor      bl, bl
  0x0140e7a2: mov      r12, qword ptr [rsp + 0x60]
  0x0140e7a7: jmp      0x140e70b
  0x0140e7ac: int3     
  0x0140e7ad: int3     
  0x0140e7ae: int3     
  0x0140e7af: int3     
  0x0140e7b0: mov      rcx, rdx
  0x0140e7b3: jmp      0x13ed1c0
  0x0140e7b8: int3     
  0x0140e7b9: int3     
  0x0140e7ba: int3     
  0x0140e7bb: int3     
  0x0140e7bc: int3     
  0x0140e7bd: int3     
  0x0140e7be: int3     
  0x0140e7bf: int3     
  0x0140e7c0: mov      qword ptr [rsp + 0x10], rbx
  0x0140e7c5: mov      qword ptr [rsp + 0x18], rbp
  0x0140e7ca: push     rsi
  0x0140e7cb: push     rdi
  0x0140e7cc: push     r12
  0x0140e7ce: push     r14
  0x0140e7d0: push     r15
  0x0140e7d2: sub      rsp, 0x30
  0x0140e7d6: mov      rbp, qword ptr [r9]
  0x0140e7d9: mov      r12, r9
  0x0140e7dc: mov      rsi, rdx
  0x0140e7df: mov      eax, 0x811c9dc5
  0x0140e7e4: mov      rdi, rcx
  0x0140e7e7: movzx    r11d, word ptr [rbp]
  0x0140e7ec: lea      r8, [rbp + 2]
  0x0140e7f0: mov      r10d, r11d
  0x0140e7f3: test     r11d, r11d
  0x0140e7f6: je       0x140e817
  0x0140e7f8: nop      dword ptr [rax + rax]
  0x0140e800: imul     eax, eax, 0x1000193
  0x0140e806: lea      r8, [r8 + 2]
  0x0140e80a: xor      eax, r10d
  0x0140e80d: movzx    r10d, word ptr [r8 - 2]
  0x0140e812: test     r10d, r10d
  0x0140e815: jne      0x140e800
  0x0140e817: mov      r10d, dword ptr [rcx + 0x10]
  0x0140e81b: xor      edx, edx
  0x0140e81d: mov      r15d, eax
  0x0140e820: div      r10
  0x0140e823: mov      rax, qword ptr [rdi + 8]
  0x0140e827: mov      ecx, edx
  0x0140e829: mov      r14, rdx
  0x0140e82c: mov      rbx, qword ptr [rax + rcx*8]
  0x0140e830: lea      r9, [rax + rcx*8]
  0x0140e834: test     rbx, rbx
  0x0140e837: je       0x140e883
  0x0140e839: nop      dword ptr [rax]
  0x0140e840: mov      rcx, qword ptr [rbx]
  0x0140e843: movzx    edx, r11w
  0x0140e847: test     r11w, r11w
  0x0140e84b: je       0x140e871
  0x0140e84d: mov      r8, rbp
  0x0140e850: movzx    eax, r11w
  0x0140e854: sub      r8, rcx
  0x0140e857: movzx    edx, ax
  0x0140e85a: cmp      ax, word ptr [rcx]
  0x0140e85d: jne      0x140e871
  0x0140e85f: movzx    eax, word ptr [rcx + r8 + 2]
  0x0140e865: add      rcx, 2
  0x0140e869: movzx    edx, ax
  0x0140e86c: test     ax, ax
  0x0140e86f: jne      0x140e857
  0x0140e871: cmp      dx, word ptr [rcx]
  0x0140e874: je       0x140e934
  0x0140e87a: mov      rbx, qword ptr [rbx + 0x10]
  0x0140e87e: test     rbx, rbx
  0x0140e881: jne      0x140e840
  0x0140e883: mov      r9d, dword ptr [rdi + 0x14]
  0x0140e887: lea      rcx, [rdi + 0x18]
  0x0140e88b: mov      r8d, r10d
  0x0140e88e: mov      dword ptr [rsp + 0x20], 1
  0x0140e896: lea      rdx, [rsp + 0x60]
  0x0140e89b: call     0x13d95b0
  0x0140e8a0: mov      rcx, qword ptr [rdi + 0x28]
  0x0140e8a4: mov      r8b, 1
  0x0140e8a7: mov      edx, 0x18
  0x0140e8ac: call     0x13fc960
  0x0140e8b1: mov      rcx, qword ptr [r12]
  0x0140e8b5: mov      rbx, rax
  0x0140e8b8: mov      qword ptr [rax], rcx
  0x0140e8bb: xor      eax, eax
  0x0140e8bd: mov      dword ptr [rbx + 8], eax
  0x0140e8c0: mov      qword ptr [rbx + 0x10], rax
  0x0140e8c4: cmp      byte ptr [rsp + 0x60], al
  0x0140e8c8: je       0x140e8e5
  0x0140e8ca: mov      r8d, dword ptr [rsp + 0x64]
  0x0140e8cf: xor      edx, edx
  0x0140e8d1: mov      rax, r15
  0x0140e8d4: mov      rcx, rdi
  0x0140e8d7: div      r8
  0x0140e8da: mov      r14d, edx
  0x0140e8dd: mov      edx, r8d
  0x0140e8e0: call     0x140e950
  0x0140e8e5: mov      eax, r14d
  0x0140e8e8: lea      rdx, [rax*8]
  0x0140e8f0: mov      rax, qword ptr [rdi + 8]
  0x0140e8f4: mov      rcx, qword ptr [rdx + rax]
  0x0140e8f8: mov      qword ptr [rbx + 0x10], rcx
  0x0140e8fc: mov      cl, 1
  0x0140e8fe: mov      rax, qword ptr [rdi + 8]
  0x0140e902: mov      qword ptr [rdx + rax], rbx
  0x0140e906: inc      dword ptr [rdi + 0x14]
  0x0140e909: mov      r9, qword ptr [rdi + 8]
  0x0140e90d: add      r9, rdx
  0x0140e910: mov      qword ptr [rsi], rbx
  0x0140e913: mov      rax, rsi
  0x0140e916: mov      qword ptr [rsi + 8], r9
  0x0140e91a: mov      byte ptr [rsi + 0x10], cl
  0x0140e91d: mov      rbx, qword ptr [rsp + 0x68]
  0x0140e922: mov      rbp, qword ptr [rsp + 0x70]
  0x0140e927: add      rsp, 0x30
  0x0140e92b: pop      r15
  0x0140e92d: pop      r14
  0x0140e92f: pop      r12
  0x0140e931: pop      rdi
  0x0140e932: pop      rsi
  0x0140e933: ret      
  0x0140e934: test     rbx, rbx
  0x0140e937: je       0x140e883
  0x0140e93d: xor      cl, cl
  0x0140e93f: jmp      0x140e910
  0x0140e941: int3     
  0x0140e942: int3     
  0x0140e943: int3     
  0x0140e944: int3     
  0x0140e945: int3     
  0x0140e946: int3     
  0x0140e947: int3     
  0x0140e948: int3     
  0x0140e949: int3     
  0x0140e94a: int3     
  0x0140e94b: int3     
  0x0140e94c: int3     
  0x0140e94d: int3     
  0x0140e94e: int3     
  0x0140e94f: int3     
  0x0140e950: mov      qword ptr [rsp + 8], rbx
  0x0140e955: mov      qword ptr [rsp + 0x10], rbp
  0x0140e95a: mov      qword ptr [rsp + 0x18], rsi
  0x0140e95f: mov      qword ptr [rsp + 0x20], rdi
  0x0140e964: push     r14
  0x0140e966: sub      rsp, 0x30
  0x0140e96a: mov      r14d, edx
  0x0140e96d: xor      r9d, r9d
  0x0140e970: mov      rdi, rcx
  0x0140e973: mov      byte ptr [rsp + 0x20], 1
  0x0140e978: mov      rcx, qword ptr [rcx + 0x28]
  0x0140e97c: lea      edx, [r14 + 1]
  0x0140e980: shl      rdx, 3
  0x0140e984: lea      r8d, [r9 + 8]
  0x0140e988: call     0x13fc9c0
  0x0140e98d: lea      rbx, [r14*8]
  0x0140e995: xor      edx, edx
  0x0140e997: mov      r8, rbx
  0x0140e99a: mov      rcx, rax
  0x0140e99d: mov      rsi, rax
  0x0140e9a0: mov      ebp, r14d
  0x0140e9a3: call     0x143eb66
  0x0140e9a8: xor      r10d, r10d
  0x0140e9ab: mov      qword ptr [rbx + rsi], 0xffffffffffffffff
  0x0140e9b3: cmp      dword ptr [rdi + 0x10], r10d
  0x0140e9b7: jbe      0x140ea50
  0x0140e9bd: nop      dword ptr [rax]
  0x0140e9c0: mov      rax, qword ptr [rdi + 8]
  0x0140e9c4: lea      r9, [r10*8]
  0x0140e9cc: mov      r8, qword ptr [r9 + rax]
  0x0140e9d0: test     r8, r8
  0x0140e9d3: je       0x140ea43
  0x0140e9d5: nop      word ptr [rax + rax]
  0x0140e9e0: mov      rcx, qword ptr [r8]
  0x0140e9e3: mov      eax, 0x811c9dc5
  0x0140e9e8: movzx    edx, word ptr [rcx]
  0x0140e9eb: add      rcx, 2
  0x0140e9ef: test     edx, edx
  0x0140e9f1: je       0x140ea14
  0x0140e9f3: nop      dword ptr [rax]
  0x0140e9f7: nop      word ptr [rax + rax]
  0x0140ea00: imul     eax, eax, 0x1000193
  0x0140ea06: lea      rcx, [rcx + 2]
  0x0140ea0a: xor      eax, edx
  0x0140ea0c: movzx    edx, word ptr [rcx - 2]
  0x0140ea10: test     edx, edx
  0x0140ea12: jne      0x140ea00
  0x0140ea14: mov      rcx, qword ptr [r8 + 0x10]
  0x0140ea18: mov      rdx, qword ptr [rdi + 8]
  0x0140ea1c: mov      qword ptr [r9 + rdx], rcx
  0x0140ea20: xor      edx, edx
  0x0140ea22: div      rbp
  0x0140ea25: mov      eax, edx
  0x0140ea27: lea      rcx, [rsi + rax*8]
  0x0140ea2b: mov      rax, qword ptr [rsi + rax*8]
  0x0140ea2f: mov      qword ptr [r8 + 0x10], rax
  0x0140ea33: mov      qword ptr [rcx], r8
  0x0140ea36: mov      rax, qword ptr [rdi + 8]
  0x0140ea3a: mov      r8, qword ptr [r9 + rax]
  0x0140ea3e: test     r8, r8
  0x0140ea41: jne      0x140e9e0
  0x0140ea43: inc      r10d
  0x0140ea46: cmp      r10d, dword ptr [rdi + 0x10]
  0x0140ea4a: jb       0x140e9c0
  0x0140ea50: mov      rbx, qword ptr [rsp + 0x40]
  0x0140ea55: mov      rbp, qword ptr [rsp + 0x48]
  0x0140ea5a: mov      qword ptr [rdi + 8], rsi
  0x0140ea5e: mov      rsi, qword ptr [rsp + 0x50]
  0x0140ea63: mov      dword ptr [rdi + 0x10], r14d
  0x0140ea67: mov      rdi, qword ptr [rsp + 0x58]
  0x0140ea6c: add      rsp, 0x30
  0x0140ea70: pop      r14
  0x0140ea72: ret      
  0x0140ea73: int3     
