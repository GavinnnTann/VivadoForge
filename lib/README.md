# lib/: tested, reusable RTL

Each folder holds one synthesisable Verilog-2001 module and its self-checking testbench. The
modules are independent (no module needs another), so you can also copy one into any project.

| Module | What it does | Key parameters |
|---|---|---|
| [tick_gen](tick_gen/tick_gen.v) | one-cycle enable pulse at `TICK_HZ` (use instead of divided clocks) | `CLK_HZ`, `TICK_HZ` |
| [debounce](debounce/debounce.v) | synchroniser + debouncer + press/release pulses for buttons and switches | `CLK_HZ`, `DEBOUNCE_MS`, `ACTIVE_LOW` |
| [seven_seg](seven_seg/seven_seg.v) | multiplexed N-digit 7-segment driver with hex decoder, blanking, dots | `CLK_HZ`, `DIGITS`, `SEG_ACTIVE_LOW`, `DIGIT_ACTIVE_LOW` |
| [pwm](pwm/pwm.v) | pulse-width modulator (LED dimming, motor control) | `WIDTH` |
| [uart_tx](uart_tx/uart_tx.v) | 8N1 UART transmitter with valid/ready handshake | `CLK_HZ`, `BAUD` |
| [uart_rx](uart_rx/uart_rx.v) | 8N1 UART receiver with synchroniser and framing-error flag | `CLK_HZ`, `BAUD` |
| [spi_master](spi_master/spi_master.v) | SPI mode-0 master, MSB first | `WIDTH`, `CLK_DIV` |
| [fifo_sync](fifo_sync/fifo_sync.v) | single-clock FIFO, first-word fall-through | `WIDTH`, `DEPTH` (power of two) |
| [ram_sp](ram_sp/ram_sp.v) | single-port RAM that Vivado maps to block RAM, optional `$readmemh` init | `WIDTH`, `DEPTH`, `INIT_FILE` |
| [lfsr](lfsr/lfsr.v) | maximal-length pseudo-random sequence (games, test patterns) | `WIDTH` = 8/16/24/32 |
| [bin2bcd](bin2bcd/bin2bcd.v) | sequential binary to decimal digits (timing-safe at 100 MHz) | `BITS`, `DIGITS` |

The header comment of each `.v` file documents the ports and shows an instantiation.

## Using a module

Add its folder name to `lib` in `forge.toml` and instantiate it:

```toml
[project]
lib = ["uart_tx", "debounce"]
```

## Tests

```sh
python scripts/forge.py sim --lib              # every module
python scripts/forge.py sim --lib uart_rx      # one module
```

All modules pass on Vivado xsim and Icarus Verilog. If you change a module, update its
testbench and rerun it. `include/forge_tb.vh` provides the `CHECK`, `CHECK_EQ`,
`TEST_TIMEOUT` and `TEST_DONE` macros used by every testbench (see
[docs/simulation.md](../docs/simulation.md)).
