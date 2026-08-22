import { useEffect, useRef, useState, useCallback, useMemo } from 'react';

interface WebSocketMessage {
  type: string;
  payload: any;
  timestamp: string;
}

type MessageHandler = (message: WebSocketMessage) => void;

interface UseWebSocketOptions {
  url: string;
  handlers: Map<string, MessageHandler>;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  reconnect?: boolean;
  maxReconnectAttempts?: number;
  baseReconnectDelay?: number;
}

export function useWebSocket(options: UseWebSocketOptions) {
  const { url, handlers, onOpen, onClose, onError, reconnect = true, maxReconnectAttempts = 10, baseReconnectDelay = 1000 } = options;
  
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef(0);
  const handlersRef = useRef(handlers);
  
  // Keep handlers ref updated
  handlersRef.current = handlers;
  
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;
      
      ws.onopen = () => {
        setConnected(true);
        setError(null);
        reconnectAttempts.current = 0;
        console.log('[WebSocket] Connected to', url);
        onOpen?.();
      };
      
      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          const handler = handlersRef.current.get(message.type);
          if (handler) {
            handler(message);
          }
          // Call wildcard handlers
          handlersRef.current.forEach((h, type) => {
            if (type === '*') h(message);
          });
        } catch (err) {
          console.error('[WebSocket] Failed to parse message:', err);
        }
      };
      
      ws.onclose = () => {
        setConnected(false);
        console.log('[WebSocket] Disconnected from', url);
        onClose?.();
        
        if (reconnect && reconnectAttempts.current < maxReconnectAttempts) {
          const delay = baseReconnectDelay * Math.pow(2, reconnectAttempts.current);
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttempts.current++;
            connect();
          }, delay);
        } else if (reconnectAttempts.current >= maxReconnectAttempts) {
          setError('Max reconnection attempts reached');
        }
      };
      
      ws.onerror = (err) => {
        setError('WebSocket error');
        console.error('[WebSocket] Error:', err);
        onError?.(err);
      };
    } catch (err) {
      setError('Failed to create WebSocket connection');
      console.error('[WebSocket] Failed to create connection:', err);
    }
  }, [url, onOpen, onClose, onError, reconnect, maxReconnectAttempts, baseReconnectDelay]);
  
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, []);
  
  const send = useCallback((type: string, payload: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, payload, timestamp: new Date().toISOString() }));
      return true;
    }
    return false;
  }, []);
  
  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);
  
  return { connected, error, send, disconnect, reconnect: connect };
}

// Specialized hooks for common use cases - matching backend /ws/{site_id} endpoint
export function useSiteWebSocket(siteId: string, handlers: Map<string, (msg: any) => void> = new Map()) {
  return useWebSocket({
    url: `ws://${window.location.hostname}:3001/ws/${siteId}`,
    handlers,
  });
}

export function useAlarmWebSocket(siteId: string, onAlarm: (alarm: any) => void) {
  const handlers = useMemo(() => {
    const h = new Map<string, (msg: any) => void>();
    h.set('alarm.triggered', (msg) => onAlarm(msg.payload));
    h.set('alarm.acknowledged', (msg) => onAlarm(msg.payload));
    h.set('alarm.resolved', (msg) => onAlarm(msg.payload));
    return h;
  }, [onAlarm]);
  
  return useWebSocket({
    url: `ws://${window.location.hostname}:3001/ws/${siteId}`,
    handlers,
  });
}

export function useCameraWebSocket(siteId: string, onCameraUpdate: (camera: any) => void) {
  const handlers = useMemo(() => {
    const h = new Map<string, (msg: any) => void>();
    h.set('camera.status', (msg) => onCameraUpdate(msg.payload));
    return h;
  }, [onCameraUpdate]);
  
  return useWebSocket({
    url: `ws://${window.location.hostname}:3001/ws/${siteId}`,
    handlers,
  });
}

export function useActuatorWebSocket(siteId: string, onActuatorUpdate: (actuator: any) => void) {
  const handlers = useMemo(() => {
    const h = new Map<string, (msg: any) => void>();
    h.set('actuator.status', (msg) => onActuatorUpdate(msg.payload));
    h.set('actuator.command', (msg) => onActuatorUpdate(msg.payload));
    return h;
  }, [onActuatorUpdate]);
  
  return useWebSocket({
    url: `ws://${window.location.hostname}:3001/ws/${siteId}`,
    handlers,
  });
}

export function useDetectionWebSocket(siteId: string, onStats: (stats: any) => void) {
  const handlers = useMemo(() => {
    const h = new Map<string, (msg: any) => void>();
    h.set('detection.stats', (msg) => onStats(msg.payload));
    return h;
  }, [onStats]);
  
  return useWebSocket({
    url: `ws://${window.location.hostname}:3001/ws/${siteId}`,
    handlers,
  });
}

export function useSystemWebSocket(siteId: string, onHealth: (health: any) => void, onLog: (log: any) => void) {
  const handlers = useMemo(() => {
    const h = new Map<string, (msg: any) => void>();
    h.set('system.health', (msg) => onHealth(msg.payload));
    h.set('system.log', (msg) => onLog(msg.payload));
    return h;
  }, [onHealth, onLog]);
  
  return useWebSocket({
    url: `ws://${window.location.hostname}:3001/ws/${siteId}`,
    handlers,
  });
}