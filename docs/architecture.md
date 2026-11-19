# Architecture

```
 person / AI agent / VS Code task / forge_gui.py
                 |
                 v
     scripts/forge.py  (Python 3.11+, standard library only)
       |-- forge.toml + forge.local.toml ----> config.py
       |-- boards/<id>/board.json + master.xdc -> boards.py, xdc.py
       |-- check: hdl.py (ports) + xdc.py (pins) + checks.py
       |-- sim:   sim.py -> xvlog/xelab/xsim  or  iverilog/vvp
       |-- build/program/flash/devices:
       |      build.py writes <build>/forge_context.tcl
       |      vivado -mode batch -source forge.tcl -tclargs --forge <action> forge_context.tcl
       |      reports.py turns logs and .rpt files into reports/summary.json
       |      manifest.py records what the bitstream was built from (reports/manifest.json)
       '-- new/pins: templates.py (RTL from templates/, pins from the board master)

     scripts/forge.tcl  (Vivado side)
       forge::make_project, forge::build, forge::program, forge::flash, forge::devices,
       forge::open_routed, forge::worst_paths
       usable in batch mode (above) and in any interactive / MCP Vivado session
```

## Design decisions

- **One entry point.** `forge.py` is the contract for people, VS Code tasks, the GUI, CI and AI
  agents. MCP servers are optional extras for interactive inspection, not a dependency. If an
  MCP server disappears, nothing breaks.
- **Settings flow one way.** `forge.toml` and `board.json` are the sources of truth. Vivado
  only ever sees the generated `forge_context.tcl`, so there is nothing to keep in sync by hand.
- **Vivado project mode, regenerated every build.** Each build recreates the `.xpr` from
  `forge.toml`, so the project in git is just text files and the build folder is disposable.
  Project mode keeps Vivado's standard reports and lets you open the result in the GUI.
- **Arguments through files.** Vivado's `.bat` wrappers pass arguments through `cmd.exe`,
  which splits `NAME=VALUE` and mangles quotes and spaces. forge passes simulator options in
  `-f` option files and runs Vivado with relative arguments from inside the build folder.
- **Verdicts from output, not exit codes.** xsim exits 0 after `$fatal`, so a test passes only
  on `TEST PASSED` with no error lines.
- **Safety by construction.** The build folder carries a marker and forge refuses to write to
  or delete folders without it. `program`/`flash` need a real terminal confirmation or `--yes`,
  and refuse a bitstream whose recorded inputs (`reports/manifest.json`) no longer match the
  sources. The Tcl `forge::program`/`forge::flash` only run when started by `forge.py`.
  `check` rejects pins that are not on the board and ports that point against the board wiring.
- **Say what was verified.** A build summary separates "a bitstream exists" from "timing was
  met", "DRC is clean" and "critical warnings are explained", and always reports hardware as
  not tested. `passed` needs all of them; anything less is `unverified` with reasons. The
  verdict is computed from the recorded facts, so `report` re-applies `[build.waive]` without a
  rebuild.

## Tests

| Layer | Test |
|---|---|
| Python tooling | `tests/test_forge.py` (unittest; parsers, config, checks, generation) |
| RTL library | `lib/<module>/<module>_tb.v`, self-checking, on xsim and Icarus |
| Templates x boards | `forge.py selftest` generates every template for every compatible board, checks and simulates it |
| Vivado flow | `forge.py build` on real designs (manual: needs Vivado) |
| CI | `.github/workflows/ci.yml` runs unit tests and `selftest --simulator iverilog` on Ubuntu |
