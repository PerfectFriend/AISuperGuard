import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableCaption } from '@/components/ui/table';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { RefreshCw, CheckCircle, VolumeX, Trash2, Loader2, AlertTriangle, Shield } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { useAlarms, useSites } from '@/hooks/useApiData';

export default function Alarms() {
  const { t } = useTranslation('alarms');
  const { siteId } = useParams<{ siteId: string }>();
  const { alarms, loading, error, refetch, acknowledge, silence } = useAlarms(siteId || '');
  const { sites } = useSites();
  
  const [ackNote, setAckNote] = useState('');
  const [ackAlarmId, setAckAlarmId] = useState<string | null>(null);
  const [isAckOpen, setIsAckOpen] = useState(false);
  const [submittingAck, setSubmittingAck] = useState(false);

  const getSiteName = (siteId: string) => {
    const site = sites.find(s => s.id === siteId);
    return site?.name || siteId;
  };

  const getStateVariant = (state: string) => {
    switch (state) {
      case 'triggered': return 'destructive';
      case 'acknowledged': return 'secondary';
      case 'resolved': return 'outline';
      case 'silenced': return 'secondary';
      default: return 'outline';
    }
  };

  const getStateLabel = (state: string) => {
    switch (state) {
      case 'triggered': return t('triggered');
      case 'acknowledged': return t('acknowledged');
      case 'resolved': return t('resolved');
      case 'silenced': return t('silenced');
      default: return state;
    }
  };

  const handleAcknowledge = async (alarmId: string) => {
    setAckAlarmId(alarmId);
    setAckNote('');
    setIsAckOpen(true);
  };

  const confirmAcknowledge = async () => {
    if (!ackAlarmId) return;
    setSubmittingAck(true);
    try {
      await acknowledge(ackAlarmId, ackNote);
      setIsAckOpen(false);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSubmittingAck(false);
    }
  };

  const handleSilence = async (alarmId: string) => {
    try {
      await silence(alarmId);
    } catch (err: any) {
      alert(err.message);
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
          <AlertTriangle className="w-12 h-12 mx-auto text-destructive mb-4" />
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
        <Button variant="outline" size="sm" onClick={refetch}>
          <RefreshCw className="w-4 h-4 mr-2" />
          {t('refresh')}
        </Button>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableCaption>
            {t('alarmHistory')} ({alarms.length} {t('total')})
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>{t('time')}</TableHead>
              <TableHead>{t('site')}</TableHead>
              <TableHead>{t('camera')}</TableHead>
              <TableHead>{t('detector')}</TableHead>
              <TableHead>{t('type')}</TableHead>
              <TableHead>{t('confidence')}</TableHead>
              <TableHead>{t('status')}</TableHead>
              <TableHead className="w-48">{t('actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {alarms.map((alarm: any) => (
              <TableRow key={alarm.id} className={`hover:bg-accent ${alarm.state === 'triggered' ? 'bg-destructive/5' : ''}`}>
                <TableCell>{new Date(alarm.created_at).toLocaleString()}</TableCell>
                <TableCell>{getSiteName(alarm.site_id)}</TableCell>
                <TableCell>{alarm.camera_id.slice(0, 8)}...</TableCell>
                <TableCell>{alarm.detector_id.slice(0, 8)}...</TableCell>
                <TableCell>{alarm.detection_class || '—'}</TableCell>
                <TableCell>
                  {alarm.confidence !== null ? `${(alarm.confidence * 100).toFixed(1)}%` : '—'}
                </TableCell>
                <TableCell>
                  <Badge variant={getStateVariant(alarm.state)} className="capitalize">
                    {getStateLabel(alarm.state)}
                  </Badge>
                </TableCell>
                <TableCell className="flex items-center gap-1">
                  {alarm.state === 'triggered' && (
                    <>
                      <Button variant="ghost" size="icon" onClick={() => handleAcknowledge(alarm.id)} aria-label={t('acknowledge')}>
                        <CheckCircle className="w-4 h-4 text-green-600" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => handleSilence(alarm.id)} aria-label={t('silence')}>
                        <VolumeX className="w-4 h-4 text-yellow-600" />
                      </Button>
                    </>
                  )}
                  <Button variant="ghost" size="icon" aria-label={t('view')} className="opacity-50 hover:opacity-100">
                    <Shield className="w-4 h-4" />
                  </Button>
                  <Button variant="ghost" size="icon" aria-label={t('delete')} className="text-destructive hover:text-destructive opacity-50 hover:opacity-100">
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {alarms.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                  <AlertTriangle className="w-12 h-12 mx-auto mb-2 opacity-50" />
                  <p>{t('noAlarms') || 'No alarms recorded'}</p>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Acknowledge Dialog */}
      <Dialog open={isAckOpen} onOpenChange={(open) => { if (!open) { setAckAlarmId(null); setAckNote(''); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-green-600" />
              {t('acknowledgeAlarm')}
            </DialogTitle>
            <DialogDescription>{t('acknowledgeDescription')}</DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <div className="space-y-2">
              <Label htmlFor="ack_note">{t('note')}</Label>
              <Textarea
                id="ack_note"
                value={ackNote}
                onChange={(e) => setAckNote(e.target.value)}
                placeholder={t('notePlaceholder')}
                rows={4}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setIsAckOpen(false)}>
              {t('cancel')}
            </Button>
            <Button onClick={confirmAcknowledge} disabled={submittingAck}>
              {submittingAck ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {t('acknowledging')}
                </>
              ) : (
                t('acknowledge')
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}