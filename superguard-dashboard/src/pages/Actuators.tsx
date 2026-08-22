import { useState, useEffect, useRef, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Plus, Power, Loader2, Wifi, Zap, Shield, RotateCcw, CheckCircle, XCircle, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { useActuators, type Actuator } from '@/hooks/useApiData';
import { api } from '@/api/api';
import { useActuatorWebSocket } from '@/hooks/useWebSocket';

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

  // Suppress unused variable warnings
  void loading; void error; void refetch;

  // WebSocket handler for real-time actuator status updates
  const handleActuatorUpdate = useCallback((msg: any) => {
    const payload = msg.payload;
    if (payload.actuatorId && payload.state !== undefined) {
      setActuatorStates(prev => ({
        ...prev,
        [payload.actuatorId]: {
          ...prev[payload.actuatorId]!,
          isOnline: true,
          lastStatus: payload.state,
          lastSeen: new Date().toISOString(),
          testState: 'idle'
        }
      }));
    }
  }, []);

  // WebSocket for real-time actuator status - replaces polling
  useActuatorWebSocket(siteId || '', handleActuatorUpdate);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
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
  const repairTimeoutRef = useRef<Record<string, Timeout>>({});

  // Initialize actuator states from API data
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

  // Polling disabled - WebSocket handles real-time updates
  // Kept for fallback if WebSocket fails
  /*
  useEffect(() => {
    if (!pollingActive) return;
    // ...
  }, [siteId, pollingActive]);
  */

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

  const handleTypeChange = (type: string) => {
    setFormData(prev => ({ ...prev, type, config: {} }));
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
    setIsCreateOpen(true);
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
      case 'sonoff':
        return (
          <div className="grid gap-4 grid-cols-2">
            {['ip', 'device_id', 'sonoff_apikey'].map(key => (
              <div key={key} className="space-y-2">
                <Label htmlFor={`config_${key}`}>{key.replace('_', ' ')}</Label>
                <Input
                  id={`config_${key}`}
                  value={config[key] || ''}
                  onChange={(e) => onChange(key, e.target.value)}
                />
              </div>
            ))}
            <div className="space-y-2">
              <Label htmlFor="config_port">Port</Label>
              <Input
                id="config_port"
                type="number"
                value={config.port || 8081}
                onChange={(e) => onChange('port', parseInt(e.target.value))}
                defaultValue={8081}
              />
            </div>
          </div>
        );
      case 'shelly':
        return (
          <div className="grid gap-4 grid-cols-2">
            {['ip', 'shelly_auth_key'].map(key => (
              <div key={key} className="space-y-2">
                <Label htmlFor={`config_${key}`}>{key.replace('_', ' ')}</Label>
                <Input
                  id={`config_${key}`}
                  value={config[key] || ''}
                  onChange={(e) => onChange(key, e.target.value)}
                />
              </div>
            ))}
          </div>
        );
      case 'tasmota':
        return (
          <div className="grid gap-4 grid-cols-2">
            {['ip', 'tasmota_username', 'tasmota_password'].map(key => (
              <div key={key} className="space-y-2">
                <Label htmlFor={`config_${key}`}>{key.replace('_', ' ')}</Label>
                <Input
                  id={`config_${key}`}
                  type={key.includes('password') ? 'password' : 'text'}
                  value={config[key] || ''}
                  onChange={(e) => onChange(key, e.target.value)}
                />
              </div>
            ))}
          </div>
        );
      case 'mqtt':
        return (
          <div className="grid gap-4 grid-cols-2">
            {['mqtt_broker', 'mqtt_topic', 'mqtt_username', 'mqtt_password'].map(key => (
              <div key={key} className="space-y-2">
                <Label htmlFor={`config_${key}`}>{key.replace('_', ' ')}</Label>
                <Input
                  id={`config_${key}`}
                  type={key.includes('password') ? 'password' : 'text'}
                  value={config[key] || ''}
                  onChange={(e) => onChange(key, e.target.value)}
                />
              </div>
            ))}
          </div>
        );
      case 'http':
        return (
          <div className="grid gap-4 grid-cols-2">
            {['http_on_url', 'http_off_url', 'http_status_url'].map(key => (
              <div key={key} className="space-y-2">
                <Label htmlFor={`config_${key}`}>{key.replace('_', ' ')}</Label>
                <Input
                  id={`config_${key}`}
                  value={config[key] || ''}
                  onChange={(e) => onChange(key, e.target.value)}
                />
              </div>
            ))}
          </div>
        );
      case 'gpio':
        return (
          <div className="grid gap-4 grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="config_gpio_pin">GPIO Pin</Label>
              <Input
                id="config_gpio_pin"
                type="number"
                value={config.gpio_pin || -1}
                onChange={(e) => onChange('gpio_pin', parseInt(e.target.value))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="config_gpio_active_low">Active Low</Label>
              <Input
                id="config_gpio_active_low"
                type="checkbox"
                checked={config.gpio_active_low || false}
                onChange={(e) => onChange('gpio_active_low', e.target.checked)}
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
            placeholder="JSON config"
            className="min-h-[120px] font-mono text-sm"
          />
        );
    }
  };

  const handleConfigChange = (key: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      config: { ...prev.config, [key]: value }
    }));
  };

  const handleDelete = async (actuatorId: string) => {
    if (!confirm(t('confirm_delete'))) return;
    try {
      await deleteActuator(actuatorId);
      setActuatorStates(prev => {
        const next = { ...prev };
        delete next[actuatorId];
        return next;
      });
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('title')}</h1>
          <p className="text-muted-foreground">{t('description')}</p>
        </div>
        <Button onClick={openCreate} className="gap-2">
          <Plus className="w-4 h-4" />
          {t('add_actuator')}
        </Button>
      </div>

      {/* Actuators Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {actuators.map(actuator => {
          const state = actuatorStates[actuator.id] || {
            id: actuator.id,
            isOnline: actuator.is_online,
            lastStatus: actuator.last_status,
            lastSeen: actuator.last_seen,
            testState: 'idle',
            lastTestTime: null,
          };

          const isOnline = state.isOnline;

          return (
            <Card key={actuator.id} className="relative overflow-hidden">
              {/* Online status indicator */}
              <div className={`absolute top-2 right-2 ${isOnline ? 'text-green-500' : 'text-red-500'}`}>
                <Wifi className={isOnline ? 'w-5 h-5' : 'w-5 h-5 opacity-50'} />
              </div>

              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">{actuator.name}</CardTitle>
                  <Badge variant={actuator.is_enabled ? 'default' : 'secondary'}>
                    {getTypeIcon(actuator.type)}
                  </Badge>
                </div>
                <CardDescription>{actuator.description || t('no_description')}</CardDescription>
              </CardHeader>

              <CardContent className="space-y-4">
                {/* Status Row */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {isOnline ? (
                      <span className="flex items-center gap-1 text-green-600">
                        <CheckCircle className="w-4 h-4" /> {t('online')}
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-red-600">
                        <XCircle className="w-4 h-4" /> {t('offline')}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    {state.lastStatus !== null && (
                      <>
                        {t('status')}: <span className={state.lastStatus ? 'text-green-600' : 'text-red-600'}>
                          {state.lastStatus ? t('on') : t('off')}
                        </span>
                      </>
                    )}
                    {state.lastSeen && (
                      <>
                        {t('last_seen')}: <time>{new Date(state.lastSeen).toLocaleString()}</time>
                      </>
                    )}
                  </div>
                </div>

                {/* Test/Repair State */}
                <div className="flex items-center gap-2">
                  {state.testState !== 'idle' && (
                    <Badge variant={
                      state.testState === 'testing' ? 'outline' :
                      state.testState === 'success' ? 'default' :
                      state.testState === 'repair' ? 'default' :
                      state.testState === 'fail' ? 'destructive' :
                      'outline'
                    } className="flex-1">
                      {state.testState === 'testing' && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
                      {state.testState === 'success' && <CheckCircle className="w-3 h-3 mr-1" />}
                      {state.testState === 'repair' && <RotateCcw className="w-3 h-3 mr-1 animate-spin" />}
                      {state.testState === 'fail' && <XCircle className="w-3 h-3 mr-1" />}
                      {t(state.testState)}
                    </Badge>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    {...getTestButtonProps(actuator)}
                  />
                  <Button
                    variant="outline"
                    onClick={() => handleToggle(actuator)}
                    disabled={!actuator.is_enabled}
                    className={state.lastStatus ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}
                  >
                    <Power className="w-4 h-4 mr-1" />
                    {state.lastStatus ? t('turn_off') : t('turn_on')}
                  </Button>
                </div>

                {/* Edit/Delete */}
                <div className="flex justify-end gap-2 pt-2 border-t">
                  <Button variant="ghost" size="sm" onClick={() => openEdit(actuator)}>
                    <Search className="w-4 h-4 mr-1" /> {t('edit')}
                  </Button>
                  <Button variant="ghost" size="sm" className="text-destructive" onClick={() => handleDelete(actuator.id)}>
                    <XCircle className="w-4 h-4 mr-1" /> {t('delete')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Empty State */}
      {actuators.length === 0 && (
        <Card className="text-center py-12">
          <CardContent>
            <Shield className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium">{t('no_actuators')}</h3>
            <p className="text-muted-foreground mb-4">{t('no_actuators_desc')}</p>
            <Button onClick={openCreate}>
              <Plus className="w-4 h-4 mr-2" />
              {t('add_first_actuator')}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingActuator ? t('edit_actuator') : t('create_actuator')}</DialogTitle>
            <DialogDescription>{t('actuator_form_desc')}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-6 p-4">
            <div className="grid gap-4">
              <div className="space-y-2">
                <Label htmlFor="name">{t('name')}</Label>
                <Input id="name" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">{t('description')}</Label>
                <Textarea id="description" value={formData.description} onChange={e => setFormData({...formData, description: e.target.value})} rows={3} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="type">{t('type')}</Label>
                <Select value={formData.type} onValueChange={handleTypeChange}>
                  <SelectTrigger><SelectValue placeholder={t('select_type')} /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="tuya">Tuya / SmartLife</SelectItem>
                    <SelectItem value="sonoff">Sonoff (eWeLink)</SelectItem>
                    <SelectItem value="shelly">Shelly</SelectItem>
                    <SelectItem value="tasmota">Tasmota</SelectItem>
                    <SelectItem value="gpio">GPIO (Raspberry Pi)</SelectItem>
                    <SelectItem value="mqtt">MQTT</SelectItem>
                    <SelectItem value="http">HTTP REST</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="is_enabled">{t('enabled')}</Label>
                <Input
                  id="is_enabled"
                  type="checkbox"
                  checked={formData.is_enabled}
                  onChange={e => setFormData({...formData, is_enabled: e.target.checked})}
                />
              </div>
            </div>

            {/* Config Fields */}
            <div className="space-y-2 border-t pt-4">
              <h4 className="font-medium">{t('configuration')}</h4>
              {renderConfigFields(formData.type, formData.config, handleConfigChange)}
            </div>
          </form>
          <DialogFooter className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={resetForm}>{t('cancel')}</Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : ''} {t('save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}