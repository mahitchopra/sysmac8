// rtl/core/systolic_grid_4x4.v
`timescale 1ns / 1ps

module systolic_grid_4x4 #(
    parameter ARCH = "BOOTH_WALLACE"
)(
    input  wire               clk,
    input  wire               rst_n,
    
    // Weight loading interface (Broadcast to columns, latched per row)
    input  wire [3:0]         weight_en_row,   // One-hot enable to load weights into a specific row
    input  wire signed [7:0]  w_in_c0, w_in_c1, w_in_c2, w_in_c3,
    
    // Activation inputs (Pre-skew)
    input  wire               skew_en,
    input  wire signed [7:0]  a_in_r0, a_in_r1, a_in_r2, a_in_r3,
    
    // Partial sum inputs (Top row feeds)
    input  wire signed [25:0] psum_in_c0, psum_in_c1, psum_in_c2, psum_in_c3,
    
    // Final partial sum outputs (Bottom row drops)
    output wire signed [25:0] psum_out_c0, psum_out_c1, psum_out_c2, psum_out_c3
);

    // -------------------------------------------------------------------------
    // 1. Skew Logic Instantiation
    // -------------------------------------------------------------------------
    wire signed [7:0] a_skewed [0:3];
    
    skew_registers u_skew (
        .clk(clk), .rst_n(rst_n), .en(skew_en),
        .a_in_r0(a_in_r0), .a_in_r1(a_in_r1), .a_in_r2(a_in_r2), .a_in_r3(a_in_r3),
        .a_out_r0(a_skewed[0]), .a_out_r1(a_skewed[1]), 
        .a_out_r2(a_skewed[2]), .a_out_r3(a_skewed[3])
    );

    // -------------------------------------------------------------------------
    // 2. The 4x4 PE Grid Wires
    // -------------------------------------------------------------------------
    // Wires passing activations rightward: [row][col]
    wire signed [7:0] a_wire [0:3][0:4]; 
    assign a_wire[0][0] = a_skewed[0];
    assign a_wire[1][0] = a_skewed[1];
    assign a_wire[2][0] = a_skewed[2];
    assign a_wire[3][0] = a_skewed[3];

    // Wires passing partial sums downward: [row][col]
    wire signed [25:0] p_wire [0:4][0:3]; 
    assign p_wire[0][0] = psum_in_c0;
    assign p_wire[0][1] = psum_in_c1;
    assign p_wire[0][2] = psum_in_c2;
    assign p_wire[0][3] = psum_in_c3;

    // Weight broadcast buses for each column
    wire signed [7:0] w_bus [0:3];
    assign w_bus[0] = w_in_c0;
    assign w_bus[1] = w_in_c1;
    assign w_bus[2] = w_in_c2;
    assign w_bus[3] = w_in_c3;

    // -------------------------------------------------------------------------
    // 3. Grid Generation
    // -------------------------------------------------------------------------
    genvar r, c;
    generate
        for (r = 0; r < 4; r = r + 1) begin : ROW
            for (c = 0; c < 4; c = c + 1) begin : COL
                pe #(
                    .ARCH(ARCH)
                ) u_pe (
                    .clk(clk),
                    .rst_n(rst_n),
                    .weight_en(weight_en_row[r]), // Latch weight if this row is enabled
                    .w_in(w_bus[c]),              // Weight from the column bus
                    .a_in(a_wire[r][c]),          // Activation from left neighbor
                    .psum_in(p_wire[r][c]),       // Psum from top neighbor
                    .a_out(a_wire[r][c+1]),       // Activation to right neighbor
                    .psum_out(p_wire[r+1][c])     // Psum to bottom neighbor
                );
            end
        end
    endgenerate

    // -------------------------------------------------------------------------
    // 4. Output Assignments
    // -------------------------------------------------------------------------
    assign psum_out_c0 = p_wire[4][0];
    assign psum_out_c1 = p_wire[4][1];
    assign psum_out_c2 = p_wire[4][2];
    assign psum_out_c3 = p_wire[4][3];

endmodule