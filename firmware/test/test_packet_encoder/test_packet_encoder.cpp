#include <Arduino.h>
#include <string.h>
#include <unity.h>
#include "PacketEncoder.h"

static void test_two_sensor_packet_shape_and_contents() {
    SensorPacketData sensors[2];
    sensors[0].status = 0x1234;
    sensors[0].raw[0] = 0x01020304;
    sensors[0].raw[1] = 0x11121314;
    sensors[0].raw[2] = 0x21222324;
    sensors[0].raw[3] = 0x31323334;
    sensors[1].status = 0xABCD;
    sensors[1].raw[0] = 0x41424344;
    sensors[1].raw[1] = 0x51525354;
    sensors[1].raw[2] = 0x61626364;
    sensors[1].raw[3] = 0x71727374;

    char packet[packetHexLength(2) + 1];
    TEST_ASSERT_TRUE(encodeMultiSensorPacket(packet, sizeof(packet), 2, 0xA1B2C3D4, sensors));

    TEST_ASSERT_EQUAL_UINT32(88, strlen(packet));
    TEST_ASSERT_EQUAL_MEMORY("02", packet, 2);
    TEST_ASSERT_EQUAL_MEMORY("FFFEFD", packet + 82, 6);
    TEST_ASSERT_EQUAL_STRING(
        "02A1B2C3D4123401020304111213142122232431323334ABCD41424344515253546162636471727374FFFEFD",
        packet);
}

void setup() {
    delay(2000);
    UNITY_BEGIN();
    RUN_TEST(test_two_sensor_packet_shape_and_contents);
    UNITY_END();
}

void loop() {
}
