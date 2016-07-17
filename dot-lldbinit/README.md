#LLDB Init

Usage
-----

Move lldbinit into .lldbinit in your ~/ directory

Move lldbinit.py into .lldbinit.py in your ~/ directory

Use .lldbinit.local in your ~/ directory for user-site configuration.

Use .lldbinit in any local directory for app-specific configuration.

Commands
--------

 - dw,dd,dc,df,dyd, etc.. - dump memory
 - ba,bp,bc,bl,be,bd - breakpoint management
 - history - malloc stack logs
 - address - page protections
 - p - to print using full expression parser 
 - lm - effective module listing 
 - ls - effective symbol lookup
 - bdisas - disassemble backwards from $pc
 - h - display current context
 - dsearch - search through disassembly 
 - more...

Example
-------

```
(lldb) h
-=[registers]=-
[rax: 0x0000000100000f50] [rbx: 0x0000000000000000] [rcx: 0x00007fff5fbffbd8]
[rdx: 0x00007fff5fbffae8] [rsi: 0x00007fff5fbffad8] [rdi: 0x0000000000000001]
[rsp: 0x00007fff5fbffaa0] [rbp: 0x00007fff5fbffab0] [ pc: 0x0000000100000f60]
[ r8: 0x0000000000000000] [ r9: 0x00007fff742760c8] [r10: 0x00000000ffffffff]
[r11: 0xffffffff00000000] [r12: 0x0000000000000000] [r13: 0x0000000000000000]
[r14: 0x0000000000000000] [r15: 0x0000000000000000] [efl: 0x0000000000000206]
[rflags: 00000000 NZ NS NO NC ND NI]

-=[stack]=-
7fff5fbffaa0 | 00007fff5fbffac8 000000005fc01036 | ..._....6.._....
7fff5fbffab0 | 00007fff5fbffac8 00007fff909e45ad | ..._.....E......
7fff5fbffac0 | 00007fff909e45ad 0000000000000000 | .E..............
7fff5fbffad0 | 0000000000000001 00007fff5fbffc38 | ........8.._....

-=[disassembly]=-
    0x100000f54 <+4>:  sub    rsp, 0x10
    0x100000f58 <+8>:  mov    dword ptr [rbp - 0x4], 0x0
    0x100000f5f <+15>: int3
->  0x100000f60 <+16>: call   0x100000ed0               ; initialize_tiny_region
    0x100000f65 <+21>: int3
    0x100000f66 <+22>: call   0x100000f10               ; initialize_small_region
    0x100000f6b <+27>: int3
```

```
(lldb) bdisas 4
    0x100000f51 <+1>:  mov    rbp, rsp
    0x100000f54 <+4>:  sub    rsp, 0x10
    0x100000f58 <+8>:  mov    dword ptr [rbp - 0x4], 0x0
    0x100000f5f <+15>: int3
->  0x100000f60 <+16>: call   0x100000ed0               ; initialize_tiny_region
```

```
(lldb) p poi($rax+10)

19703248369745920 -- 0x46000000000000

```

```
(lldb) dw -c 4 $rsp
7fff5fbff9e0 | 0000 0000 0000 0000 0000 0000 0000 0000 | ................
7fff5fbff9f0 | 0000 0000 0000 0000 0000 0000 0000 0000 | ................
7fff5fbffa00 | 0000 0000 0000 0000 0000 0000 0000 0000 | ................
7fff5fbffa10 | 8d90 eea3 3ec1 f700 0028 0000 002c 0000 | .....>..(...,...
```

```
(lldb) lm *malloc*

[25] libsystem_malloc.dylib x86_64-apple-macosx /usr/lib/system/libsystem_malloc.dylib 0x7fff98a7c000:+0x26000 num_sections=3 num_symbols=412
```

```
(lldb) ls printf
[0] overflow`printf type=5 0x100000e5e:+0x6
[1] libcache.dylib`printf type=5 0x7fff975d2530:+0x6
[2] libcommonCrypto.dylib`printf type=5 0x7fff93f53a9a:+0x6
[3] libsystem_c.dylib`printf type=BlockPointer 0x7fff86dd815c:+0xe1 external
[4] libsystem_c.dylib`printf type=5 0x7fff86e1acaa:+0x6 synthetic
[5] libsystem_dnssd.dylib`printf type=5 0x7fff8b2ba2fc:+0x6
[6] libsystem_malloc.dylib`printf type=5 0x7fff98a954cc:+0x6
[7] libauto.dylib`printf type=5 0x7fff88b6e15a:+0x6
[8] libobjc.A.dylib`printf type=5 0x7fff8d302ec6:+0x6
```

```
(lldb) df $rsp
7fff5fbffaa0 | 27667178215494909952.000000         0.000000 27679242057074868224.000000         0.000000 | ..._....6.._....
7fff5fbffab0 | 27667178215494909952.000000         0.000000        -0.000000         0.000000            | ..._.....E......
7fff5fbffac0 |        -0.000000         0.000000         0.000000         0.000000                       | .E..............
7fff5fbffad0 |         0.000000         0.000000 27667987456052953088.000000         0.000000            | ........8.._....
7fff5fbffae0 |         0.000000         0.000000 27668075416983175168.000000         0.000000            | ........`.._....
7fff5fbffaf0 | 27668242542750597120.000000         0.000000 27668273329076174848.000000         0.000000 | ..._......._....
```

View all calls in first 8 instructions of function named main
-s allows you to disassemble from an expression
```
(lldb) dsearch -n main call -c 8
new-region`main:
->  0x100000f60 <+16>: call   0x100000ed0               ; initialize_tiny_region
    0x100000f66 <+22>: call   0x100000f10               ; initialize_small_region
```
