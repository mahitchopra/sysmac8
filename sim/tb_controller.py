import cocotb
from cocotb.triggers import Timer

@cocotb.test()
async def test_controller_sequence(dut):
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.start.value = 0

    dut.weight_en.value = 0
    dut.skew_en.value = 0
    dut.accum_we.value = 0
    dut.requant_en.value = 0

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

    assert int(dut.done.value) == 0, "done should be low after reset"

    # Start the controller
    dut.start.value = 1
    await tick()
    dut.start.value = 0

    counts = {
        "weight_en": 0,
        "skew_en": 0,
        "accum_we": 0,
        "requant_en": 0,
    }

    done_seen = False

    # Full schedule: layer 1 and layer 2
    # A generous timeout prevents a broken FSM hanging the test.
    for cycle in range(40000):
        await tick()

        for signal in counts:
            counts[signal] += int(getattr(dut, signal).value)

        if int(dut.done.value):
            done_seen = True
            break

    assert done_seen, "Controller did not assert done within 40000 cycles"

    # These checks establish that each major phase was reached.
    for signal, count in counts.items():
        assert count > 0, f"{signal} was never asserted"

    dut._log.info("Controller completed in %d cycles", cycle + 1)
    dut._log.info("Control signal counts: %s", counts)