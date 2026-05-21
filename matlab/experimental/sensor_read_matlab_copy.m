%% MATLAB script for getting inductive sensor data and producing distances from calibration
% Author: Charlie DeLorey
% Date: 02/09/2025


clc;
clear;

serialportfind


%% Constants
INDUCTANCE_CONST = 25330.3387;
SENSOR_RESOLUTION = hex2dec('FFFFFFF');
FREQUENCY_CONST = 40.0 / SENSOR_RESOLUTION;
CAPACITANCE = 330.0;
DELIMITER = 'FFFEFD';



%%
port = 'COM9'; % Change to your Arduino's port
baudRate = 115200;
timeout = 5; % in seconds
delimiterBytes = uint8([255, 254, 253]); % 'FFFEFD' in decimal
delimiter = 'FFFEFD';

a = serialportfind;
delete(a);
clear a;

s = serialport(port, baudRate);
flush(s);
s.Timeout = timeout;

numSamples = 1000;
dataArray = [];


%%

for i=1:numSamples
    write(s, 's', 'char');

    dataBuffer = [];

    while true
        if s.NumBytesAvailable > 0
            newData = read(s, s.NumBytesAvailable, 'string');
            dataBuffer = [dataBuffer; newData];

            % check for delimiter
            idx = strfind(dataBuffer, DELIMITER);
            if ~isempty(idx)
                packetBytes = dataBuffer{end}(1:idx-1);

                if mod(length(packetBytes), 2) == 0
                    packet = typecast(uint8(packetBytes), 'uint16');
                    dataArray = [dataArray; packet'];
                else
                    warning('malformed packet at sample no %d', i);
                end

                break;
            end
        end
        pause(0.005);
    end
end


%% calibrating values

[timestamp, status, L0, L1, L2, L3] = calibrate_packet(dataArray, FREQUENCY_CONST, INDUCTANCE_CONST, CAPACITANCE);



%% Plot results

figure;
% plot(dataArray);
plot(timestamp, L0, 'L0');
plot(timestamp, L1, 'L1');
plot(timestamp, L2, 'L2');
plot(timestamp, L3, 'L3');

xlabel('Time (s)');
ylabel('Sensor Value');
title('Sensor Measurements');
grid on;



%%

% MAYBE NOT WORKING CODE AFTER THIS





%%

while true
    
    % trigger a measurement
    write(s, 's', 'char');

    % Read available bytes
    if s.NumBytesAvailable > 0
        newData = read(s, s.NumBytesAvailable, 'uint8');
        dataBuffer = [dataBuffer; newData];

        % Search for delimiter
        idx = strfind(dataBuffer, delimiterBytes);
        if ~isempty(idx)
            % Extract data before delimiter
            packet = dataBuffer(1:idx(1)-1);

            % Display or process the packet
            disp('Received packet:');
            disp(packet');

            data(end+1) = packet;

            % Remove processed data from buffer
            dataBuffer = dataBuffer(idx(1)+length(delimiterBytes):end);


        end
    end

    pause(0.01); % Small delay to prevent CPU overload
end





%%


% fwrite(s, 's', 'char');

% Initialize buffer
buffer = [];

% Read until delimiter [255, 254, 253] is found
delimiter = [255, 254, 253];

while true
    if s.BytesAvailable > 0
        byte = fread(s, 1, 'uint8');
        buffer = [buffer; byte];
        
        % Check if the last 3 bytes match the delimiter
        if length(buffer) >= 3 && isequal(buffer(end-2:end)', delimiter)
            break;
        end
    end
end

% Convert buffer to string (if needed)
packet_str = char(buffer');

% Decode using calibrate_packet
[timestamp, status, L0, L1, L2, L3] = calibrate_packet(packet_str, FREQUENCY_CONST, INDUCTANCE_CONST, CAPACITANCE);







%%


[timestamp, status, L0, L1, L2, L3] = calibrate_packet(buffer, FREQUENCY_CONST, INDUCTANCE_CONST, CAPACITANCE);


%% Define serial port and settings
port = 'COM10'; % Change to your Arduino's port
baudRate = 115200;
timeout = 1; % in seconds

delete(instrfind({'Port'}, {'COM10'}));

s = serial(port, 'BaudRate', baudRate, 'Timeout', timeout);

% Flush any existing data
flushoutput(s);

% make serial connection
fopen(s);
disp('Serial connection opened');

% Send trigger character to Arduino
% triggerChar = 'Q'; % Change to your desired trigger
% fprintf(s, triggerChar);

% Wait for data to be available
pause(1); % Adjust based on expected response time

% Read incoming data
data = fscanf(s); % Reads one line of data

% Display or record the data
disp(['Received: ', data]);


% initialise sensor?
% fprintf(s, 'i');
% pause(timeout);


% choose measurement mode ('s' for single, 'c' for continuous)
mode = 's';

flushoutput(s);


% sending measurement mode to sensor
fprintf(s, mode);
pause(0.1); 

data = {};
decodedData = [];

%%

try
%     while true
        if strcmp(mode, 's')
            if s.BytesAvailable > 0
                raw = fread(s, s.BytesAvailable, 'uint8');
                rawStr = char(raw');
%                 data{end+1} = rawStr;
        %         data{end+1} = fscanf(s);
                idx = strfind(rawStr, DELIMITER);
                while ~isEmpty(idx)
                    packet = rawStr(1:idx(1)-1);
    %                 rawStr = rawStr(idx(1)+length(DELIMITER):end);

                        % decode packet
                    if length(packet) >= 44
                        [timestamp, status, L0, L1, L2, L3] = calibrate_packet(packet, FREQUENCY_CONST, INDUCTANCE_CONST, CAPACITANCE);
                        decodedData(end+1, :) = [timestamp, status, L0, L1, L2, L3];
                        disp([timestamp, status, L0, L1, L2, L3]);
                    end

                        % search for next delimiter
                    idx = strfind(rawStr, DELIMITER);
                end
            end
            pause(0.5);
        end
%     end
catch
        disp('Measurement stopped by user');
end



%% Close serial connection
fclose(s);
delete(s);
clear s;
disp('Serial connection closed.');

%     else
%         disp('No single measurement data received');
%     end
% elseif strcmp(mode, 'c')
%     disp('Receiving continuous data. Press Ctrl+C to stop.');
%     while true
%         if s.BytesAvailable > 0
%             resp = fscanf(s);
%             disp(['Measurement: ', data]);
%             data{end+1} = resp;
%         end
%         pause(0.05); % Adjust for your sensor's data rate
%     end
% end


%% processing data





%%




plot(data);


%%
% Optionally save to file
filename = 'arduino_data.txt';
fid = fopen(filename, 'a');
fprintf(fid, '%s\n', data);
fclose(fid);

% Clean up
clear s;





%%
% 
% INDUCTANCE_CONST = 025330.3387; % (1/(4*3.14159*3.14159));
% SENSOR_RESOLUTION = 0xFFFFFFF; % 28-bit
% FREQUENCY_CONST = 40./SENSOR_RESOLUTION; % (f_ref/sensor_resolution)
% CAPACITANCE = 330.0; % pF
% 
% def connect_to_serial(port, baudrate=115200, timeout=1, xonxoff=False, rtscts=False, dsrdtr=False):
%     try:
%         ser = serial.Serial(port, baudrate, timeout=timeout)
%         return ser
%     except serial.SerialException as e:
%         print(f"Error connecting to serial port {port}: {e}")
%         return None
%     
% def query_device(ser):
%     if ser is not None:
%         ser.flushInput()
%         ser.flushOutput()
%         ser.write(b'Q')
%         time.sleep(0.1)  # Wait for the device to respond
%         response = ser.readline().decode()
%         return response
%     else:
%         print("Serial connection is not established.")
%         return None
% 
% class Sensor:
%     def __init__(self, port, baudrate=115200, timeout=1):
%         self.port = port
%         self.baudrate = baudrate
%         self.timeout = timeout
%         self.ser = None
%         self.calibration = FeedForwardNN(input_size=4, output_size=3)
% 
%     def connect(self):
%         try:
%             self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
%             self.ser.flushInput()
%             self.ser.flushOutput()
%             print(f"Connected to serial port {self.port}")
%         except serial.SerialException as e:
%             print(f"Error connecting to serial port {self.port}: {e}")
%             self.ser = None
% 
%     def read_single_measurement(self):
%         """
%         Reads a single measurement from the sensor.
% 
%         :return: The raw data buffer containing the measurement.
%         """
%         if not self.ser:
%             raise ConnectionError("Serial connection is not established. Call connect() first.")
% 
%         self.ser.write(b's')  # Send the single measurement command
%         time.sleep(0.01)  # Wait for the device to respond
% 
%         data = self.ser.read_all()
%         if not data:
%             raise ValueError("No data received from the sensor.")
% 
%         return data
% 
%     def process_single_measurement(self):
%         """
%         Processes a single measurement by extracting packets, calibrating, and saving.
%         """
%         data = self.read_single_measurement()
%         delimiter = b'FFFEFD'
% 
%         idx = data.find(delimiter)
%         while idx != -1:
%             raw_packet = data[:idx]  # Packet before delimiter
%             data = data[idx + len(delimiter):]  # Remove processed packet
%             timestamp, status, L0, L1, L2, L3 = self.calibrate_packet(raw_packet)
%             return timestamp, status, L0, L1, L2, L3
% 
%     def calibrate_packet(self, raw_bytes):
%         timestamp = int(raw_bytes[:8].decode('utf-8'), 16)
%         status = int(raw_bytes[8:12].decode('utf-8'), 16)
%         Raw0 = int(raw_bytes[12:20].decode('utf-8'), 16)
%         Raw1 = int(raw_bytes[20:28].decode('utf-8'), 16)
%         Raw2 = int(raw_bytes[28:36].decode('utf-8'), 16)
%         Raw3 = int(raw_bytes[36:44].decode('utf-8'), 16)
% 
%         F0 = FREQUENCY_CONST * Raw0
%         F1 = FREQUENCY_CONST * Raw1
%         F2 = FREQUENCY_CONST * Raw2
%         F3 = FREQUENCY_CONST * Raw3
% 
%         # Convert to inductance
%         L0 = INDUCTANCE_CONST / (CAPACITANCE * F0 * F0)
%         L1 = INDUCTANCE_CONST / (CAPACITANCE * F1 * F1)
%         L2 = INDUCTANCE_CONST / (CAPACITANCE * F2 * F2)
%         L3 = INDUCTANCE_CONST / (CAPACITANCE * F3 * F3)
% 
%         return timestamp, status, L0, L1, L2, L3
% 
%     def load_calib_model(self, model_path):
%         """
%         Load a calibration model from a file.
%         """
%         try:
%             self.calibration_matrix.load_state_dict(torch.load(model_path))
%             print(f"Calibration model loaded from {model_path}")
%         except Exception as e:
%             print(f"Error loading calibration model: {e}")
%             self.calibration_matrix = None
%         
%         self.calibration_matrix.eval()
% 
%     def predict_position(self, inductance_values):
%         """
%         Predicts the position based on inductance values using the calibration model.
%         
%         :param inductance_values: A list or array of inductance values [L0, L1, L2, L3].
%         :return: Predicted position as a numpy array [Tx, Ty, Tz].
%         """
%         if self.calibration_matrix is None:
%             raise ValueError("Calibration model is not loaded.")
% 
%         inductance_tensor = torch.tensor(inductance_values, dtype=torch.float32).unsqueeze(0)
%         with torch.no_grad():
%             predicted_positions = self.calibration_matrix(inductance_tensor).numpy()
%         
%         return predicted_positions
%     
%     def disconnect(self):
%         """
%         Closes the serial connection to the sensor.
%         """
%         if self.ser:
%             self.ser.write(b'x')  # Send a command to exit the device
%             
%             self.ser.flushInput()
%             self.ser.flushOutput()
% 
%             self.ser.close()
%             print("Disconnected from serial port.")
%             self.ser = None
%         else:
%             print("No active serial connection to disconnect.")
