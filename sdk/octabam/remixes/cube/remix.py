"""CUBE beside every stock effect. Static-stock, no DSP loader: CUBE's DSP voice (459 words) lives
in core 1's free program memory above its stock records (tracks 1-4; schema.DspSection.free_top),
so no stock effect gives up its code. All thirteen stay on both FX choosers of every track."""
from remix.schema import NO_FALLBACK, Remix
REMIX = Remix(name="cube", doc="CUBE wavetable machine (tracks 1-4) beside every stock effect.",
              modules=("CUBE",
                       "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER",
                       "CHORUS", "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI",
                       "DELAY", "PLATE REV", "SPRING REV", "DARK REV"),
              fallback=NO_FALLBACK)
