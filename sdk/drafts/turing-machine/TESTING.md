# Turing Machine 0.5.1-experimental — review qualification

**Hardware untested / #1697 draft.** These are local software observations on unchanged Modwerk base **0.7.9**, stock OS **1.40C**, in ot_emu MKII mode, on 19–20 November 2026. No physical USB, MIDI, flashing, listening or power-cycle test was performed. Base 0.7.7, later bases and MKI hardware are unqualified. The numeric base version is a support boundary, not an admission field enforced by this package protocol.

The module and its five-line draft release notes remain under `sdk/drafts/turing-machine/`. No catalogue entry or distribution package is published. Michael accepted behavioural stock-FX equivalence versus 1.40C on 19 November, 17:13 CET. The approved FUNC rules remain: no FUNC+LOCK shortcut, release FUNC after FUNC+AMP before editing SCALE/ROOT, stock host unchanged. No fixed-seed note difference is approved.

## Exact acceptance build

The documented command below produced the acceptance artifact, title **Turing Machine**, using installed read-only native tooling. All evidence and binaries remain local under `../diag/out/brief24/`; firmware, cards, dumps and extracted stock data are never committed.

```sh
npm run module:dev -- turing-machine --build-only \
  --out /private/review-turing24-overlay.mwrm
```

`review-overlay-build.log` records **19,868 initialized bytes + 162,384 BSS = 182,252 bytes (178.0 KiB)**, 245 relocations, three table/event hooks and nine stock-code sites. This is below the 128 KiB image and 288 KiB total caps. Loader overhead and whole-set headroom are unmeasured. Zero tables use runtime-cleared BSS. `manifest.py` is the required module-package build recipe; the superseded all-in-one card route is not qualified.

Executable source is **01862ba23**. Latest acceptance harness is **5d079ee9a**; strict reload uses **54d17dc36**, full lifecycle **500105d66**, and the final cached project-change replay **5d079ee9a**. Later changes are harness/documentation only. Every package boot links committed assembly/shared scale SDK and asserts exact image bytes, BSS and relocation count. Natural Kept restores also compare the base owner's immutable SHA with the full acceptance package. A matching module ID alone is insufficient.

## Observed gates

Full exit records, retained failures and every review finding/commit are in the private `CODEX_REPORT24.md` and `REVIEW24_RESPONSE.md`. Log names below are relative to `diag/out/brief24/`.

| Gate | Result | Evidence |
| --- | --- | --- |
| Fixed-seed C reference | PASS: 3,870,720 transitions × three note ranges versus read-only turing-arpgen | `review-overlay-native.log` |
| Separate shared-scale ColdFire wrapper | PASS: 4,680 OFF/MAJ/MIN and range-edge inputs, no skips | `review-overlay-native.log` |
| Actual linked package | PASS: twelve tests, including 4,644 shipped inlined note-key cases, AKL ownership, WRITE contract/centres, queued pattern ownership, displayed Part, load races and both WRITE edges in all five overlay slots | `review-overlay-runtime.log` |
| Actual importer | PASS: 3,072 chunk/partial/final-newline cases, directory/open/read retry, failed-load recovery and superseded text/completion rejection | `review-overlay-import.log` |
| Fixed-seed firmware reference | PASS: 59 assertions, exit 0; nine locked/unlocked cases with raw UART/queued-message cross-checks | `review-overlay-reference.log` |
| UI/S2, stock MIDI and cached legacy files | PASS: 22 assertions, exit 0; approved FUNC/Part controls, MODE-OFF messages equal stock, clock/transport/ticks/steps, old-file import/migration | `review-overlay-wake.log` |
| Actual AKL, menus, FUNC TRAN and patterns | PASS: 18 assertions, exit 0; non-Turing four-note B-Locrian chords, WRITE preserves KEY/shift, SETUP/PROJECT-menu suppression, exact TRAN +1 and no mixed pattern bars | `review-overlay-coexist.log` |
| Strict WRITE/SAVE/RELOAD/fresh boot | PASS: ten assertions, exit 0; WRITE alone dirties the clean bank and changes actual card bytes; exact MODE-OFF trigs and MODE-ON register/phrase survive both RELOAD and fresh boot; track keys work | `review-overlay-reload-card.log` |
| Real card writer, natural Kept restore, normal PROJECT CHANGE | PASS: nine assertions, exit 0; exact package, no backend reinstall/manual wake on restoring boot, real modules-ready import, exact saved phrase, legacy T2 migration and retained T1 Part settings | `review-overlay-lifecycle-final.log` |
| Cached real-Set project-change replay | PASS: four assertions, exit 0 | `review-overlay-projectchange-final.log` |
| Paired FX after real notification | PASS: all 26 complete arrays byte-identical before/after Turing, no excluded FX word | `review-overlay-fx.log` |
| Build, admission, memory and source isolation | PASS: documented package, exact Undo/corruption rejection, caps, no protected-range literal/image address, unchanged compiled base/host/FX sources/assets, no new tracked binary | `review-overlay-build.log`, `review-overlay-admission.log`, `review-overlay-storage-audit.log` |
| generate.py --check | PASS | `review-overlay-generate.log` |
| Draft doctor | PASS experimental checks, exit 0; board disabled under no-post instruction; hardware/CPU/screenshots/catalogue/packages remain release requirements | `review-final-doctor.log` |
| Full repository check | PASS exit 0: 3,258 app tests (10 skipped), 718 SDK tests in 125 jobs, isolated draft-doctor 2 passed/4 skipped; expected stock/tool/platform skips remain in log | `review-overlay-check.log` |
| pr:ready | Behind current main; final clean-tree result recorded in private ledger | Private review response |

