# Cube oscillator: a Piston Honda Mk3-style machine for the Octatrack

Status: design only, 23 October 2026. No firmware, no DSP image, and no module
is added here. This note is the behaviour target and the fitting plan for a
new Octatrack **track machine** in this fork (`pmsorhaindo/modwerk`).

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
| Phase, morph playback, FM, sync | DSP56300, both payloads, resident | Analog BD’s source seam |

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
charged at **7/4** (the owner’s MKII measured emulator claims at 1.42–1.74×
on 11 October 2026, `dsp.c`). A voice that must run on all four tracks of
the tight core, beside stock FX still being selectable, has about
`384 / 4 = 96` charged cycles, which is about **55 modelled cycles** after
the 7/4 factor. That is the design target for the per-sample loop. The
expensive morph is not allowed to live in that loop (section 4).

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

This study was asked to treat dynload as **breaking the sequencer on real
hardware**. That failure was not reproduced in this session. The design
does not depend on the loader:

- The voice is **resident** in both payloads, the way Analog BD’s engine
  is linked and uploaded before audio, not demand-loaded when a pattern
  changes.
- Code is not moved while the transport is running. The resident-engine
  note (`docs/OCTATRACK_RESIDENT_ENGINES_ON_DEMAND.md`) already requires
  placement only while the sequencer is stopped, because a bad DSP move
  can stall frames and stick the sequencer.
- The `source_kind` price is still the right admission number, so a later
  USB build can refuse an overload. Calling the dynload *uploader* to
  fetch the voice on pattern change is out of scope until that layer is
  shown, on hardware, not to disturb the sequencer.

USB install of the ColdFire machine record (chooser, page, Part signature,
Keep/Undo) can follow the base’s existing machine lifecycle. The DSP bytes
ride in the image. They are not a dynload package.

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
| C | UNI | 128 | 0 = off | 0 off. 1–96 detune B upward from A, a small fixed curve (a few cents at the bottom, about 50 cents at 96). 97–111 = B one octave down. 112–127 = B one octave up. B uses A’s morphed cycle. |
| D | TONE | 3 | 0 | 0 Orthodox: 16-bit table, no extra quantize. 1: output masked to 12 bits. 2: output masked to 8 bits. Original stand-ins, not the unnamed factory tones. |
| E | MORPH | 8 | 7 = XYZ | Bits for which axes crossfade. 0 hard (nearest frame only). 1 X, 2 Y, 4 Z, and the combinations. 7 is full trilinear. Changing this count later stalls old projects; append only. |
| F | SYNC | 3 | 1 = TRIG | 0 free-run. 1 reset A and B phase on the stock trig, at the trig’s sub-block offset. 2 hard: B’s wrap resets A’s phase (the modular jack, approximate). |

MODE (oscillator versus waveshaper) is **not** on this page in the first
version. It needs a defined track input and a gain law, and it changes
what PTCH means (the manual turns the tune knob into gain). Adding it
later is a new SETUP value or a new slot, with a migration note, not a
reuse of SYNC.

BANK, if a second original cube is ever added, is a new SETUP value
appended after SYNC. It is not a reuse of Z. Z always moves inside the
cube that is loaded.

### Pitch, trigs, MIDI

```
Hz = 261.6256 * 2^((ptch + fine/100) / 12) * 2^oct
```

`ptch` and `fine` are the signed offsets (raw byte minus 64), not the raw
bytes. `oct` is the signed octave, −2…+2 (raw OCT minus 2). Mute the voice
when `Hz < 14`, matching the manual’s floor. Do not emulate the rear
trimmers.

The phase increment is `Hz / 44100` cycles per sample, in a 24-bit (or
wider) accumulator. Thru-zero FM adds a scaled B sample into that
increment and may change its sign. LINK’s special case (B ignores A’s FM)
falls out of computing B’s increment from the pre-FM frequency plus UNI,
never from A’s modulated increment.

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
| Current cycle for the track | DSP X or Y, per core, four tracks | 256 words × 4 = 1,024 words |
| Voice state (phase, FM, morph cursor, trig) | same region | about 16 words × 4 |
| Program | resident P on **both** payloads, one copy per core, not per track | aim under 400 words |

