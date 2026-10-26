# Independent verification rerun (25 Oct 2026)

The final repository was re-run from scratch on Linux to confirm the results in `FINAL_STATUS.md`
and to extend end-to-end RTL testing from 4 inputs to 300 real MNIST test images.

## Environment

| | This rerun | Team's runs |
| --- | --- | --- |
| Simulator | Icarus Verilog 12.0 | Icarus Verilog 13.0 |
| Testbench | cocotb 2.0.1 | cocotb 2.1.0 |
| OS | Linux | Windows, MSYS2 UCRT64 |

`model/golden_model.py` imports PyTorch, which was not installed for this rerun. The golden model uses PyTorch
only as an integer array library (nine operations: `tensor`, `as_tensor`, `any`, `argmax`, `equal`,
`bitwise_right_shift`, `roll`, `flip`, `clamp`), so a small NumPy stand-in provided those operations.
No repository code was changed. The golden model reproduced the documented sample logits exactly:
`[-2701, -3208, -1496, 3178, -8540, 4063, -4892, -2413, -3024, -1931]`, class 5.

## Results: the repository's own targets

All run with `make TEST=<target>` from `sim/`. Logs are in `logs/`.

| Target | Result |
| --- | --- |
| `multiplier_array` | PASS: 65,536 / 65,536 pairs |
| `multiplier_booth` | PASS: 65,536 / 65,536 pairs |
| `requantizer` | PASS: 579 cases |
| `pe` | PASS |
| `systolic` | PASS: 2 / 2 tests, 18 vector cases |
| `grid_mac` | PASS |
| `controller` | PASS: 25,495 cycles |
| `top` | PASS |
| `top_mac` | PASS |
| `k_tile_accum` | PASS: 2 / 2 tests |
| `layer1_golden` | PASS: 32 / 32 acc1, 32 / 32 act1 |
| `mnist_infer ARCH=BOOTH_WALLACE` | PASS: 4 / 4 bit-exact |
| `mnist_infer ARCH=ARRAY` | PASS: 4 / 4 bit-exact |

## New: 300 real MNIST test images through the RTL

`sim/tb_mnist_batch.py` (added) runs the first 300 images of the MNIST **test** set through `sysmac8_top`,
one after another, and compares every Layer 1 accumulator and activation, every logit and the predicted class
with `golden_model.py`. Pixels are quantized exactly as `model/quantize.py` does (`round(p / 255 × 128)`, clamped
to [0, 127]); this reproduces `model/data/sample_img.hex` bit for bit from MNIST training image 0.

```bash
cd sim
make TEST=mnist_infer ARCH=ARRAY COCOTB_TEST_MODULES=tb_mnist_batch \
     MNIST_DIR=/path/to/mnist MNIST_START=0 MNIST_COUNT=300 MNIST_OUT=rtl_results.json
```

`MNIST_DIR` must contain `t10k-images-idx3-ubyte.gz` and `t10k-labels-idx1-ubyte.gz`.

| Measure | Result |
| --- | --- |
| Images simulated | 300 (MNIST test indices 0–299), ARRAY multiplier |
| Bit-exact with `golden_model.py` | **300 / 300** (acc1, act1, acc2, pred_class) |
| RTL classified correctly | 291 / 300 (97.0%) |
| Golden model on the same 300 images | 291 / 300: identical predictions |
| Cycles per image (testbench monitor) | 25,496 |

Per-image results are in `rtl_mnist_300.csv`. The 9 misclassified images (index: label → predicted) are
8: 5→6, 33: 4→6, 38: 2→3, 92: 9→4, 233: 8→7, 241: 9→8, 247: 4→2, 259: 6→0, 290: 8→4. The RTL makes exactly the same
mistakes as the software model, which is what bit-exact agreement means.

97.0% is higher than the 95.13% full-test-set figure only because these 300 images are an easier sample; the
RTL and integer model agree on every image, so over all 10,000 images the RTL would reproduce 95.13%.

## Python figures, re-computed from the repository files

| Figure | Value | Source |
| --- | --- | --- |
| FP32 test accuracy | 95.12% (9,512 / 10,000) | `model.pth` |
| INT8 test accuracy | 95.13% (9,513 / 10,000) | `model/data/*.hex` |
| FP32 vs INT8 prediction agreement | 99.60% (40 disagreements) | both |
| Layer 1 accumulator range | [−304,192, +269,370] | all 10,000 test images |
| Layer 2 accumulator range | [−14,680, +9,276] | all 10,000 test images |
| Hidden values negative before ReLU | 99,646 / 320,000 (31.14%) | |
| Hidden values rounding to 0 | 10,375 / 320,000 (3.24%) | |
| Hidden values saturating at 127 | 0 | |

The hex weights were also checked to be exactly the INT8 quantization of `model.pth` (power-of-two scale 2⁻⁷).
The older Layer 1 range `[-76,972, +199,708]` previously quoted in `README.md` does not match these files and has
been corrected there.

## Not covered

Vivado synthesis (`syn/run_synth.tcl`) was not run: it needs a machine with Vivado. No area, timing or power
figures are claimed.
