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
import { Plus, RefreshCw, Edit, Trash2, Loader2, Eye, Brain, Zap, Activity } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { useDetectors } from '@/hooks/useApiData';

export default function Detectors() {
  const { t } = useTranslation('detectors');
  const { siteId } = useParams<{ siteId: string }>();
  const { detectors, loading, error, refetch, createDetector, updateDetector, deleteDetector, testDetector } = useDetectors(siteId || '');
  
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editingDetector, setEditingDetector] = useState<any>(null);
  const [testingDetector, setTestingDetector] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    type: 'yolo',
    model_path: '',
    classes: '',
    confidence_threshold: 0.5,
    iou_threshold: 0.45,
    require_frames: 3,
    auto_resolve_frames: 10,
    is_enabled: true,
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
        model_path: formData.model_path || undefined,
        classes: formData.classes ? formData.classes.split(',').map(c => parseInt(c.trim())).filter(c => !isNaN(c)) : [],
        confidence_threshold: formData.confidence_threshold,
        iou_threshold: formData.iou_threshold,
        require_frames: formData.require_frames,
        auto_resolve_frames: formData.auto_resolve_frames,
        is_enabled: formData.is_enabled,
      };
      
      if (editingDetector) {
        await updateDetector(editingDetector.id, data);
      } else {
        await createDetector(data);
      }
      resetForm();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = (detector: any) => {
    setEditingDetector(detector);
    setFormData({
      name: detector.name,
      description: detector.description || '',
      type: detector.type,
      model_path: detector.model_path || '',
      classes: detector.classes?.join(', ') || '',
      confidence_threshold: detector.confidence_threshold,
      iou_threshold: detector.iou_threshold,
      require_frames: detector.require_frames,
      auto_resolve_frames: detector.auto_resolve_frames,
      is_enabled: detector.is_enabled,
    });
    setIsEditOpen(true);
  };

  const handleDelete = async (detectorId: string) => {
    if (confirm(t('confirmDelete') || 'Are you sure?')) {
      try {
        await deleteDetector(detectorId);
      } catch (err: any) {
        alert(err.message);
      }
    }
  };

  const handleTest = async (detectorId: string) => {
    setTestingDetector(detectorId);
    try {
      await testDetector(detectorId);
      alert(t('testSuccess') || 'Detector test successful');
    } catch (err: any) {
      alert(err.message);
    } finally {
      setTestingDetector(null);
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      type: 'yolo',
      model_path: '',
      classes: '',
      confidence_threshold: 0.5,
      iou_threshold: 0.45,
      require_frames: 3,
      auto_resolve_frames: 10,
      is_enabled: true,
    });
    setEditingDetector(null);
    setIsCreateOpen(false);
    setIsEditOpen(false);
  };

  const openCreate = () => {
    resetForm();
    setIsCreateOpen(true);
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'yolo': return <Brain className="w-3 h-3" />;
      case 'motion': return <Activity className="w-3 h-3" />;
      default: return <Zap className="w-3 h-3" />;
    }
  };

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
          {t('addDetector')}
        </Button>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableCaption>
            {t('detectorList')} ({detectors.length} {t('total')})
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>{t('name')}</TableHead>
              <TableHead>{t('type')}</TableHead>
              <TableHead>{t('model')}</TableHead>
              <TableHead>{t('classes')}</TableHead>
              <TableHead>{t('confidence')}</TableHead>
              <TableHead>{t('iou')}</TableHead>
              <TableHead>{t('requireFrames')}</TableHead>
              <TableHead>{t('autoResolve')}</TableHead>
              <TableHead>{t('status')}</TableHead>
              <TableHead className="w-48">{t('actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {detectors.map((detector) => (
              <TableRow key={detector.id} className="hover:bg-accent">
                <TableCell className="font-medium">{detector.name}</TableCell>
                <TableCell>
                  <Badge variant="secondary" className="flex items-center gap-1">
                    {getTypeIcon(detector.type)}
                    {detector.type.toUpperCase()}
                  </Badge>
                </TableCell>
                <TableCell className="max-w-[150px] truncate font-mono text-sm">
                  {detector.model_path || '—'}
                </TableCell>
                <TableCell>
                  {detector.classes?.length > 0 ? (
                    <span className="flex flex-wrap gap-1">
                      {detector.classes.map((c: number) => (
                        <Badge key={c} variant="outline" className="text-xs">{c}</Badge>
                      ))}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell>{detector.confidence_threshold}</TableCell>
                <TableCell>{detector.iou_threshold}</TableCell>
                <TableCell>{detector.require_frames}</TableCell>
                <TableCell>{detector.auto_resolve_frames}</TableCell>
                <TableCell>
                  <Badge variant={detector.is_enabled ? 'secondary' : 'outline'}>
                    {detector.is_enabled ? t('enabled') : t('disabled')}
                  </Badge>
                </TableCell>
                <TableCell className="flex items-center gap-1">
                  <Button variant="ghost" size="icon" onClick={() => handleTest(detector.id)} 
                    disabled={testingDetector === detector.id} aria-label={t('test')}>
                    {testingDetector === detector.id ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Eye className="w-4 h-4" />
                    )}
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => handleEdit(detector)} aria-label={t('edit')}>
                    <Edit className="w-4 h-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => handleDelete(detector.id)} aria-label={t('delete')} className="text-destructive hover:text-destructive">
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {detectors.length === 0 && (
              <TableRow>
                <TableCell colSpan={10} className="text-center py-8 text-muted-foreground">
                  {t('noDetectors') || 'No detectors configured. Add your first detector.'}
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
            <DialogTitle>{editingDetector ? t('editDetector') : t('addDetector')}</DialogTitle>
            <DialogDescription>{editingDetector ? t('editDetectorDescription') : t('addDetectorDescription')}</DialogDescription>
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
                    placeholder={t('detectorNamePlaceholder')}
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
                      <SelectItem value="yolo">YOLO (Object Detection)</SelectItem>
                      <SelectItem value="motion">Motion Detection</SelectItem>
                      <SelectItem value="custom">Custom Model</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="model_path">{t('modelPath')}</Label>
                  <Input
                    id="model_path"
                    value={formData.model_path}
                    onChange={(e) => setFormData(prev => ({ ...prev, model_path: e.target.value }))}
                    placeholder="/home/thomas/SuperGuard/yolo11n.pt"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="classes">{t('classes')} (comma separated)</Label>
                  <Input
                    id="classes"
                    value={formData.classes}
                    onChange={(e) => setFormData(prev => ({ ...prev, classes: e.target.value }))}
                    placeholder="2,3,5,7 (COCO: car=2, motorcycle=3, bus=5, truck=7)"
                  />
                </div>
                <div className="grid gap-4 grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="confidence_threshold">{t('confidenceThreshold')}</Label>
                    <Input
                      id="confidence_threshold"
                      type="number"
                      step="0.01"
                      min="0"
                      max="1"
                      value={formData.confidence_threshold}
                      onChange={(e) => setFormData(prev => ({ ...prev, confidence_threshold: parseFloat(e.target.value) }))}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="iou_threshold">{t('iouThreshold')}</Label>
                    <Input
                      id="iou_threshold"
                      type="number"
                      step="0.01"
                      min="0"
                      max="1"
                      value={formData.iou_threshold}
                      onChange={(e) => setFormData(prev => ({ ...prev, iou_threshold: parseFloat(e.target.value) }))}
                    />
                  </div>
                </div>
                <div className="grid gap-4 grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="require_frames">{t('requireFrames')}</Label>
                    <Input
                      id="require_frames"
                      type="number"
                      min="1"
                      value={formData.require_frames}
                      onChange={(e) => setFormData(prev => ({ ...prev, require_frames: parseInt(e.target.value) }))}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="auto_resolve_frames">{t('autoResolveFrames')}</Label>
                    <Input
                      id="auto_resolve_frames"
                      type="number"
                      min="1"
                      value={formData.auto_resolve_frames}
                      onChange={(e) => setFormData(prev => ({ ...prev, auto_resolve_frames: parseInt(e.target.value) }))}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="is_enabled"
                    checked={formData.is_enabled}
                    onChange={(e) => setFormData(prev => ({ ...prev, is_enabled: e.target.checked }))}
                    className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                  />
                  <Label htmlFor="is_enabled">{t('enabled')}</Label>
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