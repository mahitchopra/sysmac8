import cocotb
from cocotb.triggers import Timer

@cocotb.test()
async def test_grid_mac(dut):
    dut._log.info("Starting deterministic systolic-grid MAC test")

    # Initialize every input
    dut.clk.value = 0
    dut.rst_n.value = 0

    dut.weight_en_row.value = 0
    dut.w_in_c0.value = 0
    dut.w_in_c1.value = 0
    dut.w_in_c2.value = 0
    dut.w_in_c3.value = 0

    dut.skew_en.value = 0
    dut.activation_en.value = 0
    dut.compute_en.value = 0

    dut.a_in_r0.value = 0
    dut.a_in_r1.value = 0
    dut.a_in_r2.value = 0
    dut.a_in_r3.value = 0

    dut.psum_in_c0.value = 0
    dut.psum_in_c1.value = 0
    dut.psum_in_c2.value = 0
    dut.psum_in_c3.value = 0

    async def tick():
        dut.clk.value = 0
        await Timer(5, unit="ns")
        dut.clk.value = 1
        await Timer(5, unit="ns")

    # Reset all PE and skew registers
    for _ in range(3):
        await tick()

    dut.rst_n.value = 1
    await tick()

    # Load weights.
    # Row 0: [3, 0, 0, 0]
    # Rows 1-3: [0, 0, 0, 0]
    # Weight bus values are stable before each loading edge.
    dut.w_in_c0.value = 3
    dut.w_in_c1.value = 0
    dut.w_in_c2.value = 0
    dut.w_in_c3.value = 0

    dut.weight_en_row.value = 0b0001
    await tick()

    dut.weight_en_row.value = 0b0010
    await tick()

    dut.weight_en_row.value = 0b0100
    await tick()

    dut.weight_en_row.value = 0b1000
    await tick()

    dut.weight_en_row.value = 0

    # Inject one activation and one initial partial sum.
    # Expected arithmetic: 10 + 3*4 = 22.
    dut.skew_en.value = 1
    dut.activation_en.value = 1
    dut.compute_en.value = 1

    dut.a_in_r0.value = 4
    dut.a_in_r1.value = 0
    dut.a_in_r2.value = 0
    dut.a_in_r3.value = 0

    dut.psum_in_c0.value = 10
    dut.psum_in_c1.value = 0
    dut.psum_in_c2.value = 0
    dut.psum_in_c3.value = 0

    # First edge: row 0 performs 10 + 3*4 = 22.
    await tick()

    # Stop injecting the initial sum and activation.
    dut.psum_in_c0.value = 0
    dut.a_in_r0.value = 0
    dut.activation_en.value = 0

    # Next three edges propagate the partial sum down rows 1-3.
    for _ in range(3):
        await tick()

    actual = dut.psum_out_c0.value.to_signed()
    expected = 22

    dut._log.info("Expected column 0 output: %d", expected)
    dut._log.info("Actual column 0 output: %d", actual)

    assert actual == expected, (
        f"MAC mismatch: expected {expected}, got {actual}"
    )

    # Other columns received zero weights and zero initial sums.
    for name in ("psum_out_c1", "psum_out_c2", "psum_out_c3"):
        value = getattr(dut, name).value.to_signed()
        assert value == 0, f"{name}: expected 0, got {value}"

    dut._log.info("PASS: exact signed MAC and partial-sum propagation")