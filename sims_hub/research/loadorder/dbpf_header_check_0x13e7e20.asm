; function start 0x13e7e20
  0x013e7e20: mov      qword ptr [rsp + 8], rbx
  0x013e7e25: mov      qword ptr [rsp + 0x10], rbp
  0x013e7e2a: mov      qword ptr [rsp + 0x18], rsi
  0x013e7e2f: push     rdi
  0x013e7e30: sub      rsp, 0x20
  0x013e7e34: lea      rbp, [rcx + 0x2f8]
  0x013e7e3b: mov      rbx, rdx
  0x013e7e3e: mov      rsi, rcx
  0x013e7e41: lea      rdx, [rip + 0xc70130]
  0x013e7e48: mov      rcx, rbp
  0x013e7e4b: xor      dil, dil
  0x013e7e4e: call     0x13ead80
  0x013e7e53: cmp      qword ptr [rsi + 0x2b0], 0
  0x013e7e5b: je       0x13e7e66
  0x013e7e5d: mov      rsi, qword ptr [rsi + 0x2b8]
  0x013e7e64: jmp      0x13e7e76
  0x013e7e66: mov      rcx, qword ptr [rsi + 0x2a8]
  0x013e7e6d: mov      rax, qword ptr [rcx]
  0x013e7e70: call     qword ptr [rax + 0x38]
  0x013e7e73: mov      rsi, rax
  0x013e7e76: mov      rcx, rbp
  0x013e7e79: call     0x13eae40
  0x013e7e7e: cmp      dword ptr [rbx], 0x46504244
  0x013e7e84: jne      0x13e7eb9
  0x013e7e86: cmp      dword ptr [rbx + 4], 2
  0x013e7e8a: ja       0x13e7eb9
  0x013e7e8c: cmp      dword ptr [rbx + 0x24], 0x7ffffff
  0x013e7e93: jae      0x13e7eb9
  0x013e7e95: mov      rcx, qword ptr [rbx + 0x40]
  0x013e7e99: cmp      rcx, rsi
  0x013e7e9c: jae      0x13e7eb9
  0x013e7e9e: mov      eax, dword ptr [rbx + 0x2c]
  0x013e7ea1: add      rax, rcx
  0x013e7ea4: cmp      rax, rsi
  0x013e7ea7: ja       0x13e7eb9
  0x013e7ea9: cmp      dword ptr [rbx + 0x3c], 0
  0x013e7ead: mov      eax, 1
  0x013e7eb2: movzx    edi, dil
  0x013e7eb6: cmovne   edi, eax
  0x013e7eb9: mov      rcx, qword ptr [rbx + 0x40]
  0x013e7ebd: test     rcx, rcx
  0x013e7ec0: je       0x13e7ed1
  0x013e7ec2: mov      eax, dword ptr [rbx + 0x28]
  0x013e7ec5: test     eax, eax
  0x013e7ec7: je       0x13e7ed1
  0x013e7ec9: cmp      rcx, rax
  0x013e7ecc: sete     al
  0x013e7ecf: jmp      0x13e7ed5
  0x013e7ed1: movzx    eax, dil
  0x013e7ed5: mov      rbx, qword ptr [rsp + 0x30]
  0x013e7eda: mov      rbp, qword ptr [rsp + 0x38]
  0x013e7edf: mov      rsi, qword ptr [rsp + 0x40]
  0x013e7ee4: add      rsp, 0x20
  0x013e7ee8: pop      rdi
  0x013e7ee9: ret      
  0x013e7eea: int3     
