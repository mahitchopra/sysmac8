import cocotb
from cocotb.triggers import Timer

async def tick(dut, a, psum, weight_en=0, w=0):
    """Apply inputs, generate one rising clock edge, and let outputs settle."""
    dut.clk.value = 0
    dut.a_in.value = a
    dut.psum_in.value = psum
    dut.weight_en.value = weight_en
    dut.w_in.value = w

    # Inputs settle before the rising edge.
    await Timer(5, unit="ns")

    dut.clk.value = 1
    await Timer(5, unit="ns")

def signed_value(signal):
    """Read a signed two's-complement value from a Cocotb signal."""
    return signal.value.to_signed()

@cocotb.test()
async def test_pe_functionality(dut):
    dut._log.info("Starting PE functionality tests")

    # 1. Reset test
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.weight_en.value = 0
    dut.w_in.value = 0
    dut.a_in.value = 0
    dut.psum_in.value = 0

    # Allow asynchronous reset to take effect without a clock edge.
    await Timer(2, unit="ns")

    assert signed_value(dut.a_out) == 0, "a_out did not reset to zero"
    assert signed_value(dut.psum_out) == 0, "psum_out did not reset to zero"

    # Release reset.
    dut.rst_n.value = 1
    await Timer(1, unit="ns")

    dut._log.info("PASS: asynchronous reset")

    # 2. Load weight = 5
    # The old weight is zero during this edge, so the MAC result
    # for this edge does not use the newly loaded weight.
    await tick(dut, a=0, psum=0, weight_en=1, w=5)

    assert signed_value(dut.psum_out) == 0, (
        "Unexpected partial sum while loading the first weight"
    )

    dut._log.info("PASS: weight loading")

    # 3. MAC: 100 + (3 * 5) = 115
    await tick(dut, a=3, psum=100)

    assert signed_value(dut.psum_out) == 115, (
        f"Expected psum_out=115, got {signed_value(dut.psum_out)}"
    )
    assert signed_value(dut.a_out) == 3, (
        f"Expected a_out=3, got {signed_value(dut.a_out)}"
    )

    dut._log.info("PASS: positive multiplication and forwarding")

    # 4. Signed multiplication: 1000 + (-128 * 5) = 360
    await tick(dut, a=-128, psum=1000)

    assert signed_value(dut.psum_out) == 360, (
        f"Expected psum_out=360, got {signed_value(dut.psum_out)}"
    )
    assert signed_value(dut.a_out) == -128, (
        f"Expected a_out=-128, got {signed_value(dut.a_out)}"
    )

    dut._log.info("PASS: negative activation multiplication")

    # 5. Weight retention
    # weight_en=0, so the stored weight must remain 5.
    # 7 + (4 * 5) = 27
    await tick(dut, a=4, psum=7, weight_en=0, w=-2)

    assert signed_value(dut.psum_out) == 27, (
        f"Weight was not retained: expected 27, "
        f"got {signed_value(dut.psum_out)}"
    )

    dut._log.info("PASS: weight retention")

    # 6. Loading a new weight
    # This edge loads -2, but the MAC still uses the old weight 5.
    # 10 + (4 * 5) = 30
    await tick(dut, a=4, psum=10, weight_en=1, w=-2)

    assert signed_value(dut.psum_out) == 30, (
        f"Expected old weight to be used on load edge: "
        f"expected 30, got {signed_value(dut.psum_out)}"
    )

    # The next edge uses the newly stored weight -2.
    # 10 + (4 * -2) = 2
    await tick(dut, a=4, psum=10)

    assert signed_value(dut.psum_out) == 2, (
        f"Expected psum_out=2 with new weight, "
        f"got {signed_value(dut.psum_out)}"
    )

    dut._log.info("PASS: weight update timing")

    # 7. Asynchronous reset after nonzero outputs
    dut.clk.value = 0
    await Timer(1, unit="ns")
    dut.rst_n.value = 0
    await Timer(1, unit="ns")

    assert signed_value(dut.a_out) == 0, (
        "a_out did not clear on asynchronous reset"
    )
    assert signed_value(dut.psum_out) == 0, (
        "psum_out did not clear on asynchronous reset"
    )

    dut._log.info("PASS: asynchronous reset after operation")
    dut._log.info("All PE functionality tests passed")