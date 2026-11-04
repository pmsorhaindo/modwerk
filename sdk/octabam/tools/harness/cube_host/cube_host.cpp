// cube_host -- run CUBE's DSP engine (modules/cube/cube_engine.asm) alone,
// block by block, from the records the ColdFire would send.
//
// The engine is a source package, not an FX-slot effect: this host loads the
// relocated words, puts each block's 34-word record at X:REC, the track's
// voice index at X:$418 and the trig's frame offset at X:$20c, calls the
// proc entry with r4 = REC (the seam stub's convention) and single-steps
// back to a sentinel, then reads the 16 L,R frames at X:0. It meters the
// executed instructions per block (instructions, not cycles: CHIP.md 2).
//
//   cube_host -code eng.bin -org HEX -entry HEX -script blocks.txt -out out.raw
//             [-meter m.txt] [-voice 0..3] [-dirty SEED]
//
// blocks.txt: one line per block, "<trig offset or -1> <w0> .. <w33>" (hex
//             words). -dirty fills CUBE's private X ($2840..$393f) and X:0..31
//             with a seeded pattern first: the engine's epoch init must clear
//             what it reads (AGENTS.md, dirty state).
// out.raw:    the L,R words of every block, int32 little-endian, sign-extended.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "dsp56kEmu/dsp.h"
#include "dsp56kEmu/memory.h"
#include "dsp56kEmu/peripherals.h"

using namespace dsp56k;

namespace {
class AllowAll : public IMemoryValidator {
public:
    bool memValidateAccess(EMemArea, TWord, bool) const override { return true; }
};
TWord SENTINEL = 0x03f000; const TWord REC = 0x003a00;

// Cycles: the emulator's per-opcode table (calcCycles, no memory
// contention: a floor) summed per stepped instruction. The library is built
// with the JIT, where the interpreter does not count cycles itself, so the
// core runs host-stepped (one instruction per call, the loop-end test here:
// dsp.h setHostStepped, as ot_emu runs it) and each PC is priced before it runs.
long g_cycles = 0;
std::vector<uint64_t> g_profile(0x10000, 0);   // cycles per PC over the whole run (CUBE_PROFILE=file)
long call(DSP& dsp, TWord pc) {
    dsp.setPC(SENTINEL);
    dsp.jsr(pc);
    dsp.setHostStepped(true);
    const uint64_t i0 = dsp.getInstructionCounter();
    long cycles = 0;
    for (long i = 0; i < 20000000; ++i) {
        const TWord at = dsp.getPC().toWord();
        if (at == SENTINEL) { g_cycles = cycles; return long(dsp.getInstructionCounter() - i0); }
        const unsigned cc = dsp.calcOpcodeCycles(at);
        cycles += cc;
        if (at < g_profile.size()) g_profile[at] += cc;   // getOpcodeCycles caches per PC, and a JIT build never sizes the cache
        dsp.execInterpreter();
        dsp.doLoopEnd();
    }
    std::cerr << "no return from " << std::hex << pc << " (pc=" << dsp.getPC().toWord() << ")\n";
    std::exit(3);
}
}

