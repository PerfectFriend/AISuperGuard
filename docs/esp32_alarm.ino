/*
 * ESP32 Alarm Actuator — прожектор + сирена по WiFi-сигналу.
 *
 * Схема:
 *   GPIO2 -> реле 1 -> прожектор (220V через реле!)
 *   GPIO4 -> реле 2 -> сирена
 *
 * Прошивка: Arduino IDE + ESP32 board package.
 * Установите свой SSID/пароль ниже.
 * После загрузки: http://<ip>/on  — включить, http://<ip>/off — выключить.
 *
 * ВНИМАНИЕ: работа с 220V — только через модули реле с гальванической
 * развязкой. Не подключайте сеть напрямую к GPIO.
 */

#include <WiFi.h>
#include <WebServer.h>

const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

const int RELAY_FLOODLIGHT = 2;  // прожектор
const int RELAY_SIREN = 4;       // сирена

WebServer server(80);

void setAlarm(bool on) {
  digitalWrite(RELAY_FLOODLIGHT, on ? HIGH : LOW);
  digitalWrite(RELAY_SIREN, on ? HIGH : LOW);
  Serial.printf("Alarm: %s\n", on ? "ON" : "OFF");
}

void handleOn() {
  setAlarm(true);
  server.send(200, "text/plain", "ALARM ON");
}

void handleOff() {
  setAlarm(false);
  server.send(200, "text/plain", "ALARM OFF");
}

void handleStatus() {
  String s = String("{\"alarm\":") + (digitalRead(RELAY_FLOODLIGHT) ? "true" : "false") + "}";
  server.send(200, "application/json", s);
}

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_FLOODLIGHT, OUTPUT);
  pinMode(RELAY_SIREN, OUTPUT);
  setAlarm(false);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWiFi connected. IP: http://%s\n", WiFi.localIP().toString().c_str());

  server.on("/on", handleOn);
  server.on("/off", handleOff);
  server.on("/status", handleStatus);
  server.begin();
}

void loop() {
  server.handleClient();
}
