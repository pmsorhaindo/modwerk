"""TURING MACHINE -- Music Thing Modular style looping shift registers on the
Octatrack's MIDI tracks: one per track, each with its own LOCK and LENGTH.

The note hook is the head of the stock MIDI-track chord loop at 0x4009fb2e,
inside the MIDI sequencer routine 0x4009f794 (traced under the ColdFire port,
docs/turing-machine-feasibility.md section 7): d7 = track, d4 = chord slot,
a2 -> the four resolved notes (NOTE, NOT2..NOT4; -1 = none) in a stack array,
before TRAN is added and the note is queued. On a track whose MODE is ON its
register advances once per firing trig and every chord slot moves up by
0..24 semitones from the trig's own NOTE. The stock note-off sends the note
recorded after the hook, so a moved note is the note released. Each
register is seeded once per boot from DMA timer 3's free-running count at
the first Turing trig, which fires when PLAY is pressed, unless a test seed
record is present (turing.h).

Four rows on PROJECT > CONTROL > MIDI SEQUENCER, under CC DIRECT CONNECT:
TURING TRACK (T1..T8, the track the next three rows edit), TURING MODE
(OFF, ON), TURING LOCK (0..127, 64 = random, 127 = the phrase repeats) and
TURING LENGTH (2..16). The page's label, getter and setter arrays are grown
and its row count goes from 1 to 5 (four show; the page scrolls). It
already indexes its rows from the scroll offset, so no draw detour is
needed. Settings are a checksummed battery-RAM record: global, not per
project.

Measured under the port (TESTING.md); not run on hardware.
"""
from remix.schema import Category, Detour, Gate, Kind, Linked, Module, Poke, Proof, TableGrow
from remix.stock_guard import stock_guard

MODULE = Module(
    name="turing-machine",
    key="TURING MACHINE",
    kind=Kind.CF_PATCH,
    doc="PROJECT > CONTROL > MIDI SEQUENCER > TURING TRACK / MODE / LOCK / LENGTH: a MIDI "
        "track's notes come from a looping shift register (2..16 steps), 0..24 semitones "
        "above each trig's NOTE; LOCK 127 repeats the phrase, 64 is random.",
    category=Category.MIDI_USB, author="pmsorhaindo", author_url="https://github.com/pmsorhaindo",
    proof=Proof.PORT, proof_note="its emulator gate under the ColdFire port; not on hardware",
    linked=(
        Linked("tm", "modules/turing-machine/turing.s", cpu="5475", dram=True),
    ),
    detours=(
        Detour(0x4009fb2e, stock_guard(0x4009fb2e, 6, "c51d1ea289bd31b3ae87a587ac9c17dd9a97ffebbe73d44bb72a3605d978845a"),
               "tm", "tm_note_hook",
               "MIDI-track chord loop head: on chord slot 0 of a track whose TURING MODE is ON, move NOTE..NOT4 by its register's value",
               kind="jmp"),
    ),
    tables=(
        TableGrow("MIDI SEQUENCER labels", old=0x400b2838, count=1,
                  symbols=(("tm", "tm_label_edit"), ("tm", "tm_label_mode"),
                           ("tm", "tm_label_lock"), ("tm", "tm_label_length")),
                  refs=((0x40065f12, 0x400b2838),)),
        TableGrow("MIDI SEQUENCER getters", old=0x400b283c, count=1,
                  symbols=(("tm", "tm_get_edit"), ("tm", "tm_get_mode"),
                           ("tm", "tm_get_lock"), ("tm", "tm_get_length")),
                  refs=((0x40065f1e, 0x400b283c),)),
        TableGrow("MIDI SEQUENCER setters", old=0x400b2840, count=1,
                  symbols=(("tm", "tm_set_edit"), ("tm", "tm_set_mode"),
                           ("tm", "tm_set_lock"), ("tm", "tm_set_length")),
                  refs=((0x40066024, 0x400b2840), (0x4006609e, 0x400b2840),
                        (0x400660b8, 0x400b2840), (0x400660d2, 0x400b2840))),
    ),
    pokes=(
        Poke(0x40065fdc, expect=stock_guard(0x40065fdc, 4, "b89b9000e01202d3695f44f1aba436aeb8fbd7545a1e76d94df685072615837d"),
             write=bytes.fromhex("48780005"),
             note="MIDI SEQUENCER page: 1 -> 5 rows (CC DIRECT CONNECT, TURING TRACK, MODE, LOCK, LENGTH; four show)"),
    ),
    gates=(Gate("modules/turing-machine/verify.py", remix_arg=False, venv=True),),
)
