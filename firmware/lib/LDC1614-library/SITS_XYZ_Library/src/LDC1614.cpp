#include "LDC1614.h"
#include <Arduino.h>
#include <Wire.h>
#include <math.h>

LDC1614::LDC1614 (TwoWire &iface, uint32_t clock, int address) {
    i2c = &iface;
    i2c_clock = clock;
    LDC_ADDRESS = address;
}

void LDC1614::begin() {
    i2c->begin(); // Start I2C peripheral as a master.
    i2c->setClock(i2c_clock); // Set clock to fast I2C 400kHz.
    i2c->setTimeout(20);
}

void LDC1614::begin(int sda_pin, int scl_pin) {
    pin_SDA = sda_pin;
    pin_SCL = scl_pin;

#if defined(ARDUINO_ARCH_RP2040) || defined(ARDUINO_ARCH_RP2350)
    i2c->setSDA((pin_size_t)pin_SDA);
    i2c->setSCL((pin_size_t)pin_SCL);
    begin();
#elif defined(ARDUINO_ARCH_ESP32)
    i2c->begin(pin_SDA, pin_SCL);
    i2c->setClock(i2c_clock);
#else
    begin();
#endif
}

void LDC1614::connect() {
    begin();
}

void LDC1614::configure_properties(float f_ref_in, float capacitance_in) {
    f_ref = f_ref_in;
    capacitance = capacitance_in;
    // sensor.freq_const = sensor.f_ref / SENSOR_RESOLUTION;
}

void LDC1614::configure_rcount(RCount rcount) {
    for (int i = 0; i < 4; i++) {
        writeReg(REG_ADDR_RCOUNT + i, rcount.RCOUNT_CH0);  //TODO: Modify to work properly with varaible number of sensors
        }
    logConfig("RCOUNT: 0x" + String(rcount.RCOUNT_CH0, HEX));
}

void LDC1614::configure_offset(Offset offset) {
    for (int i = 0; i < 4; i++) {
        writeReg(REG_ADDR_OFFSET + i, offset.OFFSET_CH0);  //TODO: Modify to work properly with varaible number of sensors
    }
    logConfig("OFFSET: 0x" + String(offset.OFFSET_CH0, HEX));
}

void LDC1614::configure_settlecount(SettleCount settlecount) {
    writeReg(REG_ADDR_SETTLECOUNT, settlecount.SETTLECOUNT_CH0); //TODO: Modify to work properly with varaible number of sensors
    logConfig("SETTLECOUNT: 0x" + String(settlecount.SETTLECOUNT_CH0, HEX));
    for(int i=0; i<4; i++){
        writeReg(REG_ADDR_SETTLECOUNT + i, settlecount.SETTLECOUNT_CH0); //TODO: Modify to work properly with varaible number of sensors
    }
}

void LDC1614::configure_clock_dividers(ClockDividers clock_dividers) {
    uint16_t reg_value;
    for (int i = 0; i < 4; i++) {
        reg_value = (clock_dividers.FIN_DIVIDERS_CH0 << 12) | 
                    (clock_dividers.FREF_DIVIDERS_CH0);
        writeReg(REG_ADDR_CLOCK_DIVIDERS + i, reg_value); //TODO: Modify to work properly with varaible number of sensors
    }
    // reg_value = (clock_dividers.FIN_DIVIDERS_CH0 << 12) | 
    //             (clock_dividers.FREF_DIVIDERS_CH0);
    // writeReg(REG_ADDR_CLOCK_DIVIDERS, reg_value); //TODO: Modify to work properly with varaible number of sensors
    logConfig("CLOCK_DIVIDERS: 0x" + String(reg_value, HEX));
}

void LDC1614::configure_config(Config config) {
    uint16_t config_val =   (config.ACTIVE_CHAN << 14) | 
                            (config.SLEEP_MODE_EN << 13) | 
                            (config.RP_OVERRIDE_EN << 12) | 
                            (config.SENSOR_ACTIVATE_SEL << 11) | 
                            (config.AUTO_AMP_DIS << 10) | 
                            (config.REF_CLK_SRC << 9) | 
                            (config.INTB_DIS << 7) | 
                            (config.HIGH_CURRENT_DRV << 6); 

    writeReg(REG_ADDR_CONFIG, config_val);
    logConfig("CONFIG: 0x" + String(config_val, HEX));
}

