# SuperGuard Alarm — Evolution Plan

## Part 1: Multi-Device Actuator Support

### Current State
- Single Tuya Smart Plug (tinytuya 3.4, local key, port 6668)
- Hardcoded in `panic_mode.py` → `plug_ip`, `plug_key`, `device_id`
- One relay (DPS 1), power monitoring (DPS 20/22/23)

### Target Architecture: Plugin-Based Device Abstraction

```
panic_mode.py
    │
    ├── AlarmEngine (unchanged)
    │   ├── detection_loop()
    │   ├── trigger_alarm()
    │   └── stop_alarm()
    │
    └── ActuatorRegistry (NEW)
        │
        ├── BaseActuator (ABC)
        │   ├── async turn_on()
        │   ├── async turn_off()
        │   ├── async get_status()
        │   └── async get_power()
        │
        ├── TuyaActuator (current, refactored)
        ├── SonoffActuator (NEW)
        ├── ShellyActuator (NEW)
        ├── TasmotaActuator (NEW)
        ├── ESPHomeActuator (NEW)
        ├── ZigbeeActuator (NEW)
        ├── MatterActuator (NEW)
        └── DIYActuator (NEW - Kincony/Waveshare/ESP32)
```

### Device Protocol Matrix

| Device Family | Protocol | Library | Cost/Relay | Power Monitoring | Local Only |
|--------------|----------|---------|------------|------------------|------------|
| **Tuya** | tinytuya 3.4/3.5 | `tinytuya` | $15-25 | ✅ DPS 20/22/23 | ✅ Local key |
| **Sonoff (Tasmota)** | MQTT/HTTP | `paho-mqtt`/`aiohttp` | $8-18 | ✅ (Pow) | ✅ |
| **Sonoff (Stock)** | eWeLink LAN | `ewelink-api` | $8-18 | ✅ (Pow) | ⚠️ Cloud fallback |
| **Shelly (Gen1)** | CoAP/HTTP/MQTT | `aiohttp`/`aiocoap` | $12-20 | ✅ (PM) | ✅ |
| **Shelly Plus** | WS/MQTT/HTTP | `aiohttp`/`websockets` | $18-22 | ✅ (PM) | ✅ |
| **Tasmota (Generic)** | MQTT/HTTP/WS | `paho-mqtt`/`aiohttp` | $3-15 | ✅ | ✅ |
| **ESPHome** | Native API/MQTT | `aioesphomeapi` | $3-15 | ✅ | ✅ |
| **Zigbee (Z2M)** | MQTT | `paho-mqtt` | $15-22 | ❌ | ✅ (via coordinator) |
| **Matter/Thread** | Matter | `matter-python` | $25-35 | ✅ | ✅ |
| **Kincony KC868** | HTTP/MQTT/KCS | `aiohttp`/`paho-mqtt` | $6-20/relay | ❌ | ✅ |
| **ESP32 DIY** | Custom/MQTT/HTTP | Custom | $5-12 | Optional | ✅ |

### Implementation Phases

#### Phase 1: Abstraction Layer (Week 1-2)
- [ ] Create `actuators/__init__.py` with `BaseActuator` ABC
- [ ] Refactor current Tuya code into `TuyaActuator` class
- [ ] Add `ActuatorRegistry` singleton with `register()` / `get()` / `list()`
- [ ] Config-driven actuator selection in `sguard.env`:
  ```bash
  ACTUATOR_TYPE=tuya|sonoff_tasmota|shelly|tasmota|esphome|zigbee|matter|kincony|custom
  ACTUATOR_CONFIG={"ip": "...", "key": "...", "mqtt_host": "...", ...}
  ```

#### Phase 2: Sonoff/Tasmota Support (Week 2-3)
- [ ] `SonoffActuator` — MQTT (`cmnd/stat/tele` topics) + HTTP fallback
- [ ] `TasmotaActuator` — generic for any Tasmota device
- [ ] Auto-discovery via mDNS (`sonoff-*.local`) + MQTT `tele/+/LWT`
- [ ] Support: Basic, Mini, Dual, Pow, SV, TH, 4CH, Touch

#### Phase 3: Shelly Support (Week 3-4)
- [ ] `ShellyActuator` — Gen1 (CoAP/HTTP) + Plus (WS/MQTT)
- [ ] Native RPC over WebSocket for Plus series
- [ ] Power monitoring via `/rpc/Shelly.GetStatus`
- [ ] Auto-discovery via mDNS (`shellyplus1-*.local`)

