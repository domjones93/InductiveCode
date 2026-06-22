

import time
import collections
import threading
import queue
import numpy as np
from sensor_read import Sensor

import os
_HERE = os.path.dirname(os.path.abspath(__file__))

# ── Configuration ──────────────────────────────────────────────────────────────
# MODEL_DIR: folder containing all .pth and _scalers.pkl files.
#            Model files are expected as <MODEL_DIR>/<label_lower>.pth
#            Scaler files are expected as <MODEL_DIR>/<label_lower>_scalers.pkl
MODEL_DIR = os.path.join(_HERE, "../v2_sensor/models")

# SENSOR_SETUP: list of dicts, one per physical sensor slot.
#   "bus"   : I2C bus index (0 or 1)
#   "addr"  : I2C address (e.g. 0x2A)
#   "label" : human-readable sensor ID (e.g. "S2") — also used to find model files
SENSOR_SETUP = [
    {"bus": 0, "addr": 0x2A, "label": "s4"},
    {"bus": 1, "addr": 0x2A, "label": "s2"},
    {"bus": 1, "addr": 0x2B, "label": "s3"},
]

PORT              = "COM3"
FREQ_WINDOW       = 20
PLOT_INTERVAL_S   = 1 / 30
TEST_TIME_S       = 5.0
MAX_PLOT_POINTS   = 2000
PLOT_DECIMATION_S = 0.05
POS_LABELS        = ["dX", "dY", "dZ"]
N_POS             = 3
N_CHANNELS        = 4
TARE_SAMPLES      = 10   # number of samples averaged for tare