1,024 words is modest next to 36K and still has to be a **measured** hole
on both payloads. Stock table bases differ between payload A and B
(`AGENTS.md`: a bare literal that is right on A is wrong on B). The build
supplies the base per payload. Analog BD’s X addresses are that module’s;
they are not a donation CUBE may take. Placement is a measurement task
before any word is claimed. Analog BD’s upload path also has a 256 KiB
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
for A+B. That is the number that can sit in the 55-modelled-cycle target
on core 0 with four tracks. It has to be counted with `cycle_count.py`
before it is believed; the figures here are estimates.

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

- When X/Y/Z/MORPH are still, the sample loop only plays the buffer.
  Cost of morph: zero.
- When they move, blend toward the new cell a few frames of the buffer
  per 16-sample block (about 16 MAC pairs per block is about one extra
  cycle per sample). A full 256-point crossfade then takes 16 blocks,
  about **6 ms**. Knob moves, p-locks, and the Octatrack’s LFOs are not
  audio-rate CV. A 6 ms morph is inaudible as lag and is the difference
  between four tracks fitting and none fitting.
- The blend is time-domain linear, one axis at a time according to the
  MORPH bits, so disabling an axis is “copy that neighbour’s index, do
  not mix”, which is what the manual describes.
- The eight corner cycles (2,048 words) are copied from DRAM into a small
  DSP scratch **when the integer cell changes**, not every sample. 2,048
  words is a host transfer. Do it between blocks, while building the
  control record, not inside the sample `do`. If the transfer cannot
  finish in one frame, keep playing the old cycle until it does. A late
  table is a late morph, not a glitch and not a stalled sequencer.

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
| Voices per track | **One** note. Unison is a second phase on that note, not a second note. |
| Tracks | Up to eight, one each, subject to the core price. |
| Per core | Four tracks. Core 0 (tracks 5–8) is the tight one. |
| Chords | Not in this machine. FM Synth and POLY8 already do paraphony, and they own their own pages. |
| If the price does not fit | That track stays silent (the `ot_machines` rule). Do not steal cycles from another track’s FX. |

Declare `source_voice` as the measured per-sample cost of A+B with FM and
hard morph, and `source_engine` as 0 if the morph rebuild is inside the
voice price, or as the measured per-core overhead if the corner-table
transfer is shared. Kind is modelled until a hardware figure exists, so
the 7/4 charge applies. Four CUBE tracks on core 0 must still leave every
FX slot its 342-cycle reserve.

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

## 5. Milestones and risks

Each milestone is shippable on its own. None of them is a firmware commit.
Native assembly starts only when a milestone says so, on a machine that
has the owner’s OS outside the repo, and it never checks in an image, a
`.syx`, or a stock byte.

| Step | Delivers | Depends on | Done when |
|---|---|---|---|
| 0 | Base change: `ot_machines` room 5 (or more). Owner review. Not part of the module. | Nothing in CUBE | A fifth record is accepted by the loader and `modules:compat`, and the four current machines still appear in their order |
| 1 | Original cube generator and a host reference oscillator (no DSP): axes, morph bits, 14 Hz mute, thru-zero FM, unison, tone masks | Step 0 can lag; this step does not touch the image | Vectors: known sine, known alias of a 256-point saw at C4, morph-off equals one frame, morph-on is the linear mix, FM sign flip |
| 2 | DSP56300 voice in `dsp_host` only, one voice, resident-style source, both payload bases | Step 1 | `cycle_count.py` floor under the 55-modelled-cycle target for the sample loop; reference residual met; dirty-state init silent |
| 3 | ColdFire machine record: chooser name CUBE, SRC and SETUP pages, Part signature, render control record, static P placement on both cores. Card remix. No dynload upload | Steps 0 and 2 | Emulator: select, play, p-lock X and PTCH, LFO to Y, SYNC TRIG, leave the machine and the track is FLEX again, neighbouring Flex still plays. Sequencer runs |
| 4 | Price `source_voice` / `source_engine`. Four tracks on core 0 beside stock FX reserve | Step 3 | Admission refuses a layout that does not fit; the refused track is silent; a layout that fits plays |
| 5 | User cube from the sample pool, transport stopped, fallback to the built-in cube | Step 3 | A wrong-sized buffer is rejected; a valid 256×512 buffer changes Z = 0 |
| 6 | Hardware, owner or author, version-matched | Steps 3–4 | Heard on a named unit: one track, then four on tracks 5–8, p-locks, LFO, Part reload, power cycle. Sequencer does not stick. Chip timing recorded separately from the modelled floor |

