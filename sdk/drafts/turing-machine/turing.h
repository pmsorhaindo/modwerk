/* Turing machine for Octatrack MIDI tracks: the integer engine behind the
 * note hook at 0x4009fb2e and the MIDI SEQUENCER rows. */
#ifndef TURING_MACHINE_H
#define TURING_MACHINE_H
#include <stdint.h>

#define TM_TRACKS 8u
#define TM_SPAN 24u
#define TM_LOCK_DEFAULT 64u
#define TM_LENGTH_DEFAULT 16u
#define TM_LENGTH_MIN 2u
#define TM_LENGTH_MAX 16u

/* Settings: battery-backed RAM that stock never references
 * (0x100f859c..0x100fff00, zeroed by the cold initialise; Playmodes uses
 * 0x100f8600..0x100f8f06). A record that fails its magic, version, ranges
 * or checksum reads as the defaults, every track OFF. */
#define TM_NV_SETTINGS 0x100ffe00u
#define TM_NV_MAGIC 0x544du         /* "TM" */
#define TM_NV_VERSION 1u
typedef struct {
    uint16_t magic;
    uint8_t version;
    uint8_t enabled;                /* bit t = track t+1 on */
    uint8_t lock[TM_TRACKS];
    uint8_t length[TM_TRACKS];
    uint8_t reserved[11];
    uint8_t check;                  /* 0x5a ^ every byte before it */
} TmSettings;

/* A fixed seed for tests, written through the emulator: when this record is
 * valid the boot seed is its value instead of the timer. */
#define TM_NV_TEST_SEED 0x100ffe20u
#define TM_TEST_MAGIC 0x54534545u   /* "TSEE" */
typedef struct {
    uint32_t magic;
    uint32_t seed;
    uint32_t check;                 /* ~seed */
} TmTestSeed;

/* The free-running 32-bit count of DMA timer 3 (bus clock, reference
 * 0xffffffff, as stock programs it) and the sequencer clock Euclid reads. */
#define TM_TIMER_COUNT 0xfc07c00cu
#define TM_SEQ_CLOCK 0x4610757cu

typedef struct {
    uint32_t rng;
    uint16_t bits;
    uint8_t seeded;
    uint8_t reserved;
} TmState;

typedef struct {
    uint32_t seed;
    uint8_t seeded;
    uint8_t edit;                   /* the track the rows edit, 0..7 */
    uint16_t reserved;
} TmGlobals;

/* The project file's stock text writer, as the serializer 0x40088288 holds it
 * in a4, a3 and a2: format into a buffer, measure it, write it to the file. */
typedef int (*TmFormat)(char *buffer, const char *format, ...);
typedef int (*TmLength)(const char *text);
typedef int (*TmWrite)(int file, const char *buffer, int length);

extern TmState tm_states[TM_TRACKS];
extern TmGlobals tm_globals;

uint32_t tm_mix(uint32_t x);
uint32_t tm_boot_seed(void);
unsigned tm_step(TmState *s, unsigned lock, unsigned length, unsigned track);
void tm_note(unsigned track, int8_t *notes);
uint32_t tm_get_edit(void);
uint32_t tm_get_mode(void);
uint32_t tm_get_lock(void);
uint32_t tm_get_length(void);
void tm_set_edit(int32_t delta, int32_t toggle);
void tm_set_mode(int32_t delta, int32_t toggle);
void tm_set_lock(int32_t delta, int32_t toggle);
void tm_set_length(int32_t delta, int32_t toggle);
void tm_project_defaults(void);
void tm_project_line(const char *line, int32_t parse_only);
void tm_project_write(TmFormat format, TmLength length, TmWrite write, char *buffer, int file);
#endif
