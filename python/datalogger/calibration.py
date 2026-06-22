import os
import pickle
from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler


# Config
SENSORS = [
    {"id": "s2", "data": "./python/v2_sensor/calibration_s2_20260520-102905.csv"},
    {"id": "s3", "data": "./python/v2_sensor/calibration_s3_20260520-112205.csv"},
    {"id": "s4", "data": "./python/v2_sensor/calibration_s4_20260520-114405.csv"},
]
MODEL_DIR = "./python/v2_sensor/models"
INPUT_COLS = ["S0_L0", "S0_L1", "S0_L2", "S0_L3"]
OUTPUT_COLS = ["Tx", "Ty", "Tz"]
GROUP_COLS = OUTPUT_COLS

EPOCHS = 1500
BATCH_SIZE = 64
LR = 1e-3
TEST_SIZE = 0.2
RANDOM_SEED = 42
DEPLOY_MODEL_NAME = "Small NN physical"
SAVE_DEPLOY_TORCH_MODEL = True

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def with_physical_features(X):
    """Add pair/difference features based on the four quadrant coils."""
    L0, L1, L2, L3 = X.T
    total = L0 + L1 + L2 + L3
    mean = total / 4.0

    # In this dataset, low L0+L3 corresponds to +X and low L0+L1 to +Y.
    x_balance = (L1 + L2) - (L0 + L3)
    y_balance = (L2 + L3) - (L0 + L1)

    return np.column_stack(
        [
            X,
            total,
            mean,
            L0 + L1,
            L1 + L2,
            L2 + L3,
            L3 + L0,
            x_balance,
            y_balance,
            L0 - L2,
            L1 - L3,
        ]
    ).astype(np.float32)


FEATURE_SETS = {
    "raw": lambda X: X.astype(np.float32),
    "physical": with_physical_features,
}


@dataclass
class BenchmarkResult:
    name: str
    kind: str
    model: object
    feature_set: str
    rmse: float
    mae: float
    bias: np.ndarray
    per_axis_rmse: np.ndarray
    step_rmse: float
    step_max: float
    direction_agreement: float
    curvature_mean: float
    train_rmse: float


class FlexNet(nn.Module):
    def __init__(self, input_size, output_size, hidden_layers, activation):
        super().__init__()
        act_fn = {"relu": nn.ReLU, "tanh": nn.Tanh, "elu": nn.ELU}[activation]
        layers = []
        prev = input_size
        for hidden in hidden_layers:
            layers.append(nn.Linear(prev, hidden))
            layers.append(act_fn())
            prev = hidden
        layers.append(nn.Linear(prev, output_size))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


def make_pose_groups(data):
    return data[GROUP_COLS].astype(str).agg("|".join, axis=1).values


def grouped_train_test_split(X, y, data):
    groups = make_pose_groups(data)
    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=TEST_SIZE,
        random_state=RANDOM_SEED,
    )
    train_idx, test_idx = next(splitter.split(X, y, groups))
    return train_idx, test_idx


def rmse(y_pred, y_true):
    return float(np.sqrt(np.mean((y_pred - y_true) ** 2)))


def evaluate_predictions(y_pred, y_true):
    err = y_pred - y_true
    return {
        "rmse": rmse(y_pred, y_true),
        "mae": float(np.mean(np.abs(err))),
        "bias": np.mean(err, axis=0),
        "per_axis_rmse": np.sqrt(np.mean(err**2, axis=0)),
    }


def pose_average_inputs(data, feature_fn):
    cols = INPUT_COLS + OUTPUT_COLS
    pose_data = data[cols].groupby(OUTPUT_COLS, as_index=False).mean()
    X_pose = feature_fn(pose_data[INPUT_COLS].values.astype(np.float32))
    y_pose = pose_data[OUTPUT_COLS].values.astype(np.float32)
    keys = [tuple(row) for row in y_pose]
    return X_pose, y_pose, keys


