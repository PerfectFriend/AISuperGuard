# INTEGRATION PLAN: SuperGuard Legacy → New API

## Phase 1: Core Services (Week 1)
- [ ] DetectionEngine service (YOLO pipeline в background task)
- [ ] CameraManager service (интеграция superguard/cameras)
- [ ] ActuatorManager service (интеграция superguard/actuators + API endpoints)
- [ ] AlarmEngine service (concurrent alarms, auto-resolve, actuator binding)

## Phase 2: Telegram Bot v2 (Week 1-2)
- [ ] Async Telegram bot на python-telegram-bot v20+
- [ ] Modern inline keyboard UI (меню, зоны, таргеты, камеры, розетки)
- [ ] Webhook mode (или long-poll) + интеграция с API через HTTP
- [ ] Alarm notifications с annotated frames + live updates
- [ ] Commands: /menu, /zone, /target, /cam, /plug, /alarm, /status

## Phase 3: API Extensions (Week 1)
- [ ] POST /cameras/{id}/stream - HLS/WebRTC proxy
- [ ] POST /actuators/{id}/control - ON/OFF/STATUS
- [ ] GET /alarms/active - список активных тревог
- [ ] WS events: detection.stats, alarm.triggered, actuator.status
- [ ] Camera zones/ROI CRUD

## Phase 4: React UI (Week 2)
- [ ] Camera card с встроенным плеером + зоной (canvas overlay)
- [ ] Actuator cards с real-time статусом + power
- [ ] Alarm timeline с annotated frames
- [ ] Settings modal для zone/target/actuator binding
- [ ] Guard Map с live маркерами

## Phase 5: Polish (Week 2)
- [ ] Backup/restore (pg_dump + settings)
- [ ] Prometheus metrics
- [ ] systemd units для всех сервисов
- [ ] Health checks для каждого компонента
