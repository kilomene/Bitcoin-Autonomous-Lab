# EXP-030 Phase A: Reference Repository Audit

Status: Phase A of the EXP-030 programme (owner directive
2026-11-15, sections 2, 2.1 to 2.4). Source-level audit of the
Bitaxe, Qaxe and NerdOCTAXE reference projects. Every finding
carries its evidence: repository, audited commit, file path,
and function or document section. Companion file:
REFERENCE_TO_NOVA_MATRIX.md (translation decisions).

## Repositories audited

| Repository | Role | Audited commit | Clone |
|---|---|---|---|
| skot/bitaxe | Bitaxe Ultra hardware (BM1366), pre-split repo | 942bbd97aab09b12d826c6e82c64f3fb91246c4c | full |
| bitaxeorg/ESP-Miner | Current Bitaxe firmware (all models) | e3cfbb3b124585cf5e45a4d4842422cccee69b72 | full (1,399 commits) |
| bitaxeorg/bitaxeGamma | Current single-chip hardware (BM1370) | f04c421e28d2c7b5b8db8a6ac4ae3801cae59384 | depth 50 |
| shufps/qaxe | NerdQAxe hardware (all generations) | be1a4a071def733a601a62b4fda3f3c5558c332e | full |
| shufps/ESP-Miner-NerdQAxePlus | Qaxe and NerdOCTAXE firmware | 3f738849c55029351d863a1f4b8fd407001e9ace | full (1,513 commits) |
| Patsch91/NerdOCTAXE-Gamma | NerdOCTAXE-Gamma hardware, branch Rev-3.4 | ebe52cf634310d6e64a8b1a0e10de10ffc593a30 | depth 1 (see limits) |

Clones live under .local/refs-exp030/ and are not part of the
pushed tree. The skot/bitaxe readme carries the migration
notice: the hardware repository split into model-specific
repositories under the bitaxeorg organisation. Current models:
bitaxeUltra (BM1366), bitaxeSupra (BM1368), bitaxeGamma
(BM1370), bitaxeMax (BM1397), BitaxeGT (2x BM1370), ultraHex
(multi-ASIC). The firmware moved to bitaxeorg/ESP-Miner and is
one codebase for all models, with one driver per ASIC
generation (components/asic/bm1397.c, bm1366.c, bm1368.c,
bm1370.c, bm1373.c).

## Audit limits and honesty notes

- NerdOCTAXE-Gamma: the full clone failed twice through the
  egress proxy (fetch-pack disconnect on the large pack). The
  audit used a depth-1 clone of the default branch (Rev-3.4).
  History beyond HEAD was not audited for this repo.
- KiCad schematics (.kicad_sch) are text S-expressions and were
  inspected directly (symbol libraries, placed components,
  value fields). PCB files (.kicad_pcb) were sampled as text
  (footprint and lib_id references), not rendered or routed-
  checked. Component values were verified only where a value
  field or BOM line was read; BOM CSVs in these repos are
  mostly DigiKey part-number lists grouped by reference
  designator, so per-part values are only partially verified.
- The ESP-Miner web UI (main/http_server/axe-os) was inventoried
  but not audited line by line; it carries no mining logic.
- Performance figures quoted from READMEs (TH/s, watts) are
  the projects' own claims, recorded as claims, not as
  measurements made by this lab.

---

## 1. Bitaxe (skot/bitaxe hardware, bitaxeorg/ESP-Miner firmware)

### 1.1 Architecture and work lifecycle

B1. Standalone single-controller architecture. All mining
logic (pool protocols, job construction, ASIC control,
verification, telemetry, web UI) runs on one ESP32-S3; no host
computer is involved. Evidence: skot/bitaxe readme.md
(Goals: Standalone, Embedded); ESP-Miner main/main.c,
main/system.c (SYSTEM_init_system), main/global_state.h
(GlobalState as the single shared state object).

