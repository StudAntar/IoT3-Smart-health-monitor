#include <WiFi.h>
#include <esp_now.h>
#include <TFT_eSPI.h>
#include "TAMC_GT911.h"
#include "arduino_billede2.h"   
#include "Instructions_test.h"
#include <string.h>             
#include <esp_system.h>         

#define DEV_MODE false   

struct Button {
  int x, y, w, h;
  const char* label;
};



uint16_t COLOR_CYAN  = TFT_CYAN;   
uint16_t COLOR_WHITE = TFT_WHITE;
uint16_t COLOR_BLACK = TFT_BLACK;
uint16_t COLOR_NAVY;              


uint8_t peerAddress[] = { 0xC8, 0x2E, 0x18, 0x16, 0x91, 0xBC };   

typedef struct struct_message {
  char cmd[16];
} struct_message;

struct_message outgoingMsg;


bool uiActive = false;


bool onInstructionsScreen = false;


#define TOUCH_SDA   33
#define TOUCH_SCL   32
#define TOUCH_INT   21
#define TOUCH_RST   25


#define TOUCH_WIDTH  480
#define TOUCH_HEIGHT 320

#define TFT_BL      27

TFT_eSPI tft = TFT_eSPI();
TAMC_GT911 tp = TAMC_GT911(TOUCH_SDA, TOUCH_SCL, TOUCH_INT, TOUCH_RST,
                           TOUCH_WIDTH, TOUCH_HEIGHT);


void drawBackground() {
  tft.pushImage(
    0, 0,
    ARDUINO_BILLEDE2_WIDTH,
    ARDUINO_BILLEDE2_HEIGHT,
    arduino_billede2
  );
}


Button btnStart  = { 140, 140, 200, 70, "START" };
Button btnHelp   = {  40, 235, 200, 40, "HELP" };
Button btnManual = {  40, 285, 200, 40, "INSTRUCTIONS" };

Button btnBack   = { 480 - 100 - 10, 10, 100, 40, "TILBAGE" };

bool onHelpScreen = false;


Button btnHelpAI   = {  40, 140, 180, 80, "AI-HELPER" };
Button btnHelpFAQ  = { 260, 140, 180, 80, "FAQ" };
Button btnHelpBack = {  10,  10, 100, 40, "TILBAGE" };

bool aiPopupActive = false;

Button btnAIOk = { 0, 0, 100, 40, "OK" };


bool onFAQScreen = false;


Button btnFAQBack = { 10, 10, 100, 40, "TILBAGE" };


const char* faqQuestions[5] = {
  "Hvad bruger jeg denne enhed til?",
  "Hvor tit skal jeg lave en maaling?",
  "Hvad goer jeg hvis vaerdierne ser anderledes ud end normalt?",
  "Hvad goer jeg hvis enheden ikke virker?",
  "Sender enheden automatisk data til laegen?"
};

const char* faqAnswers[5] = {
  
  "Maaler dine helbredsvaerdier og sender dem direke til klinikken. ",

  
  "Foelg planen du har faaet af laegen. Typisk en eller flere gange dagligt.",

  
  "Gaa ikke i panik. Kontakt laegen, hvis du er i tvivl.",

  
  "Tjek Instructions og Help. Virker det ikke, så ring til klinikken",

  
  "Ja. Du skal blot tage maalingerne. Alt andet sker automatisk."
};



bool onMeasuringScreen = false;

bool resultsPopupActive = false;
unsigned long resultsPopupEndTime = 0;
bool resultsPopupDrawn = false;



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



