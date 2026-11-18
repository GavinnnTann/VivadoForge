# Configuration reference

## forge.toml (committed, one per project)

```toml
[project]
name = "blink"                        # Vivado project name: letters, digits, _ and -
top = "blink"                         # top-level module; its ports are the FPGA pins
board = "cmod_a7"                     # folder name in boards/
sources = ["src/**/*.v", "src/**/*.sv", "src/**/*.vhd", "src/**/*.mem"]
lib = ["uart_tx", "debounce"]         # modules from lib/ to include
constraints = ["constraints/*.xdc"]
include_dirs = []                     # extra `include folders (source folders are added automatically)
defines = { USE_FAST_MODE = 1 }       # Verilog `define values for synthesis and simulation
generics = { CLK_HZ = 12000000 }      # override top-level parameters in synthesis

[sim]
tests = ["tb/*_tb.v", "tb/*_tb.sv"]   # each file is one testbench; module name = file name
timeout = 300                         # seconds per testbench before it is killed
simulator = "auto"                    # auto (xsim if Vivado is installed, else Icarus) | xsim | iverilog

[build]
dir = "build"                         # build folder ({name} = project name)
jobs = 4                              # parallel Vivado jobs
synth_strategy = "Vivado Synthesis Defaults"
impl_strategy = "Vivado Implementation Defaults"
timing = "error"                      # "error": failed timing fails the build; "warn": report only
```

- Paths are relative to `forge.toml`. Patterns support `*`, `?` and `**` (any depth).
- A wildcard pattern that matches nothing is fine (e.g. no `.sv` files). A literal file path that
  does not exist is an error.
- Source types by extension: `.v` Verilog, `.sv` SystemVerilog, `.vhd`/`.vhdl` VHDL-2008, `.vh`/`.svh`
  headers, `.mem`/`.hex`/`.dat`/`.coe` memory files, `.xci` Vivado IP (build only, experimental).
- Unknown keys produce a warning (`forge.py check`), so typos do not pass silently.
- Every simulation also defines `SIMULATION`, so `` `ifdef SIMULATION `` can shorten delays in
  testbench-only code. Prefer parameters for this.

## forge.local.toml (per machine, git-ignored)

```toml
vivado = "C:/Xilinx/Vivado/2023.1/bin/vivado.bat"   # or the install folder
build_dir = "C:/fpga_build/{name}"                   # overrides [build].dir on this machine
jobs = 8
simulator = "iverilog"
iverilog = "C:/iverilog/bin"
```

Write it with `python scripts/forge.py setup --detect --build-dir "C:/fpga_build/{name}"` or by
hand. Use forward slashes on Windows.

## Environment variables

| Variable | Effect |
|---|---|
| `VIVADO_PATH` | Vivado executable or install folder (used if `forge.local.toml` has no `vivado`) |
| `XILINX_VIVADO` | Set by Vivado's `settings64` scripts; used the same way |
| `FORGE_BUILD_DIR` | Overrides the build folder (handy in CI) |

## The build folder

```
<build folder>/
  .forge-build            marker: forge only writes to / deletes folders that have it
  forge_context.tcl       generated settings for forge.tcl (do not edit)
  vivado/<name>.xpr       the Vivado project (open with `forge.py open`)
  reports/summary.json    machine-readable result of the last build
  reports/*.rpt           timing, utilization, drc, methodology, io, power, ...
  <name>.bit              copy of the last good bitstream
  sim/<test>/sim.log      simulation logs; waves.wdb / waves.vcd with --wave
  logs/                   Vivado batch logs
```

Everything there is regenerated on demand, so do not keep anything important in it.