B2. Task pipeline. FreeRTOS tasks split the lifecycle:
stratum client tasks receive work into a miner job pool,
create_jobs_task builds ASIC jobs, ASIC_result_task consumes
results, hashrate_monitor_task and power_management_task run
supervision loops. Evidence: ESP-Miner main/tasks/
(stratum_task.c, stratum_v1_client.c, stratum_v2_client.c,
create_jobs_task.c, asic_result_task.c), main/pool.h
(POOL_JOB_NOTIFY_FLAG, MINER_JOB_POOL_SIZE job pool slots,
task notifications carry pool index and slot).

B3. Staged job activation. When a notify has clean_jobs set,
work switches immediately; when it does not, the new job is
staged and the current ASIC cycle finishes first. Evidence:
ESP-Miner main/tasks/create_jobs_task.c (create_jobs_task,
current_work handling, "Staged job for next cycle").

### 1.2 Job construction and the ASIC job format

B4. The controller computes the first-block midstate in
software and sends midstates to the chip. A complete scalar
SHA-256 compression of the 64-byte first header block is
implemented for this. Evidence: ESP-Miner
components/asic/bm_job_midstate.c (midstate_sha256_bin).

B5. ASIC job derivation. mining_build_asic_job converts a
miner_job into an asic_job: for Stratum V1 it hashes the
coinbase (prefix, extranonce1, extranonce2, suffix) with
double SHA-256 and folds the merkle branches; for SV2
standard-channel jobs the pool-supplied merkle root is copied
directly. Evidence: ESP-Miner components/stratum/mining_job.c
(mining_build_asic_job), components/stratum/mining.c
(calculate_coinbase_tx_hash_bin, calculate_merkle_root_hash).

B6. Extranonce stepping. create_jobs_task increments
extranonce_2 once per ASIC job interval for rollable jobs, so
one pool job yields a stream of distinct ASIC jobs without
new pool traffic. Evidence: ESP-Miner
main/tasks/create_jobs_task.c (extranonce_2++ in the
miner_job_is_rollable branch).

B7. Version rolling, two mechanisms. Chips with hardware
rolling (BM1366 and later) get a version mask once per job
(ASIC_set_version_mask; the chip rolls bits above bit 13).
The BM1397, which cannot, is fed software-rolled versions:
increment_bitmask advances the version inside the BIP320 mask
once per midstate batch. Evidence: ESP-Miner
main/tasks/create_jobs_task.c, components/stratum/mining.c
(increment_bitmask).

### 1.3 Result processing and verification

B8. Immutable job reconstruction. Results return with a slot
index; the controller keeps a ring of full job copies and
looks the job up by slot before judging the nonce. Evidence:
ESP-Miner components/asic/asic_job_slot.c
(asic_job_store_insert, asic_job_store_lookup; lookup logs
"Invalid job nonce found" for stale slots).

B9. Exact integer verification on the controller. The result
task rebuilds the exact 80-byte header from the stored job,
the nonce and the rolled version, recomputes SHA-256d, and
compares with uint256_lte against the pool target and,
separately, against the exact network target decoded from
nBits. Share and block are distinguished exactly; floating
point difficulty is used only for display and the scoreboard.
Evidence: ESP-Miner components/mining_job/asic_job.c
(asic_job_header), components/stratum/mining.c
(mining_nonce_hash), main/tasks/asic_result_task.c
(ASIC_result_task, steps 1 to 3: bit-exact checks, immediate
submit, deferred telemetry).

B10. On-chip result filtering (ticket mask). The chip is
programmed with a power-of-two difficulty mask (register
0x14, TICKET_MASK) so it only reports nonces clearing a
leading-zero-bits threshold; a controller adapts the mask to
the expected hashrate and a target share interval, applying
increases only after a 30 second grace period and decreases
immediately. Evidence: ESP-Miner
components/asic/asic_common.c (register 0x14 comment),
components/asic/asic.c (ASIC_set_difficulty, line 243),
main/difficulty_controller.c (difficulty_controller_update,
calculate_effective_asic_difficulty, grace period).

B11. Duplicate suppression at the protocol layer. Both
stratum clients track active job ids and ignore duplicate
notify messages for a job already held. No nonce-level
duplicate detection exists on this path; the pool is the
arbiter. Evidence: ESP-Miner main/tasks/stratum_v1_client.c
(add_active_job_id, "Ignoring duplicate notify"),
main/tasks/stratum_v2_client.c ("Ignoring duplicate V2 job").

