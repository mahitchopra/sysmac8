"""
SysMAC8 integer golden model.

Network:
    Input:  784 unsigned pixel values, stored as INT8 bit patterns [0, 127]
    FC1:    784 -> 32, signed INT8 weights, signed 26-bit accumulators
    ReLU:   right shift, rounding offset, ReLU, saturation to [0, 127]
    FC2:    32 -> 10, signed INT8 weights, signed 26-bit accumulators
    Output: 10 integer logits; argmax selects the predicted class

Expected files in model/data/:
    w1.hex          32 * 784 INT8 words
    b1.hex          32 signed 26-bit words
    w2.hex          10 * 32 INT8 words
    b2.hex          10 signed 26-bit words
    sample_img.hex  784 INT8 words

Run from repository root:
    python -m model.golden_model

This model uses the quantized files exported by quantize.py.
It does not load or depend on the FP32 checkpoint.
"""
from pathlib import Path
import sys
import torch

# 1. Architecture and numeric constants
INPUT_SIZE = 784
HIDDEN_SIZE = 32
OUTPUT_SIZE = 10

INT8_BITS = 8
ACC_BITS = 26

INT8_MIN = -(1 << (INT8_BITS - 1))
INT8_MAX = (1 << (INT8_BITS - 1)) - 1

ACC_MIN = -(1 << (ACC_BITS - 1))
ACC_MAX = (1 << (ACC_BITS - 1)) - 1

ACT_MIN = 0
ACT_MAX = 127

# Must match the shift exported by quantize.py.
# The CLI loads this from quantization.txt.
DEFAULT_SHIFT1 = 12

DATA_DIR = Path(__file__).resolve().parent / "data"

# 2. Hexadecimal file loading
def decode_signed(value, bits):
    """Decode a low-bits two's-complement integer as signed."""
    value = int(value)
    mask = (1 << bits) - 1
    value &= mask

    sign_bit = 1 << (bits - 1)

    if value & sign_bit:
        value -= 1 << bits

    return value

def read_hex_file(path, bits, expected_count):
    """
    Read one fixed-width hexadecimal word per line.

    For 26-bit words, only the low 26 bits are meaningful.
    Blank lines and comment lines beginning with # are ignored.
    """
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")

    values = []

    with path.open("r", encoding="ascii") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if line.lower().startswith("0x"):
                line = line[2:]

            try:
                raw_value = int(line, 16)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid hex value in {path}, line {line_number}: "
                    f"{line!r}"
                ) from exc

            values.append(decode_signed(raw_value, bits))

    if len(values) != expected_count:
        raise ValueError(
            f"{path}: expected {expected_count} values, "
            f"found {len(values)}"
        )

    return torch.tensor(values, dtype=torch.int64)


def load_parameters(data_dir=DATA_DIR):
    """Load the exported parameters and reshape them to matrix form."""
    data_dir = Path(data_dir)

    w1 = read_hex_file(
        data_dir / "w1.hex",
        bits=8,
        expected_count=HIDDEN_SIZE * INPUT_SIZE
    ).reshape(HIDDEN_SIZE, INPUT_SIZE)

    b1 = read_hex_file(
        data_dir / "b1.hex",
        bits=26,
        expected_count=HIDDEN_SIZE
    )

    w2 = read_hex_file(
        data_dir / "w2.hex",
        bits=8,
        expected_count=OUTPUT_SIZE * HIDDEN_SIZE
    ).reshape(OUTPUT_SIZE, HIDDEN_SIZE)

    b2 = read_hex_file(
        data_dir / "b2.hex",
        bits=26,
        expected_count=OUTPUT_SIZE
    )

    return w1, b1, w2, b2


def load_sample_image(data_dir=DATA_DIR):
    """Load the flattened, quantized 784-pixel sample image."""
    return read_hex_file(
        Path(data_dir) / "sample_img.hex",
        bits=8,
        expected_count=INPUT_SIZE
    )


def load_shift(data_dir=DATA_DIR):
    """Read layer1_right_shift from quantization.txt."""
    metadata_path = Path(data_dir) / "quantization.txt"

    if not metadata_path.is_file():
        raise FileNotFoundError(
            f"Missing quantization metadata: {metadata_path}"
        )

    metadata = {}

    with metadata_path.open("r", encoding="ascii") as f:
        for line in f:
            line = line.strip()

            if not line or "=" not in line:
                continue

            key, value = line.split("=", 1)
            metadata[key.strip()] = value.strip()

    if "layer1_right_shift" not in metadata:
        raise ValueError(
            "quantization.txt does not contain layer1_right_shift"
        )

    shift = int(metadata["layer1_right_shift"])

    if not 0 <= shift <= 31:
        raise ValueError(
            f"Layer 1 shift {shift} cannot be represented by the RTL."
        )

    return shift


# ============================================================
# 3. Hardware arithmetic helpers
# ============================================================

def check_accumulator(acc, name="accumulator"):
    """Raise an error if values exceed signed 26-bit range."""
    acc_min = int(acc.min().item())
    acc_max = int(acc.max().item())

    if acc_min < ACC_MIN or acc_max > ACC_MAX:
        raise OverflowError(
            f"{name} exceeds signed {ACC_BITS}-bit range: "
            f"[{acc_min}, {acc_max}]"
        )


