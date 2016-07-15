#include <mach/mach_init.h>
#include <mach/thread_act.h>
#include <mach/thread_policy.h>
#include <mach/error.h>
#include <stdio.h>
#include <stdlib.h>

const int Quantum = 0x10;

int
get_core_number()
{
    char *p;
    struct {
        uint16_t sel;
        void* address;
    } idtr;
    asm("sidt %0\n\t": "=m"(idtr));

    return idtr.sel & 0x1f;
}

int
set_core_number(int n)
{
    int res;
    thread_port_t tp = mach_thread_self();
    thread_affinity_policy_data_t policy = {n};

    res = thread_policy_set(tp, THREAD_AFFINITY_POLICY, (thread_policy_t)&policy, 1);
    return res == err_none? 0 : -1;
}

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
    char* array[0x20];

    printf("filling up 0x40 slots\n");
    region_spray(Quantum, 0x40);
    asm("int3\n\t");

    printf("allocating 0x%x slots\n", 0x20);
    for (i=0; i < 0x20; i++)
        array[i] = malloc(Quantum);
    printf("%p - %p\n", array[0], array[sizeof(array)/sizeof(*array)-1]);
    asm("int3\n\t");

    printf("freeing elements 0x8 to 0x18\n");
    for (i = 0; i < 0x10; i++) {
        free(array[i+8]);
        printf("%d:%p\n", i+8, array[i+8]);
    }
    asm("int3\n\t");

    printf("allocating 4 chunks\n");
    for (i = 0; i < 4; i++) {
        printf("%d:%p\n", i, malloc(Quantum));
    }
    asm("int3\n\t");

    return 0;
}
