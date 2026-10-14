module requantizer (
    input  wire signed [25:0] accum_in,
    input  wire        [4:0]  shift_val,
    output reg  signed [7:0]  act_out
);

    // Extend the accumulator before adding the rounding offset.
    // A 26-bit addition can overflow near ACC_MAX.
    wire signed [31:0] accum_ext =
        {{6{accum_in[25]}}, accum_in};

    // 32-bit signed rounding offset supports shift values 0..31.
    wire signed [31:0] round_add =
        (shift_val > 0)
        ? (32'sd1 <<< (shift_val - 1))
        : 32'sd0;

    wire signed [31:0] rounded =
        accum_ext + round_add;

    // Arithmetic right shift preserves the sign.
    wire signed [31:0] scaled =
        rounded >>> shift_val;

    // ReLU followed by saturation to [0, 127].
    always @(*) begin
        if (scaled < 0)
            act_out = 8'sd0;
        else if (scaled > 127)
            act_out = 8'sd127;
        else
            act_out = scaled[7:0];
    end

endmodule