B12. Persistent best-difficulty scoreboard. The best nonces
are kept in NVS with full reconstruction context (difficulty,
job id, extranonce2, ntime, nonce, rolled version bits), so
any historical best can be re-derived and re-verified.
Evidence: ESP-Miner main/tasks/scoreboard.c
(scoreboard_init, scoreboard_add call in asic_result_task.c).

### 1.4 Hashrate, error and health measurement

B13. Hashrate is measured from on-chip hash counters, not
estimated from shares. The monitor reads per-chip (and per
hash-domain) counter registers (unit 2^20 hashes), maintains
1 minute, 10 minute and 1 hour windows, and tracks a separate
error measurement from chip error counters. Evidence:
ESP-Miner main/tasks/hashrate_monitor_task.c
(HASHRATE_UNIT 0x100000, update_hash_counter,
hashrate_monitor_register_read), components/asic/bm_hashrate.c.

B14. Supervision loops. A task monitor samples FreeRTOS
runtime statistics every 60 seconds (per-task CPU share,
task-count changes). A self-test module can take over result
processing at startup and records nonces instead of
submitting them. Evidence: ESP-Miner main/task_monitor.c,
main/self_test/, asic_result_task.c (self_test_record_nonce
branch).

### 1.5 Power, frequency, thermal

B15. Core voltage is digitally adjustable. Ultra hardware:
TPS40305 buck converter with a Maxim DS4432U+ current DAC
setting the BM1366 core voltage; INA260 meters input voltage
and current; Gamma hardware replaces this with a TPS546D24A
integrated buck. Evidence: skot/bitaxe readme.md (Features),
skot/bitaxe power.kicad_sch (TPS40305, DS4432, INA260
symbols), bitaxeGamma power.kicad_sch (TPS546D24A value
field), ESP-Miner main/power/ (DS4432U.c, INA260.c, TPS546.c,
vcore.c).

B16. Thermal management and overheat safe mode. Fan control
via EMC2101/EMC2103/EMC2302 PWM controllers with tachometer
feedback and a PID loop (main/thermal/PID.c). The power
management task watches VR and chip temperatures; on overheat
it halts operation, runs enforced cooling cycles, and only
resumes below a hysteresis threshold. Evidence: ESP-Miner
main/tasks/fan_controller_task.c,
main/tasks/power_management_task.c (TPS546_THROTTLE_TEMP,
"Entering safe mode due to overheat condition",
MIN_COOLING_CYCLES), skot/bitaxe fan.kicad_sch, readme
(EMC2101 placed close to the ASIC because the BM1366 has no
die temperature readout).

B17. Frequency changes are ramped, never jumped. PLL divider
search finds the closest legal setting; transitions step the
clock gradually. Evidence: ESP-Miner
components/asic/frequency_transition_bmXX.c, pll.c.

### 1.6 Protocols

B18. Stratum V1 and V2 both ship. V2 support includes the
Noise handshake and both channel types; standard-channel jobs
arrive with the merkle root already computed by the pool or
proxy. Evidence: ESP-Miner components/stratum_v2/
(sv2_protocol.c, sv2_noise.c), main/tasks/stratum_v2_client.c,
components/stratum/mining_job.c (JOB_TYPE_SV2_STANDARD).

### 1.7 What does not translate, and why

- The serial ASIC protocol itself (55 AA frames, CRC5/CRC16,
  chip addressing): it exists to move work to external hash
  chips. A CPU engine has no such link; only the framing
  discipline (length, CRC, response typing) is instructive.
- On-chip nonce-space partitioning and the BM1370 hash
  counting number errata compensation (bm1370.c
  BM1370_set_nonce_space): compensations for undocumented
  silicon behaviour. CPU nonce partitioning is exact by
  construction and needs no errata margin.
- DAC-set core voltage and PLL ramping: CPU frequency and
  voltage are owned by the OS and hypervisor, not by the
  miner. The transferable part is the policy (ramp, hysteresis,
  safe mode), not the mechanism.
