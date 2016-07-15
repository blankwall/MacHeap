#include <pthread.h>
#include <mach/mach_init.h>
#include <mach/thread_act.h>
#include <mach/thread_policy.h>
#include <mach/error.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <fcntl.h>

#define KNRM  "\x1B[0m"
#define KRED  "\x1B[31m"
#define KGRN  "\x1B[32m"
#define KYEL  "\x1B[33m"
#define KBLU  "\x1B[34m"
#define KMAG  "\x1B[35m"
#define KCYN  "\x1B[36m"
#define KWHT  "\x1B[37m"

#define QUANT 16

int main(){
	void* x[10];
	for(int i = 0; i < 10; ++i) x[i] = malloc(QUANT*i);
	for(int i = 0; i < 10; ++i) free(x[i]);
	asm("int3\n");
	x[0] = malloc(QUANT*9); //comes off of cache
	printf("Malloced off the cache @@: %p\n", x[0]);
	asm("int3\n");
	x[1] = malloc(QUANT*9); //comes off of free list
	printf("Malloced off the free list @@: %p\n", x[1]);

	asm("int3\n");
	printf("Clearing free list\n");

	for(int i = 0; i < 200; ++i) malloc(QUANT);
	printf("Allocating from region!");

	asm("int3\n");
x[0] = malloc(10*QUANT);

}