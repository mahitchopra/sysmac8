// rtl/arithmetic/mult_booth_8x8.v
`timescale 1ns / 1ps

module mult_booth_8x8 #(
    parameter ARCH = "BOOTH_WALLACE" // Parameter for wrapper compatibility
)(
    input  wire signed [7:0]  a_in,
    input  wire signed [7:0]  b_in,
    output wire signed [15:0] prod_out
);

    // 1. Radix-4 Booth Encoding & Sign Extension
    // Base multiplicand values extended to 10 bits to prevent overflow when 
    // generating +2A or -2A.
    wire [9:0] a_val  = {a_in[7], a_in[7], a_in};       // +1A
    wire [9:0] a2_val = {a_in[7], a_in, 1'b0};          // +2A

    // 2. Partial Product Generation (4 Rows instead of 8)
    // Triplet 0: {b_in[1], b_in[0], 1'b0}
    wire [2:0] t0 = {b_in[1], b_in[0], 1'b0};
    wire [9:0] pp0_base = (t0 == 3'b001 || t0 == 3'b010) ?  a_val :
                          (t0 == 3'b011)                 ?  a2_val :
                          (t0 == 3'b100)                 ? ~a2_val :
                          (t0 == 3'b101 || t0 == 3'b110) ? ~a_val : 10'b0;
    wire neg0 = (t0 == 3'b100 || t0 == 3'b101 || t0 == 3'b110);
    wire [15:0] row0 = {{6{pp0_base[9]}}, pp0_base}; // Sign extend to 16 bits

    // Triplet 1: {b_in[3], b_in[2], b_in[1]}
    wire [2:0] t1 = b_in[3:1];
    wire [9:0] pp1_base = (t1 == 3'b001 || t1 == 3'b010) ?  a_val :
                          (t1 == 3'b011)                 ?  a2_val :
                          (t1 == 3'b100)                 ? ~a2_val :
                          (t1 == 3'b101 || t1 == 3'b110) ? ~a_val : 10'b0;
    wire neg1 = (t1 == 3'b100 || t1 == 3'b101 || t1 == 3'b110);
    wire [15:0] row1 = {{6{pp1_base[9]}}, pp1_base} << 2; // Shift by 2

    // Triplet 2: {b_in[5], b_in[4], b_in[3]}
    wire [2:0] t2 = b_in[5:3];
    wire [9:0] pp2_base = (t2 == 3'b001 || t2 == 3'b010) ?  a_val :
                          (t2 == 3'b011)                 ?  a2_val :
                          (t2 == 3'b100)                 ? ~a2_val :
                          (t2 == 3'b101 || t2 == 3'b110) ? ~a_val : 10'b0;
    wire neg2 = (t2 == 3'b100 || t2 == 3'b101 || t2 == 3'b110);
    wire [15:0] row2 = {{6{pp2_base[9]}}, pp2_base} << 4; // Shift by 4

    // Triplet 3: {b_in[7], b_in[7], b_in[6]} -> implicitly handles sign bit in Booth
    wire [2:0] t3 = b_in[7:5];
    wire [9:0] pp3_base = (t3 == 3'b001 || t3 == 3'b010) ?  a_val :
                          (t3 == 3'b011)                 ?  a2_val :
                          (t3 == 3'b100)                 ? ~a2_val :
                          (t3 == 3'b101 || t3 == 3'b110) ? ~a_val : 10'b0;
    wire neg3 = (t3 == 3'b100 || t3 == 3'b101 || t3 == 3'b110);
    wire [15:0] row3 = {{6{pp3_base[9]}}, pp3_base} << 6; // Shift by 6

    // Compensation Row: Adds the '+1' for two's complement of negative partial products
    // at the exact bit position corresponding to their left-shift amount.
    wire [15:0] row4 = {9'b0, neg3, 1'b0, neg2, 1'b0, neg1, 1'b0, neg0};

    // 3. Wallace Tree Reduction (Using 3:2 Compressors)
    // A 3:2 compressor acts as a bitwise full adder, reducing 3 rows to 2 rows 
    // (Sum and Carry) without waiting for horizontal carry propagation.
    
    // Level 1: Compress row0, row1, row2 -> save1, carry1
    wire [15:0] save1  = row0 ^ row1 ^ row2;
    wire [15:0] carry1 = ((row0 & row1) | (row1 & row2) | (row0 & row2)) << 1;

    // Level 2: Compress save1, carry1, row3 -> save2, carry2
    wire [15:0] save2  = save1 ^ carry1 ^ row3;
    wire [15:0] carry2 = ((save1 & carry1) | (carry1 & row3) | (save1 & row3)) << 1;

    // Level 3: Compress save2, carry2, row4 -> save3, carry3
    wire [15:0] save3  = save2 ^ carry2 ^ row4;
    wire [15:0] carry3 = ((save2 & carry2) | (carry2 & row4) | (save2 & row4)) << 1;

    // 4. Final Addition
    // The final two compressed rows are added together. Vivado synthesizes this 
    // into a fast Carry-Lookahead Adder (CLA).
    assign prod_out = save3 + carry3;

endmodule