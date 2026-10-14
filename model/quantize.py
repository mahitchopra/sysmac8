import os
import torch
import torch.nn as nn
import numpy as np
from torchvision import datasets, transforms
from torch.utils.data import DataLoader

# 1. Model definition: must match train_mnist.py exactly
class SysMAC8Model(nn.Module):
    def __init__(self):
        super(SysMAC8Model, self).__init__()
        self.flatten = nn.Flatten()
        self.fc1 = nn.Linear(784, 32, bias=True)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(32, 10, bias=True)

    def forward(self, x):
        x = self.flatten(x)
        x = self.fc1(x)
        x = self.relu(x)
        x = self.fc2(x)
        return x

# 2. Quantization helpers
INT8_MIN = -128
INT8_MAX = 127

ACC_BITS = 26
ACC_MIN = -(1 << (ACC_BITS - 1))
ACC_MAX = (1 << (ACC_BITS - 1)) - 1

# The current RTL requantizer has a 5-bit shift input.
SHIFT_MIN = 0
SHIFT_MAX = 31


def get_po2_scale(tensor, max_val=127.0):
    """
    Return (scale, exponent), where scale = 2**exponent.

    The scale is rounded UP to a power of two so the largest
    absolute value fits within the requested quantization range.
    """
    abs_max = tensor.detach().abs().max().item()

    if abs_max == 0:
        return 1.0, 0

    ideal_scale = abs_max / max_val
    exponent = int(np.ceil(np.log2(ideal_scale)))
    scale = 2.0 ** exponent

    return scale, exponent


def quantize_int8(tensor, scale, name):
    """
    Symmetric signed INT8 quantization.

    The chosen scale should keep values within [-127, 127].
    Clamping to [-128, 127] is retained as a defensive check.
    """
    q = torch.round(tensor.detach() / scale)

    clipped = ((q < INT8_MIN) | (q > INT8_MAX)).sum().item()
    if clipped:
        print(f"WARNING: {name}: {clipped} values require INT8 clipping.")

    return q.clamp(INT8_MIN, INT8_MAX).to(torch.int8)


def quantize_bias(bias, bias_exponent, name):
    """
    Bias integer scale:
        bias_scale = input_scale * weight_scale
        bias_exponent = input_exponent + weight_exponent

    Bias values are stored as signed integers and must fit the
    26-bit accumulator range.
    """
    bias_scale = 2.0 ** bias_exponent
    q = torch.round(bias.detach() / bias_scale)

    out_of_range = ((q < ACC_MIN) | (q > ACC_MAX)).sum().item()
    if out_of_range:
        raise ValueError(
            f"{name}: {out_of_range} bias values exceed signed "
            f"{ACC_BITS}-bit accumulator range. Revisit the scales."
        )

    return q.to(torch.int64)


def to_hex(value, bits):
    """
    Encode an integer as a fixed-width, two's-complement hex word.
    INT8 -> 2 hex digits
    INT26 -> 7 hex digits (only the low 26 bits are encoded)
    """
    value = int(value)
    mask = (1 << bits) - 1
    hex_chars = (bits + 3) // 4
    return f"{value & mask:0{hex_chars}x}"


def write_hex(filename, values, bits):
    """Write one fixed-width hex integer per line."""
    values = values.detach().cpu().reshape(-1)

    with open(filename, "w", encoding="ascii", newline="\n") as f:
        for value in values:
            f.write(to_hex(value.item(), bits) + "\n")


def validate_shift(shift, layer_name):
    """Reject shift values the current RTL cannot represent."""
    if not SHIFT_MIN <= shift <= SHIFT_MAX:
        raise ValueError(
            f"{layer_name}: required right shift is {shift}, but RTL "
            f"supports only {SHIFT_MIN}..{SHIFT_MAX}. "
            "Do not silently truncate this value."
        )


