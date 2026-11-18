"""Turing MIDI generator: a USB runtime package for Modwerk base 0.7.9.

The base owns the generator registry and note-key event. Hardware untested.
"""
from remix.schema import Category, Detour, Gate, Kind, Linked, Module, Proof
from remix.stock_guard import stock_guard

MODULE = Module(
    name="turing-machine",
    key="TURING MACHINE",
    kind=Kind.CF_PATCH,
    doc="Live Turing MIDI generator: MODE per pattern; LOCK/LEN/SCAL/DENS per Part. "
        "AMP: main page; FUNC+AMP: SCALE/ROOT; encoder A push: WRITE.",
    category=Category.MIDI_USB, author="pmsorhaindo", author_url="https://github.com/pmsorhaindo",
    proof=Proof.PORT, proof_note="its emulator gate under the ColdFire port; not on hardware",
    linked=(
        Linked("tm", "modules/turing-machine/turing.s", cpu="54455", dram=True),
        Linked("tm_scale", "../machines/octatrack/modwerk_scale.s", cpu="54455", dram=True),
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
        Detour(0x40085404, stock_guard(0x40085404, 10, "b678e29e402f630cea4aed162fe7ec87d558348e8f2bf305f199263e67cf1bec"), "tm", "tm_project_loaded_hook",
               "Wait for complete bank restoration before migrating legacy Turing settings", pad_to=10),
        Detour(0x4008822a, stock_guard(0x4008822a, 6, "feb878879999fda6d8d14c43f5afbc4d7b778eafdbed492f294544560ac32889"), "tm", "tm_load_line_hook",
               "project loader's next-line point: read #TURING_B<b>_P<p>_T<n>=<mode>,<lock>,<len>,<scal>,<dens>[,<register>] (OCTABAM9's shorter lines and OCTABAM8's #TURING_T<n> too) on the storing pass",
               kind="jmp"),
        Detour(0x400888d2, stock_guard(0x400888d2, 8, "c93f3a2c7188693aeda0ad3c695584bdf927b5c8ce67892c744d1fe7040dd274"), "tm", "tm_write_hook",
               "project writer, after PATTERN_CHANGE_AUTO_SILENCE_TRACKS: a #TURING_B<b>_P<p>_T<n> line per pattern's track not at the defaults",
               kind="jmp", pad_to=8),
        Detour(0x40025ad4, stock_guard(0x40025ad4, 6, "866c4c6d5bddd948c550e349f2018ee46e8d49420d2ec956744e34d0af13b084"), "tm", "tm_defaults_hook",
               "project defaults (cold boot, no project, a new project): every track OFF",
               kind="jsr"),
        Detour(0x4004ecfc, stock_guard(0x4004ecfc, 8, "4c0570fc6ef0682508e64de2367e111c27f895b6b78e58c300b3f2e7b8010118"),
               "tm", "tm_push_hook",
               "encoder-push handler entry: knob A pushed and released on the TURING page with MODE ON writes the Turing sequence into the track's trigs (WRITE, popup MIDI TRACK WRITTEN); stock goes on",
               kind="jmp", pad_to=8),
        Detour(0x4009fb58, stock_guard(0x4009fb58, 6, "b9fd3e826833844716d1d4904ee373c65d291047e78b9f34f8d9e3c95dac30fd"),
               "tm", "tm_note_key_entry", "Turing local scale snap after TRAN"),
    ),
    gates=(Gate("modules/turing-machine/verify.py", remix_arg=False, venv=True),),
)
