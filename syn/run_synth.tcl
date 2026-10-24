# SysMAC8 synthesis comparison: ARRAY vs BOOTH_WALLACE
# Run from the repository root:
# vivado -mode batch -source syn/run_synth.tcl

set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize "$script_dir/.."]
set rtl_dir "$root_dir/rtl"
set out_base "$script_dir/reports"

if {[info exists ::env(SYSMAC8_PART)]} {
    set fpga_part $::env(SYSMAC8_PART)
} else {
    set fpga_part "xc7a100tcsg324-1"
}

set rtl_sources [list \
    "$rtl_dir/arithmetic/mult_array_8x8.v" \
    "$rtl_dir/arithmetic/mult_booth_8x8.v" \
    "$rtl_dir/arithmetic/multiplier_top.v" \
    "$rtl_dir/core/pe.v" \
    "$rtl_dir/core/skew_registers.v" \
    "$rtl_dir/core/requantizer.v" \
    "$rtl_dir/core/systolic_grid_4x4.v" \
    "$rtl_dir/control/controller_fsm.v" \
    "$rtl_dir/control/accum_buffer.v" \
    "$rtl_dir/control/buffer_ram.v" \
    "$rtl_dir/top/argmax.v" \
    "$rtl_dir/top/sysmac8_top.v" \
]

proc run_arch_synthesis {arch_name top_mod fpga_part rtl_sources out_base} {
    set tag [string tolower "${top_mod}_${arch_name}"]
    set rpt_dir [file join $out_base $tag]
    file mkdir $rpt_dir

    puts "============================================================"
    puts "Synthesizing TOP=$top_mod | ARCH=$arch_name | PART=$fpga_part"
    puts "============================================================"

    close_project -quiet
    create_project -in_memory -part $fpga_part

    read_verilog $rtl_sources

    if {$arch_name eq "ARRAY"} {
        set arch_define "SYSMAC8_ARCH_ARRAY=1"
    } elseif {$arch_name eq "BOOTH_WALLACE"} {
        set arch_define "SYSMAC8_ARCH_BOOTH_WALLACE=1"
    } else {
        error "Unsupported architecture: $arch_name"
    }

    set constraints_dir [file join [file dirname $out_base] "constraints"]

    if {$top_mod eq "multiplier_top"} {
        set xdc_file [file join $constraints_dir "multiplier_timing.xdc"]
    } elseif {$top_mod eq "sysmac8_top"} {
        set xdc_file [file join $constraints_dir "sysmac8_timing.xdc"]
    } else {
        error "Unsupported top module: $top_mod"
    }

    if {![file exists $xdc_file]} {
        error "Timing constraint file not found: $xdc_file"
    }

    puts "Architecture define: $arch_define"
    puts "Reading constraints: $xdc_file"
    read_xdc $xdc_file

    # Disable DSP inference for a LUT/carry-logic comparison.
    # The power report is an estimate unless switching activity is supplied.
    synth_design \
        -top $top_mod \
        -part $fpga_part \
        -verilog_define $arch_define \
        -flatten_hierarchy rebuilt \
        -max_dsp 0

    report_utilization \
        -file "$rpt_dir/utilization.rpt"

    report_timing_summary \
        -delay_type max \
        -max_paths 10 \
        -file "$rpt_dir/timing_summary.rpt"

    report_power \
        -file "$rpt_dir/power.rpt"

    close_project -quiet
}

foreach arch [list "ARRAY" "BOOTH_WALLACE"] {
    run_arch_synthesis $arch "multiplier_top" $fpga_part $rtl_sources $out_base
    run_arch_synthesis $arch "sysmac8_top" $fpga_part $rtl_sources $out_base
}

puts "\nSynthesis runs complete. Reports saved under: $out_base"