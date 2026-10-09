import cocotb
from cocotb.triggers import Timer


def signed_value(signal):
    return signal.value.to_signed()


def read_outputs(dut):
    return [
        signed_value(dut.psum_out_c0),
        signed_value(dut.psum_out_c1),
        signed_value(dut.psum_out_c2),
        signed_value(dut.psum_out_c3),
    ]


def matvec(a, w):
    return [
        sum(a[k] * w[k][j] for k in range(4))
        for j in range(4)
    ]


async def cycle(
    dut,
    activations=(0, 0, 0, 0),
    weight_en_row=0,
    weights=(0, 0, 0, 0),
    psums=(0, 0, 0, 0),
    skew_en=0,
):
    dut.clk.value = 0

    dut.a_in_r0.value = activations[0]
    dut.a_in_r1.value = activations[1]
    dut.a_in_r2.value = activations[2]
    dut.a_in_r3.value = activations[3]

    dut.weight_en_row.value = weight_en_row
    dut.w_in_c0.value = weights[0]
    dut.w_in_c1.value = weights[1]
    dut.w_in_c2.value = weights[2]
    dut.w_in_c3.value = weights[3]

    dut.psum_in_c0.value = psums[0]
    dut.psum_in_c1.value = psums[1]
    dut.psum_in_c2.value = psums[2]
    dut.psum_in_c3.value = psums[3]

    dut.skew_en.value = skew_en

    await Timer(5, unit="ns")
    dut.clk.value = 1
    await Timer(5, unit="ns")


async def reset_grid(dut):
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.skew_en.value = 0
    dut.weight_en_row.value = 0

    for name in (
        "a_in_r0", "a_in_r1", "a_in_r2", "a_in_r3",
        "w_in_c0", "w_in_c1", "w_in_c2", "w_in_c3",
        "psum_in_c0", "psum_in_c1", "psum_in_c2", "psum_in_c3",
    ):
        getattr(dut, name).value = 0

    await Timer(2, unit="ns")
    assert read_outputs(dut) == [0, 0, 0, 0], (
        "Outputs must clear on asynchronous reset"
    )

    dut.rst_n.value = 1
    await Timer(1, unit="ns")


async def load_weights(dut, w):
    for r in range(4):
        await cycle(
            dut,
            weight_en_row=1 << r,
            weights=w[r],
        )

    # Change the input buses without enabling any weight register.
    # Stored weights must remain unchanged.
    await cycle(
        dut,
        weight_en_row=0,
        weights=(17, -23, 31, -41),
    )


async def run_isolated_vector(dut, a, w, label):
    expected = matvec(a, w)
    observed = []

    dut._log.info(f"{label}: A={a}, expected={expected}")

    # One vector followed by enough zero cycles to drain the
    # row-skew and registered PE pipeline.
    for t in range(9):
        values = a if t == 0 else (0, 0, 0, 0)

        await cycle(
            dut,
            activations=values,
            weight_en_row=0,
            weights=(0, 0, 0, 0),
            psums=(0, 0, 0, 0),
            skew_en=1,
        )
        observed.append(read_outputs(dut))

    # This sampling schedule was observed and validated by the
    # earlier passing test on the current RTL.
    for col in range(4):
        sample = 3 + col
        actual = observed[sample][col]

        assert actual == expected[col], (
            f"{label}: column {col}, cycle {sample}: "
            f"expected {expected[col]}, got {actual}; "
            f"outputs={observed[sample]}"
        )

    dut._log.info(f"PASS: {label}")


@cocotb.test()
async def test_grid_regression(dut):
    dut._log.info("Starting systolic-grid regression")

    await reset_grid(dut)
    dut._log.info("PASS: asynchronous reset")

    matrices = [
        [
            [1, 2, 0, 1],
            [0, 1, 1, 0],
            [2, 0, 1, 1],
            [1, 1, 0, 2],
        ],
        [
            [-1, 2, 0, 1],
            [0, -2, 1, 0],
            [2, 0, -1, 1],
            [1, 1, 0, -2],
        ],
        [
            [-1, -2, -3, -4],
            [-2, -1, -4, -3],
            [-3, -4, -1, -2],
            [-4, -3, -2, -1],
        ],
    ]

    vectors = [
        [1, 2, 3, 4],
        [2, 0, 1, 3],
        [-1, 2, -3, 4],
        [0, 0, 0, 0],
        [127, -128, 1, -1],
        [-128, 127, -128, 127],
    ]

    total = 0

    for matrix_index, w in enumerate(matrices):
        dut._log.info(f"Loading weight tile {matrix_index}")
        await load_weights(dut, w)

        for vector_index, a in enumerate(vectors):
            await run_isolated_vector(
                dut,
                a,
                w,
                f"Tile {matrix_index}, vector {vector_index}",
            )
            total += 1

    dut._log.info(
        f"ALL GRID REGRESSION CASES PASSED: {total} vector cases"
    )