---
name: fpga-program
description: Use when the person wants their design running on the physical FPGA board - programming over JTAG (volatile) or writing configuration flash (persistent). Requires explicit approval; covers pre-flight checks and troubleshooting.
---

# Program the board (only with approval)

Programming changes physical hardware. You need the person's explicit "yes" for this design in
this conversation before running anything below with `--yes`. If they have not said yes, ask:
say what will be loaded, on which board, and whether it is volatile or persistent.

## Pre-flight

```
python scripts/forge.py report --json     # status "passed"? timing met? critical warnings explained?
python scripts/forge.py devices --json    # is the board connected? (read-only)
```

- If `devices` is empty: check the USB cable (a data cable, not charge-only), board power, and
  that the cable drivers are installed (installed with Vivado; on Linux run Vivado's
  install_drivers script). Close other Vivado Hardware Manager sessions.
- If the connected part differs from the project's part, stop: wrong board in `forge.toml`.
- If timing failed, say so; the person decides whether to try anyway.

## Volatile (default)

```
python scripts/forge.py program --yes
```

Loads the bitstream into the FPGA. It runs until power-off or until something else is
programmed. Use this for normal development.

## Persistent (only when asked for flash)

```
python scripts/forge.py flash --yes
```

Erases and rewrites the configuration flash so the board boots this design at every
power-up. It takes about a minute. Then the person power-cycles the board (or presses PROG).
If `board.json` says `verified_on_hardware: false` for the flash settings, tell the person this
board's flash flow has not been verified yet.

## After programming

You cannot see the board. Tell the person what to look for (which LED, what to press, the
serial settings for UART designs: COM port, 115200 baud, 8N1) and ask them to confirm. Only
their confirmation counts as "works on hardware".

## If it fails

- "No JTAG target": cable or driver problem (see above).
- "connected FPGA is ... but the project targets ...": wrong `board` in `forge.toml`.
- Flash part errors: the flash chip differs from `board.json` `flash.parts`. Find the part in
  Vivado's Hardware Manager (Add Configuration Memory Device) and update `board.json`; that is a
  `boards/` change, so ask the person.
