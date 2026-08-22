import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { useCameras, useActuators, useDetectors, useRules, type Rule, type RuleCreate, type RuleUpdate } from '@/hooks/useApiData';
import { Plus, Trash2, Edit, Loader2, Zap, Shield, Video, XCircle } from 'lucide-react';

export default function Rules() {
  const { t } = useTranslation('rules');
  const { siteId } = useParams<{ siteId: string }>();
  const navigate = useNavigate();
  
  const { cameras, loading: camerasLoading } = useCameras(siteId || '');
  const { actuators, loading: actuatorsLoading } = useActuators(siteId || '');
  const { detectors, loading: detectorsLoading } = useDetectors(siteId || '');
  const { rules, loading: rulesLoading, error, refetch, createRule, updateRule, deleteRule: deleteRuleApi } = useRules(siteId || '');
  
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [editingRule, setEditingRule] = useState<Rule | null>(null);
  const [selectedCamera, setSelectedCamera] = useState<string>('');
  const [selectedDetector, setSelectedDetector] = useState<string>('');
  const [selectedActuator, setSelectedActuator] = useState<string>('');
  const [selectedAction, setSelectedAction] = useState<'on' | 'off' | 'toggle'>('on');
  const [ruleName, setRuleName] = useState('');
  const [ruleDescription, setRuleDescription] = useState('');
  const [cooldownSeconds, setCooldownSeconds] = useState(30);
  const [isEnabled, setIsEnabled] = useState(true);
  const [dialogLoading, setDialogLoading] = useState(false);

  const resetForm = () => {
    setSelectedCamera('');
    setSelectedDetector('');
    setSelectedActuator('');
    setSelectedAction('on');
    setRuleName('');
    setRuleDescription('');
    setCooldownSeconds(30);
    setIsEnabled(true);
    setEditingRule(null);
  };

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCamera || !selectedActuator || !ruleName) return;
    
    setDialogLoading(true);
    try {
      const ruleData: RuleCreate = {
        name: ruleName,
        description: ruleDescription || undefined,
        camera_id: selectedCamera,
        detector_id: selectedDetector || undefined,
        actuator_id: selectedActuator,
        action: selectedAction,
        is_enabled: isEnabled,
        cooldown_seconds: cooldownSeconds,
      };
      
      if (editingRule) {
        await updateRule(editingRule.id, ruleData as RuleUpdate);
      } else {
        await createRule(ruleData);
      }
      
      setShowCreateDialog(false);
      resetForm();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setDialogLoading(false);
    }
  };

  const handleEditRule = (rule: Rule) => {
    setEditingRule(rule);
    setSelectedCamera(rule.camera_id);
    setSelectedDetector(rule.detector_id || '');
    setSelectedActuator(rule.actuator_id);
    setSelectedAction(rule.action);
    setRuleName(rule.name);
    setRuleDescription(rule.description || '');
    setCooldownSeconds(rule.cooldown_seconds);
    setIsEnabled(rule.is_enabled);
    setShowCreateDialog(true);
  };

  const handleDeleteRule = async (ruleId: string) => {
    if (!confirm(t('confirmDelete'))) return;
    
    try {
      await deleteRuleApi(ruleId);
      refetch();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleBack = () => {
    navigate(`/sites/${siteId}`);
  };

  if (camerasLoading || actuatorsLoading || detectorsLoading || rulesLoading) {
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
          <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
          <p className="text-muted-foreground">{t('description')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleBack}>
            <XCircle className="w-4 h-4 mr-2" />
            {t('backToSite')}
          </Button>
          <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="w-4 h-4 mr-2" />
                {t('addRule')}
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>{editingRule ? t('editRule') : t('addRule')}</DialogTitle>
                <DialogDescription>{editingRule ? t('editRuleDescription') : t('addRuleDescription')}</DialogDescription>
              </DialogHeader>
              <form onSubmit={handleCreateRule}>
                <div className="grid gap-4 py-4">
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="name" className="text-right">{t('name')}</Label>
                    <Input id="name" value={ruleName} onChange={e => setRuleName(e.target.value)} placeholder={t('ruleNamePlaceholder')} required />
                  </div>
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="description" className="text-right">{t('description')}</Label>
                    <Input id="description" value={ruleDescription} onChange={e => setRuleDescription(e.target.value)} placeholder={t('ruleDescriptionPlaceholder')} />
                  </div>
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="camera" className="text-right">{t('camera')}</Label>
                    <Select value={selectedCamera} onValueChange={setSelectedCamera}>
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
                    <Label htmlFor="detector" className="text-right">{t('detector')}</Label>
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
                    <Label htmlFor="actuator" className="text-right">{t('actuator')}</Label>
                    <Select value={selectedActuator} onValueChange={setSelectedActuator}>
                      <SelectTrigger id="actuator">
                        <SelectValue placeholder={t('selectActuator')} />
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
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="action" className="text-right">{t('action')}</Label>
                    <Select value={selectedAction} onValueChange={(v) => setSelectedAction(v as 'on' | 'off' | 'toggle')}>
                      <SelectTrigger id="action">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="on">{t('actionOn')}</SelectItem>
                        <SelectItem value="off">{t('actionOff')}</SelectItem>
                        <SelectItem value="toggle">{t('actionToggle')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="cooldown" className="text-right">{t('cooldown')}</Label>
                    <Input 
                      id="cooldown" 
                      type="number" 
                      value={cooldownSeconds} 
                      onChange={e => setCooldownSeconds(parseInt(e.target.value) || 0)}
                      min={0}
                      max={3600}
                      className="w-32"
                    />
                    <span className="text-sm text-muted-foreground">{t('seconds')}</span>
                  </div>
                  <div className="grid grid-cols-4 items-center gap-4">
                    <Label htmlFor="enabled" className="text-right">{t('enabled')}</Label>
                    <input
                      id="enabled"
                      type="checkbox"
                      checked={isEnabled}
                      onChange={e => setIsEnabled(e.target.checked)}
                      className="w-4 h-4"
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => { setShowCreateDialog(false); resetForm(); }}>
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
        </div>
      </div>

      {/* Rules Table */}
      <Card>
        <CardHeader>
          <CardTitle>{t('rulesList')}</CardTitle>
          <CardDescription>{t('rulesDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          {error && <div className="mb-4 p-4 bg-red-500/20 text-red-400 rounded">{error}</div>}
          {rules.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('name')}</TableHead>
                  <TableHead>{t('camera')}</TableHead>
                  <TableHead>{t('detector')}</TableHead>
                  <TableHead>{t('actuator')}</TableHead>
                  <TableHead>{t('action')}</TableHead>
                  <TableHead>{t('cooldown')}</TableHead>
                  <TableHead>{t('status')}</TableHead>
                  <TableHead className="text-right">{t('actions')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rules.map(rule => (
                  <TableRow key={rule.id}>
                    <TableCell>
                      <div>
                        <p className="font-medium">{rule.name}</p>
                        {rule.description && <p className="text-xs text-muted-foreground">{rule.description}</p>}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Video className="w-4 h-4 inline mr-1" />
                      {cameras.find(c => c.id === rule.camera_id)?.name || rule.camera_id}
                    </TableCell>
                    <TableCell>
                      {rule.detector_id ? (
                        <><Shield className="w-4 h-4 inline mr-1" />{detectors.find(d => d.id === rule.detector_id)?.name || rule.detector_id}</>
                      ) : (
                        <span className="text-muted-foreground">{t('none')}</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Zap className="w-4 h-4 inline mr-1" />
                      {actuators.find(a => a.id === rule.actuator_id)?.name || rule.actuator_id}
                    </TableCell>
                    <TableCell>
                      <Badge variant={
                        rule.action === 'on' ? 'default' :
                        rule.action === 'off' ? 'destructive' : 'secondary'
                      }>
                        {t(`action${rule.action.charAt(0).toUpperCase() + rule.action.slice(1)}`)}
                      </Badge>
                    </TableCell>
                    <TableCell>{rule.cooldown_seconds}{t('secondsShort')}</TableCell>
                    <TableCell>
                      <Badge variant={rule.is_enabled ? 'default' : 'outline'}>
                        {rule.is_enabled ? t('enabled') : t('disabled')}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon" onClick={() => handleEditRule(rule)}>
                        <Edit className="w-4 h-4" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => handleDeleteRule(rule.id)}>
                        <Trash2 className="w-4 h-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-center py-12">
              <Zap className="w-16 h-16 mx-auto mb-4 opacity-30" />
              <h3 className="text-lg font-medium mb-2">{t('noRules')}</h3>
              <p className="text-muted-foreground mb-4">{t('noRulesDescription')}</p>
              <Button onClick={() => setShowCreateDialog(true)}>
                <Plus className="w-4 h-4 mr-2" />
                {t('createFirstRule')}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick Reference */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Video className="w-5 h-5" />
              {t('availableCameras')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-64 overflow-auto">
              {cameras.map(camera => (
                <div key={camera.id} className="flex items-center justify-between p-2 border rounded">
                  <span className="text-sm">{camera.name}</span>
                  <Badge variant={camera.is_online ? 'default' : 'outline'} className="text-xs">
                    {camera.is_online ? t('online') : t('offline')}
                  </Badge>
                </div>
              ))}
              {cameras.length === 0 && <p className="text-center py-4 text-muted-foreground text-sm">{t('none')}</p>}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="w-5 h-5" />
              {t('availableDetectors')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-64 overflow-auto">
              {detectors.map(detector => (
                <div key={detector.id} className="flex items-center justify-between p-2 border rounded">
                  <span className="text-sm">{detector.name}</span>
                  <Badge variant="outline" className="text-xs">{detector.type}</Badge>
                </div>
              ))}
              {detectors.length === 0 && <p className="text-center py-4 text-muted-foreground text-sm">{t('none')}</p>}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="w-5 h-5" />
              {t('availableActuators')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-64 overflow-auto">
              {actuators.map(actuator => (
                <div key={actuator.id} className="flex items-center justify-between p-2 border rounded">
                  <span className="text-sm">{actuator.name}</span>
                  <Badge variant={actuator.is_online ? 'default' : 'outline'} className="text-xs">
                    {actuator.is_online ? t('online') : t('offline')}
                  </Badge>
                </div>
              ))}
              {actuators.length === 0 && <p className="text-center py-4 text-muted-foreground text-sm">{t('none')}</p>}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}