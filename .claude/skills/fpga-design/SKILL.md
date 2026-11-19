---
name: fpga-design
description: Use when a person describes a digital system to build on the FPGA board (e.g. "make a reaction timer on the Cmod A7", "build a UART-controlled PWM on the Basys 3"). End-to-end procedure from natural-language spec to a verified bitstream, stopping before hardware programming for approval.
---

# Design an FPGA system from a description

Goal: turn the person's description into RTL that is simulated, built and timing-clean, then
hand over for approval before anything touches the board.

## 1. Understand the board (never assume)

```
python scripts/forge.py info --json
python scripts/forge.py board --json
```

Note the FPGA part, the clock frequency (12 MHz on Cmod A7 / SUTD kit, 100 MHz elsewhere), and
which roles exist (led, button, switch, seg/dp/digit, uart_tx/uart_rx, gpio, pmod_*) with their
polarity. If the request needs a peripheral the board does not have (e.g. a 7-segment display on
a bare Cmod A7), say so and offer options (another board, a Pmod, the UART instead).

## 2. Write a short spec and get agreement when it matters

List inputs and outputs (board role, design port name, polarity), behaviour as states or
timing, numeric ranges (e.g. 0-9999 ms), and what "done" means. Ask the person only about real
ambiguities (e.g. "show milliseconds or seconds?"); pick sensible defaults for the rest and
state them.

## 3. Start from the closest template if the project is new

```
python scripts/forge.py templates
python scripts/forge.py new -t <template> -b <board> [--name <name>] [--force]
```

`--force` replaces `src/`, `tb/` and `constraints/`: confirm with the person first if those
hold their work. To add to an existing project, skip this step.

## 4. Architecture

Sketch the module hierarchy: a thin top (pins, polarity) plus one module per job. Reuse
`lib/` (`python scripts/forge.py lib`): `tick_gen` for time bases, `debounce` for buttons,
`seven_seg` for displays, `uart_tx`/`uart_rx`, `spi_master`, `pwm`, `fifo_sync`, `ram_sp`,
`lfsr`, `bin2bcd`. Add every lib module you use to `lib = [...]` in `forge.toml`.

## 5. Write RTL and tests together

Follow the `fpga-module` skill for each new module: synthesisable RTL in `src/`, a
self-checking `tb/<module>_tb.v` with `CHECK`/`CHECK_EQ`/`TEST_DONE`, and time constants as
parameters so tests run with a small `CLK_HZ`. Test the top module too.

## 6. Pins

Follow the `fpga-pins` skill: `python scripts/forge.py pins add <role or port>=<design port>`.
Every top-level port must be pinned; the clock port gets its `create_clock` automatically.

## 7. Verify in order

```
python scripts/forge.py check --json     # fix every error
python scripts/forge.py sim --json       # every test must pass
python scripts/forge.py build --json     # status must be "passed"
```

Debug with `fpga-debug-sim`, `fpga-fix-build` or `fpga-timing` as needed. Anything other than
`passed` comes with `reasons`; fix each one. A passing build can still list benign or waived
critical warnings: mention the waived ones in your report.

## 8. Report and hand over

Tell the person:
- what was built (modules, which lib modules, which pins on which board header);
- the evidence: tests passed (names and counts), timing (WNS), utilisation;
- what was NOT verified: behaviour on the real board;
- how to try it: what to press or watch. For UART designs give the baud rate and settings.

Then ask whether to program the board (volatile) or write the flash (persistent). Do nothing
on the hardware until they answer; then follow the `fpga-program` skill.
