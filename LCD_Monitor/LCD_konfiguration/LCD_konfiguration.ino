#include <WiFi.h>
#include <esp_now.h>
#include <TFT_eSPI.h>
#include "TAMC_GT911.h"
#include "arduino_billede2.h"   // Baggrundsbillede
#include "Instructions_test.h"
#include <string.h>             // til memcpy, strncpy, strstr
#include <esp_system.h>         // for esp_read_mac + ESP_MAC_WIFI_STA

#define DEV_MODE false   // ← SKIFT til false når du vil bruge SCREEN_ON igen

struct Button {
  int x, y, w, h;
  const char* label;
};

// ======================================================
//  FARVER
// ======================================================
uint16_t COLOR_CYAN  = TFT_CYAN;   // lys blå/cyan
uint16_t COLOR_WHITE = TFT_WHITE;
uint16_t COLOR_BLACK = TFT_BLACK;
uint16_t COLOR_NAVY;               // sættes i setup()

// ======================================================
//  ESP-NOW: RET peerAddress TIL STYREENHEDENS MAC-ADRESSE
// ======================================================
uint8_t peerAddress[] = { 0xC8, 0x2E, 0x18, 0x16, 0x91, 0xBC };   // <-- CONTROLLER-ESP32 MAC

// Packet-struktur
typedef struct struct_message {
  char cmd[16];
} struct_message;

struct_message outgoingMsg;

// UI state – starter SLUKKET
bool uiActive = false;

// Ekstra UI-state: er vi på instruktionsskærmen?
bool onInstructionsScreen = false;

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

Button btnStart  = { 140, 140, 200, 70, "START" };
Button btnHelp   = {  40, 235, 200, 40, "HELP" };
Button btnManual = {  40, 285, 200, 40, "INSTRUCTIONS" };
// Tilbage-knap til instruktionsskærmen (øverst til højre)
Button btnBack   = { 480 - 100 - 10, 10, 100, 40, "TILBAGE" };
// HELP-screen state
bool onHelpScreen = false;

// HELP-knapper
Button btnHelpAI   = {  40, 140, 180, 80, "AI-HELPER" };
Button btnHelpFAQ  = { 260, 140, 180, 80, "FAQ" };
Button btnHelpBack = {  10,  10, 100, 40, "TILBAGE" };

bool aiPopupActive = false;

Button btnAIOk = { 0, 0, 100, 40, "OK" };


bool onFAQScreen = false;

// FAQ tilbage-knap
Button btnFAQBack = { 10, 10, 100, 40, "TILBAGE" };

// FAQ-tekst (5 spørgsmål/svar)
const char* faqQuestions[5] = {
  "Hvad bruger jeg denne enhed til?",
  "Hvor tit skal jeg lave en maaling?",
  "Hvad goer jeg hvis vaerdierne ser anderledes ud end normalt?",
  "Hvad goer jeg hvis enheden ikke virker?",
  "Sender enheden automatisk data til laegen?"
};

const char* faqAnswers[5] = {
  // Svar 1
  "Maaler dine helbredsvaerdier og sender dem direke til klinikken. ",

  // Svar 2
  "Foelg planen du har faaet af laegen. Typisk en eller flere gange dagligt.",

  // Svar 3
  "Gaa ikke i panik. Kontakt laegen, hvis du er i tvivl.",

  // Svar 4
  "Tjek Instructions og Help. Virker det ikke, så ring til klinikken",

  // Svar 5
  "Ja. Du skal blot tage maalingerne. Alt andet sker automatisk."
};


// Måling/Resultat state
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

  // Når vi tegner forsiden, er vi ikke længere på instruktionsskærmen
  onInstructionsScreen = false;
  onHelpScreen = false;
}

// ======================================================
//  SEND KOMMANDO VIA ESP-NOW
// ======================================================

void sendCommand(const char* cmd) {
  // I DEV_MODE: send ikke noget via ESP-NOW, det er ikke initialiseret
  if (DEV_MODE) {
    Serial.print("[DEV_MODE] Ville sende kommando: ");
    Serial.println(cmd);
    return;
  }

  // Normal mode: send rigtigt via ESP-NOW
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
//  ESP-NOW MODTAGER CALLBACK (NY SIGNATUR TIL CORE v3+)
// ======================================================

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

  // --- TÆND SKÆRMEN ---
  if (!uiActive && strstr(buf, "SCREEN_ON") != NULL) {
    Serial.println(">>> SCREEN_ON modtaget – tænder UI");
    uiActive = true;
    digitalWrite(TFT_BL, HIGH);  // tænd backlight
    drawUI();                    // tegn hele forsiden
  }

  // --- SLUK SKÆRMEN ---
  if (strstr(buf, "SCREEN_OFF") != NULL) {
    Serial.println(">>> SCREEN_OFF modtaget – slukker UI");
    uiActive = false;
    digitalWrite(TFT_BL, LOW);   // sluk backlight
    tft.fillScreen(TFT_BLACK);   // ryd skærmen
    onInstructionsScreen = false;
  }

      // --- RESULTS_DONE: aktiver resultat-popup i 5 sekunder ---
  if (strstr(buf, "RESULTS_DONE") != NULL) {
    Serial.println(">>> RESULTS_DONE modtaget – viser resultat-popup");

    resultsPopupActive = true;
    resultsPopupEndTime = millis() + 5000;  // 5 sekunder fra nu
    resultsPopupDrawn = false;              // loop() sørger for at tegne den
  }


}

