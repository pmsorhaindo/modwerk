# Turing Machine

Version: 0.5.0-experimental · author: [pmsorhaindo](https://github.com/pmsorhaindo).
Private fork draft, not a published or hardware-qualified module.

MODE and register anchors live in module-owned DRAM and saved project comments. **SAVE before a power
cycle or reinstall:** unsaved edits are lost. The module never reads or writes its former battery table,
settings, test-seed or RNG addresses; the base diagnostics log and FX map keep their own storage.
This remains an experimental draft, with no hardware qualification.

## Overview

A live looping shift register for each Octatrack MIDI track, inspired by Music Thing Modular's Turing Machine.
The stock sequencer advances it on the track's steps, with the instrument's transport, speed and swing.
LOCK changes how often the loop mutates; LEN sets its length, SCAL its pitch range around NOTE, and DENS its rests.
LEN 2–7 loops whole notes; LEN 8–64 loops bits. The engine and its random sequence retain the previous design.

This version is a module-only USB runtime package for **Modwerk base 0.7.9 or later**, built from stock OS 1.40C. It replaces the arpeggiator.
SRC (NOTE/VEL/LEN), LFO, FX1 and FX2 stay stock. Every stock audio effect, including SPRING REV, is retained.
The base and existing effect packages are unchanged. The old all-in-one/card build route is superseded.

## Controls

In MIDI NOTE SETUP (FUNC+SRC, double-tap SRC, or double-tap the current track), choose TURING with DOWN and YES.
The choice belongs to the **Part and MIDI track**. Close setup and press AMP.

| Control | Main page | Scope |
| --- | --- | --- |
| A | MODE OFF/ON | Pattern and track |
| B | LOCK 0–127: 64 random, 96–127 locked, 25 a slow slip; one per tick | Part and track |
| C | LEN 2–64 | Part and track |
| D | SCAL 0–127: NOTE only through a four-octave span; 64 is two octaves | Part and track |
| E | DENS 0–127: silence through a note every step | Part and track |
| F | Unused | |
| Push A | WRITE the current phrase into ordinary trigs; turning A while pushed cancels WRITE | Pattern and track |

FUNC+AMP opens page 2: **A SCALE** (OFF, MAJ, MIN), **B ROOT** (C–B); C–F are unused. **Release FUNC before editing SCALE/ROOT.** NO returns to page 1.
The inherited FUNC+LOCK shortcut is retired; holding FUNC yields the page and encoders to stock.
The framework also toggles page 2 on an AMP double tap. WRITE works on the main page only; YES does not WRITE.
Holding a trig or scene shows stock's page so its locks remain reachable.

MODE and the 64-bit register remain per pattern. **Patterns sharing a Part now share LOCK, LEN, SCAL and DENS**,
and SCALE/ROOT. Turning MODE off restores the pattern's own trigs while the Part still chooses TURING.
Choosing OFF in NOTE SETUP leaves the generator and resets the arpeggiator through the framework.

The own quantizer runs after stock TRAN and its range check. It matches the 24 stock major/natural-minor keys:
an out-of-key note moves one semitone down; out-of-range notes and a negative snapped note are dropped.
ROOT is absolute and does not follow NOTE or TRAN. Scale OFF bypasses stock KEY on generator tracks too.
Old KEY/TRAN bytes survive migration, but KEY is no longer the generator's quantizer. `scale.c` calls the shared SDK `modwerk_scale_snap`: catalogue ID 1 for MAJ, 6 for natural MIN.
At note zero, it preserves the historical negative-result drop rather than the SDK's upward boundary fallback.
No richer scales, root following, or one-note arp are implemented.

## Usage

1. Set a MIDI track's channel in stock NOTE SETUP, choose TURING there, then close setup and press AMP.
2. Turn MODE ON and press PLAY. Set DENS 127 for every step, and LOCK 127 to repeat a phrase.
3. Change LEN and SCAL; use FUNC+AMP, release FUNC, then choose SCALE and ROOT. NO returns to the main page.
4. Push and release A to WRITE. MODE OFF then plays the written trigs through the same quantizer.
5. STOP releases the sounding note. Choose OFF in NOTE SETUP to return that Part/track to stock operation.

WRITE preserves the step's other locks, clears conditions/microtiming/retrigs and leaves MODE and the live register
unchanged. It marks its NOTE centre in spare lock bytes 30–31, as before. Muting silences output while the register
continues following the track. New trigs, note-offs, channels, clock and transport remain stock's responsibility.

## MIDI messages and timing

Turing consumes no incoming MIDI messages and assigns no CCs or SysEx commands. Notes, controllers, pitch bend, program changes, SysEx, clock and transport continue through stock handling. Generated notes use the track's stock channel and routing, NOTE centre, VEL and LEN; each enabled track schedules at most one note per step, or a rest. Stock handles note-offs, overlap, mute and STOP, with no separate clock or output queue. Timing and load on a unit remain unmeasured. Use only one incoming clock port during testing.

## Compatibility and limitations

Octatrack MKI/MKII, OS 1.40C. No hardware activity is authorized for this draft. Emulator results are not hardware
or physical reboot evidence. USB install/Keep/Undo/removal and simultaneous-module qualification remain open.

**Migration:** after a complete legacy project load, any enabled Turing pattern assigns its Part/track to TURING
unless another generator already owns it. The lowest-numbered enabled pattern supplies that Part's old settings
when patterns disagree. The mask is written directly, preserving TRAN and copying old KEY to own SCALE/ROOT.
The saved `#TURING_S2=1` marker and retained S2 flag prevent later legacy lines from overriding a Part choice.
MODE and register comment lines still load; `#TURING_FIRST` is ignored and never written.

**Old arp-MODE projects change:** stock arp MODE is forced off, including a fired step's MODE lock. Ratchets,
octave runs and stock arp note offsets are lost. Patterns sharing a Part with differing old settings also change.
KEY-only projects with matching shared settings should retain pitches; tests and exceptions are in TESTING.md.

**Stock firmware:** projects still open; stock skips the Turing comment lines. The generator mask and signed-valid
arp note bytes are stock-visible: enabling the arp under stock uses a partial step mask and unusual note offsets.
Keep the arp off there. The original KEY remains available to stock. No stock code or firmware is shipped here.

Copying or clearing patterns does not copy or clear their separate Turing registers. Incoming MIDI, dense traffic,
Part changes under load, runtime replacement, removal while playing, and physical reboot are not yet qualified.

## Tests and measurements

Build locally with the repository's pinned Elekloader checkout; output stays outside Git:

```sh
python3.11 -B sdk/octatrack/modules/turing-machine/generate.py --check
npm run module:dev -- turing-machine --build-only --out /private/turing-machine.mwrm
```

This command only builds. The private `.mwrm` uses the same package format and validator as the browser USB installer on base 0.7.9. It is not in the public catalogue: use the developer build/trial tools after exact-build hardware testing is authorized. Do not install this untested candidate on a unit as part of software verification.

`runtime.json` contributes to `ot_midi_generators` and subscribes to `ev_midi_note_key` and `ev_modules_ready`. The base hosts the generator page and quantizer event. On installation after a project has already loaded, the existing modules-ready event reads only Turing comments from `project.work`; normal SAVE/RELOAD keeps the stock project-file callbacks. No module-owned battery range is used.

`test_port.py` compares fixed-seed register transitions and notes with the prior implementation when `TURING_REFERENCE_DIR` is supplied. Its scale check executes the actual shared SDK and wrapper on ColdFire. `emulator_test.py` installs the `.mwrm` through the real backend of a private browser-built base on every test boot, including saved-card fresh boots. `verify_arpgen.py` adapts the existing engine tests; only the explicitly retired FUNC UI expectations are replaced. The old reference worktree remains unchanged.

See TESTING.md for commands, exact results and remaining gates. No chip-cycle, CPU-load or audible-output claim is made.

## Authorship and licences

Original Turing implementation by pmsorhaindo, MIT (LICENSE). Modwerk's MIDI-generator host is supplied by the base. Elekloader and its core remain separately licensed upstream tools,
pinned by the repository's kit. The shared scale SDK credits Tim Hastie and Sam Banks; no extracted firmware
routines or tables are included. Music Thing Modular's name describes the inspiration, not an endorsed product.

## Screens and audio

The earlier capture descriptions refer to the previous page ring. This draft does not ship current screenshots.
New captures and sound/hardware qualification remain pending. No audio preview is claimed.