Steps 5 and the waveshaper (external-input MODE) wait. SYNC HARD waits
until TRIG is already right, because the hardware sync law is uncertain
and the buggy mute behaviour must not be copied.

### Risks

| Risk | Why it is real | What to do |
|---|---|---|
| `ot_machines` is full | Room 4, four modules subscribed | Step 0 before any module PR. Do not poke the chooser length the way early Analog BD did; the base owns those sites |
| Dynload and the sequencer | The requester reports a hardware break. The tree still marks the loader experimental and unmeasured on several sequencer paths | Resident voice only. No pattern-time code upload |
| Tight core | 384 cycles left on tracks 5–8 after eight stock FX reserves; 7/4 charge | Sample loop stays on one pre-mixed cycle. Morph is spread. If the count misses, drop unison before dropping linear interpolation |
| Estimates are not counts | Section 4’s cycle numbers are inferred floors | Step 2 replaces them. Contention and the MKII’s 1.42–1.74× factor remain until step 6 |
| Chromatic takes are first-wins | Quantizer and FM Synth already subscribe. A claims function that accepts every track would steal theirs, or theirs would steal CUBE | Claims only CUBE tracks, order 10–29. Test PTCH bytes with Scale Quantizer installed |
| Descriptor formatter | A cloned page draws the donor’s law | Write the formatter. Semitone PTCH, enumerated OCT/TONE/MORPH/SYNC |
| Stored bytes | A value outside the count stalls the sequencer | Counts fixed above. `stamp-defaults` before play on old projects. Append-only enums |
| Payload A versus B | Absolute table addresses differ | Build-supplied bases. Render both cores in step 2 |
| Shared X/Y and P | Datasheet RAM is not free. Analog BD already occupies a donor region and removes SPRING from its remix | Measure a hole. Do not reuse Analog BD’s addresses. Do not require SPRING to be absent unless the measurement says that is the only hole, and then declare that conflict |
| Cube size versus the 256 KiB DSP staging limit | Unpacked 24-bit cube does not fit | DRAM plus a 256-word working set |
| Factory content | Named banks are other people’s work. The product name is a trademark | Original cycles only. Chooser label CUBE, not Piston Honda |
| Alias pitch will not match the hardware | Module sample rate is unpublished; the Octatrack is 44.1 kHz | State it in the module README. Do not oversample to chase it |
| Tone and sync laws | Unnamed tone modes; sync firmware reports disagree | Orthodox plus two original masks. SYNC TRIG first. Do not implement the mute bug |
| Dual independent positions | The hardware stores a separate X/Y/Z per oscillator. Six SRC knobs cannot hold both and still keep PTCH | v1 shares one position. B is unison and the FM source. A second position is a later page, not a silent reuse of these bytes |
| USB lifecycle | New Octatrack modules are expected to Try/Keep/Undo | ColdFire record can use that path. DSP bytes stay resident so Keep does not dynload a voice under a running sequencer |
| Fidelity without a unit | No listening was done for this note | Step 1’s vectors are the contract. A hardware A/B against a Mk3 is optional and must not add factory samples to the repo |

## Recommended layout

Chooser name **CUBE**. One note per track. Stock AMP is the envelope.

**SRC:** PTCH, X, Y, Z, FM, MIX.

**SETUP:** FINE, OCT, UNI, TONE, MORPH, SYNC.

PTCH is the chromatic and MIDI note (0 semitones ≈ C4). X/Y/Z scan an
8×8×8 cube of original 256-sample, 16-bit cycles, linear between
neighbours unless MORPH turns that axis off. FM is thru-zero from the
unison oscillator. The cube stays in ColdFire DRAM. The DSP plays one
pre-mixed cycle per track, resident on both cores, and does not use
dynload. Four such tracks are the goal on the tighter core; a track that
does not fit is silent.
