/* Turing machine engine. No floating point, allocation, runtime library
 * calls or clock of its own: on a MIDI track whose MODE is ON (per pattern)
 * the stock sequencer schedules one Turing step a step in place of the
 * track's trigs (tm_eval): the register advances as the step is scheduled;
 * a note step's note goes to the stock note path as a NOTE lock beside the
 * step's own locks, a rest step sends no note (its locks still go out). The
 * register is 64 bits in two 32-bit halves (no 64-bit shifts: they are
 * library calls). Compile to the checked-in ColdFire assembly with
 * generate.py. */
#include "turing.h"
#include "modwerk_events.h"

_Static_assert(sizeof(TmState) == 16, "register state");
_Static_assert(sizeof(TmGlobals) == 8, "hooks.s globals allocation");
_Static_assert(sizeof(TmSettings) == 32, "DRAM settings record");
_Static_assert(sizeof(TmTestSeed) == 12, "DRAM test seed record");
_Static_assert(sizeof(TmUi) == 28, "hooks.s page state allocation");
_Static_assert(sizeof(TmFirst) == 60, "hooks.s first-step allocation");
_Static_assert(sizeof(TmCell) == 12, "DRAM cells");
_Static_assert(sizeof(TmLive) == 12, "hooks.s live-register allocation");
#define SETTINGS (&tm_settings)
#define TEST_SEED (&tm_test_seed)
#define CELLS (tm_cells)
#define RANDOM (tm_random_states)
#define BYTE(address) (*(volatile uint8_t *)(address))
#define WORD(address) (*(volatile uint32_t *)(address))
#define CELL_COUNT (TM_BANKS * TM_PATTERNS * TM_TRACKS)

static const char tm_mode_names[2][4] = {"OFF", "ON"};

/* ---- settings --------------------------------------------------------- */

static uint8_t tm_checksum(const volatile TmSettings *s) {
    const volatile uint8_t *p = (const volatile uint8_t *)s;
    uint8_t sum = 0x5a;
    for (unsigned i = 0; i < sizeof(TmSettings) - 1u; ++i)
        sum ^= p[i];
    return sum;
}

static unsigned tm_valid(void) {
    const volatile TmSettings *s = SETTINGS;
    if (s->magic != TM_NV_MAGIC || s->version != TM_NV_VERSION || s->check != tm_checksum(s) ||
        (s->flags & ~(TM_FLAG_FIRST | TM_FLAG_CELLS10 | TM_FLAG_S2)))
        return 0;
    for (unsigned t = 0; t < TM_TRACKS; ++t)
        if (s->lock[t] > 127u || s->length[t] < TM_LENGTH_MIN || s->length[t] > TM_LENGTH_MAX)
            return 0;
    return 1;
}

static void tm_defaults(TmSettings *out) {
    uint8_t *dst = (uint8_t *)out;
    for (unsigned i = 0; i < sizeof(TmSettings); ++i)
        dst[i] = 0;
    out->magic = TM_NV_MAGIC;
    out->version = TM_NV_VERSION;
    for (unsigned t = 0; t < TM_TRACKS; ++t) {
        out->lock[t] = TM_LOCK_DEFAULT;
        out->length[t] = TM_LENGTH_DEFAULT;
    }
}

static void tm_read(TmSettings *out) {
    if (!tm_valid()) {
        tm_defaults(out);
        return;
    }
    const volatile uint8_t *src = (const volatile uint8_t *)SETTINGS;
    uint8_t *dst = (uint8_t *)out;
    for (unsigned i = 0; i < sizeof(TmSettings); ++i)
        dst[i] = src[i];
}

static void tm_write(TmSettings *in) {
    volatile uint8_t *dst = (volatile uint8_t *)SETTINGS;
    const uint8_t *src = (const uint8_t *)in;
    in->check = 0;
    for (unsigned i = 0; i < sizeof(TmSettings) - 1u; ++i)
        dst[i] = src[i];
    dst[sizeof(TmSettings) - 1u] = tm_checksum(SETTINGS);
}

/* ---- the register ----------------------------------------------------- */

