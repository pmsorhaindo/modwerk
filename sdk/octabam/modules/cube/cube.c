/* CUBE: a wavetable source machine (8 x 8 x 8 cube, two oscillators) -- the
 * ColdFire half. The voice runs on the DSP (cube_engine.asm behind the seam
 * stub cube_seam.asm, one P record at core 1's free top: tracks 1-4,
 * static-stock, no loader, every stock effect kept);
 * this file renders each CUBE track's per-frame control record, builds the
 * morphed cycles from the cube in DRAM and streams them, 16 samples a frame,
 * and draws the SRC, OSC B and SETUP pages. cube_model.py is the reference: every integer step here is its.
 *
 * Machine registration follows Analog BD's measured seams (machine.s): a
 * CUBE track is FLEX (type 1) with "CU\x01" in the unused NEIGHBOR playback
 * bytes. Its pages, top row then bottom row, and where each byte lives:
 *   SRC    PTCH FM MIX / X Y Z          FLEX's playback slots 0..5 (p-lockable)
 *   OSC B  BPCH LAW LINK / BX BY BZ     BX BY BZ: NEIGHBOR playback bytes 3..5;
 *                                       LINK LAW BPCH: NEIGHBOR SETUP bytes 0..2
 *   SETUP  FINE OCT UNI / TONE MORPH SYNC  FLEX's SETUP slots
 *   UNI's target (A, B or both)         NEIGHBOR SETUP byte 3
 * A press of SRC on SRC shows OSC B and back; a double press (or FUNC+SRC)
 * opens SETUP; pushing the UNI encoder in SETUP cycles UNI's target.
 * NEIGHBOR has no parameters (its descriptor is 12 empty count-128 slots),
 * so every value here is inside what stock's validator accepts there.
 * The model's byte order (p[], cube_model.py) is PTCH X Y Z FM MIX, FINE OCT
 * UNI TONE MORPH SYNC, BX BY BZ LINK LAW BPCH, UTGT; the pages map onto it. */
#include <stdint.h>
#include "cube_tables.inc"

#define U8(a) (*(volatile uint8_t *)(uintptr_t)(a))
#define U16(a) (*(volatile uint16_t *)(uintptr_t)(a))
#define U32(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define BANK 0x46c82456u
#define PART_IDX 0x100b14cfu
#define PART_OFF 0x8ed80u
#define PART_STRIDE 0x18b2u
#define SRAM_PART 0x100a4eceu
#define PB 0x2au
#define SU 0x1dau
#define NB 18u                      /* NEIGHBOR's slice in a track's 30 bytes */
#define FX 6u                       /* FLEX's */
#define DESC_SIZE 0x1cau
#define FLEX_DESC 0x400d3176u       /* the stock FLEX page object (page at +0x38) */
#define FLEX_DEFAULTS 0x400d320cu   /* its twelve defaults */
#define UI_TRACK 0x100b14ccu        /* byte: the selected audio track */
#define UI_MIDI 0x80000012u         /* long: MIDI mode */
#define UI_PAGE 0x460d1684u         /* long: page kind; 0 = SRC (PLAYBACK) */
#define UI_WINDOW 0x400bcd14u       /* window pointer; +8 nonzero while open */
#define UI_LAST_KEY 0x400c0aacu     /* the key a press within 15 ticks double-taps */
#define UI_TAP_COUNT 0x460d5de0u
#define UI_PUSH 0x46c7d8eeu         /* key records: + (0x38 + slot) * 24 nonzero = encoder pushed */
#define SRC_SETUP_WINDOW 0x400bb7c8u
#define KEY_SRC 0x22
#define UNI_PUSH (UI_PUSH + (0x38u + 2u) * 24u)   /* knob C: UNI in SETUP */
#define REDRAW 0x4004d948u
#define SETPAGE 0x400554e0u        /* the page setter: the only writer of the page kind */
#define WIDGET_DIAL 0x400479b4u
#define WIDGET_ENUM 0x40046c28u     /* FLEX LOOP's */
#define WIDGET_TEXT 0x400467a4u     /* THRU INAB's */
#define SEQ_RUNNING 0x800065b8u     /* nonzero while the sequencer plays (publication.c) */
#define FLEX_RENDER 0x40004008u
#define SIG0 0xcb01u
#define SIG1 0x1e1eu

typedef void (*Widget)(int, int, int, int, int, void *, void *);

/* ---- the cube (cube_data.s) ----------------------------------------------- */
extern const int16_t cube_waves[];