#### Phase 4: ESPHome / Generic Tasmota (Week 4-5)
- [ ] `ESPHomeActuator` — native API (protobuf) + MQTT fallback
- [ ] `GenericTasmotaActuator` — any device with Tasmota
- [ ] Berry scripting support for custom logic

#### Phase 5: Zigbee / Matter / Thread (Week 5-6)
- [ ] `ZigbeeActuator` — via Zigbee2MQTT MQTT topics
- [ ] `MatterActuator` — via `matter-python` (Thread border router needed)
- [ ] Auto-discovery via Z2M/ZHA/Matter controller

#### Phase 6: DIY / Industrial (Week 6-7)
- [ ] `KinconyActuator` — KC868-A4/A8/A16/A32 (HTTP/MQTT/KCS)
- [ ] `WaveshareActuator` — Relay HATs for Pi/ESP32
- [ ] `CustomActuator` — plugin interface for user scripts

#### Phase 7: Unified Config & UI (Week 7-8)
- [ ] `actuators.yaml` — declarative device definitions
- [ ] Telegram `/actuator` command: list, test, status, power
- [ ] Web UI (FastAPI) for actuator management
- [ ] Health checks + auto-reconnect

---

## Part 2: WhatsApp Integration

### Current State
- Telegram-only via `requests` + long-poll
- Commands: `/autoguard`, `/togglealarm`, `/zone`, `/target`, `/setlocal`
- Messages: trigger photo (msg A), live frame (msg B), status updates

### WhatsApp Options Comparison

| Approach | Library/Service | Cost | Pros | Cons |
|----------|----------------|------|------|------|
| **WhatsApp Business API (Cloud)** | Official Meta | Free tier 1000 conv/mo | Official, reliable, templates | Requires Meta verification, webhook HTTPS |
| **WhatsApp Business API (BSP)** | Twilio, 360dialog, Vonage | $0.005-0.03/msg | Managed, support | More expensive |
| **whatsapp-web.js** | Puppeteer + Web WhatsApp | Free | No approval needed | Unstable, QR login, can break |
| **GoWhatsApp / Whatsmeow** | Go library (linked devices) | Free | Multi-device, stable | Go dependency, complex |
| **PyWhatsApp / whatsapp-api** | Python wrappers | Free | Python native | Maintenance varies |
| **Signal (Alternative)** | `signal-cli` / `signald` | Free | Privacy, open | Smaller user base |

### Recommended: Dual-Channel Architecture

```
MessageDispatcher (NEW)
    │
    ├── TelegramChannel (existing)
    │   ├── long-poll / webhook
    │   ├── send_photo()
    │   ├── send_text()
    │   └── edit_message()
    │
    └── WhatsAppChannel (NEW)
        ├── Cloud API (webhook) — PRIMARY
        │   ├── send_image()
        │   ├── send_text()
        │   └── template_messages()
        │
        └── Fallback: whatsapp-web.js / GoWhatsApp
            (if Cloud API not available)
```

### WhatsApp Cloud API Implementation

#### Prerequisites
- Meta Developer Account → WhatsApp Business API
- Phone number verification
- Webhook HTTPS endpoint (ngrok for dev, real domain for prod)
- `VERIFY_TOKEN` + `APP_SECRET`

#### Webhook Endpoint (FastAPI)
```python
# POST /webhook/whatsapp
# GET  /webhook/whatsapp?hub.mode=subscribe&hub.challenge=...&hub.verify_token=...
```

#### Message Templates (Required for outbound)
| Template | Variables | Language |
|----------|-----------|----------|
| `alarm_trigger` | `{{1}}`=target, `{{2}}`=zone, `{{3}}`=time | en/ru/es |
| `alarm_live` | `{{1}}`=frame_id | en/ru/es |
| `alarm_resolved` | `{{1}}`=duration | en/ru/es |
| `status_update` | `{{1}}`=mode, `{{2}}`=zone, `{{3}}`=target | en/ru/es |
| `command_confirm` | `{{1}}`=command, `{{2}}`=result | en/ru/es |

#### Command Mapping (WhatsApp → Internal)
| WhatsApp Input | Internal Command |
|----------------|------------------|
| `авто` / `auto` / `autoguard` | `/autoguard` |
| `тревога` / `alarm` / `togglealarm` | `/togglealarm` |
| `зона N3x4 C9` / `zone N3x4 C9` | `/zone N3x4 C9` |
| `цель красная машина` / `target red car` | `/target red car` |
| `язык ru` / `lang en` / `idioma es` | `/setlocal` |
| `статус` / `status` | Custom: return current mode |

