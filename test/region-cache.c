#include <stdio.h>
#include <stdlib.h>

int
main()
{
    int i; char* p;
    for (i = 0; i < 0x100; i++)
        malloc(0x10);
    asm("int3\n\t");

    // should free this chunk to the mag_last_free cache
    p = malloc(0x10);
    printf("%p\n", p);
    asm("int3\n\t");
    free(p);
    asm("int3\n\t");
    printf("%p -- %p\n", malloc(0x10), p);
    asm("int3\n\t");
    return 0;
}