def continuity_metrics(model_predict, data, feature_fn):
    X_pose, y_pose, keys = pose_average_inputs(data, feature_fn)
    pred_pose = model_predict(X_pose)
    pred_by_key = {key: pred for key, pred in zip(keys, pred_pose)}

    axis_values = [np.array(sorted(set(y_pose[:, axis]))) for axis in range(3)]
    axis_steps = []
    for values in axis_values:
        deltas = np.diff(values)
        axis_steps.append(float(np.min(deltas[deltas > 0])) if np.any(deltas > 0) else 0.0)

    step_errors = []
    direction_ok = []
    curvatures = []

    for key in keys:
        key_arr = np.array(key, dtype=np.float32)
        pred_here = pred_by_key[key]

        for axis, step in enumerate(axis_steps):
            if step <= 0:
                continue

            plus_arr = key_arr.copy()
            plus_arr[axis] += step
            plus_key = tuple(plus_arr.tolist())
            if plus_key in pred_by_key:
                expected = np.zeros(3, dtype=np.float32)
                expected[axis] = step
                pred_delta = pred_by_key[plus_key] - pred_here
                step_errors.append(float(np.linalg.norm(pred_delta - expected)))
                direction_ok.append(float(np.dot(pred_delta, expected) > 0))

            minus_arr = key_arr.copy()
            minus_arr[axis] -= step
            minus_key = tuple(minus_arr.tolist())
            if minus_key in pred_by_key and plus_key in pred_by_key:
                curvature = pred_by_key[plus_key] - 2.0 * pred_here + pred_by_key[minus_key]
                curvatures.append(float(np.linalg.norm(curvature)))

    return {
        "step_rmse": float(np.sqrt(np.mean(np.square(step_errors)))) if step_errors else float("nan"),
        "step_max": float(np.max(step_errors)) if step_errors else float("nan"),
        "direction_agreement": float(np.mean(direction_ok)) if direction_ok else float("nan"),
        "curvature_mean": float(np.mean(curvatures)) if curvatures else float("nan"),
    }


def train_torch_model(name, feature_set, hidden_layers, activation, X_raw, y_raw, train_idx, test_idx, data):
    feature_fn = FEATURE_SETS[feature_set]
    X = feature_fn(X_raw)

    X_train_raw = X[train_idx]
    X_test_raw = X[test_idx]
    y_train_raw = y_raw[train_idx]
    y_test_raw = y_raw[test_idx]

    scaler_X = StandardScaler().fit(X_train_raw)
    scaler_y = StandardScaler().fit(y_train_raw)

    X_train = torch.tensor(scaler_X.transform(X_train_raw), dtype=torch.float32).to(DEVICE)
    X_test = torch.tensor(scaler_X.transform(X_test_raw), dtype=torch.float32).to(DEVICE)
    y_train = torch.tensor(scaler_y.transform(y_train_raw), dtype=torch.float32).to(DEVICE)

    model = FlexNet(X_train.shape[1], len(OUTPUT_COLS), hidden_layers, activation).to(DEVICE)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=LR)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=100, factor=0.5)

    n = X_train.size(0)
    for epoch in range(EPOCHS):
        model.train()
        perm = torch.randperm(n, device=DEVICE)
        epoch_loss = 0.0
        for i in range(0, n, BATCH_SIZE):
            idx = perm[i : i + BATCH_SIZE]
            optimizer.zero_grad()
            loss = criterion(model(X_train[idx]), y_train[idx])
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
        scheduler.step(epoch_loss)

    def predict(X_values):
        model.eval()
        with torch.no_grad():
            X_scaled = scaler_X.transform(X_values).astype(np.float32)
            y_scaled = model(torch.tensor(X_scaled, dtype=torch.float32).to(DEVICE)).cpu().numpy()
        return scaler_y.inverse_transform(y_scaled)

    y_pred = predict(X_test_raw)
    y_train_pred = predict(X_train_raw)

    scores = evaluate_predictions(y_pred, y_test_raw)
    smooth = continuity_metrics(predict, data, feature_fn)

    return BenchmarkResult(
        name=name,
        kind="torch",
        model={
            "net": model,
            "scaler_X": scaler_X,
            "scaler_y": scaler_y,
            "hidden_layers": hidden_layers,
            "activation": activation,
        },
        feature_set=feature_set,
        train_rmse=rmse(y_train_pred, y_train_raw),
        **scores,
        **smooth,
    )


def train_sklearn_model(name, feature_set, degree, alpha, X_raw, y_raw, train_idx, test_idx, data):
    feature_fn = FEATURE_SETS[feature_set]
    X = feature_fn(X_raw)

    steps = [("scaler", StandardScaler())]
    if degree > 1:
        steps.append(("poly", PolynomialFeatures(degree=degree, include_bias=False)))
    steps.append(("ridge", Ridge(alpha=alpha)))
    model = Pipeline(steps)

    X_train = X[train_idx]
    X_test = X[test_idx]
    y_train = y_raw[train_idx]
    y_test = y_raw[test_idx]

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_train_pred = model.predict(X_train)

    scores = evaluate_predictions(y_pred, y_test)
    smooth = continuity_metrics(model.predict, data, feature_fn)

    return BenchmarkResult(
        name=name,
        kind="sklearn",
        model=model,
        feature_set=feature_set,
        train_rmse=rmse(y_train_pred, y_train),
        **scores,
        **smooth,
    )


