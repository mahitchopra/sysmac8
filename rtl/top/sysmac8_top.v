// rtl/top/sysmac8_top.v
`timescale 1ns / 1ps

module sysmac8_top #(
    parameter ARCH = "BOOTH_WALLACE"
)(
    input  wire clk,
    input  wire rst_n,
    input  wire start,

    // Weight inputs, broadcast to grid columns
    input  wire signed [7:0] w_in_c0,
    input  wire signed [7:0] w_in_c1,
    input  wire signed [7:0] w_in_c2,
    input  wire signed [7:0] w_in_c3,

    // Activation inputs
    input  wire signed [7:0] a_in_r0,
    input  wire signed [7:0] a_in_r1,
    input  wire signed [7:0] a_in_r2,
    input  wire signed [7:0] a_in_r3,

    // Partial-sum inputs
    input  wire signed [25:0] psum_in_c0,
    input  wire signed [25:0] psum_in_c1,
    input  wire signed [25:0] psum_in_c2,
    input  wire signed [25:0] psum_in_c3,

    // Requantizer inputs
    input  wire [4:0] shift_val,
    input  wire signed [25:0] requant_in,

    // Accumulator buffer interface
    input  wire accum_buf_we,
    input  wire [2:0] accum_buf_addr,

    // Grid outputs
    output wire signed [25:0] psum_out_c0,
    output wire signed [25:0] psum_out_c1,
    output wire signed [25:0] psum_out_c2,
    output wire signed [25:0] psum_out_c3,

    // Buffer outputs
    output wire signed [25:0] accum_q_c0,
    output wire signed [25:0] accum_q_c1,
    output wire signed [25:0] accum_q_c2,
    output wire signed [25:0] accum_q_c3,

    // Requantized activation
    output wire signed [7:0] requant_out,

    // Controller outputs
    output wire done,
    output wire weight_en,
    output wire skew_en,
    output wire activation_en,
    output wire compute_en,
    output wire accum_we,
    output wire requant_en,
    output wire [7:0] k_tile_idx,
    output wire [3:0] n_tile_idx,
    output wire layer_idx
);

    // Controller
    controller_fsm u_controller (
        .clk           (clk),
        .rst_n         (rst_n),
        .start         (start),

        .weight_en     (weight_en),
        .skew_en       (skew_en),
        .activation_en (activation_en),
        .compute_en    (compute_en),
        .accum_we      (accum_we),
        .requant_en    (requant_en),

        .k_tile_idx    (k_tile_idx),
        .n_tile_idx    (n_tile_idx),
        .layer_idx     (layer_idx),
        .done          (done)
    );

    // One-hot weight-row selector
    reg [1:0] weight_row_idx;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            weight_row_idx <= 2'd0;
        else if (!weight_en)
            weight_row_idx <= 2'd0;
        else
            weight_row_idx <= weight_row_idx + 1'b1;
    end

    wire [3:0] weight_en_row =
        weight_en ? (4'b0001 << weight_row_idx) : 4'b0000;

    // Systolic grid
    systolic_grid_4x4 #(
        .ARCH(ARCH)
    ) u_grid (
        .clk           (clk),
        .rst_n         (rst_n),

        .weight_en_row (weight_en_row),
        .w_in_c0       (w_in_c0),
        .w_in_c1       (w_in_c1),
        .w_in_c2       (w_in_c2),
        .w_in_c3       (w_in_c3),

        .skew_en       (skew_en),
        .activation_en (activation_en),
        .compute_en    (compute_en),

        .a_in_r0       (a_in_r0),
        .a_in_r1       (a_in_r1),
        .a_in_r2       (a_in_r2),
        .a_in_r3       (a_in_r3),

        .psum_in_c0    (psum_in_c0),
        .psum_in_c1    (psum_in_c1),
        .psum_in_c2    (psum_in_c2),
        .psum_in_c3    (psum_in_c3),

        .psum_out_c0   (psum_out_c0),
        .psum_out_c1   (psum_out_c1),
        .psum_out_c2   (psum_out_c2),
        .psum_out_c3   (psum_out_c3)
    );

    // Accumulator buffer
    accum_buffer u_accum_buffer (
        .clk      (clk),
        .rst_n    (rst_n),
        .we       (accum_buf_we),
        .addr     (accum_buf_addr),

        .d_in_c0  (psum_out_c0),
        .d_in_c1  (psum_out_c1),
        .d_in_c2  (psum_out_c2),
        .d_in_c3  (psum_out_c3),

        .q_out_c0 (accum_q_c0),
        .q_out_c1 (accum_q_c1),
        .q_out_c2 (accum_q_c2),
        .q_out_c3 (accum_q_c3)
    );

    // Requantizer
    requantizer u_requantizer (
        .accum_in  (requant_in),
        .shift_val (shift_val),
        .act_out   (requant_out)
    );

endmodule