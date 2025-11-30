#include <WiFi.h>
#include <esp_now.h>
#include <TFT_eSPI.h>
#include "TAMC_GT911.h"
#include "arduino_billede2.h"   // Baggrundsbillede
//#include <Free_Fonts.h>   // Indeholder FSB12 osv.


struct Button {
  int x, y, w, h;
  const char* label;
};

// ======================================================
//  FARVER (NYT)
// ======================================================
uint16_t COLOR_CYAN  = TFT_CYAN;   // lys blå/cyan
uint16_t COLOR_WHITE = TFT_WHITE;
uint16_t COLOR_BLACK = TFT_BLACK;
uint16_t COLOR_NAVY;               // sættes i setup()

// ======================================================
//  ESP-NOW: SKIFT DENNE TIL DIN RECEIVER-ESPs MAC-ADRESSE
// ======================================================
uint8_t peerAddress[] = { 0xC8, 0x2E, 0x18, 0x14, 0xD6, 0xC0 };   // <-- RET HER

// Packet-struktur
typedef struct struct_message {
  char cmd[16];
} struct_message;

struct_message outgoingMsg;


// ======================================================
//  TOUCH / DISPLAY KONFIGURATION
// ======================================================

// Touch pins på ESP32-3248S035C
#define TOUCH_SDA   33
#define TOUCH_SCL   32
#define TOUCH_INT   21
#define TOUCH_RST   25

// Vi kører i LANDSCAPE (480x320)
#define TOUCH_WIDTH  480
#define TOUCH_HEIGHT 320

// Backlight-pin
#define TFT_BL      27

TFT_eSPI tft = TFT_eSPI();
TAMC_GT911 tp = TAMC_GT911(TOUCH_SDA, TOUCH_SCL, TOUCH_INT, TOUCH_RST,
                           TOUCH_WIDTH, TOUCH_HEIGHT);

// ======================================================
//  BAGGRUND
// ======================================================

void drawBackground() {
  tft.pushImage(
    0, 0,
    ARDUINO_BILLEDE2_WIDTH,
    ARDUINO_BILLEDE2_HEIGHT,
    arduino_billede2
  );
}

// ======================================================
//  KNAPPER
// ======================================================


// Start i midten, Hjælp + Instruktioner nederst til venstre
Button btnStart  = { 140, 140, 200, 70, "START" };
Button btnHelp   = {  40, 235, 200, 40, "HELP" };
Button btnManual = {  40, 285, 200, 40, "INSTRUCTIONS" };  // Kortere og passer

void drawButton(const Button& b, uint16_t bg, uint16_t border, uint16_t txt) {
  tft.fillRoundRect(b.x, b.y, b.w, b.h, 10, bg);
  tft.drawRoundRect(b.x, b.y, b.w, b.h, 10, border);
  tft.setTextColor(txt, bg);
  tft.setTextDatum(MC_DATUM);
  tft.drawString(b.label, b.x + b.w / 2, b.y + b.h / 2, 4);
}

bool pointInButton(const Button& b, uint16_t x, uint16_t y) {
  return (x >= b.x && x <= b.x + b.w &&
          y >= b.y && y <= b.y + b.h);
}

// ======================================================
//  UI
// ======================================================

void drawUI() {
  drawBackground();

  tft.setTextDatum(MC_DATUM);

  // Brug den indbyggede font med Æ/Ø/Å
  tft.setTextFont(1);

  tft.setTextColor(TFT_WHITE);
  tft.drawString("Smart Health Monitor", tft.width() / 2, 40);

  drawButton(btnStart,  COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
  drawButton(btnHelp,   COLOR_NAVY, COLOR_CYAN,  COLOR_WHITE);
  drawButton(btnManual, COLOR_NAVY, COLOR_CYAN,  COLOR_WHITE);
}






// ======================================================
//  SEND KOMMANDO VIA ESP-NOW
// ======================================================

void sendCommand(const char* cmd) {
  strncpy(outgoingMsg.cmd, cmd, sizeof(outgoingMsg.cmd));
  outgoingMsg.cmd[sizeof(outgoingMsg.cmd) - 1] = '\0';

  esp_err_t result = esp_now_send(peerAddress,
                                  (uint8_t*) &outgoingMsg,
                                  sizeof(outgoingMsg));

  Serial.print("Sendte kommando: ");
  Serial.print(cmd);
  Serial.print("  -> esp_now_send result: ");
  Serial.println(result == ESP_OK ? "OK" : "FEJL");
}


// ======================================================
//  SETUP
// ======================================================

void setup() {
  Serial.begin(115200);
  Serial.println("Sk\u00E6rm-ESP: Smart Health Monitor UI + ESP-NOW sender");

  // Backlight
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, HIGH);

  // TFT
  tft.init();
  tft.setRotation(1);       // Landscape (480x320)
  tft.setSwapBytes(true);   // VIGTIGT for RGB565-baggrund fra .h

  // Sæt custom navy-farve (NYT)
  COLOR_NAVY = tft.color565(10, 26, 60);

  drawUI();

  // Touch
  tp.begin();
  tp.setRotation(ROTATION_RIGHT);   // Matcher TFT-rotation

  // ESP-NOW init
  WiFi.mode(WIFI_STA);

  Serial.print("Sk\u00E6rm-ESP MAC: ");
  Serial.println(WiFi.macAddress());

  if (esp_now_init() != ESP_OK) {
    Serial.println("Fejl: esp_now_init()");
    return;
  }

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, peerAddress, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("Fejl: esp_now_add_peer()");
    return;
  }
}


// ======================================================
//  LOOP
// ======================================================

void loop() {
  tp.read();

  if (tp.isTouched) {
    uint16_t x = tp.points[0].x;
    uint16_t y = tp.points[0].y;

    // START
    if (pointInButton(btnStart, x, y)) {
      drawButton(btnStart, COLOR_WHITE, COLOR_CYAN, COLOR_BLACK);
      sendCommand("START");
      delay(150);
      drawButton(btnStart, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
    }

    // HJÆLP
    if (pointInButton(btnHelp, x, y)) {
      drawButton(btnHelp, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
      sendCommand("HELP");
      delay(150);
      drawButton(btnHelp, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);
    }

    // INSTRUKTION
    if (pointInButton(btnManual, x, y)) {
      drawButton(btnManual, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
      sendCommand("INSTRUKTION");
      delay(150);
      drawButton(btnManual, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);
    }
  }

  delay(10);
}
