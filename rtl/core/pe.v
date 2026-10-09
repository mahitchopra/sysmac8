// rtl/core/pe.v
`timescale 1ns / 1ps

module pe #(
    parameter ARCH = "BOOTH_WALLACE"
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               weight_en,  // High to latch a new stationary weight
    input  wire signed [7:0]  w_in,       // Weight loading line from above
    input  wire signed [7:0]  a_in,       // Activation streaming from the left neighbor
    input  wire signed [25:0] psum_in,    // Partial sum streaming from the top neighbor
    output reg  signed [7:0]  a_out,      // Forwarded activation to the right neighbor
    output reg  signed [25:0] psum_out    // Forwarded partial sum to the bottom neighbor
);

    // 1. Stationary Weight Register
    // Each PE holds onto its specific weight during the entire tiling pass.
    reg signed [7:0] weight_reg;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            weight_reg <= 8'sd0;
        end else if (weight_en) begin
            weight_reg <= w_in;
        end
    end

    // 2. Multiplier Instantiation
    wire signed [15:0] mult_out;

    multiplier_top #(
        .ARCH(ARCH)
    ) u_mult (
        .a_in(a_in),
        .b_in(weight_reg),
        .prod_out(mult_out)
    );

    // 3. Accumulator Adder & Output Registers (1-Cycle Latency)
    // To maintain a pure systolic flow, activations and partial sums must move 
    // exactly one grid step per clock cycle. 
    wire signed [25:0] next_psum;
    
    // Combinational 26-bit addition (Vivado infers a fast adder here)
    assign next_psum = psum_in + mult_out;
    //makes the mult_out implicitly from 16 bits to 26 bits by padding the signed bit

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a_out    <= 8'sd0;
            psum_out <= 26'sd0;
        end else begin
            // Forward the activation rightward
            a_out    <= a_in;
            
            // Forward the accumulated sum downward
            psum_out <= next_psum;
        end
    end

endmodule