def calibration_features(inductance, feature_set):
    values = np.asarray(inductance, dtype=np.float32).reshape(1, -1)
    if feature_set == "raw":
        return values
    if feature_set != "physical":
        raise ValueError(f"Unsupported calibration feature set: {feature_set}")

    L0, L1, L2, L3 = values.T
    total = L0 + L1 + L2 + L3
    mean = total / 4.0
    x_balance = (L1 + L2) - (L0 + L3)
    y_balance = (L2 + L3) - (L0 + L1)

    return np.column_stack(
        [
            values,
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


def build_calibration_model(input_size, output_size, hidden_sizes, activation):
    import torch.nn as nn

    class CalibrationNet(nn.Module):
        def __init__(self):
            super().__init__()
            act_fn = {"relu": nn.ReLU, "tanh": nn.Tanh, "elu": nn.ELU}[activation]
            layers = []
            prev = input_size
            for hidden in hidden_sizes:
                layers.append(nn.Linear(prev, hidden))
                layers.append(act_fn())
                prev = hidden
            layers.append(nn.Linear(prev, output_size))
            self.net = nn.Sequential(*layers)

        def forward(self, x):
            return self.net(x)

    return CalibrationNet()


def run_datalogger(port=PORT, sensor_setup=SENSOR_SETUP, model_dir=MODEL_DIR,
                   test_time=TEST_TIME_S, plot=True, save=True):

    sensor_config = [(s["bus"], s["addr"]) for s in sensor_setup]
    sensor_labels = [s["label"] for s in sensor_setup]
    n_sensors = len(sensor_setup)

    sensor = Sensor(port, sensor_config=sensor_config)
    sensor.connect()
    if not sensor.ser:
        print("Failed to connect to sensor.")
        return    # Load per-sensor calibration models
    import torch
    import traceback
    import pickle
    import os
    calib_models = []
    calib_scalers = []   # list of {"scaler_X": ..., "scaler_y": ...} or None
    for s in sensor_setup:
        abs_path    = os.path.abspath(os.path.join(model_dir, f"{s['label'].lower()}.pth"))
        scaler_path = os.path.abspath(os.path.join(model_dir, f"{s['label'].lower()}_scalers.pkl"))
        print(f"[CALIB] Loading {s['label']} from: {abs_path}  (exists={os.path.exists(abs_path)})")

        if os.path.exists(scaler_path):
            with open(scaler_path, "rb") as f:
                scalers = pickle.load(f)
            print(f"[CALIB] Scalers loaded for {s['label']}")
        else:
            print(f"WARNING: no scalers found at {scaler_path} - predictions will be unscaled!")
            scalers = None

        try:
            state_dict = torch.load(abs_path, map_location="cpu")
            # Infer hidden layer sizes from checkpoint weights (exclude output layer)
            weight_keys = [k for k in state_dict.keys() if k.endswith(".weight")]
            input_size = state_dict[weight_keys[0]].shape[1]
            hidden_sizes = [state_dict[k].shape[0] for k in weight_keys[:-1]]
            activation = scalers.get("activation", "relu") if scalers is not None else "relu"
            feature_set = scalers.get("feature_set", "raw") if scalers is not None else "raw"
            model = build_calibration_model(
                input_size=input_size,
                output_size=N_POS,
                hidden_sizes=hidden_sizes,
                activation=activation,
            )
            model.load_state_dict(state_dict)
            model.eval()
            print(
                f"[CALIB] Loaded OK: {s['label']} "
                f"(features={feature_set}, activation={activation}, hidden={hidden_sizes})"
            )
        except Exception as e:
            print(f"WARNING: could not load calibration for {s['label']}: {e}")
            traceback.print_exc()
            model = None
        calib_models.append(model)

        # Load scalers
        if os.path.exists(scaler_path):
            with open(scaler_path, "rb") as f:
                scalers = pickle.load(f)
            print(f"[CALIB] Scalers loaded for {s['label']}")
        else:
            print(f"WARNING: no scalers found at {scaler_path} — predictions will be unscaled!")
            scalers = None
        calib_scalers.append(scalers)

    def predict(s_idx, inductance):
        model   = calib_models[s_idx]
        scalers = calib_scalers[s_idx]
        label   = sensor_setup[s_idx]["label"]
        if model is None:
            return np.zeros(N_POS)
        if np.all(inductance == 0):
            print(f"[PREDICT] {label}: WARNING all inductance values are zero!")
        feature_set = scalers.get("feature_set", "raw") if scalers is not None else "raw"
        features = calibration_features(inductance, feature_set)
        # Scale input
        if scalers is not None:
            x = scalers["scaler_X"].transform(features).astype(np.float32)
        else:
            x = features.astype(np.float32)
        t = torch.tensor(x, dtype=torch.float32)
        with torch.no_grad():
            y_scaled = model(t).numpy()
        # Inverse-scale output
        if scalers is not None:
            result = scalers["scaler_y"].inverse_transform(y_scaled)[0]
        else:
            result = y_scaled[0]
        return result# pos_buffer[sensor_idx][axis_idx] = list of floats
    pos_buffer  = [[[] for _ in range(N_POS)] for _ in range(n_sensors)]
    time_buffer = [[] for _ in range(n_sensors)]
    lock         = threading.Lock()
    stop_event   = threading.Event()
    save_q       = queue.Queue()
    sample_times = collections.deque(maxlen=FREQ_WINDOW)
    freq_ref     = [0.0]
    time_ref     = [None]
    elapsed_ref  = [0.0]
    last_store   = [0.0]

    # ── Tare ───────────────────────────────────────────────────────────────────
    print(f"Taring sensors ({TARE_SAMPLES} samples)...")
    tare_accum = [np.zeros(N_POS) for _ in range(n_sensors)]
    tare_count = 0
    while tare_count < TARE_SAMPLES:
        try:
            _, sensors_raw = sensor.process_single_measurement_all()
            for s_idx in range(n_sensors):
                ch_data = np.array(sensors_raw[s_idx]["inductance"], dtype=float)
                tare_accum[s_idx] += predict(s_idx, ch_data)
            tare_count += 1
        except Exception as e:
            print(f"Tare sample error: {e}")
    tare_offset = [tare_accum[i] / TARE_SAMPLES for i in range(n_sensors)]
    print(f"Tare complete. Offsets: { {sensor_setup[i]['label']: np.round(tare_offset[i], 4).tolist() for i in range(n_sensors)} }")

    # ── Acquisition thread ─────────────────────────────────────────────────────
    def acquisition_loop():
        while not stop_event.is_set():
            try:
                mcu_ts, sensors_raw = sensor.process_single_measurement_all()
                positions = []
                for s_idx in range(n_sensors):
                    ch_data = np.array(sensors_raw[s_idx]["inductance"], dtype=float)
                    positions.append(predict(s_idx, ch_data) - tare_offset[s_idx])

                with lock:
                    if time_ref[0] is None:
                        time_ref[0] = mcu_ts
                    elapsed_us = (mcu_ts - time_ref[0]) & 0xFFFFFFFF
                    elapsed_s  = elapsed_us / 1e6
                    elapsed_ref[0] = elapsed_s
                    sample_times.append(elapsed_s)
                    if len(sample_times) >= 2:
                        dt = sample_times[-1] - sample_times[0]
                        freq_ref[0] = (len(sample_times) - 1) / dt if dt > 0 else 0.0
                    store = (elapsed_s - last_store[0]) >= PLOT_DECIMATION_S
                    if store:
                        last_store[0] = elapsed_s
                        for s_idx, pos in enumerate(positions):
                            time_buffer[s_idx].append(elapsed_s)
                            for ax in range(N_POS):
                                pos_buffer[s_idx][ax].append(float(pos[ax]))

                if save and store:
                    wall_t = time.time()
                    # Build one row: wall_time, elapsed_s, then for each sensor: L0..L3, dX, dY, dZ
                    parts = [f"{wall_t:.6f}", f"{elapsed_s:.6f}"]
                    for s_idx, pos in enumerate(positions):
                        parts += [f"{v:.6f}" for v in sensors_raw[s_idx]["inductance"]]
                        parts += [f"{v:.6f}" for v in pos]
                    save_q.put(",".join(parts))

            except Exception as e:
                print(f"Acquisition error: {e}")

    # ── Save thread ────────────────────────────────────────────────────────────
    def save_worker():
        filename = f"datalogger_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        print(f"Saving to {filename}")
        # Build header: wall_time, elapsed_s, then per-sensor columns
        sensor_cols = []
        for s in sensor_setup:
            lbl = s["label"]
            sensor_cols += [f"{lbl}_L{c}" for c in range(N_CHANNELS)]
            sensor_cols += [f"{lbl}_{p}" for p in POS_LABELS]
        header = "wall_time,elapsed_s," + ",".join(sensor_cols)
        with open(filename, "w", newline="") as f:
            f.write(header + "\n")
            while not stop_event.is_set() or not save_q.empty():
                try:
                    f.write(save_q.get(timeout=0.1) + "\n")
                except queue.Empty:
                    continue
        print(f"Saved: {filename}")

    acq_thread  = threading.Thread(target=acquisition_loop, daemon=True)
    save_thread = threading.Thread(target=save_worker, daemon=False)
    acq_thread.start()
    if save:
        save_thread.start()

    # ── pyqtgraph live plot ────────────────────────────────────────────────────
    if plot:
        import pyqtgraph as pg
        from pyqtgraph.Qt import QtWidgets, QtCore

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c"]

        win = pg.GraphicsLayoutWidget(
            title="Datalogger — Position Live Plot",
            size=(1100, 320 * n_sensors),
        )
        win.show()

        plot_items = []
        axis_lines = []
        for s_idx, cfg in enumerate(sensor_setup):
            p = win.addPlot(row=s_idx, col=0,
                            title=f"{cfg['label']}  |  I2C{cfg['bus']} / 0x{cfg['addr']:02X}")
            p.setLabel("bottom", "Time", units="s")
            p.setLabel("left", "Position", units="mm")
            p.setXRange(0, test_time, padding=0)
            p.addLegend(offset=(10, 10))
            lines = [p.plot([], [], pen=pg.mkPen(COLORS[ax], width=1.5),
                            name=POS_LABELS[ax]) for ax in range(N_POS)]
            axis_lines.append(lines)
            plot_items.append(p)

        status_label = pg.LabelItem(justify="center")
        win.addItem(status_label, row=n_sensors, col=0)

        def update():
            with lock:
                freq  = freq_ref[0]
                t_now = elapsed_ref[0]
                t_snap   = [time_buffer[i][:] for i in range(n_sensors)]
                pos_snap = [[pos_buffer[i][ax][:] for ax in range(N_POS)]
                            for i in range(n_sensors)]

            for s_idx, lines in enumerate(axis_lines):
                p = plot_items[s_idx]
                t_buf = t_snap[s_idx]
                n = len(t_buf)
                if n == 0:
                    continue
                t_arr = np.array(t_buf)
                if n > MAX_PLOT_POINTS:
                    idx    = np.round(np.linspace(0, n - 1, MAX_PLOT_POINTS)).astype(int)
                    t_plot = t_arr[idx]
                else:
                    idx    = None
                    t_plot = t_arr
                all_y = []
                for ax, line in enumerate(lines):
                    y_arr  = np.array(pos_snap[s_idx][ax])
                    y_plot = y_arr[idx] if idx is not None else y_arr
                    line.setData(t_plot, y_plot)
                    all_y.append(y_plot)
                if t_arr[-1] > p.viewRange()[0][1]:
                    p.setXRange(0, t_arr[-1] + test_time * 0.1, padding=0)
                all_y_cat = np.concatenate(all_y)
                if len(all_y_cat):
                    mn, mx = all_y_cat.min(), all_y_cat.max()
                    margin = (mx - mn) * 0.1 or 1.0
                    p.setYRange(mn - margin, mx + margin, padding=0)

            status_label.setText(
                f"<span style='font-size:11pt'>"
                f"t = {t_now:.3f} s &nbsp;|&nbsp; Sample rate: {freq:.1f} Hz</span>"
            )

        timer = QtCore.QTimer()
        timer.timeout.connect(update)
        timer.start(int(PLOT_INTERVAL_S * 1000))

        try:
            app.exec_()
        except KeyboardInterrupt:
            print("Exiting.")
        finally:
            timer.stop()
            stop_event.set()
            acq_thread.join(timeout=2)
            if save:
                save_thread.join(timeout=5)
            sensor.disconnect()

    else:
        print("Recording (no plot). Press Ctrl+C to stop.")
        try:
            while not stop_event.is_set():
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Stopping...")
        finally:
            stop_event.set()
            acq_thread.join(timeout=2)
            if save:
                save_thread.join(timeout=5)
            sensor.disconnect()


if __name__ == "__main__":
    run_datalogger(port=PORT, sensor_setup=SENSOR_SETUP,
                   test_time=TEST_TIME_S, plot=True, save=True)