- The OLED display, BLE setup and captive-portal WiFi
  provisioning: product features of a standalone appliance,
  irrelevant to a VM-resident agent.

---

## 2. Qaxe hardware (shufps/qaxe)

Q1. NerdQAxe++ (current flagship, rev5.1.2). Four BM1370
ASICs in a serial chain on one board, TPS53647 multiphase
buck controller for the shared core rail, claimed about
4.8 TH/s at about 76 W. Evidence: qaxe README.md
(NerdQAxe++ section), qaxe nerdqaxe++/nerdqaxe++/
power.kicad_sch (TPS53647 symbols), nerdqaxe++.kicad_sch.

Q2. NerdQAxe+ (rev5.0). Same platform with four BM1368,
claimed about 2.5 TH/s at about 55 W; the power sheet also
uses the TPS53647. Evidence: qaxe README.md,
nerdqaxe+/nerdqaxe+/power.kicad_sch.

Q3. Legacy QAxe and QAxe+ (end of life). Four BM1366 (QAxe)
or BM1368 (QAxe+), supervised by an STM32L072CB
microcontroller running Rust (Embassy) firmware: power-good
monitoring, reset sequencing, fan PWM, two I2C temperature
sensors, and a USB JSON-RPC interface to the host. Evidence:
qaxe legacy/README.md, qaxe firmware/fw-L072CB/src/bin/
qaxe.rs (power_good_task, reset_manager, pwm_manager,
temp_manager, json_rpc).

Q4. Sensing. Two TMP1075 digital temperature sensors appear
in the NerdQAxe++ BOM; a common 25 MHz oscillator clocks the
chain (replacement part listed in the README). Evidence:
qaxe nerdqaxe++/bom/digikey.csv (TMP1075NDRLRCT x2), qaxe
README.md (Compatible Replacement Parts).

Q5. Revision discipline. Board revisions are tagged releases
(rev5.1, rev5.1.2); the README marks rev5.1.2 as containing
improvements but "untested yet". Evidence: qaxe README.md,
git history (merge of rev5.1.2, "disabled FCCM").

Q6. Failure domain. One shared core rail and one serial ASIC
chain per board: a single chip or power fault disables the
whole board. No per-chip power switching or chain bypass was
found in the schematics inspected. Evidence: qaxe
nerdqaxe++/nerdqaxe++/power.kicad_sch and
nerdqaxe++.kicad_sch (single TPS53647 rail), legacy/README.md
("Known quirks with ASIC reset behavior" on QAxe+).

### What does not translate, and why

- The multiphase buck design itself, the 25 MHz chain clock
  distribution, and the serial daisy chain: these move power
  and work into silicon. The general principles that do
  translate are recorded in the matrix (shared-resource
  budgeting, per-worker sensing, explicit failure domains,
  supervisor/watchdog separation in Q3).
- Board-level performance claims (J/TH) describe ASIC
  silicon, not anything a CPU can approach; they set no
  expectation for NOVA.

---

## 3. Qaxe firmware (shufps/ESP-Miner-NerdQAxePlus)

This fork of ESP-Miner is the firmware for NerdQAxe,
NerdQAxe+, NerdQAxe++, NerdOCTAXE and several other boards:
13 board definitions under main/boards/ (nerdqaxeplus.cpp,
nerdqaxeplus2.cpp, nerdoctaxegamma.cpp, nerdoctaxeplus.cpp,
nerdaxegamma.cpp, q1370.cpp, q1373.cpp, and others) behind a
common Board abstraction. All directive-named files exist at
the named paths and were read: main/tasks/
create_jobs_task.cpp, asic_result_task.cpp, can_sender.cpp,
can_master_task.cpp, can_slave_task.cpp, mining_info_v2.cpp,
main/stratum/stratum_task.cpp, stratum_task_v2.cpp,
components/bm1397/mining.cpp, components/bm1397/asic.cpp.
The bm1397 component name is historical; the same component
carries the BM1366/BM1368/BM1370 job and protocol code used
by current boards.

### 3.1 The 17 directive areas