static uint32_t tm_random(uint32_t *state) {
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

/* The murmur3 finalizer: every input bit reaches every output bit. */
uint32_t tm_mix(uint32_t x) {
    x ^= x >> 16;
    x *= 0x85ebca6bu;
    x ^= x >> 13;
    x *= 0xc2b2ae35u;
    x ^= x >> 16;
    return x;
}

/* Taken once per boot, at the first note of a Turing track, the first step
 * after PLAY, so the timer's low bits are the moment of the press. A valid
 * test record replaces it. */
uint32_t tm_boot_seed(void) {
    TmGlobals *g = &tm_globals;
    if (!g->seeded) {
        const volatile TmTestSeed *t = TEST_SEED;
        if (t->magic == TM_TEST_MAGIC && t->check == ~t->seed)
            g->seed = t->seed;
        else
            g->seed = tm_mix(WORD(TM_TIMER_COUNT)) ^ WORD(TM_SEQ_CLOCK);
        g->seeded = 1;
    }
    return g->seed;
}

/* LOCK: the chance, in 65536ths, that what comes round at the loop point
 * changes (the README's table). 96..127 never (the loop repeats exactly);
 * 64 random; 64..96 falling straight from random to none; 25 "slip", one
 * a pass of the loop (1/LEN); 25..64 rising straight from slip to random;
 * 0..25 rising from slip to "loose", still a loop. LEN 8..64 (a bit comes
 * round): random is a half, loose four bits a pass (at most 3/8). LEN 2..7
 * (a note comes round): random is every note, loose two notes a pass (at
 * most 5/8). */
unsigned tm_flip_chance(unsigned lock, unsigned length) {
    unsigned notes = length <= TM_NOTE_LOOP_MAX, slip = 65536u / length;
    unsigned random = notes ? 65536u : 32768u;
    unsigned loose =
        notes ? (slip * 2u > 40960u ? 40960u : slip * 2u) : (slip * 4u > 24576u ? 24576u : slip * 4u);
    if (lock >= 96u)
        return 0;
    if (lock >= 64u)
        return random / 32u * (96u - lock);
    if (lock >= 25u)
        return slip + (random - slip) * (lock - 25u) / 39u;
    return loose - (loose - slip) * lock / 25u;
}

/* SCAL: the range's width in semitones, centred on NOTE: 0 at 0 (NOTE
 * only), 24 at 64 (NOTE-12..NOTE+12), 48 at 127 (NOTE-24..NOTE+24),
 * straight in between. */
unsigned tm_span(unsigned scale) {
    if (scale <= 64u)
        return (scale * 3u + 4u) / 8u;
    return 24u + ((scale - 64u) * 24u + 31u) / 63u;
}

/* DENS: a step is a note when its value (tm_step_value: the register's newest
 * eight bits), read newest bit first, is below 2 * DENS (every step at 127,
 * none at 0; at 64 exactly when the newest bit is 0, as a Turing machine's
 * pulse). A function of the register alone, so a locked loop rests on the
 * same steps every pass and a DENS turned back gives the old rhythm back. */
unsigned tm_gate(uint32_t value, unsigned density) {
    unsigned g = 0;
    for (unsigned i = 0; i < 8u; ++i)
        g |= ((value >> i) & 1u) << (7u - i);
    return g < (density >= 127u ? 256u : density * 2u);
}

/* Each pattern's register is seeded apart, 64 random bits, like a Turing
 * machine powering up: salt is bank * 16 + pattern. */
static void tm_seed(TmState *s, unsigned track, unsigned salt) {
    uint32_t x = tm_mix(tm_boot_seed() + 0x9e3779b9u * (track + 1u) + 0x85ebca6bu * salt);
    s->low = x;
    s->high = tm_mix(x + 0x6d2b79f5u);
    s->seeded = 1;
}

/* A register about to clock: seeded if it never was, and the track's random state. */
static void tm_ready(TmState *s, unsigned track, unsigned salt) {
    if (!s->seeded)
        tm_seed(s, track, salt);
    if (!s->rng) {
        s->rng = tm_mix(tm_boot_seed() + 0x9e3779b9u * (track + 1u) + 0x632be5abu);
        if (!s->rng)
            s->rng = 0x6d2b79f5u;
    }
}

/* The bit at the loop point, position LEN-1. */
static unsigned tm_loop_bit(const TmState *s, unsigned length) {
    unsigned at = length - 1u;
    return (at < 32u ? s->low >> at : s->high >> (at - 32u)) & 1u;
}

static void tm_shift(TmState *s, unsigned in) {
    s->high = s->high << 1 | s->low >> 31;
    s->low = s->low << 1 | in;
}

/* One clock of the loop, `flip` inverting what comes round at the loop
 * point.
 *  - LEN 8..64, a shift register: the bit at position LEN-1 comes back in
 *    at the bottom (flip: 1 inverts it). Bits above the loop point keep
 *    shifting, so a shorter loop can grow again.
 *  - LEN 2..7, a loop of notes: the register's newest LEN bytes turn a byte
 *    a step, byte LEN-1 back to byte 0 (flip: the bits it inverts), and the
 *    top byte counts the loop's place, 0..LEN-1 (tm_step_value). Each step reads
 *    a whole byte of its own, so the loop repeats every LEN steps and cannot
 *    settle into one note (a 2- or 3-bit loop does, half or a quarter of the
 *    time, and then fills the whole register). The bytes between the loop
 *    and the count are kept as they are, so a longer loop finds them. */
static void tm_advance(TmState *s, unsigned length, unsigned flip) {
    if (length > TM_NOTE_LOOP_MAX) {
        tm_shift(s, tm_loop_bit(s, length) ^ (flip & 1u));
        return;
    }
    uint8_t b[8];
    for (unsigned i = 0; i < 4u; ++i) {
        b[i] = (uint8_t)(s->low >> (8u * i));
        b[4u + i] = (uint8_t)(s->high >> (8u * i));
    }
    uint8_t in = (uint8_t)(b[length - 1u] ^ flip);
    for (unsigned i = length - 1u; i > 0u; --i)
        b[i] = b[i - 1u];
    b[0] = in;
    b[7] = (uint8_t)((b[7] % length + 1u) % length);
    s->low = (uint32_t)b[3] << 24 | (uint32_t)b[2] << 16 | (uint32_t)b[1] << 8 | b[0];
    s->high = (uint32_t)b[7] << 24 | (uint32_t)b[6] << 16 | (uint32_t)b[5] << 8 | b[4];
}

/* The step's value, 0..255: the newest eight bits; in a loop of notes the
 * newest byte with its place's key inverted, so a loop whose bytes are alike
 * (as the history of a shift register's loop is) still plays LEN notes. */
static const uint8_t tm_keys[TM_NOTE_LOOP_MAX] = {0x00, 0xb5, 0x6a, 0xd3, 0x2c, 0x99, 0x47};

static unsigned tm_step_value(const TmState *s, unsigned length) {
    if (length > TM_NOTE_LOOP_MAX)
        return s->low & 0xffu;
    return (s->low & 0xffu) ^ tm_keys[(s->high >> 24) % length];
}

/* One clock of the register, what comes round changing with the chance LOCK
 * sets: one draw of the track's random state every clock; a note loop's
 * byte has the draw's bits 16..23 inverted (bit 7 if none). Returns the
 * step's value (tm_step_value). */
unsigned tm_step(TmState *s, unsigned lock, unsigned length, unsigned track, unsigned salt) {
    tm_ready(s, track, salt);
    uint32_t r = tm_random(&s->rng);
    unsigned flip = 0;
    if ((r & 0xffffu) < tm_flip_chance(lock, length)) {
        flip = length > TM_NOTE_LOOP_MAX ? 1u : (r >> 16) & 0xffu;
        if (!flip)
            flip = 0x80u;
    }
    tm_advance(s, length, flip);
    return tm_step_value(s, length);
}

/* The register's note: the eight bits spread over SCAL's range around the
 * centre, value * span / 255 - span / 2; a note off the MIDI range moves an
 * octave in. */
int tm_turing_note(unsigned centre, unsigned value, unsigned scale) {
    unsigned span = tm_span(scale);
    int note = (int)centre + (int)(value * span / 255u) - (int)(span / 2u);
    while (note < 0)
        note += 12;
    while (note > 127)
        note -= 12;
    return note;
}

/* ---- per-pattern cells (turing.h) ------------------------------------------ */

typedef struct {
    unsigned on, lock, length, scale, density;
} TmConfig;

static unsigned tm_cell_valid(const volatile TmCell *c) {
    unsigned length = (c->length & 0x7fu) ^ TM_LENGTH_DEFAULT;
    return length >= TM_LENGTH_MIN && length <= TM_LENGTH_MAX && c->scale <= 127u && c->density <= 127u;
}

static void tm_cells_clear(void) {
    volatile uint32_t *p = (volatile uint32_t *)CELLS;
    for (unsigned i = 0; i < CELL_COUNT * sizeof(TmCell) / 4u; ++i)
        p[i] = 0;
}

/* Fresh loader-owned DRAM is already zeroed. There is no battery import;
 * migration happens only through validated saved-project comments. */
static void tm_cells_ready(void) {
    if (tm_globals.cells)
        return;
    tm_globals.cells = 1;
    TmSettings s;
    tm_defaults(&s);
    s.flags = TM_FLAG_CELLS10;
    tm_write(&s);
}

static volatile TmCell *tm_cell(uint32_t bank, uint32_t pattern, uint32_t track) {
    tm_cells_ready();
    if (bank >= TM_BANKS)
        bank = 0;
    if (pattern >= TM_PATTERNS)
        pattern = 0;
    if (track >= TM_TRACKS)
        track = 0;
    return CELLS + (bank * TM_PATTERNS + pattern) * TM_TRACKS + track;
}

static void tm_legacy_config(const volatile TmCell *c, TmConfig *out) {
    if (!tm_cell_valid(c)) {
        out->on = 0;
        out->lock = TM_LOCK_DEFAULT;
        out->length = TM_LENGTH_DEFAULT;
        out->scale = TM_SCALE_DEFAULT;
        out->density = TM_DENSITY_DEFAULT;
        return;
    }
    out->on = (c->cfg & TM_CELL_ON) ? 1u : 0u;
    out->lock = (c->cfg & 0x7fu) ^ TM_LOCK_DEFAULT;
    out->length = (c->length & 0x7fu) ^ TM_LENGTH_DEFAULT;
    out->scale = c->scale ^ TM_SCALE_DEFAULT;
    out->density = c->density ^ TM_DENSITY_DEFAULT;
}

static unsigned tm_seeded(const volatile TmCell *c) { return tm_cell_valid(c) && (c->length & TM_CELL_SEEDED); }

/* A cell out of range is reset (its register too) before a change lands. */
static void tm_set_config(volatile TmCell *c, const TmConfig *in) {
    unsigned seeded = tm_seeded(c) ? TM_CELL_SEEDED : 0u;
    if (!tm_cell_valid(c)) {
        c->high = 0;
        c->low = 0;
    }
    c->cfg = (uint8_t)((in->on ? TM_CELL_ON : 0u) | ((in->lock ^ TM_LOCK_DEFAULT) & 0x7fu));
    c->length = (uint8_t)(seeded | ((in->length ^ TM_LENGTH_DEFAULT) & 0x7fu));
    c->scale = (uint8_t)((in->scale ^ TM_SCALE_DEFAULT) & 0x7fu);
    c->density = (uint8_t)((in->density ^ TM_DENSITY_DEFAULT) & 0x7fu);
}

/* ---- generator Part storage (S2) ---------------------------------------
 * All sixteen arp notes stay in stock's signed -64..63 validator range.
 * Logical values are biased by 64: LOCK, LEN, SCAL, DENS, SCALE, ROOT,
 * layout (1), signature (53). The other eight notes are unused. */
#define TM_GEN_ID 1u
#define TM_PART_BASE 0x8ed80u
#define TM_MASK(t) (0x1822u + 2u * (t))
#define TM_NOTES(t) (0x1832u + 16u * (t))
#define TM_BANK_PTR 0x46c82456u
#define TM_CUR_PART 0x100b14cfu
#define TM_SRAM_PART 0x100a4eceu
static volatile unsigned tm_migration_ready;
static volatile unsigned tm_project_loading;
static volatile unsigned tm_load_generation;
/* Exclude task switches only; sequencer/audio interrupts remain enabled.
 * Protect reset or one migration batch, never file I/O. Higher-priority
 * sequencer, USB, audio and DMA interrupts remain enabled. */
static uint16_t tm_task_lock(void) {
    uint16_t sr;
    __asm__ volatile("move.w %%sr,%0" : "=d"(sr) :: "memory");
    if ((sr & 0x700u) < 0x200u) {
        uint16_t locked = (uint16_t)((sr & ~0x700u) | 0x200u);
        __asm__ volatile("move.w %0,%%sr" :: "d"(locked) : "memory");
    }
    return sr;
}
static void tm_task_unlock(uint16_t sr) {
    __asm__ volatile("move.w %0,%%sr" :: "d"(sr) : "memory");
}
static unsigned tm_install_read_done;
volatile unsigned tm_ready_events;
/* WRITE's centres are ours, never pattern lock bytes 30/31 (Arp Key Locks).
 * Zero means absent; centre + 1 keeps MIDI note zero representable. */
static uint8_t tm_written_centres[CELL_COUNT][TM_STEPS];
static uint8_t tm_scheduled[TM_TRACKS];

static volatile uint8_t *tm_part(unsigned bank, unsigned part) {
    return (volatile uint8_t *)(TM_SEQ_BANKS + bank * TM_SEQ_BANK_SIZE + TM_PART_BASE + part * TM_PART_SIZE);
}
static unsigned tm_pattern_part(unsigned bank, unsigned pattern) {
    return *(volatile uint8_t *)(TM_SEQ_BANKS + bank * TM_SEQ_BANK_SIZE + pattern * TM_SEQ_PATTERN_SIZE +
                                 TM_SEQ_PART) &
           3u;
}
static unsigned tm_selected(const volatile uint8_t *part, unsigned t) {
    return part[TM_MASK(t)] == 'M' && part[TM_MASK(t) + 1u] == TM_GEN_ID;
}
static unsigned tm_setting(const volatile uint8_t *part, unsigned t, unsigned slot) {
    return (part[TM_NOTES(t) + slot] + 64u) & 127u;
}
static unsigned tm_part_valid(const volatile uint8_t *part, unsigned t) {
    return tm_setting(part, t, 6) == 1u && tm_setting(part, t, 7) == 53u && tm_setting(part, t, 1) >= 2u &&
           tm_setting(part, t, 1) <= 64u && tm_setting(part, t, 4) <= 2u && tm_setting(part, t, 5) < 12u;
}
static void tm_part_byte(unsigned bank, unsigned part, unsigned off, uint8_t value) {
    volatile uint8_t *p = tm_part(bank, part);
    p[off] = value;
    unsigned current = WORD(TM_BANK_PTR) == TM_SEQ_BANKS + bank * TM_SEQ_BANK_SIZE;
    if (current)
        ((volatile uint8_t *)TM_SRAM_PART)[part * TM_PART_SIZE + off] = value;
    BYTE(TM_SEQ_BANKS + bank * TM_SEQ_BANK_SIZE + 0x95048u) |= (uint8_t)(1u << part);
    if (current)
        BYTE(0x100b145eu) |= (uint8_t)(1u << part);
    WORD(TM_SEQ_BANKS + bank * TM_SEQ_BANK_SIZE + 0x9b332u) = 1;
    WORD(0x100f8598u) = 1;
}
static void tm_part_setting(unsigned b, unsigned p, unsigned t, unsigned slot, unsigned value) {
    tm_part_byte(b, p, TM_NOTES(t) + slot, (uint8_t)(value - 64u));
}
static void tm_part_init(unsigned b, unsigned p, unsigned t, const TmConfig *k, unsigned key) {
    const unsigned values[8] = {
        k->lock, k->length, k->scale, k->density, key ? ((key - 1u) & 1u) + 1u : 0u, key ? (key - 1u) / 2u : 0u,
        1u,      53u};
    for (unsigned i = 0; i < 16u; ++i)
        tm_part_setting(b, p, t, i, i < 8u ? values[i] : 64u);
}
static void tm_config(const volatile TmCell *c, TmConfig *out) {
    unsigned index = (unsigned)(c - CELLS), t = index % TM_TRACKS;
    unsigned pattern = index / TM_TRACKS % TM_PATTERNS, bank = index / (TM_TRACKS * TM_PATTERNS);
    tm_legacy_config(c, out);
    const volatile uint8_t *part = tm_part(bank, tm_pattern_part(bank, pattern));
    if (!tm_migration_ready || !tm_selected(part, t) || !tm_part_valid(part, t)) {
        out->on = 0;
        return;
    }
    out->lock = tm_setting(part, t, 0);
    out->length = tm_setting(part, t, 1);
    out->scale = tm_setting(part, t, 2);
    out->density = tm_setting(part, t, 3);
}
/* UI task only, after the complete project load. The lowest-numbered enabled
 * pattern supplies a shared Part's old settings. Never migrate again once
 * S2 is present in the project or retained settings: choosing OFF must win. */
void tm_generator_tick(void) {
    if (tm_migration_ready || tm_project_loading)
        return;
    unsigned generation = tm_load_generation;
    uint32_t ui_bank = WORD(TM_BANK_PTR);
    if (ui_bank < TM_SEQ_BANKS || ui_bank >= TM_SEQ_BANKS + TM_BANKS * TM_SEQ_BANK_SIZE)
        return;
    TmSettings s;
    tm_read(&s);
    if (!(s.flags & TM_FLAG_S2)) {
        for (unsigned b = 0; b < TM_BANKS; ++b)
            for (unsigned q = 0; q < TM_PATTERNS; ++q)
                for (unsigned t = 0; t < TM_TRACKS; ++t) {
                    uint16_t sr = tm_task_lock();
                    if (tm_project_loading || generation != tm_load_generation) {
                        tm_task_unlock(sr);
                        return;
                    }
                    TmConfig k;
                    tm_legacy_config(tm_cell(b, q, t), &k);
                    unsigned p = tm_pattern_part(b, q);
                    volatile uint8_t *part = tm_part(b, p);
                    if (!k.on || part[TM_MASK(t)] == 'M') {
                        tm_task_unlock(sr);
                        continue;
                    }
                    unsigned key = part[0x4e2u + 36u * t + 17u];
                    if (key > 24u)
                        key = 0;
                    tm_part_init(b, p, t, &k, key);
                    tm_part_byte(b, p, TM_MASK(t), 'M');
                    tm_part_byte(b, p, TM_MASK(t) + 1u, TM_GEN_ID);
                    tm_part_byte(b, p, 0x3e2u + 32u * t + 14u, 0); /* preserve TRAN and KEY */
                    tm_task_unlock(sr);
                }
        /* A new load may have started while this tick was preempted. */
        uint16_t sr = tm_task_lock();
        if (tm_project_loading || generation != tm_load_generation) {
            tm_task_unlock(sr);
            return;
        }
        s.flags |= TM_FLAG_S2;
        s.flags &= ~TM_FLAG_FIRST;
        tm_write(&s);
        tm_migration_ready = 1;
        tm_task_unlock(sr);
        ((void (*)(void))0x40027e00u)();
        return;
    }
    uint16_t sr = tm_task_lock();
    if (!tm_project_loading && generation == tm_load_generation)
        tm_migration_ready = 1;
    tm_task_unlock(sr);
}
static unsigned tm_ui_bank_index(void) {
    uint32_t bank = WORD(TM_BANK_PTR);
    return bank >= TM_SEQ_BANKS && bank < TM_SEQ_BANKS + TM_BANKS * TM_SEQ_BANK_SIZE
               ? (bank - TM_SEQ_BANKS) / TM_SEQ_BANK_SIZE
               : 0u;
}
static unsigned tm_note_part(unsigned t, unsigned *bank) {
    /* MIDI's own playing-context latches, independent of the audio engine. */
    unsigned b = BYTE(0x8000666eu + t), p = BYTE(0x80006676u + t);
    if (b >= TM_BANKS || p >= 4u) {
        b = BYTE(TM_UI_BANK) & 15u;
        p = tm_pattern_part(b, BYTE(TM_UI_PATTERN) & 15u);
    }
    *bank = b;
    return p;
}
unsigned tm_note_claims(unsigned t) {
    unsigned b;
    if (t >= TM_TRACKS || !tm_migration_ready)
        return 0;
    unsigned p = tm_note_part(t, &b);
    return tm_selected(tm_part(b, p), t);
}
/* Shared scale SDK, after stock TRAN and the range check. scale.c keeps
 * the historical down-one/drop rule at note zero. */
#include "scale.c"

unsigned tm_note_key(unsigned t, volatile int8_t *note) {
    if (!tm_note_claims(t))
        return 0;
    unsigned b;
    unsigned p = tm_note_part(t, &b);
    const volatile uint8_t *part = tm_part(b, p);
    if (tm_part_valid(part, t))
        *note = (int8_t)tm_scale_snap(*note, tm_setting(part, t, 4), tm_setting(part, t, 5));
    return 1; /* own OFF bypasses the old KEY too */
}

/* The cell's register (the one its pass starts from) and the track's random state. */
static void tm_load_state(const volatile TmCell *c, uint32_t track, TmState *s) {
    s->seeded = (uint8_t)tm_seeded(c);
    s->high = c->high;
    s->low = c->low;
    s->rng = RANDOM[track];
    s->reserved[0] = s->reserved[1] = s->reserved[2] = 0;
}

static void tm_store_anchor(volatile TmCell *c, const TmState *s) {
    c->high = s->high;
    c->low = s->low;
    c->length = (uint8_t)((c->length & 0x7fu) | TM_CELL_SEEDED);
}

/* ---- the register a track plays (turing.h TmLive) ---------------------------- */

static uint16_t tm_index(const volatile TmCell *c) { return (uint16_t)(c - CELLS); }

static void tm_drop(uint32_t track) { tm_live[track].valid = 0; }

/* The register of cell c as it is before step `step`: the one playing when
 * the step follows on, else the cell's clocked `step` times as a locked loop
 * (a never-seeded cell is seeded first, and that is its pass's start). At
 * step 0 it becomes the cell's register: the start of the pass. */
static void tm_position(uint32_t track, volatile TmCell *c, unsigned length, unsigned step, unsigned salt,
                        TmState *s) {
    TmLive *l = &tm_live[track];
    if (l->valid && l->cell == tm_index(c) && l->next == step) {
        s->high = l->high;
        s->low = l->low;
        s->seeded = 1;
        s->rng = RANDOM[track];
        s->reserved[0] = s->reserved[1] = s->reserved[2] = 0;
        tm_ready(s, track, salt);
    } else {
        tm_load_state(c, track, s);
        unsigned fresh = !s->seeded;
        tm_ready(s, track, salt);
        if (fresh)
            tm_store_anchor(c, s);
        for (unsigned i = 0; i < step; ++i)
            tm_advance(s, length, 0);
    }
    if (step == 0u)
        tm_store_anchor(c, s);
}

static void tm_keep(uint32_t track, const volatile TmCell *c, const TmState *s, unsigned next) {
    TmLive *l = &tm_live[track];
    l->high = s->high;
    l->low = s->low;
    l->cell = tm_index(c);
    l->next = (uint8_t)next;
    l->valid = 1;
    RANDOM[track] = s->rng;
}

static unsigned tm_on(uint32_t bank, uint32_t pattern, uint32_t track);

/* Chord ownership is module state, never another module's saved lock bytes. */
int32_t tm_fired(uint32_t track) {
    unsigned owned = track < TM_TRACKS && tm_scheduled[track];
    if (owned || tm_note_claims(track)) {
        BYTE(0x46c76dc0u + 0x44u * track + 14u) = 0;
        BYTE(0x46c76fe0u + 32u * track + 14u) = 0;
    }
    /* The next pattern/Part can already be current when the last queued
     * step fires. Its ownership belongs to the evaluated step, not the UI. */
    return owned;
}

/* ---- REPLACE mode: one Turing step per step ---------------------------------
 * The MIDI sequencer's per-step trig evaluator 0x4009cf4c(track, bank,
 * pattern, step, slot) runs once per step of every MIDI track, and at STOP
 * (or a load) for the first step of the next PLAY, slot -1. Stock evaluates
 * the step's trig condition and trig bitmaps and, for a trig, writes the
 * event, its microtiming plus swing, its repeat count and interval and its
 * lock record; with no trig (or a condition that fails) it writes nothing.
 * On a track whose MODE is ON in the pattern being scheduled, stock's
 * evaluation still runs (so conditions are counted and locks resolved as
 * stock), and then the register advances once. A note step (DENS, tm_gate)
 * becomes a plain note trig (event 29, one note) on the grid plus the
 * step's swing: its lock record is stock's when the step had a trig or a
 * trigless lock and passed its condition, else no locks, and the register's
 * note goes in as the record's NOTE lock, centred on the step's own NOTE
 * lock (or, for a NOTE lock WRITE put there, the centre it was written
 * from) or the Part's NOTE. A rest step sends no note: nothing at all,
 * unless stock scheduled the step, which then goes out as a trigless trig
 * with stock's locks and timing (its CC locks are sent, as a lock trig's).
 * The tick ISR applies the record as for any trig (VEL, LEN, CC locks; the
 * LFO adds to NOTE after it; the arpeggiator and its KEY take the note in
 * as a trig's), and module-owned scheduling state tells the
 * chord hook drops NOT2..NOT4 and releases the step (tm_fired). A muted
 * step is scheduled the same: the register goes on and stock's note routine
 * sends nothing. The track's condition result is true on a note step and
 * false on a rest: what NEI on the next track reads. The swing and speed
 * reads are the stock evaluator's own (turing.h). */

static unsigned tm_on(uint32_t bank, uint32_t pattern, uint32_t track) {
    TmConfig k;
    tm_config(tm_cell(bank, pattern, track), &k);
    return k.on;
}

static const volatile uint8_t *tm_bank(uint32_t bank) {
    return (const volatile uint8_t *)(TM_SEQ_BANKS + bank * TM_SEQ_BANK_SIZE);
}

/* The steps a pass of the track takes: the pattern's length, or the track's with per-track scales. */
static unsigned tm_pattern_length(const volatile uint8_t *pat, uint32_t track) {
    unsigned length =
        pat[TM_SEQ_SCALE + 1u] ? pat[TM_SEQ_TRACK_LENGTH + track * TM_SEQ_TRACK_SIZE] : pat[TM_SEQ_LENGTH];
    return length < 1u ? 1u : length > TM_STEPS ? TM_STEPS : length;
}

static unsigned tm_steps(uint32_t track, uint32_t bank, uint32_t pattern) {
    return tm_pattern_length(tm_bank(bank) + pattern * TM_SEQ_PATTERN_SIZE, track);
}

/* The step's Turing trig. */
static void tm_turing_event(uint32_t track, uint32_t bank, uint32_t pattern, uint32_t step, TmEvent *e) {
    const volatile uint8_t *banks = tm_bank(bank);
    const volatile uint8_t *pat = banks + pattern * TM_SEQ_PATTERN_SIZE;
    unsigned scale =
        pat[TM_SEQ_SCALE + 1u] ? pat[TM_SEQ_TRACK_SCALE + track * TM_SEQ_TRACK_SIZE] : pat[TM_SEQ_SCALE];
    int32_t speed = *(const volatile int8_t *)(TM_SEQ_SPEEDS + 4u * (uint32_t)(int8_t)scale + 3u);
    uint32_t word = track * 556u + pattern * 9142u + (step < 32u ? 1u : 0u) + TM_SEQ_SWING_BITS;
    int32_t swing = 0;
    if (*(const volatile uint32_t *)(banks + 4u * word) & (1u << (step & 31u)))
        swing = *(const volatile int8_t *)(pat + TM_SEQ_SWING + track * TM_SEQ_TRACK_SIZE) * 336 * speed;
    e->event = TM_EV_NOTE_TRIG;
    e->repeats = 1;
    e->timing = swing;
    e->interval = speed * *(const volatile int32_t *)(TM_SEQ_REPEAT_TICKS + 4u);
}

static void tm_put_event(uint32_t track, const TmEvent *e) {
    WORD(TM_EV_EVENT + 4u * track) = (uint32_t)e->event;
    WORD(TM_EV_REPEATS + 4u * track) = (uint32_t)e->repeats;
    WORD(TM_EV_TIMING + 4u * track) = (uint32_t)e->timing;
    WORD(TM_EV_INTERVAL + 4u * track) = (uint32_t)e->interval;
}

/* The track's NOTE in the Part the pattern plays. */
static unsigned tm_part_note(uint32_t track, uint32_t bank, uint32_t pattern) {
    const volatile uint8_t *banks = tm_bank(bank);
    unsigned part = banks[pattern * TM_SEQ_PATTERN_SIZE + TM_SEQ_PART] & 3u;
    return banks[TM_PART_TRACKS + part * TM_PART_SIZE + track * 32u] & 0x7fu;
}

/* A lock record's centre: its NOTE lock (WRITE's: the centre it was written from), else the Part's NOTE. */
static unsigned tm_centre(const volatile uint8_t *record, uint32_t track, uint32_t bank, uint32_t pattern,
                          unsigned step) {
    if (record[0] == TM_LOCK_NONE)
        return tm_part_note(track, bank, pattern);
    unsigned saved = tm_written_centres[(bank * TM_PATTERNS + pattern) * TM_TRACKS + track][step];
    if (saved)
        return saved - 1u;
    /* Read-only compatibility with earlier Turing WRITE data. 'W' (87)
     * is outside AKL's valid KEY range 0..84. Never create or clear it. */
    if (record[30] == 0x57u && record[31] < 128u)
        return record[31];
    return record[0] & 0x7fu;
}

/* A Turing step's record: stock's locks when stock scheduled the step
 * (locks != 0 or stocked), else none; for a note step the register's note
 * as its NOTE lock; ownership stays in module state. The register advances here (tm_position), and
 * the track's condition result is set (true for a note). Nonzero for a note
 * step. */
static unsigned tm_turing_record(volatile uint8_t *record, const uint8_t *locks, unsigned stocked,
                                 uint32_t track, uint32_t bank, uint32_t pattern, uint32_t step,
                                 const TmConfig *config) {
    if (locks)
        for (unsigned i = 0; i < 32u; ++i)
            record[i] = locks[i];
    else if (!stocked)
        for (unsigned i = 0; i < 32u; ++i)
            record[i] = TM_LOCK_NONE;
    unsigned centre = tm_centre(record, track, bank, pattern, step);
    volatile TmCell *c = tm_cell(bank, pattern, track);
    const TmConfig k = *config;
    unsigned salt = bank * TM_PATTERNS + pattern, steps = tm_steps(track, bank, pattern);
    TmState s;
    tm_position(track, c, k.length, step % steps, salt, &s);
    unsigned value = tm_step(&s, k.lock, k.length, track, salt);
    tm_keep(track, c, &s, (step + 1u) % steps);
    unsigned gate = tm_gate(value, k.density);
    tm_scheduled[track] = 1;
    if (gate)
        record[0] = (uint8_t)tm_turing_note(centre, value, k.scale);
    *(volatile uint8_t *)(TM_COND_RESULTS + TM_TRACKS + track) = gate ? 0u : 1u;
    return gate;
}

/* The entry detour: nonzero when the step is handled here and the stock
 * evaluator must not run again. For the first step (slot -1) the stock
 * evaluator always runs, from here, and what it wrote is kept, so tm_play
 * can give PLAY the Turing step then (the register advances at PLAY, not
 * at STOP or a load). */
int32_t tm_eval(uint32_t track, uint32_t bank, uint32_t pattern, uint32_t step, int32_t slot) {
    if (track >= TM_TRACKS || step >= TM_STEPS || bank >= TM_BANKS || pattern >= TM_PATTERNS)
        return 0;
    TmConfig config;
    tm_config(tm_cell(bank, pattern, track), &config);
    unsigned on = config.on;
    if (slot < 0) {
        tm_scheduled[track] = 0;
        TmFirst *f = &tm_first_steps[track];
        volatile uint8_t *record = (volatile uint8_t *)(TM_EV_RECORD_FIRST + track * 32u);
        tm_drop(track);
        tm_globals.playing = 0;
        WORD(TM_EV_EVENT + 4u * track) = 0;
        tm_stock_eval(track, bank, pattern, step, slot);
        f->stock.event = (int32_t)WORD(TM_EV_EVENT + 4u * track);
        f->stock.repeats = (int32_t)WORD(TM_EV_REPEATS + 4u * track);
        f->stock.timing = (int32_t)WORD(TM_EV_TIMING + 4u * track);
        f->stock.interval = (int32_t)WORD(TM_EV_INTERVAL + 4u * track);
        for (unsigned i = 0; i < 32u; ++i)
            f->locks[i] = record[i];
        f->bank = bank;
        f->pattern = pattern;
        f->step = (uint8_t)step;
        f->valid = 1;
        if (on)
            *(volatile uint8_t *)(TM_COND_RESULTS + TM_TRACKS + track) = 0;
        return 1;
    }
    if (!on) {
        tm_scheduled[track] = 0;
        return 0;
    }
    WORD(TM_EV_EVENT + 4u * track) = 0;
    tm_stock_eval(track, bank, pattern, step, slot);
    uint32_t stock = WORD(TM_EV_EVENT + 4u * track);
    if (tm_turing_record((volatile uint8_t *)(TM_EV_RECORDS + (uint32_t)slot * 256u + track * 32u), 0,
                         stock != 0u, track, bank, pattern, step, &config)) {
        TmEvent e;
        tm_turing_event(track, bank, pattern, step, &e);
        tm_put_event(track, &e);
    } else if (stock == TM_EV_NOTE_TRIG) { /* a rest on a trig: its locks, no note */
        WORD(TM_EV_EVENT + 4u * track) = TM_EV_LOCK_TRIG;
        WORD(TM_EV_REPEATS + 4u * track) = 1;
    }
    return 1;
}

/* PLAY (0x4009c076), before it copies the first step: on a track whose MODE
 * is ON in the first step's pattern, its copied event, repeats, interval,
 * timing and lock record become the Turing step's; stock's stay otherwise. */
void tm_play(void) {
    tm_globals.playing = 1;
    for (unsigned t = 0; t < TM_TRACKS; ++t) {
        TmFirst *f = &tm_first_steps[t];
        if (!f->valid)
            continue;
        f->valid = 0;
        TmConfig config;
        tm_config(tm_cell(f->bank, f->pattern, t), &config);
        if (!config.on) {
            tm_scheduled[t] = 0;
            continue;
        }
        if (tm_turing_record((volatile uint8_t *)(TM_EV_RECORD_FIRST + t * 32u), f->stock.event ? f->locks : 0,
                             0, t, f->bank, f->pattern, f->step, &config)) {
            TmEvent turing;
            tm_turing_event(t, f->bank, f->pattern, f->step, &turing);
            WORD(TM_FIRST_EVENT + 4u * t) = (uint32_t)turing.event;
            WORD(TM_FIRST_REPEATS + 4u * t) = (uint32_t)turing.repeats;
            WORD(TM_FIRST_INTERVAL + 4u * t) = (uint32_t)turing.interval;
            WORD(TM_FIRST_TIMING + 4u * t) += (uint32_t)(turing.timing - f->stock.timing);
        } else if (f->stock.event == (int32_t)TM_EV_NOTE_TRIG) {
            WORD(TM_FIRST_EVENT + 4u * t) = TM_EV_LOCK_TRIG;
            WORD(TM_FIRST_REPEATS + 4u * t) = 1;
        } else if (!f->stock.event) {
            WORD(TM_FIRST_EVENT + 4u * t) = 0;
        }
    }
}

/* ---- WRITE: the Turing sequence into the track's own trigs -----------------
 * Knob A pushed and released (not turned) on the TURING page while MODE is
 * ON. Over the pattern's length (the track's, with per-track scales), from
 * the step the track plays next (the register playing; step 1 and the
 * cell's register while stopped), the register is clocked as a locked loop
 * would clock it (no flips) on a copy, and each step becomes what the Turing
 * machine would make of it:
 *  - a note step: a note trig, its NOTE lock the register's note (before
 *    the ARP, the LFO and TRAN, which act on it as on the Turing note),
 *    NOT2..NOT4 locked to the NOTE itself (one note, as ON plays), its
 *    condition, microtiming and retrigs cleared (ON ignores them); its other
 *    locks kept; module-owned DRAM and saved comments keep the NOTE centre,
 *    so ON goes on playing the same notes without owning another module's bytes.
 *    Its LED flashes as any locked trig's does on stock (a hand-placed trig
 *    with a NOTE lock flashes the same);
 *  - a rest: no note trig; a trig that carries locks becomes a trigless
 *    trig with them (ON sends them on a rest the same), WRITE's own NOTE
 *    lock is taken off.
 * MODE stays ON and the register is not moved. Nonzero when written. */

unsigned tm_write_track(unsigned track) {
    uint32_t bank = *(volatile uint8_t *)TM_UI_BANK, pattern = *(volatile uint8_t *)TM_UI_PATTERN;
    if (track >= TM_TRACKS || bank >= TM_BANKS || pattern >= TM_PATTERNS)
        return 0;
    volatile TmCell *c = tm_cell(bank, pattern, track);
    TmConfig k;
    tm_config(c, &k);
    if (!k.on)
        return 0;
    volatile uint8_t *banks = (volatile uint8_t *)(TM_SEQ_BANKS + bank * TM_SEQ_BANK_SIZE);
    volatile uint8_t *pat = banks + pattern * TM_SEQ_PATTERN_SIZE;
    volatile uint8_t *locks = pat + track * TM_SEQ_TRACK_SIZE + TM_SEQ_LOCKS;
    volatile uint16_t *conds = (volatile uint16_t *)(pat + track * TM_SEQ_TRACK_SIZE + TM_SEQ_CONDS);
    volatile uint32_t *bits = (volatile uint32_t *)banks + track * 556u + pattern * 9142u;
    unsigned length = tm_pattern_length(pat, track), start = 0;
    const TmLive *l = &tm_live[track];
    TmState s;
    if (tm_globals.playing && l->valid && l->cell == tm_index(c)) {
        s.high = l->high;
        s.low = l->low;
        start = l->next % length;
    } else {
        tm_load_state(c, track, &s);
        if (!s.seeded) { /* never played: seed it, the sequence ON will play */
            tm_seed(&s, track, bank * TM_PATTERNS + pattern);
            tm_store_anchor(c, &s);
        }
    }
    unsigned part = tm_part_note(track, bank, pattern);
    for (unsigned i = 0; i < length; ++i) {
        unsigned step = (start + i) % length;
        tm_advance(&s, k.length, 0);
        volatile uint8_t *r = locks + step * 32u;
        volatile uint32_t *note_bits = bits + TM_SEQ_NOTE_BITS + (step < 32u ? 1u : 0u);
        volatile uint32_t *lock_bits = bits + TM_SEQ_LOCK_BITS + (step < 32u ? 1u : 0u);
        uint32_t bit = 1u << (step & 31u);
        unsigned trig = ((*note_bits | *lock_bits) & bit) != 0u;
        unsigned centre = trig ? tm_centre(r, track, bank, pattern, step) : part;
        unsigned value = tm_step_value(&s, k.length);
        if (tm_gate(value, k.density)) {
            r[0] = (uint8_t)tm_turing_note(centre, value, k.scale);
            r[3] = r[4] = r[5] = TM_CHORD_NONE;
            tm_written_centres[tm_index(c)][step] = (uint8_t)(centre + 1u);
            *note_bits |= bit;
            *lock_bits &= ~bit;
            conds[step] = 0;
            continue;
        }
        if (tm_written_centres[tm_index(c)][step] || (r[30] == 0x57u && r[31] < 128u)) {
            r[0] = r[3] = r[4] = r[5] = TM_LOCK_NONE;
            tm_written_centres[tm_index(c)][step] = 0;
        }
        unsigned others = 0;
        for (unsigned j = 0; j < 30u; ++j)
            others |= r[j] != TM_LOCK_NONE;
        if (*note_bits & bit) {
            *note_bits &= ~bit;
            if (others) {
                *lock_bits |= bit;
                conds[step] = (uint16_t)(conds[step] & 0x1fffu);
            }
        }
    }
    unsigned current = WORD(TM_BANK_PTR) == (uint32_t)banks;
    for (unsigned step = 0; step < length; ++step) {
        unsigned off = pattern * TM_SEQ_PATTERN_SIZE + track * TM_SEQ_TRACK_SIZE;
        if (current) {
            for (unsigned field = 0; field < 6u; ++field) {
                if (field == 1u || field == 2u)
                    continue;
                BYTE(0x1001614eu + off + TM_SEQ_LOCKS + step * 32u + field) = locks[step * 32u + field];
            }
            *(volatile uint16_t *)(0x1001614eu + off + TM_SEQ_CONDS + 2u * step) = conds[step];
        }
        if (current && pattern == BYTE(TM_UI_PATTERN)) {
            unsigned any = 0;
            for (unsigned field = 0; field < 32u; ++field)
                any |= locks[step * 32u + field] != TM_LOCK_NONE;
            volatile uint8_t *index = (volatile uint8_t *)(0x46c7d2e4u + step);
            if (any) *index |= (uint8_t)(1u << track);
            else *index &= (uint8_t)~(1u << track);
        }
    }
    if (current)
        for (unsigned w = TM_SEQ_NOTE_BITS; w < TM_SEQ_LOCK_BITS + 2u; ++w)
            WORD(0x1001614eu + 4u * (track * 556u + pattern * 9142u + w)) = bits[w];
    WORD((uint32_t)banks + 0x9b332u) = 1;
    WORD(0x100f8598u) = 1;
    ((void (*)(void))0x40027e00u)();
    return 1;
}

static const char tm_written[] = "MIDI TRACK WRITTEN";

/* ---- the settings a TURING page knob edits (TM_KNOB_*) -------------------- */

static unsigned tm_text(char *p, unsigned value) {
    char *start = p;
    if (value >= 100u)
        *p++ = (char)('0' + value / 100u);
    if (value >= 10u)
        *p++ = (char)('0' + value / 10u % 10u);
    *p++ = (char)('0' + value % 10u);
    *p = 0;
    return (unsigned)(p - start);
}

static unsigned tm_clamp(int32_t value, unsigned low, unsigned high) {
    return value < (int32_t)low ? low : value > (int32_t)high ? high : (unsigned)value;
}

/* The page edits the current pattern's cell of the track. */
static volatile TmCell *tm_ui_cell(unsigned t) {
    return tm_cell(*(volatile uint8_t *)TM_UI_BANK, *(volatile uint8_t *)TM_UI_PATTERN, t);
}

static void tm_ui_config(unsigned t, TmConfig *k) {
    tm_legacy_config(tm_ui_cell(t), k);
    const volatile uint8_t *part = tm_part(tm_ui_bank_index(), BYTE(TM_CUR_PART) & 3u);
    if (!tm_selected(part, t) || !tm_part_valid(part, t)) { k->on = 0; return; }
    k->lock = tm_setting(part, t, 0); k->length = tm_setting(part, t, 1);
    k->scale = tm_setting(part, t, 2); k->density = tm_setting(part, t, 3);
}
static unsigned tm_value(unsigned t, unsigned what) {
    TmConfig k;
    tm_ui_config(t, &k);
    return what == TM_KNOB_MODE
               ? k.on
               : what == TM_KNOB_LOCK
                     ? k.lock
                     : what == TM_KNOB_LENGTH ? k.length : what == TM_KNOB_SCALE ? k.scale : k.density;
}

static void tm_change(unsigned t, unsigned what, int32_t delta, int32_t toggle) {
    volatile TmCell *c = tm_ui_cell(t);
    TmConfig k;
    tm_ui_config(t, &k);
    if (what == TM_KNOB_MODE) { /* ON again picks the phrase up where the pattern is (tm_position) */
        k.on = toggle ? !k.on : tm_clamp((int32_t)k.on + delta, 0u, 1u);
        if (tm_live[t].cell == tm_index(c))
            tm_drop(t);
    } else if (what == TM_KNOB_LOCK)
        k.lock = tm_clamp((int32_t)k.lock + delta, 0u, 127u);
    else if (what == TM_KNOB_LENGTH)
        k.length = tm_clamp((int32_t)k.length + delta, TM_LENGTH_MIN, TM_LENGTH_MAX);
    else if (what == TM_KNOB_SCALE)
        k.scale = tm_clamp((int32_t)k.scale + delta, 0u, 127u);
    else
        k.density = tm_clamp((int32_t)k.density + delta, 0u, 127u);
    if (what == TM_KNOB_MODE)
        tm_set_config(c, &k);
    else {
        unsigned b = tm_ui_bank_index(), p = BYTE(TM_CUR_PART) & 3u;
        unsigned value = what == TM_KNOB_LOCK
                             ? k.lock
                             : what == TM_KNOB_LENGTH ? k.length : what == TM_KNOB_SCALE ? k.scale : k.density;
        tm_part_setting(b, p, t, what - 1u, value);
        ((void (*)(void))0x40027e00u)();
    }
}

/* ---- the TURING page (turing.h) ------------------------------------------
 * Knobs A..E are MODE (the track's Turing on/off), LOCK, LEN, SCAL (the
 * pitch range) and DENS (the share of note steps) of the current MIDI
 * track; F is off. Pushing A writes the sequence into the track (WRITE).
 * The stock renderer draws it from the copy: the widgets swap the ARP byte
 * the renderer read for the Turing value and call the stock widget, so the
 * drawing is stock's. The knob detour (hooks.s) sends the page's knobs here
 * instead of to the ARP bytes. */

static const char tm_page_title[] = "TURING";
static const char tm_page_names[TM_KNOBS][6] = {"MODE", "LOCK", "LEN", "SCAL", "DENS"};

static unsigned tm_track(void) {
    unsigned t = *(volatile uint8_t *)TM_UI_TRACK;
    return t < TM_TRACKS ? t : 0u;
}

static void tm_redraw(void) { ((void (*)(int))TM_REDRAW)(-1); }

/* Byte stores: the descriptor's longs sit at 2 mod 4. */
static void tm_put32(volatile uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v >> 24);
    p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);
    p[3] = (uint8_t)v;
}

