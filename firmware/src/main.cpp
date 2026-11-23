#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <SPI.h>
#include <MFRC522.h>
#include <ThreeWire.h>
#include <RtcDS1302.h>
#include <ArduinoJson.h>
#include <mbedtls/sha256.h>
#include <Ed25519.h>
#include "pins.h"
#include "secrets.h"

static_assert(sizeof(DEVICE_PRIVATE_KEY_HEX) == 65,
              "Set the provisioned 32-byte Ed25519 private key as 64 hex characters");

MFRC522 rfid(PIN_SS, PIN_RFID_RST);
ThreeWire ds1302Wire(PIN_DS1302_DAT, PIN_DS1302_CLK, PIN_DS1302_RST);
RtcDS1302<ThreeWire> rtc(ds1302Wire);
const char *LOG_PATH = "/events.jsonl";
const char *CHAIN_PATH = "/chain.hash";
String tailHash;
uint8_t nextStep = 0;
const char *eventTypes[] = {"arrive", "start", "finish"};

String hex(const uint8_t *p, size_t n) {
  const char *digits = "0123456789abcdef"; String out; out.reserve(n * 2);
  for (size_t i=0;i<n;i++) { out += digits[p[i] >> 4]; out += digits[p[i] & 15]; }
  return out;
}
String b64(const uint8_t *p, size_t n) {
  static const char *t="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  String out; for(size_t i=0;i<n;i+=3){uint32_t v=(uint32_t)p[i]<<16;if(i+1<n)v|=(uint32_t)p[i+1]<<8;if(i+2<n)v|=p[i+2];out+=t[(v>>18)&63];out+=t[(v>>12)&63];out+=(i+1<n)?t[(v>>6)&63]:'=';out+=(i+2<n)?t[v&63]:'=';} return out;
}
String timestampUtc() {
  const RtcDateTime now = rtc.GetDateTime();
  char out[25];
  snprintf(out, sizeof(out), "%04u-%02u-%02uT%02u:%02u:%02uZ",
           now.Year(), now.Month(), now.Day(), now.Hour(), now.Minute(), now.Second());
  return String(out);
}
String canonical(String id, String type, String tier, String ts, String prev) {
  // Sorted keys, matching tools/badge_simulator.py / trusttier_live.py canonical JSON.
  return "{\"client_id\":\"" CLIENT_ID "\",\"device_id\":\"" DEVICE_ID "\",\"device_ts\":\"" + ts +
    "\",\"evidence_tier\":\"" + tier + "\",\"id\":\"" + id + "\",\"job_id\":null,\"payload\":{},\"prev_hash\":\"" + prev +
    "\",\"type\":\"" + type + "\",\"worker_id\":\"" WORKER_ID "\"}";
}
bool appendEvent(String type, String tier) {
  String id=String((uint32_t)esp_random(), HEX)+String((uint32_t)esp_random(), HEX);
  String ts=timestampUtc(); String body=canonical(id,type,tier,ts,tailHash);
  uint8_t digest[32]; mbedtls_sha256((const uint8_t*)body.c_str(),body.length(),digest,0);
  String hash=hex(digest,sizeof(digest));
  uint8_t privateKey[32]; for(int i=0;i<32;i++) privateKey[i]=strtoul(String(DEVICE_PRIVATE_KEY_HEX).substring(i*2,i*2+2).c_str(),nullptr,16);
  uint8_t sig[64]; Ed25519::sign(sig,(const uint8_t*)hash.c_str(),hash.length(),privateKey);
  JsonDocument doc; deserializeJson(doc,body); doc["hash"]=hash; doc["signature"]=b64(sig,sizeof(sig));
  String line; serializeJson(doc,line); File file=LittleFS.open(LOG_PATH,"a"); if(!file)return false;
  file.println(line); file.close(); tailHash=hash;
  File chain=LittleFS.open(CHAIN_PATH,"w"); if(chain){chain.print(tailHash);chain.close();}
  return true;
}
bool readTag() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return false;
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  return true;
}
void syncLog() {
  if(WiFi.status()!=WL_CONNECTED || !LittleFS.exists(LOG_PATH)) return;
  File file=LittleFS.open(LOG_PATH,"r"); String batch="["; bool first=true;
  while(file.available()){String row=file.readStringUntil('\n'); if(row.length()){if(!first)batch+=",";batch+=row;first=false;}} file.close(); batch+="]";
  if(first)return;
  HTTPClient http; http.begin(String(TRUSTTIER_API)+"/api/sync"); http.addHeader("Content-Type","application/json"); http.addHeader("X-API-Key",TRUSTTIER_API_KEY);
  String request="{\"events\":"+batch+"}"; int status=http.POST(request);
  if(status>=200 && status<300){LittleFS.remove(LOG_PATH);}
  http.end();
}
void setup(){
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_SS);
  rfid.PCD_Init();
  rtc.Begin();
  if (!rtc.IsDateTimeValid()) rtc.SetDateTime(RtcDateTime(__DATE__, __TIME__));
  if(!LittleFS.begin(true)) return;
  if (LittleFS.exists(CHAIN_PATH)) {
    File chain=LittleFS.open(CHAIN_PATH,"r");
    if(chain){tailHash=chain.readString();tailHash.trim();chain.close();}
  }
  WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
}
void loop(){
  if(readTag()){
    const String tier = nextStep == 0 ? "nfc" : "signed";
    if (appendEvent(eventTypes[nextStep], tier)) nextStep = (nextStep + 1) % 3;
    delay(1200);
  }
  if(WiFi.status()==WL_CONNECTED) syncLog();
  delay(100);
}
