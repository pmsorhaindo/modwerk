/* Turing machine for Octatrack MIDI tracks: the integer engine behind the
 * note hook at 0x4009fb2e and the two MIDI SEQUENCER rows. */
#ifndef TURING_MACHINE_H
#define TURING_MACHINE_H
#include <stdint.h>

/* Settings in battery-backed RAM, the padding between the settings block and
 * the project record (0x100b14e2..0x100b14ef, unreferenced by stock; Scale
 * Quantizer uses 0x100b14ec..ee). The check byte makes bytes left by other
 * firmware read as OFF. */
#define TM_NV_TRACK 0x100b14e8u
#define TM_NV_LOCK 0x100b14e9u
#define TM_NV_CHECK 0x100b14eau
#define TM_CHECK_SALT 0x5au
#define TM_LOCK_DEFAULT 64u
#define TM_TRACKS 8u
#define TM_LENGTH 16u
#define TM_SPAN 24u

typedef struct {
    uint32_t rng;
    uint16_t bits;
    uint8_t seeded;
    uint8_t reserved;
} TmState;

extern TmState tm_states[TM_TRACKS];

unsigned tm_track(void);
unsigned tm_lock(void);
unsigned tm_step(TmState *s, unsigned lock, unsigned track);
void tm_note(unsigned track, int8_t *notes);
uint32_t tm_get_track(void);
uint32_t tm_get_lock(void);
void tm_set_track(int32_t delta, int32_t toggle);
void tm_set_lock(int32_t delta, int32_t toggle);
#endif