static void tm_build(void) {
    const volatile uint8_t *arp = (const volatile uint8_t *)TM_ARP_DESC;
    uint8_t *d = tm_desc;
    for (unsigned i = 0; i < TM_DESC_SIZE; ++i)
        d[i] = arp[i];
    for (unsigned i = 0; i < 13u; ++i)
        d[0x09 + i] = i < sizeof(tm_page_title) ? (uint8_t)tm_page_title[i] : 0;
    for (unsigned slot = 0; slot < 6u; ++slot)
        for (unsigned i = 0; i < 6u; ++i)
            d[0x16 + 6u * slot + i] = slot < TM_KNOBS ? (uint8_t)tm_page_names[slot][i] : 0;
    static const uint32_t formats[TM_KNOBS] = {(uint32_t)tm_fmt_mode, (uint32_t)tm_fmt_number,
                                               (uint32_t)tm_fmt_number, (uint32_t)tm_fmt_number,
                                               (uint32_t)tm_fmt_number};
    static const uint32_t widgets[TM_KNOBS] = {(uint32_t)tm_wid_mode, (uint32_t)tm_wid_dial,
                                               (uint32_t)tm_wid_length, (uint32_t)tm_wid_dial,
                                               (uint32_t)tm_wid_dial};
    for (unsigned slot = 0; slot < 6u; ++slot) {
        tm_put32(d + 0xca + 4u * slot, slot < TM_KNOBS ? formats[slot] : 0u);
        tm_put32(d + 0xfa + 4u * slot, slot < TM_KNOBS ? widgets[slot] : 0u);
    }
    /* enable nibbles, slot 0 lowest: bit 0 the knob is live; F is off and
     * draws empty (ARP's are 1 1 1 1 1 1) */
    tm_put32(d + 0x18e, ((uint32_t)d[0x18e] << 24 & 0xff000000u) | 0x11111u);
    tm_ui.built = 1;
}

