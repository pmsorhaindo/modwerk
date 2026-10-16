# Turing Machine testing

M2 in progress, 16 October 2026 (re-run on a fresh machine after the branches were brought up to date with
the fork's `main`; row labels moved into `.text` after `module:verify`). Emulator and toolchain only; nothing
here ran on hardware.

## Commands and exact revision

Sources in `sdk/drafts/turing-machine/` at this branch (`cursor/turing-machine-m2-06d4`), copied to
`sdk/octabam/modules/turing-machine/` in a native work copy for every build and run below:

| File | SHA-256 |
|---|---|
| `turing.c` | `cea03b82a120ca63b53349fe6c0f2a4180fe0c793fddb1c04e63fb9d97502387` |
| `hooks.s` | `7ba973de52def25c566b2a493e639dd733adad872f7af0e13d1ddd284e0184fb` |
| `turing.s` | `06d761928ad8e989804539d8b7f3698b5e2cf0c62206719b3f09ea7eadde7eb5` |
| `verify.py` | `4ac78842c9b752e92c49229938ca01fa9d085f6ef22a9a94369583f4b109d81f` |

Toolchain: the official `modwerk-source-tools` image, built on this machine with
`docker build --file sdk/build/Dockerfile --tag modwerk-source-tools .` (image `sha256:da50c792…9b`): m68k-elf-gcc
16.2.0 and GNU binutils 2.47 from the archives pinned there, and the patched DSP assembler. The native
image builds below use that image's `/usr/local` toolchain copied to the host; the emulator and `dsp_host`
are built from this repository's sources at the pinned vendor revisions. `python3 generate.py --check` confirms `turing.s` matches `turing.c` and `hooks.s`
and contains no instruction that both auto-modifies and addresses through one register.

Base: stock OS 1.40C from Elektron's official download (the zip `scripts/fetch-os.sh` names, SHA-256
`370c55a3…573ff0` as recorded there; `OCTATRACK_OS1.40C.bin` `34695b60…99e1ad`, identical to the owner's
copy used before). MAIN OS SHA-256 `164f3122…0a84e` (matches `src/engine/assets/stock-dsp-metadata.json`),
extracted with `src/engine/elek.ts` and kept outside the repository with every image built from it.

Native builds in a copy of `sdk/octabam` (`make bus REMIX=<name>`):

| Remix | Modules | Result | Image SHA-256 (local, not committed) |
|---|---|---|---|
| `turing` | TURING MACHINE | built: three MIDI SEQUENCER tables grown to 1+4 entries, five detours (the note hook and four project sites), row count 1 → 5 | `f2ce92f5…31199a9d` |
| `turing-mix` | TURING MACHINE, SCALE QUANTIZER, EUCLID, CC MAP | built; no ledger refusal | `2cc1c461…364c6ef82` |

Before the label fix, the same sources rebuilt the images recorded on 9 October byte for byte
(`47b44879…c4f638a4`, `402ca72a…a0b31507`), with the image's toolchain on a fresh machine.

## Emulator results

`python3 modules/turing-machine/verify.py <image>` (this folder's `verify.py`, run from the octabam work
copy) boots the image four times under the ColdFire port (`out/emu/ot_emu`), makes each fixture through
the emulated panel on an empty scratch card and reads MIDI OUT as the bytes queued into the UART0 transmit
ring. It takes about 35 minutes on its own. Emulator: `2360ffb2…5af85115`, built from this repository's unmodified
`tools/emu/ot_emu`, and a scratch build of the same sources with an added `uart0` query, which the gate
does not use.

Boot 1, fixed test seed `0x13572468`: MIDI track 1 on channel 1 with a trig on every step and NOT2 set,
track 2 on channel 2 with a trig on every step, 120 BPM. Every note of the Turing phases is compared with
a Python model of `tm_step` from the same seed.

| Check | `turing` |
|---|---|
| Every MODE OFF: track 1 plays NOTE (C3) and NOT2 a fixed interval above; track 2 plays NOTE | pass |
| The rows store T1 ON 127/16 and T2 ON 127/5 in a valid battery-RAM record | pass |
| T1, LOCK 127, LENGTH 16: every note as the model predicts; repeats every 16 trigs | pass |
| T2, LOCK 127, LENGTH 5: every note as the model predicts; repeats every 5 trigs | pass |
| NOT2 keeps the stock interval | pass |
| After STOP, T1 LOCK 64 and T2 LOCK 0 LENGTH 16, then PLAY: every note as the model predicts (the registers were not reseeded) | pass |
| LOCK 64: the phrase keeps changing; every note within NOTE..NOTE+24 | pass |
| LOCK 127 set from the menu while playing: the phrase freezes | pass |
| Every note-on released; nothing sounding after STOP | pass |

Boots 2 and 3, no test seed: T1 ON, LOCK 127, LENGTH 16, PLAY 500 ms and 2,700 ms after the fixture.

| Check | `turing` |
|---|---|
| Each boot plays a full 16-note phrase within the range | pass |
| The two boots' first phrases differ | pass |
| Neither is the fixed seed's phrase | pass |

Boot 4, a writable scratch card: T1 ON 127/8 is set, then a set and an empty project are created through
the panel; T1 is set again and the project saved, T1 set back to OFF and the project reloaded.

| Check | `turing` |
|---|---|
| The new project starts every track OFF (T1 was ON before it) | pass |
| After SAVE, T1 set back to OFF | pass |
| RELOAD restores T1 ON, LOCK 127, LENGTH 8 | pass |
| `project.work` on the card holds exactly `#TURING_T1=1,127,8` | pass |
| The line follows `PATTERN_CHANGE_AUTO_SILENCE_TRACKS` | pass |

