; function start 0x140ef60
  0x0140ef60: mov      qword ptr [rsp + 0x20], r9
  0x0140ef65: mov      qword ptr [rsp + 0x18], r8
  0x0140ef6a: mov      qword ptr [rsp + 0x10], rdx
  0x0140ef6f: mov      qword ptr [rsp + 8], rcx
  0x0140ef74: push     rbp
  0x0140ef75: push     rbx
  0x0140ef76: push     rsi
  0x0140ef77: push     rdi
  0x0140ef78: push     r12
  0x0140ef7a: push     r13
  0x0140ef7c: push     r14
  0x0140ef7e: push     r15
  0x0140ef80: lea      rbp, [rsp - 0x638]
  0x0140ef88: sub      rsp, 0x738
  0x0140ef8f: mov      qword ptr [rbp + 0xd0], 0xfffffffffffffffe
  0x0140ef9a: mov      r15, rdx
  0x0140ef9d: mov      r13, rcx
  0x0140efa0: mov      byte ptr [rsp + 0x5c], 0
  0x0140efa5: xorps    xmm0, xmm0
  0x0140efa8: movdqu   xmmword ptr [rbp - 0x68], xmm0
  0x0140efad: xor      ebx, ebx
  0x0140efaf: mov      edi, ebx
  0x0140efb1: mov      qword ptr [rsp + 0x40], rbx
  0x0140efb6: mov      qword ptr [rbp - 0x58], rbx
  0x0140efba: mov      rsi, qword ptr [rcx]
  0x0140efbd: mov      qword ptr [rsp + 0x48], rsi
  0x0140efc2: mov      qword ptr [rbp - 0x50], rsi
  0x0140efc6: mov      dword ptr [rbp - 0x48], ebx
  0x0140efc9: mov      rcx, qword ptr [rcx + 0x70]
  0x0140efcd: mov      rax, qword ptr [rcx]
  0x0140efd0: call     qword ptr [rax + 0x10]
  0x0140efd3: mov      r14, rax
  0x0140efd6: mov      qword ptr [rsp + 0x50], rax
  0x0140efdb: mov      qword ptr [rbp + 0xd8], rax
  0x0140efe2: test     rax, rax
  0x0140efe5: je       0x140eff1
  0x0140efe7: mov      rdx, qword ptr [rax]
  0x0140efea: mov      rcx, rax
  0x0140efed: call     qword ptr [rdx + 8]
  0x0140eff0: nop      
  0x0140eff1: test     r14, r14
  0x0140eff4: je       0x1410551
  0x0140effa: mov      dword ptr [rsp + 0x58], ebx
  0x0140effe: xorps    xmm0, xmm0
  0x0140f001: movdqu   xmmword ptr [rsp + 0x60], xmm0
  0x0140f007: lea      rdx, [rip + 0x9e40d2]
  0x0140f00e: lea      rcx, [rbp - 0x70]
  0x0140f012: call     0x6a630
  0x0140f017: mov      rdx, rax
  0x0140f01a: lea      rcx, [rsp + 0x70]
  0x0140f01f: call     0x6a630
  0x0140f024: xor      r12d, r12d
  0x0140f027: mov      qword ptr [rsp + 0x70], r12
  0x0140f02c: mov      rax, qword ptr [r14]
  0x0140f02f: mov      rcx, r14
  0x0140f032: call     qword ptr [rax + 0x38]
  0x0140f035: mov      rbx, rax
  0x0140f038: lea      rax, [rip + 0xc4b749]
  0x0140f03f: mov      qword ptr [rsp + 0x30], rax
  0x0140f044: mov      rcx, qword ptr [r13]
  0x0140f048: mov      qword ptr [rsp + 0x28], rcx
  0x0140f04d: mov      byte ptr [rsp + 0x20], r12b
  0x0140f052: xor      r9d, r9d
  0x0140f055: xor      r8d, r8d
  0x0140f058: xor      edx, edx
  0x0140f05a: lea      rcx, [rbp + 0x70]
  0x0140f05e: call     0x13f08f0
  0x0140f063: nop      
  0x0140f064: movss    xmm2, dword ptr [rip + 0x9e23fc]
  0x0140f06c: lea      edx, [r12 + 1]
  0x0140f071: lea      rcx, [rbp + 0x70]
  0x0140f075: call     0x13f0ea0
  0x0140f07a: mov      rdx, rbx
  0x0140f07d: lea      rcx, [rbp + 0x70]
  0x0140f081: call     0x13f0f90
  0x0140f086: test     al, al
  0x0140f088: jne      0x140f0c7
  0x0140f08a: mov      dword ptr [r13 + 0x3e8], 0xd06b000c
  0x0140f095: mov      r10, qword ptr [r13 + 0x3d8]
  0x0140f09c: test     r10, r10
  0x0140f09f: je       0x1410492
  0x0140f0a5: mov      rax, qword ptr [r13 + 0x3e0]
  0x0140f0ac: mov      qword ptr [rsp + 0x20], rax
  0x0140f0b1: xor      r9d, r9d
  0x0140f0b4: xor      r8d, r8d
  0x0140f0b7: mov      rdx, r15
  0x0140f0ba: mov      ecx, 0xd06b000c
  0x0140f0bf: call     r10
  0x0140f0c2: jmp      0x1410492
  0x0140f0c7: mov      rax, qword ptr [r14]
  0x0140f0ca: mov      r9, qword ptr [rax + 0x60]
  0x0140f0ce: mov      rax, qword ptr [rbp + 0x88]
  0x0140f0d5: test     rax, rax
  0x0140f0d8: je       0x140f0e0
  0x0140f0da: mov      rdx, qword ptr [rax + 0x10]
  0x0140f0de: jmp      0x140f0e3
  0x0140f0e0: mov      rdx, r12
  0x0140f0e3: mov      r8, rbx
  0x0140f0e6: mov      rcx, r14
  0x0140f0e9: call     r9
  0x0140f0ec: cmp      rbx, rax
  0x0140f0ef: je       0x140f12e
  0x0140f0f1: mov      dword ptr [r13 + 0x3e8], 0xd06b000d
  0x0140f0fc: mov      r10, qword ptr [r13 + 0x3d8]
  0x0140f103: test     r10, r10
  0x0140f106: je       0x1410492
  0x0140f10c: mov      rax, qword ptr [r13 + 0x3e0]
  0x0140f113: mov      qword ptr [rsp + 0x20], rax
  0x0140f118: xor      r9d, r9d
  0x0140f11b: xor      r8d, r8d
  0x0140f11e: mov      rdx, r15
  0x0140f121: mov      ecx, 0xd06b000d
  0x0140f126: call     r10
  0x0140f129: jmp      0x1410492
  0x0140f12e: xor      r9d, r9d
  0x0140f131: mov      r8d, 0x103
  0x0140f137: lea      rdx, [rbp + 0x310]
  0x0140f13e: lea      rcx, [rbp + 0x70]
  0x0140f142: call     0x13f1480
  0x0140f147: test     eax, eax
  0x0140f149: js       0x14104ed
  0x0140f14f: movzx    ebx, byte ptr [rbp + 0x680]
  0x0140f156: movzx    edi, byte ptr [rbp + 0x680]
  0x0140f15d: mov      r12, qword ptr [rbp - 0x60]
  0x0140f161: mov      qword ptr [rsp + 0x78], r12
  0x0140f166: nop      word ptr [rax + rax]
  0x0140f170: mov      r9, 0xffffffffffffffff
  0x0140f177: mov      r8d, 0x104
  0x0140f17d: lea      rdx, [rbp + 0x310]
  0x0140f184: lea      rcx, [rbp + 0x420]
  0x0140f18b: call     0x13ca0b0
  0x0140f190: movsxd   rcx, eax
  0x0140f193: mov      r15d, dword ptr [rsp + 0x58]
  0x0140f198: inc      r15d
  0x0140f19b: mov      dword ptr [rsp + 0x58], r15d
  0x0140f1a0: mov      rdx, qword ptr [rsp + 0x60]
  0x0140f1a5: mov      qword ptr [rbp - 0x78], rdx
  0x0140f1a9: mov      qword ptr [rsp + 0x68], rdx
  0x0140f1ae: lea      r14, [rbp + 0x420]
  0x0140f1b5: lea      r8, [rbp + 0x420]
  0x0140f1bc: lea      r8, [r8 + rcx*2]
  0x0140f1c0: mov      qword ptr [rbp - 0x80], r8
  0x0140f1c4: lea      rax, [rbp + 0x420]
  0x0140f1cb: cmp      rax, r8
  0x0140f1ce: jae      0x140f4af
  0x0140f1d4: lea      rcx, [rbp + 0x420]
  0x0140f1db: lea      rsi, [rbp + 0x420]
  0x0140f1e2: mov      r10d, 0x100
  0x0140f1e8: nop      dword ptr [rax + rax]
  0x0140f1f0: movzx    r15d, word ptr [r14]
  0x0140f1f4: cmp      r15w, r10w
  0x0140f1f8: jae      0x140f21c
  0x0140f1fa: movzx    eax, r15w
  0x0140f1fe: lea      r9, [rip - 0x140f205]
  0x0140f205: movzx    eax, byte ptr [rax + r9 + 0x28056b0]
  0x0140f20e: and      eax, 6
  0x0140f211: je       0x140f21c
  0x0140f213: lea      r14, [rcx + 2]
  0x0140f217: jmp      0x140f48f
  0x0140f21c: cmp      r15w, 0x23
  0x0140f221: je       0x140f49e
  0x0140f227: cmp      r15w, 0x22
  0x0140f22c: je       0x140f381
  0x0140f232: cmp      r15w, 0x27
  0x0140f237: je       0x140f381
  0x0140f23d: cmp      rdx, qword ptr [rsp + 0x70]
  0x0140f242: jae      0x140f255
  0x0140f244: lea      rax, [rdx + 8]
  0x0140f248: mov      qword ptr [rsp + 0x68], rax
  0x0140f24d: mov      qword ptr [rdx], r14
  0x0140f250: jmp      0x140f312
  0x0140f255: mov      rax, rdx
  0x0140f258: sub      rax, qword ptr [rsp + 0x60]
  0x0140f25d: sar      rax, 3
  0x0140f261: test     eax, eax
  0x0140f263: je       0x140f272
  0x0140f265: lea      r12d, [rax + rax]
  0x0140f269: test     r12d, r12d
  0x0140f26c: jne      0x140f278
  0x0140f26e: xor      eax, eax
  0x0140f270: jmp      0x140f295
  0x0140f272: mov      r12d, 1
  0x0140f278: mov      edx, r12d
  0x0140f27b: shl      rdx, 3
  0x0140f27f: xor      r8d, r8d
  0x0140f282: lea      rcx, [rsp + 0x70]
  0x0140f287: call     0x6aaf0
  0x0140f28c: mov      rdx, qword ptr [rsp + 0x68]
  0x0140f291: mov      qword ptr [rbp - 0x78], rdx
  0x0140f295: mov      r15, rax
  0x0140f298: mov      r13, qword ptr [rsp + 0x60]
  0x0140f29d: cmp      r13, rdx
  0x0140f2a0: je       0x140f2c4
  0x0140f2a2: mov      r8, rdx
  0x0140f2a5: sub      r8, r13
  0x0140f2a8: mov      rdx, qword ptr [rsp + 0x60]
  0x0140f2ad: mov      rcx, r15
  0x0140f2b0: call     0x143eb60
  0x0140f2b5: mov      rcx, qword ptr [rbp - 0x78]
  0x0140f2b9: sub      rcx, r13
  0x0140f2bc: sar      rcx, 3
  0x0140f2c0: lea      rax, [rax + rcx*8]
  0x0140f2c4: mov      qword ptr [rax], r14
  0x0140f2c7: lea      r13, [rax + 8]
  0x0140f2cb: mov      rax, qword ptr [rsp + 0x70]
  0x0140f2d0: mov      rdx, qword ptr [rsp + 0x60]
  0x0140f2d5: sub      rax, rdx
  0x0140f2d8: sar      rax, 3
  0x0140f2dc: test     rdx, rdx
  0x0140f2df: je       0x140f2f2
  0x0140f2e1: mov      r8d, eax
  0x0140f2e4: shl      r8, 3
  0x0140f2e8: lea      rcx, [rsp + 0x70]
  0x0140f2ed: call     0x6ab30
  0x0140f2f2: mov      qword ptr [rsp + 0x60], r15
  0x0140f2f7: mov      qword ptr [rsp + 0x68], r13
  0x0140f2fc: mov      eax, r12d
  0x0140f2ff: lea      rcx, [r15 + rax*8]
  0x0140f303: mov      qword ptr [rsp + 0x70], rcx
  0x0140f308: mov      r8, qword ptr [rbp - 0x80]
  0x0140f30c: mov      r10d, 0x100
  0x0140f312: cmp      r14, r8
  0x0140f315: jae      0x140f372
  0x0140f317: nop      word ptr [rax + rax]
  0x0140f320: movzx    ecx, word ptr [r14]
  0x0140f324: cmp      cx, r10w
  0x0140f328: jae      0x140f341
  0x0140f32a: movzx    eax, cx
  0x0140f32d: lea      rdx, [rip - 0x140f334]
  0x0140f334: movzx    eax, byte ptr [rax + rdx + 0x28056b0]
  0x0140f33c: and      eax, 6
  0x0140f33f: jne      0x140f362
  0x0140f341: cmp      cx, 0x23
  0x0140f345: je       0x140f362
  0x0140f347: lea      r14, [rsi + 2]
  0x0140f34b: mov      rsi, r14
  0x0140f34e: cmp      r14, r8
  0x0140f351: jb       0x140f320
  0x0140f353: xor      eax, eax
  0x0140f355: mov      word ptr [r14], ax
  0x0140f359: lea      r14, [r14 + 2]
  0x0140f35d: jmp      0x140f486
  0x0140f362: cmp      rsi, r8
  0x0140f365: jae      0x140f372
  0x0140f367: cmp      word ptr [r14], 0x23
  0x0140f36c: je       0x140f527
  0x0140f372: xor      eax, eax
  0x0140f374: mov      word ptr [r14], ax
  0x0140f378: lea      r14, [rsi + 2]
  0x0140f37c: jmp      0x140f486
  0x0140f381: lea      rsi, [rcx + 2]
  0x0140f385: cmp      rdx, qword ptr [rsp + 0x70]
  0x0140f38a: jae      0x140f39d
  0x0140f38c: lea      rax, [rdx + 8]
  0x0140f390: mov      qword ptr [rsp + 0x68], rax
  0x0140f395: mov      qword ptr [rdx], rsi
  0x0140f398: jmp      0x140f45a
  0x0140f39d: mov      rax, rdx
  0x0140f3a0: sub      rax, qword ptr [rsp + 0x60]
  0x0140f3a5: sar      rax, 3
  0x0140f3a9: test     eax, eax
  0x0140f3ab: je       0x140f3ba
  0x0140f3ad: lea      r12d, [rax + rax]
  0x0140f3b1: test     r12d, r12d
  0x0140f3b4: jne      0x140f3c0
  0x0140f3b6: xor      eax, eax
  0x0140f3b8: jmp      0x140f3dd
  0x0140f3ba: mov      r12d, 1
  0x0140f3c0: mov      edx, r12d
  0x0140f3c3: shl      rdx, 3
  0x0140f3c7: xor      r8d, r8d
  0x0140f3ca: lea      rcx, [rsp + 0x70]
  0x0140f3cf: call     0x6aaf0
  0x0140f3d4: mov      rdx, qword ptr [rsp + 0x68]
  0x0140f3d9: mov      qword ptr [rbp - 0x78], rdx
  0x0140f3dd: mov      r14, rax
  0x0140f3e0: mov      r13, qword ptr [rsp + 0x60]
  0x0140f3e5: cmp      r13, rdx
  0x0140f3e8: je       0x140f40c
  0x0140f3ea: mov      r8, rdx
  0x0140f3ed: sub      r8, r13
  0x0140f3f0: mov      rdx, qword ptr [rsp + 0x60]
  0x0140f3f5: mov      rcx, r14
  0x0140f3f8: call     0x143eb60
  0x0140f3fd: mov      rcx, qword ptr [rbp - 0x78]
  0x0140f401: sub      rcx, r13
  0x0140f404: sar      rcx, 3
  0x0140f408: lea      rax, [rax + rcx*8]
  0x0140f40c: mov      qword ptr [rax], rsi
  0x0140f40f: lea      r13, [rax + 8]
  0x0140f413: mov      rax, qword ptr [rsp + 0x70]
  0x0140f418: mov      rdx, qword ptr [rsp + 0x60]
  0x0140f41d: sub      rax, rdx
  0x0140f420: sar      rax, 3
  0x0140f424: test     rdx, rdx
  0x0140f427: je       0x140f43a
  0x0140f429: mov      r8d, eax
  0x0140f42c: shl      r8, 3
  0x0140f430: lea      rcx, [rsp + 0x70]
  0x0140f435: call     0x6ab30
  0x0140f43a: mov      qword ptr [rsp + 0x60], r14
  0x0140f43f: mov      qword ptr [rsp + 0x68], r13
  0x0140f444: mov      eax, r12d
  0x0140f447: lea      rcx, [r14 + rax*8]
  0x0140f44b: mov      qword ptr [rsp + 0x70], rcx
  0x0140f450: mov      r8, qword ptr [rbp - 0x80]
  0x0140f454: mov      r10d, 0x100
  0x0140f45a: mov      r14, rsi
  0x0140f45d: cmp      rsi, r8
  0x0140f460: jae      0x140f47d
  0x0140f462: mov      rax, rsi
  0x0140f465: mov      r14, rax
  0x0140f468: cmp      word ptr [rsi], r15w
  0x0140f46c: je       0x140f47d
  0x0140f46e: lea      rsi, [rax + 2]
  0x0140f472: mov      rax, rsi
  0x0140f475: mov      r14, rsi
  0x0140f478: cmp      rsi, r8
  0x0140f47b: jb       0x140f465
  0x0140f47d: xor      eax, eax
  0x0140f47f: mov      word ptr [rsi], ax
  0x0140f482: add      r14, 2
  0x0140f486: mov      rdx, qword ptr [rsp + 0x68]
  0x0140f48b: mov      qword ptr [rbp - 0x78], rdx
  0x0140f48f: mov      rcx, r14
  0x0140f492: mov      rsi, r14
  0x0140f495: cmp      r14, r8
  0x0140f498: jb       0x140f1f0
  0x0140f49e: mov      r15d, dword ptr [rsp + 0x58]
  0x0140f4a3: mov      r12, qword ptr [rsp + 0x78]
  0x0140f4a8: mov      r13, qword ptr [rbp + 0x680]
  0x0140f4af: xor      r10d, r10d
  0x0140f4b2: mov      rsi, rdx
  0x0140f4b5: mov      rdx, qword ptr [rsp + 0x60]
  0x0140f4ba: sub      rsi, rdx
  0x0140f4bd: sar      rsi, 3
  0x0140f4c1: cmp      esi, 1
  0x0140f4c4: jb       0x141025a
  0x0140f4ca: lea      r9, [rip + 0xc4b2df]
  0x0140f4d1: mov      r14, qword ptr [rdx]
  0x0140f4d4: mov      r8, r14
  0x0140f4d7: lea      r11, [rip - 0x140f4de]
  0x0140f4de: nop      
  0x0140f4e0: movzx    edx, word ptr [r8]
  0x0140f4e4: lea      r8, [r8 + 2]
  0x0140f4e8: mov      eax, 0x100
  0x0140f4ed: cmp      dx, ax
  0x0140f4f0: jae      0x140f4fe
  0x0140f4f2: movzx    eax, dx
  0x0140f4f5: movzx    edx, byte ptr [rax + r11 + 0x28057b0]
  0x0140f4fe: movzx    eax, byte ptr [r9]
  0x0140f502: inc      r9
  0x0140f505: movzx    eax, byte ptr [rax + r11 + 0x28057b0]
  0x0140f50e: cmp      dx, ax
  0x0140f511: jne      0x140f54d
  0x0140f513: test     dx, dx
  0x0140f516: jne      0x140f4e0
  0x0140f518: mov      rax, qword ptr [rbp + 0x698]
  0x0140f51f: mov      byte ptr [rax], 1
  0x0140f522: jmp      0x141025a
  0x0140f527: xor      r10d, r10d
  0x0140f52a: mov      word ptr [r14], r10w
  0x0140f52e: mov      rdx, qword ptr [rsp + 0x68]
  0x0140f533: mov      qword ptr [rbp - 0x78], rdx
  0x0140f537: mov      r13, qword ptr [rbp + 0x680]
  0x0140f53e: mov      r12, qword ptr [rsp + 0x78]
  0x0140f543: mov      r15d, dword ptr [rsp + 0x58]
  0x0140f548: jmp      0x140f4b2
  0x0140f54d: lea      r9, [rip + 0xc4b268]
  0x0140f554: mov      r8, r14
  0x0140f557: nop      word ptr [rax + rax]
  0x0140f560: movzx    edx, word ptr [r8]
  0x0140f564: lea      r8, [r8 + 2]
  0x0140f568: mov      eax, 0x100
  0x0140f56d: cmp      dx, ax
  0x0140f570: jae      0x140f57e
  0x0140f572: movzx    eax, dx
  0x0140f575: movzx    edx, byte ptr [rax + r11 + 0x28057b0]
  0x0140f57e: movzx    eax, byte ptr [r9]
  0x0140f582: inc      r9
  0x0140f585: movzx    eax, byte ptr [rax + r11 + 0x28057b0]
  0x0140f58e: cmp      dx, ax
  0x0140f591: jne      0x140f59d
  0x0140f593: test     dx, dx
  0x0140f596: jne      0x140f560
  0x0140f598: mov      ecx, r10d
  0x0140f59b: jmp      0x140f5a2
  0x0140f59d: movzx    ecx, dx
  0x0140f5a0: sub      ecx, eax
  0x0140f5a2: test     ecx, ecx
  0x0140f5a4: jne      0x140f7d8
  0x0140f5aa: cmp      esi, 2
  0x0140f5ad: jb       0x1410354
  0x0140f5b3: cmp      esi, 3
  0x0140f5b6: ja       0x1410313
  0x0140f5bc: mov      rax, qword ptr [rsp + 0x60]
  0x0140f5c1: mov      rsi, qword ptr [rax + 8]
  0x0140f5c5: lea      rdx, [rip + 0xbfb494]
  0x0140f5cc: mov      rcx, rsi
  0x0140f5cf: call     0x1410aa0
  0x0140f5d4: test     eax, eax
  0x0140f5d6: jne      0x140f5e4
  0x0140f5d8: mov      r12d, 0xffffffff
  0x0140f5de: mov      r15, qword ptr [rbp - 0x78]
  0x0140f5e2: jmp      0x140f605
  0x0140f5e4: xor      r8d, r8d
  0x0140f5e7: lea      rdx, [rbp - 0x30]
  0x0140f5eb: mov      rcx, rsi
  0x0140f5ee: call     0x13caeb0
  0x0140f5f3: mov      r12d, eax
  0x0140f5f6: cmp      qword ptr [rbp - 0x30], rsi
  0x0140f5fa: je       0x14102d2
  0x0140f600: mov      r15, qword ptr [rsp + 0x68]
  0x0140f605: lea      rsi, [rip + 0xc4af74]
  0x0140f60c: mov      rdx, qword ptr [rsp + 0x60]
  0x0140f611: sub      r15, rdx
  0x0140f614: sar      r15, 3
  0x0140f618: cmp      r15d, 2
  0x0140f61c: jbe      0x140f62c
  0x0140f61e: mov      rsi, qword ptr [rdx + 0x10]
  0x0140f622: cmp      word ptr [rsi], 0
  0x0140f626: je       0x141028f
  0x0140f62c: mov      edx, 5
  0x0140f631: mov      rcx, rsi
  0x0140f634: call     0x1411620
  0x0140f639: test     al, al
  0x0140f63b: jne      0x141028f
  0x0140f641: mov      r8d, 0x5c
  0x0140f647: lea      rdx, [rbp + 0x100]
  0x0140f64e: mov      rcx, rsi
  0x0140f651: call     0x1410df0
  0x0140f656: lea      rsi, [rbp + 0x100]
  0x0140f65d: cmp      word ptr [rbp + 0x100], 0x2e
  0x0140f665: jne      0x140f6d5
  0x0140f667: nop      word ptr [rax + rax]
  0x0140f670: movzx    eax, word ptr [rsi + 2]
  0x0140f674: cmp      ax, 0x5c
  0x0140f678: je       0x140f686
  0x0140f67a: cmp      ax, 0x2f
  0x0140f67e: je       0x140f686
  0x0140f680: cmp      ax, 0x3a
  0x0140f684: jne      0x140f6d5
  0x0140f686: add      rsi, 4
  0x0140f68a: movzx    ecx, word ptr [rsi]
  0x0140f68d: cmp      cx, 0x2e
  0x0140f691: je       0x140f670
  0x0140f693: xor      eax, eax
  0x0140f695: mov      r14d, eax
  0x0140f698: mov      rdx, rsi
  0x0140f69b: test     cx, cx
  0x0140f69e: je       0x140f730
  0x0140f6a4: mov      r14d, eax
  0x0140f6a7: cmp      cx, 0x2e
  0x0140f6ab: jne      0x140f70d
  0x0140f6ad: cmp      word ptr [rsi + 2], cx
  0x0140f6b1: jne      0x140f722
  0x0140f6b3: cmp      word ptr [rsi + 4], cx
  0x0140f6b7: jne      0x140f722
  0x0140f6b9: movzx    eax, word ptr [rsi + 6]
  0x0140f6bd: cmp      ax, 0x5c
  0x0140f6c1: je       0x140f6cf
  0x0140f6c3: cmp      ax, 0x2f
  0x0140f6c7: je       0x140f6cf
  0x0140f6c9: cmp      ax, 0x3a
  0x0140f6cd: jne      0x140f722
  0x0140f6cf: add      r14d, 4
  0x0140f6d3: jmp      0x140f722
  0x0140f6d5: movzx    ecx, word ptr [rsi]
  0x0140f6d8: cmp      cx, 0x2e
  0x0140f6dc: jne      0x140f693
  0x0140f6de: cmp      word ptr [rsi + 2], cx
  0x0140f6e2: jne      0x140f693
  0x0140f6e4: movzx    eax, word ptr [rsi + 4]
  0x0140f6e8: cmp      ax, 0x5c
  0x0140f6ec: je       0x141028f
  0x0140f6f2: cmp      ax, 0x2f
  0x0140f6f6: je       0x141028f
  0x0140f6fc: cmp      ax, 0x3a
  0x0140f700: je       0x141028f
  0x0140f706: mov      rdx, rsi
  0x0140f709: xor      eax, eax
  0x0140f70b: jmp      0x140f6a4
  0x0140f70d: cmp      cx, 0x2a
  0x0140f711: jne      0x140f719
  0x0140f713: add      r14d, 2
  0x0140f717: jmp      0x140f722
  0x0140f719: cmp      cx, 0x3f
  0x0140f71d: jne      0x140f722
  0x0140f71f: inc      r14d
  0x0140f722: add      rdx, 2
  0x0140f726: cmp      word ptr [rdx], 0
  0x0140f72a: jne      0x140f6a7
  0x0140f730: lea      rcx, [r13 + 8]
  0x0140f734: mov      r8b, 1
  0x0140f737: mov      edx, 0x18
  0x0140f73c: call     0x13fc960
  0x0140f741: mov      r15, rax
  0x0140f744: xor      eax, eax
  0x0140f746: mov      dword ptr [r15], eax
  0x0140f749: mov      qword ptr [r15 + 8], rax
  0x0140f74d: mov      rcx, qword ptr [rsp + 0x78]
  0x0140f752: cmp      qword ptr [rbp - 0x68], rcx
  0x0140f756: je       0x140f760
  0x0140f758: mov      rcx, qword ptr [rcx - 8]
  0x0140f75c: mov      qword ptr [r15 + 8], rcx
  0x0140f760: neg      r14d
  0x0140f763: mov      dword ptr [r15 + 0x10], r14d
  0x0140f767: mov      dword ptr [r15 + 4], r12d
  0x0140f76b: mov      byte ptr [r15 + 0x14], al
  0x0140f76f: mov      byte ptr [r15 + 0x16], al
  0x0140f773: mov      qword ptr [rbp + 8], rax
  0x0140f777: mov      qword ptr [rbp + 0x10], rax
  0x0140f77b: mov      qword ptr [rbp + 0x18], rax
  0x0140f77f: mov      qword ptr [rbp + 0x20], rax
  0x0140f783: lea      rdx, [rbp + 8]
  0x0140f787: mov      r12, qword ptr [rbp + 0x690]
  0x0140f78e: mov      rcx, r12
  0x0140f791: call     0x1410c40
  0x0140f796: mov      rax, qword ptr [r12 + 8]
  0x0140f79b: mov      qword ptr [rax - 0x20], r15
  0x0140f79f: mov      rdx, rsi
  0x0140f7a2: mov      rcx, r13
  0x0140f7a5: call     0x1410a50
  0x0140f7aa: mov      rcx, qword ptr [r12 + 8]
  0x0140f7af: mov      qword ptr [rcx - 0x18], rax
  0x0140f7b3: mov      rax, qword ptr [r12 + 8]
  0x0140f7b8: xor      r14d, r14d
  0x0140f7bb: mov      qword ptr [rax - 0x10], r14
  0x0140f7bf: mov      rax, qword ptr [r12 + 8]
  0x0140f7c4: mov      word ptr [rax - 8], r14w
  0x0140f7c9: mov      rax, qword ptr [r12 + 8]
  0x0140f7ce: mov      word ptr [rax - 6], r14w
  0x0140f7d3: jmp      0x141025a
  0x0140f7d8: lea      rdx, [rip + 0xa5be11]
  0x0140f7df: mov      rcx, r14
  0x0140f7e2: call     0x1410aa0
  0x0140f7e7: test     eax, eax
  0x0140f7e9: jne      0x140f828
  0x0140f7eb: cmp      esi, 2
  0x0140f7ee: jne      0x1410354
  0x0140f7f4: mov      rcx, qword ptr [rsp + 0x60]
  0x0140f7f9: xor      r8d, r8d
  0x0140f7fc: lea      rdx, [rbp - 0x28]
  0x0140f800: mov      rcx, qword ptr [rcx + 8]
  0x0140f804: call     0x13cadf0
  0x0140f809: mov      rcx, qword ptr [rsp + 0x60]
  0x0140f80e: mov      rdx, qword ptr [rcx + 8]
  0x0140f812: cmp      qword ptr [rbp - 0x28], rdx
  0x0140f816: je       0x14102d2
  0x0140f81c: mov      dword ptr [r13 + 0x3bc], eax
  0x0140f823: jmp      0x141025a
  0x0140f828: lea      rdx, [rip + 0xc4af99]
  0x0140f82f: mov      rcx, r14
  0x0140f832: call     0x1410aa0
  0x0140f837: test     eax, eax
  0x0140f839: jne      0x140fb7a
  0x0140f83f: cmp      byte ptr [rsp + 0x5c], al
  0x0140f843: jne      0x140f986
  0x0140f849: mov      byte ptr [rsp + 0x5c], 1
  0x0140f84e: lea      rsi, [r13 + 8]
  0x0140f852: mov      r8b, 1
  0x0140f855: lea      edx, [rax + 0x30]
  0x0140f858: mov      rcx, rsi
  0x0140f85b: call     0x13fc960
  0x0140f860: mov      r14, rax
  0x0140f863: mov      qword ptr [rbp - 0x80], rax
  0x0140f867: test     rax, rax
  0x0140f86a: je       0x140f899
  0x0140f86c: mov      dword ptr [rax + 0x18], 0x3f800000
  0x0140f873: mov      dword ptr [rax + 0x1c], 0x40000000
  0x0140f87a: xor      eax, eax
  0x0140f87c: mov      qword ptr [r14 + 0x28], rsi
  0x0140f880: mov      qword ptr [r14 + 0x10], 1
  0x0140f888: lea      rcx, [rip + 0x13f7761]
  0x0140f88f: mov      qword ptr [r14 + 8], rcx
  0x0140f893: mov      dword ptr [r14 + 0x20], eax
  0x0140f897: jmp      0x140f89c
  0x0140f899: mov      r14, rax
  0x0140f89c: mov      rcx, qword ptr [r13 + 0x3d0]
  0x0140f8a3: mov      edx, dword ptr [rcx + 0x10]
  0x0140f8a6: mov      rax, qword ptr [rcx + 8]
  0x0140f8aa: mov      r15, qword ptr [rax + rdx*8]
  0x0140f8ae: lea      rdx, [rbp + 0xf0]
  0x0140f8b5: call     0x1410b00
  0x0140f8ba: mov      rsi, rax
  0x0140f8bd: mov      r8, qword ptr [rax + 8]
  0x0140f8c1: mov      rdx, qword ptr [rax]
  0x0140f8c4: xor      eax, eax
  0x0140f8c6: cmp      rdx, r15
  0x0140f8c9: je       0x140f8f4
  0x0140f8cb: nop      dword ptr [rax + rax]
  0x0140f8d0: mov      rcx, qword ptr [rdx + 0x10]
  0x0140f8d4: mov      rdx, rcx
  0x0140f8d7: test     rcx, rcx
  0x0140f8da: jne      0x140f8ec
  0x0140f8dc: nop      dword ptr [rax]
  0x0140f8e0: add      r8, 8
  0x0140f8e4: mov      rdx, qword ptr [r8]
  0x0140f8e7: test     rdx, rdx
  0x0140f8ea: je       0x140f8e0
  0x0140f8ec: inc      rax
  0x0140f8ef: cmp      rdx, r15
  0x0140f8f2: jne      0x140f8d0
  0x0140f8f4: lea      rcx, [r14 + 0x18]
  0x0140f8f8: mov      dword ptr [rsp + 0x20], eax
  0x0140f8fc: mov      r9d, dword ptr [r14 + 0x14]
  0x0140f900: mov      r8d, dword ptr [r14 + 0x10]
  0x0140f904: lea      rdx, [rbp - 0x40]
  0x0140f908: call     0x13d95b0
  0x0140f90d: cmp      byte ptr [rbp - 0x40], 0
  0x0140f911: je       0x140f91e
  0x0140f913: mov      edx, dword ptr [rbp - 0x3c]
  0x0140f916: mov      rcx, r14
  0x0140f919: call     0x140e950
  0x0140f91e: mov      rcx, qword ptr [rsi]
  0x0140f921: cmp      rcx, r15
  0x0140f924: je       0x140f978
  0x0140f926: nop      word ptr [rax + rax]
  0x0140f930: mov      r9, rcx
  0x0140f933: movzx    r8d, bl
  0x0140f937: lea      rdx, [rbp - 0x18]
  0x0140f93b: mov      rcx, r14
  0x0140f93e: call     0x140d0a0
  0x0140f943: mov      rax, qword ptr [rsi]
  0x0140f946: mov      rcx, qword ptr [rax + 0x10]
  0x0140f94a: mov      qword ptr [rsi], rcx
  0x0140f94d: test     rcx, rcx
  0x0140f950: jne      0x140f973
  0x0140f952: mov      rax, qword ptr [rsi + 8]
  0x0140f956: nop      word ptr [rax + rax]
  0x0140f960: add      rax, 8
  0x0140f964: mov      qword ptr [rsi + 8], rax
  0x0140f968: mov      rcx, qword ptr [rax]
  0x0140f96b: mov      qword ptr [rsi], rcx
  0x0140f96e: test     rcx, rcx
  0x0140f971: je       0x140f960
  0x0140f973: cmp      rcx, r15
  0x0140f976: jne      0x140f930
  0x0140f978: mov      qword ptr [r13 + 0x3d0], r14
  0x0140f97f: mov      r15, qword ptr [rsp + 0x68]
  0x0140f984: jmp      0x140f98a
  0x0140f986: mov      r15, qword ptr [rbp - 0x78]
  0x0140f98a: mov      rsi, r15
  0x0140f98d: mov      rdx, qword ptr [rsp + 0x60]
  0x0140f992: sub      rsi, rdx
  0x0140f995: sar      rsi, 3
  0x0140f999: cmp      esi, 2
  0x0140f99c: jb       0x14103d8
  0x0140f9a2: mov      r12d, 0xffffffff
  0x0140f9a8: mov      r14, qword ptr [rdx + 8]
  0x0140f9ac: lea      rdx, [rip + 0xbfb0ad]
  0x0140f9b3: mov      rcx, r14
  0x0140f9b6: call     0x1410aa0
  0x0140f9bb: test     eax, eax
  0x0140f9bd: jne      0x140f9ca
  0x0140f9bf: cmp      esi, 2
  0x0140f9c2: je       0x141025a
  0x0140f9c8: jmp      0x140f9eb
  0x0140f9ca: xor      r8d, r8d
  0x0140f9cd: lea      rdx, [rbp - 0x20]
  0x0140f9d1: mov      rcx, r14
  0x0140f9d4: call     0x13caeb0
  0x0140f9d9: mov      r12d, eax
  0x0140f9dc: cmp      qword ptr [rbp - 0x20], r14
  0x0140f9e0: je       0x1410395
  0x0140f9e6: mov      r15, qword ptr [rsp + 0x68]
  0x0140f9eb: mov      r14d, 2
  0x0140f9f1: mov      rcx, r15
  0x0140f9f4: sub      rcx, qword ptr [rsp + 0x60]
  0x0140f9f9: sar      rcx, 3
  0x0140f9fd: cmp      ecx, r14d
  0x0140fa00: jbe      0x141025a
  0x0140fa06: nop      word ptr [rax + rax]
  0x0140fa10: mov      ecx, r14d
  0x0140fa13: mov      rax, qword ptr [rsp + 0x60]
  0x0140fa18: mov      r11, qword ptr [rax + rcx*8]
  0x0140fa1c: mov      rcx, r11
  0x0140fa1f: cmp      word ptr [r11], 0x2e
  0x0140fa24: jne      0x140fa2d
  0x0140fa26: lea      rcx, [r11 + 2]
  0x0140fa2a: mov      r11, rcx
  0x0140fa2d: cmp      r12d, -1
  0x0140fa31: jne      0x140fb2a
  0x0140fa37: mov      rsi, qword ptr [r13 + 0x3d0]
  0x0140fa3e: mov      eax, 0x811c9dc5
  0x0140fa43: movzx    edx, word ptr [rcx]
  0x0140fa46: add      rcx, 2
  0x0140fa4a: test     edx, edx
  0x0140fa4c: je       0x140fa63
  0x0140fa4e: nop      
  0x0140fa50: imul     eax, eax, 0x1000193
  0x0140fa56: xor      eax, edx
  0x0140fa58: movzx    edx, word ptr [rcx]
  0x0140fa5b: lea      rcx, [rcx + 2]
  0x0140fa5f: test     edx, edx
  0x0140fa61: jne      0x140fa50
  0x0140fa63: mov      ecx, dword ptr [rsi + 0x10]
  0x0140fa66: xor      edx, edx
  0x0140fa68: div      rcx
  0x0140fa6b: mov      ecx, edx
  0x0140fa6d: mov      rax, qword ptr [rsi + 8]
  0x0140fa71: lea      r9, [rax + rcx*8]
  0x0140fa75: mov      rax, qword ptr [r9]
  0x0140fa78: test     rax, rax
  0x0140fa7b: je       0x140fb5d
  0x0140fa81: movzx    r10d, word ptr [r11]
  0x0140fa85: nop      word ptr [rax + rax]
  0x0140fa90: mov      rcx, qword ptr [rax]
  0x0140fa93: movzx    edx, r10w
  0x0140fa97: test     r10w, r10w
  0x0140fa9b: je       0x140fac0
  0x0140fa9d: movzx    eax, r10w
  0x0140faa1: mov      r8, r11
  0x0140faa4: sub      r8, rcx
  0x0140faa7: movzx    edx, ax
  0x0140faaa: cmp      ax, word ptr [rcx]
  0x0140faad: jne      0x140fac0
  0x0140faaf: add      rcx, 2
  0x0140fab3: movzx    eax, word ptr [r8 + rcx]
  0x0140fab8: movzx    edx, ax
  0x0140fabb: test     ax, ax
  0x0140fabe: jne      0x140faa7
  0x0140fac0: cmp      dx, word ptr [rcx]
  0x0140fac3: je       0x140fad4
  0x0140fac5: mov      r9, qword ptr [r9]
  0x0140fac8: add      r9, 0x10
  0x0140facc: mov      rax, qword ptr [r9]
  0x0140facf: test     rax, rax
  0x0140fad2: jne      0x140fa90
  0x0140fad4: mov      rax, qword ptr [r9]
  0x0140fad7: test     rax, rax
  0x0140fada: je       0x140fb5d
  0x0140fae0: mov      rcx, qword ptr [rax]
  0x0140fae3: movzx    edx, word ptr [r11]
  0x0140fae7: test     dx, dx
  0x0140faea: je       0x140fb0e
  0x0140faec: movzx    eax, dx
  0x0140faef: mov      r8, r11
  0x0140faf2: sub      r8, rcx
  0x0140faf5: movzx    edx, ax
  0x0140faf8: cmp      ax, word ptr [rcx]
  0x0140fafb: jne      0x140fb0e
  0x0140fafd: add      rcx, 2
  0x0140fb01: movzx    eax, word ptr [r8 + rcx]
  0x0140fb06: movzx    edx, ax
  0x0140fb09: test     ax, ax
  0x0140fb0c: jne      0x140faf5
  0x0140fb0e: cmp      dx, word ptr [rcx]
  0x0140fb11: jne      0x140fb58
  0x0140fb13: mov      rax, qword ptr [r9]
  0x0140fb16: mov      rcx, qword ptr [rax + 0x10]
  0x0140fb1a: mov      qword ptr [r9], rcx
  0x0140fb1d: dec      dword ptr [rsi + 0x14]
  0x0140fb20: mov      rax, qword ptr [r9]
  0x0140fb23: test     rax, rax
  0x0140fb26: jne      0x140fae0
  0x0140fb28: jmp      0x140fb58
  0x0140fb2a: mov      rdx, r11
  0x0140fb2d: mov      rcx, r13
  0x0140fb30: call     0x1410a50
  0x0140fb35: mov      qword ptr [rbp - 0x80], rax
  0x0140fb39: lea      r9, [rbp - 0x80]
  0x0140fb3d: movzx    r8d, dil
  0x0140fb41: lea      rdx, [rbp - 0x18]
  0x0140fb45: mov      rcx, qword ptr [r13 + 0x3d0]
  0x0140fb4c: call     0x140e7c0
  0x0140fb51: mov      rcx, qword ptr [rax]
  0x0140fb54: mov      dword ptr [rcx + 8], r12d
  0x0140fb58: mov      r15, qword ptr [rsp + 0x68]
  0x0140fb5d: inc      r14d
  0x0140fb60: mov      rax, r15
  0x0140fb63: sub      rax, qword ptr [rsp + 0x60]
  0x0140fb68: sar      rax, 3
  0x0140fb6c: cmp      r14d, eax
  0x0140fb6f: jb       0x140fa10
  0x0140fb75: jmp      0x141025a
  0x0140fb7a: lea      rdx, [rip + 0xc4ac53]
  0x0140fb81: mov      rcx, r14
  0x0140fb84: call     0x1410aa0
  0x0140fb89: test     eax, eax
  0x0140fb8b: jne      0x140fcc1
  0x0140fb91: cmp      esi, 2
  0x0140fb94: jb       0x1410354
  0x0140fb9a: mov      rax, qword ptr [rsp + 0x60]
  0x0140fb9f: mov      rsi, qword ptr [rax + 8]
  0x0140fba3: cmp      word ptr [rsi], 0
  0x0140fba7: je       0x1410418
  0x0140fbad: mov      edx, 5
  0x0140fbb2: mov      rcx, rsi
  0x0140fbb5: call     0x1411620
  0x0140fbba: test     al, al
  0x0140fbbc: jne      0x1410418
  0x0140fbc2: lea      r8, [r13 + 0x78]
  0x0140fbc6: mov      r9d, 5
  0x0140fbcc: mov      rdx, rsi
  0x0140fbcf: lea      rcx, [rbp + 0x100]
  0x0140fbd6: call     0x14118e0
  0x0140fbdb: test     rax, rax
  0x0140fbde: je       0x141025a
  0x0140fbe4: mov      r14b, 1
  0x0140fbe7: mov      rsi, qword ptr [r13 + 0x280]
  0x0140fbee: cmp      rsi, qword ptr [r13 + 0x288]
  0x0140fbf5: je       0x140fc76
  0x0140fbfb: mov      rbx, qword ptr [rbp + 0x688]
  0x0140fc02: mov      r12d, dword ptr [rsp + 0x58]
  0x0140fc07: nop      word ptr [rax + rax]
  0x0140fc10: mov      r8d, 5
  0x0140fc16: mov      rdx, qword ptr [rsi]
  0x0140fc19: lea      rcx, [rbp + 0x100]
  0x0140fc20: call     0x14117b0
  0x0140fc25: test     al, al
  0x0140fc27: jne      0x140fc42
  0x0140fc29: mov      r8d, 5
  0x0140fc2f: lea      rdx, [rbp + 0x100]
  0x0140fc36: mov      rcx, qword ptr [rsi]
  0x0140fc39: call     0x14117b0
  0x0140fc3e: test     al, al
  0x0140fc40: je       0x140fc59
  0x0140fc42: mov      r9d, 0xd06b000b
  0x0140fc48: mov      r8d, r12d
  0x0140fc4b: mov      rdx, rbx
  0x0140fc4e: mov      rcx, r13
  0x0140fc51: call     0x14107e0
  0x0140fc56: xor      r14b, r14b
  0x0140fc59: add      rsi, 8
  0x0140fc5d: cmp      rsi, qword ptr [r13 + 0x288]
  0x0140fc64: jne      0x140fc10
  0x0140fc66: movzx    ebx, byte ptr [rbp + 0x680]
  0x0140fc6d: test     r14b, r14b
  0x0140fc70: je       0x1410483
  0x0140fc76: lea      rcx, [rbp + 0x100]
  0x0140fc7d: call     0x13ca840
  0x0140fc82: lea      rcx, [r13 + 8]
  0x0140fc86: lea      rdx, [rax*2 + 2]
  0x0140fc8e: mov      r8b, 1
  0x0140fc91: call     0x13fc960
  0x0140fc96: mov      rsi, rax
  0x0140fc99: lea      rdx, [rbp + 0x100]
  0x0140fca0: mov      rcx, rax
  0x0140fca3: call     0x13c96e0
  0x0140fca8: mov      qword ptr [rbp - 0x80], rsi
  0x0140fcac: lea      rdx, [rbp - 0x80]
  0x0140fcb0: lea      rcx, [r13 + 0x280]
  0x0140fcb7: call     0x1410b40
  0x0140fcbc: jmp      0x141025a
  0x0140fcc1: lea      rdx, [rip + 0xc4ab18]
  0x0140fcc8: mov      rcx, r14
  0x0140fccb: call     0x1410aa0
  0x0140fcd0: test     eax, eax
  0x0140fcd2: jne      0x140fe5b
  0x0140fcd8: cmp      esi, 2
  0x0140fcdb: jb       0x140ffd2
  0x0140fce1: mov      rax, qword ptr [rsp + 0x60]
  0x0140fce6: mov      rsi, qword ptr [rax + 8]
  0x0140fcea: cmp      word ptr [rsi], 0
  0x0140fcee: je       0x1410452
  0x0140fcf4: mov      edx, 5
  0x0140fcf9: mov      rcx, rsi
  0x0140fcfc: call     0x1411620
  0x0140fd01: test     al, al
  0x0140fd03: jne      0x1410452
  0x0140fd09: mov      r8d, 0x5c
  0x0140fd0f: lea      rdx, [rbp + 0x100]
  0x0140fd16: mov      rcx, rsi
  0x0140fd19: call     0x1410df0
  0x0140fd1e: lea      rsi, [rbp + 0x100]
  0x0140fd25: cmp      word ptr [rbp + 0x100], 0x2e
  0x0140fd2d: jne      0x140fd49
  0x0140fd2f: nop      
  0x0140fd30: movzx    ecx, word ptr [rsi + 2]
  0x0140fd34: call     0x140ead0
  0x0140fd39: test     al, al
  0x0140fd3b: je       0x140fd49
  0x0140fd3d: add      rsi, 4
  0x0140fd41: cmp      word ptr [rsi], 0x2e
  0x0140fd45: je       0x140fd30
  0x0140fd47: jmp      0x140fd67
  0x0140fd49: cmp      word ptr [rsi], 0x2e
  0x0140fd4d: jne      0x140fd67
  0x0140fd4f: cmp      word ptr [rsi + 2], 0x2e
  0x0140fd54: jne      0x140fd67
  0x0140fd56: movzx    ecx, word ptr [rsi + 4]
  0x0140fd5a: call     0x140ead0
  0x0140fd5f: test     al, al
  0x0140fd61: jne      0x1410452
  0x0140fd67: lea      rcx, [r13 + 8]
  0x0140fd6b: mov      r8b, 1
  0x0140fd6e: mov      edx, 0x18
  0x0140fd73: call     0x13fc960
  0x0140fd78: mov      r14, rax
  0x0140fd7b: mov      dword ptr [rax], 1
  0x0140fd81: mov      dword ptr [rax + 4], 0x34728492
  0x0140fd88: xor      r15d, r15d
  0x0140fd8b: mov      qword ptr [rax + 8], r15
  0x0140fd8f: cmp      qword ptr [rbp - 0x68], r12
  0x0140fd93: je       0x140fd9e
  0x0140fd95: mov      rcx, qword ptr [r12 - 8]
  0x0140fd9a: mov      qword ptr [rax + 8], rcx
  0x0140fd9e: mov      ecx, dword ptr [r13 + 0x3bc]
  0x0140fda5: mov      dword ptr [rax + 0x10], ecx
  0x0140fda8: mov      byte ptr [rax + 0x14], r15b
  0x0140fdac: mov      byte ptr [rax + 0x16], r15b
  0x0140fdb0: xor      eax, eax
  0x0140fdb2: mov      qword ptr [rbp + 0x28], rax
  0x0140fdb6: mov      qword ptr [rbp + 0x30], rax
  0x0140fdba: mov      qword ptr [rbp + 0x38], rax
  0x0140fdbe: mov      qword ptr [rbp + 0x40], rax
  0x0140fdc2: lea      rdx, [rbp + 0x28]
  0x0140fdc6: mov      r12, qword ptr [rbp + 0x690]
  0x0140fdcd: mov      rcx, r12
  0x0140fdd0: call     0x1410c40
  0x0140fdd5: mov      rax, qword ptr [r12 + 8]
  0x0140fdda: mov      qword ptr [rax - 0x20], r14
  0x0140fdde: mov      rdx, rsi
  0x0140fde1: mov      rcx, r13
  0x0140fde4: call     0x1410a50
  0x0140fde9: mov      rcx, qword ptr [r12 + 8]
  0x0140fdee: mov      qword ptr [rcx - 0x18], rax
  0x0140fdf2: mov      rax, qword ptr [r12 + 8]
  0x0140fdf7: mov      qword ptr [rax - 0x10], r15
  0x0140fdfb: mov      rax, qword ptr [r12 + 8]
  0x0140fe00: mov      word ptr [rax - 8], r15w
  0x0140fe05: mov      rax, qword ptr [r12 + 8]
  0x0140fe0a: mov      word ptr [rax - 6], r15w
  0x0140fe0f: mov      rsi, qword ptr [rsp + 0x60]
  0x0140fe14: add      rsi, 0x10
  0x0140fe18: mov      r15, qword ptr [rsp + 0x68]
  0x0140fe1d: cmp      rsi, r15
  0x0140fe20: je       0x141025a
  0x0140fe26: nop      word ptr [rax + rax]
  0x0140fe30: lea      rdx, [rip + 0xc4a9b9]
  0x0140fe37: mov      rcx, qword ptr [rsi]
  0x0140fe3a: call     0x1410aa0
  0x0140fe3f: test     eax, eax
  0x0140fe41: jne      0x140fe4d
  0x0140fe43: mov      byte ptr [r14 + 0x14], 1
  0x0140fe48: mov      r15, qword ptr [rsp + 0x68]
  0x0140fe4d: add      rsi, 8
  0x0140fe51: cmp      rsi, r15
  0x0140fe54: jne      0x140fe30
  0x0140fe56: jmp      0x141025a
  0x0140fe5b: lea      rdx, [rip + 0xc4a99e]
  0x0140fe62: mov      rcx, r14
  0x0140fe65: call     0x1410aa0
  0x0140fe6a: test     eax, eax
  0x0140fe6c: jne      0x140ffb6
  0x0140fe72: cmp      esi, 2
  0x0140fe75: jb       0x140ffd2
  0x0140fe7b: mov      rax, qword ptr [rsp + 0x60]
  0x0140fe80: mov      rsi, qword ptr [rax + 8]
  0x0140fe84: cmp      word ptr [rsi], 0
  0x0140fe88: je       0x1410452
  0x0140fe8e: mov      edx, 5
  0x0140fe93: mov      rcx, rsi
  0x0140fe96: call     0x1411620
  0x0140fe9b: test     al, al
  0x0140fe9d: jne      0x1410452
  0x0140fea3: cmp      word ptr [rsi], 0x2e
  0x0140fea7: jne      0x140fec7
  0x0140fea9: nop      dword ptr [rax]
  0x0140feb0: movzx    ecx, word ptr [rsi + 2]
  0x0140feb4: call     0x140ead0
  0x0140feb9: test     al, al
  0x0140febb: je       0x140fec7
  0x0140febd: add      rsi, 4
  0x0140fec1: cmp      word ptr [rsi], 0x2e
  0x0140fec5: je       0x140feb0
  0x0140fec7: lea      r9, [rbp + 0xe0]
  0x0140fece: lea      r8, [rbp - 0x38]
  0x0140fed2: lea      rdx, [rbp + 0xe8]
  0x0140fed9: mov      rcx, rsi
  0x0140fedc: call     0x14119a0
  0x0140fee1: lea      rcx, [r13 + 8]
  0x0140fee5: mov      r8b, 1
  0x0140fee8: mov      edx, 0x18
  0x0140feed: call     0x13fc960
  0x0140fef2: mov      r14, rax
  0x0140fef5: mov      dword ptr [rax], 1
  0x0140fefb: mov      dword ptr [rax + 4], 0x2a43bd44
  0x0140ff02: xor      eax, eax
  0x0140ff04: mov      qword ptr [r14 + 8], rax
  0x0140ff08: cmp      qword ptr [rbp - 0x68], r12
  0x0140ff0c: je       0x140ff17
  0x0140ff0e: mov      rcx, qword ptr [r12 - 8]
  0x0140ff13: mov      qword ptr [r14 + 8], rcx
  0x0140ff17: mov      ecx, dword ptr [r13 + 0x3bc]
  0x0140ff1e: mov      dword ptr [r14 + 0x10], ecx
  0x0140ff22: mov      byte ptr [r14 + 0x14], al
  0x0140ff26: mov      byte ptr [r14 + 0x16], al
  0x0140ff2a: mov      qword ptr [rbp + 0x48], rax
  0x0140ff2e: mov      qword ptr [rbp + 0x50], rax
  0x0140ff32: mov      qword ptr [rbp + 0x58], rax
  0x0140ff36: mov      qword ptr [rbp + 0x60], rax
  0x0140ff3a: lea      rdx, [rbp + 0x48]
  0x0140ff3e: mov      r15, qword ptr [rbp + 0x690]
  0x0140ff45: mov      rcx, r15
  0x0140ff48: call     0x1410c40
  0x0140ff4d: mov      rax, qword ptr [r15 + 8]
  0x0140ff51: mov      qword ptr [rax - 0x20], r14
  0x0140ff55: mov      rdx, qword ptr [rbp - 0x38]
  0x0140ff59: mov      rcx, r13
  0x0140ff5c: call     0x1410a50
  0x0140ff61: mov      rdx, qword ptr [r15 + 8]
  0x0140ff65: mov      qword ptr [rdx - 0x10], rax
  0x0140ff69: mov      rax, qword ptr [rbp - 0x38]
  0x0140ff6d: xor      r12d, r12d
  0x0140ff70: mov      word ptr [rax], r12w
  0x0140ff74: lea      r8d, [r12 + 0x5c]
  0x0140ff79: lea      rdx, [rbp + 0x100]
  0x0140ff80: mov      rcx, rsi
  0x0140ff83: call     0x1410df0
  0x0140ff88: lea      rdx, [rbp + 0x100]
  0x0140ff8f: mov      rcx, r13
  0x0140ff92: call     0x1410a50
  0x0140ff97: mov      rcx, qword ptr [r15 + 8]
  0x0140ff9b: mov      qword ptr [rcx - 0x18], rax
  0x0140ff9f: mov      rax, qword ptr [r15 + 8]
  0x0140ffa3: mov      word ptr [rax - 8], r12w
  0x0140ffa8: mov      rax, qword ptr [r15 + 8]
  0x0140ffac: mov      word ptr [rax - 6], r12w
  0x0140ffb1: jmp      0x141025d
  0x0140ffb6: lea      rdx, [rip + 0xa5b633]
  0x0140ffbd: mov      rcx, r14
  0x0140ffc0: call     0x1410aa0
  0x0140ffc5: test     eax, eax
  0x0140ffc7: jne      0x140ffe0
  0x0140ffc9: cmp      esi, 2
  0x0140ffcc: jae      0x141025a
  0x0140ffd2: mov      r9d, 0xd06b0004
  0x0140ffd8: mov      r8d, r15d
  0x0140ffdb: jmp      0x1410474
  0x0140ffe0: lea      rdx, [rip + 0xbf8b11]
  0x0140ffe7: mov      rcx, r14
  0x0140ffea: call     0x1410aa0
  0x0140ffef: test     eax, eax
  0x0140fff1: jne      0x1410236
  0x0140fff7: cmp      esi, 2
  0x0140fffa: jb       0x140ffd2
  0x0140fffc: mov      rax, qword ptr [rsp + 0x60]
  0x01410001: add      rax, 8
  0x01410005: mov      qword ptr [rbp - 0x18], rax
  0x01410009: mov      r15, qword ptr [rbp - 0x78]
  0x0141000d: mov      qword ptr [rbp - 0x10], r15
  0x01410011: lea      rsi, [r13 + 8]
  0x01410015: mov      qword ptr [rbp - 0x80], rsi
  0x01410019: mov      qword ptr [rbp - 8], rsi
  0x0141001d: xor      r14d, r14d
  0x01410020: mov      dword ptr [rbp], r14d
  0x01410024: lea      rcx, [rbp - 0x18]
  0x01410028: call     0x14105a0
  0x0141002d: mov      r13, rax
  0x01410030: mov      r9d, dword ptr [rbp]
  0x01410034: test     r9d, r9d
  0x01410037: js       0x141045d
  0x0141003d: mov      rdx, qword ptr [rbp - 0x68]
  0x01410041: cmp      rdx, r12
  0x01410044: je       0x141012d
  0x0141004a: mov      rax, qword ptr [rsp + 0x78]
  0x0141004f: cmp      rax, qword ptr [rsp + 0x40]
  0x01410054: jae      0x141006f
  0x01410056: mov      rcx, rax
  0x01410059: lea      r15, [rax + 8]
  0x0141005d: mov      qword ptr [rsp + 0x78], r15
  0x01410062: mov      rax, qword ptr [r12 - 8]
  0x01410067: mov      qword ptr [rcx], rax
  0x0141006a: jmp      0x14101e2
  0x0141006f: sub      rax, rdx
  0x01410072: mov      qword ptr [rsp + 0x78], rax
  0x01410077: mov      rsi, rax
  0x0141007a: sar      rsi, 3
  0x0141007e: test     esi, esi
  0x01410080: je       0x141008d
  0x01410082: lea      r15d, [rsi + rsi]
  0x01410086: test     r15d, r15d
  0x01410089: jne      0x1410093
  0x0141008b: jmp      0x14100b7
  0x0141008d: mov      r15d, 1
  0x01410093: mov      edx, r15d
  0x01410096: shl      rdx, 3
  0x0141009a: mov      rcx, qword ptr [rsp + 0x48]
  0x0141009f: mov      rax, qword ptr [rcx]
  0x014100a2: xor      r9d, r9d
  0x014100a5: xor      r8d, r8d
  0x014100a8: call     qword ptr [rax + 0x10]
  0x014100ab: mov      r14, rax
  0x014100ae: mov      rax, qword ptr [rsp + 0x78]
  0x014100b3: mov      rdx, qword ptr [rbp - 0x68]
  0x014100b7: mov      r8, rax
  0x014100ba: mov      rcx, r14
  0x014100bd: call     0x143eb60
  0x014100c2: mov      rcx, qword ptr [r12 - 8]
  0x014100c7: mov      qword ptr [rax + rsi*8], rcx
  0x014100cb: inc      rsi
  0x014100ce: lea      rsi, [rax + rsi*8]
  0x014100d2: mov      qword ptr [rsp + 0x78], rsi
  0x014100d7: mov      rcx, qword ptr [rbp - 0x68]
  0x014100db: mov      rdx, qword ptr [rsp + 0x40]
  0x014100e0: sub      rdx, rcx
  0x014100e3: sar      rdx, 3
  0x014100e7: test     rcx, rcx
  0x014100ea: je       0x1410104
  0x014100ec: mov      r9, qword ptr [rsp + 0x48]
  0x014100f1: mov      rax, qword ptr [r9]
  0x014100f4: mov      r8d, edx
  0x014100f7: shl      r8, 3
  0x014100fb: mov      rdx, rcx
  0x014100fe: mov      rcx, r9
  0x01410101: call     qword ptr [rax + 0x18]
  0x01410104: mov      qword ptr [rbp - 0x68], r14
  0x01410108: mov      qword ptr [rbp - 0x60], rsi
  0x0141010c: mov      eax, r15d
  0x0141010f: lea      rax, [r14 + rax*8]
  0x01410113: mov      qword ptr [rsp + 0x40], rax
  0x01410118: mov      qword ptr [rbp - 0x58], rax
  0x0141011c: mov      rsi, qword ptr [rbp - 0x80]
  0x01410120: mov      r15, qword ptr [rsp + 0x78]
  0x01410125: xor      r14d, r14d
  0x01410128: jmp      0x14101e6
  0x0141012d: mov      r8, qword ptr [rsp + 0x40]
  0x01410132: cmp      r12, r8
  0x01410135: jae      0x141014a
  0x01410137: lea      r15, [r12 + 8]
  0x0141013c: mov      qword ptr [rsp + 0x78], r15
  0x01410141: mov      qword ptr [r12], r14
  0x01410145: jmp      0x14101e2
  0x0141014a: sub      r12, rdx
  0x0141014d: sar      r12, 3
  0x01410151: test     r12d, r12d
  0x01410154: je       0x141016a
  0x01410156: lea      r14d, [r12 + r12]
  0x0141015a: test     r14d, r14d
  0x0141015d: jne      0x1410170
  0x0141015f: xor      eax, eax
  0x01410161: mov      esi, eax
  0x01410163: mov      r12, qword ptr [rsp + 0x48]
  0x01410168: jmp      0x141019a
  0x0141016a: mov      r14d, 1
  0x01410170: mov      edx, r14d
  0x01410173: shl      rdx, 3
  0x01410177: mov      r12, qword ptr [rsp + 0x48]
  0x0141017c: mov      rax, qword ptr [r12]
  0x01410180: xor      r9d, r9d
  0x01410183: xor      r8d, r8d
  0x01410186: mov      rcx, r12
  0x01410189: call     qword ptr [rax + 0x10]
  0x0141018c: mov      rsi, rax
  0x0141018f: mov      rdx, qword ptr [rbp - 0x68]
  0x01410193: mov      r8, qword ptr [rsp + 0x40]
  0x01410198: xor      eax, eax
  0x0141019a: mov      qword ptr [rsi], rax
  0x0141019d: lea      r15, [rsi + 8]
  0x014101a1: mov      qword ptr [rsp + 0x78], r15
  0x014101a6: sub      r8, rdx
  0x014101a9: sar      r8, 3
  0x014101ad: test     rdx, rdx
  0x014101b0: je       0x14101c7
  0x014101b2: mov      rcx, qword ptr [r12]
  0x014101b6: mov      r9, qword ptr [rcx + 0x18]
  0x014101ba: mov      r8d, r8d
  0x014101bd: shl      r8, 3
  0x014101c1: mov      rcx, r12
  0x014101c4: call     r9
  0x014101c7: mov      qword ptr [rbp - 0x68], rsi
  0x014101cb: mov      eax, r14d
  0x014101ce: lea      rax, [rsi + rax*8]
  0x014101d2: mov      qword ptr [rsp + 0x40], rax
  0x014101d7: mov      qword ptr [rbp - 0x58], rax
  0x014101db: mov      rsi, qword ptr [rbp - 0x80]
  0x014101df: xor      r14d, r14d
  0x014101e2: mov      qword ptr [rbp - 0x60], r15
  0x014101e6: test     r13, r13
  0x014101e9: je       0x141025a
  0x014101eb: cmp      qword ptr [r15 - 8], 0
  0x014101f0: jne      0x14101f8
  0x014101f2: mov      qword ptr [r15 - 8], r13
  0x014101f6: jmp      0x141025a
  0x014101f8: mov      r8b, 1
  0x014101fb: mov      edx, 0x18
  0x01410200: mov      rcx, rsi
  0x01410203: call     0x13fc960
  0x01410208: mov      qword ptr [rbp - 0x80], rax
  0x0141020c: test     rax, rax
  0x0141020f: je       0x141022d
  0x01410211: mov      rcx, qword ptr [r15 - 8]
  0x01410215: lea      rdx, [rip + 0xc4a544]
  0x0141021c: mov      qword ptr [rax], rdx
  0x0141021f: mov      qword ptr [rax + 8], rcx
  0x01410223: mov      qword ptr [rax + 0x10], r13
  0x01410227: mov      qword ptr [r15 - 8], rax
  0x0141022b: jmp      0x141025a
  0x0141022d: mov      rax, r14
  0x01410230: mov      qword ptr [r15 - 8], rax
  0x01410234: jmp      0x141025a
  0x01410236: lea      rdx, [rip + 0xbf87c7]
  0x0141023d: mov      rcx, r14
  0x01410240: call     0x1410aa0
  0x01410245: test     eax, eax
  0x01410247: jne      0x141046b
  0x0141024d: sub      r12, 8
  0x01410251: mov      qword ptr [rsp + 0x78], r12
  0x01410256: mov      qword ptr [rbp - 0x60], r12
  0x0141025a: xor      r12d, r12d
  0x0141025d: xor      r9d, r9d
  0x01410260: mov      r8d, 0x103
  0x01410266: lea      rdx, [rbp + 0x310]
  0x0141026d: lea      rcx, [rbp + 0x70]
  0x01410271: call     0x13f1480
  0x01410276: test     eax, eax
  0x01410278: js       0x14104de
  0x0141027e: mov      r13, qword ptr [rbp + 0x680]
  0x01410285: mov      r12, qword ptr [rsp + 0x78]
  0x0141028a: jmp      0x140f170
  0x0141028f: mov      dword ptr [r13 + 0x3e8], 0xd06b0002
  0x0141029a: mov      r10, qword ptr [r13 + 0x3d8]
  0x014102a1: test     r10, r10
  0x014102a4: je       0x1410483
  0x014102aa: mov      rax, qword ptr [r13 + 0x3e0]
  0x014102b1: mov      qword ptr [rsp + 0x20], rax
  0x014102b6: xor      r9d, r9d
  0x014102b9: mov      r8d, dword ptr [rsp + 0x58]
  0x014102be: mov      rdx, qword ptr [rbp + 0x688]
  0x014102c5: mov      ecx, 0xd06b0002
  0x014102ca: call     r10
  0x014102cd: jmp      0x1410483
  0x014102d2: mov      dword ptr [r13 + 0x3e8], 0xd06b0005
  0x014102dd: mov      r10, qword ptr [r13 + 0x3d8]
  0x014102e4: test     r10, r10
  0x014102e7: je       0x1410483
  0x014102ed: mov      rax, qword ptr [r13 + 0x3e0]
  0x014102f4: mov      qword ptr [rsp + 0x20], rax
  0x014102f9: xor      r9d, r9d
  0x014102fc: mov      r8d, r15d
  0x014102ff: mov      rdx, qword ptr [rbp + 0x688]
  0x01410306: mov      ecx, 0xd06b0005
  0x0141030b: call     r10
  0x0141030e: jmp      0x1410483
  0x01410313: mov      dword ptr [r13 + 0x3e8], 0xd06b0003
  0x0141031e: mov      r10, qword ptr [r13 + 0x3d8]
  0x01410325: test     r10, r10
  0x01410328: je       0x1410483
  0x0141032e: mov      rax, qword ptr [r13 + 0x3e0]
  0x01410335: mov      qword ptr [rsp + 0x20], rax
  0x0141033a: xor      r9d, r9d
  0x0141033d: mov      r8d, r15d
  0x01410340: mov      rdx, qword ptr [rbp + 0x688]
  0x01410347: mov      ecx, 0xd06b0003
  0x0141034c: call     r10
  0x0141034f: jmp      0x1410483
  0x01410354: mov      dword ptr [r13 + 0x3e8], 0xd06b0004
  0x0141035f: mov      r10, qword ptr [r13 + 0x3d8]
  0x01410366: test     r10, r10
  0x01410369: je       0x1410483
  0x0141036f: mov      rax, qword ptr [r13 + 0x3e0]
  0x01410376: mov      qword ptr [rsp + 0x20], rax
  0x0141037b: xor      r9d, r9d
  0x0141037e: mov      r8d, r15d
  0x01410381: mov      rdx, qword ptr [rbp + 0x688]
  0x01410388: mov      ecx, 0xd06b0004
  0x0141038d: call     r10
  0x01410390: jmp      0x1410483
  0x01410395: mov      dword ptr [r13 + 0x3e8], 0xd06b0005
  0x014103a0: mov      r10, qword ptr [r13 + 0x3d8]
  0x014103a7: test     r10, r10
  0x014103aa: je       0x1410483
  0x014103b0: mov      rax, qword ptr [r13 + 0x3e0]
  0x014103b7: mov      qword ptr [rsp + 0x20], rax
  0x014103bc: xor      r9d, r9d
  0x014103bf: mov      r8d, dword ptr [rsp + 0x58]
  0x014103c4: mov      rdx, qword ptr [rbp + 0x688]
  0x014103cb: mov      ecx, 0xd06b0005
  0x014103d0: call     r10
  0x014103d3: jmp      0x1410483
  0x014103d8: mov      dword ptr [r13 + 0x3e8], 0xd06b0004
  0x014103e3: mov      r10, qword ptr [r13 + 0x3d8]
  0x014103ea: test     r10, r10
  0x014103ed: je       0x1410483
  0x014103f3: mov      rax, qword ptr [r13 + 0x3e0]
  0x014103fa: mov      qword ptr [rsp + 0x20], rax
  0x014103ff: xor      r9d, r9d
  0x01410402: mov      r8d, dword ptr [rsp + 0x58]
  0x01410407: mov      rdx, qword ptr [rbp + 0x688]
  0x0141040e: mov      ecx, 0xd06b0004
  0x01410413: call     r10
  0x01410416: jmp      0x1410483
  0x01410418: mov      dword ptr [r13 + 0x3e8], 0xd06b0002
  0x01410423: mov      r10, qword ptr [r13 + 0x3d8]
  0x0141042a: test     r10, r10
  0x0141042d: je       0x1410483
  0x0141042f: mov      rax, qword ptr [r13 + 0x3e0]
  0x01410436: mov      qword ptr [rsp + 0x20], rax
  0x0141043b: xor      r9d, r9d
  0x0141043e: mov      r8d, r15d
  0x01410441: mov      rdx, qword ptr [rbp + 0x688]
  0x01410448: mov      ecx, 0xd06b0002
  0x0141044d: call     r10
  0x01410450: jmp      0x1410483
  0x01410452: mov      r9d, 0xd06b0002
  0x01410458: mov      r8d, r15d
  0x0141045b: jmp      0x1410474
  0x0141045d: mov      r8d, dword ptr [rsp + 0x58]
  0x01410462: mov      rcx, qword ptr [rbp + 0x680]
  0x01410469: jmp      0x1410477
  0x0141046b: mov      r9d, r15d
  0x0141046e: mov      r8d, 0xd06b0003
  0x01410474: mov      rcx, r13
  0x01410477: mov      rdx, qword ptr [rbp + 0x688]
  0x0141047e: call     0x14107e0
  0x01410483: mov      r14, qword ptr [rsp + 0x50]
  0x01410488: mov      rsi, qword ptr [rsp + 0x48]
  0x0141048d: mov      rdi, qword ptr [rsp + 0x40]
  0x01410492: lea      rax, [rip + 0x9e25f7]
  0x01410499: mov      qword ptr [rbp + 0x70], rax
  0x0141049d: mov      rcx, qword ptr [rbp + 0x88]
  0x014104a4: test     rcx, rcx
  0x014104a7: je       0x14104ae
  0x014104a9: call     0x13f0c80
  0x014104ae: lea      rax, [rip + 0x9e22c3]
  0x014104b5: mov      qword ptr [rbp + 0x70], rax
  0x014104b9: mov      rdx, qword ptr [rsp + 0x60]
  0x014104be: test     rdx, rdx
  0x014104c1: je       0x14104da
  0x014104c3: mov      r8, qword ptr [rsp + 0x70]
  0x014104c8: sub      r8, rdx
  0x014104cb: and      r8, 0xfffffffffffffff8
  0x014104cf: lea      rcx, [rsp + 0x70]
  0x014104d4: call     0x6ab30
  0x014104d9: nop      
  0x014104da: xor      bl, bl
  0x014104dc: jmp      0x1410553
  0x014104de: mov      rdi, qword ptr [rsp + 0x40]
  0x014104e3: mov      rsi, qword ptr [rsp + 0x48]
  0x014104e8: mov      r14, qword ptr [rsp + 0x50]
  0x014104ed: mov      qword ptr [rsp + 0x28], r12
  0x014104f2: mov      byte ptr [rsp + 0x20], 1
  0x014104f7: xor      r9d, r9d
  0x014104fa: xor      r8d, r8d
  0x014104fd: xor      edx, edx
  0x014104ff: lea      rcx, [rbp + 0x70]
  0x01410503: call     0x13f0ce0
  0x01410508: nop      
  0x01410509: lea      rax, [rip + 0x9e2580]
  0x01410510: mov      qword ptr [rbp + 0x70], rax
  0x01410514: mov      rcx, qword ptr [rbp + 0x88]
  0x0141051b: test     rcx, rcx
  0x0141051e: je       0x1410525
  0x01410520: call     0x13f0c80
  0x01410525: lea      rax, [rip + 0x9e224c]
  0x0141052c: mov      qword ptr [rbp + 0x70], rax
  0x01410530: mov      rdx, qword ptr [rsp + 0x60]
  0x01410535: test     rdx, rdx
  0x01410538: je       0x1410551
  0x0141053a: mov      r8, qword ptr [rsp + 0x70]
  0x0141053f: sub      r8, rdx
  0x01410542: and      r8, 0xfffffffffffffff8
  0x01410546: lea      rcx, [rsp + 0x70]
  0x0141054b: call     0x6ab30
  0x01410550: nop      
  0x01410551: mov      bl, 1
  0x01410553: test     r14, r14
  0x01410556: je       0x1410562
  0x01410558: mov      rax, qword ptr [r14]
  0x0141055b: mov      rcx, r14
  0x0141055e: call     qword ptr [rax + 0x10]
  0x01410561: nop      
  0x01410562: mov      rax, qword ptr [rbp - 0x68]
  0x01410566: test     rax, rax
  0x01410569: je       0x1410586
  0x0141056b: sub      rdi, rax
  0x0141056e: and      rdi, 0xfffffffffffffff8
  0x01410572: mov      rdx, qword ptr [rsi]
  0x01410575: mov      r9, qword ptr [rdx + 0x18]
  0x01410579: mov      r8, rdi
  0x0141057c: mov      rdx, rax
  0x0141057f: mov      rcx, rsi
  0x01410582: call     r9
  0x01410585: nop      
  0x01410586: movzx    eax, bl
  0x01410589: add      rsp, 0x738
  0x01410590: pop      r15
  0x01410592: pop      r14
  0x01410594: pop      r13
  0x01410596: pop      r12
  0x01410598: pop      rdi
  0x01410599: pop      rsi
  0x0141059a: pop      rbx
  0x0141059b: pop      rbp
  0x0141059c: ret      
  0x0141059d: int3     
