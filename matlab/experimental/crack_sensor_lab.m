% Queues (use cell arrays as simple queues)
calibrationQueue = {};
saveQueue = {};
recording = true;

function sensorReadWorker(sensor)
    nextTime = tic;
    while recording
        try
            [timestamp, ~, L0, L1, L2, L3] = sensor.process_single_measurement();
            data = [L0, L1, L2, L3];
            calibrationQueue{end+1} = {timestamp, data};
        catch e
            disp(['Error reading measurement: ', e.message]);
        end
        pause(max(0, 0.01 - toc(nextTime)));
        nextTime = tic;
    end
end

function calibrationWorker(sensor)
    batchSize = 10;
    batch = {};
    while recording || ~isempty(calibrationQueue)
        if ~isempty(calibrationQueue)
            item = calibrationQueue{1};
            calibrationQueue(1) = [];
            batch{end+1} = item;
            if length(batch) >= batchSize
                timestamps = cellfun(@(x) x{1}, batch);
                rawBatch = cell2mat(cellfun(@(x) x{2}, batch, 'UniformOutput', false)');
                predictions = sensor.predict_position(rawBatch);
                for j = 1:length(batch)
                    t = timestamps(j);
                    raw = rawBatch(j, :);
                    pred = predictions(j, :);
                    formatted = sprintf('%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f', t, raw(1), raw(2), raw(3), raw(4), pred(1), pred(2), pred(3));
                    saveQueue{end+1} = formatted;
                end
                batch = {};
            end
        end
        pause(0.01);
    end
    % Process remaining
    if ~isempty(batch)
        timestamps = cellfun(@(x) x{1}, batch);
        rawBatch = cell2mat(cellfun(@(x) x{2}, batch, 'UniformOutput', false)');
        predictions = sensor.predict_position(rawBatch);
        for j = 1:length(batch)
            t = timestamps(j);
            raw = rawBatch(j, :);
            pred = predictions(j, :);
            formatted = sprintf('%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f', t, raw(1), raw(2), raw(3), raw(4), pred(1), pred(2), pred(3));
            saveQueue{end+1} = formatted;
        end
    end
end

function saveDataWorker()
    datetimeStr = datestr(now, 'yyyymmdd_HHMMSS');
    filename = ['sensor_data_', datetimeStr, '.csv'];
    disp(['Saving data to ', filename]);
    fid = fopen(filename, 'w');
    fprintf(fid, 'Time,L0,L1,L2,L3,dX,dY,dZ\n');
    while recording || ~isempty(saveQueue)
        if ~isempty(saveQueue)
            line = saveQueue{1};
            saveQueue(1) = [];
            fprintf(fid, '%s\n', line);
        end
        pause(0.01);
    end
    fclose(fid);
end

% Main
serialPort = 'COM3'; % Adjust as needed
sensor = Sensor(serialPort);
sensor.connect();
if isempty(sensor.ser)
    disp('Failed to connect to sensor.');
    return;
end

% Load model (adjust paths)
sensor.load_model('./calibration_model.mat', './scalerX.mat', './scalerY.mat');

disp('Recording started. Press Ctrl+C to stop...');

% Start "threads" using timers
t1 = timer('TimerFcn', @(~,~) sensorReadWorker(sensor), 'Period', 0.01, 'ExecutionMode', 'fixedRate');
t2 = timer('TimerFcn', @(~,~) calibrationWorker(sensor), 'Period', 0.01, 'ExecutionMode', 'fixedRate');
t3 = timer('TimerFcn', @(~,~) saveDataWorker(), 'Period', 0.01, 'ExecutionMode', 'fixedRate');

start(t1);
start(t2);
start(t3);

pause(10); % Run for 10 seconds; adjust as needed
disp('Stopping recording...');

recording = false;
stop(t1);
stop(t2);
stop(t3);
delete(t1);
delete(t2);
delete(t3);

sensor.disconnect();
disp('Recording finished.');