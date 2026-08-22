import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RefreshCw, Video, Shield, Zap, Settings, Loader2, AlertTriangle, Bell, Wifi } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useSiteDashboard, useSystemLogs, useSites } from '@/hooks/useApiData';

export default function Dashboard() {
  const { t } = useTranslation('dashboard');
  const navigate = useNavigate();
  const { sites, loading: sitesLoading } = useSites();
  const siteId = sites.length > 0 ? sites[0].id : '';
  const { dashboard, loading: dashboardLoading, refetch: refetchDashboard } = useSiteDashboard(siteId);
  const { logs } = useSystemLogs({ limit: 10 });

  const [totalActiveAlarms, setTotalActiveAlarms] = useState(0);
  const [onlineSites, setOnlineSites] = useState(0);
  const [recentAlarms, setRecentAlarms] = useState<any[]>([]);
  const [recentLogs, setRecentLogs] = useState<any[]>([]);

  // Update derived state when data changes
  useEffect(() => {
    if (dashboard) {
      const alarms = dashboard.active_alarms || [];
      const sites = dashboard.site ? [dashboard.site] : [];
      setTotalActiveAlarms(alarms.filter(a => a.state === 'triggered').length);
      setOnlineSites(sites.filter(s => s.is_active).length);
      setRecentAlarms(alarms.slice(0, 5));
    }
  }, [dashboard]);

  useEffect(() => {
    setRecentLogs(logs.slice(0, 5));
  }, [logs]);

  const handleViewAlarms = () => navigate('/alarms');
  const handleViewSites = () => navigate('/sites');

  const healthConnected = false;
  const alarmConnected = false;
  const pushPermission = 'default' as NotificationPermission;

  if (dashboardLoading || sitesLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-12 w-12 animate-spin text-primary" />
      </div>
    );
  }

  const health = dashboard?.system_health || { status: 'healthy', uptime_seconds: 0, active_alarms: 0, cameras_online: 0, cameras_total: 0 };
  const cameras = dashboard?.cameras || [];
  const onlineCameras = cameras.filter(c => c.is_online).length;
  const totalCamerasCount = cameras.length;

  return (
    <div className="space-y-6">
      {/* Connection Status Bar */}
      <Card className="border-primary/20 bg-primary/5">
        <CardContent className="flex items-center justify-between py-2 px-4">
          <div className="flex items-center gap-4 text-sm">
            <span className={`flex items-center gap-1 ${healthConnected ? 'text-green-600' : 'text-red-600'}`}>
              <span className={`w-2 h-2 rounded-full ${healthConnected ? 'bg-green-500' : 'bg-red-500'}`} />
              {healthConnected ? t('wsConnected') : t('wsDisconnected')}
            </span>
            <span className={`flex items-center gap-1 ${alarmConnected ? 'text-green-600' : 'text-red-600'}`}>
              <span className={`w-2 h-2 rounded-full ${alarmConnected ? 'bg-green-500' : 'bg-red-500'}`} />
              {alarmConnected ? t('alarmsWsConnected') : t('alarmsWsDisconnected')}
            </span>
            <span className={`flex items-center gap-1 ${pushPermission === 'granted' ? 'text-green-600' : 'text-yellow-600'}`}>
              <span className={`w-2 h-2 rounded-full ${pushPermission === 'granted' ? 'bg-green-500' : 'bg-yellow-500'}`} />
              {pushPermission === 'granted' ? t('pushEnabled') : t('pushDisabled')}
            </span>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetchDashboard()}>
            <RefreshCw className="w-4 h-4 mr-2" />
            {t('refreshAll')}
          </Button>
        </CardContent>
      </Card>

      {/* Status Cards */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        {/* System Status */}
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2">
              <Video className="w-5 h-5" />
              {t('systemStatus')}
            </CardTitle>
            <CardDescription>{t('healthDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <Video className="w-4 h-4" />
                {t('camerasOnline')}
              </span>
              <span className="text-lg font-semibold">
                {onlineCameras} / {totalCamerasCount}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <Bell className="w-4 h-4" />
                {t('activeAlarms')}
              </span>
              <span className="text-lg font-semibold text-destructive">
                {health.active_alarms ?? totalActiveAlarms}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <Settings className="w-4 h-4" />
                {t('systemUptime')}
              </span>
              <span className="text-lg font-semibold">
                {health.uptime_seconds ? `${Math.floor(health.uptime_seconds / 3600)}h ${Math.floor((health.uptime_seconds % 3600) / 60)}m` : '—'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <Shield className="w-4 h-4" />
                {t('sitesOnline')}
              </span>
              <span className="text-lg font-semibold text-green-600 dark:text-green-400">
                {onlineSites} / {sites.length}
              </span>
            </div>
          </CardContent>
          <CardFooter>
            <Button variant="outline" size="sm" onClick={handleViewSites}>
              {t('viewDetails')}
            </Button>
          </CardFooter>
        </Card>

        {/* Detection Status */}
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2">
              <Shield className="w-5 h-5" />
              {t('detectionStatus')}
            </CardTitle>
            <CardDescription>{t('detectionDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <AlertTriangle className="w-4 h-4" />
                {t('motionDetection')}
              </span>
              <span className="text-lg font-semibold text-green-600 dark:text-green-400">
                {health.status === 'healthy' ? t('active') : t('standby')}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <Video className="w-4 h-4" />
                {t('objectRecognition')}
              </span>
              <span className="text-lg font-semibold text-green-600 dark:text-green-400">
                {t('active')}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <Settings className="w-4 h-4" />
                {t('faceDetection')}
              </span>
              <span className="text-lg font-semibold text-yellow-600 dark:text-yellow-400">
                {t('standby')}
              </span>
            </div>
          </CardContent>
          <CardFooter>
            <Button variant="outline" size="sm" onClick={() => navigate('/detectors')}>
              {t('configure')}
            </Button>
          </CardFooter>
        </Card>

        {/* Actuator Status */}
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2">
              <Zap className="w-5 h-5" />
              {t('actuatorStatus')}
            </CardTitle>
            <CardDescription>{t('actuatorDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <Shield className="w-4 h-4" />
                {t('sitesOnline')}
              </span>
              <span className="text-lg font-semibold text-green-600 dark:text-green-400">
                {onlineSites} / {sites.length}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <Zap className="w-4 h-4" />
                {t('totalActuators')}
              </span>
              <span className="text-lg font-semibold">
                {sites.reduce((sum: number, s: any) => sum + (s.actuator_count || 0), 0)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <Shield className="w-4 h-4" />
                {t('totalDetectors')}
              </span>
              <span className="text-lg font-semibold">
                {sites.reduce((sum: number, s: any) => sum + (s.detector_count || 0), 0)}
              </span>
            </div>
          </CardContent>
          <CardFooter>
            <Button variant="outline" size="sm" onClick={() => navigate('/actuators')}>
              {t('control')}
            </Button>
          </CardFooter>
        </Card>

        {/* Notifications */}
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2">
              <Bell className="w-5 h-5" />
              {t('notifications')}
            </CardTitle>
            <CardDescription>{t('notificationsDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <Bell className="w-4 h-4" />
                {t('lastAlert')}
              </span>
              <span className="text-lg font-medium text-muted-foreground">
                {totalActiveAlarms > 0 ? `${totalActiveAlarms} ${t('activeAlarms')}` : t('none')}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <Wifi className="w-4 h-4" />
                {t('emailNotifications')}
              </span>
              <span className="text-lg font-medium text-green-600 dark:text-green-400">{t('enabled')}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <Shield className="w-4 h-4" />
                {t('telegramBot')}
              </span>
              <span className="text-lg font-medium text-green-600 dark:text-green-400">{t('connected')}</span>
            </div>
          </CardContent>
          <CardFooter>
            <Button variant="outline" size="sm" onClick={() => navigate('/notifiers')}>
              {t('settings')}
            </Button>
          </CardFooter>
        </Card>
      </div>

      {/* Recent Activity & Logs */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Recent Alarms */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Bell className="w-5 h-5" />
              {t('recentAlarms')}
            </CardTitle>
            <Button variant="ghost" size="sm" onClick={handleViewAlarms}>
              {t('viewAll')}
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {recentAlarms.length > 0 ? (
              recentAlarms.map((alarm: any) => (
                <div key={alarm.id} className="flex items-center justify-between p-3 border rounded-lg hover:bg-accent transition-colors">
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${alarm.state === 'triggered' ? 'bg-red-500' : alarm.state === 'acknowledged' ? 'bg-yellow-500' : 'bg-green-500'}`} />
                    <div>
                      <p className="font-medium text-sm">{alarm.detection_class || t('unknown')}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(alarm.created_at).toLocaleString()} • {alarm.confidence !== null ? `${(alarm.confidence * 100).toFixed(1)}%` : t('noConfidence')}
                      </p>
                    </div>
                  </div>
                  <Badge variant={
                    alarm.state === 'triggered' ? 'destructive' :
                    alarm.state === 'acknowledged' ? 'secondary' : 'outline'
                  } className="capitalize text-xs">
                    {alarm.state}
                  </Badge>
                </div>
              ))
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Bell className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>{t('noAlarms')}</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* System Logs */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Settings className="w-5 h-5" />
              {t('systemLogs')}
            </CardTitle>
            <Button variant="ghost" size="sm" onClick={() => navigate('/system?tab=logs')}>
              {t('viewAll')}
            </Button>
          </CardHeader>
          <CardContent>
            <div className="max-h-64 overflow-auto font-mono text-sm bg-gray-900 text-green-400 p-4 rounded">
              {recentLogs.length > 0 ? (
                recentLogs.map((log: any, i: number) => (
                  <div key={i} className="border-b border-gray-700 py-1 last:border-0">
                    <span className="text-gray-500">[{new Date(log.created_at).toLocaleTimeString()}]</span>
                    <span className={`mx-2 ${log.level === 'ERROR' ? 'text-red-400' : log.level === 'WARN' ? 'text-yellow-400' : 'text-green-400'}`}>
                      {log.level.toUpperCase()}
                    </span>
                    <span className="text-gray-400">{log.logger}:</span>
                    <span>{log.message}</span>
                  </div>
                ))
              ) : (
                <p className="text-gray-500">{t('noLogs')}</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}