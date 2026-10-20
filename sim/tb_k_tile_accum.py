import cocotb
from cocotb.triggers import Timer


ROW_TO_IDX = {0b0001: 0, 0b0010: 1, 0b0100: 2, 0b1000: 3}


def matvec4(a_vec, w_mat):
    return [
        sum(a_vec[r] * w_mat[r][c] for r in range(4))
        for c in range(4)
    ]


def requant_ref(acc, shift):
    round_add = (1 << (shift - 1)) if shift > 0 else 0
    scaled = (acc + round_add) >> shift
    return max(0, min(127, scaled))


@cocotb.test()
async def test_two_k_tile_accumulation(dut):
    """Verify multi-K-tile partial-sum accumulation, single-bias addition, and buffer read/write timing."""
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

    for _ in range(3):
        await tick()
    dut.rst_n.value = 1
    await tick()

    # Hand-computable 3-K-tile test with mixed signed weights, activations, and biases
    w_tiles = {
        0: [
            [ 2, -1,  3, -2],
            [-3,  4, -1,  1],
            [ 1,  2, -2,  3],
            [ 4, -3,  1, -4],
        ],
        1: [
            [-1,  3, -2,  2],
            [ 2, -2,  4, -1],
            [-3,  1,  1,  3],
            [ 1,  2, -3, -2],
        ],
        2: [
            [ 5, -4,  2,  1],
            [-2,  3, -3,  4],
            [ 4, -1,  5, -2],
            [-3,  2, -1,  3],
        ],
    }

    a_tiles = {
        0: [ 3, -2,  4, -1],
        1: [-2,  5, -1,  3],
        2: [ 4,  1, -3,  2],
    }

    bias = [10, -20, 5, 100]

    # Expected cumulative sums after each K-tile (bias added once on tile 0)
    dot0 = matvec4(a_tiles[0], w_tiles[0])  # [12, 0, 2, 8]
    exp_k0 = [bias[c] + dot0[c] for c in range(4)]  # [22, -20, 7, 108]

    dot1 = matvec4(a_tiles[1], w_tiles[1])  # [18, -11, 14, -18]
    exp_k1 = [exp_k0[c] + dot1[c] for c in range(4)]  # [40, -31, 21, 90]

    dot2 = matvec4(a_tiles[2], w_tiles[2])  # [0, -6, -12, 20]
    exp_k2 = [exp_k1[c] + dot2[c] for c in range(4)]  # [40, -37, 9, 110]

    expected_by_tile = [exp_k0, exp_k1, exp_k2]

    # Keep bias continuously on psum_in_c0..c3 across all tiles to verify it is only added on k_tile_idx == 0
    dut.psum_in_c0.value = bias[0]
    dut.psum_in_c1.value = bias[1]
    dut.psum_in_c2.value = bias[2]
    dut.psum_in_c3.value = bias[3]

    dut.start.value = 1
    await tick()
    dut.start.value = 0

    completed_tiles = 0

    for cyc in range(120):
        k_idx = int(dut.k_tile_idx.value)

        if int(dut.weight_en.value):
            row_mask = int(dut.u_grid.weight_en_row.value)
            r_idx = ROW_TO_IDX[row_mask]
            w_row = w_tiles.get(k_idx, [[0] * 4 for _ in range(4)])[r_idx]
            dut.w_in_c0.value = w_row[0]
            dut.w_in_c1.value = w_row[1]
            dut.w_in_c2.value = w_row[2]
            dut.w_in_c3.value = w_row[3]
        else:
            dut.w_in_c0.value = 0
            dut.w_in_c1.value = 0
            dut.w_in_c2.value = 0
            dut.w_in_c3.value = 0

        if int(dut.activation_en.value):
            a_vec = a_tiles.get(k_idx, [0, 0, 0, 0])
            dut.a_in_r0.value = a_vec[0]
            dut.a_in_r1.value = a_vec[1]
            dut.a_in_r2.value = a_vec[2]
            dut.a_in_r3.value = a_vec[3]
        else:
            dut.a_in_r0.value = 0
            dut.a_in_r1.value = 0
            dut.a_in_r2.value = 0
            dut.a_in_r3.value = 0

        if int(dut.accum_we.value):
            tile_num = completed_tiles
            exp_vec = expected_by_tile[tile_num]

            # Check grid bottom outputs before clock edge latches into accum_buffer
            grid_out = [
                dut.psum_out_c0.value.to_signed(),
                dut.psum_out_c1.value.to_signed(),
                dut.psum_out_c2.value.to_signed(),
                dut.psum_out_c3.value.to_signed(),
            ]
            assert grid_out == exp_vec, (
                f"K-tile {tile_num} psum_out mismatch: expected {exp_vec}, got {grid_out}"
            )

            # Advance one clock edge so accum_buffer latches psum_out and updates accum_q
            await tick()

            buf_out = [
                dut.accum_q_c0.value.to_signed(),
                dut.accum_q_c1.value.to_signed(),
                dut.accum_q_c2.value.to_signed(),
                dut.accum_q_c3.value.to_signed(),
            ]
            assert buf_out == exp_vec, (
                f"K-tile {tile_num} accum_q mismatch after write: expected {exp_vec}, got {buf_out}"
            )

            dut._log.info(
                "PASS K-tile %d: psum_out=%s, accum_q=%s",
                tile_num, grid_out, buf_out
            )

            completed_tiles += 1
            if completed_tiles == 3:
                break
            continue

        await tick()

    assert completed_tiles == 3, f"Expected 3 completed K-tiles, saw {completed_tiles}"


