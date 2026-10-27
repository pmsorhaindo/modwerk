"""Turing Machine beside every stock effect. A remix lists the stock effects it keeps on the FX
choosers; one that lists none ships an FX2 list of NONE only (seen on OCTABAM11U's selection)."""
from remix.schema import NO_FALLBACK, Remix
REMIX = Remix(name="turing", doc="Turing Machine beside every stock effect.",
              modules=("TURING MACHINE",
                       "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER",
                       "CHORUS", "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI",
                       "DELAY", "PLATE REV", "SPRING REV", "DARK REV"),
              fallback=NO_FALLBACK)
