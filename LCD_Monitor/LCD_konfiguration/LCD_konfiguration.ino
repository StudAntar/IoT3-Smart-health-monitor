#include <WiFi.h>
#include <esp_now.h>
#include <TFT_eSPI.h>
#include "TAMC_GT911.h"

// ======================================================
//  ESP-NOW: SKIFT DENNE TIL DIN RECEIVER-ESPs MAC-ADRESSE
//  Eksempel: uint8_t peerAddress[] = { 0xC8, 0x2E, 0x18, 0x14, 0xD6, 0xC0 };
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
//  KNAPPER
// ======================================================

struct Button {
  int x, y, w, h;
  const char* label;
};

Button btnHelp = { 60,  200, 150, 60, "HJ\u00C6LP" };
Button btnInfo = { 270, 200, 150, 60, "INFO" };

void drawButton(const Button& b, uint16_t bg, uint16_t border, uint16_t txt) {
  tft.fillRoundRect(b.x, b.y, b.w, b.h, 8, bg);
  tft.drawRoundRect(b.x, b.y, b.w, b.h, 8, border);
  tft.setTextColor(txt, bg);
  tft.setTextDatum(MC_DATUM);
  tft.drawString(b.label, b.x + b.w / 2, b.y + b.h / 2, 4);
}

bool pointInButton(const Button& b, uint16_t x, uint16_t y) {
  return (x >= b.x && x <= b.x + b.w &&
          y >= b.y && y <= b.y + b.h);
}

void drawUI() {
  tft.fillScreen(TFT_DARKGREY);

  tft.setTextColor(TFT_WHITE, TFT_DARKGREY);
  tft.setTextDatum(MC_DATUM);
  tft.drawString("HealthBox", tft.width() / 2, 40, 4);

  tft.setTextColor(TFT_YELLOW, TFT_DARKGREY);
  tft.drawString("Tryk pa en funktion", tft.width() / 2, 80, 2);

  tft.setTextColor(TFT_SKYBLUE, TFT_DARKGREY);
  tft.drawString("HJÆLP = guidet hjalp", tft.width() / 2, 120, 2);

  drawButton(btnHelp, TFT_NAVY, TFT_WHITE, TFT_WHITE);
  drawButton(btnInfo, TFT_NAVY, TFT_WHITE, TFT_WHITE);
}


// ======================================================
//  SEND KOMMANDO VIA ESP-NOW
// ======================================================

void sendCommand(const char* cmd) {
  // Kopiér tekst ind i struct
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
  Serial.println("Skærm-ESP: UI + ESP-NOW sender");

  // Backlight
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, HIGH);

  // TFT
  tft.init();
  tft.setRotation(1);      // Landscape (480x320)
  drawUI();

  // Touch
  tp.begin();
  tp.setRotation(ROTATION_RIGHT);   // Matcher TFT-rotation

  // ESP-NOW init
  WiFi.mode(WIFI_STA);

  Serial.print("Skærm-ESP MAC: ");
  Serial.println(WiFi.macAddress());

  if (esp_now_init() != ESP_OK) {
    Serial.println("Fejl: esp_now_init()");
    return;
  }

  // Tilføj peer (din MicroPython-receiver)
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

    // HJÆLP-knap
    if (pointInButton(btnHelp, x, y)) {
      Serial.println("HJÆLP trykket (sender HELP)");
      drawButton(btnHelp, TFT_GREEN, TFT_WHITE, TFT_BLACK);
      sendCommand("HELP");
      delay(150);
      drawButton(btnHelp, TFT_NAVY, TFT_WHITE, TFT_WHITE);
    }

    // INFO-knap
    if (pointInButton(btnInfo, x, y)) {
      Serial.println("INFO trykket (sender INFO)");
      drawButton(btnInfo, TFT_GREEN, TFT_WHITE, TFT_BLACK);
      sendCommand("INFO");
      delay(150);
      drawButton(btnInfo, TFT_NAVY, TFT_WHITE, TFT_WHITE);
    }
  }

  delay(10);
}
