/* Turing machine for Octatrack MIDI tracks: the integer engine behind the
 * per-step hook at 0x4009cf4c (REPLACE mode), the chord hook at 0x4009fa2a,
 * the TURING page (and its WRITE, 0x4004ecfc) and the TURING FIRST row. */
#ifndef TURING_MACHINE_H
#define TURING_MACHINE_H
#include <stdint.h>

#define TM_TRACKS 8u
#define TM_BANKS 16u
#define TM_PATTERNS 16u
#define TM_STEPS 64u
#define TM_LOCK_DEFAULT 64u
#define TM_LENGTH_DEFAULT 16u
#define TM_LENGTH_MIN 2u
#define TM_LENGTH_MAX 64u           /* the register holds 64 steps, the longest pattern */
#define TM_NOTE_LOOP_MAX 7u         /* LEN 2..7: the loop holds LEN whole notes (a byte each) and turns a note a step */
#define TM_SCALE_DEFAULT 64u        /* SCAL: the pitch range (tm_span) */
#define TM_DENSITY_DEFAULT 64u      /* DENS: how many steps are notes (tm_gate) */
#define TM_DENSITY_OLD 127u         /* what an OCTABAM9 setting gets: a note every step, as it played */

/* Settings: battery-backed RAM that stock never references
 * (0x100f859c..0x100fff00, zeroed by the cold initialise; Playmodes uses
 * 0x100f8600..0x100f8f06). A record that fails its magic, version, ranges
 * or checksum reads as the defaults. Since OCTABAM9 only its flags are
 * used (TURING FIRST, and since OCTABAM10 the cells' layout); its per-track
 * fields keep the version-1 layout and defaults but no longer decide
 * anything: the settings are per pattern (TmCell below). */
#define TM_NV_SETTINGS 0x100ffe00u
#define TM_NV_MAGIC 0x544du         /* "TM" */
#define TM_NV_VERSION 1u
#define TM_FLAG_FIRST 1u            /* a version-1 record from before it has 0 here: OFF */
#define TM_FLAG_CELLS10 2u          /* the cells are in OCTABAM10's layout (else OCTABAM9's, converted once) */
typedef struct {
    uint16_t magic;
    uint8_t version;
    uint8_t enabled;                /* bit t = track t+1 on */
    uint8_t lock[TM_TRACKS];
    uint8_t length[TM_TRACKS];
    uint8_t flags;                  /* TM_FLAG_FIRST: AMP shows TURING first (project-wide) */
    uint8_t reserved[10];
    uint8_t check;                  /* 0x5a ^ every byte before it */
} TmSettings;

/* Per pattern: one cell for each track of each of the 256 patterns (16
 * banks x 16), in the same unreferenced battery RAM, so a power cycle keeps
 * them, registers included. The register a cell holds is the one the
 * pattern's pass starts from (its first step); the register as it plays
 * lives in DRAM (TmLive), so a STOP, a SAVE while playing and a power cycle
 * all come back to the start of the pass. A zeroed cell is the defaults (OFF, LOCK 64,
 * LEN 16, SCAL 64, DENS 64, register not yet seeded): the cold initialise,
 * a new project and a storing load give every pattern stock playback. A
 * cell whose fields are out of range reads as the defaults. OCTABAM9's
 * cells (the same 12 bytes: cfg, LEN ^ 16, seeded, 0, a 16-bit register, 0,
 * its random state) are converted once, keeping MODE, LOCK, LEN and the
 * register, with SCAL 64 and DENS 127. */
#define TM_NV_CELLS 0x100f9000u     /* .. 0x100ff000 */
#define TM_CELL_ON 0x80u
#define TM_CELL_SEEDED 0x80u
typedef struct {
    uint8_t cfg;                    /* bit 7 MODE ON; bits 6..0 LOCK ^ 64 */
    uint8_t length;                 /* bit 7 the register is seeded; bits 6..0 LEN ^ 16 */
    uint8_t scale;                  /* SCAL ^ 64 */
    uint8_t density;                /* DENS ^ 64 */
    uint32_t high, low;             /* the register: bit 0 of low the newest */
} TmCell;

/* The flip decisions' random state, one per track (not per pattern: the
 * Turing machine's noise is not part of a pattern), in the same battery RAM.
 * Zero is unseeded: the boot seed and the track seed it at its first step. */
