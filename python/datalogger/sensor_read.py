import time

import serial
import serial.tools.list_ports
import torch
from torch import nn


class FeedForwardNN(nn.Module):
    def __init__(self, input_size, output_size, hidden_sizes=None):
        super().__init__()
        if hidden_sizes is None:
            hidden_sizes = [64, 64, 64, 64]
        layers = []
        in_dim = input_size
        for h in hidden_sizes:
            layers.append(nn.Linear(in_dim, h))
            layers.append(nn.ReLU())
            in_dim = h
        layers.append(nn.Linear(in_dim, output_size))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


INDUCTANCE_CONST = 25330.3387
SENSOR_RESOLUTION = 0xFFFFFFF
FREQUENCY_CONST = 40.0 / SENSOR_RESOLUTION
CAPACITANCE = 330.0
DELIMITER = b"FFFEFD"
SENSOR_PACKET_BYTES = 18
PACKET_FIXED_BYTES = 8
DEFAULT_SENSOR_CONFIG = [(0, 0x2A)]


def packet_hex_length(sensor_count):
    return (PACKET_FIXED_BYTES + SENSOR_PACKET_BYTES * sensor_count) * 2


def connect_to_serial(port, baudrate=115200, timeout=1, xonxoff=False, rtscts=False, dsrdtr=False):
    try:
        return serial.Serial(
            port,
            baudrate,
            timeout=timeout,
            xonxoff=xonxoff,
            rtscts=rtscts,
            dsrdtr=dsrdtr,
        )
    except serial.SerialException as e:
        print(f"Error connecting to serial port {port}: {e}")
        return None


def query_device(ser):
    if ser is None:
        print("Serial connection is not established.")
        return None

    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.write(b"Q")
    time.sleep(0.1)
    return ser.read_all().decode(errors="replace")


