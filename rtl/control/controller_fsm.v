module controller_fsm (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,           // Pulse to begin inference on an image
    output reg         load_weights,    // Enables weight loading into PEs
    output reg         stream_act,      // Enables streaming activations into skew logic
    output reg         accum_wen,       // Enables write-back to accumulator buffer
    output reg  [7:0]  k_tile_idx,      // 0 to 195 (tracks the 196 passes)
    output reg  [3:0]  n_tile_idx,      // Output neuron tile index (0 to 7 for 32 hidden neurons)
    output reg         layer_idx,       // 0 = Layer 1 (784->32), 1 = Layer 2 (32->10)
    output reg         done             // Pulse when inference completes
);