# SITS XYZ Library

## Overview
The SITS XYZ Library provides an interface for the SITS 4 coil sensor (FS1010A) using the Teensy microcontroller. This library allows users to easily configure the sensor, read data from its channels, and calculate inductance values.

## Installation
To install the SITS XYZ Library, follow these steps:
1. Download the library from the repository.
2. Extract the contents to your Arduino libraries folder (usually located in `Documents/Arduino/libraries`).
3. Restart the Arduino IDE to recognize the new library.

## Usage
To use the SITS XYZ Library in your Arduino project, include the header file and create an instance of the `SITS_XYZ` class. Here is a basic example:

```cpp
#include <SITS_XYZ.h>

SITS_XYZ sensor;

void setup() {
    Serial.begin(115200);
    sensor.begin();
    sensor.configure();
}

void loop() {
    float inductance0 = sensor.getInductance(0);
    Serial.print("Inductance Channel 0: ");
    Serial.println(inductance0);
    delay(1000);
}
```

## API Reference

### SITS_XYZ Class
- **`SITS_XYZ()`**: Constructor for the SITS_XYZ class.
- **`void begin()`**: Initializes the I2C communication and prepares the sensor for operation.
- **`void configure()`**: Configures the sensor registers for optimal performance.
- **`unsigned long readChannel(int channel)`**: Reads the raw data from the specified channel.
- **`float getInductance(int channel)`**: Calculates and returns the inductance value for the specified channel.

## Example
An example sketch demonstrating basic usage of the library can be found in the `examples/BasicUsage` directory. This sketch shows how to initialize the library, configure the sensor, and read inductance values continuously.

## License
This library is released under the MIT License. See the LICENSE file for more details.