# SysMAC8 — 4x4 Signed INT8 Systolic Array Neural Network Accelerator

**Repository:** `sysmac8-main` (run commands from your local repository clone)
**Target Network:** Quantized MNIST Classifier (`784 -> 32 -> ReLU -> 10 -> Argmax`)
**Toolchain:** Verilog-2001, Icarus Verilog / VVP 13.0, Cocotb 2.1.0, Python 3.14.0, PyTorch, Xilinx Vivado (batch synthesis)

## 1. Architecture Overview

SysMAC8 is a weight-stationary 4x4 signed INT8 systolic array accelerator executing tiled dense matrix-vector multiplication with 26-bit signed partial-sum accumulation, power-of-two requantization, on-chip inter-layer activation buffering, and streaming argmax classification:

- **Signed INT8 Multipliers (`rtl/arithmetic/`)**:
  - `mult_array_8x8.v`: Baugh-Wooley-style signed 8x8 -> 16-bit multiplier using inverted sign partial products and compensation constant `16'h8100`.
  - `mult_booth_8x8.v`: Radix-4 Booth recoder (4 partial products + sign correction row) with a 3-level 3:2 Wallace compressor tree.
  - `multiplier_top.v`: Parameterized wrapper selecting `ARCH = "ARRAY"` or `ARCH = "BOOTH_WALLACE"` via a `generate if` block.
- **Systolic Core & Requantizer (`rtl/core/`)**:
  - `pe.v`: Weight-stationary processing element with 8-bit weight register, combinational 8x8 multiplier, 26-bit signed partial-sum adder, registered rightward activation forwarding (`a_out`), and registered downward partial-sum forwarding (`psum_out`).
  - `skew_registers.v`: Staggered input delay registers (0, 1, 2, 3 clock cycles across rows 0-3) aligning operand wavefronts across the 4x4 grid.
  - `systolic_grid_4x4.v`: 4x4 PE array with `activation_en` input gating and row-wise weight broadcast (`weight_en_row`).
  - `requantizer.v`: Sign-extends `accum_in[25:0]` to 32 bits, adds rounding offset `1 << (shift_val - 1)`, performs arithmetic right shift, applies ReLU, and saturates to `[0, 127]`.
- **Control & On-Chip Buffers (`rtl/control/`)**:
  - `controller_fsm.v`: 7-state FSM (`IDLE`, `LOAD_W`, `STREAM`, `DRAIN`, `REQUANT`, `WRITEBACK`, `DONE_STATE`) sequencing 196 K-tiles x 8 N-tiles in Layer 1 (`layer_idx = 0`) and 8 K-tiles x 3 N-tiles in Layer 2 (`layer_idx = 1`) in **25,495 controller schedule cycles**; the end-to-end Cocotb monitor reports **25,496 cycles per image**.
  - `accum_buffer.v`: 8-row x 4-column x 26-bit signed accumulator buffer with write-first read bypass (`q_out <= d_in` when `we == 1`) so completed N-tile sums are immediately valid on `accum_q_c0..c3` during `REQUANT`/`WRITEBACK`.
  - `buffer_ram.v`: Parameterized simple dual-port synchronous RAM instantiated as 4 banks (`u_act_buf_r0..r3`, 8x8-bit each) in `sysmac8_top.v` to store the 32 Layer 1 requantized activations and feed them into Layer 2 automatically.
- **Top-Level Integration & Classification (`rtl/top/`)**:
  - `argmax.v`: Streaming signed 26-bit comparator across Layer 2's 3 N-tiles; masks out unused columns `c2, c3` on the final partial output tile (`n_tile_idx == 2`, classes 8 and 9 only) and outputs `pred_class[3:0]` and `max_logit[25:0]`.
  - `sysmac8_top.v`: Integrates the controller, 4x4 grid, K-tile partial-sum feedback mux (`(k_tile_idx == 0) ? psum_in : accum_q`), 4 parallel `requantizer` units (`requant_out_c0..c3`), 4 `buffer_ram` banks, and `argmax`.

## 2. Explicit 16-Cycle Tile Schedule

Each `(n_tile_idx, k_tile_idx)` tile runs for **16 clock cycles**:
1. **`LOAD_W` (4 cycles)**: `weight_en = 1`; `weight_en_row` steps `4'b0001 -> 4'b0010 -> 4'b0100 -> 4'b1000` to load 4 rows of 4 weights while `compute_en = 0` flushes horizontal `PE.a_out` registers.
2. **`STREAM` (8 cycles)**: `activation_en = 1, skew_en = 1, compute_en = 1`. Holds the tile's 4 activations and incoming partial sums steady (t = 0..7). On `k_tile_idx == 0`, `grid_psum_in_c0..c3` injects `psum_in_c0..c3` (bias added once); on `k_tile_idx > 0`, it feeds back `accum_q_c0..c3` from `u_accum_buffer`.
3. **`DRAIN` (4 cycles)**: `activation_en = 0, skew_en = 1, compute_en = 1`. Flushes `skew_registers` with zeros (t = 8..11) while valid waves from stream cycles t = 7, 6, 5, 4 align simultaneously at the bottom of columns c = 0, 1, 2, 3 at t = 11, captured by a single `accum_we` pulse.
4. **`REQUANT` & `WRITEBACK` (2 cycles after `last_k_tile`)**: `requant_en = 1` latches the 4 requantized Layer 1 activations into `u_act_buf_r0..r3[n_tile_idx]` (or updates `u_argmax` in Layer 2) before advancing `n_tile_idx`.

