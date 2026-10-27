# Turing Machine Sequencer — Feasibility Study

**Date:** 8 October 2026  
**Requester:** Michael (pmsorhaindo)  
**Status:** Feasibility analysis complete; implementation not started  
**Revision 2 (8 October 2026):** quantizer integration is the target, reached in stages (§2.3, §5). Corrects revision 1's conflict analysis (§3.1), frame timing (§1.4) and replaces day estimates with technical scope (§5).  
**Revision 3 (8 October 2026):** M0 done in the emulator. The MIDI-track note hook is found and proven with a patched scratch image (§7). The design sections are updated to match.

## Executive Summary

A Turing machine sequencer mode for Octatrack MIDI tracks is **feasible**. No module in this repository yet generates or transforms MIDI notes (`docs/module-guides/midi-usb.md`), so the hook had no worked example. M0 has now located it under the ColdFire emulator: a 6-byte detour at `0x4009fb2e`, inside the stock MIDI-track note-on loop, where the four resolved chord notes of a firing trig sit in a stack array before the track's TRAN is added and the note is sent. A patched scratch image transposed the notes there and MIDI OUT matched stock byte for byte apart from the moved notes, note-offs included (§7). The cleanest design is a **ColdFire-only module** (`Kind.CF_PATCH`, `category: midi-usb`, `compatibility.location: MIDI tracks`) that hooks the point where the sequencer emits a MIDI track's note, following Euclid's transport/timing pattern.

**Recommended approach:** Per-MIDI-track state with a probability control, loop length, note range/scale controls, and output routing (note/CC/velocity). The module would hook the MIDI trig execution path to override the trig's note, and expose controls first as project-level SEQUENCER rows (quantizer's SCALE/ROOT/GLIDE pattern), later on a per-track page.

**Quantizer integration is the goal and is natural:** quantizer does not touch MIDI-track output at all; it already exports a pinned scale accessor (`SCALE_AT = 0x400d2ca8`, `jmp qz_scale_mask`) that the FM Synth module consumes. The Turing machine can become a second consumer of that same contract, so one SCALE/ROOT setting covers audio tracks, synth chords and Turing notes. Stages: own internal scale table first, then an optional link to quantizer's mask, then shared UI.

**Key risks:** Low for hardware and projects (no DSP, safe-off defaults). The real build constraint is **MIDI Scenes, which Modwerk only builds standalone** today; the Turing machine cannot ship beside it until MIDI Scenes is relocatable.

## 1. Existing Module Architecture Analysis

### 1.1 MIDI Track Modules

#### **Quantizer** (`quantizer`)
- **Type:** `Kind.CF_PATCH` with DRAM unit + ROM core
- **Hook points:**
  - `qz_knob` / `qz_plock`: PTCH knob and parameter lock snapping (detours at knob/lock editing)
  - `qz_chrom`: CHROMATIC key press interception, snaps to scale before note generation
  - `qz_ld_entry` / `qz_wr`: Project file save/load for SCALE/ROOT/GLIDE settings
  - Menu rows via `TableGrow` in PROJECT > CONTROL > SEQUENCER
- **State:** Battery-RAM bytes (`NV_SCALE`, `NV_ROOT`, `NV_GLIDE` at `0x100b14ec-ee`)
- **CPU:** Minimal; runs only on keyboard events and parameter edits
- **Scope:** audio tracks only. It snaps the PTCH knob/locks of STATIC/FLEX/PICKUP tracks and CHROMATIC keys; "the MIDI note a key sends out stays the key's own (72 + key)" (`upstream/quantizer/quantizer.s` header). It never touches MIDI-track sequencer output.
- **Exported contract:** `scale.s` is a 6-byte trampoline pinned at `SCALE_AT = 0x400d2ca8` (`jmp qz_scale_mask`). `qz_scale_mask` (`core.s`) returns in `d0` the 12-bit pitch-class mask of SCALE rotated by ROOT (bit k = pitch class k, C = 0; `0` = OFF) and clobbers only `a0`/`d0`. FM Synth's `poly.s` (`po_snap`) already calls it to snap chord notes. Settings are battery-RAM bytes `NV_SCALE`/`NV_GLIDE`/`NV_ROOT` (`0x100b14ec..ee`) plus `#SEQUENCER_SCALE`/`#SEQUENCER_ROOT` project-file lines.
- **Key insight:** Shows that project-wide sequencer settings can be added as SEQUENCER rows and persisted (battery RAM + project-file comment lines). This is project-level, not per-Part, storage. Its scale accessor is the integration point for the Turing machine (§2.3).

#### **CC Map** (`cc-map`)
- **Type:** `Kind.CF_PATCH`, ColdFire cave (floating allocation)
- **Hook points:**
  - MIDI dispatch table entry `0x400d64a0[0xB]` repointed to the cave
  - Intercepts CC 62-73, maps to FX1/FX2 page-2 parameters
- **State:** None (stateless CC transformation)
- **CPU:** Minimal; runs only on incoming MIDI CC messages
- **Key insight:** Shows that MIDI message processing can be intercepted at the dispatch level. For outgoing MIDI from the sequencer, we'd need a different hook point (trig execution, not incoming CC).

#### **MIDI Scenes** (`midi-scenes`)
- **Type:** `Kind.CF_PATCH`, fixed-address author release
- **Hook points:**
  - Multiple detours in MIDI parameter editing paths
  - Scene crossfader integration
  - Parameter lock system (reads scene-held values, publishes crossfaded output)
- **State:** Scene locks per MIDI parameter per track, stored in Part
- **CPU:** Runs per-frame to publish crossfaded values
- **Key insight:** The only existing work that touches the MIDI-track trig path (its author documents "CC-before-note ordering", "preservation of active trig locks" and trig snapshots). But it is a fixed-address author recipe with 85 guarded regions and no relocatable symbols, so its knowledge is not reusable as hooks, and Modwerk builds it **standalone only** (`src/catalog/selection-conflicts.ts`, `midi-scenes-standalone`).

