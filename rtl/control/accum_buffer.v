module accum_buffer (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               we,
    input  wire [2:0]         addr,       // 8 addresses (for 32 output neurons / 4 cols)
    input  wire signed [25:0] d_in_c0, d_in_c1, d_in_c2, d_in_c3,
    output reg  signed [25:0] q_out_c0, q_out_c1, q_out_c2, q_out_c3
);
    // 8 rows x (4 columns * 26 bits)
    reg signed [25:0] mem_c0 [0:7];
    reg signed [25:0] mem_c1 [0:7];
    reg signed [25:0] mem_c2 [0:7];
    reg signed [25:0] mem_c3 [0:7];

    integer i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < 8; i = i + 1) begin
                mem_c0[i] <= 26'sd0; mem_c1[i] <= 26'sd0;
                mem_c2[i] <= 26'sd0; mem_c3[i] <= 26'sd0;
            end
            q_out_c0 <= 26'sd0; q_out_c1 <= 26'sd0;
            q_out_c2 <= 26'sd0; q_out_c3 <= 26'sd0;
        end else begin
            if (we) begin
                mem_c0[addr] <= d_in_c0; mem_c1[addr] <= d_in_c1;
                mem_c2[addr] <= d_in_c2; mem_c3[addr] <= d_in_c3;
            end
            // Read is synchronous
            q_out_c0 <= mem_c0[addr]; q_out_c1 <= mem_c1[addr];
            q_out_c2 <= mem_c2[addr]; q_out_c3 <= mem_c3[addr];
        end
    end
endmodule