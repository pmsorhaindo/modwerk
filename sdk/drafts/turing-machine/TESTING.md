# Turing Machine testing

M2 in progress, 9 October 2026 (per-project settings added). Emulator only; nothing here ran on hardware.

## Commands and exact revision

Sources in `sdk/drafts/turing-machine/` at this branch (`cursor/turing-machine-m2-06d4`), copied to
`sdk/octabam/modules/turing-machine/` in a native work copy for every build and run below:

| File | SHA-256 |
|---|---|
| `turing.c` | `839d456db340e8019507a10a65bb35ef028d80a8e44f8d88660d2252e6578cf3` |
| `hooks.s` | `9c1d6f992a611ca5aea2a4662a30ce3829323391d30459350cf0d1166e87f0b9` |
| `turing.s` | `f18b8db578b6b65520948df3a3c5801ab987b4dd4b5f7369f0d15c20dce04211` |
| `verify.py` | `ab71590fe0e12754b12e8f86706a150f3ede331e9d986534ed3e63484dba48f7` |

Toolchain: m68k-elf-gcc 16.2.0 and GNU binutils 2.47, built from the release archives pinned in
`sdk/build/Dockerfile`. `python3 generate.py --check` confirms `turing.s` matches `turing.c` and `hooks.s`
and contains no instruction that both auto-modifies and addresses through one register.

Base: stock OS 1.40C, MAIN OS SHA-256 `164f3122…0a84e` (matches
`src/engine/assets/stock-dsp-metadata.json`), extracted with `src/engine/elek.ts` and kept outside the
repository with every image built from it.

Native builds in a copy of `sdk/octabam` (`make bus REMIX=<name>`):

| Remix | Modules | Result | Image SHA-256 (local, not committed) |
|---|---|---|---|
| `turing` | TURING MACHINE | built: three MIDI SEQUENCER tables grown to 1+4 entries, five detours (the note hook and four project sites), row count 1 → 5 | `47b44879…c4f638a4` |
| `turing-mix` | TURING MACHINE, SCALE QUANTIZER, EUCLID, CC MAP | built; no ledger refusal | `402ca72a…a0b31507` |

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

A separate save on `turing-mix`, read back from the card: `project.work` and `project.strd` hold
`#SEQUENCER_SCALE=0`, `#SEQUENCER_ROOT=0`, `PATTERN_CHANGE_AUTO_SILENCE_TRACKS=0`, `#TURING_T1=1,127,8`,
`PATTERN_CHANGE_AUTO_TRIG_LFOS=0`, in that order: both modules' lines, each from its own site.

Separately, with the scratch `uart0` build, every MODE OFF on the `turing` image: the MIDI OUT bytes for a
four-trig pattern were identical to stock 1.40C's.

## Fixed on the way

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
- The browser builder (`npm run module:verify`); the module is not in `sdk/catalog.json`.
- Hardware.

## Stock flows

Compared in the emulator with and without the module: a MIDI track's note output (identical bytes with
every MODE OFF) and the MIDI SEQUENCER page (CC DIRECT CONNECT still first, showing its value; four rows
added below it, the page scrolls; toggling CC DIRECT CONNECT was not tried). Every other flow: not tested.

## Hardware

Untested.
