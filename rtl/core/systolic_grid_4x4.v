// rtl/core/systolic_grid_4x4.v
`timescale 1ns / 1ps

module systolic_grid_4x4 #(
    parameter ARCH = "BOOTH_WALLACE"
)(
    input  wire               clk,
    input  wire               rst_n,

    // Weight loading: one-hot row enable
    input  wire [3:0]         weight_en_row,
    input  wire signed [7:0]  w_in_c0,
    input  wire signed [7:0]  w_in_c1,
    input  wire signed [7:0]  w_in_c2,
    input  wire signed [7:0]  w_in_c3,

    // Activation pipeline controls
    input  wire               skew_en,
    input  wire               activation_en,
    input  wire               compute_en,

    // Activations before skewing
    input  wire signed [7:0]  a_in_r0,
    input  wire signed [7:0]  a_in_r1,
    input  wire signed [7:0]  a_in_r2,
    input  wire signed [7:0]  a_in_r3,

    // Partial sums entering the top
    input  wire signed [25:0] psum_in_c0,
    input  wire signed [25:0] psum_in_c1,
    input  wire signed [25:0] psum_in_c2,
    input  wire signed [25:0] psum_in_c3,

    // Partial sums leaving the bottom
    output wire signed [25:0] psum_out_c0,
    output wire signed [25:0] psum_out_c1,
    output wire signed [25:0] psum_out_c2,
    output wire signed [25:0] psum_out_c3
);

    // 1. Prevent invalid external activations from entering.
    wire signed [7:0] a_valid_r0 =
        activation_en ? a_in_r0 : 8'sd0;

    wire signed [7:0] a_valid_r1 =
        activation_en ? a_in_r1 : 8'sd0;

    wire signed [7:0] a_valid_r2 =
        activation_en ? a_in_r2 : 8'sd0;

    wire signed [7:0] a_valid_r3 =
        activation_en ? a_in_r3 : 8'sd0;

    // 2. Activation skewing
    wire signed [7:0] a_skewed [0:3];

    skew_registers u_skew (
        .clk      (clk),
        .rst_n    (rst_n),
        .en       (skew_en),

        .a_in_r0  (a_valid_r0),
        .a_in_r1  (a_valid_r1),
        .a_in_r2  (a_valid_r2),
        .a_in_r3  (a_valid_r3),

        .a_out_r0 (a_skewed[0]),
        .a_out_r1 (a_skewed[1]),
        .a_out_r2 (a_skewed[2]),
        .a_out_r3 (a_skewed[3])
    );

    // 3. Inter-PE wires
    wire signed [7:0] a_wire [0:3][0:4];
    wire signed [25:0] p_wire [0:4][0:3];

    assign a_wire[0][0] = a_skewed[0];
    assign a_wire[1][0] = a_skewed[1];
    assign a_wire[2][0] = a_skewed[2];
    assign a_wire[3][0] = a_skewed[3];

    assign p_wire[0][0] = psum_in_c0;
    assign p_wire[0][1] = psum_in_c1;
    assign p_wire[0][2] = psum_in_c2;
    assign p_wire[0][3] = psum_in_c3;

    wire signed [7:0] w_bus [0:3];

    assign w_bus[0] = w_in_c0;
    assign w_bus[1] = w_in_c1;
    assign w_bus[2] = w_in_c2;
    assign w_bus[3] = w_in_c3;

    // 4. Generate the 4x4 PE array
    genvar r, c;

    generate
        for (r = 0; r < 4; r = r + 1) begin : ROW
            for (c = 0; c < 4; c = c + 1) begin : COL

                pe #(
                    .ARCH(ARCH)
                ) u_pe (
                    .clk        (clk),
                    .rst_n      (rst_n),

                    .weight_en  (weight_en_row[r]),
                    .compute_en (compute_en),

                    .w_in       (w_bus[c]),
                    .a_in       (a_wire[r][c]),
                    .psum_in    (p_wire[r][c]),

                    .a_out      (a_wire[r][c+1]),
                    .psum_out   (p_wire[r+1][c])
                );

            end
        end
    endgenerate


    // 5. Outputs
    assign psum_out_c0 = p_wire[4][0];
    assign psum_out_c1 = p_wire[4][1];
    assign psum_out_c2 = p_wire[4][2];
    assign psum_out_c3 = p_wire[4][3];

endmodule