%% matlab_valid.m
% Sensor Validation Script
% Evaluates: Accuracy, Precision, Sensitivity, Linearity, Resolution
% for the inductive crack-monitoring sensor using the CivilSensorCalibv2
% neural network calibration function.
%
% Data columns: Tx | X | Y | Z | Roll | Pitch | Yaw | L0 | L1 | L2 | L3
%   Inputs  (cols 8:11) : L0, L1, L2, L3  [inductance readings, µH]
%   Outputs (cols 2:4)  : X, Y, Z          [commanded position, mm]
%
% Validation datasets:
%   validation_data_new_0deg.txt   – flat plate (0° tilt)
%   validation_data_new_2-5deg.txt – 2.5° tilt
%   validation_data_new_5deg.txt   – 5° tilt

close all; clear; clc;

%% ── 1. Configuration ─────────────────────────────────────────────────────
datasets = {
    'validation_data_new_0deg.txt',   '0 deg';
    'validation_data_new_2-5deg.txt', '2.5 deg';
    'validation_data_new_5deg.txt',   '5 deg';
};
nDatasets  = size(datasets, 1);
axisNames  = {'X','Y','Z'};

%% ── 2. Evaluate each dataset ─────────────────────────────────────────────
results = struct();

for d = 1:nDatasets
    fname = datasets{d,1};
    label = datasets{d,2};
    fprintf('\n========== Dataset: %s ==========\n', label);

    data  = readmatrix(fname, 'NumHeaderLines', 1);
    Xsens = data(:, 8:11);   % L0–L3 sensor readings  (N×4)
    Ytrue = data(:, 2:4);    % X, Y, Z ground-truth    (N×3)

    % Neural network prediction  (function expects 4×N, returns 3×N)
    Ypred = CivilSensorCalibv2(Xsens')';   % N×3

    err = Ypred - Ytrue;     % signed error (N×3)

    % ── 2a. ACCURACY ──────────────────────────────────────────────────────
    rmse   = sqrt(mean(err.^2, 1));   % 1×3
    mae    = mean(abs(err), 1);       % 1×3
    bias   = mean(err, 1);            % 1×3  systematic offset
    rmse3D = sqrt(mean(sum(err.^2, 2)));

    fprintf('\n  --- Accuracy ---\n');
    for ax = 1:3
        fprintf('    %s : RMSE = %.4f mm | MAE = %.4f mm | Bias = %+.4f mm\n', ...
            axisNames{ax}, rmse(ax), mae(ax), bias(ax));
    end
    fprintf('    3-D Euclidean RMSE = %.4f mm\n', rmse3D);

    % ── 2b. PRECISION (Repeatability) ─────────────────────────────────────
    % Group samples by unique commanded position; compute std of predictions
    [~, ~, posIdx] = unique(round(Ytrue, 4), 'rows');
    nUnique = max(posIdx);
    std_per_pos = zeros(nUnique, 3);
    for k = 1:nUnique
        mask = (posIdx == k);
        if sum(mask) > 1
            std_per_pos(k,:) = std(Ypred(mask,:), 0, 1);
        end
    end
    mean_std = mean(std_per_pos, 1);

    fprintf('\n  --- Precision (mean σ over all repeated positions) ---\n');
    for ax = 1:3
        fprintf('    %s : mean σ = %.4f mm\n', axisNames{ax}, mean_std(ax));
    end

    % ── 2c. SENSITIVITY ───────────────────────────────────────────────────
    % Δ(predicted output) / Δ(true input) along each axis (linear slope)
    fprintf('\n  --- Sensitivity ---\n');
    sensitivity = zeros(1,3);
    for ax = 1:3
        [uTrue, uIdx] = unique(Ytrue(:,ax));
        uPred = Ypred(uIdx, ax);
        if numel(uTrue) > 1
            p = polyfit(uTrue, uPred, 1);
            sensitivity(ax) = p(1);
        else
            sensitivity(ax) = NaN;
        end
        fprintf('    %s : sensitivity = %.4f (output mm / input mm)\n', ...
            axisNames{ax}, sensitivity(ax));
    end

    % ── 2d. LINEARITY ─────────────────────────────────────────────────────
    % Max deviation from best-fit line, as % of full-scale range
    fprintf('\n  --- Linearity ---\n');
    linError_mm  = zeros(1,3);
    linError_pct = zeros(1,3);
    for ax = 1:3
        [uTrue, uIdx] = unique(Ytrue(:,ax));
        uPred = Ypred(uIdx, ax);
        if numel(uTrue) > 1
            p          = polyfit(uTrue, uPred, 1);
            deviation  = abs(uPred - polyval(p, uTrue));
            linError_mm(ax)  = max(deviation);
            linError_pct(ax) = (linError_mm(ax) / range(uTrue)) * 100;
        else
            linError_mm(ax) = NaN;  linError_pct(ax) = NaN;
        end
        fprintf('    %s : max linearity error = %.4f mm  (%.2f %% FS)\n', ...
            axisNames{ax}, linError_mm(ax), linError_pct(ax));
    end

    % ── 2e. RESOLUTION ────────────────────────────────────────────────────
    % 2σ noise floor at the most-sampled commanded position
    posCount   = histcounts(posIdx, 1:nUnique+1);
    [~, bestK] = max(posCount);
    res_std    = std(Ypred(posIdx == bestK, :), 0, 1);

    fprintf('\n  --- Resolution (2σ noise floor at most-sampled position) ---\n');
    for ax = 1:3
        fprintf('    %s : ≈ %.4f mm\n', axisNames{ax}, 2*res_std(ax));
    end

    % ── Store ──────────────────────────────────────────────────────────────
    results(d).label        = label;
    results(d).Ytrue        = Ytrue;
    results(d).Ypred        = Ypred;
    results(d).err          = err;
    results(d).rmse         = rmse;
    results(d).mae          = mae;
    results(d).bias         = bias;
    results(d).rmse3D       = rmse3D;
    results(d).mean_std     = mean_std;
    results(d).sensitivity  = sensitivity;
    results(d).linError_mm  = linError_mm;
    results(d).linError_pct = linError_pct;
    results(d).res_std      = res_std;
end

%% ── 3. Summary table ─────────────────────────────────────────────────────
fprintf('\n\n======= SUMMARY TABLE (all units mm unless stated) =======\n');
hdr = '%-10s | %-8s | %8s %8s %8s\n';
fprintf(hdr, 'Tilt', 'Metric', 'X', 'Y', 'Z');
fprintf('%s\n', repmat('-',1,52));
fmt = '%-10s | %-8s | %8.4f %8.4f %8.4f\n';
for d = 1:nDatasets
    r = results(d);
    fprintf(fmt, r.label, 'RMSE',    r.rmse(1),        r.rmse(2),        r.rmse(3));
    fprintf(fmt, '',      'MAE',     r.mae(1),         r.mae(2),         r.mae(3));
    fprintf(fmt, '',      'Bias',    r.bias(1),        r.bias(2),        r.bias(3));
    fprintf(fmt, '',      'Prec σ',  r.mean_std(1),    r.mean_std(2),    r.mean_std(3));
    fprintf(fmt, '',      'Sens',    r.sensitivity(1), r.sensitivity(2), r.sensitivity(3));
    fprintf(fmt, '',      'Lin %%FS', r.linError_pct(1),r.linError_pct(2),r.linError_pct(3));
    fprintf(fmt, '',      'Res 2σ',  2*r.res_std(1),   2*r.res_std(2),   2*r.res_std(3));
    fprintf('%s\n', repmat('-',1,52));
end

%% ── 4. Figures ───────────────────────────────────────────────────────────

% Fig 1 – Error distribution (box plots)
figure('Name','Error Distributions');
for ax = 1:3
    subplot(1,3,ax);
    errData = [];  grp = {};
    for d = 1:nDatasets
        errData = [errData; results(d).err(:,ax)];                          %#ok<AGROW>
        grp     = [grp; repmat(datasets(d,2), size(results(d).err,1), 1)];  %#ok<AGROW>
    end
    boxplot(errData, grp);
    yline(0,'r--','LineWidth',1.2);
    xlabel('Tilt Angle');  ylabel('Error (mm)');
    title([axisNames{ax} ' Error']); grid on;
end
sgtitle('Prediction Error Distribution by Tilt Angle');

% Fig 2 – 3-D Euclidean error map over workspace
figure('Name','3-D Accuracy Map');
globalMax = max(arrayfun(@(r) max(vecnorm(r.err,2,2)), results));
for d = 1:nDatasets
    subplot(1,nDatasets,d);
    e3D = vecnorm(results(d).err, 2, 2);
    scatter3(results(d).Ytrue(:,1), results(d).Ytrue(:,2), ...
             results(d).Ytrue(:,3), 30, e3D, 'filled');
    colorbar; clim([0, globalMax]);
    xlabel('X (mm)'); ylabel('Y (mm)'); zlabel('Z (mm)');
    title(sprintf('Tilt %s', datasets{d,2})); grid on; view(45,30);
end
sgtitle('Euclidean Error Over Workspace (mm)');

% Fig 3 – Linearity: predicted vs true (0° dataset)
figure('Name','Linearity');
d_lin = 1;
for ax = 1:3
    subplot(1,3,ax);
    [uTrue, uIdx] = unique(results(d_lin).Ytrue(:,ax));
    uPred = results(d_lin).Ypred(uIdx, ax);
    p = polyfit(uTrue, uPred, 1);
    plot(uTrue, uPred,         'b.', 'MarkerSize',6, 'DisplayName','NN output'); hold on;
    plot(uTrue, polyval(p,uTrue), 'r-', 'LineWidth',2, ...
        'DisplayName', sprintf('Best-fit (k=%.3f)',p(1)));
    plot(uTrue, uTrue,         'k--','LineWidth',1,  'DisplayName','Ideal (k=1)');
    hold off;
    xlabel(['True ' axisNames{ax} ' (mm)']);
    ylabel(['Predicted ' axisNames{ax} ' (mm)']);
    title([axisNames{ax} ' Linearity (0°)']);
    legend('Location','northwest'); grid on;
end
sgtitle('Linearity: Predicted vs True Position (0° dataset)');

% Fig 4 – Precision: mean std per axis per tilt
figure('Name','Precision');
precMatrix = vertcat(results.mean_std);   % nDatasets × 3
bar(precMatrix);
set(gca,'XTickLabel',{datasets{:,2}});
legend({'X','Y','Z'},'Location','best');
xlabel('Tilt Angle'); ylabel('Mean σ (mm)');
title('Precision (Mean Std-Dev of Repeated Predictions)'); grid on;

% Fig 5 – Bias per axis across tilt angles
figure('Name','Systematic Bias');
biasMatrix = vertcat(results.bias);   % nDatasets × 3
bar(biasMatrix);
set(gca,'XTickLabel',{datasets{:,2}});
legend({'X','Y','Z'},'Location','best');
xlabel('Tilt Angle'); ylabel('Bias (mm)');
title('Systematic Bias per Axis vs Tilt Angle'); grid on; yline(0,'k--');

% Fig 6 – RMSE summary across tilt angles
figure('Name','RMSE Summary');
rmseMatrix = vertcat(results.rmse);   % nDatasets × 3
bar(rmseMatrix);
set(gca,'XTickLabel',{datasets{:,2}});
legend({'X','Y','Z'},'Location','best');
xlabel('Tilt Angle'); ylabel('RMSE (mm)');
title('RMSE per Axis vs Tilt Angle'); grid on;
