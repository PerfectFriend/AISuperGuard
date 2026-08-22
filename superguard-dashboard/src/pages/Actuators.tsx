import { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Plus, RefreshCw, Power, Loader2, Wifi, WifiOff, Zap, Shield, RotateCcw, AlertTriangle, CheckCircle, XCircle, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { useActuators, type Actuator } from '@/hooks/useApiData';
import { api } from '@/api/api';

type Timeout = ReturnType<typeof setTimeout>;

interface ActuatorState {
  id: string;
  isOnline: boolean;
  lastStatus: boolean | null;
  lastSeen: string | null;
  testState: 'idle' | 'testing' | 'success' | 'repair' | 'fail';
  lastTestTime: number | null;
}

export default function Actuators() {
  const { t } = useTranslation('actuators');
  const { siteId } = useParams<{ siteId: string }>();
  const { actuators, loading, error, refetch, createActuator, updateActuator, commandActuator, deleteActuator } = useActuators(siteId || '');
  
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editingActuator, setEditingActuator] = useState<Actuator | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    type: 'tuya',
    config: {} as Record<string, any>,
    is_enabled: true,
  });
  const [submitting, setSubmitting] = useState(false);
  const [actuatorStates, setActuatorStates] = useState<Record<string, ActuatorState>>({});
  const [pollingActive, setPollingActive] = useState(true);
  const pollIntervalRef = useRef<Timeout | null>(null);
  const repairTimeoutRef = useRef<Record<string, Timeout>>({});

  // Initialize actuator states
  useEffect(() => {
    setActuatorStates(prev => {
      const next = { ...prev };
      actuators.forEach(actuator => {
        if (!next[actuator.id]) {
          next[actuator.id] = {
            id: actuator.id,
            isOnline: actuator.is_online,
            lastStatus: actuator.last_status,
            lastSeen: actuator.last_seen,
            testState: 'idle',
            lastTestTime: null,
          };
        } else {
          // Update from API data
          next[actuator.id] = {
            ...next[actuator.id],
            isOnline: actuator.is_online,
            lastStatus: actuator.last_status,
            lastSeen: actuator.last_seen,
          };
        }
      });
      return next;
    });
  }, [actuators]);

  // Polling every 60 seconds
  useEffect(() => {
    if (!pollingActive) return;
    
    const poll = async () => {
      try {
        const data = await api.getActuators(siteId || '');
        // Update states from API
        setActuatorStates(prev => {
          const next = { ...prev };
          data.forEach((actuator: Actuator) => {
            const wasOnline = next[actuator.id]?.isOnline ?? false;
            const isOnline = actuator.is_online;
            
            next[actuator.id] = {
              ...next[actuator.id],
              id: actuator.id,
              isOnline,
              lastStatus: actuator.last_status,
              lastSeen: actuator.last_seen,
              // If just came online, reset test state
              testState: !wasOnline && isOnline ? 'idle' : next[actuator.id]?.testState || 'idle',
            };
          });
          return next;
        });
      } catch (err) {
        console.error('Polling error:', err);
      }
    };

    poll(); // Initial poll
    pollIntervalRef.current = setInterval(poll, 60000); // Every 60 seconds
    
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [siteId, pollingActive]);

  // Handle OFFLINE actuator repair every 2 minutes
  useEffect(() => {
    const checkOfflineRepair = async () => {
      try {
        const data = await api.getActuators(siteId || '');
        const offlineActuators = data.filter((a: Actuator) => !a.is_online && a.is_enabled);
        
        for (const actuator of offlineActuators) {
          const state = actuatorStates[actuator.id];
          // Only attempt repair if not already in repair state
          if (state?.testState !== 'repair') {
            await attemptRepair(actuator);
          }
        }
      } catch (err) {
        console.error('Offline repair check error:', err);
      }
    };

    const interval = setInterval(checkOfflineRepair, 120000); // Every 2 minutes
    return () => clearInterval(interval);
  }, [siteId, actuatorStates]);

  const attemptRepair = async (actuator: Actuator) => {
      const config = actuator.config || {};
      const mac = config.mac;
      if (!mac) return;

      setActuatorStates(prev => ({
        ...prev,
        [actuator.id]: { ...prev[actuator.id]!, testState: 'repair' }
      }));

      try {
        // Search for new IP by MAC
        const newIp = await api.findDeviceByMac(siteId || '', mac);
        if (newIp) {
          // Update actuator config with new IP
          await api.updateActuator(siteId || '', actuator.id, {
            config: { ...config, ip: newIp }
          });

          // Test connection
          const testResult = await api.testActuator(siteId || '', actuator.id);
          // API returns { status: 'ok'|'offline', details: { online: boolean, ... } }
          const isOnline = testResult.details?.online === true;
          if (isOnline) {
            // Success - will be picked up by next poll
            setActuatorStates(prev => ({
              ...prev,
              [actuator.id]: { ...prev[actuator.id]!, testState: 'success', lastTestTime: Date.now() }
            }));

            // Reset to idle after 5 seconds
            setTimeout(() => {
              setActuatorStates(prev => ({
                ...prev,
                [actuator.id]: { ...prev[actuator.id]!, testState: 'idle' }
              }));
            }, 5000);
          } else {
            // Repair test failed
            setActuatorStates(prev => ({
              ...prev,
              [actuator.id]: { ...prev[actuator.id]!, testState: 'fail', lastTestTime: Date.now() }
            }));

            // Send Telegram alert
            await api.sendTelegramAlert(siteId || '', {
              type: 'actuator_offline',
              actuatorId: actuator.id,
              actuatorName: actuator.name,
              message: `Actuator ${actuator.name} is OFFLINE after repair attempt`
            });

            setTimeout(() => {
              setActuatorStates(prev => ({
                ...prev,
                [actuator.id]: { ...prev[actuator.id]!, testState: 'idle' }
              }));
            }, 5000);
          }
        } else {
          // MAC not found
          setActuatorStates(prev => ({
            ...prev,
            [actuator.id]: { ...prev[actuator.id]!, testState: 'fail', lastTestTime: Date.now() }
          }));
          setTimeout(() => {
            setActuatorStates(prev => ({
              ...prev,
              [actuator.id]: { ...prev[actuator.id]!, testState: 'idle' }
            }));
          }, 5000);
        }
      } catch (err) {
      console.error('Repair error:', err);
      setActuatorStates(prev => ({
        ...prev,
        [actuator.id]: { ...prev[actuator.id]!, testState: 'fail', lastTestTime: Date.now() }
      }));
      setTimeout(() => {
        setActuatorStates(prev => ({
          ...prev,
          [actuator.id]: { ...prev[actuator.id]!, testState: 'idle' }
        }));
      }, 5000);
    }
  };

  const handleTest = async (actuator: Actuator) => {
    const state = actuatorStates[actuator.id];
    if (state?.testState === 'testing' || state?.testState === 'repair') return;

    setActuatorStates(prev => ({
      ...prev,
      [actuator.id]: { ...prev[actuator.id]!, testState: 'testing' }
    }));

    try {
      const result = await api.testActuator(siteId || '', actuator.id);
      
      // API returns { status: 'ok'|'offline', details: { online: boolean, ... } }
      const isOnline = result.details?.online === true;
      
      if (isOnline) {
        setActuatorStates(prev => ({
          ...prev,
          [actuator.id]: { ...prev[actuator.id]!, testState: 'success', lastTestTime: Date.now() }
        }));
        setTimeout(() => {
          setActuatorStates(prev => ({
            ...prev,
            [actuator.id]: { ...prev[actuator.id]!, testState: 'idle' }
          }));
        }, 5000);
      } else {
        // Test failed - start repair
        setActuatorStates(prev => ({
          ...prev,
          [actuator.id]: { ...prev[actuator.id]!, testState: 'repair' }
        }));
        
        // 2 minute repair timeout
        const timeout = setTimeout(() => {
          handleRepairTimeout(actuator);
        }, 120000);
        repairTimeoutRef.current[actuator.id] = timeout;
        
        await attemptRepair(actuator);
      }
    } catch (err) {
      setActuatorStates(prev => ({
        ...prev,
        [actuator.id]: { ...prev[actuator.id]!, testState: 'fail', lastTestTime: Date.now() }
      }));
      setTimeout(() => {
        setActuatorStates(prev => ({
          ...prev,
          [actuator.id]: { ...prev[actuator.id]!, testState: 'idle' }
        }));
      }, 5000);
    }
  };

  const handleRepairTimeout = async (actuator: Actuator) => {
    setActuatorStates(prev => ({
      ...prev,
      [actuator.id]: { ...prev[actuator.id]!, testState: 'fail', lastTestTime: Date.now() }
    }));
    
    // Send Telegram alert
    try {
      await api.sendTelegramAlert(siteId || '', {
        type: 'actuator_offline',
        actuatorId: actuator.id,
        actuatorName: actuator.name,
        message: `Actuator ${actuator.name} is OFFLINE after 2min repair attempt`
      });
    } catch (err) {
      console.error('Telegram alert failed:', err);
    }
    
    setTimeout(() => {
      setActuatorStates(prev => ({
        ...prev,
        [actuator.id]: { ...prev[actuator.id]!, testState: 'idle' }
      }));
    }, 5000);
  };

  const handleToggle = async (actuator: Actuator) => {
    const currentStatus = actuatorStates[actuator.id]?.lastStatus ?? actuator.last_status;
    const newAction = currentStatus ? 'off' : 'on';
    
    setActuatorStates(prev => ({
      ...prev,
      [actuator.id]: { ...prev[actuator.id]!, lastStatus: !currentStatus }
    }));

    try {
      await commandActuator(actuator.id, { action: newAction });
      
      // Wait 3 seconds then verify
      setTimeout(async () => {
        try {
          const data = await api.getActuator(siteId || '', actuator.id);
          setActuatorStates(prev => ({
            ...prev,
            [actuator.id]: { 
              ...prev[actuator.id]!, 
              lastStatus: data.last_status,
              isOnline: data.is_online,
              lastSeen: data.last_seen
            }
          }));
        } catch (err) {
          console.error('Status verification failed:', err);
        }
      }, 3000);
    } catch (err: unknown) {
      // Revert on error
      setActuatorStates(prev => ({
        ...prev,
        [actuator.id]: { ...prev[actuator.id]!, lastStatus: currentStatus }
      }));
      alert(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'tuya': return <Shield className="w-3 h-3" />;
      case 'sonoff': return <Zap className="w-3 h-3" />;
      case 'shelly': return <Zap className="w-3 h-3" />;
      default: return <Power className="w-3 h-3" />;
    }
  };

  const getTestButtonProps = (actuator: Actuator) => {
    const state = actuatorStates[actuator.id]?.testState || 'idle';
    
    switch (state) {
      case 'testing':
        return {
          variant: 'outline' as const,
          disabled: true,
          children: <><Loader2 className="w-4 h-4 mr-1 animate-spin" />{t('testing')}</>,
          className: "flex-1"
        };
      case 'success':
        return {
          variant: 'default' as const,
          disabled: true,
          children: <><CheckCircle className="w-4 h-4 mr-1" />{t('success')}</>,
          className: "flex-1 bg-green-500 text-white hover:bg-green-500"
        };
      case 'repair':
        return {
          variant: 'default' as const,
          disabled: true,
          children: <><RotateCcw className="w-4 h-4 mr-1 animate-spin" />{t('repair')}</>,
          className: "flex-1 bg-yellow-500 text-white hover:bg-yellow-500"
        };
      case 'fail':
        return {
          variant: 'destructive' as const,
          disabled: true,
          children: <><XCircle className="w-4 h-4 mr-1" />{t('fail')}</>,
          className: "flex-1 bg-red-500 text-white hover:bg-red-500"
        };
      default:
        return {
          variant: 'outline' as const,
          disabled: !actuator.is_enabled,
          onClick: () => handleTest(actuator),
          children: <><Search className="w-4 h-4 mr-1" />{t('test')}</>,
          className: "flex-1"
        };
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const data = {
        name: formData.name,
        description: formData.description || undefined,
        type: formData.type as any,
        config: formData.config,
        is_enabled: formData.is_enabled,
      };

      if (editingActuator) {
        await updateActuator(editingActuator.id, data);
      } else {
        await createActuator(data);
      }
      resetForm();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      type: 'tuya',
      config: {},
      is_enabled: true,
    });
    setEditingActuator(null);
    setIsCreateOpen(false);
    setIsEditOpen(false);
  };

  const openCreate = () => {
    resetForm();
    setIsCreateOpen(true);
  };

  const openEdit = (actuator: Actuator) => {
    setFormData({
      name: actuator.name,
      description: actuator.description || '',
      type: actuator.type,
      config: actuator.config || {},
      is_enabled: actuator.is_enabled,
    });
    setEditingActuator(actuator);
    setIsEditOpen(true);
  };

  const renderConfigFields = (type: string, config: Record<string, any>, onChange: (key: string, value: any) => void) => {
    switch (type) {
      case 'tuya':
        return (
          <div className="grid gap-4 grid-cols-2">
            {['ip', 'device_id', 'local_key', 'mac'].map(key => (
              <div key={key} className="space-y-2">
                <Label htmlFor={`config_${key}`}>{key.replace('_', ' ')}</Label>
                <Input
                  id={`config_${key}`}
                  value={config[key] || ''}
                  onChange={(e) => onChange(key, e.target.value)}
                  placeholder={key === 'port' ? '6668' : ''}
                />
              </div>
            ))}
            <div className="space-y-2">
              <Label htmlFor="config_port">Port</Label>
              <Input
                id="config_port"
                type="number"
                value={config.port || 6668}
                onChange={(e) => onChange('port', parseInt(e.target.value))}
                defaultValue={6668}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="config_version">Version</Label>
              <Input
                id="config_version"
                type="number"
                step="0.1"
                value={config.version || 3.4}
                onChange={(e) => onChange('version', parseFloat(e.target.value))}
                defaultValue={3.4}
              />
            </div>
          </div>
        );
      default:
        return (
          <Textarea
            value={JSON.stringify(config, null, 2)}
            onChange={(e) => {
              try {
                onChange('raw', JSON.parse(e.target.value));
              } catch {
              }
            }}
            rows={6}
            className="font-mono text-sm"
            placeholder="{}"
          />
        );
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
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setPollingActive(!pollingActive)}>
            {pollingActive ? <RotateCcw className="w-4 h-4 mr-1" /> : <RotateCcw className="w-4 h-4 mr-1" />}
            {pollingActive ? t('pausePolling') : t('resumePolling')}
          </Button>
          <Button onClick={openCreate}>
            <Plus className="w-4 h-4 mr-2" />
            {t('addActuator')}
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {actuators.map((actuator) => {
          const state = actuatorStates[actuator.id];
          const isOnline = state?.isOnline ?? actuator.is_online;
          const lastStatus = state?.lastStatus ?? actuator.last_status;
          const testState = state?.testState || 'idle';
          
          const isOn = lastStatus === true;
          
          return (
            <Card key={actuator.id} className="h-full">
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span>{actuator.name}</span>
                  <Badge variant="secondary" className="flex items-center gap-1">
                    {getTypeIcon(actuator.type)}
                    {actuator.type.toUpperCase()}
                  </Badge>
                </CardTitle>
                <CardDescription>{actuator.description || t('noDescription')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-muted-foreground">{t('status')}</span>
                  <Badge variant={isOnline ? 'success' : 'destructive'} className="flex items-center gap-1">
                    {isOnline ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
                    {isOnline ? t('online') : t('offline')}
                  </Badge>
                </div>
                
                {/* Main Toggle Button */}
                <Button
                  variant={isOn ? 'default' : 'destructive'}
                  className={`w-full py-3 text-lg font-medium ${isOn ? 'bg-green-500 hover:bg-green-600 text-white' : 'bg-red-500 hover:bg-red-600 text-white'}`}
                  disabled={!actuator.is_enabled || testState === 'testing' || testState === 'repair'}
                  onClick={() => handleToggle(actuator)}
                >
                  <Power className={`w-5 h-5 mr-2 ${isOn ? '' : ''}`} />
                  {isOn ? t('on') : t('off')}
                </Button>
                
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{t('lastSeen')}</span>
                  <span className="text-muted-foreground">
                    {state?.lastSeen ? new Date(state.lastSeen).toLocaleString() : (actuator.last_seen ? new Date(actuator.last_seen).toLocaleString() : '—')}
                  </span>
                </div>
                
                <div className="flex gap-2 pt-2 border-t">
                  <Button
                    {...getTestButtonProps(actuator)}
                    size="sm"
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    onClick={() => openEdit(actuator)}
                    disabled={testState === 'testing' || testState === 'repair'}
                  >
                    <Zap className="w-4 h-4 mr-1" />
                    {t('edit')}
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    className="flex-1"
                    onClick={() => {
                      if (confirm(`${t('confirmDelete') || 'Delete this actuator?'}`)) {
                        deleteActuator(actuator.id);
                      }
                    }}
                    disabled={testState === 'testing' || testState === 'repair'}
                  >
                    <AlertTriangle className="w-4 h-4 mr-1" />
                    {t('delete')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
        {actuators.length === 0 && (
          <Card className="col-span-full">
            <CardContent className="py-12 text-center text-muted-foreground">
              <Power className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>{t('noActuators') || 'No actuators configured. Add your first actuator.'}</p>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Create/Edit Dialog */}
      <Dialog open={isCreateOpen || isEditOpen} onOpenChange={(open) => { if (!open) resetForm(); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingActuator ? t('editActuator') : t('addActuator')}</DialogTitle>
            <DialogDescription>{editingActuator ? t('editActuatorDescription') : t('addActuatorDescription')}</DialogDescription>
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
                    placeholder={t('actuatorNamePlaceholder')}
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
                  <Select value={formData.type} onValueChange={(value) => setFormData(prev => ({ ...prev, type: value, config: {} }))}>
                    <SelectTrigger id="type">
                      <SelectValue placeholder={t('selectType')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="tuya">Tuya Smart</SelectItem>
                      <SelectItem value="sonoff">Sonoff</SelectItem>
                      <SelectItem value="shelly">Shelly</SelectItem>
                      <SelectItem value="tasmota">Tasmota</SelectItem>
                      <SelectItem value="gpio">GPIO</SelectItem>
                      <SelectItem value="mqtt">MQTT</SelectItem>
                      <SelectItem value="http">HTTP</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t('config')}</Label>
                  {renderConfigFields(formData.type, formData.config, (key, value) => {
                    setFormData(prev => ({ ...prev, config: { ...prev.config, [key]: value } }));
                  })}
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