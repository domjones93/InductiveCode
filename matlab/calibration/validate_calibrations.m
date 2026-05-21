% Validate all six sensor calibrations and compare transfer with a tare offset.
close all
clear
clc

scriptDir = fileparts(mfilename('fullpath'));

% ---------------- User configuration ----------------
dataDir = fullfile(fileparts(scriptDir), '../python/v2_sensor');
modelDir = fullfile(fileparts(scriptDir), 'calibrations');
resultsDir = fullfile(scriptDir, 'validation_results');
sensorIds = {'s1', 's2', 's3', 's4', 's5', 's6'};
validationPatternTemplate = 'validation_%s_*.csv';
fallbackPatternTemplate = ''; % Set to 'calibration_%s_*.csv' to test using calibration files.
targetColumns = {'Tx', 'Ty', 'Tz'};
inputColumns = {'L0', 'L1', 'L2', 'L3'};
tareMode = 'firstRows'; % 'firstRows' or 'meanAll'
tareRows = 20;
% ----------------------------------------------------

if ~isfolder(dataDir)
    error('Validation data folder not found: %s', dataDir);
end
if ~isfolder(modelDir)
    error('Calibration model folder not found: %s', modelDir);
end
if ~isfolder(resultsDir)
    mkdir(resultsDir);
end

sensorData = struct([]);
models = struct([]);

for sensorIdx = 1:numel(sensorIds)
    sensorId = sensorIds{sensorIdx};
    sensorData(sensorIdx).id = sensorId; %#ok<SAGROW>
    sensorData(sensorIdx).inputs = [];
    sensorData(sensorIdx).targets = [];
    sensorData(sensorIdx).sourceFiles = strings(1, 0);

    dataFiles = dir(fullfile(dataDir, sprintf(validationPatternTemplate, sensorId)));
    if isempty(dataFiles) && ~isempty(fallbackPatternTemplate)
        dataFiles = dir(fullfile(dataDir, sprintf(fallbackPatternTemplate, sensorId)));
    end
    if isempty(dataFiles)
        warning('No validation files found for %s.', upper(sensorId));
    else
        [inputs, targets, sourceFiles] = load_sensor_files(dataFiles, inputColumns, targetColumns, sensorId);
        validRows = all(isfinite(inputs), 2) & all(isfinite(targets), 2);
        sensorData(sensorIdx).inputs = inputs(validRows, :);
        sensorData(sensorIdx).targets = targets(validRows, :);
        sensorData(sensorIdx).sourceFiles = sourceFiles;
    end

    modelFile = fullfile(modelDir, sprintf('%s_net.mat', upper(sensorId)));
    models(sensorIdx).id = sensorId; %#ok<SAGROW>
    models(sensorIdx).file = modelFile;
    models(sensorIdx).net = [];
    if isfile(modelFile)
        loaded = load(modelFile, 'net');
        models(sensorIdx).net = loaded.net;
    else
        warning('No calibration model found for %s: %s', upper(sensorId), modelFile);
    end
end

ownRows = cell(0, 12);
transferRows = cell(0, 11);
offsetRows = cell(0, 16);

for dataIdx = 1:numel(sensorIds)
    if isempty(sensorData(dataIdx).inputs)
        continue;
    end
    target = sensorData(dataIdx).targets;

    for modelIdx = 1:numel(sensorIds)
        if isempty(models(modelIdx).net)
            continue;
        end

        pred = predict_with_net(models(modelIdx).net, sensorData(dataIdx).inputs);
        baseMetrics = calculate_metrics(pred, target);
        [offset, tareCount] = calculate_tare_offset(pred, target, tareMode, tareRows);
        tarePred = pred + offset;
        tareMetrics = calculate_metrics(tarePred, target);

        transferRows(end + 1, :) = { ...
            upper(models(modelIdx).id), upper(sensorData(dataIdx).id), size(target, 1), ...
            baseMetrics.rmseX, baseMetrics.rmseY, baseMetrics.rmseZ, baseMetrics.rmse3D, ...
            baseMetrics.mae3D, baseMetrics.biasX, baseMetrics.biasY, baseMetrics.biasZ}; %#ok<SAGROW>

        offsetRows(end + 1, :) = { ...
            upper(models(modelIdx).id), upper(sensorData(dataIdx).id), size(target, 1), tareCount, ...
            offset(1), offset(2), offset(3), ...
            tareMetrics.rmseX, tareMetrics.rmseY, tareMetrics.rmseZ, tareMetrics.rmse3D, ...
            tareMetrics.mae3D, tareMetrics.biasX, tareMetrics.biasY, tareMetrics.biasZ, ...
            baseMetrics.rmse3D - tareMetrics.rmse3D}; %#ok<SAGROW>

        if modelIdx == dataIdx
            ownRows(end + 1, :) = { ...
                upper(sensorData(dataIdx).id), size(target, 1), ...
                baseMetrics.rmseX, baseMetrics.rmseY, baseMetrics.rmseZ, baseMetrics.rmse3D, ...
                baseMetrics.mae3D, baseMetrics.biasX, baseMetrics.biasY, baseMetrics.biasZ, ...
                tareMetrics.rmse3D, baseMetrics.rmse3D - tareMetrics.rmse3D}; %#ok<SAGROW>
        end
    end
end

ownSummary = cell2table(ownRows, 'VariableNames', { ...
    'Sensor', 'Rows', 'RMSE_X', 'RMSE_Y', 'RMSE_Z', 'RMSE_3D', ...
    'MAE_3D', 'Bias_X', 'Bias_Y', 'Bias_Z', 'Tared_RMSE_3D', 'Tare_Improvement_3D'});

