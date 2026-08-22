# SuperGuard Evolution Plan to RC Release

**Current State:** Phase 1 security fixes applied (2026-08-22)
**Target:** Release Candidate (RC) with full production readiness
**Git:** Local + flash drive `/run/media/thomas/1c23f291-16dd-4af8-a9a9-0460511e75dd/SuperGuard.git`

---

## 📋 Phase 1 — Security Critical (DONE ✅)
- [x] WebSocket JWT auth (`/ws/{site_id}?token=...`)
- [x] RSA keys (RS256), HS256 fallback removed
- [x] Fernet encryption for actuator sensitive fields
- [x] Invite-only registration, admin token management
- [x] RBAC: superuser + site-based admin/operator/viewer
- [x] Audit logging (login, register, invite_create, etc.)
- [x] Admin endpoints: `/admin/invites`, `/admin/audit`

---

## 📋 Phase 2 — Code Hygiene & Cleanup (IN PROGRESS)
- [ ] Remove legacy folders: `--version/`, `-c/`, `-m/`, `web-dashboard-new/`, `.bak/`, `.backup/`, `.backup2/`
- [ ] Remove frozen copies: `superguard_light2/`, `superguard_light3/`, `superguard-flutter/`
- [ ] Deduplicate `yolo11n.pt` (keep 1 copy)
- [ ] Consolidate 3 API clients → 1 (`api.ts`, `api/client.ts`, `api/auth.ts`)
- [ ] Replace `alert()/confirm()` → toast notifications
- [ ] Add error boundaries to Dashboard.tsx
- [ ] Remove hardcoded `ws://localhost:3001` → `VITE_WS_URL`
- [ ] Fill `alembic/` with real migrations
- [ ] Fill `tests/` with pytest + httpx.AsyncClient tests

---

## 📋 Phase 3 — Infrastructure Reliability
- [ ] PostgreSQL + alembic migrations (replace SQLite)
- [ ] Redis pub/sub for WebSocket (fix workers=2 event loss)
- [ ] Rate limiting (slowapi) on auth & mutation routes
- [ ] Refresh token rotation (currently 451 unrevoked tokens)
- [ ] Populate `system_logs` table (currently 0 records)
- [ ] MediaMTX WebRTC/HLS integration (remove mjpeg_stream_server.py, dual_stream_server.py)
- [ ] Docker compose: api + redis + postgres + mediamtx + core
- [ ] CI pipeline: ruff + mypy + pytest + build on push

---

## 📋 Phase 4 — Dashboard Full Functionality
- [ ] System page: Invite token management UI (admin only)
- [ ] System page: Audit log viewer UI (admin only)
- [ ] System page: Real backup/restore (not stubs)
- [ ] System page: Real system logs from journald
- [ ] CameraBindings → use api.ts client (remove hardcoded 8080)
- [ ] Actuators page: validation guard for ActuatorConfig ip field
- [ ] WebSocket reconnection with exponential backoff
- [ ] Request deduplication (React Query / SWR)
- [ ] Error boundaries on all pages
- [ ] PTZ controls UI
- [ ] Detection zones visual editor (not JSON)
- [ ] Alarm media viewer (base64 frames)

---

## 📋 Phase 5 — Core Architecture Unification
- [ ] Single detection service (remove duplicate telegram_bot.py in API)
- [ ] API + bot as clients of detection service
- [ ] Flutter mobile client on top of unified API
- [ ] Push notifications (ntfy/FCM)

---

## 📋 Phase 6 — Testing & Hardening (RC Criteria)
- [ ] ≥70% unit test coverage on core (detection math, zone grid, HSV, alarm state machine)
- [ ] Integration tests: auth→register→login→CRUD→WS-with-token
- [ ] Golden frame detection tests (20-30 fixed frames)
- [ ] 24h memory soak test (no RSS growth)
- [ ] Locust stress on `/ws` and `/alarms`
- [ ] Smoke cron: hourly login, camera ping, actuator test (no ON), log to system_logs
- [ ] Structlog JSON + request-id middleware → Loki/journald
- [ ] mypy --strict on core/schemas, ruff + pre-commit
- [ ] Frontend: strict tsconfig, eslint, vitest hooks, Playwright smoke

---

## 📋 RC Release Checklist ("Конфетка")
- [ ] WS closed with token, RSA keys generated, no secrets in code (grep clean)
- [ ] Registration by invite only, roles enforced, PoC script can't control actuators as regular user
- [ ] CI green: ≥70% core coverage, golden frames stable
- [ ] 24h memory soak clean, smoke cron heartbeats in system_logs
- [ ] `docker compose up` brings full stack in one command
- [ ] No breaking API changes without /api/v2 versioning

---

## 🚀 Immediate Next Steps (This Session)
1. **Git initial commit to flash drive** (remove legacy folders first)
2. **System page UI**: Invite management + Audit viewer (admin-only)
3. **ActuatorConfig validation** (guard against object ip)
4. **WebSocket reconnection** with backoff
5. **Real backup/restore endpoints**
6. **Real system logs endpoint** (journald)
7. **CameraBindings refactor** → api.ts client
8. **Error boundaries** + request deduplication
9. **PostgreSQL migration** + alembic
10. **Redis pub/sub** for WebSocket

---

*Plan created: 2026-08-22 | Agent: Nemotron Ultra | Project: /home/thomas/SuperGuard*