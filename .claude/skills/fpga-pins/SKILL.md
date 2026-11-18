---
name: fpga-pins
description: Use when connecting design ports to FPGA pins - adding LEDs, buttons, switches, displays, UART, Pmod or header pins, external chips - or moving a project to another board. Pins must come from the board master XDC through forge.py, never from memory.
---

# Connect ports to pins

The board's `boards/<id>/master.xdc` is the only source of pin numbers. You copy and rename
lines from it with `forge.py pins add`; you never type a `PACKAGE_PIN`.

## 1. Find the board ports

```
python scripts/forge.py board --json          # roles: led, button, seg, digit, uart_tx, gpio, pmod_ja, ...
python scripts/forge.py pins                  # every master port, its pin, I/O standard, who uses it
```

Roles group ports and carry polarity (`active_low`). For a Pmod or header, read the role note
for the pin numbering (e.g. Cmod A7 `ja[0..3]` = Pmod pins 1-4, `ja[4..7]` = pins 7-10).

## 2. Add them under your design's port names

```
python scripts/forge.py pins add sysclk=clk           # the clock port also gets create_clock
python scripts/forge.py pins add btn[0]=start         # single bit, renamed
python scripts/forge.py pins add led                  # whole bus, same names (led[0], led[1], ...)
python scripts/forge.py pins add led=status           # whole bus, renamed status[0..N-1]
python scripts/forge.py pins add seg=seg digit=an     # roles work too
python scripts/forge.py pins add ja[0]=sclk ja[1]=mosi ja[2]=miso ja[3]=cs_n
```

It appends to the project's first constraints file (or `--file constraints/x.xdc`), refuses
pins already in use, and skips ports that are already constrained.

## 3. Match the RTL

- Port names and bus widths in the top module must match exactly (`led[0]` needs
  `output [N-1:0] led`).
- Apply polarity in the top module: `assign led = LED_ACTIVE_LOW ? ~value : value;`.
- Inputs from buttons, switches and external chips need synchronising (`lib/debounce` for
  buttons).

## 4. Verify

```
python scripts/forge.py check --json
```

It fails on unpinned ports, missing I/O standards, pins that do not exist on the board,
duplicate pins and a missing or wrong `create_clock`. It warns about constraints for ports
that are not in the design. Fix everything before building.

## External hardware

- Use 3.3 V logic (`LVCMOS33`) unless the master says otherwise; never connect 5 V signals to
  FPGA pins.
- Open-drain buses (I2C) need `PULLUP true` or external pull-ups: add the property to the
  generated line, keep the pin.
- For several signals on one connector, keep them in one bank and note the wiring (which
  header pin goes where) in a comment in the XDC.

## Moving to another board

Create the project again for the new board (`forge.py new -t <template> -b <board> --force`)
or rebuild the constraints file: remove it, then `pins add` every port again from the new
board's roles. Recheck clock-dependent parameters (`CLK_HZ`) and polarities.