## Sequencer cost

The linked instruction counter executes eight ON tracks catching up to step 63. LEN 2/3/4/5/6/7 costs **54,690 / 56,463 / 58,277 / 60,546 / 62,809 / 64,642** module instructions across eight tracks; maximum **8,151** on one track. Configuration is computed once per evaluated track. WRITE of sixteen steps costs 11,749 module instructions. Stock evaluator/edit-done routines are ABI stubs in this runner: firmware cost, uncached bus latency and interrupt interference are excluded. This is bounded software cost, not hardware timing, CPU price or real-time headroom.

## Stock FX: exact distinction

**Before versus after Turing on base 0.7.9: byte-identical.** `review-overlay-fx.log` captures all thirteen complete arrays on each DSP after the real modules-ready event. All 26 match, including COMPRESSOR and SPRING; no FX word is ignored. Resident-P differences are six core-A and three core-B meter words; no DMA-mask operand differs in this pair.

**Base 0.7.9 versus original 1.40C: behaviourally identical in the bounded proof, not wholly byte-identical.** Twelve arrays per core/helpers match after documented relocation normalization. The base's existing COMPRESSOR bridge changes four words per core (176/180 words match). Dormant bridge prefixes reproduce displaced stock state over 16,384 seeded DSP-interpreter comparisons, including registers/status, stack/return state and X/Y memory. `stock-fx-qualified.log`, `stock-fx-bridge-qualified.log` and `FX_EVIDENCE.md` hold the earlier proof; the base and captured FX code are unchanged. Michael explicitly accepted this result. No exhaustive-state or physical audio/timing equivalence is claimed.

## Corrections and limits

The expanded reference first exposed additive MIDI memory-watch registration duplicating queued bytes. Each ring is now registered once, and raw UART is independently cross-checked. A real queued last-step chord leak across pattern/Part boundaries was fixed in `32019deda`. A further real PROJECT-menu WRITE leak was reproduced and fixed in `01862ba23`; the original SETUP guard alone was insufficient.

Persistence fixtures now enter the generator through real SRC/AMP navigation and assert page ownership, select channels from observed saved values, preserve empty Set/AUDIO directories omitted by file-only card extraction, and require an actual saved bank-file change after WRITE. Stock's DISARM ALL toast is allowed to expire: repeated NO refreshed it indefinitely. Legacy migration uses an unselected track while separately preserving already-selected Part settings. No musical assertion, card wait or equality expectation was relaxed. Failed/interrupted runs remain retained; they are not passes. The first full check overlapped doctor's temporary published-tree staging and failed generation; a subsequent sequential full check passed.

LOCK/LEN/SCAL/DENS/SCALE/ROOT and generator choice follow stock Part persistence. MODE/register anchors and WRITE centres use owned DRAM plus saved-project comments; unsaved DRAM is lost on reinstall/power-cycle. Saved Part choice wins; FIRST is ignored. Legacy W=87 centres are read only, outside valid AKL KEY 0..84; new WRITE never stores those shared bytes. AKL locks remain intact and inert while Turing owns the track. WRITE uses `key:PUSHA@MIDI AMP`; covering windows/popups suppress it.

Current project/step/PLAY/chord/push detours are exclusive. Shared project hooks, push callbacks and a multi-generator per-step ABI need separate owner-reviewed base work. No base/host/FX patch or dependency on another module is part of this draft.

Targeted runtime on 0.7.7 remains untested. A source-derived capability test (ABI 10, mandatory features 135, maxSites/maxCopies 128 at `46b979ddb`) **admits** the package; it does not refuse it by version number. No semantic base-version floor is encoded. Later compatible bases are not artificially digest-pinned, and no later-base qualification is implied.

Physical install/Keep/Undo/removal, listening, dense physical MIDI traffic, CPU price, Part/channel changes under load, physical persistence, whole-set headroom and release screenshots remain **not tested**. Earlier 0.5.0 comprehensive engine/clock/models/backend results remain historical, not fresh qualification of changed 0.5.1 paths. No push, PR, external post or hardware access occurred.

## Reproduction

Use Node 24, ColdFire tools, Python 3.11 with Unicorn for linked tests, and Python 3.15 for the repository SDK suite. Private stock/tooling paths are required and are never redistributed.

```sh
python3.11 sdk/drafts/turing-machine/generate.py --check
TURING_REFERENCE_DIR=/read-only/turing-arpgen/sdk/octabam/modules/turing-machine \
  /private/unicorn-venv/bin/python sdk/drafts/turing-machine/test_port.py -v
/private/unicorn-venv/bin/python sdk/drafts/turing-machine/test_runtime.py -v
python3.11 sdk/drafts/turing-machine/test_import.py -v
python3.11 -u -B sdk/drafts/turing-machine/verify.py \
  --base /private/base079 --package /private/review-turing24-overlay.mwrm \
  --native /read-only/native-tooling --emulator /private/ot_emu \
  --output /private/new-run
MODWERK_BOARD=off npm run module:doctor -- --draft turing-machine
```

Ordinary direct-backend fixtures post the transport's real inert engine wake and assert actual modules-ready. Natural Kept restoring boots forbid that wake and backend reinstall. Startup uses 250 million instructions because this base exceeds the old 50-million default. Acceptance uses the DSP interpreter, not the failed historical JIT experiment. All reference/sentinel operations are confined to private emulator memory; the candidate's protected-range read/write traps remain active in linked tests.