#define TM_NV_RANDOM 0x100ffe40u    /* 8 x uint32 */

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

/* REPLACE mode: the stock MIDI per-step trig evaluator 0x4009cf4c(track,
 * bank, pattern, step, slot) and what it reads and writes (read from its
 * code). Pattern data: */
#define TM_SEQ_BANKS 0x400e21e0u        /* bank 0's pattern data */
#define TM_SEQ_BANK_SIZE 635712u
#define TM_SEQ_PATTERN_SIZE 36568u
#define TM_SEQ_LENGTH 0x8e53u           /* in a pattern: its length, 1..64 (measured under the port) */
#define TM_SEQ_SCALE 0x8e54u            /* ... its scale index, then nonzero = per-track scales */
#define TM_SEQ_TRACK_SIZE 2224u         /* a MIDI track in a pattern */
#define TM_SEQ_TRACK_LENGTH 0x48f8u     /* in a pattern, + track * TM_SEQ_TRACK_SIZE: the track's length (per-track scales) */
#define TM_SEQ_TRACK_SCALE 0x48f9u      /* ... the track's scale index */
#define TM_SEQ_SWING 0x48fau            /* ... the track's swing amount */
#define TM_SEQ_LOCKS 0x4900u            /* ... its 64 lock records, 32 bytes a step (0xff = no lock) */
#define TM_SEQ_CONDS 0x5100u            /* ... its 64 step words: repeats << 13 | microtiming << 7 | condition */
/* Trig bitmaps, long indexes into the bank: + track * 556 + pattern * 9142,
 * + 1 for steps 0..31, + 0 for 32..63; bit step & 31. */
#define TM_SEQ_NOTE_BITS 4660u          /* note trigs */
#define TM_SEQ_LOCK_BITS 4662u          /* trigless trigs (FUNC+TRIG): their locks, no note */
#define TM_SEQ_SWING_BITS 4666u         /* swing */
#define TM_SEQ_SPEEDS 0x400aba50u       /* per scale index, 4 bytes: byte 3 the speed factor */
#define TM_SEQ_REPEAT_TICKS 0x400abaa4u /* per repeat count: the interval, times the speed factor */
/* Its per-track outputs, which the step scheduler copies into the slot it plays: */
#define TM_EV_EVENT 0x46c7a810u         /* 0 nothing, 29 a note trig, 25 a trigless trig, 1 other */
#define TM_EV_REPEATS 0x46c7a14cu       /* notes per trig */
#define TM_EV_TIMING 0x46c7a830u        /* microtiming plus swing */
#define TM_EV_INTERVAL 0x46c77bfau      /* between repeats */
#define TM_EV_RECORDS 0x46c78960u       /* lock records, 256 bytes a slot, 32 a track; -1 = no lock */
#define TM_EV_RECORD_FIRST 0x46c7a6f0u  /* the record for slot -1 (the first step, evaluated while stopped) */
#define TM_EV_NOTE_TRIG 29u
#define TM_EV_LOCK_TRIG 25u
/* The stock trig conditions' last results, one byte per track (0..7 audio,
 * 8..15 MIDI; 0 = true, 1 = false): NEI on a track reads its neighbour's
 * (0x400a5164). */
#define TM_COND_RESULTS 0x46107979u
/* The pattern's Part, and the Parts' MIDI track blocks in the bank (byte 0
 * NOTE; the step scheduler and the tick ISR read them so). A lock record's
 * byte i replaces the track's resolved byte i (i < 30, the tick ISR's
 * loop): 0 NOTE, 1 VEL, 2 LEN, 3..5 NOT2..NOT4 (0x40: the NOTE itself,
 * which the note routine plays once), ...; bytes 30 and 31 are copied with
 * the record and never read by stock (in the pattern they are 0xff). */
#define TM_SEQ_PART 0x8e57u
#define TM_PART_TRACKS 0x8f162u
#define TM_PART_SIZE 6322u
#define TM_LOCK_NONE 0xffu
#define TM_CHORD_NONE 0x40u
#define TM_TAG 0x54u                /* "T" in a record's byte 30: a Turing note; byte 31 its step */
#define TM_WRITTEN 0x57u            /* "W" in a pattern record's byte 30: WRITE put this NOTE lock; byte 31 the centre */
/* The record of the step the tick ISR fired last, per track (copied there
 * from the slot as it fires; the note routine runs after it). */