void drawUI() {
  drawBackground();

  tft.setTextDatum(MC_DATUM);


  tft.setTextFont(1);

  tft.setTextColor(TFT_WHITE);
  tft.drawString("Smart Health Monitor", tft.width() / 2, 40);

  drawButton(btnStart,  COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
  drawButton(btnHelp,   COLOR_NAVY, COLOR_CYAN,  COLOR_WHITE);
  drawButton(btnManual, COLOR_NAVY, COLOR_CYAN,  COLOR_WHITE);

  onInstructionsScreen = false;
  onHelpScreen = false;
}



void sendCommand(const char* cmd) {
  if (DEV_MODE) {
    Serial.print("[DEV_MODE] Ville sende kommando: ");
    Serial.println(cmd);
    return;
  }

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



void onDataRecv(const esp_now_recv_info * info, const uint8_t *incomingData, int len) {
  const uint8_t * mac = info->src_addr;

  char buf[32];
  int n = (len < (int)sizeof(buf) - 1) ? len : (int)sizeof(buf) - 1;
  memcpy(buf, incomingData, n);
  buf[n] = '\0';

  Serial.print("ESP-NOW modtaget fra: ");
  for (int i = 0; i < 6; i++) {
    Serial.printf("%02X", mac[i]);
    if (i < 5) Serial.print(":");
  }
  Serial.print("  | Data: ");
  Serial.println(buf);

  if (!uiActive && strstr(buf, "SCREEN_ON") != NULL) {
    Serial.println(">>> SCREEN_ON modtaget – tænder UI");
    uiActive = true;
    digitalWrite(TFT_BL, HIGH);  
    drawUI();                   
  }

  if (strstr(buf, "SCREEN_OFF") != NULL) {
    Serial.println(">>> SCREEN_OFF modtaget – slukker UI");
    uiActive = false;
    digitalWrite(TFT_BL, LOW);   
    tft.fillScreen(TFT_BLACK);
    onInstructionsScreen = false;
  }

  if (strstr(buf, "RESULTS_DONE") != NULL) {
    Serial.println(">>> RESULTS_DONE modtaget – viser resultat-popup");

    resultsPopupActive = true;
    resultsPopupEndTime = millis() + 5000;  
    resultsPopupDrawn = false;             
  }


}



void showInstructions() {
  tft.fillScreen(TFT_BLACK);

  int x = (tft.width()  - INSTRUCTIONS_TEST_WIDTH)  / 2;
  int y = (tft.height() - INSTRUCTIONS_TEST_HEIGHT) / 2;

  tft.pushImage(
    x, y,
    INSTRUCTIONS_TEST_WIDTH,
    INSTRUCTIONS_TEST_HEIGHT,
    Instructions_test
  );

  drawButton(btnBack, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

  onInstructionsScreen = true;
}

void showMeasuringScreen() {
  tft.fillScreen(TFT_BLUE);  // eller COLOR_NAVY, hvis du foretrækker det

  tft.setTextFont(1);
  tft.setTextColor(TFT_WHITE, TFT_BLUE);
  tft.setTextDatum(MC_DATUM);
  tft.drawString("Maalinger i gang...", tft.width() / 2, tft.height() / 2);

  onMeasuringScreen = true;
  onHelpScreen = false;
  onFAQScreen = false;
  onInstructionsScreen = false;
}


void drawHelpBackground() {
  uint16_t topColor    = tft.color565(40, 90, 180);   // lys blå
  uint16_t bottomColor = tft.color565(10, 40, 90);    // navy blå

  for (int y = 0; y < tft.height(); y++) {
    float ratio = (float)y / tft.height();

    uint8_t r = ((1 - ratio) * ((topColor >> 11) & 0x1F) + ratio * ((bottomColor >> 11) & 0x1F));
    uint8_t g = ((1 - ratio) * ((topColor >> 5)  & 0x3F) + ratio * ((bottomColor >> 5)  & 0x3F));
    uint8_t b = ((1 - ratio) * ((topColor)       & 0x1F) + ratio * ((bottomColor)       & 0x1F));

    uint16_t color = (r << 11) | (g << 5) | b;

    tft.drawFastHLine(0, y, tft.width(), color);
  }
}


void showHelpScreen() {
  drawHelpBackground();

  tft.setTextDatum(MC_DATUM);
  tft.setTextFont(1);
  tft.setTextColor(TFT_WHITE);

  tft.drawString("HELP", tft.width() / 2, 40);

  drawButton(btnHelpAI,  COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);
  drawButton(btnHelpFAQ, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

  drawButton(btnHelpBack, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

  onHelpScreen = true;
}

void showAIPopup() {
  int boxW = 300;
  int boxH = 150;
  int boxX = (tft.width()  - boxW) / 2;
  int boxY = (tft.height() - boxH) / 2;

  tft.fillRoundRect(boxX - 10, boxY - 10, boxW + 20, boxH + 20, 12, tft.color565(5, 20, 40));

  tft.fillRoundRect(boxX, boxY, boxW, boxH, 10, TFT_WHITE);
  tft.drawRoundRect(boxX, boxY, boxW, boxH, 10, COLOR_CYAN);

  tft.setTextFont(1);
  tft.setTextColor(TFT_BLACK, TFT_WHITE);
  tft.setTextDatum(MC_DATUM);
  tft.drawString("AI-helper",      tft.width() / 2, boxY + 45);
  tft.drawString("Coming soon...", tft.width() / 2, boxY + 80);

  btnAIOk.x = tft.width() / 2 - btnAIOk.w / 2;
  btnAIOk.y = boxY + boxH - btnAIOk.h - 10;
  drawButton(btnAIOk, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);

  aiPopupActive = true;
}

void showResultsPopup() {
  int boxW = 340;
  int boxH = 160;
  int boxX = (tft.width()  - boxW) / 2;
  int boxY = (tft.height() - boxH) / 2;

  tft.fillRoundRect(boxX - 10, boxY - 10, boxW + 20, boxH + 20, 12, tft.color565(5, 20, 40));

  tft.fillRoundRect(boxX, boxY, boxW, boxH, 10, TFT_WHITE);
  tft.drawRoundRect(boxX, boxY, boxW, boxH, 10, COLOR_CYAN);

  tft.setTextFont(1);
  tft.setTextColor(TFT_BLACK, TFT_WHITE);
  tft.setTextDatum(MC_DATUM);

  tft.drawString("Resultat", tft.width() / 2, boxY + 45);

  tft.drawString("Maalingerne er registrerede",
                 tft.width() / 2,
                 boxY + 90);

  onMeasuringScreen = false;
}



void showFAQScreen() {
  drawHelpBackground();

  tft.setTextFont(1);
  tft.setTextDatum(TL_DATUM);   // venstre-justeret tekst
  tft.setTextColor(TFT_BLACK, TFT_WHITE);

  
  tft.drawString("FAQ", 20, 20);

  int y = 60;

  for (int i = 0; i < 5; i++) {
    tft.setTextColor(TFT_BLUE, TFT_WHITE);
    tft.drawString(String(i+1) + ". " + faqQuestions[i], 20, y);
    y += 20;

    tft.setTextColor(TFT_BLACK, TFT_WHITE);
    tft.drawString(" - " + String(faqAnswers[i]), 20, y);
    y += 25;
  }

  drawButton(btnFAQBack, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

  onFAQScreen = true;
}


void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(TFT_BL, OUTPUT);

  if (DEV_MODE) {
    Serial.println("DEV_MODE: Skærmen er tvangstændt, ESP-NOW deaktiveret");

    digitalWrite(TFT_BL, HIGH);

    tft.init();
    tft.setRotation(1);
    tft.setSwapBytes(true);
    COLOR_NAVY = tft.color565(10, 26, 60);

    drawUI();  // ← viser din arduino_billede2 + knapper

    tp.begin();
    tp.setRotation(ROTATION_RIGHT);

    uiActive = true;
    return;
  }


  WiFi.mode(WIFI_MODE_NULL);
  delay(100);
  WiFi.mode(WIFI_STA);
  delay(200);

  Serial.print("Skærm-ESP MAC: ");
  Serial.println(WiFi.macAddress());

  digitalWrite(TFT_BL, LOW);

  tft.init();
  tft.setRotation(1);
  tft.setSwapBytes(true);
  COLOR_NAVY = tft.color565(10, 26, 60);
  tft.fillScreen(TFT_BLACK);

  tp.begin();
  tp.setRotation(ROTATION_RIGHT);

  if (esp_now_init() != ESP_OK) {
    Serial.println("Fejl: esp_now_init()");
    return;
  }

  esp_now_register_recv_cb(onDataRecv);

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, peerAddress, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;
  esp_now_add_peer(&peerInfo);
}


void loop() {
  if (!uiActive) {
    delay(20);
    return;
  }

  if (resultsPopupActive) {
    if (!resultsPopupDrawn) {
      showResultsPopup();
      resultsPopupDrawn = true;
    }

    if (millis() >= resultsPopupEndTime) {
      drawUI();
      resultsPopupActive = false;
      resultsPopupDrawn = false;
      onMeasuringScreen = false;
    }

    delay(10);
    return;  
  }


  tp.read();

  if (!tp.isTouched) {
    delay(10);
    return;
  }

  uint16_t x = tp.points[0].x;
  uint16_t y = tp.points[0].y;

  if (onHelpScreen) {

  
    if (aiPopupActive) {
      if (pointInButton(btnAIOk, x, y)) {
        drawButton(btnAIOk, COLOR_WHITE, COLOR_CYAN, COLOR_BLACK);
        delay(150);

     
        showHelpScreen();
        aiPopupActive = false;
      }

      delay(10);
      return;
    }

  
    if (pointInButton(btnHelpAI, x, y)) {
      drawButton(btnHelpAI, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
      delay(150);
      drawButton(btnHelpAI, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

      showAIPopup();  
      delay(10);
      return;
    }

    
    if (pointInButton(btnHelpFAQ, x, y)) {
      drawButton(btnHelpFAQ, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
      delay(150);
      drawButton(btnHelpFAQ, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

      showFAQScreen();   
      delay(10);
      return;
    }

   
    if (pointInButton(btnHelpBack, x, y)) {
      drawButton(btnHelpBack, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
      delay(150);
      drawUI();
    }

    delay(10);
    return;
  }


  if (onFAQScreen) {
   
    if (pointInButton(btnFAQBack, x, y)) {
      drawButton(btnFAQBack, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
      delay(150);

      showHelpScreen();      
      onFAQScreen = false;  
    }

    delay(10);
    return;
  }

  if (onInstructionsScreen) {
    if (pointInButton(btnBack, x, y)) {
      drawButton(btnBack, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
      delay(150);
      drawUI();
    }

    delay(10);
    return;
  }


  if (pointInButton(btnStart, x, y)) {
    drawButton(btnStart, COLOR_WHITE, COLOR_CYAN, COLOR_BLACK);
    sendCommand("START");
    delay(150);
     
    showMeasuringScreen();
  }

  if (pointInButton(btnHelp, x, y)) {
    drawButton(btnHelp, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
    delay(150);
    drawButton(btnHelp, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

    showHelpScreen();  
  }

  if (pointInButton(btnManual, x, y)) {
    drawButton(btnManual, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
    delay(150);

    showInstructions();
  }

  delay(10);
}



