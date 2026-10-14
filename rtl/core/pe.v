// rtl/core/pe.v
`timescale 1ns / 1ps

module pe #(
    parameter ARCH = "BOOTH_WALLACE"
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               weight_en,
    input  wire               compute_en,
    input  wire signed [7:0]  w_in,
    input  wire signed [7:0]  a_in,
    input  wire signed [25:0] psum_in,
    output reg  signed [7:0]  a_out,
    output reg  signed [25:0] psum_out
);

    reg signed [7:0] weight_reg;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            weight_reg <= 8'sd0;
        else if (weight_en)
            weight_reg <= w_in;
    end

    wire signed [15:0] mult_out;

    multiplier_top #(
        .ARCH(ARCH)
    ) u_mult (
        .a_in(a_in),
        .b_in(weight_reg),
        .prod_out(mult_out)
    );

    wire signed [25:0] mult_ext =
        {{10{mult_out[15]}}, mult_out};

    wire signed [25:0] next_psum =
        compute_en ? (psum_in + mult_ext) : psum_in;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a_out    <= 8'sd0;
            psum_out <= 26'sd0;
        end else begin
            a_out    <= a_in;
            psum_out <= next_psum;
        end
    end

endmodule