; function start 0x13e3540
  0x013e3540: mov      byte ptr [rsp + 0x20], r9b
  0x013e3545: push     rbp
  0x013e3546: push     rbx
  0x013e3547: push     rdi
  0x013e3548: push     r13
  0x013e354a: push     r14
  0x013e354c: push     r15
  0x013e354e: lea      rbp, [rsp - 0x2f]
  0x013e3553: sub      rsp, 0x88
  0x013e355a: mov      r13d, dword ptr [rdx]
  0x013e355d: movzx    r15d, r9b
  0x013e3561: shr      r8, 2
  0x013e3565: movzx    r9d, r13b
  0x013e3569: and      r9b, 1
  0x013e356d: mov      edi, 0xffffffff
  0x013e3572: mov      r14, rcx
  0x013e3575: mov      byte ptr [rbp + 0x6f], r9b
  0x013e3579: mov      dword ptr [rbp + 0x77], edi
  0x013e357c: lea      r11, [rdx + r8*4]
  0x013e3580: mov      r8d, r13d
  0x013e3583: shr      r8d, 1
  0x013e3586: shr      r13d, 2
  0x013e358a: and      r8b, 1
  0x013e358e: and      r13b, 1
  0x013e3592: mov      qword ptr [rbp - 0x11], r11
  0x013e3596: mov      dword ptr [rbp - 0x21], r8d
  0x013e359a: test     r9b, r9b
  0x013e359d: je       0x13e35a5
  0x013e359f: mov      r10d, dword ptr [rdx + 4]
  0x013e35a3: jmp      0x13e35a8
  0x013e35a5: mov      r10d, edi
  0x013e35a8: movzx    eax, r9b
  0x013e35ac: mov      dword ptr [rbp - 0x25], r10d
  0x013e35b0: lea      rcx, [rdx + rax*4]
  0x013e35b4: lea      rbx, [rcx + 4]
  0x013e35b8: test     r8b, r8b
  0x013e35bb: je       0x13e35c1
  0x013e35bd: mov      eax, dword ptr [rbx]
  0x013e35bf: jmp      0x13e35c3
  0x013e35c1: mov      eax, edi
  0x013e35c3: test     r8b, r8b
  0x013e35c6: mov      dword ptr [rbp - 0x29], eax
  0x013e35c9: cmove    rbx, rcx
  0x013e35cd: add      rbx, 4
  0x013e35d1: test     r13b, r13b
  0x013e35d4: je       0x13e35df
  0x013e35d6: mov      edi, dword ptr [rbx]
  0x013e35d8: add      rbx, 4
  0x013e35dc: mov      dword ptr [rbp + 0x77], edi
  0x013e35df: cmp      rbx, r11
  0x013e35e2: jae      0x13e3820
  0x013e35e8: mov      qword ptr [rsp + 0xc0], rsi
  0x013e35f0: mov      qword ptr [rsp + 0x80], r12
  0x013e35f8: xor      r12d, r12d
  0x013e35fb: nop      dword ptr [rax + rax]
  0x013e3600: test     r9b, r9b
  0x013e3603: je       0x13e360e
  0x013e3605: mov      r11d, r10d
  0x013e3608: mov      dword ptr [rbp - 1], r10d
  0x013e360c: jmp      0x13e3619
  0x013e360e: mov      r11d, dword ptr [rbx]
  0x013e3611: add      rbx, 4
  0x013e3615: mov      dword ptr [rbp - 1], r11d
  0x013e3619: test     r8b, r8b
  0x013e361c: je       0x13e3626
  0x013e361e: mov      r10d, eax
  0x013e3621: mov      dword ptr [rbp + 3], eax
  0x013e3624: jmp      0x13e3631
  0x013e3626: mov      r10d, dword ptr [rbx]
  0x013e3629: add      rbx, 4
  0x013e362d: mov      dword ptr [rbp + 3], r10d
  0x013e3631: test     r13b, r13b
  0x013e3634: je       0x13e363e
  0x013e3636: mov      r8d, edi
  0x013e3639: mov      dword ptr [rbp - 5], edi
  0x013e363c: jmp      0x13e3649
  0x013e363e: mov      r8d, dword ptr [rbx]
  0x013e3641: add      rbx, 4
  0x013e3645: mov      dword ptr [rbp - 5], r8d
  0x013e3649: mov      eax, dword ptr [rbx + 4]
  0x013e364c: mov      edi, dword ptr [rbx]
  0x013e364e: add      rbx, 8
  0x013e3652: mov      dword ptr [rbp - 9], edi
  0x013e3655: mov      qword ptr [rbp + 7], rax
  0x013e3659: cmp      eax, 0xffff0000
  0x013e365e: jne      0x13e366b
  0x013e3660: mov      rax, qword ptr [rbx]
  0x013e3663: add      rbx, 8
  0x013e3667: mov      qword ptr [rbp + 7], rax
  0x013e366b: mov      eax, dword ptr [rbx]
  0x013e366d: mov      ecx, eax
  0x013e366f: mov      r9d, eax
  0x013e3672: btr      ecx, 0x1f
  0x013e3676: shr      r9, 0x1f
  0x013e367a: mov      qword ptr [rbp + 0xf], rcx
  0x013e367e: mov      edx, ecx
  0x013e3680: cmp      rcx, 0x3fffffff
  0x013e3687: jne      0x13e3691
  0x013e3689: mov      rdx, qword ptr [rbx + 4]
  0x013e368d: mov      qword ptr [rbp + 0xf], rdx
  0x013e3691: mov      ecx, 4
  0x013e3696: mov      eax, 0xc
  0x013e369b: cmovne   eax, ecx
  0x013e369e: add      rax, rbx
  0x013e36a1: mov      ecx, dword ptr [rax]
  0x013e36a3: lea      rbx, [rax + 4]
  0x013e36a7: mov      qword ptr [rbp + 0x17], rcx
  0x013e36ab: cmp      rdx, 0x3fffffff
  0x013e36b2: jne      0x13e36bf
  0x013e36b4: mov      rcx, qword ptr [rbx]
  0x013e36b7: lea      rbx, [rax + 0xc]
  0x013e36bb: mov      qword ptr [rbp + 0x17], rcx
  0x013e36bf: test     r9b, r9b
  0x013e36c2: je       0x13e36d5
  0x013e36c4: mov      eax, dword ptr [rbx]
  0x013e36c6: add      rbx, 4
  0x013e36ca: mov      word ptr [rbp + 0x1f], ax
  0x013e36ce: shr      eax, 0x10
  0x013e36d1: and      al, 1
  0x013e36d3: jmp      0x13e36ec
  0x013e36d5: cmp      rdx, rcx
  0x013e36d8: jne      0x13e36e1
  0x013e36da: mov      word ptr [rbp + 0x1f], r12w
  0x013e36df: jmp      0x13e36ea
  0x013e36e1: mov      eax, 0xffff
  0x013e36e6: mov      word ptr [rbp + 0x1f], ax
  0x013e36ea: xor      al, al
  0x013e36ec: movups   xmm0, xmmword ptr [rbp - 9]
  0x013e36f0: mov      r12d, dword ptr [r14 + 0x20]
  0x013e36f4: test     r15b, r15b
  0x013e36f7: movzx    eax, al
  0x013e36fa: mov      ecx, 1
  0x013e36ff: cmovne   eax, ecx
  0x013e3702: psrldq   xmm0, 8
  0x013e3707: mov      byte ptr [rbp + 0x21], al
  0x013e370a: xor      edx, edx
  0x013e370c: movq     r15, xmm0
  0x013e3711: shr      r15, 0x20
  0x013e3715: xor      r15, rdi
  0x013e3718: mov      rax, r15
  0x013e371b: div      r12
  0x013e371e: mov      rax, qword ptr [r14 + 0x18]
  0x013e3722: mov      ecx, edx
  0x013e3724: mov      rsi, rdx
  0x013e3727: mov      r9, qword ptr [rax + rcx*8]
  0x013e372b: test     r9, r9
  0x013e372e: je       0x13e3754
  0x013e3730: cmp      edi, dword ptr [r9]
  0x013e3733: jne      0x13e374b
  0x013e3735: cmp      r11d, dword ptr [r9 + 8]
  0x013e3739: jne      0x13e374b
  0x013e373b: cmp      r10d, dword ptr [r9 + 0xc]
  0x013e373f: jne      0x13e374b
  0x013e3741: cmp      r8d, dword ptr [r9 + 4]
  0x013e3745: je       0x13e37eb
  0x013e374b: mov      r9, qword ptr [r9 + 0x30]
  0x013e374f: test     r9, r9
  0x013e3752: jne      0x13e3730
  0x013e3754: mov      r9d, dword ptr [r14 + 0x24]
  0x013e3758: lea      rcx, [r14 + 0x28]
  0x013e375c: mov      eax, 1
  0x013e3761: lea      rdx, [rbp - 0x19]
  0x013e3765: mov      r8d, r12d
  0x013e3768: mov      dword ptr [rsp + 0x20], eax
  0x013e376c: call     0x13d95b0
  0x013e3771: mov      rcx, qword ptr [r14 + 0x38]
  0x013e3775: xor      r8d, r8d
  0x013e3778: mov      r9d, dword ptr [r14 + 0x40]
  0x013e377c: mov      rax, qword ptr [rcx]
  0x013e377f: lea      edx, [r8 + 0x38]
  0x013e3783: call     qword ptr [rax + 0x10]
  0x013e3786: movups   xmm0, xmmword ptr [rbp - 9]
  0x013e378a: xor      r12d, r12d
  0x013e378d: mov      rdi, rax
  0x013e3790: movups   xmmword ptr [rax], xmm0
  0x013e3793: movups   xmm0, xmmword ptr [rbp + 7]
  0x013e3797: movups   xmmword ptr [rax + 0x10], xmm0
  0x013e379b: movups   xmm0, xmmword ptr [rbp + 0x17]
  0x013e379f: movups   xmmword ptr [rax + 0x20], xmm0
  0x013e37a3: mov      qword ptr [rax + 0x30], r12
  0x013e37a7: cmp      byte ptr [rbp - 0x19], r12b
  0x013e37ab: je       0x13e37c7
  0x013e37ad: mov      r8d, dword ptr [rbp - 0x15]
  0x013e37b1: lea      rcx, [r14 + 0x10]
  0x013e37b5: xor      edx, edx
  0x013e37b7: mov      rax, r15
  0x013e37ba: div      r8
  0x013e37bd: mov      esi, edx
  0x013e37bf: mov      edx, r8d
  0x013e37c2: call     0x13e2a30
  0x013e37c7: mov      eax, esi
  0x013e37c9: lea      rdx, [rax*8]
  0x013e37d1: mov      rax, qword ptr [r14 + 0x18]
  0x013e37d5: mov      rcx, qword ptr [rdx + rax]
  0x013e37d9: mov      qword ptr [rdi + 0x30], rcx
  0x013e37dd: mov      rax, qword ptr [r14 + 0x18]
  0x013e37e1: mov      qword ptr [rdx + rax], rdi
  0x013e37e5: inc      dword ptr [r14 + 0x24]
  0x013e37e9: jmp      0x13e37ee
  0x013e37eb: xor      r12d, r12d
  0x013e37ee: mov      r8d, dword ptr [rbp - 0x21]
  0x013e37f2: movzx    r9d, byte ptr [rbp + 0x6f]
  0x013e37f7: mov      edi, dword ptr [rbp + 0x77]
  0x013e37fa: mov      eax, dword ptr [rbp - 0x29]
  0x013e37fd: mov      r10d, dword ptr [rbp - 0x25]
  0x013e3801: movzx    r15d, byte ptr [rbp + 0x7f]
  0x013e3806: cmp      rbx, qword ptr [rbp - 0x11]
  0x013e380a: jb       0x13e3600
  0x013e3810: mov      r12, qword ptr [rsp + 0x80]
  0x013e3818: mov      rsi, qword ptr [rsp + 0xc0]
  0x013e3820: mov      al, 1
  0x013e3822: add      rsp, 0x88
  0x013e3829: pop      r15
  0x013e382b: pop      r14
  0x013e382d: pop      r13
  0x013e382f: pop      rdi
  0x013e3830: pop      rbx
  0x013e3831: pop      rbp
  0x013e3832: ret      
  0x013e3833: int3     