class Sensor:
    def __init__(self, port, baudrate=115200, timeout=1, sensor_config=None, auto_configure=True):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.sensor_config = list(sensor_config or DEFAULT_SENSOR_CONFIG)
        self.auto_configure = auto_configure
        self.ser = None
        self.last_config_response = ""
        self.calibration_matrix = FeedForwardNN(input_size=4, output_size=3)

    @property
    def sensor_count(self):
        return len(self.sensor_config)

    @property
    def packet_hex_length(self):
        return packet_hex_length(self.sensor_count)

    @staticmethod
    def build_config_command(sensor_config):
        if not 1 <= len(sensor_config) <= 3:
            raise ValueError("Pico firmware supports 1 to 3 configured sensors.")

        payload = f"{len(sensor_config):02X}"
        for bus_index, address in sensor_config:
            if bus_index not in (0, 1):
                raise ValueError(f"Invalid I2C bus index: {bus_index}")
            if not 0 <= address <= 0x7F:
                raise ValueError(f"Invalid I2C address: {address}")
            payload += f"{bus_index:02X}{address:02X}"

        return f"C{payload}\n".encode("ascii")

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(0.5)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            print(f"Connected to serial port {self.port}")
            if self.auto_configure:
                self.configure_device(self.sensor_config)
        except serial.SerialException as e:
            print(f"Error connecting to serial port {self.port}: {e}")
            self.ser = None

    def configure_device(self, sensor_config=None):
        if not self.ser:
            raise ConnectionError("Serial connection is not established. Call connect() first.")

        if sensor_config is not None:
            self.sensor_config = list(sensor_config)

        command = self.build_config_command(self.sensor_config)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.ser.write(command)
        self.ser.flush()

        deadline = time.monotonic() + max(self.timeout, 3.0)
        response = ""
        while time.monotonic() < deadline:
            response = self.ser.readline().decode(errors="replace").strip()
            if response:
                break
            time.sleep(0.01)

        if not response.startswith("CONFIG OK"):
            raise RuntimeError(f"MCU rejected sensor config {command!r}: {response!r}")

        self.last_config_response = response
        print(response)
        time.sleep(0.15)
        self.ser.reset_input_buffer()
        return response

    def read_single_measurement(self):
        if not self.ser:
            raise ConnectionError("Serial connection is not established. Call connect() first.")

        self.ser.write(b"s")
        data = self.ser.read_until(DELIMITER, self.packet_hex_length)
        if len(data) != self.packet_hex_length:
            raise ValueError(
                f"Incomplete packet: expected {self.packet_hex_length} ASCII bytes, got {len(data)}."
            )
        if not data.endswith(DELIMITER):
            raise ValueError("Delimiter not found in received data.")

        return data

    def process_single_measurement_all(self):
        data = self.read_single_measurement()
        return self.calibrate_packet(data)

    def process_single_measurement(self):
        timestamp, sensors = self.process_single_measurement_all()
        first = sensors[0]
        return (
            timestamp,
            first["status"],
            first["inductance"][0],
            first["inductance"][1],
            first["inductance"][2],
            first["inductance"][3],
        )

    def calibrate_packet(self, raw_bytes):
        raw_bytes = raw_bytes.strip()
        if not raw_bytes.endswith(DELIMITER):
            raise ValueError("Delimiter not found in received data.")
        if len(raw_bytes) < packet_hex_length(1):
            raise ValueError(f"Packet too short: length {len(raw_bytes)}")

        sensor_count = int(raw_bytes[0:2].decode("ascii"), 16)
        expected_length = packet_hex_length(sensor_count)
        if sensor_count != self.sensor_count:
            raise ValueError(f"Packet has {sensor_count} sensors, expected {self.sensor_count}.")
        if len(raw_bytes) != expected_length:
            raise ValueError(f"Packet length {len(raw_bytes)} does not match expected {expected_length}.")

        timestamp = int(raw_bytes[2:10].decode("ascii"), 16)
        sensors = []
        offset = 10
        for sensor_index in range(sensor_count):
            status = int(raw_bytes[offset:offset + 4].decode("ascii"), 16)
            offset += 4

            raw_values = []
            inductance_values = []
            for _ in range(4):
                raw_value = int(raw_bytes[offset:offset + 8].decode("ascii"), 16)
                offset += 8
                frequency = FREQUENCY_CONST * raw_value
                inductance = INDUCTANCE_CONST / (CAPACITANCE * frequency * frequency)
                raw_values.append(raw_value)
                inductance_values.append(inductance)

            sensors.append({
                "index": sensor_index,
                "bus": self.sensor_config[sensor_index][0],
                "address": self.sensor_config[sensor_index][1],
                "status": status,
                "raw": raw_values,
                "inductance": inductance_values,
            })

        return timestamp, sensors

    def load_calib_model(self, model_path):
        try:
            self.calibration_matrix.load_state_dict(torch.load(model_path))
            self.calibration_matrix.eval()
            print(f"Calibration model loaded from {model_path}")
        except Exception as e:
            print(f"Error loading calibration model: {e}")
            self.calibration_matrix = None

    def predict_position(self, inductance_values):
        if self.calibration_matrix is None:
            raise ValueError("Calibration model is not loaded.")

        inductance_tensor = torch.tensor(inductance_values, dtype=torch.float32)
        if inductance_tensor.ndim == 1:
            inductance_tensor = inductance_tensor.unsqueeze(0)

        with torch.no_grad():
            return self.calibration_matrix(inductance_tensor).numpy()

    def disconnect(self):
        if self.ser:
            self.ser.write(b"x")
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            self.ser.close()
            print("Disconnected from serial port.")
            self.ser = None
        else:
            print("No active serial connection to disconnect.")


if __name__ == "__main__":
    port = "COM3"
    sensor = Sensor(port)
    sensor.connect()
    try:
        while True:
            timestamp, sensors = sensor.process_single_measurement_all()
            values = ", ".join(
                f"S{s['index']}@I2C{s['bus']}/0x{s['address']:02X}: {s['inductance']}"
                for s in sensors
            )
            print(f"Timestamp: {timestamp}, {values}")
    except KeyboardInterrupt:
        print("Exiting due to user interruption (Ctrl+C).")
    finally:
        sensor.disconnect()
