# syn/run_synth.tcl
# Vivado batch synthesis comparison for SysMAC8 (ARRAY vs BOOTH_WALLACE)
# Usage from repository root:
#   vivado -mode batch -source syn/run_synth.tcl

set script_dir [file dirname [file normalize [info script]]]
set root_dir   [file normalize "$script_dir/.."]
set rtl_dir    "$root_dir/rtl"
set out_base   "$script_dir/reports"

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
    set rpt_dir "$out_base/$tag"
    file mkdir $rpt_dir

    puts "============================================================"
    puts "Synthesizing TOP=$top_mod | ARCH=$arch_name | PART=$fpga_part"
    puts "============================================================"

    close_project -quiet
    create_project -in_memory -part $fpga_part

    read_verilog $rtl_sources

    # Disable DSP48 inference (-max_dsp 0) so LUT/carry logic is compared directly
    synth_design \
        -top $top_mod \
        -part $fpga_part \
        -generic "ARCH=$arch_name" \
        -flatten_hierarchy rebuilt \
        -max_dsp 0

    if {$top_mod eq "multiplier_top"} {
        # Combinational path constraint (10 ns virtual window)
        set_max_delay 10.0 -from [all_inputs] -to [all_outputs]
    } else {
        # 100 MHz (10.0 ns) system clock constraint
        create_clock -period 10.000 -name sys_clk [get_ports clk]
        set_input_delay  -clock sys_clk 1.000 [remove_from_collection [all_inputs] [get_ports clk]]
        set_output_delay -clock sys_clk 1.000 [all_outputs]
    }

    report_utilization    -file "$rpt_dir/utilization.rpt"
    report_timing_summary -delay_type max -max_paths 10 -file "$rpt_dir/timing_summary.rpt"
    report_power          -file "$rpt_dir/power.rpt"

    close_project -quiet
}

foreach arch {"ARRAY" "BOOTH_WALLACE"} {
    run_arch_synthesis $arch "multiplier_top" $fpga_part $rtl_sources $out_base
    run_arch_synthesis $arch "sysmac8_top"    $fpga_part $rtl_sources $out_base
}

puts "\nSynthesis runs complete. Reports saved under: $out_base"
