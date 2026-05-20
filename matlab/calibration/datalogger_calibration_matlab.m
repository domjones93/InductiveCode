% Collect calibration data for multiple LDC1614 sensors, each on its own COM port.
% The output CSV contains one target position row with L0-L3 columns for every sensor.
close all
clear
clc

scriptDir = fileparts(mfilename('fullpath'));
addpath(fileparts(scriptDir));

% ---------------- User configuration ----------------
filename = fullfile(scriptDir, 'calibration_data_all_sensors.csv');

sensorSpecs = struct( ...
    'id', {'S1', 'S2', 'S3', 'S4', 'S5', 'S6'}, ...
    'port', {'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'COM10'}, ...
    'sensorConfig', { ...
        [0, hex2dec('2A')], ...
        [0, hex2dec('2A')], ...
        [0, hex2dec('2A')], ...
        [0, hex2dec('2A')], ...
        [0, hex2dec('2A')], ...
        [0, hex2dec('2A')]});

sampleRepeatsPerLocation = 1;
samplePauseSeconds = 0.05;

hexapodHost = "192.168.16.220";
hexapodPort = 23;
xlim = 5;
ylim = 5;
zlim = 2.5;
pitchValue = 0;
rollValue = 0;
yawValue = 0;
nTests = 300;
moveSettleSeconds = 0.3;
% ----------------------------------------------------

if exist(filename, 'file')
    overwrite = input([filename, ' already exists. Overwrite? (y/n): '], 's');
    if ~strcmpi(overwrite, 'y')
        disp('Exiting without overwriting.');
        return;
    end
end

locations = rand(nTests, 6) .* [2*xlim, 2*ylim, 2*zlim, 0, 0, 0] - [xlim, ylim, zlim, 0, 0, 0];
locations(:, 4:6) = [rollValue, pitchValue, yawValue];
locations = optimize_path(locations);

sensors = cell(1, numel(sensorSpecs));
solano = [];
fid = -1;

try
    solano = tcpclient(hexapodHost, hexapodPort, "Timeout", 1);
    disp('Connecting to Solano hexapod...');
    writeline(solano, "your_auth_command");
    writeline(solano, "init_command");
    pause(0.5);
    disp('Connected to Solano hexapod.');

    for idx = 1:numel(sensorSpecs)
        sensors{idx} = Sensor(sensorSpecs(idx).port, [], [], sensorSpecs(idx).sensorConfig);
        sensors{idx}.connect();
    end

    fid = fopen(filename, 'w');
    if fid == -1
        error('Unable to create calibration file: %s', filename);
    end
    fprintf(fid, '%s\n', strjoin(build_calibration_header(sensorSpecs), ','));

    writeline(solano, "ControlOn");
    writeline(solano, "move_P2P 0 0 0 " + num2str(rollValue) + " " + num2str(pitchValue) + " " + num2str(yawValue));
    disp('Hexapod at initial position. Press Enter to start.');
    input('');

    for i = 1:size(locations, 1)
        clc;
        fprintf('Moving to location %d of %d\n', i, size(locations, 1));
        x = locations(i, 1);
        y = locations(i, 2);
        z = locations(i, 3);
        roll = locations(i, 4);
        pitch = locations(i, 5);
        yaw = locations(i, 6);

        writeline(solano, "move_P2P " + num2str(x) + " " + num2str(y) + " " + num2str(z) + " " + num2str(roll) + " " + num2str(pitch) + " " + num2str(yaw));
        pause(moveSettleSeconds);

        for repeatIdx = 1:sampleRepeatsPerLocation
            rowValues = nan(1, numel(sensorSpecs) * 4);
            for sensorIdx = 1:numel(sensors)
                try
                    [~, sensorPackets] = sensors{sensorIdx}.process_single_measurement_all();
                    rowValues(sensor_column_range(sensorIdx)) = sensorPackets(1).inductance;
                catch ME
                    warning('Failed reading %s on %s: %s', sensorSpecs(sensorIdx).id, sensorSpecs(sensorIdx).port, ME.message);
                end
            end

            fprintf(fid, ['%.10f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,', repmat('%.9f,', 1, numel(rowValues) - 1), '%.9f\n'], ...
                now, x, y, z, roll, pitch, yaw, rowValues);
            pause(samplePauseSeconds);
        end
    end

    writeline(solano, "ControlOff");
    fprintf('Calibration data saved to: %s\n', filename);
catch ME
    warning('Calibration stopped: %s', ME.message);
end

if fid ~= -1
    fclose(fid);
end
for idx = 1:numel(sensors)
    if ~isempty(sensors{idx})
        sensors{idx}.disconnect();
    end
end
if ~isempty(solano)
    try
        writeline(solano, "ControlOff");
    catch
    end
    clear solano;
end

function optimizedPath = optimize_path(locations)
    if isempty(locations)
        optimizedPath = [];
        return;
    end
    optimizedPath = locations(1, :);
    locations(1, :) = [];
    while ~isempty(locations)
        last = optimizedPath(end, 1:3);
        distances = vecnorm(locations(:, 1:3) - last, 2, 2);
        [~, idx] = min(distances);
        optimizedPath = [optimizedPath; locations(idx, :)]; %#ok<AGROW>
        locations(idx, :) = [];
    end
end

function header = build_calibration_header(sensorSpecs)
    header = {'timestamp', 'Tx', 'Ty', 'Tz', 'Roll', 'Pitch', 'Yaw'};
    for sensorIdx = 1:numel(sensorSpecs)
        for channelIdx = 0:3
            header{end + 1} = sprintf('%s_L%d', sensorSpecs(sensorIdx).id, channelIdx); %#ok<AGROW>
        end
    end
end

function cols = sensor_column_range(sensorIdx)
    firstCol = (sensorIdx - 1) * 4 + 1;
    cols = firstCol:(firstCol + 3);
end