static unsigned tm_shown(void) {
    uint32_t window = WORD(TM_UI_WINDOW);
    if (window && WORD(window + 8u)) return 0;
    return tm_ui.page == 1u && *(volatile uint32_t *)TM_UI_MIDI &&
           *(volatile uint32_t *)TM_UI_PAGE == TM_PAGE_ARP && !WORD(0x460d173au) && !WORD(0x460d1694u) &&
           tm_selected(tm_part(tm_ui_bank_index(), BYTE(TM_CUR_PART) & 3u), tm_track());
}

/* A knob of the TURING page (the detour in 0x40055008): ticks as the panel
 * sends them, x7 with the encoder pushed as stock. MODE steps once in four
 * ticks, as ARP's LEG (measured under the port); LOCK, LEN, SCAL and DENS
 * once a tick, as ARP's 128-value TRAN. Release FUNC before editing.
 * Turning A while it is pushed is not a
 * WRITE. Nothing of the ARP page is written. */
void tm_knob(int32_t slot, int32_t ticks) {
    if (slot < 0 || slot >= (int32_t)TM_KNOBS)
        return;
    if (slot == (int32_t)TM_KNOB_MODE)
        tm_ui.armed = 0;
    if (*(volatile uint32_t *)(TM_UI_PUSH + (0x38u + (uint32_t)slot) * 24u))
        ticks *= 7;
    int32_t per = slot == (int32_t)TM_KNOB_MODE ? 4 : 1, acc = tm_ui.acc[slot];
    if ((acc < 0 && ticks > 0) || (acc > 0 && ticks < 0))
        acc = 0;
    acc += ticks;
    int32_t steps = acc / per;
    tm_ui.acc[slot] = acc - steps * per;
    if (!steps)
        return;
    tm_change(tm_track(), (unsigned)slot, steps, 0);
    tm_redraw();
}

