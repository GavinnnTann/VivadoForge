# boards/

One folder per board: `board.json` (part, clock, flash, roles and polarity) and `master.xdc`
(every pin, from the vendor). These files are the pin authority for every project, so change
them only from the vendor's documentation. See [docs/boards.md](../docs/boards.md).

The Digilent master XDC files come from https://github.com/Digilent/digilent-xdc and are
licensed under the MIT licence in [LICENSE-digilent-xdc.txt](LICENSE-digilent-xdc.txt). The SUTD
DSL kit file is derived from Digilent's Cmod A7 master with the kit's pin map.
