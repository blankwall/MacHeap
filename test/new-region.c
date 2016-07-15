#include <mach/mach_init.h>
#include <mach/thread_act.h>
#include <mach/thread_policy.h>
#include <mach/error.h>
#include <stdio.h>
#include <stdlib.h>

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
initialize_tiny_region()
{
    int i;
    for (i = 0; i < 0x100; i++)
        malloc(0x10);
    return;
}

void
initialize_small_region()
{
    int i;
    for (i = 0; i < 0x100; i++)
        malloc(0x200);
    return;
}

int
main()
{
    asm("int3\n\t");
    initialize_tiny_region();
    asm("int3\n\t");
    initialize_small_region();
    asm("int3\n\t");
    return 0;
}
