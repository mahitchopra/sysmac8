module requantizer (
    input  wire signed [25:0] accum_in,   // 26-bit accumulated sum from tile
    input  wire [4:0]         shift_val,  // Right shift amount (e.g., 6 to 12)
    output wire signed [7:0]  act_out     // Requantized INT8 activation out
);