### 1.2 Sequencer-Integrated Effects

#### **Euclid** (`euclid`)
- **Type:** `Kind.HYBRID` (ColdFire control + DSP audio)
- **Hook points:**
  - `eu_frame_hook` (`0x4000d562`): Publishes modulated cutoff after stock scene/LFO processing
  - `eu_start_hook` (`0x4009c3d4`) / `eu_resume_hook` (`0x4009c4d4`): PLAY/STOP transport reset
- **Timing source:** Reads stock sequencer records:
  - Tempo: `tempo24` (halfword 31 of sequencer record)
  - Track speed, scale, length: read once per track
  - Swing: reads track mask and amount, including SWING ALL changes
- **State:** `EuClock` (20 bytes shared), `EuState` (164 bytes per instance), in DRAM
- **CPU:** Integer rhythm engine runs per-frame; skips when stopped/inactive
- **DSP:** Filter/amplitude modulation (`filter.asm`)
- **Key insight:** Demonstrates transport integration (PLAY resets phase, STOP returns to base), tempo following, and per-frame control processing. Shows the pattern for reading sequencer timing state.

### 1.3 Hook Point Locations

From the modules examined:

| Hook Purpose | Address | Module Using It | Notes |
|--------------|---------|-----------------|-------|
| CHROMATIC key press | Various in key handler | Quantizer (`qz_chrom`) | Intercepts before note generation |
| MIDI CC dispatch | `0x400d64a0[0xB]` | CC Map | Incoming MIDI only |
| MIDI parameter editing | Multiple | MIDI Scenes | Scene-lock integration |
| Frame publish (post-scene/LFO) | `0x4000d562` | Euclid (`eu_frame_hook`) | After all modulation |
| PLAY transport start | `0x4009c3d4`, `0x4009c4d4` | Euclid (both paths) | Reset timing state |
| Project file load/save | Multiple | Quantizer, MIDI Scenes | Custom data persistence |

