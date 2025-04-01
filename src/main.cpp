

#include <Adafruit_GFX.h>    // Core graphics library
#include <Adafruit_ST7789.h> // Hardware-specific library for ST7789
#include <Adafruit_NeoPixel.h>
#include <SPI.h>
#include <Wire.h>
#include <LDC1614.h>
#include "driver/periph_ctrl.h"
#include "soc/gpio_struct.h"
#include "soc/gpio_reg.h"



// Use dedicated hardware SPI pins
// SPIClass spi = SPIClass(HSPI);
Adafruit_ST7789 tft = Adafruit_ST7789(TFT_CS, TFT_DC, TFT_RST);

#define SPI_FREQUENCY 80000000

#define SCREEN_HEIGHT 135
#define SCREEN_WIDTH 240

// Text stores (filled with 0xFF)
#define FONT_SIZE 2
#define CHAR_WIDTH 6
#define CHAR_HEIGHT 8

#define TEXT_ARRAY_HEIGHT SCREEN_WIDTH / CHAR_WIDTH
#define TEXT_ARRAY_WIDTH SCREEN_HEIGHT / CHAR_HEIGHT
String text[TEXT_ARRAY_HEIGHT] = {""};
String values[TEXT_ARRAY_HEIGHT] = {""};

uint8_t text_end_index[TEXT_ARRAY_HEIGHT] = {0};


// Define sensor details
#define OSC_FREQ 40.0     //MHz
#define OSC_PERIOD 1/OSC_FREQ
#define CAPACITANCE 330.0 //pF

LDC1614 *sensor;

float pos_x, pos_y, pos_z = 0;

float p = 3.1415926;

InductanceData data;
InductanceData tare_data;

// Neopixel
#define PIN_NEOPIXEL 33
// RGB_BUILTIN and RGB_BRIGHTNESS can be used in new Arduino API rgbLedWrite() and digitalWrite() for blinking
#define RGB_BUILTIN    (PIN_NEOPIXEL + SOC_GPIO_PIN_COUNT)
#define RGB_BRIGHTNESS 64

#define NEOPIXEL_NUM      1     // number of neopixels
#define NEOPIXEL_POWER    34    // power pin
#define NEOPIXEL_POWER_ON HIGH  // power pin state when on


uint32_t colors[] = { 0xFF0000, 0x00FF00, 0xFFFFFF }; // Red, green, white

Adafruit_NeoPixel pixels = Adafruit_NeoPixel(NEOPIXEL_NUM, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);

// Initialise LDC1614 sensor
void initSensor(void) {
  
}

void setup(void) {
  Serial.begin(115200);

  // Diable Pullups on i2c
  gpio_pullup_dis(GPIO_NUM_41);
  gpio_pullup_dis(GPIO_NUM_42);

  gpio_set_level(GPIO_NUM_41,1);
  gpio_set_level(GPIO_NUM_42,1);

  // init neopixel
  sensor = new LDC1614(Wire, 300000);

  // turn on backlite
  pinMode(TFT_BACKLITE, OUTPUT);
  digitalWrite(TFT_BACKLITE, LOW);

  // turn on the TFT / I2C power supply
  pinMode(TFT_I2C_POWER, OUTPUT);
  digitalWrite(TFT_I2C_POWER, HIGH);
  delay(10);

    

  // initialize TFT
 
  tft.init(135, 240); // Init ST7789 240x135 
  tft.setSPISpeed(SPI_FREQUENCY);
  tft.setRotation(3);
  tft.fillScreen(ST77XX_BLACK);

  // turn on backlite
  pinMode(TFT_BACKLITE, OUTPUT);
  digitalWrite(TFT_BACKLITE, HIGH);

  RCount rcount;
  rcount.RCOUNT_CH0 = 0x086; //0x30BD;
  
  Offset offset;
  offset.OFFSET_CH0 = 0;

  SettleCount settlecount;
  settlecount.SETTLECOUNT_CH0 = 0x0014;

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
  drive_current.IDRIVE_CH0 = 0x15;

    // Init LDC1614 sensor
  sensor->connect();
  sensor->configure_properties(OSC_FREQ, CAPACITANCE);
  sensor->configure_rcount(rcount);
  sensor->configure_offset(offset);
  sensor->configure_settlecount(settlecount);  
  sensor->configure_mux_config(mux_config);
  sensor->configure_clock_dividers(clock_dividers);
  sensor->configure_drive_current(drive_current);
  sensor->configure_config(config);

  delay(100);
  sensor->readAllChannels(tare_data);

  tft.setTextColor(ST77XX_WHITE, ST77XX_BLACK);
  tft.setTextSize(FONT_SIZE);

  text[0] = "Sensor Values: ";
  text[1] = "Sensor x: ";
  text[2] = "Sensor y: ";
  text[3] = "Sensor z: ";
  text[5] = "Loop: ";
  text[6] = "Data: ";
  

  for (int i = 0; i < TEXT_ARRAY_HEIGHT; i++) {
    tft.setCursor(0, (i + 1) * CHAR_HEIGHT * FONT_SIZE);
    tft.print(text[i]);
    
    text_end_index[i] = text[i].length();
  }

}

