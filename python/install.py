"""
Install all dependencies for the inductive sensor datalogger.
Run with:  python python/install.py
"""
import subprocess
import sys

# PyTorch CUDA build — change cu126 to match your driver if needed
# Driver >= 525 supports CUDA 12.x  |  check with: nvidia-smi
TORCH_INDEX = "https://download.pytorch.org/whl/cu126"
TORCH_PACKAGES = ["torch", "torchvision"]

OTHER_PACKAGES = [
    "numpy",
    "pandas",
    "scipy",
    "scikit-learn",
    "matplotlib",
    "pyserial",
    "pyqtgraph",
    "PyQt5",
]


def run(cmd):
    print(f"\n> {' '.join(cmd)}")
    subprocess.check_call(cmd)


def main():
    pip = [sys.executable, "-m", "pip", "install", "--upgrade"]

    print("=" * 60)
    print("Installing PyTorch with CUDA 12.6 support...")
    print("=" * 60)
    run(pip + TORCH_PACKAGES + ["--index-url", TORCH_INDEX])

    print("\n" + "=" * 60)
    print(f"Installing {len(OTHER_PACKAGES)} other packages...")
    print("=" * 60)
    run(pip + OTHER_PACKAGES)

    print("\n" + "=" * 60)
    print("Verifying PyTorch CUDA...")
    print("=" * 60)
    subprocess.check_call([sys.executable, "-c", (
        "import torch; "
        "print(f'torch        : {torch.__version__}'); "
        "print(f'CUDA available: {torch.cuda.is_available()}'); "
        "print(f'GPU           : {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"none\"}')"
    )])

    print("\nDone.")


if __name__ == "__main__":
    main()
