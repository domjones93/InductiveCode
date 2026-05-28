import time
import collections
import threading
import numpy as np
from sensor_read import Sensor

N_CHANNELS = 4
FREQ_WINDOW = 20
PLOT_INTERVAL_S = 1 / 30  # plot refresh rate (main thread only) ~30 Hz
TEST_TIME_S = 30.0         # duration of the test window shown on x-axis (seconds)
MAX_PLOT_POINTS = 2000     # max points sent to matplotlib per channel (downsampled)
PLOT_DECIMATION_S = 0.05    # minimum time between stored plot points (seconds)


def test_and_plot_sensor(port, sensor_config=[(0, 0x2A)], plot=True, test_time=TEST_TIME_S):
    sensor = Sensor(port, sensor_config=sensor_config)
    sensor.connect()

    n_sensors = len(sensor_config)

    # Shared state between acquisition thread and main/plot thread
    lock = threading.Lock()
    stop_event = threading.Event()
    sample_times = collections.deque(maxlen=FREQ_WINDOW)
    data_buffer = [
        [[] for _ in range(N_CHANNELS)]
        for _ in range(n_sensors)
    ]
    time_buffer = [[] for _ in range(n_sensors)]
    last_plot_time = [0.0]  # last elapsed_s at which a plot point was stored
    freq_ref = [0.0]  # mutable container so thread can write
    time_ref = [None]   # MCU tare timestamp (microseconds)
    elapsed_ref = [0.0]  # elapsed time in seconds

    def acquisition_loop():
        while not stop_event.is_set():
            try:
                timestamp, sensors = sensor.process_single_measurement_all()
                with lock:
                    if time_ref[0] is None:
                        time_ref[0] = timestamp
                    elapsed_us = (timestamp - time_ref[0]) & 0xFFFFFFFF  # handle 32-bit rollover
                    elapsed_s = elapsed_us / 1e6
                    elapsed_ref[0] = elapsed_s
                    sample_times.append(elapsed_s)
                    if len(sample_times) >= 2:
                        dt = sample_times[-1] - sample_times[0]
                        freq_ref[0] = (len(sample_times) - 1) / dt if dt > 0 else 0.0
                    for s in sensors:
                        idx = s["index"]
                        if idx < n_sensors:
                            if elapsed_s - last_plot_time[0] >= PLOT_DECIMATION_S:
                                time_buffer[idx].append(elapsed_s)
                                for ch in range(N_CHANNELS):
                                    data_buffer[idx][ch].append(s["inductance"][ch])
                    if elapsed_s - last_plot_time[0] >= PLOT_DECIMATION_S:
                        last_plot_time[0] = elapsed_s
                if not plot:
                    with lock:
                        freq = freq_ref[0]
                        t = elapsed_ref[0]
                        parts = [f"t={t:.3f}s  {freq:.1f} Hz"]
                        for s in sensors:
                            vals = "  ".join(f"CH{ch}: {s['inductance'][ch]:.4f}" for ch in range(N_CHANNELS))
                            parts.append(f"S{s['index']} I2C{s['bus']}/0x{s['address']:02X}  {vals}")
                    print("  |  ".join(parts))
            except Exception as e:
                print(f"Acquisition error: {e}")

    acq_thread = threading.Thread(target=acquisition_loop, daemon=True)
    acq_thread.start()

    if plot:
        import pyqtgraph as pg
        from pyqtgraph.Qt import QtWidgets, QtCore

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

        COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']  # one per channel

        win = pg.GraphicsLayoutWidget(title="Sensor Live Plot", size=(1000, 300 * n_sensors))
        win.show()

        channel_lines = []
        plot_items = []
        for i, (bus, addr) in enumerate(sensor_config):
            p = win.addPlot(row=i, col=0,
                            title=f"Sensor {i}  |  I2C{bus} / 0x{addr:02X}")
            p.setLabel("bottom", "Time", units="s")
            p.setLabel("left", "Inductance", units="uH")
            p.setXRange(0, test_time, padding=0)
            p.addLegend(offset=(10, 10))
            lines = [p.plot([], [], pen=pg.mkPen(COLORS[ch], width=1.5),
                            name=f"CH{ch}") for ch in range(N_CHANNELS)]
            channel_lines.append(lines)
            plot_items.append(p)

        status_label = pg.LabelItem(justify="center")
        win.addItem(status_label, row=n_sensors, col=0)

        def update():
            with lock:
                freq = freq_ref[0]
                t_now = elapsed_ref[0]
                snapshot = [
                    [data_buffer[i][ch][:] for ch in range(N_CHANNELS)]
                    for i in range(n_sensors)
                ]
                t_snapshot = [time_buffer[i][:] for i in range(n_sensors)]

            for i, lines in enumerate(channel_lines):
                p = plot_items[i]
                t_buf = t_snapshot[i]
                n = len(t_buf)
                if n == 0:
                    continue
                t_arr = np.array(t_buf)
                if n > MAX_PLOT_POINTS:
                    idx = np.round(np.linspace(0, n - 1, MAX_PLOT_POINTS)).astype(int)
                    t_plot = t_arr[idx]
                else:
                    idx = None
                    t_plot = t_arr

                all_values = []
                for ch, line in enumerate(lines):
                    buf = snapshot[i][ch]
                    y_arr = np.array(buf)
                    y_plot = y_arr[idx] if idx is not None else y_arr
                    line.setData(t_plot, y_plot)
                    all_values.append(y_plot)

                # Expand x-axis if data goes beyond test_time
                if t_arr[-1] > p.viewRange()[0][1]:
                    p.setXRange(0, t_arr[-1] + test_time * 0.1, padding=0)

                # Auto y-range
                all_y = np.concatenate(all_values)
                if len(all_y):
                    mn, mx = all_y.min(), all_y.max()
                    margin = (mx - mn) * 0.1 or 1.0
                    p.setYRange(mn - margin, mx + margin, padding=0)

            status_label.setText(
                f"<span style='font-size:11pt'>t = {t_now:.3f} s &nbsp;|&nbsp; "
                f"Sample rate: {freq:.1f} Hz</span>"
            )

        timer = QtCore.QTimer()
        timer.timeout.connect(update)
        timer.start(int(PLOT_INTERVAL_S * 1000))

        try:
            app.exec_()
        except KeyboardInterrupt:
            print("Exiting due to user interruption (Ctrl+C).")
        finally:
            timer.stop()
            stop_event.set()
            acq_thread.join(timeout=2)
            sensor.disconnect()
    else:
        try:
            acq_thread.join()
        except KeyboardInterrupt:
            print("Exiting due to user interruption (Ctrl+C).")
        finally:
            stop_event.set()
            acq_thread.join(timeout=2)
            sensor.disconnect()


if __name__ == "__main__":
    port = "COM3"  # Update with your serial port
    sensor_config = [
        (0, 0x2A),
        (1, 0x2A),
        (1, 0x2B),
    ]
    test_and_plot_sensor(port, sensor_config=sensor_config, plot=True, test_time=30.0)
