# SysMAC8 --- Engineering Progress and Verification Handoff

**Purpose:** Team handoff documenting work completed after resuming at
the Baugh--Wooley multiplier, verified results, current RTL behavior,
limitations, and next steps.

**Repository:** `C:\Users\chopr\sysmac8`\
**Simulation directory:** `C:\Users\chopr\sysmac8\sim`\
**Environment:** Windows + MSYS2 UCRT64; Python 3.12.10; Cocotb 2.1.0;
Icarus Verilog/VVP 13.0; GNU Make.

------------------------------------------------------------------------

## 1. Project objective

SysMAC8 aims to implement a **4×4 weight-stationary systolic array** for
signed INT8 matrix multiplication, as a building block for tiled dense
layers in a quantized MNIST classifier.

The mathematical operation is (C = AW), with (C\_{ij} = `\sum`{=tex}*k
A*{ik}W\_{kj}).

Planned components: - Baugh--Wooley-style signed 8×8 multiplier. -
Radix-4 Booth multiplier with Wallace-tree reduction. - Processing
elements (PEs), stationary weight registers, activation forwarding, and
26-bit partial sums. - 4×4 systolic grid and activation skew
registers. - Requantization (shift/rounding, ReLU, INT8 saturation). -
Controller, buffers, top-level integration and argmax. - Python
quantization/reference model, RTL inference, and later Vivado synthesis
comparison.

**This is not yet an end-to-end MNIST implementation.** Controller,
buffers, top-level integration, inference, and synthesis comparison
remain unfinished.

## 2. Toolchain and how to run simulations

Verified tools: - Python 3.12.10 - Cocotb 2.1.0 - Icarus Verilog 13.0
and VVP 13.0 - GNU Make in MSYS2 UCRT64 - Virtual environment at
`C:\Users\chopr\sysmac8\.venv`

Repository path in MSYS2 is `/c/Users/chopr/sysmac8`. In a new MSYS2
terminal, if `cocotb-config` is not found, run:

``` bash
export PATH="/c/Users/chopr/sysmac8/.venv/Scripts:$PATH"
```

Useful checks:

``` bash
which iverilog
iverilog -V
which vvp
vvp -V
which cocotb-config
cocotb-config --version
make --version
```

Run simulation from `sim`:

``` bash
cd /c/Users/chopr/sysmac8/sim
make clean
make
```

The Makefile uses `COCOTB_TEST_MODULES`, whose value must match the test
filename without `.py` (e.g. `tb_systolic` for `tb_systolic.py`).

## 3. Work completed

### 3.1 Baugh--Wooley-style multiplier

**File:** `rtl/arithmetic/mult_array_8x8.v`

The module takes signed 8-bit operands and outputs a signed 16-bit
product. It constructs eight shifted partial-product rows, inverts the
sign-related partial products, and adds a compensation constant:

``` verilog
wire [15:0] bw_constant = 16'h8100;
assign prod_out =
    pp0 + pp1 + pp2 + pp3 + pp4 + pp5 + pp6 + pp7 + bw_constant;
```

The RTL does not use the behavioral `*` operator. The result is a
combinational signed product.

**Architecture caveat:** this is a Baugh--Wooley-style partial-product
implementation, but its rows are summed with a chain of `+` operators
rather than an explicitly instantiated regular array of half/full
adders. Functional correctness is distinct from proving a particular
synthesized gate topology.

**Test result:** the exhaustive multiplier test iterated all 65,536
pairs ((a,b)) for (a,b`\in[-128,127]`{=tex}), comparing the RTL result
to Python's `a*b`. The observed result was `PASS=1, FAIL=0`; simulation
time was `131072 ns` (2 ns per case). See Section 5 before claiming that
both multiplier architectures passed.

### 3.2 Booth--Wallace multiplier source

**File:** `rtl/arithmetic/mult_booth_8x8.v`

The supplied code implements: 1. Radix-4 Booth recoding into four
overlapping 3-bit groups. 2. Partial-product choices `0`, `+A`, `+2A`,
`-A`, `-2A`. 3. Sign extension and shifts by 0, 2, 4, and 6 bits. 4. A
correction row adding the `+1` terms for two's-complement negative
partial products. 5. Three levels of bitwise 3:2 compressor logic (sum
via XOR, carry via the majority function), then a final addition.

