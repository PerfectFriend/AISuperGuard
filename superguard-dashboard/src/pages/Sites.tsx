import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableCaption } from '@/components/ui/table';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Plus, RefreshCw, Edit, Trash2, MapPin, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSites } from '@/hooks/useApiData';

export default function Sites() {
  const { t } = useTranslation('sites');
  const { sites, loading, error, refetch, createSite, updateSite, deleteSite } = useSites();
  
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editingSite, setEditingSite] = useState<any>(null);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    timezone: 'UTC',
    latitude: '',
    longitude: '',
    is_active: true,
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const data = {
        name: formData.name,
        description: formData.description || undefined,
        timezone: formData.timezone,
        latitude: formData.latitude ? parseFloat(formData.latitude) : undefined,
        longitude: formData.longitude ? parseFloat(formData.longitude) : undefined,
        is_active: formData.is_active,
      };
      
      if (editingSite) {
        await updateSite(editingSite.id, data);
      } else {
        await createSite(data);
      }
      resetForm();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = (site: any) => {
    setEditingSite(site);
    setFormData({
      name: site.name,
      description: site.description || '',
      timezone: site.timezone,
      latitude: site.latitude?.toString() || '',
      longitude: site.longitude?.toString() || '',
      is_active: site.is_active,
    });
    setIsEditOpen(true);
  };

  const handleDelete = async (siteId: string) => {
    if (confirm(t('confirmDelete') || 'Are you sure?')) {
      try {
        await deleteSite(siteId);
      } catch (err: any) {
        alert(err.message);
      }
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      timezone: 'UTC',
      latitude: '',
      longitude: '',
      is_active: true,
    });
    setEditingSite(null);
    setIsCreateOpen(false);
    setIsEditOpen(false);
  };

  const openCreate = () => {
    resetForm();
    setIsCreateOpen(true);
  };

  const getStatusVariant = (isActive: boolean) => isActive ? 'secondary' : 'destructive';

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
          {t('addSite')}
        </Button>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableCaption>
            {t('siteList')} ({sites.length} {t('total')})
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>{t('name')}</TableHead>
              <TableHead>{t('location')}</TableHead>
              <TableHead>{t('coordinates')}</TableHead>
              <TableHead>{t('cameras')}</TableHead>
              <TableHead>{t('actuators')}</TableHead>
              <TableHead>{t('detectors')}</TableHead>
              <TableHead>{t('activeAlarms')}</TableHead>
              <TableHead>{t('status')}</TableHead>
              <TableHead className="w-32">{t('actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sites.map((site) => (
              <TableRow key={site.id} className="hover:bg-accent">
                <TableCell className="font-medium">{site.name}</TableCell>
                <TableCell>{site.description || '—'}</TableCell>
                <TableCell>
                  {site.latitude && site.longitude ? (
                    <span className="flex items-center gap-1 text-sm">
                      <MapPin className="w-3 h-3 text-muted-foreground" />
                      {site.latitude.toFixed(4)}, {site.longitude.toFixed(4)}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">{t('notSet')}</span>
                  )}
                </TableCell>
                <TableCell>{site.camera_count}</TableCell>
                <TableCell>{site.actuator_count}</TableCell>
                <TableCell>{site.detector_count}</TableCell>
                <TableCell>
                  <Badge variant={site.active_alarms > 0 ? 'destructive' : 'secondary'}>
                    {site.active_alarms}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={getStatusVariant(site.is_active)}>
                    {site.is_active ? t('active') : t('inactive')}
                  </Badge>
                </TableCell>
                <TableCell className="flex items-center gap-2">
                  <Button variant="ghost" size="icon" onClick={() => handleEdit(site)} aria-label={t('edit')}>
                    <Edit className="w-4 h-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => handleDelete(site.id)} aria-label={t('delete')} className="text-destructive hover:text-destructive">
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {sites.length === 0 && (
              <TableRow>
                <TableCell colSpan={9} className="text-center py-8 text-muted-foreground">
                  {t('noSites') || 'No sites configured. Create your first site.'}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Create/Edit Dialog */}
      <Dialog open={isCreateOpen || isEditOpen} onOpenChange={(open) => { if (!open) resetForm(); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editingSite ? t('editSite') : t('addSite')}</DialogTitle>
            <DialogDescription>{editingSite ? t('editSiteDescription') : t('addSiteDescription')}</DialogDescription>
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
                    placeholder={t('siteNamePlaceholder')}
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
                    rows={3}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="timezone">{t('timezone')}</Label>
                  <Input
                    id="timezone"
                    value={formData.timezone}
                    onChange={(e) => setFormData(prev => ({ ...prev, timezone: e.target.value }))}
                    placeholder="UTC"
                  />
                </div>
                <div className="grid gap-4 grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="latitude">{t('latitude')}</Label>
                    <Input
                      id="latitude"
                      type="number"
                      step="0.0001"
                      value={formData.latitude}
                      onChange={(e) => setFormData(prev => ({ ...prev, latitude: e.target.value }))}
                      placeholder="-6.1754"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="longitude">{t('longitude')}</Label>
                    <Input
                      id="longitude"
                      type="number"
                      step="0.0001"
                      value={formData.longitude}
                      onChange={(e) => setFormData(prev => ({ ...prev, longitude: e.target.value }))}
                      placeholder="106.8272"
                    />
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="is_active"
                    checked={formData.is_active}
                    onChange={(e) => setFormData(prev => ({ ...prev, is_active: e.target.checked }))}
                    className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                  />
                  <Label htmlFor="is_active">{t('isActive')}</Label>
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