/* ---- state: explicitly initialised (a DRAM unit's .bss is never cleared) -- */
struct stream { uint32_t last[2]; uint32_t pos; uint8_t busy, which, chunk, pad; };
struct cube_track { uint16_t epoch; uint8_t was, gen; struct stream s; };
static struct cube_track tracks[8] = {{0, 0, 0, {{0, 0}, 0, 0, 0, 0, 0}}};
static uint8_t before = 0;           /* the view a single SRC press left (a double press goes back) */
static uint8_t push_was = 0, push_armed = 0, push_uni = 0;
/* tracks just made CUBE: stock's commit leaves FLEX's SETUP defaults in the
 * live track copy, which CUBE reads (params); the next UI tick copies the
 * Part's SETUP bytes over them, so a note before the next PLAY is CUBE's */
static uint8_t fresh = 0;
uint8_t cube_view = 0;   /* the ring: 0 SRC, 1 SETUP, 2 OSC B (OSC B shows while 2) */
uint8_t cube_desc[2][DESC_SIZE] = {{0}};   /* machine.s compares the knob routine's descriptor with OSC B's */
static uint32_t built = 0;
static int32_t acc[6] = {0, 0, 0, 0, 0, 0};
uint32_t cube_render_calls = 0, cube_hits = 0, cube_chunks = 0, cube_commits = 0;
uint32_t cube_ring_steps = 0, cube_knob_b = 0;
uint32_t cube_last_record[17] = {0};

/* page slot -> model byte: SRC PTCH FM MIX / X Y Z, OSC B BPCH LAW LINK / BX BY BZ */
static const uint8_t SRC_SEM[6] = {0, 4, 5, 1, 2, 3};
static const uint8_t SRC_SLOT[6] = {0, 3, 4, 5, 1, 2};      /* model byte -> page slot */
static const uint8_t OSCB_SEM[6] = {5, 4, 3, 0, 1, 2};       /* page slot -> OSC B byte (BX BY BZ LINK LAW BPCH) */
static const uint8_t OSCB_COUNT[6] = {128, 128, 128, 4, 3, 128};

static volatile uint8_t *part_base(void) {
    return (volatile uint8_t *)(uintptr_t)(U32(BANK) + PART_OFF + (U8(PART_IDX) & 3) * PART_STRIDE);
}
/* CUBE's voice lives in DSP core 1's free program memory, and core 1 runs
 * tracks 1-4 (payload B; payload A, tracks 5-8, has no CUBE code). */
#define CUBE_TRACKS 4u
void cube_sig_write(volatile uint8_t *part, unsigned t, unsigned on);
static unsigned raw_signed(const volatile uint8_t *part, unsigned t) {
    const volatile uint8_t *s = part + PB + 30 * t + NB;
    return t < 8 && part[0x22 + t] == 1 && s[0] == 'C' && s[1] == 'U' && s[2] == 1;
}
static unsigned signed_track(const volatile uint8_t *part, unsigned t) {
    return t < CUBE_TRACKS && raw_signed(part, t);
}

/* ---- control math (cube_model.controls) ---------------------------------- */
static uint32_t inc_of(int32_t cents) {
    int32_t o = cents >= 0 ? cents / 1200 : -((-cents + 1199) / 1200);
    int32_t r = cents - 1200 * o, sh = o - 8;
    uint32_t v;
    if (sh >= 0) return CUBE_MAXINC;
    v = -sh >= 32 ? 0 : CUBE_CENT[r] >> (unsigned)-sh;
    return v < CUBE_MAXINC ? v : CUBE_MAXINC;
}
static unsigned clampn(unsigned v, unsigned n) { return v < n ? v : 0; }

struct ctl { uint32_t inc_a, inc_b, d, g_a, g_b, mask; uint8_t sync, own; uint32_t pos_a, pos_b; };

static uint32_t key(unsigned x, unsigned y, unsigned z, unsigned m) {
    return 0x80000000u | (x & 127) << 21 | (y & 127) << 14 | (z & 127) << 7 | (m & 7);
}
/* p[19]: PTCH X Y Z FM MIX, FINE OCT UNI TONE MORPH SYNC, BX BY BZ LINK LAW BPCH, UTGT */
static void controls(const uint8_t *p, struct ctl *c) {
    unsigned oct = clampn(p[7], 5), tone = clampn(p[9], 3), morph = clampn(p[10], 8);
    unsigned sync = clampn(p[11], 3), link = clampn(p[15], 4), law = clampn(p[16], 3);
    int32_t cents_a = ((int32_t)p[0] - 64) * 100 + ((int32_t)p[6] - 64) + ((int32_t)oct - 2) * 1200;
    unsigned u = p[8], tgt = clampn(p[18], 3);
    int32_t uoct = (u >= 97 && u <= 111) ? -1200 : u >= 112 ? 1200 : 0;
    int32_t udet = (u >= 1 && u <= 96) ? CUBE_UNIC[u] : 0;
    /* UNI's target: 0 B, 1 BOTH (A down by the offset, B up: an octave stays in key), 2 A.
     * B follows A's note from before UNI moves it. */
    int32_t off = uoct + udet;
    int32_t note = link <= 1 ? cents_a : 0;
    unsigned mute_a, mute_b, fm = p[4] & 127;
    c->inc_a = inc_of(cents_a + (tgt == 2 ? off : tgt == 1 ? -off : 0));
    c->inc_b = inc_of(note + ((int32_t)p[17] - 64) * 100 + (tgt <= 1 ? off : 0));
    mute_a = c->inc_a < CUBE_MININC; mute_b = c->inc_b < CUBE_MININC;
    if (law == 0) c->d = CUBE_FMLIN[fm];
    else if (law == 1) { uint32_t e = (c->inc_a * 2u * fm) / 127u; c->d = e < 0x7fffffu ? e : 0x7fffffu; }
    else c->d = 0;
    if (mute_b) c->d = 0;
    c->g_b = CUBE_MIXG[p[5] & 127];
    c->g_a = 0x7fffffu - c->g_b;
    if (mute_a) c->g_a = 0;
    if (mute_b) c->g_b = 0;
    c->mask = tone == 0 ? 0xffffffu : tone == 1 ? 0xfff000u : 0xff0000u;
    c->sync = (uint8_t)sync;
    c->own = link == 1 || link == 3;
    c->pos_a = key(p[1], p[2], p[3], morph);
    c->pos_b = c->own ? key(p[12], p[13], p[14], morph) : 0;
}

