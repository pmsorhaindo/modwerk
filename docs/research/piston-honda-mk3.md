# Cube oscillator: a Piston Honda Mk3-style machine for the Octatrack

Status: design only, 23 October 2026. Dynload addendum the same day. OSC B
page added 24 October 2026.
No firmware, no DSP image, and no module is added here. This note is the
behaviour target and the fitting plan for a new Octatrack **track machine**
in this fork (`pmsorhaindo/modwerk`).

CUBE is one machine among the others. Any one track can run it, or several,
or all eight. Every track that does not stays a stock machine (FLEX, STATIC,
THRU, NEIGHBOR, PICKUP) or another contributed machine whose price fits that
core. The goal is not an instrument that only plays this oscillator.

The behaviour target is the Industrial Music Electronics Piston Honda Mark III
(model 1991, firmware manual v1.1): a dual wavetable oscillator with an
8×8×8 waveform cube. The shipping module must be an original instrument.
It must not carry IME’s factory wavetables, panel artwork, firmware, or the
product name in the chooser. Working name below: **CUBE**. Ideas and the
published file layout are usable; the named factory banks are not (see
[What not to copy](#what-not-to-copy)).

Confidence is marked on each claim:

- **Documented** — stated in a public manual, datasheet, or this repository.
- **Reported** — a public user report, not a measurement made here.
- **Inferred** — follows from those sources, not directly stated.
- **Uncertain** — the sources disagree or say nothing. Do not treat it as
  specified.

Nothing in this note was heard on a Piston Honda or measured on an Octatrack
during this study.

## 1. How the Piston Honda Mk3 works

### What it is

**Documented.** The v1.1 operations manual describes a dual wavetable
oscillator: two independent oscillators, a mix output, three-axis morphing,
thru-zero FM, an external-input waveshaper mode, unison, and eight presets.
Panel jacks are labelled 1V/oct (0–8 V), bipolar CV (±8 V, some drawings say
±10 V in the text), FM/ext (AC, 10 V peak-to-peak), and sync (0–5 V).

Sources:

- Operations manual, firmware v1.1 (IME PDF):
  <https://ime-assets.s3.amazonaws.com/uploads/manual/manual/24/phmk3manual11.pdf>
  Mirror:
  <https://www.analoguehaven.com/the-harvestman/model-1991-mark-iii/manual.pdf>
- Product page linked from that manual:
  <http://www.industrialmusicelectronics.com/products/21>
- ModularGrid module page (file layout and factory bank credits):
  <https://modulargrid.net/e/industrial-music-electronics-piston-honda-mk-iii>

The manual’s OCR is damaged in a few paragraphs (the FM-normal paragraph and
parts of the preset menu). Those gaps are called out below rather than filled
in.

### The 3D wavetable

**Documented.** 512 single-cycle waveforms sit in a cube of 8×8×8. Axes are
X, Y, and Z. Each axis has a slider and a CV input with an attenuverter that
adds to or subtracts from the slider. Both oscillators share the sliders and
the CV jacks; each oscillator stores its own position. A SELECT button
chooses which oscillator receives the next slider move. The controls lock
after a select or a preset load until the slider actually moves, so the
other oscillator’s position stays put.

**Documented.** One Z step is one file. ModularGrid states the indexing
inside the file: eight waves in a row are one X line, and eight such lines
are the Y positions. So:

| Axis | What one step selects | Span |
|---|---|---|
| X | the next waveform inside a group of eight | 8 |
| Y | the next group of eight inside the file | 8 |
| Z | the next file | 8 |

Index of a frame, **inferred** from that description:

```
frame = Z * 64 + Y * 8 + X     with X, Y, Z in 0..7
```

A missing colon after an axis label on the OLED means morph is off for that
axis on the oscillator being shown.

**Documented.** Morph can be disabled per axis, per oscillator. Enabled, the
manual says the slider mixes neighbouring waveforms (“a mix of two Z axis
waveforms”). Disabled, it “makes hard transitions between the eight
waveforms” and “allows you to hear a selection with no content from the
neighbor waveforms mixed in.” That is a time-domain crossfade, not a
spectral morph. The manual does not say linear versus higher-order.
**Inferred:** trilinear (or three successive linear mixes) across the
2×2×2 cell when all three axes are enabled, and nearest-of-eight on any
axis whose morph is off. **Uncertain:** cubic or Hermite morph. Do not
assume it.

**Uncertain:** interpolation *inside* one 256-sample cycle (drop-sample,
linear, or cubic). The manual never says. Linear is the recommendation in
[section 4](#4-efficient-high-fidelity-implementation) because it is the
usual cost of a short table and it does not invent band-limiting the
hardware does not claim.

### Memory layout and bit depth

**Documented** (manual, “File format description”, and the same figures on
ModularGrid and
<https://wavestack.app/instruments/piston-honda-mk-iii/>):

| Item | Value |
|---|---|
| File | mono WAV, 16-bit, 32,768 bytes |
| Cycle | 256 samples, 2 bytes each |
| Cycles per file | 64 (one Z position: 8 X by 8 Y) |
| Files per cube | 8, named `1.wav` … `8.wav` in the root of a FAT microSD card |
| Cube | 512 × 256 × 2 = **262,144 bytes** (256 KiB) of PCM |

All eight files load together (“Load Waves from SD” on the second page of
Global options). A bad name or a missing file fails the load. Success writes
the cube to the module’s memory and restarts. The card can then come out.
The manual points at Synthesis Technology’s WaveEdit as a tool that already
writes this layout (64 slots of 256 samples). Any other generator is fine
if the samples sit on 256-sample boundaries.

**Documented.** “Orthodox” tone “presents the full resolution of the 16 bit
waveform set.” The other tone settings “introduce different flavors of
quantization noise, enjoyable by enthusiasts of previous generations.” The
v1.1 text extracted for this study does not name those other settings or
their bit depths. **Uncertain:** how many tone modes, what they are called,
and whether they quantize the table, the oscillator output, or both. The
manual does say the effect is easiest to hear on a sine, low in pitch, as
“quiet foldover of high frequency aliases of the distortion products.”

### What not to copy

The cube geometry, the 256-sample 16-bit file layout, and the oscillator
behaviour above are published techniques. The factory cycles are credited
work. Do not vendor them, a recording of them, or the panel artwork. Do not
label the chooser with the product name. Author new cycles in the same
layout instead.

Factory set, **documented** on ModularGrid, not to be copied:

| Z | Bank | Credit |
|---|---|---|
| 1 | Classic Waveforms 1 | traditional |
| 2 | Lucifer Additive | Scott Jaeger |
| 3 | Classic Waveforms 2 | traditional |
| 4 | LFSR Vectors | Scott Jaeger |
| 5 | (bank) | Radek Rudnicki |
| 6 | (bank) | Joey Blush |
| 7 | (bank) | Rodent |
| 8 | (bank) | Surachai Sutthisasanakul |

### Oscillator, tracking, FM, sync, modes

**Documented.** With coarse at minimum, fine at centre, and no CV, the
frequency is **16.35 Hz (C0)**. Pitch is coarse + fine + 1V/oct + the
bipolar CV (through a nonlinear attenuverter) + an octave shift of ±2
octaves + the preset, if preset scope is “all params”. The oscillator
“will become silent if you exceed the minimum range of about 14 Hz.”
Rear trimmers (`OSC1SCALE`, `OSC2SCALE`) calibrate 1 V and 7 V to C1 and
C7. That is an analog front end. An equal-tempered digital tracker will
be cleaner than an uncalibrated unit. That difference is accepted.

**Documented.** The FM jack is audio-rate **thru-zero** FM. It is normalled
to the other oscillator’s output (the manual’s sentence is garbled at this
point; the panel and the external-input section agree that an unpatched FM
jack hears the other oscillator). Thru-zero means the phase increment may
go negative and the cycle plays backwards. **Uncertain:** the FM index law
(linear in the audio voltage, through what gain).

**Documented.** LINK makes oscillator B follow A’s frequency. B’s coarse
knob is ignored. B still adds its own fine tune and CV. A’s FM does **not**
pass into the frequency B follows. Fine at centre is unison at the mix
output. Each oscillator can also enable its own unison voice (a second
oscillator at a small detune, or at +1 / −1 octave). The manual’s shortcut
sentences disagree with each other: one says hold the encoder and press
SELECT, another says press the oscillator’s MODE button. **Uncertain**
which shortcut a given firmware actually uses. The parameter itself is
clear.

**Documented.** MODE switches that oscillator from the internal phase
accumulator to external-input waveshaping. The FM jack becomes the audio
to be shaped, the large tune knob becomes gain, and the pitch CV becomes
gain CV. The classic patch in the manual is a sine into the table, with an
envelope on the gain. Putting both oscillators in this mode while both FM
jacks are unpatched “will result in an unpleasant feedback signal.”
**Inferred** transfer: the input sample, scaled by gain, indexes the
currently morphed cycle. **Uncertain:** whether the index wraps, folds, or
clips, and whether the table is read as a transfer function (one sample
out per sample in) or as a windowed oscillator reset.

**Sync. Documented** only as a 0–5 V jack on the panel. The v1.1 body text
extracted here does not define the mode. **Reported:** players describe it
as hard sync, not soft sync
(<https://modwiggler.com/forum/viewtopic.php?t=245109>). **Reported,** and
not to be copied: on firmware 1.81 and 1.85 the jack has been described as
buggy — positive voltage mutes, a falling edge resets — rather than as
ordinary hard sync
(<https://www.modwiggler.com/forum/viewtopic.php?start=1320&t=195254>,
<https://www.reddit.com/r/modular/comments/1r16m21/piston_honda_mk3_sync_issue/>,
pointing at an earlier note
<https://www.modwiggler.com/forum/viewtopic.php?p=3624532>). **Uncertain:**
what a current unit with working firmware actually does. The Octatrack
mapping in section 3 uses the sequencer trig as the reliable reset, and
treats audio-rate hard sync as a later, explicitly approximate milestone.

**Documented** and out of scope for the machine: eight presets in onboard
EEPROM (not on the card), preset morph, preset CV modes (offset, attenuate,
trig-advance, trig-random), OLED screensaver at ten minutes, startup preset
restore, soft reboot, and Pickit3 firmware update. The Pickit3 requirement
**implies** a Microchip PIC as the control processor. **Uncertain:** the
PIC part, the audio DAC or codec, the converter’s sample rate, and any
analog reconstruction filter. No public teardown with part numbers was
found for this study. Do not invent a DAC model.

### Character, and what fidelity actually means

The Mk3 is not a band-limited modern wavetable. The traits that define it,
in the order they are worth spending cycles on:

1. **Short cycles.** 256 samples, no mipmaps in the file format. Harmonics
   above the 128th alias as soon as the fundamental rises.
   **Inferred** threshold at a 44.1 kHz player: aliasing starts once the
   fundamental exceeds `44100 / (2 × 256)` ≈ **86 Hz**. A C3 already
   aliases. That rising alias is the sound. Removing it with mipmaps,
   BLEP, or default oversampling would miss the instrument.
2. **Morph versus step.** Smooth neighbour mixes on X (adjacent cycles),
   wider jumps on Y (groups of eight), and file-to-file jumps on Z.
   Turning morph off per axis is the glitch. Both must exist.
3. **16-bit Orthodox, plus optional crunch.** Full 16-bit is the clean
   voice. Quantization is a tone option, not the default, and the exact
   factory curves are **uncertain**. An original 12-bit and 8-bit output
   mask is an honest stand-in; it is not a claim of matching unnamed menu
   items.
4. **Thru-zero FM from the other oscillator**, and a mix of the two.
5. **Unison**, small detune or ±1 octave, sharing the table position.
6. **Low end.** Useful down to C0 (16.35 Hz), silent near 14 Hz. The
   manual specifically points at low notes when judging tone and alias
   foldover.
7. **Waveshaper mode** (external audio indexes the cycle). Real, and
   secondary to the oscillator. It needs a track input the Octatrack
   already has (neighbour or thru). Not in the first slice.

What does **not** need to be reproduced: slider-lock feel, attenuverter
curves, OLED, presets (Parts, scenes, and p-locks already do this job),
analog 1V/oct scale error, the screensaver, and the reported sync mute bug.

**Sample-rate caveat. Uncertain** what clock the module’s audio path runs
at. This machine plays at the Octatrack’s **44.1 kHz** (the rate the DSP
sources in this repo are written for). The pitch where aliasing becomes
obvious will not match a module that scans the same 256-point tables at
another rate. That is a limit of the port, not a defect to oversample away.

## 2. How a new machine fits in this fork

### Two processors

**Documented** in `sdk/octabam/docs/remixer/TOOLING.md`: audio runs on a
Freescale **DSP56721**, two DSP56300-family cores, 24-bit fixed point, 200
MHz, three memory spaces each (P program, X data, Y data). The ColdFire
runs the OS, the panel, and the sequencer. They are different instruction
sets. NXP’s public figures match the chip the repo names:

- Fact sheet: <https://www.nxp.com/docs/en/fact-sheet/DSP56720FS.pdf>
- Migration note AN3653 (default RAM map):
  <https://www.nxp.com/docs/en/application-note/AN3653.pdf>
- Reference manual (shared RAM at `$030000`):
  <https://www.nxp.com/docs/en/reference-manual/DSP56720RM.pdf>

**Documented** (AN3653, default `OMR:MS = 0`): each core has 8K words of P,
36K of X, and 48K of Y, plus 64K words of shared RAM in eight 8K blocks
from `$030000`. Shared RAM is zero-wait as X or Y and one-wait as P. The
Octatrack’s stock payloads already occupy these maps. Datasheet capacity
is not free memory. `sdk/octabam/docs/remixer/PLACEMENT.md` records the
ColdFire map the same way: a region that exists is not a region that is
free.

Payload assignment, **documented** in `sdk/octabam/AGENTS.md`: payload A
serves tracks 5–8, payload B serves tracks 1–4. The runtime source charge
uses the same split (`source_core` in
`sdk/machines/octatrack/elekloader/dsp.c`: tracks 1–4 on core 1, tracks
5–8 on core 0).

The audio block is **16 samples** at 44.1 kHz, about 362.8 µs
(`docs/turing-machine-feasibility.md` on the Turing branch, and the frame
the performance notes budget against). Analog BD’s voice writes sixteen
stereo frames and then falls into stock AMP, FX1, FX2, and the packer
(`sdk/octabam/modules/analog-bassdrum/DSP909.md`).

### Remixes, modules, platform

A **module** declares what it is. A **remix** is a set of modules composed
onto the owner’s own OS 1.40C. Placement is a ROM cave, a DRAM unit, or an
appended runtime (`sdk/octabam/docs/remixer/PLACEMENT.md`). The build
refuses two modules that claim one address.

On this fork the shared sites are no longer per-module detours. The base
owns them and modules subscribe (`docs/module-guides/README.md`,
`sdk/machines/octatrack/EVENTS.md`). A track machine contributes one
80-byte `struct modwerk_machine` to the **`ot_machines`** table: chooser
name, Part signature, page, defaults, render, validator. Stock machines
stay FLEX, STATIC, THRU, NEIGHBOR, and PICKUP. Contributed machines are
chooser rows from 5 upward. Order today: POLY8 (10), Analog BD (20),
VECTOR (30), FM Synth (40).

**The table’s room is 4, and it is full** (`events.json`, `"room": 4`,
four subscribers). A fifth machine cannot contribute until that room is
raised in the base. The guide says a module that needs a full table
proposes more room first, in the base’s own review, not inside the module.
That proposal is milestone 0. It is shared-code work. It is not a CUBE
feature and it must not be stacked under a module release.

Analog BD is the DSP-machine precedent: ColdFire glue for the chooser,
page, and control record; the voice itself in DSP56300 assembly; static
placement; stock AMP downstream. FM Synth is the *page* precedent (SRC
knobs as musical parameters, PTCH as semitones, chromatic and MIDI notes)
but its engine runs on the **ColdFire**, and its README still marks chip
timing unmeasured. A 256-point oscillator with a per-sample phase does not
belong on the CPU that also runs the sequencer.

### Turing, as the ColdFire example

The Turing machine is not on `main`. The latest of it is branch
`cursor/turing-machine-m2-06d4`, staged at `sdk/drafts/turing-machine/`
(its README says to copy that folder to
`sdk/octabam/modules/turing-machine/` before a native build). It is a
**ColdFire-only** module: `turing.c` compiled to `turing.s`, hooks beside
it, DRAM for the engine, battery RAM for settings, project-file lines the
stock loader ignores because they start with `#`. It moves a MIDI track’s
notes when that track’s trig fires. It has no sample clock of its own.

That split is the one to copy:

| Work | Where | Precedent |
|---|---|---|
| Chooser row, SRC labels, Part signature, project bytes | ColdFire, through `ot_machines` | Analog BD, FM Synth, POLY8 |
| Note-rate or trig-rate decisions | ColdFire, on the stock trig | Turing (MIDI notes), Euclid (transport) |
| Phase, morph playback, FM, sync | DSP56300, one shared image per core, uploaded while stopped | Analog BD’s source seam for the render; dynload for the bytes ([section 5](#5-loading-cube-per-track-through-dynload)) |

CUBE does not hook Turing’s MIDI-out site and does not link Turing’s code.
A MIDI track is a different machine. Eight audio tracks of CUBE are eight
notes; Turing remains how a MIDI track would drive an external oscillator.

### Cycle budget

**Documented** arithmetic in `sdk/octabam/tools/build/cycle_count.py`:

```
CORE_TOTAL = 4535     # 200e6 / 44100
USABLE     = 3120     # what new code may spend, per core, per sample
```

`sdk/octabam/tools/emu/ot_emu/dsp.h` records **4532** instructions per
sample measured on the board, and calls 4535 the datasheet ceiling (an
earlier 4160 is marked retracted there). One-word instructions are one
cycle on the 56300; the static counter is a floor. Memory contention makes
the chip slower. Executed-instruction counts are not chip cycles. Analog
BD’s `CPU.md` says so explicitly and forbids comparing a voice’s
instruction count with the 3120 effect budget as if they were one number.

The USB runtime allocator does subtract source voices from that allowance
(`sdk/machines/octatrack/elekloader/dsp.c`, host constants in
`test_dsp.c`):

| Core | Tracks | Allowance | Eight FX slots at the stock reserve (342) | Left for source voices |
|---|---|---:|---:|---:|
| 0 | 5–8 | 3120 | 2736 | **384** |
| 1 | 1–4 | 3565 | 2736 | **829** |

Until a module carries a hardware cycle figure, a modelled price is
charged at **7/4**, rounded as `(cycles * 7 + 3) / 4` (`dsp.c`). The owner’s
MKII measured emulator claims at 1.42–1.74× on 11 October 2026. A voice
that must run on all four tracks of the tight core, beside stock FX still
being selectable, has `384 / 4 = 96` charged cycles. The integer charge of
a **55**-cycle model is `(55 * 7 + 3) / 4 = 97`, and four of those are 388,
which misses the 384 remainder by four. A **54**-cycle model charges 95,
and four of those are 380, leaving four charged cycles. **54 modelled
cycles, and a per-core engine price of 0**, is the design target for the
per-sample loop. The expensive morph is not allowed to live in that loop
(section 4). The instance table in [section 5](#5-loading-cube-per-track-through-dynload)
uses this arithmetic.

A track the core cannot carry “renders stock’s silent source”
(`EVENTS.md`, `ot_machines`). Price the worst voice honestly so a fifth
heavy use goes silent instead of missing the frame.

Analog BD’s 909, for scale and not as a budget CUBE may spend: about 410
executed instructions per sample per voice, and a full four-track loop
with FX measured in the 3600–4100 instructions/sample range (`CPU.md`).
Those are host instruction counts. They show that a source engine plus
stock FX already sits near the 4532 board figure. CUBE should be cheaper
than that 909 voice, not similar.

### Dynload

`sdk/octabam/platform/dsp-dynload/README.md` marks dynamic DSP loading as
an experiment: emulator qualification only, not a flash candidate, static
originals still resident, hardware timing unqualified. Its publication
notes leave several sequencer paths unmeasured on hardware. The runtime
`dsp.c` header says that loader is how USB-installed effect code is
admitted, and labels that path development only.

The voice should be **one shared DSP image per core**, uploaded through
that layer while the transport is stopped, then selected per track. Stock
machines stay on the tracks that did not select CUBE. That is [section 5](#5-loading-cube-per-track-through-dynload).
It is not a reason to link a private copy of the oscillator into both
payloads the way Analog BD does, and it is not a request to turn every
track into this machine.

Michael reports that, on real hardware, **any image which includes the
dynload platform never starts the sequencer**, including an image with
Turing left out and including an image after a 16-byte alignment fix of
the transport mailboxes. This session did not reproduce that. No CUBE
package is uploaded until that start works. The resident-engine note
(`docs/OCTATRACK_RESIDENT_ENGINES_ON_DEMAND.md`) still applies: code moves
only while the sequencer is stopped, because a bad DSP move can stall
frames and stick the sequencer.

USB install of the ColdFire machine record (chooser, page, Part signature,
Keep/Undo) can follow the base’s existing machine lifecycle. The DSP bytes
are a source package admitted by the same transport, not an effect slot.

### Pages, locks, and the rules that already exist

**Documented** (`docs/module-guides/machines.md`): playback parameter locks
are slots 0–5, then LFO 6–11, AMP 12–17, FX1 18–23, FX2 24–29. A slot can
draw a knob and publish nothing; each published knob has to be tested as a
lock. A stored value outside its count can stall the sequencer (the MODE
re-slot trap in `sdk/octabam/AGENTS.md`). Enumerated SETUP controls need a
fixed count from the first version, and new values are appended, never
inserted.

Stock AMP (attack, hold, release, level) stays the envelope. CUBE does not
add a second one. Three stock LFOs stay available; FM Synth’s habit of
replacing LFO 3 is not copied. Scenes crossfade the continuous knobs. That
is the Octatrack’s preset morph. The Mk3’s eight EEPROM presets are not
reimplemented.

Pitch comes from the track’s own PTCH byte, chromatic trigs, and MIDI
note-on. The oscillator’s phase advances at the audio rate whenever the
voice is sounding, including while the transport is stopped, because live
chromatic play is not the sequencer clock. Turing’s rule still holds for
anything that *steps*: no private clock, no private tempo.

Modules do not call each other. CUBE does not link Scale Quantizer, FM
Synth, Analog BD, or Turing. Scale snap of other tracks stays quantizer’s.
CUBE’s own chromatic take, if added, claims **only CUBE tracks** and sits
in the machine band (order 10–29) so a null claim does not swallow every
track. See the risk list.

## 3. Parameter mapping

Slot 0 is PTCH because chromatic recording and MIDI note-on already write
that playback byte (`docs/module-guides/machines.md`; FM Synth’s measured
keyboard uses the same slot, with a C4 key near 261.6 Hz). The other five
SRC encoders are the controls a pattern wants to lock and an LFO wants to
ride: the three cube axes, FM depth, and the A/B mix.

Defaults are the raw byte a fresh Part stores. Continuous ranges are
0–127. Enumerated ranges say their count. PTCH is stored as the signed
semitone offset FM Synth uses (raw 64 reads as 0, span −64…+63), so the
page formatter has to be the semitone one, not Flex’s sample-pitch
formatter. A cloned descriptor that keeps the donor’s formatter draws the
wrong control (the WOW/MODE trap in `sdk/octabam/AGENTS.md`).

### SRC page (playback slots 0–5)

| Slot | Label | Default | Law | Mk3 control it stands in for |
|---|---|---|---|---|
| A / 0 | PTCH | 64 (0 semitones) | −64…+63 semitones, equal tempered. 0 is the note the chromatic key already calls C4 (about 261.6 Hz), not the module’s 0 V = C0. | 1V/oct, coarse tune, and the played note, as one Octatrack pitch |
| B / 1 | X | 0 | 0–127 across eight frames. With morph on, linear mix of the two neighbouring X frames. With morph off, nearest of the eight. | X slider |
| C / 2 | Y | 0 | Same, across the eight groups. | Y slider |
| D / 3 | Z | 0 | Same, across the eight files of the loaded cube. | Z slider, which is also the file select |
| E / 4 | FM | 0 | 0 is off. 1–127 is thru-zero depth from oscillator B into A’s phase increment. The increment may be negative. | FM jack, normalled to the other oscillator |
| F / 5 | MIX | 64 | 0 = A only, 64 = equal, 127 = B only. | A MIX B |

X, Y, Z, FM, and MIX are the p-lock and LFO targets that matter while a
pattern plays. Scenes may crossfade all six. PTCH locks are the sequenced
notes. A trig’s chromatic lock writes slot 0; it must not be asked to also
carry a wavetable position.

### SRC SETUP (FUNC+SRC)

These are Part bytes. They are published on the SETUP page the way Analog
BD publishes ACCNT and the desk. Each one is still tested as a lock. They
are not the default LFO targets, because the six SRC slots already are.

| Encoder | Label | Count | Default | Behaviour |
|---|---|---:|---|---|
| A | FINE | 128 | 64 = 0 cents | −64…+63 cents on the PTCH note. |
| B | OCT | 5 | 2 = 0 | −2, −1, 0, +1, +2 octaves, applied before the low-note mute. Matches the manual’s ±2 octave shift. |
| C | UNI | 128 | 0 = off | 0 off. 1–96 detune B upward from A, a small fixed curve (a few cents at the bottom, about 50 cents at 96). 97–111 = B one octave down. 112–127 = B one octave up. This is the fine layer on top of OSC B’s B PTCH. It is not what turns B’s own cube position on. |
| D | TONE | 3 | 0 | 0 Orthodox: 16-bit table, no extra quantize. 1: output masked to 12 bits. 2: output masked to 8 bits. Original stand-ins, not the unnamed factory tones. |
| E | MORPH | 8 | 7 = XYZ | Bits for which axes crossfade. 0 hard (nearest frame only). 1 X, 2 Y, 4 Z, and the combinations. 7 is full trilinear. Changing this count later stalls old projects; append only. |
| F | SYNC | 3 | 1 = TRIG | 0 free-run. 1 reset A and B phase on the stock trig, at the trig’s sub-block offset. 2 hard: B’s wrap resets A’s phase (the modular jack, approximate). |

MODE (oscillator versus waveshaper) is **not** on this page, and it is
not the FM-law knob on OSC B. It needs a defined track input and a gain
law, and it changes what PTCH means (the manual turns the tune knob into
gain). Adding it later is a new value appended to LAW, or a new slot,
with a migration note. It is not a reuse of SYNC, and a p-lock must not
be able to turn the track into a waveshaper for one step.

BANK, if a second original cube is ever added, is a new SETUP value
appended after SYNC. It is not a reuse of Z. Z always moves inside the
cube that is loaded.

### The SRC ring (SRC, SETUP, OSC B)

On a CUBE track the SRC key walks three pages:

```
SRC  --double tap-->  SETUP  --double tap-->  OSC B  --double tap-->  SRC
```

A single press of SRC always shows the SRC page, from either of the other
two. FUNC+SRC always opens SETUP, from any of the three, and does not
walk the ring. The double tap is the stock page-key double tap, not a
second timer and not the TRACK key.

**Documented stock, and where it clashes.**

- Double-tap of a page key opens that page’s SETUP. FM Synth’s notes call
  the SRC case “double-tap PLAYBACK” and name the opener. The same notes
  cite the manual for AMP: FUNC+AMP or a double press of AMP opens AMP
  SETUP. VECTOR’s page 2 is SRC SETUP, opened by a double tap of SRC, and
  a single SRC press returns. POLY8 opens SRC SETUP with a double-click
  of SRC or with FUNC+SRC. `docs/OCTATRACK_DRIVING.md` uses FUNC+SRC for
  the same screen.
- The TRACK key is a different control. Its double tap opens the sample
  list or the machine list. Playmodes records the track keys and the five
  page keys as different handlers. Analog BD already refuses the track
  double tap for a synthesized source so it does not open Flex’s pool.
  CUBE does the same. The ring does not bind that key.
- The panel tools treat a track double tap the OS accepts as 50 ms down,
  150 ms up, 50 ms down (`docs/MODULE_UI_CAPTURES.md`, the `ot_emu`
  oracle). A 150 ms press is a single press. The SRC key’s own window was
  not measured separately. CUBE does not invent one. It uses whatever
  detector already decides that the PLAYBACK double tap opens SETUP.

From the SRC page, one double tap still opens SETUP. That is the stock
result, so the usual gesture does not change. The clash is the next
double tap, and only on a CUBE track: stock has no third SRC page, and
this study did not measure what a Flex track does if you double-tap SRC
again while SETUP is already open. VECTOR only documents the single press
as the way back. On CUBE that second double tap is defined. It opens OSC
B. A third double tap returns to SRC, which is also where a single press
goes. A musician who double-taps from OSC B expecting SETUP lands on SRC
instead.

**Fallback.**

- FUNC+SRC opens SETUP from SRC, from SETUP, and from OSC B. SETUP is
  never only reachable by walking the ring.
- A single SRC press leaves OSC B and leaves SETUP.
- The ring runs only when the current track is CUBE. Every other machine,
  MIDI mode, and the master track keep the stock double tap. Switching
  from a CUBE track to a stock track leaves OSC B; that track has no such
  page.
- A held trig or a held scene does not advance the ring. Lock and scene
  edits stay on the page that is open. A double tap during a hold falls
  through to the stock page-key handler.
- The gesture is not a project-wide `key:SRC` claim. That claim has no
  “only my tracks” scope (`docs/module-guides/README.md`), so naming it
  would clash with every other module that names SRC. The machine record
  owns the tap the way it owns its page: the handler replays stock unless
  this track is CUBE, and `uiClaims` stays empty. If that per-track wrap
  cannot be done without a global detour on the page-key handler, stop.
  Do not add a private timer. Double tap keeps the stock meaning (open
  SETUP only), FUNC+SRC still opens SETUP, and OSC B waits until the
  page key can be taken per track.

### OSC B

Panel labels are four characters: BX, BY, BZ, LINK, LAW, BPCH. The six
values are Part bytes, one set per track, saved with the Part the way
SETUP is. Defaults below are the raw byte a fresh Part stores.

| Encoder | Label | Count | Default | Law |
|---|---|---:|---|---|
| A | BX | 128 | 0 | B’s X. Same law as SRC X. Ignored while LINK keeps B on A’s position. |
| B | BY | 128 | 0 | B’s Y. Same law as SRC Y. Same ignore. |
| C | BZ | 128 | 0 | B’s Z. Same law as SRC Z. Same ignore. |
| D | LINK | 4 | 0 = BOTH | See the table under this one. Count is fixed. New values are appended. |
| E | LAW | 3 | 0 = LIN | The FM law for the SRC FM knob. Not the waveshaper. |
| F | BPCH | 128 | 64 = 0 | Signed semitones, −64…+63, same encoding as PTCH. 0 is unison with A before UNI. |

LINK is one knob with four values, because position and pitch are
different follows and a single on/off would tie them together. BOTH is
the previous v1 behaviour and the default.

| LINK | B’s cube position | B’s pitch |
|---|---|---|
| 0 BOTH | Follows A’s X/Y/Z. BX/BY/BZ are stored and not read. One shared cycle. | A’s note, plus BPCH, plus UNI. |
| 1 POS | BX/BY/BZ, own cycle, own morph. | A’s note, plus BPCH, plus UNI. |
| 2 PITCH | Follows A, one shared cycle. | Drone. A’s note is not added. |
| 3 OFF | Own cycle. | Drone. |

A’s note is PTCH plus FINE plus OCT, including a chromatic key and a MIDI
note. UNI still applies in every row: cents for 1–96, an extra octave down
for 97–111, an extra octave up for 112–127. UNI at 0 does not clear BPCH.
Unison is BPCH 0 and UNI 0.

A drone means fixed pitch, not a second voice and not a sound that ignores
AMP. B’s frequency does not use A’s PTCH, FINE, OCT, chromatic key, or
MIDI note. With BPCH at 0 and UNI at 0 that pitch is the same C4 the
chromatic key already calls about 261.6 Hz. SYNC still resets B’s phase
with A’s. The track’s AMP envelope still gates the mix. A closed amp is
silence, drone or not.

LAW, and why it is not the waveshaper:

| LAW | Behaviour |
|---|---|
| 0 LIN | Thru-zero linear FM. A scaled B sample is added to A’s phase increment and may change its sign. Depth is the SRC FM knob. This is the v1 law. |
| 1 EXP | Thru-zero exponential FM. B scales A’s increment instead of being added. Same depth knob, same two oscillators. A few arithmetic ops, not a second morph. |
| 2 OFF | SRC FM is ignored. B can be a drone or a second cycle without modulating A. |

The waveshaper stays off this knob. Shipping it as a LAW value would let
one p-lock change what PTCH means. When an input and a gain law exist, it
is appended as value 3, not inserted, and not stored by reusing OFF.

**Locks.** All six are p-lock targets and scene targets for the continuous
ones (BX, BY, BZ, BPCH). LINK and LAW are enums: they lock as steps, and
scenes do not crossfade them. They are not LFO destinations. BX, BY, BZ,
and BPCH are. CUBE still does not replace LFO 3.

They do not reuse playback slots 0–5. A BX lock that shared slot 1 would
replace the X lock on that step. The stock step record is 32 bytes: slots
0–29 are the five pages (playback, LFO, AMP, FX1, FX2), slot 30 is the
spare POLY8 stores a chord shape in, and slot 31 is the sample slot (FM
Synth’s measured layout, POLY8’s README). OSC B does not take slot 30.
The six lock bytes have to be a measured hole in the pattern track
record, or a base extension of that record in the same review as the
`ot_machines` room. Until a held trig on OSC B locks BX and the SRC X lock
on that step is unchanged, and the next step returns to the Part value,
the page is not done. Part save alone is not that test.

### Pitch, trigs, MIDI

```
A Hz = 261.6256 * 2^((ptch + fine/100) / 12) * 2^oct
B Hz = 261.6256 * 2^((note + bpch) / 12) * 2^uniOct * detune(uni)
```

`ptch`, `fine`, and `bpch` are the signed offsets (raw byte minus 64), not
the raw bytes. `oct` is the signed octave, −2…+2 (raw OCT minus 2).
`note` is `ptch + fine/100 + 12*oct` when LINK is BOTH or POS, and 0 when
LINK is PITCH or OFF (the drone). `uniOct` is −1, 0, or +1 from UNI’s
octave band. `detune(uni)` is 1 when UNI is 0 or an octave band, and the
small upward curve when UNI is 1–96. Mute A when `A Hz < 14`. Mute B when
`B Hz < 14`. Do not emulate the rear trimmers.

The phase increment is `Hz / 44100` cycles per sample, in a 24-bit (or
wider) accumulator. LAW LIN adds a scaled B sample into A’s increment and
may change its sign. LAW EXP multiplies that increment by a function of
the B sample and may change its sign. LAW OFF does neither. B’s increment
is always computed from B Hz, never from A’s modulated increment, so A’s
FM does not move B. That is the Mk3 LINK rule, and it holds for every
LINK value.

Chromatic keys and MIDI note-on, for a CUBE track only:

- Subscribe to `ev_midi_note_on`, `ev_midi_note_off`, and the chromatic
  takes with a claims function that accepts only this machine’s tracks,
  order in the 10–29 band (`EVENTS.md`).
- Store PTCH as the semitone the key is. Do not call FM Synth’s handler
  and do not read quantizer’s scale mask.
- Replay the stock tail the event contract requires. A CUBE track is one
  voice. Note-off is the stock AMP release, not a second envelope.
- v1 does not scale-snap. If Scale Quantizer is also installed, test that
  its knob and p-lock takes do not rewrite a CUBE PTCH byte under Flex’s
  pitch law. If they do, that is a base claims bug to fix in the base, not
  a private detour.

Trigs use the stock trigger flag and the sub-block offset Analog BD
already reads (the glue masks host-port tags before using the record).
SYNC = TRIG resets phase at that offset. AMP HOLD and REL stay in charge
of length. Retrigs reset phase only when SYNC is TRIG or HARD; FREE leaves
the cycle running so a held drone does not click every step.

### Wavetables: built in, then the card

**First version.** One original cube, generated by a script in the module,
16-bit, 256×512, in the frame order above. Suggested contents, all
original: sines and a few additive partial sets, band-unlimited geometric
shapes (the aliasing is wanted), and a couple of sequences that evolve
across X. No IME bank, no WaveEdit factory download, no sampled recording
of a Piston Honda.

The cube lives in ColdFire DRAM, once, shared by both cores. 256 KiB is
about 43 audio-arena pages (`6144` bytes each, `PLACEMENT.md`). Declare
the reservation the way the platform reserve is declared, so Flex free
memory drops by a stated amount. Do not hide it in the 10 MiB code
reserve and do not put it in DSP internal RAM (section 4).

**Later.** A user cube in the published WaveEdit layout: eight mono
16-bit files, or one static sample that is eight files concatenated
(262,144 bytes of PCM). Load it through the sample pool the instrument
already has, while the transport is stopped, into the same DRAM buffer.
Reject a short or a non-mono buffer and keep the built-in cube. Do not
add a private filesystem. The stock loader’s sample pages are the reader;
the exact page format is measured at implementation time and is not
copied into this document.

Z selects the file inside whichever cube is resident. There is no
per-note table switch in v1.

## 4. Efficient high-fidelity implementation

### Where the bytes sit

A 24-bit DSP word holds one 16-bit sample in the high bits (`<< 8`), low
eight clear, so a fractional `mpy` sees the table value. The cube is
131,072 words unpacked. That is larger than one core’s entire default X
RAM (36K) and larger than the 64K shared block. It cannot be resident on
the DSP. The shared window the effects already use starts at `X:0x30000`
(`dsp.h`), which is the datasheet’s shared RAM, and payload A’s half of
it is owned (BusVerb, `AGENTS.md`). Do not place the cube there.

| Data | Home | Size |
|---|---|---|
| Cube, 16-bit PCM | ColdFire DRAM, one copy | 262,144 bytes |
| A’s cycle, and B’s when LINK shares it | DSP X or Y, per CUBE track | 256 words. Four tracks on one core: 1,024 |
| B’s cycle when LINK is POS or OFF | same region, a second buffer on that track | +256 words. Four independent tracks: 2,048, not 1,024 |
| Voice state (both phases, FM, morph cursors, trig) | same region, per CUBE track | about 16 words while linked. A few more for B’s own cursor when it has its own cycle |
| Program | Dynload P arena, one image per core that has a CUBE track, not per track and not a static cave beside stock | aim under 400 words |

1,024 words is modest next to 36K and still has to be a **measured** hole
on both payloads. The program does not take that hole: it uses the
build-owned dynload arena, one copy per core, shared by every CUBE track
on it. Stock table bases differ between payload A and B (`AGENTS.md`: a
bare literal that is right on A is wrong on B). The build supplies the
base per payload. Analog BD’s X addresses are that module’s; they are not
a donation CUBE may take. Analog BD’s upload path also has a 256 KiB
staging limit (`DSP909.md`). An unpacked 24-bit cube (about 384 KiB) does
not fit that path. Another reason to keep the cube in DRAM and upload only
the working cycle.

### Playback

Per sample, per sounding oscillator, after the cycle is already mixed:

1. Add the phase increment (negative allowed).
2. Split the accumulator into a 8-bit integer index and a fraction.
3. Linear interpolation: `y = s0 + (s1 − s0) * frac`, with the read wrapped
   modulo 256. Hardware modulo addressing is the natural form; a computed
   address is the fallback if the modulo register is already owned by the
   stock dispatcher. Check which registers the source seam leaves free
   before using `m`.
4. On SYNC TRIG, zero the phase when the sample index equals the trig
   offset inside the 16-sample block.
5. On SYNC HARD, zero A’s phase when B’s integer index wraps.
6. Apply TONE as a mask on the output word, then write the MIX of A and B
   into the stereo source buffer stock AMP already reads.

**Inferred** cost of that loop, straight-line, no contention, one-word
`mpy`: about **20–30 cycles** per oscillator. Unison on is a second pass
over the same 256 words, about **+15–20**. FM is a few more arithmetic
ops on the increment, about **+8–12**. Hard morph (MORPH = 0) never builds
a new cycle, so the per-sample total stays near **30–55** modelled cycles
for A+B reading one buffer. The top of that range charges 97 and does not
fit four times on core 0 (388 against a 384 remainder). The counted loop
has to land at **54** modelled cycles, 95 charged, or the fourth track on
tracks 5–8 stays silent.

B’s own cube position does not add a third oscillator. The second pass
was already the unison pass. POS and OFF make that pass read B’s buffer
instead of A’s. The planning target for that loop is the same **54**. A
second full oscillator on top, about +20 modelled, is the miss case in
[section 5](#instances-memory-and-cycles): 74 modelled, 130 charged, and
core 0 then holds two such tracks, not four. It has to be counted with
`cycle_count.py` before it is believed; the figures here are estimates.

Drop-sample playback (ignore the fraction) is cheaper and harsher.
**Uncertain** whether the hardware does it. It is not the default. It can
be a later TONE value, appended, if a recording shows the hardware
stepping.

### Morph without blowing the budget

Doing trilinear interpolation per sample is eight linear reads plus seven
blends, on the order of **100+ cycles per oscillator**, and it doubles
with unison. Four tracks of that do not fit the 384-cycle remainder on
core 0. Do not put it in the sample loop.

Instead, maintain the 256-word current cycle and **spread** the rebuild:

- When the axes and MORPH are still, the sample loop only plays the
  buffer or buffers. Cost of morph: zero.
- When they move, blend toward the new cell a few frames of a buffer per
  16-sample block (about 16 MAC pairs per block is about one extra cycle
  per sample). A full 256-point crossfade then takes 16 blocks, about
  **6 ms**. Knob moves, p-locks, and the Octatrack’s LFOs are not
  audio-rate CV.
- BOTH and PITCH dirty one buffer. POS and OFF can dirty two. Both
  rebuilds share that one block of MACs, so two dirty buffers take about
  **12 ms** each instead of 6. The sample loop does not gain a second
  extra cycle. One extra modelled cycle on every voice is already a
  55-cycle model, and four of those miss core 0 (section 2). A 12 ms morph
  is still not a per-sample trilinear lookup. Per-sample trilinear is
  what does not fit.
- The blend is time-domain linear, one axis at a time according to the
  MORPH bits, so disabling an axis is “copy that neighbour’s index, do
  not mix”, which is what the manual describes.
- The eight corner cycles (2,048 words) are copied from DRAM into a small
  DSP scratch **when the integer cell changes**, not every sample. 2,048
  words is a host transfer. Do it between blocks, while building the
  control record, not inside the sample `do`. A and B share that scratch.
  When their cells differ, B’s corners follow A’s in a later block. If the
  transfer cannot finish in one frame, keep playing the old cycle until
  it does. A late table is a late morph, not a glitch and not a stalled
  sequencer.

Audio-rate XYZ, the thing a modular CV input can do, is **not** available.
The Octatrack has no audio-rate feed into a SRC knob. Document that. Do
not spend a resident copy of the whole cube to provide it.

### Anti-aliasing

Default is linear intra-cycle interpolation and **no** mipmap, **no**
2× oversampling, **no** BLEP. Oversampling doubles the cycle price (the
effects notes in `sdk/octabam/docs/effects/PORTS.md` say so for filters)
and would move the aliasing away from the Mk3. The alias above ~86 Hz is
kept.

Orthodox output is the 16-bit table value in the high bits of the 24-bit
word, then MIX. No extra saturation unless the sum of A and B exceeds
full scale; then the stock limiter behaviour is enough. Do not add a
modelled DAC. The converter is **uncertain**.

DC: a 256-point cycle with a non-zero mean will thump when the phase
resets. The generator script removes the mean of each original cycle.
User tables are left as the file stored them, which is what the hardware
plays. A reset click on a user table is the table.

### Polyphony

| Limit | Choice |
|---|---|
| Voices per track | **One** note. B is a second phase on that note, or a drone at its own pitch. It is not a second note and not a second trig. |
| Tracks | Up to eight, one each, subject to the core price. |
| Per core | Four tracks. Core 0 (tracks 5–8) is the tight one. |
| Chords | Not in this machine. FM Synth and POLY8 already do paraphony, and they own their own pages. |
| If the price does not fit | That track stays silent (the `ot_machines` rule). Do not steal cycles from another track’s FX. |

Declare `source_voice` as the measured per-sample cost of A+B with FM,
hard morph, and B on its own cycle, and `source_engine` as 0. The
descriptor carries one voice price (`dsp.c`), so a track that can flip
LINK to POS or OFF has to be admitted at that worst price. A non-zero
engine price is charged once per core on top of every voice, and core 0’s
four-voice margin at the 54-cycle target is four charged cycles, so an
engine price does not fit there. Kind is modelled until a hardware figure
exists, so the 7/4 charge applies. Four CUBE tracks on core 0 must still
leave every FX slot its 342-cycle reserve. The per-track instance table
is in [section 5](#instances-memory-and-cycles).

### Fixed-point habits already paid for

From `sdk/octabam/AGENTS.md`, applied to this voice and not repeated as a
tutorial:

- Disassemble every `mpy`. A second operand that can be negative must not
  assemble as `mpysu`. FM and a bipolar mix both can.
- Do not read `a0` and expect the same scale as `a1`.
- A logical mask on an accumulator leaves the extension dirty and the next
  store saturates. TONE masks belong in a register, or the store must be
  a clean transfer.
- `tfr` moves all 56 bits; `move a,b` limits. Phase state that is wider
  than 24 bits has to be explicit about which one it uses.
- Init must not write `r1`. Proc may.
- Init clears every state word the loop reads, including the current-cycle
  buffer, or a stale cycle plays forever.
- New labels must not prefix an existing label. `lua` offsets stay inside
  −64…63 or the long form is used.
- No instruction form that does not already appear in the stock payloads,
  until a hardware probe says otherwise.

The reference model is a small float (or integer) program that implements
the same phase, linear read, morph, FM, and mute. The DSP gate compares
it the way Analog BD compares `dsp909.Voice`. Agreement within a stated
residual (a few LSB at Orthodox, exact at the 8-bit mask) is the bar.
A listening render is not that bar.

## 5. Loading CUBE per track through dynload

This section is the loading plan. Sections 1–4 are unchanged as the
sound and the sample loop. Nothing here is a module, a firmware image,
or a measurement made on a unit during this study.

### How the platform works today

**Documented** (`sdk/octabam/platform/dsp-dynload/README.md`,
`sdk/octabam/platform/dsp-dynload-transport/README.md`, `PUBLICATION.md`,
`transfer.h`, `allocator.c`, `buffers.h`, and
`sdk/machines/octatrack/elekloader/dsp.c`).

Two pieces sit in the base:

| Piece | What it owns |
|---|---|
| `platform/dsp-dynload` | Which program is resident, and the publication guards around pattern, Part, and project changes |
| `platform/dsp-dynload-transport` | The frame mailbox that moves words onto a core and binds them |

The ColdFire side does not write DSP program memory itself. On an idle
audio frame the state-7 eDMA extension sends one **64-halfword** packet
to each core (idle bank +0x320) and reads a **32-halfword** status block
back (+0x360). The mailboxes are private per core: X:`0x2320`–`0x235f`
and X:`0x4320`–`0x435f` for the packet, X:`0x2360`–`0x237f` and
X:`0x4360`–`0x437f` for status. Software and DMA both use the uncached
alias of the ColdFire buffers (`UNCACHED` adds `0x08000000`). The
checksum detects a torn packet. It is not authentication.

Opcodes in `transfer.h`:

| Opcode | Role |
|---|---|
| PROBE | Packet check, acknowledgement, no store |
| STAGE | Diagnostic: 24 words into a build-owned 128-word P table. The transport README’s probe does not execute them |
| WRITE | Up to 24 program words into the build-owned arena. The DSP checks the range, reads the chunk back, and returns the sum |
| BIND | Point a dispatch id at an init/proc pair inside that arena |
| UNBIND | Restore that id’s original entry |
| BYPASS | Point an unbound id at a null stub, so a route nobody guarded goes dry instead of into reclaimed code |
| BASE | One entry of the eight-word Y-buffer table at X:`0x255` (an effect’s delay memory, not a machine) |

Sequence zero is skipped. A missing reply ages out after **64 frames**
(`dl_frame`). The frame interrupt must acknowledge DMA channel 1, restore
that channel’s byte count, and restore the host core selector to core 0
before the next frame. The transport README records why: the stock frame
sends its first command without selecting core 0, and forgetting the
restore sent the command to core 1 and **stopped both DSPs after three
frames in the emulator**. That repair was not tested on hardware.

The UI task owns allocation, file I/O, waiting, and the popup (`DSP
MEMORY FULL`, `DSP OVERLOAD`, `DSP LOAD FAILED`). The sequencer callback
and the DMA interrupt must not do those. Guards cover a queued pattern,
a stopped request, LOAD PROJECT, the chain restart on STOP, and PASTE /
RELOAD / RESET of the Part. Many live-effect writers are still unguarded;
`dl_unguarded` counts a live set that reaches the DSP unprepared. Static
originals stay resident. Do not reclaim them on the strength of the
emulator gates.

What the allocator actually admits is **effects**. Sixteen instances, two
per track (FX1, then FX2). Tracks 0–3 (panel tracks 1–4) sit on core 1;
tracks 4–7 (panel tracks 5–8) sit on core 0. One algorithm’s program is
reserved **once per core** and shared by every slot that selected it.
Per-slot memory is the effect’s Y block, handed out through X:`0x255`,
not a copy of the program. The arena in the experiment’s README is a
build-owned P table: 64 words of saved dispatch entries and 1,344 words
of code. The processing allowance is the stock scheduling allowance
(`MODWERK_DSP_ALLOWANCE0` 3120, `MODWERK_DSP_ALLOWANCE1` 3565). The P
allocator does not invent a second cycle budget. `dsp.c` then subtracts
source-machine voices *before* those effect slots, and each of the eight
slots on a core still costs at least `MODWERK_DSP_RESERVE` (342).

`elekloader/dsp.c` is the USB runtime that fills this catalog from module
packages. Its header labels that path development only.

### Selecting it on one track beside stock machines

A machine and an effect are different selections.

The panel’s machine chooser is the ColdFire `ot_machines` record: label,
Part signature, page, and the source price. A track is CUBE only when its
machine type byte is the FLEX/STATIC backing value (0 or 1) **and** its
signature matches CUBE (`machine_registry.c`, `owner`). A stock track
(type byte above 1, or a backing byte with no contributed signature) does
not take that row. Its source renderer stays stock. `claim` charges
`source_voice` on that track and `source_engine` once on that track’s
core; `release` drops the voice, and the engine drops when the last track
on the machine releases. A track the core cannot carry is unchanged and
renders stock’s silent source.

So the coexistence rule is the ordinary one:

- CUBE on track 1, FLEX on track 2: core 1 pays one CUBE voice. Track 2
  keeps the stock FLEX source and both of its effect slots. No CUBE state
  is allocated for it.
- The same on any mix of STATIC, THRU, NEIGHBOR, and PICKUP.
- Another contributed DSP machine on the same core adds its own voice and
  engine to the **same** remainder. Tracks on the other core do not see
  that sum. Payload A (tracks 5–8, core 0) and payload B (tracks 1–4,
  core 1) are separate budgets.
- Leaving the machine, or removing the module, releases the voice before
  the module’s memory goes (`modwerk_machine_tables_changed`).

Dynload’s BIND path does **not** perform that selection. BIND writes an
effect init/proc id. The sixteen catalog slots are FX1 and FX2. CUBE must
not be registered as an effect id: that would displace a reverb or a
filter and would still not appear in the machine chooser. The platform
README says the experiment adds no chooser and no controls.

What dynload should do for this voice, once [the sequencer starts](#the-sequencer-does-not-start):

1. The ColdFire record is selected per track, as above. That is the only
   chooser.
2. While the transport is stopped, the UI uploads **one** program image
   to each core that has at least one CUBE track, through WRITE, into the
   build-owned arena. The second, third, and fourth track on that core
   bind the same image. They do not upload it again.
3. Each CUBE track gets its own state and its own 256-word cycle buffer
   (below). That pointer is a source-machine field, not a `BASE` write to
   X:`0x255`. Those eight entries are effect delay memory.
4. The admission number is `modwerk_dsp_source_claim`, not the effect
   allocator’s slot sum. A core with no CUBE track does not hold the
   engine (`source_engine` off) and does not need the image.
5. A pattern change, a Part change, and LOAD PROJECT must prepare that
   set on the UI task before publication, the way the effect guards
   already require. The sequencer callback still must not allocate, read
   a file, wait, or transfer code.

That program is a **source package** in the catalog: shared code, no
effect-slot bits, admitted by the source claim. The allocator’s
`resident` flag today means “zero arena words, code lives outside.” CUBE
is the opposite shape (arena words, not an effect). Teaching the catalog
that shape is a base change, reviewed with the machine-table room, not a
private loader inside the module. Until it exists, the voice has nowhere
legal to be uploaded.

### Instances, memory, and cycles

**Inferred** from section 4 and from the charge formula. These are not
`cycle_count.py` results and not hardware figures. The sample loop plays
pre-mixed cycles, one shared by A and B, or two when LINK is POS or OFF.
B is a second pass on that note, not a second trig. Morph is spread
across blocks. Trilinear-per-sample does not fit and is not in this table.

Shared versus per track:

| What | How many | Where |
|---|---|---|
| Program image | One per core that has a CUBE track | Dynload P arena. Paid once, not per track |
| Cube | One for the whole unit | ColdFire DRAM, 262,144 bytes. Not copied per track |
| Playing cycle | One 256-word buffer per CUBE track, plus a second 256 when that track’s LINK is POS or OFF | DSP data on that track’s core |
| Phase, increment, FM, morph cursor | Per CUBE track | Same core. Section 4’s planning figure is about 16 words. B’s own cursor adds a few more. Neither moves the cycle budget. The voice sets the real size |
| Corner cycles (2,048 words per cell) | Not kept per track | Stream from DRAM into the cycle buffer between blocks. A second cell, when B’s position differs, is a second stream, not a second resident copy. Four tracks times two resident corner sets would be 16,384 words on the tight core |
| Effect Y blocks | Untouched | X:`0x255` stays with FX1/FX2 |

DSP data for the cycle buffers alone, plus the planning figure for state:

| CUBE tracks on that core | Cycle words, LINK shares B | Cycle words, every track POS or OFF | State, planning figure | Program images |
|---|---:|---:|---:|---|
| 1 | 256 | 512 | ~16 | One, on that core |
| 2 | 512 | 1,024 | ~32 | One |
| 4 | 1,024 | 2,048 | ~64 | One |
| 8, four per core | 1,024 per core | 2,048 per core | ~64 per core | One per core |

The cube is not in this sum. Eight tracks do not multiply DRAM by eight.
2,048 words of cycles on the tight core is still a measured hole, not a
reason to keep B’s corners resident.

Cycle price depends on which loop was counted. The target is still modelled
**54**, engine **0**, charge `(7 * 54 + 3) / 4 = 95` per voice. That target
already includes B’s second pass (the old unison pass). POS and OFF change
which buffer that pass reads. In-flight morph stays inside the 54 by
sharing one MAC block across dirty buffers (section 4). Effect slots stay
at the 342 reserve (8 × 342 = 2,736). Remainder before any source voice:
core 0 **384**, core 1 **829**.

If `cycle_count.py` says the second buffer costs a full extra oscillator,
use the miss row. That is about +20 modelled on the 54, so **74** modelled
and `(7 * 74 + 3) / 4 = 130` charged. The descriptor has one
`source_voice`, so this miss price would be charged even for BOTH unless
the claim learns the track’s LINK. Learning it is a base change beside the
machine-table room, not a second price hidden in the module.

At the **54 / 95** target, shared cycle or B’s own cycle:

| Layout | Charged source | Against | Result |
|---|---:|---|---|
| 1 track, either core | 95 | 384 or 829 | Fits |
| 2 tracks, same core | 190 | 384 or 829 | Fits. Two tracks on opposite cores are one voice each |
| 4 tracks, panel 5–8 (core 0) | 380 | 384 | Fits, **four charged cycles** left. This is the whole tight remainder |
| 4 tracks, panel 1–4 (core 1) | 380 | 829 | Fits, 449 charged cycles left |
| 8 tracks, four per core | 380 per core | 384 and 829 | Fits only while core 0’s margin holds |

A **55**-cycle model charges 97. Four of those are 388 and the fourth
claim on core 0 returns `RUNTIME_CYCLES`. That track stays silent. Core 1
still accepts it. Two dirty morphs must not be that 55th cycle. The
sample loop is aimed at 54 so the four-track case on tracks 5–8 is the
one that fits, not the one that refuses.

At the **74 / 130** miss, if B’s own cycle is a full extra oscillator:

| Layout | Charged source | Against | Result |
|---|---:|---|---|
| 1 track, either core | 130 | 384 or 829 | Fits |
| 2 tracks, same core | 260 | 384 or 829 | Fits. Core 0 has 124 charged cycles left |
| 3 tracks on core 0 | 390 | 384 | Does not fit. Over by 6 |
| 4 tracks, panel 5–8 (core 0) | 520 | 384 | Does not fit. Over by 136. The fourth claim is refused and that track is silent |
| 4 tracks, panel 1–4 (core 1) | 520 | 829 | Fits, 309 charged cycles left |
| 8 tracks | 520 and 520 | 384 and 829 | Does not fit. Core 0 holds two, not four |

So 1, 2, 4, and 8 still fit only while the counted two-buffer loop stays
at 54. Four independent tracks on tracks 1–4 still fit even at 130. Four
on tracks 5–8, and therefore all eight, do not fit at 130. Default LINK
BOTH does not get the cheap price unless the counted loop is actually
cheap, or the claim is allowed to follow LINK.

What else moves the remainder:

- `source_engine` is added once per core, on top of the voices. Any
  non-zero engine price spends the four-cycle margin on core 0. Keep it
  at 0, or drop the per-voice target by the same charge.
- An effect whose real cost is above 342 shrinks the remainder by the
  difference (`slot_charge` takes the max of the slot and the reserve).
  Four CUBE tracks on core 0 have no room for that. The same four on
  core 1 have hundreds of charged cycles left, so a heavier effect
  belongs on tracks 1–4 when both are in the pattern.
- CUBE does not free an effect slot and does not consume one. A CUBE
  track still has FX1 and FX2. Eight CUBE tracks still have sixteen
  effect slots, each reserving at least 342 before the source sum.
- Polyphony stays **one note per CUBE track**. B’s second pass is inside
  the 54 when the count hits the target. A FLEX track is not an extra
  CUBE voice. Chords stay with FM Synth and POLY8. A drone is still that
  one note, at a pitch that ignores A.
- A refused claim does not steal cycles from a neighbour. The refused
  track renders the silent source. The tracks that fit keep playing.

Tracks 1–4 are the comfortable core. Tracks 5–8 are the qualification
case: four voices at the target, stock reserves untouched, and almost
nothing left. A layout that only fits on tracks 1–4 is not done.

### Machine-table room

**Documented.** Dynload cannot add the chooser row.

`events.json` gives `ot_machines` `"room": 4`. `machine_registry.c` sets
`ROWS` to 9 (five stock machines plus four contributions) and stops the
reader at `n < ROWS - 5`. The experiment’s README says no new chooser is
added. BIND never writes a machine label, a Part signature, or a page.
A package that exists only in the DSP arena is not something the panel
can select on one track.

The chooser’s own immediates already follow the number of contributions
(`counts` writes `5 + n` and `4 + n`). The cap that does not follow is
`ROWS` and `room`. Raising one without the other either hides a record
or advertises a row the reader will not load.

Two ways to get a slot, and the way that is not available:

1. **A free subscription in that image.** Room 4 is how many contributed
   machines one image may include. It is not a reservation of POLY8,
   Analog BD, VECTOR, and FM Synth by name. Stock FLEX, STATIC, THRU,
   NEIGHBOR, and PICKUP are the five stock rows and do not use the four.
   An image that leaves one of today’s four contributed machines out can
   take CUBE in the free seat, beside every stock machine, with no room
   change. An image that wants CUBE **and** all four current machines
   cannot.
2. **Raise the room in the base**, before the module exists. `events.json`
   room, `ROWS`, and the loader’s table move together, in one
   owner-reviewed change. That is shared-code work. It is not a CUBE
   feature and it must not ship inside the module release. The module
   then subscribes as row five (or whichever seat is free).

Dynload does not sidestep either path. Overloading another machine’s
signature, stuffing CUBE into an effect row, or keeping a second chooser
inside the platform would put two owners on one selection. Do not.

### The sequencer does not start

**Reported** by Michael, 23 October 2026. Not reproduced in this study.
Not an emulator result.

On real hardware, any image that includes the dynload platform layer
never starts the sequencer. Turing left out of the image does not change
it. A 16-byte alignment fix of `dl_tx` / `dl_rx` does not change it. After
PLAY there is no MIDI clock, no notes, and no trig-LED chase. Start and
stop messages still go out. The emulator does not show the failure.

The current tree matches the “already tried” half of that report and
does not contain the fix. `transfer.c` declares
`volatile uint16_t dl_tx[2][DL_WORDS]` and `dl_rx[2][32]` with `DL_WORDS`
64, and no alignment attribute. Do not spend the next session realigning
those arrays, and do not spend it linking or unlinking Turing. Both are
already excluded as the cause.

What the symptom bounds, **inferred**, not a diagnosis:

- Start and stop still leave, so the ColdFire is running, the MIDI-out
  path runs, and the transport task that sends those two messages runs.
  This is not a dead CPU and not a dead MIDI port.
- Clock, notes, and the trig LEDs are the step advance. Those do not run.
  The bug is on the path from PLAY to the step clock, or on something
  that step clock waits for (an audio frame, a DSP reply, a DMA
  completion). It is not “MIDI output is broken.”

The platform’s own notes already say the emulator is the wrong witness
for this class of bug:

- The transport README: the core-select repair “passed both-core
  acknowledgements and continued frame execution in the emulator. No
  hardware test occurred.” Passing that gate did not qualify hardware.
- `UNCACHED` is `+0x08000000` on the ColdFire and the identity map in the
  native test. The port has no caches. A bug in which eDMA and the core
  disagree about the mailbox is invisible there. Alignment was tried;
  cache policy was not. Those are different experiments.
- The port’s DSP answers. `dl_frame`’s 64-frame timeout is about 23 ms of
  audio frames on the unit and is a path the port does not take when the
  model always acknowledges. A waiter that treats “reply pending” as
  “do not advance” hangs only when the reply is late.
- `PUBLICATION.md` already records one port blind spot: a queued Part
  change does not rewrite the live effect arrays unless a track’s source
  byte is 4. Gates that passed on that path were not testing the thing
  they were named for. The same standard applies here. An emulator that
  starts the sequencer does not contradict the hardware report.
- `hooks.s` says this module owns the state-7 hook and cannot compose
  with USB IN until a shared scheduler exists, and that the interrupt
  must not busy-wait. If PLAY’s step clock depends on that DMA chain
  completing the way stock completes it, the port can still count frames
  while the unit never arms the clock. That is a hypothesis to test, not
  a found cause.

### Investigation plan

Find the cause on the unit, with the emulator taught to show the same
hang, before any CUBE word is uploaded. No image, dump, or `.syx` comes
back into the repo. Counters stay on the machine or in a private log.

**Control and first cut.** Build two images from the same base. One does
not link the platform. One links it, with residency disabled, with no
probe and no upload, without Turing, and without CUBE. On the unit, PLAY,
and record four things separately: trig-LED chase, MIDI clock, MIDI
notes, MIDI start/stop. Then STOP and PLAY again. Also note whether
audio frames are still coming out of the converters. If the
residency-off image fails, the bug is in the linked hook or its static
data, not in an upload and not in a CUBE package. If it passes, the next
cut turns residency on and sends a single PROBE with no STAGE and no
WRITE.

**What to read, each cut.** Names that already exist in the platform,
plus the step clock the symptom is about:

| Watch | What it distinguishes |
|---|---|
| `dl_frames`, and whether PLAY increases it | The frame interrupt is still entering. A frozen count means the audio ISR stopped |
| `dl_errors`, `dl_accepted`, `dl_rejected`, `dl_modal_pending`, job state, pending sequence, `age` | A probe was sent, a reply was late (age reaching 64), or the mailbox was never idle |
| Host core-select after the frame | The known “left on core 1” failure. If it sticks, both DSPs can stop even though start/stop MIDI still leaves |
| eDMA channel 1 done, error, and byte count, on an idle frame and on a frame with a job | The hook returned is not the same as the descriptor completing. The idle path still saves and restores the byte count |
| Whether PLAY or the frame path waits while `dl_frame` reports a reply pending | The publication notes forbid that wait on the sequencer. A violation here matches “messages go out, steps do not” |
| DSP running versus halted, and whether the converters still move | A dead DSP or a stuck ESAI can hold the step clock while a separate MIDI task sends start and stop |
| Step index against the trig LEDs | Confirms the missing chase is the sequencer, not only the LED driver |

**Bisect the platform, not the experiments already done.** In order,
stopping at the first image that fails the LED chase and the MIDI clock:

1. Platform absent (control).
2. State-7 hook linked, `dl_frame` forced idle (returns immediately, sends
   nothing). This separates “the hook replaced stock’s DMA chain” from
   “the mailbox protocol runs.”
3. Real idle `dl_frame` (the counters move, no packet).
4. Publication guards linked.
5. Allocator and manager linked, residency still off.
6. One PROBE at boot, still no code upload.

If a parent of the alignment attempt is known, bisect commits from
“platform absent” to “platform present” with that same oracle. Do not
use emulator frame counts as the oracle. Do not repeat the alignment
build, and do not repeat Turing-on against Turing-off.

**What the emulator has to grow** before a green gate is evidence:

- A DSP that does not acknowledge, so the 64-frame age-out actually runs,
  and an assertion that the step clock still advances while a reply is
  outstanding.
- The host core selector left on core 1, and the same assertion.
- The uncached alias as a different memory from the cached view of
  `dl_tx` / `dl_rx`, so a packet written through one and read through the
  other fails the gate.
- eDMA completion, channel-1 error, and the byte-count restore as a step
  after the hook returns, including the idle frame that arms nothing.

Until those four fail in the port when forced, and pass when the hardware
cause is fixed, an emulator PLAY is not a qualification of this layer.

### Updated milestones

Each milestone is shippable on its own. None of them is a firmware commit.
Native assembly starts only when a milestone says so, on a machine that
has the owner’s OS outside the repo, and it never checks in an image, a
`.syx`, or a stock byte. Step 0 is the gate. Later steps do not start
around it. Step 2 is host-only and may run beside it.

| Step | Delivers | Depends on | Done when |
|---|---|---|---|
| 0 | The sequencer starts on hardware with the dynload platform linked. Residency off and Turing absent first; then one no-op probe. Cause written down. The emulator models the four gaps above | Nothing in CUBE | On a named unit: trig LEDs chase, MIDI clock and notes leave, start/stop still leave, audio frames continue. Forcing the cause in the port reproduces the hang; the fix removes it |
| 1 | Base change, owner review, not the module: `ot_machines` room enough for CUBE beside the contributed machines that image should combine, a source package in the dynload catalog that is not an effect id, and, if the pattern track has no spare for six OSC B locks, the lock-record extension | Step 0 | The loader accepts the new record. Stock rows stay in order. The sixteen effect slots stay effects. CUBE’s program admits through the source claim. A BX lock has a byte that is not slot 0–5 or slot 30 |
| 2 | Original cube generator and a host reference oscillator: axes, morph bits, 14 Hz mute, both FM laws, UNI, and all four LINK values including the drone | None | Vectors: known sine, known alias of a 256-point saw at C4, morph-off equals one frame, morph-on is the linear mix, FM sign flip, BOTH matches v1, POS uses BX, PITCH and OFF ignore A’s note, LAW OFF is dry |
| 3 | DSP56300 voice in `dsp_host` only, one voice, both payload bases, both cycle buffers. Sample loop at or under 54 modelled cycles with B on its own cycle, engine price 0. If the count is the 74-cycle miss, record 130 charged and do not claim four-wide on core 0. Teaching `source_voice` to follow LINK is a base change, done with step 1, and only then may BOTH stay at 95 while OFF pays 130 | Step 2 | `cycle_count.py` floor meets the target that the instance table will use. Reference residual met for BOTH and OFF. Dirty-state init silent. Two dirty morphs do not add a per-sample trilinear |
| 4 | Per-track loading, plus the SRC ring and the OSC B Part bytes. One shared program image per core, per-track state and cycle buffers, `source_voice` / `source_engine` claim. Upload only while stopped | Steps 0, 1, and 3 | CUBE on track 1, FLEX on track 2, tried on both cores. Double tap walks SRC, SETUP, OSC B on the CUBE track only. A single SRC press shows SRC. FUNC+SRC opens SETUP. Flex double-tap still opens Flex SETUP. A BX lock does not change that step’s X lock. Leaving CUBE returns the track to FLEX. The sequencer runs. A refused track is silent |
| 5 | The instance matrix: 1, 2, 4 on tracks 5–8, 4 on tracks 1–4, and 8, each in BOTH and in OFF | Step 4 | Admission matches the table for the price step 3 actually counted. At 54, core 0’s four-cycle margin holds or the extra track is silent. At 130, core 0 admits two OFF tracks and refuses the third. A stock effect on a CUBE track is still selectable. No effect slot was consumed by the voice |
| 6 | User cube from the sample pool, transport stopped, fallback to the built-in cube | Step 4 | A wrong-sized buffer is rejected. A valid 256×512 buffer changes Z = 0 |
| 7 | Hardware, owner or author, version-matched, of the voice rather than of the empty platform | Steps 4 and 5 | Heard on a named unit at the admitted price: one track, the layouts step 5 allowed, OSC B locks, LFO on BX, Part reload, power cycle. Sequencer does not stick. Chip timing recorded separately from the modelled floor |

SYNC HARD and the external-input waveshaper wait until step 4’s TRIG path
is already right. The hardware sync law is uncertain, and the buggy mute
behaviour must not be copied.

## 6. Risks

| Risk | Why it is real | What to do |
|---|---|---|
| Sequencer never starts | Michael reports that any image with the dynload platform fails this way on hardware, including Turing left out and including the mailbox alignment attempt. The emulator does not show it. The transport README already says the core-select repair had no hardware test | Step 0 before any CUBE upload. Instrument the idle hook, not a new voice. Teach the port the four gaps in section 5. Do not realign `dl_tx` / `dl_rx` and do not toggle Turing as the next experiment |
| `ot_machines` is full | Room 4, and four modules already subscribe. Dynload adds no chooser row | An image that omits one current contributed machine can take the free seat beside stock. An image that wants all four as well needs step 1, in the base, before the module. Do not poke the chooser length from the module, and do not hide CUBE in an effect id |
| Tight core | 384 cycles left on tracks 5–8 after eight stock FX reserves. Four voices at 54 modelled cycles leave four charged cycles. Four voices at the 74-cycle miss charge 520 and do not fit | Keep the two-buffer loop inside 54. Engine price stays 0. Both morphs share one MAC block. If the count is 130 charged, core 0 admits two independent tracks, not four, and eight tracks do not fit. Drop UNI’s second-pass detail before dropping linear interpolation |
| SRC double tap | Stock double-tap of SRC opens SETUP. The ring’s second double tap, on a CUBE track, opens OSC B instead. From OSC B a further double tap returns to SRC, not to SETUP | First double tap from SRC still opens SETUP. FUNC+SRC opens SETUP from any page. A single SRC press always shows SRC. Other machines are untouched. If the tap cannot be wrapped per track, do not claim the key and do not add a private timer |
| OSC B locks | Slots 0–5 are A’s page. Slot 30 is POLY8’s chord. Slot 31 is the sample. Six new lock bytes are not in that map | A BX lock must not write slot 1. Measure a hole or extend the pattern record in the base review. Part save is not a substitute for the held-trig test |
| One voice price | `source_voice` is one number per machine. A BOTH track and an OFF track on the same core are admitted alike | Declare the worst counted price, or teach the claim to follow LINK in that same base review. Do not admit OFF at the BOTH price |
| Effect cost above the reserve | `slot_charge` takes the max of the slot and 342, and that sum is added before the source voices | Four CUBE tracks on core 0 assume every slot is at the reserve. A heavier effect on tracks 5–8 spends the margin. Tracks 1–4 have the headroom |
| Estimates are not counts | Section 4’s cycle numbers are inferred floors | Step 3 replaces them. Contention and the MKII’s 1.42–1.74× factor remain until step 7 |
| Chromatic takes are first-wins | Quantizer and FM Synth already subscribe. A claims function that accepts every track would steal theirs, or theirs would steal CUBE | Claims only CUBE tracks, order 10–29. Test PTCH bytes with Scale Quantizer installed |
| Descriptor formatter | A cloned page draws the donor’s law | Write the formatter for all three pages. Semitone PTCH and BPCH. Enumerated OCT, TONE, MORPH, SYNC, LINK, and LAW |
| Stored bytes | A value outside the count stalls the sequencer | Counts fixed above. `stamp-defaults` before play on old projects. Append-only enums |
| Payload A versus B | Absolute table addresses differ | Build-supplied bases. Render both cores in step 3 |
| Data RAM versus the arena | Datasheet RAM is not free. The program can live in the dynload arena; the per-track cycles cannot. POS and OFF add a second 256-word buffer on that track | Measure a hole for two cycle buffers, not one. Do not reuse Analog BD’s addresses. Do not take an X:`0x255` entry. Do not require SPRING to be absent unless that measurement says so, and then declare the conflict |
| Cube size versus the 256 KiB DSP staging limit | Unpacked 24-bit cube does not fit | DRAM plus a 256-word working set per CUBE track |
| Factory content | Named banks are other people’s work. The product name is a trademark | Original cycles only. Chooser label CUBE, not Piston Honda |
| Alias pitch will not match the hardware | Module sample rate is unpublished; the Octatrack is 44.1 kHz | State it in the module README. Do not oversample to chase it |
| Tone and sync laws | Unnamed tone modes; sync firmware reports disagree | Orthodox plus two original masks. SYNC TRIG first. Do not implement the mute bug |
| USB lifecycle | New Octatrack modules are expected to Try/Keep/Undo | The ColdFire record can use that path. Keep must not be the first moment program words move. Upload only while the transport is stopped, and only after step 0 |
| Fidelity without a unit | No listening was done for this note | Step 2’s vectors are the contract. A hardware A/B against a Mk3 is optional and must not add factory samples to the repo |

## Recommended layout

Chooser name **CUBE**. One note per track. Stock AMP is the envelope.

**SRC:** PTCH, X, Y, Z, FM, MIX.

**SETUP** (FUNC+SRC, or one double tap of SRC): FINE, OCT, UNI, TONE, MORPH, SYNC.

**OSC B** (the next double tap): BX, BY, BZ, LINK, LAW, BPCH.

PTCH is the chromatic and MIDI note (0 semitones ≈ C4). X/Y/Z scan an
8×8×8 cube of original 256-sample, 16-bit cycles, linear between
neighbours unless MORPH turns that axis off. A single SRC press always
shows SRC. FUNC+SRC always opens SETUP. The double tap walks the ring
only on a CUBE track; from SRC it still opens SETUP, which is what stock
does. LINK defaults to BOTH: B uses A’s position and A’s note, plus BPCH
and UNI. POS and OFF give B its own cycle. PITCH and OFF make B a drone
at BPCH, still under the track’s amp. LAW defaults to thru-zero linear
FM. The cube stays in ColdFire DRAM, one copy for every track. The DSP
plays from one shared program image per core, uploaded through dynload
while the transport is stopped. The sample loop stays at 54 modelled
cycles (95 charged) with B on its own buffer; four such tracks fit core
0 with four charged cycles left, and eight fit as four per core. A
counted 74 (130 charged) fits four on tracks 1–4 and only two on tracks
5–8, so eight does not fit. Tracks that are not CUBE keep their stock
machines and their effect slots. A track that does not fit is silent.
Nothing is uploaded until an image that merely contains the platform
starts the sequencer on hardware.
