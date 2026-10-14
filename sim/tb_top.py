import cocotb
from cocotb.triggers import Timer

@cocotb.test()
async def test_top_level_integration(dut):
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.start.value = 0

    for name in (
        "w_in_c0", "w_in_c1", "w_in_c2", "w_in_c3",
        "a_in_r0", "a_in_r1", "a_in_r2", "a_in_r3",
        "psum_in_c0", "psum_in_c1", "psum_in_c2", "psum_in_c3",
    ):
        getattr(dut, name).value = 0

    dut.shift_val.value = 2
    dut.requant_in.value = 0
    dut.accum_buf_we.value = 0
    dut.accum_buf_addr.value = 3

    async def tick():
        dut.clk.value = 0
        await Timer(5, unit="ns")
        dut.clk.value = 1
        await Timer(5, unit="ns")

    for _ in range(3):
        await tick()

    dut.rst_n.value = 1
    await tick()

    assert int(dut.done.value) == 0

    # Requantizer checks.
    dut.requant_in.value = 500
    await Timer(1, unit="ns")
    assert dut.requant_out.value.to_signed() == 125

    dut.requant_in.value = 1000
    await Timer(1, unit="ns")
    assert dut.requant_out.value.to_signed() == 127

    dut.requant_in.value = -20
    await Timer(1, unit="ns")
    assert dut.requant_out.value.to_signed() == 0

    # Start the controller and collect the control sequence.
    dut.start.value = 1
    await tick()
    dut.start.value = 0

    counts = {
        "weight_en": 0,
        "skew_en": 0,
        "activation_en": 0,
        "compute_en": 0,
        "accum_we": 0,
        "requant_en": 0,
    }

    row_sequence = []
    done_seen = False

    for cycle in range(30000):
        await tick()

        for signal in counts:
            counts[signal] += int(getattr(dut, signal).value)

        if int(dut.weight_en.value):
            row_sequence.append(int(dut.u_grid.weight_en_row.value))

        if int(dut.done.value):
            done_seen = True
            break

    assert done_seen, "Controller did not complete"

    for signal, count in counts.items():
        assert count > 0, f"{signal} was never asserted"

    expected_rows = [1, 2, 4, 8]

    assert len(row_sequence) == 6368, (
        f"Expected 6368 weight-loading cycles, got {len(row_sequence)}"
    )

    for i in range(0, len(row_sequence), 4):
        assert row_sequence[i:i + 4] == expected_rows, (
            f"Incorrect row sequence at burst {i // 4}: "
            f"{row_sequence[i:i + 4]}"
        )

    dut._log.info("PASS: top-level controller and row loading")
    dut._log.info("PASS: requantization, saturation, and ReLU")
    dut._log.info("Controller cycles: %d", cycle + 1)
    dut._log.info("Signal counts: %s", counts)