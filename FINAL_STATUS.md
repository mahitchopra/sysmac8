# SysMAC8 — Final Engineering Status & Viva Handover (`FINAL_STATUS.md`)

## 1. Completed Work Summary

| Milestone | Subsystem / Files | Verification Target | Result & Evidence |
| :--- | :--- | :--- | :--- |
| **Stage 1** | `mult_array_8x8.v`, `mult_booth_8x8.v`, `multiplier_top.v` | `make TEST=multiplier_array`<br>`make TEST=multiplier_booth` | **PASS**: 65,536 / 65,536 signed INT8 operand pairs (`[-128, 127]^2`) verified bit-exact for both architectures. |
| **Stage 2** | `pe.v`, `skew_registers.v`, `systolic_grid_4x4.v`, `requantizer.v` | `make TEST=pe`<br>`make TEST=requantizer`<br>`make TEST=systolic`<br>`make TEST=grid_mac` | **PASS**: PE MAC/hold checks, 579 requantizer boundary/random cases, 18 signed tile x vector grid cases, and `3*4+10 = 22` grid MAC passed. |
| **Stage 3** | `controller_fsm.v`, `accum_buffer.v`, `buffer_ram.v`, `sysmac8_top.v` | `make TEST=controller`<br>`make TEST=top`<br>`make TEST=top_mac`<br>`make TEST=k_tile_accum` | **PASS**: 25,495-cycle schedule, top-level MAC (`22`), 3-K-tile signed accumulation (`[22,-20,7,108] -> [40,-31,21,90] -> [40,-37,9,110]`), and 196-K-tile multi-address requantization passed. |
| **Stage 4** | `argmax.v`, `sysmac8_top.v`, `tb_layer1_golden.py`, `tb_mnist_infer.py` | `make TEST=layer1_golden`<br>`make TEST=mnist_infer` | **PASS**: 100% bit-exact match vs. `model/golden_model.py` across all 32 `acc1`, 32 `act1`, 10 `acc2` logits, and `pred_class` on 4 test images (101,984 total cycles). |
| **Stage 5** | `syn/run_synth.tcl` | `vivado -mode batch -source syn/run_synth.tcl` | **Script Ready**: Automated non-project Vivado batch script written to synthesize `ARRAY` vs. `BOOTH_WALLACE` with `-max_dsp 0` and 100 MHz clock constraints. |

## 2. Resolution of Historical & Stage 3/4 Engineering Defects

1. **Historical Top-Level MAC Discrepancy (`Expected 22, Observed 10`)**:
   - **Root Cause**: `controller_fsm.v` registers `weight_en`, introducing a 1-cycle latency before `sysmac8_top.v` asserts `weight_en_row = 4'b0001, 0010, 0100, 1000`. Driving `w_in_c0 = 3` only before `weight_en` asserted left `PE[0][0].weight_reg = 0`, computing `0 * 4 + 10 = 10` instead of `3 * 4 + 10 = 22`.
   - **Resolution**: Synchronizing weight broadcast to `weight_en` / `weight_en_row` in `tb_top_mac.py` (and all subsequent testbenches) loads `[3, 0, 0, 0]` into Row 0 and produces `22` deterministically.
2. **Multi-K-Tile Accumulation & Single-Bias Seeding (`sysmac8_top.v`)**:
   - **Root Cause**: `u_accum_buffer` was unconnected to `accum_we` and `n_tile_idx`, and `u_grid.psum_in_c0..c3` did not feed back `accum_q_c0..c3`.
   - **Resolution**: Added `grid_psum_in_c0..c3 = (k_tile_idx == 8'd0) ? psum_in_c0..c3 : accum_q_c0..c3` and connected `accum_we_mux = accum_buf_we | accum_we` and `accum_addr_mux = accum_buf_we ? accum_buf_addr : (ctrl_busy ? n_tile_idx[2:0] : accum_buf_addr)`.
