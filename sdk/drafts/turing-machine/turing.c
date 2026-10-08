/* Turing machine engine. No floating point, allocation, runtime library
 * calls or clock of its own: a register advances only when the stock
 * sequencer fires a trig on its MIDI track. Compile to the checked-in
 * ColdFire assembly with generate.py. */
#include "turing.h"

_Static_assert(sizeof(TmState) == 8, "hooks.s state allocation");
_Static_assert(sizeof(TmGlobals) == 8, "hooks.s globals allocation");
_Static_assert(sizeof(TmSettings) == 32, "battery-RAM settings record");
_Static_assert(sizeof(TmTestSeed) == 12, "battery-RAM test seed record");

#define SETTINGS ((volatile TmSettings *)TM_NV_SETTINGS)
#define TEST_SEED ((volatile TmTestSeed *)TM_NV_TEST_SEED)
#define WORD(address) (*(volatile uint32_t *)(address))

const char tm_label_edit[] = "TURING TRACK";
const char tm_label_mode[] = "TURING MODE";
const char tm_label_lock[] = "TURING LOCK";
const char tm_label_length[] = "TURING LENGTH";

static const char tm_track_names[TM_TRACKS][3] = {"T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"};
static const char tm_mode_names[2][4] = {"OFF", "ON"};
static char tm_number_text[4];

/* ---- settings --------------------------------------------------------- */

static uint8_t tm_checksum(const volatile TmSettings *s) {
    const volatile uint8_t *p = (const volatile uint8_t *)s;
    uint8_t sum = 0x5a;
    for (unsigned i = 0; i < sizeof(TmSettings) - 1u; ++i) sum ^= p[i];
    return sum;
}

static unsigned tm_valid(void) {
    const volatile TmSettings *s = SETTINGS;
    if (s->magic != TM_NV_MAGIC || s->version != TM_NV_VERSION || s->check != tm_checksum(s)) return 0;
    for (unsigned t = 0; t < TM_TRACKS; ++t)
        if (s->lock[t] > 127u || s->length[t] < TM_LENGTH_MIN || s->length[t] > TM_LENGTH_MAX) return 0;
    return 1;
}

static void tm_read(TmSettings *out) {
    if (tm_valid()) {
        const volatile uint8_t *src = (const volatile uint8_t *)SETTINGS;
        uint8_t *dst = (uint8_t *)out;
        for (unsigned i = 0; i < sizeof(TmSettings); ++i) dst[i] = src[i];
        return;
    }
    uint8_t *dst = (uint8_t *)out;
    for (unsigned i = 0; i < sizeof(TmSettings); ++i) dst[i] = 0;
    out->magic = TM_NV_MAGIC;
    out->version = TM_NV_VERSION;
    for (unsigned t = 0; t < TM_TRACKS; ++t) {
        out->lock[t] = TM_LOCK_DEFAULT;
        out->length[t] = TM_LENGTH_DEFAULT;
    }
}

static void tm_write(TmSettings *in) {
    volatile uint8_t *dst = (volatile uint8_t *)SETTINGS;
    const uint8_t *src = (const uint8_t *)in;
    in->check = 0;
    for (unsigned i = 0; i < sizeof(TmSettings) - 1u; ++i) dst[i] = src[i];
    dst[sizeof(TmSettings) - 1u] = tm_checksum(SETTINGS);
}

/* ---- the register ----------------------------------------------------- */

static uint32_t tm_random(uint32_t *state) {
    uint32_t x = *state;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    *state = x;
    return x;
}

/* The murmur3 finalizer: every input bit reaches every output bit. */
uint32_t tm_mix(uint32_t x) {
    x ^= x >> 16; x *= 0x85ebca6bu;
    x ^= x >> 13; x *= 0xc2b2ae35u;
    x ^= x >> 16;
    return x;
}

/* Taken once per boot, at the first trig of a Turing track: that trig fires
 * when PLAY is pressed (or a fixed number of steps after it), so the timer's
 * low bits are the moment of the press. A valid test record replaces it. */
uint32_t tm_boot_seed(void) {
    TmGlobals *g = &tm_globals;
    if (!g->seeded) {
        const volatile TmTestSeed *t = TEST_SEED;
        if (t->magic == TM_TEST_MAGIC && t->check == ~t->seed) g->seed = t->seed;
        else g->seed = tm_mix(WORD(TM_TIMER_COUNT)) ^ WORD(TM_SEQ_CLOCK);
        g->seeded = 1;
    }
    return g->seed;
}

