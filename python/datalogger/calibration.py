import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd

# ── Config ─────────────────────────────────────────────────────────────────────
SENSOR_ID   = "s2"
DATA_FILE   = "./python/v2_sensor/calibration_s2_20260520-102905.csv"
MODEL_OUT   = f"./python/v2_sensor/models/{SENSOR_ID}.pth"
INPUT_COLS  = ["S0_L0", "S0_L1", "S0_L2", "S0_L3"]
OUTPUT_COLS = ["Tx", "Ty", "Tz"]

EPOCHS      = 2000
BATCH_SIZE  = 64
LR          = 1e-3
TEST_SIZE   = 0.2
RANDOM_SEED = 42
LOSS_PLOT   = True   # set False to skip matplotlib loss curves

# ── Architectures to benchmark ─────────────────────────────────────────────────
# (name, hidden_layers, activation)
ARCHITECTURES = [
    ("Small-ReLU",      [64, 64],             "relu"),
    ("Medium-ReLU",     [128, 128, 64],        "relu"),
    ("Large-ReLU",      [256, 128, 64, 32],    "relu"),
    ("Medium-Tanh",     [128, 128, 64],        "tanh"),
    ("Medium-ELU",      [128, 128, 64],        "elu"),
    ("Wide-ReLU",       [512, 256],            "relu"),
    ("Deep-ReLU",       [64, 64, 64, 64, 64],  "relu"),
    ("Medium-Dropout",  [128, 128, 64],        "relu"),  # adds dropout
]



# ── Model builder ──────────────────────────────────────────────────────────────
class FlexNet(nn.Module):
    def __init__(self, input_size, output_size, hidden_layers, activation, dropout=0.0):
        super().__init__()
        act_fn = {"relu": nn.ReLU, "tanh": nn.Tanh, "elu": nn.ELU}[activation]
        layers = []
        prev = input_size
        for h in hidden_layers:
            layers.append(nn.Linear(prev, h))
            layers.append(act_fn())
            if dropout > 0:
                layers.append(nn.Dropout(dropout))
            prev = h
        layers.append(nn.Linear(prev, output_size))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


# ── Load & preprocess data ─────────────────────────────────────────────────────
print(f"Loading {DATA_FILE}")
data = pd.read_csv(DATA_FILE, header=0)

X_raw = data[INPUT_COLS].values.astype(np.float32)
y_raw = data[OUTPUT_COLS].values.astype(np.float32)

X_train_raw, X_test_raw, y_train_raw, y_test_raw = train_test_split(
    X_raw, y_raw, test_size=TEST_SIZE, random_state=RANDOM_SEED
)

scaler_X = StandardScaler().fit(X_train_raw)
scaler_y = StandardScaler().fit(y_train_raw)

X_train = torch.tensor(scaler_X.transform(X_train_raw), dtype=torch.float32)
X_test  = torch.tensor(scaler_X.transform(X_test_raw),  dtype=torch.float32)
y_train = torch.tensor(scaler_y.transform(y_train_raw), dtype=torch.float32)
y_test  = torch.tensor(scaler_y.transform(y_test_raw),  dtype=torch.float32)

print(f"Train: {len(X_train)} samples  |  Test: {len(X_test)} samples")

# ── Device ─────────────────────────────────────────────────────────────────────
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {DEVICE}" + (f"  ({torch.cuda.get_device_name(0)})" if DEVICE.type == "cuda" else "  (no CUDA GPU found)"))
print()

X_train = X_train.to(DEVICE)
X_test  = X_test.to(DEVICE)
y_train = y_train.to(DEVICE)
y_test  = y_test.to(DEVICE)


# ── Train & evaluate one architecture ─────────────────────────────────────────
def train_and_evaluate(name, hidden_layers, activation):
    dropout = 0.2 if "Dropout" in name else 0.0
    model = FlexNet(len(INPUT_COLS), len(OUTPUT_COLS), hidden_layers, activation, dropout).to(DEVICE)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=LR)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=100, factor=0.5
    )

    n = X_train.size(0)
    train_losses, test_losses = [], []

    for epoch in range(EPOCHS):
        model.train()
        perm = torch.randperm(n)
        epoch_loss = 0.0
        for i in range(0, n, BATCH_SIZE):
            idx = perm[i:i + BATCH_SIZE]
            optimizer.zero_grad()
            loss = criterion(model(X_train[idx]), y_train[idx])
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
        scheduler.step(epoch_loss)

        # Record losses every 10 epochs (scaled loss, not mm)
        if (epoch + 1) % 10 == 0:
            model.eval()
            with torch.no_grad():
                tl = criterion(model(X_train), y_train).item()
                vl = criterion(model(X_test),  y_test).item()
            train_losses.append(tl)
            test_losses.append(vl)
            model.train()

        if (epoch + 1) % 100 == 0:
            print(f"  [{name}] {epoch+1:>4}/{EPOCHS}  train={train_losses[-1]:.5f}  test={test_losses[-1]:.5f}")

    # Evaluate in mm
    model.eval()
    with torch.no_grad():
        y_pred_mm  = scaler_y.inverse_transform(model(X_test).cpu().numpy())
        y_train_mm = scaler_y.inverse_transform(model(X_train).cpu().numpy())

    rmse_test  = float(np.sqrt(np.mean((y_pred_mm  - y_test_raw)  ** 2)))
    rmse_train = float(np.sqrt(np.mean((y_train_mm - y_train_raw) ** 2)))
    overfit_ratio = rmse_test / rmse_train if rmse_train > 0 else float("inf")

    per_axis = np.sqrt(np.mean((y_pred_mm - y_test_raw) ** 2, axis=0))
    return model, rmse_test, rmse_train, overfit_ratio, per_axis, train_losses, test_losses


