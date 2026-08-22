import { useState, useEffect, useCallback } from 'react';
import { api, 
  type Site, 
  type Camera, 
  type Actuator, 
  type Detector, 
  type Alarm, 
  type Notifier, 
  type SystemHealth, 
  type SystemLog,
  type Rule,
  type RuleCreate,
  type RuleUpdate,
  type SiteCreate, 
  type SiteUpdate, 
  type CameraCreate, 
  type CameraUpdate, 
  type ActuatorCreate, 
  type ActuatorUpdate, 
  type DetectorCreate, 
  type DetectorUpdate, 
  type ActuatorCommand, 
  type NotifierCreate, 
  type DashboardResponse,
  type InviteToken,
  type AuditLog
} from '@/api/api';

// Re-export types for use in components
export type { 
  Site, Camera, Actuator, Detector, Alarm, Notifier, SystemHealth, SystemLog,
  Rule, RuleCreate, RuleUpdate,
  SiteCreate, SiteUpdate, CameraCreate, CameraUpdate, ActuatorCreate, ActuatorUpdate,
  DetectorCreate, DetectorUpdate, ActuatorCommand, NotifierCreate, DashboardResponse,
  ActuatorBinding,
  InviteToken,
  AuditLog
} from '@/api/api';

export function useSites() {
  const [sites, setSites] = useState<Site[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSites = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getSites();
      setSites(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSites();
  }, [fetchSites]);

  const createSite = async (data: SiteCreate) => {
    const newSite = await api.createSite(data);
    setSites(prev => [newSite, ...prev]);
    return newSite;
  };

  const updateSite = async (siteId: string, data: SiteUpdate) => {
    const updated = await api.updateSite(siteId, data);
    setSites(prev => prev.map(s => s.id === siteId ? updated : s));
    return updated;
  };

  const deleteSite = async (siteId: string) => {
    await api.deleteSite(siteId);
    setSites(prev => prev.filter(s => s.id !== siteId));
  };

  return { sites, loading, error, refetch: fetchSites, createSite, updateSite, deleteSite };
}

export function useSite(siteId: string) {
  const [site, setSite] = useState<Site | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSite = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getSite(siteId);
      setSite(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    if (siteId) fetchSite();
  }, [fetchSite, siteId]);

  return { site, loading, error, refetch: fetchSite };
}

export function useSiteDashboard(siteId: string) {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboard = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getSiteDashboard(siteId);
      setDashboard(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    if (siteId) fetchDashboard();
    const interval = setInterval(fetchDashboard, 15000);
    return () => clearInterval(interval);
  }, [fetchDashboard, siteId]);

  return { dashboard, loading, error, refetch: fetchDashboard };
}

export function useCameras(siteId: string) {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCameras = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getCameras(siteId);
      setCameras(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    if (siteId) fetchCameras();
  }, [fetchCameras, siteId]);

  const createCamera = async (data: CameraCreate) => {
    const newCamera = await api.createCamera(siteId, data);
    setCameras(prev => [newCamera, ...prev]);
    return newCamera;
  };

  const updateCamera = async (cameraId: string, data: CameraUpdate) => {
    const updated = await api.updateCamera(siteId, cameraId, data);
    setCameras(prev => prev.map(c => c.id === cameraId ? updated : c));
    return updated;
  };

  const deleteCamera = async (cameraId: string) => {
    await api.deleteCamera(siteId, cameraId);
    setCameras(prev => prev.filter(c => c.id !== cameraId));
  };

  const testCamera = async (cameraId: string) => {
    return api.testCamera(siteId, cameraId);
  };

  const discoverCameras = async (networkRange = '192.168.1.0/24') => {
    return api.discoverCameras(siteId, networkRange);
  };

  return { cameras, loading, error, refetch: fetchCameras, createCamera, updateCamera, deleteCamera, testCamera, discoverCameras };
}