/* ---- the morph (cube_model.morph_samples) -------------------------------- */
static void axis(unsigned v, unsigned on, unsigned *i0, unsigned *i1, int32_t *t8) {
    if (!on) { *i0 = *i1 = (v * 7 + 63) / 127; *t8 = 0; return; }
    unsigned a = v * 7;
    *i0 = a / 127; *i1 = *i0 < 7 ? *i0 + 1 : 7; *t8 = (int32_t)((a % 127) * 256 / 127);
}
static int32_t lerp(int32_t a, int32_t b, int32_t t8) { return a + (((b - a) * t8) >> 8); }
static int32_t wave(unsigned z, unsigned f, unsigned s) { return cube_waves[(z * 64 + f) * 256 + s]; }

static void morph(uint32_t pos, unsigned start, uint16_t *out) {
    unsigned x = (pos >> 21) & 127, y = (pos >> 14) & 127, z = (pos >> 7) & 127, m = pos & 7;
    unsigned xi0, xi1, yi0, yi1, zi0, zi1;
    int32_t xt, yt, zt;
    axis(x, m & 1, &xi0, &xi1, &xt);
    axis(y, m & 2, &yi0, &yi1, &yt);
    axis(z, m & 4, &zi0, &zi1, &zt);
    for (unsigned s = start; s < start + 16; ++s) {
        int32_t v[2];
        for (unsigned k = 0; k < (zt ? 2u : 1u); ++k) {
            unsigned zi = k ? zi1 : zi0;
            int32_t r0 = xt ? lerp(wave(zi, yi0 * 8 + xi0, s), wave(zi, yi0 * 8 + xi1, s), xt) : wave(zi, yi0 * 8 + xi0, s);
            if (yt) {
                int32_t r1 = xt ? lerp(wave(zi, yi1 * 8 + xi0, s), wave(zi, yi1 * 8 + xi1, s), xt) : wave(zi, yi1 * 8 + xi0, s);
                r0 = lerp(r0, r1, yt);
            }
            v[k] = r0;
        }
        *out++ = (uint16_t)(zt ? lerp(v[0], v[1], zt) : v[0]);
    }
}

/* ---- the stream (cube_model.Stream): one chunk a frame, A before B -------- */
static unsigned chunk(struct stream *s, const struct ctl *c, uint32_t *pos, unsigned *k, unsigned *commit) {
    if (!s->busy) {
        if (c->pos_a != s->last[0]) { s->busy = 1; s->which = 0; s->pos = c->pos_a; s->chunk = 0; }
        else if (c->own && c->pos_b != s->last[1]) { s->busy = 1; s->which = 1; s->pos = c->pos_b; s->chunk = 0; }
    }
    if (!s->busy) return 0;
    unsigned which = s->which;
    *pos = s->pos; *k = s->chunk; *commit = s->chunk == 15;
    if (*commit) { s->last[which] = s->pos; s->busy = 0; }
    else ++s->chunk;
    return which + 1;
}

static void put24(volatile uint32_t *r, uint32_t v) { *r = ((v >> 8) & 0xffffu) << 16 | (v & 0xffu); }

/* The track's 18 bytes: SRC from the live playback values (locks, chromatic
 * keys), SETUP from the live track copy, OSC B from the active Part. */
