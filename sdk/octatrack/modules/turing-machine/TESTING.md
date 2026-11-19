# Turing Machine 0.5.0-experimental — private software qualification

**Hardware untested / #1697 draft.** No physical USB write, flash, MIDI send, listening or reboot was performed. These observations apply to the module-only package on the unchanged Modwerk base **0.7.9**, built privately from stock OS **1.40C**. Base 0.7.7 and later base versions were not qualified. The previous turing-arpgen implementation is a read-only reference, not hardware evidence for this port.

Michael approved retiring FUNC+LOCK and releasing FUNC after FUNC+AMP before editing SCALE/ROOT on 18 November 2026 (`ANSWERS24.md`, private Brief 24 diagnostics). All other note, engine, storage and WRITE assertions retain their reference expectations. Saved SCALE IDs remain OFF/MAJ/MIN, mapped to shared SDK IDs 0/1/6; the negative down-snap at note zero is dropped.

## Exact private package

The tested local artifact is `../diag/out/brief24/turing24.mwrm`, outside this worktree. It contains **43,708 initialized bytes + 4,536 BSS = 48,244 bytes (47.1 KiB)**, 163 relocations, three table/event hooks and nine stock-code sites. It is below the 128 KiB initialized-image and 288 KiB total per-module caps; this is not a measurement of loader overhead or whole-set headroom.

Every package-harness boot links current `turing.s` and the shared scale SDK and asserts equality of the executable image, BSS and relocation count before installation. The build-only reproduction `turing24-reproduction.mwrm` differs solely in the 16-byte display title (`TURING` versus `Turing Machine`); all remaining bytes match. Acceptance uses the original artifact throughout. No binary, card, dump or image digest is committed or uploaded.

## Observed results

Evidence is local under `../diag/out/brief24/`; `../diag/CODEX_REPORT24.md` holds the full gate ledger. An interrupted log counts only for its completed assertions.

| Check | Observation | Local evidence |
| --- | --- | --- |
| Fixed-seed C engine versus turing-arpgen | PASS: 3,870,720 state transitions and three note ranges each | `port-native.log` |
| Executed ColdFire shared scale wrapper | PASS: 4,680 OFF/MAJ/MIN and range-edge cases | `port-native.log` |
| Actual candidate/reference UART output | PASS: 32 notes/velocities per key, OFF and four MAJ/MIN keys; 25 assertions | `reference.log` |
| Stock host UI / S2 controls | PASS: 14 assertions, main controls, second-page SCALE/ROOT after releasing FUNC, per-Part settings and stock SRC | `wake-smoke.log` (corrected harness, exit 0); earlier `smoke2.log` |
| DRAM reset/import and former battery isolation | PASS: storage and migration assertions, including private-emulator sentinel preservation | `persist.log`, `storage-source-audit.log` |
| Stock 1.40C MIDI contract | PASS: MODE-OFF message identity, clock/transport, tick counts and one generated note per step; four contract assertions plus two fixtures, exit 0 | `wake-stock.log` (corrected harness, exit 0); earlier `resume-stock.log` |
| Pattern/Part state and timer seeding | PASS: 12 assertions, distinct phrases at different PLAY times, exit 0 | `resume-shape-tail.log` |
| Live LEN and fresh registers | PASS: eight assertions, live changes and four tracks × four patterns match the model, exit 0 | `resume-shape-live.log` |
| WRITE PUSHA / flags / repeated toggles | PASS: message equality, four-sample timing tolerance and live transition; historical trig structure byte-identical; all seven resumed flags/toggle checks pass, exit 0 | `write.log`, `resume-write.log` |
| SCAL / density | PASS: 14 assertions, including model/range/quantizer, rests/NEI/CC and live rhythm restoration, exit 0 | `resume-shape-scale.log` |
| LOCK / LEN periods | PASS: eight assertions, curve/clamps and exact note and notes/rests periods, exit 0 | `resume-lock.log` |
| Grid/locks/NEI/range/LFO/clock/models | PASS: 42 completed replacement checks, 16 resumed locks/NEI/range/LFO checks and 15 clock/model checks; clock run exit 0. Sequential engine run intentionally partitioned after LFO closed, before clock; zero failed assertions | `engine.log`, `resume-engine.log`, `partition-engine.log`, `resume-clock.log` |
| SAVE/RELOAD and saved-card fresh boot | PASS: seven unchanged strict assertions, exit 0; exact saved pass-start register/MODE/Part settings, identical phrase after RELOAD and fresh boot, and track keys after WRITE/SAVE/RELOAD/boot | `run12-reload.log`, `run12-reload.exit` |
| Cached legacy-file import | PASS: two unchanged strict assertions, exit 0; OCTABAM8/9 comments, shared Part controls and independent pattern MODE | `wake-oldlines.log`, `wake-oldlines.exit` |
| Browser package admission | PASS: validator accepts the package, prepares exact Undo and rejects corruption; no transport used | `package-admission.log` |
| Runtime backend lifecycle | PASS: 18 assertions, installation/replacement/Undo/removal and retained Part state | `beta.log` |
| Declared cross-compatibility | PASS: 43 modules, 903 pairs, 104 hooks; no concurrent-module audio claim | `compat.log` |
| Focused SDK and late-project import | PASS: ten focused tests and one import test | `sdk-focused.log`, `import-native.log` |
| Full SDK suite | PASS: 721 tests / 127 jobs with Python 3.15 | `sdk-check-current-python.log` |
| ColdFire ISA / hooks / stock inbound references | PASS: 91 ISA sources, 12 pre-existing unsupported-source skips; six hook tests; all nine Turing sites have zero interior inbound references | `coldfire-isa.log`, `hook-coverage.log`, `inbound.log` |
| module:doctor / pr:ready | NOT GREEN: publication/catalogue/package/board records and CPU/UI/hardware evidence missing; nothing waived | `doctor.log`, `pr-ready.log` |