#define TM_EV_FIRED 0x46c7a000u
/* What the first-step evaluation (slot -1) leaves for PLAY, per track
 * (measured under the port: the timing is the evaluator's, unchanged): */
#define TM_FIRST_EVENT 0x46c779f2u
#define TM_FIRST_REPEATS 0x46c77bc2u
#define TM_FIRST_INTERVAL 0x46c79fdeu
#define TM_FIRST_TIMING 0x46c7a936u

typedef struct {
    int32_t event, repeats, timing, interval;
} TmEvent;

/* The last first-step evaluation of a track: the stock result, and the
 * arguments that give the Turing one. */
typedef struct {
    TmEvent stock;
    uint8_t locks[32];              /* stock's lock record */
    uint32_t bank, pattern;
    uint8_t step;
    uint8_t mode;                   /* unused since OCTABAM9 */
    uint8_t valid;                  /* evaluated since the last PLAY */
    uint8_t reserved;
} TmFirst;

/* A register being clocked: the cell's 64 bits and the track's random state. */
typedef struct {
    uint32_t high, low;
    uint32_t rng;
    uint8_t seeded;
    uint8_t reserved[3];
} TmState;

/* The register a track is playing: it clocks when a step is scheduled, a
 * step or so before it plays (measured: step N is scheduled just after step
 * N-1 fires). At the pass's first step (step 0) it is written to the cell
 * (the anchor). A step that does not follow on (PLAY, a MODE switched ON, a
 * pattern change, a load) starts from the cell's register clocked to it as a
 * locked loop, so a locked phrase always sits the same way on the pattern.
 * STOP drops it. */
typedef struct {
    uint32_t high, low;
    uint16_t cell;                  /* index into TM_NV_CELLS */
    uint8_t next;                   /* the step that follows on */
    uint8_t valid;
} TmLive;

typedef struct {
    uint32_t seed;
    uint8_t seeded;
    uint8_t cells;                  /* the cells' layout was checked this boot (tm_cells_ready) */
    uint8_t playing;                /* PLAY since the last first-step evaluation (WRITE starts at the step that plays next) */
    uint8_t reserved;
} TmGlobals;

#define TM_UI_BANK 0x800065bdu     /* byte: the playing (current) bank, 0..15 */
#define TM_UI_PATTERN 0x800065beu  /* byte: the playing (current) pattern, 0..15 */

/* The project file's stock text writer, as the serializer 0x40088288 holds it
 * in a4, a3 and a2: format into a buffer, measure it, write it to the file. */
typedef int (*TmFormat)(char *buffer, const char *format, ...);
typedef int (*TmLength)(const char *text);
typedef int (*TmWrite)(int file, const char *buffer, int length);

/* The TURING page: on a MIDI track, AMP's pages are ARP, ARP SETUP and
 * TURING in a ring. A double tap of AMP shows the next one, a single press
 * the first: ARP, or TURING when TURING FIRST is ON. TURING shows in place
 * of MIDI ARPEGGIATOR; it is a runtime copy of the stock ARP descriptor with
 * its names, formatters, widgets and enable nibbles replaced. Storage fields
 * (defaults, minimums, counts) stay ARP's. Stock UI state it reads: */
