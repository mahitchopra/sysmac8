module pe #(
    parameter ARCH = "BOOTH_WALLACE"
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               weight_en,  // High to latch stationary weight
    input  wire signed [7:0]  w_in,       // Weight loading line
    input  wire signed [7:0]  a_in,       // Activation streaming from left
    input  wire signed [25:0] psum_in,    // Partial sum streaming from top
    output reg  signed [7:0]  a_out,      // Forwarded activation to right
    output reg  signed [25:0] psum_out    // Forwarded partial sum to bottom
);