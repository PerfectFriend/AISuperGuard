import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableCaption } from '@/components/ui/table';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Plus, RefreshCw, Edit, Trash2, Play, Loader2, Wifi, WifiOff } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useParams } from 'react-router-dom';
import { useCameras } from '@/hooks/useApiData';

export default function Cameras() {
  const { t } = useTranslation('cameras');
  const { siteId } = useParams<{ siteId: string }>();
  const navigate = useNavigate();
  const { cameras, loading, error, refetch, createCamera, updateCamera, deleteCamera, testCamera } = useCameras(siteId || '');
  
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editingCamera, setEditingCamera] = useState<any>(null);
  const [testingCamera, setTestingCamera] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    type: 'rtsp',
    stream_url: '',
    username: '',
    password: '',
    width: 1920,
    height: 1080,
    fps: 25,
    ptz_enabled: false,
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const data = {
        name: formData.name,
        description: formData.description || undefined,
        type: formData.type as any,
        stream_url: formData.stream_url,
        username: formData.username || undefined,
        password: formData.password || undefined,
        width: formData.width,
        height: formData.height,
        fps: formData.fps,
        ptz_enabled: formData.ptz_enabled,
      };
      
      if (editingCamera) {
        await updateCamera(editingCamera.id, data);
      } else {
        await createCamera(data);
      }
      resetForm();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = (camera: any) => {
    setEditingCamera(camera);
    setFormData({
      name: camera.name,
      description: camera.description || '',
      type: camera.type,
      stream_url: camera.stream_url,
      username: camera.username || '',
      password: camera.password || '',
      width: camera.width,
      height: camera.height,
      fps: camera.fps,
      ptz_enabled: camera.ptz_enabled,
    });
    setIsEditOpen(true);
  };

  const handleDelete = async (cameraId: string) => {
    if (confirm(t('confirmDelete') || 'Are you sure?')) {
      try {
        await deleteCamera(cameraId);
      } catch (err: any) {
        alert(err.message);
      }
    }
  };

  const handleView = (cameraId: string) => {
    if (siteId) {
      navigate(`/sites/${siteId}/cameras/${cameraId}`);
    }
  };

  const handleTest = async (cameraId: string) => {
    setTestingCamera(cameraId);
    try {
      await testCamera(cameraId);
      alert(t('testSuccess') || 'Camera test successful');
    } catch (err: any) {
      alert(err.message);
    } finally {
      setTestingCamera(null);
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      type: 'rtsp',
      stream_url: '',
      username: '',
      password: '',
      width: 1920,
      height: 1080,
      fps: 25,
      ptz_enabled: false,
    });
    setEditingCamera(null);
    setIsCreateOpen(false);
    setIsEditOpen(false);
  };

  const openCreate = () => {
    resetForm();
    setIsCreateOpen(true);
  };

  const getStatusVariant = (isOnline: boolean) => isOnline ? 'secondary' : 'destructive';

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-12 w-12 animate-spin text-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <svg className="w-12 h-12 mx-auto text-destructive mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <p className="text-destructive">{t('errorLoading')}: {error}</p>
          <Button variant="outline" onClick={refetch} className="mt-4">
            <RefreshCw className="w-4 h-4 mr-2" />
            {t('retry')}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">{t('title')}</h2>
        <Button onClick={openCreate}>
          <Plus className="w-4 h-4 mr-2" />
          {t('addCamera')}
        </Button>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableCaption>
            {t('cameraList')} ({cameras.length} {t('total')})
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>{t('name')}</TableHead>
              <TableHead>{t('type')}</TableHead>
              <TableHead>{t('streamUrl')}</TableHead>
              <TableHead>{t('resolution')}</TableHead>
              <TableHead>{t('fps')}</TableHead>
              <TableHead>{t('status')}</TableHead>
              <TableHead>{t('ptz')}</TableHead>
              <TableHead className="w-48">{t('actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cameras.map((camera) => (
              <TableRow key={camera.id} className="hover:bg-accent">
                <TableCell className="font-medium">{camera.name}</TableCell>
                <TableCell>
                  <Badge variant="secondary">{camera.type.toUpperCase()}</Badge>
                </TableCell>
                <TableCell className="max-w-[200px] truncate" title={camera.stream_url}>
                  {camera.stream_url}
                </TableCell>
                <TableCell>{camera.width}x{camera.height}</TableCell>
                <TableCell>{camera.fps}</TableCell>
                <TableCell>
                  <Badge variant={getStatusVariant(camera.is_online)} className="flex items-center gap-1">
                    {camera.is_online ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
                    {camera.is_online ? t('online') : t('offline')}
                  </Badge>
                </TableCell>
                <TableCell>
                  {camera.ptz_enabled ? (
                    <Badge variant="secondary">{t('enabled')}</Badge>
                  ) : (
                    <Badge variant="outline">{t('disabled')}</Badge>
                  )}
                </TableCell>
                <TableCell className="flex items-center gap-1">
                  <Button variant="ghost" size="icon" onClick={() => handleView(camera.id)} aria-label={t('view')}>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M1 12s4-8 11-8 11 8-11 8-11-8-11-11-8z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12l-2-2 2-2 2 2 2 2-2 2-2 2 2-2z" />
                    </svg>
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => handleTest(camera.id)} 
                    disabled={testingCamera === camera.id} aria-label={t('test')}>
                    {testingCamera === camera.id ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Play className="w-4 h-4" />
                    )}
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => handleEdit(camera)} aria-label={t('edit')}>
                    <Edit className="w-4 h-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => handleDelete(camera.id)} aria-label={t('delete')} className="text-destructive hover:text-destructive">
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {cameras.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                  {t('noCameras') || 'No cameras configured. Add your first camera.'}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Create/Edit Dialog */}
      <Dialog open={isCreateOpen || isEditOpen} onOpenChange={(open) => { if (!open) resetForm(); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingCamera ? t('editCamera') : t('addCamera')}</DialogTitle>
            <DialogDescription>{editingCamera ? t('editCameraDescription') : t('addCameraDescription')}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit}>
            <div className="space-y-4 py-4">
              <div className="grid gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">{t('name')}</Label>
                  <Input
                    id="name"
                    value={formData.name}
                    onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                    placeholder={t('cameraNamePlaceholder')}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">{t('description')}</Label>
                  <Textarea
                    id="description"
                    value={formData.description}
                    onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                    placeholder={t('descriptionPlaceholder')}
                    rows={2}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="type">{t('type')}</Label>
                  <Select value={formData.type} onValueChange={(value) => setFormData(prev => ({ ...prev, type: value }))}>
                    <SelectTrigger id="type">
                      <SelectValue placeholder={t('selectType')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="rtsp">RTSP</SelectItem>
                      <SelectItem value="onvif">ONVIF</SelectItem>
                      <SelectItem value="http">HTTP</SelectItem>
                      <SelectItem value="hls">HLS</SelectItem>
                      <SelectItem value="webcam">Webcam</SelectItem>
                      <SelectItem value="file">File</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="stream_url">{t('streamUrl')}</Label>
                  <Input
                    id="stream_url"
                    value={formData.stream_url}
                    onChange={(e) => setFormData(prev => ({ ...prev, stream_url: e.target.value }))}
                    placeholder="rtsp://user:pass@192.168.1.100:554/stream1"
                    required
                  />
                </div>
                <div className="grid gap-4 grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="username">{t('username')}</Label>
                    <Input
                      id="username"
                      value={formData.username}
                      onChange={(e) => setFormData(prev => ({ ...prev, username: e.target.value }))}
                      placeholder={t('optional')}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">{t('password')}</Label>
                    <Input
                      id="password"
                      type="password"
                      value={formData.password}
                      onChange={(e) => setFormData(prev => ({ ...prev, password: e.target.value }))}
                      placeholder={t('optional')}
                    />
                  </div>
                </div>
                <div className="grid gap-4 grid-cols-3">
                  <div className="space-y-2">
                    <Label htmlFor="width">{t('width')}</Label>
                    <Input
                      id="width"
                      type="number"
                      value={formData.width}
                      onChange={(e) => setFormData(prev => ({ ...prev, width: parseInt(e.target.value) }))}
                      min={1}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="height">{t('height')}</Label>
                    <Input
                      id="height"
                      type="number"
                      value={formData.height}
                      onChange={(e) => setFormData(prev => ({ ...prev, height: parseInt(e.target.value) }))}
                      min={1}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="fps">{t('fps')}</Label>
                    <Input
                      id="fps"
                      type="number"
                      step="0.1"
                      value={formData.fps}
                      onChange={(e) => setFormData(prev => ({ ...prev, fps: parseFloat(e.target.value) }))}
                      min={0.1}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="ptz_enabled"
                    checked={formData.ptz_enabled}
                    onChange={(e) => setFormData(prev => ({ ...prev, ptz_enabled: e.target.checked }))}
                    className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                  />
                  <Label htmlFor="ptz_enabled">{t('ptzEnabled')}</Label>
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={resetForm}>
                {t('cancel')}
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    {t('saving')}
                  </>
                ) : (
                  t('save')
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}