/* An encoder push (0x4004ecfc(code, down), before stock sets its x7): knob
 * A pressed on the TURING page, FUNC up, with the track's MODE ON arms
 * WRITE; its release writes, if A was not turned meanwhile, and shows the
 * popup. Stock goes on as for any push. */
void tm_push(int32_t code, int32_t down) {
    if (code != (int32_t)TM_KEY_PUSH_A)
        return;
    if (down) {
        tm_ui.armed = (uint8_t)(down == 1 && tm_shown() && !*(volatile uint32_t *)TM_UI_FUNC &&
                                tm_value(tm_track(), TM_KNOB_MODE));
        return;
    }
    unsigned armed = tm_ui.armed;
    tm_ui.armed = 0;
    if (!armed || !tm_shown() || !tm_write_track(tm_track()))
        return;
    ++tm_ui.writes;
    ((TmPopup)TM_POPUP)(tm_written, TM_POPUP_TICKS);
    tm_redraw();
}

static uint8_t tm_scale_desc[0x194];
static const char tm_scale_names[3][4] = {"OFF", "MAJ", "MIN"};
static const char tm_roots[12][3] = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
static int tm_fmt_scale(char *buffer, int value) {
    const char *s = tm_scale_names[(unsigned)value < 3u ? value : 0];
    int n = 0;
    while ((buffer[n] = s[n]))
        ++n;
    return n;
}
static int tm_fmt_root(char *buffer, int value) {
    const char *s = tm_roots[(unsigned)value < 12u ? value : 0];
    int n = 0;
    while ((buffer[n] = s[n]))
        ++n;
    return n;
}
static void tm_wid_quant(int x, int y, int slot, int value, int flags, void *format, void *window) {
    (void)value;
    const volatile uint8_t *p = tm_part(tm_ui_bank_index(), BYTE(TM_CUR_PART) & 3u);
    ((TmWidget)TM_WIDGET_TEXT)(x, y, slot, (int)tm_setting(p, tm_track(), slot ? 5u : 4u), flags, format,
                               window);
}
static void tm_assign(unsigned t, unsigned on) {
    if (t >= TM_TRACKS)
        return;
    tm_drop(t);
    tm_ui.armed = 0;
    if (on) {
        TmConfig k = {0, TM_LOCK_DEFAULT, TM_LENGTH_DEFAULT, TM_SCALE_DEFAULT, TM_DENSITY_DEFAULT};
        unsigned b = tm_ui_bank_index(), p = BYTE(TM_CUR_PART) & 3u;
        tm_part_init(b, p, t, &k, 0);
        ((void (*)(void))0x40027e00u)();
    }
}
static uint32_t tm_generator_page(uint32_t stock, unsigned page, unsigned second) {
    if (page != TM_PAGE_ARP)
        return stock;
    if (!tm_ui.built) {
        tm_build();
        for (unsigned i = 0; i < TM_DESC_SIZE; ++i)
            tm_scale_desc[i] = tm_desc[i];
        for (unsigned slot = 0; slot < 6u; ++slot) {
            const char *name = slot == 0 ? "SCALE" : slot == 1 ? "ROOT" : "";
            unsigned n = 0;
            while (name[n])
                ++n;
            for (unsigned i = 0; i < 6u; ++i)
                tm_scale_desc[0x16 + 6u * slot + i] = i < n ? (uint8_t)name[i] : 0;
            tm_put32(tm_scale_desc + 0xca + 4u * slot,
                     slot == 0 ? (uint32_t)tm_fmt_scale : slot == 1 ? (uint32_t)tm_fmt_root : 0);
            tm_put32(tm_scale_desc + 0xfa + 4u * slot, slot < 2u ? (uint32_t)tm_wid_quant : 0);
        }
        tm_put32(tm_scale_desc + 0x18e, ((uint32_t)tm_scale_desc[0x18e] << 24) | 0x11u);
    }
    unsigned shown = second ? 2u : 1u;
    if (tm_ui.page != shown) {
        tm_ui.armed = 0;
        for (unsigned i = 0; i < TM_KNOBS; ++i)
            tm_ui.acc[i] = 0;
    }
    tm_ui.page = (uint8_t)shown;
    return (uint32_t)(second ? tm_scale_desc : tm_desc);
}
static void tm_generator_knob(unsigned page, unsigned index, int delta, unsigned second) {
    if (page != TM_PAGE_ARP)
        return;
    if (!second) {
        tm_knob((int32_t)index, delta);
        return;
    }
    if (index > 1u)
        return;
    unsigned b = tm_ui_bank_index(), p = BYTE(TM_CUR_PART) & 3u, t = tm_track();
    unsigned old = tm_setting(tm_part(b, p), t, index ? 5u : 4u);
    tm_part_setting(b, p, t, index ? 5u : 4u, tm_clamp((int32_t)old + delta, 0u, index ? 11u : 2u));
    ((void (*)(void))0x40027e00u)();
}
const struct modwerk_midi_generator tm_generator = {MODWERK_MIDI_GENERATOR_ABI, "TURING",  TM_GEN_ID,
                                                    (1u << TM_PAGE_ARP), tm_assign, tm_generator_page,
                                                    tm_generator_knob,          0,         tm_generator_tick};

