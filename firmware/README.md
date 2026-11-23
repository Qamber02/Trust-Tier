# TrustTier ESP32 badge setup

These steps are for the **ESP32-WROOM-32 DevKit (30-pin, HW-463)** and the exact RC522 + DS1302 pins defined in `include/pins.h`. Do not change pin mappings. On this board the printed D number is the GPIO number.

## Required software and libraries

1. Install Arduino IDE 2.x.
2. In **File → Preferences → Additional boards manager URLs**, add Espressif's stable package index:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. Open **Tools → Board → Boards Manager**, install **esp32 by Espressif Systems 3.3.12**, then select **ESP32 Dev Module**.
4. In **Sketch → Include Library → Manage Libraries**, install:
   - **MFRC522** by **GithubCommunity** (RC522 SPI reader)
   - **Rtc** by **Makuna** (DS1302 support through `RtcDS1302.h`; this package includes `ThreeWire`)
   - **ArduinoJson** by **Benoit Blanchon**, version 7.x
   - **Crypto** by **Rhys Weatherley** (the `Ed25519.h` signing implementation)

`Arduino.h`, `SPI.h`, `WiFi.h`, `HTTPClient.h`, `LittleFS.h`, and ESP32's `mbedtls/sha256.h` come from the board core; do not install separate RTC/I²C alternatives. This project uses neither DS3231 nor RTClib.

## Fixed wiring

| Module | Signal | ESP32 pin |
|---|---|---:|
| RC522 | SDA / SS / CS | GPIO 5 (D5) |
| RC522 | SCK | GPIO 18 (D18) |
| RC522 | MOSI | GPIO 23 (D23) |
| RC522 | MISO | GPIO 19 (D19) |
| RC522 | RST | GPIO 22 (D22) |
| RC522 | 3.3V / GND | 3V3 / GND |
| RC522 | IRQ | Not connected |
| DS1302 | CLK | GPIO 27 (D27) |
| DS1302 | DAT | GPIO 26 (D26) |
| DS1302 | RST | GPIO 25 (D25) |
| DS1302 | VCC / GND | 3V3 / GND |

The sketch includes `pins.h` and initializes SPI with `SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_SS)`. No I²C device is used. Do not connect or remap other pins.

## Provisioning and upload

1. Start the FastAPI service on the development computer, reachable from the ESP32 over the same Wi-Fi network. Set the firmware API URL to the computer's LAN address—not `127.0.0.1`—and use the same server API key.
2. From the repository root, register a device and generate its keypair (the script reads `TRUSTTIER_API_KEY` from `.env`):

   ```powershell
   python tools/provision_badge.py --url http://<COMPUTER-LAN-IP>:8000 --device ESP32-RDR-025 --worker RDR-025 --output badge-private-key.json
   ```

3. Copy `firmware/include/secrets.example.h` to `firmware/include/secrets.h`. Fill in Wi-Fi SSID/password, the reachable API URL, API key, the exact registered device ID, worker/client IDs, and the `private_key_hex` value from the generated JSON file. The private key is 64 hexadecimal characters. Keep both secret files private; never commit or send the private key to Supabase.
4. Open `firmware/arduino/TrustTierBadge/TrustTierBadge.ino` in Arduino IDE. It includes the shared source in `firmware/src/`. Confirm board **ESP32 Dev Module**, select the connected COM port, then compile and upload.
5. Use the IDE compile output for diagnostics. Do not use GPIO 1 or 3 for serial debugging; this firmware intentionally does not initialize USB serial.

## Runtime behavior and test boundary

Each detected RC522 tag scan advances the local demo sequence `arrive → start → finish`; it buffers signed events in LittleFS and posts the batch when Wi-Fi is available. The DS1302 supplies timestamps. This starter firmware currently has no per-job selection UI, so generated firmware events have `job_id: null`; the rider app's job lifecycle is separately linked to customer-created jobs through the API. A real badge tap and an app workflow action are different records and must not be treated as interchangeable proof.

The Python badge simulator tests API signing, chaining, offline batch upload, and tamper rejection. Arduino CLI/PlatformIO and a physical ESP32 + RC522 + DS1302 have not been available for validation here. Compile with the versions above, check actual module operation, and perform supervised hardware tests before relying on it in the field.
