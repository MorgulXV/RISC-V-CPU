CC      = gcc
CFLAGS  = -Wall -Wextra -std=c11 -g

.PHONY: all run test-immediates clean

all: emulator

emulator: emulator.c
	$(CC) $(CFLAGS) -o emulator emulator.c

test-immediates: test_immediates.c
	$(CC) $(CFLAGS) -o test_immediates test_immediates.c
	./test_immediates

clean:
	rm -f emulator test_immediates unit_test
