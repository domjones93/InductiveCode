#ifndef LDC1614_H
#define LDC1614_H

#include <Arduino.h>
#include <Wire.h>

#define INDUCTANCE_CONST 025330.3387 // (1/(4*3.14159*3.14159));
#define SENSOR_RESOLUTION 0xFFFFFFF //28-bit
#define FREQUENCY_CONST 40./SENSOR_RESOLUTION // (f_ref/sensor_resolution)

enum class REGISTERS {
    RESET = 0x1C,
    RCOUNT = 0x08,
    OFFSET = 0x0D,
    SETTLECOUNT = 0x10,
    CLOCK_DIVIDERS = 0x14,
    STATUS = 0x18,
    CONFIG = 0x1A,
    MUX_CONFIG = 0x1B,
    DRIVE_CURRENT = 0x1E
};
   
struct InductanceData {
    float inductance[4];
};

struct RCount{                              // LDC1614 Datasheet Table 9. Address 0x08, RCOUNT0 Field Descriptions; Register 0x08->0x0B
    uint16_t RCOUNT_CH0 = 0x0080;           
    uint16_t RCOUNT_CH1 = 0x0080;           //Conversion time = (RCOUNT * 16) / fREF
    uint16_t RCOUNT_CH2 = 0x0080;       
    uint16_t RCOUNT_CH3 = 0x0080;
};

struct Offset{                              // LDC1614 Datasheet Table 14. Address 0x0D, OFFSET1 Field Descriptions; Register 0x0D->0x0F
    unsigned long OFFSET_CH0 = 0;
    unsigned long OFFSET_CH1 = 0;           // Offset frequency = ( OFFSET / (2^16) ) / fREF
    unsigned long OFFSET_CH2 = 0;
    unsigned long OFFSET_CH3 = 0;
};

struct SettleCount{                         // LDC1614 Datasheet Table 17. Address 0x10, SETTLECOUNT0 Field Description
    uint16_t SETTLECOUNT_CH0 = 0x0014;
    uint16_t SETTLECOUNT_CH1 = 0x0014;      // If SETTLECOUNT = 0x0000 or 0x0001,: Settling time = 32 / fREF
    uint16_t SETTLECOUNT_CH2 = 0x0014;      // Otherwise: Settling time = (SETTLECOUNT * 16) / fREF
    uint16_t SETTLECOUNT_CH3 = 0x0014;
};

struct ClockDividers{                      // LDC1614 Datasheet able 21. Address 0x14, CLOCK_DIVIDERS0 Field Descriptions
                                            // Bit 15:12 FIN_DIVIDER: Must be set to ≥2 if the Sensor frequency is ≥ 8.75MHz; FIN_DIVIDER0 ≥ b0001: ƒin = ƒSENSOR / FIN_DIVIDER
                                            // Bit 9:0 FREF_DIVIDER must be ≥ 0x001:: ƒREF = ƒCLK / FREF_DIVIDER
    uint16_t FIN_DIVIDERS_CH0 = 0x1;
    uint16_t FIN_DIVIDERS_CH1 = 0x1;
    uint16_t FIN_DIVIDERS_CH2 = 0x1;
    uint16_t FIN_DIVIDERS_CH3 = 0x1;
    uint16_t FREF_DIVIDERS_CH0 = 0x001;
    uint16_t FREF_DIVIDERS_CH1 = 0x001;
    uint16_t FREF_DIVIDERS_CH2 = 0x001;
    uint16_t FREF_DIVIDERS_CH3 = 0x001;
};

struct Status{                              // LDC1614 Datasheet Table 25. Address 0x18, STATUS Field Descriptions
    uint16_t ERR_CHAN = 0x0;                // Bit 15:14    Error Channel (which flag has generated an error)
    uint16_t ERR_UR = 0x0;                  // Bit 13:      Conversion Under Range Error (ERR_CHAN tells which channel)
    uint16_t ERR_OR = 0x0;                  // Bit 12:      Conversion Over Range Error (ERR_CHAN tells which channel)
    uint16_t ERR_WD = 0x0;                  // Bit 11:      Watchdog Error (ERR_CHAN tells which channel)
    uint16_t ERR_AHE = 0x0;                 // Bit  9:      Amplitude High Error (Amplitude > 1.8v; ERR_CHAN tells which channel)
    uint16_t ERR_ALE = 0x0;                 // Bit  8:      Amplitude Low Error (Amplitude < 1.2v; ERR_CHAN tells which channel)
    uint16_t ERR_ZC = 0x0;                  // Bit  7:      Zero Count Error (ERR_CHAN tells which channel)
    uint16_t DRDY = 0x0;                    // Bit  6:      Data Ready (0=No new data, 1=New data)
    uint16_t UNREADCONV0 = 0x0;             // Bit  3:      Unread Conversion Result; Channel 0 (0=No new data, 1=New data)
    uint16_t UNREADCONV1 = 0x0;             // Bit  2:      Unread Conversion Result; Channel 1 (0=No new data, 1=New data)
    uint16_t UNREADCONV2 = 0x0;             // Bit  1:      Unread Conversion Result; Channel 2 (0=No new data, 1=New data)
    uint16_t UNREADCONV3 = 0x0;             // Bit  0:      Unread Conversion Result; Channel 3 (0=No new data, 1=New data)
};  