The file was added to the Icarus source list and compiled. **Independent
functional verification of this Booth module is not established by the
current evidence.** The wrapper-selection issue described in Section 5
must be fixed first.

### 3.3 Multiplier wrapper

**File:** `rtl/arithmetic/multiplier_top.v`

It provides a shared signed 8-bit input / signed 16-bit output interface
and an `ARCH` parameter. However, the version shown during development
instantiated only `mult_array_8x8`, regardless of `ARCH`:

``` verilog
mult_array_8x8 u_array (
    .a_in(a_in),
    .b_in(b_in),
    .prod_out(prod_out)
);
```

Therefore, setting `-Pmultiplier_top.ARCH="BOOTH_WALLACE"` does not
itself select Booth. A generate/conditional branch or a direct Booth
test top is required. Until then, do not claim Booth passed exhaustive
testing or that grid tests exercised Booth.

### 3.4 Processing element (PE)

**File:** `rtl/core/pe.v`

Interface includes clock, active-low asynchronous reset, weight
enable/input, activation input, 26-bit partial-sum input, registered
activation output, and registered 26-bit partial-sum output. The `ARCH`
parameter is passed to `multiplier_top`.

Behavior: 1. `weight_reg` captures `w_in` on a rising edge when
`weight_en` is high. 2. The multiplier uses `a_in` and the stored
weight. 3. `next_psum = psum_in + mult_out`. 4. On the rising edge,
`a_out <= a_in` and `psum_out <= next_psum`. 5. Asynchronous reset
clears the stored weight and registered outputs.

**Test result:** directed PE tests passed for asynchronous reset, weight
loading, positive multiplication/forwarding, negative activation
multiplication, weight retention, weight-update timing, and reset after
operation. Observed `PASS=1, FAIL=0`, simulation time `65 ns`. This was
a directed test, not exhaustive PE sequence verification.

### 3.5 Requantizer

**File:** `rtl/core/requantizer.v`

Inputs are signed 26-bit accumulator and 5-bit shift value; output is
signed INT8. Current intended operations: 1. Add (2\^{shift-1}) when
`shift_val > 0`. 2. Arithmetic right shift by `shift_val`. 3. Apply ReLU
(negative values become zero). 4. Clamp values above 127 to 127;
otherwise use the low 8 bits.

**Status:** source exists, but no dedicated test result has been
recorded. Test shift 0 and large shifts, rounding boundaries, negative
inputs, zero, 127, and saturation. The exact rounding behavior for
negative values should be documented.

### 3.6 Activation skew registers

**File:** `rtl/core/skew_registers.v`

-   Row 0: direct pass-through (0 register cycles).
-   Row 1: one register stage.
-   Row 2: two stages.
-   Row 3: three stages.

Stages asynchronously reset and update only when `en` is high, so they
hold their state while `en=0`.

**Status:** included in the grid and indirectly exercised by grid
simulations, but there is no standalone test of exact delays, reset, or
disabled-cycle hold behavior yet.

### 3.7 4×4 systolic grid

**File:** `rtl/core/systolic_grid_4x4.v`

The grid instantiates 16 PEs: - Four activation inputs pass through
row-skew logic and move horizontally through registered PEs. - Four
26-bit partial-sum inputs enter at the top, one per column. - Each PE
adds its product to the incoming partial sum and registers the result to
the PE below. - Four outputs expose the bottom-row partial sums.

**Weight loading:** four buses provide one weight per column.
`weight_en_row` selects a row, so one row of four PE weights is loaded
per cycle. Once enables are low, changing the external buses should not
affect stored weights.

**Observed timing:** with the current test schedule, bottom output
columns were observed staggered at sample indices 3, 4, 5, and 6. This
is an observed property of the current RTL and test---not yet a general,
documented protocol for arbitrary streaming.

**Limitations:** there is no output-valid signal or controller. Current
grid tests send one vector, then zeros to flush the pipeline. They do
not prove back-to-back streaming, arbitrary stalls, or a complete
matrix-multiplication tile schedule.