/* Formatters, the stock signature fmt(buffer, value) -> length. */
int tm_fmt_mode(char *buffer, int value) {
    const char *name = tm_mode_names[value ? 1 : 0];
    int n = 0;
    while ((buffer[n] = name[n]))
        ++n;
    return n;
}

int tm_fmt_number(char *buffer, int value) { return (int)tm_text(buffer, (unsigned)value); }

/* Widgets, the stock signature widget(x, y, slot, value, flags, fmt, window). */
void tm_wid_mode(int x, int y, int slot, int value, int flags, void *format, void *window) {
    (void)value;
    ((TmWidget)TM_WIDGET_TEXT)(x, y, slot, (int)tm_value(tm_track(), TM_KNOB_MODE), flags, format, window);
}

/* LOCK, SCAL and DENS. The MIDI pages' renderer (0x4004e21a..) passes flags
 * 0, or 6 in the compact layout, and never the audio pages' "always show"
 * 8: these set it, so the dial keeps the number under it as the FM synth's
 * do. */
void tm_wid_dial(int x, int y, int slot, int value, int flags, void *format, void *window) {
    (void)value;
    if (!(flags & 2))
        flags |= 8;
    unsigned what = slot >= 0 && slot < (int)TM_KNOBS ? (unsigned)slot : TM_KNOB_LOCK;
    ((TmWidget)TM_WIDGET_DIAL)(x, y, slot, (int)tm_value(tm_track(), what), flags, format, window);
}