int main(int argc, char** argv) {
    std::string code, script, out, meterPath, seam;
    TWord seamOrg = 0;
    TWord org = 0, entry = 0; int voice = 0; long dirty = -1;
    for (int i = 1; i + 1 < argc; i += 2) {
        std::string k = argv[i], v = argv[i + 1];
        if (k == "-code") code = v;
        else if (k == "-org") org = std::strtoul(v.c_str(), nullptr, 16);
        else if (k == "-entry") entry = std::strtoul(v.c_str(), nullptr, 16);
        else if (k == "-script") script = v;
        else if (k == "-out") out = v;
        else if (k == "-meter") meterPath = v;
        else if (k == "-voice") voice = std::atoi(v.c_str());
        else if (k == "-dirty") dirty = std::atol(v.c_str());
        else if (k == "-seam") seam = v;                                   // the seam stub, CONTADDR = the sentinel
        else if (k == "-seamorg") seamOrg = std::strtoul(v.c_str(), nullptr, 16);
        else if (k == "-sentinel") SENTINEL = std::strtoul(v.c_str(), nullptr, 16);   // a short-jump target for the seam
        else { std::cerr << "unknown option " << k << "\n"; return 2; }
    }
    if (!code.empty() && std::getenv("CUBE_CYCLES")) {   // print the table's price of every word: CUBE_CYCLES=from-to
        AllowAll v0; Memory m0(v0, 0x080000, 0x800000, 0x200000); Peripherals56362 a0; Peripherals56367 b0; DSP d0(m0, &a0, &b0);
        std::ifstream f0(code, std::ios::binary);
        std::vector<unsigned char> b((std::istreambuf_iterator<char>(f0)), {});
        for (size_t w = 0; w < b.size() / 3; ++w) m0.set(MemArea_P, org + TWord(w), b[3*w] | (b[3*w+1] << 8) | (b[3*w+2] << 16));
        unsigned lo = 0, hi = 0; std::sscanf(std::getenv("CUBE_CYCLES"), "%x-%x", &lo, &hi);
        for (TWord a = lo; a < hi; ++a) std::printf("%05x %06x %u\n", a, m0.get(MemArea_P, a), d0.calcOpcodeCycles(a));
        return 0;
    }
    if (code.empty() || script.empty() || out.empty()) {
        std::cerr << "usage: cube_host -code eng.bin -org HEX -entry HEX -script blocks.txt -out out.raw\n";
        return 2;
    }
    AllowAll validator;
    Memory mem(validator, 0x080000, 0x800000, 0x200000);
    Peripherals56362 px; Peripherals56367 py;
    DSP dsp(mem, &px, &py);

    std::ifstream cf(code, std::ios::binary);
    std::vector<unsigned char> blob((std::istreambuf_iterator<char>(cf)), {});
    if (blob.empty() || blob.size() % 3) { std::cerr << "bad code blob " << code << "\n"; return 2; }
    for (size_t w = 0; w < blob.size() / 3; ++w)
        mem.set(MemArea_P, org + TWord(w), blob[3*w] | (blob[3*w+1] << 8) | (blob[3*w+2] << 16));
    mem.set(MemArea_P, SENTINEL, 0x000000);
    if (!seam.empty()) {
        // enter through the resident stub: X:$209 = the record, X:$254 = id $1f's proc
        std::ifstream sf2(seam, std::ios::binary);
        std::vector<unsigned char> sb((std::istreambuf_iterator<char>(sf2)), {});
        for (size_t w = 0; w < sb.size() / 3; ++w)
            mem.set(MemArea_P, seamOrg + TWord(w), sb[3*w] | (sb[3*w+1] << 8) | (sb[3*w+2] << 16));
        mem.set(MemArea_X, 0x209, REC);
        mem.set(MemArea_X, 0x254, entry);
        mem.set(MemArea_X, 0x20b, 0x1e00);
    }
    if (dirty >= 0) {
        uint32_t s = uint32_t(dirty) * 2654435761u + 12345u;
        auto next = [&] { s = s * 1103515245u + 12345u; return TWord((s >> 7) & 0xffffff); };
        for (TWord a = 0x2840; a < 0x3940; ++a) mem.set(MemArea_X, a, next());
        for (TWord a = 0; a < 0x20; ++a) mem.set(MemArea_X, a, next());
    }
    mem.set(MemArea_X, 0x418, TWord(voice * 0x20));

    std::ifstream sf(script); std::ofstream of(out, std::ios::binary);
    std::ofstream mf; if (!meterPath.empty()) mf.open(meterPath);
    std::string line; long block = 0, maxN = 0, sum = 0;
    while (std::getline(sf, line)) {
        std::istringstream ls(line); long trig; if (!(ls >> trig)) continue;
        for (int k = 0; k < 34; ++k) {
            std::string w; if (!(ls >> w)) { std::cerr << "bad script line " << block << "\n"; return 2; }
            // the transport's 16-bit halves: junk above bit 15 must be ignored
            TWord v = TWord(std::strtoul(w.c_str(), nullptr, 16)) & 0xffff;
            if (dirty >= 0) v |= TWord((block * 0x5a + k * 0x13) & 0xff) << 16;
            mem.set(MemArea_X, REC + k, v);
        }
        mem.set(MemArea_X, 0x20c, trig < 0 ? 0xffffff : TWord(trig));
        dsp.regs().r[4].var = REC; dsp.regs().r[0].var = 0;
        for (int k = 0; k < 8; ++k) dsp.regs().m[k].var = 0xffffff;
        long n = call(dsp, seam.empty() ? entry : seamOrg);
        for (int s = 0; s < 32; ++s) {
            int32_t w = int32_t(mem.get(MemArea_X, s) << 8) >> 8;
            of.write(reinterpret_cast<char*>(&w), 4);
        }
        bool linear = true;
        for (int k = 0; k < 8; ++k) linear = linear && dsp.regs().m[k].var == 0xffffff;
        if (!linear) { std::cerr << "block " << block << ": an m register is not linear on return\n"; return 4; }
        if (mf) mf << n << ' ' << g_cycles << "\n";
        maxN = std::max(maxN, n); sum += n; ++block;
    }
    if (const char* pf = std::getenv("CUBE_PROFILE")) {
        std::ofstream pr(pf);
        for (size_t a = 0; a < g_profile.size(); ++a) if (g_profile[a]) pr << std::hex << a << ' ' << std::dec << g_profile[a] << "\n";
    }
    std::printf("blocks %ld  max %ld instr/block (%.1f/sample)  mean %.1f/sample\n",
                block, maxN, double(maxN) / 16, double(sum) / std::max(1L, block) / 16);
    return 0;
}
