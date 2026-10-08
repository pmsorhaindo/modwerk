"""TURING MACHINE -- a Music Thing Modular style looping shift register on one
Octatrack MIDI track (M1 prototype: fixed 16-step loop, chromatic notes).

The note hook is the head of the stock MIDI-track chord loop at 0x4009fb2e,
inside the MIDI sequencer routine 0x4009f794 (traced under the ColdFire port,
docs/turing-machine-feasibility.md section 7): d7 = track, d4 = chord slot,
a2 -> the four resolved notes (NOTE, NOT2..NOT4; -1 = none) in a stack array,
before TRAN is added and the note is queued. On the selected track the
register advances once per firing trig and every chord slot moves up by
0..24 semitones from the trig's own NOTE. The stock note-off sends the note
recorded after the hook, so a moved note is the note released.

Two rows on PROJECT > CONTROL > MIDI SEQUENCER, under CC DIRECT CONNECT:
TURING TRACK (OFF, T1..T8) and TURING LOCK (0..127, 64 = random, 127 = the
phrase repeats). The page's label, getter and setter arrays are grown and
its row count goes from 1 to 3; the page already indexes its rows from the
scroll offset, so no draw detour is needed. Settings are battery-RAM bytes
(turing.h), like CC DIRECT CONNECT's: global, not per project.

Measured under the port (TESTING.md); not run on hardware.
"""
from remix.schema import Category, Detour, Gate, Kind, Linked, Module, Poke, Proof, TableGrow
from remix.stock_guard import stock_guard

MODULE = Module(
    name="turing-machine",
    key="TURING MACHINE",
    kind=Kind.CF_PATCH,
    doc="PROJECT > CONTROL > MIDI SEQUENCER > TURING TRACK / TURING LOCK: one MIDI "
        "track's notes come from a 16-step looping shift register, 0..24 semitones "
        "above each trig's NOTE; LOCK 127 repeats the phrase, 64 is random.",
    category=Category.MIDI_USB, author="pmsorhaindo", author_url="https://github.com/pmsorhaindo",
    proof=Proof.PORT, proof_note="its emulator gate under the ColdFire port; not on hardware",
    linked=(
        Linked("tm", "modules/turing-machine/turing.s", cpu="5475", dram=True),
    ),
    detours=(
        Detour(0x4009fb2e, stock_guard(0x4009fb2e, 6, "c51d1ea289bd31b3ae87a587ac9c17dd9a97ffebbe73d44bb72a3605d978845a"),
               "tm", "tm_note_hook",
               "MIDI-track chord loop head: on chord slot 0 of the selected track, move NOTE..NOT4 by the register's value",
               kind="jmp"),
    ),
    tables=(
        TableGrow("MIDI SEQUENCER labels", old=0x400b2838, count=1,
                  symbols=(("tm", "tm_label_track"), ("tm", "tm_label_lock")),
                  refs=((0x40065f12, 0x400b2838),)),
        TableGrow("MIDI SEQUENCER getters", old=0x400b283c, count=1,
                  symbols=(("tm", "tm_get_track"), ("tm", "tm_get_lock")),
                  refs=((0x40065f1e, 0x400b283c),)),
        TableGrow("MIDI SEQUENCER setters", old=0x400b2840, count=1,
                  symbols=(("tm", "tm_set_track"), ("tm", "tm_set_lock")),
                  refs=((0x40066024, 0x400b2840), (0x4006609e, 0x400b2840),
                        (0x400660b8, 0x400b2840), (0x400660d2, 0x400b2840))),
    ),
    pokes=(
        Poke(0x40065fdc, expect=stock_guard(0x40065fdc, 4, "b89b9000e01202d3695f44f1aba436aeb8fbd7545a1e76d94df685072615837d"),
             write=bytes.fromhex("48780003"),
             note="MIDI SEQUENCER page: 1 -> 3 rows (CC DIRECT CONNECT, TURING TRACK, TURING LOCK)"),
    ),
    gates=(Gate("modules/turing-machine/verify.py", remix_arg=False, venv=True),),
)
