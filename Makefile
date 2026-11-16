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

test-solo-vardiff:
	python3 tests/test_solo_vardiff.py

test-solo-cutover:
	python3 tests/test_solo_cutover.py

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

test-task0038:
	python3 tests/test_task0038_abi.py

test-task0039:
	python3 tests/test_task0039_accounting.py

test-avx512:
	python3 tests/test_avx512_integration.py

test-avx512dual:
	python3 tests/test_avx512_dual_integration.py

test-mainnet-live:
	python3 tests/test_mainnet_live_accounting.py

test-template-cache:
	python3 tests/test_template_cache.py

test-avx512flags:
	python3 tests/test_avx512_flags_integration.py

test-exp039:
	python3 tests/test_exp039_fallback_integration.py

test-exp040:
	python3 tests/test_exp040_category_f.py

test-exp049:
	python3 tests/test_exp049_bench_mode.py

test-exp036:
	python3 tests/test_exp036_verification.py

test-exp034:
	python3 tests/test_exp034_job_template.py

test-exp037:
	python3 tests/test_exp037_statistics.py

test-exp038:
	python3 tests/test_exp038_checkpoint.py

test-probability:
	python3 tests/test_probability_percentiles.py

test-agent-intelligence:
	python3 tests/test_agent_intelligence.py

test-agent-awareness:
	python3 tests/test_agent_awareness.py

test-agent-operations:
	python3 tests/test_agent_operations.py

test-agent-security:
	python3 tests/test_agent_security.py

test-agent-controller:
	python3 tests/test_agent_controller_modes.py

test-stage8:
	python3 tests/test_stage8_demonstration.py

test-all: test test-regtest test-engine test-pow test-gpu test-gpu-correction test-mining test-adversarial test-deepening test-cpu test-cpu-correction test-rtl test-solo test-solo-vardiff test-solo-cutover test-research test-autopilot test-judgement test-installer test-task003 test-task0038 test-task0039 test-avx512 test-avx512dual test-mainnet-live test-template-cache test-avx512flags test-exp036 test-exp034 test-exp037 test-exp038 test-probability test-exp039 test-exp040 test-agent-intelligence test-agent-awareness test-agent-operations test-agent-security test-agent-controller test-stage8 test-exp049

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
