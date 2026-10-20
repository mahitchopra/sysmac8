// rtl/top/argmax.v
`timescale 1ns / 1ps

module argmax (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               clear,
    input  wire               en,
    input  wire [1:0]         tile_idx,
    input  wire signed [25:0] score_c0,
    input  wire signed [25:0] score_c1,
    input  wire signed [25:0] score_c2,
    input  wire signed [25:0] score_c3,
    output reg  [3:0]         max_class,
    output reg  signed [25:0] max_score
);

    wire [3:0] base_idx = {tile_idx, 2'b00};

    reg signed [25:0] tile_best_score;
    reg [3:0]         tile_best_class;

    // Select max across valid lanes in current N-tile.
    // Tile 2 only has 2 valid outputs (classes 8 and 9); c2/c3 are unused.
    always @(*) begin
        tile_best_score = score_c0;
        tile_best_class = base_idx;

        if (score_c1 > tile_best_score) begin
            tile_best_score = score_c1;
            tile_best_class = base_idx + 4'd1;
        end

        if (tile_idx != 2'd2) begin
            if (score_c2 > tile_best_score) begin
                tile_best_score = score_c2;
                tile_best_class = base_idx + 4'd2;
            end
            if (score_c3 > tile_best_score) begin
                tile_best_score = score_c3;
                tile_best_class = base_idx + 4'd3;
            end
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            max_class <= 4'd0;
            max_score <= -26'sd33554432;
        end else if (clear) begin
            max_class <= 4'd0;
            max_score <= -26'sd33554432;
        end else if (en) begin
            if (tile_idx == 2'd0 || tile_best_score > max_score) begin
                max_class <= tile_best_class;
                max_score <= tile_best_score;
            end
        end
    end

endmodule