# ── Run all architectures ──────────────────────────────────────────────────────
results    = []
best_rmse  = float("inf")
best_model = None
best_name  = ""

print(f"Training {len(ARCHITECTURES)} architectures in parallel...\n")

all_train_losses = {}
all_test_losses  = {}

def train_task(arch):
    arch_name, hidden, act = arch
    model, rmse_test, rmse_train, ratio, per_axis, tl, vl = train_and_evaluate(arch_name, hidden, act)
    return arch_name, model, rmse_test, rmse_train, ratio, per_axis, tl, vl

with ThreadPoolExecutor(max_workers=len(ARCHITECTURES)) as executor:
    futures = {executor.submit(train_task, arch): arch[0] for arch in ARCHITECTURES}
    for future in as_completed(futures):
        arch_name, model, rmse_test, rmse_train, ratio, per_axis, tl, vl = future.result()
        results.append((arch_name, rmse_test, rmse_train, ratio, per_axis))
        all_train_losses[arch_name] = tl
        all_test_losses[arch_name]  = vl
        flag = " ◄ best so far" if rmse_test < best_rmse else ""
        print(f"  {arch_name:<22} test={rmse_test:.4f}  train={rmse_train:.4f}  ratio={ratio:.2f}  "
              f"{per_axis[0]:.4f}/{per_axis[1]:.4f}/{per_axis[2]:.4f}{flag}")
        if rmse_test < best_rmse:
            best_rmse  = rmse_test
            best_model = model
            best_name  = arch_name

# ── Summary table ──────────────────────────────────────────────────────────────
print("\n── Final Results (sorted by test RMSE) ────────────────────────────────")
print(f"{'Architecture':<22} {'Test RMSE':>10} {'Train RMSE':>11} {'Ratio':>7}  Overfit?")
print("-" * 70)
for arch_name, rmse_test, rmse_train, ratio, _ in sorted(results, key=lambda r: r[1]):
    overfit = "YES" if ratio > 1.3 else "ok"
    marker  = " ◄ BEST" if arch_name == best_name else ""
    print(f"{arch_name:<22} {rmse_test:>10.4f} {rmse_train:>11.4f} {ratio:>7.2f}  {overfit}{marker}")

# ── Loss curves ────────────────────────────────────────────────────────────────
if LOSS_PLOT:
    import matplotlib.pyplot as plt
    epochs_axis = [(e + 1) * 10 for e in range(len(next(iter(all_train_losses.values()))))]
    n_arch = len(ARCHITECTURES)
    cols = 2
    rows = (n_arch + 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(14, 4 * rows), sharex=True)
    axes = axes.flatten()
    for ax, (arch_name, _, _, _, _) in zip(axes, results):
        ax.plot(epochs_axis, all_train_losses[arch_name], label="Train")
        ax.plot(epochs_axis, all_test_losses[arch_name],  label="Test", linestyle="--")
        ax.set_title(arch_name)
        ax.set_xlabel("Epoch")
        ax.set_ylabel("MSE Loss (scaled)")
        ax.legend(fontsize=8)
        ax.set_yscale("log")
    for ax in axes[n_arch:]:
        ax.set_visible(False)
    fig.suptitle(f"Train vs Test Loss — {SENSOR_ID}", fontsize=13)
    fig.tight_layout()
    plt.savefig(f"../v2_sensor/models/{SENSOR_ID}_loss_curves.png", dpi=150)
    print(f"\nLoss curves saved to ../v2_sensor/models/{SENSOR_ID}_loss_curves.png")
    plt.show()

# ── Save best model ────────────────────────────────────────────────────────────
print(f"\nBest: {best_name}  (RMSE = {best_rmse:.4f} mm)")
import os; os.makedirs(os.path.dirname(MODEL_OUT), exist_ok=True)
torch.save(best_model.state_dict(), MODEL_OUT)
print(f"Saved to {MODEL_OUT}")