## Stock FX

**Paired Turing preservation: byte-identical. Original-stock comparison: normalized identity plus bounded compressor-bridge behavioural equivalence, not whole-FX byte identity.** All 26 complete arrays match before/after Turing installation on the same base 0.7.9 boot after the real modules-ready notification (`fx-before-after-wake.log`, exit 0). No FX word is excluded. Against original stock 1.40C, the base's existing COMPRESSOR bridges differ in four words per core, so the literal all-13 original-stock byte-identity gate is not met; it has not been waived. The exact browser base was booted and Turing installed through its real runtime backend before reading all 26 unpacked stock arrays and both DSP resident P blocks. Recovery fingerprint-checks the original 1.40C MAIN, both payloads, all original spans and all normalized recipes.

Twelve complete effect arrays per core, including SPRING REV, and every shared DSP helper match their normalized stock reference. The original source spans are recovered exactly by reversing the named address adjustments. Absolute original FX addresses are not a valid comparison: this existing base relocates the effects and reconstructs core B from shared literals plus sparse differences.

COMPRESSOR matches in 176/180 words per core. The remaining four are the base's existing guarded init/proc long JSR bridges, not padding and not a Turing edit. The exact captured dormant paths disassemble to branch/move/RTS sequences replaying stock's prefixes. Under the vendored DSP interpreter, all four core/entry cases match the displaced original prefix over 4,096 seeded states each (16,384 comparisons): ALU, address/modulo/offset registers, status, return/stack balance and X/Y memory. The unchanged remainder resumes with the same state. Turing carries no DSP contribution and cannot enable Sidechain's hook.

Evidence and reproducible private probes: `FX_EVIDENCE.md`, `stock-fx-qualified.log`, `stock-fx-bridge-qualified.log`, `fx-runtime-probe.py`, `qualify-stock-fx.mjs`, `fx-bridge-proof.cpp`. This proves software code equivalence with dormant hooks, not hardware audio, timing, or an identical instruction count. A second paired run after correcting the engine wake also passes (`fx-before-after-wake.log`, exit 0). All 26 complete stock arrays match before/after; all other P differences are limited to verified load-meter data and stock per-frame DMA-mask operands. No FX word is excluded. No base/FX source or asset was changed. Earlier fixed-address and incomplete-fill probes are retained as invalid comparison attempts, not product failures.

## Reproduction

Use Node 24.22.2 for repository tooling, Python 3.11 with Unicorn for the module checks, and the installed ColdFire toolchain. The full current SDK suite used Python 3.15 because existing upstream f-string syntax fails under Python 3.11; that first tooling failure is retained in `sdk-check.log`.

```sh
python3.11 -B sdk/octatrack/modules/turing-machine/generate.py --check
TURING_REFERENCE_DIR=/path/to/read-only/turing-arpgen/sdk/octabam/modules/turing-machine \
  python3.11 -B sdk/octatrack/modules/turing-machine/test_port.py -v
python3.11 -u -B sdk/octatrack/modules/turing-machine/verify.py \
  --base /private/diag/out/brief24/base079 \
  --package /private/diag/out/brief24/turing24.mwrm \
  --native /path/to/native-tooling --emulator /path/to/ot_emu \
  --output /private/diag/out/brief24/new-run
```

The initial direct-backend harness did not post the inert engine-queue wake that the USB transport posts. On an otherwise idle fresh boot, the base's engine service therefore never raised modules-ready; MODE/register and legacy-import checks correctly failed (`resume-persist.log`). A direct diagnostic call proved the file parser could restore the exact state, but is not acceptance evidence. The corrected harness posts the base's own inert message to the stock engine queue, waits for the real idle/event path, and asserts module-ready initialization. `import-wake.log` observes the actual event and restored state without calling Turing directly. No module/base firmware changed; the corrected-harness UI/S2, stock MIDI, legacy-file and paired FX reruns pass at exit 0. The unchanged full reload gate also passes: seven assertions at exit 0 in `run12-reload.log`, including exact saved MODE/register state and phrase identity after a fresh boot. The interrupted `wake-reload.log` has no exit record and is not acceptance evidence.

All firmware boots use ot_emu's MKII mode. The package harness installs through the existing backend on every boot, including saved-card fresh boots. The startup instruction allowance is bounded at 250 million because this current base boots after approximately 53.48 million instructions; the old emulator default was 50 million. Acceptance uses the DSP interpreter. A faster JIT experiment failed the unchanged D-major playback assertion and is not qualifying evidence (`jit-probe.log`).

## Unqualified and known behavior changes

Physical USB enumeration/install/Keep/Undo/removal, whole-set hardware headroom, CPU price, audio, dense incoming traffic, Part/channel changes under load, physical power-cycle persistence and screenshots are **not tested**. Emulator state and UART observations do not establish these. No push, PR or upstream/board post was made.

MODE/register anchors are per pattern/track in DRAM plus saved comments; LOCK/LEN/SCAL/DENS/SCALE/ROOT are shared per Part/track. Unsaved DRAM changes are lost on power-cycle or reinstall. Saved Part choice wins over legacy lines; FIRST is ignored. Old arp-MODE projects intentionally change because stock arp MODE is forced off, including fired MODE locks. WRITE remains encoder A push (`key:PUSHA@MIDI TURING`), not YES. No fixed-seed note difference is approved.