/* One clock of a 16-bit shift register whose loop closes at LENGTH: the bit
 * at position LENGTH-1 comes back in at the bottom, inverted with a chance
 * set by LOCK. 127 never flips (the phrase repeats every LENGTH trigs), 64
 * flips about half the time, 0 always flips (a phrase twice as long, its
 * second half inverted). Bits above the loop point keep shifting, so a
 * shorter loop can grow again. Returns the low eight bits. */
unsigned tm_step(TmState *s, unsigned lock, unsigned length, unsigned track) {
    if (!s->seeded) {
        s->rng = tm_mix(tm_boot_seed() + 0x9e3779b9u * (track + 1u));
        if (!s->rng) s->rng = 0x6d2b79f5u;
        s->bits = (uint16_t)tm_random(&s->rng);
        s->seeded = 1;
    }
    unsigned out = (s->bits >> (length - 1u)) & 1u;
    unsigned threshold = (127u - lock) * 256u / 127u;
    if ((tm_random(&s->rng) & 0xffu) < threshold) out ^= 1u;
    s->bits = (uint16_t)((s->bits << 1) | out);
    return s->bits & 0xffu;
}

/* Chord slot 0 of a firing trig. notes[0..3] are NOTE and NOT2..NOT4 as the
 * stock sequencer resolved them (-1 = no note), before TRAN is added. The
 * trig's NOTE is the bottom of the range; every slot moves by the same
 * interval so chords keep their shape and the stock duplicate test still
 * sees NOT2..NOT4 equal to NOTE where they were. */
void tm_note(unsigned track, int8_t *notes) {
    if (track >= TM_TRACKS || notes[0] < 0) return;
    TmSettings s;
    tm_read(&s);
    if (!(s.enabled & (1u << track))) return;
    unsigned offset = tm_step(&tm_states[track], s.lock[track], s.length[track], track) * TM_SPAN / 255u;
    for (unsigned i = 0; i < 4u; ++i) {
        int note = notes[i];
        if (note < 0) continue;
        note += (int)offset;
        notes[i] = (int8_t)(note > 127 ? -1 : note);
    }
}

/* ---- MIDI SEQUENCER rows: a getter returns the value text, a setter takes
 * (delta, toggle). TURING TRACK picks the track the three rows below edit. */

static uint32_t tm_number(unsigned value) {
    char *p = tm_number_text;
    if (value >= 100u) *p++ = (char)('0' + value / 100u);
    if (value >= 10u) *p++ = (char)('0' + value / 10u % 10u);
    *p++ = (char)('0' + value % 10u);
    *p = 0;
    return (uint32_t)tm_number_text;
}

static unsigned tm_clamp(int32_t value, unsigned low, unsigned high) {
    return value < (int32_t)low ? low : value > (int32_t)high ? high : (unsigned)value;
}

static unsigned tm_edit(void) { return tm_globals.edit < TM_TRACKS ? tm_globals.edit : 0u; }

uint32_t tm_get_edit(void) { return (uint32_t)tm_track_names[tm_edit()]; }

uint32_t tm_get_mode(void) {
    TmSettings s;
    tm_read(&s);
    return (uint32_t)tm_mode_names[(s.enabled >> tm_edit()) & 1u];
}

uint32_t tm_get_lock(void) {
    TmSettings s;
    tm_read(&s);
    return tm_number(s.lock[tm_edit()]);
}

uint32_t tm_get_length(void) {
    TmSettings s;
    tm_read(&s);
    return tm_number(s.length[tm_edit()]);
}

void tm_set_edit(int32_t delta, int32_t toggle) {
    (void)toggle;
    tm_globals.edit = (uint8_t)tm_clamp((int32_t)tm_edit() + delta, 0u, TM_TRACKS - 1u);
}

void tm_set_mode(int32_t delta, int32_t toggle) {
    TmSettings s;
    unsigned t = tm_edit(), on;
    tm_read(&s);
    on = (s.enabled >> t) & 1u;
    on = toggle ? !on : tm_clamp((int32_t)on + delta, 0u, 1u);
    s.enabled = (uint8_t)((s.enabled & ~(1u << t)) | (on << t));
    tm_write(&s);
}

void tm_set_lock(int32_t delta, int32_t toggle) {
    TmSettings s;
    unsigned t = tm_edit();
    (void)toggle;
    tm_read(&s);
    s.lock[t] = (uint8_t)tm_clamp((int32_t)s.lock[t] + delta, 0u, 127u);
    tm_write(&s);
}

void tm_set_length(int32_t delta, int32_t toggle) {
    TmSettings s;
    unsigned t = tm_edit();
    (void)toggle;
    tm_read(&s);
    s.length[t] = (uint8_t)tm_clamp((int32_t)s.length[t] + delta, TM_LENGTH_MIN, TM_LENGTH_MAX);
    tm_write(&s);
}