1. Job lifecycle and ownership. Jobs are built by
create_jobs_task into heap bm_job objects and stored in the
AsicJobs registry; the result path clones the job before use
and frees the clone. On a clean notify, cleanJobs(pool)
frees all stored jobs of that pool. Evidence:
main/tasks/asic_jobs.h (AsicJobs::storeJob, getClone,
cleanJobs, cloneBmJob), main/tasks/create_jobs_task.cpp
(create_job_mining_notify with abandonWork).

2. Immutable job reconstruction. The registry stores the
complete bm_job (header fields, merkle root in two byte
orders, extranonce2 string, pool id, pool difficulty, nBits
target), so a result can be re-derived without the pool.
The clone-on-read rule means the stored job is never mutated
by the result path. Evidence: main/tasks/asic_jobs.h,
components/bm1397/include/mining.h (bm_job definition),
components/bm1397/mining.cpp (construct_bm_job).

3. Extranonce generation. V1: one global uint32 extranonce_2
counter, incremented per job sent, formatted as fixed-width
hex into the coinbase. CAN slaves get a partitioned space:
extranonce_2 = (slave_id << 25) | (counter & 0x1FFFFFF), so
up to 128 slaves hold disjoint coinbase spaces by
construction. Evidence: main/tasks/create_jobs_task.cpp
(extranonce_2++), main/tasks/can_sender.h
(can_make_extranonce2).

4. Merkle-root construction. V1 builds the coinbase as hex
text (coinbase_1 + extranonce1 + extranonce2 + coinbase_2),
double-hashes it, and folds the branch list. Evidence:
components/bm1397/mining.cpp (calculate_merkle_root_hash),
main/tasks/create_jobs_task.cpp (MiningInfoV1::buildBmJob).

5. Version rolling. The chip rolls version bits on hardware;
the returned rolled version is a 16-bit field shifted left
13, and the result path ORs it with the job version. SV2
requires the pool to allow version rolling because the chips
roll bits 13 to 28 on every job. Evidence:
components/bm1397/asic.cpp (Asic::processWork),
main/tasks/asic_result_task.cpp (rolled_version |=
job->version), main/stratum/stratum_task_v2.cpp (comment at
SetupConnection).

6. Timestamp handling. ntime comes from the notify and is
stored per job; new-work detection keys on ntime change
only (MiningInfoV1::isNewWork). Jobs are rebuilt on the job
interval timer regardless. Evidence:
main/tasks/create_jobs_task.cpp (isNewWork, job_timer).

7. Nonce-result processing. Asic::processWork parses the
11-byte response, separates register responses from nonce
results by a flag bit in the CRC byte, derives the
originating chip from address bits inside the nonce, and
hands a task_result to ASIC_result_task. Evidence:
components/bm1397/asic.cpp (receiveWork, processWork,
nonceToAsic).

8. Job identifiers. Two levels: the pool job id string
(Stratum) and the ASIC job id byte. sendWork is passed the
extranonce_2 counter and converts it with jobToAsicId; the
registry is indexed by that byte (128 slots). Evidence:
components/bm1397/asic.cpp (Asic::sendWork),
main/tasks/asic_jobs.h (MAX_ASIC_JOBS 128).

9. Duplicate result detection. A ring of the last 32
(nonce, rolled_version) keys (SimpleRing64<32>);
insert_if_absent decides duplication and a counter
(duplicateHWNonces) is exported. Duplicates are excluded
from share statistics but are still submitted to the pool
on purpose, to be rejected and counted there. Evidence:
main/tasks/asic_result_task.cpp (s_seen_keys, make_key,
"send duplicates to the server" comment).

10. Best-difficulty accounting. Every result's difficulty is
compared against session best and the persisted all-time
best; found-block events increment counters persisted to
config and can fire a Discord alert. Evidence:
main/stratum/stratum_manager.cpp (checkForBestDiff,
checkForFoundBlock), main/tasks/asic_result_task.cpp
(getBestSessionDiff), HEAD commit 3f738849 (all-time best
difficulty exported to InfluxDB).

