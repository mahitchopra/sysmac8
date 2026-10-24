// WRAPPER MODULE
module multiplier_top #(
    `ifdef SYSMAC8_ARCH_ARRAY
    parameter ARCH = "ARRAY"
`elsif SYSMAC8_ARCH_BOOTH_WALLACE
    parameter ARCH = "BOOTH_WALLACE"
`else
    parameter ARCH = "ARRAY"
`endif
)(
    input  wire signed [7:0]  a_in,
    input  wire signed [7:0]  b_in,
    output wire signed [15:0] prod_out
);

    generate
        if (ARCH == "ARRAY") begin : gen_array

            mult_array_8x8 u_array (
                .a_in     (a_in),
                .b_in     (b_in),
                .prod_out (prod_out)
            );

        end else if (ARCH == "BOOTH_WALLACE") begin : gen_booth

            mult_booth_8x8 u_booth (
                .a_in     (a_in),
                .b_in     (b_in),
                .prod_out (prod_out)
            );

        end else begin : gen_invalid
            // Invalid architecture: drive output to zero.
            assign prod_out = 16'sd0;
        end
    endgenerate

endmodule
