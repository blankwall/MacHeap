#include <pthread.h>
#include <mach/mach_init.h>
#include <mach/thread_act.h>
#include <mach/thread_policy.h>
#include <mach/error.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <fcntl.h>

int gd;

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


/* this function is run by the second thread */
void *busy(void *x_void_ptr) {
	printf("IN X\n");
	FILE* fp;\
	void *x;
	while(1){
		x = mmap(0, 4096, PROT_READ, MAP_PRIVATE, gd, 0);
		munmap(x, 4096);
	}
}

/* this function is run by the second thread */
void *core(void *x_void_ptr) {
	printf("IN Y\n");
	FILE* fp;
	while(1){
		printf("CORE: %d\n", get_core_number());
		for(int i =0; i < 10000000; ++i);
	}
}



int main()
{
	int x;
	gd = open("/dev/zero", O_RDONLY);
	pthread_t x_t, y_t;

	if(pthread_create(&x_t, NULL, busy, &x)) {

		fprintf(stderr, "Error creating thread\n");
		return 1;

	}

	if(pthread_create(&y_t, NULL, core, &x)) {
		fprintf(stderr, "Error creating thread\n");
		return 1;
	}

	while(1);
	return 0;

}