## 4. Current grid testbench and its result

**File:** `sim/tb_systolic.py`

The latest version is a directed regression with: - `signed_value` and
`read_outputs` helpers. - `matvec(a, w)` Python reference calculation
(y_j=`\sum`{=tex}*k a_k w*{kj}). - A `cycle` helper to drive inputs and
apply a rising edge. - An asynchronous reset helper. - Row-by-row weight
loading, followed by changing the weight buses with enables low to
exercise retention. - Isolated vectors followed by zero cycles to flush
the pipeline. - Column checks at the observed staggered sample indices.

Three weight matrices were tested:

Tile 0:

``` text
[ 1,  2,  0,  1]
[ 0,  1,  1,  0]
[ 2,  0,  1,  1]
[ 1,  1,  0,  2]
```

Tile 1:

``` text
[-1,  2,  0,  1]
[ 0, -2,  1,  0]
[ 2,  0, -1,  1]
[ 1,  1,  0, -2]
```

Tile 2:

``` text
[-1, -2, -3, -4]
[-2, -1, -4, -3]
[-3, -4, -1, -2]
[-4, -3, -2, -1]
```

Each tile was tested against these six vectors:

``` text
[1, 2, 3, 4]
[2, 0, 1, 3]
[-1, 2, -3, 4]
[0, 0, 0, 0]
[127, -128, 1, -1]
[-128, 127, -128, 127]
```

Python calculates expected values from each vector and matrix
independently. The test injects a vector once, then uses zeros to flush
the pipeline; it checks each output column at its expected observed
sample index.

**Latest observed result:**

``` text
ALL GRID REGRESSION CASES PASSED: 18 vector cases
tb_systolic.test_grid_regression passed
TESTS=1 PASS=1 FAIL=0 SKIP=0
```

Simulation time: `1773 ns`.

This supports correctness for those 18 directed vector/tile combinations
under the tested schedule. It does not establish arbitrary tile
correctness, continuous throughput, or a general timing protocol.

## 5. Critical caveat: Booth selection has not been demonstrated

The Makefile contained a parameter override similar to:

``` makefile
COMPILE_ARGS += -Pmultiplier_top.ARCH=\"BOOTH_WALLACE\"
```

But the wrapper code shown above hard-wired the array multiplier. A
parameter override changes a parameter's value; it does not
automatically change the instantiated module.

Consequently: - The exhaustive test demonstrates correctness of the
multiplier actually selected in that run. - It must not be reported as
proof that both architectures passed unless the wrapper/test top is
confirmed to select each one separately. - The grid regression similarly
cannot be claimed as a Booth-grid test while the wrapper is hard-wired
to the array implementation.

**Required action:** add explicit architecture selection to
`multiplier_top.v`, or instantiate each multiplier directly as a
separate simulation top. Then run the exhaustive signed INT8 test
independently against both architectures, and run the PE/grid regression
for both selections.

## 6. File-status snapshot

Based on the code and logs discussed; inspect the repository before
assuming anything not confirmed here is empty.

  -----------------------------------------------------------------------
  File                                Status at this checkpoint
  ----------------------------------- -----------------------------------
  `rtl/arithmetic/mult_array_8x8.v`   Implemented; exhaustive test
                                      reported passing

  `rtl/arithmetic/mult_booth_8x8.v`   Source exists; independent
                                      verification not established

  `rtl/arithmetic/multiplier_top.v`   Wrapper exists; architecture
                                      selection needs fixing

  `rtl/core/pe.v`                     Implemented; directed test passed

  `rtl/core/skew_registers.v`         Implemented; standalone test
                                      pending

  `rtl/core/systolic_grid_4x4.v`      Implemented; 18 directed vector
                                      cases passed

  `rtl/core/requantizer.v`            Implemented; dedicated test pending

  `rtl/control/controller_fsm.v`      Not implemented yet, per latest
                                      user update

  `rtl/control/accum_buffer.v`        Not implemented yet

  `rtl/control/buffer_ram.v`          Not implemented yet

  `rtl/top/sysmac8_top.v`             Empty at last check

  `rtl/top/argmax.v`                  Not implemented / not confirmed

  `sim/tb_multiplier.py`              Exhaustive test exists; retest with
                                      explicit architecture selection

  `sim/tb_systolic.py`                Directed grid regression; 18 cases
                                      passed

  `sim/Makefile`                      Icarus/Cocotb setup and grid
                                      sources configured

  `model/train_mnist.py`              Implementation not confirmed

  `model/quantize.py`                 Implementation not confirmed

  `model/golden_model.py`             Implementation not confirmed

  `syn/run_synth.tcl`                 Implementation not confirmed
  -----------------------------------------------------------------------

