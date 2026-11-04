# CUBE: testing

The build tested is `OCTATRACK_CUBE_PR`: `make image REMIX=cube` on this branch, static-stock,
built from the tester's own 1.40C. Its MAIN OS sha1 is in the pull request. Everything below ran
in the emulator (`ot_emu`, the ColdFire port with both DSP cores) or in `cube_host`. Nothing in
this file was observed on hardware.

## Gates

| Command | What it shows | Result |
|---|---|---|
| `python3 modules/cube/verify.py dsp` | The engine (`cube_voice.asm`) against `cube_model.py`, word for word: every patch, both voices, trig split, SYNC HARD, TONE, LINK, LAW, the epoch init from garbage memory, and the worst-case cycles through the seam | 21 PASS |
| `verify_static.py fx IMAGE ELF STOCK` | The FX1 and FX2 choosers of T1, T4, T5 and T8 draw row for row what stock 1.40C draws. Each row picked on FX1 (T1, T5) and FX2 (T2, T6) stores stock's bytes | 24 PASS (FX1 11 rows, FX2 15 rows; SPRING REV 0x15) |
| `verify_static.py fxaudio …` | The same rows stepped on THRU tracks of both cores, with each effect's six knobs turned off their defaults, compared on MAIN (after the effects) with stock and with a stock control run 2.3 s later. Rows stock repeats within 2 LSB of itself (rows 0, 2-4 and 7-9) must match within 2 LSB. Rows that depend on start timing (row 1 FILTER with its knobs moved, PHASER, FLANGER, row 10, DELAY, PLATE, SPRING, DARK) must match within 1 dB of level. On stock, every row changes MAIN from all-NONE | 58 PASS |
| `verify_static.py dspmem …` | The P memory both DSP cores booted. Core 0 is stock's word for word, and core 1 is stock's except the seam's two words, with CUBE's 459 above P:0x1d9f. Stock's own run-time P words (A 0x58c/0x59b, B 0x371/0x380) are not compared | 4 PASS |
| `verify_static.py fxid …` | Each chooser row picked on T3, T4, T7 and T8 stores the id stock stores | 96 PASS |
| `verify_static.py ui …` | Machine lists: six rows on T1, stock's five on T5 (screens identical to stock), and no CUBE reachable on T5/T8. A CUBE signature planted on T6 reverts to FLEX. CUBE's defaults reach the live SETUP copy before any PLAY. SRC `PTCH FM MIX / X Y Z`, OSC B `BPCH LAW LINK / BX BY BZ`, SETUP `FINE OCT UNI / TONE MORPH SYNC`: each knob moves only its own byte. Single presses toggle SRC and OSC B and never open SETUP; a double press and FUNC+SRC open SETUP. The UNI push cycles B -> BOTH -> A -> B. UNI on A, B and BOTH moves the matching increments in the control record (BOTH: A down, B up), and the renders differ. The strip letter differs from FLEX's in a glyph-sized box. LFO PMTR draws CUBE's names | 26 PASS |
| `verify_static.py four …` | CUBE on T1-T4 and THRU on T5-T8 together: every stem sounds, four different pitches, and the sequencer tick runs | 4 PASS |
| `verify_static.py save …` | SAVE, change, RELOAD on a writable card brings back T1's and T3's CUBE bytes and T1's UNI target. FLEX restores FLEX's bytes. The bank file carries the signature | 6 PASS |
| `verify_static.py clock …` | T1 at defaults plays C4, and frames and ticks run | 2 PASS |

Screens and WAVs from the gate are written outside Git (`$CUBE_SHOTS`). They are renders of the
firmware's screen and are never committed.

Measured levels on the timing-dependent rows: the louder channel is within 0.05 dB of stock (the
control 0.02 dB). The quiet left channel of DELAY, PLATE, SPRING and DARK (tail only, rms 220-570)
is 0.11-0.68 dB above stock's, where the control is 0.04-0.24 dB. Both go the same way, and the
build boots later than stock through the loader, which points to timing in the tails. This is not
proven.

A per-track stem comparison was tried first and dropped. `ot_emu`'s track stems come before the
effects (on stock, a reverb changes T2's stem by at most 5 LSB), so matching them proves nothing
about the effects.

## Not tested

- Hardware: everything, in this build. CUBE1, a loader build of the same engine, was listened to
  on a unit.
- Parameter locks and LFO modulation of CUBE's parameters (only the PMTR names are checked).
- Pasting a CUBE track onto T5-T8 through the panel's copy/paste. The gate plants the signature
  directly.
- CUBE1 projects loaded into this build.
- External MIDI and clock beside CUBE, beyond the tick check.
