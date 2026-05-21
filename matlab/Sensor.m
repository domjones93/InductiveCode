classdef Sensor < handle
    properties (Constant)
        INDUCTANCE_CONST = 25330.3387;
        FREQUENCY_CONST = 1.4901161249358807e-07;
        CAPACITANCE = 330.0;
        SENSOR_PACKET_BYTES = 18;
        PACKET_FIXED_BYTES = 8;
        DELIMITER = 'FFFEFD';
    end

    properties
        port
        baudrate = 115200
        timeout = 1
        ser = []
        net = []
        sensorConfig = [0, hex2dec('2A'); 1, hex2dec('2A')]
        autoConfigure = true
    end

    methods
        function obj = Sensor(port, baudrate, timeout, sensorConfig)
            if nargin >= 1 && ~isempty(port)
                obj.port = port;
            else
                obj.port = '';
            end
            if nargin >= 2 && ~isempty(baudrate)
                obj.baudrate = baudrate;
            end
            if nargin >= 3 && ~isempty(timeout)
                obj.timeout = timeout;
            end
            if nargin >= 4 && ~isempty(sensorConfig)
                obj.sensorConfig = sensorConfig;
            end
        end

        function count = sensor_count(obj)
            count = size(obj.sensorConfig, 1);
        end

        function len = packet_hex_length(obj)
            len = (obj.PACKET_FIXED_BYTES + obj.SENSOR_PACKET_BYTES * obj.sensor_count()) * 2;
        end

        function connect(obj)
            if isempty(obj.port)
                error('No port specified. Construct with Sensor(port) or set obj.port.');
            end
            try
                if ~isempty(obj.ser)
                    try
                        clear obj.ser;
                    catch
                    end
                    obj.ser = [];
                end

                obj.ser = serialport(obj.port, obj.baudrate, 'Timeout', obj.timeout);
                pause(0.5);
                try
                    flush(obj.ser);
                catch
                end
                fprintf('Connected to serial port %s\n', obj.port);

                if obj.autoConfigure
                    obj.configure_device(obj.sensorConfig);
                end
            catch ME
                warning('Error connecting to serial port %s: %s', obj.port, ME.message);
                obj.ser = [];
            end
        end

        function response = configure_device(obj, sensorConfig)
            if isempty(obj.ser)
                error('Serial connection is not established. Call connect() first.');
            end
            if nargin >= 2 && ~isempty(sensorConfig)
                obj.sensorConfig = sensorConfig;
            end
            obj.validate_sensor_config();

            payload = sprintf('%02X', obj.sensor_count());
            for i = 1:obj.sensor_count()
                payload = [payload, sprintf('%02X%02X', obj.sensorConfig(i, 1), obj.sensorConfig(i, 2))]; %#ok<AGROW>
            end
            command = ['C', payload, sprintf('\n')];

            flush(obj.ser);
            write(obj.ser, uint8(command), 'uint8');
            deadline = tic;
            response = '';
            while toc(deadline) < max(obj.timeout, 3.0)
                response = strtrim(readline(obj.ser));
                if ~isempty(response)
                    break;
                end
                pause(0.01);
            end
            if ~startsWith(response, 'CONFIG OK')
                error('MCU rejected sensor config %s: %s', strtrim(command), response);
            end
            fprintf('%s\n', response);
            pause(0.15);
            flush(obj.ser);
        end

        function data = read_single_measurement(obj)
            if isempty(obj.ser)
                error('Serial connection is not established. Call connect() first.');
            end

            flush(obj.ser);
            write(obj.ser, uint8('s'), 'uint8');
            expected = obj.packet_hex_length();
            deadline = tic;
            while obj.ser.NumBytesAvailable < expected
                if toc(deadline) > obj.timeout
                    error('Timed out waiting for packet: expected %d bytes, got %d.', expected, obj.ser.NumBytesAvailable);
                end
                pause(0.001);
            end

            raw = read(obj.ser, expected, 'uint8');
            data = char(raw(:)');
            if ~endsWith(data, obj.DELIMITER)
                error('Delimiter not found in received data.');
            end
        end

        function [timestamp, sensors] = process_single_measurement_all(obj)
            rawdata = obj.read_single_measurement();
            [timestamp, sensors] = obj.calibrate_packet(rawdata);
        end

        function [timestamp, status, L0, L1, L2, L3] = process_single_measurement(obj)
            [timestamp, sensors] = obj.process_single_measurement_all();
            status = sensors(1).status;
            L0 = sensors(1).inductance(1);
            L1 = sensors(1).inductance(2);
            L2 = sensors(1).inductance(3);
            L3 = sensors(1).inductance(4);
        end

        function [timestamp, sensors] = calibrate_packet(obj, raw_bytes)
            if length(raw_bytes) < obj.packet_hex_length()
                error('Packet too short: length %d', length(raw_bytes));
            end
            if ~endsWith(raw_bytes, obj.DELIMITER)
                error('Delimiter not found in received data.');
            end

            packet_count = double(hex2dec(raw_bytes(1:2)));
            if packet_count ~= obj.sensor_count()
                error('Packet has %d sensors, expected %d.', packet_count, obj.sensor_count());
            end
            if length(raw_bytes) ~= obj.packet_hex_length()
                error('Packet length %d does not match expected %d.', length(raw_bytes), obj.packet_hex_length());
            end

            timestamp = hex2dec(raw_bytes(3:10));
            offset = 11;
            sensors = repmat(struct( ...
                'index', 0, ...
                'bus', 0, ...
                'address', 0, ...
                'status', 0, ...
                'raw', zeros(1, 4), ...
                'inductance', zeros(1, 4)), packet_count, 1);

            for sensorIdx = 1:packet_count
                status_hex = raw_bytes(offset:offset + 3);
                offset = offset + 4;
                raw_values = zeros(1, 4);
                inductance_values = zeros(1, 4);

                for channelIdx = 1:4
                    raw_hex = raw_bytes(offset:offset + 7);
                    offset = offset + 8;
                    raw_value = double(hex2dec(raw_hex));
                    frequency = obj.FREQUENCY_CONST .* raw_value;
                    inductance_values(channelIdx) = obj.INDUCTANCE_CONST ./ (obj.CAPACITANCE .* (frequency .* frequency));
                    raw_values(channelIdx) = raw_value;
                end

                sensors(sensorIdx).index = sensorIdx - 1;
                sensors(sensorIdx).bus = obj.sensorConfig(sensorIdx, 1);
                sensors(sensorIdx).address = obj.sensorConfig(sensorIdx, 2);
                sensors(sensorIdx).status = double(hex2dec(status_hex));
                sensors(sensorIdx).raw = raw_values;
                sensors(sensorIdx).inductance = inductance_values;
            end
        end

        function values = flatten_inductance(~, sensors)
            values = [];
            for i = 1:numel(sensors)
                values = [values, sensors(i).inductance]; %#ok<AGROW>
            end
        end

        function load_calib_model(obj, model_path)
            if ~isfile(model_path)
                error('Model file not found: %s', model_path);
            end
            S = load(model_path, 'net');
            if isfield(S, 'net')
                obj.net = S.net;
                fprintf('Calibration model loaded from %s\n', model_path);
            else
                error('No variable ''net'' found in %s', model_path);
            end
        end

        function predictions = predict_position(obj, inductance_values)
            if isempty(obj.net)
                error('Calibration network not loaded. Call load_calib_model first.');
            end
            if ~isnumeric(inductance_values)
                error('inductance_values must be numeric.');
            end

            try
                if ismatrix(inductance_values) && size(inductance_values,2) == 4
                    in = inductance_values';
                else
                    in = inductance_values(:)';
                end
                if exist('predict','builtin') || exist('predict','file')
                    out = predict(obj.net, in);
                else
                    out = obj.net(in);
                end
                predictions = out';
            catch ME
                error('Prediction failed: %s', ME.message);
            end
        end

        function disconnect(obj)
            if isempty(obj.ser)
                fprintf('No active serial connection to disconnect.\n');
                return;
            end
            try
                write(obj.ser, uint8('x'), 'uint8');
                pause(0.01);
                flush(obj.ser);
            catch
            end
            try
                clear obj.ser;
            catch
            end
            obj.ser = [];
            fprintf('Disconnected from serial port.\n');
        end
    end

    methods (Access = private)
        function validate_sensor_config(obj)
            if size(obj.sensorConfig, 2) ~= 2
                error('sensorConfig must be an Nx2 matrix: [bus_index, i2c_address].');
            end
            if obj.sensor_count() < 1 || obj.sensor_count() > 3
                error('Pico firmware supports 1 to 3 configured sensors.');
            end
            if any(obj.sensorConfig(:, 1) < 0 | obj.sensorConfig(:, 1) > 1)
                error('I2C bus index must be 0 or 1.');
            end
            if any(obj.sensorConfig(:, 2) < 0 | obj.sensorConfig(:, 2) > 127)
                error('I2C addresses must be 7-bit values from 0 to 127.');
            end
        end
    end
end