#### Media Handling
- **Trigger photo (msg A)** → `POST /messages` with `type=image`, `link=<url>` (upload to media endpoint first)
- **Live frame (msg B)** → Same, but with `caption="Live frame"` + auto-delete via `DELETE /messages/{id}` after 2s
- **Max file size**: 16 MB (images), 64 MB (video)

#### Multi-Language Support
- Same `tr()` i18n dict → WhatsApp template variables
- User language stored in `sguard_settings.json` (`lang` field)
- Template selection: `alarm_trigger_ru`, `alarm_trigger_en`, `alarm_trigger_es`

### Implementation Phases

#### Phase 1: Core Abstraction (Week 1)
- [ ] Create `channels/__init__.py` with `BaseChannel` ABC
- [ ] Refactor Telegram into `TelegramChannel` class
- [ ] Add `MessageDispatcher` with `register_channel()` / `dispatch()`
- [ ] Config: `CHANNELS=telegram,whatsapp`

#### Phase 2: WhatsApp Cloud API (Week 2-3)
- [ ] `WhatsAppChannel` class with:
  - Webhook verification (`GET /webhook`)
  - Inbound message parsing (text, image, button reply)
  - Outbound: `send_text()`, `send_image()`, `send_template()`
  - Media upload: `POST /media` → returns `media_id`
- [ ] Template management: create via Meta Console, store IDs in config
- [ ] Signature verification: `X-Hub-Signature-256` HMAC

#### Phase 3: Feature Parity (Week 3-4)
- [ ] Command router: WhatsApp text → internal command
- [ ] Trigger photo + live frame (msg A/B) via WhatsApp
- [ ] Auto-delete live frame (2s) via `DELETE /messages/{id}`
- [ ] Status updates (auto-resolve, manual alarm, zone/target changes)
- [ ] Language switch via WhatsApp (`язык ru` / `lang en` / `idioma es`)

#### Phase 4: Reliability & Polish (Week 4-5)
- [ ] Webhook retry logic (exponential backoff)
- [ ] Rate limiting (WhatsApp: 80 msg/s burst, 1000/day free tier)
- [ ] Fallback to `whatsapp-web.js` if Cloud API unavailable
- [ ] Health check endpoint for both channels
- [ ] Logging + metrics (delivery status: sent/delivered/read/failed)

#### Phase 5: Unified Management (Week 5-6)
- [ ] Telegram `/channel` command: list, test, enable/disable
- [ ] WhatsApp: reply with button list (interactive messages)
- [ ] Web UI: channel status, message history, template management
- [ ] Per-user preferences (which channel for alerts)

---

## Part 3: Unified Configuration Schema

### `sguard.env` (Secrets)
```bash
# Telegram (existing)
SG_TELEGRAM_BOT_TOKEN=...
SG_CHAT_ID=...

# WhatsApp (NEW)
WA_CLOUD_API_TOKEN=...
WA_PHONE_NUMBER_ID=...
WA_VERIFY_TOKEN=...
WA_APP_SECRET=...
WA_TEMPLATE_ALARM_TRIGGER=...
WA_TEMPLATE_ALARM_LIVE=...
WA_TEMPLATE_ALARM_RESOLVED=...
WA_TEMPLATE_STATUS=...
WA_TEMPLATE_COMMAND=...

# Actuator (NEW)
ACTUATOR_TYPE=tuya|sonoff_tasmota|shelly|tasmota|esphome|zigbee|matter|kincony|custom
ACTUATOR_CONFIG={"ip": "192.168.x.x", "key": "...", "mqtt_host": "..."}

# Channels
CHANNELS=telegram,whatsapp
```

### `actuators.yaml` (Declarative)
```yaml
devices:
  - id: plug_main
    type: tuya
    name: "Main Plug"
    config:
      ip: "192.168.137.109"
      local_key: "xxx"
      device_id: "bfd23bfc0bdd93b6904c3s"
    channels: [telegram, whatsapp]
    default: true

  - id: light_zone1
    type: sonoff_tasmota
    name: "Zone 1 Light"
    config:
      mqtt_topic: "cmnd/zone1_light"
      mqtt_host: "192.168.137.50"
    channels: [telegram]

  - id: siren_esp32
    type: custom
    name: "ESP32 Siren"
    config:
      script: "actuators/custom/siren.py"
    channels: [telegram, whatsapp]
```

