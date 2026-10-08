# Turing Machine testing

M1 prototype, 8 October 2026. Emulator only; nothing here ran on hardware.

## Commands and exact revision

Sources in `sdk/drafts/turing-machine/` at this branch (`cursor/turing-machine-m1-06d4`), copied to
`sdk/octabam/modules/turing-machine/` in a native work copy for every build and run below:

| File | SHA-256 |
|---|---|
| `turing.c` | `644ad317b23a34ac899874dadf786845cd509cdc4f4a7497e089e9f905ac7d98` |
| `hooks.s` | `d9a25d1b97c1111b908f4242a180dbd351774ebf65c0378b9ab734a01046a7f9` |
| `turing.s` | `e0f99a4f84a593a24f2b52a3645728c34882e0e5b10efde9f2059775e157e053` |

Toolchain: m68k-elf-gcc 16.2.0 and GNU binutils 2.47, built from the release archives pinned in
`sdk/build/Dockerfile`. `python3 generate.py --check` confirms `turing.s` matches `turing.c` and
`hooks.s`. (Moving the folder into drafts changed only `turing.s`'s header comment; the rebuilt image
was byte-identical, `3ef31261…`.)

Base: stock OS 1.40C, MAIN OS SHA-256 `164f3122…0a84e` (matches
`src/engine/assets/stock-dsp-metadata.json`), extracted with `src/engine/elek.ts` and kept outside
the repository with every image built from it.

Native builds in a copy of `sdk/octabam` (`make bus REMIX=<name>`):

| Remix | Modules | Result | Image SHA-256 (local, not committed) |
|---|---|---|---|
| `turing` | TURING MACHINE | built: three MIDI SEQUENCER tables grown, the detour wired to `tm:tm_note_hook`, the row-count poke applied | `3ef31261…4fb6eb` |
| `turing-mix` | TURING MACHINE, SCALE QUANTIZER, EUCLID, CC MAP | built; no ledger refusal | `b1edee21…9f8af` |

## Emulator results

`python3 modules/turing-machine/verify.py <image>` (this folder's `verify.py`, run from the octabam
work copy) boots the image under the ColdFire port
(`out/emu/ot_emu`, built from this repository's `tools/emu/ot_emu`), makes its fixture through the
emulated panel on an empty scratch card and reads MIDI OUT as the bytes queued into the UART0
transmit ring. Fixture: MIDI track 1 on channel 1 with a trig on every step and NOT2 set; track 2 on
channel 2 with trigs on steps 1 and 9; 120 BPM.

Emulator builds: `2360ffb2…5af85115`, from this repository's unmodified `tools/emu/ot_emu`; and a
scratch build of the same sources with one added `uart0` query (below), which the gate does not use.
The `turing` image passed on both, the `turing-mix` image on the scratch build.

| Check | `turing` | `turing-mix` |
|---|---|---|
| TURING TRACK OFF: both tracks play their NOTE (C3) | pass | pass |
| OFF: NOT2 at a fixed interval above NOTE | pass | pass |
| The rows store T1 and LOCK 127 (battery RAM with check byte) | pass | pass |
| LOCK 127: at least 32 trigs; the 16-note phrase repeats exactly; it moves | pass | pass |
| LOCK 127: every note within NOTE..NOTE+24 | pass | pass |
| LOCK 127: NOT2 keeps the stock interval | pass | pass |
| LOCK 127: track 2 untouched | pass | pass |
| LOCK 64 set from the menu while playing; the phrase changes; range kept | pass | pass |
| Every note-on released; nothing sounding after STOP | pass | pass |

Separately, with a scratch build of the port that can return UART0's transmitted bytes (a local
`uart0` query, not in this repository):

- With TURING TRACK OFF, the MIDI OUT bytes for a four-trig pattern were identical to stock 1.40C's.
- With T1 and LOCK 127, a 16-step pattern sent `49 50 52 57 67 63 54 60 48 48 48 49 51 54 60 48`
  four times running; after LOCK 64 the line changed. 130 note-ons and 130 note-offs, none left
  sounding after STOP.
- The rows draw in the stock style under CC DIRECT CONNECT (LCD inspected; no capture committed).

## Not tested

- Arpeggiator on the track, NOTE parameter locks, trig conditions, incoming MIDI notes, live recording.
- Part, pattern or bank changes while playing; project save, load and reload; reboot. The settings are
  battery RAM and the emulator's battery RAM was not carried across boots.
- More than one track: the prototype drives one.
- Timing and load: no cycle count, no `cfmeter.py` run, no MIDI flood. `evidence/performance.json` is
  not written.
- The browser builder (`npm run module:verify`); the module is not in `sdk/catalog.json`.
- Hardware.

## Stock flows

Compared in the emulator with and without the module: a MIDI track's note output (identical bytes
with TURING TRACK OFF) and the MIDI SEQUENCER page (CC DIRECT CONNECT still first, showing its
value; two rows added below it; toggling it was not tried). Every other flow: not tested.

## Hardware

Untested.