static void params(unsigned track, uint8_t *p) {
    const volatile uint16_t *fp = (const volatile uint16_t *)(uintptr_t)U32(0x800062a8u);
    const volatile uint8_t *part = part_base();
    for (unsigned k = 0; k < 6; ++k) p[k] = (uint8_t)(fp[SRC_SLOT[k]] >> 8);
    for (unsigned k = 0; k < 6; ++k) p[6 + k] = U8(0x80000810u + 72 * track + 0x20 + k);
    for (unsigned k = 0; k < 3; ++k) p[12 + k] = part[PB + 30 * track + NB + 3 + k];
    for (unsigned k = 0; k < 3; ++k) p[15 + k] = part[SU + 30 * track + NB + k];
    p[18] = part[SU + 30 * track + NB + 3];
}

/* ABI measured at 4000d430/4000d518 (Analog BD): every track is rendered
 * twice per frame around its event's sample offset, the second call with
 * end = 16; the transport sends each long as two 16-bit DSP words. */
int cube_render(unsigned track, unsigned ping, unsigned start, unsigned end) {
    if (track >= 8 || !signed_track(part_base(), track)) {
        if (track < 8) tracks[track].was = 0;
        return ((int (*)(unsigned, unsigned, unsigned, unsigned))FLEX_RENDER)(track, ping, start, end);
    }
    ++cube_render_calls;
    volatile uint32_t *cursor = (volatile uint32_t *)(uintptr_t)U32(0x80001c80u);
    unsigned n = end > start && end <= 16 ? end - start : 0;
    for (unsigned i = 0; i < 4 + 2 * n; ++i) cursor[i] = 0;
    if (end == 16) {
        struct cube_track *t = &tracks[track];
        if (!t->was) { t->was = 1; ++t->gen; }
        /* a new epoch each time the track becomes CUBE: the engine clears
         * this voice's buffers and phases on the first block it sees it */
        uint16_t epoch = (uint16_t)(1u + ((unsigned)t->gen << 8));
        if (epoch != t->epoch) {
            t->epoch = epoch;
            t->s.last[0] = t->s.last[1] = 0; t->s.busy = 0;
        }
        /* The source gain stock AMP multiplies in (DSP record word $1d, B
         * P:$3b6). A FLEX trig sets it from the sample slot's gain
         * (0x4000c6e0: the table at 0x80001850 + 2 * track); CUBE has no
         * sample, so it would be 0 and the track silent. 0x800 is what stock
         * gives every non-sample source (THRU, 0x4000c6ea). The frame builder
         * has already copied the table into this frame's records (0x40004c3c,
         * 0x80000110 + 0x200 * ping + 0x40 * track + 0x3a), so both are set. */
        U16(0x80001850u + 2u * track) = 0x800;
        U16(0x80000110u + 0x40u * track + 0x3au) = 0x800;
        U16(0x80000310u + 0x40u * track + 0x3au) = 0x800;
        uint8_t p[19];
        struct ctl ctl;
        params(track, p);
        controls(p, &ctl);
        volatile uint32_t *r = (volatile uint32_t *)(uintptr_t)(0x80001c90u + (ping & 1) * 0xa80u + 336u * track);
        unsigned trig = (U8(0x46104d0cu + track) & 16) != 0;
        uint32_t pos = 0; unsigned k = 0, commit = 0, target = 0;
        target = chunk(&t->s, &ctl, &pos, &k, &commit);
        r[0] = SIG0 << 16 | trig | (ctl.own ? 2u : 0u) | (unsigned)ctl.sync << 2;
        r[1] = SIG1 << 16 | t->epoch;
        put24(r + 2, ctl.inc_a); put24(r + 3, ctl.inc_b); put24(r + 4, ctl.d);
        put24(r + 5, ctl.g_a); put24(r + 6, ctl.g_b); put24(r + 7, ctl.mask);
        r[8] = (uint32_t)(target | (commit ? 4u : 0u) | k << 4) << 16;
        if (target) {
            uint16_t s[16];
            morph(pos, k * 16, s);
            for (unsigned i = 0; i < 8; ++i) r[9 + i] = (uint32_t)s[2 * i] << 16 | s[2 * i + 1];
            ++cube_chunks; if (commit) ++cube_commits;
        } else for (unsigned i = 0; i < 8; ++i) r[9 + i] = 0;
        for (unsigned i = 0; i < 17; ++i) cube_last_record[i] = r[i];
        if (trig) ++cube_hits;
    }
    U32(0x80001c80u) = (uint32_t)(uintptr_t)(cursor + 4 + 2 * n);
    return 0;
}

/* ---- pages ------------------------------------------------------------------ */
static void put32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}
static void text(uint8_t *p, const char *s, unsigned n) {
    unsigned i = 0; for (; i + 1 < n && s[i]; ++i) p[i] = (uint8_t)s[i];
    for (; i < n; ++i) p[i] = 0;
}
static int copy(char *out, const char *s) { int n = 0; while ((out[n] = s[n])) ++n; return n; }
static int number(char *out, int v) {
    char d[6]; int n = 0, i = 0;
    if (v < 0) { out[i++] = '-'; v = -v; }
    do { d[n++] = (char)('0' + v % 10); v /= 10; } while (v && n < 5);
    while (n) out[i++] = d[--n];
    out[i] = 0; return i;
}
static int signed_num(char *out, int v) { if (v > 0) { out[0] = '+'; return 1 + number(out + 1, v); } return number(out, v); }

