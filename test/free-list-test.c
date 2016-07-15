void clear_cache(){
	free(malloc(128));
}

int main(){
	int* x[10];

	for(int i =0; i < 10; ++i){
		x[i] = malloc(16);
		printf("%p\n", x[i]);
	}
	free(x[0]);
	free(x[2]);
	free(x[4]);
	free(x[6]);

	printf("Will allocate this block %p\n", x[6]);
	clear_cache();
	printf("%p\n", malloc(16));

}