def print_results(results):
    results = sorted(results, key=lambda r: (r.rmse, r.step_rmse))
    print("\nBenchmark results, sorted by grouped test RMSE")
    print(
        f"{'Model':<26} {'Feat':<9} {'Test':>8} {'Train':>8} {'MAE':>8} "
        f"{'Tx/Ty/Tz':>22} {'Bias Tx/Ty/Tz':>24} {'Step':>8} {'MaxStep':>8} "
        f"{'Dir%':>7} {'Curv':>8}"
    )
    print("-" * 160)
    for r in results:
        per_axis = "/".join(f"{v:.3f}" for v in r.per_axis_rmse)
        bias = "/".join(f"{v:+.3f}" for v in r.bias)
        print(
            f"{r.name:<26} {r.feature_set:<9} {r.rmse:8.3f} {r.train_rmse:8.3f} {r.mae:8.3f} "
            f"{per_axis:>22} {bias:>24} {r.step_rmse:8.3f} {r.step_max:8.3f} "
            f"{100.0 * r.direction_agreement:6.1f}% {r.curvature_mean:8.3f}"
        )

    print("\nContinuity metric guide")
    print("  Step: RMSE of adjacent 1 mm pose-to-pose prediction changes vs the true 1 mm step.")
    print("  MaxStep: worst adjacent step error; useful for spotting jumps/discontinuities.")
    print("  Dir%: percent of adjacent steps whose predicted movement points in the correct direction.")
    print("  Curv: mean second finite difference of predictions; lower is smoother, but too low can mean underfit.")
    return results


def save_torch_model(sensor_id, result):
    if result.kind != "torch":
        print(f"\nBest model is {result.kind}; skipping torch checkpoint save.")
        return

    os.makedirs(MODEL_DIR, exist_ok=True)
    model_path = os.path.join(MODEL_DIR, f"{sensor_id}.pth")
    scaler_path = os.path.join(MODEL_DIR, f"{sensor_id}_scalers.pkl")
    torch.save(result.model["net"].state_dict(), model_path)
    with open(scaler_path, "wb") as f:
        pickle.dump(
            {
                "scaler_X": result.model["scaler_X"],
                "scaler_y": result.model["scaler_y"],
                "feature_set": result.feature_set,
                "hidden_layers": result.model["hidden_layers"],
                "activation": result.model["activation"],
                "input_cols": INPUT_COLS,
                "output_cols": OUTPUT_COLS,
                "model_name": result.name,
            },
            f,
        )
    print(f"\nSaved deploy torch model to {model_path}")
    print(f"Saved scalers to {scaler_path}")


def run_sensor_benchmark(sensor):
    sensor_id = sensor["id"]
    data_file = sensor["data"]

    print(f"Device: {DEVICE}" + (f" ({torch.cuda.get_device_name(0)})" if DEVICE.type == "cuda" else ""))
    print(f"\nSensor: {sensor_id}")
    print(f"Loading {data_file}")

    data = pd.read_csv(data_file, header=0)
    X_raw = data[INPUT_COLS].values.astype(np.float32)
    y_raw = data[OUTPUT_COLS].values.astype(np.float32)
    train_idx, test_idx = grouped_train_test_split(X_raw, y_raw, data)

    train_poses = data.iloc[train_idx][GROUP_COLS].drop_duplicates().shape[0]
    test_poses = data.iloc[test_idx][GROUP_COLS].drop_duplicates().shape[0]
    print(f"Rows: {len(data)} | Train rows: {len(train_idx)} | Test rows: {len(test_idx)}")
    print(f"Grouped poses: train={train_poses}, test={test_poses}")

    results = []

    sklearn_specs = [
        ("Ridge raw", "raw", 1, 1.0),
        ("Poly2 Ridge raw", "raw", 2, 10.0),
        ("Poly3 Ridge raw", "raw", 3, 100.0),
        ("Ridge physical", "physical", 1, 1.0),
        ("Poly2 Ridge physical", "physical", 2, 10.0),
        ("Poly3 Ridge physical", "physical", 3, 100.0),
    ]
    torch_specs = [
        ("Small NN physical", "physical", [32, 16], "tanh"),
    ]

    for spec in sklearn_specs:
        print(f"Training {spec[0]}...")
        results.append(train_sklearn_model(*spec, X_raw, y_raw, train_idx, test_idx, data))

    for spec in torch_specs:
        print(f"Training {spec[0]}...")
        results.append(train_torch_model(*spec, X_raw, y_raw, train_idx, test_idx, data))

    sorted_results = print_results(results)
    best = sorted_results[0]
    print(f"\nBest by grouped test RMSE: {best.name} ({best.rmse:.3f} mm)")

    if SAVE_DEPLOY_TORCH_MODEL:
        deploy = next((result for result in results if result.name == DEPLOY_MODEL_NAME), None)
        if deploy is None:
            deploy = next((result for result in sorted_results if result.kind == "torch"), None)
        if deploy is None:
            print("\nNo torch model available to save.")
        else:
            print(f"Deploy model: {deploy.name} ({deploy.rmse:.3f} mm grouped test RMSE)")
            save_torch_model(sensor_id, deploy)


if __name__ == "__main__":
    for sensor in SENSORS:
        run_sensor_benchmark(sensor)
