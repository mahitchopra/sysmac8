// rtl/core/requantizer.v
`timescale 1ns / 1ps

module requantizer (
    input  wire signed [25:0] accum_in,
    input  wire [4:0]         shift_val,  // Scaling factor determined during Python quantization
    output wire signed [7:0]  act_out
);

    // 1. Rounding: Add 2^(shift_val - 1) before shifting to round to nearest integer.
    // If shift_val is 0, we add nothing.
    wire signed [25:0] round_add = (shift_val > 0) ? (26'sd1 <<< (shift_val - 1)) : 26'sd0;
    
    // 2. Arithmetic Right Shift (Scaling)
    wire signed [25:0] scaled = (accum_in + round_add) >>> shift_val;

    // 3. ReLU Activation: If the sign bit (MSB) is 1, output 0. Otherwise, pass through.
    wire signed [25:0] relu_val = (scaled[25]) ? 26'sd0 : scaled;

    // 4. Saturation: Clamp to maximum INT8 value (127)
    assign act_out = (relu_val > 26'sd127) ? 8'sd127 : relu_val[7:0];

endmodule