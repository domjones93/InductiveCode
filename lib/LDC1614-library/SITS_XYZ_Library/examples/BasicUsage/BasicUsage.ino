#include <Wire.h>
#include <LDC1614.h>

LDC1614 sensor;

void setup() {
    Serial.begin(115200);
    sensor.begin();
    sensor.configure();
    Serial.println("SITS XYZ Sensor Initialized and Configured.");
}

void loop() {
    float inductance[4];

    for (int i = 0; i < 4; i++) {
        inductance[i] = sensor.getInductance(i);
        Serial.print("Channel ");
        Serial.print(i);
        Serial.print(": Inductance = ");
        Serial.print(inductance[i]);
        Serial.println(" µH");
    }

    delay(1000); // Delay for readability
}