### `channels.yaml` (Declarative)
```yaml
telegram:
  enabled: true
  bot_token: "${SG_TELEGRAM_BOT_TOKEN}"
  chat_id: "${SG_CHAT_ID}"
  features:
    - commands
    - photos
    - live_frames
    - inline_keyboards

whatsapp:
  enabled: true
  provider: cloud_api  # or webjs
  phone_number_id: "${WA_PHONE_NUMBER_ID}"
  token: "${WA_CLOUD_API_TOKEN}"
  verify_token: "${WA_VERIFY_TOKEN}"
  app_secret: "${WA_APP_SECRET}"
  templates:
    alarm_trigger: "alarm_trigger_{{lang}}"
    alarm_live: "alarm_live_{{lang}}"
    alarm_resolved: "alarm_resolved_{{lang}}"
    status: "status_{{lang}}"
    command: "command_{{lang}}"
  features:
    - commands
    - photos
    - live_frames
    - templates
    - interactive_buttons
```

---

## Part 4: Migration Strategy (Non-Breaking)

### v1.1 — Actuator Abstraction (Backward Compatible)
- TuyaActuator = current behavior exactly
- Config fallback: if `ACTUATOR_TYPE` not set → Tuya
- All existing tests pass

### v1.2 — Multi-Actuator + Telegram Refactor
- TelegramChannel extracted
- MessageDispatcher introduced
- `/actuator` command added
- Zero config change for existing users

### v1.3 — WhatsApp Cloud API (Opt-in)
- `CHANNELS=telegram,whatsapp` enables
- Templates created via Meta Console (one-time)
- Fallback: if WhatsApp fails → log + continue Telegram only

### v1.4 — Web UI + Declarative Config
- FastAPI + React/HTMX frontend
- `actuators.yaml` / `channels.yaml` hot-reload
- Per-user channel preferences

---

## Part 5: Testing Matrix

| Component | Unit Tests | Integration Tests | Hardware Tests |
|-----------|------------|-------------------|----------------|
| TuyaActuator | ✅ Mock tinytuya | ✅ Real plug | ✅ Nivian |
| SonoffActuator | ✅ Mock MQTT | ✅ Tasmota device | 🔲 |
| ShellyActuator | ✅ Mock HTTP/WS | ✅ Shelly Plus | 🔲 |
| TasmotaActuator | ✅ Generic | ✅ Any Tasmota | 🔲 |
| ESPHomeActuator | ✅ Mock API | ✅ ESPHome device | 🔲 |
| ZigbeeActuator | ✅ Mock Z2M | ✅ Z2M + ZBMINI | 🔲 |
| WhatsAppChannel | ✅ Mock API | ✅ Meta test number | 🔲 |
| MessageDispatcher | ✅ Routing | ✅ Dual channel | 🔲 |

---

## Part 6: Estimated Timeline

| Phase | Weeks | Deliverable |
|-------|-------|-------------|
| 1. Actuator Abstraction | 2 | `actuators/` package, Tuya refactor |
| 2. Sonoff/Tasmota | 2 | Sonoff + Generic Tasmota support |
| 3. Shelly | 1 | Gen1 + Plus support |
| 4. ESPHome/Zigbee/Matter | 2 | ESPHome, Z2M, Matter |
| 5. DIY/Kincony | 1 | KC868, ESP32 DIY |
| 6. WhatsApp Core | 2 | Cloud API, templates, webhook |
| 7. WhatsApp Features | 2 | Commands, photos, live, i18n |
| 8. Unified Config/UI | 2 | YAML config, web UI, health |
| **Total** | **14** | **Production-ready multi-device, multi-channel** |

---

## Part 7: Immediate Next Steps (This Week)

1. **Create `actuators/` package structure**
   ```bash
   mkdir -p actuators channels
   touch actuators/__init__.py channels/__init__.py
   ```

2. **Extract `BaseActuator` ABC** from current Tuya code

3. **Create `TuyaActuator` class** — exact current behavior

4. **Add `ACTUATOR_TYPE` env var** with fallback to `tuya`

5. **Test** — verify zero behavior change

6. **Create `github-perfectfriend-push` skill** already done ✅

7. **Document** in `docs/ACTUATORS.md` and `docs/WHATSAPP.md`

---

## Appendix: Useful Links

- **Sonoff Tasmota MQTT**: https://tasmota.github.io/docs/MQTT/
- **Shelly API**: https://shelly-api-docs.shelly.cloud/
- **ESPHome Native API**: https://esphome.io/components/api.html
- **Zigbee2MQTT**: https://www.zigbee2mqtt.io/
- **Matter Python**: https://github.com/project-chip/connectedhomeip
- **WhatsApp Cloud API**: https://developers.facebook.com/docs/whatsapp/cloud-api
- **WhatsApp Templates**: https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates
- **tinytuya**: https://github.com/jasonacox/tinytuya
- **Kincony KC868**: https://www.kincony.com/