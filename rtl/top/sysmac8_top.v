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

    // Partial-sum inputs (bias on k_tile_idx == 0)
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

    // Requantized activations
    output wire signed [7:0] requant_out,
    output wire signed [7:0] requant_out_c0,
    output wire signed [7:0] requant_out_c1,
    output wire signed [7:0] requant_out_c2,
    output wire signed [7:0] requant_out_c3,

    // Argmax outputs
    output wire [3:0]         pred_class,
    output wire signed [25:0] max_logit,

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

    // Track when FSM is actively running a schedule
    reg ctrl_busy;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            ctrl_busy <= 1'b0;
        else if (start)
            ctrl_busy <= 1'b1;
        else if (done)
            ctrl_busy <= 1'b0;
    end

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

    // Layer 1 -> Layer 2 activation buffer (4 banks x 8 tiles = 32 INT8 activations)
    wire [7:0] act_buf_dout_r0;
    wire [7:0] act_buf_dout_r1;
    wire [7:0] act_buf_dout_r2;
    wire [7:0] act_buf_dout_r3;

    wire act_buf_we = ctrl_busy & (layer_idx == 1'b0) & requant_en;

    buffer_ram #(
        .DATA_WIDTH(8),
        .ADDR_WIDTH(3)
    ) u_act_buf_r0 (
        .clk   (clk),
        .we    (act_buf_we),
        .waddr (n_tile_idx[2:0]),
        .raddr (k_tile_idx[2:0]),
        .din   (requant_out_c0),
        .dout  (act_buf_dout_r0)
    );

    buffer_ram #(
        .DATA_WIDTH(8),
        .ADDR_WIDTH(3)
    ) u_act_buf_r1 (
        .clk   (clk),
        .we    (act_buf_we),
        .waddr (n_tile_idx[2:0]),
        .raddr (k_tile_idx[2:0]),
        .din   (requant_out_c1),
        .dout  (act_buf_dout_r1)
    );

    buffer_ram #(
        .DATA_WIDTH(8),
        .ADDR_WIDTH(3)
    ) u_act_buf_r2 (
        .clk   (clk),
        .we    (act_buf_we),
        .waddr (n_tile_idx[2:0]),
        .raddr (k_tile_idx[2:0]),
        .din   (requant_out_c2),
        .dout  (act_buf_dout_r2)
    );

    buffer_ram #(
        .DATA_WIDTH(8),
        .ADDR_WIDTH(3)
    ) u_act_buf_r3 (
        .clk   (clk),
        .we    (act_buf_we),
        .waddr (n_tile_idx[2:0]),
        .raddr (k_tile_idx[2:0]),
        .din   (requant_out_c3),
        .dout  (act_buf_dout_r3)
    );

    // Use external activations in Layer 1; use buffered Layer 1 activations in Layer 2
    wire signed [7:0] grid_a_in_r0 = (ctrl_busy && layer_idx == 1'b1) ? $signed(act_buf_dout_r0) : a_in_r0;
    wire signed [7:0] grid_a_in_r1 = (ctrl_busy && layer_idx == 1'b1) ? $signed(act_buf_dout_r1) : a_in_r1;
    wire signed [7:0] grid_a_in_r2 = (ctrl_busy && layer_idx == 1'b1) ? $signed(act_buf_dout_r2) : a_in_r2;
    wire signed [7:0] grid_a_in_r3 = (ctrl_busy && layer_idx == 1'b1) ? $signed(act_buf_dout_r3) : a_in_r3;

    // Seed with bias (psum_in) on K-tile 0; feed back running sum from accum_buffer on K-tile > 0
    wire signed [25:0] grid_psum_in_c0 = (k_tile_idx == 8'd0) ? psum_in_c0 : accum_q_c0;
    wire signed [25:0] grid_psum_in_c1 = (k_tile_idx == 8'd0) ? psum_in_c1 : accum_q_c1;
    wire signed [25:0] grid_psum_in_c2 = (k_tile_idx == 8'd0) ? psum_in_c2 : accum_q_c2;
    wire signed [25:0] grid_psum_in_c3 = (k_tile_idx == 8'd0) ? psum_in_c3 : accum_q_c3;

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

        .a_in_r0       (grid_a_in_r0),
        .a_in_r1       (grid_a_in_r1),
        .a_in_r2       (grid_a_in_r2),
        .a_in_r3       (grid_a_in_r3),

        .psum_in_c0    (grid_psum_in_c0),
        .psum_in_c1    (grid_psum_in_c1),
        .psum_in_c2    (grid_psum_in_c2),
        .psum_in_c3    (grid_psum_in_c3),

        .psum_out_c0   (psum_out_c0),
        .psum_out_c1   (psum_out_c1),
        .psum_out_c2   (psum_out_c2),
        .psum_out_c3   (psum_out_c3)
    );

    // Accumulator buffer muxing: allow manual access when idle, controller access when running
    wire       accum_we_mux   = accum_buf_we | accum_we;
    wire [2:0] accum_addr_mux = accum_buf_we ? accum_buf_addr :
                                (ctrl_busy   ? n_tile_idx[2:0] : accum_buf_addr);

    accum_buffer u_accum_buffer (
        .clk      (clk),
        .rst_n    (rst_n),
        .we       (accum_we_mux),
        .addr     (accum_addr_mux),

        .d_in_c0  (psum_out_c0),
        .d_in_c1  (psum_out_c1),
        .d_in_c2  (psum_out_c2),
        .d_in_c3  (psum_out_c3),

        .q_out_c0 (accum_q_c0),
        .q_out_c1 (accum_q_c1),
        .q_out_c2 (accum_q_c2),
        .q_out_c3 (accum_q_c3)
    );

    // Requantizers for all 4 columns (c0 muxes external requant_in when idle for standalone test)
    wire signed [25:0] req_in_c0 = (ctrl_busy && requant_en) ? accum_q_c0 : requant_in;

    requantizer u_requantizer (
        .accum_in  (req_in_c0),
        .shift_val (shift_val),
        .act_out   (requant_out_c0)
    );

    requantizer u_requant_c1 (
        .accum_in  (accum_q_c1),
        .shift_val (shift_val),
        .act_out   (requant_out_c1)
    );

    requantizer u_requant_c2 (
        .accum_in  (accum_q_c2),
        .shift_val (shift_val),
        .act_out   (requant_out_c2)
    );

    requantizer u_requant_c3 (
        .accum_in  (accum_q_c3),
        .shift_val (shift_val),
        .act_out   (requant_out_c3)
    );

    assign requant_out = requant_out_c0;

    // Layer 2 output argmax tracker
    argmax u_argmax (
        .clk       (clk),
        .rst_n     (rst_n),
        .clear     (start),
        .en        (ctrl_busy & (layer_idx == 1'b1) & requant_en),
        .tile_idx  (n_tile_idx[1:0]),
        .score_c0  (accum_q_c0),
        .score_c1  (accum_q_c1),
        .score_c2  (accum_q_c2),
        .score_c3  (accum_q_c3),
        .max_class (pred_class),
        .max_score (max_logit)
    );

endmodule
