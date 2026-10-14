import cocotb
from cocotb.triggers import Timer

@cocotb.test()
async def test_top_mac(dut):
    dut._log.info("Starting controller-driven top-level MAC test")

    # Initialize inputs
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.start.value = 0

    for name in (
        "w_in_c0", "w_in_c1", "w_in_c2", "w_in_c3",
        "a_in_r0", "a_in_r1", "a_in_r2", "a_in_r3",
        "psum_in_c0", "psum_in_c1", "psum_in_c2", "psum_in_c3",
    ):
        getattr(dut, name).value = 0

    dut.shift_val.value = 0
    dut.requant_in.value = 0
    dut.accum_buf_we.value = 0
    dut.accum_buf_addr.value = 0

    async def tick():
        dut.clk.value = 0
        await Timer(5, unit="ns")
        dut.clk.value = 1
        await Timer(5, unit="ns")

    # Reset
    for _ in range(3):
        await tick()

    dut.rst_n.value = 1
    await tick()

    # Start controller
    dut.start.value = 1
    await tick()
    dut.start.value = 0

    # During each weight-loading cycle, set the broadcast
    # bus according to the currently selected PE row.
    #
    # Desired weights:
    #   row 0: [3, 0, 0, 0]
    #   row 1: [0, 0, 0, 0]
    #   row 2: [0, 0, 0, 0]
    #   row 3: [0, 0, 0, 0]
    loaded_rows = []

    for cycle in range(30):
        if int(dut.weight_en.value):
            row_enable = int(dut.u_grid.weight_en_row.value)
            loaded_rows.append(row_enable)

            dut.w_in_c0.value = 3 if row_enable == 0b0001 else 0
            dut.w_in_c1.value = 0
            dut.w_in_c2.value = 0
            dut.w_in_c3.value = 0

        await tick()

        if int(dut.activation_en.value):
            break
    else:
        assert False, "Controller never entered activation streaming"

    expected_rows = [1, 2, 4, 8]
    assert loaded_rows == expected_rows, (
        f"Unexpected weight-loading sequence: {loaded_rows}"
    )

    dut._log.info("PASS: first tile loaded weights in row order")

    # Inject the single valid activation and initial sum.
    #
    # Expected: 3 * 4 + 10 = 22.
    dut.a_in_r0.value = 4
    dut.a_in_r1.value = 0
    dut.a_in_r2.value = 0
    dut.a_in_r3.value = 0

    dut.psum_in_c0.value = 10
    dut.psum_in_c1.value = 0
    dut.psum_in_c2.value = 0
    dut.psum_in_c3.value = 0

    # First active edge: row 0, column 0 should calculate 22.
    await tick()

    # Inject no additional activations or partial sums.
    dut.a_in_r0.value = 0
    dut.psum_in_c0.value = 0

    # Let the result traverse the remaining registered PE rows.
    for _ in range(3):
        await tick()

    actual = dut.psum_out_c0.value.to_signed()
    expected = 22

    dut._log.info("Expected bottom-column-0 result: %d", expected)
    dut._log.info("Actual bottom-column-0 result: %d", actual)

    assert actual == expected, (
        f"Top-level MAC mismatch: expected {expected}, got {actual}"
    )

    dut._log.info("PASS: controller-driven top-level MAC")