void LDC1614::configure_mux_config(MuxConfig mux_config) {
    uint16_t mux_config_val =   (mux_config.AUTOSCAN_EN << 15) | 
                                (mux_config.RR_SEQUENCE << 13) | 
                                (mux_config.MUX_RESERVED << 3) | 
                                (mux_config.DEGLITCH << 0);

    writeReg(REG_ADDR_MUX_CONFIG, mux_config_val);
    logConfig("MUX_CONFIG: 0x" + String(mux_config_val, HEX));
}

void LDC1614::configure_drive_current(DriveCurrent drive_current) {
    for (int i = 0; i < 4; i++) {
        uint16_t drive_current_val = (drive_current.IDRIVE_CH0 << 11) | 
                                     (drive_current.INIT_IDRIVE_CH0 << 6);

        writeReg(REG_ADDR_DRIVE_CURRENT + i, drive_current_val);
        logConfig("DRIVE_CURRENT: 0x" + String(drive_current_val, HEX));
    }
    
}

bool LDC1614::readAllChannels(InductanceData &inductance_data) {
    uint16_t data_LSB = 0;
    uint16_t data_MSB = 0;
    uint32_t data_full = 0;
    uint16_t status = 0;
    bool ok = readValue(0x18, status); // Read the status register
    // Serial.println("Status: 0x" + String(status, HEX));
    
    for (int i = 0; i < 4; i++) {
        ok = readValue(channelMSB[i], data_MSB) && ok;
        ok = readValue(channelLSB[i], data_LSB) && ok;
        data_full = ( (data_MSB & 0x0FFF) << 16) | data_LSB;
        getInductance(data_full, inductance_data.inductance[i]);
        //Serial.println("Inductance (bin): " + String(inductance_data.inductance[i]));
    }
    //Serial.println("Inductance (bin): " + String(data_full,HEX));
    return ok;
}

bool LDC1614::rawReadAllChannels(uint16_t &status, RawData &raw_data) {
    uint16_t data_LSB = 0;
    uint16_t data_MSB = 0;

    status = 0;
    bool ok = readValue(0x18, status); // Read the status register
    // Serial.println("Status: 0x" + String(status, HEX));
    
    for (int i = 0; i < 4; i++) {
        ok = readValue(channelMSB[i], data_MSB) && ok;
        ok = readValue(channelLSB[i], data_LSB) && ok;
        raw_data.raw_data[i] = ( (data_MSB & 0x0FFF) << 16) | data_LSB;
        //Serial.println("Inductance (bin): " + String(inductance_data.inductance[i]));
    }
    //Serial.println("Inductance (bin): " + String(data_full,HEX));
    if (!ok) {
        status |= 0x8000;
    }
    return ok;
}

inline void LDC1614::getInductance(uint32_t& raw_data,  float& inductance) {
    // Calculate oscillating frequency from raw value.
    // Note: Adjust the formula as needed based on your application.
    // freq_calc = (f_ref) * (raw_data / sensor_resolution); freq_const = f_ref/sensor_resolution
    float frequency = FREQUENCY_CONST * (float)raw_data;
    // Calculate inductance L in microHenries: L = (1/(2*pi*f))^2 / 330 * 1e6 (rearranged to 1e6*{invers of 4pisq} / (capacitance * frequency))
    inductance = INDUCTANCE_CONST / (capacitance * frequency * frequency);
}

bool LDC1614::readValue(uint8_t reg, uint16_t &data) {
    uint8_t num_bytes = 2;
    data = 0;

    i2c->beginTransmission(LDC_ADDRESS);
    i2c->write(reg);
    if (i2c->endTransmission(false) != 0) {
        data = 0xFFFF;
        return false;
    }

    const uint8_t received = i2c->requestFrom(LDC_ADDRESS, num_bytes);
    if (received != num_bytes || i2c->available() < num_bytes) {
        data = 0xFFFF;
        while (i2c->available()) {
            i2c->read();
        }
        return false;
    }

    uint8_t a = i2c->read();
    uint8_t b = i2c->read();
    data =  (a << 8) | b;
    return true;
}

bool LDC1614::writeReg(uint8_t regAddr, uint16_t regValue) {
    i2c->beginTransmission(LDC_ADDRESS);
    i2c->write(regAddr);
    i2c->write(highByte(regValue));
    i2c->write(lowByte(regValue));
    return i2c->endTransmission() == 0;
}

void LDC1614::setAddress(int address) {
    LDC_ADDRESS = address;
}

void LDC1614::logConfig(const String &message) {
#ifdef LDC1614_DEBUG_CONFIG
    Serial.println(message);
#else
    (void)message;
#endif
}
