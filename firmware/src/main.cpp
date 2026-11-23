#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Wire.h>
#include <Adafruit_PN532.h>
#include <ArduinoJson.h>
#include <mbedtls/sha256.h>
#include <mbedtls/ed25519.h>
#include "secrets.h"

// PN532 I2C: SDA=21, SCL=22; IRQ=4, RESET=5. RTC is the ESP32's battery-backed
// system clock (synchronize with NTP when online). Optional MPU6050 uses I2C bus.
Adafruit_PN532 nfc(4, 5);
const char *LOG_PATH = "/events.jsonl";
String tailHash;

String hex(const uint8_t *p, size_t n) {
  const char *digits = "0123456789abcdef"; String out; out.reserve(n * 2);
  for (size_t i=0;i<n;i++) { out += digits[p[i] >> 4]; out += digits[p[i] & 15]; }
  return out;
}
String b64(const uint8_t *p, size_t n) {
  static const char *t="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  String out; for(size_t i=0;i<n;i+=3){uint32_t v=(uint32_t)p[i]<<16;if(i+1<n)v|=(uint32_t)p[i+1]<<8;if(i+2<n)v|=p[i+2];out+=t[(v>>18)&63];out+=t[(v>>12)&63];out+=(i+1<n)?t[(v>>6)&63]:'=';out+=(i+2<n)?t[v&63]:'=';} return out;
}
String eventType="arrive";
String canonical(String id, String type, String tier, String ts, String prev) {
  // Sorted keys, matching tools/badge_simulator.py / trusttier_live.py canonical JSON.
  return "{\"client_id\":\"" CLIENT_ID "\",\"device_id\":\"" DEVICE_ID "\",\"device_ts\":\"" + ts +
    "\",\"evidence_tier\":\"" + tier + "\",\"id\":\"" + id + "\",\"job_id\":null,\"payload\":{},\"prev_hash\":\"" + prev +
    "\",\"type\":\"" + type + "\",\"worker_id\":\"" WORKER_ID "\"}";
}
bool appendEvent(String type, String tier) {
  String id=String((uint32_t)esp_random(), HEX)+String((uint32_t)esp_random(), HEX);
  String ts=String((uint64_t)time(nullptr)); String body=canonical(id,type,tier,ts,tailHash);
  uint8_t digest[32]; mbedtls_sha256((const uint8_t*)body.c_str(),body.length(),digest,0);
  String hash=hex(digest,sizeof(digest));
  uint8_t privateKey[32]; for(int i=0;i<32;i++) privateKey[i]=strtoul(String(DEVICE_PRIVATE_KEY_HEX).substring(i*2,i*2+2).c_str(),nullptr,16);
  uint8_t sig[64]; size_t sigLen=sizeof(sig);
  if(mbedtls_ed25519_sign(privateKey,digest,sizeof(digest),sig,&sigLen)!=0) return false;
  JsonDocument doc; deserializeJson(doc,body); doc["hash"]=hash; doc["signature"]=b64(sig,sigLen);
  String line; serializeJson(doc,line); File file=LittleFS.open(LOG_PATH,"a"); if(!file)return false;
  file.println(line); file.close(); tailHash=hash; Serial.println("Buffered signed event: "+line); return true;
}
void syncLog() {
  if(WiFi.status()!=WL_CONNECTED || !LittleFS.exists(LOG_PATH)) return;
  File file=LittleFS.open(LOG_PATH,"r"); String batch="["; bool first=true;
  while(file.available()){String row=file.readStringUntil('\n'); if(row.length()){if(!first)batch+=",";batch+=row;first=false;}} file.close(); batch+="]";
  if(first)return;
  HTTPClient http; http.begin(String(TRUSTTIER_API)+"/api/sync"); http.addHeader("Content-Type","application/json"); http.addHeader("X-API-Key",TRUSTTIER_API_KEY);
  String request="{\"events\":"+batch+"}"; int status=http.POST(request);
  if(status>=200 && status<300){LittleFS.remove(LOG_PATH);Serial.println("Synced; server acknowledged batch.");}else Serial.printf("Sync deferred (HTTP %d); will retry.\n",status);
  http.end();
}
void setup(){
  Serial.begin(115200); Wire.begin(21,22); if(!LittleFS.begin(true)){Serial.println("LittleFS mount failed");return;}
  nfc.begin(); nfc.SAMConfig(); WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  Serial.println("TrustTier badge ready; waiting for NFC / network...");
}
void loop(){
  uint8_t uid[7]; uint8_t uidLength;
  if(nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A,uid,&uidLength,100)){
    appendEvent("arrive","nfc"); delay(1200);
  }
  if(WiFi.status()==WL_CONNECTED) syncLog();
  delay(100);
}
