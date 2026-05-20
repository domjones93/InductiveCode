import matplotlib.pyplot as plt
import time
import collections
from sensor_read import Sensor

# Function to test and plot raw sensor values in real-time
def test_and_plot_sensor(port, sensor_config=[(0, 0x2A)]):
    sensor = Sensor(port, sensor_config=sensor_config)
    sensor.connect()

    plt.ion()  # Enable interactive mode for real-time plotting
    fig, ax = plt.subplots()
    lines = [ax.plot([], [], label=f"Sensor {i}")[0] for i in range(4)]
    ax.set_xlim(0, 100)  # Keep 1 second of data (assuming 0.01s refresh rate)
    ax.set_ylim(0, 100)  # Adjust based on expected raw value range
    ax.set_xlabel("Time (samples)")
    ax.set_ylabel("Raw Value")
    ax.legend()

    # Initialize deque to store the last 100 samples for each sensor
    data_buffer = [collections.deque(maxlen=100) for _ in range(4)]

    # Zero the sensor before starting
    data_zero = sensor.process_single_measurement()

    try:
        while True:
            try:
                # Read and process a single measurement
                _, _, L0, L1, L2, L3 = sensor.process_single_measurement()
                raw_values = [L0, L1, L2, L3]
                tared_values = [raw - zero for raw, zero in zip(raw_values, data_zero[2:6])]

                # Append new values to the buffer
                for i, value in enumerate(tared_values):
                    data_buffer[i].append(value)

                # Update plot for each sensor
                for i, line in enumerate(lines):
                    line.set_data(range(len(data_buffer[i])), list(data_buffer[i]))

                ax.set_ylim(
                    min(min(buffer) for buffer in data_buffer) * 0.9,
                    max(max(buffer) for buffer in data_buffer) * 1.1
                )  # Dynamically adjust y-axis

                fig.canvas.draw()
                fig.canvas.flush_events()

                time.sleep(0.001)  # Adjust refresh rate as needed
            except Exception as e:
                print(f"Error during measurement processing: {e}")
    except KeyboardInterrupt:
        print("Exiting due to user interruption (Ctrl+C).")
    finally:
        sensor.disconnect()
        plt.ioff()
        plt.show()

if __name__ == "__main__":
    port = "COM3"  # Update with your serial port
    test_and_plot_sensor(port, sensor_config=[(0, 0x2B)])