#MacHeap

About
-----
MacHeap is a LLDB Python script for use with OS X heap introspection. All heap structures are parsed and presented as Python objects accessible via dictionaries. This allows full understanding and representation of the internal heap state and structures of the default malloc on OS X. More documentation will be added in the future. Also check out the IDB directory for the marked up default malloc IDB with full structures and the LLDB init directory for a unique, featureful, and easily extensible LLDB init script.

Usage
-----

Basic usage is run lldb and once you are at a point where you want to inspect type:
```
script execfile ("scripts/load.py")
```
Load.py is going to set up the basic structures and give you access to a few variables. You can look at that file more to see exactly what it exposes and some of the other features available.  Below is a quick example on how to use it.

Example
-----
Initialized LLDB instance using the tiny-slot-multi-frag test and run forward till the third break. 

```
lldb test/tiny-slot-multi-frag
(lldb) target create "test/tiny-slot-multi-frag"
Current executable set to 'test/tiny-slot-multi-frag' (x86_64).
(lldb) r
...

Process 47573 stopped
* thread #1: tid = 0x44343, 0x0000000100000e4d tiny-slot-multi-frag`main + 413, queue = 'com.apple.main-thread', stop reason = EXC_BREAKPOINT (code=EXC_I386_BPT, subcode=0x0)
    frame #0: 0x0000000100000e4d tiny-slot-multi-frag`main + 413
tiny-slot-multi-frag`main:
->  0x100000e4d <+413>: lea    rdi, [rip + 0x146]        ; "allocating 4 Q*2 chunks\n"
    0x100000e54 <+420>: mov    al, 0x0
    0x100000e56 <+422>: call   0x100000ef8               ; symbol stub for: printf
    0x100000e5b <+427>: mov    dword ptr [rbp - 0x418], 0x0

(lldb) script execfile("scripts/load.py")
(lldb) script
Python Interactive Interpreter. To exit, type 'quit()', 'exit()' or Ctrl-D.
>>> z
[100034000] <instance macheap.malloc_zones '*unnamed_x11481a750'> macheap._object_[2] DefaultMallocZone/8
>>> z[0]
[100034000] <instance macheap._object_<macheap.zone_t> '0'> DefaultMallocZone version=8 complex_zone=0x100005000
>>> z[0].d.l
<class macheap.zone_t> '*0'
[100004000] <instance macheap.malloc_zone_t 'basic_zone'> name=u'DefaultMallocZone' version=8 reserved1=0x0 reserved2=0x0 ...
[100004088] <instance dynamic.block(3960) 'pad'> "\x00\x00\x00\x00\x00\x00\x00   ..skipped ~3940 bytes..  \x00\x00\x00\x00\x00\x00"
[100005000] <instance macheap.szone_t 'complex_zone'> "\xff\xff\xff\xff\xff\xff\xff   ..skipped ~2144 bytes..  \x00\x00\x00\x00\x00\x00"
```
***z*** represents the overall zone structure, ***z[0]*** being the default zone. ***a*** represents the interior complex zone of ***z[0]***
```
>>> t = a.mag("t")
>>> t
[100007000] <instance macheap.magazine_array '*tiny_magazines'> macheap.magazine_t[9] "\x20\x44\xc6\x77\xff\x7f\x00  ..skipped ~23020 bytes..  \x00\x00\x00\x00\x00\x00"
```
***t*** now holds an array of tiny magazines from the default zone 

Note: all allocations were forced into the first magazine with malloc breakpoints using com.py available in the repo
```
>>> t[1]
<class macheap.magazine_t> '1' {magazine_size='tiny'}
[100007a00] <instance macheap._malloc_lock_s 'magazine_lock'> "\x20\x44\xc6\x77\xff\x7f\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
[100007a10] <instance macheap.boolean_t 'alloc_underway'> 0x00000000 (0)
[100007a14] <instance dynamic.block(4) 'padding(alloc_underway)'> "\x00\x00\x00\x00"
[100007a18] <instance macheap._mag_last_free(ptype._value_, _calculate_) 'mag_last_free'> *0x1001037b0 msize=14(+224)
[100007a20] <instance ptype.pointer_t<macheap.region_t> 'mag_last_free_rgn'> *0x100100000
[100007a28] <instance macheap._mag_free_list 'mag_free_list'> "\x70\x2d\x10\x00\x01\x00\x00   ..skipped ~2028 bytes..  \x00\x00\x00\x00\x00\x00"
[100008228] <instance macheap._mag_bitmap 'mag_bitmap'> XX...XXX.X..X..X.X.X.X.X.X.X.X.X.X.X.X.X.X.X.X.X.X.X.X.X.X.X.X.X................................................................................................................................................................................................
[100008248] <instance macheap.size_t 'mag_bytes_free_at_end'> 0x00000000000f1210 (987664)
[100008250] <instance macheap.size_t 'mag_bytes_free_at_start'> 0x0000000000000000 (0)
[100008258] <instance ptype.pointer_t<macheap.region_t> 'mag_last_region'> *0x100100000
[100008260] <instance macheap.size_t 'mag_num_objects'> 0x00000000000000fe (254)
[100008268] <instance macheap.size_t 'mag_num_bytes_in_objects'> 0x0000000000006fe0 (28640)
[100008270] <instance macheap.size_t 'num_bytes_in_magazine'> 0x00000000000fc080 (1032320)
[100008278] <instance macheap.unsigned 'recirculation_entries'> 0x00000001 (1)
[10000827c] <instance dynamic.block(4) 'padding(recirculation_entries)'> "\x00\x00\x00\x00"
[100008280] <instance macheap.fpointer_t(macheap.region_t, ('trailer',)) 'firstNode'> *0x1001fc080
[100008288] <instance macheap.fpointer_t(macheap.region_t, ('trailer',)) 'lastNode'> *0x1001fc080
[100008290] <instance dynamic.array(macheap.uintptr_t,46) 'pad'> "\x00\x00\x00\x00\x00\x00\x00 ..skipped ~348 bytes.. \x00\x00\x00\x00\x00\x00\x00"
```
And viewing the free list
```
>>> print t[1].dump()
[1] 0x100102d70
[2] 0x100102d90
[6] 0x100102ea0
[7] 0x100102dd0
[8] 0x100102f60
...
[60] 0x100109f30
[62] 0x10010a6b0
```
Can also look at region information via the magazine trailer
```
>>> r = t[1]['firstnode'].d.l
>>>> bit.string(r.bitmap())
'1111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111
...
00000000000000000000000000000111111111111111111111111111111111111111111111111111111110000000000000000000000000000000000000000000000000000000000111111111111111111111111111111111111111111111111111111111100000000000000000000000000000000000000000000000000000000000011111111111111111111111111111111111111111111111111111111111100000000000000000000000000000000000000000000000000000000000000111111111111111111111111111111111111111111111111111111111111111'
```
bit is an internal module given allowing the bitmap to easily be represented as a string
```
>>> r.at(0x1001090f0)
[1001090f0] <instance dynamic.block(16) '2319'> 1001090f0  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
```
using region functionality to determine where in the map a block is located
