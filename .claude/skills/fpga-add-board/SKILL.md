---
name: fpga-add-board
description: Use when someone wants to use an FPGA board that is not in boards/ yet. Creates boards/<id>/board.json and master.xdc from the vendor's official files, never from memory.
---

# Add a board

A board definition is two files in `boards/<id>/`:

- `master.xdc`: every user pin, from the vendor (Digilent publishes them at
  https://github.com/Digilent/digilent-xdc). Keep it verbatim, every line commented out.
- `board.json`: part number, clock, configuration properties, flash parameters and roles
  (named groups of master ports with direction and polarity).

Board data must come from the vendor's files and reference manual. If you cannot get the
official master XDC, stop and ask the person for it. Do not reconstruct pin lists from memory.
Adding a board is a `boards/` change, so get the person's approval for the result.

## Steps

1. Copy an existing `board.json` with the same vendor as a starting point.
2. Put the vendor master XDC in `boards/<id>/master.xdc` (note its source URL in
   `master_xdc_source`).
3. Fill `board.json`:
   - `part`: the exact FPGA part, including speed grade (e.g. `xc7a35ticsg324-1L`).
   - `clock.port`: the master's clock port name; `clock.freq_hz` from the reference manual.
   - `xdc_config`: at least `CFGBVS` and `CONFIG_VOLTAGE` for 7-series boards.
   - `flash`: Vivado configuration-memory part names, size in MB, interface; set
     `verified_on_hardware` to false until someone has flashed a real board.
   - `roles`: `clock`, `led`, `button`, `switch`, `seg`/`dp`/`digit`, `uart_tx`/`uart_rx`
     (`uart_tx` is the FPGA's output), Pmods, headers. Ports may use patterns (`led[*]`,
     `pio*`). Set `active_low` from the reference manual and write anything surprising in
     `note`.
4. Validate:

```
python scripts/forge.py boards --json          # problems[] must be empty for the new board
python scripts/forge.py board <id>
python scripts/forge.py new -t blink -b <id> --dir build/try-<id>
python scripts/forge.py -p build/try-<id> check
python scripts/forge.py -p build/try-<id> sim
python scripts/forge.py -p build/try-<id> build
```

5. Run `python scripts/forge.py selftest --quick`, add the board to the table in README.md and
   docs/boards.md, and say which parts were verified on hardware.
