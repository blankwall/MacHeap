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
 - more...

Example
-------

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
