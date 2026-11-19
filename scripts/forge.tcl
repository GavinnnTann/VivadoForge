# forge.tcl - the Vivado side of VivadoForge.
#
# Batch mode (this is what `python scripts/forge.py build|program|flash|devices` runs):
#   vivado -mode batch -source forge.tcl -tclargs --forge <build|program|flash|devices> <context.tcl>
#
# Interactive / MCP session (Vivado Tcl console, AMD Ross `vivado_execute`, or any MCP server
# that can run Tcl in a live Vivado):
#   source <repo>/scripts/forge.tcl
#   forge::load <build_dir>/forge_context.tcl   ;# written by every forge.py build/program/flash
#   forge::open_routed                          ;# open the routed design of the last build
#   forge::worst_paths 10                       ;# text report of the 10 worst setup paths
#
# All settings come from the context file that forge.py generates from forge.toml and
# boards/<board>/board.json. Edit forge.toml, not the generated files.

namespace eval ::forge {
    variable ctx [dict create]
}

proc ::forge::load {ctx_file} {
    variable ctx
    if {![file exists $ctx_file]} {
        error "context file not found: $ctx_file (run 'python scripts/forge.py build' first)"
    }
    source $ctx_file
    return [dict get $ctx name]
}

proc ::forge::get {key {default ""}} {
    variable ctx
    if {[dict exists $ctx $key]} { return [dict get $ctx $key] }
    return $default
}

proc ::forge::say {msg} {
    puts "FORGE: $msg"
    flush stdout
}

proc ::forge::runs_dir {} {
    return [file join [get project_dir] "[get name].runs"]
}

proc ::forge::bitstream {} {
    return [file join [runs_dir] impl_1 "[get top].bit"]
}

# ------------------------------------------------------------------------------------------------
# Build
# ------------------------------------------------------------------------------------------------
proc ::forge::make_project {} {
    set pdir [get project_dir]
    file mkdir $pdir
    say "creating project [get name] for [get part] in $pdir"
    ::create_project -force [get name] $pdir -part [get part]
    set_property target_language Verilog [current_project]

    set srcs [get sources]
    if {[llength $srcs] == 0} { error "no source files (check \[project\].sources in forge.toml)" }
    add_files -norecurse -fileset sources_1 $srcs
    foreach f [get vhdl_sources] {
        set_property FILE_TYPE {VHDL 2008} [get_files -of_objects [get_filesets sources_1] $f]
    }
    set xdcs [get constraints]
    if {[llength $xdcs]} { add_files -norecurse -fileset constrs_1 $xdcs }

    set fs [get_filesets sources_1]
    set_property top [get top] $fs
    if {[llength [get include_dirs]]} { set_property include_dirs [get include_dirs] $fs }
    if {[llength [get defines]]}      { set_property verilog_define [get defines] $fs }
    if {[llength [get generics]]}     { set_property generic [get generics] $fs }
    set_property strategy [get synth_strategy] [get_runs synth_1]
    set_property strategy [get impl_strategy] [get_runs impl_1]

    set ips [get_ips -quiet]
    if {[llength $ips]} {
        foreach ip $ips {
            if {[get_property IS_LOCKED $ip]} {
                say "upgrading locked IP $ip"
                upgrade_ip $ip
            }
        }
        generate_target all $ips
    }
    update_compile_order -fileset sources_1
}

proc ::forge::run_step {run args} {
    say "running $run"
    launch_runs $run -jobs [get jobs 4] {*}$args
    wait_on_run $run
    set r [get_runs $run]
    set progress [get_property PROGRESS $r]
    set status [get_property STATUS $r]
    say "$run: $status ($progress)"
    if {$progress ne "100%" || [string match -nocase "*error*" $status] || [string match -nocase "*fail*" $status]} {
        error "$run failed: $status (log: [get_property DIRECTORY $r]/runme.log)"
    }
}