def wrap_signed(value, bits):
    """
    Model fixed-width two's-complement wraparound.

    Normal inference should pass the accumulator bounds checks,
    so wrapping should not change valid results.
    """
    mask = (1 << bits) - 1
    value = value & mask
    sign_bit = 1 << (bits - 1)

    if value & sign_bit:
        value -= 1 << bits

    return value

def requantize(acc, shift):
    """
    Match the current RTL requantizer:

        round_add = 2**(shift - 1), if shift > 0
        scaled = (acc + round_add) >>> shift
        ReLU
        clamp to [0, 127]

    The RTL uses a signed 26-bit accumulator. This function checks
    the input and the addition before applying the shift.
    """
    if not 0 <= shift <= 31:
        raise ValueError(f"Unsupported right shift: {shift}")

    check_accumulator(acc, "requantizer input")

    round_add = (1 << (shift - 1)) if shift > 0 else 0
    rounded = acc + round_add

    check_accumulator(rounded, "requantizer rounding addition")

    # torch's right shift on signed integer tensors is arithmetic.
    scaled = torch.bitwise_right_shift(rounded, shift)

    return scaled.clamp(ACT_MIN, ACT_MAX)

# 4. Golden-model inference
def infer_integer(image, w1, b1, w2, b2, shift1):
    """
    Run one image through the quantized integer network.

    Args:
        image: 784 quantized input pixels, values 0..127.
        w1:    [32, 784] signed integer weights.
        b1:    [32] signed integer biases.
        w2:    [10, 32] signed integer weights.
        b2:    [10] signed integer biases.
        shift1: Layer 1 right-shift amount.

    Returns:
        A dictionary containing:
            acc1:   first-layer pre-requantization accumulators
            act1:   first-layer quantized activations
            acc2:   final integer logits
            pred:   predicted class (0..9)
    """
    image = torch.as_tensor(image, dtype=torch.int64).reshape(-1)

    if image.numel() != INPUT_SIZE:
        raise ValueError(
            f"Expected {INPUT_SIZE} input pixels, got {image.numel()}"
        )

    if torch.any(image < 0) or torch.any(image > 127):
        raise ValueError("Input pixels must be in the range [0, 127].")

    if w1.shape != (HIDDEN_SIZE, INPUT_SIZE):
        raise ValueError(f"Unexpected W1 shape: {tuple(w1.shape)}")

    if b1.shape != (HIDDEN_SIZE,):
        raise ValueError(f"Unexpected b1 shape: {tuple(b1.shape)}")

    if w2.shape != (OUTPUT_SIZE, HIDDEN_SIZE):
        raise ValueError(f"Unexpected W2 shape: {tuple(w2.shape)}")

    if b2.shape != (OUTPUT_SIZE,):
        raise ValueError(f"Unexpected b2 shape: {tuple(b2.shape)}")

    # Layer 1: 32 dot products, with bias added exactly once.
    acc1 = w1 @ image + b1
    check_accumulator(acc1, "Layer 1 accumulator")

    # Layer 1 requantization, ReLU and saturation.
    act1 = requantize(acc1, shift1)

    # Layer 2: ten dot products, with bias added exactly once.
    # The logits are kept at their accumulator scale. Since they
    # share one positive scale, argmax is unchanged.
    acc2 = w2 @ act1 + b2
    check_accumulator(acc2, "Layer 2 accumulator")

    prediction = int(torch.argmax(acc2).item())

    return {
        "acc1": acc1,
        "act1": act1,
        "acc2": acc2,
        "pred": prediction,
    }

# 5. CLI self-test
def main():
    print("SysMAC8 integer golden model")
    print("-" * 50)

    w1, b1, w2, b2 = load_parameters()
    image = load_sample_image()
    shift1 = load_shift()

    print(f"Loaded W1: {tuple(w1.shape)}")
    print(f"Loaded b1: {tuple(b1.shape)}")
    print(f"Loaded W2: {tuple(w2.shape)}")
    print(f"Loaded b2: {tuple(b2.shape)}")
    print(f"Loaded input pixels: {image.numel()}")
    print(f"Layer 1 right shift: {shift1}")

    result = infer_integer(image, w1, b1, w2, b2, shift1)

    print("\nInteger inference results")
    print(f"Layer 1 accumulator range: "
          f"[{int(result['acc1'].min())}, {int(result['acc1'].max())}]")
    print(f"Layer 1 activations: {result['act1'].tolist()}")
    print(f"Layer 2 logits: {result['acc2'].tolist()}")
    print(f"Predicted class: {result['pred']}")

    # Repeated execution must be deterministic.
    repeated = infer_integer(image, w1, b1, w2, b2, shift1)

    assert torch.equal(result["acc1"], repeated["acc1"])
    assert torch.equal(result["act1"], repeated["act1"])
    assert torch.equal(result["acc2"], repeated["acc2"])
    assert result["pred"] == repeated["pred"]

    print("\nPASS: parameter loading and deterministic inference.")
    print(
        "Next: compare these intermediate integer values with the "
        "Cocotb/Verilog outputs."
    )

if __name__ == "__main__":
    main()