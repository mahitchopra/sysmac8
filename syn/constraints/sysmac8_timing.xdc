create_clock -period 10.000 -name sys_clk [get_ports clk]
set_input_delay -clock sys_clk 1.000 [remove_from_collection [all_inputs] [get_ports clk]]
set_output_delay -clock sys_clk 1.000 [all_outputs]