void tm_wid_length(int x, int y, int slot, int value, int flags, void *format, void *window) {
    (void)value;
    ((TmWidget)TM_WIDGET_TEXT)(x, y, slot, (int)tm_value(tm_track(), TM_KNOB_LENGTH), flags, format, window);
}

/* ---- project comments -------------------------------------------------
 * MODE and the 64-bit anchor remain per pattern, in stock-skipped comment
 * lines. S2 saves canonical placeholders for the old four settings fields:
 * the authoritative settings and generator choice live in the Part. Old
 * three/six/five/nine-number lines remain accepted for one-time migration.
 * S2 is saved even with every MODE off, so a later load never reassigns an
 * intentionally deselected Part from stale MODE lines. FIRST is ignored. */

static const char tm_line_key[] = "#TURING_T";
static const char tm_cell_key[] = "#TURING_B";
static const char tm_cell_format[] = "#TURING_B%d_P%d_T%d=%d,%d,%d,%d,%d\r\n";
static const char tm_cell_format_bits[] = "#TURING_B%d_P%d_T%d=%d,%d,%d,%d,%d,%d,%d,%d,%d\r\n";
static const char tm_first_key[] = "#TURING_FIRST=";

static void tm_project_reset(void) {
    tm_ui.armed = 0;
    TmSettings s;
    tm_defaults(&s);
    s.flags = TM_FLAG_CELLS10;
    tm_write(&s);
    tm_cells_clear();
    for (unsigned c = 0; c < CELL_COUNT; ++c)
        for (unsigned step = 0; step < TM_STEPS; ++step)
            tm_written_centres[c][step] = 0;
    for (unsigned t = 0; t < TM_TRACKS; ++t) tm_scheduled[t] = 0;
    tm_globals.cells = 1;
    for (unsigned t = 0; t < TM_TRACKS; ++t)
        tm_drop(t);
}

/* A storing load spans project text AND bank restoration. Its completion
 * detour runs just before the base's own project-end hook; UI ticks during
 * the load must never migrate a half-loaded project. */
unsigned tm_project_begin(void) {
    uint16_t sr = tm_task_lock();
    tm_project_loading = 1;
    tm_migration_ready = 0;
    unsigned generation = ++tm_load_generation;
    tm_project_reset();
    tm_task_unlock(sr);
    return generation;
}
void tm_project_defaults(void) {
    uint16_t sr = tm_task_lock();
    unsigned loading = tm_project_loading;
    tm_project_begin();
    tm_project_loading = loading; /* stock defaults can run inside a load */
    tm_task_unlock(sr);
}
void tm_project_loaded(int result) {
    uint16_t sr = tm_task_lock();
    tm_project_loading = 0; /* a failed load must not latch Turing inert */
    tm_install_read_done = result >= 0;
    tm_task_unlock(sr);
}

/* The decimal at *p (at most five digits), advancing past it; -1 when there
 * is none or it is too long. */
static int32_t tm_decimal(const char **p) {
    const char *s = *p;
    int32_t value = 0;
    unsigned digits = 0;
    while (*s >= '0' && *s <= '9' && digits < 5u)
        value = value * 10 + (*s++ - '0'), ++digits;
    if (!digits || (*s >= '0' && *s <= '9'))
        return -1;
    *p = s;
    return value;
}

static unsigned tm_prefix(const char *line, const char *key) {
    for (unsigned i = 0; key[i]; ++i)
        if (line[i] != key[i])
            return 0;
    return 1;
}

static unsigned tm_eol(const char *p) { return !*p || *p == '\r' || *p == '\n'; }

/* Up to `most` comma-separated decimals of at most 0xffff; how many, or -1. */
static int32_t tm_numbers(const char **p, int32_t *out, unsigned most) {
    unsigned n = 0;
    for (;;) {
        int32_t v = tm_decimal(p);
        if (v < 0 || n >= most)
            return -1;
        out[n++] = v;
        if (**p != ',')
            return (int32_t)n;
        ++*p;
    }
}

/* The numbers of a cell line -> k, the register (bits_n 0, 1 (OCTABAM9's 16
 * bits) or 4); nonzero when well formed and in range. */
static unsigned tm_parse_config(const int32_t *v, int32_t n, TmConfig *k, uint32_t *high, uint32_t *low,
                                unsigned *registered) {
    unsigned old = n == 3 || n == 6;
    if (!old && n != 5 && n != 9)
        return 0;
    k->on = (unsigned)v[0];
    k->lock = (unsigned)v[1];
    k->length = (unsigned)v[2];
    k->scale = old ? TM_SCALE_DEFAULT : (unsigned)v[3];
    k->density = old ? TM_DENSITY_OLD : (unsigned)v[4];
    if (k->on > 1u || k->lock > 127u || k->length < TM_LENGTH_MIN || k->length > TM_LENGTH_MAX ||
        k->scale > 127u || k->density > 127u)
        return 0;
    *registered = 0;
    *high = *low = 0;
    if (n == 6) {
        if (v[3] > 0xffff || v[4] > 0xffff || v[5] > 0xffff)
            return 0;
        *low = (uint32_t)v[3];
        *registered = (v[4] | v[5]) != 0; /* OCTABAM9 saved a register with its random state */
    } else if (n == 9) {
        for (unsigned i = 5; i < 9u; ++i)
            if (v[i] > 0xffff)
                return 0;
        *high = (uint32_t)v[5] << 16 | (uint32_t)v[6];
        *low = (uint32_t)v[7] << 16 | (uint32_t)v[8];
        *registered = 1;
    }
    return 1;
}