proc ::forge::build {} {
    make_project
    run_step synth_1
    run_step impl_1 -to_step write_bitstream
    set bit [bitstream]
    if {![file exists $bit]} { error "implementation finished but no bitstream was written: $bit" }
    say "bitstream: $bit"
}

# ------------------------------------------------------------------------------------------------
# Hardware: program (volatile), flash (non-volatile), list devices
#
# program and flash run only from `python scripts/forge.py program|flash`, which first checks that
# the bitstream was built from the current sources and that a person approved. Called from an
# interactive or MCP session they refuse, so they are never an unguarded path to the hardware.
# Every error path closes the hardware session, so a failed attempt leaves no session open.
# ------------------------------------------------------------------------------------------------
proc ::forge::fail {code msg} {
    error $msg "" [list FORGE $code]
}

proc ::forge::require_cli {action} {
    if {![info exists ::forge::from_cli] || !$::forge::from_cli} {
        fail not_from_cli "forge::$action only runs from 'python scripts/forge.py $action', which checks that the\
            bitstream matches the current sources and asks a person to approve. Use that command instead."
    }
}

proc ::forge::hw_open {} {
    if {[catch {open_hw_manager; connect_hw_server -allow_non_jtag} msg]} {
        hw_close
        fail no_hw_server "could not start or reach the Vivado hardware server ($msg)"
    }
    if {[catch {open_hw_target} msg]} {
        hw_close
        fail no_jtag_target "no JTAG target found ($msg). Check the USB cable, board power and cable drivers."
    }
    set devs [get_hw_devices -quiet]
    if {[llength $devs] == 0} {
        hw_close
        fail no_device "the JTAG chain has no devices"
    }
    set want ""
    regexp -nocase {^(xc[0-9]+[a-z]+[0-9]+t)} [get part] -> want
    foreach d $devs {
        if {$want ne "" && [string match -nocase "${want}*" [get_property PART $d]]} {
            current_hw_device $d
            return $d
        }
    }
    set found {}
    foreach d $devs { lappend found "$d ([get_property PART $d])" }
    hw_close
    fail wrong_device "connected FPGA is [join $found {, }] but the project targets [get part]. Check \[project\].board in forge.toml."
}

proc ::forge::hw_close {} {
    catch {close_hw_target}
    catch {disconnect_hw_server}
    catch {close_hw_manager}
}

proc ::forge::program {} {
    require_cli program
    set bit [bitstream]
    if {![file exists $bit]} { fail no_bitstream "bitstream not found: $bit (run 'python scripts/forge.py build' first)" }
    set dev [hw_open]
    if {[catch {
        say "programming $dev with $bit"
        set_property PROGRAM.FILE $bit $dev
        program_hw_devices $dev
        refresh_hw_device $dev
    } msg opts]} {
        hw_close
        return -options $opts $msg
    }
    hw_close
    say "programmed (volatile: the design is lost at power-off)"
}

proc ::forge::flash {} {
    require_cli flash
    set bit [bitstream]
    if {![file exists $bit]} { fail no_bitstream "bitstream not found: $bit (run 'python scripts/forge.py build' first)" }
    set dev [hw_open]
    if {[catch {write_flash $dev $bit} msg opts]} {
        catch {endgroup}
        hw_close
        return -options $opts $msg
    }
    hw_close
    say "flash programmed and verified. Power-cycle or press PROG/reset to boot from flash."
}