// ======================================================
//  INSTRUKTIONSSKÆRM
// ======================================================

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
  // Simpel blå skærm med tekst
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

  // Overskrift
  tft.drawString("HELP", tft.width() / 2, 40);

  // De to bokse
  drawButton(btnHelpAI,  COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);
  drawButton(btnHelpFAQ, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

  // Tilbage-knap til forsiden
  drawButton(btnHelpBack, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

  onHelpScreen = true;
}

void showAIPopup() {
  // Popup-boks i midten
  int boxW = 300;
  int boxH = 150;
  int boxX = (tft.width()  - boxW) / 2;
  int boxY = (tft.height() - boxH) / 2;

  // "Overlay"-effekt: mørk baggrund rundt om boksen
  // (vi tegner bare et lidt mørkere felt bagved - pseudo-overlay)
  tft.fillRoundRect(boxX - 10, boxY - 10, boxW + 20, boxH + 20, 12, tft.color565(5, 20, 40));

  // Selve popup-boksen
  tft.fillRoundRect(boxX, boxY, boxW, boxH, 10, TFT_WHITE);
  tft.drawRoundRect(boxX, boxY, boxW, boxH, 10, COLOR_CYAN);

  // Tekst i boksen
  tft.setTextFont(1);
  tft.setTextColor(TFT_BLACK, TFT_WHITE);
  tft.setTextDatum(MC_DATUM);
  tft.drawString("AI-helper",      tft.width() / 2, boxY + 45);
  tft.drawString("Coming soon...", tft.width() / 2, boxY + 80);

  // Placer OK-knappen i bunden af boksen
  btnAIOk.x = tft.width() / 2 - btnAIOk.w / 2;
  btnAIOk.y = boxY + boxH - btnAIOk.h - 10;
  drawButton(btnAIOk, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);

  aiPopupActive = true;
}

void showResultsPopup() {
  // Størrelse på boksen (samme stil som AI-helper)
  int boxW = 340;
  int boxH = 160;
  int boxX = (tft.width()  - boxW) / 2;
  int boxY = (tft.height() - boxH) / 2;

  // "Overlay" baggrund – mørk blå, som i AI-helper
  tft.fillRoundRect(boxX - 10, boxY - 10, boxW + 20, boxH + 20, 12, tft.color565(5, 20, 40));

  // Selve hvid boks
  tft.fillRoundRect(boxX, boxY, boxW, boxH, 10, TFT_WHITE);
  tft.drawRoundRect(boxX, boxY, boxW, boxH, 10, COLOR_CYAN);

  // Tekst inde i boksen
  tft.setTextFont(1);
  tft.setTextColor(TFT_BLACK, TFT_WHITE);
  tft.setTextDatum(MC_DATUM);

  // Overskrift
  tft.drawString("Resultat", tft.width() / 2, boxY + 45);

  // Selve beskeden
  tft.drawString("Maalingerne er registrerede",
                 tft.width() / 2,
                 boxY + 90);

  // Vi er ikke længere i "Maalinger i gang..." state
  onMeasuringScreen = false;
}



void showFAQScreen() {
  drawHelpBackground();

  tft.setTextFont(1);
  tft.setTextDatum(TL_DATUM);   // venstre-justeret tekst
  tft.setTextColor(TFT_BLACK, TFT_WHITE);

  // Overskrift
  tft.drawString("FAQ", 20, 20);

  // Startposition for FAQ-tekst
  int y = 60;

  // Loop gennem de 5 spørgsmål og svar
  for (int i = 0; i < 5; i++) {
    tft.setTextColor(TFT_BLUE, TFT_WHITE);
    tft.drawString(String(i+1) + ". " + faqQuestions[i], 20, y);
    y += 20;

    tft.setTextColor(TFT_BLACK, TFT_WHITE);
    tft.drawString(" - " + String(faqAnswers[i]), 20, y);
    y += 25;
  }

  // Tegn tilbage-knappen
  drawButton(btnFAQBack, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

  onFAQScreen = true;
}


// ======================================================
//  SETUP
// ======================================================

void setup() {
  Serial.begin(115200);
  delay(500);

  // Backlight pin
  pinMode(TFT_BL, OUTPUT);

  // ----- DEV MODE: Skærmen tændes direkte, ESP-NOW ignoreres -----
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

  // ----- NORMAL MODE: Skærmen er slukket og venter på SCREEN_ON -----

  // Fix for ESP32-3248S035C MAC bug
  WiFi.mode(WIFI_MODE_NULL);
  delay(100);
  WiFi.mode(WIFI_STA);
  delay(200);

  Serial.print("Skærm-ESP MAC: ");
  Serial.println(WiFi.macAddress());

  // Backlight – START SLUKKET
  digitalWrite(TFT_BL, LOW);

  // TFT
  tft.init();
  tft.setRotation(1);
  tft.setSwapBytes(true);
  COLOR_NAVY = tft.color565(10, 26, 60);
  tft.fillScreen(TFT_BLACK);

  // Touch
  tp.begin();
  tp.setRotation(ROTATION_RIGHT);

  // ESP-NOW
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

// ======================================================
//  LOOP
// ======================================================

void loop() {
  // Hvis UI ikke er aktivt endnu, ignorer touch
  if (!uiActive) {
    delay(20);
    return;
  }

    // Hvis resultat-popup er aktiv, så håndter kun tid og ignorér touch
  // Håndter RESULTS_DONE-popup’en
  if (resultsPopupActive) {
    // Sørg for at popuppen bliver tegnet (kun første gang)
    if (!resultsPopupDrawn) {
      showResultsPopup();
      resultsPopupDrawn = true;
    }

    // Når de 5 sekunder er gået → tilbage til forsiden
    if (millis() >= resultsPopupEndTime) {
      drawUI();
      resultsPopupActive = false;
      resultsPopupDrawn = false;
      onMeasuringScreen = false;
    }

    delay(10);
    return;  // Ignorér touch mens popuppen vises
  }


  tp.read();

  if (!tp.isTouched) {
    delay(10);
    return;
  }

  uint16_t x = tp.points[0].x;
  uint16_t y = tp.points[0].y;

  // 1) Hvis vi ER på HELP-skærmen
  if (onHelpScreen) {

    // Først: hvis popup er aktiv → kun OK-knappen virker
    if (aiPopupActive) {
      if (pointInButton(btnAIOk, x, y)) {
        drawButton(btnAIOk, COLOR_WHITE, COLOR_CYAN, COLOR_BLACK);
        delay(150);

        // Tegn HELP-skærmen igen og luk popup
        showHelpScreen();
        aiPopupActive = false;
      }

      delay(10);
      return;
    }

    // AI-HELPER → åbn popup
    if (pointInButton(btnHelpAI, x, y)) {
      drawButton(btnHelpAI, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
      delay(150);
      drawButton(btnHelpAI, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

      showAIPopup();   // åbner "Coming soon..."-boksen
      delay(10);
      return;
    }

    // FAQ → gå til FAQ-skærm
    if (pointInButton(btnHelpFAQ, x, y)) {
      drawButton(btnHelpFAQ, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
      delay(150);
      drawButton(btnHelpFAQ, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

      showFAQScreen();   // ← NYT: tegn FAQ-siden
      delay(10);
      return;
    }

    // Tilbage → tilbage til forsiden (nulstiller onHelpScreen i drawUI)
    if (pointInButton(btnHelpBack, x, y)) {
      drawButton(btnHelpBack, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
      delay(150);
      drawUI();
    }

    delay(10);
    return;
  }

  // 1.5) Hvis vi ER på FAQ-skærmen
  if (onFAQScreen) {
    // Tilbage fra FAQ → tilbage til HELP-skærm
    if (pointInButton(btnFAQBack, x, y)) {
      drawButton(btnFAQBack, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
      delay(150);

      showHelpScreen();      // tilbage til HELP
      onFAQScreen = false;   // (showHelpScreen sætter onHelpScreen = true)
    }

    delay(10);
    return;
  }

  // 2) Hvis vi ER på instruktionsskærmen → kun "Tilbage" virker
  if (onInstructionsScreen) {
    if (pointInButton(btnBack, x, y)) {
      // Lille visuel feedback på knappen (valgfrit)
      drawButton(btnBack, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
      delay(150);
      // Tilbage til forsiden
      drawUI();
    }

    delay(10);
    return;
  }

  // 3) Ellers: vi er på forsiden med START / HELP / INSTRUCTIONS

  // START → må bruge ESP-NOW
  if (pointInButton(btnStart, x, y)) {
    drawButton(btnStart, COLOR_WHITE, COLOR_CYAN, COLOR_BLACK);
    sendCommand("START");
    delay(150);
     // I stedet for at tegne knappen tilbage → skift til maale-skærm
    showMeasuringScreen();
  }

  // HJÆLP → åbner HELP-skærm (ingen ESP-NOW)
  if (pointInButton(btnHelp, x, y)) {
    drawButton(btnHelp, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
    delay(150);
    drawButton(btnHelp, COLOR_NAVY, COLOR_CYAN, COLOR_WHITE);

    showHelpScreen();  // gå til HELP-skærm
  }

  // INSTRUKTION → KUN UI, INGEN ESP-NOW
  if (pointInButton(btnManual, x, y)) {
    drawButton(btnManual, COLOR_CYAN, COLOR_WHITE, COLOR_BLACK);
    delay(150);

    // Vis instruktions-billedet med "Tilbage"-knap
    showInstructions();
  }

  delay(10);
}



