# SuperGuard Dashboard Development Plan

## Overview
Building a comprehensive, production-ready dashboard for SuperGuard Alarm System with full CRUD capabilities for all entities, real-time updates, and beautiful UI using existing banner assets.

## Current State Analysis

### Existing Assets
- **Hero banner**: `/assets/hero.png` (13KB)
- **Vite + React + TypeScript** setup with TanStack Router
- Basic auth flow with JWT (mock)
- TanStack Query for data fetching
- Tailwind CSS for styling
- SuperGuard banner images available

### Backend API Ready (Port 8000)
- Sites CRUD + Dashboard
- Cameras CRUD + Zone config + Discovery + Bindings
- Actuators CRUD + Commands + Bindings
- Detectors CRUD
- Alarms (list, acknowledge, media)
- Notifiers
- System health/metrics
- WebSocket for real-time updates

### Flutter App Reference (More Complete)
- Sites management with full CRUD
- Camera management with zone/target config
- Actuator control
- Alarm handling
- Media gallery

## Development Plan

### Phase 1: Core Infrastructure (Week 1)
- [ ] Setup project structure with proper folder organization
- [ ] Configure API client with TanStack Query + Axios
- [ ] Implement authentication flow (Login, JWT, Refresh)
- [ ] Create layout components (Sidebar, Header, Layout)
- [ ] Setup React Query + Axios interceptors
- [ ] Implement protected routes + Auth context
- [ ] Add Tailwind config with SuperGuard theme colors

### Phase 2: Site Management (Week 1-2)
- [ ] Sites list page with grid/table view
- [ ] Create site modal (name, description, timezone, coordinates)
- [ ] Site detail page with tabs (Overview, Cameras, Actuators, Detectors, Alarms, Media)
- [ ] Site dashboard with health metrics
- [ ] Site settings modal

### Phase 3: Camera Management (Week 2-3)
- [ ] Camera list with live preview thumbnails
- [ ] Camera create/edit modal (RTSP/HLS/ONVIF/JPG)
- [ ] Zone configuration (N×M grid visual editor)
- [ ] Target configuration (classes + HSV color ranges)
- [ ] PTZ controls (if supported)
- [ ] Stream preview with HLS/RTSP/WebRTC
- [ ] Camera health monitoring

### Phase 4: Actuator Control (Week 3)
- [ ] Actuator list with status cards
- [ ] Actuator create/edit (Tuya, Sonoff, Shelly, Tasmota, MQTT, HTTP)
- [ ] Camera-actuator binding matrix
- [ ] Manual control buttons (On/Off/Toggle)
- [ ] Power monitoring display
- [ ] Tuya Cloud integration

### Phase 5: Detection & Alarms (Week 3-4)
- [ ] Detector configuration (YOLO classes, HSV colors, zones)
- [ ] Zone visual editor (N×M grid overlay on stream)
- [ ] Alarm configuration (require_frames, auto_resolve)
- [ ] Alarm history with infinite scroll
- [ ] Alarm detail with annotated frames
- [ ] Acknowledge/Resolve workflow
- [ ] Live frame updates during alarm

### Phase 5: Media Gallery & Alarms History (Week 4)
- [ ] Media grid with infinite scroll
- [ ] Filter by camera, date, alarm state
- [ ] Frame viewer with zoom/pan
- [ ] Download original/annotated
- [ ] Alarm timeline with frames
- [ ] Acknowledge/Resolve actions

### Phase 6: System & Integrations (Week 4-5)
- [ ] Tuya Cloud sync status
- [ ] Notifiers (Telegram, Email, Pushover, Webhook, MQTT)
- [ ] System health dashboard
- [ ] User management + RBAC
- [ ] Settings (Tailscale, Telegram, Timezone)
- [ ] Backup/Restore

### Phase 6: Real-time & Polish (Week 5-6)
- [ ] WebSocket integration for live updates
- [ ] Live frame streaming during alarms
- [ ] Push notifications (Web Push / PWA)
- [ ] Offline support (Service Worker)
- [ ] PWA manifest + icons
- [ ] Dark/Light theme
- [ ] Multi-language (RU/EN/ES)
- [ ] Accessibility (WCAG 2.1)

### Phase 7: Testing & Deploy (Week 6)
- [ ] Unit tests (Vitest)
- [ ] E2E tests (Playwright)
- [ ] Storybook components
- [ ] CI/CD pipeline
- [ ] Docker build
- [ ] Production deploy

## Design System (Based on Existing Assets)

### Color Palette (from hero.png)
- Primary: Deep blue/navy (#0f172a, #1e293b)
- Accent: Amber/gold (#fbbf24, #f59e0b)
- Accent 2: Teal/cyan (#0d9488, #14b8a6)
- Danger: Red (#dc2626, #ef4444)
- Success: Green (#16a34a, #22c55e)
- Warning: Amber (#f59e0b)
- Background: Slate (#0f172a, #1e293b, #334155)
- Text: White (#f8fafc), Muted (#94a3b8)

### Components to Build
1. **Layout**: Sidebar (collapsible), TopBar (user, notifications, theme), Breadcrumbs
2. **DataDisplay**: Tables (sortable, filterable, paginated), Cards, StatCards
3. **Forms**: SiteForm, CameraForm, ActuatorForm, DetectorForm, ZoneEditor
3. **Maps**: Leaflet for site locations
4. **Media**: Grid, Lightbox, VideoPlayer (HLS/RTSP)
5. **Charts**: Recharts for metrics (alarms over time, camera health)

## Technical Stack Decisions
- **State**: TanStack Query + React Context (Auth) + LocalStorage (settings)
- **Forms**: React Hook Form + Zod validation
- **UI**: Headless UI / Radix UI + Tailwind
- **Icons**: Lucide React
- **Charts**: Recharts
- **Maps**: Leaflet + React Leaflet
- **Video**: Custom HLS/RTSP player (HLS.js / WebRTC)

## File Structure
```
src/
├── api/           # Axios instance, endpoints, types
├── components/
│   ├── ui/        # Base components (Button, Card, Modal, Table, Form, etc.)
│   ├── layout/    # Sidebar, Header, Layout, Breadcrumbs
│   ├── forms/     # Form components with React Hook Form
│   ├── data/      # Table, Card, StatCard, Chart, MediaGrid
│   └── maps/      # Leaflet map components
├── features/
│   ├── auth/
│   ├── sites/
│   ├── cameras/
│   ├── actuators/
│   ├── detectors/
│   ├── alarms/
│   ├── media/
│   ├── settings/
│   └── dashboard/
├── hooks/         # Custom hooks
├── lib/           # Utilities, constants, validators
├── pages/         # Page components
├── providers/     # React Context providers
├── routes/        # Router configuration
├── services/      # API client, WebSocket, Storage
├── styles/        # Tailwind config, global styles
├── types/         # TypeScript types
└── utils/         # Helpers, formatters, validators
```

## Next Steps
1. Start with Phase 1 - Core Infrastructure
2. Build incrementally with testing at each step
4. Use existing banner images for visual consistency
5. Test each feature with real backend API
5. Document API contracts

## Risk Mitigation
- **Stream compatibility**: Test with actual RTSP/HLS streams early
- **WebSocket reliability**: Implement reconnection logic
- **Mobile responsiveness**: Test on mobile viewport
- **Auth token refresh**: Handle 401 gracefully
- **Large media files**: Implement lazy loading + pagination

---

*This plan is a living document. Update as implementation progresses.*