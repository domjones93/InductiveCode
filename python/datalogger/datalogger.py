

import time
import threading
import queue
import numpy as np
from sensor_read import Sensor


calibration_queue = queue.Queue()
save_queue = queue.Queue()

recording = True

calibration_finished = threading.Event()
SENSOR_CONFIG = [(0, 0x2A)] #, (0, 0x2B), (1, 0x2A), (1, 0x2B)]


def sensor_read_worker(sensor):
    count = 0
    next_time = time.perf_counter()

    while recording:
        timestamp = time.time()
        _, sensors = sensor.process_single_measurement_all()
        data = np.array(
            [value for sensor_data in sensors for value in sensor_data["inductance"]],
            dtype=float,
        )
        
        calibration_queue.put((timestamp, data))

        next_time += 0.01
        sleep_time = next_time - time.perf_counter()
        if sleep_time > 0:
            time.sleep(sleep_time)

def calibration_worker(sensor):
    BATCH_SIZE = 10
    batch = []

    while recording or not calibration_queue.empty():
        try:
            timestamp, raw_data = calibration_queue.get(timeout=0.1)
            batch.append((timestamp, raw_data))

            if len(batch) >= BATCH_SIZE:
                timestamps, raw_batch = zip(*batch)
                raw_array = np.stack(raw_batch)

                # The current calibration model expects one 4-channel LDC1614.
                predictions = sensor.predict_position(raw_array[:, :4])

                for t, raw, pred in zip(timestamps, raw_batch, predictions):
                    formatted = f"{t}," + ",".join(f"{v:.6f}" for v in raw) + f",{pred[0]:.6f},{pred[1]:.6f},{pred[2]:.6f}"
                    save_queue.put(formatted)
                batch = []

        except queue.Empty:
            continue

    # Process remaining if any
    if batch:
        timestamps, raw_batch = zip(*batch)
        raw_array = np.stack(raw_batch)
        predictions = sensor.predict_position(raw_array[:, :4])
        for t, raw, pred in zip(timestamps, raw_batch, predictions):
            formatted = f"{t}," + ",".join(f"{v:.6f}" for v in raw) + f",{pred[0]:.6f},{pred[1]:.6f},{pred[2]:.6f}"
            save_queue.put(formatted)

    calibration_finished.set()


def save_data_worker():
    # Filename as time and date
    datetimestring = time.strftime("%Y%m%d_%H%M%S")
    filename = f"sensor_data_{datetimestring}.csv"
    print(f"Saving data to {filename}...")
    sensor_columns = [
        f"S{sensor_idx}_L{channel_idx}"
        for sensor_idx in range(len(SENSOR_CONFIG))
        for channel_idx in range(4)
    ]
    with open(filename, "w", newline="") as f:
        f.write("Time," + ",".join(sensor_columns) + ",dX,dY,dZ\n")

        while recording or not save_queue.empty():
            try:
                line = save_queue.get(timeout=0.1)
                f.write(line + "\n")
            except queue.Empty:
                continue



if __name__ == "__main__":
    serial_port = "COM5"  # Replace with actual serial port
    
    sensor = Sensor(port=serial_port, sensor_config=SENSOR_CONFIG)
    sensor.connect()
    if not sensor.ser:
        print("Failed to connect to sensor.")
        exit()

    threads = [
        threading.Thread(target=sensor_read_worker, args=(sensor,)),
        threading.Thread(target=calibration_worker, args=(sensor,)),
        threading.Thread(target=save_data_worker)
    ]

    print("Recording started. Press Ctrl+C to stop...")

    try:
        for t in threads:
            t.start()

        time.sleep(10)  # Run for 10 seconds or change as needed
        print("Stopping recording...")

    except KeyboardInterrupt:
        print("Interrupted by user. Closing threads...")

    finally:
        recording = False
        for t in threads:
            t.join()

        print("Recording finished. Data saved to 'sensor_data.csv'.")


