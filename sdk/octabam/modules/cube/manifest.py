"""CUBE: a wavetable source machine for audio tracks. Two oscillators over an
original 8 x 8 x 8 cube of 256-sample, 16-bit single cycles (modules/cube/
generate_cube.py), X/Y/Z morph, thru-zero FM from B into A, unison, TONE
quantisation, trig and hard sync. SRC page: PTCH FM MIX / X Y Z; a press of
SRC on it shows OSC B: BPCH LAW LINK / BX BY BZ; a double press of SRC (or
FUNC+SRC) opens SETUP: FINE OCT UNI / TONE MORPH SYNC. Pushing the UNI
encoder in SETUP cycles which oscillator unison detunes: A, B or BOTH.

Tracks 1-4 only. Static-stock (OCTABAM_STATIC_STOCK=1, upstream's default),
no DSP loader, and every stock effect kept: the voice (cube_voice.asm = the
seam stub cube_seam.asm + the engine cube_engine.asm) lives in DSP core 1's
free program memory above its stock records (payload B, P:0x1d9f.., 459 of
609 words; schema.DspSection.free_top), entered from Analog BD's track source
seam. Core 0 (tracks 5-8) has 33 free words, so T5-T8 do not offer CUBE: their
machine lists keep stock's five rows, and a CUBE signature there (a pasted
track, a CUBE1 Part) is put back to FLEX. The registration is Analog BD's
measured chooser/Part seams (machine row 5; the two cannot share an image).
Emulator-qualified only; not on hardware in this form.
"""
import pathlib
import sys
from remix.schema import (Category, Detour, DspHook, DspSection, Gate, Kind, Linked, Module, Poke,
                          Proof, SymbolRef)
from remix.stock_guard import stock_dsp_words, stock_guard

H = bytes.fromhex
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def data_include(_modules):
    """remix.inc for cube_data.s: the cube."""
    sys.path.insert(0, str(HERE))
    import generate_cube
    blob = ROOT / "out/cube/cube.bin"
    fresh = generate_cube.to_bin(generate_cube.cube())
    if not blob.exists() or blob.read_bytes() != fresh:
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(fresh)
    return "\n".join(["        .section .rodata", "        .balign 4", "        .global cube_waves",
                      "cube_waves:", f'        .incbin "{blob}"']) + "\n"


SEAM = stock_dsp_words("B", 0x1A2, 2, "e5789bc296dc4459ae42db3801b86bffe42ef74675547fd17f51cdc90e476315")

