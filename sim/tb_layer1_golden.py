from pathlib import Path
import sys
import cocotb
from cocotb.triggers import Timer

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from model.golden_model import (
    DATA_DIR,
    load_parameters,
    load_sample_image,
    load_shift,
    infer_integer,
)

ROW_TO_IDX = {0b0001: 0, 0b0010: 1, 0b0100: 2, 0b1000: 3}


@cocotb.test()
async def test_layer1_rtl_vs_golden(dut):
    """Run complete Layer 1 (784 -> 32) on real quantized parameters and compare against golden_model.py."""
    w1, b1, w2, b2 = load_parameters(DATA_DIR)
    image = load_sample_image(DATA_DIR)
    shift1 = load_shift(DATA_DIR)

    golden = infer_integer(image, w1, b1, w2, b2, shift1)
    exp_acc1 = [int(x) for x in golden["acc1"].tolist()]
    exp_act1 = [int(x) for x in golden["act1"].tolist()]

    w1_list = w1.tolist()
    b1_list = [int(x) for x in b1.tolist()]
    img_list = [int(x) for x in image.tolist()]

    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.start.value = 0

    for name in (
        "w_in_c0", "w_in_c1", "w_in_c2", "w_in_c3",
        "a_in_r0", "a_in_r1", "a_in_r2", "a_in_r3",
        "psum_in_c0", "psum_in_c1", "psum_in_c2", "psum_in_c3",
    ):
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

    dut.start.value = 1
    await tick()
    dut.start.value = 0

    rtl_acc1 = [None] * 32
    rtl_act1 = [None] * 32
    tiles_done = 0

    for cyc in range(30000):
        layer = int(dut.layer_idx.value)
        n_tile = int(dut.n_tile_idx.value)
        k_tile = int(dut.k_tile_idx.value)

        if layer == 0:
            base_n = 4 * n_tile
            base_k = 4 * k_tile

            dut.psum_in_c0.value = b1_list[base_n + 0]
            dut.psum_in_c1.value = b1_list[base_n + 1]
            dut.psum_in_c2.value = b1_list[base_n + 2]
            dut.psum_in_c3.value = b1_list[base_n + 3]

            if int(dut.weight_en.value):
                row_mask = int(dut.u_grid.weight_en_row.value)
                r_idx = ROW_TO_IDX[row_mask]
                k_idx = base_k + r_idx
                dut.w_in_c0.value = int(w1_list[base_n + 0][k_idx])
                dut.w_in_c1.value = int(w1_list[base_n + 1][k_idx])
                dut.w_in_c2.value = int(w1_list[base_n + 2][k_idx])
                dut.w_in_c3.value = int(w1_list[base_n + 3][k_idx])
            else:
                dut.w_in_c0.value = 0
                dut.w_in_c1.value = 0
                dut.w_in_c2.value = 0
                dut.w_in_c3.value = 0

            if int(dut.activation_en.value):
                dut.a_in_r0.value = img_list[base_k + 0]
                dut.a_in_r1.value = img_list[base_k + 1]
                dut.a_in_r2.value = img_list[base_k + 2]
                dut.a_in_r3.value = img_list[base_k + 3]
            else:
                dut.a_in_r0.value = 0
                dut.a_in_r1.value = 0
                dut.a_in_r2.value = 0
                dut.a_in_r3.value = 0

            if int(dut.requant_en.value):
                acc_cols = [
                    dut.accum_q_c0.value.to_signed(),
                    dut.accum_q_c1.value.to_signed(),
                    dut.accum_q_c2.value.to_signed(),
                    dut.accum_q_c3.value.to_signed(),
                ]
                act_cols = [
                    dut.requant_out_c0.value.to_signed(),
                    dut.requant_out_c1.value.to_signed(),
                    dut.requant_out_c2.value.to_signed(),
                    dut.requant_out_c3.value.to_signed(),
                ]
                for c in range(4):
                    rtl_acc1[base_n + c] = acc_cols[c]
                    rtl_act1[base_n + c] = act_cols[c]
                tiles_done += 1

        if layer == 1:
            break

        await tick()

    assert tiles_done == 8, f"Expected 8 Layer 1 output tiles, completed {tiles_done}"

    acc_mismatches = [
        (i, exp_acc1[i], rtl_acc1[i])
        for i in range(32)
        if rtl_acc1[i] != exp_acc1[i]
    ]
    act_mismatches = [
        (i, exp_act1[i], rtl_act1[i])
        for i in range(32)
        if rtl_act1[i] != exp_act1[i]
    ]

    dut._log.info("Layer 1 Golden acc1: %s", exp_acc1)
    dut._log.info("Layer 1 RTL    acc1: %s", rtl_acc1)
    dut._log.info("Layer 1 Golden act1: %s", exp_act1)
    dut._log.info("Layer 1 RTL    act1: %s", rtl_act1)

    assert not acc_mismatches, f"Layer 1 accumulator mismatches: {acc_mismatches}"
    assert not act_mismatches, f"Layer 1 activation mismatches: {act_mismatches}"

    dut._log.info("PASS: all 32 Layer 1 accumulators and 32 activations match golden_model.py exactly.")