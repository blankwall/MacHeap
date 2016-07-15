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
    int i;
    char* array[128];

    printf("filling up 0x40 slots\n");
    region_spray(Quantum, 0x40);
    asm("int3\n\t");

    printf("allocating 0x%x 64 slots\n", 64);
    for (i=0; i < 128; i+=2){
        array[i] = malloc(Quantum*i);
    array[i+1] = malloc(Quantum*i);
    }
        printf("%p - %p\n", array[0], array[sizeof(array)/sizeof(*array)-1]);
    asm("int3\n\t");

    printf("freeing every other element\n");
    for (i = 0; i < 128; i++) {
          if((i%2)==0) { free(array[i]);
          printf("%d:%p\n", i, array[i]);
          }
    }
    asm("int3\n\t");

    printf("allocating 4 Q*2 chunks\n");
    for (i = 0; i < 4; i++) {
        printf("%d:%p\n", i, malloc(Quantum*2));
    }
    asm("int3\n\t");

    return 0;
}
