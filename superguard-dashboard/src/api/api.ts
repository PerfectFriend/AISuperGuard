import axios, { type AxiosInstance, type AxiosError } from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:3001/api/v1';

export interface Site {
  id: string;
  name: string;
  description: string | null;
  timezone: string;
  latitude: number | null;
  longitude: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  camera_count: number;
  actuator_count: number;
  detector_count: number;
  active_alarms: number;
}

export interface SiteCreate {
  name: string;
  description?: string;
  timezone?: string;
  latitude?: number | null;
  longitude?: number | null;
}

export interface SiteUpdate {
  name?: string;
  description?: string;
  timezone?: string;
  latitude?: number | null;
  longitude?: number | null;
  is_active?: boolean;
}

export interface Camera {
  id: string;
  site_id: string;
  name: string;
  description: string | null;
  type: 'rtsp' | 'onvif' | 'http' | 'hls' | 'webcam' | 'file';
  stream_url: string;
  width: number;
  height: number;
  fps: number;
  is_enabled: boolean;
  is_online: boolean;
  last_seen: string | null;
  ptz_enabled: boolean;
  zone: any;
  created_at: string;
}

export interface CameraCreate {
  name: string;
  description?: string;
  type?: 'rtsp' | 'onvif' | 'http' | 'hls' | 'webcam' | 'file';
  stream_url: string;
  username?: string;
  password?: string;
  width?: number;
  height?: number;
  fps?: number;
  ptz_enabled?: boolean;
}

export interface CameraUpdate {
  name?: string;
  description?: string;
  stream_url?: string;
  username?: string;
  password?: string;
  is_enabled?: boolean;
  ptz_enabled?: boolean;
}

export interface Actuator {
  id: string;
  site_id: string;
  name: string;
  description: string | null;
  type: 'tuya' | 'sonoff' | 'shelly' | 'tasmota' | 'gpio' | 'mqtt' | 'http';
  config: Record<string, any>;
  is_enabled: boolean;
  is_online: boolean;
  last_status: boolean | null;
  last_power_w: number | null;
  last_seen: string | null;
  created_at: string;
}

export interface ActuatorCreate {
  name: string;
  description?: string;
  type: 'tuya' | 'sonoff' | 'shelly' | 'tasmota' | 'gpio' | 'mqtt' | 'http';
  config: Record<string, any>;
  is_enabled?: boolean;
}

export interface ActuatorUpdate {
  name?: string;
  description?: string;
  config?: Record<string, any>;
  is_enabled?: boolean;
}

export interface ActuatorCommand {
  action: 'on' | 'off' | 'toggle';
}

export interface Detector {
  id: string;
  site_id: string;
  name: string;
  description: string | null;
  type: 'yolo' | 'motion' | 'custom';
  model_path: string | null;
  classes: number[];
  confidence_threshold: number;
  iou_threshold: number;
  is_enabled: boolean;
  require_frames: number;
  auto_resolve_frames: number;
  created_at: string;
}

export interface DetectorCreate {
  name: string;
  description?: string;
  type?: 'yolo' | 'motion' | 'custom';
  model_path?: string;
  classes?: number[];
  confidence_threshold?: number;
  iou_threshold?: number;
  require_frames?: number;
  auto_resolve_frames?: number;
}

export interface DetectorUpdate {
  name?: string;
  description?: string;
  model_path?: string;
  classes?: number[];
  confidence_threshold?: number;
  iou_threshold?: number;
  is_enabled?: boolean;
  require_frames?: number;
  auto_resolve_frames?: number;
}

export interface ActuatorBinding {
  id: string;
  camera_id: string;
  actuator_id: string;
  detector_id: string | null;
  is_active: boolean;
  created_at: string;
}