int cube_fmt_cents(char *out, int v) { return signed_num(out, v - 64); }
int cube_fmt_semi(char *out, int v) { return signed_num(out, v - 64); }
int cube_fmt_oct(char *out, int v) { return signed_num(out, (v > 4 ? 2 : v) - 2); }
int cube_fmt_uni(char *out, int v) {
    if (v == 0) return copy(out, "OFF");
    if (v <= 96) return number(out, v);
    return copy(out, v <= 111 ? "-OCT" : "+OCT");
}
static const char *const tone_names[3] = {"16B", "12B", "8B"};
static const char *const morph_names[8] = {"OFF", "X", "Y", "XY", "Z", "XZ", "YZ", "XYZ"};
static const char *const sync_names[3] = {"FREE", "TRIG", "HARD"};
static const char *const link_names[4] = {"BOTH", "POS", "PTCH", "OFF"};
static const char *const law_names[3] = {"LIN", "EXP", "OFF"};
int cube_fmt_tone(char *out, int v) { return copy(out, tone_names[(unsigned)v < 3 ? v : 0]); }
int cube_fmt_morph(char *out, int v) { return copy(out, morph_names[(unsigned)v < 8 ? v : 0]); }
int cube_fmt_sync(char *out, int v) { return copy(out, sync_names[(unsigned)v < 3 ? v : 0]); }
int cube_fmt_link(char *out, int v) { return copy(out, link_names[(unsigned)v < 4 ? v : 0]); }
int cube_fmt_law(char *out, int v) { return copy(out, law_names[(unsigned)v < 3 ? v : 0]); }

/* OSC B's byte under page slot `slot` (BPCH LAW LINK / BX BY BZ) of the selected track, in the working Part. */
static volatile uint8_t *oscb_byte(unsigned track, unsigned slot) {
    volatile uint8_t *part = part_base();
    unsigned s = OSCB_SEM[slot < 6 ? slot : 0];
    return s < 3 ? part + PB + 30 * track + NB + 3 + s : part + SU + 30 * track + NB + s - 3;
}
static unsigned ui_track(void) { unsigned t = U8(UI_TRACK); return t < 8 ? t : 0; }

void cube_wid_b(int x, int y, int slot, int value, int flags, void *format, void *window) {
    (void)value;
    unsigned s = (unsigned)slot < 6 ? (unsigned)slot : 0;
    int v = *oscb_byte(ui_track(), s);
    ((Widget)(OSCB_SEM[s] == 3 || OSCB_SEM[s] == 4 ? WIDGET_ENUM : WIDGET_DIAL))(x, y, slot, v, flags, format, window);
}

/* model order: PTCH X Y Z FM MIX, FINE OCT UNI TONE MORPH SYNC, BX BY BZ LINK LAW BPCH */
static const uint8_t cube_defaults[18] = {64, 0, 0, 0, 0, 64, 64, 2, 0, 0, 7, 1, 0, 0, 0, 0, 0, 64};
static const char *const uni_labels[3] = {"UNI B", "UNIAB", "UNI A"};

