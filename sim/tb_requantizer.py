import random
import cocotb
from cocotb.triggers import Timer

ACC_BITS = 26
ACC_MIN = -(1 << 25)
ACC_MAX = (1 << 25) - 1

def expected_requantization(acc, shift):
    """Reference behavior for the current requantizer RTL."""
    round_add = (1 << (shift - 1)) if shift > 0 else 0
    scaled = (acc + round_add) >> shift
    return max(0, min(127, scaled))

def encode_signed(value, bits):
    """Encode signed integer as a fixed-width two's-complement bit pattern."""
    return value & ((1 << bits) - 1)

@cocotb.test()
async def test_requantizer(dut):
    rng = random.Random(42)

    dut.accum_in.value = 0
    dut.shift_val.value = 0
    await Timer(2, unit="ns")

    tested = 0

    # Include boundary cases and the shift used by our model.
    test_cases = [
        (0, 0),
        (1, 0),
        (-1, 0),
        (127, 0),
        (128, 0),
        (-128, 0),
        (4095, 12),
        (4096, 12),
        (8192, 12),
        (-4096, 12),
        (-8192, 12),
        (127 << 12, 12),
        (128 << 12, 12),
        (200 << 12, 12),
        (ACC_MAX, 12),
        (ACC_MIN, 12),
    ]

    # Exercise shifts relevant to the 5-bit hardware input.
    for shift in [0, 1, 2, 3, 7, 12, 16, 20, 25]:
        for acc in [
            -100000,
            -1000,
            -1,
            0,
            1,
            1000,
            100000,
        ]:
            test_cases.append((acc, shift))

    # Randomized testing, including the actual model shift.
    for _ in range(500):
        shift = rng.choice([0, 1, 2, 3, 7, 12, 16, 20, 25])
        acc = rng.randint(-1_000_000, 1_000_000)
        test_cases.append((acc, shift))

    for acc, shift in test_cases:
        assert ACC_MIN <= acc <= ACC_MAX

        dut.accum_in.value = encode_signed(acc, ACC_BITS)
        dut.shift_val.value = shift

        await Timer(2, unit="ns")

        actual = dut.act_out.value.to_signed()
        expected = expected_requantization(acc, shift)

        assert actual == expected, (
            f"Mismatch: accum_in={acc}, shift={shift}, "
            f"expected={expected}, actual={actual}"
        )

        tested += 1

    dut._log.info(
        f"PASS: {tested} requantizer cases matched the Python reference."
    )