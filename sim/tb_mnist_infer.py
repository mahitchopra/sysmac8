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


async def run_single_image_inference(dut, img_tensor, w1, b1, w2, b2, shift1, poison_unused_l2_cols=False):
    """Run full 2-layer schedule on sysmac8_top and return RTL intermediate and final outputs."""
    w1_list = w1.tolist()
    b1_list = [int(x) for x in b1.tolist()]
    w2_list = w2.tolist()
    b2_list = [int(x) for x in b2.tolist()]
    img_list = [int(x) for x in img_tensor.tolist()]

    dut.shift_val.value = shift1
    dut.requant_in.value = 0
    dut.accum_buf_we.value = 0
    dut.accum_buf_addr.value = 0

    async def tick():
        dut.clk.value = 0
        await Timer(5, unit="ns")
        dut.clk.value = 1
        await Timer(5, unit="ns")

    dut.start.value = 1
    await tick()
    dut.start.value = 0

    rtl_acc1 = [None] * 32
    rtl_act1 = [None] * 32
    rtl_acc2 = [None] * 10
    done_cycle = None

    for cyc in range(30000):
        layer = int(dut.layer_idx.value)
        n_tile = int(dut.n_tile_idx.value)
        k_tile = int(dut.k_tile_idx.value)
        base_n = 4 * n_tile
        base_k = 4 * k_tile

        if layer == 0:
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
        else:
            # Layer 2 reads activations from internal buffer_ram; keep external a_in at 0
            dut.a_in_r0.value = 0
            dut.a_in_r1.value = 0
            dut.a_in_r2.value = 0
            dut.a_in_r3.value = 0

            # On n_tile == 2 (final partial tile), only c0 (class 8) and c1 (class 9) are valid.
            # Optionally drive large dummy biases on c2/c3 to verify argmax masks out unused columns.
            unused_bias = 500000 if poison_unused_l2_cols else 0
            dut.psum_in_c0.value = b2_list[base_n + 0] if (base_n + 0) < 10 else unused_bias
            dut.psum_in_c1.value = b2_list[base_n + 1] if (base_n + 1) < 10 else unused_bias
            dut.psum_in_c2.value = b2_list[base_n + 2] if (base_n + 2) < 10 else unused_bias
            dut.psum_in_c3.value = b2_list[base_n + 3] if (base_n + 3) < 10 else unused_bias

            if int(dut.weight_en.value):
                row_mask = int(dut.u_grid.weight_en_row.value)
                r_idx = ROW_TO_IDX[row_mask]
                k_idx = base_k + r_idx
                dut.w_in_c0.value = int(w2_list[base_n + 0][k_idx]) if (base_n + 0) < 10 else 0
                dut.w_in_c1.value = int(w2_list[base_n + 1][k_idx]) if (base_n + 1) < 10 else 0
                dut.w_in_c2.value = int(w2_list[base_n + 2][k_idx]) if (base_n + 2) < 10 else (127 if poison_unused_l2_cols else 0)
                dut.w_in_c3.value = int(w2_list[base_n + 3][k_idx]) if (base_n + 3) < 10 else (127 if poison_unused_l2_cols else 0)
            else:
                dut.w_in_c0.value = 0
                dut.w_in_c1.value = 0
                dut.w_in_c2.value = 0
                dut.w_in_c3.value = 0

            if int(dut.requant_en.value):
                acc_cols = [
                    dut.accum_q_c0.value.to_signed(),
                    dut.accum_q_c1.value.to_signed(),
                    dut.accum_q_c2.value.to_signed(),
                    dut.accum_q_c3.value.to_signed(),
                ]
                for c in range(4):
                    if (base_n + c) < 10:
                        rtl_acc2[base_n + c] = acc_cols[c]

        if int(dut.done.value):
            done_cycle = cyc + 1
            break

        await tick()

    assert done_cycle is not None, "Controller did not assert done within 30,000 cycles"

    pred_class = int(dut.pred_class.value)
    max_logit = dut.max_logit.value.to_signed()

    return {
        "cycles": done_cycle,
        "acc1": rtl_acc1,
        "act1": rtl_act1,
        "acc2": rtl_acc2,
        "pred": pred_class,
        "max_logit": max_logit,
    }


@cocotb.test()
async def test_mnist_two_layer_inference(dut):
    """Verify end-to-end 2-layer MNIST inference, internal activation RAM handoff, partial output tile, and argmax."""
    import torch

    w1, b1, w2, b2 = load_parameters(DATA_DIR)
    sample_img = load_sample_image(DATA_DIR)
    shift1 = load_shift(DATA_DIR)

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

    # Build deterministic multi-image test suite spanning multiple predicted digit classes
    test_samples = [
        ("sample_img.hex", sample_img, True),
        ("shifted_plus_2rows", torch.roll(sample_img, shifts=56, dims=0), True),
        ("shifted_minus_2rows", torch.roll(sample_img, shifts=-56, dims=0), False),
        ("flipped_sample", torch.flip(sample_img, dims=[0]), False),
    ]

    agreements = 0

    for idx, (label_name, img_vec, poison_unused) in enumerate(test_samples):
        golden = infer_integer(img_vec, w1, b1, w2, b2, shift1)
        exp_acc1 = [int(x) for x in golden["acc1"].tolist()]
        exp_act1 = [int(x) for x in golden["act1"].tolist()]
        exp_acc2 = [int(x) for x in golden["acc2"].tolist()]
        exp_pred = int(golden["pred"])
        exp_max_logit = max(exp_acc2)

        rtl = await run_single_image_inference(
            dut, img_vec, w1, b1, w2, b2, shift1, poison_unused_l2_cols=poison_unused
        )

        assert rtl["acc1"] == exp_acc1, (
            f"[{label_name}] Layer 1 acc1 mismatch:\n  exp={exp_acc1}\n  got={rtl['acc1']}"
        )
        assert rtl["act1"] == exp_act1, (
            f"[{label_name}] Layer 1 act1 mismatch:\n  exp={exp_act1}\n  got={rtl['act1']}"
        )
        assert rtl["acc2"] == exp_acc2, (
            f"[{label_name}] Layer 2 acc2 mismatch:\n  exp={exp_acc2}\n  got={rtl['acc2']}"
        )
        assert rtl["pred"] == exp_pred, (
            f"[{label_name}] Argmax pred mismatch: expected {exp_pred}, got {rtl['pred']}"
        )
        assert rtl["max_logit"] == exp_max_logit, (
            f"[{label_name}] Argmax max_logit mismatch: expected {exp_max_logit}, got {rtl['max_logit']}"
        )

        agreements += 1
        dut._log.info(
            "Sample %d (%s): cycles=%d, pred=%d (expected %d), max_logit=%d, acc2=%s",
            idx, label_name, rtl["cycles"], rtl["pred"], exp_pred, rtl["max_logit"], rtl["acc2"]
        )

        # Let controller settle in IDLE for 1 cycle before starting next sample
        await tick()

    dut._log.info(
        "PASS: %d/%d samples matched Python golden_model.py (100%% bit-exact acc1, act1, acc2, and argmax).",
        agreements, len(test_samples)
    )