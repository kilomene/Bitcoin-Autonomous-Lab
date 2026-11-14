CC = gcc
CFLAGS = -O3 -march=native -Wall -Wno-deprecated-declarations -pthread

bal-miner: mining/cpu/bal_miner.c
	$(CC) $(CFLAGS) -o bal-miner mining/cpu/bal_miner.c -lcrypto

test: bal-miner
	python3 tests/test_known_blocks.py
	./bal-miner search 0100000000000000000000000000000000000000000000000000000000000000000000003ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a29ab5f49ffff001d1dac2b7c 00000000ffff0000000000000000000000000000000000000000000000000000 2083236000 2000 4

test-regtest:
	python3 tests/test_regtest_integration.py

test-engine:
	python3 tests/test_intelligence_engine.py

test-pow:
	python3 tests/test_pow_engine.py

test-gpu:
	python3 tests/test_gpu_compute.py

test-gpu-correction:
	python3 tests/test_gpu_correction.py

test-mining:
	python3 tests/test_mining_engine.py

test-adversarial:
	python3 tests/test_adversarial.py

test-deepening:
	python3 tests/test_deepening.py

test-cpu:
	python3 tests/test_cpu_aspect.py

test-cpu-correction:
	python3 tests/test_cpu_correction.py

test-rtl:
	python3 tests/test_rtl_aspects.py

test-solo:
	python3 tests/test_solo_server.py

test-research:
	python3 tests/test_research.py

test-autopilot:
	python3 tests/test_autopilot.py

test-judgement:
	python3 tests/test_judgement.py

test-installer:
	python3 tests/test_installer.py

test-task003:
	python3 tests/test_task003_corrections.py

test-all: test test-regtest test-engine test-pow test-gpu test-gpu-correction test-mining test-adversarial test-deepening test-cpu test-cpu-correction test-rtl test-solo test-research test-autopilot test-judgement test-installer test-task003

cuda-build:
	python3 gpu/cuda/build.py

cuda-diag:
	python3 -m gpu.diagnostics

bench: bal-miner
	./bal-miner bench 5 4

node-status:
	python3 -m node.node_manager status

clean:
	rm -f bal-miner