**Key finding:** No examined module or firmware document (including upstream octabam's `docs/firmware/MIDI.md`) covers MIDI-track note *output*. Quantizer intercepts user input, and MIDI Scenes works at the parameter level. M0 found the output hook by tracing: the MIDI-track note-on chord loop at `0x4009fb2e` (§2.2, §7).

### 1.4 Where Code Runs

- **ColdFire CPU** (`-mcpu=5475` or `-mcpu=5407`):
  - All MIDI processing (sequencer, keyboard, CC, note output)
  - Parameter editing, scene/LFO modulation
  - Project save/load
  - Frame-rate control processing
  - **Timing:** the frame interrupt runs every 362.8 µs (16 samples at 44.1 kHz), the frame the performance guide budgets against
  - **Budget:** Unknown worst-case for MIDI processing; perf guide requires ≤10% frame overhead for new modules

- **DSP56300** (dual core, payload A serves tracks 5-8, payload B serves tracks 1-4):
  - Audio effects only (FX1/FX2 processing)
  - **Not involved** for MIDI track output
  - A Turing machine on MIDI tracks would not use the DSP at all

### 1.5 Timing and CPU Constraints

From `docs/module-guides/README.md` performance requirements:

- **ColdFire modules:** Benchmark against stock image under the same flood; may add at most **10% of a 362.8 µs frame** to the interrupt and 10 points of idle time
- **Cycle counting:** Static floor + worst measured case (with knobs moving)
- **Stress test:** MIDI flood at ~1040 messages/sec, 240 BPM, 60+ seconds
- **Frame budget:** `cfmeter.py` measures longest frame interrupt and idle time

**Analysis for Turing machine:**
- Per-frame shift-register updates: minimal (8-16 bit shifts, random bit generation)
- Note output: work happens only when a trig fires. At 240 BPM a 1x track steps 16 times a second; eight MIDI tracks at 2x speed are 256 steps a second, under 0.1 per 362.8 µs frame
- Estimated CPU: **Low to moderate**; much lighter than MIDI Scenes' per-frame crossfader interpolation across all parameters

## 2. Turing Machine Feasibility

### 2.1 Functional Requirements

From the request:
1. **Per-MIDI-track mode** that turns the track into a Turing machine
2. **Shift register** of configurable length (2-16 steps)
3. **Probability/"lock" control** for bit mutation (fully random → slowly mutating → locked loop)
4. **Note output** from register value, with:
   - Scale quantization (root/scale selection)
   - Range control (min/max note)
5. **Optional:** CC or velocity output
6. **Live playability:** turning probability knob freezes/unfreezes patterns in real-time

### 2.2 Proposed Design

#### Architecture: `Kind.CF_PATCH`
- **ColdFire-only module** (no DSP code)
- DRAM unit for state storage + ROM core for boot/defaults
- Similar structure to quantizer: DRAM unit with pinned trampoline for performance-critical path

#### Hook Points

**Required hooks:**

1. **MIDI-track note hook (found in M0, §7)**: `0x4009fb2e`, 6 bytes `1212 7101 76ff` (`move.b (%a2),%d1; mvs.b %d1,%d0; moveq #-1,%d3`), SHA-256 `c51d1ea289bd31b3ae87a587ac9c17dd9a97ffebbe73d44bb72a3605d978845a`.
   - It is the head of the chord loop inside the stock MIDI sequencer routine at `0x4009f794` (`linkw %fp,#-104`). `d7` = track (0–7), `d4` = chord slot (0 = NOTE, 1–3 = NOT2–NOT4), `a2` → the slot's resolved note byte in a stack array at `%fp@(-4)` (`-1` = no note), `a5` → the track's record. Measured: one pass per slot per firing trig per track.
   - The loop is re-entered only by `bne.w 0x4009fb2e` at `0x4009fd36`; nothing branches into the displaced bytes, and none of them is PC-relative.
   - After the hook, stock adds `TRAN` (`a5@(556)` − 64) and a per-track offset (`0x46c7a124[t]`), optionally remaps the pitch class through `0x400d80a0` (driven by a byte at `+49` of another per-track record; what that setting is, is unverified), suppresses a note already sounding on the channel (`0x46c78152[chan·128 + note]`), sends `9n note vel` through the 3-byte queue `0x40010bc8`, and records the sent status and note at `0x46c77a16/0x46c77a1a + 32·t (+8·slot)`. The note-off path (`0x4009f8a2`) sends from that record.
   - **Action:** at `d4 == 0` on an enabled track, replace NOTE with the generated note and shift NOT2–NOT4 by the same interval (dropping any that leave 0–127). Then run the displaced instructions and `jmp 0x4009fb34`. `d0` is free (the displaced `mvs.b` overwrites it).
   - **Fallback no longer needed** for v0.1.

2. **Transport (PLAY/STOP)**: do **not** reuse Euclid's sites
   - Euclid already detours both PLAY paths (`0x4009c3d4`, `0x4009c4d4`) and the post-scene/LFO frame site (`0x4000d562`). The build refuses two modules claiming one detour site, so reusing them would make Turing and Euclid mutually exclusive.
   - Preferred: no transport detour at all. In the trig hook, edge-detect the stock PLAYING word that Euclid's hook stores (`0x800065b8`) and reset when it goes from stopped to playing. Euclid itself shows that word is the PLAY anchor.
   - Alternative: a shared transport bridge that both modules chain from (the `Override`/bridge mechanism in `schema.py`), which changes Euclid and needs owner agreement.
   - PLAY: reset the read position; the register contents survive (as the Music Thing module does, and as Euclid's LOOP values do). STOP: send note-offs for any note the module emitted; keep the register.

3. **No frame hook in v0.1**
   - The register advances only on the track's own trigs, so it needs no per-frame work. That also follows `sequencing.md`: no clock of its own.

4. **Project file save/load** (pattern: quantizer's `qz_ld_entry`, `qz_wr`)
   - Save: shift register state, current position, enabled flag
   - Load: restore state or initialize fresh

#### State Storage

```
Per-MIDI-track state (~32 bytes per track):
  - uint16_t shift_register;      // 16-bit shift register
  - uint8_t  position;             // current position (0-15)
  - uint8_t  length;               // loop length (2-16)
  - uint8_t  probability;          // lock amount (0-127)
  - uint8_t  enabled;              // mode on/off
  - uint8_t  scale;                // scale index (reuse quantizer's scales)
  - uint8_t  root;                 // root note (0-11)
  - uint8_t  note_min;             // minimum MIDI note
  - uint8_t  note_max;             // maximum MIDI note
  - uint8_t  output_mode;          // 0=note, 1=CC, 2=velocity
  - uint8_t  cc_number;            // CC# if output_mode=1
  - uint32_t rng_state;            // xorshift32 RNG state
```

**Storage location:**
- Runtime register state: DRAM unit (depacked at boot, like quantizer), 8 MIDI tracks × ~32 bytes = 256 bytes.
- Settings: the only persistence path with a precedent is quantizer's, which is **project-level**: battery-RAM bytes plus `#…` comment lines in the project file that the stock loader skips. Per-Part or per-track settings that follow Part save/reload have **no precedent** among the relocatable modules (MIDI Scenes stores Part data, but as a fixed-address recipe). v0.1 therefore uses project-level settings; per-Part storage is an open research item (§5, M4).
- The register contents themselves are runtime state, not project data, in v0.1 (Euclid's LOOP values take the same position). Saving a "frozen" phrase with the project is a later feature.

#### Controls and UI

**Menu location:** PROJECT > CONTROL > SEQUENCER (new rows below quantizer's GLIDE)

```
TURING MODE:    [OFF | T1 .. T8]     which MIDI track runs the register (v0.1: one track)
TURING LOCK:    [0-127]              flip chance; 64 = fully random, 127 = locked loop
TURING LENGTH:  [2-16]               loop length in steps
TURING LOW:     [MIDI note]          bottom of the note range
TURING SPAN:    [1-48 semitones]     width of the note range
TURING SCALE:   [FOLLOW | CHROMATIC] stage 2+: FOLLOW reads quantizer's SCALE/ROOT
TURING OUTPUT:  [NOTE | CC | VEL]    later milestone
```

These are project-level rows, like quantizer's. They are reachable without new gestures, which matters for review, but a SEQUENCER menu row is not a live control. The live "turn toward lock to freeze a phrase" gesture needs LOCK on an encoder of the MIDI track's own pages (ARP or a CTRL page, where MIDI Scenes works), which also makes it lockable and scene-morphable. That is a change to a stock MIDI page, so it falls under "minor change to a stock flow" in `docs/module-guides/README.md` and needs the owner's agreement before it is built (§2.5).

#### Algorithm

The Music Thing Modular Turing Machine rotates a loop of `length` bits once per clock. The bit leaving the end comes back in at the start, inverted with a chance set by the big knob. Centre is fully random, fully clockwise never flips (a locked loop), and fully anticlockwise always flips, which locks a loop of twice the length with the second half inverted. An 8-bit window of the register drives the output.

```c
// Called once per trig of the enabled MIDI track, from the trig hook.
// Returns the MIDI note that replaces the trig's NOTE.
typedef struct {
    uint16_t bits;      // the loop; only the low `length` bits are used
    uint32_t rng;       // xorshift32 state, seeded per track
} TuringState;

uint8_t turing_step(TuringState *s, const TuringParams *p, uint16_t scale_mask) {
    unsigned n = p->length;                       // 2..16, clamped by the caller
    unsigned out = (s->bits >> (n - 1)) & 1;      // the bit leaving the loop
    // LOCK 127 -> flip chance 0; LOCK 64 -> 1/2; LOCK 0 -> always flip.
    unsigned flip_threshold = (127u - p->lock) * 256u / 127u;   // 0..256, compared with a byte
    if ((xorshift32(&s->rng) & 0xff) < flip_threshold) out ^= 1;
    s->bits = ((s->bits << 1) | out) & ((1u << n) - 1);

    // Read the low 8 bits (fewer for n < 8) as 0..255.
    unsigned v = n >= 8 ? (s->bits & 0xff) : (s->bits << (8 - n)) & 0xff;
    unsigned note = p->low + (v * p->span) / 255u;
    if (scale_mask) note = snap_to_mask(note, scale_mask);   // nearest pitch class in the mask, ties down
    return note > 127 ? 127 : note;
}
```

`snap_to_mask` uses the same convention as quantizer's chromatic snap (nearest degree, ties to the lower), so a Turing note and a played key agree. `scale_mask` comes from the integration stage in force (§2.3); `0` means chromatic.

### 2.3 Integration with Quantizer (the target, in stages)

Integration is the aim, approached incrementally. Revision 1 called the two modules conflicting because "both modify MIDI output"; that was wrong. Quantizer acts only on audio tracks (§1.1). Nothing in either module writes the other's sites, so there is **no technical conflict to declare**. The question is only how the Turing machine gets its scale. There is a contract for that already: `SCALE_AT`, consumed today by FM Synth.

**Who provides the scale in Modwerk.** Either `quantizer`, or `synth`, which bundles its own copy of quantizer and is refused beside it (`synth-machine-conflict` in `src/catalog/selection-conflicts.ts`). Both put `jmp qz_scale_mask` at `SCALE_AT`. Without either, `SCALE_AT` is stock bytes in a zero run, so **calling it without a provider would execute garbage**. Every stage below is built around that fact.

| Stage | What the Turing machine does for scale | Build relationship to quantizer | What it proves |
| --- | --- | --- | --- |
| **S0** (v0.1) | Chromatic only: no scale. | Independent; no `requires`, no `conflicts`. Builds with or without quantizer. | The trig hook and register work alone. |
| **S1** | Its own small mask table (a handful of scales + root) in its own unit, using quantizer's mask format (12-bit pitch-class mask, rotated by root) and the same snap rule. | Still independent. | The snap path and UI, with no cross-module coupling. Code that S2 replaces is small and isolated. |
| **S2** | **Optional link to quantizer's mask.** When a scale provider is in the image, call `SCALE_AT`; otherwise fall back to S1's table (or chromatic). One SCALE/ROOT in PROJECT > CONTROL > SEQUENCER then drives audio-track PTCH, CHROMATIC keys, FM Synth chords and Turing notes. | Optional dependency, resolved at build time (see below). | Shared settings; the integration the owner and user want. |
| **S3** | Shared UI and persistence: a FOLLOW/OWN choice, Turing rows placed beside SCALE/ROOT/GLIDE, and a check that both modules' project-file lines and battery-RAM bytes coexist on save/load/reboot. | Same as S2. | No duplicated settings a musician has to keep in sync. |

**How S2 can link optionally.** Two mechanisms already exist and either fits:

1. *Build-time symbol with a fallback* (preferred). cc-map declares `defsyms` (`CC_MODEDEF1/2`) that resolve to mode-defaults' exported globals when that module is in the image and to a stock `rts` otherwise (`sdk/octabam/tools/build/build_bus.py`, the `_exports` / `_defsym_ovr` resolution beside the "ROM-placed linked units go FIRST" comment). `qz_scale_mask` is a global of quantizer's ROM unit `core.s`, so a Turing ROM stub could name it the same way and fall back to its own "return S1 mask" routine. Caveat: quantizer's own notes say "a ROM unit cannot name a DRAM symbol and a DRAM unit cannot name a ROM one at link time". That is why `SCALE_AT` is a fixed address. The resolving call must therefore sit in a small ROM stub of the Turing module, not in its DRAM unit. The exact fallback form, a symbol default that points at the module's own routine, is new for this mechanism and needs checking against `build_bus.py` and the browser engine (`src/engine/`), with `module:verify` proving they agree.
2. *`requires`*. `schema.Module.requires` makes the ledger refuse a remix without the named module. That turns S2 into a hard dependency on quantizer (or synth), which is simpler but forces users to install quantizer to get Turing. Note that `requires` is checked by the native ledger; this study found the browser composer enforcing `requires` only for Digitakt/Digitone `.elemod` files (`src/engine/elektron/elemod.ts`). For an Octatrack module, browser enforcement needs confirming or adding in `src/catalog/selection-conflicts.ts`.

A runtime probe (compare the bytes at `SCALE_AT` against `jmp qz_scale_mask`) would also work but reads like a workaround and should not be the plan.

**Pinned addresses are a shared contract.** quantizer's manifest says "SYNTH MACHINE reads the pinned addresses, so a pin that moves them needs both modules bumped together." Turing becomes a third party to that rule, which should be written into quantizer's README when S2 lands.

### 2.4 Testing Strategy

Following the module guides:

1. **Emulator testing, no hardware** (`tools/emu/ot_emu`, the ColdFire port):
   - Fixture projects from `ot_spec.py` with MIDI tracks, trigs and NOTE locks, written into every Part of every bank.
   - `--sequencer --frames N --midi-out <file>` captures the MIDI OUT bytes, so the generated notes, their note-offs and the LOCK behaviour can be checked byte by byte in a gate (`verify_turing.py`), the way `verify_ccmap.py` and `verify_euclid.py` pin their modules.
   - `--scenario` forks several runs from one load: stop mid-note, Part change, pattern change, tempo change.
   - Project save/load/reload under the port (`--card-rw`). This proves project loading, not power-cycle survival (`ADD_A_MODULE.md`).

2. **Browser flow:** `npm run dev`, select the module in the configurator, build from a local 1.40C file. `npm run module:verify` proves the browser builder reproduces or refuses exactly what native octabam does, alone and beside every other module. The browser never executes the module, so it proves composition, not behaviour.

3. **Hardware testing** (required before release unless the owner waives it for that exact version):
   - External MIDI receiver (synth, DAW)
   - Live probability knob tweaking (freeze/unfreeze patterns)
   - Multi-track stress test (8 MIDI tracks with Turing enabled)
   - Part/project save/reload
   - Pattern changes, tempo changes

4. **Performance benchmarking** (`tools/harness/cfmeter.py`):
   - MIDI flood at 240 BPM, 60+ seconds
   - Measure frame interrupt overhead
   - Must be ≤10% of 362.8 µs frame budget

### 2.5 Open Questions for Maintainer

1. **The note hook at `0x4009fb2e` (found in M0):**  
   Should it be recorded in octabam's firmware notes (`docs/firmware/MIDI.md` upstream) when the module lands, with the trace method of §7?

2. **Optional or required scale provider (stage S2):**  
   Should Turing link to quantizer's `SCALE_AT` optionally (symbol with fallback, preferred) or declare `requires` quantizer? If optional, is extending the `defsyms` fallback to point at the module's own routine acceptable in `build_bus.py` and `src/engine/`?

3. **Live LOCK control on a MIDI page:**  
   Is putting LOCK (and later LENGTH) on an encoder of a stock MIDI track page acceptable as a documented minor change to a stock flow, and which page: ARP setup, or a CTRL page?

4. **Shift register initialization:**  
   On first enable: seeded random (per track, like Euclid's `identity`-seeded RNG) or empty? Should PLAY reset the read position only, as proposed?

5. **Transport without Euclid's sites:**  
   Is edge-detecting the PLAYING word acceptable, or would the owner prefer a shared PLAY bridge that Euclid and Turing both chain from?

6. **Quantizer's pinned contract:**  
   May a third module depend on `SCALE_AT`, with the "bump together" rule extended to it?

## 3. Conflicts and Risks

### 3.1 Module Conflicts

| Module | Relationship | Severity | Plan |
|--------|--------------|----------|------|
| **Quantizer** | No shared sites. Quantizer acts on audio tracks only; Turing on MIDI-track output. Integration target: Turing consumes quantizer's `SCALE_AT` mask. | None as a conflict; integration work | S0/S1 independent; S2 optional link; S3 shared UI (§2.3). |
| **FM Synth** (`synth`) | Bundles its own quantizer copy, so it also provides `SCALE_AT`. | None | Treat as a scale provider in S2; test both providers. |
| **MIDI Scenes** | Built standalone only in Modwerk (`midi-scenes-standalone` refusal), and its fixed regions overlap allocations every checked companion uses. It is also the one module that touches the MIDI-track trig path. | **Blocking for combination** | Turing cannot ship beside it. Rule enforced by the existing refusal; no new conflict entry needed. Revisit if MIDI Scenes becomes relocatable. |
| **Euclid** | Owns both PLAY detour sites and the frame-publish site. | Conflict **only if** Turing reuses those sites | Avoid them (edge-detect PLAYING; no frame hook). Then no conflict. |
| **Menu space** (`module-menu-space`) | Mini Verb + Tape Echo + Euclid + Repitch + Scale Quantizer already exhaust chooser/menu space together. Turing adds SEQUENCER rows (a `TableGrow`, as quantizer's). | Unknown until measured | `module:verify` will show whether Turing's rows fit beside that set. If not, the refusal grows to include Turing. |
| CC Map | Incoming CC 62–73 only; Turing emits notes. | None expected | Verify that Turing's note-out does not pass through CC Map's dispatch cave. |

**Recommendation:** `compatibility.conflicts: []` at v0.1. The real build-level exclusions (MIDI Scenes standalone; menu space, if measured) are expressed by existing refusals. Do not add a quantizer conflict; that would block the integration path rather than stage it.

### 3.2 Hardware and Safety Risks

**Risk level: LOW**

- **No audio processing:** No DSP code, no risk of clipping/DC/aliasing
- **No firmware extraction:** Uses standard hook/detour mechanism
- **Bounded CPU:** Per-trig execution only; under 0.1 trigs per frame even with eight 2x tracks at 240 BPM
- **Safe defaults:** Enabled = OFF by default; no output until user enables and configures
- **Project compatibility:** v0.1 adds only project-level settings (battery RAM + skipped `#` project-file lines, quantizer's pattern); old projects load with Turing OFF, and a project saved with Turing loads on stock (the stock loader skips the lines)

**Potential issues:**
- **Stuck notes: largely retired by M0.** The stock note-off is sent from the note recorded *after* the hook ran (`0x46c77a1a + 32·t`), so a note replaced at `0x4009fb2e` is the one that is switched off. The spike confirmed matching `9n kk 00` for every replaced note. One trap remains, also measured: NOT2–NOT4 are precomputed from the original NOTE, and a slot equal to NOTE is dropped as a duplicate. Replacing NOTE alone made the old note sound as an extra voice. The module must shift every chord slot by the same interval. The midi-usb checklist items (stop mid-note, Part/pattern change, bypass, removal) still need their own runs.
- MIDI output flood → **Mitigation:** the register advances only on the track's own trigs; at most one note out per trig, never free-running.
- Battery-RAM bytes → quantizer uses `0x100b14ec..ee` from the padding `0x100b14e2..ef`. Whether the remaining padding bytes are free must be measured as quantizer did (no absolute reference in the OS) before Turing claims any; clamp them at boot like `qz_boot`.

### 3.3 User Project Safety

- **Saved projects without the module:** load safely; Turing defaults to OFF.
- **Projects saved with the module, loaded without it:** MIDI trigs play their own notes; the stock loader skips the `#` lines.
- **Part save/reload (v0.1):** the register is runtime state and is not saved, so a frozen phrase does not survive a reload. That must be stated in the README. Saving it is milestone M4.

## 4. Contribution Requirements

From `docs/ADD_A_MODULE.md`:

### 4.1 Folder Structure

```
sdk/octabam/modules/turing-machine/
├── manifest.py              # Module declaration
├── octamod.module.json      # Generated manifest
├── README.md                # Overview, Controls, Usage, Compatibility, etc.
├── TESTING.md               # Commands, results, limitations
├── LICENSE                  # MIT or other (choose and credit)
├── turing.c                 # Core algorithm (C)
├── turing.s                 # Generated ColdFire assembly
├── hooks.s                  # Hook adapter code
├── core.s                   # ROM core (boot clamps, defaults)
├── generate.py              # C → assembly builder
├── evidence/
│   └── performance.json     # coldfire perf record (perf:audit)
├── media/
│   ├── capture.json         # Screenshot provenance
│   ├── ot-sequencer-menu.png
│   ├── ot-turing-enabled.png
│   └── LICENSE.md
└── presentation/
    └── thumbnail.svg        # 320×192 SVG
```

### 4.2 Documentation Requirements

**README.md sections:**
1. **Overview:** What it does, how it works
2. **Controls:** Table of parameters, ranges, descriptions
3. **Usage:** Tutorial with ≥3 steps (enable, set probability/length, hear result)
4. **Compatibility and limitations:** Conflicts, hardware status, known issues
5. **Tests and measurements:** What was verified, what was not
6. **Authorship and licences:** Credits, licence text
7. **Screens and audio:** Screenshots with captions

**TESTING.md:**
- Commands run (e.g., `npm run check`, `npm run module:doctor -- turing-machine`)
- Emulator tests, ColdFire port tests
- Hardware test report (device, duration, what was tested)
- Performance benchmarks (`cfmeter.py` results)
- What was NOT tested (be explicit)

### 4.3 Manifest Requirements

`manifest.py` must define:
- `Module()` with `kind=Kind.CF_PATCH`
- `category=Category.MIDI_USB`; in `octamod.module.json`, `category: midi-usb` and `compatibility.location: MIDI tracks` (`docs/module-guides/midi-usb.md`)
- `author` and `author_url`
- `proof` level (`Proof.RENDER`, `Proof.PORT`, or `Proof.HARDWARE`)
- Detour sites with `stock_guard()` (address, length, SHA-256 of stock bytes)
- DRAM allocation with `Linked(dram=True)` if using platform runtime
- `TableGrow` entries for menu rows
- `gates` list (verification scripts)
- `evidence/performance.json` from `npm run perf:audit -- template coldfire`, passing `npm run perf:audit -- check`. `module:doctor` enforces it for modules listed from 7 October 2026: worst event in cycles, `cfmeter.py` frame-interrupt and idle deltas against stock (≤10% of 362.8 µs, ≤10 idle points), and a 60 s+ flood at ~1040 messages/s and ≥240 BPM with stop mid-note and a Part change, counting stuck notes and drops

### 4.4 Native Comparison

```bash
# Build comparison packages
image=$(docker image inspect modwerk-source-tools --format '{{.Id}}')
bash scripts/build-modules-isolated.sh . ../module-packages "$image"
npm run modules:import -- ../module-packages/packages --development

# Run native vs. browser comparison
npm run module:verify -- turing-machine --os ~/path/to/OCTATRACK_OS1.40C.bin

# Result: sdk/native-comparisons/turing-machine.json
```

**What must match:**
- Browser builder refuses what native refuses
- Browser builder reproduces what native builds (byte-identical)

### 4.5 Screenshots

Captured with `scripts/capture-module-ui.py`:
- PROJECT > CONTROL > SEQUENCER with new TURING rows
- MIDI track with Turing enabled, playing
- External receiver showing generated notes

**Requirements:**
- Real 128×64 LCD pixels (headless emulator)
- Monochrome (black and white only)
- Provenance in `media/capture.json` (date, version, setup)

### 4.6 Release Notes

Add entry to `src/community/module-changelogs.json`:

```json
{
  "turing-machine": [
    {
      "version": "0.1.0-experimental",
      "date": "2026-10-XX",
      "changes": [
        "Initial release: shift register sequencer for MIDI tracks",
        "Loop length 2-16 steps, probability/lock control",
        "Chromatic note output over a LOW/SPAN range; no scale yet",
        "No declared conflicts; quantizer scale integration is staged for later versions",
        "Register contents are runtime state and are not saved with the project"
      ]
    }
  ]
}
```

### 4.7 Validation Steps

Before opening PR:

```bash
npm run modules:generate                        # Regenerate catalog
npm run check -- --base origin/main             # Lint, types, tests
npm run module:doctor -- turing-machine         # Integration checks
npm run modules:check -- --base origin/main     # Version/publication rules
npm run module:verify -- turing-machine --os <1.40C.bin>  # Native comparison
```

All must pass before the PR is ready for owner review.

## 5. Implementation Plan

Integration with quantizer is the target, reached incrementally: each milestone is shippable on its own, and the coupling to quantizer grows only after the part before it is proven. Revision 1 gave day estimates; they are replaced here by the technical scope of each step. The dominant uncertainty is M0, and nothing after it can be sized honestly until M0 has located the hook.

**Before M0:** the midi-usb guide asks contributors to "agree the design with the owner before you spend long on one that has no precedent". This report is the basis for that conversation (§2.5).

### M0: Locate the MIDI-track note hook ✅ (emulator, 8 October 2026)

Found and proven under the ColdFire emulator with a patched scratch image. Details, method and limits are in §7. Not yet done: the same detour through the real octabam build (`build_bus.py` with a `Detour` and `stock_guard`), and the ARP, NOTE-lock, MIDI-IN and Part-change cases listed in §7.

### M1: v0.1 (scale stage S0): one track, fixed length 16, note only

- `sdk/octabam/modules/turing-machine/` from `npm run module:new -- turing-machine --kind coldfire --author <login>`. C engine compiled to checked-in assembly the way Euclid's `generate_control.py` does it, plus a hook adapter.
- One MIDI track (TURING MODE OFF/T1..T8), LENGTH fixed at 16, LOCK on a SEQUENCER row, chromatic LOW/SPAN mapping.
- Transport by edge-detecting the PLAYING word; note-off bookkeeping on STOP, Part change and pattern change.
- No `requires`/`conflicts`; project-level settings with clamps at boot.
- Gates: a `verify_turing.py` that runs the port with `--midi-out` and checks (a) LOCK 127 repeats a 16-note phrase exactly, (b) LOCK 64 changes it, (c) every note-on has its note-off, (d) Turing OFF output is byte-identical to stock.

**Scope:** one DRAM unit, one detour, a `TableGrow` for 2–4 rows, one gate. This is the smallest module that proves the hook and the live freeze behaviour.

### M2: v0.1 release quality (still S0)

- LENGTH 2–16; all eight MIDI tracks (one register per track, a shared enable mask).
- Everything §4 lists: README with full message map and tutorial, TESTING.md, screenshots via `scripts/capture-module-ui.py`, thumbnail, `evidence/performance.json`, `module:verify` against native, release notes.
- Multi-instance and persistence checks from `ADD_A_MODULE.md` (different tracks with different settings; project save/load/reload; reboot on a unit, recorded separately from emulator results).
- Hardware report from a real unit. Michael can supply this. Untested items stay "not tested".

**Scope:** mostly qualification, documentation and the multi-track generalisation; no new hook.

### M3: scale stage S1, then S2 (the quantizer integration)

- **S1:** Turing's own mask table and `snap_to_mask`, in quantizer's mask format and snap rule. Its own SCALE/ROOT rows, or a single SCALE row, to keep menu space down.
- **S2:** a small ROM stub that names `qz_scale_mask` through the `defsyms` fallback mechanism (§2.3), falling back to S1. Native and browser builds of three selections: without a provider, with `quantizer`, with `synth`. A gate that sets quantizer's SCALE/ROOT and checks Turing notes land on the scale.
- Document the `SCALE_AT` dependency in both modules' READMEs ("bump together").

**Scope:** S1 is self-contained. S2 touches the shared build (`build_bus.py`) and the browser engine (`src/engine/`) if the fallback form is new, plus a cross-module gate. That cross-module work is where owner review matters most.

### M4: shared UI, live control, persistence (S3 and extras)

- S3: FOLLOW/OWN choice; Turing rows beside SCALE/ROOT/GLIDE; both modules' battery-RAM bytes and project lines coexist on save/load/reboot.
- LOCK on a MIDI page encoder (after owner agreement on the stock-page change), making it lockable and scene-morphable.
- Saving a frozen register with the project or Part. This is research: there is no relocatable per-Part precedent.
- Output modes: CC (a configurable CC number) and VEL (the sequencer keeps NOTE; Turing sets velocity). A rotation/offset of the read window.

### Scope summary

| Milestone | Scale stage | Touches | Main risk |
|---|---|---|---|
| M0 ✅ | n/a | Emulator tracing, one detour | Done: hook at `0x4009fb2e` proven on a patched image |
| M1 | S0 | New module folder, one DRAM unit, one detour, SEQUENCER rows, one gate | Note-off pairing |
| M2 | S0 | Docs, media, perf record, native comparison, hardware report | Menu-space refusal beside the crowded set |
| M3 | S1 → S2 | Turing unit, then a ROM stub + `defsyms` fallback, possibly `build_bus.py` and `src/engine/` | Shared-build change; pinned-address contract |
| M4 | S3 | Stock MIDI page (owner-approved), persistence research | Stock-flow change; no per-Part precedent |

## 6. Conclusion

A Turing machine for Octatrack MIDI tracks is **feasible** as a ColdFire-only `midi-usb` module, with low hardware and project risk. Its central hook is now **found and proven in the emulator** (§7): the stock note-on loop at `0x4009fb2e`, where a replaced note is also the one the stock note-off releases.

Quantizer integration is not only possible but has an existing contract (`SCALE_AT`, already used by FM Synth). Staging it S0 → S1 → S2 → S3 keeps every release independent of quantizer until the optional link is proven. No quantizer conflict should be declared at any stage.

**Real exclusions:** MIDI Scenes (standalone-only today). Euclid's PLAY/frame sites, avoided by design. Possibly the crowded-menu set, to be measured.

**Next steps:**
1. Owner review of this study and the questions in §2.5.
2. M1 on a branch: the same detour through the real octabam build, the shift register, and an emulator gate built on MIDI OUT capture.
3. A draft PR for early feedback once M1's gate is green.


## 7. M0 result: the hook, measured (8 October 2026)

Everything below ran on this repository's vendored octabam emulator (`tools/emu/ot_emu`, built from `sdk/octabam` at this branch) with the stock 1.40C MAIN OS (SHA-256 `164f3122…0a84e`, matching `src/engine/assets/stock-dsp-metadata.json`). The firmware and every image derived from it stayed outside the repository. Nothing here ran on hardware.

**Fixture, through the emulated panel.** No project template was needed. On an empty scratch card: dismiss the date prompt, MIDI → T1, FUNC+SRC, turn CHAN to 1 and confirm with YES, then REC, TRIG 1/5/9/13, REC and PLAY. The CHAN edit only takes effect after YES. Before that, the track sends nothing.

**MIDI OUT capture.** The interactive emulator does not expose UART0's transmit bytes (`--midi-out` writes only in batch mode), so the scratch copy of `ot_emu` gained a one-command `uart0` query. That small change to the emulator is worth proposing upstream. Stock output for four trigs at 120 BPM over 4 s:

```
90 30 64 30 00 90 30 64 30 00 30 64 30 00 ...    note-on C3 vel 100, note-off as vel 0, running status
```

**Tracing.**
1. The note bytes do not pass through the single-byte UART queues `0x4001084c`/`0x400108b0`. A PC watch on every routine of the UART driver (`0x400106ec..0x40011040`) showed the 3-byte queue `0x40010bc8(len, buf)` called once per note from two sites in the sequencer: `0x4009fbac` (note-on) and `0x4009f8bc` (note-off).
2. Reading back from `0x4009fbac` gives the chord loop described in §2.2, with its head at `0x4009fb2e`.
3. A PC watch on `0x4009fb2e`, with trigs on T1 (4 steps) and T2 (2 steps), recorded `d7=0` 9 passes and `d7=1` 4 passes for each `d4` = 0..3, matching the 13 note-ons sent. One pass per slot per firing trig per track. (T2's channel edit did not take in that run, so both tracks transmitted on channel 1; the pass counts are unaffected.)

**Proof by patching (scratch image, never committed).** The six bytes at `0x4009fb2e` were replaced by `jmp 0x400d2800`, a 60-byte stub in the free zero run `0x400d24d0..0x400d2ce0` (`OVERFLOW_RUN` in `build_bus.py`). On T1, at `d4 == 0`, the stub adds 12 to all four chord slots (keeping `-1` and dropping notes above 127), then runs the displaced instructions and jumps to `0x4009fb34`.

| Image | MIDI OUT (first notes) | Verdict |
|---|---|---|
| stock | `90 30 64 30 00 90 30 64 30 00 30 64 30 00 …` | baseline |
| +12 on NOTE only | `90 3c 64 30 64 3c 00 30 00 …` | the old note sounds too: NOT2–4 were precomputed from the original NOTE (§3.2) |
| +12 on all four slots | `90 3c 64 3c 00 90 3c 64 3c 00 3c 64 3c 00 …` | identical to stock with 0x30 → 0x3c, note-offs matched |

```asm
| the stub (GNU as, -mcpu=5475), linked at 0x400d2800
stub:   tst.l %d4 ; bne.s 9f            | chord slot 0 only
        tst.l %d7 ; bne.s 9f            | track 1 only (the spike)
        move.l %d1,-(%sp) ; move.l %a0,-(%sp)
        move.l %a2,%a0 ; moveq #3,%d1
1:      mvs.b (%a0),%d0 ; bmi.s 2f      | -1: no note in this slot
        addi.l #12,%d0 ; cmpi.l #127,%d0 ; ble.s 3f
        moveq #-1,%d0                   | out of range: drop it
3:      move.b %d0,(%a0)
2:      addq.l #1,%a0 ; subq.l #1,%d1 ; bpl.s 1b
        move.l (%sp)+,%a0 ; move.l (%sp)+,%d1
9:      move.b (%a2),%d1 ; mvs.b %d1,%d0 ; moveq #-1,%d3   | displaced
        jmp 0x4009fb34
```

**What M0 did not cover:**
- The detour has not yet been built through octabam's composition (`build_bus.py`, `Detour` + `stock_guard`) or the browser builder. That is the first M1 step and needs the Docker toolchain image or the native setup used here.
- No NOTE parameter lock, trig condition, ARP, live recording, MIDI-IN-played notes, Part/pattern change or stop-mid-note case has been run. Whether ARP notes pass through this loop is unknown.
- The pitch-class remap after the hook (`0x400d80a0`) is only read, not identified. If it is a stock key/scale setting it matters for scale stages S1–S2, which would then compose with or replace it.
- No timing or cycle measurement. The stub's cost is a few dozen instructions per trig, but that is an estimate, not a `cfmeter.py` result.
- No hardware.

---

## Appendix A: Hook search, concretely

Written before M0 as a plan. §7 records what was actually run: the panel-driven fixture and an interactive `uart0` query replaced the batch `--midi-out` path, and the UART driver's routine entries replaced `--watch-mem`.

1. Fixture: `ot_spec.py apply` a scratch project with MIDI track 1 on channel 1, trigs on steps 1/5/9/13, NOTE lock on step 9. Write it into every Part of every bank (the AGENTS.md "the part the emulated load applies is not the part that plays" trap).
2. Baseline: `ot_emu --card <img> --project <name> --sequencer --frames 400 --midi-out base.bin`. Parse `base.bin` for `9n kk vv` / `8n kk vv` (or `9n kk 00`). Expect four note-on/off pairs, the third at the locked note.
3. Trace: repeat with `--pc-ring` and `--watch-mem` on the UART0 transmit register (the address comes from the port's `periph.h`). Walk back to the routine that selects the note byte, and look for one place where the trig's resolved NOTE is read for both the on and the off.
4. Prove: pass-through detour → byte-identical `--midi-out` to baseline. +12 detour → every note shifted, pairs intact.
5. Use `--scenario` to fork several runs from one project load (stop mid-note, Part change, pattern change) for the note-off checks.

Note: `0x4000e79c` / `0x400d64a0` (CC Map's sites) are the *incoming* MIDI CC dispatch, not the output path.

## Appendix B: Code sketch

See §2.2 "Algorithm". Revision 1's sketch here advanced a position counter and shifted the register at the same time, which does not loop like the Music Thing module, and has been removed.

---

## Appendix C: References

- **Octabam AGENTS.md:** `sdk/octabam/AGENTS.md` (assembler traps, hardware constraints)
- **Module guide:** `docs/module-guides/README.md`, `docs/module-guides/midi-usb.md`
- **Sequencing guide:** `docs/module-guides/sequencing.md` (transport, tempo, timing)
- **Add a module:** `docs/ADD_A_MODULE.md` (contribution workflow)
- **Module qualification:** `docs/MODULE_QUALIFICATION.md` (evidence, testing)
- **Quantizer source:** `sdk/octabam/modules/quantizer/` (MIDI track integration example)
- **Euclid source:** `sdk/octabam/modules/euclid/` (transport, timing, frame hooks)
- **CC Map source:** `sdk/octabam/modules/cc-map/` (MIDI dispatch interception)
- **MIDI Scenes source:** `sdk/octabam/modules/midi-scenes/` (MIDI parameter state)

---

**End of feasibility study.**