#define TM_UI_TRACK 0x80000000u     /* byte: the current track of the current mode */
#define TM_UI_MIDI 0x80000012u      /* long: nonzero in MIDI mode */
#define TM_UI_PAGE 0x460d1684u      /* long: the current page kind; 2 = AMP (ARP) */
#define TM_UI_WINDOW 0x400bcd14u    /* pointer: +8 nonzero while a window (a SETUP) shows */
#define TM_UI_FUNC 0x46c7dd26u      /* long: FUNC held */
#define TM_UI_PUSH 0x46c7d8eeu      /* key records, 24 bytes each: + (0x38 + slot) * 24 nonzero = encoder pushed */
#define TM_UI_LAST_KEY 0x400c0aacu  /* long: the page key a press within 15 ticks makes a double tap of */
#define TM_SETUP_WINDOW 0x400cfeb6u /* the MIDI ARP SETUP window, as TM_UI_WINDOW holds it */
#define TM_SETUP_OPENED 0x40079c90u /* the return address of its opener's call to the page setter */
#define TM_KEY_AMP 0x23u
#define TM_KEY_PUSH_A 0x38u         /* encoder A pushed: 0x4004ecfc(code, 1) on the press, (code, 0) on the release */
#define TM_PAGE_ARP 2u
#define TM_ARP_DESC 0x400d3fd0u     /* the stock MIDI ARPEGGIATOR descriptor */
#define TM_DESC_SIZE 0x192u
#define TM_REDRAW 0x4004d948u       /* redraw(-1): what the stock page and knob paths call */
#define TM_WIDGET_TEXT 0x400467a4u  /* the stock widgets: ARP MODE's text and the dial */
#define TM_WIDGET_DIAL 0x400479b4u
#define TM_POPUP 0x4005a2b8u        /* popup(text, ticks): the message COPY MIDI TRACK shows (0x4005f450) */
#define TM_POPUP_TICKS 0x30u

/* AMP's pages in ring order; a double tap goes from one to the next. */
#define TM_VIEW_ARP 0u
#define TM_VIEW_SETUP 1u
#define TM_VIEW_TURING 2u
#define TM_VIEWS 3u

/* The page's knobs (A..E); F is off. */
#define TM_KNOB_MODE 0u
#define TM_KNOB_LOCK 1u
#define TM_KNOB_LENGTH 2u
#define TM_KNOB_SCALE 3u
#define TM_KNOB_DENSITY 4u
#define TM_KNOBS 5u

typedef struct {
    uint8_t page;                   /* the TURING page shows in place of ARP */
    uint8_t view;                   /* the page showing before the last press: a double tap goes on from it */
    uint8_t built;                  /* tm_desc holds the copy */
    uint8_t armed;                  /* knob A pushed on the TURING page, not turned: its release WRITEs */
    int32_t acc[TM_KNOBS];          /* knob ticks not yet a step, per slot */
    uint32_t writes;                /* WRITEs done (tests read it) */
} TmUi;

typedef void (*TmWidget)(int x, int y, int slot, int value, int flags, void *format, void *window);
typedef void (*TmPopup)(const char *text, int ticks);

extern TmGlobals tm_globals;
extern TmUi tm_ui;
extern uint8_t tm_desc[];

uint32_t tm_mix(uint32_t x);
uint32_t tm_boot_seed(void);
unsigned tm_flip_chance(unsigned lock, unsigned length);
unsigned tm_span(unsigned scale);
unsigned tm_gate(uint32_t value, unsigned density);
unsigned tm_step(TmState *s, unsigned lock, unsigned length, unsigned track, unsigned salt);
int tm_turing_note(unsigned centre, unsigned value, unsigned scale);
int32_t tm_eval(uint32_t track, uint32_t bank, uint32_t pattern, uint32_t step, int32_t slot);
void tm_stock_eval(uint32_t track, uint32_t bank, uint32_t pattern, uint32_t step, int32_t slot);
void tm_play(void);
extern TmFirst tm_first_steps[TM_TRACKS];
extern TmLive tm_live[TM_TRACKS];
int32_t tm_fired(uint32_t track, uint32_t tag);
uint32_t tm_get_first(void);
void tm_set_first(int32_t delta, int32_t toggle);
void tm_project_defaults(void);
void tm_project_line(const char *line, int32_t parse_only);
void tm_project_write(TmFormat format, TmLength length, TmWrite write, char *buffer, int file);
uint32_t tm_resolve(uint32_t track);
int32_t tm_page_key(int32_t code, int32_t arg);
void tm_page_reset(int32_t kind, uint32_t caller);
void tm_knob(int32_t slot, int32_t ticks);
void tm_push(int32_t code, int32_t down);
unsigned tm_write_track(unsigned track);
int tm_fmt_mode(char *buffer, int value);
int tm_fmt_number(char *buffer, int value);
void tm_wid_mode(int x, int y, int slot, int value, int flags, void *format, void *window);
void tm_wid_dial(int x, int y, int slot, int value, int flags, void *format, void *window);
void tm_wid_length(int x, int y, int slot, int value, int flags, void *format, void *window);
#endif
