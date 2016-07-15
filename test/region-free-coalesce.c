#include <stdio.h>
#include <stdlib.h>

int
main()
{
    int i; char* p[0x10];
    for (i = 0; i < 0x100; i++)
        malloc(0x10);
    asm("int3\n\t");
    for (i = 0; i < sizeof(p)/sizeof(*p); i++)
        p[i] = malloc(0x10);

    // should try and coalesce w/ the front and back chunks
    asm("int3\n\t");
    free(p[3]);
    asm("int3\n\t");
    free(p[5]);
    asm("int3\n\t");
    free(p[4]);
    asm("int3\n\t");
    return 0;
}
