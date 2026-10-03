module multiplier_top #(
    parameter string ARCH = "ARRAY"
)(
    input  wire signed [7:0] a_in,
    input  wire signed [7:0] b_in,
    output wire signed [15:0] prod_out
);

    mult_array_8x8 u_array (
        .a_in    (a_in),
        .b_in    (b_in),
        .prod_out(prod_out)
    );

endmodule