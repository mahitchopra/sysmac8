// rtl/core/skew_registers.v
`timescale 1ns / 1ps

module skew_registers (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               en,
    input  wire signed [7:0]  a_in_r0, // Row 0 input
    input  wire signed [7:0]  a_in_r1, // Row 1 input
    input  wire signed [7:0]  a_in_r2, // Row 2 input
    input  wire signed [7:0]  a_in_r3, // Row 3 input
    output wire signed [7:0]  a_out_r0,
    output wire signed [7:0]  a_out_r1,
    output wire signed [7:0]  a_out_r2,
    output wire signed [7:0]  a_out_r3
);
    // To ensure matching operands meet in the correct PE, each row of activation 
    // inputs must be delayed by one clock cycle more than the row above it.

    // Row 0: 0 cycle delay (passes straight through)
    assign a_out_r0 = a_in_r0;

    // Row 1: 1 cycle delay
    reg signed [7:0] r1_d1;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) r1_d1 <= 8'sd0;
        else if (en) r1_d1 <= a_in_r1;
    end
    assign a_out_r1 = r1_d1;

    // Row 2: 2 cycle delay
    reg signed [7:0] r2_d1, r2_d2;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin r2_d1 <= 8'sd0; r2_d2 <= 8'sd0; end
        else if (en) begin r2_d1 <= a_in_r2; r2_d2 <= r2_d1; end
    end
    assign a_out_r2 = r2_d2;

    // Row 3: 3 cycle delay
    reg signed [7:0] r3_d1, r3_d2, r3_d3;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin r3_d1 <= 8'sd0; r3_d2 <= 8'sd0; r3_d3 <= 8'sd0; end
        else if (en) begin r3_d1 <= a_in_r3; r3_d2 <= r3_d1; r3_d3 <= r3_d2; end
    end
    assign a_out_r3 = r3_d3;

endmodule