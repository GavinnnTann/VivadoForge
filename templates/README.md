# templates/: starting projects

`python scripts/forge.py new --template <name> --board <board>` turns a template into a project
for one board: it fills in the board's clock frequency and polarities, copies the testbench,
and writes the constraints from the board's master XDC.

| Template | Shows | Boards |
|---|---|---|
| `blink` | clock, counter, LEDs | all |
| `button_counter` | synchronising and debouncing a button | all |
| `uart_echo` | UART receive, FIFO, transmit (talk to it from a serial terminal at 115200 8N1) | all |
| `reaction_timer` | state machine, random delay, 1 ms tick, BCD counting, 7-segment display | boards with a 4+ digit display |

## Anatomy

```
templates/<name>/
  template.json     description, top module, lib modules, parameters, port -> board role
  src/*.v           RTL with {{PARAM}} placeholders
  tb/*_tb.v         self-checking testbench, also with placeholders
```

`template.json`:

```json
{
  "top": "uart_echo",
  "lib": ["uart_rx", "fifo_sync", "uart_tx"],
  "params": { "CLK_HZ": "clock_hz", "N_LED": "count:led|max:8", "LED_ACTIVE_LOW": "active_low:led" },
  "ports": {
    "clk": { "role": "clock" },
    "uart_rx": { "role": "uart_rx" },
    "led": { "role": "led", "width": "N_LED" }
  },
  "requires": { "digit": 4 }
}
```

Parameter expressions: `clock_hz`, `count:<role>`, `active_low:<role>` (1 or 0), a number, with
optional `|max:N` / `|min:N`. A port with `width` maps its bits to the first ports of the role;
without `width` it takes the role's first port (or `index`). `forge.py selftest` generates
every template for every compatible board and runs its testbench.
