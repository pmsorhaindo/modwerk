# Turing Machine 0.5.1-experimental — local review qualification

**Hardware untested / #1697 draft.** These are software observations on the unchanged Modwerk base **0.7.9**, stock OS **1.40C**, in ot_emu MKII mode. No physical USB, MIDI, flash, listening or power-cycle test was performed. Neither base 0.7.7 nor MKI hardware is qualified. Later bases are untested. The numeric base version is a support boundary, not a version field enforced by the package protocol.

The module lives in `sdk/drafts/turing-machine/`; its draft release notes are `CHANGELOG.json`. No catalogue entry or distribution package is published. Michael accepted behavioural stock-FX equivalence versus 1.40C on 19 November 2026, 17:13 CET. The approved FUNC rules remain: no FUNC+LOCK shortcut, release FUNC after FUNC+AMP before SCALE/ROOT edits, stock host unchanged. No fixed-seed note difference is approved.

## Exact acceptance build

The documented command `npm run module:dev -- turing-machine --build-only --out /private/review-turing24.mwrm` built the acceptance artifact, title **Turing Machine**, using the installed, read-only native toolchain. Local evidence is under `../diag/out/brief24/`; no firmware, binary, card, dump or extracted stock data is committed.

`review-build-final.log`: **19,860 initialized bytes + 162,384 BSS = 182,244 bytes (178.0 KiB)**, 246 relocations, three table/event hooks and nine code sites. This is below the 128 KiB initialized-image and 288 KiB total caps; loader overhead and whole-set headroom are unmeasured. The package harness links the committed assembly and shared scale SDK and asserts exact initialized-image bytes, BSS size and relocation count before every acceptance boot. Explicit zero tables now reside in BSS, which the runtime loader clears. `manifest.py` remains the build recipe for the module package; it does not qualify the superseded all-in-one card route.

The executed source revision is `7b74656e5` (legacy WRITE compatibility included). Subsequent assembly comments do not change the executable image. Harness and documentation revisions are recorded separately in the private review response.

## Review observations

A full ledger with exit status and interrupted attempts is in the private `CODEX_REPORT24.md` and `REVIEW24_RESPONSE.md`. Logs below have the prefix `review-`. Pending rows are not passes.

| Gate | Observation | Local evidence |
| --- | --- | --- |
| Fixed-seed C engine | PASS: 3,870,720 transitions, three note ranges per transition, versus read-only turing-arpgen | `review-port-native.log` |
| Linked ColdFire note-key entry | PASS: 4,644 signed-byte inputs across OFF/MAJ/MIN and all roots, executing the shipped inlined wrapper. The separate shared wrapper also passes 4,680 inputs including 128. | `review-runtime.log`, `review-port-native.log` |
| Ownership, WRITE, UI and load races | PASS: ten executed ColdFire tests, including AKL 84, unchanged lock bytes 30/31, owned centre serialization, stock mirror/edited/index contract, covered window, divergent displayed/playing Parts, failed load and migration generation interleavings | `review-runtime.log` |
| Late importer | PASS: chunk/partial/final-newline parsing, transient directory/open/read retries, and rejection of superseded-project text/completion | `review-import.log` |
| Fixed-seed firmware reference | Rerun in progress: OFF/four keys plus four unlocked LEN 5/7, DENS 64, SCAL 0/127 cases | `review-reference-final.log` |
| UI / S2 / stock MIDI | PASS: corrected backend-wake harness, 14 UI/S2 and six stock fixture/contract assertions, exit 0; MODE-OFF messages, clock/transport, tick and track-step counts | `review-wake-smoke.log` |
| AKL coexistence and held-FUNC TRAN | Rerun in progress: AKL non-Turing four-note chords, WRITE preserves AKL KEY/shift, covered NOTE SETUP, actual TRAN transposition | `review-coexist-final.log` |
| SAVE / RELOAD / fresh saved-card boot | In progress: stronger gate clears the two edited flags after saving the fixture, proves WRITE alone sets them, and compares MODE-OFF written trigs after RELOAD and a fresh boot, alongside the original strict MODE-ON phrase checks | `review-reload.log` |
| Natural Kept-set restore / PROJECT CHANGE | In progress: actual base card writer and plain boot, without backend reinstall or manual wake on the restoring boot | `review-lifecycle-v2.log` |
| Paired FX after real modules-ready | PASS: all 26 complete arrays byte-identical before/after Turing; no FX word excluded | `review-fx-capture.log` |
| Draft doctor | PASS: experimental checks green, exit 0; publication, CPU, screenshots and hardware requirements remain pending | `review-doctor.log` |
| Repository check / PR readiness | Rerun after this ledger update. First review check correctly rejected the stale 0.5.0 TESTING heading. | `review-check.log` |