11. Candidate submission. Results meeting the pool
difficulty are submitted immediately by the result task
through the StratumManager, which owns per-pool tasks for
two pools (dual-pool share splitting or fallback modes).
Evidence: main/tasks/asic_result_task.cpp (submitShare
call), main/stratum/stratum_manager_dual_pool.h,
stratum_manager_fallback.h, stratum_manager.cpp.

12. Stratum V1 and V2. V1: subscribe, authorize,
extranonce.subscribe, mining.submit with the version delta
only. V2: Noise-encrypted transport with optional authority
public-key pinning, extended channel by default, standard
channel supported (pool supplies merkle root; extranonce2
unused). Evidence: main/stratum/stratum_task.cpp
(StratumTaskV1::submitShare, reconnect logic),
main/stratum/stratum_task_v2.cpp (sv2_noise, channel
selection), main/tasks/mining_info_v2.cpp
(MiningInfoV2Standard::buildBmJob).

13. Master/slave coordination. One board can be CAN master
for up to 32 slave boards. Slaves announce by MAC (HELLO),
the master assigns ids (ASSIGN) and persists the registry
in NVS, detects foreign-fleet slaves by master MAC, sends
each slave its own raw job with a slave-specific
extranonce2, receives slave nonces, validates them against
its own job registry and submits centrally. Fleet power is
summed; fleet thermal shutdown and board errors are
aggregated; frequency, voltage and fan settings can be
pushed to slaves. Evidence: main/tasks/can_master_task.cpp
and can_master_task.h, main/tasks/can_sender.cpp
(can_send_hello, can_send_assign, can_send_raw_job),
main/tasks/create_jobs_task.cpp (per-slave job fan-out).

14. CAN frame fragmentation and reassembly. Classic CAN
8-byte frames carry 1 sequence byte plus 7 payload bytes.
Sequence 0 starts a new frame (any partial frame is
discarded with a warning), a CAN_SEQ_LAST marker ends it,
overflow discards. A TX mutex makes multiframe sends
atomic. The sender implements BUS_OFF recovery and transmit
queue clearing. There is no payload checksum or total
length field; integrity rests on the CAN per-frame CRC and
sequence discipline. Evidence: main/tasks/can_sender.cpp
(send_multiframe, can_transmit_with_recovery),
main/tasks/can_master_task.cpp (reassembly, lines around
470 to 500), main/tasks/can_slave_task.cpp (job
reassembly).

