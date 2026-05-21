% Collect calibration data for multiple LDC1614 sensors, each on its own COM port.
% Each sensor gets its own CSV file, while all sensors are sampled at each target.
close all
clear
clc

scriptDir = fileparts(mfilename('fullpath'));
addpath(fileparts(scriptDir));

% ---------------- User configuration ----------------
recordingType = 'calibration'; % 'calibration' or 'validation'
outputDir = fullfile(fileparts(scriptDir), 'v2_sensor');

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

if ~isfolder(outputDir)
    mkdir(outputDir);
end

locations = rand(nTests, 6) .* [2*xlim, 2*ylim, 2*zlim, 0, 0, 0] - [xlim, ylim, zlim, 0, 0, 0];
locations(:, 4:6) = [rollValue, pitchValue, yawValue];
locations = optimize_path(locations);

sensors = cell(1, numel(sensorSpecs));
fileIds = -ones(1, numel(sensorSpecs));
filenames = cell(1, numel(sensorSpecs));
solano = [];

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

    timestampLabel = datestr(now, 'yyyymmdd-HHMMSS');
    for sensorIdx = 1:numel(sensorSpecs)
        sensorId = lower(sensorSpecs(sensorIdx).id);
        filenames{sensorIdx} = fullfile(outputDir, sprintf('%s_%s_%s.csv', recordingType, sensorId, timestampLabel));
        fileIds(sensorIdx) = fopen(filenames{sensorIdx}, 'w');
        if fileIds(sensorIdx) == -1
            error('Unable to create calibration file: %s', filenames{sensorIdx});
        end
        fprintf(fileIds(sensorIdx), 'timestamp,Tx,Ty,Tz,Roll,Pitch,Yaw,L0,L1,L2,L3\n');
    end

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
            for sensorIdx = 1:numel(sensors)
                try
                    [~, sensorPackets] = sensors{sensorIdx}.process_single_measurement_all();
                    inductanceValues = sensorPackets(1).inductance;
                catch ME
                    inductanceValues = nan(1, 4);
                    warning('Failed reading %s on %s: %s', sensorSpecs(sensorIdx).id, sensorSpecs(sensorIdx).port, ME.message);
                end

                fprintf(fileIds(sensorIdx), '%.10f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.9f,%.9f,%.9f,%.9f\n', ...
                    now, x, y, z, roll, pitch, yaw, inductanceValues);
            end
            pause(samplePauseSeconds);
        end
    end

    writeline(solano, "ControlOff");
    fprintf('Calibration data saved to:\n');
    for sensorIdx = 1:numel(filenames)
        fprintf('  %s\n', filenames{sensorIdx});
    end
catch ME
    warning('Calibration stopped: %s', ME.message);
end

for sensorIdx = 1:numel(fileIds)
    if fileIds(sensorIdx) ~= -1
        fclose(fileIds(sensorIdx));
    end
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