static void build(void) {
    const volatile uint8_t *src = (const volatile uint8_t *)FLEX_DESC;
    static const char *const names[2][12] = {
        {"PTCH", "FM", "MIX", "X", "Y", "Z", "FINE", "OCT", "UNI B", "TONE", "MORPH", "SYNC"},
        {"BPCH", "LAW", "LINK", "BX", "BY", "BZ", "FINE", "OCT", "UNI B", "TONE", "MORPH", "SYNC"}};
    static const uint32_t counts[2][12] = {{121, 128, 128, 128, 128, 128, 128, 5, 128, 3, 8, 3},
                                           {128, 3, 4, 128, 128, 128, 128, 5, 128, 3, 8, 3}};
    static const uint32_t fmts[2][12] = {
        {0, 0, 0, 0, 0, 0, (uint32_t)cube_fmt_cents, (uint32_t)cube_fmt_oct, (uint32_t)cube_fmt_uni,
         (uint32_t)cube_fmt_tone, (uint32_t)cube_fmt_morph, (uint32_t)cube_fmt_sync},
        {(uint32_t)cube_fmt_semi, (uint32_t)cube_fmt_law, (uint32_t)cube_fmt_link, 0, 0, 0,
         (uint32_t)cube_fmt_cents, (uint32_t)cube_fmt_oct, (uint32_t)cube_fmt_uni,
         (uint32_t)cube_fmt_tone, (uint32_t)cube_fmt_morph, (uint32_t)cube_fmt_sync}};
    for (unsigned m = 0; m < 2; ++m) {
        uint8_t *d = cube_desc[m];
        for (unsigned i = 0; i < DESC_SIZE; ++i) d[i] = src[i];
        text(d + 0x3c, m ? "OSCB" : "CUBE", 5);
        text(d + 0x41, m ? "CUBE OSC B" : "CUBE", 13);
        for (unsigned i = 0; i < 12; ++i) {
            /* LOOP's bar draws up to five values; MORPH's eight take THRU INAB's text */
            uint32_t wid = i == 10 ? WIDGET_TEXT : i == 7 || i >= 9 ? WIDGET_ENUM : 0;
            if (m && i < 6) wid = (uint32_t)cube_wid_b;
            text(d + 0x4e + 6 * i, names[m][i], 6);
            if (i == 0 && !m) continue;             /* PTCH: FLEX's slot, whole */
            d[0x96 + i] = i >= 6 ? cube_defaults[i] : m ? cube_defaults[12 + OSCB_SEM[i]] : cube_defaults[SRC_SEM[i]];
            put32(d + 0xa2 + 4 * i, 0);
            put32(d + 0xd2 + 4 * i, counts[m][i]);
            put32(d + 0x102 + 4 * i, fmts[m][i]);
            put32(d + 0x132 + 4 * i, wid);
            put32(d + 0x162 + 4 * i, 0);
        }
        /* enable nibbles, slot 0 lowest: 1 a live knob, 5 a live enum (FLEX's LOOP) */
        put32(d + 0x1c2, 0x5551u);
        put32(d + 0x1c6, m ? 0x51111551u : 0x51111111u);
    }
    built = 1;
}

static unsigned current_cube(void) {
    return !U32(UI_MIDI) && U32(BANK) >= 0x40000000u && U32(BANK) < 0x48000000u &&
           signed_track(part_base(), ui_track());
}
static unsigned window_open(void) { uint32_t w = U32(UI_WINDOW); return w && U32(w + 8); }

/* The descriptor for kind 5 on this track: OSC B while the ring shows it on
 * the selected CUBE track and the SRC page is up, else CUBE's. */
uint32_t cube_track_page(const volatile uint8_t *type_ptr) {
    if (!built) build();
    volatile uint8_t *part = part_base();
    uintptr_t track = (uintptr_t)type_ptr - (uintptr_t)(part + 0x22);
    unsigned b = cube_view == 2 && track == ui_track() && U32(UI_PAGE) == 0 && !window_open() && current_cube();
    return (uint32_t)(uintptr_t)(cube_desc[b] + 0x38);
}
/* One byte of the selected track's Part, in the working copy and its SRAM
 * shadow, marked edited as stock's SETUP editor marks a Part. */
static void set_part_byte(volatile uint8_t *b, uint8_t v) {
    *b = v;
    unsigned part = U8(PART_IDX) & 3;
    uintptr_t off = (uintptr_t)b - (uintptr_t)part_base();
    U8(SRAM_PART + PART_STRIDE * part + off) = v;
    uint32_t bank = U32(BANK);
    U8(bank + 0x95048u) |= (uint8_t)(1u << part);       /* the Part's dirty flags */
    U8(0x100b145eu) |= (uint8_t)(1u << part);
    U32(bank + 0x9b332u) = 1;
    U32(0x100f8598u) = 1;
}
uint32_t cube_uni_cycles = 0;
void cube_ui_tick(void) {
    if (!built) build();
    if (U32(BANK) >= 0x40000000u && U32(BANK) < 0x48000000u) {
        volatile uint8_t *part = part_base();
        for (unsigned t = CUBE_TRACKS; t < 8; ++t) if (raw_signed(part, t)) cube_sig_write(part, t, 0);
        for (unsigned t = 0; fresh && t < CUBE_TRACKS; ++t) if (fresh & (1u << t)) {
            fresh &= (uint8_t)~(1u << t);
            if (signed_track(part, t))
                for (unsigned k = 0; k < 6; ++k) U8(0x80000810u + 72 * t + 0x20 + k) = part[SU + 30 * t + FX + k];
        }
    }
    U32(0x400d5f38u + 5 * 4) = (uint32_t)(uintptr_t)(cube_desc[0] + 0x38);
    if (cube_view && (!current_cube() || U32(UI_PAGE) != 0)) cube_view = 0;
    unsigned cube = current_cube();
    volatile uint8_t *tgt = cube ? part_base() + SU + 30 * ui_track() + NB + 3 : 0;
    /* UNI's label names its target on the selected CUBE track */
    if (cube) {
        const char *l = uni_labels[*tgt < 3 ? *tgt : 0];
        text(cube_desc[0] + 0x4e + 6 * 8, l, 6);
        text(cube_desc[1] + 0x4e + 6 * 8, l, 6);
    }
    /* A push of the UNI encoder (knob C) in SETUP that does not turn it cycles
     * UNI's target A -> B -> BOTH -> A (stored 2 -> 0 -> 1 -> 2). A push that
     * turns the encoder (stock's fast turn) changes UNI's value instead. */
    unsigned setup = cube && window_open() && U32(UI_WINDOW) == SRC_SETUP_WINDOW;
    unsigned pushed = U32(UNI_PUSH) != 0;
    volatile uint8_t *uni = cube ? part_base() + SU + 30 * ui_track() + FX + 2 : 0;
    if (!setup) push_armed = 0;
    else if (pushed && !push_was) { push_armed = 1; push_uni = *uni; }
    else if (!pushed && push_was && push_armed) {
        push_armed = 0;
        if (*uni == push_uni) {
            set_part_byte(tgt, (uint8_t)((*tgt < 3 ? *tgt + 1u : 1u) % 3u));
            text(cube_desc[0] + 0x4e + 6 * 8, uni_labels[*tgt], 6);
            text(cube_desc[1] + 0x4e + 6 * 8, uni_labels[*tgt], 6);
            ++cube_uni_cycles;
            ((void (*)(int))REDRAW)(-1);
        }
    }
    push_was = (uint8_t)pushed;
}

