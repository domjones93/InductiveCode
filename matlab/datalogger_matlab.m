% Multi-sensor MATLAB datalogger.
% Select active sensors by ID; each selected sensor uses its own COM port and calibration.
close all
clear
clc

% ---------------- User configuration ----------------
sensorSpecs = struct( ...
    'id', {'S1', 'S2', 'S3', 'S4', 'S5', 'S6'}, ...
    'port', {'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'COM10'}, ...
    'calibrationFile', { ...
        fullfile('calibrations', 'S1_net.mat'), ...
        fullfile('calibrations', 'S2_net.mat'), ...
        fullfile('calibrations', 'S3_net.mat'), ...
        fullfile('calibrations', 'S4_net.mat'), ...
        fullfile('calibrations', 'S5_net.mat'), ...
        fullfile('calibrations', 'S6_net.mat')}, ...
    'sensorConfig', { ...
        [0, hex2dec('2A')], ...
        [0, hex2dec('2A')], ...
        [0, hex2dec('2A')], ...
        [0, hex2dec('2A')], ...
        [0, hex2dec('2A')], ...
        [0, hex2dec('2A')]});

activeSensorIds = {'S1', 'S2', 'S3', 'S4', 'S5', 'S6'};
samplePeriod = 0.01;
durationSeconds = 5;
BATCH_SIZE = 10;
% ----------------------------------------------------

scriptDir = fileparts(mfilename('fullpath'));
logfile = fullfile(scriptDir, sprintf('sensor_data_%s.csv', datestr(now, 'yyyymmdd_HHMMSS')));
activeSpecs = select_sensor_specs(sensorSpecs, activeSensorIds);

sensors = cell(1, numel(activeSpecs));
for idx = 1:numel(activeSpecs)
    sensors{idx} = Sensor(activeSpecs(idx).port, [], [], activeSpecs(idx).sensorConfig);
    sensors{idx}.connect();
    calibrationPath = resolve_path(scriptDir, activeSpecs(idx).calibrationFile);
    if isfile(calibrationPath)
        sensors{idx}.load_calib_model(calibrationPath);
    else
        warning('Calibration file for %s was not found: %s. Predictions will be NaN.', activeSpecs(idx).id, calibrationPath);
    end
end

fid = fopen(logfile, 'w');
if fid == -1
    error('Unable to create logfile: %s', logfile);
end
fprintf(fid, '%s\n', strjoin(build_log_header(activeSpecs), ','));
fclose(fid);

state = containers.Map();
state('sensors') = sensors;
state('sensorSpecs') = activeSpecs;
state('batch') = {};
state('BATCH_SIZE') = BATCH_SIZE;
state('logfile') = logfile;

t = timer('ExecutionMode', 'fixedSpacing', 'Period', samplePeriod, ...
          'TimerFcn', {@timerTick, state});
start(t);
fprintf('Recording started for %s. Logging to: %s\n', strjoin({activeSpecs.id}, ', '), logfile);

if isfinite(durationSeconds)
    pause(durationSeconds);
    stop(t);
    delete(t);
    flushRemainingBatch(state);
    disconnect_all(sensors);
    fprintf('Recording finished. File saved to: %s\n', logfile);
else
    fprintf('Recording running indefinitely. Use stop(t); delete(t); then flushRemainingBatch(state) to stop manually.\n');
end

function timerTick(~, ~, st)
    sensors = st('sensors');
    sensorSpecs = st('sensorSpecs');
    measurement.timestamp = now;
    measurement.raw = nan(numel(sensors), 4);
    measurement.pred = nan(numel(sensors), 3);

    for sensorIdx = 1:numel(sensors)
        try
            [~, sensorPackets] = sensors{sensorIdx}.process_single_measurement_all();
            inductanceValues = sensorPackets(1).inductance;
            measurement.raw(sensorIdx, :) = inductanceValues;
            measurement.pred(sensorIdx, :) = predict_sensor(sensors{sensorIdx}, inductanceValues);
        catch ME
            warning('Failed reading %s on %s: %s', sensorSpecs(sensorIdx).id, sensorSpecs(sensorIdx).port, ME.message);
        end
    end

    batch = st('batch');
    batch{end + 1, 1} = measurement;
    st('batch') = batch;

    if numel(batch) >= st('BATCH_SIZE')
        append_batch(st('logfile'), batch);
        st('batch') = {};
    end
end

function flushRemainingBatch(st)
    batch = st('batch');
    if isempty(batch)
        return;
    end
    append_batch(st('logfile'), batch);
    st('batch') = {};
end

function append_batch(logfile, batch)
    fidw = fopen(logfile, 'a');
    if fidw == -1
        warning('Failed to open logfile for append: %s', logfile);
        return;
    end

    for rowIdx = 1:numel(batch)
        measurement = batch{rowIdx};
        rowValues = [reshape(measurement.raw.', 1, []), reshape(measurement.pred.', 1, [])];
        fprintf(fidw, ['%.10f,', repmat('%.9f,', 1, numel(rowValues) - 1), '%.9f\n'], measurement.timestamp, rowValues);
    end
    fclose(fidw);
end

function pred = predict_sensor(sensor, inductanceValues)
    pred = nan(1, 3);
    if isempty(sensor.net)
        return;
    end

    try
        sensorPred = sensor.predict_position(inductanceValues);
        sensorPred = sensorPred(:).';
        pred(1:min(3, numel(sensorPred))) = sensorPred(1:min(3, numel(sensorPred)));
    catch ME
        warning('Prediction failed on %s: %s', sensor.port, ME.message);
    end
end

function activeSpecs = select_sensor_specs(sensorSpecs, activeSensorIds)
    activeSpecs = sensorSpecs([]);
    for idx = 1:numel(activeSensorIds)
        match = find(strcmp({sensorSpecs.id}, activeSensorIds{idx}), 1);
        if isempty(match)
            error('Unknown sensor ID selected: %s', activeSensorIds{idx});
        end
        activeSpecs(end + 1) = sensorSpecs(match); %#ok<AGROW>
    end
end

function header = build_log_header(sensorSpecs)
    header = {'timestamp'};
    for sensorIdx = 1:numel(sensorSpecs)
        sensorId = sensorSpecs(sensorIdx).id;
        for channelIdx = 0:3
            header{end + 1} = sprintf('%s_L%d', sensorId, channelIdx); %#ok<AGROW>
        end
    end
    for sensorIdx = 1:numel(sensorSpecs)
        sensorId = sensorSpecs(sensorIdx).id;
        header{end + 1} = sprintf('%s_dX', sensorId); %#ok<AGROW>
        header{end + 1} = sprintf('%s_dY', sensorId); %#ok<AGROW>
        header{end + 1} = sprintf('%s_dZ', sensorId); %#ok<AGROW>
    end
end

function pathOut = resolve_path(scriptDir, pathIn)
    if isabsolute(pathIn)
        pathOut = pathIn;
    else
        pathOut = fullfile(scriptDir, pathIn);
    end
end

function tf = isabsolute(pathIn)
    tf = startsWith(pathIn, filesep) || ~isempty(regexp(pathIn, '^[A-Za-z]:[\\/]', 'once'));
end

function disconnect_all(sensors)
    for idx = 1:numel(sensors)
        if ~isempty(sensors{idx})
            sensors{idx}.disconnect();
        end
    end
end
