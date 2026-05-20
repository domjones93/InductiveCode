#ifndef PACKET_ENCODER_H
#define PACKET_ENCODER_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

static const uint8_t PACKET_DELIMITER[3] = {0xFF, 0xFE, 0xFD};
static const size_t SENSOR_PACKET_BYTES = 18;
static const size_t PACKET_FIXED_BYTES = 8;

struct SensorPacketData {
    uint16_t status = 0;
    uint32_t raw[4] = {0, 0, 0, 0};
};

constexpr size_t packetBinaryLength(uint8_t sensor_count) {
    return PACKET_FIXED_BYTES + (SENSOR_PACKET_BYTES * sensor_count);
}

constexpr size_t packetHexLength(uint8_t sensor_count) {
    return packetBinaryLength(sensor_count) * 2;
}

inline void appendHexByte(char *out, size_t &offset, uint8_t value) {
    snprintf(out + offset, 3, "%02X", value);
    offset += 2;
}

inline bool encodeMultiSensorPacket(
    char *out,
    size_t out_len,
    uint8_t sensor_count,
    uint32_t timestamp_us,
    const SensorPacketData *sensors
) {
    const size_t hex_len = packetHexLength(sensor_count);
    if (out_len < hex_len + 1 || sensors == nullptr) {
        return false;
    }

    size_t offset = 0;
    appendHexByte(out, offset, sensor_count);

    appendHexByte(out, offset, (timestamp_us >> 24) & 0xFF);
    appendHexByte(out, offset, (timestamp_us >> 16) & 0xFF);
    appendHexByte(out, offset, (timestamp_us >> 8) & 0xFF);
    appendHexByte(out, offset, timestamp_us & 0xFF);

    for (uint8_t sensor = 0; sensor < sensor_count; sensor++) {
        appendHexByte(out, offset, (sensors[sensor].status >> 8) & 0xFF);
        appendHexByte(out, offset, sensors[sensor].status & 0xFF);

        for (uint8_t channel = 0; channel < 4; channel++) {
            const uint32_t raw = sensors[sensor].raw[channel];
            appendHexByte(out, offset, (raw >> 24) & 0xFF);
            appendHexByte(out, offset, (raw >> 16) & 0xFF);
            appendHexByte(out, offset, (raw >> 8) & 0xFF);
            appendHexByte(out, offset, raw & 0xFF);
        }
    }

    appendHexByte(out, offset, PACKET_DELIMITER[0]);
    appendHexByte(out, offset, PACKET_DELIMITER[1]);
    appendHexByte(out, offset, PACKET_DELIMITER[2]);

    out[offset] = '\0';
    return true;
}

#endif
