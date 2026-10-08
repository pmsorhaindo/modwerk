# Turing Machine Sequencer — Feasibility Study

**Date:** 8 October 2026  
**Requester:** Michael (pmsorhaindo)  
**Status:** Feasibility analysis complete; implementation not started

## Executive Summary

A Turing machine sequencer mode for Octatrack MIDI tracks is **feasible** with the existing module architecture. The cleanest design is a **ColdFire-only module** (`Kind.CF_PATCH`) that hooks into MIDI note generation at the sequencer trig processing path, similar to how the quantizer intercepts chromatic keys and how MIDI Scenes adds scene morphing to MIDI parameters.

**Recommended approach:** Per-MIDI-track state with a probability control, loop length, note range/scale controls, and output routing (note/CC/velocity). The module would hook the MIDI trig execution path to override or supplement note output, persist as Part data, and expose controls through new SEQUENCER menu rows (similar to quantizer's SCALE/ROOT/GLIDE pattern).

**Key risks:** Low. Conflicts with quantizer (both modify MIDI output) require careful integration or mutual exclusion. No DSP code needed, no audio processing, moderate ColdFire CPU impact per active MIDI track.

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
- **Key insight:** Shows that MIDI track sequencer parameters can be added as menu rows and persisted as Part/project data. The quantizer modifies notes *before* they reach the synth engine by intercepting the chromatic key handler.

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
- **Key insight:** Shows that per-track, per-parameter state can be stored in Part data and integrated with the existing parameter system. Demonstrates frame-rate processing for MIDI parameter interpolation.

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
  - **Timing:** Frame ISR runs every ~2.9 ms (44.1 kHz / 128 samples)
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
- Note output: triggers only when a trig fires (typically 16 steps/pattern at most 240 BPM = ~64 trigs/sec = ~0.064 trigs/frame)
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

2. **Transport hooks** (known: `0x4009c3d4`, `0x4009c4d4`)
   - PLAY: Reset shift register position (or let it continue per user preference)
   - STOP: Freeze state (preserve for next PLAY)

3. **Frame hook** (optional, for live parameter updates)
   - Read probability, length controls
   - Update shift register on each step/trig

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
- DRAM unit (depacked at boot, like quantizer)
- 8 MIDI tracks × 32 bytes = 256 bytes maximum
- Or battery-RAM for persistence across power cycles (like quantizer's `NV_SCALE`)

#### Controls and UI

**Menu location:** PROJECT > CONTROL > SEQUENCER (new rows below quantizer's GLIDE)

```
TURING MODE:    [OFF | TRACK 1-8 | ALL]
TURING LOCK:    [0-127]          (probability)
TURING LENGTH:  [2-16]
TURING SCALE:   [OFF | MAJOR | MINOR | ...]  (reuse quantizer scales)
TURING ROOT:    [C-B]
TURING RANGE:   [note_min - note_max]
TURING OUTPUT:  [NOTE | CC | VEL]
```

**Alternative:** Per-track enable in MIDI track settings, with global controls in SEQUENCER menu. This fits the Octatrack's pattern of per-track assignment + global parameters.

#### Algorithm

```c
// Per-trig execution (when a MIDI trig fires on an enabled track)
void turing_process_trig(uint8_t track, uint8_t trig_note) {
    TuringState *s = &turing_states[track];
    if (!s->enabled) return;  // pass through normal trig
    
    // Read current bit
    uint8_t current_bit = (s->shift_register >> s->position) & 1;
    
    // Shift register right (loop at length)
    uint8_t length = s->length;  // 2-16
    if (++s->position >= length) {
        s->position = 0;
    }
    
    // Mutate bit based on probability
    uint8_t new_bit = current_bit;
    uint32_t random = xorshift32(&s->rng_state);
    if ((random & 0x7F) >= s->probability) {  // Higher prob = more locked
        new_bit = (random >> 7) & 1;  // Flip randomly
    }
    
    // Update shift register
    uint16_t mask = 1 << (length - 1);
    s->shift_register = (s->shift_register >> 1) | (new_bit ? mask : 0);
    
    // Map shift register value to note
    // Use only `length` bits of the register
    uint16_t value_mask = (1 << length) - 1;
    uint16_t value = s->shift_register & value_mask;
    
    // Scale to note range
    uint8_t note = s->note_min + 
                   (value * (s->note_max - s->note_min)) / value_mask;
    
    // Apply scale quantization (reuse quantizer's qz_scale_mask)
    if (s->scale != 0) {
        note = quantize_to_scale(note, s->scale, s->root);
    }
    
    // Output
    switch (s->output_mode) {
        case 0: midi_send_note(track, note, trig_velocity); break;
        case 1: midi_send_cc(track, s->cc_number, value >> (length - 7)); break;
        case 2: midi_send_note(track, trig_note, value >> (length - 7)); break;
    }
}
```

### 2.3 Integration with Quantizer

**Compatibility question:** Can Turing machine and quantizer coexist?

**Option A: Conflict** (simplest, safest for v0.1)
- Declare `compatibility.conflicts: ["quantizer"]`
- Rationale: Both modify MIDI output, and integration needs careful testing
- Future: Integrate in a later version after both are stable

**Option B: Integration** (v0.2+)
- Turing machine generates the raw note value
- Pass through quantizer's `qz_scale_mask` for quantization
- Requires: Exposing quantizer's scale/root state, or Turing machine reimplementing it
- Benefit: Unified scale/root controls, user can apply same scale to sequencer and Turing tracks

**Recommendation:** Start with **Option A** (conflict) for v0.1. Integration can come in a later version once the core Turing machine is proven.

### 2.4 Testing Strategy

Following the module guides:

1. **Emulator testing** (`tools/emu/ot_emu`):
   - Build test project with MIDI tracks, various trig patterns
   - Verify shift register state evolution
   - Verify note output (MIDI monitor or virtual MIDI)
   - Transport start/stop behavior

2. **ColdFire port testing** (`tools/verify/`):
   - Verify hook execution with `--dsp-pcwatch`
   - Frame-by-frame state inspection
   - Project save/load/reload persistence

3. **Hardware testing** (required before v0.1 release):
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

2. **Quantizer integration priority:**  
   Should v0.1 conflict with quantizer (simplest), or is integration expected from the start?

3. **Per-track enable vs. global mode:**  
   Preferred UI pattern: per-track switch (like track mute) or global SEQUENCER menu with track selection?

4. **Shift register initialization:**  
   On first enable or PLAY: start with all zeros, all ones, or seeded random? User preference?

5. **Scale quantization:**  
   Reuse quantizer's code (requires linking or exposing its functions), or reimplement scale masks?

## 3. Conflicts and Risks

### 3.1 Module Conflicts

| Conflict | Reason | Severity | Mitigation |
|----------|--------|----------|------------|
| **Quantizer** | Both modify MIDI note output | High | Declare conflict in v0.1, integrate in v0.2+ |
| MIDI Scenes | Possible interaction with scene locks on MIDI params | Low | Test: Turing note output should not be morphed by scenes |
| CC Map | None (operates on incoming CC, Turing on outgoing notes) | None | - |

**Recommendation:** `compatibility.conflicts: ["quantizer"]` for the initial release.

### 3.2 Hardware and Safety Risks

**Risk level: LOW**

- **No audio processing:** No DSP code, no risk of clipping/DC/aliasing
- **No firmware extraction:** Uses standard hook/detour mechanism
- **Bounded CPU:** Per-trig execution only; MIDI trigs are sparse (~64/sec max)
- **Safe defaults:** Enabled = OFF by default; no output until user enables and configures
- **Project compatibility:** New Part data fields; old projects load with Turing disabled

**Potential issues:**
- MIDI output flood if shift register update is too fast → **Mitigation:** Tie updates to sequencer trigs, never free-running
- Stuck notes if state is not reset properly → **Mitigation:** Clear state on STOP, follow Euclid's transport pattern
- Battery-RAM corruption if save/load is wrong → **Mitigation:** Clamp values at boot like quantizer's `qz_boot`

### 3.3 User Project Safety

- **Saved projects without the module:** Load safely (Turing state ignored)
- **Saved projects with the module, loaded without it:** MIDI trigs revert to normal behavior (no data loss)
- **Part save/reload:** Shift register state and position are preserved (user-visible pattern stays the same)

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
- `category=Category.MIDI_USB`
- `author` and `author_url`
- `proof` level (`Proof.RENDER`, `Proof.PORT`, or `Proof.HARDWARE`)
- Detour sites with `stock_guard()` (address, length, SHA-256 of stock bytes)
- DRAM allocation with `Linked(dram=True)` if using platform runtime
- `TableGrow` entries for menu rows
- `gates` list (verification scripts)

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
        "Note output with range and optional scale quantization",
        "Conflicts with quantizer in v0.1; integration planned for v0.2"
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

### Milestone 0: Research Hook Point (1-2 days)

**Goal:** Locate the MIDI trig execution path in the firmware.

**Tasks:**
1. Search existing modules for MIDI output references
2. Use ColdFire port (`ot_emu --watch-pc`) with a test project:
   - MIDI track, simple trig pattern
   - Trace from trig fire to MIDI note-on event
   - Identify candidate hook address
3. Verify hook with a minimal detour (e.g., log trig event, pass through unchanged)

**Deliverable:** Hook address, stock guard (address/length/SHA-256), proof it runs per-trig

**Open question:** If direct trig override is not feasible, can we:
- Hook after trig execution and send a second note?
- Override the MIDI output buffer before transmission?
- Use a frame hook and track trig state manually?

---

### Milestone 1: Minimal v0.1 (3-5 days)

**Goal:** Fixed-length (16 steps), note-only Turing machine with probability control.

**Features:**
- Single MIDI track mode (hardcoded track 1 for testing)
- 16-bit shift register (fixed length)
- Probability control (0-127): 0 = fully random, 127 = fully locked
- Note range: MIDI 36-84 (C1-C6)
- No scale quantization
- No save/load (runtime state only)

**Implementation:**
1. Create module folder, `manifest.py` skeleton
2. Implement core algorithm in `turing.c`:
   - `turing_process_trig(track, trig_note)` → MIDI note output
   - `turing_reset()` (on PLAY)
   - Fixed 16-bit shift register, xorshift32 RNG
3. Compile to `turing.s` with `generate.py`
4. Add hooks:
   - MIDI trig execution detour (found in Milestone 0)
   - PLAY transport hook (`eu_start_hook` pattern)
5. Add minimal menu controls (PROJECT > CONTROL > SEQUENCER):
   - TURING MODE: OFF / TRACK 1
   - TURING LOCK: 0-127
6. Test in emulator: verify notes change based on probability

**Validation:**
- Emulator playback: pattern evolves over time
- Probability 0: fully random each trig
- Probability 127: pattern locks and repeats

**Deliverable:** Working prototype, not yet production-ready

**Effort estimate:** 3-5 days (assuming hook point is found)

---

### Milestone 2: Full v0.1 Release (5-7 days)

**Goal:** Production-ready initial release with essential features.

**Add to v0.1:**
1. **Variable loop length:** 2-16 steps (menu control)
2. **Per-track enable:** All 8 MIDI tracks supported
3. **Note range controls:** min/max MIDI note (menu controls)
4. **Transport integration:**
   - PLAY: reset position (or continue, configurable?)
   - STOP: preserve state for next PLAY
5. **Project persistence:**
   - Save: shift register, position, enabled flag, parameters
   - Load: restore state or initialize fresh
   - Battery-RAM for cross-power-cycle persistence
6. **Menu UI:**
   - Complete SEQUENCER rows
   - Value clamping and defaults
7. **README.md:** Full documentation (all required sections)
8. **TESTING.md:** Emulator + ColdFire port testing
9. **Screenshots:** Captured with `capture-module-ui.py`
10. **Performance benchmark:** `cfmeter.py` under MIDI flood

**Validation:**
- `npm run check -- --base origin/main`: pass
- `npm run module:doctor -- turing-machine`: all green
- `npm run module:verify -- turing-machine --os <1.40C.bin>`: pass
- Hardware test: owner or contributor with MKI/MKII

**Conflicts:** Declare `compatibility.conflicts: ["quantizer"]`

**Effort estimate:** 5-7 days after Milestone 1

**Deliverable:** Ready for PR, pending owner review

---

### Milestone 3: v0.2 Enhancements (future)

**Goal:** Additional features and polish.

**Features:**
1. **Scale quantization:**
   - Reuse quantizer's scale/root, or reimplement
   - Integration: remove conflict declaration
2. **CC output mode:**
   - Output shift register value as MIDI CC
   - Configurable CC number
3. **Velocity mode:**
   - Sequencer provides note, Turing machine provides velocity
4. **Rotation control:**
   - Offset the shift register readout (like Euclid's ROT)
5. **Multiple Turing machines per track:**
   - Separate instances for note + CC + velocity?

**Effort estimate:** 3-5 days per feature

---

### Effort Summary

| Milestone | Description | Estimated Effort |
|-----------|-------------|------------------|
| **M0** | Research hook point | 1-2 days |
| **M1** | Minimal v0.1 prototype | 3-5 days |
| **M2** | Full v0.1 release | 5-7 days |
| **M3** | v0.2 enhancements | 3-5 days per feature |
| **Total (v0.1)** | Ready for PR | **9-14 days** |

**Note:** Effort assumes:
- Contributor familiar with ColdFire assembly and octabam architecture
- Hook point can be found (Milestone 0 is critical)
- No major blockers in firmware RE

---

## 6. Conclusion

A Turing machine sequencer for Octatrack MIDI tracks is **feasible and safe** to implement as a Modwerk module. The architecture follows established patterns (quantizer for MIDI track integration, Euclid for transport/timing), the CPU/memory impact is low, and the risks are minimal (no DSP, no firmware extraction, bounded CPU).

**Key dependencies:**
1. **Locate MIDI trig execution hook** (Milestone 0 is critical)
2. **Owner approval** for the module concept and initial design
3. **Hardware testing** before v0.1 release (can be emulator-only for prototype)

**Recommended next steps:**
1. Owner review of this feasibility study
2. Approval to proceed with Milestone 0 (hook location research)
3. If M0 succeeds, proceed with M1 (minimal prototype)
4. Open draft PR with M1 for early feedback
5. Complete M2 for full v0.1 release

**Questions for owner:**
- Is the proposed design acceptable?
- Any preference on UI (per-track enable vs. global mode)?
- Should v0.1 conflict with quantizer, or is integration expected?
- Any additional features or constraints for the initial release?

---

## Appendix A: Hook Point Search Strategy

If Milestone 0 research is needed, search strategy:

1. **Grep the firmware docs** for "MIDI output", "note generation", "trig execution"
2. **Trace with ColdFire port:**
   ```bash
   # Test project: MIDI track 1, simple trig pattern (e.g., 4 trigs on steps 1, 5, 9, 13)
   tools/hw/ot_spec.py apply test-project.json --remix <your-remix>
   
   # Run with PC watch and trig on known MIDI handler addresses
   tools/emu/ot_emu --project test-project.json --watch-pc 0x4000e700:0x4000e800 \
                     --frames 200 > trace.txt
   
   # Look for per-trig execution pattern
   ```
3. **Compare with quantizer's hooks:** The quantizer intercepts *input* (chromatic keys), not output. Look for the path *after* the sequencer reads a trig and *before* the MIDI byte is sent.
4. **Candidate regions:**
   - Near `0x4009...` (transport/sequencer code, based on Euclid's PLAY hooks)
   - Near `0x4000e7...` (MIDI dispatch, based on CC Map)
   - MIDI output buffer preparation (unknown address)

---

## Appendix B: Code Sketch (Minimal v0.1)

```c
// turing.c - Core Turing machine algorithm

#include <stdint.h>

typedef struct {
    uint16_t shift_register;
    uint8_t  position;
    uint8_t  probability;
    uint32_t rng_state;
    uint8_t  enabled;
} TuringState;

// One state per MIDI track
static TuringState turing_states[8];

uint32_t xorshift32(uint32_t *state) {
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

void turing_reset(uint8_t track) {
    TuringState *s = &turing_states[track];
    s->position = 0;
    // Shift register preserved (pattern continues) or reset to 0?
}

uint8_t turing_process_trig(uint8_t track) {
    TuringState *s = &turing_states[track];
    if (!s->enabled) return 60;  // Middle C passthrough
    
    // Read current bit
    uint8_t current_bit = (s->shift_register >> s->position) & 1;
    
    // Advance position
    if (++s->position >= 16) s->position = 0;
    
    // Mutate bit
    uint8_t new_bit = current_bit;
    uint32_t random = xorshift32(&s->rng_state);
    if ((random & 0x7F) >= s->probability) {
        new_bit = (random >> 7) & 1;
    }
    
    // Shift right and insert new bit at position 15
    s->shift_register = (s->shift_register >> 1) | (new_bit ? 0x8000 : 0);
    
    // Map to MIDI note (36-84 = C1-C6)
    uint16_t value = s->shift_register;
    uint8_t note = 36 + (value * 48) / 65535;
    
    return note;
}
```

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
