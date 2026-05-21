% Train one calibration network per sensor from individual calibration CSV files.
close all
clear
clc

scriptDir = fileparts(mfilename('fullpath'));

% ---------------- User configuration ----------------
calibrationDataDir = fullfile(fileparts(scriptDir), '../python/v2_sensor');
outputDir = fullfile(fileparts(scriptDir), 'calibrations');
sensorIds = {'s1', 's2', 's3', 's4', 's5', 's6'};
filePatternTemplate = 'calibration_%s_*.csv';
targetColumns = {'Tx', 'Ty', 'Tz'};
inputColumns = {'L0', 'L1', 'L2', 'L3'};
hiddenLayerSize = [10,10,10];
trainFcn = 'trainlm';
useGPU = 'no';
% ----------------------------------------------------

if ~isfolder(calibrationDataDir)
    error('Calibration data folder not found: %s', calibrationDataDir);
end
if ~isfolder(outputDir)
    mkdir(outputDir);
end

for sensorIdx = 1:numel(sensorIds)
    sensorId = sensorIds{sensorIdx};
    dataFiles = dir(fullfile(calibrationDataDir, sprintf(filePatternTemplate, sensorId)));
    if isempty(dataFiles)
        warning('Skipping %s. No files matched %s', sensorId, fullfile(calibrationDataDir, sprintf(filePatternTemplate, sensorId)));
        continue;
    end

    inputs = [];
    targets = [];
    sourceFiles = strings(1, numel(dataFiles));
    for fileIdx = 1:numel(dataFiles)
        sourceFile = fullfile(dataFiles(fileIdx).folder, dataFiles(fileIdx).name);
        sourceFiles(fileIdx) = string(sourceFile);
        data = readtable(sourceFile);
        [fileInputs, fileTargets] = extract_calibration_columns(data, inputColumns, targetColumns, sensorId);
        inputs = [inputs; fileInputs]; %#ok<AGROW>
        targets = [targets; fileTargets]; %#ok<AGROW>
    end

    validRows = all(isfinite(inputs), 2) & all(isfinite(targets), 2);
    if nnz(validRows) < 10
        warning('Skipping %s. Only %d valid calibration rows.', sensorId, nnz(validRows));
        continue;
    end

    x = inputs(validRows, :).';
    t = targets(validRows, :).';

    net = fitnet(hiddenLayerSize, trainFcn);
    net.input.processFcns = {'removeconstantrows', 'mapminmax'};
    net.output.processFcns = {'removeconstantrows', 'mapminmax'};
    net.divideFcn = 'dividerand';
    net.divideMode = 'sample';
    net.divideParam.trainRatio = 70/100;
    net.divideParam.valRatio = 15/100;
    net.divideParam.testRatio = 15/100;
    net.performFcn = 'mse';
    net.plotFcns = {'plotperform', 'plottrainstate', 'ploterrhist', 'plotregression', 'plotfit'};
    net.trainParam.epochs = 250E3;
    net.trainParam.goal = 0;
    net.trainParam.max_fail = 100;

    fprintf('Training %s with %d rows from %d files...\n', upper(sensorId), nnz(validRows), numel(dataFiles));
    [net, tr] = train(net, x, t, 'useGPU', useGPU, 'showResources', 'yes'); %#ok<ASGLU>

    y = net(x);
    performance = perform(net, t, y); %#ok<NOPTS>
    errorValues = y.' - targets(validRows, :);

    modelFile = fullfile(outputDir, sprintf('%s_net.mat', upper(sensorId)));
    save(modelFile, 'net', 'sensorId', 'inputColumns', 'targetColumns', 'sourceFiles', 'performance', 'errorValues');
    fprintf('Saved %s calibration to %s\n', upper(sensorId), modelFile);

    figure('Name', sprintf('%s calibration fit', upper(sensorId)));
    for axisIdx = 1:3
        subplot(1, 3, axisIdx);
        plot(y(axisIdx, :).');
        hold on;
        plot(t(axisIdx, :).');
        hold off;
        title(sprintf('%s axis %d', upper(sensorId), axisIdx));
    end
end

function [inputs, targets] = extract_calibration_columns(data, inputColumns, targetColumns, sensorId)
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
