# Turing Machine

Version: 0.3.0-experimental (OCTABAM11U) · author: [pmsorhaindo](https://github.com/pmsorhaindo)

A ColdFire module for the native octabam build (`sdk/octabam`), built static-stock as upstream ships it
(no DSP loader). Not in the catalog yet and without the base/USB lifecycle. Build it from `sdk/octabam` with
`make image REMIX=turing` (selection in `remixes/turing/remix.py`). The design and the plan are in
[the feasibility study](../../../docs/turing-machine-feasibility.md) (fork PR #1).

## Overview

Looping shift registers play the Octatrack's MIDI tracks, in the style of the
[Music Thing Modular Turing Machine](https://www.musicthing.co.uk/Turing-Machine/). Each MIDI track can
run its own 64-bit register (OCTABAM10; 16 bits before).

When a track's Turing MODE is ON, its trigs no longer make notes and the register plays instead. On every
step of the track's sequencer it shifts once, whether or not the step has a trig. The bit at the loop point
(LEN, 2..64) comes back in at the bottom, flipped with a chance set by LOCK (a fresh random decision for
every bit as it comes round, as on the Turing Machine). The newest eight bits make the step: DENS decides
whether it is a note or a rest, and SCAL how wide the notes spread around the track's NOTE. A LEN of 2..7
(OCTABAM11) is a loop of LEN whole notes instead: the register's newest LEN bytes turn one byte a step, so
the notes and rests repeat every LEN steps (below). The step's
parameter locks still apply (below). When MODE is OFF the track is stock: its trigs play their notes. A
push of knob A (WRITE) copies the current Turing sequence into the track's own trigs.

The TURING page's settings (MODE, LOCK, LEN, SCAL, DENS) and the register itself belong to the **pattern**
(since OCTABAM9): each of the 256 patterns has its own for each MIDI track.

### LOCK (since OCTABAM10)

LOCK is the chance that the bit coming round at the loop point flips, a curve modelled on the Turing
Machine's knob: noon (64) random, clockwise from 3 o'clock (96..127) locked, and a "slip" zone around 9
o'clock (25) where the loop repeats but occasionally changes. In 65536ths (`tm_flip_chance`), with
slip = 65536 / max(LEN, 4) and loose = min(4 x slip, 24576):

| LOCK | flip chance per bit | flips per pass, LEN 16 | LEN 64 | LEN 8 |
|---|---|---|---|---|
| 0 | loose: 4/LEN (at most 3/8) | 4 | 4 | 3 |
| 0..25 | straight from loose down to slip | | | |
| 25 | slip: 1/LEN (at most 1/4) | 1 | 1 | 1 |
| 40 | slip + (1/2 - slip) x 15/39 | 3.69 | 12.9 | 2.15 |
| 25..64 | straight from slip up to 1/2 | | | |
| 64 | 1/2 (random) | 8 | 32 | 4 |
| 80 | (96 - LOCK)/64 = 1/4 | 4 | 16 | 2 |
| 64..96 | straight from 1/2 down to 0 | | | |
| 96..127 | 0: the loop repeats exactly | 0 | 0 | 0 |

The model in `verify.py` measures these within 6 % over 3,000 passes per cell. One flipped bit is read by
the next eight steps as it moves through the eight-bit note window (as the Turing Machine's DAC reads it),
so at LOCK 25 one bit a pass changes about 4.5 notes a pass on average (measured on the model, LEN 16),
mostly within one run of eight steps. A literal "one note a pass" would need a note stored per step (64
bytes per pattern and track), which the battery RAM cannot hold for 2048 cells.

FUNC held while turning LOCK snaps it: right to the next of 0, 64 and 127, left to the previous.

### LEN 2..7: a loop of notes (OCTABAM11)

Up to OCTABAM10 every LEN was a bit loop. Eight bits make a note, so a loop of 2..7 bits read bits from
outside itself for the first steps, and a 2-bit loop is 00 or 11 half of the time (a 3-bit one a quarter):
it then plays one note on every step and, as it shifts, fills the whole 64-bit register with that one value.
Every longer LEN afterwards played the same bottom (or top) note until LOCK below 96 flipped bits back in.
That is the hardware report of 26 Oct 2026 (LEN 2 not looping, a fresh pattern "all zeros").

Since OCTABAM11, LEN 2..7 keeps LEN whole notes: bytes 0..LEN-1 of the register turn a byte a step (byte
LEN-1 comes back as byte 0), and the top byte counts the place in the loop. A step's value is its byte with
a fixed per-place key inverted (`tm_keys`), so a loop whose bytes are alike (a shift register's history)
still plays LEN different values. The notes and rests repeat exactly every LEN steps at LOCK 96..127. LOCK
then changes a whole note as it comes round (its bits inverted by a random byte), with the same curve:
slip one note a pass, random every note at 64, loose two notes a pass at 0 (at most 5/8). The bytes between
the loop and the count are left alone, so a longer LEN finds them again. LEN 8..64 are unchanged.

### SCAL (pitch range, since OCTABAM10)

The width of the range, centred on NOTE (`tm_span`): note = NOTE + value x span / 255 - span / 2 for the
eight-bit value, folded by octaves into 0..127.

| SCAL | span | notes |
|---|---|---|
| 0 | 0 | NOTE only |
| 0..64 | (3 x SCAL + 4) / 8 | |
| 32 | 12 | NOTE-6..NOTE+6 |
| 64 (default) | 24 | NOTE-12..NOTE+12 (two octaves, OCTABAM9's range) |
| 64..127 | 24 + ((SCAL - 64) x 24 + 31) / 63 | |
| 96 | 36 | NOTE-18..NOTE+18 |
| 127 | 48 | NOTE-24..NOTE+24 (four octaves) |

It is called SCAL, not SCALE (the Octatrack's PATTERN SCALE is a speed) and not RNGE (the ARP page, one
double tap away on the same ring, already has a RNGE knob, in octaves of the arpeggio).

### DENS (density, since OCTABAM10)

Whether a step is a note or a rest (`tm_gate`): the newest eight bits read newest-first, g (0..255), against
2 x DENS: a note when g < 2 x DENS, every step at 127.

| DENS | steps that are notes |
|---|---|
| 0 | none (silence) |
| 32 | about a quarter |
| 64 (default) | about half: exactly the steps whose newest bit is 0, as a Turing Machine pulse output |
| 96 | about three quarters |
| 127 | every step (OCTABAM9's stream) |

The gate is a function of the register alone, so with LOCK locked the same steps rest on every pass, turning
DENS changes which steps play at once, and turning it back gives the old rhythm back. A rest sends no note;
if the step has a trig or lock trig (whose condition passes) it goes out as a trigless trig with its locks,
so its CC locks are still sent.

The registers have no clock of their own. They step with the track's own sequencer, so tempo (internal or
external MIDI clock), the pattern and track scale (speed), pattern length and swing stay the instrument's,
and the line starts and stops with PLAY and STOP. The cell of a pattern's track holds the register as it is
at the pattern's first step (the start of the pass): it is written there every pass. PLAY starts from it, so
a locked phrase always sits the same way on the pattern: a STOP and PLAY, a SAVE (while playing too), a
RELOAD and a power cycle all give the same phrase from the same step (OCTABAM11; before, the register was
saved wherever the loop was, and a reload came back rotated).

## Controls

### The TURING page (on the MIDI track)

On a MIDI track, AMP has three pages in a ring: **MIDI ARPEGGIATOR**, **MIDI ARP SETUP** and **MIDI
TURING**. A double tap of AMP shows the next page in the ring, and a double tap on the last page wraps to
the first. A single press of AMP always shows the first page. TURING FIRST (below) picks which page is
first:

| TURING FIRST | AMP | double tap | double tap | double tap |
|---|---|---|---|---|
| OFF (default) | ARP | ARP SETUP | TURING | ARP |
| ON | TURING | ARP | ARP SETUP | TURING |

FUNC + AMP opens MIDI ARP SETUP directly, as on stock. NO closes ARP SETUP onto ARP. The TURING page is
there on every MIDI track, and its knobs edit the active track:

| Knob | Name | Values | Default | What it does |
|---|---|---|---|---|
| A | MODE | OFF, ON | OFF | The track's Turing switch. ON: one register note on every step, and the track's trigs send nothing. OFF: the track is stock. |
| B | LOCK | 0..127 (dial) | 64 | The flip chance (table above). FUNC + turn snaps to 0, 64, 127. |
| C | LEN | 2..64 | 16 | The loop length, in steps (2..7: a loop of whole notes, above). Changing it keeps the register, so a shorter loop can grow back. |
| D | SCAL | 0..127 (dial) | 64 | The pitch range around NOTE (table above). |
| E | DENS | 0..127 (dial) | 64 | How many steps are notes (table above). |
| F | (off) | | | |
| push A | WRITE | | | With MODE ON: the current sequence into the track's trigs (below). |

- LOCK, LEN, SCAL and DENS move one per click, x7 with the knob pressed. MODE needs four clicks a step, like ARP's LEG.
- Selecting another track (T1..T8) keeps the page and shows that track's settings.
- A double tap is stock's: a second press of AMP within 15 ticks of the first, about a quarter of a second under the emulator. A tick is about 17 ms there; that is measured in the port and inferred for the unit. On ARP SETUP stock acts on AMP when it is released, so there the 15 ticks count from the release.
- A double tap's first press is a single press, so it shows the first page for a moment before the second press moves on. For example, with TURING FIRST OFF, a double tap on ARP SETUP shows ARP briefly, then TURING.
- The values are per pattern and track (the pattern playing, or selected while stopped), not per Part, and cannot be parameter-locked. Holding a trig while turning a knob changes the value.

### WRITE (push knob A, since OCTABAM10)

Push and release knob A on the TURING page while MODE is ON: the popup MIDI TRACK WRITTEN shows (the stock
popup COPY MIDI TRACK uses, `0x4005a2b8`) and the Turing machine's current sequence is written into the
MIDI track's own sequence in the current pattern, so MODE OFF afterwards plays the same notes and rests (on
a locked loop). MODE stays ON and the register is not moved. With MODE OFF a push does nothing; turning A
while it is pushed is not a WRITE (that is stock's x7).

- Over the pattern's length (the track's length with per-track scales), the register is clocked on a copy as a locked loop (no flips), starting with the step the track plays next (step 1 while stopped). A LEN shorter than the pattern repeats to fill it; a LEN that does not divide the pattern length gives the pattern's first pass (ON goes on looping LEN, OFF repeats the pattern).
- A note step gets a note trig whose NOTE lock is the register's note before the ARP, the LFO and TRAN (stock processes it the same way as the Turing note). NOT2..NOT4 are locked to the NOTE itself (one note, as ON). Its **trig condition, microtiming and retrig count are cleared** (ON ignores them); its other locks (VEL, LEN, CCs, ...) are kept.
- A rest step gets no note trig; a trig there that carries other locks becomes a trigless trig with them (as ON sends them on a rest), otherwise the step is cleared.
- Bytes 30-31 of a written step's lock record (never read by stock, 0xff in a stock pattern) mark the NOTE lock as WRITE's and keep the centre it was computed from, so MODE ON goes on playing the same notes after a WRITE instead of re-centring on the written note. A NOTE lock you change afterwards by hand is still read through that mark (the centre stays the written one) until the step is written again or its locks cleared.
- Steps past the pattern length are not touched. The bank data is edited in place: save the project (or the bank) as usual to keep it.
- The written trigs blink on the trig keys in GRID REC. That is stock: the Octatrack flashes every trig that carries a parameter lock, and a hand-placed trig with a NOTE lock blinks the same way. They are ordinary note trigs and can be edited, moved and cleared like any other. Kept as it is since the hardware test (brief 9; OCTABAM11's trigs are byte-identical to OCTABAM10's).

Verified under the port: MODE OFF after a WRITE gives the same MIDI OUT messages as ON and every note at
the same time (TESTING.md).

### PROJECT > CONTROL > MIDI SEQUENCER

One row under CC DIRECT CONNECT:

| Row | Values | Default | What it does |
|---|---|---|---|
| TURING FIRST | OFF, ON | OFF | ON makes TURING the first of AMP's pages on every MIDI track. Project-wide. |

RIGHT and LEFT or LEVEL change it. It and the TURING page's values are saved with the project (below) and
kept in battery-backed RAM in between, so a power cycle keeps them.

### Saved with the project

SAVE and SYNC TO CARD write one line per pattern's track that is not at the defaults into `project.work`,
after `PATTERN_CHANGE_AUTO_SILENCE_TRACKS`, and one more when TURING FIRST is ON:

```
#TURING_B1_P1_T1=1,127,64,100,30,4660,22136,48879,1
#TURING_FIRST=1
```

That is bank (1-16), pattern (1-16), track, MODE (0/1), LOCK, LEN, SCAL, DENS and, once the register has
played, the 64-bit register as four 16-bit numbers, oldest first: the register of the pass's first step
(above). So a RELOAD plays the same locked phrase from the same step. OCTABAM9's lines (`=mode,lock,len[,bits,rng hi,rng lo]`) still load, with SCAL
64 and DENS 127 so they sound as they did (their 16-bit register kept; the random state is no longer part
of a pattern: each track has one, in battery RAM at `0x100ffe40`). Loading a project, RELOAD and CHANGE included, starts from every pattern OFF and
TURING FIRST OFF, then applies its lines, so a project without them plays stock. A new project starts OFF.
OCTABAM6-8's per-track line `#TURING_T1=1,127,8` still loads, into every pattern of that track (not tested
under the port). The stock loader skips lines that start with `#`, so a project saved with the module loads
on stock firmware or without the module, with its MIDI tracks playing their own notes.

Where it lives: the live copy is a table in battery-backed RAM that stock never references,
`0x100f9000..0x100ff000` (12 bytes per pattern and track, 24 KB: MODE+LOCK, LEN+seeded, SCAL, DENS and
the 64-bit register), so a power cycle keeps every pattern's settings and register. OCTABAM9's cells (the
same 12 bytes, laid out differently) are converted once on the first boot of OCTABAM10, keeping MODE, LOCK,
LEN and the register, with SCAL 64 and DENS 127 (a settings-record flag, `TM_FLAG_CELLS10`, marks it done). A zeroed entry is the defaults. The project lines are the copy that SAVE/RELOAD
carry; nothing goes into the bank or pattern files. Copying, clearing or pasting a pattern does not copy or
clear its Turing settings.

## Usage

With MODE ON a MIDI track needs no trigs. It plays a note or a rest on every step (DENS):

- **Pitch:** NOTE plus the register's value spread over SCAL's range (NOTE−12 … NOTE+12 at the default 64), then as any trig's note: the LFO on NOTE, TRAN, the arpeggiator and its KEY. NOTE is the step's NOTE lock if it has one, else the Part's NOTE. A note that would leave 0..127 moves an octave in.
- **Velocity and length:** the track's VEL and LEN, or the step's VEL/LEN locks. A new note releases the one before it, as on stock (so a LEN longer than a step is cut by the next step, as on a stock track with a trig on every step). A VEL lock of 0 (OFF) sends no note on that step.
- **Channel:** the track's own (SRC SETUP).
- **Timing:** every step of the track's sequencer: tempo (internal or external MIDI clock), the pattern scale (per-track scale too), the pattern length and swing. Nothing plays while stopped.
- **Mute:** a muted track sends nothing (no notes, no CCs, as stock). The register keeps clocking every step while muted, so unmuting comes back in on the note of that step and loops stay aligned with the bar.
- **STOP:** releases the sounding note, as stock does.

Locks: on any step where the stock sequencer would apply locks (a trig or a lock trig whose condition
passes), they apply to the Turing note of that step: VEL, LEN, NOTE (the centre, above), CC/PB/AT and every
other lock, exactly as stock applies them to a trig, and the next step goes back to the track's values. CC
locks go out on their step even when no note does (VEL 0). Trig conditions are still evaluated, but only
decide whether the step's locks apply; the Turing note plays every step. Microtiming and retrigs of a trig
are not used: the Turing note sits on the grid plus swing. NOT2 to NOT4 are not sent, so each step is one
note (the arpeggiator gets that one note). The trigs stay in the pattern. Set MODE to OFF and they play
again, from the next step.

NEI: with MODE ON the track's condition result follows its Turing steps: true on a note step, false on a
rest (since OCTABAM10), so NEI on the next track plays with T1's notes and NOT NEI on its rests. With MODE
OFF, NEI follows the track's trigs as stock.

Patterns: when the sequencer moves to another pattern, the track follows that pattern's MODE, LOCK and LEN
and its register. Coming back to a pattern starts from its register at the pass's first step (clocked on to
the step it comes in at, as a locked loop), so a LOCK 127 phrase comes back identical and in place. Part changes have no effect on Turing.

Switching MODE takes effect from the next step while playing, and from the first step of the next PLAY
while stopped. MODE ON while playing picks the loop up where the pattern is (the pass's register clocked on
to that step), so a locked phrase switched OFF (the written trigs) and ON again stays in place.

### The first phrase after a boot

Each pattern's register is seeded at its first step (the first step after PLAY, or the first step of the
pattern) with 64 random bits, like a Turing Machine powering up, from a seed taken once per boot, mixed
with the track and the pattern (checked: over 2,000 seeds the first notes average NOTE); a seeded register is kept
in battery RAM and in the project, so it is not seeded again. The seed is read from a free-running hardware counter (DMA timer 3, which stock runs at the bus
clock), so the first phrase depends on the moment PLAY was hit. Later PLAYs keep the registers.

For tests, a fixed seed can be written to battery RAM through the emulator: a 12-byte record at
`0x100ffe20`, `"TSEE"` then the seed and its complement (`turing.h`). While it is valid every boot uses that
seed; a cold initialise clears it.

### Quick tutorial

1. Press MIDI and select T1. Hold FUNC and press SRC, set CHAN to your synth's channel and press YES. No trigs are needed.
2. Press AMP (MIDI ARPEGGIATOR), double-tap AMP (MIDI ARP SETUP) and double-tap it again: MIDI TURING. Turn knob A to the right so MODE reads ON and press PLAY: T1 plays a 16th-note line within an octave either side of its NOTE (C3), C2 to C4.
3. The default DENS 64 rests on about half the steps; turn knob E (DENS) to 127 for a note every step. Hold FUNC and turn knob B (LOCK) right to snap it to 127: the last 16 steps repeat. Turn knob C (LEN) for a shorter or longer loop (up to 64), D (SCAL) for a narrower or wider range, LOCK back to 25 to let the phrase slip, or to 64 for random.
4. Like the loop? Push knob A: MIDI TRACK WRITTEN. Turn MODE OFF and the track's own trigs play the same phrase; edit them as any trigs.
5. FUNC+PAGE changes the speed (PATTERN SCALE) and the line follows it. To reach TURING with one press, set PROJECT > CONTROL > MIDI SEQUENCER > TURING FIRST to ON.

## Compatibility and limitations

Octatrack MKI or MKII on OS 1.40C. No declared conflicts. A native build beside Scale Quantizer, Euclid and
CC Map was accepted by the ledger (before the page ring; not rebuilt since). The row grows the MIDI
SEQUENCER page's own tables, not the SEQUENCER page Scale Quantizer grows.

What changes in stock flows: the MIDI SEQUENCER page shows one more row. On a MIDI track a double tap
of AMP steps ARP -> ARP SETUP -> TURING instead of only opening ARP SETUP, and a single AMP press on ARP
SETUP closes it onto the first page as stock does (TURING with TURING FIRST ON). With every MODE OFF
the sequencer runs its stock evaluation of every step; MIDI OUT matched stock 1.40C byte for byte on the
wire in the emulator (OCTABAM8 and OCTABAM9, 25 Oct 2026).

Limitations:

- Chromatic notes unless the arpeggiator's KEY quantizes them. Scale stages are planned (study, section 2.3).
- A rest step with a trig that carries locks still fires (as a trigless trig): a note held longer than a step is not cut by a rest without a trig, as on stock.
- LOCK 25 flips one bit a pass, which changes several neighbouring notes (about 4.5 a pass at LEN 16, as measured on the hardware too; above). At LEN 2..7 it changes one note a pass.
- Microtiming and retrigs on a Turing track's trigs are ignored.
- The register clocks when a step is scheduled (about a step ahead); STOP drops the playing register and the next PLAY starts from the cell's (the pass's first step). The track's random state is not taken back: a step scheduled and never played has drawn from it (only LOCK below 96 notices: which bits flip). A pattern change by any path other than the sequencer's (e.g. a direct jump) was not tested.
- Playmodes hooks the MIDI step mapping just before the evaluator (`0x400a39b6`); the two share no site, but they were not built together.
- Settings are per pattern, not per Part; copying a pattern does not copy them.
- The boot seed relies on DMA timer 3 counting on the unit as stock programs it (mode `0x000b`, reference `0xffffffff`). That is inferred from stock's register setup and measured in the emulator, not on hardware.
- MIDI Scenes builds only on its own, so the two cannot be combined.
- Not tested: incoming MIDI notes, live recording, Part changes while playing, per-track scale mode, LFOs other than LFO 1 on NOTE, the OCTABAM8 project-line upgrade, timing under load, hardware.

## Tests and measurements

`verify.py` (`modules/turing-machine/verify.py` once copied into octabam) runs under the ColdFire port and
reads MIDI OUT. Since OCTABAM9 it also checks locks (VEL, LEN, NOTE, CC, a lock trig, VEL 0, mute), NEI,
the note range, the arpeggiator and its KEY against a stock track playing the same notes, the LFO on NOTE
against a stock track, external MIDI clock at 1x, 2x and 1/2x, and pattern switching. With the fixed test seed, an empty T1 in REPLACE mode is checked against a stock T2 with a
trig on every step (one note on each of its steps at 1x, 2x and 1/2x), every note against a model of the
engine, trigs placed later, mute, MODE switched while playing and while stopped, and STOP's note-offs.
Without the seed, two boots with PLAY at different moments must start different phrases. A fourth boot
saves and reloads a project on a writable card, a fifth drives AMP's ring of pages and the TURING page's
knobs, and the last two run one panel script on stock 1.40C and on the image: with MODE OFF the MIDI
messages must be identical, and with T1 ON the clock, START and STOP must match stock's. Since OCTABAM11 it
also checks the loop period on the wire for LEN 2..64, LEN turned live on the panel, fresh registers, WRITE's
trigs against OCTABAM10's, MODE switched live (timing), and SAVE -> RELOAD / reboot giving the same phrase
from the same step. See
[TESTING.md](TESTING.md). Cycles, memory totals and hardware behaviour are not measured.

## Implementation

REPLACE mode works by changing what the stock sequencer schedules, so every note still goes through the
stock note path (length, note-off, STOP, mute, channel and TRAN stay stock's):

- **`0x4009cf4c`, the MIDI per-step trig evaluator** `(track, bank, pattern, step, slot)`. The step scheduler (`0x400a39c6`) calls it once per step of every MIDI track, trig or not. Stock runs the step's trig condition (`0x400a5164`, which also records the result NEI reads) and its trig bitmaps; for a trig or a lock trig it writes the event (29 for a note trig), its repeat count and interval, its microtiming plus swing and a 32-byte lock record; with no trig it writes nothing. On a track whose MODE is ON in that pattern, `tm_eval` runs the stock evaluator first and clocks the pattern's register. A note step (DENS) becomes a note trig (event 29, one note, the step's swing, no microtiming) that keeps stock's lock record if stock wrote one (else no locks), with the register's note as the record's NOTE lock (centred on the step's own NOTE lock, WRITE's recorded centre, or the Part's NOTE). A rest becomes nothing (event 0), or, when stock scheduled the step, a trigless trig (event 25) with stock's locks and timing. The track's condition result is true on a note and false on a rest. The tick ISR (`0x400a1e0c`) applies the record as it does any trig's, so VEL/LEN/CC locks, the LFO, TRAN, the arpeggiator and its KEY all act on the Turing note in stock code. Byte 30 of the record (never read by stock: the ISR applies bytes 0..29) carries a tag and byte 31 the step.
- **`0x4009fa2a`, in the MIDI note routine** `0x4009f794`, where a fired step's chord (NOTE, NOT2..NOT4) is built and about to enter the arpeggiator (`0x40099c08`), before the mute and VEL checks. For a tagged record (the ISR copied it to `0x46c7a000 + 32·track` just before) `tm_fired` recognises a Turing step and NOT2..NOT4 are dropped. The register a track plays is in DRAM (`tm_live`: the register, its cell and the step that follows on); a step that does not follow on (PLAY, MODE switched ON, a pattern change, a load) starts from the cell's register clocked to the step as a locked loop, and the pattern's first step writes the register to the cell (`tm_position`). STOP, a load and a new project drop it.
- **The first step after PLAY** is evaluated earlier, at STOP or a load (slot -1, from `0x4009e3fe`), and PLAY copies the result (`0x4009c0bc`, `0x4009c268`). For it `tm_eval` runs the stock evaluator and keeps its result. **`0x4009c076`**, at PLAY before the copy, gives a track whose MODE is ON in that pattern the Turing step (the register clocks at PLAY, not at STOP), and leaves stock's otherwise.

With MODE OFF the evaluator, the first step and the note routine are stock. OCTABAM8's chord-loop hook at
`0x4009fb2e` is gone.

`turing.c` is the engine, the TURING page and the row's getter and setter; `generate.py` compiles it to the checked-in
`turing.s`, appends `hooks.s` and refuses an instruction that both auto-modifies and addresses through one
register (GCC produced one; it wrote every byte one address high). The unit is linked into the platform
runtime in DRAM. The row label is in `hooks.s`'s `.text`: the stock label table points straight
at it, and the browser builder and native octabam place a DRAM unit's `.rodata` differently. TURING FIRST lives in a 32-byte checksummed record at `0x100ffe00` in battery RAM that
stock never references (an invalid record reads as OFF); its OCTABAM8 per-track fields are kept but unused.
The per-pattern table is at `0x100f9000` (above).

The project file uses four more detours, each beside one of Scale Quantizer's rather than on it, so the
two build together without sharing a site: the loader after its frame is set up (`0x400866ee`, reset on
the storing pass), the loader's next-line point (`0x40088224`, which every complete line reaches,
quantizer's included), the serializer one block after quantizer's (`0x400888d2`) and the project defaults
(`0x40025ad4`).

## Authorship and licences

Module source by [pmsorhaindo](https://github.com/pmsorhaindo) under the [MIT licence](LICENSE), built with
octabam by Sam Banks. The idea follows Tom Whitwell's Music Thing Modular Turing Machine; no code from it is
used. No Elektron firmware, extracted routines or tables are included. The thumbnail is an original
illustration.

### The TURING page

The ARP page's descriptor is copied out of the running image into the unit's DRAM on first use (none of its
bytes are in the repository). The copy keeps ARP's storage fields and changes only these: the title (footer
`MIDI TURING`), the six names, formatters and widgets, and the enable nibbles (D, E and F off).

Five detours:
- **`0x400322f0`**: the stock handler of a page key pressed on its own page. On a MIDI track a press of AMP shows the first page and a double tap (stock's `arg 3`) the page after the one the first press left. When the next page is ARP SETUP, stock opens it. Over MIDI ARP SETUP, stock closes the window, the first page shows under it, and the key is noted again in `0x400c0aac` (stock clears it while a window shows), so a quick second press is a double tap.
- **`0x400554e0`**: set page, given the caller's return address. AMP arriving from another page, or the MIDI/audio toggle, shows the first page. The call from MIDI ARP SETUP's opener (`0x40079c90`) puts ARP under the window. A track change keeps the page.
- **`0x40031dea`**: the page resolver's MIDI ARP load. It returns the copy while the page shows, for the current track only.
- **`0x4004ecfc`** (since OCTABAM10): the stock encoder-push handler `(code, down)`, at its entry. Knob A (code `0x38`) pressed on the TURING page with MODE ON and FUNC up arms WRITE; its release writes and calls the popup. Stock then runs as for any push.
- **`0x4005502a`**: in the knob routine, after it resolves. The page's knobs go to the current pattern's entry for the track (`0x800065bd`/`0x800065be`, the playing bank and pattern), and the routine returns before it would store, send or mark an ARP byte.

The widgets call the stock text widget (`0x400467a4`) and dial (`0x400479b4`) with the Turing value in place
of the ARP byte the renderer read.

## Screens and audio

The TURING page: on a MIDI track, AMP and then two double taps (or one press with TURING FIRST ON; PROJ >
CONTROL > MIDI SEQUENCER > TURING FIRST). Knobs A..E are MODE, LOCK, LEN, SCAL and DENS for the active MIDI
track; a push of knob A with MODE ON is WRITE. Emulator LCD captures are kept outside Git (they are renders
of the firmware's screen); [media/capture.json](media/capture.json) records how they are made. No audio preview.