static void tm_apply_line(volatile TmCell *c, const TmConfig *k, uint32_t high, uint32_t low,
                          unsigned registered) {
    tm_set_config(c, k);
    c->high = high;
    c->low = low;
    c->length = (uint8_t)((c->length & 0x7fu) | (registered ? TM_CELL_SEEDED : 0u));
}

/* "#TURING_B<b>_P<p>_T<t>=..." */
static void tm_project_cell(const char *p, int32_t parse_only) {
    int32_t bank = tm_decimal(&p), pattern, track, v[9];
    if (bank < 1 || bank > (int32_t)TM_BANKS || *p++ != '_' || *p++ != 'P')
        return;
    if ((pattern = tm_decimal(&p)) < 1 || pattern > (int32_t)TM_PATTERNS || *p++ != '_' || *p++ != 'T')
        return;
    if ((track = tm_decimal(&p)) < 1 || track > (int32_t)TM_TRACKS || *p++ != '=')
        return;
    int32_t n = tm_numbers(&p, v, 9u);
    TmConfig k;
    uint32_t high, low;
    unsigned registered;
    if (n < 0 || !tm_eol(p) || !tm_parse_config(v, n, &k, &high, &low, &registered) || parse_only)
        return;
    tm_apply_line(tm_cell((uint32_t)bank - 1u, (uint32_t)pattern - 1u, (uint32_t)track - 1u), &k, high, low,
                  registered);
}

static void tm_project_centres(const char *p, int32_t parse_only) {
    int32_t b = tm_decimal(&p), q, t;
    if (b < 1 || b > (int32_t)TM_BANKS || *p++ != '_' || *p++ != 'P') return;
    q = tm_decimal(&p);
    if (q < 1 || q > (int32_t)TM_PATTERNS || *p++ != '_' || *p++ != 'T') return;
    t = tm_decimal(&p);
    if (t < 1 || t > (int32_t)TM_TRACKS || *p++ != '=') return;
    uint8_t values[TM_STEPS];
    for (unsigned i = 0; i < TM_STEPS; ++i) {
        unsigned value = 0;
        for (unsigned j = 0; j < 2u; ++j) {
            unsigned digit = (unsigned char)*p++;
            if (digit >= '0' && digit <= '9') digit -= '0';
            else if (digit >= 'a' && digit <= 'f') digit -= 'a' - 10u;
            else return;
            value = value * 16u + digit;
        }
        if (value > 128u) return;
        values[i] = (uint8_t)value;
    }
    if (!tm_eol(p) || parse_only) return;
    unsigned index = (((unsigned)b - 1u) * TM_PATTERNS + (unsigned)q - 1u) * TM_TRACKS + (unsigned)t - 1u;
    for (unsigned i = 0; i < TM_STEPS; ++i) tm_written_centres[index][i] = values[i];
}
void tm_project_line(const char *line, int32_t parse_only) {
    if (tm_prefix(line, "#TURING_WB")) {
        tm_project_centres(line + 10, parse_only);
        return;
    }
    if (tm_prefix(line, "#TURING_S2=1") && tm_eol(line + 12)) {
        if (!parse_only) {
            TmSettings s;
            tm_read(&s);
            s.flags |= TM_FLAG_S2;
            tm_write(&s);
        }
        return;
    }
    if (tm_prefix(line, tm_first_key)) {
        /* Legacy page-ring preference has no meaning with generator pages. */
        return;
    }
    if (tm_prefix(line, tm_cell_key)) {
        tm_project_cell(line + sizeof(tm_cell_key) - 1u, parse_only);
        return;
    }
    if (!tm_prefix(line, tm_line_key))
        return;
    const char *p = line + sizeof(tm_line_key) - 1u;
    int32_t track = tm_decimal(&p), v[9];
    if (track < 1 || track > (int32_t)TM_TRACKS || *p++ != '=')
        return;
    int32_t n = tm_numbers(&p, v, 9u);
    TmConfig k;
    uint32_t high, low;
    unsigned registered;
    if (n != 3 || !tm_eol(p) || !tm_parse_config(v, n, &k, &high, &low, &registered) || parse_only)
        return;
    for (unsigned b = 0; b < TM_BANKS; ++b)
        for (unsigned q = 0; q < TM_PATTERNS; ++q)
            tm_apply_line(tm_cell(b, q, (uint32_t)track - 1u), &k, 0, 0, 0);
}

void tm_project_write(TmFormat format, TmLength length, TmWrite write, char *buffer, int file) {
    TmSettings settings;
    tm_read(&settings);
    unsigned s2 = settings.flags & TM_FLAG_S2;
    if (s2) {
        format(buffer, "#TURING_S2=1\r\n");
        write(file, buffer, length(buffer));
    }
    for (unsigned b = 0; b < TM_BANKS; ++b)
        for (unsigned q = 0; q < TM_PATTERNS; ++q)
            for (unsigned t = 0; t < TM_TRACKS; ++t) {
                const volatile TmCell *c = tm_cell(b, q, t);
                TmConfig k;
                tm_legacy_config(c, &k);
                if (s2) {
                    k.lock = TM_LOCK_DEFAULT;
                    k.length = TM_LENGTH_DEFAULT;
                    k.scale = TM_SCALE_DEFAULT;
                    k.density = TM_DENSITY_DEFAULT;
                }
                const uint8_t *centres = tm_written_centres[tm_index(c)];
                unsigned written = 0;
                for (unsigned i = 0; i < TM_STEPS; ++i) written |= centres[i];
                if (written) {
                    static char centre_line[160];
                    static const char hex[] = "0123456789abcdef";
                    format(centre_line, "#TURING_WB%d_P%d_T%d=", (int)(b+1u), (int)(q+1u), (int)(t+1u));
                    unsigned at = (unsigned)length(centre_line);
                    for (unsigned i = 0; i < TM_STEPS; ++i) {
                        centre_line[at++] = hex[centres[i] >> 4];
                        centre_line[at++] = hex[centres[i] & 15u];
                    }
                    centre_line[at++] = '\r'; centre_line[at++] = '\n'; centre_line[at] = 0;
                    write(file, centre_line, (int)at);
                }
                if (!k.on && !tm_seeded(c) && k.lock == TM_LOCK_DEFAULT && k.length == TM_LENGTH_DEFAULT &&
                    k.scale == TM_SCALE_DEFAULT && k.density == TM_DENSITY_DEFAULT)
                    continue;
                if (tm_seeded(c))
                    format(buffer, tm_cell_format_bits, (int)(b + 1u), (int)(q + 1u), (int)(t + 1u), (int)k.on,
                           (int)k.lock, (int)k.length, (int)k.scale, (int)k.density, (int)(c->high >> 16),
                           (int)(c->high & 0xffffu), (int)(c->low >> 16), (int)(c->low & 0xffffu));
                else
                    format(buffer, tm_cell_format, (int)(b + 1u), (int)(q + 1u), (int)(t + 1u), (int)k.on,
                           (int)k.lock, (int)k.length, (int)k.scale, (int)k.density);
                write(file, buffer, length(buffer));
            }
}

/* The base restores packages after stock has loaded the project. On the
 * existing engine-task ready event, import saved comments once per install.
 * Normal loads still use the existing stock project callbacks above.
 * The file's I/O buffer belongs to stock until close; parse a separate block.
 */
unsigned tm_modules_ready(void) {
    ++tm_ready_events;
    if (tm_install_read_done || tm_project_loading)
        return 0;
    uint32_t directory = ((uint32_t (*)(int,int))0x40025230u)(0,0);
    if (!directory)
        return 0;
    static char path[260];
    const char *dir = (const char *)directory;
    unsigned n = 0;
    while (dir[n] && n < sizeof(path) - sizeof("/project.work")) {
        path[n] = dir[n];
        ++n;
    }
    if (dir[n])
        return 0;
    const char suffix[] = "/project.work";
    for (unsigned i = 0; i < sizeof(suffix); ++i)
        path[n+i] = suffix[i];
    static uint32_t file[6];
    static uint8_t io[4096];
    int opened = ((int (*)(void *,const char *,const char *,void *,unsigned))0x40016864u)
        (file,path,"r",io,sizeof(io));
    if (opened < 0)
        return 0;
    unsigned generation = tm_project_begin();
    static char block[512], line[160];
    unsigned used = 0, overflow = 0;
    int more;
    do {
        for (unsigned i = 0; i < sizeof(block); ++i)
            block[i] = 0;
        more = ((int (*)(void *,void *,unsigned))0x40016564u)(file,block,sizeof(block));
        if (generation != tm_load_generation) break;
        for (unsigned i = 0; i < sizeof(block) && block[i]; ++i) {
            char c = block[i];
            if (c == '\r' || c == '\n') {
                line[used] = 0;
                if (!overflow && used) {
                    uint16_t sr = tm_task_lock();
                    if (generation == tm_load_generation) tm_project_line(line,0);
                    tm_task_unlock(sr);
                }
                used = overflow = 0;
            } else if (used + 1u < sizeof(line)) {
                line[used++] = c;
            } else {
                overflow = 1;
            }
        }
    } while (more == 1 && generation == tm_load_generation);
    if (!overflow && used) {
        line[used] = 0;
        uint16_t sr = tm_task_lock();
        if (generation == tm_load_generation) tm_project_line(line,0);
        tm_task_unlock(sr);
    }
    ((int (*)(void *))0x4001677cu)(file);
    uint16_t sr = tm_task_lock();
    if (generation == tm_load_generation) tm_project_loaded(more < 0 ? -1 : 0);
    tm_task_unlock(sr);
    return 0;
}
