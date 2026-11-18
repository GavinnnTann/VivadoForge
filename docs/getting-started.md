# Getting started

From a fresh computer to a blinking LED. Takes about an hour, mostly the Vivado download.

## 1. Install the tools

| Tool | Notes |
|---|---|
| [AMD Vivado](https://www.xilinx.com/support/download.html) 2023.1 or newer | The free **Vivado ML Standard** edition supports every board in `boards/`. Install with the "Vivado" product and the Artix-7 device family; tick **Install Cable Drivers**. About 30-60 GB. |
| Python 3.11 or newer | [python.org](https://www.python.org/downloads/). On Windows tick "Add python.exe to PATH". Only the standard library is used. |
| VS Code (recommended) | Open the folder and accept the recommended extensions (Verilog syntax, Python). |
| Icarus Verilog (optional) | A fast second simulator: [bleyer.org/icarus](https://bleyer.org/icarus/) on Windows, `apt install iverilog` / `brew install icarus-verilog`. |

Linux: run `<Vivado>/data/xicom/cable_drivers/lin64/install_script/install_drivers/install_drivers`
as root once so the USB-JTAG cable is visible.

## 2. Get the project

On GitHub press **Use this template** to get your own copy, then clone it. Or clone this
repository directly:

```sh
git clone https://github.com/GavinnnTann/VivadoForge my-fpga-project
cd my-fpga-project
```

## 3. Tell forge where Vivado is

```sh
python scripts/forge.py setup --detect
```

This finds Vivado in the usual install folders and records it in `forge.local.toml` (a
per-computer file that git ignores). If it is somewhere unusual:
`python scripts/forge.py setup --vivado "D:/Tools/Vivado/2024.2/bin/vivado.bat"`.

**Project inside OneDrive, Dropbox or a path with many spaces?** Keep Vivado's build output
out of it; syncing thousands of temporary files is slow and can lock files mid-build:

```sh
python scripts/forge.py setup --build-dir "C:/fpga_build/{name}"
```

## 4. Make a project for your board

```sh
python scripts/forge.py boards                                     # which boards exist
python scripts/forge.py templates                                  # which starting points exist
python scripts/forge.py new --template blink --board basys3 --force
```

`--force` replaces `src/`, `tb/` and `constraints/`. The repository ships with `blink` for the
Cmod A7. The template writes the RTL with your board's clock frequency and LED polarity, a
testbench, and a constraints file whose pins come straight from the board's master XDC.

## 5. Check, simulate, build

```sh
python scripts/forge.py check     # seconds: config, pins and clock
python scripts/forge.py sim       # runs tb/*_tb.v; prints PASS/FAIL per testbench
python scripts/forge.py build     # a few minutes: synthesis, implementation, bitstream
```

The build ends with a summary like:

```
BUILD PASSED  (279.9 s, Vivado 2023.1)
  timing:  met   WNS 79.65 ns   TNS 0.0 ns   WHS 0.245 ns   failing endpoints 0
  usage:   LUT 7/20800 (0.03%)   FF 25/41600 (0.06%)   BRAM 0/50 (0.0%)   DSP 0/90 (0.0%)   IO 3/106 (2.83%)
```

**WNS** (worst negative slack) must be zero or positive: then the design meets its clock. Every
report is in the build folder under `reports/`; `forge.py open` opens the project in the Vivado
GUI if you want to look at schematics.

## 6. Program the board

Plug the board in with a USB **data** cable, then:

```sh
python scripts/forge.py devices   # should list the FPGA, e.g. xc7a35t_0
python scripts/forge.py program   # asks, then loads the FPGA (lost at power-off)
python scripts/forge.py flash     # asks, then writes the flash (boots at every power-up)
```

## 7. Make it yours

1. Edit or replace `src/*.v`. Keep `top` in `forge.toml` pointing at the module whose ports are
   the FPGA pins.
2. Connect ports to pins with `python scripts/forge.py pins add <board port>=<your port>`; list
   the board's ports with `python scripts/forge.py pins`.
3. Reuse tested modules from `lib/` (`python scripts/forge.py lib`): add their names to
   `lib = [...]` in `forge.toml`.
4. Write a testbench for each module ([simulation.md](simulation.md)).
5. `check`, then `sim`, then `build`, then `program`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Vivado not found` | `forge.py setup --vivado <path>`, or set `VIVADO_PATH` |
| `Build folder ... already contains files that VivadoForge did not create` | Point `build_dir` at an empty or new folder. Forge never mixes its output with other files, because `clean` deletes the whole folder. |
| `no JTAG target found` / `devices` lists nothing | Use a data cable (not charge-only), check the power LED, reinstall the cable drivers, close any open Vivado Hardware Manager |
| `connected FPGA is ... but the project targets ...` | `board` in `forge.toml` does not match the board you plugged in |
| Build fails in a OneDrive folder with file-lock errors | `forge.py setup --build-dir "C:/fpga_build/{name}"` |
| `python` not found (Windows) | Reinstall Python with "Add to PATH", or use `py scripts/forge.py ...` |
| LED does the opposite of what you expect | Polarity: `forge.py board` lists which signals are active-low |
| Simulation passes, hardware does not work | Read the build's critical warnings, check the pins (`forge.py check`) and polarity, make sure inputs are synchronised/debounced |
