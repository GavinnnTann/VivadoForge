## Pin constraints for blink (template 'blink')
## Board: Digilent Cmod A7-35T (xc7a35tcpg236-1). Pins copied from boards/cmod_a7/master.xdc.
## Add pins with `python scripts/forge.py pins add <board port>=<your port>`; never type pin
## numbers from memory. `python scripts/forge.py check` verifies this file against the board.

## Board configuration
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]

## 12 MHz Clock Signal
set_property -dict { PACKAGE_PIN L17  IOSTANDARD LVCMOS33 } [get_ports { clk }]; #IO_L12P_T1_MRCC_14 Sch=gclk
create_clock -add -name sys_clk_pin -period 83.333 -waveform {0 41.667} [get_ports { clk }];
## LEDs
set_property -dict { PACKAGE_PIN A17  IOSTANDARD LVCMOS33 } [get_ports { led[0] }]; #IO_L12N_T1_MRCC_16 Sch=led[1]
set_property -dict { PACKAGE_PIN C16  IOSTANDARD LVCMOS33 } [get_ports { led[1] }]; #IO_L13P_T2_MRCC_16 Sch=led[2]
