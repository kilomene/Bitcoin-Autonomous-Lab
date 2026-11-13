CC = gcc
CFLAGS = -O3 -march=native -Wall -Wno-deprecated-declarations -pthread

bal-miner: src/bal_miner.c
	$(CC) $(CFLAGS) -o bal-miner src/bal_miner.c -lcrypto

test: bal-miner
	python3 tests/test_known_blocks.py
	./bal-miner search 0100000000000000000000000000000000000000000000000000000000000000000000003ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a29ab5f49ffff001d1dac2b7c 00000000ffff0000000000000000000000000000000000000000000000000000 2083236000 2000 4

bench: bal-miner
	./bal-miner bench 5 4

clean:
	rm -f bal-miner