export function useActuators(siteId: string) {
  const [actuators, setActuators] = useState<Actuator[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchActuators = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getActuators(siteId);
      setActuators(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    if (siteId) fetchActuators();
  }, [fetchActuators, siteId]);

  const createActuator = async (data: ActuatorCreate) => {
    const newActuator = await api.createActuator(siteId, data);
    setActuators(prev => [newActuator, ...prev]);
    return newActuator;
  };

  const updateActuator = async (actuatorId: string, data: ActuatorUpdate) => {
    const updated = await api.updateActuator(siteId, actuatorId, data);
    setActuators(prev => prev.map(a => a.id === actuatorId ? updated : a));
    return updated;
  };

  const deleteActuator = async (actuatorId: string) => {
    await api.deleteActuator(siteId, actuatorId);
    setActuators(prev => prev.filter(a => a.id !== actuatorId));
  };

  const commandActuator = async (actuatorId: string, command: ActuatorCommand) => {
    const result = await api.commandActuator(siteId, actuatorId, command);
    // Refresh to get updated status
    await fetchActuators();
    return result;
  };

  return { actuators, loading, error, refetch: fetchActuators, createActuator, updateActuator, deleteActuator, commandActuator };
}

export function useDetectors(siteId: string) {
  const [detectors, setDetectors] = useState<Detector[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetectors = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getDetectors(siteId);
      setDetectors(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    if (siteId) fetchDetectors();
  }, [fetchDetectors, siteId]);

  const createDetector = async (data: DetectorCreate) => {
    const newDetector = await api.createDetector(siteId, data);
    setDetectors(prev => [newDetector, ...prev]);
    return newDetector;
  };

  const updateDetector = async (detectorId: string, data: DetectorUpdate) => {
    const updated = await api.updateDetector(siteId, detectorId, data);
    setDetectors(prev => prev.map(d => d.id === detectorId ? updated : d));
    return updated;
  };

  const deleteDetector = async (detectorId: string) => {
    await api.deleteDetector(siteId, detectorId);
    setDetectors(prev => prev.filter(d => d.id !== detectorId));
  };

  const testDetector = async (detectorId: string, cameraId?: string) => {
    return api.testDetector(siteId, detectorId, cameraId);
  };

  return { detectors, loading, error, refetch: fetchDetectors, createDetector, updateDetector, deleteDetector, testDetector };
}

export function useAlarms(siteId: string) {
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAlarms = useCallback(async () => {
    if (!siteId) {
      setAlarms([]);
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const data = await api.getAlarms(siteId);
      setAlarms(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    if (siteId) fetchAlarms();
  }, [fetchAlarms, siteId]);

  const acknowledge = async (alarmId: string, note?: string) => {
    try {
      const updated = await api.acknowledgeAlarm(siteId, alarmId, note);
      setAlarms(prev => prev.map(a => a.id === alarmId ? updated : a));
    } catch (err: any) {
      throw new Error(err.response?.data?.detail || err.message);
    }
  };

  const silence = async (alarmId: string) => {
    try {
      const updated = await api.silenceAlarm(siteId, alarmId);
      setAlarms(prev => prev.map(a => a.id === alarmId ? updated : a));
    } catch (err: any) {
      throw new Error(err.response?.data?.detail || err.message);
    }
  };

  const getMedia = async (alarmId: string) => {
    return api.getAlarmMedia(siteId, alarmId);
  };

  return { alarms, loading, error, refetch: fetchAlarms, acknowledge, silence, getMedia };
}

export function useNotifiers(siteId: string) {
  const [notifiers, setNotifiers] = useState<Notifier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchNotifiers = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getNotifiers(siteId);
      setNotifiers(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    if (siteId) fetchNotifiers();
  }, [fetchNotifiers, siteId]);

  const createNotifier = async (data: NotifierCreate) => {
    const newNotifier = await api.createNotifier(siteId, data);
    setNotifiers(prev => [newNotifier, ...prev]);
    return newNotifier;
  };

  const deleteNotifier = async (notifierId: string) => {
    await api.deleteNotifier(siteId, notifierId);
    setNotifiers(prev => prev.filter(n => n.id !== notifierId));
  };

  const testNotifier = async (notifierId: string) => {
    return api.testNotifier(siteId, notifierId);
  };

  return { notifiers, loading, error, refetch: fetchNotifiers, createNotifier, deleteNotifier, testNotifier };
}

export function useSystemHealth() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getSystemHealth();
      setHealth(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 15000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  return { health, loading, error, refetch: fetchHealth };
}

export function useSystemLogs(params?: { level?: string; limit?: number }) {
  const [logs, setLogs] = useState<SystemLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getSystemLogs(params);
      setLogs(data.logs || []);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, [params]);

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 15000);
    return () => clearInterval(interval);
  }, [fetchLogs]);

  return { logs, loading, error, refetch: fetchLogs };
}

