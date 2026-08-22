import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { RefreshCw, Shield, Database, Server, Cpu, Info, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSystemHealth, useSystemLogs, useSystemVersion } from '@/hooks/useApiData';

export default function System() {
  const { t } = useTranslation('system');
  const { health, loading: healthLoading, refetch: refetchHealth } = useSystemHealth();
  const { logs, loading: logsLoading, refetch: refetchLogs } = useSystemLogs({ limit: 100 });
  const { version } = useSystemVersion();

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">{t('title')}</h2>
      
      <Tabs defaultValue="general">
        <TabsList className="w-full">
          <TabsTrigger value="general">
            <span className="flex items-center gap-2">
              <Shield className="w-4 h-4" />
              {t('general')}
            </span>
          </TabsTrigger>
          <TabsTrigger value="backup">
            <span className="flex items-center gap-2">
              <Database className="w-4 h-4" />
              {t('backup')}
            </span>
          </TabsTrigger>
          <TabsTrigger value="logs">
            <span className="flex items-center gap-2">
              <Server className="w-4 h-4" />
              {t('logs')}
            </span>
          </TabsTrigger>
          <TabsTrigger value="about">
            <span className="flex items-center gap-2">
              <Info className="w-4 h-4" />
              {t('about')}
            </span>
          </TabsTrigger>
        </TabsList>
        
        <TabsContent value="general" className="mt-4 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="w-5 h-5" />
                {t('generalSettings')}
              </CardTitle>
              <CardDescription>{t('generalDescription')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">{t('autoStartMonitoring')}</h4>
                  <p className="text-sm text-muted-foreground">{t('autoStartDescription')}</p>
                </div>
                <Switch checked={true} onCheckedChange={() => {}} />
              </div>
              
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">{t('enableDarkMode')}</h4>
                  <p className="text-sm text-muted-foreground">{t('darkModeDescription')}</p>
                </div>
                <Switch checked={false} onCheckedChange={() => {}} />
              </div>
              
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">{t('sendAnalytics')}</h4>
                  <p className="text-sm text-muted-foreground">{t('analyticsDescription')}</p>
                </div>
                <Switch checked={false} onCheckedChange={() => {}} />
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="w-5 h-5" />
                {t('network')}
              </CardTitle>
              <CardDescription>{t('networkDescription')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">{t('apiBaseUrl')}</label>
                <input
                                  type="text"
                                  defaultValue="http://localhost:3001"
                                  className="w-full px-3 py-2 border rounded-md bg-background"
                                  readOnly
                                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">{t('websocketUrl')}</label>
                <input
                                  type="text"
                                  defaultValue="ws://localhost:3001/ws"
                                  className="w-full px-3 py-2 border rounded-md bg-background"
                                  readOnly
                                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        
        <TabsContent value="backup" className="mt-4 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="w-5 h-5" />
                {t('backupConfiguration')}
              </CardTitle>
              <CardDescription>{t('backupDescription')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-4">
                <Button variant="outline" disabled>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  {t('createBackup')}
                </Button>
                <Button variant="outline" disabled>
                  {t('restoreBackup')}
                </Button>
              </div>
              <p className="text-sm text-muted-foreground">{t('backupInfo')}</p>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="w-5 h-5" />
                {t('recentBackups')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm text-muted-foreground">
                <p>{t('noBackups') || 'No backups found'}</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        
        <TabsContent value="logs" className="mt-4 space-y-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Server className="w-5 h-5" />
                  {t('systemLogs')}
                </CardTitle>
                <CardDescription>{t('logsDescription')}</CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={refetchLogs} disabled={logsLoading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${logsLoading ? 'animate-spin' : ''}`} />
                {t('refresh')}
              </Button>
            </CardHeader>
            <CardContent>
              {logsLoading ? (
                <div className="flex items-center justify-center h-64">
                  <Loader2 className="h-12 w-12 animate-spin text-primary" />
                </div>
              ) : (
                <pre className="bg-gray-900 text-green-400 p-4 rounded-md font-mono text-sm max-h-96 overflow-auto">
                  {logs.length > 0 ? logs.map((log: any) => 
                    `[${new Date(log.created_at).toLocaleString()}] ${log.level.toUpperCase()}  ${log.logger}: ${log.message}`
                  ).join('\n') : 'No logs available'}
                </pre>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        
        <TabsContent value="about" className="mt-4 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Info className="w-5 h-5" />
                {t('aboutSuperGuard')}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 bg-primary rounded-lg flex items-center justify-center">
                  <span className="text-2xl font-bold text-primary-foreground">SG</span>
                </div>
                <div>
                  <h3 className="text-lg font-bold">SuperGuard AI Surveillance</h3>
                  <p className="text-muted-foreground">{t('version')}: {version || '0.1.0'}</p>
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <h4 className="font-medium mb-2 flex items-center gap-2">
                    <Cpu className="w-4 h-4" />
                    {t('systemInfo')}
                  </h4>
                  <dl className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">{t('buildDate')}</dt>
                      <dd>2024.01.15</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">{t('apiVersion')}</dt>
                      <dd>v1</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">{t('database')}</dt>
                      <dd>SQLite</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">{t('runtime')}</dt>
                      <dd>Python 3.11 / Node 18+</dd>
                    </div>
                  </dl>
                </div>
                <div>
                  <h4 className="font-medium mb-2 flex items-center gap-2">
                    <Shield className="w-4 h-4" />
                    {t('components')}
                  </h4>
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    <li>✓ {t('cameraManagement')}</li>
                    <li>✓ {t('motionObjectDetection')}</li>
                    <li>✓ {t('faceRecognition')}</li>
                    <li>✓ {t('actuatorControl')}</li>
                    <li>✓ {t('alarmSystem')}</li>
                    <li>✓ {t('multiChannelNotifications')}</li>
                    <li>✓ {t('telegramBotIntegration')}</li>
                    <li>✓ {t('webDashboard')}</li>
                  </ul>
                </div>
              </div>
              <Button variant="outline" disabled>
                <Info className="w-4 h-4 mr-2" />
                {t('checkForUpdates')}
              </Button>
            </CardContent>
          </Card>
          
          {/* API Health Status */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="w-5 h-5" />
                API Health Status
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {healthLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
              ) : health ? (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="flex items-center justify-between p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
                    <span className="text-sm text-muted-foreground">Status</span>
                    <span className="font-medium text-green-600 dark:text-green-400 flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-green-500" />
                      {health.status}
                    </span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                    <span className="text-sm text-muted-foreground">Version</span>
                    <span className="font-medium">{health.version}</span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                    <span className="text-sm text-muted-foreground">Database</span>
                    <span className="font-medium text-green-600 dark:text-green-400">
                      {health.database}
                    </span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                    <span className="text-sm text-muted-foreground">Redis</span>
                    <span className="font-medium text-green-600 dark:text-green-400">
                      {health.redis}
                    </span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                    <span className="text-sm text-muted-foreground">Cameras Online</span>
                    <span className="font-medium">{health.cameras_online} / {health.cameras_total}</span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                    <span className="text-sm text-muted-foreground">Active Alarms</span>
                    <span className="font-medium text-destructive">{health.active_alarms}</span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                    <span className="text-sm text-muted-foreground">Uptime</span>
                    <span className="font-medium">
                      {health.uptime_seconds ? `${Math.floor(health.uptime_seconds / 3600)}h ${Math.floor((health.uptime_seconds % 3600) / 60)}m` : '—'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                    <span className="text-sm text-muted-foreground">Last Check</span>
                    <span className="font-medium">{new Date().toLocaleString()}</span>
                  </div>
                </div>
              ) : (
                <p className="text-destructive">Failed to load health status</p>
              )}
              <Button variant="outline" size="sm" onClick={refetchHealth} disabled={healthLoading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${healthLoading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}