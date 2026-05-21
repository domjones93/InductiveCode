% Multi-sensor MATLAB datalogger.
% Select active sensors by ID; sensors can share a COM port when their
% bus/address pairs are listed separately.
close all
clear
clc

% ---------------- User configuration ----------------
sensorSpecs = struct( ...
    'id', {'S1', 'S2', 'S3', 'S4', 'S5', 'S6'}, ...
    'port', {'COM3', 'COM3', 'COM3', 'COM8', 'COM9', 'COM10'}, ...
    'calibrationFile', { ...
        fullfile('calibrations', 'S1_net.mat'), ...
        fullfile('calibrations', 'S2_net.mat'), ...
        fullfile('calibrations', 'S3_net.mat'), ...
        fullfile('calibrations', 'S4_net.mat'), ...
        fullfile('calibrations', 'S5_net.mat'), ...
        fullfile('calibrations', 'S6_net.mat')}, ...
    'sensorConfig', { ...
        [0, hex2dec('2A')], ...
        [1, hex2dec('2A')], ...
        [1, hex2dec('2B')], ...
        [0, hex2dec('2A')], ...
        [0, hex2dec('2A')], ...
        [0, hex2dec('2A')]});

activeSensorIds = {'S1', 'S2', 'S3'};
samplePeriod = 0.01;
durationSeconds = 5;
BATCH_SIZE = 10;
serialTimeout = 5;
% ----------------------------------------------------

scriptDir = fileparts(mfilename('fullpath'));
logfile = fullfile(scriptDir, sprintf('sensor_data_%s.csv', datestr(now, 'yyyymmdd_HHMMSS')));
activeSpecs = select_sensor_specs(sensorSpecs, activeSensorIds);
activeSpecs = load_calibration_models(activeSpecs, scriptDir);

portSessions = build_port_sessions(activeSpecs, serialTimeout);
verify_port_sessions(portSessions, activeSpecs);

fid = fopen(logfile, 'w');
if fid == -1
    error('Unable to create logfile: %s', logfile);
end
fprintf(fid, '%s\n', strjoin(build_log_header(activeSpecs), ','));
fclose(fid);

state = containers.Map();
state('portSessions') = portSessions;
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
    disconnect_all(portSessions);
    fprintf('Recording finished. File saved to: %s\n', logfile);
else
    fprintf('Recording running indefinitely. Use stop(t); delete(t); then flushRemainingBatch(state) to stop manually.\n');
end

function timerTick(~, ~, st)
    portSessions = st('portSessions');
    sensorSpecs = st('sensorSpecs');
    measurement.timestamp = now;
    measurement.raw = nan(numel(sensorSpecs), 4);
    measurement.pred = nan(numel(sensorSpecs), 3);

    for sessionIdx = 1:numel(portSessions)
        try
            session = portSessions(sessionIdx);
            [~, sensorPackets] = session.sensor.process_single_measurement_all();
            for packetIdx = 1:numel(sensorPackets)
                sensorIdx = session.sensorIndices(packetIdx);
                inductanceValues = sensorPackets(packetIdx).inductance;
                measurement.raw(sensorIdx, :) = inductanceValues;
                measurement.pred(sensorIdx, :) = predict_sensor(sensorSpecs(sensorIdx), inductanceValues);
            end
        catch ME
            warning('Failed reading %s: %s', describe_session(portSessions(sessionIdx), sensorSpecs), ME.message);
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

function pred = predict_sensor(sensorSpec, inductanceValues)
    pred = nan(1, 3);
    if ~isfield(sensorSpec, 'net') || isempty(sensorSpec.net)
        return;
    end

    try
        if ismatrix(inductanceValues) && size(inductanceValues, 2) == 4
            in = inductanceValues';
        else
            in = inductanceValues(:)';
        end
        if exist('predict','builtin') || exist('predict','file')
            sensorPred = predict(sensorSpec.net, in);
        else
            sensorPred = sensorSpec.net(in);
        end
        sensorPred = sensorPred(:).';
        pred(1:min(3, numel(sensorPred))) = sensorPred(1:min(3, numel(sensorPred)));
    catch ME
        warning('Prediction failed for %s: %s', sensorSpec.id, ME.message);
    end
end

function activeSpecs = load_calibration_models(activeSpecs, scriptDir)
    for idx = 1:numel(activeSpecs)
        activeSpecs(idx).net = [];
        calibrationPath = resolve_path(scriptDir, activeSpecs(idx).calibrationFile);
        if isfile(calibrationPath)
            S = load(calibrationPath, 'net');
            if isfield(S, 'net')
                activeSpecs(idx).net = S.net;
                fprintf('Calibration model for %s loaded from %s\n', activeSpecs(idx).id, calibrationPath);
            else
                warning('No variable ''net'' found in %s. Predictions for %s will be NaN.', calibrationPath, activeSpecs(idx).id);
            end
        else
            warning('Calibration file for %s was not found: %s. Predictions will be NaN.', activeSpecs(idx).id, calibrationPath);
        end
    end
end

function portSessions = build_port_sessions(activeSpecs, serialTimeout)
    ports = unique({activeSpecs.port}, 'stable');
    portSessions = repmat(struct('port', '', 'sensor', [], 'sensorIndices', []), 1, numel(ports));

    for portIdx = 1:numel(ports)
        sensorIndices = find(strcmp({activeSpecs.port}, ports{portIdx}));
        sensorConfig = vertcat(activeSpecs(sensorIndices).sensorConfig);

        portSessions(portIdx).port = ports{portIdx};
        portSessions(portIdx).sensorIndices = sensorIndices;
        portSessions(portIdx).sensor = Sensor(ports{portIdx}, [], serialTimeout, sensorConfig);
        portSessions(portIdx).sensor.connect();
        if isempty(portSessions(portIdx).sensor.ser)
            error('Failed to connect/configure %s for %s. Check that the port is correct, not already open, and that the MCU firmware accepts %d configured sensors.', ...
                ports{portIdx}, strjoin({activeSpecs(sensorIndices).id}, ', '), numel(sensorIndices));
        end
    end
end

function verify_port_sessions(portSessions, sensorSpecs)
    for sessionIdx = 1:numel(portSessions)
        session = portSessions(sessionIdx);
        try
            [~, sensorPackets] = session.sensor.process_single_measurement_all();
            if numel(sensorPackets) ~= numel(session.sensorIndices)
                error('Expected %d sensor packets, received %d.', numel(session.sensorIndices), numel(sensorPackets));
            end
        catch ME
            error(['Connected to %s, but no valid measurement packet was received for %s. ', ...
                   'If the timeout says "got 0", confirm the updated firmware is flashed and that ', ...
                   'the firmware responds to the lowercase ''s'' single-sample command. Original error: %s'], ...
                session.port, describe_session(session, sensorSpecs), ME.message);
        end
    end
end

function activeSpecs = select_sensor_specs(sensorSpecs, activeSensorIds)
    activeSpecs = sensorSpecs([]);
    for idx = 1:numel(activeSensorIds)
        match = find(strcmpi({sensorSpecs.id}, activeSensorIds{idx}), 1);
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

function description = describe_session(session, sensorSpecs)
    ids = {sensorSpecs(session.sensorIndices).id};
    description = sprintf('%s on %s', strjoin(ids, ', '), session.port);
end

function disconnect_all(portSessions)
    for idx = 1:numel(portSessions)
        if ~isempty(portSessions(idx).sensor)
            portSessions(idx).sensor.disconnect();
        end
    end
end