/* The track strip's machine letter: a lowercase c for a CUBE track (machine.s
 * cube_letter), in stock's strip glyph format: 3 columns of a 32-bit word,
 * MSB the bottom row, 4 rows of ink under a 7-row mask. */
static const uint32_t cube_glyph_ink[3] = {0xe0000000u, 0xa0000000u, 0xa0000000u};
static const uint32_t cube_glyph_mask[3] = {0xfe000000u, 0xfe000000u, 0xfe000000u};
const uint32_t cube_glyph[5] = {3, 4, 1, (uint32_t)cube_glyph_ink, (uint32_t)cube_glyph_mask};
unsigned cube_strip_track(unsigned track) {
    return U32(BANK) >= 0x40000000u && U32(BANK) < 0x48000000u && signed_track(part_base(), track);
}

/* ---- the SRC page key on CUBE tracks ------------------------------------------
 * 0x40055720(code, arg), the page select a page key's event calls: arg 1 a
 * press, 3 the second press of a double tap, 0 the release of a press stock
 * held back over a window (measured: diag/cube1/probe_stock_74.log). On a
 * CUBE track's SRC page a press shows OSC B, and the next press SRC again; a
 * double press goes back to the page its first press left and lets stock
 * open SRC SETUP over it (as FUNC+SRC does). Arriving from another page and
 * pressing over SETUP stay stock's. Returns 0 stock, 1 consumed. */
int32_t cube_page_pre(int32_t code, int32_t arg) {
    if (code != KEY_SRC || !current_cube()) { cube_view = 0; return 0; }
    if (U32(UI_PAGE) != 0) { cube_view = 0; before = 0; return 0; }   /* arriving: stock shows SRC */
    if (window_open()) return 0;                                       /* stock closes SETUP */
    if (arg == 3) {
        cube_view = before;
        ++cube_ring_steps;
    } else if (arg == 1) {
        before = cube_view;
        cube_view = cube_view == 2 ? 0 : 2;
        ++cube_ring_steps;
    } else {
        return 0;
    }
    /* Stock's own page setter, as a stock SRC press calls it (0x40055778):
     * it resolves the page again (cube_track_page now answers for the new
     * view) and caches its per-knob steps. A redraw alone left OSC B's
     * enumerated steps on the SRC page's knobs whenever a track change had
     * set the page while OSC B showed. */
    ((void (*)(int))SETPAGE)(0);
    if (arg == 3) return 0;                                            /* stock opens SETUP */
    ((void (*)(int))REDRAW)(-1);
    return 1;
}
void cube_page_post(int32_t code) {
    U32(UI_LAST_KEY) = (uint32_t)code;
    U32(UI_TAP_COUNT) = 0;
}

/* ---- OSC B's knobs (the detour after the knob routine's resolve) ---------- */
void cube_knob(int32_t slot, int32_t ticks) {
    if (slot < 0 || slot > 5) return;
    unsigned count = OSCB_COUNT[OSCB_SEM[slot]];
    unsigned track = ui_track();
    if (U32(UI_PUSH + (0x38u + (uint32_t)slot) * 24u)) ticks *= 7;
    int32_t per = count < 128 ? 4 : 1, a = acc[slot];
    if ((a < 0 && ticks > 0) || (a > 0 && ticks < 0)) a = 0;
    a += ticks;
    int32_t steps = a / per;
    acc[slot] = a - steps * per;
    if (!steps) return;
    volatile uint8_t *b = oscb_byte(track, (unsigned)slot);
    int32_t v = (int32_t)*b + steps;
    if (v < 0) v = 0;
    if (v >= (int32_t)count) v = (int32_t)count - 1;
    set_part_byte(b, (uint8_t)v);
    ++cube_knob_b;
    ((void (*)(int))REDRAW)(-1);
}
uint32_t cube_oscb_desc(void) { if (!built) build(); return (uint32_t)(uintptr_t)(cube_desc[1] + 0x38); }

