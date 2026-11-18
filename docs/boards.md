# Boards, pins and polarity

## Where pin data comes from

Each board has two files in `boards/<id>/`:

- **`master.xdc`**: every user-accessible pin, copied verbatim from the vendor
  ([Digilent's master XDC files](https://github.com/Digilent/digilent-xdc), MIT licence). Every
  line is commented out, and it is never added to a project. It is the only source of pin
  numbers.
- **`board.json`**: the facts a design needs: FPGA part, clock, configuration properties, flash
  chip and *roles* (named groups of master ports with direction and polarity).

Your project's own constraints (`constraints/*.xdc`) are built from the master with
`forge.py pins add` or `forge.py new`, and `forge.py check` cross-checks them against it.

## Using pins

```sh
python scripts/forge.py board              # roles with polarity and notes
python scripts/forge.py board --pins       # every pin of the board
python scripts/forge.py pins               # every pin + which design port uses it
python scripts/forge.py pins add sysclk=clk btn[0]=start led=status
```

`pins add` accepts a master port (`btn[0]`), a whole bus (`led` = every `led[i]`) or a role
(`seg`, `digit`, `uart_tx`), optionally renamed with `=name`. Buses are renumbered from 0. The
clock port also gets its `create_clock` line, and new constraint files start with the board's
configuration properties (`CFGBVS`, `CONFIG_VOLTAGE`).

`forge.py check` reports:

- a top-level port bit without `PACKAGE_PIN` or `IOSTANDARD` (Vivado would refuse the bitstream);
- a pin that does not exist on the board (typed by hand, or for another board);
- two ports on one pin;
- a clock port without `create_clock`, or with a period that is not the board's;
- an I/O standard that differs from the master's (usually a bank-voltage DRC error);
- constraints for ports the design does not have.

## Polarity

| Board | Active-low signals |
|---|---|
| Cmod A7 | RGB LED (`led0_r/g/b`) |
| SUTD DSL kit | RGB LED, 7-segment digit selects (`hex[*]`). Segments are active-high. Key polarity unconfirmed. |
| Basys 3 | 7-segment segments, decimal point and digit enables |
| Arty A7 | reset button `ck_rst` |
| Nexys A7 | 7-segment segments, decimal point and digit enables; `CPU_RESETN` |

Everything else (LEDs, buttons, switches) is active-high. The templates read polarity from
`board.json` and pass it to the RTL as parameters (`LED_ACTIVE_LOW`, `SEG_ACTIVE_LOW`, ...).

## board.json reference

```json
{
  "schema": 1,
  "name": "Digilent Basys 3",
  "vendor": "Digilent",
  "part": "xc7a35tcpg236-1",
  "master_xdc": "master.xdc",
  "master_xdc_source": "https://github.com/Digilent/digilent-xdc/blob/master/Basys-3-Master.xdc",
  "reference_manual": "https://digilent.com/reference/programmable-logic/basys-3/reference-manual",
  "clock": { "port": "clk", "freq_hz": 100000000 },
  "xdc_config": ["set_property CFGBVS VCCO [current_design]", "set_property CONFIG_VOLTAGE 3.3 [current_design]"],
  "flash": { "parts": ["s25fl032p-spi-x1_x2_x4"], "size_mb": 4, "interface": "SPIx1", "verified_on_hardware": false },
  "roles": {
    "led":    { "ports": ["led[*]"], "dir": "out", "active_low": false, "note": "16 LEDs" },
    "button": { "ports": ["btnC", "btnU", "btnL", "btnR", "btnD"], "dir": "in", "active_low": false }
  },
  "notes": ["..."]
}
```

- `clock.port` must be a port in the master XDC.
- `roles.*.ports` lists master port names; `*` matches any text (`led[*]`, `pio*`). Order
  matters: design bit 0 maps to the first port.
- Role names used by the templates: `clock`, `led`, `button`, `switch`, `seg` (A..G), `dp`,
  `digit`, `uart_tx` (FPGA output), `uart_rx` (FPGA input). Add any others you like (`pmod_ja`,
  `gpio`, `rgb`, ...).
- `flash.parts` are Vivado configuration-memory names (`get_cfgmem_parts` in the Vivado Tcl
  console). The first one Vivado knows is used, so list the board's actual chip first.

## Adding a board

1. Create `boards/<id>/` (lower case, `_` separators).
2. Copy the vendor's master XDC to `master.xdc` unchanged.
3. Write `board.json` (start from a similar board). Take the part, clock and polarity from the
   reference manual, not from memory.
4. Validate and try it:

```sh
python scripts/forge.py boards                      # the new board's "problems" must be empty (--json)
python scripts/forge.py new -t blink -b <id> --dir build/try-<id>
python scripts/forge.py -p build/try-<id> check
python scripts/forge.py -p build/try-<id> build
python scripts/forge.py selftest --quick
```

AI agents: follow `.claude/skills/fpga-add-board/SKILL.md`.

## Supported boards

| Id | Board | Part | Clock | Notes |
|---|---|---|---|---|
| `cmod_a7` | Digilent Cmod A7-35T | xc7a35tcpg236-1 | 12 MHz | 2 LEDs, RGB LED, 2 buttons, 48-pin DIP header, Pmod, USB-UART |
| `sutd_dsl_kit` | SUTD DSL Starter Kit + Cmod A7-35T | xc7a35tcpg236-1 | 12 MHz | adds 10 LEDs, 10 switches, 6-digit 7-segment, 2 keys, MCP3202 ADC |
| `basys3` | Digilent Basys 3 | xc7a35tcpg236-1 | 100 MHz | 16 LEDs, 16 switches, 5 buttons, 4-digit 7-segment, VGA, 3 Pmods |
| `arty_a7_35t` | Digilent Arty A7-35T | xc7a35ticsg324-1L | 100 MHz | 4 LEDs, 4 RGB LEDs, 4 switches, 4 buttons, 4 Pmods, Arduino header, Ethernet |
| `nexys_a7_100t` | Digilent Nexys A7-100T | xc7a100tcsg324-1 | 100 MHz | 16 LEDs, 16 switches, 5 buttons, 8-digit 7-segment, VGA, sensors, 4 Pmods |
