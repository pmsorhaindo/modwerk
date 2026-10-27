"""TURING MACHINE -- Music Thing Modular style looping shift registers on the
Octatrack's MIDI tracks: one per track, each with its own LOCK and LENGTH.

REPLACE mode (OCTABAM8, reworked in OCTABAM9; OCTABAM10: a 64-step register,
the Turing Machine's LOCK curve, SCAL, DENS and WRITE; OCTABAM11: LEN 2..7 a
loop of whole notes, the register kept as at the pass's first step): on a track whose MODE
is ON in the pattern being played, the track's trigs make no notes and every
step of its sequencer is a note or a rest (DENS) from that pattern's register. The MIDI
per-step trig evaluator 0x4009cf4c(track, bank, pattern, step, slot), which
the step scheduler calls for every step of every MIDI track, is detoured at
its entry: for such a track stock's evaluation runs first (condition,
bitmaps, the step's lock record), then a note step becomes a note trig (event
29, one note, the step's swing, no microtiming) whose lock record is
stock's (or none), with the register's note, spread over SCAL's range
around the step's NOTE lock or the Part's NOTE, written as its NOTE lock; a
rest sends no note (a trigless trig with stock's locks when stock scheduled
the step); the track's condition result follows (what NEI reads). The tick ISR applies the
record as any trig's, so VEL/LEN/CC locks, the LFO, TRAN, the arpeggiator
and its KEY act on the Turing note in stock code. The record's byte 30-31
(never read by stock) tag the step; in the note routine (0x4009fa2a, before
the arpeggiator's input and the mute check) a tagged step drops NOT2..NOT4
and is recognised. The register a track plays lives in DRAM; the pattern's
first step writes it to the cell, and a step that does not follow on (PLAY,
MODE ON, a pattern change, a load) starts from the cell's register clocked to
that step, so a locked phrase keeps its place on the pattern across STOP,
SAVE, RELOAD and a power cycle. The first step after PLAY is evaluated at STOP; PLAY (0x4009c076,
before the first step is copied) swaps in the Turing step for an ON track.
MODE, LOCK, LEN, SCAL, DENS and the 64-bit register are kept per pattern and
track in battery RAM (0x100f9000..0x100ff000, a zeroed entry is the defaults;
OCTABAM9's entries are converted once; the flip random state is per track at
0x100ffe40), so a pattern
change follows the new pattern's and a power cycle keeps them. Each register
is seeded from a once-per-boot seed (DMA timer 3's count at the first Turing
step, or a test seed record, turing.h), the track and the pattern.

The TURING page: on a MIDI track AMP's pages are a ring, MIDI ARPEGGIATOR
-> MIDI ARP SETUP -> MIDI TURING -> back. A double tap of AMP shows the next
page, a single press the first one (ARP, or TURING when TURING FIRST is ON);
FUNC+AMP opens ARP SETUP as stock. Knobs A..E = MODE (the track's Turing
on/off) / LOCK (64 = random, 96..127 = locked, 25 = slip; FUNC snaps
0/64/127) / LEN (2..64) / SCAL (pitch range, 0 NOTE only .. 127 four
octaves) / DENS (0 silent .. 127 every step) of the active track; pushing
knob A with MODE ON writes the sequence into the track's trigs (WRITE, the
stock popup "MIDI TRACK WRITTEN"; the encoder-push handler 0x4004ecfc). A runtime copy of the stock ARP
descriptor (no stock bytes here) served by the resolver while that page
shows; four detours (the same-page key handler, the page setter, the
resolver's ARP load, the knob routine after its resolve).

One row on PROJECT > CONTROL > MIDI SEQUENCER, under CC DIRECT CONNECT:
TURING FIRST (OFF, ON; project-wide). The page's label, getter and setter
arrays are grown and its row count goes from 1 to 2. The live settings are
a checksummed battery-RAM record, so a power cycle (which reads no project
file) keeps them. They are saved per project: a pattern's track not at the
defaults is written as "#TURING_B<b>_P<p>_T<n>=<mode>,<lock>,<len>,<scal>,<dens>[,
<the register as four 16-bit numbers>]" (OCTABAM9's 3/6-number lines load
with SCAL 64, DENS 127) and TURING FIRST ON as "#TURING_FIRST=1" in project.work,
lines stock loaders skip (OCTABAM8's "#TURING_T<n>=..." loads into every
pattern); a storing load and a new project start from every pattern OFF and
TURING FIRST OFF. The four
project sites neighbour Scale Quantizer's own (0x400866cc, 0x400867a2,
0x400888aa, 0x40025ac2) without sharing one.

Measured under the port (TESTING.md). The trig-reshaping note path ran on
hardware as OCTABAM4 (23 Oct 2026) and with the page ring and TURING FIRST as
OCTABAM74 (25 Oct 2026); REPLACE mode (OCTABAM8, OCTABAM9 on hardware since
25 Oct 2026, behaviour reported) and OCTABAM10 (26 Oct 2026, MIDI captured,
brief 9's fixes in OCTABAM11) have not been measured there.
"""
from remix.schema import Category, Detour, Gate, Kind, Linked, Module, Poke, Proof, TableGrow
from remix.stock_guard import stock_guard

