"""CUBE: a wavetable source machine for audio tracks. Two oscillators over an
original 8 x 8 x 8 cube of 256-sample, 16-bit single cycles (modules/cube/
generate_cube.py), X/Y/Z morph, thru-zero FM from B into A, unison, TONE
quantisation, trig and hard sync. SRC: PTCH X Y Z FM MIX; SETUP (FUNC+SRC):
FINE OCT UNI TONE MORPH SYNC; OSC B (a double tap of SRC from SETUP): BX BY
BZ LINK LAW BPCH. The SRC key's double tap walks SRC -> SETUP -> OSC B ->
SRC on CUBE tracks only.

The voice is a dynload SOURCE PACKAGE (cube_engine.asm): the ColdFire
uploads it into the top of the loader's P arena, one image per core that
has a CUBE track, while the sequencer is stopped, and binds it on id $1f
(platform/dsp-dynload-transport/manager.c, source packages: a base change).
A resident seam stub (cube_seam.asm) runs it for a CUBE track's record, or
renders silence until it is bound. The registration is Analog BD's measured
chooser/Part seams (machine row 5; the two cannot share an image).
Emulator-qualified only (diag/CLAUDE_REPORT5.md); not on hardware.
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
    """remix.inc for cube_data.s: the engine package and the cube."""
    sys.path.insert(0, str(HERE))
    import cube_pkg
    import generate_cube
    blob = ROOT / "out/cube/cube.bin"
    fresh = generate_cube.to_bin(generate_cube.cube())
    if not blob.exists() or blob.read_bytes() != fresh:
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(fresh)
    pkg = cube_pkg.package()
    w = pkg["words"]
    lines = ["        .section .rodata", "        .balign 4",
             "        .global cube_pkg_words, cube_pkg_reloc, cube_pkg_count, cube_pkg_nreloc",
             "        .global cube_pkg_init, cube_pkg_proc, cube_waves",
             f"cube_pkg_count: .long {len(w)}", f"cube_pkg_nreloc: .long {len(pkg['relocations'])}",
             f"cube_pkg_init: .long {pkg['init']}", f"cube_pkg_proc: .long {pkg['proc']}",
             "cube_pkg_words:"]
    lines += ["        .long " + ",".join(f"0x{v:06x}" for v in w[i:i + 8]) for i in range(0, len(w), 8)]
    lines += ["cube_pkg_reloc:", "        .word " + ",".join(str(r) for r in pkg["relocations"]),
              "        .balign 4", "cube_waves:", f'        .incbin "{blob}"']
    return "\n".join(lines) + "\n"


SEAM = stock_dsp_words("A", 0x39C, 2, "e5789bc296dc4459ae42db3801b86bffe42ef74675547fd17f51cdc90e476315")

MODULE = Module(
    name="cube", key="CUBE", kind=Kind.HYBRID, category=Category.MACHINES,
    author="pmsorhaindo", author_url="https://github.com/pmsorhaindo",
    doc="CUBE wavetable machine: two oscillators over an original 8x8x8 cube; "
        "SRC PTCH X Y Z FM MIX, SETUP FINE OCT UNI TONE MORPH SYNC, OSC B BX BY BZ LINK LAW BPCH "
        "(double tap SRC: SRC -> SETUP -> OSC B). The voice loads per core through dynload.",
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
               "cubemachine", "cube_tick_hook", "publish CUBE's page descriptor; ask for the engine while stopped",
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
               "page select: on a CUBE track the SRC double tap walks SRC -> SETUP -> OSC B -> SRC", pad_to=8),
        Detour(0x40055030, stock_guard(0x40055030, 6, "055a629c6dc5b238b5301bf40e8fabd0719384e779c1fa6936c406e2b58546b4"),
               "cubemachine", "cube_knob_hook",
               "knob routine after its resolve (and after TURING's own detour): OSC B's knobs edit its Part bytes"),
    ),
    pokes=(
        Poke(0x40079248, stock_guard(0x40079248, 4, "8fbd3190028fe564c11b56e3e73e8eaf36925cbabf94164176eeb4c4f57bc6ac"), H("48780006"),
             "machine chooser has six rows, CUBE the last"),
        Poke(0x400585FA, stock_guard(0x400585fa, 4, "8fbd3190028fe564c11b56e3e73e8eaf36925cbabf94164176eeb4c4f57bc6ac"), H("48780006"),
             "SRC SETUP selector has six rows"),
        Poke(0x4003C950, stock_guard(0x4003c950, 2, "74d01dadcbe6a57ef61bc53a5a65404cd8446c6738ff0ac86b1b1a78d8ae7d41"), H("7205"),
             "SRC SETUP name lookup admits CUBE"),
        Poke(0x40078678, stock_guard(0x40078678, 2, "04cd1c6d463ba6752ff68f9125991b1c4af983ae355b62366122ba2d47eee3b2"), H("7005"),
             "machine chooser draws CUBE"),
        Poke(0x400786CE, stock_guard(0x400786ce, 2, "04cd1c6d463ba6752ff68f9125991b1c4af983ae355b62366122ba2d47eee3b2"), H("7005"),
             "machine chooser highlights CUBE"),
        Poke(0x40079904, stock_guard(0x40079904, 2, "577d7ba37f9786ab02a7dc9eeb612bb55936018179b550b14f4b9f000a89bf20"), H("7605"),
             "machine chooser persists CUBE"),
    ),
    dsp=DspSection(asm="modules/cube/cube_seam.asm", priority=5, payloads=frozenset({"A", "B"}),
                   hooks=(DspHook({"A": 0x39C, "B": 0x1A2}, SEAM, "cs01",
                                  "track source seam: a CUBE record runs the loaded engine (or silence)"),),
                   subst={"A": {"CONTADDR": "$426", "NULLPROC": "$7c9"},
                          "B": {"CONTADDR": "$221", "NULLPROC": "$589"}}),
    gates=(Gate("modules/cube/verify.py", remix_arg=False),),
)
