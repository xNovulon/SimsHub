; function start 0x14f580
  0x0014f580: mov      rax, rsp
  0x0014f583: mov      byte ptr [rax + 0x18], r8b
  0x0014f587: push     rbp
  0x0014f588: push     rsi
  0x0014f589: push     rdi
  0x0014f58a: push     r12
  0x0014f58c: push     r13
  0x0014f58e: push     r14
  0x0014f590: push     r15
  0x0014f592: lea      rbp, [rax - 0x418]
  0x0014f599: sub      rsp, 0x4e0
  0x0014f5a0: mov      qword ptr [rbp - 0x50], 0xfffffffffffffffe
  0x0014f5a8: mov      qword ptr [rax + 8], rbx
  0x0014f5ac: movaps   xmmword ptr [rax - 0x48], xmm6
  0x0014f5b0: movzx    ebx, r8b
  0x0014f5b4: mov      r12, rdx
  0x0014f5b7: mov      r13, rcx
  0x0014f5ba: xor      r14d, r14d
  0x0014f5bd: mov      dword ptr [rsp + 0x70], r14d
  0x0014f5c2: movsx    eax, byte ptr [rdx + 0xf]
  0x0014f5c6: shr      eax, 7
  0x0014f5c9: and      al, 1
  0x0014f5cb: je       0x14f5d2
  0x0014f5cd: mov      rcx, qword ptr [rdx]
  0x0014f5d0: jmp      0x14f5d5
  0x0014f5d2: mov      rcx, r12
  0x0014f5d5: xor      r8d, r8d
  0x0014f5d8: xor      edx, edx
  0x0014f5da: call     0x13f3a50
  0x0014f5df: mov      r15, rax
  0x0014f5e2: test     rax, rax
  0x0014f5e5: je       0x14fd28
  0x0014f5eb: lea      rsi, [rax + 2]
  0x0014f5ef: lea      rdi, [rip + 0x1cc9d3a]
  0x0014f5f6: movaps   xmm6, xmmword ptr [rbp - 0x60]
  0x0014f5fa: nop      word ptr [rax + rax]
  0x0014f600: lea      rdx, [rip + 0x1cc9d15]
  0x0014f607: mov      rcx, rsi
  0x0014f60a: call     0x13c9620
  0x0014f60f: test     eax, eax
  0x0014f611: je       0x14fd17
  0x0014f617: lea      rdx, [rip + 0x1cc9d0a]
  0x0014f61e: mov      rcx, rsi
  0x0014f621: call     0x13c9620
  0x0014f626: test     eax, eax
  0x0014f628: je       0x14fd17
  0x0014f62e: cmp      byte ptr [r15 + 0x20a], 0
  0x0014f636: je       0x14fa96
  0x0014f63c: test     bl, bl
  0x0014f63e: je       0x14fd05
  0x0014f644: lea      rdx, [r13 + 0x38]
  0x0014f648: mov      r8, rsi
  0x0014f64b: lea      rcx, [rsp + 0x60]
  0x0014f650: call     0x14dd50
  0x0014f655: nop      
  0x0014f656: mov      rbx, rdi
  0x0014f659: nop      dword ptr [rax]
  0x0014f660: add      rbx, 2
  0x0014f664: cmp      word ptr [rbx], 0
  0x0014f668: jne      0x14f660
  0x0014f66a: sub      rbx, rdi
  0x0014f66d: sar      rbx, 1
  0x0014f670: movsx    ecx, byte ptr [rsp + 0x6f]
  0x0014f675: mov      eax, ecx
  0x0014f677: shr      eax, 7
  0x0014f67a: and      al, 1
  0x0014f67c: je       0x14f684
  0x0014f67e: mov      eax, dword ptr [rsp + 0x68]
  0x0014f682: jmp      0x14f68b
  0x0014f684: mov      eax, 7
  0x0014f689: sub      eax, ecx
  0x0014f68b: lea      edi, [rax + rbx]
  0x0014f68e: lea      rdx, [rsp + 0x60]
  0x0014f693: lea      rcx, [rsp + 0x20]
  0x0014f698: call     0x6a630
  0x0014f69d: xor      eax, eax
  0x0014f69f: mov      qword ptr [rsp + 0x20], rax
  0x0014f6a4: mov      qword ptr [rsp + 0x28], rax
  0x0014f6a9: mov      byte ptr [rsp + 0x2f], 7
  0x0014f6ae: cmp      edi, 7
  0x0014f6b1: jbe      0x14f6e5
  0x0014f6b3: lea      edx, [rdi + 1]
  0x0014f6b6: add      rdx, rdx
  0x0014f6b9: xor      r8d, r8d
  0x0014f6bc: lea      rcx, [rsp + 0x20]
  0x0014f6c1: call     0x6aaf0
  0x0014f6c6: mov      rcx, rax
  0x0014f6c9: mov      qword ptr [rsp + 0x20], rax
  0x0014f6ce: bts      edi, 0x1f
  0x0014f6d2: mov      dword ptr [rsp + 0x2c], edi
  0x0014f6d6: xor      r9d, r9d
  0x0014f6d9: mov      edx, r9d
  0x0014f6dc: mov      dword ptr [rsp + 0x28], edx
  0x0014f6e0: shr      edi, 0x18
  0x0014f6e3: jmp      0x14f700
  0x0014f6e5: xor      ecx, ecx
  0x0014f6e7: mov      qword ptr [rsp + 0x20], rcx
  0x0014f6ec: mov      qword ptr [rsp + 0x28], rcx
  0x0014f6f1: mov      byte ptr [rsp + 0x2f], 7
  0x0014f6f6: mov      dil, 7
  0x0014f6f9: mov      edx, dword ptr [rsp + 0x28]
  0x0014f6fd: xor      r9d, r9d
  0x0014f700: movsx    r8d, dil
  0x0014f704: mov      eax, r8d
  0x0014f707: shr      eax, 7
  0x0014f70a: and      al, 1
  0x0014f70c: je       0x14f716
  0x0014f70e: mov      eax, edx
  0x0014f710: lea      rdx, [rcx + rax*2]
  0x0014f714: jmp      0x14f727
  0x0014f716: mov      eax, 7
  0x0014f71b: sub      eax, r8d
  0x0014f71e: lea      rdx, [rsp + 0x20]
  0x0014f723: lea      rdx, [rdx + rax*2]
  0x0014f727: mov      word ptr [rdx], r9w
  0x0014f72b: or       r14d, 1
  0x0014f72f: mov      dword ptr [rsp + 0x70], r14d
  0x0014f734: movsx    edx, byte ptr [rsp + 0x6f]
  0x0014f739: mov      ecx, edx
  0x0014f73b: shr      ecx, 7
  0x0014f73e: and      cl, 1
  0x0014f741: mov      r9, qword ptr [rsp + 0x60]
  0x0014f746: je       0x14f752
  0x0014f748: mov      eax, dword ptr [rsp + 0x68]
  0x0014f74c: lea      r8, [r9 + rax*2]
  0x0014f750: jmp      0x14f762
  0x0014f752: mov      eax, 7
  0x0014f757: sub      eax, edx
  0x0014f759: lea      r8, [rsp + 0x60]
  0x0014f75e: lea      r8, [r8 + rax*2]
  0x0014f762: lea      rdx, [rsp + 0x60]
  0x0014f767: test     cl, cl
  0x0014f769: cmovne   rdx, r9
  0x0014f76d: lea      rcx, [rsp + 0x20]
  0x0014f772: call     0x7dce0
  0x0014f777: mov      eax, ebx
  0x0014f779: lea      rdi, [rip + 0x1cc9bb0]
  0x0014f780: lea      r8, [rdi + rax*2]
  0x0014f784: mov      rdx, rdi
  0x0014f787: lea      rcx, [rsp + 0x20]
  0x0014f78c: call     0x7dce0
  0x0014f791: lea      rcx, [rip + 0x1ca8d70]
  0x0014f798: mov      rax, rcx
  0x0014f79b: cmp      word ptr [rip + 0x1ca8d65], 0
  0x0014f7a3: je       0x14f7af
  0x0014f7a5: add      rax, 2
  0x0014f7a9: cmp      word ptr [rax], 0
  0x0014f7ad: jne      0x14f7a5
  0x0014f7af: sub      rax, rcx
  0x0014f7b2: sar      rax, 1
  0x0014f7b5: lea      r8, [rcx + rax*2]
  0x0014f7b9: mov      rdx, rcx
  0x0014f7bc: lea      rcx, [rsp + 0x20]
  0x0014f7c1: call     0x7dce0
  0x0014f7c6: nop      
  0x0014f7c7: lea      rdx, [rsp + 0x20]
  0x0014f7cc: lea      rcx, [rbp - 0x80]
  0x0014f7d0: call     0x6a630
  0x0014f7d5: movaps   xmm1, xmmword ptr [rsp + 0x20]
  0x0014f7da: movaps   xmmword ptr [rbp - 0x80], xmm1
  0x0014f7de: xor      eax, eax
  0x0014f7e0: mov      qword ptr [rsp + 0x20], rax
  0x0014f7e5: mov      qword ptr [rsp + 0x28], rax
  0x0014f7ea: mov      byte ptr [rsp + 0x2f], 7
  0x0014f7ef: or       r14d, 2
  0x0014f7f3: and      r14d, 0xfffffffe
  0x0014f7f7: mov      dword ptr [rsp + 0x70], r14d
  0x0014f7fc: movdqa   xmm0, xmm1
  0x0014f800: psrldq   xmm0, 0xf
  0x0014f805: movd     eax, xmm0
  0x0014f809: movsx    ecx, al
  0x0014f80c: shr      ecx, 7
  0x0014f80f: and      cl, 1
  0x0014f812: lea      rcx, [rbp - 0x80]
  0x0014f816: movq     rax, xmm1
  0x0014f81b: cmovne   rcx, rax
  0x0014f81f: call     0x13ed1c0
  0x0014f824: test     al, al
  0x0014f826: je       0x14fa22
  0x0014f82c: lea      rdx, [rip + 0x1ca045d]
  0x0014f833: lea      rcx, [rbp + 0x438]
  0x0014f83a: call     0x6a630
  0x0014f83f: mov      rdx, rax
  0x0014f842: lea      rcx, [rsp + 0x30]
  0x0014f847: call     0x6a630
  0x0014f84c: xor      eax, eax
  0x0014f84e: mov      qword ptr [rsp + 0x30], rax
  0x0014f853: mov      qword ptr [rsp + 0x38], rax
  0x0014f858: mov      byte ptr [rsp + 0x3f], 7
  0x0014f85d: lea      rdx, [rip + 0x1ca042c]
  0x0014f864: lea      rcx, [rsp + 0x58]
  0x0014f869: call     0x6a630
  0x0014f86e: mov      rdx, rax
  0x0014f871: lea      rcx, [rsp + 0x48]
  0x0014f876: call     0x6a630
  0x0014f87b: xor      eax, eax
  0x0014f87d: mov      qword ptr [rsp + 0x48], rax
  0x0014f882: mov      qword ptr [rsp + 0x50], rax
  0x0014f887: mov      byte ptr [rsp + 0x57], 7
  0x0014f88c: mov      rax, rsi
  0x0014f88f: cmp      word ptr [rsi], 0
  0x0014f893: je       0x14f89f
  0x0014f895: add      rax, 2
  0x0014f899: cmp      word ptr [rax], 0
  0x0014f89d: jne      0x14f895
  0x0014f89f: sub      rax, rsi
  0x0014f8a2: sar      rax, 1
  0x0014f8a5: lea      r8, [rsi + rax*2]
  0x0014f8a9: mov      rdx, rsi
  0x0014f8ac: lea      rcx, [rsp + 0x30]
  0x0014f8b1: call     0x7dfe0
  0x0014f8b6: movsx    ecx, byte ptr [rsp + 0x3f]
  0x0014f8bb: mov      r10d, ecx
  0x0014f8be: shr      r10d, 7
  0x0014f8c2: and      r10b, 1
  0x0014f8c6: mov      r11d, dword ptr [rsp + 0x38]
  0x0014f8cb: je       0x14f8db
  0x0014f8cd: mov      eax, r11d
  0x0014f8d0: mov      r8d, 7
  0x0014f8d6: sub      r8d, ecx
  0x0014f8d9: jmp      0x14f8e5
  0x0014f8db: mov      eax, 7
  0x0014f8e0: sub      eax, ecx
  0x0014f8e2: mov      r8d, eax
  0x0014f8e5: dec      eax
  0x0014f8e7: lea      rdx, [rsp + 0x30]
  0x0014f8ec: test     r10b, r10b
  0x0014f8ef: cmovne   rdx, qword ptr [rsp + 0x30]
  0x0014f8f5: cmovne   r8d, r11d
  0x0014f8f9: sub      r8d, eax
  0x0014f8fc: mov      ecx, eax
  0x0014f8fe: mov      eax, 0xffffffff
  0x0014f903: cmp      r8d, eax
  0x0014f906: cmovb    eax, r8d
  0x0014f90a: add      rax, rcx
  0x0014f90d: lea      r8, [rdx + rax*2]
  0x0014f911: lea      rax, [rsp + 0x30]
  0x0014f916: test     r10b, r10b
  0x0014f919: cmovne   rax, qword ptr [rsp + 0x30]
  0x0014f91f: lea      rdx, [rax + rcx*2]
  0x0014f923: lea      rcx, [rsp + 0x30]
  0x0014f928: call     0x702b0
  0x0014f92d: lea      rbx, [r13 + 0x20]
  0x0014f931: mov      rcx, qword ptr [rbx + 8]
  0x0014f935: sub      rcx, qword ptr [rbx]
  0x0014f938: movabs   rax, 0x6666666666666667
  0x0014f942: imul     rcx
  0x0014f945: sar      rdx, 4
  0x0014f949: mov      rax, rdx
  0x0014f94c: shr      rax, 0x3f
  0x0014f950: add      rdx, rax
  0x0014f953: mov      dword ptr [rsp + 0x40], edx
  0x0014f957: movsx    edx, byte ptr [rbp - 0x71]
  0x0014f95b: mov      r9d, edx
  0x0014f95e: shr      r9d, 7
  0x0014f962: and      r9b, 1
  0x0014f966: mov      rcx, qword ptr [rbp - 0x80]
  0x0014f96a: je       0x14f975
  0x0014f96c: mov      eax, dword ptr [rbp - 0x78]
  0x0014f96f: lea      r8, [rcx + rax*2]
  0x0014f973: jmp      0x14f984
  0x0014f975: mov      eax, 7
  0x0014f97a: sub      eax, edx
  0x0014f97c: lea      r8, [rbp - 0x80]
  0x0014f980: lea      r8, [r8 + rax*2]
  0x0014f984: lea      rdx, [rbp - 0x80]
  0x0014f988: test     r9b, r9b
  0x0014f98b: cmovne   rdx, rcx
  0x0014f98f: lea      rcx, [rsp + 0x48]
  0x0014f994: call     0x7dfe0
  0x0014f999: mov      rcx, qword ptr [rbx + 8]
  0x0014f99d: lea      rdx, [rsp + 0x30]
  0x0014f9a2: cmp      rcx, qword ptr [rbx + 0x10]
  0x0014f9a6: jae      0x14f9b7
  0x0014f9a8: lea      rax, [rcx + 0x28]
  0x0014f9ac: mov      qword ptr [rbx + 8], rax
  0x0014f9b0: call     0x14e4e0
  0x0014f9b5: jmp      0x14f9c0
  0x0014f9b7: mov      rcx, rbx
  0x0014f9ba: call     0x14e010
  0x0014f9bf: nop      
  0x0014f9c0: movsx    eax, byte ptr [rsp + 0x57]
  0x0014f9c5: shr      eax, 7
  0x0014f9c8: and      al, 1
  0x0014f9ca: je       0x14f9f1
  0x0014f9cc: mov      eax, dword ptr [rsp + 0x54]
  0x0014f9d0: btr      eax, 0x1f
  0x0014f9d4: inc      eax
  0x0014f9d6: mov      rdx, qword ptr [rsp + 0x48]
  0x0014f9db: test     rdx, rdx
  0x0014f9de: je       0x14f9f1
  0x0014f9e0: mov      r8d, eax
  0x0014f9e3: add      r8, r8
  0x0014f9e6: lea      rcx, [rsp + 0x48]
  0x0014f9eb: call     0x6ab30
  0x0014f9f0: nop      
  0x0014f9f1: movsx    eax, byte ptr [rsp + 0x3f]
  0x0014f9f6: shr      eax, 7
  0x0014f9f9: and      al, 1
  0x0014f9fb: je       0x14fa22
  0x0014f9fd: mov      eax, dword ptr [rsp + 0x3c]
  0x0014fa01: btr      eax, 0x1f
  0x0014fa05: inc      eax
  0x0014fa07: mov      rdx, qword ptr [rsp + 0x30]
  0x0014fa0c: test     rdx, rdx
  0x0014fa0f: je       0x14fa22
  0x0014fa11: mov      r8d, eax
  0x0014fa14: add      r8, r8
  0x0014fa17: lea      rcx, [rsp + 0x30]
  0x0014fa1c: call     0x6ab30
  0x0014fa21: nop      
  0x0014fa22: xor      r8d, r8d
  0x0014fa25: lea      rdx, [rsp + 0x60]
  0x0014fa2a: mov      rcx, r13
  0x0014fa2d: call     0x14f580
  0x0014fa32: nop      
  0x0014fa33: movsx    eax, byte ptr [rbp - 0x71]
  0x0014fa37: shr      eax, 7
  0x0014fa3a: and      al, 1
  0x0014fa3c: je       0x14fa60
  0x0014fa3e: mov      eax, dword ptr [rbp - 0x74]
  0x0014fa41: btr      eax, 0x1f
  0x0014fa45: inc      eax
  0x0014fa47: mov      rdx, qword ptr [rbp - 0x80]
  0x0014fa4b: test     rdx, rdx
  0x0014fa4e: je       0x14fa60
  0x0014fa50: mov      r8d, eax
  0x0014fa53: add      r8, r8
  0x0014fa56: lea      rcx, [rbp - 0x80]
  0x0014fa5a: call     0x6ab30
  0x0014fa5f: nop      
  0x0014fa60: movsx    eax, byte ptr [rsp + 0x6f]
  0x0014fa65: shr      eax, 7
  0x0014fa68: and      al, 1
  0x0014fa6a: je       0x14fa91
  0x0014fa6c: mov      eax, dword ptr [rsp + 0x6c]
  0x0014fa70: btr      eax, 0x1f
  0x0014fa74: inc      eax
  0x0014fa76: mov      rdx, qword ptr [rsp + 0x60]
  0x0014fa7b: test     rdx, rdx
  0x0014fa7e: je       0x14fa91
  0x0014fa80: mov      r8d, eax
  0x0014fa83: add      r8, r8
  0x0014fa86: lea      rcx, [rsp + 0x60]
  0x0014fa8b: call     0x6ab30
  0x0014fa90: nop      
  0x0014fa91: jmp      0x14fcfe
  0x0014fa96: mov      rdx, rsi
  0x0014fa99: lea      rcx, [rbp - 0x40]
  0x0014fa9d: call     0x1403430
  0x0014faa2: lea      rcx, [rbp - 0x40]
  0x0014faa6: call     0x1403d30
  0x0014faab: mov      rbx, rax
  0x0014faae: lea      rdx, [rip + 0x1cc988b]
  0x0014fab5: mov      rcx, rax
  0x0014fab8: call     0x13c9620
  0x0014fabd: test     eax, eax
  0x0014fabf: je       0x14fad8
  0x0014fac1: lea      rdx, [rip + 0x1cc9888]
  0x0014fac8: mov      rcx, rbx
  0x0014facb: call     0x13c9620
  0x0014fad0: test     eax, eax
  0x0014fad2: jne      0x14fcfe
  0x0014fad8: mov      r8, rsi
  0x0014fadb: mov      rdx, r12
  0x0014fade: lea      rcx, [rbp - 0x70]
  0x0014fae2: call     0x14dd50
  0x0014fae7: nop      
  0x0014fae8: lea      rdx, [rip + 0x1ca01a1]
  0x0014faef: lea      rcx, [rsp + 0x59]
  0x0014faf4: call     0x6a630
  0x0014faf9: mov      rdx, rax
  0x0014fafc: lea      rcx, [rsp + 0x30]
  0x0014fb01: call     0x6a630
  0x0014fb06: xor      eax, eax
  0x0014fb08: mov      qword ptr [rsp + 0x30], rax
  0x0014fb0d: mov      qword ptr [rsp + 0x38], rax
  0x0014fb12: mov      byte ptr [rsp + 0x3f], 7
  0x0014fb17: lea      rdx, [rip + 0x1ca0172]
  0x0014fb1e: lea      rcx, [rsp + 0x5a]
  0x0014fb23: call     0x6a630
  0x0014fb28: mov      rdx, rax
  0x0014fb2b: lea      rcx, [rsp + 0x48]
  0x0014fb30: call     0x6a630
  0x0014fb35: xor      eax, eax
  0x0014fb37: mov      qword ptr [rsp + 0x48], rax
  0x0014fb3c: mov      qword ptr [rsp + 0x50], rax
  0x0014fb41: mov      byte ptr [rsp + 0x57], 7
  0x0014fb46: lea      r8, [rbp - 0x70]
  0x0014fb4a: lea      rdx, [rbp - 0x60]
  0x0014fb4e: mov      rcx, r13
  0x0014fb51: call     0x14e900
  0x0014fb56: mov      rbx, rax
  0x0014fb59: mov      rdx, rax
  0x0014fb5c: lea      rcx, [rsp + 0x30]
  0x0014fb61: call     0x6a760
  0x0014fb66: test     al, al
  0x0014fb68: je       0x14fb81
  0x0014fb6a: movups   xmm1, xmmword ptr [rsp + 0x30]
  0x0014fb6f: movups   xmmword ptr [rsp + 0x30], xmm6
  0x0014fb74: movups   xmm0, xmmword ptr [rbx]
  0x0014fb77: movups   xmmword ptr [rsp + 0x30], xmm0
  0x0014fb7c: movups   xmmword ptr [rbx], xmm1
  0x0014fb7f: jmp      0x14fbb3
  0x0014fb81: movsx    ecx, byte ptr [rbx + 0xf]
  0x0014fb85: mov      eax, ecx
  0x0014fb87: shr      eax, 7
  0x0014fb8a: test     al, 1
  0x0014fb8c: je       0x14fb9a
  0x0014fb8e: mov      rdx, qword ptr [rbx]
  0x0014fb91: mov      eax, dword ptr [rbx + 8]
  0x0014fb94: lea      r8, [rdx + rax*2]
  0x0014fb98: jmp      0x14fba8
  0x0014fb9a: mov      eax, 7
  0x0014fb9f: sub      eax, ecx
  0x0014fba1: lea      r8, [rbx + rax*2]
  0x0014fba5: mov      rdx, rbx
  0x0014fba8: lea      rcx, [rsp + 0x30]
  0x0014fbad: call     0x7dfe0
  0x0014fbb2: nop      
  0x0014fbb3: movsx    eax, byte ptr [rbp - 0x51]
  0x0014fbb7: shr      eax, 7
  0x0014fbba: and      al, 1
  0x0014fbbc: je       0x14fbe0
  0x0014fbbe: mov      eax, dword ptr [rbp - 0x54]
  0x0014fbc1: btr      eax, 0x1f
  0x0014fbc5: inc      eax
  0x0014fbc7: mov      rdx, qword ptr [rbp - 0x60]
  0x0014fbcb: test     rdx, rdx
  0x0014fbce: je       0x14fbe0
  0x0014fbd0: mov      r8d, eax
  0x0014fbd3: add      r8, r8
  0x0014fbd6: lea      rcx, [rbp - 0x60]
  0x0014fbda: call     0x6ab30
  0x0014fbdf: nop      
  0x0014fbe0: lea      rbx, [r13 + 0x20]
  0x0014fbe4: mov      rcx, qword ptr [rbx + 8]
  0x0014fbe8: sub      rcx, qword ptr [rbx]
  0x0014fbeb: movabs   rax, 0x6666666666666667
  0x0014fbf5: imul     rcx
  0x0014fbf8: sar      rdx, 4
  0x0014fbfc: mov      rax, rdx
  0x0014fbff: shr      rax, 0x3f
  0x0014fc03: add      rdx, rax
  0x0014fc06: mov      dword ptr [rsp + 0x40], edx
  0x0014fc0a: movsx    edx, byte ptr [rbp - 0x61]
  0x0014fc0e: mov      ecx, edx
  0x0014fc10: shr      ecx, 7
  0x0014fc13: and      cl, 1
  0x0014fc16: mov      r9, qword ptr [rbp - 0x70]
  0x0014fc1a: je       0x14fc25
  0x0014fc1c: mov      eax, dword ptr [rbp - 0x68]
  0x0014fc1f: lea      r8, [r9 + rax*2]
  0x0014fc23: jmp      0x14fc34
  0x0014fc25: mov      eax, 7
  0x0014fc2a: sub      eax, edx
  0x0014fc2c: lea      r8, [rbp - 0x70]
  0x0014fc30: lea      r8, [r8 + rax*2]
  0x0014fc34: lea      rdx, [rbp - 0x70]
  0x0014fc38: test     cl, cl
  0x0014fc3a: cmovne   rdx, r9
  0x0014fc3e: lea      rcx, [rsp + 0x48]
  0x0014fc43: call     0x7dfe0
  0x0014fc48: mov      rcx, qword ptr [rbx + 8]
  0x0014fc4c: lea      rdx, [rsp + 0x30]
  0x0014fc51: cmp      rcx, qword ptr [rbx + 0x10]
  0x0014fc55: jae      0x14fc66
  0x0014fc57: lea      rax, [rcx + 0x28]
  0x0014fc5b: mov      qword ptr [rbx + 8], rax
  0x0014fc5f: call     0x14e4e0
  0x0014fc64: jmp      0x14fc6f
  0x0014fc66: mov      rcx, rbx
  0x0014fc69: call     0x14e010
  0x0014fc6e: nop      
  0x0014fc6f: movsx    eax, byte ptr [rsp + 0x57]
  0x0014fc74: shr      eax, 7
  0x0014fc77: and      al, 1
  0x0014fc79: je       0x14fca0
  0x0014fc7b: mov      eax, dword ptr [rsp + 0x54]
  0x0014fc7f: btr      eax, 0x1f
  0x0014fc83: inc      eax
  0x0014fc85: mov      rdx, qword ptr [rsp + 0x48]
  0x0014fc8a: test     rdx, rdx
  0x0014fc8d: je       0x14fca0
  0x0014fc8f: mov      r8d, eax
  0x0014fc92: add      r8, r8
  0x0014fc95: lea      rcx, [rsp + 0x48]
  0x0014fc9a: call     0x6ab30
  0x0014fc9f: nop      
  0x0014fca0: movsx    eax, byte ptr [rsp + 0x3f]
  0x0014fca5: shr      eax, 7
  0x0014fca8: and      al, 1
  0x0014fcaa: je       0x14fcd1
  0x0014fcac: mov      eax, dword ptr [rsp + 0x3c]
  0x0014fcb0: btr      eax, 0x1f
  0x0014fcb4: inc      eax
  0x0014fcb6: mov      rdx, qword ptr [rsp + 0x30]
  0x0014fcbb: test     rdx, rdx
  0x0014fcbe: je       0x14fcd1
  0x0014fcc0: mov      r8d, eax
  0x0014fcc3: add      r8, r8
  0x0014fcc6: lea      rcx, [rsp + 0x30]
  0x0014fccb: call     0x6ab30
  0x0014fcd0: nop      
  0x0014fcd1: movsx    eax, byte ptr [rbp - 0x61]
  0x0014fcd5: shr      eax, 7
  0x0014fcd8: and      al, 1
  0x0014fcda: je       0x14fcfe
  0x0014fcdc: mov      eax, dword ptr [rbp - 0x64]
  0x0014fcdf: btr      eax, 0x1f
  0x0014fce3: inc      eax
  0x0014fce5: mov      rdx, qword ptr [rbp - 0x70]
  0x0014fce9: test     rdx, rdx
  0x0014fcec: je       0x14fcfe
  0x0014fcee: mov      r8d, eax
  0x0014fcf1: add      r8, r8
  0x0014fcf4: lea      rcx, [rbp - 0x70]
  0x0014fcf8: call     0x6ab30
  0x0014fcfd: nop      
  0x0014fcfe: movzx    ebx, byte ptr [rbp + 0x430]
  0x0014fd05: mov      rcx, r15
  0x0014fd08: call     0x13f3e20
  0x0014fd0d: test     rax, rax
  0x0014fd10: je       0x14fd28
  0x0014fd12: jmp      0x14f600
  0x0014fd17: mov      rcx, r15
  0x0014fd1a: call     0x13f3e20
  0x0014fd1f: test     rax, rax
  0x0014fd22: jne      0x14f600
  0x0014fd28: mov      rcx, r15
  0x0014fd2b: mov      rbx, qword ptr [rsp + 0x520]
  0x0014fd33: movaps   xmm6, xmmword ptr [rsp + 0x4d0]
  0x0014fd3b: add      rsp, 0x4e0
  0x0014fd42: pop      r15
  0x0014fd44: pop      r14
  0x0014fd46: pop      r13
  0x0014fd48: pop      r12
  0x0014fd4a: pop      rdi
  0x0014fd4b: pop      rsi
  0x0014fd4c: pop      rbp
  0x0014fd4d: jmp      0x13f3a00
  0x0014fd52: int3     
  0x0014fd53: int3     
  0x0014fd54: int3     
  0x0014fd55: int3     
  0x0014fd56: int3     
  0x0014fd57: int3     
  0x0014fd58: int3     
  0x0014fd59: int3     
  0x0014fd5a: int3     
  0x0014fd5b: int3     
  0x0014fd5c: int3     
  0x0014fd5d: int3     
  0x0014fd5e: int3     
  0x0014fd5f: int3     
  0x0014fd60: mov      qword ptr [rsp + 0x18], rsi
  0x0014fd65: push     r14
  0x0014fd67: sub      rsp, 0x20
  0x0014fd6b: mov      rsi, rcx
  0x0014fd6e: call     0x118f6e0
  0x0014fd73: test     byte ptr [rsi + 0x58], 1
  0x0014fd77: mov      r14, rax
  0x0014fd7a: jne      0x14fdca
  0x0014fd7c: mov      qword ptr [rsp + 0x30], rbx
  0x0014fd81: xor      ebx, ebx
  0x0014fd83: mov      qword ptr [rsp + 0x38], rdi
  0x0014fd88: mov      edi, ebx
  0x0014fd8a: nop      word ptr [rax + rax]
  0x0014fd90: mov      rcx, qword ptr [r14]
  0x0014fd93: mov      rdx, qword ptr [rip + 0x1cc912e]
  0x0014fd9a: add      rdx, rdi
  0x0014fd9d: mov      rax, qword ptr [rcx + 0xd8]
  0x0014fda4: mov      rcx, r14
  0x0014fda7: call     rax
  0x0014fda9: test     al, al
  0x0014fdab: jne      0x14fdbc
  0x0014fdad: inc      rbx
  0x0014fdb0: add      rdi, 0x10
  0x0014fdb4: cmp      rbx, 1
  0x0014fdb8: jb       0x14fd90
  0x0014fdba: jmp      0x14fdc0
  0x0014fdbc: or       dword ptr [rsi + 0x58], 1
  0x0014fdc0: mov      rbx, qword ptr [rsp + 0x30]
  0x0014fdc5: mov      rdi, qword ptr [rsp + 0x38]
  0x0014fdca: mov      rsi, qword ptr [rsp + 0x40]
  0x0014fdcf: add      rsp, 0x20
  0x0014fdd3: pop      r14
  0x0014fdd5: ret      
  0x0014fdd6: int3     