MODULE = Module(
    name="cube", key="CUBE", kind=Kind.HYBRID, category=Category.MACHINES,
    author="pmsorhaindo", author_url="https://github.com/pmsorhaindo",
    doc="CUBE wavetable machine: two oscillators over an original 8x8x8 cube; "
        "SRC PTCH FM MIX / X Y Z, OSC B (SRC again) BPCH LAW LINK / BX BY BZ, "
        "SETUP (double press SRC) FINE OCT UNI / TONE MORPH SYNC. Tracks 1-4; static-stock, "
        "no DSP loader, every stock effect kept.",
    proof=Proof.PORT, proof_note="emulator only (modules/cube/verify.py); not on hardware",
    linked=(
        Linked("cubemachine", "modules/cube/machine.s", dram=True),
        Linked("cube", "modules/cube/cube.s", dram=True),
        Linked("cubedata", "modules/cube/cube_data.s", dram=True, include=data_include),
    ),
    symbol_refs=(SymbolRef(0x400d6438, 0x40004008, "cube", "cube_render",
                           note="FLEX renderer: a signed CUBE track sends its control record"),),
    detours=(
        Detour(0x400791E4, stock_guard(0x400791e4, 8, "fa7132fac15d6e498fd0e73744e1f94218824f3f54d5b3bad6083b60363e9f14"),
               "cubemachine", "cube_pool_open", "track double-tap: a CUBE track has no sample pool", pad_to=8),
        Detour(0x400334D8, stock_guard(0x400334d8, 6, "d6c9f1f60272197a17511f496fc19dd21ddd7df5f1f1ec0cab7a16cad60b0609"),
               "cubemachine", "cube_machine_name", "format machine row 5 as CUBE"),
        Detour(0x4003C928, stock_guard(0x4003c928, 6, "237cd1acd4da7acb61dc7fda7c88e648a5186b36732f433b4dd91966c5a669af"),
               "cubemachine", "cube_src_names", "point SRC SETUP at six machine names", kind="lea"),
        Detour(0x4003D718, stock_guard(0x4003d718, 6, "53b8d23acf2c3fe0f794c0a5f37475b17c3433bc6a466e0e1861515989cfecda"),
               "cubemachine", "cube_name_a", "main page name lookup for the signed CUBE track"),
        Detour(0x4004C36A, stock_guard(0x4004c36a, 6, "53b8d23acf2c3fe0f794c0a5f37475b17c3433bc6a466e0e1861515989cfecda"),
               "cubemachine", "cube_name_b", "second main page name lookup for the signed CUBE track"),
        Detour(0x4003C980, stock_guard(0x4003c980, 6, "237e017ccd95444195ca390a3e6ca6076fbfa1f0931f2e7dfbdbee8c5ec72ca3"),
               "cubemachine", "cube_setup_row", "SRC SETUP row highlights CUBE on a signed FLEX track"),
        Detour(0x400786C8, stock_guard(0x400786c8, 4, "f829e3570d9d9e95b7d7b9b0433b1aad2f13c0ac087873dbf981482521301309"),
               "cubemachine", "cube_chooser_row", "main chooser row highlights CUBE on a signed FLEX track"),
        Detour(0x400585DC, stock_guard(0x400585dc, 10, "22fb6e2bea4520003d2fae7035c0cd57bcd6fe6f2cfdd5b70580a3f6f2a68034"),
               "cubemachine", "cube_setup_open", "SRC SETUP opens on CUBE for the CUBE track", pad_to=10),
        Detour(0x4005221E, stock_guard(0x4005221e, 10, "8f0fa4f7d6db857f695996b185b38b788fa6af0eacd86d7dd01e2ff61201ffed"),
               "cubemachine", "cube_tick_hook", "publish CUBE's page descriptor; the UNI encoder push",
               pad_to=10),
        Detour(0x40078886, stock_guard(0x40078886, 10, "fe6cb52458c7d968dc467c1cd7721d832baf6bc2fac1826c8c10ed07fee2e7f8"),
               "cubemachine", "cube_chooser_open", "the track's machine list opens on CUBE for the CUBE track", pad_to=10),
        Detour(0x40031E74, stock_guard(0x40031e74, 8, "bba32826863751ec568719c202735da1ba8f06560e4d375a80637ae6653caa8f"),
               "cubemachine", "cube_resolve_pb", "resolve CUBE's page (or OSC B's) without changing other FLEX tracks",
               pad_to=10),
        Detour(0x4007981C, stock_guard(0x4007981c, 6, "89c50ac3ca041fdf5647ec5ee2c3580f9a67dd79f0b5cc15ceadda4b9e9bede0"),
               "cubemachine", "cube_main_commit", "assign CUBE at the main chooser commit"),
        Detour(0x4005A616, stock_guard(0x4005a616, 6, "7a7350a69423ec41ec468a189ba167059626cb7f499d9862394d2388a23c8b59"),
               "cubemachine", "cube_src_commit", "assign CUBE at SRC SETUP commit"),
        Detour(0x4005A850, stock_guard(0x4005a850, 6, "7a7350a69423ec41ec468a189ba167059626cb7f499d9862394d2388a23c8b59"),
               "cubemachine", "cube_src_commit2", "the same at SRC SETUP's second commit path"),
        Detour(0x4003A52E, stock_guard(0x4003a52e, 8, "cae34bf50383462ed4f92d8044e3021247edb8bf69c17a9c7ead62f6edf79510"),
               "cubemachine", "cube_setup_edit6", "SETUP's editor stores CUBE's row in the track's FLEX slot", pad_to=8),
        Detour(0x4003CD98, stock_guard(0x4003cd98, 8, "ed71ef874312890edc87cef7e19cd8c0f8ac4ac9b90182c2364f78d3a4567f45"),
               "cubemachine", "cube_setup_draw6", "SETUP's drawer reads CUBE's row from the track's FLEX slot", pad_to=8),
        Detour(0x40002318, stock_guard(0x40002318, 8, "3d25d06bf11f3a7bccef894d0016b52adbb4ae468a0f475dd497d7b5966e2694"),
               "cubemachine", "cube_validate", "the Part validator reads a CUBE track's FLEX slots as FLEX defaults",
               pad_to=8),
        Detour(0x40055720, stock_guard(0x40055720, 8, "684371b3fd401a481c6051f2075ec73a1351144cbe1ba6b70b98b035693709c1"),
               "cubemachine", "cube_pagesel_hook",
               "page select: on a CUBE track a press of SRC on SRC shows OSC B and back; a double press opens SETUP", pad_to=8),
        Detour(0x40055030, stock_guard(0x40055030, 6, "055a629c6dc5b238b5301bf40e8fabd0719384e779c1fa6936c406e2b58546b4"),
               "cubemachine", "cube_knob_hook",
               "knob routine after its resolve: OSC B's knobs edit its Part bytes"),
        Detour(0x40040132, stock_guard(0x40040132, 10, "9a04d3b319401c726c5664118a6d9d252162d1264acbb06031ae92406761b622"),
               "cubemachine", "cube_letter", "track strip: a CUBE track's machine letter is c, not FLEX's F", pad_to=10),
        Detour(0x4003BFF2, stock_guard(0x4003bff2, 6, "6d3a05238393510d126d994050dab31053b5a64c8adddd87d51c20a00b9984c2"),
               "cubemachine", "cube_lfo_pmtr", "LFO SETUP PMTR names a CUBE track's own SRC parameters"),
        Detour(0x40079248, stock_guard(0x40079248, 8, "3ec3e33dc9eae9cfbe075a2a5e2697563293203896e3649ae7e7a718a6d7f34c"),
               "cubemachine", "cube_rows_main", "machine chooser: six rows (CUBE last) on T1-T4, stock's five on T5-T8",
               pad_to=8),
        Detour(0x400585FA, stock_guard(0x400585fa, 8, "28992093b4deda97ffa595ce8acd14c8a2a391c67871c1e8dd3421d97467a29d"),
               "cubemachine", "cube_rows_setup", "SRC SETUP selector: six rows on T1-T4, five on T5-T8", pad_to=8),
        Detour(0x40078678, stock_guard(0x40078678, 6, "c29a846c95212b4710bfddec551a50d6cf923af6a648a2f2f2af6398cc98e5a5"),
               "cubemachine", "cube_rows_draw", "machine chooser draws CUBE's row on T1-T4 only"),
    ),
    pokes=(
        Poke(0x4003C950, stock_guard(0x4003c950, 2, "74d01dadcbe6a57ef61bc53a5a65404cd8446c6738ff0ac86b1b1a78d8ae7d41"), H("7205"),
             "SRC SETUP name lookup admits CUBE"),
        Poke(0x400786CE, stock_guard(0x400786ce, 2, "04cd1c6d463ba6752ff68f9125991b1c4af983ae355b62366122ba2d47eee3b2"), H("7005"),
             "machine chooser highlights CUBE"),
        Poke(0x40079904, stock_guard(0x40079904, 2, "577d7ba37f9786ab02a7dc9eeb612bb55936018179b550b14f4b9f000a89bf20"), H("7605"),
             "machine chooser persists CUBE"),
    ),
    dsp=DspSection(asm="modules/cube/cube_voice.asm", priority=5, payloads=frozenset({"B"}), free_top=True,
                   hooks=(DspHook({"B": 0x1A2}, SEAM, "cs01",
                                  "track source seam (core 1, T1-T4): a CUBE record runs the built-in engine"),),
                   subst={"B": {"CONTADDR": "$221"}}),
    gates=(Gate("modules/cube/verify.py", remix_arg=False),),
)
