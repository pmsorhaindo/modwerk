# CUBE

A wavetable source machine for Octatrack audio tracks 1-4. It has two oscillators over an original
8 x 8 x 8 cube of single cycles (made by `generate_cube.py`, with no third-party wavetables), X/Y/Z
morphing, thru-zero FM from B into A, unison, TONE quantisation, and trig and hard sync.

Build: `make image REMIX=cube` (`sdk/octabam/remixes/cube/remix.py`). The image is static-stock
(`OCTABAM_STATIC_STOCK=1`, upstream's default) and has no DSP loader. Every stock effect is kept on
both FX choosers of every track, SPRING REV included.

## Where it is

- **Tracks 1-4.** Pick CUBE in the machine list (FUNC+SRC, or the main chooser). It is the sixth
  row, after PICKUP. On tracks 5-8 the lists keep stock's five rows.
- **SRC page:** `PTCH FM MIX` / `X Y Z`.
- **Press SRC again (OSC B):** `BPCH LAW LINK` / `BX BY BZ`. A further press goes back to SRC.
- **Double press SRC, or FUNC+SRC (SETUP):** `FINE OCT UNI` / `TONE MORPH SYNC`. This page is
  never in the single-press cycle.
- **UNI target:** in SETUP, push the UNI encoder (C) without turning it. Each push cycles the
  target A -> B -> BOTH, and the UNI label shows it. BOTH detunes A down and B up by the UNI
  amount. A new CUBE track starts on B.
- **The track letter** is `c`. FLEX's is `F`.
- **LFO SETUP PMTR** names CUBE's own SRC parameters on a CUBE track.

The SRC parameters sit in FLEX's playback slots, so LFOs and parameter locks reach them as they
reach FLEX's (the LFO PMTR names are checked in the emulator; locks are not tested). The values
live in the track's FLEX and NEIGHBOR Part bytes, with the signature `CU\x01` in NEIGHBOR's unused playback bytes, so a
project saves and reloads as stock does.

## How it fits the stock OS

- **DSP.** The voice (`cube_voice.asm`: the seam stub `cube_seam.asm`, then the engine
  `cube_engine.asm`, 459 words) is one extra P record above core 1's stock code: payload B,
  P:0x1d9f..0x1f6a, out of 609 free words (`DspSection(free_top=True)`,
  `docs/remixer/PLACEMENT.md`). It boots with the payload as a pre-boot upload of octabam's
  loader, which is Analog BD's route. Payload A is byte-identical to stock. Payload B differs only
  in the two-word `jsr` at the track source seam P:0x1a2, which leaves every non-CUBE track's
  source as stock.
- **Why tracks 1-4.** Core 1 runs tracks 1-4. Core 0 (tracks 5-8) has 33 free words, and a static
  build could only make room there by taking a stock effect's code. Four CUBE voices are charged
  616 cycles/sample against core 1's 829 remainder (`verify.py dsp`, step 4a).
- **ColdFire.** These are DRAM units (`machine.s`, `cube.c`): the chooser and Part seams Analog BD
  measured, the SRC page select, the knob routine, the track strip letter and the LFO PMTR name.
  `cube_rows` gives six machine rows on T1-T4 and five on T5-T8.

## Compatibility

- **Not with Analog BD.** Both use machine row 5, the track source seam and payload B's upload.
  The build refuses the pair.
- **Not with another free-top section on payload B.** The build refuses it.
- **Saved work.** A Part from the CUBE1 test build with CUBE on tracks 5-8 loads with those tracks
  as FLEX at FLEX's defaults, and their CUBE settings are dropped. The same happens to a CUBE track
  pasted onto tracks 5-8. Tracks 1-4 keep their CUBE settings.

## Changes to stock flows

- The machine lists of tracks 1-4 have a sixth row (CUBE). Tracks 5-8 are unchanged.
- On a CUBE track only, these work differently: a single SRC press toggles SRC and OSC B, a double
  press opens SETUP, a push of SETUP's UNI encoder cycles UNI's target, and a double tap of the
  track key opens no sample pool (CUBE has none). The code paths are keyed on the CUBE signature,
  so FLEX tracks keep stock's behaviour (CUBE1's gate checked the double tap; this build's gate
  does not).

## Proof level

`PORT`: emulator only (`verify.py dsp`, `verify_static.py`). This build has not run on hardware.
CUBE1, a loader build of the same engine, was listened to on a unit. See `TESTING.md`.
