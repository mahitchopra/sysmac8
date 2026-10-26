"""
Batch end-to-end check: run many real MNIST test images through sysmac8_top
and compare every intermediate value with model/golden_model.py.

Run (from sim/):
  make TEST=mnist_infer ARCH=ARRAY COCOTB_TEST_MODULES=tb_mnist_batch \
       MNIST_DIR=/path/to/mnist MNIST_START=0 MNIST_COUNT=100 MNIST_OUT=rtl_results.json

MNIST_DIR must contain t10k-images-idx3-ubyte.gz and t10k-labels-idx1-ubyte.gz.
Pixels are quantized exactly as model/quantize.py does: round(p / 255 * 128),
clamped to [0, 127] (input exponent -7).
"""
import gzip
import json
import os
from pathlib import Path
import sys

import numpy as np
import cocotb
from cocotb.triggers import Timer

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from model.golden_model import DATA_DIR, load_parameters, load_shift, infer_integer  # noqa: E402
from tb_mnist_infer import run_single_image_inference  # noqa: E402


def load_mnist_test(mnist_dir):
    d = Path(mnist_dir)
    imgs = np.frombuffer(gzip.open(d / "t10k-images-idx3-ubyte.gz").read(), np.uint8, offset=16).reshape(-1, 784)
    labels = np.frombuffer(gzip.open(d / "t10k-labels-idx1-ubyte.gz").read(), np.uint8, offset=8)
    return imgs, labels


def quantize_pixels(raw):
    return np.clip(np.round(raw.astype(np.float64) / 255.0 * 128.0), 0, 127).astype(np.int64)


@cocotb.test()
async def test_mnist_batch(dut):
    start = int(os.environ.get("MNIST_START", "0"))
    count = int(os.environ.get("MNIST_COUNT", "20"))
    out_path = os.environ.get("MNIST_OUT", "rtl_results.json")
    imgs, labels = load_mnist_test(os.environ["MNIST_DIR"])

    w1, b1, w2, b2 = load_parameters(DATA_DIR)
    shift1 = load_shift(DATA_DIR)

    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.start.value = 0
    for name in ("w_in_c0", "w_in_c1", "w_in_c2", "w_in_c3", "a_in_r0", "a_in_r1", "a_in_r2", "a_in_r3",
                 "psum_in_c0", "psum_in_c1", "psum_in_c2", "psum_in_c3"):
        getattr(dut, name).value = 0
    dut.shift_val.value = shift1
    dut.requant_in.value = 0
    dut.accum_buf_we.value = 0
    dut.accum_buf_addr.value = 0

    async def tick():
        dut.clk.value = 0
        await Timer(5, unit="ns")
        dut.clk.value = 1
        await Timer(5, unit="ns")

    for _ in range(3):
        await tick()
    dut.rst_n.value = 1
    await tick()

    results = []
    mismatches = 0
    for idx in range(start, start + count):
        x = quantize_pixels(imgs[idx])
        golden = infer_integer(x, w1, b1, w2, b2, shift1)
        rtl = await run_single_image_inference(dut, x, w1, b1, w2, b2, shift1)
        g = {k: [int(v) for v in golden[k].tolist()] for k in ("acc1", "act1", "acc2")}
        match = rtl["acc1"] == g["acc1"] and rtl["act1"] == g["act1"] and rtl["acc2"] == g["acc2"] \
            and rtl["pred"] == int(golden["pred"])
        mismatches += 0 if match else 1
        results.append({
            "index": idx,
            "label": int(labels[idx]),
            "pixels": [int(v) for v in x],
            "rtl_logits": rtl["acc2"],
            "rtl_hidden": rtl["act1"],
            "rtl_pred": rtl["pred"],
            "golden_pred": int(golden["pred"]),
            "bit_exact": bool(match),
            "cycles": rtl["cycles"],
        })
        dut._log.info(f"image {idx}: label={int(labels[idx])} rtl_pred={rtl['pred']} golden_pred={int(golden['pred'])} "
                      f"bit_exact={match} cycles={rtl['cycles']}")
        # Write after every image so partial runs are not lost.
        Path(out_path).write_text(json.dumps(results))
        for _ in range(2):
            await tick()

    correct = sum(r["rtl_pred"] == r["label"] for r in results)
    dut._log.info(f"SUMMARY: {count} images, bit-exact {count - mismatches}/{count}, "
                  f"RTL correct {correct}/{count}")
    assert mismatches == 0, f"{mismatches} image(s) differ from golden_model.py"
