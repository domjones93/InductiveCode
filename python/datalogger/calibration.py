import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import numpy as np

import pandas as pd

# Load your data (replace with your actual data loading logic)
filename = "./datalogger/calibration/calibration_data_1mms.txt"

data = pd.read_csv(filename, delimiter=",", header=0)

# Extract inductance values and positions
inductance_values = data[['L0', 'L1', 'L2', 'L3']].values
positions = data[['Tx', 'Ty', 'Tz']].values

# Split the data into training and testing sets
X_train, X_test, y_train, y_test = train_test_split(inductance_values, positions, test_size=0.2, random_state=42)

# Standardize the data
scaler_X = StandardScaler()
scaler_y = StandardScaler()

X_train = scaler_X.fit_transform(X_train)
X_test = scaler_X.transform(X_test)

y_train = scaler_y.fit_transform(y_train)
y_test = scaler_y.transform(y_test)

# Convert data to PyTorch tensors
X_train = torch.tensor(X_train, dtype=torch.float32)
X_test = torch.tensor(X_test, dtype=torch.float32)
y_train = torch.tensor(y_train, dtype=torch.float32)
y_test = torch.tensor(y_test, dtype=torch.float32)

# Define the feed-forward neural network
class FeedForwardNN(nn.Module):
    def __init__(self, input_size, output_size):
        super(FeedForwardNN, self).__init__()
        self.fc1 = nn.Linear(input_size, 64)
        self.fc2 = nn.Linear(64, 64)
        self.fc3 = nn.Linear(64, 64)  # Second hidden layer
        self.fc4 = nn.Linear(64, output_size)  # Output layer
        self.relu = nn.ReLU()

    def forward(self, x):
        x = self.relu(self.fc1(x))
        x = self.relu(self.fc2(x))
        x = self.relu(self.fc3(x))  # Activation for second hidden layer
        x = self.fc4(x)
        return x

# Initialize the model, loss function, and optimizer
input_size = X_train.shape[1]
output_size = y_train.shape[1]
model = FeedForwardNN(input_size, output_size)
criterion = nn.MSELoss()
optimizer = optim.Adam(model.parameters(), lr=0.001)

# Train the model
epochs = 5000
batch_size = 32
for epoch in range(epochs):
    model.train()
    permutation = torch.randperm(X_train.size(0))
    for i in range(0, X_train.size(0), batch_size):
        indices = permutation[i:i + batch_size]
        batch_X, batch_y = X_train[indices], y_train[indices]

        optimizer.zero_grad()
        outputs = model(batch_X)
        loss = criterion(outputs, batch_y)
        loss.backward()
        optimizer.step()

    # Print loss for every epoch
    if (epoch + 1) % 10 == 0:
        print(f"Epoch {epoch + 1}/{epochs}, Loss: {loss.item()}")

# Evaluate the model
model.eval()
with torch.no_grad():
    y_pred = model(X_test)
    test_loss = criterion(y_pred, y_test)
    print(f"Test Loss: {test_loss.item()}")

    # Example prediction
    # filename = "calibration_data1.txt"
    inductance_valid = pd.read_csv(filename, delimiter=",", header=0)[['L0', 'L1', 'L2', 'L3']].values
    inductance_valid = scaler_X.transform(inductance_valid)

    positions_valid = pd.read_csv(filename, delimiter=",", header=0)[['Tx', 'Ty', 'Tz']].values

    inductance_valid_tensor = torch.tensor(inductance_valid, dtype=torch.float32)
    predicted_positions = model(inductance_valid_tensor).numpy()
    predicted_positions = scaler_y.inverse_transform(predicted_positions)
    
    position_error = np.mean(np.abs(predicted_positions - positions_valid), axis=0)
    print(f"Position Error: {position_error}")


## save model
    model_path = "./calibration_model.pth"
    torch.save(model.state_dict(), model_path)


