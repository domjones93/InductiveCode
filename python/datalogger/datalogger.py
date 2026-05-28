

import time
import collections
import threading
import queue
import numpy as np
from sensor_read import Sensor

# ── Configuration ──────────────────────────────────────────────────────────────
# SENSOR_SETUP: list of dicts, one per physical sensor slot.
#   "bus"    : I2C bus index (0 or 1)
#   "addr"   : I2C address (e.g. 0x2A)
#   "label"  : human-readable sensor ID (e.g. "S3") — used in plot titles & CSV
#   "calib"  : path to the .pth calibration model for this sensor
SENSOR_SETUP = [
    {"bus": 0, "addr": 0x2A, "label": "S6", "calib": "../v2_sensor/models/s6.pth"},
]

PORT              = "COM5"
FREQ_WINDOW       = 20
PLOT_INTERVAL_S   = 1 / 30
TEST_TIME_S       = 60.0
MAX_PLOT_POINTS   = 2000
PLOT_DECIMATION_S = 0.05
POS_LABELS        = ["dX", "dY", "dZ"]
N_POS             = 3
N_CHANNELS        = 4


def run_datalogger(port=PORT, sensor_setup=SENSOR_SETUP,
                   test_time=TEST_TIME_S, plot=True, save=True):

    sensor_config = [(s["bus"], s["addr"]) for s in sensor_setup]
    sensor_labels = [s["label"] for s in sensor_setup]
    n_sensors = len(sensor_setup)

    sensor = Sensor(port, sensor_config=sensor_config)
    sensor.connect()
    if not sensor.ser:
        print("Failed to connect to sensor.")
        return

    # Load per-sensor calibration models
    import torch
    from sensor_read import FeedForwardNN
    calib_models = []
    for s in sensor_setup:
        model = FeedForwardNN(input_size=N_CHANNELS, output_size=N_POS)
        try:
            model.load_state_dict(torch.load(s["calib"], map_location="cpu"))
            model.eval()
            print(f"Loaded calibration for {s['label']} from {s['calib']}")
        except Exception as e:
            print(f"WARNING: could not load calibration for {s['label']}: {e}")
            model = None
        calib_models.append(model)

    def predict(s_idx, inductance):
        model = calib_models[s_idx]
        if model is None:
            return np.zeros(N_POS)
        t = torch.tensor(inductance, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            return model(t).numpy()[0]

    # pos_buffer[sensor_idx][axis_idx] = list of floats
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

    # ── Acquisition thread ─────────────────────────────────────────────────────
    def acquisition_loop():
        while not stop_event.is_set():
            try:
                mcu_ts, sensors_raw = sensor.process_single_measurement_all()
                positions = []
                for s_idx in range(n_sensors):
                    ch_data = np.array(sensors_raw[s_idx]["inductance"], dtype=float)
                    positions.append(predict(s_idx, ch_data))

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
                    for s_idx, pos in enumerate(positions):
                        label   = sensor_setup[s_idx]["label"]
                        raw_str = ",".join(f"{v:.6f}" for v in sensors_raw[s_idx]["inductance"])
                        pos_str = ",".join(f"{v:.6f}" for v in pos)
                        save_q.put(f"{wall_t:.6f},{elapsed_s:.6f},{label},{raw_str},{pos_str}")

            except Exception as e:
                print(f"Acquisition error: {e}")

    # ── Save thread ────────────────────────────────────────────────────────────
    def save_worker():
        filename = f"datalogger_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        print(f"Saving to {filename}")
        raw_cols = ",".join(f"L{c}" for c in range(N_CHANNELS))
        with open(filename, "w", newline="") as f:
            f.write(f"wall_time,elapsed_s,sensor_label,{raw_cols},{','.join(POS_LABELS)}\n")
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



