/* Turing machine engine. No floating point, allocation, runtime library
 * calls or clock of its own: the register advances only when the stock
 * sequencer fires a trig on the selected MIDI track. Compile to the
 * checked-in ColdFire assembly with generate.py. */
#include "turing.h"

_Static_assert(sizeof(TmState) == 8, "hooks.s state allocation");

#define NV(address) (*(volatile uint8_t *)(address))

const char tm_label_track[] = "TURING TRACK";
const char tm_label_lock[] = "TURING LOCK";

static const char tm_track_names[TM_TRACKS + 1][4] = {
    "OFF", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"
};
static char tm_lock_text[4];

static uint32_t tm_random(uint32_t *state) {
    uint32_t x = *state;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    *state = x;
    return x;
}

static unsigned tm_valid(void) {
    unsigned track = NV(TM_NV_TRACK), lock = NV(TM_NV_LOCK);
    return track <= TM_TRACKS && lock <= 127u
        && NV(TM_NV_CHECK) == ((track ^ lock ^ TM_CHECK_SALT) & 0xffu);
}

unsigned tm_track(void) { return tm_valid() ? NV(TM_NV_TRACK) : 0; }

unsigned tm_lock(void) { return tm_valid() ? NV(TM_NV_LOCK) : TM_LOCK_DEFAULT; }

static void tm_store(unsigned track, unsigned lock) {
    NV(TM_NV_TRACK) = (uint8_t)track;
    NV(TM_NV_LOCK) = (uint8_t)lock;
    NV(TM_NV_CHECK) = (uint8_t)(track ^ lock ^ TM_CHECK_SALT);
}

/* One clock of a TM_LENGTH-bit loop: the bit leaving the top returns at the
 * bottom, inverted with a chance set by LOCK. 127 never flips (a locked
 * phrase), 64 flips about half the time (random), 0 always flips (a locked
 * phrase twice as long, second half inverted). Returns the low eight bits. */
unsigned tm_step(TmState *s, unsigned lock, unsigned track) {
    if (!s->seeded) {
        s->rng = 0x6d2b79f5u ^ (0x9e3779b9u * (track + 1u));
        s->bits = (uint16_t)tm_random(&s->rng);
        s->seeded = 1;
    }
    unsigned out = (s->bits >> (TM_LENGTH - 1u)) & 1u;
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
    if (track >= TM_TRACKS || tm_track() != track + 1u || notes[0] < 0) return;
    unsigned offset = tm_step(&tm_states[track], tm_lock(), track) * TM_SPAN / 255u;
    for (unsigned i = 0; i < 4u; ++i) {
        int note = notes[i];
        if (note < 0) continue;
        note += (int)offset;
        notes[i] = (int8_t)(note > 127 ? -1 : note);
    }
}

/* MIDI SEQUENCER rows, called by the stock page: a getter returns the value
 * text, a setter takes (delta, toggle). */
uint32_t tm_get_track(void) { return (uint32_t)tm_track_names[tm_track()]; }

uint32_t tm_get_lock(void) {
    unsigned lock = tm_lock();
    char *p = tm_lock_text;
    if (lock >= 100u) *p++ = (char)('0' + lock / 100u);
    if (lock >= 10u) *p++ = (char)('0' + lock / 10u % 10u);
    *p++ = (char)('0' + lock % 10u);
    *p = 0;
    return (uint32_t)tm_lock_text;
}

static unsigned tm_clamp(int32_t value, unsigned top) {
    return value < 0 ? 0u : value > (int32_t)top ? top : (unsigned)value;
}

void tm_set_track(int32_t delta, int32_t toggle) {
    (void)toggle;
    tm_store(tm_clamp((int32_t)tm_track() + delta, TM_TRACKS), tm_lock());
}

void tm_set_lock(int32_t delta, int32_t toggle) {
    (void)toggle;
    tm_store(tm_track(), tm_clamp((int32_t)tm_lock() + delta, 127u));
}