/* ---- Part bytes: assignment, leaving, validation -------------------------- */
/* on: CUBE's defaults into FLEX's twelve and OSC B's six, unless the
 * signature is already there (a reselect keeps the patch); off: FLEX's
 * defaults back and NEIGHBOR's bytes zero, so a FLEX track never holds a
 * CUBE byte outside FLEX's counts (AGENTS.md: a stored value outside its
 * count stalls the sequencer). Both copies: the bank and the SRAM shadow. */
static void sig_one(volatile uint8_t *part, unsigned t, unsigned on) {
    volatile uint8_t *s = part + PB + 30 * t + NB;
    const volatile uint8_t *flex = (const volatile uint8_t *)FLEX_DEFAULTS;
    unsigned have = s[0] == 'C' && s[1] == 'U' && s[2] == 1;
    if (on && !have) {
        for (unsigned k = 0; k < 6; ++k) {
            part[PB + 30 * t + FX + SRC_SLOT[k]] = cube_defaults[k];
            part[SU + 30 * t + FX + k] = cube_defaults[6 + k];
        }
        for (unsigned k = 0; k < 3; ++k) {
            s[3 + k] = cube_defaults[12 + k];
            part[SU + 30 * t + NB + k] = cube_defaults[15 + k];
        }
        part[SU + 30 * t + NB + 3] = 0;                 /* UNI on B */
        s[0] = 'C'; s[1] = 'U'; s[2] = 1;
    } else if (!on && have) {
        for (unsigned k = 0; k < 6; ++k) {
            part[PB + 30 * t + FX + k] = flex[k];
            part[SU + 30 * t + FX + k] = flex[6 + k];
            s[k] = 0;
            part[SU + 30 * t + NB + k] = 0;
        }
    }
}
void cube_sig_write(volatile uint8_t *part, unsigned t, unsigned on) {
    if (t >= 8) return;
    if (on && t < CUBE_TRACKS) fresh |= (uint8_t)(1u << t);
    sig_one(part, t, on);
    uintptr_t off = (uintptr_t)part - (U32(BANK) + PART_OFF);
    sig_one((volatile uint8_t *)(SRAM_PART + off), t, on);
}
unsigned cube_admit_track(const volatile uint8_t *part, unsigned track) {
    /* the measured price fits four tracks on either core (verify.py step 4),
     * so admission is the track's range; the arithmetic is in the report */
    (void)part;
    return track < CUBE_TRACKS;
}
/* Rows in the selected track's machine lists: CUBE is the sixth on T1-T4. */
unsigned cube_rows(void) { return U8(UI_TRACK) < CUBE_TRACKS ? 6u : 5u; }
unsigned cube_type(unsigned type, const volatile uint8_t *ptr) {
    volatile uint8_t *part = part_base();
    uintptr_t t = (uintptr_t)ptr - (uintptr_t)(part + 0x22);
    return type == 1 && t < 8 && signed_track(part, (unsigned)t) ? 5 : type;
}
/* Track double-tap: a synthesized source has no sample pool. */
unsigned cube_selected_source(void) {
    unsigned track = U8(UI_TRACK);
    return !U8(0x80000015u) && track < 8 && signed_track(part_base(), track);
}
/* Stock's validator sees FLEX's defaults in a CUBE track's FLEX bytes (FINE
 * etc. are outside FLEX's counts); every original byte is put back. */
extern int cube_stock_validate(void *part);
int cube_validate_part(uint8_t *part) {
    uint8_t saved[8][12]; unsigned mask = 0;
    const volatile uint8_t *flex = (const volatile uint8_t *)FLEX_DEFAULTS;
    /* a CUBE signature on T5-T8 (a pasted track, a CUBE1 Part) becomes FLEX */
    for (unsigned t = CUBE_TRACKS; t < 8; ++t) if (raw_signed(part, t)) sig_one(part, t, 0);
    for (unsigned t = 0; t < 8; ++t) if (signed_track(part, t)) {
        mask |= 1u << t;
        for (unsigned k = 0; k < 12; ++k) {
            unsigned at = (k < 6 ? PB : SU) + 30 * t + FX + k % 6;
            saved[t][k] = part[at]; part[at] = flex[k];
        }
    }
    int result = cube_stock_validate(part);
    for (unsigned t = 0; t < 8; ++t) if (mask & (1u << t))
        for (unsigned k = 0; k < 12; ++k) part[(k < 6 ? PB : SU) + 30 * t + FX + k % 6] = saved[t][k];
    return result;
}
