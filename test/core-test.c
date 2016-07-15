#include <mach/mach_init.h>
#include <mach/thread_act.h>
#include <mach/thread_policy.h>
#include <mach/error.h>
#include <stdio.h>
#include <time.h>

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

int
main()
{
    time_t tl;
    set_core_number(2);

    printf("core number is : %d\n", get_core_number());
    tl = time(NULL) + 5;
    printf("core number is : %d\n", get_core_number());
    while (time(NULL) < tl) {}
    printf("core number is : %d\n", get_core_number());
    return 0;
}