void loop() {
  int t = micros();
  sensor->readAllChannels(data);

  // pos_x = -(data.inductance[0] - tare_data.inductance[0]) - (data.inductance[1] - tare_data.inductance[1]) + (data.inductance[2] - tare_data.inductance[2]) + (data.inductance[3] - tare_data.inductance[3]);
  // pos_y = -(data.inductance[0] - tare_data.inductance[0]) + (data.inductance[1] - tare_data.inductance[1]) + (data.inductance[2] - tare_data.inductance[2]) - (data.inductance[3] - tare_data.inductance[3]);
  // pos_z = (data.inductance[0] - tare_data.inductance[0]) - (data.inductance[1] - tare_data.inductance[1]) + (data.inductance[2] - tare_data.inductance[2]) - (data.inductance[3] - tare_data.inductance[3]);
  // int data_t = micros() - t;
  
  // tft.setTextColor(ST77XX_BLACK);
  // for (int i = 0; i < TEXT_ARRAY_HEIGHT; i++) {
  //   tft.setCursor(text_end_index[i]*CHAR_WIDTH * FONT_SIZE, (i + 1) * CHAR_HEIGHT * FONT_SIZE);
  //   tft.print(values[i]);
  // }

  // tft.setTextColor(ST77XX_WHITE);

  // values[6] = String(data_t);
  // tft.setCursor(text_end_index[6] * CHAR_WIDTH * FONT_SIZE, (6 + 1) * CHAR_HEIGHT * FONT_SIZE);
  // tft.print(values[6]);

  // for (int i = 1; i < 4; i++) {
  //   tft.setCursor(text_end_index[i]*CHAR_WIDTH * FONT_SIZE, (i + 1) * CHAR_HEIGHT * FONT_SIZE);
    
  //   switch (i)
  //   {
  //   case 1:
  //     values[i] = String(pos_x, 4);
  //     tft.print(values[i]);
  //     break;
  //   case 2:
  //     values[i] = String(pos_y, 4);
  //     tft.print(values[i]);
  //     break;
  //   case 3:
  //     values[i] = String(pos_z, 4);
  //     tft.print(values[i]);
  //     break;    
  //   default:
  //     break;
  //   }    
  // }

  // Serial.println("Sensor Values:");
  // Serial.println(" ");
  // Serial.println("Sensor x: " + String(pos_x, 6));
  // Serial.println("Sensor y: " + String(pos_y, 6));
  // Serial.println("Sensor x: " + String(pos_z, 6));

  // Serial.println("Sensor 1: " + String(data.inductance[0]) + "uH");
  // Serial.println("Sensor 2: " + String(data.inductance[1]) + "uH");
  // Serial.println("Sensor 3: " + String(data.inductance[2]) + "uH");
  // Serial.println("Sensor 4: " + String(data.inductance[3]) + "uH");

  Serial.println(String(data.inductance[3],10));
  
  // values[5] = String((micros() - t));
  // tft.setCursor(text_end_index[5] * CHAR_WIDTH * FONT_SIZE, (5 + 1) * CHAR_HEIGHT * FONT_SIZE);
  // tft.print(values[5]);

  // delay(30);
}