## 7. Current Makefile

The latest supplied Makefile was:

``` makefile
SIM ?= icarus
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../rtl/arithmetic/multiplier_top.v
VERILOG_SOURCES += $(PWD)/../rtl/arithmetic/mult_array_8x8.v
VERILOG_SOURCES += $(PWD)/../rtl/arithmetic/mult_booth_8x8.v
VERILOG_SOURCES += $(PWD)/../rtl/core/pe.v
VERILOG_SOURCES += $(PWD)/../rtl/core/skew_registers.v
VERILOG_SOURCES += $(PWD)/../rtl/core/systolic_grid_4x4.v

COMPILE_ARGS += -Pmultiplier_top.ARCH=\"BOOTH_WALLACE\"

TOPLEVEL = systolic_grid_4x4
COCOTB_TEST_MODULES = tb_systolic

include $(shell cocotb-config --makefiles)/Makefile.sim
```

Once wrapper selection is fixed, make the intended architecture explicit
in separate test targets or invocations. The current override is
misleading if the wrapper ignores `ARCH`.

## 8. Git handoff

Do not assume the changes have been committed or pushed. In Windows
PowerShell:

``` powershell
cd C:\Users\chopr\sysmac8
git status
git diff
git remote -v
```

Review what will be committed. Source files (`.v`, `.py`, Makefile,
`.md`, authored `.tcl`) should be tracked. Usually ignore: - `.venv/` -
`sim/sim_build/` - `results.xml` - Python `__pycache__/` - generated
waveforms and temporary simulator/synthesis outputs.

After adding this document to the repository root as
`PROJECT_PROGRESS_SUMMARY.md`, stage and inspect the intended changes:

``` powershell
git add rtl sim
git add PROJECT_PROGRESS_SUMMARY.md
git status
git diff --cached
git commit -m "Document multiplier and systolic-grid verification"
git push
```

If the document is stored elsewhere, adjust the path. Do not push until
the staged diff contains the intended source/tests/documentation and
excludes local build products and the virtual environment.

## 9. Recommended order of remaining work

1.  Fix wrapper architecture selection and independently exhaustively
    verify both multipliers.
2.  Add dedicated `requantizer.v` tests: shift 0, representative shifts,
    rounding boundaries, ReLU, 0/127 and saturation.
3.  Add dedicated `skew_registers.v` tests for 0/1/2/3-cycle delays,
    reset, and disabled-cycle hold.
4.  Document and verify a general grid timing schedule; test
    back-to-back traffic if required by the design.
5.  Re-run PE and grid tests for both multiplier architectures.
6.  Implement and test the controller and buffers.
7.  Integrate `sysmac8_top.v` and argmax.
8.  Implement the Python quantization/golden model.
9.  Run cycle-accurate RTL inference on the target MNIST subset.
10. Synthesize both verified architectures with controlled settings and
    compare area/timing/power.

## 10. Handoff summary

The Baugh--Wooley-style multiplier passed an exhaustive signed INT8
test; the PE passed directed functionality tests; and the current 4×4
grid passed 18 directed vector cases across three weight tiles,
including signed values and INT8 boundary inputs. The simulation
toolchain is working.

The most important outstanding correctness issue is proving that the
Booth implementation is actually selected and independently correct.
Requantizer and skew-register standalone tests are also outstanding. The
grid regression uses isolated vectors with pipeline flushing, so it does
not yet prove uninterrupted streaming or every possible matrix tile.

This is the current defensible checkpoint: meaningful progress on the
arithmetic/PE/grid datapath, with explicit verification limits and a
concrete path to completion.