def check_accumulator(acc, layer_name):
    """Check actual accumulator values against signed 26-bit limits."""
    actual_min = int(acc.min().item())
    actual_max = int(acc.max().item())

    print(
        f"{layer_name} accumulator range: "
        f"[{actual_min}, {actual_max}] "
        f"(allowed [{ACC_MIN}, {ACC_MAX}])"
    )

    if actual_min < ACC_MIN or actual_max > ACC_MAX:
        raise OverflowError(
            f"{layer_name}: accumulator overflow in the integer model."
        )


def requantize_reference(acc, shift):
    """
    Software reference for the current RTL behavior:
      1. Add positive rounding offset for nonzero shifts.
      2. Arithmetic right shift.
      3. ReLU.
      4. Saturate to [0, 127].

    This function assumes the accumulator itself has not overflowed.
    """
    validate_shift(shift, "Requantizer")

    if shift > 0:
        round_add = 1 << (shift - 1)
    else:
        round_add = 0

    scaled = torch.bitwise_right_shift(acc + round_add, shift)
    return torch.relu(scaled).clamp(0, INT8_MAX).to(torch.int32)

# 3. Main quantization flow
def main():
    torch.manual_seed(42)

    print("Loading FP32 model...")

    if not os.path.isfile("model.pth"):
        raise FileNotFoundError(
            "model.pth was not found in the current directory. "
            "Run train_mnist.py from the project root first."
        )

    model = SysMAC8Model()
    state = torch.load(
        "model.pth",
        map_location="cpu",
        weights_only=True
    )
    model.load_state_dict(state)
    model.eval()

    # Keep exported files in model/data/.
    output_dir = os.path.join("model", "data")
    os.makedirs(output_dir, exist_ok=True)

    # 4. Input quantization
    # MNIST ToTensor() produces pixel values in [0, 1].
    # q = round(x / 2^-7) maps this range to [0, 127].
    p_in = -7
    s_in = 2.0 ** p_in

    # 5. Calibration on actual MNIST images
    print("Loading MNIST calibration data...")

    transform = transforms.ToTensor()
    calibration_dataset = datasets.MNIST(
        root="./data_mnist",
        train=True,
        download=True,
        transform=transform
    )

    # Use a deterministic subset to keep calibration reproducible.
    calibration_count = min(5000, len(calibration_dataset))
    calibration_subset = torch.utils.data.Subset(
        calibration_dataset,
        range(calibration_count)
    )
    calibration_loader = DataLoader(
        calibration_subset,
        batch_size=128,
        shuffle=False
    )

    activation_chunks = []

    with torch.no_grad():
        for images, _ in calibration_loader:
            images = images.reshape(images.shape[0], -1)
            activations = model.relu(model.fc1(images))
            activation_chunks.append(activations)

    calibration_activations = torch.cat(activation_chunks, dim=0)

    s_a1, p_a1 = get_po2_scale(calibration_activations)

    # Quantize actual calibration activations to assess clipping.
    activation_q_unclipped = torch.round(
        calibration_activations / s_a1
    )
    activation_clipped_count = (
        (activation_q_unclipped < 0)
        | (activation_q_unclipped > INT8_MAX)
    ).sum().item()

    print(f"Calibration images: {calibration_count}")
    print(f"Layer 1 activation scale: {s_a1:g} (2^{p_a1})")
    print(
        "Layer 1 activation values outside [0, 127] before clipping: "
        f"{activation_clipped_count}"
    )

    # 6. Layer 1: 784 -> 32
    W1 = model.fc1.weight.detach()
    b1 = model.fc1.bias.detach()

    s_w1, p_w1 = get_po2_scale(W1)
    W1_q = quantize_int8(W1, s_w1, "W1")

    p_b1 = p_in + p_w1
    b1_q = quantize_bias(b1, p_b1, "b1")

    # acc_int * 2^p_b1 represents the real-valued accumulator.
    # To produce activation integers at scale 2^p_a1, use:
    # right_shift = p_a1 - p_b1.
    shift_val_1 = p_a1 - p_b1
    validate_shift(shift_val_1, "Layer 1")

    print(f"Layer 1 weight scale: {s_w1:g} (2^{p_w1})")
    print(f"Layer 1 bias exponent: {p_b1}")
    print(f"Layer 1 right shift: {shift_val_1}")

    # 7. Layer 2: 32 -> 10
    W2 = model.fc2.weight.detach()
    b2 = model.fc2.bias.detach()

    s_w2, p_w2 = get_po2_scale(W2)
    W2_q = quantize_int8(W2, s_w2, "W2")

    p_b2 = p_a1 + p_w2
    b2_q = quantize_bias(b2, p_b2, "b2")

    # Preserve the output scale of the integer logits. Argmax does
    # not require conversion to an INT8 output if all logits share
    # the same positive scale.
    shift_val_2 = 0

    print(f"Layer 2 weight scale: {s_w2:g} (2^{p_w2})")
    print(f"Layer 2 bias exponent: {p_b2}")
    print(
        "Layer 2 output: raw integer logits; "
        "no output requantization needed for argmax."
    )

    # 8. Export quantized parameters
    print(f"\nExporting files to {output_dir}...")

    write_hex(
        os.path.join(output_dir, "w1.hex"),
        W1_q,
        8
    )
    write_hex(
        os.path.join(output_dir, "b1.hex"),
        b1_q,
        26
    )
    write_hex(
        os.path.join(output_dir, "w2.hex"),
        W2_q,
        8
    )
    write_hex(
        os.path.join(output_dir, "b2.hex"),
        b2_q,
        26
    )

    # Export the first MNIST training image deterministically.
    sample_img, label = calibration_dataset[0]
    sample_img_q = torch.round(
        sample_img.reshape(-1) / s_in
    ).clamp(0, INT8_MAX).to(torch.int8)

    write_hex(
        os.path.join(output_dir, "sample_img.hex"),
        sample_img_q,
        8
    )

    # Export scale metadata for the future testbench and golden model.
    metadata_path = os.path.join(output_dir, "quantization.txt")

    with open(metadata_path, "w", encoding="ascii") as f:
        f.write(f"input_exponent={p_in}\n")
        f.write(f"w1_exponent={p_w1}\n")
        f.write(f"b1_exponent={p_b1}\n")
        f.write(f"activation1_exponent={p_a1}\n")
        f.write(f"layer1_right_shift={shift_val_1}\n")
        f.write(f"w2_exponent={p_w2}\n")
        f.write(f"b2_exponent={p_b2}\n")
        f.write(f"layer2_right_shift={shift_val_2}\n")
        f.write("weight_quantization=symmetric_signed_int8\n")
        f.write("activation_quantization=unsigned_range_0_to_127_in_int8\n")
        f.write("hex_encoding=low_bits_twos_complement_one_word_per_line\n")

    # --------------------------------------------------------
    # 9. Integer software reference and basic checks
    # --------------------------------------------------------

    print("\nRunning integer software reference...")

    # Test the exported arithmetic on the first real MNIST image.
    x_q = sample_img_q.to(torch.int64)
    w1_int = W1_q.to(torch.int64)
    b1_int = b1_q.to(torch.int64)

    # PyTorch weights are [output_neuron, input_feature].
    acc1 = torch.matmul(w1_int, x_q) + b1_int
    check_accumulator(acc1, "Layer 1")

    act1 = requantize_reference(acc1, shift_val_1)

    w2_int = W2_q.to(torch.int64)
    b2_int = b2_q.to(torch.int64)

    acc2 = torch.matmul(w2_int, act1.to(torch.int64)) + b2_int
    check_accumulator(acc2, "Layer 2")

    integer_prediction = int(torch.argmax(acc2).item())

    with torch.no_grad():
        float_logits = model(sample_img.unsqueeze(0))
        float_prediction = int(torch.argmax(float_logits, dim=1).item())

    print(f"Integer reference prediction: {integer_prediction}")
    print(f"FP32 prediction:              {float_prediction}")
    print(
        "Prediction agreement: "
        f"{'YES' if integer_prediction == float_prediction else 'NO'}"
    )
    print(
        "NOTE: Prediction agreement is not proof of bit-exact RTL "
        "equivalence. Cocotb must compare RTL values against this "
        "integer reference."
    )

    print("\nQuantized parameter export complete.")


if __name__ == "__main__":
    main()