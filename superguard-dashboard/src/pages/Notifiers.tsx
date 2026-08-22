import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { useNotifiers } from '@/hooks/useApiData';
import { Plus, Trash2, Edit, Loader2, Bot, CheckCircle, XCircle, Bell, TestTube } from 'lucide-react';

interface Notifier {
  id: string;
  site_id: string;
  name: string;
  type: 'telegram' | 'email' | 'sms' | 'pushover' | 'webhook' | 'mqtt' | 'signal';
  config: Record<string, any>;
  is_enabled: boolean;
  notify_on_trigger: boolean;
  notify_on_ack: boolean;
  notify_on_resolve: boolean;
  created_at: string;
}

export default function Notifiers() {
  const { t } = useTranslation('notifiers');
  const { siteId } = useParams<{ siteId: string }>();
  const navigate = useNavigate();
  
  const { notifiers, loading, refetch, createNotifier, deleteNotifier, testNotifier } = useNotifiers(siteId || '');
  
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [editingNotifier, setEditingNotifier] = useState<Notifier | null>(null);
  const [selectedType, setSelectedType] = useState<'telegram' | 'email' | 'sms' | 'pushover' | 'webhook' | 'mqtt' | 'signal'>('telegram');
  const [notifierName, setNotifierName] = useState('');
  const [isEnabled, setIsEnabled] = useState(true);
  const [notifyOnTrigger, setNotifyOnTrigger] = useState(true);
  const [notifyOnAck, setNotifyOnAck] = useState(false);
  const [notifyOnResolve, setNotifyOnResolve] = useState(false);
  
  // Type-specific config
  const [telegramConfig, setTelegramConfig] = useState({ bot_token: '', chat_id: '', parse_mode: 'HTML' });
  const [emailConfig, setEmailConfig] = useState({ smtp_host: '', smtp_port: 587, smtp_user: '', smtp_pass: '', from_email: '', to_emails: '' });
  const [webhookConfig, setWebhookConfig] = useState({ url: '', method: 'POST', headers: '', timeout: 10 });
  const [mqttConfig, setMqttConfig] = useState({ broker: '', topic: '', username: '', password: '', client_id: '' });
  const [pushoverConfig, setPushoverConfig] = useState({ user_key: '', api_token: '', device: '' });
  const [signalConfig, setSignalConfig] = useState({ phone_number: '', api_url: '' });
  const [smsConfig, setSmsConfig] = useState({ provider: 'twilio', account_sid: '', auth_token: '', from_number: '', to_number: '' });
  
  const [dialogLoading, setDialogLoading] = useState(false);
  const [testLoading, setTestLoading] = useState<string | null>(null);

  const resetForm = () => {
    setSelectedType('telegram');
    setNotifierName('');
    setIsEnabled(true);
    setNotifyOnTrigger(true);
    setNotifyOnAck(false);
    setNotifyOnResolve(false);
    setTelegramConfig({ bot_token: '', chat_id: '', parse_mode: 'HTML' });
    setEmailConfig({ smtp_host: '', smtp_port: 587, smtp_user: '', smtp_pass: '', from_email: '', to_emails: '' });
    setWebhookConfig({ url: '', method: 'POST', headers: '', timeout: 10 });
    setMqttConfig({ broker: '', topic: '', username: '', password: '', client_id: '' });
    setPushoverConfig({ user_key: '', api_token: '', device: '' });
    setSignalConfig({ phone_number: '', api_url: '' });
    setSmsConfig({ provider: 'twilio', account_sid: '', auth_token: '', from_number: '', to_number: '' });
    setEditingNotifier(null);
  };

  const handleTypeChange = (type: 'telegram' | 'email' | 'sms' | 'pushover' | 'webhook' | 'mqtt' | 'signal') => {
    setSelectedType(type);
  };

  const buildConfig = () => {
    switch (selectedType) {
      case 'telegram':
        return telegramConfig;
      case 'email':
        return { ...emailConfig, to_emails: emailConfig.to_emails.split(',').map(e => e.trim()) };
      case 'webhook':
        return {
          ...webhookConfig,
          headers: webhookConfig.headers ? JSON.parse(webhookConfig.headers) : {}
        };
      case 'mqtt':
        return mqttConfig;
      case 'pushover':
        return pushoverConfig;
      case 'signal':
        return signalConfig;
      case 'sms':
        return smsConfig;
      default:
        return {};
    }
  };

  const handleCreateNotifier = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!siteId || !notifierName) return;
    
    setDialogLoading(true);
    try {
      await createNotifier({
        name: notifierName,
        type: selectedType,
        config: buildConfig(),
        notify_on_trigger: notifyOnTrigger,
        notify_on_ack: notifyOnAck,
        notify_on_resolve: notifyOnResolve,
      });
      
      setShowCreateDialog(false);
      resetForm();
      refetch();
    } catch (err: any) {
      console.error('Create notifier error:', err);
    } finally {
      setDialogLoading(false);
    }
  };

  const handleEditNotifier = (notifier: Notifier) => {
    setEditingNotifier(notifier);
    setNotifierName(notifier.name);
    setSelectedType(notifier.type);
    setIsEnabled(notifier.is_enabled);
    setNotifyOnTrigger(notifier.notify_on_trigger);
    setNotifyOnAck(notifier.notify_on_ack);
    setNotifyOnResolve(notifier.notify_on_resolve);
    
    // Populate type-specific config
    const config = notifier.config as Record<string, any>;
    switch (notifier.type) {
      case 'telegram':
        setTelegramConfig({ bot_token: config.bot_token || '', chat_id: config.chat_id || '', parse_mode: config.parse_mode || 'HTML' });
        break;
      case 'email':
        setEmailConfig({ smtp_host: config.smtp_host || '', smtp_port: config.smtp_port || 587, smtp_user: config.smtp_user || '', smtp_pass: config.smtp_pass || '', from_email: config.from_email || '', to_emails: config.to_emails?.join(', ') || '' });
        break;
      case 'webhook':
        setWebhookConfig({ url: config.url || '', method: config.method || 'POST', headers: JSON.stringify(config.headers || {}, null, 2), timeout: config.timeout || 10 });
        break;
      case 'mqtt':
        setMqttConfig({ broker: config.broker || '', topic: config.topic || '', username: config.username || '', password: config.password || '', client_id: config.client_id || '' });
        break;
      case 'pushover':
        setPushoverConfig({ user_key: config.user_key || '', api_token: config.api_token || '', device: config.device || '' });
        break;
      case 'signal':
        setSignalConfig({ phone_number: config.phone_number || '', api_url: config.api_url || '' });
        break;
      case 'sms':
        setSmsConfig({ provider: config.provider || 'twilio', account_sid: config.account_sid || '', auth_token: config.auth_token || '', from_number: config.from_number || '', to_number: config.to_number || '' });
        break;
    }
    
    setShowCreateDialog(true);
  };

  const handleDeleteNotifier = async (notifierId: string) => {
    if (!confirm(t('confirmDelete'))) return;
    
    try {
      await deleteNotifier(notifierId);
      refetch();
    } catch (err: any) {
      console.error('Delete notifier error:', err);
    }
  };

  const handleTestNotifier = async (notifierId: string) => {
    setTestLoading(notifierId);
    try {
      await testNotifier(notifierId);
      alert(t('testSuccess'));
    } catch (err: any) {
      alert(t('testFailed') + ': ' + err.message);
    } finally {
      setTestLoading(null);
    }
  };

  const handleBack = () => {
    navigate(`/sites/${siteId}`);
  };

  if (loading) {
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
                {t('addNotifier')}
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{editingNotifier ? t('editNotifier') : t('addNotifier')}</DialogTitle>
                <DialogDescription>{editingNotifier ? t('editNotifierDescription') : t('addNotifierDescription')}</DialogDescription>
              </DialogHeader>
              <form onSubmit={handleCreateNotifier}>
                <Tabs defaultValue="general" className="space-y-4">
                  <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="general">{t('general')}</TabsTrigger>
                    <TabsTrigger value="config">{t('configuration')}</TabsTrigger>
                    <TabsTrigger value="triggers">{t('triggerSettings')}</TabsTrigger>
                  </TabsList>
                  
                  <TabsContent value="general">
                    <div className="grid gap-4 py-4">
                      <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="name" className="text-right">{t('name')}</Label>
                        <Input id="name" value={notifierName} onChange={e => setNotifierName(e.target.value)} placeholder={t('notifierNamePlaceholder')} required />
                      </div>
                      <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="type" className="text-right">{t('type')}</Label>
                        <Select value={selectedType} onValueChange={handleTypeChange}>
                          <SelectTrigger id="type">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="telegram">{t('typeTelegram')}</SelectItem>
                            <SelectItem value="email">{t('typeEmail')}</SelectItem>
                            <SelectItem value="webhook">{t('typeWebhook')}</SelectItem>
                            <SelectItem value="mqtt">{t('typeMqtt')}</SelectItem>
                            <SelectItem value="pushover">{t('typePushover')}</SelectItem>
                            <SelectItem value="signal">{t('typeSignal')}</SelectItem>
                            <SelectItem value="sms">{t('typeSms')}</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="enabled" className="text-right">{t('enabled')}</Label>
                        <Switch id="enabled" checked={isEnabled} onCheckedChange={setIsEnabled} />
                      </div>
                    </div>
                  </TabsContent>
                  
                  <TabsContent value="config">
                    <div className="grid gap-4 py-4">
                      {selectedType === 'telegram' && (
                        <>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="bot_token" className="text-right">{t('botToken')}</Label>
                            <Input id="bot_token" type="password" value={telegramConfig.bot_token} onChange={e => setTelegramConfig({...telegramConfig, bot_token: e.target.value})} placeholder="123456:ABC-DEF..." required />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="chat_id" className="text-right">{t('chatId')}</Label>
                            <Input id="chat_id" value={telegramConfig.chat_id} onChange={e => setTelegramConfig({...telegramConfig, chat_id: e.target.value})} placeholder="-1001234567890" required />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="parse_mode" className="text-right">{t('parseMode')}</Label>
                            <Select value={telegramConfig.parse_mode} onValueChange={v => setTelegramConfig({...telegramConfig, parse_mode: v})}>
                              <SelectTrigger id="parse_mode"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="HTML">HTML</SelectItem>
                                <SelectItem value="Markdown">Markdown</SelectItem>
                                <SelectItem value="MarkdownV2">MarkdownV2</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          <p className="text-sm text-muted-foreground col-span-4">{t('telegramHelp')}</p>
                        </>
                      )}
                      
                      {selectedType === 'email' && (
                        <>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="smtp_host" className="text-right">{t('smtpHost')}</Label>
                            <Input id="smtp_host" value={emailConfig.smtp_host} onChange={e => setEmailConfig({...emailConfig, smtp_host: e.target.value})} placeholder="smtp.gmail.com" />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="smtp_port" className="text-right">{t('smtpPort')}</Label>
                            <Input id="smtp_port" type="number" value={emailConfig.smtp_port} onChange={e => setEmailConfig({...emailConfig, smtp_port: parseInt(e.target.value) || 587})} />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="smtp_user" className="text-right">{t('smtpUser')}</Label>
                            <Input id="smtp_user" value={emailConfig.smtp_user} onChange={e => setEmailConfig({...emailConfig, smtp_user: e.target.value})} />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="smtp_pass" className="text-right">{t('smtpPass')}</Label>
                            <Input id="smtp_pass" type="password" value={emailConfig.smtp_pass} onChange={e => setEmailConfig({...emailConfig, smtp_pass: e.target.value})} />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="from_email" className="text-right">{t('fromEmail')}</Label>
                            <Input id="from_email" value={emailConfig.from_email} onChange={e => setEmailConfig({...emailConfig, from_email: e.target.value})} />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="to_emails" className="text-right">{t('toEmails')}</Label>
                            <Input id="to_emails" value={emailConfig.to_emails} onChange={e => setEmailConfig({...emailConfig, to_emails: e.target.value})} placeholder="admin@example.com, user@example.com" />
                          </div>
                        </>
                      )}
                      
                      {selectedType === 'webhook' && (
                        <>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="webhook_url" className="text-right">{t('webhookUrl')}</Label>
                            <Input id="webhook_url" value={webhookConfig.url} onChange={e => setWebhookConfig({...webhookConfig, url: e.target.value})} placeholder="https://example.com/webhook" required />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="webhook_method" className="text-right">{t('method')}</Label>
                            <Select value={webhookConfig.method} onValueChange={v => setWebhookConfig({...webhookConfig, method: v})}>
                              <SelectTrigger id="webhook_method"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="POST">POST</SelectItem>
                                <SelectItem value="PUT">PUT</SelectItem>
                                <SelectItem value="PATCH">PATCH</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="webhook_headers" className="text-right">{t('headers')}</Label>
                            <Input id="webhook_headers" value={webhookConfig.headers} onChange={e => setWebhookConfig({...webhookConfig, headers: e.target.value})} placeholder='{"Authorization": "Bearer token"}' />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="webhook_timeout" className="text-right">{t('timeout')}</Label>
                            <Input id="webhook_timeout" type="number" value={webhookConfig.timeout} onChange={e => setWebhookConfig({...webhookConfig, timeout: parseInt(e.target.value) || 10})} className="w-32" />
                            <span className="text-sm text-muted-foreground">{t('seconds')}</span>
                          </div>
                        </>
                      )}
                      
                      {selectedType === 'mqtt' && (
                        <>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="mqtt_broker" className="text-right">{t('broker')}</Label>
                            <Input id="mqtt_broker" value={mqttConfig.broker} onChange={e => setMqttConfig({...mqttConfig, broker: e.target.value})} placeholder="mqtt://localhost:1883" required />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="mqtt_topic" className="text-right">{t('topic')}</Label>
                            <Input id="mqtt_topic" value={mqttConfig.topic} onChange={e => setMqttConfig({...mqttConfig, topic: e.target.value})} placeholder="superguard/alarms" required />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="mqtt_username" className="text-right">{t('username')}</Label>
                            <Input id="mqtt_username" value={mqttConfig.username} onChange={e => setMqttConfig({...mqttConfig, username: e.target.value})} />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="mqtt_password" className="text-right">{t('password')}</Label>
                            <Input id="mqtt_password" type="password" value={mqttConfig.password} onChange={e => setMqttConfig({...mqttConfig, password: e.target.value})} />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="mqtt_client_id" className="text-right">{t('clientId')}</Label>
                            <Input id="mqtt_client_id" value={mqttConfig.client_id} onChange={e => setMqttConfig({...mqttConfig, client_id: e.target.value})} placeholder="superguard-dashboard" />
                          </div>
                        </>
                      )}
                      
                      {selectedType === 'pushover' && (
                        <>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="pushover_user_key" className="text-right">{t('userKey')}</Label>
                            <Input id="pushover_user_key" value={pushoverConfig.user_key} onChange={e => setPushoverConfig({...pushoverConfig, user_key: e.target.value})} required />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="pushover_api_token" className="text-right">{t('apiToken')}</Label>
                            <Input id="pushover_api_token" value={pushoverConfig.api_token} onChange={e => setPushoverConfig({...pushoverConfig, api_token: e.target.value})} required />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="pushover_device" className="text-right">{t('device')}</Label>
                            <Input id="pushover_device" value={pushoverConfig.device} onChange={e => setPushoverConfig({...pushoverConfig, device: e.target.value})} placeholder={t('optional')} />
                          </div>
                        </>
                      )}
                      
                      {selectedType === 'signal' && (
                        <>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="signal_phone" className="text-right">{t('phoneNumber')}</Label>
                            <Input id="signal_phone" value={signalConfig.phone_number} onChange={e => setSignalConfig({...signalConfig, phone_number: e.target.value})} placeholder="+1234567890" required />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="signal_api_url" className="text-right">{t('apiUrl')}</Label>
                            <Input id="signal_api_url" value={signalConfig.api_url} onChange={e => setSignalConfig({...signalConfig, api_url: e.target.value})} placeholder="http://localhost:3001" />
                          </div>
                        </>
                      )}
                      
                      {selectedType === 'sms' && (
                        <>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="sms_provider" className="text-right">{t('provider')}</Label>
                            <Select value={smsConfig.provider} onValueChange={v => setSmsConfig({...smsConfig, provider: v})}>
                              <SelectTrigger id="sms_provider"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="twilio">Twilio</SelectItem>
                                <SelectItem value="plivo">Plivo</SelectItem>
                                <SelectItem value="nexmo">Nexmo/Vonage</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="sms_account_sid" className="text-right">{t('accountSid')}</Label>
                            <Input id="sms_account_sid" value={smsConfig.account_sid} onChange={e => setSmsConfig({...smsConfig, account_sid: e.target.value})} required />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="sms_auth_token" className="text-right">{t('authToken')}</Label>
                            <Input id="sms_auth_token" type="password" value={smsConfig.auth_token} onChange={e => setSmsConfig({...smsConfig, auth_token: e.target.value})} required />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="sms_from" className="text-right">{t('fromNumber')}</Label>
                            <Input id="sms_from" value={smsConfig.from_number} onChange={e => setSmsConfig({...smsConfig, from_number: e.target.value})} required />
                          </div>
                          <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="sms_to" className="text-right">{t('toNumber')}</Label>
                            <Input id="sms_to" value={smsConfig.to_number} onChange={e => setSmsConfig({...smsConfig, to_number: e.target.value})} required />
                          </div>
                        </>
                      )}
                    </div>
                  </TabsContent>
                  
                  <TabsContent value="triggers">
                    <div className="grid gap-4 py-4">
                      <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="notify_trigger" className="text-right">{t('notifyOnTrigger')}</Label>
                        <Switch id="notify_trigger" checked={notifyOnTrigger} onCheckedChange={setNotifyOnTrigger} />
                      </div>
                      <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="notify_ack" className="text-right">{t('notifyOnAck')}</Label>
                        <Switch id="notify_ack" checked={notifyOnAck} onCheckedChange={setNotifyOnAck} />
                      </div>
                      <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="notify_resolve" className="text-right">{t('notifyOnResolve')}</Label>
                        <Switch id="notify_resolve" checked={notifyOnResolve} onCheckedChange={setNotifyOnResolve} />
                      </div>
                    </div>
                  </TabsContent>
                </Tabs>
                
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

      {/* Notifiers Table */}
      <Card>
        <CardHeader>
          <CardTitle>{t('notifierList')}</CardTitle>
          <CardDescription>{t('notifierDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          {notifiers.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('name')}</TableHead>
                  <TableHead>{t('type')}</TableHead>
                  <TableHead>{t('triggers')}</TableHead>
                  <TableHead>{t('status')}</TableHead>
                  <TableHead className="text-right">{t('actions')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {notifiers.map(notifier => (
                  <TableRow key={notifier.id}>
                    <TableCell>
                      <div>
                        <p className="font-medium">{notifier.name}</p>
                        <p className="text-xs text-muted-foreground">{notifier.config.bot_token ? 'Bot: ' + notifier.config.bot_token.substring(0, 10) + '...' : notifier.config.url ? notifier.config.url.substring(0, 30) + '...' : notifier.config.broker || ''}</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={
                        notifier.type === 'telegram' ? 'default' :
                        notifier.type === 'email' ? 'secondary' :
                        notifier.type === 'webhook' ? 'outline' :
                        'outline'
                      } className="capitalize">
                        {t(`type${notifier.type.charAt(0).toUpperCase() + notifier.type.slice(1)}`)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {notifier.notify_on_trigger && (
                          <Bell className="w-4 h-4 text-green-600">
                            <title>{t('notifyOnTrigger')}</title>
                          </Bell>
                        )}
                        {notifier.notify_on_ack && (
                          <CheckCircle className="w-4 h-4 text-blue-600">
                            <title>{t('notifyOnAck')}</title>
                          </CheckCircle>
                        )}
                        {notifier.notify_on_resolve && (
                          <CheckCircle className="w-4 h-4 text-gray-600">
                            <title>{t('notifyOnResolve')}</title>
                          </CheckCircle>
                        )}
                        {!notifier.notify_on_trigger && !notifier.notify_on_ack && !notifier.notify_on_resolve && (
                          <span className="text-muted-foreground text-xs">{t('none')}</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={notifier.is_enabled ? 'default' : 'outline'}>
                        {notifier.is_enabled ? t('active') : t('inactive')}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon" onClick={() => handleEditNotifier(notifier)}>
                        <Edit className="w-4 h-4" />
                      </Button>
                      <Button 
                        variant="ghost" 
                        size="icon" 
                        onClick={() => handleTestNotifier(notifier.id)}
                        disabled={testLoading === notifier.id}
                      >
                        {testLoading === notifier.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <TestTube className="w-4 h-4" />}
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => handleDeleteNotifier(notifier.id)}>
                        <Trash2 className="w-4 h-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-center py-12">
              <Bot className="w-16 h-16 mx-auto mb-4 opacity-30" />
              <h3 className="text-lg font-medium mb-2">{t('noNotifiers')}</h3>
              <p className="text-muted-foreground mb-4">{t('noNotifiersDescription')}</p>
              <Button onClick={() => setShowCreateDialog(true)}>
                <Plus className="w-4 h-4 mr-2" />
                {t('createFirstNotifier')}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Telegram Bot Commands Reference */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="w-5 h-5" />
            {t('telegramBotCommands')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="font-mono text-sm space-y-2 bg-gray-900 text-green-400 p-4 rounded">
            <div className="text-primary font-bold mb-2">{t('telegramCommandsTitle')}</div>
            <div>/start - {t('cmdStart')}</div>
            <div>/status - {t('cmdStatus')}</div>
            <div>/sites - {t('cmdSites')}</div>
            <div>/alarms - {t('cmdAlarms')}</div>
            <div>/cameras - {t('cmdCameras')}</div>
            <div>/arm - {t('cmdArm')}</div>
            <div>/disarm - {t('cmdDisarm')}</div>
            <div>{`/actuator <id> on|off|toggle - ${t('cmdActuator')}`}</div>
            <div>{`/snapshot <camera_id> - ${t('cmdSnapshot')}`}</div>
            <div>/help - {t('cmdHelp')}</div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}