struct Config{                              // LDC1614 Datasheet Table 26. Address 0x1A, CONFIG Field Descriptions
    uint16_t ACTIVE_CHAN = 0x0;             // Bit 15:14    Active Channel when MUX_CONFIG.AUTOSCAN_EN = 0x0 (0x0=Channel 0, 0x1=Channel 1, 0x2=Channel 2, 0x3=Channel 3)
    uint16_t SLEEP_MODE_EN = 0x1;           // Bit 13:      Sleep Mode Enable (0x0=Normal operation, 0x1=Sleep mode)
    uint16_t RP_OVERRIDE_EN = 0x0;          // Bit 12:      RP Override Enable (0x0=Normal operation, 0x1=Override RP_DRIVE_CURRENT)
    uint16_t SENSOR_ACTIVATE_SEL = 0x0;     // Bit 11:      Sensor Activate Select (0x0=Full current, 0x1=DRIVE_CURRENT_CHx setting)
    uint16_t AUTO_AMP_DIS = 0x0;            // Bit 10:      Auto Amplitude Disable (0x0=Auto amplitude enabled, 0x1=Auto amplitude disabled)
    uint16_t REF_CLK_SRC = 0x0;             // Bit  9:      Reference Clock Source (0x0=Internal clock, 0x1=External clock)
    uint16_t INTB_DIS = 0x0;                // Bit  7:      INTB Dis (0x0=INTB enabled, 0x1=INTB disabled)
    uint16_t HIGH_CURRENT_DRV = 0x0;        // Bit  6:      High Current Drive (0x0= maximum 1.5mA current, 0x1=High current enabled > 1.5mA)
};

struct MuxConfig{                          // LDC1614 Datasheet Table 28. Address 0x1B, MUX_CONFIG Field Descriptions
    uint16_t AUTOSCAN_EN = 0x0;             // Bit 15:      Autoscan Enable (0x0=Continuous conversion, 0x1=Autoscan conversion)
    uint16_t RR_SEQUENCE = 0x00;            // Bit 14:13    Configure multiplexing channel sequence (0x0=Ch0,1; 0x1=Ch1,0,2; 0x2=Ch0,1,2,3; 0x3=Ch0,1)
    uint16_t MUX_RESERVED = 0b0001000001;   // Bit 12:3     Reserved - MUST be set to 0b0001000001
    uint16_t DEGLITCH = 0x5;                // Bit 2:0      Deglitch Filter Bandwidth (0b001: 1.0 MHz; 0b100: 3.3 MHz; 0b101: 10 MHz; 0b111: 33 MHz)
}; 

struct DriveCurrent{                       // LDC1614 Datasheet Table 30. Address 0x1E, DRIVE_CURRENT Field Descriptions
    uint16_t IDRIVE_CH0 = 0x00;                 // Bit 15:11    Drive Current (See datasheet section xxx; RP_OVERRIDE_EN bit must be set to 1.)
    uint16_t INIT_IDRIVE_CH0 = 0x00;            // Bit 10:6     the Initial Drive Current measured during the initial Amplitude Calibration phase
    uint16_t IDRIVE_CH1 = 0x00;                
    uint16_t INIT_IDRIVE_CH1 = 0x00;
    uint16_t IDRIVE_CH2 = 0x00;
    uint16_t INIT_IDRIVE_CH2 = 0x00;
    uint16_t IDRIVE_CH3 = 0x00;
    uint16_t INIT_IDRIVE_CH3 = 0x00;
    uint16_t IDRIVE_RESERVED = 0x00;            // Bit 5:0      Reserved - MUST be set to 0b00 0000
};

class LDC1614 {
public:
    LDC1614(TwoWire &iface, uint32_t clock);

    void connect();
    void configure_properties(float f_ref, float capacitance);
    void configure_rcount(RCount rcount);
    void configure_offset(Offset offset);
    void configure_settlecount(SettleCount settlecount);
    void configure_clock_dividers(ClockDividers clock_dividers);
    void configure_config(Config config);
    void configure_mux_config(MuxConfig mux_config);
    void configure_drive_current(DriveCurrent drive_current);

    // Read a specific channel [0-3] and return the calibrated raw value
    void readAllChannels(InductanceData& inductance_data);  // TODO: Modify to work properly with varaible number of sensors
    void getInductance(uint32_t& raw_data,  float& inductance);

    // Configuration attributes

private:
    int pin_SDA;
    int pin_SCL;
    const int LDC_ADDRESS = 0x2B;

    // Configuration attributes
    const uint8_t CH_Max = 4;
    unsigned long CH_Offset[4] = {0, 0, 0, 0};
    const unsigned long CH_Gain = 1;

    // Register address constants (from the LDC1614 datasheet)
    static const uint8_t REG_ADDR_RESET = 0x1C;
    static const uint8_t REG_ADDR_RCOUNT = 0x08;
    static const uint8_t REG_ADDR_OFFSET = 0x0D;
    static const uint8_t REG_ADDR_SETTLECOUNT = 0x10;
    static const uint8_t REG_ADDR_CLOCK_DIVIDERS = 0x14;
    static const uint8_t REG_ADDR_MUX_CONFIG = 0x1B;
    static const uint8_t REG_ADDR_DRIVE_CURRENT = 0x1E;
    static const uint8_t REG_ADDR_CONFIG = 0x1A;

    float f_ref;
    float capacitance;
    //const uint32_t sensor_resolution = 0xFFFFFFF;
    float freq_const;
    //float inductance_const; 
    //(1/(4*3.14159*3.14159));

    TwoWire *i2c;
    
    // Channel MSB/LSB addresses for channels 0-3
    const uint8_t channelMSB[4] = {0x00, 0x02, 0x04, 0x06};
    const uint8_t channelLSB[4] = {0x01, 0x03, 0x05, 0x07};

    // Private low-level I2C routines
    void writeReg(uint8_t regAddr, uint16_t regValue);
    void readValue(uint8_t regAddr, uint16_t &data);

};

#endif // LDC1614_H