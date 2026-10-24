import cocotb
from cocotb.triggers import Timer


def matvec4(a_vec, w_mat):
    return [
        sum(a_vec[r] * w_mat[r][c] for r in range(4))
        for c in range(4)
    ]


@cocotb.test()
async def test_systolic(dut):
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

    for name in ("a_in_r0", "a_in_r1", "a_in_r2", "a_in_r3"):
        getattr(dut, name).value = 0

    for name in ("psum_in_c0", "psum_in_c1", "psum_in_c2", "psum_in_c3"):
        getattr(dut, name).value = 0

    async def tick():
        dut.clk.value = 0
        await Timer(5, unit="ns")
        dut.clk.value = 1
        await Timer(5, unit="ns")

    for _ in range(3):
        await tick()

    dut.rst_n.value = 1
    await tick()

    # Test 1: signed partial sums pass through with compute_en low and zero weights.
    expected = [-123, 456, 789, -1000]

    dut.psum_in_c0.value = expected[0]
    dut.psum_in_c1.value = expected[1]
    dut.psum_in_c2.value = expected[2]
    dut.psum_in_c3.value = expected[3]

    for _ in range(6):
        await tick()

    outputs = (
        dut.psum_out_c0,
        dut.psum_out_c1,
        dut.psum_out_c2,
        dut.psum_out_c3,
    )

    for i, signal in enumerate(outputs):
        actual = signal.value.to_signed()
        assert actual == expected[i], (
            f"Column {i}: expected {expected[i]}, got {actual}"
        )

    dut._log.info("PASS: signed partial-sum propagation")

    # Test 2: one active PE MAC.
    dut.psum_in_c0.value = 0
    dut.psum_in_c1.value = 0
    dut.psum_in_c2.value = 0
    dut.psum_in_c3.value = 0

    dut.rst_n.value = 0
    for _ in range(2):
        await tick()

    dut.rst_n.value = 1
    await tick()

    dut.w_in_c0.value = 3
    dut.weight_en_row.value = 0b0001
    await tick()
    dut.weight_en_row.value = 0

    dut.skew_en.value = 1
    dut.activation_en.value = 1
    dut.compute_en.value = 1
    dut.a_in_r0.value = 4

    for _ in range(5):
        await tick()

    dut._log.info(
        "Grid outputs after enabled MAC: %s, %s, %s, %s",
        dut.psum_out_c0.value.to_signed(),
        dut.psum_out_c1.value.to_signed(),
        dut.psum_out_c2.value.to_signed(),
        dut.psum_out_c3.value.to_signed(),
    )

    dut._log.info("Systolic interface regression completed")


@cocotb.test()
async def test_grid_regression(dut):
    """Verify 18 directed vector x tile signed INT8 matrix-vector cases."""
    dut.clk.value = 0
    dut.rst_n.value = 0

    async def tick():
        dut.clk.value = 0
        await Timer(5, unit="ns")
        dut.clk.value = 1
        await Timer(5, unit="ns")

    tiles = [
        [
            [ 1,  2,  0,  1],
            [ 0,  1,  1,  0],
            [ 2,  0,  1,  1],
            [ 1,  1,  0,  2],
        ],
        [
            [-1,  2,  0,  1],
            [ 0, -2,  1,  0],
            [ 2,  0, -1,  1],
            [ 1,  1,  0, -2],
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

    case_count = 0

    for t_idx, w_mat in enumerate(tiles):
        dut.rst_n.value = 0
        dut.weight_en_row.value = 0
        dut.skew_en.value = 0
        dut.activation_en.value = 0
        dut.compute_en.value = 0
        for c in range(4):
            getattr(dut, f"w_in_c{c}").value = 0
            getattr(dut, f"psum_in_c{c}").value = 0
        for r in range(4):
            getattr(dut, f"a_in_r{r}").value = 0

        for _ in range(2):
            await tick()
        dut.rst_n.value = 1
        await tick()

        # Load 4 weight rows
        for r in range(4):
            dut.weight_en_row.value = 1 << r
            for c in range(4):
                getattr(dut, f"w_in_c{c}").value = w_mat[r][c]
            await tick()

        dut.weight_en_row.value = 0
        for c in range(4):
            getattr(dut, f"w_in_c{c}").value = 0

        for v_idx, a_vec in enumerate(vectors):
            expected = matvec4(a_vec, w_mat)

            # Inject single vector on cycle 0, then flush with zeros
            dut.skew_en.value = 1
            dut.activation_en.value = 1
            dut.compute_en.value = 1
            for r in range(4):
                getattr(dut, f"a_in_r{r}").value = a_vec[r]
            await tick()

            dut.activation_en.value = 0
            for r in range(4):
                getattr(dut, f"a_in_r{r}").value = 0

            # Staggered column outputs arrive at sample indices 3, 4, 5, 6 after injection
            observed = [None] * 4
            for step in range(1, 8):
                await tick()
                if step == 3:
                    observed[0] = dut.psum_out_c0.value.to_signed()
                elif step == 4:
                    observed[1] = dut.psum_out_c1.value.to_signed()
                elif step == 5:
                    observed[2] = dut.psum_out_c2.value.to_signed()
                elif step == 6:
                    observed[3] = dut.psum_out_c3.value.to_signed()

            assert observed == expected, (
                f"Tile {t_idx} vec {v_idx} ({a_vec}): expected {expected}, got {observed}"
            )
            case_count += 1

    dut._log.info("ALL GRID REGRESSION CASES PASSED: %d vector cases", case_count)
