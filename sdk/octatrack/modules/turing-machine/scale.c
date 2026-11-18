/* SPDX-License-Identifier: MIT
 * Turing's saved SCALE values stay 0 OFF, 1 MAJ, 2 natural MIN.
 * The SDK catalogue uses 1 for major and 6 for natural minor.
 * After TRAN, these scales snap down one semitone. At note zero the SDK
 * searches upward inside MIDI range; preserve Turing's historical drop.
 */
#include "../../../machines/octatrack/include/modwerk_scale.h"
int tm_scale_snap(int note, unsigned scale, unsigned root) {
    if (note < 0 || note > 127)
        return -1;
    if (!scale || scale > 2u || root > 11u)
        return note;
    int snapped = modwerk_scale_snap(note, scale == 1u ? 1u : 6u, root);
    return snapped > note ? -1 : snapped;
}
