# Turing Machine testing

M2 in progress, 16 October 2026 (re-run on a fresh machine after the branches were brought up to date with
the fork's `main`; row labels moved into `.text` after `module:verify`). Emulator and toolchain only; nothing
here ran on hardware.

## OCTABAM11: hardware-test fixes (26-27 October 2026, local work copy)

Emulator only; nothing here ran on hardware. Brief 9 (`diag/claude_brief9.md`), report
`diag/CLAUDE_REPORT9.md`. Built on OCTABAM10 (no CUBE). The OCTABAM10 sources are in `diag/octabam11/orig10/`.

- **Build:** `diag/octabam11/build_octabam11.sh` (OCTABAM10's script, `BUILD=11`, same 74 transport copies).
  The image's payload is bit-identical to the gated `out/turing_11.bin`.
- **Images:** payload `out/turing_11.bin` = `out/mainos_bus.bin` sha1 `6672ad307f2f16aa651527e4d25b281571873f36`;
  `out/OCTATRACK_OCTABAM11.bin` sha1 `6df8f2a142a98bdcbde640094ee54c84187a81ae`; `out/OCTATRACK_OCTABAM11.syx`
  sha1 `def88ef8f26f4fe29fbdb7d067190b5a50e46683`.
- **Sources (SHA-256):** `turing.c` `e12fed71…2355`, `turing.h` `4283e97f…04ee`, `hooks.s` `a0972adc…3e2b`,
  `turing.s` `d63aab71…a6dc`, `verify.py` `24015904…9059`. Port `out/emu/ot_emu` `187243df…49d9` (`OT_HW_RULES` on).

### `verify.py out/turing_11.bin`: 192/192 PASS, exit 0, ~166 min (`diag/octabam11/verify11.log`)

`TM_ONLY=<run>[,<run>]` runs single runs (names in `main()`); each new run also passed alone first
(`diag/octabam11/logs/`). The engine model was checked bit-exact against the compiled C engine (4,000
random registers x 40 steps, every LEN and LOCK, 0 mismatches).

| Item | Check | Result |
|---|---|---|
| (1) wire | LOCK 127, LEN 2, 3, 4, 5, 7, 8, 16, 33, 64 (poked registers, SCAL 127, 2X): the notes on the wire repeat with period exactly LEN (minimal period = LEN), as the model | pass |
| (1) gates | LOCK 127, DENS 64, LEN 2, 3, 4, 5, 7, 8, 16: notes and rests on the grid repeat with period LEN, as the model | pass |
| (1)(2) live | The hardware's sequence on the panel alone (fresh pattern, fixed seed, MODE ON at the defaults, PLAY, FUNC+LOCK to 127, DENS 127, LEN turned live 16, 4, 2, 3, 5, 8, 7, 16): each repeats with period LEN and plays more than one note; the first LEN 16 plays 12 notes 40..57; LEN 16 after a locked LEN 8 repeats within 16 (it replays the 8-loop, the register's history) with 6 notes over 15 semitones | pass |
| (2) model | 2,000 boot seeds x 8 tracks x 4 patterns: the first pass's notes average NOTE (within 0.5), a quarter in the bottom quarter | pass |
| (2) port | 4 tracks x 4 patterns never played (unseeded cells): each plays the model's seeded register; mean within 6 semitones of C3 at SCAL 127, below C3-12 and above C3+12 reached | pass |
| (3) | WRITE on the same fixture and register on `out/turing_10.bin`: trig bits, trigless bits, lock records and step words byte-identical (the trig type and LEDs OCTABAM10's). A hand-placed NOTE-locked trig: note bit 1, trigless 0, step word 0000, as WRITE's; WRITE's record adds NOT2..4 0x40 and its `W` + centre | pass |
| (4) | After WRITE, MODE OFF <-> ON 12 times while playing, then 6 LOCK redraws: 140 notes on 140 steps, worst offset from the grid 0.007 ms (limit 2 ms) | pass |
| (5) | New project, T1 ON 127/16/64/64; WRITE and SAVE while playing mid-pass; STOP: the cell holds the pass-start register; RELOAD: the same cell and the identical phrase (notes and rests on their steps) as before SAVE and as the written trigs; a fresh boot of the saved card (`--mount`) loads the same cell and plays the identical phrase from the same step | pass |
| (5) on OCTABAM10 | The same run on `out/turing_10.bin` (`diag/octabam11/logs/v_reload_10.log`): 5 of the 6 checks FAIL. The phrase after RELOAD and after reboot is the one before SAVE rotated by two steps, which is the hardware report | (reproduces bug 5) |
| (6) | Track keys (T3, T2, T1 select tracks) after WRITE, SAVE and RELOAD while playing (each closed with NO) and after the boot load | pass |
| (a) model | Flip table now for LEN 4 too (LEN 2..7 change a note: slip 1 a pass, 64 every note, 0 two a pass); LOCK 25 0.85..1.15 a pass | pass |
| (h) | MODE OFF: MIDI OUT **messages** identical to stock 1.40C (the raw wire happened to be identical too, 378 B); T1 ON with CLOCK SEND: F8/FA/FC and tick ISRs as stock; `repro_clock.py` F8 139 FA 1 FC 1, 36 notes, 431 tick ISRs; `dl_counters.py` [21, 21], 0 errors, core-1 select at state 7 = 0 | pass |

Changed because the spec changed: the engine model (`flip_chance`, `advance`/`step_value` for LEN 2..7,
`gate` on the step's value, and `Model.restart`: a PLAY starts from the cell's pass-start register, MODE ON
at the pattern's step); replace_run, page_run and clock_run restart the model at each PLAY; replace_run's
"toggled" check reads the phrase by grid step (ON again picks the loop up at the pattern's step, not where
it was switched OFF); lock_run (c) is now (1) above (no more forcing LEN 2's two bits apart); lock_model_check
adds LEN 4; stock_run's MODE OFF comparison is on messages.

Probes (not part of the gate): `diag/octabam11/probe_keys.py` on stock 1.40C, OCTABAM10 and OCTABAM11
(`probe_keys_*.log`): right after RELOAD while playing the track keys select nothing until NO, on all three,
stock included. `probe_toggle.py`, `probe_len.py`, `probe_trigs.py` as the report describes.

### Not tested (OCTABAM11)

Hardware; LOAD PROJECT through the project list (RELOAD and a boot load were); a power cycle that keeps
battery RAM *and* loads the project (each path was tested on its own); LEN 2..7 with per-track scales.

## OCTABAM10: Turing Machine behaviour, SCAL, DENS, LEN 64, WRITE (25 October 2026, local work copy)

Emulator only; nothing here ran on hardware. Brief 8 (`diag/claude_brief8.md`), report
`diag/CLAUDE_REPORT8.md`. The OCTABAM9 section below stays as the record of that image.

- **Build:** `diag/octabam10/build_octabam10.sh` (OCTABAM9's script, `BUILD=10`, same 74 transport copies).
  The image's payload is bit-identical to the gated `out/turing_10.bin`.
- **Images:** payload `out/turing_10.bin` = `out/mainos_bus.bin` sha1 `3ddeaf3c4c89e13d9ddcdb6d2547df4e27943bda`;
  `out/OCTATRACK_OCTABAM10.bin` sha1 `37e77713f1ad961a86e86688d96670bba1a41acc`; `out/OCTATRACK_OCTABAM10.syx`
  sha1 `097c2667a819ecfb08cdac679ebd4e23a88a959c`.
- **Sources (SHA-256):** `turing.c` `4df04c0e…a48b`, `turing.h` `cbe3f5db…10cf`, `hooks.s` `3c68f312…446d`,
  `turing.s` `5f528669…5017`. Port `out/emu/ot_emu` `187243df…49d9` (`OT_HW_RULES` on).

### `verify.py out/turing_10.bin`: 172/172 PASS, exit 0, 197 min (`diag/octabam10/verify10.log`)

New checks (brief 8 items a–h); each run also passed on its own first (`diag/octabam10/logs/`):

| Item | Check | Result |
|---|---|---|
| (a) model | Flips per pass at LOCK 0/25/40/64/80/96/127 for LEN 8, 16, 64 within 6 % of the table (3,000 passes a cell); every LOCK 96..127 repeats over 40 passes; LOCK 25 0.85..1.15 flips a pass | pass |
| (a) port | LOCK 0/25/40/64/80/96/127, LEN 16, SCAL 127, poked registers, 2X: every note as the model; 96 and 127 repeat exactly (period 16, no flip); the others change | pass |
| (b) | FUNC + LOCK (knob B): 30 -> 64 -> 127 -> 127, -> 64 -> 0 -> 0; 100 -> 64 -> 127; the dial draws 64; without FUNC one a tick | pass |
| (c) | LOCK 127, LEN 2, 16, 33, 64: period exactly LEN (and no shorter) over at least two passes, as the model; LEN on the page stops at 64 | pass |
| (d) model | 3,000 registers: SCAL 0 NOTE only; 64 exactly NOTE-12..+12 reached; 127 NOTE-24..+24 reached, >= 45 of 49 notes; the span monotonic, 0/24/48 | pass |
| (d) port | SCAL 0/64/127 x LOCK 25/127: every note as the model and in range, a NOTE lock (C4, step 5) the centre of its step; knob D sets SCAL (dial); SCAL 127 with ARP SETUP KEY C MAJ: every note in C major, range >= 24 | pass |
| (e) model | 4,000 registers: DENS 0 no note, 127 every step, 64 49..51 %, rising with DENS; LOCK 127 DENS 64 rests repeat with the loop | pass |
| (e) port | DENS 0: T1 silent (and T2's NEI); 127: a note every step; 64: notes and rests as the model, the same rests every pass; NEI on T2 true exactly on T1's note steps; CC1 lock on a rest step (3) goes out with no note, on a note step (7) with its note; DENS turned live 64 -> 100 -> 64: denser bars, then the old bars exactly | pass |
| (f) | Push A with MODE OFF: nothing written, no popup. ON: popup "MIDI TRACK WRITTEN" (a watch on `0x4005a2b8`); MODE stays ON, register and random state unchanged; note trigs + NOTE locks (NOT2..4 0x40, byte 30-31 `W` + centre) exactly on the model's note steps, rests empty, conditions clear; ON continues the phrase; MODE OFF: the same MIDI messages as ON and every note time within 4 samples (measured 1.2; stock's own jitter between identical runs 1.7); LEN 5: OFF's first 16 steps = ON's, then repeats 16; WRITE while playing + OFF while playing: one unbroken phrase | pass |
| (g) | Battery RAM of one boot carried into a fresh boot (a power cycle): the page shows ON, LOCK 40, LEN 64, SCAL 100, DENS 30 and the same notes and rests play; an OCTABAM9 cell (valid record, no OCTABAM10 flag) is converted: ON 127 8, SCAL 64, DENS 127, register 0xa53c, plays its 8-step phrase; SAVE writes `#TURING_B1_P1_T1=1,127,64,100,30,<register>` and RELOAD restores them (project_run) | pass |
| (g) old lines | A SAVEd project's #TURING lines replaced by OCTABAM9's `=1,127,8,42300,4660,22136` (A01 T1) and `=1,100,5` (A02 T2) and OCTABAM8's `#TURING_T3=1,30,12`; a fresh boot loads it (`--mount --set --project`): each cell as its line, SCAL 64, DENS 127, the 16-bit register kept, T3 in every pattern, A01 T2 the defaults. Playback after the port's load not checked (the fixture's channel edits do not land there) | pass |
| (h) | MODE OFF: wire bytes identical to stock 1.40C (stock_run, unchanged); T1 ON with CLOCK SEND: F8/FA/FC and tick ISRs as stock; `repro_clock.py` F8 139 FA 1 FC 1, 36 notes; `dl_counters.py` [21, 21], 0 errors | pass |

Changed because the spec changed (each listed in the report): the engine model (64-bit register, the
LOCK curve, the per-track random state, SCAL, DENS) under every model check, `poke_cell` defaulting to
DENS 127, `set_page` (LEN one tick a step; SCAL and DENS), `view()` (five widgets), page_run (defaults
with SCAL and DENS; knob F does nothing, D and E edit), project_run (LEN 64, SCAL 100, DENS 30; the line
`=1,127,64,100,30,<4 x 16 bits>`; new: a new project has SCAL 64 and DENS 64), range_run and
range_model_check (64-bit registers, LEN 2..64).

**Running status.** Stock 1.40C clears MIDI OUT's running status every 89 passes of `0x400a4df0`, whose
phase against PLAY changes from run to run: two identical stock runs gave 257 and 258 wire bytes with the
same messages (`diag/octabam10/probe_rs.py`). The WRITE comparison is therefore on the messages with status
written out; stock_run's MODE OFF wire comparison is unaffected (it passes byte for byte).

Screens: `diag/octabam10/shots/` (`shots10.py`): the page's defaults, ON 127 64 100 30, the FUNC snap, the
WRITE popup, after it. Media `ot-page-default.png`, `ot-page-set.png`, `ot-page-written.png` regenerated.

### Not tested (OCTABAM10)

Hardware; per-track scale mode with WRITE; WRITE on a pattern longer than 16 with a different per-track
length; MIDI timing under load with eight Turing tracks at LEN 64.

## OCTABAM9: quirk fixes (25 October 2026, local work copy)

Emulator only; nothing here ran on hardware. Brief 7 (`diag/claude_brief7.md`), report
`diag/CLAUDE_REPORT7.md`. The OCTABAM8 section below stays as the record of that image.

- **Build:** `diag/octabam9/build_octabam9.sh` (OCTABAM8's script, `BUILD=9`, same 74 transport copies).
  Rebuilt after the last source edit: payload bit-identical to the gated one.
- **Images:** payload `out/turing_9.bin` = `out/mainos_bus.bin` sha1 `886d721aef8cf0a55fa7f36b9ea5cc3a8b86fa80`;
  `out/OCTATRACK_OCTABAM9.bin` sha1 `d68f442bb13b583be3386d59725e36e5e5cf3405`; `out/OCTATRACK_OCTABAM9.syx`
  sha1 `aa6d4dac77428515892f73c45a6cc529b2537f90`.
- **Sources (SHA-256):** `turing.c` `ecca8da7…6427`, `turing.h` `9bac77c3…b250`, `hooks.s` `064d03b2…e289`,
  `turing.s` `9e8ad9e0…88a9`. `verify.py` as run differed from the checked-in one only in its docstring.
  Port `out/emu/ot_emu` `187243df…49d9` (`OT_HW_RULES` on).

### `verify.py out/turing_9.bin`: 124/124 PASS, exit 0, 83 min (`diag/octabam9/verify9.log`)

Every OCTABAM8 check still runs (the model now centres the note: NOTE − 12 + offset). Changed or new:

| Item | Check | Result |
|---|---|---|
| (a) mute | Muted twice (once across STOP): T1 silent while muted, T2 goes on; each T1 note is the model's note for the step it lands on, the model clocking every step, muted or not; the toggle checks after a STOP while muted continue the model with no lost step | pass |
| (b) locks | Panel-entered locks on T1 (step 1 VEL 0 + CC1 87, 3 CC1 107, 5 NOTE C4, 7 a lock trig with VEL 30 + CC1 77, 9 VEL 60 + shorter LEN). ON: velocities 30/60/100, no note on 1, step 9's length equals stock's locked length, CC1 87/107/77 on steps 1/3/7 and back to its value the next step; stock (OFF) sends the same CC locks | pass |
| (b) muted | ON muted and stock muted both send nothing on T1's channel; the track's resolved NOTE still moves step to step while muted ON | pass |
| (c) NOTE lock | Step 5's note = register offset − 12 + 60 (C4) | pass |
| (d) NEI | Conditions poked: T1 FILL on 1, NOT FILL on 9; T2 NEI on all 16. OFF: T2 plays 9..16 only. ON: T2 plays every step | pass |
| (e) range | 9 poked registers at NOTE 48, 6, 121: every note as the model predicts and within NOTE±12 ∩ 0..127; model: 4,000 registers × 64 steps | pass |
| (f) ARP | ARP UP, faster SPD, 2 octaves on T1 (Turing) and T3 (stock, NOTE locks = T1's phrase): identical notes and times, more notes than steps, octave-up notes present; KEY C MAJ: every T1 note in C major and T1 = T3 | pass |
| (g) LFO | LFO 1 (NOTE, its default target) DEP 24 on T1 (LOCK 127, LEN 4) and stock T2: T1 − model note = T2 − 48 on every step, swing ≥ 12 | pass |
| (h) ext clock | CLOCK/TRANSPORT RECV (poked), FA + 192 F8 at 20 ms + FC on MIDI IN: 32/64/16 steps at 1x/2x/1/2x, on T2's steps, mean step 6 clocks × factor, notes as the model | pass |
| (i) patterns | A01 T1 ON 127/16, A02 T1 OFF with trigs; A02 page shows OFF; PLAY with PATTERN+TRIG switches: bars A01, A02, A01 … A02; every A01 bar the same phrase, continuing the model; A02 stock chords on 1/5/9/13 | pass |
| (j) stock | MODE OFF wire bytes identical to stock 1.40C; T1 ON with CLOCK SEND: F8, FA, FC, tick ISRs as stock | pass |
| project | SAVE writes `#TURING_B1_P1_T1=1,127,8,<bits>,<rng hi>,<rng lo>` and `#TURING_FIRST=1`; RELOAD restores config and register exactly | pass |

Also: `diag/repro_clock.py` (F8 139, FA 1, FC 1, 36 notes, tick ISR 431×) and `diag/dl_counters.py`
(loader [21, 21], 0 errors, core-1 select at state 7 = 0) match 74/8 (`diag/octabam9/{repro_clock_9,cnt_9}.log`).

How the harness sets what the panel could not under the port (stated, not hidden): trig conditions are poked
into the pattern data; CC1's send bit (Part byte 30, bit 2) is poked because CTRL 1's knobs did not move CC1
off OFF; CLOCK/TRANSPORT RECV are poked; registers for (e) and (f) are poked into cells.

### Not tested (OCTABAM9)

Hardware; the OCTABAM8 `#TURING_T<n>` line upgrade; incoming notes and live recording; Part changes; per-track
scale mode; LFO 2/3 and other LFO targets; direct pattern jumps; pattern copy/paste; CPU load.

## REPLACE mode (OCTABAM8, 25 October 2026, local work copy)

Emulator only; nothing here ran on hardware. The sections after this one describe the earlier trig-reshaping
design (OCTABAM4 to OCTABAM74) and are kept as its record.

- **Build:** `diag/octabam8/build_octabam8.sh` (REMIX=turing on OCTABAM74's dynload transport, `BUILD=8`). The
  script first proved its base: `TAG=74 … bus` rebuilds 74's payload bit-identical (sha1 `48987645…`), once 74's
  own generated `buffers.s`/`transfer.s` are used (the tree's were regenerated on 24 Oct with other compiler
  output; copies in `diag/octabam8/platform74/`).
- **Images:** payload `out/turing_8.bin` = `out/mainos_bus.bin` sha1 `40477d4e3c080d802eda25aff1c2fb09349386c4`;
  `out/OCTATRACK_OCTABAM8.bin` sha1 `c2a3c911…146be`; `out/OCTATRACK_OCTABAM8.syx` sha1 `0187f482…30b25`.
- **Generator:** `generate.py --check` passes.
- **Sources (SHA-256):** `turing.c` `44ed69f9…7ae1`, `turing.h` `b01fad3f…6304`, `hooks.s` `3ea08c2c…d8e5`,
  `turing.s` `6828877b…ab7c`, `verify.py` `b157515a…5fdd5f`. Port `out/emu/ot_emu` `187243df…49d9` (this tree's,
  `OT_HW_RULES` on). Stock reference `out/raw/section_3_MAIN_OS.bin` `164f3122…0a84e`.

### `verify.py out/turing_8.bin`: 88/88 PASS, exit 0 (`diag/octabam8/verify8.log`)

Boot 1, fixed seed `0x13572468`: T1 (ch 1, NOT2 +7) **empty**, T2 (ch 2) a trig on every step, MODE OFF, as the
stock reference. 120 BPM.

| Check | Result |
|---|---|
| Empty T1, MODE OFF: silent | pass |
| T1 ON 127/16 (set on the page): one note a step, no NOT2, on every T2 step and only there, every note as the model predicts | pass |
| 1x: mean step 5512.5 samples (16 a bar) | pass |
| LOCK 127, LENGTH 16 repeats every 16 steps; LENGTH 5 every 5 | pass |
| T1's velocity and note length (median) equal T2's | pass |
| Trigs placed on T1 while ON (steps 1,3,5,8,11,14): still one note a step, nothing of their own | pass |
| PATTERN SCALE 2x and 1/2x: on every T2 step, mean step half / twice the 1x one | pass |
| Mute (FUNC+T1, mask bit 8 of `0x8000000c`): T1 silent, T2 goes on; T1 back after unmute; the model holds across | pass |
| MODE OFF while playing: only T1's trigs, as NOTE+NOT2 pairs on T2's steps; no Turing note; ON again: one a step; every Turing note as the model predicts | pass |
| MODE OFF while stopped: the next PLAY starts on T1's step-1 trig pair; ON while stopped: starts with a Turing note on step 1 | pass |
| LEN at its longest: STOP sends a note-off for every T1 note, the last one at STOP | pass |
| Every note-on released over the boot | pass |

Boots 2-3 (no seed, empty T1 ON): full phrases, different between the two PLAY moments, not the fixed seed's.
Boot 4 (project save/reload) and boot 5 (the page ring, knobs, TURING FIRST): as on OCTABAM6; boot 5's model
checks now take one note a step.

Boots 6-7, one panel script on stock 1.40C and on the image (T1 trigs 1,3,4,7,9,12,13,16 with NOT2, T2 every
step):

| Check | image 8 | stock |
|---|---|---|
| Every MODE OFF, 4.3 s: UART0 wire bytes | 378 B | 378 B, **identical** |
| CLOCK SEND + TRANSPORT SEND, T1 ON (image), 2.3 s: F8 / FA / FC | 153 / 1 / 1 | 153 / 1 / 1 |
| Sequencer tick ISRs over the same PLAY | 488 | 488 |
| T1 note-ons vs T2's | 21 vs 21 | |

Also: `diag/repro_clock.py out/turing_8.bin` (the 74 regression, T1 ch11 trigs, Turing OFF): F8 139, FA 1, FC 1,
36 note-ons, eDMA errors 0, core-1 selects at state 7: 0, frames stopped 0, as 74. `diag/dl_counters.py`: accepted
[21, 21], errors 0, as 74 (`diag/octabam8/repro_clock_8.log`, `cnt_8.log`).

### Not tested

The arpeggiator on a Turing track; per-track scale mode; LFOs on NOTE; NOTE/TRAN parameter locks (ignored by
design while ON); incoming MIDI notes and live recording; Part, pattern or bank changes while playing; the
sequencer driven by external clock; cycles and timing under load; hardware.

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

## The TURING page (23 October 2026, local work copy)

Emulator only; the page has not run on hardware (the rows and note path ran as OCTABAM4).

- **Build:** `OCTABAM_STATIC_STOCK=1 make image REMIX=turing BUILD=5` (no dynload platform, as OCTABAM4) gives `OCTATRACK_OCTABAM5.bin`, sha1 `7eba2a31…e166`.
- **Generator:** `generate.py --check` passes.
- **Boot 5 of `verify.py` ("page"):** fixed seed `0x2468ace1`, T1 on channel 1 with NOT2 and T2 on channel 2.
  - **Navigation:** AMP shows stock ARP, and AMP again shows TURING. The values the stock widgets are called with match the active track's settings.
  - **Knobs:** A/B/C set T1, then T2 after it is selected; D and F do nothing.
  - **No side effects:** no MIDI OUT bytes during the knob turns, and no ARP Part byte changes.
  - **SETUP still works:** a double tap opens MIDI ARP SETUP, and NO closes it onto TURING. AMP returns to ARP.
  - **Notes:** every note of both tracks matches the model.
- **Boot 4** now sets the saved value through the page.
- **LCD captures:** `diag/turing_page_shots.py` in the work copy, which also writes `media/ot-page-*.png`.

## AMP's page ring and TURING FIRST (23 October 2026, local work copy, OCTABAM6)

Emulator only; nothing here has run on hardware.

- **Build:** `OCTABAM_STATIC_STOCK=1 make image REMIX=turing BUILD=6` (no dynload platform) gives `OCTATRACK_OCTABAM6.bin`, sha1 `4daf4e52…d05563`. Its payload `out/mainos_bus.bin` (sha1 `aefc9a3f…e19a0`) is byte-identical to the one tested.
- **Generator:** `generate.py --check` passes.
- **`verify.py` on that payload: 55/55 PASS, exit 0.** Every track setting is now made on the TURING page; the MIDI SEQUENCER rows that did it are gone.
  - **Boot 5, TURING FIRST OFF:** AMP from SRC shows ARP; double taps go ARP SETUP, TURING, ARP (the wrap). A press from TURING or ARP SETUP shows ARP. FUNC+AMP opens ARP SETUP from ARP and from TURING, and FUNC+AMP again or NO closes it onto ARP.
  - **Boot 5, knobs:** knob A switches T2 alone OFF and ON. A played run with T2 OFF gives its NOTE while T1 follows the model.
  - **Boot 5, TURING FIRST ON (the row):** AMP shows TURING; double taps go ARP, ARP SETUP, TURING. A press from ARP or ARP SETUP shows TURING. A track change keeps TURING, and so does MIDI to audio and back.
  - **Boot 4:** a new project starts with TURING FIRST OFF. SAVE writes `#TURING_T1=1,127,8` and `#TURING_FIRST=1`, and RELOAD restores both, after which AMP shows TURING.
- **`diag/repro_clock.py`:** the same numbers as OCTABAM4 rerun beside it: 431 tick ISRs, F8 139, FA/FC, 36 ch11 note-ons, 0 eDMA errors.
- **LCD captures:** `diag/turing_page_shots6.py` (writes `diag/octabam6/*.png` and `media/ot-page-*.png`, `media/ot-row-first.png`).