export interface Alarm {
  id: string;
  site_id: string;
  camera_id: string;
  detector_id: string;
  state: 'triggered' | 'acknowledged' | 'resolved' | 'silenced';
  confidence: number | null;
  detection_class: string | null;
  color_fraction: number | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface AlarmAck {
  note?: string;
}

export interface Notifier {
  id: string;
  site_id: string;
  name: string;
  type: 'telegram' | 'email' | 'sms' | 'pushover' | 'webhook' | 'mqtt' | 'signal';
  config: Record<string, any>;
  is_enabled: boolean;
  notify_on_trigger: boolean;
  notify_on_ack: boolean;
  notify_on_resolve: boolean;
  created_at: string;
}

export interface NotifierCreate {
  name: string;
  type: 'telegram' | 'email' | 'sms' | 'pushover' | 'webhook' | 'mqtt' | 'signal';
  config: Record<string, any>;
  notify_on_trigger?: boolean;
  notify_on_ack?: boolean;
  notify_on_resolve?: boolean;
}

export interface SystemHealth {
  status: string;
  version: string;
  database: string;
  redis: string;
  uptime_seconds: number;
  cameras_online: number;
  cameras_total: number;
  active_alarms: number;
}

export interface InviteToken {
  id: string;
  token: string;
  site_id: string | null;
  role: 'admin' | 'operator' | 'viewer';
  max_uses: number;
  used_count: number;
  expires_at: string | null;
  created_at: string;
  created_by: string;
}

export interface AuditLog {
  id: string;
  user_id: string | null;
  site_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, any>;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface SystemLog {
  id: string;
  level: string;
  logger: string;
  message: string;
  created_at: string;
}

export interface RuleAction {
  on: 'on';
  off: 'off';
  toggle: 'toggle';
}

export interface Rule {
  id: string;
  site_id: string;
  name: string;
  description: string | null;
  camera_id: string;
  detector_id: string | null;
  actuator_id: string;
  action: 'on' | 'off' | 'toggle';
  is_enabled: boolean;
  cooldown_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface RuleCreate {
  name: string;
  description?: string;
  camera_id: string;
  detector_id?: string;
  actuator_id: string;
  action?: 'on' | 'off' | 'toggle';
  is_enabled?: boolean;
  cooldown_seconds?: number;
}

export interface RuleUpdate {
  name?: string;
  description?: string;
  camera_id?: string;
  detector_id?: string;
  actuator_id?: string;
  action?: 'on' | 'off' | 'toggle';
  is_enabled?: boolean;
  cooldown_seconds?: number;
}

export interface DashboardResponse {
  site: Site;
  cameras: Camera[];
  actuators: Actuator[];
  detectors: Detector[];
  active_alarms: Alarm[];
  system_health: SystemHealth;
}

class ApiService {
  private client: AxiosInstance;
  private token: string | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE,
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 10000,
    });

    // Load token from localStorage
    this.token = localStorage.getItem('auth_token');
    if (this.token) {
      this.client.defaults.headers.common['Authorization'] = `Bearer ${this.token}`;
    }

