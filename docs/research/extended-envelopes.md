# Extended amplitude and filter envelopes

**Date:** 23 October 2026
**Status:** Research only. No module, no firmware, no image.
**Instrument:** Octatrack, stock OS 1.40C as this repository builds it.
**Revision:** later the same day, a second question: finer control of the stock knobs, in [Finer control of the stock envelopes](#finer-control-of-the-stock-envelopes).

This note says what the stock amplitude and filter envelopes actually are, which extensions are already covered by modules in this tree, and which build is worth doing. It does not add Elektron firmware or a new effect. The second half stays on the stock envelopes and only changes how their existing knobs are read.

## What the stock instrument does

The public behaviour below is the Octatrack MKII manual, OS 1.40A, sections 11.4.5–11.4.6 and appendix B.2 ([English PDF](https://elektron.se/wp-content/uploads/2024/09/Octatrack-MKII-User-Manual_ENG_OS1.40A_210414.pdf)). Times that the manual does not state are taken only from measurements already written up for the FM Synth engine. Where those two sources do not meet, this note says so.

### Amplitude

AMP MAIN is an attack–hold–release envelope, then level and pan:

| Knob | Role |
| --- | --- |
| ATK | Time to reach full level. |
| HOLD | Time at full level, counted from the trig, with the attack included. If the attack is longer than the hold, release waits until the attack finishes. HOLD at its top is infinite: a keyboard holds until key-up (or the sample ends). A key-up inside a finite hold starts release early. |
| REL | Fade to silence after the hold. |
| VOL | Level before the effects. Main and cue both see it. |
| BAL | Pan. |

There is no decay to a sustain below full, and no sustain level. XVOL exists only while a scene key is held; it is extra scene level, not another stage.

AMP SETUP (manual 11.4.6):

| Knob | Role |
| --- | --- |
| AMP | ANLG starts the attack from the current level. RTRG restarts from zero on a sample trig. R+T restarts from zero on a sample trig or a trigless trig. TTRG starts from the current level on either. |
| SYNC | Whether the envelope follows tempo. The manual says the hold is in sequencer steps and follows BPM unless this is off. |
| ATCK | LIN or LOG. LOG is the manual's "exponential" attack, for a slower fade-in. |
| FX1, FX2 | How a multi-mode filter or a lo-fi amplitude modulator in that slot retriggers. Same four words as AMP. They do nothing for any other effect. |

The FM Synth write-up reimplemented the DSP's laws from a stock FLEX sine (`sdk/octabam/modules/synth/upstream/synth/README.md`, "The engine owns the envelope"). Those figures are the linear attack, not ATCK LOG, and they were measured for that engine's tables:

- **Attack, linear.** Duration `3.85 ms × 2^(value / 8.53)`. Stated points: 8 → 7.5 ms, 16 → 15 ms, 32 → 50 ms, 64 → 700 ms, 96 → 9.45 s. Value 127 on the DSP is called out there as anomalous: the ramp stops about 21.5 dB down instead of reaching full. The engine's own Q15 step cannot represent that top end; from 91 up its ramp is 11.9 s.
- **Hold.** A timer from the start of the note, whether or not a key is still held. Stated points at 120 BPM: 32 → 282 ms, 64 → 1132 ms, 100 → 5.5 s, 127 → infinite. When the timer ends, release starts even if nothing sent a note-off. A key-up during the hold releases immediately. The manual's "sequencer steps" and these millisecond points are not the same sentence; this note does not invent a conversion. SYNC off was not part of that measurement.
- **Release.** Exponential, `tau = 0.295 ms × 2^(value / 8.53)`. Stated points: 40 → 7.6 ms, 60 → 38.5 ms, 80 → 196 ms, 100 → 994 ms, 126 → 9 s, 127 → infinite. Release 0 on the DSP is a one-sample cut. The engine floors the fade near 1 ms so a short release is still a fade.

The same notes record the order inside a frame: scene morph, then LFOs, then the voice record is what the DSP envelope reads. VOL, balance, the filter and both effect slots stay the DSP's.

TapeHead's overview is the level order that matters for an effect: AMP VOL is applied before the FX chain.

### Filter

The Octatrack has no track filter page. The filter envelope is the envelope inside the **12/24 dB multi-mode filter**, which can sit in either effect slot (manual appendix B.2).

| Main | Role |
| --- | --- |
| BASE | Base cutoff. With WIDTH at maximum, sweeping BASE behaves as a high-pass. |
| WIDTH | Gap between the low-pass and high-pass cutoffs. With BASE at minimum, sweeping WIDTH behaves as a low-pass. |
| Q | Resonance, applied to the cutoffs chosen on the setup page. |
| DEPTH | How far the envelope moves those cutoffs. Negative depth flips the envelope. |
| ATK, DEC | Attack and decay of that envelope. |

Setup chooses 12 or 24 dB slopes (HP, LP), which parameter the envelope moves (ENV), whether AMP HOLD also holds this envelope, which cutoffs Q applies to, and headroom (DIST). The manual's extracted text says ENV "selects which parameter the filter envelope will affect" and does not list the choices. Those choices are **not** stated here.

This envelope is attack–decay plus a bipolar depth. It has no sustain and no release of its own. It retriggers only through AMP SETUP's FX1 or FX2, and only when this filter (or the lo-fi amplitude modulator) occupies that slot. No attack or decay time for it is recorded in this repository. Do not borrow the amplitude times.

### What already fakes an envelope

These are real, and they are not a missing ADSR:

- **LFO TRIG ONE / HALF** runs one cycle or half a cycle from a sample trig, then stops. **HOLD** latches the LFO level until the next sample trig. Speed is tempo only. The designer is one 16-step shape per audio track, shared by that track's LFOs, stepped or interpolated. A saw into VOL is a decay. It cannot hold an independent sustain level for as long as a key is down and then release on note-off.
- **Scenes** morph the envelope's settings, including between scene slots. They do not add stages.
- **Lo-fi amplitude modulator** is an LFO on level (AMF, AMD, start phase). AMP SETUP restarts its phase. It is not a note envelope.
- **Dynamix compressor** has its own attack (0.5–100 ms) and release (50 ms–5 s). That is a dynamics detector.
- **Euclid** (below) is the module that already does rhythmic level and filter envelopes.

## What is already in this repository

### FM Synth owns the amplitude law

On a synth track the engine writes the DSP voice's attack, hold and release so the stock envelope stays open (attack 0, hold infinite, release infinite), then applies the same laws itself to the samples it renders. The page the musician sees is still ATK, HOLD and REL. Scenes and LFOs are read from the lane after the frame has applied them. VOL, balance, filter and effects stay stock.

That is the proof that a longer or better-shaped amplitude envelope can be done by holding the stock envelope open and multiplying gain. It is also local to that machine. Sample, Thru, Neighbor and Pickup tracks still use the DSP envelope. The engine's note-off, key and sequencer paths are that module's detours. Another module does not get to call them.

The same work already filled the empty sixth box on AMP SETUP. **LEG** (OFF / MONO / POLY) is that box, on every audio track in that fork, stored as an ordinary Part byte. A second module cannot add decay or sustain to that page: the drawer, the editor and the lane write are already detours, and a module may not hook another module.

### Euclid is a rhythmic envelope in an effect slot

Euclid is an insert for either slot. A Euclidean pulse drives a filter (low-pass, band-pass, high-pass, notch) or a gain (AMP). Its ENV output retriggers an attack and a curved decay per pulse: attack up to one step, decay up to eight steps. GATE, random-hold and loop are the other outputs. It follows transport, tempo, track speed, length and swing, and it publishes after scene and LFO processing on its own frame hook. PLAY resets phase. STOP returns to the base.

On its host instruction meter the AMP path is about 462 instructions per 16-sample block, and the filter path about 2,276, against roughly 314 executed instructions per sample for stock Spring reverb at the cost target used for new effects. Those are Euclid's figures, not a budget for a new effect. The AMP path is cheap relative to Spring; the filter path is in range and still has to be measured again if it is rewritten.

Euclid's clock is the sequencer grid. It does not follow a live key, a TRIG LEN gate, or microtiming. Decay is in steps, not the amplitude release law. It is the right tool for a rhythmic duck or a stepped filter, and the wrong tool for "sustain while the note is held."

### Polyphony does not want a shared envelope

Poly8 compared independent per-voice amplitude envelopes with a shared one, on held notes only (`sdk/octabam/modules/poly8/evidence/amp-comparison.json`). Sharing saved about 3.8% of measured native instructions. The decision recorded there is independent envelopes. That comparison does not cover a moving envelope, and it is not a hardware cycle count.

## The gap

A musician who wants a synthesizer envelope on the Octatrack is missing four things:

1. **A sustain level below full** on amplitude, held for the note and released on note-off, with its own decay into that level.
2. **The same shape on a filter**, with sustain and release, without giving up the stock multi-mode filter on the other slot.
3. **A curve choice on the whole shape.** Amplitude attack can be LIN or LOG. Release is fixed exponential. The filter envelope's curves are unmeasured.
4. **Note edges, not only the grid.** Sample trigs, trigless trigs, retrigs, chromatic and MIDI notes, and note-offs. Euclid has the grid. The stock amplitude envelope has the note. A new envelope has to say which of those it sees.

Longer times are not the gap. Linear attack already reaches several seconds well before the top of the knob, and release is already multi-second before infinite. The top attack value's failure to reach full level is a stock quirk worth preserving or avoiding on purpose, not a reason to build a module.

## Constraints on any build

- **One module, or it is not a module.** It builds and runs as the only chosen module. It does not call Euclid, FM Synth, or the quantizer, and it does not take their detour sites (Euclid's frame hook and both PLAY paths; the synth's envelope write and the six AMP SETUP detours).
- **New effect id.** An id that replaces the stock multi-mode filter removes that filter from both slots. Keep the stock filter. The new effect is an insert beside it.
- **Twelve knobs, four-character names.** Page 2's mode select sits on an even slot; slot 6 is the one already confirmed on hardware. Defaults must be inside the count. A dry default is exact silence of the wet path (MIX 0 passes audio through).
- **Clock.** Stage times that are sequencer steps read the stock tempo, track speed, length and swing. Attack and release in milliseconds advance on the audio frame (16 samples, 362.8 µs), which is how the stock amplitude envelope already moves, not on a private tempo. That reason has to be written in the module README. PLAY resets the phase. STOP returns to the base. Idle instances do no timing work. Publish after scenes and LFOs if the module writes a value the stock frame would overwrite.
- **Cost.** A gain multiply should land with Euclid's AMP path, far under worst-case Spring. A filter has to be benchmarked against Spring on both cores, with the knobs moving and with trig splits, before it is kept. ColdFire work on the frame may add at most 10% of a 362.8 µs frame under the flood used for ColdFire modules.
- **Do not rewrite the musician's AMP knobs.** FM Synth already writes the DSP attack, hold and release on synth tracks. A silent "hold the stock envelope open" from a second module would fight that, and on a sample track it would discard p-locks. Stacking after a held-open stock envelope (ATK 0, HOLD infinite, REL infinite, VOL as the ceiling) is the honest default, and it is a documented setup, not a hidden write.
- **Part bytes move if a slot's position or count moves.** All twelve slots exist in the first descriptor, in the order below. A knob that is not on the panel yet stays in that descriptor with its enable nibble clear, the way the unused AMP SETUP byte already does, so switching it on later does not slide the other bytes. Changing a slot from a 0–127 value into a short select is the change that stalls a saved Part.

## Designs

### 1. One insert effect, gain first, filter second

A new effect in either slot. The envelope runs on note edges. MIX 0 is dry. The stock amplitude envelope is left alone; the musician opens it when the new envelope should be the only one.

Main page, and these meanings do not move when the mode changes:

| Knob | Name | Role |
| --- | --- | --- |
| A | ATK | Attack time, free-running, the stock linear-attack range as a starting law. |
| B | DEC | Decay from full down to SUS. |
| C | SUS | Level held while the note gate is open. |
| D | REL | Release after note-off, exponential by default. |
| E | DEP | Bipolar depth. Centre is no movement. On gain, depth is how far the envelope multiplies level. On a filter, depth is how far it moves cutoff. |
| F | MIX | Dry/wet. Zero is bit-exact dry. |

Setup:

| Knob | Name | Role |
| --- | --- | --- |
| A | MODE | AMP, then later FILTER and BOTH. Even slot, first of the setup page. |
| B | CURV | LIN or EXP for the ramps. EXP matches the stock release shape; LIN matches the stock linear attack. |
| C | TRIG | GATE (sustain until note-off, restart from zero), LEG (sustain, restart from the current level), ONCE (attack then decay to zero, ignore note-off), TLES (also restart on a trigless trig). The words match the manual's ANLG / RTRG behaviour without taking over AMP SETUP. |
| D | BASE | Filter cutoff. Inert in AMP, still stored. |
| E | WDTH | Second cutoff, unused by the single-cutoff filter. Present in the descriptor from the first version with the enable nibble clear, so it is not on the panel and not read. Turning it on later does not move the other slots. |
| F | Q | Resonance. Inert in AMP. |

Draw BASE and Q from the first version, and have the DSP read them, but keep FILTER out of MODE until the filter exists. In AMP mode those two knobs do nothing audible and the labels have to say so. Leaving WDTH undrawn matches the effects guide's rule that a drawn knob is one the DSP reads. The byte is still reserved.

The filter this describes is a single cutoff plus depth and resonance. It is not the stock filter's BASE/WIDTH gap, and it does not replace that effect. BOTH is one envelope into gain and cutoff together, not two envelopes.

Per instance the state is the stage, the phase, and the current gain or cutoff. No delay line. The DSP ramps the applied gain or cutoff every sample. The ColdFire side, if that is where the note edge is observed, advances the stage once a frame and skips inactive instances.

**This is the build to do**, once the note edge in [Note edge, the gating unknown](#note-edge-the-gating-unknown) is found.

### 2. The same effect, clocked from the grid

If a note-off edge cannot be read without taking FM Synth's detours, the same twelve knobs still work with Euclid's clock: GATE sustain lasts a number of steps (a new use of SUS as "hold for this many steps at this level"), ONCE is a one-shot from the trig, and live keys are out of scope. Timing then follows `docs/module-guides/sequencing.md` in full, including swing. PLAY and STOP use new detours, not Euclid's.

This is a better Euclid envelope, not a synthesizer envelope. It is still worth shipping if the note edge is blocked, because sequenced Octatrack parts rarely need the keyboard. It must not be described as following TRIG LEN or chromatic notes.

### 3. Write VOL and the stock filter from the ColdFire

A frame hook after scenes and LFOs writes AMP VOL, or the stock filter's BASE, from an ADSR. No new DSP audio code. The resolution matches the stock envelope, which already steps in frames.

It is a poor instrument. VOL is the knob the musician and their p-locks are using. The stock filter only moves if that effect is selected, and writing BASE fights its locks. The hook cannot be Euclid's. And the note-edge problem is the same as design 1. Use this only as a probe while looking for the edge, not as the module.

### 4. Generalise FM Synth's plan B to sample tracks

Hold the DSP amplitude envelope open on Flex, Static, Thru, Neighbor and Pickup, and multiply inside the voice, the way the synth engine already does for its own tracks. The AMP page could then grow decay and sustain.

This is the only design that makes the existing ATK / HOLD / REL knobs mean the new shape, and the only one whose note path is already proven — on synth tracks, inside that module. It is the wrong home for a filter envelope (the filter is later, in the effect slot). It collides with the synth engine on synth tracks if both write the voice. It is a playback change, not an effect, and it wants owner review of the voice path before any code. It is not the first build.

### 5. Replace the stock multi-mode filter

Rejected. The effect id is shared by both slots. Projects that use the stock filter would lose it, including the BASE/WIDTH gap and the FX1/FX2 retrigger words. An extended envelope that only exists as a replacement is a compatibility break for a small addition (sustain and release on top of an attack–decay).

### 6. Do not build: LFO designer, ONE, and a held-open stock amp

For a one-shot decay or a 16-step shape locked to tempo, LFO TRIG ONE plus the designer is already the instrument. HOLD infinite plus a short release is already a keyboard sustain at full level. Neither is a sustain-at-half. Recommend them in the module guide when someone asks for "an envelope" and means a shape. Do not spend a module on them.

## Note edge, the gating unknown

Design 1 needs a sample-trig start and a note-off that:

- sees sequencer trigs, trigless trigs, retrigs, chromatic keys and MIDI notes,
- sees note-off from a key, from TRIG LEN, and from the hold timer expiring,
- does not use FM Synth's detours or Euclid's frame and PLAY sites,
- still runs while the transport is stopped, because live keys do.

No such site is identified in this note. The synth write-up shows that those edges exist and that the stock DSP envelope consumes them inside the voice. It does not hand another module a flag. Reading a voice phase and guessing that a trig happened is not good enough to specify.

Until that observation is found on the emulator, design 1 stays a specification and design 2 is the one that can be coded. Finding it is M0. It is a read of the running image under the port, and it does not belong in the repository as firmware bytes.

## Milestones

| | Work | Done when |
| --- | --- | --- |
| M0 | On the emulator, name a note-on and note-off observation that is not an FM Synth or Euclid detour. Record what it misses (thru, neighbor, master, pickup, transport stopped). Separately, if anyone still wants to match the stock filter, measure its attack and decay at a few knob values. Do not commit an image. | A paragraph in this file, or a decision that design 2 is the ship. |
| M1 | The insert, AMP only, MODE without FILTER, BASE and Q stored and inert, MIX 0 bit-exact, both slots, both cores, Analog BD and the stock effects in the companion matrix. Trig source is whatever M0 allowed. Changelog at 0.1.0. | `npm run module:doctor` green, native and browser packages, Spring comparison for the gain path, no hardware claim. |
| M2 | FILTER and BOTH. Single cutoff, DEP as depth, Q as resonance. Benchmark against Spring on both cores with moving knobs and trig splits. | The cost sits in Spring's range, or the overage is written down and reviewed. |
| M3 | Only with a named owner decision: sample-track plan B, as its own module, after the shared voice write lives in the base rather than in FM Synth. | Not started from M1's branch. |

M1's README has to say, in one place, which edges it follows and which it does not. Emulator playback is not hardware qualification.

## Risks

- **The note edge is shared with FM Synth.** If the only clean observation is a detour that module already owns, design 1 cannot be combined with FM Synth. That is a documented conflict, not a silent one, and it may push the ship to design 2.
- **Stacked envelopes.** With the stock hold left at a short value, the new gain envelope multiplies a shape that is already closing. The tutorial has to set ATK 0, HOLD infinite, REL infinite before judging the new shape.
- **Zipper and clicks.** Frame steps on a gain or a cutoff need a per-sample ramp. Release 0 must be a short fade, not the DSP's one-sample cut, unless ONCE asks for a cut on purpose.
- **Filter is not the stock filter.** Musicians will expect BASE and WIDTH. The panel names and the overview have to say this is one cutoff.
- **Master track.** The manual limits a master track's track pages. Whether this effect can sit on the master is unverified and stays out of M1's claims.
- **Layout.** WDTH's byte is reserved undrawn. Giving it a new count, or sliding MODE onto another slot, is the change that breaks saved Parts. That version stamps defaults.

## Ranked summary

| Rank | Approach | What it gives | Why it sits here |
| --- | --- | --- | --- |
| 1 | Insert effect, amplitude then filter, note-gated if M0 finds an edge | Sustain, decay, release, curve, bipolar depth, on level and on one cutoff, either slot, stock filter kept | Matches the gap. Gain is cheap beside Spring. One module, no dependency. Blocked only on the note-edge read. |
| 2 | Same effect, sequencer-grid gate | The same knobs for sequenced parts, with swing and track speed | Ship this if M0 fails. Say plainly that live keys and TRIG LEN are outside it. |
| 3 | ColdFire writer into VOL and stock-filter BASE | An ADSR with no new audio code | Fights the knobs and the locks. Same missing edge. A probe, not a product. |
| 4 | Sample-track copy of FM Synth's open-envelope gain | The AMP page itself becomes the new shape | Right for amplitude, wrong for the filter, and it collides with the synth engine. Later, and only as its own change to the base. |
| 5 | Replace the stock multi-mode filter | Sustain on the familiar BASE/WIDTH filter | Removes the stock effect from both slots. Not worth it. |
| 6 | No module: LFO ONE, the designer, HOLD infinite | One-shot shapes and a full-level keyboard hold | Already shipped with the instrument. Use it when the request is a shape rather than a sustain level. |

**Build rank 1** of that list only if the goal is a new shape. Spend M0 on the note edge before writing DSP. If that edge is not free of FM Synth, ship rank 2 under the same twelve knobs and do not call it a keyboard envelope. Leave the stock amplitude page and the stock multi-mode filter where they are.

## Finer control of the stock envelopes

This section answers a different request: keep AMP ATK, HOLD and REL, and the multi-mode filter's own attack and decay, and make those knobs finer. No new envelope stage, no new effect id.

### How a knob becomes a time

Every one of these parameters is a byte, 0–127, on the panel, in the Part, and in a parameter lock. The bank file stores one byte per lockable parameter per step, `0xff` meaning no lock. AMP attack, hold and release are lock slots 12–14. An effect's six main-page knobs are slots 18–23 (FX1) and 24–29 (FX2). A bipolar value is stored as the panel value plus 64. That layout is measured in `sdk/octabam/tools/hw/ot_bank.py`. The filter's setup knobs, including which parameter its envelope moves, are not in those 32 bytes. E-Verb's notes say the same thing for every stock effect: locks, LFOs, scenes and MIDI CC reach the six main-page knobs only.

The live DSP record is wider than the byte. FM Synth writes AMP attack, hold and release as halfwords, `value << 8`, so the knob sits in the high byte and the low byte is zero (`sdk/octabam/modules/synth/upstream/synth/README.md`, the DSP-facing override). On the playback page the same packing is used, and that write-up says the low byte is what lets an LFO or a scene land between two knob values. Scene morph and the LFO stage are the last writers of the voice record before it is shipped to the DSP. So the stock machine already has an 8-bit fraction under the 7-bit knob. What is not measured is whether the amplitude envelope and the filter envelope *consume* that fraction or take only the high byte. A crossfader parked between two scenes one step apart, on attack and on the filter's decay, is the test. Until it is done, a finer value written into the low byte is a guess.

The ColdFire side publishes the byte. The sample-by-sample ramp is the DSP's. For a synth track, FM Synth took that ramp over and left the DSP envelope open; its tables (`po_atk`, `po_relk`, `po_hold128`) were generated to match a stock FLEX measurement, and they are not a copy of the DSP's table. The DSP's own representation, a table or an instruction sequence, is not in this repository and does not belong in it. The filter's attack and decay are inside the multi-mode filter effect. No time for them is recorded here. ColdFire only delivers the six main-page bytes.

### The step size, from the published amplitude laws

Attack and release, as the synth engine states the DSP's law, share an exponent. Each step is about 8.5% longer than the one below it (`2^(1/8.53)`). The absolute gap therefore grows with the knob. These are that formula and the points the write-up states, not a new listening test. The formula at the stated points lands within a few percent (attack 8 is 7.4 ms against the stated 7.5; attack 64 is 698 ms against 700; attack 96 is 9.4 s against 9.45).

| Knob | Bottom | Middle | Top, before the special value |
| --- | --- | --- | --- |
| ATK | 0 is 3.85 ms, and the next step is about 0.3 ms. Value 8 is the stated 7.5 ms. | 32 is 50 ms, a step of about 4 ms. 64 is 700 ms, a step of about 60 ms. | 96 is 9.45 s, a step of about 0.8 s. Value 127 does not follow the formula: the ramp stops about 21.5 dB down. |
| REL | The formula at 0 is 0.3 ms, but the DSP's 0 is a one-sample cut. 40 is 7.6 ms, a step under 1 ms. | 60 is 38.5 ms. 80 is 196 ms, a step of about 17 ms. | 100 is 994 ms. 126 is 9 s. 127 is infinite, not a longer tau. |

Hold has no published per-step law. At 120 BPM the stated points are 32 → 282 ms, 64 → 1132 ms, 100 → 5.5 s, and 127 → infinite. From 32 to 64 the time grows about fourfold, so the milliseconds per click are increasing. The manual calls the hold a count of sequencer steps when SYNC is on. These points are not an integer number of sixteenths at 120 BPM (one sixteenth is 125 ms), and this note does not invent the conversion. SYNC off is unmeasured.

The synth engine's own playback does not follow the attack formula to the top. Its gain step is a Q15 integer, and from attack 91 upward that step is stuck at 1, which is an 11.9 s ramp. That collapse is the engine, not a stock-DSP measurement. Release 0–15 in the engine is floored near a 1 ms tau, where the DSP's 0 is a cut.

The filter envelope has 128 steps and no published time. Do not reuse the amplitude table for it.

### Where a change would sit

A finer reading that the stock DSP already understands is a ColdFire change: the knob handler, the formatter that draws the box, or the halfword published after scenes and LFOs. It does not upload DSP code.

The DSP loader is the wrong tool here. Its early hardware runs stopped the frame engine, and when frames stop the sequencer sticks on the first step (`docs/OCTATRACK_HARDWARE_TRAPS.md`, "DSP loader"). Later aligned builds kept frames running through an upload, but the loader is still the path that has wedged the cores. Anything in this section publishes a value the stock envelope already reads. Replacing the filter's coefficient routine would be the loader, or a static patch of that effect, and both are out of scope.

FM Synth already writes the three amplitude halfwords on a synth track. A second writer on those words fights it. Sample tracks are the place a publish-side remap is free. The AMP SETUP detours and the spare sixth box are taken by LEG in that fork; a range byte does not go there.

### The options

**1. A range switch, stock law by default.** One new saved value per track, defaulting to the law above, so an old Part sounds the same. A second value, short, publishes a remapped index: the musician's 0–126 covers a narrow band of the stock curve, and 127 stays the stock special (infinite hold and release, the anomalous attack). The DSP still sees a 7-bit index, or a 7-bit index plus a fraction if the low-byte test passes. Musical value is at the long end, where one click is already a large fraction of a second; the short band spends the 128 steps there. UI is one word on a setup or project row, not a gesture on the knob. FUNC+turn on a 0–127 knob already jumps to an end (the synth write-up; some effect knobs also stop at the centre). The encoder push, on pitch, makes the step coarser, not finer. Neither gesture is the range switch. Cost is a byte and a remap when the frame publishes, ColdFire only. Risk is a byte that stock already uses, and a short law that surprises someone who copies a Part onto a build without the module (the byte must read as stock when the module is absent). No loader.

**2. The low byte, once it is shown to count.** The halfword has 256 fractions under each knob step. Writing them is the actual increase in resolution, and it needs no new time table. UI: turn while the encoder is held, only if that hold is free on these knobs. It is not free on pitch. The box prints the time, not the raw word. A five-character string already fills an FM Synth box (`774ms` in that write-up), so the formats that fit are `7.6ms`, `700ms`, `1.1s`, `9.4s`, `INF`. Cost is the formatter plus a few instructions in the knob handler. Risk: if the DSP ignores the low byte, the gesture does nothing audible. P-locks and the Part byte stay 7-bit, so a lock or a reload snaps back to the click. Live playing and a scene crossfade would be the fine path; the sequence would not keep it. No loader.

**3. Print the time on the stock clicks.** The formatters for attack, hold and release draw milliseconds from the law above, including infinite and the anomalous attack. The filter's attack and decay stay numeric until their law is measured. This does not add resolution. It makes the 8.5% spacing visible, which is what tells a musician that the top of the knob is the coarse end. Same five-character budget. ColdFire, UI thread, no publish change, no save change, no loader. It is the display half of option 2 and worth shipping with option 1 even if the low byte is dead.

**4. Tempo-synced attack and release.** SYNC already exists. The manual says it chooses whether the amplitude envelope follows tempo. The published attack and release formulas have no tempo term, and the hold points are given at one tempo, so it is unmeasured whether SYNC already scales attack and release or only the hold. The first job is that measurement. If attack and release are absolute, a second SYNC behaviour can publish a step count from the stock tempo and the track speed, the way hold is described, instead of a millisecond. That is a coarser grid on purpose, useful when a decay should be a sixteenth, and it is not finer. The filter has no SYNC of its own; its setup can couple its envelope to AMP HOLD. ColdFire publish, instrument tempo, no private clock, no loader. Risk is overriding a SYNC that already does this.

**5. A curve per segment.** AMP SETUP's ATCK is already LIN or LOG, for the attack only. Release is exponential in the measurement. The filter has no curve control. Offering LIN release, or a curve on the filter, changes the shape the DSP was built to run. If that shape is hard-wired, the only implementation is to own the ramp, which is the new envelope the previous section ranked, not a finer knob. Leave it. The existing ATCK control is the curve the instrument already gives.

**6. High-resolution MIDI.** Audio CC in and out are 7-bit. Attack, hold and release are CC 22, 23 and 24 on the track's trig channel (manual appendix C.7). With the multi-mode filter in a slot, its main page is listed BASE, WIDTH, Q, DEPTH, ATK, DEC, so attack and decay are FX parameter 5 and 6: CC 38 and 39 in FX1, CC 44 and 45 in FX2. CC Map's handler is also 7-bit, and only for effect setup. Standard 14-bit pairing uses CC 32–63 as the LSB of CC 0–31, and that range is already the other audio parameters (CC 54 is All Arm, CC 48 is the crossfader). NRPN select is CC 98 and 99, which CC Map's notes say tail-call stock rather than being taken as audio parameters. An NRPN can carry a fine value without colliding with CC 22–24, and it is worth a ColdFire MIDI hook only after option 2 exists. Until the destination has more than 128 steps, NRPN and 14-bit CC add nothing a 7-bit CC does not. No loader. Risk is consuming NRPN that stock or another module already uses; the hook has to tail-call when the NRPN is not one of these parameters.

**7. Finer parameter locks.** This is the one musicians would feel in a sequence, and it does not fit the file. A step has 32 lock bytes and no spare for a fraction (slots 30 and 31 are present and undecoded; they are not a place to hide a fine value). A sidecar table in the project, on the quantizer's pattern of comment lines the stock loader skips, would survive a save and would be dropped by trig copy, paste, and a stock load that never sees it. Default remains the 7-bit lock, so old patterns are unchanged. Do not do this in the first version. A range switch (option 1) makes the existing lock byte finer in time without a new lock format, which is the compatible version of the same wish.

### Minimal first slice

ColdFire only. No DSP upload, no new effect, no new envelope stage, no change to a project that leaves the new value at its default.

1. On the emulator, park a scene crossfade between two attack values one apart, and do the same for the filter's decay. Record whether the time moves inside the step. That decides option 2. It writes no firmware into the repository.
2. Ship option 3 for the amplitude knobs, and option 1 with two words, STOCK and SHORT, default STOCK. SHORT remaps 0–126 into the band where the stock steps are coarsest (around the stated 700 ms to 9 s region) and leaves 127 alone. The published value is still a stock index. Filter attack and decay wait on their own measurement; the same switch can cover them once that law exists.
3. Option 2 joins the slice only if step 1 says the low byte is audible, and only as a live gesture, with the time printed in the box. Locks stay 7-bit.
4. Leave NRPN, lock sidecars, release curves and the DSP loader out.

## Ranked summary, finer stock knobs

| Rank | Approach | Musical value | UI | Where | Cost | Risk | Loader |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Range switch, default the stock law | The 128 steps cover the long, coarse end instead of 4 ms through minutes | One word, STOCK or SHORT | ColdFire publish of the existing byte | A remap per frame on tracks that leave STOCK | A saved byte stock already uses; a build without the module must still read as stock | No |
| 2 | Low byte under the knob, after the scene test | Real steps inside one click, if the DSP reads the fraction | Push-turn only if that hold is free; the box shows the time | Knob handler and the halfword | Small, UI plus one word | Silent if the DSP ignores the fraction; locks and reloads snap to the byte | No |
| 3 | Print milliseconds on the stock clicks | None added; the coarse top becomes visible | Five characters: `700ms`, `9.4s`, `INF` | The slot formatter | UI thread only | A string that touches the box edge | No |
| 4 | Tempo-synced attack and release, after measuring SYNC | Decays land on sixteenths. Not a finer millisecond | The existing SYNC word, or one added behaviour | ColdFire, from the stock tempo | Small | May duplicate a SYNC that already scales these | No |
| 5 | NRPN into the low byte | External control of rank 2 | None on the panel | MIDI in, then the same halfword | A dispatch hook that tail-calls | Useless until rank 2 is real; must not swallow stock NRPN | No |
| 6 | A finer lock byte | The sequence keeps the fine value | None, if the sidecar is invisible | Project file, outside the 32 lock bytes | A second store, and every trig copy | Copy, paste and a stock load drop it | No |
| 7 | A new curve on release or on the filter | A different shape, which is the previous section's problem | A setup word | Owning the ramp | A new envelope | Out of this request | No |

**First slice:** the scene test, then the time formatter and the STOCK/SHORT switch. The low byte is in that slice only if the test hears it. NRPN and finer locks wait. The DSP loader stays out.