3. **Final K-Tile (`k_tile_idx == 195`) Read-After-Write Latency Bug (`accum_buffer.v`)**:
   - **Root Cause**: `accum_we` asserts on the `REQUANT` state cycle and `requant_en` asserts on the immediately following `WRITEBACK` cycle. A read-first synchronous `accum_buffer` caused `accum_q_c0..c3` during `requant_en == 1` to output the stale sum from `k = 194` (dropping `k = 195`).
   - **Resolution**: Added write-first read bypass (`if (we) q_out <= d_in; else q_out <= mem[addr];`) in `accum_buffer.v`.
4. **Layer 1 -> Layer 2 Activation Handoff & Partial Output Tile Masking (`sysmac8_top.v`, `argmax.v`)**:
   - **Root Cause**: Layer 1 produces 4 columns per N-tile across 8 `requant_en` pulses and transitions directly to Layer 2; Layer 2's final output tile (`n_tile_idx == 2`) has only 2 valid neurons (classes 8 and 9).
   - **Resolution**: Instantiated 4 parallel `requantizer` units (`requant_out_c0..c3`) feeding 4 `buffer_ram` banks (`u_act_buf_r0..r3`) for automatic Layer 2 readout, and implemented `argmax.v` with `if (tile_idx != 2'd2)` column masking on `c2, c3`.

## 3. Bit-Exact RTL vs. Python Golden Model Results (`sample_img.hex`)

- **Layer 1 Accumulators (`acc1[0..31]`, signed 26-bit)**:
  `[53244, 23672, 31931, 125391, -12197, 46183, -2059, 103115, 57644, 79207, -7274, -26492, 42507, 49907, 23627, 80892, 39395, 144458, -12890, 21391, 75010, 57066, -3190, 65735, -4067, -58344, 15177, -32519, 40858, -2011, 61970, 37552]` (RTL == Golden, **0 mismatches**).
- **Layer 1 Requantized Activations (`act1[0..31]`, INT8 `[0, 127]`, `shift_val = 12`)**:
  `[13, 6, 8, 31, 0, 11, 0, 25, 14, 19, 0, 0, 10, 12, 6, 20, 10, 35, 0, 5, 18, 14, 0, 16, 0, 0, 4, 0, 10, 0, 15, 9]` (RTL == Golden, **0 mismatches**).
- **Layer 2 Final Integer Logits (`acc2[0..9]`, signed 26-bit)**:
  `[-2701, -3208, -1496, 3178, -8540, 4063, -4892, -2413, -3024, -1931]` (RTL == Golden, **0 mismatches**).
- **Predicted Class & Winning Score**: `pred_class = 5`, `max_logit = 4063` after `25,495` clock cycles.

## 4. Exact Reproduction Commands

```bash
# In MSYS2 UCRT64 terminal:
export PATH="/c/Users/chopr/sysmac8/.venv/Scripts:$PATH"
cd /c/Users/chopr/sysmac8/sim

make clean && make TEST=multiplier_array
make clean && make TEST=multiplier_booth
make clean && make TEST=requantizer
make clean && make TEST=pe
make clean && make TEST=systolic
make clean && make TEST=grid_mac
make clean && make TEST=controller
make clean && make TEST=top
make clean && make TEST=top_mac
make clean && make TEST=k_tile_accum
make clean && make TEST=layer1_golden
make clean && make TEST=mnist_infer ARCH=BOOTH_WALLACE
make clean && make TEST=mnist_infer ARCH=ARRAY
```

## 5. Remaining Items & Honest Viva Boundaries

- **Software vs. Hardware Sample Count**: The `95.12%` FP32 / `95.13%` INT8 accuracy figures across 10,000 MNIST test images are from the Python integer evaluation (`model/evaluate_quantized.py`). In cycle-accurate RTL simulation (`25,495` cycles/image), 4 full 784-pixel images (`101,984` cycles) have been verified bit-for-bit with `0` mismatches.
- **Vivado Synthesis Execution**: `syn/run_synth.tcl` is complete and ready to run on a machine with Xilinx Vivado installed (`vivado -mode batch -source syn/run_synth.tcl`). Do not quote LUT/FF/MHz/W numbers until `syn/reports/` is generated by Vivado.
