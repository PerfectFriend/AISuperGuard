import { useEffect, useCallback, useState } from 'react';

interface PushNotificationOptions {
  title: string;
  body: string;
  icon?: string;
  tag?: string;
  data?: any;
  actions?: Array<{ action: string; title: string }>;
  requireInteraction?: boolean;
}

export function usePushNotifications() {
  const [permission, setPermission] = useState<NotificationPermission>('default');
  const [supported, setSupported] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      setSupported(true);
      setPermission(Notification.permission);
    }
  }, []);

  const requestPermission = useCallback(async (): Promise<NotificationPermission> => {
    if (!supported) return 'denied';
    
    try {
      const perm = await Notification.requestPermission();
      setPermission(perm);
      return perm;
    } catch (error) {
      console.error('Failed to request notification permission:', error);
      return 'denied';
    }
  }, [supported]);

  const showNotification = useCallback((options: PushNotificationOptions): Notification | null => {
    if (!supported || permission !== 'granted') {
      console.warn('Notifications not supported or permission not granted');
      return null;
    }

    try {
      const notification = new Notification(options.title, {
        body: options.body,
        icon: options.icon || '/favicon.svg',
        tag: options.tag,
        data: options.data,
        requireInteraction: options.requireInteraction ?? true,
      });

      // Auto-close after 10 seconds unless requireInteraction
      if (!options.requireInteraction) {
        setTimeout(() => notification.close(), 10000);
      }

      return notification;
    } catch (error) {
      console.error('Failed to show notification:', error);
      return null;
    }
  }, [supported, permission]);

  const showAlarmNotification = useCallback((alarm: {
    id: string;
    camera_name: string;
    detection_class: string;
    confidence: number | null;
    site_name: string;
  }) => {
    return showNotification({
      title: `🚨 Тревога: ${alarm.detection_class}`,
      body: `${alarm.site_name} • ${alarm.camera_name} • ${alarm.confidence ? `${(alarm.confidence * 100).toFixed(0)}%` : 'N/A'}`,
      tag: `alarm-${alarm.id}`,
      data: { alarmId: alarm.id, type: 'alarm' },
      requireInteraction: true,
    });
  }, [showNotification]);

  const showSystemNotification = useCallback((title: string, body: string, tag?: string) => {
    return showNotification({
      title,
      body,
      tag: tag || `system-${Date.now()}`,
      data: { type: 'system' },
      requireInteraction: false,
    });
  }, [showNotification]);

  return {
    supported,
    permission,
    requestPermission,
    showNotification,
    showAlarmNotification,
    showSystemNotification,
  };
}