// rtl/arithmetic/mult_array_8x8.v
`timescale 1ns / 1ps

module mult_array_8x8 #(
    parameter ARCH = "ARRAY" // Parameter included for wrapper compatibility
)(
    input  wire signed [7:0]  a_in,
    input  wire signed [7:0]  b_in,
    output wire signed [15:0] prod_out
);

    // -------------------------------------------------------------------------
    // Baugh-Wooley Partial Product Generation
    // -------------------------------------------------------------------------
    wire [15:0] pp0, pp1, pp2, pp3, pp4, pp5, pp6, pp7;

    // Rows 0 to 6: Multiply standard bits of 'b' against 'a'. 
    // The MSB of 'a' (a_in[7]) has a negative weight, so its product is inverted (NAND).
    // The remaining bits are standard AND products.
    assign pp0 = { 8'b0, ~(a_in[7] & b_in[0]), (a_in[6:0] & {7{b_in[0]}}) };
    assign pp1 = { 7'b0, ~(a_in[7] & b_in[1]), (a_in[6:0] & {7{b_in[1]}}), 1'b0 };
    assign pp2 = { 6'b0, ~(a_in[7] & b_in[2]), (a_in[6:0] & {7{b_in[2]}}), 2'b0 };
    assign pp3 = { 5'b0, ~(a_in[7] & b_in[3]), (a_in[6:0] & {7{b_in[3]}}), 3'b0 };
    assign pp4 = { 4'b0, ~(a_in[7] & b_in[4]), (a_in[6:0] & {7{b_in[4]}}), 4'b0 };
    assign pp5 = { 3'b0, ~(a_in[7] & b_in[5]), (a_in[6:0] & {7{b_in[5]}}), 5'b0 };
    assign pp6 = { 2'b0, ~(a_in[7] & b_in[6]), (a_in[6:0] & {7{b_in[6]}}), 6'b0 };

    // Row 7: Multiply the sign bit of 'b' (b_in[7]) against 'a'.
    // Since b_in[7] has a negative weight, all standard products are inverted (NAND).
    // However, a_in[7] * b_in[7] involves TWO negative weights, making it positive, 
    // so it remains a standard AND gate.
    assign pp7 = { 1'b0,  (a_in[7] & b_in[7]), ~(a_in[6:0] & {7{b_in[7]}}), 7'b0 };

    // -------------------------------------------------------------------------
    // Baugh-Wooley Compensation Constant
    // -------------------------------------------------------------------------
    // To complete the two's complement arithmetic without sign-extending every row,
    // the Baugh-Wooley algorithm adds a pre-calculated mathematical constant.
    // For an 8x8 signed multiplier, we add a '1' to column 8 (2^8) and column 15 (2^15).
    // 16'h8100 = 1000_0001_0000_0000 in binary.
    wire [15:0] bw_constant = 16'h8100;

    // -------------------------------------------------------------------------
    // Combinational Summation Tree
    // -------------------------------------------------------------------------
    // The synthesizer will automatically map this addition into a fast combinational 
    // adder tree (e.g., carry-lookahead or carry-save tree) without using the '*' operator.
    assign prod_out = pp0 + 
                      pp1 + 
                      pp2 + 
                      pp3 + 
                      pp4 + 
                      pp5 + 
                      pp6 + 
                      pp7 + 
                      bw_constant;

endmodule