proc ::forge::write_flash {dev bit} {
    set mcs [file join [runs_dir] impl_1 "[get top].mcs"]
    refresh_hw_device $dev

    # Pick the first configuration-memory part name Vivado knows from the board's list.
    set cfgmem_part ""
    foreach pattern [get flash_parts] {
        set matches [get_cfgmem_parts -quiet $pattern]
        if {[llength $matches] > 0} {
            set cfgmem_part [lindex $matches 0]
            break
        }
    }
    if {$cfgmem_part eq ""} {
        fail unknown_flash_part "none of the flash parts listed in board.json are known to this Vivado ([get flash_parts]). Run 'get_cfgmem_parts *spi*' in a Vivado Tcl console to find the right name."
    }
    say "flash part: $cfgmem_part"
    create_hw_cfgmem -hw_device $dev [lindex [get_cfgmem_parts $cfgmem_part] 0]
    set cfgmem [get_property PROGRAM.HW_CFGMEM $dev]

    say "writing configuration image $mcs ([get flash_size_mb] MB, [get flash_interface])"
    write_cfgmem -force -format mcs -size [get flash_size_mb] -interface [get flash_interface] \
        -loadbit "up 0x0 $bit" -file $mcs

    set_property PROGRAM.ADDRESS_RANGE {use_file} $cfgmem
    set_property PROGRAM.FILES [list $mcs] $cfgmem
    set_property PROGRAM.BPI_RS_PINS {none} $cfgmem
    set_property PROGRAM.BLANK_CHECK 0 $cfgmem
    set_property PROGRAM.ERASE 1 $cfgmem
    set_property PROGRAM.CFG_PROGRAM 1 $cfgmem
    set_property PROGRAM.VERIFY 1 $cfgmem

    startgroup
    # Load the flash-programming helper bitstream into the FPGA if it is not already there.
    if {![string equal [get_property PROGRAM.HW_CFGMEM_TYPE $dev] \
                       [get_property MEM_TYPE [get_property CFGMEM_PART $cfgmem]]]} {
        create_hw_bitstream -hw_device $dev [get_property PROGRAM.HW_CFGMEM_BITFILE $dev]
        program_hw_devices $dev
    }
    say "erasing, programming and verifying flash"
    program_hw_cfgmem -hw_cfgmem $cfgmem
    endgroup

    refresh_hw_device $dev
}

proc ::forge::devices {} {
    open_hw_manager
    connect_hw_server -allow_non_jtag
    set targets [get_hw_targets -quiet]
    if {[llength $targets] == 0} {
        puts "FORGE_DEVICE: none"
    }
    foreach t $targets {
        if {[catch {open_hw_target $t} msg]} {
            puts "FORGE_DEVICE: target=$t error=[string map {\n { }} $msg]"
            continue
        }
        foreach d [get_hw_devices -quiet] {
            puts "FORGE_DEVICE: target=$t device=$d part=[get_property PART $d]"
        }
        catch {close_hw_target $t}
    }
    catch {disconnect_hw_server}
    catch {close_hw_manager}
}

# ------------------------------------------------------------------------------------------------
# Helpers for interactive / MCP sessions
# ------------------------------------------------------------------------------------------------
proc ::forge::open_routed {} {
    set dcp [file join [runs_dir] impl_1 "[get top]_routed.dcp"]
    if {![file exists $dcp]} { error "no routed checkpoint at $dcp (run 'python scripts/forge.py build' first)" }
    open_checkpoint $dcp
    return $dcp
}

proc ::forge::worst_paths {{n 10}} {
    return [report_timing -max_paths $n -nworst 1 -sort_by group -input_pins -return_string]
}

# ------------------------------------------------------------------------------------------------
# Batch entry point
# ------------------------------------------------------------------------------------------------
if {[info exists ::argv] && [lindex $::argv 0] eq "--forge"} {
    set ::forge::action [lindex $::argv 1]
    if {$::forge::action ni {build program flash devices}} {
        puts "FORGE_ERROR: unknown action '$::forge::action'"
        exit 2
    }
    set ::forge::from_cli 1
    if {[catch {
        ::forge::load [lindex $::argv 2]
        ::forge::$::forge::action
    } ::forge::msg ::forge::opts]} {
        puts "FORGE_ERROR: $::forge::msg"
        set ::forge::code [dict get $::forge::opts -errorcode]
        if {[lindex $::forge::code 0] eq "FORGE"} { puts "FORGE_ERROR_CODE: [lindex $::forge::code 1]" }
        puts [dict get $::forge::opts -errorinfo]
        exit 1
    }
    exit 0
}
