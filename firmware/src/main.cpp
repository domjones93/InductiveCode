#include <Arduino.h>
#include <Wire.h>
#include <LDC1614.h>
#include "PacketEncoder.h"

static const uint32_t SERIAL_BAUD = 115200;
static const uint32_t I2C_CLOCK_HZ = 400000;
static const uint8_t LDC1614_ADDRESS = 0x2A;
static const uint8_t BUS_COUNT = 2;
static const uint8_t MAX_SENSOR_COUNT = 3;
static const uint16_t SAMPLE_DELAY_MS = 66;

static const float OSC_FREQ_MHZ = 40.0;
static const float SENSOR_CAPACITANCE_PF = 220.0;

struct BusSlot {
    TwoWire *bus;
    uint8_t sda_pin;
    uint8_t scl_pin;
    LDC1614 sensor;
};

struct ActiveSensorConfig {
    uint8_t bus_index;
    uint8_t address;
};

static BusSlot bus_slots[BUS_COUNT] = {
    {&Wire, 0, 1, LDC1614(Wire, I2C_CLOCK_HZ, LDC1614_ADDRESS)},    // I2C0: GP0 SDA, GP1 SCL
    {&Wire1, 2, 3, LDC1614(Wire1, I2C_CLOCK_HZ, LDC1614_ADDRESS)},  // I2C1: GP2 SDA, GP3 SCL
};

static ActiveSensorConfig active_sensors[MAX_SENSOR_COUNT] = {
    {0, LDC1614_ADDRESS},
    {1, LDC1614_ADDRESS},
    {1, 0x2B},
};
static uint8_t active_sensor_count = 3;

static SensorPacketData packet_data[MAX_SENSOR_COUNT];
static char packet_hex[packetHexLength(MAX_SENSOR_COUNT) + 1];
static bool sensors_configured = false;

static void configureSensor(LDC1614 &sensor) {
    RCount rcount;
    rcount.RCOUNT_CH0 = 0x24FF;

    Offset offset;
    offset.OFFSET_CH0 = 0;

    SettleCount settlecount;
    settlecount.SETTLECOUNT_CH0 = 0x00FF;

    ClockDividers clock_dividers;
    clock_dividers.FIN_DIVIDERS_CH0 = 0x01;
    clock_dividers.FREF_DIVIDERS_CH0 = 0x0001;

    Config config;
    config.ACTIVE_CHAN = 0x0000;
    config.SLEEP_MODE_EN = 0x0000;
    config.RP_OVERRIDE_EN = 0x0001;
    config.SENSOR_ACTIVATE_SEL = 0x0000;
    config.AUTO_AMP_DIS = 0x0001;
    config.REF_CLK_SRC = 0x0001;
    config.INTB_DIS = 0x0000;
    config.HIGH_CURRENT_DRV = 0x0000;

    MuxConfig mux_config;
    mux_config.AUTOSCAN_EN = 0b1;
    mux_config.RR_SEQUENCE = 0b10;
    mux_config.DEGLITCH = 0b101;

    DriveCurrent drive_current;
    drive_current.IDRIVE_CH0 = 0x18;

    sensor.configure_properties(OSC_FREQ_MHZ, SENSOR_CAPACITANCE_PF);
    sensor.configure_rcount(rcount);
    sensor.configure_offset(offset);
    sensor.configure_settlecount(settlecount);
    sensor.configure_mux_config(mux_config);
    sensor.configure_clock_dividers(clock_dividers);
    sensor.configure_drive_current(drive_current);
    sensor.configure_config(config);
}

static void beginBuses() {
    for (uint8_t bus = 0; bus < BUS_COUNT; bus++) {
        bus_slots[bus].sensor.begin(bus_slots[bus].sda_pin, bus_slots[bus].scl_pin);
    }
}

static void initSensors() {
    beginBuses();
    for (uint8_t i = 0; i < active_sensor_count; i++) {
        const ActiveSensorConfig &config = active_sensors[i];
        LDC1614 &sensor = bus_slots[config.bus_index].sensor;
        sensor.setAddress(config.address);
        configureSensor(sensor);
    }

    sensors_configured = true;
    delay(100);
}