## 3. How to Run Simulations & Golden Model

### 3.1 Python Quantization & Golden Reference (PowerShell)
```powershell
# Run from the repository root
python -m model.golden_model
python model\evaluate_quantized.py
```

### 3.2 RTL & Cocotb Regression Suite (MSYS2 UCRT64)
```bash
export PATH="$(cygpath -u "$APPDATA")/Python/Python314/Scripts:$PATH"
cd sim  # run from the repository root in MSYS2 UCRT64

# Unit & multiplier architecture tests (both ARRAY and BOOTH_WALLACE)
make clean && make TEST=multiplier_array
make clean && make TEST=multiplier_booth
make clean && make TEST=requantizer
make clean && make TEST=pe

# Grid & controller tests
make clean && make TEST=systolic
make clean && make TEST=grid_mac
make clean && make TEST=controller
make clean && make TEST=top
make clean && make TEST=top_mac

# Stage 3: Multi-K-tile & multi-N-tile accumulation regression
make clean && make TEST=k_tile_accum

# Stage 4: Full Layer 1 (784->32) and full 2-layer MNIST inference vs golden_model.py
make clean && make TEST=layer1_golden
make clean && make TEST=mnist_infer ARCH=BOOTH_WALLACE
make clean && make TEST=mnist_infer ARCH=ARRAY
```

### 3.3 Vivado Synthesis Comparison (Stage 5)
```powershell
# Run from the repository root
vivado -mode batch -source syn/run_synth.tcl
```
The synthesis script has not yet been executed with Vivado. If both architecture runs complete successfully, reports should be generated under `syn/reports/`. No FPGA resource, timing, or power measurements have been established.

## 4. Verification Summary & Known Limitations

- **Software 10,000-Image MNIST Benchmark (`model/evaluate_quantized.py`)**: `95.12%` FP32 accuracy, `95.13%` INT8 quantized accuracy, `99.60%` prediction agreement (`40/10,000` disagreements), zero 26-bit accumulator overflows (`acc1` in `[-304,192, +269,370]`, `acc2` in `[-14,680, +9,276]`, re-computed from `model/data/*.hex` over all 10,000 test images).
- **Hardware RTL Bit-Exact Verification**:
  - `tb_multiplier.py`: `65,536 / 65,536` signed INT8 pairs passed on both `ARRAY` and `BOOTH_WALLACE`.
  - `tb_requantizer.py`: `579 / 579` cases passed across shifts `0..25`.
  - `tb_systolic.py` & `tb_grid_mac.py`: `18 / 18` directed matrix-vector cases and `3 * 4 + 10 = 22` deterministic MAC passed.
  - `tb_k_tile_accum.py`: 3-K-tile signed accumulation (`[22, -20, 7, 108] -> [40, -31, 21, 90] -> [40, -37, 9, 110]`) and 196-K-tile multi-address retention/requantization passed.
  - `tb_layer1_golden.py` & `tb_mnist_infer.py`: `100%` bit-exact match against `model/golden_model.py` across all 32 Layer 1 accumulators, 32 Layer 1 activations, 10 Layer 2 logits (`[-2701, -3208, -1496, 3178, -8540, 4063, -4892, -2413, -3024, -1931]`), and `pred_class = 5` (`max_logit = 4063`) on `sample_img.hex` and 3 additional test vectors (including partial-tile unused-column poisoning).
- **Independent rerun and 300-image RTL test** (`sim/tb_mnist_batch.py`): all targets re-run, and the first 300 MNIST test images run through `sysmac8_top` with 300 / 300 bit-exact against `golden_model.py` and 291 / 300 classified correctly. See `docs/verification_rerun/README.md`.
- **Known Limitations**:
  - Weights (`w1`, `w2`), biases (`b1`, `b2`), and Layer 1 input pixels stream across top-level buses indexed by `(layer_idx, n_tile_idx, k_tile_idx)` rather than being stored in a dedicated 75 KB on-chip weight ROM.
  - Each image is processed at batch size 1. The controller schedule is documented as 25,495 FSM cycles, while the end-to-end Cocotb monitor reports 25,496 cycles per image.
