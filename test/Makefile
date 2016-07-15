CFLAGS=-O0
LDFLAGS=-static

%.o: %.c
	@echo "[+] Compiling $< to $@"
	$(CC) -c $(CFLAGS) $< -o $@

%: %.o
	@echo "[+] Linking $^ into $@"
	$(CC) $(LDFLAGS) $^ -o $@

default: all
include Makefile.dep Makefile.obj
include Makefile.all