15. Device heartbeat and timeout. Slaves stream telemetry
frames to the master; 10 seconds without telemetry marks a
slave offline. A slave that receives no job for 10 seconds
drops its assignment and re-negotiates from HELLO.
Evidence: main/tasks/can_master_task.cpp
(CAN_SLAVE_TIMEOUT_MS 10000, check_slave_timeouts),
main/tasks/can_slave_task.cpp ("No job for 10s,
re-negotiating").

16. Worker failure and reconnection. Pool side: a 30 second
reconnect timer with a 10 second pre-reconnect delay;
transport shutdown gates new submits first. ASIC side:
boards expose a shutdown state; on shutdown the mining
tasks suspend themselves and the core voltage is cut (see
18 below). CAN side: BUS_OFF recovery and driver restart
(area 14). Evidence: main/stratum/stratum_task.cpp
(reconnectTimer, 30000 ms, vTaskDelay 10000),
main/tasks/can_sender.cpp, main/tasks/power_management_
task.cpp (isShutdown checks in task loops).

17. Hardware performance monitoring. Per-chip hashrate from
the total-nonce counter register 0x90, hardware error rate
from register 0x4C, die temperature from register 0xB4,
polled on a 5 second monitor interval; telemetry is also
exported to InfluxDB and a web API. Evidence:
main/tasks/hashrate_monitor_task.cpp (REG_NONCE_TOTAL_CNT
0x90, REG_HW_ERROR_CNT 0x4C, HR_INTERVAL 5000),
main/tasks/asic_result_task.cpp (register response switch),
main/tasks/influx_task.cpp.

18. (Beyond the 17) Power and thermal enforcement. PID fan
control over chip and VR temperatures; on overheat the
board error is recorded and the core voltage is set to
0.0 V, which stops the ASICs; tasks observe the shutdown
flag and suspend. Evidence: main/tasks/
power_management_task.cpp (fanController.isOverheated,
setVoltage(0.0), Board::Error), main/boards/board.h.

### 3.2 Weaknesses and defects found (do not inherit)

W1. Floating-point difficulty is the authoritative test.
test_nonce_value returns a double difficulty (cgminer
truediffone method) and submission is decided by
nonce_diff >= pool_diff; block detection compares doubles
against a double network difficulty. Near a boundary this
can misjudge candidates in either direction, and a "found
block" is declared on a float comparison. The pool remains
the final arbiter for shares, but for solo block candidacy
this pattern is exactly what EXP-036 forbids. Evidence:
components/bm1397/mining.cpp (test_nonce_value,
le256todouble), main/tasks/asic_result_task.cpp,
main/stratum/stratum_manager.cpp (checkForFoundBlock).

W2. The duplicate ring is small and job-blind. 32 entries
keyed only by (nonce, version): the same nonce and version
under a different job (different merkle root) is flagged a
duplicate, and a genuine duplicate older than 32 results is
missed. Deliberately submitting duplicates to the pool
wastes pool goodwill and pollutes rejection statistics.
Evidence: main/tasks/asic_result_task.cpp.

W3. Registry slot recycling can misattribute late results.
storeJob silently frees the job previously in a slot. A
chip result that arrives after its slot was recycled is
then verified against the new job (it will normally fail
the difficulty test and be dropped, but the accounting and
logging attach to the wrong job). The same structural risk
exists in the Bitaxe slot ring (B8). Evidence:
main/tasks/asic_jobs.h (storeJob).

W4. New-work detection keys on ntime only. A notify with a
new prevhash inside the same second is not flagged as new
work. Impact here is limited (jobs rebuild every interval
anyway) but the pattern is unsafe to copy. Evidence:
main/tasks/create_jobs_task.cpp (isNewWork).

W5. Byte-order fragility. bm_job carries both normal and
_be (ASIC byte order) copies of merkle root and prevhash,
produced by different transform chains for V1 and V2; the
SV2 builder needs a 30-line comment to argue the transforms
agree. This dual-representation design is a standing source
of endianness bugs. Evidence: main/tasks/
mining_info_v2.cpp (buildBmJob comment block),
components/bm1397/mining.cpp (construct_bm_job).

W6. Thin in-repo test coverage. The test/ tree holds two
static python checks and a test-app skeleton; the mining
logic (job construction, result verification, CAN
reassembly) has no unit tests in the repo, unlike the
Bitaxe ESP-Miner components which carry test directories.
Evidence: ESP-Miner-NerdQAxePlus/test/ listing vs
bitaxeorg/ESP-Miner components/*/test.

W7. CAN multiframe has no end-to-end integrity check (see
area 14): a lost middle frame is caught only indirectly by
sequence expectations, and there is no payload length to
validate the reassembled job against.

### 3.3 What does not translate, and why

- The CAN bus itself: a wiring solution for boards in one
  enclosure. The coordination semantics translate (registry,
  leases, timeouts, central validation); the transport does
  not.
- Deriving the worker identity from bits inside the nonce
  (nonceToAsic): a silicon addressing artifact. CPU workers
  identify themselves explicitly.
- Register-poll telemetry (0x90, 0x4C, 0xB4): the principle
  (counters owned by the worker, polled by a monitor)
  translates; the registers do not.

---

## 4. NerdOCTAXE-Gamma (Patsch91/NerdOCTAXE-Gamma)

O1. Eight-ASIC architecture. One board carries eight
BM1370 ASICs (variants BM1370BC, BM1370PA, BM1370PF tested
by the author), driven by one ESP32 controller (Lilygo
T-Display S3). Evidence: README.md (ASICS section, Build),
Nerd8.kicad_pcb (BM1370 footprints), Nerd8.kicad_sch with
per-chip sheets (BM1368.kicad_sch, BM1368-1 to 3,
bm1370.kicad_sch, Asic0.kicad_sch; sheet names retain
earlier-generation names).

O2. Six-phase power delivery. Rev3.4 uses a six-phase buck
converter: TPS53647 multiphase controller with CSD95472Q5MC
power stages, sized for eight chips on one rail. A
TPS53667 symbol also appears in the power sheet library
(alternative controller footprint; the placed controller is
the TPS53647). Evidence: README.md (Rev3.4 notes, "6 Phase
Buck Converter"), power.kicad_sch (TPS53647 placed symbol,
CSD95472Q5MC stages).

O3. Per-chip temperature sensing. Rev3.4 explicitly "added
circuit to read the internal temperature of each asic"; the
pi.kicad_sch sheet carries TMP1075 sensors. Evidence:
README.md (Rev3.4), pi.kicad_sch (TMP1075).

O4. Cooling architecture. Eight chips are cooled by two
LGA115x-class CPU tower heatsinks (Thermalright AXP90-X53),
repurposing desktop CPU coolers as ASIC cooling. Evidence:
README.md (HEATSINKS).

O5. Firmware integration. The board runs the NerdQAxePlus
ESP-Miner fork (releases published for NerdOCTAXE-Gamma);
board support exists in that repo as
main/boards/nerdoctaxegamma.cpp. This repo is hardware
only: KiCad project, BOM CSVs, iBOM HTML, 3D models; no
firmware source and no gerber folder (manufacturing files
are exported with the JLC KiCad plugin per the README).
Evidence: README.md, repo file inventory,
ESP-Miner-NerdQAxePlus main/boards/nerdoctaxegamma.cpp.

O6. Scaling shape, four to eight. Doubling the QAxe's four
chips to eight on one board scales the power and thermal
systems (six phases, two tower coolers, per-chip sensing)
while keeping one controller, one rail and one failure
domain: a rail or controller fault stops all eight chips.
Evidence: README.md, power.kicad_sch, Q6 comparison.

### What does not translate, and why

- The six-phase converter, DrMOS stages and tower heatsinks
  are electrical and thermal engineering for silicon loads.
  Their CPU analogues are capacity budgeting, per-worker
  telemetry and sustained-performance throttling policy,
  recorded in the matrix; the circuits themselves have no
  software counterpart.
- One-controller-per-eight-workers is the opposite of the
  NOVA direction (autonomous agents with local state); only
  its supervision economy is instructive.

---

## 5. Cross-cutting observations

X1. Both firmwares independently converged on the same
skeleton: pool tasks, a job-construction task, a job
registry keyed by a small integer slot, a result task that
re-derives the header, counter-based hashrate telemetry,
and a power/thermal supervisor that can halt work. That
convergence is the strongest signal in this audit for the
NOVA architecture (directive section 12).

X2. The two firmwares diverge exactly where it matters most
for NOVA: Bitaxe ESP-Miner verifies results with exact
integer target comparison (B9); the Qaxe fork judges with
floating-point difficulty (W1). NOVA already follows the
exact pattern and must keep it.

X3. Both codebases treat the stored job as the unit of
trust: results are meaningless without the immutable job
they belong to. Both also accept the slot-recycling risk
(W3) as the price of a small fixed registry.

X4. Neither firmware counts unique search coverage. Their
accounting is shares, best difficulty and counter deltas.
The EXP-037 separation (unique headers, repeated work,
verification hashes, candidates) has no reference
implementation here and must be built NOVA-side.

X5. Search-space expansion in the references is exactly:
extranonce stepping (B6, area 3), on-chip version rolling
(B7, area 5), on-chip nonce partitioning (B13 area, bm1370
HCN), and per-worker extranonce partitioning (area 3, CAN).
No reference rolls timestamps or mutates the coinbase
beyond extranonce; ntime is pool-supplied in both.

## Finding counts

- Bitaxe line (hardware plus ESP-Miner firmware): 18
  findings (B1 to B18; B15 to B17 grouped under power and
  thermal).
- Qaxe hardware: 6 findings (Q1 to Q6).
- Qaxe firmware: 18 areas plus 7 weaknesses (W1 to W7).
- NerdOCTAXE-Gamma: 6 findings (O1 to O6).
- Cross-cutting: 5 observations (X1 to X5).
