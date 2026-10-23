# Extended amplitude and filter envelopes

**Date:** 23 October 2026
**Status:** Research only. No module, no firmware, no image.
**Instrument:** Octatrack, stock OS 1.40C as this repository builds it.

This note says what the stock amplitude and filter envelopes actually are, which extensions are already covered by modules in this tree, and which build is worth doing. It does not add Elektron firmware or a new effect.

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

**Build rank 1.** Spend M0 on the note edge before writing DSP. If that edge is not free of FM Synth, ship rank 2 under the same twelve knobs and do not call it a keyboard envelope. Leave the stock amplitude page and the stock multi-mode filter where they are.