MODULE = Module(
    name="turing-machine",
    key="TURING MACHINE",
    kind=Kind.CF_PATCH,
    doc="MIDI track: double-tap AMP to step ARP -> ARP SETUP -> TURING (MODE / LOCK / LEN); "
        "PROJECT > CONTROL > MIDI SEQUENCER > TURING FIRST puts TURING first. With MODE ON "
        "the track's trigs make no notes and every step is a note or a rest from a looping shift "
        "register (2..64 steps): LOCK (64 random, 96+ locked, 25 slip; FUNC snaps), LEN, SCAL "
        "(pitch range around NOTE), DENS (notes vs rests); the step's locks apply; push knob A "
        "to WRITE the sequence into the track's trigs. Settings and register per pattern.",
    category=Category.MIDI_USB, author="pmsorhaindo", author_url="https://github.com/pmsorhaindo",
    proof=Proof.PORT, proof_note="its emulator gate under the ColdFire port; not on hardware",
    linked=(
        Linked("tm", "modules/turing-machine/turing.s", cpu="5475", dram=True),
    ),
    detours=(
        Detour(0x4009fa2a, stock_guard(0x4009fa2a, 6, "1a818bb964bc3b78d3f8eac772a8ce85ac6df50971c59376a8e954d91d547117"),
               "tm", "tm_chord_hook",
               "MIDI note routine, a step firing, before the arpeggiator's input: a Turing step (its record tagged) drops NOT2..NOT4, one note a step",
               kind="jmp"),
        Detour(0x4009cf4c, stock_guard(0x4009cf4c, 8, "dc335d0aed0cc4febec4501776825159505f5b413de340f6e74208856577c47b"),
               "tm", "tm_eval_hook",
               "MIDI per-step trig evaluator entry: on a track whose TURING MODE is ON in the pattern every step is a note trig (or a rest, DENS) from the register, with the step's own locks (stock evaluates them and the condition); swing kept, no microtiming",
               kind="jmp", pad_to=8),
        Detour(0x4009c076, stock_guard(0x4009c076, 6, "76a4f6d1f0d5e7cd6237305e04fe6217524882ec299e152ebbc427bea2661e8e"),
               "tm", "tm_play_hook",
               "PLAY, before the first step is copied: a track whose TURING MODE is ON in the first step's pattern gets the Turing step (the register advances at PLAY)",
               kind="jmp"),
        Detour(0x400866ee, stock_guard(0x400866ee, 6, "5cf9e6109ce8cb58a9bf4dc66339e546dd063412195eeb9d8290218748e8fdd2"), "tm", "tm_load_entry_hook",
               "project loader, after its frame: a storing load starts from every track OFF",
               kind="jmp"),
        Detour(0x40088224, stock_guard(0x40088224, 6, "5cf9e6109ce8cb58a9bf4dc66339e546dd063412195eeb9d8290218748e8fdd2"), "tm", "tm_load_line_hook",
               "project loader's next-line point: read #TURING_B<b>_P<p>_T<n>=<mode>,<lock>,<len>,<scal>,<dens>[,<register>] (OCTABAM9's shorter lines and OCTABAM8's #TURING_T<n> too) on the storing pass",
               kind="jmp"),
        Detour(0x400888d2, stock_guard(0x400888d2, 8, "c93f3a2c7188693aeda0ad3c695584bdf927b5c8ce67892c744d1fe7040dd274"), "tm", "tm_write_hook",
               "project writer, after PATTERN_CHANGE_AUTO_SILENCE_TRACKS: a #TURING_B<b>_P<p>_T<n> line per pattern's track not at the defaults",
               kind="jmp", pad_to=8),
        Detour(0x40025ad4, stock_guard(0x40025ad4, 6, "866c4c6d5bddd948c550e349f2018ee46e8d49420d2ec956744e34d0af13b084"), "tm", "tm_defaults_hook",
               "project defaults (cold boot, no project, a new project): every track OFF",
               kind="jsr"),
        Detour(0x400322f0, stock_guard(0x400322f0, 6, "a1996a6c76af4b5fdde21154ee36fc6ac996e43e56705def1ae80989f4c4edfe"),
               "tm", "tm_pagekey_hook",
               "page key pressed on its own page: AMP on a MIDI track steps the ring ARP -> ARP SETUP -> TURING (double tap) or shows the first page (press)",
               kind="jmp"),
        Detour(0x400554e0, stock_guard(0x400554e0, 8, "d43e64e0210fdd98e9dd8476d7cea57c93492ec611d50eddcbf6fd90ea80cef7"),
               "tm", "tm_setpage_hook",
               "page change (the only writer of the page kind 0x460d1684): AMP arriving shows its first page, ARP SETUP opens over ARP",
               kind="jmp", pad_to=8),
        Detour(0x40031dea, stock_guard(0x40031dea, 6, "1dc2f0ca1a8241e4c7998227cd891033ed388df47132b04c3421bfea7eb036ab"),
               "tm", "tm_resolve_hook",
               "page resolver, MIDI ARP: the TURING descriptor (a runtime copy of ARP's) while that page shows on the current track",
               kind="jmp"),
        Detour(0x4005502a, stock_guard(0x4005502a, 6, "3d95d0b834d9d683b9fc370f213c9a44f70efe788b591199e54ee229e36f7214"),
               "tm", "tm_knob_hook",
               "knob routine after its resolve: the TURING page's knobs edit MODE/LOCK/LEN/SCAL/DENS (FUNC+LOCK snaps 0/64/127), no ARP byte is written",
               kind="jmp"),
        Detour(0x4004ecfc, stock_guard(0x4004ecfc, 8, "4c0570fc6ef0682508e64de2367e111c27f895b6b78e58c300b3f2e7b8010118"),
               "tm", "tm_push_hook",
               "encoder-push handler entry: knob A pushed and released on the TURING page with MODE ON writes the Turing sequence into the track's trigs (WRITE, popup MIDI TRACK WRITTEN); stock goes on",
               kind="jmp", pad_to=8),
    ),
    tables=(
        TableGrow("MIDI SEQUENCER labels", old=0x400b2838, count=1,
                  symbols=(("tm", "tm_label_first"),),
                  refs=((0x40065f12, 0x400b2838),)),
        TableGrow("MIDI SEQUENCER getters", old=0x400b283c, count=1,
                  symbols=(("tm", "tm_get_first"),),
                  refs=((0x40065f1e, 0x400b283c),)),
        TableGrow("MIDI SEQUENCER setters", old=0x400b2840, count=1,
                  symbols=(("tm", "tm_set_first"),),
                  refs=((0x40066024, 0x400b2840), (0x4006609e, 0x400b2840),
                        (0x400660b8, 0x400b2840), (0x400660d2, 0x400b2840))),
    ),
    pokes=(
        Poke(0x40065fdc, expect=stock_guard(0x40065fdc, 4, "b89b9000e01202d3695f44f1aba436aeb8fbd7545a1e76d94df685072615837d"),
             write=bytes.fromhex("48780002"),
             note="MIDI SEQUENCER page: 1 -> 2 rows (CC DIRECT CONNECT, TURING FIRST)"),
    ),
    gates=(Gate("modules/turing-machine/verify.py", remix_arg=False, venv=True),),
)