The same 26 checks on `turing-mix`: all pass.

Runs: on 16 October all 26 checks passed on both images before the label fix (`47b44879…`, `402ca72a…`)
then on both images after it (`f2ce92f5…`, `2cc1c461…`), the current sources. One intermediate run on the
fixed combined image failed "after SAVE, T1 set back to OFF": the menu edit after SAVE did not take, as
when SAVE is still writing (that run shared the machine with `npm run check`). The gate now waits until the
card's written-sector count stops changing after creating, saving and reloading a project, never less than
the previous fixed waits, and the rerun passed all 26 on both images.

A separate save on `turing-mix`, read back from the card: `project.work` and `project.strd` hold
`#SEQUENCER_SCALE=0`, `#SEQUENCER_ROOT=0`, `PATTERN_CHANGE_AUTO_SILENCE_TRACKS=0`, `#TURING_T1=1,127,8`,
`PATTERN_CHANGE_AUTO_TRIG_LFOS=0`, in that order: both modules' lines, each from its own site.

Separately, with the scratch `uart0` build, every MODE OFF on the `turing` image: the MIDI OUT bytes for a
four-trig pattern were identical to stock 1.40C's.

## Toolchain check: `module:verify`

`npm run module:verify -- turing-machine --os <OCTATRACK_OS1.40C.bin> --jobs 2`, 16 October 2026, with the
official image above. The module is not listed, so the run used a disposable local worktree of this branch
that listed it the way ADD_A_MODULE step 4 does, and nothing from that worktree is committed:

- the folder copied to `sdk/octabam/modules/turing-machine/`, a `sdk/catalog.json` pin
  (`0.1.0-experimental`), `turing-machine` appended to `REQUESTED` in `scripts/build-module-packages.py`;
- packages compiled in the image with `scripts/build-modules-isolated.sh` and imported with
  `npm run modules:import -- … --development`;
- the module's document appended to `src/catalog/module-documents.json` by hand, because
  `modules:generate` refuses an unqualified module (no cycles, memory or hardware evidence yet).

First run: 0 of 48 buildable selections matched native, 66 refusals matched. A byte diff of Turing alone
(native image written with `export-composition-proofs.py --image-dir`, outside the checkout, deleted after)
showed one difference: 14 bytes of the grown MIDI SEQUENCER label table. The row labels were C `const`
strings in `.rodata`; the browser and native place a DRAM unit's `.rodata` differently, and the stock table
points at them. Fixed by defining the labels in `hooks.s`'s `.text`, as Scale Quantizer does.

After the fix: **114 selections, 48 built and matching native outside the platform writes, 66 matching
refusals, 0 mismatches.** The record is [evidence/native-comparison.json](evidence/native-comparison.json)
(fingerprints only; module source `1c1f3475…`, pool of 17 modules). The refusals are space and overlap
refusals that browser and native agree on: 44 Scale Quantizer and FM Synth claiming one cave, 10 FM Synth
and VECTOR claiming one hook site, 7 label formatters not fitting, 2 Mute Modes' cave not free, 2 past the
stock zero run, 1 an FX1 chooser list too long. 32 of them are refused without Turing as well, by the other
modules' own records; 34 have no record without Turing; none builds without Turing and fails with it.

Native declaration checks were recorded for 27,904 selections (written to the worktree's
`src/catalog/native-metadata.json`, not committed).

Listing the module (M2's catalog step) needs, beyond this folder: the folder in `sdk/octabam/modules/`,
the `sdk/catalog.json` pin, `turing-machine` in `REQUESTED` in `scripts/build-module-packages.py`, the
rebuilt packages, its `src/engine/assets/chooser-metadata.json` entry (`fxId` null, not on FX1), the
declaration checks and `sdk/native-comparisons/turing-machine.json`. The qualification record must exist
first.

## Fixed on the way

`module:verify` found the row labels' `.rodata` placement above.

GCC 16.2 compiled the settings write into `move.b (%a0)+,(%a0,%d1.l)`. The CPU forms the destination after
the source's increment, so every byte of the record landed one address high, the record never validated,
and each row edit started again from the defaults. Seen in the emulator as a record beginning `00 54 4d`.
`generate.py` now passes `-fno-auto-inc-dec` and refuses that instruction shape.

## Not tested

- Arpeggiator on a track, NOTE parameter locks, trig conditions, incoming MIDI notes, live recording.
- Part, pattern or bank changes while playing; CHANGE to another saved project (a CHANGE that reloaded the
  same project restored its line, in a scratch run); SAVE TO NEW and EXPORT TO SET; reboot with the
  emulator's battery RAM carried across. Loading a saved project on stock firmware relies on the stock
  loader skipping `#` lines, as Scale Quantizer documents; not run here.
- DMA timer 3 on a unit: the seed source is inferred from stock's own programming of the timer.
- Timing and load: no cycle count, no `cfmeter.py` run, no MIDI flood. `evidence/performance.json` is not
  written.
- Hardware.

## Stock flows

Compared in the emulator with and without the module: a MIDI track's note output (identical bytes with
every MODE OFF) and the MIDI SEQUENCER page (CC DIRECT CONNECT still first, showing its value; four rows
added below it, the page scrolls; toggling CC DIRECT CONNECT was not tried). Every other flow: not tested.

## Hardware

Untested.