transferSummary = cell2table(transferRows, 'VariableNames', { ...
    'Calibration', 'ValidationSensor', 'Rows', 'RMSE_X', 'RMSE_Y', 'RMSE_Z', 'RMSE_3D', ...
    'MAE_3D', 'Bias_X', 'Bias_Y', 'Bias_Z'});

taredTransferSummary = cell2table(offsetRows, 'VariableNames', { ...
    'Calibration', 'ValidationSensor', 'Rows', 'TareRows', 'Offset_X', 'Offset_Y', 'Offset_Z', ...
    'RMSE_X', 'RMSE_Y', 'RMSE_Z', 'RMSE_3D', 'MAE_3D', ...
    'Bias_X', 'Bias_Y', 'Bias_Z', 'Tare_Improvement_3D'});

writetable(ownSummary, fullfile(resultsDir, 'own_calibration_summary.csv'));
writetable(transferSummary, fullfile(resultsDir, 'transfer_summary.csv'));
writetable(taredTransferSummary, fullfile(resultsDir, 'tared_transfer_summary.csv'));

disp('Own calibration summary:');
disp(ownSummary);
disp('Transfer summary, lower RMSE_3D is better:');
disp(transferSummary);
disp('Tared transfer summary, positive Tare_Improvement_3D means tare helped:');
disp(taredTransferSummary);

plot_transfer_heatmap(transferSummary, sensorIds, 'RMSE_3D', ...
    'Cross-sensor transfer RMSE 3D', fullfile(resultsDir, 'transfer_rmse3d.png'));
plot_transfer_heatmap(taredTransferSummary, sensorIds, 'RMSE_3D', ...
    'Cross-sensor transfer RMSE 3D after tare', fullfile(resultsDir, 'tared_transfer_rmse3d.png'));

fprintf('Validation results saved to: %s\n', resultsDir);

function [inputs, targets, sourceFiles] = load_sensor_files(dataFiles, inputColumns, targetColumns, sensorId)
    inputs = [];
    targets = [];
    sourceFiles = strings(1, numel(dataFiles));
    for fileIdx = 1:numel(dataFiles)
        sourceFile = fullfile(dataFiles(fileIdx).folder, dataFiles(fileIdx).name);
        sourceFiles(fileIdx) = string(sourceFile);
        data = readtable(sourceFile);
        [fileInputs, fileTargets] = extract_columns(data, inputColumns, targetColumns, sensorId);
        inputs = [inputs; fileInputs]; %#ok<AGROW>
        targets = [targets; fileTargets]; %#ok<AGROW>
    end
end

function [inputs, targets] = extract_columns(data, inputColumns, targetColumns, sensorId)
    if all(ismember(inputColumns, data.Properties.VariableNames))
        inputs = data{:, inputColumns};
    else
        prefixedInputColumns = strcat(upper(sensorId), {'_L0', '_L1', '_L2', '_L3'});
        if all(ismember(prefixedInputColumns, data.Properties.VariableNames))
            inputs = data{:, prefixedInputColumns};
        else
            inputs = data{:, 8:11};
        end
    end

    if all(ismember(targetColumns, data.Properties.VariableNames))
        targets = data{:, targetColumns};
    else
        targets = data{:, 2:4};
    end
end

function pred = predict_with_net(net, inputs)
    pred = net(inputs.').';
end

function metrics = calculate_metrics(pred, target)
    err = pred - target;
    errNorm = vecnorm(err, 2, 2);
    metrics.rmseX = sqrt(mean(err(:, 1).^2));
    metrics.rmseY = sqrt(mean(err(:, 2).^2));
    metrics.rmseZ = sqrt(mean(err(:, 3).^2));
    metrics.rmse3D = sqrt(mean(errNorm.^2));
    metrics.mae3D = mean(errNorm);
    metrics.biasX = mean(err(:, 1));
    metrics.biasY = mean(err(:, 2));
    metrics.biasZ = mean(err(:, 3));
end

function [offset, tareCount] = calculate_tare_offset(pred, target, tareMode, tareRows)
    switch lower(tareMode)
        case 'firstrows'
            tareCount = min(tareRows, size(target, 1));
            tareIdx = 1:tareCount;
        case 'meanall'
            tareCount = size(target, 1);
            tareIdx = 1:tareCount;
        otherwise
            error('Unknown tareMode: %s', tareMode);
    end
    offset = mean(target(tareIdx, :) - pred(tareIdx, :), 1);
end

function plot_transfer_heatmap(summaryTable, sensorIds, metricName, figureTitle, outputFile)
    if isempty(summaryTable)
        return;
    end

    labels = upper(sensorIds);
    values = nan(numel(labels), numel(labels));
    for rowIdx = 1:height(summaryTable)
        modelIdx = find(strcmp(labels, summaryTable.Calibration{rowIdx}), 1);
        dataIdx = find(strcmp(labels, summaryTable.ValidationSensor{rowIdx}), 1);
        if ~isempty(modelIdx) && ~isempty(dataIdx)
            values(dataIdx, modelIdx) = summaryTable.(metricName)(rowIdx);
        end
    end

    fig = figure('Name', figureTitle);
    h = heatmap(labels, labels, values);
    h.Title = figureTitle;
    h.XLabel = 'Calibration used';
    h.YLabel = 'Validation sensor';
    h.CellLabelFormat = '%.3f';
    saveas(fig, outputFile);
end