The expanded reference initially decoded repeated bytes because ot_emu **adds** memory-watch ranges on each `watchmem`. Re-registering the same ring duplicates each queued byte and breaks MIDI running status. `watch_midi_out` now registers each ring once per port; raw UART output demonstrated the discrepancy. Failed/interrupted diagnostic logs are retained, not silently counted as passes. The strict musical assertions remain.

## Sequencer cost

The linked instruction counter executes eight ON tracks with non-following catch-up to step 63. LEN 2/3/4/5/6/7 costs respectively **54,690 / 56,463 / 58,277 / 60,546 / 62,809 / 64,642** instructions across eight tracks, at most **8,151** on one track. Configuration is computed once per evaluated track, not twice. WRITE of 16 steps costs 11,749 module instructions. The isolated runner replaces the stock evaluator and edit-done routine with ABI stubs: these counts exclude firmware cost, interrupt interference and uncached bus latency. They are not hardware timing, CPU price or proof of real-time headroom.

## Stock FX: exactly what matches

**Before versus after Turing on base 0.7.9: byte-identical.** The paired `review-fx-capture.log` captures all 13 complete arrays on each DSP after the real modules-ready event. All 26 match, including COMPRESSOR and SPRING; no FX word is ignored. Resident-P differences in this pair are six core-A and three core-B meter words; no DMA-mask operand differs in this pair.

**Base 0.7.9 versus original 1.40C: behaviourally identical in the bounded software proof, not wholly byte-identical.** Twelve arrays per core and the shared helpers match after documented relocation normalization. The base's existing COMPRESSOR bridge differs in four words per core (176/180 words match). The dormant bridge paths reproduce the displaced stock prefixes over 4,096 seeded machine states per core/entry, 16,384 comparisons, with equal registers, status, stack/return state and X/Y memory. The unchanged remainder resumes with equal state. `stock-fx-qualified.log`, `stock-fx-bridge-qualified.log` and `FX_EVIDENCE.md` hold that earlier proof; the base and its captured FX code are unchanged. Michael explicitly accepted this behavioural comparison. No hardware audible/timing or exhaustive-state equivalence is claimed.

## State and compatibility

LOCK/LEN/SCAL/DENS/SCALE/ROOT and the TURING choice use the stock Part and its mirror; they follow stock's Part persistence. MODE/register anchors and WRITE centres are module-owned DRAM plus saved-project comments. Unsaved DRAM state is lost on reinstall or power-cycle. Legacy WRITE centres are read only from W (87), outside valid AKL KEY 0..84; new WRITE never changes those shared bytes. Saved Part choice wins over old comments; FIRST is ignored. The stock arp is forced off for Turing, including fired MODE locks. AKL's key/shift locks remain intact and are inert while Turing owns that track. Encoder A push belongs to `key:PUSHA@MIDI AMP`; covered windows suppress it.

The current guarded project/step/PLAY/chord/push detours are exclusive stock sites. Shared multi-subscriber project hooks, push callbacks and a per-step generator ABI require separate owner-reviewed base work; no base/host/FX patch is part of this port.

## Reproduction and limits

Use Node 24, the ColdFire toolchain, Python 3.11 plus Unicorn for linked tests, and Python 3.15 for the repository's current SDK suite. The module gate needs private stock/tooling paths; none is downloaded or redistributed.

```sh
python3.11 sdk/drafts/turing-machine/generate.py --check
TURING_REFERENCE_DIR=/read-only/turing-arpgen/sdk/octabam/modules/turing-machine \
  python3.11 sdk/drafts/turing-machine/test_port.py -v
python3.11 sdk/drafts/turing-machine/test_runtime.py -v
python3.11 sdk/drafts/turing-machine/test_import.py -v
python3.11 -u -B sdk/drafts/turing-machine/verify.py \
  --base /private/base079 --package /private/review-turing24.mwrm \
  --native /read-only/native-tooling --emulator /private/ot_emu \
  --output /private/new-run
npm run module:doctor -- --draft turing-machine
```

Every package-harness boot posts the transport's actual inert engine-queue wake after direct backend installation and checks the real modules-ready callback. That is an emulator backend fixture, not a physical USB run. A natural Kept-set restoring boot is tested separately. The startup allowance is 250 million instructions because this base exceeds ot_emu's older 50-million default. Acceptance uses the DSP interpreter, not the failed historical JIT experiment.

Earlier 0.5.0 engine/LOCK/LEN/SCAL/density/WRITE/model/clock/legacy-file/backend lifecycle passes remain historical evidence only (`run12-reload.log`, `resume-*.log`, `beta.log`); they do not qualify changed 0.5.1 paths. Physical install/Keep/Undo/removal, CPU price, audio, dense traffic, Part/channel changes under load, physical persistence, whole-set headroom and screenshots remain **not tested**. No push, PR or upstream/board post was made.
