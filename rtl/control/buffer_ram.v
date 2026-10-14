module buffer_ram #(
    parameter DATA_WIDTH = 8,
    parameter ADDR_WIDTH = 10
)(
    input  wire                  clk,
    input  wire                  we,
    input  wire [ADDR_WIDTH-1:0] waddr,
    input  wire [ADDR_WIDTH-1:0] raddr,
    input  wire [DATA_WIDTH-1:0] din,
    output reg  [DATA_WIDTH-1:0] dout
);
    // Infer Simple Dual-Port RAM
    reg [DATA_WIDTH-1:0] ram [0:(1<<ADDR_WIDTH)-1];

    always @(posedge clk) begin
        if (we)
            ram[waddr] <= din;
        dout <= ram[raddr];
    end
endmodule