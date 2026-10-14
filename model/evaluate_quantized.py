import os
import torch
import torch.nn as nn
import numpy as np
from torchvision import datasets, transforms
from torch.utils.data import DataLoader

# 1. Model definition: identical to train_mnist.py
class SysMAC8Model(nn.Module):
    def __init__(self):
        super().__init__()
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
def get_po2_scale(tensor, max_val=127.0):
    abs_max = tensor.detach().abs().max().item()

    if abs_max == 0:
        return 1.0, 0

    exponent = int(np.ceil(np.log2(abs_max / max_val)))
    return 2.0 ** exponent, exponent

def quantize_int8(tensor, scale):
    return torch.round(tensor / scale).clamp(-128, 127).to(torch.int64)

def main():
    torch.manual_seed(42)
    torch.set_grad_enabled(False)

    print("Loading FP32 checkpoint...")

    if not os.path.isfile("model.pth"):
        raise FileNotFoundError(
            "model.pth not found. Run this script from the project root."
        )

    model = SysMAC8Model()
    model.load_state_dict(
        torch.load("model.pth", map_location="cpu", weights_only=True)
    )
    model.eval()

    transform = transforms.ToTensor()

    # 3. Recreate calibration using the first 5,000 MNIST
    #    training images, matching quantize.py
    print("Preparing calibration dataset...")

    calibration_dataset = datasets.MNIST(
        root="./data_mnist",
        train=True,
        download=True,
        transform=transform
    )

    calibration_loader = DataLoader(
        torch.utils.data.Subset(calibration_dataset, range(5000)),
        batch_size=128,
        shuffle=False
    )

    activation_chunks = []

    for images, _ in calibration_loader:
        images = images.reshape(images.shape[0], -1)
        activation_chunks.append(model.relu(model.fc1(images)))

    calibration_activations = torch.cat(activation_chunks, dim=0)
    s_a1, p_a1 = get_po2_scale(calibration_activations)

    # 4. Quantize model parameters
    p_in = -7
    s_in = 2.0 ** p_in

    W1 = model.fc1.weight.detach()
    b1 = model.fc1.bias.detach()
    W2 = model.fc2.weight.detach()
    b2 = model.fc2.bias.detach()

    s_w1, p_w1 = get_po2_scale(W1)
    s_w2, p_w2 = get_po2_scale(W2)

    W1_q = quantize_int8(W1, s_w1)
    W2_q = quantize_int8(W2, s_w2)

    p_b1 = p_in + p_w1
    p_b2 = p_a1 + p_w2

    b1_q = torch.round(b1 / (2.0 ** p_b1)).to(torch.int64)
    b2_q = torch.round(b2 / (2.0 ** p_b2)).to(torch.int64)

    shift1 = p_a1 - p_b1

    if not 0 <= shift1 <= 31:
        raise ValueError(
            f"Layer 1 shift {shift1} is unsupported by the RTL."
        )

    print("\nQuantization configuration")
    print(f"Input exponent:       {p_in}")
    print(f"Layer 1 weight exp:   {p_w1}")
    print(f"Layer 1 bias exp:     {p_b1}")
    print(f"Layer 1 activation:   {p_a1}")
    print(f"Layer 1 right shift:  {shift1}")
    print(f"Layer 2 weight exp:   {p_w2}")
    print(f"Layer 2 bias exp:     {p_b2}")

    # 5. Load held-out MNIST test set
    print("\nLoading MNIST test set...")

    test_dataset = datasets.MNIST(
        root="./data_mnist",
        train=False,
        download=True,
        transform=transform
    )

    test_loader = DataLoader(
        test_dataset,
        batch_size=128,
        shuffle=False
    )

    total = 0
    fp32_correct = 0
    integer_correct = 0
    disagreements = 0

    negative_before_relu_total = 0
    positive_overflow_total = 0
    total_activations = 0

    disagreement_examples = []

    acc_min = -(1 << 25)
    acc_max = (1 << 25) - 1

    acc1_observed_min = None
    acc1_observed_max = None
    acc2_observed_min = None
    acc2_observed_max = None

    print("Evaluating both models...")

    # 6. Test loop
    for images, labels in test_loader:
        batch_size = images.shape[0]
        x_float = images.reshape(batch_size, -1)

        # Floating-point inference
        float_logits = model(x_float)
        float_pred = float_logits.argmax(dim=1)

        # Quantized input pixels
        x_q = torch.round(
            x_float / s_in
        ).clamp(0, 127).to(torch.int64)

        # Layer 1: integer MAC with bias
        acc1 = x_q @ W1_q.T + b1_q

        batch_min = int(acc1.min().item())
        batch_max = int(acc1.max().item())

        acc1_observed_min = (
            batch_min if acc1_observed_min is None
            else min(acc1_observed_min, batch_min)
        )
        acc1_observed_max = (
            batch_max if acc1_observed_max is None
            else max(acc1_observed_max, batch_max)
        )

        # Hardware rounding and arithmetic right shift
        round_add = (1 << (shift1 - 1)) if shift1 > 0 else 0

        activation_unclipped = torch.bitwise_right_shift(
            acc1 + round_add,
            shift1
        )

        # Negative values are expected before ReLU.
        negative_before_relu_total += (
            activation_unclipped < 0
        ).sum().item()

        # Only positive values above 127 are upper-saturated.
        positive_overflow_total += (
            activation_unclipped > 127
        ).sum().item()

        total_activations += activation_unclipped.numel()

        # ReLU followed by upper saturation
        a1_q = activation_unclipped.clamp(0, 127)

        # Layer 2: integer MAC with bias
        acc2 = a1_q @ W2_q.T + b2_q

        batch_min = int(acc2.min().item())
        batch_max = int(acc2.max().item())

        acc2_observed_min = (
            batch_min if acc2_observed_min is None
            else min(acc2_observed_min, batch_min)
        )
        acc2_observed_max = (
            batch_max if acc2_observed_max is None
            else max(acc2_observed_max, batch_max)
        )

        integer_pred = acc2.argmax(dim=1)

        fp32_correct += (float_pred == labels).sum().item()
        integer_correct += (integer_pred == labels).sum().item()

        mismatch = float_pred != integer_pred
        disagreements += mismatch.sum().item()

        if mismatch.any():
            for idx in torch.where(mismatch)[0].tolist():
                if len(disagreement_examples) < 20:
                    disagreement_examples.append({
                        "index": total + idx,
                        "label": int(labels[idx]),
                        "fp32": int(float_pred[idx]),
                        "integer": int(integer_pred[idx])
                    })

        total += batch_size

    # 7. Results
    fp32_accuracy = 100.0 * fp32_correct / total
    integer_accuracy = 100.0 * integer_correct / total
    agreement = 100.0 * (total - disagreements) / total

    negative_rate = (
        100.0 * negative_before_relu_total / total_activations
    )
    positive_overflow_rate = (
        100.0 * positive_overflow_total / total_activations
    )

    print("\n" + "=" * 60)
    print("MNIST TEST RESULTS")
    print("=" * 60)
    print(f"Test images:                    {total}")
    print(f"FP32 accuracy:                  {fp32_accuracy:.2f}%")
    print(f"Integer accuracy:               {integer_accuracy:.2f}%")
    print(f"Prediction disagreements:       {disagreements}/{total}")
    print(f"Prediction agreement:           {agreement:.2f}%")

    print("\nActivation diagnostics")
    print(
        f"Negative values zeroed by ReLU: "
        f"{negative_before_relu_total}/{total_activations} "
        f"({negative_rate:.4f}%)"
    )
    print(
        f"Positive values saturated at 127: "
        f"{positive_overflow_total}/{total_activations} "
        f"({positive_overflow_rate:.4f}%)"
    )

    print("\nAccumulator diagnostics")
    print(
        f"Layer 1 observed range:          "
        f"[{acc1_observed_min}, {acc1_observed_max}]"
    )
    print(
        f"Layer 2 observed range:          "
        f"[{acc2_observed_min}, {acc2_observed_max}]"
    )
    print(f"Signed 26-bit allowed range:     [{acc_min}, {acc_max}]")

    overflow = (
        acc1_observed_min < acc_min
        or acc1_observed_max > acc_max
        or acc2_observed_min < acc_min
        or acc2_observed_max > acc_max
    )

    print(f"Observed 26-bit overflow:        {'YES' if overflow else 'NO'}")
    print("=" * 60)

    if disagreement_examples:
        print("\nFirst prediction disagreements:")
        print("Index | Label | FP32 | Integer")

        for item in disagreement_examples:
            print(
                f"{item['index']:5d} | "
                f"{item['label']:5d} | "
                f"{item['fp32']:4d} | "
                f"{item['integer']:7d}"
            )

    print(
        "\nNote: This is software-level evaluation. "
        "It does not prove bit-exact equivalence against Verilog."
    )


if __name__ == "__main__":
    main()