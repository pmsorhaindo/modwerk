# Turing Machine testing

M2 in progress, 8 October 2026. Emulator only; nothing here ran on hardware.

## Commands and exact revision

Sources in `sdk/drafts/turing-machine/` at this branch (`cursor/turing-machine-m2-06d4`), copied to
`sdk/octabam/modules/turing-machine/` in a native work copy for every build and run below:

| File | SHA-256 |
|---|---|
| `turing.c` | `ef57b0b9d16faafe07088592eec11405c5143d0749cb01fab673e4c74ad49449` |
| `hooks.s` | `cd94af2708e463dd1fca2c58a780d9f1d9bfe90bd575df7cc13c82d841515c5c` |
| `turing.s` | `f251c1d15c9d128dca29324f68aacb50e1065658911a2d81c29ab840909ae262` |
| `verify.py` | `9f5ce5c12716ecde169f0d7b88008e7b3dfe33318e0918396952fc80d53b64fa` |

Toolchain: m68k-elf-gcc 16.2.0 and GNU binutils 2.47, built from the release archives pinned in
`sdk/build/Dockerfile`. `python3 generate.py --check` confirms `turing.s` matches `turing.c` and `hooks.s`
and contains no instruction that both auto-modifies and addresses through one register.

Base: stock OS 1.40C, MAIN OS SHA-256 `164f3122…0a84e` (matches
`src/engine/assets/stock-dsp-metadata.json`), extracted with `src/engine/elek.ts` and kept outside the
repository with every image built from it.

Native builds in a copy of `sdk/octabam` (`make bus REMIX=<name>`):

| Remix | Modules | Result | Image SHA-256 (local, not committed) |
|---|---|---|---|
| `turing` | TURING MACHINE | built: three MIDI SEQUENCER tables grown to 1+4 entries, the detour wired to `tm:tm_note_hook`, row count 1 → 5 | `f4d565ba…bc41527` |
| `turing-mix` | TURING MACHINE, SCALE QUANTIZER, EUCLID, CC MAP | built; no ledger refusal | `c4b7d803…4016d0f75` |

## Emulator results

`python3 modules/turing-machine/verify.py <image>` (this folder's `verify.py`, run from the octabam work
copy) boots the image three times under the ColdFire port (`out/emu/ot_emu`), makes each fixture through
the emulated panel on an empty scratch card and reads MIDI OUT as the bytes queued into the UART0 transmit
ring. It takes about 20 minutes. Emulator: `2360ffb2…5af85115`, built from this repository's unmodified
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

The same 21 checks on `turing-mix`: all pass.

Separately, with the scratch `uart0` build, every MODE OFF on the `turing` image: the MIDI OUT bytes for a
four-trig pattern were identical to stock 1.40C's.

## Fixed on the way

GCC 16.2 compiled the settings write into `move.b (%a0)+,(%a0,%d1.l)`. The CPU forms the destination after
the source's increment, so every byte of the record landed one address high, the record never validated,
and each row edit started again from the defaults. Seen in the emulator as a record beginning `00 54 4d`.
`generate.py` now passes `-fno-auto-inc-dec` and refuses that instruction shape.

## Not tested

- Arpeggiator on a track, NOTE parameter locks, trig conditions, incoming MIDI notes, live recording.
- Part, pattern or bank changes while playing; project save, load and reload; reboot with the emulator's
  battery RAM carried across.
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