export function useSystemVersion() {
  const [version, setVersion] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchVersion = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getSystemVersion();
      setVersion(data.version || data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchVersion();
  }, [fetchVersion]);

  return { version, loading, error, refetch: fetchVersion };
}

export function useAuth() {
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const login = async (email: string, password: string) => {
    try {
      setLoading(true);
      const data = await api.login(email, password);
      await fetchUser();
      setError(null);
      return data;
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const register = async (email: string, password: string, full_name: string) => {
    try {
      setLoading(true);
      const data = await api.register(email, password, full_name);
      setError(null);
      return data;
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    api.clearToken();
    setUser(null);
  };

  const fetchUser = async () => {
    if (!api.isAuthenticated()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const data = await api.getMe();
      setUser(data);
    } catch (err) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUser();
  }, []);

  const isAuthenticated = api.isAuthenticated();

  return { user, loading, error, login, register, logout, refetch: fetchUser, isAuthenticated };
}

export function useRules(siteId: string) {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRules = useCallback(async () => {
    if (!siteId) {
      setRules([]);
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const data = await api.getRules(siteId);
      setRules(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    if (siteId) fetchRules();
  }, [fetchRules, siteId]);

  const createRule = async (data: RuleCreate) => {
    const newRule = await api.createRule(siteId, data);
    setRules(prev => [newRule, ...prev]);
    return newRule;
  };

  const updateRule = async (ruleId: string, data: RuleUpdate) => {
    const updated = await api.updateRule(siteId, ruleId, data);
    setRules(prev => prev.map(r => r.id === ruleId ? updated : r));
    return updated;
  };

  const deleteRule = async (ruleId: string) => {
    await api.deleteRule(siteId, ruleId);
    setRules(prev => prev.filter(r => r.id !== ruleId));
  };

  return { rules, loading, error, refetch: fetchRules, createRule, updateRule, deleteRule };
}

export function useSystemActions() {
  const createBackup = async () => {
    return api.createBackup();
  };

  const restoreBackup = async (file: File) => {
    return api.restoreBackup(file);
  };

  const ping = async (ip: string, count = 3) => {
    return api.ping(ip, count);
  };

  const scanMac = async (mac: string, timeout = 2000) => {
    return api.scanMac(mac, timeout);
  };

  return { createBackup, restoreBackup, ping, scanMac };
}

// Admin: Invite Tokens
export function useInviteTokens() {
  const [invites, setInvites] = useState<InviteToken[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchInvites = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getInviteTokens();
      setInvites(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInvites();
  }, [fetchInvites]);

  const createInvite = async (data: { site_id?: string; role: string; max_uses: number; expires_days?: number }) => {
    const newInvite = await api.createInviteToken(data);
    setInvites(prev => [newInvite, ...prev]);
    return newInvite;
  };

  const revokeInvite = async (inviteId: string) => {
    await api.revokeInviteToken(inviteId);
    setInvites(prev => prev.filter(i => i.id !== inviteId));
  };

  return { invites, loading, error, refetch: fetchInvites, createInvite, revokeInvite };
}

// Admin: Audit Logs
export function useAuditLogs(params?: { limit?: number; offset?: number; action?: string; user_id?: string; site_id?: string }) {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getAuditLogs(params);
      setLogs(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, [params]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs, params]);

  return { logs, loading, error, refetch: fetchLogs };
}