# Turing Machine Sequencer — Feasibility Study

**Date:** 8 October 2026  
**Requester:** Michael (pmsorhaindo)  
**Status:** Feasibility analysis complete; implementation not started  
**Revision 2 (8 October 2026):** quantizer integration is the target, reached in stages (§2.3, §5). Corrects revision 1's conflict analysis (§3.1), frame timing (§1.4) and replaces day estimates with technical scope (§5).

## Executive Summary

A Turing machine sequencer mode for Octatrack MIDI tracks is **feasible in principle** with the existing module architecture, but **no module in this repository yet generates or transforms MIDI notes** (`docs/module-guides/midi-usb.md`, "MIDI generators and MIDI effects"), so the MIDI-track trig/note-out hook has no worked example and must be located first. The cleanest design is a **ColdFire-only module** (`Kind.CF_PATCH`, `category: midi-usb`, `compatibility.location: MIDI tracks`) that hooks the point where the sequencer emits a MIDI track's note, following Euclid's transport/timing pattern.

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

**Key finding:** There is **no documented "MIDI trig execution" hook** in the examined modules. The quantizer intercepts *user input* (keyboard, knobs), not sequencer trig playback. MIDI Scenes works at the parameter level. To generate or override sequencer MIDI output, we need to find or create a hook at the **MIDI trig processing / note output stage**.

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

1. **MIDI trig execution hook** (new; not yet identified)
   - **Where:** At the point where the sequencer processes a MIDI track trig and prepares to send a note
   - **Action:** Read Turing machine state, compute next note, override/supplement the trig's note value
   - **Challenge:** This hook point needs to be located in the firmware. Likely near:
     - Sequencer trig processing (`0x4009...` range based on Euclid's PLAY hooks)
     - MIDI note output preparation
   - **Fallback:** If direct trig override is not feasible, could use a **post-trig event hook** similar to how Euclid publishes after scene/LFO processing

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

1. **MIDI trig execution hook location:**  
   Where exactly does the sequencer process MIDI trigs and prepare note output? Is there an existing hook point, or does one need to be added to the firmware RE knowledge base?

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
- **Stuck notes (the main risk).** If the hook replaces a trig's note-on, the stock note-off at the end of the trig's LEN must carry the *replaced* note, or the receiver holds the original forever. The hook has to sit where note-on and note-off share one note value (the trig's resolved NOTE), or the module must remember the note it emitted per track and voice and rewrite the matching note-off. The same applies to the chord notes NOT2–NOT4 and to ARP, which are out of scope for v0.1 and should be passed through untouched. The midi-usb checklist's "every note-on gets its note-off" items (stop, Part/pattern change, bypass, removal) are the acceptance tests.
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

### M0: Locate the MIDI-track note hook (research spike)

**Goal:** One stock address where a MIDI track's trig resolves its NOTE and both the note-on and its later note-off read that value.

- Build a test project with `sdk/octabam/tools/hw/ot_spec.py`: one MIDI track, channel set, four trigs, one with a NOTE lock.
- Run it under the ColdFire port with `--sequencer --frames N --midi-out <file>`. `--midi-out` writes UART0's transmit bytes, so the note-ons and note-offs can be read without hardware. Use `--pc-ring` / `--watch-pc` / `--watch-mem` to walk back from the UART transmit to the routine that chose the note byte.
- Prove the site with a pass-through detour (displaced instructions only), then with a fixed transpose (+12) and check in the `--midi-out` capture that every note-off matches its note-on.
- Record the site and its `stock_guard` (address, length, SHA-256). Check it against every claimed site in the ledger (`make modules`); MIDI Scenes' regions do not matter, since it is standalone-only.

**Scope:** emulator tracing and one 6-byte detour; no module code yet. **Needs:** the native toolchain image and the contributor's own 1.40C update file. Neither is in this environment, which is why no spike was run for this study.  
**Exit:** a site that passes the note-off check, or a documented negative result and a fallback (rewriting the track's live NOTE value before the sequencer reads it, as Euclid publishes FREQ).

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
| M0 | n/a | Emulator tracing, one detour | No clean note hook. Fallback: publish the live NOTE value |
| M1 | S0 | New module folder, one DRAM unit, one detour, SEQUENCER rows, one gate | Note-off pairing |
| M2 | S0 | Docs, media, perf record, native comparison, hardware report | Menu-space refusal beside the crowded set |
| M3 | S1 → S2 | Turing unit, then a ROM stub + `defsyms` fallback, possibly `build_bus.py` and `src/engine/` | Shared-build change; pinned-address contract |
| M4 | S3 | Stock MIDI page (owner-approved), persistence research | Stock-flow change; no per-Part precedent |

## 6. Conclusion

A Turing machine for Octatrack MIDI tracks is **feasible** as a ColdFire-only `midi-usb` module, with low hardware and project risk, but **unproven at its central hook**: no module here yet generates MIDI notes. M0 is therefore a research spike and must come first.

Quantizer integration is not only possible but has an existing contract (`SCALE_AT`, already used by FM Synth). Staging it S0 → S1 → S2 → S3 keeps every release independent of quantizer until the optional link is proven. No quantizer conflict should be declared at any stage.

**Real exclusions:** MIDI Scenes (standalone-only today). Euclid's PLAY/frame sites, avoided by design. Possibly the crowded-menu set, to be measured.

**Next steps:**
1. Owner review of this study and the questions in §2.5.
2. M0 on a machine with the native toolchain and a 1.40C update file.
3. If M0 succeeds, M1 on a branch, with a draft PR for early feedback.

---

## Appendix A: Hook search, concretely

The emulator options below exist in `sdk/octabam/tools/emu/ot_emu/main.cpp`. How they combine for this search is a plan, not a run.

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
