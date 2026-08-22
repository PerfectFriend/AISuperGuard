import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { useCameras, useActuators, useDetectors } from '@/hooks/useApiData';
import { Plus, Trash2, Link2, Loader2, AlertTriangle, XCircle } from 'lucide-react';

interface Binding {
  id: string;
  camera_id: string;
  detector_id?: string;
  actuator_id: string;
  camera_name: string;
  detector_name?: string;
  actuator_name: string;
  is_active: boolean;
  created_at: string;
}

export default function CameraBindings() {
  const { t } = useTranslation('cameras');
  const { siteId } = useParams<{ siteId: string }>();
  const navigate = useNavigate();
  
  const { cameras, loading: camerasLoading, refetch: refetchCameras } = useCameras(siteId || '');
  const { actuators, loading: actuatorsLoading, refetch: refetchActuators } = useActuators(siteId || '');
  const { detectors, loading: detectorsLoading, refetch: refetchDetectors } = useDetectors(siteId || '');
  
  const [bindings, setBindings] = useState<Binding[]>([]);
  const [_loading, setLoading] = useState(false);
  const [_error, setError] = useState<string | null>(null);
  const [selectedCamera, setSelectedCamera] = useState<string>('');
  
  // Dialog states
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [selectedCameraForDialog, setSelectedCameraForDialog] = useState<string>('');
  const [selectedDetector, setSelectedDetector] = useState<string>('');
  const [selectedActuator, setSelectedActuator] = useState<string>('');
  const [dialogLoading, setDialogLoading] = useState(false);

  const fetchBindings = async () => {
    if (!siteId) return;
    try {
      setLoading(true);
      const token = localStorage.getItem('auth_token');
      const response = await fetch(`http://localhost:3001/api/v1/sites/${siteId}/cameras/bindings`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setBindings(data);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBindings();
    refetchCameras();
    refetchActuators();
    refetchDetectors();
  }, [siteId, refetchCameras, refetchActuators, refetchDetectors]);

  const handleCreateBinding = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!siteId || !selectedCameraForDialog || !selectedActuator) return;
    
    setDialogLoading(true);
    try {
      const token = localStorage.getItem('auth_token');
      const response = await fetch(`http://localhost:8080/api/v1/sites/${siteId}/cameras/${selectedCameraForDialog}/bindings`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          camera_id: selectedCameraForDialog,
          actuator_id: selectedActuator,
          detector_id: selectedDetector || undefined
        })
      });
      
      if (response.ok) {
        setShowCreateDialog(false);
        setSelectedCameraForDialog('');
        setSelectedDetector('');
        setSelectedActuator('');
        fetchBindings();
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setDialogLoading(false);
    }
  };

  const handleDeleteBinding = async (bindingId: string) => {
    if (!confirm(t('confirmDelete'))) return;
    
    try {
      const token = localStorage.getItem('auth_token');
      const response = await fetch(`http://localhost:8080/api/v1/sites/${siteId}/cameras/${selectedCamera}/bindings/${bindingId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        fetchBindings();
      }
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleBack = () => {
    navigate(`/sites/${siteId}/cameras`);
  };

  if (camerasLoading || actuatorsLoading || detectorsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-12 w-12 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('bindings')}</h1>
          <p className="text-muted-foreground">{t('detectionZone')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleBack}>
            <XCircle className="w-4 h-4 mr-2" />
            {t('backToCameras')}
          </Button>
        </div>
      </div>

      {/* Camera Selector */}
      <Card>
        <CardHeader>
          <CardTitle>{t('selectCamera')}</CardTitle>
        </CardHeader>
        <CardContent>
          <Select value={selectedCamera} onValueChange={setSelectedCamera}>
            <SelectTrigger className="w-full max-w-xs">
              <SelectValue placeholder={t('selectCamera')} />
            </SelectTrigger>
            <SelectContent>
              {cameras.map(camera => (
                <SelectItem key={camera.id} value={camera.id}>
                  {camera.name} ({camera.type})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {/* Bindings List */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>{t('bindings')}</CardTitle>
          <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="w-4 h-4 mr-2" />
                {t('addBinding')}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{t('addBinding')}</DialogTitle>
                <DialogDescription>{t('addCameraDescription')}</DialogDescription>
              </DialogHeader>
              <form onSubmit={handleCreateBinding}>
                <div className="grid gap-4 py-4">
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="camera" className="text-right">{t('name')}</Label>
                    <Select
                      value={selectedCameraForDialog}
                      onValueChange={setSelectedCameraForDialog}
                      disabled={!!selectedCamera}
                    >
                      <SelectTrigger id="camera">
                        <SelectValue placeholder={t('selectCamera')} />
                      </SelectTrigger>
                      <SelectContent>
                        {cameras.map(camera => (
                          <SelectItem key={camera.id} value={camera.id}>
                            {camera.name} ({camera.type})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="detector" className="text-right">{t('detectors')}</Label>
                    <Select value={selectedDetector} onValueChange={setSelectedDetector}>
                      <SelectTrigger id="detector">
                        <SelectValue placeholder={t('optional')} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="">{t('optional')}</SelectItem>
                        {detectors.map(detector => (
                          <SelectItem key={detector.id} value={detector.id}>
                            {detector.name} ({detector.type})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="actuator" className="text-right">{t('actuators')}</Label>
                    <Select value={selectedActuator} onValueChange={setSelectedActuator}>
                      <SelectTrigger id="actuator">
                        <SelectValue placeholder={t('selectType')} />
                      </SelectTrigger>
                      <SelectContent>
                        {actuators.map(actuator => (
                          <SelectItem key={actuator.id} value={actuator.id}>
                            {actuator.name} ({actuator.type})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setShowCreateDialog(false)}>
                    {t('cancel')}
                  </Button>
                  <Button type="submit" disabled={dialogLoading}>
                    {dialogLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                    {t('save')}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent>
          {selectedCamera ? (
            bindings.filter(b => b.camera_id === selectedCamera).length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('camera')}</TableHead>
                    <TableHead>{t('detectors')}</TableHead>
                    <TableHead>{t('actuators')}</TableHead>
                    <TableHead>{t('status')}</TableHead>
                    <TableHead className="text-right">{t('actions')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {bindings.filter(b => b.camera_id === selectedCamera).map(binding => (
                    <TableRow key={binding.id}>
                      <TableCell>{binding.camera_name}</TableCell>
                      <TableCell>{binding.detector_name || t('none')}</TableCell>
                      <TableCell>{binding.actuator_name}</TableCell>
                      <TableCell>
                        <Badge variant={binding.is_active ? 'default' : 'outline'}>
                          {binding.is_active ? t('active') : t('inactive')}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="icon" onClick={() => handleDeleteBinding(binding.id)}>
                          <Trash2 className="w-4 h-4 text-destructive" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Link2 className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>{t('noBindings')}</p>
                <p className="text-sm">{t('addBindingDesc')}</p>
              </div>
            )
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <AlertTriangle className="w-12 h-12 mx-auto mb-2 opacity-50" />
              <p>{t('selectCameraFirst')}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Available Components */}
      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>{t('availableDetectors')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {detectors.map(detector => (
                <div key={detector.id} className="flex items-center justify-between p-2 border rounded">
                  <div>
                    <p className="font-medium text-sm">{detector.name}</p>
                    <p className="text-xs text-muted-foreground">{detector.type} • classes: {detector.classes.length}</p>
                  </div>
                  <Badge variant="outline">{detector.type}</Badge>
                </div>
              ))}
              {detectors.length === 0 && (
                <p className="text-center py-4 text-muted-foreground">{t('none')}</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t('availableActuators')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {actuators.map(actuator => (
                <div key={actuator.id} className="flex items-center justify-between p-2 border rounded">
                  <div>
                    <p className="font-medium text-sm">{actuator.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {actuator.type} • {actuator.is_online ? t('online') : t('offline')}
                    </p>
                  </div>
                  <Badge variant={actuator.is_online ? 'default' : 'outline'}>
                    {actuator.is_online ? t('online') : t('offline')}
                  </Badge>
                </div>
              ))}
              {actuators.length === 0 && (
                <p className="text-center py-4 text-muted-foreground">{t('none')}</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t('availableCameras')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {cameras.map(camera => (
                <div key={camera.id} className="flex items-center justify-between p-2 border rounded">
                  <div>
                    <p className="font-medium text-sm">{camera.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {camera.type} • {camera.is_online ? t('online') : t('offline')}
                    </p>
                  </div>
                  <Badge variant={camera.is_online ? 'default' : 'outline'}>
                    {camera.is_online ? t('online') : t('offline')}
                  </Badge>
                </div>
              ))}
              {cameras.length === 0 && (
                <p className="text-center py-4 text-muted-foreground">{t('none')}</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}