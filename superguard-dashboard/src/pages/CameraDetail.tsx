import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowLeft, Video, Shield, Zap, Settings, Loader2, AlertTriangle, Plus, Link2, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { useCameras, useActuators, useDetectors, useAlarms, type Camera, type ActuatorBinding } from '@/hooks/useApiData';
import { VideoPlayer } from '@/components/VideoPlayer';
import { api } from '@/api/api';

export default function CameraDetail() {
  const { t } = useTranslation('cameras');
  const { siteId, cameraId } = useParams<{ siteId: string; cameraId: string }>();
  const navigate = useNavigate();
  
  const { cameras, loading: camerasLoading } = useCameras(siteId || '');
  const { actuators } = useActuators(siteId || '');
  const { detectors } = useDetectors(siteId || '');
  const { alarms } = useAlarms(siteId || '');
  
  const [camera, setCamera] = useState<Camera | null>(null);
  const [bindings, setBindings] = useState<ActuatorBinding[]>([]);
  const [bindingLoading, setBindingLoading] = useState(false);

  useEffect(() => {
    if (cameras.length > 0) {
      const found = cameras.find(c => c.id === cameraId);
      setCamera(found || null);
    }
  }, [cameras, cameraId]);

  // Fetch bindings when camera loads
  useEffect(() => {
    if (cameraId && siteId) {
      fetchBindings();
    }
  }, [cameraId, siteId]);

  const fetchBindings = async () => {
    if (!cameraId || !siteId) return;
    setBindingLoading(true);
    try {
      const data = await api.getBindings(siteId, cameraId);
      setBindings(data);
    } catch (err: any) {
      console.error('Failed to fetch bindings:', err);
    } finally {
      setBindingLoading(false);
    }
  };

  const handleBindActuator = async (actuatorId: string, actuatorName: string) => {
    if (!cameraId || !siteId) return;
    try {
      await api.createBinding(siteId, cameraId, { actuator_id: actuatorId });
      fetchBindings();
      alert(`${t('boundTo') || 'Bound to'} ${actuatorName}`);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleBindDetector = async (detectorId: string, detectorName: string) => {
    if (!cameraId || !siteId) return;
    try {
      await api.createBinding(siteId, cameraId, { actuator_id: '', detector_id: detectorId });
      fetchBindings();
      alert(`${t('boundTo') || 'Bound to'} ${detectorName}`);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleUnbind = async (bindingId: string) => {
    if (!cameraId || !siteId) return;
    try {
      await api.deleteBinding(siteId, cameraId, bindingId);
      fetchBindings();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const isActuatorBound = (actuatorId: string) => 
    bindings.some(b => b.actuator_id === actuatorId && b.is_active);
  
  const isDetectorBound = (detectorId: string) => 
    bindings.some(b => b.detector_id === detectorId && b.is_active);

  const cameraAlarms = alarms.filter(a => a.camera_id === cameraId);
  const activeAlarms = cameraAlarms.filter(a => a.state === 'triggered');

  if (camerasLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-12 w-12 animate-spin text-primary" />
      </div>
    );
  }

  if (!camera) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <AlertTriangle className="w-12 h-12 mx-auto text-destructive mb-4" />
          <p className="text-destructive">{t('cameraNotFound') || 'Camera not found'}</p>
          <Button variant="outline" onClick={() => navigate(`/sites/${siteId}/cameras`)} className="mt-4">
            <ArrowLeft className="w-4 h-4 mr-2" />
            {t('backToCameras')}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="icon" onClick={() => navigate(`/sites/${siteId}/cameras`)}>
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div className="flex-1 text-center">
          <h1 className="text-2xl font-bold">{camera.name}</h1>
          <p className="text-muted-foreground">{camera.description || t('noDescription')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={camera.is_online ? 'secondary' : 'destructive'} className="flex items-center gap-1">
            {camera.is_online ? <span className="w-2 h-2 rounded-full bg-green-500" /> : <span className="w-2 h-2 rounded-full bg-red-500" />}
            {camera.is_online ? t('online') : t('offline')}
          </Badge>
          <Badge variant="secondary">{camera.type.toUpperCase()}</Badge>
        </div>
      </div>

      {/* Video Player */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Video className="w-5 h-5" />
            {t('liveView')}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <VideoPlayer
            src={camera.stream_url}
            type={camera.type as any}
            width={1280}
            height={720}
            muted={true}
            controls={true}
          />
        </CardContent>
      </Card>

      {/* Details Tabs */}
      <Tabs defaultValue="info" className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="info">
            <span className="flex items-center gap-2 justify-center">
              <Settings className="w-4 h-4" />
              {t('info')}
            </span>
          </TabsTrigger>
          <TabsTrigger value="alarms">
            <span className="flex items-center gap-2 justify-center">
              <AlertTriangle className="w-4 h-4" />
              {t('alarms')} ({activeAlarms.length})
            </span>
          </TabsTrigger>
          <TabsTrigger value="bindings">
            <span className="flex items-center gap-2 justify-center">
              <Zap className="w-4 h-4" />
              {t('bindings')}
            </span>
          </TabsTrigger>
          <TabsTrigger value="detectors">
            <span className="flex items-center gap-2 justify-center">
              <Shield className="w-4 h-4" />
              {t('detectors')}
            </span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="info" className="mt-4 space-y-6">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-muted-foreground">{t('resolution')}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{camera.width}x{camera.height}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-muted-foreground">{t('fps')}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{camera.fps}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-muted-foreground">{t('ptz')}</CardTitle>
              </CardHeader>
              <CardContent>
                <Badge variant={camera.ptz_enabled ? 'secondary' : 'outline'}>
                  {camera.ptz_enabled ? t('enabled') : t('disabled')}
                </Badge>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-muted-foreground">{t('streamUrl')}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm font-mono truncate" title={camera.stream_url}>{camera.stream_url}</p>
              </CardContent>
            </Card>
          </div>

          {camera.zone && (
            <Card>
              <CardHeader>
                <CardTitle>{t('detectionZone')}</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="bg-gray-100 dark:bg-gray-800 p-4 rounded text-sm overflow-auto">
                  {JSON.stringify(camera.zone, null, 2)}
                </pre>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>{t('streamUrl')}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2 flex-wrap">
                <input 
                  type="text" 
                  value={camera.stream_url} 
                  readOnly 
                  className="flex-1 px-3 py-2 bg-gray-100 dark:bg-gray-800 border rounded font-mono text-sm"
                />
                <Button variant="outline" onClick={() => navigator.clipboard.writeText(camera.stream_url)}>
                  <Link2 className="w-4 h-4 mr-2" />
                  {t('copyUrl')}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="alarms" className="mt-4">
          {cameraAlarms.length > 0 ? (
            <div className="space-y-3">
              {cameraAlarms.map((alarm) => (
                <Card key={alarm.id} className={alarm.state === 'triggered' ? 'border-destructive/50' : ''}>
                  <CardContent className="flex items-center justify-between p-4">
                    <div className="flex items-center gap-4">
                      <div className={`w-3 h-3 rounded-full ${alarm.state === 'triggered' ? 'bg-red-500' : alarm.state === 'acknowledged' ? 'bg-yellow-500' : 'bg-green-500'}`} />
                      <div>
                        <p className="font-medium">{alarm.detection_class || t('unknown')}</p>
                        <p className="text-sm text-muted-foreground">
                          {new Date(alarm.created_at).toLocaleString()} • {alarm.confidence !== null ? `${(alarm.confidence * 100).toFixed(1)}%` : t('noConfidence')}
                        </p>
                      </div>
                    </div>
                    <Badge variant={
                      alarm.state === 'triggered' ? 'destructive' :
                      alarm.state === 'acknowledged' ? 'secondary' : 'outline'
                    } className="capitalize">
                      {alarm.state}
                    </Badge>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                <AlertTriangle className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>{t('noAlarms') || 'No alarms for this camera'}</p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="bindings" className="mt-4">
          {/* Actuator Bindings */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>{t('actuatorBindings')}</CardTitle>
            </CardHeader>
            <CardContent>
              {actuators.length > 0 ? (
                <div className="space-y-3">
                  {actuators.map((actuator) => {
                    const bound = isActuatorBound(actuator.id);
                    const binding = bindings.find(b => b.actuator_id === actuator.id && b.is_active);
                    return (
                      <div key={actuator.id} className="flex items-center justify-between p-3 border rounded-lg">
                        <div className="flex items-center gap-3">
                          <Badge variant="secondary">{actuator.type.toUpperCase()}</Badge>
                          <span className="font-medium">{actuator.name}</span>
                          <Badge variant={actuator.is_online ? 'secondary' : 'destructive'}>
                            {actuator.is_online ? t('online') : t('offline')}
                          </Badge>
                          {bound && (
                            <Badge variant="secondary" className="flex items-center gap-1">
                              <Link2 className="w-3 h-3" />
                              {t('bound')}
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {bound ? (
                            <Button 
                              variant="outline" 
                              size="sm" 
                              onClick={() => handleUnbind(binding!.id)}
                              disabled={bindingLoading}
                            >
                              <Trash2 className="w-4 h-4 mr-1" />
                              {t('unbind')}
                            </Button>
                          ) : (
                            <Button 
                              variant="outline" 
                              size="sm" 
                              onClick={() => handleBindActuator(actuator.id, actuator.name)}
                              disabled={bindingLoading || !actuator.is_online || !actuator.is_enabled}
                            >
                              <Plus className="w-4 h-4 mr-1" />
                              {t('bind')}
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-muted-foreground text-center py-8">{t('noActuatorsAvailable')}</p>
              )}
            </CardContent>
          </Card>

          {/* Detector Bindings */}
          <Card className="mt-4">
            <CardHeader>
              <CardTitle>{t('detectorBindings')}</CardTitle>
            </CardHeader>
            <CardContent>
              {detectors.length > 0 ? (
                <div className="space-y-3">
                  {detectors.map((detector) => {
                    const bound = isDetectorBound(detector.id);
                    const binding = bindings.find(b => b.detector_id === detector.id && b.is_active);
                    return (
                      <div key={detector.id} className="flex items-center justify-between p-3 border rounded-lg">
                        <div className="flex items-center gap-3">
                          <Badge variant="secondary">{detector.type.toUpperCase()}</Badge>
                          <span className="font-medium">{detector.name}</span>
                          <Badge variant={detector.is_enabled ? 'secondary' : 'outline'}>
                            {detector.is_enabled ? t('enabled') : t('disabled')}
                          </Badge>
                          {bound && (
                            <Badge variant="secondary" className="flex items-center gap-1">
                              <Link2 className="w-3 h-3" />
                              {t('bound')}
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {bound ? (
                            <Button 
                              variant="outline" 
                              size="sm" 
                              onClick={() => handleUnbind(binding!.id)}
                              disabled={bindingLoading}
                            >
                              <Trash2 className="w-4 h-4 mr-1" />
                              {t('unbind')}
                            </Button>
                          ) : (
                            <Button 
                              variant="outline" 
                              size="sm" 
                              onClick={() => handleBindDetector(detector.id, detector.name)}
                              disabled={bindingLoading || !detector.is_enabled}
                            >
                              <Plus className="w-4 h-4 mr-1" />
                              {t('bind')}
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-muted-foreground text-center py-8">{t('noDetectorsAvailable')}</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="detectors" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>{t('detectors')}</CardTitle>
            </CardHeader>
            <CardContent>
              {detectors.length > 0 ? (
                <div className="space-y-3">
                  {detectors.map((detector) => (
                    <div key={detector.id} className="flex items-center justify-between p-3 border rounded-lg">
                      <div className="flex items-center gap-3">
                        <Badge variant="secondary">{detector.type.toUpperCase()}</Badge>
                        <span className="font-medium">{detector.name}</span>
                        <Badge variant={detector.is_enabled ? 'secondary' : 'outline'}>
                          {detector.is_enabled ? t('enabled') : t('disabled')}
                        </Badge>
                      </div>
                      <Button variant="outline" size="sm" disabled>
                        {t('infoOnly')}
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-center py-8">{t('noDetectorsAvailable')}</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}