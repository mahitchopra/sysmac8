// rtl/control/controller_fsm.v
`timescale 1ns / 1ps

module controller_fsm (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       start,

    output reg        weight_en,
    output reg        skew_en,
    output reg        activation_en,
    output reg        compute_en,
    output reg        accum_we,
    output reg        requant_en,

    output reg [7:0]  k_tile_idx,
    output reg [3:0]  n_tile_idx,
    output reg        layer_idx,
    output reg        done
);

    localparam IDLE       = 3'd0;
    localparam LOAD_W     = 3'd1;
    localparam STREAM     = 3'd2;
    localparam DRAIN      = 3'd3;
    localparam REQUANT    = 3'd4;
    localparam WRITEBACK  = 3'd5;
    localparam DONE_STATE = 3'd6;

    reg [2:0] state;
    reg [3:0] cycle_count;

    wire [7:0] last_k_tile =
        (layer_idx == 1'b0) ? 8'd195 : 8'd7;

    wire [3:0] last_n_tile =
        (layer_idx == 1'b0) ? 4'd7 : 4'd2;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= IDLE;
            cycle_count   <= 0;
            k_tile_idx    <= 0;
            n_tile_idx    <= 0;
            layer_idx     <= 0;

            weight_en     <= 0;
            skew_en       <= 0;
            activation_en <= 0;
            compute_en    <= 0;
            accum_we      <= 0;
            requant_en    <= 0;
            done          <= 0;
        end else begin
            weight_en     <= 0;
            skew_en       <= 0;
            activation_en <= 0;
            compute_en    <= 0;
            accum_we      <= 0;
            requant_en    <= 0;
            done          <= 0;

            case (state)
                IDLE: begin
                    cycle_count <= 0;

                    if (start) begin
                        k_tile_idx <= 0;
                        n_tile_idx <= 0;
                        layer_idx  <= 0;
                        state      <= LOAD_W;
                    end
                end

                LOAD_W: begin
                    weight_en <= 1;

                    if (cycle_count == 4'd3) begin
                        cycle_count <= 0;
                        state <= STREAM;
                    end else begin
                        cycle_count <= cycle_count + 1'b1;
                    end
                end

                STREAM: begin
                    skew_en       <= 1;
                    activation_en <= 1;
                    compute_en    <= 1;

                    if (cycle_count == 4'd7) begin
                        cycle_count <= 0;
                        state <= DRAIN;
                    end else begin
                        cycle_count <= cycle_count + 1'b1;
                    end
                end

                DRAIN: begin
                    // Advance the pipeline, but inject no new activations.
                    skew_en    <= 1;
                    compute_en <= 1;

                    if (cycle_count == 4'd3) begin
                        cycle_count <= 0;
                        accum_we <= 1;

                        if (k_tile_idx == last_k_tile) begin
                            state <= REQUANT;
                        end else begin
                            k_tile_idx <= k_tile_idx + 1'b1;
                            state <= LOAD_W;
                        end
                    end else begin
                        cycle_count <= cycle_count + 1'b1;
                    end
                end

                REQUANT: begin
                    requant_en <= 1;
                    state <= WRITEBACK;
                end

                WRITEBACK: begin
                    if (n_tile_idx == last_n_tile) begin
                        if (layer_idx == 1'b0) begin
                            layer_idx  <= 1'b1;
                            n_tile_idx <= 0;
                            k_tile_idx <= 0;
                            state      <= LOAD_W;
                        end else begin
                            state <= DONE_STATE;
                        end
                    end else begin
                        n_tile_idx <= n_tile_idx + 1'b1;
                        k_tile_idx <= 0;
                        state <= LOAD_W;
                    end
                end

                DONE_STATE: begin
                    done <= 1;
                    state <= IDLE;
                end

                default: begin
                    state <= IDLE;
                    cycle_count <= 0;
                end
            endcase
        end
    end

endmodule