@cocotb.test()
async def test_full_n_tile_requant_and_multi_address(dut):
    """Verify accumulation across all 196 K-tiles for two consecutive N-tiles (addr 0 and addr 1)."""
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.start.value = 0

    for name in (
        "w_in_c0", "w_in_c1", "w_in_c2", "w_in_c3",
        "a_in_r0", "a_in_r1", "a_in_r2", "a_in_r3",
        "psum_in_c0", "psum_in_c1", "psum_in_c2", "psum_in_c3",
    ):
        getattr(dut, name).value = 0

    shift = 2
    dut.shift_val.value = shift
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

    # Only K-tiles 0 and 195 (first and last) are non-zero to verify retention across 194 zero K-tiles
    # and verify that the final K-tile (195) is visible on accum_q during REQUANT/WRITEBACK.
    biases_by_ntile = {
        0: [40, -40, 100, 500],
        1: [-10, 80, -200, 30],
    }

    w_by_ntile_ktile = {
        (0, 0):   [[2, -1, 3, 1], [1, 2, -2, 0], [0, 1, 1, -1], [-1, 0, 2, 2]],
        (0, 195): [[1, -2, 1, 3], [2, 1, 0, -1], [-1, 3, 2, 1], [3, -1, -1, 2]],
        (1, 0):   [[-2, 3, 1, -1], [1, -1, 2, 3], [3, 2, -1, 1], [0, 1, 3, -2]],
        (1, 195): [[2, 1, -2, 2], [-1, 2, 1, 1], [1, -3, 2, -1], [2, 0, 1, 3]],
    }

    a_by_ktile = {
        0:   [4, -2, 3, 1],
        195: [-1, 3, 2, 4],
    }

    exp_acc = {}
    exp_req = {}
    for n_idx in (0, 1):
        total = list(biases_by_ntile[n_idx])
        for k_idx in (0, 195):
            contrib = matvec4(a_by_ktile[k_idx], w_by_ntile_ktile[(n_idx, k_idx)])
            total = [total[c] + contrib[c] for c in range(4)]
        exp_acc[n_idx] = total
        exp_req[n_idx] = [requant_ref(total[c], shift) for c in range(4)]

    dut.start.value = 1
    await tick()
    dut.start.value = 0

    requant_seen = 0
    zero_mat = [[0] * 4 for _ in range(4)]

    for _ in range(7000):
        n_idx = int(dut.n_tile_idx.value)
        k_idx = int(dut.k_tile_idx.value)

        b_vec = biases_by_ntile.get(n_idx, [0, 0, 0, 0])
        dut.psum_in_c0.value = b_vec[0]
        dut.psum_in_c1.value = b_vec[1]
        dut.psum_in_c2.value = b_vec[2]
        dut.psum_in_c3.value = b_vec[3]

        if int(dut.weight_en.value):
            row_mask = int(dut.u_grid.weight_en_row.value)
            r_idx = ROW_TO_IDX[row_mask]
            w_row = w_by_ntile_ktile.get((n_idx, k_idx), zero_mat)[r_idx]
            dut.w_in_c0.value = w_row[0]
            dut.w_in_c1.value = w_row[1]
            dut.w_in_c2.value = w_row[2]
            dut.w_in_c3.value = w_row[3]
        else:
            dut.w_in_c0.value = 0
            dut.w_in_c1.value = 0
            dut.w_in_c2.value = 0
            dut.w_in_c3.value = 0

        if int(dut.activation_en.value):
            a_vec = a_by_ktile.get(k_idx, [0, 0, 0, 0])
            dut.a_in_r0.value = a_vec[0]
            dut.a_in_r1.value = a_vec[1]
            dut.a_in_r2.value = a_vec[2]
            dut.a_in_r3.value = a_vec[3]
        else:
            dut.a_in_r0.value = 0
            dut.a_in_r1.value = 0
            dut.a_in_r2.value = 0
            dut.a_in_r3.value = 0

        if int(dut.requant_en.value):
            got_acc = [
                dut.accum_q_c0.value.to_signed(),
                dut.accum_q_c1.value.to_signed(),
                dut.accum_q_c2.value.to_signed(),
                dut.accum_q_c3.value.to_signed(),
            ]
            got_req = [
                dut.requant_out_c0.value.to_signed(),
                dut.requant_out_c1.value.to_signed(),
                dut.requant_out_c2.value.to_signed(),
                dut.requant_out_c3.value.to_signed(),
            ]

            assert got_acc == exp_acc[n_idx], (
                f"N-tile {n_idx} final accum_q mismatch: expected {exp_acc[n_idx]}, got {got_acc}"
            )
            assert got_req == exp_req[n_idx], (
                f"N-tile {n_idx} requant_out mismatch: expected {exp_req[n_idx]}, got {got_req}"
            )

            dut._log.info(
                "PASS N-tile %d (196 K-tiles): accum_q=%s, requant_out=%s",
                n_idx, got_acc, got_req
            )
            requant_seen += 1
            if requant_seen == 2:
                break

        await tick()

    assert requant_seen == 2, f"Expected 2 N-tile requant events, saw {requant_seen}"