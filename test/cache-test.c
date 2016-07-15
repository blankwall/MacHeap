#include <mach/mach_init.h>
#include <mach/thread_act.h>
#include <mach/thread_policy.h>
#include <mach/error.h>
#include <stdio.h>
#include <stdlib.h>

void tiny_test(){
	printf("TINY CACHE TEST\n");
	int* x = malloc(64);
	printf("Putting %p onto the cache\n", x);
	free(x);

	x = malloc(32);
	printf("Allocated 32 bytes @ %p (not from the cache)\n", x);

	x = malloc(512);
	printf("Allocated 512 bytes @ %p (wont effect cache)\n", x);
	free(x);

	x = malloc(64);
	printf("Allocated 64 bytes @ %p (from the cache)\n", x);
}

void lldb_free_list_tiny(){
	int* x, *y, *xe[10];

	asm("int3\n\t");
/*(lldb) script execfile("load.py")
CACHE
<class dynamic.block(208)> '*mag_last_free'
100203550  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
100203560  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
100203570  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
100203580  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
 ..skipped 5 rows, 80 bytes..
1002035e0  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
1002035f0  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
100203600  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
100203610  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU

FREE LIST
(lldb) script free.dump()
[0][0x10010e428L]:  0x100200390 [240]
[4][0x10010e468L]:  0x100203620 [9]
[31][0x10010e618L]:  0x100202b80 [65] <--> 0x100202fb0 [70]
*/

	xe[0] = malloc(64);
/*

returned 0x100203620

Took 64 bytes from slot 2 

(lldb) script free.dump()
[0][0x10010e428L]:  0x100200390 [240]
[2][0x10010e448L]:  0x100203660 [5]
[31][0x10010e618L]:  0x100202b80 [65] <--> 0x100202fb0 [70]
*/
	xe[1] = malloc(128);

/*

returned 0x100202b80

(lldb) script free.dump()
[0][0x10010e428L]:  0x100200390 [240]
[2][0x10010e448L]:  0x100203660 [5]
[28][0x10010e5e8L]:  0x100202c00 [57]
[31][0x10010e618L]:  0x100202fb0 [70]
*/
	xe[2] = malloc(256);

/*
returned 0x100202c00

[0][0x10010e428L]:  0x100200390 [240]
[2][0x10010e448L]:  0x100203660 [5]
[20][0x10010e568L]:  0x100202d00 [41]
[31][0x10010e618L]:  0x100202fb0 [70]
*/
	xe[3] = malloc(320);

/*
returned  0x100202d00

[0][0x10010e428L]:  0x100200390 [240]
[2][0x10010e448L]:  0x100203660 [5]
[10][0x10010e4c8L]:  0x100202e40 [21]
[31][0x10010e618L]:  0x100202fb0 [70]
*/
	printf("RET: %p -%p - %p - %p\n", xe[0], xe[1], xe[2], xe[3]);

/*
cache unaffected by previous allocations 

Allocator gets msize(size / quantum) 
finds slot based on msize (roughly msize/2)
starts searching free list from there to try and find enough free space
stops search at first adequate block
returns block coalesces free list  and reslots any item the shrunk due to the allocation
*/


	asm("int3\n\t");
	y = malloc(16);
	free(y);
/*
overwrites cache - [100200390] <instance dynamic.block(16) '*mag_last_free'> 100200390  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU

cache moved to free list --block # 6

[2][0x10010e448L]:  0x100203660 [5]
[6][0x10010e488L]:  0x100203550 [13]
[10][0x10010e4c8L]:  0x100202e40 [21]
[31][0x10010e618L]:  0x100202fb0 [70]

*/
	asm("int3\n\t");

	x = malloc(512);
	free(x);

/*
Cache unaffected took allocation from 0x100202fb0

[2][0x10010e448L]:  0x100203660 [5]
[6][0x10010e488L]:  0x100203550 [13]
[10][0x10010e4c8L]:  0x100202e40 [21]
[18][0x10010e548L]:  0x1002031b0 [38]
*/

	asm("int3\n\t");
	for(int i = 0; i < 4; ++i){
		printf("FREEING %p of size %d\n", xe[i], i);
		asm("int3\n\t");
		free(xe[i]);
	}
/*
(lldb) script execfile("load.py")
<class dynamic.block(128)> '*mag_last_free'
100202b80  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
100202b90  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
100202ba0  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
100202bb0  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
100202bc0  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
100202bd0  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
100202be0  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
100202bf0  55 55 55 55 55 55 55 55  55 55 55 55 55 55 55 55  UUUUUUUUUUUUUUUU
(lldb) script free.dump()
[0][0x10010e428L]:  0x100200390 [240]
[10][0x10010e4c8L]:  0x100203550 [22]
[28][0x10010e5e8L]:  0x100202c00 [57]
[31][0x10010e618L]:  0x100202fb0 [70]
*/
}


void small_test(){
	int* x, *xe[10];

	// for(int i = 0; i < 100; ++i){
	// 	x = malloc(1024+(i*512));
	// 	free(x);
	// }

asm("int3\n\t");
	x = malloc(1024);
	asm("int3\n\t");

	printf("Allocated 1024 bytes @ %p (not from the cache)\n", x);
	free(x);
	x = malloc(1024);
	printf("Allocated 1024 bytes @ %p (cache?)\n", x);

	xe[0] = malloc(1024);
	xe[1] = malloc(1024);
	xe[2] = malloc(1024);

	free(xe[0]);
	free(xe[1]);
	free(xe[2]);
 //    asm("int3\n\t");
	// x = malloc(1024);
	// free(x);
	// x = malloc(1024);
	// for(int i = 1; i< 5; ++i){
	// 	xe[i-1] = malloc(1024*i);
	// }

	// for(int i = 1; i< 5; ++i){
	// 	free(xe[i-1]);
	// }

}

int main(){
	small_test();
	lldb_free_list_tiny();
	tiny_test();
}