    // Response interceptor for token refresh
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as any;
        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;
          try {
            const refreshToken = localStorage.getItem('refresh_token');
            if (refreshToken) {
              const response = await axios.post(`${API_BASE}/auth/refresh`, {
                refresh_token: refreshToken,
              });
              const { access_token, refresh_token: newRefreshToken } = response.data;
              this.setToken(access_token, newRefreshToken);
              originalRequest.headers.Authorization = `Bearer ${access_token}`;
              return this.client(originalRequest);
            }
          } catch (refreshError) {
            this.clearToken();
            window.location.href = '/login';
          }
        }
        return Promise.reject(error);
      }
    );
  }

  setToken(accessToken: string, refreshToken?: string) {
    this.token = accessToken;
    this.client.defaults.headers.common['Authorization'] = `Bearer ${accessToken}`;
    localStorage.setItem('auth_token', accessToken);
    if (refreshToken) {
      localStorage.setItem('refresh_token', refreshToken);
    }
  }

  clearToken() {
    this.token = null;
    delete this.client.defaults.headers.common['Authorization'];
    localStorage.removeItem('auth_token');
    localStorage.removeItem('refresh_token');
  }

  getToken(): string | null {
    return this.token;
  }

  isAuthenticated(): boolean {
    return !!this.token;
  }

  // Auth
  async login(email: string, password: string) {
    const response = await this.client.post('/auth/login', { email, password });
    const { access_token, refresh_token } = response.data;
    this.setToken(access_token, refresh_token);
    return response.data;
  }

  async register(email: string, password: string, full_name: string) {
    return this.client.post('/auth/register', { email, password, full_name });
  }

  async refreshToken() {
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) throw new Error('No refresh token');
    const response = await this.client.post('/auth/refresh', { refresh_token: refreshToken });
    const { access_token, refresh_token: newRefreshToken } = response.data;
    this.setToken(access_token, newRefreshToken);
    return response.data;
  }

  async getMe() {
    return this.client.get('/auth/me');
  }

  // Sites
  async getSites(skip = 0, limit = 50) {
    const response = await this.client.get('/sites', { params: { skip, limit } });
    return response.data;
  }

  async getSite(siteId: string) {
    const response = await this.client.get(`/sites/${siteId}`);
    return response.data;
  }

  async createSite(data: SiteCreate) {
    const response = await this.client.post('/sites', data);
    return response.data;
  }

  async updateSite(siteId: string, data: SiteUpdate) {
    const response = await this.client.patch(`/sites/${siteId}`, data);
    return response.data;
  }

  async deleteSite(siteId: string) {
    return this.client.delete(`/sites/${siteId}`);
  }

  async getSiteDashboard(siteId: string) {
    const response = await this.client.get(`/sites/${siteId}/dashboard`);
    return response.data;
  }

  // Cameras
  async getCameras(siteId: string, skip = 0, limit = 100) {
    const response = await this.client.get(`/sites/${siteId}/cameras`, { params: { skip, limit } });
    return response.data;
  }

  async getCamera(siteId: string, cameraId: string) {
    const response = await this.client.get(`/sites/${siteId}/cameras/${cameraId}`);
    return response.data;
  }

  async createCamera(siteId: string, data: CameraCreate) {
    const response = await this.client.post(`/sites/${siteId}/cameras`, data);
    return response.data;
  }

  async updateCamera(siteId: string, cameraId: string, data: CameraUpdate) {
    const response = await this.client.patch(`/sites/${siteId}/cameras/${cameraId}`, data);
    return response.data;
  }

  async deleteCamera(siteId: string, cameraId: string) {
    return this.client.delete(`/sites/${siteId}/cameras/${cameraId}`);
  }

  async testCamera(siteId: string, cameraId: string) {
    const response = await this.client.post(`/sites/${siteId}/cameras/${cameraId}/test`);
    return response.data;
  }

  async discoverCameras(siteId: string, networkRange = '192.168.1.0/24') {
    const response = await this.client.post(`/sites/${siteId}/cameras/discover`, { network_range: networkRange });
    return response.data;
  }

  async getCameraBindings(siteId: string, cameraId: string) {
    const response = await this.client.get(`/sites/${siteId}/cameras/${cameraId}/bindings`);
    return response.data;
  }

  async createCameraBinding(siteId: string, cameraId: string, actuatorId: string, detectorId?: string) {
    const response = await this.client.post(`/sites/${siteId}/cameras/${cameraId}/bindings`, {
      camera_id: cameraId,
      actuator_id: actuatorId,
      detector_id: detectorId,
    });
    return response.data;
  }

  // Camera bindings - new simpler methods
  async getBindings(siteId: string, cameraId: string) {
    const response = await this.client.get(`/sites/${siteId}/cameras/${cameraId}/bindings`);
    return response.data;
  }

  async createBinding(siteId: string, cameraId: string, data: { actuator_id?: string; detector_id?: string }) {
    const response = await this.client.post(`/sites/${siteId}/cameras/${cameraId}/bindings`, data);
    return response.data;
  }

  async deleteBinding(siteId: string, cameraId: string, bindingId: string) {
    return this.client.delete(`/sites/${siteId}/cameras/${cameraId}/bindings/${bindingId}`);
  }

  // Actuators
  async getActuators(siteId: string) {
    const response = await this.client.get(`/sites/${siteId}/actuators`);
    return response.data;
  }

  async getActuator(siteId: string, actuatorId: string) {
    const response = await this.client.get(`/sites/${siteId}/actuators/${actuatorId}`);
    return response.data;
  }

  async createActuator(siteId: string, data: ActuatorCreate) {
    const response = await this.client.post(`/sites/${siteId}/actuators`, data);
    return response.data;
  }

  async updateActuator(siteId: string, actuatorId: string, data: ActuatorUpdate) {
    const response = await this.client.patch(`/sites/${siteId}/actuators/${actuatorId}`, data);
    return response.data;
  }

  async deleteActuator(siteId: string, actuatorId: string) {
    return this.client.delete(`/sites/${siteId}/actuators/${actuatorId}`);
  }

  async commandActuator(siteId: string, actuatorId: string, command: ActuatorCommand) {
    const response = await this.client.post(`/sites/${siteId}/actuators/${actuatorId}/command`, command);
    return response.data;
  }

  // New actuator methods
  async testActuator(siteId: string, actuatorId: string) {
    const response = await this.client.post(`/sites/${siteId}/actuators/${actuatorId}/test`);
    return response.data;
  }

  async findDeviceByMac(siteId: string, mac: string) {
    const response = await this.client.get(`/sites/${siteId}/actuators/find-by-mac/${mac}`);
    return response.data;
  }

  async sendTelegramAlert(siteId: string, data: any) {
    const response = await this.client.post(`/sites/${siteId}/telegram/alert`, data);
    return response.data;
  }

  // Detectors
  async getDetectors(siteId: string) {
    const response = await this.client.get(`/sites/${siteId}/detectors`);
    return response.data;
  }

  async getDetector(siteId: string, detectorId: string) {
    const response = await this.client.get(`/sites/${siteId}/detectors/${detectorId}`);
    return response.data;
  }

  async createDetector(siteId: string, data: DetectorCreate) {
    const response = await this.client.post(`/sites/${siteId}/detectors`, data);
    return response.data;
  }

  async updateDetector(siteId: string, detectorId: string, data: DetectorUpdate) {
    const response = await this.client.patch(`/sites/${siteId}/detectors/${detectorId}`, data);
    return response.data;
  }

  async deleteDetector(siteId: string, detectorId: string) {
    return this.client.delete(`/sites/${siteId}/detectors/${detectorId}`);
  }

  async testDetector(siteId: string, detectorId: string, cameraId?: string) {
    const params = cameraId ? `?camera_id=${cameraId}` : '';
    const response = await this.client.post(`/sites/${siteId}/detectors/${detectorId}/test${params}`);
    return response.data;
  }

  // Alarms
  async getAlarms(siteId: string) {
    const response = await this.client.get(`/sites/${siteId}/alarms`);
    return response.data;
  }

  async getAlarm(siteId: string, alarmId: string) {
    const response = await this.client.get(`/sites/${siteId}/alarms/${alarmId}`);
    return response.data;
  }

  async acknowledgeAlarm(siteId: string, alarmId: string, note?: string) {
    const response = await this.client.post(`/sites/${siteId}/alarms/${alarmId}/ack`, { note });
    return response.data;
  }

  async silenceAlarm(siteId: string, alarmId: string) {
    const response = await this.client.post(`/sites/${siteId}/alarms/${alarmId}/silence`);
    return response.data;
  }

  async getAlarmMedia(siteId: string, alarmId: string) {
    const response = await this.client.get(`/sites/${siteId}/alarms/${alarmId}/media`);
    return response.data;
  }

  // Notifiers
  async getNotifiers(siteId: string) {
    const response = await this.client.get(`/sites/${siteId}/notifiers`);
    return response.data;
  }

  async createNotifier(siteId: string, data: NotifierCreate) {
    const response = await this.client.post(`/sites/${siteId}/notifiers`, data);
    return response.data;
  }

  async deleteNotifier(siteId: string, notifierId: string) {
    return this.client.delete(`/sites/${siteId}/notifiers/${notifierId}`);
  }

  async testNotifier(siteId: string, notifierId: string) {
    const response = await this.client.post(`/sites/${siteId}/notifiers/${notifierId}/test`);
    return response.data;
  }

  // System
  async getSystemHealth() {
    const response = await this.client.get('/system/health');
    return response.data;
  }

  async getSystemVersion() {
    const response = await this.client.get('/system/version');
    return response.data;
  }

  async getSystemLogs(params?: { level?: string; limit?: number }) {
    const response = await this.client.get('/system/logs', { params });
    return response.data;
  }

  async createBackup() {
    const response = await this.client.post('/system/backup');
    return response.data;
  }

  async restoreBackup(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    const response = await this.client.post('/system/restore', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  async ping(ip: string, count = 3) {
    const response = await this.client.post('/system/ping', { ip, count });
    return response.data;
  }

  async scanMac(mac: string, timeout = 2000) {
    const response = await this.client.post('/system/scan-mac', { mac, timeout });
    return response.data;
  }

  // Admin: Invite Tokens
  async createInviteToken(data: { site_id?: string; role: string; max_uses: number; expires_days?: number }) {
    const response = await this.client.post('/auth/admin/invites', data);
    return response.data;
  }

  async getInviteTokens() {
    const response = await this.client.get('/auth/admin/invites');
    return response.data;
  }

  async revokeInviteToken(inviteId: string) {
    const response = await this.client.delete(`/auth/admin/invites/${inviteId}`);
    return response.data;
  }

  // Admin: Audit Logs
  async getAuditLogs(params?: { limit?: number; offset?: number; action?: string; user_id?: string; site_id?: string }) {
    const response = await this.client.get('/auth/admin/audit', { params });
    return response.data;
  }

  // Rules
  async getRules(siteId: string) {
    const response = await this.client.get(`/sites/${siteId}/rules`);
    return response.data;
  }

  async createRule(siteId: string, data: RuleCreate) {
    const response = await this.client.post(`/sites/${siteId}/rules`, data);
    return response.data;
  }

  async getRule(siteId: string, ruleId: string) {
    const response = await this.client.get(`/sites/${siteId}/rules/${ruleId}`);
    return response.data;
  }

  async updateRule(siteId: string, ruleId: string, data: RuleUpdate) {
    const response = await this.client.patch(`/sites/${siteId}/rules/${ruleId}`, data);
    return response.data;
  }

  async deleteRule(siteId: string, ruleId: string) {
    return this.client.delete(`/sites/${siteId}/rules/${ruleId}`);
  }
}

export const api = new ApiService();
export default api;