static int hexDigit(char value) {
    if (value >= '0' && value <= '9') {
        return value - '0';
    }
    if (value >= 'A' && value <= 'F') {
        return 10 + value - 'A';
    }
    if (value >= 'a' && value <= 'f') {
        return 10 + value - 'a';
    }
    return -1;
}

static bool parseHexByte(const String &payload, size_t offset, uint8_t &value) {
    if (offset + 1 >= payload.length()) {
        return false;
    }

    const int high = hexDigit(payload[offset]);
    const int low = hexDigit(payload[offset + 1]);
    if (high < 0 || low < 0) {
        return false;
    }

    value = (high << 4) | low;
    return true;
}

static bool parseConfigPayload(const String &payload, ActiveSensorConfig *requested, uint8_t &requested_count) {
    if (!parseHexByte(payload, 0, requested_count)) {
        return false;
    }
    if (requested_count < 1 || requested_count > MAX_SENSOR_COUNT) {
        return false;
    }
    if (payload.length() != 2 + (requested_count * 4)) {
        return false;
    }

    size_t offset = 2;
    for (uint8_t i = 0; i < requested_count; i++) {
        uint8_t bus_index = 0;
        uint8_t address = 0;
        if (!parseHexByte(payload, offset, bus_index) ||
            !parseHexByte(payload, offset + 2, address)) {
            return false;
        }
        if (bus_index >= BUS_COUNT || address > 0x7F) {
            return false;
        }

        requested[i] = {bus_index, address};
        offset += 4;
    }
    return true;
}

static void handleConfigCommand() {
    const String payload = Serial.readStringUntil('\n');
    ActiveSensorConfig requested[MAX_SENSOR_COUNT];
    uint8_t requested_count = 0;

    if (!parseConfigPayload(payload, requested, requested_count)) {
        Serial.println("CONFIG ERR");
        return;
    }

    active_sensor_count = requested_count;
    for (uint8_t i = 0; i < active_sensor_count; i++) {
        active_sensors[i] = requested[i];
    }

    initSensors();

    Serial.print("CONFIG OK ");
    Serial.print(active_sensor_count);
    for (uint8_t i = 0; i < active_sensor_count; i++) {
        Serial.print(" ");
        Serial.print(active_sensors[i].bus_index);
        Serial.print(":0x");
        if (active_sensors[i].address < 0x10) {
            Serial.print("0");
        }
        Serial.print(active_sensors[i].address, HEX);
    }
    Serial.println();
    Serial.flush();
}

static void readAndWritePacket() {
    if (!sensors_configured) {
        initSensors();
    }

    const uint32_t timestamp_us = micros();

    for (uint8_t i = 0; i < active_sensor_count; i++) {
        const ActiveSensorConfig &config = active_sensors[i];
        RawData raw_data;
        LDC1614 &sensor = bus_slots[config.bus_index].sensor;
        sensor.setAddress(config.address);
        const bool read_ok = sensor.rawReadAllChannels(packet_data[i].status, raw_data);
        if (!read_ok) {
            packet_data[i].status |= 0x8000;
        }

        for (uint8_t channel = 0; channel < 4; channel++) {
            packet_data[i].raw[channel] = raw_data.raw_data[channel];
        }
    }

    if (encodeMultiSensorPacket(
            packet_hex,
            sizeof(packet_hex),
            active_sensor_count,
            timestamp_us,
            packet_data)) {
        Serial.write(packet_hex, packetHexLength(active_sensor_count));
    }
}

void setup() {
    Serial.begin(SERIAL_BAUD);
    beginBuses();
}

void loop() {
    if (!Serial.available()) {
        return;
    }

    const char command = Serial.read();

    switch (command) {
        case 'Q':
            Serial.print("Device Ready");
            break;

        case 'i':
            initSensors();
            Serial.println("Sensor initialized.");
            break;

        case 'C':
            handleConfigCommand();
            break;

        case 's':
            readAndWritePacket();
            break;

        case 'c':
            while (true) {
                if (Serial.available() && Serial.read() == 'x') {
                    break;
                }

                readAndWritePacket();
                delay(SAMPLE_DELAY_MS);
            }
            break;

        default:
            break;
    }
}
