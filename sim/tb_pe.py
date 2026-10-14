import cocotb
from cocotb.triggers import Timer

@cocotb.test()
async def test_pe(dut):
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.weight_en.value = 0
    dut.compute_en.value = 0
    dut.w_in.value = 0
    dut.a_in.value = 0
    dut.psum_in.value = 0

    async def tick():
        dut.clk.value = 0
        await Timer(5, unit="ns")
        dut.clk.value = 1
        await Timer(5, unit="ns")

    await tick()
    await tick()

    dut.rst_n.value = 1
    await tick()

    assert dut.psum_out.value.to_signed() == 0

    # Load weight 3.
    dut.weight_en.value = 1
    dut.w_in.value = 3
    await tick()
    dut.weight_en.value = 0

    # Compute 3 * 4 + 10 = 22.
    dut.compute_en.value = 1
    dut.a_in.value = 4
    dut.psum_in.value = 10
    await tick()

    assert dut.psum_out.value.to_signed() == 22

    # Hold the weight and disable computation.
    # The partial sum should pass through unchanged.
    dut.compute_en.value = 0
    dut.a_in.value = 7
    dut.psum_in.value = 123
    await tick()

    assert dut.psum_out.value.to_signed() == 123

    # Negative signed MAC: 3 * -5 + 20 = 5.
    dut.compute_en.value = 1
    dut.a_in.value = -5
    dut.psum_in.value = 20
    await tick()

    assert dut.psum_out.value.to_signed() == 5

    dut._log.info("PE signed MAC and compute-enable tests passed")